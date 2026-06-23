"""A small in-process sliding-window rate limiter.

Bounds abuse of state-changing endpoints (directive/company spam) without any
external dependency. Per-client sliding window over monotonic time; thread-safe
for the company's modest concurrency. Disabled when ``limit <= 0``.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_MAX_KEYS = 10_000  # bound memory: a flood of distinct clients can't grow this unbounded


class RateLimiter:
    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.limit > 0

    def check(self, key: str) -> tuple[bool, float]:
        """Record a hit for ``key``. Returns (allowed, retry_after_seconds)."""
        if not self.enabled:
            return True, 0.0
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            if len(self._hits) > _MAX_KEYS:
                self._hits.clear()  # crude but bounded under a distributed flood
            dq = self._hits[key]
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= self.limit:
                return False, max(self.window - (now - dq[0]), 0.0)
            dq.append(now)
            return True, 0.0
