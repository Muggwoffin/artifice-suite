// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/* byom.js — Bring-Your-Own-Model onboarding screen.
 *
 * Ships from packages/shared-ui and is loaded by all four apps, which is
 * why this file is written in ES5: artifice-graph's static/app.js (the
 * house style this follows — IIFE, "use strict", a namespace object on
 * `window`) is the only prior shared-JS convention in the suite, but the
 * other three apps run modern JS. ES5 is the floor that runs in all four.
 *
 * Namespacing precedent: this is the first JavaScript packages/shared-ui
 * has ever shipped, so the choice here sets the pattern for anything shared
 * that follows it. graph's own app.js exposes `window.Callopp` — a name
 * that does not derive from "artifice" or "graph" and appears to be a
 * leftover from an unrelated codebase (see ~/.callosip in the maintainer's
 * environment notes). That name is not repeated here. This file exposes a
 * single global, `window.ArtificeByom`, prefixed with the suite name so it
 * cannot collide with any app-local global (app.js, palette.js, etc. in
 * each app already define their own page-scoped identifiers).
 *
 * Unlike app.js's house style, this file does NOT self-initialise on
 * DOMContentLoaded. graph's app.js runs its init() unconditionally because
 * it owns one fixed page. byom.js is a component invoked on demand by four
 * different host pages with four different DOMs — it has nothing to
 * initialise until a caller asks for it. The public surface is a factory:
 *
 *   var byom = window.ArtificeByom.create({
 *     appName: "OCR Pipeline",
 *     onConfigured: function (result) { ... }   // called after a
 *                                                // successful Test connection
 *   });
 *   byom.open();
 *
 * `create()` builds nothing until `open()` is called, and `open()` can be
 * called again after `close()` — each call re-fetches state so the screen
 * never shows stale detection results.
 *
 * Talks to the /api/byom/* contract defined in the phase6 brief (not yet
 * implemented — see server-side TODO for Step 4). A caller may override the
 * transport via `opts.fetchImpl`, which is how the dev-only preview route
 * in artifice-ocr exercises every state with fixture data and no backend:
 * `fetchImpl(url, opts)` must return a Promise that resolves to the
 * *parsed* JSON body (matching packages/model-harness's dataclasses field
 * for field), not a Response object. The default implementation wraps
 * window.fetch to satisfy that contract.
 *
 * KNOWN CONTRACT MISMATCH, deliberately not resolved silently: the brief's
 * GET /api/byom/state example shows each recommendation as
 * `{ name, why, size_bytes }`. model_harness.registry.ModelRecommendation
 * (registry.py:167-181) has no `why` or `size_bytes` field at all, and
 * calls the model identifier `model_name`, not `name` — only
 * AsrModelInfo (a different dataclass, for artifice-transcribe) carries
 * size_bytes. This file reads `model_name` and `min_vram_gb`, the fields
 * the dataclass actually has, rather than the brief's example shape, per
 * the brief's own instruction to mirror model_harness rather than invent a
 * shape the backend cannot produce. Step 4's /api/byom/state handler must
 * serialise ModelRecommendation with these field names (or the route can
 * rename them in its response — either way, `why`/`size_bytes` cannot
 * come from this dataclass as it stands today).
 */

(function () {
  "use strict";

  // ── Motion ────────────────────────────────────────────────────────────
  // Design_Philosophy.md §7 line 501: JS-driven animation must check
  // reduced-motion before triggering, not rely solely on the CSS media
  // query catching it.

  function prefersReducedMotion() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  // ── Small helpers ────────────────────────────────────────────────────

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      var map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
      return map[c];
    });
  }

  function qs(root, sel) { return root.querySelector(sel); }
  function qsa(root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }

  function elFromHtml(html) {
    var wrap = document.createElement("div");
    wrap.innerHTML = html;
    return wrap.firstElementChild;
  }

  // Default transport: real fetch, parsed to JSON, contract-uniform with
  // the fixture-backed override the preview route supplies (see file
  // header). Throws on non-2xx with the server's own `hint`/`error` field
  // as the message, so callers never have to branch on status separately.
  function defaultFetchImpl(url, opts) {
    opts = opts || {};
    var headers = opts.headers || {};
    var body = opts.body;
    if (body && typeof body !== "string") {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    return window.fetch(url, {
      method: opts.method || "GET",
      headers: headers,
      body: body
    }).then(function (r) {
      return r.json()["catch"](function () { return {}; }).then(function (data) {
        if (!r.ok) {
          var message = (data && (data.hint || data.error)) || ("HTTP " + r.status);
          var err = new Error(message);
          err.status = r.status;
          err.data = data;
          throw err;
        }
        return data;
      });
    });
  }

  function copyToClipboard(text) {
    if (window.navigator && window.navigator.clipboard && window.navigator.clipboard.writeText) {
      return window.navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      try {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        var ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (ok) { resolve(); } else { reject(new Error("copy command failed")); }
      } catch (e) {
        reject(e);
      }
    });
  }

  // ── Static content: hardware tiers ──────────────────────────────────
  // Values match model_harness.registry.HardwareTier exactly (laptop,
  // desktop, mac_unified) — see packages/model-harness/src/model_harness/
  // registry.py. Icons are line-drawn per Design_Philosophy.md §8.8 (viewBox
  // 0 0 24 24, stroke=currentColor, stroke-width 2, round caps, aria-hidden).
  // No product screenshots or trademarked logos — see the brief's
  // "no screenshots" decision; the Apple Silicon tier is represented as a
  // generic chip-with-pins glyph, not an Apple mark.

  var ICON_LAPTOP =
    '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<rect x="4" y="4" width="16" height="10" rx="1"></rect>' +
    '<path d="M2 18h20l-2 2H4l-2-2z"></path>' +
    "</svg>";

  var ICON_DESKTOP =
    '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<rect x="6" y="3" width="12" height="18" rx="1"></rect>' +
    '<line x1="9" y1="7" x2="15" y2="7"></line>' +
    '<line x1="9" y1="11" x2="15" y2="11"></line>' +
    '<circle cx="12" cy="17" r="1"></circle>' +
    "</svg>";

  var ICON_CHIP =
    '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<rect x="6" y="6" width="12" height="12" rx="1"></rect>' +
    '<line x1="9" y1="2" x2="9" y2="6"></line><line x1="15" y1="2" x2="15" y2="6"></line>' +
    '<line x1="9" y1="18" x2="9" y2="22"></line><line x1="15" y1="18" x2="15" y2="22"></line>' +
    '<line x1="2" y1="9" x2="6" y2="9"></line><line x1="2" y1="15" x2="6" y2="15"></line>' +
    '<line x1="18" y1="9" x2="22" y2="9"></line><line x1="18" y1="15" x2="22" y2="15"></line>' +
    "</svg>";

  var TIERS = [
    { value: "laptop", label: "Laptop", hint: "8–16GB memory, built-in graphics", icon: ICON_LAPTOP },
    { value: "desktop", label: "Desktop", hint: "A dedicated graphics card (12GB+ VRAM)", icon: ICON_DESKTOP },
    { value: "mac_unified", label: "Apple Silicon Mac", hint: "M-series chip, unified memory", icon: ICON_CHIP }
  ];

  var ICON_CLOSE =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<line x1="4" y1="4" x2="20" y2="20"></line><line x1="20" y1="4" x2="4" y2="20"></line></svg>';

  var ICON_COPY =
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<rect x="9" y="9" width="11" height="11" rx="1"></rect>' +
    '<path d="M5 15H4a1 1 0 01-1-1V4a1 1 0 011-1h10a1 1 0 011 1v1"></path></svg>';

  var ICON_CHECK =
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>';

  var ICON_FAIL =
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<circle cx="12" cy="12" r="9"></circle><line x1="9" y1="9" x2="15" y2="15"></line><line x1="15" y1="9" x2="9" y2="15"></line></svg>';

  // No icon glyph for the detect callout's states — an earlier version had
  // one (a "seeking" magnifying glass, a plain dot, a warning triangle) but
  // at rendered size it read as a stray bullet or broken glyph rather than
  // an intentional mark. See the matching comment on .byom-detect in
  // byom.css: the callout now uses a left accent rule instead, and the
  // state's full meaning lives in the text (role="status" aria-live).

  var TIER_STORAGE_KEY = "artifice_byom_hardware_tier";

  function getStoredTier() {
    try { return window.localStorage.getItem(TIER_STORAGE_KEY); } catch (e) { return null; }
  }
  function setStoredTier(tier) {
    try { window.localStorage.setItem(TIER_STORAGE_KEY, tier); } catch (e) { /* ignore */ }
  }

  // ── Byom ─────────────────────────────────────────────────────────────

  function Byom(opts) {
    opts = opts || {};
    this.appName = opts.appName || document.title || "this app";
    this.fetchImpl = opts.fetchImpl || defaultFetchImpl;
    this.onConfigured = typeof opts.onConfigured === "function" ? opts.onConfigured : function () {};
    // Whether Escape / overlay-click / the close button may dismiss the
    // screen. Step 4's first-run interception may want this false until a
    // model is configured; defaults true so the screen is dismissable
    // during this preview/implementation phase.
    this.dismissable = opts.dismissable !== false;

    this.overlay = null;
    this.modal = null;
    this.lastFocused = null;
    this.state = null;
    this.selectedTier = getStoredTier() || "laptop";

    this._onKeydown = this._onKeydown.bind(this);
    this._onOverlayClick = this._onOverlayClick.bind(this);
  }

  // -- lifecycle -----------------------------------------------------------

  Byom.prototype.open = function (openOpts) {
    openOpts = openOpts || {};
    if (this.overlay) { this.close(); }

    this.lastFocused = document.activeElement;
    this._build();
    document.body.appendChild(this.overlay);

    if (prefersReducedMotion()) {
      this.modal.style.animation = "none";
    }

    document.addEventListener("keydown", this._onKeydown, true);
    this.overlay.addEventListener("mousedown", this._onOverlayClick);

    if (openOpts.initialTab === "advanced") {
      this._activateTab("advanced");
    }

    // Focus the close button: always present, gives a predictable first
    // stop for both keyboard and screen-reader users, and is announced
    // alongside the dialog's role/label.
    this.closeBtn.focus();

    this._refresh(openOpts.autoTest);
  };

  Byom.prototype.close = function () {
    if (!this.overlay) return;
    document.removeEventListener("keydown", this._onKeydown, true);
    this.overlay.removeEventListener("mousedown", this._onOverlayClick);
    if (this.overlay.parentNode) { this.overlay.parentNode.removeChild(this.overlay); }
    this.overlay = null;
    this.modal = null;
    if (this.lastFocused && typeof this.lastFocused.focus === "function") {
      this.lastFocused.focus();
    }
  };

  // -- keyboard / focus trap ------------------------------------------------

  Byom.prototype._onOverlayClick = function (e) {
    if (e.target === this.overlay && this.dismissable) { this.close(); }
  };

  Byom.prototype._focusableEls = function () {
    var sel = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), ' +
      'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    return qsa(this.modal, sel).filter(function (el) {
      return el.offsetWidth > 0 || el.offsetHeight > 0 || el === document.activeElement;
    });
  };

  Byom.prototype._onKeydown = function (e) {
    if (!this.overlay) return;
    var key = e.key || (e.keyCode === 27 ? "Escape" : (e.keyCode === 9 ? "Tab" : ""));
    if (key === "Escape") {
      if (this.dismissable) { this.close(); }
      return;
    }
    if (key === "Tab") {
      var items = this._focusableEls();
      if (items.length === 0) { e.preventDefault(); return; }
      var first = items[0];
      var last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    }
  };

  // -- markup ---------------------------------------------------------------

  Byom.prototype._build = function () {
    var self = this;

    var tierCards = TIERS.map(function (t) {
      return (
        '<label class="byom-tier-card" data-tier="' + t.value + '">' +
        '<input type="radio" name="byom-tier" class="byom-tier-radio" value="' + t.value + '">' +
        // Non-colour selection indicator (§9) — a filled check badge,
        // opacity-toggled by .is-checked / :has() in byom.css. Never
        // display:none, so it costs no layout when it appears.
        '<span class="byom-tier-check" aria-hidden="true">' + ICON_CHECK + "</span>" +
        '<span class="byom-tier-figure">' + t.icon + "</span>" +
        '<span class="byom-tier-name">' + escapeHtml(t.label) + "</span>" +
        '<span class="byom-tier-hint">' + escapeHtml(t.hint) + "</span>" +
        "</label>"
      );
    }).join("");

    var html =
      '<div class="byom-overlay" role="presentation">' +
      '<div class="byom-modal" role="dialog" aria-modal="true" aria-labelledby="byomTitle" aria-describedby="byomLede">' +
      '<div class="byom-modal-inner">' +
      // Visually-hidden live region for state changes that a visible label
      // alone would not announce — the copy buttons below change their
      // *visible* text ("Copy" -> "Copied") but keep a static aria-label
      // ("Copy command"), and aria-label wins the accessible-name
      // computation over content, so a screen-reader user would otherwise
      // never hear the confirmation.
      '<div class="byom-sr-only" id="byomSrStatus" role="status" aria-live="polite"></div>' +
      '<div class="byom-head">' +
      '<h2 class="byom-title" id="byomTitle">Connect a local model</h2>' +
      '<button type="button" class="byom-close" id="byomClose" aria-label="Close">' + ICON_CLOSE + "</button>" +
      "</div>" +
      '<p class="byom-lede" id="byomLede">' + escapeHtml(this.appName) +
      " runs entirely on your machine. To do its work it needs a language model &mdash; but instead of " +
      "shipping one, you connect your own: a small program that runs on this computer, so nothing you " +
      "process here is ever sent anywhere else.</p>" +
      '<div class="byom-detect" id="byomDetect" data-state="detecting" role="status" aria-live="polite">' +
      '<div class="byom-detect-inner">' +
      '<span class="byom-detect-text" id="byomDetectText">Looking for a model server on your machine&hellip;</span>' +
      "</div>" +
      '<div class="byom-detect-actions" id="byomDetectActions"></div>' +
      "</div>" +
      '<div class="byom-tabs" role="tablist" aria-label="Setup path">' +
      '<button type="button" class="byom-tab" id="byomTabBeginner" role="tab" aria-selected="true" ' +
      'aria-controls="byomPanelBeginner">New to this</button>' +
      '<button type="button" class="byom-tab" id="byomTabAdvanced" role="tab" aria-selected="false" ' +
      'aria-controls="byomPanelAdvanced" tabindex="-1">Done this before</button>' +
      "</div>" +
      '<div class="byom-panel" id="byomPanelBeginner" role="tabpanel" aria-labelledby="byomTabBeginner">' +
      '<fieldset class="byom-tier">' +
      '<legend class="byom-tier-legend">What machine are you using?</legend>' +
      '<div class="byom-tier-grid" id="byomTierGrid">' + tierCards + "</div>" +
      "</fieldset>" +
      '<ol class="byom-steps" id="byomSteps"></ol>' +
      "</div>" +
      '<div class="byom-panel" id="byomPanelAdvanced" role="tabpanel" aria-labelledby="byomTabAdvanced" hidden>' +
      '<p class="byom-advanced-lede">Commands are grouped by hardware &mdash; use the block that matches yours.</p>' +
      // Stated once: Ollama/LM Studio's ports don't vary by hardware tier,
      // so this used to repeat verbatim under all three groups below.
      '<p class="byom-endpoints-note">Whichever block you use, Ollama listens on ' +
      "<code>http://localhost:11434</code> and LM Studio on <code>http://localhost:1234/v1</code>.</p>" +
      '<div id="byomAdvancedGroups"></div>' +
      "</div>" +
      '<div class="byom-connect">' +
      '<h3 class="byom-connect-title">Connect</h3>' +
      '<div class="byom-field">' +
      '<label for="byomUrl">Server URL</label>' +
      '<input type="text" id="byomUrl" class="byom-input" placeholder="http://localhost:11434" autocomplete="off">' +
      "</div>" +
      '<details class="byom-apikey"><summary>API key (optional &mdash; only needed for some servers)</summary>' +
      '<div class="byom-field"><label for="byomApiKey">API key</label>' +
      '<input type="password" id="byomApiKey" class="byom-input" autocomplete="off"></div>' +
      "</details>" +
      '<div class="byom-connect-actions">' +
      '<button type="button" class="byom-btn-primary" id="byomTestBtn">Test connection</button>' +
      '<div class="byom-result" id="byomResult" role="status" aria-live="polite" data-state="idle">Not tested yet.</div>' +
      "</div>" +
      "</div>" +
      "</div></div></div>";

    this.overlay = elFromHtml(html);
    this.modal = qs(this.overlay, ".byom-modal");
    this.closeBtn = qs(this.overlay, "#byomClose");
    this.detectEl = qs(this.overlay, "#byomDetect");
    this.detectText = qs(this.overlay, "#byomDetectText");
    this.detectActions = qs(this.overlay, "#byomDetectActions");
    this.tabBeginner = qs(this.overlay, "#byomTabBeginner");
    this.tabAdvanced = qs(this.overlay, "#byomTabAdvanced");
    this.panelBeginner = qs(this.overlay, "#byomPanelBeginner");
    this.panelAdvanced = qs(this.overlay, "#byomPanelAdvanced");
    this.tierGrid = qs(this.overlay, "#byomTierGrid");
    this.stepsEl = qs(this.overlay, "#byomSteps");
    this.advancedGroupsEl = qs(this.overlay, "#byomAdvancedGroups");
    this.urlInput = qs(this.overlay, "#byomUrl");
    this.apiKeyInput = qs(this.overlay, "#byomApiKey");
    this.testBtn = qs(this.overlay, "#byomTestBtn");
    this.resultEl = qs(this.overlay, "#byomResult");
    this.srStatusEl = qs(this.overlay, "#byomSrStatus");

    this.closeBtn.addEventListener("click", function () { if (self.dismissable) { self.close(); } });
    this.tabBeginner.addEventListener("click", function () { self._activateTab("beginner"); });
    this.tabAdvanced.addEventListener("click", function () { self._activateTab("advanced"); });
    this.tabBeginner.addEventListener("keydown", function (e) { self._onTabKeydown(e); });
    this.tabAdvanced.addEventListener("keydown", function (e) { self._onTabKeydown(e); });

    this.tierGrid.addEventListener("change", function (e) {
      if (e.target && e.target.name === "byom-tier") {
        self.selectedTier = e.target.value;
        setStoredTier(self.selectedTier);
        self._markSelectedTier();
        self._renderSteps();
      }
    });

    this.testBtn.addEventListener("click", function () { self._testConnection(); });

    this.overlay.addEventListener("click", function (e) {
      var copyBtn = e.target.closest ? e.target.closest(".byom-copy") : null;
      if (copyBtn) { self._handleCopy(copyBtn); }
    });
  };

  Byom.prototype._onTabKeydown = function (e) {
    var key = e.key;
    if (key !== "ArrowLeft" && key !== "ArrowRight") return;
    e.preventDefault();
    this._activateTab(document.activeElement === this.tabBeginner ? "advanced" : "beginner");
    (document.activeElement === this.tabBeginner ? this.tabAdvanced : this.tabBeginner).focus();
  };

  Byom.prototype._activateTab = function (name) {
    var beginner = name === "beginner";
    this.tabBeginner.setAttribute("aria-selected", beginner ? "true" : "false");
    this.tabBeginner.setAttribute("tabindex", beginner ? "0" : "-1");
    this.tabAdvanced.setAttribute("aria-selected", beginner ? "false" : "true");
    this.tabAdvanced.setAttribute("tabindex", beginner ? "-1" : "0");
    if (beginner) {
      this.panelBeginner.removeAttribute("hidden");
      this.panelAdvanced.setAttribute("hidden", "");
    } else {
      this.panelAdvanced.removeAttribute("hidden");
      this.panelBeginner.setAttribute("hidden", "");
    }
  };

  // -- data / rendering -------------------------------------------------

  Byom.prototype._refresh = function (autoTest) {
    var self = this;
    this._setDetect("detecting", "Looking for a model server on your machine…");

    this.fetchImpl("/api/byom/state")
      .then(function (state) {
        self.state = state;
        self._renderSteps();
        self._renderAdvancedGroups();
        self._markSelectedTier();
        return self.fetchImpl("/api/byom/detect");
      })
      .then(function (detect) {
        self._renderDetect(detect);
        if (autoTest) { self._testConnection(autoTest.url, autoTest.apiKey); }
      })
      ["catch"](function () {
        self._setDetect("error",
          "Could not check for a local model server automatically. You can still connect one below.");
      });
  };

  Byom.prototype._setDetect = function (state, text) {
    this.detectEl.setAttribute("data-state", state);
    this.detectText.textContent = text;
  };

  Byom.prototype._renderDetect = function (detect) {
    var self = this;
    var endpoints = (detect && detect.endpoints) || [];
    var found = null;
    for (var i = 0; i < endpoints.length; i++) {
      if (endpoints[i].reachable) { found = endpoints[i]; break; }
    }
    this.detectActions.innerHTML = "";
    if (found) {
      var modelCount = (found.models || []).length;
      var modelsText = modelCount
        ? modelCount + " model" + (modelCount === 1 ? "" : "s") + " available"
        : "no models pulled yet";
      this._setDetect("found",
        "Found " + (found.name || found.provider || "a server") + " running locally — " + modelsText + ".");
      var useBtn = elFromHtml('<button type="button" class="byom-btn-primary">Use this endpoint</button>');
      useBtn.addEventListener("click", function () {
        self.urlInput.value = found.url;
        self._testConnection(found.url, "");
      });
      this.detectActions.appendChild(useBtn);
    } else {
      this._setDetect("not-found",
        "No local model server found yet — that's normal on a first run. Follow the steps below.");
    }
  };

  Byom.prototype._markSelectedTier = function () {
    var cards = qsa(this.tierGrid, ".byom-tier-card");
    for (var i = 0; i < cards.length; i++) {
      var isSel = cards[i].getAttribute("data-tier") === this.selectedTier;
      cards[i].classList.toggle("is-checked", isSel);
      var radio = qs(cards[i], ".byom-tier-radio");
      radio.checked = isSel;
    }
  };

  Byom.prototype._recommendationsFor = function (tier) {
    if (!this.state || !this.state.recommendations) return [];
    return this.state.recommendations[tier] || [];
  };

  Byom.prototype._renderSteps = function () {
    var recs = this._recommendationsFor(this.selectedTier);
    var top = recs.length ? recs[0] : null;
    // Field is `model_name`, not `name` — see the file-level note on the
    // /api/byom/state contract mismatch (model_harness.registry
    // .ModelRecommendation has no `name`, `why` or `size_bytes` field; this
    // reads the fields the dataclass actually has: model_name, vision,
    // min_vram_gb).
    var pullCmd = top ? "ollama pull " + top.model_name : "ollama pull llama3.2:3b";
    var whyText = top && top.min_vram_gb
      ? "recommended for machines with at least " + top.min_vram_gb + "GB VRAM"
      : "";

    var steps = [
      {
        title: "Download Ollama",
        desc: "Get the installer for your operating system from ollama.com — it is free and open source. " +
          "(LM Studio is a good alternative if you prefer a graphical model browser.)"
      },
      {
        title: "Install and open it",
        desc: "Ollama runs quietly in the background once installed — there is no window to keep open."
      },
      {
        title: "Pull a model sized for your machine",
        desc: "Open a terminal and run the command below" + (whyText ? " — " + escapeHtml(whyText) : "") + ".",
        code: pullCmd
      },
      {
        title: "Test the connection",
        desc: "Use the Test connection button below once the model has finished downloading."
      }
    ];

    var html = steps.map(function (s, idx) {
      var codeHtml = s.code
        ? '<div class="byom-code-row"><pre class="byom-code"><code>' + escapeHtml(s.code) + "</code></pre>" +
          '<button type="button" class="byom-copy" data-copy="' + escapeHtml(s.code) + '" aria-label="Copy command">' +
          ICON_COPY + "<span>Copy</span></button></div>"
        : "";
      return (
        '<li class="byom-step">' +
        '<span class="byom-step-num" aria-hidden="true">' + (idx + 1) + "</span>" +
        '<div class="byom-step-body">' +
        '<p class="byom-step-title">' + escapeHtml(s.title) + "</p>" +
        '<p class="byom-step-desc">' + s.desc + "</p>" +
        codeHtml +
        "</div></li>"
      );
    }).join("");

    this.stepsEl.innerHTML = html;
  };

  Byom.prototype._renderAdvancedGroups = function () {
    var self = this;
    var html = TIERS.map(function (t) {
      var recs = self._recommendationsFor(t.value);
      var rows = (recs.length ? recs : [{ model_name: "llama3.2:3b" }]).map(function (r) {
        var cmd = "ollama pull " + r.model_name;
        return (
          '<div class="byom-code-row"><pre class="byom-code"><code>' + escapeHtml(cmd) + "</code></pre>" +
          '<button type="button" class="byom-copy" data-copy="' + escapeHtml(cmd) + '" aria-label="Copy command">' +
          ICON_COPY + "<span>Copy</span></button></div>"
        );
      }).join("");
      return (
        '<div class="byom-code-group" data-tier="' + t.value + '">' +
        '<h4 class="byom-code-group-title">' + escapeHtml(t.label) +
        '<span class="byom-code-group-hint">' + escapeHtml(t.hint) + "</span></h4>" +
        rows +
        "</div>"
      );
    }).join("");
    this.advancedGroupsEl.innerHTML = html;
  };

  Byom.prototype._handleCopy = function (btn) {
    var self = this;
    var text = btn.getAttribute("data-copy") || "";
    var label = qs(btn, "span");
    copyToClipboard(text).then(function () {
      btn.setAttribute("data-copied", "true");
      if (label) { label.textContent = "Copied"; }
      // The visible label change above is not itself announced — see the
      // comment on #byomSrStatus in _build for why aria-label wins over
      // content for this button's accessible name.
      if (self.srStatusEl) { self.srStatusEl.textContent = "Command copied to clipboard."; }
      window.setTimeout(function () {
        btn.removeAttribute("data-copied");
        if (label) { label.textContent = "Copy"; }
      }, 1500);
    })["catch"](function () {
      if (label) { label.textContent = "Copy failed"; }
      if (self.srStatusEl) { self.srStatusEl.textContent = "Could not copy the command — copy it manually."; }
      window.setTimeout(function () { if (label) { label.textContent = "Copy"; } }, 1500);
    });
  };

  Byom.prototype._setResult = function (state, text) {
    this.resultEl.setAttribute("data-state", state);
    var icon = state === "ok" ? ICON_CHECK : (state === "fail" ? ICON_FAIL : "");
    this.resultEl.innerHTML = icon ? icon + " " + escapeHtml(text) : escapeHtml(text);
  };

  Byom.prototype._testConnection = function (url, apiKey) {
    var self = this;
    url = url != null ? url : this.urlInput.value.trim();
    apiKey = apiKey != null ? apiKey : (this.apiKeyInput.value || "");
    if (url && this.urlInput.value !== url) { this.urlInput.value = url; }

    if (!url) {
      this._setResult("idle", "Enter a server URL first.");
      return;
    }

    this._setResult("pending", "Testing connection…");
    this.testBtn.disabled = true;

    this.fetchImpl("/api/byom/test", { method: "POST", body: { url: url, api_key: apiKey } })
      .then(function (result) {
        self.testBtn.disabled = false;
        if (result.reachable) {
          var count = (result.models || []).length;
          var modelsText = count
            ? count + " model" + (count === 1 ? "" : "s") + " available"
            : "connected, but no models are pulled yet";
          self._setResult("ok", "Connected — " + modelsText + ".");
          self.onConfigured({ url: url, apiKey: apiKey, provider: result.provider, models: result.models });
        } else {
          self._setResult("fail", result.hint || "Could not reach that server.");
        }
      })
      ["catch"](function (err) {
        self.testBtn.disabled = false;
        self._setResult("fail", (err && err.message) || "Could not reach that server.");
      });
  };

  // ── Public namespace ─────────────────────────────────────────────────

  window.ArtificeByom = {
    create: function (opts) { return new Byom(opts); }
  };
})();
