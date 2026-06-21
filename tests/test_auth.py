"""Optional API-token auth: gates state-changing requests when configured."""
from fastapi.testclient import TestClient

import company.api as api
from company.api import app


def test_no_token_means_open(monkeypatch):
    monkeypatch.setattr(api, "API_TOKEN", None)
    with TestClient(app) as client:
        assert client.post("/api/world/start").status_code == 200
        client.post("/api/world/stop")


def test_token_required_for_mutations(monkeypatch):
    monkeypatch.setattr(api, "API_TOKEN", "secret")
    with TestClient(app) as client:
        # Reads stay open.
        assert client.get("/api/state").status_code == 200
        # Mutations without the token are rejected.
        assert client.post("/api/world/start").status_code == 401
        # With the token they succeed (header or bearer).
        ok = client.post("/api/world/start", headers={"Authorization": "Bearer secret"})
        assert ok.status_code == 200
        client.post("/api/world/stop", headers={"X-API-Token": "secret"})


def test_wrong_token_rejected(monkeypatch):
    monkeypatch.setattr(api, "API_TOKEN", "secret")
    with TestClient(app) as client:
        res = client.put("/api/agents/support", json={"enabled": True},
                         headers={"Authorization": "Bearer nope"})
        assert res.status_code == 401
