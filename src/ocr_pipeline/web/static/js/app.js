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
 "btn-clear", "btn-skip", "btn-retry", "btn-browse-output",
 "btn-run", "btn-pause", "btn-stop", "progress-bar", "status-text",
 "stage-text", "stage-ocr", "stage-cleanup", "stage-translate", "stage-force",
].forEach(id => {
  els[id] = document.getElementById(id);
});

let items = new Map();   // id -> item dict, insertion order preserved
let selected = new Set();
let running = false;
let lastClickedId = null;  // for Shift+click range selection

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
    lastClickedId = item.id;
  });

  // Shift+click range selection
  tr.addEventListener("click", (e) => {
    if (e.target.closest("button") || e.target.tagName === "INPUT") return;
    if (e.shiftKey && lastClickedId) {
      const allIds = [...items.keys()];
      const start = allIds.indexOf(lastClickedId);
      const end = allIds.indexOf(item.id);
      if (start !== -1 && end !== -1) {
        const [lo, hi] = start < end ? [start, end] : [end, start];
        for (let i = lo; i <= hi; i++) {
          selected.add(allIds[i]);
          const row = els["queue-body"].querySelector(`tr[data-id="${allIds[i]}"]`);
          if (row) {
            row.classList.add("selected");
            const cb = row.querySelector(".row-select");
            if (cb) cb.checked = true;
          }
        }
      }
    } else if (e.ctrlKey || e.metaKey) {
      // Ctrl/Cmd+click: toggle individual
      if (selected.has(item.id)) {
        selected.delete(item.id);
        tr.classList.remove("selected");
        const cb = tr.querySelector(".row-select");
        if (cb) cb.checked = false;
      } else {
        selected.add(item.id);
        tr.classList.add("selected");
        const cb = tr.querySelector(".row-select");
        if (cb) cb.checked = true;
      }
    }
    lastClickedId = item.id;
  });

  // Drag-drop reorder
  tr.draggable = true;
  tr.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/plain", item.id);
    tr.classList.add("dragging");
  });
  tr.addEventListener("dragend", () => tr.classList.remove("dragging"));
  tr.addEventListener("dragover", (e) => {
    e.preventDefault();
    const rect = tr.getBoundingClientRect();
    const mid = rect.top + rect.height / 2;
    tr.classList.toggle("drag-over-top", e.clientY < mid);
    tr.classList.toggle("drag-over-bottom", e.clientY >= mid);
  });
  tr.addEventListener("dragleave", () => {
    tr.classList.remove("drag-over-top", "drag-over-bottom");
  });
  tr.addEventListener("drop", async (e) => {
    e.preventDefault();
    tr.classList.remove("drag-over-top", "drag-over-bottom");
    const dragId = e.dataTransfer.getData("text/plain");
    const dropId = item.id;
    if (dragId === dropId) return;
    const allIds = [...items.keys()];
    const dragIdx = allIds.indexOf(dragId);
    const dropIdx = allIds.indexOf(dropId);
    if (dragIdx === -1 || dropIdx === -1) return;
    // Reorder via API: remove and re-add at position
    const rect = tr.getBoundingClientRect();
    const insertBefore = e.clientY < rect.top + rect.height / 2;
    await api("POST", "/api/queue/reorder", {
      drag_id: dragId, drop_id: dropId, before: insertBefore,
    }).catch(() => {});
    await refreshQueue();
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
els["btn-retry"].onclick = async () => {
  if (!selected.size) { log("Select items to retry", "warning"); return; }
  await api("POST", "/api/run/retry", [...selected]);
  await refreshQueue();
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
  // Also show toasts for non-trivial messages
  if (window.Toast && tag && message.length > 3) {
    window.Toast.show(message, tag, tag === "error" ? 6000 : 3000);
  }
}

// ---------------------------------------------------------------------- SSE

let startTime = null;
let finishedCount = 0;

function updateProgress() {
  const total = items.size;
  const finished = [...items.values()]
    .filter(i => ["done", "failed", "skipped", "cancelled"].includes(i.state)).length;
  els["progress-bar"].style.width = total ? `${(finished / total) * 100}%` : "0%";
  if (running) {
    let text = `Running — ${finished}/${total}`;
    if (startTime && finishedCount > 0) {
      const elapsed = (Date.now() - startTime) / 1000;
      const eta = elapsed / finishedCount * (total - finishedCount);
      if (eta > 60) {
        text += `  ~${Math.round(eta / 60)}m remaining`;
      } else {
        text += `  ~${Math.round(eta)}s remaining`;
      }
    }
    els["status-text"].textContent = text;
  }
}

function connectEvents() {
  const es = new EventSource("/api/events");
  es.onmessage = (e) => {
    const evt = JSON.parse(e.data);
    if (evt.message) log(evt.message, evt.tag);
    if (evt.item) updateRow(evt.item);

    switch (evt.kind) {
      case "run_started":
        startTime = Date.now();
        finishedCount = 0;
        setRunning(true);
        els["stage-text"].textContent = "";
        break;
      case "stage_started":
        els["stage-text"].textContent = evt.item ? `${evt.stage} · ${evt.item.name}` : "";
        updateProgress();
        break;
      case "item_finished":
        finishedCount++;
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
function renderCompare(container, data, { editableStages = new Set() } = {}) {
  const confBits = [];
  if (data.language) confBits.push(`source: ${escapeHtml(data.language)}`);
  if (data.confidence != null) confBits.push(`confidence ${data.confidence}/100`);

  container.querySelector(".compare-title").textContent = data.title || "No document selected";
  const confEl = container.querySelector(".compare-conf");
  confEl.textContent = confBits.join("   ");
  confEl.className = `compare-conf dim conf-${data.confidence_tier || "none"}`;

  // Store original text for "Show original" toggle
  container.dataset.originalRaw = data.original_raw || "";
  container.dataset.originalCleaned = data.original_cleaned || "";
  container.dataset.originalTranslated = data.original_translated || "";

  const panes = {
    raw: { text: data.raw, ranges: data.diff?.raw_ranges || [], original: data.original_raw || "" },
    cleaned: { text: data.cleaned, ranges: data.diff?.cleaned_ranges || [], original: data.original_cleaned || "" },
    translated: { text: data.translated, ranges: data.diff?.translated_ranges || [], original: data.original_translated || "" },
  };
  for (const [key, { text, ranges, original }] of Object.entries(panes)) {
    const el = container.querySelector(`.compare-pane[data-pane="${key}"] .compare-text`);
    const meta = container.querySelector(`.compare-pane[data-pane="${key}"] .compare-meta`);
    // Store original text on the pane itself for toggle access
    const paneEl = container.querySelector(`.compare-pane[data-pane="${key}"]`);
    if (paneEl) paneEl.dataset.originalText = original;
    // Any stage in editableStages gets a plain-text textarea instead of highlighted innerHTML.
    if (editableStages.has(key)) {
      el.innerHTML = "";
      const textarea = document.createElement("textarea");
      textarea.className = "raw-edit";
      textarea.value = text || "";
      textarea.placeholder = "(not run)";
      el.appendChild(textarea);
      meta.textContent = text ? `${text.length.toLocaleString()} chars` : "";
      continue;
    }
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
  container.querySelectorAll(".compare-pane").forEach(el => { delete el.dataset.originalText; });
}

// Shared: toggle between current/edited text and original text.
// Called from both Preview and History tabs.
function wireOriginalToggles(container) {
  container.addEventListener("click", (e) => {
    const btn = e.target.closest(".btn-show-original");
    if (!btn) return;
    const pane = btn.closest(".compare-pane");
    if (!pane) return;
    const textEl = pane.querySelector(".compare-text");
    const textarea = textEl ? textEl.querySelector("textarea") : null;
    const currentText = textarea ? textarea.value : (textEl ? textEl.textContent || textEl.innerText : "");
    const originalText = pane.dataset.originalText || "";

    if (!originalText) return; // nothing to show

    const showingOriginal = btn.classList.toggle("showing-original");
    btn.textContent = showingOriginal ? "Edited" : "Original";

    if (textarea) {
      // Editable pane: swap textarea value
      if (showingOriginal) {
        textarea.dataset.editedText = currentText;
        textarea.value = originalText;
      } else {
        textarea.value = textarea.dataset.editedText || currentText;
        delete textarea.dataset.editedText;
      }
      // Trigger input event so save button state updates
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
}

// Shared: cross-highlight — when text is selected in one pane,
// find and select the same text in all other editable panes.
function wireCrossHighlight(container) {
  let lastSearch = "";
  let lastKey = "";
  let timer = null;

  function findInPane(key, query) {
    const pane = container.querySelector(`.compare-pane[data-pane="${key}"]`);
    if (!pane) return;
    const textarea = pane.querySelector("textarea.raw-edit");
    if (!textarea) return;
    const text = textarea.value;
    const idx = text.indexOf(query);
    if (idx !== -1) {
      textarea.focus();
      textarea.setSelectionRange(idx, idx + query.length);
      // Scroll into view roughly
      const linesBefore = text.slice(0, idx).split("\n").length - 1;
      const lineHeight = 20;
      textarea.scrollTop = Math.max(0, linesBefore * lineHeight - textarea.clientHeight / 3);
    }
  }

  container.addEventListener("mouseup", (e) => {
    const textarea = e.target.closest("textarea.raw-edit");
    if (!textarea) return;
    const pane = textarea.closest(".compare-pane");
    if (!pane) return;
    const key = pane.dataset.pane;
    if (!key) return;
    const selected = textarea.value.substring(
      textarea.selectionStart, textarea.selectionEnd
    ).trim();
    if (!selected || selected.length < 2) {
      lastSearch = "";
      return;
    }
    if (selected === lastSearch && key === lastKey) return;
    lastSearch = selected;
    lastKey = key;

    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      const others = ["raw", "cleaned", "translated"].filter((k) => k !== key);
      others.forEach((k) => findInPane(k, selected));
    }, 200);
  });
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

// ----------------------------------------------------------------- theme toggle

const ThemeToggle = (function () {
  const STORAGE_KEY = "ocr_theme";
  const btn = document.getElementById("btn-theme-toggle");

  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    if (btn) btn.textContent = theme === "dark" ? "☀️" : "🌙";
  }

  function init() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      apply(saved);
    } else if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
      apply("dark");
    }
  }

  function toggle() {
    const current = document.documentElement.dataset.theme;
    const next = current === "dark" ? "light" : "dark";
    apply(next);
    localStorage.setItem(STORAGE_KEY, next);
  }

  if (btn) btn.addEventListener("click", toggle);
  init();
  return { toggle };
})();

window.ThemeToggle = ThemeToggle;

// --------------------------------------------------------- palette hint button

document.getElementById("btn-palette-hint")?.addEventListener("click", () => {
  window.Palette?.open();
});

// -------------------------------------------------------- column visibility

const ColVis = (function () {
  const STORAGE_KEY = "ocr_col_vis";
  let menuEl = null;
  const COLS = [
    { key: "ocr", label: "OCR", default: true },
    { key: "cleanup", label: "Cleanup", default: true },
    { key: "translate", label: "Translate", default: true },
    { key: "confidence", label: "Conf", default: true },
    { key: "elapsed", label: "Time", default: true },
  ];

  function loadState() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch { return {}; }
  }

  function saveState(state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function isVisible(key) {
    const state = loadState();
    if (key in state) return state[key];
    return COLS.find(c => c.key === key)?.default ?? true;
  }

  function toggle(key) {
    const state = loadState();
    state[key] = !isVisible(key);
    saveState(state);
    apply();
  }

  function apply() {
    const header = els["queue-body"]?.closest("table")?.querySelector("thead tr");
    const rows = els["queue-body"]?.querySelectorAll("tr");
    if (!header) return;
    const ths = header.querySelectorAll("th");
    // th indices: 0=checkbox, 1=File, 2=OCR, 3=Cleanup, 4=Translate, 5=Conf, 6=Time, 7=Status, 8=view
    const colMap = { ocr: 2, cleanup: 3, translate: 4, confidence: 5, elapsed: 6 };
    for (const [key, idx] of Object.entries(colMap)) {
      const vis = isVisible(key);
      if (ths[idx]) ths[idx].style.display = vis ? "" : "none";
      rows?.forEach(tr => {
        const td = tr.children[idx];
        if (td) td.style.display = vis ? "" : "none";
      });
    }
  }

  function showMenu(e) {
    if (!menuEl) {
      menuEl = document.createElement("div");
      menuEl.className = "col-vis-menu hidden";
      menuEl.innerHTML = COLS.map(c => `
        <div class="col-vis-item" data-col="${c.key}">
          <input type="checkbox" ${isVisible(c.key) ? "checked" : ""}>
          <span>${c.label}</span>
        </div>`).join("");
      document.body.appendChild(menuEl);
      menuEl.querySelectorAll(".col-vis-item").forEach(el => {
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          const cb = el.querySelector("input");
          cb.checked = !cb.checked;
          toggle(el.dataset.col);
        });
      });
    }
    menuEl.classList.toggle("hidden");
    if (!menuEl.classList.contains("hidden")) {
      const rect = e.target.getBoundingClientRect();
      menuEl.style.top = `${rect.bottom + 4}px`;
      menuEl.style.left = `${rect.left}px`;
      // Sync checkboxes
      menuEl.querySelectorAll(".col-vis-item").forEach(el => {
        el.querySelector("input").checked = isVisible(el.dataset.col);
      });
      const close = (ev) => {
        if (!menuEl.contains(ev.target)) {
          menuEl.classList.add("hidden");
          document.removeEventListener("click", close);
        }
      };
      setTimeout(() => document.addEventListener("click", close), 0);
    }
  }

  apply();
  return { showMenu, apply };
})();

window.ColVis = ColVis;

// -------------------------------------------------------- batch correct

const TEMPLATE_STORAGE_KEY = "ocr_batch_templates";

const BatchCorrect = (function () {
  const modal = document.getElementById("modal-batch-correct");
  const findInput = document.getElementById("batch-find");
  const replaceInput = document.getElementById("batch-replace");
  const stageRaw = document.getElementById("batch-stage-raw");
  const stageCleaned = document.getElementById("batch-stage-cleaned");
  const stageTranslated = document.getElementById("batch-stage-translated");
  const applySelected = document.getElementById("batch-apply-selected");
  const statusEl = document.getElementById("batch-status");
  const templateSelect = document.getElementById("batch-template-select");
  const btnApply = document.getElementById("btn-batch-apply");
  const btnSave = document.getElementById("btn-batch-template-save");
  const btnDelete = document.getElementById("btn-batch-template-delete");
  const btnClose = document.getElementById("btn-batch-cancel");

  function loadTemplates() {
    try { return JSON.parse(localStorage.getItem(TEMPLATE_STORAGE_KEY)) || []; } catch { return []; }
  }

  function saveTemplates(templates) {
    localStorage.setItem(TEMPLATE_STORAGE_KEY, JSON.stringify(templates));
  }

  function renderTemplates(selectEl) {
    const templates = loadTemplates();
    selectEl.innerHTML = `<option value="">-- Load template --</option>`
      + templates.map((t, i) => `<option value="${i}">${escapeHtml(t.name)}</option>`).join("");
  }

  function open() {
    if (!modal) return;
    modal.classList.remove("hidden");
    renderTemplates(templateSelect);
    statusEl.textContent = "";
  }

  function close() {
    if (modal) modal.classList.add("hidden");
  }

  async function apply() {
    const find = findInput.value.trim();
    const replace = replaceInput.value;
    if (!find) { statusEl.textContent = "Enter text to find."; return; }
    const stages = [];
    if (stageRaw.checked) stages.push("raw");
    if (stageCleaned.checked) stages.push("cleaned");
    if (stageTranslated.checked) stages.push("translated");
    if (!stages.length) { statusEl.textContent = "Select at least one stage."; return; }

    btnApply.disabled = true;
    const label = btnApply.textContent;
    btnApply.textContent = "Applying\u2026";
    statusEl.textContent = "";

    try {
      const body = { find, replace, stages };
      if (applySelected.checked) body.item_ids = [...selected];
      const result = await api("POST", "/api/queue/batch-replace", body);
      setQueue(result.items);
      statusEl.textContent = `Applied to ${result.updated} text(s) across ${result.items.length} item(s).`;
      log(`Batch correct applied: "${find}" -> "${replace}" (${result.updated} change(s))`, "accent");
    } catch (err) {
      statusEl.textContent = `Error: ${err.message}`;
      log(`Batch correct failed: ${err.message}`, "error");
    } finally {
      btnApply.textContent = label;
      btnApply.disabled = false;
    }
  }

  function saveTemplate() {
    const name = prompt("Template name:");
    if (!name) return;
    const templates = loadTemplates();
    templates.push({
      name,
      find: findInput.value,
      replace: replaceInput.value,
      stages: {
        raw: stageRaw.checked,
        cleaned: stageCleaned.checked,
        translated: stageTranslated.checked,
      },
    });
    saveTemplates(templates);
    renderTemplates(templateSelect);
    templateSelect.value = templates.length - 1;
  }

  function loadTemplate() {
    const idx = parseInt(templateSelect.value, 10);
    if (isNaN(idx)) return;
    const templates = loadTemplates();
    const t = templates[idx];
    if (!t) return;
    findInput.value = t.find || "";
    replaceInput.value = t.replace || "";
    stageRaw.checked = t.stages?.raw ?? true;
    stageCleaned.checked = t.stages?.cleaned ?? true;
    stageTranslated.checked = t.stages?.translated ?? true;
  }

  function deleteTemplate() {
    const idx = parseInt(templateSelect.value, 10);
    if (isNaN(idx)) return;
    if (!confirm("Delete this template?")) return;
    const templates = loadTemplates();
    templates.splice(idx, 1);
    saveTemplates(templates);
    renderTemplates(templateSelect);
  }

  templateSelect.addEventListener("change", loadTemplate);
  btnSave.addEventListener("click", saveTemplate);
  btnDelete.addEventListener("click", deleteTemplate);
  btnApply.addEventListener("click", apply);
  btnClose.addEventListener("click", close);
  // Close on backdrop click
  modal?.addEventListener("click", (e) => { if (e.target === modal) close(); });

  document.getElementById("btn-batch-correct")?.addEventListener("click", open);

  return { open, close };
})();

window.BatchCorrect = BatchCorrect;
