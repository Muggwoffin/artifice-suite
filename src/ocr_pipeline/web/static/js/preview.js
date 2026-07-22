/*
 * Preview tab: Raw / Cleaned / Translated for one in-memory queue item.
 * Populated either by clicking a queue row's view arrow, by picking from the
 * dropdown here, or automatically as items finish while this tab is open
 * (wired from app.js's SSE handler, mirroring the desktop build's
 * `App.preview_item` auto-follow behaviour).
 */

const PreviewTab = (function () {
  const container = document.getElementById("panel-preview");
  const select = document.getElementById("preview-item-select");
  const btnSaveRaw = document.getElementById("btn-save-raw");

  let currentItemId = null;
  let originalRawText = "";

  function refreshList(keepSelection) {
    const prev = keepSelection ? select.value : null;
    const eligible = [...items.values()].filter(i => i.state !== "pending");
    select.innerHTML = eligible.length
      ? eligible.map(i => `<option value="${i.id}">${escapeHtml(i.name)}</option>`).join("")
      : `<option value="">No documents yet</option>`;
    if (prev && eligible.some(i => i.id === prev)) select.value = prev;
  }

  function getRawTextarea() {
    return container.querySelector('.compare-pane[data-pane="raw"] textarea.raw-edit');
  }

  // Re-run after every render (renderCompare rebuilds the textarea element
  // each time) so the dirty flag and Ctrl+S shortcut stay attached to
  // whichever textarea is currently in the DOM.
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

  // Not autosaved on every keystroke — a scan-correction session is a
  // deliberate, occasional action, not a live-typing document, so saving
  // only happens on the button click or Ctrl+S.
  async function saveRawText() {
    const textarea = getRawTextarea();
    if (!textarea || !currentItemId || !btnSaveRaw) return;
    btnSaveRaw.disabled = true;
    const label = btnSaveRaw.textContent;
    btnSaveRaw.textContent = "Saving…";
    try {
      const data = await api("POST", `/api/queue/${currentItemId}/raw-text`, { text: textarea.value });
      renderCompare(container, data, { editableRaw: true });
      wireRawEditing();
      log("Raw OCR text corrected and saved.", "accent");
    } catch (err) {
      log(`Could not save correction: ${err.message}`, "error");
      btnSaveRaw.disabled = false;
    } finally {
      btnSaveRaw.textContent = label;
    }
  }

  if (btnSaveRaw) btnSaveRaw.addEventListener("click", saveRawText);

  async function open(id) {
    refreshList(false);
    select.value = id;
    currentItemId = id;

    try {
      const data = await api("GET", `/api/queue/${id}/preview`);
      renderCompare(container, data, { editableRaw: true });
      wireRawEditing();
    } catch (err) {
      clearCompare(container);
      container.querySelector(".compare-title").textContent = `Could not load: ${err.message}`;
      if (btnSaveRaw) btnSaveRaw.disabled = true;
    }

    if (window.PreviewImage) window.PreviewImage.load(`/api/queue/${id}/image`);

    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    document.querySelector('.tab[data-tab="preview"]').classList.add("active");
    container.classList.add("active");
  }

  select.addEventListener("change", () => { if (select.value) open(select.value); });

  TAB_ACTIVATE.preview = () => refreshList(true);

  return { open };
})();

window.PreviewTab = PreviewTab;
