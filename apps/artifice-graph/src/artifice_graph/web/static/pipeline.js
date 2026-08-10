// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/* Enhanced UI Interaction Script for Better UX */

(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };

  // ── Element cache & shared state ──────────────────────────────────
  var els = {};
  var running = false;
  var currentEventSource = null;
  var stageCards = { ingest: "idle", extract: "idle", resolve: "idle", vault: "idle", graph: "idle" };

  // Enhanced Configuration State Management
  var cfg = {
    llmUrl: $("llmUrl"),
    llmApiKey: $("llmApiKey"),
    llmModel: $("llmModel"),
    embeddingUrl: $("embeddingUrl"),
    embeddingModel: $("embeddingModel"),
    chunkSize: $("chunkSize"),
    chunkOverlap: $("chunkOverlap"),
    batchSize: $("batchSize"),
    graphFormats: $("graphFormats"),
    useSemantic: $("useSemantic"),
    incremental: $("incremental"),
    visionMode: $("visionMode"),
    btnTestConnection: $("btnTestConnection"),
    btnFetchModels:    $("btnFetchModels"),
    btnSaveConfig:     $("btnSaveConfig")
  };

  // Warn on startup if any cached element resolved to null — a missing
  // id in the template must produce a visible complaint, not a dead page.
  Object.keys(cfg).forEach(function (key) {
    if (cfg[key] === null) {
      console.warn("pipeline.js: cfg." + key + " resolved to null — element #" + key + " not found in the DOM");
    }
  });

  var modelState = {
    availableModels: [],
    visionModels: [],
    isLoading: false,
    connectionStatus: "disconnected"
  };

  var currentStep = 0;

  // Enhanced Helper Functions
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function showResult(container, success, message, suggestions = []) {
    // Hide all result states
    container.querySelectorAll(".result-success, .result-error, .result-loading").forEach(function(el) {
      el.style.display = "none";
    });

    if (success) {
      var successEl = container.querySelector(".result-success");
      var messageEl = $("connectionSuccessMessage");
      if (successEl && messageEl) {
        messageEl.textContent = message;
        successEl.style.display = "flex";
      }
    } else {
      var errorEl = container.querySelector(".result-error");
      var messageEl = $("connectionErrorMessage");
      var suggestionsEl = $("connectionErrorSuggestions");
      if (errorEl && messageEl && suggestionsEl) {
        messageEl.textContent = message;
        // Clear existing suggestions
        suggestionsEl.innerHTML = "";
        // Add new suggestions
        suggestions.forEach(function(suggestion) {
          var li = document.createElement("li");
          li.textContent = suggestion;
          suggestionsEl.appendChild(li);
        });
        errorEl.style.display = "flex";
      }
    }
  }

  function updateSectionStates() {
    var sections = document.querySelectorAll(".config-section");
    sections.forEach(function(section, index) {
      if (index <= currentStep) {
        section.classList.add("completed");
        section.classList.remove("pending");
      } else {
        section.classList.remove("completed");
        section.classList.add("pending");
      }
    });
  }

  function handlePresetButtonClick(url, modelName) {
    // Update configuration fields
    if (cfg.llmUrl) cfg.llmUrl.value = url;
    if (cfg.llmModel) cfg.llmModel.value = modelName || "";
    
    // Show helpful tooltip
    Callopp.setStatus(cfg.btnTestConnection, "running", "Preset applied! Click 'Test Connection'")
    
    // Auto-scroll to model settings
    var modelSection = document.querySelector(".config-section:nth-child(4)");
    if (modelSection) {
      modelSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    currentStep = 0;
    updateSectionStates();
  }

  function handleFetchModelsClick() {
    if (modelState.isLoading) return;
    
    modelState.isLoading = true;
    var btn = cfg.btnFetchModels;
    
    if (btn) {
      btn.disabled = true;
        btn.textContent = "Loading...";
    }

    Callopp.fetchJson("/api/models").then(function(response) {
      if (response.models) {
        modelState.availableModels = response.models || [];
        modelState.visionModels = response.vision_models || [];
        modelState.connectionStatus = response.error ? "error" : "connected";

        updateModelDropdown();
        updateConnectionStatus(response.error || "Connected");
        
        currentStep = 2;
        updateSectionStates();
        
        // Show success message
        window.ArtificeToast.success("Models loaded successfully!");
      } else {
        updateConnectionStatus("Error fetching models: " + (response.error || "Unknown error"));
        modelState.connectionStatus = "error";
        window.ArtificeToast.error("Error loading models. Please check your connection.");
      }

      modelState.isLoading = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Fetch Available Models";
      }
    }).catch(function(err) {
      console.error("Error fetching models:", err);
      updateConnectionStatus("Error fetching models: " + err.message);
      modelState.connectionStatus = "error";
      window.ArtificeToast.error("Error loading models. Please try again.");
      
      modelState.isLoading = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Fetch Available Models";
      }
    });
  }

  function updateModelDropdown() {
    var select = $("llmModel");
    if (!select) return;

    var currentValue = select.value;
    var optionsHtml = '<option value="">Select a model...</option>';

    var allModels = modelState.availableModels;

    allModels.forEach(function(model) {
      var displayName = model.name || model.id;
      var optionHtml = 
        '<option value="' + esc(model.id) + '">'
        + esc(displayName) + ' [' + esc(model.source) + ']';
      
      if (model.supports_vision) {
        optionHtml += ' (Vision)';
      }
      
      optionHtml += '</option>';
      optionsHtml += optionHtml;
    });

    select.innerHTML = optionsHtml;

    if (currentValue && modelState.availableModels.some(function(m) { return m.id === currentValue; })) {
      select.value = currentValue;
    }
  }

  function updateConnectionStatus(statusText) {
    var statusEl = $("logConnState");
    var statusStrip = $("statusStrip");

    if (!statusEl || !statusStrip) return;

    var isConnected = modelState.connectionStatus === "connected";
    var state = isConnected ? "running" : "idle";

    statusStrip.setAttribute("data-state", state);
    statusEl.textContent = statusText || (isConnected ? "Connected" : "Disconnected");

    var dot = statusStrip.querySelector(".dot");
    if (dot) {
      dot.className = "dot" + (isConnected ? " dot-connected" : "");
    }
  }

  function collectConfig(extra) {
    var o = {
      llm_base_url:       cfg.llmUrl ? cfg.llmUrl.value : "",
      llm_api_key:        cfg.llmApiKey ? cfg.llmApiKey.value : "",
      llm_model:          cfg.llmModel ? cfg.llmModel.value : "",
      embedding_base_url: cfg.embeddingUrl ? cfg.embeddingUrl.value : "",
      embedding_model:    cfg.embeddingModel ? cfg.embeddingModel.value : "",
      vision_mode:        cfg.visionMode ? !!cfg.visionMode.checked : false,
      chunk_size:         cfg.chunkSize ? (parseInt(cfg.chunkSize.value, 10) || 2000) : 2000,
      chunk_overlap:      cfg.chunkOverlap ? (parseInt(cfg.chunkOverlap.value, 10) || 200) : 200,
      batch_size:         cfg.batchSize ? (parseInt(cfg.batchSize.value, 10) || 5) : 5,
      graph_formats:      cfg.graphFormats ? cfg.graphFormats.value.split(",").map(function (s) { return s.trim(); }).filter(Boolean) : [],
      use_semantic:       cfg.useSemantic ? !!cfg.useSemantic.checked : false,
      incremental:        cfg.incremental ? !!cfg.incremental.checked : false
    };
    if (extra) { Object.keys(extra).forEach(function (k) { o[k] = extra[k]; }); }
    return o;
  }

  function setStatus(state, text) {
    els.statusStrip.setAttribute("data-state", state);
    if (typeof text === "string") { els.statusStrip.querySelector("[data-status-text]").textContent = text; }
  }

  // Tracks whether we have failed since the last successful state refresh.
  // Used to toast only on the first failure after a success — a polling
  // function that toasts on every failed poll would spam the user during
  // any extended outage.
  var _stateFailedSinceSuccess = false;

  function refreshState() {
    window.ArtificeBind.apiFetch("/api/state").then(function(s) {
      _stateFailedSinceSuccess = false;
      if (!s) return;
      setStat("documents", s.documents);
      setStat("chunks", s.chunks);
      setStat("entities", s.entities);
      setStat("relationships", s.relationships);
      setStat("raw", s.entities_raw);
      renderBreakdowns(s);
    }).catch(function(err) {
      if (!_stateFailedSinceSuccess) {
        _stateFailedSinceSuccess = true;
        if (window.ArtificeToast) {
          window.ArtificeToast.error("Could not refresh state: " + err.message);
        }
      }
    });
  }

  // Singular / plural label pairs for each stat tile, keyed by the same
  // data-stat name pipeline.js already looks up. Index 0 is singular
  // (count === 1), index 1 is plural (every other count, including the
  // "—" placeholder before any run has produced a count).
  var STAT_LABELS = {
    documents: ["Document", "Documents"],
    chunks: ["Chunk", "Chunks"],
    entities: ["Entity", "Entities"],
    relationships: ["Relationship", "Relationships"],
    raw: ["Raw Entity", "Raw Entities"]
  };

  function setStat(name, n) {
    var el = els.statRow.querySelector("[data-stat=\"" + name + "\"]");
    if (!el) return;
    el.textContent = (n == null ? "—" : n);

    var labels = STAT_LABELS[name];
    var labelEl = el.parentElement ? el.parentElement.querySelector(".stat-l") : null;
    if (labels && labelEl) {
      labelEl.textContent = (n === 1) ? labels[0] : labels[1];
    }
  }

  // ── Pipeline execution ─────────────────────────────────────────────

  function _populateEls() {
    els.btnRunAll    = $("btnRunAll");
    els.btnDemo      = $("btnDemo");
    els.btnClearLog  = $("btnClearLog");
    els.btnSaveConfig = $("btnSaveConfig");
    els.logPanel     = $("logPanel");
    els.statusStrip  = $("statusStrip");
    els.lastRunLabel = $("lastRunLabel");
    els.logConnState = $("logConnState");
    els.autoscroll   = $("autoscroll");
    els.typeBreakdown = $("typeBreakdown");
    els.relBreakdown = $("relBreakdown");
    els.statRow      = $("statRow");
    els.stageAnnouncer = $("stageAnnouncer");
  }

  // ── Stage card helpers ────────────────────────────────────────────

  var STAGE_ORDER = ["ingest", "extract", "resolve", "vault", "graph"];

  function setStageState(key, state) {
    var card = document.querySelector(".stage-card[data-stage=\"" + key + "\"]");
    var stageName = key;
    if (card) {
      card.setAttribute("data-state", state);
      var badge = card.querySelector("[data-stage-badge]");
      if (badge) badge.textContent = state;
      var nameEl = card.querySelector(".stage-name");
      if (nameEl) stageName = nameEl.textContent;
    }
    stageCards[key] = state;
    _announceStageState(stageName, state);
  }

  // Screen-reader announcement for stage transitions (WCAG 4.1.3). One
  // shared polite live region for all five stages, not five — five
  // simultaneous badges updating (e.g. on Run All) would fire five
  // near-simultaneous announcements and bury the one the user actually
  // needs. "idle" resets (the silent reset pipeline.js does immediately
  // before starting a new run) are deliberately not announced: they carry
  // no new information for the user and, on page load, the region starts
  // empty and untouched so nothing is read out unprompted.
  function _announceStageState(stageName, state) {
    if (!els.stageAnnouncer) return;
    if (state === "running") {
      els.stageAnnouncer.textContent = stageName + ": running";
    } else if (state === "done") {
      els.stageAnnouncer.textContent = stageName + ": complete";
    } else if (state === "error") {
      els.stageAnnouncer.textContent = stageName + ": failed";
    }
  }

  function _allStagesDone() {
    for (var i = 0; i < STAGE_ORDER.length; i++) {
      if (stageCards[STAGE_ORDER[i]] !== "done") return false;
    }
    return true;
  }

  // ── File pickers ──────────────────────────────────────────────────

  // ── File upload dropzone ──────────────────────────────────────────
  // Mirrors the pattern from artifice-transcribe: real <input type="file">
  // plus drag-and-drop, both uploading file *contents* to the server rather
  // than sending a typed filesystem path.

  function wireUploadDropzone() {
    var dropzone  = $("uploadDropzone");
    var fileInput = $("uploadFileInput");
    var fileList  = $("uploadFileList");
    var summary   = $("uploadSummary");
    var browseBtn = $("btnBrowseFiles");

    if (!dropzone || !fileInput) return;

    function escHtml(s) {
      return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function setStatus(li, state, text) {
      var span = li.querySelector(".upload-file-status");
      if (!span) return;
      span.className = "upload-file-status " + state;
      span.textContent = text;
    }

    function uploadFiles(files) {
      if (!files || files.length === 0) return;

      // Clear previous list
      while (fileList.firstChild) fileList.removeChild(fileList.firstChild);
      summary.textContent = "";

      var total   = files.length;
      var done    = 0;
      var ok      = 0;
      var failed  = 0;

      function updateSummary() {
        if (done < total) {
          summary.textContent = "Uploading " + done + " / " + total + "…";
        } else {
          summary.textContent = ok + " uploaded" + (failed ? ", " + failed + " failed" : "") + ".";
        }
      }

      var formData = new FormData();
      var listItems = [];

      for (var i = 0; i < files.length; i++) {
        var f = files[i];
        formData.append("files", f);

        var li = document.createElement("li");
        li.innerHTML =
          '<span class="upload-file-name">' + escHtml(f.name) + '</span>' +
          '<span class="upload-file-status wait">Pending…</span>';
        fileList.appendChild(li);
        listItems.push(li);
      }

      updateSummary();

      // Send all files in one multipart request
      window.fetch("/api/upload-files", {
        method: "POST",
        body: formData
      })
      .then(function (r) {
        if (!r.ok) {
          return r.json().then(function (err) {
            throw new Error(err.detail || ("HTTP " + r.status));
          });
        }
        return r.json();
      })
      .then(function (data) {
        var results = data.uploaded || [];
        results.forEach(function (res, idx) {
          var li = listItems[idx];
          if (!li) return;
          if (res.status === "ok") {
            setStatus(li, "ok", "✓ Saved");
            ok++;
          } else {
            setStatus(li, "err", "✗ " + (res.reason || "Error"));
            failed++;
          }
          done++;
        });
        // Mark any remaining (shouldn't happen) as failed
        for (var j = results.length; j < listItems.length; j++) {
          setStatus(listItems[j], "err", "✗ No response");
          failed++;
          done++;
        }
        updateSummary();
        if (ok > 0) { refreshState(); }
      })
      .catch(function (err) {
        listItems.forEach(function (li) {
          setStatus(li, "err", "✗ " + (err && err.message ? err.message : "Upload failed"));
        });
        done = total;
        failed = total;
        updateSummary();
      });
    }

    // Click on dropzone or Browse button → trigger file picker
    dropzone.addEventListener("click", function () { fileInput.click(); });
    if (browseBtn) {
      browseBtn.addEventListener("click", function (e) {
        e.stopPropagation(); // prevent the dropzone click handler from double-firing
        fileInput.click();
      });
    }

    // Keyboard activation for the dropzone (role="button")
    dropzone.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        fileInput.click();
      }
    });

    // File picker change
    fileInput.addEventListener("change", function () {
      if (fileInput.files && fileInput.files.length > 0) {
        uploadFiles(fileInput.files);
        fileInput.value = ""; // reset so the same file can be re-picked
      }
    });

    // Drag-and-drop
    dropzone.addEventListener("dragover", function (e) {
      e.preventDefault();
      dropzone.classList.add("drag-over");
    });
    dropzone.addEventListener("dragleave", function (e) {
      // Only remove if leaving the dropzone itself, not a child element
      if (!dropzone.contains(e.relatedTarget)) {
        dropzone.classList.remove("drag-over");
      }
    });
    dropzone.addEventListener("drop", function (e) {
      e.preventDefault();
      dropzone.classList.remove("drag-over");
      var files = e.dataTransfer ? e.dataTransfer.files : null;
      if (files && files.length > 0) {
        uploadFiles(files);
      }
    });
  }

  function wireFilePickers() {
    var rows = document.querySelectorAll(".dir-row");
    for (var i = 0; i < rows.length; i++) {
      (function (row) {
        var input = row.querySelector(".dir-file");
        var btn = row.querySelector("button");
        if (input && btn) {
          btn.addEventListener("click", function () { input.click(); });
        }
      })(rows[i]);
    }
    var dirInputs = document.querySelectorAll(".dir-file");
    for (var j = 0; j < dirInputs.length; j++) {
      dirInputs[j].addEventListener("change", function () {
        var row = this.closest(".dir-row");
        if (row) {
          var label = row.querySelector(".dir-label");
          if (label) label.textContent = this.value || "(none)";
        }
      });
    }
  }

  // ── Log helpers ───────────────────────────────────────────────────

  function _appendLogLine(text, level) {
    level = level || "info";
    var div = document.createElement("div");
    div.className = "log-line log-" + level;
    div.textContent = text;
    els.logPanel.appendChild(div);
    if (els.autoscroll && els.autoscroll.checked) {
      els.logPanel.scrollTop = els.logPanel.scrollHeight;
    }
  }

  function _appendLogSep() {
    var div = document.createElement("div");
    div.className = "log-sep";
    els.logPanel.appendChild(div);
  }

  function clearLog() {
    while (els.logPanel.firstChild) {
      els.logPanel.removeChild(els.logPanel.firstChild);
    }
  }

  // ── SSE stream handling ───────────────────────────────────────────

  function _handleSSEEvent(evt, runMode) {
    try {
      var data = JSON.parse(evt.data);
    } catch (e) { return; }

    if (data.sep) { _appendLogSep(); return; }

    if (data.gotoState !== undefined) {
      var text = data.text || "";
      // Advance stage state
      if (runMode === "single") {
        // Find the single running stage (there should be exactly one)
        for (var i = 0; i < STAGE_ORDER.length; i++) {
          if (stageCards[STAGE_ORDER[i]] === "running") {
            setStageState(STAGE_ORDER[i], "done");
            break;
          }
        }
      } else if (runMode === "run-all" || runMode === "demo") {
        // Advance through stages: mark first "running" as done,
        // then mark the next stage as running if it exists
        var advanced = false;
        for (var j = 0; j < STAGE_ORDER.length; j++) {
          if (stageCards[STAGE_ORDER[j]] === "running") {
            setStageState(STAGE_ORDER[j], "done");
            // If there's a next stage, mark it running
            if (j + 1 < STAGE_ORDER.length && !_allStagesDone()) {
              setStageState(STAGE_ORDER[j + 1], "running");
            }
            advanced = true;
            break;
          }
        }
        if (!advanced && runMode === "run-all") {
          // No running stage found — first gotoState after stream start
          // (e.g., stream reconnected). Just mark all done.
          for (var k = 0; k < STAGE_ORDER.length; k++) {
            setStageState(STAGE_ORDER[k], "done");
          }
        }
      }
      if (data.gotoState === "done") {
        _appendLogLine(text || "Stage complete", "success");
      } else {
        _appendLogLine(text || "Complete", "success");
      }
      // If all stages are done, mark pipeline idle
      if (_allStagesDone()) { _finishRun(); }
      return;
    }

    if (data.text !== undefined) {
      _appendLogLine(data.text, data.level || "info");
    }
  }

  function _finishRun() {
    running = false;
    if (currentEventSource) {
      currentEventSource.close();
      currentEventSource = null;
    }
    setStatus("idle", "Idle");
    updateConnectionStatus("connected");
    refreshState();
  }

  // ── Stage wiring ──────────────────────────────────────────────────

  function wireStageButtons() {
    var buttons = document.querySelectorAll("[data-run-stage]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function () {
        var stage = this.getAttribute("data-run-stage");
        if (stage) runStage(stage);
      });
    }
  }

  // ── runStage — the main pipeline executor ─────────────────────────

  function runStage(stage) {
    if (running) return;
    try {

    var endpoint;
    if (stage === "run-all") {
      endpoint = "/api/run-all";
    } else if (stage === "demo") {
      endpoint = "/api/demo";
    } else {
      var stageToEndpoint = {
        ingest: "/api/ingest",
        extract: "/api/extract",
        resolve: "/api/resolve",
        vault: "/api/build-vault",
        graph: "/api/build-graph"
      };
      endpoint = stageToEndpoint[stage];
      if (!endpoint) return;
    }

    // Close any stale SSE connection
    if (currentEventSource) {
      currentEventSource.close();
      currentEventSource = null;
    }

    running = true;
    clearLog();

    var runMode = (stage === "run-all" || stage === "demo") ? stage === "demo" ? "demo" : "run-all" : "single";

    // Set stage state(s)
    if (runMode === "run-all") {
      for (var i = 0; i < STAGE_ORDER.length; i++) {
        setStageState(STAGE_ORDER[i], i === 0 ? "running" : "idle");
      }
    } else if (runMode === "demo") {
      for (var j = 0; j < STAGE_ORDER.length; j++) {
        setStageState(STAGE_ORDER[j], "running");
      }
    } else {
      setStageState(stage, "running");
    }

    setStatus("running", stage === "demo" ? "Running Demo..." : "Running " + stage + "...");

    var config = collectConfig();

    window.fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (!data.run_key) {
        _appendLogLine("Error: No run key returned from server", "error");
        running = false;
        setStatus("idle", "Error");
        return;
      }

      var runKey = data.run_key;
      if (els.lastRunLabel) els.lastRunLabel.textContent = "Run: " + stage + " (" + runKey + ")";
      updateConnectionStatus("connected (streaming)");

      var es = new EventSource("/api/stream?run=" + encodeURIComponent(runKey));
      currentEventSource = es;

      es.addEventListener("message", function (evt) {
        _handleSSEEvent(evt, runMode);
      });

      es.addEventListener("error", function () {
        if (es.readyState === EventSource.CLOSED && running) {
          // Stream closed but we think we're still running — finish up
          _finishRun();
        }
      });
    }).catch(function (err) {
      _appendLogLine("Error: " + (err && err.message ? err.message : err), "error");
      running = false;
      setStatus("idle", "Error");
      updateConnectionStatus("disconnected");
    });
    } catch (e) {
      running = false;
      if (currentEventSource) {
        currentEventSource.close();
        currentEventSource = null;
      }
      setStatus("idle", "Error: " + (e && e.message ? e.message : e));
      // Set any running stages to error so the UI reflects the failure
      for (var i = 0; i < STAGE_ORDER.length; i++) {
        if (stageCards[STAGE_ORDER[i]] === "running") {
          setStageState(STAGE_ORDER[i], "error");
        }
      }
      // Also mark the requested stage as error if it's a single-stage run
      if (stage && stage !== "run-all" && stage !== "demo") {
        if (stageCards[stage] !== "error") {
          setStageState(stage, "error");
        }
      }
      console.error("runStage error:", e);
    }
  }

  // ── Breakdown rendering ───────────────────────────────────────────

  function renderBreakdowns(state) {
    if (!els.typeBreakdown || !els.relBreakdown) return;

    // Entity type breakdown
    if (state && state.type_counts && state.type_counts.length) {
      var html = "";
      for (var i = 0; i < state.type_counts.length; i++) {
        var tc = state.type_counts[i];
        html += "<div class=\"breakdown-row\"><span class=\"breakdown-label\">" + esc(tc.type) + "</span><span class=\"breakdown-count\">" + tc.count + "</span></div>";
      }
      els.typeBreakdown.innerHTML = html;
    } else {
      els.typeBreakdown.innerHTML = '<p class="stat-empty">No entities yet — run Extract or Demo.</p>';
    }

    // Relationship type breakdown
    if (state && state.rel_counts && state.rel_counts.length) {
      var relHtml = "";
      for (var j = 0; j < state.rel_counts.length; j++) {
        var rc = state.rel_counts[j];
        relHtml += "<div class=\"breakdown-row\"><span class=\"breakdown-label\">" + esc(rc.type) + "</span><span class=\"breakdown-count\">" + rc.count + "</span></div>";
      }
      els.relBreakdown.innerHTML = relHtml;
    } else {
      els.relBreakdown.innerHTML = '<p class="stat-empty">No relationships yet — run Extract or Demo.</p>';
    }
  }

  // Wiring
  function init() {
    _populateEls();

    // Wiring for preset buttons
    var presetButtons = document.querySelectorAll(".preset-card");
    Array.prototype.forEach.call(presetButtons, function(btn) {
      btn.addEventListener("click", function(e) {
        var url = this.getAttribute("data-url");
        var model = this.getAttribute("data-name");
        handlePresetButtonClick(url, model);
      });
    });

    // Wiring for connection test button
    if (cfg.btnTestConnection) {
      cfg.btnTestConnection.addEventListener("click", function() {
        var btn = this;
        btn.disabled = true;
        btn.textContent = "Testing...";
        
        var runKey = "test-" + Date.now();
        var endpoint = "/api/test-connection";
        
        window.fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(collectConfig())
        }).then(function(r) {
          return r.json();
        }).then(function(data) {
          var resultContainer = $("connectionResult");
          if (resultContainer) {
            showResult(resultContainer, data.status === "connected", data.error || data.message, data.suggestions || []);
            modelState.connectionStatus = data.status;
          }
        }).catch(function(err) {
          var resultContainer = $("connectionResult");
          if (resultContainer) {
            showResult(resultContainer, false, "Network error: " + err.message, ["Check your internet connection and try again."]);
          }
        }).finally(function() {
          btn.disabled = false;
          btn.textContent = "Test Connection";
        });
      });
    }

    // Wiring for fetch models button
    if (cfg.btnFetchModels) {
      cfg.btnFetchModels.addEventListener("click", handleFetchModelsClick);
    }

    // Wiring for save configuration button
    if (cfg.btnSaveConfig) {
      cfg.btnSaveConfig.addEventListener("click", function () {
        var btn = this;
        btn.disabled = true;
        var prevText = btn.textContent;
        btn.textContent = "Saving...";

        window.fetch("/api/save-config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(collectConfig())
        }).then(function (r) {
          return r.json();
        }).then(function (data) {
          if (data.status === "ok") {
            window.ArtificeToast.success(data.message);
          } else {
            window.ArtificeToast.error(data.message || "Error saving configuration");
          }
        }).catch(function (err) {
          window.ArtificeToast.error("Error saving configuration: " + (err && err.message ? err.message : err));
        }).finally(function () {
          btn.disabled = false;
          btn.textContent = prevText;
        });
      });
    }

    // Initial state
    updateSectionStates();
    refreshState();
    setInterval(function () { if (!running) refreshState(); }, 5000);

    // Existing wiring functions
    wireStageButtons();
    wireFilePickers();
    wireUploadDropzone();

    if (els.btnRunAll) els.btnRunAll.addEventListener("click", function () {
      document.querySelectorAll(".stage-card").forEach(function(){});
      Object.keys(stageCards).forEach(function (k) { setStageState(k, "idle"); });
      runStage("run-all");
    });

    if (els.btnDemo) els.btnDemo.addEventListener("click", function () {
      Object.keys(stageCards).forEach(function (k) { setStageState(k, "idle"); });
      runStage("demo");
    });

    if (els.btnSaveConfig) els.btnSaveConfig.addEventListener("click", function () {
      var config = collectConfig();

      window.fetch("/api/save-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config)
      }).then(function (r) { return r.json(); }).then(function (data) {
        if (data.status === "ok") {
          window.ArtificeToast.success("Configuration saved");
        } else {
          window.ArtificeToast.error("Save failed: " + (data.message || "Unknown error"));
        }
      }).catch(function (err) {
        window.ArtificeToast.error("Save failed: " + (err && err.message ? err.message : "Network error"));
      });
    });

    if (els.btnClearLog) els.btnClearLog.addEventListener("click", clearLog);

    // ── Handoff: show toast if an import just completed ────────────
    (function () {
      var params = new URLSearchParams(window.location.search);
      if (params.get("handoff_ok") === "1") {
        var source = params.get("handoff_source") || "another app";
        if (window.ArtificeToast) {
          window.ArtificeToast.success("Imported text from " + source + " — file added to input directory.");
        }
        // Clean URL
        if (window.history && window.history.replaceState) {
          var clean = window.location.pathname;
          window.history.replaceState(null, "", clean);
        }
      } else if (params.get("handoff_error") === "invalid") {
        if (window.ArtificeToast) {
          window.ArtificeToast.error("Handoff expired or invalid.");
        }
        if (window.history && window.history.replaceState) {
          window.history.replaceState(null, "", window.location.pathname);
        }
      }
    })();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }

  window.Pipeline = { runStage: runStage, refreshState: refreshState };
})();