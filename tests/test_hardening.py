"""Security-hardening behaviors from the audit."""
import pytest
from fastapi.testclient import TestClient

import company.api as api
import company.db as dbmod
from company.api import app
from company.config import Settings
from company.db import Database
from company.manager import CompanyManager
from company.models import Department, Event
from company.orchestrator import Company
from company.ratelimit import RateLimiter


def _settings(tmp_path) -> Settings:
    return Settings(
        api_key=None, model="claude-opus-4-8", effort="high",
        db_path=str(tmp_path / "company.db"), force_simulate=True, budget=25.0, api_token=None,
    )


def test_company_cap_enforced(tmp_path):
    mgr = CompanyManager(_settings(tmp_path))
    mgr.max_companies = 2  # default already occupies one slot
    mgr.create("Second")
    with pytest.raises(ValueError):
        mgr.create("Third — over the cap")
    for c in mgr.list():
        mgr.get(c["id"]).db.close()


def test_invalid_company_id_rejected(tmp_path):
    mgr = CompanyManager(_settings(tmp_path))
    with pytest.raises(ValueError):
        mgr._instantiate({"id": "../../etc/passwd", "name": "evil", "created_at": 0.0})
    for c in mgr.list():
        mgr.get(c["id"]).db.close()


def test_log_messages_are_sanitized(tmp_path):
    c = Company(settings=_settings(tmp_path))
    c.submit_directive("hello\nINFO forged log line\r\ndrop table")
    # No stored activity message may contain control characters.
    assert all("\n" not in e["message"] and "\r" not in e["message"] for e in c.db.get_events())
    c.db.close()


def test_update_rejects_illegal_column_names(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    with pytest.raises(ValueError):
        db.update_task("whatever", **{"status; DROP TABLE tasks": "x"})
    db.close()


def test_events_table_is_trimmed(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "EVENTS_KEEP", 5)
    db = Database(str(tmp_path / "t.db"))
    for i in range(20):
        db.add_event(Event(department=Department.CEO, message=str(i), kind="info"))
    assert len(db.get_events(1000)) <= 5
    db.close()


def test_rate_limiter_allows_then_blocks():
    rl = RateLimiter(limit=3, window=60)
    key = "1.2.3.4"
    assert all(rl.check(key)[0] for _ in range(3))
    allowed, retry_after = rl.check(key)
    assert allowed is False
    assert retry_after > 0


def test_rate_limiter_disabled_when_zero():
    rl = RateLimiter(limit=0, window=60)
    assert all(rl.check("x")[0] for _ in range(1000))


def test_api_rate_limit_returns_429(monkeypatch):
    monkeypatch.setattr(api, "RATE_LIMITER", RateLimiter(limit=2, window=60))
    with TestClient(app) as client:
        assert client.post("/api/world/start").status_code == 200
        assert client.post("/api/world/stop").status_code == 200
        blocked = client.post("/api/world/start")
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        # Reads are never rate-limited.
        assert client.get("/api/state").status_code == 200
