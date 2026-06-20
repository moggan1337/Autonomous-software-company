"""The real tools: company memory, grounded metrics, and code validation."""
from pathlib import Path

from company.db import Database
from company.models import Artifact, Department
from company.tools import ToolBox


def _toolbox(tmp_path) -> ToolBox:
    db = Database(str(tmp_path / "t.db"))
    return ToolBox(db, Path(tmp_path) / "ws")


def test_recall_finds_relevant_prior_work(tmp_path):
    tb = _toolbox(tmp_path)
    tb.db.add_artifact(Artifact(
        title="Spec: dark mode", department=Department.PRODUCT, kind="spec",
        content="A theme toggle for dark and light appearance.",
    ))
    tb.db.add_artifact(Artifact(
        title="Sales Plan: pricing", department=Department.SALES, kind="plan",
        content="Outreach for enterprise pricing accounts.",
    ))
    hits = tb.recall("implement dark mode theme")
    assert hits, "should recall the relevant spec"
    assert hits[0]["title"] == "Spec: dark mode"


def test_recall_summary_is_empty_without_matches(tmp_path):
    tb = _toolbox(tmp_path)
    assert tb.recall_summary("nonexistent topic xyzzy") == ""


def test_company_metrics_reads_real_data(tmp_path):
    tb = _toolbox(tmp_path)
    from company.models import Task, TaskStatus
    t = tb.db.add_task(Task(title="x", department=Department.PRODUCT))
    tb.db.update_task(t.id, status=TaskStatus.DONE)
    tb.db.add_artifact(Artifact(title="a", department=Department.PRODUCT, kind="spec", content="c"))
    m = tb.company_metrics()
    assert m["total_tasks"] == 1
    assert m["completed"] == 1
    assert m["deliverables"] == 1
    assert "product" in m["throughput_by_department"]


def test_validate_code_accepts_good_and_rejects_bad(tmp_path):
    tb = _toolbox(tmp_path)
    ok, _ = tb.validate_code("good", "def f():\n    return 1\n")
    assert ok is True
    bad_ok, detail = tb.validate_code("bad", "def f(:\n    return\n")
    assert bad_ok is False
    assert detail
