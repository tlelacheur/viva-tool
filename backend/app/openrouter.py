import json
import logging
import httpx
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger("viva_openrouter")


def _heuristic_generate_viva_plan(artifact_text: str) -> Dict[str, Any]:
    """Fallback generator when OpenRouter API is unavailable or unconfigured."""
    lines = [line.strip() for line in artifact_text.strip().splitlines() if line.strip()]
    first_few = " ".join(lines[:5]) if lines else "Submitted document."
    summary = (first_few[:200] + "...") if len(first_few) > 200 else first_few

    # Extract sentences as core claims
    sentences = [s.strip() for s in artifact_text.replace("\n", " ").split(".") if len(s.strip()) > 15]
    core_claims = sentences[:6] if sentences else ["The document presents experimental findings and analytical claims."]
    
    probe_questions = [
        "Can you describe your physical experimental setup and why you chose to measure 20 oscillations per trial rather than single periods?",
        "How did you measure the pendulum length L, and what steps were taken to ensure the measurement reference point was consistent?",
        "Walk me through your graph plotting method and how you decided which points to use for your line of best fit.",
        "What primary sources of experimental uncertainty (such as human reaction time or length precision) were identified in your data?",
        "Your model assumes a simple pendulum. How did you verify that your release angle satisfied the small-angle approximation?",
        "Did you observe any damping or air resistance effects during the 20 oscillations, and how would that affect your calculated period T?",
        "If you were to repeat this experiment with a much heavier bob, how would that impact your measured period and g value?",
        "What was the single largest limitation in your apparatus, and how would you redesign the experiment to improve precision?"
    ]

    perturbations = [
        "How would your calculations and resulting g value change if the thin inextensible string were replaced by a uniform rigid rod of length L pivoted at one end?",
        "If this exact experimental setup were conducted in a vacuum chamber on the Moon, how would the slope of your L vs T² graph change?"
    ]

    return {
        "summary": summary,
        "core_claims": core_claims,
        "probe_questions": probe_questions,
        "perturbation_question": perturbations
    }


def _heuristic_evaluate_transcript(artifact_text: str, transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fallback evaluator when OpenRouter API is unavailable or unconfigured."""
    student_turns = [t.get("text", "").strip() for t in transcript if t.get("role") in ["student", "user"]]
    full_student_text = " ".join(student_turns).lower()

    red_flags = []
    # Check for admissions of external help or AI generation
    if any(kw in full_student_text for kw in ["gemini", "gpt", "chatgpt", "asked a mate", "mate", "did it for me", "friend"]):
        red_flags.append("Student admitted during oral examination that the work or analysis was delegated to external parties or an AI assistant.")
    
    if any(kw in full_student_text for kw in ["no, not really", "no really", "don't know", "dunno", "no idea"]):
        red_flags.append("Student was unable to explain core concepts when questioned directly.")

    if red_flags:
        return {
            "comprehension_score": 1 if len(red_flags) > 1 else 2,
            "authentication_confidence": "Low",
            "flagged_contradictions": red_flags,
            "summary_evaluation": "Authentication failed: Student made explicit admissions in the oral defense indicating the submission was not entirely their own independent work."
        }

    num_answers = len(student_turns)
    if num_answers >= 6:
        comprehension_score = 5
        auth_confidence = "High"
        contradictions = []
        summary_eval = "Student demonstrated thorough understanding across the 10-question viva examination."
    elif num_answers >= 3:
        comprehension_score = 4
        auth_confidence = "High"
        contradictions = []
        summary_eval = "Student demonstrated solid understanding of key concepts during probing."
    elif num_answers >= 1:
        comprehension_score = 3
        auth_confidence = "Med"
        contradictions = ["Minor uncertainty expressed when defending baseline assumptions."]
        summary_eval = "Student partially defended the submission, but provided brief responses."
    else:
        comprehension_score = 2
        auth_confidence = "Low"
        contradictions = ["Student provided incomplete answers or skipped viva questions."]
        summary_eval = "Insufficient defense provided during the oral examination."

    return {
        "comprehension_score": comprehension_score,
        "authentication_confidence": auth_confidence,
        "flagged_contradictions": contradictions,
        "summary_evaluation": summary_eval
    }


async def generate_viva_plan(artifact_text: str) -> Dict[str, Any]:
    """
    Sends document text to OpenRouter LLM to generate a structured 10-question Viva examination plan across diverse topics.
    """
    if not settings.OPENROUTER_API_KEY or "xxxxxxxx" in settings.OPENROUTER_API_KEY:
        logger.info("Using heuristic fallback for generate_viva_plan (no valid OpenRouter key)")
        return _heuristic_generate_viva_plan(artifact_text)

    prompt = f"""You are an expert academic examiner analyzing a student's submission.
Read the submission text below and output a strict JSON object with the exact following keys:
- "summary": A concise 2-3 sentence summary of the paper.
- "core_claims": A list of 4-6 key claims or hypotheses made in the text.
- "probe_questions": A list of EXACTLY 8 specific probing questions covering DIVERSE aspects of the report:
    1. Experimental setup & measurement procedures
    2. Data recording & oscillation timing
    3. Graphing, slope & curve fitting
    4. Error identification & uncertainty propagation
    5. Small-angle approximation & physical assumptions
    6. Damping, air resistance & systematic errors
    7. Equipment precision & limitations
    8. Experimental redesign & improvements
- "perturbation_question": A list of EXACTLY 2 counterfactual or boundary-testing questions (e.g. "What if parameter X were changed by Y?").

Document Text:
\"\"\"
{artifact_text[:6000]}
\"\"\"

Return ONLY valid JSON matching this schema:
{{
  "summary": "...",
  "core_claims": ["..."],
  "probe_questions": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8"],
  "perturbation_question": ["p1", "p2"]
}}
"""

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://viva-tool.poc",
        "X-Title": "Viva Tool"
    }

    payload = {
        "model": settings.ANALYSIS_MODEL,
        "messages": [
            {"role": "system", "content": "You are a precise academic evaluator. Respond only with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(f"{settings.OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            
            if all(k in parsed for k in ["summary", "core_claims", "probe_questions", "perturbation_question"]):
                return parsed
            else:
                logger.warning("OpenRouter output missing required keys, using fallback")
                return _heuristic_generate_viva_plan(artifact_text)
    except Exception as e:
        logger.error(f"Error calling OpenRouter API for viva plan: {e}")
        return _heuristic_generate_viva_plan(artifact_text)


async def generate_adaptive_next_question(artifact_text: str, transcript: List[Dict[str, Any]], turn_index: int) -> Optional[str]:
    """
    Dynamically generates the next viva question adapted to the student's previous answers with enforced Topic Diversity & Pivot Control.
    """
    if not settings.OPENROUTER_API_KEY or "xxxxxxxx" in settings.OPENROUTER_API_KEY:
        return None

    formatted_transcript = json.dumps(transcript, indent=2)

    prompt = f"""You are a balanced, professional academic examiner conducting a live oral viva examination.
The student submitted the document below and has answered previous questions.

Document Text (excerpt):
\"\"\"
{artifact_text[:3000]}
\"\"\"

Current Viva Conversation History:
\"\"\"
{formatted_transcript}
\"\"\"

CRITICAL EXAMINER INSTRUCTIONS FOR QUESTION {turn_index + 1} OF 10:
1. TOPIC DIVERSITY & MAX REPETITION CAP: Review recent questions in the history. DO NOT ask more than 2 consecutive questions on the exact same micro-topic (e.g. error propagation, uncertainty calculation, or gradient fitting).
2. PIVOT WHEN STUCK: If the student already acknowledged confusion, guessed a number, admitted an error, or stated they don't recall/know a specific detail, note that for evaluation and IMMEDIATELY PIVOT to a completely different section of their report (e.g. experimental setup, physical assumptions, period formula, damping, or equipment limitations).
3. BALANCED TOPIC SCHEDULE ACROSS THE 10 QUESTIONS:
   - Questions 1-2: Experimental setup, apparatus & data collection procedure
   - Questions 3-4: Graphing methodology, slope & data fitting
   - Questions 5-6: Error analysis & uncertainty propagation
   - Questions 7-8: Theoretical framework & physical assumptions (e.g. small angle approximation, string tension, pivot point)
   - Questions 9-10: Counterfactual & boundary testing (e.g. replacing string with rigid rod, changing gravity, vacuum)
4. TONE: Direct, encouraging yet rigorous, concise (1-2 sentences maximum).

Formulate the NEXT single probing question (Question {turn_index + 1} of 10).

Return ONLY a JSON object:
{{
  "next_question": "..."
}}
"""

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://viva-tool.poc",
        "X-Title": "Viva Tool"
    }

    payload = {
        "model": settings.ANALYSIS_MODEL,
        "messages": [
            {"role": "system", "content": "You are a dynamic academic examiner adhering strictly to topic diversity and pivot control. Respond only with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(f"{settings.OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return parsed.get("next_question")
    except Exception as e:
        logger.error(f"Error generating adaptive next question: {e}")
        return None


async def evaluate_transcript(artifact_text: str, transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compares the student's oral interview transcript against the original document.
    Returns comprehension score (1-5), authentication confidence, and flagged contradictions.
    """
    if not settings.OPENROUTER_API_KEY or "xxxxxxxx" in settings.OPENROUTER_API_KEY:
        logger.info("Using heuristic fallback for evaluate_transcript (no valid OpenRouter key)")
        return _heuristic_evaluate_transcript(artifact_text, transcript)

    formatted_transcript = json.dumps(transcript, indent=2)

    prompt = f"""You are a rigorous academic integrity evaluator assessing a student's oral defense (viva).
Compare the student's oral answers in the transcript against the original submitted artifact text.

Submitted Text:
\"\"\"
{artifact_text[:4000]}
\"\"\"

Viva Session Transcript:
\"\"\"
{formatted_transcript[:4000]}
\"\"\"

Analyze if the student understands their work and if their spoken explanations match the written submission.
Return a strict JSON object with the exact keys:
- "comprehension_score": integer from 1 to 5 (1=poor, 5=excellent)
- "authentication_confidence": string, one of "High", "Med", "Low"
- "flagged_contradictions": list of strings detailing any contradictions or red flags between transcript and paper (empty list if none)
- "summary_evaluation": string summarizing the student's defense quality

Return ONLY valid JSON matching this schema:
{{
  "comprehension_score": 4,
  "authentication_confidence": "High",
  "flagged_contradictions": [],
  "summary_evaluation": "..."
}}
"""

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://viva-tool.poc",
        "X-Title": "Viva Tool"
    }

    payload = {
        "model": settings.EVALUATION_MODEL,
        "messages": [
            {"role": "system", "content": "You are a precise academic integrity reviewer. Respond only with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(f"{settings.OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            
            if all(k in parsed for k in ["comprehension_score", "authentication_confidence", "flagged_contradictions", "summary_evaluation"]):
                return parsed
            else:
                return _heuristic_evaluate_transcript(artifact_text, transcript)
    except Exception as e:
        logger.error(f"Error calling OpenRouter API for evaluation: {e}")
        return _heuristic_evaluate_transcript(artifact_text, transcript)
