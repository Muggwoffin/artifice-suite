/* SPDX-FileCopyrightText: 2026 Maurice Casey
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

/* window-controls.js — Reveals and wires the frameless-PyWebView window
 * controls injected by _masthead.html.
 *
 * The buttons are rendered with display:none by masthead.css.  When PyWebView
 * fires the pywebviewready event, this IIFE adds the .pywebview-active class
 * to <html> (which the CSS keys off to show the controls) and wires the
 * Minimize / Close buttons to the JS-Python bridge.
 *
 * Expected Python-side API (to be exposed via webview.create_window(...,
 * js_api=api_instance)):
 *
 *   class Api:
 *       def minimize(self):
 *           webview.windows[0].minimize()
 *
 *       def destroy(self):
 *           webview.windows[0].destroy()
 *
 * In a standard browser pywebviewready never fires, so the buttons stay
 * hidden and the page is unchanged.
 *
 * ES5-compatible: no const/let, arrow functions, or template literals.
 */
(function () {
  "use strict";

  function callPywebview(name) {
    if (
      typeof window.pywebview !== "undefined" &&
      window.pywebview !== null &&
      typeof window.pywebview.api !== "undefined" &&
      window.pywebview.api !== null &&
      typeof window.pywebview.api[name] === "function"
    ) {
      window.pywebview.api[name]();
      return true;
    }
    return false;
  }

  function onPywebviewReady() {
    var root = document.documentElement;
    if (root) {
      var cls = " " + root.className + " ";
      if (cls.indexOf(" pywebview-active ") === -1) {
        root.className = root.className + " pywebview-active";
      }
    }

    function stopDrag(e) {
      if (e && typeof e.stopPropagation === "function") {
        e.stopPropagation();
      }
    }

    var minimizeBtn = document.getElementById("windowMinimize");
    var closeBtn = document.getElementById("windowClose");

    if (minimizeBtn) {
      minimizeBtn.onmousedown = stopDrag;
      minimizeBtn.onclick = function () {
        callPywebview("minimize");
      };
    }

    if (closeBtn) {
      closeBtn.onmousedown = stopDrag;
      closeBtn.onclick = function () {
        if (!callPywebview("destroy")) {
          if (typeof window.close === "function") {
            window.close();
          }
        }
      };
    }
  }

  if (typeof window.addEventListener === "function") {
    window.addEventListener("pywebviewready", onPywebviewReady, false);
  } else if (typeof window.attachEvent === "function") {
    window.attachEvent("onpywebviewready", onPywebviewReady);
  }
})();
