"""The CEO agent: the only agent the human talks to directly.

It takes a single human directive and decomposes it into the first wave of tasks,
delegated to the right departments. Everything after that cascades on its own as
departments hand work to one another.
"""
from __future__ import annotations

from ..agentconfig import ConfigRegistry
from ..llm import LLMClient
from ..models import WORKER_DEPARTMENTS, Department, Priority, Task
from ..tools import ToolBox

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "tasks": {
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
    "required": ["summary", "tasks"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are the CEO of an autonomous software company. Seven AI departments "
    "report to you: Customer Support, Sales, Marketing, Product Management, "
    "Development, QA, and Analytics. A human gives you one direction at a time. "
    "Decompose it into the FIRST wave of tasks only — the natural starting points "
    "— delegated to the right departments. Do not plan the whole chain; "
    "departments hand off downstream work themselves. Usually 1-3 starting tasks "
    "is right. Respond strictly in the required JSON shape."
)


class CEOAgent:
    department = Department.CEO

    def __init__(self, llm: LLMClient, tools: ToolBox, config: ConfigRegistry) -> None:
        self.llm = llm
        self.tools = tools
        self.config = config

    def plan(self, directive_text: str, directive_id: str) -> tuple[str, list[Task]]:
        memory = self.tools.recall_summary(directive_text)
        prompt = f"DIRECTION FROM HUMAN:\n{directive_text}"
        if memory:
            prompt += f"\n\n{memory}"
        cfg = self.config.get(Department.CEO)
        raw = self.llm.generate_json(
            SYSTEM, prompt, PLAN_SCHEMA, model=cfg.model, effort=cfg.effort
        )
        if raw is None:
            raw = self._simulate(directive_text)

        tasks: list[Task] = []
        for t in raw.get("tasks") or []:
            dept = _safe_department(t.get("department"))
            if dept is None:
                continue
            tasks.append(
                Task(
                    title=t.get("title", "Untitled"),
                    department=dept,
                    description=t.get("description", ""),
                    priority=_safe_priority(t.get("priority")),
                    directive_id=directive_id,
                    created_by=Department.CEO,
                )
            )
        if not tasks:  # never leave a directive with nothing to do
            tasks.append(
                Task(
                    title=directive_text[:80],
                    department=Department.PRODUCT,
                    description=directive_text,
                    directive_id=directive_id,
                    created_by=Department.CEO,
                )
            )
        summary = raw.get("summary", "Delegated the direction to the relevant departments.")
        return summary, tasks

    def _simulate(self, directive_text: str) -> dict:
        """Route by intent keywords when Claude is unavailable."""
        text = directive_text.lower()
        product_words = (
            "feature", "build", "implement", "ship", "add ", "redesign",
            "improve", "product", "mode", "ui", "ux", "rebuild",
        )
        if any(w in text for w in ("bug", "broken", "complaint", "outage", "crash")):
            dept, title = "support", "Triage and resolve customer issue"
        elif any(w in text for w in product_words):
            dept, title = "product", directive_text.strip()[:70]
        elif any(w in text for w in ("campaign", "market", "awareness", "brand", "promote")):
            dept, title = "marketing", "Plan marketing campaign"
        elif any(w in text for w in ("sell", "sales", "pipeline", "revenue", "deal")):
            dept, title = "sales", "Build sales motion"
        elif any(w in text for w in ("metric", "data", "analy", "measure", "retention", "report")):
            dept, title = "analytics", "Analyze and report"
        else:
            dept, title = "product", "Define product scope"
        return {
            "summary": f"Delegated '{directive_text[:60]}' to the {dept} team to lead.",
            "tasks": [
                {
                    "department": dept,
                    "title": title,
                    "description": directive_text,
                    "priority": "high",
                }
            ],
        }


def _safe_department(value):
    try:
        d = Department(value)
    except (ValueError, TypeError):
        return None
    return d if d in WORKER_DEPARTMENTS else None


def _safe_priority(value):
    try:
        return Priority(value)
    except (ValueError, TypeError):
        return Priority.NORMAL
