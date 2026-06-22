"""Standing orders: recurring directives the company runs on a schedule."""
from company.models import now


def test_create_standing_order(company):
    order = company.create_standing_order("Analyze retention and report", 30)
    assert order["text"] == "Analyze retention and report"
    assert order["enabled"] is True
    assert order["next_run"] > now()
    assert company.db.get_standing_orders()


def test_due_order_fires_and_reschedules(company):
    order = company.create_standing_order("Analyze retention and report", 5)
    # Force it due.
    company.db.update_standing_order(order["id"], next_run=now() - 1)
    fired = company.run_due_schedules()
    assert fired == 1

    # A scheduled directive was created and processed.
    dirs = company.db.get_directives()
    assert any(d["source"] == "schedule" for d in dirs)
    company.run_until_idle()
    assert any(t.status.value == "done" for t in company.db.get_tasks())

    # It was rescheduled into the future and the run count advanced.
    refreshed = company.db.get_standing_orders()[0]
    assert refreshed["runs"] == 1
    assert refreshed["next_run"] > now()


def test_disabled_order_does_not_fire(company):
    order = company.create_standing_order("Analyze retention and report", 5)
    company.toggle_standing_order(order["id"])  # pause
    company.db.update_standing_order(order["id"], next_run=now() - 1)
    assert company.run_due_schedules() == 0


def test_toggle_and_delete(company):
    order = company.create_standing_order("Weekly marketing review", 60)
    toggled = company.toggle_standing_order(order["id"])
    assert toggled["enabled"] is False
    assert company.delete_standing_order(order["id"]) is True
    assert company.db.get_standing_orders() == []
    assert company.delete_standing_order("ord_missing") is False


def test_schedules_in_snapshot(company):
    company.create_standing_order("Analyze retention and report", 30)
    snap = company.snapshot()
    assert "schedules" in snap
    assert len(snap["schedules"]) == 1
