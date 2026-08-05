// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * First-run onboarding tips — shown once when the user first opens the app.
 * Persists dismissal in localStorage and (optionally) server-side settings
 * so it never shows again.  A "Don't show this again" checkbox lets the
 * user opt out permanently; clicking "Got it" without the checkbox only
 * closes for this session.
 */

const Onboarding = (function () {
  const STORAGE_KEY = "ocr_onboarding_dismissed";
  const SESSION_KEY = "ocr_onboarding_session_closed";

  const tips = [
    { icon: "▶", label: "Run Pipeline", desc: "Add files, select steps (OCR / Cleanup / Translate), and press Run." },
    { icon: "📄", label: "Tropy Integration", desc: "Use 'Add from Tropy' to pull pages, and 'Send to Tropy' to write results back." },
    { icon: "📋", label: "Templates", desc: "Save step/option combinations as named templates in Settings → Run Templates." },
    { icon: "🖼", label: "Preview & History", desc: "Preview items with source image and editable text. History shows past runs." },
    { icon: "📑", label: "PDF Export", desc: "Compile processed text files into a reading PDF or Markdown from the Main tab." },
    { icon: "🔍", label: "OCR Engine", desc: "By default, images are read using a local AI model via LM Studio. You can also configure PaddleOCR or Tesseract 4 as alternatives in Settings." },
    { icon: "⌨", label: "Quick Actions", desc: "Press Ctrl+K to search tabs, actions, and templates instantly." },
    { icon: "🌙", label: "Dark Mode", desc: "Click the moon icon (top-right) or use Quick Actions to toggle themes." },
  ];

  function isDismissed() {
    return localStorage.getItem(STORAGE_KEY) === "1"
        || sessionStorage.getItem(SESSION_KEY) === "1";
  }

  function dismiss(permanent) {
    if (permanent) {
      localStorage.setItem(STORAGE_KEY, "1");
      // Also persist server-side so it survives browser cache clears.
      try { api("POST", "/api/config", { onboarding_dismissed: true }); } catch (_) {}
    } else {
      sessionStorage.setItem(SESSION_KEY, "1");
    }
    const overlay = document.getElementById("onboarding-overlay");
    if (overlay) overlay.classList.add("hidden");
  }

  function show() {
    if (isDismissed()) return;

    let overlay = document.getElementById("onboarding-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "onboarding-overlay";
      overlay.className = "onboarding-overlay";
      overlay.innerHTML = `
        <div class="onboarding-card">
          <h2>Welcome to ArtificeOCR</h2>
          <p class="dim" style="margin:0 0 1rem;">Here's what you can do — this only shows once.</p>
          <div class="onboarding-tips">
            ${tips.map(t => `
              <div class="tip">
                <span class="tip-icon">${t.icon}</span>
                <div><strong>${t.label}</strong> — ${t.desc}</div>
              </div>`).join("")}
          </div>
          <div class="onboarding-actions">
            <label class="check" style="margin-right:auto; font-size:var(--text-sm);">
              <input type="checkbox" id="onboarding-dont-show" checked> Don't show this again
            </label>
            <button class="btn accent" id="btn-onboarding-gotit">Got it</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) {
          const cb = document.getElementById("onboarding-dont-show");
          dismiss(cb && cb.checked);
        }
      });
      document.getElementById("btn-onboarding-gotit").addEventListener("click", () => {
        const cb = document.getElementById("onboarding-dont-show");
        dismiss(cb && cb.checked);
      });
    } else {
      overlay.classList.remove("hidden");
    }
  }

  // Auto-show after a short delay if not dismissed
  setTimeout(() => show(), 600);

  function retrigger() {
    localStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(SESSION_KEY);
    show();
  }

  return { show, dismiss, isDismissed, retrigger };
})();

window.Onboarding = Onboarding;
