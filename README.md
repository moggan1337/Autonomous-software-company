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

And the company is **alive**, not just reactive:

- **Autopilot (the world)** — flip it on and a background world generates inbound
  work on its own — support tickets, sales leads, product ideas, analytics
  requests — which the company handles with no human input at all. This is the
  full vision: one person watches a company run itself.
- **Real-time dashboard** — activity and agent reasoning are pushed live over
  Server-Sent Events (no polling); you watch each agent start "thinking" and
  hand work off the instant it happens.
- **Standing orders** — schedule recurring directives ("every 30s, analyze
  retention") that the company submits to itself on a timer, so routine
  operations run on a cadence without you lifting a finger.

And the human stays **in control** when they want to be:

- **Approval gates** — turn them on and outward-facing or hard-to-reverse work
  (sales, marketing, anything that sends/publishes/deploys/deletes) pauses for
  your sign-off. Approve or reject each item from the dashboard; everything else
  still flows autonomously.
- **Agent configuration** — click any department to tune its reasoning effort,
  model, and extra instructions, or disable it entirely. Changes take effect on
  the next task and persist across restarts.
- **Cost & budget tracking** — every completed task records estimated token
  usage and cost; the dashboard shows live spend against a budget and the
  company raises an alert when the budget is exceeded.

It has a real **business backbone**:

- **CRM / pipeline** — completed Sales work becomes real Customer and Deal
  records (won or lost, ~75% win rate), and resolved Support issues become
  Tickets. The dashboard shows active customers, win rate, revenue, recent deals,
  and recent tickets — all created automatically from agent activity.

And it's **production-ready**:

- **Business KPIs over time** — revenue, customers, tickets resolved, and
  deliverables are snapshotted after every completed task and charted live on the
  dashboard. Revenue and customers read straight off the CRM (won deals, active
  customers), so the charts are backed by real entities, not a formula.
- **Optional auth** — set `COMPANY_API_TOKEN` and state-changing requests require
  the token (reads stay open so the dashboard still works); unset, everything is
  open for local use.
- **Container + CI** — a `Dockerfile` and `docker compose` for one-command
  deploys, and a GitHub Actions workflow that lints (ruff) and runs the full test
  suite on every push, plus a Docker build job.

## What the agents do

| Department | Responsibility |
|---|---|
| **CEO / Orchestrator** | The only agent you talk to. Turns your direction into the first wave of delegated tasks. |
| **Product Management** | Writes specs with user stories & acceptance criteria; routes build + positioning. |
| **Development** | Implements features from specs, validates the code compiles, opens a PR; fixes QA-reported defects on rework. |
| **Quality Assurance** | Independently re-checks builds, **approves or rejects**, drives the rework loop, then asks Support to prep release notes. |
| **Marketing** | Creates positioning and launch campaigns; briefs Sales. |
| **Sales** | Turns campaign interest into pipeline and outreach; closes deals into the CRM. |
| **Customer Support** | Resolves issues (filing CRM tickets), writes help content, escalates real gaps to Product. |
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

### Run with Docker

```bash
docker compose up --build      # http://127.0.0.1:8000, state persisted in a volume
# or:
docker build -t company . && docker run -p 8000:8000 company
```

## The dashboard

The single human seat. From `http://127.0.0.1:8000` you can:

- **Give a direction** in the CEO console (or click an example).
- Flip on **Autopilot** to let the world send inbound work the company handles itself.
- Add **Standing orders** to run a directive on a repeating schedule.
- Flip on **Approvals** to gate risky work, then approve/reject from the queue.
- Click any **department** to configure its effort, model, instructions, or disable it.
- Watch a live **reasoning ticker** as agents start working (streamed, not polled).
- Watch every **department** light up as it works (live status).
- Track **Business KPIs** (revenue, customers, tickets resolved) on live charts.
- Browse the **CRM** — active customers, win rate, recent deals and tickets.
- **Drill down** — click a directive to see its full task tree (with statuses,
  rework, and artifacts) and cost; click a deal to see the customer's record.
- Follow the **activity feed** of delegations, work, and hand-offs in real time.
- Open any **deliverable** to read what an agent produced.
- See company-wide **metrics** (tasks, in progress, awaiting, rework, est. cost).

## Configuration

All via environment variables (or a `.env` file — see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | _(unset)_ | Claude key. Unset ⇒ simulation mode. |
| `COMPANY_MODEL` | `claude-opus-4-8` | Model every agent uses. |
| `COMPANY_EFFORT` | `high` | Reasoning effort: `low`…`max`. |
| `COMPANY_DB` | `company.db` | SQLite state file. |
| `COMPANY_SIMULATE` | `0` | Set `1` to force simulation even with a key. |
| `COMPANY_BUDGET` | `25` | Spend budget (USD) before the company raises a budget alert. |
| `COMPANY_API_TOKEN` | _(unset)_ | If set, state-changing API calls require this token. |

## Architecture

```
company/
  config.py          settings + .env loader
  models.py          domain types: Department, Task, Artifact, Directive, Event
  db.py              SQLite persistence (atomic task claiming, snapshots, rework tracking)
  llm.py             Claude wrapper (adaptive thinking, structured outputs, graceful fallback)
  tools.py           real tools: company memory (recall), live metrics, code validation
  bus.py             thread-safe pub/sub bridging the worker thread to SSE subscribers
  world.py           autopilot: generates inbound tickets/leads/ideas on a timer
  agentconfig.py     human-tunable per-department config (model/effort/instructions/enabled)
  (standing orders)  recurring directives on a schedule — see orchestrator + db
  (CRM)              customers / deals / tickets from agent activity — see orchestrator + db
  orchestrator.py    the engine: delegation, work loop, rework, approvals, cost, background worker
  agents/
    ceo.py           decomposes a human directive into delegated tasks
    base.py          shared agent contract: summary + artifact + cross-dept hand-offs
    departments.py   the seven department agents (Claude-guided + simulation)
  api.py             FastAPI: dashboard host + JSON API
web/                 single-page dashboard (no build step) — incl. live KPI charts
run.py               `serve` and `demo` entrypoints
tests/               pytest suite (runs fully offline in simulation mode)
Dockerfile           container image; docker-compose.yml for one-command run
pyproject.toml       project metadata, ruff + pytest config
.github/workflows/   CI: ruff lint + pytest + docker build on every push
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
| `GET` | `/api/state` | Full live snapshot (directives, tasks, artifacts, events, metrics, approvals, agents, cost, KPIs, CRM). |
| `GET` | `/api/directives/{id}` | Drill-down: a directive's task tree, artifacts, and cost. |
| `GET` | `/api/customers/{id}` | Drill-down: a customer with their deals and tickets. |
| `GET` | `/api/stream` | Server-Sent Events: live activity + agent reasoning. |
| `POST` | `/api/directive` | Submit a human direction: `{"text": "..."}`. |
| `POST` | `/api/world/start` · `/stop` | Turn autopilot on/off. |
| `POST` | `/api/schedules` | Create a standing order: `{"text": "...", "interval_seconds": N}`. |
| `POST` | `/api/schedules/{id}/toggle` · `DELETE /api/schedules/{id}` | Pause/resume or delete a standing order. |
| `POST` | `/api/approvals/start` · `/stop` | Turn approval gating on/off. |
| `POST` | `/api/tasks/{id}/approve` · `/reject` | Decide on a task awaiting approval. |
| `GET` | `/api/agents` | List per-department agent configs. |
| `PUT` | `/api/agents/{department}` | Update a department's model/effort/instructions/enabled. |

State-changing calls (`POST`/`PUT`) require `Authorization: Bearer <token>` (or
`X-API-Token`) when `COMPANY_API_TOKEN` is set; `GET` endpoints stay open.

## Tests

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

The suite (64 tests) runs entirely offline (forced simulation mode, isolated
temp DB) and covers CEO routing, the cross-department cascade and its
termination, deliverable production, the snapshot shape, the LLM fallback, the
HTTP API, the tools (memory recall, live metrics, code validation), the QA
rework loop (rejection → fix → re-verify, bounded and terminating), the world
autopilot, standing orders (recurring directives), the CRM/pipeline (customers,
deals, tickets from agent activity), drill-down detail (directive task trees and
customer records), the cross-thread event bus, the human-in-the-loop controls
(approval gating, agent config persistence, cost tracking, budget alerts), the
KPI time series, and optional token auth.

## Design notes

- **Emergent org behavior from one rule:** every agent returns the same shape —
  a summary, an optional deliverable, and follow-up tasks for other departments.
  That single contract is what makes a one-line instruction fan out into
  coordinated, multi-department work.
- **Always runnable:** the Claude layer degrades to deterministic simulation, so
  the company never hard-depends on network or credentials.
- **One human seat:** the only human input is a directive; everything downstream
  is autonomous.
