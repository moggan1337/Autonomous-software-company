"""The world (autopilot): inbound work the company generates and handles itself."""
from company.world import _ANALYTICS, _PRODUCT, _SALES, _SUPPORT, World


def _all_templates() -> set[str]:
    return set(_SUPPORT) | set(_SALES) | set(_PRODUCT) | set(_ANALYTICS)


def test_generate_one_submits_world_directive(company):
    directive = company.world.generate_one()
    assert directive.source == "world"
    dirs = company.db.get_directives()
    assert any(d["source"] == "world" for d in dirs)


def test_world_work_is_processed_end_to_end(company):
    company.world.generate_one()
    company.run_until_idle()
    tasks = company.db.get_tasks()
    assert tasks
    assert all(t.status.value in ("done", "blocked") for t in tasks)


def test_generated_text_comes_from_known_pools(company):
    templates = _all_templates()
    world = World(company.submit_directive, seed=7)
    for _ in range(20):
        d = world.generate_one()
        assert d.text in templates


def test_autopilot_reflected_in_snapshot(company):
    assert company.snapshot()["autopilot"] is False
