/*
 * Both Tropy dialogs: "Add from Tropy…" (pull pages into the queue) and
 * "Send to Tropy…" (write finished results back). Loaded after app.js, whose
 * helpers (api, escapeHtml, pickFolder, setQueue, log) it reuses rather than
 * duplicating — the same relationship the tk build's TropyPicker and
 * TropySendDialog have to the App instance that opens them.
 */

const tropyEls = {};
["btn-add-tropy", "modal-tropy-add", "tropy-project", "tropy-lists",
 "btn-tropy-cancel", "btn-tropy-browse-project",
 "btn-send-tropy", "modal-tropy-send", "send-tropy-project",
 "send-tropy-targets-notes", "send-tropy-targets-transcriptions",
 "send-tropy-stage", "send-tropy-backup", "send-tropy-status",
 "send-tropy-plans", "btn-send-tropy-preview", "btn-send-tropy-write",
 "btn-send-tropy-close"].forEach(id => {
  tropyEls[id] = document.getElementById(id);
});

let tropyProjects = [];

// ------------------------------------------------------------- add from tropy

async function openTropyAdd() {
  tropyEls["modal-tropy-add"].classList.remove("hidden");
  await ensureTropyProjectList(tropyEls["tropy-project"]);
  if (tropyEls["tropy-project"].value) loadTropyLists();
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
tropyEls["btn-tropy-cancel"].onclick = () => tropyEls["modal-tropy-add"].classList.add("hidden");
tropyEls["tropy-project"].addEventListener("change", loadTropyLists);
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
  loadTropyLists();
};

async function loadTropyLists() {
  const project = tropyEls["tropy-project"].value;
  if (!project) return;
  tropyEls["tropy-lists"].innerHTML = `<p class="dim">Loading…</p>`;
  try {
    const data = await api("POST", "/api/tropy/browse", { project });
    tropyEls["tropy-lists"].innerHTML = data.lists.map(l => `
      <div class="tropy-list-row" style="padding-left:${l.depth * 1.2}rem;">
        <span>${escapeHtml(l.name)} <span class="dim">(${l.item_count})</span></span>
        <button class="btn" data-list-id="${l.list_id}">Add list</button>
      </div>`).join("") || `<p class="dim">No lists in this project.</p>`;

    tropyEls["tropy-lists"].querySelectorAll("button[data-list-id]").forEach(btn => {
      btn.addEventListener("click", () => addTropyList(project, Number(btn.dataset.listId)));
    });
  } catch (err) {
    tropyEls["tropy-lists"].innerHTML = `<p class="dim">${escapeHtml(err.message)}</p>`;
  }
}

async function addTropyList(project, listId) {
  const browse = await api("POST", "/api/tropy/browse", { project, list_id: listId });
  const itemIds = browse.items.map(i => i.item_id);
  const data = await api("POST", "/api/tropy/add", { project, item_ids: itemIds });
  setQueue(data.items);
  log(`Added ${data.added} page(s) from Tropy`, "accent");
  tropyEls["modal-tropy-add"].classList.add("hidden");
}

// ------------------------------------------------------------- send to tropy

let lastPreview = null;

function selectedTargets() {
  const targets = [];
  if (tropyEls["send-tropy-targets-notes"].checked) targets.push("notes");
  if (tropyEls["send-tropy-targets-transcriptions"].checked) targets.push("transcriptions");
  return targets;
}

async function openTropySend() {
  tropyEls["modal-tropy-send"].classList.remove("hidden");
  tropyEls["send-tropy-plans"].innerHTML = "";
  tropyEls["btn-send-tropy-write"].disabled = true;
  setTropySendStatus(
    "Preview before writing — nothing is sent to Tropy until you press Write.",
    "");
  await ensureTropyProjectList(tropyEls["send-tropy-project"]);
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
    lastPreview = await api("POST", "/api/tropy/send/preview", body);
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
    const report = await api("POST", "/api/tropy/send/write", body);
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
tropyEls["btn-send-tropy-close"].onclick = () => tropyEls["modal-tropy-send"].classList.add("hidden");
tropyEls["btn-send-tropy-preview"].onclick = previewTropySend;
tropyEls["btn-send-tropy-write"].onclick = writeTropySend;
tropyEls["modal-tropy-send"].addEventListener("click", (e) => {
  if (e.target === tropyEls["modal-tropy-send"]) tropyEls["modal-tropy-send"].classList.add("hidden");
});
