// SPDX-FileCopyrightText: 2026 Maurice Casey
// SPDX-License-Identifier: AGPL-3.0-or-later

/* Live, read-only Tropy browsing and official Developer API note write-back. */
const tropy = {};
[
  "btn-add-tropy", "modal-tropy-add", "tropy-browse-path", "btn-tropy-browse-pick",
  "btn-tropy-browse-load", "tropy-browse-project-info", "tropy-browse-project-name",
  "tropy-browse-loading", "tropy-browse-error", "tropy-browse-error-text",
  "tropy-browse-recent-row", "tropy-browse-recent",
  "tropy-browse-picker", "tropy-browse-lists", "tropy-browse-tags",
  "tropy-browse-item-empty", "tropy-browse-item-list", "btn-tropy-browse-item-select-all",
  "tropy-browse-summary", "tropy-browse-summary-text", "btn-tropy-cancel-browse",
  "btn-tropy-browse-enqueue", "btn-send-tropy", "modal-tropy-send",
  "tropy-export-stat-items", "tropy-export-stat-photos", "tropy-export-stat-transcriptions",
  "tropy-export-stage", "tropy-writeback-preview", "btn-send-tropy-close-writeback",
  "btn-writeback-preview", "btn-writeback-commit",
].forEach((id) => { tropy[id] = document.getElementById(id); });

let project = null;
let lists = [];
let tags = [];
let visibleItems = [];
let selected = new Map();
let filter = null;
let sendContext = null;
let notePreview = null;
let browserReturnFocus = null;
let sendReturnFocus = null;

function notify(kind, message) {
  if (!window.ArtificeToast) return;
  if (kind === "error") window.ArtificeToast.error(message);
  else if (kind === "warning") window.ArtificeToast.show(message, "warning");
  else window.ArtificeToast.success(message);
}

function setupProjectPickers() {
  const input = tropy["tropy-browse-path"];
  tropy["tropy-browse-recent"].onchange = () => {
    if (!tropy["tropy-browse-recent"].value) return;
    input.value = tropy["tropy-browse-recent"].value;
    loadProject();
  };
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    loadProject();
  });
}

function resetBrowser() {
  project = null;
  lists = [];
  tags = [];
  visibleItems = [];
  selected = new Map();
  filter = null;
  ["tropy-browse-project-info", "tropy-browse-loading", "tropy-browse-error",
    "tropy-browse-picker", "tropy-browse-summary"].forEach((id) => tropy[id].classList.add("hidden"));
  tropy["btn-tropy-browse-enqueue"].disabled = true;
  tropy["btn-tropy-browse-enqueue"].textContent = "Add selected pages";
  tropy["tropy-browse-path"].removeAttribute("aria-invalid");
  tropy["tropy-browse-path"].disabled = false;
  tropy["btn-tropy-browse-pick"].disabled = false;
  tropy["btn-tropy-browse-load"].disabled = false;
  tropy["btn-tropy-browse-load"].removeAttribute("aria-busy");
}

async function openBrowser() {
  browserReturnFocus = document.activeElement;
  resetBrowser();
  tropy["modal-tropy-add"].classList.remove("hidden");
  try {
    const config = await api("GET", "/api/config");
    if (config.tropy_last_path) tropy["tropy-browse-path"].value = config.tropy_last_path;
  } catch (_) { /* A saved path is optional. */ }
  try {
    const data = await api("GET", "/api/tropy/browse/recent");
    const projects = data.projects || [];
    tropy["tropy-browse-recent"].innerHTML = '<option value="">Choose a recent project…</option>' + projects.map(
      (path) => `<option value="${escapeHtml(path)}">${escapeHtml(path)}</option>`
    ).join("");
    tropy["tropy-browse-recent-row"].classList.toggle("hidden", !projects.length);
  } catch (error) {
    tropy["tropy-browse-recent-row"].classList.add("hidden");
    const disabled = error.message === "Live Tropy browse is not enabled";
    tropy["tropy-browse-error-text"].textContent = disabled
      ? "Enable Tropy project browsing in Settings before adding pages."
      : "Could not load recent Tropy projects: " + error.message;
    tropy["tropy-browse-error"].classList.remove("hidden");
    if (disabled) {
      tropy["tropy-browse-path"].disabled = true;
      tropy["btn-tropy-browse-pick"].disabled = true;
      tropy["btn-tropy-browse-load"].disabled = true;
    }
  }
  requestAnimationFrame(() => {
    const target = tropy["tropy-browse-path"].disabled
      ? tropy["modal-tropy-add"].querySelector("[data-modal-close]")
      : tropy["tropy-browse-path"];
    target.focus();
  });
}

async function pickProject(endpoint, body) {
  try {
    const data = await api("POST", endpoint, body);
    if (data.state === "selected" && data.paths?.length) {
      tropy["tropy-browse-path"].value = data.paths[0];
      return true;
    } else if (data.state === "unavailable") {
      notify("warning", data.reason || "Project picker unavailable");
    }
  } catch (error) {
    notify("error", "Could not open the project picker: " + error.message);
  }
  return false;
}

async function loadProject() {
  const path = tropy["tropy-browse-path"].value.trim();
  if (!path) {
    tropy["tropy-browse-path"].setAttribute("aria-invalid", "true");
    tropy["tropy-browse-error-text"].textContent = "Choose a .tropy project folder first.";
    tropy["tropy-browse-error"].classList.remove("hidden");
    tropy["tropy-browse-path"].focus();
    return;
  }
  resetBrowser();
  tropy["tropy-browse-loading"].classList.remove("hidden");
  tropy["btn-tropy-browse-load"].disabled = true;
  tropy["btn-tropy-browse-load"].setAttribute("aria-busy", "true");
  tropy["btn-tropy-browse-load"].textContent = "Opening…";
  try {
    const data = await api("POST", "/api/tropy/browse/projects", { path });
    const details = data.projects?.[0];
    if (!details) throw new Error("No Tropy project was found at that location");
    project = { ...details, path };
    tropy["tropy-browse-project-name"].textContent = details.name || path;
    tropy["tropy-browse-project-info"].classList.remove("hidden");
    await api("POST", "/api/config", { tropy_last_path: path });
    const [listData, tagData] = await Promise.all([
      api("POST", "/api/tropy/browse/lists", { path }),
      api("POST", "/api/tropy/browse/tags", { path }),
    ]);
    lists = listData.lists || [];
    tags = tagData.tags || [];
    renderSources();
    await loadItems();
    tropy["tropy-browse-picker"].classList.remove("hidden");
  } catch (error) {
    tropy["tropy-browse-path"].setAttribute("aria-invalid", "true");
    tropy["tropy-browse-error-text"].textContent = error.message;
    tropy["tropy-browse-error"].classList.remove("hidden");
  } finally {
    tropy["tropy-browse-loading"].classList.add("hidden");
    tropy["btn-tropy-browse-load"].disabled = false;
    tropy["btn-tropy-browse-load"].removeAttribute("aria-busy");
    tropy["btn-tropy-browse-load"].textContent = "Open project";
  }
}

function renderSources() {
  const listContainer = tropy["tropy-browse-lists"];
  function tree(parentId) {
    return lists.filter((entry) => entry.parent_list_id === parentId).map((entry) =>
      '<div class="tropy-browse-list-node">' +
      `<button type="button" class="tropy-browse-list-link" aria-pressed="false" data-list-id="${entry.list_id}">${escapeHtml(entry.name || "")}</button>` +
      tree(entry.list_id) + "</div>"
    ).join("");
  }
  listContainer.innerHTML = '<button type="button" class="tropy-browse-list-link active" aria-pressed="true" data-list-id="all"><strong>All items</strong></button>' + tree(0);
  listContainer.querySelectorAll(".tropy-browse-list-link").forEach((element) => {
    element.onclick = () => {
      setActiveSource(element);
      filter = element.dataset.listId === "all" ? null : { list_id: Number(element.dataset.listId) };
      loadItems();
    };
  });
  const tagContainer = tropy["tropy-browse-tags"];
  tagContainer.innerHTML = tags.map((tag) =>
    `<button type="button" class="tropy-browse-tag-link" aria-pressed="false" data-tag="${escapeHtml(tag.name)}">${escapeHtml(tag.name)}</button>`
  ).join("") || '<span class="dim tropy-source-empty">No tags</span>';
  tagContainer.querySelectorAll(".tropy-browse-tag-link").forEach((element) => {
    element.onclick = () => { setActiveSource(element); filter = { tag: element.dataset.tag }; loadItems(); };
  });
}

function setActiveSource(activeElement) {
  tropy["tropy-browse-picker"].querySelectorAll(".tropy-browse-list-link, .tropy-browse-tag-link").forEach((element) => {
    const active = element === activeElement;
    element.classList.toggle("active", active);
    element.setAttribute("aria-pressed", String(active));
  });
}

async function loadItems() {
  const params = new URLSearchParams();
  if (filter?.list_id !== undefined) params.set("list_id", filter.list_id);
  if (filter?.tag !== undefined) params.set("tag", filter.tag);
  try {
    const data = await api("POST", "/api/tropy/browse/items" + (params.size ? "?" + params : ""), { path: project.path });
    visibleItems = data.items || [];
    renderItems();
  } catch (error) {
    notify("error", error.message);
  }
}

function renderItems() {
  const allSelected = visibleItems.length > 0 && visibleItems.every((item) => selected.has(item.item_id));
  tropy["tropy-browse-item-empty"].style.display = visibleItems.length ? "none" : "";
  tropy["btn-tropy-browse-item-select-all"].disabled = !visibleItems.length;
  tropy["btn-tropy-browse-item-select-all"].textContent = allSelected ? "Deselect all" : "Select all";
  tropy["tropy-browse-item-list"].innerHTML = visibleItems.map((item) => {
    const missing = item.missing_count ? `<span class="tropy-result-missing-badge">${item.missing_count} missing</span>` : "";
    const photos = `${item.photo_count} ${item.photo_count === 1 ? "photo" : "photos"}`;
    return `<label class="tropy-browse-item-row"><input type="checkbox" class="tropy-browse-item-check" ` +
      `data-item-id="${item.item_id}" ${selected.has(item.item_id) ? "checked" : ""}>` +
      `<span class="item-title">${escapeHtml(item.title || "Untitled item")}</span><span class="item-meta">${photos}</span>${missing}</label>`;
  }).join("");
  tropy["tropy-browse-item-list"].querySelectorAll(".tropy-browse-item-check").forEach((checkbox) => {
    checkbox.onchange = () => {
      const id = Number(checkbox.dataset.itemId);
      if (checkbox.checked) selected.set(id, true); else selected.delete(id);
      updateSummary();
    };
  });
  updateSummary();
}

function updateSummary() {
  let missing = 0;
  let total = 0;
  visibleItems.forEach((item) => {
    if (selected.has(item.item_id)) {
      missing += item.missing_count || 0;
      total += item.photo_count || 0;
    }
  });
  let text = `${selected.size} ${selected.size === 1 ? "item" : "items"} selected`;
  if (missing) text += ` — ${missing} of ${total} ${total === 1 ? "page is" : "pages are"} unavailable`;
  tropy["tropy-browse-summary-text"].textContent = text;
  tropy["tropy-browse-summary-text"].classList.toggle("warning", missing > 0);
  tropy["tropy-browse-summary"].classList.toggle("hidden", selected.size === 0);
  tropy["btn-tropy-browse-enqueue"].disabled = selected.size === 0;
}

async function enqueueSelection() {
  const button = tropy["btn-tropy-browse-enqueue"];
  button.disabled = true;
  button.textContent = "Adding…";
  button.setAttribute("aria-busy", "true");
  try {
    const data = await api("POST", "/api/tropy/browse/enqueue", {
      path: project.path,
      output_dir: document.getElementById("output-dir")?.value || "output",
      item_ids: [...selected.keys()],
    });
    setQueue(data.items);
    tropy["modal-tropy-add"].classList.add("hidden");
    const suffix = data.missing ? `; ${data.missing} of ${data.total} page(s) unavailable` : "";
    notify(data.missing ? "warning" : "success", `Added ${data.added} page(s) from Tropy${suffix}`);
  } catch (error) {
    notify("error", "Could not add Tropy pages: " + error.message);
    button.disabled = false;
  } finally {
    button.textContent = "Add selected pages";
    button.removeAttribute("aria-busy");
  }
}

function sendBody() {
  return {
    source: sendContext?.isHistory ? "history" : "queue",
    item_ids: sendContext?.itemIds || null,
    stage: tropy["tropy-export-stage"].value,
  };
}

function hasUnsavedText() {
  const editor = sendContext?.isHistory ? window.HistoryTab : window.PreviewTab;
  return Boolean(editor?.hasUnsavedEdits?.(tropy["tropy-export-stage"].value));
}

function showNoteStatus(message, state = "default") {
  const target = tropy["tropy-writeback-preview"];
  target.textContent = message;
  target.classList.remove("hidden");
  target.classList.toggle("error", state === "error");
  target.classList.toggle("success", state === "success");
}

async function previewNotes() {
  notePreview = null;
  tropy["btn-writeback-commit"].disabled = true;
  if (hasUnsavedText()) return showNoteStatus("Save the current edits before sending this text to Tropy.", "error");
  showNoteStatus("Checking the open Tropy project…");
  tropy["btn-writeback-preview"].disabled = true;
  tropy["btn-writeback-preview"].setAttribute("aria-busy", "true");
  try {
    const data = await api("POST", "/api/tropy/notes/preview", sendBody());
    notePreview = data;
    const count = data.counts || {};
    tropy["tropy-export-stat-items"].textContent = String(count.selected || 0);
    tropy["tropy-export-stat-photos"].textContent = String((count.ready || 0) + (count.duplicate || 0));
    tropy["tropy-export-stat-transcriptions"].textContent = String(count.ready || 0);
    const blockers = data.blockers || [];
    const message = `${count.ready || 0} ready · ${count.duplicate || 0} duplicate · ${count.empty || 0} empty · ${(count.foreign || 0) + (count.ineligible || 0)} blocked` +
      (blockers.length ? "\n" + blockers.join("\n") : "");
    showNoteStatus(message, blockers.length > 0 ? "error" : "success");
    tropy["btn-writeback-commit"].disabled = blockers.length > 0 || data.write_count < 1;
    tropy["btn-writeback-commit"].textContent = `Add ${data.write_count || 0} note${data.write_count === 1 ? "" : "s"}`;
  } catch (error) {
    showNoteStatus("Could not check Tropy: " + error.message, "error");
  } finally {
    tropy["btn-writeback-preview"].disabled = false;
    tropy["btn-writeback-preview"].removeAttribute("aria-busy");
  }
}

async function commitNotes() {
  if (!notePreview || hasUnsavedText()) return previewNotes();
  tropy["btn-writeback-preview"].disabled = true;
  tropy["btn-writeback-commit"].disabled = true;
  tropy["btn-writeback-commit"].setAttribute("aria-busy", "true");
  showNoteStatus("Adding notes to Tropy…");
  try {
    const data = await api("POST", "/api/tropy/notes/commit", {
      ...sendBody(), expected_write_count: notePreview.write_count,
    });
    const blocked = data.remaining || data.errors?.length || 0;
    const errors = data.errors?.length ? "\n" + data.errors.map((entry) => `${entry.label}: ${entry.message}`).join("\n") : "";
    showNoteStatus(`${data.written} added · ${data.skipped} duplicates skipped · ${blocked} blocked${errors}`, data.status === "partial" ? "error" : "success");
    notify(data.status === "partial" ? "warning" : "success", `${data.written} note(s) added to Tropy`);
    notePreview = null;
  } catch (error) {
    showNoteStatus("Could not add notes: " + error.message + "\nCheck again before retrying.", "error");
  } finally {
    tropy["btn-writeback-preview"].disabled = false;
    tropy["btn-writeback-commit"].removeAttribute("aria-busy");
  }
}

async function openTropyExport(context) {
  sendReturnFocus = document.activeElement;
  sendContext = context || null;
  notePreview = null;
  ["tropy-export-stat-items", "tropy-export-stat-photos", "tropy-export-stat-transcriptions"].forEach((id) => {
    tropy[id].textContent = "0";
  });
  tropy["modal-tropy-send"].classList.remove("hidden");
  tropy["tropy-writeback-preview"].classList.add("hidden");
  requestAnimationFrame(() => tropy["tropy-export-stage"].focus());
  await previewNotes();
}

function closeSend() {
  tropy["modal-tropy-send"].classList.add("hidden");
  sendContext = null;
  notePreview = null;
  sendReturnFocus?.focus?.();
}

function closeBrowser() {
  tropy["modal-tropy-add"].classList.add("hidden");
  browserReturnFocus?.focus?.();
}

setupProjectPickers();
tropy["btn-add-tropy"].onclick = openBrowser;
tropy["btn-tropy-browse-pick"].onclick = async () => {
  if (await pickProject("/api/native/pick-folder", {})) await loadProject();
};
tropy["btn-tropy-browse-load"].onclick = loadProject;
tropy["btn-tropy-browse-item-select-all"].onclick = () => {
  const all = visibleItems.length && visibleItems.every((item) => selected.has(item.item_id));
  visibleItems.forEach((item) => all ? selected.delete(item.item_id) : selected.set(item.item_id, true));
  renderItems();
};
tropy["btn-tropy-browse-enqueue"].onclick = enqueueSelection;
tropy["btn-tropy-cancel-browse"].onclick = closeBrowser;
tropy["modal-tropy-add"].querySelector("[data-modal-close]").onclick = closeBrowser;
tropy["btn-send-tropy"].onclick = () => openTropyExport({ isHistory: false });
tropy["btn-send-tropy-close-writeback"].onclick = closeSend;
tropy["modal-tropy-send"].querySelector("[data-modal-close]").onclick = closeSend;
tropy["btn-writeback-preview"].onclick = previewNotes;
tropy["btn-writeback-commit"].onclick = commitNotes;
tropy["tropy-export-stage"].onchange = previewNotes;
tropy["modal-tropy-add"].addEventListener("click", (event) => {
  if (event.target === tropy["modal-tropy-add"]) closeBrowser();
});
tropy["modal-tropy-send"].addEventListener("click", (event) => {
  if (event.target === tropy["modal-tropy-send"]) closeSend();
});
document.addEventListener("keydown", (event) => {
  const openModal = [tropy["modal-tropy-send"], tropy["modal-tropy-add"]].find((modal) => !modal.classList.contains("hidden"));
  if (!openModal) return;
  if (event.key === "Escape") {
    event.preventDefault();
    openModal === tropy["modal-tropy-send"] ? closeSend() : closeBrowser();
    return;
  }
  if (event.key !== "Tab") return;
  const focusable = [...openModal.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])')];
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}, { capture: true });
window.openTropyExport = openTropyExport;
