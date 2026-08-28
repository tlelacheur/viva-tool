import os
import uuid
import json
import logging
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings, storage_dir
from app.parser import extract_text_from_file
from app.openrouter import generate_viva_plan, evaluate_transcript, generate_adaptive_next_question
from app.livekit_worker import create_livekit_token, VivaSessionController

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("viva_backend")

app = FastAPI(
    title="Online Viva Tool API",
    description="Backend API for automated oral assessment (viva) tool",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for active sessions & reports (persisted to storage_dir as JSON)
SUBMISSIONS_DB: Dict[str, Dict[str, Any]] = {}
REPORTS_DB: Dict[str, Dict[str, Any]] = {}
ACTIVE_CONTROLLERS: Dict[str, VivaSessionController] = {}


class SessionCompleteRequest(BaseModel):
    transcript: List[Dict[str, Any]]
    telemetry_logs: List[Dict[str, Any]]


class TurnRequest(BaseModel):
    student_response: str
    current_transcript: Optional[List[Dict[str, Any]]] = None


@app.get("/")
def read_root():
    return {"message": "Viva Tool API is online", "version": "1.0.0"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/submissions", status_code=status.HTTP_201_CREATED)
async def create_submission(file: UploadFile = File(...)):
    """
    1. Accepts file upload (.txt, .md, .pdf)
    2. Parses raw text
    3. Calls OpenRouter to generate Viva Plan
    4. Creates LiveKit room token
    5. Returns submission metadata, token, and plan
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        raw_text = extract_text_from_file(file.filename, contents)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {str(e)}")

    # Generate unique submission ID
    submission_id = str(uuid.uuid4())
    room_name = f"viva_room_{submission_id[:8]}"

    # Generate Viva Plan using OpenRouter / fallback
    viva_plan = await generate_viva_plan(raw_text)

    # Generate LiveKit Token
    token = create_livekit_token(room_name=room_name, identity=f"student_{submission_id[:6]}")

    # Store submission record
    submission_record = {
        "submission_id": submission_id,
        "filename": file.filename,
        "artifact_text": raw_text,
        "viva_plan": viva_plan,
        "token": token,
        "livekit_url": settings.LIVEKIT_URL,
        "room_name": room_name
    }
    SUBMISSIONS_DB[submission_id] = submission_record

    # Initialize viva session controller
    ACTIVE_CONTROLLERS[submission_id] = VivaSessionController(submission_id, viva_plan)

    # Persist file copy to storage directory
    try:
        file_path = storage_dir / f"{submission_id}_{file.filename}"
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        logger.warning(f"Could not persist upload to disk: {e}")

    return {
        "submission_id": submission_id,
        "filename": file.filename,
        "token": token,
        "livekit_url": settings.LIVEKIT_URL,
        "viva_plan": viva_plan,
        "artifact_text_snippet": raw_text[:300] + ("..." if len(raw_text) > 300 else "")
    }


@app.get("/api/submissions/{submission_id}")
async def get_submission(submission_id: str):
    """Retrieve details for a specific submission."""
    if submission_id not in SUBMISSIONS_DB:
        raise HTTPException(status_code=404, detail="Submission not found")
    return SUBMISSIONS_DB[submission_id]


@app.post("/api/sessions/{submission_id}/turn")
async def process_turn(submission_id: str, request: TurnRequest):
    """Process one turn of question-answering during live viva with dynamic adaptive follow-ups."""
    submission = SUBMISSIONS_DB.get(submission_id)
    if submission_id not in ACTIVE_CONTROLLERS:
        if submission:
            ACTIVE_CONTROLLERS[submission_id] = VivaSessionController(
                submission_id, submission["viva_plan"]
            )
        else:
            raise HTTPException(status_code=404, detail="Session controller not found")

    controller = ACTIVE_CONTROLLERS[submission_id]
    result = controller.advance_turn(request.student_response)

    # Adaptively generate follow-up question via OpenRouter LLM based on student answer
    if not result.get("is_complete") and submission:
        artifact_text = submission.get("artifact_text", "")
        transcript_history = request.current_transcript or result.get("transcript", [])
        adaptive_q = await generate_adaptive_next_question(
            artifact_text, transcript_history, controller.current_question_index
        )
        if adaptive_q:
            result["next_question"] = adaptive_q

    return result


@app.post("/api/sessions/{submission_id}/complete")
async def complete_session(submission_id: str, req: SessionCompleteRequest):
    """
    1. Accepts transcript + telemetry logs
    2. Calls evaluate_transcript via OpenRouter / fallback
    3. Generates teacher report and stores it
    """
    submission = SUBMISSIONS_DB.get(submission_id)
    artifact_text = submission["artifact_text"] if submission else "No document text available."

    evaluation = await evaluate_transcript(artifact_text, req.transcript)

    report_data = {
        "report_id": submission_id,
        "submission_id": submission_id,
        "filename": submission.get("filename", "document.txt") if submission else "document.txt",
        "artifact_text": artifact_text,
        "viva_plan": submission.get("viva_plan") if submission else {},
        "transcript": req.transcript,
        "telemetry_logs": req.telemetry_logs,
        "evaluation": evaluation,
        "completed_at": json.dumps({"timestamp": os.path.basename(str(submission_id))})
    }

    REPORTS_DB[submission_id] = report_data

    # Save report to storage_dir JSON file
    try:
        report_file = storage_dir / f"report_{submission_id}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not persist report to disk: {e}")

    return {
        "status": "completed",
        "report_id": submission_id,
        "report": report_data
    }


@app.get("/api/reports/{report_id}")
async def get_report(report_id: str):
    """Returns full report data for teacher review."""
    if report_id in REPORTS_DB:
        return REPORTS_DB[report_id]

    # Try loading from disk
    report_file = storage_dir / f"report_{report_id}.json"
    if report_file.exists():
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                REPORTS_DB[report_id] = data
                return data
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading report: {e}")

    raise HTTPException(status_code=404, detail="Report not found")
