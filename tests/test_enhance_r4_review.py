# -*- coding: utf-8 -*-
"""
เทสต์ของ R4 (รอบ 5, 2026-09-30): กล่องตรวจทานในการ์ดอนุญาต local_confirm (webui-enhance.js / webui-theme.css)

รันฟังก์ชันจริงจากซอร์สใน Node (ไม่ต้องเปิดเบราว์เซอร์/hub):
  * pickConfirmCall — ตัวที่รออนุญาต = calls[จำนวนผล] (จับคู่ด้วยตำแหน่ง, id ซ้ำ/ลำดับไม่ตรง = ไม่เดา),
    ชื่อต้องตรงกับการ์ด, แปลงอาร์กิวเมนต์แบบ WebUI
  * confirmCallFromDb — อ่าน IndexedDB แบบอ่านอย่างเดียว: currNode → ข้อความผู้ช่วย → ลูก (ผลเครื่องมือเป็นพี่น้องกัน
    แบบที่ WebUI สร้างจริง) · แก้ 2026-10-01: แบบเดิมการ์ดของการเรียกตัวที่ 3 โชว์ของตัวที่ 1
  * rvAppend/rvCode — อักขระซ่อนดิบ -> «U+XXXX», รหัส/เครื่องหมายของเซิร์ฟเวอร์ถูกเน้น, ข้อความที่แสดง = ข้อความจริงทุกตัว
  * ป้ายใหม่มีคำแปลไทย, CSS ใช้ token, การ์ดของ local_confirm ซ่อนเมนู "อนุญาตเสมอ", ไม่มี innerHTML จากข้อมูล
ชี้ไปไฟล์สำเนาได้: QWEN_ENH_FILE, QWEN_THEME_FILE
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ENH = os.environ.get("QWEN_ENH_FILE") or r"C:\LLM\projects\static\webui-enhance.js"
CSS = os.environ.get("QWEN_THEME_FILE") or r"C:\LLM\projects\static\webui-theme.css"
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
HAVE_NODE = os.path.isfile(NODE) if os.path.isabs(NODE) else bool(shutil.which("node"))
R4_START = "R4 (รอบ 5, 2026-09-30)"
R4_END = "\n  function confirmCards()"

LABELS = [
    "Review this — it is exactly what will run",
    "Loading what will run...",
    "Confirm code",
    "Hidden or look-alike characters are shown as «U+XXXX». Don't allow unless you expected them.",
    "This request has no review text, so you can't see what will run. Choose Deny.",
    "Arguments sent by the model:",
    "This request's arguments aren't valid JSON. Choose Deny.",
    "Couldn't read what this request will run. Expand the local_confirm call above to check it, or choose Deny.",
    "This review is far longer than the server ever issues. Choose Deny.",
]


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def js_block(src, start):
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
        raise AssertionError("node failed: %s" % r.stderr[-2000:])
    return json.loads(r.stdout)


# DOM จิ๋วพอให้ rvAppend/rvCode ทำงานใน Node: element = {tag, className, classList, children, textContent, title}
DOM_STUB = r"""
function mkEl(tag) {
  var e = {tag: tag, className: "", children: [], attrs: {}, title: "", _text: null, style: {setProperty: function () {}}};
  e.classList = {add: function (c) { e.className = (e.className ? e.className + " " : "") + c; },
                 contains: function (c) { return (" " + e.className + " ").indexOf(" " + c + " ") >= 0; }};
  e.appendChild = function (c) { e.children.push(c); return c; };
  e.setAttribute = function (k, v) { e.attrs[k] = v; };
  Object.defineProperty(e, "textContent", {
    get: function () { return e._text != null ? e._text : e.children.map(function (c) { return c.textContent; }).join(""); },
    set: function (v) { e._text = String(v); e.children = []; }
  });
  return e;
}
var document = {createTextNode: function (t) { return {textContent: t, text: true}; }};
function el(tag, cls) { var e = mkEl(tag); if (cls) e.className = cls; return e; }
function kinds(node) {
  return node.children.map(function (c) { return c.text ? ["t", c.textContent] : [c.className, c.textContent, c.title || ""]; });
}
"""


@unittest.skipUnless(HAVE_NODE, "ไม่มี node")
class ReviewBoxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(ENH)
        cls.css = read(CSS)
        a = cls.src.index(R4_START)
        cls.r4 = cls.src[cls.src.rindex("/*", 0, a):cls.src.index(R4_END, a)]

    def test_labels_have_thai(self):
        th = run_node(js_block(self.src, self.src.index("var TH = {")).replace("var TH =", "const TH =", 1) +
                      ";\nconsole.log(JSON.stringify(TH));")
        for en in LABELS:
            self.assertIn(en, th, en)
            self.assertRegex(th[en], "[\u0E00-\u0E7F]", en)
        self.assertEqual(th["Review this — it is exactly what will run"].replace("\u2060", ""),
                         "ตรวจโค้ด/คำสั่งนี้ก่อนกดอนุญาต — นี่คือสิ่งที่จะรันจริง")
        # ทุกข้อความของ rvNote / textContent ในส่วน R4 ต้องอยู่ในรายการข้างบน
        for lit in re.findall(r'rvNote\("[a-z]+", "([^"]+)"\)|textContent = "([^"]+)"', self.r4):
            s = lit[0] or lit[1]
            self.assertIn(s, th, "ป้าย %r ไม่มีคำแปลไทย" % s)

    def test_pick_confirm_call(self):
        code = self.r4 + r"""
function call(id, name, args) { return {id: id, type: "function", function: {name: name, arguments: args}}; }
var A = JSON.stringify({confirm_token: "aaaa1111", review: "[python]\n1│ print(1)"});
var B = JSON.stringify({confirm_token: "bbbb2222", review: "[run]\n1│ dir"});
var C3 = JSON.stringify({confirm_token: "cccc3333"});
var two = JSON.stringify([call("c1", "local_confirm", A), call("c2", "local_confirm", B)]);
var three = JSON.stringify([call("c1", "local_confirm", A), call("c2", "local_confirm", B), call("c3", "local_confirm", C3)]);
// อาร์กิวเมนต์ที่ 2 = toolCallId ของผลที่บันทึกแล้วตามลำดับ (จับคู่ด้วยตำแหน่ง แก้ 2026-10-01)
var out = {
  first: pickConfirmCall(two, [], "local_confirm"),
  second: pickConfirmCall(two, ["c1"], "local_confirm"),
  none: pickConfirmCall(two, ["c1", "c2"], "local_confirm"),
  third: pickConfirmCall(three, ["c1", "c2"], "local_confirm"),
  // ผลของตัวที่ 2 มาแต่ไม่มีของตัวที่ 1 / ลำดับสลับ / ผลเกิน = ไม่ใช่สิ่งที่ WebUI ทำ → ไม่เดา
  skipped: pickConfirmCall(three, ["c2"], "local_confirm"),
  swapped: pickConfirmCall(three, ["c2", "c1"], "local_confirm"),
  extra: pickConfirmCall(two, ["c1", "c2", "c3"], "local_confirm"),
  // id ซ้ำ (ตัวที่ 1/2) หรือว่างซ้ำ = ระบุไม่ได้ว่าผลไหนของใคร (เคยโชว์ของตัวที่ 3 บนการ์ดของตัวที่ 2)
  dupIds: pickConfirmCall(JSON.stringify([call("x1", "local_confirm", A), call("x1", "local_confirm", B),
                                          call("x3", "local_confirm", C3)]), ["x1"], "local_confirm"),
  dupFirst: pickConfirmCall(JSON.stringify([call("x1", "local_confirm", A), call("x1", "local_confirm", B)]), [], "local_confirm"),
  emptyIds: pickConfirmCall(JSON.stringify([call("", "local_confirm", A), call("", "local_confirm", B)]), [""], "local_confirm"),
  noId: pickConfirmCall(JSON.stringify([{type: "function", function: {name: "local_confirm", arguments: A}}]), [], "local_confirm"),
  numId: pickConfirmCall([call(7, "local_confirm", A), call("7", "local_confirm", B)], [7], "local_confirm"),
  nullCall: pickConfirmCall(JSON.stringify([null, call("c2", "local_confirm", B)]), [], "local_confirm"),
  notArray: pickConfirmCall(two, {c1: 1}, "local_confirm"),
  mismatch: pickConfirmCall(JSON.stringify([call("c1", "local_do", A)]), [], "local_confirm"),
  bad: pickConfirmCall(JSON.stringify([call("c1", "local_confirm", "{\"review\": \"x")]), [], "local_confirm"),
  arr: pickConfirmCall(JSON.stringify([call("c1", "local_confirm", "[1,2]")]), [], "local_confirm"),
  empty: pickConfirmCall(JSON.stringify([call("c1", "local_confirm", "  ")]), [], "local_confirm"),
  obj: pickConfirmCall([call("c1", "local_confirm", {review: "r", confirm_token: "t"})], [], "local_confirm"),
  dup: pickConfirmCall(JSON.stringify([call("c1", "local_confirm", "{\"review\":\"shown?\",\"review\":\"sent\"}")]), [], "local_confirm"),
  noCalls: pickConfirmCall("", [], "local_confirm"),
  junk: pickConfirmCall("{not json", [], "local_confirm")
};
console.log(JSON.stringify(out));
"""
        r = run_node(code)
        self.assertEqual(r["first"]["status"], "ok")
        self.assertEqual(r["first"]["args"]["confirm_token"], "aaaa1111")
        self.assertEqual(r["second"]["callId"], "c2", "ตัวแรกมีผลแล้ว = ตัวที่รอคือตัวที่สอง")
        self.assertEqual(r["second"]["args"]["confirm_token"], "bbbb2222")
        self.assertIsNone(r["none"], "ทุกตัวมีผลแล้ว = ไม่มีคำขอค้าง")
        self.assertEqual(r["third"]["callId"], "c3", "สองตัวแรกมีผลแล้ว = รอตัวที่สาม")
        self.assertEqual(r["third"]["args"]["confirm_token"], "cccc3333")
        for k in ("skipped", "swapped", "extra", "dupIds", "dupFirst", "emptyIds", "noId", "numId", "nullCall", "notArray"):
            self.assertIsNone(r[k], k)
        self.assertIsNone(r["mismatch"], "ชื่อไม่ตรงกับการ์ด = ไม่เดา")
        self.assertEqual(r["bad"]["status"], "badargs")
        self.assertEqual(r["arr"]["status"], "badargs")
        self.assertEqual(r["empty"]["status"], "ok")
        self.assertEqual(r["empty"]["args"], {})
        self.assertEqual(r["obj"]["args"]["review"], "r")
        # คีย์ซ้ำ: JSON.parse (ทั้ง WebUI และ json.loads ของเซิร์ฟเวอร์) ใช้ตัวท้าย — กล่องต้องโชว์ตัวเดียวกับที่ถูกส่ง
        self.assertEqual(r["dup"]["args"]["review"], "sent")
        self.assertIsNone(r["noCalls"])
        self.assertIsNone(r["junk"])

    def test_confirm_call_from_db_read_only(self):
        code = r"""
var log = {closed: 0, aborted: 0, modes: []};
function later(f) { setTimeout(f, 1); }
function makeDb(stores) {
  return {
    objectStoreNames: {contains: function (n) { return Object.prototype.hasOwnProperty.call(stores, n); }},
    close: function () { log.closed++; },
    transaction: function (names, mode) {
      log.modes.push(mode);
      return {objectStore: function (n) { return {get: function (id) {
        // เหมือน IndexedDB จริง: key ผิดชนิด = DataError โยนทันที (ไม่ใช่ onerror)
        if (typeof id !== "string") throw new Error("DataError: invalid key");
        var r = {}; later(function () { r.result = stores[n][id]; r.onsuccess && r.onsuccess(); }); return r; }}; }};
    }
  };
}
function fakeIdb(db) {
  return {open: function (name, ver) {
    log.name = name; log.ver = ver;
    var req = {};
    later(function () {
      if (!db) {
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
function call(id, args) { return {id: id, type: "function", function: {name: "local_confirm", arguments: JSON.stringify(args)}}; }
var calls = JSON.stringify([call("c0", {confirm_token: "deadbeef", review: "decoy"}), call("c1", {confirm_token: "7c0ffee1", review: "real"})]);
var calls3 = JSON.stringify([call("k0", {confirm_token: "aaaa0000"}), call("k1", {confirm_token: "bbbb1111"}),
                             call("k2", {confirm_token: "cccc2222"})]);
var dup3 = JSON.stringify([call("d", {confirm_token: "aaaa0000"}), call("d", {confirm_token: "bbbb1111"}),
                           call("d3", {confirm_token: "cccc2222"})]);
// รูปต้นไม้แบบที่ WebUI b10410 สร้างจริง: ผลของเครื่องมือทุกตัวในเทิร์นเดียว = ลูกของข้อความผู้ช่วย (createToolResultMessage
// ใช้ parent = ผู้ช่วย) ต่อท้าย children ตามลำดับ, currNode = ผลล่าสุด (ยังไม่มีผล = currNode คือผู้ช่วย)
var msgs = {
  u: {id: "u", role: "user", parent: "r", children: ["a", "a0", "a3", "d3a"]},
  a: {id: "a", role: "assistant", parent: "u", toolCalls: calls, children: ["t0"]},
  a0: {id: "a0", role: "assistant", parent: "u", toolCalls: calls, children: []},
  t0: {id: "t0", role: "tool", parent: "a", toolCallId: "c0", children: ["plain"]},
  plain: {id: "plain", role: "assistant", parent: "t0", toolCalls: "", children: []},
  loop: {id: "loop", role: "tool", parent: "loop", toolCallId: "x"},
  // สามการเรียก: ตัวที่ 1, 2 ถูกปฏิเสธ (ผลเป็นพี่น้องกัน) → การ์ดของตัวที่ 3 (แบบเดิมโชว์ของตัวที่ 1 ที่ยังค้าง)
  a3: {id: "a3", role: "assistant", parent: "u", toolCalls: calls3, children: ["s0", "s1"]},
  s0: {id: "s0", role: "tool", parent: "a3", toolCallId: "k0", children: []},
  s1: {id: "s1", role: "tool", parent: "a3", toolCallId: "k1", children: []},
  // id ซ้ำ: ผลของ "d" ตัวแรกบันทึกแล้ว → การ์ดของ "d" ตัวที่สอง (แบบเดิมโชว์ของ d3)
  d3a: {id: "d3a", role: "assistant", parent: "u", toolCalls: dup3, children: ["e0"]},
  e0: {id: "e0", role: "tool", parent: "d3a", toolCallId: "d", children: []},
  // currNode ไม่ใช่ลูกตัวท้าย / ลูกที่ไม่ใช่ผลเครื่องมือ / ลำดับผลสลับ / ผู้ช่วยมีลูกแต่ currNode อยู่ที่ผู้ช่วย
  b: {id: "b", role: "assistant", parent: "u", toolCalls: calls3, children: ["b0", "b1"]},
  b0: {id: "b0", role: "tool", parent: "b", toolCallId: "k0", children: []},
  b1: {id: "b1", role: "tool", parent: "b", toolCallId: "k1", children: []},
  n: {id: "n", role: "assistant", parent: "u", toolCalls: calls3, children: ["nu", "n0"]},
  n0: {id: "n0", role: "tool", parent: "n", toolCallId: "k0", children: []},
  nu: {id: "nu", role: "user", parent: "n", children: []},
  w: {id: "w", role: "assistant", parent: "u", toolCalls: calls3, children: ["w1", "w0"]},
  w1: {id: "w1", role: "tool", parent: "w", toolCallId: "k1", children: []},
  w0: {id: "w0", role: "tool", parent: "w", toolCallId: "k0", children: []},
  // ผลอ้าง parent เป็นผู้ช่วยอื่น (ข้อมูลเพี้ยน) = ไม่นับ
  x: {id: "x", role: "assistant", parent: "u", toolCalls: calls3, children: ["x0", "x1"]},
  x0: {id: "x0", role: "tool", parent: "a3", toolCallId: "k0", children: []},
  x1: {id: "x1", role: "tool", parent: "x", toolCallId: "k1", children: []},
  // parent/children ผิดชนิด (ms.get โยน) = อ่านไม่ได้ทันที ไม่ค้างจนหมดเวลา 3 วิ
  q0: {id: "q0", role: "tool", parent: {bad: 1}, toolCallId: "k0", children: []},
  y: {id: "y", role: "assistant", parent: "u", toolCalls: calls3, children: [{bad: 1}, "y1"]},
  y1: {id: "y1", role: "tool", parent: "y", toolCallId: "k1", children: []}
};
var stores = {conversations: {c1: {id: "c1", currNode: "t0"}, c2: {id: "c2", currNode: "a0"}, c3: {id: "c3", currNode: "plain"},
                              c4: {id: "c4", currNode: "loop"}, c5: {id: "c5", currNode: "s1"}, c6: {id: "c6", currNode: "e0"},
                              c7: {id: "c7", currNode: "b0"}, c8: {id: "c8", currNode: "b"}, c9: {id: "c9", currNode: "n0"},
                              c10: {id: "c10", currNode: "w0"}, c11: {id: "c11", currNode: "x1"},
                              c12: {id: "c12", currNode: "q0"}, c13: {id: "c13", currNode: "y1"}}, messages: msgs};
var window = {}, indexedDB;
""" + self.r4 + r"""
(async function () {
  var out = {};
  window.indexedDB = indexedDB = fakeIdb(makeDb(stores));
  out.afterFirst = await confirmCallFromDb("c1", "local_confirm");
  out.atAssistant = await confirmCallFromDb("c2", "local_confirm");
  out.plain = await confirmCallFromDb("c3", "local_confirm");
  out.loop = await confirmCallFromDb("c4", "local_confirm");
  out.third = await confirmCallFromDb("c5", "local_confirm");
  out.dupIds = await confirmCallFromDb("c6", "local_confirm");
  out.notLastChild = await confirmCallFromDb("c7", "local_confirm");
  out.asstWithKids = await confirmCallFromDb("c8", "local_confirm");
  out.nonToolChild = await confirmCallFromDb("c9", "local_confirm");
  out.swapped = await confirmCallFromDb("c10", "local_confirm");
  out.foreignParent = await confirmCallFromDb("c11", "local_confirm");
  var t0 = Date.now();
  out.badParentKey = await confirmCallFromDb("c12", "local_confirm");
  out.badChildKey = await confirmCallFromDb("c13", "local_confirm");
  out.badKeyMs = Date.now() - t0;
  out.missing = await confirmCallFromDb("nope", "local_confirm");
  out.noId = await confirmCallFromDb(null, "local_confirm");
  window.indexedDB = indexedDB = fakeIdb(null);
  out.noDb = await confirmCallFromDb("c1", "local_confirm");
  out.log = log;
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""
        r = run_node(code)
        self.assertEqual(r["afterFirst"]["status"], "ok")
        self.assertEqual(r["afterFirst"]["args"]["review"], "real", "ผลของ c0 บันทึกแล้ว = รอ c1")
        self.assertEqual(r["atAssistant"]["args"]["review"], "decoy", "ยังไม่มีผลใดเลย = รอตัวแรก")
        self.assertEqual(r["third"]["status"], "ok")
        self.assertEqual(r["third"]["callId"], "k2", "ผลสองตัวเป็นพี่น้องกัน = รอตัวที่สาม (ไม่ใช่ตัวแรกที่ถูกปฏิเสธ)")
        self.assertEqual(r["third"]["args"]["confirm_token"], "cccc2222")
        for k in ("plain", "loop", "dupIds", "notLastChild", "asstWithKids", "nonToolChild", "swapped", "foreignParent",
                  "badParentKey", "badChildKey", "missing", "noId", "noDb"):
            self.assertEqual(r[k]["status"], "unknown", k)
        self.assertLess(r["badKeyMs"], 1500, "key ผิดชนิด = จบทันที ไม่รอหมดเวลา 3 วิ")
        lg = r["log"]
        self.assertEqual(lg["name"], "LlamaUi")
        self.assertIsNone(lg.get("ver"))
        self.assertEqual(set(lg["modes"]), {"readonly"})
        self.assertEqual(lg["aborted"], 1, "ไม่มีฐานข้อมูล = ยกเลิก ไม่สร้างฐานว่าง")
        self.assertEqual(lg["closed"], 14, "ปิดการเชื่อมต่อทุกครั้งที่เปิดสำเร็จ")
        for bad in ('"readwrite"', "deleteDatabase", "createObjectStore", ".put(", ".delete(", ".clear("):
            self.assertNotIn(bad, self.r4, bad)

    def test_render_escapes_and_marks(self):
        code = DOM_STUB + self.r4 + r"""
function line(s) { var p = el("span"); var n = rvAppend(p, s); return {n: n, k: kinds(p), text: p.textContent}; }
var out = {
  bidi: line('if x != "user\u202E \u2066# admin\u2069 \u2066":'),
  zw: line("ad\u200Bmin = \uFEFFTrue\u00AD"),
  nbsp: line("a\u00A0b\u3000c"),
  tag: line("x\uDB40\uDC41y"),
  lone: line("a\uD800b"),
  cr: line("a\rb"),
  plain: line("\tif ok:  ประมวลผล 😀 é → «done»"),
  server: line('x«U+202E»y«TAB»z«180 spaces»w'),
  wrap: line("abc↩"),
  cont: line("↪def"),
  spaces: line("x = 1" + new Array(41).join(" ") + "import os")
};
var c = rvCode("⚠ คำเตือน (WARNING): พบ\n[python]\n 1│ a = 1\n12│ b = 2\n↪  ต่อ\n--- a/f\n+++ b/f\n@@ -1,2 +1,2 @@\n-old\n+new\n ctx");
out.code = {text: c.node.textContent, lines: c.lines, hidden: c.hidden, attrs: c.node.attrs,
  cls: c.node.children.map(function (l) { return l.className; }),
  ln: c.node.children[2].children[0].className + "|" + c.node.children[2].children[0].textContent};
console.log(JSON.stringify(out));
"""
        r = run_node(code)
        b = r["bidi"]
        self.assertEqual(b["n"], 4)
        self.assertEqual(b["text"], 'if x != "user«U+202E» «U+2066»# admin«U+2069» «U+2066»":')
        self.assertIn(["qw-rv-esc", "«U+202E»", "U+202E RIGHT-TO-LEFT OVERRIDE"], b["k"])
        self.assertEqual(r["zw"]["text"], "ad«U+200B»min = «U+FEFF»True«U+00AD»")
        self.assertEqual(r["nbsp"]["text"], "a«U+00A0»b«U+3000»c")
        self.assertEqual(r["tag"]["text"], "x«U+E0041»y")
        self.assertEqual(r["lone"]["text"], "a«U+D800»b")
        self.assertEqual(r["cr"]["text"], "a«U+000D»b", "\\r เดี่ยว = ขึ้นบรรทัดที่ตาไม่เห็น")
        self.assertEqual(r["plain"]["n"], 0, "tab/ไทย/อีโมจิ/อักษรทั่วไปไม่ใช่อักขระซ่อน")
        self.assertEqual(r["plain"]["text"], "\tif ok:  ประมวลผล 😀 é → «done»")
        s = r["server"]
        self.assertEqual(s["n"], 1, "«U+…» ของเซิร์ฟเวอร์นับเป็นอักขระซ่อน")
        self.assertEqual(s["text"], "x«U+202E»y«TAB»z«180 spaces»w", "ข้อความของเซิร์ฟเวอร์ต้องไม่ถูกเปลี่ยนแม้ตัวเดียว")
        self.assertIn(["qw-rv-mark", "«TAB»", ""], s["k"])
        self.assertIn(["qw-rv-mark", "«180 spaces»", ""], s["k"])
        self.assertIn(["qw-rv-wrap", "↩", ""], r["wrap"]["k"])
        self.assertIn(["qw-rv-wrap", "↪", ""], r["cont"]["k"])
        self.assertTrue(any(k[0] == "qw-rv-ws" for k in r["spaces"]["k"]), "ช่องว่างยาวดิบถูกระบาย")
        self.assertEqual(r["spaces"]["text"], "x = 1" + " " * 40 + "import os")
        c = r["code"]
        self.assertEqual(c["text"], "⚠ คำเตือน (WARNING): พบ\n[python]\n 1│ a = 1\n12│ b = 2\n↪  ต่อ\n--- a/f\n+++ b/f\n"
                                    "@@ -1,2 +1,2 @@\n-old\n+new\n ctx", "แสดงครบทุกตัวอักษร ไม่ตัด")
        self.assertEqual(c["attrs"].get("data-qw-no-tx"), "", "ตัวแปลห้ามแตะเนื้อหา")
        self.assertEqual(c["attrs"].get("tabindex"), "0")
        cls = c["cls"]
        self.assertIn("qw-rv-warnline", cls[0])
        self.assertIn("qw-rv-cont", cls[4])
        self.assertNotIn("qw-rv-del", cls[5], "หัว --- ไม่ใช่บรรทัดลบ")
        self.assertNotIn("qw-rv-add", cls[6], "หัว +++ ไม่ใช่บรรทัดเพิ่ม")
        self.assertIn("qw-rv-hunk", cls[7])
        self.assertIn("qw-rv-del", cls[8])
        self.assertIn("qw-rv-add", cls[9])
        self.assertEqual(c["lines"], 10, "บรรทัดต่อ (↪) ไม่นับเป็นบรรทัดใหม่")
        self.assertEqual(c["ln"], "qw-rv-ln| 1│ ")

    def test_integration_points(self):
        src = self.src
        # การ์ดอ่านแค่แถวข้อความ/แถวปุ่ม (ข้อความในกล่องตรวจทานเปลี่ยนชนิดการ์ดไม่ได้)
        pi = js_block(src, src.index("\n  function promptInfo(") + 1)
        self.assertNotIn("enText(card)", pi)
        self.assertIn("kids[0]", pi)
        self.assertIn("try { confirmCards(); }", src)
        self.assertIn('var CONFIRM_TOOL = "local_confirm";', src)
        # ไม่มี innerHTML จากข้อมูล — ข้อความจากโมเดลเข้าผ่าน text node เท่านั้น
        for ln in self.r4.splitlines():
            if "innerHTML" in ln:
                self.assertRegex(ln, r"innerHTML = xIcon\(")
        for bad in ("fetch(", "XMLHttpRequest", "http://", "https://", "eval(", "Claude", "Anthropic"):
            self.assertNotIn(bad, self.r4, bad)

    def test_css(self):
        a = self.css.index("11. รอบ 5")
        sec = self.css[a:]
        for sel in (".qw-review", ".qw-review-head", ".qw-review-note[data-kind=\"danger\"]", "pre.qw-review-code",
                    ".qw-rv-esc", ".qw-rv-mark", ".qw-rv-wrap", ".qw-rv-warnline", ".qw-rv-add", ".qw-rv-del",
                    "focus-visible", "@media (max-width: 640px)"):
            self.assertIn(sel, sec, sel)
        self.assertNotRegex(sec, r"#[0-9a-fA-F]{3,8}\b", "ใช้ token ไม่ใช่สีตายตัว")
        self.assertNotRegex(sec, r"rgba?\(", "ใช้ token ไม่ใช่สีตายตัว")
        pre = sec[sec.index("html:root pre.qw-review-code {"):]
        pre = pre[:pre.index("}")]
        self.assertIn("overflow: auto", pre)
        self.assertIn("white-space: break-spaces", pre, "ห้ามซ่อนส่วนเกินไว้นอกขอบขวา")
        self.assertIn("overflow-wrap: anywhere", pre)
        self.assertIn("font-family: var(--qw-font-mono)", pre)
        line = sec[sec.index("html:root pre.qw-review-code .qw-rv-l {"):]
        line = line[:line.index("}")]
        self.assertIn("unicode-bidi: bidi-override", line, "แสดงตามลำดับจริงจากซ้ายไปขวา")
        # การ์ด local_confirm: ไม่มีทางลัด "อนุญาตเสมอ"
        self.assertIn('.qw-confirm-card button[aria-label="More allow options"]', sec)
        self.assertNotIn("white-space: nowrap", pre)


if __name__ == "__main__":
    unittest.main()
