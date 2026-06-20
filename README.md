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

The agents are also **grounded and accountable**, not just generative:

- **Company memory** — before acting, every agent recalls relevant prior work
  (specs, code, reports) and builds on it instead of starting cold.
- **Real tools** — Analytics computes live metrics from the operational database
  (throughput, cycle time, rework rate); Development writes code to a workspace
  and validates that it compiles.
- **QA rework loop** — QA independently re-checks each build and can **reject**
  it, sending it back to Development for a fix. The loop is bounded
  (`MAX_REWORK`), so it always terminates — a feature ships once it passes or the
  rework budget is exhausted.

## What the agents do

| Department | Responsibility |
|---|---|
| **CEO / Orchestrator** | The only agent you talk to. Turns your direction into the first wave of delegated tasks. |
| **Product Management** | Writes specs with user stories & acceptance criteria; routes build + positioning. |
| **Development** | Implements features from specs, validates the code compiles, opens a PR; fixes QA-reported defects on rework. |
| **Quality Assurance** | Independently re-checks builds, **approves or rejects**, drives the rework loop, then asks Support to prep release notes. |
| **Marketing** | Creates positioning and launch campaigns; briefs Sales. |
| **Sales** | Turns campaign interest into pipeline and outreach sequences. |
| **Customer Support** | Resolves issues, reuses/writes help content, escalates real gaps to Product. |
| **Analytics** | Measures **real outcomes from company data** and recommends the next move. |

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
  db.py              SQLite persistence (atomic task claiming, snapshots, rework tracking)
  llm.py             Claude wrapper (adaptive thinking, structured outputs, graceful fallback)
  tools.py           real tools: company memory (recall), live metrics, code validation
  orchestrator.py    the engine: delegation, work loop, bounded cascade + rework, background worker
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
departments. Two safety limits keep it from running forever: a hand-off depth
limit (`MAX_DEPTH`) and a rework budget (`MAX_REWORK`) for the QA → Development
loop. A directive auto-closes when all its tasks are done.

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

The suite (20 tests) runs entirely offline (forced simulation mode, isolated
temp DB) and covers CEO routing, the cross-department cascade and its
termination, deliverable production, the snapshot shape, the LLM fallback, the
HTTP API, the tools (memory recall, live metrics, code validation), and the QA
rework loop (rejection → fix → re-verify, bounded and terminating).

## Design notes

- **Emergent org behavior from one rule:** every agent returns the same shape —
  a summary, an optional deliverable, and follow-up tasks for other departments.
  That single contract is what makes a one-line instruction fan out into
  coordinated, multi-department work.
- **Always runnable:** the Claude layer degrades to deterministic simulation, so
  the company never hard-depends on network or credentials.
- **One human seat:** the only human input is a directive; everything downstream
  is autonomous.
