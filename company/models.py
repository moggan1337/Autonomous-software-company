"""Domain model for the autonomous software company.

These are the nouns every agent and the dashboard share: departments, the tasks
that flow between them, the artifacts they produce, and the activity log.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def now() -> float:
    return time.time()


class Department(str, Enum):
    CEO = "ceo"
    SUPPORT = "support"
    SALES = "sales"
    MARKETING = "marketing"
    PRODUCT = "product"
    DEVELOPMENT = "development"
    QA = "qa"
    ANALYTICS = "analytics"

    @property
    def title(self) -> str:
        return {
            Department.CEO: "CEO / Orchestrator",
            Department.SUPPORT: "Customer Support",
            Department.SALES: "Sales",
            Department.MARKETING: "Marketing",
            Department.PRODUCT: "Product Management",
            Department.DEVELOPMENT: "Development",
            Department.QA: "Quality Assurance",
            Department.ANALYTICS: "Analytics",
        }[self]


# Departments that actually pick up and work tasks (the CEO only delegates).
WORKER_DEPARTMENTS = [d for d in Department if d != Department.CEO]


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    BLOCKED = "blocked"


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Task:
    title: str
    department: Department
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: Priority = Priority.NORMAL
    id: str = field(default_factory=lambda: _id("task"))
    directive_id: str | None = None
    parent_id: str | None = None
    created_by: Department = Department.CEO
    result: str = ""
    rework_count: int = 0
    approved: bool = False
    created_at: float = field(default_factory=now)
    updated_at: float = field(default_factory=now)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["department"] = self.department.value
        d["status"] = self.status.value
        d["priority"] = self.priority.value
        d["created_by"] = self.created_by.value
        return d


@dataclass
class Artifact:
    """A concrete deliverable produced by a department (a doc, a PR, a campaign)."""

    title: str
    department: Department
    kind: str  # e.g. "spec", "code", "campaign", "report", "reply"
    content: str
    task_id: str | None = None
    id: str = field(default_factory=lambda: _id("art"))
    created_at: float = field(default_factory=now)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["department"] = self.department.value
        return d


@dataclass
class Directive:
    """A human instruction to the company. The CEO breaks it into tasks."""

    text: str
    id: str = field(default_factory=lambda: _id("dir"))
    status: TaskStatus = TaskStatus.PENDING
    summary: str = ""
    source: str = "human"  # "human" | "world" (autopilot)
    created_at: float = field(default_factory=now)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class AgentConfig:
    """Human-tunable settings for one department agent."""

    department: Department
    model: str | None = None       # None -> use the company default
    effort: str | None = None      # None -> use the company default
    instructions: str = ""         # extra guidance appended to the system prompt
    enabled: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["department"] = self.department.value
        d["title"] = self.department.title
        return d


@dataclass
class Customer:
    name: str
    status: str = "active"          # active | lead | lost
    seats: int = 1
    source: str = "sales"
    id: str = field(default_factory=lambda: _id("cust"))
    created_at: float = field(default_factory=now)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Deal:
    name: str
    value: float
    stage: str = "won"             # won | lost
    customer_id: str | None = None
    id: str = field(default_factory=lambda: _id("deal"))
    created_at: float = field(default_factory=now)
    closed_at: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Ticket:
    subject: str
    status: str = "resolved"       # open | resolved
    priority: str = "normal"
    customer_id: str | None = None
    id: str = field(default_factory=lambda: _id("tkt"))
    created_at: float = field(default_factory=now)
    resolved_at: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StandingOrder:
    """A recurring directive the company submits to itself on a fixed interval."""

    text: str
    interval_seconds: float
    next_run: float
    id: str = field(default_factory=lambda: _id("ord"))
    enabled: bool = True
    last_run: float | None = None
    runs: int = 0
    created_at: float = field(default_factory=now)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Event:
    """An entry in the company activity feed."""

    department: Department
    message: str
    kind: str = "info"  # info | delegate | work | artifact | metric | error
    id: str = field(default_factory=lambda: _id("evt"))
    created_at: float = field(default_factory=now)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["department"] = self.department.value
        return d
