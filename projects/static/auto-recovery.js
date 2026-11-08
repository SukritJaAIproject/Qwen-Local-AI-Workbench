/* Durable connection recovery for the local WebUI.  Every reconnect attaches to
 * the same server operation; it never resubmits an action with a new identity. */
(function () {
  "use strict";
  if (window.qwenRecovery || typeof window.fetch !== "function" || typeof ReadableStream !== "function") return;
  var inner = window.fetch.bind(window), operations = new Map(), wakeups = new Set();
  var KEY = "qwen-stream-recovery-v1", STOP_KEY = "qwen-stream-recovery-stops-v1", REFRESH_KEY = "qwen-stream-recovery-refresh-v1", LEASE = "qwen-stream-recovery-lease:";
  var MAX_RESULT = 32 * 1024 * 1024, LEASE_MS = 20000;
  var HEADER_MS = Number(window.QWEN_RECOVERY_HEADER_MS) || 30000, IDLE_MS = Number(window.QWEN_RECOVERY_IDLE_MS) || 60000;
  var owner = uuid(), records = read(KEY, {}), stops = read(STOP_KEY, {}), banner = null, notices = {};
  var restoring = false, lastOn = null, pageLeaving = false, continuing = false;

  function uuid() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
    var bytes = new Uint8Array(16);
    if (!window.crypto || !window.crypto.getRandomValues) throw new Error("Secure operation identities are unavailable");
    window.crypto.getRandomValues(bytes); bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    var s = Array.from(bytes, function (b) { return b.toString(16).padStart(2, "0"); }).join("");
    return s.slice(0, 8) + "-" + s.slice(8, 12) + "-" + s.slice(12, 16) + "-" + s.slice(16, 20) + "-" + s.slice(20);
  }
  function read(key, fallback) { try { return JSON.parse(window.sessionStorage.getItem(key) || "null") || fallback; } catch (_) { return fallback; } }
  function save() {
    try {
      var ids = Object.keys(records).sort(function (a, b) { return records[b].createdAt - records[a].createdAt; });
      ids.slice(24).forEach(function (id) { if (!operations.has(id)) delete records[id]; });
      window.sessionStorage.setItem(KEY, JSON.stringify(records));
    } catch (_) { /* A full browser store cannot disable recovery in the current page. */ }
  }
  function saveStops() { try { window.sessionStorage.setItem(STOP_KEY, JSON.stringify(stops)); } catch (_) {} }
  function identity(op) { return op.project + "|" + op.chat; }
  function unresolved(record) { return record && !/^(?:stopped|superseded|acknowledged)$/.test(record.state); }
  function state() { try { return window.qwenEnhance && window.qwenEnhance.autoContinue() || {}; } catch (_) { return {}; } }
  function route() { try { return window.qwenEnhance && window.qwenEnhance.route() || {}; } catch (_) { return {}; } }
  function isPlan() { try { return !!(window.qwenEnhance && window.qwenEnhance.plan && window.qwenEnhance.plan().on); } catch (_) { return true; } }
  function text(en, th) {
    var language = document.documentElement.lang;
    try { if (window.qwenEnhance && typeof window.qwenEnhance.lang === "function") language = window.qwenEnhance.lang(); } catch (_) {}
    return language === "th" ? th : en;
  }
  function abortError(message) { var e = new Error(message || "Connection recovery paused"); e.name = "AbortError"; return e; }
  function fatal(message, code) { var e = new Error(message); e.recoveryTerminal = true; e.status = code || 0; return e; }
  function wake() { wakeups.forEach(function (f) { f(); }); wakeups.clear(); }
  function delay(ms, interruptible) {
    return new Promise(function (resolve) {
      var done = false, timer = setTimeout(finish, ms);
      function finish() { if (done) return; done = true; clearTimeout(timer); wakeups.delete(finish); resolve(); }
      if (interruptible !== false) wakeups.add(finish);
    });
  }
  async function guarded(op, promise, timeout) {
    var controller = op.controller, timer = null, listener = null;
    var interruption = new Promise(function (_, reject) {
      listener = function () { reject(abortError("The connection was interrupted")); };
      if (controller.signal.aborted) { listener(); return; }
      controller.signal.addEventListener("abort", listener, {once: true});
      timer = setTimeout(function () {
        reject(new Error("The connection stopped responding"));
        controller.abort();
        if (op.reader) { try { op.reader.cancel().catch(function () {}); } catch (_) {} }
      }, Math.max(1, timeout));
    });
    try { return await Promise.race([promise, interruption]); }
    finally { clearTimeout(timer); if (listener) controller.signal.removeEventListener("abort", listener); }
  }
  function update(op, status) {
    op.state = status;
    var r = records[op.id];
    if (r) { r.state = status; r.offset = op.offset; r.updatedAt = Date.now(); save(); }
  }
  function notice(op, message) { notices[op.id] = {project: op.project, chat: op.chat, message: message}; paint(); }
  function clearNotice(op) { delete notices[op.id]; paint(); }
  function paint() {
    if (!document.body || !document.createElement) return;
    var r = route(), s = state(), visible = Object.keys(notices).filter(function (id) {
      return notices[id].project === s.project && notices[id].chat === r.id;
    });
    if (!visible.length) { if (banner) banner.hidden = true; return; }
    if (!banner) {
      banner = document.createElement("div"); banner.className = "qw-recovery-status";
      banner.setAttribute("role", "status"); banner.setAttribute("aria-live", "polite");
      banner.style.cssText = "position:fixed;bottom:7rem;left:50%;transform:translateX(-50%);z-index:90;max-width:min(90vw,52rem);padding:.65rem 1rem;border:1px solid #64748b;border-radius:.6rem;background:var(--background,#172033);color:var(--foreground,#fff);font-size:.85rem;box-shadow:0 4px 18px #0004";
      document.body.appendChild(banner);
    }
    banner.textContent = notices[visible[visible.length - 1]].message; banner.hidden = false;
  }
  function lease(op) {
    try {
      var key = LEASE + op.id, now = Date.now(), found = JSON.parse(window.localStorage.getItem(key) || "null");
      if (found && found.owner !== owner && found.until > now) return false;
      window.localStorage.setItem(key, JSON.stringify({owner: owner, until: now + LEASE_MS}));
      return JSON.parse(window.localStorage.getItem(key)).owner === owner;
    } catch (_) { return true; } // Server operation identity still prevents duplicate execution.
  }
  function release(op) {
    try { var key = LEASE + op.id, v = JSON.parse(window.localStorage.getItem(key) || "null"); if (v && v.owner === owner) window.localStorage.removeItem(key); } catch (_) {}
  }
  function allowed(op) {
    if (op.stopped || stops[identity(op)]) throw abortError("Stopped by the user");
    if (op.superseded || op.detached || pageLeaving) throw abortError("The original response is no longer attached");
    var s = state(), r = route();
    return !!(s.on && !s.stopped && !isPlan() && s.project === op.project && r.name === "chat" && r.id === op.chat &&
      (!window.navigator || window.navigator.onLine !== false) && lease(op));
  }
  async function ready(op, backoff) {
    if (backoff) await delay(backoff, false);
    while (!allowed(op)) {
      update(op, "paused"); notice(op, text("Connection recovery is waiting for this chat and a network connection.", "กำลังรอเปิดแชตนี้และเชื่อมต่อเครือข่ายเพื่อทำงานต่อ"));
      await delay(1000);
    }
  }
  async function verifyBranch(op) {
    var api = window.qwenRecoveryHistory, permitted = false, timer = null;
    if (op.helper && api && typeof api.canAttach === "function") {
      try {
        permitted = await Promise.race([api.canAttach(op.helper), new Promise(function (resolve) { timer = setTimeout(function () { resolve(false); }, 2000); })]);
      } catch (_) { permitted = false; }
      finally { clearTimeout(timer); }
    }
    if (!permitted) throw fatal(text("The chat branch changed or cannot be verified. The saved task was not repeated.", "แชตเปลี่ยนแขนงหรือยังตรวจสอบไม่ได้ ระบบเก็บงานเดิมไว้และไม่ได้สั่งงานซ้ำ"));
    if (op.stopped || op.superseded || op.detached || pageLeaving || stops[identity(op)]) throw abortError();
  }
  function safeTarget(input, init) {
    var raw = typeof input === "string" ? input : input && input.url, url;
    try { url = new URL(raw, location.href); } catch (_) { return null; }
    var method = String(init && init.method || input && input.method || "GET").toUpperCase();
    if (method !== "POST" || url.search || url.hash || url.username || url.password) return null;
    if (url.origin === location.origin && (url.pathname === "/v1/chat/completions" || url.pathname === "/tools")) {
      return {url: url.href, kind: url.pathname === "/tools" ? "tools" : "chat", original: null};
    }
    var s = state(), local = (url.hostname === "127.0.0.1" || url.hostname === "localhost" || url.hostname === "[::1]") && url.protocol === "http:";
    if (!local || !s.project) return null;
    var path = url.pathname, encoded = encodeURIComponent(s.project);
    if (url.port === "8791" && path === "/mcp") return {url: location.origin + "/_qwen/recovery/mcp/web", kind: "mcp", original: url.href};
    if (url.port === "8792" && (path === "/fast/" + encoded || path === "/mcp/" + encoded)) return {url: location.origin + "/_qwen/recovery/mcp/local", kind: "mcp", original: url.href};
    return null;
  }
  async function specification(input, init, target) {
    var req = typeof Request === "function" && input instanceof Request ? input : null;
    var body = init && init.body !== undefined ? init.body : req ? await req.clone().text() : null;
    if (typeof body !== "string") return null;
    var doc; try { doc = JSON.parse(body); } catch (_) { return null; }
    if (target.kind === "mcp" && (!doc || doc.method !== "tools/call")) return null;
    var headers = new Headers(init && init.headers !== undefined ? init.headers : req ? req.headers : undefined);
    var s = state(), r = route();
    var conv = (headers.get("X-Conversation-Id") || "").split("::")[0].trim();
    if (!s.on || s.stopped || isPlan() || !s.project || r.name !== "chat" || !r.id || (conv && conv !== r.id)) return null;
    if (stops[s.project + "|" + r.id]) return null;
    return {id: uuid(), project: s.project, chat: conv || r.id, kind: target.kind, url: target.url, target: target.original,
      body: body, headers: headers, signal: init && init.signal || req && req.signal, offset: 0, createdAt: Date.now(),
      attempts: 0, state: "starting", stopped: false, superseded: false, detached: false, reader: null, controller: null,
      terminal: false, eventText: "", decoder: new TextDecoder(), helper: null};
  }
  function persisted(op) {
    // Prompts, command arguments, cookies and authentication never enter this store.
    return {id: op.id, project: op.project, chat: op.chat, kind: op.kind, offset: op.offset, state: op.state,
      createdAt: op.createdAt, updatedAt: Date.now(), binding: op.helper, requestHash: op.helper && op.helper.bodyHash || null};
  }
  async function capture(op) {
    var api = window.qwenRecoveryHistory, timer = null;
    if (api && typeof api.capture === "function") {
      try {
        op.helper = await Promise.race([api.capture({id: op.id, kind: op.kind, project: op.project, chat: op.chat, body: op.body, createdAt: op.createdAt}),
          new Promise(function (resolve) { timer = setTimeout(function () { resolve(null); }, 2000); })]);
      } catch (_) {}
      finally { clearTimeout(timer); }
    }
    records[op.id] = persisted(op); save();
  }
  function observeSSE(op, bytes, flush) {
    if (!op.sse) return;
    op.eventText += op.decoder.decode(bytes || new Uint8Array(), {stream: !flush});
    var lines = op.eventText.split(/\r?\n/); op.eventText = lines.pop();
    if (flush && op.eventText) { lines.push(op.eventText); op.eventText = ""; }
    lines.forEach(function (line) {
      if (line.indexOf("data:") !== 0) return;
      var value = line.slice(5).trim(); if (value === "[DONE]") { op.terminal = true; return; }
      try {
        var event = JSON.parse(value);
        if (event.done === true || (Array.isArray(event.choices) && event.choices.some(function (c) { return c.finish_reason != null; }))) op.terminal = true;
        // JSON-RPC replies over Streamable HTTP complete with result/error, no [DONE].
        if (op.kind === "mcp" && event.jsonrpc === "2.0" && (Object.prototype.hasOwnProperty.call(event, "result") || Object.prototype.hasOwnProperty.call(event, "error"))) op.terminal = true;
      } catch (_) {}
    });
    if (op.eventText.length > 2 * 1024 * 1024) op.eventText = op.eventText.slice(-1024 * 1024);
  }
  async function connect(op) {
    var backoff = 0;
    for (;;) {
      await ready(op, backoff); update(op, op.attempts ? "reconnecting" : "running");
      var headers = new Headers(op.headers);
      headers.set("X-Qwen-Recovery-ID", op.id); headers.set("X-Qwen-Recovery-Offset", String(op.offset));
      if (!headers.get("X-Conversation-Id")) headers.set("X-Conversation-Id", op.chat);
      if (op.target) headers.set("X-Qwen-Recovery-Target", op.target);
      op.controller = new AbortController();
      try {
        if (op.attempts || op.mustValidateBranch) await verifyBranch(op);
        var response = await guarded(op, inner(op.url, {method: "POST", body: op.body, headers: headers, signal: op.controller.signal,
          credentials: "same-origin", cache: "no-store"}), HEADER_MS);
        if (!response.ok) {
          if ([408, 429, 500, 502, 503, 504].indexOf(response.status) >= 0) {
            try { if (response.body) await response.body.cancel(); } catch (_) {}
            if (response.headers.get("X-Qwen-Recovery-ID")) throw fatal(text("The original task saved an error response and needs review. It was not repeated.", "งานเดิมมีข้อผิดพลาดที่ต้องตรวจสอบ ระบบเก็บผลไว้และไม่ได้สั่งงานซ้ำ"), response.status);
            throw new Error("The recovery service is temporarily unavailable");
          }
          // A retained failed operation may have already produced effects. Never replace its ID.
          throw fatal(text("Recovery stopped: HTTP " + response.status + ". The original action was retained and was not repeated.", "พักการกู้คืนเนื่องจากข้อผิดพลาด HTTP " + response.status + " ระบบเก็บงานเดิมไว้และไม่ได้สั่งงานซ้ำ"), response.status);
        }
        var returned = response.headers.get("X-Qwen-Recovery-Offset");
        if (returned === null || !/^\d+$/.test(returned) || Number(returned) !== op.offset) {
          throw fatal(text("The recovery byte position did not match. The action was not repeated.", "ตำแหน่งข้อมูลที่กู้คืนไม่ตรงกัน ระบบพักไว้และไม่ได้สั่งงานซ้ำ"), 409);
        }
        if (!response.body) throw fatal("The recovery response has no readable body.");
        op.sse = /text\/event-stream/i.test(response.headers.get("Content-Type") || "");
        op.reader = response.body.getReader(); clearNotice(op); return response;
      } catch (e) {
        if (e.recoveryTerminal || op.stopped || op.superseded || op.detached || pageLeaving || stops[identity(op)]) throw e;
        op.attempts++; backoff = Math.min(15000, 500 * Math.pow(2, Math.min(op.attempts - 1, 5)));
        notice(op, text("Connection interrupted. Reconnecting to the same task…", "การเชื่อมต่อขัดข้อง กำลังเชื่อมต่องานเดิมอีกครั้ง…"));
      }
    }
  }
  function cleanup(op, complete) {
    if (op.signal && op.abortListener) op.signal.removeEventListener("abort", op.abortListener);
    release(op); operations.delete(op.id);
    if (complete) { delete records[op.id]; save(); clearNotice(op); }
  }
  async function managed(op, input, init) {
    operations.set(op.id, op); await capture(op);
    // The native UI also calls /tools to browse its working directory. Only
    // actual agent calls have a matching pending call in native chat history.
    // Leave unbound UI requests on their original transport and never create
    // restore markers or a continuation for them.
    if (op.kind !== "chat" && !op.helper) {
      cleanup(op, true);
      if (op.stopped || op.superseded || op.detached || pageLeaving || stops[identity(op)]) throw abortError();
      return inner(input, init);
    }
    op.abortListener = function () {
      op.mustValidateBranch = true;
      if (op.controller) op.controller.abort();
      if (op.reader) { try { op.reader.cancel().catch(function () {}); } catch (_) {} }
      op.transportAborted = true; wake();
    };
    if (op.signal) op.signal.addEventListener("abort", op.abortListener);
    var first;
    try { first = await connect(op); }
    catch (e) { update(op, op.stopped ? "stopped" : op.superseded ? "superseded" : "needs_attention"); if (!op.stopped && !op.superseded && !pageLeaving) notice(op, e.message); else clearNotice(op); cleanup(op, false); throw e; }
    var stream = new ReadableStream({
      pull: async function (out) {
        for (;;) {
          try {
            if (op.stopped || stops[identity(op)] || op.superseded || op.detached || pageLeaving) throw abortError();
            if (op.transportAborted) { op.transportAborted = false; op.reader = null; }
            if (!op.reader) await connect(op);
            var part = await guarded(op, op.reader.read(), IDLE_MS);
            if (op.transportAborted) { op.transportAborted = false; op.reader = null; continue; }
            if (part.done) {
              observeSSE(op, null, true);
              if (op.sse && !op.terminal) throw fatal(text("The saved response ended before completion. The task needs review; no action was repeated.", "คำตอบที่บันทึกไว้ยังไม่สมบูรณ์ ต้องตรวจผลก่อนทำงานต่อ ระบบไม่ได้สั่งงานซ้ำ"));
              // Native IndexedDB persistence happens after the reader sees EOF.
              // Keep the journal marker until exact durable content is acknowledged.
              update(op, "delivered"); cleanup(op, false); clearNotice(op); out.close();
              setTimeout(restorePending, 250); return;
            }
            var bytes = part.value instanceof Uint8Array ? part.value : new Uint8Array(part.value);
            if (op.mustValidateBranch) { await verifyBranch(op); op.mustValidateBranch = false; }
            observeSSE(op, bytes, false); op.offset += bytes.byteLength; update(op, "running"); lease(op); out.enqueue(bytes); return;
          } catch (e) {
            if (e.recoveryTerminal || op.stopped || op.superseded || op.detached || pageLeaving || stops[identity(op)]) {
              update(op, op.stopped || stops[identity(op)] ? "stopped" : op.superseded ? "superseded" : "needs_attention");
              if (!op.stopped && !op.superseded && !stops[identity(op)] && !pageLeaving) notice(op, e.message); else clearNotice(op);
              cleanup(op, false); out.error(e); return;
            }
            op.reader = null; op.attempts++;
            notice(op, text("Connection interrupted. Reconnecting to the same task…", "การเชื่อมต่อขัดข้อง กำลังเชื่อมต่องานเดิมอีกครั้ง…"));
            await delay(Math.min(15000, 500 * Math.pow(2, Math.min(op.attempts - 1, 5))), false);
          }
        }
      },
      cancel: function () {
        op.detached = true;
        if (op.controller) op.controller.abort();
        if (op.reader) { try { op.reader.cancel().catch(function () {}); } catch (_) {} }
        update(op, stops[identity(op)] ? "stopped" : "pending"); cleanup(op, false); wake();
      }
    });
    return new Response(stream, {status: first.status, statusText: first.statusText, headers: first.headers});
  }
  window.fetch = function (input, init) {
    var target = safeTarget(input, init);
    if (!target) return inner(input, init);
    return specification(input, init, target).then(function (op) { return op ? managed(op, input, init) : inner(input, init); });
  };

  function nativeStop(event) {
    if (!event || !event.isTrusted || (event.type === "keydown" && event.key !== "Enter" && event.key !== " ")) return false;
    var button = event.target && event.target.closest && event.target.closest("button");
    if (!button || button.closest(".markdown-content,.chat-message-user,pre,code,[role='dialog']") ||
      (button.classList && (button.classList.contains("qw-auto-continue") || button.classList.contains("qw-mic")))) return false;
    var form = button.closest(".chat-screen-form-wrapper form"), card = button.closest(".agentic-content");
    var value = [button.textContent, button.getAttribute("aria-label"), button.getAttribute("title")].filter(Boolean).join(" ").trim();
    if (button.classList && button.classList.contains("stop-button")) return true;
    return !!((form || card) &&
      /^(?:Stop(?: generation)?|หยุด(?:สร้างคำตอบ)?)(?:\s+(?:Stop(?: generation)?|หยุด(?:สร้างคำตอบ)?))*$/i.test(value));
  }
  function stop(event) {
    if (!nativeStop(event)) return;
    var s = state(), r = route(); if (!s.project || !r.id) return;
    stops[s.project + "|" + r.id] = Date.now(); saveStops();
    try { window.sessionStorage.removeItem(REFRESH_KEY); } catch (_) {}
    try { if (window.qwenRecoveryHistory && window.qwenRecoveryHistory.invalidate) window.qwenRecoveryHistory.invalidate(r.id); } catch (_) {}
    Object.keys(records).forEach(function (id) {
      var record = records[id]; if (record.project !== s.project || record.chat !== r.id || record.state === "stopped") return;
      record.state = "stopped";
      var op = operations.get(id); if (op) { op.stopped = true; if (op.controller) op.controller.abort(); }
      inner("/_qwen/recovery/" + encodeURIComponent(id) + "/cancel", {method: "POST", credentials: "same-origin", cache: "no-store"}).catch(function () {});
      delete notices[id];
    });
    save(); paint(); wake();
  }
  // The open chat is still working: its composer shows the Stop control for the whole agent run
  // (including tool calls and permission prompts). Labels may be translated (Thai) by enhance.
  function chatRunning(form) {
    var buttons = form && typeof form.querySelectorAll === "function" ? form.querySelectorAll("button") : [];
    for (var i = 0; i < buttons.length; i++) {
      var b = buttons[i];
      if ((b.closest && b.closest(".qw-queue")) || (b.classList && b.classList.contains("qw-auto-continue"))) continue;
      var sr = b.querySelector && b.querySelector(".sr-only");
      var labels = b.getAttribute ? [b.getAttribute("data-qw-tx"), b.getAttribute("aria-label"), sr && sr.textContent] : [];
      for (var j = 0; j < labels.length; j++) {
        if (/^(?:stop|stop generation|skip reasoning|หยุด|หยุดสร้างคำตอบ|ข้ามการคิด)$/i.test(String(labels[j] || "").replace(/[\u2060\u200b]/g, "").trim())) return true;
      }
    }
    return false;
  }
  function humanSend(event) {
    if (!event || !event.isTrusted) return;
    var target = event.target, form = target && target.closest && target.closest(".chat-screen-form-wrapper form");
    if (!form) return;
    if (event.type === "keydown" && (target.tagName !== "TEXTAREA" || event.key !== "Enter" || event.shiftKey || event.isComposing)) return;
    if (event.type === "click" && !(target.closest && target.closest('button[type="submit"]'))) return;
    // A message sent while the reply is still running is queued by the WebUI (or by message-queue.js);
    // the running reply must keep streaming, so nothing is superseded, aborted or invalidated here.
    if (chatRunning(form)) return;
    noteHumanSend();
  }
  // Bookkeeping for a new user turn: also called by message-queue.js when it sends a queued message.
  function noteHumanSend() {
    var s = state(), r = route(); if (!s.project || !r.id) return;
    delete stops[s.project + "|" + r.id]; saveStops();
    try { window.sessionStorage.removeItem(REFRESH_KEY); } catch (_) {}
    try { if (window.qwenRecoveryHistory && window.qwenRecoveryHistory.invalidate) window.qwenRecoveryHistory.invalidate(r.id); } catch (_) {}
    Object.keys(records).forEach(function (id) { if (records[id].project === s.project && records[id].chat === r.id) { records[id].state = "superseded"; delete notices[id]; } });
    save(); paint();
    operations.forEach(function (op) { if (op.project === s.project && op.chat === r.id) { op.superseded = true; if (op.controller) op.controller.abort(); update(op, "superseded"); } });
    wake();
  }
  function nativeBranchChange(event) {
    if (!event || !event.isTrusted || (event.type === "keydown" && event.key !== "Enter" && event.key !== " ")) return;
    var control = event.target && event.target.closest && event.target.closest("button,[role='menuitem']");
    if (!control || control.closest(".markdown-content,pre,code,.qw-review")) return;
    var labels = [control.textContent, control.getAttribute("aria-label"), control.getAttribute("title")];
    var action = /^(?:Regenerate|Edit(?: message)?|Delete(?: message| chat| conversation)?|Previous version|Next version|Fork(?: conversation)?|สร้างคำตอบใหม่|แก้ไข(?:ข้อความ)?|ลบ(?:ข้อความ|แชต|บทสนทนา)?|เวอร์ชันก่อนหน้า|เวอร์ชันถัดไป|แยก(?:เป็น)?แชตใหม่)$/i;
    if (!labels.some(function (label) { return action.test(String(label || "").trim()); })) return;
    if (!control.closest(".chat-message,.chat-messages,[role='menu'],[role='dialog']") && control.getAttribute("role") !== "menuitem") return;
    var s = state(), r = route(); if (!s.project || !r.id) return;
    try { if (window.qwenRecoveryHistory && window.qwenRecoveryHistory.invalidate) window.qwenRecoveryHistory.invalidate(r.id); } catch (_) {}
    try { window.sessionStorage.removeItem(REFRESH_KEY); } catch (_) {}
    operations.forEach(function (op) {
      if (op.project !== s.project || op.chat !== r.id) return;
      op.detached = true; update(op, "needs_attention"); if (op.controller) op.controller.abort();
    });
    wake();
  }
  ["pointerdown", "click", "keydown"].forEach(function (name) { window.addEventListener(name, stop, true); });
  ["pointerdown", "click", "keydown"].forEach(function (name) { window.addEventListener(name, nativeBranchChange, true); });
  window.addEventListener("click", function (event) {
    var chip = event.isTrusted && event.target && event.target.closest && event.target.closest(".qw-auto-continue");
    if (!chip) return;
    var before = state().on;
    Promise.resolve().then(function () {
      var s = state(), r = route();
      if (before === false && s.on && !s.stopped && s.project && r.id) { delete stops[s.project + "|" + r.id]; saveStops(); wake(); }
    });
  }, true);
  ["click", "keydown", "submit"].forEach(function (name) { window.addEventListener(name, humanSend, true); });
  ["online", "offline", "hashchange", "pageshow", "storage"].forEach(function (name) { window.addEventListener(name, function () { if (name === "pageshow") pageLeaving = false; paint(); wake(); }); });
  window.addEventListener("pagehide", function () {
    pageLeaving = true; operations.forEach(function (op) { update(op, "pending"); if (op.controller) op.controller.abort(); release(op); }); save(); wake();
  });

  async function getStatus(record) {
    var response = await inner("/_qwen/recovery/" + encodeURIComponent(record.id), {credentials: "same-origin", cache: "no-store"});
    if (!response.ok) throw fatal("The interrupted task cannot be identified safely. It was not repeated.", response.status);
    return response.json();
  }
  async function savedResult(record) {
    var response = await inner("/_qwen/recovery/" + encodeURIComponent(record.id) + "/result", {credentials: "same-origin", cache: "no-store"});
    if (!response.ok || response.headers.get("X-Qwen-Recovery-Offset") !== "0") throw fatal("The saved response cannot be restored safely.", response.status);
    var reader = response.body.getReader(), bytes = [], size = 0;
    for (;;) { var item = await reader.read(); if (item.done) break; size += item.value.byteLength; if (size > MAX_RESULT) { reader.cancel(); throw fatal("The saved result needs manual review because it is too large."); } bytes.push(item.value); }
    var merged = new Uint8Array(size), offset = 0; bytes.forEach(function (part) { merged.set(part, offset); offset += part.byteLength; });
    return {text: new TextDecoder().decode(merged), contentType: response.headers.get("Content-Type") || "", status: response.status, size: size};
  }
  async function restorePending() {
    if (restoring || pageLeaving) return;
    var s = state(), r = route(); if (!s.on || s.stopped || !s.project || r.name !== "chat" || !r.id || isPlan() || stops[s.project + "|" + r.id]) return;
    restoring = true;
    try {
      var ids = Object.keys(records).sort(function (a, b) { return records[a].createdAt - records[b].createdAt; });
      var needsRefresh = false, continuation = null;
      for (var i = 0; i < ids.length; i++) {
        var record = records[ids[i]];
        if (!record || operations.has(record.id) || record.project !== s.project || record.chat !== r.id || /^(stopped|superseded)$/.test(record.state) || !lease(record)) continue;
        try {
          var status = await getStatus(record);
          if (status.state === "completed" || status.state === "complete" || status.state === "done") {
            var helper = window.qwenRecoveryHistory;
            if (!helper || typeof helper.restore !== "function") {
              notice(record, text("The interrupted response was saved. Reopen this chat to restore it, or review the saved task.", "บันทึกคำตอบที่ขาดช่วงไว้แล้ว โปรดเปิดแชตนี้ใหม่เพื่อกู้คืนหรือตรวจงานที่บันทึกไว้")); continue;
            }
            var completion = await savedResult(record);
            if (typeof helper.acknowledge === "function" && await helper.acknowledge(record, completion)) {
              delete records[record.id]; save(); clearNotice(record); continue;
            }
            var result = await helper.restore(record, completion);
            if (result && result.restored) {
              delete records[record.id]; save(); clearNotice(record);
              needsRefresh = needsRefresh || !!result.reload;
              continuation = result.continue && result.continuation || null;
            }
            else notice(record, result && result.pendingPermission ? text("Recovered results were saved. A tool still needs your approval.", "กู้คืนผลที่ตรวจสอบได้แล้ว แต่ยังมีเครื่องมือที่รออนุญาตจากคุณ") : text("The saved response needs review before it can be merged into this chat.", "ต้องตรวจผลที่บันทึกไว้ก่อนรวมกลับเข้าแชตนี้"));
          } else if (status.state === "running" || status.state === "pending" || status.state === "starting") {
            notice(record, text("The original task is still running. Its result will be restored when it finishes.", "งานเดิมยังทำงานอยู่ จะกู้คืนคำตอบเมื่อเสร็จแล้ว"));
          } else {
            update(record, "needs_attention"); notice(record, text("The previous task's outcome needs review. It was not repeated automatically.", "ต้องตรวจผลของงานก่อนหน้า ระบบไม่ได้สั่งงานเดิมซ้ำโดยอัตโนมัติ"));
          }
        } catch (e) { notice(record, e.recoveryTerminal ? e.message : text("Waiting to reconnect to the saved task…", "กำลังรอเชื่อมต่องานที่บันทึกไว้…")); }
        finally { release(record); }
      }
      if (needsRefresh && !Object.keys(records).some(function (id) { var entry = records[id]; return unresolved(entry) && entry.project === s.project && entry.chat === r.id; })) {
        try { window.sessionStorage.setItem(REFRESH_KEY, JSON.stringify({project: s.project, chat: r.id, ticket: continuation, at: Date.now(), phase: "refresh"})); } catch (_) {}
        await refreshNative();
      }
    } finally { restoring = false; }
  }
  function idleComposer() {
    if (!document.querySelector) return null;
    var form = document.querySelector(".chat-screen-form-wrapper form.conversation-chat-form");
    var area = form && form.querySelector("textarea"), button = form && form.querySelector('button[type="submit"]');
    if (!form || !area || !button || String(area.value || "").trim()) return null;
    if (document.querySelector(".qw-review,[role='dialog'][open]")) return null;
    try { if (window.qwenEnhance.isStreaming()) return null; } catch (_) { return null; }
    return {form: form, area: area, button: button};
  }
  async function refreshNative() {
    if (continuing || pageLeaving || operations.size) return;
    var pending = read(REFRESH_KEY, null), s = state(), r = route();
    if (!pending || pending.project !== s.project || pending.chat !== r.id || r.name !== "chat" || !s.on || s.stopped || isPlan() || stops[s.project + "|" + r.id]) return;
    if (Date.now() - pending.at > 30 * 60 * 1000) { try { window.sessionStorage.removeItem(REFRESH_KEY); } catch (_) {} return; }
    var composer = idleComposer(); if (!composer) return;
    if (Object.keys(records).some(function (id) { return unresolved(records[id]) && records[id].project === s.project && records[id].chat === r.id; })) return;
    continuing = true;
    try {
      if (pending.phase === "refresh") {
        if (typeof location.reload !== "function") return;
        pending.phase = "continue";
        try { window.sessionStorage.setItem(REFRESH_KEY, JSON.stringify(pending)); } catch (_) { return; }
        pageLeaving = true; location.reload(); return;
      }
      if (!pending.ticket) { window.sessionStorage.removeItem(REFRESH_KEY); return; }
      var api = window.qwenRecoveryHistory;
      if (!api || typeof api.canContinue !== "function" || !await api.canContinue(pending.ticket)) return;
      // Validate again after the asynchronous IndexedDB read. Never overwrite a draft.
      s = state(); r = route(); composer = idleComposer();
      if (!composer || !s.on || s.stopped || isPlan() || r.id !== pending.chat || s.project !== pending.project || stops[s.project + "|" + r.id]) return;
      var prompt = text("Continue the interrupted task from the recovered result. Verify any uncertain action before repeating it.", "ทำงานที่ขาดช่วงต่อจากผลที่กู้คืนแล้ว ตรวจผลของงานที่ไม่แน่ใจก่อนสั่งซ้ำ");
      var setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
      setter.set.call(composer.area, prompt); composer.area.dispatchEvent(new Event("input", {bubbles: true}));
      // Persist the one-shot consumption before dispatching a native send.
      window.sessionStorage.removeItem(REFRESH_KEY);
      await Promise.resolve();
      if (composer.button.disabled || composer.button.getAttribute("aria-disabled") === "true") {
        // A disabled composer keeps the text visible for the user to send; no second automatic send.
        return;
      }
      if (typeof composer.form.requestSubmit === "function") composer.form.requestSubmit(composer.button);
      else composer.button.click();
    } finally { continuing = false; }
  }
  function tick() {
    var s = state(), r = route();
    if (lastOn === false && s.on && !s.stopped && s.project && r.id) { delete stops[s.project + "|" + r.id]; saveStops(); }
    lastOn = !!s.on;
    operations.forEach(function (op) { lease(op); }); paint(); wake(); restorePending(); refreshNative();
  }
  window.qwenRecovery = {
    version: 1,
    status: function () { return {active: operations.size, pending: Object.keys(records).length, operations: Object.keys(records).map(function (id) { var r = records[id]; return {id: id, project: r.project, chat: r.chat, kind: r.kind, state: r.state, offset: r.offset}; })}; },
    restore: restorePending,
    resume: refreshNative,
    noteSend: function () { var f = document.querySelector(".chat-screen-form-wrapper form"); if (!chatRunning(f)) noteHumanSend(); }
  };
  setInterval(tick, 3000);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", tick, {once: true}); else setTimeout(tick, 0);
})();
