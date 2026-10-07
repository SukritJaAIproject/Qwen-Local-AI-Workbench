# -*- coding: utf-8 -*-
"""ตรวจสแตกที่รันอยู่จริงหลัง integrator รีสตาร์ต (ปิดไว้เป็นค่าเริ่มต้น)

เปิดด้วย:  set LLM_SECURITY_LIVE=1  แล้วรัน
  C:\\Python313\\python.exe -m unittest C:\\LLM\\tests\\test_security_live.py -v

ยิงแค่คำขอที่ไม่เปลี่ยนอะไร: OPTIONS, GET /health, POST initialize/tools/list แบบ "ไม่มี token"
(ซึ่งต้องโดน 401 อยู่แล้ว) — ไม่อ่านไฟล์ token จริง ไม่เรียกเครื่องมือ ไม่ส่งแชตให้โมเดล
ส่วนการทดสอบว่า "มี token แล้วใช้ได้" ให้ใช้  python C:\\LLM\\mcp-local\\scheduler.py heartbeat
ซึ่งอ่าน token เองโดยไม่แสดงค่า
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

ENABLED = os.environ.get("LLM_SECURITY_LIVE") == "1"


@unittest.skipUnless(ENABLED, "ตั้ง LLM_SECURITY_LIVE=1 เพื่อตรวจสแตกที่รันอยู่จริง")
class LiveMcpTests(unittest.TestCase):
    PORTS = (8791, 8792)

    def test_mcp_requires_token(self):
        for port in self.PORTS:
            if not C.port_in_use(port):
                self.skipTest("พอร์ต %d ไม่ได้เปิดอยู่" % port)
            status, _h, _b = C.rpc(port, "/mcp", "initialize", token=None)
            self.assertEqual(status, 401, "พอร์ต %d ยังรับคำขอที่ไม่มี token" % port)

    def test_mcp_rejects_foreign_origin(self):
        for port in self.PORTS:
            if not C.port_in_use(port):
                self.skipTest("พอร์ต %d ไม่ได้เปิดอยู่" % port)
            status, headers, _b = C.http("OPTIONS", port, "/mcp", headers={
                "Origin": C.EVIL_ORIGIN, "Access-Control-Request-Method": "POST"})
            self.assertNotEqual(headers.get("access-control-allow-origin"), C.EVIL_ORIGIN, port)
            self.assertNotEqual(headers.get("access-control-allow-origin"), "*", port)

    def test_mcp_rejects_rebinding_host(self):
        for port in self.PORTS:
            if not C.port_in_use(port):
                self.skipTest("พอร์ต %d ไม่ได้เปิดอยู่" % port)
            status, _h, _b = C.http("GET", port, "/health", host="attacker.example:%d" % port)
            self.assertEqual(status, 403, port)

    def test_health_public_and_minimal(self):
        for port in self.PORTS:
            if not C.port_in_use(port):
                self.skipTest("พอร์ต %d ไม่ได้เปิดอยู่" % port)
            status, _h, body = C.http("GET", port, "/health")
            self.assertEqual(status, 200)
            self.assertNotIn("tools", json.loads(body))


@unittest.skipUnless(ENABLED, "ตั้ง LLM_SECURITY_LIVE=1 เพื่อตรวจสแตกที่รันอยู่จริง")
class LiveLlamaServerTests(unittest.TestCase):
    """สัญญา C4 (งานของเจ้าของ launcher) — ตรวจจากภายนอกว่า router ไม่สะท้อน Origin แปลกปลอม"""

    PORT = 8099

    def setUp(self):
        if not C.port_in_use(self.PORT):
            self.skipTest("llama-server ไม่ได้เปิดอยู่")

    def test_no_foreign_origin_with_credentials(self):
        status, headers, _b = C.http("OPTIONS", self.PORT, "/v1/models", headers={
            "Origin": C.EVIL_ORIGIN, "Access-Control-Request-Method": "GET"})
        acao = headers.get("access-control-allow-origin")
        self.assertNotIn(acao, (C.EVIL_ORIGIN, "*"), "llama-server ยังเปิด CORS ให้ทุก Origin")
        self.assertNotEqual(headers.get("access-control-allow-credentials", "").lower(), "true")

    def test_cors_proxy_not_exposed_to_foreign_origin(self):
        status, headers, _b = C.http(
            "GET", self.PORT, "/cors-proxy?url=" + "http%3A%2F%2F127.0.0.1%3A8792%2Fhealth",
            headers={"Origin": C.EVIL_ORIGIN})
        self.assertNotEqual(headers.get("access-control-allow-origin"), C.EVIL_ORIGIN)


if __name__ == "__main__":
    unittest.main()
