"""CRM / pipeline: customers, deals, and tickets created from agent activity."""
from company.config import Settings
from company.orchestrator import Company


def _company(tmp_path) -> Company:
    return Company(settings=Settings(
        api_key=None, model="claude-opus-4-8", effort="high",
        db_path=str(tmp_path / "c.db"), force_simulate=True, budget=25.0, api_token=None,
    ))


def test_completed_sales_creates_customer_and_deal(tmp_path):
    c = _company(tmp_path)
    # Many sales closes so both won and lost outcomes appear deterministically.
    for i in range(12):
        c.submit_directive(f"Increase sales pipeline for account {i}")
    c.run_until_idle()
    summary = c.db.crm_summary()
    assert summary["customers_total"] >= 1
    assert summary["deals_total"] >= 1
    assert summary["deals_won"] + summary["deals_lost"] == summary["deals_total"]
    # Revenue equals the sum of won-deal values only.
    won_value = sum(d["value"] for d in c.db.get_deals(999) if d["stage"] == "won")
    assert round(won_value, 2) == summary["revenue"]
    c.db.close()


def test_support_issue_creates_resolved_ticket(tmp_path):
    c = _company(tmp_path)
    c.submit_directive("A customer reports the export button is broken")
    c.run_until_idle()
    tickets = c.db.get_tickets()
    assert tickets, "a support issue should create a ticket"
    assert any(t["status"] == "resolved" for t in tickets)
    assert c.db.crm_summary()["tickets_resolved"] >= 1
    c.db.close()


def test_non_issue_support_makes_no_ticket(tmp_path):
    c = _company(tmp_path)
    # A pure product/feature directive: support only writes release notes, no ticket.
    c.submit_directive("Improve feature item q")
    c.run_until_idle()
    issue_tickets = c.db.get_tickets()
    # Release-notes / help-doc support work is not an issue, so no ticket is filed.
    assert all("broken" not in t["subject"].lower() for t in issue_tickets)
    c.db.close()


def test_active_customers_only_from_won_deals(tmp_path):
    c = _company(tmp_path)
    for i in range(12):
        c.submit_directive(f"Increase sales pipeline for account {i}")
    c.run_until_idle()
    customers = c.db.get_customers(999)
    active = [cu for cu in customers if cu["status"] == "active"]
    won = [d for d in c.db.get_deals(999) if d["stage"] == "won"]
    assert len(active) == len(won)
    c.db.close()


def test_snapshot_includes_crm(company):
    company.submit_directive("Increase sales pipeline for enterprise")
    company.run_until_idle()
    snap = company.snapshot()
    assert "crm" in snap
    assert "summary" in snap["crm"]
    assert isinstance(snap["crm"]["customers"], list)
    assert isinstance(snap["crm"]["deals"], list)
