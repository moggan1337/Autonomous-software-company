# Autonomous Software Company

A company where **AI agents perform nearly all operations** and a single human only
provides direction. You type one instruction; the CEO agent delegates it, and the
work cascades through seven AI departments on its own — exactly like a 100-person
org, run from one seat.

> **Vision:** one person running a company that would traditionally require 100+ employees.

```
        Human (you)
            │  one direction
            ▼
        ┌─────────┐
        │   CEO   │  decomposes & delegates
        └────┬────┘
   ┌─────────┼───────────────────────────────┐
   ▼         ▼                                ▼
Product → Development → QA → Support     Marketing → Sales
   │                                                  
   └──────────────► Analytics (measures outcomes) ◄──┘
```

Each department is an autonomous agent. When it finishes a task it produces a
concrete **deliverable** (a spec, code, a QA report, a campaign, a sales plan,
help docs, an analytics report) and **hands off** the natural next steps to other
departments — no human in the loop after the first instruction.

## What the agents do

| Department | Responsibility |
|---|---|
| **CEO / Orchestrator** | The only agent you talk to. Turns your direction into the first wave of delegated tasks. |
| **Product Management** | Writes specs with user stories & acceptance criteria; routes build + positioning. |
| **Development** | Implements features from specs; opens a PR; hands the build to QA. |
| **Quality Assurance** | Verifies builds, reports results, signs off; asks Support to prep release notes. |
| **Marketing** | Creates positioning and launch campaigns; briefs Sales. |
| **Sales** | Turns campaign interest into pipeline and outreach sequences. |
| **Customer Support** | Resolves issues, writes help content, escalates real gaps to Product. |
| **Analytics** | Measures outcomes and recommends the next move. |

## Runs with or without an API key

The company is powered by **Claude (`claude-opus-4-8`)** with adaptive thinking and
structured outputs. If no `ANTHROPIC_API_KEY` is set, every agent falls back to a
deterministic **simulation mode** so the whole company still runs, cascades work,
and produces deliverables — ideal for demos and tests. Set a key to have real
Claude write the specs, code, campaigns, and analyses.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Option A — the live dashboard (recommended)
python run.py serve            # then open http://127.0.0.1:8000

# Option B — run one direction in the terminal
python run.py demo "Launch a dark mode feature"
```

To use real Claude:

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=...
python run.py serve
```

## The dashboard

The single human seat. From `http://127.0.0.1:8000` you can:

- **Give a direction** in the CEO console (or click an example).
- Watch every **department** light up as it works (live status).
- Follow the **activity feed** of delegations, work, and hand-offs in real time.
- Open any **deliverable** to read what an agent produced.
- See company-wide **metrics** (tasks, in progress, done, deliverables).

## Configuration

All via environment variables (or a `.env` file — see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | _(unset)_ | Claude key. Unset ⇒ simulation mode. |
| `COMPANY_MODEL` | `claude-opus-4-8` | Model every agent uses. |
| `COMPANY_EFFORT` | `high` | Reasoning effort: `low`…`max`. |
| `COMPANY_DB` | `company.db` | SQLite state file. |
| `COMPANY_SIMULATE` | `0` | Set `1` to force simulation even with a key. |

## Architecture

```
company/
  config.py          settings + .env loader
  models.py          domain types: Department, Task, Artifact, Directive, Event
  db.py              SQLite persistence (atomic task claiming, snapshots)
  llm.py             Claude wrapper (adaptive thinking, structured outputs, graceful fallback)
  orchestrator.py    the engine: delegation, work loop, bounded cascade, background worker
  agents/
    ceo.py           decomposes a human directive into delegated tasks
    base.py          shared agent contract: summary + artifact + cross-dept hand-offs
    departments.py   the seven department agents (Claude-guided + simulation)
  api.py             FastAPI: dashboard host + JSON API
web/                 single-page dashboard (no build step)
run.py               `serve` and `demo` entrypoints
tests/               pytest suite (runs fully offline in simulation mode)
```

**How work flows:** `submit_directive` → CEO plans first tasks → the work loop has
each department atomically claim its next task, the agent does the work (Claude or
simulation), persists a deliverable, and queues follow-up tasks for other
departments. A depth limit (`MAX_DEPTH`) keeps the natural chain
(spec → build → QA → docs) from running forever. A directive auto-closes when all
its tasks are done.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | The dashboard. |
| `GET` | `/api/health` | Liveness + current mode. |
| `GET` | `/api/state` | Full live snapshot (directives, tasks, artifacts, events, metrics). |
| `POST` | `/api/directive` | Submit a human direction: `{"text": "..."}`. |

## Tests

```bash
pip install pytest httpx
python -m pytest
```

The suite runs entirely offline (forced simulation mode, isolated temp DB) and
covers the CEO routing, the cross-department cascade, cascade termination,
deliverable production, the snapshot shape, the LLM fallback, and the HTTP API.

## Design notes

- **Emergent org behavior from one rule:** every agent returns the same shape —
  a summary, an optional deliverable, and follow-up tasks for other departments.
  That single contract is what makes a one-line instruction fan out into
  coordinated, multi-department work.
- **Always runnable:** the Claude layer degrades to deterministic simulation, so
  the company never hard-depends on network or credentials.
- **One human seat:** the only human input is a directive; everything downstream
  is autonomous.
