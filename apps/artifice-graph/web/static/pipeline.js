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
    inputDir: $("inputDir"),
    outputDir: $("outputDir"),
    vaultDir: $("vaultDir"),
    llmUrl: $("llmUrl"),
    llmApiKey: $("llmApiKey"),
    llmModel: $("llmModel"),
    chunkSize: $("chunkSize"),
    chunkOverlap: $("chunkOverlap"),
    batchSize: $("batchSize"),
    graphFormats: $("graphFormats"),
    useSemantic: $("useSemantic"),
    incremental: $("incremental"),
    visionMode: $("visionMode"),
    btnTestConnection: $("btnTestConnection"),
    btnFetchModels:    $("btnFetchModels")
  };

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
        showNotification("Models loaded successfully!", "success");
      } else {
        updateConnectionStatus("Error fetching models: " + (response.error || "Unknown error"));
        modelState.connectionStatus = "error";
        showNotification("Error loading models. Please check your connection.", "error");
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
      showNotification("Error loading models. Please try again.", "error");
      
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

  // Notification helper
  function showNotification(message, type) {
    type = type || "info";
    var notification = document.createElement("div");
    notification.className = "notification notification-" + type;
    notification.textContent = message;
    document.body.appendChild(notification);

    // Remove after 3 seconds
    setTimeout(function() {
      notification.style.opacity = "0";
      setTimeout(function() {
        if (notification.parentNode) {
          notification.parentNode.removeChild(notification);
        }
      }, 300);
    }, 3000);
  }

  function collectConfig(extra) {
    var o = {
      input_dir:      cfg.inputDir.value,
      output_dir:     cfg.outputDir.value,
      vault_dir:      cfg.vaultDir.value,
      llm_base_url:   cfg.llmUrl.value,
      llm_api_key:    cfg.llmApiKey.value,
      llm_model:       cfg.llmModel.value,
      vision_mode:    !!cfg.visionMode.checked,
      chunk_size:     parseInt(cfg.chunkSize.value, 10) || 2000,
      chunk_overlap:  parseInt(cfg.chunkOverlap.value, 10) || 200,
      batch_size:     parseInt(cfg.batchSize.value, 10) || 5,
      graph_formats:  cfg.graphFormats.value.split(",").map(function (s) { return s.trim(); }).filter(Boolean),
      use_semantic:   !!cfg.useSemantic.checked,
      incremental:    !!cfg.incremental.checked
    };
    if (extra) { Object.keys(extra).forEach(function (k) { o[k] = extra[k]; }); }
    return o;
  }

  function setStatus(state, text) {
    els.statusStrip.setAttribute("data-state", state);
    if (typeof text === "string") { els.statusStrip.querySelector("[data-status-text]").textContent = text; }
  }

  function refreshState() {
    window.fetch("/api/state").then(function(r) { return r.json(); }).then(function(s) {
      if (!s) return;
      setStat("documents", s.documents);
      setStat("chunks", s.chunks);
      setStat("entities", s.entities);
      setStat("relationships", s.relationships);
      setStat("raw", s.entities_raw);
      renderBreakdowns(s);
    }).catch(function() {});
  }

  function setStat(name, n) {
    var el = els.statRow.querySelector("[data-stat=\"" + name + "\"]");
    if (el) el.textContent = (n == null ? "—" : n);
  }

  // ── Pipeline execution ─────────────────────────────────────────────

  function _populateEls() {
    els.btnRunAll    = $("btnRunAll");
    els.btnDemo      = $("btnDemo");
    els.btnClearLog  = $("btnClearLog");
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
            showResult(resultContainer, false, "Network error: " + err.message, ["Check your internet connection and try again."].concat(data.suggestions || []));
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

    // Initial state
    updateSectionStates();
    refreshState();
    setInterval(function () { if (!running) refreshState(); }, 5000);

    // Existing wiring functions
    wireStageButtons();
    wireFilePickers();

    if (els.btnRunAll) els.btnRunAll.addEventListener("click", function () {
      document.querySelectorAll(".stage-card").forEach(function(){});
      Object.keys(stageCards).forEach(function (k) { setStageState(k, "idle"); });
      runStage("run-all");
    });

    if (els.btnDemo) els.btnDemo.addEventListener("click", function () {
      Object.keys(stageCards).forEach(function (k) { setStageState(k, "idle"); });
      runStage("demo");
    });

    if (els.btnClearLog) els.btnClearLog.addEventListener("click", clearLog);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }

  window.Pipeline = { runStage: runStage, refreshState: refreshState };
})();