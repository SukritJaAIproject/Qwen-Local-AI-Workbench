# -*- coding: utf-8 -*-
"""
เทสต์การแนบโทเคนถึง llama-server ของ gpu_profile.py / gpu_bench.py (router เปิดด้วย --api-key-file ตั้งแต่ 2026-09-30)

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

ทำไมต้องมี
  llama-server b10984 ที่มีคีย์ตอบ 401 ทุกเส้นทางยกเว้น /health (วัดแล้ว: /models /v1/models /slots ก็ต้องใช้)
  ตัวเปิดใช้ gpu_profile --wait-idle / --compare-running ก่อนรีสตาร์ต router และ gpu_bench วัดความเร็วผ่าน router
  ถ้าไม่แนบโทเคน ตัวเปิดจะ "ตรวจสถานะแชตไม่ได้" ตลอดไป และไม่มีวันรีสตาร์ต router ตอนเสียบ eGPU

สิ่งที่ตรวจ (router ปลอมบนพอร์ตสุ่มที่ทำตัวแบบ --api-key-file: ไม่มี/ผิด Bearer = 401)
  * http_json แนบ Bearer จากไฟล์โทเคน (LLM_LOCAL_TOKEN_FILE) เฉพาะ 127.0.0.1/localhost — host อื่นไม่แนบ
  * ไม่มีไฟล์ / ไฟล์ผิดรูปแบบ = ไม่แนบ (ไม่สร้างไฟล์ใหม่เอง) และไม่วิ่งผ่าน HTTP_PROXY ของ environment
  * wait_idle ที่เจอ 401 คืน EXIT_AUTH (13) ทันที ไม่รอจนหมดเวลาแล้วรายงานผิดว่า "ยังมีแชตตอบอยู่"
  * gpu_bench บอกสาเหตุ 401 ชัดเจน และวัดผ่าน router ที่ต้องใช้คีย์ได้
ปลอดภัยต่อระบบจริง: โทเคนเป็นค่าทดสอบในโฟลเดอร์ชั่วคราว ไม่อ่าน C:\\LLM\\secrets ไม่แตะ router จริง

ชุด LiveRouterKeyTests (ต้องตั้ง LLM_SECURITY_LIVE=1) ตรวจ router 8099 + hub ตัวจริงหลัง deploy:
  เว็บอื่นส่ง POST แบบ text/plain (simple request ไม่มี preflight) / DNS rebinding (Host ปลอม) ต้องได้ 401
  และพอร์ตโปรเจกต์ของ hub ยังคุยกับ router ได้ (hub แนบคีย์ให้) — ไม่อ่านไฟล์โทเคน ไม่แชต ไม่โหลดโมเดล
"""
import http.client
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gpu_profile as gp  # noqa: E402
import gpu_bench  # noqa: E402

MODEL = "Qwen3-4B-Instruct-2507-Q4_K_M"


class _KeyedRouter(BaseHTTPRequestHandler):
    """router ปลอมแบบ llama-server --api-key-file: /health สาธารณะ ที่เหลือต้องมี Bearer ที่ตรง"""
    key = ""
    seen = []

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authed(self):
        got = self.headers.get("Authorization")
        type(self).seen.append((self.command, self.path, got))
        return got == "Bearer " + type(self).key

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"status": "ok"})
        if not self._authed():
            return self._send(401, {"error": {"code": 401, "message": "Invalid API Key"}})
        if self.path == "/models":
            return self._send(200, {"data": [{"id": MODEL, "status": {"value": "loaded", "args": []}}]})
        if self.path.startswith("/slots"):
            return self._send(200, [{"id": 0, "id_task": -1, "is_processing": False}])
        return self._send(404, {})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if not self._authed():
            return self._send(401, {"error": {"code": 401}})
        return self._send(200, {"choices": [{"message": {"content": "ok"}}],
                                "timings": {"predicted_n": 8, "predicted_ms": 100.0, "predicted_per_second": 80.0,
                                            "prompt_n": 5, "prompt_ms": 10.0, "prompt_per_second": 500.0}})


class RouterAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="routerauth-")
        self.key = secrets.token_hex(32)            # ค่าทดสอบ ไม่ใช่โทเคนจริง
        self.token_file = os.path.join(self.tmp, "local-services.token")
        with open(self.token_file, "w", encoding="ascii", newline="\n") as fh:
            fh.write(self.key + "\n")
        _KeyedRouter.key = self.key
        _KeyedRouter.seen = []
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _KeyedRouter)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]
        self.env = mock.patch.dict(os.environ, {gp.LOCAL_TOKEN_ENV: self.token_file})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.srv.shutdown()
        self.srv.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_http_json_sends_bearer_to_loopback_router(self):
        doc = gp.http_json("http://127.0.0.1:%d/models" % self.port)
        self.assertEqual(doc["data"][0]["id"], MODEL)
        self.assertEqual(_KeyedRouter.seen[-1][2], "Bearer " + self.key)
        self.assertEqual(gp.router_auth_headers("http://localhost:%d/slots" % self.port),
                         {"Authorization": "Bearer " + self.key})

    def test_token_never_sent_to_other_hosts(self):
        for url in ("http://192.168.1.10:8099/models", "http://example.com/models",
                    "http://127.0.0.1.evil.example/models", "http://[::1]:8099/models", "not a url"):
            with self.subTest(url=url):
                self.assertEqual(gp.router_auth_headers(url), {})

    def test_missing_or_malformed_token_file_sends_nothing(self):
        for content in (None, b"", b"not-a-token", b"\xef\xbb\xbf" + b"z" * 64, self.key.encode()[:63]):
            with self.subTest(content=content):
                if content is None:
                    os.remove(self.token_file)
                else:
                    with open(self.token_file, "wb") as fh:
                        fh.write(content)
                self.assertEqual(gp.router_auth_headers("http://127.0.0.1:%d/models" % self.port), {})
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    gp.http_json("http://127.0.0.1:%d/models" % self.port)
                self.assertEqual(cm.exception.code, 401)
                if content is None:
                    # การสร้างโทเคนเป็นงานของ secrets_util/ตัวเปิด — gpu_profile ห้ามสร้างเอง
                    self.assertFalse(os.path.exists(self.token_file))

    def test_env_proxy_is_ignored(self):
        # HTTP_PROXY ชี้ไปที่ที่ไม่มีใครฟัง: ถ้า http_json ใช้ proxy ของ env จะต่อไม่ติด (และโทเคนจะไปที่ proxy)
        with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9",
                                          "NO_PROXY": "", "no_proxy": ""}):
            doc = gp.http_json("http://127.0.0.1:%d/models" % self.port)
        self.assertEqual(doc["data"][0]["id"], MODEL)

    def test_wait_idle_and_activity_work_with_key(self):
        busy, notes, _sig = gp.router_activity(self.port)
        self.assertFalse(busy, notes)
        lines = []
        rc = gp.wait_idle(self.port, 30, out=lines.append, sleep=lambda s: None,
                          clock=iter(range(0, 1000, 5)).__next__)
        self.assertEqual(rc, gp.EXIT_OK, lines)

    def test_wait_idle_reports_rejected_token_immediately(self):
        _KeyedRouter.key = secrets.token_hex(32)       # router จำโทเคนชุดเก่า
        lines = []
        rc = gp.wait_idle(self.port, 180, out=lines.append, sleep=lambda s: None,
                          clock=iter(range(0, 100000, 1)).__next__)
        self.assertEqual(rc, gp.EXIT_AUTH)
        self.assertEqual(gp.EXIT_AUTH, 13, "ตัวเปิดเทียบกับเลข 13 ตรงๆ (Restart-RouterWhenIdle)")
        self.assertIn("401", " ".join(lines))
        self.assertNotIn(self.key, " ".join(lines))

    def test_gpu_bench_through_keyed_router(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gpu_bench.main(["--port", str(self.port), "--models", MODEL, "--tokens", "8",
                                 "--profile", os.path.join(self.tmp, "none.json"), "--out-dir", self.tmp])
        self.assertEqual(rc, gpu_bench.EXIT_OK, buf.getvalue()[-600:])
        posts = [s for s in _KeyedRouter.seen if s[0] == "POST"]
        self.assertTrue(posts and all(a == "Bearer " + self.key for _m, _p, a in posts))
        self.assertNotIn(self.key, buf.getvalue())

    def test_gpu_bench_explains_401(self):
        os.remove(self.token_file)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gpu_bench.main(["--port", str(self.port), "--out-dir", self.tmp])
        self.assertEqual(rc, gpu_bench.EXIT_NO_ROUTER)
        self.assertIn("401", buf.getvalue())


LIVE = os.environ.get("LLM_SECURITY_LIVE") == "1"
# ชี้ router ทดสอบบนพอร์ตสำรองได้ (เช่น 8199 ที่เปิดด้วยโทเคนทดสอบ) โดยไม่แตะตัวจริง
LIVE_ROUTER_PORT = int(os.environ.get("LLM_LIVE_ROUTER_PORT") or 8099)
LIVE_HUB_PORT = int(os.environ.get("LLM_LIVE_HUB_PORT") or 8100)


def _raw(port, method, path, headers=None, body=None, host=None, timeout=10):
    """คำขอดิบที่กำหนด Host เองได้ (จำลอง DNS rebinding) — คืน (status, body)"""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    c.putheader("Host", host or "127.0.0.1:%d" % port)
    for k, v in (headers or {}).items():
        c.putheader(k, v)
    data = body.encode("utf-8") if isinstance(body, str) else body
    if data is not None:
        c.putheader("Content-Length", str(len(data)))
    c.endheaders(data)
    r = c.getresponse()
    raw = r.read()
    c.close()
    return r.status, raw


@unittest.skipUnless(LIVE, "ตั้ง LLM_SECURITY_LIVE=1 เพื่อตรวจ router/hub ตัวจริง")
class LiveRouterKeyTests(unittest.TestCase):
    """router ตัวจริงต้องเปิดด้วย --api-key-file (finding: llama-server ไม่ตรวจ Host และ CORS กันแค่ "การอ่าน"
    — เดิมเว็บไหนก็สั่ง /tokenize /v1/chat/completions /models/load ด้วย POST text/plain ได้ และหน้า DNS rebinding
    อ่าน /props /slots ได้)  เทสต์นี้ไม่ใช้คีย์เลย: ทุกคำขอที่ส่งตรงถึง router ต้องถูกปฏิเสธก่อนถึงตัวจัดการ
    ชื่อโมเดลในคำขอเป็นชื่อที่ไม่มีอยู่จริง — ถ้าคีย์หายไป router จะตอบ 400/404 ไม่ใช่โหลดโมเดลของผู้ใช้"""

    BOGUS = "no-such-model-security-probe"

    def test_router_started_with_key_file_path_not_value(self):
        ps = ("$c = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort %d -State Listen -EA SilentlyContinue"
              " | Select-Object -First 1; if ($c) { (Get-CimInstance Win32_Process -Filter ('ProcessId=' +"
              " $c.OwningProcess)).CommandLine }" % LIVE_ROUTER_PORT)
        cl = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                            timeout=60).stdout
        # ข้อความตอนล้มสั้นๆ พอ ไม่พ่น command line ทั้งบรรทัด (รายการ --cors-origins ยาว 162 origin)
        self.assertTrue("llama-server" in cl.lower(), "พอร์ต %d ไม่ใช่ llama-server" % LIVE_ROUTER_PORT)
        self.assertTrue(re.search(r"--api-key-file\s+\S*local-services\.token", cl),
                        "router ไม่ได้เปิดด้วย --api-key-file <ไฟล์โทเคน>")
        # ค่าคีย์ห้ามอยู่บน command line (ใครในเครื่องก็อ่านได้ และ router ส่ง argv ต่อให้โมเดลลูก)
        self.assertFalse(re.search(r"--api-key\s", cl), "router เปิดด้วย --api-key <ค่า> บน command line")
        self.assertFalse(re.search(r"\b[0-9a-fA-F]{64}\b", cl), "มีสตริงหน้าตาเหมือนโทเคนบน command line")

    def test_health_stays_public(self):
        st, _b = _raw(LIVE_ROUTER_PORT, "GET", "/health")
        self.assertEqual(st, 200)

    def test_cross_site_simple_post_is_rejected(self):
        body = json.dumps({"model": self.BOGUS, "content": "x"})
        simple = {"Content-Type": "text/plain;charset=UTF-8", "Origin": "http://evil.example",
                  "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "no-cors"}
        for path in ("/tokenize", "/v1/chat/completions", "/models/load", "/models/unload"):
            with self.subTest(path=path):
                st, _b = _raw(LIVE_ROUTER_PORT, "POST", path, simple, body)
                self.assertEqual(st, 401)

    def test_rebinding_reads_are_rejected(self):
        for path in ("/props", "/v1/models", "/models", "/slots?model=" + self.BOGUS, "/metrics"):
            with self.subTest(path=path):
                st, _b = _raw(LIVE_ROUTER_PORT, "GET", path, host="attacker.example:%d" % LIVE_ROUTER_PORT)
                self.assertEqual(st, 401)

    def test_hub_project_port_still_reaches_router(self):
        st, raw = _raw(LIVE_HUB_PORT, "GET", "/api/projects")
        self.assertEqual(st, 200)
        projects = json.loads(raw.decode("utf-8")).get("projects") or []
        self.assertTrue(projects, "hub ไม่มีโปรเจกต์ให้ทดสอบ")
        port = int(projects[0]["port"])
        for path in ("/props", "/v1/models"):
            with self.subTest(path=path):
                st, raw = _raw(port, "GET", path)
                self.assertEqual(st, 200, "hub ส่งต่อถึง router ไม่ได้ (ไม่ได้แนบคีย์?)")
                self.assertIsNone(re.search(rb"\b[0-9a-fA-F]{64}\b", raw), "มีสตริงหน้าตาเหมือนโทเคนหลุดมา")


if __name__ == "__main__":
    unittest.main()
