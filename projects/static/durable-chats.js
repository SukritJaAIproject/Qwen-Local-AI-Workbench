/* Keep chat history on the local server, independent of browser storage. */
(function () {
  "use strict";
  var fetchOriginal = window.fetch, running = null, signatures = Object.create(null), revisions = Object.create(null);
  var state = {saved: false, failed: false, conflicts: 0, restored: 0}, badge = null, protectedChats = Object.create(null);
  try { revisions = JSON.parse(localStorage.getItem("qwen-history-ack-v1") || "{}"); } catch (e) {}
  if (!revisions || typeof revisions !== "object" || Array.isArray(revisions)) revisions = Object.create(null);
  var requestedId = "";
  try { requestedId = (window.top.location.hash.match(/^#\/chat\/([A-Za-z0-9_-]+)$/) || [])[1] || ""; } catch (e) {}
  function thai() { return window.qwenEnhance && window.qwenEnhance.lang() === "th"; }
  function label(en, th) { return thai() ? th : en; }
  function api(path, data) {
    var options = data === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)};
    return fetchOriginal.call(window, "/_qwen/chats/" + path, options).then(function (response) {
      if (!response.ok) throw new Error("History request failed");
      return response.json();
    });
  }
  function openDB() {
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open("LlamaUi");
      request.onupgradeneeded = function () { request.transaction.abort(); };
      request.onerror = function () { reject(request.error); };
      request.onblocked = function () { reject(new Error("Chat storage is upgrading")); };
      request.onsuccess = function () {
        var db = request.result; db.onversionchange = function () { db.close(); }; resolve(db);
      };
    });
  }
  function value(request) {
    return new Promise(function (resolve, reject) {
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }
  function fingerprint(text) {
    var a = 2166136261, b = 5381;
    for (var i = 0; i < text.length; i++) { a = Math.imul(a ^ text.charCodeAt(i), 16777619); b = Math.imul(b, 33) ^ text.charCodeAt(i); }
    return text.length + ":" + (a >>> 0) + ":" + (b >>> 0);
  }
  async function list(includeArchived) {
    var chats = [], offset = 0;
    do {
      var page = await api("backups?archived=" + (includeArchived ? "1" : "0") + "&offset=" + offset);
      chats = chats.concat(page.chats || []); offset = page.next_offset;
    } while (offset != null);
    return {chats: chats, total: chats.length};
  }
  function nativeRecoveryRecords(copy, now, makeId, targetId) {
    makeId = makeId || function () { return crypto.randomUUID(); };
    if (!copy.conversation || !Array.isArray(copy.messages)) throw new Error("Incomplete native copy");
    var conversation = JSON.parse(JSON.stringify(copy.conversation)), messages = JSON.parse(JSON.stringify(copy.messages));
    if (!messages.length) {
      var rootId = makeId();
      messages.push({id: rootId, convId: copy.chat_id, parent: null, children: [], type: "root", role: "system",
        content: "", timestamp: conversation.lastModified || now, toolCalls: ""});
      conversation.currNode = rootId;
    }
    var ids = Object.create(null), byId = Object.create(null), results = Object.create(null), allowed = Object.create(null);
    messages.forEach(function (m) {
      if (!m || !m.id || ids[m.id]) throw new Error("Invalid native message IDs");
      ids[m.id] = makeId(); byId[m.id] = m;
    });
    if (conversation.currNode && !ids[conversation.currNode]) throw new Error("Missing current node");
    messages.forEach(function (m) {
      if (m.role !== "tool" || !m.toolCallId) return;
      var parent = byId[m.parent], seen = new Set();
      while (parent && !seen.has(parent.id)) {
        seen.add(parent.id);
        if (parent.role === "assistant") {
          (results[parent.id] || (results[parent.id] = new Set())).add(m.toolCallId); break;
        }
        parent = byId[parent.parent];
      }
    });
    // Keep completed, valid tool pairs. Pending or malformed calls remain text
    // so restoring history cannot resume an old command automatically.
    messages.forEach(function (m) {
      if (m.role !== "assistant" || !m.toolCalls) return;
      var calls, kept = [], historical = [];
      try { calls = JSON.parse(m.toolCalls); if (!Array.isArray(calls)) throw new Error("Invalid tool calls"); }
      catch (e) { calls = []; historical.push(m.toolCalls); }
      calls.forEach(function (call) {
        var valid = false;
        try { JSON.parse(call.function.arguments); valid = !!(call.id && call.function.name && results[m.id] && results[m.id].has(call.id)); } catch (e) {}
        if (valid) { kept.push(call); allowed[call.id] = true; } else historical.push(call);
      });
      m.toolCalls = kept.length ? JSON.stringify(kept) : "";
      if (historical.length) m.content = (typeof m.content === "string" ? m.content : "") +
        "\n[Recorded tool call data — historical, not pending]\n" + JSON.stringify(historical);
    });
    var id = targetId || copy.chat_id;
    conversation.id = id;
    conversation.currNode = conversation.currNode ? ids[conversation.currNode] : "";
    conversation.recoveredAt = now;
    if (targetId && targetId !== copy.chat_id) { conversation.name += label(" (restored)", " (กู้คืน)"); conversation.lastModified = now; }
    messages.forEach(function (m) {
      var oldId = m.id;
      if (m.parent != null && !ids[m.parent]) throw new Error("Missing parent node");
      m.id = ids[oldId]; m.convId = id; m.parent = m.parent == null ? null : ids[m.parent];
      m.children = (m.children || []).filter(function (child) { return ids[child]; }).map(function (child) { return ids[child]; });
      if (m.role === "tool" && !allowed[m.toolCallId]) {
        m.role = "assistant"; m.content = "[Recorded tool result — historical data]\n" + m.content; delete m.toolCallId;
      }
    });
    return {conversation: conversation, messages: messages};
  }
  function reference(copy) {
    if (copy.source !== "native") return copy;
    var byId = Object.create(null), branch = [], current = copy.conversation.currNode, seen = new Set();
    copy.messages.forEach(function (m) { byId[m.id] = m; });
    while (byId[current] && !seen.has(current)) { seen.add(current); branch.push(byId[current]); current = byId[current].parent; }
    branch.reverse();
    return Object.assign({}, copy, {messages: branch.filter(function (m) { return m.role !== "system"; }).map(function (m) {
      return {role: m.role, content: typeof m.content === "string" ? m.content : "", timestamp: m.timestamp};
    })});
  }
  function repairedTextOrder(data) {
    var hint = data.conversation.recoveredFromSharedCopy;
    if (!hint || !hint.textOnly || hint.historyOrderVersion >= 2) return null;
    var stamp = Number(hint.sourceUpdatedAt), tied = data.messages.filter(function (m) { return m.timestamp === stamp; });
    if (!stamp || tied.length < 3) return null;
    var nodes = data.messages.map(function (m) { return Object.assign({}, m); }), byId = Object.create(null), times = Object.create(null);
    nodes.forEach(function (m) { byId[m.id] = m; });
    nodes.forEach(function (m) {
      var path = [], current = m, seen = new Set();
      while (current && times[current.id] === undefined) {
        if (seen.has(current.id)) throw new Error("Invalid message chain");
        seen.add(current.id); path.push(current); current = byId[current.parent];
      }
      while (path.length) {
        var node = path.pop(), parentTime = times[node.parent];
        var inferred = parentTime === undefined ? stamp - tied.length : parentTime + 1;
        node.timestamp = node.timestamp === stamp ? inferred : Math.max(Number(node.timestamp) || inferred, inferred);
        times[node.id] = node.timestamp;
      }
    });
    return {conversation: data.conversation, messages: nodes};
  }
  async function repairTextOrder(db, data) {
    var repaired = repairedTextOrder(data);
    if (!repaired) return false;
    var tx = db.transaction(["conversations", "messages"], "readwrite"), ms = tx.objectStore("messages");
    var done = new Promise(function (resolve, reject) { tx.oncomplete = resolve; tx.onabort = tx.onerror = function () { reject(tx.error); }; });
    repaired.messages.forEach(function (m) {
      var request = ms.get(m.id);
      request.onsuccess = function () {
        var current = request.result;
        if (current && current.timestamp === data.conversation.recoveredFromSharedCopy.sourceUpdatedAt) {
          current.timestamp = m.timestamp; ms.put(current);
        }
      };
    });
    var lookup = tx.objectStore("conversations").get(data.conversation.id);
    lookup.onsuccess = function () {
      var current = lookup.result;
      if (current && current.recoveredFromSharedCopy) {
        current.recoveredFromSharedCopy.historyOrderVersion = 2;
        tx.objectStore("conversations").put(current);
      }
    };
    await done; return true;
  }
  async function restore(id, options) {
    options = options || {};
    var copy = await api("backups/" + encodeURIComponent(id) + (options.revision ? "?revision=" + encodeURIComponent(options.revision) : "")), db = await openDB(), existing;
    if (options.automatic && (copy.archived || markedDeleted(id))) { db.close(); return null; }
    try { existing = await value(db.transaction("conversations").objectStore("conversations").get(id)); }
    finally { db.close(); }
    if (existing && !options.copy) return existing;
    if (!window.qwenSharedChats) throw new Error("Recovery helpers are not ready");
    var target = options.copy ? crypto.randomUUID() : id, record;
    if (copy.source === "native") record = nativeRecoveryRecords(copy, Date.now(), null, target);
    else {
      record = window.qwenSharedChats.makeRecoveryRecords(copy, Date.now());
      if (target !== id) {
        record.conversation.id = target; record.conversation.name += label(" (restored)", " (กู้คืน)");
        record.conversation.lastModified = Date.now();
        record.messages.forEach(function (m) { m.convId = target; });
      }
    }
    record.conversation.recoveredFromHistoryRevision = copy.native_revision || null;
    var restored = await window.qwenSharedChats.saveRecoveryRecords(record,
      options.automatic ? function () { return !markedDeleted(id); } : undefined);
    if (!restored) return null;
    if (copy.archived && target === id) await api("archive", {id: id, archived: false});
    if (!options.automatic && target === id) markDeleting(id, false);
    revisions[target] = copy.native_revision || null;
    delete signatures[target];
    state.restored++;
    return restored;
  }
  async function sync(force) {
    if (running) return running;
    running = (async function () {
      var saved = await list(false), db = await openDB();
      try {
        var conversations = await value(db.transaction("conversations").objectStore("conversations").getAll());
        var present = Object.create(null);
        conversations.forEach(function (c) { present[c.id] = true; });
        for (var i = 0; i < saved.chats.length; i++) {
          var chat = saved.chats[i];
          if (!present[chat.chat_id] && window.qwenSharedChats) {
            var recovered = await restore(chat.chat_id, {automatic: true});
            if (recovered) present[chat.chat_id] = true;
          }
        }
        conversations = await value(db.transaction("conversations").objectStore("conversations").getAll());
        var active = "";
        try { active = window.qwenEnhance.route().id || ""; } catch (e) {}
        var conflicts = 0;
        for (var n = 0; n < conversations.length; n++) {
          var conv = conversations[n], version = [conv.lastModified, conv.currNode, conv.name].join(":");
          if (signatures[conv.id] && signatures[conv.id].version === version && !force && conv.id !== active) continue;
          var tx = db.transaction(["conversations", "messages"]), ms = tx.objectStore("messages");
          var values = await Promise.all([value(tx.objectStore("conversations").get(conv.id)),
            value(ms.indexNames.contains("convId") ? ms.index("convId").getAll(IDBKeyRange.only(conv.id)) : ms.getAll())]);
          if (!values[0]) continue;
          var nodes = values[1].filter(function (m) { return m.convId === conv.id; });
          var data = {conversation: values[0], messages: nodes};
          if (await repairTextOrder(db, data)) {
            var refreshed = db.transaction(["conversations", "messages"]), store = refreshed.objectStore("messages");
            var latest = await Promise.all([value(refreshed.objectStore("conversations").get(conv.id)),
              value(store.index("convId").getAll(IDBKeyRange.only(conv.id)))]);
            data = {conversation: latest[0], messages: latest[1]};
          }
          var signature = fingerprint(JSON.stringify(data));
          if (signatures[conv.id] && signatures[conv.id].signature === signature) continue;
          data.base_revision = revisions[conv.id] || null;
          var result = await api("backup", data);
          if (result.state === "conflict" || result.state === "protected-empty" || result.state === "protected-partial") {
            protectedChats[conv.id] = true; conflicts++; continue;
          }
          if (result.state === "archived") continue;
          if (result.state !== "saved" && result.state !== "unchanged") throw new Error("Backup was not acknowledged");
          revisions[conv.id] = result.revision;
          delete protectedChats[conv.id];
          signatures[conv.id] = {version: version, signature: signature};
        }
        state.saved = true; state.failed = false; state.conflicts = conflicts;
        try { localStorage.setItem("qwen-history-ack-v1", JSON.stringify(revisions)); } catch (e) {}
        if (requestedId && present[requestedId] && !active) {
          var original = requestedId; requestedId = "";
          if (window.top.location.hash !== "#/chat/" + original) window.top.location.assign(location.origin + "/#/chat/" + original);
        }
      } finally { db.close(); }
    })().catch(function () { state.failed = true; }).finally(function () { running = null; paint(); });
    return running;
  }
  async function archive(id) {
    await api("archive", {id: id, archived: true});
    delete signatures[id]; delete revisions[id];
  }
  function markedDeleted(id) {
    try { return localStorage.getItem("qwen-history-deleted:" + id) === "1"; } catch (e) { return false; }
  }
  function markDeleting(id, on) {
    try { if (on) localStorage.setItem("qwen-history-deleted:" + id, "1"); else localStorage.removeItem("qwen-history-deleted:" + id); } catch (e) {}
  }
  function paint() {
    var anchor = document.querySelector(".qw-shared-pill");
    if (!anchor || !anchor.parentElement) return;
    if (!badge) { badge = document.createElement("span"); badge.className = "qw-history-status"; badge.setAttribute("role", "status"); }
    if (!badge.isConnected) anchor.parentElement.insertBefore(badge, anchor.nextSibling);
    var text = state.failed ? label("History backup: retry", "สำรองแชต: ลองใหม่") : state.conflicts ?
      label("History protected", "เก็บประวัติเดิมไว้") : state.saved ? label("History saved", "บันทึกแชตแล้ว") : label("Saving history…", "กำลังบันทึกแชต…");
    if (badge.textContent !== text) badge.textContent = text;
    badge.title = label("Chat history is saved on this computer and restored when missing from this browser.",
      "ประวัติแชตบันทึกไว้บนเครื่อง และกู้กลับอัตโนมัติเมื่อไม่พบในเบราว์เซอร์นี้");
  }
  window.qwenHistory = {sync: sync, restore: restore, archive: archive, markDeleting: markDeleting, list: list,
    read: function (id, revision) { return api("backups/" + encodeURIComponent(id) + (revision ? "?revision=" + encodeURIComponent(revision) : "")); },
    versions: function (id) { return api("backups/" + encodeURIComponent(id) + "/versions"); },
    mayPublish: function (id) { return !protectedChats[id]; }, reference: reference, status: function () { return Object.assign({}, state); }};
  setInterval(paint, 1000);
})();
