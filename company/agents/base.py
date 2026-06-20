"""Base class for every department agent.

An agent turns a single task into three things:
  1. a short summary of what it did,
  2. an optional concrete artifact (a spec, code, a campaign, a report), and
  3. zero or more follow-up tasks handed to other departments.

This uniform shape is what makes work flow across the company on its own: a
product spec spawns development, development spawns QA, marketing spawns sales,
and so on — exactly like a real org, but driven by agents.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..llm import LLMClient
from ..models import (
    Artifact,
    Department,
    Priority,
    Task,
    WORKER_DEPARTMENTS,
)

# JSON schema every worker agent returns (via Claude structured outputs or sim).
WORKER_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "artifact": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "kind": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["title", "kind", "content"],
                    "additionalProperties": False,
                },
            ]
        },
        "followups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "department": {
                        "type": "string",
                        "enum": [d.value for d in WORKER_DEPARTMENTS],
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": [p.value for p in Priority],
                    },
                },
                "required": ["department", "title", "description", "priority"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "artifact", "followups"],
    "additionalProperties": False,
}


@dataclass
class WorkResult:
    summary: str
    artifact: Artifact | None = None
    followups: list[Task] = field(default_factory=list)


class BaseAgent:
    department: Department = Department.SUPPORT
    role_description: str = ""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    # ---- public API -------------------------------------------------------
    def work(self, task: Task, allow_followups: bool = True) -> WorkResult:
        """Process a task, preferring Claude and falling back to simulation."""
        raw = self.llm.generate_json(
            self.system_prompt(), self._user_prompt(task), WORKER_SCHEMA
        )
        if raw is None:
            raw = self.simulate(task)
        return self._materialize(task, raw, allow_followups)

    # ---- to be specialized ------------------------------------------------
    def system_prompt(self) -> str:
        return (
            f"You are the {self.department.title} agent in an autonomous software "
            f"company where AI agents run all operations and a human only sets "
            f"direction. {self.role_description}\n\n"
            "You are given one task. Do the work, produce at most one concrete "
            "artifact, and hand off any natural next steps to the right "
            "departments as follow-up tasks. Only create follow-ups that a real "
            "team in your position would actually create — do not invent busywork. "
            "Respond strictly in the required JSON shape."
        )

    def simulate(self, task: Task) -> dict:  # pragma: no cover - overridden
        """Deterministic stand-in used when Claude is unavailable."""
        return {
            "summary": f"{self.department.title} handled: {task.title}",
            "artifact": None,
            "followups": [],
        }

    # ---- helpers ----------------------------------------------------------
    def _user_prompt(self, task: Task) -> str:
        return (
            f"TASK: {task.title}\n"
            f"DETAILS: {task.description or '(none)'}\n"
            f"PRIORITY: {task.priority.value}\n"
        )

    def _materialize(self, task: Task, raw: dict, allow_followups: bool) -> WorkResult:
        artifact = None
        art = raw.get("artifact")
        if art:
            artifact = Artifact(
                title=art.get("title", task.title),
                department=self.department,
                kind=art.get("kind", "note"),
                content=art.get("content", ""),
                task_id=task.id,
            )

        followups: list[Task] = []
        if allow_followups:
            for f in raw.get("followups") or []:
                dept = _safe_department(f.get("department"))
                if dept is None or dept == self.department:
                    continue
                followups.append(
                    Task(
                        title=f.get("title", "Follow-up"),
                        department=dept,
                        description=f.get("description", ""),
                        priority=_safe_priority(f.get("priority")),
                        directive_id=task.directive_id,
                        parent_id=task.id,
                        created_by=self.department,
                    )
                )

        return WorkResult(
            summary=raw.get("summary", f"{self.department.title} completed {task.title}"),
            artifact=artifact,
            followups=followups,
        )


def _safe_department(value: str | None) -> Department | None:
    try:
        dept = Department(value)
    except (ValueError, TypeError):
        return None
    return dept if dept in WORKER_DEPARTMENTS else None


def _safe_priority(value: str | None) -> Priority:
    try:
        return Priority(value)
    except (ValueError, TypeError):
        return Priority.NORMAL
