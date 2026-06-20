"""HTTP API and dashboard host for the autonomous software company.

This is the human's single seat: submit a direction, watch every department work.
The background worker runs the company continuously; the dashboard polls
``/api/state`` for a live snapshot.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .orchestrator import Company

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# A small delay per task makes the activity feed readable in simulation mode,
# where work would otherwise complete instantly.
company = Company(step_delay=0.25)


@asynccontextmanager
async def lifespan(app: FastAPI):
    company.start()
    try:
        yield
    finally:
        company.stop()


app = FastAPI(title="Autonomous Software Company", version="0.1.0", lifespan=lifespan)


class DirectiveIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


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


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
