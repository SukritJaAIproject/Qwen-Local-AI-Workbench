/* message-queue.js — ถามต่อได้ระหว่างที่ Qwen กำลังทำงาน (คิวข้อความของแชต)
 *
 * WebUI (b10984) มีช่องรอส่งของตัวเองแค่ช่องเดียว และส่งข้อความนั้นแทรกเข้าไป "ทันทีหลังขั้นที่กำลังทำ"
 * (ข้ามเครื่องมือที่เหลือของรอบนั้น) — ข้อความที่สองทับข้อความแรกหาย และงานยาวหลายขั้นถูกตัดกลางทาง
 * ไฟล์นี้จึงทำคิวของเราเอง:
 *   * ระหว่างที่แชตนี้กำลังทำงาน (ปุ่มหยุดอยู่ในกล่องพิมพ์) กด Enter = เข้าคิว ไม่ส่งแทรก ไม่หยุดงานเดิม
 *   * คิวส่งให้เองทีละข้อความตามลำดับ เมื่องานจบแล้วนิ่งอย่างน้อย IDLE_MS และช่องพิมพ์ว่าง
 *     (ไม่ส่งระหว่างที่ระบบกู้การเชื่อมต่อยังค้างงานของแชตนี้อยู่ หรือมีหน้าต่าง/การ์ดรอผู้ใช้)
 *   * กดหยุด = พักคิวของแชตนั้น (ไม่ส่งอะไรเองหลังหยุด) จนผู้ใช้กด "ส่งต่อ" หรือส่งข้อความใหม่
 *   * แต่ละข้อความในคิว: แทรกตอนนี้ (ใช้ช่องรอส่งของ WebUI = Qwen เห็นหลังขั้นที่กำลังทำ) / แก้ไข / ลบ
 *   * มีไฟล์แนบในกล่องพิมพ์ = ปล่อยให้ WebUI จัดการเอง (คิวเก็บได้แค่ข้อความ)
 * คิวอยู่ใน sessionStorage ของแท็บนี้ (รีโหลดแล้วยังอยู่ ปิดแท็บแล้วหาย) แยกตามโปรเจกต์ + แชต
 * ต้องโหลดก่อน auto-recovery.js: ตัวดัก Enter ของเราหยุด event ก่อนถึงตัวกู้การเชื่อมต่อ
 * (ตัวนั้นถือว่าการส่งใหม่ = เลิกงานเดิม แล้วตัดสตรีมที่กำลังตอบอยู่)
 */
(function () {
  "use strict";
  if (window.qwenQueue) return;

  var KEY = "qwen-message-queue-v1";
  var IDLE_MS = Number(window.QWEN_QUEUE_IDLE_MS) || 1500;     // งานจบแล้วต้องนิ่งเท่านี้ก่อนส่งข้อความถัดไป
  var START_MS = Number(window.QWEN_QUEUE_START_MS) || 10000;  // ส่งแล้วต้องเห็นงานเริ่มภายในเวลานี้
  var TICK_MS = 300, MAX_ITEMS = 30, MAX_TEXT = 100000;
  var REFRESH_KEY = "qwen-stream-recovery-refresh-v1";        // ตัวกู้การเชื่อมต่อกำลังจะรีโหลด/ทำต่อ (auto-recovery.js)

  var store = load();             // {items: {key: [{id, text, at}]}, paused: {key: true}}
  var idleSince = 0, sending = null, dispatching = false, bypass = 0, panel = null, live = null, lastSig = "";

  /* ---- ข้อมูลรอบตัว ---------------------------------------------------------- */
  function enh() { return window.qwenEnhance || null; }
  function lang() {
    try { var l = enh() && enh().lang(); if (l === "en" || l === "th") return l; } catch (e) {}
    return document.documentElement.lang === "en" ? "en" : "th";
  }
  function T(th, en) { return lang() === "en" ? en : th; }
  function route() {
    try { var r = enh() && enh().route(); if (r) return r; } catch (e) {}
    var m = /^#\/chat\/([^/?]+)/.exec(location.hash || "");
    return m ? { name: "chat", id: decodeURIComponent(m[1]) } : { name: "other", id: null };
  }
  function project() {
    try {
      var s = window.parent && window.parent !== window ? window.parent.qwenShell : window.qwenShell;
      var slug = s && s.project && s.project.slug;
      return typeof slug === "string" ? slug : "";
    } catch (e) { return ""; }
  }
  function chatKey() {
    var r = route();
    return r.name === "chat" && r.id ? project() + "|" + r.id : "";
  }
  function form() { return document.querySelector(".chat-screen-form-wrapper form.conversation-chat-form"); }
  function textarea() { var f = form(); return f ? f.querySelector("textarea") : null; }
  function inputArea() { var f = form(); return f ? f.querySelector('[data-slot="input-area"]') : null; }
  function clean(s) { return String(s || "").replace(/[\u2060\u200b]/g, "").replace(/\s+/g, " ").trim(); }
  var STOP_RE = /^(?:stop|stop generation|skip reasoning|หยุด|หยุดสร้างคำตอบ|ข้ามการคิด)$/i;
  function buttonLabel(b) {
    var sr = b.querySelector(".sr-only");
    return [b.getAttribute("data-qw-tx"), b.getAttribute("aria-label"), sr && sr.textContent, b.textContent]
      .map(clean).filter(Boolean);
  }
  /* แชตที่เปิดอยู่กำลังทำงาน: ปุ่มหยุดของกล่องพิมพ์ (WebUI คงปุ่มนี้ไว้ตลอดงาน รวมช่วงรออนุญาตเครื่องมือ
     และช่วงระหว่างรอบของเอเจนต์) — ไม่ดู .stop-button ในรายการแชต เพราะนั่นอาจเป็นของแชตอื่น */
  function busy() {
    var f = form();
    if (!f) return false;
    var bs = f.querySelectorAll("button");
    for (var i = 0; i < bs.length; i++) {
      var b = bs[i];
      if (b.closest(".qw-queue") || b.classList.contains("qw-auto-continue")) continue;
      var labels = buttonLabel(b);
      for (var j = 0; j < labels.length; j++) if (STOP_RE.test(labels[j])) return true;
    }
    return false;
  }
  function hasAttachments() {
    var a = inputArea();
    return !!(a && a.querySelector('[data-qw-tx="Remove"], button[aria-label="Remove"], button[aria-label="ลบ"]'));
  }
  function pickerOpen() {
    var f = form();
    return !!((f && f.querySelector('[data-slot="popover-trigger"][data-state="open"]')) ||
      document.querySelector('[data-slot="popover-content"][data-state="open"]'));
  }
  function nativePending() {
    return !!document.querySelector('[role="group"][aria-label="Pending user message"], [role="group"][data-qw-tx="Pending user message"], [role="group"][aria-label="ข้อความที่รอส่ง"]');
  }
  function dialogOpen() {
    var ds = document.querySelectorAll('[role="dialog"], [role="alertdialog"], .qw-review');
    for (var i = 0; i < ds.length; i++) {
      var d = ds[i];
      if (d.closest(".qw-queue")) continue;
      var r = d.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) return true;
    }
    return false;
  }
  /* ตัวกู้การเชื่อมต่อยังถืองานของแชตนี้อยู่ → "recovery" (กำลังต่อใหม่ / กำลังจะรีโหลดเพื่อทำต่อ) หรือ
     "review" (งานขาดช่วงแล้วรอผู้ใช้ตรวจ) — ทั้งสองแบบคิวไม่ส่งเอง (กด "ส่งเลย" ได้เสมอ)
     "delivered" = สตรีมจบครบแล้ว รอแค่ยืนยันว่าบันทึกลงแชตแล้ว (การส่งของคนตามปกติก็ไม่รอสถานะนี้) */
  function recoveryPending(key) {
    var chat = key.split("|").slice(1).join("|");
    try {
      var p = JSON.parse(sessionStorage.getItem(REFRESH_KEY) || "null");
      if (p && p.chat === chat) return "recovery";
    } catch (e) {}
    var why = "";
    try {
      var st = window.qwenRecovery && window.qwenRecovery.status();
      (st && st.operations || []).forEach(function (o) {
        if (o.chat !== chat || /^(?:stopped|superseded|acknowledged|delivered)$/.test(o.state)) return;
        if (o.state === "needs_attention") { if (!why) why = "review"; }
        else why = "recovery";
      });
    } catch (e) {}
    return why;
  }
  function sendOnEnter() {
    try { var c = JSON.parse(localStorage.getItem("LlamaUi.config") || "{}"); return c.sendOnEnter !== false; } catch (e) { return true; }
  }
  /* WebUI: Enter ภายในบล็อกโค้ด ``` ที่ยังไม่ปิด (นับจากต้นข้อความถึงเคอร์เซอร์) = ขึ้นบรรทัดใหม่ ไม่ส่ง */
  function inOpenFence(text, caret) {
    var n = 0, re = /```/g, m;
    while ((m = re.exec(text)) && m.index + 3 <= caret) n++;
    return n % 2 === 1;
  }

  /* ---- ที่เก็บคิว ------------------------------------------------------------- */
  function load() {
    try {
      var v = JSON.parse(sessionStorage.getItem(KEY) || "null");
      if (v && typeof v === "object" && v.items && typeof v.items === "object") {
        v.paused = v.paused && typeof v.paused === "object" ? v.paused : {};
        return v;
      }
    } catch (e) {}
    return { items: {}, paused: {} };
  }
  function save() {
    try {
      Object.keys(store.items).forEach(function (k) { if (!store.items[k] || !store.items[k].length) delete store.items[k]; });
      Object.keys(store.paused).forEach(function (k) { if (!store.items[k]) delete store.paused[k]; });
      sessionStorage.setItem(KEY, JSON.stringify(store));
    } catch (e) { /* โหมดส่วนตัว/เต็ม: คิวยังทำงานในหน้านี้ */ }
  }
  function list(key) { return (key && store.items[key]) || []; }
  function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
  function enqueue(key, text) {
    var q = store.items[key] || (store.items[key] = []);
    if (q.length >= MAX_ITEMS) return false;
    q.push({ id: uid(), text: String(text).slice(0, MAX_TEXT), at: Date.now() });
    save();
    return true;
  }
  function removeItem(key, id) {
    var q = list(key);
    for (var i = 0; i < q.length; i++) if (q[i].id === id) { var it = q.splice(i, 1)[0]; save(); return it; }
    return null;
  }

  /* ---- เขียนข้อความลงกล่องพิมพ์แล้วส่งผ่านเส้นทางของ WebUI เอง ----------------------------- */
  function setComposer(ta, value) {
    var desc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (desc && desc.set) desc.set.call(ta, value); else ta.value = value;
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  }
  function submitButton() {
    var f = form();
    if (!f) return null;
    var bs = f.querySelectorAll('button[type="submit"]');
    for (var i = 0; i < bs.length; i++) if (!bs[i].closest(".qw-queue")) return bs[i];
    return null;
  }
  /* ส่งข้อความที่อยู่ในกล่องพิมพ์ตอนนี้ (Enter ของ WebUI เดิน onSubmit เส้นเดียวกับปุ่มส่ง) —
     ระหว่างงานยังทำอยู่ปุ่มส่งไม่มี (ปุ่มหยุดแทนที่) จึงยิง Enter ให้ตัวจัดการของกล่องพิมพ์แทน */
  function nativeSubmit() {
    var ta = textarea(), f = form();
    if (!ta || !f) return false;
    bypass++;
    try {
      var b = submitButton();
      if (b && !b.disabled && b.getAttribute("aria-disabled") !== "true") {
        if (typeof f.requestSubmit === "function") f.requestSubmit(b); else b.click();
        return true;
      }
      if (!busy()) return false;
      var ev = new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true });
      ta.dispatchEvent(ev);
      return ev.defaultPrevented;
    } finally { bypass--; }
  }

  /* ---- ดัก Enter ของกล่องพิมพ์ ------------------------------------------------------ */
  function onKey(e) {
    if (bypass || e.defaultPrevented || !e.isTrusted || e.key !== "Enter" || e.shiftKey || e.altKey) return;
    if (e.isComposing || e.keyCode === 229) return;
    var ta = textarea();
    if (!ta || e.target !== ta) return;
    var mod = e.ctrlKey || e.metaKey;
    if (!mod && !sendOnEnter()) return;
    var key = chatKey();
    if (!key) return;
    var queued = list(key).length > 0;
    if (!busy() && !queued) return;                       // แชตว่างและไม่มีคิว = ส่งตามปกติของ WebUI
    var text = String(ta.value || "");
    if (!text.trim() || pickerOpen() || hasAttachments()) return;
    if (!mod && inOpenFence(text, typeof ta.selectionStart === "number" ? ta.selectionStart : text.length)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (!enqueue(key, text.trim())) { say(T("คิวเต็มแล้ว (สูงสุด " + MAX_ITEMS + " ข้อความ)", "The queue is full (" + MAX_ITEMS + " messages)"), true); return; }
    delete store.paused[key];                              // ส่งข้อความใหม่ = ปลดคิวที่พักไว้หลังกดหยุด
    save();
    setComposer(ta, "");
    idleSince = 0;
    render();
    say(busy() ? T("เข้าคิวแล้ว จะส่งให้เมื่อ Qwen ทำงานนี้เสร็จ", "Queued. It will be sent when Qwen finishes this task.")
      : T("เข้าคิวแล้ว", "Queued."));
  }
  /* ปุ่มหยุด (ในกล่องพิมพ์ / รายการแชต / การ์ด "ทำต่อไหม") = พักคิวของแชตนี้ ไม่ส่งอะไรเองหลังผู้ใช้สั่งหยุด */
  function onStop(e) {
    if (!e.isTrusted || (e.type === "keydown" && e.key !== "Enter" && e.key !== " ")) return;
    var b = e.target && e.target.closest ? e.target.closest("button") : null;
    if (!b || b.closest(".qw-queue")) return;
    var stop = b.classList.contains("stop-button") ||
      ((b.closest(".chat-screen-form-wrapper form") || b.closest(".agentic-content")) && buttonLabel(b).some(function (l) { return STOP_RE.test(l); }));
    if (!stop) return;
    var key = chatKey();
    if (key && list(key).length && !store.paused[key]) { store.paused[key] = true; save(); render(); }
  }
  window.addEventListener("keydown", onKey, true);
  ["pointerdown", "click", "keydown"].forEach(function (t) { window.addEventListener(t, onStop, true); });

  /* ---- ส่งคิวเมื่อแชตว่าง ----------------------------------------------------------- */
  function blockedReason(key) {
    if (store.paused[key]) return "paused";
    var ta = textarea();
    if (!ta || !form()) return "nocomposer";
    if (String(ta.value || "").trim()) return "draft";
    if (hasAttachments()) return "draft";
    if (nativePending()) return "native";
    if (dialogOpen()) return "dialog";
    return recoveryPending(key);
  }
  function dispatch(key, it) {
    var ta = textarea();
    if (!ta) { putBack(key, it, null); return false; }
    dispatching = true;
    setComposer(ta, it.text);
    // Svelte อัปเดตสถานะปุ่มส่งหลัง event input — ส่งในรอบถัดไป (setTimeout ทำงานต่อแม้แท็บถูกซ่อน ต่างจาก rAF)
    setTimeout(function () {
      dispatching = false;
      if (chatKey() !== key || busy()) { putBack(key, it, ta); return; }
      try { if (window.qwenRecovery && window.qwenRecovery.noteSend) window.qwenRecovery.noteSend(); } catch (e) {}
      if (!nativeSubmit()) { putBack(key, it, ta); fail(key); return; }
      sending = { key: key, item: it, at: Date.now(), count: messageCount() };
      render(true);
    }, 80);
    return true;
  }
  function putBack(key, it, ta) {
    var q = store.items[key] || (store.items[key] = []);
    if (!q.some(function (x) { return x.id === it.id; })) q.unshift(it);
    save();
    if (ta && ta.value === it.text) setComposer(ta, "");
    render();
  }
  function fail(key) {
    store.paused[key] = true;
    save();
    render();
    say(T("ส่งข้อความในคิวไม่สำเร็จ — พักคิวไว้ กด ส่งต่อ เพื่อลองอีกครั้ง", "Couldn't send the queued message. The queue is paused; press Resume to try again."), true);
  }
  function messageCount() { return document.querySelectorAll(".chat-messages .chat-message").length; }
  function tick() {
    if (dispatching) return;
    var key = chatKey();
    if (sending) {
      if (busy() || messageCount() > sending.count) {
        sending = null; idleSince = 0; render();
      } else if (Date.now() - sending.at > START_MS || sending.key !== key) {
        var s = sending; sending = null;
        if (s.key === key) { var ta = textarea(); putBack(key, s.item, ta && ta.value === s.item.text ? ta : null); fail(key); }
        else putBack(s.key, s.item, null);
      }
      return;
    }
    var q = list(key);
    if (!q.length || busy()) { idleSince = 0; paintMaybe(); return; }
    if (!idleSince) { idleSince = Date.now(); paintMaybe(); return; }
    if (Date.now() - idleSince < IDLE_MS) return;
    if (blockedReason(key)) { paintMaybe(); return; }
    var it = q.shift();
    save();
    idleSince = 0;
    dispatch(key, it);
  }
  setInterval(tick, TICK_MS);

  /* ---- แถบคิวเหนือกล่องพิมพ์ ---------------------------------------------------------- */
  var STYLE_TEXT = [
    "html:root .qw-queue{display:flex;flex-direction:column;gap:6px;margin:0 0 8px;padding:8px 8px 8px 12px;",
    "border:.5px solid var(--qw-border-strong);border-radius:var(--qw-r-md,12px);background:var(--qw-bg-elev);",
    "color:var(--qw-text);font-family:var(--qw-font-ui);font-size:var(--qw-fs-sm,13px);line-height:1.45}",
    "html:root .qw-queue[hidden]{display:none}",
    "html:root .qw-queue-h{display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:var(--qw-text-2)}",
    "html:root .qw-queue-t{flex:1 1 200px;min-width:0}",
    "html:root .qw-queue-dot{width:7px;height:7px;border-radius:50%;flex:none;background:var(--qw-accent)}",
    "html:root .qw-queue[data-state=paused] .qw-queue-dot{background:var(--qw-text-4)}",
    "html:root .qw-queue[data-state=busy] .qw-queue-dot{animation:qwq-pulse 1.4s ease-in-out infinite}",
    "@keyframes qwq-pulse{50%{opacity:.35}}",
    "html:root .qw-queue-list{display:flex;flex-direction:column;gap:4px;margin:0;padding:0;list-style:none}",
    "html:root .qw-queue-it{display:flex;align-items:flex-start;gap:8px;padding:6px 6px 6px 8px;border-radius:var(--qw-r-sm,8px);background:var(--qw-bg)}",
    "html:root .qw-queue-n{flex:none;min-width:18px;color:var(--qw-text-4);font-variant-numeric:tabular-nums}",
    "html:root .qw-queue-x{flex:1;min-width:0;white-space:pre-wrap;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}",
    "html:root .qw-queue-acts{flex:none;display:inline-flex;gap:4px}",
    "html:root .qw-queue-b{flex:none;height:26px;padding:0 10px;border:.5px solid var(--qw-border-strong);border-radius:var(--qw-r-full,999px);",
    "background:var(--qw-bg-elev);color:var(--qw-text);font:500 var(--qw-fs-xs,12px)/1 var(--qw-font-ui);white-space:nowrap;cursor:pointer}",
    "html:root .qw-queue-b:hover{background:var(--qw-bg-hover)}",
    "html:root .qw-queue-b:disabled{opacity:.45;cursor:default}",
    "html:root .qw-queue-b.go{border-color:var(--qw-accent);box-shadow:inset 0 0 0 .5px var(--qw-accent)}",
    "html:root .qw-queue-b:focus-visible{outline:2px solid var(--qw-focus-ring);outline-offset:2px}",
    "html:root .qw-queue-hint{margin:0 0 6px;padding:0 4px;color:var(--qw-text-3);font:var(--qw-fs-xs,12px)/1.5 var(--qw-font-ui)}",
    "html:root .qw-queue-hint[hidden]{display:none}",
    "html:root .qw-queue-vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}"
  ].join("\n");
  function ensureCss() {
    if (document.getElementById("qw-queue-css")) return;
    var st = document.createElement("style");
    st.id = "qw-queue-css";
    st.textContent = STYLE_TEXT;
    (document.head || document.documentElement).appendChild(st);
  }
  function say(msg, urgent) {
    if (!document.body) return;
    if (!live) {
      live = document.createElement("div");
      live.className = "qw-queue-vh";
      live.setAttribute("role", "status");
      live.setAttribute("aria-live", "polite");
      document.body.appendChild(live);
    }
    live.setAttribute("aria-live", urgent ? "assertive" : "polite");
    live.textContent = "";
    setTimeout(function () { live.textContent = msg; }, 30);
  }
  function btn(cls, label, title, onClick, disabled) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "qw-queue-b" + (cls ? " " + cls : "");
    b.textContent = label;
    if (title) { b.title = title; b.setAttribute("aria-label", title); }
    b.disabled = !!disabled;
    b.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); onClick(); });
    return b;
  }
  function headline(key, q, isBusy) {
    if (store.paused[key]) return T("พักคิวไว้หลังกดหยุด — ข้อความด้านล่างยังไม่ถูกส่ง", "Queue paused after Stop — these messages have not been sent");
    if (sending && sending.key === key) return T("กำลังส่งข้อความถัดไป…", "Sending the next message…");
    if (isBusy) return T("รอส่งต่อเมื่อ Qwen ทำงานนี้เสร็จ", "Will be sent when Qwen finishes this task");
    var why = blockedReason(key);
    if (why === "draft") return T("รอส่ง — มีข้อความพิมพ์ค้างอยู่ในช่องพิมพ์", "Waiting — there is a draft in the message box");
    if (why === "native") return T("รอข้อความที่แทรกไว้ส่งก่อน", "Waiting for the interjected message to be sent first");
    if (why === "recovery") return T("รอระบบกู้การเชื่อมต่อทำงานเดิมให้จบก่อน", "Waiting for connection recovery to finish the previous task");
    if (why === "review") return T("งานก่อนหน้าขาดช่วงและรอให้ตรวจ — กด ส่งเลย เมื่อพร้อม", "The previous task was interrupted and needs review — press Send now when ready");
    if (why === "dialog") return T("รอปิดหน้าต่างที่เปิดอยู่ก่อน", "Waiting for the open dialog to close");
    return T("กำลังจะส่งข้อความถัดไป", "About to send the next message");
  }
  function signature(key, q, isBusy, draftHint) {
    return [lang(), key, isBusy, !!store.paused[key], sending && sending.key === key, draftHint, blockedReason(key),
      nativePending(), q.map(function (x) { return x.id; }).join(",")].join("|");
  }
  function paintMaybe() { render(false); }
  function render(force) {
    var f = form(), area = inputArea();
    if (!f || !area) return;
    var key = chatKey(), q = list(key), isBusy = busy();
    var ta = textarea(), draftHint = !!(isBusy && !q.length && ta && String(ta.value || "").trim());
    var sig = signature(key, q, isBusy, draftHint);
    if (!panel) {
      ensureCss();
      panel = document.createElement("div");
      panel.className = "qw-queue-wrap";
    }
    // วางก่อนแถบโหมดวางแผน (enhance ต้องการให้แถบนั้นติดกล่องพิมพ์) ไม่งั้นวางติดกล่องพิมพ์
    var planBar = area.previousElementSibling && area.previousElementSibling.classList.contains("qw-plan-bar") ? area.previousElementSibling : null;
    var anchor = planBar || area;
    if (panel.parentNode !== f || panel.nextElementSibling !== anchor) f.insertBefore(panel, anchor);
    if (!force && sig === lastSig) return;
    lastSig = sig;
    var hadFocus = panel.contains(document.activeElement) ? document.activeElement.getAttribute("data-qwq") : null;
    panel.textContent = "";
    if (draftHint) {
      var hint = document.createElement("p");
      hint.className = "qw-queue-hint";
      hint.textContent = T("Qwen กำลังทำงาน — กด Enter เพื่อเข้าคิว ระบบจะส่งให้เองเมื่องานนี้เสร็จ (งานเดิมไม่ถูกหยุด)",
        "Qwen is working — press Enter to queue this message. It will be sent when this task finishes (the task keeps running).");
      panel.appendChild(hint);
    }
    if (!q.length) return;
    var box = document.createElement("section");
    box.className = "qw-queue";
    box.setAttribute("aria-label", T("คิวข้อความ", "Message queue"));
    box.setAttribute("data-state", store.paused[key] ? "paused" : isBusy ? "busy" : "idle");
    var h = document.createElement("div");
    h.className = "qw-queue-h";
    var dot = document.createElement("span"); dot.className = "qw-queue-dot"; dot.setAttribute("aria-hidden", "true");
    var t = document.createElement("span"); t.className = "qw-queue-t";
    t.textContent = T("คิว " + q.length + " ข้อความ · ", q.length + " queued · ") + headline(key, q, isBusy);
    h.appendChild(dot); h.appendChild(t);
    if (store.paused[key]) {
      var resume = btn("go", T("ส่งต่อ", "Resume"), T("ส่งข้อความในคิวต่อ", "Resume sending the queue"), function () {
        delete store.paused[key]; save(); idleSince = 0; render(true); say(T("ส่งคิวต่อแล้ว", "Queue resumed"));
      });
      resume.setAttribute("data-qwq", "resume");
      h.appendChild(resume);
    }
    var clear = btn("", T("ล้างคิว", "Clear"), T("ลบข้อความทั้งหมดในคิว", "Remove every queued message"), function () {
      delete store.items[key]; save(); render(true); say(T("ล้างคิวแล้ว", "Queue cleared")); if (ta) ta.focus();
    });
    clear.setAttribute("data-qwq", "clear");
    h.appendChild(clear);
    box.appendChild(h);
    var ul = document.createElement("ol");
    ul.className = "qw-queue-list";
    var pending = nativePending();
    q.forEach(function (it, i) {
      var li = document.createElement("li");
      li.className = "qw-queue-it";
      var n = document.createElement("span"); n.className = "qw-queue-n"; n.textContent = (i + 1) + ".";
      var x = document.createElement("span"); x.className = "qw-queue-x"; x.textContent = it.text; x.title = it.text.slice(0, 2000);
      var acts = document.createElement("span"); acts.className = "qw-queue-acts";
      if (isBusy) {
        var now = btn("", T("แทรกตอนนี้", "Interject"),
          pending ? T("มีข้อความแทรกรอส่งอยู่แล้ว", "Another interjected message is already waiting")
            : T("ส่งข้อความนี้ให้ Qwen เห็นหลังขั้นที่กำลังทำ (ขั้นที่เหลือของรอบนี้จะถูกข้าม)", "Show this message to Qwen right after its current step (the rest of that step is skipped)"),
          function () { interject(key, it.id); }, pending);
        now.setAttribute("data-qwq", "now-" + it.id);
        acts.appendChild(now);
      } else if (store.paused[key] || i === 0) {
        var go = btn("", T("ส่งเลย", "Send now"), T("ส่งข้อความนี้ตอนนี้", "Send this message now"), function () { sendNow(key, it.id); });
        go.setAttribute("data-qwq", "go-" + it.id);
        acts.appendChild(go);
      }
      var ed = btn("", T("แก้ไข", "Edit"), T("ย้ายข้อความนี้กลับไปที่ช่องพิมพ์", "Move this message back to the message box"), function () { edit(key, it.id); });
      ed.setAttribute("data-qwq", "edit-" + it.id);
      var del = btn("", T("ลบ", "Remove"), T("ลบข้อความนี้ออกจากคิว", "Remove this message from the queue"), function () {
        removeItem(key, it.id); render(true); say(T("ลบออกจากคิวแล้ว", "Removed from the queue")); var nb = panel.querySelector("[data-qwq^='del-']"); if (nb) nb.focus(); else if (ta) ta.focus();
      });
      del.setAttribute("data-qwq", "del-" + it.id);
      acts.appendChild(ed); acts.appendChild(del);
      li.appendChild(n); li.appendChild(x); li.appendChild(acts);
      ul.appendChild(li);
    });
    box.appendChild(ul);
    panel.appendChild(box);
    if (hadFocus) { var back = panel.querySelector('[data-qwq="' + hadFocus + '"]'); if (back) back.focus(); }
  }
  function edit(key, id) {
    var it = removeItem(key, id), ta = textarea();
    if (!it || !ta) { render(true); return; }
    var cur = String(ta.value || "");
    setComposer(ta, cur.trim() ? it.text + "\n\n" + cur : it.text);
    render(true);
    try { ta.focus(); ta.setSelectionRange(it.text.length, it.text.length); } catch (e) {}
  }
  function sendNow(key, id) {
    if (busy()) { interject(key, id); return; }
    var q = list(key), idx = -1;
    for (var i = 0; i < q.length; i++) if (q[i].id === id) idx = i;
    if (idx < 0) return;
    var ta = textarea();
    if (ta && String(ta.value || "").trim()) { say(T("ช่องพิมพ์มีข้อความค้างอยู่ — ส่งหรือลบข้อความนั้นก่อน", "The message box has a draft — send or clear it first"), true); return; }
    var it = q.splice(idx, 1)[0];
    delete store.paused[key];
    save();
    dispatch(key, it);
  }
  function interject(key, id) {
    if (!busy()) { sendNow(key, id); return; }
    if (nativePending()) { say(T("มีข้อความแทรกรอส่งอยู่แล้ว", "Another interjected message is already waiting"), true); return; }
    var ta = textarea();
    if (!ta) return;
    var it = removeItem(key, id);
    if (!it) return;
    var draft = String(ta.value || "");
    setComposer(ta, it.text);
    dispatching = true;
    setTimeout(function () {
      dispatching = false;
      var ok = nativeSubmit();
      if (!ok) { putBack(key, it, ta); say(T("แทรกไม่สำเร็จ ข้อความยังอยู่ในคิว", "Couldn't interject; the message stays queued"), true); }
      else {
        // WebUI ล้างช่องพิมพ์หลังรับข้อความ — คืนข้อความที่ผู้ใช้พิมพ์ค้างไว้หลังจากนั้น
        if (draft.trim()) setTimeout(function () { if (!String(ta.value || "").trim()) setComposer(ta, draft); }, 400);
        say(T("แทรกแล้ว Qwen จะเห็นข้อความนี้หลังขั้นที่กำลังทำ", "Interjected. Qwen will see it after the current step.")); }
      render(true);
    }, 80);
  }

  /* วาดซ้ำเมื่อเปลี่ยนแชต/ภาษา/สถานะงาน — tick เรียก paintMaybe อยู่แล้ว ที่นี่จับการเปลี่ยนที่ไม่รอ tick */
  window.addEventListener("hashchange", function () { idleSince = 0; render(true); });
  document.addEventListener("input", function (e) { if (e.target === textarea()) render(false); }, true);
  window.addEventListener("storage", function (e) { if (e.key === null) { store = load(); render(true); } });

  window.qwenQueue = {
    version: 1,
    list: function () { var k = chatKey(); return list(k).map(function (x) { return { id: x.id, text: x.text }; }); },
    status: function () { var k = chatKey(); return { chat: k, busy: busy(), paused: !!store.paused[k], size: list(k).length, sending: !!sending, blocked: k ? blockedReason(k) : "" }; },
    clear: function () { var k = chatKey(); delete store.items[k]; save(); render(true); },
    resume: function () { var k = chatKey(); delete store.paused[k]; save(); idleSince = 0; render(true); }
  };
})();
