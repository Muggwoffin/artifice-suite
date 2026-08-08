// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * "Send to Draft" / "Send to Graph" handoff buttons for the Preview tab.
 *
 * When OCR extraction is complete and the user is viewing the extracted
 * text, these buttons write a handoff package to the shared platformdirs
 * directory and notify the target app to import it.
 */

(function () {
  "use strict";

  var btnSendDraft = document.getElementById("btn-send-draft");
  var btnSendGraph = document.getElementById("btn-send-graph");

  if (!btnSendDraft && !btnSendGraph) return;

  var TARGETS = {
    draft: { slug: "artifice-draft", label: "Draft" },
    graph: { slug: "artifice-graph", label: "Graph" },
  };

  /**
   * Grab the currently displayed text from the Preview tab's editable
   * textarea (cleaned text if available, raw OCR otherwise).
   */
  function getCurrentText() {
    // Try cleaned text first
    var cleanedPane = document.querySelector('.compare-pane[data-pane="cleaned"] .raw-edit');
    if (cleanedPane && cleanedPane.value && cleanedPane.value.trim()) {
      return cleanedPane.value;
    }
    // Fall back to raw OCR
    var rawPane = document.querySelector('.compare-pane[data-pane="raw"] .raw-edit');
    if (rawPane && rawPane.value && rawPane.value.trim()) {
      return rawPane.value;
    }
    return "";
  }

  /**
   * Check whether the target app is running by asking the OCR server to
   * read its discovery file.
   */
  function checkRunning(slug, callback) {
    fetch("/api/handoff/discovery/" + encodeURIComponent(slug))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        callback(null, data);
      })
      .catch(function (err) {
        callback(err, null);
      });
  }

  /**
   * Enable the "Send to" buttons when a document is being previewed with
   * actual text available.
   */
  function updateButtonState() {
    var text = getCurrentText();
    var hasText = text.length > 10; // require some meaningful text
    if (btnSendDraft) btnSendDraft.disabled = !hasText;
    if (btnSendGraph) btnSendGraph.disabled = !hasText;
  }

  /**
   * Send extracted text to a target app via the handoff mechanism.
   */
  function sendTo(target) {
    var cfg = TARGETS[target];
    if (!cfg) return;

    var text = getCurrentText();
    if (!text) {
      if (window.ArtificeToast) {
        window.ArtificeToast.warning("No text to send. Select a document in the Preview tab first.", { duration: 3000 });
      }
      return;
    }

    var btn = target === "draft" ? btnSendDraft : btnSendGraph;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Sending\u2026";
    }

    checkRunning(cfg.slug, function (err, data) {
      if (err || !data || !data.running) {
        if (window.ArtificeToast) {
          window.ArtificeToast.warning(cfg.label + " is not running \u2014 launch it from the Hub first.", { duration: 0 });
        }
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Send to " + cfg.label;
        }
        return;
      }

      // Create the handoff package on the server side
      fetch("/api/handoff/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target: cfg.slug,
          body: text,
        }),
      })
        .then(function (r) { return r.json(); })
        .then(function (result) {
          if (result.error) {
            throw new Error(result.error);
          }

          // Notify the target app by fetching its import URL
          var notifyUrl = "http://127.0.0.1:" + data.port + "/import?handoff=" + encodeURIComponent(result.uuid);
          return fetch(notifyUrl, { mode: "no-cors" }).then(function () { return result; });
        })
        .then(function (result) {
          if (window.ArtificeToast) {
            window.ArtificeToast.success("Sent to " + cfg.label, { duration: 3000 });
          }
        })
        .catch(function (err) {
          if (window.ArtificeToast) {
            window.ArtificeToast.error("Send failed: " + (err.message || "Could not reach " + cfg.label), { duration: 0 });
          }
        })
        .finally(function () {
          if (btn) {
            btn.disabled = false;
            btn.textContent = "Send to " + cfg.label;
          }
        });
    });
  }

  // ── Wire buttons ──────────────────────────────────────────────────
  if (btnSendDraft) {
    btnSendDraft.addEventListener("click", function () { sendTo("draft"); });
  }
  if (btnSendGraph) {
    btnSendGraph.addEventListener("click", function () { sendTo("graph"); });
  }

  // ── Keep button state in sync with what's in the preview pane ─────
  var previewContainer = document.getElementById("panel-preview");
  if (previewContainer) {
    // Observe DOM changes in the preview panel to re-check button state
    var observer = new MutationObserver(function () {
      updateButtonState();
    });
    observer.observe(previewContainer, { childList: true, subtree: true, characterData: true });
  }

  // Initial check
  updateButtonState();
})();
