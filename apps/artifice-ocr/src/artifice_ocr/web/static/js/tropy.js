// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * Tropy JSON-LD bridge: import modal ("Import from Tropy") and export modal
 * ("Export to Tropy"). All old SQLite-based browse/preview/write machinery
 * is deleted. The bridge works with JSON-LD files only.
 *
 * Loaded after app.js — reuses api(), escapeHtml(), and the shared toast
 * (window.ArtificeToast) from /shared/toast.js.
 */

const tropyEls = {};
[
  // Import modal
  "btn-add-tropy", "modal-tropy-add",
  "tropy-dropzone",
  "tropy-dropzone-idle", "tropy-dropzone-parsing",
  "tropy-dropzone-success", "tropy-dropzone-error",
  "tropy-dropzone-success-text", "tropy-dropzone-error-text",
  "tropy-dropzone-live",
  "tropy-import-path", "btn-tropy-browse-file",
  "tropy-import-results", "tropy-import-count",
  "tropy-import-list", "btn-tropy-import-select-all",
  "tropy-import-summary-text", "tropy-import-summary-warning",
  "btn-tropy-cancel", "btn-tropy-add-queue",
  // Browse-project mode
  "tropy-tab-jsonld", "tropy-tab-browse",
  "tropy-mode-jsonld", "tropy-mode-browse",
  "tropy-browse-path", "btn-tropy-browse-pick", "btn-tropy-browse-load",
  "tropy-browse-project-info", "tropy-browse-project-name",
  "tropy-browse-loading", "tropy-browse-error", "tropy-browse-error-text",
  "tropy-browse-picker", "tropy-browse-source-pane",
  "tropy-browse-lists", "tropy-browse-tags",
  "tropy-browse-item-pane", "tropy-browse-item-empty", "tropy-browse-item-list",
  "tropy-browse-summary", "tropy-browse-summary-text",
  "tropy-footer-jsonld", "tropy-footer-browse",
  "btn-tropy-cancel-browse", "btn-tropy-browse-enqueue",
  // Export modal
  "btn-send-tropy", "modal-tropy-send",
  "tropy-export-stat-items", "tropy-export-stat-photos",
  "tropy-export-stat-transcriptions",
  "tropy-export-stage", "tropy-export-loading",
  "tropy-export-loading-text", "tropy-export-status",
  "btn-send-tropy-close", "btn-send-tropy-write",
].forEach(id => {
  tropyEls[id] = document.getElementById(id);
});

let tropyImportPreview = null;  // { export_name, items, warnings }
let tropyImportSource = null;   // { type: "path" | "content", value: string, name?: string }
let tropyExportContext = null;  // { itemIds, isHistory }

// Browse-project state
let tropyBrowseActive = false;   // current mode: false=jsonld, true=browse
let tropyBrowseProject = null;   // { path, project_id, name }
let tropyBrowseLists = [];       // flat list rows from /browse/lists
let tropyBrowseTags = [];        // flat tag rows from /browse/tags
let tropyBrowseItems = [];      // items from /browse/items for current filter
let tropyBrowseSelected = new Map(); // item_id -> true for checked items
let tropyBrowseFilter = null;    // { list_id?, tag? } current filter

// ------------------------------------------------------------- import modal

async function openTropyAdd() {
  tropyEls["modal-tropy-add"].classList.remove("hidden");
  resetImportState();
  // Restore last-used Tropy import path
  try {
    const cfg = await api("GET", "/api/config");
    if (cfg.tropy_last_path) {
      tropyEls["tropy-import-path"].value = cfg.tropy_last_path;
    }
    // Show or hide the browse-project tab based on the setting
    if (tropyEls["tropy-tab-browse"]) {
      if (cfg.tropy_live_browse_enabled) {
        tropyEls["tropy-tab-browse"].style.display = "";
      } else {
        tropyEls["tropy-tab-browse"].style.display = "none";
      }
    }
  } catch { /* settings are optional */ }
}

function resetImportState() {
  tropyImportPreview = null;
  tropyImportSource = null;
  tropyEls["tropy-import-path"].value = "";
  showDropzoneState("idle");
  tropyEls["tropy-import-results"].classList.add("hidden");
  tropyEls["tropy-import-list"].innerHTML = "";
  tropyEls["tropy-import-count"].textContent = "0 items found";
  tropyEls["tropy-import-summary-text"].textContent = "No file selected";
  tropyEls["tropy-import-summary-warning"].textContent = "";
  tropyEls["btn-tropy-add-queue"].disabled = true;
  tropyEls["btn-tropy-add-queue"].textContent = "Add to Queue";
  // Reset browse mode
  tropyBrowseProject = null;
  tropyBrowseLists = [];
  tropyBrowseTags = [];
  tropyBrowseItems = [];
  tropyBrowseSelected = new Map();
  tropyBrowseFilter = null;
  if (tropyEls["tropy-browse-path"]) tropyEls["tropy-browse-path"].value = "";
  if (tropyEls["tropy-browse-project-info"]) tropyEls["tropy-browse-project-info"].classList.add("hidden");
  if (tropyEls["tropy-browse-loading"]) tropyEls["tropy-browse-loading"].classList.add("hidden");
  if (tropyEls["tropy-browse-error"]) tropyEls["tropy-browse-error"].classList.add("hidden");
  if (tropyEls["tropy-browse-picker"]) tropyEls["tropy-browse-picker"].classList.add("hidden");
  if (tropyEls["tropy-browse-summary"]) tropyEls["tropy-browse-summary"].classList.add("hidden");
  if (tropyEls["tropy-browse-item-list"]) tropyEls["tropy-browse-item-list"].innerHTML = "";
  if (tropyEls["tropy-browse-lists"]) tropyEls["tropy-browse-lists"].innerHTML = '<span class="dim" style="padding:0.35rem 0.7rem;display:block;">No lists</span>';
  if (tropyEls["tropy-browse-tags"]) tropyEls["tropy-browse-tags"].innerHTML = "";
  if (tropyEls["tropy-browse-item-empty"]) {
    tropyEls["tropy-browse-item-empty"].style.display = "";
  }
  if (tropyEls["btn-tropy-browse-enqueue"]) {
    tropyEls["btn-tropy-browse-enqueue"].disabled = true;
    tropyEls["btn-tropy-browse-enqueue"].textContent = "Add to Queue";
  }
}

function showDropzoneState(state, message) {
  const states = ["idle", "parsing", "success", "error"];
  states.forEach(s => {
    const el = tropyEls["tropy-dropzone-" + s];
    if (el) el.classList.toggle("hidden", s !== state);
  });
  if (state === "success" && tropyEls["tropy-dropzone-success-text"]) {
    tropyEls["tropy-dropzone-success-text"].textContent = message || "Ready to import";
  }
  if (state === "error" && tropyEls["tropy-dropzone-error-text"]) {
    tropyEls["tropy-dropzone-error-text"].textContent = message || "Import failed";
  }
  if (tropyEls["tropy-dropzone-live"]) {
    const liveMsg = state === "idle"
      ? "Drop a Tropy JSON-LD file here, or press Enter to browse"
      : (message || state);
    tropyEls["tropy-dropzone-live"].textContent = liveMsg;
  }
}

async function loadImportPreview(opts) {
  if (!opts || (!opts.path && !opts.content)) return;
  resetImportState();

  tropyImportSource = opts.path
    ? { type: "path", value: opts.path }
    : { type: "content", value: opts.content, name: opts.name || "" };

  if (opts.path) {
    tropyEls["tropy-import-path"].value = opts.path;
  } else if (opts.name) {
    tropyEls["tropy-import-path"].value = opts.name;
  }

  showDropzoneState("parsing");

  try {
    const payload = opts.path ? { path: opts.path } : { content: opts.content };
    const data = await api("POST", "/api/tropy/import/preview", payload);
    tropyImportPreview = data;
    const photoCount = (data.items || []).reduce((sum, it) => sum + (it.photo_count || 0), 0);
    showDropzoneState("success", `${data.items.length} item(s), ${photoCount} photo(s) ready`);
    renderImportResults(data);
  } catch (err) {
    tropyImportPreview = null;
    tropyImportSource = null;
    showDropzoneState("error", escapeHtml(err.message));
    tropyEls["tropy-import-summary-text"].textContent = "Error: " + escapeHtml(err.message);
  }
}

function renderImportResults(data) {
  const items = data.items || [];
  tropyEls["tropy-import-results"].classList.remove("hidden");
  tropyEls["tropy-import-count"].textContent =
    `${items.length} item(s) found`;

  const frag = document.createDocumentFragment();
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "tropy-result-row";
    const missingBadge = item.missing_count > 0
      ? ` <span class="tropy-result-missing" data-missing="${item.missing_count}" title="${item.missing_count} photo(s) not found on disk">${item.missing_count} missing</span>`
      : "";
    row.innerHTML = `
      <input type="checkbox" class="tropy-result-check" data-group="${escapeHtml(item.group)}" checked>
      <span class="tropy-result-title">${escapeHtml(item.title)}</span>
      <span class="tropy-result-meta">${item.photo_count} photo(s)${missingBadge}</span>`;
    row.addEventListener("click", (e) => {
      if (e.target.tagName !== "INPUT" && !e.target.closest(".tropy-result-missing")) {
        const cb = row.querySelector("input[type=checkbox]");
        cb.checked = !cb.checked;
        updateImportSummary();
      }
    });
    row.querySelector("input[type=checkbox]").addEventListener("change", updateImportSummary);
    // Missing badge tooltip toggle
    const badge = row.querySelector(".tropy-result-missing");
    if (badge) {
      badge.addEventListener("click", (e) => {
        e.stopPropagation();
        const existing = row.querySelector(".tropy-missing-tooltip");
        if (existing) {
          existing.remove();
          return;
        }
        const tip = document.createElement("div");
        tip.className = "tropy-missing-tooltip dim";
        tip.textContent = `${badge.dataset.missing} photo(s) not found on disk`;
        row.appendChild(tip);
        // Auto-dismiss after 5 seconds
        setTimeout(() => { if (tip.parentNode) tip.remove(); }, 5000);
      });
    }
    frag.appendChild(row);
  }

  tropyEls["tropy-import-list"].innerHTML = "";
  tropyEls["tropy-import-list"].appendChild(frag);
  updateImportSummary();

  if (items.length > 0) {
    tropyEls["btn-tropy-add-queue"].disabled = false;
  }

  // Render warnings below the list
  renderTropyWarnings(data.warnings);
}

function updateImportSummary() {
  const checks = tropyEls["tropy-import-list"].querySelectorAll(".tropy-result-check");
  const selected = Array.from(checks).filter(cb => cb.checked);
  const totalPhotos = selected.reduce((sum, cb) => {
    const row = cb.closest(".tropy-result-row");
    const meta = row.querySelector(".tropy-result-meta");
    const match = meta && meta.textContent.match(/(\d+)/);
    return sum + (match ? parseInt(match[1], 10) : 0);
  }, 0);

  tropyEls["tropy-import-summary-text"].textContent =
    selected.length > 0
      ? `${selected.length} of ${checks.length} item(s) — ${totalPhotos} photo(s)`
      : "No items selected";
  tropyEls["btn-tropy-add-queue"].disabled = selected.length === 0;
}

function renderTropyWarnings(warnings) {
  // Remove any existing warnings section
  const existing = tropyEls["tropy-import-results"].querySelector(".tropy-warnings");
  if (existing) existing.remove();

  if (!warnings || !warnings.length) return;

  const section = document.createElement("div");
  section.className = "tropy-warnings dim";
  for (const warning of warnings) {
    const line = document.createElement("div");
    line.className = "tropy-warning-line";
    line.textContent = "\u26A0 " + warning;
    section.appendChild(line);
  }
  tropyEls["tropy-import-results"].appendChild(section);
}

// Events
tropyEls["btn-add-tropy"].onclick = openTropyAdd;

tropyEls["modal-tropy-add"].querySelector("[data-modal-close]")?.addEventListener("click", () => {
  tropyEls["modal-tropy-add"].classList.add("hidden");
});

tropyEls["btn-tropy-cancel"].onclick = () => {
  tropyEls["modal-tropy-add"].classList.add("hidden");
};

tropyEls["modal-tropy-add"].addEventListener("click", (e) => {
  if (e.target === tropyEls["modal-tropy-add"]) {
    tropyEls["modal-tropy-add"].classList.add("hidden");
  }
});

async function browseTropyFile() {
  try {
    const res = await fetch("/api/native/pick-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preset: "json" }),
    });
    const data = await res.json();
    if (data.path) {
      loadImportPreview({ path: data.path });
    }
  } catch (err) {
    if (window.ArtificeToast)
      window.ArtificeToast.error("File picker not available — type the path instead.");
  }
}

tropyEls["btn-tropy-browse-file"].onclick = browseTropyFile;

// Dropzone click / keyboard activation triggers the same file picker
tropyEls["tropy-dropzone"].onclick = browseTropyFile;
tropyEls["tropy-dropzone"].addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    browseTropyFile();
  }
});

// Drag-and-drop handling for the dropzone
let tropyDragCounter = 0;

["dragenter", "dragover"].forEach(evt => {
  tropyEls["tropy-dropzone"].addEventListener(evt, (e) => {
    e.preventDefault();
    if (evt === "dragenter") tropyDragCounter++;
    tropyEls["tropy-dropzone"].classList.add("dragover");
  });
});

tropyEls["tropy-dropzone"].addEventListener("dragleave", (e) => {
  e.preventDefault();
  tropyDragCounter--;
  if (tropyDragCounter <= 0) {
    tropyDragCounter = 0;
    tropyEls["tropy-dropzone"].classList.remove("dragover");
  }
});

tropyEls["tropy-dropzone"].addEventListener("drop", (e) => {
  e.preventDefault();
  tropyDragCounter = 0;
  tropyEls["tropy-dropzone"].classList.remove("dragover");
  const files = e.dataTransfer && e.dataTransfer.files;
  if (!files || !files.length) return;
  const file = Array.from(files).find(isTropyFile) || files[0];
  handleTropyDroppedFile(file);
});

function isTropyFile(file) {
  const name = (file.name || "").toLowerCase();
  return name.endsWith(".json") || name.endsWith(".jsonld");
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Could not read the dropped file"));
    reader.readAsText(file);
  });
}

function countPhotosInTropyItem(item) {
  if (!item || typeof item !== "object") return 0;
  const photoKeys = ["photo", "photos", "http://schema.org/photo", "https://schema.org/photo"];
  for (const key of photoKeys) {
    const val = item[key];
    if (Array.isArray(val)) return val.length;
    if (val && typeof val === "object") return 1;
  }
  for (const key of Object.keys(item)) {
    if (key.toLowerCase().indexOf("photo") !== -1 && Array.isArray(item[key])) {
      return item[key].length;
    }
  }
  return 0;
}

function quickCountTropyExport(json) {
  let itemCount = 0;
  let photoCount = 0;
  if (json && Array.isArray(json["@graph"])) {
    itemCount = json["@graph"].length;
    for (const item of json["@graph"]) {
      photoCount += countPhotosInTropyItem(item);
    }
  } else if (Array.isArray(json)) {
    itemCount = json.length;
    for (const item of json) {
      photoCount += countPhotosInTropyItem(item);
    }
  }
  return { itemCount, photoCount };
}

async function handleTropyDroppedFile(file) {
  if (!isTropyFile(file)) {
    showDropzoneState("error", "Please drop a .json or .jsonld Tropy export file.");
    return;
  }

  resetImportState();
  tropyEls["tropy-import-path"].value = file.name;
  showDropzoneState("parsing");

  let content;
  let parsed;
  try {
    content = await readFileAsText(file);
    parsed = JSON.parse(content);
  } catch (err) {
    showDropzoneState("error", "Could not parse the file as JSON: " + err.message);
    return;
  }

  const quick = quickCountTropyExport(parsed);
  showDropzoneState("success", `Found ${quick.itemCount} item(s), ${quick.photoCount} photo(s)`);

  // Send the full content to the backend for validation and item details
  try {
    const data = await api("POST", "/api/tropy/import/preview", { content });
    tropyImportPreview = data;
    tropyImportSource = { type: "content", value: content, name: file.name };
    const photoCount = (data.items || []).reduce((sum, it) => sum + (it.photo_count || 0), 0);
    showDropzoneState("success", `${data.items.length} item(s), ${photoCount} photo(s) ready`);
    renderImportResults(data);
  } catch (err) {
    tropyImportPreview = null;
    tropyImportSource = null;
    showDropzoneState("error", escapeHtml(err.message));
    tropyEls["tropy-import-summary-text"].textContent = "Error: " + escapeHtml(err.message);
  }
}

// Re-load on manual path change (if user pastes into the status field)
tropyEls["tropy-import-path"].addEventListener("change", () => {
  loadImportPreview({ path: tropyEls["tropy-import-path"].value });
});

// Select all / none toggle
let allSelected = true;
tropyEls["btn-tropy-import-select-all"].onclick = () => {
  allSelected = !allSelected;
  const checks = tropyEls["tropy-import-list"].querySelectorAll(".tropy-result-check");
  checks.forEach(cb => { cb.checked = allSelected; });
  tropyEls["btn-tropy-import-select-all"].textContent = allSelected ? "Select all" : "Deselect all";
  updateImportSummary();
};

tropyEls["btn-tropy-add-queue"].onclick = async () => {
  const checks = tropyEls["tropy-import-list"].querySelectorAll(".tropy-result-check:checked");
  const groups = Array.from(checks).map(cb => cb.dataset.group);
  if (!groups.length) return;

  if (!tropyImportSource) {
    if (window.ArtificeToast) window.ArtificeToast.error("No Tropy export loaded");
    return;
  }

  const outputDir = document.getElementById("output-dir")
    ? document.getElementById("output-dir").value || "output"
    : "output";

  const body = { groups, output_dir: outputDir };
  if (tropyImportSource.type === "path") {
    body.path = tropyImportSource.value;
  } else {
    body.content = tropyImportSource.value;
  }

  tropyEls["btn-tropy-add-queue"].disabled = true;
  tropyEls["btn-tropy-add-queue"].textContent = "Adding…";

  try {
    const data = await api("POST", "/api/tropy/import/add", body);

    let msg = `Imported ${data.added} item(s) from Tropy`;
    if (data.missing && data.missing.length) {
      msg += ` (${data.missing.length} file(s) missing)`;
    }
    if (window.ArtificeToast) window.ArtificeToast.success(msg);
    // Persist last-used Tropy import path
    if (tropyImportSource && tropyImportSource.type === "path" && tropyImportSource.value) {
      api("POST", "/api/config", { tropy_last_path: tropyImportSource.value }).catch(function(err) {
        if (window.ArtificeToast) window.ArtificeToast.error("Could not save import path: " + err.message);
      });
    }
    setQueue(data.items);
    tropyEls["modal-tropy-add"].classList.add("hidden");
  } catch (err) {
    if (window.ArtificeToast) window.ArtificeToast.error(`Import failed: ${err.message}`);
    tropyEls["btn-tropy-add-queue"].disabled = false;
    tropyEls["btn-tropy-add-queue"].textContent = "Add to Queue";
  }
};

function switchTropyMode(mode) {
  tropyBrowseActive = (mode === "browse");
  tropyEls["tropy-tab-jsonld"].classList.toggle("active", mode === "jsonld");
  tropyEls["tropy-tab-jsonld"].setAttribute("aria-selected", mode === "jsonld" ? "true" : "false");
  tropyEls["tropy-tab-browse"].classList.toggle("active", mode === "browse");
  tropyEls["tropy-tab-browse"].setAttribute("aria-selected", mode === "browse" ? "true" : "false");
  tropyEls["tropy-mode-jsonld"].classList.toggle("hidden", mode !== "jsonld");
  tropyEls["tropy-mode-browse"].classList.toggle("hidden", mode !== "browse");
  tropyEls["tropy-footer-jsonld"].classList.toggle("hidden", mode !== "jsonld");
  tropyEls["tropy-footer-browse"].classList.toggle("hidden", mode !== "browse");
}
tropyEls["tropy-tab-jsonld"].onclick = () => switchTropyMode("jsonld");
tropyEls["tropy-tab-browse"].onclick = () => switchTropyMode("browse");

tropyEls["btn-tropy-browse-pick"].onclick = async () => {
  try {
    const res = await fetch("/api/native/pick-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (data.path) tropyEls["tropy-browse-path"].value = data.path;
  } catch (err) {
    if (window.ArtificeToast) window.ArtificeToast.error("File picker not available — type the path instead.");
  }
};

tropyEls["btn-tropy-browse-load"].onclick = async () => {
  const path = tropyEls["tropy-browse-path"].value.trim();
  if (!path) {
    if (window.ArtificeToast) window.ArtificeToast.error("Enter a path to a .tropy project file");
    return;
  }
  tropyEls["tropy-browse-loading"].classList.remove("hidden");
  tropyEls["tropy-browse-error"].classList.add("hidden");
  tropyEls["tropy-browse-project-info"].classList.add("hidden");
  try {
    const data = await window.ArtificeBind.apiFetch("/api/tropy/browse/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const proj = data.projects[0];
    tropyBrowseProject = Object.assign({ path }, proj);
    tropyEls["tropy-browse-project-name"].textContent = proj.name || path;
    tropyEls["tropy-browse-loading"].classList.add("hidden");
    tropyEls["tropy-browse-project-info"].classList.remove("hidden");
    await loadTropyBrowseSources();
    tropyEls["tropy-browse-picker"].classList.remove("hidden");
  } catch (err) {
    tropyEls["tropy-browse-loading"].classList.add("hidden");
    tropyEls["tropy-browse-error"].classList.remove("hidden");
    tropyEls["tropy-browse-error-text"].textContent = err.message;
  }
};

async function loadTropyBrowseSources() {
  const body = JSON.stringify({ path: tropyBrowseProject.path });
  const headers = { "Content-Type": "application/json" };
  const [listsData, tagsData] = await Promise.all([
    window.ArtificeBind.apiFetch("/api/tropy/browse/lists", { method: "POST", headers, body }),
    window.ArtificeBind.apiFetch("/api/tropy/browse/tags", { method: "POST", headers, body }),
  ]);
  tropyBrowseLists = listsData.lists || [];
  tropyBrowseTags = tagsData.tags || [];
  renderTropyBrowseLists();
  renderTropyBrowseTags();
}

function renderTropyBrowseLists() {
  const container = tropyEls["tropy-browse-lists"];
  if (!tropyBrowseLists.length) {
    container.innerHTML = '<span class="dim" style="padding:0.35rem 0.7rem;display:block;">No lists</span>';
    return;
  }
  function buildTree(parentId) {
    return tropyBrowseLists
      .filter(l => l.parent_list_id === parentId)
      .map(l => {
        const children = buildTree(l.list_id);
        return `<div class="tropy-browse-list-node" data-list-id="${l.list_id}" style="padding-left:${parentId === 0 ? 0 : 12}px;">`
          + `<span class="tropy-browse-list-link" data-list-id="${l.list_id}" style="cursor:pointer;">${escapeHtml(l.name || "")}</span>`
          + children
          + `</div>`;
      })
      .join("");
  }
  container.innerHTML = `<div class="tropy-browse-list-node" data-list-id="all" style="padding-bottom:0.3rem;"><span class="tropy-browse-list-link" data-list-id="all" style="cursor:pointer;font-weight:600;">All items</span></div>` + buildTree(0);
  container.querySelectorAll(".tropy-browse-list-link").forEach(el => {
    el.onclick = () => {
      const id = el.dataset.listId;
      tropyBrowseFilter = id === "all" ? null : { list_id: parseInt(id, 10) };
      loadTropyBrowseItems();
    };
  });
}

function renderTropyBrowseTags() {
  const container = tropyEls["tropy-browse-tags"];
  container.innerHTML = tropyBrowseTags.map(t =>
    `<span class="tropy-browse-tag-link" data-tag="${escapeHtml(t.name)}" style="cursor:pointer;display:inline-block;margin:0.15rem 0.3rem 0.15rem 0;">${escapeHtml(t.name)}</span>`
  ).join("");
  container.querySelectorAll(".tropy-browse-tag-link").forEach(el => {
    el.onclick = () => {
      tropyBrowseFilter = { tag: el.dataset.tag };
      loadTropyBrowseItems();
    };
  });
}

async function loadTropyBrowseItems() {
  const params = new URLSearchParams();
  if (tropyBrowseFilter) {
    if (tropyBrowseFilter.list_id !== undefined) params.set("list_id", tropyBrowseFilter.list_id);
    if (tropyBrowseFilter.tag !== undefined) params.set("tag", tropyBrowseFilter.tag);
  }
  const qs = params.toString() ? "?" + params.toString() : "";
  try {
    const data = await window.ArtificeBind.apiFetch("/api/tropy/browse/items" + qs, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: tropyBrowseProject.path }),
    });
    tropyBrowseItems = data.items || [];
    renderTropyBrowseItems();
  } catch (err) {
    if (window.ArtificeToast) window.ArtificeToast.error(err.message);
  }
}

function renderTropyBrowseItems() {
  tropyEls["tropy-browse-item-empty"].style.display = tropyBrowseItems.length ? "none" : "";
  tropyEls["tropy-browse-item-list"].innerHTML = tropyBrowseItems.map(it => {
    const missing = it.missing_count > 0
      ? `<span class="tropy-result-missing-badge">${it.missing_count} missing</span>`
      : "";
    return `<label class="tropy-browse-item-row" style="display:flex;align-items:center;gap:0.5rem;padding:0.3rem 0;">`
      + `<input type="checkbox" class="tropy-browse-item-check" data-item-id="${it.item_id}" ${tropyBrowseSelected.has(it.item_id) ? "checked" : ""}>`
      + `<span>${escapeHtml(it.title || "(untitled)")}</span>`
      + `<span class="dim">${it.photo_count} photo(s)</span>`
      + missing
      + `</label>`;
  }).join("");
  tropyEls["tropy-browse-item-list"].querySelectorAll(".tropy-browse-item-check").forEach(cb => {
    cb.onchange = () => {
      const id = parseInt(cb.dataset.itemId, 10);
      if (cb.checked) tropyBrowseSelected.set(id, true); else tropyBrowseSelected.delete(id);
      tropyEls["tropy-browse-summary-text"].textContent = tropyBrowseSelected.size + " item(s) selected";
      tropyEls["tropy-browse-summary"].classList.toggle("hidden", tropyBrowseSelected.size === 0);
      tropyEls["btn-tropy-browse-enqueue"].disabled = tropyBrowseSelected.size === 0;
    };
  });
}

tropyEls["btn-tropy-browse-enqueue"].onclick = async () => {
  const outputDir = document.getElementById("output-dir")
    ? document.getElementById("output-dir").value || "output"
    : "output";
  tropyEls["btn-tropy-browse-enqueue"].disabled = true;
  tropyEls["btn-tropy-browse-enqueue"].textContent = "Adding…";
  try {
    const data = await window.ArtificeBind.apiFetch("/api/tropy/browse/enqueue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: tropyBrowseProject.path,
        output_dir: outputDir,
        item_ids: Array.from(tropyBrowseSelected.keys()),
      }),
    });
    if (window.ArtificeToast) window.ArtificeToast.success(`Added ${data.added} item(s) from Tropy`);
    setQueue(data.items);
    tropyEls["modal-tropy-add"].classList.add("hidden");
  } catch (err) {
    if (window.ArtificeToast) window.ArtificeToast.error(`Enqueue failed: ${err.message}`);
    tropyEls["btn-tropy-browse-enqueue"].disabled = false;
    tropyEls["btn-tropy-browse-enqueue"].textContent = "Add to Queue";
  }
};

tropyEls["btn-tropy-cancel-browse"].onclick = () => {
  tropyEls["modal-tropy-add"].classList.add("hidden");
};

// ------------------------------------------------------------- export modal

async function openTropyExport(context) {
  tropyExportContext = context || null;
  tropyEls["modal-tropy-send"].classList.remove("hidden");
  tropyEls["tropy-export-status"].textContent = "";
  tropyEls["tropy-export-status"].className = "tropy-export-status dim";
  tropyEls["tropy-export-loading"].classList.add("hidden");

  // Fetch export summary counts
  try {
    if (context && context.isHistory) {
      // History: fetch the item detail to show counts
      const data = await api("GET", `/api/history/items/${context.itemIds[0]}`);
      const hasText = (data.cleaned || data.raw || data.translated) ? 1 : 0;
      tropyEls["tropy-export-stat-items"].textContent = "1";
      tropyEls["tropy-export-stat-photos"].textContent = "1";
      tropyEls["tropy-export-stat-transcriptions"].textContent = hasText > 0 ? "1" : "0";
    } else {
      // Queue: count eligible items
      const stage = tropyEls["tropy-export-stage"].value;
      const items = await countEligibleItems(stage);
      tropyEls["tropy-export-stat-items"].textContent = String(items.count);
      tropyEls["tropy-export-stat-photos"].textContent = String(items.photos);
      tropyEls["tropy-export-stat-transcriptions"].textContent = String(items.withText);
    }
  } catch (err) {
    // Swallow — stats are cosmetic
    tropyEls["tropy-export-stat-items"].textContent = "?";
    tropyEls["tropy-export-stat-photos"].textContent = "?";
    tropyEls["tropy-export-stat-transcriptions"].textContent = "?";
  }
}

async function countEligibleItems(stage) {
  const items = await api("GET", "/api/queue");
  const stageMap = {
    raw_ocr: "raw",
    cleaned: "cleaned",
    translated: "translated",
  };
  const textMap = {
    raw_ocr: "extracted_text",
    cleaned: "cleaned_text",
    translated: "translated_text",
  };
  const stageKey = stageMap[stage] || "cleaned";
  const textKey = textMap[stage] || "cleaned_text";

  let count = 0;
  let photos = 0;
  let withText = 0;
  for (const item of items) {
    if (item.source && item.source.origin === "tropy-jsonld") {
      count++;
      photos++;
      // We can't get full preview text from the queue snapshot, but
      // we can check what's available in the item
      if (item.state === "done") withText++;
    }
  }
  return { count, photos, withText };
}

function closeTropyExport() {
  tropyEls["modal-tropy-send"].classList.add("hidden");
  tropyExportContext = null;
}

tropyEls["btn-send-tropy"].onclick = () => openTropyExport({ isHistory: false });
tropyEls["btn-send-tropy-close"].onclick = closeTropyExport;
tropyEls["modal-tropy-send"].querySelector("[data-modal-close]")?.addEventListener("click", closeTropyExport);
tropyEls["modal-tropy-send"].addEventListener("click", (e) => {
  if (e.target === tropyEls["modal-tropy-send"]) closeTropyExport();
});

tropyEls["btn-send-tropy-write"].onclick = async () => {
  const stage = tropyEls["tropy-export-stage"].value;
  const endpoint = tropyExportContext && tropyExportContext.isHistory
    ? "/api/tropy/export/history"
    : "/api/tropy/export";

  // Step 1 – ask the user where to save the file
  tropyEls["tropy-export-loading"].classList.remove("hidden");
  tropyEls["tropy-export-loading-text"].textContent = "Choose save location…";
  tropyEls["tropy-export-status"].textContent = "";

  let saveRes;
  try {
    saveRes = await fetch("/api/native/save-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preset: "json", default_name: "artifice-ocr-tropy.jsonld" }),
    });
  } catch (err) {
    tropyEls["tropy-export-loading"].classList.add("hidden");
    tropyEls["tropy-export-status"].textContent = "Save dialog not available";
    tropyEls["tropy-export-status"].className = "tropy-export-status error";
    if (window.ArtificeToast) window.ArtificeToast.error("Save dialog not available — try running from the desktop app");
    return;
  }

  const pathData = await saveRes.json().catch(() => ({}));
  const savePath = pathData.path;
  if (!savePath) {
    tropyEls["tropy-export-loading"].classList.add("hidden");
    return;  // user cancelled the dialog
  }

  // Step 2 – generate the export, writing to the chosen path
  tropyEls["tropy-export-loading-text"].textContent = "Generating Tropy export…";
  const body = { stage, path: savePath };
  if (tropyExportContext) {
    body.item_ids = tropyExportContext.itemIds;
  }

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      const msg = detail.detail || `Server returned ${res.status}`;
      tropyEls["tropy-export-status"].textContent = msg;
      tropyEls["tropy-export-status"].className = "tropy-export-status error";
      if (window.ArtificeToast) window.ArtificeToast.error(`Export failed: ${msg}`);
      return;
    }

    const data = await res.json();
    const filename = data.filename || savePath.split(/[\\/]/).pop();
    const jsonldContent = data.jsonld || null;

    // Step 3 – try direct import into Tropy via local HTTP API
    if (jsonldContent) {
      tropyEls["tropy-export-loading-text"].textContent = "Importing into Tropy…";
      try {
        const importRes = await api("POST", "/api/tropy/import-to-tropy", { jsonld: jsonldContent });
        if (importRes.ok) {
          tropyEls["tropy-export-status"].textContent = "Imported into Tropy via API";
          tropyEls["tropy-export-status"].className = "tropy-export-status success";
          if (window.ArtificeToast) {
            window.ArtificeToast.success("Imported into Tropy via API");
          }
          tropyEls["tropy-export-loading"].classList.add("hidden");
          // Persist last-used Tropy export path
          api("POST", "/api/config", { tropy_last_export_path: savePath }).catch(function(err) {
            if (window.ArtificeToast) window.ArtificeToast.error("Could not save export path: " + err.message);
          });
          return;
        }
        // API import failed — fall through to file-based flow with a note
        const reason = importRes.reason || "Tropy API not reachable";
        tropyEls["tropy-export-status"].textContent = reason + " — file saved at " + filename;
        tropyEls["tropy-export-status"].className = "tropy-export-status dim";
      } catch (err) {
        // Network error to our own backend — fall through to file-based flow
        tropyEls["tropy-export-status"].textContent = "Tropy API not available — file saved at " + filename;
        tropyEls["tropy-export-status"].className = "tropy-export-status dim";
      }
    }

    // Build multi-line success block with actions
    const statusBlock = document.createElement("div");

    const statusLine = document.createElement("div");
    statusLine.textContent = "Exported to " + filename;
    statusBlock.appendChild(statusLine);

    // Re-import instructions
    const stepsLine = document.createElement("div");
    stepsLine.className = "dim";
    stepsLine.textContent = "In Tropy: File → Import Items\u2026 → Select the exported file";
    statusBlock.appendChild(stepsLine);

    // Action buttons row
    const actionsRow = document.createElement("div");
    actionsRow.className = "tropy-export-actions";

    const btnReveal = document.createElement("button");
    btnReveal.type = "button";
    btnReveal.className = "btn";
    btnReveal.textContent = "Reveal in file manager";
    btnReveal.onclick = async () => {
      btnReveal.disabled = true;
      btnReveal.textContent = "Opening\u2026";
      try {
        const rev = await api("POST", "/api/native/reveal", { path: savePath });
        if (!rev.ok) {
          if (window.ArtificeToast) window.ArtificeToast.error("Reveal failed: " + (rev.error || "unknown"));
        }
      } catch (err) {
        if (window.ArtificeToast) window.ArtificeToast.error("Reveal failed: " + err.message);
      }
      btnReveal.disabled = false;
      btnReveal.textContent = "Reveal in file manager";
    };
    actionsRow.appendChild(btnReveal);

    const btnCopyPath = document.createElement("button");
    btnCopyPath.type = "button";
    btnCopyPath.className = "btn";
    btnCopyPath.textContent = "Copy path";
    btnCopyPath.onclick = () => {
      navigator.clipboard.writeText(savePath).then(() => {
        const orig = btnCopyPath.textContent;
        btnCopyPath.textContent = "Copied!";
        setTimeout(() => { btnCopyPath.textContent = orig; }, 2000);
      }).catch(() => {
        if (window.ArtificeToast) window.ArtificeToast.error("Could not copy to clipboard");
      });
    };
    actionsRow.appendChild(btnCopyPath);

    statusBlock.appendChild(actionsRow);

    // Replace the status element's content and set success class
    tropyEls["tropy-export-status"].innerHTML = "";
    tropyEls["tropy-export-status"].className = "tropy-export-status success";
    tropyEls["tropy-export-status"].appendChild(statusBlock);

    if (window.ArtificeToast) {
      window.ArtificeToast.success("Exported to " + filename);
    }

    // Persist last-used Tropy export path
    api("POST", "/api/config", { tropy_last_export_path: savePath }).catch(function(err) {
      if (window.ArtificeToast) window.ArtificeToast.error("Could not save export path: " + err.message);
    });
  } catch (err) {
    tropyEls["tropy-export-status"].textContent = err.message;
    tropyEls["tropy-export-status"].className = "tropy-export-status error";
    if (window.ArtificeToast) window.ArtificeToast.error(`Export failed: ${err.message}`);
  } finally {
    tropyEls["tropy-export-loading"].classList.add("hidden");
  }
};

// Expose openTropyExport for history.js to call
window.openTropyExport = openTropyExport;
