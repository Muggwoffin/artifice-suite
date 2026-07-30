// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: MIT

/*
 * LudwigLang export dialog: export a cleaned collection as a frontmatter .md
 * file for LudwigLang's Import Text page (Transport A).
 */

const llEls = {};
["btn-send-ludwiglang", "modal-ludwiglang", "ll-collection",
 "ll-medium", "ll-author", "ll-date", "ll-page-markers",
 "ll-skip-language-gate", "ll-preview-area", "ll-status",
 "btn-ll-export", "btn-ll-close", "btn-ll-refresh"].forEach(id => {
  llEls[id] = document.getElementById(id);
});

let llCollections = [];

async function openLudwigLang() {
  llEls["modal-ludwiglang"].classList.remove("hidden");
  llEls["ll-preview-area"].innerHTML =
    `<p class="dim">Loading collections…</p>`;
  llEls["ll-status"].textContent = "";
  llEls["btn-ll-export"].disabled = true;
  await refreshLudwigLangCollections();
}

async function refreshLudwigLangCollections() {
  const outputDir = document.getElementById("output-dir").value || "output";
  llEls["ll-collection"].innerHTML = `<option>Loading…</option>`;
  try {
    const data = await api("GET",
      `/api/ludwiglang/collections?output_dir=${encodeURIComponent(outputDir)}`);
    llCollections = data.collections || [];
    if (!llCollections.length) {
      llEls["ll-collection"].innerHTML =
        `<option value="">-- No collections found --</option>`;
      llEls["ll-preview-area"].innerHTML =
        `<p class="dim">No processed collections found. Run the pipeline first.</p>`;
      return;
    }
    llEls["ll-collection"].innerHTML = llCollections.map(c =>
      `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
    llEls["btn-ll-export"].disabled = false;
    updateLudwigLangPreview();
  } catch (err) {
    llEls["ll-collection"].innerHTML =
      `<option value="">-- Error loading --</option>`;
    llEls["ll-preview-area"].innerHTML =
      `<p class="error">${escapeHtml(err.message)}</p>`;
  }
}

function updateLudwigLangPreview() {
  const coll = llEls["ll-collection"].value;
  if (!coll) {
    llEls["ll-preview-area"].innerHTML =
      `<p class="dim">Select a collection above to export.</p>`;
    return;
  }
  const medium = llEls["ll-medium"].value;
  const markers = llEls["ll-page-markers"].checked ? " (with page markers)" : "";
  llEls["ll-preview-area"].innerHTML = `
    <p class="dim" style="margin-bottom:0.3rem;">Export summary:</p>
    <table class="queue" style="font-size:0.82rem;">
      <tbody>
        <tr><td><strong>Collection</strong></td><td>${escapeHtml(coll)}</td></tr>
        <tr><td><strong>Medium</strong></td><td>${escapeHtml(medium)}</td></tr>
        <tr><td><strong>Page markers</strong></td><td>${escapeHtml(markers || "none")}</td></tr>
        <tr><td><strong>Output</strong></td><td>output/ludwiglang/${escapeHtml(coll)}/text.md</td></tr>
      </tbody>
    </table>
    <p class="dim" style="margin-top:0.5rem;">
      The exported file can be dragged onto LudwigLang's Import page.
    </p>`;
}

async function exportLudwigLang() {
  const coll = llEls["ll-collection"].value;
  if (!coll) return;

  llEls["btn-ll-export"].disabled = true;
  llEls["ll-status"].textContent = "Exporting…";
  llEls["ll-status"].className = "dim";

  const outputDir = document.getElementById("output-dir").value || "output";

  try {
    const data = await api("POST", "/api/ludwiglang/export", {
      collection: coll,
      output_dir: outputDir,
      medium: llEls["ll-medium"].value,
      author: llEls["ll-author"].value,
      date: llEls["ll-date"].value,
      page_markers: llEls["ll-page-markers"].checked,
      skip_language_gate: llEls["ll-skip-language-gate"].checked,
    });

    // Trigger download from server
    const downloadUrl = `/api/ludwiglang/download?path=${encodeURIComponent(data.path)}`;
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = data.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    llEls["ll-status"].textContent =
      `Exported: ${data.filename || data.path}`;
    llEls["ll-status"].className = "success";
    log(`LudwigLang export: ${coll} → ${data.filename}`, "success");
  } catch (err) {
    llEls["ll-status"].textContent = `Export failed: ${err.message}`;
    llEls["ll-status"].className = "error";
    log(`LudwigLang export failed: ${err.message}`, "error");
  } finally {
    llEls["btn-ll-export"].disabled = false;
  }
}

llEls["btn-send-ludwiglang"].onclick = openLudwigLang;
llEls["btn-ll-close"].onclick = () => {
  llEls["modal-ludwiglang"].classList.add("hidden");
};
llEls["modal-ludwiglang"].querySelector("[data-modal-close]")?.addEventListener("click", () => {
  llEls["modal-ludwiglang"].classList.add("hidden");
});
llEls["modal-ludwiglang"].addEventListener("click", (e) => {
  if (e.target === llEls["modal-ludwiglang"]) {
    llEls["modal-ludwiglang"].classList.add("hidden");
  }
});
llEls["btn-ll-refresh"].onclick = refreshLudwigLangCollections;
llEls["ll-collection"].addEventListener("change", () => {
  llEls["btn-ll-export"].disabled = !llEls["ll-collection"].value;
  updateLudwigLangPreview();
});
llEls["ll-medium"].addEventListener("change", updateLudwigLangPreview);
llEls["ll-page-markers"].addEventListener("change", updateLudwigLangPreview);
llEls["btn-ll-export"].onclick = exportLudwigLang;
