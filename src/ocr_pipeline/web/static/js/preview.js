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

  function refreshList(keepSelection) {
    const prev = keepSelection ? select.value : null;
    const eligible = [...items.values()].filter(i => i.state !== "pending");
    select.innerHTML = eligible.length
      ? eligible.map(i => `<option value="${i.id}">${escapeHtml(i.name)}</option>`).join("")
      : `<option value="">No documents yet</option>`;
    if (prev && eligible.some(i => i.id === prev)) select.value = prev;
  }

  async function open(id) {
    refreshList(false);
    select.value = id;

    try {
      const data = await api("GET", `/api/queue/${id}/preview`);
      renderCompare(container, data);
    } catch (err) {
      clearCompare(container);
      container.querySelector(".compare-title").textContent = `Could not load: ${err.message}`;
    }

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
