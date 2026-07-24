/*
 * Guide import: scrape a URL, review the extracted StyleGuide, save it.
 * Relies on the shared `api()` helper from app.js.
 */

(function () {
  const modal = document.getElementById("guide-modal");
  const stepUrl = document.getElementById("step-url");
  const stepReview = document.getElementById("step-review");
  const urlInput = document.getElementById("guide-url");
  const btnScrape = document.getElementById("btn-scrape");
  const btnImport = document.getElementById("btn-import-guide");
  const btnClose = document.getElementById("modal-close");
  const btnBack = document.getElementById("btn-back-url");
  const btnSave = document.getElementById("btn-save-guide");
  const scrapeLog = document.getElementById("scrape-log");

  let scrapedGuide = null;

  function showStep(which) {
    stepUrl.style.display = which === "url" ? "block" : "none";
    stepReview.style.display = which === "review" ? "block" : "none";
  }

  function openModal() {
    modal.style.display = "flex";
    showStep("url");
    urlInput.value = "";
    scrapedGuide = null;
    scrapeLog.innerHTML = "";
    scrapeLog.style.display = "none";
  }

  function closeModal() {
    modal.style.display = "none";
  }

  btnImport.addEventListener("click", openModal);
  btnClose.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  btnBack.addEventListener("click", () => showStep("url"));

  // ------------------------------------------------------------------ scrape
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
      showStep("review");
    } catch (err) {
      scrapeLog.innerHTML += `\n<div class="line error">${escapeHtml(err.message)}</div>`;
    } finally {
      btnScrape.disabled = false;
      btnScrape.textContent = "Scrape & Preview";
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
