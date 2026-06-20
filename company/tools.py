"""Real tools the agents can use.

This is what makes the agents *grounded* rather than purely generative:

  * ``recall`` — company memory: relevance search over everything the company
    has already produced, so an agent builds on prior work instead of starting
    cold. Dependency-free keyword scoring keeps it fully offline.
  * ``company_metrics`` — Analytics reads real numbers (throughput, cycle time,
    rework rate, workload per department) from the live database instead of
    inventing them.
  * ``validate_code`` — Development writes generated code to a workspace and
    compiles it with ``py_compile`` (which checks syntax without executing the
    code), giving QA a real signal to verify against.
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

from .db import Database

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "our",
    "is", "are", "be", "it", "this", "that", "we", "you", "your", "as", "by",
    "new", "make", "build", "create", "add", "feature", "report", "issue",
}

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


def _slug(text: str) -> str:
    parts = _TOKEN.findall(text.lower())
    return "_".join(parts)[:60] or "artifact"


class ToolBox:
    def __init__(self, db: Database, workspace: Path) -> None:
        self.db = db
        self.workspace = workspace
        self.workspace.mkdir(parents=True, exist_ok=True)

    # ---- company memory ---------------------------------------------------
    def recall(self, query: str, k: int = 3, exclude_task: str | None = None) -> list[dict]:
        """Return the most relevant prior artifacts for a query (keyword overlap)."""
        q = _tokens(query)
        if not q:
            return []
        scored: list[tuple[int, dict]] = []
        for art in self.db.get_artifacts():
            if exclude_task and art.get("task_id") == exclude_task:
                continue
            text = f"{art['title']} {art['kind']} {art['content']}"
            score = len(q & _tokens(text))
            if score:
                scored.append((score, art))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [a for _, a in scored[:k]]

    def recall_summary(self, query: str, k: int = 3, exclude_task: str | None = None) -> str:
        hits = self.recall(query, k, exclude_task)
        if not hits:
            return ""
        lines = [
            f"- ({h['department']}/{h['kind']}) {h['title']}: {h['content'][:140].strip()}"
            for h in hits
        ]
        return "RELEVANT PRIOR COMPANY WORK:\n" + "\n".join(lines)

    # ---- grounded analytics ----------------------------------------------
    def company_metrics(self) -> dict:
        tasks = self.db.get_tasks()
        done = [t for t in tasks if t.status.value == "done"]
        per_dept: dict[str, int] = {}
        for t in done:
            per_dept[t.department.value] = per_dept.get(t.department.value, 0) + 1
        cycle_times = [t.updated_at - t.created_at for t in done if t.updated_at >= t.created_at]
        avg_cycle = sum(cycle_times) / len(cycle_times) if cycle_times else 0.0
        reworked = sum(1 for t in tasks if t.rework_count > 0)
        return {
            "total_tasks": len(tasks),
            "completed": len(done),
            "in_flight": sum(1 for t in tasks if t.status.value == "in_progress"),
            "deliverables": len(self.db.get_artifacts()),
            "avg_cycle_seconds": round(avg_cycle, 2),
            "rework_tasks": reworked,
            "throughput_by_department": per_dept,
        }

    def metrics_report(self, title: str) -> str:
        m = self.company_metrics()
        by_dept = ", ".join(f"{d}={n}" for d, n in sorted(m["throughput_by_department"].items())) or "n/a"
        return (
            f"# Analytics: {title}\n\n"
            f"_Computed live from company operational data ({time.strftime('%Y-%m-%d %H:%M')})._\n\n"
            f"- Tasks completed: {m['completed']} / {m['total_tasks']}\n"
            f"- Deliverables produced: {m['deliverables']}\n"
            f"- Avg task cycle time: {m['avg_cycle_seconds']}s\n"
            f"- Tasks requiring rework: {m['rework_tasks']}\n"
            f"- Throughput by department: {by_dept}\n\n"
            "Recommendation: " + self._recommend(m)
        )

    @staticmethod
    def _recommend(m: dict) -> str:
        if m["rework_tasks"] and m["completed"]:
            rate = m["rework_tasks"] / max(m["completed"], 1)
            if rate > 0.3:
                return "rework rate is elevated — invest in clearer specs and earlier QA."
        if m["completed"] == 0:
            return "no completed work yet — give the company a direction to act on."
        return "throughput is healthy; keep shipping and monitor the activation funnel."

    # ---- code validation --------------------------------------------------
    def validate_code(self, name: str, code: str) -> tuple[bool, str]:
        """Write code to the workspace and syntax-check it (compile, never run)."""
        path = self.workspace / f"{_slug(name)}.py"
        try:
            path.write_text(code)
            proc = subprocess.run(
                [sys.executable, "-m", "py_compile", str(path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ok = proc.returncode == 0
            detail = (proc.stderr or proc.stdout).strip() or "compiled cleanly"
            return ok, detail
        except Exception as exc:  # pragma: no cover - defensive
            return False, f"validation error: {exc}"
