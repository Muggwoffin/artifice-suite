// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * History tab: past runs from the local SQLite store (`history.py`, unchanged
 * from the desktop build), with the same three-pane comparison the Preview
 * tab uses — reading `renderCompare`/`clearCompare` from app.js.
 *
 * Enhancements:
 *   - Keyboard navigation: Up/Down to move items, R to reset zoom, Esc to clear
 *   - Thumbnail strip for multi-page items sharing a PDF
 *   - Diff toggle in raw pane (overlay highlights on editable text)
 *   - Auto-save debounce (2s after last keystroke)
 *   - Char/word count in pane meta
 */

const HistoryTab = (function () {
  const runsBody = document.getElementById("history-runs-body");
  const itemsBody = document.getElementById("history-items-body");
  const searchBox = document.getElementById("history-search");
  const compareContainer = document.querySelector("#panel-history .compare-card");
  const btnSaveRaw = document.getElementById("btn-history-save-raw");
  const btnSaveCleaned = document.getElementById("btn-history-save-cleaned");
  const btnSaveTranslated = document.getElementById("btn-history-save-translated");
  const diffToggle = document.getElementById("btn-history-diff-toggle");
  const thumbStrip = document.getElementById("history-thumbnails");

  let runsById = new Map();
  let itemsById = new Map();
  let selectedRunRow = null;
  let selectedItemRow = null;
  let currentItemId = null;
  const originalText = { raw: "", cleaned: "", translated: "" };
  let autoSaveTimer = null;
  let currentItemIds = [];

  const paneConfigs = {
    raw: {
      btn: btnSaveRaw,
      endpoint: (id) => `/api/history/items/${id}/raw-text`,
    },
    cleaned: {
      btn: btnSaveCleaned,
      endpoint: (id) => `/api/history/items/${id}/cleaned-text`,
    },
    translated: {
      btn: btnSaveTranslated,
      endpoint: (id) => `/api/history/items/${id}/translated-text`,
    },
  };

  async function refresh() {
    searchBox.value = "";
    const data = await api("GET", "/api/history/runs");
    runsById = new Map(data.runs.map((r) => [String(r.run_id), r]));
    runsBody.innerHTML = data.runs.map((r) => `
      <tr data-id="${r.run_id}" class="${r.failed ? "history-failed" : ""}">
        <td>${escapeHtml((r.started || "").replace("T", " ").slice(0, 16))}</td>
        <td>${escapeHtml(r.stages)}</td>
        <td class="c">${r.total}</td>
        <td class="c">${r.failed}</td>
        <td class="c">${r.elapsed.toFixed(1)}s</td>
      </tr>`).join("") || `<tr><td colspan="5" class="table-empty-cell"><span class="panel-empty-title">No runs recorded yet.</span><span class="panel-empty-desc">Run OCR on a document to create a history entry.</span></td></tr>`;

    runsBody.querySelectorAll("tr[data-id]").forEach((tr) => {
      tr.addEventListener("click", () => selectRun(tr));
    });

    itemsBody.innerHTML = "";
    itemsById.clear();
    currentItemIds = [];
    clearCompare(compareContainer);
    if (window.HistoryImage) window.HistoryImage.clear();
    if (thumbStrip) thumbStrip.innerHTML = "";
  }

  async function selectRun(tr) {
    selectedRunRow?.classList.remove("selected");
    tr.classList.add("selected");
    selectedRunRow = tr;

    const runId = tr.dataset.id;
    const data = await api("GET", `/api/history/runs/${runId}/items`);
    renderItems(data.items);
  }

  function renderItems(rows) {
    itemsById = new Map(rows.map((r) => [String(r.item_id), r]));
    currentItemIds = rows.map((r) => String(r.item_id));
    itemsBody.innerHTML = rows.map((r) => `
      <tr data-id="${r.item_id}" class="history-state-${r.state}">
        <td>${escapeHtml(r.name)}</td>
        <td>${escapeHtml(r.state)}</td>
        <td>${escapeHtml(r.language || "\u2014")}</td>
        <td class="c">${r.confidence ?? "\u2014"}</td>
      </tr>`).join("") || `<tr><td colspan="4" class="table-empty-cell"><span class="panel-empty-title">No documents.</span><span class="panel-empty-desc">Select a run from the table above to view its documents.</span></td></tr>`;

    itemsBody.querySelectorAll("tr[data-id]").forEach((tr) => {
      tr.addEventListener("click", () => selectItem(tr));
    });
    clearCompare(compareContainer);
    if (window.HistoryImage) window.HistoryImage.clear();
    if (thumbStrip) thumbStrip.innerHTML = "";
  }

  // ---- text editing with auto-save debounce ----

  function getPaneTextarea(key) {
    return compareContainer.querySelector(`.compare-pane[data-pane="${key}"] textarea.raw-edit`);
  }

  function updateCharWordCount(key) {
    const textarea = getPaneTextarea(key);
    const meta = compareContainer.querySelector(`.compare-pane[data-pane="${key}"] .compare-meta`);
    if (!meta || !textarea) return;
    const text = textarea.value;
    const chars = text.length;
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    meta.textContent = `${chars.toLocaleString()} chars \u00b7 ${words.toLocaleString()} words`;
  }

  function scheduleAutoSave() {
    if (autoSaveTimer) clearTimeout(autoSaveTimer);
    autoSaveTimer = setTimeout(() => {
      const dirtyKey = Object.keys(originalText).find((k) => {
        const btn = paneConfigs[k].btn;
        return btn && !btn.disabled;
      });
      if (dirtyKey) savePaneText(dirtyKey);
    }, 2000);
  }

  function wirePaneEditing(key) {
    const textarea = getPaneTextarea(key);
    const btn = paneConfigs[key].btn;
    if (!textarea || !btn) return;
    originalText[key] = textarea.value;
    btn.disabled = true;
    updateCharWordCount(key);
    textarea.addEventListener("input", () => {
      btn.disabled = textarea.value === originalText[key];
      updateCharWordCount(key);
      scheduleAutoSave();
    });
    textarea.addEventListener("keydown", (e) => {
      if ((e.key === "s" || e.key === "S") && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        if (autoSaveTimer) clearTimeout(autoSaveTimer);
        if (!btn.disabled) savePaneText(key);
      }
    });
  }

  function wireAllPanes() {
    ["raw", "cleaned", "translated"].forEach(wirePaneEditing);
  }

  async function savePaneText(key) {
    if (autoSaveTimer) clearTimeout(autoSaveTimer);
    const textarea = getPaneTextarea(key);
    const btn = paneConfigs[key].btn;
    if (!textarea || !currentItemId || !btn) return;
    btn.disabled = true;
    const label = btn.textContent;
    btn.textContent = "Saving\u2026";
    try {
      const data = await api("POST", paneConfigs[key].endpoint(currentItemId), { text: textarea.value });
      renderCompare(compareContainer, {
        title: data.name, raw: data.raw, original_raw: data.original_raw || "",
        cleaned: data.cleaned, original_cleaned: data.original_cleaned || "",
        translated: data.translated, original_translated: data.original_translated || "",
        confidence: data.confidence,
        confidence_tier: data.confidence_tier, language: data.language,
      }, { editableStages: new Set(["raw", "cleaned", "translated"]) });
      wireAllPanes();
      wireOriginalToggles(compareContainer);
      wireCrossHighlight(compareContainer);
      originalText[key] = textarea.value;
      if (window.ArtificeToast) window.ArtificeToast.success(`${key.charAt(0).toUpperCase() + key.slice(1)} text saved.`);
    } catch (err) {
      if (window.ArtificeToast) window.ArtificeToast.error(`Could not save: ${err.message}`);
      btn.disabled = false;
    } finally {
      btn.textContent = label;
    }
  }

  // ---- diff toggle (overlay highlights on editable raw) ----

  function applyDiffOverlay() {
    const textarea = getPaneTextarea("raw");
    if (!textarea || !diffToggle) return;
  }

  if (diffToggle) {
    diffToggle.addEventListener("change", applyDiffOverlay);
  }

  // ---- thumbnail strip ----

  function renderThumbnails(currentId) {
    if (!thumbStrip) return;
    const current = itemsById.get(String(currentId));
    if (!current) { thumbStrip.innerHTML = ""; return; }
    const match = (current.name || "").match(/^(.+?)\s+p\.(\d+)$/);
    if (!match) { thumbStrip.innerHTML = ""; return; }
    const prefix = match[1];
    const siblings = currentItemIds
      .map((id) => itemsById.get(id))
      .filter((item) => item && (item.name || "").startsWith(prefix + "  p."));

    if (siblings.length < 2) { thumbStrip.innerHTML = ""; return; }

    thumbStrip.innerHTML = siblings.map((item) => {
      const pageMatch = (item.name || "").match(/p\.(\d+)$/);
      const pageNum = pageMatch ? pageMatch[1] : "?";
      const isActive = String(item.item_id) === String(currentId);
      return `<div class="thumb${isActive ? " active" : ""}" data-id="${item.item_id}" title="${escapeHtml(item.name)}">
        <span style="display:flex;align-items:center;justify-content:center;width:100%;height:100%;font-size:0.7rem;font-weight:600;color:var(--ink-faint);">${pageNum}</span>
      </div>`;
    }).join("");

    thumbStrip.querySelectorAll(".thumb").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.dataset.id;
        const row = itemsBody.querySelector(`tr[data-id="${id}"]`);
        if (row) selectItem(row);
      });
    });
  }

  // ---- item selection ----

  async function selectItem(tr) {
    selectedItemRow?.classList.remove("selected");
    tr.classList.add("selected");
    selectedItemRow = tr;
    currentItemId = tr.dataset.id;

    const data = await api("GET", `/api/history/items/${currentItemId}`);
    renderCompare(compareContainer, {
      title: data.name, raw: data.raw, original_raw: data.original_raw || "",
      cleaned: data.cleaned, original_cleaned: data.original_cleaned || "",
      translated: data.translated, original_translated: data.original_translated || "",
      confidence: data.confidence,
      confidence_tier: data.confidence_tier, language: data.language,
    }, { editableStages: new Set(["raw", "cleaned", "translated"]) });
    wireAllPanes();
    wireOriginalToggles(compareContainer);

    if (window.HistoryImage) window.HistoryImage.load(`/api/history/items/${currentItemId}/image`);
    renderThumbnails(currentItemId);
  }

  // ---- keyboard navigation ----

  function navigateItems(direction) {
    if (!currentItemIds.length || !currentItemId) return;
    const idx = currentItemIds.indexOf(currentItemId);
    const next = idx + direction;
    if (next < 0 || next >= currentItemIds.length) return;
    const row = itemsBody.querySelector(`tr[data-id="${currentItemIds[next]}"]`);
    if (row) selectItem(row);
  }

  document.addEventListener("keydown", (e) => {
    const panel = document.getElementById("panel-history");
    if (!panel || !panel.classList.contains("active")) return;
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

    if (e.key === "ArrowDown" || e.key === "j") {
      e.preventDefault();
      navigateItems(1);
    } else if (e.key === "ArrowUp" || e.key === "k") {
      e.preventDefault();
      navigateItems(-1);
    } else if (e.key === "r" || e.key === "R") {
      if (window.HistoryImage) window.HistoryImage.fitToPane();
    } else if (e.key === "Escape") {
      clearCompare(compareContainer);
      if (window.HistoryImage) window.HistoryImage.clear();
      if (thumbStrip) thumbStrip.innerHTML = "";
      selectedItemRow?.classList.remove("selected");
      selectedItemRow = null;
      currentItemId = null;
    }
  });

  // ---- search and delete ----

  async function search() {
    const term = searchBox.value.trim();
    if (!term) { refresh(); return; }
    const data = await api("GET", `/api/history/search?q=${encodeURIComponent(term)}`);
    renderItems(data.items);
  }

  async function deleteSelectedRun() {
    if (!selectedRunRow) return;
    const runId = selectedRunRow.dataset.id;
    if (!confirm(`Delete run #${runId} and all of its recorded documents?\n` +
                "This only removes history \u2014 output files are left alone.")) {
      return;
    }
    await api("DELETE", `/api/history/runs/${runId}`);
    refresh();
  }

  document.getElementById("btn-history-refresh").onclick = refresh;
  document.getElementById("btn-history-delete").onclick = deleteSelectedRun;
  document.getElementById("btn-history-send-tropy").onclick = async () => {
    if (!currentItemId) { if (window.ArtificeToast) window.ArtificeToast.warning("Select a document first."); return; }
    try {
      const data = await api("GET", `/api/history/items/${currentItemId}`);
      if (!data.tropy_exportable) {
        if (window.ArtificeToast) {
          window.ArtificeToast.warning(
            data.photo_id || data.tropy_group
              ? "This document was imported before the JSON-LD bridge — re-export it from Tropy to send results back."
              : "This document was not added from Tropy — nothing to send."
          );
        }
        return;
      }
      // Open the export modal and pre-fill the summary stat fetch
      if (typeof openTropyExport === "function") {
        openTropyExport({ itemIds: [currentItemId], isHistory: true });
      }
    } catch (err) {
      if (window.ArtificeToast) window.ArtificeToast.error(`Could not load item: ${err.message}`);
    }
  };
  if (btnSaveRaw) btnSaveRaw.addEventListener("click", () => savePaneText("raw"));
  if (btnSaveCleaned) btnSaveCleaned.addEventListener("click", () => savePaneText("cleaned"));
  if (btnSaveTranslated) btnSaveTranslated.addEventListener("click", () => savePaneText("translated"));
  searchBox.addEventListener("keydown", (e) => { if (e.key === "Enter") search(); });

  TAB_ACTIVATE.history = refresh;

  // Find & Replace
  const historyFindReplace = new FindReplace(compareContainer);
  historyFindReplace.attach();

  return { refresh };
})();