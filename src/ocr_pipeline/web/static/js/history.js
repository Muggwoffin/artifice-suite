/*
 * History tab: past runs from the local SQLite store (`history.py`, unchanged
 * from the desktop build), with the same three-pane comparison the Preview
 * tab uses — reading `renderCompare`/`clearCompare` from app.js.
 */

const HistoryTab = (function () {
  const runsBody = document.getElementById("history-runs-body");
  const itemsBody = document.getElementById("history-items-body");
  const searchBox = document.getElementById("history-search");
  const compareContainer = document.querySelector("#panel-history .compare-card");
  const btnSaveRaw = document.getElementById("btn-history-save-raw");

  let runsById = new Map();
  let itemsById = new Map();
  let selectedRunRow = null;
  let selectedItemRow = null;
  let currentItemId = null;
  let originalRawText = "";

  async function refresh() {
    searchBox.value = "";
    const data = await api("GET", "/api/history/runs");
    runsById = new Map(data.runs.map(r => [String(r.run_id), r]));
    runsBody.innerHTML = data.runs.map(r => `
      <tr data-id="${r.run_id}" class="${r.failed ? "history-failed" : ""}">
        <td>${escapeHtml((r.started || "").replace("T", " ").slice(0, 16))}</td>
        <td>${escapeHtml(r.stages)}</td>
        <td class="c">${r.total}</td>
        <td class="c">${r.failed}</td>
        <td class="c">${r.elapsed.toFixed(1)}s</td>
      </tr>`).join("") || `<tr><td colspan="5" class="dim">No runs recorded yet.</td></tr>`;

    runsBody.querySelectorAll("tr[data-id]").forEach(tr => {
      tr.addEventListener("click", () => selectRun(tr));
    });

    itemsBody.innerHTML = "";
    itemsById.clear();
    clearCompare(compareContainer);
    if (window.HistoryImage) window.HistoryImage.clear();
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
    itemsById = new Map(rows.map(r => [String(r.item_id), r]));
    itemsBody.innerHTML = rows.map(r => `
      <tr data-id="${r.item_id}" class="history-state-${r.state}">
        <td>${escapeHtml(r.name)}</td>
        <td>${escapeHtml(r.state)}</td>
        <td>${escapeHtml(r.language || "—")}</td>
        <td class="c">${r.confidence ?? "—"}</td>
      </tr>`).join("") || `<tr><td colspan="4" class="dim">No documents.</td></tr>`;

    itemsBody.querySelectorAll("tr[data-id]").forEach(tr => {
      tr.addEventListener("click", () => selectItem(tr));
    });
    clearCompare(compareContainer);
    if (window.HistoryImage) window.HistoryImage.clear();
  }

  function getRawTextarea() {
    return compareContainer.querySelector('.compare-pane[data-pane="raw"] textarea.raw-edit');
  }

  function wireRawEditing() {
    const textarea = getRawTextarea();
    if (!textarea || !btnSaveRaw) return;
    originalRawText = textarea.value;
    btnSaveRaw.disabled = true;
    textarea.addEventListener("input", () => {
      btnSaveRaw.disabled = textarea.value === originalRawText;
    });
    textarea.addEventListener("keydown", (e) => {
      if ((e.key === "s" || e.key === "S") && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        if (!btnSaveRaw.disabled) saveRawText();
      }
    });
  }

  async function saveRawText() {
    const textarea = getRawTextarea();
    if (!textarea || !currentItemId || !btnSaveRaw) return;
    btnSaveRaw.disabled = true;
    const label = btnSaveRaw.textContent;
    btnSaveRaw.textContent = "Saving…";
    try {
      const data = await api("POST", `/api/history/items/${currentItemId}/raw-text`, { text: textarea.value });
      renderCompare(compareContainer, data, { editableRaw: true });
      wireRawEditing();
      log("Raw OCR text corrected and saved.", "accent");
    } catch (err) {
      log(`Could not save correction: ${err.message}`, "error");
      btnSaveRaw.disabled = false;
    } finally {
      btnSaveRaw.textContent = label;
    }
  }

  async function selectItem(tr) {
    selectedItemRow?.classList.remove("selected");
    tr.classList.add("selected");
    selectedItemRow = tr;
    currentItemId = tr.dataset.id;

    const data = await api("GET", `/api/history/items/${currentItemId}`);
    renderCompare(compareContainer, {
      title: data.name, raw: data.raw, cleaned: data.cleaned,
      translated: data.translated, confidence: data.confidence,
      confidence_tier: data.confidence_tier, language: data.language,
    }, { editableRaw: true });
    wireRawEditing();

    if (window.HistoryImage) window.HistoryImage.load(`/api/history/items/${currentItemId}/image`);
  }

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
                "This only removes history — output files are left alone.")) {
      return;
    }
    await api("DELETE", `/api/history/runs/${runId}`);
    refresh();
  }

  document.getElementById("btn-history-refresh").onclick = refresh;
  document.getElementById("btn-history-delete").onclick = deleteSelectedRun;
  if (btnSaveRaw) btnSaveRaw.addEventListener("click", saveRawText);
  searchBox.addEventListener("keydown", (e) => { if (e.key === "Enter") search(); });

  TAB_ACTIVATE.history = refresh;

  return { refresh };
})();
