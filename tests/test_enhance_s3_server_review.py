# -*- coding: utf-8 -*-
"""
เทสต์ของ S3 (2026-09-30 ดึก): การ์ดอนุญาต local_confirm แสดง review "ของเซิร์ฟเวอร์" (webui-enhance.js / webui-theme.css)

สัญญา S3: เอา confirm_token จากการเรียก local_confirm ที่รออยู่ (IndexedDB) → GET <MCP base>/review/<slug>?token=
ด้วย Bearer จากค่าตั้ง MCP ของ WebUI เอง (id "local"/"local-full") → โชว์ review ของเซิร์ฟเวอร์ (เต็ม, เลื่อนได้, อักขระซ่อน
ถูกเน้น) · review ของโมเดลไม่ตรง = เตือนแดง · โหลดไม่ได้ = แดง "อย่ากดอนุญาต" + ปุ่มอนุญาตจาง

รันฟังก์ชันจริงจากซอร์สใน Node (ไม่เปิดเบราว์เซอร์/hub ไม่แตะบริการจริง):
  * srvEntry/srvConfig — ปลายทาง loopback เท่านั้น, ส่งเฉพาะ Authorization, slug จาก path, เลือก entry ตามชื่อบนการ์ด
  * srvParse — ทุกคำตอบของ S1 (server.review_lookup) + ด่าน/rate limit + เซิร์ฟเวอร์รุ่นเก่า
  * srvReviewGet — URL/ตัวเลือกของ fetch (GET, ไม่ตาม redirect, ไม่ส่ง cookie/referrer), หมดเวลา, ไม่มีค่าตั้ง = ไม่ส่ง
  * rvToken/rvModelDiffers — เลียน server._confirm_call + guard.review_provided/review_matches (เทียบกับของจริง)
  * rvShow — มุมมอง loading/ok/fail + คำเตือน + data-qw-rv บนการ์ด; rvSrv — ขอครั้งเดียวต่อ token, ลองใหม่, หมดอายุ
  * rvLoad → confirmCallFromDb → rvSrv (แก้ 2026-10-01): การ์ดขอ review ของการเรียกที่รออยู่ "ตามตำแหน่ง" (ผลของ WebUI
    เป็นพี่น้องกันใต้ข้อความผู้ช่วย) · id ซ้ำ = ไม่ขออะไร + แดง
ย้ายจาก scratchpad ของเจ้าของ enhance เข้าชุดเทสต์เมื่อ 2026-10-01 (fixer ของรีวิว S3)
ชี้ไปไฟล์สำเนาได้: QWEN_ENH_FILE, QWEN_THEME_FILE
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, r"C:\LLM\tests")
import test_security_common as C  # noqa: E402  (ตั้ง env ทดสอบ + import guard ของจริง)

ENH = os.environ.get("QWEN_ENH_FILE") or r"C:\LLM\projects\static\webui-enhance.js"
CSS = os.environ.get("QWEN_THEME_FILE") or r"C:\LLM\projects\static\webui-theme.css"
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
HAVE_NODE = os.path.isfile(NODE) if os.path.isabs(NODE) else bool(shutil.which("node"))

NET_START = "S3 (2026-09-30 ดึก): ดึงข้อความตรวจทาน"
NET_END = "รอบ 4 (2026-09-30) — สัญญา K5-K9"
R4_START = "R4 (รอบ 5, 2026-09-30)"
R4_END = "\n  function confirmCards()"
MODULE_END = "/* ---- API ----"

CAPTION_EN = "Review this before you allow it — this is exactly what will run (from the server)"
CAPTION_TH = "ตรวจโค้ด/คำสั่งนี้ก่อนกดอนุญาต — นี่คือสิ่งที่จะรันจริง (จากเซิร์ฟเวอร์)"
STOP_EN = "Could not load details — do not allow"
STOP_TH = "โหลดรายละเอียดไม่ได้ — อย่ากดอนุญาต"
MISMATCH_EN = ("The review the model sent differs from the server's version below. The server will refuse it, "
               "so allowing runs nothing.")


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
        raise AssertionError("node failed: %s" % r.stderr[-3000:])
    return json.loads(r.stdout)


def sections(src):
    a = src.index(NET_START)
    net = src[src.rindex("/*", 0, a):]
    b = net.index(NET_END)
    net = net[:net.rindex("/*", 0, b)]
    a = src.index(R4_START)
    r4 = src[src.rindex("/*", 0, a):src.index(R4_END, a)]
    m0 = src.index(NET_END)
    module = src[m0:src.index(MODULE_END, m0)]
    return net, r4, module


HAS_OWN = "function hasOwn(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }\n"
DOM_STUB = r"""
function mkEl(tag) {
  var e = {tag: tag, className: "", children: [], attrs: {}, title: "", hidden: false, _text: null};
  e.classList = {add: function (c) { e.className = (e.className ? e.className + " " : "") + c; },
                 contains: function (c) { return (" " + e.className + " ").indexOf(" " + c + " ") >= 0; }};
  e.appendChild = function (c) { e.children.push(c); c.parentNode = e; return c; };
  e.removeChild = function (c) { e.children.splice(e.children.indexOf(c), 1); return c; };
  Object.defineProperty(e, "firstChild", {get: function () { return e.children[0] || null; }});
  e.setAttribute = function (k, v) { e.attrs[k] = String(v); };
  e.getAttribute = function (k) { return Object.prototype.hasOwnProperty.call(e.attrs, k) ? e.attrs[k] : null; };
  e.removeAttribute = function (k) { delete e.attrs[k]; };
  // เหมือน DOM จริง: ตั้ง textContent = แทนลูกทั้งหมดด้วย text node เดียว (ต่อท้ายลูกเพิ่มได้ภายหลัง)
  Object.defineProperty(e, "textContent", {
    get: function () { return e.children.map(function (c) { return c.textContent; }).join(""); },
    set: function (v) { e.children = [{textContent: String(v), text: true}]; }
  });
  return e;
}
var document = {createTextNode: function (t) { return {textContent: t, text: true}; }};
function el(tag, cls) { var e = mkEl(tag); if (cls) e.className = cls; return e; }
function xIcon() { return ""; }
function mkSt() { var c = mkEl("div"); return {box: rvBox(), card: c, seq: 0, key: null, good: false, srv: null, r: null}; }
function view(st) {
  var body = st.box.__qwBody, pre = null, notes = [], meta = null;
  body.children.forEach(function (c) {
    if (c.tag === "pre") pre = c;
    if (c.className === "qw-review-note") notes.push([c.attrs["data-kind"], c.textContent]);
    if (c.className === "qw-review-meta") meta = c.textContent;
  });
  return {state: st.box.attrs["data-state"], card: st.card.attrs["data-qw-rv"], text: pre && pre.textContent,
          notes: notes, meta: meta, cap: st.box.children[0].children[0].textContent};
}
"""


@unittest.skipUnless(HAVE_NODE, "ไม่มี node")
class S3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(ENH)
        cls.css = read(CSS)
        cls.net, cls.r4, cls.module = sections(cls.src)
        cls.guard = C.import_local("guard")

    # ---------------------------------------------------------------- ป้าย + ภาษา
    def test_labels_have_thai_and_caption_is_exact(self):
        th = run_node(js_block(self.src, self.src.index("var TH = {")).replace("var TH =", "const TH =", 1) +
                      ";\nconsole.log(JSON.stringify(TH));")
        self.assertEqual(th[CAPTION_EN].replace("\u2060", ""), CAPTION_TH, "หัวกล่องตามสัญญาทุกตัวอักษร")
        self.assertEqual(th[STOP_EN].replace("\u2060", ""), STOP_TH)
        self.assertIn('cap.textContent = "%s"' % CAPTION_EN, self.r4)
        # ทุกข้อความที่ส่วน R4 ใส่ลง DOM (rvNote/textContent/RV_WHY) ต้องมีคำแปลไทย
        lits = [a or b for a, b in re.findall(r'rvNote\("[a-z]+", "([^"]+)"\)|textContent = "([^"]+)"', self.r4)]
        why = js_block(self.r4, self.r4.index("var RV_WHY = {"))
        lits += re.findall(r':\s*"([^"]+)"', why)
        self.assertGreaterEqual(len(lits), 20)
        for s in lits:
            self.assertIn(s, th, "ป้าย %r ไม่มีคำแปลไทย" % s)
            # ตัวแปลค้นด้วย txKey (ยุบช่องว่าง, … -> ...) — ป้ายที่ไม่อยู่ในรูปนั้นจะไม่มีวันถูกแปล
            self.assertEqual(s, re.sub(r"\s+", " ", s).strip().replace("…", "..."), "ป้าย %r ไม่อยู่ในรูป txKey" % s)
            self.assertRegex(th[s], "[\u0E00-\u0E7F]", s)

    # ---------------------------------------------------------------- ค่าตั้ง MCP → ปลายทาง
    def cfg_js(self, servers, labels):
        return HAS_OWN + self.net + r"""
var store = {"LlamaUi.config": JSON.stringify({mcpServers: JSON.stringify(%s)})};
var localStorage = {getItem: function (k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; }};
console.log(JSON.stringify(%s.map(function (l) { return srvConfig(l); })));
""" % (json.dumps(servers, ensure_ascii=False), json.dumps(labels))

    def test_config_pick_and_loopback_only(self):
        H = json.dumps({"Authorization": "Bearer " + "a" * 64, "X-Other": "no"})
        servers = [
            {"id": "websearch", "name": "ค้นอินเทอร์เน็ต", "url": "http://127.0.0.1:8791/mcp", "headers": H},
            {"id": "local", "name": "เครื่องนี้", "url": "http://127.0.0.1:8792/fast/%E0%B8%A7%E0%B8%B4", "enabled": True,
             "headers": H},
            {"id": "local-full", "name": "เครื่องนี้ (เครื่องมือครบ)", "url": "http://127.0.0.1:8792/mcp/%E0%B8%A7%E0%B8%B4",
             "enabled": False, "headers": H},
        ]
        r = run_node(self.cfg_js(servers, ["qwen38-local-fast", "qwen38-local", "", "เครื่องนี้ (เครื่องมือครบ)",
                                           "qwen38-local (2)"]))
        fast, full = r[0], r[1]
        self.assertEqual(fast, {"base": "http://127.0.0.1:8792", "slug": "%E0%B8%A7%E0%B8%B4", "surface": "fast",
                                "auth": "Bearer " + "a" * 64})
        self.assertEqual(full["surface"], "mcp", "การ์ดบอก qwen38-local = ผิวเต็ม")
        self.assertEqual(r[2]["surface"], "fast", "ไม่รู้ชื่อ = ตัวที่เปิดใช้อยู่")
        self.assertEqual(r[3]["surface"], "mcp", "ชื่อในค่าตั้งตรงกับการ์ด")
        self.assertEqual(r[4]["surface"], "mcp", "ชื่อซ้ำที่ WebUI ต่อท้าย (2)")
        self.assertNotIn("X-Other", json.dumps(r), "ส่งเฉพาะ Authorization")

        bad = [
            {"id": "local", "url": "http://192.168.1.5:8792/fast/p", "headers": H},          # ไม่ใช่ loopback
            {"id": "local", "url": "http://evil.example:8792/fast/p", "headers": H},
            {"id": "local", "url": "http://127.0.0.1.evil.example:8792/fast/p", "headers": H},
            {"id": "local", "url": "http://user:pw@127.0.0.1:8792/fast/p", "headers": H},
            {"id": "local", "url": "file:///C:/x/fast/p", "headers": H},
            {"id": "local", "url": "http://127.0.0.1:8792/other/p", "headers": H},             # path ไม่ใช่ /fast|/mcp
            {"id": "local", "url": "http://127.0.0.1:8792/fast/", "headers": H},
            {"id": "local", "url": "http://127.0.0.1:8792/fast/p"},                           # ไม่มี Bearer
            {"id": "local", "url": "http://127.0.0.1:8792/fast/p", "headers": '{"Authorization":"Basic xxxxxxxxxx"}'},
            {"id": "local", "url": "http://127.0.0.1:8792/fast/p", "headers": "{not json"},
            {"id": "mine", "url": "http://127.0.0.1:8792/fast/p", "headers": H},               # id อื่น
        ]
        for s in bad:
            self.assertEqual(run_node(self.cfg_js([s], ["qwen38-local-fast"])), [None], s)
        ok_hosts = ["http://localhost:8891/mcp/p", "http://[::1]:8792/fast/p",
                    "http://127.0.0.1:8792/fast/p"]
        for u in ok_hosts:
            got = run_node(self.cfg_js([{"id": "local", "url": u, "headers": {"authorization": "Bearer " + "b" * 64}}],
                                       [""]))[0]
            self.assertIsNotNone(got, u)
            self.assertEqual(got["auth"], "Bearer " + "b" * 64, "header เป็น object และตัวพิมพ์เล็กก็ได้")
        # ค่าตั้งเสีย/ไม่มี = null ไม่ throw
        js = HAS_OWN + self.net + r"""
var out = [];
[null, "{", JSON.stringify({}), JSON.stringify({mcpServers: "{"}), JSON.stringify({mcpServers: 5})].forEach(function (v) {
  var localStorage = {getItem: function () { return v; }};
  globalThis.localStorage = localStorage; out.push(srvConfig("qwen38-local-fast"));
});
console.log(JSON.stringify(out));
"""
        self.assertEqual(run_node(js), [None] * 5)

    # ---------------------------------------------------------------- คำตอบของ S1
    def test_parse_every_answer_of_s1(self):
        cases = [
            [200, {"ok": True, "action": "python", "review": "[python] x\n1│ print(1)", "expires_in_s": 598,
                   "pending": True}],
            [200, {"ok": True, "review": "x", "expires_in_s": 5}],                       # ไม่มี pending
            [200, {"ok": True, "review": "  ", "pending": True}],                         # review ว่าง
            [200, {"ok": True, "review": 5, "pending": True}],
            [404, {"ok": False, "reason": "not_pending"}],
            [400, {"ok": False, "reason": "bad_token"}],
            [400, {"ok": False, "reason": "missing_token"}],
            [404, {"ok": False, "reason": "other_project"}],
            [403, {"error": "origin_project_mismatch", "message": "x"}],
            [401, {"error": "missing_or_bad_token"}],
            [429, {"ok": False, "reason": "rate_limited"}],
            [500, None], [0, None], [503, {"ok": False, "reason": "x"}],
            [200, {"status": "ok", "server": "qwen38-local", "surface": "full"}],        # เซิร์ฟเวอร์ก่อน S1
            [404, None], [405, None],
            [200, "not json"], [200, [1, 2]],
            [404, {"ok": False, "reason": "a very long reason text with spaces that must not reach the card"}],
        ]
        js = HAS_OWN + self.net + "\nconsole.log(JSON.stringify(%s.map(function (c) { return srvParse(c[0], " \
            "c[1] === null ? '' : typeof c[1] === 'string' ? c[1] : JSON.stringify(c[1])); })));" % json.dumps(cases)
        r = run_node(js)
        self.assertEqual(r[0], {"state": "ok", "review": "[python] x\n1│ print(1)", "action": "python", "expiresIn": 598})
        got = [(x["state"], x.get("why"), x.get("code"), x.get("transient")) for x in r[1:]]
        self.assertEqual(got, [
            ("fail", "bad", "", False), ("fail", "bad", "", False), ("fail", "bad", "", False),
            ("fail", "token", "not_pending", False), ("fail", "notoken", "bad_token", False),
            ("fail", "notoken", "missing_token", False), ("fail", "project", "other_project", False),
            ("fail", "auth", "origin_project_mismatch", False), ("fail", "auth", "missing_or_bad_token", False),
            ("fail", "busy", "rate_limited", True), ("fail", "network", "", True), ("fail", "network", "", True),
            ("fail", "network", "x", True), ("fail", "old", "", False), ("fail", "old", "", False),
            ("fail", "old", "", False), ("fail", "bad", "", False), ("fail", "bad", "", False),
            ("fail", "token", "", False)])
        # ยาวผิดปกติ = ไม่ parse
        js = HAS_OWN + self.net + "\nvar big = JSON.stringify({ok: true, pending: true, review: new Array(2000001).join('x')});" \
            "\nconsole.log(JSON.stringify(srvParse(200, big)));"
        self.assertEqual(run_node(js)["why"], "bad")

    def test_parse_matches_real_server_answers(self):
        # คำตอบจริงจาก server.review_lookup (ถ้าฝั่ง MCP มีแล้ว) ผ่าน srvParse ต้องได้ชนิดที่ถูก
        srv = C.import_local("server")
        if not hasattr(srv, "review_lookup"):
            self.skipTest("server.review_lookup ยังไม่มี")
        g = self.guard
        slug = "s3-ui-test"
        with g.project_scope(slug):
            tok = g.need_confirm("run", "dir", review="[run] dir\n$ dir")
        answers = [srv.review_lookup(slug, "token=" + (tok or "00000000")),
                   srv.review_lookup(slug, "token=zz"), srv.review_lookup(slug, "token="),
                   srv.review_lookup("other-project", "token=" + (tok or "00000000"))]
        js = HAS_OWN + self.net + "\nconsole.log(JSON.stringify(%s.map(function (c) { return srvParse(c[0], JSON.stringify(c[1])); })));" \
            % json.dumps(answers, ensure_ascii=False)
        r = run_node(js)
        if tok:
            self.assertEqual(r[0]["state"], "ok", answers[0])
        self.assertEqual(r[1]["why"], "notoken")
        self.assertEqual(r[2]["why"], "notoken")
        self.assertEqual(r[3]["why"], "token", "ของโปรเจกต์อื่น = เหมือนไม่มี")

    # ---------------------------------------------------------------- fetch: URL + ตัวเลือก + หมดเวลา
    def test_fetch_request_shape_and_timeout(self):
        js = HAS_OWN + self.net + r"""
var calls = [], mode = "ok";
var window = {fetch: function (url, opt) {
  calls.push({url: url, opt: JSON.parse(JSON.stringify(Object.assign({}, opt, {signal: !!opt.signal})))});
  if (mode === "hang") return new Promise(function () {});
  if (mode === "throw") return Promise.reject(new TypeError("Failed to fetch"));
  return Promise.resolve({status: 200, text: function () {
    return Promise.resolve(JSON.stringify({ok: true, pending: true, review: "[run] x", action: "run", expires_in_s: 30})); }});
}};
var cfg = {base: "http://127.0.0.1:8792", slug: "%E0%B8%81", surface: "fast", auth: "Bearer " + new Array(65).join("c")};
(async function () {
  var out = {};
  out.ok = await srvReviewGet(cfg, "3fa1c29e");
  out.none = await srvReviewGet(null, "3fa1c29e");
  mode = "throw"; out.thrown = await srvReviewGet(cfg, "3fa1c29e");
  mode = "hang"; SRV_TIMEOUT_MS = 60; out.hang = await srvReviewGet(cfg, "ab&c=d");
  out.calls = calls;
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""
        r = run_node(js)
        self.assertEqual(r["ok"]["state"], "ok")
        self.assertEqual(r["none"]["why"], "config")
        self.assertEqual(r["thrown"], {"state": "fail", "why": "network", "code": "", "transient": True})
        self.assertEqual(r["hang"]["why"], "network")
        self.assertTrue(r["hang"]["transient"])
        self.assertEqual(len(r["calls"]), 3, "ไม่มีค่าตั้ง = ไม่ส่งอะไรเลย")
        c = r["calls"][0]
        self.assertEqual(c["url"], "http://127.0.0.1:8792/review/%E0%B8%81?token=3fa1c29e")
        self.assertEqual(r["calls"][2]["url"], "http://127.0.0.1:8792/review/%E0%B8%81?token=ab%26c%3Dd")
        o = c["opt"]
        self.assertEqual(o["method"], "GET")
        self.assertEqual(sorted(o["headers"]), ["Accept", "Authorization"], "header อื่นไม่ส่ง")
        self.assertEqual(o["credentials"], "omit")
        self.assertEqual(o["redirect"], "error", "ไม่ตาม redirect (Bearer ต้องไม่ไปที่อื่น)")
        self.assertEqual(o["referrerPolicy"], "no-referrer")
        self.assertEqual(o["cache"], "no-store")
        self.assertTrue(o["signal"])

    # ---------------------------------------------------------------- token + review ของโมเดล = แบบเดียวกับเซิร์ฟเวอร์
    def test_token_pick_mirrors_server(self):
        cases = [{"confirm_token": "3fa1c29e"}, {"confirm_token": " 3fa1c29e\n"}, {"token": "3fa1c29e"},
                 {"confirm_token": "", "token": "3fa1c29e"}, {"confirm_token": None, "token": "abcd"},
                 {"confirm_token": [], "token": "abcd"}, {"confirm_token": 12345678}, {"confirm_token": 0, "token": "ab"},
                 {"confirm_token": "3fa1c29g"}, {"confirm_token": "\u200b3fa1c29e"}, {"confirm_token": "3fa1c29e\u3000"},
                 {"confirm_token": {"a": 1}}, {"confirm_token": 1.5}, {"confirm_token": True}, {}, {"confirm_token": "a" * 65}]
        js = self.r4 + "\nconsole.log(JSON.stringify(%s.map(rvToken)));" % json.dumps(cases)
        r = run_node(js)
        want = []
        for a in cases:
            t = str(a.get("confirm_token") or a.get("token") or "").strip()     # server._confirm_call
            want.append(t if re.fullmatch(r"[0-9A-Fa-f]{1,64}", t) else "")
        self.assertEqual(r, want)

    def test_model_review_compare_mirrors_guard(self):
        g = self.guard
        if not hasattr(g, "review_provided"):
            self.skipTest("guard.review_provided ยังไม่มี (S2)")
        stored = "⚠ คำเตือน (WARNING): x\n[python] run\n 1│ a = 1\n 2│ \n 3│ b = 2"
        givens = [None, "", "   ", "\x1c\x1d", "\ufeff", "\u3000\n", stored, stored + "\n", "  " + stored,
                  stored.replace("\n", "\r\n"), stored[:-1], stored + "x", "\n" * 4 + stored, stored + "    \n",
                  stored.replace("\n", "     \n", 1), 5, ["x"], {"a": 1}, True, stored.replace("a = 1", "a = 2"),
                  "[python] run", "\t" + stored]
        js = self.r4 + "\nconsole.log(JSON.stringify(%s.map(function (g) { return rvModelDiffers(g, %s); })));" % (
            json.dumps(givens, ensure_ascii=False), json.dumps(stored, ensure_ascii=False))
        r = run_node(js)
        for gv, differs in zip(givens, r):
            refused = g.review_provided(gv) and not g.review_matches(stored, gv)
            self.assertEqual(differs, refused, repr(gv)[:60])

    # ---------------------------------------------------------------- มุมมองของกล่อง
    def test_views(self):
        review = "[python] run\n 1│ print(\"hi\")\n 2│ x = «U+202E»1"
        js = DOM_STUB + HAS_OWN + self.r4 + r"""
var R = %s, out = {};
function show(r, srv) { var st = mkSt(); st.srv = srv || null; rvShow(st, r); return view(st); }
var ok = {status: "ok", callId: "c1", raw: "{}", args: {confirm_token: "3fa1c29e"}};
out.first = show({status: "loading"});
out.waiting = show(ok);
out.server = show(ok, {tok: "3fa1c29e", state: "ok", review: R + "\n"});
out.sameModel = show({status: "ok", callId: "c1", raw: "{}", args: {confirm_token: "3fa1c29e", review: " " + R}},
                     {tok: "3fa1c29e", state: "ok", review: R});
out.mismatch = show({status: "ok", callId: "c1", raw: "{}", args: {confirm_token: "3fa1c29e", review: "[python] run\n 1│ print(\"hi\")"}},
                    {tok: "3fa1c29e", state: "ok", review: R});
out.otherTok = show(ok, {tok: "deadbeef", state: "ok", review: "[run] rm -rf"});
out.expired = show(ok, {tok: "3fa1c29e", state: "fail", why: "token", code: "not_pending"});
out.retry = show(ok, {tok: "3fa1c29e", state: "fail", why: "network", code: "", retry: true});
out.unknown = show({status: "unknown"});
out.badargs = show({status: "badargs", callId: "c1", raw: "{\"confirm_token\": \"3fa"});
out.notoken = show({status: "ok", callId: "c1", raw: "{}", args: {review: "[run] x"}});
var st = mkSt(); rvShow(st, ok); st.srv = {tok: "3fa1c29e", state: "ok", review: R};
out.repaint = rvShow(st, ok); out.again = rvShow(st, ok);
st.good = true; out.noBack = rvShow(st, {status: "unknown"});
console.log(JSON.stringify(out));
""" % json.dumps(review, ensure_ascii=False)
        r = run_node(js)
        self.assertEqual((r["first"]["state"], r["first"]["card"]), ("loading", "loading"))
        self.assertEqual(r["first"]["cap"], CAPTION_EN)
        self.assertEqual((r["waiting"]["state"], r["waiting"]["card"]), ("loading", "loading"),
                         "มี token แต่เซิร์ฟเวอร์ยังไม่ตอบ = ยังไม่โชว์อะไร")
        s = r["server"]
        self.assertEqual((s["state"], s["card"]), ("ok", "ok"))
        self.assertEqual(s["text"], review, "โชว์ review ของเซิร์ฟเวอร์เต็มๆ")
        self.assertIn("3fa1c29e", s["meta"])
        self.assertEqual([k for k, _ in s["notes"]], ["warn"], "«U+202E» = คำเตือนอักขระซ่อน ไม่มีคำเตือนอื่น")
        self.assertEqual([k for k, _ in r["sameModel"]["notes"]], ["warn"], "review ของโมเดลตรง (อนุโลมช่องว่างนำ) = ไม่เตือน")
        mm = r["mismatch"]
        self.assertEqual(mm["text"], review, "ยังโชว์ของเซิร์ฟเวอร์ ไม่ใช่ของโมเดล")
        self.assertIn(["danger", MISMATCH_EN], mm["notes"])
        self.assertEqual(r["otherTok"]["state"], "loading", "ผลของ token อื่นห้ามถูกใช้")
        self.assertNotEqual(r["otherTok"]["text"], "[run] rm -rf")
        for k, why in (("expired", "no pending request"), ("retry", "didn't answer"), ("unknown", "find this request"),
                       ("badargs", "valid JSON"), ("notoken", "no valid confirm code")):
            v = r[k]
            self.assertEqual((v["state"], v["card"]), ("fail", "fail"), k)
            self.assertEqual(v["notes"][0], ["stop", STOP_EN], k)
            self.assertEqual(v["notes"][1][0], "reason", k)
            self.assertIn(why, v["notes"][1][1], k)
        self.assertIn("not_pending", r["expired"]["notes"][1][1], "รหัสเหตุผลของเซิร์ฟเวอร์แสดงแยก")
        self.assertEqual(r["retry"]["notes"][-1], ["label", "Trying again..."])
        self.assertIsNone(r["expired"]["text"], "โหลดไม่ได้ = ไม่มีโค้ดให้หลงกดอนุญาต")
        self.assertIn('"confirm_token": "3fa', r["badargs"]["text"])
        self.assertIn('"review": "[run] x"', r["notoken"]["text"], "ไม่มี token = โชว์สิ่งที่โมเดลส่ง (กำกับว่าเป็นของโมเดล)")
        self.assertTrue(r["repaint"])
        self.assertFalse(r["again"], "ไม่เปลี่ยน = ไม่วาดใหม่ (ตรวจซ้ำทุก 2 วิ)")
        self.assertFalse(r["noBack"])

    # ---------------------------------------------------------------- ลำดับการขอ: ครั้งเดียว, ลองใหม่, หมดอายุ
    def test_srv_requests_once_retries_and_expires(self):
        js = DOM_STUB + HAS_OWN + self.r4 + r"""
var now = 1000000, gets = [], queue = [], paints = 0;
Date.now = function () { return now; };
function srvConfig(label) { return {base: "b", slug: "s", auth: "Bearer x", label: label}; }
function srvReviewGet(cfg, tok) { gets.push([tok, cfg.label]); var r = queue.shift(); return {then: function (f) { f(r); }}; }
rvPaint = function () { paints++; };
var card = {isConnected: true}, st = mkSt(); st.card = card; card.__qwRv = st; st.server = "qwen38-local-fast";
st.r = {status: "ok", callId: "c1", raw: "{}", args: {confirm_token: "3fa1c29e"}};
var out = {};
queue.push({state: "fail", why: "network", code: "", transient: true});
rvSrv(card, st); out.a = [gets.length, st.srv.state, !!st.srv.retry, st.srv.retryAt - now];
rvSrv(card, st); out.b = gets.length;                               // ยังไม่ถึงเวลาลองใหม่
now += 2000; queue.push({state: "fail", why: "busy", code: "rate_limited", transient: true});
rvSrv(card, st); out.c = [gets.length, st.srv.why, st.srv.retryAt - now];
now += 4000; queue.push({state: "ok", review: "[run] x", action: "run", expiresIn: 30});
rvSrv(card, st); out.d = [gets.length, st.srv.state, st.srv.expAt - now];
now += 10000; rvSrv(card, st); out.e = [gets.length, st.srv.state];  // ได้แล้ว = ไม่ถามซ้ำ
now += 21000; rvSrv(card, st); out.f = [gets.length, st.srv.state, st.srv.why];  // หมดอายุตามเซิร์ฟเวอร์
// token ใหม่ = ถามใหม่ · ลองใหม่ไม่เกิน 3 ครั้ง
st.r = {status: "ok", callId: "c2", raw: "{}", args: {confirm_token: "bbbb2222"}};
for (var i = 0; i < 6; i++) { queue.push({state: "fail", why: "network", code: "", transient: true}); rvSrv(card, st); now += 60000; }
out.g = [gets.length, st.srv.tries, !!st.srv.retry];
// ไม่มี token = ไม่ส่งอะไร · ผลที่มาช้าหลังการ์ดหาย = ไม่วาด
var n0 = gets.length; st.r = {status: "ok", callId: "c3", raw: "{}", args: {}}; rvSrv(card, st); out.h = gets.length - n0;
out.labels = gets.map(function (g) { return g[1]; }).filter(function (l, i, a) { return a.indexOf(l) === i; });
out.paints = paints;
console.log(JSON.stringify(out));
"""
        r = run_node(js)
        self.assertEqual(r["a"], [1, "fail", True, 2000])
        self.assertEqual(r["b"], 1)
        self.assertEqual(r["c"], [2, "busy", 4000])
        self.assertEqual(r["d"], [3, "ok", 30000])
        self.assertEqual(r["e"], [3, "ok"])
        self.assertEqual(r["f"], [3, "fail", "expired"])
        self.assertEqual(r["g"], [3 + 4, 4, False], "ครั้งแรก + ลองใหม่ 3 ครั้ง แล้วหยุด")
        self.assertEqual(r["h"], 0)
        self.assertEqual(r["labels"], ["qwen38-local-fast"])

    # ---------------------------------------------------------------- การ์ด ↔ การเรียกที่รออยู่ (แก้ 2026-10-01)
    def test_card_fetches_review_of_the_pending_call_by_position(self):
        """รีวิว S3 พบ: การ์ดเลือก "ตัวแรกที่ยังไม่มีผล" จากผลที่เดินขึ้นจาก currNode — แต่ WebUI เก็บผลทุกตัวของเทิร์นเป็น
        พี่น้องกันใต้ข้อความผู้ช่วย จึงเห็นแค่ผลล่าสุด: สามการเรียก [A, B, C] ปฏิเสธ A, B → การ์ดของ C ขอและโชว์ review + รหัส
        ของ A (ยังค้าง = โชว์เขียว) แต่กดอนุญาตแล้ว C รัน · id ซ้ำ [d:A, d:B, c3:C] → การ์ดของ B โชว์ของ C
        ตอนนี้: ขอ review ของ token ที่ตำแหน่งตรงเท่านั้น, id ซ้ำ/ลำดับไม่ตรง = ไม่ขออะไรเลย + แดง "อย่ากดอนุญาต" """
        js = DOM_STUB + HAS_OWN + r"""
function later(f) { setTimeout(f, 1); }
function makeIdb(stores) {
  var db = {objectStoreNames: {contains: function (n) { return hasOwn(stores, n); }}, close: function () {},
    transaction: function () { return {objectStore: function (n) { return {get: function (id) {
      var r = {}; later(function () { r.result = stores[n][id]; r.onsuccess && r.onsuccess(); }); return r; }}; }}; }};
  return {open: function () { var q = {}; later(function () { q.result = db; q.onsuccess && q.onsuccess(); }); return q; }};
}
function call(id, tok) { return {id: id, type: "function", function: {name: "local_confirm", arguments: JSON.stringify({confirm_token: tok})}}; }
// ต้นไม้แบบที่ WebUI สร้างจริง ณ ตอนการ์ดของตัวที่ k โผล่: ผล 0..k-1 เป็นลูกของผู้ช่วย, currNode = ผลล่าสุด
function scene(calls, k) {
  var m = {a: {id: "a", role: "assistant", parent: "u", toolCalls: JSON.stringify(calls), children: []}};
  for (var i = 0; i < k; i++) { m["t" + i] = {id: "t" + i, role: "tool", parent: "a", toolCallId: calls[i].id, children: []}; m.a.children.push("t" + i); }
  return {conversations: {c1: {id: "c1", currNode: k ? "t" + (k - 1) : "a"}}, messages: m};
}
var window = {}, indexedDB, gets = [];
function route() { return {name: "chat", id: "c1"}; }
function srvConfig() { return {base: "b", slug: "s", auth: "Bearer x"}; }
function srvReviewGet(cfg, tok) {
  gets.push(tok);
  return Promise.resolve({state: "ok", review: "[run] echo " + tok, action: "run", expiresIn: 600});
}
""" + self.r4 + r"""
rvPaint = function (card, st) { rvShow(st, st.r || {status: "loading"}); };
function flush() { return new Promise(function (r) { setTimeout(r, 30); }); }
async function card(calls, k) {
  window.indexedDB = indexedDB = makeIdb(scene(calls, k));
  gets = [];
  var c = mkEl("div"); c.isConnected = true;
  var st = mkSt(); st.card = c; c.__qwRv = st; st.server = "qwen38-local-fast";
  rvLoad(c, st, "local_confirm");
  for (var i = 0; i < 10; i++) await flush();
  var v = view(st);
  return {gets: gets, state: v.state, card: v.card, text: v.text, notes: v.notes, meta: v.meta};
}
(async function () {
  var U = [call("x1", "aaaa0001"), call("x2", "bbbb0002"), call("x3", "cccc0003")];
  var D = [call("d", "aaaa0001"), call("d", "bbbb0002"), call("c3", "cccc0003")];
  var out = {u1: await card(U, 0), u2: await card(U, 1), u3: await card(U, 2), d2: await card(D, 1), d3: await card(D, 2)};
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""
        r = run_node(js)
        for k, tok in (("u1", "aaaa0001"), ("u2", "bbbb0002"), ("u3", "cccc0003")):
            v = r[k]
            self.assertEqual(v["gets"], [tok], "%s: ขอ review ของ token ที่รออยู่จริงเท่านั้น" % k)
            self.assertEqual((v["state"], v["card"]), ("ok", "ok"), k)
            self.assertEqual(v["text"], "[run] echo " + tok, k)
            self.assertIn(tok, v["meta"], k)
        for k in ("d2", "d3"):
            v = r[k]
            self.assertEqual(v["gets"], [], "%s: id ซ้ำ = ไม่รู้ว่าตัวไหนรอ → ไม่ขอ review ของใครเลย" % k)
            self.assertEqual((v["state"], v["card"]), ("fail", "fail"), k)
            self.assertEqual(v["notes"][0], ["stop", STOP_EN], k)
            self.assertIn("find this request", v["notes"][1][1], k)
            self.assertIsNone(v["text"], "%s: ไม่มีโค้ดให้หลงกดอนุญาต" % k)

    # ---------------------------------------------------------------- เครือข่ายอยู่ที่เดียว
    def test_network_is_isolated(self):
        self.assertEqual(self.src.count("fetch("), 1, "ทั้งไฟล์มีการเรียก fetch ที่เดียว")
        self.assertIn("window.fetch(url, opt)", self.net)
        for bad in ("XMLHttpRequest", "sendBeacon", "WebSocket(", "EventSource(", "importScripts", "eval(",
                    "console.log", "console.info", "Claude", "Anthropic"):
            self.assertNotIn(bad, self.net, bad)
        self.assertIn('"/review/"', self.net)
        self.assertIn('method: "GET"', self.net)
        for part in (self.module, self.r4):
            for bad in ("fetch(", "XMLHttpRequest", "http://", "https://"):
                self.assertNotIn(bad, part, bad)
        # token ของเครื่องไม่ถูกเก็บค้าง/ใส่ DOM: auth ใช้แค่ใน srvEntry (อ่าน) และ srvReviewGet (header)
        uses = [ln.strip() for ln in self.src.splitlines() if ".auth" in ln]
        self.assertTrue(all("cfg.auth" in u or "c.auth" in u for u in uses), uses)

    def test_css(self):
        a = self.css.index("S3 (2026-09-30 ดึก)")
        sec = self.css[a:self.css.index("pre.qw-review-code {", a)]
        for sel in ('.qw-review-note[data-kind="stop"]', '.qw-review-note[data-kind="reason"]', ".qw-review-why",
                    '.qw-confirm-card[data-qw-rv="fail"]', '.qw-confirm-card[data-qw-rv="loading"]',
                    'button[data-slot="button"]:not(.bg-destructive)', "prefers-reduced-motion"):
            self.assertIn(sel, sec, sel)
        self.assertNotRegex(sec, r"#[0-9a-fA-F]{3,8}\b", "ใช้ token ไม่ใช่สีตายตัว")
        self.assertNotRegex(sec, r"rgba?\(")
        dim = sec[sec.index('[data-qw-rv="fail"] button'):]
        dim = dim[:dim.index("}")]
        self.assertIn("opacity", dim)
        self.assertNotIn("pointer-events", dim, "ปุ่มแค่จาง ไม่ถูกปิด (ไม่ยุ่งกลไกของ WebUI)")
        self.assertNotIn("display: none", dim)


if __name__ == "__main__":
    unittest.main()
