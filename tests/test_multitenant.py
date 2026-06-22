"""Multi-company: independent companies sharing one deployment."""
from fastapi.testclient import TestClient

from company.api import app
from company.config import Settings
from company.manager import DEFAULT_ID, CompanyManager


def _manager(tmp_path) -> CompanyManager:
    settings = Settings(
        api_key=None, model="claude-opus-4-8", effort="high",
        db_path=str(tmp_path / "company.db"), force_simulate=True, budget=25.0, api_token=None,
    )
    return CompanyManager(settings)


def test_default_company_always_exists(tmp_path):
    mgr = _manager(tmp_path)
    assert mgr.get(DEFAULT_ID) is not None
    assert any(c["id"] == DEFAULT_ID for c in mgr.list())


def test_create_company_and_isolation(tmp_path):
    mgr = _manager(tmp_path)
    beta = mgr.create("Beta Inc")
    assert mgr.get(beta["id"]) is not None
    assert len(mgr.list()) == 2

    default = mgr.get(DEFAULT_ID)
    other = mgr.get(beta["id"])
    default.submit_directive("Improve feature item z")
    default.run_until_idle()
    other.submit_directive("Run a marketing campaign for new pricing")
    other.run_until_idle()

    # Each company only sees its own work — separate databases.
    default_titles = {t.title for t in default.db.get_tasks()}
    other_titles = {t.title for t in other.db.get_tasks()}
    assert default_titles and other_titles
    assert default_titles.isdisjoint(other_titles)

    default.db.close()
    other.db.close()


def test_unknown_company_is_none(tmp_path):
    assert _manager(tmp_path).get("co_missing") is None


def test_registry_persists_across_restart(tmp_path):
    mgr = _manager(tmp_path)
    beta = mgr.create("Beta Inc")
    for c in mgr.list():
        mgr.get(c["id"]).db.close()
    # A fresh manager on the same base dir reloads the registry.
    mgr2 = _manager(tmp_path)
    ids = {c["id"] for c in mgr2.list()}
    assert DEFAULT_ID in ids and beta["id"] in ids
    for c in mgr2.list():
        mgr2.get(c["id"]).db.close()


# ---- API ------------------------------------------------------------------
def test_companies_api_create_and_scope():
    with TestClient(app) as client:
        assert any(c["id"] == "default" for c in client.get("/api/companies").json()["companies"])
        created = client.post("/api/companies", json={"name": "Gamma"}).json()["company"]
        cid = created["id"]

        # Submit to the new company only; default stays empty of that work.
        client.post("/api/directive", params={"company": cid}, json={"text": "Improve feature item z"})
        new_state = client.get("/api/state", params={"company": cid}).json()
        assert new_state["metrics"]["total_tasks"] >= 1

        # Unknown company id 404s.
        assert client.get("/api/state", params={"company": "co_nope"}).status_code == 404
