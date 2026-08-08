// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * Core app: settings form, document upload, run control, SSE progress.
 * Plain globals (no module system) — matches the OCR Pipeline tool's web
 * build, which this frontend is deliberately styled and structured after.
 */

async function api(method, path, body, isFormData = false) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    if (isFormData) {
      opts.body = body;
    } else {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* ignore */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* `ranges` is a list of [start, end, tag] character offsets, computed
 * server-side (src/_diff.py) so the highlight logic can never quietly
 * diverge between what the model changed and what the UI shows. */
function highlightRanges(text, ranges) {
  if (!ranges || !ranges.length) return escapeHtml(text);
  const sorted = [...ranges].sort((a, b) => a[0] - b[0]);
  let out = "", pos = 0;
  for (const [start, end, tag] of sorted) {
    if (start > pos) out += escapeHtml(text.slice(pos, start));
    out += `<mark class="hl-${tag}">${escapeHtml(text.slice(start, end))}</mark>`;
    pos = end;
  }
  out += escapeHtml(text.slice(pos));
  return out;
}

const els = {
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("file-input"),
  btnBrowse: document.getElementById("btn-browse"),
  btnStart: document.getElementById("btn-start"),
  btnDownload: document.getElementById("btn-download"),
  docInfo: document.getElementById("doc-info"),
  progressBar: document.getElementById("progress-bar"),
  log: document.getElementById("log"),
  cardReview: document.getElementById("card-review"),
  cardResult: document.getElementById("card-result"),
  changelogText: document.getElementById("changelog-text"),
};

let currentDocId = null;

function logLine(msg, cls) {
  const div = document.createElement("div");
  div.className = "line" + (cls ? ` ${cls}` : "");
  div.textContent = msg;
  els.log.appendChild(div);
  els.log.scrollTop = els.log.scrollHeight;
}

function setProgress(pct) {
  els.progressBar.style.width = `${Math.max(0, Math.min(100, pct || 0))}%`;
}

// --------------------------------------------------------------- settings

async function loadSettings() {
  const cfg = await api("GET", "/api/settings");

  const provider = document.getElementById("set-llm_provider");
  const style = document.getElementById("set-editing_style");
  const guide = document.getElementById("set-style_guide");
  const fmt = document.getElementById("set-export_format");

  provider.innerHTML = cfg.providers.map(p => `<option value="${p}">${p}</option>`).join("");
  style.innerHTML = cfg.styles.map(s => `<option value="${s}">${s}</option>`).join("");
  guide.innerHTML = cfg.style_guides.map(g => `<option value="${g}">${g}</option>`).join("");
  fmt.innerHTML = cfg.export_formats.map(f => `<option value="${f}">${f}</option>`).join("");

  provider.value = cfg.llm_provider;
  style.value = cfg.editing_style;
  guide.value = cfg.style_guide || "";
  fmt.value = cfg.export_format;
  document.getElementById("set-batch_size").value = cfg.batch_size;
  document.getElementById("set-temperature").value = cfg.temperature;
  document.getElementById("set-author_name").value = cfg.author_name;
  document.getElementById("set-enable_review").checked = cfg.enable_review;
  document.getElementById("set-custom_system_prompt").value = cfg.custom_system_prompt;
  document.getElementById("model-hint").textContent = `Active model: ${cfg.active_model}`;
}

function readSettingsForm() {
  return {
    llm_provider: document.getElementById("set-llm_provider").value,
    editing_style: document.getElementById("set-editing_style").value,
    style_guide: document.getElementById("set-style_guide").value,
    export_format: document.getElementById("set-export_format").value,
    batch_size: parseInt(document.getElementById("set-batch_size").value, 10) || 5,
    temperature: parseFloat(document.getElementById("set-temperature").value),
    author_name: document.getElementById("set-author_name").value,
    enable_review: document.getElementById("set-enable_review").checked,
    custom_system_prompt: document.getElementById("set-custom_system_prompt").value,
  };
}

document.querySelectorAll(".settings-card input, .settings-card select, #model-settings-modal input, #model-settings-modal select").forEach(el => {
  el.addEventListener("change", () => {
    api("POST", "/api/settings", readSettingsForm())
      .then(cfg => { document.getElementById("model-hint").textContent = `Active model: ${cfg.active_model}`; })
      .catch(err => window.ArtificeToast.error("Settings error: " + err.message));
  });
});

document.getElementById("btn-model-settings").addEventListener("click", () => {
  document.getElementById("model-settings-modal").style.display = "flex";
});
document.getElementById("btn-model-close").addEventListener("click", () => {
  document.getElementById("model-settings-modal").style.display = "none";
});
document.getElementById("model-settings-modal").addEventListener("click", e => {
  if (e.target === e.currentTarget) e.currentTarget.style.display = "none";
});

// ----------------------------------------------------------------- upload

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith(".docx")) {
    window.ArtificeToast.error("Only .docx files are supported.");
    return;
  }
  els.cardReview.style.display = "none";
  els.cardResult.style.display = "none";
  els.btnDownload.style.display = "none";
  els.log.innerHTML = "";
  setProgress(0);

  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    const doc = await res.json();
    currentDocId = doc.doc_id;
    els.docInfo.textContent = `${doc.filename} — ${doc.paragraph_count} paragraphs`;
    els.btnStart.disabled = false;
    logLine(`Loaded ${doc.filename} (${doc.paragraph_count} paragraphs)`);
  } catch (err) {
    window.ArtificeToast.error("Upload failed: " + err.message);
  }
}

els.dropzone.addEventListener("click", () => els.fileInput.click());
els.btnBrowse.addEventListener("click", () => els.fileInput.click());
els.fileInput.addEventListener("change", () => {
  if (els.fileInput.files.length) handleFile(els.fileInput.files[0]);
});
els.dropzone.addEventListener("dragover", e => { e.preventDefault(); els.dropzone.classList.add("drag"); });
els.dropzone.addEventListener("dragleave", () => els.dropzone.classList.remove("drag"));
els.dropzone.addEventListener("drop", e => {
  e.preventDefault();
  els.dropzone.classList.remove("drag");
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});

// -------------------------------------------------------------------- run

els.btnStart.addEventListener("click", async () => {
  if (!currentDocId) return;
  els.btnStart.disabled = true;
  els.cardReview.style.display = "none";
  els.cardResult.style.display = "none";
  els.btnDownload.style.display = "none";
  els.log.innerHTML = "";
  setProgress(0);
  try {
    await api("POST", `/api/run/${currentDocId}/start`);
    logLine("Started processing…", "accent");
    listenForProgress(currentDocId);
  } catch (err) {
    window.ArtificeToast.error("Could not start: " + err.message);
    els.btnStart.disabled = false;
  }
});

function listenForProgress(docId) {
  const source = new EventSource(`/api/run/${docId}/events`);
  source.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.message) {
      if (data.stage === "error") {
        window.ArtificeToast.error(data.message);
      } else {
        logLine(data.message);
      }
    }
    setProgress(data.percentage);

    if (data.stage === "awaiting_review") {
      source.close();
      window.ReviewUI.open(docId);
    } else if (data.stage === "done") {
      source.close();
      onRunFinished(docId);
    } else if (data.stage === "error") {
      source.close();
      els.btnStart.disabled = false;
    }
  };
}

async function onRunFinished(docId) {
  const status = await api("GET", `/api/run/${docId}/status`);
  els.cardResult.style.display = "block";
  els.changelogText.textContent = status.summary || "";
  els.btnDownload.style.display = "inline-block";
  els.btnDownload.href = `/api/run/${docId}/download`;
  els.btnStart.disabled = false;
  window.ArtificeToast.success("Saved to " + status.output_filename);
}

window.PersonaeApp = { logLine, setProgress, onRunFinished };

// --------------------------------------------------------------- theme
//
// Same pattern and storage-key convention as artifice-graph's app.js
// ("artifice-<app>-theme"), adapted to this file's non-IIFE, arrow-function
// idiom. The toggle button (#themeToggle / #themeGlyph) is rendered by the
// shared _masthead.html partial, included via base.html.

function getThemePref() {
  try { return window.localStorage.getItem("artifice-draft-theme"); } catch (e) { return null; }
}

function setThemePref(theme) {
  try { window.localStorage.setItem("artifice-draft-theme", theme); } catch (e) { /* ignore */ }
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const glyph = document.getElementById("themeGlyph");
  if (!glyph) return;
  const sun = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
  const moon = '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>';
  glyph.innerHTML = theme === "dark" ? moon : sun;
}

function initTheme() {
  let saved = getThemePref();
  if (!saved) {
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    saved = prefersDark ? "dark" : "light";
  }
  applyTheme(saved);

  const toggle = document.getElementById("themeToggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "light";
      const next = current === "dark" ? "light" : "dark";
      applyTheme(next);
      setThemePref(next);
    });
  }
}

// ----------------------------------------------------- keyboard shortcuts
//
// Deliberately small relative to artifice-transcribe's shortcut set: this
// app's interaction surface (upload -> run -> review -> download) is much
// thinner than transcribe's segment editor, so only the two shortcuts that
// map onto an existing, always-present control are bound. Both modals
// (#guide-modal, #model-settings-modal) already close via a visible button
// and an overlay click; Escape is the keyboard-equivalent third path.

function anyModalOpen() {
  const guideModal = document.getElementById("guide-modal");
  const modelModal = document.getElementById("model-settings-modal");
  const byomOverlay = document.querySelector(".byom-overlay");
  return (!!guideModal && guideModal.style.display !== "none") ||
         (!!modelModal && modelModal.style.display !== "none") ||
         !!byomOverlay;
}

function closeOpenModals() {
  const guideModal = document.getElementById("guide-modal");
  if (guideModal && guideModal.style.display !== "none") guideModal.style.display = "none";
  const modelModal = document.getElementById("model-settings-modal");
  if (modelModal && modelModal.style.display !== "none") modelModal.style.display = "none";
}

function initKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    // Escape: close whichever modal is open.
    if (e.key === "Escape") {
      closeOpenModals();
      return;
    }
    // Ctrl/Cmd+Enter: start editing the loaded document, mirroring
    // artifice-transcribe's Ctrl+Enter-to-save. Guarded on no modal being
    // open so it can't fire the pipeline while the guide-import or
    // model-settings dialog is mid-edit.
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !anyModalOpen()) {
      const btnStart = document.getElementById("btn-start");
      if (btnStart && !btnStart.disabled) {
        e.preventDefault();
        btnStart.click();
      }
    }
  });
}

initTheme();
initKeyboardShortcuts();

loadSettings().catch(err => window.ArtificeToast.error("Could not load settings: " + err.message));

// ── Handoff: check for text sent from another app ────────────────
(function () {
  var params = new URLSearchParams(window.location.search);
  var source = params.get("handoff_source");
  if (source) {
    fetch("/api/handoff-text")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.text) {
          var area = document.getElementById("handoff-area");
          var textarea = document.getElementById("handoff-text");
          var sourceLabel = document.getElementById("handoff-source");
          if (area && textarea) {
            textarea.value = data.text;
            if (sourceLabel) sourceLabel.textContent = "from " + source;
            area.style.display = "block";
            els.docInfo.textContent = "Imported text from " + source + " (" + data.text.length + " chars)";
          }
        }
      })
      .catch(function () { /* silent */ });
    // Clean URL
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }
})();
