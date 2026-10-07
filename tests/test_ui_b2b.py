# -*- coding: utf-8 -*-
"""
เทสต์ของ batch 2b สัญญา C4 (owner ui): ไมค์ (พูดแทนพิมพ์), "วางแผนก่อน", @ไฟล์ของโปรเจกต์, ทางลัด Office,
สวิตช์ "ค้นเอกสารของโปรเจกต์อัตโนมัติ" ในแผงโปรเจกต์ และแถว "พูดแทนพิมพ์" ในก้อนบริการ

ส่วนที่ 1 — รันเสมอ (ไม่เปิดเบราว์เซอร์/hub):
  * webui-enhance.js: node --check, ส่วน batch 2b อยู่หลังออบเจกต์ API (นอกช่วงที่เทสต์รอบ 4/5 ห้ามเรียกเครือข่าย)
    และต่อเข้ากับ extrasPass()/observer ของ body
  * ป้ายทุกคำของส่วนใหม่มีคำแปลไทย (พจนานุกรม TH_B2B แยกจาก TH ของตัวแปล — "Output" ของ WebUI แปลคนละความหมาย)
  * เครือข่าย: เรียกได้เฉพาะเส้นทางของ hub บน origin เดียวกัน (/_qwen/stt, /_qwen/files, /_qwen/out/) ไม่มี URL ภายนอก
    innerHTML ใช้กับไอคอนคงที่เท่านั้น
  * ฟังก์ชันล้วนรันจริงใน Node: ติด X-Qwen-Plan เฉพาะ POST ของ /v1/chat/completions origin เดียวกันในแชตที่เปิดโหมด,
    อ่าน id แชตจาก X-Conversation-Id, โทเค็น @, จัดอันดับไฟล์, นาฬิกา, แปลงสถานะ HTTP ของ STT
  * CSS ส่วน 12 มีชิ้นใหม่ครบ ใช้ token ไม่มีสีตายตัว มีวงโฟกัส + reduced-motion + container query ของกล่องพิมพ์แคบ
  * hub_i18n_parts.py: สวิตช์ auto_kb (role=switch), ตรวจค่าที่ PATCH ตอบกลับ, services() ใน qwenShellApi,
    แถว stt ในก้อนบริการ, ข้อความใหม่ครบสองภาษา
ตรวจไฟล์สำเนาก่อนติดตั้งได้: QWEN_ENH_FILE, QWEN_THEME_FILE, QWEN_PARTS_FILE, QWEN_STATIC_DIR (E2E)

ส่วนที่ 2 — E2E (ปิดไว้เป็นค่าเริ่มต้น: set QWEN_UI_E2E=1, ต้องมี Edge + router 8099 ที่รันอยู่):
  hub สำเนาใน process นี้บนพอร์ตว่างใน 8174-8177 (API + พอร์ตโปรเจกต์) ข้อมูลอยู่ในโฟลเดอร์ชั่วคราวทั้งหมด,
  upstream ปลอม: GET ส่งต่อไป router (หน้า WebUI) แต่ GET ที่มี model= ถูกบล็อก (router โหลดโมเดลให้เองถ้าส่งไป),
  คำขอแชตตอบเองด้วย SSE ปลอม (ไม่ถึงโมเดลจริง), POST อื่น 403 · MCP ปิด · ไมค์ = อุปกรณ์ปลอมของ Chromium และ
  POST /_qwen/stt ถูกตอบในเบราว์เซอร์ด้วย CDP Fetch (ไม่แตะพอร์ต 8795 ของบริการจริง)
  QWEN_UI_WEBUI_DIR=<โฟลเดอร์> (resume 2026-10-06): ใช้หน้า WebUI ที่เก็บจาก llama-server จริงแทนการส่งต่อไป router
  (index.html, bundle.*.js/css, props.json, models.json, v1_models.json, health.json) — รัน E2E ได้แม้บริการจริงปิดอยู่
  (หลังรีบูต) และไม่ต้องเปิด llama-server ตัวทดสอบไปแย่งพอร์ต 8199 กับ gpu_bench
"""
import base64
import http.client
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

ENH = os.environ.get("QWEN_ENH_FILE") or r"C:\LLM\projects\static\webui-enhance.js"
CSS = os.environ.get("QWEN_THEME_FILE") or r"C:\LLM\projects\static\webui-theme.css"
PARTS = os.environ.get("QWEN_PARTS_FILE") or r"C:\LLM\projects\hub_i18n_parts.py"
STATIC_DIR = os.environ.get("QWEN_STATIC_DIR") or ""
HUB = r"C:\LLM\projects\hub.py"
TOOLS = r"C:\LLM\projects\tools"
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
HAVE_NODE = os.path.isfile(NODE) if os.path.isabs(NODE) else bool(shutil.which("node"))
B2B_START = "batch 2b (2026-10-01, owner ui) — สัญญา C4"
B2B_END = "\n  /* ---- เริ่มทำงาน"
API_START = "  window.qwenEnhance = {"
THAI = re.compile("[\u0E00-\u0E7F]")


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def js_block(src, start):
    """ซอร์สของบล็อก {...} ตัวแรกหลังตำแหน่ง start (นับวงเล็บ ข้ามสตริง/คอมเมนต์/regex อย่างง่าย)"""
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
    """ฟังก์ชันระดับบนของ IIFE (ย่อหน้า 2 ช่อง) — จบที่บรรทัด "  }" แรก ไม่ต้องแยกวิเคราะห์ regex ที่มีเครื่องหมายคำพูดข้างใน"""
    m = re.search(r"\n  function %s\(" % re.escape(name), src)
    if not m:
        raise AssertionError("function %s not found" % name)
    end = src.index("\n  }\n", m.start() + 1)
    return src[m.start() + 1:end + 4]


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


def load_parts():
    spec = importlib.util.spec_from_file_location("hub_i18n_parts_b2b_ui", PARTS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------------------------------------ enhance.js
class EnhanceStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(ENH)
        a = cls.src.index(B2B_START)
        cls.block = cls.src[cls.src.rindex("/*", 0, a):cls.src.index(B2B_END, a)]

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_syntax(self):
        r = subprocess.run([NODE, "--check", ENH], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_position_and_hooks(self):
        s = self.src
        a = s.index(B2B_START)
        # หลังออบเจกต์ API (เทสต์รอบ 4/5 ตัดช่วง "รอบ 4 … /* ---- API ----" ไปตรวจว่าไม่เรียกเครือข่าย) และก่อนส่วนเริ่มทำงาน
        self.assertLess(s.index("/* ---- API ----"), a)
        self.assertLess(s.index(API_START), a)
        self.assertLess(a, s.index(B2B_END))
        ex = js_function(s, "extrasPass")
        self.assertIn("b2bPass(r, st)", ex)
        obs = js_block(s, s.index("var bodyObs = new MutationObserver("))
        self.assertIn("b2bObs(recs)", obs)
        self.assertLess(obs.index("bodyObs.takeRecords()"), obs.index("b2bObs(recs)"))
        # API เพิ่มของส่วนนี้
        for name in ("plan", "setPlan", "dictation", "startDictation", "stopDictation", "cancelDictation", "mention"):
            self.assertIn("window.qwenEnhance.%s = function" % name, self.block)

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_every_label_has_thai(self):
        th = run_node(js_block(self.block, self.block.index("var TH_B2B = {")).replace("var TH_B2B =", "const TH_B2B =", 1)
                      + ";\nconsole.log(JSON.stringify(TH_B2B));")
        used = set(re.findall(r'\b[LA]\(\s*"([^"]+)"\s*\)', self.block))
        errs = js_block(self.block, self.block.index("var MIC_ERR = {"))
        used |= set(re.findall(r':\s*"([^"]+)"', errs))
        self.assertGreater(len(used), 30)
        for en in sorted(used):
            self.assertIn(en, th, "ไม่มีคำแปลไทยของ %r" % en)
            self.assertRegex(th[en], THAI, "คำแปลของ %r ไม่ใช่ภาษาไทย" % en)
            # ตัวแปรในข้อความ ({n} {q} {name}) ต้องอยู่ครบในคำแปล
            for ph in re.findall(r"\{[a-z]+\}", en):
                self.assertIn(ph, th[en], (en, ph))
        # ทุกคำในพจนานุกรมถูกใช้จริง (ป้ายที่เลือกด้วยเงื่อนไข เช่น "Stop and transcribe" ถูกนับตรงนี้)
        rest = self.block.replace(js_block(self.block, self.block.index("var TH_B2B = {")), "")
        for en in th:
            self.assertIn(json.dumps(en, ensure_ascii=False), rest, "คำ %r ไม่ได้ถูกใช้" % en)
        # พจนานุกรมแยกจาก TH ของตัวแปล — ไม่เขียนใส่ TH (คำซ้ำกับป้ายของ WebUI จะเพี้ยนความหมาย)
        self.assertNotRegex(self.block, r"\bTH\[[^\]]+\]\s*=")
        self.assertIn('hasOwn(TH_B2B, en) ? TH_B2B[en] : en', self.block)

    def test_network_scope_and_safety(self):
        b = self.block
        for bad in ("http://", "https://", "XMLHttpRequest", "WebSocket(", "sendBeacon", "eval(", "Claude", "Anthropic",
                    "insertAdjacentHTML", "document.write"):
            self.assertNotIn(bad, b, bad)
        self.assertIn('STT_URL = "/_qwen/stt"', b)
        self.assertIn('atGet("/_qwen/files", "attachments")', b)
        self.assertIn('atGet("/_qwen/out/", "outputs")', b)
        # ทุกการเรียกเครือข่ายของส่วนนี้ผ่าน nativeFetch (ไม่วนกลับเข้าตัวห่อ) ด้วย credentials same-origin
        # p[0] = ตัวห่อ fetch ส่งคำขอเดิมของ WebUI ต่อ (เพิ่มแค่ header) — ที่เหลือคือ STT และรายชื่อไฟล์
        calls = re.findall(r"nativeFetch\.call\(window, ([^,]+),", b)
        self.assertEqual(sorted(set(calls)), ["STT_URL", "p[0]", "url"])
        self.assertEqual(b.count('credentials: "same-origin"'), 2)
        for line in b.splitlines():
            if ".innerHTML" in line:
                self.assertRegex(line, r"\.innerHTML = xIcon\(", line.strip())
        # อ่าน IndexedDB แบบไม่สร้าง/อัปเกรดฐานของ WebUI
        idb = js_function(b, "convModifiedAt")
        self.assertIn("req.transaction.abort()", idb)
        self.assertIn('"readonly"', idb)
        self.assertNotRegex(idb, r"\.(put|add|delete|clear)\(")

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_plan_request_pure(self):
        fns = "\n".join(js_function(self.block, n) for n in ("planConv", "planRequest"))
        code = r"""
var location = {href: "http://127.0.0.1:8103/?ui=1", origin: "http://127.0.0.1:8103"};
var PLAN_HEADER = "X-Qwen-Plan", ON = {"c1": 1}, PRE = false, seen = [];
function planFor(conv) { seen.push(conv); return conv ? !!ON[conv] : PRE; }
""" + fns + r"""
function hdrs(p) { return p ? Object.fromEntries(new Headers(p[1].headers)) : null; }
var out = {};
out.conv = [planConv("c1::Qwen3-4B"), planConv("abc"), planConv(""), planConv(null), planConv(" x ::m::n")];
var base = {method: "POST", body: "{}", headers: {"Content-Type": "application/json", "X-Conversation-Id": "c1::m"}};
var p = planRequest("./v1/chat/completions", base);
out.on = hdrs(p);
out.bodyKept = p && p[1].body === "{}" && p[1].method === "POST";
out.origUntouched = !("X-Qwen-Plan" in base.headers) && !base.headers["x-qwen-plan"];
out.off = planRequest("./v1/chat/completions", Object.assign({}, base, {headers: {"X-Conversation-Id": "c2::m"}}));
out.get = planRequest("./v1/chat/completions", {headers: {"X-Conversation-Id": "c1::m"}});
out.control = planRequest("./v1/chat/completions/control", base);
out.other = planRequest("/v1/completions", base);
out.cross = planRequest("http://evil.example/v1/chat/completions", base);
out.otherPort = planRequest("http://127.0.0.1:8104/v1/chat/completions", base);
out.abs = hdrs(planRequest("http://127.0.0.1:8103/v1/chat/completions", base));
out.arr = hdrs(planRequest("./v1/chat/completions", {method: "post", headers: [["X-Conversation-Id", "c1::m"], ["A", "b"]]}));
PRE = true;
out.preEncode = hdrs(planRequest("./v1/chat/completions", {method: "POST", headers: {"Content-Type": "application/json"}}));
out.req = hdrs(planRequest(new Request("http://127.0.0.1:8103/v1/chat/completions",
  {method: "POST", body: "{}", headers: {"X-Conversation-Id": "c1::m"}})));
out.nonStr = planRequest(12345, base);
out.seen = seen;
console.log(JSON.stringify(out));
"""
        r = run_node(code)
        self.assertEqual(r["conv"], ["c1", "abc", "", "", "x"])
        self.assertEqual(r["on"]["x-qwen-plan"], "1")
        self.assertEqual(r["on"]["x-conversation-id"], "c1::m")
        self.assertEqual(r["on"]["content-type"], "application/json")
        self.assertTrue(r["bodyKept"])
        self.assertTrue(r["origUntouched"], "ต้องไม่แก้ออบเจกต์ header ของ WebUI เอง")
        for k in ("off", "get", "control", "other", "cross", "otherPort", "nonStr"):
            self.assertIsNone(r[k], k)
        self.assertEqual(r["abs"]["x-qwen-plan"], "1")
        self.assertEqual(r["arr"], {"x-conversation-id": "c1::m", "a": "b", "x-qwen-plan": "1"})
        self.assertEqual(r["preEncode"]["x-qwen-plan"], "1")
        self.assertEqual(r["req"]["x-qwen-plan"], "1")
        # ตัดสินจาก id ในคำขอ ("" = ไม่มี id → ดูแชตที่เปิดอยู่)
        self.assertEqual(r["seen"][:2], ["c1", "c2"])

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_mention_and_mic_helpers_pure(self):
        fns = "\n".join(js_function(self.block, n) for n in ("atToken", "atRank", "fmtBytes", "fmtClock", "sttWhy"))
        code = "var AT_HEAD = 400, AT_MAX = 8;\n" + fns + r"""
function ta(v, pos, end) { return {value: v, selectionStart: pos == null ? v.length : pos, selectionEnd: end == null ? (pos == null ? v.length : pos) : end}; }
var files = [
  {name: "รายงานตรวจรอบเดือน กันยายน.pdf", where: "attachments", size: 13, mtime: 5},
  {name: "budget-2026.xlsx", where: "attachments", size: 7, mtime: 9},
  {name: "OCPP-1.6J-spec.pdf", where: "attachments", size: 9, mtime: 3},
  {name: "notes.md", where: "attachments", size: 7, mtime: 1},
  {name: "research-2026-10-01-r15f97b.md", where: "outputs", size: 4, mtime: 8},
  {name: "สรุปผลการตรวจ.docx", where: "outputs", size: 4, mtime: 7},
  {name: "my-report.pdf", where: "outputs", size: 4, mtime: 2}
];
function names(a) { return a.map(function (f) { return f.where + "/" + f.name; }); }
var out = {
  t1: atToken(ta("สรุป @ราย")), t2: atToken(ta("@")), t3: atToken(ta("mail a@b.co")), t4: atToken(ta("x @ab cd")),
  t5: atToken(ta("(@not")), t6: atToken(ta("x @ab", 2)), t7: atToken(ta("abc @x", 0, 3)),
  t8: atToken(ta(new Array(500).join("y") + "@q")), t9: atToken(ta(new Array(500).join("y") + " @q")),
  all: names(atRank(files, "")), th: names(atRank(files, "ราย")), pre: names(atRank(files, "re")),
  folder: names(atRank(files, "outputs/")), folderQ: names(atRank(files, "attachments/pdf")),
  upper: names(atRank(files, "OCPP")), none: atRank(files, "zzz"), cap: atRank(new Array(30).fill(files[0]), "").length,
  bytes: [fmtBytes(0), fmtBytes(900), fmtBytes(2048), fmtBytes(15 * 1048576)],
  clock: [fmtClock(0), fmtClock(7400), fmtClock(61000), fmtClock(179999)],
  why: [404, 405, 413, 415, 422, 429, 409, 502, 503, 504, 500, 400].map(sttWhy)
};
console.log(JSON.stringify(out));
"""
        r = run_node(code)
        self.assertEqual(r["t1"], {"start": 5, "end": 9, "q": "ราย"})
        self.assertEqual(r["t2"], {"start": 0, "end": 1, "q": ""})
        self.assertIsNone(r["t3"], "อีเมลไม่ใช่ @ไฟล์")
        self.assertIsNone(r["t4"], "เคอร์เซอร์ไม่ได้อยู่ท้ายโทเค็น")
        self.assertEqual(r["t5"]["q"], "not")
        self.assertIsNone(r["t6"])
        self.assertIsNone(r["t7"], "มีข้อความถูกเลือกอยู่")
        self.assertIsNone(r["t8"], "ข้อความยาวที่ตัดกลางคำต้องไม่นับเป็นต้นข้อความ")
        self.assertEqual(r["t9"]["q"], "q")
        # ไม่มีคำค้น = ทั้งหมด ใหม่ก่อน
        self.assertEqual(r["all"][0], "attachments/budget-2026.xlsx")
        self.assertEqual(len(r["all"]), 7)
        self.assertEqual(r["th"], ["attachments/รายงานตรวจรอบเดือน กันยายน.pdf"])
        # ขึ้นต้นด้วยคำค้นมาก่อน "มีอยู่กลางชื่อ" (my-report.pdf มี "re" หลังขีด = ต้นคำ อันดับ 2)
        self.assertEqual(r["pre"][0], "outputs/research-2026-10-01-r15f97b.md")
        self.assertIn("outputs/my-report.pdf", r["pre"])
        self.assertEqual(r["folder"], ["outputs/research-2026-10-01-r15f97b.md", "outputs/สรุปผลการตรวจ.docx",
                                       "outputs/my-report.pdf"])
        self.assertEqual(r["folderQ"], ["attachments/รายงานตรวจรอบเดือน กันยายน.pdf", "attachments/OCPP-1.6J-spec.pdf"])
        self.assertEqual(r["upper"], ["attachments/OCPP-1.6J-spec.pdf"])
        self.assertEqual(r["none"], [])
        self.assertEqual(r["cap"], 8)
        self.assertEqual(r["bytes"], ["0 B", "900 B", "2.0 KB", "15 MB"])
        self.assertEqual(r["clock"], ["0:00", "0:07", "1:01", "2:59"])
        self.assertEqual(r["why"], ["nohub", "nohub", "big", "format", "format", "busy", "busy", "down", "down", "down",
                                    "server", "server"])

    def test_office_chip_and_mic_contract(self):
        s = self.src
        # ชิป Office บนหน้าเริ่มแชตทั้งสองภาษา + คำอธิบาย (title) ว่าการเขียนกลับต้องอนุญาต
        self.assertEqual(len(re.findall(r'\["office", "Office", "', s)), 2)
        self.assertIn("อ่านข้อมูลที่เลือกไว้ใน Excel ที่เปิดอยู่ แล้ว", s)
        self.assertIn("writing back always asks for your approval", s)
        self.assertIn("if (c[3]) b.title = c[3];", s)
        self.assertIn("office:", js_block(s, s.index("var ICON = {")))
        b = self.block
        # ปิดไมค์ทันทีที่หยุด/ยกเลิก และไม่เก็บเสียงไว้ที่ไหน
        self.assertIn("t.stop()", js_function(b, "micStopTracks"))
        for fn in ("micRelease", "micCancel"):
            self.assertIn("micStopTracks(MIC.stream)" if fn == "micRelease" else "micRelease()", js_function(b, fn))
        self.assertNotRegex(b, r"localStorage\.setItem|lsSet\((?!PLAN_KEY)")
        self.assertIn("MIC_MAX_MS = 180000", b)
        # Esc ของเราไม่ไปแย่งหน้าต่าง/เมนูของ WebUI และไม่ตอบสนองต่อ Escape ที่เราส่งให้ตัวเลือก @ ของ WebUI เอง
        self.assertIn("dialogOpen() || plusLayerOpen() || menuOpen()", b)
        self.assertEqual(b.count("mentionClosing"), 6)


# ------------------------------------------------------------------------------------------------ theme.css
class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        css = read(CSS)
        a = css.index("12. batch 2b (2026-10-01, owner ui)")
        cls.sec = css[css.rindex("/*", 0, a):]

    def test_pieces_present(self):
        for sel in (".qw-plan", '.qw-plan[aria-pressed="true"]', ".qw-plan-bar", ".qw-plan-bar-acts", ".qw-plan-go",
                    ".qw-plan-bar-btn[hidden]", ".qw-mic-box", ".qw-mic", '.qw-mic-box[data-state="rec"] .qw-mic',
                    '.qw-mic-box[data-state="off"] .qw-mic', ".qw-rec", ".qw-rec[hidden]", ".qw-rec-x",
                    ".qw-mic-hint", ".qw-mic-hint[hidden]", ".qw-at", ".qw-at[hidden]", '.qw-at-o[aria-selected="true"]',
                    ".qw-at-empty", ".qw-at-add", "[data-qw-webui-mention]", ":focus-visible", "@container",
                    "prefers-reduced-motion", "pointer: coarse"):
            self.assertIn(sel, self.sec, sel)

    def test_tokens_only(self):
        self.assertNotRegex(self.sec, r"#[0-9a-fA-F]{3,8}\b", "ใช้ token ไม่ใช่สีตายตัว")
        self.assertNotRegex(self.sec, r"rgba?\(")
        # ตัวอักษรบนพื้นส้มทึบไม่ผ่าน AA — ปุ่มที่มีข้อความต้องไม่ใช้ --qw-accent เป็นพื้น
        for rule in re.findall(r"\.qw-(?:plan-bar-btn|plan-go|at-add)[^{]*\{([^}]*)\}", self.sec):
            self.assertNotRegex(rule, r"background:\s*var\(--qw-accent\)")


# ------------------------------------------------------------------------------------------------ shell
class ShellTests(unittest.TestCase):
    NEW = ("autokb", "autokb_hint", "autokb_on", "autokb_off", "autokb_unsupported", "errautokb", "svc_stt",
           "svc_stt_dev", "svc_stt_hint")

    @classmethod
    def setUpClass(cls):
        cls.parts = load_parts()
        cls.shell = cls.parts.SHELL

    def test_strings(self):
        th, en = self.parts.STRINGS_UI["th"], self.parts.STRINGS_UI["en"]
        for k in self.NEW:
            self.assertRegex(th[k], THAI, k)
            self.assertTrue(en[k].strip(), k)
            self.assertNotRegex(en[k], THAI, k)
        self.assertEqual(th["autokb"], "ค้นเอกสารของโปรเจกต์อัตโนมัติ")
        self.assertIn("%s", th["svc_stt_dev"])
        self.assertIn("%s", en["svc_stt_dev"])

    def test_switch_markup(self):
        m = re.search(r'<button type="button" class="switch" id="ppAkb"[^>]*>', self.shell)
        self.assertTrue(m)
        for a in ('role="switch"', 'aria-labelledby="ppAkbL"', 'aria-describedby="ppAkbH"', 'aria-checked='):
            self.assertIn(a, m.group(0))
        self.assertIn('id="ppAkbL">__T_autokb__</span>', self.shell)
        # อยู่ในส่วนไฟล์ความรู้ (ก่อนส่วนไฟล์ที่ Qwen สร้าง)
        self.assertLess(self.shell.index('id="ppKnow"'), self.shell.index('id="ppAkb"'))
        self.assertLess(self.shell.index('id="ppAkb"'), self.shell.index('id="ppOut"'))

    def test_switch_logic(self):
        s = self.shell
        a = s.index("var ppAkb = $('#ppAkb')")
        code = s[a:s.index("\n});", a)]
        self.assertIn("AKB_KEYS = ['auto_kb', 'auto_knowledge']", code)
        # hub ที่ไม่รู้จักฟิลด์ตอบ 200 แต่ไม่มีค่า — ต้องไม่หลอกว่าเปลี่ยนแล้ว
        self.assertIn("hit[k] !== want", code)
        self.assertIn("t('autokb_unsupported')", code)
        self.assertIn("patchProject(PROJ.slug, data)", code)
        self.assertIn("if (!akbBusy) setAttr(ppAkb, 'aria-checked', autoKbOn() ? 'true' : 'false');", s)

    def test_services(self):
        s = self.shell
        api = re.search(r"window\.qwenShellApi = \{(.*?)\n\};", s, re.S).group(1)
        self.assertRegex(api, r"\n  services: function \(\)")
        self.assertIn("JSON.parse(JSON.stringify(SVC))", api)
        node = js_block(s, s.index("function svcNode()"))
        self.assertIn("var v = s.stt;", node)
        self.assertIn("t('svc_stt')", node)
        self.assertNotIn("innerHTML", node)


@unittest.skipUnless(os.path.isfile(HUB), "ไม่มี hub.py")
class ShellRenderTests(unittest.TestCase):
    """หน้า shell ที่ hub สร้างจริง (ใช้ hub_i18n_parts.py ที่ติดตั้งอยู่) — ไม่มี placeholder ค้างและเป็นภาษาที่ขอ"""

    def test_render_both_languages(self):
        sys.path.insert(0, os.path.dirname(HUB))
        spec = importlib.util.spec_from_file_location("hub_ui_b2b_render", HUB)
        hub = importlib.util.module_from_spec(spec)
        tmp = tempfile.gettempdir()
        with mock.patch.object(sys, "argv", ["hub.py"]), \
                mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                             "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
            spec.loader.exec_module(hub)
        if "ppAkb" not in hub.templates()[0]:
            self.skipTest("hub_i18n_parts.py ที่ติดตั้งยังไม่ใช่รุ่นนี้")
        proj = {"slug": "b2btest", "name": "b2btest", "port": 8177, "system_prompt": "", "think": "off", "extend": True}
        with mock.patch.object(hub, "upstream_models", return_value=[]), \
                mock.patch.object(hub, "attach_dir", return_value=Path(tmp)):
            th = hub.build_shell(proj, [proj], lang="th")
            en = hub.build_shell(proj, [proj], lang="en")
        for page, want in ((th, "ค้นเอกสารของโปรเจกต์อัตโนมัติ"), (en, "Search project files automatically")):
            self.assertIn(want, page)
            self.assertNotRegex(page, r"__T_[a-z0-9_]+__")


# ------------------------------------------------------------------------------------------------ E2E
E2E = os.environ.get("QWEN_UI_E2E") == "1"
# หน้า WebUI ที่เก็บไว้ (ไม่ต้องมี router) — ดูหัวไฟล์ ส่วนที่ 2
WEBUI_DIR = os.environ.get("QWEN_UI_WEBUI_DIR") or ""
FAST = "Qwen3-4B-Instruct-2507-Q4_K_M"
STT_TEXT = "ช่วยสรุปรายงานตรวจรอบเดือนให้หน่อย"


def free_ports(n, cands=(8174, 8175, 8176, 8177)):
    out = []
    for p in cands:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", p)) != 0:
                out.append(p)
        if len(out) == n:
            return out
    return None


class _Up(BaseHTTPRequestHandler):
    """upstream ปลอม: GET → router จริง (หน้า WebUI) ยกเว้นมี model= ของโมเดลที่ยังไม่โหลด · แชต = SSE ปลอม · POST อื่น 403"""
    protocol_version = "HTTP/1.1"
    log = []
    loaded = set()

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _captured(self, method):
        """หน้า WebUI จากไฟล์ใน QWEN_UI_WEBUI_DIR — ไม่มี router ไม่มีโมเดลไหนถูกโหลด (/props?model= ตอบค่าคงที่)"""
        u = urlparse(self.path)
        d, base = Path(WEBUI_DIR), os.path.basename(u.path)
        if u.path in ("/", "/index.html") and (d / "index.html").is_file():
            data, ctype = (d / "index.html").read_bytes(), "text/html; charset=utf-8"
        elif u.path.startswith("/_app/immutable/") and base and (d / base).is_file():
            data, ctype = (d / base).read_bytes(), "text/javascript" if base.endswith(".js") else "text/css"
        else:
            name = {"/props": "props", "/v1/models": "v1_models", "/models": "models", "/health": "health"}.get(u.path)
            if not name or not (d / (name + ".json")).is_file():
                self._send(404, {"error": {"code": 404, "message": "Not Found", "type": "not_found_error"}})
                return
            doc = json.loads((d / (name + ".json")).read_text(encoding="utf-8"))
            want = (parse_qs(u.query).get("model") or [""])[0]
            if name == "props" and want:
                doc = {"role": "model", "model_alias": want, "model_path": want + ".gguf",
                       "modalities": {"vision": False, "audio": False},
                       "default_generation_settings": {"n_ctx": 32768, "params": {}},
                       "build_info": doc.get("build_info", "")}
            data, ctype = json.dumps(doc, ensure_ascii=False).encode("utf-8"), "application/json"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(data)

    def _relay(self, method):
        if WEBUI_DIR:
            self._captured(method)
            return
        q = parse_qs(urlparse(self.path).query)
        want = (q.get("model") or [""])[0]
        if want and want not in self.loaded:
            self._send(404, {"error": {"code": 404, "message": "blocked by test"}})
            return
        h = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "connection")}
        c = http.client.HTTPConnection("127.0.0.1", 8099, timeout=60)
        try:
            c.request(method, self.path, headers=h)
            r = c.getresponse()
            data = r.read()
        except OSError:
            self._send(502, {"error": "router"})
            return
        finally:
            c.close()
        self.send_response(r.status)
        for k, v in r.getheaders():
            if k.lower() not in ("content-length", "transfer-encoding", "connection"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(data)

    def do_GET(self):
        self._relay("GET")

    def do_HEAD(self):
        self._relay("HEAD")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if not urlparse(self.path).path.endswith("/chat/completions"):
            self._send(403, {"error": "blocked by test"})
            return
        try:
            doc = json.loads(raw.decode("utf-8"))
        except ValueError:
            doc = {}
        msgs = doc.get("messages") or []
        type(self).log.append({"headers": {k.lower(): v for k, v in self.headers.items() if k.lower() != "authorization"},
                               "system": "\n".join(str(m.get("content")) for m in msgs if m.get("role") == "system"),
                               "tools": [(t.get("function") or {}).get("name") for t in doc.get("tools") or []]})
        if not doc.get("stream"):
            self._send(200, {"choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                                          "finish_reason": "stop"}]})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        for piece in ("แผน: ", "1. อ่าน ", "2. สรุป"):
            ev = {"choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}], "model": doc.get("model")}
            self.wfile.write(("data: %s\n\n" % json.dumps(ev, ensure_ascii=False)).encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.05)
        fin = {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "model": doc.get("model"),
               "timings": {"prompt_n": 5, "prompt_ms": 5.0, "predicted_n": 5, "predicted_ms": 100.0,
                           "predicted_per_second": 50.0}}
        self.wfile.write(("data: %s\n\ndata: [DONE]\n\n" % json.dumps(fin)).encode("utf-8"))
        self.wfile.flush()
        self.close_connection = True


def router_up():
    try:
        with socket.create_connection(("127.0.0.1", 8099), timeout=1):
            return True
    except OSError:
        return False


@unittest.skipUnless(E2E, "E2E ปิดอยู่ (set QWEN_UI_E2E=1)")
class BrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if WEBUI_DIR and not os.path.isfile(os.path.join(WEBUI_DIR, "index.html")):
            raise unittest.SkipTest("QWEN_UI_WEBUI_DIR ไม่มี index.html")
        if not WEBUI_DIR and not router_up():
            raise unittest.SkipTest("router 8099 ไม่ได้รันอยู่ (หน้า WebUI มาจาก router) — หรือ set QWEN_UI_WEBUI_DIR")
        ports = free_ports(2)
        if not ports:
            raise unittest.SkipTest("พอร์ตสำรอง 8174-8177 ว่างไม่พอ")
        cls.api_port, cls.port = ports
        sys.path.insert(0, TOOLS)
        sys.path.insert(0, os.path.dirname(HUB))
        import shot  # noqa: E402
        cls.shot = shot
        spec = importlib.util.spec_from_file_location("hub_ui_b2b_e2e", HUB)
        hub = importlib.util.module_from_spec(spec)
        cls.tmp = tempfile.mkdtemp(prefix="qwen-ui-b2b-")
        with mock.patch.object(sys, "argv", ["hub.py", str(cls.api_port), "8099"]), \
                mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(cls.tmp, "none-profile.json"),
                                             "QWEN_GPU_CHOICE": os.path.join(cls.tmp, "none-choice.json")}):
            spec.loader.exec_module(hub)
        cls.hub = hub
        data = Path(cls.tmp) / "data"
        for sub, names in (("attachments", ("รายงานตรวจรอบเดือน กันยายน.pdf", "budget-2026.xlsx")),
                           ("outputs", ("สรุปผลการตรวจ.docx",))):
            (data / "uitest" / sub).mkdir(parents=True, exist_ok=True)
            for nm in names:
                (data / "uitest" / sub / nm).write_bytes(b"x")
        store = Path(cls.tmp) / "projects.json"
        store.write_text(json.dumps([{"slug": "uitest", "name": "uitest", "port": cls.port, "system_prompt": "",
                                      "think": "off", "model": FAST, "extend": True}]), encoding="utf-8")
        settings = Path(cls.tmp) / "settings.json"
        settings.write_text(json.dumps({"lang": "th", "theme": "dark", "font": "serif"}), encoding="utf-8")
        cls.patches = [mock.patch.object(hub, "DATA_ROOT", data), mock.patch.object(hub, "STORE", store),
                       mock.patch.object(hub, "SETTINGS", settings),
                       mock.patch.object(hub, "mcp_servers", lambda project, with_auth=True: [])]
        if STATIC_DIR:
            cls.patches.append(mock.patch.object(hub, "STATIC_DIR", Path(STATIC_DIR)))
        if hasattr(hub, "stt_probe"):
            cls.patches.append(mock.patch.object(hub, "stt_probe", lambda tok=None: {"state": "ok", "port": 8795,
                                                                                    "device": "cpu"}))
        if hasattr(hub, "_mcp_fast_call"):
            # ค้นเอกสารอัตโนมัติ/แนบไฟล์ @ ของ hub เรียก MCP 8792 ด้วยโทเคนจริง — เทสต์นี้ห้ามแตะบริการจริง
            # (slug ทดสอบ "uitest" ไม่มีใน MCP และไม่ควรมี kb ถูกสร้างให้) จึงตอบ "down" เหมือนบริการปิดอยู่
            cls.patches.append(mock.patch.object(hub, "_mcp_fast_call", lambda *a, **k: ("down", "")))
        for p in cls.patches:
            p.start()
        if os.environ.get("QWEN_PARTS_FILE"):
            # หน้า shell จากไฟล์สำเนา (ทดสอบก่อนติดตั้ง) — templates() ของ hub ใช้โมดูลนี้แทนของจริง
            for p in (mock.patch.object(hub, "_parts", load_parts()),
                      mock.patch.object(hub, "_parts_mtime", Path(PARTS).stat().st_mtime)):
                p.start()
                cls.patches.append(p)
            hub._merge_strings()
        # โมเดลที่โหลดอยู่ (GET /models ไม่มี model= จึงไม่สั่งโหลด) — GET ที่มี model= ของตัวอื่นถูกบล็อก
        try:
            if WEBUI_DIR:
                raise OSError("captured WebUI — ไม่ถาม router")
            c = http.client.HTTPConnection("127.0.0.1", 8099, timeout=10)
            c.request("GET", "/models", headers=hub.router_auth_headers())
            d = json.loads(c.getresponse().read().decode("utf-8"))
            c.close()
            _Up.loaded = {m.get("id") for m in d.get("data") or []
                          if (m.get("status") or {}).get("value") == "loaded"}
        except (OSError, ValueError):
            _Up.loaded = set()
        cls.up = ThreadingHTTPServer(("127.0.0.1", 0), _Up)
        cls.up.daemon_threads = True
        cls.up.handle_error = lambda *a: None          # Edge ปิดซ็อกเก็ตเอง = ConnectionReset ไม่ใช่ความผิดพลาด
        threading.Thread(target=cls.up.serve_forever, daemon=True).start()
        cls.patches.append(mock.patch.object(hub, "UPSTREAM_PORT", cls.up.server_address[1]))
        cls.patches[-1].start()
        cls.proxy = ThreadingHTTPServer(("127.0.0.1", cls.port), hub.make_proxy_handler("uitest", hub.load_projects))
        cls.proxy.daemon_threads = True
        cls.proxy.handle_error = lambda *a: None
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        cls.api = ThreadingHTTPServer(("127.0.0.1", cls.api_port), hub.HubHandler)
        cls.api.daemon_threads = True
        cls.api.handle_error = lambda *a: None
        threading.Thread(target=cls.api.serve_forever, daemon=True).start()
        edge = next((p for p in shot.EDGE_CANDIDATES if os.path.isfile(p)), None)
        if not edge:
            cls._stop_servers()
            raise unittest.SkipTest("ไม่มี Edge")
        cls.dbg = shot.free_port()
        cls.profile = tempfile.mkdtemp(prefix="qwen-shot-")
        cls.proc = subprocess.Popen([edge, "--headless=new", "--disable-gpu", "--no-first-run", "--mute-audio",
                                     "--no-default-browser-check", "--disable-extensions",
                                     "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                                     "--remote-debugging-port=%d" % cls.dbg, "--user-data-dir=%s" % cls.profile,
                                     "--window-size=1440,900", "about:blank"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(100):
            try:
                tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % cls.dbg, timeout=2).read())
                page = next((t for t in tabs if t.get("type") == "page"), None)
                if page:
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except OSError:
                pass
            time.sleep(0.15)
        cls.stt_seen = []

        class WS2(shot.WS):
            """ตอบ POST /_qwen/stt ในเบราว์เซอร์เอง (ไม่มีเสียงไปถึงบริการจริง)"""

            def recv(self_ws):
                txt = shot.WS.recv(self_ws)
                try:
                    msg = json.loads(txt)
                except ValueError:
                    return txt
                if msg.get("method") == "Fetch.requestPaused":
                    p = msg["params"]
                    cls.stt_seen.append(p["request"]["method"])
                    body = base64.b64encode(json.dumps({"text": STT_TEXT, "language": "th", "segments": []},
                                                       ensure_ascii=False).encode("utf-8")).decode()
                    self_ws.next_id += 1
                    self_ws.send(json.dumps({"id": self_ws.next_id, "method": "Fetch.fulfillRequest", "params": {
                        "requestId": p["requestId"], "responseCode": 200, "body": body,
                        "responseHeaders": [{"name": "Content-Type", "value": "application/json"}]}}))
                return txt

        cls.ws = WS2(ws_url)
        cls.ws.call("Fetch.enable", {"patterns": [{"urlPattern": "*/_qwen/stt*", "requestStage": "Request"}]})
        cls.ws.call("Page.enable")
        cls.ws.call("Runtime.enable")
        cls.ws.call("Network.enable")
        cls.ws.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1,
                                                            "mobile": False})
        cls.origin = "http://127.0.0.1:%d" % cls.port
        shot.navigate(cls.ws, cls.origin + "/?lang=th", settle=5.0)

    @classmethod
    def _stop_servers(cls):
        for srv in (getattr(cls, "proxy", None), getattr(cls, "api", None), getattr(cls, "up", None)):
            if srv:
                srv.shutdown()
        for p in reversed(getattr(cls, "patches", [])):
            try:
                p.stop()
            except RuntimeError:
                pass

    @classmethod
    def tearDownClass(cls):
        try:
            cls.shot.close_edge(cls.proc, cls.profile)
        finally:
            cls._stop_servers()

    @classmethod
    def frame(cls, js):
        return cls.shot.evaluate(cls.ws, "(async()=>{const w=document.getElementById('frame').contentWindow;"
                                         "return await w.eval(%s)})()" % json.dumps(js))

    def click(self, sel, inner=True):
        xy = self.shot.evaluate(self.ws, "(()=>{const f=document.getElementById('frame'),o=f.getBoundingClientRect();"
                                         "const d=%s,e=d.querySelector(%s);if(!e)return null;const r=e.getBoundingClientRect();"
                                         "return [r.left+r.width/2+%s,r.top+r.height/2+%s]})()" % (
                                             "f.contentDocument" if inner else "document", json.dumps(sel),
                                             "o.left" if inner else "0", "o.top" if inner else "0"))
        self.assertTrue(xy, sel)
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.ws.call("Input.dispatchMouseEvent", {"type": t, "x": xy[0], "y": xy[1], "button": "left",
                                                     "clickCount": 1})
        self.ws.drain(0.3)

    def type(self, text):
        self.ws.call("Input.insertText", {"text": text})
        self.ws.drain(0.3)

    def key(self, name, code, vk):
        base = {"key": name, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
        self.ws.call("Input.dispatchKeyEvent", dict(base, type="rawKeyDown"))
        self.ws.call("Input.dispatchKeyEvent", dict(base, type="keyUp"))
        self.ws.drain(0.3)

    def composer(self):
        return self.frame("document.querySelector('.chat-screen-form-wrapper form textarea').value")

    def test_1_pieces_present(self):
        self.assertTrue(self.frame("!!document.querySelector('.qw-plan') && !!document.querySelector('.qw-mic')"
                                   " && !!document.querySelector('.qw-chip[data-chip=office]')"))
        want = "ok" if hasattr(self.hub, "stt_probe") else ""
        # ก้อนบริการมาถึง shell ตามรอบ (hub ตรวจทุก ~8 วินาที, shell ถาม /api/projects ทุก ~10 วินาที) — รอบแรกหลังเปิด
        # hub ใหม่ยังเป็น null ได้ จึงรอแทนการอ่านครั้งเดียว (resume 2026-10-06: อ่านครั้งเดียวพลาดเพราะจังหวะ)
        got = None
        for _ in range(100):
            got = self.frame("qwenEnhance.dictation().service")
            if got == want:
                break
            self.ws.drain(0.25)
        self.assertEqual(got, want)

    def test_2_mention_picker(self):
        self.click(".chat-screen-form-wrapper form textarea")
        self.type("สรุป ")
        self.type("@")
        self.ws.drain(1.0)
        m = self.frame("qwenEnhance.mention()")
        self.assertTrue(m["open"])
        self.assertEqual(sorted(i["where"] + "/" + i["name"] for i in m["items"]),
                         sorted(["attachments/รายงานตรวจรอบเดือน กันยายน.pdf", "attachments/budget-2026.xlsx",
                                 "outputs/สรุปผลการตรวจ.docx"]))
        # ตัวเลือก @ ของ WebUI (ค้นไฟล์ไม่ได้) ต้องไม่ค้างให้เห็น
        self.assertFalse(self.frame("!!document.querySelector('[data-slot=popover-content][data-state=open]"
                                    ":not([data-qw-webui-mention])')"))
        self.type("ราย")
        self.ws.drain(0.6)
        self.key("Enter", "Enter", 13)
        self.assertEqual(self.composer(), "สรุป @attachments/รายงานตรวจรอบเดือน กันยายน.pdf ")
        self.assertFalse(self.frame("qwenEnhance.mention().open"))
        self.frame("qwenEnhance.prefill('')")

    def test_3_dictation(self):
        self.click(".chat-screen-form-wrapper form textarea")
        self.type("เรื่อง")
        self.click(".qw-mic")
        self.ws.drain(2.0)
        self.assertEqual(self.frame("qwenEnhance.dictation().state"), "rec")
        self.click(".qw-mic")
        for _ in range(40):
            self.ws.drain(0.25)
            if self.frame("qwenEnhance.dictation().state") == "idle":
                break
        self.assertEqual(self.composer(), "เรื่อง " + STT_TEXT)
        self.assertIn("POST", self.stt_seen)
        self.frame("qwenEnhance.prefill('')")

    def test_4_plan_mode_header(self):
        del _Up.log[:]
        self.click(".qw-plan")
        self.assertTrue(self.frame("qwenEnhance.plan().on"))
        self.click(".chat-screen-form-wrapper form textarea")
        self.type("ขอแผนก่อนย้ายไฟล์")
        self.click(".chat-screen-form-wrapper form button[type=submit]")
        for _ in range(40):
            self.ws.drain(0.25)
            if _Up.log and self.frame("qwenEnhance.route().name") == "chat" and not self.frame("qwenEnhance.isStreaming()"):
                break
        self.assertTrue(_Up.log, "ไม่มีคำขอแชตถึง upstream")
        sent = [e for e in self.ws.events if e["method"] == "Network.requestWillBeSent"
                and e["params"]["request"]["url"].endswith("/v1/chat/completions")]
        self.assertTrue(sent)
        hdr = {k.lower(): v for k, v in sent[-1]["params"]["request"]["headers"].items()}
        self.assertEqual(hdr.get("x-qwen-plan"), "1")
        if hasattr(self.hub, "PLAN_HEADER"):
            # hub บังคับโหมดวางแผน: เพิ่มคำสั่งใน system และไม่ส่ง header ต่อไปที่ router
            self.assertIn("PLAN MODE", _Up.log[-1]["system"])
        self.assertTrue(self.frame("qwenEnhance.plan().on && qwenEnhance.plan().count === 1"))
        self.ws.drain(1.0)
        self.assertFalse(self.frame("document.querySelector('.qw-plan-go').hidden"))
        self.click(".qw-plan-go")
        self.assertFalse(self.frame("qwenEnhance.plan().on"))
        self.assertEqual(self.composer(), "อนุมัติแผนแล้ว ลงมือทำตามแผนได้เลย")
        self.frame("qwenEnhance.prefill('')")

    def test_5_auto_kb_switch(self):
        self.click("#projBtn", inner=False)
        self.ws.drain(1.0)
        get = "fetch('http://127.0.0.1:%d/api/projects').then(r=>r.json()).then(d=>d.projects[0].auto_kb)" % self.api_port
        before = self.shot.evaluate(self.ws, get)
        self.shot.evaluate(self.ws, "document.getElementById('ppAkbRow').scrollIntoView({block:'center'})")
        self.ws.drain(0.3)
        self.click("#ppAkb", inner=False)
        self.ws.drain(1.2)
        if before is None:
            # hub ที่ยังไม่รู้จักฟิลด์: สวิตช์ต้องกลับเป็นเปิดพร้อมข้อความบอก
            self.assertEqual(self.shot.evaluate(self.ws, "document.getElementById('ppAkb').getAttribute('aria-checked')"),
                             "true")
            return
        self.assertIs(self.shot.evaluate(self.ws, get), False)
        self.assertEqual(self.shot.evaluate(self.ws, "document.getElementById('ppAkb').getAttribute('aria-checked')"),
                         "false")
        self.click("#ppAkb", inner=False)
        self.ws.drain(1.2)
        self.assertIs(self.shot.evaluate(self.ws, get), True)


if __name__ == "__main__":
    unittest.main()
