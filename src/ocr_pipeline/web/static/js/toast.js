/*
 * Toast notification system — non-blocking messages that appear in the
 * top-right corner and auto-dismiss. Intentionally lightweight: no
 * framework, no dependencies, just DOM + CSS animations.
 */

const Toast = (function () {
  let container = null;

  function ensureContainer() {
    if (!container) {
      container = document.createElement("div");
      container.className = "toast-container";
      document.body.appendChild(container);
    }
    return container;
  }

  /**
   * Show a toast message.
   * @param {string} message - The message to display.
   * @param {string} [type] - "accent" | "warning" | "error" | "" (default).
   * @param {number} [duration] - Auto-dismiss after ms (default 3500).
   */
  function show(message, type, duration) {
    const c = ensureContainer();
    const el = document.createElement("div");
    el.className = `toast ${type || ""}`;
    el.textContent = message;
    c.appendChild(el);

    const ms = duration ?? (type === "error" ? 6000 : 3500);
    setTimeout(() => {
      el.classList.add("toast-out");
      el.addEventListener("animationend", () => el.remove());
    }, ms);
  }

  return {
    show,
    accent: (msg, dur) => show(msg, "accent", dur),
    warning: (msg, dur) => show(msg, "warning", dur),
    error: (msg, dur) => show(msg, "error", dur),
    info: (msg, dur) => show(msg, "", dur),
  };
})();

window.Toast = Toast;
