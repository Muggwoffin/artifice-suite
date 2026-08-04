// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * Guide import: scrape a URL, paste text, or upload a file, then review the
 * extracted StyleGuide and save it. Relies on the shared `api()` helper.
 */

(function () {
  const modal = document.getElementById("guide-modal");
  const panels = {
    url: document.getElementById("panel-url"),
    text: document.getElementById("panel-text"),
    file: document.getElementById("panel-file"),
  };
  const stepReview = document.getElementById("step-review");
  const tabs = document.querySelectorAll(".import-tab");
  const urlInput = document.getElementById("guide-url");
  const btnScrape = document.getElementById("btn-scrape");
  const btnParseText = document.getElementById("btn-parse-text");
  const btnParseFile = document.getElementById("btn-parse-file");
  const btnImport = document.getElementById("btn-import-guide");
  const btnClose = document.getElementById("modal-close");
  const btnBack = document.getElementById("btn-back-url");
  const btnSave = document.getElementById("btn-save-guide");
  const scrapeLog = document.getElementById("scrape-log");
  const textLog = document.getElementById("text-log");
  const fileLog = document.getElementById("file-log");
  const pasteTextArea = document.getElementById("guide-paste-text");
  const fileInput = document.getElementById("guide-file-input");

  let scrapedGuide = null;

  function showPanel(which) {
    for (const [key, el] of Object.entries(panels)) {
      el.style.display = key === which ? "block" : "none";
    }
    stepReview.style.display = "none";
  }

  function showReview() {
    for (const el of Object.values(panels)) {
      el.style.display = "none";
    }
    stepReview.style.display = "block";
  }

  function setActiveTab(tabName) {
    tabs.forEach((t) => {
      const isActive = t.dataset.tab === tabName;
      t.classList.toggle("active", isActive);
    });
  }

  function openModal() {
    modal.style.display = "flex";
    showPanel("url");
    setActiveTab("url");
    urlInput.value = "";
    pasteTextArea.value = "";
    fileInput.value = "";
    scrapedGuide = null;
    scrapeLog.innerHTML = "";
    scrapeLog.style.display = "none";
    textLog.innerHTML = "";
    textLog.style.display = "none";
    fileLog.innerHTML = "";
    fileLog.style.display = "none";
  }

  function closeModal() {
    modal.style.display = "none";
  }

  btnImport.addEventListener("click", openModal);
  btnClose.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  btnBack.addEventListener("click", () => {
    showPanel("url");
    setActiveTab("url");
  });

  tabs.forEach((t) => {
    t.addEventListener("click", () => {
      showPanel(t.dataset.tab);
      setActiveTab(t.dataset.tab);
    });
  });

  // ------------------------------------------------------------------ scrape (URL)
  btnScrape.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!url) {
      scrapeLog.style.display = "block";
      scrapeLog.innerHTML = '<div class="line error">Please enter a URL.</div>';
      return;
    }

    btnScrape.disabled = true;
    btnScrape.textContent = "Scraping…";
    scrapeLog.style.display = "block";
    scrapeLog.innerHTML = '<div class="line accent">Fetching page and parsing with LLM…</div>';

    try {
      const result = await api("POST", "/api/style-guides/preview", { url });
      scrapedGuide = result.guide;
      populateForm(scrapedGuide);
      showReview();
    } catch (err) {
      scrapeLog.innerHTML += `\n<div class="line error">${escapeHtml(err.message)}</div>`;
    } finally {
      btnScrape.disabled = false;
      btnScrape.textContent = "Scrape & Preview";
    }
  });

  // ------------------------------------------------------------------ parse text
  btnParseText.addEventListener("click", async () => {
    const text = pasteTextArea.value.trim();
    if (!text) {
      textLog.style.display = "block";
      textLog.innerHTML = '<div class="line error">Please paste some text.</div>';
      return;
    }

    btnParseText.disabled = true;
    btnParseText.textContent = "Parsing…";
    textLog.style.display = "block";
    textLog.innerHTML = '<div class="line accent">Parsing with LLM…</div>';

    try {
      const result = await api("POST", "/api/style-guides/preview-text", { text });
      scrapedGuide = result.guide;
      populateForm(scrapedGuide);
      showReview();
    } catch (err) {
      textLog.innerHTML += `\n<div class="line error">${escapeHtml(err.message)}</div>`;
    } finally {
      btnParseText.disabled = false;
      btnParseText.textContent = "Parse & Preview";
    }
  });

  // ------------------------------------------------------------------ parse file
  btnParseFile.addEventListener("click", async () => {
    const file = fileInput.files[0];
    if (!file) {
      fileLog.style.display = "block";
      fileLog.innerHTML = '<div class="line error">Please select a file.</div>';
      return;
    }

    btnParseFile.disabled = true;
    btnParseFile.textContent = "Parsing…";
    fileLog.style.display = "block";
    fileLog.innerHTML = `<div class="line accent">Uploading and parsing ${file.name}…</div>`;

    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = await api("POST", "/api/style-guides/preview-file", formData, true);
      scrapedGuide = result.guide;
      populateForm(scrapedGuide);
      showReview();
    } catch (err) {
      fileLog.innerHTML += `\n<div class="line error">${escapeHtml(err.message)}</div>`;
    } finally {
      btnParseFile.disabled = false;
      btnParseFile.textContent = "Parse & Preview";
    }
  });

  // ------------------------------------------------------------------ form populate
  const FIELD_MAP = {
    name: "gf-name",
    edition: "gf-edition",
    citation_style: "gf-citation_style",
    heading_capitalization: "gf-heading_capitalization",
    footnote_format: "gf-footnote_format",
    bibliography_format: "gf-bibliography_format",
    prose_rules: "gf-prose_rules",
    quotation_rules: "gf-quotation_rules",
    abbreviation_rules: "gf-abbreviation_rules",
    date_format: "gf-date_format",
    page_reference_format: "gf-page_reference_format",
    url_format: "gf-url_format",
    system_prompt_addendum: "gf-system_prompt_addendum",
    custom_rules: "gf-custom_rules",
  };

  function populateForm(guide) {
    for (const [field, elId] of Object.entries(FIELD_MAP)) {
      const el = document.getElementById(elId);
      if (!el) continue;
      const val = guide[field];
      if (Array.isArray(val)) {
        el.value = val.join("\n");
      } else {
        el.value = val || "";
      }
    }
  }

  function collectForm() {
    const data = {};
    for (const [field, elId] of Object.entries(FIELD_MAP)) {
      const el = document.getElementById(elId);
      if (!el) continue;
      if (["prose_rules", "custom_rules"].includes(field)) {
        data[field] = el.value.split("\n").map((s) => s.trim()).filter(Boolean);
      } else {
        data[field] = el.value;
      }
    }
    return data;
  }

  // ------------------------------------------------------------------ save
  btnSave.addEventListener("click", async () => {
    const guideData = collectForm();
    const name = guideData.name;
    if (!name) {
      alert("Guide name is required.");
      return;
    }

    btnSave.disabled = true;
    btnSave.textContent = "Saving…";

    try {
      const result = await api("POST", "/api/style-guides/save", { name, guide: guideData });

      // refresh the dropdown
      const guideSelect = document.getElementById("set-style_guide");
      guideSelect.innerHTML = result.guides.map((g) => `<option value="${g}">${g}</option>`).join("");
      guideSelect.value = result.saved;

      // persist to server settings
      await api("POST", "/api/settings", { style_guide: result.saved });

      closeModal();
      if (window.PersonaeApp && window.PersonaeApp.logLine) {
        window.PersonaeApp.logLine(`Style guide "${result.saved}" imported and saved.`, "success");
      }
    } catch (err) {
      alert(`Save failed: ${err.message}`);
    } finally {
      btnSave.disabled = false;
      btnSave.textContent = "Save Guide";
    }
  });

  window.GuideImport = { openModal };
})();
