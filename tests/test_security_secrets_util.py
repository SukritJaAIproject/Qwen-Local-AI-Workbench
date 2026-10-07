# -*- coding: utf-8 -*-
"""
เทสต์หน่วยของ secrets_util (สัญญา C1/C2) — ไม่เปิดพอร์ตใดๆ

ทำไมต้องมี
  เดิม check_request / host_allowed / origin_allowed / cors_headers / scrub ถูกทดสอบผ่าน HTTP บนพอร์ต 8891/8892
  (ข้ามทั้งไฟล์ได้ถ้าพอร์ตไม่ว่าง) กับเทสต์ live ที่ต้องเปิดเอง — ด่านเดียวที่กั้นเว็บทั้งโลกออกจากเครื่องมือในเครื่อง
  ต้องมีเทสต์ที่รันทุกครั้ง ไม่ขึ้นกับพอร์ต

สิ่งที่ตรวจ: ตาราง Host × Origin × Authorization × method × path (รวม absolute-form, query, / ท้าย, ตัวพิมพ์),
fail-closed เมื่อไฟล์โทเคนเสีย, CORS echo เฉพาะ origin ในรายการและไม่มี credentials, scrub ลบโทเคนทุกตัวพิมพ์
ปลอดภัยต่อระบบจริง: test_security_common ชี้ LLM_LOCAL_TOKEN_FILE ไปที่โทเคนทดสอบในโฟลเดอร์ชั่วคราว
"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402  (ตั้ง env โทเคนทดสอบก่อน import secrets_util)

sys.path.insert(0, C.LLM_ROOT)
import secrets_util as su  # noqa: E402

PORT = 8792
GOOD_HOST = "127.0.0.1:%d" % PORT


def req(method="POST", path="/mcp", host=GOOD_HOST, origin=None, auth="token"):
    h = {}
    if host is not None:
        h["Host"] = host
    if origin is not None:
        h["Origin"] = origin
    if auth == "token":
        h["Authorization"] = "Bearer " + C.TOKEN
    elif auth is not None:
        h["Authorization"] = auth
    return su.check_request(method, path, h, PORT)


class TokenFileTests(unittest.TestCase):
    def test_uses_test_token_not_real_one(self):
        self.assertEqual(os.path.normcase(str(su.token_path())), os.path.normcase(C.TOKEN_FILE))
        self.assertEqual(su.get_token(), C.TOKEN)

    def test_malformed_token_file_fails_closed(self):
        bad = os.path.join(C.new_dir("badtok"), "t.token")
        with open(bad, "w", encoding="ascii") as fh:
            fh.write("not-a-token")
        with mock.patch.dict(os.environ, {su.TOKEN_ENV: bad}), mock.patch.object(su.time, "sleep"):
            with self.assertRaises(su.TokenError):
                su.get_token()
            self.assertFalse(su.token_matches("not-a-token"))
            self.assertEqual(req(), (401, "missing_or_bad_token"))
            self.assertEqual(su.scrub("x " + C.TOKEN), "x " + C.TOKEN)   # ไม่มีโทเคนที่ถูกต้อง = ไม่มีอะไรให้ลบ
        with open(bad, encoding="ascii") as fh:
            self.assertEqual(fh.read(), "not-a-token", "ห้ามเขียนทับไฟล์โทเคนที่มีอยู่แล้ว")


class CheckRequestMatrixTests(unittest.TestCase):
    def test_valid_request_passes(self):
        self.assertIsNone(req())
        self.assertIsNone(req(host="localhost:%d" % PORT))
        self.assertIsNone(req(host="LOCALHOST:%d" % PORT))
        self.assertIsNone(req(origin="http://127.0.0.1:8103"))
        self.assertIsNone(req(origin="http://localhost:8100"))
        self.assertIsNone(req(origin="http://127.0.0.1:8099"))
        self.assertIsNone(req(auth="bearer " + C.TOKEN))                 # scheme ไม่สนตัวพิมพ์
        self.assertIsNone(req(auth="Bearer   %s  " % C.TOKEN))

    def test_host_rules_anti_rebinding(self):
        for host in ("attacker.example:%d" % PORT, "127.0.0.1:8791", "127.0.0.1", "localhost",
                     "[::1]:%d" % PORT, "127.0.0.1.nip.io:%d" % PORT, "localhost.:%d" % PORT, "", None,
                     "127.0.0.1:%d, evil" % PORT, "0.0.0.0:%d" % PORT):
            with self.subTest(host=host):
                self.assertEqual(req(host=host), (403, "host_not_allowed"))
                # Host ผิดต้องชนะทุกอย่าง แม้เป็น OPTIONS หรือ /health
                self.assertEqual(req("OPTIONS", host=host, auth=None), (403, "host_not_allowed"))
                self.assertEqual(req("GET", "/health", host=host, auth=None), (403, "host_not_allowed"))

    def test_origin_rules(self):
        for origin in ("http://evil.example", "null", "", "https://127.0.0.1:8103", "http://127.0.0.1:8180",
                       "http://127.0.0.1:8098", "http://127.0.0.1:8103/", "http://127.0.0.1:8103.evil.example",
                       "http://127.0.0.1:81030", "http://127.0.0.2:8103", "http://[::1]:8103",
                       "http://user@127.0.0.1:8103", "HTTP://127.0.0.1:8103x"):
            with self.subTest(origin=origin):
                self.assertEqual(req(origin=origin), (403, "origin_not_allowed"))
                self.assertEqual(req("OPTIONS", origin=origin, auth=None), (403, "origin_not_allowed"))
                self.assertFalse(su.origin_allowed(origin))

    def test_token_rules(self):
        for auth in (None, "", "Bearer", "Bearer ", "Basic " + C.TOKEN, C.TOKEN, "Bearer " + C.TOKEN + "x",
                     "Bearer " + C.TOKEN[:-1], "Bearer " + C.TOKEN.upper(), "Bearer " + "0" * 64,
                     "Token " + C.TOKEN):
            with self.subTest(auth=auth):
                self.assertEqual(req(auth=auth), (401, "missing_or_bad_token"))

    def test_preflight_and_public_health(self):
        self.assertIsNone(req("OPTIONS", auth=None))
        self.assertIsNone(req("OPTIONS", origin="http://127.0.0.1:8103", auth=None))
        for path in ("/health", "/health/", "/health?x=1", "/health?"):
            with self.subTest(path=path):
                self.assertIsNone(req("GET", path, auth=None))

    def test_public_path_cannot_be_abused(self):
        # เฉพาะ GET /health เท่านั้นที่ไม่ต้องใช้โทเคน — method อื่น / path ที่หน้าตาคล้าย / absolute-form ต้องใช้
        cases = [("POST", "/health"), ("DELETE", "/health"), ("GET", "/mcp"), ("GET", "/fast/p"),
                 ("GET", "/HEALTH"), ("GET", "//health"), ("GET", "/health/../mcp"), ("GET", "/healthz"),
                 ("GET", "/health%2F..%2Fmcp"), ("GET", "http://127.0.0.1:%d/health" % PORT),
                 ("GET", "http://127.0.0.1:%d/mcp" % PORT), ("GET", "/mcp?/health"), ("GET", ""),
                 ("GET", "*")]
        for method, path in cases:
            with self.subTest(method=method, path=path):
                self.assertEqual(req(method, path, auth=None), (401, "missing_or_bad_token"))

    def test_custom_public_paths(self):
        h = {"Host": GOOD_HOST}
        self.assertIsNone(su.check_request("GET", "/status", h, PORT, public_paths=("/status",)))
        self.assertEqual(su.check_request("GET", "/health", h, PORT, public_paths=("/status",)),
                         (401, "missing_or_bad_token"))

    def test_reasons_never_echo_input(self):
        evil = "http://evil.example/" + C.TOKEN
        for r in (req(origin=evil), req(host=evil), req(auth="Bearer " + C.TOKEN + "zz")):
            self.assertNotIn(C.TOKEN, repr(r))
            self.assertNotIn("evil", repr(r))


class CorsAndScrubTests(unittest.TestCase):
    def test_cors_only_for_allowed_origins_without_credentials(self):
        for origin in (None, "", "http://evil.example", "null", "http://127.0.0.1:8180"):
            with self.subTest(origin=origin):
                self.assertEqual(su.cors_headers(origin), [("Vary", "Origin")])
        got = dict(su.cors_headers("http://127.0.0.1:8103"))
        self.assertEqual(got["Access-Control-Allow-Origin"], "http://127.0.0.1:8103")
        self.assertEqual({h.strip().lower() for h in got["Access-Control-Allow-Headers"].split(",")},
                         {"authorization", "content-type", "mcp-session-id", "mcp-protocol-version",
                          "last-event-id"})
        self.assertIn("Mcp-Session-Id", got["Access-Control-Expose-Headers"])
        self.assertNotIn("Access-Control-Allow-Credentials", got)
        self.assertNotIn("*", got["Access-Control-Allow-Origin"])

    def test_scrub_removes_token_in_any_case(self):
        text = "a %s b %s c %s" % (C.TOKEN, C.TOKEN.upper(), C.TOKEN.lower())
        out = su.scrub(text)
        self.assertNotIn(C.TOKEN.lower(), out.lower())
        self.assertEqual(su.scrub("nothing here"), "nothing here")
        self.assertEqual(su.scrub(""), "")
        self.assertIsNone(su.scrub(None))

    def test_auth_headers_and_bearer_parsing(self):
        self.assertEqual(su.auth_headers(), {"Authorization": "Bearer " + C.TOKEN})
        self.assertEqual(su.bearer_from_header("Bearer abc"), "abc")
        self.assertEqual(su.bearer_from_header("Basic abc"), "")
        self.assertEqual(su.bearer_from_header(None), "")


if __name__ == "__main__":
    unittest.main()
