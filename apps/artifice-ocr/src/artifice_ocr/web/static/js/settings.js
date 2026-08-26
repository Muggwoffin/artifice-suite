// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * Settings tab: models/endpoints/processing options bound to /api/config,
 * plus a pre-flight service-health check. Mirrors gui/views/settings_view.py
 * field-for-field; the persistence rules are identical too — Save writes to
 * ~/.artifice_ocr/settings.json via the same config.save_user_settings() the
 * desktop build calls, Reset only clears the in-memory/session override until
 * Save is pressed again.
 */

const SettingsTab = (function () {
  const FIELDS = {
    ocr_backend: "select", cleanup_backend: "select", translate_backend: "select",
    ocr_model: "text", cleanup_model: "text", translate_model: "text",
    lm_studio_url: "text", ollama_url: "text", huggingface_token: "text",
    api_key: "text", api_base_url: "text",
    document_type: "select",
    max_ocr_workers: "int", chunk_max_tokens: "int", context_size: "int",
    resume: "bool", confidence_enabled: "bool", ollama_think: "bool", tropy_live_browse_enabled: "bool",
  };

  // Only Ollama honours a per-request context window. LM Studio fixes it when
  // it *loads* a model and hosted APIs set it server-side, so on those backends
  // the field is disabled and says where the limit really lives — a control
  // that looks live and is ignored is worse than no control.
  const CONTEXT_SIZE_HINTS = {
    ollama: null,   // null = field stays enabled, default hint shown
    lm_studio:
      "LM Studio sets the context window when it loads a model, so this cannot " +
      "be changed from here. Raise it in LM Studio, or run: " +
      "lms load <model> --context-length 8192",
    api_key:
      "This backend sets its context window server-side. Choose a model with a " +
      "larger context window instead.",
    huggingface:
      "This backend sets its context window server-side. Choose a model with a " +
      "larger context window instead.",
  };

  const DEFAULT_CONTEXT_HINT =
    "0 uses the model’s own default. Raise this if a page fails with " +
    "“exceeds the available context size”.";

  // The OCR stage is what overflows on a page image, so the *vision* backend
  // decides whether this field can do anything — not cleanup or translate.
  function updateContextSizeState() {
    const input = document.getElementById("set-context_size");
    const hint = document.getElementById("context-size-hint");
    if (!input || !hint) return;

    const backendSel = document.getElementById("set-ocr_backend");
    const backend = backendSel ? backendSel.value : "";

    // "auto" resolves at run time, so it cannot be pinned to one answer here.
    if (!backend || backend === "auto") {
      input.disabled = false;
      hint.textContent =
        DEFAULT_CONTEXT_HINT +
        " With OCR backend set to Auto, this applies only when Ollama is chosen.";
      return;
    }

    const hintText = CONTEXT_SIZE_HINTS[backend];
    if (hintText) {
      input.disabled = true;
      hint.textContent = hintText;
    } else {
      input.disabled = false;
      hint.textContent = DEFAULT_CONTEXT_HINT;
    }
  }

  // Connection fields are only meaningful — and only visible — when a backend
  // that uses them is selected.  Mirrors the server's URL→backend mapping plus
  // the two credential rows ``updateConnectionVisibility`` also hides.  collect()
  // skips any field whose backend is inactive, so a hidden row's stale value is
  // never posted back (e.g. the shipped api_base_url default on an Ollama-only
  // install, which would otherwise 400 on the server's endpoint policy).
  const CONNECTION_FIELDS = {
    lm_studio_url: "lm_studio",
    ollama_url: "ollama",
    huggingface_token: "huggingface",
    api_key: "api_key",
    api_base_url: "api_key",
  };

  const docTypeSelect = document.getElementById("set-document_type");
  const docTypeHint = document.getElementById("doc-type-hint");
  const savedLabel = document.getElementById("settings-saved");
  const healthPanel = document.getElementById("health-panel");

  const approvedFoldersList = document.getElementById("approved-folders-list");
  const approvedFoldersStatus = document.getElementById("approved-folders-status");
  let approvedFolders = [];

  let docTypes = {};

  function el(key) {
    return document.getElementById(`set-${key}`);
  }

  async function ensureDocTypes() {
    if (Object.keys(docTypes).length) return;
    const data = await api("GET", "/api/document-types");
    docTypes = data.types;
    docTypeSelect.innerHTML = Object.keys(docTypes)
      .map(k => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join("");
  }

  function updateDocTypeHint() {
    docTypeHint.textContent = docTypes[docTypeSelect.value] || "";
  }

  function apply(values) {
    for (const [key, kind] of Object.entries(FIELDS)) {
      const value = values[key];
      if (kind === "bool") el(key).checked = !!value;
      else el(key).value = value ?? "";
    }
    approvedFolders = Array.isArray(values.approved_folders) ? values.approved_folders.slice() : [];
    renderApprovedFolders();
    updateDocTypeHint();
    updateConnectionVisibility();
    updateContextSizeState();
  }

  function collect() {
    const out = {};
    const backends = activeBackends();
    for (const [key, kind] of Object.entries(FIELDS)) {
      const backend = CONNECTION_FIELDS[key];
      if (backend && !backends.has(backend)) continue;
      const field = el(key);
      if (kind === "bool") out[key] = field.checked;
      else if (kind === "int") out[key] = parseInt(field.value, 10) || 0;
      else out[key] = field.value;
    }
    return out;
  }

  function activeBackends() {
    return new Set([
      el("ocr_backend").value,
      el("cleanup_backend").value,
      el("translate_backend").value,
    ]);
  }

  function updateConnectionVisibility() {
    const backends = activeBackends();
    const lmRow = el("lm_studio_url")?.closest("label");
    const olRow = el("ollama_url")?.closest("label");
    const hfRow = el("huggingface_token")?.closest("label");
    const akRow = el("api_key")?.closest("label");
    const buRow = el("api_base_url")?.closest("label");
    if (lmRow) lmRow.style.display = backends.has("lm_studio") ? "" : "none";
    if (olRow) olRow.style.display = backends.has("ollama") ? "" : "none";
    if (hfRow) hfRow.style.display = backends.has("huggingface") ? "" : "none";
    if (akRow) akRow.style.display = backends.has("api_key") ? "" : "none";
    if (buRow) buRow.style.display = backends.has("api_key") ? "" : "none";
  }

  function setApprovedStatus(msg, isError) {
    approvedFoldersStatus.textContent = msg;
    approvedFoldersStatus.style.color = isError ? "var(--gold)" : "";
  }

  function renderApprovedFolders() {
    approvedFoldersList.innerHTML = approvedFolders.length
      ? approvedFolders.map((folder, i) =>
          `<li style="display:flex; align-items:center; gap:0.5rem;">
             <span class="dim" style="flex:1; word-break:break-all;">${escapeHtml(folder)}</span>
             <button class="btn btn-small" data-remove-folder="${i}" type="button">Remove</button>
           </li>`).join("")
      : `<li class="dim">No folders approved yet.</li>`;
    approvedFoldersList.querySelectorAll("[data-remove-folder]").forEach(btn => {
      btn.addEventListener("click", () => removeApprovedFolder(Number(btn.dataset.removeFolder)));
    });
  }

  async function persistApprovedFolders() {
    await api("POST", "/api/config", { approved_folders: approvedFolders });
  }

  async function addApprovedFolder() {
    let folder = null;
    try {
      folder = await pickFolder();
    } catch {
      setApprovedStatus("Could not open the folder picker.", true);
      return;
    }
    if (!folder) return; // cancelled or unavailable without a typed path
    if (approvedFolders.includes(folder)) {
      setApprovedStatus("That folder is already approved.", true);
      return;
    }
    approvedFolders.push(folder);
    try {
      await persistApprovedFolders();
    } catch (err) {
      approvedFolders.pop();
      setApprovedStatus("Could not approve folder: " + err.message, true);
      return;
    }
    renderApprovedFolders();
    setApprovedStatus("", false);
  }

  async function removeApprovedFolder(index) {
    const removed = approvedFolders.splice(index, 1)[0];
    try {
      await persistApprovedFolders();
    } catch (err) {
      approvedFolders.splice(index, 0, removed);
      setApprovedStatus("Could not remove folder: " + err.message, true);
      return;
    }
    renderApprovedFolders();
    setApprovedStatus("", false);
  }

  async function load() {
    await ensureDocTypes();
    const cfg = await api("GET", "/api/config");
    apply(cfg);
  }

  async function save() {
    try {
      await api("POST", "/api/config", collect());
      savedLabel.textContent = "Saved.";
      savedLabel.style.color = "var(--accent)";
      setTimeout(() => { savedLabel.textContent = ""; }, 2500);
    } catch (err) {
      if (window.ArtificeToast) window.ArtificeToast.error("Could not save settings: " + err.message);
    }
  }

  async function resetDefaults() {
    const cfg = await api("POST", "/api/config/reset");
    apply(cfg);
    savedLabel.textContent = "Reset to defaults (not yet saved).";
    savedLabel.style.color = "var(--gold)";
    setTimeout(() => { savedLabel.textContent = ""; }, 3000);
  }

  function healthLine(label, ok, detail) {
    const cls = ok ? "health-ok" : "health-fail";
    const status = ok ? "OK" : "FAIL";
    return `<div class="${cls}">${label}   ${status}${detail ? `   ${escapeHtml(detail)}` : ""}</div>`;
  }

  async function runPreflight() {
    healthPanel.innerHTML = `<p class="dim">Checking connections&hellip;</p>`;
    try {
      const health = await api("GET", "/api/health");
      const lines = [];
      if (health.lm_studio) {
        lines.push(healthLine("LM Studio", health.lm_studio.ok,
                   health.lm_studio.ok ? health.lm_studio.url : health.lm_studio.detail));
      }
      if (health.ollama) {
        lines.push(healthLine("Ollama", health.ollama.ok, health.ollama.ok ? "" : health.ollama.detail));
        if (health.models) {
          lines.push(...health.models.map(m => healthLine(`  ${m.name}`, m.ok)));
        }
      }
      if (health.huggingface) {
        lines.push(healthLine("Hugging Face", health.huggingface.ok, health.huggingface.detail));
      }
      if (health.api_key) {
        lines.push(healthLine("API Key", health.api_key.ok,
                   health.api_key.ok ? health.api_key.url : health.api_key.detail));
      }
      healthPanel.innerHTML = lines.join("");
    } catch (err) {
      healthPanel.innerHTML = `<p class="health-fail">Could not check connections &mdash; is the server running?</p>`;
    }
  }

  // ---- templates ----

  const templateSelect = document.getElementById("template-select");
  const templateName = document.getElementById("template-name");
  const templateStatus = document.getElementById("template-status");

  function setTemplateStatus(msg, isError) {
    templateStatus.textContent = msg;
    templateStatus.style.color = isError ? "var(--gold)" : "";
  }

  async function refreshTemplates() {
    const data = await api("GET", "/api/templates");
    const names = Object.keys(data.templates);
    templateSelect.innerHTML = '<option value="">-- Select a template --</option>' +
      names.map(n => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("");
    return data.templates;
  }

  async function saveTemplate() {
    const name = templateName.value.trim();
    if (!name) { setTemplateStatus("Please enter a template name.", true); return; }
    const config = collect();
    config.stages = {
      ocr: document.getElementById("stage-ocr").checked,
      cleanup: document.getElementById("stage-cleanup").checked,
      translate: document.getElementById("stage-translate").checked,
    };
    config.force = document.getElementById("stage-force").checked;
    config.output_dir = document.getElementById("output-dir").value;
    await api("POST", "/api/templates/save", { name, config });
    templateName.value = "";
    await refreshTemplates();
    setTemplateStatus(`Template "${name}" saved.`);
  }

  async function applyTemplate() {
    const name = templateSelect.value;
    if (!name) { setTemplateStatus("Select a template first.", true); return; }
    await api("POST", "/api/templates/apply", { name });
    await load();
    // Also update non-settings fields (stages, output, force) if in template
    const data = await api("GET", "/api/templates");
    const templ = data.templates[name] || {};
    if (templ.stages) {
      if (templ.stages.ocr !== undefined) document.getElementById("stage-ocr").checked = templ.stages.ocr;
      if (templ.stages.cleanup !== undefined) document.getElementById("stage-cleanup").checked = templ.stages.cleanup;
      if (templ.stages.translate !== undefined) document.getElementById("stage-translate").checked = templ.stages.translate;
    }
    if (templ.force !== undefined) document.getElementById("stage-force").checked = templ.force;
    if (templ.output_dir) document.getElementById("output-dir").value = templ.output_dir;
    setTemplateStatus(`Template "${name}" applied.`);
  }

  async function deleteTemplate() {
    const name = templateSelect.value;
    if (!name) { setTemplateStatus("Select a template first.", true); return; }
    if (!confirm(`Delete template "${name}"?`)) return;
    await api("POST", "/api/templates/delete", { name });
    await refreshTemplates();
    setTemplateStatus(`Template "${name}" deleted.`);
  }

  // Wire up backend dropdown change events to update connection visibility
  ["ocr_backend", "cleanup_backend", "translate_backend"].forEach(key => {
    el(key).addEventListener("change", updateConnectionVisibility);
  });

  // Context size follows the *vision* backend specifically: the OCR stage is
  // what overflows on a page image, and it is the only stage whose backend
  // decides whether a per-request context window is honoured at all.
  el("ocr_backend").addEventListener("change", updateContextSizeState);

  docTypeSelect.addEventListener("change", updateDocTypeHint);
  document.getElementById("btn-settings-save").onclick = save;
  document.getElementById("btn-settings-reset").onclick = resetDefaults;
  document.getElementById("btn-preflight").onclick = runPreflight;
  document.getElementById("btn-approved-folder-add").onclick = addApprovedFolder;
  document.getElementById("btn-template-save").onclick = saveTemplate;
  document.getElementById("btn-template-apply").onclick = applyTemplate;
  document.getElementById("btn-template-delete").onclick = deleteTemplate;

  let loaded = false;
  TAB_ACTIVATE.settings = () => {
    if (!loaded) { loaded = true; load(); }
    refreshTemplates();
  };

  return { load };
})();
