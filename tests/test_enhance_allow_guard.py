# -*- coding: utf-8 -*-
"""
เทสต์รอบ 5 แก้หลังรีวิว (2026-09-30) ของ webui-enhance.js / webui-theme.css (เจ้าของ: enhance)

ข้อที่รีวิวความปลอดภัยพบ แล้วแก้ในไฟล์นี้:
  F1 (major) "Always allow all tools from <เซิร์ฟเวอร์>" บนการ์ดของเครื่องมืออื่น (local_do) หรือสวิตช์ "Always allow"
     ในหน้าตั้งค่า ใส่ local_confirm ลงรายการ "อนุญาตเสมอ" ในหน่วยความจำของ WebUI → local_confirm รันโดยไม่มีการ์ด
     ไม่มีใครเห็น review จนกว่าจะโหลดหน้าใหม่ (boot.js ตัดแค่ตอนเปิดหน้า)
     → ALLOW_GUARD (ต้นไฟล์): ดัก Storage.setItem + จำ Set ที่รับคีย์ local_confirm แล้วลบคีย์ออกจาก Set นั้นทันที,
       ตัดคีย์ตอนเปิดหน้า/จาก storage event · ฝั่ง UI: ซ่อนรายการเมนู, ล็อกช่อง "Always allow", ใส่ class การ์ดแบบ sync
  F2 (minor) กล่องตรวจทานวาดสตริงดิบ ขณะที่เซิร์ฟเวอร์ยอมรับบรรทัดว่าง/ช่องว่างท้ายบรรทัดไม่จำกัด → โค้ดจริงหลุดใต้ขอบ
     → rvNormalize = guard.normalize_review ทุกประการ (เทียบกับฟังก์ชันจริงของเซิร์ฟเวอร์) + เตือน "กดอนุญาตก็ไม่รัน"
       ตรงกับจุดที่เซิร์ฟเวอร์ปฏิเสธช่องว่างที่เกินขอบเขต (guard._review_norm ของรอบแก้ฝั่ง mcp)
  F4 (minor) local_confirm ถูกปฏิเสธแล้วคนไม่เห็นอะไร → ป้ายผลบนแถวเครื่องมือ (ข้อความจริงของเซิร์ฟเวอร์ทุกแบบถูกจัดชนิดถูก)

ส่วนที่ 1 — รันเสมอ (Node รันฟังก์ชันจริงจากซอร์ส, ไม่เปิดเบราว์เซอร์/hub, ไม่แตะบริการจริง)
ส่วนที่ 2 — E2E (ปิดเป็นค่าเริ่มต้น): set QWEN_UI_E2E=1 — hub สำเนาบนพอร์ตว่าง 8178-8185 (import hub.py เป็นโมดูล)
  + Edge headless โปรไฟล์ชั่วคราว คำขอหาโมเดล/MCP/hub API ทุกตัวถูกดักใน CDP แล้วตอบด้วยข้อมูลจำลอง
  (ไม่โหลดโมเดล ไม่เรียกเครื่องมือจริง ไม่เขียนค่าตั้งของผู้ใช้)
ชี้ไปไฟล์สำเนาได้: QWEN_ENH_FILE, QWEN_THEME_FILE, QWEN_STATIC_DIR (E2E)
"""
import base64
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

ENH = os.environ.get("QWEN_ENH_FILE") or r"C:\LLM\projects\static\webui-enhance.js"
CSS = os.environ.get("QWEN_THEME_FILE") or r"C:\LLM\projects\static\webui-theme.css"
STATIC_DIR = os.environ.get("QWEN_STATIC_DIR") or ""
HUB = r"C:\LLM\projects\hub.py"
TOOLS = r"C:\LLM\projects\tools"
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
HAVE_NODE = os.path.isfile(NODE) if os.path.isabs(NODE) else bool(shutil.which("node"))

GUARD_START = "  var ALLOW_GUARD = (function allowGuard() {"
GUARD_END = "\n  var root = document.documentElement;"
UI_START = "  /* ---- ALLOW-GUARD ฝั่ง UI"
CF_START = "  /* ---- ป้ายผลของ local_confirm"
CF_END = "  // ---- เนื้อความของการแจ้งเตือน \"ตอบเสร็จ\""
R4_START = "R4 (รอบ 5, 2026-09-30)"
R4_END = "\n  function confirmCards()"

NEW_LABELS = [
    "The model padded this text with extra blank lines or spaces (left out here). The server refuses text padded like "
    "this, so allowing it won't run anything. Choose Deny.",
    "local_confirm always asks, so you can see exactly what will run before you allow it.",
    "Ran — expand to see the result",
    "Not run — the review text didn't match",
    "Not run — the confirm code expired or was already used",
    "Not run — you chose Deny",
    "Not run — interrupted",
    "Not run — refused",
    "Failed — expand to see the error",
]


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def js_block(src, start):
    """ซอร์สของบล็อก {...} ตัวแรกหลังตำแหน่ง start (นับวงเล็บ ข้ามสตริง/คอมเมนต์/regex แบบง่าย)"""
    i = src.index("{", start)
    depth, q, n, j = 0, None, len(src), i
    while j < n:
        c = src[j]
        if q:
            if c == "\\":
                j += 2
                continue
            if c == q:
                q = None
        elif c in "\"'`":
            q = c
        elif src.startswith("//", j):
            j = src.index("\n", j)
            continue
        elif src.startswith("/*", j):
            j = src.index("*/", j) + 2
            continue
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1
    raise ValueError("unbalanced block")


def run_node(code):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(code)
        path = fh.name
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True, encoding="utf-8", timeout=60)
    finally:
        os.remove(path)
    if r.returncode != 0:
        raise AssertionError("node failed: %s" % r.stderr[-3000:])
    return json.loads(r.stdout)


def sections(src):
    g0 = src.index(GUARD_START)
    guard = src[g0:src.index(GUARD_END, g0)]
    u0 = src.index(UI_START)
    c0 = src.index(CF_START, u0)
    ui = src[u0:c0]
    cf = src[c0:src.index(CF_END, c0)]
    a = src.index(R4_START)
    r4 = src[src.rindex("/*", 0, a):src.index(R4_END, a)]
    return guard, ui, cf, r4


# สภาพแวดล้อมจำลองของ ALLOW_GUARD: Storage/localStorage/sessionStorage, window.addEventListener, location.reload
GUARD_ENV = r"""
class Storage {
  constructor(d) { this._d = Object.assign({}, d || {}); }
  getItem(k) { return Object.prototype.hasOwnProperty.call(this._d, k) ? this._d[k] : null; }
  setItem(k, v) { this._d[k] = String(v); }
  removeItem(k) { delete this._d[k]; }
}
var localStorage = new Storage(__INIT__), sessionStorage = new Storage(__SESSION__);
var listeners = {};
var window = {Set: Set, Storage: Storage, addEventListener: function (t, f) { listeners[t] = f; }};
var reloads = 0, location = {reload: function () { reloads++; }};
// แบบเดียวกับ SvelteSet (za) ของ bundle b10984: add/delete ของตัวเองเรียก super.* แล้วนับรุ่น
class SSet extends Set {
  add(e) { if (!super.has(e)) { super.add(e); this.v = (this.v || 0) + 1; } return this; }
  delete(e) { var r = super.delete(e); if (r) this.v++; return r; }
}
var J6 = "LlamaUi.alwaysAllowedTools";
// แบบเดียวกับ ZMt (p2) ของ bundle: persist เขียน [...this._tools] ทันทีหลังเพิ่ม
class Perm {
  constructor() { this._tools = new SSet(); }
  initialize() { var e = localStorage.getItem(J6); if (e) for (var r of JSON.parse(e)) this._tools.add(r); }
  allowTool(e) { this._tools.add(e); this.persist(); }
  allowTools(l) { for (var r of l) this._tools.add(r); this.persist(); }
  hasTool(e) { return this._tools.has(e); }
  revokeTool(e) { this._tools.delete(e); this.persist(); }
  persist() { localStorage.setItem(J6, JSON.stringify([...this._tools])); }
}
// getter allTools ของ Bn สร้าง Set กันซ้ำชั่วคราวใหม่ทุกครั้ง (มีคีย์ local_confirm ด้วย)
function allToolsTemp(keys) { var r = new SSet(); keys.forEach(function (k) { r.add(k); }); return r; }
function flush() { return new Promise(function (r) { setTimeout(r, 5); }); }
"""


@unittest.skipUnless(HAVE_NODE, "ไม่มี node")
class AllowGuardBackstopTests(unittest.TestCase):
    """F1 ด่านหลัก: ไม่ว่าคนจะกดตรงไหน คีย์ของ local_confirm ต้องไม่ค้างในหน่วยความจำของ WebUI"""

    @classmethod
    def setUpClass(cls):
        cls.src = read(ENH)
        cls.guard, cls.ui, cls.cf, cls.r4 = sections(cls.src)

    def run_guard(self, body, init=None, session=None):
        env = GUARD_ENV.replace("__INIT__", json.dumps(init or {})).replace("__SESSION__", json.dumps(session or {}))
        code = env + self.guard + "\n(async function () {\n" + body + "\n})().catch(function (e) { " \
            "console.error(e && e.stack || e); process.exit(3); });"
        return run_node(code)

    def test_installed_before_everything_else(self):
        i = self.src.index(GUARD_START)
        self.assertLess(i, self.src.index("var root = document.documentElement;"))
        self.assertLess(i, self.src.index("new MutationObserver("))
        # ติดตั้งตรงนี้เท่านั้น (ไม่มีที่อื่นแทน setItem/add ซ้ำ)
        self.assertEqual(self.src.count('Object.defineProperty(SP, "add"'), 1)
        self.assertEqual(self.src.count('Object.defineProperty(StP, "setItem"'), 1)
        self.assertIn("allowGuard: function ()", self.src)

    def test_always_server_on_local_do_card_never_keeps_local_confirm(self):
        r = self.run_guard(r"""
var p2 = new Perm(); p2.initialize();
var keys = ["mcp-local:local_read", "mcp-local:local_do", "mcp-local:local_confirm"];
// เหมือน resolver ของ ALWAYS_SERVER: allTools ถูกอ่านหลายรอบ (Set ชั่วคราว) แล้วค่อย allowTools
allToolsTemp(keys); allToolsTemp(keys); allToolsTemp(keys.concat(["mcp-websearch:search"]));
p2.allowTools(keys);
var out = {has: p2.hasTool("mcp-local:local_confirm"), hasDo: p2.hasTool("mcp-local:local_do"),
           stored: JSON.parse(localStorage.getItem(J6)), stats: ALLOW_GUARD.stats, version: p2._tools.v};
await flush();
out.reloads = reloads;
console.log(JSON.stringify(out));
""")
        self.assertFalse(r["has"], "local_confirm ต้องไม่อยู่ในรายการอนุญาตเสมอในหน่วยความจำ")
        self.assertTrue(r["hasDo"], "เครื่องมืออื่นยังอนุญาตเสมอได้ตามที่คนเลือก")
        self.assertEqual(r["stored"], ["mcp-local:local_read", "mcp-local:local_do"])
        self.assertEqual(r["stats"]["deleted"], 1)
        self.assertTrue(r["stats"]["installed"])
        self.assertEqual(r["reloads"], 0, "หา Set เจอ = ไม่ต้องโหลดหน้าใหม่")
        self.assertEqual(r["version"], 4, "ลบผ่าน .delete() ของ SvelteSet เอง (UI ได้รู้ว่าค่าเปลี่ยน)")

    def test_settings_checkbox_and_every_confirm_key_form(self):
        r = self.run_guard(r"""
var p2 = new Perm();
var out = {};
["mcp-local:local_confirm", "mcp-local-full:local_confirm", "mcp-mine:local_confirm", "mcp:local_confirm"].forEach(function (k) {
  p2.allowTool(k);
  out[k] = p2.hasTool(k);
});
["mcp-local:local_confirmx", "local_confirm", "mcp-local:local_do", "custom:local_confirm", "xmcp-local:local_confirm"].forEach(function (k) {
  p2.allowTool(k);
  out[k] = p2.hasTool(k);
});
out.stored = JSON.parse(localStorage.getItem(J6));
p2.revokeTool("mcp-local:local_do");
out.afterRevoke = JSON.parse(localStorage.getItem(J6));
await flush();
out.reloads = reloads;
console.log(JSON.stringify(out));
""")
        for k in ("mcp-local:local_confirm", "mcp-local-full:local_confirm", "mcp-mine:local_confirm", "mcp:local_confirm"):
            self.assertFalse(r[k], k)
        for k in ("mcp-local:local_confirmx", "local_confirm", "mcp-local:local_do", "custom:local_confirm",
                  "xmcp-local:local_confirm"):
            self.assertTrue(r[k], "ไม่ใช่คีย์ของ local_confirm ต้องไม่ถูกแตะ: " + k)
        self.assertNotIn("mcp-local:local_confirm", r["stored"])
        self.assertNotIn("mcp-local:local_do", r["afterRevoke"])
        self.assertEqual(r["reloads"], 0)

    def test_other_sets_and_keys_are_untouched(self):
        r = self.run_guard(r"""
// รายการเครื่องมือที่ปิดไว้ใช้คีย์รูปแบบเดียวกัน — ปิด local_confirm ได้ตามปกติ (ปลอดภัยกว่า)
var dis = new SSet(); dis.add("mcp-local:local_confirm");
localStorage.setItem("LlamaUi.disabledToolKeys", JSON.stringify([...dis]));
var plain = new Set([1, 2]); var ret = plain.add(3);
var obj = {}; var s2 = new Set(); s2.add(obj);
var d = Object.getOwnPropertyDescriptor(Set.prototype, "add");
var ds = Object.getOwnPropertyDescriptor(Storage.prototype, "setItem");
localStorage.setItem(J6, "not json local_confirm");
console.log(JSON.stringify({dis: dis.has("mcp-local:local_confirm"), disStored: localStorage.getItem("LlamaUi.disabledToolKeys"),
  ret: ret === plain, size: plain.size, obj: s2.has(obj), enumerable: d.enumerable, writable: d.writable,
  sEnumerable: ds.enumerable, junk: localStorage.getItem(J6), stats: ALLOW_GUARD.stats}));
""")
        self.assertTrue(r["dis"])
        self.assertEqual(r["disStored"], '["mcp-local:local_confirm"]')
        self.assertTrue(r["ret"])
        self.assertEqual(r["size"], 3)
        self.assertTrue(r["obj"])
        self.assertFalse(r["enumerable"])
        self.assertTrue(r["writable"])
        self.assertFalse(r["sEnumerable"])
        self.assertEqual(r["junk"], "not json local_confirm", "อ่านไม่ออก = WebUI ก็อ่านไม่ออก ปล่อยตามเดิม")
        self.assertEqual(r["stats"]["stripped"], 0)

    def test_startup_strips_both_keys_and_reloads_once(self):
        init = {"LlamaUi.alwaysAllowedTools": json.dumps(["mcp-local:local_read", "mcp-local:local_confirm"]),
                "LlamaCppWebui.alwaysAllowedTools": json.dumps(["mcp-local-full:local_confirm"])}
        r = self.run_guard(r"""
await flush();
console.log(JSON.stringify({a: localStorage.getItem(J6), b: localStorage.getItem("LlamaCppWebui.alwaysAllowedTools"),
  reloads: reloads, mark: sessionStorage.getItem("qwen-allow-guard-reload") != null, stats: ALLOW_GUARD.stats}));
""", init=init)
        self.assertEqual(json.loads(r["a"]), ["mcp-local:local_read"])
        self.assertEqual(json.loads(r["b"]), [])
        self.assertEqual(r["reloads"], 1, "บันเดิลอาจอ่านคีย์เข้าหน่วยความจำก่อนสคริปต์นี้ → โหลดใหม่ครั้งเดียว")
        self.assertTrue(r["mark"])
        # โหลดใหม่ภายใน 30 วินาทีแล้วยังเจอ = ไม่วนโหลดซ้ำ (ตัดอย่างเดียว)
        r = self.run_guard("await flush(); console.log(JSON.stringify({reloads: reloads, a: localStorage.getItem(J6)}));",
                           init=init, session={"qwen-allow-guard-reload": str(int(time.time() * 1000))})
        self.assertEqual(r["reloads"], 0)
        self.assertEqual(json.loads(r["a"]), ["mcp-local:local_read"])
        # ไม่มีคีย์ = ไม่ทำอะไรเลย
        r = self.run_guard("await flush(); console.log(JSON.stringify({reloads: reloads, s: ALLOW_GUARD.stats}));",
                           init={"LlamaUi.alwaysAllowedTools": '["mcp-local:local_read"]'})
        self.assertEqual(r["reloads"], 0)
        self.assertEqual(r["s"]["stripped"], 0)

    def test_write_without_known_holder_is_stripped_and_reloads(self):
        r = self.run_guard(r"""
localStorage.setItem(J6, JSON.stringify(["a", "mcp-local:local_confirm"]));   // ไม่มี Set ในหน่วยความจำที่ตรงกัน
var first = localStorage.getItem(J6);
await flush();
var n1 = reloads;
localStorage.setItem(J6, JSON.stringify(["mcp-local:local_confirm"]));
await flush();
console.log(JSON.stringify({first: first, n1: n1, n2: reloads, stats: ALLOW_GUARD.stats}));
""")
        self.assertEqual(r["first"], '["a"]')
        self.assertEqual(r["n1"], 1, "ไม่รู้ว่าในหน่วยความจำมีค้างไหม = โหลดใหม่")
        self.assertEqual(r["n2"], 1, "ครั้งที่สองภายใน 30 วินาทีไม่โหลดซ้ำ")

    def test_storage_event_from_other_documents(self):
        r = self.run_guard(r"""
localStorage._d[J6] = JSON.stringify(["mcp-local:local_confirm", "x"]);      // หน้าอื่นเขียน (ไม่ผ่าน setItem ของหน้านี้)
listeners.storage({key: J6, newValue: localStorage._d[J6], storageArea: localStorage});
var a = localStorage.getItem(J6);
localStorage._d["other"] = "mcp-local:local_confirm";
listeners.storage({key: "other", newValue: "mcp-local:local_confirm", storageArea: localStorage});
listeners.storage({key: J6, newValue: null, storageArea: localStorage});
listeners.storage({key: J6, newValue: '["mcp-local:local_confirm"]', storageArea: sessionStorage});
console.log(JSON.stringify({a: a, other: localStorage.getItem("other")}));
""")
        self.assertEqual(r["a"], '["x"]')
        self.assertEqual(r["other"], "mcp-local:local_confirm")


# DOM จิ๋วสำหรับส่วน UI / กล่องตรวจทาน
DOM_STUB = r"""
function mkEl(tag, cls) {
  var e = {tag: tag, nodeType: 1, className: cls || "", children: [], attrs: {}, title: "", hidden: false, _text: null,
           parentNode: null, style: {setProperty: function () {}}};
  e.classList = {
    add: function (c) { if (!e.classList.contains(c)) e.className = (e.className ? e.className + " " : "") + c; },
    remove: function (c) { e.className = e.className.split(" ").filter(function (x) { return x && x !== c; }).join(" "); },
    contains: function (c) { return (" " + e.className + " ").indexOf(" " + c + " ") >= 0; }
  };
  e.appendChild = function (c) { e.children.push(c); c.parentNode = c.parentElement = e; e._text = null; return c; };
  e.removeChild = function (c) { e.children.splice(e.children.indexOf(c), 1); c.parentNode = c.parentElement = null; return c; };
  e.setAttribute = function (k, v) { e.attrs[k] = String(v); };
  e.getAttribute = function (k) { return Object.prototype.hasOwnProperty.call(e.attrs, k) ? e.attrs[k] : null; };
  e.hasAttribute = function (k) { return Object.prototype.hasOwnProperty.call(e.attrs, k); };
  e.removeAttribute = function (k) { delete e.attrs[k]; };
  Object.defineProperty(e, "firstChild", {get: function () { return e.children[0] || null; }});
  Object.defineProperty(e, "textContent", {
    get: function () { return e._text != null ? e._text : e.children.map(function (c) { return c.textContent; }).join(""); },
    set: function (v) { e._text = String(v); e.children = []; }
  });
  return e;
}
var document = {createTextNode: function (t) { return {nodeType: 3, textContent: t, text: true}; },
                querySelectorAll: function () { return []; }};
function el(tag, cls) { return mkEl(tag, cls); }
function xIcon() { return "<svg/>"; }
function hasOwn(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
"""


@unittest.skipUnless(HAVE_NODE, "ไม่มี node")
class AllowGuardUiTests(unittest.TestCase):
    """F1 ฝั่ง UI: เมนู "อนุญาตเสมอ" ที่ข้าม local_confirm ถูกซ่อน, ช่องในหน้าตั้งค่าถูกล็อก, ตัดสินแบบ sync ใน observer"""

    @classmethod
    def setUpClass(cls):
        cls.src = read(ENH)
        cls.guard, cls.ui, cls.cf, cls.r4 = sections(cls.src)

    def ui_env(self, cfg):
        return DOM_STUB + r"""
var listeners = {}, window = {addEventListener: function (t, f) { (listeners[t] = listeners[t] || []).push(f); }};
var localStorage = {getItem: function (k) { return k === "LlamaUi.config" ? __CFG__ : null; }};
var PROMPT_SEL = ".chat-messages div.rounded-lg.border.bg-card.p-3", CONFIRM_TOOL = "local_confirm";
var TX_FAST = ".markdown-content, pre, code, .reasoning-content";
var ran = 0; function confirmCards() { ran++; }
function enText(n) { return n.textContent; }
""".replace("__CFG__", json.dumps(json.dumps(cfg))) + self.ui

    def test_menu_items_hidden_only_for_our_servers_and_local_confirm(self):
        cfg = {"mcpServers": json.dumps([
            {"id": "websearch", "name": "ค้นอินเทอร์เน็ต", "url": "http://127.0.0.1:8791/mcp"},
            {"id": "local", "name": "เครื่องนี้", "url": "http://127.0.0.1:8792/fast/project1"},
            {"id": "local-full", "name": "เครื่องนี้ (เครื่องมือครบ)", "url": "http://127.0.0.1:8792/mcp/project1"},
            {"id": "mine", "name": "ของฉัน", "url": "http://localhost:8792/fast/x"},
            {"id": "other", "name": "other", "url": "http://127.0.0.1:9000/mcp"}])}
        cases = {
            "Always allow all tools from qwen38-local-fast": True,
            "Always allow all tools from qwen38-local": True,
            "Always allow all tools from qwen38-local (2)": True,
            "Always allow all tools from เครื่องนี้": True,
            "Always allow all tools from เครื่องนี้ (เครื่องมือครบ)": True,
            "Always allow all tools from ของฉัน": True,
            "Always allow all tools from http://127.0.0.1:8792/fast/project1": True,
            "Always allow  local_confirm \n tool": True,
            "Always allow local_confirm tool": True,
            "Always allow all tools from ค้นอินเทอร์เน็ต": False,
            "Always allow all tools from other": False,
            "Always allow all tools from my tool": False,
            "Always allow local_do tool": False,
            "Always allow local_confirmx tool": False,
            "Approve all tools from MCP Tools": False,
            "Copy": False,
        }
        code = self.ui_env(cfg) + "\nvar labels = ourServerLabels(), out = {};\n" + \
            "".join("out[%s] = allowItemBlocked(%s, labels);\n" % (json.dumps(k), json.dumps(k)) for k in cases) + \
            "console.log(JSON.stringify(out));"
        r = run_node(code)
        for k, want in cases.items():
            self.assertEqual(r[k], want, k)

    def test_hide_lock_and_event_blocking(self):
        code = self.ui_env({}) + r"""
var it = mkEl("div", "relative flex");
allowHide(it, true);
var hidden = {cls: it.className, attrs: JSON.parse(JSON.stringify(it.attrs))};
allowHide(it, false);
var shown = {cls: it.className, attrs: JSON.parse(JSON.stringify(it.attrs))};
var own = mkEl("div"); own.setAttribute("data-disabled", ""); allowHide(own, true); allowHide(own, false);
// ปุ่ม/ช่องที่ล็อก: เหตุการณ์ทุกชนิดถูกหยุดก่อนถึง bits-ui (Enter/Space เท่านั้นสำหรับแป้นพิมพ์)
function ev(type, inside, key) {
  var e = {type: type, key: key, stopped: 0, prevented: 0,
           target: {nodeType: 1, closest: function (s) { return inside && s.indexOf("qw-allow-hidden") >= 0 ? {} : null; }},
           preventDefault: function () { e.prevented++; }, stopImmediatePropagation: function () { e.stopped++; }};
  listeners[type].forEach(function (f) { f(e); });
  return e.stopped + e.prevented;
}
var blocked = {click: ev("click", true), pointerdown: ev("pointerdown", true), pointerup: ev("pointerup", true),
  mousedown: ev("mousedown", true), mouseup: ev("mouseup", true), enter: ev("keydown", true, "Enter"), space: ev("keydown", true, " "),
  arrow: ev("keydown", true, "ArrowDown"), outside: ev("click", false)};
console.log(JSON.stringify({hidden: hidden, shown: shown, ownDis: own.hasAttribute("data-disabled"), blocked: blocked}));
"""
        r = run_node(code)
        self.assertIn("qw-allow-hidden", r["hidden"]["cls"])
        for k in ("aria-hidden", "aria-disabled", "data-disabled"):
            self.assertIn(k, r["hidden"]["attrs"], k)
        self.assertNotIn("qw-allow-hidden", r["shown"]["cls"])
        self.assertEqual(r["shown"]["attrs"], {})
        self.assertTrue(r["ownDis"], "data-disabled ที่ bits-ui ใส่เองต้องไม่ถูกถอด")
        b = r["blocked"]
        for k in ("click", "pointerdown", "pointerup", "mousedown", "mouseup", "enter", "space"):
            self.assertEqual(b[k], 2, k)
        self.assertEqual(b["arrow"], 0, "เลื่อนด้วยลูกศรยังใช้ได้ (bits-ui ข้ามรายการที่ data-disabled เอง)")
        self.assertEqual(b["outside"], 0)

    def test_settings_checkbox_locked_only_for_local_confirm(self):
        code = self.ui_env({}) + r"""
function row(name) {
  var r = mkEl("div", "flex items-center gap-2 rounded px-2 py-1.5 text-sm");
  var n = mkEl("span", "flex min-w-0 flex-1"); n.textContent = " " + name + " ";
  var e = mkEl("div", "flex w-16 shrink-0 justify-center"), a = mkEl("div", "flex w-20 shrink-0 justify-center");
  var sw = mkEl("button"); sw.setAttribute("role", "checkbox");
  a.appendChild(sw); r.appendChild(n); r.appendChild(e); r.appendChild(a);
  r.firstElementChild = n;
  return sw;
}
var rows = [row("local_read"), row("local_do"), row("local_confirm")];
document.querySelectorAll = function (s) { return s === ALLOW_SW_SEL ? rows : []; };
allowSwitches(); allowSwitches();
var out = rows.map(function (sw) { return [sw.parentNode.className.indexOf("qw-allow-locked") >= 0, sw.getAttribute("aria-disabled"),
  sw.getAttribute("tabindex"), sw.parentNode.getAttribute("title")]; });
console.log(JSON.stringify({out: out, sel: ALLOW_SW_SEL}));
"""
        r = run_node(code)
        self.assertEqual(r["out"][0], [False, None, None, None])
        self.assertEqual(r["out"][1], [False, None, None, None])
        self.assertEqual(r["out"][2][:3], [True, "true", "-1"])
        self.assertIn("always asks", r["out"][2][3])
        self.assertIn('[role="checkbox"]', r["sel"], "b10984 วาดช่อง Always allow เป็น checkbox")

    def test_perm_guard_runs_for_cards_menus_checkboxes_not_for_streamed_text(self):
        code = self.ui_env({}) + r"""
var runs = [];
confirmCards = function () { runs.push("cards"); };
function node(opts) {
  return {nodeType: 1,
    closest: function (s) { if (s === TX_FAST) return opts.content ? {} : null; return opts.inCard ? {} : null; },
    matches: function (s) { return !!opts.is; }, querySelector: function (s) { return opts.has ? {} : null; }};
}
function text(parent) { return {nodeType: 3, parentNode: parent}; }
function go(recs) { runs = []; permGuard(recs); return runs.length; }
var out = {
  card: go([{type: "childList", addedNodes: [node({is: true})]}]),
  containsCard: go([{type: "childList", addedNodes: [node({has: true})]}]),
  inCard: go([{type: "childList", addedNodes: [node({inCard: true})]}]),
  streamed: go([{type: "childList", addedNodes: [node({content: true, is: true}), text(node({content: true}))]},
                {type: "characterData", target: text(node({content: true}))}]),
  unrelated: go([{type: "childList", addedNodes: [node({})]}, {type: "characterData", target: text(node({}))}]),
  cardText: go([{type: "characterData", target: text(node({inCard: true}))}]),
  attr: go([{type: "attributes", target: node({is: true})}])
};
console.log(JSON.stringify(out));
"""
        r = run_node(code)
        self.assertEqual(r["card"], 1)
        self.assertEqual(r["containsCard"], 1)
        self.assertEqual(r["inCard"], 1)
        self.assertEqual(r["cardText"], 1)
        self.assertEqual(r["streamed"], 0, "ข้อความที่สตรีมในเนื้อหาไม่ทำให้สแกนทั้งหน้า")
        self.assertEqual(r["unrelated"], 0)
        self.assertEqual(r["attr"], 0)

    def test_wired_synchronously_into_body_observer(self):
        obs = js_block(self.src, self.src.index("var bodyObs = new MutationObserver("))
        self.assertIn("permGuard(recs)", obs)
        self.assertLess(obs.index("bodyObs.takeRecords()"), obs.index("permGuard(recs)"),
                        "หลัง takeRecords: กล่องที่เราใส่ต้องเป็น record รอบหน้าให้ตัวแปลแปล")
        self.assertNotIn("setTimeout", obs[obs.index("permGuard(recs)") - 200:obs.index("permGuard(recs)")])
        self.assertIn('[role="menuitem"]', self.ui)
        for bad in ("innerHTML", "fetch(", "XMLHttpRequest", "http://", "Claude", "Anthropic"):
            for part in (self.ui, self.cf, self.guard):
                self.assertNotIn(bad, part.replace("https?:\\/\\/", ""), bad)


@unittest.skipUnless(HAVE_NODE, "ไม่มี node")
class ReviewNormalizeTests(unittest.TestCase):
    """F2: กล่องตรวจทานแสดงรูปเดียวกับที่เซิร์ฟเวอร์เทียบ (guard.normalize_review) — ตรวจกับฟังก์ชันจริงของเซิร์ฟเวอร์"""

    @classmethod
    def setUpClass(cls):
        cls.src = read(ENH)
        cls.guard, cls.ui, cls.cf, cls.r4 = sections(cls.src)
        cls.srv_guard = C.import_local("guard")

    def test_same_result_as_server_normalize_review(self):
        base = "⚠ คำเตือน (WARNING): x\n[python] run\n 1│ a = 1\n 2│ \n 3│ b = 2"
        cases = [
            base, "\n" * 300 + base, base + "\n" * 50, "\r\n".join(base.split("\n")) + "\r\n",
            "\n".join(ln + " " * 10000 for ln in base.split("\n")), "\n".join(ln + "\t \t" for ln in base.split("\n")),
            "\n" + base + "\n", "  \n\t\n" + base + "\n \n\t", "a\rb\n c \r\n", "x\r", "\r\r\n", " ", "", "\n\n", "only",
            "a\n\n\nb", "  lead spaces kept\ntrail", "a\u00a0\nb\u3000", "\u202e rlo \n", "tab\tinside\t",
            "x" + " " * 50 + "y" + " " * 50, "\n".join(["l%d" % i for i in range(200)]),
        ]
        cases += ["  " + base, "     " + base, "\t" + base, "\n\n\n" + base + "\n\n\n\n", "\n\n\n\n" + base,
                  base + "\n\n\n\n\n", base.replace("\n", "    \n"), base.replace("\n", "     \n", 1)]
        code = self.r4 + "\nconsole.log(JSON.stringify(%s.map(function (s) { var n = rvNormalize(s); " \
            "return [n.text, rvPadded(n)]; })));" % json.dumps(cases)
        got = run_node(code)
        for s, (text, _pad) in zip(cases, got):
            self.assertEqual(text, self.srv_guard.normalize_review(s), repr(s[:80]))
        pads = [g[1] for g in got]
        # เตือนตรงกับที่เซิร์ฟเวอร์จะปฏิเสธพอดี (ช่องว่างที่ตัดเกินขอบเขต = review_matches เป็นเท็จ ไม่มีอะไรรัน)
        norm = getattr(self.srv_guard, "_review_norm", None)
        if norm is not None:
            for s, pad in zip(cases, pads):
                self.assertEqual(pad, not norm(s)[1], repr(s[:80]))
                if s.strip():
                    self.assertEqual(pad, not self.srv_guard.review_matches(self.srv_guard.normalize_review(s), s),
                                     repr(s[:80]))
        self.assertFalse(pads[0])
        self.assertTrue(pads[1], "บรรทัดว่างนำหน้า 300 บรรทัด = เตือน")
        self.assertTrue(pads[2])
        self.assertFalse(pads[3], "CRLF + ขึ้นบรรทัดท้าย 1 บรรทัดเป็นเรื่องปกติของการคัดลอก")
        self.assertTrue(pads[4], "ช่องว่างท้ายบรรทัดยาว = เตือน")
        self.assertFalse(pads[6], "บรรทัดว่างรอบข้อความ 1 บรรทัด (คัดลอกจากรั้ว) ไม่เตือน")

    def test_linear_time_on_long_space_runs(self):
        code = self.r4 + r"""
var s = "x" + new Array(200001).join(" ") + "y", t0 = Date.now();
var n = rvNormalize(s + "\n" + s);
console.log(JSON.stringify({ms: Date.now() - t0, len: n.text.length}));
"""
        r = run_node(code)
        self.assertLess(r["ms"], 2000)
        self.assertEqual(r["len"], 2 * 200002 + 1)

    def test_box_renders_normalized_text_and_warns(self):
        """S3 (2026-09-30 ดึก) เปลี่ยนสิ่งที่กล่องวาด: โค้ดในกล่อง = review ของเซิร์ฟเวอร์ (GET /review) เท่านั้น ไม่ใช่ของโมเดล
        (เทสต์เดิมป้อน review ของโมเดลแล้วคาดว่าจะถูกวาด + โน้ต "padded" — ทางนั้นไม่มีแล้ว) · review ของโมเดลที่เติมบรรทัดว่าง/
        ช่องว่างเกินขอบเขต = เซิร์ฟเวอร์ปฏิเสธ → คำเตือนแดง "ไม่ตรง" (rvModelDiffers) แทนโน้ต padded; ข้อความของโมเดลไม่ถูกวาด
        · ช่องว่างในขอบเขต/CRLF/ไม่ส่ง review/ส่งแต่ช่องว่าง = ไม่เตือน · review ของเซิร์ฟเวอร์ผ่าน rvNormalize ก่อนวาด"""
        code = DOM_STUB + self.r4 + r"""
var want = "[python] run\n1│ print(1)\n2│ x = 2";
function show(review, srvReview) {
  var st = {box: rvBox(), card: el("div"), seq: 0, key: null, good: false, r: null};
  var args = {confirm_token: "3fa1c29e"};
  if (review !== undefined) args.review = review;
  st.srv = {tok: "3fa1c29e", state: "ok", review: srvReview === undefined ? want : srvReview};
  rvShow(st, {status: "ok", callId: "c1", raw: "{}", args: args});
  var body = st.box.__qwBody, pre = null, notes = [];
  body.children.forEach(function (c) {
    if (c.tag === "pre") pre = c;
    if (c.className === "qw-review-note") notes.push([c.attrs["data-kind"], c.textContent]);
  });
  return {text: pre && pre.textContent, notes: notes, state: st.box.attrs["data-state"], card: st.card.attrs["data-qw-rv"],
          lines: st.box.__qwLines ? st.box.__qwLines.textContent : null};
}
var PAD = new Array(301).join("\n") + "[python] run" + new Array(4001).join(" ") + "\n1│ print(1)\t\t\n2│ x = 2" + new Array(51).join("\n");
console.log(JSON.stringify({
  padded: show(PAD),
  normal: show(want + "\n"),
  crlf: show(want.replace(/\n/g, "\r\n")),
  absent: show(undefined),
  blank: show("  \n\t "),
  srvTrail: show(undefined, "\n" + want + "\n\n")
}));
"""
        r = run_node(code)
        want = "[python] run\n1│ print(1)\n2│ x = 2"
        p = r["padded"]
        self.assertEqual((p["state"], p["card"]), ("ok", "ok"))
        self.assertEqual(p["text"], want, "วาด review ของเซิร์ฟเวอร์ ไม่ใช่ข้อความที่โมเดลเติมบรรทัดว่าง/ช่องว่าง")
        self.assertEqual(p["lines"], "3 lines — scroll to read them all", "นับบรรทัดของ review เซิร์ฟเวอร์")
        self.assertEqual([k for k, _ in p["notes"]], ["danger"], p["notes"])
        self.assertIn("differs from the server's version", p["notes"][0][1], "เติมเกินขอบเขต = เซิร์ฟเวอร์ปฏิเสธ = เตือนไม่ตรง")
        for k in ("normal", "crlf", "absent", "blank", "srvTrail"):
            self.assertEqual(r[k]["text"], want, k)
            self.assertEqual(r[k]["notes"], [], k)
        # ตรงกับที่เซิร์ฟเวอร์ตัดสินจริง: ข้อความที่เตือน = ข้อความที่ guard.review_matches ปฏิเสธ
        g = self.srv_guard
        if hasattr(g, "review_provided"):
            pad = ("\n" * 300 + "[python] run" + " " * 4000 + "\n1│ print(1)\t\t\n2│ x = 2" + "\n" * 50)
            self.assertTrue(g.review_provided(pad) and not g.review_matches(want, pad))
            for ok in (want + "\n", want.replace("\n", "\r\n")):
                self.assertTrue(g.review_matches(want, ok), repr(ok))
            self.assertFalse(g.review_provided("  \n\t "), "ส่งแต่ช่องว่าง = เหมือนไม่ส่ง (token อย่างเดียว)")


@unittest.skipUnless(HAVE_NODE, "ไม่มี node")
class ConfirmResultBadgeTests(unittest.TestCase):
    """F4: ป้ายผลของ local_confirm — ข้อความจริงของเซิร์ฟเวอร์ทุกแบบถูกจัดชนิดถูก, จับคู่แถวไม่เดา, อ่าน DB อย่างเดียว"""

    @classmethod
    def setUpClass(cls):
        cls.src = read(ENH)
        cls.guard, cls.ui, cls.cf, cls.r4 = sections(cls.src)
        cls.server = C.import_local("server")
        cls.server.load_modules()

    def kinds(self, texts):
        code = "var CONFIRM_TOOL = 'local_confirm'; function hasOwn(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }\n" + \
            self.cf + "\nconsole.log(JSON.stringify(%s.map(confirmResultKind)));" % json.dumps(texts)
        return run_node(code)

    def rpc(self, project, name, args, fast=True):
        reply = self.server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                        "params": {"name": name, "arguments": args}}, project, fast)
        return reply["result"]["content"][0]["text"]

    def test_real_server_texts(self):
        project = "cf-%s" % os.urandom(3).hex()
        d = C.new_dir("cfbadge")
        p = os.path.join(d, "a.txt")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write("one\n")
        hint = self.rpc(project, "local_do", {"action": "edit", "path": p, "old": "one", "new": "two"})
        args = C.confirm_args(hint)
        self.assertTrue(args["confirm_token"] and args["review"], hint[:300])
        texts = {
            "wrong_review": self.rpc(project, "local_confirm", dict(args, review=args["review"] + "x")),
            "no_token": self.rpc(project, "local_confirm", {}),
            "unknown_token": self.rpc(project, "local_confirm", {"confirm_token": "deadbeef", "review": "x"}),
            "wrong_surface": self.rpc(project, "local_confirm", args, fast=False),
            "ok": self.rpc(project, "local_confirm", args),
            "reused": self.rpc(project, "local_confirm", args),
        }
        with open(p, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "two\n", "ขั้นยืนยันที่ถูกต้องต้องทำงานจริง (texts['ok'] คือผลของการรัน)")
        # รอบ review-fetch (S2): review ไม่บังคับแล้ว — token อย่างเดียวรันจริง ป้ายต้องเป็น "ran" (เดิมคือ missing_review)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write("one\n")
        tok2 = C.token_from_hint(self.rpc(project, "local_do", {"action": "edit", "path": p, "old": "one",
                                                                "new": "three"}))
        # รอบ FIXER ของ mcp (S1/S2): token อย่างเดียวรันได้เฉพาะหลังการ์ดอนุญาตดึง review ไปแสดง (GET /review ที่มี Origin)
        # ก่อนนั้นเซิร์ฟเวอร์ปฏิเสธ ("ยังไม่ได้ทำอะไร: กล่อง ...") ป้ายต้องเป็น "refused" ไม่ใช่ "review" และไม่ใช่ "ran"
        texts["token_unviewed"] = self.rpc(project, "local_confirm", {"confirm_token": tok2})
        with open(p, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "one\n", texts["token_unviewed"][:160])
        self.assertEqual(self.server.review_lookup(project, "token=" + tok2, viewer=True)[0], 200)
        texts["token_only"] = self.rpc(project, "local_confirm", {"confirm_token": tok2})
        with open(p, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "three\n", texts["token_only"][:160])
        want = {"wrong_review": "review", "no_token": "refused", "unknown_token": "token",
                "wrong_surface": "refused", "ok": "ran", "reused": "token", "token_only": "ran",
                "token_unviewed": "refused"}
        got = dict(zip(texts, self.kinds(list(texts.values()))))
        for k, w in want.items():
            self.assertEqual(got[k], w, "%s: %s" % (k, texts[k][:160]))

    def test_webui_texts_and_spoofing(self):
        texts = [
            "Tool execution was denied by the user.",
            "Tool execution was interrupted by a new user message.",
            'Error: Tool "local_confirm" execution failed on server "local": fetch failed',
            "เครื่องมือ local_do ล้มเหลว: RuntimeError: x",
            "ผิดพลาด: kernel ไม่ตอบ",
            "ปฏิเสธ: โค้ดนี้อ้างถึงโฟลเดอร์ความลับของระบบ",
            "confirm_token ใช้ไม่ได้ (หมดอายุ ไม่ได้ยืนยันผ่าน local_confirm หรือโค้ดไม่ตรงกับที่อนุมัติ)",
            "kernel ของโปรเจกต์นี้กำลังรันโค้ดอื่นอยู่ ยังไม่ได้รันโค้ดนี้",
            # ผลของโค้ด/คำสั่งที่พิมพ์ข้อความปฏิเสธออกมา ต้องไม่ทำให้ป้ายโกหกว่า "ไม่ได้รัน"
            "ผลการรันโค้ด Python — โปรเจกต์ p\n```\nยังไม่ได้ทำอะไร: review ที่ส่งมาไม่ตรง\n```",
            "ยังไม่ได้ทำอะไร: review ที่ส่งมาไม่ตรงกับข้อความตรวจทานของ token นี้\n[stderr]\nx\n[exit code: 0]",
            "confirm_token นี้ใช้ไม่ได้\n[exit code: -1]\n",
            "  \n ยังไม่ได้ทำอะไร: review ที่ส่งมาไม่ตรง",
        ]
        self.assertEqual(self.kinds(texts),
                         ["denied", "interrupted", "failed", "failed", "failed", "refused", "token", "refused", "ran",
                          "ran", "ran", "review"])
        code = "var CONFIRM_TOOL = 'local_confirm'; function hasOwn(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }\n" + \
            self.cf + "\nconsole.log(JSON.stringify([confirmResultKind(null), confirmResultKind([{text: 'x'}]), confirmResultKind(5)]));"
        self.assertEqual(run_node(code), [None, None, None], "ไม่ใช่ข้อความ = ไม่ใส่ป้าย")

    def test_every_kind_has_a_label_and_thai(self):
        th = run_node(js_block(self.src, self.src.index("var TH = {")).replace("var TH =", "const TH =", 1) +
                      ";\nconsole.log(JSON.stringify(TH));")
        for en in NEW_LABELS:
            self.assertIn(en, th, en)
            self.assertRegex(th[en], "[\u0E00-\u0E7F]", en)
        labels = run_node("var CONFIRM_TOOL = 'local_confirm';\n" + self.cf + "\nconsole.log(JSON.stringify(CF_LABEL));")
        for kind in ("ran", "review", "token", "denied", "interrupted", "refused", "failed"):
            self.assertIn(labels[kind], NEW_LABELS, kind)
        self.assertEqual(th["Not run — the review text didn't match"].replace("\u2060", ""), "ไม่ได้รัน — review ไม่ตรง")

    def test_plan_matches_rows_to_calls_without_guessing(self):
        code = "var CONFIRM_TOOL = 'local_confirm'; function hasOwn(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }\n" + \
            self.cf + r"""
function call(id, name) { return {id: id, type: "function", function: {name: name, arguments: "{}"}}; }
var path = [
  {id: "r", role: "system"},
  {id: "u1", role: "user"},
  {id: "a1", role: "assistant", toolCalls: JSON.stringify([call("do1", "local_do"), call("cf1", "local_confirm")])},
  {id: "t1", role: "tool", toolCallId: "do1", content: "REVIEW ..."},
  {id: "t2", role: "tool", toolCallId: "cf1", content: "ยังไม่ได้ทำอะไร: review ที่ส่งมาไม่ตรง"},
  {id: "a1b", role: "assistant", content: "done", toolCalls: ""},
  {id: "u2", role: "user"},
  {id: "a2", role: "assistant", toolCalls: [call("cf2", "local_confirm")]},
  {id: "t3", role: "tool", toolCallId: "cf2", content: "แก้ไขแล้ว: a.txt"},
  {id: "a2b", role: "assistant", toolCalls: JSON.stringify([call("cf3", "local_confirm")])}
];
var out = {
  ok: cfPlan([{u: 1, names: ["local_do", "local_confirm"]}, {u: 2, names: ["Reasoning", "local_confirm", "local_confirm"]}], path),
  missingRow: cfPlan([{u: 1, names: ["local_confirm"]}], path),
  wrongOrder: cfPlan([{u: 1, names: ["local_confirm", "local_do"]}], path),
  noSeg: cfPlan([{u: 5, names: ["local_confirm"]}], path),
  extraDomRow: cfPlan([{u: 2, names: ["local_confirm", "local_confirm", "local_confirm"]}], path),
  empty: cfPlan([{u: 1, names: ["local_confirm"]}], []),
  junkCalls: cfPlan([{u: 1, names: ["local_confirm"]}], [{role: "user"}, {role: "assistant", toolCalls: "{bad"}])
};
console.log(JSON.stringify(out));
"""
        r = run_node(code)
        self.assertEqual(r["ok"], [[None, "review"], [None, "ran", None]], "ตัวที่ยังไม่มีผล = ยังไม่ใส่ป้าย")
        self.assertEqual(r["missingRow"], [[None]], "แถวใน DOM ไม่ครบ = ไม่เดา")
        self.assertEqual(r["wrongOrder"], [[None, None]])
        self.assertEqual(r["noSeg"], [[None]])
        self.assertEqual(r["extraDomRow"], [["ran", None, None]])
        self.assertEqual(r["empty"], [[None]])
        self.assertEqual(r["junkCalls"], [[None]])

    def test_path_read_only_from_indexeddb(self):
        code = r"""
var log = {closed: 0, aborted: 0, modes: [], index: []};
function later(f) { setTimeout(f, 1); }
function req(v) { var r = {}; later(function () { r.result = v; r.onsuccess && r.onsuccess(); }); return r; }
function makeDb(stores) {
  return {
    objectStoreNames: {contains: function (n) { return Object.prototype.hasOwnProperty.call(stores, n); }},
    close: function () { log.closed++; },
    transaction: function (names, mode) {
      log.modes.push(mode);
      return {objectStore: function (n) { return {
        indexNames: {contains: function (x) { return x === "convId"; }},
        get: function (id) { return req(stores[n][id]); },
        index: function (x) { log.index.push(x); return {getAll: function (cid) {
          return req(Object.keys(stores[n]).map(function (k) { return stores[n][k]; }).filter(function (m) { return m.convId === cid; })); }}; }
      }; }};
    }
  };
}
function fakeIdb(db) {
  return {open: function (name, ver) {
    log.name = name; log.ver = ver;
    var q = {};
    later(function () {
      if (!db) {
        q.result = makeDb({});
        q.transaction = {abort: function () { log.aborted++; later(function () { q.onerror && q.onerror(); }); }};
        q.onupgradeneeded && q.onupgradeneeded();
        return;
      }
      q.result = db; q.onsuccess && q.onsuccess();
    });
    return q;
  }};
}
var msgs = {r: {id: "r", convId: "c1", role: "system", parent: null}, u: {id: "u", convId: "c1", role: "user", parent: "r"},
  a: {id: "a", convId: "c1", role: "assistant", parent: "u"}, other: {id: "other", convId: "c1", role: "assistant", parent: "u"},
  t: {id: "t", convId: "c1", role: "tool", parent: "a"}, loop: {id: "loop", convId: "c2", role: "tool", parent: "loop"}};
var stores = {conversations: {c1: {id: "c1", currNode: "t"}, c2: {id: "c2", currNode: "loop"}, c3: {id: "c3"}}, messages: msgs};
var window = {}, indexedDB, CONFIRM_TOOL = "local_confirm";
function hasOwn(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
""" + self.cf + r"""
(async function () {
  var out = {};
  window.indexedDB = indexedDB = fakeIdb(makeDb(stores));
  out.path = (await cfPathFromDb("c1")).map(function (m) { return m.id; });
  out.loop = (await cfPathFromDb("c2")).map(function (m) { return m.id; });
  out.noHead = await cfPathFromDb("c3");
  out.missing = await cfPathFromDb("nope");
  out.noId = await cfPathFromDb(null);
  window.indexedDB = indexedDB = fakeIdb(null);
  out.noDb = await cfPathFromDb("c1");
  out.log = log;
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""
        r = run_node(code)
        self.assertEqual(r["path"], ["r", "u", "a", "t"], "เฉพาะสายที่แสดงอยู่ (ไม่รวมกิ่ง 'other')")
        self.assertEqual(r["loop"], ["loop"])
        for k in ("noHead", "missing", "noId", "noDb"):
            self.assertIsNone(r[k], k)
        lg = r["log"]
        self.assertEqual(lg["name"], "LlamaUi")
        self.assertIsNone(lg.get("ver"))
        self.assertEqual(set(lg["modes"]), {"readonly"})
        self.assertEqual(lg["aborted"], 1, "ไม่มีฐานข้อมูล = ยกเลิก ไม่สร้างฐานว่าง")
        self.assertEqual(lg["closed"], 4, "ปิดการเชื่อมต่อทุกครั้งที่เปิดสำเร็จ (c1, c2, c3, nope)")
        self.assertEqual(lg["index"], ["convId", "convId"], "อ่านทั้งแชตด้วยดัชนี convId ครั้งเดียวต่อรอบ")
        for bad in ('"readwrite"', "deleteDatabase", "createObjectStore", ".put(", ".delete(", ".clear("):
            self.assertNotIn(bad, self.cf, bad)

    def test_long_wait_before_allow_does_not_delay_the_badge(self):
        """ระหว่างรอคนกด WebUI ขยับ DOM ถี่ๆ → อ่าน DB ซ้ำพร้อมยืดระยะ (ถึง 30 วิ) แต่พอคนกด (การ์ดหาย) ต้องอ่านทันที"""
        code = "var CONFIRM_TOOL = 'local_confirm', PROMPT_SEL = 'CARDS';\n" \
            "function hasOwn(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }\n" + self.cf + r"""
var T = 1000000, cards = 1, turns = 1, streaming = true, reads = 0, timers = 0;
Date.now = function () { return T; };
setTimeout = function () { timers++; return timers; };
function route() { return {name: "chat", id: "c1"}; }
function isStreaming() { return streaming; }
var holder = {querySelector: function () { return null; }};
var span = {textContent: " local_confirm ", parentNode: holder, closest: function () { return null; }};
var document = {
  querySelectorAll: function (s) { return s === CF_TITLE_SEL ? [span] : s === PROMPT_SEL ? new Array(cards) : []; },
  getElementsByClassName: function () { return {length: turns}; }
};
cfPathFromDb = function () { reads++; return Promise.resolve([]); };
cfGroups = function () { return [{u: 1, rows: [{name: "local_confirm", holder: holder}], names: ["local_confirm"]}]; };
cfPlan = function () { return [[null]]; };           // ผลยังไม่ถูกบันทึก
function flush() { return new Promise(function (r) { setImmediate(r); }); }
(async function () {
  var log = [];
  cfBadgeScan(); await flush(); log.push(reads);                 // อ่านครั้งแรก
  T += 1300; cfBadgeScan(); await flush(); log.push(reads);      // ยืดระยะ 2.4 วิ
  T += 2500; cfBadgeScan(); await flush(); log.push(reads);      // 4.8
  T += 5000; cfBadgeScan(); await flush(); log.push(reads);      // 9.6
  T += 1000; cfBadgeScan(); await flush(); log.push(reads);      // ยังไม่ถึงเวลา = ไม่อ่าน
  cards = 0; T += 100; cfBadgeScan(); await flush(); log.push(reads);   // คนกดอนุญาต: การ์ดหาย → อ่านทันที
  T += 100; cfBadgeScan(); await flush(); log.push(reads);       // ไม่มีอะไรเปลี่ยน = ไม่อ่านซ้ำถี่
  turns = 2; T += 100; cfBadgeScan(); await flush(); log.push(reads);   // รอบเอเจนต์ใหม่ (ผลเพิ่งบันทึก) → อ่านทันที
  console.log(JSON.stringify({log: log, delay: cf.delay}));
})();
"""
        r = run_node(code)
        self.assertEqual(r["log"], [1, 2, 3, 4, 4, 5, 5, 6])

    def test_wired_into_scan_and_badge_is_text_only(self):
        sp = js_block(self.src, self.src.index("\n  function scanPrompts(") + 1)
        self.assertIn("cfBadgeScan()", sp)
        bs = js_block(self.cf, self.cf.index("function cfBadgeSet("))
        self.assertIn("b.textContent = CF_LABEL[kind]", bs)
        self.assertNotIn("innerHTML", self.cf)


class ThemeTests(unittest.TestCase):
    def test_new_css(self):
        css = read(CSS)
        a = css.index("รอบ 5 แก้หลังรีวิว (enhance.js: ALLOW-GUARD ฝั่ง UI)")
        sec = css[a:css.index("@media (max-width: 640px)", a)]
        hid = sec[sec.index('[role="menuitem"].qw-allow-hidden {'):]
        self.assertIn("display: none !important", hid[:hid.index("}")])
        lock = sec[sec.index(".qw-allow-locked > :is("):]
        lock = lock[:lock.index("}")]
        self.assertIn("pointer-events: none", lock)
        self.assertIn('[role="checkbox"]', sec[sec.index(".qw-allow-locked > :is("):][:80])
        for sel in (".qw-cf-status {", '.qw-cf-status[data-tone="ok"]', '.qw-cf-status[data-tone="notrun"]',
                    '.qw-cf-status[data-tone="failed"]'):
            self.assertIn(sel, sec, sel)
        import re
        self.assertNotRegex(sec, r"#[0-9a-fA-F]{3,8}\b", "ใช้ token ไม่ใช่สีตายตัว")
        self.assertNotRegex(sec, r"rgba?\(", "ใช้ token ไม่ใช่สีตายตัว")
        # กฎเดิมของการ์ด local_confirm ต้องยังอยู่
        self.assertIn('.qw-confirm-card button[aria-label="More allow options"]', css)


# =========================================================================== ส่วนที่ 2: E2E (opt-in)
E2E = os.environ.get("QWEN_UI_E2E") == "1"
TOOL_DEFS = [
    {"name": "local_read", "description": "test stub", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "local_do", "description": "test stub",
     "inputSchema": {"type": "object", "properties": {"action": {"type": "string"}, "code": {"type": "string"}}}},
    {"name": "local_confirm", "description": "test stub",
     "inputSchema": {"type": "object", "required": ["confirm_token", "review"],
                     "properties": {"confirm_token": {"type": "string"}, "review": {"type": "string"}}}},
]
MODEL_FAIL = ("/v1/chat/completions/control", "/tokenize", "/detokenize", "/apply-template", "/infill", "/completion",
              "/completions", "/v1/completions", "/embedding", "/embeddings", "/v1/embeddings", "/rerank", "/v1/rerank",
              "/models/unload", "/slots", "/v1/stream", "/v1/streams/lookup", "/metrics", "/lora-adapters")
E2E_PROPS = {
    "default_generation_settings": {"params": json.loads(
        '{"seed":4294967295,"temperature":1.0,"dynatemp_range":0.0,"dynatemp_exponent":1.0,"top_k":20,"top_p":0.95,'
        '"min_p":0.05,"top_n_sigma":-1.0,"xtc_probability":0.0,"xtc_threshold":0.1,"typical_p":1.0,"repeat_last_n":64,'
        '"repeat_penalty":1.0,"presence_penalty":0.0,"frequency_penalty":0.0,"dry_multiplier":0.0,"dry_base":1.75,'
        '"dry_allowed_length":2,"dry_penalty_last_n":64,"mirostat":0,"mirostat_tau":5.0,"mirostat_eta":0.1,'
        '"adaptive_target":-1.0,"adaptive_decay":0.9,"max_tokens":-1,"n_predict":-1,"n_keep":0,"n_discard":0,'
        '"ignore_eos":false,"stream":false,"n_probs":0,"min_keep":0,"chat_format":"Content-only","reasoning_format":"none",'
        '"reasoning_in_content":false,"generation_prompt":"","samplers":["penalties","dry","top_n_sigma","top_k","typ_p",'
        '"top_p","min_p","xtc","temperature"],"speculative.types":"none","timings_per_token":false,'
        '"post_sampling_probs":false,"backend_sampling":false,"lora":[]}'), "n_ctx": 32768},
    "total_slots": 4, "model_alias": "Qwen3-4B-Instruct-2507-Q4_K_M", "model_ftype": "Q4_K - Medium",
    "modalities": {"vision": False, "video": False, "audio": False}, "endpoint_slots": True, "endpoint_props": False,
    "endpoint_metrics": False, "ui": True, "bos_token": "<|endoftext|>", "eos_token": "<|im_end|>",
    "chat_template_caps": {"supports_object_arguments": True, "supports_parallel_tool_calls": True,
                           "supports_preserve_reasoning": True, "supports_reasoning_effort": True,
                           "supports_string_content": True, "supports_system_role": True, "supports_tool_calls": True,
                           "supports_tools": True, "supports_typed_content": True},
    "build_info": "b10984-test", "is_sleeping": False, "cors_proxy_enabled": False,
}
E2E_ROUTER_PROPS = {"role": "router", "default_generation_settings": {"params": None, "n_ctx": 0}, "max_instances": 2,
                    "models_autoload": False, "model_alias": "llama-server", "build_info": "b10984-test",
                    "cors_proxy_enabled": False}
# ทุกตัว "loaded" = WebUI ไม่มีวันสั่ง router โหลดโมเดล
E2E_MODELS = {"object": "list", "data": [
    {"id": m, "aliases": [], "tags": [], "object": "model", "owned_by": "llamacpp", "created": 0,
     "status": {"value": "loaded", "args": [], "preset": ""}}
    for m in ("Qwen3-4B-Instruct-2507-Q4_K_M", "Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL", "Qwen3.8-27B-UD-Q4_K_M",
              "gpt-oss-20b-MXFP4")]}
REVIEW = "[python] run\n1│ print(1+1)"
ALLOW_BTN = ".qw-confirm-card button[data-slot=button]:not(.bg-destructive)"
STATE_JS = r"""(()=>({cards:[...document.querySelectorAll('.chat-messages div.rounded-lg.border.bg-card.p-3')].map(c=>[c.classList.contains('qw-confirm-card'), c.textContent.replace(/\s+/g,' ').slice(0,60)]),
  allow: localStorage.getItem('LlamaUi.alwaysAllowedTools'), guard: qwenEnhance.allowGuard ? qwenEnhance.allowGuard() : {},
  streaming: qwenEnhance.isStreaming()}))()"""
BADGES_JS = r"""(()=>[...document.querySelectorAll('.chat-messages [data-slot=collapsible] > button[data-slot=collapsible-trigger]')].map(t=>{const h=t.firstElementChild;const b=h&&h.querySelector(':scope > .qw-cf-status');return [h&&(h.querySelector(':scope > span.font-medium')||{}).textContent, b&&b.getAttribute('data-kind')]}))()"""
# ผู้สังเกตที่สร้างทีหลัง observer ของ enhance จึงถูกเรียกหลังมันในไมโครทาสก์เดียวกัน: เห็นสถานะ "ตอนการ์ดโผล่" จริง
WATCH_JS = r"""(()=>{window.__cardSeen=[];new MutationObserver(rs=>{for(const r of rs)for(const n of r.addedNodes){if(n.nodeType!==1)continue;
  const cs=n.matches('div.rounded-lg.border.bg-card.p-3')?[n]:[...n.querySelectorAll('div.rounded-lg.border.bg-card.p-3')];
  for(const c of cs){const a=c.querySelector('button[aria-label="More allow options"]');
  window.__cardSeen.push([c.textContent.includes('local_confirm'), c.classList.contains('qw-confirm-card'), !!c.querySelector('.qw-review'), a?getComputedStyle(a).display:'none'])}}})
  .observe(document.body,{childList:true,subtree:true});return 1})()"""


@unittest.skipUnless(E2E, "E2E ปิดไว้ (set QWEN_UI_E2E=1)")
class BrowserE2E(unittest.TestCase):
    """เปิด Edge headless ผ่าน hub สำเนา — ทุกคำขอหาโมเดล/MCP/hub API ถูกดักและตอบด้วยข้อมูลจำลอง"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, TOOLS)
        import shot
        cls.shot = shot
        sys.path.insert(0, os.path.dirname(HUB))
        spec = importlib.util.spec_from_file_location("hub_allow_guard_e2e", HUB)
        hub = importlib.util.module_from_spec(spec)
        tmp = tempfile.gettempdir()
        with mock.patch.object(sys, "argv", ["hub.py"]), \
                mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                             "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
            spec.loader.exec_module(hub)
        if STATIC_DIR:
            from pathlib import Path
            hub.STATIC_DIR = Path(STATIC_DIR)
        cls.port = None
        from http.server import ThreadingHTTPServer

        class Srv(ThreadingHTTPServer):
            # Windows: SO_REUSEADDR (ค่าเริ่มต้นของ HTTPServer) ให้ bind ทับพอร์ตที่โปรเซสอื่นฟังอยู่ได้ — คำขอจะไปตกที่
            # เซิร์ฟเวอร์อื่น (เช่น hub สำเนาของคนอื่นที่เสิร์ฟไฟล์คนละชุด) แล้วเทสต์ผ่าน/พังผิดสาเหตุ
            allow_reuse_address = False
            daemon_threads = True

        for port in range(8178, 8186):
            try:
                socket.create_connection(("127.0.0.1", port), 0.3).close()
                continue                                   # มีคนฟังอยู่แล้ว
            except OSError:
                pass
            try:
                projects = (lambda p: (lambda: [dict(x, port=p) for x in hub.load_projects() if x["slug"] == "project1"]))(port)
                srv = Srv(("127.0.0.1", port), hub.make_proxy_handler("project1", projects))
            except OSError:
                continue
            cls.port, cls.srv = port, srv
            break
        if not cls.port:
            raise unittest.SkipTest("ไม่มีพอร์ตว่างใน 8178-8185")
        cls.srv.daemon_threads = True
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "srv", None):
            cls.srv.shutdown()
            cls.srv.server_close()

    # ---- ตัวขับเบราว์เซอร์ (ย่อจากเครื่องมือทดสอบของรอบ R4) ----
    def drive(self, steps, script=(), mcp=(), lang="en"):
        shot = self.shot
        origin = "http://127.0.0.1:%d" % self.port
        script, mcp = list(script), list(mcp)
        calls, results = [], []

        def b64(s):
            return base64.b64encode(s.encode("utf-8") if isinstance(s, str) else s).decode()

        def sse(item):
            base = {"id": "t", "object": "chat.completion.chunk", "created": int(time.time()),
                    "model": "Qwen3-4B-Instruct-2507-Q4_K_M"}
            if "tool" in item:
                raw = json.dumps(item["args"], ensure_ascii=False)
                ch = [dict(base, choices=[{"index": 0, "delta": {"role": "assistant", "content": None, "tool_calls": [
                    {"index": 0, "id": item["id"], "type": "function",
                     "function": {"name": item["tool"], "arguments": raw}}]}, "finish_reason": None}]),
                      dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": "tool_calls"}])]
            else:
                ch = [dict(base, choices=[{"index": 0, "delta": {"role": "assistant", "content": item["text"]},
                                           "finish_reason": None}]),
                      dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}])]
            return "".join("data: %s\n\n" % json.dumps(c, ensure_ascii=False) for c in ch) + "data: [DONE]\n\n"

        class D(shot.WS):
            def send_nowait(self, method, params):
                self.next_id += 1
                self.send(json.dumps({"id": self.next_id, "method": method, "params": params}))

            def fulfill(self, rid, status, body, ctype="application/json", extra=None):
                h = [{"name": "Content-Type", "value": ctype}, {"name": "Cache-Control", "value": "no-store"}]
                h += [{"name": k, "value": v} for k, v in (extra or {}).items()]
                self.send_nowait("Fetch.fulfillRequest", {"requestId": rid, "responseCode": status,
                                                          "responseHeaders": h, "body": b64(body or "")})

            def handle(self, p):
                rid, req = p["requestId"], p["request"]
                u = urlparse(req["url"])
                method, path = req["method"], u.path
                if u.netloc in ("127.0.0.1:8791", "127.0.0.1:8792"):
                    org = (req.get("headers") or {}).get("Origin") or origin
                    cors = {"Access-Control-Allow-Origin": org, "Access-Control-Expose-Headers": "Mcp-Session-Id",
                            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
                            "Access-Control-Allow-Headers": "authorization, content-type, mcp-session-id, "
                                                            "mcp-protocol-version, accept, last-event-id"}
                    if method == "OPTIONS":
                        return self.fulfill(rid, 204, "", "text/plain", cors)
                    if method != "POST":
                        return self.fulfill(rid, 405, "", "text/plain", cors)
                    msg = json.loads(req.get("postData") or "{}")
                    m, mid = msg.get("method"), msg.get("id")
                    local = u.netloc.endswith(":8792")
                    name = ("qwen38-local-fast" if path.startswith("/fast/") else "qwen38-local") if local else "websearch"
                    if m == "initialize":
                        res = {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2025-06-18"),
                               "capabilities": {"tools": {}}, "serverInfo": {"name": name, "version": "test"}}
                        return self.fulfill(rid, 200, json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}),
                                            extra=dict(cors, **{"Mcp-Session-Id": "test"}))
                    if mid is None:
                        return self.fulfill(rid, 202, "", "text/plain", cors)
                    if m == "tools/list":
                        res = {"tools": TOOL_DEFS if local else []}
                    elif m == "tools/call":
                        calls.append(msg.get("params") or {})
                        it = mcp.pop(0) if mcp else {}
                        res = {"content": [{"type": "text", "text": it.get("text", "blocked by test")}],
                               "isError": bool(it.get("isError"))}
                    else:
                        res = {}
                    return self.fulfill(rid, 200, json.dumps({"jsonrpc": "2.0", "id": mid, "result": res},
                                                             ensure_ascii=False), extra=cors)
                if u.netloc == "127.0.0.1:8100":
                    if method in ("GET", "OPTIONS"):
                        return self.send_nowait("Fetch.continueRequest", {"requestId": rid})
                    return self.send_nowait("Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"})
                if path == "/v1/chat/completions" and method == "POST":
                    if not script:
                        return self.send_nowait("Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"})
                    return self.fulfill(rid, 200, sse(script.pop(0)), "text/event-stream")
                # API ของ llama-server ตอบเองทั้งหมด: ห้ามถาม router ด้วยชื่อโมเดล (router โหลดโมเดลให้เอง) และ hub สำเนา
                # ใช้โทเคนทดสอบ (test_security_common) ซึ่ง llama-server ตัวจริงไม่รับ — ไฟล์หน้าเว็บ (/_app/*) ยังผ่านได้
                if path in ("/v1/models", "/models"):
                    return self.fulfill(rid, 200, json.dumps(E2E_MODELS))
                if path == "/props":
                    q = parse_qs(u.query)
                    return self.fulfill(rid, 200, json.dumps(E2E_PROPS if "model" in q else E2E_ROUTER_PROPS))
                if path == "/tools":
                    return self.send_nowait("Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"})
                if path == "/models/load":
                    return self.fulfill(rid, 200, json.dumps({"success": True}))
                if path == "/models/sse":
                    return self.fulfill(rid, 200, ": test\n\n", "text/event-stream")
                if path in MODEL_FAIL or path.startswith("/v1/chat/") or (
                        method not in ("GET", "HEAD", "OPTIONS") and not path.startswith("/_qwen/")):
                    return self.send_nowait("Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"})
                return self.send_nowait("Fetch.continueRequest", {"requestId": rid})

            def recv(self):
                while True:
                    raw = super().recv()
                    try:
                        msg = json.loads(raw)
                    except ValueError:
                        return raw
                    if msg.get("method") == "Fetch.requestPaused":
                        try:
                            self.handle(msg["params"])
                        except Exception:  # noqa: BLE001
                            self.send_nowait("Fetch.failRequest", {"requestId": msg["params"]["requestId"],
                                                                   "errorReason": "Failed"})
                        continue
                    return raw

        edge = next(p for p in shot.EDGE_CANDIDATES if os.path.isfile(p))
        dport = shot.free_port()
        profile = tempfile.mkdtemp(prefix="qwen-shot-")
        proc = subprocess.Popen([edge, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                                 "--disable-extensions", "--mute-audio", "--remote-debugging-port=%d" % dport,
                                 "--user-data-dir=%s" % profile, "--window-size=1440,900", "about:blank"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        out, ws = [], None
        try:
            ws_url = None
            for _ in range(100):
                try:
                    tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % dport, timeout=2).read())
                    page = next((t for t in tabs if t.get("type") == "page"), None)
                    if page:
                        ws_url = page["webSocketDebuggerUrl"]
                        break
                except OSError:
                    pass
                time.sleep(0.15)
            ws = D(ws_url)
            ws.call("Page.enable")
            ws.call("Runtime.enable")
            ws.call("Fetch.enable", {"patterns": [{"urlPattern": origin + "/*"}, {"urlPattern": "http://127.0.0.1:8100/*"},
                                                  {"urlPattern": "http://127.0.0.1:8791/*"},
                                                  {"urlPattern": "http://127.0.0.1:8792/*"}]})
            ws.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1,
                                                            "mobile": False})
            shot.navigate(ws, origin + "/?lang=%s" % lang, settle=4.0)
            for st in steps:
                if "wait" in st:
                    ws.drain(st["wait"] / 1000.0)
                elif "frame" in st:
                    js = ("(async()=>{const w=document.getElementById('frame').contentWindow;return await w.eval(%s)})()"
                          % json.dumps(st["frame"]))
                    out.append(shot.evaluate(ws, js))
                elif "click" in st:
                    js = ("(()=>{const f=document.getElementById('frame');const e=f.contentDocument.querySelector(%s);"
                          "if(!e) return null;const r=e.getBoundingClientRect(),o=f.getBoundingClientRect();"
                          "return [o.left+r.left+r.width/2,o.top+r.top+r.height/2]})()" % json.dumps(st["click"]))
                    xy = shot.evaluate(ws, js)
                    out.append(bool(xy))
                    if xy:
                        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
                            ws.call("Input.dispatchMouseEvent", {"type": t, "x": xy[0], "y": xy[1], "button": "left",
                                                                 "clickCount": 1})
        finally:
            try:
                if ws is not None:
                    ws.sock.close()
            except OSError:
                pass
            shot.close_edge(proc, profile)
        return out, calls

    def submit(self):
        return [{"wait": 2500}, {"frame": WATCH_JS}, {"frame": "qwenEnhance.prefill('go'); 1"}, {"wait": 300},
                {"click": ".chat-screen-form-wrapper form button[type=submit]"}, {"wait": 3500}]

    def test_1_always_server_hidden_and_backstop_keeps_the_card(self):
        menu = r"""(()=>[...document.querySelectorAll('[role=menuitem]')].map(i=>[i.textContent.replace(/\s+/g,' ').trim(), getComputedStyle(i).display]))()"""
        force = r"""(()=>{const t=[...document.querySelectorAll('[role=menuitem]')].find(i=>/all tools from/.test(i.textContent));
          t.classList.remove('qw-allow-hidden');['data-disabled','aria-hidden','aria-disabled'].forEach(a=>t.removeAttribute(a));t.id='qwtarget';return 1})()"""
        steps = self.submit() + [
            {"click": "button[aria-label='More allow options']"}, {"wait": 700}, {"frame": menu},
            # จำลองว่าชั้น UI พลาด: เอารายการกลับมาแล้วกดจริง — ด่านหลักต้องยังทำให้ local_confirm ขึ้นการ์ด
            {"frame": force}, {"wait": 100}, {"click": "#qwtarget"}, {"wait": 4000}, {"frame": STATE_JS},
            {"frame": "window.__cardSeen"},
            {"click": ALLOW_BTN}, {"wait": 3500}, {"frame": STATE_JS}]
        script = [{"tool": "local_do", "id": "c_do", "args": {"action": "python", "code": "print(1+1)"}},
                  {"tool": "local_confirm", "id": "c_cf", "args": {"confirm_token": "3fa1c29e", "review": REVIEW}},
                  {"text": "done"}]
        mcp = [{"text": "REVIEW ... confirm_token=3fa1c29e"}, {"text": "ผลการรันโค้ด Python — โปรเจกต์ project1\n2"}]
        out, calls = self.drive(steps, script, mcp)
        # out = ผลของทุกขั้น frame/click ตามลำดับ: 0 WATCH, 1 prefill, 2 ส่ง, 3 ลูกศร, 4 เมนู, 5 force, 6 กด, 7 STATE,
        #       8 __cardSeen, 9 อนุญาต, 10 STATE
        items = dict(out[4])
        self.assertEqual(items.get("Always allow local_do tool"), "flex")
        self.assertEqual(items.get("Always allow all tools from qwen38-local-fast"), "none")
        st = out[7]
        self.assertEqual(len(st["cards"]), 1, st)
        self.assertTrue(st["cards"][0][0], "การ์ด local_confirm ต้องขึ้น (และมี class ของเรา)")
        self.assertNotIn("local_confirm", st["allow"])
        self.assertEqual(st["guard"]["deleted"], 1)
        self.assertEqual([c["name"] for c in calls], ["local_do", "local_confirm"])
        seen = out[8]
        confirm = [s for s in seen if s[0]]
        self.assertTrue(confirm, seen)
        for s in confirm:
            self.assertEqual(s[1:], [True, True, "none"], "ตอนการ์ดโผล่ต้องมี class + กล่อง + ไม่มีปุ่มลูกศรแล้ว")
        self.assertEqual(out[-1]["cards"], [])

    def test_2_result_badges(self):
        wrong = REVIEW + "x"
        steps = self.submit() + [{"click": ALLOW_BTN}, {"wait": 3000}, {"click": ALLOW_BTN}, {"wait": 3000},
                                 {"click": ".qw-confirm-card button.bg-destructive"}, {"wait": 4500},
                                 {"frame": BADGES_JS}]
        script = [{"tool": "local_confirm", "id": "cA", "args": {"confirm_token": "aaaa1111", "review": wrong}},
                  {"tool": "local_confirm", "id": "cB", "args": {"confirm_token": "bbbb2222", "review": REVIEW}},
                  {"tool": "local_confirm", "id": "cC", "args": {"confirm_token": "cccc3333", "review": REVIEW}},
                  {"text": "ผมรันให้แล้วครับ"}]
        mcp = [{"text": "ยังไม่ได้ทำอะไร: review ที่ส่งมาไม่ตรงกับข้อความตรวจทานของ token นี้ (token ยังใช้ได้)", "isError": True},
               {"text": "ผลการรันโค้ด Python — โปรเจกต์ project1\n```\nยังไม่ได้ทำอะไร: fake\n```"}]
        out, calls = self.drive(steps, script, mcp)
        self.assertEqual(out[-1], [["local_confirm", "review"], ["local_confirm", "ran"], ["local_confirm", "denied"]])
        self.assertEqual(len(calls), 2, "กดปฏิเสธ = ไม่มีการเรียก MCP")


if __name__ == "__main__":
    unittest.main()
