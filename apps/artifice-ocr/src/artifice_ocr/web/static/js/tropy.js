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

// ------------------------------------------------------------- import modal

async function openTropyAdd() {
  tropyEls["modal-tropy-add"].classList.remove("hidden");
  resetImportState();
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
      ? ` <span class="tropy-result-missing">${item.missing_count} missing</span>`
      : "";
    row.innerHTML = `
      <input type="checkbox" class="tropy-result-check" data-group="${escapeHtml(item.group)}" checked>
      <span class="tropy-result-title">${escapeHtml(item.title)}</span>
      <span class="tropy-result-meta">${item.photo_count} photo(s)${missingBadge}</span>`;
    row.addEventListener("click", (e) => {
      if (e.target.tagName !== "INPUT") {
        const cb = row.querySelector("input[type=checkbox]");
        cb.checked = !cb.checked;
        updateImportSummary();
      }
    });
    row.querySelector("input[type=checkbox]").addEventListener("change", updateImportSummary);
    frag.appendChild(row);
  }

  tropyEls["tropy-import-list"].innerHTML = "";
  tropyEls["tropy-import-list"].appendChild(frag);
  updateImportSummary();

  if (items.length > 0) {
    tropyEls["btn-tropy-add-queue"].disabled = false;
  }
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
    setQueue(data.items);
    tropyEls["modal-tropy-add"].classList.add("hidden");
  } catch (err) {
    if (window.ArtificeToast) window.ArtificeToast.error(`Import failed: ${err.message}`);
    tropyEls["btn-tropy-add-queue"].disabled = false;
    tropyEls["btn-tropy-add-queue"].textContent = "Add to Queue";
  }
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
    tropyEls["tropy-export-status"].textContent = "Exported to " + filename;
    tropyEls["tropy-export-status"].className = "tropy-export-status success";
    if (window.ArtificeToast) {
      window.ArtificeToast.success("Exported to " + filename);
    }
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
