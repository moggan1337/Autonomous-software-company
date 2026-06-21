"""Base class for every department agent.

An agent turns a single task into:
  1. a short summary of what it did,
  2. an optional concrete artifact (a spec, code, a campaign, a report),
  3. zero or more follow-up tasks handed to other departments, and
  4. (QA only) a verdict — approved or rejected — that drives the rework loop.

Every agent is also handed a :class:`ToolBox`: it recalls relevant prior work
(company memory) before acting, and specific agents use grounded tools
(real metrics, code validation). This uniform shape is what makes work flow
across the company on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..agentconfig import ConfigRegistry
from ..llm import LLMClient
from ..models import (
    WORKER_DEPARTMENTS,
    Artifact,
    Department,
    Priority,
    Task,
)
from ..tools import ToolBox

# JSON schema every worker agent returns (via Claude structured outputs or sim).
WORKER_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "verdict": {"type": ["string", "null"], "enum": ["approved", "rejected", None]},
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
                    "priority": {"type": "string", "enum": [p.value for p in Priority]},
                },
                "required": ["department", "title", "description", "priority"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "verdict", "artifact", "followups"],
    "additionalProperties": False,
}


@dataclass
class WorkResult:
    summary: str
    artifact: Artifact | None = None
    followups: list[Task] = field(default_factory=list)
    verdict: str | None = None


class BaseAgent:
    department: Department = Department.SUPPORT
    role_description: str = ""

    def __init__(self, llm: LLMClient, tools: ToolBox, config: ConfigRegistry) -> None:
        self.llm = llm
        self.tools = tools
        self.config = config

    # ---- public API -------------------------------------------------------
    def work(self, task: Task, allow_followups: bool = True) -> WorkResult:
        """Process a task, preferring Claude and falling back to simulation."""
        cfg = self.config.get(self.department)
        context = self.tools.recall(
            f"{task.title} {task.description}", k=3, exclude_task=task.id
        )
        raw = self.llm.generate_json(
            self.system_prompt(), self._user_prompt(task, context), WORKER_SCHEMA,
            model=cfg.model, effort=cfg.effort,
        )
        if raw is None:
            raw = self.simulate(task, context)
        return self._materialize(task, raw, allow_followups)

    # ---- to be specialized ------------------------------------------------
    def system_prompt(self) -> str:
        base = (
            f"You are the {self.department.title} agent in an autonomous software "
            f"company where AI agents run all operations and a human only sets "
            f"direction. {self.role_description}\n\n"
            "You are given one task plus any relevant prior company work. Build on "
            "that prior work rather than repeating it. Do the work, produce at most "
            "one concrete artifact, and hand off natural next steps to the right "
            "departments as follow-up tasks — only ones a real team would actually "
            "create. Set 'verdict' to null unless you are QA. Respond strictly in "
            "the required JSON shape."
        )
        extra = self.config.get(self.department).instructions.strip()
        if extra:
            base += f"\n\nADDITIONAL INSTRUCTIONS FROM LEADERSHIP:\n{extra}"
        return base

    def simulate(self, task: Task, context: list[dict]) -> dict:  # pragma: no cover
        """Deterministic stand-in used when Claude is unavailable."""
        return {
            "summary": f"{self.department.title} handled: {task.title}",
            "verdict": None,
            "artifact": None,
            "followups": [],
        }

    # ---- helpers ----------------------------------------------------------
    def _user_prompt(self, task: Task, context: list[dict]) -> str:
        memory = self.tools.recall_summary(f"{task.title} {task.description}", exclude_task=task.id)
        base = (
            f"TASK: {task.title}\n"
            f"DETAILS: {task.description or '(none)'}\n"
            f"PRIORITY: {task.priority.value}\n"
        )
        if task.rework_count:
            base += f"REWORK PASS: this is rework iteration {task.rework_count}.\n"
        return f"{base}\n{memory}" if memory else base

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
                        rework_count=task.rework_count,  # rework state flows downstream
                    )
                )

        verdict = raw.get("verdict")
        if verdict not in ("approved", "rejected"):
            verdict = None

        return WorkResult(
            summary=raw.get("summary", f"{self.department.title} completed {task.title}"),
            artifact=artifact,
            followups=followups,
            verdict=verdict,
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
