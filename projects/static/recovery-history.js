/* Merge completed transport journals into their exact native WebUI branch.
 * No request is executed here. Ambiguous, changed or unapproved work pauses.
 */
(function () {
  "use strict";
  var MAX_TEXT = 16 * 1024 * 1024, MAX_NODES = 20000;
  function clone(v) { return JSON.parse(JSON.stringify(v)); }
  function stable(v) {
    if (Array.isArray(v)) return "[" + v.map(stable).join(",") + "]";
    if (v && typeof v === "object") return "{" + Object.keys(v).sort().map(function (k) { return JSON.stringify(k) + ":" + stable(v[k]); }).join(",") + "}";
    return JSON.stringify(v);
  }
  function hash(v) {
    var s = stable(v), a = 2166136261, b = 5381;
    for (var i = 0; i < s.length; i++) { a = Math.imul(a ^ s.charCodeAt(i), 16777619); b = Math.imul(b, 33) ^ s.charCodeAt(i); }
    return s.length + ":" + (a >>> 0) + ":" + (b >>> 0);
  }
  function text(v) {
    if (typeof v === "string") return v;
    return Array.isArray(v) ? v.filter(function (p) { return p && p.type === "text" && typeof p.text === "string"; }).map(function (p) { return p.text; }).join("\n") : "";
  }
  function bodyOf(v) { try { return typeof v === "string" ? JSON.parse(v) : v; } catch (e) { return null; } }
  function index(snapshot) {
    if (!snapshot || !snapshot.conversation || !Array.isArray(snapshot.messages) || snapshot.messages.length > MAX_NODES) return null;
    var byId = Object.create(null), valid = true, conv = snapshot.conversation;
    snapshot.messages.forEach(function (m) { if (!m || typeof m.id !== "string" || byId[m.id] || m.convId !== conv.id) valid = false; else byId[m.id] = m; });
    return valid && byId[conv.currNode] ? byId : null;
  }
  function path(byId, id) {
    var rows = [], seen = Object.create(null);
    while (id != null && id !== "") {
      var m = byId[id];
      if (!m || seen[id]) return null;
      seen[id] = true; rows.push(m); id = m.parent;
    }
    return rows;
  }
  function nodeHash(m) {
    var copy = clone(m); delete copy.children; delete copy.recoveredTransport;
    return hash(copy);
  }
  function pathHash(rows) { return hash(rows.map(function (m) { return [m.id, nodeHash(m)]; })); }
  function calls(m) {
    var c = bodyOf(m.toolCalls || "[]"), ids = Object.create(null);
    if (!Array.isArray(c) || c.length > 400) return null;
    for (var i = 0; i < c.length; i++) {
      var item = c[i], key = item && String(item.id);
      if (!item || typeof item.id !== "string" || !item.id || ids[key] || !item.function || typeof item.function.name !== "string") return null;
      ids[key] = true;
      if (!bodyOf(item.function.arguments || "{}") || typeof bodyOf(item.function.arguments || "{}") !== "object") return null;
    }
    return c;
  }
  function completedChildren(byId, assistant, allCalls) {
    if (!Array.isArray(assistant.children) || assistant.children.length > allCalls.length) return null;
    var out = [], seen = Object.create(null);
    for (var i = 0; i < assistant.children.length; i++) {
      var m = byId[assistant.children[i]];
      if (!m || seen[m.id] || m.role !== "tool" || m.parent !== assistant.id || m.toolCallId !== allCalls[i].id) return null;
      seen[m.id] = true; out.push(m);
    }
    return out;
  }
  function command(body, kind) {
    if (!body || typeof body !== "object") return null;
    if (kind === "tools" && typeof body.tool === "string" && body.params && typeof body.params === "object") return {name: body.tool, args: body.params};
    if (kind === "mcp" && body.method === "tools/call" && body.params && typeof body.params.name === "string") return {name: body.params.name, args: body.params.arguments || {}};
    return null;
  }
  // Pure capture/planning functions are exported for adversarial branch tests.
  function capturePlan(snapshot, context) {
    var byId = index(snapshot), body = bodyOf(context && context.body), conv = snapshot && snapshot.conversation;
    if (!byId || !context || !context.id || !body || conv.id !== context.chat || !context.project || !context.origin) return null;
    var tip = byId[conv.currNode], kind = context.kind, assistant = null, anchor = tip, done = [], allCalls;
    if (kind === "chat") {
      if (!Array.isArray(body.messages)) return null;
      if (tip.role === "assistant") {
        if (text(tip.content) || tip.toolCalls || !Array.isArray(tip.children) || tip.children.length) return null;
        assistant = tip; anchor = byId[tip.parent];
      }
      if (!anchor || ["user", "tool"].indexOf(anchor.role) < 0) return null;
    } else {
      assistant = tip.role === "assistant" ? tip : tip.role === "tool" ? byId[tip.parent] : null;
      if (!assistant || assistant.role !== "assistant" || !(allCalls = calls(assistant))) return null;
      done = completedChildren(byId, assistant, allCalls);
      if (!done || done.length >= allCalls.length || conv.currNode !== (done.length ? done[done.length - 1].id : assistant.id)) return null;
      var op = command(body, kind), call = allCalls[done.length];
      if (!op || call.function.name !== op.name || stable(bodyOf(call.function.arguments || "{}")) !== stable(op.args)) return null;
      anchor = byId[assistant.parent];
    }
    var branch = path(byId, anchor.id), user = branch && branch.find(function (m) { return m.role === "user"; });
    if (!branch || !user) return null;
    if (kind === "chat") {
      var users = body.messages.filter(function (m) { return m && m.role === "user"; });
      if (!users.length || text(users[users.length - 1].content) !== text(user.content)) return null;
    }
    return {version: 1, id: context.id, chat: context.chat, project: context.project, origin: context.origin,
      kind: kind, epoch: context.epoch || "0", bodyHash: hash(body), userId: user.id,
      anchorId: anchor.id, branchHash: pathHash(branch), anchorChildren: (anchor.children || []).slice(),
      assistantId: assistant ? assistant.id : null, assistantHash: assistant ? nodeHash(assistant) : null,
      completedIds: done.map(function (m) { return m.id; }), completedHashes: done.map(nodeHash),
      callId: kind === "chat" ? null : allCalls[done.length].id, callIndex: kind === "chat" ? null : done.length,
      model: kind === "chat" && typeof body.model === "string" ? body.model : ""};
  }
  function sseEvents(raw) {
    var out = [], done = false;
    raw.replace(/\r\n/g, "\n").split("\n\n").forEach(function (block) {
      var data = block.split("\n").filter(function (line) { return line.indexOf("data:") === 0; }).map(function (line) { return line.slice(5).replace(/^ /, ""); }).join("\n");
      if (!data) return;
      if (data === "[DONE]") { done = true; return; }
      out.push(JSON.parse(data));
    });
    return {events: out, done: done};
  }
  function generation(completion) {
    var raw = completion.text, answer = "", reasoning = "", finish = null, tool = [], seenFinish = false;
    if (/text\/event-stream/i.test(completion.contentType || "")) {
      var parsed = sseEvents(raw);
      if (!parsed.done) return null;
      parsed.events.forEach(function (event) {
        if (event.error) throw new Error("Generation failed");
        var choice = event.choices && event.choices[0];
        if (!choice) return;
        var delta = choice.delta || choice.message || {};
        if (typeof delta.content === "string") answer += delta.content;
        if (typeof delta.reasoning_content === "string") reasoning += delta.reasoning_content;
        if (Array.isArray(delta.tool_calls)) delta.tool_calls.forEach(function (c) {
          var n = c.index == null ? 0 : c.index;
          if (!Number.isInteger(n) || n < 0 || n > 399) throw new Error("Invalid tool index");
          var target = tool[n] || (tool[n] = {id: "", type: "function", function: {name: "", arguments: ""}});
          if (c.id) target.id += c.id;
          if (c.function) { target.function.name += c.function.name || ""; target.function.arguments += c.function.arguments || ""; }
        });
        if (choice.finish_reason != null) { finish = choice.finish_reason; seenFinish = true; }
      });
    } else {
      var doc = JSON.parse(raw), choice = doc.choices && doc.choices[0], message = choice && choice.message;
      if (!message || doc.error) return null;
      answer = text(message.content); reasoning = text(message.reasoning_content); tool = message.tool_calls || [];
      finish = choice.finish_reason; seenFinish = finish != null;
    }
    if (!seenFinish || ["stop", "length", "tool_calls"].indexOf(finish) < 0 || !Array.isArray(tool)) return null;
    // Calls have not passed the native permission UI after a reload. Keep data
    // as historical text rather than creating executable pending toolCalls.
    var rawContent = answer;
    if (tool.length) answer += "\n[Recovered tool calls; not executed. A new permission review is required.]\n" + JSON.stringify(tool);
    if (!answer && !reasoning) return null;
    return {content: answer, rawContent: rawContent, toolCalls: tool, reasoning: reasoning, pendingPermission: tool.length > 0, truncated: finish === "length"};
  }
  function toolOutput(completion, kind) {
    var doc;
    if (/text\/event-stream/i.test(completion.contentType || "")) {
      var parsed = sseEvents(completion.text), output = "", done = false;
      if (kind === "tools") {
        parsed.events.forEach(function (event) { if (event.error) throw new Error("Tool response failed"); if (typeof event.chunk === "string") output += event.chunk; if (event.done === true) done = true; });
        return done ? output : null;
      }
      var replies = parsed.events.filter(function (event) { return event && event.jsonrpc === "2.0" &&
        (Object.prototype.hasOwnProperty.call(event, "result") || Object.prototype.hasOwnProperty.call(event, "error")); });
      if (replies.length !== 1) return null;
      doc = replies[0];
    } else doc = JSON.parse(completion.text);
    if (kind === "tools") return typeof doc.plain_text_response === "string" ? doc.plain_text_response : null;
    if (doc.error || !doc.result || !Array.isArray(doc.result.content) || !doc.result.content.every(function (p) { return p && p.type === "text" && typeof p.text === "string"; })) return null;
    var content = doc.result.content.map(function (p) { return p.text; }).join("\n");
    return (doc.result.isError ? "[Recovered tool error]\n" : "") + content;
  }
  function reject(reason) { return {restored: false, continue: false, reason: reason}; }
  function restorePlan(snapshot, record, completion, environment) {
    var binding = record && record.binding, byId = index(snapshot), env = environment || {};
    if (!binding || binding.version !== 1 || !byId || binding.id !== record.id) return reject("missing_binding");
    if (env.deleted || env.stopped || record.stopped || env.streaming || env.chat !== binding.chat || env.project !== binding.project || env.origin !== binding.origin || String(env.epoch || "0") !== binding.epoch) return reject("context_changed");
    var requestHash = record.body == null ? record.requestHash : hash(bodyOf(record.body));
    if (snapshot.conversation.id !== binding.chat || requestHash !== binding.bodyHash) return reject("request_changed");
    if (!completion || completion.status !== 200 || typeof completion.text !== "string" || completion.text.length > MAX_TEXT) return reject("incomplete_response");
    var anchor = byId[binding.anchorId], branch = anchor && path(byId, anchor.id);
    if (!branch || pathHash(branch) !== binding.branchHash || !branch.some(function (m) { return m.id === binding.userId && m.role === "user"; })) return reject("branch_changed");
    var marks = snapshot.conversation.recoveredTransport || {};
    if (marks[record.id]) return {restored: true, continue: false, already: true, reason: "already_restored", reload: false};
    var conv = clone(snapshot.conversation), writes = [], result = {restored: true, continue: false, reload: true};
    var now = Number(env.now) || Date.now(), restoredId = "recovery-" + record.id;
    if (binding.kind === "chat") {
      var parsed;
      try { parsed = generation(completion); } catch (e) { return reject("invalid_generation"); }
      if (!parsed) return reject("incomplete_generation");
      var assistant = binding.assistantId && byId[binding.assistantId], current = byId[conv.currNode];
      // An assistant ID created after capture could be another browser's new
      // branch. Only an exactly matching complete answer is safe to adopt.
      if (!assistant && current && current.parent === anchor.id && current.role === "assistant" &&
          !(current.children || []).length && !current.toolCalls && text(current.content) === parsed.content) assistant = current;
      var expected = binding.anchorChildren.slice(), children = anchor.children || [];
      if (assistant && expected.indexOf(assistant.id) < 0) expected.push(assistant.id);
      if (stable(children) !== stable(expected) || conv.currNode !== (assistant ? assistant.id : anchor.id)) return reject("branch_changed");
      if (assistant) {
        if ((assistant.children || []).length || assistant.toolCalls || parsed.content.indexOf(text(assistant.content)) !== 0) return reject("assistant_changed");
        if (binding.assistantId && nodeHash(assistant) !== binding.assistantHash) return reject("assistant_changed");
        assistant = clone(assistant);
      } else {
        if (byId[restoredId]) return reject("id_conflict");
        assistant = {id: restoredId, convId: conv.id, parent: anchor.id, children: [], role: "assistant", type: "text", timestamp: now, toolCalls: ""};
        var changedAnchor = clone(anchor); changedAnchor.children = children.concat([restoredId]); writes.push(changedAnchor);
      }
      assistant.content = parsed.content; assistant.toolCalls = "";
      if (parsed.reasoning) assistant.reasoningContent = parsed.reasoning;
      if (binding.model) assistant.model = binding.model;
      assistant.recoveredTransport = record.id; writes.push(assistant); conv.currNode = assistant.id;
      result.continue = parsed.truncated && !parsed.pendingPermission;
      result.reason = parsed.pendingPermission ? "pending_permission" : parsed.truncated ? "generation_limit" : "final_answer_restored";
      result.pendingPermission = parsed.pendingPermission;
    } else {
      var original = byId[binding.assistantId], allCalls = original && calls(original), done = allCalls && completedChildren(byId, original, allCalls), output;
      if (!original || nodeHash(original) !== binding.assistantHash || !done ||
          (done.length !== binding.callIndex && done.length !== binding.callIndex + 1) || allCalls[binding.callIndex].id !== binding.callId ||
          stable(done.slice(0, binding.callIndex).map(function (m) { return m.id; })) !== stable(binding.completedIds) ||
          stable(done.slice(0, binding.callIndex).map(nodeHash)) !== stable(binding.completedHashes) ||
          conv.currNode !== (done.length ? done[done.length - 1].id : original.id)) return reject("tool_branch_changed");
      try { output = toolOutput(completion, binding.kind); } catch (e) { return reject("invalid_tool_response"); }
      if (output == null) return reject("incomplete_tool_response");
      var alreadySaved = done.length === binding.callIndex + 1;
      if (alreadySaved) {
        if (done[done.length - 1].content !== output || done[done.length - 1].toolCallId !== binding.callId) return reject("tool_result_changed");
      } else {
        if (byId[restoredId]) return reject("id_conflict");
        var tool = {id: restoredId, convId: conv.id, parent: original.id, children: [], role: "tool", type: "text", content: output,
          timestamp: now, toolCalls: "", toolCallId: binding.callId, recoveredTransport: record.id};
        var changed = clone(original); changed.children = changed.children.concat([tool.id]);
        writes.push(changed, tool); conv.currNode = tool.id;
      }
      // Other calls in this generated batch have never been approved/executed.
      // Leave them for the normal UI; do not synthesize their results or run them.
      result.pendingPermission = binding.callIndex + 1 !== allCalls.length;
      result.continue = !result.pendingPermission;
      result.reason = result.pendingPermission ? "pending_permission" : "tool_result_restored";
    }
    conv.lastModified = Math.max(now, Number(conv.lastModified) || 0);
    conv.recoveredTransport = Object.assign({}, marks); conv.recoveredTransport[record.id] = {at: now, kind: binding.kind};
    // Keep only bounded idempotency markers, independent of private response text.
    var keys = Object.keys(conv.recoveredTransport);
    if (keys.length > 200) keys.slice(0, keys.length - 200).forEach(function (key) { delete conv.recoveredTransport[key]; });
    if (result.continue) result.continuation = {id: record.id, chat: binding.chat, project: binding.project, origin: binding.origin,
      epoch: binding.epoch, currNode: conv.currNode, userId: binding.userId, branchHash: binding.branchHash, anchorId: binding.anchorId};
    result.conversation = conv; result.messages = writes; return result;
  }
  function continuationPlan(snapshot, ticket, env) {
    var byId = index(snapshot), conv = snapshot && snapshot.conversation;
    if (!byId || !ticket || !env || env.deleted || env.streaming || env.stopped || env.chat !== ticket.chat || env.project !== ticket.project ||
        env.origin !== ticket.origin || String(env.epoch || "0") !== ticket.epoch || conv.id !== ticket.chat || conv.currNode !== ticket.currNode ||
        !conv.recoveredTransport || !conv.recoveredTransport[ticket.id]) return false;
    var anchor = byId[ticket.anchorId], branch = anchor && path(byId, anchor.id), tip = byId[conv.currNode];
    if (!branch || pathHash(branch) !== ticket.branchHash || !branch.some(function (m) { return m.id === ticket.userId && m.role === "user"; })) return false;
    if (tip.role === "tool") {
      var assistant = byId[tip.parent], all = assistant && calls(assistant), done = all && completedChildren(byId, assistant, all);
      return !!(done && done.length === all.length && done.length && done[done.length - 1].id === tip.id);
    }
    return tip.role === "assistant" && !tip.toolCalls && !(tip.children || []).length;
  }
  function canonicalCalls(raw) {
    var parsed = typeof raw === "string" ? bodyOf(raw || "[]") : raw;
    if (!Array.isArray(parsed)) return null;
    try { return parsed.map(function (call) { return [call.id, call.function.name, bodyOf(call.function.arguments || "{}")]; }); } catch (e) { return null; }
  }
  function acknowledgePlan(snapshot, record, completion, env) {
    var b = record && record.binding, byId = index(snapshot), e = env || {};
    if (!b || b.id !== record.id || !byId || e.deleted || e.stopped || record.stopped || e.chat !== b.chat || e.project !== b.project ||
        e.origin !== b.origin || String(e.epoch || "0") !== b.epoch || snapshot.conversation.id !== b.chat ||
        (record.body == null ? record.requestHash : hash(bodyOf(record.body))) !== b.bodyHash || !completion || completion.status !== 200 ||
        typeof completion.text !== "string" || completion.text.length > MAX_TEXT) return false;
    var anchor = byId[b.anchorId], branch = anchor && path(byId, anchor.id), active = path(byId, snapshot.conversation.currNode);
    if (!branch || !active || pathHash(branch) !== b.branchHash || !branch.some(function (m) { return m.id === b.userId && m.role === "user"; })) return false;
    try {
      if (b.kind === "chat") {
        var parsed = generation(completion);
        if (!parsed) return false;
        var candidates = b.assistantId ? [byId[b.assistantId]] : (anchor.children || []).filter(function (id) { return b.anchorChildren.indexOf(id) < 0; }).map(function (id) { return byId[id]; });
        if (candidates.length !== 1) return false;
        var assistant = candidates[0];
        return !!(assistant && assistant.role === "assistant" && assistant.parent === anchor.id && active.some(function (m) { return m.id === assistant.id; }) &&
          text(assistant.content) === parsed.rawContent && stable(canonicalCalls(assistant.toolCalls || "[]")) === stable(canonicalCalls(parsed.toolCalls)));
      }
      var owner = byId[b.assistantId], all = owner && calls(owner), done = all && completedChildren(byId, owner, all), output = toolOutput(completion, b.kind);
      return !!(owner && nodeHash(owner) === b.assistantHash && done && done.length > b.callIndex && output != null &&
        active.some(function (m) { return m.id === owner.id; }) && done[b.callIndex].toolCallId === b.callId && done[b.callIndex].content === output &&
        stable(done.slice(0, b.callIndex).map(function (m) { return m.id; })) === stable(b.completedIds) && stable(done.slice(0, b.callIndex).map(nodeHash)) === stable(b.completedHashes));
    } catch (e2) { return false; }
  }
  function attachPlan(snapshot, binding, env) {
    var byId = index(snapshot), b = binding, e = env || {}, conv = snapshot && snapshot.conversation;
    if (!byId || !b || b.version !== 1 || e.deleted || e.stopped || e.chat !== b.chat || e.project !== b.project || e.origin !== b.origin ||
        String(e.epoch || "0") !== b.epoch || conv.id !== b.chat) return false;
    var anchor = byId[b.anchorId], branch = anchor && path(byId, anchor.id);
    if (!branch || pathHash(branch) !== b.branchHash || !branch.some(function (m) { return m.id === b.userId && m.role === "user"; })) return false;
    if (b.kind === "chat") {
      if (stable(anchor.children || []) !== stable(b.anchorChildren)) return false;
      if (!b.assistantId) return conv.currNode === anchor.id;
      var assistant = byId[b.assistantId], parsed = assistant && calls(assistant);
      // The original streaming assistant may update its text and timestamp.
      // Its identity, parent, leaf and empty tool state must stay unchanged.
      return !!(assistant && assistant.role === "assistant" && assistant.parent === anchor.id && !(assistant.children || []).length &&
        parsed && !parsed.length && conv.currNode === assistant.id);
    }
    var owner = byId[b.assistantId], all = owner && calls(owner), done = all && completedChildren(byId, owner, all);
    return !!(owner && nodeHash(owner) === b.assistantHash && done && done.length === b.callIndex &&
      stable(done.map(function (m) { return m.id; })) === stable(b.completedIds) && stable(done.map(nodeHash)) === stable(b.completedHashes) &&
      conv.currNode === (done.length ? done[done.length - 1].id : owner.id));
  }
  function route() {
    try { return window.qwenEnhance.route(); } catch (e) {
      var id = (window.location.hash.match(/^#\/chat\/([A-Za-z0-9_-]+)$/) || [])[1]; return {name: id ? "chat" : "", id: id || ""};
    }
  }
  function project() { try { return (window.parent.qwenShell || window.qwenShell).project.slug; } catch (e) { return ""; } }
  function epoch(chat) { try { return localStorage.getItem("qwen-recovery-epoch:" + chat) || "0"; } catch (e) { return "unavailable"; } }
  function invalidate(chat) { try { localStorage.setItem("qwen-recovery-epoch:" + chat, String(Date.now()) + ":" + Math.random()); } catch (e) {} }
  function openDB() {
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open("LlamaUi");
      request.onupgradeneeded = function () { request.transaction.abort(); };
      request.onerror = request.onblocked = function () { reject(new Error("Chat storage unavailable")); };
      request.onsuccess = function () { var db = request.result; db.onversionchange = function () { db.close(); }; resolve(db); };
    });
  }
  async function transact(chat, write, planner) {
    var db = await openDB();
    try {
      return await new Promise(function (resolve, rejectPromise) {
        var tx = db.transaction(["conversations", "messages"], write ? "readwrite" : "readonly"), cs = tx.objectStore("conversations"), ms = tx.objectStore("messages");
        var c = cs.get(chat), m = ms.indexNames.contains("convId") ? ms.index("convId").getAll(IDBKeyRange.only(chat)) : ms.getAll(), count = 0, result;
        function ready() {
          if (++count !== 2) return;
          try {
            result = planner({conversation: c.result, messages: m.result.filter(function (row) { return row.convId === chat; })});
            if (write && result.restored && !result.already) { result.messages.forEach(function (row) { ms.put(row); }); cs.put(result.conversation); }
          } catch (e) { tx.abort(); }
        }
        c.onsuccess = m.onsuccess = ready;
        tx.oncomplete = function () { resolve(result); };
        tx.onerror = tx.onabort = function () { rejectPromise(new Error("Recovery transaction failed")); };
      });
    } finally { db.close(); }
  }
  async function capture(context, requestBody, kind) {
    if (typeof context === "string") context = {chat: context, body: requestBody, kind: kind, id: crypto.randomUUID(), project: project()};
    var current = route();
    if (!context || current.name !== "chat" || current.id !== context.chat || context.project !== project()) return null;
    var full = Object.assign({}, context, {origin: location.origin, epoch: epoch(context.chat)});
    try { return await transact(context.chat, false, function (snapshot) { return capturePlan(snapshot, full); }); } catch (e) { return null; }
  }
  async function restore(record, completion) {
    var current = route(), binding = record && record.binding;
    if (!binding) return reject("missing_binding");
    try {
      return await transact(binding.chat, true, function (snapshot) {
        var deleted = false, streaming = false;
        try { deleted = localStorage.getItem("qwen-history-deleted:" + binding.chat) === "1"; } catch (e) { deleted = true; }
        try { streaming = window.qwenEnhance.isStreaming(); } catch (e) {}
        return restorePlan(snapshot, record, completion, {origin: location.origin, project: project(), chat: route().id,
          epoch: epoch(binding.chat), deleted: deleted, streaming: streaming});
      });
    } catch (e) { return reject("storage_unavailable"); }
  }
  async function canContinue(ticket) {
    if (!ticket) return false;
    try {
      return await transact(ticket.chat, false, function (snapshot) {
        var deleted = false, streaming = false;
        try { deleted = localStorage.getItem("qwen-history-deleted:" + ticket.chat) === "1"; } catch (e) { deleted = true; }
        try { streaming = window.qwenEnhance.isStreaming(); } catch (e) {}
        return continuationPlan(snapshot, ticket, {origin: location.origin, project: project(), chat: route().id, epoch: epoch(ticket.chat), deleted: deleted, streaming: streaming});
      });
    } catch (e) { return false; }
  }
  async function acknowledge(record, completion) {
    var b = record && record.binding;
    if (!b) return false;
    try {
      return await transact(b.chat, false, function (snapshot) {
        var deleted = false;
        try { deleted = localStorage.getItem("qwen-history-deleted:" + b.chat) === "1"; } catch (e) { deleted = true; }
        return acknowledgePlan(snapshot, record, completion, {origin: location.origin, project: project(), chat: route().id, epoch: epoch(b.chat), deleted: deleted});
      });
    } catch (e) { return false; }
  }
  async function canAttach(binding) {
    if (!binding) return false;
    try {
      return await transact(binding.chat, false, function (snapshot) {
        var deleted = false;
        try { deleted = localStorage.getItem("qwen-history-deleted:" + binding.chat) === "1"; } catch (e) { deleted = true; }
        return attachPlan(snapshot, binding, {origin: location.origin, project: project(), chat: route().id, epoch: epoch(binding.chat), deleted: deleted});
      });
    } catch (e) { return false; }
  }
  window.qwenRecoveryHistory = {capture: capture, restore: restore, invalidate: invalidate, canContinue: canContinue, acknowledge: acknowledge, canAttach: canAttach,
    planner: {capture: capturePlan, restore: restorePlan, generation: generation, toolOutput: toolOutput, canContinue: continuationPlan, acknowledge: acknowledgePlan, canAttach: attachPlan}};
})();
