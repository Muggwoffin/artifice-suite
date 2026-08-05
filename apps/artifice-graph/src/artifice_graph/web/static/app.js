// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/* app.js — shared, theme toggle + motion guard + tiny helpers. IIFE-wrapped, ES5-safe. */
(function () {
  "use strict";

  function getPref(name) {
    try { return window.localStorage.getItem(name); } catch (e) { return null; }
  }
  function setPref(name, val) {
    try { window.localStorage.setItem(name, val); } catch (e) {}
  }

  function applyTheme(theme) {
    var html = document.documentElement;
    html.setAttribute("data-theme", theme);
    var g = document.getElementById("themeGlyph");
    if (!g) return;
    var sun = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
    var moon = '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>';
    g.innerHTML = theme === "dark" ? moon : sun;
  }

  function applyMotion(reduce) {
    document.documentElement.setAttribute("data-reduce-motion", reduce ? "true" : "false");
  }

  function init() {
    var savedTheme = getPref("artifice-graph-theme");
    if (!savedTheme) {
      var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
      savedTheme = prefersDark ? "dark" : "light";
    }
    applyTheme(savedTheme);

    var toggle = document.getElementById("themeToggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var cur = document.documentElement.getAttribute("data-theme") || "light";
        applyTheme(cur === "dark" ? "light" : "dark");
        setPref("artifice-graph-theme", cur === "dark" ? "light" : "dark");
      });
    }

    var motionPref = getPref("artifice-graph-reduce-motion");
    if (motionPref === null && window.matchMedia) {
      motionPref = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "true" : "false";
    }
    applyMotion(motionPref === "true");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }

  window.Callopp = {
    setStatus: setStatus,
    escapeHtml: escapeHtml,
    fetchJson: fetchJson
  };

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function setStatus(el, state, text) {
    if (!el) return;
    el.setAttribute("data-state", state);
    if (typeof text === "string") { el.querySelector("[data-status-text]").textContent = text; }
  }

  function fetchJson(url, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    if (opts.body && typeof opts.body !== "string") {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    return window.fetch(url, opts).then(function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return { error: "HTTP " + r.status }; })
          .then(function (d) { throw new Error(d.error || ("HTTP " + r.status)); });
      }
      return r.json();
    });
  }
})();