"""HTTP API and dashboard host for the autonomous software company.

This is the human's single seat. A :class:`CompanyManager` runs one or more
independent companies; every endpoint is scoped by an optional ``?company=<id>``
query parameter that defaults to ``"default"``, so a single-company setup needs
no extra plumbing. The dashboard polls ``/api/state`` and streams ``/api/stream``.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import SETTINGS
from .manager import CompanyManager
from .models import Department
from .orchestrator import Company

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Optional auth: when COMPANY_API_TOKEN is set, every /api request (reads
# included — to protect tenant data) must carry the token. Liveness and the
# static dashboard assets stay open. When unset, the API is open for local use.
API_TOKEN = SETTINGS.api_token

# /api paths reachable without a token even when one is configured.
_PUBLIC_API_PATHS = {"/api/health"}


def _request_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    # x-api-token header or ?token= query (the latter lets EventSource/SSE auth,
    # since it cannot set request headers).
    return token or request.headers.get("x-api-token", "") or request.query_params.get("token", "")

# A small delay per task makes the activity feed readable in simulation mode,
# where work would otherwise complete instantly.
manager = CompanyManager(SETTINGS, step_delay=0.25)


def _co(company_id: str) -> Company:
    company = manager.get(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail=f"No company with id '{company_id}'.")
    return company


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager.bind_loop(asyncio.get_running_loop())
    manager.start_all()
    try:
        yield
    finally:
        manager.stop_all()


app = FastAPI(title="Autonomous Software Company", version="0.5.0", lifespan=lifespan)


@app.middleware("http")
async def require_token(request: Request, call_next):
    """When a token is configured, require it on all /api requests (reads too)."""
    if API_TOKEN:
        path = request.url.path
        if path.startswith("/api/") and path not in _PUBLIC_API_PATHS:
            if not hmac.compare_digest(_request_token(request), API_TOKEN):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


class DirectiveIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class AgentConfigIn(BaseModel):
    model: str | None = None
    effort: str | None = None
    instructions: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None


class ScheduleIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    interval_seconds: float = Field(ge=2, le=86400)


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "mode": _co("default").snapshot()["mode"]}


# ---- companies (tenants) --------------------------------------------------
@app.get("/api/companies")
def list_companies() -> JSONResponse:
    return JSONResponse({"companies": manager.list()})


@app.post("/api/companies")
def create_company(payload: CompanyIn) -> JSONResponse:
    try:
        company = manager.create(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    return JSONResponse({"company": company})


# ---- per-company endpoints (scoped by ?company=) --------------------------
@app.get("/api/state")
def state(company: str = "default") -> JSONResponse:
    return JSONResponse(_co(company).snapshot())


@app.post("/api/directive")
def submit_directive(payload: DirectiveIn, company: str = "default") -> JSONResponse:
    directive = _co(company).submit_directive(payload.text.strip())
    return JSONResponse({"directive": directive.to_dict()})


@app.post("/api/world/start")
def world_start(company: str = "default") -> dict:
    _co(company).start_world()
    return {"autopilot": True}


@app.post("/api/world/stop")
def world_stop(company: str = "default") -> dict:
    _co(company).stop_world()
    return {"autopilot": False}


@app.post("/api/approvals/start")
def approvals_start(company: str = "default") -> dict:
    _co(company).set_approvals(True)
    return {"approvals_enabled": True}


@app.post("/api/approvals/stop")
def approvals_stop(company: str = "default") -> dict:
    _co(company).set_approvals(False)
    return {"approvals_enabled": False}


@app.post("/api/tasks/{task_id}/approve")
def approve(task_id: str, company: str = "default") -> dict:
    if not _co(company).approve_task(task_id):
        raise HTTPException(status_code=404, detail="No task awaiting approval with that id.")
    return {"ok": True}


@app.post("/api/tasks/{task_id}/reject")
def reject(task_id: str, company: str = "default") -> dict:
    if not _co(company).reject_task(task_id):
        raise HTTPException(status_code=404, detail="No task awaiting approval with that id.")
    return {"ok": True}


@app.get("/api/agents")
def list_agents(company: str = "default") -> JSONResponse:
    return JSONResponse({"agents": _co(company).config.all()})


@app.put("/api/agents/{department}")
def update_agent(department: str, payload: AgentConfigIn, company: str = "default") -> JSONResponse:
    try:
        dept = Department(department)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown department.")
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    cfg = _co(company).update_agent_config(dept, **fields)
    return JSONResponse({"agent": cfg.to_dict()})


@app.post("/api/schedules")
def create_schedule(payload: ScheduleIn, company: str = "default") -> JSONResponse:
    order = _co(company).create_standing_order(payload.text.strip(), payload.interval_seconds)
    return JSONResponse({"schedule": order})


@app.post("/api/schedules/{order_id}/toggle")
def toggle_schedule(order_id: str, company: str = "default") -> JSONResponse:
    order = _co(company).toggle_standing_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="No standing order with that id.")
    return JSONResponse({"schedule": order})


@app.delete("/api/schedules/{order_id}")
def delete_schedule(order_id: str, company: str = "default") -> dict:
    if not _co(company).delete_standing_order(order_id):
        raise HTTPException(status_code=404, detail="No standing order with that id.")
    return {"ok": True}


@app.get("/api/directives/{directive_id}")
def directive_detail(directive_id: str, company: str = "default") -> JSONResponse:
    detail = _co(company).directive_detail(directive_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="No directive with that id.")
    return JSONResponse(detail)


@app.get("/api/customers/{customer_id}")
def customer_detail(customer_id: str, company: str = "default") -> JSONResponse:
    detail = _co(company).customer_detail(customer_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="No customer with that id.")
    return JSONResponse(detail)


@app.get("/api/stream")
async def stream(company: str = "default") -> StreamingResponse:
    """Server-Sent Events: push activity and agent reasoning to the dashboard live."""
    co = _co(company)

    async def event_stream():
        q = co.bus.subscribe()
        try:
            yield 'data: {"type": "hello"}\n\n'
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(item)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"  # comment frame keeps the connection open
        finally:
            co.bus.unsubscribe(q)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
