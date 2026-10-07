# -*- coding: utf-8 -*-
"""
เทสต์ฝั่ง hub ของ batch 2a สัญญา B5 (owner stack): งานค้นคว้า (/_qwen/research) + สถานะบริการ (/api/projects services)

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

สิ่งที่ตรวจ
  * รายการงานอ่านรูปแบบจริงของ tools_research.py (counts/limits ซ้อน, progress เป็น int เปอร์เซ็นต์, eta_left_s,
    error/phase สองภาษา, log, report {md, docx}) และรูปแบบอื่นที่ชื่อฟิลด์ต่างกันได้
  * ข้อมูลในไฟล์งานถือว่าไว้ใจไม่ได้: ลิงก์รายงานต้องเป็นไฟล์ที่มีอยู่จริงใน outputs\\ ของโปรเจกต์นี้ (../, path เต็ม,
    javascript:, ไฟล์ที่ไม่มี ถูกทิ้ง), อักขระควบคุม/สลับทิศทางถูกตัด, path ของเครื่องในข้อผิดพลาดเหลือแค่ชื่อไฟล์
    (คำถามของผู้ใช้ไม่ถูกตัด), ไฟล์ JSON ที่ไม่ใช่งาน/ใหญ่ผิดปกติถูกข้าม, GET ไม่สร้างโฟลเดอร์
  * HTTP: Origin ต้องเป็นพอร์ตของโปรเจกต์นี้ (โปรเจกต์อื่น/เว็บอื่น = 403), POST ต้องเป็น application/json (415),
    รหัสงานผิดรูป 400 / ไม่มี 404 / จบแล้ว 409, method อื่น 405, ไม่ส่งต่อไป llama-server เลย
  * ยกเลิก: เขียน <id>.cancel (ธงที่ tools_research ตรวจ) + เรียก local_do action=research_cancel ที่ /fast/<slug>
    ของ MCP ด้วย Bearer (MCP ปลอม) — MCP ไม่ตอบก็ยังยกเลิกได้ด้วยธง
  * สถานะบริการ: embedding ok/loading/down/absent, MCP auth/down, research missing/broken/down, ผู้ให้บริการค้นเว็บ,
    ไม่ส่งโทเคนให้พอร์ต embedding, ค่าในแคชไม่ถามซ้ำภายใน SVC_TTL, /api/projects และ /api/services มี services
ปลอดภัยต่อระบบจริง: DATA_ROOT / projects.json / settings.json / โทเคน ชี้โฟลเดอร์ชั่วคราว, upstream/MCP/embedding
เป็นเซิร์ฟเวอร์ปลอมบนพอร์ตสุ่ม ไม่แตะบริการที่รันอยู่
"""
import http.client
import importlib.util
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HUB = r"C:\LLM\projects\hub.py"
TOKEN_ENV = "LLM_LOCAL_TOKEN_FILE"
SLUG = "b5hubtest"


def load_hub():
    sys.path.insert(0, os.path.dirname(HUB))
    spec = importlib.util.spec_from_file_location("hub_stack_b2_under_test", HUB)
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


hub = load_hub()


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t))


def real_job(jid="r3fa9c1d2", **over):
    """งานในรูปแบบที่ tools_research.py เขียนจริง (ย่อ)"""
    now = time.time()
    doc = {
        "schema": 1, "kind": "qwen-research", "id": jid, "project": SLUG,
        "question": "มาตรฐาน OCPP 2.0.1 ต่างจาก 1.6J อย่างไร", "lang": "th", "depth": "standard", "model": "4b",
        "model_label": "Qwen3-4B", "status": "running", "phase": "read",
        "phase_th": "อ่านแหล่งข้อมูลและจดโน้ต", "phase_en": "Reading sources and taking notes", "progress": 45,
        "created": iso(now - 300), "updated": iso(now - 5), "finished": None, "heartbeat": now - 5,
        "eta_left_s": 420, "cancel_requested": False,
        "counts": {"llm_calls": 6, "sources_read": 3, "claims": 9},
        "limits": {"sources": 8, "searches": 10},
        "log": [{"t": iso(now - 20), "th": "อ่านแล้ว: example.org", "en": "Read: example.org"}],
        "report": None, "error": None,
    }
    doc.update(over)
    return doc


# ---------------------------------------------------------------- เซิร์ฟเวอร์ปลอม
class _Rec(BaseHTTPRequestHandler):
    """เซิร์ฟเวอร์ปลอมอเนกประสงค์: ตอบตาม cls.routes {(method, path): (status, body)} และจดทุกคำขอ"""
    protocol_version = "HTTP/1.1"
    routes = {}
    seen = []

    def log_message(self, *a):
        pass

    def _go(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        type(self).seen.append((method, self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        st, out = type(self).routes.get((method, self.path.split("?")[0]), (404, b'{"error":"nf"}'))
        if isinstance(out, (dict, list)):
            out = json.dumps(out).encode()
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        self._go("GET")

    def do_POST(self):
        self._go("POST")


def fake_server(routes):
    cls = type("FakeSrv", (_Rec,), {"routes": dict(routes), "seen": []})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), cls)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, cls


def free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _req(port, method, path, headers=None, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read()
    c.close()
    try:
        doc = json.loads(data.decode("utf-8")) if data else None
    except ValueError:
        doc = None
    return r.status, doc


class _Env(unittest.TestCase):
    """โฟลเดอร์ข้อมูลชั่วคราว + โทเคนทดสอบ + upstream ปลอม + proxy ของโปรเจกต์ทดสอบบนพอร์ตสุ่ม"""
    with_proxy = True

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stackb2-"))
        self.data = self.tmp / "data"
        self.data.mkdir()
        self.store = self.tmp / "projects.json"
        self.settings = self.tmp / "settings.json"
        self.settings.write_text(json.dumps({"lang": "th", "theme": "dark", "font": "serif"}), encoding="utf-8")
        self.tok = self.tmp / "local-services.token"
        self.token = secrets.token_hex(32)                  # ค่าทดสอบ ไม่ใช่โทเคนจริง
        self.tok.write_text(self.token, encoding="ascii")
        self.patches = [mock.patch.dict(os.environ, {TOKEN_ENV: str(self.tok)}),
                        mock.patch.object(hub, "DATA_ROOT", self.data),
                        mock.patch.object(hub, "STORE", self.store),
                        mock.patch.object(hub, "SETTINGS", self.settings),
                        mock.patch.object(hub, "upstream_models", return_value=[]),
                        mock.patch.object(hub, "upstream_model", return_value="")]
        for p in self.patches:
            p.start()
        self.rdir = self.data / SLUG / "research"
        self.odir = self.data / SLUG / "outputs"
        if self.with_proxy:
            self.up, self.up_cls = fake_server({})
            p = mock.patch.object(hub, "UPSTREAM_PORT", self.up.server_address[1])
            p.start()
            self.patches.append(p)
            self.srv = ThreadingHTTPServer(("127.0.0.1", 0), hub.make_proxy_handler(SLUG, lambda: [self.proj]))
            self.srv.daemon_threads = True
            self.port = self.srv.server_address[1]
            self.proj = {"slug": SLUG, "name": SLUG, "port": self.port, "system_prompt": "", "think": "off",
                         "extend": True}
            self.store.write_text(json.dumps([self.proj]), encoding="utf-8")
            self.own = "http://127.0.0.1:%d" % self.port
            p = mock.patch.object(hub, "ALLOWED_ORIGIN", re.compile(
                r"^http://(127\.0\.0\.1|localhost):(8100|81[0-7][0-9]|%d)$" % self.port))
            p.start()
            self.patches.append(p)
            threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        else:
            self.store.write_text(json.dumps([{"slug": SLUG, "name": SLUG, "port": 8199}]), encoding="utf-8")

    def tearDown(self):
        if self.with_proxy:
            self.srv.shutdown()
            self.srv.server_close()
            self.up.shutdown()
            self.up.server_close()
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def job(self, jid, doc):
        self.rdir.mkdir(parents=True, exist_ok=True)
        (self.rdir / (jid + ".json")).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    def out(self, name, data=b"x"):
        self.odir.mkdir(parents=True, exist_ok=True)
        (self.odir / name).write_bytes(data)

    def get(self, path, origin="own", extra=None):
        h = dict(extra or {})
        if origin == "own":
            h["Origin"] = self.own
        elif origin:
            h["Origin"] = origin
        return _req(self.port, "GET", path, h)

    def post(self, path, origin="own", ctype="application/json", body=b"{}"):
        h = {}
        if origin == "own":
            h["Origin"] = self.own
        elif origin:
            h["Origin"] = origin
        if ctype:
            h["Content-Type"] = ctype
        return _req(self.port, "POST", path, h, body)


# ============================================================================ การอ่าน/แปลงงาน
class ResearchNormalizeTests(_Env):
    with_proxy = False

    def test_real_tools_research_format(self):
        self.job("r3fa9c1d2", real_job())
        d = hub.research_list(SLUG)
        self.assertEqual((d["total"], d["running"]), (1, 1))
        j = d["jobs"][0]
        self.assertEqual(j["id"], "r3fa9c1d2")
        self.assertEqual(j["status"], "running")
        self.assertEqual(j["phase"], "read")
        self.assertEqual(j["progress"], 0.45)
        self.assertEqual((j["sources_read"], j["sources_total"], j["notes"]), (3, 8, 9))
        self.assertEqual(j["eta_s"], 420)
        self.assertEqual(j["depth"], "standard")
        self.assertEqual(j["model"], "Qwen3-4B")
        self.assertEqual(j["note"], "อ่านแล้ว: example.org")       # บรรทัดบันทึกล่าสุด ภาษาตามหน้า (th)
        self.assertTrue(j["active"])
        self.assertFalse(j["stale"])
        self.assertIsNone(j["report"])

    def test_done_job_report_links_and_bilingual_error(self):
        self.out("research-2026-10-01-r3fa9c1d2.md", b"# r")
        self.out("research-2026-10-01-r3fa9c1d2.docx", b"PK")
        self.job("r3fa9c1d2", real_job(status="done", phase="done", progress=100, finished=iso(time.time()),
                                       report={"md": "research-2026-10-01-r3fa9c1d2.md",
                                               "docx": "research-2026-10-01-r3fa9c1d2.docx"}))
        self.job("r0bad0bad", real_job("r0bad0bad", status="failed", phase="failed",
                                       error={"th": "ค้นเว็บไม่ได้", "en": "web search failed"}))
        jobs = {j["id"]: j for j in hub.research_list(SLUG)["jobs"]}
        done = jobs["r3fa9c1d2"]
        self.assertEqual(done["report"], "/_qwen/out/research-2026-10-01-r3fa9c1d2.md")
        self.assertEqual([f["kind"] for f in done["files"]], ["md", "docx"])
        self.assertEqual(done["note"], "")                      # งานจบแล้วไม่แสดงบันทึก
        self.assertEqual(jobs["r0bad0bad"]["error"], "ค้นเว็บไม่ได้")
        with mock.patch.object(hub, "get_lang", return_value="en"):
            en = {j["id"]: j for j in hub.research_list(SLUG)["jobs"]}
        self.assertEqual(en["r0bad0bad"]["error"], "web search failed")          # ข้อความตามภาษาของหน้า

    def test_progress_forms(self):
        P = hub._res_progress
        self.assertEqual(P(1), 0.01)                # int = เปอร์เซ็นต์เสมอ (tools_research) — 1 คือ 1% ไม่ใช่ 100%
        self.assertEqual(P(100), 1.0)
        self.assertEqual(P(0.45), 0.45)
        self.assertEqual(P(1.0), 1.0)
        self.assertEqual(P(45.0), 0.45)
        self.assertEqual(P("42%"), 0.42)
        self.assertEqual(P({"done": 3, "total": 8}), 0.375)
        self.assertEqual(P(250), 1.0)
        for bad in (None, True, "abc", float("nan"), {"x": 1}, [1]):
            self.assertIsNone(P(bad), bad)

    def test_other_field_names_are_understood(self):
        self.job("job-alt-1", {"state": "in_progress", "query": "q?", "stage": "searching",
                               "progress": {"done": 1, "total": 4}, "sources": [{"u": 1}, {"u": 2, "skipped": True}],
                               "eta_s": 60, "message": "กำลังค้น"})
        j = hub.research_list(SLUG)["jobs"][0]
        self.assertEqual((j["status"], j["phase"], j["progress"], j["sources_read"], j["note"]),
                         ("running", "search", 0.25, 1, "กำลังค้น"))

    def test_phase_same_as_status_is_hidden_and_unknown_phase_uses_job_label(self):
        self.job("r111111", real_job("r111111", status="queued", phase="queued"))
        self.job("r222222", real_job("r222222", phase="polish", phase_th="ขัดเกลา", phase_en="Polishing"))
        jobs = {j["id"]: j for j in hub.research_list(SLUG)["jobs"]}
        self.assertEqual((jobs["r111111"]["phase"], jobs["r111111"]["phase_text"]), ("", ""))
        self.assertEqual((jobs["r222222"]["phase"], jobs["r222222"]["phase_text"]), ("", "ขัดเกลา"))

    def test_forged_report_links_are_dropped(self):
        # batch 2a (fix): ลิงก์รายงานมาจาก report{md, docx} เท่านั้น และต้องเป็นชื่อรายงานของงานนี้ — ไฟล์อื่นใน outputs
        # (ok.md) ไม่ถูกแสดงเป็น "รายงานค้นคว้า" แม้มีอยู่จริง (ดูชุดเต็มที่ test_stack_b2_fix.ReportLinkContractTests)
        self.out("ok.md", b"# ok")
        (self.data / SLUG / "secret.md").parent.mkdir(parents=True, exist_ok=True)
        (self.data / SLUG / "secret.md").write_text("no", encoding="utf-8")
        self.job("r333333", real_job("r333333", status="done", result=[
            "javascript:alert(1)", "/_qwen/out/../secret.md", "/_qwen/out/..%2Fsecret.md", r"C:\Windows\win.ini",
            "missing.md", "/_qwen/out/sub/x.md", "[r](/_qwen/out/ok.md)"], report={"md": "ok.md"}))
        j = hub.research_list(SLUG)["jobs"][0]
        self.assertEqual(j["files"], [])
        self.assertIsNone(j["report"])

    def test_text_is_sanitised(self):
        self.job("r444444", real_job("r444444", status="failed",
                                     question="ดู C:\\logs\\ocpp.log \u202eevil\u202c\x07 ด้วย",
                                     error="พัง (C:\\LLM\\projects\\data\\x\\tmp.json)\nบรรทัดสอง"))
        j = hub.research_list(SLUG)["jobs"][0]
        self.assertEqual(j["question"], "ดู C:\\logs\\ocpp.log evil ด้วย")      # คำถามของผู้ใช้: ไม่ตัด path
        self.assertNotIn("\u202e", j["question"])
        self.assertEqual(j["error"], "พัง (tmp.json) บรรทัดสอง")                  # ข้อผิดพลาด: path เหลือชื่อไฟล์

    def test_non_jobs_bad_names_and_huge_files_are_skipped(self):
        self.job("r555555", real_job("r555555"))
        self.rdir.mkdir(parents=True, exist_ok=True)
        (self.rdir / "notes.cache.json").write_text("{}", encoding="utf-8")        # ชื่อมีจุด = ไม่ใช่งาน
        (self.rdir / "sidecar.json").write_text('{"x": 1}', encoding="utf-8")       # ไม่มีคำถาม/สถานะ
        (self.rdir / "broken.json").write_text("{not json", encoding="utf-8")
        (self.rdir / "list.json").write_text("[1, 2]", encoding="utf-8")
        (self.rdir / "huge.json").write_text(json.dumps({"question": "x" * (hub.RESEARCH_FILE_MAX + 10)}),
                                             encoding="utf-8")
        self.assertEqual([j["id"] for j in hub.research_list(SLUG)["jobs"]], ["r555555"])

    def test_listing_does_not_create_folders(self):
        self.assertEqual(hub.research_list(SLUG), {"jobs": [], "total": 0, "running": 0})
        self.assertFalse((self.data / SLUG).exists())

    def test_order_newest_first_and_limit(self):
        now = time.time()
        for i in range(hub.RESEARCH_LIST_MAX + 5):
            self.job("r%06x" % i, real_job("r%06x" % i, status="done", created=iso(now - 1000 + i)))
        d = hub.research_list(SLUG)
        self.assertEqual(d["total"], hub.RESEARCH_LIST_MAX + 5)
        self.assertEqual(len(d["jobs"]), hub.RESEARCH_LIST_MAX)
        self.assertEqual(d["jobs"][0]["id"], "r%06x" % (hub.RESEARCH_LIST_MAX + 4))

    def test_stale_and_cancel_flag(self):
        old = time.time() - hub.RESEARCH_STALE_S - 60
        self.job("r666666", real_job("r666666", updated=iso(old), heartbeat=old))
        self.job("r777777", real_job("r777777"))
        (self.rdir / "r777777.cancel").write_text("{}", encoding="utf-8")
        d = hub.research_list(SLUG)
        jobs = {j["id"]: j for j in d["jobs"]}
        self.assertTrue(jobs["r666666"]["stale"])
        self.assertEqual(jobs["r777777"]["status"], "cancelling")
        self.assertTrue(jobs["r777777"]["cancel_requested"])
        self.assertEqual(d["running"], 1)                     # ค้างไม่นับว่ากำลังทำ

    def test_running_total_counts_all_projects(self):
        self.job("r888888", real_job("r888888"))
        other = self.data / "other" / "research"
        other.mkdir(parents=True)
        (other / "r999999.json").write_text(json.dumps(real_job("r999999", project="other")), encoding="utf-8")
        self.store.write_text(json.dumps([{"slug": SLUG, "name": "a", "port": 8101},
                                          {"slug": "other", "name": "b", "port": 8102}]), encoding="utf-8")
        self.assertEqual(hub.research_running_total(), 2)


# ============================================================================ HTTP บนพอร์ตโปรเจกต์
class ResearchHttpTests(_Env):
    def setUp(self):
        super().setUp()
        self.mcp, self.mcp_cls = fake_server({("POST", "/fast/" + SLUG): (200, {
            "jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "ยกเลิกแล้ว"}],
                                                  "isError": False}})})
        p = mock.patch.object(hub, "MCP_LOCAL_PORT", self.mcp.server_address[1])
        p.start()
        self.patches.append(p)

    def tearDown(self):
        self.mcp.shutdown()
        self.mcp.server_close()
        super().tearDown()

    def test_listing_origin_rules(self):
        self.job("r3fa9c1d2", real_job())
        st, d = self.get("/_qwen/research")
        self.assertEqual(st, 200)
        self.assertEqual(d["jobs"][0]["id"], "r3fa9c1d2")
        self.assertEqual(self.get("/_qwen/research", origin=None)[0], 200)              # สคริปต์ในเครื่อง
        self.assertEqual(self.get("/_qwen/research", origin="http://127.0.0.1:8101")[0], 403)   # โปรเจกต์อื่น
        self.assertEqual(self.get("/_qwen/research", origin="https://evil.example")[0], 403)
        self.assertEqual(self.get("/_qwen/research", origin=None, extra={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.get("/_qwen/research/r3fa9c1d2")[1]["job"]["id"], "r3fa9c1d2")
        self.assertEqual(self.get("/_qwen/research/nope-1")[0], 404)
        self.assertEqual(self.get("/_qwen/research/..%2Fsecret")[0], 400)
        self.assertEqual(self.up_cls.seen, [], "ห้ามส่งต่อไป llama-server")

    def test_cancel_writes_flag_and_calls_mcp(self):
        self.job("r3fa9c1d2", real_job())
        st, d = self.post("/_qwen/research/r3fa9c1d2/cancel")
        self.assertEqual(st, 200, d)
        self.assertTrue(d["ok"])
        self.assertTrue(d["flag"])
        self.assertEqual(d["mcp"], "ok")
        self.assertEqual(d["job"]["status"], "cancelling")
        flag = json.loads((self.rdir / "r3fa9c1d2.cancel").read_text(encoding="utf-8"))
        self.assertTrue(flag["cancel"])
        (method, path, headers, body), = self.mcp_cls.seen
        self.assertEqual((method, path), ("POST", "/fast/" + SLUG))
        self.assertEqual(headers.get("authorization"), "Bearer " + self.token)
        self.assertNotIn("origin", headers)
        rpc = json.loads(body.decode("utf-8"))
        self.assertEqual(rpc["method"], "tools/call")
        self.assertEqual(rpc["params"], {"name": "local_do", "arguments": {"action": "research_cancel",
                                                                              "id": "r3fa9c1d2"}})
        self.assertEqual(self.up_cls.seen, [])

    def test_cancel_works_with_mcp_down_via_flag(self):
        self.job("r3fa9c1d2", real_job())
        with mock.patch.object(hub, "MCP_LOCAL_PORT", free_port()):
            st, d = self.post("/_qwen/research/r3fa9c1d2/cancel")
        self.assertEqual(st, 200, d)
        self.assertEqual((d["flag"], d["mcp"]), (True, "down"))
        self.assertTrue((self.rdir / "r3fa9c1d2.cancel").exists())

    def test_mcp_tool_error_or_confirm_is_not_reported_as_ok(self):
        self.job("r3fa9c1d2", real_job())
        self.mcp_cls.routes[("POST", "/fast/" + SLUG)] = (200, {"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "text", "text": "ไม่รู้จัก action"}], "isError": True}})
        self.assertEqual(self.post("/_qwen/research/r3fa9c1d2/cancel")[1]["mcp"], "refused")
        self.mcp_cls.routes[("POST", "/fast/" + SLUG)] = (200, {"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "text", "text": "ต้องยืนยัน confirm_token=abc"}], "isError": False}})
        self.assertEqual(self.post("/_qwen/research/r3fa9c1d2/cancel")[1]["mcp"], "needs_confirm")

    def test_cancel_rules(self):
        self.job("r3fa9c1d2", real_job())
        self.job("rdonedone", real_job("rdonedone", status="done"))
        self.assertEqual(self.post("/_qwen/research/r3fa9c1d2/cancel", ctype="text/plain")[0], 415)
        self.assertEqual(self.post("/_qwen/research/r3fa9c1d2/cancel", ctype=None)[0], 415)
        self.assertEqual(self.post("/_qwen/research/r3fa9c1d2/cancel", origin="http://127.0.0.1:8101")[0], 403)
        self.assertEqual(self.post("/_qwen/research/r3fa9c1d2/cancel", origin="https://evil.example")[0], 403)
        self.assertEqual(self.post("/_qwen/research/r3fa9c1d2/cancel",
                                   body=b"{" + b" " * (hub.RESEARCH_BODY_MAX + 10) + b"}")[0], 413)
        self.assertFalse((self.rdir / "r3fa9c1d2.cancel").exists(), "คำขอที่ถูกปฏิเสธต้องไม่เขียนธง")
        st, d = self.post("/_qwen/research/rdonedone/cancel")
        self.assertEqual((st, d["error"]), (409, "not_running"))
        self.assertEqual(self.post("/_qwen/research/nothere/cancel")[0], 404)
        self.assertEqual(self.post("/_qwen/research/a%20b/cancel")[0], 400)
        self.assertEqual(self.post("/_qwen/research")[0], 405)
        self.assertEqual(self.post("/_qwen/research/r3fa9c1d2/delete")[0], 405)
        self.assertEqual(_req(self.port, "DELETE", "/_qwen/research/r3fa9c1d2", {"Origin": self.own})[0], 405)
        self.assertTrue((self.rdir / "r3fa9c1d2.json").exists(), "ไม่มีทางลบไฟล์งาน")
        self.assertEqual(self.mcp_cls.seen, [])
        self.assertEqual(self.up_cls.seen, [])


# ============================================================================ สถานะบริการ
class ServicesTests(_Env):
    with_proxy = False

    def setUp(self):
        super().setUp()
        self.embed, self.embed_cls = fake_server({("GET", "/health"): (200, {"status": "ok"})})
        self.mcp, self.mcp_cls = fake_server({("GET", "/mcp"): (200, {"status": "ok", "modules_failed": {}})})
        self.web, self.web_cls = fake_server({("GET", "/mcp"): (200, {"status": "ok", "provider": "builtin"})})
        self.tool = self.tmp / "tools_research.py"
        self.tool.write_text("# stub", encoding="utf-8")
        for name, val in (("EMBED_PORT", self.embed.server_address[1]), ("MCP_LOCAL_PORT", self.mcp.server_address[1]),
                          ("MCP_WEB_PORT", self.web.server_address[1]), ("RESEARCH_TOOL_PY", self.tool)):
            p = mock.patch.object(hub, name, val)
            p.start()
            self.patches.append(p)

    def tearDown(self):
        for s in (self.embed, self.mcp, self.web):
            s.shutdown()
            s.server_close()
        super().tearDown()

    def test_all_ok_and_token_only_to_mcps(self):
        self.job("r3fa9c1d2", real_job())
        d = hub._svc_probe()
        self.assertEqual(d["embed"]["state"], "ok")
        self.assertEqual(d["mcp"]["state"], "ok")
        self.assertEqual((d["web"]["state"], d["web"]["provider"]), ("ok", "builtin"))
        self.assertEqual((d["research"]["state"], d["research"]["running"]), ("ok", 1))
        self.assertNotIn("authorization", self.embed_cls.seen[0][2], "ห้ามส่งโทเคนให้พอร์ต embedding")
        self.assertEqual(self.mcp_cls.seen[0][2].get("authorization"), "Bearer " + self.token)
        self.assertEqual(self.web_cls.seen[0][2].get("authorization"), "Bearer " + self.token)

    def test_degraded_states(self):
        self.embed_cls.routes[("GET", "/health")] = (503, {"error": "loading"})
        self.mcp_cls.routes[("GET", "/mcp")] = (200, {"modules_failed": {"tools_research": "SyntaxError"}})
        self.web_cls.routes[("GET", "/mcp")] = (200, {"provider": "<b>x</b>"})
        d = hub._svc_probe()
        self.assertEqual((d["embed"]["state"], d["research"]["state"], d["web"]["provider"]),
                         ("loading", "broken", ""))
        self.mcp_cls.routes[("GET", "/mcp")] = (401, {"error": "missing_or_bad_token"})
        d = hub._svc_probe()
        self.assertEqual((d["mcp"]["state"], d["research"]["state"]), ("auth", "down"))
        self.tool.unlink()
        self.assertEqual(hub._svc_probe()["research"]["state"], "missing")

    def test_embed_down_vs_absent(self):
        with mock.patch.object(hub, "EMBED_PORT", free_port()):
            with mock.patch.object(hub, "EMBED_MODEL", self.tmp / "no-model.gguf"):
                self.assertEqual(hub._svc_probe()["embed"]["state"], "absent")
            with mock.patch.object(hub, "EMBED_MODEL", self.tool):
                self.assertEqual(hub._svc_probe()["embed"]["state"], "down")

    def test_cached_within_ttl_and_refreshed_in_background(self):
        calls = []

        def fake_probe():
            calls.append(1)
            return {"n": len(calls)}
        with mock.patch.object(hub, "_svc", {"doc": None, "at": 0.0, "busy": False}), \
                mock.patch.object(hub, "_svc_first", threading.Event()), \
                mock.patch.object(hub, "_svc_probe", fake_probe):
            self.assertEqual(hub.services_status(wait=3.0), {"n": 1})
            self.assertEqual(hub.services_status(), {"n": 1})
            self.assertEqual(len(calls), 1, "ภายใน SVC_TTL ต้องไม่ตรวจซ้ำ")
            hub._svc["at"] -= hub.SVC_TTL + 1
            self.assertEqual(hub.services_status(), {"n": 1})     # ตอบค่าเดิมทันที แล้วตรวจใหม่เบื้องหลัง
            for _ in range(50):
                if hub._svc["doc"] == {"n": 2}:
                    break
                time.sleep(0.05)
            self.assertEqual(hub.services_status(), {"n": 2})

    def test_probe_failure_never_breaks_status(self):
        def boom():
            raise RuntimeError("x")
        with mock.patch.object(hub, "_svc", {"doc": None, "at": 0.0, "busy": False}), \
                mock.patch.object(hub, "_svc_first", threading.Event()), \
                mock.patch.object(hub, "_svc_probe", boom), mock.patch.object(hub, "safe_print"):
            self.assertIsNone(hub.services_status(wait=2.0))


class HubApiServicesTests(_Env):
    with_proxy = False

    def test_projects_and_services_endpoints(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), hub.HubHandler)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        doc = {"embed": {"state": "ok"}, "research": {"state": "ok", "running": 0}}
        try:
            with mock.patch.object(hub, "services_status", return_value=doc), \
                    mock.patch.object(hub, "upstream_alive", return_value=False), \
                    mock.patch.object(hub, "gpu_status_safe", return_value=None):
                st, d = _req(port, "GET", "/api/projects", {"Host": "127.0.0.1:%d" % port})
                self.assertEqual(st, 200)
                self.assertEqual(d["services"], doc)
                st, d = _req(port, "GET", "/api/services", {"Host": "127.0.0.1:%d" % port})
                self.assertEqual((st, d), (200, {"services": doc}))
        finally:
            srv.shutdown()
            srv.server_close()


class OwnDataRouteTests(unittest.TestCase):
    def test_research_is_project_data(self):
        for r in ("/_qwen/research", "/_qwen/research/r1/cancel"):
            self.assertTrue(hub.is_own_data_route(r), r)
        self.assertFalse(hub.is_own_data_route("/_qwen/researchx"))


if __name__ == "__main__":
    unittest.main()
