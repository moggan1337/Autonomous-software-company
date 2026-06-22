"""Real-time push: the cross-thread event bus and the autopilot endpoints.

The SSE endpoint streams whatever the bus publishes. We test the bus directly
(it's the part with real concurrency logic) rather than consuming an infinite
SSE body through TestClient, which deadlocks on close.
"""
import asyncio
import threading

from fastapi.testclient import TestClient

from company.api import app
from company.bus import EventBus


def test_eventbus_delivers_across_threads():
    """The worker thread publishes; an asyncio subscriber (the SSE handler) receives."""

    async def scenario():
        bus = EventBus()
        bus.bind_loop(asyncio.get_running_loop())
        q = bus.subscribe()
        threading.Thread(
            target=lambda: bus.publish({"type": "event", "data": {"n": 1}})
        ).start()
        item = await asyncio.wait_for(q.get(), timeout=2)
        assert item == {"type": "event", "data": {"n": 1}}
        bus.unsubscribe(q)

    asyncio.run(scenario())


def test_eventbus_noop_without_loop():
    """Publishing before a loop is bound is a safe no-op (CLI / tests)."""
    EventBus().publish({"type": "event", "data": {}})  # must not raise


def test_stream_route_registered():
    paths = {r.path for r in app.routes}
    assert "/api/stream" in paths


def test_autopilot_endpoints_toggle_state():
    with TestClient(app) as client:
        assert client.post("/api/world/start").json()["autopilot"] is True
        assert client.get("/api/state").json()["autopilot"] is True
        assert client.post("/api/world/stop").json()["autopilot"] is False
        assert client.get("/api/state").json()["autopilot"] is False


def test_approvals_endpoints_toggle_state():
    with TestClient(app) as client:
        assert client.post("/api/approvals/start").json()["approvals_enabled"] is True
        assert client.get("/api/state").json()["approvals_enabled"] is True
        assert client.post("/api/approvals/stop").json()["approvals_enabled"] is False


def test_agent_config_endpoint_updates():
    with TestClient(app) as client:
        res = client.put("/api/agents/support", json={"instructions": "Be terse.", "enabled": True})
        assert res.status_code == 200
        assert res.json()["agent"]["instructions"] == "Be terse."
        agents = client.get("/api/agents").json()["agents"]
        support = next(a for a in agents if a["department"] == "support")
        assert support["instructions"] == "Be terse."


def test_unknown_department_is_404():
    with TestClient(app) as client:
        assert client.put("/api/agents/nope", json={"enabled": False}).status_code == 404


def test_schedule_endpoints_crud():
    with TestClient(app) as client:
        created = client.post(
            "/api/schedules", json={"text": "Analyze retention", "interval_seconds": 30}
        )
        assert created.status_code == 200
        oid = created.json()["schedule"]["id"]
        assert client.post(f"/api/schedules/{oid}/toggle").json()["schedule"]["enabled"] is False
        assert client.delete(f"/api/schedules/{oid}").status_code == 200
        assert client.delete(f"/api/schedules/{oid}").status_code == 404


def test_schedule_interval_validation():
    with TestClient(app) as client:
        # Below the 2s minimum is rejected.
        assert client.post(
            "/api/schedules", json={"text": "x", "interval_seconds": 0.5}
        ).status_code == 422


def test_approve_missing_task_is_404():
    with TestClient(app) as client:
        assert client.post("/api/tasks/task_doesnotexist/approve").status_code == 404
