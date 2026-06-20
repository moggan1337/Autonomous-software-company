"""End-to-end behavior of the company engine in simulation mode."""
from company.models import Department, TaskStatus


def test_directive_creates_initial_tasks(company):
    directive = company.submit_directive("Launch a dark mode feature")
    assert directive.summary
    tasks = company.db.get_tasks(directive.id)
    assert tasks, "CEO must delegate at least one task"
    assert all(t.directive_id == directive.id for t in tasks)


def test_work_cascades_across_departments(company):
    company.submit_directive("Launch a dark mode feature")
    company.run_until_idle()

    tasks = company.db.get_tasks()
    departments_touched = {t.department for t in tasks}
    # A product directive should flow: product -> development -> qa -> support,
    # plus marketing -> sales. Verify the hand-offs actually happened.
    assert Department.PRODUCT in departments_touched
    assert Department.DEVELOPMENT in departments_touched
    assert Department.QA in departments_touched
    assert {Department.MARKETING, Department.SALES} & departments_touched


def test_everything_finishes_and_directive_closes(company):
    directive = company.submit_directive("Launch a dark mode feature")
    company.run_until_idle()

    tasks = company.db.get_tasks()
    assert tasks
    assert all(t.status in (TaskStatus.DONE, TaskStatus.BLOCKED) for t in tasks)

    directives = {d["id"]: d for d in company.db.get_directives()}
    assert directives[directive.id]["status"] == TaskStatus.DONE.value


def test_artifacts_are_produced(company):
    company.submit_directive("Launch a dark mode feature")
    company.run_until_idle()
    artifacts = company.db.get_artifacts()
    kinds = {a["kind"] for a in artifacts}
    assert "spec" in kinds
    assert "code" in kinds


def test_cascade_is_bounded(company):
    """The follow-up chain must terminate, not explode."""
    company.submit_directive("Launch a dark mode feature")
    worked = company.run_until_idle(max_rounds=100)
    assert worked > 0
    # Generous ceiling: a single directive should not generate hundreds of tasks.
    assert len(company.db.get_tasks()) < 40


def test_support_issue_routes_to_support_and_escalates(company):
    company.submit_directive("A customer reports the export button is broken")
    company.run_until_idle()
    tasks = company.db.get_tasks()
    depts = {t.department for t in tasks}
    assert Department.SUPPORT in depts
    # A reported bug should escalate from Support back to Product.
    assert Department.PRODUCT in depts


def test_snapshot_shape(company):
    company.submit_directive("Analyze last quarter retention")
    company.run_until_idle()
    snap = company.snapshot()
    assert snap["mode"] == "simulation"
    assert "departments" in snap and len(snap["departments"]) == 7
    assert snap["metrics"]["total_tasks"] >= 1
    assert isinstance(snap["events"], list)
