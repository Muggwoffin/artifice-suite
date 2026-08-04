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
    max_ocr_workers: "int", chunk_max_tokens: "int",
    resume: "bool", confidence_enabled: "bool", ollama_think: "bool",
  };

  const docTypeSelect = document.getElementById("set-document_type");
  const docTypeHint = document.getElementById("doc-type-hint");
  const savedLabel = document.getElementById("settings-saved");
  const healthPanel = document.getElementById("health-panel");

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
    updateDocTypeHint();
    updateConnectionVisibility();
  }

  function collect() {
    const out = {};
    for (const [key, kind] of Object.entries(FIELDS)) {
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

  async function load() {
    await ensureDocTypes();
    const cfg = await api("GET", "/api/config");
    apply(cfg);
  }

  async function save() {
    await api("POST", "/api/config", collect());
    savedLabel.textContent = "Saved.";
    savedLabel.style.color = "var(--accent)";
    setTimeout(() => { savedLabel.textContent = ""; }, 2500);
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

  docTypeSelect.addEventListener("change", updateDocTypeHint);
  document.getElementById("btn-settings-save").onclick = save;
  document.getElementById("btn-settings-reset").onclick = resetDefaults;
  document.getElementById("btn-preflight").onclick = runPreflight;
  document.getElementById("btn-template-save").onclick = saveTemplate;
  document.getElementById("btn-template-apply").onclick = applyTemplate;
  document.getElementById("btn-template-delete").onclick = deleteTemplate;
  document.getElementById("btn-retrigger-onboarding").onclick = () => {
    if (window.Onboarding) window.Onboarding.retrigger();
  };

  let loaded = false;
  TAB_ACTIVATE.settings = () => {
    if (!loaded) { loaded = true; load(); }
    refreshTemplates();
  };

  return { load };
})();
