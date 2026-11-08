# -*- coding: utf-8 -*-
"""
เทสต์เบราว์เซอร์ในตัว (2026-10-19): hub_browser.py + เส้นทาง /_qwen/browser ของพอร์ตโปรเจกต์ + สคริปต์ของแผง/คิวข้อความ

รัน:  C:\\Python313\\python.exe -m unittest C:\\LLM\\tests\\test_browser_panel.py -v

สิ่งที่ตรวจ (ไม่เปิดเบราว์เซอร์จริง ไม่แตะโปรไฟล์จริง ไม่ใช้พอร์ต 8797 ของพร็อกซีตัวจริง)
  * กฎที่อยู่: เปิดได้เฉพาะ http/https บนอินเทอร์เน็ตสาธารณะ — loopback / LAN / link-local / CGNAT / ชื่อ .local ฯลฯ ถูกปฏิเสธ
  * พร็อกซีขาออก (ตัวทดสอบบนพอร์ตสุ่ม): ไป loopback / LAN / ชื่อที่ resolve เป็นที่อยู่ในเครื่อง (DNS rebinding) ได้ 403
    พร้อมหน้าบล็อก, ปลายทาง "สาธารณะ" (จำลอง) ผ่านทั้งแบบ absolute-form และ CONNECT, header ของพร็อกซีถูกตัดทิ้ง
  * DNS สำรอง (เซิร์ฟเวอร์ DNS ปลอมบน 127.0.0.1 + DoH จำลอง ไม่ออกเน็ต): DNS ของเครื่องเสีย/ช้า/ตอบ "ไม่มีชื่อ" กับทุกชื่อ
    = ใช้ DNS สาธารณะ, คำตอบของเครื่อง (รวม hosts ที่ชี้ 0.0.0.0) และ "ไม่มีชื่อนี้" ของ DNS ที่ยังดีต้องชนะ, ที่อยู่ในเครื่อง/
    วงแลนจาก DNS สาธารณะถูกบล็อก, แพ็กเก็ตปลอม/หลงมาถูกทิ้ง, ชื่อภายใน (.corp, ชื่อคำเดียว) ไม่ถูกส่งออก, แคช, ปิดได้
  * MCP: initialize / tools/list (11 ตัว) / notification / batch / method ที่ไม่รู้จัก และคำขอผิด (ที่อยู่ต้องห้าม ไฟล์ที่ห้าม
    อัปโหลด สคริปต์ว่าง ปุ่มเมาส์ผิด) ถูกปฏิเสธ "ก่อน" เปิดเบราว์เซอร์ (ไม่มี Edge ถูกเปิดขึ้นมาเปล่าๆ)
  * ไฟล์: อัปโหลดได้เฉพาะ attachments/outputs ของโปรเจกต์ + โฟลเดอร์เนื้อหาของผู้ใช้ ไม่รับคีย์/รหัสผ่าน/ไฟล์ซ่อน,
    ชื่อไฟล์ดาวน์โหลดปลอดภัยบน Windows และไม่ทับไฟล์เดิม
  * http() ของแผง: สถานะตอนยังไม่เปิด / frame = 409 / ขนาดจอถูกจำกัดช่วง / ไม่มีกล่องข้อความ = ok false
  * hub.py: แถว MCP "browser" ชี้พอร์ตโปรเจกต์ + โทเคน, โหมดวางแผนเหลือแค่อ่าน/ถ่ายภาพ, /_qwen/browser ต้องเป็น
    Origin ของพอร์ตนี้ และ /mcp ต้องมีโทเคน, shell มีสคริปต์ของแผง, คิวข้อความโหลดก่อนตัวกู้การเชื่อมต่อ
  * browser-panel.js / message-queue.js: syntax ผ่าน node (ข้ามถ้าไม่มี node)

ทดสอบสด (เปิด Edge แบบ headless จริงในโปรไฟล์ชั่วคราว ต้องต่อเน็ต): ตั้ง QWEN_BROWSER_LIVE_TEST=1
  — เปิด example.com, อ่าน, ภาพหน้าจอ, กันเข้าเครื่องนี้ แล้วทดสอบการควบคุมบนฟอร์มที่ใส่ลงในหน้านั้น (dropdown, ติ๊ก, ชี้เมาส์,
    ลากวาง, รอข้อความ, ภาพขยาย, อัปโหลด, ดาวน์โหลด, รันสคริปต์, ช่องรหัสผ่านถูกปฏิเสธ)
  — จำลอง DNS ของเครื่องล่ม (เฉพาะในโปรเซสเทสต์) แล้วเปิด example.com ผ่าน DNS สาธารณะจริง (UDP และ DoH)
"""
import functools
import http.client
import importlib.util
import json
import os
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

PROJECTS = Path(os.environ.get("QWEN_PROJECTS_DIR", r"C:\LLM\projects"))
HUB = PROJECTS / "hub.py"
HB_FILE = PROJECTS / "hub_browser.py"
STATIC = PROJECTS / "static"
TOKEN_ENV = "LLM_LOCAL_TOKEN_FILE"
TOOL_NAMES = {"browser_navigate", "browser_read", "browser_click", "browser_type", "browser_scroll",
              "browser_screenshot", "browser_tabs", "browser_fill", "browser_wait", "browser_upload", "browser_evaluate"}
READ_ONLY = {"browser_read", "browser_screenshot", "browser_wait"}


def _load(path, name, patch_argv=False):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"] if patch_argv else sys.argv), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


try:
    hb = _load(HB_FILE, "hub_browser_under_test") if HB_FILE.is_file() else None
    HB_ERR = None if hb else "ไม่มี hub_browser.py"
except Exception as e:      # noqa: BLE001
    hb, HB_ERR = None, "import hub_browser.py ไม่ได้: %s: %s" % (type(e).__name__, e)

try:
    hub = _load(HUB, "hub_browser_panel_under_test", patch_argv=True) if HUB.is_file() else None
    HUB_ERR = None if hub else "ไม่มี hub.py"
except Exception as e:      # noqa: BLE001
    hub, HUB_ERR = None, "import hub.py ไม่ได้: %s: %s" % (type(e).__name__, e)


def node_exe():
    for p in (shutil.which("node"), r"C:\Program Files\nodejs\node.exe"):
        if p and os.path.isfile(p):
            return p
    return None


class ImportTests(unittest.TestCase):
    """import ไม่ได้ต้องล้มดังๆ ไม่ใช่ข้ามทั้งชุดเงียบๆ"""

    def test_modules_import(self):
        self.assertIsNotNone(hb, HB_ERR)
        self.assertIsNotNone(hub, HUB_ERR)
        self.assertIsNotNone(getattr(hub, "_browser", None), "hub.py เปิดโดยไม่มีเบราว์เซอร์ในตัว (hub_browser import ไม่ได้)")


# ------------------------------------------------------------------------------------------------ กฎที่อยู่
class AddressRuleTests(unittest.TestCase):
    def test_ip_public(self):
        for ip in ("8.8.8.8", "1.1.1.1", "93.184.216.34", "2001:4860:4860::8888", "::ffff:8.8.8.8"):
            with self.subTest(ip=ip):
                self.assertTrue(hb.ip_public(ip))
        for ip in ("127.0.0.1", "127.8.9.10", "0.0.0.0", "10.0.0.1", "172.16.5.4", "192.168.1.1", "169.254.169.254",
                   "100.64.0.1", "224.0.0.251", "239.255.255.250", "255.255.255.255", "::1", "::", "fe80::1",
                   "fc00::1", "fd12:3456::1", "ff02::1", "::ffff:127.0.0.1", "::ffff:192.168.0.10", "not-an-ip", ""):
            with self.subTest(ip=ip):
                self.assertFalse(hb.ip_public(ip))

    def test_normalize_url_accepts_public_web_addresses(self):
        cases = {
            "example.com": "https://example.com/",
            "example.com/a b?q=1": "https://example.com/a b?q=1",
            "example.com:8443/x": "https://example.com:8443/x",
            "http://example.com/a?b=1#c": "http://example.com/a?b=1#c",
            "HTTPS://Example.com": "https://Example.com/",
            "https://8.8.8.8/": "https://8.8.8.8/",
            "  https://th.wikipedia.org/wiki/แมว  ": "https://th.wikipedia.org/wiki/แมว",
            "about:blank": "about:blank",
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(hb.normalize_url(raw), want)

    def test_normalize_url_refuses_local_and_non_web_addresses(self):
        for raw in ("", "   ", "file:///C:/Windows/win.ini", "javascript:alert(1)", "data:text/html,hi",
                    "edge://settings", "chrome://version", "view-source:https://example.com", "ftp://example.com/",
                    "ws://example.com/", "mailto:a@b.c", "http://user:pass@example.com/", "https://user@example.com/",
                    "http://localhost:8100/", "localhost:8104", "http://LOCALHOST./", "http://127.0.0.1:8104/health",
                    "http://[::1]:8100/", "http://10.0.0.5/", "http://192.168.1.1/", "http://172.20.0.1/",
                    "http://169.254.169.254/latest/meta-data/", "http://100.64.1.1/", "http://0.0.0.0:8100/",
                    "http://[::ffff:127.0.0.1]/", "http://shell.localhost/", "http://printer.local/",
                    "http://svc.internal/", "http://nas.lan/", "http://router.home.arpa/", "https:///no-host"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    hb.normalize_url(raw)

    def test_resolve_public_checks_every_resolved_address(self):
        def fake(rows):
            return lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in rows]
        with mock.patch.object(hb.socket, "getaddrinfo", fake(["10.1.2.3", "93.184.216.34"])):
            fam, addr = hb.resolve_public("mixed.example", 443)
            self.assertEqual((fam, addr), (socket.AF_INET, ("93.184.216.34", 443)))
        # DNS rebinding: ชื่อสาธารณะที่ resolve เป็นที่อยู่ในเครื่อง
        with mock.patch.object(hb.socket, "getaddrinfo", fake(["127.0.0.1"])):
            with self.assertRaises(ValueError):
                hb.resolve_public("rebind.example", 80)
        with mock.patch.object(hb.socket, "getaddrinfo", fake(["192.168.1.20", "fe80::1"])):
            with self.assertRaises(ValueError):
                hb.resolve_public("lan.example", 80)
        with mock.patch.object(hb.socket, "getaddrinfo", side_effect=socket.gaierror(11001, "no such host")):
            with self.assertRaises(ValueError):
                hb.resolve_public("nope.example", 80)
        # ชื่อในเครื่องถูกปฏิเสธโดยไม่ต้อง resolve
        with mock.patch.object(hb.socket, "getaddrinfo", side_effect=AssertionError("must not resolve")):
            for host in ("localhost", "LocalHost.", "x.localhost", "printer.local", "svc.internal", "nas.lan",
                         "router.home.arpa", "", "[]"):
                with self.subTest(host=host):
                    with self.assertRaises(ValueError):
                        hb.resolve_public(host, 80)

    def test_key_event(self):
        self.assertEqual(hb.key_event("Enter"), ("Enter", "Enter", 13, "\r", 0))
        self.assertEqual(hb.key_event("ctrl+a"), ("a", "KeyA", 65, "", 2))
        self.assertEqual(hb.key_event("shift+Tab"), ("Tab", "Tab", 9, "", 8))
        self.assertEqual(hb.key_event("ctrl + shift + K")[4], 10)
        self.assertEqual(hb.key_event("7"), ("7", "Digit7", 55, "7", 0))
        self.assertEqual(hb.key_event("PageDown")[:3], ("PageDown", "PageDown", 34))
        for bad in ("", "hyper+x", "F13", "ctrl+"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    hb.key_event(bad)

    def test_profile_must_stay_inside_the_isolated_root(self):
        tmp = tempfile.mkdtemp(prefix="bp-root-")
        try:
            with mock.patch.object(hb, "PROFILE_ROOT", Path(tmp)):
                self.assertTrue(hb._assert_isolated(Path(tmp) / "_panel" / "proj"))
                for bad in (Path(tmp), Path(tmp).parent / "elsewhere", Path(tmp) / ".." / "escape"):
                    with self.subTest(bad=str(bad)):
                        with self.assertRaises(ValueError):
                            hb._assert_isolated(bad)
                real = (Path(tmp) / "Microsoft" / "Edge" / "User Data" / "Default" if os.name == "nt"
                        else Path(tmp) / ".config" / "google-chrome" / "Default")
                with self.assertRaises(ValueError):
                    hb._assert_isolated(real)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(hb._safe_slug("../../etc"), "etc")
        self.assertEqual(hb._safe_slug(""), "project")
        self.assertEqual(hb._safe_slug("old-project"), "old-project")
        self.assertEqual(hb._safe_slug("งาน ใหม่"), "งาน-ใหม่")


class FileRuleTests(unittest.TestCase):
    def setUp(self):
        # ไม่ใช้ %TEMP% (อยู่ใต้ AppData ซึ่งเป็นตำแหน่งต้องห้ามของการอัปโหลดอยู่แล้ว)
        self.tmp = Path(tempfile.mkdtemp(prefix="bp-files-", dir=os.path.dirname(os.path.abspath(__file__))))
        self.att, self.out = self.tmp / "attachments", self.tmp / "outputs"
        self.att.mkdir()
        self.out.mkdir()
        self.p = mock.patch.object(hb, "PROJECT_DIRS", lambda slug: (self.att, self.out))
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_upload_paths(self):
        ok = self.att / "รายงาน.pdf"
        ok.write_bytes(b"%PDF-1")
        made = self.out / "chart.png"
        made.write_bytes(b"png")
        self.assertEqual(hb.check_upload_path("p", str(ok)), os.path.realpath(str(ok)))
        self.assertEqual(hb.check_upload_path("p", "attachments/รายงาน.pdf"), os.path.realpath(str(ok)))
        self.assertEqual(hb.check_upload_path("p", "outputs/chart.png"), os.path.realpath(str(made)))
        self.assertEqual(hb.check_upload_path("p", "chart.png"), os.path.realpath(str(made)))
        bad = []
        for name in ("server.pem", "id_rsa", ".env", "prod.env", "credentials.json", "Login Data", "secrets.txt"):
            f = self.att / name
            f.write_text("x", encoding="utf-8")
            bad.append(str(f))
        hidden = self.att / ".hidden" / "a.txt"
        hidden.parent.mkdir()
        hidden.write_text("x", encoding="utf-8")
        bad += [str(hidden), str(self.tmp / "outside.txt"), "attachments/../outside.txt", "nope.txt", "",
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_browser_panel.py")]
        (self.tmp / "outside.txt").write_text("x", encoding="utf-8")
        for raw in bad:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    hb.check_upload_path("p", raw)

    def test_home_content_folders_are_allowed_roots(self):
        home = Path(os.path.expanduser("~"))
        roots = [str(r) for r in hb.upload_roots("p")]
        for name in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"):
            self.assertIn(str(home / name), roots)
        self.assertIn(str(self.att), roots)
        self.assertNotIn(str(home), roots)

    def test_download_names(self):
        self.assertEqual(hb.safe_download_name("a/b:c?.pdf"), "a_b_c_.pdf")
        self.assertEqual(hb.safe_download_name("CON.txt"), "_CON.txt")
        self.assertEqual(hb.safe_download_name("..."), "download")
        self.assertEqual(hb.safe_download_name("~$temp.docx"), "temp.docx")
        self.assertEqual(hb.safe_download_name("รายงาน ประจำปี.xlsx"), "รายงาน ประจำปี.xlsx")
        self.assertLessEqual(len(hb.safe_download_name("x" * 400 + ".pdf")), 124)
        (self.out / "a.csv").write_text("1", encoding="utf-8")
        (self.out / "a (2).csv").write_text("1", encoding="utf-8")
        self.assertEqual(hb.unique_path(self.out, "a.csv").name, "a (3).csv")
        self.assertEqual(hb.unique_path(self.out, "b.csv").name, "b.csv")

    def test_modifier_keys(self):
        self.assertEqual(hb._parse_mods("ctrl+shift"), 10)
        self.assertEqual(hb._parse_mods(""), 0)
        with self.assertRaises(ValueError):
            hb._parse_mods("hyper")


# ------------------------------------------------------------------------------------------------ พร็อกซีขาออก
class _Echo(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


def _read_all(sock, timeout=5):
    sock.settimeout(timeout)
    data = b""
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    except socket.timeout:
        pass
    return data


class EgressProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proxy = hb._ProxyServer(("127.0.0.1", 0), hb._ProxyHandler)
        cls.pport = cls.proxy.server_address[1]
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        cls.up = ThreadingHTTPServer(("127.0.0.1", 0), _Echo)
        cls.uport = cls.up.server_address[1]
        threading.Thread(target=cls.up.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for s in (cls.proxy, cls.up):
            s.shutdown()
            s.server_close()

    def send(self, head):
        s = socket.create_connection(("127.0.0.1", self.pport), timeout=5)
        try:
            s.sendall(head.encode("latin-1"))
            return _read_all(s)
        finally:
            s.close()

    def fake_public(self):
        real = hb.resolve_public
        uport = self.uport

        def resolve(host, port):
            if str(host).lower() == "public.example":
                return socket.AF_INET, ("127.0.0.1", uport)        # จำลองเว็บสาธารณะ (ทดสอบเท่านั้น)
            return real(host, port)
        return mock.patch.object(hb, "resolve_public", resolve)

    def test_local_targets_get_the_block_page(self):
        heads = [
            "CONNECT 127.0.0.1:%d HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % (self.uport, self.uport),
            "CONNECT localhost:443 HTTP/1.1\r\nHost: localhost:443\r\n\r\n",
            "CONNECT [::1]:443 HTTP/1.1\r\nHost: [::1]:443\r\n\r\n",
            "GET http://127.0.0.1:%d/ HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % (self.uport, self.uport),
            "GET http://10.0.0.1/ HTTP/1.1\r\nHost: 10.0.0.1\r\n\r\n",
            "GET http://169.254.169.254/latest/meta-data/ HTTP/1.1\r\nHost: 169.254.169.254\r\n\r\n",
            "GET http://printer.local/ HTTP/1.1\r\nHost: printer.local\r\n\r\n",
        ]
        for head in heads:
            with self.subTest(head=head.split("\r\n")[0]):
                data = self.send(head)
                self.assertTrue(data.startswith(b"HTTP/1.1 403 "), data[:80])
                self.assertIn("ไม่เปิดที่อยู่นี้".encode("utf-8"), data)

    def test_dns_rebinding_to_loopback_is_blocked(self):
        real = socket.getaddrinfo
        uport = self.uport

        def lookup(host, port, *a, **k):     # เฉพาะชื่อทดสอบ — การต่อของเทสต์เองไปที่พร็อกซียัง resolve ปกติ
            if host == "rebind.example":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", uport))]
            return real(host, port, *a, **k)
        with mock.patch.object(hb.socket, "getaddrinfo", side_effect=lookup):
            data = self.send("CONNECT rebind.example:443 HTTP/1.1\r\nHost: rebind.example:443\r\n\r\n")
            self.assertTrue(data.startswith(b"HTTP/1.1 403 "), data[:80])
            data = self.send("GET http://rebind.example:%d/ HTTP/1.1\r\nHost: rebind.example\r\n\r\n" % self.uport)
            self.assertTrue(data.startswith(b"HTTP/1.1 403 "), data[:80])

    def test_bad_requests(self):
        self.assertTrue(self.send("GET / HTTP/1.1\r\nHost: x\r\n\r\n").startswith(b"HTTP/1.1 400 "))
        self.assertTrue(self.send("GET ftp://example.com/ HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 400 "))
        self.assertTrue(self.send("garbage\r\n\r\n").startswith(b"HTTP/1.1 400 "))

    def test_public_absolute_form_passes_without_proxy_headers(self):
        with self.fake_public():
            data = self.send("GET http://public.example/echo?x=1 HTTP/1.1\r\nHost: public.example\r\n"
                             "Proxy-Connection: keep-alive\r\nProxy-Authorization: Basic Zm9vOmJhcg==\r\n"
                             "Connection: keep-alive\r\nUser-Agent: unit\r\n\r\n")
        self.assertTrue(data.startswith(b"HTTP/1.1 200"), data[:80])
        seen = json.loads(data.partition(b"\r\n\r\n")[2])
        self.assertEqual(seen["path"], "/echo?x=1")
        self.assertNotIn("proxy-authorization", seen["headers"])
        self.assertNotIn("proxy-connection", seen["headers"])
        self.assertEqual(seen["headers"].get("connection"), "close")
        self.assertEqual(seen["headers"].get("user-agent"), "unit")

    def test_public_connect_tunnel_passes(self):
        with self.fake_public():
            s = socket.create_connection(("127.0.0.1", self.pport), timeout=5)
            try:
                s.sendall(b"CONNECT public.example:443 HTTP/1.1\r\nHost: public.example:443\r\n\r\n")
                s.settimeout(5)
                head = b""
                while b"\r\n\r\n" not in head:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    head += chunk
                self.assertTrue(head.startswith(b"HTTP/1.1 200 Connection Established"), head[:80])
                s.sendall(b"GET /tunnel HTTP/1.1\r\nHost: public.example\r\nConnection: close\r\n\r\n")
                data = head.partition(b"\r\n\r\n")[2] + _read_all(s)
            finally:
                s.close()
        self.assertTrue(data.startswith(b"HTTP/1.1 200"), data[:80])
        self.assertEqual(json.loads(data.partition(b"\r\n\r\n")[2])["path"], "/tunnel")


# ------------------------------------------------------------------------------------------------ DNS สำรอง
def _qname(name):
    return b"".join(bytes([len(l)]) + l.encode("ascii") for l in name.split(".")) + b"\0"


def _rr(owner, rtype, ttl, data):
    """เรคคอร์ดคำตอบ — owner=None = ตัวชี้ย่อชื่อไปที่ชื่อในคำถาม (0xC00C)"""
    head = struct.pack(">H", 0xC00C) if owner is None else _qname(owner)
    if rtype in (1, 28):
        rdata = __import__("ipaddress").ip_address(data).packed
    elif rtype == 5:
        rdata = _qname(data)
    else:
        rdata = data
    return head + struct.pack(">HHIH", rtype, 1, ttl, len(rdata)) + rdata


def _reply(query, rcode, rrs, qid=None, question=None, tc=False):
    end = query.index(b"\0", 12) + 5
    flags = 0x8180 | rcode | (0x0200 if tc else 0)
    return (struct.pack(">HHHHHH", struct.unpack(">H", query[:2])[0] if qid is None else qid, flags, 1, len(rrs), 0, 0)
            + (query[12:end] if question is None else question) + b"".join(rrs))


class _FakeDns:
    """เซิร์ฟเวอร์ DNS ปลอม (UDP บน 127.0.0.1) — table[(ชื่อ, ชนิด)] = (rcode, [เรคคอร์ด]) หรือ None = เงียบ
    ไม่มีในตาราง = NXDOMAIN;  before(query) คืนแพ็กเก็ตที่จะส่งก่อนคำตอบจริง (ทดสอบของปลอม)"""

    def __init__(self, table, before=None):
        self.table, self.before, self.queries = table, before, []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.1)
        self.addr = ("127.0.0.1", self.sock.getsockname()[1])
        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while self.running:
            try:
                data, peer = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            labels, i = [], 12
            while data[i]:
                labels.append(data[i + 1:i + 1 + data[i]].decode("ascii"))
                i += 1 + data[i]
            key = (".".join(labels), struct.unpack(">H", data[i + 1:i + 3])[0])
            self.queries.append(key)
            for pkt in (self.before(data) if self.before else ()):
                self.sock.sendto(pkt, peer)
            row = self.table.get(key, (3, []))
            if row is not None:
                self.sock.sendto(_reply(data, row[0], row[1]), peer)

    def close(self):
        self.running = False
        self.thread.join(2)
        self.sock.close()


class _FakeHttps:
    """แทน http.client.HTTPSConnection ของ DoH — replies[host] = (status, เอกสาร JSON)"""
    replies, calls = {}, []

    def __init__(self, host, port=443, timeout=None, context=None):
        self.host = host

    def request(self, method, path, headers=None):
        _FakeHttps.calls.append((self.host, path, dict(headers or {})))

    def getresponse(self):
        status, doc = _FakeHttps.replies[self.host]
        body = json.dumps(doc).encode("utf-8")
        return types.SimpleNamespace(status=status, read=lambda n=-1: body)

    def close(self):
        pass


def _fail(errno_name="EAI_AGAIN"):
    def lookup(host, port):
        raise socket.gaierror(getattr(socket, errno_name), "simulated DNS failure")
    return lookup


def _answer_rows(*ips):
    return lambda host, port: [((socket.AF_INET6 if ":" in ip else socket.AF_INET), socket.SOCK_STREAM, 6, "", (ip, port))
                               for ip in ips]


@unittest.skipIf(hb is None, HB_ERR)
class DnsFallbackTests(unittest.TestCase):
    NAME = "site.qwen-test.net"

    def setUp(self):
        hb._dns_reset()
        self.dns = _FakeDns({
            (self.NAME, 1): (0, [_rr(None, 5, 300, "edge.qwen-cdn.net"), _rr("edge.qwen-cdn.net", 1, 120, "93.184.215.14"),
                                 _rr("edge.qwen-cdn.net", 1, 90, "93.184.215.15"), _rr("other.net", 1, 50, "1.2.3.4"),
                                 _rr(None, 16, 50, b"\x05hello")]),
            ("v6only.qwen-test.net", 1): (0, []),
            ("v6only.qwen-test.net", 28): (0, [_rr(None, 28, 300, "2606:4700::6810:1")]),
            ("lan.qwen-test.net", 1): (0, [_rr(None, 1, 300, "10.0.0.5")]),
            ("loop.qwen-test.net", 1): (0, [_rr(None, 1, 300, "127.0.0.1")]),
            ("broken.qwen-test.net", 1): (2, []),
            ("silent.qwen-test.net", 1): None,
        })
        self.patches = [mock.patch.object(hb, "DNS_SERVERS", [self.dns.addr]), mock.patch.object(hb, "DOH_URLS", []),
                        mock.patch.object(hb, "UDP_ROUND", 0.3), mock.patch.object(hb, "DNS_FALLBACK", True)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.dns.close()
        hb._dns_reset()

    def test_wire_format(self):
        q = hb._dns_query("www.example.com", 1, 0x1234)
        self.assertEqual(q[:12], bytes.fromhex("123401000001000000000001"))
        self.assertEqual(q[12:29], b"\x03www\x07example\x03com\x00")
        self.assertEqual(q[29:33], b"\x00\x01\x00\x01")
        self.assertEqual(q[33:], b"\x00\x00\x29\x04\xd0\x00\x00\x00\x00\x00\x00")       # EDNS0 OPT, 1232 ไบต์
        ans = _reply(q, 0, [_rr(None, 5, 300, "cdn.example.net"), _rr("cdn.example.net", 1, 60, "93.184.215.14"),
                            _rr("unrelated.net", 1, 60, "1.2.3.4")])
        rcode, records, tc = hb._dns_parse(ans, 0x1234, "www.example.com", 1)
        self.assertEqual((rcode, tc), (0, False))
        self.assertEqual(hb._dns_chain("www.example.com", records, 1), (["93.184.215.14"], 60))
        for bad in (_reply(q, 0, [], qid=0x4321), _reply(q, 0, [], question=_qname("evil.example") + b"\x00\x01\x00\x01"),
                    ans[:20], b"\x12\x34" + b"\x01\x00" + ans[4:]):               # id ผิด / คำถามอื่น / ขาด / ไม่ใช่คำตอบ
            with self.assertRaises(ValueError):
                hb._dns_parse(bad, 0x1234, "www.example.com", 1)
        loop = bytes.fromhex("123481800001000100000000") + b"\xc0\x0c"         # ชื่อชี้วนตัวเอง
        with self.assertRaises(ValueError):
            hb._dns_parse(loop, 0x1234, "www.example.com", 1)
        self.assertTrue(hb._dns_ascii("ทดสอบ.com").startswith("xn--"))
        self.assertEqual(hb._dns_ascii("WWW.Example.COM."), "www.example.com")
        for name in ("a" * 64 + ".com", "a..com", ""):
            with self.assertRaises(ValueError):
                hb._dns_ascii(name)

    def test_udp_lookup_cache_and_ipv6(self):
        self.assertEqual(hb.public_lookup("Site.Qwen-Test.NET."), ("ok", ["93.184.215.14", "93.184.215.15"]))
        self.assertEqual(hb.public_lookup(self.NAME), ("ok", ["93.184.215.14", "93.184.215.15"]))
        self.assertEqual(self.dns.queries.count((self.NAME, 1)), 1)                 # ครั้งที่สองมาจากแคช
        self.assertEqual(hb.public_lookup("v6only.qwen-test.net"), ("ok", ["2606:4700::6810:1"]))
        self.assertEqual(hb.public_lookup("missing.qwen-test.net"), ("nx", []))
        self.assertEqual(hb.public_lookup("broken.qwen-test.net"), ("servfail", []))
        self.assertFalse(hb.dns_status()["public_unreachable"])                     # SERVFAIL ≠ DNS สาธารณะใช้ไม่ได้

    def test_spoofed_and_stray_packets_are_ignored(self):
        def junk(query):
            return [_reply(query, 0, [_rr(None, 1, 60, "6.6.6.6")], qid=(struct.unpack(">H", query[:2])[0] + 1) % 65536),
                    _reply(query, 0, [_rr("evil.example", 1, 60, "6.6.6.7")],
                           question=_qname("evil.example") + b"\x00\x01\x00\x01"),
                    b"\x00garbage"]
        self.dns.before = junk
        self.assertEqual(hb.public_lookup(self.NAME), ("ok", ["93.184.215.14", "93.184.215.15"]))

    def test_system_dns_failure_uses_public_dns(self):
        with mock.patch.object(hb, "_system_lookup", _fail("EAI_AGAIN")):
            self.assertEqual(hb.resolve_public(self.NAME, 443), (socket.AF_INET, ("93.184.215.14", 443)))
            st = hb.dns_status()
            self.assertTrue(st["system_bad"])
            self.assertEqual(st["public_answers"], 1)
            self.assertEqual(hb.resolve_public("v6only.qwen-test.net", 443),
                             (socket.AF_INET6, ("2606:4700::6810:1", 443, 0, 0)))
            for host, word in (("lan.qwen-test.net", "วงแลน"), ("loop.qwen-test.net", "วงแลน"),
                               ("missing.qwen-test.net", "ไม่มีชื่อนี้"), ("broken.qwen-test.net", "หาชื่อนี้ไม่ได้")):
                with self.subTest(host=host):
                    with self.assertRaises(ValueError) as cm:
                        hb.resolve_public(host, 443)
                    self.assertIn(word, str(cm.exception))

    def test_slow_system_dns_falls_back_quickly(self):
        def slow(host, port):
            time.sleep(4)
            return _answer_rows("93.184.215.99")(host, port)
        with mock.patch.object(hb, "_system_lookup", slow), mock.patch.object(hb, "SYS_DNS_WAIT", 0.3):
            t0 = time.time()
            self.assertEqual(hb.resolve_public(self.NAME, 443)[1][0], "93.184.215.14")
            self.assertLess(time.time() - t0, 2.0)
            t0 = time.time()                                    # ช่วง DNS ของเครื่องเสีย: ชื่อที่ได้มาแล้วไม่ต้องรอซ้ำ
            self.assertEqual(hb.resolve_public(self.NAME, 443)[1][0], "93.184.215.14")
            self.assertLess(time.time() - t0, 0.2)

    def test_answers_from_the_computer_always_win(self):
        with mock.patch.object(hb, "_system_lookup", _answer_rows("0.0.0.0")):       # hosts ที่บล็อกชื่อนี้ไว้
            with self.assertRaises(ValueError):
                hb.resolve_public(self.NAME, 443)
        with mock.patch.object(hb, "_system_lookup", _answer_rows("10.9.8.7", "203.0.113.9", "93.184.215.50")):
            self.assertEqual(hb.resolve_public(self.NAME, 443), (socket.AF_INET, ("93.184.215.50", 443)))
        self.assertEqual(self.dns.queries, [])
        self.assertFalse(hb.dns_status()["system_bad"])

    def test_no_such_name_from_a_working_dns_is_respected(self):
        def lookup(host, port):
            if host.endswith(".github.io"):                     # DNS ของเครื่องยังดี (ชื่อตรวจสุขภาพได้คำตอบ)
                return _answer_rows("185.199.108.153")(host, port)
            raise socket.gaierror(socket.EAI_NONAME, "no such host")
        with mock.patch.object(hb, "_system_lookup", lookup):
            with self.assertRaises(ValueError) as cm:
                hb.resolve_public(self.NAME, 443)
        self.assertIn("ไม่มีชื่อนี้", str(cm.exception))
        self.assertEqual(self.dns.queries, [])                  # ไม่ไปถาม DNS สาธารณะเพื่อหลบคำตอบของเครื่อง

    def test_dns_that_says_no_to_every_name_is_bypassed(self):
        with mock.patch.object(hb, "_system_lookup", _fail("EAI_NONAME")):
            self.assertEqual(hb.resolve_public(self.NAME, 443)[1][0], "93.184.215.14")
        self.assertIn("ไม่มีชื่อนี้", hb.dns_status()["why"])

    def test_names_that_must_not_leave_the_machine(self):
        with mock.patch.object(hb, "_system_lookup", _fail("EAI_AGAIN")):
            for host in ("intranet", "nas.corp", "pc.home", "x.test", "1.2.3.4", "fileserver.localdomain"):
                with self.subTest(host=host):
                    with self.assertRaises(ValueError):
                        hb.resolve_public(host, 443)
            with mock.patch.object(hb, "DNS_FALLBACK", False):
                with self.assertRaises(ValueError) as cm:
                    hb.resolve_public(self.NAME, 443)
                self.assertIn("ไม่เจอ", str(cm.exception))
        self.assertEqual(self.dns.queries, [])

    def test_public_dns_unreachable(self):
        with mock.patch.object(hb, "_system_lookup", _fail("EAI_AGAIN")):
            t0 = time.time()
            with self.assertRaises(ValueError) as cm:
                hb.resolve_public("silent.qwen-test.net", 443)
            self.assertIn("อินเทอร์เน็ตอาจหลุด", str(cm.exception))
            self.assertLess(time.time() - t0, 3)
            self.assertTrue(hb.dns_status()["public_unreachable"])
            t0 = time.time()                                    # ไม่ถามซ้ำช่วงนี้ — ไม่หน่วงทุกคำขอ
            self.assertEqual(hb.public_lookup("other.qwen-test.net"), ("fail", []))
            self.assertLess(time.time() - t0, 0.1)

    def test_dns_over_https_when_udp_is_blocked(self):
        _FakeHttps.calls = []
        _FakeHttps.replies = {
            "1.1.1.1": (503, {}),
            "8.8.8.8": (200, {"Status": 0, "Answer": [
                {"name": "doh.qwen-test.net.", "type": 5, "TTL": 120, "data": "edge.qwen-cdn.net."},
                {"name": "edge.qwen-cdn.net.", "type": 1, "TTL": 60, "data": "93.184.215.20"},
                {"name": "edge.qwen-cdn.net.", "type": 1, "TTL": 60, "data": "not-an-ip"}]}),
        }
        silent = _FakeDns({("doh.qwen-test.net", 1): None, ("nope.qwen-test.net", 1): None})    # UDP ถูกปิด: ไม่มีคำตอบ
        udp = mock.Mock(wraps=hb._udp_ask)
        try:
            with mock.patch.object(hb, "DNS_SERVERS", [silent.addr]), mock.patch.object(hb, "_udp_ask", udp), \
                    mock.patch.object(hb, "DOH_URLS", ["https://1.1.1.1/dns-query", "https://8.8.8.8/resolve"]), \
                    mock.patch.object(hb._http_client, "HTTPSConnection", _FakeHttps):
                self.assertEqual(hb.public_lookup("doh.qwen-test.net"), ("ok", ["93.184.215.20"]))
                self.assertEqual([c[0] for c in _FakeHttps.calls], ["1.1.1.1", "8.8.8.8"])
                self.assertEqual(_FakeHttps.calls[1][1], "/resolve?name=doh.qwen-test.net&type=1")
                self.assertEqual(_FakeHttps.calls[0][2].get("Accept"), "application/dns-json")
                self.assertTrue(hb.dns_status()["udp_blocked"])
                _FakeHttps.replies["1.1.1.1"] = (200, {"Status": 3})
                t0 = time.time()                                # ชื่อถัดไปไม่ต้องเสียเวลารอ UDP อีก
                self.assertEqual(hb.public_lookup("nope.qwen-test.net"), ("nx", []))
                self.assertLess(time.time() - t0, 0.3)
                self.assertEqual(udp.call_count, 1)
        finally:
            silent.close()

    def test_proxy_failure_reason_reaches_navigate(self):
        hb._note_block("Example.ORG", ValueError("หาที่อยู่ของ example.org ไม่ได้ — ทดสอบ"))
        self.assertIn("ทดสอบ", hb.block_reason("https://example.org/page", time.time() - 5))
        self.assertEqual(hb.block_reason("https://example.org/page", time.time() + 5), "")
        self.assertEqual(hb.block_reason("https://other.example/", 0), "")


# ------------------------------------------------------------------------------------------------ MCP + http() ของแผง
class _NoLaunch:
    """กันเทสต์เปิด Edge จริงโดยไม่ตั้งใจ: ensure() ถูกเรียก = เทสต์ล้ม"""

    def __enter__(self):
        self.p = mock.patch.object(hb.PanelBrowser, "_start", side_effect=AssertionError("browser must not launch"))
        self.p.start()
        return self

    def __exit__(self, *a):
        self.p.stop()


class McpTests(unittest.TestCase):
    def setUp(self):
        self.b = hb.PanelBrowser("unit-test")
        self.guard = _NoLaunch().__enter__()

    def tearDown(self):
        self.guard.__exit__()

    def rpc(self, method, params=None, rid=1):
        doc = {"jsonrpc": "2.0", "method": method}
        if rid is not None:
            doc["id"] = rid
        if params is not None:
            doc["params"] = params
        return hb.rpc(self.b, doc)

    def call(self, name, args=None):
        return self.rpc("tools/call", {"name": name, "arguments": args or {}})["result"]

    def test_initialize_and_list(self):
        r = self.rpc("initialize", {"protocolVersion": "2025-03-26"})["result"]
        self.assertEqual(r["protocolVersion"], "2025-03-26")
        self.assertEqual(r["serverInfo"]["name"], "qwen-browser")
        self.assertIn("tools", r["capabilities"])
        tools = self.rpc("tools/list")["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, TOOL_NAMES)
        for t in tools:
            with self.subTest(tool=t["name"]):
                self.assertEqual(t["inputSchema"]["type"], "object")
                self.assertTrue(t["description"])
        self.assertEqual(set(hb.READ_ONLY_TOOLS), READ_ONLY)
        self.assertEqual(self.rpc("ping")["result"], {})

    def test_notifications_batches_and_errors(self):
        self.assertIsNone(self.rpc("notifications/initialized", rid=None))
        out = hb.rpc(self.b, [{"jsonrpc": "2.0", "method": "notifications/initialized"},
                              {"jsonrpc": "2.0", "id": 7, "method": "ping"}])
        self.assertEqual(out, [{"jsonrpc": "2.0", "id": 7, "result": {}}])
        self.assertEqual(self.rpc("resources/list")["error"]["code"], -32601)
        self.assertEqual(hb.rpc(self.b, "nope")["error"]["code"], -32600)

    def test_forbidden_addresses_are_refused_before_the_browser_starts(self):
        for url in ("http://127.0.0.1:8100/", "localhost:8104", "file:///C:/LLM/secrets/local-services.token",
                    "http://192.168.1.1/", "javascript:alert(1)", ""):
            with self.subTest(url=url):
                r = self.call("browser_navigate", {"url": url})
                self.assertTrue(r.get("isError"), r)
                self.assertFalse(self.b.running())
        self.assertIsNone(self.b.proc)

    def test_bad_requests_are_refused_before_the_browser_starts(self):
        cases = [("browser_upload", {"paths": ["C:/Windows/win.ini"]}), ("browser_upload", {"paths": []}),
                 ("browser_upload", {"paths": ["x%d.txt" % i for i in range(30)]}),
                 ("browser_evaluate", {"expression": "  "}), ("browser_fill", {"fields": []}),
                 ("browser_click", {"ref": 1, "button": "side"}), ("browser_click", {"ref": 1, "modifiers": "hyper"}),
                 ("browser_tabs", {"action": "new", "url": "http://127.0.0.1:8100/"})]
        for name, args in cases:
            with self.subTest(name=name, args=args):
                r = self.call(name, args)
                self.assertTrue(r.get("isError"), r)
                self.assertFalse(self.b.running())
        r = self.call("browser_tabs", {"action": "close_browser"})
        self.assertFalse(r.get("isError"))

    def test_tools_without_a_browser(self):
        r = self.call("browser_tabs")
        self.assertFalse(r.get("isError"))
        self.assertIn("browser_navigate", r["content"][0]["text"])
        r = self.call("browser_unknown")
        self.assertTrue(r.get("isError"))
        self.assertFalse(self.b.running())


class PanelHttpTests(unittest.TestCase):
    def setUp(self):
        self.slug = "unit-http-" + secrets.token_hex(3)
        self.guard = _NoLaunch().__enter__()

    def tearDown(self):
        self.guard.__exit__()
        with hb._reg_lock:
            hb._browsers.pop(self.slug, None)

    def http(self, method, sub, body=None, query=""):
        raw = json.dumps(body).encode() if isinstance(body, (dict, list)) else (body or b"")
        code, ctype, payload, extra = hb.http(self.slug, method, sub, query, raw)
        doc = json.loads(payload) if payload and ctype.startswith("application/json") else None
        return code, doc, extra

    def test_state_before_start_does_not_launch(self):
        code, doc, _ = self.http("GET", "state")
        self.assertEqual(code, 200)
        self.assertFalse(doc["running"])
        self.assertEqual(doc["tabs"], [])
        self.assertIsNone(doc["dialog"])
        code, doc, _ = self.http("GET", "")
        self.assertEqual(code, 200)

    def test_frame_needs_a_running_browser(self):
        code, doc, _ = self.http("GET", "frame", query="after=0&wait=0")
        self.assertEqual(code, 409)
        self.assertFalse(doc["state"]["running"])

    def test_view_is_clamped(self):
        code, doc, _ = self.http("POST", "view", {"w": 10, "h": 99999, "dpr": 3})
        self.assertEqual(code, 200)
        self.assertEqual(doc["view"], {"w": 320, "h": 1600, "dpr": 2.0})

    def test_misc_routes(self):
        self.assertEqual(self.http("GET", "mcp")[0], 405)
        self.assertEqual(self.http("POST", "mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"})[0], 202)
        self.assertEqual(self.http("POST", "mcp", b"{not json")[0], 400)
        self.assertEqual(self.http("POST", "nav", {"action": "explode"})[0], 400)
        self.assertEqual(self.http("POST", "nav", {"action": "activate", "tab": "x"})[0], 400)
        self.assertEqual(self.http("POST", "input", {"type": "telepathy"})[0], 400)
        self.assertEqual(self.http("POST", "input", {"type": "mouse", "event": "down"})[0], 400)
        code, doc, _ = self.http("POST", "dialog", {"accept": True})
        self.assertEqual((code, doc["ok"]), (200, False))
        self.assertEqual(self.http("POST", "notice", {})[0], 200)
        self.assertEqual(self.http("GET", "nope")[0], 405)
        self.assertEqual(self.http("POST", "nope", {})[0], 404)
        code, doc, _ = self.http("POST", "start", {"url": "http://127.0.0.1:8100/"})
        self.assertEqual(code, 400)


# ------------------------------------------------------------------------------------------------ hub.py
PROJECT = {"slug": "bptest", "name": "bptest", "port": 0, "system_prompt": "", "think": "off", "extend": True}


class _TokenMixin:
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hubbp-")
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


class HubWiringTests(_TokenMixin, unittest.TestCase):
    def test_browser_mcp_row(self):
        rows = {r["id"]: r for r in hub.mcp_servers(dict(PROJECT, port=8123))}
        row = rows["browser"]
        self.assertEqual(row["url"], "http://127.0.0.1:8123/_qwen/browser/mcp")
        self.assertIs(row["enabled"], True)
        self.assertIs(row["useProxy"], False)
        self.assertEqual(json.loads(row["headers"]), {"Authorization": "Bearer " + self.token})
        self.assertNotIn("headers", {r["id"]: r for r in hub.mcp_servers(dict(PROJECT, port=8123), with_auth=False)}["browser"])

    def test_project_folders_and_prompt(self):
        # ทุกสำเนาของ hub.py ที่ถูกโหลดในโปรเซสเดียวกัน (เทสต์ไฟล์อื่นก็โหลด) ตั้ง hook นี้ใหม่ — ตัวสุดท้ายชนะ
        # จึงตรวจ hook ที่ติดอยู่จริงกับ DATA_ROOT ของโมดูลที่ตั้งมัน ไม่ผูกกับสำเนาใดสำเนาหนึ่ง
        fn = hub._browser.PROJECT_DIRS
        with mock.patch.dict(fn.__globals__, {"DATA_ROOT": Path(self.tmp) / "data"}):
            att, out = fn("bptest")
        self.assertEqual(Path(att), Path(self.tmp) / "data" / "bptest" / "attachments")
        self.assertEqual(Path(out), Path(self.tmp) / "data" / "bptest" / "outputs")
        base = hub.base_system_prompt("Qwen3.8-27B-UD-Q4_K_M", "th")
        self.assertIn(hub._browser.GUIDANCE, base)
        self.assertIn("browser_*", base)
        self.assertTrue(base.endswith(hub._browser.GUIDANCE))

    def test_plan_mode_keeps_only_reading_tools(self):
        self.assertEqual(TOOL_NAMES & hub.PLAN_KEEP_TOOLS, READ_ONLY)
        self.assertEqual(TOOL_NAMES & hub.PLAN_DROP_TOOLS, TOOL_NAMES - READ_ONLY)
        self.assertEqual({t["name"] for t in hub._browser.TOOLS}, TOOL_NAMES)

    def test_browser_routes_are_project_data(self):
        for route in ("/_qwen/browser", "/_qwen/browser/state", "/_qwen/browser/mcp", "/_qwen/browser/frame"):
            with self.subTest(route=route):
                self.assertTrue(hub.is_own_data_route(route))

    def test_shell_loads_the_panel_and_webui_loads_the_queue_first(self):
        with mock.patch.object(hub, "upstream_models", return_value=[]), \
                mock.patch.object(hub, "upstream_model", return_value=""):
            page = hub.build_shell(dict(PROJECT, port=8175), [dict(PROJECT, port=8175)], "", "th")
        self.assertIn('<script src="/_qwen/static/browser-panel.js?v=', page)
        self.assertNotIn("__BP_VER__", page)
        inject = hub.webui_inject()
        self.assertIn("/_qwen/static/message-queue.js?v=", inject)
        self.assertLess(inject.index("message-queue.js"), inject.index("auto-recovery.js"))


def _req(port, method, path, headers=None, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, data


class ProjectRouteTests(_TokenMixin, unittest.TestCase):
    """เส้นทาง /_qwen/browser ผ่าน handler จริงของพอร์ตโปรเจกต์ (ไม่มี upstream — ไม่ถึง router)"""

    def setUp(self):
        super().setUp()
        # พอร์ตต้องอยู่ในช่วงของเรา (8100-8179) ไม่งั้น Origin ของหน้าตัวเองก็ไม่ผ่าน origin_allowed — ใช้ปลายช่วงที่ว่าง
        handler = hub.make_proxy_handler("bptest", lambda: [self.proj])
        self.srv = None
        for port in range(8179, 8159, -1):
            with socket.socket() as probe:          # Windows: SO_REUSEADDR ให้ bind ซ้อนพอร์ตที่มีคนใช้อยู่ได้ — ถามก่อนว่าว่างจริง
                probe.settimeout(0.3)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    continue
            try:
                self.srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
                break
            except OSError:
                continue
        if self.srv is None:
            super().tearDown()
            self.skipTest("ไม่มีพอร์ตว่างในช่วง 8160-8179")
        self.port = self.srv.server_address[1]
        self.proj = dict(PROJECT, port=self.port)
        self.own = "http://127.0.0.1:%d" % self.port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.guard = mock.patch.object(hub._browser.PanelBrowser, "_start",
                                       side_effect=AssertionError("browser must not launch"))
        self.guard.start()

    def tearDown(self):
        self.guard.stop()
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def mcp(self, headers):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
        return _req(self.port, "POST", "/_qwen/browser/mcp", dict({"Content-Type": "application/json"}, **headers), body)

    def test_state_for_our_page_only(self):
        # แผงถามสถานะแบบ same-origin GET (เบราว์เซอร์ไม่ส่ง Origin) / POST มี Origin ของพอร์ตนี้ / โปรแกรมในเครื่อง
        for hdr in ({"Sec-Fetch-Site": "same-origin"}, {"Origin": self.own, "Sec-Fetch-Site": "same-origin"}, {}):
            with self.subTest(h=hdr):
                st, h, body = _req(self.port, "GET", "/_qwen/browser/state", hdr)
                self.assertEqual(st, 200)
                self.assertFalse(json.loads(body)["running"])
                self.assertEqual(h.get("cache-control"), "no-store")
                self.assertEqual(h.get("x-content-type-options"), "nosniff")
        st, _h, body = _req(self.port, "POST", "/_qwen/browser/view", {"Origin": self.own, "Sec-Fetch-Site": "same-origin",
                                                                      "Content-Type": "application/json"},
                            json.dumps({"w": 800, "h": 600}).encode())
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body)["view"]["w"], 800)
        for hdr in ({"Origin": "http://evil.example"}, {"Origin": "http://127.0.0.1:8103"}, {"Origin": "null"},
                    {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"},
                    {"Host": "rebind.example:%d" % self.port}):
            with self.subTest(h=hdr):
                st, _h, _b = _req(self.port, "GET", "/_qwen/browser/state", hdr)
                self.assertEqual(st, 403)

    def test_mcp_needs_the_token(self):
        st, _h, body = self.mcp({"Origin": self.own, "Authorization": "Bearer " + self.token})
        self.assertEqual(st, 200)
        self.assertEqual({t["name"] for t in json.loads(body)["result"]["tools"]}, TOOL_NAMES)
        for hdr in ({"Origin": self.own}, {"Origin": self.own, "Authorization": "Bearer wrong"},
                    {"Origin": self.own, "Authorization": self.token}):
            with self.subTest(h=sorted(hdr)):
                st, _h, body = self.mcp(hdr)
                self.assertEqual(st, 401)
                self.assertNotIn(self.token.encode(), body)
        st, _h, _b = self.mcp({"Origin": "http://evil.example", "Authorization": "Bearer " + self.token})
        self.assertEqual(st, 403)

    def test_panel_actions_refuse_other_sites(self):
        for path, doc in (("/_qwen/browser/start", {"url": "https://example.com/"}),
                          ("/_qwen/browser/input", {"type": "text", "text": "x"}),
                          ("/_qwen/browser/nav", {"action": "go", "url": "https://example.com/"})):
            with self.subTest(path=path):
                st, _h, _b = _req(self.port, "POST", path, {"Origin": "http://evil.example",
                                                            "Content-Type": "text/plain"}, json.dumps(doc).encode())
                self.assertEqual(st, 403)


# ------------------------------------------------------------------------------------------------ สคริปต์หน้าเว็บ
@unittest.skipUnless(node_exe(), "Node is required")
class FrontendSyntaxTests(unittest.TestCase):
    def test_scripts_parse(self):
        for name in ("browser-panel.js", "message-queue.js", "auto-recovery.js", "boot.js"):
            with self.subTest(name=name):
                r = subprocess.run([node_exe(), "--check", str(STATIC / name)], capture_output=True, timeout=30)
                self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-600:])

    def test_panel_and_queue_keep_their_public_hooks(self):
        panel = (STATIC / "browser-panel.js").read_text(encoding="utf-8")
        queue = (STATIC / "message-queue.js").read_text(encoding="utf-8")
        self.assertIn("window.qwenBrowserPanel", panel)
        self.assertIn("/_qwen/browser/", panel)
        self.assertNotIn("var CSS =", panel)          # เคยบัง CSS.escape ของเบราว์เซอร์
        self.assertIn("window.qwenQueue", queue)
        self.assertIn("qwen-message-queue-v1", queue)
        self.assertNotIn("var CSS =", queue)


# ------------------------------------------------------------------------------------------------ ทดสอบสด (เลือกเปิด)
_LIVE_PAGE_JS = r"""
document.title = 'controls';
document.body.innerHTML = '<h1>controls</h1>' +
  '<label for=fr>fruit</label><select id=fr><option value="">--</option><option value=a>apple</option><option value=b>banana</option></select>' +
  '<label><input type=checkbox id=ok> agree</label>' +
  '<label for=nm>name</label><input id=nm>' +
  '<label for=pw>password</label><input id=pw type=password>' +
  '<div id=menu style="display:inline-block;padding:6px;border:1px solid #888">menu<div id=sub style="display:none">secret item</div></div>' +
  '<p><span id=drag draggable=true style="display:inline-block;width:80px;height:30px;background:#fc8">drag me</span>' +
  '<span id=drop style="display:inline-block;width:150px;height:50px;border:2px dashed #888;margin-left:30px">drop here</span>' +
  '<span id=dropOut>not dropped</span></p>' +
  '<p><input type=file id=f1 style="display:none" multiple><button id=pick type=button>choose files</button><span id=fileOut></span></p>' +
  '<p><button id=later type=button>later</button><span id=lateOut></span> <button id=dl type=button>download</button></p>' +
  '<table id=tbl><tr><td>coffee</td><td>55</td></tr><tr><td>tea</td><td>40</td></tr></table>';
var $ = function (id) { return document.getElementById(id); };
$('menu').onmouseenter = function () { $('sub').style.display = 'block'; };
$('drag').addEventListener('dragstart', function (e) { e.dataTransfer.setData('text/plain', 'drag me'); });
$('drop').addEventListener('dragover', function (e) { e.preventDefault(); });
$('drop').addEventListener('drop', function (e) { e.preventDefault(); $('dropOut').textContent = 'dropped: ' + e.dataTransfer.getData('text/plain'); });
$('pick').onclick = function () { $('f1').click(); };
$('f1').onchange = function () { $('fileOut').textContent = [].map.call(this.files, function (f) { return f.name + ':' + f.size; }).join(','); };
$('later').onclick = function () { setTimeout(function () { $('lateOut').textContent = 'loaded now'; }, 1200); };
$('dl').onclick = function () { var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['live ok'])); a.download = 'ทดสอบ.txt'; document.body.appendChild(a); a.click(); };
1
"""


@unittest.skipUnless(os.environ.get("QWEN_BROWSER_LIVE_TEST") == "1", "ตั้ง QWEN_BROWSER_LIVE_TEST=1 เพื่อเปิด Edge จริง")
class LiveBrowserTests(unittest.TestCase):
    def test_headless_panel_browser(self):
        try:
            hb.resolve_public("example.com", 443)               # รวม DNS สำรองแล้ว
        except (OSError, ValueError):
            self.skipTest("เครื่องนี้หาที่อยู่ example.com ไม่ได้ตอนนี้ (DNS/เน็ต) — ข้ามเทสต์ที่ต้องออกเน็ต")
        tmp = tempfile.mkdtemp(prefix="bp-live-")
        b = None
        try:
            with mock.patch.object(hb, "PROFILE_ROOT", Path(tmp)), mock.patch.object(hb, "PROXY_PORT_PREF", 0):
                b = hb.PanelBrowser("live-test")
                started = time.time()
                r = hb.call_tool(b, "browser_navigate", {"url": "https://example.com/"})
                self.assertFalse(r.get("isError"), r)
                self.assertIn("Example", r["content"][0]["text"])
                self.assertLess(time.time() - started, 45)
                r = hb.call_tool(b, "browser_read", {})
                self.assertIn("Example Domain", r["content"][0]["text"])
                self.assertIn(hb.DATA_NOTE, r["content"][0]["text"])
                r = hb.call_tool(b, "browser_screenshot", {})
                self.assertEqual(r["content"][1]["type"], "image")
                self.assertGreater(len(r["content"][1]["data"]), 1000)
                # หน้าเว็บสาธารณะยิงเข้าเครื่องนี้ไม่ได้ (พร็อกซีบล็อก loopback) — ทั้ง fetch จากหน้าเว็บ
                c = b._c()
                tid, sid = b.active_session()
                res = c.call("Runtime.evaluate", {"expression": "fetch('http://127.0.0.1:8100/health').then(r => 'open:' + r.status, e => 'blocked')",
                                                  "awaitPromise": True, "returnByValue": True}, sid, timeout=20)
                self.assertEqual(res.get("result", {}).get("value"), "blocked")
                # ...และการนำทางตรงผ่าน CDP ที่ข้ามการตรวจ URL ของเรา (เหลือแต่พร็อกซีกั้น)
                c.call("Page.navigate", {"url": "http://127.0.0.1:8100/health"}, sid, timeout=20)
                time.sleep(2.0)
                page = b.eval_json("JSON.stringify({u: location.href, t: document.body ? document.body.innerText : ''})")
                self.assertTrue("ไม่เปิดที่อยู่นี้" in page["t"] or page["u"].startswith("chrome-error") or "ERR_" in page["t"], page)
                self.assertNotIn('"status"', page["t"])
                self.assertTrue(b.state()["running"])
        finally:
            if b is not None:
                b.shutdown()
            time.sleep(1.0)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dns_outage_uses_public_dns(self):
        """จำลอง DNS ที่ Wi-Fi แจกมาล่ม (ตอบไม่ได้) เฉพาะในโปรเซสนี้ แล้วเปิดเว็บจริงผ่าน DNS สาธารณะ"""
        def outage(host, port):
            try:
                __import__("ipaddress").ip_address(str(host).strip("[]"))
                return socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
            except ValueError:
                raise socket.gaierror(socket.EAI_AGAIN, "simulated Wi-Fi DNS outage") from None
        hb._dns_reset()
        udp = hb._udp_ask("example.com", 1, 3.0)
        doh = hb._doh_ask("example.com", 1, 6.0)
        if udp[0] != "ok" and doh[0] != "ok":
            self.skipTest("ติดต่อ DNS สาธารณะไม่ได้ตอนนี้ (UDP %s / DoH %s) — ข้าม" % (udp[0], doh[0]))
        for got in (udp, doh):                                  # ทางที่ใช้ได้ต้องได้ที่อยู่สาธารณะจริง
            if got[0] == "ok":
                self.assertTrue(all(hb.ip_public(ip) for ip in got[1]), got)
        tmp = tempfile.mkdtemp(prefix="bp-live-dns-")
        b = None
        try:
            with mock.patch.object(hb, "PROFILE_ROOT", Path(tmp)), mock.patch.object(hb, "PROXY_PORT_PREF", 0), \
                    mock.patch.object(hb, "_system_lookup", outage):
                with self.assertRaises(socket.gaierror):
                    hb._system_lookup("example.com", 443)
                b = hb.PanelBrowser("live-dns")
                r = hb.call_tool(b, "browser_navigate", {"url": "https://example.com/"})
                self.assertFalse(r.get("isError"), r)
                r = hb.call_tool(b, "browser_read", {})
                self.assertIn("Example Domain", r["content"][0]["text"])
                st = hb.dns_status()
                self.assertTrue(st["system_bad"], st)
                self.assertGreater(st["public_answers"], 0, st)
                # ชื่อที่ไม่มีจริง: เหตุผลจากพร็อกซีต้องไปถึงโมเดล (ไม่ใช่แค่ ERR_TUNNEL_CONNECTION_FAILED)
                r = hb.call_tool(b, "browser_navigate", {"url": "https://qwen-no-such-name-%s.com/" % os.urandom(4).hex()})
                self.assertTrue(r.get("isError"), r)
                self.assertIn("ไม่มีชื่อนี้", r["content"][0]["text"])
        finally:
            if b is not None:
                b.shutdown()
            hb._dns_reset()
            time.sleep(1.0)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_controls_on_a_real_page(self):
        import re
        tmp = Path(tempfile.mkdtemp(prefix="bp-live-ctl-", dir=os.path.dirname(os.path.abspath(__file__))))
        prof = tempfile.mkdtemp(prefix="bp-live-prof-")
        att, out = tmp / "attachments", tmp / "outputs"
        att.mkdir()
        out.mkdir()
        (att / "up.txt").write_text("upload me", encoding="utf-8")
        b = None

        def call(name, **args):
            r = hb.call_tool(b, name, args)
            return r, "\n".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")

        def js(expr):
            ok, val = b.evaluate(expr)
            self.assertTrue(ok, val)
            return val

        def ref(query, pattern):
            _r, t = call("browser_read", mode="elements", query=query)
            m = re.search(r"\[(\d+)\][^\n]*" + pattern, t)
            self.assertIsNotNone(m, t)
            return int(m.group(1))
        site = tmp / "site"
        site.mkdir()
        (site / "index.html").write_text("<!doctype html><meta charset=utf-8><title>live</title><body>live</body>",
                                         encoding="utf-8")

        class _Quiet(SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
        srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(site)))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        sport = srv.server_address[1]
        base = "http://127.0.0.1:%d/" % sport
        real_resolve, real_norm = hb.resolve_public, hb.normalize_url

        def resolve(host, port):              # เฉพาะเทสต์นี้: พร็อกซีของเทสต์ยอมให้เข้าเว็บทดสอบบนเครื่องนี้พอร์ตเดียว
            if str(host).strip("[]") == "127.0.0.1" and int(port) == sport:
                return socket.AF_INET, ("127.0.0.1", sport)
            return real_resolve(host, port)
        try:
            with mock.patch.object(hb, "PROFILE_ROOT", Path(prof)), mock.patch.object(hb, "PROXY_PORT_PREF", 0), \
                    mock.patch.object(hb, "PROJECT_DIRS", lambda slug: (att, out)), \
                    mock.patch.object(hb, "resolve_public", resolve), \
                    mock.patch.object(hb, "normalize_url", lambda u: u if str(u).startswith(base) else real_norm(u)):
                b = hb.PanelBrowser("live-controls")
                r, t = call("browser_navigate", url=os.environ.get("QWEN_BROWSER_LIVE_URL") or base + "index.html")
                self.assertFalse(r.get("isError"), t)
                js(_LIVE_PAGE_JS)
                r, t = call("browser_fill", fields=[{"ref": ref("fruit", "select"), "value": "banana"},
                                                    {"ref": ref("agree", "checkbox"), "value": "true"},
                                                    {"ref": ref("name", "textbox"), "value": "สมชาย"}])
                self.assertFalse(r.get("isError"), t)
                self.assertEqual(js("[fr.value, ok.checked, nm.value].join('|')"), "b|true|สมชาย")
                r, t = call("browser_type", ref=ref("password", "textbox"), text="secret")
                self.assertTrue(r.get("isError"), t)
                self.assertEqual(js("pw.value"), "")
                call("browser_screenshot")
                rect = json.loads(js("JSON.stringify(menu.getBoundingClientRect())"))
                with b.lock:
                    sc = b.shot_scale.get(b.active, 1.0)
                call("browser_click", x=(rect["left"] + 10) / sc, y=(rect["top"] + 8) / sc, hover=True)
                self.assertIn("secret item", call("browser_read")[1])
                drop = json.loads(js("JSON.stringify(drop.getBoundingClientRect())"))
                r, t = call("browser_click", ref=ref("drag me", "drag me"),
                            drag_to_x=(drop["left"] + drop["width"] / 2) / sc, drag_to_y=(drop["top"] + drop["height"] / 2) / sc)
                self.assertEqual(js("dropOut.textContent"), "dropped: drag me", t)
                r, t = call("browser_upload", ref=ref("choose files", "button"), paths=["attachments/up.txt"])
                self.assertFalse(r.get("isError"), t)
                self.assertEqual(js("fileOut.textContent"), "up.txt:9")
                call("browser_click", ref=ref("later", "button"))
                r, t = call("browser_wait", text="loaded now", timeout=8)
                self.assertIn("loaded now", js("lateOut.textContent"), t)
                r, t = call("browser_click", ref=ref("download", "button"))
                r, t = call("browser_wait", download=True, timeout=30)
                self.assertTrue((out / "ทดสอบ.txt").is_file(), (t, [p.name for p in out.iterdir()]))
                self.assertEqual((out / "ทดสอบ.txt").read_text(encoding="utf-8"), "live ok")
                r, t = call("browser_evaluate", expression="[...tbl.rows].map(r => [...r.cells].map(c => c.textContent))")
                self.assertIn('[["coffee","55"],["tea","40"]]', t)
                r, t = call("browser_screenshot", ref=ref("fruit", "select"))
                self.assertEqual(r["content"][1]["type"], "image")
        finally:
            if b is not None:
                b.shutdown()
            srv.shutdown()
            srv.server_close()
            time.sleep(1.0)
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(prof, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
