# -*- coding: utf-8 -*-
"""
เทสต์ความปลอดภัยของ hub + boot.js (รอบแก้ 2026-09-30: สัญญา C2/C3/C4)

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

สิ่งที่ตรวจ
  * boot_config ส่งโทเคนให้ WebUI ในรูปที่ bundle ของ WebUI b10984 ใช้จริง: headers = "สตริง JSON" ของ object
    ({"Authorization": "Bearer <โทเคน>"}) + useProxy=false (ถอด --ui-mcp-proxy แล้ว)
  * /props ของพอร์ตโปรเจกต์ไม่มีโทเคน และ proxy ไม่ส่ง Access-Control-* ของ llama-server ต่อ
  * Host ที่ไม่ใช่ 127.0.0.1/localhost:<พอร์ตนี้> ได้ 403 ทั้ง hub และพอร์ตโปรเจกต์ (กัน DNS rebinding)
  * คำขอเขียนจากเว็บอื่น (Origin แปลก / ไม่มี Origin แต่ Sec-Fetch-Site เป็น cross-site/same-site) ได้ 403
  * boot.js: เบราว์เซอร์ใหม่ได้เซิร์ฟเวอร์ + โทเคน + รายการ "อนุญาตเสมอ" ว่าง, รุ่นเก่าได้ของใหม่โดยคง enabled
    และเซิร์ฟเวอร์ที่ผู้ใช้เพิ่มเอง, โทเคนใหม่ถึงเบราว์เซอร์โดยไม่ต้องขยับเลขรุ่น, ไม่แตะสิทธิ์ที่ผู้ใช้ให้ไว้

ปลอดภัยต่อระบบจริง: โทเคนเป็นค่าทดสอบในโฟลเดอร์ชั่วคราว (LLM_LOCAL_TOKEN_FILE) ไม่แตะ C:\\LLM\\secrets
DATA_ROOT ชี้โฟลเดอร์ชั่วคราว, upstream เป็นเซิร์ฟเวอร์ปลอมบนพอร์ตสุ่ม, ไม่มีคำขอเขียนที่สำเร็จไปถึง settings.json
"""
import http.client
import importlib.util
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HUB = r"C:\LLM\projects\hub.py"
BOOT_JS = r"C:\LLM\projects\static\boot.js"
TOKEN_ENV = "LLM_LOCAL_TOKEN_FILE"


def load_hub():
    sys.path.insert(0, os.path.dirname(HUB))
    spec = importlib.util.spec_from_file_location("hub_security_under_test", HUB)
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


try:
    hub = load_hub() if os.path.isfile(HUB) else None
    HUB_ERR = None if hub else "ไม่มี hub.py"
except Exception as e:      # noqa: BLE001
    hub, HUB_ERR = None, "import hub.py ไม่ได้: %s: %s" % (type(e).__name__, e)


class HubImportTests(unittest.TestCase):
    """เดิมทุกคลาสมี skipIf(hub is None): hub.py ที่ import ไม่ได้ (syntax error) ให้ผล "OK (skipped=N)"
    เทสต์ความปลอดภัยหายไปทั้งชุดโดยไม่มีอะไรล้ม — ตอนนี้ import ไม่ได้ = ล้มดังๆ ตรงนี้ (และคลาสอื่น error ตาม)"""

    def test_hub_imported(self):
        self.assertIsNotNone(hub, HUB_ERR)


def node_exe():
    for p in (shutil.which("node"), r"C:\Program Files\nodejs\node.exe"):
        if p and os.path.isfile(p):
            return p
    return None


PROJECT = {"slug": "sectest", "name": "sectest", "port": 0, "system_prompt": "", "think": "off", "extend": True}


class _TokenMixin:
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hubsec-")
        self.token = secrets.token_hex(32)          # ค่าทดสอบ ไม่ใช่โทเคนจริง
        self.token_file = Path(self.tmp) / "secrets" / "local-services.token"
        self.token_file.parent.mkdir(parents=True)
        self.token_file.write_text(self.token + "\n", encoding="ascii")
        self.patches = [mock.patch.dict(os.environ, {TOKEN_ENV: str(self.token_file)}),
                        mock.patch.object(hub, "DATA_ROOT", Path(self.tmp) / "data")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class BootConfigTokenTests(_TokenMixin, unittest.TestCase):
    def test_entries_carry_bearer_header_as_json_string(self):
        rows = hub.mcp_servers(dict(PROJECT))
        self.assertEqual([r["id"] for r in rows], ["websearch", "local", "local-full"])
        for r in rows:
            with self.subTest(id=r["id"]):
                self.assertIsInstance(r["headers"], str)       # WebUI: typeof headers == "string" เท่านั้น
                self.assertEqual(json.loads(r["headers"]), {"Authorization": "Bearer " + self.token})
                self.assertIs(r["useProxy"], False)
        self.assertIn("/fast/sectest", rows[1]["url"])
        self.assertIn("/mcp/sectest", rows[2]["url"])

    def test_props_variant_has_no_token(self):
        rows = hub.mcp_servers(dict(PROJECT), with_auth=False)
        self.assertTrue(all("headers" not in r for r in rows))
        self.assertNotIn(self.token, json.dumps(rows))

    def test_malformed_or_missing_token_means_no_headers(self):
        self.token_file.write_text("not-a-token", encoding="ascii")
        self.assertIsNone(hub.local_token())
        self.assertTrue(all("headers" not in r for r in hub.mcp_servers(dict(PROJECT))))

    @unittest.skipUnless(os.path.isfile(r"C:\LLM\secrets_util.py"), "ไม่มี secrets_util.py")
    def test_missing_token_file_is_created_by_helper(self):
        self.token_file.unlink()
        tok = hub.local_token()
        self.assertIsNotNone(tok)
        self.assertRegex(tok, r"^[0-9a-fA-F]{64}$")
        self.assertTrue(self.token_file.is_file())
        self.assertNotEqual(tok, self.token)

    def test_tool_policy_asks_for_write_and_run_tools(self):
        pol = hub.boot_config(dict(PROJECT))["toolPolicy"]
        self.assertIn("mcp-local:local_do", pol["ask"])
        for name in ("write_file", "edit_file", "exec_shell_command", "task_start", "media_transcode"):
            self.assertIn("mcp-local-full:" + name, pol["ask"])
        self.assertNotIn("mcp-local:local_read", pol["ask"])
        self.assertEqual(pol["allow"], [])
        self.assertEqual(hub.BOOT_VERSION, 3)

    def test_shell_embeds_token_only_inside_boot_config(self):
        with mock.patch.object(hub, "upstream_models", return_value=[]), \
                mock.patch.object(hub, "upstream_model", return_value=""):
            page = hub.build_shell(dict(PROJECT, port=8175), [dict(PROJECT, port=8175)], "", "en")
        self.assertIn(self.token, page)
        start = page.index("window.__QWEN_BOOT__ = ")
        end = page.index("window.qwenShell = ", start)
        self.assertEqual(page.count(self.token), page[start:end].count(self.token))
        self.assertNotIn("</script>" + self.token, page)


class OriginHostRuleTests(unittest.TestCase):
    def test_origin_rules(self):
        ok = hub.origin_allowed
        self.assertTrue(ok({"Origin": "http://127.0.0.1:8103"}))
        self.assertTrue(ok({"Origin": "http://localhost:8100"}))
        for bad in ("http://evil.example", "null", "http://127.0.0.1:8180", "http://127.0.0.1:8099",
                    "http://127.0.0.1:8100.evil.com", "https://127.0.0.1:8100", "http://127.0.0.1:8100/"):
            with self.subTest(origin=bad):
                self.assertFalse(ok({"Origin": bad}))
        self.assertTrue(ok({}))                                      # curl / สคริปต์ในเครื่อง
        self.assertTrue(ok({"Sec-Fetch-Site": "none"}))              # พิมพ์ในแถบที่อยู่
        self.assertTrue(ok({"Sec-Fetch-Site": "same-origin"}))
        self.assertFalse(ok({"Sec-Fetch-Site": "cross-site"}))       # <img src> จากเว็บอื่น
        self.assertFalse(ok({"Sec-Fetch-Site": "same-site"}))        # เว็บบนพอร์ตอื่นของ 127.0.0.1

    def test_host_rules(self):
        ok = hub.host_allowed
        self.assertTrue(ok({"Host": "127.0.0.1:8101"}, 8101))
        self.assertTrue(ok({"Host": "LOCALHOST:8101"}, 8101))
        self.assertTrue(ok({}, 8101))
        for bad in ("evil.example:8101", "127.0.0.1:8102", "127.0.0.1", "localhost.:8101", "[::1]:8101"):
            with self.subTest(host=bad):
                self.assertFalse(ok({"Host": bad}, 8101))


def _raw(port, head, timeout=5):
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    try:
        s.sendall(head.encode("latin-1"))
        data = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\r\n\r\n" in data and b"Content-Length: " in data:
                h, _, body = data.partition(b"\r\n\r\n")
                n = int(h.split(b"Content-Length: ", 1)[1].split(b"\r\n", 1)[0])
                if len(body) >= n:
                    break
        return data
    finally:
        s.close()


def _req(port, method, path, headers=None, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, data


class HubHostHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = hub.ThreadingHTTPServer(("127.0.0.1", 0), hub.HubHandler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_rebinding_host_is_forbidden_for_every_method(self):
        for method in ("GET", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                st, _h, _d = _req(self.port, method, "/api/settings",
                                  {"Host": "attacker.example:%d" % self.port, "Origin": "http://127.0.0.1:8103",
                                   "Content-Type": "application/json"}, b"{}" if method != "GET" else None)
                self.assertEqual(st, 403)

    def test_loopback_hosts_and_http10_without_host_work(self):
        st, _h, _d = _req(self.port, "GET", "/api/settings", {"Host": "localhost:%d" % self.port})
        self.assertEqual(st, 200)
        st, _h, _d = _req(self.port, "GET", "/api/settings")
        self.assertEqual(st, 200)
        data = _raw(self.port, "GET /api/settings HTTP/1.0\r\n\r\n")
        self.assertTrue(data.startswith(b"HTTP/1.0 200") or data.startswith(b"HTTP/1.1 200"), data[:40])

    def test_same_site_write_without_origin_is_forbidden(self):
        st, _h, _d = _req(self.port, "PATCH", "/api/settings",
                          {"Sec-Fetch-Site": "same-site", "Content-Type": "application/json"}, b'{"lang":"en"}')
        self.assertEqual(st, 403)


class _FakeUpstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen = []
    auth = []          # (path, ค่า Authorization ที่ router ได้รับ) — เทียบกับโทเคนทดสอบเท่านั้น

    def log_message(self, *a):
        pass

    def _send(self, obj, ctype="application/json"):
        data = obj if isinstance(obj, bytes) else json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # llama-server ค่าเดิม: สะท้อนทุก origin + credentials — proxy ต้องไม่ส่งต่อ
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        type(self).seen.append(("GET", self.path, self.headers.get("Origin")))
        type(self).auth.append((self.path, self.headers.get("Authorization")))
        if self.path.startswith("/props"):
            self._send({"ui_settings": {}, "model_path": "none"})
        elif self.path.startswith("/v1/models"):
            self._send({"data": [{"id": "Qwen3-4B-Instruct-2507-Q4_K_M"}]})
        elif self.path == "/":
            self._send(b"<html><head></head><body>webui</body></html>", "text/html")
        else:
            self._send({"ok": True})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        type(self).seen.append(("POST", self.path, self.headers.get("Origin")))
        type(self).auth.append((self.path, self.headers.get("Authorization")))
        self._send({"ok": True})

    def do_OPTIONS(self):
        type(self).seen.append(("OPTIONS", self.path, self.headers.get("Origin")))
        self._send({"ok": True})


class ProjectProxySecurityTests(_TokenMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        _FakeUpstream.seen = []
        _FakeUpstream.auth = []
        self.up = ThreadingHTTPServer(("127.0.0.1", 0), _FakeUpstream)
        threading.Thread(target=self.up.serve_forever, daemon=True).start()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), hub.make_proxy_handler("sectest", lambda: [self.proj]))
        self.port = self.srv.server_address[1]
        self.proj = dict(PROJECT, port=self.port)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        for p in (mock.patch.object(hub, "UPSTREAM_PORT", self.up.server_address[1]),
                  mock.patch.object(hub, "upstream_models", return_value=[]),
                  mock.patch.object(hub, "upstream_model", return_value="")):
            p.start()
            self.patches.append(p)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.up.shutdown()
        self.up.server_close()
        super().tearDown()

    def test_shell_needs_our_host(self):
        st, _h, body = _req(self.port, "GET", "/")
        self.assertEqual(st, 200)
        self.assertIn(self.token.encode(), body)
        st, _h, body = _req(self.port, "GET", "/", {"Host": "rebind.example:%d" % self.port})
        self.assertEqual(st, 403)
        self.assertNotIn(self.token.encode(), body)

    def test_props_has_no_token_and_no_upstream_cors(self):
        # Origin แปลกปลอม: ตอนนี้ถูกปฏิเสธตั้งแต่ proxy (GET ที่ถึง router ต้องผ่านกฎ origin ด้วย)
        st, h, body = _req(self.port, "GET", "/props", {"Origin": "http://evil.example"})
        self.assertEqual(st, 403)
        self.assertNotIn(self.token.encode(), body)
        self.assertFalse([k for k in h if k.startswith("access-control-")])
        # หน้าของเรา (Origin อยู่ในรายการ): ได้ props แต่ไม่มีโทเคนและไม่มี CORS ของ llama-server หลุดมา
        st, h, body = _req(self.port, "GET", "/props", {"Origin": "http://127.0.0.1:8175"})
        self.assertEqual(st, 200)
        self.assertNotIn(self.token.encode(), body)
        servers = json.loads(json.loads(body)["ui_settings"]["mcpServers"])
        self.assertTrue(all("headers" not in s for s in servers))
        self.assertFalse([k for k in h if k.startswith("access-control-")])

    def test_foreign_writes_are_forbidden_before_reaching_upstream(self):
        cases = [
            ("POST", "/v1/chat/completions", {"Origin": "http://evil.example"}),
            ("POST", "/v1/chat/completions", {"Origin": "null"}),
            ("POST", "/_qwen/files", {"Origin": "http://127.0.0.1:9999", "X-Filename": "eA=="}),
            ("DELETE", "/_qwen/files/x.txt", {"Sec-Fetch-Site": "cross-site"}),
        ]
        for method, path, h in cases:
            with self.subTest(method=method, path=path, h=h):
                st, _h, _d = _req(self.port, method, path, dict(h, **{"Content-Type": "application/json"}),
                                  b"{}" if method == "POST" else None)
                self.assertEqual(st, 403)
        self.assertEqual(_FakeUpstream.seen, [])
        self.assertFalse((Path(self.tmp) / "data" / "sectest" / "attachments" / "x").exists())

    def test_local_clients_and_our_pages_still_reach_upstream(self):
        body = json.dumps({"model": "m", "messages": [{"role": "user", "content": "x"}]}).encode()
        st, h, _d = _req(self.port, "POST", "/v1/chat/completions", {"Content-Type": "application/json"}, body)
        self.assertEqual(st, 200)
        self.assertFalse([k for k in h if k.startswith("access-control-")])
        st, _h, _d = _req(self.port, "POST", "/v1/chat/completions",
                          {"Content-Type": "application/json", "Origin": "http://127.0.0.1:8175"}, body)
        self.assertEqual(st, 200)
        self.assertEqual([s[0] for s in _FakeUpstream.seen], ["POST", "POST"])

    # ---- router เปิดด้วย --api-key-file: proxy ต้องแนบโทเคนเอง (เบราว์เซอร์ไม่มีโทเคนนี้) ----
    def test_router_token_injected_and_client_value_replaced(self):
        body = json.dumps({"model": "m", "messages": [{"role": "user", "content": "x"}]}).encode()
        for h in ({}, {"Authorization": "Bearer from-webui-settings"}, {"authorization": "Basic eDp5"}):
            with self.subTest(client=h):
                _FakeUpstream.auth = []
                st, rh, data = _req(self.port, "POST", "/v1/chat/completions",
                                    dict(h, **{"Content-Type": "application/json"}), body)
                self.assertEqual(st, 200)
                self.assertEqual(_FakeUpstream.auth, [("/v1/chat/completions", "Bearer " + self.token)])
                self.assertNotIn(self.token.encode(), data)
                self.assertNotIn(self.token, json.dumps(rh))
        _FakeUpstream.auth = []
        st, _h, data = _req(self.port, "GET", "/props")
        self.assertEqual(st, 200)
        self.assertEqual(_FakeUpstream.auth, [("/props", "Bearer " + self.token)])
        self.assertNotIn(self.token.encode(), data)

    def test_webui_page_fetch_carries_router_token(self):
        _FakeUpstream.auth = []
        st, _h, body = _req(self.port, "GET", "/?ui=1")
        self.assertEqual(st, 200)
        self.assertIn(b"webui", body)
        self.assertEqual(_FakeUpstream.auth, [("/", "Bearer " + self.token)])
        self.assertNotIn(self.token.encode(), body)

    def test_no_token_file_passes_client_authorization_through(self):
        self.token_file.write_text("broken", encoding="ascii")
        _FakeUpstream.auth = []
        st, _h, _d = _req(self.port, "GET", "/props", {"Authorization": "Bearer user-own-key"})
        self.assertEqual(st, 200)
        self.assertEqual(_FakeUpstream.auth, [("/props", "Bearer user-own-key")])

    # ---- GET จากเว็บอื่น: router โหลดโมเดลเองเมื่อ GET มี ?model= จึงต้องปฏิเสธก่อนถึง router ----
    def test_cross_site_get_to_router_is_forbidden(self):
        cases = [
            {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Dest": "image"},
            {"Sec-Fetch-Site": "same-site", "Sec-Fetch-Mode": "no-cors"},      # เว็บบนพอร์ตอื่นของ 127.0.0.1
            {"Origin": "http://evil.example", "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "cors"},
            {"Origin": "null"},
        ]
        for path in ("/props?model=gpt-oss-20b-MXFP4", "/slots?model=x", "/v1/models", "/_qwen/files",
                     "/_qwen/project", "/_app/immutable/bundle.js"):
            for h in cases:
                with self.subTest(path=path, h=h):
                    st, _h, body = _req(self.port, "GET", path, h)
                    self.assertEqual(st, 403)
                    self.assertNotIn(self.token.encode(), body)
        st, _h, _d = _req(self.port, "OPTIONS", "/v1/chat/completions",
                          {"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
        self.assertEqual(st, 403)
        self.assertEqual(_FakeUpstream.seen, [], "คำขอจากเว็บอื่นต้องไม่ถึง router เลย")

    def test_same_origin_local_and_typed_gets_still_work(self):
        for h in ({}, {"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors"},
                  {"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate"},
                  {"Origin": "http://127.0.0.1:8175", "Sec-Fetch-Site": "same-origin"}):
            with self.subTest(h=h):
                st, _h, _d = _req(self.port, "GET", "/props?model=m", h)
                self.assertEqual(st, 200)

    def test_links_from_other_sites_still_open_our_pages(self):
        # ลิงก์/บุ๊กมาร์กจากเว็บอื่นเปิดหน้า shell / หน้าแชตได้ (ไม่แตะ router) — กรอบ iframe กันด้วย X-Frame-Options
        nav = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        st, h, _d = _req(self.port, "GET", "/", nav)
        self.assertEqual(st, 200)
        self.assertEqual(h.get("x-frame-options"), "SAMEORIGIN")
        st, _h, _d = _req(self.port, "GET", "/_qwen/static/boot.js", {"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(st, 200)


class UpstreamHelperAuthTests(_TokenMixin, unittest.TestCase):
    """ตัวช่วยที่ hub ถาม router เอง (รายชื่อโมเดล / props) ต้องแนบโทเคนด้วย ไม่งั้นได้ 401 = แถบโมเดลว่าง"""

    def setUp(self):
        super().setUp()
        _FakeUpstream.auth = []
        self.up = ThreadingHTTPServer(("127.0.0.1", 0), _FakeUpstream)
        threading.Thread(target=self.up.serve_forever, daemon=True).start()
        p = mock.patch.object(hub, "UPSTREAM_PORT", self.up.server_address[1])
        p.start()
        self.patches.append(p)
        hub._models_cache.update(at=0.0, list=[])

    def tearDown(self):
        self.up.shutdown()
        self.up.server_close()
        hub._models_cache.update(at=0.0, list=[])
        super().tearDown()

    def test_models_and_props_helpers_send_token(self):
        self.assertEqual(hub.upstream_models(max_age=0), ["Qwen3-4B-Instruct-2507-Q4_K_M"])
        hub.upstream_model()
        self.assertEqual(sorted(p for p, _a in _FakeUpstream.auth), ["/props", "/v1/models"])
        self.assertTrue(all(a == "Bearer " + self.token for _p, a in _FakeUpstream.auth))
        self.assertEqual(hub.router_auth_headers(), {"Authorization": "Bearer " + self.token})


BOOT_HARNESS = r"""
const vm = require('vm'), fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const scen = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = scen.map(function (s) {
  const store = s.store;
  const ls = {
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
    setItem: function (k, v) { store[k] = String(v); },
    removeItem: function (k) { delete store[k]; }
  };
  const win = { __QWEN_BOOT__: s.boot, matchMedia: function () { return { matches: true, addEventListener: function () {} }; },
                dispatchEvent: function () {}, localStorage: ls };
  const ctx = { window: win, localStorage: ls, CustomEvent: function () {},
                document: { documentElement: { setAttribute: function () {}, style: {} } } };
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return store;
});
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(node_exe(), "ไม่มี node — ข้ามเทสต์ boot.js")
class BootJsMergeTests(_TokenMixin, unittest.TestCase):
    def run_boot(self, scenarios):
        h = Path(self.tmp) / "harness.js"
        h.write_text(BOOT_HARNESS, encoding="utf-8")
        s = Path(self.tmp) / "scen.json"
        s.write_text(json.dumps(scenarios), encoding="utf-8")
        r = subprocess.run([node_exe(), str(h), BOOT_JS, str(s)], capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-800:])
        return json.loads(r.stdout.decode("utf-8"))

    def boot(self):
        return json.loads(json.dumps(hub.boot_config(dict(PROJECT))))

    @staticmethod
    def servers(store):
        return {s["id"]: s for s in json.loads(json.loads(store["LlamaUi.config"])["mcpServers"])}

    def bearer(self, tok):
        return json.dumps({"Authorization": "Bearer " + tok})

    def test_new_browser(self):
        (st,) = self.run_boot([{"store": {}, "boot": self.boot()}])
        sv = self.servers(st)
        self.assertEqual(sorted(sv), ["local", "local-full", "websearch"])
        self.assertTrue(all(s["headers"] == self.bearer(self.token) and s["useProxy"] is False for s in sv.values()))
        self.assertEqual(st["qwen-boot-version"], "3")
        self.assertEqual(json.loads(st["LlamaUi.alwaysAllowedTools"]), [])

    def test_upgrade_keeps_user_choices(self):
        old = [{"id": "websearch", "name": "w", "url": "http://127.0.0.1:8791/mcp", "enabled": False},
               {"id": "local", "name": "l", "url": "http://127.0.0.1:8792/mcp/sectest", "enabled": True,
                "useProxy": True},
               {"id": "mine", "name": "m", "url": "http://example.test/mcp", "enabled": True}]
        store = {"LlamaUi.config": json.dumps({"mcpServers": json.dumps(old), "theme": "light"}),
                 "qwen-boot-version": "2",
                 "LlamaUi.alwaysAllowedTools": json.dumps(["mcp-local:local_do"])}
        (st,) = self.run_boot([{"store": store, "boot": self.boot()}])
        sv = self.servers(st)
        self.assertIs(sv["websearch"]["enabled"], False)            # ผู้ใช้ปิดไว้ — คงไว้
        self.assertIn("/fast/sectest", sv["local"]["url"])
        self.assertIs(sv["local"]["useProxy"], False)
        self.assertEqual(sv["local"]["headers"], self.bearer(self.token))
        self.assertEqual(sv["mine"], old[2])                         # ของผู้ใช้ไม่แตะ ไม่ได้โทเคนไปด้วย
        self.assertEqual(st["qwen-boot-version"], "3")
        self.assertEqual(json.loads(st["LlamaUi.alwaysAllowedTools"]), ["mcp-local:local_do"])  # เลือกเองแล้ว ไม่ถอน
        self.assertEqual(json.loads(st["LlamaUi.config"])["theme"], "light")

    def test_rotated_token_reaches_open_browsers_without_version_bump(self):
        (st,) = self.run_boot([{"store": {}, "boot": self.boot()}])
        cfg = json.loads(st["LlamaUi.config"])
        sv = json.loads(cfg["mcpServers"])
        for s in sv:
            if s["id"] == "local":
                s["useProxy"] = True
            if s["id"] == "local-full":
                s["enabled"] = True
        cfg["mcpServers"] = json.dumps(sv)
        st["LlamaUi.config"] = json.dumps(cfg)
        new_tok = secrets.token_hex(32)
        self.token_file.write_text(new_tok, encoding="ascii")
        (st2,) = self.run_boot([{"store": st, "boot": self.boot()}])
        sv2 = self.servers(st2)
        self.assertTrue(all(s["headers"] == self.bearer(new_tok) for s in sv2.values()))
        self.assertIs(sv2["local"]["useProxy"], False)
        self.assertIs(sv2["local-full"]["enabled"], True)

    def test_unreadable_token_keeps_stored_headers(self):
        (st,) = self.run_boot([{"store": {}, "boot": self.boot()}])
        self.token_file.write_text("broken", encoding="ascii")
        (st2,) = self.run_boot([{"store": st, "boot": self.boot()}])
        self.assertTrue(all(s["headers"] == self.bearer(self.token) for s in self.servers(st2).values()))

    def test_version_bump_without_readable_token_keeps_stored_headers(self):
        old = [{"id": "local", "url": "http://127.0.0.1:8792/fast/sectest", "enabled": True,
                "headers": self.bearer(self.token)}]
        store = {"LlamaUi.config": json.dumps({"mcpServers": json.dumps(old)}), "qwen-boot-version": "2"}
        self.token_file.write_text("broken", encoding="ascii")
        (st,) = self.run_boot([{"store": store, "boot": self.boot()}])
        sv = self.servers(st)
        self.assertEqual(sv["local"]["headers"], self.bearer(self.token))
        self.assertNotIn("headers", sv["websearch"])
        self.assertEqual(st["qwen-boot-version"], "3")

    def test_legacy_permission_key_counts_as_user_choice(self):
        (st,) = self.run_boot([{"store": {"LlamaCppWebui.alwaysAllowedTools": '["x"]'}, "boot": self.boot()}])
        self.assertNotIn("LlamaUi.alwaysAllowedTools", st)


if __name__ == "__main__":
    unittest.main()
