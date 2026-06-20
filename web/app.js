"use strict";

const EXAMPLES = [
  "Launch a dark mode feature",
  "A customer reports the export button is broken",
  "Run a marketing campaign for our new pricing",
  "Analyze last quarter's user retention",
  "Increase sales pipeline for enterprise accounts",
];

let artifactsById = {};

async function fetchState() {
  try {
    const res = await fetch("/api/state");
    if (!res.ok) return;
    render(await res.json());
  } catch (e) {
    /* transient; next poll will retry */
  }
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
  renderMetrics(state.metrics);
  renderDepartments(state.departments);
  renderFeed(state.events);
  renderArtifacts(state.artifacts);
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

function renderMetrics(m) {
  const cards = [
    { label: "Tasks", num: m.total_tasks },
    { label: "In progress", num: m.in_progress },
    { label: "Done", num: m.done },
    { label: "Rework", num: m.rework ?? 0 },
    { label: "Deliverables", num: m.artifacts },
  ];
  document.getElementById("metrics").innerHTML = cards
    .map((c) => `<div class="metric"><div class="num">${c.num}</div><div class="label">${c.label}</div></div>`)
    .join("");
}

function renderDepartments(depts) {
  document.getElementById("dept-grid").innerHTML = depts
    .map((d) => {
      const active = d.in_progress > 0;
      return `<div class="dept-card ${active ? "active" : ""}">
        <h3><span class="dot"></span>${escapeHtml(d.title)}</h3>
        <div class="dept-stats">
          <span>pending <b>${d.pending}</b></span>
          <span>active <b>${d.in_progress}</b></span>
          <span>done <b>${d.done}</b></span>
        </div>
      </div>`;
    })
    .join("");
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

  document.getElementById("modal-close").addEventListener("click", () => {
    document.getElementById("artifact-modal").hidden = true;
  });
  document.getElementById("artifact-modal").addEventListener("click", (e) => {
    if (e.target.id === "artifact-modal") e.target.hidden = true;
  });

  fetchState();
  setInterval(fetchState, 1500);
}

document.addEventListener("DOMContentLoaded", init);
