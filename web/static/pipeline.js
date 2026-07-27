/* Enhanced UI Interaction Script for Better UX */

(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };

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

  // ── Existing pipeline.js code continues... (rest of the file)
  // This preserves all existing functionality while adding the new interactions

  // Wiring
  function init() {
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