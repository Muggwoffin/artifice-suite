// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * Both Tropy dialogs: "Add from Tropy…" (pull pages into the queue) and
 * "Send to Tropy…" (write finished results back). Loaded after app.js, whose
 * helpers (api, escapeHtml, pickFolder, setQueue, log) it reuses rather than
 * duplicating — the same relationship the tk build's TropyPicker and
 * TropySendDialog have to the App instance that opens them.
 */

const tropyEls = {};
["btn-add-tropy", "modal-tropy-add", "tropy-project",
 "tropy-sources", "tropy-items", "tropy-summary-text",
 "tropy-summary-warning", "btn-tropy-add-queue",
 "btn-tropy-cancel", "btn-tropy-browse-project",
 "btn-send-tropy", "modal-tropy-send", "send-tropy-project",
 "send-tropy-targets-notes", "send-tropy-targets-transcriptions",
 "send-tropy-stage", "send-tropy-backup", "send-tropy-status",
 "send-tropy-plans", "btn-send-tropy-preview", "btn-send-tropy-write",
 "btn-send-tropy-close",
 "send-tropy-history-detail", "send-tropy-history-name",
 "send-tropy-history-photo", "send-tropy-history-page"].forEach(id => {
  tropyEls[id] = document.getElementById(id);
});

let tropyProjects = [];
let tropyProjectData = null;
let historySendContext = null;
const ALL_ITEMS = "__all__";

// ------------------------------------------------------------- add from tropy

async function openTropyAdd() {
  tropyEls["modal-tropy-add"].classList.remove("hidden");
  tropyEls["tropy-sources"].innerHTML = "";
  tropyEls["tropy-items"].innerHTML =
    `<div class="empty-state">Select a list, tag, or "All items" on the left</div>`;
  tropyProjectData = null;
  selectedSources.clear();
  updateTropySummary(0, 0, []);
  tropyEls["btn-tropy-add-queue"].disabled = true;
  await ensureTropyProjectList(tropyEls["tropy-project"]);
  if (tropyEls["tropy-project"].value) loadTropySources();
}

async function ensureTropyProjectList(selectEl) {
  if (!tropyProjects.length) {
    const data = await api("GET", "/api/tropy/recent");
    tropyProjects = data.projects;
  }
  selectEl.innerHTML = tropyProjects
    .map(p => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join("");
}

tropyEls["btn-add-tropy"].onclick = openTropyAdd;
tropyEls["btn-tropy-cancel"].onclick = () => {
  tropyEls["modal-tropy-add"].classList.add("hidden");
};
tropyEls["modal-tropy-add"].querySelector("[data-modal-close]")?.addEventListener("click", () => {
  tropyEls["modal-tropy-add"].classList.add("hidden");
});
tropyEls["tropy-project"].addEventListener("change", loadTropySources);
tropyEls["btn-tropy-browse-project"].onclick = async () => {
  const dir = await pickFolder("tropy");
  if (!dir) return;
  if (!tropyProjects.includes(dir)) {
    tropyProjects.unshift(dir);
    const opt = document.createElement("option");
    opt.value = dir; opt.textContent = dir;
    tropyEls["tropy-project"].prepend(opt);
  }
  tropyEls["tropy-project"].value = dir;
  loadTropySources();
};

async function loadTropySources() {
  const project = tropyEls["tropy-project"].value;
  if (!project) return;
  tropyEls["tropy-sources"].innerHTML = `<p class="dim" style="padding:0.7rem;">Loading…</p>`;
  tropyEls["tropy-items"].innerHTML =
    `<div class="empty-state">Select a list, tag, or "All items" on the left</div>`;
  updateTropySummary(0, 0, []);
  tropyEls["btn-tropy-add-queue"].disabled = true;
  try {
    const data = await api("POST", "/api/tropy/browse", { project });
    tropyProjectData = data;
    renderSourceTree(data);
    // Reset to default selection: All items
    selectedSources.clear();
    selectedSources.set(sourceKey(ALL_ITEMS, null), { type: ALL_ITEMS, id: null });
    updateSourceHighlight();
  } catch (err) {
    tropyEls["tropy-sources"].innerHTML =
      `<p class="dim" style="padding:0.7rem;">${escapeHtml(err.message)}</p>`;
  }
}

function renderSourceTree(data) {
  const el = tropyEls["tropy-sources"];
  const frag = document.createDocumentFragment();

  // "All items" section label
  const allLabel = document.createElement("div");
  allLabel.className = "tropy-source-section-label";
  allLabel.textContent = "Overview";
  frag.appendChild(allLabel);

  // All items node
  const allItems = document.createElement("div");
  allItems.className = "tropy-source-node active";
  allItems.dataset.type = ALL_ITEMS;
  allItems.dataset.id = "";
  allItems.innerHTML = `<span class="icon">&#128196;</span>All items<span class="count">${data.lists.reduce((s, l) => s + l.item_count, 0)}</span>`;
  allItems.addEventListener("click", () => selectSource(allItems, ALL_ITEMS, null));
  frag.appendChild(allItems);

  let totalItems = data.lists.reduce((s, l) => s + l.item_count, 0);

  // Lists section label
  if (data.lists.length) {
    const listLabel = document.createElement("div");
    listLabel.className = "tropy-source-section-label";
    listLabel.textContent = "Lists";
    frag.appendChild(listLabel);

    // Build hierarchy: parent_id -> children
    const childrenOf = {};
    for (const l of data.lists) {
      const parentKey = l.parent_id ?? 0;
      if (!childrenOf[parentKey]) childrenOf[parentKey] = [];
      childrenOf[parentKey].push(l);
    }

    function renderListBranch(list, depth) {
      const node = document.createElement("div");
      node.className = "tropy-source-node";
      node.style.paddingLeft = `${0.7 + depth * 1.2}rem`;
      node.dataset.type = "list";
      node.dataset.id = list.list_id;
      node.innerHTML =
        `<span class="icon">${depth === 0 ? "&#128193;" : "&#128193;"}</span>${escapeHtml(list.name)}<span class="count">${list.item_count}</span>`;
      node.addEventListener("click", () => selectSource(node, "list", list.list_id));
      frag.appendChild(node);

      const sub = childrenOf[list.list_id];
      if (sub) {
        sub.sort((a, b) => a.name.localeCompare(b.name));
        for (const child of sub) renderListBranch(child, depth + 1);
      }
    }

    const roots = (childrenOf[0] || []).concat(childrenOf[null] || []);
    roots.sort((a, b) => a.name.localeCompare(b.name));
    for (const root of roots) renderListBranch(root, 0);
  }

  // Tags section label
  if (data.tags && data.tags.length) {
    const tagLabel = document.createElement("div");
    tagLabel.className = "tropy-source-section-label";
    tagLabel.textContent = "Tags";
    frag.appendChild(tagLabel);

    for (const t of data.tags) {
      const node = document.createElement("div");
      node.className = "tropy-source-node";
      node.dataset.type = "tag";
      node.dataset.id = t.name;
      node.innerHTML =
        `<span class="icon">&#127991;</span>${escapeHtml(t.name)}<span class="count">${t.count}</span>`;
      node.addEventListener("click", () => selectSource(node, "tag", t.name));
      frag.appendChild(node);
    }
  }

  el.innerHTML = "";
  el.appendChild(frag);
}

let currentSource = ALL_ITEMS;
const selectedSources = new Map(); // key -> {type, id}

function sourceKey(type, id) {
  return `${type}::${id ?? ""}`;
}

function getSourceNode(type, id) {
  const key = sourceKey(type, id);
  return tropyEls["tropy-sources"].querySelector(
    `.tropy-source-node[data-type="${type}"]` +
    (id != null ? `[data-id="${id}"]` : ""));
}

function updateSourceHighlight() {
  tropyEls["tropy-sources"].querySelectorAll(".tropy-source-node")
    .forEach(n => {
      const key = sourceKey(n.dataset.type, n.dataset.id);
      n.classList.toggle("active", selectedSources.has(key));
    });
}

async function fetchCombinedItems() {
  const project = tropyEls["tropy-project"].value;
  if (!project || !selectedSources.size) return;

  tropyEls["tropy-items"].innerHTML =
    `<div class="empty-state">Loading…</div>`;

  try {
    const seen = new Set();
    const merged = [];

    for (const [, src] of selectedSources) {
      const body = { project };
      if (src.type === "list") body.list_id = src.id;
      else if (src.type === "tag") body.tag = src.id;

      const data = await api("POST", "/api/tropy/browse", body);
      for (const item of (data.items || [])) {
        if (!seen.has(item.item_id)) {
          seen.add(item.item_id);
          merged.push(item);
        }
      }
    }

    renderItems(merged);
  } catch (err) {
    tropyEls["tropy-items"].innerHTML =
      `<div class="empty-state">${escapeHtml(err.message)}</div>`;
  }
}

async function selectSource(node, type, id) {
  const ctrl = window.event ? window.event.ctrlKey || window.event.metaKey : false;

  if (ctrl) {
    const key = sourceKey(type, id);
    if (selectedSources.has(key)) {
      selectedSources.delete(key);
    } else {
      selectedSources.set(key, { type, id });
    }
    updateSourceHighlight();
    await fetchCombinedItems();
  } else {
    selectedSources.clear();
    const key = sourceKey(type, id);
    selectedSources.set(key, { type, id });
    updateSourceHighlight();

    const project = tropyEls["tropy-project"].value;
    if (!project) return;

    tropyEls["tropy-items"].innerHTML =
      `<div class="empty-state">Loading…</div>`;

    try {
      const body = { project };
      if (type === "list") body.list_id = id;
      else if (type === "tag") body.tag = id;

      const data = await api("POST", "/api/tropy/browse", body);
      renderItems(data.items || []);
    } catch (err) {
      tropyEls["tropy-items"].innerHTML =
        `<div class="empty-state">${escapeHtml(err.message)}</div>`;
    }
  }
}

function renderItems(items) {
  const el = tropyEls["tropy-items"];
  if (!items.length) {
    el.innerHTML = `<div class="empty-state">No items in this ${currentSource.type}.</div>`;
    updateTropySummary(0, 0, []);
    tropyEls["btn-tropy-add-queue"].disabled = true;
    return;
  }

  const frag = document.createDocumentFragment();
  for (const i of items) {
    const row = document.createElement("div");
    row.className = "tropy-item-row";
    row.innerHTML = `
      <input type="checkbox" class="tropy-item-check" data-item-id="${i.item_id}" checked>
      <span class="item-title">${escapeHtml(i.title || "(untitled)")}</span>
      <span class="item-meta">${i.photo_count} page(s)</span>`;
    row.querySelector("input[type=checkbox]").addEventListener("change", () => {
      updateTropySummaryFromCheckboxes();
    });
    // clicking the row toggles the checkbox
    row.addEventListener("click", (e) => {
      if (e.target.tagName !== "INPUT") {
        const cb = row.querySelector("input[type=checkbox]");
        cb.checked = !cb.checked;
        updateTropySummaryFromCheckboxes();
      }
    });
    frag.appendChild(row);
  }

  el.innerHTML = "";
  el.appendChild(frag);
  updateTropySummaryFromCheckboxes();
}

function updateTropySummaryFromCheckboxes() {
  const checkboxes = tropyEls["tropy-items"].querySelectorAll(".tropy-item-check");
  const selected = [];
  let totalPages = 0;
  for (const cb of checkboxes) {
    if (cb.checked) {
      selected.push(Number(cb.dataset.itemId));
      // Find the page count from the row label
      const meta = cb.closest(".tropy-item-row").querySelector(".item-meta");
      const match = meta.textContent.match(/(\d+)/);
      totalPages += match ? parseInt(match[1], 10) : 0;
    }
  }
  updateTropySummary(selected.length, totalPages, []);
  tropyEls["btn-tropy-add-queue"].disabled = selected.length === 0;
}

function updateTropySummary(items, pages, missing) {
  const parts = [];
  if (items > 0) parts.push(`${items} item(s)`);
  if (pages > 0) parts.push(`${pages} page(s)`);
  tropyEls["tropy-summary-text"].textContent =
    parts.length ? `${parts.join(", ")} to queue` : "No items selected";
  tropyEls["tropy-summary-warning"].textContent =
    missing.length ? `${missing.length} page(s) missing from computer — will be skipped` : "";
}

tropyEls["btn-tropy-add-queue"].onclick = async () => {
  const project = tropyEls["tropy-project"].value;
  if (!project) return;

  const checkboxes = tropyEls["tropy-items"].querySelectorAll(".tropy-item-check:checked");
  const itemIds = Array.from(checkboxes).map(cb => Number(cb.dataset.itemId));
  if (!itemIds.length) return;

  tropyEls["btn-tropy-add-queue"].disabled = true;
  tropyEls["btn-tropy-add-queue"].textContent = "Adding…";

  try {
    const data = await api("POST", "/api/tropy/add", {
      project, item_ids: itemIds, output_dir: document.getElementById("output-dir").value || "output",
    });

    let note = `Added ${data.added} page(s) from Tropy`;
    if (data.missing && data.missing.length) {
      note += `; ${data.missing.length} page(s) missing from computer and skipped`;
      const names = data.missing.slice(0, 5).map(escapeHtml).join(", ");
      note += data.missing.length > 5 ? ` (e.g. ${names}…)` : ` (${names})`;
    }
    log(note, data.missing && data.missing.length ? "warning" : "accent");
    setQueue(data.items);
    tropyEls["modal-tropy-add"].classList.add("hidden");
  } catch (err) {
    log(`Error adding from Tropy: ${err.message}`, "error");
    tropyEls["btn-tropy-add-queue"].disabled = false;
    tropyEls["btn-tropy-add-queue"].textContent = "Add to Queue";
  }
};

// ------------------------------------------------------------- send to tropy

let lastPreview = null;

function selectedTargets() {
  const targets = [];
  if (tropyEls["send-tropy-targets-notes"].checked) targets.push("notes");
  if (tropyEls["send-tropy-targets-transcriptions"].checked) targets.push("transcriptions");
  return targets;
}

async function openTropySend(historyInfo) {
  historySendContext = historyInfo || null;
  tropyEls["modal-tropy-send"].classList.remove("hidden");
  tropyEls["send-tropy-plans"].innerHTML = "";
  tropyEls["btn-send-tropy-write"].disabled = true;

  // Show/hide history item detail section
  if (historySendContext) {
    tropyEls["send-tropy-history-detail"].classList.remove("hidden");
    tropyEls["send-tropy-history-name"].textContent = historySendContext.name || "";
    tropyEls["send-tropy-history-photo"].textContent = historySendContext.photoTitle || "";
    tropyEls["send-tropy-history-page"].textContent = historySendContext.page != null ? String(historySendContext.page) : "";
    setTropySendStatus("Preview before writing — nothing is sent to Tropy until you press Write.", "");
  } else {
    tropyEls["send-tropy-history-detail"].classList.add("hidden");
    setTropySendStatus(
      "Preview before writing — nothing is sent to Tropy until you press Write.",
      "");
  }

  await ensureTropyProjectList(tropyEls["send-tropy-project"]);

  // Pre-select project if known from history
  if (historySendContext && historySendContext.project) {
    const opts = tropyEls["send-tropy-project"].options;
    for (let i = 0; i < opts.length; i++) {
      if (opts[i].value === historySendContext.project) {
        opts[i].selected = true;
        break;
      }
    }
  }
}

function setTropySendStatus(text, cls) {
  tropyEls["send-tropy-status"].textContent = text;
  tropyEls["send-tropy-status"].className = `dim ${cls}`;
}

async function previewTropySend() {
  const project = tropyEls["send-tropy-project"].value;
  const targets = selectedTargets();
  if (!project) { setTropySendStatus("Choose a Tropy project first.", "warning"); return; }
  if (!targets.length) { setTropySendStatus("Choose at least one write target.", "warning"); return; }

  setTropySendStatus("Building preview…", "");
  tropyEls["btn-send-tropy-write"].disabled = true;

  try {
    const body = { project, targets, stage: tropyEls["send-tropy-stage"].value };
    if (historySendContext) {
      body.item_ids = historySendContext.itemIds;
      lastPreview = await api("POST", "/api/tropy/send/history/preview", body);
    } else {
      lastPreview = await api("POST", "/api/tropy/send/preview", body);
    }
  } catch (err) {
    setTropySendStatus(`Could not read project: ${err.message}`, "error");
    return;
  }

  renderTropyPlans(lastPreview.plans);

  if (lastPreview.blockers.length) {
    setTropySendStatus(lastPreview.blockers.join("  •  "), "error");
  } else if (!lastPreview.insertable) {
    setTropySendStatus("Nothing new to write — everything is already in Tropy.", "");
  } else {
    setTropySendStatus(
      `${lastPreview.insertable} row(s) will be created. Nothing is written until you press Write.`,
      "");
    tropyEls["btn-send-tropy-write"].disabled = false;
  }
}

function renderTropyPlans(plans) {
  if (!plans.length) {
    tropyEls["send-tropy-plans"].innerHTML =
      `<p class="dim">No Tropy-sourced documents are finished yet.</p>`;
    return;
  }
  const rows = plans.map(p => `
    <tr>
      <td>${escapeHtml(p.label)}</td>
      <td>${escapeHtml(p.target)}</td>
      <td class="tropy-action-${p.action}">${escapeHtml(p.action)}</td>
      <td class="dim">${escapeHtml(p.reason || "")}</td>
    </tr>`).join("");
  tropyEls["send-tropy-plans"].innerHTML = `
    <table class="queue" style="font-size:0.82rem;">
      <thead><tr><th>Page</th><th>Target</th><th>Action</th><th>Detail</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

async function writeTropySend() {
  if (!lastPreview || !lastPreview.insertable) return;
  const project = tropyEls["send-tropy-project"].value;
  const targets = selectedTargets();
  const n = lastPreview.insertable;

  if (!confirm(`Create ${n} row(s) in ${targets.join(", ")} in\n${project}?\n\n` +
              (tropyEls["send-tropy-backup"].checked
                ? "A backup will be taken first."
                : "NO BACKUP will be taken."))) {
    return;
  }

  tropyEls["btn-send-tropy-write"].disabled = true;
  setTropySendStatus("Writing…", "");

  try {
    const body = {
      project, targets, stage: tropyEls["send-tropy-stage"].value,
      make_backup: tropyEls["send-tropy-backup"].checked,
    };
    const endpoint = historySendContext
      ? "/api/tropy/send/history/write"
      : "/api/tropy/send/write";
    if (historySendContext) body.item_ids = historySendContext.itemIds;
    const report = await api("POST", endpoint, body);
    let note = `Wrote ${report.written} row(s).`;
    if (report.backup) note += `  Backup: ${report.backup.split(/[\\/]/).pop()}`;
    setTropySendStatus(note, "success");
    log(note, "success");
    await previewTropySend(); // refresh so duplicates show correctly
  } catch (err) {
    setTropySendStatus(`Write failed: ${err.message}`, "error");
  }
}

tropyEls["btn-send-tropy"].onclick = openTropySend;
function closeTropySend() {
  tropyEls["modal-tropy-send"].classList.add("hidden");
  historySendContext = null;
}
tropyEls["btn-send-tropy-close"].onclick = closeTropySend;
tropyEls["modal-tropy-send"].querySelector("[data-modal-close]")?.addEventListener("click", closeTropySend);
tropyEls["btn-send-tropy-preview"].onclick = previewTropySend;
tropyEls["btn-send-tropy-write"].onclick = writeTropySend;
tropyEls["modal-tropy-send"].addEventListener("click", (e) => {
  if (e.target === tropyEls["modal-tropy-send"]) closeTropySend();
});

// Click-outside-to-close for add modal
tropyEls["modal-tropy-add"].addEventListener("click", (e) => {
  if (e.target === tropyEls["modal-tropy-add"]) tropyEls["modal-tropy-add"].classList.add("hidden");
});
