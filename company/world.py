"""The world the company reacts to.

Real companies don't sit idle waiting for the founder to speak — customers file
tickets, leads come in, ideas surface. The World generates that inbound stream
on a timer (autopilot), submitting each item as a directive tagged ``world`` so
the company runs itself with no human input at all.

It can be driven two ways:
  * ``generate_one()`` — produce a single inbound item (used by tests).
  * ``start()`` / ``stop()`` — a background thread that emits on an interval.
"""
from __future__ import annotations

import logging
import random
import threading
from collections.abc import Callable

from .models import Directive

log = logging.getLogger("company.world")

# (weight, source-flavored directive templates) per inbound category.
_SUPPORT = [
    "A customer reports the export button is broken on Safari",
    "Customer complaint: login fails intermittently after the latest update",
    "A user says the dashboard is loading slowly and times out",
    "Bug report: invoices show the wrong currency symbol",
    "Customer can't reset their password — the email never arrives",
]
_SALES = [
    "Enterprise lead: Acme Corp wants a demo of the analytics suite",
    "Inbound trial from Globex — 200 seats, evaluating this quarter",
    "A prospect asked for pricing on the team plan",
    "Warm lead from a webinar wants to discuss an annual contract",
]
_PRODUCT = [
    "Build a feature: keyboard shortcuts for power users",
    "Improve onboarding so new users activate faster",
    "Add an integration with Slack for notifications",
]
_ANALYTICS = [
    "Analyze last week's signup-to-activation funnel",
    "Report on which features drive the most retention",
]

_CATEGORIES = [
    (45, _SUPPORT),
    (30, _SALES),
    (15, _PRODUCT),
    (10, _ANALYTICS),
]


class World:
    def __init__(
        self,
        submit: Callable[..., Directive],
        interval: float = 8.0,
        seed: int | None = None,
    ) -> None:
        self._submit = submit
        self.interval = interval
        self._rng = random.Random(seed)
        self._running = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def generate_one(self) -> Directive:
        """Pick a weighted inbound category and submit one directive from it."""
        pool = self._weighted_pick()
        text = self._rng.choice(pool)
        directive = self._submit(text, source="world")
        log.info("World generated inbound: %s", text)
        return directive

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("World autopilot started (interval=%ss).", self.interval)

    def stop(self) -> None:
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=2)
        log.info("World autopilot stopped.")

    def _loop(self) -> None:
        while self._running.is_set():
            # Wait first so toggling on doesn't immediately flood the board.
            if self._running.wait(self.interval) is False and not self._running.is_set():
                break
            if self._running.is_set():
                try:
                    self.generate_one()
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning("World generation failed: %s", exc)

    def _weighted_pick(self) -> list[str]:
        total = sum(w for w, _ in _CATEGORIES)
        roll = self._rng.uniform(0, total)
        upto = 0.0
        for weight, pool in _CATEGORIES:
            upto += weight
            if roll <= upto:
                return pool
        return _CATEGORIES[0][1]  # pragma: no cover
