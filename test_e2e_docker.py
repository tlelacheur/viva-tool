import requests
import json
import time

def test_docker_e2e():
    print("==> Testing Docker End-to-End Viva Workflow...")
    base_url = "http://localhost:8000"

    # 1. Check health
    r = requests.get(f"{base_url}/health")
    assert r.status_code == 200, f"Health check failed: {r.text}"
    print("✔ 1. Health check passed:", r.json())

    # 2. Upload Dummy Physics Lab Report
    physics_report = """
    PHYSICS EXPERIMENTAL LAB REPORT: QUANTUM HALL EFFECT
    Author: Jane Doe
    
    1. Abstract:
    We present measurements of the transverse Hall resistance R_xy in a high-mobility two-dimensional electron gas (2DEG) at cryogenic temperatures (T = 1.5 K) under intense perpendicular magnetic fields (B up to 12 Tesla).
    
    2. Key Claims:
    - Hall resistance plateaus are quantized at R_H = h / (e^2 * nu) with filling factor nu = 1, 2, 3.
    - Longitudinal resistance R_xx drops to zero simultaneously at plateau centers.
    - Quantum precision observed within 1 part in 10^7.
    
    3. Methodology:
    Hall bar geometry fabricated via GaAs/AlGaAs heterostructure. Lock-in amplifiers used to measure current I = 100 nA at low frequency 13 Hz.
    
    4. Conclusion:
    The fundamental constant ratio h/e^2 is confirmed with exceptional accuracy, proving topological edge state quantization.
    """

    files = {
        "file": ("quantum_hall_lab_report.txt", physics_report.encode("utf-8"), "text/plain")
    }

    r = requests.post(f"{base_url}/api/submissions", files=files)
    assert r.status_code == 201, f"Submission failed: {r.text}"
    sub_data = r.json()
    sub_id = sub_data["submission_id"]
    plan = sub_data["viva_plan"]
    print("✔ 2. Submission uploaded successfully. ID:", sub_id)
    print("   Generated Viva Plan Summary:", plan.get("summary"))
    print("   Probe Questions:", json.dumps(plan.get("probe_questions"), indent=2))
    print("   Perturbation Question:", plan.get("perturbation_question"))

    # 3. Simulate Viva Turn
    r = requests.post(
        f"{base_url}/api/sessions/{sub_id}/turn",
        json={"student_response": "We calibrated our lock-in amplifier at 13 Hz to minimize 50 Hz power-line interference."}
    )
    assert r.status_code == 200, f"Turn processing failed: {r.text}"
    print("✔ 3. Turn processed successfully:", r.json())

    # 4. Complete Session & Generate Report
    transcript = [
        {"role": "examiner", "text": plan["probe_questions"][0], "timestamp": "10:15:00"},
        {"role": "student", "text": "The lock-in amplifier was isolated using low-noise pre-amplifiers to achieve microvolt resolution.", "timestamp": "10:15:20"},
        {"role": "examiner", "text": plan["probe_questions"][1], "timestamp": "10:15:40"},
        {"role": "student", "text": "Zero longitudinal resistance arises because edge states propagate without backscattering.", "timestamp": "10:16:05"}
    ]
    telemetry = [
        {"type": "tab_visible", "description": "Student initialized session", "timestamp": "10:15:00"},
        {"type": "tab_hidden", "description": "Student switched away for 3s", "timestamp": "10:15:30"},
        {"type": "tab_visible", "description": "Student returned", "timestamp": "10:15:33"}
    ]

    r = requests.post(
        f"{base_url}/api/sessions/{sub_id}/complete",
        json={"transcript": transcript, "telemetry_logs": telemetry}
    )
    assert r.status_code == 200, f"Complete session failed: {r.text}"
    report_resp = r.json()
    report = report_resp["report"]
    print("✔ 4. Session completed. Evaluation Report generated:")
    print("   Comprehension Score:", report["evaluation"]["comprehension_score"])
    print("   Authentication Confidence:", report["evaluation"]["authentication_confidence"])
    print("   Flagged Contradictions:", report["evaluation"]["flagged_contradictions"])
    print("   Summary Evaluation:", report["evaluation"]["summary_evaluation"])

    # 5. Fetch Report via GET /api/reports/{id}
    r = requests.get(f"{base_url}/api/reports/{sub_id}")
    assert r.status_code == 200, f"Get report failed: {r.text}"
    assert r.json()["submission_id"] == sub_id
    print("✔ 5. GET /api/reports/{id} returned report successfully.")

    # 6. Verify Frontend
    r = requests.get("http://localhost:3000")
    assert r.status_code == 200, f"Frontend request failed: {r.status_code}"
    assert "VivaTool" in r.text or "<div id=\"app\"></div>" in r.text
    print("✔ 6. Frontend Svelte application serving on http://localhost:3000.")

    print("\nALL END-TO-END SMOKE TESTS PASSED CLEANLY!")

if __name__ == "__main__":
    test_docker_e2e()
