"""The QA rework loop: QA can reject work, send it back, and always terminate."""
from company.models import Department, TaskStatus
from company.orchestrator import MAX_REWORK


def _directive(parity: int) -> str:
    """Build a product directive of a given QA parity (0 = rejected on first pass)."""
    for suffix in "abcdefghijklmnopqrstuvwxyz":
        cand = f"Improve feature item {suffix}"
        if sum(ord(c) for c in cand[:70]) % 2 == parity:
            return cand
    raise AssertionError("no candidate found")  # pragma: no cover


def _flaky_directive() -> str:
    return _directive(0)


def _stable_directive() -> str:
    return _directive(1)


def test_rejected_build_triggers_rework_then_ships(company):
    company.submit_directive(_flaky_directive())
    company.run_until_idle()

    tasks = company.db.get_tasks()
    assert any(t.rework_count > 0 for t in tasks), "a rework task should have been opened"

    # QA rejected at least once, visible in the activity feed.
    events = company.db.get_events()
    assert any("rework" in e["message"].lower() for e in events)

    # The feature still ships: QA eventually approved -> Support release notes.
    assert any(t.department == Department.SUPPORT for t in tasks)


def test_rework_is_bounded_and_terminates(company):
    company.submit_directive(_flaky_directive())
    company.run_until_idle()
    tasks = company.db.get_tasks()
    assert max(t.rework_count for t in tasks) <= MAX_REWORK
    assert all(t.status in (TaskStatus.DONE, TaskStatus.BLOCKED) for t in tasks)


def test_stable_feature_passes_without_rework(company):
    company.submit_directive(_stable_directive())
    company.run_until_idle()
    tasks = company.db.get_tasks()
    assert all(t.rework_count == 0 for t in tasks)
    assert any(t.department == Department.QA for t in tasks)
    assert any(t.department == Department.SUPPORT for t in tasks)
