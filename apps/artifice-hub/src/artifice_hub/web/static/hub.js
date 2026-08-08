/* SPDX-FileCopyrightText: 2026 Maurice Casey
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 *
 * hub.js — Artifice Hub dashboard controller.
 * Vanilla JS, ES5-compatible, IIFE-wrapped. No frameworks, no build step.
 */
(function () {
    "use strict";

    /* ── State ─────────────────────────────────────────────────────────── */
    var apps = [];
    var hardware = null;
    var uvFound = false;
    var installSlug = null; // slug of the app being installed via modal

    /* ── DOM refs ──────────────────────────────────────────────────────── */
    var $ = function (sel) { return document.querySelector(sel); };
    var $$ = function (sel) { return document.querySelectorAll(sel); };

    var elGrid = $("#app-grid");
    var elJobSection = $("#job-section");
    var elHubVersion = $("#hub-version");
    var elHubUv = $("#hub-uv");
    var elModal = $("#install-modal");
    var elModalTitle = $("#modal-title");
    var elModalClose = $("#modal-close");
    var elModalSkip = $("#modal-skip");
    var elModalConfirm = $("#modal-confirm");
    var elHwDetail = $("#hw-detail");
    var elVariantOptions = $("#variant-options");

    /* ── API helpers ──────────────────────────────────────────────────── */
    function apiGet(path) {
        return fetch(path).then(function (r) {
            if (!r.ok) throw new Error(r.statusText);
            return r.json();
        });
    }

    function apiPost(path, body) {
        return fetch(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: body ? JSON.stringify(body) : undefined
        }).then(function (r) {
            if (!r.ok) throw new Error(r.statusText);
            return r.json();
        });
    }

    /* ── Stream job SSE ──────────────────────────────────────────────── */
    function streamJob(jobId, logEl) {
        var es = new EventSource("/api/jobs/" + jobId + "/events");

        es.addEventListener("log", function (e) {
            var data = JSON.parse(e.data);
            logEl.textContent += data.line + "\n";
            logEl.scrollTop = logEl.scrollHeight;
        });

        es.addEventListener("heartbeat", function () {
            // keep-alive, no action needed
        });

        es.addEventListener("done", function (e) {
            var data = e.data ? JSON.parse(e.data) : {};
            es.close();
            if (data.returncode === 0) {
                loadApps(); // refresh dashboard
            } else {
                logEl.textContent += "\n[FAILED: " + (data.error_detail || "unknown error") + "]\n";
                logEl.scrollTop = logEl.scrollHeight;
                // Mark job card as error
                var card = logEl.closest(".job-card");
                if (card) {
                    var statusEl = card.querySelector(".job-status");
                    if (statusEl) { statusEl.textContent = "FAILED"; statusEl.style.color = "var(--error)"; }
                }
            }
        });

        es.onerror = function () {
            es.close();
            logEl.textContent += "\n[Connection lost]\n";
        };
    }

    /* ── Job UI ──────────────────────────────────────────────────────── */
    function showJob(jobId, slug, action) {
        var app = null;
        for (var i = 0; i < apps.length; i++) {
            if (apps[i].slug === slug) { app = apps[i]; break; }
        }
        var name = app ? app.display_name : slug;
        var actionLabel = action === "install" ? "Installing" : "Upgrading";

        var card = document.createElement("div");
        card.className = "job-card";
        card.innerHTML =
            '<div class="job-header">' +
                '<span class="job-title">' + actionLabel + ' ' + name + '</span>' +
                '<span class="job-status">IN PROGRESS</span>' +
            '</div>' +
            '<div class="progress-track">' +
                '<div class="progress-indeterminate"></div>' +
            '</div>' +
            '<button class="job-log-toggle" type="button">Show Log</button>' +
            '<pre class="job-log" hidden></pre>';

        var toggle = card.querySelector(".job-log-toggle");
        var logEl = card.querySelector(".job-log");
        var shown = false;

        toggle.addEventListener("click", function () {
            shown = !shown;
            logEl.hidden = !shown;
            toggle.textContent = shown ? "Hide Log" : "Show Log";
        });

        elJobSection.appendChild(card);
        streamJob(jobId, logEl);
    }

    /* ── Render app cards ────────────────────────────────────────────── */
    function renderApps() {
        elGrid.innerHTML = "";
        for (var i = 0; i < apps.length; i++) {
            elGrid.appendChild(renderCard(apps[i]));
        }
    }

    function renderCard(app) {
        var card = document.createElement("div");
        card.className = "app-card";

        // Status chip
        var chip = document.createElement("span");
        chip.className = "status-chip";
        if (app.status === "not_installed" || app.status === "uv_missing") {
            chip.className += " status-not-installed";
            chip.textContent = "NOT INSTALLED";
        } else if (app.status === "installed") {
            chip.className += " status-installed";
            chip.textContent = "INSTALLED v" + app.version;
        } else if (app.status === "update_available") {
            chip.className += " status-update";
            chip.textContent = "UPDATE AVAILABLE (v" + app.version + ")";
        }

        var name = document.createElement("h2");
        name.className = "app-card-name";
        name.textContent = app.display_name;

        var desc = document.createElement("p");
        desc.className = "app-card-desc";
        desc.textContent = app.description;

        card.appendChild(name);
        card.appendChild(desc);
        card.appendChild(chip);

        // Button
        if (uvFound) {
            if (app.status === "not_installed") {
                var btn = document.createElement("button");
                btn.className = "btn btn-primary btn-full";
                btn.textContent = "Install";
                btn.addEventListener("click", function () {
                    if (app.has_asr_variants) {
                        openTranscribeModal(app.slug);
                    } else {
                        installApp(app.slug, null);
                    }
                });
                card.appendChild(btn);
            } else if (app.status === "update_available") {
                var btnU = document.createElement("button");
                btnU.className = "btn btn-primary btn-full";
                btnU.textContent = "Update";
                btnU.addEventListener("click", function () {
                    apiPost("/api/apps/" + app.slug + "/upgrade").then(function (resp) {
                        showJob(resp.job_id, app.slug, "upgrade");
                    }).catch(function (e) {
                        console.error(e);
                    });
                });
                card.appendChild(btnU);

                var btnL = document.createElement("button");
                btnL.className = "btn btn-launch btn-full";
                btnL.textContent = "Launch";
                btnL.style.marginTop = "0.5rem";
                btnL.addEventListener("click", function () {
                    launchApp(app.slug);
                });
                card.appendChild(btnL);
            } else if (app.status === "installed") {
                var btnL2 = document.createElement("button");
                btnL2.className = "btn btn-launch btn-full";
                btnL2.textContent = "Launch";
                btnL2.addEventListener("click", function () {
                    launchApp(app.slug);
                });
                card.appendChild(btnL2);
            }
        } else if (app.status === "uv_missing") {
            var btnErr = document.createElement("span");
            btnErr.className = "status-chip status-error";
            btnErr.textContent = "uv not installed";
            btnErr.style.display = "block";
            btnErr.style.textAlign = "center";
            card.appendChild(btnErr);
        }

        return card;
    }

    /* ── App actions ────────────────────────────────────────────────── */
    function installApp(slug, variant) {
        var body = {};
        if (variant) body.variant = variant;

        apiPost("/api/apps/" + slug + "/install", body).then(function (resp) {
            showJob(resp.job_id, slug, "install");
        }).catch(function (e) {
            console.error(e);
        });
    }

    function launchApp(slug) {
        apiPost("/api/apps/" + slug + "/launch").then(function (resp) {
            if (resp.url) {
                window.open(resp.url, "_blank");
            }
        }).catch(function (e) {
            console.error(e);
        });
    }

    /* ── Load data ──────────────────────────────────────────────────── */
    function loadApps() {
        apiGet("/api/apps").then(function (data) {
            uvFound = data.uv_found;
            apps = data.apps;
            renderApps();
            elHubUv.textContent = uvFound ? "found" : "not found";
        }).catch(function (e) {
            console.error("Failed to load apps:", e);
            elGrid.innerHTML = '<p class="footer-text" style="text-align:center;padding:var(--space-9) 0;">Could not connect to the Hub server.</p>';
        });
    }

    function loadHardware() {
        apiGet("/api/hardware").then(function (data) {
            hardware = data;
            elHwDetail.textContent = data.detail + " (" + data.gpu + ")";
        }).catch(function () {
            elHwDetail.textContent = "Unknown";
        });
    }

    function loadVersion() {
        apiGet("/api/health").then(function (data) {
            elHubVersion.textContent = data.version || "—";
            elHubUv.textContent = data.uv ? "found" : "not found";
        }).catch(function () {});
    }

    /* ── Transcribe modal ───────────────────────────────────────────── */
    function openTranscribeModal(slug) {
        installSlug = slug;
        elModalTitle.textContent = "Install Artifice Transcribe";

        // Find the transcribe app
        var app = null;
        for (var i = 0; i < apps.length; i++) {
            if (apps[i].slug === slug) { app = apps[i]; break; }
        }
        // Pre-select the best variant based on hardware
        var radios = elVariantOptions.querySelectorAll('input[type="radio"]');
        var best = hardware && hardware.gpu === "cuda" ? "cuda" : "cpu";
        for (var j = 0; j < radios.length; j++) {
            radios[j].checked = radios[j].value === best;
        }
        updateModalConfirm();
        elModal.showModal();
    }

    function updateModalConfirm() {
        var checked = elVariantOptions.querySelector('input[type="radio"]:checked');
        elModalConfirm.disabled = !checked;
    }

    function closeModal() {
        elModal.close();
        installSlug = null;
    }

    elModalClose.addEventListener("click", closeModal);
    elModal.addEventListener("click", function (e) {
        if (e.target === elModal) closeModal();
    });

    elVariantOptions.addEventListener("change", updateModalConfirm);

    elModalConfirm.addEventListener("click", function () {
        var checked = elVariantOptions.querySelector('input[type="radio"]:checked');
        var variant = checked ? checked.value : null;
        if (installSlug) {
            installApp(installSlug, variant);
        }
        closeModal();
    });

    elModalSkip.addEventListener("click", function () {
        if (installSlug) {
            installApp(installSlug, null); // base install, no ASR packs
        }
        closeModal();
    });

    /* ── Bootstrap ──────────────────────────────────────────────────── */
    loadVersion();
    loadHardware();
    loadApps();

})();
