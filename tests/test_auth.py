"""Optional API-token auth: when set, gates ALL /api requests (reads included)."""
from fastapi.testclient import TestClient

import company.api as api
from company.api import app


def test_no_token_means_open(monkeypatch):
    monkeypatch.setattr(api, "API_TOKEN", None)
    with TestClient(app) as client:
        assert client.get("/api/state").status_code == 200
        assert client.post("/api/world/start").status_code == 200
        client.post("/api/world/stop")


def test_token_required_for_reads_and_writes(monkeypatch):
    monkeypatch.setattr(api, "API_TOKEN", "secret")
    with TestClient(app) as client:
        # Health stays open (liveness probe).
        assert client.get("/api/health").status_code == 200
        # Reads now require the token too — tenant data must not leak.
        assert client.get("/api/state").status_code == 401
        assert client.get("/api/companies").status_code == 401
        # Mutations without the token are rejected.
        assert client.post("/api/world/start").status_code == 401
        # With the token, both reads and writes succeed (bearer / header / query).
        assert client.get("/api/state", headers={"Authorization": "Bearer secret"}).status_code == 200
        assert client.get("/api/state", headers={"X-API-Token": "secret"}).status_code == 200
        assert client.get("/api/state", params={"token": "secret"}).status_code == 200
        assert client.post("/api/world/start", headers={"Authorization": "Bearer secret"}).status_code == 200
        client.post("/api/world/stop", headers={"Authorization": "Bearer secret"})


def test_wrong_token_rejected(monkeypatch):
    monkeypatch.setattr(api, "API_TOKEN", "secret")
    with TestClient(app) as client:
        assert client.get("/api/state", headers={"Authorization": "Bearer nope"}).status_code == 401
        res = client.put("/api/agents/support", json={"enabled": True},
                         headers={"Authorization": "Bearer nope"})
        assert res.status_code == 401
