# -*- coding: utf-8 -*-
"""
เทสต์ของ webui-enhance.js / webui-theme.css รอบ 4 (สัญญา K5-K9, เจ้าของ: enhance)

ส่วนที่ 1 — รันเสมอ ไม่ต้องเปิดเบราว์เซอร์หรือ hub:
  * ไวยากรณ์ของ webui-enhance.js (node --check)
  * ป้ายใหม่ทุกคำมีคำแปลไทยในพจนานุกรม TH (ป้ายเขียนเป็นอังกฤษลง DOM แล้วให้ตัวแปลแปล — ขาดคำเดียว = โหมดไทยมีอังกฤษโผล่)
  * ฟังก์ชันล้วน (จับคู่ชื่อโมเดลจากป้าย, แบ่งชิ้นเสียงอ่านไทย/อังกฤษ, ชื่อ artifact) รันจริงใน Node จากซอร์สในไฟล์
  * CSS มีตัวเลือกของชิ้นใหม่ครบ และใช้ token ไม่ใช้สีตายตัว
  * ความเป็นส่วนตัว/แบรนด์: ส่วนใหม่ไม่เรียกเครือข่าย ใช้เสียงอ่านในเครื่องเท่านั้น ไม่มีคำว่า Claude/Anthropic

ส่วนที่ 2 — E2E (ปิดไว้เป็นค่าเริ่มต้น เพราะเปิด Edge headless + hub สำเนาบนพอร์ตสำรอง ~1 นาที):
  set QWEN_UI_E2E=1  แล้วรัน  C:\\Python313\\python.exe -m unittest C:\\LLM\\tests\\test_enhance_round4.py -v
  import hub.py เป็นโมดูล (ไม่แตะ hub ตัวจริงบน 8100) เปิด proxy ของ project1 บนพอร์ตว่างตัวแรกใน 8174-8177
  ใช้โปรไฟล์ Edge ชั่วคราว (IndexedDB/localStorage ว่าง) ไม่ส่งข้อความหาโมเดล และไม่สลับไปโมเดลที่ router ยังไม่โหลด
  (การเลือกโมเดลที่ยังไม่โหลดใน WebUI = สั่งโหลดจริง) — สลับได้แค่ไปหา 4B เมื่อ 4B โหลดอยู่แล้วเท่านั้น
  ตัวกันที่ proxy สำเนา: POST .../models/load และคำขอแชต/completion ทุกชนิดได้ 403 (จดไว้ใน BLOCKED) — เทสต์ชิปที่สลับ
  โมเดลไปมาจึงไม่มีทางสั่งโหลดโมเดลจริงหรือส่งข้อความหาโมเดล

รอบแก้หลังรีวิว UX (2026-09-30): เนื้อความแจ้งเตือนจาก IndexedDB (อ่านอย่างเดียว), ถามก่อนโหลดโมเดลใหญ่ตอนปิดโหมดเร็ว,
ชิปอยู่ฝั่งซ้ายถัดจาก "+" (ไม่ขยับ), แผงตามรุ่นใหม่ของชิ้นที่เปิดอยู่, ฟอนต์โค้ดไม่รวมตัวอักษร (ligature)
ชี้ไปไฟล์สำเนาได้ (ทดสอบก่อนติดตั้ง): QWEN_ENH_FILE, QWEN_THEME_FILE, QWEN_STATIC_DIR (E2E)
"""
import importlib.util
import json
import os
import re
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

ENH = os.environ.get("QWEN_ENH_FILE") or r"C:\LLM\projects\static\webui-enhance.js"
CSS = os.environ.get("QWEN_THEME_FILE") or r"C:\LLM\projects\static\webui-theme.css"
STATIC_DIR = os.environ.get("QWEN_STATIC_DIR") or ""
HUB = r"C:\LLM\projects\hub.py"
TOOLS = r"C:\LLM\projects\tools"
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
HAVE_NODE = os.path.isfile(NODE) if os.path.isabs(NODE) else bool(shutil.which("node"))
FAST_MODEL = "Qwen3-4B-Instruct-2507-Q4_K_M"
MODEL_IDS = ["Qwen3-4B-Instruct-2507-Q4_K_M", "Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL",
             "Qwen3.8-27B-UD-Q4_K_M", "gpt-oss-20b-MXFP4"]

# ป้ายที่ส่วนใหม่เขียนลง DOM หรือส่งผ่าน tx() — ทุกคำต้องมีคำแปลไทย
LABELS = [
    "Fast (4B)",
    "Fast mode: answer with Qwen3-4B, much faster but less thorough. Click again to go back to the project model "
    "(if it isn't loaded yet, it loads first: large and slow).",
    "Click again to load the project model and switch back.",
    "{model} isn't loaded yet. Click again to load it and switch back (large model, slow to load).",
    "Open the chat to read the reply.",
    "Couldn't switch the model. Choose it from the model menu instead.",
    "Open in panel", "Read aloud", "Pause reading", "Resume reading", "Stop reading", "Ask about this",
    "HTML page", "SVG image", "Mermaid diagram", "Markdown document", "CSV table", "Chart image",
    "Reply finished", "Tool permission needed", "Agentic turn limit reached", "Press Continue to keep going, or Stop.",
    "Allow use of",
]
MODULE_START = "รอบ 4 (2026-09-30) — สัญญา K5-K9"
MODULE_END = "/* ---- API ----"


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def js_block(src, start):
    """ซอร์สของบล็อก {...} ตัวแรกหลังตำแหน่ง start (นับวงเล็บ ข้ามสตริง/คอมเมนต์)"""
    i = src.index("{", start)
    depth, q, n = 0, None, len(src)
    j = i
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


def js_function(src, name):
    m = re.search(r"\n  function %s\(" % re.escape(name), src)
    if not m:
        raise AssertionError("function %s not found in webui-enhance.js" % name)
    return js_block(src, m.start() + 1)


def run_node(code):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(code)
        path = fh.name
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True, encoding="utf-8", timeout=60)
    finally:
        os.remove(path)
    if r.returncode != 0:
        raise AssertionError("node failed: %s" % r.stderr[-2000:])
    return json.loads(r.stdout)


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(ENH)
        cls.css = read(CSS)
        a = cls.src.index(MODULE_START)
        cls.module = cls.src[a:cls.src.index(MODULE_END, a)]

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_syntax(self):
        r = subprocess.run([NODE, "--check", ENH], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_every_new_label_has_thai(self):
        th = run_node(js_block(self.src, self.src.index("var TH = {")).replace("var TH =", "const TH =", 1) +
                      ";\nconsole.log(JSON.stringify(TH));")
        for en in LABELS:
            self.assertIn(en, th, "ไม่มีคำแปลไทยของ %r" % en)
            self.assertRegex(th[en], "[\u0E00-\u0E7F]", "คำแปลของ %r ไม่ใช่ภาษาไทย" % en)
        # ป้ายที่ใช้จริงในโค้ดต้องอยู่ในรายการ (กันเพิ่มป้ายใหม่แล้วลืมแปล)
        for lit in re.findall(r'(?:xButton\([^,]+,|setXLabel\([^,]+,|textContent = |tx\()\s*"([^"]+)"', self.module):
            self.assertIn(lit, th, "ป้าย %r ในโค้ดไม่มีคำแปลไทย" % lit)

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_pure_helpers(self):
        fns = "\n".join(js_function(self.src, n) for n in ("alnum", "modelFromParts", "speakChunks", "artTitle", "clip"))
        code = ("var THAI_CH = /[\\u0E00-\\u0E7F]/;\n" + fns + "\nvar ids = %s;\n" % json.dumps(MODEL_IDS) + r"""
var out = {
  b4: modelFromParts(["Qwen3", "4B"], ids),
  opt4: modelFromParts(["Qwen3", "4B", "Q4_K_M", "Instruct", "2507"], ids),
  b27: modelFromParts(["Qwen3.8", "27B"], ids),
  coder: modelFromParts(["Qwen3-Coder", "30B-A3B"], ids),
  oss: modelFromParts(["gpt-oss", "20B"], ids),
  none: modelFromParts([], ids),
  unknown: modelFromParts(["Llama", "8B"], ids),
  tie: modelFromParts(["ab"], ["ab-x", "ab-y"]),
  th: speakChunks("สรุปแบบสั้น: ตู้ที่หลุดบ่อยเกิดจาก Heartbeat ขาดช่วง ตรวจ BootNotification ล่าสุด"),
  en: speakChunks("Then check the WebSocket ping interval on the CSMS side as well."),
  mixed: speakChunks("ตรวจสายก่อน then check the WebSocket ping interval twice"),
  long: speakChunks(new Array(80).join("word ") + "end."),
  titleHtml: artTitle("html", "<html><head><title>Dash</title></head><body><h1>X</h1></body></html>"),
  titleH1: artTitle("html", "<body><h1>สถานะ <b>ตู้</b></h1></body>"),
  titleMd: artTitle("markdown", "intro\n## Weekly report\n- a"),
  titleSvg: artTitle("svg", "<svg><title>Plug</title></svg>"),
  titleNone: artTitle("csv", "a,b\n1,2"),
  clip: clip("  a   b  c ", 4)
};
console.log(JSON.stringify(out));
""")
        r = run_node(code)
        self.assertEqual(r["b4"], FAST_MODEL)
        self.assertEqual(r["opt4"], FAST_MODEL)
        self.assertEqual(r["b27"], "Qwen3.8-27B-UD-Q4_K_M")
        self.assertEqual(r["coder"], "Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL")
        self.assertEqual(r["oss"], "gpt-oss-20b-MXFP4")
        self.assertIsNone(r["none"])
        self.assertIsNone(r["unknown"])
        self.assertIsNone(r["tie"], "เสมอกัน = ไม่รู้ ต้องไม่เดา")
        # ย่อหน้าไทยที่มีคำอังกฤษสั้นๆ ปน = ชิ้นเดียว เสียงไทย
        self.assertEqual([c["lang"] for c in r["th"]], ["th-TH"])
        self.assertEqual([c["lang"] for c in r["en"]], ["en-US"])
        # ช่วงอังกฤษยาว (≥ 4 คำ) ในย่อหน้าไทยแยกเป็นเสียงอังกฤษ
        self.assertEqual([c["lang"] for c in r["mixed"]], ["th-TH", "en-US"])
        self.assertTrue(all(len(c["text"]) <= 200 for c in r["long"]) and len(r["long"]) >= 2)
        self.assertEqual(r["titleHtml"], "Dash")
        self.assertEqual(r["titleH1"], "สถานะ ตู้")
        self.assertEqual(r["titleMd"], "Weekly report")
        self.assertEqual(r["titleSvg"], "Plug")
        self.assertEqual(r["titleNone"], "")
        self.assertEqual(r["clip"], "a b…")

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_fix_notify_text_helpers(self):
        """เนื้อความแจ้งเตือน 'ตอบเสร็จ' มาจากข้อความใน IndexedDB: Markdown → ข้อความล้วน, เลือกคำตอบสุดท้ายของรอบเอเจนต์"""
        fns = "\n".join(js_function(self.src, n) for n in ("mdPlain", "replyText", "modelLabel"))
        code = fns + r"""
var md = "สร้างไฟล์ให้แล้วครับ: [ux4-สถานี.xlsx](/_qwen/out/ux4.xlsx)\n\n## สรุป\n\n1. **สถานี A** ผ่าน\n- [x] เปลี่ยน `contactor`\n" +
  "> หมายเหตุ *สำคัญ*\n\n```python\nprint('ห้ามโผล่')\n```\n\n| ตู้ | ผล |\n|---|:---:|\n| EV-01 | ผ่าน |\n\n---\n![fig](/_qwen/out/f.png)\n" +
  "ชื่อเครื่องมือ local_read ~~เก่า~~ <b>ตัวหนา</b>";
var chain = [
  {role: "assistant", content: ""},                                   // ล่างสุดแต่ว่าง (จบที่เรียกเครื่องมือ)
  {role: "tool", content: "สร้างไฟล์แล้ว"},
  {role: "assistant", content: "<think>คิดอยู่</think>คำตอบก่อนเรียกเครื่องมือ"},
];
var out = {
  plain: mdPlain(md),
  think: mdPlain("<think>ลับ</think>\nผลลัพธ์"),
  openThink: mdPlain("<think>ยังคิดไม่จบ"),
  tildeFence: mdPlain("ก่อน\n~~~\nโค้ด\n~~~\nหลัง"),
  unclosedFence: mdPlain("ก่อน\n```js\nโค้ดไม่ปิด"),
  last: replyText([{role: "assistant", content: "คำตอบสุดท้าย **ครบ**"}, {role: "tool", content: "x"},
                   {role: "assistant", content: "ก่อนหน้า"}]),
  skipEmpty: replyText(chain),
  none: replyText([{role: "tool", content: "ผลเครื่องมือ"}]),
  lbl27: modelLabel("Qwen3.8-27B-UD-Q4_K_M"),
  lblOss: modelLabel("gpt-oss-20b-MXFP4"),
  lblCoder: modelLabel("Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL"),
  lblPlain: modelLabel("my-model")
};
console.log(JSON.stringify(out));
"""
        r = run_node(code)
        p = r["plain"]
        for want in ("สร้างไฟล์ให้แล้วครับ: ux4-สถานี.xlsx", "สรุป", "สถานี A ผ่าน", "เปลี่ยน contactor", "หมายเหตุ สำคัญ",
                     "ตู้, ผล", "EV-01, ผ่าน", "local_read", "เก่า", "ตัวหนา"):
            self.assertIn(want, p)
        for bad in ("ห้ามโผล่", "](/", "**", "|", "```", "---", "![", "<b>", "fig", "##", "[x]"):
            self.assertNotIn(bad, p, "ต้องไม่เหลือ %r ใน %r" % (bad, p))
        self.assertEqual(r["think"], "ผลลัพธ์")
        self.assertEqual(r["openThink"], "")
        self.assertEqual(r["tildeFence"], "ก่อน\nหลัง")
        self.assertEqual(r["unclosedFence"], "ก่อน")
        self.assertEqual(r["last"], "คำตอบสุดท้าย ครบ")
        self.assertEqual(r["skipEmpty"], "คำตอบก่อนเรียกเครื่องมือ", "ข้ามข้อความผู้ช่วยที่ว่าง และตัดความคิดออก")
        self.assertEqual(r["none"], "", "ผลของเครื่องมือไม่ใช่คำตอบ")
        self.assertEqual(r["lbl27"], "Qwen3.8-27B")
        self.assertEqual(r["lblOss"], "gpt-oss-20b")
        self.assertEqual(r["lblCoder"], "Qwen3-Coder-30B-A3B-Instruct")
        self.assertEqual(r["lblPlain"], "my-model")

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_fix_reply_from_db_is_read_only(self):
        """replyFromDb อ่าน IndexedDB ของ WebUI แบบอ่านอย่างเดียว: ไม่มีฐานข้อมูล = ยกเลิกการสร้าง (ไม่สร้างฐานว่างแทน WebUI),
        เดินจาก currNode ขึ้นไปจนถึงข้อความผู้ใช้, ปิดการเชื่อมต่อทุกครั้ง, ไม่ขอทรานแซกชันแบบเขียน"""
        fns = "\n".join(js_function(self.src, n) for n in ("mdPlain", "replyText", "replyFromDb"))
        code = r"""
var log = {closed: 0, aborted: 0, modes: [], created: 0};
function later(f) { setTimeout(f, 1); }
function makeDb(stores) {
  return {
    objectStoreNames: {contains: function (n) { return Object.prototype.hasOwnProperty.call(stores, n); }},
    close: function () { log.closed++; },
    createObjectStore: function () { log.created++; },
    transaction: function (names, mode) {
      log.modes.push(mode);
      return {objectStore: function (n) { return {get: function (id) {
        var r = {}; later(function () { r.result = stores[n][id]; r.onsuccess && r.onsuccess(); }); return r; }}; }};
    }
  };
}
function fakeIdb(db) {
  return {open: function (name, ver) {
    log.name = name; log.ver = ver;
    var req = {};
    later(function () {
      if (!db) {                          // ฐานข้อมูลยังไม่มี: เบราว์เซอร์จะสร้างใหม่ถ้าไม่ยกเลิก
        req.result = makeDb({});
        req.transaction = {abort: function () { log.aborted++; later(function () { req.onerror && req.onerror(); }); }};
        req.onupgradeneeded && req.onupgradeneeded();
        return;
      }
      req.result = db; req.onsuccess && req.onsuccess();
    });
    return req;
  }};
}
var msgs = {
  u: {id: "u", role: "user", content: "ขอไฟล์", parent: "r"},
  a1: {id: "a1", role: "assistant", content: "", parent: "u"},
  t1: {id: "t1", role: "tool", content: "สร้างไฟล์แล้ว", parent: "a1"},
  a2: {id: "a2", role: "assistant", content: "เสร็จแล้วครับ: [รายงาน.docx](/_qwen/out/r.docx)\n\n```py\nx=1\n```", parent: "t1"},
  loop: {id: "loop", role: "assistant", content: "", parent: "loop"}
};
var stores = {conversations: {c1: {id: "c1", currNode: "a2"}, c2: {id: "c2", currNode: "loop"}}, messages: msgs};
var window = {}, indexedDB;
""" + fns + r"""
(async function () {
  var out = {};
  window.indexedDB = indexedDB = fakeIdb(makeDb(stores));
  out.chain = await replyFromDb("c1");
  out.loop = await replyFromDb("c2");
  out.missingConv = await replyFromDb("nope");
  out.noId = await replyFromDb(null);
  window.indexedDB = indexedDB = fakeIdb(null);
  out.noDb = await replyFromDb("c1");
  window.indexedDB = indexedDB = undefined;
  out.noApi = await replyFromDb("c1");
  out.log = log;
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""
        r = run_node(code)
        self.assertEqual(r["chain"], "เสร็จแล้วครับ: รายงาน.docx")
        self.assertEqual(r["loop"], "", "วนกลับหาตัวเองต้องไม่ค้าง")
        self.assertEqual(r["missingConv"], "")
        self.assertEqual(r["noId"], "")
        self.assertEqual(r["noDb"], "")
        self.assertEqual(r["noApi"], "")
        lg = r["log"]
        self.assertEqual(lg["name"], "LlamaUi")
        self.assertIsNone(lg.get("ver"), "เปิดโดยไม่ระบุเวอร์ชัน (ไม่อัปเกรดสคีมาของ WebUI)")
        self.assertEqual(lg["aborted"], 1, "ไม่มีฐานข้อมูล = ยกเลิก ไม่สร้างฐานว่าง")
        self.assertEqual(lg["created"], 0)
        self.assertEqual(set(lg["modes"]), {"readonly"})
        self.assertEqual(lg["closed"], 3, "ปิดการเชื่อมต่อทุกครั้งที่เปิดสำเร็จ (c1, c2, nope)")
        # ทั้งโมดูลไม่มีทางเขียนฐานข้อมูลของ WebUI (ตัวอ่านเองก็ไม่มีคำสั่งเขียน)
        for bad in ('"readwrite"', "'readwrite'", "deleteDatabase", "createObjectStore"):
            self.assertNotIn(bad, self.module, bad)
        fn = js_function(self.src, "replyFromDb")
        for bad in (".put(", ".add(", ".delete(", ".clear("):
            self.assertNotIn(bad, fn, bad)

    def test_fix_fast_confirm_and_position_contract(self):
        m = self.module
        # ปิดโหมดเร็ว: ตรวจสถานะตัวเลือกก่อนคลิก (ยังไม่โหลด = ไม่คลิก) — ชิปไม่เคยส่ง force
        self.assertIn('if (needLoaded && !optionReady(opt)) return "unloaded";', m)
        self.assertIn("var guard = want !== FAST_MODEL && !force && !fastArmed;", m)
        self.assertRegex(m, r"toggleFast\(\);\s*\n\s*\}\);", "คลิกชิปเรียก toggleFast() ไม่มี force")
        # ชิปอยู่ฝั่งซ้ายถัดจากกล่องปุ่ม "+" — ตำแหน่งไม่ขึ้นกับความกว้างของชื่อโมเดล
        self.assertIn('plus.closest(".mr-auto")', m)
        self.assertIn("anchor.after(fastChip)", m)
        th = self.src[self.src.index("var TH = {"):]
        self.assertIn('"{model} ยังไม่ได้โหลด', th, "คำแปลต้องเก็บตัวแทน {model} ไว้")

    def test_css_has_new_pieces_with_tokens_only(self):
        a = self.css.index("10. รอบ 4")
        sec = self.css[a:]
        for sel in (".qw-fast", ".qw-fast[aria-pressed=\"true\"]", ".qw-art-btn", ".qw-img-art", ".qw-speak",
                    ".qw-speak-stop", ".qw-quote", ".qw-quote[hidden]", ":focus-visible",
                    ".qw-fast[data-armed=\"1\"]", ".qw-fast-hint", ".qw-fast-hint[hidden]", ".qw-sr"):
            self.assertIn(sel, sec, sel)
        self.assertNotRegex(sec, r"#[0-9a-fA-F]{3,8}\b", "ส่วนใหม่ต้องใช้ token ไม่ใช่สีตายตัว")
        self.assertNotRegex(sec, r"rgba?\(", "ส่วนใหม่ต้องใช้ token ไม่ใช่สีตายตัว")
        # ขั้นถามต้องไม่ทำให้ชิปกว้างขึ้น (ชิปห้ามขยับ): ไม่เปลี่ยนความหนาเส้นขอบ ใช้เงาด้านในแทน
        armed = sec[sec.index('.qw-fast[data-armed="1"]'):]
        armed = armed[:armed.index("}")]
        self.assertNotRegex(armed, r"\bborder(-width)?\s*:", "ห้ามตั้ง border/border-width ใหม่ตอนถาม")
        # ฟอนต์โค้ด (Cascadia Code) ห้ามรวมตัวอักษร: |---| ->> <= => ต้องเห็นตามจริง
        m = re.search(r"html:root :is\(([^)]*)\)\s*\{([^}]*)\}", sec[sec.index("ligature"):])
        self.assertTrue(m, "ไม่พบกฎปิด ligature")
        for sel in ("pre", "code", ".font-mono"):
            self.assertIn(sel, [s.strip() for s in m.group(1).split(",")])
        self.assertIn("font-variant-ligatures: none", m.group(2))
        self.assertIn('"calt" 0', m.group(2))

    def test_privacy_branding_and_contract(self):
        m = self.module
        for bad in ("fetch(", "XMLHttpRequest", "http://", "https://", "WebSocket(", "sendBeacon", "eval(", "Claude",
                    "Anthropic"):
            self.assertNotIn(bad, m, bad)
        self.assertIn("v.localService", m, "เสียงอ่านต้องเลือกจากเสียงในเครื่องเท่านั้น")
        self.assertNotRegex(m, r"voices?\s*\[\s*0\s*\]", "ห้ามหยิบเสียงตัวแรก (อาจเป็นเสียงออนไลน์)")
        for call in ('callShell("notify"', 'callShell("openArtifact"', "prefill(q + "):
            self.assertIn(call, m)
        for kind in ('"done"', '"permission"', '"continue"'):
            self.assertIn(kind, m)
        self.assertIn('FAST_MODEL = "%s"' % FAST_MODEL, m)
        # ต่อเข้ากับวงจรเดิม: ท้าย pass() และ observer ของ body
        self.assertIn("extrasPass(r, st);", self.src)
        self.assertIn("promptScanSoon();", self.src)
        # ไม่มี innerHTML จากข้อมูล (ใช้กับ svg คงที่เท่านั้น)
        for line in m.splitlines():
            if "innerHTML" in line:
                self.assertRegex(line, r"innerHTML = xIcon\(", line.strip())


# ------------------------------------------------------------------------------------------------ E2E
E2E = os.environ.get("QWEN_UI_E2E") == "1"
T0 = 1790200000000
IMG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAHElEQVR4nGP4z8BAEmIY1TCqYVTDqIZR"
       "DSNUAwCdEj/BtP7rNQAAAABJRU5ErkJggg==")
A1 = ("หน้า HTML:\n\n```html\n<html><head><title>Dash</title></head><body><h1>ตู้</h1></body></html>\n```\n\n"
      "```csv\nstation,faults\nEV150-01,3\n```\n\n```python\nprint(1)\n```\n\n![fig](%s)\n\n"
      "สรุปแบบสั้น: ตู้ที่หลุดบ่อยเกิดจาก Heartbeat ขาดช่วงครับ\n\nThen check the WebSocket ping interval as well." % IMG)


def fixture():
    cid = "enh-e2e-0001"
    root = {"id": cid + "-r", "convId": cid, "type": "root", "role": "system", "content": "", "parent": None,
            "children": [cid + "-u"], "timestamp": T0, "toolCalls": ""}
    u = {"id": cid + "-u", "convId": cid, "type": "text", "role": "user", "content": "ขอหน้า HTML", "parent": root["id"],
         "children": [cid + "-a"], "timestamp": T0 + 1, "toolCalls": "", "extra": []}
    a = {"id": cid + "-a", "convId": cid, "type": "text", "role": "assistant", "content": A1, "parent": u["id"],
         "children": [], "timestamp": T0 + 2, "toolCalls": "", "model": "Qwen3.8-27B-UD-Q4_K_M",
         "timings": {"prompt_n": 10, "prompt_ms": 10.0, "predicted_n": 10, "predicted_ms": 1000.0, "predicted_per_second": 10}}
    conv2, msgs2 = fixture_regen()
    return {"conversations": [{"id": cid, "name": "E2E artifacts", "lastModified": T0 + 10, "currNode": a["id"],
                               "reasoningEffort": "default"}, conv2], "messages": [root, u, a] + msgs2}


def regen_html(word):
    return ("```html\n<html><head><title>สถานะตู้ชาร์จ</title></head><body><h1>สถานะตู้ชาร์จ</h1><p>%s</p></body></html>\n"
            "```\n\n```markdown\n| สถานี | สถานะ |\n|---|---|\n```\n\n```text\nCharger->>CSMS: Boot\na <= b => c\n```" % word)


def fixture_regen():
    """แชตที่สอง: คำตอบพี่น้องสองรุ่น (เหมือนกด Regenerate) บล็อก HTML ชื่อเดียวกัน — เปลี่ยนรุ่นด้วยปุ่ม Next version"""
    cid = "enh-e2e-0002"
    tm = {"prompt_n": 10, "prompt_ms": 10.0, "predicted_n": 10, "predicted_ms": 1000.0, "predicted_per_second": 10}
    root = {"id": cid + "-r", "convId": cid, "type": "root", "role": "system", "content": "", "parent": None,
            "children": [cid + "-u"], "timestamp": T0 + 20, "toolCalls": ""}
    u = {"id": cid + "-u", "convId": cid, "type": "text", "role": "user", "content": "ขอหน้าสถานะ", "parent": root["id"],
         "children": [cid + "-a1", cid + "-a2"], "timestamp": T0 + 21, "toolCalls": "", "extra": []}
    a1 = {"id": cid + "-a1", "convId": cid, "type": "text", "role": "assistant", "content": "รุ่น 1\n\n" + regen_html("ขัดข้อง"),
          "parent": u["id"], "children": [], "timestamp": T0 + 22, "toolCalls": "", "model": "Qwen3.8-27B-UD-Q4_K_M",
          "timings": tm}
    a2 = {"id": cid + "-a2", "convId": cid, "type": "text", "role": "assistant", "content": "รุ่น 2\n\n" + regen_html("ปกติ"),
          "parent": u["id"], "children": [], "timestamp": T0 + 23, "toolCalls": "", "model": "Qwen3.8-27B-UD-Q4_K_M",
          "timings": tm}
    conv = {"id": cid, "name": "E2E regenerate", "lastModified": T0, "currNode": a1["id"], "reasoningEffort": "default"}
    return conv, [root, u, a1, a2]


# ตัวกันที่ proxy สำเนา: ห้ามสั่งโหลดโมเดล/ส่งข้อความหาโมเดล (เทสต์ชิปสลับโมเดลไปมาได้โดยไม่แตะ router)
BLOCK_POST = ("/models/load", "/chat/completions", "/v1/completions", "/completions", "/completion", "/infill",
              "/v1/responses", "/v1/messages")
BLOCKED = []


def guarded_handler(base):
    class Guarded(base):
        def do_POST(self):
            p = self.path.split("?", 1)[0].rstrip("/")
            if any(p.endswith(b) for b in BLOCK_POST):
                BLOCKED.append(p)
                data = b'{"error":"blocked by test"}'
                self.close_connection = True
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_POST()
    return Guarded


def free_port(cands=(8174, 8175, 8176, 8177)):
    for p in cands:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return None


@unittest.skipUnless(E2E, "E2E ปิดอยู่ (set QWEN_UI_E2E=1)")
class BrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, TOOLS)
        sys.path.insert(0, os.path.dirname(HUB))
        import shot  # noqa: E402  (tools/shot.py — WS/evaluate/close_edge)
        cls.shot = shot
        cls.port = free_port()
        if not cls.port:
            raise unittest.SkipTest("พอร์ตสำรอง 8174-8177 ไม่ว่าง")
        spec = importlib.util.spec_from_file_location("hub_enh_e2e", HUB)
        hub = importlib.util.module_from_spec(spec)
        tmp = tempfile.gettempdir()
        with mock.patch.object(sys, "argv", ["hub.py"]), \
                mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                             "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
            spec.loader.exec_module(hub)
        if STATIC_DIR:
            from pathlib import Path
            hub.STATIC_DIR = Path(STATIC_DIR)          # ทดสอบไฟล์สำเนาก่อนติดตั้ง (หน้าจริงของผู้ใช้ไม่เห็น)
        port = cls.port

        def projects():
            return [dict(p, port=port) for p in hub.load_projects() if p["slug"] == "project1"]
        if not projects():
            raise unittest.SkipTest("ไม่มีโปรเจกต์ project1")
        cls.srv = hub.ThreadingHTTPServer(("127.0.0.1", port),
                                          guarded_handler(hub.make_proxy_handler("project1", projects)))
        cls.srv.daemon_threads = True
        cls.srv.handle_error = lambda *a: None      # Edge ปิดซ็อกเก็ตตอนจบเทสต์ = ConnectionReset ไม่ใช่ความผิดพลาด
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        edge = next((p for p in shot.EDGE_CANDIDATES if os.path.isfile(p)), None)
        if not edge:
            cls.srv.shutdown()
            raise unittest.SkipTest("ไม่มี Edge")
        dbg = shot.free_port()
        cls.profile = tempfile.mkdtemp(prefix="qwen-shot-")
        cls.proc = subprocess.Popen([edge, "--headless=new", "--disable-gpu", "--no-first-run", "--mute-audio",
                                     "--no-default-browser-check", "--disable-extensions",
                                     "--remote-debugging-port=%d" % dbg, "--user-data-dir=%s" % cls.profile,
                                     "--window-size=1440,900", "about:blank"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(100):
            try:
                tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % dbg, timeout=2).read())
                page = next((t for t in tabs if t.get("type") == "page"), None)
                if page:
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except OSError:
                pass
            time.sleep(0.15)
        cls.ws = shot.WS(ws_url)
        cls.ws.call("Page.enable")
        cls.ws.call("Runtime.enable")
        cls.ws.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1,
                                                            "mobile": False})
        # การทดสอบห้ามเปลี่ยนค่าตั้งจริงของผู้ใช้บน hub
        cls.ws.call("Fetch.enable", {"patterns": [{"urlPattern": "http://127.0.0.1:8100/api/settings*"}]})
        origin = "http://127.0.0.1:%d" % port
        shot.navigate(cls.ws, origin + "/?ui=1", settle=3.0)
        shot.evaluate(cls.ws, shot.SEED_JS % json.dumps(fixture(), ensure_ascii=False))
        shot.navigate(cls.ws, origin + "/?lang=th", settle=4.0)
        # ตัวจดแทนของจริง (ตัวจริงเก็บไว้ใน __realOpen ให้เทสต์แผงตามรุ่นใหม่ใช้แผงจริงของ shell)
        cls.shell("(()=>{window.__notes=[];window.__arts=[];const a=window.qwenShellApi;window.__realOpen=a.openArtifact;"
                  "a.notify=function(n){__notes.push(n)};a.openArtifact=function(x){__arts.push(x)};return 1})()")
        cls.frame("qwenEnhance.openChat('enh-e2e-0001')")
        cls.ws.drain(4.0)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.shot.close_edge(cls.proc, cls.profile)
        finally:
            cls.srv.shutdown()

    @classmethod
    def shell(cls, js):
        return cls.shot.evaluate(cls.ws, js)

    @classmethod
    def frame(cls, js):
        return cls.shot.evaluate(cls.ws, "(async()=>{const w=document.getElementById('frame').contentWindow;"
                                         "return await w.eval(%s)})()" % json.dumps(js))

    def click_frame(self, sel):
        self.shell("(()=>{const e=document.getElementById('frame').contentDocument.querySelector(%s);"
                   "if(e)e.scrollIntoView({block:'center'});return 1})()" % json.dumps(sel))
        self.ws.drain(0.3)
        xy = self.shell("(()=>{const f=document.getElementById('frame'),e=f.contentDocument.querySelector(%s);"
                        "if(!e)return null;const r=e.getBoundingClientRect(),o=f.getBoundingClientRect();"
                        "return [o.left+r.left+r.width/2,o.top+r.top+r.height/2]})()" % json.dumps(sel))
        self.assertTrue(xy, sel)
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.ws.call("Input.dispatchMouseEvent", {"type": t, "x": xy[0], "y": xy[1], "button": "left",
                                                     "clickCount": 1})

    def test_1_artifact_buttons_and_payloads(self):
        n = self.frame("(()=>{qwenEnhance.refresh(); return [document.querySelectorAll('.qw-art-btn').length,"
                       " document.querySelectorAll('.qw-img-art').length]})()")
        self.assertEqual(n, [2, 1], "html + csv (ไม่ใช่ python) และภาพ 1 ภาพ")
        self.click_frame(".qw-art-btn")
        self.click_frame(".qw-img-art")
        arts = self.shell("__arts.splice(0)")
        self.assertEqual([a["kind"] for a in arts], ["html", "image"])
        self.assertEqual(arts[0]["title"], "Dash")
        self.assertEqual(arts[0]["id"], "enh-e2e-0001:html:t:dash")
        self.assertIn("<title>Dash</title>", arts[0]["code"])
        self.assertTrue(arts[1]["code"].startswith("data:image/png"))
        # ป้ายไทยผ่านตัวแปล
        self.assertEqual(self.frame("document.querySelector('.qw-img-art').textContent"), "เปิดในแผง")

    def test_2_notify_done_and_permission(self):
        self.frame("(()=>{const s=document.createElement('span');s.className='stop-button';s.id='e2eStop';"
                   "document.body.appendChild(s);return 1})()")
        self.ws.drain(0.6)
        # จำลองแท็บที่ถูกซ่อน: WebUI ไม่วาด DOM ของคำตอบ (รีวิว UX เห็น body = "" / "[ux") — เนื้อความต้องมาจาก IndexedDB
        self.frame("(()=>{const ms=document.querySelectorAll('.chat-message-assistant .markdown-content');"
                   "window.__saved=[...ms].map(mc=>[mc,[...mc.childNodes]]);ms.forEach(mc=>mc.replaceChildren());"
                   "document.getElementById('e2eStop').remove();return ms.length})()")
        self.ws.drain(1.6)
        self.frame("(()=>{(window.__saved||[]).forEach(([mc,k])=>mc.replaceChildren(...k));return 1})()")
        notes = self.shell("__notes.splice(0)")
        self.assertEqual([x["kind"] for x in notes], ["done"])
        self.assertTrue(notes[0]["title"].startswith("ตอบเสร็จแล้ว"))
        body = notes[0]["body"]
        self.assertTrue(body.startswith("หน้า HTML: สรุปแบบสั้น: ตู้ที่หลุดบ่อย"), body)
        for bad in ("print(1)", "<title>", "data:image", "```"):
            self.assertNotIn(bad, body)
        self.assertLessEqual(len(body), 140)
        self.assertEqual(notes[0]["chatId"], "enh-e2e-0001")
        self.assertTrue(self.frame("qwenEnhance.lastReply()").startswith("หน้า HTML:"))
        self.frame("(()=>{const m=document.querySelector('.chat-message-assistant .agentic-content');"
                   "const d=document.createElement('div');d.id='e2ePerm';d.className='my-2 rounded-lg border border-border bg-card p-3';"
                   "d.innerHTML='<div class=\"mb-3 flex items-center gap-2 text-sm\"><span>Allow use of <span class=\"font-semibold\">local_confirm</span>?</span></div>"
                   "<div class=\"flex flex-wrap items-center gap-2\"><button>Allow once</button><button>Deny</button></div>';"
                   "m.appendChild(d);return 1})()")
        self.ws.drain(1.0)
        notes = self.shell("__notes.splice(0)")
        self.frame("document.getElementById('e2ePerm').remove()")
        self.assertEqual([x["kind"] for x in notes], ["permission"])
        self.assertIn("local_confirm", notes[0]["body"])

    def test_3_quote_to_ask(self):
        self.frame("qwenEnhance.prefill('')")
        sel = self.frame("(()=>{const ps=[...document.querySelectorAll('.chat-message-assistant .markdown-content p')];"
                         "const p=ps.find(x=>/สรุปแบบสั้น/.test(x.textContent)); p.scrollIntoView({block:'center'});"
                         "const t=document.createTreeWalker(p,NodeFilter.SHOW_TEXT).nextNode(); const r=document.createRange();"
                         "r.setStart(t,0); r.setEnd(t,11); getSelection().removeAllRanges(); getSelection().addRange(r);"
                         "return getSelection().toString()})()")
        self.ws.drain(0.6)
        self.assertFalse(self.frame("document.querySelector('.qw-quote').hidden"))
        self.click_frame(".qw-quote")
        self.ws.drain(0.4)
        v = self.frame("(()=>{const ta=document.querySelector('.chat-screen-form-wrapper textarea');"
                       "return [ta.value, document.activeElement===ta, ta.selectionStart===ta.value.length]})()")
        self.assertEqual(v, ["> " + sel + "\n\n", True, True])
        self.frame("qwenEnhance.prefill('')")

    def test_4_read_aloud_state_machine(self):
        # เสียงจริงไม่จำเป็น: แทน speak ด้วยตัวปลอมที่จบชิ้นทันที แล้วจดเสียงที่ถูกเลือก
        self.frame("(()=>{window.__spk=[]; speechSynthesis.speak=function(u){__spk.push([u.voice&&u.voice.localService,u.lang]);"
                   " setTimeout(function(){u.onend&&u.onend({})},30)}; return 1})()")
        self.frame("document.querySelector('.qw-speak').click()")
        st = self.frame("qwenEnhance.speechState()")
        self.assertEqual(st["state"], "playing")
        self.assertTrue(self.frame("!!document.querySelector('.qw-speak-stop')"))
        self.ws.drain(3.0)                  # รอรายชื่อเสียง (≤ 1.5 วิ) + ชิ้นละ 30ms
        spk = self.frame("__spk")
        self.assertTrue(spk, "ต้องเริ่มพูด")
        self.assertTrue(all(x[0] in (True, None) for x in spk), "ห้ามใช้เสียงออนไลน์: %r" % spk)
        self.assertIn("th-TH", [x[1] for x in spk])
        self.assertIn("en-US", [x[1] for x in spk])
        self.assertEqual(self.frame("qwenEnhance.speechState().state"), "idle", "อ่านจบแล้วต้องกลับเป็น idle")
        self.assertFalse(self.frame("!!document.querySelector('.qw-speak-stop')"))

    def test_5_fast_chip(self):
        fm = self.frame("qwenEnhance.fastModel()")
        self.assertTrue(fm["available"])
        self.assertTrue(self.frame("!!document.querySelector('.qw-fast[aria-pressed]')"))
        # สลับจริงเฉพาะเมื่อ 4B โหลดอยู่แล้ว (ไม่สั่งโหลดโมเดลจริงระหว่างเทสต์) และไม่สลับกลับ
        loaded = self.shell("fetch('/models').then(r=>r.json()).then(d=>(d.data||[]).filter(m=>(m.status||{}).value==='loaded').map(m=>m.id))")
        if FAST_MODEL not in (loaded or []):
            self.skipTest("4B ไม่ได้โหลดอยู่ — ข้ามการสลับจริง")
        self.click_frame(".qw-fast")
        self.ws.drain(2.5)
        fm = self.frame("qwenEnhance.fastModel()")
        self.assertTrue(fm["fast"])
        self.assertTrue(fm["remembered"])
        self.assertEqual(self.frame("document.querySelector('.qw-fast').getAttribute('aria-pressed')"), "true")
        self.assertFalse(self.frame("!!document.querySelector('[data-slot=dropdown-menu-content][data-state=open]')"))

    # ---- รอบแก้หลังรีวิว UX ----
    CHIP = ("(()=>{const c=document.querySelector('.qw-fast'),h=document.querySelector('.qw-fast-hint');"
            "const r=c.getBoundingClientRect();return {x:Math.round(r.left),w:Math.round(r.width),left:!!c.closest('.mr-auto'),"
            "pressed:c.getAttribute('aria-pressed'),armed:c.getAttribute('data-armed'),"
            "hint:h&&!h.hidden?h.textContent:null,live:(document.querySelector('.qw-sr[role=status]')||{}).textContent||'',"
            "fm:qwenEnhance.fastModel()}})()")

    def test_6_fast_chip_stable_and_asks_before_loading(self):
        """ชิปอยู่ฝั่งซ้ายถัดจาก "+" ตำแหน่งไม่ขยับเมื่อสลับ · ปิดโหมดเร็วไปหาโมเดลที่ยังไม่โหลด = ถามก่อน ไม่สั่งโหลด"""
        loaded = self.shell("fetch('/v1/models').then(r=>r.json()).then(d=>(d.data||[]).filter(m=>(m.status||{}).value"
                            "==='loaded').map(m=>m.id))") or []
        pm = self.frame("qwenEnhance.fastModel().project")
        if pm in loaded:
            self.skipTest("โมเดลของโปรเจกต์โหลดอยู่แล้ว — ไม่มีอะไรต้องถาม")
        del BLOCKED[:]
        before = self.frame(self.CHIP)
        self.assertTrue(before["left"], "ชิปต้องอยู่ในกลุ่มซ้ายของแถวเครื่องมือ (ถัดจาก +)")
        self.assertTrue(self.frame("qwenEnhance.setFast(true, true)"))   # WebUI เลือก 4B (คำขอโหลดถูกตัวกันตัดทิ้ง)
        self.ws.drain(0.8)
        on = self.frame(self.CHIP)
        self.assertEqual(on["pressed"], "true")
        self.assertEqual(on["x"], before["x"], "ชิปขยับเมื่อชื่อโมเดลเปลี่ยน")
        n_load = len(BLOCKED)
        self.click_frame(".qw-fast")                                        # กดครั้งแรก: ถาม ไม่สลับ ไม่โหลด
        self.ws.drain(2.2)
        armed = self.frame(self.CHIP)
        self.assertEqual(armed["armed"], "1")
        self.assertTrue(armed["fm"]["fast"], "ยังต้องอยู่ที่ 4B")
        self.assertEqual(len(BLOCKED), n_load, "กดครั้งแรกต้องไม่มีคำขอโหลดโมเดล: %r" % BLOCKED)
        self.assertIn("ยังไม่ได้โหลด", armed["hint"] or "")
        self.assertIn(pm.split("-UD-")[0].split("-Q")[0], armed["hint"])
        self.assertEqual(armed["live"], armed["hint"], "ผู้อ่านจอได้ยินข้อความเดียวกัน")
        self.assertEqual(armed["x"], before["x"])
        self.click_frame(".qw-fast")                                        # กดซ้ำ = ยืนยัน → สลับจริง
        self.ws.drain(2.5)
        back = self.frame(self.CHIP)
        self.assertFalse(back["fm"]["fast"])
        self.assertIsNone(back["armed"])
        self.assertIsNone(back["hint"])
        self.assertEqual(back["x"], before["x"])
        self.assertIn("/models/load", BLOCKED[n_load:], "ยืนยันแล้ว WebUI จึงสั่งโหลด (ถูกตัวกันตัดทิ้ง)")
        # Esc ยกเลิกขั้นถาม
        self.frame("qwenEnhance.setFast(true, true)")
        self.ws.drain(0.8)
        self.frame("qwenEnhance.setFast(false)")
        self.ws.drain(2.0)
        self.assertEqual(self.frame(self.CHIP)["armed"], "1")
        self.ws.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape",
                                                "windowsVirtualKeyCode": 27})
        self.ws.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape",
                                                "windowsVirtualKeyCode": 27})
        self.ws.drain(0.4)
        esc = self.frame(self.CHIP)
        self.assertIsNone(esc["armed"])
        self.assertTrue(esc["fm"]["fast"])
        self.frame("qwenEnhance.setFast(false, true)")
        self.ws.drain(1.5)

    def test_7_panel_follows_regeneration(self):
        """แผงเปิดชิ้น "สถานะตู้ชาร์จ" รุ่น 1 → ได้คำตอบรุ่นใหม่ (จำลอง: สตรีมจบหลังสลับไปคำตอบพี่น้อง) → แผงเป็นรุ่น 2/2 เอง"""
        self.shell("(()=>{window.qwenShellApi.openArtifact=window.__realOpen;return 1})()")
        try:
            self.frame("qwenEnhance.openChat('enh-e2e-0002')")
            self.ws.drain(3.0)
            panel = ("(()=>{const a=document.getElementById('art'),f=document.getElementById('artFrame');"
                     "const s=f&&f.getAttribute('srcdoc')||'';return {open:!a.hidden,title:document.getElementById('artTitle')"
                     ".textContent,ver:document.getElementById('artVerT').textContent,v1:s.includes('ขัดข้อง'),"
                     "v2:s.includes('ปกติ')}})()")
            self.click_frame(".chat-message-assistant .qw-art-btn")
            self.ws.drain(1.0)
            p1 = self.shell(panel)
            self.assertEqual([p1["open"], p1["title"], p1["ver"], p1["v1"]], [True, "สถานะตู้ชาร์จ", "1 / 1", True])
            self.frame("(()=>{const s=document.createElement('span');s.className='stop-button';s.id='e2eStop2';"
                       "document.body.appendChild(s);return 1})()")
            self.ws.drain(0.8)
            self.click_frame(".chat-message-assistant button[aria-label='Next version']")
            self.ws.drain(1.0)
            self.frame("document.getElementById('e2eStop2').remove()")
            self.ws.drain(2.5)
            p2 = self.shell(panel)
            self.assertEqual([p2["open"], p2["title"], p2["ver"], p2["v2"], p2["v1"]],
                             [True, "สถานะตู้ชาร์จ", "2 / 2", True, False], p2)
        finally:
            self.shell("(()=>{window.qwenShellApi.closeArtifact();window.qwenShellApi.openArtifact="
                       "function(x){__arts.push(x)};return 1})()")

    def test_8_code_font_has_no_ligatures(self):
        """Cascadia Code รวม |---| ->> <= => เป็นสัญลักษณ์ — ซอร์สที่ผู้ใช้คัดลอก/เรียนต้องเห็นตัวอักษรจริง"""
        r = self.frame("(()=>{const out=[];document.querySelectorAll('.chat-message-assistant pre code, "
                       ".chat-message-assistant pre').forEach(e=>{const s=getComputedStyle(e);"
                       "out.push([s.fontVariantLigatures,s.fontFeatureSettings])});return out})()")
        self.assertTrue(r)
        for lig, feat in r:
            self.assertEqual(lig, "none")
            self.assertIn('"calt" 0', feat)


if __name__ == "__main__":
    unittest.main()
