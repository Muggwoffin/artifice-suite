// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/* library.js — library-view interaction logic for Artifice Graph.
 *
 * Extracted from the inline <script> block in library.html (commit
 * e74d243 incident: event bindings split across an inline template script
 * and external *.js files caused "five dead controls" to go undetected
 * by audits that scanned only static/*.js). All five binding surfaces are
 * now in this external file with no event-binding code remaining inline.
 *
 * The five relocated controls are:
 *   1. Tab switching (.tab click → aria-selected, pane show/hide, filterLibrary)
 *   2. refresh-map button (initOrRefreshMap)
 *   3. Entity row click (inline drawer expand/collapse)
 *   4. Filter pill click (activeTypeFilter + filterLibrary)
 *   5. Search input (input → filterLibrary)
 *
 * Also includes initOrRefreshMap (map state + fetch /api/map-entities with
 * the same silent-fetch bug present in the original inline script — that
 * specific bug was not listed in the three confirmed patterns and will be
 * fixed separately under the apiFetch sweep).
 */

(function () {
  "use strict";

  // Guard: this module is only loaded on library.html, but wrap in onReady
  // anyway so the script tag can stay in base.html alongside pipeline.js.
  window.ArtificeBind.onReady(function () {

    // Set marker image path for vendored Leaflet
    if (typeof L !== "undefined") {
      L.Icon.Default.prototype.options.imagePath = "/static/vendor/leaflet/images/";
    }

    var tabs = document.querySelectorAll(".tab");
    var panes = {
      entities: document.getElementById("tab-entities"),
      relationships: document.getElementById("tab-relationships"),
      documents: document.getElementById("tab-documents"),
      map: document.getElementById("tab-map")
    };
    var currentTab = "entities";
    var mapInstance = null;
    var markersLayer = null;

    // 1. Tab switching
    Array.prototype.forEach.call(tabs, function (t) {
      t.addEventListener("click", function () {
        var key = t.getAttribute("data-tab");
        currentTab = key;
        Array.prototype.forEach.call(tabs, function (x) {
          x.setAttribute("aria-selected", x === t ? "true" : "false");
        });
        Object.keys(panes).forEach(function (k) {
          panes[k].hidden = (k !== key);
        });
        var filterRow = document.getElementById("entityFilterRow");
        if (filterRow) {
          filterRow.style.display = (key === "entities") ? "flex" : "none";
        }
        filterLibrary();

        if (key === "map") {
          setTimeout(initOrRefreshMap, 200);
        }
      });
    });

    // 2. refresh-map button
    window.ArtificeBind.bindIfPresent("refreshMapBtn", "click", initOrRefreshMap);

    function initOrRefreshMap() {
      var container = document.getElementById("mapContainer");
      if (!container) return;

      if (!mapInstance) {
        mapInstance = L.map("mapContainer").setView([50.0, 10.0], 4);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 18,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(mapInstance);
        markersLayer = L.layerGroup().addTo(mapInstance);
      } else {
        mapInstance.invalidateSize();
      }

      var modeSelect = document.getElementById("mapModeSelect");
      var mode = modeSelect ? modeSelect.value : "approx";
      var statusEl = document.getElementById("mapStatus");
      if (statusEl) statusEl.textContent = "Loading location entities...";

      fetch("/api/map-entities?mode=" + mode)
        .then(function (res) { return res.json(); })
        .then(function (data) {
          markersLayer.clearLayers();
          var locations = data.locations || [];
          if (locations.length === 0) {
            if (statusEl) statusEl.textContent = "No location entities found in output or coordinates could not be resolved.";
            return;
          }

          var bounds = [];
          locations.forEach(function (loc) {
            var lat = loc.lat;
            var lng = loc.lng;
            bounds.push([lat, lng]);

            var popupHtml = '<div>' +
              '<h4>' + escapeHtml(loc.name) + '</h4>' +
              '<p style="margin: 0 0 0.5rem 0; font-size: 0.85rem;">' + escapeHtml(loc.summary || "No summary.") + '</p>' +
              '<div style="font-size: 0.75rem; color: var(--ink-faint);">Source: ' + escapeHtml(loc.source_method) + '</div>';

            if (loc.relationships && loc.relationships.length > 0) {
              popupHtml += '<div style="margin-top: 0.5rem; font-size: 0.8rem; border-top: 1px solid var(--rule); padding-top: 0.3rem;"><strong>Relations:</strong><ul style="margin: 0.2rem 0 0 1rem; padding: 0;">';
              loc.relationships.slice(0, 3).forEach(function (r) {
                popupHtml += '<li>' + escapeHtml(r.source_entity) + ' ' + escapeHtml(r.relationship_type) + ' ' + escapeHtml(r.target_entity) + '</li>';
              });
              popupHtml += '</ul></div>';
            }
            popupHtml += '</div>';

            var marker = L.marker([lat, lng]).bindPopup(popupHtml);
            markersLayer.addLayer(marker);
          });

          if (bounds.length > 0) {
            mapInstance.fitBounds(bounds, { padding: [50, 50], maxZoom: 6 });
          }
          if (statusEl) {
            statusEl.textContent = "Successfully mapped " + locations.length + " location entity(ies) using " + mode + " mode.";
          }
        })
        .catch(function (err) {
          if (statusEl) statusEl.textContent = "Error loading map data: " + err.message;
        });
    }

    function escapeHtml(str) {
      return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    // 3. Inline Entity Drawer (row click)
    var entityRows = document.querySelectorAll(".entity-row");
    Array.prototype.forEach.call(entityRows, function (row) {
      row.addEventListener("click", function () {
        var drawerRow = row.nextElementSibling;
        if (!drawerRow || !drawerRow.classList.contains("entity-drawer-row")) return;
        var isHidden = drawerRow.hidden;
        Array.prototype.forEach.call(document.querySelectorAll(".entity-drawer-row"), function (dr) {
          dr.hidden = true;
          if (dr.previousElementSibling) dr.previousElementSibling.setAttribute("aria-expanded", "false");
        });
        if (isHidden) {
          drawerRow.hidden = false;
          row.setAttribute("aria-expanded", "true");
        }
      });
    });

    // 4. Filter pill click
    var filterPills = document.querySelectorAll("#entityFilterRow .sort-pill");
    var activeTypeFilter = "all";

    Array.prototype.forEach.call(filterPills, function (pill) {
      pill.addEventListener("click", function () {
        Array.prototype.forEach.call(filterPills, function (p) {
          p.setAttribute("aria-pressed", p === pill ? "true" : "false");
        });
        activeTypeFilter = pill.getAttribute("data-filter");
        filterLibrary();
      });
    });

    // 5. Search input
    var searchInput = document.getElementById("libSearch");
    if (searchInput) {
      searchInput.addEventListener("input", filterLibrary);
    }

    function filterLibrary() {
      var query = (searchInput ? searchInput.value : "").toLowerCase().trim();

      if (currentTab === "entities") {
        var visibleCount = 0;
        var rows = document.querySelectorAll(".entity-row");
        Array.prototype.forEach.call(rows, function (row) {
          var name = row.getAttribute("data-name") || "";
          var type = row.getAttribute("data-type") || "";
          var aliases = row.getAttribute("data-aliases") || "";
          var summary = row.getAttribute("data-summary") || "";

          var matchesQuery = !query || name.indexOf(query) !== -1 || aliases.indexOf(query) !== -1 || summary.indexOf(query) !== -1;
          var matchesType = activeTypeFilter === "all" || type === activeTypeFilter;

          var shouldShow = matchesQuery && matchesType;
          row.style.display = shouldShow ? "" : "none";
          var drawerRow = row.nextElementSibling;
          if (!shouldShow && drawerRow && drawerRow.classList.contains("entity-drawer-row")) {
            drawerRow.hidden = true;
            row.setAttribute("aria-expanded", "false");
          }
          if (shouldShow) visibleCount++;
        });
        var emptyEl = document.getElementById("entityEmptyState");
        if (emptyEl) emptyEl.hidden = (visibleCount > 0);
      } else if (currentTab === "relationships") {
        var relVisible = 0;
        var relRows = document.querySelectorAll(".rel-row");
        Array.prototype.forEach.call(relRows, function (row) {
          var text = row.getAttribute("data-search") || "";
          var matches = !query || text.indexOf(query) !== -1;
          row.style.display = matches ? "" : "none";
          if (matches) relVisible++;
        });
        var relEmpty = document.getElementById("relEmptyState");
        if (relEmpty) relEmpty.hidden = (relVisible > 0);
      } else if (currentTab === "documents") {
        var docVisible = 0;
        var docCards = document.querySelectorAll(".doc-card");
        Array.prototype.forEach.call(docCards, function (card) {
          var text = card.getAttribute("data-search") || "";
          var matches = !query || text.indexOf(query) !== -1;
          card.style.display = matches ? "" : "none";
          if (matches) docVisible++;
        });
        var docEmpty = document.getElementById("docEmptyState");
        if (docEmpty) docEmpty.hidden = (docVisible > 0);
      }
    }

  }); // end onReady
})();
