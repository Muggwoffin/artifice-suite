/*
 * Main-tab client. Talks to the FastAPI backend in server.py: queue mutation
 * over plain POSTs, live progress over one persistent EventSource (SSE).
 *
 * File paths: a browser <input type=file> or drag-and-drop never exposes a
 * real filesystem path (that's a deliberate browser security boundary), which
 * is exactly the problem noted when this port was proposed. Inside the
 * pywebview shell, `window.pywebview.api.browse_files()` opens a native
 * dialog and returns real paths. Without pywebview (a plain browser tab, for
 * quick iteration) this falls back to `prompt()` for a typed path — crude,
 * but honest about what a browser can and cannot do on its own.
 */

const STATE_GLYPH = {
  pending: "·", running: "▸", done: "✓",
  skipped: "–", failed: "✕", cancelled: "—",
};

const STAGE_KEYS = ["ocr", "cleanup", "translate"];

const els = {};
["queue-body", "queue-count", "dropzone", "log", "output-dir",
 "btn-browse-files", "btn-add-folder", "btn-remove",
 "btn-clear", "btn-skip", "btn-browse-output",
 "btn-run", "btn-pause", "btn-stop", "progress-bar", "status-text",
 "stage-text", "stage-ocr", "stage-cleanup", "stage-translate", "stage-force",
].forEach(id => {
  els[id] = document.getElementById(id);
});

let items = new Map();   // id -> item dict, insertion order preserved
let selected = new Set();
let running = false;

const isNative = () => !!window.pywebview;

// Tabs register a callback here (`TAB_ACTIVATE.history = fn`) to load or
// refresh their content only when the user actually switches to them.
const TAB_ACTIVATE = {};

// --------------------------------------------------------------- fetch helpers

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || res.statusText);
  }
  return res.json();
}

// -------------------------------------------------------------------- queue

function setQueue(list) {
  items = new Map(list.map(it => [it.id, it]));
  selected = new Set([...selected].filter(id => items.has(id)));
  renderAll();
}

function renderAll() {
  els["queue-body"].innerHTML = "";
  for (const item of items.values()) els["queue-body"].appendChild(rowFor(item));
  updateCount();
}

function updateCount() {
  const n = items.size;
  const done = [...items.values()].filter(i => i.state === "done").length;
  const failed = [...items.values()].filter(i => i.state === "failed").length;
  let text = `${n} file${n === 1 ? "" : "s"}`;
  if (done || failed) {
    text += `  ·  ${done} done`;
    if (failed) text += `  ·  ${failed} failed`;
  }
  els["queue-count"].textContent = text;
}

function stageCell(item, key) {
  const s = item.stages[key];
  const glyph = STATE_GLYPH[s.state] || "·";
  const text = (s.state === "done" && s.chars) ? `${glyph} ${s.chars}` : glyph;
  return `<td class="c stage-${s.state}">${text}</td>`;
}

function statusText(item) {
  if (item.state === "failed") {
    const head = (item.error || "").split(":")[0];
    return head ? `failed (${head})` : "failed";
  }
  const running = STAGE_KEYS.find(k => item.stages[k].state === "running");
  if (running) return `${running[0].toUpperCase()}${running.slice(1)}…`;
  return item.state;
}

function rowFor(item) {
  const tr = document.createElement("tr");
  tr.dataset.id = item.id;
  tr.className = `state-${item.state}` + (selected.has(item.id) ? " selected" : "");
  tr.title = item.path;

  const checked = selected.has(item.id) ? "checked" : "";
  const canPreview = item.state !== "pending";
  tr.innerHTML = `
    <td><input type="checkbox" class="row-select" ${checked}></td>
    <td>${escapeHtml(item.name)}</td>
    ${stageCell(item, "ocr")}
    ${stageCell(item, "cleanup")}
    ${stageCell(item, "translate")}
    <td class="c">${item.confidence ?? "—"}</td>
    <td class="c">${item.elapsed ? item.elapsed.toFixed(1) + "s" : "—"}</td>
    <td><span class="status-pill ${item.state}">${escapeHtml(statusText(item))}</span></td>
    <td class="c">${canPreview ? `<button class="btn row-view" title="Open in Preview">&rarr;</button>` : ""}</td>
  `;
  tr.querySelector(".row-select").addEventListener("change", (e) => {
    if (e.target.checked) selected.add(item.id); else selected.delete(item.id);
    tr.classList.toggle("selected", e.target.checked);
  });
  const viewBtn = tr.querySelector(".row-view");
  if (viewBtn) {
    viewBtn.addEventListener("click", () => {
      if (window.PreviewTab) window.PreviewTab.open(item.id);
    });
  }
  return tr;
}

function updateRow(item) {
  items.set(item.id, item);
  const tr = els["queue-body"].querySelector(`tr[data-id="${item.id}"]`);
  if (tr) tr.replaceWith(rowFor(item));
  else els["queue-body"].appendChild(rowFor(item));
  updateCount();
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

async function refreshQueue() {
  const data = await api("GET", "/api/queue");
  setQueue(data.items);
  applyRunStatus(data.status);
}

// -------------------------------------------------------------- adding files

async function pickFiles() {
  if (isNative()) return (await window.pywebview.api.browse_files()) || [];
  const raw = prompt("Enter an absolute file path (browser mode has no native file dialog):");
  return raw ? [raw] : [];
}

async function pickFolder(kind) {
  if (isNative()) {
    const method = kind === "output" ? "browse_output_dir"
                 : kind === "tropy" ? "browse_tropy_project" : "browse_folder";
    return await window.pywebview.api[method]();
  }
  return prompt("Enter an absolute folder path (browser mode has no native picker):");
}

async function addPaths(paths) {
  if (!paths || !paths.length) return;
  const data = await api("POST", "/api/queue/add-paths", { paths });
  setQueue(data.items);
  log(`Added ${data.added} file(s)`, "accent");
}

els["btn-browse-files"].onclick = async () => addPaths(await pickFiles());
els["btn-add-folder"].onclick = async () => {
  const folder = await pickFolder("folder");
  if (folder) addPaths([folder]);
};

els["dropzone"].addEventListener("click", () => els["btn-browse-files"].click());
["dragenter", "dragover"].forEach(evt =>
  els["dropzone"].addEventListener(evt, e => { e.preventDefault(); els["dropzone"].classList.add("drag"); }));
["dragleave", "drop"].forEach(evt =>
  els["dropzone"].addEventListener(evt, e => { e.preventDefault(); els["dropzone"].classList.remove("drag"); }));
els["dropzone"].addEventListener("drop", () => {
  // A browser drop event carries File objects, never a filesystem path, so
  // there is nothing usable to send here outside the native shell.
  if (!isNative()) {
    log("Drag-and-drop needs the native window (browsers don't expose real file paths) — use Browse Files instead.", "warning");
  }
});

els["btn-remove"].onclick = async () => {
  if (!selected.size) return;
  const data = await api("POST", "/api/queue/remove", { ids: [...selected] });
  setQueue(data.items);
};
els["btn-clear"].onclick = async () => {
  const data = await api("POST", "/api/queue/clear");
  setQueue(data.items);
};
els["btn-skip"].onclick = async () => {
  for (const id of selected) await api("POST", "/api/run/skip", { id });
  log(`Skip requested for ${selected.size} item(s)`, "warning");
};

// ------------------------------------------------------------------- running

function setRunning(isRunning) {
  running = isRunning;
  els["btn-run"].disabled = isRunning;
  els["btn-pause"].disabled = !isRunning;
  els["btn-stop"].disabled = !isRunning;
  if (!isRunning) els["btn-pause"].textContent = "⏸ Pause";
}

function applyRunStatus(status) {
  setRunning(!!status.running);
  if (status.paused) els["btn-pause"].textContent = "▶ Resume";
}

els["btn-run"].onclick = async () => {
  const stages = [];
  if (els["stage-ocr"].checked) stages.push("ocr");
  if (els["stage-cleanup"].checked) stages.push("cleanup");
  if (els["stage-translate"].checked) stages.push("translate");
  if (!items.size) { log("Add at least one document first.", "warning"); return; }
  if (!stages.length) { log("Enable at least one pipeline stage.", "warning"); return; }

  try {
    await api("POST", "/api/run/start", {
      stages, output_dir: els["output-dir"].value || "output",
      force: els["stage-force"].checked,
    });
    setRunning(true);
    els["progress-bar"].style.width = "0%";
  } catch (err) {
    log(`Could not start: ${err.message}`, "error");
  }
};

els["btn-pause"].onclick = async () => {
  const paused = els["btn-pause"].textContent.includes("Resume");
  await api("POST", paused ? "/api/run/resume" : "/api/run/pause");
  els["btn-pause"].textContent = paused ? "⏸ Pause" : "▶ Resume";
};
els["btn-stop"].onclick = async () => {
  await api("POST", "/api/run/cancel");
  els["status-text"].textContent = "Stopping — waiting for in-flight requests…";
};

// ---------------------------------------------------------------------- log

function log(message, tag) {
  const line = document.createElement("div");
  line.className = `line ${tag || ""}`;
  line.textContent = message;
  els["log"].appendChild(line);
  els["log"].scrollTop = els["log"].scrollHeight;
}

// ---------------------------------------------------------------------- SSE

function updateProgress() {
  const total = items.size;
  const finished = [...items.values()]
    .filter(i => ["done", "failed", "skipped", "cancelled"].includes(i.state)).length;
  els["progress-bar"].style.width = total ? `${(finished / total) * 100}%` : "0%";
  if (running) els["status-text"].textContent = `Running — ${finished}/${total}`;
}

function connectEvents() {
  const es = new EventSource("/api/events");
  es.onmessage = (e) => {
    const evt = JSON.parse(e.data);
    if (evt.message) log(evt.message, evt.tag);
    if (evt.item) updateRow(evt.item);

    switch (evt.kind) {
      case "run_started":
        setRunning(true);
        els["stage-text"].textContent = "";
        break;
      case "stage_started":
        els["stage-text"].textContent = evt.item ? `${evt.stage} · ${evt.item.name}` : "";
        updateProgress();
        break;
      case "item_finished":
        updateProgress();
        // Mirrors the desktop build: if Preview is the open tab, follow
        // whichever item just finished rather than making the user click it.
        if (window.PreviewTab && document.getElementById("panel-preview").classList.contains("active")) {
          window.PreviewTab.open(evt.item.id);
        }
        break;
      case "paused":
        els["status-text"].textContent = "Paused";
        break;
      case "resumed":
        els["status-text"].textContent = "Running";
        break;
      case "run_finished": {
        const p = evt.payload || {};
        setRunning(false);
        els["stage-text"].textContent = "";
        els["status-text"].textContent =
          `Done — ${p.done ?? 0} ok` + (p.failed ? `, ${p.failed} failed` : "");
        refreshQueue();
        break;
      }
    }
  };
  es.onerror = () => { /* EventSource retries on its own */ };
}

// -------------------------------------------------------------------- tabs

document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`panel-${tab.dataset.tab}`).classList.add("active");
    TAB_ACTIVATE[tab.dataset.tab]?.();
  });
});

// ------------------------------------------------------- shared: comparison

/*
 * Renders the Raw / Cleaned / Translated three-pane comparison, used by both
 * the Preview tab (live queue items) and the History tab (past runs). Both
 * send the same shape of `data` — see `serialize_item_preview` and
 * `serialize_history_item_detail` in runtime.py, which is precisely the
 * point: one renderer, two sources, no drift between them.
 *
 * Diff/marker ranges arrive as (start, end, tag) triples computed in Python
 * (`_diff.py`) rather than recomputed here, so the highlight logic can never
 * quietly diverge from the desktop build's.
 */
function renderCompare(container, data) {
  const confBits = [];
  if (data.language) confBits.push(`source: ${escapeHtml(data.language)}`);
  if (data.confidence != null) confBits.push(`confidence ${data.confidence}/100`);

  container.querySelector(".compare-title").textContent = data.title || "No document selected";
  const confEl = container.querySelector(".compare-conf");
  confEl.textContent = confBits.join("   ");
  confEl.className = `compare-conf dim conf-${data.confidence_tier || "none"}`;

  const panes = {
    raw: { text: data.raw, ranges: data.diff?.raw_ranges || [] },
    cleaned: { text: data.cleaned, ranges: data.diff?.cleaned_ranges || [] },
    translated: { text: data.translated, ranges: data.diff?.translated_ranges || [] },
  };
  for (const [key, { text, ranges }] of Object.entries(panes)) {
    const el = container.querySelector(`.compare-pane[data-pane="${key}"] .compare-text`);
    const meta = container.querySelector(`.compare-pane[data-pane="${key}"] .compare-meta`);
    if (text) {
      el.innerHTML = highlightRanges(text, ranges);
      meta.textContent = `${text.length.toLocaleString()} chars`;
    } else {
      el.innerHTML = `<span class="empty">(not run)</span>`;
      meta.textContent = "";
    }
  }
}

function clearCompare(container) {
  container.querySelector(".compare-title").textContent = "No document selected";
  container.querySelector(".compare-conf").textContent = "";
  container.querySelectorAll(".compare-text").forEach(el => {
    el.innerHTML = `<span class="empty">(not run)</span>`;
  });
  container.querySelectorAll(".compare-meta").forEach(el => { el.textContent = ""; });
}

// A tag maps 1:1 to a CSS class (delete_/insert_/replace_/marker); markers
// and diff ranges are applied to the same text in independent passes on the
// Python side, so overlaps are already resolved before they reach here.
function highlightRanges(text, ranges) {
  if (!ranges.length) return escapeHtml(text);
  const sorted = [...ranges].sort((a, b) => a[0] - b[0]);
  let out = "";
  let pos = 0;
  for (const [start, end, tag] of sorted) {
    if (start < pos) continue; // ignore any accidental overlap defensively
    out += escapeHtml(text.slice(pos, start));
    out += `<mark class="hl-${tag}">${escapeHtml(text.slice(start, end))}</mark>`;
    pos = end;
  }
  out += escapeHtml(text.slice(pos));
  return out;
}

// ------------------------------------------------------------------- output

els["btn-browse-output"].onclick = async () => {
  const dir = await pickFolder("output");
  if (dir) els["output-dir"].value = dir;
};

// Tropy (both "Add from…" and "Send to…") lives in tropy.js, loaded after
// this file — it reuses api(), escapeHtml(), pickFolder(), setQueue() and log()
// from here, the same way the tk build's TropyPicker/TropySendDialog reuse
// helpers from the app it's attached to.

// -------------------------------------------------------------------- init

(async function init() {
  try {
    const cfg = await api("GET", "/api/config");
    if (cfg.output_dir) els["output-dir"].value = cfg.output_dir;
  } catch { /* config is optional at startup */ }
  await refreshQueue();
  connectEvents();
})();
