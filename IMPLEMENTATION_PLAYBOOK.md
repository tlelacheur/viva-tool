# Antigravity Autonomous Build Playbook: Online Viva Tool PoC

## Goal
Build a working Proof of Concept for an automated oral assessment (viva) tool.
Students submit a document (PDF/text), an LLM generates a probing interview plan, 
a WebRTC voice session runs the interview, and a post-analysis report maps the 
student's defense against the submission for teacher review.

## System Architecture
1. Backend: FastAPI (Python 3.11) with OpenRouter API integration for LLMs and LiveKit for WebRTC room dispatching.
2. Frontend: Minimalist Svelte SPA compiled via Vite, connecting to LiveKit room via `livekit-client`.
3. Deployment: Docker Compose orchestrating Frontend + Backend containers.

## Execution Tasks for Agent

### Task 1: Backend Setup (`backend/app/`)
1. Create `config.py` loading environment variables via `pydantic-settings` or `os.environ`.
2. Implement `parser.py`:
   - Extract raw text from uploaded `.txt`, `.md`, and `.pdf` files using `pypdf`.
3. Implement `openrouter.py`:
   - Function `generate_viva_plan(artifact_text: str) -> dict`: Sends prompt to Claude 3.5 Sonnet / GPT-4o via OpenRouter.
     Enforce strict JSON schema output containing:
     - `summary`: string
     - `core_claims`: list of strings
     - `probe_questions`: list of 3 questions targeting specific methodologies/claims
     - `perturbation_question`: 1 question testing conceptual bounds
   - Function `evaluate_transcript(artifact_text: str, transcript: list) -> dict`: Compares transcript answers against the original text and returns comprehension score (1-5), authentication confidence (High/Med/Low), and flagged contradictions.
4. Implement `main.py` FastAPI routes:
   - `POST /api/submissions`: Accepts file upload, parses text, calls `generate_viva_plan`, creates a LiveKit room token, returns `{ submission_id, token, livekit_url, viva_plan }`.
   - `POST /api/sessions/{id}/complete`: Accepts transcript + telemetry logs, calls `evaluate_transcript`, saves and returns JSON report.
   - `GET /api/reports/{id}`: Returns full report data for teacher review.

### Task 2: LiveKit Voice Worker (`backend/app/livekit_worker.py`)
1. Implement basic agent script that connects to the generated room.
2. Step sequentially through the `probe_questions` and `perturbation_question` in the Viva Plan.
3. Manage turn transitions and log spoken transcript entries with timestamps.

### Task 3: Svelte Frontend (`frontend/src/`)
1. `App.svelte`:
   - View A: File upload form (PDF/Text) with a "Generate Viva" button.
   - View B: Live Room screen showing:
     - Connection status indicator.
     - Active speaker indicator (Examiner vs Student).
     - LiveKit audio player container.
     - End Viva button.
     - Focus listener using `document.visibilitychange` logging tab-switch events to an array.
   - View C: Teacher Report screen rendering JSON data:
     - Authentication status badge.
     - Submission text side-by-side with full transcript.
     - Timestamped telemetry log of tab switches.

### Task 4: Verification & Smoke Test
1. Start containers via `docker compose up -d --build`.
2. Execute an automated test uploading a dummy physics lab report.
3. Verify JSON generation from OpenRouter.
4. Validate that the Svelte build completes with zero errors and serves index.html on port 3000.