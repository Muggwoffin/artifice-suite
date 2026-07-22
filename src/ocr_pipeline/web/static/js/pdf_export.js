/*
 * "Compile PDF…" modal — one-off PDF export of a folder of processed .txt
 * files. Uses SSE for live progress instead of a synchronous fetch (the
 * structuring pass calls the LLM once per page; blocking for 275 pages
 * would hang the browser tab).
 *
 * Loaded after app.js, whose helpers (api, escapeHtml, pickFolder, log) it
 * reuses rather than duplicating — the same relationship tropy.js has.
 */

const pdfEls = {};
["btn-compile-pdf", "modal-compile-pdf", "pdf-folder", "pdf-stage",
 "pdf-structure", "pdf-output", "pdf-status", "pdf-log",
 "btn-pdf-start", "btn-pdf-download", "btn-pdf-close",
 "btn-pdf-browse-folder", "btn-pdf-browse-output",
 "pdf-format", "pdf-style", "pdf-bilingual", "pdf-bilingual-hint",
].forEach(id => {
  pdfEls[id] = document.getElementById(id);
});

let pdfEventSource = null;

// ------------------------------------------------------------- open / close

function openPdfExport() {
  pdfEls["modal-compile-pdf"].classList.remove("hidden");
  pdfEls["pdf-log"].innerHTML = "";
  pdfEls["btn-pdf-download"].disabled = true;
  pdfEls["btn-pdf-start"].disabled = false;
  setPdfStatus("Select a folder of processed .txt files, then press Start.", "");

  // Smart default: use the output dir from the main view
  const outputDir = (els["output-dir"] && els["output-dir"].value) || "output";
  pdfEls["pdf-output"].value = "";

  // Try to guess from the first queue item
  if (items.size > 0) {
    const first = items.values().next().value;
    if (first && first.name) {
      const name = first.name.replace(/\.[^.]+$/, "");
      pdfEls["pdf-folder"].value = outputDir + "/cleaned/text/" + name;
    }
  }
}

function closePdfExport() {
  if (pdfEventSource) { pdfEventSource.close(); pdfEventSource = null; }
  pdfEls["modal-compile-pdf"].classList.add("hidden");
}

function setPdfStatus(text, cls) {
  pdfEls["pdf-status"].textContent = text;
  pdfEls["pdf-status"].className = "dim " + (cls || "");
}

function appendPdfLog(text) {
  const line = document.createElement("div");
  line.className = "line";
  line.textContent = text;
  pdfEls["pdf-log"].appendChild(line);
  pdfEls["pdf-log"].scrollTop = pdfEls["pdf-log"].scrollHeight;
}

// -------------------------------------------------------- browse / download

async function browsePdfFolder() {
  const dir = await pickFolder("folder");
  if (dir) pdfEls["pdf-folder"].value = dir;
}

async function browsePdfOutput() {
  if (isNative()) {
    const path = await window.pywebview.api.browse_save_file("pdf");
    if (path) pdfEls["pdf-output"].value = path;
  } else {
    const path = prompt("Enter an absolute output PDF path (browser mode):");
    if (path) pdfEls["pdf-output"].value = path;
  }
}

// --------------------------------------------------------- start / download

async function startPdfExport() {
  const folder = pdfEls["pdf-folder"].value.trim();
  if (!folder) { setPdfStatus("Choose a folder first.", "warning"); return; }

  pdfEls["btn-pdf-start"].disabled = true;
  pdfEls["btn-pdf-download"].disabled = true;
  pdfEls["pdf-log"].innerHTML = "";
  setPdfStatus("Starting…", "");

  try {
    await api("POST", "/api/pdf-export/start", {
      folder: folder,
      stage: pdfEls["pdf-stage"].value,
      structure: pdfEls["pdf-structure"].checked,
      output: pdfEls["pdf-output"].value.trim() || null,
      format: pdfEls["pdf-format"].value,
      style: pdfEls["pdf-style"].value,
      bilingual: pdfEls["pdf-bilingual"].checked,
    });
  } catch (err) {
    setPdfStatus("Failed to start: " + err.message, "error");
    pdfEls["btn-pdf-start"].disabled = false;
    return;
  }

  pdfEventSource = new EventSource("/api/pdf-export/events");
  pdfEventSource.onmessage = (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch (_) { return; }
    if (data.type === "log") {
      appendPdfLog(data.message);
    } else if (data.type === "done") {
      appendPdfLog("Done: " + data.output_path);
      setPdfStatus("PDF compiled successfully.", "success");
      pdfEls["btn-pdf-download"].disabled = false;
      pdfEls["btn-pdf-start"].disabled = false;
      pdfEventSource.close();
      pdfEventSource = null;
    } else if (data.type === "error") {
      appendPdfLog("ERROR: " + data.message);
      setPdfStatus("Error: " + data.message, "error");
      pdfEls["btn-pdf-start"].disabled = false;
      pdfEventSource.close();
      pdfEventSource = null;
    }
  };
  pdfEventSource.onerror = () => {
    // EventSource auto-reconnects; only surface a real error after
    // the stream should have ended.
  };
}

async function downloadPdf() {
  if (pdfEls["btn-pdf-download"].disabled) return;
  window.open("/api/pdf-export/download", "_blank");
}

// ------------------------------------------------------------- event wiring

pdfEls["btn-compile-pdf"].onclick = openPdfExport;
pdfEls["btn-pdf-close"].onclick = closePdfExport;
pdfEls["btn-pdf-start"].onclick = startPdfExport;
pdfEls["btn-pdf-download"].onclick = downloadPdf;
pdfEls["btn-pdf-browse-folder"].onclick = browsePdfFolder;
pdfEls["btn-pdf-browse-output"].onclick = browsePdfOutput;
pdfEls["modal-compile-pdf"].addEventListener("click", (e) => {
  if (e.target === pdfEls["modal-compile-pdf"]) closePdfExport();
});

// Bilingual mode: disable stage selector, show hint, default no-structure
pdfEls["pdf-bilingual"].addEventListener("change", (e) => {
  const on = e.target.checked;
  pdfEls["pdf-bilingual-hint"].style.display = on ? "block" : "none";
  pdfEls["pdf-stage"].disabled = on;
  if (on) {
    pdfEls["pdf-structure"].checked = false;
  }
});
