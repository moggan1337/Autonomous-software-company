"""Security-hardening behaviors from the audit."""
import pytest

import company.db as dbmod
from company.config import Settings
from company.db import Database
from company.manager import CompanyManager
from company.models import Department, Event
from company.orchestrator import Company


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
