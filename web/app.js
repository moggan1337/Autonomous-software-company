"use strict";

const EXAMPLES = [
  "Launch a dark mode feature",
  "A customer reports the export button is broken",
  "Run a marketing campaign for our new pricing",
  "Analyze last quarter's user retention",
  "Increase sales pipeline for enterprise accounts",
];

let artifactsById = {};
let agentsById = {};
let autopilot = false;
let approvalsEnabled = false;
let refreshTimer = null;
let tickerTimer = null;

async function fetchState() {
  try {
    const res = await fetch("/api/state");
    if (!res.ok) return;
    render(await res.json());
  } catch (e) {
    /* transient; the fallback poll or next event will retry */
  }
}

// Coalesce bursts of stream events into one state refresh.
function scheduleRefresh() {
  if (refreshTimer) return;
  refreshTimer = setTimeout(() => {
    refreshTimer = null;
    fetchState();
  }, 250);
}

function connectStream() {
  const es = new EventSource("/api/stream");
  es.onmessage = (msg) => {
    let item;
    try {
      item = JSON.parse(msg.data);
    } catch {
      return;
    }
    if (item.type === "thinking") {
      showTicker(`${item.data.department}: ${item.data.message}`);
    } else if (item.type === "event") {
      scheduleRefresh();
    }
  };
  es.onerror = () => {
    /* EventSource auto-reconnects; the fallback poll covers any gap. */
  };
}

function showTicker(text) {
  const el = document.getElementById("ticker");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(tickerTimer);
  tickerTimer = setTimeout(() => el.classList.remove("show"), 2500);
}

async function toggleAutopilot() {
  await mutate(autopilot ? "/api/world/stop" : "/api/world/start");
  fetchState();
}

async function submitDirective(text) {
  await mutate("/api/directive", "POST", { text });
  fetchState();
}

// Auth-aware mutation helper: attaches a stored token, prompts once on 401.
async function mutate(path, method = "POST", body = null) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  const token = localStorage.getItem("asc_token");
  if (token) headers["Authorization"] = "Bearer " + token;
  const res = await fetch(path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    const t = prompt("This action requires an API token:");
    if (t) {
      localStorage.setItem("asc_token", t);
      return mutate(path, method, body);
    }
  }
  return res;
}

function render(state) {
  renderMode(state);
  renderToggles(state);
  renderMetrics(state);
  renderKpis(state);
  renderCrm(state.crm);
  renderApprovals(state.approvals || []);
  renderSchedules(state.schedules || []);
  renderDepartments(state);
  renderFeed(state.events);
  renderArtifacts(state.artifacts);
}

function renderCrm(crm) {
  if (!crm) return;
  const s = crm.summary || {};
  const cards = [
    { label: "Active customers", num: s.customers_active ?? 0 },
    { label: "Revenue", num: `$${Math.round(s.revenue || 0).toLocaleString()}` },
    { label: "Win rate", num: `${Math.round((s.win_rate || 0) * 100)}%` },
    { label: "Tickets resolved", num: s.tickets_resolved ?? 0 },
  ];
  document.getElementById("crm-cards").innerHTML = cards
    .map((c) => `<div class="crm-card"><div class="c-num">${c.num}</div><div class="c-label">${c.label}</div></div>`)
    .join("");

  const deals = crm.deals || [];
  document.getElementById("crm-deals").innerHTML = deals.length
    ? deals
        .map(
          (d) => `<li><span>${escapeHtml(d.name)}</span>
            <span><b>$${Math.round(d.value).toLocaleString()}</b>
            <span class="pill ${d.stage}">${d.stage}</span></span></li>`
        )
        .join("")
    : `<li class="crm-empty">Deals appear as Sales closes work.</li>`;

  const tickets = crm.tickets || [];
  document.getElementById("crm-tickets").innerHTML = tickets.length
    ? tickets
        .map(
          (t) => `<li><span>${escapeHtml(t.subject)}</span>
            <span class="pill ${t.status}">${t.status}</span></li>`
        )
        .join("")
    : `<li class="crm-empty">Tickets appear as Support resolves issues.</li>`;
}

function renderSchedules(orders) {
  const list = document.getElementById("schedule-list");
  if (!orders.length) {
    list.innerHTML = `<li class="sched-empty">No standing orders yet. Add one above to run a directive on a repeating schedule.</li>`;
    return;
  }
  const now = Date.now() / 1000;
  list.innerHTML = orders
    .map((o) => {
      const inN = Math.max(0, Math.round(o.next_run - now));
      const when = o.enabled ? `next in ${inN}s` : "paused";
      return `<li class="${o.enabled ? "" : "paused"}">
        <div>
          <div>${escapeHtml(o.text)}</div>
          <div class="sched-meta">every ${Math.round(o.interval_seconds)}s · ${o.runs} run(s) · ${when}</div>
        </div>
        <div class="sched-actions">
          <button data-toggle="${o.id}">${o.enabled ? "Pause" : "Resume"}</button>
          <button data-delete="${o.id}">Delete</button>
        </div>
      </li>`;
    })
    .join("");
  list.querySelectorAll("[data-toggle]").forEach((b) =>
    b.addEventListener("click", async () => {
      await mutate(`/api/schedules/${b.dataset.toggle}/toggle`);
      fetchState();
    })
  );
  list.querySelectorAll("[data-delete]").forEach((b) =>
    b.addEventListener("click", async () => {
      await mutate(`/api/schedules/${b.dataset.delete}`, "DELETE");
      fetchState();
    })
  );
}

function renderKpis(state) {
  const k = state.kpi_latest || {};
  const cards = [
    { label: "Revenue", num: `$${Math.round(k.revenue || 0).toLocaleString()}` },
    { label: "Customers", num: k.customers || 0 },
    { label: "Tickets resolved", num: k.tickets_resolved || 0 },
    { label: "Deliverables", num: k.deliverables || 0 },
  ];
  document.getElementById("kpi-cards").innerHTML = cards
    .map((c) => `<div class="kpi"><div class="k-num">${c.num}</div><div class="k-label">${c.label}</div></div>`)
    .join("");
  drawChart(state.kpis || []);
}

function drawChart(series) {
  const host = document.getElementById("kpi-chart");
  const legend = document.getElementById("chart-legend");
  if (series.length < 2) {
    host.innerHTML = `<div class="chart-empty">Charts appear as the company completes work over time.</div>`;
    legend.innerHTML = "";
    return;
  }
  const lines = [
    { key: "revenue", color: "#3fb950", label: "Revenue" },
    { key: "deliverables", color: "#4f9cf9", label: "Deliverables" },
    { key: "cost", color: "#d29922", label: "Est. cost" },
  ];
  legend.innerHTML = lines
    .map((l) => `<span><i style="background:${l.color}"></i>${l.label}</span>`)
    .join("");

  const W = 800, H = 180, pad = 8;
  const n = series.length;
  const xAt = (i) => pad + (i * (W - 2 * pad)) / (n - 1);
  const paths = lines
    .map((l) => {
      const max = Math.max(1, ...series.map((s) => s[l.key] || 0));
      const yAt = (v) => H - pad - ((v || 0) / max) * (H - 2 * pad);
      const d = series
        .map((s, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(s[l.key]).toFixed(1)}`)
        .join(" ");
      return `<path d="${d}" fill="none" stroke="${l.color}" stroke-width="2" />`;
    })
    .join("");
  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${paths}</svg>`;
}

function renderToggles(state) {
  autopilot = !!state.autopilot;
  approvalsEnabled = !!state.approvals_enabled;
  const a = document.getElementById("autopilot-btn");
  a.textContent = `Autopilot: ${autopilot ? "on" : "off"}`;
  a.classList.toggle("on", autopilot);
  const p = document.getElementById("approvals-btn");
  p.textContent = `Approvals: ${approvalsEnabled ? "on" : "off"}`;
  p.classList.toggle("on", approvalsEnabled);
}

function renderMode(state) {
  const badge = document.getElementById("mode-badge");
  if (state.mode === "claude") {
    badge.textContent = `live · ${state.model}`;
    badge.className = "mode claude";
  } else {
    badge.textContent = `simulation · ${state.model}`;
    badge.className = "mode simulation";
  }
}

function renderMetrics(state) {
  const m = state.metrics;
  const overBudget = state.budget && m.cost > state.budget;
  const cards = [
    { label: "Tasks", num: m.total_tasks },
    { label: "In progress", num: m.in_progress },
    { label: "Done", num: m.done },
    { label: "Awaiting", num: m.awaiting_approval ?? 0 },
    { label: "Rework", num: m.rework ?? 0 },
    {
      label: `Est. cost / $${(state.budget ?? 0).toFixed(0)}`,
      num: `$${(m.cost ?? 0).toFixed(2)}`,
      over: overBudget,
    },
  ];
  document.getElementById("metrics").innerHTML = cards
    .map(
      (c) =>
        `<div class="metric ${c.over ? "over" : ""}"><div class="num">${c.num}</div><div class="label">${c.label}</div></div>`
    )
    .join("");
}

function renderApprovals(approvals) {
  const section = document.getElementById("approvals-section");
  const list = document.getElementById("approvals-list");
  if (!approvals.length) {
    section.hidden = true;
    list.innerHTML = "";
    return;
  }
  section.hidden = false;
  list.innerHTML = approvals
    .map(
      (t) => `<li>
        <div>
          <div>${escapeHtml(t.title)}</div>
          <div class="ap-meta">${escapeHtml(t.department)} · ${escapeHtml(t.priority)}</div>
        </div>
        <div class="ap-actions">
          <button class="btn-approve" data-approve="${t.id}">Approve</button>
          <button class="btn-reject" data-reject="${t.id}">Reject</button>
        </div>
      </li>`
    )
    .join("");
  list.querySelectorAll("[data-approve]").forEach((b) =>
    b.addEventListener("click", () => decide(b.dataset.approve, "approve"))
  );
  list.querySelectorAll("[data-reject]").forEach((b) =>
    b.addEventListener("click", () => decide(b.dataset.reject, "reject"))
  );
}

async function decide(taskId, action) {
  await mutate(`/api/tasks/${taskId}/${action}`);
  fetchState();
}

async function toggleApprovals() {
  await mutate(approvalsEnabled ? "/api/approvals/stop" : "/api/approvals/start");
  fetchState();
}

function renderDepartments(state) {
  agentsById = {};
  (state.agents || []).forEach((a) => (agentsById[a.department] = a));
  const grid = document.getElementById("dept-grid");
  grid.innerHTML = state.departments
    .map((d) => {
      const active = d.in_progress > 0 && d.enabled;
      const off = d.enabled === false;
      return `<div class="dept-card ${active ? "active" : ""} ${off ? "disabled" : ""}" data-dept="${d.id}">
        <h3><span class="dot"></span>${escapeHtml(d.title)}${off ? '<span class="badge-off">off</span>' : ""}</h3>
        <div class="dept-stats">
          <span>pending <b>${d.pending}</b></span>
          <span>active <b>${d.in_progress}</b></span>
          <span>wait <b>${d.awaiting_approval ?? 0}</b></span>
          <span>done <b>${d.done}</b></span>
        </div>
      </div>`;
    })
    .join("");
  grid.querySelectorAll("[data-dept]").forEach((card) =>
    card.addEventListener("click", () => openConfig(card.dataset.dept))
  );
}

function openConfig(deptId) {
  const a = agentsById[deptId];
  if (!a) return;
  document.getElementById("config-modal").dataset.dept = deptId;
  document.getElementById("config-title").textContent = `Configure: ${a.title}`;
  document.getElementById("cfg-enabled").checked = a.enabled !== false;
  document.getElementById("cfg-effort").value = a.effort || "";
  document.getElementById("cfg-model").value = a.model || "";
  document.getElementById("cfg-instructions").value = a.instructions || "";
  document.getElementById("config-modal").hidden = false;
}

async function saveConfig() {
  const modal = document.getElementById("config-modal");
  const dept = modal.dataset.dept;
  const body = {
    enabled: document.getElementById("cfg-enabled").checked,
    effort: document.getElementById("cfg-effort").value || null,
    model: document.getElementById("cfg-model").value.trim() || null,
    instructions: document.getElementById("cfg-instructions").value,
  };
  await mutate(`/api/agents/${dept}`, "PUT", body);
  modal.hidden = true;
  fetchState();
}

function renderFeed(events) {
  const feed = document.getElementById("feed");
  if (!events.length) {
    feed.innerHTML = `<li class="empty">No activity yet. Give the company a direction above.</li>`;
    return;
  }
  feed.innerHTML = events
    .map(
      (e) => `<li>
        <span class="tag ${e.kind}">${e.kind}</span>
        <span class="msg">${escapeHtml(e.message)}<div class="who">${escapeHtml(e.department)}</div></span>
      </li>`
    )
    .join("");
}

function renderArtifacts(artifacts) {
  artifactsById = {};
  const el = document.getElementById("artifacts");
  if (!artifacts.length) {
    el.innerHTML = `<li class="empty">Deliverables appear here as departments finish work.</li>`;
    return;
  }
  el.innerHTML = artifacts
    .map((a) => {
      artifactsById[a.id] = a;
      return `<li data-id="${a.id}">
        <div class="a-title">${escapeHtml(a.title)}</div>
        <div class="a-meta">${escapeHtml(a.department)} · ${escapeHtml(a.kind)}</div>
      </li>`;
    })
    .join("");
  el.querySelectorAll("li[data-id]").forEach((li) =>
    li.addEventListener("click", () => openArtifact(li.dataset.id))
  );
}

function openArtifact(id) {
  const a = artifactsById[id];
  if (!a) return;
  document.getElementById("modal-title").textContent = a.title;
  document.getElementById("modal-content").textContent = a.content;
  document.getElementById("artifact-modal").hidden = false;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function init() {
  const ex = document.getElementById("examples");
  ex.innerHTML = EXAMPLES.map((e) => `<span class="example">${escapeHtml(e)}</span>`).join("");
  ex.querySelectorAll(".example").forEach((s) =>
    s.addEventListener("click", () => {
      document.getElementById("directive-input").value = s.textContent;
    })
  );

  document.getElementById("directive-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = document.getElementById("directive-input");
    const text = input.value.trim();
    if (!text) return;
    submitDirective(text);
    input.value = "";
  });

  document.getElementById("autopilot-btn").addEventListener("click", toggleAutopilot);
  document.getElementById("approvals-btn").addEventListener("click", toggleApprovals);

  document.getElementById("schedule-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = document.getElementById("sched-text").value.trim();
    const interval = parseInt(document.getElementById("sched-interval").value, 10);
    if (!text || !(interval >= 2)) return;
    await mutate("/api/schedules", "POST", { text, interval_seconds: interval });
    document.getElementById("sched-text").value = "";
    fetchState();
  });

  document.getElementById("modal-close").addEventListener("click", () => {
    document.getElementById("artifact-modal").hidden = true;
  });
  document.getElementById("artifact-modal").addEventListener("click", (e) => {
    if (e.target.id === "artifact-modal") e.target.hidden = true;
  });

  document.getElementById("config-close").addEventListener("click", () => {
    document.getElementById("config-modal").hidden = true;
  });
  document.getElementById("config-modal").addEventListener("click", (e) => {
    if (e.target.id === "config-modal") e.target.hidden = true;
  });
  document.getElementById("cfg-save").addEventListener("click", saveConfig);

  fetchState();
  connectStream();             // live push of activity + agent reasoning
  setInterval(fetchState, 5000); // slow fallback in case the stream drops
}

document.addEventListener("DOMContentLoaded", init);
