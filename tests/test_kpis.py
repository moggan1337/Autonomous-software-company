"""KPI time series modeled from real company activity."""
from company.models import Department


def test_kpi_snapshots_accumulate(company):
    company.submit_directive("Improve feature item z")
    company.run_until_idle()
    kpis = company.db.get_kpis()
    assert len(kpis) >= 2
    # Snapshots are chronological and cumulative (non-decreasing deliverables).
    deliverables = [k["deliverables"] for k in kpis]
    assert deliverables == sorted(deliverables)


def test_sales_work_creates_crm_records(company):
    # A campaign cascades into a completed sales plan -> a CRM customer + deal.
    company.submit_directive("Run a marketing campaign for new pricing")
    company.run_until_idle()
    sales_done = [
        t for t in company.db.get_tasks()
        if t.department == Department.SALES and t.status.value == "done"
    ]
    crm = company.db.crm_summary()
    latest = company.snapshot()["kpi_latest"]
    if sales_done:
        assert crm["customers_total"] >= 1
        assert crm["deals_total"] >= 1
        # KPI revenue reads straight off won deals — they must agree.
        assert latest["revenue"] == crm["revenue"]


def test_snapshot_exposes_kpis(company):
    company.submit_directive("Improve feature item z")
    company.run_until_idle()
    snap = company.snapshot()
    assert "kpis" in snap and isinstance(snap["kpis"], list)
    assert "kpi_latest" in snap
    assert snap["kpi_latest"]["deliverables"] >= 1
