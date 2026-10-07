# -*- coding: utf-8 -*-
"""เทสต์ถดถอยของ SSRF (ช่องโหว่ V5): fetch_url ของ mcp-websearch และเครื่องมือเบราว์เซอร์ของ mcp-local

เป้าหมายภายในในเทสต์คือเว็บเซิร์ฟเวอร์เล็กๆ บน 127.0.0.1 พอร์ตสุ่มที่เทสต์เปิดเอง
ถ้าเครื่องมือดึงเนื้อหามาได้ จะเห็นข้อความ MARKER ในผลลัพธ์ = ยิงเข้าเครือข่ายภายในได้ = ช่องโหว่
ไม่มีการออกอินเทอร์เน็ตจริงในไฟล์นี้ (โดเมนสาธารณะถูกจำลองด้วยการแทน getaddrinfo)
"""
import os
import socket
import sys
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

tools_browser = C.import_local("tools_browser")
guard = C.import_local("guard")
ws = C.import_websearch()

try:
    netguard = C.import_local("netguard")
except ImportError:                     # โค้ดรุ่นเก่ายังไม่มีโมดูลนี้
    netguard = None


class WebsearchFetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = C.LocalHTTPServer()

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()

    def test_fetch_url_blocks_loopback(self):
        for url in ("http://127.0.0.1:%d/" % self.srv.port,
                    "http://localhost:%d/" % self.srv.port,
                    "http://2130706433:%d/" % self.srv.port,
                    "http://127.1:%d/" % self.srv.port,
                    "http://0x7f.0.0.1:%d/" % self.srv.port,
                    "http://[::ffff:127.0.0.1]:%d/" % self.srv.port):
            try:
                out = ws.fetch_url(url)
            except Exception as exc:     # noqa: BLE001 — โค้ดเก่าอาจโยน error แทนการปฏิเสธ
                out = "EXC %s" % exc
            self.assertNotIn(C.LocalHTTPServer.MARKER, out, url)

    @unittest.skipIf(C.OLD_CODE_MODE, "โค้ดเก่าจะยิงบริการจริง/วง LAN จริง — ข้ามในโหมดเทียบโค้ดเก่า")
    def test_fetch_url_blocks_stack_services_and_metadata(self):
        for url in ("http://127.0.0.1:8100/api/projects", "http://127.0.0.1:8792/mcp",
                    "http://169.254.169.254/latest/meta-data/", "http://10.0.0.1/",
                    "http://192.168.1.1/", "http://100.64.0.1/", "http://[fe80::1]/",
                    "http://0/"):
            out = ws.fetch_url(url)
            self.assertTrue(out.startswith("ปฏิเสธ"), "%s -> %s" % (url, out[:120]))

    def test_non_http_schemes_rejected(self):
        for url in ("file:///C:/Windows/win.ini", "ftp://example.com/x"):
            out = ws.fetch_url(url)
            self.assertNotIn("[fonts]", out)
            self.assertFalse(out.startswith("เนื้อหาจาก"), out[:100])


class BrowserToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = C.LocalHTTPServer()

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()

    def test_browser_fetch_blocks_loopback(self):
        out = tools_browser.browser_fetch(project="ssrf-test",
                                          url="http://127.0.0.1:%d/" % self.srv.port)
        self.assertNotIn(C.LocalHTTPServer.MARKER, out)

    def test_allow_local_needs_user_confirmation(self):
        url = "http://127.0.0.1:%d/" % self.srv.port
        out = tools_browser.browser_fetch(project="ssrf-test", url=url, allow_local=True)
        self.assertNotIn(C.LocalHTTPServer.MARKER, out, "allow_local ต้องขอ confirm_token ก่อน")
        tok = C.token_from_hint(out)
        self.assertTrue(tok, out[:200])
        guard = C.import_local("guard")
        with C.confirming(guard, tok):
            out = tools_browser.browser_fetch(project="ssrf-test", url=url, allow_local=True,
                                              confirm_token=tok)
        self.assertIn(C.LocalHTTPServer.MARKER, out, "อนุมัติแล้วต้องเข้าได้จริง")

    @unittest.skipIf(C.OLD_CODE_MODE, "โค้ดเก่าจะยิงบริการจริง — ข้ามในโหมดเทียบโค้ดเก่า")
    def test_stack_ports_blocked_even_with_allow_local(self):
        for url in ("http://127.0.0.1:8792/mcp", "http://localhost:8100/",
                    "http://127.0.0.1:8099/v1/models", "http://169.254.169.254/"):
            out = tools_browser.browser_fetch(project="ssrf-test", url=url, allow_local=True)
            self.assertTrue(out.startswith("ERROR"), "%s -> %s" % (url, out[:150]))
            self.assertNotIn("confirm_token", out, url)


@unittest.skipIf(netguard is None, "โค้ดรุ่นนี้ยังไม่มี netguard")
class NetguardTests(unittest.TestCase):
    BLOCKED = ["http://127.0.0.1/", "http://127.1/", "http://2130706433/", "http://0x7f000001/",
               "http://0177.0.0.1/", "http://[::1]/", "http://[::ffff:127.0.0.1]/",
               "http://[::ffff:7f00:1]/", "http://169.254.169.254/", "http://10.1.2.3/",
               "http://172.16.0.1/", "http://192.168.0.1/", "http://100.64.0.1/", "http://0/",
               "http://[fe80::1]/", "http://[fc00::1]/", "http://[2002:7f00:1::1]/",
               "http://[64:ff9b::7f00:1]/", "http://224.0.0.1/", "http://localhost/",
               "file:///C:/x", "ftp://example.com/", "gopher://127.0.0.1/"]

    def test_internal_targets_blocked(self):
        for url in self.BLOCKED:
            with self.assertRaises(ValueError, msg=url):
                netguard.check_target(url, allow_local=False, add_scheme=False)

    def test_public_literal_allowed(self):
        self.assertEqual(netguard.check_target("http://93.184.216.34/x", False, False),
                         "http://93.184.216.34/x")

    def test_allow_local_still_blocks_stack_and_link_local(self):
        self.assertTrue(netguard.check_target("http://127.0.0.1:3000/", True, False))
        for url in ("http://127.0.0.1:8792/", "http://127.0.0.1:8100/", "http://127.0.0.1:8150/",
                    "http://127.0.0.1:8780/", "http://127.0.0.1:8099/", "http://169.254.169.254/"):
            with self.assertRaises(ValueError, msg=url):
                netguard.check_target(url, True, False)

    def test_redirect_to_internal_rejected(self):
        handler = netguard.GuardedRedirect(False)
        req = urllib.request.Request("http://93.184.216.34/")
        for target in ("http://127.0.0.1:8100/", "http://169.254.169.254/", "file:///C:/x"):
            with self.assertRaises(urllib.error.URLError, msg=target):
                handler.redirect_request(req, None, 302, "Found", {}, target)

    def test_dns_rebinding_blocked_at_connect(self):
        """ตรวจตอนแปลงชื่อได้ IP สาธารณะ แต่ตอนต่อจริงชื่อเดียวกันกลายเป็น 127.0.0.1"""
        srv = C.LocalHTTPServer()
        calls = {"n": 0}
        real = socket.getaddrinfo

        def fake(host, port, *a, **kw):
            if host == "rebind.invalid":
                calls["n"] += 1
                ip = "93.184.216.34" if calls["n"] == 1 else "127.0.0.1"
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
            return real(host, port, *a, **kw)

        socket.getaddrinfo = fake
        try:
            url = "http://rebind.invalid:%d/" % srv.port
            netguard.check_target(url, False, False)          # รอบแรกผ่าน (IP สาธารณะ)
            with self.assertRaises((ValueError, urllib.error.URLError, OSError)):
                netguard.build_opener(False).open(url, timeout=5).read()
            self.assertEqual(srv.seen_headers, [], "ต้องไม่มีคำขอไปถึงเป้าหมายภายในเลย")
        finally:
            socket.getaddrinfo = real
            srv.close()

    def test_env_proxy_is_ignored(self):
        opener = netguard.build_opener(False)
        names = {type(h).__name__ for h in opener.handlers}
        self.assertNotIn("ProxyHandler", names)
        self.assertNotIn("FTPHandler", names)
        self.assertNotIn("FileHandler", names)
        self.assertNotIn("DataHandler", names)


if __name__ == "__main__":
    unittest.main()
