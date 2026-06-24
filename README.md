# Autonomous Software Company

> **A company where AI agents perform nearly all operations — and a single human only provides direction.**
> You type one instruction; a CEO agent delegates it, and the work cascades through seven AI departments on its own, producing real deliverables, customers, and revenue. It's a 100-person org you run from one seat.

![Python](https://img.shields.io/badge/python-3.11-blue)
![Tests](https://img.shields.io/badge/tests-77%20passing-brightgreen)
![Lint](https://img.shields.io/badge/lint-ruff-7c3aed)
![Powered by](https://img.shields.io/badge/powered%20by-Claude-d97757)
![Runs offline](https://img.shields.io/badge/runs-offline%20(simulation)-success)

---

## Table of contents

- [Vision](#vision)
- [Highlights](#highlights)
- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [The dashboard](#the-dashboard)
- [The departments](#the-departments)
- [Concepts & data model](#concepts--data-model)
- [Claude mode vs. simulation mode](#claude-mode-vs-simulation-mode)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Multi-tenancy](#multi-tenancy)
- [Security](#security)
- [Project layout](#project-layout)
- [Development & testing](#development--testing)
- [Extending the company](#extending-the-company)
- [Design principles](#design-principles)
- [Troubleshooting / FAQ](#troubleshooting--faq)
- [Roadmap & status](#roadmap--status)

---

## Vision

Traditionally, shipping and running a software product takes dozens of people across
product, engineering, QA, marketing, sales, support, and analytics. **This project
collapses all of that into AI agents.** A human provides *direction* — one sentence —
and the company does the rest:

```
        Human (you)
            │  one direction  ("Launch a dark mode feature")
            ▼
        ┌─────────┐
        │   CEO   │  decomposes & delegates the first wave of work
        └────┬────┘
   ┌─────────┼─────────────────────────────────────┐
   ▼         ▼                                       ▼
Product ─▶ Development ─▶ QA ─▶ Support        Marketing ─▶ Sales
   │            ▲         │                                   │
   │            └─ rework ┘  (QA can reject)                  ▼
   └────────────────────────────────► Analytics ◀── CRM (customers, deals, tickets)
                                       (measures real outcomes)
```

Each department is an autonomous agent. When it finishes a task it produces a
concrete **deliverable** (a spec, code, a QA report, a campaign, a sales plan,
help docs, an analytics report) and **hands off** the natural next steps to other
departments. No human is in the loop after the first instruction — unless you
*want* to be (see [approval gates](#human-in-the-loop)).

The whole thing **runs with or without an API key**: with `ANTHROPIC_API_KEY` set,
real Claude writes everything; without it, a deterministic simulation produces
realistic output so you can explore, demo, and test the entire system offline.

---

## Highlights

**Autonomous operations**
- **CEO delegation** — one human directive becomes the first wave of departmental tasks.
- **Emergent cascade** — departments hand work to each other, so a single instruction fans out across the whole org (spec → build → QA → release notes; campaign → pipeline).
- **Bounded & terminating** — a hand-off depth limit (`MAX_DEPTH = 8`) and a QA rework budget (`MAX_REWORK = 2`) guarantee every directive finishes.

**Grounded, accountable agents**
- **Company memory** — agents recall relevant prior work (specs, code, reports) before acting and build on it instead of starting cold.
- **Real tools** — Analytics computes live metrics from the database; Development writes code to a workspace and validates it compiles (`py_compile`, never executed).
- **QA rework loop** — QA independently re-checks each build and can **reject** it, sending it back to Development for a fix, until it passes or the budget is exhausted.

**A living company**
- **Autopilot (the world)** — a background world generates inbound work on its own (support tickets, sales leads, product ideas, analytics requests) which the company handles unattended.
- **Standing orders** — schedule recurring directives ("every 30s, analyze retention") the company submits to itself on a timer.
- **Real-time dashboard** — activity and agent "thinking" are pushed live over Server-Sent Events (no polling).

**Human-in-the-loop**
- **Approval gates** — gate outward-facing / hard-to-reverse work (sales, marketing, anything that sends/publishes/deploys/deletes) for your sign-off.
- **Agent configuration** — tune each department's model, reasoning effort, and extra instructions, or disable it — persisted across restarts.
- **Cost & budget tracking** — estimated token cost per task, live spend vs. budget, and a budget-exceeded alert.

**A real business backbone**
- **CRM / pipeline** — completed Sales work becomes Customer + Deal records (won/lost); resolved Support issues become Tickets.
- **Business KPIs over time** — revenue, customers, tickets resolved, and deliverables are snapshotted and charted live, read straight off the CRM.
- **Drill-down** — open any directive to see its full task tree, artifacts, and cost; open any deal to see the customer's record.

**Multi-tenant & production-ready**
- **Many companies, one deployment** — each company is fully isolated (own database, agents, world, CRM); switch or create from the dashboard.
- **Optional auth** — a single token gates the whole API (reads included) when set.
- **Rate limiting** — per-client throttling of state-changing requests.
- **Docker + CI** — one-command container deploy and a GitHub Actions pipeline (ruff lint + 77 tests + Docker build).

---

## How it works

### The one rule that creates an org

Every worker agent — whatever its department — returns the **same shape**:

```jsonc
{
  "summary":  "what I did",
  "verdict":  "approved" | "rejected" | null,   // QA only
  "artifact": { "title": "...", "kind": "spec|code|report|...", "content": "..." } | null,
  "followups": [
    { "department": "qa", "title": "...", "description": "...", "priority": "high" }
  ]
}
```

That single contract is the whole trick: a summary, an optional **deliverable**, and
zero or more **follow-up tasks for other departments**. Because Product's follow-ups
land in Development's queue, and Development's land in QA's, a one-line instruction
fans out into coordinated, multi-department work — no central script tells the
company "now do QA." The behavior **emerges** from the hand-offs.

### The work loop

```
submit_directive(text)
   └─ CEO.plan() ───────────────▶ first tasks (one per relevant department)
        for each tick:
          for each department (that is enabled):
            task = claim_next_task(department)        # atomic, priority-ordered
            if approvals on and task is risky:        # park for human sign-off
                → AWAITING_APPROVAL
            result = agent.work(task)                 # Claude, or simulation
            persist deliverable + record cost + KPI + CRM
            if QA verdict == "rejected":              # bounded rework
                open a Development "fix" task
            else:
                enqueue result.followups
          directive auto-closes when all its tasks are done/blocked
```

- **Atomic claiming** — `claim_next_task` marks a task `in_progress` under a write
  lock, so concurrent department loops never grab the same task. Tasks are ordered
  by priority (`urgent` → `high` → `normal` → `low`) then age.
- **Background worker** — a daemon thread runs the loop continuously so the dashboard
  shows live progress; tests drive the same loop synchronously via `run_until_idle()`.

### The rework loop (accountability)

QA doesn't rubber-stamp. It independently re-validates the latest build (recalling
Development's code artifact and re-compiling it), sets `verdict: "approved" | "rejected"`,
and on rejection the orchestrator opens a Development *fix* task carrying an
incremented `rework_count`. Development ships a v2, QA re-verifies, and the feature
ships once it passes — or once `MAX_REWORK` is reached (then it ships with known
issues). This loop is **deterministic in simulation** (a feature is "flaky" based on
a hash of its name) so it's reproducible and always terminates.

### The CRM & KPIs (a real business)

Completed work becomes business entities, not just log lines:

- A completed **Sales** task → a `Customer` + a won/lost `Deal` (~75% win rate,
  value modeled from the task).
- A resolved **Support** issue → a `Ticket`.

KPIs then read **straight off those entities** — `revenue = Σ won-deal values`,
`customers = active customers`, `tickets_resolved = resolved tickets` — and are
snapshotted after every completed task into a time series the dashboard charts.
So the numbers are backed by real records, not a formula on task counts.

### Two ways work arrives

| Source | Trigger | Tagged |
|---|---|---|
| **Human** | You submit a directive in the console / `POST /api/directive` | `source: human` |
| **Autopilot (world)** | A background timer emits inbound tickets/leads/ideas | `source: world` |
| **Standing order** | A recurring directive fires on its interval | `source: schedule` |

---

## Quick start

**Requirements:** Python 3.11+. No external services required (it runs offline in
simulation mode).

```bash
git clone <your-fork-url> && cd Autonomous-software-company
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Run the live dashboard (recommended):**

```bash
python run.py serve            # open http://127.0.0.1:8000
```

**Run a single directive in the terminal:**

```bash
python run.py demo "Launch a dark mode feature"
```

<details>
<summary>Example <code>demo</code> output (simulation mode)</summary>

```
=== Autonomous Software Company (simulation mode) ===
Direction: Launch a dark mode feature

--- Activity feed ---
  [ceo        ] New direction received: Launch a dark mode feature
  [ceo        ] Delegated to Product Management: Launch a dark mode feature
  [product    ] Produced spec: Spec: Launch a dark mode feature
  [product    ] Handed off to Development: Implement ...
  [development] Produced code: PR v1: ...
  [development] Handed off to Quality Assurance: Verify ...
  [qa         ] Produced report: QA Report: ... (approved)
  [qa         ] Handed off to Customer Support: Prepare release notes ...
  [marketing  ] Produced campaign: Campaign: ...
  [sales      ] Produced plan: Sales Plan: ...
  [ceo        ] Direction complete — all work finished.
```
</details>

**Use real Claude:**

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...
python run.py serve
```

**Run with Docker:**

```bash
docker compose up --build      # http://127.0.0.1:8000, state persisted in a named volume
# or, plain Docker:
docker build -t company . && docker run -p 8000:8000 company
```

---

## The dashboard

The single human seat at `http://127.0.0.1:8000`:

- **Switch companies** (or create one) from the header — each is fully isolated.
- **Give a direction** in the CEO console (or click an example prompt).
- **Autopilot** toggle — let the world send inbound work the company handles itself.
- **Standing orders** — add a directive that runs on a repeating schedule.
- **Approvals** toggle — gate risky work, then approve/reject from the queue.
- **Department cards** — click one to configure its effort, model, instructions, or disable it; cards light up while working.
- **Reasoning ticker** — watch agents start "thinking" (streamed, not polled).
- **Business KPIs** — revenue / customers / tickets-resolved on live SVG charts.
- **CRM panel** — active customers, win rate, recent deals (won/lost) and tickets.
- **Directives list** — click any directive to drill into its full task tree, artifacts, rework, and cost.
- **Activity feed** — delegations, work, and hand-offs in real time.
- **Deliverables** — open any artifact to read exactly what an agent produced.
- **Metrics** — tasks, in progress, awaiting approval, rework, estimated cost.

The dashboard is a dependency-free single page (`web/`) — no build step.

---

## The departments

| Department | Responsibility |
|---|---|
| **CEO / Orchestrator** | The only agent you talk to. Turns your direction into the first wave of delegated tasks. |
| **Product Management** | Writes specs with user stories & acceptance criteria; routes building to Development and positioning to Marketing. |
| **Development** | Implements features from specs, validates the code compiles, "opens a PR"; fixes QA-reported defects on rework. |
| **Quality Assurance** | Independently re-checks builds, **approves or rejects**, drives the rework loop, then asks Support to prepare release notes. |
| **Marketing** | Creates positioning and launch campaigns; briefs Sales. |
| **Sales** | Turns campaign interest into pipeline and outreach; **closes deals into the CRM**. |
| **Customer Support** | Resolves issues (**filing CRM tickets**), writes help content, escalates real product gaps to Product. |
| **Analytics** | Measures **real outcomes from company data** and recommends the next move. |

Each agent's persona lives in `company/agents/` and is used as the Claude system
prompt; the same class also defines a deterministic `simulate()` for offline mode.

---

## Concepts & data model

All state lives in SQLite (`company/db.py`), one database **per company**.

### Task lifecycle

```
            ┌──────────── approvals on & risky ───────────┐
            ▼                                              │
pending ──▶ in_progress ──▶ done                  awaiting_approval
   ▲             │                                    │      │
   │             └──▶ blocked (error / rejected)      │      │
   └───────────── approve ◀──────────────────────────┘      │
                          reject ──▶ blocked ◀───────────────┘
```

| Type | Fields (selected) | Notes |
|---|---|---|
| `Directive` | `text`, `status`, `summary`, `source` (`human`/`world`/`schedule`) | A human (or world) instruction; the CEO breaks it into tasks. |
| `Task` | `title`, `department`, `status`, `priority`, `directive_id`, `parent_id`, `created_by`, `result`, `rework_count`, `approved` | The unit of work. `parent_id` builds the task tree; `rework_count` drives the QA loop. |
| `Artifact` | `title`, `department`, `kind`, `content`, `task_id` | A concrete deliverable (spec, code, report, campaign, plan, doc, reply). |
| `Event` | `department`, `message`, `kind` (`info`/`delegate`/`work`/`artifact`/`approval`/`error`) | The activity feed (control characters sanitized; table retention-capped). |
| `Customer` | `name`, `status` (`active`/`lost`), `seats`, `source` | Created when Sales closes a deal. |
| `Deal` | `name`, `value`, `stage` (`won`/`lost`), `customer_id`, `closed_at` | Revenue is the sum of won-deal values. |
| `Ticket` | `subject`, `status` (`resolved`/`open`), `priority`, `customer_id` | Filed when Support resolves an issue. |
| `StandingOrder` | `text`, `interval_seconds`, `enabled`, `next_run`, `runs` | A recurring directive. |
| `AgentConfig` | `department`, `model`, `effort`, `instructions`, `enabled` | Human-tunable per department; persisted. |
| KPI snapshot | `ts`, `revenue`, `customers`, `tickets_resolved`, `deliverables`, `tasks_done`, `cost` | One row per completed task; the time series for charts. |
| Usage (ledger) | `task_id`, `department`, `input_tokens`, `output_tokens`, `cost` | Cost ledger (never trimmed, so totals stay exact). |

**Enums:** `Department` (8, incl. CEO) · `TaskStatus` (`pending`, `in_progress`,
`awaiting_approval`, `done`, `blocked`) · `Priority` (`low`, `normal`, `high`, `urgent`).

---

## Claude mode vs. simulation mode

| | **Claude mode** (`ANTHROPIC_API_KEY` set) | **Simulation mode** (no key, or `COMPANY_SIMULATE=1`) |
|---|---|---|
| Who writes the work | Claude (`claude-opus-4-8` by default) with adaptive thinking + structured outputs | Deterministic per-department `simulate()` |
| Output quality | Real specs/code/campaigns/analyses | Realistic, templated, reproducible |
| Network / credentials | Required | None |
| Use for | Production-style runs | Demos, CI, offline development |
| Fallback | Any Claude error (refusal, network) **degrades to simulation** automatically | — |

The integration lives in `company/llm.py`: a thin wrapper that returns `None` on any
failure so the calling agent transparently falls back to simulation. **The company
never hard-depends on the network.** Models and reasoning effort are configurable
globally and per department.

---

## Configuration

All configuration is via environment variables (or a `.env` file — see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | _(unset)_ | Claude API key. Unset ⇒ simulation mode. |
| `COMPANY_MODEL` | `claude-opus-4-8` | Model every agent uses (override per-department in the UI). |
| `COMPANY_EFFORT` | `high` | Reasoning effort: `low` · `medium` · `high` · `xhigh` · `max`. |
| `COMPANY_DB` | `company.db` | SQLite path for the **default** company (others derive `company_<id>.db` beside it). |
| `COMPANY_SIMULATE` | `0` | Set `1` to force simulation even with a key. |
| `COMPANY_BUDGET` | `25` | Spend budget (USD) before the company raises a budget alert. |
| `COMPANY_API_TOKEN` | _(unset)_ | If set, **all** `/api` calls (except `/api/health`) require this token. |
| `COMPANY_RATE_LIMIT` | `300` | Max state-changing requests per client per window (`0` disables). |
| `COMPANY_RATE_WINDOW` | `60` | Rate-limit window length, in seconds. |

**Tunable constants** (in code): `MAX_DEPTH = 8` (hand-off depth), `MAX_REWORK = 2`
(QA loop budget), `MAX_COMPANIES = 50` (tenant cap), `EVENTS_KEEP`/`KPI_KEEP = 2000`
(table retention).

---

## API reference

Base URL `http://127.0.0.1:8000`. All responses are JSON unless noted.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | The dashboard (HTML). |
| `GET` | `/api/health` | Liveness + current mode (always open). |
| `GET` | `/api/companies` | List companies (tenants). |
| `POST` | `/api/companies` | Create a company: `{"name": "..."}` → `429` if at the cap. |
| `GET` | `/api/state` | Full live snapshot (directives, tasks, artifacts, events, metrics, approvals, agents, cost, KPIs, CRM). |
| `POST` | `/api/directive` | Submit a human direction: `{"text": "..."}`. |
| `GET` | `/api/stream` | Server-Sent Events: live activity + agent reasoning. |
| `GET` | `/api/directives/{id}` | Drill-down: a directive's task tree, artifacts, and cost. |
| `GET` | `/api/customers/{id}` | Drill-down: a customer with their deals and tickets. |
| `POST` | `/api/world/start` · `/api/world/stop` | Turn autopilot on/off. |
| `POST` | `/api/approvals/start` · `/api/approvals/stop` | Turn approval gating on/off. |
| `POST` | `/api/tasks/{id}/approve` · `/api/tasks/{id}/reject` | Decide on a task awaiting approval. |
| `POST` | `/api/schedules` | Create a standing order: `{"text": "...", "interval_seconds": N}` (2–86400). |
| `POST` | `/api/schedules/{id}/toggle` · `DELETE /api/schedules/{id}` | Pause/resume or delete a standing order. |
| `GET` | `/api/agents` | List per-department agent configs. |
| `PUT` | `/api/agents/{department}` | Update `model` / `effort` / `instructions` / `enabled`. |

**Company scoping.** Every per-company endpoint accepts an optional `?company=<id>`
(default `"default"`); omit it for a single-company setup. Unknown ids return `404`.

**Auth.** When `COMPANY_API_TOKEN` is set, all `/api` endpoints except `/api/health`
require the token — via `Authorization: Bearer <token>`, an `X-API-Token` header, or
`?token=` (the query form lets the SSE stream authenticate). Comparison is
constant-time.

**Rate limiting.** State-changing requests are throttled per client IP
(`COMPANY_RATE_LIMIT` per `COMPANY_RATE_WINDOW`s); reads and SSE are never throttled.
Exceeding the limit returns `429` with a `Retry-After` header.

### Examples

```bash
# Submit a direction
curl -X POST localhost:8000/api/directive \
  -H 'Content-Type: application/json' \
  -d '{"text":"Launch a dark mode feature"}'

# Read the live snapshot for a specific company
curl 'localhost:8000/api/state?company=default' | jq '.metrics'

# Stream live events (Ctrl-C to stop)
curl -N localhost:8000/api/stream

# Create a second company and direct it
CID=$(curl -s -X POST localhost:8000/api/companies \
  -H 'Content-Type: application/json' -d '{"name":"Beta Inc"}' | jq -r .company.id)
curl -X POST "localhost:8000/api/directive?company=$CID" \
  -H 'Content-Type: application/json' -d '{"text":"Run a marketing campaign"}'

# With auth enabled (COMPANY_API_TOKEN=secret)
curl -H 'Authorization: Bearer secret' localhost:8000/api/state
```

---

## Multi-tenancy

One deployment hosts any number of **fully isolated** companies:

- Each company is a complete `Company` with its **own SQLite database**, agents,
  background worker, event bus, world, and CRM — they share nothing.
- A small `companies.json` registry persists the set across restarts; there is
  always a `default` company (it reuses `COMPANY_DB`), so single-company use needs
  nothing extra.
- The manager (`company/manager.py`) enforces `MAX_COMPANIES` and validates company
  ids (so a tampered registry can't turn an id into a path-traversal).

The dashboard header has a company switcher and a "+ Company" button; the selected
company is threaded through every request and the event stream.

---

## Security

The codebase has been through a full security review (see git history). Current posture:

**Protected**
- **Auth gates the whole API** when a token is configured — reads included, so one
  tenant's data can't be read by an unauthenticated client. Constant-time token
  comparison; token accepted via header or `?token=` (for SSE).
- **Rate limiting** on state-changing requests (per client IP, `429` + `Retry-After`).
- **Tenant isolation** — separate databases per company; company id validated.
- **Parameterized SQL everywhere** — no string-interpolated values; dynamic
  `UPDATE` column names are guarded against non-identifiers.
- **Dashboard output is HTML-escaped** — all free-text fields go through an escaper;
  artifact bodies render via `textContent`.
- **Code "validation" never executes code** — Development/QA run `py_compile`
  (compile-only) in a list-form subprocess with a timeout; filenames are slugified.
- **Secrets from env, never logged**; `.env`, `*.db`, and `companies.json` are gitignored.
- **Log/event sanitization** — control characters stripped to prevent log forging.
- **Bounded resources** — company cap, SSE queue cap, retention caps on the
  `events`/`kpi_snapshots` tables, bounded cascade depth and rework.

**Residual / by-design risks**
- The `usage` cost ledger is intentionally **not** trimmed (so cost totals stay exact);
  it grows slowly over time.
- No per-user authorization — the token is all-or-nothing. Suitable for a single
  operator; add real authz before exposing to untrusted multi-user traffic.
- The default Docker image binds `0.0.0.0` — set `COMPANY_API_TOKEN` before exposing it.

---

## Project layout

```
company/
  __init__.py        package exports (Company)
  config.py          settings + .env loader + model pricing table
  models.py          domain types: Department, Task, Artifact, Directive, Event,
                     Customer, Deal, Ticket, StandingOrder, AgentConfig
  db.py              SQLite persistence (atomic task claiming, snapshots, CRM,
                     KPI series, cost ledger, retention trimming, column guard)
  llm.py             Claude wrapper (adaptive thinking, structured outputs, fallback)
  tools.py           ToolBox: company memory (recall), live metrics, code validation
  bus.py             thread-safe pub/sub bridging the worker thread to SSE subscribers
  world.py           autopilot: generates inbound tickets/leads/ideas on a timer
  agentconfig.py     ConfigRegistry: human-tunable per-department config (persisted)
  ratelimit.py       in-process sliding-window rate limiter
  manager.py         CompanyManager: one isolated Company (own DB) per tenant
  orchestrator.py    the engine: delegation, work loop, rework, approvals, cost,
                     KPIs, CRM, standing orders, drill-down, background worker
  agents/
    base.py          shared agent contract (summary + artifact + hand-offs + verdict)
    ceo.py           decomposes a human directive into delegated tasks
    departments.py   the seven department agents (Claude-guided + simulation)
  api.py             FastAPI app: dashboard host, JSON API, auth + rate-limit middleware, SSE
web/
  index.html         single-page dashboard (no build step)
  app.js             dashboard logic (SSE, charts, drill-down, company switcher)
  styles.css         dashboard styling
run.py               entrypoint: `serve` (dashboard/API) and `demo` (CLI)
tests/               pytest suite — 16 files, 77 tests, fully offline
Dockerfile           container image
docker-compose.yml   one-command run with a persistent volume
pyproject.toml       project metadata, ruff + pytest config
.github/workflows/   CI: ruff lint + pytest + docker build on every push
requirements.txt     runtime dependencies (anthropic, fastapi, uvicorn, pydantic)
.env.example         documented configuration template
```

~2,900 lines of Python (backend) + ~1,100 lines of dashboard (HTML/CSS/JS).

---

## Development & testing

```bash
pip install -e ".[dev]"     # installs ruff + pytest + httpx
ruff check .                # lint (clean)
pytest                      # 77 tests, fully offline
```

The test suite runs entirely offline (forced simulation mode, isolated temp DB per
test) and covers:

- CEO routing & the cross-department cascade (and its termination)
- deliverable production and the snapshot shape
- the LLM fallback (no key ⇒ unavailable ⇒ simulate)
- the QA **rework loop** (reject → fix → re-verify, bounded & terminating)
- the **tools** (memory recall, live metrics, code validation accept/reject)
- the **world autopilot** (inbound generation, end-to-end handling)
- **standing orders** (due-logic, reschedule, disable, CRUD)
- the **CRM/pipeline** (customers, deals, tickets; revenue consistency)
- **drill-down** detail (directive task trees, customer records)
- **multi-company** isolation & registry persistence
- the cross-thread **event bus** that powers the live stream
- **human-in-the-loop** controls (approval gating, agent-config persistence, cost, budget alerts)
- the **KPI** time series
- **security hardening** (token-gated reads, rate limiting, company cap, log sanitization, SQL column guard, table retention)

CI (`.github/workflows/ci.yml`) runs ruff + the full suite and builds the Docker
image on every push and PR.

---

## Extending the company

**Add a new department agent:**

1. Add the value to `Department` in `company/models.py`.
2. Create an agent subclass in `company/agents/departments.py` with a
   `role_description` (its Claude persona) and a `simulate(self, task, context)`
   method returning the standard `{summary, verdict, artifact, followups}` dict.
3. Register it in `AGENT_CLASSES`.
4. Optionally teach the CEO (`company/agents/ceo.py`) to route relevant directives to it.

**Add a real tool** an agent can call: add a method to `ToolBox` in
`company/tools.py` (it already has the database and a workspace dir) and use it from
an agent's `work`/`simulate` path. Keep tools side-effect-safe and offline-capable.

**Change models/effort:** globally via `COMPANY_MODEL` / `COMPANY_EFFORT`, or
per-department live from the dashboard (persisted via `ConfigRegistry`).

Because every agent honors the same return contract, new departments and tools plug
into the cascade automatically.

---

## Design principles

- **Emergent behavior from one rule.** The uniform agent contract (summary +
  deliverable + hand-offs) is what turns a one-line instruction into coordinated,
  multi-department work — there's no global workflow script.
- **Always runnable.** The Claude layer degrades to deterministic simulation, so the
  company never hard-depends on network or credentials. Tests and demos run offline.
- **One human seat.** The only required human input is a directive; everything
  downstream is autonomous, with optional checkpoints (approvals) when you want them.
- **Grounded, not just generative.** Agents recall prior work, compute real metrics,
  validate real code, and produce real CRM records — so the numbers mean something.
- **Bounded by construction.** Depth limits, rework budgets, retention caps, company
  caps, and rate limits ensure the system terminates and stays within resources.

---

## Troubleshooting / FAQ

**It says "simulation mode" — is that broken?**
No. Without `ANTHROPIC_API_KEY` the company runs the deterministic simulation. Set the
key (and unset `COMPANY_SIMULATE`) to switch to real Claude.

**Nothing happens after I submit a directive.**
Check the activity feed / `GET /api/state`. If a department is **disabled** (agent
config) or **approvals** are on, work may be parked. Disabled-department tasks stay
`pending`; risky tasks sit in `awaiting_approval` until you approve them.

**The dashboard stopped updating.**
The dashboard uses SSE with a 5-second fallback poll; it reconnects automatically.
If you enabled `COMPANY_API_TOKEN`, the dashboard will prompt for it on the first
blocked request and store it in `localStorage`.

**`429 Rate limit exceeded`.**
You exceeded `COMPANY_RATE_LIMIT` state-changing requests in the window. Wait for the
`Retry-After` period, or raise/disable the limit.

**Where is the data?**
SQLite files next to `COMPANY_DB` (default `company.db`; other tenants
`company_<id>.db`), the company registry in `companies.json`, and validated code in
`workspace/`. All are gitignored. Delete them to reset.

**Can I run several companies?**
Yes — create them from the dashboard header or `POST /api/companies`; each is fully
isolated. See [Multi-tenancy](#multi-tenancy).

---

## Roadmap & status

**Implemented:** CEO delegation · 7 department agents · emergent cascade · company
memory · real tools · QA rework loop · autopilot world · standing orders · real-time
SSE dashboard · approval gates · agent configuration · cost & budget tracking ·
CRM/pipeline · KPI charts · drill-down views · multi-tenancy · optional auth · rate
limiting · Docker · CI · 77 tests.

**Possible future work:** real Claude tool-execution sandboxes for Development,
external integrations (Slack/GitHub/email), per-user authorization & audit logs, and
a billing/usage-export layer.

---

*Built as a demonstration of agent orchestration with Claude. Powered by
`claude-opus-4-8` with a deterministic offline simulation fallback.*
