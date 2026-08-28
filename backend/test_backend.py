import asyncio
import io
import os
import json
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.parser import extract_text_from_file
from app.openrouter import generate_viva_plan, evaluate_transcript


class TestBackendPipeline(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    def test_parser(self):
        txt_content = b"This is a physics lab report on pendulum harmonic motion."
        text = extract_text_from_file("sample.txt", txt_content)
        self.assertIn("pendulum harmonic motion", text)

    def test_full_submission_and_evaluation_flow(self):
        # 1. Upload Submission
        sample_doc = (
            "Lab Report: Measuring Gravitational Acceleration using a Simple Pendulum.\n"
            "Hypothesis: The period T of a pendulum is proportional to the square root of length L.\n"
            "Methodology: We suspended a 50g brass bob using light thread at length 1.0m, 0.8m, 0.6m.\n"
            "Results: Measured g = 9.81 m/s^2 with 1.2% experimental uncertainty.\n"
            "Conclusion: The inverse square law holds and period matches theoretical predictions."
        )

        files = {
            "file": ("physics_lab_report.txt", sample_doc.encode("utf-8"), "text/plain")
        }

        res = self.client.post("/api/submissions", files=files)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        
        self.assertIn("submission_id", data)
        self.assertIn("token", data)
        self.assertIn("viva_plan", data)
        
        sub_id = data["submission_id"]
        viva_plan = data["viva_plan"]
        
        self.assertIn("summary", viva_plan)
        self.assertIn("probe_questions", viva_plan)
        self.assertEqual(len(viva_plan["probe_questions"]), 3)

        # 2. Process Turn
        turn_res = self.client.post(
            f"/api/sessions/{sub_id}/turn",
            json={"student_response": "We measured the length using a digital caliper with +/- 0.5mm precision."}
        )
        self.assertEqual(turn_res.status_code, 200)

        # 3. Complete Session
        transcript = [
            {"role": "examiner", "text": viva_plan["probe_questions"][0], "timestamp": "10:00:00"},
            {"role": "student", "text": "We calibrated the photogate timer before every trial run.", "timestamp": "10:00:15"},
            {"role": "examiner", "text": viva_plan["probe_questions"][1], "timestamp": "10:00:30"},
            {"role": "student", "text": "Air resistance was neglected because the bob velocity was well below turbulent flow thresholds.", "timestamp": "10:00:50"}
        ]
        telemetry = [
          {"type": "tab_visible", "description": "Viva room focused", "timestamp": "10:00:00"}
        ]

        complete_res = self.client.post(
            f"/api/sessions/{sub_id}/complete",
            json={"transcript": transcript, "telemetry_logs": telemetry}
        )
        self.assertEqual(complete_res.status_code, 200)
        report_data = complete_res.json()["report"]

        self.assertEqual(report_data["submission_id"], sub_id)
        self.assertIn("evaluation", report_data)
        eval_res = report_data["evaluation"]
        self.assertIn("comprehension_score", eval_res)
        self.assertIn("authentication_confidence", eval_res)

        # 4. Fetch Report via GET /api/reports/{id}
        get_report_res = self.client.get(f"/api/reports/{sub_id}")
        self.assertEqual(get_report_res.status_code, 200)
        self.assertEqual(get_report_res.json()["submission_id"], sub_id)


if __name__ == "__main__":
    unittest.main()
