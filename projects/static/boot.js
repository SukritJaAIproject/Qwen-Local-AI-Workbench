/* boot.js — รันใน <head> ของหน้า shell ก่อน iframe ของ WebUI เริ่มโหลด
 *
 * ทำไมต้องเขียนค่าเอง ทั้งที่มี --ui-config-file:
 *   WebUI หยิบค่าจาก /props ก็ต่อเมื่อ default_generation_settings.params ไม่ว่าง
 *   และเป็นการเปิดครั้งแรกของเบราว์เซอร์นั้น ใน router mode params เป็น null เสมอ
 *   ค่าจาก ui-config.json จึงถูกมองข้ามทั้งไฟล์ (ธีมไม่ติด MCP ไม่ถูกลงทะเบียน)
 *
 * shell กับ iframe อยู่ origin เดียวกัน ใช้ localStorage ก้อนเดียวกัน
 * เขียนตรงนี้แล้ว WebUI ใน iframe อ่านเจอตอนเริ่มทำงาน
 *
 * ข้อมูลจากเซิร์ฟเวอร์: window.__QWEN_BOOT__ = {version, prefs, defaults, owned, mcpServers, toolPolicy}
 * API สำหรับหน้า shell: window.qwenBoot.{getTheme,setTheme,getFont,setFont,resolvedTheme}
 *
 * mcpServers ของเรามี headers = สตริง JSON {"Authorization":"Bearer <โทเคน>"} (MCP ต้องการตามสัญญา C2)
 * โทเคนเป็นความลับ: ห้าม console.log / ส่งไปที่อื่น — อยู่แค่ใน LlamaUi.config ของ origin พอร์ตโปรเจกต์
 */
(function () {
  "use strict";
  var BOOT = window.__QWEN_BOOT__ || {};
  var CFG_KEY = "LlamaUi.config";
  var VER_KEY = "qwen-boot-version";
  var THEME_KEY = "qwen-theme";       // dark | light | system — ค่าที่ผู้ใช้เลือก
  var FONT_KEY = "qwen-font";         // serif | sans — ฟอนต์ของคำตอบ
  var MW_KEY = "mode-watcher-mode";   // ที่ WebUI (mode-watcher) อ่าน

  function readJSON(key, fallback) {
    try { var v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; }
    catch (e) { return fallback; }
  }
  function write(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* โหมดส่วนตัว/ถูกบล็อก */ }
  }

  /* ---- 1. ค่าตั้งของ WebUI ------------------------------------------------ */
  try {
    var cfg = readJSON(CFG_KEY, {}) || {};
    var changed = false;
    var defaults = BOOT.defaults || {};
    for (var k in defaults) {
      if (!(k in cfg)) { cfg[k] = defaults[k]; changed = true; }
    }
    // คีย์ที่เป็นของโปรเจกต์ (เช่นคำสั่งของโปรเจกต์) เขียนทับทุกครั้ง
    // ไม่งั้นแก้คำสั่งที่แผงโปรเจกต์แล้ว WebUI ยังใช้ค่าเก่าที่จำไว้
    var owned = BOOT.owned || {};
    for (var o in owned) {
      if (cfg[o] !== owned[o]) { cfg[o] = owned[o]; changed = true; }
    }

    // MCP: เซิร์ฟเวอร์ที่เราเป็นเจ้าของ (ตาม id) ถูกแทนเมื่อเลขรุ่นขยับ
    // ตัวที่ผู้ใช้เพิ่มเองผ่านหน้าตั้งค่าของ WebUI ต้องอยู่ครบ ไม่หายไปกับการอัปเดต
    // enabled ของตัวเราที่ผู้ใช้เคยเปิด/ปิดเองคงไว้ (ขยับเลขรุ่นเพื่อเปลี่ยน URL/โทเคน ไม่ใช่เพื่อเปิดของที่ผู้ใช้ปิด)
    var ours = BOOT.mcpServers || [];
    var ownById = {};
    ours.forEach(function (s) { if (s && s.id) ownById[s.id] = s; });
    var storedVer = parseInt(localStorage.getItem(VER_KEY) || "0", 10) || 0;
    var current = [];
    try { current = JSON.parse(cfg.mcpServers || "[]") || []; } catch (e) { current = []; }
    if (!Array.isArray(current)) current = [];
    if (ours.length && (storedVer < (BOOT.version || 0) || !cfg.mcpServers)) {
      var prevEnabled = {}, prevHeaders = {};
      current.forEach(function (s) {
        if (!s || !ownById[s.id]) return;
        if (typeof s.enabled === "boolean") prevEnabled[s.id] = s.enabled;
        if (s.headers) prevHeaders[s.id] = s.headers;
      });
      var kept = current.filter(function (s) { return s && !ownById[s.id]; });
      var fresh = ours.map(function (s) {
        var c = {};
        for (var k in s) c[k] = s[k];
        if (s.id in prevEnabled) c.enabled = prevEnabled[s.id];
        // hub อ่านโทเคนไม่ได้รอบนี้ — ใช้ค่าที่เก็บไว้เดิมไปก่อน ดีกว่าลบทิ้งแล้วติด 401
        if (!c.headers && prevHeaders[s.id]) c.headers = prevHeaders[s.id];
        return c;
      });
      cfg.mcpServers = JSON.stringify(fresh.concat(kept));
      changed = true;
      write(VER_KEY, String(BOOT.version || 0));
    } else if (ours.length && current.length) {
      // โทเคน (headers) เป็นของเรา เขียนทับทุกครั้งที่เปิดหน้า เหมือน owned — ไฟล์โทเคนถูกสร้างใหม่เมื่อไร
      // เบราว์เซอร์ที่เปิดค้างไว้ต้องได้ค่าใหม่ทันทีที่รีโหลด ไม่ใช่ติด 401 จนกว่าเลขรุ่นจะขยับ
      // useProxy ของเราต้องปิดเสมอ: /cors-proxy ของ llama-server ถูกถอดออกแล้ว
      // hub อ่านโทเคนไม่ได้ (ไม่มี headers) = ไม่แตะค่าที่เก็บไว้
      var synced = false;
      current.forEach(function (s) {
        var o = s && ownById[s.id];
        if (!o) return;
        if (o.headers && s.headers !== o.headers) { s.headers = o.headers; synced = true; }
        if (s.useProxy) { s.useProxy = false; synced = true; }
      });
      if (synced) { cfg.mcpServers = JSON.stringify(current); changed = true; }
    }
    if (changed) write(CFG_KEY, JSON.stringify(cfg));
  } catch (e) { /* ค่าตั้งพังก็ยังเปิดหน้าได้ แค่ใช้ค่าเริ่มต้นของ WebUI */ }

  /* ---- 1b. สิทธิ์เรียกเครื่องมือ ------------------------------------------- */
  // WebUI (b10984) ถามผู้ใช้ก่อนเรียกเครื่องมือทุกครั้ง ยกเว้นคีย์ที่อยู่ใน LlamaUi.alwaysAllowedTools
  // (array ของ "mcp-<id>:<ชื่อเครื่องมือ>" ที่ได้จากปุ่ม "อนุญาตเสมอ" หรือสวิตช์ในหน้าเครื่องมือ)
  // เบราว์เซอร์ใหม่ (ยังไม่มีคีย์นี้) = เขียนรายการเริ่มต้นไว้ชัดเจน โดยตัดเครื่องมือที่เขียนไฟล์/รันโปรแกรม
  // (toolPolicy.ask) ออกเสมอ → local_do และเครื่องมือเขียน/รันของผิวเต็ม "ถามทุกครั้ง"
  // มีคีย์อยู่แล้ว = ผู้ใช้เลือกเองแล้ว ไม่แตะ (ไม่ถอนสิทธิ์ที่ผู้ใช้ให้ไว้เอง)
  // คีย์ชื่อเก่า LlamaCppWebui.* ก็นับเป็นการเลือกของผู้ใช้: WebUI คัดลอกไปชื่อใหม่เองเฉพาะเมื่อชื่อใหม่ยังว่าง
  // (migration "localstorage-prefix-v1") ถ้าเราเขียนชื่อใหม่ก่อน ค่าเก่าของผู้ใช้จะหายเงียบๆ
  try {
    var ALLOW_KEY = "LlamaUi.alwaysAllowedTools";
    var LEGACY_ALLOW_KEY = "LlamaCppWebui.alwaysAllowedTools";
    var pol = BOOT.toolPolicy || null;
    if (pol && localStorage.getItem(ALLOW_KEY) === null && localStorage.getItem(LEGACY_ALLOW_KEY) === null) {
      var askSet = {};
      (pol.ask || []).forEach(function (k) { askSet[k] = true; });
      var seed = (pol.allow || []).filter(function (k) { return typeof k === "string" && !askSet[k]; });
      write(ALLOW_KEY, JSON.stringify(seed));
    }
    // ข้อยกเว้นเดียวที่ถอนสิทธิ์ที่ผู้ใช้ให้ไว้: local_confirm คือด่านที่ "คน" กดอนุมัติคำสั่งที่เปลี่ยนเครื่อง
    // ถ้าอยู่ในรายการ "อนุญาตเสมอ" (กดทีละตัว หรือ "อนุญาตทุกเครื่องมือของเซิร์ฟเวอร์นี้" ซึ่ง WebUI
    // เก็บเป็นคีย์รายตัวเหมือนกัน) การยืนยันสองขั้นจะเหลือแค่โมเดลตัดสินใจเอง — ตัดออกทุกครั้งที่เปิดหน้า
    // (ทำก่อน iframe โหลด WebUI จึงอ่านรายการที่ตัดแล้ว) ชื่อคีย์เก่าก็ตัดด้วย เพราะ WebUI ย้ายค่ามาเอง
    var CONFIRM_KEYS = { "mcp-local:local_confirm": 1, "mcp-local-full:local_confirm": 1 };
    [ALLOW_KEY, LEGACY_ALLOW_KEY].forEach(function (key) {
      var raw = localStorage.getItem(key);
      if (!raw) return;
      var list;
      try { list = JSON.parse(raw); } catch (e2) { return; }
      if (!Array.isArray(list)) return;
      var kept = list.filter(function (k) { return !CONFIRM_KEYS[k]; });
      if (kept.length !== list.length) write(key, JSON.stringify(kept));
    });
  } catch (e) { /* ไม่มี localStorage = WebUI ถามทุกครั้งอยู่แล้ว */ }

  /* ---- 2. ค่าที่ผู้ใช้เลือก (ธีม ฟอนต์) ------------------------------------ */
  // แต่ละโปรเจกต์อยู่คนละพอร์ต = คนละ origin = localStorage คนละก้อน
  // ถ้าเก็บแค่ใน localStorage เลือกธีมสว่างในโปรเจกต์หนึ่ง อีกโปรเจกต์ยังมืดอยู่
  // hub จึงเป็นเจ้าของค่าจริง ค่าจากเซิร์ฟเวอร์ชนะเสมอตอนเปิดหน้า
  var prefs = BOOT.prefs || {};
  if (prefs.theme) write(THEME_KEY, prefs.theme);
  if (prefs.font) write(FONT_KEY, prefs.font);

  function savePref(key, value) {
    var hub = (window.qwenShell && window.qwenShell.hub) || "";
    if (!hub || !window.fetch) return;
    var body = {}; body[key] = value;
    fetch(hub + "/api/settings", {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).catch(function () { /* hub ไม่ตอบ: ค่ายังอยู่ใน localStorage ของพอร์ตนี้ */ });
  }

  /* ---- 3. ธีม -------------------------------------------------------------- */
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function getTheme() {
    var t = null;
    try { t = localStorage.getItem(THEME_KEY); } catch (e) {}
    if (t === "dark" || t === "light" || t === "system") return t;
    // ยังไม่เคยเลือก: ใช้ค่าที่ WebUI เคยเก็บไว้ ไม่งั้นมืดตามที่ผู้ใช้ขอไว้ตั้งแต่แรก
    var mw = null;
    try { mw = localStorage.getItem(MW_KEY); } catch (e) {}
    return (mw === "light" || mw === "system") ? mw : "dark";
  }
  function resolvedTheme(pref) {
    pref = pref || getTheme();
    if (pref === "system") return media && media.matches ? "dark" : "light";
    return pref;
  }
  function applyTheme() {
    var r = resolvedTheme();
    document.documentElement.setAttribute("data-theme", r);
    document.documentElement.style.colorScheme = r;
  }
  function setTheme(pref) {
    if (pref !== "dark" && pref !== "light" && pref !== "system") return;
    write(THEME_KEY, pref);
    write(MW_KEY, pref);                      // iframe ได้ storage event แล้วเปลี่ยนตาม
    var cfg = readJSON(CFG_KEY, {}) || {};
    cfg.theme = pref;                         // ให้หน้าตั้งค่าของ WebUI แสดงค่าตรงกัน
    write(CFG_KEY, JSON.stringify(cfg));
    applyTheme();
    savePref("theme", pref);
    try { window.dispatchEvent(new CustomEvent("qwen:theme", { detail: resolvedTheme(pref) })); } catch (e) {}
  }

  // ให้ WebUI เริ่มด้วยธีมเดียวกับ shell เสมอ
  (function syncOnBoot() {
    var pref = getTheme();
    write(MW_KEY, pref);
    applyTheme();
  })();
  if (media && media.addEventListener) {
    media.addEventListener("change", function () { if (getTheme() === "system") applyTheme(); });
  }

  /* ---- 4. ฟอนต์ของคำตอบ ---------------------------------------------------- */
  function getFont() {
    var f = null;
    try { f = localStorage.getItem(FONT_KEY); } catch (e) {}
    return f === "sans" ? "sans" : "serif";
  }
  function setFont(f) {
    if (f !== "serif" && f !== "sans") return;
    write(FONT_KEY, f);
    savePref("font", f);
    try { window.dispatchEvent(new CustomEvent("qwen:font", { detail: f })); } catch (e) {}
  }

  window.qwenBoot = {
    getTheme: getTheme, setTheme: setTheme, resolvedTheme: resolvedTheme,
    getFont: getFont, setFont: setFont,
    keys: { theme: THEME_KEY, font: FONT_KEY, modeWatcher: MW_KEY, config: CFG_KEY }
  };
})();
