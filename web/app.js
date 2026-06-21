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
  const path = autopilot ? "/api/world/stop" : "/api/world/start";
  await fetch(path, { method: "POST" });
  fetchState();
}

async function submitDirective(text) {
  await fetch("/api/directive", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  fetchState();
}

function render(state) {
  renderMode(state);
  renderToggles(state);
  renderMetrics(state);
  renderApprovals(state.approvals || []);
  renderDepartments(state);
  renderFeed(state.events);
  renderArtifacts(state.artifacts);
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
  await fetch(`/api/tasks/${taskId}/${action}`, { method: "POST" });
  fetchState();
}

async function toggleApprovals() {
  await fetch(approvalsEnabled ? "/api/approvals/stop" : "/api/approvals/start", { method: "POST" });
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
  await fetch(`/api/agents/${dept}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
