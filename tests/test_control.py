"""Human-in-the-loop control: approval gates, agent config, cost tracking."""
from company.config import Settings
from company.models import Department, TaskStatus
from company.orchestrator import Company


def _awaiting(company):
    return [t for t in company.db.get_tasks() if t.status == TaskStatus.AWAITING_APPROVAL]


# ---- approval gates -------------------------------------------------------
def test_risky_work_waits_for_approval(company):
    company.set_approvals(True)
    company.submit_directive("Run a marketing campaign for new pricing")
    company.run_until_idle()
    awaiting = _awaiting(company)
    assert awaiting, "marketing work should be parked awaiting approval"
    # Parked work has not been done.
    assert all(t.status != TaskStatus.DONE for t in awaiting)


def test_approval_lets_work_proceed(company):
    company.set_approvals(True)
    company.submit_directive("Run a marketing campaign for new pricing")
    # Drain the approval queue: approve everything that parks, repeatedly.
    for _ in range(10):
        company.run_until_idle()
        pending = _awaiting(company)
        if not pending:
            break
        for t in pending:
            assert company.approve_task(t.id) is True
    company.run_until_idle()
    assert not _awaiting(company)
    assert any(t.status == TaskStatus.DONE for t in company.db.get_tasks())


def test_rejection_blocks_the_task(company):
    company.set_approvals(True)
    company.submit_directive("Send an outreach email blast to all customers")
    company.run_until_idle()
    awaiting = _awaiting(company)
    assert awaiting
    assert company.reject_task(awaiting[0].id) is True
    blocked = [t for t in company.db.get_tasks() if t.status == TaskStatus.BLOCKED]
    assert blocked and blocked[0].result == "Rejected by human"


def test_approvals_off_by_default(company):
    assert company.approvals_enabled is False
    company.submit_directive("Run a marketing campaign for new pricing")
    company.run_until_idle()
    assert not _awaiting(company)  # nothing parked when gating is off


# ---- agent config ---------------------------------------------------------
def test_disabled_department_stops_picking_up_work(company):
    company.update_agent_config(Department.MARKETING, enabled=False)
    company.submit_directive("Run a marketing campaign for new pricing")
    company.run_until_idle()
    marketing = [t for t in company.db.get_tasks() if t.department == Department.MARKETING]
    assert marketing
    assert all(t.status == TaskStatus.PENDING for t in marketing)
    # Re-enabling lets the work flow again.
    company.update_agent_config(Department.MARKETING, enabled=True)
    company.run_until_idle()
    assert any(t.status == TaskStatus.DONE for t in marketing_tasks(company))


def marketing_tasks(company):
    return [t for t in company.db.get_tasks() if t.department == Department.MARKETING]


def test_config_persists_and_reloads(company):
    company.update_agent_config(
        Department.SUPPORT, model="claude-haiku-4-5", instructions="Be terse."
    )
    cfg = company.config.get(Department.SUPPORT)
    assert cfg.model == "claude-haiku-4-5"
    assert cfg.instructions == "Be terse."
    # A fresh registry on the same DB sees the persisted config.
    from company.agentconfig import ConfigRegistry

    reloaded = ConfigRegistry(company.db).get(Department.SUPPORT)
    assert reloaded.model == "claude-haiku-4-5"
    assert reloaded.instructions == "Be terse."


# ---- cost / budget --------------------------------------------------------
def test_cost_is_tracked_per_department(company):
    company.submit_directive("Improve feature item z")
    company.run_until_idle()
    cost = company.db.cost_summary()
    assert cost["total_cost"] > 0
    assert cost["by_department"]
    assert company.snapshot()["metrics"]["cost"] > 0


def test_budget_alert_fires_when_exceeded(tmp_path):
    settings = Settings(
        api_key=None, model="claude-opus-4-8", effort="high",
        db_path=str(tmp_path / "c.db"), force_simulate=True, budget=0.0, api_token=None,
    )
    c = Company(settings=settings)
    c.submit_directive("Improve feature item z")
    c.run_until_idle()
    events = c.db.get_events()
    assert any("budget alert" in e["message"].lower() for e in events)
    c.db.close()
