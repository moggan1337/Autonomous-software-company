"""SQLite persistence for company state.

Everything the company knows — directives, tasks, artifacts, the activity feed —
lives here so the company survives restarts and the dashboard can read a
consistent snapshot. A single connection guarded by a lock keeps it simple and
correct for the company's modest write volume.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from .models import (
    Artifact,
    Department,
    Directive,
    Event,
    Priority,
    Task,
    TaskStatus,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS directives (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'human',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    department TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    directive_id TEXT,
    parent_id TEXT,
    created_by TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT '',
    rework_count INTEGER NOT NULL DEFAULT 0,
    approved INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_configs (
    department TEXT PRIMARY KEY,
    model TEXT,
    effort TEXT,
    instructions TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS usage (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    directive_id TEXT,
    department TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kpi_snapshots (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    tasks_done INTEGER NOT NULL,
    deliverables INTEGER NOT NULL,
    cost REAL NOT NULL,
    revenue REAL NOT NULL,
    customers INTEGER NOT NULL,
    tickets_resolved INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS standing_orders (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    interval_seconds REAL NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run REAL,
    next_run REAL NOT NULL,
    runs INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    seats INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'sales',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS deals (
    id TEXT PRIMARY KEY,
    customer_id TEXT,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    stage TEXT NOT NULL,
    created_at REAL NOT NULL,
    closed_at REAL
);
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    customer_id TEXT,
    subject TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'normal',
    created_at REAL NOT NULL,
    resolved_at REAL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    department TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    task_id TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    department TEXT NOT NULL,
    message TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_department ON tasks(department);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
"""


class Database:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- directives -------------------------------------------------------
    def add_directive(self, d: Directive) -> Directive:
        with self._lock:
            self._conn.execute(
                "INSERT INTO directives (id, text, status, summary, source, created_at) VALUES (?,?,?,?,?,?)",
                (d.id, d.text, d.status.value, d.summary, d.source, d.created_at),
            )
            self._conn.commit()
        return d

    def update_directive(self, directive_id: str, **fields: Any) -> None:
        if not fields:
            return
        if "status" in fields and isinstance(fields["status"], TaskStatus):
            fields["status"] = fields["status"].value
        self._update("directives", directive_id, fields)

    def get_directives(self) -> list[dict]:
        return [dict(r) for r in self._query("SELECT * FROM directives ORDER BY created_at DESC")]

    # ---- tasks ------------------------------------------------------------
    def add_task(self, t: Task) -> Task:
        with self._lock:
            self._conn.execute(
                """INSERT INTO tasks
                   (id, title, department, description, status, priority, directive_id,
                    parent_id, created_by, result, rework_count, approved, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    t.id, t.title, t.department.value, t.description, t.status.value,
                    t.priority.value, t.directive_id, t.parent_id, t.created_by.value,
                    t.result, t.rework_count, int(t.approved), t.created_at, t.updated_at,
                ),
            )
            self._conn.commit()
        return t

    def update_task(self, task_id: str, **fields: Any) -> None:
        for key in ("status", "priority", "department", "created_by"):
            if key in fields and hasattr(fields[key], "value"):
                fields[key] = fields[key].value
        if "approved" in fields:
            fields["approved"] = int(fields["approved"])
        self._update("tasks", task_id, fields)

    def claim_next_task(self, department: Department) -> Task | None:
        """Atomically pick the oldest pending task for a department and mark it in-progress.

        The claim happens under the write lock so two worker loops never grab the
        same task.
        """
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM tasks
                   WHERE department=? AND status=?
                   ORDER BY CASE priority
                       WHEN 'urgent' THEN 0 WHEN 'high' THEN 1
                       WHEN 'normal' THEN 2 ELSE 3 END, created_at
                   LIMIT 1""",
                (department.value, TaskStatus.PENDING.value),
            ).fetchone()
            if row is None:
                return None
            task = _row_to_task(row)
            self._conn.execute(
                "UPDATE tasks SET status=?, updated_at=updated_at WHERE id=?",
                (TaskStatus.IN_PROGRESS.value, task.id),
            )
            self._conn.commit()
            task.status = TaskStatus.IN_PROGRESS
            return task

    def get_task(self, task_id: str) -> Task | None:
        rows = self._query("SELECT * FROM tasks WHERE id=?", (task_id,))
        return _row_to_task(rows[0]) if rows else None

    def get_tasks(self, directive_id: str | None = None) -> list[Task]:
        if directive_id:
            rows = self._query(
                "SELECT * FROM tasks WHERE directive_id=? ORDER BY created_at", (directive_id,)
            )
        else:
            rows = self._query("SELECT * FROM tasks ORDER BY created_at")
        return [_row_to_task(r) for r in rows]

    def count_tasks_by_status(self) -> dict[str, int]:
        rows = self._query("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status")
        return {r["status"]: r["n"] for r in rows}

    # ---- artifacts --------------------------------------------------------
    def add_artifact(self, a: Artifact) -> Artifact:
        with self._lock:
            self._conn.execute(
                """INSERT INTO artifacts (id, title, department, kind, content, task_id, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (a.id, a.title, a.department.value, a.kind, a.content, a.task_id, a.created_at),
            )
            self._conn.commit()
        return a

    def get_artifacts(self) -> list[dict]:
        return [dict(r) for r in self._query("SELECT * FROM artifacts ORDER BY created_at DESC")]

    # ---- agent configs ----------------------------------------------------
    def get_agent_configs(self) -> dict[str, dict]:
        rows = self._query("SELECT * FROM agent_configs")
        return {r["department"]: dict(r) for r in rows}

    def upsert_agent_config(
        self, department: str, model, effort, instructions: str, enabled: bool
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO agent_configs (department, model, effort, instructions, enabled)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(department) DO UPDATE SET
                     model=excluded.model, effort=excluded.effort,
                     instructions=excluded.instructions, enabled=excluded.enabled""",
                (department, model, effort, instructions, int(enabled)),
            )
            self._conn.commit()

    # ---- usage / cost ledger ---------------------------------------------
    def add_usage(
        self, usage_id: str, task_id, directive_id, department: str,
        input_tokens: int, output_tokens: int, cost: float, created_at: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO usage
                   (id, task_id, directive_id, department, input_tokens, output_tokens, cost, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (usage_id, task_id, directive_id, department, input_tokens, output_tokens, cost, created_at),
            )
            self._conn.commit()

    def cost_summary(self) -> dict:
        total = self._query(
            "SELECT COALESCE(SUM(cost),0) AS c, COALESCE(SUM(input_tokens),0) AS i, "
            "COALESCE(SUM(output_tokens),0) AS o FROM usage"
        )[0]
        by_dept = {
            r["department"]: r["c"]
            for r in self._query(
                "SELECT department, SUM(cost) AS c FROM usage GROUP BY department"
            )
        }
        return {
            "total_cost": round(total["c"], 4),
            "input_tokens": total["i"],
            "output_tokens": total["o"],
            "by_department": {d: round(c, 4) for d, c in by_dept.items()},
        }

    # ---- KPI time series --------------------------------------------------
    def add_kpi_snapshot(self, snapshot_id: str, ts: float, values: dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO kpi_snapshots
                   (id, ts, tasks_done, deliverables, cost, revenue, customers, tickets_resolved)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id, ts, values["tasks_done"], values["deliverables"],
                    values["cost"], values["revenue"], values["customers"],
                    values["tickets_resolved"],
                ),
            )
            self._conn.commit()

    def get_kpis(self, limit: int = 300) -> list[dict]:
        rows = self._query(
            "SELECT * FROM kpi_snapshots ORDER BY ts DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in reversed(rows)]

    # ---- CRM: customers / deals / tickets ---------------------------------
    def add_customer(self, c) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO customers (id, name, status, seats, source, created_at) VALUES (?,?,?,?,?,?)",
                (c.id, c.name, c.status, c.seats, c.source, c.created_at),
            )
            self._conn.commit()

    def add_deal(self, d) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO deals (id, customer_id, name, value, stage, created_at, closed_at) VALUES (?,?,?,?,?,?,?)",
                (d.id, d.customer_id, d.name, d.value, d.stage, d.created_at, d.closed_at),
            )
            self._conn.commit()

    def add_ticket(self, t) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO tickets (id, customer_id, subject, status, priority, created_at, resolved_at) VALUES (?,?,?,?,?,?,?)",
                (t.id, t.customer_id, t.subject, t.status, t.priority, t.created_at, t.resolved_at),
            )
            self._conn.commit()

    def get_customers(self, limit: int = 50) -> list[dict]:
        return [dict(r) for r in self._query(
            "SELECT * FROM customers ORDER BY created_at DESC LIMIT ?", (limit,))]

    def get_deals(self, limit: int = 50) -> list[dict]:
        return [dict(r) for r in self._query(
            "SELECT * FROM deals ORDER BY created_at DESC LIMIT ?", (limit,))]

    def get_tickets(self, limit: int = 50) -> list[dict]:
        return [dict(r) for r in self._query(
            "SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?", (limit,))]

    def crm_summary(self) -> dict:
        cust = self._query(
            "SELECT COUNT(*) AS total, COALESCE(SUM(status='active'),0) AS active, "
            "COALESCE(SUM(seats),0) AS seats FROM customers"
        )[0]
        deals = self._query(
            "SELECT COUNT(*) AS total, COALESCE(SUM(stage='won'),0) AS won, "
            "COALESCE(SUM(stage='lost'),0) AS lost, "
            "COALESCE(SUM(CASE WHEN stage='won' THEN value ELSE 0 END),0) AS revenue FROM deals"
        )[0]
        tickets = self._query(
            "SELECT COUNT(*) AS total, COALESCE(SUM(status='resolved'),0) AS resolved, "
            "COALESCE(SUM(status='open'),0) AS open FROM tickets"
        )[0]
        won = deals["won"] or 0
        total_deals = deals["total"] or 0
        return {
            "customers_total": cust["total"] or 0,
            "customers_active": cust["active"] or 0,
            "seats": cust["seats"] or 0,
            "deals_total": total_deals,
            "deals_won": won,
            "deals_lost": deals["lost"] or 0,
            "win_rate": round(won / total_deals, 2) if total_deals else 0.0,
            "revenue": round(deals["revenue"] or 0.0, 2),
            "tickets_total": tickets["total"] or 0,
            "tickets_resolved": tickets["resolved"] or 0,
            "tickets_open": tickets["open"] or 0,
        }

    # ---- standing orders (recurring directives) ---------------------------
    def add_standing_order(self, order) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO standing_orders
                   (id, text, interval_seconds, enabled, last_run, next_run, runs, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    order.id, order.text, order.interval_seconds, int(order.enabled),
                    order.last_run, order.next_run, order.runs, order.created_at,
                ),
            )
            self._conn.commit()

    def get_standing_orders(self) -> list[dict]:
        rows = self._query("SELECT * FROM standing_orders ORDER BY created_at")
        out = []
        for r in rows:
            d = dict(r)
            d["enabled"] = bool(d["enabled"])
            out.append(d)
        return out

    def get_due_standing_orders(self, ts: float) -> list[dict]:
        rows = self._query(
            "SELECT * FROM standing_orders WHERE enabled=1 AND next_run<=? ORDER BY next_run",
            (ts,),
        )
        return [dict(r) for r in rows]

    def update_standing_order(self, order_id: str, **fields: Any) -> None:
        if "enabled" in fields:
            fields["enabled"] = int(fields["enabled"])
        self._update("standing_orders", order_id, fields)

    def delete_standing_order(self, order_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM standing_orders WHERE id=?", (order_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def cost_by_directive(self, directive_id: str) -> float:
        row = self._query(
            "SELECT COALESCE(SUM(cost),0) AS c FROM usage WHERE directive_id=?", (directive_id,)
        )[0]
        return round(row["c"], 4)

    # ---- events -----------------------------------------------------------
    def add_event(self, e: Event) -> Event:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (id, department, message, kind, created_at) VALUES (?,?,?,?,?)",
                (e.id, e.department.value, e.message, e.kind, e.created_at),
            )
            self._conn.commit()
        return e

    def get_events(self, limit: int = 200) -> list[dict]:
        rows = self._query("SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # ---- internals --------------------------------------------------------
    def _update(self, table: str, row_id: str, fields: dict[str, Any]) -> None:
        from .models import now as _now

        fields = dict(fields)
        if table == "tasks":
            fields.setdefault("updated_at", _now())
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE {table} SET {cols} WHERE id=?", (*fields.values(), row_id)
            )
            self._conn.commit()

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        department=Department(row["department"]),
        description=row["description"],
        status=TaskStatus(row["status"]),
        priority=Priority(row["priority"]),
        directive_id=row["directive_id"],
        parent_id=row["parent_id"],
        created_by=Department(row["created_by"]),
        result=row["result"],
        rework_count=row["rework_count"],
        approved=bool(row["approved"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


__all__ = ["Database", "json"]
