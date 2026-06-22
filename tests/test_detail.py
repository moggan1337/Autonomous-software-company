"""Drill-down detail: directive task trees and customer records."""
from fastapi.testclient import TestClient

from company.api import app


def test_directive_detail_has_tasks_and_artifacts(company):
    directive = company.submit_directive("Improve feature item z")
    company.run_until_idle()
    detail = company.directive_detail(directive.id)
    assert detail is not None
    assert detail["directive"]["id"] == directive.id
    assert detail["tasks"], "directive should have tasks"
    assert detail["artifacts"], "directive should have artifacts"
    assert detail["cost"] >= 0
    # Every artifact belongs to a task in this directive.
    task_ids = {t["id"] for t in detail["tasks"]}
    assert all(a["task_id"] in task_ids for a in detail["artifacts"])


def test_directive_detail_unknown_is_none(company):
    assert company.directive_detail("dir_missing") is None


def test_customer_detail_includes_deals(company):
    company.submit_directive("Increase sales pipeline for enterprise")
    company.run_until_idle()
    customers = company.db.get_customers(999)
    if customers:
        detail = company.customer_detail(customers[0]["id"])
        assert detail is not None
        assert detail["customer"]["id"] == customers[0]["id"]
        assert isinstance(detail["deals"], list)
        assert isinstance(detail["tickets"], list)


def test_customer_detail_unknown_is_none(company):
    assert company.customer_detail("cust_missing") is None


# ---- API ------------------------------------------------------------------
def test_directive_detail_endpoint():
    with TestClient(app) as client:
        created = client.post("/api/directive", json={"text": "Improve feature item z"}).json()
        did = created["directive"]["id"]
        res = client.get(f"/api/directives/{did}")
        assert res.status_code == 200
        assert res.json()["directive"]["id"] == did
        assert client.get("/api/directives/dir_missing").status_code == 404


def test_customer_detail_endpoint_404():
    with TestClient(app) as client:
        assert client.get("/api/customers/cust_missing").status_code == 404
