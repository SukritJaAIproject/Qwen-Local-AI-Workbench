/* webui-enhance.js — พฤติกรรมเสริมภายใน iframe ของ WebUI (llama.cpp, SvelteKit ที่คอมไพล์แล้ว)
 *
 * แก้ซอร์สของ WebUI ไม่ได้ จึงทำงานจากภายนอกทั้งหมด:
 *   - ตั้ง attribute บน <html> ให้ webui-theme.css ใช้เป็นตัวเลือก (data-theme, data-qw-*)
 *   - แทรก hero (คำทักทาย) + ชิปคำแนะนำ บนหน้าเริ่มแชต และเปลี่ยน placeholder ของกล่องพิมพ์
 *   - เปิด window.qwenEnhance ให้หน้า shell สั่งงาน (ดู DESIGN.md ข้อ 5b)
 *   - รอบ 4 (K5-K9, ส่วนท้ายไฟล์): แจ้ง shell เมื่อคำตอบจบ/รออนุญาต/ถึงรอบเอเจนต์สูงสุด (qwenShellApi.notify),
 *     ชิป "เร็ว (4B)" ข้างปุ่ม "+" ของกล่องพิมพ์, ปุ่ม "เปิดในแผง" (qwenShellApi.openArtifact), อ่านออกเสียง, "ถามเรื่องนี้"
 *     แก้หลังรีวิว UX: เนื้อความแจ้งเตือนจาก IndexedDB, ถามก่อนโหลดโมเดลใหญ่, ชิปไม่ขยับ, แผงตามรุ่นใหม่ของชิ้นที่เปิดอยู่
 *
 * Svelte วาด DOM ใหม่ได้ทุกเมื่อ ทุกอย่างที่แทรกจึงต้องทำซ้ำได้โดยไม่ซ้อน (idempotent)
 * และถูกเรียกใหม่จาก MutationObserver ที่ถูกจำกัดความถี่ไว้ไม่เกินเฟรมละครั้ง
 */
(function () {
  "use strict";
  if (window.qwenEnhance) return;           // กันสคริปต์ถูกฉีดซ้ำ

  /* ---- ซ่อมหน้า shell เก่าที่ค้างอยู่ในเบราว์เซอร์ --------------------------------
     service worker (Workbox) ของ WebUI เคย precache "./" ซึ่งบนพอร์ตโปรเจกต์คือหน้า shell
     เบราว์เซอร์ที่เคยเปิดไว้ก่อนการปรับหน้าตาจึงได้ shell ฉบับเก่า (iframe กว้าง 300px
     ที่เหลือเป็นพื้นดำ) ครอบหน้าแชตใหม่ — เจอจริงในเบราว์เซอร์ของผู้ใช้ 2026-09-24
     hub เสิร์ฟ /sw.js ตัวใหม่ที่ล้างแคชให้แล้ว แต่ต้องรอเบราว์เซอร์เช็กอัปเดตเอง
     หน้าแชตนี้โหลดสดจากเซิร์ฟเวอร์เสมอ จึงเป็นจุดที่รู้ตัวได้ทันที:
     parent ไม่มี qwenShell = shell เก่า → ถอด SW + ล้าง Cache Storage แล้วโหลดหน้าบนสุดใหม่
     ไม่แตะ IndexedDB/localStorage (แชตและค่าตั้งของผู้ใช้อยู่ที่นั่น) และทำครั้งเดียวต่อแท็บ
     (sessionStorage ใช้ร่วมกับ parent ที่ origin เดียวกัน) ถ้ายังไม่หายก็ไม่วนรีโหลด */
  (function healStaleShell() {
    try {
      var p = window.parent;
      if (!p || p === window || p.qwenShell) return;
      if (p.location.origin !== location.origin) return;
      if (sessionStorage.getItem("qwen-shell-heal")) return;
      sessionStorage.setItem("qwen-shell-heal", String(Date.now()));
      var jobs = [];
      if (navigator.serviceWorker && navigator.serviceWorker.getRegistrations) {
        jobs.push(navigator.serviceWorker.getRegistrations().then(function (rs) {
          return Promise.all(rs.map(function (r) { return r.unregister(); }));
        }));
      }
      if (window.caches && caches.keys) {
        jobs.push(caches.keys().then(function (ks) {
          return Promise.all(ks.map(function (k) { return caches.delete(k); }));
        }));
      }
      Promise.all(jobs).catch(function () {}).then(function () { p.location.reload(); });
    } catch (e) { /* parent คนละ origin หรือถูกบล็อก — ปล่อยไว้ */ }
  })();

  /* ---- ALLOW-GUARD (รอบ 5 แก้หลังรีวิว, 2026-09-30): local_confirm ต้องมีการ์ดให้คนกดทุกครั้ง -----------------------
     ปัญหาที่รีวิวความปลอดภัยพบ: WebUI b10984 เก็บรายการ "อนุญาตเสมอ" ไว้ใน Set ในหน่วยความจำ (p2._tools, SvelteSet)
     แล้วเขียนสำเนาลง localStorage "LlamaUi.alwaysAllowedTools" แต่อ่านกลับจาก localStorage แค่ตอนเปิดหน้า
     "อนุญาตทุกเครื่องมือจาก <เซิร์ฟเวอร์>" บนการ์ดของเครื่องมืออื่น (เช่น local_do) หรือสวิตช์ "อนุญาตเสมอ" ในหน้าตั้งค่า
     จึงใส่ local_confirm ลง Set นั้นไปด้วย → requestPermission() ตอบ "อนุญาต" เองโดยไม่มีการ์ด ไม่มีใครเห็น review
     โมเดลยืนยัน token ไหนก็ได้จนกว่าจะโหลดหน้าใหม่ (boot.js ตัดคีย์ออกแค่ตอนเปิดหน้า)
     ส่วนนี้คือด่านที่ไม่พึ่งว่าคนกดตรงไหน (ส่วน UI ที่ซ่อนเมนู/ล็อกสวิตช์อยู่ท้ายส่วน R4) ติดตั้งก่อนส่วนอื่นทั้งหมด ไม่พึ่ง DOM:
       1) ดัก Storage.prototype.setItem: WebUI เขียนรายการนี้ทันทีหลังเพิ่มลง Set (p2.persist() ในจังหวะเดียวกับ
          allowTool/allowTools ก่อนเรียกเครื่องมือถัดไป) ถ้ามีคีย์ของ local_confirm → หา Set ที่เพิ่งรับคีย์นั้นและมีสมาชิก
          ตรงกับรายการที่กำลังเขียนทุกตัว (= p2._tools) แล้วลบคีย์ด้วย .delete() ของมันเอง (SvelteSet อัปเดตสวิตช์ในหน้าตั้งค่าด้วย)
          และเขียนรายการที่ตัดแล้วลงแทน · หา Set ไม่เจอ = ไม่รู้ว่าในหน่วยความจำมีคีย์ค้างไหม → โหลดหน้านี้ใหม่
       2) ดัก Set.prototype.add เฉพาะค่าที่เป็นคีย์ของ local_confirm: จำ Set ที่เพิ่งรับคีย์ไว้ 8 ตัวล่าสุดให้ข้อ 1 ค้น
          ไม่ขวางการเพิ่มเอง — Set อื่นที่ใช้คีย์เดียวกันต้องทำงานตามเดิม (รายการเครื่องมือที่ปิดไว้ในหน้าตั้งค่า,
          ตัวกันซ้ำชั่วคราวใน getter allTools ของ WebUI ที่ถูกสร้างใหม่ทุกครั้งที่อ่าน)
       3) เปิดหน้า: ตัดคีย์ออกจาก localStorage (หน้า /?ui=1 ที่เปิดเดี่ยวๆ ไม่มี boot.js) ถ้าเจอ บันเดิลอาจอ่านเข้า
          หน่วยความจำไปก่อนสคริปต์นี้แล้ว (สองอย่างโหลดขนานกัน) → โหลดใหม่ครั้งเดียว
       4) storage event: หน้าอื่นของ origin เดียวกัน (แท็บอื่น, หน้า shell) เขียนคีย์ลงมา → ตัดออกทันที หน่วยความจำของหน้านี้
          ไม่ได้รับค่านั้นอยู่แล้ว แต่ถ้า iframe ถูกโหลดใหม่ทีหลัง (shell สั่งได้โดยไม่รัน boot.js ซ้ำ) จะอ่านเข้าไป
     การโหลดหน้าใหม่ทุกกรณีทำได้ครั้งเดียวต่อ 30 วินาที (sessionStorage) กันวนไม่รู้จบ */
  var ALLOW_GUARD = (function allowGuard() {
    var KEYS = ["LlamaUi.alwaysAllowedTools", "LlamaCppWebui.alwaysAllowedTools"];
    var RELOAD_KEY = "qwen-allow-guard-reload", RELOAD_GAP_MS = 30000;
    var stats = { stripped: 0, deleted: 0, reloads: 0, installed: false };
    var CONFIRM_KEY_RE = /^mcp(?:-[\s\S]+)?:local_confirm$/;
    // คีย์สิทธิ์ของ WebUI = "mcp-<id เซิร์ฟเวอร์>:<ชื่อเครื่องมือ>" ("mcp:<ชื่อ>" เมื่อไม่มี id) — นับทุกเซิร์ฟเวอร์ที่มี local_confirm
    // ไม่ใช่แค่ id local/local-full: ผู้ใช้เพิ่ม MCP ตัวเดียวกันซ้ำด้วย id อื่นได้ (เซิร์ฟเวอร์อื่นที่บังเอิญมีชื่อนี้ = ถามทุกครั้ง ไม่เสียหาย)
    // ถูกเรียกทุกครั้งที่ Set ใดๆ รับสตริง จึงเช็กท้ายสตริงก่อน (ถูก) แล้วค่อยใช้ regex
    function isConfirmKey(k) {
      return typeof k === "string" && k.length >= 17 && k.slice(-14) === ":local_confirm" && CONFIRM_KEY_RE.test(k);
    }
    // คืน {list, kept} เมื่อรายการมีคีย์ที่ต้องตัด · null = ไม่มี/อ่านไม่ออก (WebUI เองก็อ่านไม่ออก = ไม่ได้อนุญาตอะไร)
    function scrubList(raw) {
      if (typeof raw !== "string" || raw.indexOf("local_confirm") < 0) return null;
      var list;
      try { list = JSON.parse(raw); } catch (e) { return null; }
      if (!Array.isArray(list)) return null;
      var kept = list.filter(function (k) { return !isConfirmKey(k); });
      return kept.length === list.length ? null : { list: list, kept: kept };
    }
    var SP = window.Set && Set.prototype, StP = window.Storage && Storage.prototype;
    if (!SP || !StP || typeof StP.setItem !== "function") return { isConfirmKey: isConfirmKey, scrubList: scrubList, stats: stats };
    var nativeAdd = SP.add, nativeHas = SP.has, nativeSet = StP.setItem;
    var sizeDesc = Object.getOwnPropertyDescriptor(SP, "size"), nativeSize = sizeDesc && sizeDesc.get;
    var recent = [];                      // Set ที่เพิ่งรับคีย์ของ local_confirm (ใหม่สุดอยู่ท้าย)

    function reloadSoon() {
      var last = 0;
      try { last = +sessionStorage.getItem(RELOAD_KEY) || 0; } catch (e) { return; }     // กันวนไม่ได้ = ไม่โหลดใหม่
      if (Date.now() - last < RELOAD_GAP_MS) return;
      try { sessionStorage.setItem(RELOAD_KEY, String(Date.now())); } catch (e) { return; }
      stats.reloads++;
      setTimeout(function () { try { location.reload(); } catch (e) {} }, 0);
    }
    // Set ที่เก็บ "รายการนี้ทุกตัวพอดี" (persist() เขียน [...this._tools] จึงตรงกันเป๊ะ) — ใช้เมธอดดั้งเดิมของ Set
    // อ่านสถานะจริงโดยไม่ไปแตะการติดตามค่าของ Svelte
    function holderOf(list) {
      for (var i = recent.length - 1; i >= 0; i--) {
        var s = recent[i];
        try {
          if (nativeSize && nativeSize.call(s) !== list.length) continue;
          var all = true;
          for (var j = 0; j < list.length && all; j++) all = nativeHas.call(s, list[j]);
          if (all) return s;
        } catch (e) { /* ไม่ใช่ Set จริง */ }
      }
      return null;
    }
    function neutralize(fx) {
      var s = holderOf(fx.list), clean = false;
      if (s) {
        clean = true;
        for (var i = 0; i < fx.list.length; i++) {
          var k = fx.list[i];
          if (!isConfirmKey(k)) continue;
          try { s.delete(k); stats.deleted++; } catch (e) {}
          if (nativeHas.call(s, k)) clean = false;
        }
      }
      if (!clean) reloadSoon();
    }
    function add(v) {
      if (typeof v === "string" && isConfirmKey(v)) {
        var i = recent.indexOf(this);
        if (i >= 0) recent.splice(i, 1);
        recent.push(this);
        if (recent.length > 8) recent.shift();
      }
      return nativeAdd.call(this, v);
    }
    function setItem(k, v) {
      try {
        if (KEYS.indexOf(String(k)) >= 0) {
          var fx = scrubList(String(v));
          if (fx) {
            stats.stripped++;
            v = JSON.stringify(fx.kept);
            neutralize(fx);
          }
        }
      } catch (e) { /* ด่านพังต้องไม่ทำให้ WebUI เขียนค่าไม่ได้ */ }
      return nativeSet.call(this, k, v);
    }
    function stripStored() {
      var hit = false;
      KEYS.forEach(function (key) {
        var fx = null;
        try { fx = scrubList(localStorage.getItem(key)); } catch (e) { return; }
        if (!fx) return;
        hit = true;
        stats.stripped++;
        try { nativeSet.call(localStorage, key, JSON.stringify(fx.kept)); } catch (e) {}
      });
      return hit;
    }
    try {
      // คงคุณสมบัติเดิมของเมธอด (ไม่ enumerable) — แทนแค่ตัวฟังก์ชัน
      Object.defineProperty(SP, "add", { value: add, writable: true, configurable: true, enumerable: false });
      Object.defineProperty(StP, "setItem", { value: setItem, writable: true, configurable: true, enumerable: false });
      stats.installed = true;
    } catch (e) { /* แทนไม่ได้: ยังเหลือการซ่อนเมนูฝั่ง UI และ boot.js ตอนเปิดหน้า */ }
    if (stripStored()) reloadSoon();
    window.addEventListener("storage", function (e) {
      try {
        if (!e || KEYS.indexOf(e.key) < 0 || e.storageArea !== localStorage) return;
        var fx = scrubList(e.newValue);
        if (!fx) return;
        stats.stripped++;
        nativeSet.call(localStorage, e.key, JSON.stringify(fx.kept));
      } catch (x) {}
    });
    return { isConfirmKey: isConfirmKey, scrubList: scrubList, stats: stats };
  })();

  var root = document.documentElement;
  var KEY_THEME = "qwen-theme", KEY_MW = "mode-watcher-mode", KEY_FONT = "qwen-font";

  /* ---- ข้อความ (ตรงตาม DESIGN.md 5d ทุกตัวอักษร) --------------------------- */
  var STR = {
    th: {
      greet: ["อรุณสวัสดิ์", "สวัสดีตอนบ่าย", "สวัสดีตอนเย็น", "สวัสดียามค่ำ"],
      project: "โปรเจกต์",
      phStart: "วันนี้ให้ช่วยอะไรดี?",
      phChat: "ตอบกลับ Qwen…",
      chipsLabel: "คำแนะนำ",
      sysMsg: "คำสั่งของโปรเจกต์",
      // คำอธิบาย (sr-only) ของชีต "+" บนจอแคบ — ต้องเรียกรายการเดียวกับป้ายข้างล่าง (sysMsg) ไม่ใช่ "system prompt"
      sheetDesc: "เพิ่มไฟล์ คำสั่งของโปรเจกต์ หรือตั้งค่าเซิร์ฟเวอร์ MCP",
      // batch 2a (B5): รายการ "ค้นคว้าเชิงลึก" ในเมนู "+" — เติมคำขอลงช่องพิมพ์ (ไม่ส่งเอง) ข้อความเดียวกับ res_prefill ของ shell
      research: "ค้นคว้าเชิงลึก",
      researchPrefill: "ค้นคว้าเชิงลึกแล้วเขียนรายงานพร้อมอ้างอิงเรื่อง: ",
      chips: [
        ["write", "เขียน", "ช่วยเขียน "],
        ["learn", "เรียนรู้", "อธิบายให้เข้าใจง่ายๆ ว่า "],
        ["code", "โค้ด", "เขียนโค้ด Python ที่ "],
        ["files", "ไฟล์โปรเจกต์", "อ่านไฟล์ของโปรเจกต์นี้แล้วสรุปประเด็นสำคัญ"],
        ["web", "ค้นเว็บ", "ค้นเว็บเรื่อง "],
        // batch 2b (C4): ทางลัด Office — ช่องที่ 4 = คำอธิบาย (title) บอกว่าทำอะไรได้ และการเขียนกลับต้องอนุญาตทุกครั้ง
        ["office", "Office", "อ่านข้อมูลที่เลือกไว้ใน Excel ที่เปิดอยู่ แล้ว",
          "ใช้กับ Excel, Word และ PowerPoint ที่เปิดอยู่ในเครื่องนี้ — อ่านได้ทันที ส่วนการเขียนกลับต้องกดอนุญาตทุกครั้ง"]
      ]
    },
    en: {
      greet: ["Good morning", "Good afternoon", "Good evening", "Good evening"],
      project: "Project",
      phStart: "How can I help you today?",
      phChat: "Reply to Qwen…",
      chipsLabel: "Suggestions",
      sysMsg: "Project instructions",
      sheetDesc: "Add files, project instructions or configure MCP servers",
      research: "Deep research",
      researchPrefill: "Do deep research and write a cited report on: ",
      chips: [
        ["write", "Write", "Help me write "],
        ["learn", "Learn", "Explain simply: "],
        ["code", "Code", "Write Python code that "],
        ["files", "Project files", "Read this project's files and summarize the key points"],
        ["web", "Search web", "Search the web for "],
        ["office", "Office", "Read what's selected in my open Excel workbook, then ",
          "Works with the Excel, Word and PowerPoint files open on this computer — reading is instant; writing back always asks for your approval"]
      ]
    }
  };

  /* ---- พจนานุกรม UI ของ WebUI: อังกฤษ → ไทย -----------------------------------------
     สร้างจากซอร์สจริงของ WebUI (bundle ของ llama.cpp ที่เสิร์ฟอยู่: ข้อความในเทมเพลต se("…"),
     label/help ของหน้าตั้งค่า, title/aria-label/placeholder, ข้อความ toast) แล้วตรวจกับหน้าจอจริง
     ไม่ได้เดาเอา — คีย์คือข้อความหลังยุบช่องว่างและแทน "…" ด้วย "..." (WebUI ใช้ปนกันทั้งสองแบบ)
     คำศัพท์ให้ตรงกับ STRINGS ของ hub (แชต, โปรเจกต์, โมเดล, พรอมต์, โทเค็น, เซิร์ฟเวอร์ MCP)
     ชื่อเฉพาะทางเทคนิคที่ผู้ใช้ไทยคุ้นเป็นอังกฤษคงไว้ (Temperature, Top K/P, Min P, Max tokens,
     DRY, XTC, JSON, API key, KV cache, Markdown) แต่แปลคำอธิบายของมันทั้งหมด
     ข้อความที่ไม่ใช่ UI ของ WebUI (ข้อความแชต, ชื่อแชต, ชื่อโมเดล/ไฟล์/เครื่องมือ) ไม่อยู่ที่นี่
     และตัวแปลไม่แตะพื้นที่เหล่านั้นอยู่แล้ว (ดู TX_SKIP) */
  var TH = {
    // ---- ทั่วไป / ปุ่ม ----
    "Settings": "การตั้งค่า", "Close": "ปิด", "Cancel": "ยกเลิก", "Save": "บันทึก", "Delete": "ลบ",
    "Edit": "แก้ไข", "Copy": "คัดลอก", "Add": "เพิ่ม", "Remove": "นำออก", "Update": "อัปเดต",
    // "Dismiss" มีที่เดียวคือลิงก์ซ่อนรายการเซิร์ฟเวอร์ที่แนะนำ ซึ่งอยู่ข้างปุ่ม ✕ (ปิด) ของหน้าต่าง — ใช้คนละคำ
    "Confirm": "ยืนยัน", "Continue": "ทำต่อ", "Dismiss": "ซ่อน", "Refresh": "รีเฟรช", "Reload": "โหลดใหม่",
    "Retry": "ลองใหม่", "Try again": "ลองอีกครั้ง", "Got it": "เข้าใจแล้ว", "Select": "เลือก",
    "Search": "ค้นหา", "Search...": "ค้นหา…", "Searching...": "กำลังค้นหา…", "Searching": "กำลังค้นหา",
    "Searched": "ค้นหาแล้ว", "Browse": "เรียกดู", "Previous": "ก่อนหน้า", "Next": "ถัดไป",
    "Preview": "ดูตัวอย่าง", "Close preview": "ปิดตัวอย่าง", "Preview only": "ดูตัวอย่างเท่านั้น",
    "Key": "คีย์", "Value": "ค่า", "Title": "ชื่อ", "(optional)": "(ไม่บังคับ)", "details": "รายละเอียด",
    "Unknown": "ไม่ทราบ", "Error": "ข้อผิดพลาด", "Error:": "ข้อผิดพลาด:", "Cancelled": "ยกเลิกแล้ว",
    "Success!": "สำเร็จ!", "Not available": "ไม่มีข้อมูล", "No results": "ไม่พบผลลัพธ์",
    "No results found": "ไม่พบผลลัพธ์", "No items found": "ไม่พบรายการ", "Something went wrong": "เกิดข้อผิดพลาด",
    "Go Home": "กลับหน้าแรก", "Custom": "กำหนดเอง", "Enabled": "เปิดใช้", "Files": "ไฟล์",
    "Server": "เซิร์ฟเวอร์", "Browser": "เบราว์เซอร์", "Tools": "เครื่องมือ", "Tool": "เครื่องมือ",
    "Notifications alt+T": "การแจ้งเตือน alt+T",
    // ---- ระดับการคิด: ทั้งในเมนูย่อย (ตัวใหญ่) และค่าบนปุ่มที่ WebUI เขียนตัวเล็กแล้วใช้ CSS capitalize ----
    "Reasoning": "การคิด", "Default": "ค่าเริ่มต้น", "default": "ค่าเริ่มต้น", "Model default": "ตามโมเดล",
    "Off": "ปิด", "off": "ปิด", "Low": "ต่ำ", "low": "ต่ำ", "Medium": "กลาง", "medium": "กลาง",
    "High": "สูง", "high": "สูง", "Max": "สูงสุด", "max": "สูงสุด", "Unlimited": "ไม่จำกัด",
    "Maximum reasoning effort with extended context usage": "คิดละเอียดที่สุด ใช้บริบทมากขึ้น",
    // ---- แถบข้าง / แท็บ / รายการแชตของ WebUI ----
    "New chat": "แชตใหม่", "Go to start": "ไปหน้าเริ่มต้น", "Expand navigation": "กางแถบนำทาง",
    "Collapse navigation": "พับแถบนำทาง", "Open Sidebar": "เปิดแถบข้าง", "Close Sidebar": "ปิดแถบข้าง",
    "Recent conversations": "แชตล่าสุด", "Pinned": "ปักหมุดไว้", "Search results": "ผลการค้นหา",
    "No conversations yet": "ยังไม่มีแชต", "Start typing to see results": "เริ่มพิมพ์เพื่อดูผลลัพธ์",
    "Search conversations...": "ค้นหาแชต…", "See parent conversation": "ดูแชตต้นทาง",
    "Pin": "ปักหมุด", "Unpin": "เลิกปักหมุด", "Pin all": "ปักหมุดทั้งหมด", "Unpin all": "เลิกปักหมุดทั้งหมด",
    "More actions": "ตัวเลือกเพิ่มเติม", "Select all": "เลือกทั้งหมด", "Deselect all": "ไม่เลือกทั้งหมด",
    "Export selected": "ส่งออกที่เลือก", "Delete selected": "ลบที่เลือก",
    "Exit bulk selection mode": "ออกจากโหมดเลือกหลายรายการ",
    "Bulk actions for selected conversations": "จัดการแชตที่เลือกพร้อมกัน",
    "Unavailable for mixed state selection": "ใช้ไม่ได้เมื่อแชตที่เลือกมีสถานะต่างกัน",
    "Rename conversation": "เปลี่ยนชื่อแชต", "Choose a new title for this conversation.": "ตั้งชื่อใหม่ให้แชตนี้",
    "Delete Conversation": "ลบแชต",
    "Are you sure you want to delete this conversation? This action cannot be undone and will permanently remove all messages in this conversation.":
      "ลบแชตนี้? ข้อความทั้งหมดในแชตนี้จะถูกลบถาวร กู้คืนไม่ได้",
    "Open conversations": "แชตที่เปิดอยู่", "Close tab": "ปิดแท็บ", "Scroll left": "เลื่อนซ้าย",
    "Scroll right": "เลื่อนขวา", "Conversation Name": "ชื่อแชต", "Messages": "ข้อความ",
    "No conversations available": "ไม่มีแชต", "Conversations": "แชต",
    // ---- หน้าเริ่มแชต / กล่องพิมพ์ ----
    "Hello there": "สวัสดี",
    "Type a message or upload files to get started": "พิมพ์ข้อความหรืออัปโหลดไฟล์เพื่อเริ่มต้น",
    "Record audio, type a message or upload files to get started": "อัดเสียง พิมพ์ข้อความ หรืออัปโหลดไฟล์เพื่อเริ่มต้น",
    "Type a message...": "พิมพ์ข้อความ…", "Ask anything...": "ถามอะไรก็ได้…",
    "Send": "ส่ง", "Stop": "หยุด", "Skip reasoning": "ข้ามการคิด", "Stop generation": "หยุดสร้างคำตอบ",
    "Stop recording": "หยุดอัดเสียง", "Start recording": "เริ่มอัดเสียง",
    "Current model does not support audio": "โมเดลปัจจุบันไม่รองรับเสียง",
    "Audio recording not supported": "อัดเสียงในเบราว์เซอร์นี้ไม่ได้",
    "Attach a file": "แนบไฟล์", "Drop your files here to upload": "วางไฟล์ที่นี่เพื่ออัปโหลด",
    "Scroll to bottom": "เลื่อนลงล่างสุด", "Context usage": "การใช้บริบท",
    "Please select a model first": "เลือกโมเดลก่อน",
    "Selected model is not available, please select another": "โมเดลที่เลือกใช้ไม่ได้ เลือกโมเดลอื่น",
    "Selected model is not available": "โมเดลที่เลือกใช้ไม่ได้",
    "Open command picker": "เปิดรายการคำสั่ง", "No matching command": "ไม่พบคำสั่งที่ตรงกัน",
    "Open prompt picker": "เปิดรายการพรอมต์", "Open picker": "เปิดรายการ", "Search prompts...": "ค้นหาพรอมต์…",
    "No MCP prompts available": "ไม่มีพรอมต์ MCP", "Use Prompt": "ใช้พรอมต์",
    "Unknown error executing prompt": "เกิดข้อผิดพลาดขณะใช้พรอมต์",
    "Open file mention picker": "เปิดรายการไฟล์ (@)", "No matching files or folders": "ไม่พบไฟล์หรือโฟลเดอร์ที่ตรงกัน",
    "File search is unavailable on this server (started without --tools)": "เซิร์ฟเวอร์นี้ค้นหาไฟล์ไม่ได้ (เปิดโดยไม่มี --tools)",
    "File search is unavailable on this server - type a full path and press Enter": "เซิร์ฟเวอร์นี้ค้นหาไฟล์ไม่ได้ พิมพ์ path เต็มแล้วกด Enter",
    "Insert an MCP prompt": "แทรกพรอมต์ MCP", "Set working directory": "ตั้งโฟลเดอร์ทำงาน",
    "Set working directory to": "ตั้งโฟลเดอร์ทำงานเป็น", "Working directory cleared": "ล้างโฟลเดอร์ทำงานแล้ว",
    "Reset working directory": "รีเซ็ตโฟลเดอร์ทำงาน", "Choose working directory": "เลือกโฟลเดอร์ทำงาน",
    "Open working directory picker": "เปิดตัวเลือกโฟลเดอร์ทำงาน", "Searching in:": "ค้นใน:",
    "No matching folders": "ไม่พบโฟลเดอร์ที่ตรงกัน", "Clear search": "ล้างคำค้น", "Select model": "เลือกโมเดล",
    // ---- เมนู "+" / แนบไฟล์ ----
    "Add files": "เพิ่มไฟล์", "Add to chat": "เพิ่มลงในแชต", "MCP Servers": "เซิร์ฟเวอร์ MCP",
    "Add files, prompts, tools or MCP Servers": "เพิ่มไฟล์ พรอมต์ เครื่องมือ หรือเซิร์ฟเวอร์ MCP",
    // ใน shell ตัวแปลใช้ STR.sheetDesc แทน (รายการในชีตถูกเปลี่ยนเป็นคำสั่งของโปรเจกต์) — ค่านี้ใช้ตอนเปิดเดี่ยว
    "Add files, system prompt or configure MCP servers": "เพิ่มไฟล์ ข้อความระบบ หรือตั้งค่าเซิร์ฟเวอร์ MCP",
    "Inject custom system message at the beginning of the conversation": "แทรกข้อความระบบไว้ต้นแชต",
    "Add custom system message for a new conversation": "เพิ่มข้อความระบบให้แชตใหม่",
    "Images": "รูปภาพ", "Audio Files": "ไฟล์เสียง", "Video Files": "ไฟล์วิดีโอ", "Text Files": "ไฟล์ข้อความ",
    "PDF Files": "ไฟล์ PDF", "PDFs": "PDF", "Audio": "เสียง", "Video": "วิดีโอ", "Vision": "ภาพ",
    "Image processing requires a vision model": "การประมวลผลรูปภาพต้องใช้โมเดลที่รองรับภาพ",
    "Audio files processing requires an audio model": "การประมวลผลไฟล์เสียงต้องใช้โมเดลที่รองรับเสียง",
    "Video files processing requires a video model": "การประมวลผลไฟล์วิดีโอต้องใช้โมเดลที่รองรับวิดีโอ",
    "PDFs will be converted to text. Image-based PDFs may not work properly.": "PDF จะถูกแปลงเป็นข้อความ PDF ที่เป็นภาพสแกนอาจอ่านได้ไม่ครบ",
    "Images require a vision-capable model": "รูปภาพต้องใช้โมเดลที่รองรับภาพ",
    "Audio files require an audio-capable model": "ไฟล์เสียงต้องใช้โมเดลที่รองรับเสียง",
    "Video files require a video-capable model": "ไฟล์วิดีโอต้องใช้โมเดลที่รองรับวิดีโอ",
    "Loading tools...": "กำลังโหลดเครื่องมือ…", "Failed to load tools": "โหลดเครื่องมือไม่สำเร็จ",
    "No tools available": "ไม่มีเครื่องมือ", "MCP Tools": "เครื่องมือ MCP",
    "Run llama-server with": "รัน llama-server ด้วยแฟล็ก", "flag to enable": "เพื่อเปิดใช้",
    "Sent as Image": "ส่งเป็นรูปภาพ", "Sent as Text": "ส่งเป็นข้อความ", "Unknown File": "ไฟล์ไม่ทราบชนิด",
    "Pages": "หน้า", "Preview not available for this file type": "ไฟล์ประเภทนี้ดูตัวอย่างไม่ได้",
    "Audio preview not available": "ดูตัวอย่างเสียงไม่ได้", "Video preview not available": "ดูตัวอย่างวิดีโอไม่ได้",
    "The selected model does not support vision. Only the extracted": "โมเดลที่เลือกไม่รองรับภาพ จะส่งเฉพาะ",
    "text": "ข้อความ", "will be sent to the model.": "ที่ดึงออกมาให้โมเดล",
    "Converting PDF to images...": "กำลังแปลง PDF เป็นรูปภาพ…", "Failed to load PDF images": "โหลดรูปจาก PDF ไม่สำเร็จ",
    "No PDF pages available": "ไม่มีหน้า PDF",
    // ---- ข้อความแชต: ปุ่ม, สถิติ, การคิด, เครื่องมือ ----
    "Regenerate": "สร้างคำตอบใหม่", "Fork conversation": "แยกเป็นแชตใหม่", "Fork": "แยกแชต",
    "Fork Conversation": "แยกเป็นแชตใหม่", "Create a new conversation branching from this message.": "สร้างแชตใหม่ที่แตกแขนงจากข้อความนี้",
    "Enter fork name": "ตั้งชื่อแชตใหม่", "Include all attachments": "รวมไฟล์แนบทั้งหมด",
    "Previous version": "เวอร์ชันก่อนหน้า", "Next version": "เวอร์ชันถัดไป",
    "Copy code": "คัดลอกโค้ด", "Code incomplete": "โค้ดยังไม่ครบ", "Preview code": "ดูตัวอย่างโค้ด",
    "Copy to clipboard": "คัดลอกไปคลิปบอร์ด", "Message copied to clipboard": "คัดลอกข้อความแล้ว",
    // ค่าเริ่มต้นของตัวช่วยคัดลอกของ WebUI (ปุ่มคัดลอกบล็อกโค้ด ชื่อ/path โมเดล ซอร์ส mermaid/SVG) — toast ไม่ได้ส่งข้อความเอง
    "Code copied to clipboard": "คัดลอกโค้ดแล้ว", "Failed to copy code": "คัดลอกโค้ดไม่สำเร็จ",
    "Copied to clipboard": "คัดลอกแล้ว", "Failed to copy to clipboard": "คัดลอกไม่สำเร็จ",
    "Toggle content": "แสดง/ซ่อนเนื้อหา", "Toggle source": "สลับดูซอร์ส", "Copy mermaid syntax": "คัดลอกโค้ด mermaid",
    "Toggle mermaid source": "สลับดูซอร์ส mermaid", "Preview diagram": "ดูตัวอย่างแผนภาพ",
    "Copy svg source": "คัดลอกซอร์ส SVG", "Toggle svg source": "สลับดูซอร์ส SVG", "Preview svg": "ดูตัวอย่าง SVG",
    "Zoom in": "ขยาย", "Zoom out": "ย่อ", "Reset view": "รีเซ็ตมุมมอง", "Download SVG": "ดาวน์โหลด SVG",
    "Generating diagram...": "กำลังสร้างแผนภาพ…", "Rendering svg...": "กำลังเรนเดอร์ SVG…",
    "Diagram incomplete": "แผนภาพยังไม่ครบ",
    "User message with actions": "ข้อความของคุณ", "Assistant message with actions": "คำตอบของโมเดล",
    "System message with actions": "ข้อความระบบ", "MCP Prompt message with actions": "ข้อความพรอมต์ MCP",
    "Pending user message": "ข้อความที่รอส่ง", "Send immediately": "ส่งทันที",
    "Update without re-sending": "อัปเดตโดยไม่ส่งใหม่", "Branch conversation after edit": "แตกแขนงแชตหลังแก้ไข",
    "Edit your message...": "แก้ไขข้อความ…", "Edit system message...": "แก้ไขข้อความระบบ…",
    "Keep editing": "แก้ไขต่อ", "Discard": "ทิ้ง", "Discard changes?": "ทิ้งการแก้ไข?",
    "You have unsaved changes. Are you sure you want to discard them?": "มีการแก้ไขที่ยังไม่ได้บันทึก ทิ้งการแก้ไขนี้?",
    "Show full system message": "แสดงข้อความระบบทั้งหมด", "Collapse System Message": "ย่อข้อความระบบ",
    "Show raw output": "แสดงผลดิบ",
    "Delete Message": "ลบข้อความนี้?",
    "Are you sure you want to delete this message? This action cannot be undone.": "ข้อความนี้จะถูกลบถาวร กู้คืนไม่⁠ได้",
    "Reasoning...": "กำลังคิด…", "failed": "ล้มเหลว", "incomplete": "ไม่ครบ",
    "Processing...": "กำลังประมวลผล…", "Initializing...": "กำลังเริ่มต้น…", "Preparing response...": "กำลังเตรียมคำตอบ…",
    "Reconnecting to the stream...": "กำลังเชื่อมต่อสตรีมใหม่…", "Loading model": "กำลังโหลดโมเดล",
    "Server unavailable": "เซิร์ฟเวอร์ใช้งานไม่ได้", "Speculative decoding enabled": "เปิด speculative decoding อยู่",
    "Agentic turn limit reached. Continue?": "ถึงจำนวนรอบเอเจนต์สูงสุดแล้ว ทำต่อไหม?",
    "Allow use of": "อนุญาตให้ใช้", "from": "จาก", "Allow once": "อนุญาตครั้งนี้", "More allow options": "ตัวเลือกการอนุญาตเพิ่มเติม",
    "Deny": "ปฏิเสธ", "Always allow": "อนุญาตเสมอ", "tool": "",
    "Receiving arguments...": "กำลังรับอาร์กิวเมนต์…", "Response was truncated": "ผลลัพธ์ถูกตัดท้าย",
    "Input": "อินพุต", "Output": "เอาต์พุต", "No output": "ไม่มีเอาต์พุต", "Waiting for result...": "กำลังรอผลลัพธ์…",
    "(failed)": "(ล้มเหลว)", "No edits": "ไม่มีการแก้ไข", "Running...": "กำลังรัน…", "timed out": "หมดเวลา",
    "in": "ใน", "Total matches:": "พบทั้งหมด:", "No matches": "ไม่พบที่ตรงกัน", "Current time is": "เวลาปัจจุบันคือ",
    "Search for": "ค้นหา", "(with line numbers)": "(พร้อมเลขบรรทัด)", "bytes": "ไบต์",
    "Waiting for file content...": "กำลังรอเนื้อหาไฟล์…", "Waiting for media data...": "กำลังรอข้อมูลสื่อ…",
    "Media attachment not found in message extras": "ไม่พบไฟล์สื่อที่แนบในข้อความ",
    // ชื่อเครื่องมือในตัวของ WebUI (ป้ายของมันเอง ไม่ใช่ชื่อเครื่องมือ MCP)
    "Current time": "เวลาปัจจุบัน", "Read media": "อ่านไฟล์สื่อ", "Run JavaScript": "รัน JavaScript",
    "Edit file": "แก้ไขไฟล์", "Run command": "รันคำสั่ง", "Search files": "ค้นหาไฟล์", "Runtime info": "ข้อมูลระบบ",
    "Search in files": "ค้นข้อความในไฟล์", "Read file": "อ่านไฟล์", "Write file": "เขียนไฟล์",
    // แถบสถิติใต้ข้อความ (ปุ่มสลับมุมมอง + tooltip)
    "Reading": "อ่านพรอมต์", "Processing": "ประมวลผลพรอมต์", "Generation": "สร้างคำตอบ",
    "Waiting for tokens...": "กำลังรอโทเค็น…", "Tool calls": "การเรียกเครื่องมือ", "Summary": "สรุป",
    "Agentic summary": "สรุปการทำงานแบบเอเจนต์",
    "Generated tokens": "โทเค็นที่สร้าง", "Generation time": "เวลาที่ใช้สร้างคำตอบ",
    "Generation speed": "ความเร็วในการสร้าง", "Prompt tokens": "โทเค็นของพรอมต์",
    "Prompt processing time": "เวลาประมวลผลพรอมต์", "Prompt processing speed": "ความเร็วประมวลผลพรอมต์",
    "Tool calls executed": "จำนวนครั้งที่เรียกเครื่องมือ", "Tool execution time": "เวลาที่เครื่องมือทำงาน",
    "Tool execution rate": "อัตราการเรียกเครื่องมือ", "Agentic turns (LLM calls)": "จำนวนรอบที่เรียกโมเดล",
    "Total tokens generated": "โทเค็นที่สร้างทั้งหมด", "Total time (LLM + tools)": "เวลารวม (โมเดล + เครื่องมือ)",
    // วงแหวน/ป๊อปอัปการใช้บริบท
    "Token usage details": "รายละเอียดการใช้โทเค็น", "Across all turns": "รวมทุกรอบ",
    "This turn · KV cache": "รอบนี้ · KV cache", "KV cache total": "KV cache ทั้งหมด",
    "Prompt tokens evaluated": "โทเค็นพรอมต์ที่ประมวลผล", "Tokens generated": "โทเค็นที่สร้าง",
    // "Generated" เป็นป้ายแถวคู่กับ "Prompt" ใต้หัว "รอบนี้" (โทเค็นขาออกของรอบนี้) — "ที่สร้าง" ห้วนเป็นครึ่งประโยค
    "Prompt": "พรอมต์", "Generated": "คำตอบ", "Avg speed": "ความเร็วเฉลี่ย", "used": "ใช้แล้ว",
    "Available context size is only visible once the model is loaded.": "ขนาดบริบทที่ใช้ได้จะแสดงเมื่อโหลดโมเดลแล้ว",
    "Loading model...": "กำลังโหลดโมเดล…", "Load model": "โหลดโมเดล", "No context info available": "ไม่มีข้อมูลบริบท",
    "Context": "บริบท", "Context size:": "ขนาดบริบท:", "Prompt tokens:": "โทเค็นพรอมต์:",
    // ---- ตัวเลือกโมเดล / ข้อมูลโมเดล ----
    "Loaded models": "โมเดลที่โหลดอยู่", "Available models": "โมเดลอื่น", "Favorite models": "โมเดลโปรด",
    "Loading models...": "กำลังโหลดโมเดล…", "Search models...": "ค้นหาโมเดล…", "No models available.": "ไม่มีโมเดล",
    "No models found.": "ไม่พบโมเดล", "No model": "ไม่มีโมเดล", "(not available)": "(ใช้ไม่ได้)",
    "Add to favorites": "เพิ่มในรายการโปรด", "Remove from favorites": "นำออกจากรายการโปรด",
    "Model information": "ข้อมูลโมเดล", "Model Information": "ข้อมูลโมเดล", "Unload model": "เลิกโหลดโมเดล",
    "Retry loading model": "ลองโหลดโมเดลอีกครั้ง", "Select Model": "เลือกโมเดล",
    "Choose a model to use for the conversation": "เลือกโมเดลที่จะใช้ในแชตนี้", "Copy model name": "คัดลอกชื่อโมเดล",
    "Click for model details": "คลิกเพื่อดูรายละเอียดโมเดล", "Current model details and capabilities": "รายละเอียดและความสามารถของโมเดลปัจจุบัน",
    "Loading model information...": "กำลังโหลดข้อมูลโมเดล…", "No model information available": "ไม่มีข้อมูลโมเดล",
    "Copy model name to clipboard": "คัดลอกชื่อโมเดล", "Copy model path to clipboard": "คัดลอก path ของโมเดล",
    "Model": "โมเดล", "File Path": "ที่อยู่ไฟล์", "Build Info": "ข้อมูลบิลด์", "Chat Template": "เทมเพลตแชต",
    "Modalities": "ข้อมูลที่รองรับ", "Context Size": "ขนาดบริบท", "Training Context": "บริบทตอนเทรน",
    "Model Size": "ขนาดโมเดล", "Parameters": "จำนวนพารามิเตอร์", "Embedding Size": "ขนาด embedding",
    "Vocabulary Size": "ขนาดคลังคำ", "Vocabulary Type": "ชนิดคลังคำ", "Parallel Slots": "จำนวน slot ขนาน",
    "Model Not Available": "ไม่มีโมเดลนี้", "Select an available model:": "เลือกโมเดลที่มีอยู่:", "Requested:": "ที่ขอ:",
    "The requested model could not be found. Select an available model to continue.": "ไม่พบโมเดลที่ขอ เลือกโมเดลที่มีอยู่เพื่อทำต่อ",
    "Loading projector": "กำลังโหลด projector", "Loading draft": "กำลังโหลดโมเดลร่าง", "Loading weights": "กำลังโหลดน้ำหนักโมเดล",
    "Unknown Model": "ไม่ทราบโมเดล",
    // ---- หน้าต่างตั้งค่า: หมวด + ส่วนท้าย ----
    "General": "ทั่วไป", "Display": "การแสดงผล", "Agentic": "เอเจนต์", "Import/Export": "นำเข้า/ส่งออก",
    "Sampling & Penalties": "การสุ่มและค่าปรับ", "Developer": "นักพัฒนา",
    "Reload app": "โหลดแอปใหม่", "Settings are saved in browser's localStorage": "การตั้งค่าเก็บไว้ใน localStorage ของเบราว์เซอร์",
    "Reset to default": "คืนค่าเริ่มต้น", "Reset to Default": "คืนค่าเริ่มต้น", "Save settings": "บันทึกการตั้งค่า",
    "Reset Settings to Default": "คืนการตั้งค่าเป็นค่าเริ่มต้น",
    "Are you sure you want to reset all settings to their default values? This will reset all parameters to the values provided by the server's /props endpoint and remove all your custom configurations.":
      "คืนการตั้งค่าทั้งหมดเป็นค่าเริ่มต้น? พารามิเตอร์ทุกตัวจะกลับเป็นค่าจาก /props ของเซิร์ฟเวอร์ และค่าที่คุณตั้งเองจะหายทั้งหมด",
    "Invalid JSON in custom parameters. Please check the format and try again.": "JSON ในพารามิเตอร์เพิ่มเติมไม่ถูกต้อง ตรวจรูปแบบแล้วลองใหม่",
    // ทั่วไป
    "Theme": "ธีม", "System": "ระบบ", "Light": "สว่าง", "Dark": "มืด",
    "Choose the color theme for the interface. You can choose between System (follows your device settings), Light, or Dark.":
      "เลือกธีมสีของหน้าจอ: ระบบ (ตามการตั้งค่าของอุปกรณ์) สว่าง หรือมืด",
    "Set the API Key if you are using": "ใส่ API key หากเปิดเซิร์ฟเวอร์ด้วยตัวเลือก", "option for the server.": "",
    "System Message": "ข้อความระบบ", "System message": "ข้อความระบบ",
    "The starting message that defines how model should behave.": "ข้อความตั้งต้นที่กำหนดว่าโมเดลควรตอบอย่างไร",
    "Show system message": "แสดงข้อความระบบ", "Show system message in conversations": "แสดงข้อความระบบในแชต",
    "Display the system message at the top of each conversation.": "แสดงข้อความระบบไว้บนสุดของทุกแชต",
    "Paste long text to file length": "ความยาวข้อความที่วางแล้วแปลงเป็นไฟล์",
    "On pasting long text, it will be converted to a file. You can control the file length by setting the value of this parameter. Value 0 means disable.":
      "เมื่อวางข้อความยาวเกินค่านี้ (ตัวอักษร) ระบบจะแปลงเป็นไฟล์แนบให้ ใส่ 0 เพื่อปิด",
    "Send message on Enter": "กด Enter เพื่อส่งข้อความ",
    "Use Enter to send messages and Shift + Enter for new lines. When disabled, use Ctrl/Cmd + Enter.":
      "กด Enter เพื่อส่ง และ Shift + Enter เพื่อขึ้นบรรทัดใหม่ ถ้าปิด ให้กด Ctrl/Cmd + Enter เพื่อส่ง",
    "Show microphone on empty input": "แสดงไมโครโฟนเมื่อช่องพิมพ์ว่าง",
    "Automatically show microphone button instead of send button when textarea is empty for models with audio modality support.":
      "แสดงปุ่มไมโครโฟนแทนปุ่มส่งเมื่อช่องพิมพ์ว่าง (เฉพาะโมเดลที่รองรับเสียง)",
    "Enable \"Continue\" button": "เปิดปุ่ม \"ทำต่อ\"",
    "Enable \"Continue\" button for assistant messages, including reasoning models.": "เปิดปุ่ม \"ทำต่อ\" ใต้คำตอบของโมเดล รวมถึงโมเดลที่คิดก่อนตอบ",
    "Conversation title": "ชื่อแชต", "Use first non-empty line for the conversation title": "ใช้บรรทัดแรกที่ไม่ว่างเป็นชื่อแชต",
    "Generate title with LLM": "ให้ LLM ตั้งชื่อแชต",
    "Choose how conversation titles are generated. The first non-empty line uses a fast deterministic rule; the LLM option uses a model-generated title from the first message exchange.":
      "เลือกวิธีตั้งชื่อแชต: บรรทัดแรกที่ไม่ว่างเร็วและได้ผลแน่นอน ส่วน LLM จะให้โมเดลตั้งชื่อจากข้อความคู่แรก",
    "LLM title generation prompt": "พรอมต์ที่ให้ LLM ตั้งชื่อแชต",
    "Optional template for the title generation prompt. Use {{USER}} for the user message and {{ASSISTANT}} for the assistant message.":
      "เทมเพลตพรอมต์สำหรับตั้งชื่อ (ไม่ใส่ก็ได้) ใช้ {{USER}} แทนข้อความของผู้ใช้ และ {{ASSISTANT}} แทนคำตอบของโมเดล",
    "Copy text attachments as plain text": "คัดลอกไฟล์ข้อความที่แนบเป็นข้อความล้วน",
    "When copying a message with text attachments, combine them into a single plain text string instead of a special format that can be pasted back as attachments.":
      "เมื่อคัดลอกข้อความที่มีไฟล์ข้อความแนบ ให้รวมเป็นข้อความล้วนก้อนเดียว แทนรูปแบบพิเศษที่วางกลับเป็นไฟล์แนบได้",
    "Parse PDF as image": "อ่าน PDF เป็นรูปภาพ",
    "Parse PDF as image instead of text. Automatically falls back to text processing for non-vision models.":
      "อ่าน PDF เป็นรูปภาพแทนข้อความ ถ้าโมเดลไม่รองรับภาพจะกลับไปอ่านเป็นข้อความเอง",
    "Maximum image resolution (megapixels)": "ความละเอียดรูปสูงสุด (ล้านพิกเซล)",
    "Images larger than this will be resized before sending to server. Set to 0 to disable.": "รูปที่ใหญ่กว่านี้จะถูกย่อก่อนส่งไปเซิร์ฟเวอร์ ใส่ 0 เพื่อปิด",
    // การแสดงผล
    "Show message generation statistics": "แสดงสถิติการสร้างคำตอบ",
    "Display generation statistics (tokens/second, token count, duration) below each assistant message.":
      "แสดงสถิติการสร้าง (โทเค็น/วินาที จำนวนโทเค็น เวลา) ใต้คำตอบแต่ละข้อความ",
    "Show statistics for individual agentic turns": "แสดงสถิติของแต่ละรอบเอเจนต์",
    "Display per-turn statistics (tokens, duration) under each turn in agentic responses. Shown only when \"Show message generation statistics\" is enabled.":
      "แสดงสถิติ (โทเค็น เวลา) ใต้แต่ละรอบของคำตอบแบบเอเจนต์ แสดงเฉพาะเมื่อเปิด \"แสดงสถิติการสร้างคำตอบ\"",
    "Show thought in progress": "แสดงการคิดระหว่างตอบ",
    "Expand thought process by default when generating messages.": "กางส่วนการคิดไว้ตั้งแต่แรกขณะโมเดลกำลังตอบ",
    "Always show tool call content": "แสดงรายละเอียดการเรียกเครื่องมือเสมอ",
    "Automatically expand tool call details while executing and keep them expanded after completion.":
      "กางรายละเอียดการเรียกเครื่องมือขณะทำงาน และกางค้างไว้หลังทำเสร็จ",
    "Render user content as Markdown": "แสดงข้อความผู้ใช้เป็น Markdown",
    "Render user messages using markdown formatting in the chat. Turn this off to keep a message exactly as typed; @-mention badges show either way.":
      "จัดรูปแบบข้อความของผู้ใช้ด้วย Markdown ปิดไว้ถ้าต้องการเห็นตรงตามที่พิมพ์ ป้าย @-mention แสดงเสมอ",
    "Render thinking as Markdown": "แสดงการคิดเป็น Markdown",
    "Render the reasoning/thinking block content as formatted Markdown instead of plain text.": "แสดงเนื้อหาส่วนการคิดเป็น Markdown แทนข้อความล้วน",
    "Use full height code blocks": "แสดงบล็อกโค้ดเต็มความสูง",
    "Always display code blocks at their full natural height, overriding any height limits.": "แสดงบล็อกโค้ดเต็มความสูงเสมอ ไม่จำกัดความสูง",
    "Disable automatic scroll": "ปิดการเลื่อนอัตโนมัติ",
    "Disable automatic scrolling while messages stream so you can control the viewport position manually.":
      "ไม่เลื่อนหน้าจอตามอัตโนมัติขณะโมเดลกำลังตอบ ให้เลื่อนเองได้",
    "Always show sidebar on desktop": "แสดงแถบข้างเสมอบนเดสก์ท็อป",
    "Always keep the sidebar visible on desktop instead of auto-hiding it.": "แสดงแถบข้างค้างไว้บนเดสก์ท็อป ไม่ซ่อนอัตโนมัติ",
    "Conversation tabs": "แท็บแชต",
    "Show open chats as browser-style tabs above the conversation, one per open chat. When disabled, only one chat is shown at a time.":
      "แสดงแชตที่เปิดอยู่เป็นแท็บแบบเบราว์เซอร์เหนือหน้าแชต แชตละแท็บ ถ้าปิดจะแสดงทีละแชต",
    "Show raw model names": "แสดงชื่อโมเดลแบบเต็ม",
    "Display full raw model identifiers (e.g. \"ggml-org/GLM-4.7-Flash-GGUF:Q8_0\") instead of parsed names with badges.":
      "แสดงชื่อโมเดลตามต้นฉบับ (เช่น \"ggml-org/GLM-4.7-Flash-GGUF:Q8_0\") แทนชื่อย่อพร้อมป้าย",
    "Show model quantization information": "แสดงข้อมูล quantization ของโมเดล",
    "Display quantization badges (e.g. Q8_0, Q4_K_M) next to model names throughout the interface.":
      "แสดงป้าย quantization (เช่น Q8_0, Q4_K_M) ข้างชื่อโมเดลทุกที่",
    "Show model tags": "แสดงแท็กของโมเดล",
    "Display model tags (e.g. \"vision\", \"reasoning\") next to model names throughout the interface.":
      "แสดงแท็กของโมเดล (เช่น \"vision\", \"reasoning\") ข้างชื่อโมเดลทุกที่",
    "Show organization name in model selector trigger": "แสดงชื่อองค์กรในปุ่มเลือกโมเดล",
    "Display the organization name in the model selector trigger button.": "แสดงชื่อองค์กร (เช่น ggml-org) บนปุ่มเลือกโมเดล",
    "Show build version information": "แสดงเวอร์ชันบิลด์",
    "Display the current build version in the bottom-right corner of the interface.": "แสดงเวอร์ชันบิลด์ปัจจุบันที่มุมขวาล่างของหน้าจอ",
    "Show full path in mentions": "แสดง path เต็มใน mention",
    "Display the full file system path inside file and folder @-mention badges instead of just the file or folder name.":
      "แสดง path เต็มในป้าย @-mention ของไฟล์และโฟลเดอร์ แทนที่จะแสดงแค่ชื่อ",
    // เครื่องมือ
    "Applies to new conversations. Tool picks inside a chat only affect that chat.": "มีผลกับแชตใหม่ การเลือกเครื่องมือภายในแชตมีผลเฉพาะแชตนั้น",
    "MCP servers": "เซิร์ฟเวอร์ MCP",
    "Configure MCP servers as a JSON list. Use the form in the MCP Client settings section to edit.":
      "ตั้งค่าเซิร์ฟเวอร์ MCP เป็นรายการ JSON แก้ไขได้จากฟอร์มในส่วนตั้งค่า MCP",
    "Browser Tools": "เครื่องมือในเบราว์เซอร์", "Custom Tools": "เครื่องมือที่กำหนดเอง", "Server Tools": "เครื่องมือของเซิร์ฟเวอร์",
    // เอเจนต์
    "Agentic turns": "จำนวนรอบเอเจนต์สูงสุด",
    "Maximum number of tool execution cycles before stopping (prevents infinite loops).": "จำนวนรอบการเรียกเครื่องมือสูงสุดก่อนหยุด (กันการวนไม่รู้จบ)",
    "MCP request timeout (seconds)": "เวลารอคำขอ MCP (วินาที)",
    "Timeout for individual MCP tool calls.": "เวลาสูงสุดที่รอการเรียกเครื่องมือ MCP แต่ละครั้ง",
    "Mention search depth": "ความลึกในการค้นหา mention",
    "How many directory levels below the working directory the @-mention file search descends. Larger values surface deeply nested files but take longer on large trees.":
      "จำนวนชั้นโฟลเดอร์ใต้โฟลเดอร์ทำงานที่การค้นหาไฟล์ด้วย @-mention จะลงไปค้น ค่ามากเจอไฟล์ที่อยู่ลึกได้ แต่ช้าลงกับโฟลเดอร์ใหญ่",
    // นำเข้า/ส่งออก
    "Export": "ส่งออก", "Import": "นำเข้า", "Exported": "ส่งออกแล้ว", "Imported": "นำเข้าแล้ว",
    "Export conversations": "ส่งออกแชต", "Import conversations": "นำเข้าแชต",
    "Download your conversations as a ZIP of JSONL files. This includes all messages, attachments, and conversation history.":
      "ดาวน์โหลดแชตทั้งหมดเป็นไฟล์ ZIP ของ JSONL รวมข้อความ ไฟล์แนบ และประวัติแชตทั้งหมด",
    "Import one or more conversations from a previously exported ZIP or JSONL file. This will merge with your existing conversations.":
      "นำเข้าแชตจากไฟล์ ZIP หรือ JSONL ที่เคยส่งออกไว้ จะรวมเข้ากับแชตที่มีอยู่",
    "Delete All": "ลบทั้งหมด", "Delete all conversations": "ลบแชตทั้งหมด",
    "Permanently delete all conversations and their messages. This action cannot be undone. Consider exporting your conversations first if you want to keep a backup.":
      "ลบแชตและข้อความทั้งหมดถาวร กู้คืนไม่ได้ ถ้าต้องการเก็บสำรองไว้ ให้ส่งออกแชตก่อน",
    "Are you sure you want to delete all conversations? This action cannot be undone and will permanently remove all your conversations and messages.":
      "ลบแชตทั้งหมด? แชตและข้อความทั้งหมดจะถูกลบถาวร กู้คืนไม่ได้",
    "Export settings": "ส่งออกการตั้งค่า", "Export Settings": "ส่งออกการตั้งค่า", "Import settings": "นำเข้าการตั้งค่า",
    "Export your chat settings and preferences as a JSON file.": "ส่งออกการตั้งค่าหน้าแชตเป็นไฟล์ JSON",
    "Import chat settings from a previously exported JSON file. This will merge with your existing settings.":
      "นำเข้าการตั้งค่าจากไฟล์ JSON ที่เคยส่งออกไว้ จะรวมเข้ากับการตั้งค่าเดิม",
    "Warning: This export will include sensitive data such as API keys and MCP server custom headers (e.g., authorization tokens). Do not share this file with anyone you don't trust.":
      "คำเตือน: ไฟล์ที่ส่งออกจะมีข้อมูลลับ เช่น API key และ header ที่กำหนดเองของเซิร์ฟเวอร์ MCP (เช่น token ยืนยันตัวตน) อย่าส่งไฟล์นี้ให้คนที่ไม่ไว้ใจ",
    "Sensitive data (API keys, MCP server custom headers) will not be included in the export to protect your credentials.":
      "ข้อมูลลับ (API key, header ที่กำหนดเองของเซิร์ฟเวอร์ MCP) จะไม่ถูกรวมในไฟล์ที่ส่งออก เพื่อปกป้องข้อมูลเข้าสู่ระบบของคุณ",
    "Include sensitive data (not recommended)": "รวมข้อมูลลับด้วย (ไม่แนะนำ)", "Include sensitive data": "รวมข้อมูลลับด้วย",
    "Export Anyway": "ส่งออกต่อไป", "Export Without Sensitive Data": "ส่งออกโดยไม่รวมข้อมูลลับ",
    "Choose which conversations you want to export. Selected conversations will be downloaded as a JSON file.":
      "เลือกแชตที่ต้องการส่งออก แชตที่เลือกจะถูกดาวน์โหลดเป็นไฟล์ JSON",
    "Choose which conversations you want to import. Selected conversations will be merged with your existing conversations.":
      "เลือกแชตที่ต้องการนำเข้า แชตที่เลือกจะรวมเข้ากับแชตที่มีอยู่",
    // การสุ่มและค่าปรับ (ชื่อพารามิเตอร์ที่เป็นศัพท์เฉพาะคงเป็นอังกฤษ แปลคำอธิบาย)
    "Controls the randomness of the generated text by affecting the probability distribution of the output tokens. Higher = more random, lower = more focused.":
      "ควบคุมความสุ่มของข้อความที่สร้างโดยปรับการกระจายความน่าจะเป็นของโทเค็น ค่าสูง = หลากหลายขึ้น ค่าต่ำ = ตรงประเด็นขึ้น",
    "Dynamic temperature range": "ช่วง Temperature แบบไดนามิก",
    "Addon for the temperature sampler. The added value to the range of dynamic temperature, which adjusts probabilities by entropy of tokens.":
      "ส่วนเสริมของ Temperature: ช่วงที่บวกเพิ่มให้ Temperature แบบไดนามิก ซึ่งปรับความน่าจะเป็นตามเอนโทรปีของโทเค็น",
    "Dynamic temperature exponent": "เลขชี้กำลัง Temperature แบบไดนามิก",
    "Addon for the temperature sampler. Smoothes out the probability redistribution based on the most probable token.":
      "ส่วนเสริมของ Temperature: ทำให้การกระจายความน่าจะเป็นใหม่นุ่มนวลขึ้น โดยอิงโทเค็นที่น่าจะเป็นที่สุด",
    "Keeps only k top tokens.": "เก็บไว้เฉพาะ k โทเค็นที่น่าจะเป็นสูงสุด",
    "Limits tokens to those that together have a cumulative probability of at least p": "จำกัดเฉพาะโทเค็นที่ความน่าจะเป็นสะสมรวมกันอย่างน้อย p",
    "Limits tokens based on the minimum probability for a token to be considered, relative to the probability of the most likely token.":
      "ตัดโทเค็นที่ความน่าจะเป็นต่ำกว่าเกณฑ์ขั้นต่ำ (เทียบกับโทเค็นที่น่าจะเป็นที่สุด)",
    "XTC probability": "ความน่าจะเป็น XTC", "XTC threshold": "เกณฑ์ XTC",
    "XTC sampler cuts out top tokens; this parameter controls the chance of cutting tokens at all. 0 disables XTC.":
      "XTC ตัดโทเค็นอันดับต้นๆ ออก ค่านี้คือโอกาสที่จะตัดเลย ใส่ 0 เพื่อปิด XTC",
    "XTC sampler cuts out top tokens; this parameter controls the token probability that is required to cut that token.":
      "XTC ตัดโทเค็นอันดับต้นๆ ออก ค่านี้คือความน่าจะเป็นขั้นต่ำที่โทเค็นจะถูกตัด",
    "Sorts and limits tokens based on the difference between log-probability and entropy.": "เรียงและจำกัดโทเค็นตามผลต่างระหว่าง log-probability กับเอนโทรปี",
    "The maximum number of token per output. Use -1 for infinite (no limit).": "จำนวนโทเค็นสูงสุดต่อคำตอบ ใส่ -1 เพื่อไม่จำกัด",
    "Samplers": "ลำดับ sampler",
    "The order at which samplers are applied, in simplified way. Default is \"top_k;typ_p;top_p;min_p;temperature\": top_k->typ_p->top_p->min_p->temperature":
      "ลำดับการใช้ sampler แบบย่อ ค่าเริ่มต้นคือ \"top_k;typ_p;top_p;min_p;temperature\": top_k->typ_p->top_p->min_p->temperature",
    "Backend sampling": "สุ่มโทเค็นบน backend",
    "Enable backend-based samplers. When enabled, supported samplers run on the accelerator backend for faster sampling.":
      "ให้ sampler ที่รองรับทำงานบน backend ของตัวเร่ง (เช่น GPU) เพื่อสุ่มโทเค็นได้เร็วขึ้น",
    "Repeat last N": "ช่วงตรวจการซ้ำ (N โทเค็น)", "Last n tokens to consider for penalizing repetition": "จำนวนโทเค็นล่าสุดที่ใช้ตรวจการซ้ำ",
    "Repeat penalty": "ค่าปรับการซ้ำ", "Controls the repetition of token sequences in the generated text": "ลดการซ้ำของลำดับโทเค็นในข้อความที่สร้าง",
    "Presence penalty": "ค่าปรับการปรากฏ", "Limits tokens based on whether they appear in the output or not.": "ลงโทษโทเค็นที่เคยปรากฏในคำตอบแล้ว",
    "Frequency penalty": "ค่าปรับความถี่", "Limits tokens based on how often they appear in the output.": "ลงโทษโทเค็นตามจำนวนครั้งที่ปรากฏในคำตอบ",
    "DRY multiplier": "ตัวคูณ DRY", "DRY base": "ค่าฐาน DRY", "DRY allowed length": "ความยาวที่ยอมให้ซ้ำ (DRY)",
    "DRY penalty last N": "ช่วงลงโทษของ DRY (N โทเค็น)",
    "DRY sampling reduces repetition in generated text even across long contexts. This parameter sets the DRY sampling multiplier.":
      "DRY ลดการซ้ำในข้อความที่สร้างได้แม้บริบทยาว ค่านี้คือตัวคูณของ DRY",
    "DRY sampling reduces repetition in generated text even across long contexts. This parameter sets the DRY sampling base value.":
      "DRY ลดการซ้ำในข้อความที่สร้างได้แม้บริบทยาว ค่านี้คือค่าฐานของ DRY",
    "DRY sampling reduces repetition in generated text even across long contexts. This parameter sets the allowed length for DRY sampling.":
      "DRY ลดการซ้ำในข้อความที่สร้างได้แม้บริบทยาว ค่านี้คือความยาวที่ยอมให้ซ้ำได้",
    "DRY sampling reduces repetition in generated text even across long contexts. This parameter sets DRY penalty for the last n tokens.":
      "DRY ลดการซ้ำในข้อความที่สร้างได้แม้บริบทยาว ค่านี้คือจำนวนโทเค็นล่าสุดที่ DRY ใช้ลงโทษ",
    // นักพัฒนา
    "Pre-fill KV cache after response": "เติม KV cache ล่วงหน้าหลังตอบ",
    "After each response, re-submit the conversation to pre-fill the server KV cache. Makes the next turn faster since the prompt is already encoded while you read the response.":
      "หลังตอบเสร็จ ส่งแชตกลับไปให้เซิร์ฟเวอร์เติม KV cache ไว้ก่อน รอบถัดไปจะเร็วขึ้นเพราะพรอมต์ถูกประมวลผลไว้แล้วระหว่างที่คุณอ่านคำตอบ",
    "Disable reasoning content parsing": "ปิดการแยกเนื้อหาการคิด",
    "Send reasoning_format=none so the server returns thinking tokens inline instead of extracting them into a separate field.":
      "ส่ง reasoning_format=none ให้เซิร์ฟเวอร์ส่งโทเค็นการคิดปนมากับคำตอบ แทนการแยกไว้อีกช่อง",
    "Exclude reasoning from context": "ไม่ส่งการคิดกลับเข้าบริบท",
    "Strip thinking from previous messages before sending. When off, thinking is sent back via the reasoning_content field so the model sees its own chain-of-thought across turns.":
      "ตัดส่วนการคิดของข้อความก่อนหน้าออกก่อนส่ง ถ้าปิด การคิดจะถูกส่งกลับในช่อง reasoning_content ให้โมเดลเห็นการคิดของตัวเองข้ามรอบ",
    "Enable raw output toggle": "เปิดสวิตช์แสดงผลดิบ",
    "Show toggle button to display messages as plain text instead of Markdown-formatted content": "แสดงสวิตช์ให้ดูข้อความเป็นข้อความล้วน แทนแบบจัดรูปแบบ Markdown",
    "JavaScript sandbox tool": "เครื่องมือ JavaScript sandbox",
    "Expose a run_javascript tool to the model. Code runs in a Web Worker inside a sandboxed iframe with an opaque origin, isolated from the WebUI and its API, with a hard timeout.":
      "ให้โมเดลใช้เครื่องมือ run_javascript ได้ โค้ดรันใน Web Worker ภายใน iframe แบบ sandbox ที่แยกจาก WebUI และ API และมีเวลาจำกัดตายตัว",
    "Symbolic math (nerdamer)": "คณิตศาสตร์เชิงสัญลักษณ์ (nerdamer)",
    "Pre-load nerdamer in the sandbox for symbolic computation: simplify, diff, integrate, solve, and more. Requires \"JavaScript sandbox tool\" to be enabled.":
      "โหลด nerdamer ไว้ใน sandbox สำหรับคำนวณเชิงสัญลักษณ์: ลดรูป อนุพันธ์ ปริพันธ์ แก้สมการ และอื่นๆ ต้องเปิด \"เครื่องมือ JavaScript sandbox\" ก่อน",
    "Custom JSON": "JSON กำหนดเอง", "Custom JSON parameters to send to the API. Must be valid JSON format.": "พารามิเตอร์ JSON เพิ่มเติมที่ส่งไปกับคำขอ API ต้องเป็น JSON ที่ถูกต้อง",
    "Custom CSS": "CSS กำหนดเอง",
    "CSS injected into the page at runtime. Set it here, or ship it server side via the --ui-config customCss field.":
      "CSS ที่ใส่เข้าหน้าเว็บขณะทำงาน ตั้งที่นี่ หรือส่งจากฝั่งเซิร์ฟเวอร์ผ่านช่อง customCss ของ --ui-config",
    // ---- หน้าต่าง MCP ----
    "Add your first MCP server": "เพิ่มเซิร์ฟเวอร์ MCP ตัวแรก", "Connect a remote MCP server by URL.": "เชื่อมต่อเซิร์ฟเวอร์ MCP ระยะไกลด้วย URL",
    "Add another MCP server": "เพิ่มเซิร์ฟเวอร์ MCP อีกตัว", "Add New Server": "เพิ่มเซิร์ฟเวอร์ใหม่",
    "Add New MCP Server": "เพิ่มเซิร์ฟเวอร์ MCP ใหม่", "Recommended Servers": "เซิร์ฟเวอร์ที่แนะนำ",
    "Server instructions": "คำแนะนำจากเซิร์ฟเวอร์", "Configure Server": "ตั้งค่าเซิร์ฟเวอร์", "Delete Server": "ลบเซิร์ฟเวอร์",
    "Server URL": "URL ของเซิร์ฟเวอร์", "Display name": "ชื่อที่แสดง", "Name reported by the server": "ชื่อที่เซิร์ฟเวอร์รายงาน",
    "URL is required": "ต้องใส่ URL", "Please enter a server URL first.": "ใส่ URL ของเซิร์ฟเวอร์ก่อน",
    "Use llama-server proxy": "ใช้พร็อกซีของ llama-server", "(Run": "(รัน", "with": "ด้วยแฟล็ก", "flag)": ")",
    "Authorization": "การยืนยันตัวตน", "Logging": "การบันทึก log", "Completions": "การเติมคำ",
    "Retrying...": "กำลังลองใหม่…", "List files": "แสดงรายการไฟล์", "Console": "คอนโซล", "Text": "ข้อความ",
    "Paste token here": "วาง token ที่นี่", "Custom Headers": "Header ที่กำหนดเอง", "Header name": "ชื่อ header",
    "No custom headers configured.": "ยังไม่มี header ที่กำหนดเอง", "No items configured.": "ยังไม่มีรายการ",
    "Remove item": "ลบรายการ", "Open website": "เปิดเว็บไซต์", "Resources": "ทรัพยากร", "Prompts": "พรอมต์",
    "Tasks": "งาน", "Templates": "เทมเพลต", "MCP Resources": "ทรัพยากร MCP", "Available resources": "ทรัพยากรที่ใช้ได้",
    "Loading resources...": "กำลังโหลดทรัพยากร…", "No resources available": "ไม่มีทรัพยากร", "No resources": "ไม่มีทรัพยากร",
    "Search resources...": "ค้นหาทรัพยากร…", "Refresh resources": "รีเฟรชทรัพยากร",
    "Select a resource to preview": "เลือกทรัพยากรเพื่อดูตัวอย่าง", "No content available": "ไม่มีเนื้อหา",
    "Failed to load resource content": "โหลดเนื้อหาทรัพยากรไม่สำเร็จ", "Copy content": "คัดลอกเนื้อหา",
    "Download content": "ดาวน์โหลดเนื้อหา", "Resolved URI:": "URI ที่ได้:", "Read Resource": "อ่านทรัพยากร",
    "Attach Resource": "แนบทรัพยากร", "Resource already attached": "แนบทรัพยากรนี้แล้ว", "Resource content": "เนื้อหาทรัพยากร",
    "Browse and attach resources from connected MCP servers to your chat context.": "เรียกดูและแนบทรัพยากรจากเซิร์ฟเวอร์ MCP ที่เชื่อมต่ออยู่เข้าในบริบทของแชต",
    "Binary content": "ข้อมูลไบนารี", "Connecting...": "กำลังเชื่อมต่อ…", "Connected": "เชื่อมต่อแล้ว",
    "Connection Error": "เชื่อมต่อไม่สำเร็จ", "All MCP server connections failed": "เชื่อมต่อเซิร์ฟเวอร์ MCP ไม่สำเร็จทั้งหมด",
    "Failed to read resource": "อ่านทรัพยากรไม่สำเร็จ",
    "Search the web and fetch full page content as clean markdown.": "ค้นเว็บและดึงเนื้อหาทั้งหน้ามาเป็น Markdown ที่อ่านง่าย",
    "Search and browse AI models, datasets, spaces, and docs on the Hugging Face Hub.": "ค้นหาและเรียกดูโมเดล AI ชุดข้อมูล Spaces และเอกสารบน Hugging Face Hub",
    "Search repositories, issues, pull requests and interact with code on GitHub.": "ค้นหา repository, issue, pull request และทำงานกับโค้ดบน GitHub",
    "Browse up-to-date documentation and code examples for libraries and frameworks.": "เรียกดูเอกสารและตัวอย่างโค้ดล่าสุดของไลบรารีและเฟรมเวิร์ก",
    // ---- หน้าต่างแจ้งปัญหาไฟล์ / เซิร์ฟเวอร์ ----
    "Empty Files Detected": "พบไฟล์ว่าง", "Empty Files:": "ไฟล์ว่าง:", "What happened:": "เกิดอะไรขึ้น:",
    "Empty files cannot be processed or sent to the AI model": "ไฟล์ว่างประมวลผลหรือส่งให้โมเดลไม่ได้",
    "These files have been automatically removed from your attachments": "ไฟล์เหล่านี้ถูกนำออกจากไฟล์แนบให้อัตโนมัติแล้ว",
    "You can try uploading files with content instead": "ลองอัปโหลดไฟล์ที่มีเนื้อหาแทน",
    "The following files are empty and have been removed from your attachments:": "ไฟล์ต่อไปนี้ว่างเปล่าและถูกนำออกจากไฟล์แนบแล้ว:",
    "File type not supported": "ไม่รองรับไฟล์ประเภทนี้", "Unsupported File Types": "ประเภทไฟล์ที่ไม่รองรับ",
    "This model supports:": "โมเดลนี้รองรับ:", "File Upload Error": "อัปโหลดไฟล์ไม่สำเร็จ",
    "Some files cannot be uploaded with the current model.": "บางไฟล์อัปโหลดกับโมเดลปัจจุบันไม่ได้",
    "Not supported by current model": "โมเดลปัจจุบันไม่รองรับ",
    "TCP Timeout": "TCP หมดเวลา", "Server Error": "เซิร์ฟเวอร์ผิดพลาด",
    "The request did not receive a response from the server before timing out.": "ไม่ได้รับการตอบกลับจากเซิร์ฟเวอร์ก่อนหมดเวลา",
    "The server responded with an error message. Review the details below.": "เซิร์ฟเวอร์ตอบกลับเป็นข้อผิดพลาด ดูรายละเอียดด้านล่าง",
    "Server Connection Error": "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้", "Connecting to Server": "กำลังเชื่อมต่อเซิร์ฟเวอร์",
    "Initializing connection to server...": "กำลังเริ่มเชื่อมต่อเซิร์ฟเวอร์…", "Troubleshooting": "การแก้ปัญหา",
    "Start the llama-server:": "เปิด llama-server:", "or": "หรือ",
    "Check that the server is accessible at the correct URL": "ตรวจว่าเข้าถึงเซิร์ฟเวอร์ได้ที่ URL ที่ถูกต้อง",
    "Verify your network connection": "ตรวจการเชื่อมต่อเครือข่าย", "Check server logs for any error messages": "ดูข้อผิดพลาดใน log ของเซิร์ฟเวอร์",
    "Enter API Key": "ใส่ API key", "Enter your API key...": "ใส่ API key…", "Validating...": "กำลังตรวจสอบ…",
    "Save & Retry": "บันทึกแล้วลองใหม่", "Retry Connection": "ลองเชื่อมต่ออีกครั้ง",
    "✓ API key validated successfully! Connecting...": "✓ API key ถูกต้อง กำลังเชื่อมต่อ…",
    "Invalid API key - please check and try again": "API key ไม่ถูกต้อง ตรวจแล้วลองใหม่",
    "Cannot connect to server - check if server is running": "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ตรวจว่าเซิร์ฟเวอร์ทำงานอยู่",
    "Connection error - please try again": "เชื่อมต่อผิดพลาด ลองอีกครั้ง",
    "Access denied - check server permissions": "ไม่มีสิทธิ์เข้าถึง ตรวจสิทธิ์ของเซิร์ฟเวอร์",
    "A new version is available. Reload to update.": "มีเวอร์ชันใหม่ โหลดหน้าใหม่เพื่ออัปเดต", "Update available": "มีอัปเดต",
    // ---- toast / ข้อผิดพลาด ----
    "Access denied": "ไม่มีสิทธิ์เข้าถึง", "Request failed": "คำขอล้มเหลว",
    "Server error - check server logs": "เซิร์ฟเวอร์ผิดพลาด ตรวจ log ของเซิร์ฟเวอร์",
    "Server temporarily unavailable": "เซิร์ฟเวอร์ใช้งานไม่ได้ชั่วคราว", "Failed to connect to server": "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ",
    "Server not found - check server address": "ไม่พบเซิร์ฟเวอร์ ตรวจที่อยู่เซิร์ฟเวอร์",
    "Connection refused - server may be offline": "การเชื่อมต่อถูกปฏิเสธ เซิร์ฟเวอร์อาจปิดอยู่",
    "Request timed out": "คำขอหมดเวลา", "Server is not running or unreachable": "เซิร์ฟเวอร์ไม่ได้ทำงานหรือเข้าถึงไม่ได้",
    "Unable to connect to server - please check if the server is running": "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ตรวจว่าเซิร์ฟเวอร์ทำงานอยู่",
    "Request timed out - the server took too long to respond": "คำขอหมดเวลา เซิร์ฟเวอร์ตอบช้าเกินไป",
    "Unknown error occurred while sending message": "เกิดข้อผิดพลาดขณะส่งข้อความ",
    "No response received from server. Please try again.": "ไม่ได้รับคำตอบจากเซิร์ฟเวอร์ ลองอีกครั้ง",
    "Unknown server error": "เซิร์ฟเวอร์ผิดพลาดโดยไม่ทราบสาเหตุ", "Unknown error": "ข้อผิดพลาดที่ไม่ทราบสาเหตุ",
    "Unknown error occurred": "เกิดข้อผิดพลาดที่ไม่ทราบสาเหตุ", "Stream connection lost and could not be resumed": "การเชื่อมต่อสตรีมหลุดและต่อใหม่ไม่ได้",
    "No active conversation": "ไม่มีแชตที่เปิดอยู่", "Failed to read file": "อ่านไฟล์ไม่สำเร็จ", "File reading error": "อ่านไฟล์ผิดพลาด",
    "Failed to access microphone. Please check permissions.": "เข้าถึงไมโครโฟนไม่ได้ ตรวจสิทธิ์อีกครั้ง", "Recording failed": "อัดเสียงไม่สำเร็จ",
    "Conversation deleted": "ลบแชตแล้ว", "Failed to delete conversations": "ลบแชตไม่สำเร็จ",
    "No conversations to export": "ไม่มีแชตให้ส่งออก", "Conversation exported": "ส่งออกแชตแล้ว",
    "Failed to export conversations": "ส่งออกแชตไม่สำเร็จ", "Conversation pin toggled": "เปลี่ยนการปักหมุดแล้ว",
    "Failed to update pin state": "เปลี่ยนการปักหมุดไม่สำเร็จ", "All conversations deleted": "ลบแชตทั้งหมดแล้ว",
    "Conversation forked": "แยกแชตแล้ว", "Failed to fork conversation": "แยกแชตไม่สำเร็จ",
    "Failed to load model": "โหลดโมเดลไม่สำเร็จ", "Failed to unload model": "เลิกโหลดโมเดลไม่สำเร็จ",
    "Failed to load models": "โหลดรายการโมเดลไม่สำเร็จ",
    "Failed to load favorite models from local storage": "โหลดรายการโมเดลโปรดจากเบราว์เซอร์ไม่สำเร็จ",
    "Failed to save favorite models to local storage": "บันทึกรายการโมเดลโปรดลงเบราว์เซอร์ไม่สำเร็จ",
    "Settings exported": "ส่งออกการตั้งค่าแล้ว", "Failed to export settings": "ส่งออกการตั้งค่าไม่สำเร็จ",
    "Settings imported successfully": "นำเข้าการตั้งค่าแล้ว", "Failed to import settings": "นำเข้าการตั้งค่าไม่สำเร็จ",
    "Invalid settings file: missing config": "ไฟล์การตั้งค่าไม่ถูกต้อง: ไม่มี config",
    "Invalid settings data: missing config": "ข้อมูลการตั้งค่าไม่ถูกต้อง: ไม่มี config",
    "Failed to open file picker": "เปิดหน้าต่างเลือกไฟล์ไม่สำเร็จ", "Failed to load conversations": "โหลดแชตไม่สำเร็จ",
    "No conversations found in file": "ไม่พบแชตในไฟล์", "Failed to import conversations": "นำเข้าแชตไม่สำเร็จ",
    "Failed to import conversations. Please check the file format.": "นำเข้าแชตไม่สำเร็จ ตรวจรูปแบบไฟล์อีกครั้ง",
    "No conversations to delete": "ไม่มีแชตให้ลบ",
    "Error processing file": "ประมวลผลไฟล์ไม่สำเร็จ", "Enable PDF as Images": "อ่าน PDF เป็นรูปภาพ",
    "You can enable parsing PDF as images with vision models.": "เปิดการอ่าน PDF เป็นรูปภาพได้เมื่อใช้โมเดลที่รองรับภาพ",
    "PDF parsing as images enabled!": "เปิดการอ่าน PDF เป็นรูปภาพแล้ว!",
    "PDF setting changed: Non-vision model detected, PDFs will be processed as text instead of images.":
      "เปลี่ยนการตั้งค่า PDF: โมเดลไม่รองรับภาพ จะอ่าน PDF เป็นข้อความแทนรูปภาพ",
    // ---- รอบ 4: ป้ายของส่วนที่ enhance ใส่เอง (ชิปโมเดลเร็ว, เปิดในแผง, อ่านออกเสียง, ถามเรื่องนี้, การแจ้งเตือน) ----
    // เขียนเป็นอังกฤษลง DOM แล้วให้ตัวแปลชุดเดียวกับ UI ของ WebUI แปล — setLang() สลับภาษาได้สดโดยไม่ต้องจัดการเอง
    "Fast (4B)": "เร็ว (4B)",
    "Fast mode: answer with Qwen3-4B, much faster but less thorough. Click again to go back to the project model (if it isn't loaded yet, it loads first: large and slow).":
      "โหมดเร็ว: ให้ Qwen3-4B ตอบ เร็วกว่ามากแต่คิดละเอียดน้อยกว่า กดอีกครั้งเพื่อกลับไปใช้โมเดลของโปรเจกต์ (ถ้ายังไม่ได้โหลด จะโหลดก่อน ซึ่งเป็นโมเดลใหญ่และใช้เวลานาน)",
    "Click again to load the project model and switch back.": "กดอีกครั้งเพื่อโหลดโมเดลของโปรเจกต์แล้วสลับกลับ",
    "{model} isn't loaded yet. Click again to load it and switch back (large model, slow to load).":
      "{model} ยังไม่ได้โหลด กดอีกครั้งเพื่อโหลดแล้วสลับกลับ (โมเดลใหญ่ โหลดนาน)",
    "Couldn't switch the model. Choose it from the model menu instead.": "สลับโมเดลไม่สำเร็จ เลือกจากเมนูโมเดลแทน",
    "Open the chat to read the reply.": "เปิดแชตเพื่ออ่านคำตอบ",
    "Open in panel": "เปิดในแผง",
    "Read aloud": "อ่านออกเสียง", "Pause reading": "หยุดอ่านชั่วคราว", "Resume reading": "อ่านต่อ",
    "Stop reading": "หยุดอ่าน", "Ask about this": "ถามเรื่องนี้",
    "HTML page": "หน้า HTML", "SVG image": "ภาพ SVG", "Mermaid diagram": "แผนภาพ Mermaid",
    "Markdown document": "เอกสาร Markdown", "CSV table": "ตาราง CSV", "Chart image": "ภาพกราฟ",
    "Reply finished": "ตอบเสร็จแล้ว", "Tool permission needed": "รอคุณอนุญาตใช้เครื่องมือ",
    "Agentic turn limit reached": "ถึงจำนวนรอบเอเจนต์สูงสุดแล้ว",
    "Press Continue to keep going, or Stop.": "กด \"ทำต่อ\" เพื่อให้ทำงานต่อ หรือกด \"หยุด\"",
    // ---- รอบ 5 (R4): กล่องตรวจทานในการ์ดอนุญาต local_confirm — ปุ่มปฏิเสธของ WebUI แปลว่า "ปฏิเสธ" จึงใช้คำเดียวกัน ----
    "Review this — it is exactly what will run": "ตรวจโค้ด/คำสั่งนี้ก่อนกดอนุญาต — นี่คือสิ่งที่จะรันจริง",
    "Loading what will run...": "กำลังโหลดสิ่งที่จะรัน…",
    "Confirm code": "รหัสยืนยัน",
    "Hidden or look-alike characters are shown as «U+XXXX». Don't allow unless you expected them.":
      "อักขระที่มองไม่เห็นหรือหน้าตาคล้ายตัวอื่นแสดงเป็น «U+XXXX» — อย่าอนุญาตถ้าไม่ได้ตั้งใจให้มี",
    "This request has no review text, so you can't see what will run. Choose Deny.":
      "คำขอนี้ไม่มีข้อความให้ตรวจ จึงไม่เห็นว่าจะรันอะไร — กดปฏิเสธ",
    "Arguments sent by the model:": "อาร์กิวเมนต์ที่โมเดลส่งมา:",
    "This request's arguments aren't valid JSON. Choose Deny.": "อาร์กิวเมนต์ของคำขอนี้ไม่ใช่ JSON ที่ถูกต้อง — กดปฏิเสธ",
    "Couldn't read what this request will run. Expand the local_confirm call above to check it, or choose Deny.":
      "อ่านไม่ได้ว่าคำขอนี้จะรันอะไร — กางรายการ local_confirm ด้านบนเพื่อตรวจ หรือกดปฏิเสธ",
    "This review is far longer than the server ever issues. Choose Deny.":
      "ข้อความตรวจทานนี้ยาวเกินกว่าที่เซิร์ฟเวอร์ออกให้จริง — กดปฏิเสธ",
    // ---- รอบ 5 แก้หลังรีวิว: ช่องว่างที่โมเดลเติม, สวิตช์ "อนุญาตเสมอ" ที่ล็อกไว้, ป้ายผลของ local_confirm บนแถวเครื่องมือ ----
    "The model padded this text with extra blank lines or spaces (left out here). The server refuses text padded like this, so allowing it won't run anything. Choose Deny.":
      "โมเดลเติมบรรทัดว่างหรือช่องว่างเกินมาในข้อความนี้ (ตัดออกให้ดูแล้ว) — เซิร์ฟเวอร์ไม่รับข้อความที่เติมแบบนี้ กดอนุญาตก็ไม่มีอะไรรัน กดปฏิเสธ",
    "local_confirm always asks, so you can see exactly what will run before you allow it.":
      "local_confirm ถามทุกครั้งเสมอ เพื่อให้คุณเห็นสิ่งที่จะรันจริงก่อนกดอนุญาต",
    "Ran — expand to see the result": "รันแล้ว — กางดูผลลัพธ์",
    "Not run — the review text didn't match": "ไม่ได้รัน — review ไม่ตรง",
    "Not run — the confirm code expired or was already used": "ไม่ได้รัน — รหัสยืนยันหมดอายุหรือถูกใช้ไปแล้ว",
    "Not run — you chose Deny": "ไม่ได้รัน — คุณกดปฏิเสธ",
    "Not run — interrupted": "ไม่ได้รัน — ถูกขัดจังหวะ",
    "Not run — refused": "ไม่ได้รัน — ถูกปฏิเสธ",
    "Failed — expand to see the error": "ล้มเหลว — กางดูข้อผิดพลาด",
    // ---- S3 (2026-09-30 ดึก): การ์ด local_confirm แสดง review "ของเซิร์ฟเวอร์" (GET /review/<slug>) แทนข้อความที่โมเดลส่ง ----
    // หัวกล่องต้องตรงตามสัญญาทุกตัวอักษร: "ตรวจโค้ด/คำสั่งนี้ก่อนกดอนุญาต — นี่คือสิ่งที่จะรันจริง (จากเซิร์ฟเวอร์)"
    "Review this before you allow it — this is exactly what will run (from the server)":
      "ตรวจโค้ด/คำสั่งนี้ก่อนกดอนุญาต — นี่คือสิ่งที่จะรันจริง (จากเซิร์ฟเวอร์)",
    "Could not load details — do not allow": "โหลดรายละเอียดไม่ได้ — อย่ากดอนุญาต",
    "The review the model sent differs from the server's version below. The server will refuse it, so allowing runs nothing.":
      "review ที่โมเดลส่งมาไม่ตรงกับของเซิร์ฟเวอร์ด้านล่าง — เซิร์ฟเวอร์จะปฏิเสธ กดอนุญาตก็ไม่มีอะไรรัน",
    "Couldn't find this request in the chat.": "หาคำขอนี้ในแชตไม่เจอ",
    "This request has no valid confirm code.": "คำขอนี้ไม่มีรหัสยืนยันที่ถูกต้อง",
    "The server has no pending request for this confirm code — it expired, was already used, or never existed.":
      "เซิร์ฟเวอร์ไม่มีคำขอที่รออยู่สำหรับรหัสยืนยันนี้ — หมดอายุ ถูกใช้ไปแล้ว หรือไม่เคยมี",
    "This confirm code belongs to another project.": "รหัสยืนยันนี้เป็นของโปรเจกต์อื่น",
    "This confirm code has expired.": "รหัสยืนยันนี้หมดอายุแล้ว",
    "The local tool server refused this page's request.": "เซิร์ฟเวอร์เครื่องมือในเครื่องไม่รับคำขอจากหน้านี้",
    "The local tool server didn't answer.": "เซิร์ฟเวอร์เครื่องมือในเครื่องไม่ตอบ",
    "The local tool server is busy.": "เซิร์ฟเวอร์เครื่องมือในเครื่องไม่ว่าง",
    "The local tool server can't show request details yet (it needs an update).":
      "เซิร์ฟเวอร์เครื่องมือในเครื่องยังแสดงรายละเอียดคำขอไม่ได้ (ต้องอัปเดต)",
    "The server's answer couldn't be read.": "อ่านคำตอบของเซิร์ฟเวอร์ไม่ได้",
    "This page has no local tool server set up.": "หน้านี้ไม่ได้ตั้งค่าเซิร์ฟเวอร์เครื่องมือในเครื่องไว้",
    // คีย์ต้องใช้ "..." ไม่ใช่ "…": txKey แปลง … เป็น ... ก่อนค้นพจนานุกรม (คีย์ที่มี … จะไม่มีวันถูกแปล)
    "Trying again...": "กำลังลองใหม่…"
  };
  // คำทับศัพท์ที่พจนานุกรมตัดคำของเบราว์เซอร์ไม่รู้จัก จะถูกตัดกลางคำตอนขึ้นบรรทัดใหม่ (เห็นจริงบนจอ 390px:
  // "…ของโท|เค็น") — ใส่ U+2060 (word joiner) ระหว่างตัวอักษรของคำเหล่านี้ ยกเว้นหน้าสระ/วรรณยุกต์ที่ซ้อนบน-ล่าง
  // (แยกออกจากพยัญชนะแล้วจะวาดเป็นวงกลมประ) ทำครั้งเดียวกับ TH ตอนเริ่ม และกับผลของ TH_RE ทุกครั้ง
  // "ตัวเอง" เป็นคำไทยแท้แต่ตัวตัดคำแยกเป็น "ตัว|เอง" (เห็นในคำอธิบาย "ไม่ส่งการคิดกลับเข้าบริบท" บนเดสก์ท็อป)
  var GLUE_RE = new RegExp(["โทเค็น", "พรอมต์", "เอเจนต์", "เซิร์ฟเวอร์", "อาร์กิวเมนต์", "เอาต์พุต", "อินพุต",
    "ไดนามิก", "เอนโทรปี", "แคช", "สวิตช์", "เวอร์ชัน", "บิลด์", "เรนเดอร์", "รีเซ็ต", "รีเฟรช", "พร็อกซี", "ไบนารี",
    "เทมเพลต", "โปรโตคอล", "เฟรมเวิร์ก", "ไลบรารี", "คลิปบอร์ด", "เดสก์ท็อป", "ไมโครโฟน", "พิกเซล", "ซอร์ส",
    "แฟล็ก", "ไบต์", "โปรเจกต์", "เบราว์เซอร์", "อัปโหลด", "ดาวน์โหลด", "อัปเดต", "แท็บ", "แท็ก",
    "พารามิเตอร์", "ไฟล์", "โมเดล", "แชต", "ตัวเอง"].join("|"), "g");
  function glue(s) {
    return s.replace(GLUE_RE, function (w) {
      return w.replace(/(.)(?=[^ัิ-ฺ็-๎])/g, "$1⁠");
    });
  }
  (function () { for (var k in TH) if (Object.prototype.hasOwnProperty.call(TH, k)) TH[k] = glue(TH[k]); })();

  // รูปแบบที่มีตัวเลข/ชื่อปน: [regex ทั้งข้อความ, ฟังก์ชันคืนภาษาไทย] — ส่วนที่จับได้ (ชื่อ, ตัวเลข) คงตามเดิม
  // ป้ายสถิติมาก่อน เพราะเปลี่ยนทุกโทเค็นระหว่างสตรีม (เจอเร็ว = เช็กน้อยข้อ)
  var STAT_UNIT_TH = { "tokens": "โทเค็น", "tokens/s": "โทเค็น/วิ", "t/s": "โทเค็น/วิ", "tok": "โทเค็น",
    "calls": "ครั้ง", "calls/s": "ครั้ง/วิ", "turns": "รอบ" };
  var DUR_TH = { h: "ชม.", min: "นาที", s: "วิ" };
  // U+2060 (word joiner) ใน "ไม่ได้": ตัวตัดคำไทยของเบราว์เซอร์ตัดระหว่าง "ไม่|ได้" ได้ บนมือถือเลยเหลือ "ได้" ค้างบรรทัดเดียว
  var NO_UNDO_TH = "กู้คืนไม่⁠ได้";
  function thVerb(v) { return v === "Export" || v === "Exported" ? "ส่งออก" : "นำเข้า"; }
  var TH_RE = [
    [/^([\d.,]+) ?(tokens\/s|tokens|t\/s|tok|calls\/s|calls|turns)$/, function (_, n, u) { return n + " " + STAT_UNIT_TH[u]; }],
    // ระยะเวลาจาก formatter ของ WebUI: "0.7s", "12.3s", "2min 22s", "1h 5min"
    [/^(?=\d)(\d+h)? ?(\d+min)? ?([\d.]+s)?$/, function (t) {
      return t.replace(/([\d.]+)(h|min|s)/g, function (_, n, u) { return n + " " + DUR_TH[u]; });
    }],
    [/^(\d+) tools?$/, function (_, n) { return n + " เครื่องมือ"; }],
    // คำอธิบายใต้ระดับการคิด: "สูงสุด" เป็นชื่อระดับ Max อยู่แล้ว ถ้าใช้ซ้ำเป็นคำนำเพดาน แถว "สูงสุด — ไม่จำกัด"
    // จะอ่านเหมือนคำอธิบายของแถวบน จึงใช้ "ไม่เกิน" สำหรับเพดานโทเค็น
    [/^Max ([\d,]+) tokens$/, function (_, n) { return "ไม่เกิน " + n + " โทเค็น"; }],
    [/^Default: (.+)$/, function (_, v) { return "ค่าเริ่มต้น: " + v; }],
    [/^Processing \((\d+)%\)$/, function (_, p) { return "กำลังประมวลผล (" + p + "%)"; }],
    [/^Processing (\d+)% \(ETA: (\d+)s\)$/, function (_, p, s) { return "กำลังประมวลผล " + p + "% (อีกราว " + s + " วิ)"; }],
    [/^Processing (\d+)%$/, function (_, p) { return "กำลังประมวลผล " + p + "%"; }],
    [/^Context: (.+)$/, function (_, v) { return "บริบท: " + v; }],
    [/^Output: (.+)$/, function (_, v) { return "เอาต์พุต: " + v; }],
    [/^([\d.,]+[KMB]?) remaining$/, function (_, n) { return "เหลือ " + n; }],
    [/^([\d,]+) fresh \+ ([\d,]+) cached$/, function (_, a, b) { return "ใหม่ " + a + " + แคช " + b; }],
    [/^([\d,]+) reused from KV cache$/, function (_, n) { return "ใช้ซ้ำจาก KV cache " + n; }],
    [/^(Enable|Disable) ([\d,]+) tools?$/, function (_, v, n) { return (v === "Enable" ? "เปิด " : "ปิด ") + n + " เครื่องมือ"; }],
    [/^([\d,]+) args?$/, function (_, n) { return n + " อาร์กิวเมนต์"; }],
    [/^([\d,]+) tools available · Show details$/, function (_, n) { return "มี " + n + " เครื่องมือ · ดูรายละเอียด"; }],
    [/^· Connected in ([\d.,]+)ms$/, function (_, n) { return "· เชื่อมต่อใน " + n + " ms"; }],
    [/^Connection Log \((\d+)\)$/, function (_, n) { return "บันทึกการเชื่อมต่อ (" + n + ")"; }],
    [/^Protocol version: (.+)$/, function (_, v) { return "เวอร์ชันโปรโตคอล: " + v; }],
    [/^Binary content \((.+)\)$/, function (_, v) { return "ข้อมูลไบนารี (" + v + ")"; }],
    [/^, ([\d,]+) templates?$/, function (_, n) { return ", " + n + " เทมเพลต"; }],
    [/^\(([\d,]+) resources?$/, function (_, n) { return "(" + n + " ทรัพยากร"; }],
    [/^Resource attached: (.+)$/, function (_, v) { return "แนบทรัพยากรแล้ว: " + v; }],
    [/^([\d,]+) resources attached$/, function (_, n) { return "แนบ " + n + " ทรัพยากรแล้ว"; }],
    [/^Priority: (.+)$/, function (_, v) { return "ลำดับความสำคัญ: " + v; }],
    [/^Server: (.+)$/, function (_, v) { return "เซิร์ฟเวอร์: " + v; }],
    [/^Error: (.+)$/, function (_, v) { return "ข้อผิดพลาด: " + v; }],
    [/^Error (\d+)$/, function (_, v) { return "ข้อผิดพลาด " + v; }],
    [/^Authentication failed \((.+)\)$/, function (_, v) { return "ยืนยันตัวตนไม่สำเร็จ (" + v + ")"; }],
    [/^Connection failed: (.+)$/, function (_, v) { return "เชื่อมต่อไม่สำเร็จ: " + v; }],
    [/^Failed to reconnect to "(.+)"$/, function (_, v) { return "เชื่อมต่อ \"" + v + "\" ใหม่ไม่สำเร็จ"; }],
    [/^Server "(.+)" is not connected$/, function (_, v) { return "เซิร์ฟเวอร์ \"" + v + "\" ไม่ได้เชื่อมต่อ"; }],
    [/^Server error \((\d+)\): (.+)$/, function (_, c, v) { return "เซิร์ฟเวอร์ผิดพลาด (" + c + "): " + v; }],
    [/^Delete "(.+)"\? This action cannot be undone\.$/, function (_, v) { return "ลบ \"" + v + "\"? " + NO_UNDO_TH; }],
    [/^Invalid numeric value for (.+)\. Please enter a valid number\.$/, function (_, v) { return "ค่าของ " + v + " ไม่ใช่ตัวเลขที่ถูกต้อง ใส่ตัวเลขอีกครั้ง"; }],
    [/^Always allow all tools from (.+)$/, function (_, v) { return "อนุญาตทุกเครื่องมือจาก " + v + " เสมอ"; }],
    [/^Approve all tools from (.+)$/, function (_, v) { return "อนุมัติทุกเครื่องมือจาก " + v; }],
    [/^Edit ([\d,]+) of ([\d,]+)$/, function (_, a, b) { return "แก้ไขที่ " + a + " จาก " + b; }],
    [/^\(lines ([\d,]+)-([\d,]+)\)$/, function (_, a, b) { return "(บรรทัด " + a + "-" + b + ")"; }],
    // กล่องตรวจทาน (R4) บอกเมื่อข้อความยาวเกินกล่อง
    [/^([\d,]+) lines — scroll to read them all$/, function (_, n) { return n + " บรรทัด — เลื่อนอ่านให้ครบ"; }],
    [/^Size: ([\d,]+) bytes$/, function (_, n) { return "ขนาด: " + n + " ไบต์"; }],
    [/^· timeout ([\d,]+) ms$/, function (_, n) { return "· หมดเวลา " + n + " ms"; }],
    [/^(PDF )?Page ([\d,]+)$/, function (_, p, n) { return (p ? "หน้า PDF " : "หน้า ") + n; }],
    [/^Message version ([\d,]+) of ([\d,]+)$/, function (_, a, b) { return "ข้อความเวอร์ชัน " + a + " จาก " + b; }],
    // หน้าต่างยืนยันลบข้อความ / แชต (ตัวเลขมาจาก WebUI)
    [/^Delete ([\d,]+) Messages$/, function (_, n) { return "ลบ " + n + " ข้อความ"; }],
    [/^This will delete ([\d,]+) messages including: ([\d,]+) user messages? and ([\d,]+) assistant responses?\. All messages in this branch and their responses will be permanently removed\. This action cannot be undone\.$/,
      function (_, a, u, r) {
        return "จะลบทั้งหมด " + a + " ข้อความ (ข้อความของคุณ " + u + " และคำตอบ " + r +
          ") คือข้อความนี้กับทุกข้อความที่ต่อจากมันในแขนงนี้ ลบแล้ว" + NO_UNDO_TH;
      }],
    [/^Delete ([\d,]+) conversations?$/, function (_, n) { return "ลบ " + n + " แชต"; }],
    [/^This action cannot be undone\. The selected conversations? and (its|their) messages will be permanently removed, including any forks\.$/,
      function () { return "แชตที่เลือกและข้อความทั้งหมดจะถูกลบถาวร รวมถึงแชตที่แยกออกไป " + NO_UNDO_TH; }],
    [/^([\d,]+) \/ ([\d,]+) selected$/, function (_, a, b) { return "เลือก " + a + " / " + b; }],
    [/^([\d,]+) of ([\d,]+) selected$/, function (_, a, b) { return "เลือกแล้ว " + a + " จาก " + b; }],
    [/^\(([\d,]+) shown\)$/, function (_, n) { return "(แสดง " + n + ")"; }],
    [/^(Export|Import) \(([\d,]+)\)$/, function (_, v, n) { return thVerb(v) + " (" + n + ")"; }],
    [/^Select Conversations to (Export|Import)$/, function (_, v) { return "เลือกแชตที่จะ" + thVerb(v); }],
    [/^(Exported|Imported) ([\d,]+) conversations?$/, function (_, v, n) { return thVerb(v) + "แล้ว " + n + " แชต"; }],
    [/^No conversations found matching "(.*)"$/, function (_, v) { return "ไม่พบแชตที่ตรงกับ \"" + v + "\""; }],
    [/^\.\.\. and ([\d,]+) more$/, function (_, n) { return "…และอีก " + n + " รายการ"; }],
    [/^Skipped ([\d,]+) conversations? already in your library$/, function (_, n) { return "ข้าม " + n + " แชตที่มีอยู่แล้ว"; }],
    [/^([\d,]+) conversations deleted$/, function (_, n) { return "ลบ " + n + " แชตแล้ว"; }],
    [/^([\d,]+) conversations exported$/, function (_, n) { return "ส่งออก " + n + " แชตแล้ว"; }],
    [/^Updated pin state for ([\d,]+) conversations$/, function (_, n) { return "เปลี่ยนการปักหมุด " + n + " แชตแล้ว"; }],
    [/^(Export|Import) failed: (.+)$/, function (_, v, e) { return thVerb(v) + "ไม่สำเร็จ: " + e; }],
    // toast ของโมเดล (ชื่อโมเดลคงเดิม)
    [/^Model loaded: (.+)$/, function (_, v) { return "โหลดโมเดลแล้ว: " + v; }],
    [/^Failed to load model: (.+)$/, function (_, v) { return "โหลดโมเดลไม่สำเร็จ: " + v; }],
    [/^Model unloaded: (.+)$/, function (_, v) { return "เลิกโหลดโมเดลแล้ว: " + v; }],
    [/^Failed to unload model: (.+)$/, function (_, v) { return "เลิกโหลดโมเดลไม่สำเร็จ: " + v; }],
    [/^Model failed: (.+)$/, function (_, v) { return "โมเดลล้มเหลว: " + v; }],
    [/^Model removed: (.+)$/, function (_, v) { return "นำโมเดลออกแล้ว: " + v; }],
    [/^Failed to parse file: (.+)$/, function (_, v) { return "อ่านไฟล์ไม่สำเร็จ: " + v; }],
    [/^PDF "(.+)" processed as ([\d,]+) images for vision model\.$/, function (_, v, n) { return "แปลง PDF \"" + v + "\" เป็นรูปภาพ " + n + " หน้าให้โมเดลที่รองรับภาพแล้ว"; }],
    [/^PDF "(.+)" processed as text content\.$/, function (_, v) { return "อ่าน PDF \"" + v + "\" เป็นข้อความแล้ว"; }],
    [/^File (.+) is empty and will be skipped$/, function (_, v) { return "ไฟล์ " + v + " ว่างเปล่า จะถูกข้าม"; }],
    [/^File (.+) appears to be binary and will be skipped$/, function (_, v) { return "ไฟล์ " + v + " เป็นไฟล์ไบนารี จะถูกข้าม"; }],
    // ไฟล์แนบ: ขนาดจาก formatter ของ WebUI ("22 Bytes", "1.5 KB" — KB/MB/GB เป็นหน่วยสากล คงไว้)
    // และชื่อปุ่ม "Go to <ชื่อไฟล์>" (ภาพย่อในหน้าต่างดูตัวอย่าง) / "Preview <ชื่อไฟล์>" (การ์ดไฟล์แนบ) — ชื่อไฟล์คงเดิม
    [/^([\d.]+) Bytes$/, function (_, n) { return n + " ไบต์"; }],
    [/^Go to (.+)$/, function (_, v) { return "ไปที่ " + v; }],
    [/^Preview (.+)$/, function (_, v) { return "ดูตัวอย่าง " + v; }],
    // ช่องเลือกแชตในโหมดเลือกหลายรายการ: "Select <ชื่อแชต>" (ชื่อแชตคงเดิม) — ต้องอยู่ท้ายสุด หลังรูปแบบ Select อื่น
    [/^(Select|Deselect) (.+)$/, function (_, v, n) { return (v === "Select" ? "เลือก " : "เลิกเลือก ") + n; }]
  ];

  // ประโยคที่เทมเพลตของ WebUI แยกเป็นหลาย text node รอบชื่อที่เน้นตัวหนา ตัวจับทั้งข้อความจึงไม่เคยเห็นทั้งประโยค:
  // "Are you sure you want to delete <strong>ชื่อเซิร์ฟเวอร์</strong>? This action cannot be undone." (ยืนยันลบเซิร์ฟเวอร์ MCP)
  // แปลทีละชิ้นเฉพาะในคำอธิบายของ alert dialog (ชิ้นเหล่านี้ไม่ใช่ประโยคที่ควรแปลที่อื่น) ชื่อใน <strong> ไม่แตะ
  // → "ลบ ชื่อ? กู้คืนไม่ได้" แบบเดียวกับ window.confirm ลบแชต — ช่องว่างหัวท้ายของ text node คงเดิม (txText)
  var FRAG_SCOPE = '[data-slot="alert-dialog-description"]';
  var FRAG_TH = {
    "Are you sure you want to delete": "ลบ",
    "? This action cannot be undone.": "? " + NO_UNDO_TH
  };

  // ข้อความประกาศเปลี่ยนหน้าของ SvelteKit (#svelte-announcer, aria-live) คือ document.title ของ WebUI:
  // "llama-ui" (หน้าเริ่ม), "<ชื่อแชต> - llama-ui", "Chat - llama-ui" (แชตยังไม่มีชื่อ), "Search · llama.cpp",
  // "Error 404 - llama-ui" — ผู้ใช้โปรแกรมอ่านจอได้ยินทุกครั้งที่เปลี่ยนแชต แปลเฉพาะคำของ WebUI และใช้ชื่อผลิตภัณฑ์
  // ที่เห็นบนจอ (Qwen3.8) แทนชื่อแอปของ WebUI ที่ถูกซ่อนไว้ ชื่อแชตคงเดิม (ไม่ใส่ word joiner — เป็นข้อความสำหรับเสียงอ่าน)
  var APP_NAME = "Qwen3.8";
  function thTitle(t) {
    if (t === "llama-ui" || t === "untitled page") return APP_NAME;
    if (t === "Search · llama.cpp") return "ค้นหาแชต · " + APP_NAME;
    var m = /^([\s\S]*) - llama-ui$/.exec(t);
    if (!m) return null;
    var name = m[1], e = /^Error (\d*)$/.exec(name);
    if (name === "Chat") name = "แชต";
    else if (e) name = ("ข้อผิดพลาด " + e[1]).trim();
    return name + " - " + APP_NAME;
  }

  /* ---- ไอคอน (วาดเอง ไม่ได้ลอกโลโก้ของใคร) ----------------------------------- */
  // เครื่องหมายเดียวกับแถบข้างของ shell (.mark): สี่เหลี่ยมมุมมนสีส้ม + ตัว Q serif สีขาว
  // สัดส่วนย่อ/ขยายจากของ shell (28px, มุม 8, ตัวอักษร 17px) ให้แบรนด์ดูเป็นชุดเดียวกัน
  var MARK_SVG =
    '<svg viewBox="0 0 32 32" width="32" height="32" focusable="false" aria-hidden="true" style="user-select:none">' +
    '<rect width="32" height="32" rx="9.1" style="fill:var(--qw-accent,#d97757)"/>' +
    '<text x="16" y="22.4" text-anchor="middle" style="fill:var(--qw-accent-fg,#fff);' +
    'font-family:var(--qw-font-serif,Georgia,serif);font-weight:600;font-size:19.4px">Q</text>' +
    '</svg>';
  var ICON = {
    write: '<path d="M4 20h4L18.5 9.5a2.12 2.12 0 0 0-3-3L5 17v3Z"/><path d="m13.5 8.5 3 3"/>',
    learn: '<path d="M2.5 9.5 12 5l9.5 4.5L12 14 2.5 9.5Z"/><path d="M6.5 11.8V16c0 1.4 2.5 3 5.5 3s5.5-1.6 5.5-3v-4.2"/><path d="M21.5 9.5v5"/>',
    code: '<path d="m8.5 7.5-4.5 4.5 4.5 4.5"/><path d="m15.5 7.5 4.5 4.5-4.5 4.5"/><path d="m13.5 5.5-3 13"/>',
    files: '<path d="M3.5 7.5a2 2 0 0 1 2-2h3.6l2 2h7.4a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2Z"/>',
    web: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.3 2.4 3.5 5.2 3.5 8.5s-1.2 6.1-3.5 8.5c-2.3-2.4-3.5-5.2-3.5-8.5s1.2-6.1 3.5-8.5Z"/>',
    office: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M3.5 9.5h17"/><path d="M3.5 14.5h17"/><path d="M9.5 9.5v10"/>'
  };
  function chipIcon(name) {
    return '<svg class="qw-chip-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" ' +
      'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ' +
      'aria-hidden="true" focusable="false">' + (ICON[name] || "") + "</svg>";
  }

  /* ---- ตัวช่วย -------------------------------------------------------------- */
  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* โหมดส่วนตัว */ } }
  function setAttr(name, value) {
    if (value == null) { if (root.hasAttribute(name)) root.removeAttribute(name); }
    else if (root.getAttribute(name) !== value) root.setAttribute(name, value);
  }
  // เข้าถึง parent ได้เฉพาะตอนอยู่ใน shell origin เดียวกัน ที่อื่นจะโยน SecurityError
  function shell() {
    try { if (window.parent !== window && window.parent.qwenShell) return window.parent.qwenShell; }
    catch (e) {}
    return null;
  }
  function shellApi() {
    try { if (window.parent !== window) return window.parent.qwenShellApi || null; }
    catch (e) {}
    return null;
  }
  function callShell(fn, arg) {
    var api = shellApi();
    if (!api || typeof api[fn] !== "function") return false;
    try { api[fn](arg); } catch (e) { /* shell พังต้องไม่ลากหน้าแชตพังตาม */ }
    return true;
  }
  // ภาษาที่ใช้: ค่าที่ setLang() ตั้งไว้ (สลับสดโดยไม่โหลดหน้า) มาก่อน แล้วจึงเป็นของ shell / <html lang>
  var langOverride = null;
  function lang() {
    if (langOverride) return langOverride;
    var s = shell(), l = s && s.lang;
    if (l !== "th" && l !== "en") l = (root.getAttribute("lang") || "").slice(0, 2).toLowerCase();
    return l === "th" ? "th" : "en";
  }
  function S() { return STR[lang()]; }

  /* ---- ธีม ------------------------------------------------------------------ */
  // ต้นทางของธีมคือ class "dark" ที่ mode-watcher ของ WebUI คุม เราแค่สะท้อนเป็น data-theme
  // (mode-watcher เองก็เขียน data-theme="" ทับตอน mount จึงต้องคอยตั้งกลับ)
  function validPref(p) { return p === "dark" || p === "light" || p === "system"; }
  function readPref() {
    var t = lsGet(KEY_THEME);
    if (validPref(t)) return t;
    var m = lsGet(KEY_MW);
    return validPref(m) ? m : "dark";
  }
  function mirrorTheme() {
    setAttr("data-theme", root.classList.contains("dark") ? "dark" : "light");
  }
  function applyPref(pref) {
    if (!validPref(pref)) return;
    var dark = resolvedDark(pref);
    root.classList.toggle("dark", dark);
    setAttr("data-theme", dark ? "dark" : "light");
    root.style.colorScheme = dark ? "dark" : "light";
    // ให้ mode-watcher รู้ค่าใหม่ด้วย ไม่งั้นมันจะวาด class เดิมกลับเมื่อมีอะไรมากระตุ้น
    // การเขียน localStorage ในเอกสารเดียวกันไม่เกิด storage event จึงยิง event จำลองให้เอง
    if (lsGet(KEY_MW) !== pref) {
      var old = lsGet(KEY_MW);
      lsSet(KEY_MW, pref);
      try {
        window.dispatchEvent(new StorageEvent("storage",
          { key: KEY_MW, oldValue: old, newValue: pref, storageArea: localStorage }));
      } catch (e) {}
    }
  }
  function applyTheme(pref) { applyPref(validPref(pref) ? pref : readPref()); }

  // ---- ให้ธีมของ shell กับ WebUI ไม่แย่งกัน (เฉพาะตอนอยู่ใน shell) ----
  // WebUI ตั้งธีมจาก LlamaUi.config.theme ทุกครั้งที่โหลด (settings store เรียก setMode หลัง
  // migration ของ IndexedDB ราว 1-2 วินาที) ทับ mode-watcher-mode ที่ boot.js ตั้งไว้
  // ถ้าค่านั้นค้างเป็นค่าเก่า หน้าแชตจะมืดขณะที่แถบข้างสว่าง จึงต้องแก้ config ก่อน WebUI อ่าน
  var CFG_KEY = "LlamaUi.config";
  function cfgTheme() {
    try { var c = JSON.parse(lsGet(CFG_KEY) || "null"); return c && c.theme; } catch (e) { return null; }
  }
  function syncCfgTheme(pref) {
    try {
      var c = JSON.parse(lsGet(CFG_KEY) || "null");
      // ไม่สร้าง config เอง — ไม่มีคีย์นี้ WebUI จะถือเป็นการเปิดครั้งแรกแล้วใช้ค่าจากเซิร์ฟเวอร์
      if (!c || typeof c !== "object" || c.theme === pref) return;
      c.theme = pref;
      lsSet(CFG_KEY, JSON.stringify(c));
    } catch (e) {}
  }
  function parentBoot() {
    try { return window.parent !== window ? window.parent.qwenBoot || null : null; } catch (e) { return null; }
  }
  // ธีมที่ shell ใช้อยู่จริง (เฉพาะตอนอยู่ใน shell)
  // ผู้ใช้ส่วนใหญ่ไม่เคยกดปุ่มธีมของเรา (qwen-theme ว่าง) จึงต้องมีค่าถอยเสมอ ไม่งั้นธีมสองฝั่งแยกกัน
  // ห้ามเชื่อ boot.getTheme() อย่างเดียว: ตอน qwen-theme ว่างมันอ่าน mode-watcher-mode
  // ซึ่งหน้าตั้งค่าของ WebUI เขียนทับตอนพรีวิว จึงรับค่านั้นเฉพาะเมื่อตรงกับสีที่ shell แสดงอยู่
  function shellPref() {
    if (!shell()) return null;
    var t = lsGet(KEY_THEME);
    if (validPref(t)) return t;
    var shown = null, boot = parentBoot(), g = null;
    try { shown = window.parent.document.documentElement.getAttribute("data-theme"); } catch (e) {}
    try { g = boot && boot.getTheme ? boot.getTheme() : null; } catch (e) {}
    if (validPref(g) && (shown !== "dark" && shown !== "light" || (resolvedDark(g) ? "dark" : "light") === shown)) return g;
    return shown === "light" ? "light" : "dark";
  }
  function resolvedDark(pref) {
    return pref === "dark" ||
      (pref === "system" && !!(window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches));
  }
  // หน้าตั้งค่าของ WebUI พรีวิวธีมทันทีที่เลือก — ระหว่างเปิดอยู่ (และจนกว่า pass() จะเก็บงานตอนปิด) ห้ามแย่ง
  function dialogOpen() {
    return !!document.querySelector('[role="dialog"]:not([data-state="closed"]),' +
      '[role="alertdialog"]:not([data-state="closed"])');
  }
  // นอกหน้าตั้งค่า ค่าที่ผู้ใช้เลือกใน shell เป็นตัวตัดสิน
  function reconcileTheme() {
    var want = shellPref();
    if (!want || hadDialog || dialogOpen()) return;
    if (lsGet(KEY_MW) !== want || root.classList.contains("dark") !== resolvedDark(want)) applyPref(want);
  }

  // สถานะของหน้าต่างที่เปิดอยู่ — WebUI อ่าน config แค่ตอนโหลด ตอนกด Save มันเขียนค่าในหน่วยความจำ
  // ทั้งก้อนกลับลง localStorage (ธีมเก่าที่ค้างอยู่ด้วย) จึงยอมรับธีมจาก WebUI เฉพาะเมื่อผู้ใช้เลือกเองจริง
  var hadDialog = false, themeTouched = false, dlgWant = null, dlgCfgRaw = null;
  var dlgThemeSynced = false, quietPick = false;
  function onDialogOpen() {
    themeTouched = false;
    dlgThemeSynced = false;
    dlgCfgRaw = lsGet(CFG_KEY);
    dlgWant = uiPref();
  }
  // ธีมที่ใช้อยู่จริง: ใน shell = ค่าของ shell (qwen-theme เดียวกับ qwenBoot.getTheme()), เปิดเดี่ยว = mode-watcher
  function uiPref() {
    var p = shellPref();
    if (p) return p;
    var m = lsGet(KEY_MW);
    return validPref(m) ? m : null;
  }
  // ตัวเลือกธีมของ WebUI มีค่า system/light/dark — ใช้เป็นสัญญาณว่าผู้ใช้แตะธีมเอง
  // ไม่นับปุ่ม "Reset to default" (ตั้ง theme=system ให้เอง) และไม่นับตอนที่เราเลือกแทนใน syncDialogTheme
  function noteThemePick(e) {
    if (quietPick) return;
    if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
    var t = e.target, it = t && t.closest ? t.closest('[data-slot="select-item"]') : null;
    // คีย์บอร์ด: bits-ui ให้โฟกัสค้างที่ปุ่ม select แล้ว Enter เลือกตัวที่ไฮไลต์อยู่ (event ไม่ได้เกิดที่ item)
    if (!it && e.type === "keydown" && t && t.closest && t.closest('[data-slot="select-trigger"]')) {
      it = document.querySelector('[data-slot="select-content"] [data-slot="select-item"][data-highlighted]');
    }
    var v = it && it.getAttribute("data-value");
    if (!validPref(v)) return;
    themeTouched = true;
    // ใน shell ส่งทันทีที่เลือก ไม่รอ Save: WebUI พรีวิวธีมเฉพาะใน iframe ถ้ารอ แถบข้างของ shell
    // จะค้างอีกสีหนึ่งระหว่างที่หน้าต่างยังเปิดอยู่ (หน้าจอผ่าครึ่ง) — รอให้ตัวจัดการของ WebUI ทำงานก่อน
    if (shell()) setTimeout(function () { persistTheme(v); }, 0);
  }
  // บันทึกธีมระดับทั้งเครื่อง: qwenBoot.setTheme PATCH ไปที่ hub ให้ทุกโปรเจกต์ (คนละพอร์ต) ตรงกัน
  // และเปลี่ยน shell ทั้งหน้า — pointerup + click ของการเลือกครั้งเดียวจะเรียกซ้ำ จึงข้ามถ้าค่าเท่าเดิม
  function persistTheme(v) {
    if (!validPref(v) || shellPref() === v) return;
    var boot = parentBoot();
    if (boot && typeof boot.setTheme === "function") {
      try { boot.setTheme(v); } catch (e) {}
    } else {
      lsSet(KEY_THEME, v);
    }
    applyPref(v);
  }

  // หน้าต่างตั้งค่าคัดลอก config ของ settings store มาเป็นฟอร์มตอนเปิด แต่ store อ่าน localStorage
  // ครั้งเดียวตอนโหลด ธีมที่เปลี่ยนจาก shell ทีหลังจึงไม่ถึง store — จอสว่างแต่ช่องธีมขึ้น "Dark"
  // และกด Save จะเขียนค่าเก่านั้นกลับ store เข้าถึงจากภายนอกไม่ได้ ทางเดียวที่แก้สถานะของฟอร์มคือ
  // เลือกตัวเลือกให้เองผ่าน select ของมัน (onValueChange → ฟอร์ม, Save → store) ทำครั้งเดียวต่อการเปิด
  function themeTrigger() {
    var lb = document.querySelector('[role="dialog"] label[for="theme"]');
    for (var n = lb && lb.parentElement, i = 0; n && i < 4; n = n.parentElement, i++) {
      var t = n.querySelector('[data-slot="select-trigger"]');
      if (t) return t;
    }
    return null;
  }
  // ป้ายบนปุ่มคือ System/Light/Dark ตรงกับค่า — ถ้ารุ่นหน้าเปลี่ยนป้าย ใช้ไอคอนแทน
  var THEME_ICON = { "lucide-monitor": "system", "lucide-sun": "light", "lucide-moon": "dark" };
  function shownTheme(t) {
    var v = enText(t).trim().toLowerCase();              // ป้ายถูกแปลเป็นไทยได้ อ่านต้นฉบับอังกฤษ
    if (validPref(v)) return v;
    for (var k in THEME_ICON) if (t.querySelector("svg." + k)) return THEME_ICON[k];
    return null;
  }
  function mousePointer(type) {
    return new PointerEvent(type, { bubbles: true, cancelable: true, button: 0,
      buttons: type === "pointerdown" ? 1 : 0, pointerType: "mouse", pointerId: 1, isPrimary: true });
  }
  function selectOpen() { return !!document.querySelector('[data-slot="select-content"][data-state="open"]'); }
  // รายการที่เด้งขึ้นระหว่างเลือกแทนต้องไม่ให้เห็น — ซ่อนด้วยกฎชั่วคราวที่ผูกกับ attribute บน <html>
  // (ใส่ style ทีหลังตอน element โผล่มาไม่ทัน มันถูกวาดไปแล้วหนึ่งเฟรม)
  function quietStyle() {
    if (document.getElementById("qw-quiet-select")) return;
    var st = document.createElement("style");
    st.id = "qw-quiet-select";
    st.textContent = 'html[data-qw-quiet-select] [data-slot="select-content"]' +
      "{opacity:0!important;pointer-events:none!important;animation:none!important}";
    (document.head || root).appendChild(st);
  }
  function syncDialogTheme() {
    if (dlgThemeSynced || quietPick) return;
    var t = themeTrigger();
    if (!t) return;                    // หน้าต่างอื่น (MCP, ยืนยันลบ) หรือยังไม่ได้อยู่หมวดที่มีช่องธีม
    dlgThemeSynced = true;
    var want = dlgWant || uiPref(), shown = shownTheme(t);
    if (!want || !shown || shown === want) return;
    var prev = document.activeElement;
    quietPick = true;
    quietStyle();
    setAttr("data-qw-quiet-select", "1");
    t.dispatchEvent(mousePointer("pointerdown"));      // bits-ui เปิด select ด้วย pointerdown (เมาส์)
    waitFor(function () {
      return document.querySelector('[data-slot="select-content"] [data-slot="select-item"][data-value="' + want + '"]');
    }, 1000).then(function (it) {
      if (it) {
        it.dispatchEvent(mousePointer("pointerup"));    // item เลือกค่าตอน pointerup
        if (selectOpen()) it.click();
      }
      return waitFor(function () { return !selectOpen(); }, 600);
    }).then(function (closed) {
      if (!closed) {
        var c = document.querySelector('[data-slot="select-content"]');
        if (c) c.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
      }
      // ให้โฟกัสอยู่ที่เดิมที่หน้าต่างตั้งไว้ ไม่ใช่ย้ายมาที่ช่องธีม
      if (prev && prev !== document.activeElement && prev.isConnected && dialogOpen()) {
        try { prev.focus({ preventScroll: true }); } catch (e) {}
      }
    }).then(function () {
      // ปลดหลังแอนิเมชันปิดของรายการ (~150ms) — ปลดทันทีจะเห็นมันจางหายแวบหนึ่ง
      setTimeout(function () { setAttr("data-qw-quiet-select", null); quietPick = false; }, 200);
    });
  }

  function afterDialog() {
    var saved = cfgTheme(), raw = lsGet(CFG_KEY), want = shellPref();
    if (!want) return;
    // ทางสำรองของ noteThemePick: ผู้ใช้แตะธีมแล้วกด Save แต่ค่ายังไม่ถึง shell
    // ต้องมีการ Save จริง (config เปลี่ยน) — theme ใน localStorage ตอนไม่ได้ Save อาจเป็นค่าเก่าค้าง
    if (themeTouched && raw !== dlgCfgRaw && validPref(saved) && saved !== want) {
      persistTheme(saved);
    } else {
      // ไม่ได้แตะธีม (หรือกดยกเลิกหลังพรีวิว): คืนค่าของ shell ทั้งใน config และบนจอ
      syncCfgTheme(want);
      applyPref(want);
    }
    // WebUI บันทึก config ทั้งก้อน อาจทับ systemMessage ที่ shell เพิ่งเขียนแต่ยังรอรีโหลดอยู่
    if (raw !== dlgCfgRaw) callShell("afterWebuiSave");
    themeTouched = false;
  }

  /* ---- ฟอนต์ของคำตอบ -------------------------------------------------------- */
  function readFont() { return lsGet(KEY_FONT) === "sans" ? "sans" : "serif"; }
  function applyFont(f) { setAttr("data-qw-font", f === "sans" ? "sans" : "serif"); }
  function setFont(mode) {
    if (mode !== "serif" && mode !== "sans") return false;
    if (lsGet(KEY_FONT) !== mode) lsSet(KEY_FONT, mode);
    applyFont(mode);
    return true;
  }

  /* ---- เส้นทาง (hash router ของ SvelteKit) ----------------------------------- */
  function route() {
    var path = (location.hash || "").replace(/^#/, "").split("?")[0];
    if (path === "" || path === "/") return { name: "start", id: null };
    var m = /^\/chat\/([^/]+)/.exec(path);
    if (m) {
      var id = m[1];
      try { id = decodeURIComponent(id); } catch (e) {}
      return { name: "chat", id: id };
    }
    return { name: "other", id: null };
  }
  function routeKey() { var r = route(); return r.name + ":" + (r.id || ""); }
  var lastRouteKey = null, routeDelivered = false, routeAt = 0;
  // WebUI เปลี่ยนหน้าด้วย pushState ซึ่งไม่ยิง hashchange จึงเช็กซ้ำทุกรอบที่ DOM เปลี่ยนด้วย
  function checkRoute() {
    var r = route(), key = r.name + ":" + (r.id || "");
    setAttr("data-qw-route", r.name);
    if (key !== lastRouteKey || !routeDelivered) {
      if (key !== lastRouteKey) { routeAt = Date.now(); if (r.name === "chat") startPin(r.id); else stopPin(); }
      lastRouteKey = key;
      // ส่งซ้ำจนกว่า shell จะมี API พร้อมรับ (shell อาจยังโหลดไม่เสร็จตอน iframe เริ่ม)
      routeDelivered = callShell("onRoute", { name: r.name, id: r.id });
    }
    return r;
  }

  /* ---- กล่องพิมพ์ ----------------------------------------------------------- */
  // เลือกเฉพาะฟอร์มหลักใน .chat-screen-form-wrapper — ช่องแก้ไขข้อความเก่าก็เป็น textarea เหมือนกัน
  function composerForm() {
    return document.querySelector(".chat-screen-form-wrapper form.conversation-chat-form");
  }
  function composer() {
    var f = composerForm();
    return f ? f.querySelector("textarea") : null;
  }
  function focusComposer() {
    var ta = composer();
    if (!ta) return false;
    allowFocus++;                     // คำสั่งตรงจาก shell/ชิป ไม่ใช่ autofocus — ผ่านตัวกันเสมอ
    try { ta.focus(); } finally { allowFocus--; }
    var n = ta.value.length;
    try { ta.setSelectionRange(n, n); } catch (e) {}
    return true;
  }

  /* ---- กัน autofocus ของ WebUI แย่งโฟกัสจาก shell ตอน iframe โหลดใหม่ ------------- */
  // shell รีโหลด iframe หลังบันทึกคำสั่ง/เปลี่ยนชื่อ/ลบแชต ราว 1-1.5 วินาทีต่อมา WebUI เรียก
  // textarea.focus() เอง (Svelte autofocus + ตอนนำทาง) โฟกัสจึงหลุดจากแผงโปรเจกต์หรือช่องสร้าง
  // โปรเจกต์ไปอยู่ในกล่องพิมพ์ที่อยู่ข้างหลัง — Enter ตอนนั้นจะส่งข้อความจริง
  // และ SvelteKit เองก็ "รีเซ็ตโฟกัส" หลังนำทางครั้งแรกด้วย document.body.focus() ซึ่งดึงโฟกัส
  // ของหน้าบนสุดเข้ามาใน iframe เหมือนกัน (พิมพ์ต่อแล้วตัวอักษรหายไปเฉยๆ)
  // ต้องกันที่ตัวเรียก focus() (ไม่ใช่ blur ทีหลัง) เพราะการ blur ใน shell ก็ปิดช่องสร้างโปรเจกต์ไปแล้ว
  // ครอบเฉพาะ textarea กับ body ช่วงสั้นๆ หลังโหลด และปลดทันทีที่ผู้ใช้แตะหน้าแชตหรือเปลี่ยนหน้า
  var GUARD_MS = 8000, bootAt = Date.now(), allowFocus = 0, userActed = false;
  var bootRoute = null, guardOn = false;
  var nativeFocus = HTMLElement.prototype.focus;
  function frameEl() { try { return window.frameElement; } catch (e) { return null; } }
  function shownModal(el) {
    if (!el || el.closest("[hidden]")) return false;
    var cs = el.ownerDocument.defaultView.getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") return false;
    var r = el.getBoundingClientRect(), w = el.ownerDocument.defaultView.innerWidth;
    return r.width > 0 && r.height > 0 && r.right > 0 && r.left < w;
  }
  // ผู้ใช้กำลังทำงานใน shell: มีช่อง/ปุ่มของ shell ถือโฟกัสอยู่ หรือมีหน้าต่างของ shell เปิดค้าง
  // (กดปุ่มบันทึกด้วยเมาส์แล้วปุ่มถูก disable โฟกัสจะตกไปที่ body ทั้งที่แผงยังเปิด)
  function shellBusy() {
    try {
      var d = window.parent.document, a = d.activeElement, f = frameEl();
      if (a && a !== d.body && a !== d.documentElement && a !== f) return true;
      var ms = d.querySelectorAll('[aria-modal="true"]');
      for (var i = 0; i < ms.length; i++) if (shownModal(ms[i])) return true;
    } catch (e) {}
    return false;
  }
  function guardedFocus(opts) {
    if (guardOn && !allowFocus && !userActed && Date.now() - bootAt < GUARD_MS &&
        (this === document.body || (this.closest && this.closest(".chat-screen-form-wrapper"))) &&
        routeKey() === bootRoute && shell() && shellBusy()) return;
    return nativeFocus.call(this, opts);
  }
  var GUARDED = [window.HTMLTextAreaElement, window.HTMLBodyElement];
  function releaseFocusGuard() {
    if (!guardOn) return;
    guardOn = false;
    GUARDED.forEach(function (C) {
      try { if (C && C.prototype.focus === guardedFocus) delete C.prototype.focus; } catch (e) {}
    });
  }
  function installFocusGuard() {
    if (!shell() || !nativeFocus) return;
    bootRoute = routeKey();
    try {
      GUARDED.forEach(function (C) {
        if (C) Object.defineProperty(C.prototype, "focus", { value: guardedFocus, configurable: true, writable: true });
      });
      guardOn = true;
    } catch (e) { guardOn = true; releaseFocusGuard(); return; }
    setTimeout(releaseFocusGuard, GUARD_MS);
    var acted = function () { userActed = true; releaseFocusGuard(); };
    ["pointerdown", "keydown", "touchstart"].forEach(function (t) {
      window.addEventListener(t, acted, { capture: true, once: true });
    });
  }
  installFocusGuard();              // ต้องติดตั้งก่อน WebUI mount (สคริปต์นี้ defer แต่ bundle โหลดทีหลัง)
  // Svelte ผูกค่าผ่าน event "input" — ตั้ง .value เฉยๆ ปุ่มส่งจะยังถูกปิดอยู่
  // ใช้ setter ของ prototype เผื่อ framework ห่อ property ของ element ไว้
  function prefill(text) {
    var ta = composer();
    if (!ta) return false;
    var v = text == null ? "" : String(text);
    var desc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (desc && desc.set) desc.set.call(ta, v); else ta.value = v;
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    return focusComposer();
  }

  /* ---- ชื่อที่ตั้งให้แชตที่แยกออกมา (หน้าต่าง "แยกเป็นแชตใหม่") ------------------------------------------ */
  // WebUI เติมช่องชื่อเป็น "Fork of <ชื่อแชต>" ทุกครั้งที่เปิดหน้าต่าง ผู้ใช้ไทยกดยืนยันเลยจะได้แชตที่ชื่อขึ้นต้นด้วย
  // ภาษาอังกฤษค้างในรายการแชตและหัวหน้าจอ — โหมดไทยเปลี่ยนคำนำหน้าเป็น "แยกจาก " ครั้งเดียวต่อการเปิด (ช่องถูกสร้างใหม่
  // ทุกครั้ง) เขียนผ่าน setter ของ prototype + event input ให้ bind:value ของ Svelte รับค่า แบบเดียวกับ prefill()
  // ค่าที่ไม่ขึ้นต้นด้วย "Fork of " (ผู้ใช้แก้แล้ว) ไม่แตะ และจำค่าเดิมไว้คืนเมื่อ setLang("en")
  var FORK_EN = "Fork of ";
  var forkSeen = new WeakSet(), forkMine = new WeakMap();   // ช่องชื่อ → [ค่าของ WebUI, ค่าที่เราเขียน]
  function setInputValue(inp, v) {
    var all = document.activeElement === inp && inp.selectionStart === 0 && inp.selectionEnd === inp.value.length;
    var desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
    if (desc && desc.set) desc.set.call(inp, v); else inp.value = v;
    inp.dispatchEvent(new Event("input", { bubbles: true }));
    if (all) try { inp.select(); } catch (e) {}              // เลือกไว้ทั้งช่องอยู่แล้ว (พิมพ์ทับได้) ให้คงเดิม
  }
  function syncForkName(l) {
    var inp = document.getElementById("fork-name");
    if (!inp || inp.tagName !== "INPUT" || forkSeen.has(inp)) return;
    var v = inp.value;
    if (!v) return;                                         // Svelte ยังไม่ผูกค่า — รอบหน้าค่อยดู
    forkSeen.add(inp);
    if (l !== "th" || v.indexOf(FORK_EN) !== 0) return;
    var rest = v.slice(FORK_EN.length);
    var out = "แยกจาก " + (rest === "Conversation" ? "แชต" : rest);   // "Conversation" = แชตไม่มีชื่อ (ค่าของ WebUI)
    forkMine.set(inp, [v, out]);
    setInputValue(inp, out);
  }
  function restoreForkName() {
    var inp = document.getElementById("fork-name"), r = inp && forkMine.get(inp);
    if (r && inp.value === r[1]) setInputValue(inp, r[0]);
  }
  // ปุ่ม Stop ของ WebUI มีแค่ข้อความ sr-only "Stop" (ไม่มี aria-label) และจะกลายเป็นปุ่มส่ง
  // ถ้าผู้ใช้พิมพ์ระหว่างรอ จึงดู .stop-button ในแถบแท็บ/รายการแชตประกอบด้วย
  // โหมดไทยแปล sr-only และ title เป็นไทย จึงอ่านต้นฉบับอังกฤษ (enText / data-qw-en-title)
  function isStreaming() {
    var f = composerForm();
    if (f) {
      var btns = f.querySelectorAll("button");
      for (var i = 0; i < btns.length; i++) {
        var b = btns[i], sr = b.querySelector(".sr-only");
        var label = (b.getAttribute("aria-label") || "") + " " + (enAttr(b, "title") || "") +
          " " + (sr ? enText(sr) : "");
        if (/\bstop\b|skip reasoning/i.test(label)) return true;
      }
    }
    return !!document.querySelector('.stop-button, [aria-label="Stop generation"]');
  }

  /* ---- เปิดแชตแล้วต้องจบที่ข้อความล่าสุด ------------------------------------------- */
  // WebUI เลื่อนลงก้นตอนข้อความพร้อม (onMessagesReady) แล้ววน rAF ซ้ำอีก ≤1 วินาที แต่เลิกทันทีที่ scroll event
  // มี scrollTop ลดลงและห่างก้นเกิน 10px (ถือว่าผู้ใช้เลื่อนขึ้นเอง) — แชตแรกหลังโหลดหน้า markdown/ไฮไลต์โค้ด
  // วาดใหม่ในงานก้อนยาว ความสูงยุบชั่วขณะ เบราว์เซอร์บีบ scrollTop เหลือ 0 (ธีมปลด min-height ของคำตอบสุดท้าย
  // จึงไม่มีอะไรค้ำความสูงไว้) WebUI เข้าใจว่าผู้ใช้เลื่อน → ค้างบนสุด
  // จึงตรึงก้นเองหลังเปิดแชตทุกครั้งที่ความสูงเปลี่ยน (ResizeObserver บน body) หรือถูกบีบ (scroll ของเอกสาร)
  // จนเลย์เอาต์นิ่ง — เลิกทันทีเมื่อผู้ใช้แตะ/เลื่อน/กดแป้นเอง หรือเริ่มสตรีม (ตอนนั้น WebUI คุมเอง)
  // ช่วงเวลานับจากที่ข้อความโผล่ ไม่ใช่จากเปลี่ยนเส้นทาง: F5 บนหน้าแชต ข้อความมาหลังสคริปต์นี้ 1-3 วินาที
  var PIN_ARM_MS = 15000, PIN_MS = 1500, PIN_QUIET_MS = 600, PIN_MAX_MS = 5000;
  // เธรดหลักค้างนานกว่านี้ถือว่าเป็น stall ไม่ใช่เวลาที่เลย์เอาต์นิ่ง, และเพดานสัมบูรณ์กันตรึงไม่รู้จบ
  // (แท็บพื้นหลังโดนหน่วง timer เป็น 1 วินาที ทุกติ๊กจะดูเหมือน stall)
  var PIN_STALL_MS = 400, PIN_ABS_MS = 30000;
  // pointerdown ครอบการลากแถบเลื่อนด้วย (Chromium ส่งให้ <html>)
  var PIN_INPUT = ["wheel", "touchstart", "pointerdown", "keydown"];
  var pin = null;
  function startPin(id) {
    stopPin();
    if (!window.ResizeObserver) return;
    var p = pin = { id: id, t0: Date.now(), shown: 0, moved: 0 };
    p.ro = new ResizeObserver(function () { pinTick(true, false); });
    p.ro.observe(document.body || root, { box: "border-box" });
    p.iv = setInterval(function () { pinTick(false, true); }, 250);   // ให้หมดเวลาได้แม้ไม่มี event มาเลย
    PIN_INPUT.forEach(function (t) { window.addEventListener(t, onPinInput, { capture: true, passive: true }); });
    window.addEventListener("scroll", onPinScroll, { capture: true, passive: true });
  }
  function stopPin() {
    var p = pin;
    if (!p) return;
    pin = null;
    p.ro.disconnect();
    clearInterval(p.iv);
    PIN_INPUT.forEach(function (t) { window.removeEventListener(t, onPinInput, { capture: true }); });
    window.removeEventListener("scroll", onPinScroll, { capture: true });
  }
  // event ที่สคริปต์จำลอง (เช่น pointerdown ที่เราส่งเปิดเมนูของ bits-ui) ไม่ใช่ผู้ใช้ — ไม่นับ
  function onPinInput(e) { if (e.isTrusted) stopPin(); }
  function onPinScroll(e) { if (e.target === document) pinTick(false, false); }
  function pinTick(resized, timer) {
    var p = pin;
    if (!p) return;
    var now = Date.now(), r = route();
    if (r.name !== "chat" || r.id !== p.id || isStreaming()) { stopPin(); return; }
    if (!document.querySelector(".chat-messages .chat-message")) {
      if (now - p.t0 > PIN_ARM_MS) stopPin();       // แชตไม่มีจริง/ถูกลบไปแล้ว
      return;
    }
    if (now - p.t0 > PIN_ABS_MS) { stopPin(); return; }
    if (!p.shown) p.shown = p.moved = now;
    // เธรดหลักเพิ่งหลุดจากงานก้อนยาว (เรนเดอร์ markdown/ไฮไลต์โค้ดตอน CPU ถูกแย่ง วัดได้ ~2.7 วินาที)
    // ช่วงที่ค้างไม่ใช่ช่วงที่เลย์เอาต์ "นิ่ง" — เลื่อนนาฬิกาออกไปเท่าที่ค้าง ไม่งั้นติ๊กแรกหลังหลุดบล็อก
    // จะเห็นว่าหมดเวลาแล้วเลิกตรึง ทั้งที่หน้าเพิ่งยุบจน scrollTop เหลือ 0 (พบ 3 ใน ~110 ครั้งตอนเครื่องโหลดหนัก)
    if (p.last && now - p.last > PIN_STALL_MS) { p.shown += now - p.last; p.moved = now; }
    p.last = now;
    if (resized) p.moved = now;
    var se = document.scrollingElement || root;
    // resize/ถูกบีบ scroll คือจังหวะที่ต้องแก้พอดี จึงดึงลงก้นก่อนตัดสินหมดเวลา
    // ส่วนติ๊กของตัวจับเวลาไม่เลื่อนเอง — เผื่อผู้ใช้เลื่อนด้วยทางที่ไม่มี event ให้จับ
    if (!timer && se.scrollHeight - se.clientHeight - se.scrollTop > 1) se.scrollTop = se.scrollHeight;
    if (now - p.shown > PIN_MAX_MS || (now - p.shown > PIN_MS && now - p.moved > PIN_QUIET_MS)) stopPin();
  }

  /* ---- การนำทาง ------------------------------------------------------------- */
  // ห้ามตั้ง location.hash ตรงๆ: router แบบ hash ของ SvelteKit เจอ popstate ที่ตัวเองไม่ได้ก่อ
  // จะสั่ง location.reload() ทั้งหน้า (คำตอบที่กำลังสตรีมหายไปด้วย)
  // จึงสร้างลิงก์ชั่วคราวในกล่องของแอปแล้วคลิก ให้ตัวดักคลิกลิงก์ของ SvelteKit นำทางแบบไม่โหลดใหม่
  function appRoot() {
    var n = document.querySelector("div[role=main], aside");
    while (n && n.parentElement && n.parentElement !== document.body) n = n.parentElement;
    return n && n.parentElement === document.body ? n : null;
  }
  function go(hash) {
    var host = appRoot();
    if (!host) { location.hash = hash; return; }
    var a = document.createElement("a");
    a.href = hash;
    a.style.display = "none";
    a.setAttribute("aria-hidden", "true");
    host.appendChild(a);
    try { a.click(); }
    finally { setTimeout(function () { detach(a); }, 0); }
  }
  // จอกว้าง (iframe ≥ 768px) ปุ่มในแถบข้างของ WebUI มี aria-label
  // จอแคบ (มือถือ และหน้าต่างที่แคบกว่า ~1056px) เป็นปุ่มข้อความล้วน เช่น "New chat ⌘ O", "Settings"
  // ซึ่งโหมดไทยถูกแปลแล้ว จึงเทียบกับต้นฉบับอังกฤษ (enText)
  function asideButton(label) {
    var b = document.querySelector('aside button[aria-label="' + label + '"]');
    if (b) return b;
    var all = document.querySelectorAll("aside button");
    for (var i = 0; i < all.length; i++) {
      var t = enText(all[i]).replace(/\s+/g, " ").trim();
      if (t === label || t.indexOf(label + " ") === 0) return all[i];
    }
    return null;
  }
  function visible(el) { return !!(el && el.getClientRects().length); }
  function newChat() {
    // ปุ่มของ WebUI ล้างสถานะแชตที่เปิดอยู่ด้วย ดีกว่าแค่เปลี่ยนเส้นทาง (คลิกได้แม้ถูกซ่อน)
    var b = asideButton("New chat");
    if (b) b.click(); else go("#/");
  }
  function openChat(id) {
    if (id) go("#/chat/" + encodeURIComponent(id));
  }
  function openSearch() {
    // จอกว้าง: WebUI ค้นหาได้เฉพาะในแถบข้างของมันเอง (หน้า /search เด้งกลับ / ทันทีถ้าไม่ใช่มือถือ)
    // แถบนั้นถูกซ่อนเมื่ออยู่ใน shell จึงส่งให้ช่องค้นหาของ shell ทำแทน
    var b = asideButton("Search");
    if (b && visible(b)) { b.click(); return; }
    if (callShell("focusSearch")) return;
    go("#/search");                         // มือถือ: หน้า /search ใช้งานได้จริง
  }
  // คืน Promise<boolean> = หน้าต่างตั้งค่าเปิดขึ้นจริงหรือไม่ (ให้ shell แจ้งผู้ใช้เมื่อไม่สำเร็จ)
  function openSettings() {
    var b = asideButton("Settings");
    if (b) {
      b.click();
      return waitFor(contentDialogOpen, 3000).then(Boolean);
    }
    // สำรอง: บางรุ่นวาดปุ่มเฉพาะตอนกางแถบข้าง — กาง (คลิกได้แม้ถูกซ่อน) กด แล้วหุบคืน
    var exp = document.querySelector('aside button[aria-label="Expand navigation"]');
    if (!exp) return Promise.resolve(false);
    exp.click();
    return waitFor(function () { return asideButton("Settings"); }, 1000).then(function (s) {
      if (s) s.click();
      var col = document.querySelector('aside button[aria-label="Collapse navigation"]');
      if (col) col.click();
      return s ? waitFor(contentDialogOpen, 3000).then(Boolean) : false;
    });
  }
  // รอเงื่อนไขแบบมีเพดานเวลา (ไม่ใช้ setInterval ค้างไว้)
  function waitFor(test, ms) {
    return new Promise(function (resolve) {
      var end = Date.now() + ms;
      (function tick() {
        var v = null;
        try { v = test(); } catch (e) {}
        if (v || Date.now() > end) resolve(v || null); else setTimeout(tick, 50);
      })();
    });
  }
  // WebUI รุ่นนี้ไม่มีหน้า #/mcp-servers (มีแค่ /, /chat/[id], /search) ตั้ง hash ไปก็ได้ "Not found"
  // หน้าต่าง MCP Servers เปิดได้ทางเดียวคือปุ่ม "+" ของกล่องพิมพ์ จึงกดแทนผู้ใช้
  //   จอกว้าง: เมนูของ bits-ui ที่เปิดด้วย pointerdown (click เฉยๆ ไม่เปิด)
  //   จอแคบ: ชีต "Add to chat" ที่เปิดด้วย click และข้างในเป็นปุ่มธรรมดา ไม่ใช่ menuitem
  function plusButton() {
    return document.querySelector(".chat-screen-form-wrapper form button.file-upload-button");
  }
  // ต้องตรงทั้งข้อความ: รายการเครื่องมือในเมนูเดียวกันคือชื่อเซิร์ฟเวอร์ ซึ่งอาจมีคำว่า mcp อยู่ด้วย
  function mcpItem() {
    var items = document.querySelectorAll('[role="menuitem"], [data-slot="sheet-content"] button');
    for (var i = 0; i < items.length; i++) {
      var t = enText(items[i]).replace(/\s+/g, " ").trim();
      if (!items[i].disabled && /^(MCP Servers?|เซิร์ฟเวอร์ MCP)$/i.test(t)) return items[i];
    }
    return null;
  }
  function plusLayerOpen() {
    return !!document.querySelector('[data-slot="dropdown-menu-content"][data-state="open"],' +
      '[data-slot="sheet-content"][data-state="open"]');
  }
  function contentDialogOpen() {
    return !!document.querySelector('[role="dialog"]:not([data-slot="sheet-content"]):not([data-state="closed"])');
  }
  function openMcp() {
    return (plusButton() ? Promise.resolve(plusButton())
      : (go("#/"), waitFor(plusButton, 3000))
    ).then(function (b) {
      if (!b) return openSettings();
      var hit = mcpItem();
      if (!hit) b.dispatchEvent(mousePointer("pointerdown"));
      return (hit ? Promise.resolve(hit) : waitFor(mcpItem, 250)).then(function (item) {
        if (item) return item;
        if (!plusLayerOpen()) b.click();      // จอแคบ: pointerdown ไม่มีผล ต้อง click
        return waitFor(mcpItem, 1500);
      }).then(function (item) {
        if (item) {
          item.click();
          return waitFor(contentDialogOpen, 3000).then(Boolean);
        }
        // หน้าตาเปลี่ยนในรุ่นหน้า: ปิดเมนูที่ค้างแล้วไปหน้าตั้งค่าแทน (มีส่วน MCP อยู่ในนั้น)
        document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        return openSettings();
      });
    });
  }

  /* ---- "System Message" ในเมนู "+" → คำสั่งของโปรเจกต์ใน shell ------------------ */
  // ใน shell การ์ด system message ของ WebUI ถูกซ่อน (คำสั่งของโปรเจกต์คุมที่แผงโปรเจกต์)
  // ถ้าปล่อยให้ WebUI ทำงาน มันสร้างแชตเปล่าชื่อวันที่ภาษาอังกฤษ แล้วเปิดตัวแก้ที่มองไม่เห็น
  // จึงดักตั้งแต่ capture ของ window (ก่อนตัวจัดการแบบ delegate ของ Svelte) แล้วเปิดแผงโปรเจกต์แทน
  function sysMsgItem(t) {
    var it = t && t.closest ?
      t.closest('[data-slot="dropdown-menu-item"], [data-slot="sheet-content"] button') : null;
    return it && it.querySelector("svg.lucide-message-square") ? it : null;
  }
  function canRedirectSysMsg() {
    var api = shellApi();
    return !!(shell() && api && typeof api.openProjectPanel === "function");
  }
  function focusShellInstructions() {
    var api = shellApi();
    if (api && typeof api.focusInstructions === "function") {
      try { api.focusInstructions(); return; } catch (e) {}
    }
    try {
      var ta = window.parent.document.getElementById("ppInstr");
      if (!visible(ta)) return;
      ta.focus();
      var n = ta.value.length;
      ta.setSelectionRange(n, n);
    } catch (e) {}
  }
  var lastSysMsg = 0;
  function interceptSysMsg(e) {
    if (e.type === "keydown" || e.type === "keyup") {
      if (e.key !== "Enter" && e.key !== " ") return;
    }
    var it = sysMsgItem(e.target);
    if (!it || !canRedirectSysMsg()) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (e.type !== "click" && e.type !== "keydown") return;   // กลืน pointerdown/up ทิ้งอย่างเดียว
    if (Date.now() - lastSysMsg < 600) return;               // Enter แล้วตามด้วย click ซ้ำ
    lastSysMsg = Date.now();
    // ปิดเมนู/ชีตผ่าน Escape ของ WebUI เอง (สถานะภายในของมันจะถูกเก็บให้ถูกต้อง)
    try {
      it.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true, cancelable: true }));
    } catch (err) {}
    setTimeout(function () {
      callShell("openProjectPanel");
      // shell โฟกัสปุ่มปิดของแผงหลัง 60ms — รอให้เสร็จก่อนแล้วค่อยย้ายไปช่องคำสั่ง
      setTimeout(focusShellInstructions, 140);
    }, 30);
  }

  /* ---- batch 2a (B5): "ค้นคว้าเชิงลึก" ในเมนู "+" ของกล่องพิมพ์ ------------------------------------------ */
  // เติมคำขอค้นคว้าลงช่องพิมพ์ (ไม่ส่งเอง — ผู้ใช้เติมหัวข้อแล้วส่ง โมเดลเรียก local_do action=research ต่อ)
  // ข้อความที่พิมพ์ค้างอยู่ = หัวข้อ (shell.startResearch ต่อคำนำหน้าให้) — ไม่มี shell (เปิด /?ui=1 ตรงๆ) เติมเองที่นี่
  // รายการถูก "โคลน" จากรายการ System Message ของเมนูเดียวกัน (หน้าตา/ขนาด/แอตทริบิวต์ data-dropdown-menu-item ตรงกัน
  // ลูกศรขึ้นลงของ bits-ui จึงเดินผ่านได้) — ตัวจัดการของ Svelte ไม่ติดมากับโคลน จึงผูก click/Enter/ไฮไลต์เอง
  // ใส่ใน observer ของ body (ไมโครทาสก์เดียวกับที่เมนูโผล่) = ไม่เห็นเมนูกระพริบจาก 4 เป็น 5 รายการ
  // [data-qw-no-tx]: ป้ายตั้งตามภาษาตอนใส่ ตัวแปลไม่ต้องแตะ
  var RES_ICON = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ' +
    'class="h-4 w-4"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m20 20-4.6-4.6"/><path d="M10.5 7.5v6M7.5 10.5h6"/></svg>';
  var PLUS_SCOPES = '[data-slot="dropdown-menu-content"], [data-slot="sheet-content"]';
  function plusMenuTemplate(scope) {
    // รายการ System Message (ไอคอน message-square) มีแค่ในเมนู "+" — ใช้ทั้งเป็นตัวระบุเมนูและแม่แบบ
    var ic = scope.querySelector('[data-slot="dropdown-menu-item"] svg.lucide-message-square, button svg.lucide-message-square');
    return ic ? ic.closest('[data-slot="dropdown-menu-item"], button') : null;
  }
  function researchStart() {
    var api = shellApi();
    if (api && typeof api.startResearch === "function") {
      try { if (api.startResearch() !== false) return; } catch (e) {}
    }
    var ta = composer(), draft = ta ? String(ta.value || "").trim() : "", pre = S().researchPrefill;
    prefill(!draft ? pre : (draft.indexOf(pre.trim()) === 0 ? draft : pre + draft));
  }
  var lastResearch = 0;
  function researchActivate(it, e) {
    if (e) { e.preventDefault(); e.stopImmediatePropagation(); }
    if (Date.now() - lastResearch < 600) return;           // Enter แล้วตามด้วย click ซ้ำ
    lastResearch = Date.now();
    // ปิดเมนู/ชีตด้วย Escape ของ WebUI เอง (สถานะภายในของ bits-ui ถูกต้อง) แล้วค่อยเติม — เมนูคืนโฟกัสให้ปุ่ม "+" ก่อน
    try {
      it.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true, cancelable: true }));
    } catch (err) {}
    setTimeout(researchStart, 40);
  }
  function researchItem(tpl, l) {
    var it = tpl.cloneNode(false);                          // ตัวรายการอย่างเดียว ไม่เอาไอคอน/ป้ายเดิม
    it.removeAttribute("id");
    it.removeAttribute("data-highlighted");
    it.removeAttribute("aria-labelledby");
    it.setAttribute("data-qw-research", "1");
    it.setAttribute("data-qw-no-tx", "");
    it.innerHTML = RES_ICON;
    var span = document.createElement("span");
    span.textContent = STR[l].research;
    it.appendChild(span);
    it.addEventListener("click", function (e) { researchActivate(it, e); });
    it.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") researchActivate(it, e);
    });
    // ไฮไลต์แบบรายการของ bits-ui (ธีมจับ data-highlighted) — ชี้แล้วย้ายโฟกัสมาที่รายการนี้เหมือนรายการอื่น
    it.addEventListener("pointermove", function () { if (document.activeElement !== it) try { it.focus({ preventScroll: true }); } catch (e) {} });
    it.addEventListener("focus", function () { it.setAttribute("data-highlighted", ""); });
    it.addEventListener("blur", function () { it.removeAttribute("data-highlighted"); });
    return it;
  }
  // จาก observer ของ body: เฉพาะรอบที่มีเมนู/ชีตถูกเพิ่มเข้ามา (ไม่ค้นทั้งเอกสารทุก token ระหว่างสตรีม)
  function researchMenu(recs) {
    var scopes = [];
    for (var i = 0; i < recs.length; i++) {
      var r = recs[i];
      if (r.type !== "childList" || !r.addedNodes.length) continue;
      if (r.target.closest && r.target.closest(".chat-messages")) continue;
      for (var k = 0; k < r.addedNodes.length; k++) {
        var n = r.addedNodes[k];
        if (n.nodeType !== 1) continue;
        var sc = n.matches(PLUS_SCOPES) ? n : n.closest(PLUS_SCOPES) || n.querySelector(PLUS_SCOPES);
        if (sc && scopes.indexOf(sc) < 0) scopes.push(sc);
      }
    }
    for (var j = 0; j < scopes.length; j++) {
      var scope = scopes[j];
      if (scope.querySelector("[data-qw-research]")) continue;
      var tpl = plusMenuTemplate(scope);
      if (!tpl) continue;
      tpl.after(researchItem(tpl, lang()));
    }
  }

  /* ---- hero + ชิป ----------------------------------------------------------- */
  function el(tag, cls) { var e = document.createElement(tag); if (cls) e.className = cls; return e; }

  var hero = el("div", "qw-hero");
  var heroRow = el("div", "qw-hero-row");
  var heroMark = el("span", "qw-hero-mark");
  heroMark.setAttribute("aria-hidden", "true");
  heroMark.innerHTML = MARK_SVG;
  var greeting = el("h1", "qw-greeting");
  heroRow.appendChild(heroMark);
  heroRow.appendChild(greeting);
  hero.appendChild(heroRow);
  var pill = el("div", "qw-project-pill");
  pill.addEventListener("click", function () { callShell("openProjectPanel"); });
  pill.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); callShell("openProjectPanel"); }
  });

  // role=group + ชื่อกลุ่ม (ไม่ใช่ list/listitem): role=listitem บน <button> ทับบทบาทปุ่ม
  // โปรแกรมอ่านจอจะอ่านเป็น "รายการ" ไม่มีชื่อ และไม่รู้ว่ากดได้
  var chips = el("div", "qw-chips");
  chips.setAttribute("role", "group");
  // กล่องล่างของ WebUI เป็น pointer-events:none ทั้งก้อน ชิปต้องเปิดเองไม่งั้นคลิกไม่ติด
  chips.style.pointerEvents = "auto";
  chips.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest(".qw-chip") : null;
    if (b && b.__qwPrefill != null) prefill(b.__qwPrefill);
  });

  function greetIndex(h) {
    if (h >= 5 && h < 11) return 0;
    if (h >= 11 && h < 17) return 1;
    if (h >= 17 && h < 21) return 2;
    return 3;
  }
  function updateHero(s) {
    var g = s.greet[greetIndex(new Date().getHours())];
    if (greeting.textContent !== g) greeting.textContent = g;
    var sh = shell(), name = sh && sh.project && sh.project.name;
    if (name) {
      var t = s.project + " · " + name;
      if (pill.textContent !== t) pill.textContent = t;
      // กดเพื่อเปิดแผงโปรเจกต์ได้เฉพาะเมื่อ shell รองรับ ไม่งั้นเป็นแค่ป้าย
      var api = shellApi(), clickable = !!(api && typeof api.openProjectPanel === "function");
      if (clickable && pill.getAttribute("role") !== "button") {
        pill.setAttribute("role", "button");
        pill.setAttribute("tabindex", "0");
        pill.style.pointerEvents = "auto";
        pill.style.cursor = "pointer";
      }
      if (pill.parentNode !== hero) hero.appendChild(pill);
    } else if (pill.parentNode) {
      pill.parentNode.removeChild(pill);
    }
  }
  function updateChips(s, l) {
    if (chips.getAttribute("data-lang") === l && chips.children.length) return;
    chips.setAttribute("data-lang", l);
    chips.setAttribute("aria-label", s.chipsLabel);
    chips.innerHTML = "";
    s.chips.forEach(function (c) {
      var b = el("button", "qw-chip");
      b.type = "button";
      b.setAttribute("data-chip", c[0]);
      b.innerHTML = chipIcon(c[0]);
      var span = el("span");
      span.textContent = c[1];
      b.appendChild(span);
      b.__qwPrefill = c[2];
      if (c[3]) b.title = c[3];                             // batch 2b: คำอธิบายของทางลัด (เช่น Office)
      chips.appendChild(b);
    });
  }
  function detach(node) { if (node.parentNode) node.parentNode.removeChild(node); }

  /* ---- แปล UI ของ WebUI เป็นภาษาไทย (ข้อความ, title, placeholder, ชื่อที่โปรแกรมอ่านจอใช้) ---------- */
  // หลักการ:
  //  1) แปลเฉพาะ "เปลือก" ของ WebUI เนื้อหา (ข้อความแชต การคิด ชื่อแชต ชื่อโมเดล/ไฟล์/เครื่องมือ JSON)
  //     ถูกกันด้วยตำแหน่งใน DOM (TX_SKIP) ไม่ใช่ด้วยคำ คำตอบที่เป็นคำว่า "Cancel" เฉยๆ จึงไม่ถูกแตะ
  //  2) จับคู่ทั้งข้อความ (TH) หรือรูปแบบทั้งข้อความ (TH_RE) เท่านั้น ไม่แทนคำย่อยกลางประโยค
  //  3) เขียน DOM เฉพาะเมื่อค่าเปลี่ยนจริง และจำต้นฉบับไว้คืนได้: text node → WeakMap txOrig,
  //     title/placeholder → data-qw-en-*, aria-label ไม่แตะเลย (webui-theme.css ใช้เป็นตัวเลือก)
  //     ให้ชื่อไทยผ่าน aria-labelledby ที่ชี้ไป <span> ไทยที่ซ่อนไว้ (มาก่อน aria-label ในการคำนวณชื่อ)
  //  4) Svelte 5 จำค่าที่ตัวเองเขียนไว้ (text.__t, __attributes) จึงไม่เขียนทับกลับจนกว่าค่าจริงจะเปลี่ยน
  //     พอเปลี่ยน (เช่น "Processing..." → "Preparing response...") MutationObserver เห็น characterData แล้ว
  //     แปลใหม่ในไมโครทาสก์เดียวกัน ก่อนเบราว์เซอร์วาดภาพ จึงไม่เห็นอังกฤษแวบ — record ที่เกิดจากการเขียน
  //     ของเราเองถูกทิ้งด้วย takeRecords() และ txText() ข้ามค่าที่ตัวเองเขียนไว้แล้ว จึงไม่วนไม่รู้จบ
  //  5) ระหว่างสตรีม ทำเฉพาะ node ที่ถูกเพิ่ม/เปลี่ยน ไม่เดินทั้งเอกสาร และตัดทิ้งทันทีถ้าอยู่ในเนื้อหา (TX_FAST)
  var TX_SKIP = [
    ".markdown-content", "pre", "code", "textarea", "script", "style",
    "[contenteditable]:not([contenteditable=\"false\"])", "[data-qw-no-tx]",
    ".qw-hero", ".qw-chips", "[data-qw-tx-labels]",
    ".reasoning-content",                                  // เนื้อหาการคิดของโมเดล (ทั้งแบบ markdown และข้อความล้วน)
    // ฟองข้อความผู้ใช้ (ข้อความ ป้าย @) ทั้งที่ส่งแล้วและที่รอส่งระหว่างโมเดลยังตอบ — ฟองที่รอส่ง ("Pending user message")
    // วางนอก .chat-message-user แต่ WebUI ใส่ class นี้ให้การ์ดทั้งสองแบบ (ไฟล์แนบอยู่นอกการ์ด ดูชื่อไฟล์แนบข้างล่าง)
    ".chat-message-user-bubble", ".chat-message-user [data-slot=\"card\"]",
    // ชื่อเครื่องมือ/คำสั่ง/ผลลัพธ์แบบโค้ด — ยกเว้นตัวเลขในรายละเอียดของวงแหวนบริบท ("1,645 tok", "2.2t/s", "Context: …")
    // ซึ่ง WebUI จัดรูปเองทั้งหมด (ป๊อปอัป role=status ไม่มีเนื้อหาของผู้ใช้)
    ".font-mono:not([role=\"status\"] [data-slot=\"collapsible-content\"] .font-mono)",
    // ป้ายภาษาของบล็อกโค้ด (```text) มาจากคำตอบของโมเดล และ WebUI อ่านกลับจาก DOM ไปเป็นภาษาของหน้าต่างดูโค้ด
    // (ปุ่มคัดลอก/ดูตัวอย่างในหัวบล็อกยังแปลผ่าน TX_REOPEN — span นี้ไม่ได้ครอบหัวบล็อก จึงยังถูกข้าม)
    ".code-language",
    "[data-conversation-row]",                             // ชื่อแชตในแถบข้าง/หน้าค้นหา/ตารางนำเข้า-ส่งออก
    // ชื่อแชตบนแถบแท็บ: ยึดโครงสร้าง (ลิงก์ไป #/chat/<id> ใน nav ของแถบแท็บ ซึ่ง aria-label ภาษาอังกฤษไม่ถูกเปลี่ยน)
    // ไม่ใช่ data-active-tab ที่ WebUI ใส่ให้เฉพาะแท็บที่เปิดอยู่ — โหลดหน้าใหม่แล้วแท็บอื่นเคยถูกแปล
    // แท็บ "แชตใหม่" ลิงก์ไป #/ จึงยังแปลได้
    "nav[aria-label=\"Open conversations\"] a[href^=\"#/chat/\"]",
    "nav[aria-label=\"Open conversations\"] a[href^=\"#/chat/\"] ~ span.truncate",
    "[data-slot=\"card\"] [data-slot=\"collapsible-content\"]",   // การ์ด MCP: คำอธิบายเครื่องมือ คำแนะนำ log
    "[data-slot=\"card\"] .font-medium.truncate",          // ชื่อเซิร์ฟเวอร์ MCP
    ".models-list [role=\"option\"] > span:first-child",   // ชื่อโมเดล + ป้ายขนาด/quant
    ".chat-messages .bg-card .font-semibold",              // ชื่อเครื่องมือ/เซิร์ฟเวอร์ในกล่องขออนุญาตใช้เครื่องมือ
    // ชื่อไฟล์แนบ (WebUI ไม่มี class/attribute เฉพาะให้เกาะ): การ์ดไฟล์เป็น <button> พื้น bg-muted ทั้งในกล่องพิมพ์
    // ข้อความที่ส่งแล้ว และข้อความที่รอส่ง ชื่อคือ span.truncate.font-medium ข้างใน, ชิปทรัพยากร MCP ที่แนบ,
    // และหัวหน้าต่างดูตัวอย่างไฟล์แนบ — ส่วนอื่นในการ์ด (ขนาดไฟล์ "Sent as Text" ปุ่ม Remove) ยังแปลตามปกติ
    "button.bg-muted .truncate.font-medium", "button > span.max-w-\\[150px\\].truncate",
    ".sticky.top-0 > p.font-medium.text-white:first-child"
  ].join(", ");
  // ส่วนควบคุมของ WebUI ที่วางอยู่ในพื้นที่เนื้อหา: หัวบล็อกโค้ด/ปุ่มของแผนภาพใน markdown (markdown ของโมเดล
  // สร้างปุ่มเองไม่ได้) ปุ่ม "…"/ช่องเลือกที่ซ้อนอยู่ในแถวชื่อแชต (ตัวแถวเองเป็น button แต่ไม่ได้ซ้อนในแถว จึงยังถูกข้าม)
  // และปุ่มกาง "details" ใต้แต่ละบรรทัดของบันทึกการเชื่อมต่อในการ์ด MCP (ไม่นับ <details> ใน markdown ของเซิร์ฟเวอร์)
  var TX_LOG_DETAILS = "[data-slot=\"card\"] [data-slot=\"collapsible-content\"] details > summary:not(.markdown-content *)";
  var TX_REOPEN = ".code-block-header, .code-block-actions, .markdown-content button, " +
    "[data-conversation-row] :is(button, [role=\"checkbox\"], .sr-only), " + TX_LOG_DETAILS;
  // ที่ต้องค้นเพิ่มใต้ส่วนที่ TreeWalker ข้ามทั้งก้อน (ตรงกับ TX_REOPEN) + textarea ที่ต้องแปลแค่ placeholder
  var TX_EXTRA = ".markdown-content :is(.code-block-header, .code-block-actions, button), " +
    "[data-conversation-row] :is(button, [role=\"checkbox\"], .sr-only), textarea[placeholder], " + TX_LOG_DETAILS;
  var TX_FAST = ".markdown-content, pre, code, .reasoning-content";     // เช็กก่อนอย่างอื่นตอนสตรีม
  var MENU_SCOPES = '[data-slot="dropdown-menu-content"], [data-slot="dropdown-menu-sub-content"], [data-slot="sheet-content"]';
  var TX_ATTRS = ["title", "placeholder"];
  var LETTER = /[A-Za-z]/, NF = window.NodeFilter;
  var txOrig = new WeakMap();          // text node → [ค่าอังกฤษเดิม, ค่าไทยที่เราเขียน]

  function hasOwn(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
  function txKey(s) { return s.replace(/\s+/g, " ").trim().replace(/…/g, "..."); }
  function thOf(key) {
    if (hasOwn(TH, key)) return TH[key];
    for (var i = 0; i < TH_RE.length; i++) {
      var m = TH_RE[i][0].exec(key);
      if (!m) continue;
      var out = TH_RE[i][1].apply(null, m);
      // ค่าที่จับได้เป็นไทย (เช่นชื่อไฟล์ภาษาไทยใน toast) ต้องคงเดิมทุกตัวอักษร — ไม่ใส่ word joiner ทั้งข้อความ
      for (var j = 1; j < m.length; j++) if (m[j] && THAI.test(m[j])) return out;
      return glue(out);
    }
    return null;
  }
  // ข้อความที่ใช้แทน key ในภาษา l (null = ปล่อยตามเดิม)
  // "System Message" ในเมนู "+" เป็นกรณีพิเศษทั้งสองภาษา: ใน shell มันเปิดแผงคำสั่งของโปรเจกต์ (interceptSysMsg)
  // แต่ในหน้าตั้งค่ามันคือชื่อช่อง system message ของ WebUI จึงเปลี่ยนเฉพาะในเมนู — คำอธิบายของชีต "+" (sr-only)
  // ก็ต้องเรียกรายการนั้นด้วยชื่อเดียวกัน ไม่งั้นโปรแกรมอ่านจอพูด "system prompt" แต่รายการข้างล่างชื่อ "คำสั่งของโปรเจกต์"
  var SHEET_DESC_EN = "Add files, system prompt or configure MCP servers";
  function txFor(key, el, l) {
    if ((key === "System Message" || key === SHEET_DESC_EN) && el && el.closest && el.closest(MENU_SCOPES) &&
        canRedirectSysMsg()) return key === SHEET_DESC_EN ? STR[l].sheetDesc : STR[l].sysMsg;
    if (l !== "th" || !key || key.length > 400 || !LETTER.test(key)) return null;
    if (el && el.id === "svelte-announcer") return thTitle(key);       // text node เป็นลูกตรงของตัวประกาศ
    if (hasOwn(FRAG_TH, key)) return el && el.closest && el.closest(FRAG_SCOPE) ? FRAG_TH[key] : null;
    return thOf(key);
  }
  // ชื่อเครื่องมือ/เซิร์ฟเวอร์ที่วางถัดจากไอคอนประแจหรือ favicon (หัวบล็อกเครื่องมือในแชต ตารางเครื่องมือ)
  // คือชื่อจริงของเครื่องมือ MCP ต้องคงเดิม — เครื่องมือในตัวของ WebUI มีไอคอนของมันเองและป้ายที่แปลได้
  // (ปุ่มสลับมุมมองสถิติ "Tools" ก็ใช้ไอคอนประแจ แต่ป้ายของมันเป็น sr-only)
  function toolName(el) {
    if (el.tagName !== "SPAN" || el.classList.contains("sr-only")) return false;
    var s = el.previousElementSibling;
    return !!(s && (s.tagName === "IMG" || (s.classList && s.classList.contains("lucide-wrench"))));
  }
  // el อยู่ในพื้นที่เนื้อหาหรือไม่ (el = แม่ของ text node หรือ element เจ้าของ attribute)
  function txBlocked(el) {
    if (!el || el.nodeType !== 1) return true;
    var c = el.closest(TX_SKIP);
    if (c) {
      var o = el.closest(TX_REOPEN);
      if (!o || o === c || !c.contains(o)) return true;
    }
    return toolName(el);
  }
  // textarea อยู่ใน TX_SKIP เพราะ text node ลูกของมันคือค่าที่พิมพ์ แต่ placeholder ของมันเป็นป้ายของ WebUI
  function txBlockedAttr(el) { return txBlocked(el.tagName === "TEXTAREA" ? el.parentElement : el); }

  function txText(n, l) {
    var raw = n.nodeValue, rec = txOrig.get(n);
    if (rec && raw === rec[1]) return;                     // ยังเป็นค่าที่เราเขียนไว้เอง
    var x = raw && raw.length < 600 && LETTER.test(raw) ? txFor(txKey(raw), n.parentNode, l) : null;
    var out = x == null ? raw : raw.match(/^\s*/)[0] + x + raw.match(/\s*$/)[0];
    if (out === raw) { if (rec) txOrig.delete(n); return; }
    txOrig.set(n, [raw, out]);
    n.nodeValue = out;
    // tagEnglish() เคยติด lang="en" ให้ข้อความ sr-only ที่ยังเป็นอังกฤษ — ตอนนี้เป็นไทยแล้ว
    var p = n.parentNode;
    if (p.classList.contains("sr-only")) untagEnglish(p);
  }
  function txAttr(el, a, l) {
    var v = el.getAttribute(a);
    if (v == null) return;
    // placeholder ของกล่องพิมพ์หลักเป็นของ pass() (วันนี้ให้ช่วยอะไรดี? / ตอบกลับ Qwen…)
    if (a === "placeholder" && el.tagName === "TEXTAREA" && el.closest(".chat-screen-form-wrapper")) return;
    var k = "data-qw-en-" + a, en = el.getAttribute(k);
    if (en != null) {
      if (v === txFor(txKey(en), el, l)) return;           // ยังเป็นค่าที่เราเขียนไว้เอง
      el.removeAttribute(k);                               // WebUI เขียนค่าใหม่ทับ — ค่าใหม่คือต้นฉบับ
    }
    var x = LETTER.test(v) ? txFor(txKey(v), el, l) : null;
    if (x == null || x === v) return;
    el.setAttribute(k, v);
    el.setAttribute(a, x);
  }
  // <span> ไทยที่ซ่อนไว้ชุดเดียว ใช้ร่วมกันทุกปุ่มที่มี aria-label เดียวกัน
  // id ต้องไม่ชนกันระหว่างป้ายต่างกัน: ส่วนที่อ่านง่าย (slug) ตัดอักษรไทยทิ้งหมด "Select <ชื่อแชตไทย>" ทุกแถวจึงเคยได้
  // "qw-tx-select" ตัวเดียวกัน แล้วข้อความของแถวสุดท้ายทับของทุกแถว — ต่อท้ายด้วย hash ของป้ายอังกฤษ + คำแปล
  // (ป้ายเดียวกันแปลต่างกันได้ตามตำแหน่ง เช่น "System Message" ในเมนู "+")
  var txBox = null;
  function txHash(s) {
    for (var h = 5381, i = 0; i < s.length; i++) h = (h * 33 + s.charCodeAt(i)) | 0;   // djb2 ต่อ code unit
    return (h >>> 0).toString(36);
  }
  function txLabelId(en, x) {
    var slug = en.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
    var id = "qw-tx-" + (slug ? slug + "-" : "") + txHash(en + "\u0000" + x);
    var s = document.getElementById(id);
    if (!s) {
      if (!txBox || !txBox.isConnected) {
        txBox = el("div");
        txBox.hidden = true;
        txBox.setAttribute("data-qw-tx-labels", "");
        document.body.appendChild(txBox);
      }
      s = el("span");
      s.id = id;
      txBox.appendChild(s);
    }
    if (s.textContent !== x) s.textContent = x;
    return id;
  }
  function txAria(el, l) {
    var en = el.getAttribute("aria-label"), lb = el.getAttribute("aria-labelledby"), cur = el.getAttribute("data-qw-tx");
    var x = en != null && l === "th" && LETTER.test(en) ? txFor(txKey(en), el, l) : null;
    if (x) {
      if (lb && lb.indexOf("qw-tx-") !== 0) return;       // WebUI ผูกชื่อไว้เองแล้ว ไม่แตะ
      var id = txLabelId(en, x);
      if (lb !== id) el.setAttribute("aria-labelledby", id);
      if (cur !== en) el.setAttribute("data-qw-tx", en);
      untagEnglish(el);                                     // tagEnglish() รอบก่อนติดไว้
    } else if (cur != null) {
      // Svelte ใช้ element เดิมซ้ำแต่ป้ายเปลี่ยนเป็นคำอื่น หรือกลับเป็นภาษาอังกฤษ — คืนชื่อของ WebUI
      el.removeAttribute("data-qw-tx");
      if (lb && lb.indexOf("qw-tx-") === 0) el.removeAttribute("aria-labelledby");
    }
  }
  function txEl(e, l) {
    if (e.hasAttribute("title")) txAttr(e, "title", l);
    if (e.hasAttribute("placeholder")) txAttr(e, "placeholder", l);
    if (e.hasAttribute("aria-label") || e.hasAttribute("data-qw-tx")) txAria(e, l);
  }
  var TX_FILTER = { acceptNode: function (n) {
    if (n.nodeType === 3) return NF.FILTER_ACCEPT;
    return n.matches(TX_SKIP) || toolName(n) ? NF.FILTER_REJECT : NF.FILTER_ACCEPT;
  } };
  function txWalk(root, l) {           // root ผ่านการเช็กว่าแปลได้มาแล้ว
    txEl(root, l);
    var w = document.createTreeWalker(root, NF.SHOW_ELEMENT | NF.SHOW_TEXT, TX_FILTER), n;
    while ((n = w.nextNode())) { if (n.nodeType === 3) txText(n, l); else txEl(n, l); }
  }
  // ส่วนที่ถูกข้ามทั้งก้อนแต่ข้างในมีส่วนควบคุมของ WebUI (หัวบล็อกโค้ด) หรือช่องพิมพ์ที่ placeholder ต้องแปล
  function txExtra(root, l) {
    if (root.matches(TX_EXTRA)) {
      if (root.tagName === "TEXTAREA") { if (!txBlockedAttr(root)) txEl(root, l); } else if (!txBlocked(root)) txWalk(root, l);
      return;
    }
    if (!root.firstElementChild) return;
    var ex = root.querySelectorAll(TX_EXTRA);
    for (var i = 0; i < ex.length; i++) {
      var e = ex[i];
      if (e.tagName === "TEXTAREA") { if (!txBlockedAttr(e)) txEl(e, l); }
      else if (!txBlocked(e)) txWalk(e, l);
    }
  }
  function txTree(root, l) {
    if (root.nodeType === 3) { if (!txBlocked(root.parentNode)) txText(root, l); return; }
    if (root.nodeType !== 1) return;
    if (!txBlocked(root)) txWalk(root, l);
    txExtra(root, l);
  }

  // ---- จาก MutationObserver: เฉพาะ node ที่เพิ่ม/เปลี่ยน (ระหว่างสตรีมเกือบทั้งหมดอยู่ในเนื้อหาคำตอบ → ตัดทิ้งเร็ว) ----
  var txStat = { batches: 0, records: 0, ms: 0, maxMs: 0 };
  function txRecords(recs) {
    // record ติดกันมักมาจาก node เดียวกัน (โทเค็นต่อท้าย text node / <p> เดิม) — จำผลของ node ล่าสุดไว้
    var l = lang(), t0 = performance.now(), lastT = null, lastHost = null, lastFast = false;
    if (l !== "th") { if (canRedirectSysMsg()) txRedirectOnly(recs); }
    else for (var i = 0; i < recs.length; i++) {
      var r = recs[i], t = r.target;
      if (r.type === "characterData") {
        if (t === lastT) continue;
        lastT = t;
        var p = t.parentNode;
        if (p && p.nodeType === 1 && !p.closest(TX_FAST) && !txBlocked(p)) txText(t, l);
      } else if (r.type === "childList") {
        var ad = r.addedNodes;
        if (!ad.length) continue;
        var host = t.nodeType === 1 ? t : t.parentNode;
        if (host !== lastHost) { lastHost = host; lastFast = !host || !!host.closest(TX_FAST); }
        var fast = lastFast;
        for (var j = 0; j < ad.length; j++) {
          var n = ad[j];
          if (!n.isConnected) continue;                     // ถูกถอดออกไปแล้วในชุดเดียวกัน
          if (!fast) txTree(n, l);
          else if (n.nodeType === 1) txExtra(n, l);         // ในเนื้อหา: หาเฉพาะหัวบล็อกโค้ด/ปุ่มของ WebUI
        }
      } else {
        var an = r.attributeName;
        if (an !== "title" && an !== "placeholder" && an !== "aria-label") continue;
        if (txBlockedAttr(t)) continue;
        if (an === "aria-label") txAria(t, l); else txAttr(t, an, l);
      }
    }
    var dt = performance.now() - t0;
    txStat.batches++; txStat.records += recs.length; txStat.ms += dt;
    if (dt > txStat.maxMs) txStat.maxMs = dt;
  }
  // โหมดอังกฤษ: แตะเฉพาะป้าย "System Message" ในเมนู "+" (เมนูถูกวาดใหม่ทั้งก้อนทุกครั้งที่เปิด)
  function txRedirectOnly(recs) {
    var lastHost = null, inMenu = false;
    for (var i = 0; i < recs.length; i++) {
      var r = recs[i];
      if (r.type !== "childList" || !r.addedNodes.length) continue;
      var host = r.target.nodeType === 1 ? r.target : r.target.parentNode;
      if (host !== lastHost) { lastHost = host; inMenu = !!(host && host.closest && host.closest(MENU_SCOPES)); }
      for (var j = 0; j < r.addedNodes.length; j++) {
        var n = r.addedNodes[j];
        if (n.nodeType !== 1 || !n.isConnected) continue;
        if (inMenu || n.matches(MENU_SCOPES) || n.querySelector(MENU_SCOPES)) txTree(n, "en");
      }
    }
  }

  // ---- สลับภาษาสดๆ โดยไม่โหลดหน้าใหม่ ----
  // คืนต้นฉบับทุกจุดที่เราเคยเปลี่ยน (WeakMap วนไม่ได้ จึงเดิน text node ทั้งเอกสารครั้งเดียว — ทำเฉพาะตอนสลับภาษา)
  function txRestore() {
    var w = document.createTreeWalker(document.body, NF.SHOW_TEXT), n;
    while ((n = w.nextNode())) {
      var r = txOrig.get(n);
      if (r) { if (n.nodeValue === r[1]) n.nodeValue = r[0]; txOrig.delete(n); }
    }
    TX_ATTRS.forEach(function (a) {
      var k = "data-qw-en-" + a, els = document.querySelectorAll("[" + k + "]");
      for (var i = 0; i < els.length; i++) {
        var e = els[i], en = e.getAttribute(k);
        if (e.getAttribute(a) === txFor(txKey(en), e, "th")) e.setAttribute(a, en);
        e.removeAttribute(k);
      }
    });
    var ts = document.querySelectorAll("[data-qw-tx]");
    for (var i = 0; i < ts.length; i++) {
      var lb = ts[i].getAttribute("aria-labelledby");
      ts[i].removeAttribute("data-qw-tx");
      if (lb && lb.indexOf("qw-tx-") === 0) ts[i].removeAttribute("aria-labelledby");
    }
    // lang="en" ที่ tagEnglish() ติดไว้ตอนหน้าเป็นไทย — หน้าอังกฤษไม่มี (<html lang="en"> อยู่แล้ว)
    var tg = document.querySelectorAll("[" + EN_MARK + "]");
    for (var j = 0; j < tg.length; j++) untagEnglish(tg[j]);
    // ป้ายไทยที่ซ่อนไว้ไม่มีใครอ้างถึงแล้ว — ถอดออกให้ DOM เหมือนหน้าที่เปิดเป็นอังกฤษตั้งแต่แรก
    if (txBox) { detach(txBox); txBox = null; }
  }
  // ข้อความอังกฤษเดิมของ node (ก่อนแปล) — โค้ดที่ตัดสินใจจากป้ายของ WebUI ต้องอ่านค่านี้ ไม่ใช่ textContent
  function enText(node) {
    if (!node) return "";
    if (node.nodeType === 3) {
      var r = txOrig.get(node);
      return r && node.nodeValue === r[1] ? r[0] : node.nodeValue;
    }
    var s = "", w = document.createTreeWalker(node, NF.SHOW_TEXT), n;
    while ((n = w.nextNode())) s += enText(n);
    return s;
  }
  function enAttr(e, a) {
    var v = e.getAttribute("data-qw-en-" + a);
    return v != null ? v : e.getAttribute(a);
  }

  // <html lang> เป็นภาษาของ shell (สัญญา 5c) — ชื่อปุ่มของ WebUI ที่ยังเป็นอังกฤษล้วน (ไม่อยู่ในพจนานุกรม
  // เช่นชื่อโมเดล) ติด lang="en" ให้ เสียงอ่านภาษาไทยจะได้ไม่อ่านด้วยกฎภาษาไทย
  // ไม่แตะกล่องที่มีเนื้อหาข้อความ (เช่น role=group ของข้อความแชต) — เฉพาะปุ่ม/ลิงก์/sr-only
  var THAI = /[฀-๿]/, ASCII_NAME = /^[\x20-\x7E…⌘]*[A-Za-z][\x20-\x7E…⌘]*$/;
  // จด element ที่เราติด lang="en" เอง (ไม่ใช่ของ WebUI) ไว้ถอดคืนได้ — สลับกลับเป็นอังกฤษแล้ว DOM ต้องเหมือนหน้าที่
  // เปิดเป็นอังกฤษตั้งแต่แรก
  var EN_MARK = "data-qw-lang-en";
  function tagEnglish() {
    if (root.getAttribute("lang") !== "th") return;
    // ปุ่มที่ได้ชื่อไทยแล้ว (data-qw-tx) ไม่ใช่ชื่ออังกฤษ ห้ามติด lang="en"
    var els = document.querySelectorAll(
      ':is(button, a, [role="button"])[aria-label]:not([lang]):not([data-qw-tx]), .sr-only:not([lang])');
    for (var i = 0; i < els.length; i++) {
      var e = els[i], name = (e.getAttribute("aria-label") || e.textContent || "").trim();
      if (ASCII_NAME.test(name) && !THAI.test(e.textContent)) { e.setAttribute("lang", "en"); e.setAttribute(EN_MARK, ""); }
    }
  }
  function untagEnglish(e) {
    if (!e.hasAttribute(EN_MARK)) return;                  // lang ที่ WebUI ใส่เองไม่แตะ
    e.removeAttribute(EN_MARK);
    if (e.getAttribute("lang") === "en") e.removeAttribute("lang");
  }

  /* ---- กล่องโต้ตอบของเบราว์เซอร์ (confirm/prompt/alert) ------------------------------------- */
  // WebUI เรียก window.confirm('Delete "<ชื่อแชต>"? This action cannot be undone.') และ
  // window.prompt("Rename conversation", ชื่อเดิม) จากรายการแชต (แถบข้าง/หน้าค้นหาบนมือถือ) ข้อความในกล่องของ
  // เบราว์เซอร์แปลผ่าน DOM ไม่ได้ จึงห่อฟังก์ชันไว้แปลเฉพาะข้อความคำถาม — ค่าตั้งต้นของ prompt (ชื่อแชต) และค่าที่คืน
  // ส่งผ่านตามเดิมทุกอย่าง ข้อความที่ไม่อยู่ในพจนานุกรมก็ส่งต่อไปตามเดิม
  ["confirm", "prompt", "alert"].forEach(function (fn) {
    var orig = window[fn];
    if (typeof orig !== "function") return;
    window[fn] = function (msg) {
      var args = Array.prototype.slice.call(arguments);
      if (typeof msg === "string" && lang() === "th") {
        try { var x = txFor(txKey(msg), null, "th"); if (x != null) args[0] = x; } catch (e) {}
      }
      return orig.apply(window, args);
    };
  });

  /* ---- วงแหวนการใช้บริบท: ว่างอยู่ไม่ต้องเป็นจุดหยุดของ Tab ----------------------------- */
  // WebUI วาด stroke-dashoffset = เส้นรอบวง × (1 − เปอร์เซ็นต์) → เท่ากับเส้นรอบวงเมื่อยังไม่มีการใช้/0%
  // อ่านไม่ออก (รุ่นหน้าเปลี่ยนวิธีวาด) ถือว่าไม่ว่าง — ปล่อย tabindex ตามเดิมของ WebUI
  function gaugeEmpty(g) {
    var cs = g.querySelectorAll("circle"), c = cs[cs.length - 1];
    if (!c) return false;
    var len = parseFloat(c.getAttribute("stroke-dasharray")), off = parseFloat(c.getAttribute("stroke-dashoffset"));
    if (!(len > 0) || isNaN(off)) return false;
    return off >= len - 0.01;
  }
  function syncGauge() {
    var gs = document.querySelectorAll("[data-context-gauge-trigger]");
    for (var i = 0; i < gs.length; i++) {
      var g = gs[i];
      if (g.__qwTab === undefined) g.__qwTab = g.getAttribute("tabindex");   // ค่าเดิมของ WebUI ("0")
      var want = gaugeEmpty(g) ? "-1" : g.__qwTab;
      if (want == null) { if (g.hasAttribute("tabindex")) g.removeAttribute("tabindex"); }
      else if (g.getAttribute("tabindex") !== want) g.setAttribute("tabindex", want);
    }
  }

  /* ---- รอบปรับ DOM (idempotent: ถ้าทุกอย่างถูกที่แล้วต้องไม่เขียน DOM เลย) -------- */
  var wasStreaming = false;
  // ภาษาที่ <html lang> ควรเป็น: ค่าจาก setLang() หรือของ shell — เปิดเดี่ยว (ไม่มีทั้งคู่) ไม่แตะ
  function wantLang() {
    if (langOverride) return langOverride;
    var sh = shell();
    return sh && (sh.lang === "th" || sh.lang === "en") ? sh.lang : null;
  }
  function syncRootAttrs() {
    var sh = shell(), wl = wantLang();
    setAttr("data-qw-embedded", sh ? "1" : null);
    if (wl) setAttr("lang", wl);
  }
  function pass() {
    syncRootAttrs();
    mirrorTheme();
    var r = checkRoute();
    var s = S(), l = lang();
    var wrap = document.querySelector(".chat-screen-form-wrapper");
    var form = wrap && wrap.querySelector("form.conversation-chat-form");
    var host = wrap && wrap.parentNode;

    // ติดป้ายกล่องต้อนรับเดิมของ WebUI ให้ธีมซ่อนได้ด้วยตัวเลือกที่ไม่เปราะ
    if (host) {
      for (var c = host.firstElementChild; c; c = c.nextElementSibling) {
        if (c !== hero && c.querySelector && c.querySelector(":scope > h1") &&
            c.getAttribute("data-qw-welcome") !== "orig") c.setAttribute("data-qw-welcome", "orig");
      }
    }

    if (r.name === "start" && wrap && form) {
      updateHero(s);
      if (hero.parentNode !== host || hero.nextElementSibling !== wrap) host.insertBefore(hero, wrap);
      updateChips(s, l);
      if (chips.parentNode !== wrap || chips.previousElementSibling !== form) form.after(chips);
      setAttr("data-qw-hero", "1");
    } else {
      detach(hero);
      detach(chips);
      setAttr("data-qw-hero", null);
    }

    var ta = form && form.querySelector("textarea");
    if (ta) {
      var ph = r.name === "chat" ? s.phChat : s.phStart;
      if (ta.getAttribute("placeholder") !== ph) ta.setAttribute("placeholder", ph);
    }

    var dlg = dialogOpen();
    if (!hadDialog && dlg) onDialogOpen();
    if (hadDialog && !dlg) { hadDialog = false; afterDialog(); }
    hadDialog = dlg;
    if (dlg) { syncDialogTheme(); syncForkName(l); }

    // การแปลทำใน MutationObserver ทันทีที่ node โผล่ (txRecords) ไม่ใช่ที่นี่ — ที่นี่แค่ติด lang="en"
    // ให้ชื่อที่ยังเป็นอังกฤษ ซึ่งต้องทำหลังแปลแล้ว (ปุ่มที่ได้ชื่อไทยต้องไม่ถูกติด)
    tagEnglish();
    syncGauge();

    // คำตอบจบ = ชื่อแชตอาจถูกตั้ง/เปลี่ยน ให้ shell อ่านรายการล่าสุดใหม่
    var st = isStreaming();
    if (wasStreaming && !st) { callShell("refreshRecents"); onStreamEnd(); skillTitleSoon(0); }
    if (!wasStreaming && st) { onStreamStart(); skillTitleSoon(1500); }   // batch 2a (fix): ชื่อแชตจากชิปสกิล
    wasStreaming = st;
    extrasPass(r, st);                      // รอบ 4 (K5-K9) — แยกไว้ท้ายไฟล์ แต่ละส่วนพังได้โดยไม่ลากกัน
  }

  // จำกัดความถี่: รวมทุกการเปลี่ยนแปลงในเฟรมเดียวเป็นหนึ่งรอบ
  // rAF ทำให้แทรก hero ก่อนเบราว์เซอร์วาดภาพ (ไม่เห็น "Hello there" แวบ)
  // setTimeout สำรองไว้เผื่อ iframe ถูกซ่อนจน rAF ไม่ทำงาน — ยกเลิกตัวที่เหลือเมื่ออีกตัวทำไปแล้ว
  var pending = false, rafId = 0, toId = 0;
  function runPass() {
    if (!pending) return;
    pending = false;
    cancelAnimationFrame(rafId);
    clearTimeout(toId);
    try { pass(); } catch (e) { /* อย่าให้ข้อผิดพลาดรอบเดียวหยุดการทำงานถาวร */ }
  }
  function schedule() {
    if (pending) return;
    pending = true;
    rafId = requestAnimationFrame(runPass);
    toId = setTimeout(runPass, 250);
  }
  // ระหว่างสตรีม ทุก token ทำให้ DOM ใน .chat-messages เปลี่ยน แต่ pass() ไม่ได้สนใจส่วนนั้น
  // (hero, ชิป, placeholder, ปุ่ม Stop อยู่นอก) จึงข้ามรอบที่เปลี่ยนแต่ในนั้นล้วนๆ
  function onlyInMessages(recs) {
    for (var i = 0; i < recs.length; i++) {
      var t = recs[i].target;
      if (t && t.nodeType !== 1) t = t.parentNode;
      if (!t || !t.closest || !t.closest(".chat-messages")) return false;
    }
    return true;
  }

  /* ---- ผู้ฟังเหตุการณ์ ------------------------------------------------------- */
  // ทำแบบ sync (ไม่รอเฟรม) — ถ้าปล่อยช้าจะเห็นสีผิดแวบหนึ่งตอน mode-watcher เปลี่ยน class
  new MutationObserver(function () {
    mirrorTheme();
    reconcileTheme();
    var wl = wantLang();
    if (wl) setAttr("lang", wl);
  }).observe(root, { attributes: true, attributeFilter: ["class", "data-theme", "lang"] });

  // ตัวเดียวทำสองงาน:
  //  1) แปล UI ของ WebUI ทันที (sync ในไมโครทาสก์ ก่อนวาดภาพ) จาก record ที่เพิ่ม/เปลี่ยน — characterData,
  //     title/aria-label เฝ้าไว้ให้งานนี้อย่างเดียว แล้วทิ้ง record ที่การแปลของเราเองก่อขึ้นด้วย takeRecords()
  //  2) นัด pass() เฉพาะเมื่อโครงสร้างเปลี่ยน/placeholder ถูกตั้งใหม่ (เหมือนเดิม)
  // stroke-dashoffset = วงแหวนบริบทขยับ (เปลี่ยนแค่ attribute ไม่มี node ใหม่) — จัดการตรงนี้เลย
  // ไม่ต้องรันรอบเต็ม เพราะระหว่างสตรีมมันขยับถี่ (attribute ที่เราเขียนเองไม่ได้ถูกเฝ้า จึงไม่วนซ้ำ)
  var bodyObs = new MutationObserver(function (recs) {
    try { txRecords(recs); } catch (e) { /* แปลพลาดรอบเดียวต้องไม่ทำให้ส่วนอื่นหยุด */ }
    bodyObs.takeRecords();
    try { watchAnnouncer(); } catch (e) {}                  // ต้องอยู่ในไมโครทาสก์นี้ (ก่อนโปรแกรมอ่านจอเห็นค่าเก่า)
    // การ์ด local_confirm / เมนู "อนุญาตเสมอ" / สวิตช์ในหน้าตั้งค่า: จัดการในไมโครทาสก์นี้ก่อนวาดภาพ (ALLOW-GUARD ฝั่ง UI)
    // หลัง takeRecords: สิ่งที่เราใส่ (กล่องตรวจทาน) ต้องเป็น record ของรอบหน้า ตัวแปลจะได้แปลป้ายของมัน
    try { permGuard(recs); } catch (e) {}
    try { researchMenu(recs); } catch (e) {}                // batch 2a (B5): รายการ "ค้นคว้าเชิงลึก" ในเมนู "+"
    try { b2bObs(recs); } catch (e) {}                      // batch 2b (C4): ปิดตัวเลือก @ ของ WebUI ที่ค้นไฟล์ไม่ได้
    var rest = [], gauge = false;
    for (var j = 0; j < recs.length; j++) {
      var r = recs[j], an = r.attributeName;
      if (r.type === "characterData") continue;
      if (r.type === "attributes" && an !== "placeholder") {
        if (an === "stroke-dashoffset" && !gauge && r.target.closest && r.target.closest("[data-context-gauge-trigger]")) gauge = true;
        continue;
      }
      rest.push(r);
    }
    if (gauge) syncGauge();
    if (!rest.length) return;
    promptScanSoon();                       // การ์ดขออนุญาต/ทำต่อโผล่กลางสตรีม (pass() ถูกข้ามตอนนั้น) — หน่วงไว้ ≤ 300ms
    if (wasStreaming && onlyInMessages(rest)) return;
    schedule();
  });
  bodyObs.observe(document.body || root, {
    childList: true, subtree: true, characterData: true, attributes: true,
    attributeFilter: ["placeholder", "stroke-dashoffset", "title", "aria-label"]
  });

  /* ---- ประกาศเปลี่ยนหน้า (aria-live) ให้ตรงกับแชตที่เปิดจริง ---------------------------------------- */
  // SvelteKit เขียน document.title ลงตัวประกาศ (#svelte-announcer, aria-live="assertive") หนึ่ง tick หลังเปลี่ยนเส้นทาง
  // แต่ WebUI ตั้ง title ของแชตหลังโหลดแชตจาก IndexedDB เสร็จซึ่งช้ากว่านั้น โปรแกรมอ่านจอจึงประกาศชื่อแชต "ก่อนหน้า"
  // ทุกครั้งที่เปลี่ยนแชต (ทั้งสองภาษา) — หลังเปลี่ยนเส้นทาง ล้างค่าที่ SvelteKit เขียน (ทำใน MutationObserver ซึ่งจบก่อน
  // เบราว์เซอร์ส่งข้อความให้โปรแกรมอ่านจอ ค่าเก่าจึงไม่ถูกอ่าน) รอให้ title นิ่ง (ไม่เปลี่ยนอีก 300ms, ช้าสุด 1.5 วินาที
  // หลังเปลี่ยนเส้นทาง) แล้วเขียน title ล่าสุดครั้งเดียว — เขียนลง text node เดิม (Svelte ถือ node นี้ไว้ ห้ามแทนทั้ง node)
  // โหมดไทย: เขียนค่าอังกฤษ แล้ว observer ของ body แปลต่อในไมโครทาสก์เดียวกัน (thTitle) ก่อนเบราว์เซอร์อ่าน
  var ANN_QUIET_MS = 300, ANN_MAX_MS = 1500;
  var annRoute = 0, annDone = true, annTo = 0, annSeen = null;
  function announcerNode() {
    var a = document.getElementById("svelte-announcer");
    if (!a) return null;                                    // SvelteKit สร้างตัวประกาศตอนนำทางครั้งแรก
    for (var c = a.firstChild; c; c = c.nextSibling) if (c.nodeType === 3) return c;
    return null;
  }
  function annNewRoute() {
    checkRoute();                                           // pass() อาจยังไม่ได้รัน (มันรอเฟรม)
    if (annRoute === routeAt) return false;
    annRoute = routeAt;
    annDone = false;
    return true;
  }
  function announceNow() {
    clearTimeout(annTo);
    var n = announcerNode();
    if (!n) return;                                         // ยังไม่มีตัวประกาศ — รอให้ SvelteKit เขียนแล้วค่อยทำ
    annDone = true;
    var t = document.title || "untitled page";
    if (enText(n) !== t) n.nodeValue = t;
  }
  function announceLater() {
    clearTimeout(annTo);
    annTo = setTimeout(announceNow, Math.max(0, Math.min(ANN_QUIET_MS, annRoute + ANN_MAX_MS - Date.now())));
  }
  // จาก observer ของ body ทุกรอบ (หลังแปล): ดูเฉพาะว่าข้อความของตัวประกาศเปลี่ยนไปจากที่เห็นล่าสุดหรือไม่
  function watchAnnouncer() {
    var n = announcerNode(), v = n ? enText(n) : null;
    if (v === annSeen) return;
    annSeen = v;
    if (!n || !v) return;
    annNewRoute();
    if (annDone) return;                                    // ค่าที่เราเขียนเอง หรือ SvelteKit เขียนโดยไม่ได้เปลี่ยนหน้า
    n.nodeValue = "";
    annSeen = "";
    announceLater();
  }
  if (document.head) {
    new MutationObserver(function () {                      // title เปลี่ยน: เริ่มนับเวลานิ่งใหม่
      annNewRoute();
      if (!annDone) announceLater();
    }).observe(document.head, { childList: true, subtree: true, characterData: true });
  }

  // สลับภาษาสดๆ (shell เรียกได้โดยไม่ต้องโหลด iframe ใหม่): คืนต้นฉบับอังกฤษทุกจุดก่อน แล้วแปลใหม่ตามภาษาใหม่
  // ค่าที่ตั้งอยู่ในหน้าแชตนี้เท่านั้น (langOverride) — ไม่เขียน qwenShell.lang ของ parent: หน้า shell ไม่ได้วาดใหม่
  // ตาม ข้อมูลของมันจะบอกภาษาหนึ่งขณะที่หน้าจอเป็นอีกภาษา และถ้า shell โหลด iframe ใหม่ (บันทึกคำสั่ง/เปลี่ยนโมเดล)
  // หน้าแชตจะบูตจากค่านั้นเป็นคนละภาษากับ shell รอบข้าง ภาษาของ shell เป็นของ shell (PATCH /api/settings แล้วโหลดใหม่)
  function setLang(l) {
    if (l !== "th" && l !== "en") return false;
    var prev = lang();
    langOverride = l;
    setAttr("lang", l);
    if (prev !== l) {
      txRestore();
      restoreForkName();
      txTree(document.body, l);
      bodyObs.takeRecords();
    }
    chips.removeAttribute("data-lang");
    pass();
    return true;
  }

  // ดัก "System Message" ของเมนู "+" และจดว่าผู้ใช้เลือกธีมเองในหน้าตั้งค่าหรือไม่
  ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "keydown", "keyup"].forEach(function (t) {
    window.addEventListener(t, interceptSysMsg, true);
  });
  ["pointerup", "click", "keydown"].forEach(function (t) {
    window.addEventListener(t, noteThemePick, true);
  });

  window.addEventListener("storage", function (e) {
    if (e.key === null) { applyTheme(); applyFont(readFont()); return; }   // localStorage.clear()
    if (e.key === KEY_MW || e.key === KEY_THEME) {
      if (validPref(e.newValue)) applyPref(e.newValue);
    } else if (e.key === KEY_FONT) {
      applyFont(e.newValue);
    }
  });

  window.addEventListener("hashchange", function () { checkRoute(); schedule(); });
  window.addEventListener("popstate", function () { checkRoute(); schedule(); });

  // ช็อตคัตเมื่ออยู่ใน shell: ส่งต่อให้ shell (แถบข้างของ WebUI ถูกซ่อน กดไปก็ไม่เห็นผล)
  // ใช้ capture + หยุด event เพื่อไม่ให้ตัวจัดการของ WebUI ทำงานซ้อน
  // เช็ก e.code ด้วยเพราะแป้นพิมพ์ภาษาไทยให้ e.key เป็นอักษรไทย
  window.addEventListener("keydown", function (e) {
    if (!(e.ctrlKey || e.metaKey) || e.altKey || !shell()) return;
    var k = (e.key || "").toLowerCase(), code = e.code || "";
    var fn = null;
    if (!e.shiftKey && (k === "k" || code === "KeyK")) fn = "focusSearch";
    else if (e.shiftKey && (k === "o" || code === "KeyO")) fn = "newChat";
    else if (!e.shiftKey && (k === "b" || code === "KeyB")) fn = "toggleSidebar";
    if (!fn) return;
    var api = shellApi();
    if (!api || typeof api[fn] !== "function") return;
    e.preventDefault();
    e.stopImmediatePropagation();
    try { api[fn](); } catch (err) {}
  }, true);

  // คำทักทายเปลี่ยนตามชั่วโมง — เช็กทุกนาทีพอ
  setInterval(function () { if (hero.parentNode) schedule(); }, 60000);

  /* ======================================================================================
     S3 (2026-09-30 ดึก): ดึงข้อความตรวจทาน "ของเซิร์ฟเวอร์" ให้การ์ดอนุญาต local_confirm
     นี่คือช่องทางเครือข่ายช่องเดียวของไฟล์นี้ (ส่วนอื่นทั้งไฟล์ไม่ส่งอะไรออกไปไหน) จึงแยกไว้ตรงนี้ให้ตรวจได้ในที่เดียว
     ทำไมต้องมี: เดิมโมเดลต้องคัดลอก review ทั้งก้อนกลับมาใน local_confirm แล้วการ์ดโชว์ "ข้อความที่โมเดลส่ง" — ทดสอบจริง
     Qwen3-4B คัดลอกได้แค่บางส่วน (เซิร์ฟเวอร์ปฏิเสธ) แล้วหันไปถามคนซ้ำแทนที่จะลองใหม่ สัญญา S2 จึงให้ review เป็นทางเลือก
     และด่านจริงย้ายมาอยู่ที่ "คนอ่าน review ของเซิร์ฟเวอร์ในการ์ดก่อนกด" — การ์ดจึงต้องถามเซิร์ฟเวอร์เอง (S1:
     GET /review/<slug>?token=<confirm token>) ห้ามเชื่อข้อความที่โมเดลส่งมา (โมเดลที่ถูกหลอกโชว์โค้ดหนึ่ง ยืนยันอีกโค้ดได้)
     ขอบเขตที่ตั้งใจให้แคบที่สุด:
       • ปลายทางเดียว = URL ของเซิร์ฟเวอร์ id "local"/"local-full" ในค่าตั้ง MCP ของ WebUI เอง (ที่ WebUI ส่ง Bearer ไปอยู่แล้ว
         ทุกคำขอ) และต้องเป็น loopback — token ของเครื่องไม่มีวันถูกส่งไปเครื่องอื่นแม้ค่าตั้งจะถูกแก้
       • GET อย่างเดียว ส่งเฉพาะ Authorization (header อื่นในค่าตั้งไม่ส่ง) ไม่ตาม redirect ไม่ส่ง cookie/referrer หมดเวลา 6 วิ
       • token อ่านจาก localStorage ตอนใช้ ไม่เก็บไว้ในตัวแปรค้าง ไม่ log ไม่ใส่ DOM
       • endpoint ไม่เผา/ไม่ต่ออายุ token แต่มี rate limit — ผู้เรียก (rvSrv) ขอครั้งเดียวต่อ token ลองใหม่เฉพาะความล้มเหลว
         ชั่วคราวไม่เกิน 3 ครั้ง
     ====================================================================================== */
  var SRV_TIMEOUT_MS = 6000;
  // review จริงไม่เกิน ~48,000 ตัวอักษร (JSON escape แล้วยาวขึ้นได้หลายเท่า) — ยาวเกินนี้ไม่ใช่คำตอบของเซิร์ฟเวอร์เรา ไม่ parse
  var SRV_MAX_BODY = 2000000;
  var SRV_IDS = { "local": 1, "local-full": 1 };
  var SRV_LOOPBACK = /^(?:127\.0\.0\.1|localhost|\[::1\])$/i;
  // serverInfo.name ที่ mcp-local ตอบ (การ์ดเรียกเซิร์ฟเวอร์ด้วยชื่อนี้) → ผิวของ URL
  var SRV_LABEL_SURFACE = { "qwen38-local-fast": "fast", "qwen38-local": "mcp" };

  // entry ของ MCP เครื่องนี้ → {base, slug, surface, auth} หรือ null · slug คงรูป percent-encoded ตามที่อยู่ใน URL
  // (slug ภาษาไทยจึงต่อเข้า path ได้ตรงตัว เซิร์ฟเวอร์ unquote เอง) · ไม่มี Authorization แบบ Bearer = ใช้ไม่ได้
  function srvEntry(s) {
    var u, auth = "", h = s.headers;
    try { u = new URL(String(s.url || "")); } catch (e) { return null; }
    if ((u.protocol !== "http:" && u.protocol !== "https:") || !SRV_LOOPBACK.test(u.hostname) || u.username || u.password) return null;
    var seg = u.pathname.split("/");
    if (seg.length < 3 || (seg[1] !== "fast" && seg[1] !== "mcp") || !seg[2]) return null;
    try { if (typeof h === "string") h = h ? JSON.parse(h) : null; } catch (e) { h = null; }
    if (h && typeof h === "object" && !Array.isArray(h)) {
      for (var k in h) if (hasOwn(h, k) && /^authorization$/i.test(k) && typeof h[k] === "string") auth = h[k];
    }
    if (!/^Bearer [\x21-\x7E]{8,512}$/.test(auth)) return null;
    return { base: u.origin, slug: seg[2], surface: seg[1], auth: auth };
  }
  // เลือก entry ที่การ์ดเอ่ยชื่อก่อน (ชื่อ/URL ในค่าตั้ง แล้วผิวตาม serverInfo.name) ไม่งั้นตัวที่เปิดใช้อยู่
  // (สองผิวของเครื่องนี้ชี้ slug เดียวกันเสมอ และ S1 รับ token ของโปรเจกต์นั้นจากผิวไหนก็ได้ — ข้อนี้แค่เลือกให้ตรงที่สุด)
  function srvConfig(label) {
    var list;
    try {
      var cfg = JSON.parse(localStorage.getItem("LlamaUi.config") || "{}") || {};
      list = typeof cfg.mcpServers === "string" ? JSON.parse(cfg.mcpServers || "[]") : cfg.mcpServers;
    } catch (e) { return null; }
    if (!Array.isArray(list)) return null;
    label = String(label || "").replace(/ \(\d+\)$/, "");        // ชื่อซ้ำ WebUI ต่อท้าย " (2)"
    var want = hasOwn(SRV_LABEL_SURFACE, label) ? SRV_LABEL_SURFACE[label] : "", best = null, rank = -1;
    for (var i = 0; i < list.length; i++) {
      var s = list[i], c = s && typeof s === "object" && hasOwn(SRV_IDS, s.id) ? srvEntry(s) : null;
      if (!c) continue;
      var r = (label && (s.name === label || s.url === label) ? 4 : 0) + (want && c.surface === want ? 2 : 0) +
        (s.enabled !== false ? 1 : 0);
      if (r > rank) { best = c; rank = r; }
    }
    return best;
  }
  // คำตอบของ S1 → {state:"ok", review, action, expiresIn} | {state:"fail", why, code, transient}
  // why: token (ไม่มี/หมดอายุ/ใช้แล้ว) · notoken (รหัสผิดรูป) · project (ของโปรเจกต์อื่น — เผื่อไว้ S1 ตอบรวมกับ token)
  //      · auth (401/403) · busy (429) · network (ไม่ตอบ/5xx)
  //      · old (เซิร์ฟเวอร์รุ่นที่ยังไม่มี /review) · bad (อ่านไม่ออก) — code = รหัสเหตุผลสั้นๆ ของเซิร์ฟเวอร์ (ข้อความยาวไม่เอา)
  function srvParse(status, text) {
    var j = null;
    if (typeof text === "string" && text.length <= SRV_MAX_BODY) { try { j = JSON.parse(text); } catch (e) { j = null; } }
    if (!j || typeof j !== "object" || Array.isArray(j)) j = null;
    if (status === 200 && j && j.ok === true && j.pending === true && typeof j.review === "string" && j.review.trim()) {
      var ex = Number(j.expires_in_s);
      return { state: "ok", review: j.review, action: typeof j.action === "string" ? j.action.slice(0, 40) : "",
        expiresIn: isFinite(ex) && ex > 0 ? ex : 0 };
    }
    var code = j ? (typeof j.reason === "string" ? j.reason : typeof j.error === "string" ? j.error : "") : "";
    if (!/^[A-Za-z0-9_.:-]{1,48}$/.test(code)) code = "";
    var f = function (why, transient) { return { state: "fail", why: why, code: code, transient: !!transient }; };
    if (status === 429) return f("busy", true);
    if (status === 401 || status === 403) return f("auth");
    if (!status || status >= 500) return f("network", true);
    // S1: 404 not_pending (ไม่มี/หมดอายุ/ใช้แล้ว/ของโปรเจกต์อื่น — ตอบเหมือนกันโดยตั้งใจ) · 400 missing_token/bad_token
    if (j && j.ok === false) return f(/^(?:missing|bad)_token$/.test(code) ? "notoken" : /project/i.test(code) ? "project" : "token");
    // เซิร์ฟเวอร์รุ่นก่อน S1 ตอบ GET ทุก path ด้วย JSON สถานะ (ไม่มีคีย์ ok) หรือ 404/405
    if ((j && !hasOwn(j, "ok")) || status === 404 || status === 405) return f("old");
    return f("bad");
  }
  // GET /review/<slug>?token=… → Promise ของผล srvParse (ไม่ reject) · ไม่มีค่าตั้ง = ไม่ส่งอะไรเลย
  function srvReviewGet(cfg, tok) {
    return new Promise(function (resolve) {
      var done = false, ctl = null, timer = 0;
      function fin(v) {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve(v);
      }
      if (!cfg) { fin({ state: "fail", why: "config", code: "", transient: false }); return; }
      if (typeof window.fetch !== "function") { fin({ state: "fail", why: "network", code: "", transient: false }); return; }
      try { ctl = new AbortController(); } catch (e) { ctl = null; }
      timer = setTimeout(function () {
        try { if (ctl) ctl.abort(); } catch (e) {}
        fin({ state: "fail", why: "network", code: "", transient: true });
      }, SRV_TIMEOUT_MS);
      var url = cfg.base + "/review/" + cfg.slug + "?token=" + encodeURIComponent(tok);
      var opt = { method: "GET", headers: { "Authorization": cfg.auth, "Accept": "application/json" }, mode: "cors",
        credentials: "omit", cache: "no-store", redirect: "error", referrerPolicy: "no-referrer" };
      if (ctl) opt.signal = ctl.signal;
      try {
        window.fetch(url, opt).then(function (res) {
          return res.text().then(function (t) { fin(srvParse(res.status, t)); });
        }).catch(function () { fin({ state: "fail", why: "network", code: "", transient: true }); });
      } catch (e) { fin({ state: "fail", why: "network", code: "", transient: true }); }
    });
  }

  /* ======================================================================================
     รอบ 4 (2026-09-30) — สัญญา K5-K9: แจ้งเตือน · ชิปโมเดลเร็ว · เปิดในแผง · อ่านออกเสียง · ถามเรื่องนี้
     ทุกส่วนเรียกจาก extrasPass() ท้าย pass() และห่อ try แยกกัน ส่วนที่ต้องพึ่ง shell (notify, openArtifact,
     ข้อมูลโมเดลของโปรเจกต์) ไม่แสดง/ไม่ทำอะไรเมื่อ shell ยังไม่มีฟังก์ชันนั้น — หน้าแชตต้องไม่พังเพราะอีกฝั่งยังไม่เสร็จ
     ====================================================================================== */

  // ข้อความที่ไม่ได้อยู่ใน DOM (การแจ้งเตือน ชื่อ artifact สำรอง) แปลจากพจนานุกรมเดียวกับ UI
  // ตัด U+2060 ทิ้ง: word joiner มีไว้กันตัดบรรทัดในหน้าจอ ไม่ควรติดไปกับข้อความแจ้งเตือนของระบบปฏิบัติการ
  function tx(en) {
    if (lang() !== "th") return en;
    var t = thOf(txKey(en));
    return t == null ? en : t.replace(/⁠/g, "");
  }
  function clip(s, n) {
    s = String(s || "").replace(/\s+/g, " ").trim();
    return s.length > n ? s.slice(0, n - 1).trim() + "…" : s;
  }
  // ไอคอนเส้นเรียบแบบเดียวกับชิป (วาดเอง) — ขนาด/สีคุมจาก CSS ผ่าน currentColor
  var XICON = {
    bolt: '<path d="M13.2 3 5 13.4h6.1L10.8 21 19 10.6h-6.1L13.2 3Z"/>',
    panel: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M14.5 4.5v15"/><path d="m8 9.5 2.5 2.5L8 14.5"/>',
    speak: '<path d="M11 5.5 6.5 9H3.5v6h3l4.5 3.5v-13Z"/><path d="M15.2 9a4.2 4.2 0 0 1 0 6"/><path d="M18 6.5a8 8 0 0 1 0 11"/>',
    pause: '<path d="M8.5 5.5v13"/><path d="M15.5 5.5v13"/>',
    play: '<path d="M8 5.2v13.6L19 12 8 5.2Z"/>',
    stop: '<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>',
    quote: '<path d="M20.5 14.5a2 2 0 0 1-2 2H8l-4.5 4v-15a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2v9Z"/>' +
      '<path d="M8.5 11.5c1 0 1.7-.7 1.7-1.7V7.8H8.2"/><path d="M13.8 11.5c1 0 1.7-.7 1.7-1.7V7.8h-2"/>',
    review: '<path d="M2.5 12s3.4-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.4 6.5-9.5 6.5S2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.8"/>'
  };
  function xIcon(name) {
    return '<svg class="qw-x-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' +
      (XICON[name] || "") + "</svg>";
  }
  // ปุ่มไอคอนล้วน: ชื่อ (aria-label) + tooltip (title) เป็นอังกฤษ ตัวแปลให้ชื่อไทยผ่าน aria-labelledby/title เอง
  function xButton(cls, label, icon) {
    var b = el("button", cls);
    b.type = "button";
    setXLabel(b, label);
    b.innerHTML = xIcon(icon);
    return b;
  }
  // เทียบกับต้นฉบับอังกฤษ (โหมดไทยถูกแปลไปแล้ว) — เขียนเฉพาะเมื่อเปลี่ยนจริง ไม่งั้น observer วนไม่จบ
  function setXLabel(b, label) {
    if (enAttr(b, "title") !== label) b.setAttribute("title", label);
    if (b.getAttribute("aria-label") !== label) b.setAttribute("aria-label", label);
  }
  function shellToast(msg, bad) {
    var api = shellApi();
    if (api && typeof api.toast === "function") { try { api.toast(msg, !!bad); return true; } catch (e) {} }
    return false;
  }
  function lastAssistant() {
    var ms = document.querySelectorAll(".chat-message-assistant");
    return ms.length ? ms[ms.length - 1] : null;
  }

  /* ---- K5: แจ้งเตือนเมื่อคำตอบจบ / รออนุญาตใช้เครื่องมือ / ถึงรอบเอเจนต์สูงสุด ------------------------ */
  // โมเดลหลักตอบ ~1.3 โทเค็น/วิ ผู้ใช้จึงสลับไปทำอย่างอื่นระหว่างรอ — shell เป็นคนตัดสินว่าจะเด้งการแจ้งเตือนหรือไม่
  // (เฉพาะแท็บถูกซ่อน + ผู้ใช้เปิดไว้) ที่นี่แค่บอกว่า "เกิดอะไรขึ้น" ครั้งเดียวต่อเหตุการณ์
  // การ์ดขออนุญาตและการ์ด "ถึงรอบเอเจนต์สูงสุด" ของ WebUI เป็นคอมโพเนนต์เดียวกัน (my-2 rounded-lg border bg-card p-3)
  // แยกชนิดจากข้อความต้นฉบับอังกฤษ (enText — โหมดไทยถูกแปลแล้ว)
  var PROMPT_SEL = ".chat-messages div.rounded-lg.border.bg-card.p-3";
  var promptSeen = new WeakSet(), promptAt = {}, promptTimer = 0;
  var streamStartAt = 0, userStopAt = 0;
  function chatName() {
    var m = /^([\s\S]*) - llama-ui$/.exec(document.title || "");
    return m && m[1] && m[1] !== "Chat" ? m[1] : "";
  }
  // chatId ส่งมาเองได้ (คำตอบจบ: อ่านข้อความจาก IndexedDB แบบ async ระหว่างนั้นผู้ใช้อาจเปลี่ยนแชตไปแล้ว)
  function notifyShell(kind, title, body, chatId) {
    var id = chatId === undefined ? route().id : chatId;
    return callShell("notify", {
      kind: kind, title: title, body: body || "", chatId: id || null,
      // tag เดียวกัน = แทนการแจ้งเตือนเก่าของแชตเดียวกัน (ไม่กองเป็นตั้ง)
      tag: "qwen-" + kind + "-" + (id || "start")
    });
  }
  // ป้ายต้นฉบับ หรือคำแปลไทยของมัน (node ที่ถูกคัดลอกหลังแปลแล้วไม่มีต้นฉบับใน txOrig ให้ enText อ่าน)
  function hasLabel(t, en) {
    return t.indexOf(en) >= 0 || (hasOwn(TH, en) && !!TH[en] && t.indexOf(TH[en].replace(/\s+/g, " ")) >= 0);
  }
  // อ่านเฉพาะแถวข้อความ (ลูกตัวแรก) กับแถวปุ่ม (ลูกตัวสุดท้าย) ไม่ใช่ทั้งการ์ด: กล่องตรวจทานของ local_confirm (R4)
  // อยู่ในการ์ดเดียวกันและเนื้อหาเป็นข้อความที่โมเดลกำหนดได้ ถ้าในโค้ดมีคำว่า "Agentic turn limit reached. Continue?"
  // การ์ดจะถูกนับเป็นอีกชนิด แล้วกล่องตรวจทานถูกถอดออก — คนจะกดอนุญาตโดยไม่เห็นสิ่งที่จะรัน
  function promptInfo(card) {
    var kids = card.children, head = kids[0], acts = kids.length > 1 ? kids[kids.length - 1] : null;
    if (!head) return null;
    var t = enText(head).replace(/\s+/g, " ");
    if (hasLabel(t, "Agentic turn limit reached. Continue?")) return { kind: "continue" };
    if (hasLabel(t, "Allow use of") ||
        acts && acts.querySelector("button") && hasLabel(enText(acts).replace(/\s+/g, " "), "Allow once")) {
      // "Allow use of <b>เครื่องมือ</b> from <b>เซิร์ฟเวอร์</b>?" — S3 ใช้ชื่อเซิร์ฟเวอร์เลือกว่าจะถาม review จาก entry ไหน
      var ns = head.querySelectorAll(".font-semibold"), n = ns[0];
      return { kind: "permission", tool: n ? enText(n).trim() : "",
        server: ns.length > 1 ? enText(ns[ns.length - 1]).trim() : "" };
    }
    return null;
  }
  function promptPending() {
    var cs = document.querySelectorAll(PROMPT_SEL);
    for (var i = 0; i < cs.length; i++) if (promptInfo(cs[i])) return true;
    return false;
  }
  function scanPrompts() {
    promptTimer = 0;
    try { confirmCards(); } catch (e) { /* กล่องตรวจทานพังรอบเดียว ต้องไม่ทำให้การแจ้งเตือนหาย */ }
    try { cfBadgeScan(); } catch (e) { /* ป้ายผลของ local_confirm ไม่มี = หน้าตาแบบเดิม ไม่กระทบส่วนอื่น */ }
    var cs = document.querySelectorAll(PROMPT_SEL);
    for (var i = 0; i < cs.length; i++) {
      var c = cs[i];
      if (promptSeen.has(c)) continue;
      var info = promptInfo(c);
      if (!info) continue;
      promptSeen.add(c);
      // Svelte วาดการ์ดเดิมใหม่ได้ (เปลี่ยนแชตไปกลับ) — การ์ดชนิดเดียวกันของแชต/เครื่องมือเดียวกันภายใน 15 วิ ไม่แจ้งซ้ำ
      var key = info.kind + "|" + (route().id || "") + "|" + (info.tool || ""), now = Date.now();
      if (promptAt[key] && now - promptAt[key] < 15000) continue;
      promptAt[key] = now;
      var name = chatName();
      if (info.kind === "permission") {
        notifyShell("permission", tx("Tool permission needed") + (name ? " · " + name : ""),
          tx("Allow use of") + " " + (info.tool || "?") + "?");
      } else {
        notifyShell("continue", tx("Agentic turn limit reached") + (name ? " · " + name : ""),
          tx("Press Continue to keep going, or Stop."));
      }
    }
  }
  // ถูกเรียกทุกชุดที่โครงสร้างเปลี่ยน รวมระหว่างสตรีม — throttle (ไม่ใช่ debounce ที่ไม่มีวันถึงตอนโทเค็นไหลต่อเนื่อง)
  function promptScanSoon() {
    if (!promptTimer) promptTimer = setTimeout(function () { try { scanPrompts(); } catch (e) { promptTimer = 0; } }, 300);
  }

  /* ---- R4 (รอบ 5, 2026-09-30): การ์ดอนุญาต local_confirm แสดง "สิ่งที่จะรันจริง" -----------------------------
     ปัญหา: การ์ด "Allow use of local_confirm from …?" ของ WebUI (oVt ใน bundle b10984) รู้แค่ {serverLabel, toolName}
     อาร์กิวเมนต์อยู่ในบล็อกเครื่องมือด้านบนที่พับไว้ และเป็น JSON ที่ \n ถูก escape อ่านเป็นโค้ดไม่ได้ — คนกดอนุญาตโดยไม่เห็น
     สิ่งที่จะรัน โมเดลที่ถูกเนื้อหาแปลกปลอมหลอกจึงโชว์โค้ดหนึ่งในแชต แล้วยืนยัน token ของอีกโค้ดได้
     ตอนนี้ local_confirm ต้องส่ง review = ข้อความตรวจทานที่เซิร์ฟเวอร์สร้างเอง และเซิร์ฟเวอร์ทำก็ต่อเมื่อ review ตรงกับที่เก็บไว้
     ทุกตัวอักษร — การ์ดจึงต้องโชว์ review "ของคำขอนี้" ให้อ่านได้ครบก่อนคนกด ส่วนนี้ทำแค่นั้น (อ่านอย่างเดียว ไม่กดอะไรแทนคน)
     แหล่งข้อมูล: IndexedDB ของ WebUI ก่อนถามสิทธิ์ WebUI await onAssistantTurnComplete ซึ่งบันทึก toolCalls ของข้อความผู้ช่วย
     (สตริง JSON ชุดเดียวกับที่ parseToolArguments แปลงแล้วส่งให้ MCP) และ currNode เสร็จก่อน; เครื่องมือถูกเรียกทีละตัวและผลของตัว
     ก่อนหน้า (role "tool" + toolCallId, เป็นลูกของข้อความผู้ช่วยตัวเดียวกันทุกตัว) ถูกบันทึกก่อนถามตัวถัดไป → ตัวที่รออนุญาต =
     calls[จำนวนผล] โดยผลตัวที่ i ต้องเป็นของ calls[i] (จับคู่ด้วยตำแหน่ง แก้ 2026-10-01 — ดู confirmCallFromDb)
     หาไม่เจอ/ชื่อไม่ตรงกับการ์ด/id ซ้ำ/ลำดับไม่ตรง = บอกว่าอ่านไม่ได้ ไม่เดา (โชว์ผิดคำขอแย่กว่าไม่โชว์)
     S3 (2026-09-30 ดึก) เปลี่ยนสิ่งที่แสดง: จาก IndexedDB เอาแค่ confirm_token (+ review ของโมเดลไว้เทียบ) แล้วถามเซิร์ฟเวอร์
     (srvReviewGet — ส่วน S3 ก่อนรอบ 4) โค้ดในกล่อง = review ของเซิร์ฟเวอร์เท่านั้น เพราะ review ของโมเดลกลายเป็นทางเลือก
     (S2) และโมเดลเล็กคัดลอกไม่ครบอยู่แล้ว · โหลดไม่ได้ทุกกรณี = แดง "อย่ากดอนุญาต" + ปุ่มอนุญาตจาง (data-qw-rv บนการ์ด)
     · review ของโมเดลไม่ตรงกับของเซิร์ฟเวอร์ = เตือนแดงว่าเซิร์ฟเวอร์จะปฏิเสธ (เทียบแบบ guard.review_matches ทุกประการ) */
  var CONFIRM_TOOL = "local_confirm";
  // รูปแบบ confirm_token ที่ยอมส่งไปถาม = รูปเดียวกับที่ S1 รับ (server._REVIEW_TOKEN_RE; ของจริงคือ hex 8 ตัว)
  // อย่างอื่นไม่ส่งออกไปเลย — local_confirm ของเซิร์ฟเวอร์ก็หา token แบบนั้นไม่เจออยู่แล้ว
  var RV_TOKEN_OK = /^[0-9A-Fa-f]{1,64}$/;
  // ช่องว่างตามนิยามของ Python str.strip()/isspace() (ไม่ใช่ \s ของ JS: JS นับ U+FEFF แต่ไม่นับ U+001C-001F/U+0085)
  // ใช้ตัดแบบเดียวกับเซิร์ฟเวอร์ ทั้ง confirm_token และการตัดสินว่า "ส่ง review มาหรือไม่" (guard.review_provided)
  var PY_WS = "\\t\\n\\x0B\\f\\r\\x1C-\\x1F \\x85\\xA0\\u1680\\u2000-\\u200A\\u2028\\u2029\\u202F\\u205F\\u3000";
  var PY_STRIP_RE = new RegExp("^[" + PY_WS + "]+|[" + PY_WS + "]+$", "g");
  function pyStrip(s) { return String(s).replace(PY_STRIP_RE, ""); }
  // ความจริงแบบ Python (ใช้เลียน `a or b` ของเซิร์ฟเวอร์): ลิสต์/อ็อบเจกต์ว่างเป็นเท็จ ต่างจาก JS
  function pyTruthy(v) {
    if (v && typeof v === "object") return Array.isArray(v) ? v.length > 0 : Object.keys(v).length > 0;
    return !!v;
  }
  // เหตุผลที่โหลดไม่ได้ (why จาก srvParse/srvReviewGet หรือจากการ์ดเอง) → ข้อความ (อังกฤษลง DOM ตัวแปลแปลให้)
  var RV_WHY = {
    token: "The server has no pending request for this confirm code — it expired, was already used, or never existed.",
    project: "This confirm code belongs to another project.",
    expired: "This confirm code has expired.",
    auth: "The local tool server refused this page's request.",
    network: "The local tool server didn't answer.",
    busy: "The local tool server is busy.",
    old: "The local tool server can't show request details yet (it needs an update).",
    bad: "The server's answer couldn't be read.",
    config: "This page has no local tool server set up.",
    notoken: "This request has no valid confirm code.",
    missing: "Couldn't find this request in the chat.",
    badargs: "This request's arguments aren't valid JSON. Choose Deny."
  };
  // ข้อความตรวจทานจริงสั้นกว่านี้มาก (เพดานของเซิร์ฟเวอร์ 48,000 ตัวอักษร) เกินนี้คือของปลอม — วาดเท่านี้ไม่ให้แท็บค้าง
  var RV_RENDER_MAX = 1000000;
  // ช่องว่างติดกันยาวขนาดนี้ไม่มีในโค้ดปกติ แต่ใช้ดันโค้ดให้หลุดขอบจอได้ — ระบายสีให้เห็น (เซิร์ฟเวอร์ย่อเป็น «N spaces»
  // ตั้งแต่ 32 ตัวอยู่แล้ว ข้อนี้เผื่อ review ที่ไม่ได้มาจากเซิร์ฟเวอร์)
  var RV_WS_RUN = 32;
  // อักขระที่มองไม่เห็นหรือทำให้ลำดับที่ตาเห็นต่างจากลำดับที่โปรแกรมอ่าน (Trojan Source, CVE-2021-42574): ตัวควบคุม C0/C1
  // (ยกเว้น tab), ตัวจัดรูปแบบทั้งหมด Cf (ตัวกำหนดทิศทาง U+202A-202E/2066-2069, ความกว้างศูนย์ U+200B-200F/2060, BOM,
  // soft hyphen, แท็ก), ตัวคั่นบรรทัด/ย่อหน้าของ Unicode, ช่องว่างแบบอื่นที่หน้าตาเหมือนเว้นวรรค, surrogate ไม่มีคู่,
  // private use/ยังไม่กำหนด, ตัวเลือกรูปแบบ (variation selector), ตัวเติมฮันกึล/เบรลล์ว่างที่มองไม่เห็น — ชุดเดียวกับ
  // guard._review_hidden ของ MCP เซิร์ฟเวอร์แปลงให้แล้ว (review ที่ตรงกับของเซิร์ฟเวอร์จึงไม่มีตัวดิบ) ที่นี่เป็นชั้นที่สอง:
  // ข้อความในอาร์กิวเมนต์มาจากโมเดล ถ้ามีตัวดิบปนมา (ซึ่งเซิร์ฟเวอร์จะปฏิเสธ) หน้าจอก็ต้องไม่หลอกตา
  // \p{…} ต้องใช้ธง u (Edge/Chromium ที่ใช้อยู่รองรับ) สร้างผ่าน RegExp ใน try เพื่อให้ไฟล์ยัง parse ได้ในเอนจินเก่า
  // กลุ่ม: 1 ตัวดิบ · 2 «U+XXXX» ของเซิร์ฟเวอร์ · 3 ↩/↪ จุดตัดบรรทัดของเซิร์ฟเวอร์ · 4 «TAB»/«N spaces» · 5 ช่องว่างยาวดิบ
  // U+180B-180D/180F (ตัวเลือกรูปแบบอิสระของมองโกเลีย) เป็นหมวด Mn ไม่ใช่ Cf — \p{Cf} ไม่ครอบ จึงใส่ทั้งช่วง 180B-180F เอง
  // ให้ตรงกับ guard._review_hidden ของเซิร์ฟเวอร์ (ตัวสำรองด้านล่างมีช่วงนี้อยู่แล้ว)
  var RV_TOKEN = (function () {
    var tail = "|(«U\\+[0-9A-Fa-f]{4,6}»)|([↩↪])|(«TAB»|«\\d+ spaces»)|( {" + RV_WS_RUN + ",})";
    try {
      return new RegExp("((?![\\t ])[\\p{Cc}\\p{Cf}\\p{Cs}\\p{Co}\\p{Cn}\\p{Zl}\\p{Zp}\\p{Zs}\\u034F\\u115F\\u1160" +
        "\\u17B4\\u17B5\\u180B-\\u180F\\u2800\\u3164\\uFE00-\\uFE0F\\uFFA0\\u{E0100}-\\u{E01EF}])" + tail, "gu");
    } catch (e) {
      return new RegExp("([\\x00-\\x08\\x0B-\\x1F\\x7F-\\xA0\\xAD\\u034F\\u061C\\u115F\\u1160\\u1680\\u17B4\\u17B5" +
        "\\u180B-\\u180F\\u2000-\\u200F\\u2028-\\u202F\\u205F-\\u206F\\u2800\\u3000\\u3164\\uE000-\\uF8FF" +
        "\\uFE00-\\uFE0F\\uFEFF\\uFFA0\\uFFF9-\\uFFFB\\uD800-\\uDFFF])" + tail, "g");
    }
  })();
  // ชื่อสั้นของตัวที่พบบ่อย (tooltip ของ «U+…») — ชื่อทางเทคนิคเป็นอังกฤษทั้งสองภาษา เหมือนชื่อพารามิเตอร์อื่น
  var RV_NAMES = { "00A0": "NO-BREAK SPACE", "00AD": "SOFT HYPHEN", "061C": "ARABIC LETTER MARK",
    "200B": "ZERO WIDTH SPACE", "200C": "ZERO WIDTH NON-JOINER", "200D": "ZERO WIDTH JOINER",
    "200E": "LEFT-TO-RIGHT MARK", "200F": "RIGHT-TO-LEFT MARK", "2028": "LINE SEPARATOR", "2029": "PARAGRAPH SEPARATOR",
    "202A": "LEFT-TO-RIGHT EMBEDDING", "202B": "RIGHT-TO-LEFT EMBEDDING", "202C": "POP DIRECTIONAL FORMATTING",
    "202D": "LEFT-TO-RIGHT OVERRIDE", "202E": "RIGHT-TO-LEFT OVERRIDE", "2060": "WORD JOINER",
    "2066": "LEFT-TO-RIGHT ISOLATE", "2067": "RIGHT-TO-LEFT ISOLATE", "2068": "FIRST STRONG ISOLATE",
    "2069": "POP DIRECTIONAL ISOLATE", "FEFF": "ZERO WIDTH NO-BREAK SPACE (BOM)" };
  var RV_HUNK = /^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@/m;
  var rvSeq = 0, rvTimer = 0;

  function rvHex(ch) {
    var cp = ch.codePointAt ? ch.codePointAt(0) : ch.charCodeAt(0), h = cp.toString(16).toUpperCase();
    return h.length < 4 ? ("0000" + h).slice(-4) : h;
  }
  function rvEscText(hx) { return "«U+" + hx + "»"; }
  // เขียนข้อความหนึ่งบรรทัดลง parent เป็น text node ล้วน (ห้ามแปลงเป็น HTML เด็ดขาด — ข้อความมาจากอาร์กิวเมนต์ที่โมเดลเขียน)
  // คืนจำนวนอักขระซ่อนที่พบ (ทั้งตัวจริงที่เราแปลงเอง และ «U+…» ที่เซิร์ฟเวอร์แปลงมาแล้ว)
  function rvAppend(parent, s) {
    var n = 0, last = 0, m;
    RV_TOKEN.lastIndex = 0;
    while ((m = RV_TOKEN.exec(s))) {
      if (m.index > last) parent.appendChild(document.createTextNode(s.slice(last, m.index)));
      var sp;
      if (m[1]) {
        // รหัสแบบเดียวกับที่เซิร์ฟเวอร์แสดง «U+XXXX» (ไม่ใช่ป้าย UI — ไม่แปล)
        var hx = rvHex(m[1]);
        sp = el("span", "qw-rv-esc");
        sp.textContent = rvEscText(hx);
        sp.title = "U+" + hx + (RV_NAMES[hx] ? " " + RV_NAMES[hx] : "");
        n++;
      } else if (m[2]) {
        sp = el("span", "qw-rv-esc");
        sp.textContent = m[2];
        n++;
      } else if (m[3]) {
        sp = el("span", "qw-rv-wrap");
        sp.textContent = m[3];
      } else if (m[4]) {
        sp = el("span", "qw-rv-mark");
        sp.textContent = m[4];
      } else {
        sp = el("span", "qw-rv-ws");
        sp.textContent = m[5];
        sp.title = m[5].length + " spaces";
      }
      parent.appendChild(sp);
      last = RV_TOKEN.lastIndex;
    }
    if (last < s.length) parent.appendChild(document.createTextNode(s.slice(last)));
    return n;
  }
  // วาดข้อความตรวจทานทั้งหมด (ไม่ตัด) หนึ่งบรรทัดของข้อความ = หนึ่ง span แบบ block มีย่อหน้าแขวน: ส่วนที่เบราว์เซอร์
  // ตัดขึ้นบรรทัดใหม่เอง (กล่องแคบ) จะเยื้องเข้าไป แยกออกจากบรรทัดจริงได้ด้วยตา; จุดที่เซิร์ฟเวอร์ตัดเองมี ↩ ท้าย/↪ หัว
  // เนื้อหาที่เซิร์ฟเวอร์ใส่เลข "12│ " ไว้หน้าแต่ละบรรทัด (กันเนื้อหาปลอมบรรทัดหัว/ท้ายของ review) — หรี่เลขให้โค้ดเด่น
  // บรรทัดคำเตือน "⚠ …" ของเซิร์ฟเวอร์ระบายสีเตือน · diff (มีหัว @@ จริง) ระบายพื้น +/- · ตัวอักษรยังเป็นตัวเดิมทุกตัว
  function rvCode(text) {
    var pre = el("pre", "qw-review-code");
    pre.setAttribute("data-qw-no-tx", "");            // ห้ามตัวแปลแตะ: คำว่า "Deny" ในโค้ดต้องเป็น "Deny"
    pre.setAttribute("tabindex", "0");                  // เลื่อนด้วยแป้นพิมพ์ได้
    var lines = text.split("\n"), diff = RV_HUNK.test(text), hidden = 0, num = 0;
    for (var i = 0; i < lines.length; i++) {
      var s = lines[i], ln = el("span", "qw-rv-l"), nm = /^( *\d+│ ?)/.exec(s);
      if (/^↪/.test(s)) ln.classList.add("qw-rv-cont");
      else num++;
      if (/^⚠/.test(s)) ln.classList.add("qw-rv-warnline");
      if (diff && !nm) {
        if (/^\+(?!\+\+)/.test(s)) ln.classList.add("qw-rv-add");
        else if (/^-(?!--)/.test(s)) ln.classList.add("qw-rv-del");
        else if (/^@@ /.test(s)) ln.classList.add("qw-rv-hunk");
      }
      if (nm) {
        var g = el("span", "qw-rv-ln");
        g.textContent = nm[1];
        ln.appendChild(g);
        s = s.slice(nm[1].length);
      }
      hidden += rvAppend(ln, s);
      if (i < lines.length - 1) ln.appendChild(document.createTextNode("\n"));   // คัดลอกออกไปได้ครบทุกบรรทัด
      pre.appendChild(ln);
    }
    return { node: pre, hidden: hidden, lines: num };
  }
  function rvNote(kind, text) {
    var d = el("div", "qw-review-note");
    d.setAttribute("data-kind", kind);
    d.textContent = text;
    return d;
  }
  function rvBox() {
    var id = "qw-rv-" + (++rvSeq);
    var box = el("div", "qw-review");
    box.setAttribute("role", "group");
    box.setAttribute("aria-labelledby", id + "-cap");
    var head = el("div", "qw-review-head");
    head.innerHTML = xIcon("review");                 // svg คงที่ของเราเอง
    var cap = el("span", "qw-review-cap");
    cap.id = id + "-cap";
    // S3: โค้ดในกล่องมาจากเซิร์ฟเวอร์เสมอ — หัวกล่องบอกแหล่งที่มาด้วย (คนจะได้ไม่เทียบกับข้อความที่โมเดลพิมพ์ในแชต)
    cap.textContent = "Review this before you allow it — this is exactly what will run (from the server)";
    head.appendChild(cap);
    box.appendChild(head);
    box.__qwBody = box.appendChild(el("div", "qw-review-body"));
    box.__qwId = id;
    return box;
  }
  // confirm_token ที่ส่งไปถามเซิร์ฟเวอร์ได้ ("" = ไม่มี/รูปแบบผิด) — เลียน server._confirm_call ทุกประการ:
  // str(args.get("confirm_token") or args.get("token") or "").strip() (ตัวที่การ์ดโชว์ต้องเป็นตัวที่เซิร์ฟเวอร์จะใช้จริง)
  // ตัวเลขเต็มที่โมเดลเขียนเป็น number ก็รับ (str ของ Python = String ของ JS สำหรับจำนวนเต็ม) ชนิดอื่นไม่รับ
  function rvToken(a) {
    if (!a) return "";
    var t = pyTruthy(a.confirm_token) ? a.confirm_token : a.token;
    t = typeof t === "string" ? pyStrip(t) : typeof t === "number" && Number.isSafeInteger(t) && t ? String(t) : "";
    return RV_TOKEN_OK.test(t) ? t : "";
  }
  // S2: review ของโมเดลเป็นทางเลือก — ถ้าส่งมา เซิร์ฟเวอร์เทียบด้วย guard.review_matches (ไม่ตรง = ปฏิเสธ ไม่มีอะไรรัน)
  // เทียบแบบเดียวกันทุกประการ (rvNormalize = guard._review_norm: ช่องว่างที่ตัดต้องอยู่ในขอบเขต และรูปที่เทียบต้องเท่ากัน)
  // เพื่อบอกคนก่อนกด · "ส่งมาหรือไม่" = guard.review_provided: ไม่มีคีย์/null/สตริงที่มีแต่ช่องว่าง = ไม่ได้ส่ง
  // (เซิร์ฟเวอร์ใช้ token อย่างเดียว) · ชนิดอื่นทุกแบบ = ส่งมาและไม่ตรงแน่นอน
  function rvModelDiffers(given, stored) {
    if (given == null || (typeof given === "string" && !pyStrip(given))) return false;
    if (typeof given !== "string") return true;
    var want = rvNormalize(stored).text, got = rvNormalize(given);
    return !(want && got.ok && got.text === want);
  }
  // แถว "รหัสยืนยัน <token>" — รหัสมาจากอาร์กิวเมนต์ของโมเดล จึงผ่าน rvAppend (อักขระซ่อนถูกแปลงให้เห็น)
  function rvMeta(tok) {
    var meta = el("div", "qw-review-meta");
    if (tok) {
      var tw = el("span", "qw-review-tok"), tl = el("span"), tc = el("code");
      tl.textContent = "Confirm code";
      tc.setAttribute("data-qw-no-tx", "");
      rvAppend(tc, String(tok).slice(0, 80));
      tw.appendChild(tl);
      tw.appendChild(document.createTextNode(" "));
      tw.appendChild(tc);
      meta.appendChild(tw);
    }
    return meta;
  }
  // โหลดไม่ได้: หัวข้อแดง "อย่ากดอนุญาต" + เหตุผล (+ รหัสเหตุผลของเซิร์ฟเวอร์เป็น code แยก เพื่อให้ตัวแปลจับคู่ประโยคได้ตรงตัว)
  function rvFailNotes(body, why, code, retry) {
    body.appendChild(rvNote("stop", "Could not load details — do not allow"));
    var d = rvNote("reason", why);
    if (code) {
      var c = el("code", "qw-review-why");
      c.setAttribute("data-qw-no-tx", "");
      c.textContent = code;
      d.appendChild(document.createTextNode(" "));
      d.appendChild(c);
    }
    body.appendChild(d);
    if (retry) body.appendChild(rvNote("label", "Trying again..."));
  }
  // r = ผลจาก IndexedDB {status: loading|ok|badargs|unknown, args?, raw?, callId?} · st.srv = ผลจากเซิร์ฟเวอร์ของ token นั้น
  // มุมมอง (data-qw-rv บนการ์ด): loading · ok (review ของเซิร์ฟเวอร์) · fail (แดง + ปุ่มอนุญาตจาง)
  function rvShow(st, r) {
    // ได้คำขอที่อ่านออกแล้ว อย่าถอยเป็น "อ่านไม่ได้" ตอนตรวจซ้ำ (ช่วงสั้นๆ หลังกดที่ผลถูกบันทึกแต่การ์ดยังไม่หาย)
    if (r.status === "unknown" && st.good) return false;
    var a = r.status === "ok" ? (r.args || {}) : null, tok = a ? rvToken(a) : "";
    var srv = tok && st.srv && st.srv.tok === tok ? st.srv : null;
    var key = [r.status, r.callId || "", r.raw || "", srv ? [srv.state, srv.why || "", srv.code || "",
      srv.retry ? 1 : 0, srv.review || ""].join("\u0001") : ""].join("\u0000");
    if (key === st.key) return false;
    st.key = key;
    if (r.status === "ok" || r.status === "badargs") st.good = true;
    var body = st.box.__qwBody;
    while (body.firstChild) body.removeChild(body.firstChild);
    st.box.__qwLines = null;
    var view = r.status === "loading" || (tok && (!srv || srv.state === "loading")) ? "loading"
      : srv && srv.state === "ok" ? "ok" : "fail";
    st.box.setAttribute("data-state", view);
    if (st.card) st.card.setAttribute("data-qw-rv", view);
    if (view === "loading") {
      body.appendChild(rvNote("info", "Loading what will run..."));
      return true;
    }
    if (view === "fail") {
      var why = r.status === "unknown" ? RV_WHY.missing : r.status === "badargs" ? RV_WHY.badargs
        : !tok ? RV_WHY.notoken : RV_WHY[srv.why] || RV_WHY.bad;
      if (tok) body.appendChild(rvMeta(tok));
      rvFailNotes(body, why, srv ? srv.code : "", !!(srv && srv.retry));
      // สิ่งที่โมเดลส่งมาเมื่ออ่าน token ไม่ได้ — ให้คนเห็นว่าเกิดอะไร (ข้อความของโมเดล ไม่ใช่สิ่งที่จะรัน)
      if (r.status === "badargs" || (a && !tok)) {
        var raw = String(r.raw || "");
        if (a) { try { raw = JSON.stringify(a, null, 2); } catch (e) {} }
        body.appendChild(rvNote("label", "Arguments sent by the model:"));
        body.appendChild(rvCode(String(raw).slice(0, RV_RENDER_MAX)).node);
      }
      return true;
    }
    // review ของเซิร์ฟเวอร์ = สร้างและ escape อักขระซ่อนมาแล้ว ไม่มีช่องว่างเติม — ยังผ่าน rvNormalize/rvCode เหมือนเดิม
    // (ตัดขอบว่างแบบเดียวกับที่เซิร์ฟเวอร์เทียบ + ชั้นที่สองของการแปลงอักขระซ่อน) ข้อความไม่ถูกตัดความยาว
    var text = rvNormalize(srv.review).text, big = text.length > RV_RENDER_MAX;
    var code = rvCode(big ? text.slice(0, RV_RENDER_MAX) : text), meta = rvMeta(tok);
    // บอกว่ามีต่อข้างล่างเฉพาะตอนล้นกล่องจริง (rvFit วัดหลังวางลงหน้า) — จำนวนบรรทัดของข้อความตรวจทาน ไม่ใช่ของโค้ด
    var lc = el("span", "qw-review-lines");
    lc.hidden = true;
    lc.textContent = code.lines + " lines — scroll to read them all";
    meta.appendChild(lc);
    st.box.__qwLines = lc;
    body.appendChild(meta);
    if (rvModelDiffers(a.review, srv.review)) {
      body.appendChild(rvNote("danger", "The review the model sent differs from the server's version below. The server will refuse it, so allowing runs nothing."));
    }
    if (code.hidden) body.appendChild(rvNote("warn", "Hidden or look-alike characters are shown as «U+XXXX». Don't allow unless you expected them."));
    body.appendChild(code.node);
    return true;
  }
  // รูปที่ใช้เทียบของเซิร์ฟเวอร์ (mcp-local guard._review_norm / normalize_review) ทุกประการ: \r\n → \n,
  // ตัด " \t\r" ท้ายทุกบรรทัด, ตัดบรรทัดว่างหัว/ท้ายทั้งก้อน, ตัด " \t" หน้าบรรทัดแรกของทั้งก้อน — ไม่แตะอย่างอื่นเลย
  // ok = ช่องว่างที่ตัดอยู่ในขอบเขตที่เซิร์ฟเวอร์ยอม (เกิน = review_matches เป็นเท็จ เซิร์ฟเวอร์ปฏิเสธ ไม่มีอะไรรัน)
  // ค่าขอบเขตต้องเท่ากับ guard.REVIEW_PAD_MAX / REVIEW_BLANK_MAX (เทสต์เทียบกับฟังก์ชันจริงของเซิร์ฟเวอร์)
  // ตัดท้ายบรรทัดด้วยลูป ไม่ใช้ /[ \t\r]+$/ (ช่องว่างยาวกลางบรรทัดทำให้ regex นั้นช้าแบบกำลังสอง)
  var RV_PAD_MAX = 4, RV_BLANK_MAX = 3;
  function rvNormalize(s) {
    var lines = String(s == null ? "" : s).replace(/\r\n/g, "\n").split("\n"), ws = 0, ok = true;
    for (var i = 0; i < lines.length; i++) {
      var ln = lines[i], e = ln.length;
      while (e > 0) {
        var c = ln.charCodeAt(e - 1);
        if (c === 32 || c === 9 || c === 13) e--; else break;
      }
      if (ln.length - e > ws) ws = ln.length - e;
      if (ln.length - e > RV_PAD_MAX) ok = false;
      if (e < ln.length) lines[i] = ln.slice(0, e);
    }
    var a = 0, b = lines.length;
    while (b > a && !lines[b - 1]) b--;
    while (a < b && !lines[a]) a++;
    var lead = a, trail = lines.length - b, out = lines.slice(a, b);
    if (lead > RV_BLANK_MAX || trail > RV_BLANK_MAX + 1) ok = false;       // +1 = บรรทัดหลัง \n ปิดท้าย
    if (out.length) {
      var f = out[0], k = 0;
      while (k < f.length && (f.charCodeAt(k) === 32 || f.charCodeAt(k) === 9)) k++;
      if (k > RV_PAD_MAX) ok = false;
      if (k) out[0] = f.slice(k);
    }
    return { text: out.join("\n"), lead: lead, trail: trail, ws: ws, ok: ok };
  }
  function rvPadded(nv) { return !nv.ok; }
  // อ่านอย่างเดียวจาก IndexedDB ของ WebUI (เหมือน replyFromDb): ไม่สร้างฐาน ไม่ถือการเชื่อมต่อค้าง หมดเวลา 3 วินาที
  // แก้ 2026-10-01 (รีวิว S3): ผลของเครื่องมือทุกตัวในเทิร์นเดียวเป็น "ลูก" ของข้อความผู้ช่วยตัวเดียวกัน (createToolResultMessage
  // ของ WebUI ใช้ parent = ข้อความผู้ช่วย ไม่ต่อกันเป็นสาย) เดินจาก currNode ขึ้นไปจึงเห็นแค่ผลตัวล่าสุด — แบบเดิม ("ตัวแรกที่ยัง
  // ไม่มีผล" จากผลที่เห็น) การ์ดของการเรียกตัวที่ 3 ในข้อความเดียวโชว์ review + รหัสของตัวที่ 1 (ที่ถูกปฏิเสธจึงยังค้าง) แต่กด
  // อนุญาตแล้วตัวที่ 3 รัน; id ซ้ำก็ทำให้โชว์ตัวถัดไปผิดตัวแบบเดียวกัน · ตอนนี้จับคู่ด้วย "ตำแหน่ง": WebUI รันทีละตัวตามลำดับ
  // และบันทึกผลหนึ่งอันต่อหนึ่งการเรียกก่อนถามตัวถัดไป → ตัวที่รอ = calls[k] เมื่อ k = จำนวนผล (ลูก role tool ของผู้ช่วย)
  // และ toolCallId ของผลต้องเท่ากับ id ของ calls[0..k-1] ตามลำดับ · อะไรไม่ตรงรูปนี้ = "อ่านไม่ได้" (แดง อย่ากดอนุญาต)
  var RV_MAX_CALLS = 400;
  function confirmCallFromDb(convId, toolName) {
    return new Promise(function (resolve) {
      var db = null, settled = false, req;
      function fin(v) {
        if (settled) return;
        settled = true;
        try { if (db) db.close(); } catch (e) {}
        resolve(v || { status: "unknown" });
      }
      if (!convId || !window.indexedDB) { fin(); return; }
      setTimeout(function () { fin(); }, 3000);
      try { req = indexedDB.open("LlamaUi"); } catch (e) { fin(); return; }
      req.onupgradeneeded = function () { try { req.transaction.abort(); } catch (e) {} };
      req.onerror = req.onblocked = function () { fin(); };
      req.onsuccess = function () {
        db = req.result;
        if (settled) { try { db.close(); } catch (e) {} return; }
        db.onversionchange = function () { fin(); };
        try {
          if (!db.objectStoreNames.contains("conversations") || !db.objectStoreNames.contains("messages")) { fin(); return; }
          var t = db.transaction(["conversations", "messages"], "readonly"), ms = t.objectStore("messages");
          // ms.get โยน DataError ทันทีถ้า key ไม่ใช่ชนิดที่ใช้ได้ (children/parent เพี้ยน) — ต้องจบเป็น "อ่านไม่ได้" ไม่ใช่ค้าง 3 วิ
          var get = function (id, cb) {
            var g;
            if (id == null || id === "") { fin(); return; }
            try { g = ms.get(id); } catch (e) { fin(); return; }
            g.onsuccess = function () { if (g.result) cb(g.result); else fin(); };
            g.onerror = function () { fin(); };
          };
          // ลูกของผู้ช่วย = ผลของการเรียกก่อนหน้าตามลำดับที่บันทึก (addChildToParent ต่อท้ายเสมอ) — ต้องเป็นผลเครื่องมือทุกตัว
          // และ currNode ต้องเป็นลูกตัวท้าย (ยังไม่มีผล = currNode คือผู้ช่วยเองและยังไม่มีลูก) ไม่งั้นไม่ใช่จังหวะ "รออนุญาต"
          var fromAssistant = function (asst, tip) {
            var kids = Array.isArray(asst.children) ? asst.children : [], done = [], seen = {}, i = 0;
            if (tip == null ? kids.length !== 0 : kids[kids.length - 1] !== tip) { fin(); return; }
            if (kids.length > RV_MAX_CALLS) { fin(); return; }
            var next = function () {
              if (i >= kids.length) { fin(pickConfirmCall(asst.toolCalls, done, toolName)); return; }
              var kid = kids[i++];
              if (seen["$" + kid]) { fin(); return; }
              seen["$" + kid] = 1;
              get(kid, function (m) {
                if (m.role !== "tool" || m.parent !== asst.id) { fin(); return; }
                done.push(m.toolCallId);
                next();
              });
            };
            next();
          };
          var c = t.objectStore("conversations").get(convId);
          c.onsuccess = function () {
            get(c.result && c.result.currNode, function (m) {
              if (m.role === "assistant") { fromAssistant(m, null); return; }
              if (m.role !== "tool") { fin(); return; }
              get(m.parent, function (p) {
                if (p.role === "assistant") fromAssistant(p, m.id);
                else fin();
              });
            });
          };
          c.onerror = function () { fin(); };
        } catch (e) { fin(); }
      };
    });
  }
  // done = toolCallId ของผลที่บันทึกแล้วตามลำดับ → ตัวที่รออนุญาต = calls[done.length] และต้องชื่อเดียวกับที่การ์ดถาม
  // (จับคู่ด้วยตำแหน่ง — ดู confirmCallFromDb) · id ของทุกการเรียกต้องเป็นสตริง/ตัวเลขที่ไม่ซ้ำกัน (เทียบเป็นข้อความ: 7 กับ "7"
  // นับว่าซ้ำ) และผลตัวที่ i ต้องเป็นของ calls[i] ทุกตัว: id ซ้ำ = ระบุไม่ได้ว่าผลไหนของใคร (การ์ดเคยโชว์ตัวถัดไปผิดตัว) จึงไม่เดา
  // แปลงอาร์กิวเมนต์แบบเดียวกับ WebUI (trim → ว่าง = {} → JSON.parse)
  function pickConfirmCall(raw, done, toolName) {
    var calls = raw;
    if (typeof raw === "string") {
      try { calls = raw ? JSON.parse(raw) : []; } catch (e) { return null; }
    }
    if (!Array.isArray(calls) || !Array.isArray(done) || done.length >= calls.length) return null;
    var ids = {};
    for (var i = 0; i < calls.length; i++) {
      var id = calls[i] && calls[i].id, key = "$" + id;
      if ((typeof id !== "string" && typeof id !== "number") || ids[key] === 1) return null;
      ids[key] = 1;
      if (i < done.length && done[i] !== id) return null;
    }
    var c = calls[done.length];
    if (!c.function || c.function.name !== toolName) return null;
    var a = c.function.arguments, args;
    var rawStr = typeof a === "string" ? a : JSON.stringify(a == null ? "" : a);
    if (a && typeof a === "object") args = a;
    else {
      var s = String(a == null ? "" : a).trim();
      try { args = s ? JSON.parse(s) : {}; } catch (e) { return { status: "badargs", callId: c.id, raw: rawStr }; }
    }
    if (!args || typeof args !== "object" || Array.isArray(args)) return { status: "badargs", callId: c.id, raw: rawStr };
    return { status: "ok", callId: c.id, args: args, raw: rawStr };
  }
  function rvLoad(card, st, tool) {
    st.busy = true;
    var seq = ++st.seq, conv = route().id;
    confirmCallFromDb(conv, tool).then(function (r) {
      st.busy = false;
      st.at = Date.now();
      if (seq !== st.seq || !card.isConnected || route().id !== conv) return;
      // อ่านออกแล้วครั้งหนึ่ง = ไม่ถอยเป็น "หาไม่เจอ" (ดู rvShow) — เก็บผลที่ดีล่าสุดไว้วาดซ้ำตอนเซิร์ฟเวอร์ตอบ
      if (!(r.status === "unknown" && st.good)) st.r = r;
      rvSrv(card, st);
      rvPaint(card, st);
    }, function () { st.busy = false; st.at = Date.now(); });
  }
  // วาดตาม st.r (IndexedDB) + st.srv (เซิร์ฟเวอร์) — เรียกได้ทั้งตอน IndexedDB ตอบและตอนเซิร์ฟเวอร์ตอบ
  function rvPaint(card, st) {
    var vis = rvVisible(card);
    if (!rvShow(st, st.r || { status: "loading" })) return;
    rvFit(st);
    if (vis && !st.scrolled && st.box.getAttribute("data-state") !== "loading") {
      // การ์ดอยู่ในจออยู่แล้ว (ผู้ใช้อยู่ท้ายแชต): กล่องที่ขยายต้องไม่ดันปุ่มลงไปใต้กล่องพิมพ์ — เลื่อนพอเห็นแถวปุ่ม ครั้งเดียว
      // (รอจนเนื้อหาจริงมา — ตอน "กำลังโหลด" กล่องยังเตี้ย เลื่อนตอนนั้นแล้วปุ่มจะถูกดันลงอีกทีตอน review มาถึง)
      st.scrolled = true;
      var kids = card.children, acts = kids[kids.length - 1];
      if (acts && acts !== st.box) rvReveal(acts);
    }
  }
  // S3: ขอ review ของเซิร์ฟเวอร์ครั้งเดียวต่อ token (endpoint มี rate limit และการ์ดตรวจซ้ำทุก 2 วิ) ลองใหม่เฉพาะที่พลาด
  // ชั่วคราว (ไม่ตอบ/ยุ่ง) สูงสุด 3 ครั้ง เว้น 2/4/8 วิ · review ที่ได้แล้วหมดอายุตาม expires_in_s = เปลี่ยนเป็น "โหลดไม่ได้"
  // (คนที่ทิ้งการ์ดไว้นานแล้วกลับมา ต้องไม่เห็นโค้ดที่กดไปก็ถูกปฏิเสธ) · ผลที่มาช้าของ token เก่า/การ์ดที่หายไปแล้ว = ทิ้ง
  function rvSrv(card, st) {
    var r = st.r, tok = r && r.status === "ok" ? rvToken(r.args) : "", s = st.srv, now = Date.now();
    if (!tok) return;
    if (s && s.tok === tok) {
      if (s.state === "ok" && s.expAt && now >= s.expAt) st.srv = { tok: tok, state: "fail", why: "expired", code: "" };
      if (s.inflight || !(s.state === "fail" && s.retry && now >= s.retryAt)) return;
    }
    var again = !!(s && s.tok === tok), tries = again ? (s.tries || 0) + 1 : 1;
    // ลองใหม่: ค้างหน้าจอเดิม (แดง + "กำลังลองใหม่") ไว้ระหว่างรอ ไม่กระพริบกลับเป็น "กำลังโหลด"
    var req = st.srv = again ? Object.assign({}, s, { inflight: true, tries: tries })
      : { tok: tok, state: "loading", tries: tries, inflight: true };
    srvReviewGet(srvConfig(st.server), tok).then(function (res) {
      if (st.srv !== req) return;
      res.tok = tok;
      res.tries = tries;
      if (res.state === "ok") res.expAt = res.expiresIn ? Date.now() + res.expiresIn * 1000 : 0;
      else if (res.transient && tries < 4) { res.retry = true; res.retryAt = Date.now() + 1000 * Math.pow(2, tries); }
      st.srv = res;
      if (card.isConnected && card.__qwRv === st) rvPaint(card, st);
    });
  }
  function rvFit(st) {
    var lc = st.box.__qwLines, pre = st.box.querySelector("pre.qw-review-code");
    if (lc && pre) lc.hidden = !(pre.scrollHeight > pre.clientHeight + 2);
  }
  function rvVisible(node) {
    var r = node.getBoundingClientRect();
    return r.bottom > 0 && r.top < (window.innerHeight || document.documentElement.clientHeight);
  }
  // กล่องพิมพ์ของ WebUI ลอยทับท้ายพื้นที่แชต scrollIntoView จึงวางปุ่มไว้ใต้มันได้ — คำนวณจากขอบบนของกล่องพิมพ์เอง
  function rvReveal(node) {
    var form = composerForm(), vh = window.innerHeight || document.documentElement.clientHeight;
    var limit = (form ? Math.min(form.getBoundingClientRect().top, vh) : vh) - 12;
    var d = node.getBoundingClientRect().bottom - limit;
    if (d <= 0) return;
    for (var p = node.parentElement; p && p !== document.body; p = p.parentElement) {
      var oy = getComputedStyle(p).overflowY;
      if ((oy === "auto" || oy === "scroll") && p.scrollHeight > p.clientHeight) { p.scrollTop += d; return; }
    }
    (document.scrollingElement || document.documentElement).scrollTop += d;
  }
  function rvDrop(card) {
    var st = card.__qwRv;
    if (!st) return;
    detach(st.box);
    card.classList.remove("qw-confirm-card");
    card.removeAttribute("data-qw-rv");
    card.__qwRv = null;
  }
  // ทุกการ์ดขออนุญาตของ local_confirm ในหน้า: ใส่กล่องตรวจทาน (ครั้งแรก = "กำลังโหลด" แล้วอ่าน IndexedDB)
  // ระหว่างที่การ์ดยังค้าง ตรวจซ้ำทุก 2 วินาที — ถ้าคำขอที่รออยู่เปลี่ยน (ไม่ควรเกิด แต่ถ้า Svelte ใช้การ์ดเดิมซ้ำ) กล่องต้องตามทัน
  function confirmCards() {
    var cs = document.querySelectorAll(PROMPT_SEL), any = false;
    for (var i = 0; i < cs.length; i++) {
      var c = cs[i], info = promptInfo(c);
      if (!info || info.kind !== "permission" || info.tool !== CONFIRM_TOOL) { rvDrop(c); continue; }
      any = true;
      var st = c.__qwRv;
      if (!st) {
        st = c.__qwRv = { box: rvBox(), card: c, seq: 0, key: null, at: 0, busy: false, good: false, scrolled: false,
          r: null, srv: null, server: "" };
        c.classList.add("qw-confirm-card");
        rvShow(st, { status: "loading" });
      }
      st.server = info.server || "";                     // S3: ชื่อเซิร์ฟเวอร์บนการ์ด → เลือก entry ในค่าตั้ง MCP
      // วางต่อจากแถวข้อความ (ลูกตัวแรก) = ก่อนแถวปุ่มเสมอ: อ่านก่อนถึงปุ่ม และ promptInfo ยังเห็นแถวข้อความเป็นลูกตัวแรก
      var head = c.firstElementChild;
      if (head && head !== st.box && (st.box.parentNode !== c || st.box.previousElementSibling !== head)) {
        c.insertBefore(st.box, head.nextSibling);
      }
      if (!st.busy && Date.now() - st.at >= 1500) rvLoad(c, st, info.tool);
      else rvFit(st);                                   // ความกว้างจอเปลี่ยน = ล้นกล่องหรือไม่ก็เปลี่ยน
    }
    if (any && !rvTimer) rvTimer = setInterval(function () { try { confirmCards(); } catch (e) {} }, 2000);
    else if (!any && rvTimer) { clearInterval(rvTimer); rvTimer = 0; }
  }

  /* ---- ALLOW-GUARD ฝั่ง UI (รอบ 5 แก้หลังรีวิว): ทางลัด "อนุญาตเสมอ" ที่ทำให้ local_confirm ไม่ถามคน -------------------
     ด่านที่รับประกันจริงคือ ALLOW_GUARD ต้นไฟล์ (ตัดคีย์ออกจากหน่วยความจำของ WebUI ทันทีที่ถูกเพิ่ม) ส่วนนี้กันไม่ให้คน
     เลือกทางลัดตั้งแต่แรก จะได้ไม่เข้าใจผิดว่าตั้งไว้แล้ว — ทำแบบ sync ใน observer ของ body (ไมโครทาสก์เดียวกับที่ Svelte
     ใส่ DOM = ก่อนวาดภาพและก่อนคลิกใดๆ ถึงหน้า) แทน scan ที่หน่วง 300ms ของรอบแรก ซึ่งช่วงนั้นปุ่มลูกศรยังกดได้:
       • การ์ดของ local_confirm: .qw-confirm-card (CSS ซ่อนปุ่มลูกศร) + กล่องตรวจทาน ทันทีที่การ์ดโผล่
       • เมนูของปุ่มลูกศร (อยู่ใน portal นอกการ์ด): ซ่อน "Always allow local_confirm tool" และ
         "Always allow all tools from <เซิร์ฟเวอร์ของเรา>" บนการ์ดของทุกเครื่องมือ (ALWAYS_SERVER ใส่ทุกเครื่องมือของ
         เซิร์ฟเวอร์ลงรายการ รวม local_confirm — การ์ด local_do คือทางที่รีวิวพบ) "Always allow local_do tool" ยังเลือกได้
       • หน้าตั้งค่า > เครื่องมือ: ล็อกสวิตช์ "Always allow" ของแถว local_confirm (สวิตช์ "Enabled" ยังใช้ได้ ปิดเครื่องมือ = ปลอดภัยกว่า)
     ตัดสินจากข้อความต้นฉบับอังกฤษ (enText — โหมดไทยถูกแปลไปแล้ว) ทุกจุด */
  // ช่อง "Always allow" ของแถวเครื่องมือในหน้าตั้งค่า (b10984 วาดเป็นช่องติ๊ก role=checkbox — เผื่อรุ่นที่เป็นสวิตช์ไว้ด้วย)
  var ALLOW_SW_SEL = '.w-20.shrink-0 > [role="checkbox"], .w-20.shrink-0 > [role="switch"]';
  var GUARD_SEL = PROMPT_SEL + ', [role="menuitem"], ' + ALLOW_SW_SEL;
  var GUARD_UP_SEL = PROMPT_SEL + ', [role="menuitem"]';
  // ชื่อที่ WebUI ใช้เรียกเซิร์ฟเวอร์ MCP ของเรา: serverInfo.name ที่ mcp-local ตอบ (server.py) เมื่อเชื่อมต่อสำเร็จ
  // ไม่งั้นชื่อ/URL ในค่าตั้ง (id local, local-full หรือ URL ไปพอร์ต 8792 ที่ผู้ใช้เพิ่มเอง) — ชื่อซ้ำกัน WebUI ต่อท้าย " (2)"
  var OUR_SERVER_NAMES = ["qwen38-local-fast", "qwen38-local"];
  var MCP_LOCAL_URL = /^https?:\/\/(?:127\.0\.0\.1|localhost|\[::1\]):8792(?:\/|$)/i;
  var ALLOW_LOCK_TIP = "local_confirm always asks, so you can see exactly what will run before you allow it.";
  function ourServerLabels() {
    var out = {};
    OUR_SERVER_NAMES.forEach(function (n) { out[n] = 1; });
    try {
      var cfg = JSON.parse(localStorage.getItem("LlamaUi.config") || "{}") || {};
      var list = typeof cfg.mcpServers === "string" ? JSON.parse(cfg.mcpServers || "[]") : cfg.mcpServers;
      (Array.isArray(list) ? list : []).forEach(function (s) {
        if (!s || !(s.id === "local" || s.id === "local-full" || MCP_LOCAL_URL.test(String(s.url || "")))) return;
        if (s.name) out[String(s.name)] = 1;
        if (s.url) out[String(s.url)] = 1;
      });
    } catch (e) { /* ค่าตั้งอ่านไม่ออก: ยังมีชื่อ serverInfo และด่าน ALLOW_GUARD */ }
    return out;
  }
  // true = รายการเมนูนี้ต้องซ่อน · ตรวจ "ทุกเครื่องมือจาก…" ก่อน (ชื่อเซิร์ฟเวอร์ที่ลงท้ายว่า " tool" ต้องไม่หลุดไปเข้ารูปแบบรายตัว)
  function allowItemBlocked(t, labels) {
    t = String(t || "").replace(/\s+/g, " ").trim();
    var m = /^(?:Always allow all tools from|Approve all tools from) ([\s\S]+)$/.exec(t);
    if (m) {
      var name = m[1], base = name.replace(/ \(\d+\)$/, "");
      return hasOwn(labels, name) || hasOwn(labels, base);
    }
    m = /^Always allow ([\s\S]+) tool$/.exec(t);
    return !!m && m[1] === CONFIRM_TOOL;
  }
  function allowHide(it, on) {
    if (on === it.classList.contains("qw-allow-hidden")) return;
    if (on) {
      it.classList.add("qw-allow-hidden");
      it.setAttribute("aria-hidden", "true");
      it.setAttribute("aria-disabled", "true");
      // bits-ui ข้ามรายการที่มี data-disabled ตอนเลื่อนด้วยแป้นลูกศร/พิมพ์หา — จดว่าเราใส่เอง จะถอดคืนได้ถูกตัว
      if (!it.hasAttribute("data-disabled")) { it.setAttribute("data-disabled", ""); it.setAttribute("data-qw-allow-dis", ""); }
    } else {
      it.classList.remove("qw-allow-hidden");
      it.removeAttribute("aria-hidden");
      it.removeAttribute("aria-disabled");
      if (it.hasAttribute("data-qw-allow-dis")) { it.removeAttribute("data-disabled"); it.removeAttribute("data-qw-allow-dis"); }
    }
  }
  function allowMenus() {
    var items = document.querySelectorAll('[role="menuitem"]'), labels = null;
    for (var i = 0; i < items.length; i++) {
      var it = items[i], t = enText(it).replace(/\s+/g, " ").trim(), block = false;
      if (/^(?:Always allow|Approve all tools from) /.test(t)) {
        if (!labels) labels = ourServerLabels();
        block = allowItemBlocked(t, labels);
      }
      allowHide(it, block);
    }
  }
  function allowSwitches() {
    var sws = document.querySelectorAll(ALLOW_SW_SEL);
    for (var i = 0; i < sws.length; i++) {
      var sw = sws[i], cell = sw.parentElement, row = cell && cell.parentElement;
      var name = row && row.firstElementChild !== cell ? row.firstElementChild : null;
      var lock = !!name && enText(name).replace(/\s+/g, " ").trim() === CONFIRM_TOOL;
      if (lock === cell.classList.contains("qw-allow-locked")) continue;
      if (lock) {
        cell.classList.add("qw-allow-locked");
        sw.setAttribute("aria-disabled", "true");
        sw.setAttribute("tabindex", "-1");
        cell.setAttribute("title", ALLOW_LOCK_TIP);          // ตัวแปลแปล title ให้เอง
      } else {
        cell.classList.remove("qw-allow-locked");
        sw.removeAttribute("aria-disabled");
        sw.removeAttribute("tabindex");
        cell.removeAttribute("title");
        cell.removeAttribute("data-qw-en-title");
      }
    }
  }
  // ชั้นที่สอง: รายการที่ซ่อน/สวิตช์ที่ล็อกกดไม่ได้แม้เหตุการณ์จะไปถึง (ดักตั้งแต่ window ขาลง ก่อน bits-ui เห็น)
  function allowBlock(e) {
    var t = e.target;
    if (!t || t.nodeType !== 1 || !t.closest(".qw-allow-hidden, .qw-allow-locked")) return;
    if (e.type === "keydown" && e.key !== "Enter" && e.key !== " " && e.key !== "Spacebar") return;
    e.preventDefault();
    e.stopImmediatePropagation();
  }
  ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "keydown"].forEach(function (t) {
    window.addEventListener(t, allowBlock, true);
  });
  // เรียกจาก observer ของ body ทุกชุด: ดูเฉพาะว่ามีการ์ดขออนุญาต/รายการเมนู/สวิตช์ "อนุญาตเสมอ" ถูกใส่หรือเปลี่ยนหรือไม่
  // (ข้อความที่ไหลระหว่างสตรีมอยู่ใน TX_FAST ตัดทิ้งก่อน — ต้นทุนต่อชุดแทบเป็นศูนย์) เจอ = จัดการทั้งหน้าทันที
  function permGuard(recs) {
    for (var i = 0; i < recs.length; i++) {
      var r = recs[i];
      if (r.type === "childList") {
        for (var k = 0; k < r.addedNodes.length; k++) {
          var n = r.addedNodes[k];
          if (n.nodeType === 1) {
            if (n.closest(TX_FAST)) continue;
            if (n.matches(GUARD_SEL) || n.querySelector(GUARD_SEL) || n.closest(GUARD_UP_SEL)) { permGuardRun(); return; }
          } else if (n.nodeType === 3 && guardUp(n.parentNode)) { permGuardRun(); return; }
        }
      } else if (r.type === "characterData" && guardUp(r.target.parentNode)) { permGuardRun(); return; }
    }
  }
  function guardUp(p) { return !!p && p.nodeType === 1 && !p.closest(TX_FAST) && !!p.closest(GUARD_UP_SEL); }
  function permGuardRun() {
    try { confirmCards(); } catch (e) {}
    try { allowMenus(); } catch (e) {}
    try { allowSwitches(); } catch (e) {}
  }

  /* ---- ป้ายผลของ local_confirm บนแถวเครื่องมือในแชต (รอบ 5 แก้หลังรีวิว) --------------------------------------------
     ปัญหา: local_confirm ถูกปฏิเสธ (review ไม่ตรง, token หมดอายุ) แล้วคนไม่เห็นอะไรเลย — แถวเครื่องมือพับไว้ กล่องตรวจทาน
     หายไปกับการ์ด โมเดลพูดต่อราวกับรันแล้ว (เห็นจริงในการทดสอบ e2e ของผู้ตรวจ) คนจึงเชื่อได้ง่ายๆ ว่าโค้ดรันไปแล้ว
     ป้ายต่อท้ายชื่อบนแถว (อยู่ในปุ่มพับ/กาง = โปรแกรมอ่านจออ่านพร้อมชื่อ): รันแล้ว / ไม่ได้รัน — เหตุผล / ล้มเหลว
     ข้อมูล: ผลที่ WebUI บันทึกใน IndexedDB (role "tool" + toolCallId) — WebUI ทิ้ง isError ของ MCP ไม่เก็บ จึงตัดสินจาก
     "หัว" ข้อความ ซึ่งเซิร์ฟเวอร์เขียนเองทุกกรณี (server._confirm_call หรือหัวของเครื่องมือที่ถูกเล่นซ้ำ เช่น
     "ผลการรันโค้ด Python —") ไม่ใช่ผลลัพธ์ของโค้ด — เทียบเฉพาะต้นข้อความ ห้ามค้นกลางข้อความ (โค้ดที่พิมพ์คำว่า
     "ยังไม่ได้ทำอะไร" ออกมาต้องไม่ทำให้ป้ายกลายเป็น "ไม่ได้รัน")
     จับคู่แถวใน DOM กับการเรียกใน DB: กลุ่มข้อความผู้ช่วยที่ตามหลังข้อความผู้ใช้ตัวที่ k = ช่วงของสายข้อความหลังผู้ใช้ตัวที่ k
     แล้วเทียบชื่อเครื่องมือตามลำดับ ต้องจับได้ครบทุกการเรียกของช่วงนั้น ไม่งั้นไม่ใส่ป้าย (ใส่ผิดแถวแย่กว่าไม่ใส่) */
  var CF_RESULT = [
    [/^Tool execution was denied by the user/, "denied"],
    [/^Tool execution was interrupted/, "interrupted"],
    [/^ยังไม่ได้ทำอะไร: (?:review |\S+ ต้องมีพารามิเตอร์ review)/, "review"],
    [/^confirm_token (?:นี้)?ใช้ไม่ได้/, "token"],
    [/^(?:ยังไม่ได้ทำอะไร|ยังไม่ได้รัน|ต้องใส่ confirm_token|confirm_token นี้ขอมาจาก|token นี้ไม่มีข้อความตรวจทาน|เครื่องมือ \S+ ที่ขอ token นี้ไม่มีแล้ว|ปฏิเสธ|kernel ของโปรเจกต์นี้กำลังรันโค้ดอื่นอยู่)/, "refused"],
    [/^(?:เครื่องมือ \S+ ล้มเหลว|ผิดพลาด|Error:)/, "failed"]
  ];
  var CF_LABEL = {
    ran: "Ran — expand to see the result",
    review: "Not run — the review text didn't match",
    token: "Not run — the confirm code expired or was already used",
    denied: "Not run — you chose Deny",
    interrupted: "Not run — interrupted",
    refused: "Not run — refused",
    failed: "Failed — expand to see the error"
  };
  // ข้อยกเว้นหนึ่งเดียวที่หัวข้อความมาจากสิ่งที่ถูกรัน: คำสั่งระบบ (action run) ที่ถูกเล่นซ้ำ — ผลขึ้นต้นด้วย stdout ของคำสั่ง
  // (echo อะไรก็ได้) แต่ท้ายเป็น "[exit code: N]" ของเซิร์ฟเวอร์เสมอ (tools_files) และคำปฏิเสธของ local_confirm ไม่มีวันลงท้ายแบบนี้
  // จึงเช็กท้ายก่อน: คำสั่งที่พิมพ์ข้อความปฏิเสธปลอมออกมาต้องไม่ทำให้ป้ายบอกว่า "ไม่ได้รัน"
  var CF_RAN_TAIL = /\[exit code: -?\d+\]\s*$/;
  function confirmResultKind(text) {
    if (typeof text !== "string") return null;
    var s = text.replace(/^\s+/, "");
    if (CF_RAN_TAIL.test(s)) return "ran";
    for (var i = 0; i < CF_RESULT.length; i++) if (CF_RESULT[i][0].test(s)) return CF_RESULT[i][1];
    return "ran";
  }
  function cfCalls(raw) {
    var calls = raw;
    if (typeof raw === "string") {
      try { calls = raw ? JSON.parse(raw) : []; } catch (e) { return []; }
    }
    if (!Array.isArray(calls)) return [];
    var out = [];
    for (var i = 0; i < calls.length; i++) {
      var c = calls[i];
      if (c && c.function) out.push({ id: c.id, name: String(c.function.name || "") });
    }
    return out;
  }
  // groups = [{u: จำนวนข้อความผู้ใช้ก่อนกลุ่มนี้ในหน้า, names: [ชื่อแถวเครื่องมือตามลำดับ]}]
  // path = ข้อความในสายที่แสดงอยู่ จาก root ถึง currNode → [[ชนิดผล | null ต่อแถว], ...] (null = ไม่ใส่ป้าย)
  function cfPlan(groups, path) {
    var segs = {}, u = 0;
    for (var i = 0; i < (path || []).length; i++) {
      var m = path[i];
      if (!m) continue;
      if (m.role === "user") { u++; continue; }
      if (m.role !== "assistant" && m.role !== "tool") continue;
      var sg = segs[u] || (segs[u] = { calls: [], res: {} });
      if (m.role === "assistant") sg.calls = sg.calls.concat(cfCalls(m.toolCalls));
      else if (m.toolCallId != null) sg.res[m.toolCallId] = m.content;
    }
    return groups.map(function (g) {
      var out = g.names.map(function () { return null; }), sg = hasOwn(segs, g.u) ? segs[g.u] : null;
      if (!sg || !sg.calls.length) return out;
      var p = 0, pairs = [];
      for (var k = 0; k < g.names.length && p < sg.calls.length; k++) {
        if (g.names[k] === sg.calls[p].name) { pairs.push([k, sg.calls[p]]); p++; }
      }
      if (p !== sg.calls.length) return out;
      pairs.forEach(function (pr) {
        var c = pr[1];
        if (c.name === CONFIRM_TOOL && c.id != null && hasOwn(sg.res, c.id)) out[pr[0]] = confirmResultKind(sg.res[c.id]);
      });
      return out;
    });
  }
  // แถวหัวบล็อกเครื่องมือระดับบนของกลุ่มข้อความผู้ช่วย ตามลำดับในหน้า (บล็อกที่ซ้อนอยู่ในเนื้อหาของบล็อกอื่นไม่นับ)
  function cfRows(group) {
    var ts = group.querySelectorAll('[data-slot="collapsible"] > button[data-slot="collapsible-trigger"]'), out = [];
    for (var i = 0; i < ts.length; i++) {
      var t = ts[i];
      if (t.closest('[data-slot="collapsible-content"]')) continue;
      var holder = t.firstElementChild, sp = holder && holder.querySelector(":scope > span.font-medium");
      if (!sp) continue;
      out.push({ holder: holder, name: enText(sp).replace(/\s+/g, " ").trim() });
    }
    return out;
  }
  function cfGroups() {
    var ns = document.querySelectorAll(".chat-messages .chat-message-user, .chat-messages .chat-message-assistant");
    var groups = [], u = 0;
    for (var i = 0; i < ns.length; i++) {
      if (ns[i].classList.contains("chat-message-user")) { u++; continue; }
      var rows = cfRows(ns[i]);
      if (rows.length) groups.push({ u: u, rows: rows, names: rows.map(function (r) { return r.name; }) });
    }
    return groups;
  }
  function cfBadge(holder) { return holder.querySelector(":scope > .qw-cf-status"); }
  function cfBadgeSet(holder, kind) {
    var b = cfBadge(holder);
    if (b && b.getAttribute("data-kind") === kind) return;
    if (!b) b = holder.appendChild(el("span", "qw-cf-status"));
    b.setAttribute("data-kind", kind);
    b.setAttribute("data-tone", kind === "ran" ? "ok" : kind === "failed" ? "failed" : "notrun");
    b.textContent = CF_LABEL[kind];                    // อังกฤษลง DOM แล้วให้ตัวแปลแปล (เหมือนป้ายอื่นของเรา)
  }
  // สายข้อความที่แสดงอยู่ (root → currNode) อ่านอย่างเดียวแบบเดียวกับ confirmCallFromDb: ไม่สร้างฐาน ปิดทุกครั้ง หมดเวลา 3 วิ
  function cfPathFromDb(convId) {
    return new Promise(function (resolve) {
      var db = null, settled = false, req;
      function fin(v) {
        if (settled) return;
        settled = true;
        try { if (db) db.close(); } catch (e) {}
        resolve(v || null);
      }
      if (!convId || !window.indexedDB) { fin(); return; }
      setTimeout(function () { fin(); }, 3000);
      try { req = indexedDB.open("LlamaUi"); } catch (e) { fin(); return; }
      req.onupgradeneeded = function () { try { req.transaction.abort(); } catch (e) {} };
      req.onerror = req.onblocked = function () { fin(); };
      req.onsuccess = function () {
        db = req.result;
        if (settled) { try { db.close(); } catch (e) {} return; }
        db.onversionchange = function () { fin(); };
        try {
          if (!db.objectStoreNames.contains("conversations") || !db.objectStoreNames.contains("messages")) { fin(); return; }
          var t = db.transaction(["conversations", "messages"], "readonly"), ms = t.objectStore("messages");
          if (!ms.indexNames.contains("convId")) { fin(); return; }
          var c = t.objectStore("conversations").get(convId);
          c.onsuccess = function () {
            var head = c.result && c.result.currNode;
            if (!head) { fin(); return; }
            var g = ms.index("convId").getAll(convId);
            g.onsuccess = function () {
              var by = {}, list = g.result || [], path = [], seen = {}, id = head;
              for (var i = 0; i < list.length; i++) if (list[i] && list[i].id != null) by[list[i].id] = list[i];
              while (id != null && hasOwn(by, id) && !seen[id] && path.length < 5000) {
                seen[id] = 1;
                path.push(by[id]);
                id = by[id].parent;
              }
              fin(path.reverse());
            };
            g.onerror = function () { fin(); };
          };
          c.onerror = function () { fin(); };
        } catch (e) { fin(); }
      };
    });
  }
  // เรียกจาก scanPrompts (หน่วง ≤300ms หลัง DOM เปลี่ยน): อ่าน DB เฉพาะเมื่อมีแถว local_confirm ที่ยังไม่มีป้าย
  // ผลยังไม่ถูกบันทึก (รอคนกด/กำลังรัน) = เว้นระยะอ่านห่างขึ้นเรื่อยๆ (1.2 → 30 วิ; ระหว่างรอคนกด WebUI ยังขยับ DOM อยู่
  // ถี่ๆ) กันอ่านทั้งแชตซ้ำไม่เลิก · แต่ทุกครั้งที่ "จังหวะที่ผลอาจเพิ่งถูกบันทึก" เปลี่ยน (การ์ดขออนุญาตโผล่/หาย, รอบเอเจนต์
  // ใหม่เริ่ม, สตรีมเริ่ม/จบ, จำนวนแถวที่รอ, เปลี่ยนแชต) กลับมาอ่านทันที — ไม่งั้นคนที่รอนานก่อนกด จะเห็นป้ายช้าไปถึง 30 วิ
  // ถูกเว้นระยะไว้ = นัดรอบท้ายไว้หนึ่งครั้ง
  var cf = { busy: false, next: 0, delay: 1200, timer: 0, sig: "" };
  var CF_TITLE_SEL = '.chat-messages [data-slot="collapsible"] > button[data-slot="collapsible-trigger"] > div > span.font-medium';
  // นับแถว local_confirm ที่ยังไม่มีป้าย ด้วย query เดียว (ถูกเรียกทุก ≤300ms ระหว่างสตรีม — แชตยาวต้องไม่ช้า)
  function cfPendingRows() {
    var sp = document.querySelectorAll(CF_TITLE_SEL), n = 0;
    for (var i = 0; i < sp.length; i++) {
      if (sp[i].textContent.trim() !== CONFIRM_TOOL || cfBadge(sp[i].parentNode)) continue;
      if (!sp[i].closest('[data-slot="collapsible-content"]')) n++;
    }
    return n;
  }
  function cfBadgeScan() {
    var r = route();
    if (r.name !== "chat" || !r.id) return;
    var pend = cfPendingRows(), now = Date.now();
    if (!pend) { cf.sig = ""; return; }
    var sig = [r.id, pend, document.querySelectorAll(PROMPT_SEL).length,
      document.getElementsByClassName("agentic-turn").length, isStreaming() ? 1 : 0].join("|");
    if (sig !== cf.sig) {
      cf.sig = sig;
      cf.delay = 1200;
      if (cf.next > now) cf.next = now;
    }
    if (cf.busy || now < cf.next) {
      if (!cf.timer) {
        cf.timer = setTimeout(function () { cf.timer = 0; try { cfBadgeScan(); } catch (e) {} }, Math.max(50, cf.next - now));
      }
      return;
    }
    cf.busy = true;
    var conv = r.id;
    cfPathFromDb(conv).then(function (path) {
      cf.busy = false;
      cf.next = Date.now() + cf.delay;
      if (!path || route().id !== conv) return;
      var groups = cfGroups(), plan = cfPlan(groups, path), left = 0;
      groups.forEach(function (g, gi) {
        g.rows.forEach(function (row, ri) {
          if (row.name !== CONFIRM_TOOL) return;
          var kind = plan[gi][ri];
          if (kind) cfBadgeSet(row.holder, kind);
          else if (!cfBadge(row.holder)) left++;
        });
      });
      cf.delay = left ? Math.min(cf.delay * 2, 30000) : 1200;
    }, function () { cf.busy = false; cf.next = Date.now() + cf.delay; });
  }
  // ---- เนื้อความของการแจ้งเตือน "ตอบเสร็จ" มาจากข้อมูล ไม่ใช่จาก DOM (แก้หลังรีวิว UX รอบ 4) ----
  // ตอนแท็บถูกซ่อน WebUI ไม่วาด DOM ของรอบเอเจนต์หลังเรียกเครื่องมือ (วัดจริง: .markdown-content ว่าง หรือได้แค่ "[ux")
  // ซึ่งเป็นจังหวะที่ผู้ใช้สลับแท็บไปพอดี — ข้อความที่ WebUI บันทึกลง IndexedDB "LlamaUi" (origin เดียวกัน) ครบก่อนปุ่มหยุดหายเสมอ
  // (onComplete/onAssistantTurnComplete: updateMessage + currNode แล้วจึง cleanupStreaming)
  // Markdown → ข้อความล้วนพออ่านรู้เรื่องในการแจ้งเตือน: ตัดความคิด บล็อกโค้ด รูป เส้นคั่น เหลือข้อความของลิงก์
  // "_" เดี่ยวไม่แตะ (ชื่อเครื่องมือ/ตัวแปรอย่าง local_read ต้องอ่านได้ตามจริง)
  function mdPlain(s) {
    s = String(s || "").replace(/\r\n?/g, "\n")
      .replace(/<think>[\s\S]*?(?:<\/think>|$)/gi, "\n")
      .replace(/<<<reasoning_content_start>>>[\s\S]*?(?:<<<reasoning_content_end>>>|$)/g, "\n");
    var out = [], fence = "";
    s.split("\n").forEach(function (l) {
      var f = /^\s{0,3}(`{3,}|~{3,})/.exec(l);
      if (fence) {
        if (f && f[1].charAt(0) === fence.charAt(0) && f[1].length >= fence.length && !/\S/.test(l.slice(f[0].length))) fence = "";
        return;
      }
      if (f) { fence = f[1]; return; }
      if (/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/.test(l)) return;     // เส้นใต้หัวตาราง
      if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(l)) return;                            // เส้นคั่น ---
      l = l.replace(/^\s{0,3}#{1,6}\s+/, "").replace(/^\s*(>\s?)+/, "")
        .replace(/^\s*(?:[-*+]|\d{1,3}[.)])\s+(?:\[[ xX]\]\s+)?/, "")
        .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
        .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
        .replace(/<\/?[a-zA-Z][^>]*>/g, " ")
        .replace(/(\*\*|__)(?=\S)([\s\S]*?\S)\1/g, "$2")
        .replace(/(^|[^*\w])\*(?=\S)([^*]*?\S)\*(?!\w)/g, "$1$2")
        .replace(/~~(?=\S)([\s\S]*?\S)~~/g, "$1")
        .replace(/`+([^`]+)`+/g, "$1");
      if (/^\s*\|.*\|\s*$/.test(l)) {                                               // แถวตาราง → คั่นด้วย ", "
        l = l.replace(/^\s*\||\|\s*$/g, "").split("|").map(function (c) { return c.trim(); }).filter(Boolean).join(", ");
      }
      out.push(l);
    });
    return out.join("\n").replace(/[ \t]+/g, " ").replace(/ ?\n\s*/g, "\n").trim();
  }
  // คำตอบสุดท้ายของรอบนี้ — chain = ข้อความจาก currNode ไล่ขึ้นไปจนก่อนถึงข้อความผู้ใช้ (ล่างสุดก่อน)
  // รอบเอเจนต์คือ ผู้ช่วย → tool → ผู้ช่วย …: ข้อความผู้ช่วยตัวล่างสุดที่มีเนื้อความ = สรุปที่ผู้ใช้จะเห็นท้ายสุด
  function replyText(chain) {
    for (var i = 0; i < chain.length; i++) {
      var m = chain[i];
      if (!m || m.role !== "assistant") continue;
      var t = mdPlain(m.content);
      if (t) return t;
    }
    return "";
  }
  // อ่านอย่างเดียว เปิดโดยไม่ระบุเวอร์ชัน: ถ้าฐานข้อมูลยังไม่มี (onupgradeneeded) ยกเลิกทันที ไม่สร้างฐานว่างแทน WebUI
  // ปิดการเชื่อมต่อทุกครั้ง (และเมื่อ WebUI ขออัปเกรดสคีมา) — ห้ามถือค้างจน Dexie ของ WebUI เปิดเวอร์ชันใหม่ไม่ได้
  function replyFromDb(convId) {
    return new Promise(function (resolve) {
      var db = null, settled = false, req;
      function fin(v) {
        if (settled) return;
        settled = true;
        try { if (db) db.close(); } catch (e) {}
        resolve(v || "");
      }
      if (!convId || !window.indexedDB) { fin(""); return; }
      setTimeout(function () { fin(""); }, 3000);                      // IndexedDB ไม่ตอบ ต้องไม่ทำให้การแจ้งเตือนหาย
      try { req = indexedDB.open("LlamaUi"); } catch (e) { fin(""); return; }
      req.onupgradeneeded = function () { try { req.transaction.abort(); } catch (e) {} };
      req.onerror = req.onblocked = function () { fin(""); };
      req.onsuccess = function () {
        db = req.result;
        if (settled) { try { db.close(); } catch (e) {} return; }
        db.onversionchange = function () { fin(""); };
        try {
          if (!db.objectStoreNames.contains("conversations") || !db.objectStoreNames.contains("messages")) { fin(""); return; }
          var t = db.transaction(["conversations", "messages"], "readonly"), ms = t.objectStore("messages");
          var chain = [], seen = {};
          // ต่อคำขอใน onsuccess ตรงๆ (ไม่ผ่าน Promise) — ทรานแซกชันยัง active แน่นอนทุกเบราว์เซอร์
          var step = function (id) {
            if (!id || seen[id] || chain.length >= 400) { fin(replyText(chain)); return; }
            seen[id] = 1;
            var g = ms.get(id);
            g.onsuccess = function () {
              var m = g.result;
              if (!m || m.role === "user" || m.type === "root") { fin(replyText(chain)); return; }
              chain.push(m);
              step(m.parent);
            };
            g.onerror = function () { fin(replyText(chain)); };
          };
          var c = t.objectStore("conversations").get(convId);
          c.onsuccess = function () { step(c.result && c.result.currNode); };
          c.onerror = function () { fin(""); };
        } catch (e) { fin(""); }
      };
    });
  }
  // IndexedDB ก่อน (ยังว่าง = บันทึกอาจช้ากว่าปุ่มหยุดนิดหน่อย ลองอีกครั้ง) → DOM เฉพาะตอนแท็บมองเห็นอยู่ (DOM ตรงกับจอ)
  // → ไม่ได้อะไรเลย = ข้อความกลางๆ ให้เปิดแชตอ่าน (ดีกว่าส่งเศษข้อความที่ขาดกลางคำ)
  function doneBody(chatId) {
    return replyFromDb(chatId).then(function (t) {
      return t || new Promise(function (r) { setTimeout(r, 1200); }).then(function () { return replyFromDb(chatId); });
    }).then(function (t) {
      if (!t && !document.hidden) { var m = lastAssistant(); t = m ? speakText(m) : ""; }
      return t ? clip(t, 140) : tx("Open the chat to read the reply.");
    }, function () { return tx("Open the chat to read the reply."); });
  }
  function onStreamStart() { streamStartAt = Date.now(); artFollow = null; }
  function onStreamEnd() {
    var started = streamStartAt;
    // รอสั้นๆ: รอบเอเจนต์ถัดไป/การ์ดขออนุญาตอาจตามมาทันที — ไม่ใช่ "ตอบเสร็จ" จริง
    setTimeout(function () {
      try {
        if (userStopAt && userStopAt >= started) return;          // ผู้ใช้กดหยุดเอง = อยู่หน้าจออยู่แล้ว
        if (isStreaming() || promptPending()) return;            // ยังไม่จบ หรือการ์ดแจ้งไปแล้วในตัวมันเอง
        var chatId = route().id || null, name = chatName();
        armArtFollow(chatId);                                    // K7: แผงที่เปิดชิ้นเดียวกันอยู่ตามรุ่นใหม่ของคำตอบนี้
        doneBody(chatId).then(function (body) {
          notifyShell("done", tx("Reply finished") + (name ? " · " + name : ""), body, chatId);
        });
      } catch (e) {}
    }, 700);
  }
  // ปุ่มหยุดของ WebUI (กล่องพิมพ์ / การ์ด "ทำต่อ") — กดด้วยมือจริงเท่านั้น
  function noteUserStop(e) {
    if (!e.isTrusted) return;
    if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
    var b = e.target && e.target.closest ? e.target.closest("button") : null;
    if (!b || b.closest(".qw-speak-stop")) return;
    var lab = (b.getAttribute("aria-label") || "") + " " + (enAttr(b, "title") || "") + " " + enText(b);
    if (/\bstop\b/i.test(lab) || /hover:bg-destructive/.test(b.className || "")) userStopAt = Date.now();
  }

  /* ---- K6: ชิป "เร็ว (4B)" ในแถวเครื่องมือของกล่องพิมพ์ (ฝั่งซ้าย ถัดจากปุ่ม "+") ---------------------------- */
  // สลับโมเดลผ่านเมนูเลือกโมเดลของ WebUI เอง (ไม่ใช่แอบเปลี่ยนที่ proxy) ปุ่มโมเดลจึงแสดงชื่อที่ใช้จริงเสมอ
  // WebUI ไม่จำโมเดลที่เลือกข้ามการโหลดหน้า (iframe ได้ ?model= ของโปรเจกต์ทุกครั้ง) จึงจำ "โหมดเร็ว" เองใน
  // localStorage — แต่ละโปรเจกต์คนละพอร์ต = คนละ origin = จำแยกต่อโปรเจกต์โดยอัตโนมัติ
  // ตำแหน่ง: เดิมวางซ้ายของปุ่มโมเดล แต่ปุ่มโมเดลกว้างไม่เท่ากัน ("Qwen3.8 27B" vs "Qwen3 4B Instruct 2507") ชิปจึงกระโดด
  // ~83px ทุกครั้งที่สลับ กดซ้ำที่เดิมไปโดนเมนูโมเดลแทน — ย้ายไปฝั่งซ้ายถัดจาก "+" ซึ่งกว้างคงที่ (แบบปุ่มสลับของกล่องพิมพ์ทั่วไป)
  // ปิดโหมดเร็ว = เลือกโมเดลของโปรเจกต์ ซึ่ง WebUI สั่ง POST /models/load ทันทีถ้ายังไม่ได้โหลด (27B ~18 GB บนเครื่องที่
  // หน่วยความจำตึง) — ตรวจสถานะจากตัวเลือกในเมนูก่อนคลิก ยังไม่โหลด = ไม่สลับ ขอให้กดยืนยันอีกครั้งภายใน FAST_ARM_MS
  var FAST_MODEL = "Qwen3-4B-Instruct-2507-Q4_K_M", KEY_FAST = "qwen-fast-model";
  var FAST_TIP = "Fast mode: answer with Qwen3-4B, much faster but less thorough. Click again to go back to the project model (if it isn't loaded yet, it loads first: large and slow).";
  var FAST_ARM_TIP = "Click again to load the project model and switch back.";
  var FAST_ARM_MS = 8000;
  var fastChip = null, fastBusy = false, fastApplied = false, fastBootAt = Date.now();
  var fastArmed = 0, fastArmTimer = 0;
  // ชื่อสั้นสำหรับข้อความ: ตัดส่วนควอนไทซ์ท้าย id (Qwen3.8-27B-UD-Q4_K_M → Qwen3.8-27B)
  function modelLabel(id) {
    return String(id || "").replace(/-(?:UD-)?(?:I?Q\d\w*|MXFP4\w*|BF16|F16|F32)$/i, "") || String(id || "");
  }
  function projectModel() {
    var sh = shell();
    if (!sh) return "";
    var p = sh.project || {};
    return String(p.model || sh.primaryModel || "");
  }
  function shellModels() {
    var sh = shell(), ms = sh && sh.models;
    if (!Array.isArray(ms)) return [];
    return ms.map(function (m) { return typeof m === "string" ? m : (m && (m.id || m.model)) || ""; }).filter(Boolean);
  }
  function modelButton() {
    var f = composerForm(), s = f && f.querySelector("button svg.lucide-package");
    return s ? s.closest("button") : null;
  }
  function alnum(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, ""); }
  // ปุ่ม/ตัวเลือกโมเดลแสดง "ชื่อ + ป้าย" ที่ WebUI แยกออกจาก id (Qwen3 · 4B · Q4_K_M …) ไม่มี id ให้อ่านตรงๆ
  // จึงเทียบทุกชิ้นกับ id ที่มี (ตัดเครื่องหมายออก) — ต้องมีครบทุกชิ้น เลือกตัวที่ชิ้นครอบคลุม id มากที่สุด เสมอกัน = ไม่รู้
  function modelFromParts(parts, ids) {
    parts = parts.map(alnum).filter(Boolean);
    if (!parts.length) return null;
    var best = null, bestLeft = Infinity, tie = false;
    for (var i = 0; i < ids.length; i++) {
      var a = alnum(ids[i]), used = 0, ok = true;
      for (var j = 0; j < parts.length && ok; j++) { if (a.indexOf(parts[j]) < 0) ok = false; else used += parts[j].length; }
      if (!ok) continue;
      var left = a.length - used;
      if (left < bestLeft) { best = ids[i]; bestLeft = left; tie = false; } else if (left === bestLeft) tie = true;
    }
    return tie ? null : best;
  }
  function partsOf(node) {
    var name = node && node.querySelector(".font-medium");
    if (!name) return [];
    var parts = [enText(name)], bs = node.querySelectorAll(".font-mono");
    for (var i = 0; i < bs.length; i++) parts.push(enText(bs[i]));
    return parts;
  }
  function currentModel() { return modelFromParts(partsOf(modelButton()), shellModels()); }
  // ตัวเลือกโมเดลมีสองแบบตามความกว้าง: จอกว้าง = เมนู bits-ui (เมนูย่อยมีช่องค้นหา + .models-list เปิดด้วย pointerdown)
  // จอแคบ = ชีตล่าง "Select Model" (เปิดด้วย click ตัวเลือกอยู่ในชีต ไม่มี .models-list)
  var PICKER_OPEN = '[data-slot="dropdown-menu-content"][data-state="open"], [data-slot="sheet-content"][data-state="open"]';
  function menuOpen() { return !!document.querySelector(PICKER_OPEN); }
  function modelSearch() {
    return document.querySelector('[data-slot="dropdown-menu-sub-content"] input, ' +
      '[data-slot="sheet-content"][data-state="open"] input');
  }
  function modelOptions() {
    return document.querySelectorAll('.models-list [role="option"], [data-slot="sheet-content"][data-state="open"] [role="option"]');
  }
  function quietMenuStyle() {
    if (document.getElementById("qw-quiet-menu")) return;
    var st = document.createElement("style");
    st.id = "qw-quiet-menu";
    st.textContent = 'html[data-qw-quiet-menu] :is([data-slot="dropdown-menu-content"],[data-slot="dropdown-menu-sub-content"],' +
      '[data-slot="sheet-content"],[data-slot="sheet-overlay"])' +
      "{opacity:0!important;pointer-events:none!important;animation:none!important}";
    (document.head || root).appendChild(st);
  }
  // เลือกโมเดลด้วยเมนูของ WebUI: เปิดเมนู/ชีต → พิมพ์ id เต็มในช่องค้นหา (WebUI กรองด้วย model.includes(คำค้น)
  // เหลือตัวเดียว) → คลิกตัวเลือกนั้น → รอปุ่มโมเดลเปลี่ยนเป็นตัวที่ต้องการ
  // เมนูชั่วคราวถูกซ่อนไว้ระหว่างนี้ (ไม่ให้เห็นกะพริบ) และปิด/คืนเสมอแม้ขั้นไหนพลาด
  // ผู้ใช้กดแป้นระหว่างนั้น (กำลังพิมพ์) = ยกเลิก — ช่องค้นหาของเมนูแย่งโฟกัส ตัวอักษรที่พิมพ์จะหายไปในนั้น
  // หมายเหตุ: เลือกโมเดลที่ router ยังไม่ได้โหลด WebUI จะสั่งโหลดให้เอง (พฤติกรรมเดียวกับผู้ใช้เลือกจากเมนู)
  // needLoaded = ตัวเลือกยังไม่โหลด (และไม่ได้กำลังโหลด) ให้ปิดเมนูโดยไม่คลิก คืน "unloaded" — ผู้เรียกถามผู้ใช้ก่อน
  function pickModel(id, needLoaded) {
    var b = modelButton();
    if (!b || fastBusy || !id) return Promise.resolve(false);
    fastBusy = true;
    var prev = document.activeElement, typed = false;
    var onKey = function (e) { if (e.isTrusted) typed = true; };
    var viaMenu = b.hasAttribute("data-dropdown-menu-trigger") || b.getAttribute("aria-haspopup") === "menu";
    window.addEventListener("keydown", onKey, true);
    quietMenuStyle();
    setAttr("data-qw-quiet-menu", "1");
    function finish(ok) {
      window.removeEventListener("keydown", onKey, true);
      if (menuOpen()) {
        var c = document.querySelector('[data-slot="dropdown-menu-sub-content"]') || document.querySelector(PICKER_OPEN);
        if (c) c.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true, cancelable: true }));
      }
      // ปลดหลังแอนิเมชันปิด (~150ms) — ปลดทันทีจะเห็นเมนูจางหายแวบหนึ่ง
      setTimeout(function () { setAttr("data-qw-quiet-menu", null); }, 220);
      fastBusy = false;
      // WebUI ย้ายโฟกัสไปกล่องพิมพ์หลังเลือก (rAF) — คืนให้ที่เดิม (ชิปที่เพิ่งกด) หลังเฟรมนั้น
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          if (prev && prev !== document.body && prev.isConnected && document.activeElement !== prev && !typed) {
            try { prev.focus({ preventScroll: true }); } catch (e) {}
          }
        });
      });
      schedule();
      return ok;
    }
    if (viaMenu) b.dispatchEvent(mousePointer("pointerdown")); else b.click();
    return waitFor(modelSearch, 1200).then(function (inp) {
      if (inp || typed) return inp;
      // รุ่นหน้าเปลี่ยนวิธีเปิด: ลองอีกแบบหนึ่ง
      if (!menuOpen()) { if (viaMenu) b.click(); else b.dispatchEvent(mousePointer("pointerdown")); }
      return waitFor(modelSearch, 1200);
    }).then(function (inp) {
      if (!inp || typed) return null;
      setInputValue(inp, id);
      return waitFor(function () {
        var os = modelOptions();
        if (os.length !== 1 || os[0].getAttribute("aria-disabled") === "true") return null;
        return modelFromParts(partsOf(os[0]), shellModels()) === id ? os[0] : null;
      }, 1500);
    }).then(function (opt) {
      if (!opt || typed) return false;
      if (needLoaded && !optionReady(opt)) return "unloaded";
      opt.click();
      return waitFor(function () { return currentModel() === id; }, 3000).then(Boolean);
    }).then(finish, function () { return finish(false); });
  }
  // สถานะจากตัวเลือกในเมนูโมเดลของ WebUI (โหมด router — ดูจาก bundle: จุดสีเขียว = โหลดแล้ว, ส้ม = หลับ, ไอคอนหมุน =
  // กำลังโหลด, ตัวอักษร text-muted-foreground = ยังไม่โหลด/โหลดพลาด) ไม่ถาม router เอง (ไม่ยิงเครือข่ายเพิ่ม)
  // อ่านไม่ออก (markup เปลี่ยน) = ถือว่าพร้อม ไม่ขวางการสลับ — tooltip ของชิปเตือนเรื่องการโหลดไว้แล้ว
  function optionReady(opt) {
    if (opt.querySelector(".animate-spin, span.bg-green-500, span.bg-orange-400")) return true;
    return !opt.classList.contains("text-muted-foreground");
  }
  function fastVisible() {
    var pm = projectModel();
    return !!(shell() && modelButton() && pm && pm !== FAST_MODEL && shellModels().indexOf(FAST_MODEL) >= 0);
  }
  // force = ข้ามการถามก่อนโหลดโมเดลใหญ่ (API สำหรับ shell/เทสต์) — การกดชิปไม่เคยส่ง force
  function toggleFast(on, force) {
    if (fastBusy || isStreaming() || !fastVisible()) return Promise.resolve(false);
    var cur = currentModel(), want = on == null ? (cur === FAST_MODEL ? projectModel() : FAST_MODEL)
      : (on ? FAST_MODEL : projectModel());
    if (cur === want) { disarmFast(); lsSet(KEY_FAST, want === FAST_MODEL ? "1" : "0"); return Promise.resolve(true); }
    fastApplied = true;                                   // ผู้ใช้สั่งเองแล้ว ไม่ต้องใช้ค่าที่จำไว้ทับอีก
    // กลับไปโมเดลของโปรเจกต์: กดครั้งแรกดูสถานะก่อน ยังไม่โหลด = ถาม · กดซ้ำขณะถามอยู่ = ยืนยันให้โหลด
    var guard = want !== FAST_MODEL && !force && !fastArmed;
    disarmFast();
    var job = pickModel(want, guard);                     // ตั้ง fastBusy ทันที — วาดสถานะ "กำลังสลับ" หลังจากนั้น
    paintFast(false);
    return job.then(function (ok) {
      if (ok === "unloaded") { armFast(want); return false; }
      if (ok) lsSet(KEY_FAST, want === FAST_MODEL ? "1" : "0");
      else if (!shellToast(tx("Couldn't switch the model. Choose it from the model menu instead."), true)) {
        try { console.warn("qwen: fast model switch failed"); } catch (e) {}
      }
      paintFast(isStreaming());
      return ok;
    });
  }
  // ขั้น "ถามก่อนโหลด": ชิปติดกรอบเตือน + tooltip เปลี่ยน + ป้ายเล็กลอยเหนือชิป บอกชื่อโมเดลที่จะถูกโหลด
  // ไม่ใช้ confirm() ของเบราว์เซอร์ (บล็อกทั้งหน้า กล่องของระบบไม่เข้ากับหน้าตาแอป) และไม่ใช้ toast ของ shell: toast อยู่
  // กลางล่างจอ ข้อความยาวจึงทับชิปฝั่งซ้ายพอดี (เห็นจริงที่ 1440) — ป้ายผูกกับชิปอ่านรู้เรื่องกว่า
  // ผู้อ่านจอ: ป้ายที่มองเห็นเป็น aria-hidden ข้อความเดียวกันไปที่ live region ที่มีอยู่ในหน้าตั้งแต่สร้างชิป (ประกาศแน่นอน)
  // หมดเวลา / กด Esc / กดที่อื่น = ยกเลิก กลับเป็นปกติ
  var fastHint = null, fastLive = null;
  function fastLiveEl() {
    if (!fastLive || !fastLive.isConnected) {
      fastLive = el("div", "qw-sr");
      fastLive.setAttribute("role", "status");
      fastLive.setAttribute("aria-live", "polite");
      fastLive.setAttribute("data-qw-no-tx", "");         // ข้อความเป็นภาษาปัจจุบันแล้ว (tx) ตัวแปลไม่ต้องแตะ
      document.body.appendChild(fastLive);
    }
    return fastLive;
  }
  function placeFastHint() {
    if (!fastHint || fastHint.hidden || !fastChip || !fastChip.isConnected) return;
    var r = fastChip.getBoundingClientRect(), vw = document.documentElement.clientWidth || innerWidth;
    var x = Math.round(Math.min(Math.max(8, r.left), vw - fastHint.offsetWidth - 8));
    fastHint.style.left = Math.max(8, x) + "px";
    fastHint.style.bottom = Math.round(innerHeight - r.top + 8) + "px";
  }
  function armFast(model) {
    fastArmed = Date.now();
    clearTimeout(fastArmTimer);
    fastArmTimer = setTimeout(disarmFast, FAST_ARM_MS);
    var msg = tx("{model} isn't loaded yet. Click again to load it and switch back (large model, slow to load).")
      .replace("{model}", modelLabel(model));
    if (!fastHint || !fastHint.isConnected) {
      fastHint = el("div", "qw-fast-hint");
      fastHint.setAttribute("aria-hidden", "true");
      fastHint.setAttribute("data-qw-no-tx", "");
      document.body.appendChild(fastHint);
    }
    fastHint.textContent = msg;
    fastHint.hidden = false;
    placeFastHint();
    // ล้างก่อนแล้วใส่ในจังหวะถัดไป — ข้อความเดิมซ้ำ โปรแกรมอ่านจอจะไม่อ่านอีกรอบถ้าไม่ล้าง
    var live = fastLiveEl();
    live.textContent = "";
    setTimeout(function () { if (fastArmed) live.textContent = msg; }, 60);
    paintFast(isStreaming());
  }
  function disarmFast() {
    if (!fastArmed && !fastArmTimer) return;
    fastArmed = 0;
    clearTimeout(fastArmTimer);
    fastArmTimer = 0;
    if (fastHint) fastHint.hidden = true;
    if (fastLive) fastLive.textContent = "";
    paintFast(isStreaming());
  }
  // ยกเลิกขั้นถาม: Esc หรือกดที่อื่นที่ไม่ใช่ชิป (กดชิปซ้ำ = ยืนยัน ไปทาง click ตามปกติ)
  window.addEventListener("keydown", function (e) { if (fastArmed && e.key === "Escape") disarmFast(); }, true);
  window.addEventListener("pointerdown", function (e) {
    // เฉพาะการกดจริง — pickModel ยิง pointerdown สังเคราะห์ใส่ปุ่มโมเดลเอง
    if (fastArmed && e.isTrusted && !(fastChip && e.target && fastChip.contains(e.target))) disarmFast();
  }, true);
  window.addEventListener("resize", function () { if (fastArmed) placeFastHint(); });
  function makeFastChip() {
    var c = el("button", "qw-fast");
    c.type = "button";
    c.setAttribute("aria-pressed", "false");
    c.setAttribute("title", FAST_TIP);
    c.innerHTML = xIcon("bolt");
    var s = el("span");
    s.textContent = "Fast (4B)";
    c.appendChild(s);
    // กล่องล่างของ WebUI เป็น pointer-events:none ทั้งก้อน (แบบเดียวกับชิปคำแนะนำ)
    c.style.pointerEvents = "auto";
    fastLiveEl();                                         // live region ต้องอยู่ในหน้าก่อนข้อความมา จึงจะถูกประกาศ
    c.addEventListener("click", function (e) {
      e.preventDefault();
      if (c.getAttribute("aria-disabled") === "true") return;
      toggleFast();
    });
    return c;
  }
  function paintFast(st) {
    var c = fastChip;
    if (!c) return;
    var p = currentModel() === FAST_MODEL ? "true" : "false";
    if (c.getAttribute("aria-pressed") !== p) c.setAttribute("aria-pressed", p);
    // ระหว่างตอบ/กำลังสลับ: aria-disabled ไม่ใช่ disabled — ปุ่มที่ถือโฟกัสอยู่จะได้ไม่ทำโฟกัสหลุดไป body
    var dis = st || fastBusy ? "true" : null;
    if (c.getAttribute("aria-disabled") !== dis) { if (dis) c.setAttribute("aria-disabled", dis); else c.removeAttribute("aria-disabled"); }
    var busy = fastBusy ? "true" : null;
    if (c.getAttribute("aria-busy") !== busy) { if (busy) c.setAttribute("aria-busy", busy); else c.removeAttribute("aria-busy"); }
    // กำลังถามก่อนโหลด: เทียบกับต้นฉบับอังกฤษ (โหมดไทยถูกแปลแล้ว) เขียนเฉพาะเมื่อเปลี่ยน ไม่งั้น observer วน
    var arm = fastArmed ? "1" : null, tip = fastArmed ? FAST_ARM_TIP : FAST_TIP;
    if (c.getAttribute("data-armed") !== arm) { if (arm) c.setAttribute("data-armed", arm); else c.removeAttribute("data-armed"); }
    if (enAttr(c, "title") !== tip) c.setAttribute("title", tip);
  }
  // ใช้ "โหมดเร็ว" ที่จำไว้ครั้งเดียวต่อการโหลดหน้า — หลัง WebUI เลือกโมเดลจาก ?model= เสร็จ (มันลบพารามิเตอร์ทิ้งเอง)
  // ต้องรอให้ปุ่มโมเดล "นิ่ง": ตอนโหลด WebUI ใส่ตัวแรกตามตัวอักษร (ซึ่งคือ 4B พอดี) ก่อน แล้วค่อยเปลี่ยนเป็นตัวจาก ?model=
  // ถ้าตัดสินตอนนั้นจะนึกว่าอยู่ในโหมดเร็วแล้ว และไม่สลับให้เลย
  var fastSeen = null, fastSeenAt = 0;
  function maybeApplyFast(st) {
    if (fastApplied || fastBusy || st) return;
    if (lsGet(KEY_FAST) !== "1") { fastApplied = true; return; }
    var cur = currentModel(), now = Date.now();
    if (cur !== fastSeen) { fastSeen = cur; fastSeenAt = now; }
    if (!cur || /[?&]model=/.test(location.search)) return;
    var wait = Math.max(1500 - (now - fastBootAt), 900 - (now - fastSeenAt));
    if (wait > 0) { setTimeout(schedule, wait + 20); return; }
    if (cur === FAST_MODEL) { fastApplied = true; return; }
    if (dialogOpen() || menuOpen() || plusLayerOpen()) return;
    var ta = composer();
    if (ta && document.activeElement === ta && ta.value) return;      // กำลังพิมพ์ — ไว้รอบหน้า
    fastApplied = true;
    pickModel(FAST_MODEL).then(function () { paintFast(isStreaming()); });
  }
  // ผู้ใช้เลือกโมเดลเองจากเมนู = ความตั้งใจล่าสุด → จำตามนั้น (เลือก 4B = โหมดเร็ว, ตัวอื่น = ปิด)
  function noteModelPick(e) {
    if (!e.isTrusted || fastBusy) return;
    var t = e.target;
    if (!t || !t.closest) return;
    var hit = e.type === "keydown"
      ? e.key === "Enter" && t.closest('[data-slot="dropdown-menu-sub-content"], [data-slot="sheet-content"]') && modelOptions().length
      : t.closest('.models-list [role="option"], [data-slot="sheet-content"] [role="option"]');
    if (!hit) return;
    setTimeout(function () {
      var cur = currentModel();
      if (cur && fastVisible()) { lsSet(KEY_FAST, cur === FAST_MODEL ? "1" : "0"); fastApplied = true; }
      schedule();
    }, 800);
  }
  function syncFastChip(st) {
    var b = modelButton();
    if (!fastVisible()) { if (fastChip) detach(fastChip); disarmFast(); return; }
    if (!fastChip) fastChip = makeFastChip();
    // ฝั่งซ้ายของแถวเครื่องมือ ถัดจากกล่องปุ่ม "+" (div.mr-auto > div > button.file-upload-button) — ตำแหน่งไม่ขยับตามชื่อโมเดล
    // หาไม่เจอ (WebUI เปลี่ยนโครงสร้าง) ใช้ที่เดิม: ก่อนกล่องของตัวเลือกโมเดล (div.relative.inline-flex ที่ครอบปุ่ม)
    var plus = plusButton(), grp = plus && plus.closest(".mr-auto"), anchor = null;
    if (grp && composerForm() && composerForm().contains(grp)) {
      for (anchor = plus; anchor && anchor.parentNode !== grp; anchor = anchor.parentNode) {}
    }
    if (anchor) {
      if (fastChip.parentNode !== grp || fastChip.previousElementSibling !== anchor) anchor.after(fastChip);
    } else {
      var host = b.closest("div.relative.inline-flex") || b;
      if (host.parentNode && (fastChip.parentNode !== host.parentNode || fastChip.nextElementSibling !== host)) {
        host.parentNode.insertBefore(fastChip, host);
      }
    }
    paintFast(st);
    maybeApplyFast(st);
  }

  /* ---- K7: "เปิดในแผง" ที่บล็อกโค้ด html/svg/mermaid/markdown/csv และภาพกราฟ ------------------------------ */
  // shell วาดแผงด้านขวาเป็น iframe sandbox (ไม่มี network/same-origin) — ที่นี่แค่ส่งซอร์สไปให้
  // id คงที่ข้ามรุ่น (สร้างคำตอบใหม่/แก้แล้วตอบใหม่) เพื่อให้ shell เก็บเป็นเวอร์ชันของชิ้นเดียวกัน:
  //   มีชื่อในเนื้อหา (<title>, # หัวข้อ, ชื่อไฟล์ภาพ) = แชต + ชนิด + ชื่อ  ไม่มี = แชต + ลำดับคำตอบ + ลำดับบล็อกชนิดนั้น
  var ART_KINDS = { html: "html", htm: "html", xhtml: "html", svg: "svg", mermaid: "mermaid",
    markdown: "markdown", md: "markdown", csv: "csv" };
  var ART_LABEL = { html: "HTML page", svg: "SVG image", mermaid: "Mermaid diagram", markdown: "Markdown document",
    csv: "CSV table", image: "Chart image" };
  var ART_WRAP = ".code-block-wrapper, .svg-block-wrapper, .mermaid-block-wrapper";
  function canOpenArtifact() {
    var api = shellApi();
    return !!(api && typeof api.openArtifact === "function");
  }
  function blockKind(w) {
    if (w.classList.contains("svg-block-wrapper")) return "svg";
    if (w.classList.contains("mermaid-block-wrapper")) return "mermaid";
    var l = w.querySelector(".code-language"), k = l ? enText(l).trim().toLowerCase() : "";
    return hasOwn(ART_KINDS, k) ? ART_KINDS[k] : null;
  }
  function blockCode(w, kind) {
    var p;
    if (kind === "svg") { p = w.querySelector("pre.svg-block[data-svg-source]"); return p ? p.getAttribute("data-svg-source") : ""; }
    if (kind === "mermaid") { p = w.querySelector("pre.mermaid[data-mermaid-syntax]"); return p ? p.getAttribute("data-mermaid-syntax") : ""; }
    p = w.querySelector("pre code");
    return p ? p.textContent : "";
  }
  function artTitle(kind, code) {
    var m = null;
    if (kind === "html") m = /<title[^>]*>([^<]{1,160})<\/title>/i.exec(code) || /<h1[^>]*>([\s\S]{1,300}?)<\/h1>/i.exec(code);
    else if (kind === "svg") m = /<title[^>]*>([^<]{1,160})<\/title>/i.exec(code);
    else if (kind === "markdown") m = /^ {0,3}#{1,3}[ \t]+(.{1,160})$/m.exec(code);
    return m ? clip(m[1].replace(/<[^>]*>/g, " "), 80) : "";
  }
  function artId(kind, msg, idx, key) {
    var ms = document.querySelectorAll(".chat-message-assistant");
    var mi = Array.prototype.indexOf.call(ms, msg);
    return (route().id || "start") + ":" + kind + ":" + (key ? "t:" + key.toLowerCase() : "m" + mi + "b" + idx);
  }
  function blockPayload(w) {
    var kind = blockKind(w), msg = w.closest(".chat-message-assistant");
    if (!kind || !msg) return null;
    var code = blockCode(w, kind), idx = 0, all = msg.querySelectorAll(ART_WRAP);
    for (var i = 0; i < all.length && all[i] !== w; i++) if (blockKind(all[i]) === kind) idx++;
    var t = artTitle(kind, code);
    return { id: artId(kind, msg, idx, t), kind: kind, title: t || tx(ART_LABEL[kind]), code: code };
  }
  // ภาพที่ควรเปิดในแผง: ผลจากเครื่องมือ Python ที่ hub เสิร์ฟจาก /_qwen/out/ และภาพฝังในข้อความ (data:image)
  function artImage(img) {
    var src = img.getAttribute("src") || "";
    return /^data:image\//i.test(src) || /^\/_qwen\/out\/[^/]/.test(src) || img.src.indexOf(location.origin + "/_qwen/out/") === 0;
  }
  function imagePayload(img) {
    var msg = img.closest(".chat-message-assistant");
    if (!msg) return null;
    var m = /\/_qwen\/out\/([^?#]+)/.exec(img.src), file = "";
    if (m) { try { file = decodeURIComponent(m[1]); } catch (e) { file = m[1]; } }
    var alt = (img.getAttribute("alt") || "").trim(), idx = 0, all = msg.querySelectorAll(".markdown-content img");
    for (var i = 0; i < all.length && all[i] !== img; i++) if (artImage(all[i])) idx++;
    // alt สั้นๆ แบบ "fig"/"image" ไม่ใช่ชื่อที่บอกอะไร
    var t = alt && !/^(fig(ure)?|image|img|chart|plot|png)\d*$/i.test(alt) ? clip(alt, 80) : file;
    return { id: artId("image", msg, idx, file), kind: "image", title: t || tx(ART_LABEL.image), code: img.src, src: img.src };
  }
  // จำรุ่นล่าสุดที่ส่งให้ shell ต่อ id (โค้ด + ชนิด + ชื่อ) — ใช้ตัดสินว่าแผงกำลังแสดงชิ้นของเรา และรุ่นใหม่ต่างจากเดิมไหม
  var artSent = {};
  function openPayload(p) {
    if (!p) return;
    artSent[p.id] = { code: p.code, kind: p.kind, title: p.title };
    callShell("openArtifact", p);
  }

  // ---- แผงตามรุ่นใหม่ (แก้หลังรีวิว UX รอบ 4): เปิด "สถานะตู้ชาร์จ" v1 ในแผงไว้ แล้วกด Regenerate / ขอแก้ ได้บล็อกใหม่
  // id เดิม (id ผูกกับชื่อ/ตำแหน่ง ไม่ใช่เนื้อหา) — เดิมแผงค้าง v1 จนผู้ใช้กด "เปิดในแผง" อีกครั้ง
  // ตอนนี้: คำตอบจบ (ไม่ได้กดหยุดเอง) → ตั้งธง → รอบ pass ถัดๆ ไปที่ DOM ของคำตอบล่าสุดวาดครบ (แท็บมองเห็นอยู่) หาบล็อกที่
  // id ตรงกับชิ้นที่แผงแสดงอยู่ + โค้ดต่างจากที่ส่งไป → ส่งเป็นรุ่นใหม่ (shell ต่อท้ายเวอร์ชันเอง ไม่แย่งโฟกัสเมื่อเป็นชิ้นเดิม)
  // ส่งเฉพาะเมื่อโค้ดนิ่งแล้ว (อ่านซ้ำห่าง 500ms ได้เท่ากัน) — กันส่งบล็อกที่ markdown ยังวาดไม่ครบเป็นรุ่นหนึ่ง
  var artFollow = null, artFollowTimer = 0;
  function armArtFollow(chatId) {
    artFollow = chatId && !(userStopAt && userStopAt >= streamStartAt) ? { chat: chatId, vis: 0 } : null;
    if (artFollow) schedule();
  }
  // แผงของ shell แสดงชิ้น id นี้อยู่ไหม — shell รุ่นที่มี artifactState() ตอบตรงๆ; รุ่นนี้ยังไม่มี จึงดูจากแผงเอง
  // (origin เดียวกัน อ่านอย่างเดียว): เปิดอยู่ + ชนิดตรง (#art.k-<kind>) + หัวเรื่องตรงกับที่เราส่ง id นี้ไปล่าสุด
  // ผู้ใช้เลือกชิ้นอื่นจากรายการในแผงไปแล้ว = หัวเรื่องไม่ตรง = ไม่ดึงแผงกลับมา
  function panelShows(p) {
    var api = shellApi();
    if (api && typeof api.artifactState === "function") {
      try { var s = api.artifactState(); return !!(s && s.open && s.id === p.id); } catch (e) { return false; }
    }
    var sent = hasOwn(artSent, p.id) ? artSent[p.id] : null;
    if (!sent) return false;
    try {
      var d = window.parent.document, a = d.getElementById("art"), t = d.getElementById("artTitle");
      return !!(a && !a.hidden && t && a.classList.contains("k-" + p.kind) && t.textContent === sent.title);
    } catch (e) { return false; }
  }
  function followCandidates() {
    var m = lastAssistant(), out = [];
    if (!m) return out;
    var ws = m.querySelectorAll(ART_WRAP);
    for (var i = 0; i < ws.length; i++) {
      if (!blockKind(ws[i])) continue;
      var p = blockPayload(ws[i]);
      if (p && p.code && panelShows(p) && (!hasOwn(artSent, p.id) || artSent[p.id].code !== p.code)) out.push(p);
    }
    return out;
  }
  function followArtifacts(st) {
    if (!artFollow || st || artFollowTimer) return;
    if (route().id !== artFollow.chat || !canOpenArtifact()) { artFollow = null; return; }
    if (document.hidden) return;                          // DOM ของคำตอบยังไม่ถูกวาดตอนแท็บซ่อน — รอกลับมา
    if (!artFollow.vis) artFollow.vis = Date.now();
    var c = followCandidates();
    if (!c.length) {
      // มองเห็นแล้ว 5 วิยังไม่มีบล็อกที่ตรง = คำตอบนี้ไม่ได้แก้ชิ้นในแผง เลิกเฝ้า
      if (Date.now() - artFollow.vis > 5000) artFollow = null;
      return;
    }
    var f = artFollow;
    artFollowTimer = setTimeout(function () {
      artFollowTimer = 0;
      try {
        if (artFollow !== f || isStreaming() || route().id !== f.chat) return;
        var again = followCandidates(), sent = false;
        for (var i = 0; i < again.length; i++) {
          for (var j = 0; j < c.length; j++) {
            if (again[i].id === c[j].id && again[i].code === c[j].code) { openPayload(again[i]); sent = true; }
          }
        }
        if (sent) artFollow = null; else schedule();       // ยังเปลี่ยนอยู่ — ลองรอบหน้า
      } catch (e) { artFollow = null; }
    }, 500);
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden && artFollow) schedule(); });
  function makeArtBtn() {
    var b = xButton("qw-art-btn", "Open in panel", "panel");
    b.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var w = b.closest(ART_WRAP);
      if (w) openPayload(blockPayload(w));
    });
    return b;
  }
  function makeImgBtn() {
    var b = el("button", "qw-img-art");
    b.type = "button";
    b.innerHTML = xIcon("panel");
    var s = el("span");
    s.textContent = "Open in panel";
    b.appendChild(s);
    b.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var img = b.previousElementSibling;
      if (img && img.tagName === "IMG") openPayload(imagePayload(img));
    });
    return b;
  }
  function syncArtifacts(st) {
    var ok = canOpenArtifact(), last = st ? lastAssistant() : null;
    // ระหว่างสตรีม บล็อกของคำตอบล่าสุดยังไม่ครบ ("Code incomplete") — ใส่ปุ่มหลังตอบจบ
    var heads = document.querySelectorAll(".chat-message-assistant .code-block-header");
    for (var i = 0; i < heads.length; i++) {
      var h = heads[i], w = h.parentElement, acts = h.querySelector(".code-block-actions");
      if (!acts || !w) continue;
      var mine = acts.querySelector(".qw-art-btn");
      var want = ok && !(last && last.contains(h)) && w.matches(ART_WRAP) && !!blockKind(w);
      if (want && !mine) acts.insertBefore(makeArtBtn(), acts.firstChild);
      else if (!want && mine) detach(mine);
    }
    var imgs = document.querySelectorAll(".chat-message-assistant .markdown-content img");
    for (var j = 0; j < imgs.length; j++) {
      var img = imgs[j], nx = img.nextElementSibling, has = !!(nx && nx.classList.contains("qw-img-art"));
      var wantImg = ok && !(last && last.contains(img)) && artImage(img);
      if (wantImg && !has) img.after(makeImgBtn());
      else if (!wantImg && has) detach(nx);
    }
    if (!ok) {                                            // shell ถอดความสามารถออก — เก็บปุ่มที่ค้างอยู่ให้หมด
      var left = document.querySelectorAll(".qw-art-btn, .qw-img-art");
      for (var k = 0; k < left.length; k++) detach(left[k]);
    }
  }

  /* ---- K8: อ่านออกเสียงคำตอบ ------------------------------------------------------------------------ */
  // speechSynthesis ของเบราว์เซอร์ ใช้เฉพาะเสียงในเครื่อง (localService) — Edge มีเสียง "Online (Natural)" ด้วย
  // ซึ่งส่งข้อความไปสังเคราะห์บนคลาวด์ ข้อความแชตของโปรเจกต์ (log ของตู้ชาร์จ ฯลฯ) ต้องไม่ออกจากเครื่องโดยผู้ใช้ไม่รู้
  // เครื่องนี้มี Microsoft Pattara (th-TH) + David/Zira/Mark (en-US) ในเครื่อง
  // หยุดชั่วคราว = cancel แล้วจำชิ้นที่อ่านอยู่ (pause()/resume() ของ Chromium ค้างบ่อยกับเสียง SAPI) อ่านต่อ = เริ่มชิ้นนั้นใหม่
  // ชิ้นละ ≤ ~200 ตัวอักษร แบ่งตามช่วงภาษา: ย่อหน้าไทยใช้เสียงไทย (คำอังกฤษสั้นๆ ในประโยคไทยอ่านด้วยเสียงไทยต่อไป)
  var SPK = { msg: null, chunks: [], i: 0, state: "idle", gen: 0, utt: null, errs: 0 };
  var THAI_CH = /[฀-๿]/;
  var SPEAK_DROP = "pre, .code-block-wrapper, .svg-block-wrapper, .mermaid-block-wrapper, img, svg, button, " +
    ".katex-mathml, script, style, textarea";
  function speechOk() { return !!(window.speechSynthesis && window.SpeechSynthesisUtterance); }
  function speakText(msg) {
    var parts = [], mcs = msg.querySelectorAll(".markdown-content");
    for (var i = 0; i < mcs.length; i++) {
      var mc = mcs[i];
      // การคิดของโมเดล และผลลัพธ์ของเครื่องมือ (กล่องยุบ) ไม่ใช่คำตอบ
      if (mc.closest(".reasoning-content, [data-slot='collapsible-content']")) continue;
      var c = mc.cloneNode(true), rm = c.querySelectorAll(SPEAK_DROP), j;
      for (j = 0; j < rm.length; j++) detach(rm[j]);
      // ก้อนที่ถอดออกจากหน้าไม่มี innerText ตามเลย์เอาต์ — ใส่ขึ้นบรรทัดหลังบล็อกและคั่นช่องตารางเอง
      var bl = c.querySelectorAll("p, li, h1, h2, h3, h4, h5, h6, blockquote, tr, dt, dd, br");
      for (j = 0; j < bl.length; j++) bl[j].appendChild(document.createTextNode("\n"));
      var cells = c.querySelectorAll("td, th");
      for (j = 0; j < cells.length; j++) cells[j].appendChild(document.createTextNode(", "));
      parts.push(c.textContent);
    }
    return parts.join("\n").replace(/⁠/g, "").replace(/[ \t ]+/g, " ").replace(/ ?\n[\s]*/g, "\n").trim();
  }
  function speakChunks(text) {
    var out = [];
    text.split(/\n+/).forEach(function (para) {
      var words = para.split(/\s+/).filter(Boolean);
      if (!words.length) return;
      var hasThai = THAI_CH.test(para), runs = [];
      words.forEach(function (w) {
        var th = THAI_CH.test(w), r = runs[runs.length - 1];
        if (r && r.th === th) r.w.push(w); else runs.push({ th: th, w: [w] });
      });
      // คำอังกฤษ < 4 คำกลางย่อหน้าไทย (BootNotification, Heartbeat, 3 kW) ให้เสียงไทยอ่านต่อ ไม่สลับเสียงถี่ๆ
      if (hasThai) runs.forEach(function (r) { if (!r.th && r.w.length < 4) r.th = true; });
      var merged = [];
      runs.forEach(function (r) {
        var p = merged[merged.length - 1];
        if (p && p.th === r.th) p.w = p.w.concat(r.w); else merged.push({ th: r.th, w: r.w.slice() });
      });
      merged.forEach(function (r) {
        var cur = "";
        r.w.forEach(function (w) {
          var next = cur ? cur + " " + w : w;
          // ตัดที่จุดจบประโยคเมื่อยาวพอ หรือบังคับตัดเมื่อเกิน 200 ตัวอักษร
          if (cur && (next.length > 200 || (/[.!?:;]$/.test(cur) && cur.length > 80))) {
            out.push({ text: cur, lang: r.th ? "th-TH" : "en-US" });
            cur = w;
          } else cur = next;
        });
        if (cur) out.push({ text: cur, lang: r.th ? "th-TH" : "en-US" });
      });
    });
    return out;
  }
  function pickVoice(lang) {
    var vs = [];
    try { vs = window.speechSynthesis.getVoices() || []; } catch (e) {}
    var local = vs.filter(function (v) { return v.localService; }), pre = lang.slice(0, 2).toLowerCase();
    function find(test) { for (var i = 0; i < local.length; i++) if (test(local[i])) return local[i]; return null; }
    return find(function (v) { return v.lang === lang && v.default; }) ||
      find(function (v) { return v.lang === lang; }) ||
      find(function (v) { return (v.lang || "").toLowerCase().slice(0, 2) === pre; }) ||
      // ไม่มีเสียงของภาษานี้ในเครื่อง: ใช้เสียงในเครื่องตัวหลัก (ไม่ปล่อยให้เบราว์เซอร์หยิบเสียงออนไลน์เอง)
      find(function (v) { return v.default; }) || local[0] || null;
  }
  function voicesReady() {
    var ss = window.speechSynthesis;
    try { if (ss.getVoices().length) return Promise.resolve(); } catch (e) { return Promise.resolve(); }
    return new Promise(function (res) {
      var done = false;
      function fin() { if (done) return; done = true; try { ss.removeEventListener("voiceschanged", fin); } catch (e) {} res(); }
      try { ss.addEventListener("voiceschanged", fin); } catch (e) {}
      setTimeout(fin, 1500);
    });
  }
  function speakNext(gen) {
    if (gen !== SPK.gen || SPK.state !== "playing") return;
    if (!SPK.msg || !SPK.msg.isConnected || SPK.i >= SPK.chunks.length) { stopSpeaking(); return; }
    var c = SPK.chunks[SPK.i], u = new SpeechSynthesisUtterance(c.text), v = pickVoice(c.lang);
    u.lang = v ? v.lang : c.lang;
    if (v) u.voice = v;
    u.onend = function () {
      if (gen !== SPK.gen || SPK.state !== "playing") return;
      SPK.errs = 0;
      SPK.i++;
      speakNext(gen);
    };
    u.onerror = function (e) {
      if (gen !== SPK.gen) return;                        // จาก cancel() ของเราเอง (หยุด/หยุดชั่วคราว)
      var err = e && e.error;
      if (err === "interrupted" || err === "canceled") return;
      // ชิ้นที่สังเคราะห์ไม่ได้ข้ามไป แต่พังติดกันหลายชิ้น = เสียงใช้ไม่ได้ เลิกอ่าน
      if (++SPK.errs >= 3 || err === "not-allowed") { stopSpeaking(); return; }
      SPK.i++;
      speakNext(gen);
    };
    SPK.utt = u;                                          // ถือไว้กัน GC เก็บก่อน onend มา (บั๊กเก่าของ Chromium)
    try { window.speechSynthesis.speak(u); } catch (e) { stopSpeaking(); }
  }
  function startSpeaking(msg) {
    stopSpeaking();
    var chunks = speakChunks(speakText(msg));
    if (!chunks.length) return;
    SPK.msg = msg; SPK.chunks = chunks; SPK.i = 0; SPK.errs = 0; SPK.state = "playing";
    var g = ++SPK.gen;
    paintSpeakAll();
    voicesReady().then(function () { speakNext(g); });
  }
  function pauseSpeaking() {
    if (SPK.state !== "playing") return;
    SPK.state = "paused";
    SPK.gen++;
    try { window.speechSynthesis.cancel(); } catch (e) {}
    paintSpeakAll();
  }
  function resumeSpeaking() {
    if (SPK.state !== "paused") return;
    SPK.state = "playing";
    var g = ++SPK.gen;
    paintSpeakAll();
    speakNext(g);
  }
  function stopSpeaking() {
    if (SPK.state === "idle" && !SPK.msg) return;
    SPK.gen++;
    SPK.state = "idle";
    SPK.msg = null;
    SPK.chunks = [];
    SPK.utt = null;
    try { window.speechSynthesis.cancel(); } catch (e) {}
    paintSpeakAll();
  }
  function copyBtnOf(msg) {
    for (var c = msg.firstElementChild; c; c = c.nextElementSibling) {
      if (c.classList.contains("info") || c.classList.contains("agentic-content")) continue;
      var b = c.querySelector('button[aria-label="Copy"]');
      if (b) return b;
    }
    return null;
  }
  var SPEAK_UI = {
    idle: ["Read aloud", "speak"], playing: ["Pause reading", "pause"], paused: ["Resume reading", "play"]
  };
  function paintSpeak(btn) {
    var m = btn.closest(".chat-message-assistant"), mine = !!m && m === SPK.msg;
    var state = mine ? SPK.state : "idle", ui = SPEAK_UI[state] || SPEAK_UI.idle;
    if (btn.getAttribute("data-state") !== state) btn.setAttribute("data-state", state);
    setXLabel(btn, ui[0]);
    if (btn.__qwIcon !== ui[1]) { btn.__qwIcon = ui[1]; btn.innerHTML = xIcon(ui[1]); }
    var stop = btn.nextElementSibling, hasStop = !!(stop && stop.classList.contains("qw-speak-stop"));
    if (mine && state !== "idle" && !hasStop) {
      stop = xButton("qw-speak-stop", "Stop reading", "stop");
      stop.addEventListener("click", function (e) { e.preventDefault(); stopSpeaking(); try { btn.focus({ preventScroll: true }); } catch (x) {} });
      btn.after(stop);
    } else if ((!mine || state === "idle") && hasStop) {
      // ปุ่มหยุดที่ถือโฟกัสอยู่กำลังจะหายไป — ส่งโฟกัสคืนให้ปุ่มอ่าน ไม่ปล่อยตกไปที่ body
      if (document.activeElement === stop) try { btn.focus({ preventScroll: true }); } catch (x) {}
      detach(stop);
    }
  }
  function paintSpeakAll() {
    var bs = document.querySelectorAll(".qw-speak");
    for (var i = 0; i < bs.length; i++) paintSpeak(bs[i]);
  }
  function makeSpeakBtn() {
    var b = xButton("qw-speak", "Read aloud", "speak");
    b.__qwIcon = "speak";
    b.setAttribute("data-state", "idle");
    b.addEventListener("click", function (e) {
      e.preventDefault();
      var m = b.closest(".chat-message-assistant");
      if (!m) return;
      if (SPK.msg === m && SPK.state === "playing") pauseSpeaking();
      else if (SPK.msg === m && SPK.state === "paused") resumeSpeaking();
      else startSpeaking(m);
    });
    return b;
  }
  function syncSpeak(st) {
    if (!speechOk()) return;
    var ms = document.querySelectorAll(".chat-message-assistant"), last = ms[ms.length - 1];
    for (var i = 0; i < ms.length; i++) {
      var m = ms[i], copy = copyBtnOf(m), have = m.querySelector(".qw-speak");
      // คำตอบที่กำลังสตรีมยังไม่ครบ — ปุ่มโผล่เมื่อตอบจบ (ตัวที่กำลังอ่านอยู่ไม่ถอด)
      if (!copy || (st && m === last && SPK.msg !== m)) {
        if (have) {
          var orphan = have.nextElementSibling;
          if (orphan && orphan.classList.contains("qw-speak-stop")) detach(orphan);
          detach(have);
        }
        continue;
      }
      if (!have) have = makeSpeakBtn();
      if (copy.nextElementSibling !== have) {
        var stop = have.nextElementSibling;
        copy.after(have);
        if (stop && stop.classList && stop.classList.contains("qw-speak-stop")) have.after(stop);
      }
      paintSpeak(have);
    }
    if (SPK.msg && !SPK.msg.isConnected) stopSpeaking();  // ข้อความถูกลบ/วาดใหม่
  }

  /* ---- K9: เลือกข้อความในคำตอบ → "ถามเรื่องนี้" ------------------------------------------------------ */
  // ปุ่มลอย (position:fixed ใน iframe) ใต้ปลายส่วนที่เลือก — ถ้าไปชนกล่องพิมพ์ให้ขึ้นไปอยู่เหนือจุดเริ่มแทน
  // กดแล้วเติมกล่องพิมพ์เป็น Markdown quote + บรรทัดว่าง (ข้อความที่พิมพ์ค้างไว้ต่อท้าย ไม่หาย)
  var quoteBtn = null, quoteTimer = 0;
  function selectionInReply() {
    var s = window.getSelection ? window.getSelection() : null;
    if (!s || s.isCollapsed || !s.rangeCount) return null;
    function host(n) {
      var e = n && (n.nodeType === 1 ? n : n.parentElement);
      return e && e.closest ? e : null;
    }
    var a = host(s.anchorNode), f = host(s.focusNode);
    if (!a || !f) return null;
    var m = a.closest(".chat-message-assistant");
    if (!m || f.closest(".chat-message-assistant") !== m) return null;
    // ต้องอยู่ในเนื้อคำตอบ/การคิด ไม่ใช่แถวสถิติหรือปุ่ม
    if (!a.closest(".markdown-content, .reasoning-content") && !f.closest(".markdown-content, .reasoning-content")) return null;
    if (a.closest("textarea, input, button, [contenteditable]")) return null;
    var text = s.toString().replace(/⁠/g, "").replace(/\r\n?/g, "\n").trim();
    return text ? { range: s.getRangeAt(0), text: text.slice(0, 4000) } : null;
  }
  function makeQuoteBtn() {
    var b = el("button", "qw-quote");
    b.type = "button";
    b.hidden = true;
    b.innerHTML = xIcon("quote");
    var s = el("span");
    s.textContent = "Ask about this";
    b.appendChild(s);
    // กดแล้วห้ามล้างส่วนที่เลือกก่อน click จะมาถึง
    b.addEventListener("pointerdown", function (e) { e.preventDefault(); });
    b.addEventListener("mousedown", function (e) { e.preventDefault(); });
    b.addEventListener("click", function (e) {
      e.preventDefault();
      var sel = selectionInReply(), text = sel ? sel.text : b.__qwText;
      hideQuote();
      if (!text) return;
      var q = text.split("\n").map(function (l) { return l.trim() ? "> " + l.replace(/\s+$/, "") : ">"; })
        .join("\n").replace(/(\n>)+$/, "");
      var ta = composer(), cur = ta ? ta.value.replace(/^\s+/, "") : "";
      // ล้างส่วนที่เลือกก่อนเติม — ล้างทีหลัง Chromium พาเคอร์เซอร์ในกล่องพิมพ์กลับไปต้นข้อความ
      try { window.getSelection().removeAllRanges(); } catch (x) {}
      prefill(q + "\n\n" + cur);
    });
    document.body.appendChild(b);
    return b;
  }
  function hideQuote() {
    if (quoteBtn && !quoteBtn.hidden) quoteBtn.hidden = true;
  }
  function placeQuote() {
    quoteTimer = 0;
    var sel = selectionInReply();
    if (!sel) { hideQuote(); return; }
    if (!quoteBtn || !quoteBtn.isConnected) quoteBtn = makeQuoteBtn();
    var rs = sel.range.getClientRects(), first = rs[0], lastR = rs[rs.length - 1];
    if (!first) { var br = sel.range.getBoundingClientRect(); first = lastR = br; }
    var vw = document.documentElement.clientWidth || innerWidth, vh = innerHeight;
    if (lastR.bottom < 0 || first.top > vh) { hideQuote(); return; }   // เลื่อนจนส่วนที่เลือกพ้นจอ
    quoteBtn.__qwText = sel.text;
    quoteBtn.hidden = false;
    var bw = quoteBtn.offsetWidth, bh = quoteBtn.offsetHeight;
    var form = composerForm(), limit = form ? form.getBoundingClientRect().top - 8 : vh - 8;
    var x = Math.round(Math.min(Math.max(8, lastR.right - bw / 2), vw - bw - 8));
    var y = Math.round(lastR.bottom + 8);
    if (y + bh > limit) {
      y = Math.round(first.top - bh - 8);
      x = Math.round(Math.min(Math.max(8, first.left), vw - bw - 8));
    }
    y = Math.max(8, Math.min(y, vh - bh - 8));
    quoteBtn.style.left = x + "px";
    quoteBtn.style.top = y + "px";
  }
  function quoteSoon() {
    if (quoteTimer) clearTimeout(quoteTimer);
    quoteTimer = setTimeout(function () { try { placeQuote(); } catch (e) { hideQuote(); } }, 120);
  }

  /* ---- batch 2a (fix, owner stack): แชตที่เริ่มจากชิปสกิล (MCP prompt) ได้ชื่อตามสกิล -------------------------- */
  // WebUI ตั้งชื่อแชตจากเนื้อความของข้อความแรกเท่านั้น (sendMessage: `s && e && applyTitleFromContent(...)`) — เลือกสกิล
  // จาก "/prompt" แล้วส่งชิปอย่างเดียว เนื้อความว่าง ชื่อจึงค้างเป็นชื่อชั่วคราว `Chat <วันเวลา>` (shell แสดง
  // "แชตใหม่ · 3:08") ทุกแชตที่เริ่มจากสกิลจึงหน้าตาเหมือนกันหมดใน Recents
  // ส่วนนี้แค่บอก shell ว่าแชตนี้เพิ่งเริ่ม/จบการตอบ — shell อ่านข้อความแรกแล้วตั้งชื่อเอง (nameSkillChat ใน hub_i18n_parts.py)
  // เพราะโมดูลนี้ไม่เขียนฐานข้อมูลของ WebUI (สัญญารอบ 4) การเขียนชื่อแชตเป็นของ shell ที่เดียว เหมือนเปลี่ยนชื่อ/ลบแชต
  // เรียกตอนเริ่มตอบ (ข้อความผู้ใช้ถูกบันทึกก่อนสตรีมเสมอ — รอให้ hash เป็น #/chat/<id> ก่อน) และตอนตอบจบ (สำรอง)
  // shell จำแชตที่ตัดสินแล้วเอง (ไม่เปิดฐานข้อมูลซ้ำ) ไม่มี shell (เปิด /?ui=1 ตรงๆ) = ไม่ทำอะไร
  var skillTimer = 0;
  function skillTitleSoon(ms) {
    if (skillTimer) clearTimeout(skillTimer);
    skillTimer = setTimeout(function () {
      skillTimer = 0;
      var r = route(), api = shellApi();
      if (r.name !== "chat" || !r.id || !api || typeof api.nameSkillChat !== "function") return;
      try { api.nameSkillChat(r.id); } catch (e) { /* shell พังต้องไม่ลากหน้าแชตพังตาม */ }
    }, ms);
  }

  /* ---- รวมทุกส่วน: เรียกท้าย pass() ------------------------------------------------------------------ */
  var extrasRouteKey = null;
  function extrasPass(r, st) {
    var key = r.name + ":" + (r.id || "");
    if (key !== extrasRouteKey) {                         // เปลี่ยนแชต: เลิกอ่าน ซ่อนปุ่มถาม
      extrasRouteKey = key;
      try { stopSpeaking(); hideQuote(); } catch (e) {}
    }
    try { syncFastChip(st); } catch (e) {}
    try { syncArtifacts(st); } catch (e) {}
    try { followArtifacts(st); } catch (e) { artFollow = null; }
    try { syncSpeak(st); } catch (e) {}
    try { scanPrompts(); } catch (e) {}
    try { b2bPass(r, st); } catch (e) {}                 // batch 2b (C4): ไมค์ · วางแผนก่อน · @ไฟล์
    try { b3Pass(r); } catch (e) {}                      // batch 3 (D4): ป้าย "สรุปช่วงต้นของบทสนทนาแล้ว" (ท้ายไฟล์)
  }
  ["pointerdown", "keydown"].forEach(function (t) { window.addEventListener(t, noteUserStop, true); });
  ["click", "keydown"].forEach(function (t) { window.addEventListener(t, noteModelPick, true); });
  document.addEventListener("selectionchange", quoteSoon);
  window.addEventListener("pointerup", quoteSoon, true);
  window.addEventListener("keyup", function (e) { if (e.shiftKey || e.key === "Shift" || /^Arrow/.test(e.key)) quoteSoon(); }, true);
  window.addEventListener("scroll", function () { if (quoteBtn && !quoteBtn.hidden) quoteSoon(); }, { capture: true, passive: true });
  window.addEventListener("resize", function () { if (quoteBtn && !quoteBtn.hidden) quoteSoon(); });
  window.addEventListener("pagehide", function () { try { stopSpeaking(); } catch (e) {} });

  /* ---- API ------------------------------------------------------------------ */
  window.qwenEnhance = {
    version: "1",
    route: route,
    newChat: newChat,
    openChat: openChat,
    openSearch: openSearch,
    openSettings: openSettings,
    openMcp: openMcp,
    prefill: prefill,
    focusComposer: focusComposer,
    isStreaming: isStreaming,
    applyTheme: applyTheme,
    setFont: setFont,
    // นอกสัญญา: ให้ shell สั่งอ่าน qwenShell ใหม่ (เช่นเปลี่ยนชื่อโปรเจกต์โดยไม่โหลดหน้า)
    refresh: function () { chips.removeAttribute("data-lang"); routeDelivered = false; pass(); },
    // สลับภาษา th ⇄ en สดๆ (คืนต้นฉบับอังกฤษทุกจุดเมื่อไป en) คืน true เมื่อรับค่า
    setLang: setLang,
    lang: lang,
    // สถิติของตัวแปล (ใช้วัดว่าระหว่างสตรีมเสียเวลาต่อรอบเท่าไร): {batches, records, ms, maxMs}
    txStats: function (reset) {
      var s = { batches: txStat.batches, records: txStat.records, ms: txStat.ms, maxMs: txStat.maxMs };
      if (reset) { txStat.batches = txStat.records = 0; txStat.ms = txStat.maxMs = 0; }
      return s;
    },
    // ---- รอบ 4 (นอกสัญญา 5b): ให้ shell/การทดสอบถามสถานะหรือสั่งได้ ----
    // โมเดลที่ปุ่มโมเดลแสดงอยู่ + โหมดเร็ว: {current, fast, project, remembered, available}
    fastModel: function () {
      var cur = currentModel();
      return { current: cur, fast: cur === FAST_MODEL, project: projectModel(),
        remembered: lsGet(KEY_FAST) === "1", available: fastVisible(), armed: !!fastArmed };
    },
    // true/false = เปิด/ปิดโหมดเร็ว, ไม่ส่ง = สลับ → Promise<boolean> (สลับผ่านเมนูโมเดลของ WebUI)
    // ปิดไปหาโมเดลที่ยังไม่โหลด: ครั้งแรกคืน false + ชิปขึ้นสถานะถาม (fastModel().armed) · force=true = ไม่ถาม
    setFast: function (on, force) { return toggleFast(on == null ? null : !!on, !!force); },
    stopSpeaking: function () { stopSpeaking(); },
    speechState: function () { return { state: SPK.state, chunk: SPK.i, chunks: SPK.chunks.length }; },
    // ข้อความคำตอบล่าสุดของแชตที่เปิดอยู่ จาก IndexedDB (ตัวเดียวกับเนื้อความการแจ้งเตือน "ตอบเสร็จ") → Promise<string>
    lastReply: function () { return replyFromDb(route().id); },
    // ---- รอบ 5 แก้หลังรีวิว: สถิติของด่าน ALLOW-GUARD (ให้การทดสอบ/การตรวจดูว่าติดตั้งแล้วและทำงานกี่ครั้ง) ----
    // {installed, stripped, deleted, reloads}
    allowGuard: function () {
      var s = ALLOW_GUARD.stats;
      return { installed: !!s.installed, stripped: s.stripped, deleted: s.deleted, reloads: s.reloads };
    }
  };

  /* ======================================================================================
     batch 2b (2026-10-01, owner ui) — สัญญา C4: ไมค์ (พูดแทนพิมพ์) · วางแผนก่อน · @ไฟล์ของโปรเจกต์ · Office
     วางไว้หลังออบเจกต์ API (ไม่อยู่ในช่วงที่เทสต์รอบ 4/5 ตัดไปตรวจว่า "ห้ามเรียกเครือข่าย") เพราะส่วนนี้ต้องเรียก
     เส้นทางของ hub บน origin เดียวกันเอง: POST /_qwen/stt (ถอดเสียง), GET /_qwen/files + /_qwen/out/ (รายชื่อไฟล์)
     และห่อ window.fetch เพื่อติด X-Qwen-Plan: 1 ให้คำขอแชตของ WebUI ในแชตที่เปิดโหมดวางแผน
     ความปลอดภัยไม่ได้พึ่งส่วนนี้: hub เป็นคนตัดเครื่องมือที่เปลี่ยนเครื่องออกเมื่อเห็น header (โหมดวางแผน "บังคับ" ที่ฝั่ง hub)
     header นี้ทำได้แค่ "จำกัด" สิ่งที่โมเดลทำได้ ไม่มีทางเพิ่มสิทธิ์ — ส่วนนี้พังหรือถูกข้าม = กลับไปเป็นแชตปกติเท่านั้น
     ทุกชิ้นที่ใส่ลง DOM มี data-qw-no-tx (ป้ายเป็นภาษาปัจจุบันจาก L()/A() แล้ว ตัวแปลไม่ต้องแตะ) และสร้างด้วย textContent
     ชื่อไฟล์/ข้อความจากเซิร์ฟเวอร์ไม่เคยผ่าน innerHTML (innerHTML ใช้กับไอคอน svg คงที่เท่านั้น)
     ====================================================================================== */
  var TH_B2B = {
    // ---- ไมค์ ----
    "Voice input": "พูดแทนพิมพ์",
    "Voice input: speak Thai or English, then press again to put the text in the message box":
      "พูดแทนพิมพ์: พูดไทยหรืออังกฤษก็ได้ แล้วกดอีกครั้งเพื่อใส่ข้อความลงช่องพิมพ์",
    "Stop and transcribe": "หยุดและถอดเสียง",
    "Cancel recording": "ยกเลิกการอัดเสียง",
    "Cancel transcription": "ยกเลิกการถอดเสียง",
    "Transcribing…": "กำลังถอดเสียง…",
    "Waiting for microphone permission…": "รออนุญาตให้ใช้ไมโครโฟน…",
    "Recording — press the button again when you're done, Escape to cancel":
      "กำลังอัดเสียง — พูดจบแล้วกดปุ่มอีกครั้ง กด Esc เพื่อยกเลิก",
    "Text from your voice was added to the message box": "ใส่ข้อความจากเสียงลงช่องพิมพ์แล้ว",
    "Recording cancelled": "ยกเลิกการอัดเสียงแล้ว",
    "Voice input is unavailable: the speech service isn't running": "พูดแทนพิมพ์ใช้ไม่ได้: บริการถอดเสียงไม่ทำงาน",
    "Microphone access is blocked. Allow the microphone for this page (icon at the left of the address bar), then try again.":
      "เบราว์เซอร์ไม่ให้ใช้ไมโครโฟน — อนุญาตไมโครโฟนให้หน้านี้ (ไอคอนทางซ้ายของช่องที่อยู่เว็บ) แล้วลองอีกครั้ง",
    "No microphone was found.": "ไม่พบไมโครโฟน",
    "The microphone is being used by another app.": "ไมโครโฟนถูกโปรแกรมอื่นใช้อยู่",
    "This browser can't record audio.": "เบราว์เซอร์นี้อัดเสียงไม่ได้",
    "That was too short — hold on and speak a little longer.": "สั้นเกินไป — กดแล้วพูดให้นานขึ้นอีกนิด",
    "No speech was recognised. Try again closer to the microphone.": "ไม่ได้ยินคำพูด ลองอีกครั้งใกล้ไมโครโฟนขึ้น",
    "The recording is too long. Keep it under 3 minutes.": "เสียงยาวเกินไป พูดไม่เกิน 3 นาทีต่อครั้ง",
    "The speech service couldn't read this audio format.": "บริการถอดเสียงอ่านไฟล์เสียงแบบนี้ไม่ได้",
    "The speech service isn't running. Open Qwen3.8 again from its icon to start it.":
      "บริการถอดเสียงไม่ทำงาน — เปิด Qwen3.8 จากไอคอนอีกครั้งเพื่อเริ่มบริการ",
    "Voice input needs the updated hub. Open Qwen3.8 again from its icon.":
      "พูดแทนพิมพ์ต้องใช้ hub รุ่นใหม่ — เปิด Qwen3.8 จากไอคอนอีกครั้ง",
    "Couldn't reach the speech service.": "ติดต่อบริการถอดเสียงไม่ได้",
    "Transcription took too long and was stopped.": "ถอดเสียงนานเกินไป จึงหยุดไว้",
    "Transcription failed.": "ถอดเสียงไม่สำเร็จ",
    "The speech service is busy. Try again in a moment.": "บริการถอดเสียงกำลังทำงานอื่นอยู่ ลองใหม่อีกสักครู่",
    // ---- วางแผนก่อน ----
    "Plan first": "วางแผนก่อน",
    "Plan first: Qwen answers with a numbered plan and waits for your approval. Tools that change files, run code or write to Office are switched off in this chat until you turn it off.":
      "วางแผนก่อน: Qwen จะตอบเป็นแผนทีละข้อแล้วรอคุณอนุมัติ เครื่องมือที่แก้ไฟล์ รันโค้ด หรือเขียนลง Office ถูกปิดในแชตนี้จนกว่าคุณจะปิดโหมดนี้",
    "Plan mode: Qwen proposes a plan first and won't change anything yet": "โหมดวางแผน: Qwen จะเสนอแผนก่อน ยังไม่แก้ไขหรือรันอะไร",
    "Approve plan": "อนุมัติแผน",
    "Approve the plan: turn plan mode off and ask Qwen to carry it out": "อนุมัติแผน: ปิดโหมดวางแผนแล้วให้ Qwen ลงมือทำตามแผน",
    "Turn off": "ปิดโหมด",
    "Turn off plan mode": "ปิดโหมดวางแผน",
    "Plan approved — go ahead and carry it out.": "อนุมัติแผนแล้ว ลงมือทำตามแผนได้เลย",
    "Plan mode is on for this chat": "เปิดโหมดวางแผนในแชตนี้แล้ว",
    "Plan mode is on for the new chat": "เปิดโหมดวางแผนสำหรับแชตใหม่นี้แล้ว",
    "Plan mode is off": "ปิดโหมดวางแผนแล้ว",
    // ---- @ไฟล์ ----
    "Project files": "ไฟล์ของโปรเจกต์",
    "↑↓ choose · Enter insert · Esc close": "↑↓ เลือก · Enter แทรก · Esc ปิด",
    "Attachment": "ไฟล์แนบ",
    "Output": "ไฟล์ผลลัพธ์",
    "Loading project files…": "กำลังโหลดรายชื่อไฟล์…",
    "This project has no files yet.": "โปรเจกต์นี้ยังไม่มีไฟล์",
    "Add files": "เพิ่มไฟล์",
    "No files match “{q}”": "ไม่พบไฟล์ที่ตรงกับ “{q}”",
    "{n} matching files — arrow keys to choose, Enter to insert": "พบ {n} ไฟล์ — ลูกศรขึ้นลงเพื่อเลือก Enter เพื่อแทรก",
    "Inserted {name}": "แทรก {name} แล้ว"
  };
  // พจนานุกรมแยกจาก TH ของตัวแปล: คำอย่าง "Output" / "Turn off" มีในพจนานุกรมของ WebUI แล้วด้วยความหมายอื่น
  // (เจอจริง: "Output" → "เอาต์พุต") และใส่รวมใน TH จะทำให้ตัวแปลไปแปลป้ายของ WebUI ที่บังเอิญตรงคำเหล่านี้ด้วย
  (function () { for (var k in TH_B2B) if (hasOwn(TH_B2B, k)) TH_B2B[k] = glue(TH_B2B[k]); })();
  // ป้ายบนจอ (คำแปลไทยมี word joiner กันตัดกลางคำทับศัพท์) / ชื่อสำหรับ aria-label และ title (ไม่มี word joiner)
  function L(en) { return lang() === "th" && hasOwn(TH_B2B, en) ? TH_B2B[en] : en; }
  function A(en) { return L(en).replace(/⁠/g, ""); }
  function setTxt(n, s) { if (n.textContent !== s) n.textContent = s; }
  function setAt(n, k, v) {
    if (v == null) { if (n.hasAttribute(k)) n.removeAttribute(k); }
    else if (n.getAttribute(k) !== String(v)) n.setAttribute(k, v);
  }
  // ปุ่ม/ป้ายของส่วนนี้: ไม่ให้ตัวแปลแตะ และเปิด pointer-events เอง (กล่องล่างของ WebUI เป็น pointer-events:none ทั้งก้อน)
  function b2El(tag, cls) {
    var e = el(tag, cls);
    e.setAttribute("data-qw-no-tx", "");
    e.style.pointerEvents = "auto";
    return e;
  }
  XICON.mic = '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0"/><path d="M12 18v2.5"/>';
  XICON.micstop = '<rect x="7" y="7" width="10" height="10" rx="2"/>';
  XICON.x = '<path d="m7 7 10 10"/><path d="M17 7 7 17"/>';
  XICON.plan = '<path d="M9.5 6.5h10"/><path d="M9.5 12h10"/><path d="M9.5 17.5h10"/><path d="m3.8 6.4 1.2 1.2 2.2-2.4"/>' +
    '<path d="m3.8 11.9 1.2 1.2 2.2-2.4"/><circle cx="5.3" cy="17.5" r="1.3"/>';
  XICON.file = '<path d="M13.5 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9l-5.5-5.5Z"/><path d="M13.5 3.5V9H19"/>';
  XICON.out = '<path d="M13.5 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9l-5.5-5.5Z"/><path d="M13.5 3.5V9H19"/>' +
    '<path d="m9.5 14.5 2 2 3.5-4"/>';
  var B2_LIVE = null;
  // live region ของส่วนนี้ (มีอยู่ในหน้าตั้งแต่ก่อนข้อความแรก จึงถูกประกาศแน่นอน) — ล้างก่อนใส่ ข้อความซ้ำก็ยังถูกอ่าน
  function b2Say(msg, urgent) {
    if (!B2_LIVE || !B2_LIVE.isConnected) {
      B2_LIVE = el("div", "qw-sr");
      B2_LIVE.setAttribute("aria-live", "polite");
      B2_LIVE.setAttribute("role", "status");
      B2_LIVE.setAttribute("data-qw-no-tx", "");
      (document.body || root).appendChild(B2_LIVE);
    }
    B2_LIVE.setAttribute("aria-live", urgent ? "assertive" : "polite");
    B2_LIVE.textContent = "";
    setTimeout(function () { B2_LIVE.textContent = msg; }, 60);
  }
  // แถวเครื่องมือของกล่องพิมพ์ (มี container-type ของ WebUI) = พ่อของกล่องปุ่ม "+" (div.mr-auto)
  function composerToolbar() {
    var p = plusButton(), g = p && p.closest(".mr-auto"), f = composerForm();
    return g && f && f.contains(g) ? g.parentElement : null;
  }
  // เขียนค่ากล่องพิมพ์ผ่าน setter ของ prototype + event input (Svelte ผูกค่าด้วย input) แล้ววางเคอร์เซอร์
  function setComposer(ta, v, caret) {
    var desc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (desc && desc.set) desc.set.call(ta, v); else ta.value = v;
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    allowFocus++;
    try { ta.focus(); } finally { allowFocus--; }
    try { ta.setSelectionRange(caret, caret); } catch (e) {}
  }

  /* ---- 1) วางแผนก่อน (X-Qwen-Plan: 1) ---------------------------------------------------------------- */
  // สถานะเป็น "ต่อแชต": id แชตที่เปิดโหมดไว้เก็บใน localStorage qwen-plan (แท็บอื่น/โหลดหน้าใหม่ยังเห็นตรงกัน)
  // หน้าเริ่มแชต (ยังไม่มี id) = planNew: ใช้กับแชตที่ถูกสร้างจากการส่งข้อความครั้งถัดไปเท่านั้น — WebUI สร้างแชตแล้ว
  // เปลี่ยนเส้นทางไป #/chat/<id> ตอนกดส่ง จึงจดเวลากดส่ง (planSendAt) ไว้แยก "แชตใหม่ที่เพิ่งสร้าง" ออกจากการเปิดแชตเก่า
  // จากรายการ (เปลี่ยนเส้นทางแบบไม่มีการส่ง = ทิ้ง planNew ไม่ให้ไปติดแชตเก่า)
  var PLAN_KEY = "qwen-plan", PLAN_HEADER = "X-Qwen-Plan", PLAN_MAX = 300, PLAN_ADOPT_MS = 5000;
  var planIds = planLoad(), planNew = null, planSendAt = 0, planRoute = null;
  function planLoad() {
    var o = {};
    try {
      var a = JSON.parse(lsGet(PLAN_KEY) || "[]");
      if (Array.isArray(a)) a.slice(-PLAN_MAX).forEach(function (id) { if (typeof id === "string" && id && id.length <= 128) o[id] = 1; });
    } catch (e) {}
    return o;
  }
  function planSave() { lsSet(PLAN_KEY, JSON.stringify(Object.keys(planIds).slice(-PLAN_MAX))); }
  // ช่วง "เพิ่งกดส่งจากหน้าเริ่มแชต" (รอคำขอแชตแรกยืนยัน id) แสดงเป็นเปิดไว้ก่อน — ชิปไม่กระพริบดับระหว่าง WebUI เปลี่ยนหน้า
  function planSending() { return !!planNew && planSendAt > 0 && Date.now() - planSendAt < PLAN_ADOPT_MS; }
  function planCurrent() {
    var r = route();
    if (r.name === "chat") return !!(planIds[r.id] || (planSending() && planNew.checking === r.id));
    return r.name === "start" && !!planNew;
  }
  // lastModified ของแชตจาก IndexedDB ของ WebUI (อ่านอย่างเดียว ไม่สร้าง/อัปเกรดฐาน) → Promise<number|null>
  // WebUI สร้างแชตใหม่ตอนกดส่ง (lastModified = เวลานั้น) แล้วเปลี่ยนหน้าไป #/chat/<id> ก่อนส่งคำขอแชตราวครึ่งวินาที
  // (วัดแล้วทั้งจอกว้างและจอแคบ) — ใช้แยก "แชตใหม่ที่เพิ่งสร้าง" ออกจาก "แชตเก่าที่ผู้ใช้เปิด" หลัง Enter ที่ไม่ได้ส่งจริง
  // (บนมือถือ Enter = ขึ้นบรรทัดใหม่)
  function convModifiedAt(id) {
    return new Promise(function (resolve) {
      var db = null, settled = false, req;
      function fin(v) {
        if (settled) return;
        settled = true;
        try { if (db) db.close(); } catch (e) {}
        resolve(typeof v === "number" ? v : null);
      }
      if (!id || !window.indexedDB) { fin(null); return; }
      setTimeout(function () { fin(null); }, 2000);
      try { req = indexedDB.open("LlamaUi"); } catch (e) { fin(null); return; }
      req.onupgradeneeded = function () { try { req.transaction.abort(); } catch (e) {} };
      req.onerror = req.onblocked = function () { fin(null); };
      req.onsuccess = function () {
        db = req.result;
        if (settled) { try { db.close(); } catch (e) {} return; }
        db.onversionchange = function () { fin(null); };
        try {
          if (!db.objectStoreNames.contains("conversations")) { fin(null); return; }
          var g = db.transaction(["conversations"], "readonly").objectStore("conversations").get(id);
          g.onsuccess = function () { fin(g.result && +g.result.lastModified); };
          g.onerror = function () { fin(null); };
        } catch (e) { fin(null); }
      };
    });
  }
  function planAdopt(id) {
    if (!id || typeof id !== "string" || id.length > 128) return;
    planNew = null;
    planSendAt = 0;
    delete planIds[id];                                  // ย้ายไปท้าย = ใหม่สุด (ตัดของเก่าออกก่อนเมื่อเกิน PLAN_MAX)
    planIds[id] = 1;
    planSave();
    schedule();
  }
  // ตัดสินต่อคำขอ: id แชตจาก X-Conversation-Id ของ WebUI ("<id>::<โมเดล>") — คำขอที่ไม่มี id (pre-encode) ดูแชตที่เปิดอยู่
  // planNew ผูกกับแชตด้วย id ในคำขอแชตแรกหลังกดส่งจากหน้าเริ่มแชตเท่านั้น (แม่นกว่าดูเส้นทาง: ผู้ใช้อาจเปิดแชตอื่น
  // ต่อทันทีหลังกดส่ง — เส้นทางตอนคำขอออกไปจึงไม่ใช่แชตใหม่เสมอ ถ้าดูเส้นทางจะผูกผิดแชต)
  function planFor(conv) {
    var r = route();
    if (conv) {
      if (planIds[conv]) return true;
      // ยังตรวจ IndexedDB ไม่เสร็จแต่คำขอของแชตที่กำลังตรวจมาถึงแล้ว = แชตใหม่แน่ (แชตเก่าไม่ส่งคำขอเองตอนเปิด)
      if (planSending() && (planNew.checking === conv || r.name === "start")) { planAdopt(conv); return true; }
      return false;
    }
    if (r.name === "chat") return !!planIds[r.id];
    return r.name === "start" && !!planNew;
  }
  function planConv(v) {
    v = String(v || "");
    var i = v.indexOf("::");
    return (i >= 0 ? v.slice(0, i) : v).trim();
  }
  // คืน [input, init ใหม่] เมื่อต้องติด header — null = ส่งต่อตามเดิมทุกอย่าง (ไม่แตะคำขออื่นเลย)
  function planRequest(input, init) {
    var u = typeof input === "string" ? input : input && typeof input.url === "string" ? input.url : input && input.href ? String(input.href) : "";
    if (!u || u.indexOf("chat/completions") < 0) return null;
    var url;
    try { url = new URL(u, location.href); } catch (e) { return null; }
    if (url.origin !== location.origin || !/\/v1\/chat\/completions$/.test(url.pathname)) return null;
    var isReq = typeof input !== "string" && typeof Request === "function" && input instanceof Request;
    var method = String((init && init.method) || (isReq ? input.method : "GET")).toUpperCase();
    if (method !== "POST") return null;
    var h = new Headers((init && init.headers) || (isReq ? input.headers : undefined));
    if (!planFor(planConv(h.get("X-Conversation-Id")))) return null;
    h.set(PLAN_HEADER, "1");
    return [input, Object.assign({}, init || {}, { headers: h })];
  }
  var nativeFetch = window.fetch;
  if (typeof nativeFetch === "function") {
    window.fetch = function (input, init) {
      var p = null;
      try { p = planRequest(input, init); } catch (e) { p = null; }   // ตัดสินพลาด = ส่งแบบปกติ (ไม่ขวางแชต)
      return p ? nativeFetch.call(window, p[0], p[1]) : nativeFetch.apply(window, arguments);
    };
  }
  // จดการกดส่งจากกล่องพิมพ์หลัก (Enter ที่ไม่ใช่ Shift+Enter / ปุ่มส่ง / submit) — ใช้แยกแชตใหม่ออกจากการเปิดแชตเก่า
  function planNoteSend(e) {
    if (!planNew || route().name !== "start") return;
    var t = e.target, f = composerForm();
    if (!f || !t || !f.contains(t)) return;
    if (e.type === "keydown" && (e.key !== "Enter" || e.shiftKey || e.isComposing || t.tagName !== "TEXTAREA")) return;
    if (e.type === "click" && !(t.closest && t.closest('button[type="submit"]'))) return;
    planSendAt = Date.now();
  }
  ["keydown", "click", "submit"].forEach(function (ty) { window.addEventListener(ty, planNoteSend, true); });
  // เปลี่ยนเส้นทางออกจากหน้าเริ่มแชต: ไม่ได้กดส่ง (เปิดแชตเก่า/ไปหน้าอื่น) = ทิ้ง planNew ไม่ให้ไปติดแชตเก่า
  // หลังกดส่งไม่นานไปที่แชต X: ดู lastModified ของ X — เพิ่งสร้างตอนกดส่ง = แชตใหม่ ผูกโหมดวางแผนเลย, ไม่ใช่ = ทิ้ง
  function planRouteChange(r) {
    var key = r.name + ":" + (r.id || "");
    if (planNew && planSendAt && !planSending() && r.name !== "start") { planNew = null; planSendAt = 0; }
    if (key === planRoute) return;
    var prev = planRoute;
    planRoute = key;
    if (!planNew || prev === null || r.name === "start") return;
    if (r.name === "chat" && r.id && prev === "start:" && planSending()) {
      var pn = planNew, id = r.id, sent = planSendAt;
      pn.checking = id;
      convModifiedAt(id).then(function (t) {
        if (planNew !== pn) return;                      // ตัดสินไปแล้ว (คำขอแชตมาก่อน / ผู้ใช้กดชิปเอง)
        if (t != null && t >= sent - 3000) planAdopt(id);
        else { planNew = null; planSendAt = 0; schedule(); }
      });
      return;
    }
    planNew = null;
    planSendAt = 0;
  }
  function setPlan(on) {
    var r = route();
    if (r.name === "chat" && r.id) {
      if (on) planAdopt(r.id); else { delete planIds[r.id]; planNew = null; planSendAt = 0; planSave(); }
    } else if (r.name === "start") {
      planNew = on ? { at: Date.now() } : null;
      planSendAt = 0;
    } else {
      return false;
    }
    b2Say(A(on ? (r.name === "chat" ? "Plan mode is on for this chat" : "Plan mode is on for the new chat") : "Plan mode is off"));
    schedule();
    return true;
  }
  window.addEventListener("storage", function (e) {
    if (e && e.key === PLAN_KEY) { planIds = planLoad(); schedule(); }
  });
  var planChip = null, planBar = null, planBarText = null, planApprove = null, planOff = null;
  function makePlanChip() {
    var c = b2El("button", "qw-plan");
    c.type = "button";
    c.setAttribute("aria-pressed", "false");
    c.innerHTML = xIcon("plan");
    c.appendChild(el("span"));
    c.addEventListener("click", function (e) { e.preventDefault(); setPlan(!planCurrent()); });
    return c;
  }
  function makePlanBar() {
    var b = b2El("div", "qw-plan-bar");
    b.setAttribute("role", "note");
    var ic = el("span", "qw-plan-bar-ic");
    ic.innerHTML = xIcon("plan");
    planBarText = el("span", "qw-plan-bar-t");
    planApprove = el("button", "qw-plan-bar-btn qw-plan-go");
    planApprove.type = "button";
    planApprove.addEventListener("click", function (e) {
      e.preventDefault();
      var ta = composer(), draft = ta ? String(ta.value || "").trim() : "";
      setPlan(false);
      // ไม่ส่งเอง: เติมคำอนุมัติเมื่อช่องว่าง (มีข้อความค้างอยู่ = ผู้ใช้เขียนเอง ไม่ทับ) แล้วให้ผู้ใช้กดส่ง
      if (!draft) prefill(A("Plan approved — go ahead and carry it out."));
      else focusComposer();
    });
    planOff = el("button", "qw-plan-bar-btn");
    planOff.type = "button";
    planOff.addEventListener("click", function (e) { e.preventDefault(); setPlan(false); focusComposer(); });
    // ปุ่มสองตัวอยู่กล่องเดียวกัน: จอแคบขึ้นบรรทัดใหม่พร้อมกัน (ไม่แยกเป็นสามแถว)
    var acts = el("span", "qw-plan-bar-acts");
    acts.appendChild(planApprove);
    acts.appendChild(planOff);
    b.appendChild(ic);
    b.appendChild(planBarText);
    b.appendChild(acts);
    return b;
  }
  // .chat-message เป็นกล่องครอบ — ชนิดของข้อความอยู่ที่ลูก ([role=group].chat-message-assistant / -user)
  function lastIsAssistant() {
    var ms = document.querySelectorAll(".chat-messages .chat-message");
    var m = ms.length ? ms[ms.length - 1] : null;
    return !!(m && (m.classList.contains("chat-message-assistant") || m.querySelector(".chat-message-assistant")));
  }
  function syncPlan(r, st) {
    planRouteChange(r);
    var f = composerForm(), tb = composerToolbar(), area = f && f.querySelector('[data-slot="input-area"]');
    if (!f || !tb || (r.name !== "start" && r.name !== "chat")) {
      if (planChip) detach(planChip);
      if (planBar) detach(planBar);
      return;
    }
    if (!planChip) planChip = makePlanChip();
    var grp = tb.querySelector(":scope > .mr-auto"), after = null;
    // ต่อท้ายชิป "เร็ว (4B)" ถ้ามี ไม่งั้นต่อจากกล่องปุ่ม "+" — ตำแหน่งคงที่ไม่ขยับตามชื่อโมเดล
    if (fastChip && fastChip.parentNode === grp) after = fastChip;
    else for (after = plusButton(); after && after.parentNode !== grp; after = after.parentNode) {}
    if (after && after.parentNode === grp) { if (after.nextElementSibling !== planChip) after.after(planChip); }
    else if (planChip.parentNode !== grp && grp) grp.appendChild(planChip);
    var on = planCurrent();
    setAt(planChip, "aria-pressed", on ? "true" : "false");
    setTxt(planChip.lastChild, L("Plan first"));
    setAt(planChip, "aria-label", A("Plan first"));
    setAt(planChip, "title", A("Plan first: Qwen answers with a numbered plan and waits for your approval. Tools that change files, run code or write to Office are switched off in this chat until you turn it off."));
    // แถบบอกสถานะเหนือกล่องพิมพ์ (เห็นชัดว่าอยู่ในโหมดวางแผน) — อยู่ในฟอร์ม ก่อนการ์ดกล่องพิมพ์
    if (!on || !area) { if (planBar) detach(planBar); return; }
    if (!planBar) planBar = makePlanBar();
    if (planBar.parentNode !== f || planBar.nextElementSibling !== area) f.insertBefore(planBar, area);
    setTxt(planBarText, L("Plan mode: Qwen proposes a plan first and won't change anything yet"));
    setTxt(planApprove, L("Approve plan"));
    setAt(planApprove, "title", A("Approve the plan: turn plan mode off and ask Qwen to carry it out"));
    setTxt(planOff, L("Turn off"));
    setAt(planOff, "aria-label", A("Turn off plan mode"));
    planApprove.hidden = !(r.name === "chat" && !st && lastIsAssistant());
  }

  /* ---- 2) ไมค์: MediaRecorder → POST /_qwen/stt (hub ส่งต่อ 127.0.0.1:8795 พร้อมโทเค็น) → ใส่ข้อความที่เคอร์เซอร์ ------ */
  // สถานะ: idle | asking (รออนุญาตไมค์) | rec | busy (กำลังถอดเสียง) — ปุ่มเดียวสลับตามสถานะ + ป้ายเวลา/ยกเลิกข้างๆ
  // เสียงไม่ถูกเก็บที่ไหนในหน้า: ชิ้นเสียงอยู่ในหน่วยความจำจนส่งเสร็จ/ยกเลิกแล้วทิ้ง ไมค์ถูกปิด (track.stop) ทันทีที่หยุดอัด
  var STT_URL = "/_qwen/stt", MIC_MAX_MS = 180000, MIC_MIN_MS = 600, MIC_MAX_BYTES = 24 * 1024 * 1024;
  var STT_TIMEOUT_MS = 240000, MIC_HINT_MS = 8000;
  var MIC = { state: "idle", rec: null, stream: null, chunks: [], t0: 0, tick: 0, ctl: null, cancel: false,
    mime: "", err: "", hintT: 0 };
  var MIC_ERR = {
    denied: "Microphone access is blocked. Allow the microphone for this page (icon at the left of the address bar), then try again.",
    nodevice: "No microphone was found.",
    inuse: "The microphone is being used by another app.",
    record: "This browser can't record audio.",
    short: "That was too short — hold on and speak a little longer.",
    empty: "No speech was recognised. Try again closer to the microphone.",
    big: "The recording is too long. Keep it under 3 minutes.",
    format: "The speech service couldn't read this audio format.",
    down: "The speech service isn't running. Open Qwen3.8 again from its icon to start it.",
    nohub: "Voice input needs the updated hub. Open Qwen3.8 again from its icon.",
    network: "Couldn't reach the speech service.",
    timeout: "Transcription took too long and was stopped.",
    busy: "The speech service is busy. Try again in a moment.",
    server: "Transcription failed."
  };
  function micSupported() {
    return !!(navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === "function" &&
      typeof window.MediaRecorder === "function");
  }
  // สถานะบริการ stt จาก shell (hub ตรวจทุก ~8 วินาที) — ไม่รู้ (hub รุ่นก่อน/เปิดเดี่ยว) = ให้ลองกดได้
  function sttState() {
    var api = shellApi(), s = null;
    try { s = api && typeof api.services === "function" ? api.services() : null; } catch (e) { s = null; }
    var st = s && s.stt && typeof s.stt.state === "string" ? s.stt.state : "";
    return st;
  }
  // สถานะที่รู้แน่ว่าใช้ไม่ได้ (ok / loading / ไม่รู้ = ให้ลองกดได้ — ถ้าไม่พร้อมจริง hub ตอบ 503 แล้วขึ้นข้อความเอง)
  var STT_BAD = { down: 1, absent: 1, missing: 1, off: 1, error: 1, broken: 1, auth: 1, stopped: 1 };
  function sttBlocked() { return hasOwn(STT_BAD, sttState()); }
  function pickMime() {
    var c = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    for (var i = 0; i < c.length; i++) {
      try { if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(c[i])) return c[i]; } catch (e) {}
    }
    return "";
  }
  // สถานะของ HTTP → ชนิดข้อผิดพลาด (ข้อความเป็นของเราเอง ไม่แสดงข้อความดิบจากเซิร์ฟเวอร์ยกเว้น error_th/error_en ของ hub)
  function sttWhy(status) {
    if (status === 404 || status === 405 || status === 501) return "nohub";
    if (status === 413) return "big";
    if (status === 415 || status === 422) return "format";
    if (status === 429 || status === 409) return "busy";
    if (status === 502 || status === 503 || status === 504) return "down";
    return "server";
  }
  function sttServerMsg(d) {
    var s = d && (lang() === "th" ? d.error_th : d.error_en);
    return typeof s === "string" && s.trim() ? s.trim().slice(0, 240) : "";
  }
  function micStopTracks(stream) {
    try { (stream ? stream.getTracks() : []).forEach(function (t) { try { t.stop(); } catch (e) {} }); } catch (e) {}
  }
  function micRelease() {
    clearInterval(MIC.tick);
    MIC.tick = 0;
    micStopTracks(MIC.stream);
    MIC.stream = null;
    MIC.rec = null;
  }
  function micSet(state) {
    MIC.state = state;
    setAttr("data-qw-mic", state === "idle" ? null : state);
    paintMic();
  }
  function micFail(why, msg) {
    micRelease();
    MIC.chunks = [];
    MIC.err = why;
    micSet("idle");
    micHint(msg || L(MIC_ERR[why] || MIC_ERR.server));
  }
  function micStart() {
    if (MIC.state !== "idle") return;
    hideMicHint();
    if (sttBlocked()) { micHint(L("Voice input is unavailable: the speech service isn't running")); return; }
    if (!micSupported()) { micFail("record"); return; }
    MIC.cancel = false;
    MIC.err = "";
    micSet("asking");
    var p;
    try {
      p = navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true,
        autoGainControl: true, channelCount: 1 } });
    } catch (e) { micFail("record"); return; }
    p.then(function (stream) {
      if (MIC.state !== "asking" || MIC.cancel) { micStopTracks(stream); return; }   // ยกเลิกระหว่างรออนุญาต
      var mime = pickMime(), rec;
      try { rec = mime ? new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 32000 }) : new MediaRecorder(stream); }
      catch (e) { micStopTracks(stream); micFail("record"); return; }
      MIC.stream = stream;
      MIC.rec = rec;
      MIC.chunks = [];
      MIC.mime = rec.mimeType || mime || "audio/webm";
      rec.ondataavailable = function (ev) { if (ev.data && ev.data.size) MIC.chunks.push(ev.data); };
      rec.onstop = micStopped;
      rec.onerror = function () { if (MIC.rec === rec) micFail("record"); };
      try { rec.start(1000); } catch (e) { micStopTracks(stream); micFail("record"); return; }
      MIC.t0 = Date.now();
      micSet("rec");
      b2Say(A("Recording — press the button again when you're done, Escape to cancel"));
      MIC.tick = setInterval(function () {
        if (MIC.state !== "rec") return;
        if (Date.now() - MIC.t0 >= MIC_MAX_MS) { micStop(); return; }   // ครบเวลา: หยุดแล้วถอดเสียงเลย
        paintMic();
      }, 250);
    }, function (err) {
      var n = err && err.name;
      if (MIC.cancel) { micSet("idle"); return; }
      micFail(n === "NotAllowedError" || n === "SecurityError" || n === "PermissionDeniedError" ? "denied"
        : n === "NotFoundError" || n === "OverconstrainedError" || n === "DevicesNotFoundError" ? "nodevice"
        : n === "NotReadableError" || n === "TrackStartError" || n === "AbortError" ? "inuse" : "record");
    });
  }
  function micStop() {
    if (MIC.state !== "rec" || !MIC.rec) return;
    MIC.cancel = false;
    micSet("busy");
    try { MIC.rec.stop(); } catch (e) { micFail("record"); }   // onstop → micStopped ส่งเสียงไปถอด
  }
  function micCancel() {
    var st = MIC.state;
    if (st === "idle") return;
    MIC.cancel = true;
    if (st === "rec" && MIC.rec) { try { MIC.rec.stop(); } catch (e) {} }
    if (MIC.ctl) { try { MIC.ctl.abort(); } catch (e) {} }
    micRelease();
    MIC.chunks = [];
    micSet("idle");
    b2Say(A("Recording cancelled"));
    focusComposer();
  }
  function micStopped() {
    var dur = Date.now() - MIC.t0, blob = null;
    if (!MIC.cancel) { try { blob = new Blob(MIC.chunks, { type: MIC.mime || "audio/webm" }); } catch (e) { blob = null; } }
    micRelease();
    MIC.chunks = [];
    if (MIC.cancel) return;
    if (!blob) { micFail("record"); return; }
    if (dur < MIC_MIN_MS || blob.size < 256) { micFail("short"); return; }
    if (blob.size > MIC_MAX_BYTES) { micFail("big"); return; }
    micUpload(blob);
  }
  function micUpload(blob) {
    micSet("busy");
    b2Say(A("Transcribing…"));
    var ctl = null, done = false;
    try { ctl = new AbortController(); } catch (e) { ctl = null; }
    MIC.ctl = ctl;
    var to = setTimeout(function () { try { if (ctl) ctl.abort(); } catch (e) {} fin(null, "timeout"); }, STT_TIMEOUT_MS);
    function fin(text, why, msg) {
      if (done) return;
      done = true;
      clearTimeout(to);
      if (MIC.ctl === ctl) MIC.ctl = null;
      if (MIC.cancel) return;                              // ผู้ใช้กดยกเลิก — micCancel จัดการสถานะแล้ว
      if (why) { micFail(why, msg); return; }
      micSet("idle");
      micInsert(text);
    }
    var opt = { method: "POST", headers: { "Content-Type": blob.type || "application/octet-stream", "Accept": "application/json" },
      body: blob, credentials: "same-origin", cache: "no-store", redirect: "error" };
    if (ctl) opt.signal = ctl.signal;
    try {
      nativeFetch.call(window, STT_URL, opt).then(function (res) {
        return res.text().then(function (t) {
          var d = null;
          try { d = JSON.parse(t); } catch (e) { d = null; }
          if (!res.ok) { fin(null, sttWhy(res.status), sttServerMsg(d)); return; }
          var text = d && typeof d.text === "string" ? d.text : null;
          if (text == null) { fin(null, "server"); return; }
          text = text.replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, "").replace(/[ \t]+/g, " ").trim();
          if (!text) { fin(null, "empty"); return; }
          fin(text);
        });
      }).catch(function () { fin(null, "network"); });
    } catch (e) { fin(null, "network"); }
  }
  // ใส่ที่เคอร์เซอร์ของกล่องพิมพ์ (textarea จำตำแหน่งไว้แม้โฟกัสย้ายไปที่ปุ่มไมค์) — ไม่เคยโฟกัสเลยแต่มีข้อความอยู่ = ต่อท้าย
  function micInsert(text) {
    var ta = composer();
    if (!ta) return;
    var v = ta.value, s = ta.selectionStart, e = ta.selectionEnd;
    if (typeof s !== "number" || typeof e !== "number" || s > v.length) { s = e = v.length; }
    if (v && s === 0 && e === 0 && document.activeElement !== ta) s = e = v.length;
    var before = v.slice(0, s), after = v.slice(e), ins = text;
    if (before && !/\s$/.test(before)) ins = " " + ins;
    if (after && !/^\s/.test(after)) ins = ins + " ";
    setComposer(ta, before + ins + after, before.length + ins.length);
    b2Say(A("Text from your voice was added to the message box"));
  }
  var micBox = null, micBtn = null, micRec = null, micTime = null, micX = null, micHintEl = null;
  function makeMic() {
    var box = b2El("div", "qw-mic-box");
    micRec = el("span", "qw-rec");
    var dot = el("span", "qw-rec-dot");
    dot.setAttribute("aria-hidden", "true");
    micTime = el("span", "qw-rec-time");
    micX = el("button", "qw-rec-x");
    micX.type = "button";
    micX.innerHTML = xIcon("x");
    micX.addEventListener("click", function (e) { e.preventDefault(); micCancel(); });
    micRec.appendChild(dot);
    micRec.appendChild(micTime);
    micRec.appendChild(micX);
    micBtn = el("button", "qw-mic");
    micBtn.type = "button";
    micBtn.addEventListener("click", function (e) {
      e.preventDefault();
      if (MIC.state === "idle") micStart();
      else if (MIC.state === "rec") micStop();
      else if (MIC.state === "asking") micCancel();
    });
    box.appendChild(micRec);
    box.appendChild(micBtn);
    return box;
  }
  function fmtClock(ms) {
    var s = Math.max(0, Math.floor(ms / 1000));
    return Math.floor(s / 60) + ":" + (s % 60 < 10 ? "0" : "") + (s % 60);
  }
  function paintMic() {
    if (!micBox) return;
    var st = MIC.state, off = st === "idle" && sttBlocked();
    setAt(micBox, "data-state", off ? "off" : st);
    var icon = st === "rec" ? "micstop" : "mic";
    if (micBtn.getAttribute("data-icon") !== icon) { micBtn.setAttribute("data-icon", icon); micBtn.innerHTML = xIcon(icon); }
    var label = st === "rec" ? "Stop and transcribe" : st === "busy" ? "Transcribing…"
      : st === "asking" ? "Waiting for microphone permission…" : "Voice input";
    setAt(micBtn, "aria-label", A(label));
    setAt(micBtn, "title", A(off ? "Voice input is unavailable: the speech service isn't running"
      : st === "idle" ? "Voice input: speak Thai or English, then press again to put the text in the message box" : label));
    setAt(micBtn, "aria-pressed", st === "rec" ? "true" : "false");
    setAt(micBtn, "aria-busy", st === "busy" || st === "asking" ? "true" : null);
    setAt(micBtn, "aria-disabled", st === "busy" ? "true" : null);
    micRec.hidden = !(st === "rec" || st === "busy");
    var warn = st === "rec" && Date.now() - MIC.t0 > MIC_MAX_MS - 30000;
    setAt(micRec, "data-warn", warn ? "1" : null);
    var tv = st === "rec" ? fmtClock(Date.now() - MIC.t0) : st === "busy" ? L("Transcribing…") : "";
    if (!micTime.firstChild) micTime.appendChild(document.createTextNode(""));
    if (micTime.firstChild.nodeValue !== tv) micTime.firstChild.nodeValue = tv;
    setAt(micX, "aria-label", A(st === "busy" ? "Cancel transcription" : "Cancel recording"));
    setAt(micX, "title", A(st === "busy" ? "Cancel transcription" : "Cancel recording"));
  }
  function placeMicHint() {
    if (!micHintEl || micHintEl.hidden || !micBtn || !micBtn.isConnected) return;
    var r = micBtn.getBoundingClientRect(), vw = document.documentElement.clientWidth || innerWidth;
    var w = micHintEl.offsetWidth;
    micHintEl.style.left = Math.round(Math.max(8, Math.min(r.right - w, vw - w - 8))) + "px";
    micHintEl.style.bottom = Math.round(innerHeight - r.top + 8) + "px";
  }
  function micHint(msg) {
    if (!micHintEl || !micHintEl.isConnected) {
      micHintEl = el("div", "qw-mic-hint");
      micHintEl.setAttribute("aria-hidden", "true");          // ข้อความเดียวกันไปที่ live region (ประกาศแน่นอน)
      micHintEl.setAttribute("data-qw-no-tx", "");
      document.body.appendChild(micHintEl);
    }
    micHintEl.textContent = msg;
    micHintEl.hidden = false;
    placeMicHint();
    b2Say(msg, true);
    clearTimeout(MIC.hintT);
    MIC.hintT = setTimeout(hideMicHint, MIC_HINT_MS);
  }
  function hideMicHint() {
    clearTimeout(MIC.hintT);
    if (micHintEl) micHintEl.hidden = true;
  }
  window.addEventListener("resize", function () { placeMicHint(); });
  window.addEventListener("pointerdown", function (e) {
    if (micHintEl && !micHintEl.hidden && e.isTrusted && !(micBox && micBox.contains(e.target))) hideMicHint();
  }, true);
  // resume 2026-10-06: คลิกที่ shell (เมนูบัญชี/แผงโปรเจกต์/แถบข้าง) ไม่ผ่าน pointerdown ของ iframe — ข้อความค้างทับกล่องพิมพ์
  // ระหว่างที่เมนูของ shell เปิดอยู่ (เห็นในภาพทดสอบ) จึงซ่อนเมื่อหน้าต่างของ iframe เสียโฟกัสด้วย (live region ประกาศไปแล้ว)
  window.addEventListener("blur", function () { if (micHintEl && !micHintEl.hidden) hideMicHint(); });
  // Esc = ยกเลิกการอัด/ถอดเสียง (ไม่แย่ง Esc ของหน้าต่าง/เมนูของ WebUI ที่เปิดอยู่)
  window.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || MIC.state === "idle" || e.defaultPrevented || mentionClosing) return;
    if (dialogOpen() || plusLayerOpen() || menuOpen()) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    micCancel();
  }, true);
  window.addEventListener("pagehide", function () { if (MIC.state !== "idle") micCancel(); });
  function syncMic(r) {
    var tb = composerToolbar();
    if (!tb || !micSupported() || (r.name !== "start" && r.name !== "chat")) {
      if (micBox && MIC.state === "idle") detach(micBox);
      return;
    }
    if (!micBox) micBox = makeMic();
    // ก่อนปุ่มส่ง/หยุด (ลูกตัวสุดท้ายของแถวเครื่องมือ) — ถ้ามีปุ่มไมค์ของ WebUI เอง (โมเดลรับเสียงได้) มันอยู่ในช่องเดียวกับปุ่มส่ง
    var kids = tb.children, send = null;
    for (var i = kids.length - 1; i >= 0; i--) if (kids[i] !== micBox && kids[i].tagName === "BUTTON") { send = kids[i]; break; }
    if (send) { if (micBox.nextElementSibling !== send) tb.insertBefore(micBox, send); }
    else if (micBox.parentNode !== tb) tb.appendChild(micBox);
    paintMic();
  }

  /* ---- 3) @ไฟล์ของโปรเจกต์: พิมพ์ @ ในกล่องพิมพ์ → รายชื่อไฟล์แนบ (/_qwen/files) + ไฟล์ผลลัพธ์ (/_qwen/out/) ---------- */
  // แทรกเป็นข้อความ "@attachments/<ชื่อ>" / "@outputs/<ชื่อ>" (hub เห็นแล้วบอกโมเดลให้ extract ไฟล์นั้นก่อน)
  // ตัวเลือกไฟล์ @ ของ WebUI เอง (ค้นไฟล์ทั้งเครื่องผ่าน --tools ของ llama-server ซึ่งปิดอยู่) ขึ้นแค่ "ค้นหาไฟล์ไม่ได้"
  // จึงปิดมันทุกครั้งที่มันเปิดในสถานะนั้น (Escape ของมันเอง — ใน observer ก่อนเบราว์เซอร์วาดภาพ) ถ้าวันหนึ่งเปิด --tools
  // แล้วมันค้นได้จริง ตัวของเราจะหลีกให้ (ไม่เปิดซ้อนกัน)
  var AT_TTL_MS = 20000, AT_MAX = 8, AT_HEAD = 400, mentionClosing = false;
  var AT = { box: null, list: null, head: null, foot: null, open: false, items: [], idx: 0, tok: null, files: null,
    at: 0, loading: null, dismissed: -1, seq: 0 };
  function atGet(url, where) {
    return nativeFetch.call(window, url, { headers: { "Accept": "application/json" }, credentials: "same-origin",
      cache: "no-store", redirect: "error" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        var fs = d && Array.isArray(d.files) ? d.files : [];
        return fs.filter(function (f) { return f && typeof f.name === "string" && f.name && f.name.length <= 255; })
          .map(function (f) { return { name: f.name, where: where, size: +f.size || 0, mtime: +f.mtime || 0 }; });
      })
      .catch(function () { return []; });
  }
  function atFiles(force) {
    if (!force && AT.files && Date.now() - AT.at < AT_TTL_MS) return Promise.resolve(AT.files);
    if (AT.loading) return AT.loading;
    AT.loading = Promise.all([atGet("/_qwen/files", "attachments"), atGet("/_qwen/out/", "outputs")]).then(function (r) {
      AT.loading = null;
      AT.files = r[0].concat(r[1]);
      AT.at = Date.now();
      return AT.files;
    });
    return AT.loading;
  }
  // โทเค็น @ ที่เคอร์เซอร์อยู่ท้ายพอดี: ต้นข้อความหรือหลังช่องว่าง/วงเล็บ/เครื่องหมายคำพูด — อีเมล (a@b) ไม่นับ
  function atToken(ta) {
    if (!ta || ta.selectionStart !== ta.selectionEnd) return null;
    var pos = ta.selectionStart, before = ta.value.slice(Math.max(0, pos - AT_HEAD), pos);
    var m = /(^|[\s(\[{"'“‘])@([^\s@]{0,120})$/.exec(before);
    if (!m) return null;
    if (!m[1] && pos - before.length > 0) return null;     // ตัดกลางข้อความยาว — ตัวหน้า @ ไม่ใช่ต้นข้อความจริง
    return { start: pos - m[2].length - 1, end: pos, q: m[2] };
  }
  // จัดอันดับ: ขึ้นต้นด้วยคำค้น > ต้นคำ > มีอยู่ในชื่อ แล้วไฟล์ใหม่ก่อน · "attachments/…" "outputs/…" = ค้นเฉพาะโฟลเดอร์นั้น
  function atRank(files, q) {
    q = String(q || "").toLowerCase();
    var where = null, m = /^(attachments|outputs)\/(.*)$/.exec(q);
    if (m) { where = m[1]; q = m[2]; }
    var out = [];
    files.forEach(function (f) {
      if (where && f.where !== where) return;
      var n = f.name.toLowerCase(), i = q ? n.indexOf(q) : 0, rank;
      if (i < 0) {
        if (!where && q && (f.where + "/" + n).indexOf(q) === 0) rank = 3; else return;
      } else rank = i === 0 ? 0 : /[\s_\-.()\[\]]/.test(n.charAt(i - 1)) ? 1 : 2;
      out.push({ f: f, rank: rank });
    });
    out.sort(function (a, b) {
      return a.rank - b.rank || b.f.mtime - a.f.mtime || (a.f.name < b.f.name ? -1 : a.f.name > b.f.name ? 1 : 0);
    });
    return out.slice(0, AT_MAX).map(function (x) { return x.f; });
  }
  function fmtBytes(n) {
    var u = ["B", "KB", "MB", "GB"], i = 0;
    n = +n || 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return (i ? n.toFixed(n < 10 ? 1 : 0) : n) + " " + u[i];
  }
  function atMakeBox() {
    var box = b2El("div", "qw-at");
    box.hidden = true;
    AT.head = el("div", "qw-at-h");
    AT.head.setAttribute("aria-hidden", "true");
    AT.list = el("div", "qw-at-list");
    AT.list.id = "qw-at-list";
    AT.list.setAttribute("role", "listbox");
    AT.foot = el("div", "qw-at-empty");
    box.appendChild(AT.head);
    box.appendChild(AT.list);
    box.appendChild(AT.foot);
    // กดรายการด้วยเมาส์/นิ้ว: โฟกัสต้องค้างที่กล่องพิมพ์ (รายการไม่รับโฟกัส) — กันที่ pointerdown แล้วแทรกตอน click
    box.addEventListener("pointerdown", function (e) { e.preventDefault(); });
    box.addEventListener("mousedown", function (e) { e.preventDefault(); });
    box.addEventListener("click", function (e) {
      var o = e.target.closest ? e.target.closest("[data-qw-at-i]") : null;
      if (o) { atInsert(+o.getAttribute("data-qw-at-i")); return; }
      var add = e.target.closest ? e.target.closest(".qw-at-add") : null;
      if (add) { atClose(); callShell("openProjectPanel"); }
    });
    document.body.appendChild(box);
    return box;
  }
  function atPlace() {
    if (!AT.box || AT.box.hidden) return;
    var f = composerForm(), card = f && (f.querySelector('[data-slot="input-area"]') || f);
    if (!card) { atClose(); return; }
    var r = card.getBoundingClientRect(), vw = document.documentElement.clientWidth || innerWidth;
    var w = Math.min(r.width, 480);
    AT.box.style.width = Math.round(w) + "px";
    AT.box.style.left = Math.round(Math.max(8, Math.min(r.left, vw - w - 8))) + "px";
    AT.box.style.bottom = Math.round(innerHeight - r.top + 6) + "px";
    AT.box.style.maxHeight = Math.round(Math.max(140, Math.min(360, r.top - 16))) + "px";
  }
  function atAria(ta, on) {
    if (!ta) return;
    setAt(ta, "aria-controls", on ? "qw-at-list" : null);
    setAt(ta, "aria-expanded", on ? "true" : null);
    setAt(ta, "aria-autocomplete", on ? "list" : null);
    setAt(ta, "aria-activedescendant", on && AT.items.length ? "qw-at-o" + AT.idx : null);
  }
  function atClose() {
    if (!AT.open && (!AT.box || AT.box.hidden)) return;
    AT.open = false;
    AT.items = [];
    AT.tok = null;
    if (AT.box) AT.box.hidden = true;
    setAttr("data-qw-at", null);
    atAria(composer(), false);
  }
  function atItemLabel(f) { return f.name + ", " + A(f.where === "outputs" ? "Output" : "Attachment"); }
  function atRender(state, q) {
    if (!AT.box || !AT.box.isConnected) AT.box = atMakeBox();
    setTxt(AT.head, L("Project files") + "  ·  " + L("↑↓ choose · Enter insert · Esc close"));
    AT.list.replaceChildren.apply(AT.list, AT.items.map(function (f, i) {
      var o = el("div", "qw-at-o");
      o.id = "qw-at-o" + i;
      o.setAttribute("role", "option");
      o.setAttribute("data-qw-at-i", String(i));
      o.setAttribute("aria-selected", i === AT.idx ? "true" : "false");
      o.setAttribute("aria-label", atItemLabel(f));
      var ic = el("span", "qw-at-ic");
      ic.innerHTML = xIcon(f.where === "outputs" ? "out" : "file");
      var nm = el("span", "qw-at-n");
      nm.textContent = f.name;
      nm.setAttribute("dir", "auto");
      var meta = el("span", "qw-at-m");
      meta.textContent = L(f.where === "outputs" ? "Output" : "Attachment") + (f.size ? " · " + fmtBytes(f.size) : "");
      o.appendChild(ic);
      o.appendChild(nm);
      o.appendChild(meta);
      return o;
    }));
    AT.foot.replaceChildren();
    AT.foot.hidden = !!AT.items.length;
    if (!AT.items.length) {
      var msg = state === "loading" ? L("Loading project files…") : state === "none" ? L("This project has no files yet.")
        : L("No files match “{q}”").replace("{q}", clip(q, 40));
      AT.foot.appendChild(document.createTextNode(msg));
      if (state === "none" && canRedirectSysMsg()) {
        var add = el("button", "qw-at-add");
        add.type = "button";
        add.textContent = L("Add files");
        AT.foot.appendChild(add);
      }
    }
    AT.box.hidden = false;
    AT.open = true;
    setAttr("data-qw-at", "1");
    atPlace();
    atAria(composer(), true);
    var sel = AT.list.children[AT.idx];
    if (sel && sel.scrollIntoView) { try { sel.scrollIntoView({ block: "nearest" }); } catch (e) {} }
  }
  function atCheck() {
    var ta = composer();
    if (!ta || document.activeElement !== ta || MIC.state === "rec") { atClose(); return; }
    var tok = atToken(ta);
    if (!tok) { AT.dismissed = -1; atClose(); return; }
    if (tok.start === AT.dismissed) { atClose(); return; }
    if (webuiMentionLive()) { atClose(); return; }         // ตัวเลือกของ WebUI ค้นได้จริง — หลีกให้
    var same = AT.tok && AT.tok.start === tok.start;
    AT.tok = tok;
    if (!same) AT.idx = 0;
    var seq = ++AT.seq, cached = AT.files && Date.now() - AT.at < AT_TTL_MS;
    if (!cached) { AT.items = []; atRender("loading", tok.q); }
    atFiles(false).then(function (files) {
      if (seq !== AT.seq || !AT.tok || AT.tok.start !== tok.start) return;
      var prevLen = AT.items.length;
      AT.items = atRank(files, tok.q);
      if (AT.idx >= AT.items.length) AT.idx = 0;
      atRender(files.length ? "nomatch" : "none", tok.q);
      if (AT.items.length && AT.items.length !== prevLen) {
        b2Say(A("{n} matching files — arrow keys to choose, Enter to insert").replace("{n}", String(AT.items.length)));
      }
    });
  }
  var atRaf = 0;
  function atSoon() {
    if (atRaf) return;
    atRaf = requestAnimationFrame(function () { atRaf = 0; try { atCheck(); } catch (e) { atClose(); } });
  }
  function atMove(d) {
    if (!AT.items.length) return;
    AT.idx = (AT.idx + d + AT.items.length) % AT.items.length;
    [].forEach.call(AT.list.children, function (o, i) { o.setAttribute("aria-selected", i === AT.idx ? "true" : "false"); });
    atAria(composer(), true);
    var sel = AT.list.children[AT.idx];
    if (sel && sel.scrollIntoView) { try { sel.scrollIntoView({ block: "nearest" }); } catch (e) {} }
    b2Say(atItemLabel(AT.items[AT.idx]));
  }
  function atInsert(i) {
    var ta = composer(), f = AT.items[i], tok = atToken(ta);
    if (!ta || !f || !tok) { atClose(); return; }
    var v = ta.value, before = v.slice(0, tok.start), after = v.slice(tok.end);
    var ins = "@" + f.where + "/" + f.name + (after && /^\s/.test(after) ? "" : " ");
    AT.dismissed = before.length;                       // ข้อความที่แทรกยังเป็นโทเค็น @ อยู่ (ถ้าไม่มีช่องว่างตาม) — ไม่เปิดซ้ำ
    atClose();
    setComposer(ta, before + ins + after, before.length + ins.length);
    b2Say(A("Inserted {name}").replace("{name}", f.name));
  }
  window.addEventListener("keydown", function (e) {
    if (!AT.open || mentionClosing || e.isComposing || e.target !== composer()) return;
    var k = e.key;
    if (k === "ArrowDown" || k === "ArrowUp") { if (!AT.items.length) return; atMove(k === "ArrowDown" ? 1 : -1); }
    else if ((k === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) || (k === "Tab" && !e.shiftKey)) {
      if (!AT.items.length) return;                      // ไม่มีรายการ: Enter ส่งข้อความตามปกติ
      atInsert(AT.idx);
    } else if (k === "Escape") {
      AT.dismissed = AT.tok ? AT.tok.start : -1;
      atClose();
    } else return;
    e.preventDefault();
    e.stopImmediatePropagation();
  }, true);
  document.addEventListener("input", function (e) { if (e.target === composer()) atSoon(); }, true);
  document.addEventListener("selectionchange", function () { if (AT.open || document.activeElement === composer()) atSoon(); });
  document.addEventListener("focusout", function (e) {
    if (AT.open && e.target === composer()) setTimeout(function () { if (document.activeElement !== composer()) atClose(); }, 120);
  }, true);
  window.addEventListener("resize", function () { atPlace(); });
  // ตัวเลือก @ ของ WebUI: ปุ่มเปิดที่ซ่อนอยู่ในฟอร์ม (sr-only "Open file mention picker") + popover ที่เปิดอยู่
  function webuiMention() {
    var f = composerForm();
    if (!f) return null;
    var bs = f.querySelectorAll("button[data-popover-trigger]");
    for (var i = 0; i < bs.length; i++) {
      var sr = bs[i].querySelector(".sr-only");
      if (sr && /file mention picker/i.test(enText(sr))) return bs[i];
    }
    return null;
  }
  function webuiMentionContent() {
    var b = webuiMention();
    if (!b || b.getAttribute("data-state") !== "open") return null;
    return document.querySelector('[data-slot="popover-content"][data-state="open"]');
  }
  // ค้นได้จริง = ไม่ได้ขึ้นข้อความ "ค้นหาไฟล์ไม่ได้/ปิดอยู่" ของมัน
  function webuiMentionLive() {
    var c = webuiMentionContent();
    return !!(c && !/File search is (unavailable|disabled)/i.test(enText(c)));
  }
  // จาก observer ของ body (หลังแปล ก่อนวาดภาพ): ตัวเลือก @ ของ WebUI เปิดในสถานะใช้ไม่ได้ → ปิดด้วย Escape ของมันเอง
  function b2bObs(recs) {
    if (mentionClosing || !shell()) return;
    var added = false;
    for (var i = 0; i < recs.length && !added; i++) {
      var r = recs[i];
      if (r.type !== "childList" || !r.addedNodes.length) continue;
      if (r.target.closest && r.target.closest(".chat-messages")) continue;
      added = true;
    }
    if (!added) return;
    var c = webuiMentionContent(), ta = composer();
    if (!c || !ta || !/File search is (unavailable|disabled)/i.test(enText(c))) return;
    c.setAttribute("data-qw-webui-mention", "");           // ธีมซ่อนไว้ตั้งแต่เฟรมแรก เผื่อ Escape ไม่ปิด
    mentionClosing = true;
    try {
      ta.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true, cancelable: true }));
    } catch (e) {} finally { mentionClosing = false; }
    atSoon();
  }

  /* ---- รวม: เรียกจาก extrasPass() ทุกรอบ ---------------------------------------------------------------- */
  function b2bPass(r, st) {
    try { syncPlan(r, st); } catch (e) {}
    try { syncMic(r); } catch (e) {}
    if (AT.open && (r.name !== "start" && r.name !== "chat")) atClose();
  }
  // ---- API เพิ่ม (นอกสัญญา 5b): ให้ shell/เทสต์ถามสถานะหรือสั่งได้ ----
  // plan() → {on, pendingNew, count} · setPlan(true|false|ไม่ส่ง=สลับ) → boolean
  window.qwenEnhance.plan = function () { return { on: planCurrent(), pendingNew: !!planNew, count: Object.keys(planIds).length }; };
  window.qwenEnhance.setPlan = function (on) { return setPlan(on == null ? !planCurrent() : !!on); };
  // dictation() → {state, supported, error} · startDictation()/stopDictation()/cancelDictation()
  window.qwenEnhance.dictation = function () { return { state: MIC.state, supported: micSupported(), error: MIC.err, service: sttState() }; };
  window.qwenEnhance.startDictation = function () { micStart(); return MIC.state !== "idle"; };
  window.qwenEnhance.stopDictation = function () { micStop(); return MIC.state; };
  window.qwenEnhance.cancelDictation = function () { micCancel(); return MIC.state; };
  // mention() → {open, items:[{name, where}]} — สิ่งที่รายการ @ แสดงอยู่ตอนนี้
  window.qwenEnhance.mention = function () {
    return { open: AT.open, idx: AT.idx, items: AT.items.map(function (f) { return { name: f.name, where: f.where }; }) };
  };

  /* ---- เริ่มทำงาน ----------------------------------------------------------- */
  applyFont(readFont());
  syncRootAttrs();
  if (shellPref()) syncCfgTheme(shellPref());   // ต้องเกิดก่อน settings store ของ WebUI อ่าน config
  mirrorTheme();
  reconcileTheme();
  checkRoute();
  // สิ่งที่อยู่ในหน้าก่อน observer เริ่มเฝ้า (ปกติ WebUI ยัง mount ไม่เสร็จ จึงแทบไม่มี)
  try { txTree(document.body, lang()); } catch (e) {}
  bodyObs.takeRecords();
  schedule();

  /* ======================================================================================
     batch 3 (2026-10-06, owner ui) — สัญญา D4(b): แจ้งเบาๆ ในแชตเมื่อ hub สรุปช่วงต้นของบทสนทนาให้อัตโนมัติ
     hub (สัญญา D1) ตอบ header X-Qwen-Compacted: <จำนวนรอบที่ถูกสรุป> กับคำขอแชตที่ถูกย่อ ส่วนนี้ห่อ window.fetch อีกชั้น
     (ทับตัวห่อของ "วางแผนก่อน") แล้วอ่านแค่ header ของคำตอบ — คืน Promise ตัวเดิมให้ WebUI ไม่ clone ไม่อ่าน body
     (สตรีม SSE ต้องไหลเหมือนเดิมทุกไบต์) แล้วจำต่อแชตไว้ใน localStorage qwen-compact เพื่อแสดงเส้นบอกเหนือกล่องพิมพ์
     ทุกครั้งที่เปิดแชตนั้น · คำตอบของแชตเดียวกันที่ไม่มี header = ไม่ได้ย่อแล้ว (เช่น แยกกิ่งไปข้อความที่สั้นลง) → ลบป้าย
     วางไว้หลัง "เริ่มทำงาน" เพราะชุดทดสอบของรอบก่อนตัดช่วงไฟล์ตามหัวข้อ (รอบ 4 … API, batch 2b … เริ่มทำงาน) ไปตรวจว่า
     เรียกเครือข่าย/ใช้ป้ายอะไร — ส่วนนี้จึงไม่ปนกับช่วงเหล่านั้น · ฟังก์ชันประกาศแบบ function (hoist) และ pass() รอบแรกเกิดใน
     rAF/setTimeout หลังสคริปต์รันจบ ตัวแปรของส่วนนี้จึงพร้อมก่อนถูกเรียกเสมอ (b3Pass เช็ก B3C_READY กันไว้อีกชั้น)
     ทุกชิ้นมี data-qw-no-tx (ป้ายเป็นภาษาปัจจุบันจาก L3/A3 แล้ว) และสร้างด้วย textContent — innerHTML ใช้กับไอคอนคงที่เท่านั้น
     ====================================================================================== */
  var TH_B3 = {
    "Earlier part of this chat summarized ({n} turns)": "สรุปช่วงต้นของบทสนทนาแล้ว ({n} รอบ)",
    "This chat got longer than the model can hold at once, so the middle part ({n} turns) was summarized automatically. Qwen still sees your first message, the summary and the latest turns. Every message is still here on this page.":
      "บทสนทนานี้ยาวเกินกว่าที่โมเดลจำได้ในครั้งเดียว ระบบจึงสรุปช่วงกลาง ({n} รอบ) ให้อัตโนมัติ Qwen ยังเห็นข้อความแรก บทสรุป และรอบล่าสุด ส่วนข้อความทั้งหมดยังอยู่ครบในหน้านี้",
    "The earlier part of this chat was summarized to fit the model's memory": "สรุปช่วงต้นของบทสนทนาแล้ว เพื่อให้พอดีกับหน่วยความจำของโมเดล"
  };
  // พจนานุกรมแยก (เหมือน TH_B2B): ไม่ใส่รวมใน TH ของตัวแปล ป้ายของ WebUI ที่บังเอิญตรงคำจะได้ไม่เพี้ยน
  (function () { for (var k in TH_B3) if (hasOwn(TH_B3, k)) TH_B3[k] = glue(TH_B3[k]); })();
  function L3(en) { return lang() === "th" && hasOwn(TH_B3, en) ? TH_B3[en] : en; }
  function A3(en) { return L3(en).replace(/⁠/g, ""); }
  XICON.compact = '<path d="M12 3.5v6"/><path d="m8.8 6.6 3.2 3.2 3.2-3.2"/><path d="M12 20.5v-6"/><path d="m8.8 17.4 3.2-3.2 3.2 3.2"/>' +
    '<path d="M4.5 12h15"/>';
  XICON.info = '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><circle cx="12" cy="8" r=".9" fill="currentColor" stroke="none"/>';
  var B3C_KEY = "qwen-compact", B3C_MAX = 300, B3C_HDR = "X-Qwen-Compacted";
  var b3cState = b3cLoad(), b3cEl = null, b3cBtn = null, b3cTxt = null, b3cTip = null, b3cPinned = false, b3cHoverT = 0;
  // อ่านอย่างระวัง: ค่าใน localStorage อาจถูกแก้/เสีย — รับเฉพาะ id สั้นๆ กับจำนวนรอบที่เป็นเลขบวก
  function b3cLoad() {
    var o = {};
    try {
      var v = JSON.parse(lsGet(B3C_KEY) || "{}");
      if (v && typeof v === "object" && !Array.isArray(v)) {
        Object.keys(v).forEach(function (id) {
          var x = v[id], n = x && typeof x === "object" ? Math.floor(+x.n) : 0;
          if (id && id.length <= 128 && n > 0 && n < 1e6) o[id] = { n: n, at: +x.at || 0 };
        });
      }
    } catch (e) {}
    return o;
  }
  function b3cSave() {
    var ids = Object.keys(b3cState).sort(function (a, b) { return b3cState[a].at - b3cState[b].at; });
    while (ids.length > B3C_MAX) delete b3cState[ids.shift()];   // ทิ้งของเก่าสุดก่อน
    lsSet(B3C_KEY, JSON.stringify(b3cState));
  }
  // ค่าของ header: จำนวนเต็มบวก ("12") — ว่าง/0/ข้อความอื่น = คำขอนี้ไม่ได้ถูกย่อ
  function b3cTurns(v) {
    var m = /^\s*(\d{1,6})\s*$/.exec(v == null ? "" : String(v));
    return m ? +m[1] : 0;
  }
  // เฉพาะคำขอแชตของ WebUI (POST /v1/chat/completions origin เดียวกัน) → id แชต ("" = คำขอไม่มี id) · อื่นๆ → null (ไม่แตะเลย)
  function b3cConvOf(input, init) {
    var u = typeof input === "string" ? input : input && typeof input.url === "string" ? input.url : input && input.href ? String(input.href) : "";
    if (!u || u.indexOf("chat/completions") < 0) return null;
    var url;
    try { url = new URL(u, location.href); } catch (e) { return null; }
    if (url.origin !== location.origin || !/\/v1\/chat\/completions$/.test(url.pathname)) return null;
    var isReq = typeof input !== "string" && typeof Request === "function" && input instanceof Request;
    var method = String((init && init.method) || (isReq ? input.method : "GET")).toUpperCase();
    if (method !== "POST") return null;
    var h;
    try { h = new Headers((init && init.headers) || (isReq ? input.headers : undefined)); } catch (e) { return ""; }
    return planConv(h.get("X-Conversation-Id"));
  }
  // ผลของคำขอแชตหนึ่งครั้ง: มี header (n > 0) = จำ/อัปเดตจำนวนรอบ · ไม่มี/0 = ลบ (เฉพาะคำขอที่รู้ id แชต)
  // คำขอที่ไม่มี id (pre-encode ของ WebUI) ตั้งค่าให้แชตที่เปิดอยู่ได้ แต่ลบไม่ได้ — มันไม่ได้บอกว่าแชตนั้นสั้นลง
  function b3cNote(conv, res) {
    if (!res || !res.ok || !res.headers || typeof res.headers.get !== "function") return;
    var n = b3cTurns(res.headers.get(B3C_HDR)), id = conv || "", r = route();
    if (!id && n > 0 && r.name === "chat" && r.id) id = r.id;
    if (!id) return;
    var had = b3cState[id];
    if (n > 0) {
      if (had && had.n === n) return;
      b3cState[id] = { n: n, at: Date.now() };
      b3cSave();
      if (!had && r.name === "chat" && r.id === id) b2Say(A3("The earlier part of this chat was summarized to fit the model's memory"));
    } else if (conv && had) {
      delete b3cState[id];
      b3cSave();
    } else return;
    schedule();
  }
  var b3cInner = window.fetch;
  if (typeof b3cInner === "function") {
    window.fetch = function (input, init) {
      var conv = null;
      try { conv = b3cConvOf(input, init); } catch (e) { conv = null; }
      var p = b3cInner.apply(window, arguments);
      if (conv === null || !p || typeof p.then !== "function") return p;
      // กิ่งข้าง: อ่านแค่ header แล้วจบ (จัดการ reject ของกิ่งนี้เอง) — WebUI ได้ Promise ตัวเดิม ข้อผิดพลาดของมันไม่ถูกกลืน
      p.then(function (res) { try { b3cNote(conv, res); } catch (e) {} }, function () {});
      return p;
    };
  }
  window.addEventListener("storage", function (e) {
    if (e && e.key === B3C_KEY) { b3cState = b3cLoad(); schedule(); }
  });
  function b3cTipShow(on) {
    if (!b3cTip) return;
    if (!on) b3cPinned = false;
    if (b3cTip.hidden === !on) return;
    b3cTip.hidden = !on;
    setAt(b3cBtn, "data-open", on ? "1" : null);
  }
  function b3cMake() {
    b3cEl = b2El("div", "qw-compact");
    b3cEl.setAttribute("role", "note");
    var r1 = el("span", "qw-compact-rule"), r2 = el("span", "qw-compact-rule");
    r1.setAttribute("aria-hidden", "true");
    r2.setAttribute("aria-hidden", "true");
    b3cBtn = el("button", "qw-compact-b");
    b3cBtn.type = "button";
    b3cBtn.setAttribute("aria-describedby", "qwCompactTip");
    b3cBtn.innerHTML = xIcon("compact");
    b3cTxt = el("span", "qw-compact-t");
    var info = el("span", "qw-compact-i");
    info.setAttribute("aria-hidden", "true");
    info.innerHTML = xIcon("info");
    b3cBtn.appendChild(b3cTxt);
    b3cBtn.appendChild(info);
    b3cTip = el("div", "qw-compact-tip");
    b3cTip.id = "qwCompactTip";
    b3cTip.setAttribute("role", "tooltip");
    b3cTip.hidden = true;
    // ชี้ = เปิดหลังหน่วงสั้นๆ, คลิก/แตะ = ปักไว้ (จอสัมผัสไม่มี hover), โฟกัสด้วยคีย์บอร์ด = เปิด, Esc/ออก = ปิด
    b3cBtn.addEventListener("mouseenter", function () {
      clearTimeout(b3cHoverT);
      b3cHoverT = setTimeout(function () { b3cTipShow(true); }, 350);
    });
    b3cBtn.addEventListener("mouseleave", function () { clearTimeout(b3cHoverT); if (!b3cPinned) b3cTipShow(false); });
    b3cBtn.addEventListener("click", function (e) {
      e.preventDefault();
      clearTimeout(b3cHoverT);
      b3cPinned = !b3cPinned || b3cTip.hidden;
      b3cTipShow(b3cPinned);
    });
    b3cBtn.addEventListener("focus", function () {
      var fv = false;
      try { fv = b3cBtn.matches(":focus-visible"); } catch (e) {}
      if (fv) b3cTipShow(true);
    });
    b3cBtn.addEventListener("blur", function () { b3cTipShow(false); });
    b3cBtn.addEventListener("keydown", function (e) {
      if (e.key !== "Escape" || b3cTip.hidden) return;
      e.preventDefault();
      e.stopPropagation();
      b3cTipShow(false);
    });
    b3cEl.appendChild(r1);
    b3cEl.appendChild(b3cBtn);
    b3cEl.appendChild(r2);
    b3cEl.appendChild(b3cTip);
  }
  function b3cNum(n) {
    try { return Number(n).toLocaleString(lang() === "th" ? "th-TH" : "en-GB"); } catch (e) { return String(n); }
  }
  // จาก extrasPass() ทุกรอบ: แสดงเฉพาะในแชตที่ถูกย่อ — อยู่ในฟอร์ม ก่อนแถบโหมดวางแผน (ถ้ามี) หรือก่อนการ์ดกล่องพิมพ์
  function b3Pass(r) {
    if (!B3C_READY) return;
    var f = composerForm(), area = f && f.querySelector('[data-slot="input-area"]');
    var c = r.name === "chat" && r.id ? b3cState[r.id] : null;
    if (!c || !f || !area) {
      if (b3cEl) { b3cTipShow(false); detach(b3cEl); }
      return;
    }
    if (!b3cEl) b3cMake();
    // ย้ายไปอีกแชตที่ถูกย่อเหมือนกัน (ใช้ชิ้นเดิม) — คำอธิบายที่ปักค้างไว้ของแชตก่อนต้องปิด
    if (b3cEl.getAttribute("data-chat") !== r.id) { b3cTipShow(false); setAt(b3cEl, "data-chat", r.id); }
    var before = planBar && planBar.parentNode === f ? planBar : area;
    if (b3cEl.parentNode !== f || b3cEl.nextElementSibling !== before) f.insertBefore(b3cEl, before);
    var n = b3cNum(c.n);
    setTxt(b3cTxt, L3("Earlier part of this chat summarized ({n} turns)").replace("{n}", n));
    setTxt(b3cTip, L3("This chat got longer than the model can hold at once, so the middle part ({n} turns) was summarized automatically. Qwen still sees your first message, the summary and the latest turns. Every message is still here on this page.").replace("{n}", n));
    setAt(b3cEl, "data-turns", String(c.n));
  }
  // ---- API เพิ่ม: compaction() → {id, turns, shown} ของแชตที่เปิดอยู่ (ให้ shell/เทสต์ถามได้) ----
  window.qwenEnhance.compaction = function () {
    var r = route(), c = r.name === "chat" && r.id ? b3cState[r.id] : null;
    return { id: r.id || null, turns: c ? c.n : 0, shown: !!(b3cEl && b3cEl.isConnected) };
  };
  var B3C_READY = true;
  schedule();
})();
