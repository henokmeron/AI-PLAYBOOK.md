(function () {
  "use strict";

  var views = ["chat", "documents", "agent", "status"];
  var messages = [];
  var ragTurns = [];
  var busy = false;
  var ragBusy = false;
  var lastStatus = null;
  var catalogModels = [];
  var selectedModelId = "";
  var MAX_RAG_HISTORY_MESSAGES = 12;

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
    return fetch(path, {
      method: options && options.method ? options.method : "GET",
      headers: options && options.body ? { "Content-Type": "application/json", "Accept": "application/json" } : { "Accept": "application/json" },
      body: options && options.body ? JSON.stringify(options.body) : undefined,
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
        if (!response.ok) {
          var message = body && body.error ? body.error : "Request failed (" + response.status + ").";
          if (body && typeof body.error_id === "string") message += " (error id " + body.error_id + ")";
          throw new Error(message);
        }
        return body;
      });
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
    document.title = name === "documents" ? "Document Q&A" : name === "agent" ? "Agent" : name === "status" ? "System Status" : "Chat";
    if (name === "agent") loadConnectors();
    if (name === "status") renderStatus();
  }

  function statusLabel(connection) {
    if (connection === "ready") return "Gateway ready";
    if (connection === "degraded") return "Model upstream unavailable";
    if (connection === "key_missing") return "API key not configured";
    if (connection === "model_missing") return "Model id not configured";
    if (connection === "unreachable") return "Gateway unreachable";
    return "Status unavailable";
  }

  function applyNavStatus(body, failed) {
    navStatus.className = "nav-status";
    if (failed) {
      navStatus.textContent = "Status check failed";
      navStatus.classList.add("is-error");
      return;
    }
    var connection = body && body.connection ? body.connection : "unreachable";
    navStatus.textContent = statusLabel(connection);
    navStatus.classList.add("is-" + connection);
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
    return request("/api/status").then(function (body) {
      lastStatus = body;
      if (!selectedModelId && body && body.model_id) selectedModelId = body.model_id;
      applyNavStatus(body, false);
      if (!document.getElementById("status-view").hidden) renderStatus();
      return refreshModels();
    }).catch(function () {
      lastStatus = null;
      applyNavStatus(null, true);
      if (!document.getElementById("status-view").hidden) {
        statusPanel.textContent = "The status check failed. Reload the page if this console just restarted.";
      }
    });
  }

  function addRow(label, value) {
    return [el("dt", null, label), el("dd", null, value)];
  }

  function renderStatus() {
    statusPanel.textContent = "";
    if (!lastStatus) {
      statusPanel.textContent = "Checking the gateway…";
      return;
    }
    var body = lastStatus;
    var list = el("dl", "status-list");
    var rows = []
      .concat(addRow("Connection", statusLabel(body.connection)))
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
    if (body.health && typeof body.health.model_count === "number") {
      rows = rows.concat(addRow("Models reported", String(body.health.model_count)));
    }
    rows.forEach(function (node) { list.appendChild(node); });
    statusPanel.appendChild(list);
    statusPanel.appendChild(el("p", "meta", body.detail || ""));
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
  var agentError = document.getElementById("agent-error");
  var agentLog = document.getElementById("agent-log");
  var agentSend = document.getElementById("agent-send");
  var agentLoading = document.getElementById("agent-loading");
  var agentApproval = document.getElementById("agent-approval");
  var agentApprovalText = document.getElementById("agent-approval-text");
  var agentApprovalTarget = document.getElementById("agent-approval-target");
  var agentApprovalArgs = document.getElementById("agent-approval-args");
  var agentExecution = document.getElementById("agent-execution");
  var agentRecord = document.getElementById("agent-record");
  var agentInfo = document.getElementById("agent-info");
  var agentInfoText = document.getElementById("agent-info-text");
  var agentInfoInput = document.getElementById("agent-info-input");
  var agentCancel = document.getElementById("agent-cancel");
  var connectorList = document.getElementById("connector-list");
  var agentTaskId = "";
  var agentCallId = "";
  var executionLabels = {
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

  function renderAgent(view) {
    agentLog.textContent = "";
    agentRecord.textContent = "";
    if (!view) {
      agentExecution.textContent = "";
      agentLog.appendChild(el("p", "empty", "Run a task to see what the agent did."));
      agentApproval.hidden = true;
      agentInfo.hidden = true;
      agentCancel.hidden = true;
      return;
    }
    var execution = view.execution || view.state;
    var label = executionLabels[execution] || execution;
    var states = (view.states || []).map(function (item) {
      return executionLabels[item] || item;
    });
    agentExecution.textContent = states.length
      ? "Execution: " + label + ". Recorded states: " + states.join(" → ")
      : "Execution: " + label;
    var record = view.record || {};
    if (record.objective) agentRecord.appendChild(el("p", null, "Objective: " + record.objective));
    (record.plan || []).forEach(function (step) {
      agentRecord.appendChild(el("p", "meta", "Plan: " + step));
    });
    (record.tool_calls || []).forEach(function (call) {
      agentRecord.appendChild(el("p", "meta", "Tool: " + (call.tool || "unknown")));
    });
    if (record.outcome) agentRecord.appendChild(el("p", "meta", "Outcome: " + record.outcome));
    var headingText = view.answer || view.failure || label;
    if (execution === "completed") headingText = view.answer || "Completed.";
    if (execution === "escalated") headingText = view.answer || "Escalated.";
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
    agentCancel.hidden = execution !== "awaiting_approval" && execution !== "awaiting_information";
    if (pending) {
      agentTaskId = view.task_id;
      agentCallId = pending.call_id || "";
      agentApprovalText.textContent = pending.reason || "This action needs approval.";
      agentApprovalTarget.textContent = "Tool " + pending.tool + ", call " + pending.call_id;
      agentApprovalArgs.textContent = JSON.stringify(pending.arguments || {}, null, 2);
    } else {
      agentCallId = "";
    }
    if (execution === "awaiting_information") {
      agentTaskId = view.task_id;
      agentInfoText.textContent = view.pending_question || "The agent needs more information.";
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
    }).catch(function (error) {
      showError(agentError, errorMessage(error));
    });
  }

  agentForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var task = agentTask.value.trim();
    if (!task) return;
    agentSend.disabled = true;
    agentLoading.hidden = false;
    showError(agentError, "");
    request("/api/agent", { method: "POST", body: { task: task } }).then(function (result) {
      agentTaskId = result.task_id || "";
      renderAgent(result);
    }).catch(function (error) {
      showError(agentError, errorMessage(error));
    }).then(function () {
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
    }).catch(function (error) {
      showError(agentError, errorMessage(error));
    });
  });
  renderAgent(null);

  document.getElementById("status-refresh").addEventListener("click", refreshStatus);

  renderChat();
  renderRag();
  var microsoftResult = new URLSearchParams(location.search).get("microsoft");
  var startView = location.hash.replace("#", "");
  if (microsoftResult) startView = "agent";
  showView(startView || "chat");
  loadDocuments().catch(function () {});
  refreshStatus();
  window.setInterval(refreshStatus, 15000);
})();
