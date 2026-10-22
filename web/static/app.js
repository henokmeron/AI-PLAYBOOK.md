(function () {
  "use strict";

  var views = ["chat", "documents", "agent", "repair", "ops", "status"];
  var messages = [];
  var ragTurns = [];
  var busy = false;
  var ragBusy = false;
  var lastStatus = null;
  var catalogModels = [];
  var selectedModelId = "";
  var MAX_RAG_HISTORY_MESSAGES = 12;
  var authState = null;
  var csrfToken = "";

  var navStatus = document.getElementById("nav-status");
  var chatLog = document.getElementById("chat-log");
  var chatForm = document.getElementById("chat-form");
  var chatInput = document.getElementById("chat-input");
  var chatError = document.getElementById("chat-error");
  var chatLoading = document.getElementById("chat-loading");
  var chatSend = document.getElementById("chat-send");
  var modelSelect = document.getElementById("model-select");
  var modelHint = document.getElementById("model-hint");
  var ragForm = document.getElementById("rag-form");
  var ragQuestion = document.getElementById("rag-question");
  var ragCollection = document.getElementById("rag-collection");
  var ragTopK = document.getElementById("rag-top-k");
  var ragError = document.getElementById("rag-error");
  var ragLoading = document.getElementById("rag-loading");
  var ragSend = document.getElementById("rag-send");
  var ragClear = document.getElementById("rag-clear");
  var ragLog = document.getElementById("rag-log");
  var uploadForm = document.getElementById("upload-form");
  var uploadCollection = document.getElementById("upload-collection");
  var uploadFile = document.getElementById("upload-file");
  var uploadSubmit = document.getElementById("upload-submit");
  var uploadLoading = document.getElementById("upload-loading");
  var uploadError = document.getElementById("upload-error");
  var uploadStatus = document.getElementById("upload-status");
  var documentList = document.getElementById("document-list");
  var statusPanel = document.getElementById("status-panel");
  var statusLoading = document.getElementById("status-loading");
  var statusError = document.getElementById("status-error");
  var chatGateway = document.getElementById("chat-gateway");
  var agentGateway = document.getElementById("agent-gateway");
  var statusInFlight = false;
  var statusPhase = "loading";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function showError(node, message) {
    if (!message) {
      node.hidden = true;
      node.textContent = "";
      return;
    }
    node.hidden = false;
    node.textContent = message;
  }

  function errorMessage(error) {
    if (error && error.name === "TimeoutError") return "The gateway took too long to respond.";
    if (error && error.name === "AbortError") return "The request was cancelled.";
    return error && error.message ? error.message : "The request failed.";
  }

  function setRagBusy(isBusy) {
    ragBusy = isBusy;
    // Keep the question box editable so the user can draft the next question.
    // Disable Ask only to prevent duplicate concurrent submissions that could
    // mis-order answers. Collection and top_k stay usable for the next ask.
    ragSend.disabled = isBusy;
    ragQuestion.disabled = false;
    ragCollection.disabled = false;
    ragTopK.disabled = false;
    ragClear.disabled = isBusy;
    ragLoading.hidden = !isBusy;
  }

  function request(path, options) {
    var signal = typeof AbortSignal !== "undefined" && AbortSignal.timeout
      ? AbortSignal.timeout(190000)
      : undefined;
    var method = options && options.method ? options.method : "GET";
    var headers = { "Accept": "application/json" };
    if (options && options.body) headers["Content-Type"] = "application/json";
    if (options && options.headers) {
      Object.keys(options.headers).forEach(function (name) {
        headers[name] = options.headers[name];
      });
    }
    if (csrfToken && method !== "GET" && method !== "HEAD") {
      headers["X-CSRF-Token"] = csrfToken;
    }
    return fetch(path, {
      method: method,
      headers: headers,
      body: options && options.body ? JSON.stringify(options.body) : undefined,
      credentials: "same-origin",
      signal: signal
    }).then(function (response) {
      return response.text().then(function (text) {
        var body = {};
        if (text) {
          try {
            body = JSON.parse(text);
          } catch (parseError) {
            throw new Error("The server returned an unreadable response.");
          }
        }
        if (response.status === 401 && path.indexOf("/api/auth/") !== 0) {
          showLoginGate(authState);
          throw new Error("Sign in required.");
        }
        if (!response.ok) {
          var message = body && body.error ? body.error : "Request failed (" + response.status + ").";
          if (body && typeof body.error_id === "string") message += " (error id " + body.error_id + ")";
          throw new Error(message);
        }
        return body;
      });
    });
  }

  function showLoginGate(status) {
    var gate = document.getElementById("login-gate");
    var shell = document.getElementById("app-shell");
    var setup = document.getElementById("login-setup");
    if (gate) gate.hidden = false;
    if (shell) shell.hidden = true;
    authState = status || authState;
    csrfToken = "";
    if (setup) {
      if (status && status.configured === false && status.setup) {
        setup.hidden = false;
        setup.textContent = status.setup;
      } else {
        setup.hidden = true;
        setup.textContent = "";
      }
    }
  }

  function showAppShell(status) {
    var gate = document.getElementById("login-gate");
    var shell = document.getElementById("app-shell");
    var label = document.getElementById("operator-label");
    if (gate) gate.hidden = true;
    if (shell) shell.hidden = false;
    authState = status;
    csrfToken = status && status.csrf_token ? status.csrf_token : "";
    if (label) {
      label.textContent = status && status.username
        ? (status.username + " · " + (status.role || "operator"))
        : "Signed in";
    }
  }

  function refreshAuth() {
    return request("/api/auth/status").then(function (body) {
      if (body && body.authenticated) {
        showAppShell(body);
        return body;
      }
      showLoginGate(body);
      return body;
    }).catch(function () {
      showLoginGate({ configured: false, setup: "Could not reach the console auth status endpoint." });
      return null;
    });
  }

  function showView(name) {
    if (views.indexOf(name) === -1) name = "chat";
    views.forEach(function (view) {
      var section = document.getElementById(view + "-view");
      var button = document.querySelector('[data-view="' + view + '"]');
      var active = view === name;
      if (section) section.hidden = !active;
      if (button) {
        if (active) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
      }
    });
    if (location.hash !== "#" + name) {
      history.replaceState(null, "", location.pathname + location.search + "#" + name);
    }
    document.title =
      name === "documents" ? "Document Q&A"
        : name === "agent" ? "IT Helpdesk"
        : name === "repair" ? "Windows repair"
        : name === "ops" ? "Operations Centre"
        : name === "status" ? "System Status"
        : "Chat";
    if (name === "agent") {
      loadConnectors();
      loadAgentHistory();
    }
    if (name === "repair") loadRepair();
    if (name === "ops") loadOpsCentre();
    if (name === "status") renderStatus();
  }

  function modelIsAlive(body) {
    if (!body || body.model_alive !== true || body.model_dead === true) return false;
    if (body.connection !== "ready") return false;
    var health = body.health || {};
    if (health.reason === "model_engine_dead" || health.reason === "no_models_reported" || health.reason === "model_server_absent") {
      return false;
    }
    if (health.status && health.status !== "ok") return false;
    if (typeof health.model_count === "number" && health.model_count < 1) return false;
    if (body.upstream && body.upstream !== "ok") return false;
    return true;
  }

  function statusLabel(connection, body) {
    if (connection === "ready" && modelIsAlive(body)) return "Gateway ready";
    if (connection === "ready") return "Model is not ready";
    if (connection === "model_dead") return "Model engine is dead";
    if (connection === "degraded") return "Model upstream unavailable";
    if (connection === "key_missing") return "API key not configured";
    if (connection === "model_missing") return "Model id not configured";
    if (connection === "unreachable") return "Gateway unreachable";
    if (connection === "unknown") return "No model reported";
    return "Status unavailable";
  }

  function gatewayNotice(body, failed) {
    if (failed || !body) {
      return "The gateway is down. The status check did not succeed, so chat and the helpdesk cannot treat a model as ready.";
    }
    if (!body.gateway_reachable || body.connection === "unreachable") {
      return "The gateway is down. This console could not open the configured loopback gateway.";
    }
    if (body.connection === "model_dead" || body.model_dead === true || (body.health && body.health.reason === "model_engine_dead")) {
      return "The model engine is dead. A listed model is not treated as ready.";
    }
    if (!modelIsAlive(body) && body.connection === "ready") {
      return "The model is not ready. A dead or missing model is not treated as ready.";
    }
    if (body.connection === "unknown") {
      return "No loaded model was reported. An empty model list is not ready.";
    }
    if (body.connection === "degraded") {
      return "The model upstream is unavailable.";
    }
    if (body.connection === "key_missing") {
      return "The gateway answered, but the API key is not configured.";
    }
    if (body.connection === "model_missing") {
      return "The gateway answered, but no model id is configured for chat.";
    }
    return "";
  }

  function paintNotice(node, message, loading) {
    if (!node) return;
    if (loading) {
      node.hidden = false;
      node.className = "loading gateway-loading";
      node.setAttribute("role", "status");
      node.textContent = "Checking the gateway…";
      return;
    }
    if (!message) {
      node.hidden = true;
      node.textContent = "";
      return;
    }
    node.hidden = false;
    node.className = "banner banner-error";
    node.setAttribute("role", "alert");
    node.textContent = message;
  }

  function applyNavStatus(body, failed) {
    navStatus.className = "nav-status";
    if (statusInFlight && !lastStatus && !failed) {
      navStatus.textContent = "Checking gateway…";
      return;
    }
    if (failed) {
      navStatus.textContent = "The gateway is down";
      navStatus.classList.add("is-error");
      return;
    }
    var connection = body && body.connection ? body.connection : "unreachable";
    if (body && (body.model_dead === true || (body.health && body.health.reason === "model_engine_dead"))) {
      connection = "model_dead";
    } else if (connection === "ready" && !modelIsAlive(body)) {
      connection = "model_dead";
    }
    navStatus.textContent = statusLabel(connection, body);
    navStatus.classList.add("is-" + connection);
  }

  function paintGatewayState() {
    var failed = statusPhase === "failed" && !statusInFlight;
    var showLoading = (statusInFlight || statusPhase === "loading") && !lastStatus;
    var notice = showLoading ? "" : gatewayNotice(lastStatus, failed);
    if (statusLoading) {
      statusLoading.hidden = !showLoading && !statusInFlight;
      statusLoading.textContent = "Checking the gateway…";
    }
    if (statusError) {
      statusError.hidden = !notice;
      statusError.textContent = notice;
    }
    paintNotice(chatGateway, notice, showLoading);
    paintNotice(agentGateway, notice, showLoading);
  }

  function modelUsable(item) {
    if (!item || item.selection_eligible === false) return false;
    if (item.runtime_loaded === false) return false;
    return true;
  }

  function modelOptionLabel(item) {
    var label = item.id || "unknown";
    if (item.is_production_default) label += " (default)";
    if (item.runtime_loaded === true) label += " — loaded";
    else if (item.runtime_loaded === false) label += " — not loaded";
    else if (item.selection_eligible === false) label += " — unavailable";
    return label;
  }

  function renderModelSelect() {
    if (!modelSelect) return;
    var previous = selectedModelId || (lastStatus && lastStatus.model_id) || "";
    modelSelect.textContent = "";
    if (!catalogModels.length) {
      var empty = el("option", null, previous || "No registry catalog yet");
      empty.value = previous || "";
      modelSelect.appendChild(empty);
      modelSelect.disabled = !previous;
      if (modelHint) {
        modelHint.textContent = "Waiting for /api/platform/models. Only one GPU model can be loaded at a time.";
      }
      return;
    }
    catalogModels.forEach(function (item) {
      var option = el("option", null, modelOptionLabel(item));
      option.value = item.id;
      option.disabled = !modelUsable(item);
      modelSelect.appendChild(option);
    });
    var preferred = previous;
    var match = catalogModels.filter(function (item) { return item.id === preferred && modelUsable(item); })[0];
    if (!match) {
      match = catalogModels.filter(function (item) { return item.is_active_default && modelUsable(item); })[0];
    }
    selectedModelId = match ? match.id : "";
    modelSelect.value = selectedModelId;
    modelSelect.disabled = !selectedModelId;
    if (modelHint) {
      modelHint.textContent = selectedModelId
        ? ("Selected " + selectedModelId + ". Unavailable models stay listed but cannot be used until an operator switches the GPU runtime.")
        : "The configured default model is not loaded. Another model is not selected automatically.";
    }
  }

  function refreshModels() {
    return request("/api/platform/models").then(function (body) {
      catalogModels = Array.isArray(body && body.models) ? body.models : [];
      renderModelSelect();
    }).catch(function () {
      catalogModels = [];
      renderModelSelect();
    });
  }

  function refreshStatus() {
    statusInFlight = true;
    if (!lastStatus) statusPhase = "loading";
    paintGatewayState();
    if (!lastStatus) applyNavStatus(null, false);
    return request("/api/status").then(function (body) {
      lastStatus = body;
      statusPhase = "ok";
      if (!selectedModelId && body && body.model_id) selectedModelId = body.model_id;
      return refreshModels();
    }).catch(function () {
      lastStatus = null;
      statusPhase = "failed";
    }).then(function () {
      statusInFlight = false;
      applyNavStatus(lastStatus, statusPhase === "failed");
      paintGatewayState();
      if (!document.getElementById("status-view").hidden) renderStatus();
    });
  }

  function addRow(label, value) {
    return [el("dt", null, label), el("dd", null, value)];
  }

  function loadAcceptance() {
    request("/api/acceptance").then(renderAcceptance).catch(function () {
      renderAcceptance(null);
    });
  }

  function renderStatus() {
    loadAcceptance();
    paintGatewayState();
    if (!lastStatus) {
      statusPanel.hidden = true;
      statusPanel.textContent = "";
      return;
    }
    var body = lastStatus;
    var alive = modelIsAlive(body);
    var connection = body.connection;
    if (body.model_dead === true || (body.health && body.health.reason === "model_engine_dead")) {
      connection = "model_dead";
    } else if (connection === "ready" && !alive) {
      connection = "model_dead";
    }
    var detail = body.detail || "";
    if (!alive && /healthy/i.test(detail)) {
      detail = "The model is not ready. A dead or missing model is not treated as ready.";
    }
    statusPanel.hidden = false;
    statusPanel.textContent = "";
    var list = el("dl", "status-list");
    var rows = []
      .concat(addRow("Connection", statusLabel(connection, body)))
      .concat(addRow("Model alive", alive ? "Yes" : "No"))
      .concat(addRow("Gateway", body.gateway_url || "Not configured"))
      .concat(addRow("Gateway reachable", body.gateway_reachable ? "Yes" : "No"))
      .concat(addRow("Upstream", body.upstream || "Unknown"))
      .concat(addRow("API key configured", body.key_configured ? "Yes" : "No"))
      .concat(addRow("Key file", body.key_file || "Not set"))
      .concat(addRow("Key file found", body.key_file ? (body.key_file_found ? "Yes" : "No") : "Not applicable"))
      .concat(addRow("Default model id", body.model_id || "Not configured"))
      .concat(addRow("Selected model", selectedModelId || "Not selected"))
      .concat(addRow("RunPod connection", "Not verified"))
      .concat(addRow("Checked", new Date().toLocaleString()));
    if (body.health && typeof body.health.reason === "string") {
      rows = rows.concat(addRow("Health reason", body.health.reason));
    }
    if (body.health && typeof body.health.model_count === "number") {
      var countLabel = String(body.health.model_count);
      if (!alive) countLabel += " (not a live model)";
      rows = rows.concat(addRow("Models reported", countLabel));
    }
    rows.forEach(function (node) { list.appendChild(node); });
    statusPanel.appendChild(list);
    statusPanel.appendChild(el("p", "meta", detail));
  }

  function acceptanceBar(percent, live) {
    var track = el("div", "bar-track");
    var fill = el("div", live ? "bar-fill-live" : "bar-fill");
    fill.style.width = Math.max(0, Math.min(100, Number(percent) || 0)) + "%";
    track.appendChild(fill);
    return track;
  }

  function renderAcceptanceRow(row) {
    var section = el("section", "acceptance-row");
    section.appendChild(el("h3", null, row.name + " " + row.percent + "%"));
    section.appendChild(acceptanceBar(row.percent, row.lane === "live"));
    section.appendChild(el("p", "meta", "Completed: " + ((row.completed || []).join("; ") || "None")));
    section.appendChild(el("p", "meta", "Remaining: " + ((row.remaining || []).join("; ") || "None")));
    section.appendChild(el("p", "meta", "Evidence: " + (row.evidence || "")));
    section.appendChild(el("p", "meta", "Next: " + (row.next_action || "") + " Blocker: " + (row.blocker || "")));
    return section;
  }

  function renderAcceptance(board) {
    var decision = document.getElementById("acceptance-decision");
    var summary = document.getElementById("acceptance-summary");
    var rows = document.getElementById("acceptance-rows");
    if (!decision || !rows) return;
    rows.textContent = "";
    if (summary) summary.textContent = "";
    if (!board || !Array.isArray(board.workstreams)) {
      decision.textContent = "The acceptance board could not be loaded.";
      return;
    }
    decision.className = "acceptance-decision";
    decision.textContent = "Production decision " + board.decision + ". Offline implementation is not a production GO. Live acceptance " + board.live_acceptance_percent + "%. " + (board.note || "");
    if (summary) {
      var offline = el("section", "acceptance-row");
      offline.appendChild(el("h3", null, "Offline implementation " + board.offline_percent + "%"));
      offline.appendChild(acceptanceBar(board.offline_percent, false));
      summary.appendChild(offline);
      var live = el("section", "acceptance-row");
      live.appendChild(el("h3", null, "Live acceptance " + board.live_acceptance_percent + "%"));
      live.appendChild(acceptanceBar(board.live_acceptance_percent, true));
      summary.appendChild(live);
    }
    var offlineRows = board.workstreams.filter(function (row) { return row.lane !== "live"; });
    var liveRows = board.workstreams.filter(function (row) { return row.lane === "live"; });
    rows.appendChild(el("h3", "lane-label", "Offline implementation"));
    offlineRows.forEach(function (row) { rows.appendChild(renderAcceptanceRow(row)); });
    rows.appendChild(el("h3", "lane-label", "Live acceptance"));
    liveRows.forEach(function (row) { rows.appendChild(renderAcceptanceRow(row)); });
  }

  function renderChat() {
    chatLog.textContent = "";
    if (!messages.length && !busy) {
      chatLog.appendChild(el("p", "placeholder", "Send a message to the local gateway."));
      return;
    }
    messages.forEach(function (message) {
      var block = el("article", "message " + (message.role === "user" ? "message-user" : "message-assistant"));
      block.appendChild(el("div", "message-label", message.role === "user" ? "You" : "Assistant"));
      block.appendChild(el("p", null, message.content));
      chatLog.appendChild(block);
    });
    if (busy) {
      var pending = el("article", "message message-assistant");
      pending.appendChild(el("div", "message-label", "Assistant"));
      pending.appendChild(el("p", null, "Generating a reply…"));
      chatLog.appendChild(pending);
    }
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function retrievalText(retrieval) {
    if (!retrieval || typeof retrieval !== "object") return "";
    var parts = [];
    if (retrieval.reason === "below_min_score") parts.push("The best match was below the gateway score threshold.");
    else if (retrieval.reason === "no_match") parts.push("No document match was found.");
    else if (retrieval.reason === "low_query_coverage") parts.push("The documents do not appear to cover the key terms of this question.");
    else if (retrieval.reason === "invalid_citations") parts.push("The answer cited a source that was not in the evidence.");
    else if (retrieval.reason === "missing_citations") parts.push("The answer did not cite a source from the evidence.");
    else if (typeof retrieval.reason === "string") parts.push("Retrieval: " + retrieval.reason);
    if (typeof retrieval.top_score === "number") parts.push("Top score " + retrieval.top_score + ".");
    if (typeof retrieval.minimum_score === "number") parts.push("Minimum score " + retrieval.minimum_score + ".");
    return parts.join(" ");
  }

  function renderSources(sources) {
    var list = el("ul", "sources");
    if (!sources || !sources.length) {
      list.appendChild(el("li", null, "No sources were cited."));
      return list;
    }
    sources.forEach(function (source) {
      var item = el("li");
      item.appendChild(el("strong", null, source && source.label ? source.label : "Source"));
      item.appendChild(el("span", null, source && source.file ? source.file : "Unknown file"));
      var where = locationText(source && source.location);
      var chunk = source && source.chunk != null ? "Chunk " + source.chunk : "Chunk unknown";
      var score = source && typeof source.score === "number" ? "Score " + source.score : "Score unavailable";
      item.appendChild(el("span", null, (where ? where + " · " : "") + chunk + " · " + score));
      if (source && Array.isArray(source.duplicate_files) && source.duplicate_files.length > 1) {
        item.appendChild(el("span", null, "Identical content also in: " + source.duplicate_files.slice(1).join(", ")));
      }
      if (source && Array.isArray(source.flags) && source.flags.indexOf("instruction_like_text") !== -1) {
        item.appendChild(el("span", "source-warning", "Warning: this passage contains instruction-like text and was treated as data only."));
      }
      list.appendChild(item);
    });
    return list;
  }

  function locationText(location) {
    if (!location || typeof location !== "object") return "";
    var parts = [];
    if (typeof location.page === "number") parts.push("Page " + location.page);
    if (typeof location.sheet === "string" && location.sheet) parts.push("Sheet " + location.sheet);
    if (typeof location.row_start === "number") {
      var rows = location.row_start;
      if (typeof location.row_end === "number" && location.row_end !== location.row_start) rows += "–" + location.row_end;
      parts.push("Rows " + rows);
    }
    return parts.join(", ");
  }

  function historyPayload() {
    var pairs = [];
    ragTurns.forEach(function (turn) {
      if (!turn || typeof turn.question !== "string" || typeof turn.answer !== "string") return;
      pairs.push({ role: "user", content: turn.question });
      pairs.push({ role: "assistant", content: turn.answer });
    });
    if (pairs.length > MAX_RAG_HISTORY_MESSAGES) {
      return pairs.slice(pairs.length - MAX_RAG_HISTORY_MESSAGES);
    }
    return pairs;
  }

  function renderRag() {
    ragLog.textContent = "";
    if (!ragTurns.length && !ragBusy) {
      ragLog.appendChild(el("p", "placeholder", "Ask a document question. Follow-ups stay in this conversation."));
      return;
    }
    ragTurns.forEach(function (turn) {
      var userBlock = el("article", "message message-user");
      userBlock.appendChild(el("div", "message-label", "You"));
      userBlock.appendChild(el("p", null, turn.question));
      ragLog.appendChild(userBlock);

      var assistantBlock = el("article", "message message-assistant");
      assistantBlock.appendChild(el("div", "message-label", "Assistant"));
      var answered = turn.status === "answered";
      assistantBlock.appendChild(el("div", "badge " + (answered ? "badge-answered" : "badge-abstained"), answered ? "Answered" : "Abstained"));
      assistantBlock.appendChild(el("p", "answer", turn.answer || ""));
      var notes = [];
      if (turn.collection) notes.push("Collection " + turn.collection + ".");
      if (turn.model) notes.push("Model " + turn.model + ".");
      var retrieval = retrievalText(turn.retrieval);
      if (retrieval) notes.push(retrieval);
      if (notes.length) assistantBlock.appendChild(el("p", "meta", notes.join(" ")));
      var sourcesWrap = el("div", "message-sources");
      sourcesWrap.appendChild(el("h3", null, "Sources"));
      sourcesWrap.appendChild(renderSources(turn.sources));
      assistantBlock.appendChild(sourcesWrap);
      ragLog.appendChild(assistantBlock);
    });
    if (ragBusy) {
      var pending = el("article", "message message-assistant");
      pending.appendChild(el("div", "message-label", "Assistant"));
      pending.appendChild(el("p", null, "Searching documents… You can type the next question now; Ask stays locked until this reply finishes."));
      ragLog.appendChild(pending);
    }
    ragLog.scrollTop = ragLog.scrollHeight;
  }

  document.querySelectorAll("[data-view]").forEach(function (button) {
    button.addEventListener("click", function () {
      showView(button.getAttribute("data-view"));
    });
  });

  window.addEventListener("hashchange", function () {
    showView(location.hash.replace("#", ""));
  });

  chatInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatForm.requestSubmit();
    }
  });

  ragQuestion.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      ragForm.requestSubmit();
    }
  });

  if (modelSelect) {
    modelSelect.addEventListener("change", function () {
      selectedModelId = modelSelect.value || "";
      showError(chatError, "");
    });
  }

  chatForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (busy) return;
    var content = chatInput.value.trim();
    if (!content) return;
    if (!selectedModelId) {
      showError(chatError, "Select a loaded model before sending a chat message.");
      return;
    }
    messages.push({ role: "user", content: content });
    chatInput.value = "";
    busy = true;
    chatSend.disabled = true;
    chatLoading.hidden = false;
    showError(chatError, "");
    renderChat();
    request("/api/chat", {
      method: "POST",
      body: { model: selectedModelId, messages: messages }
    }).then(function (body) {
      var contentText = body && body.choices && body.choices[0] && body.choices[0].message
        ? body.choices[0].message.content
        : "";
      if (typeof contentText !== "string" || !contentText.trim()) {
        throw new Error("The model returned an empty reply.");
      }
      var note = "";
      if (body.platform_selection && body.platform_selection.resolved_id) {
        note = "\n\n[Selected model: " + body.platform_selection.resolved_id + "]";
      }
      messages.push({ role: "assistant", content: contentText.trim() + note });
    }).catch(function (error) {
      showError(chatError, errorMessage(error));
    }).finally(function () {
      busy = false;
      chatSend.disabled = false;
      chatLoading.hidden = true;
      renderChat();
      refreshStatus();
    });
  });

  document.getElementById("chat-clear").addEventListener("click", function () {
    if (busy) return;
    messages = [];
    showError(chatError, "");
    renderChat();
  });

  ragForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (ragBusy) return;
    var question = ragQuestion.value.trim();
    if (!question) return;
    var collection = ragCollection.value.trim();
    if (collection && !/^[a-z0-9][a-z0-9_-]{0,39}$/.test(collection)) {
      showError(ragError, "Collection must be a lowercase slug using letters, numbers, hyphens, or underscores.");
      return;
    }
    var body = {
      question: question,
      top_k: Number(ragTopK.value),
      history: historyPayload()
    };
    if (collection) body.collection = collection;
    ragQuestion.value = "";
    setRagBusy(true);
    showError(ragError, "");
    renderRag();
    request("/api/rag", { method: "POST", body: body }).then(function (result) {
      var answer = typeof result.answer === "string" ? result.answer : "";
      if (!answer.trim()) {
        throw new Error("The document endpoint returned an empty answer.");
      }
      ragTurns.push({
        question: question,
        answer: answer.trim(),
        status: result.status === "answered" ? "answered" : "abstained",
        sources: Array.isArray(result.sources) ? result.sources : [],
        retrieval: result.retrieval || null,
        collection: result.collection || collection || null,
        model: result.model || null
      });
    }).catch(function (error) {
      showError(ragError, errorMessage(error));
    }).finally(function () {
      setRagBusy(false);
      renderRag();
      refreshStatus();
      ragQuestion.focus();
    });
  });

  ragClear.addEventListener("click", function () {
    if (ragBusy) return;
    // Clear transcript/history only. Keep collection, top_k, and uploaded docs.
    ragTurns = [];
    showError(ragError, "");
    renderRag();
    ragQuestion.focus();
  });

  function renderDocumentList(documents, collection) {
    documentList.textContent = "";
    if (!documents || !documents.length) {
      documentList.appendChild(el("li", null, "No documents in this collection yet."));
      return;
    }
    documents.forEach(function (documentInfo) {
      var item = el("li");
      item.appendChild(el("strong", null, documentInfo.filename));
      item.appendChild(el("span", null, documentInfo.extension + " · " + Number(documentInfo.size_bytes).toLocaleString() + " bytes"));
      var remove = el("button", "secondary", "Delete");
      remove.type = "button";
      remove.addEventListener("click", function () {
        if (!window.confirm("Delete " + documentInfo.filename + " from collection " + collection + "?")) return;
        request("/api/documents?collection=" + encodeURIComponent(collection) + "&filename=" + encodeURIComponent(documentInfo.filename), { method: "DELETE" })
          .then(function (body) {
            if (!body || body.removed_from_index !== true) {
              throw new Error("Delete completed but the document may still be searchable. Refresh and retry.");
            }
            // Clear conversation so prior answers cannot cite the deleted workbook.
            ragTurns = [];
            renderRag();
            uploadStatus.textContent = "Deleted " + documentInfo.filename + " and removed it from search. Conversation cleared.";
            syncCollectionFields(collection);
            return loadDocuments();
          })
          .catch(function (error) { showError(uploadError, errorMessage(error)); });
      });
      item.appendChild(remove);
      documentList.appendChild(item);
    });
  }

  function syncCollectionFields(collection) {
    if (!collection) return;
    uploadCollection.value = collection;
    ragCollection.value = collection;
  }

  function loadDocuments() {
    var collection = uploadCollection.value.trim();
    if (!/^[a-z0-9][a-z0-9_-]{0,39}$/.test(collection)) {
      showError(uploadError, "Use lowercase letters, numbers, hyphens or underscores for the collection.");
      return Promise.reject(new Error("Invalid collection name"));
    }
    syncCollectionFields(collection);
    return request("/api/documents?collection=" + encodeURIComponent(collection)).then(function (body) {
      renderDocumentList(body.documents || [], collection);
      showError(uploadError, "");
    });
  }

  uploadForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var collection = uploadCollection.value.trim();
    var file = uploadFile.files && uploadFile.files[0];
    if (!/^[a-z0-9][a-z0-9_-]{0,39}$/.test(collection)) {
      showError(uploadError, "Collection must be a lowercase slug (letters, numbers, hyphens or underscores).");
      return;
    }
    if (!file) {
      showError(uploadError, "Choose a document first.");
      return;
    }
    if (file.size < 1 || file.size > 10 * 1024 * 1024) {
      showError(uploadError, "Choose a non-empty file no larger than 10 MiB.");
      return;
    }
    var ext = file.name.indexOf(".") >= 0 ? file.name.slice(file.name.lastIndexOf(".")).toLowerCase() : "";
    if ([".txt", ".md", ".csv", ".html", ".htm", ".docx", ".pdf", ".xlsx"].indexOf(ext) < 0) {
      showError(uploadError, "This file type is not supported.");
      return;
    }
    showError(uploadError, "");
    uploadStatus.textContent = "";
    uploadSubmit.disabled = true;
    uploadLoading.hidden = false;
    var reader = new FileReader();
    reader.onerror = function () {
      showError(uploadError, "The browser could not read this file.");
      uploadSubmit.disabled = false;
      uploadLoading.hidden = true;
    };
    reader.onload = function () {
      var dataUrl = String(reader.result || "");
      var comma = dataUrl.indexOf(",");
      if (comma < 0) {
        showError(uploadError, "The browser returned an invalid file encoding.");
        uploadSubmit.disabled = false;
        uploadLoading.hidden = true;
        return;
      }
      request("/api/documents", {
        method: "POST",
        body: { collection: collection, filename: file.name, content_base64: dataUrl.slice(comma + 1), overwrite: false }
      }).then(function (body) {
        var documentInfo = body && body.document ? body.document : null;
        if (!documentInfo || documentInfo.searchable !== true) {
          throw new Error("Upload finished but the document is not searchable yet. Do not ask questions against it until indexing succeeds.");
        }
        syncCollectionFields(collection);
        ragTurns = [];
        renderRag();
        uploadStatus.textContent = "Saved and searchable: " + documentInfo.filename + " (" + Number(documentInfo.chunk_count || 0).toLocaleString() + " chunks) in " + collection + ".";
        uploadFile.value = "";
        return loadDocuments();
      }).catch(function (error) {
        showError(uploadError, errorMessage(error));
      }).finally(function () {
        uploadSubmit.disabled = false;
        uploadLoading.hidden = true;
      });
    };
    reader.readAsDataURL(file);
  });

  document.getElementById("list-documents").addEventListener("click", function () {
    loadDocuments().catch(function (error) {
      if (error && error.message !== "Invalid collection name") showError(uploadError, errorMessage(error));
    });
  });

  uploadCollection.addEventListener("change", function () {
    syncCollectionFields(uploadCollection.value.trim());
    loadDocuments().catch(function (error) {
      if (error && error.message !== "Invalid collection name") showError(uploadError, errorMessage(error));
    });
  });
  ragCollection.addEventListener("change", function () {
    var collection = ragCollection.value.trim();
    if (collection) syncCollectionFields(collection);
  });

  var agentForm = document.getElementById("agent-form");
  var agentTask = document.getElementById("agent-task");
  var agentTaskType = document.getElementById("agent-task-type");
  var agentError = document.getElementById("agent-error");
  var agentLog = document.getElementById("agent-log");
  var agentSend = document.getElementById("agent-send");
  var agentLoading = document.getElementById("agent-loading");
  var agentApproval = document.getElementById("agent-approval");
  var agentApprovalText = document.getElementById("agent-approval-text");
  var agentApprovalWhat = document.getElementById("agent-approval-what");
  var agentApprovalWhy = document.getElementById("agent-approval-why");
  var agentApprovalSystem = document.getElementById("agent-approval-system");
  var agentApprovalRisks = document.getElementById("agent-approval-risks");
  var agentApprovalVerify = document.getElementById("agent-approval-verify");
  var agentApprovalTarget = document.getElementById("agent-approval-target");
  var agentApprovalArgs = document.getElementById("agent-approval-args");
  var agentExecution = document.getElementById("agent-execution");
  var agentRecord = document.getElementById("agent-record");
  var agentIncident = document.getElementById("agent-incident");
  var agentIncidentBody = document.getElementById("agent-incident-body");
  var agentInfo = document.getElementById("agent-info");
  var agentInfoText = document.getElementById("agent-info-text");
  var agentInfoInput = document.getElementById("agent-info-input");
  var agentCancel = document.getElementById("agent-cancel");
  var agentHistory = document.getElementById("agent-history");
  var agentHistoryEmpty = document.getElementById("agent-history-empty");
  var connectorList = document.getElementById("connector-list");
  var agentTaskId = "";
  var agentCallId = "";
  var agentPollTimer = null;
  var executionLabels = {
    queued: "Queued",
    received: "Received",
    investigating: "Investigating",
    awaiting_information: "Awaiting information",
    awaiting_approval: "Awaiting approval",
    executing: "Executing",
    verifying: "Verifying",
    completed: "Completed",
    failed: "Failed",
    escalated: "Escalated",
    cancelled: "Cancelled"
  };
  var terminalExecution = {
    completed: true,
    failed: true,
    escalated: true,
    cancelled: true
  };

  function stopAgentPoll() {
    if (agentPollTimer) {
      window.clearInterval(agentPollTimer);
      agentPollTimer = null;
    }
  }

  function loadAgentHistory() {
    return request("/api/agent/history?limit=12").then(function (result) {
      agentHistory.textContent = "";
      var tasks = (result && result.tasks) || [];
      agentHistoryEmpty.hidden = tasks.length > 0;
      tasks.forEach(function (item) {
        var label = executionLabels[item.execution] || item.execution || item.state || "unknown";
        var goal = item.goal || "(no goal)";
        if (goal.length > 80) goal = goal.slice(0, 77) + "...";
        var row = el("li", null, label + " — " + goal);
        row.title = item.task_id || "";
        row.addEventListener("click", function () {
          if (!item.task_id) return;
          request("/api/agent?task_id=" + encodeURIComponent(item.task_id)).then(function (view) {
            agentTaskId = view.task_id || "";
            renderAgent(view);
            if (view.running) startAgentPoll(view.task_id);
          }).catch(function (error) {
            showError(agentError, errorMessage(error));
          });
        });
        agentHistory.appendChild(row);
      });
    }).catch(function () {
      agentHistoryEmpty.hidden = false;
      agentHistoryEmpty.textContent = "Task history is unavailable.";
    });
  }

  function startAgentPoll(taskId) {
    stopAgentPoll();
    if (!taskId) return;
    agentPollTimer = window.setInterval(function () {
      request("/api/agent?task_id=" + encodeURIComponent(taskId)).then(function (view) {
        renderAgent(view);
        var execution = view.execution || view.state;
        var paused = execution === "awaiting_approval" || execution === "awaiting_information";
        if (!view.running && (terminalExecution[execution] || paused)) {
          stopAgentPoll();
          agentLoading.hidden = true;
          agentSend.disabled = false;
          loadAgentHistory();
        }
      }).catch(function () {
        stopAgentPoll();
        agentLoading.hidden = true;
        agentSend.disabled = false;
      });
    }, 750);
  }

  function renderAgent(view) {
    agentLog.textContent = "";
    agentRecord.textContent = "";
    if (agentIncidentBody) agentIncidentBody.textContent = "";
    if (!view) {
      agentExecution.textContent = "";
      agentLog.appendChild(el("p", "empty", "Submit an IT issue to see the investigation."));
      agentApproval.hidden = true;
      if (agentIncident) agentIncident.hidden = true;
      agentInfo.hidden = true;
      agentCancel.hidden = true;
      return;
    }
    var execution = view.execution || view.state;
    var label = executionLabels[execution] || execution;
    if (view.running) label = label + " (in progress)";
    var states = (view.states || []).map(function (item) {
      return executionLabels[item] || item;
    });
    agentExecution.textContent = states.length
      ? "Status: " + label + ". Steps: " + states.join(" → ")
      : "Status: " + label;
    var record = view.record || {};
    if (view.task_kind) agentRecord.appendChild(el("p", "meta", "Task type: " + view.task_kind));
    if (view.task_kind) {
      var ran = view.tools_executed || [];
      agentRecord.appendChild(el("p", "meta", "Tools that ran: " + (ran.length ? ran.join(", ") : "none")));
    }
    if (record.objective) agentRecord.appendChild(el("p", null, "Issue: " + record.objective));
    (record.plan || []).forEach(function (step) {
      agentRecord.appendChild(el("p", "meta", "Plan: " + step));
    });
    (record.tool_calls || []).forEach(function (call) {
      agentRecord.appendChild(el("p", "meta", "Checked with tool: " + (call.tool || "unknown")));
    });
    (record.results || []).forEach(function (result) {
      var ok = result.ok === false ? "failed" : "ok";
      var preview = result.preview ? " — " + result.preview : "";
      agentRecord.appendChild(el("p", "meta", "Result (" + ok + "): " + (result.tool || "tool") + preview));
    });
    (record.verification || []).forEach(function (check) {
      var ok = check.ok === false ? "not confirmed" : "confirmed";
      agentRecord.appendChild(el("p", "meta", "Verification — " + (check.check || "step") + ": " + ok + (check.tool ? " (" + check.tool + ")" : "")));
    });
    (record.errors || []).forEach(function (err) {
      agentRecord.appendChild(el("p", "meta", "Problem: " + (err.kind || "issue") + (err.detail ? " — " + err.detail : "")));
    });
    if (record.outcome) agentRecord.appendChild(el("p", "meta", "Outcome: " + record.outcome));
    var incident = view.incident_report;
    if (agentIncident && agentIncidentBody) {
      if (incident) {
        agentIncident.hidden = false;
        agentIncidentBody.appendChild(el("p", null, incident.summary || "Incident closed."));
        agentIncidentBody.appendChild(el("p", "meta", "Severity: " + (incident.severity || "unknown") + (incident.category ? " · Category: " + incident.category : "")));
        if (incident.desired_outcome) {
          agentIncidentBody.appendChild(el("p", "meta", "Desired outcome: " + incident.desired_outcome));
        }
        (incident.evidence || []).forEach(function (item) {
          agentIncidentBody.appendChild(el("p", "meta", "Evidence: " + item));
        });
        (incident.actions_taken || []).forEach(function (item) {
          agentIncidentBody.appendChild(el("p", "meta", "Action: " + item));
        });
        (incident.verification || []).forEach(function (item) {
          agentIncidentBody.appendChild(el("p", "meta", "Verified: " + item));
        });
        (incident.next_steps || []).forEach(function (item) {
          agentIncidentBody.appendChild(el("p", "meta", "Next: " + item));
        });
        agentIncidentBody.appendChild(el("p", "meta", "Final status: " + (incident.outcome || "unknown")));
      } else {
        agentIncident.hidden = true;
      }
    }
    var headingText = view.answer || view.failure || label;
    if (execution === "queued") headingText = "Waiting in the queue for an earlier task to finish.";
    if (execution === "completed") headingText = view.answer || "Completed.";
    if (execution === "failed") headingText = view.failure || "The investigation could not finish. Try again or add more detail.";
    if (execution === "escalated") headingText = view.answer || "This needs a person to continue.";
    agentLog.appendChild(el("p", null, headingText));
    (view.activity || []).forEach(function (item) {
      var labels = {
        tool_requested: "Used a tool",
        tool_result: "Tool result",
        tool_error: "Tool problem",
        approval_required: "Waiting for approval",
        approval_decision: "Approval recorded",
        information_requested: "Asked for information",
        task_final: "Finished",
        task_failed: "Failed",
        task_cancelled: "Cancelled"
      };
      var line = (labels[item.kind] || item.kind) + (item.tool ? ": " + item.tool : "");
      if (item.detail) line += " — " + item.detail;
      agentLog.appendChild(el("p", "meta", line));
    });
    var pending = view.pending_approval;
    agentApproval.hidden = !pending;
    agentInfo.hidden = execution !== "awaiting_information";
    agentCancel.hidden = !(view.cancellable || view.running || execution === "queued" || execution === "awaiting_approval" || execution === "awaiting_information");
    if (pending) {
      agentTaskId = view.task_id;
      agentCallId = pending.call_id || "";
      agentApprovalText.textContent = pending.reason || "This change needs your approval before it runs.";
      if (agentApprovalWhat) agentApprovalWhat.textContent = "What changes: " + (pending.what_changes || pending.tool || "See details below.");
      if (agentApprovalWhy) agentApprovalWhy.textContent = "Why: " + (pending.why || "Recommended to address the reported issue.");
      if (agentApprovalSystem) agentApprovalSystem.textContent = "System affected: " + (pending.system || "local platform");
      if (agentApprovalRisks) agentApprovalRisks.textContent = "Risks: " + (pending.risks || "May change local console state.");
      if (agentApprovalVerify) agentApprovalVerify.textContent = "How success will be checked: " + (pending.verification_plan || "A follow-up health or diagnostic check.");
      agentApprovalTarget.textContent = "Tool " + pending.tool + ", call " + pending.call_id;
      agentApprovalArgs.textContent = JSON.stringify(pending.arguments || {}, null, 2);
    } else {
      agentCallId = "";
    }
    if (execution === "awaiting_information") {
      agentTaskId = view.task_id;
      agentInfoText.textContent = view.pending_question || "The agent needs a bit more information to continue.";
    }
  }

  function renderMicrosoft(signIn) {
    var status = document.getElementById("microsoft-status");
    var setup = document.getElementById("microsoft-setup");
    var permissions = document.getElementById("microsoft-permissions");
    var mail = document.getElementById("microsoft-mail");
    var options = document.getElementById("microsoft-signin");
    var disconnect = document.getElementById("microsoft-disconnect");
    var notice = microsoftNotice();
    var state = signIn.status || (signIn.connected ? "connected" : (signIn.configured ? "disconnected" : "unconfigured"));
    var labels = {
      unconfigured: "Microsoft is not configured.",
      disconnected: "Microsoft is disconnected.",
      connected: "Microsoft is connected.",
      error: "Microsoft sign-in needs attention."
    };
    if (notice === "connected" && state !== "connected") {
      status.textContent = "Microsoft is disconnected.";
    } else {
      status.textContent = labels[state] || "Microsoft status is unknown.";
    }
    setup.textContent = signIn.setup || "";
    if (signIn.permissions) permissions.textContent = signIn.permissions;
    options.textContent = "";
    options.hidden = state === "connected";
    if (state !== "connected") {
      (signIn.accounts || []).forEach(function (account) {
        var control = signIn.configured ? document.createElement("a") : document.createElement("button");
        control.className = account.id === "any" ? "sign-in" : "sign-in secondary";
        control.textContent = account.label;
        if (signIn.configured) {
          control.href = "/api/microsoft/start?account=" + encodeURIComponent(account.id);
        } else {
          control.type = "button";
          control.disabled = true;
        }
        options.appendChild(control);
        if (account.detail) options.appendChild(el("p", "meta", account.detail));
      });
    }
    disconnect.hidden = state !== "connected";
    disconnect.disabled = false;
    disconnect.textContent = "Disconnect Microsoft";
    if (state === "connected" && signIn.account) {
      mail.textContent = signIn.mail_read
        ? "Verified account " + signIn.account + ". Mail search is read-only."
        : "Verified account " + signIn.account + ". Mail.Read was not granted, so mail search stays unavailable.";
    } else if (notice === "connected") {
      mail.textContent = "The browser returned from Microsoft, but this server has not confirmed an account.";
    } else if (notice === "cancelled") {
      mail.textContent = "Microsoft sign-in was cancelled. No mailbox was read.";
    } else if (notice === "failed") {
      mail.textContent = "Microsoft sign-in did not finish. No mailbox was read.";
    } else {
      mail.textContent = "";
    }
  }

  function microsoftNotice() {
    var params = new URLSearchParams(location.search);
    var result = params.get("microsoft");
    if (result !== "connected" && result !== "cancelled" && result !== "failed") return "";
    params.delete("microsoft");
    var query = params.toString();
    history.replaceState(null, "", location.pathname + (query ? "?" + query : "") + (location.hash || "#agent"));
    return result;
  }

  function loadConnectors() {
    request("/api/connectors").then(function (result) {
      connectorList.textContent = "";
      var rows = result.connectors || [];
      if (!rows.length) {
        connectorList.appendChild(el("li", null, "No connectors are registered."));
        return;
      }
      rows.forEach(function (row) {
        var readiness = row.readiness || (row.connected ? "connected" : "disconnected");
        var label = row.service + " — " + readiness;
        if (row.account) label += " as " + row.account;
        if (row.detail) label += ". " + row.detail;
        connectorList.appendChild(el("li", null, label));
        (row.operations || []).forEach(function (op) {
          var opLabel = (op.tool_name || op.name) + " — " + (op.status || op.evidence || "unavailable");
          connectorList.appendChild(el("li", "meta", opLabel));
        });
        if (row.connector_id === "microsoft365") renderMicrosoft(row.sign_in || {});
      });
      loadDevices();
    }).catch(function (error) {
      showError(agentError, errorMessage(error));
    });
  }

  function loadDevices() {
    var list = document.getElementById("device-list");
    request("/api/devices").then(function (body) {
      list.textContent = "";
      var devices = body.devices || [];
      if (!devices.length) {
        list.appendChild(el("li", null, "No computer is enrolled."));
        return;
      }
      devices.forEach(function (device) {
        var text = device.display_name + " — " + device.status;
        if (device.report && device.report.status === "ok") {
          text += ". " + device.report.os_family + ", " + device.report.disk_free_bytes + " bytes free. Remote control is off.";
        } else {
          text += ". No diagnostic has arrived. Remote control is off.";
        }
        var item = el("li");
        item.appendChild(document.createTextNode(text + " "));
        if (device.status === "enrolled") {
          var button = el("button", "secondary", "Revoke");
          button.type = "button";
          button.addEventListener("click", function () {
            request("/api/devices/revoke", { method: "POST", body: { device_id: device.device_id } }).then(function () {
              loadDevices();
              loadConnectors();
            }).catch(function (error) {
              showError(agentError, errorMessage(error));
            });
          });
          item.appendChild(button);
        }
        list.appendChild(item);
      });
    }).catch(function (error) {
      showError(agentError, errorMessage(error));
    });
  }

  document.getElementById("device-enrol").addEventListener("click", function () {
    var node = document.getElementById("device-code");
    request("/api/devices/enrolment", { method: "POST", body: {} }).then(function (body) {
      node.textContent = "On that computer run python -m integrations.endpoint_worker enrol --code " +
        body.enrolment_code + " --name \"Office PC\" --console http://127.0.0.1:8080 --token-file <private-file>. " +
        "The code works once, expires in " + body.expires_in_seconds +
        " seconds, and cannot control the computer. It is not shown again.";
    }).catch(function (error) {
      showError(agentError, errorMessage(error));
    });
  });

  agentForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var task = agentTask.value.trim();
    if (!task) return;
    stopAgentPoll();
    agentSend.disabled = true;
    agentLoading.hidden = false;
    showError(agentError, "");
    var body = { task: task, wait: false };
    if (agentTaskType && agentTaskType.value) body.task_type = agentTaskType.value;
    request("/api/agent", { method: "POST", body: body }).then(function (result) {
      agentTaskId = result.task_id || "";
      renderAgent(result);
      if (result.running || !(terminalExecution[result.execution] || result.execution === "awaiting_approval" || result.execution === "awaiting_information")) {
        startAgentPoll(agentTaskId);
      } else {
        agentSend.disabled = false;
        agentLoading.hidden = true;
        loadAgentHistory();
      }
    }).catch(function (error) {
      showError(agentError, errorMessage(error));
      agentSend.disabled = false;
      agentLoading.hidden = true;
    });
  });

  function decide(approved) {
    if (!agentTaskId) return;
    request("/api/agent/decision", {
      method: "POST",
      body: { task_id: agentTaskId, call_id: agentCallId, approved: approved }
    }).then(function (result) {
      renderAgent(result);
    }).catch(function (error) {
      showError(agentError, errorMessage(error));
    });
  }

  document.getElementById("microsoft-disconnect").addEventListener("click", function () {
    var button = document.getElementById("microsoft-disconnect");
    button.disabled = true;
    button.textContent = "Disconnecting…";
    request("/api/microsoft/disconnect", { method: "POST", body: {} }).then(function () {
      loadConnectors();
    }).catch(function (error) {
      button.disabled = false;
      button.textContent = "Disconnect Microsoft";
      showError(agentError, errorMessage(error));
    });
  });
  document.getElementById("agent-approve").addEventListener("click", function () { decide(true); });
  document.getElementById("agent-reject").addEventListener("click", function () { decide(false); });
  document.getElementById("agent-info-send").addEventListener("click", function () {
    var information = agentInfoInput.value.trim();
    if (!agentTaskId || !information) return;
    request("/api/agent/information", {
      method: "POST",
      body: { task_id: agentTaskId, information: information }
    }).then(function (result) {
      agentInfoInput.value = "";
      renderAgent(result);
    }).catch(function (error) {
      showError(agentError, errorMessage(error));
    });
  });
  agentCancel.addEventListener("click", function () {
    if (!agentTaskId) return;
    request("/api/agent/cancel", {
      method: "POST",
      body: { task_id: agentTaskId }
    }).then(function (result) {
      renderAgent(result);
      if (result.running) startAgentPoll(agentTaskId);
      else {
        stopAgentPoll();
        agentLoading.hidden = true;
        agentSend.disabled = false;
        loadAgentHistory();
      }
    }).catch(function (error) {
      showError(agentError, errorMessage(error));
    });
  });
  renderAgent(null);
  loadAgentHistory();
  document.getElementById("nav-agent").addEventListener("click", function () {
    loadAgentHistory();
  });

  document.getElementById("status-refresh").addEventListener("click", refreshStatus);

  var opsError = document.getElementById("ops-error");
  var opsOverall = document.getElementById("ops-overall");
  var opsOverviewList = document.getElementById("ops-overview-list");
  var opsHealthList = document.getElementById("ops-health-list");
  var opsAlertsList = document.getElementById("ops-alerts-list");
  var opsAlertsEmpty = document.getElementById("ops-alerts-empty");
  var opsIncidentsList = document.getElementById("ops-incidents-list");
  var opsIncidentsEmpty = document.getElementById("ops-incidents-empty");
  var opsTimeline = document.getElementById("ops-timeline");
  var opsCoverage = document.getElementById("ops-coverage");
  var opsIntegrity = document.getElementById("ops-integrity");

  function showOpsError(message) {
    if (!opsError) return;
    if (!message) {
      opsError.hidden = true;
      opsError.textContent = "";
      return;
    }
    opsError.hidden = false;
    opsError.textContent = message;
  }

  function li(text) {
    var item = document.createElement("li");
    item.textContent = text;
    return item;
  }

  function loadOpsCentre(filterQ) {
    showOpsError("");
    var overviewReq = request("/api/ops/overview");
    var eventsPath = "/api/ops/events?limit=40";
    if (filterQ) eventsPath += "&q=" + encodeURIComponent(filterQ);
    var eventsReq = request(eventsPath);
    var coverageReq = request("/api/ops/coverage");
    var integrityReq = request("/api/ops/integrity");
    Promise.all([overviewReq, eventsReq, coverageReq, integrityReq]).then(function (parts) {
      var overview = parts[0];
      var events = parts[1];
      var coverage = parts[2];
      var integrity = parts[3];
      opsOverall.textContent =
        "Overall: " + (overview.overall || "unknown")
        + " · verified " + (overview.verified_at || "never")
        + " · " + (overview.verification || "unknown")
        + ". " + (overview.coverage_note || "");
      opsOverviewList.innerHTML = "";
      var counts = overview.alert_counts || {};
      opsOverviewList.appendChild(li(
        "Open alerts: " + (counts.total_open || 0)
        + " (critical " + (counts.critical || 0)
        + ", high " + (counts.high || 0) + ")"
      ));
      opsOverviewList.appendChild(li("Open incidents: " + ((overview.open_incidents || []).length)));
      opsOverviewList.appendChild(li("Pending approvals seen in history: " + (overview.pending_approvals || 0)));
      opsOverviewList.appendChild(li("Recent failed agent tasks (collected): " + (overview.recent_failed_tasks || 0)));
      opsOverviewList.appendChild(li("Event integrity: " + (((overview.integrity || {}).ok) ? "chain OK" : "BROKEN")));

      opsHealthList.innerHTML = "";
      ((overview.health && overview.health.services) || []).forEach(function (svc) {
        opsHealthList.appendChild(li(
          svc.name + " — " + svc.state
          + " [" + svc.verification + "/" + svc.check_kind + "]"
          + (svc.latency_ms != null ? " " + svc.latency_ms + "ms" : "")
          + " — " + (svc.detail || "")
        ));
      });

      opsAlertsList.innerHTML = "";
      var alerts = overview.open_alerts || [];
      opsAlertsEmpty.hidden = alerts.length > 0;
      alerts.forEach(function (alert) {
        var item = document.createElement("li");
        var label = document.createElement("span");
        label.textContent = (alert.severity || "?") + " · " + (alert.status || "?") + " — " + (alert.title || "");
        item.appendChild(label);
        var ack = document.createElement("button");
        ack.type = "button";
        ack.textContent = "Acknowledge";
        ack.className = "secondary";
        ack.style.marginLeft = "0.5rem";
        ack.addEventListener("click", function () {
          request("/api/ops/alerts/transition", {
            method: "POST",
            body: { alert_id: alert.alert_id, status: "acknowledged", actor: "console-operator" }
          }).then(function () { loadOpsCentre(filterQ); }).catch(function (err) {
            showOpsError(errorMessage(err));
          });
        });
        var openInc = document.createElement("button");
        openInc.type = "button";
        openInc.textContent = "Open incident";
        openInc.style.marginLeft = "0.35rem";
        openInc.addEventListener("click", function () {
          request("/api/ops/incidents", {
            method: "POST",
            body: { alert_id: alert.alert_id, actor: "console-operator" }
          }).then(function () { loadOpsCentre(filterQ); }).catch(function (err) {
            showOpsError(errorMessage(err));
          });
        });
        item.appendChild(ack);
        item.appendChild(openInc);
        opsAlertsList.appendChild(item);
      });

      opsIncidentsList.innerHTML = "";
      var incidents = overview.open_incidents || [];
      opsIncidentsEmpty.hidden = incidents.length > 0;
      incidents.forEach(function (inc) {
        opsIncidentsList.appendChild(li(
          (inc.severity || "?") + " · " + (inc.status || "?") + " — " + (inc.title || "")
          + " (" + (inc.incident_id || "").slice(0, 8) + "…)"
        ));
      });

      opsTimeline.innerHTML = "";
      (events.events || []).forEach(function (ev) {
        opsTimeline.appendChild(li(
          (ev.at || "") + " · " + (ev.severity || "info")
          + " · " + (ev.component || "") + "/" + (ev.event_type || "")
          + " · " + (ev.outcome || "") + " — " + (ev.summary || "")
          + " [" + (ev.verification || "") + "]"
        ));
      });

      opsCoverage.textContent = coverage.coverage || "";
      var chain = (integrity.event_store || {});
      opsIntegrity.textContent =
        "Integrity: " + (chain.ok ? "OK" : "FAILED")
        + " (" + (chain.events != null ? chain.events + " events" : chain.detail || "") + "). "
        + (integrity.limitation || "");
    }).catch(function (error) {
      showOpsError(errorMessage(error));
    });
  }

  function loadRepair() {
    var remote = document.getElementById("repair-remote");
    var errorBox = document.getElementById("repair-error");
    errorBox.hidden = true;
    request("/api/repair/remote").then(function (body) {
      remote.textContent = (body.state || "UNKNOWN") + " — " + (body.detail || "No detail.");
    }).catch(function (error) {
      errorBox.hidden = false;
      errorBox.textContent = errorMessage(error);
    });
    loadRepairDevice();
  }

  var repairDevice = { id: "", secret: "" };

  function loadRepairDevice() {
    var node = document.getElementById("repair-device-status");
    request("/api/repair/device").then(function (body) {
      var jobs = Array.isArray(body.jobs) ? body.jobs : [];
      var latest = jobs.length ? jobs[jobs.length - 1] : null;
      var evidence = latest
        ? " Latest job " + (latest.lifecycle || "unknown") +
          " on " + (latest.device_id || "unknown device") +
          ", evidence " + (latest.evidence_source || "none") +
          ", collected by " + (latest.collected_by || "nobody yet") + "."
        : " No job has been stored.";
      node.textContent = "Enrolled devices: " + body.device_count +
        ". Pending jobs: " + body.pending_jobs +
        ". Accepted jobs: " + body.accepted_jobs +
        ". Last seen: " + (body.last_seen == null ? "never" : body.last_seen) +
        ". Repair authority is off." + evidence +
        " Results are reported by the endpoint worker, not collected by this page.";
    }).catch(function (error) {
      node.textContent = errorMessage(error);
    });
  }

  document.getElementById("repair-device-enrol").addEventListener("click", function () {
    var errorBox = document.getElementById("repair-error");
    errorBox.hidden = true;
    request("/api/repair/device/enrol", { method: "POST", body: {} }).then(function (body) {
      repairDevice.id = body.device_id || "";
      repairDevice.secret = "";
      document.getElementById("repair-result").textContent =
        "Save this endpoint credential now. It is not shown again and it is not a console login.\n" +
        JSON.stringify({
          device_id: body.device_id,
          tenant_id: body.tenant_id,
          device_secret: body.device_secret,
          mac_key: body.mac_key
        }, null, 2);
      loadRepairDevice();
    }).catch(function (error) {
      errorBox.hidden = false;
      errorBox.textContent = errorMessage(error);
    });
  });

  document.getElementById("repair-device-issue").addEventListener("click", function () {
    var errorBox = document.getElementById("repair-error");
    errorBox.hidden = true;
    if (!repairDevice.id) {
      errorBox.hidden = false;
      errorBox.textContent = "Enrol an endpoint in this page first. Issuing a job does not run the collector here.";
      return;
    }
    request("/api/repair/device/issue", {
      method: "POST",
      body: { device_id: repairDevice.id, procedure_id: "win.storage.space" }
    }).then(function (envelope) {
      document.getElementById("repair-result").textContent =
        "Issued " + envelope.procedure_id + " for " + envelope.device_id +
        ". The endpoint worker collects it. This page did not run the check.";
      loadRepairDevice();
    }).catch(function (error) {
      errorBox.hidden = false;
      errorBox.textContent = errorMessage(error);
    });
  });

  document.getElementById("repair-device-revoke").addEventListener("click", function () {
    var errorBox = document.getElementById("repair-error");
    errorBox.hidden = true;
    if (!repairDevice.id) {
      errorBox.hidden = false;
      errorBox.textContent = "Enrol an endpoint in this page first. Revoking does not run a collector on this computer.";
      return;
    }
    request("/api/repair/device/revoke", { method: "POST", body: { device_id: repairDevice.id } }).then(function () {
      repairDevice.id = "";
      repairDevice.secret = "";
      loadRepairDevice();
    }).catch(function (error) {
      errorBox.hidden = false;
      errorBox.textContent = errorMessage(error);
    });
  });

  document.getElementById("repair-live").addEventListener("click", function () {
    var errorBox = document.getElementById("repair-error");
    errorBox.hidden = true;
    request("/api/repair/live", { method: "POST", body: { procedure_id: "print.diagnose" } }).then(function (result) {
      document.getElementById("repair-result").textContent = JSON.stringify(result, null, 2);
    }).catch(function (error) {
      errorBox.hidden = false;
      errorBox.textContent = errorMessage(error);
    });
  });

  document.getElementById("repair-practise").addEventListener("click", function () {
    var errorBox = document.getElementById("repair-error");
    var resultBox = document.getElementById("repair-result");
    errorBox.hidden = true;
    request("/api/repair/printer/diagnose", { method: "POST", body: { fixture: "printer_spooler_stopped" } }).then(function (diagnosis) {
      return request("/api/repair/printer/request", {
        method: "POST",
        body: { tenant_id: "local-test", device_id: "this-pc", requester: "console-operator" }
      }).then(function (requested) {
        return request("/api/repair/printer/approve", {
          method: "POST",
          body: { tenant_id: "local-test", approval_id: requested.approval_id, approver: "console-reviewer" }
        }).then(function (approved) {
          return request("/api/repair/printer/execute", {
            method: "POST",
            body: {
              tenant_id: "local-test",
              device_id: "this-pc",
              approval_id: requested.approval_id,
              operator: "console-operator",
              fixture: "printer_spooler_stopped"
            }
          }).then(function (executed) {
            resultBox.textContent = JSON.stringify({
              practice: true,
              fixture: "printer_spooler_stopped",
              diagnosis: diagnosis,
              approval: approved,
              execution: executed
            }, null, 2);
          });
        });
      });
    }).catch(function (error) {
      errorBox.hidden = false;
      errorBox.textContent = errorMessage(error);
    });
  });

  document.getElementById("repair-form").addEventListener("submit", function (event) {
    event.preventDefault();
    var errorBox = document.getElementById("repair-error");
    var symptom = document.getElementById("repair-symptom").value.trim();
    var fixture = document.getElementById("repair-fixture").value;
    errorBox.hidden = true;
    var body = { symptom: symptom };
    if (fixture) body.fixture = fixture;
    request("/api/repair/plan", { method: "POST", body: body }).then(function (planned) {
      var ids = planned.procedure_ids || [];
      var first = ids[0];
      if (!first) {
        document.getElementById("repair-result").textContent = JSON.stringify(planned, null, 2);
        return null;
      }
      var executeBody = { procedure_id: first };
      if (fixture) executeBody.fixture = fixture;
      return request("/api/repair/execute", { method: "POST", body: executeBody }).then(function (result) {
        document.getElementById("repair-result").textContent = JSON.stringify({
          plan: planned,
          first_procedure: result
        }, null, 2);
      });
    }).catch(function (error) {
      errorBox.hidden = false;
      errorBox.textContent = errorMessage(error);
    });
  });

  document.getElementById("ops-refresh").addEventListener("click", function () {
    request("/api/ops/refresh", { method: "POST", body: {} }).then(function () {
      loadOpsCentre();
    }).catch(function (error) {
      showOpsError(errorMessage(error));
    });
  });
  document.getElementById("ops-filter-form").addEventListener("submit", function (event) {
    event.preventDefault();
    loadOpsCentre(document.getElementById("ops-filter-q").value.trim());
  });

  var loginForm = document.getElementById("login-form");
  var loginError = document.getElementById("login-error");
  var loginLoading = document.getElementById("login-loading");
  var loginSubmit = document.getElementById("login-submit");
  var logoutButton = document.getElementById("logout-button");

  if (loginForm) {
    loginForm.addEventListener("submit", function (event) {
      event.preventDefault();
      showError(loginError, "");
      if (loginLoading) loginLoading.hidden = false;
      if (loginSubmit) loginSubmit.disabled = true;
      var username = document.getElementById("login-username").value.trim();
      var password = document.getElementById("login-password").value;
      request("/api/auth/login", {
        method: "POST",
        body: { username: username, password: password }
      }).then(function (body) {
        document.getElementById("login-password").value = "";
        showAppShell(body);
        bootConsole();
      }).catch(function (error) {
        showError(loginError, errorMessage(error));
      }).then(function () {
        if (loginLoading) loginLoading.hidden = true;
        if (loginSubmit) loginSubmit.disabled = false;
      });
    });
  }

  if (logoutButton) {
    logoutButton.addEventListener("click", function () {
      request("/api/auth/logout", { method: "POST", body: {} }).catch(function () {}).then(function () {
        showLoginGate(authState);
      });
    });
  }

  function bootConsole() {
    renderChat();
    renderRag();
    var microsoftResult = new URLSearchParams(location.search).get("microsoft");
    var startView = location.hash.replace("#", "");
    if (microsoftResult) startView = "agent";
    showView(startView || "chat");
    loadDocuments().catch(function () {});
    refreshStatus();
  }

  refreshAuth().then(function (body) {
    if (body && body.authenticated) bootConsole();
  });
  window.setInterval(function () {
    if (authState && authState.authenticated) refreshStatus();
  }, 15000);
})();
