"""A tiny thread-safe pub/sub bus for pushing live updates to the dashboard.

The company's work loop runs in a background thread (synchronous), while the
web layer serves Server-Sent Events from the asyncio loop. This bus bridges the
two: the worker thread calls :meth:`publish`, which hands each item to every
subscriber's asyncio queue via the bound event loop.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once from the web layer so cross-thread publishes can enqueue."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, item: dict[str, Any]) -> None:
        """Fan an item out to all subscribers. No-op until a loop is bound."""
        loop = self._loop
        if loop is None:
            return
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                loop.call_soon_threadsafe(_offer, q, item)
            except RuntimeError:  # pragma: no cover - loop shutting down
                pass


def _offer(q: asyncio.Queue, item: dict) -> None:
    """Put without blocking; drop on a slow/full consumer rather than stall."""
    try:
        q.put_nowait(item)
    except asyncio.QueueFull:  # pragma: no cover - slow client
        pass
