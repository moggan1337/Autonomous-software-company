"""HTTP surface: health, directive submission, and live state snapshot."""
import time

from fastapi.testclient import TestClient

from company.api import app


def test_health_reports_simulation_mode():
    with TestClient(app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["mode"] == "simulation"


def test_submit_directive_and_observe_work():
    with TestClient(app) as client:
        res = client.post("/api/directive", json={"text": "Launch a dark mode feature"})
        assert res.status_code == 200
        assert res.json()["directive"]["text"] == "Launch a dark mode feature"

        # The background worker should process the cascade; poll briefly.
        done = 0
        for _ in range(40):
            snap = client.get("/api/state").json()
            done = snap["metrics"]["done"]
            if done >= 3:
                break
            time.sleep(0.25)
        assert done >= 3


def test_directive_validation_rejects_empty():
    with TestClient(app) as client:
        res = client.post("/api/directive", json={"text": ""})
        assert res.status_code == 422
