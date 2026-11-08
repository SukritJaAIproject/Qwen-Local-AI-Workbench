/* browser-panel.js — แผงเบราว์เซอร์ในตัว (ทางขวาของหน้าแชต) สำหรับหน้า shell ของพอร์ตโปรเจกต์
 *
 * ฝั่งเซิร์ฟเวอร์คือ hub_browser.py (Edge โปรไฟล์แยกของโปรเจกต์ ไม่มีหน้าต่าง) — แผงนี้แค่ "จอ + เมาส์ + คีย์บอร์ด":
 *   ภาพ: long-poll GET /_qwen/browser/frame?after=<seq> (JPEG จาก Page.startScreencast ขนาดเท่าช่องแสดงผลพอดี)
 *   คลิก/เลื่อน/พิมพ์: POST /_qwen/browser/input  (ข้อความพิมพ์ส่งเป็น insertText — ภาษาไทยและ IME ใช้ได้)
 *   แถบที่อยู่/แท็บ: POST /_qwen/browser/nav  · ขนาดช่องแสดงผล: POST /_qwen/browser/view
 *   สถานะ (แท็บ, กล่องยืนยันของหน้าเว็บ, สิ่งที่ Qwen เพิ่งทำ): GET /_qwen/browser/state ทุก ~1 วินาทีตอนเปิดแผง
 * Qwen ใช้เบราว์เซอร์ตัวเดียวกันผ่านเครื่องมือ browser_* — ผู้ใช้จึงเห็นทุกอย่างที่ Qwen ทำในแผงนี้
 * ทุกคำขอเป็น same-origin (hub ตรวจ Origin ของพอร์ตนี้) ไม่มีโทเคนในไฟล์นี้
 */
(function () {
  "use strict";
  if (window.qwenBrowserPanel || !document.getElementById("app")) return;

  var API = "/_qwen/browser/";
  var LS_W = "qwen-bp-w", LS_OPEN = "qwen-bp-open";
  var NARROW = window.matchMedia("(max-width: 829.98px)");
  var TH = document.documentElement.lang !== "en";
  var S = {
    open: false, state: null, seq: 0, fw: 0, fh: 0, url: null, loopId: 0, pollTimer: 0, lastModelSeq: -1,
    userClosedAt: 0, w: 0, dragging: false, inputQ: Promise.resolve(), lastMove: 0, wheel: null, viewSent: "",
    pointerDown: false, lastPoint: null, starting: false
  };

  /* ---- ข้อความ ---------------------------------------------------------------- */
  var STR = {
    browser: ["เบราว์เซอร์", "Browser"],
    open_panel: ["เปิดเบราว์เซอร์ในตัว", "Open the built-in browser"],
    close_panel: ["ปิดแผงเบราว์เซอร์", "Close the browser panel"],
    new_tab: ["แท็บใหม่", "New tab"],
    close_tab: ["ปิดแท็บ", "Close tab"],
    back: ["ย้อนกลับ", "Back"], forward: ["ไปข้างหน้า", "Forward"], reload: ["โหลดใหม่", "Reload"], stop: ["หยุดโหลด", "Stop loading"],
    url_ph: ["พิมพ์ URL หรือชื่อเว็บ แล้วกด Enter", "Type a URL and press Enter"],
    url_label: ["ที่อยู่เว็บ", "Address"],
    more: ["ตัวเลือกเพิ่มเติม", "More options"],
    window_mode: ["เปิดเป็นหน้าต่างจริง (สำหรับล็อกอิน)", "Open as a real window (for sign-in)"],
    panel_mode: ["กลับมาใช้ในแผง", "Back to the panel"],
    shutdown: ["ปิดเบราว์เซอร์", "Quit the browser"],
    resize: ["ปรับความกว้างแผงเบราว์เซอร์", "Resize the browser panel"],
    empty_t: ["ท่องเว็บกับ Qwen", "Browse with Qwen"],
    empty_s: ["พิมพ์ URL หรือบอก Qwen ให้เปิดเว็บ — Qwen อ่าน คลิก พิมพ์ กรอกฟอร์ม ลากวาง อัปโหลดและดาวน์โหลดไฟล์ในหน้านี้ได้ และคุณเห็นทุกอย่างที่ทำ",
      "Type a URL or ask Qwen to open a site. Qwen can read, click, type, fill forms, drag, upload and download files here, and you see everything it does."],
    examples: ["ตัวอย่าง", "Examples"],
    ex1: ["เปิด google.com แล้วค้นหาข่าวเทคโนโลยีวันนี้ สรุปให้ 3 ข้อ", "Open google.com, search today's tech news and give me 3 points"],
    ex2: ["เปิดหน้าเว็บที่อยู่ในแผงตอนนี้ แล้วสรุปเนื้อหาให้หน่อย", "Summarise the page that is open in the browser panel"],
    ex3: ["ไปที่ youtube.com แล้วหาวิดีโอสอน Python สำหรับมือใหม่", "Go to youtube.com and find a beginner Python tutorial"],
    starting: ["กำลังเปิดเบราว์เซอร์…", "Starting the browser…"],
    start_btn: ["เริ่มใช้เบราว์เซอร์", "Start the browser"],
    window_note: ["เบราว์เซอร์เปิดเป็นหน้าต่างจริงอยู่ — ล็อกอินหรือทำในหน้าต่างนั้นได้เลย ภาพยังแสดงที่นี่ด้วย",
      "The browser is open as a real window — sign in there. The view still mirrors here."],
    qwen_doing: ["Qwen กำลังใช้เบราว์เซอร์", "Qwen is using the browser"],
    dialog_q: ["หน้าเว็บถาม", "The page asks"],
    ok: ["ตกลง", "OK"], cancel: ["ยกเลิก", "Cancel"], dismiss: ["ปิด", "Dismiss"], open_file: ["เปิดไฟล์", "Open file"],
    err: ["เบราว์เซอร์มีปัญหา", "Browser problem"],
    typing: ["คลิกในหน้าเว็บแล้วพิมพ์ได้เลย", "Click the page and type"],
    view_label: ["หน้าเว็บในเบราว์เซอร์ของ Qwen", "Web page in Qwen's browser"],
    blank: ["แท็บว่าง", "Blank tab"],
    secure: ["การเชื่อมต่อเข้ารหัส (https)", "Encrypted connection (https)"],
    insecure: ["ไม่เข้ารหัส (http) — อย่ากรอกข้อมูลสำคัญ", "Not encrypted (http) — don't enter sensitive data"]
  };
  function t(k) { var v = STR[k]; return v ? v[TH ? 0 : 1] : k; }

  /* ---- ไอคอน (เส้นแบบเดียวกับไอคอนของ shell) ----------------------------------------- */
  var IC = {
    globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.5 3.4 5.3 3.4 8.5s-1 6-3.4 8.5c-2.4-2.5-3.4-5.3-3.4-8.5s1-6 3.4-8.5z"/>',
    x: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    back: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    fwd: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    reload: '<path d="M19.5 12a7.5 7.5 0 1 1-2.3-5.4"/><path d="M19.5 4.5v4.2h-4.2"/>',
    more: '<circle cx="5.5" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="18.5" cy="12" r="1.4" fill="currentColor" stroke="none"/>',
    win: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 8.5h17"/>',
    power: '<path d="M12 3.5v8"/><path d="M7 6.5a7 7 0 1 0 10 0"/>',
    lock: '<rect x="5.5" y="10.5" width="13" height="9" rx="2"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
    unlock: '<rect x="5.5" y="10.5" width="13" height="9" rx="2"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 6.8-1.2"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>'
  };
  function icon(name, cls) {
    return '<svg class="ic ' + (cls || "ic-sm") + '" viewBox="0 0 24 24" aria-hidden="true">' + IC[name] + "</svg>";
  }
  function el(tag, attrs, html) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (attrs[k] == null || attrs[k] === false) return;
      if (k === "text") n.textContent = attrs[k]; else n.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    });
    if (html) n.innerHTML = html;
    return n;
  }

  /* ---- CSS ----------------------------------------------------------------------- */
  var STYLE_TEXT = [
    "#bp{position:fixed;top:0;right:0;bottom:0;z-index:30;width:var(--bp-w,600px);display:flex;flex-direction:column;min-width:0;",
    "  background:var(--qw-bg-elev);border-left:.5px solid var(--qw-border-strong)}",
    "#bp[hidden]{display:none}",
    "@media (min-width:830px){body.bp-open #app{grid-template-columns:var(--sb,288px) minmax(0,1fr) var(--bp-w,600px)}}",
    "@media (max-width:829.98px){#bp{left:0;width:auto;z-index:65;border-left:0}.bp-grip{display:none}}",
    ".bp-grip{position:absolute;left:-5px;top:0;bottom:0;z-index:3;width:10px;cursor:col-resize;touch-action:none}",
    ".bp-grip::after{content:'';position:absolute;left:4.5px;top:0;bottom:0;width:1.5px;background:transparent;transition:background-color var(--qw-dur) var(--qw-ease)}",
    ".bp-grip:hover::after,body.bp-drag .bp-grip::after,.bp-grip:focus-visible::after{background:var(--qw-border-focus)}",
    ".bp-grip:focus-visible{outline:none}",
    "body.bp-drag{cursor:col-resize;user-select:none}body.bp-drag iframe,body.bp-drag #bpView{pointer-events:none}",
    ".bp-bar{display:flex;align-items:center;gap:4px;height:var(--qw-header-h,52px);padding:0 8px 0 10px;flex:none;min-width:0}",
    ".bp-tabs{display:flex;align-items:center;gap:2px;min-width:0;flex:1 1 auto;overflow-x:auto;scrollbar-width:none}",
    ".bp-tabs::-webkit-scrollbar{display:none}",
    ".bp-tab{display:inline-flex;align-items:center;gap:6px;min-width:0;max-width:200px;height:32px;padding:0 4px 0 10px;border-radius:var(--qw-r-sm);",
    "  color:var(--qw-text-3);font-size:var(--qw-fs-sm);flex:0 1 auto}",
    ".bp-tab:hover{background:var(--qw-bg-hover);color:var(--qw-text)}",
    ".bp-tab[aria-selected=true]{background:var(--qw-bg-active);color:var(--qw-text)}",
    ".bp-tab-t{min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}",
    ".bp-tab .icon-btn{opacity:.7}.bp-tab .icon-btn:hover{opacity:1}",
    ".bp-tab-dot{width:6px;height:6px;border-radius:50%;flex:none;background:var(--qw-accent);animation:bpPulse 1.2s ease-in-out infinite}",
    "@keyframes bpPulse{50%{opacity:.3}}",
    ".bp-sp{flex:1 1 0;min-width:4px}",
    ".bp-nav{display:flex;align-items:center;gap:4px;padding:0 10px 10px;flex:none;border-bottom:.5px solid var(--qw-border)}",
    ".bp-url{flex:1;min-width:0;display:flex;align-items:center;gap:6px;height:32px;padding:0 10px;border-radius:var(--qw-r-full);",
    "  background:var(--qw-bg);box-shadow:inset 0 0 0 .5px var(--qw-border-strong);color:var(--qw-text-3)}",
    ".bp-url:focus-within{box-shadow:inset 0 0 0 1px var(--qw-border-focus)}",
    ".bp-url input{flex:1;min-width:0;height:100%;border:0;outline:0;background:none;color:var(--qw-text);font-size:var(--qw-fs-sm)}",
    ".bp-sec{display:inline-flex;flex:none}.bp-sec[data-k=unlock]{color:var(--qw-warn)}",
    ".bp-note{flex:none;display:flex;align-items:center;gap:8px 10px;flex-wrap:wrap;margin:8px 10px 0;padding:7px 10px;border-radius:var(--qw-r-sm);",
    "  font-size:var(--qw-fs-xs);line-height:1.5;color:var(--qw-text-2);background:var(--qw-bg);box-shadow:inset 0 0 0 .5px var(--qw-border)}",
    ".bp-note[hidden]{display:none}",
    ".bp-note.warn{background:color-mix(in srgb,var(--qw-warn) 11%,transparent);box-shadow:inset 0 0 0 .5px color-mix(in srgb,var(--qw-warn) 42%,transparent)}",
    ".bp-note.qwen{background:var(--qw-accent-soft);box-shadow:inset 0 0 0 .5px color-mix(in srgb,var(--qw-accent) 45%,transparent)}",
    ".bp-note-t{flex:1 1 180px;min-width:0;overflow-wrap:anywhere}",
    ".bp-note input{flex:1 1 140px;min-width:0;height:26px;padding:0 8px;border-radius:var(--qw-r-xs);border:.5px solid var(--qw-border-strong);background:var(--qw-bg-elev)}",
    ".bp-b{flex:none;height:26px;padding:0 11px;border-radius:var(--qw-r-full);font-size:var(--qw-fs-xs);font-weight:500;white-space:nowrap;",
    "  border:.5px solid var(--qw-border-strong);background:var(--qw-bg-elev);color:var(--qw-text)}",
    ".bp-b:hover{background:var(--qw-bg-hover)}.bp-b.ink{background:var(--qw-text);color:var(--qw-bg);border-color:transparent}.bp-b.ink:hover{opacity:.86}",
    ".bp-b:focus-visible,.bp-tab:focus-visible{outline:2px solid var(--qw-focus-ring);outline-offset:2px}",
    ".bp-view{position:relative;flex:1;min-height:0;margin:10px;border-radius:var(--qw-r-md);overflow:hidden;background:#fff;",
    "  box-shadow:0 0 0 .5px var(--qw-border-strong);outline:none}",
    ".bp-view.focus{box-shadow:0 0 0 2px var(--qw-focus-ring)}",
    ".bp-view img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;object-position:left top;user-select:none;-webkit-user-drag:none;cursor:default}",
    ".bp-view img[hidden]{display:none}",
    ".bp-ime{position:absolute;left:0;top:0;width:1px;height:1px;opacity:0;border:0;padding:0;resize:none;pointer-events:none;color:transparent;background:transparent}",
    ".bp-empty{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:24px;",
    "  background:var(--qw-bg);color:var(--qw-text-2);text-align:center}",
    ".bp-empty[hidden]{display:none}",
    ".bp-empty .ic{width:30px;height:30px;color:var(--qw-text-3)}",
    ".bp-empty h3{margin:4px 0 0;font:600 var(--qw-fs-lg,17px)/1.3 var(--qw-font-ui);color:var(--qw-text)}",
    ".bp-empty p{margin:0;max-width:420px;font-size:var(--qw-fs-sm);line-height:1.6;color:var(--qw-text-3)}",
    ".bp-ex{display:flex;flex-direction:column;gap:6px;width:min(100%,440px);margin-top:10px}",
    ".bp-ex-l{font-size:var(--qw-fs-xs);color:var(--qw-text-4);text-align:left}",
    ".bp-ex button{padding:8px 12px;border-radius:var(--qw-r-sm);text-align:left;font-size:var(--qw-fs-sm);color:var(--qw-text-2);",
    "  background:var(--qw-bg-elev);box-shadow:inset 0 0 0 .5px var(--qw-border)}",
    ".bp-ex button:hover{background:var(--qw-bg-hover);color:var(--qw-text)}",
    ".bp-menu{position:absolute;right:8px;top:46px;z-index:5;min-width:240px;padding:4px;border-radius:var(--qw-r-sm);background:var(--qw-bg-elev);",
    "  box-shadow:var(--qw-shadow-md),0 0 0 .5px var(--qw-border-strong)}",
    ".bp-menu[hidden]{display:none}",
    ".bp-menu button{display:flex;align-items:center;gap:8px;width:100%;height:32px;padding:0 10px;border-radius:var(--qw-r-xs);font-size:var(--qw-fs-sm);color:var(--qw-text-2);text-align:left}",
    ".bp-menu button:hover,.bp-menu button:focus-visible{background:var(--qw-bg-hover);color:var(--qw-text);outline:none}",
    "#bpToggle[aria-pressed=true]{background:var(--qw-bg-active);color:var(--qw-text)}",
    "#bpToggle .bp-live{width:6px;height:6px;border-radius:50%;background:var(--qw-accent);margin-left:-2px}",
    "#bpToggle .bp-live[hidden]{display:none}"
  ].join("\n");

  /* ---- สร้างแผง ---------------------------------------------------------------------- */
  var style = el("style", { id: "bp-css" });
  style.textContent = STYLE_TEXT;
  document.head.appendChild(style);

  var panel = el("section", { id: "bp", "aria-label": t("browser"), hidden: true });
  panel.innerHTML =
    '<div class="bp-grip" id="bpGrip" role="separator" aria-orientation="vertical" tabindex="0"></div>' +
    '<div class="bp-bar"><div class="bp-tabs" id="bpTabs" role="tablist"></div>' +
    '<button type="button" class="icon-btn sm" id="bpNewTab">' + icon("plus") + "</button>" +
    '<span class="bp-sp"></span>' +
    '<button type="button" class="icon-btn sm" id="bpMore" aria-haspopup="menu" aria-expanded="false">' + icon("more") + "</button>" +
    '<button type="button" class="icon-btn sm" id="bpClose">' + icon("x") + "</button></div>" +
    '<div class="bp-menu" id="bpMenu" role="menu" hidden>' +
    '<button type="button" role="menuitem" id="bpWin">' + icon("win") + '<span id="bpWinT"></span></button>' +
    '<button type="button" role="menuitem" id="bpQuit">' + icon("power") + "<span>" + t("shutdown") + "</span></button></div>" +
    '<div class="bp-nav">' +
    '<button type="button" class="icon-btn sm" id="bpBack">' + icon("back") + "</button>" +
    '<button type="button" class="icon-btn sm" id="bpFwd">' + icon("fwd") + "</button>" +
    '<button type="button" class="icon-btn sm" id="bpReload">' + icon("reload") + "</button>" +
    '<form class="bp-url" id="bpUrlForm"><span id="bpSec" class="bp-sec">' + icon("search") + '</span><input id="bpUrl" type="text" inputmode="url" autocomplete="off" spellcheck="false"></form>' +
    "</div>" +
    '<div class="bp-note" id="bpNote" hidden></div>' +
    '<div class="bp-view" id="bpView" tabindex="0" role="application">' +
    '<img id="bpImg" alt="" draggable="false" hidden>' +
    '<textarea id="bpIme" class="bp-ime" tabindex="-1" aria-hidden="true" autocomplete="off" autocapitalize="off" spellcheck="false"></textarea>' +
    '<div class="bp-empty" id="bpEmpty">' + icon("globe", "") + "<h3>" + t("empty_t") + "</h3><p>" + t("empty_s") + "</p>" +
    '<div class="bp-ex" id="bpEx"><span class="bp-ex-l">' + t("examples") + "</span></div></div>" +
    "</div>";
  document.body.appendChild(panel);
  var $ = function (id) { return document.getElementById(id); };
  var view = $("bpView"), img = $("bpImg"), ime = $("bpIme"), urlIn = $("bpUrl"), note = $("bpNote");
  [["bpNewTab", "new_tab"], ["bpMore", "more"], ["bpClose", "close_panel"], ["bpBack", "back"], ["bpFwd", "forward"],
    ["bpReload", "reload"], ["bpGrip", "resize"]].forEach(function (p) {
    $(p[0]).setAttribute("aria-label", t(p[1]));
    $(p[0]).setAttribute("data-tip", t(p[1]));
  });
  urlIn.placeholder = t("url_ph");
  urlIn.setAttribute("aria-label", t("url_label"));
  view.setAttribute("aria-label", t("view_label"));
  ["ex1", "ex2", "ex3"].forEach(function (k) {
    var b = el("button", { type: "button", text: t(k) });
    b.addEventListener("click", function () { askQwen(t(k)); });
    $("bpEx").appendChild(b);
  });

  /* ปุ่มเปิด/ปิดแผงที่ส่วนหัว (ก่อนปุ่มโปรเจกต์) */
  var toggle = el("button", { type: "button", class: "hdr-btn", id: "bpToggle", "aria-pressed": "false", "aria-controls": "bp",
    "aria-label": t("open_panel"), "data-tip": t("open_panel") },
    icon("globe") + '<span class="lbl">' + t("browser") + '</span><span class="bp-live" aria-hidden="true" hidden></span>');
  var hdr = $("hdr"), projBtn = $("projBtn");
  if (hdr) { if (projBtn && projBtn.parentNode === hdr) hdr.insertBefore(toggle, projBtn); else hdr.appendChild(toggle); }

  /* ---- เรียก API ----------------------------------------------------------------- */
  function api(path, body, opts) {
    var init = { method: body === undefined ? "GET" : "POST", cache: "no-store", credentials: "same-origin" };
    if (body !== undefined) { init.headers = { "Content-Type": "application/json" }; init.body = JSON.stringify(body); }
    if (opts && opts.signal) init.signal = opts.signal;
    return fetch(API + path, init).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (d && d.state) applyState(d.state);
        else if (d && Array.isArray(d.tabs) && "running" in d) applyState(d);     // nav/start/stop ตอบสถานะล่าสุดมาเลย
        if (!r.ok) { var e = new Error((d && d.error) || ("HTTP " + r.status)); e.status = r.status; throw e; }
        return d;
      });
    });
  }
  function toast(msg, bad) {
    try { if (window.qwenShellApi && window.qwenShellApi.toast) { window.qwenShellApi.toast(msg, bad); return; } } catch (e) {}
    showNote(msg, bad ? "warn" : "");
  }
  /* ส่ง input ทีละคำขอตามลำดับ (คลิกต้องไม่แซงกัน) — ฝั่ง hub ไม่รอผลจากหน้าเว็บ จึงเร็ว */
  function sendInput(doc) {
    S.inputQ = S.inputQ.then(function () {
      return fetch(API + "input", { method: "POST", cache: "no-store", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(doc) }).then(function (r) {
        if (!r.ok) return r.json().then(function (d) { if (d && d.state) applyState(d.state); }).catch(function () {});
      }).catch(function () {});
    });
    return S.inputQ;
  }

  /* ---- เปิด/ปิดแผง --------------------------------------------------------------- */
  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function sbWidth() {
    var sb = $("sb");
    var w = sb ? sb.getBoundingClientRect().width : 0;
    return w > 0 ? w : 288;
  }
  function clampW(w) {
    var max = Math.max(360, innerWidth - sbWidth() - 480);
    return Math.round(Math.min(Math.max(+w || 0, 360), max));
  }
  function defaultW() { return Math.round(Math.min(760, Math.max(420, (innerWidth - sbWidth()) * 0.48))); }
  function applyW(w) {
    S.w = clampW(w);
    document.body.style.setProperty("--bp-w", S.w + "px");
    var g = $("bpGrip");
    g.setAttribute("aria-valuemin", "360");
    g.setAttribute("aria-valuemax", String(clampW(1e6)));
    g.setAttribute("aria-valuenow", String(S.w));
  }
  function openPanel(opts) {
    if (S.open) { if (opts && opts.focus) view.focus(); return; }
    var art = $("art");
    if (art && !art.hidden) { try { window.qwenShellApi.closeArtifact(); } catch (e) {} }
    S.open = true;
    applyW(parseInt(lsGet(LS_W) || "", 10) || defaultW());
    panel.hidden = false;
    document.body.classList.add("bp-open");
    toggle.setAttribute("aria-pressed", "true");
    toggle.setAttribute("aria-label", t("close_panel"));
    toggle.setAttribute("data-tip", t("close_panel"));
    lsSet(LS_OPEN, "1");
    refreshState().then(function () {
      if (S.state && S.state.running) startFrames();
      sendView(true);
    });
    schedulePoll();
    if (opts && opts.focus) setTimeout(function () { (S.state && S.state.running ? urlIn : $("bpEx").querySelector("button") || urlIn).focus(); }, 30);
  }
  function closePanel(byUser) {
    if (!S.open) return;
    S.open = false;
    panel.hidden = true;
    document.body.classList.remove("bp-open");
    toggle.setAttribute("aria-pressed", "false");
    toggle.setAttribute("aria-label", t("open_panel"));
    toggle.setAttribute("data-tip", t("open_panel"));
    closeMenu();
    stopFrames();
    if (byUser) { S.userClosedAt = Date.now(); lsSet(LS_OPEN, "0"); }
    schedulePoll();
  }
  toggle.addEventListener("click", function () { if (S.open) closePanel(true); else openPanel({ focus: true }); });
  $("bpClose").addEventListener("click", function () { closePanel(true); toggle.focus(); });
  /* แผงแสดงผล (artifact) ใช้คอลัมน์ขวาเดียวกัน — เปิดอันหนึ่งปิดอีกอัน */
  var artEl = $("art");
  if (artEl && window.MutationObserver) {
    new MutationObserver(function () { if (!artEl.hidden && S.open) closePanel(false); }).observe(artEl, { attributes: true, attributeFilter: ["hidden"] });
  }
  addEventListener("resize", function () { if (S.open && !NARROW.matches) applyW(S.w || defaultW()); });

  /* ---- ปรับความกว้าง -------------------------------------------------------------- */
  var grip = $("bpGrip");
  grip.addEventListener("pointerdown", function (e) {
    if (e.button !== 0) return;
    e.preventDefault();
    grip.setPointerCapture(e.pointerId);
    S.dragging = true;
    document.body.classList.add("bp-drag");
  });
  grip.addEventListener("pointermove", function (e) {
    if (!S.dragging) return;
    applyW(innerWidth - e.clientX);
  });
  function endDrag() {
    if (!S.dragging) return;
    S.dragging = false;
    document.body.classList.remove("bp-drag");
    lsSet(LS_W, String(S.w));
    sendView(true);
  }
  grip.addEventListener("pointerup", endDrag);
  grip.addEventListener("pointercancel", endDrag);
  grip.addEventListener("keydown", function (e) {
    var step = e.shiftKey ? 80 : 24, w = S.w;
    if (e.key === "ArrowLeft") w += step; else if (e.key === "ArrowRight") w -= step;
    else if (e.key === "Home") w = 1e6; else if (e.key === "End") w = 0; else return;
    e.preventDefault();
    applyW(w);
    lsSet(LS_W, String(S.w));
    sendView(true);
  });

  /* ---- สถานะ -------------------------------------------------------------------- */
  function refreshState() {
    return api("state").then(function (st) { applyState(st); return st; }).catch(function (e) {
      if (e && !e.status) { try { console.warn("[qwen browser panel]", e); } catch (x) {} }   // ข้อผิดพลาดของโค้ดแผงเอง (ไม่ใช่เครือข่าย)
      return null;
    });
  }
  function schedulePoll() {
    clearTimeout(S.pollTimer);
    var hidden = document.visibilityState !== "visible";
    var ms = S.open ? (hidden ? 4000 : 1000) : (hidden ? 15000 : 4000);
    S.pollTimer = setTimeout(function () { refreshState().then(schedulePoll, schedulePoll); }, ms);
  }
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible") schedulePoll(); });

  function hostOf(u) { try { return new URL(u).host; } catch (e) { return ""; } }
  function applyState(st) {
    if (!st || typeof st !== "object") return;
    var prev = S.state;
    S.state = st;
    var running = !!st.running;
    /* Qwen เพิ่งใช้เบราว์เซอร์ → เปิดแผงให้เห็น (จอกว้างเท่านั้น และไม่เปิดซ้ำทันทีหลังผู้ใช้ปิดเอง) */
    var m = st.model || {};
    var fresh = m.at && (st.now || Date.now() / 1000) - m.at < 10;
    if (S.lastModelSeq >= 0 && m.seq > S.lastModelSeq && fresh && !S.open && !NARROW.matches && Date.now() - S.userClosedAt > 30000) {
      openPanel();
    }
    S.lastModelSeq = m.seq || 0;
    toggle.querySelector(".bp-live").hidden = !(running && fresh);
    if (!S.open) return;
    renderTabs(st);
    var tab = activeTab(st);
    if (document.activeElement !== urlIn) urlIn.value = tab && tab.url && tab.url !== "about:blank" ? tab.url : "";
    var sec = $("bpSec"), scheme = tab && tab.url ? String(tab.url).split(":")[0] : "";
    var secKind = scheme === "https" ? "lock" : scheme === "http" ? "unlock" : "search";
    if (sec.getAttribute("data-k") !== secKind) {
      sec.setAttribute("data-k", secKind);
      sec.innerHTML = icon(secKind);
      if (secKind === "search") { sec.removeAttribute("title"); sec.removeAttribute("aria-label"); sec.removeAttribute("role"); }
      else { var lbl = t(secKind === "lock" ? "secure" : "insecure"); sec.setAttribute("title", lbl); sec.setAttribute("role", "img"); sec.setAttribute("aria-label", lbl); }
    }
    var loading = !!(tab && tab.loading);
    var rl = $("bpReload");
    rl.innerHTML = loading ? icon("x") : icon("reload");
    rl.setAttribute("aria-label", t(loading ? "stop" : "reload"));
    rl.setAttribute("data-tip", t(loading ? "stop" : "reload"));
    var blank = !running || !tab || !tab.url || tab.url === "about:blank";
    $("bpEmpty").hidden = !blank;
    img.hidden = blank;
    $("bpWinT").textContent = st.headful ? t("panel_mode") : t("window_mode");
    renderNote(st, fresh && running ? m.what : "");
    if (running && !S.loopId) startFrames();
    if (!running && S.loopId) stopFrames();
    if (running && (!prev || !prev.running)) sendView(true);
  }
  function activeTab(st) {
    var tabs = (st && st.tabs) || [];
    for (var i = 0; i < tabs.length; i++) if (tabs[i].active) return tabs[i];
    return tabs[0] || null;
  }
  /* แท็บอัปเดตแบบคงองค์ประกอบเดิม (ตาม id) — ถ้าสร้างใหม่ทุกครั้งที่ชื่อ/สถานะโหลดเปลี่ยน การคลิกที่กดลงบนแท็บเดิม
     แล้วปล่อยบนแท็บที่ถูกแทนที่ไปแล้วจะไม่เป็น click (เจอจริงตอนกดสลับแท็บระหว่างหน้ากำลังโหลด) */
  function tabName(x) { return x.url === "about:blank" || !x.url ? t("blank") : (x.title || hostOf(x.url) || x.url); }
  function makeTab(id) {
    var b = el("div", { class: "bp-tab", role: "tab", "data-tab": id });
    var dot = el("span", { class: "bp-tab-dot", "aria-hidden": "true", hidden: true });
    var name = el("span", { class: "bp-tab-t" });
    var c = el("button", { type: "button", class: "icon-btn xs", tabindex: "-1" }, icon("x"));
    c.addEventListener("click", function (e) { e.stopPropagation(); api("nav", { action: "close", tab: id }).catch(fail); });
    b.addEventListener("click", function () {
      // ไม่เชื่อ aria-selected (สถานะในแผงอาจช้ากว่าเบราว์เซอร์ ~1 วินาที) — ส่งไปเสมอ ฝั่ง hub ไม่ทำอะไรถ้าเป็นแท็บเดิม
      api("nav", { action: "activate", tab: id }).then(restartFrames).catch(fail);
    });
    b.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); b.click(); }
      else if (e.key === "Delete") { e.preventDefault(); c.click(); }
      else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        var all = [].slice.call($("bpTabs").querySelectorAll(".bp-tab")), i = all.indexOf(b);
        var nx = all[(i + (e.key === "ArrowRight" ? 1 : -1) + all.length) % all.length];
        if (nx) { e.preventDefault(); nx.focus(); }
      }
    });
    b.appendChild(dot); b.appendChild(name); b.appendChild(c);
    return b;
  }
  function renderTabs(st) {
    var box = $("bpTabs"), tabs = st.tabs || [], keep = {};
    tabs.forEach(function (x, i) {
      keep[x.id] = true;
      var b = box.querySelector('.bp-tab[data-tab="' + CSS.escape(x.id) + '"]') || makeTab(x.id);
      var name = tabName(x);
      if (b.children[1].textContent !== name) b.children[1].textContent = name;
      b.children[0].hidden = !x.loading;
      if (b.getAttribute("aria-selected") !== String(!!x.active)) b.setAttribute("aria-selected", String(!!x.active));
      b.setAttribute("tabindex", x.active ? "0" : "-1");
      if ((b.getAttribute("title") || "") !== (x.url || "")) b.setAttribute("title", x.url || "");
      b.children[2].setAttribute("aria-label", t("close_tab") + " " + name);
      if (box.children[i] !== b) box.insertBefore(b, box.children[i] || null);
    });
    [].slice.call(box.querySelectorAll(".bp-tab")).forEach(function (b) {
      if (!keep[b.getAttribute("data-tab")]) {
        var wasFocused = b.contains(document.activeElement);
        b.remove();
        if (wasFocused) { var a = box.querySelector('.bp-tab[aria-selected="true"]'); if (a) a.focus(); }
      }
    });
  }
  function showNote(text, kind, actions) {
    note.textContent = "";
    note.className = "bp-note" + (kind ? " " + kind : "");
    note.appendChild(el("span", { class: "bp-note-t", text: text }));
    (actions || []).forEach(function (a) { note.appendChild(a); });
    note.hidden = !text;
  }
  function btn(label, cls, fn) {
    var b = el("button", { type: "button", class: "bp-b" + (cls ? " " + cls : ""), text: label });
    b.addEventListener("click", fn);
    return b;
  }
  var noteSig = "";
  function renderNote(st, qwenWhat) {
    var d = st.dialog, sig;
    if (d) {
      sig = "d|" + d.at;
      if (sig === noteSig) return;
      noteSig = sig;
      var input = null;
      if (d.type === "prompt") { input = el("input", { type: "text", "aria-label": d.message || t("dialog_q") }); input.value = d.default || ""; }
      var acts = [];
      if (input) acts.push(input);
      acts.push(btn(t("ok"), "ink", function () { api("dialog", { accept: true, text: input ? input.value : null }).catch(fail); }));
      acts.push(btn(t("cancel"), "", function () { api("dialog", { accept: false }).catch(fail); }));
      showNote(t("dialog_q") + ": " + (d.message || ""), "warn", acts);
      return;
    }
    if (st.error && !st.running) {
      sig = "e|" + st.error;
      if (sig === noteSig) return;
      noteSig = sig;
      showNote(t("err") + ": " + st.error, "warn");
      return;
    }
    if (st.starting && !st.running) {
      sig = "s";
      if (sig === noteSig) return;
      noteSig = sig;
      showNote(t("starting"), "");
      return;
    }
    // ข้อความแจ้ง (ดาวน์โหลดเสร็จ / หน้าเว็บแจ้ง) มาก่อนบรรทัด "Qwen กำลังใช้เบราว์เซอร์" เมื่อเพิ่งเกิด (15 วินาที) หรือใหม่กว่า
    var nowS = st.now || Date.now() / 1000, nAt = st.noticeAt || 0;
    var noticeFirst = st.notice && (!qwenWhat || nowS - nAt < 15 || nAt >= ((st.model || {}).at || 0));
    if (qwenWhat && !noticeFirst) {
      sig = "q|" + qwenWhat;
      if (sig === noteSig) return;
      noteSig = sig;
      showNote(t("qwen_doing") + " · " + qwenWhat, "qwen");
      return;
    }
    if (st.notice) {
      sig = "n|" + st.notice;
      if (sig === noteSig) return;
      noteSig = sig;
      var acts = [];
      // ไฟล์ที่ดาวน์โหลดเสร็จ: เปิดจาก /_qwen/out/ ของพอร์ตนี้ (hub เสิร์ฟพร้อม nosniff/sandbox อยู่แล้ว)
      if (st.noticeLink && /^\/_qwen\/out\/[^\/]+$/.test(st.noticeLink)) {
        acts.push(btn(t("open_file"), "", function () { window.open(st.noticeLink, "_blank", "noopener"); }));
      }
      acts.push(btn(t("dismiss"), "", function () { api("notice", {}).catch(function () {}); showNote(""); noteSig = ""; }));
      showNote(st.notice, "", acts);
      return;
    }
    if (st.headful && st.running) {
      sig = "w";
      if (sig === noteSig) return;
      noteSig = sig;
      showNote(t("window_note"), "", [btn(t("panel_mode"), "", function () { switchMode(false); })]);
      return;
    }
    if (noteSig) { noteSig = ""; showNote(""); }
  }
  function fail(e) { toast((e && e.message) || String(e), true); }

  /* ---- ภาพสด --------------------------------------------------------------------- */
  function startFrames() {
    if (S.loopId) return;
    var id = S.loopId = Date.now() + Math.random();
    var ctl = window.AbortController ? new AbortController() : null;
    S.frameCtl = ctl;
    (function loop() {
      if (S.loopId !== id || !S.open) return;
      fetch(API + "frame?after=" + S.seq + "&wait=20", { cache: "no-store", credentials: "same-origin", signal: ctl ? ctl.signal : undefined })
        .then(function (r) {
          if (S.loopId !== id) return null;
          if (r.status === 200) {
            S.seq = +r.headers.get("X-Frame-Seq") || S.seq;
            S.fw = +r.headers.get("X-Frame-W") || S.fw;
            S.fh = +r.headers.get("X-Frame-H") || S.fh;
            return r.blob().then(function (b) {
              if (S.loopId !== id) return;
              var u = URL.createObjectURL(b), old = S.url;
              img.onload = function () { if (old) URL.revokeObjectURL(old); };
              img.src = u;
              S.url = u;
            });
          }
          if (r.status === 409) { return new Promise(function (res) { setTimeout(res, 1500); }); }
          if (r.status !== 204) return new Promise(function (res) { setTimeout(res, 1000); });
          return null;
        })
        .catch(function () { return new Promise(function (res) { setTimeout(res, 1000); }); })
        .then(function () { if (S.loopId === id) setTimeout(loop, 0); });
    })();
  }
  function stopFrames() {
    S.loopId = 0;
    if (S.frameCtl) { try { S.frameCtl.abort(); } catch (e) {} S.frameCtl = null; }
  }
  function restartFrames() { stopFrames(); S.seq = 0; startFrames(); }

  /* ขนาดช่องแสดงผล = ขนาดหน้าจอของเบราว์เซอร์ (ภาพ 1:1 ไม่ยืด) */
  var viewTimer = 0;
  function sendView(now) {
    clearTimeout(viewTimer);
    viewTimer = setTimeout(function () {
      if (!S.open || !S.state || !S.state.running) return;
      var r = view.getBoundingClientRect();
      if (r.width < 50 || r.height < 50) return;
      var dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
      var sig = Math.round(r.width) + "x" + Math.round(r.height) + "@" + dpr;
      if (sig === S.viewSent) return;
      S.viewSent = sig;
      api("view", { w: Math.round(r.width), h: Math.round(r.height), dpr: dpr }).catch(function () { S.viewSent = ""; });
    }, now ? 30 : 250);
  }
  if (window.ResizeObserver) new ResizeObserver(function () { sendView(false); }).observe(view);

  /* ---- เมาส์ ---------------------------------------------------------------------- */
  function toPage(e) {
    var r = view.getBoundingClientRect(), fw = S.fw || r.width, fh = S.fh || r.height;
    var scale = Math.min(r.width / fw, r.height / fh) || 1;
    var x = (e.clientX - r.left) / scale, y = (e.clientY - r.top) / scale;
    if (x < 0 || y < 0 || x > fw || y > fh) return null;
    return { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 };
  }
  function mods(e) { return (e.altKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.metaKey ? 4 : 0) | (e.shiftKey ? 8 : 0); }
  var BTN = ["left", "middle", "right"];
  img.addEventListener("pointerdown", function (e) {
    var p = toPage(e);
    if (!p) return;
    e.preventDefault();
    focusTyping(e);
    S.pointerDown = BTN[e.button] || "left";
    try { img.setPointerCapture(e.pointerId); } catch (x) {}
    sendInput({ type: "mouse", event: "down", x: p.x, y: p.y, button: S.pointerDown, clicks: Math.max(1, e.detail || 1), mods: mods(e) });
  });
  img.addEventListener("pointerup", function (e) {
    if (!S.pointerDown) return;
    var p = toPage(e) || S.lastPoint;
    var b = S.pointerDown;
    S.pointerDown = false;
    if (p) sendInput({ type: "mouse", event: "up", x: p.x, y: p.y, button: b, clicks: Math.max(1, e.detail || 1), mods: mods(e) });
  });
  img.addEventListener("pointermove", function (e) {
    var p = toPage(e);
    if (!p) return;
    S.lastPoint = p;
    var now = Date.now();
    if (now - S.lastMove < (S.pointerDown ? 30 : 90)) return;
    S.lastMove = now;
    sendInput({ type: "mouse", event: "move", x: p.x, y: p.y, button: S.pointerDown || "none", mods: mods(e) });
  });
  img.addEventListener("contextmenu", function (e) { e.preventDefault(); });
  view.addEventListener("wheel", function (e) {
    if (img.hidden) return;
    var p = toPage(e);
    if (!p) return;
    e.preventDefault();
    var k = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? 800 : 1;
    if (!S.wheel) {
      S.wheel = { x: p.x, y: p.y, dx: 0, dy: 0, mods: mods(e) };
      setTimeout(function () {
        var w = S.wheel; S.wheel = null;
        if (w && (w.dx || w.dy)) sendInput({ type: "mouse", event: "wheel", x: w.x, y: w.y, dx: w.dx, dy: w.dy, mods: w.mods });
      }, 40);
    }
    S.wheel.dx += e.deltaX * k;
    S.wheel.dy += e.deltaY * k;
  }, { passive: false });

  /* ---- คีย์บอร์ด: textarea ซ่อนรับตัวอักษร (รวม IME/ภาษาไทย) → insertText; ปุ่มพิเศษส่งเป็น key event ------- */
  function focusTyping(e) {
    if (e) { var r = view.getBoundingClientRect(); ime.style.left = Math.max(0, e.clientX - r.left) + "px"; ime.style.top = Math.max(0, e.clientY - r.top) + "px"; }
    if (document.activeElement !== ime) { try { ime.focus({ preventScroll: true }); } catch (x) { ime.focus(); } }
  }
  view.addEventListener("focus", function () { if (!img.hidden) focusTyping(); });
  ime.addEventListener("focus", function () { view.classList.add("focus"); });
  ime.addEventListener("blur", function () { view.classList.remove("focus"); });
  var SPECIAL = { Enter: 13, Backspace: 8, Tab: 9, Escape: 27, Delete: 46, ArrowUp: 38, ArrowDown: 40, ArrowLeft: 37, ArrowRight: 39,
    Home: 36, End: 35, PageUp: 33, PageDown: 34, Insert: 45, F1: 112, F2: 113, F3: 114, F4: 115, F5: 116, F6: 117, F7: 118,
    F8: 119, F9: 120, F10: 121, F11: 122, F12: 123 };
  function keyDoc(e, kind) {
    var vk = SPECIAL[e.key] || (e.key && e.key.length === 1 ? e.key.toUpperCase().charCodeAt(0) : 0);
    return { type: "key", event: kind, key: e.key, code: e.code || "", keyCode: vk, text: kind === "down" && e.key === "Enter" ? "\r" : "", mods: mods(e) };
  }
  ime.addEventListener("keydown", function (e) {
    if (e.isComposing || e.keyCode === 229) return;
    var combo = e.ctrlKey || e.metaKey || e.altKey;
    if (combo && !e.altKey && (e.key === "v" || e.key === "V")) return;            // วาง: ให้ event paste ทำงาน
    if (combo && !e.altKey && (e.key === "c" || e.key === "C" || e.key === "x" || e.key === "X")) {
      e.preventDefault();
      api("input", { type: "copy" }).then(function (d) {
        if (d && d.text && navigator.clipboard) navigator.clipboard.writeText(d.text).catch(function () {});
        if (e.key.toLowerCase() === "x") sendInput({ type: "key", event: "down", key: "Delete", code: "Delete", keyCode: 46, mods: 0 }).then(function () { sendInput({ type: "key", event: "up", key: "Delete", code: "Delete", keyCode: 46, mods: 0 }); });
      }).catch(function () {});
      return;
    }
    if (SPECIAL[e.key] || combo) {
      e.preventDefault();
      sendInput(keyDoc(e, "down"));
    }
  });
  ime.addEventListener("keyup", function (e) {
    if (e.isComposing || e.keyCode === 229) return;
    var combo = e.ctrlKey || e.metaKey || e.altKey;
    if (SPECIAL[e.key] || (combo && !/^[cvxCVX]$/.test(e.key))) { e.preventDefault(); sendInput(keyDoc(e, "up")); }
  });
  function flushText() {
    var v = ime.value;
    if (!v) return;
    ime.value = "";
    sendInput({ type: "text", text: v });
  }
  ime.addEventListener("input", function (e) { if (!e.isComposing) flushText(); });
  ime.addEventListener("compositionend", function () { setTimeout(flushText, 0); });
  ime.addEventListener("paste", function (e) {
    var txt = e.clipboardData && e.clipboardData.getData("text/plain");
    e.preventDefault();
    if (txt) sendInput({ type: "text", text: txt });
  });

  /* ---- ปุ่มนำทาง / แถบที่อยู่ / เมนู --------------------------------------------------------- */
  /* url = เปิดหน้านี้ทันทีที่เบราว์เซอร์พร้อม (hub ตรวจที่อยู่ก่อนเปิดเบราว์เซอร์ — ที่อยู่ต้องห้ามไม่ทำให้ Edge เปิดเปล่าๆ) */
  function ensureRunning(url) {
    if (S.state && S.state.running) return Promise.resolve(S.state);
    S.starting = true;
    noteSig = "s";
    showNote(t("starting"), "");
    return api("start", url ? { url: url } : {}).then(function (st) { S.starting = false; applyState(st); restartFrames(); sendView(true); return st; },
      function (e) { S.starting = false; if (noteSig === "s") { noteSig = ""; showNote(""); } throw e; });
  }
  $("bpUrlForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var u = urlIn.value.trim();
    if (!u) return;
    var go = S.state && S.state.running ? api("nav", { action: "go", url: u }) : ensureRunning(u);
    go.then(function () {
      urlIn.blur();
      focusTyping();
    }).catch(fail);
  });
  urlIn.addEventListener("focus", function () { try { urlIn.select(); } catch (e) {} });
  urlIn.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { var tab = activeTab(S.state); urlIn.value = tab && tab.url !== "about:blank" ? tab.url : ""; urlIn.blur(); }
  });
  $("bpBack").addEventListener("click", function () { api("nav", { action: "back" }).catch(fail); });
  $("bpFwd").addEventListener("click", function () { api("nav", { action: "forward" }).catch(fail); });
  $("bpReload").addEventListener("click", function () {
    var tab = activeTab(S.state);
    api("nav", { action: tab && tab.loading ? "stop" : "reload" }).catch(fail);
  });
  $("bpNewTab").addEventListener("click", function () {
    ensureRunning().then(function () { return api("nav", { action: "newtab" }); }).then(function () { restartFrames(); urlIn.focus(); }).catch(fail);
  });
  var menu = $("bpMenu"), moreBtn = $("bpMore");
  function closeMenu() { menu.hidden = true; moreBtn.setAttribute("aria-expanded", "false"); }
  moreBtn.addEventListener("click", function () {
    var open = menu.hidden;
    menu.hidden = !open;
    moreBtn.setAttribute("aria-expanded", String(open));
    if (open) menu.querySelector("button").focus();
  });
  menu.addEventListener("keydown", function (e) {
    var items = [].slice.call(menu.querySelectorAll("button")), i = items.indexOf(document.activeElement);
    if (e.key === "Escape") { e.preventDefault(); closeMenu(); moreBtn.focus(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
  });
  document.addEventListener("pointerdown", function (e) { if (!menu.hidden && !menu.contains(e.target) && e.target !== moreBtn && !moreBtn.contains(e.target)) closeMenu(); }, true);
  function switchMode(windowed) {
    closeMenu();
    noteSig = "s";
    showNote(t("starting"), "");
    api("start", { window: windowed }).then(function (st) { applyState(st); restartFrames(); S.viewSent = ""; sendView(true); })
      .catch(function (e) { if (noteSig === "s") { noteSig = ""; showNote(""); } fail(e); });
  }
  $("bpWin").addEventListener("click", function () { switchMode(!(S.state && S.state.headful)); });
  $("bpQuit").addEventListener("click", function () { closeMenu(); api("stop", {}).then(function (st) { applyState(st); stopFrames(); }).catch(fail); });

  /* ตัวอย่างในหน้าว่าง: เติมคำขอลงช่องพิมพ์ของแชต (ไม่ส่งเอง) */
  function askQwen(text) {
    try {
      var f = $("frame"), enh = f && f.contentWindow && f.contentWindow.qwenEnhance;
      if (enh && enh.prefill && enh.prefill(text)) { f.focus(); return; }
    } catch (e) {}
    toast(text);
  }

  /* Esc ในแผง (นอกช่องพิมพ์ของหน้าเว็บ) = ปิดเมนู/ปิดแผง บนจอแคบ */
  panel.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && e.target !== ime && e.target !== urlIn && menu.hidden && NARROW.matches) { closePanel(true); toggle.focus(); }
  });

  window.qwenBrowserPanel = {
    version: 1,
    open: function () { openPanel({ focus: true }); },
    close: function () { closePanel(false); },
    isOpen: function () { return S.open; },
    state: function () { return S.state; }
  };

  /* เริ่ม: ถามสถานะเป็นระยะ (ตรวจว่า Qwen เริ่มใช้เบราว์เซอร์หรือยัง) · เปิดแผงคืนถ้าผู้ใช้เปิดค้างไว้ครั้งก่อนและเบราว์เซอร์ยังทำงาน */
  refreshState().then(function (st) {
    if (st && st.running && lsGet(LS_OPEN) === "1" && !NARROW.matches) openPanel();
    schedulePoll();
  });
})();
