(function () {
  "use strict";

  var views = ["chat", "documents", "status"];
  var messages = [];
  var busy = false;
  var ragBusy = false;
  var lastStatus = null;

  var navStatus = document.getElementById("nav-status");
  var chatLog = document.getElementById("chat-log");
  var chatForm = document.getElementById("chat-form");
  var chatInput = document.getElementById("chat-input");
  var chatError = document.getElementById("chat-error");
  var chatLoading = document.getElementById("chat-loading");
  var chatSend = document.getElementById("chat-send");
  var ragForm = document.getElementById("rag-form");
  var ragQuestion = document.getElementById("rag-question");
  var ragCollection = document.getElementById("rag-collection");
  var ragTopK = document.getElementById("rag-top-k");
  var ragError = document.getElementById("rag-error");
  var ragLoading = document.getElementById("rag-loading");
  var ragSend = document.getElementById("rag-send");
  var ragResult = document.getElementById("rag-result");
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
          throw new Error(body && body.error ? body.error : "Request failed (" + response.status + ").");
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
    if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
    document.title = name === "documents" ? "Document Q&A" : name === "status" ? "System Status" : "Chat";
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

  function refreshStatus() {
    return request("/api/status").then(function (body) {
      lastStatus = body;
      applyNavStatus(body, false);
      if (!document.getElementById("status-view").hidden) renderStatus();
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
      .concat(addRow("Model id", body.model_id || "Not configured"))
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
      var chunk = source && source.chunk != null ? "Chunk " + source.chunk : "Chunk unknown";
      var score = source && typeof source.score === "number" ? "Score " + source.score : "Score unavailable";
      item.appendChild(el("span", null, chunk + " · " + score));
      list.appendChild(item);
    });
    return list;
  }

  function renderRag(body) {
    ragResult.hidden = false;
    ragResult.textContent = "";
    var answered = body.status === "answered";
    ragResult.appendChild(el("div", "badge " + (answered ? "badge-answered" : "badge-abstained"), answered ? "Answered" : "Abstained"));
    ragResult.appendChild(el("p", "answer", typeof body.answer === "string" ? body.answer : ""));
    var notes = [];
    if (body.collection) notes.push("Collection " + body.collection + ".");
    if (body.model) notes.push("Model " + body.model + ".");
    var retrieval = retrievalText(body.retrieval);
    if (retrieval) notes.push(retrieval);
    if (notes.length) ragResult.appendChild(el("p", "meta", notes.join(" ")));
    ragResult.appendChild(el("h2", null, "Sources"));
    ragResult.appendChild(renderSources(body.sources));
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

  chatForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (busy) return;
    var content = chatInput.value.trim();
    if (!content) return;
    messages.push({ role: "user", content: content });
    chatInput.value = "";
    busy = true;
    chatSend.disabled = true;
    chatLoading.hidden = false;
    showError(chatError, "");
    renderChat();
    request("/api/chat", { method: "POST", body: { messages: messages } }).then(function (body) {
      var contentText = body && body.choices && body.choices[0] && body.choices[0].message
        ? body.choices[0].message.content
        : "";
      if (typeof contentText !== "string" || !contentText.trim()) {
        throw new Error("The model returned an empty reply.");
      }
      messages.push({ role: "assistant", content: contentText.trim() });
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
    var body = { question: question, top_k: Number(ragTopK.value) };
    if (collection) body.collection = collection;
    ragBusy = true;
    ragSend.disabled = true;
    ragLoading.hidden = false;
    showError(ragError, "");
    request("/api/rag", { method: "POST", body: body }).then(function (result) {
      renderRag(result);
    }).catch(function (error) {
      ragResult.hidden = true;
      showError(ragError, errorMessage(error));
    }).finally(function () {
      ragBusy = false;
      ragSend.disabled = false;
      ragLoading.hidden = true;
      refreshStatus();
    });
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
          .then(function () {
            uploadStatus.textContent = "Deleted " + documentInfo.filename + ".";
            return loadDocuments();
          })
          .catch(function (error) { showError(uploadError, errorMessage(error)); });
      });
      item.appendChild(remove);
      documentList.appendChild(item);
    });
  }

  function loadDocuments() {
    var collection = uploadCollection.value.trim();
    if (!/^[a-z0-9][a-z0-9_-]{0,39}$/.test(collection)) {
      showError(uploadError, "Use lowercase letters, numbers, hyphens or underscores for the collection.");
      return Promise.reject(new Error("Invalid collection name"));
    }
    return request("/api/documents?collection=" + encodeURIComponent(collection)).then(function (body) {
      renderDocumentList(body.documents || [], collection);
      ragCollection.value = collection;
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
        uploadStatus.textContent = "Saved " + body.document.filename + " to persistent collection " + collection + ".";
        uploadFile.value = "";
        ragCollection.value = collection;
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
    loadDocuments().catch(function (error) {
      if (error && error.message !== "Invalid collection name") showError(uploadError, errorMessage(error));
    });
  });

  document.getElementById("status-refresh").addEventListener("click", refreshStatus);

  renderChat();
  showView(location.hash.replace("#", "") || "chat");
  loadDocuments().catch(function () {});
  refreshStatus();
  window.setInterval(refreshStatus, 15000);
})();
