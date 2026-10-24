/* Read-only view of the stored /api/devices payload.
   A device is healthy only when all nine checks are present, ok is true,
   the evidence source is live_windows, and the summary has no failure status.
   A missing category stays not reported. It is never marked ok or healthy.
*/
(function (root) {
  "use strict";

  var MONITOR_CHECKS = [
    { id: "win.storage.space", label: "Disk" },
    { id: "win.services.inspect", label: "Services" },
    { id: "win.update.inspect", label: "Windows updates" },
    { id: "hw.devices.inventory", label: "Device inventory" },
    { id: "print.diagnose", label: "Printers" },
    { id: "net.diagnose", label: "Network" },
    { id: "win.events.recurring", label: "Events" },
    { id: "win.startup.inspect", label: "Startup" },
    { id: "hw.identity.inspect", label: "Hardware specs" }
  ];

  var FAILURE_STATUSES = {
    unavailable: true,
    unsupported: true,
    "permission-denied": true,
    failed: true,
    failure: true,
    error: true,
    denied: true
  };

  var HISTORY_KEYS = ["history", "reports", "report_history", "disk_history"];

  function finiteNumber(value) {
    return typeof value === "number" && isFinite(value);
  }

  function visibleText(value) {
    var text = String(value == null ? "" : value);
    text = text.replace(/[\u0000-\u001f\u007f]/g, " ");
    text = text.replace(/\bbearer\s+\S+/gi, "bearer [redacted]");
    text = text.replace(
      /\b(secret_hash|device_secret|enrolment_code|enrollment_code|api_key|authorization|password|secret|token)\b\s*[:=]\s*\S+/gi,
      "$1=[redacted]"
    );
    return text;
  }

  function clip(value) {
    var text = visibleText(value).replace(/\s+/g, " ").trim();
    if (text.length <= 400) return text;
    return text.slice(0, 399) + "…";
  }

  function formatUnix(seconds) {
    if (!finiteNumber(seconds) || seconds <= 0) return "";
    var date = new Date(seconds * 1000);
    if (isNaN(date.getTime())) return "";
    return date.toLocaleString();
  }

  function formatDuration(seconds) {
    if (!finiteNumber(seconds)) return "";
    var sign = seconds < 0 ? "-" : "";
    var whole = Math.abs(Math.floor(seconds));
    var days = Math.floor(whole / 86400);
    var hours = Math.floor((whole % 86400) / 3600);
    var minutes = Math.floor((whole % 3600) / 60);
    if (days > 0) return sign + days + "d " + hours + "h";
    if (hours > 0) return sign + hours + "h " + minutes + "m";
    return sign + minutes + "m";
  }

  function reportOf(device) {
    if (!device || typeof device !== "object") return null;
    var report = device.report;
    if (!report || typeof report !== "object" || Array.isArray(report)) return null;
    return report;
  }

  function storedChecks(device) {
    var report = reportOf(device);
    if (!report || !Array.isArray(report.checks)) return [];
    return report.checks.filter(function (check) {
      return check && typeof check === "object";
    });
  }

  function findCheck(device, procedureId) {
    var checks = storedChecks(device);
    for (var i = 0; i < checks.length; i++) {
      if (checks[i].procedure_id === procedureId) return checks[i];
    }
    return null;
  }

  function failureStatusInSummary(summary) {
    var text = typeof summary === "string" ? summary : "";
    var matcher = /(?:^|[\s;])status=([a-z0-9-]+)/gi;
    var match;
    while ((match = matcher.exec(text))) {
      var status = match[1].toLowerCase();
      if (FAILURE_STATUSES[status]) return status;
    }
    return "";
  }

  function classifyCheck(check) {
    if (!check || typeof check !== "object" || typeof check.procedure_id !== "string" || !check.procedure_id) {
      return { state: "not_reported", summary: "" };
    }
    var summary = typeof check.summary === "string" ? check.summary : "";
    var failure = failureStatusInSummary(summary);
    if (check.ok === false || failure || check.evidence_source === "unavailable") {
      return { state: "failed", summary: summary, failureStatus: failure };
    }
    if (check.ok === true && check.evidence_source === "live_windows") {
      return { state: "reported", summary: summary, failureStatus: "" };
    }
    return { state: "unknown", summary: summary, failureStatus: "" };
  }

  function checksForDevice(device) {
    return MONITOR_CHECKS.map(function (spec) {
      var found = findCheck(device, spec.id);
      if (!found) {
        var missing = "Not reported. This check was not in the stored report.";
        if (spec.id === "win.update.inspect") {
          missing += " Update events only, not proof of full patch compliance.";
        }
        return { id: spec.id, label: spec.label, state: "not_reported", summary: missing };
      }
      var classified = classifyCheck(found);
      var summary = classified.summary || "No summary was stored.";
      if (spec.id === "win.update.inspect") {
        summary += " Update events only, not proof of full patch compliance.";
      }
      if (classified.state === "unknown") {
        summary = "The check is stored, but it is not marked passed or failed. " + summary;
      }
      return {
        id: spec.id,
        label: spec.label,
        state: classified.state,
        summary: clip(summary)
      };
    });
  }

  function overallHealth(device, rows) {
    if (!reportOf(device)) {
      return { state: "unknown", reason: "No check-in is stored." };
    }
    var failed = 0;
    var passed = 0;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].state === "failed") failed += 1;
      if (rows[i].state === "reported") passed += 1;
    }
    if (failed > 0) {
      return {
        state: "degraded",
        reason: failed + " of the nine checks failed."
      };
    }
    if (passed === rows.length && rows.length === MONITOR_CHECKS.length) {
      return {
        state: "healthy",
        reason: "All nine checks are stored and none have ok set to false."
      };
    }
    return {
      state: "unknown",
      reason: "The stored check-in does not include a passing result for every one of the nine checks. Missing checks are not healthy."
    };
  }

  function indicator(id, label, state, summary) {
    return { id: id, label: label, state: state, summary: clip(summary) };
  }

  function fieldValue(summary, key) {
    var matcher = new RegExp("(?:^|[\\s;])" + key + "=([^;]+)", "i");
    var match = String(summary || "").match(matcher);
    return match ? match[1].trim() : "";
  }

  function checksWhere(device, predicate) {
    return storedChecks(device).filter(predicate);
  }

  function fromMatches(id, label, matches, absentCopy) {
    if (!matches.length) return indicator(id, label, "not_reported", absentCopy);
    var failed = matches.some(function (check) {
      return classifyCheck(check).state === "failed";
    });
    var text = matches.map(function (check) {
      return typeof check.summary === "string" && check.summary ? check.summary : check.procedure_id;
    }).join(" ");
    return indicator(id, label, failed ? "failed" : "reported", text);
  }

  function summaryHas(summary, pattern) {
    return pattern.test(typeof summary === "string" ? summary : "");
  }

  function addDiskPoint(points, seen, free, total, at) {
    if (!finiteNumber(free) || !finiteNumber(total) || !finiteNumber(at) || at <= 0) return;
    var key = String(at) + ":" + String(free) + ":" + String(total);
    if (seen[key]) return;
    seen[key] = true;
    points.push({ free: free, total: total, at: at });
  }

  function consumeDiskRecord(points, seen, record) {
    if (!record || typeof record !== "object") return;
    var nested = record.report && typeof record.report === "object" ? record.report : null;
    var source = nested || record;
    var at = source.collected_at_unix;
    if (!finiteNumber(at)) at = record.collected_at_unix;
    addDiskPoint(points, seen, source.disk_free_bytes, source.disk_total_bytes, at);
  }

  function diskMeasurements(device) {
    var points = [];
    var seen = {};
    var report = reportOf(device);
    if (report) consumeDiskRecord(points, seen, report);
    HISTORY_KEYS.forEach(function (key) {
      var lists = [];
      if (device && Array.isArray(device[key])) lists.push(device[key]);
      if (report && Array.isArray(report[key])) lists.push(report[key]);
      lists.forEach(function (list) {
        list.forEach(function (item) { consumeDiskRecord(points, seen, item); });
      });
    });
    points.sort(function (a, b) { return a.at - b.at; });
    return points;
  }

  function diskTrendIndicator(device) {
    var points = diskMeasurements(device);
    if (points.length < 2 || points[points.length - 1].at <= points[0].at) {
      var note = "Not reported. A single stored snapshot has no consumption rate.";
      if (points.length === 1) {
        note += " Stored free bytes " + points[0].free + " of " + points[0].total + ".";
      } else {
        var report = reportOf(device);
        if (report && finiteNumber(report.disk_free_bytes) && finiteNumber(report.disk_total_bytes)) {
          note += " Free bytes are stored (" + report.disk_free_bytes + " of " + report.disk_total_bytes + ") without a second measurement.";
        }
      }
      return indicator("disk-trend", "Disk space trending", "not_reported", note);
    }
    var older = points[0];
    var newer = points[points.length - 1];
    var delta = newer.free - older.free;
    var change = "Free space was unchanged";
    if (delta < 0) change = "Free space fell by " + Math.abs(delta) + " bytes";
    if (delta > 0) change = "Free space rose by " + delta + " bytes";
    var start = formatUnix(older.at) || "the earlier measurement";
    var end = formatUnix(newer.at) || "the later measurement";
    return indicator(
      "disk-trend",
      "Disk space trending",
      "reported",
      change + " between " + start + " and " + end + " (" + points.length + " stored measurements). This is the stored difference, not a forecast."
    );
  }

  function lastSeenIndicator(device) {
    var stamp = device && finiteNumber(device.last_report_at) && device.last_report_at > 0 ? device.last_report_at : 0;
    var report = reportOf(device);
    if (!stamp && report && finiteNumber(report.collected_at_unix) && report.collected_at_unix > 0) {
      stamp = report.collected_at_unix;
    }
    if (!stamp) {
      return indicator(
        "last-seen",
        "Last seen",
        "not_reported",
        "Not reported. No check-in time is stored. This is not a live remote session."
      );
    }
    var parts = ["Last seen " + (formatUnix(stamp) || "at the stored check-in time") + "."];
    if (device && finiteNumber(device.evidence_age_seconds)) {
      parts.push("Stored age " + formatDuration(device.evidence_age_seconds) + ".");
    }
    if (device && device.evidence_stale === true) parts.push("The console marks this check-in stale.");
    parts.push("This is the stored check-in, not a live remote session.");
    return indicator("last-seen", "Last seen", "reported", parts.join(" "));
  }

  function networkIndicator(device) {
    var check = findCheck(device, "net.diagnose");
    if (!check) {
      return indicator(
        "network",
        "Network connection and quality",
        "not_reported",
        "Not reported. No net.diagnose check is stored."
      );
    }
    var classified = classifyCheck(check);
    var summary = classified.summary || "No summary was stored.";
    var quality = /\b(signal|latency|packet\s+loss|jitter|rssi|quality)\b/i.test(summary)
      ? " The stored summary includes a quality reading."
      : " Quality (signal, loss, or latency) is not in this stored check.";
    var state = classified.state === "failed" ? "failed" : "reported";
    if (state !== "failed" && /(?:^|[\s;])(?:gateway_ok|dns_localhost_ok)=false\b/i.test(summary)) {
      state = "finding";
    }
    return indicator("network", "Network connection and quality", state, "Connection: " + summary + "." + quality);
  }

  function uptimeIndicator(device) {
    var report = reportOf(device);
    var startup = findCheck(device, "win.startup.inspect");
    var lastBoot = startup ? fieldValue(startup.summary, "last_boot") : "";
    var boot = report && finiteNumber(report.boot_time_unix) ? report.boot_time_unix : null;
    var collected = report && finiteNumber(report.collected_at_unix) ? report.collected_at_unix : null;
    if (boot != null && collected != null && collected >= boot) {
      var text = "Uptime at check-in was " + formatDuration(collected - boot) +
        ", from stored boot time " + (formatUnix(boot) || String(boot)) +
        " to collected time " + (formatUnix(collected) || String(collected)) +
        ". This is not a live uptime reading.";
      if (lastBoot) text += " Startup check last_boot=" + lastBoot + ".";
      return indicator("uptime", "Uptime", "reported", text);
    }
    if (lastBoot) {
      return indicator(
        "uptime",
        "Uptime",
        "reported",
        "Stored startup check last_boot=" + lastBoot + ". A duration was not calculated because boot time and collected time were not both usable. This is not a live uptime reading."
      );
    }
    return indicator("uptime", "Uptime", "not_reported", "Not reported. The stored check-in has no usable boot time.");
  }

  function updateIndicator(device) {
    var check = findCheck(device, "win.update.inspect");
    var disclaimer = " This is an update-event summary, not proof of full patch compliance.";
    if (!check) {
      return indicator(
        "updates",
        "Update events",
        "not_reported",
        "Not reported. No win.update.inspect check is stored." + disclaimer
      );
    }
    var classified = classifyCheck(check);
    var state = classified.state === "failed" ? "failed" : (classified.state === "reported" ? "reported" : "unknown");
    return indicator(
      "updates",
      "Update events",
      state,
      (classified.summary || "No summary was stored.") + disclaimer
    );
  }

  function rebootIndicator(device) {
    var check = findCheck(device, "win.reboot.pending");
    if (!check) {
      return indicator(
        "reboot",
        "Pending reboot",
        "not_reported",
        "Not reported. win.reboot.pending is not in the stored report. A missing check is not the same as no reboot pending."
      );
    }
    var classified = classifyCheck(check);
    var summary = classified.summary || "No summary was stored.";
    var state = classified.state === "failed" ? "failed" : (classified.state === "reported" ? "reported" : "unknown");
    if (state === "reported" && /(?:^|[\s;])pending=true\b/i.test(summary)) state = "finding";
    return indicator("reboot", "Pending reboot", state, "Stored win.reboot.pending check: " + summary);
  }

  function textIndicators(device) {
    return [
      fromMatches(
        "antivirus",
        "Antivirus / malware protection",
        checksWhere(device, function (check) {
          return summaryHas(check.summary, /\b(antivirus|anti-virus|malware)\b/i);
        }),
        "Not reported. The stored report does not contain antivirus or malware protection."
      ),
      fromMatches(
        "sync",
        "Device syncing",
        checksWhere(device, function (check) {
          return summaryHas(check.summary, /\b(device\s+sync(?:ing)?|sync\s+status|syncing)\b/i);
        }),
        "Not reported. The stored report does not contain device sync status."
      ),
      fromMatches(
        "downloads",
        "Downloading activity",
        checksWhere(device, function (check) {
          return summaryHas(check.summary, /\b(downloading|download\s+activity|bytes\s+downloaded)\b/i);
        }),
        "Not reported. The stored report does not contain downloading activity."
      ),
      fromMatches(
        "posture",
        "Security posture",
        checksWhere(device, function (check) {
          return summaryHas(check.summary, /\bsecurity\s+posture\b/i);
        }),
        "Not reported. The stored report does not contain a security posture."
      ),
      fromMatches(
        "logins",
        "Failed login attempts and security events",
        checksWhere(device, function (check) {
          return summaryHas(check.summary, /failed\s+log(?:in|on)s?|security\s+events?/i);
        }),
        "Not reported. The stored report does not mention failed logins or security events. A generic event check is not treated as failed logins."
      ),
      fromMatches(
        "backup",
        "Backup success or failure",
        checksWhere(device, function (check) {
          var summary = typeof check.summary === "string" ? check.summary : "";
          var procedureId = typeof check.procedure_id === "string" ? check.procedure_id : "";
          var mentionsBackup = /\bbackup\b/i.test(summary) || /backup/i.test(procedureId);
          if (!mentionsBackup) return false;
          return /\b(success|succeeded|successful|failed|failure|complete|completed)\b/i.test(summary) ||
            /(?:^|[\s;])status=/i.test(summary) ||
            /\bbackup\s*=\s*ok\b/i.test(summary);
        }),
        "Not reported. The stored report does not contain backup status."
      ),
      fromMatches(
        "certificates",
        "Certificate expiration dates",
        checksWhere(device, function (check) {
          var summary = typeof check.summary === "string" ? check.summary : "";
          var hasCert = /\bcertificates?\b/i.test(summary) || /\bcert\b/i.test(summary);
          var hasExpiry = /\bexpir(?:e|es|ed|y|ation|ing)?\b/i.test(summary) ||
            /\bnot_after\b/i.test(summary) || /\bnotafter\b/i.test(summary);
          return hasCert && hasExpiry;
        }),
        "Not reported. The stored report does not contain certificate expiry."
      ),
      fromMatches(
        "thermal",
        "Thermal or battery health",
        checksWhere(device, function (check) {
          return summaryHas(check.summary, /\b(temperature|thermal|battery\s+health|battery_health)\b/i);
        }),
        "Not reported. The stored report does not contain temperature or battery health."
      )
    ];
  }

  function indicatorsFor(device) {
    var text = textIndicators(device);
    return [
      text[0],
      text[1],
      lastSeenIndicator(device),
      networkIndicator(device),
      text[2],
      uptimeIndicator(device),
      updateIndicator(device),
      text[3],
      diskTrendIndicator(device),
      text[4],
      text[5],
      rebootIndicator(device),
      text[6],
      text[7]
    ];
  }

  function monitorDevice(device) {
    var rows = checksForDevice(device);
    var failedCount = rows.filter(function (row) { return row.state === "failed"; }).length;
    var report = reportOf(device);
    var lastCheckIn = formatUnix(device && device.last_report_at) ||
      (report ? formatUnix(report.collected_at_unix) : "") ||
      "No check-in";
    var enrolmentStatus = "";
    if (device && (device.status === "enrolled" || device.status === "revoked")) enrolmentStatus = device.status;
    var fixtureLabel = "";
    if (device && typeof device.fixture_label === "string" && device.fixture_label) {
      fixtureLabel = clip(device.fixture_label);
    }
    return {
      displayName: clip(device && device.display_name ? device.display_name : "Unnamed device"),
      deviceId: clip(device && device.device_id ? device.device_id : "Not stored"),
      enrolmentStatus: enrolmentStatus,
      fixtureLabel: fixtureLabel,
      lastCheckIn: lastCheckIn,
      failedCount: failedCount,
      health: overallHealth(device, rows),
      checks: rows,
      indicators: indicatorsFor(device)
    };
  }

  var api = {
    MONITOR_CHECKS: MONITOR_CHECKS,
    classifyCheck: classifyCheck,
    failureStatusInSummary: failureStatusInSummary,
    checksForDevice: checksForDevice,
    overallHealth: overallHealth,
    indicatorsFor: indicatorsFor,
    diskMeasurements: diskMeasurements,
    monitorDevice: monitorDevice
  };
  root.DeviceMonitor = api;

  if (!root.document || typeof root.document.getElementById !== "function") return;

  var selectedKey = "";

  function el(tag, className, text) {
    var node = root.document.createElement(tag);
    if (className) node.className = className;
    if (text != null && text !== "") node.textContent = text;
    return node;
  }

  function badgeLabel(state) {
    if (state === "healthy") return "Healthy";
    if (state === "degraded") return "Degraded";
    if (state === "failed") return "Failed";
    if (state === "finding") return "Finding";
    if (state === "reported") return "Reported";
    if (state === "not_reported") return "Not reported";
    return "Unknown";
  }

  function badge(state) {
    return el("span", "badge badge-" + state, badgeLabel(state));
  }

  function setStatus(message) {
    var node = root.document.getElementById("monitor-status");
    if (node) node.textContent = message;
  }

  function showBody(visible) {
    var body = root.document.getElementById("monitor-body");
    if (body) body.hidden = !visible;
  }

  function paintCounts(models) {
    var host = root.document.getElementById("fleet-counts");
    if (!host) return;
    host.textContent = "";
    var counts = { devices: models.length, healthy: 0, degraded: 0, unknown: 0 };
    models.forEach(function (model) {
      if (counts[model.health.state] != null && model.health.state !== "devices") counts[model.health.state] += 1;
    });
    [
      ["Devices", counts.devices],
      ["Healthy", counts.healthy],
      ["Degraded", counts.degraded],
      ["Unknown", counts.unknown]
    ].forEach(function (pair) {
      var item = el("div", "count");
      item.appendChild(el("span", null, pair[0]));
      item.appendChild(el("strong", null, String(pair[1])));
      host.appendChild(item);
    });
  }

  function paintList(models) {
    var list = root.document.getElementById("device-list");
    if (!list) return;
    list.textContent = "";
    models.forEach(function (model) {
      var button = el("button", "device-row" + (model.key === selectedKey ? " is-selected" : ""));
      button.type = "button";
      button.setAttribute("aria-pressed", model.key === selectedKey ? "true" : "false");
      button.appendChild(badge(model.health.state));
      button.appendChild(el("strong", "device-name", model.displayName));
      button.appendChild(el("span", "meta", model.deviceId));
      button.appendChild(el("span", "meta", "Last check-in: " + model.lastCheckIn));
      var failed = el(
        "span",
        "meta failed-count" + (model.failedCount > 0 ? " is-failed" : ""),
        model.failedCount + (model.failedCount === 1 ? " failed check" : " failed checks")
      );
      button.appendChild(failed);
      button.addEventListener("click", function () {
        selectedKey = model.key;
        paint(models);
      });
      list.appendChild(button);
    });
  }

  function paintCards(host, rows, kind) {
    host.textContent = "";
    var grid = el("div", "cards");
    rows.forEach(function (row) {
      var card = el("article", kind + " is-" + row.state);
      var title = el("h3", null, row.label);
      card.appendChild(badge(row.state));
      card.appendChild(title);
      if (row.id && kind === "check") card.appendChild(el("p", "meta", row.id));
      card.appendChild(el("p", null, row.summary));
      grid.appendChild(card);
    });
    host.appendChild(grid);
  }

  function paintDetail(model) {
    var host = root.document.getElementById("device-detail");
    if (!host) return;
    host.textContent = "";
    if (!model) {
      host.appendChild(el("p", "meta", "Select a device."));
      return;
    }
    var head = el("div", "detail-head is-" + model.health.state);
    head.appendChild(badge(model.health.state));
    head.appendChild(el("h3", null, model.displayName));
    head.appendChild(el("p", "meta", "Device id: " + model.deviceId));
    head.appendChild(el("p", null, "Last check-in: " + model.lastCheckIn));
    head.appendChild(el(
      "p",
      model.failedCount > 0 ? "failed-count is-failed" : "meta",
      model.failedCount + (model.failedCount === 1 ? " failed check" : " failed checks")
    ));
    if (model.enrolmentStatus) head.appendChild(el("p", "meta", "Enrolment status: " + model.enrolmentStatus));
    if (model.fixtureLabel) head.appendChild(el("p", "meta", "Fixture label: " + model.fixtureLabel));
    head.appendChild(el("p", null, model.health.reason));
    host.appendChild(head);
    host.appendChild(el("h3", "group-title", "Nine checks"));
    var checks = el("div");
    paintCards(checks, model.checks, "check");
    host.appendChild(checks);
    host.appendChild(el("h3", "group-title", "Health indicators"));
    var indicators = el("div");
    paintCards(indicators, model.indicators, "indicator");
    host.appendChild(indicators);
  }

  function paint(models) {
    paintCounts(models);
    paintList(models);
    var selected = null;
    for (var i = 0; i < models.length; i++) {
      if (models[i].key === selectedKey) selected = models[i];
    }
    paintDetail(selected);
  }

  function renderDevices(devices) {
    var models = devices.map(function (device, index) {
      var model = api.monitorDevice(device);
      var id = device && typeof device.device_id === "string" ? device.device_id : "row";
      model.key = id + ":" + index;
      return model;
    });
    var stillThere = models.some(function (model) { return model.key === selectedKey; });
    if (!stillThere) selectedKey = models.length ? models[0].key : "";
    showBody(true);
    paint(models);
    setStatus(models.length
      ? models.length + (models.length === 1 ? " stored device." : " stored devices.")
      : "No enrolled devices are stored.");
    if (!models.length) {
      var detail = root.document.getElementById("device-detail");
      if (detail) {
        detail.textContent = "";
        detail.appendChild(el("p", "meta", "No enrolled devices are stored."));
      }
    }
  }

  function loadDevices() {
    if (root.location && root.location.protocol === "file:") {
      showBody(false);
      setStatus("This page reads /api/devices from the console. Opened as a file, the list stays empty. The live console shows this page only after feature/device-monitor-dashboard is merged, and this work does not merge it.");
      return;
    }
    var button = root.document.getElementById("refresh-devices");
    if (button) button.disabled = true;
    setStatus("Reading stored devices…");
    root.fetch("/api/devices", {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin"
    }).then(function (response) {
      return response.text().then(function (text) {
        var body = {};
        if (text) {
          try {
            body = JSON.parse(text);
          } catch (parseError) {
            throw new Error("The console returned an unreadable device list.");
          }
        }
        if (!response.ok) {
          var message = body && typeof body.error === "string" ? body.error : "The device list could not be read.";
          throw new Error(message);
        }
        return body;
      });
    }).then(function (body) {
      if (!body || !Array.isArray(body.devices)) {
        throw new Error("The console response did not include a device list.");
      }
      renderDevices(body.devices);
    }).catch(function (error) {
      showBody(false);
      setStatus(clip(error && error.message ? error.message : "The device list could not be read."));
    }).then(function () {
      if (button) button.disabled = false;
    });
  }

  function init() {
    var button = root.document.getElementById("refresh-devices");
    if (button) button.addEventListener("click", loadDevices);
    loadDevices();
  }

  if (root.document.readyState === "loading") {
    root.document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
}(typeof window !== "undefined" ? window : globalThis));
