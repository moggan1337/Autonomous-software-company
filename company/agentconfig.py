"""Human-tunable agent configuration, backed by the database.

The registry gives each department an :class:`AgentConfig` (model, effort, extra
instructions, enabled). Agents read their config at work time, so changes a human
makes in the dashboard take effect on the next task — model/effort overrides flow
to Claude, extra instructions are appended to the system prompt, and a disabled
department stops picking up work.
"""
from __future__ import annotations

import threading

from .db import Database
from .models import AgentConfig, Department


class ConfigRegistry:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._lock = threading.RLock()
        self._configs: dict[Department, AgentConfig] = {
            d: AgentConfig(department=d) for d in Department
        }
        self._load()

    def _load(self) -> None:
        rows = self.db.get_agent_configs()
        with self._lock:
            for dept in Department:
                row = rows.get(dept.value)
                if row:
                    self._configs[dept] = AgentConfig(
                        department=dept,
                        model=row["model"] or None,
                        effort=row["effort"] or None,
                        instructions=row["instructions"] or "",
                        enabled=bool(row["enabled"]),
                    )

    def get(self, department: Department) -> AgentConfig:
        with self._lock:
            return self._configs[department]

    def all(self) -> list[dict]:
        with self._lock:
            return [self._configs[d].to_dict() for d in Department]

    def update(self, department: Department, **fields) -> AgentConfig:
        with self._lock:
            cfg = self._configs[department]
            cfg.model = fields.get("model", cfg.model) or None
            cfg.effort = fields.get("effort", cfg.effort) or None
            if "instructions" in fields:
                cfg.instructions = fields["instructions"] or ""
            if "enabled" in fields:
                cfg.enabled = bool(fields["enabled"])
            self.db.upsert_agent_config(
                department.value, cfg.model, cfg.effort, cfg.instructions, cfg.enabled
            )
            return cfg
