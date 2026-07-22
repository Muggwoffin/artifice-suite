/*
 * First-run onboarding tips — shown once when the user first opens the app.
 * Persists dismissal in localStorage so it never shows again.
 */

const Onboarding = (function () {
  const STORAGE_KEY = "ocr_onboarding_dismissed";

  const tips = [
    { icon: "▶", label: "Run Pipeline", desc: "Add files, select stages (OCR / Cleanup / Translate), and press Run." },
    { icon: "📄", label: "Tropy Integration", desc: "Use 'Add from Tropy' to pull pages, and 'Send to Tropy' to write results back." },
    { icon: "📋", label: "Templates", desc: "Save stage/option combos as named templates in Settings → Run Templates." },
    { icon: "🖼", label: "Preview & History", desc: "Preview live queue items with source image + editable raw text. History shows past runs." },
    { icon: "📑", label: "PDF Export", desc: "Compile processed text files into a reading PDF or Markdown from the Main tab." },
    { icon: "⌨", label: "Command Palette", desc: "Press Ctrl+K to search tabs, actions, and templates instantly." },
    { icon: "🌙", label: "Dark Mode", desc: "Click the moon icon (bottom-right) or use the palette to toggle themes." },
  ];

  function isDismissed() {
    return localStorage.getItem(STORAGE_KEY) === "1";
  }

  function dismiss() {
    localStorage.setItem(STORAGE_KEY, "1");
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
          <h2>Welcome to OCR Pipeline</h2>
          <p class="dim" style="margin:0 0 1rem;">Here's what you can do — this only shows once.</p>
          <div class="onboarding-tips">
            ${tips.map(t => `
              <div class="tip">
                <span class="tip-icon">${t.icon}</span>
                <div><strong>${t.label}</strong> — ${t.desc}</div>
              </div>`).join("")}
          </div>
          <div class="onboarding-actions">
            <button class="btn accent" id="btn-onboarding-gotit">Got it</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) dismiss();
      });
      document.getElementById("btn-onboarding-gotit").addEventListener("click", dismiss);
    } else {
      overlay.classList.remove("hidden");
    }
  }

  // Auto-show after a short delay if not dismissed
  setTimeout(() => show(), 600);

  return { show, dismiss, isDismissed };
})();

window.Onboarding = Onboarding;
