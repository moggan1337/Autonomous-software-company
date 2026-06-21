"""HTTP API and dashboard host for the autonomous software company.

This is the human's single seat: submit a direction, watch every department work.
The background worker runs the company continuously; the dashboard polls
``/api/state`` for a live snapshot.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .models import Department
from .orchestrator import Company

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# A small delay per task makes the activity feed readable in simulation mode,
# where work would otherwise complete instantly.
company = Company(step_delay=0.25)


@asynccontextmanager
async def lifespan(app: FastAPI):
    company.bus.bind_loop(asyncio.get_running_loop())
    company.start()
    try:
        yield
    finally:
        company.stop()


app = FastAPI(title="Autonomous Software Company", version="0.1.0", lifespan=lifespan)


class DirectiveIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class AgentConfigIn(BaseModel):
    model: str | None = None
    effort: str | None = None
    instructions: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "mode": company.snapshot()["mode"]}


@app.get("/api/state")
def state() -> JSONResponse:
    return JSONResponse(company.snapshot())


@app.post("/api/directive")
def submit_directive(payload: DirectiveIn) -> JSONResponse:
    directive = company.submit_directive(payload.text.strip())
    return JSONResponse({"directive": directive.to_dict()})


@app.post("/api/world/start")
def world_start() -> dict:
    company.start_world()
    return {"autopilot": True}


@app.post("/api/world/stop")
def world_stop() -> dict:
    company.stop_world()
    return {"autopilot": False}


@app.post("/api/approvals/start")
def approvals_start() -> dict:
    company.set_approvals(True)
    return {"approvals_enabled": True}


@app.post("/api/approvals/stop")
def approvals_stop() -> dict:
    company.set_approvals(False)
    return {"approvals_enabled": False}


@app.post("/api/tasks/{task_id}/approve")
def approve(task_id: str) -> dict:
    if not company.approve_task(task_id):
        raise HTTPException(status_code=404, detail="No task awaiting approval with that id.")
    return {"ok": True}


@app.post("/api/tasks/{task_id}/reject")
def reject(task_id: str) -> dict:
    if not company.reject_task(task_id):
        raise HTTPException(status_code=404, detail="No task awaiting approval with that id.")
    return {"ok": True}


@app.get("/api/agents")
def list_agents() -> JSONResponse:
    return JSONResponse({"agents": company.config.all()})


@app.put("/api/agents/{department}")
def update_agent(department: str, payload: AgentConfigIn) -> JSONResponse:
    try:
        dept = Department(department)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown department.")
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    cfg = company.update_agent_config(dept, **fields)
    return JSONResponse({"agent": cfg.to_dict()})


@app.get("/api/stream")
async def stream() -> StreamingResponse:
    """Server-Sent Events: push activity and agent reasoning to the dashboard live."""

    async def event_stream():
        q = company.bus.subscribe()
        try:
            yield 'data: {"type": "hello"}\n\n'
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(item)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # comment frame keeps the connection open
        finally:
            company.bus.unsubscribe(q)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
