"""The company engine.

Holds the CEO and the seven department agents, accepts human directives, and
runs the work loop: each department repeatedly claims its next task, the agent
does the work, and any follow-ups are queued for other departments. A depth
limit keeps the natural cascade (spec -> build -> QA -> docs) from running
forever.

The engine is safe to drive two ways:
  * `tick()` / `run_until_idle()` — synchronous, used by tests and the simulator.
  * `start()` / `stop()` — a background thread that ticks continuously so the
    dashboard shows work happening live.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from .agents import AGENT_CLASSES, CEOAgent
from .config import SETTINGS, Settings
from .db import Database
from .llm import LLMClient
from .models import (
    Department,
    Directive,
    Event,
    Priority,
    Task,
    TaskStatus,
    WORKER_DEPARTMENTS,
)
from .tools import ToolBox

log = logging.getLogger("company.orchestrator")

MAX_DEPTH = 8   # how many hand-offs deep the cascade may run
MAX_REWORK = 2  # how many times QA may send a feature back before it ships anyway

_QA_PREFIXES = ("Re-verify ", "Verify ", "Re-test ", "Test ")


def _feature_name(title: str) -> str:
    for p in _QA_PREFIXES:
        if title.startswith(p):
            return title[len(p):]
    return title


class Company:
    def __init__(self, settings: Settings | None = None, step_delay: float = 0.0) -> None:
        self.settings = settings or SETTINGS
        self.db = Database(self.settings.db_path)
        self.llm = LLMClient(self.settings)
        workspace = Path(self.settings.db_path).resolve().parent / "workspace"
        self.tools = ToolBox(self.db, workspace)
        self.ceo = CEOAgent(self.llm, self.tools)
        self.agents = {dept: cls(self.llm, self.tools) for dept, cls in AGENT_CLASSES.items()}
        self.step_delay = step_delay
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    # ---- human interface --------------------------------------------------
    def submit_directive(self, text: str) -> Directive:
        """Accept a human direction and have the CEO delegate the first tasks."""
        directive = self.db.add_directive(Directive(text=text, status=TaskStatus.IN_PROGRESS))
        self._log(Department.CEO, f"New direction received: {text}", "info")
        summary, tasks = self.ceo.plan(text, directive.id)
        self.db.update_directive(directive.id, summary=summary)
        directive.summary = summary
        for task in tasks:
            self.db.add_task(task)
            self._log(
                Department.CEO,
                f"Delegated to {task.department.title}: {task.title}",
                "delegate",
            )
        return directive

    # ---- work loop --------------------------------------------------------
    def process_one(self, department: Department) -> bool:
        """Claim and complete a single task for a department. Returns True if it did."""
        task = self.db.claim_next_task(department)
        if task is None:
            return False

        agent = self.agents[department]
        depth = self._depth(task)
        self._log(department, f"Working: {task.title}", "work")
        try:
            result = agent.work(task, allow_followups=depth < MAX_DEPTH)
        except Exception as exc:  # pragma: no cover - defensive
            self.db.update_task(task.id, status=TaskStatus.BLOCKED, result=f"error: {exc}")
            self._log(department, f"Blocked on '{task.title}': {exc}", "error")
            return True

        self.db.update_task(task.id, status=TaskStatus.DONE, result=result.summary)
        if result.artifact:
            self.db.add_artifact(result.artifact)
            self._log(
                department,
                f"Produced {result.artifact.kind}: {result.artifact.title}",
                "artifact",
            )

        if department == Department.QA and result.verdict == "rejected":
            self._handle_rejection(task, result, depth)
        else:
            for follow in result.followups:
                self.db.add_task(follow)
                self._log(
                    department,
                    f"Handed off to {follow.department.title}: {follow.title}",
                    "delegate",
                )
        self._maybe_close_directive(task.directive_id)
        return True

    def _handle_rejection(self, task: Task, result, depth: int) -> None:
        """QA rejected a build: send it back to Development, or ship if capped."""
        feature = _feature_name(task.title)
        if task.rework_count < MAX_REWORK and depth < MAX_DEPTH:
            fix = Task(
                title=f"Fix issues in {feature}",
                department=Department.DEVELOPMENT,
                description=result.summary,
                priority=Priority.HIGH,
                directive_id=task.directive_id,
                parent_id=task.id,
                created_by=Department.QA,
                rework_count=task.rework_count + 1,
            )
            self.db.add_task(fix)
            self._log(
                Department.QA,
                f"Rejected build; opened rework #{fix.rework_count} for Development: {feature}",
                "delegate",
            )
        else:
            # Rework budget exhausted — ship with known issues and notify Support.
            rel = Task(
                title=f"Release notes for {feature} (known issues)",
                department=Department.SUPPORT,
                description="Shipping after exhausting rework budget; document known issues.",
                priority=Priority.NORMAL,
                directive_id=task.directive_id,
                parent_id=task.id,
                created_by=Department.QA,
                rework_count=task.rework_count,
            )
            self.db.add_task(rel)
            self._log(
                Department.QA,
                f"Rework budget exhausted for {feature}; shipping with known issues.",
                "info",
            )

    def tick(self) -> int:
        """Give every department one chance to work. Returns tasks completed."""
        worked = 0
        for dept in WORKER_DEPARTMENTS:
            if self.process_one(dept):
                worked += 1
                if self.step_delay:
                    time.sleep(self.step_delay)
        return worked

    def run_until_idle(self, max_rounds: int = 200) -> int:
        """Process tasks until the board is clear (or a safety cap is hit)."""
        total = 0
        for _ in range(max_rounds):
            n = self.tick()
            if n == 0:
                break
            total += n
        return total

    # ---- background runner ------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Company background worker started.")

    def stop(self) -> None:
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while self._running.is_set():
            if self.tick() == 0:
                time.sleep(0.4)

    # ---- snapshot for the dashboard --------------------------------------
    def snapshot(self) -> dict:
        tasks = [t.to_dict() for t in self.db.get_tasks()]
        counts = self.db.count_tasks_by_status()
        per_dept = {d.value: {"pending": 0, "in_progress": 0, "done": 0} for d in WORKER_DEPARTMENTS}
        for t in tasks:
            bucket = per_dept.get(t["department"])
            if bucket and t["status"] in bucket:
                bucket[t["status"]] += 1
        return {
            "mode": "simulation" if self.settings.simulate else "claude",
            "model": self.settings.model,
            "directives": self.db.get_directives(),
            "tasks": tasks,
            "artifacts": self.db.get_artifacts(),
            "events": self.db.get_events(120),
            "departments": [
                {"id": d.value, "title": d.title, **per_dept[d.value]}
                for d in WORKER_DEPARTMENTS
            ],
            "metrics": {
                "total_tasks": len(tasks),
                "done": counts.get("done", 0),
                "in_progress": counts.get("in_progress", 0),
                "pending": counts.get("pending", 0),
                "blocked": counts.get("blocked", 0),
                "artifacts": len(self.db.get_artifacts()),
                "rework": sum(1 for t in tasks if t["rework_count"] > 0),
            },
        }

    # ---- internals --------------------------------------------------------
    def _depth(self, task: Task) -> int:
        depth, parent_id, guard = 0, task.parent_id, 0
        while parent_id and guard < MAX_DEPTH + 2:
            parent = self.db.get_task(parent_id)
            if parent is None:
                break
            depth += 1
            parent_id = parent.parent_id
            guard += 1
        return depth

    def _maybe_close_directive(self, directive_id: str | None) -> None:
        if not directive_id:
            return
        tasks = self.db.get_tasks(directive_id)
        if tasks and all(t.status in (TaskStatus.DONE, TaskStatus.BLOCKED) for t in tasks):
            self.db.update_directive(directive_id, status=TaskStatus.DONE)
            self._log(Department.CEO, "Direction complete — all work finished.", "info")

    def _log(self, department: Department, message: str, kind: str) -> None:
        self.db.add_event(Event(department=department, message=message, kind=kind))
        log.info("[%s] %s", department.value, message)
