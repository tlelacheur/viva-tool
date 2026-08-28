import asyncio
import time
import logging
from typing import List, Dict, Any
from livekit import api
from app.config import settings

logger = logging.getLogger("livekit_worker")


def create_livekit_token(room_name: str, identity: str, name: str = "Student") -> str:
    """Generates a LiveKit JWT token for joining a WebRTC room."""
    try:
        grant = api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True
        )
        token = api.AccessToken(
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET
        ).with_identity(identity).with_name(name).with_grants(grant)
        return token.to_jwt()
    except Exception as e:
        logger.error(f"Error generating LiveKit token: {e}")
        # Fallback dummy token for development/POC simulation
        return f"mock_token_{room_name}_{identity}_{int(time.time())}"


class VivaSessionController:
    """
    Manages the sequential execution of questions during an active Viva session.
    Controls probe questions, perturbation question, turn transitions, and transcript logging.
    """
    def __init__(self, room_id: str, viva_plan: Dict[str, Any]):
        self.room_id = room_id
        self.viva_plan = viva_plan
        self.probe_questions = viva_plan.get("probe_questions", [])
        self.perturbation_question = viva_plan.get("perturbation_question", "")
        self.all_questions = list(self.probe_questions)
        if self.perturbation_question:
            self.all_questions.append(self.perturbation_question)
        
        self.current_question_index = 0
        self.transcript: List[Dict[str, Any]] = []

    def get_current_question(self) -> str:
        if 0 <= self.current_question_index < len(self.all_questions):
            return self.all_questions[self.current_question_index]
        return "The viva examination is now complete. Thank you."

    def advance_turn(self, student_response: str) -> Dict[str, Any]:
        """Record current Q&A turn and move to the next question."""
        question_asked = self.get_current_question()
        timestamp = time.strftime("%H:%M:%S")

        # Record examiner question entry
        self.transcript.append({
            "role": "examiner",
            "text": question_asked,
            "timestamp": timestamp,
            "question_index": self.current_question_index
        })

        # Record student response entry
        if student_response:
            self.transcript.append({
                "role": "student",
                "text": student_response,
                "timestamp": timestamp,
                "question_index": self.current_question_index
            })

        self.current_question_index += 1
        is_complete = self.current_question_index >= len(self.all_questions)

        return {
            "next_question": self.get_current_question() if not is_complete else None,
            "is_complete": is_complete,
            "transcript": self.transcript
        }
