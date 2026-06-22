"""Multi-company support: run several independent companies from one deployment.

Each company is a full :class:`Company` with its own SQLite database, background
worker, event bus, and world — so they share nothing. The manager owns the set,
persists a small registry (id, name) so companies survive restarts, and always
guarantees a ``default`` company exists for backward compatibility.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import threading
from pathlib import Path

from .config import Settings
from .models import _id, now
from .orchestrator import Company

log = logging.getLogger("company.manager")

DEFAULT_ID = "default"


class CompanyManager:
    def __init__(self, settings: Settings, step_delay: float = 0.0) -> None:
        self.settings = settings
        self.step_delay = step_delay
        self._base = Path(settings.db_path).resolve().parent
        self._registry_path = self._base / "companies.json"
        self._lock = threading.RLock()
        self._companies: dict[str, Company] = {}
        self._meta: dict[str, dict] = {}
        self._loop = None
        self._started = False
        self._load()

    # ---- registry ---------------------------------------------------------
    def _load(self) -> None:
        entries = []
        if self._registry_path.exists():
            try:
                entries = json.loads(self._registry_path.read_text())
            except Exception:  # pragma: no cover - corrupt file
                entries = []
        if not any(e["id"] == DEFAULT_ID for e in entries):
            entries.insert(0, {"id": DEFAULT_ID, "name": "Default Company", "created_at": now()})
        for entry in entries:
            self._instantiate(entry)
        self._save()

    def _save(self) -> None:
        ordered = sorted(self._meta.values(), key=lambda m: m["created_at"])
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._registry_path.write_text(json.dumps(ordered, indent=2))

    def _db_path_for(self, company_id: str) -> str:
        # The default company keeps the original db file for backward compatibility.
        if company_id == DEFAULT_ID:
            return self.settings.db_path
        return str(self._base / f"company_{company_id}.db")

    def _instantiate(self, entry: dict) -> Company:
        cid = entry["id"]
        settings = dataclasses.replace(self.settings, db_path=self._db_path_for(cid))
        company = Company(settings=settings, step_delay=self.step_delay)
        self._companies[cid] = company
        self._meta[cid] = entry
        return company

    # ---- public API -------------------------------------------------------
    def get(self, company_id: str) -> Company | None:
        with self._lock:
            return self._companies.get(company_id)

    def list(self) -> list[dict]:
        with self._lock:
            return sorted(self._meta.values(), key=lambda m: m["created_at"])

    def create(self, name: str) -> dict:
        with self._lock:
            entry = {"id": _id("co"), "name": name.strip() or "Untitled Company", "created_at": now()}
            company = self._instantiate(entry)
            self._save()
        if self._loop is not None:
            company.bus.bind_loop(self._loop)
        if self._started:
            company.start()
        log.info("Created company %s (%s)", entry["id"], entry["name"])
        return entry

    # ---- lifecycle --------------------------------------------------------
    def bind_loop(self, loop) -> None:
        self._loop = loop
        with self._lock:
            for company in self._companies.values():
                company.bus.bind_loop(loop)

    def start_all(self) -> None:
        self._started = True
        with self._lock:
            for company in self._companies.values():
                company.start()

    def stop_all(self) -> None:
        self._started = False
        with self._lock:
            for company in self._companies.values():
                company.stop()
