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
      .catch(err => logLine(`Settings error: ${err.message}`, "error"));
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
    logLine("Only .docx files are supported.", "error");
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
    logLine(`Upload failed: ${err.message}`, "error");
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
    logLine(`Could not start: ${err.message}`, "error");
    els.btnStart.disabled = false;
  }
});

function listenForProgress(docId) {
  const source = new EventSource(`/api/run/${docId}/events`);
  source.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.message) logLine(data.message, data.stage === "error" ? "error" : undefined);
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
  logLine(`Saved to ${status.output_filename}`, "success");
}

window.PersonaeApp = { logLine, setProgress, onRunFinished };

loadSettings().catch(err => logLine(`Could not load settings: ${err.message}`, "error"));
