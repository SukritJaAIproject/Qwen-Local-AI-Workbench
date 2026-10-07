# -*- coding: utf-8 -*-
"""เทสต์ชั้น HTTP ของงานค้นคว้า: ไคลเอนต์ของจริง (LLMClient / WebClient) กับเซิร์ฟเวอร์จำลองบน 127.0.0.1 พอร์ตสุ่ม
และ MCP ตัวจริงบนพอร์ตสำรองที่ชี้ router/websearch ไปที่ของจำลอง (token ทดสอบ ข้อมูลใน temp — ไม่แตะบริการจริง)

ตรวจ
  * สตรีม SSE แบบ chunked ของ llama-server ต่อชิ้นได้ถูก, ส่ง Bearer (token ทดสอบ), ขอ response_format json_schema และปิดการคิด
  * router ไม่รับ schema (400) -> ขอใหม่แบบไม่มี schema เอง, 401 = fatal, router ไม่เปิด = conn/fatal, เงียบเกินเวลา = timeout
  * ยกเลิกกลางสตรีม: คืนภายในไม่กี่วินาทีและปิด socket (llama-server จึงหยุดสร้างข้อความ)
  * WebClient: JSON-RPC + Bearer ไปที่ websearch, ไม่ส่ง Origin, แยกผลค้น/หน้าเว็บ, 401 = conn, isError = ข้อผิดพลาด
  * ทั้งท่อผ่าน MCP จริง: local_do research -> research_status จนเสร็จ -> ไฟล์รายงานใน outputs + ผิวเต็ม + ด่าน Origin
"""
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

guard = C.import_local("guard")
tr = C.import_local("tools_research")
ws = C.import_websearch()

WIKI_EXTRACT = ("The Open Charge Point Protocol (OCPP) is an application protocol for communication between "
                "charging stations for electric vehicles and a central management system.\n"
                "A charging station sends a Heartbeat message at a configurable interval so the central system knows "
                "it is online.\n" + "Encyclopedic padding text about protocols and charging networks. " * 15)
OCA_URL = "https://www.openchargealliance.org/protocols/ocpp-16/"
PAGE_OCA = ("OCPP 1.6 overview.\nThe Charge Point SHALL send a Heartbeat.req PDU to the Central System at the "
            "interval configured by the HeartbeatInterval key.\n" + "Background information about the alliance. " * 20)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _QuietServer(http.server.ThreadingHTTPServer):
    """ไคลเอนต์ปิด keep-alive/ยกเลิกสตรีมเป็นเรื่องปกติของเทสต์นี้ — ไม่ต้องพิมพ์ traceback ลง stderr"""
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


# ------------------------------------------------------------------ router จำลอง (SSE แบบ chunked)
def _llm_reply(body):
    sysmsg = body["messages"][0]["content"]
    user = body["messages"][1]["content"]
    if sysmsg.startswith("You plan"):
        return json.dumps({"subquestions": [
            {"q": "What is the OCPP heartbeat?", "search": "Open Charge Point Protocol"},
            {"q": "How is the interval configured?", "search": "OCPP heartbeat interval"},
            {"q": "Who maintains OCPP?", "search": "Open Charge Alliance"}]})
    if sysmsg.startswith("You take research"):
        m = re.search(r"<<<PAGE-(\w+)\n(.*?)\nPAGE-\1>>>", user, re.S)
        lines = [s for s in (m.group(2) if m else "").split("\n") if len(s) > 40 and s != "[...]"]
        return json.dumps({"relevant": True, "claims": [
            {"sub": i, "claim": "Fact: " + s[:80], "quote": s[:100]} for i, s in enumerate(lines[:2], 1)]})
    if sysmsg.startswith("You check research"):          # ขั้นตรวจโน้ต: ทุกข้อผ่าน
        n = len(re.findall(r"(?m)^\d+\. CLAIM: ", user))
        return json.dumps({"verdicts": [{"n": i, "why": "same fact", "supported": True} for i in range(1, n + 1)]})
    return ("## Answer\nOCPP charging stations send Heartbeat messages at a configured interval [1][2].\n"
            "## Details\n### 1. Heartbeat\nThe charge point sends Heartbeat.req [2].\n")


class FakeRouter:
    def __init__(self):
        self.requests, self.mode, self.gone = [], "ok", threading.Event()
        owner = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _authed(self):
                return self.headers.get("Authorization") == "Bearer " + C.TOKEN

            def do_GET(self):
                if self.path == "/health":
                    return self._json(200, {"status": "ok"})
                if self.path == "/v1/models" and self._authed():
                    return self._json(200, {"data": [
                        {"id": "Qwen3-4B-Instruct-2507-Q4_K_M", "status": {"value": "loaded"}},
                        {"id": "mmproj-Qwen3.8-27B-F16", "status": {"value": "unloaded"}},
                        {"id": "Qwen3.8-27B-UD-Q4_K_M", "status": {"value": "unloaded"}}]})
                return self._json(401, {"error": "no"})

            def _chunk(self, text):
                data = text.encode("utf-8")
                self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
                self.wfile.flush()

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                owner.requests.append({"auth": self.headers.get("Authorization"), "host": self.headers.get("Host"),
                                       "origin": self.headers.get("Origin"), "body": body})
                if owner.mode == "deny" or not self._authed():
                    return self._json(401, {"error": {"message": "Invalid API Key"}})
                if owner.mode == "reject_schema" and "response_format" in body:
                    return self._json(400, {"error": {"message": "response_format not supported"}})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                if owner.mode == "stall":
                    time.sleep(3)
                    return
                text = "x" * 400 if owner.mode == "slow" else _llm_reply(body)
                step = 4 if owner.mode == "slow" else max(1, len(text) // 3)
                try:
                    for i in range(0, len(text), step):
                        ev = {"choices": [{"delta": {"content": text[i:i + step]}, "finish_reason": None}]}
                        self._chunk("data: %s\n\n" % json.dumps(ev))
                        if owner.mode == "slow":
                            time.sleep(0.2)
                    self._chunk('data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\n')
                    self._chunk("data: [DONE]\n\n")
                    self.wfile.write(b"0\r\n\r\n")
                except OSError:
                    owner.gone.set()                    # ไคลเอนต์ปิด socket ระหว่างสตรีม (การยกเลิก)

        self.httpd = _QuietServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


# ------------------------------------------------------------------ websearch MCP จำลอง
class FakeWebMCP:
    def __init__(self):
        self.requests, self.mode = [], "ok"
        owner = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _authed(self):
                return owner.mode != "deny" and self.headers.get("Authorization") == "Bearer " + C.TOKEN

            def do_GET(self):
                if self.path == "/health":
                    return self._json(200, {"status": "ok"})
                if self.path == "/mcp" and self._authed():
                    return self._json(200, {"status": "ok", "provider": "builtin"})
                return self._json(401, {"error": "missing_or_bad_token"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                msg = json.loads(self.rfile.read(n) or b"{}")
                owner.requests.append({"auth": self.headers.get("Authorization"), "origin": self.headers.get("Origin"),
                                       "host": self.headers.get("Host"), "msg": msg})
                if not self._authed():
                    return self._json(401, {"error": "missing_or_bad_token"})
                p = msg.get("params") or {}
                name, args = p.get("name"), p.get("arguments") or {}
                is_error = False
                if name == "web_search":
                    text = ws._fmt([("Open Charge Point Protocol",
                                     "https://en.wikipedia.org/wiki/Open_Charge_Point_Protocol", "OCPP"),
                                    ("OCPP 1.6", OCA_URL, "spec")], args.get("query"), ws.BUILTIN_NOTE)
                elif name == "fetch_url":
                    url = args.get("url", "")
                    if owner.mode == "tool_error":
                        text, is_error = "เครื่องมือ fetch_url ล้มเหลว: ValueError: x", True
                    elif "wikipedia.org/w/api.php" in url:
                        title = parse_qs(urlsplit(url).query).get("titles", [""])[0]
                        doc = {"query": {"pages": [{"title": unquote(title), "extract": WIKI_EXTRACT}]}}
                        text = "เนื้อหาจาก %s\n%s\n\n%s" % (url, ws.DATA_MARKER, json.dumps(doc, ensure_ascii=False))
                    elif url == OCA_URL:
                        text = "เนื้อหาจาก %s\n%s\n\n%s" % (url, ws.DATA_MARKER, PAGE_OCA)
                    else:
                        text = "ผิดพลาด: เซิร์ฟเวอร์ตอบ HTTP 404 สำหรับ %s" % url
                else:
                    return self._json(200, {"jsonrpc": "2.0", "id": msg.get("id"),
                                            "error": {"code": -32601, "message": "unknown"}})
                self._json(200, {"jsonrpc": "2.0", "id": msg.get("id"),
                                 "result": {"content": [{"type": "text", "text": text}], "isError": is_error}})

        self.httpd = _QuietServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


# ================================================================== ไคลเอนต์
class LLMClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = FakeRouter()

    @classmethod
    def tearDownClass(cls):
        cls.router.close()

    def setUp(self):
        self.router.mode = "ok"
        self.router.requests.clear()
        self.router.gone.clear()
        self.c = tr.LLMClient("4b", base="http://127.0.0.1:%d" % self.router.port)

    def msgs(self, step="synth"):
        s = {"plan": tr.PLAN_SYSTEM, "synth": tr.SYNTH_SYSTEM}[step]
        return [{"role": "system", "content": s}, {"role": "user", "content": "Question: x"}]

    def test_resolve_and_stream_with_schema(self):
        self.assertTrue(self.c.health())
        self.assertEqual(self.c.resolve(), ("Qwen3-4B-Instruct-2507-Q4_K_M", "loaded"))
        c27 = tr.LLMClient("27b", base="http://127.0.0.1:%d" % self.router.port)
        self.assertEqual(c27.resolve()[0], "Qwen3.8-27B-UD-Q4_K_M")          # ไม่หยิบ mmproj
        text, finish = self.c.chat(self.msgs("plan"), max_tokens=50, schema=tr._plan_schema(3, 3))
        self.assertEqual(finish, "stop")
        self.assertEqual(len(json.loads(text)["subquestions"]), 3)
        req = self.router.requests[-1]
        self.assertEqual(req["auth"], "Bearer " + C.TOKEN)                    # token ทดสอบ ไม่ใช่ของจริง
        self.assertEqual(req["host"], "127.0.0.1:%d" % self.router.port)
        self.assertIsNone(req["origin"])
        b = req["body"]
        self.assertTrue(b["stream"])
        self.assertEqual(b["model"], "Qwen3-4B-Instruct-2507-Q4_K_M")
        self.assertEqual(b["response_format"]["type"], "json_schema")
        self.assertEqual(b["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(b["max_tokens"], 50)

    def test_schema_rejected_falls_back(self):
        self.router.mode = "reject_schema"
        text, _f = self.c.chat(self.msgs("plan"), max_tokens=50, schema=tr._plan_schema(3, 3))
        self.assertIn("subquestions", text)
        self.assertEqual(["response_format" in r["body"] for r in self.router.requests], [True, False])
        self.assertFalse(self.c.schema_ok)

    def test_abort_closes_stream_quickly(self):
        self.router.mode = "slow"
        t0 = time.monotonic()
        with self.assertRaises(tr.Cancelled):
            self.c.chat(self.msgs(), max_tokens=500,
                        abort=lambda: tr.Cancelled() if time.monotonic() - t0 > 0.8 else None)
        self.assertLess(time.monotonic() - t0, 3.0)
        self.assertTrue(self.router.gone.wait(5), "router ไม่เห็นการปิด socket")

    def test_errors(self):
        self.router.mode = "deny"
        with self.assertRaises(tr.LLMError) as cm:
            self.c.chat(self.msgs(), max_tokens=10)
        self.assertTrue(cm.exception.fatal)
        self.assertEqual(cm.exception.status, 401)
        self.router.mode = "stall"
        self.c.idle = 1
        with self.assertRaises(tr.LLMError) as cm:
            self.c.chat(self.msgs(), max_tokens=10)
        self.assertEqual(cm.exception.kind, "timeout")
        dead = tr.LLMClient("4b", base="http://127.0.0.1:%d" % _free_port())
        self.assertFalse(dead.health())
        with self.assertRaises(tr.LLMError) as cm:
            dead.chat(self.msgs(), max_tokens=10)
        self.assertEqual(cm.exception.kind, "conn")
        self.assertTrue(cm.exception.fatal)


class WebClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = FakeWebMCP()

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        self.web.mode = "ok"
        self.web.requests.clear()
        self.c = tr.WebClient("http://127.0.0.1:%d/mcp" % self.web.port)

    def test_search_fetch_provider(self):
        self.assertTrue(self.c.health())
        self.assertEqual(self.c.provider(), "builtin")
        hits, builtin = self.c.search("OCPP", 5)
        self.assertTrue(builtin)
        self.assertEqual([h["url"] for h in hits], ["https://en.wikipedia.org/wiki/Open_Charge_Point_Protocol", OCA_URL])
        final, text = self.c.fetch(OCA_URL, 5000)
        self.assertEqual(final, OCA_URL)
        self.assertTrue(text.startswith("OCPP 1.6 overview."))
        self.assertNotIn("ข้อมูล\" ที่ดึงมาจากเว็บ", text)                     # ป้าย S07 ของ fetch_url ถูกแยกออก
        with self.assertRaises(tr.WebError) as cm:
            self.c.fetch("https://nope.example/", 5000)
        self.assertEqual(cm.exception.kind, "tool")
        for r in self.web.requests:
            self.assertEqual(r["auth"], "Bearer " + C.TOKEN)
            self.assertIsNone(r["origin"])                                   # ไคลเอนต์ในเครื่อง ไม่ใช่หน้าเว็บ
        args = [r["msg"]["params"]["arguments"] for r in self.web.requests]
        self.assertEqual(args[0], {"query": "OCPP", "max_results": 5})

    def test_errors(self):
        self.web.mode = "tool_error"
        with self.assertRaises(tr.WebError):
            self.c.fetch(OCA_URL, 100)
        self.web.mode = "deny"
        with self.assertRaises(tr.WebError) as cm:
            self.c.search("x", 3)
        self.assertEqual(cm.exception.kind, "conn")
        self.assertEqual(self.c.provider(), "")
        dead = tr.WebClient("http://127.0.0.1:%d/mcp" % _free_port())
        self.assertFalse(dead.health())
        with self.assertRaises(tr.WebError) as cm:
            dead.search("x", 3)
        self.assertEqual(cm.exception.kind, "conn")


# ================================================================== MCP จริงบนพอร์ตสำรอง
class SparePortResearchE2E(unittest.TestCase):
    """MCP ตัวจริง (server.py) บนพอร์ตสำรอง ด้วย token ทดสอบ + ข้อมูลใน temp; router/websearch เป็นของจำลอง
    — ปิดเฉพาะโปรเซสที่เปิดเองตอนจบ"""

    @classmethod
    def setUpClass(cls):
        cls.router, cls.web = FakeRouter(), FakeWebMCP()
        # พอร์ตสุ่มเสมอ (รอบ FIXER): 8892 ใช้ร่วมกับเทสต์ของเอเจนต์อื่นที่รันพร้อมกัน และ HTTPServer บน Windows ผูกพอร์ตซ้ำได้
        # เงียบๆ — เคยได้ 401 เพราะคำขอไปถึง MCP ทดสอบของอีกชุดที่ใช้ token ทดสอบคนละตัว
        cls.port = _free_port()
        env = C.clean_env()
        env["QWEN_RESEARCH_LLM_URL"] = "http://127.0.0.1:%d" % cls.router.port
        env["QWEN_RESEARCH_WEB_URL"] = "http://127.0.0.1:%d/mcp" % cls.web.port
        cls.log = os.path.join(C.TMP, "research-mcp-%d.log" % cls.port)
        out = open(cls.log, "wb")
        cls.proc = subprocess.Popen([sys.executable, os.path.join(C.MCP_LOCAL, "server.py"), str(cls.port)],
                                    cwd=C.MCP_LOCAL, env=env, stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out.close()
        deadline = time.time() + 30
        while time.time() < deadline and not C.port_in_use(cls.port):
            if cls.proc.poll() is not None:
                raise RuntimeError("MCP ทดสอบตายตอนเริ่ม ดู %s" % cls.log)
            time.sleep(0.2)
        cls.slug = C.PROJECT_OF_ALLOWED_ORIGIN

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.kill()                                  # เฉพาะโปรเซสที่เทสต์นี้เปิดเอง
            cls.proc.wait(10)
        cls.router.close()
        cls.web.close()

    def call(self, path, name, args, origin=C.ALLOWED_ORIGIN):
        status, _h, raw = C.rpc(self.port, path, "tools/call", {"name": name, "arguments": args}, origin=origin)
        self.assertEqual(status, 200, raw[:300])
        return C.tool_text(raw)

    def test_research_through_real_mcp(self):
        fast = "/fast/%s" % self.slug
        out = self.call(fast, "local_do", {"action": "research", "depth": "quick",
                                           "question": "How does the OCPP heartbeat work?"})
        m = re.search(r"id=(r[0-9a-f]+)", out)
        self.assertTrue(m, out)
        jid = m.group(1)
        self.assertIn("about 4-10 minutes", out)
        deadline, text = time.time() + 60, ""
        while time.time() < deadline:
            text = self.call(fast, "local_read", {"action": "research_status", "id": jid})
            if "is done" in text or "failed" in text:
                break
            time.sleep(0.3)
        self.assertIn("is done", text, text)
        link = re.search(r"\((/_qwen/out/(research-[^)]+\.md))\)", text)
        self.assertTrue(link, text)
        path = os.path.join(C.PROJECT_DATA, self.slug, "outputs", link.group(2))
        self.assertTrue(os.path.isfile(path))
        with open(path, encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("## Limitations", md)
        self.assertIn("(https://en.wikipedia.org/wiki/Open_Charge_Point_Protocol)", md)
        self.assertTrue(os.path.isfile(path[:-3] + ".docx"))
        with open(os.path.join(C.PROJECT_DATA, self.slug, "research", jid + ".json"), encoding="utf-8") as fh:
            st = json.load(fh)
        self.assertEqual(st["status"], "done")
        self.assertEqual(st["model_id"], "Qwen3-4B-Instruct-2507-Q4_K_M")
        # ทุกคำขอที่ MCP ส่งออกไปใช้ token ที่ตั้งให้ MCP (ของทดสอบ) และไม่มี Origin
        self.assertTrue(self.router.requests)
        self.assertTrue(all(r["auth"] == "Bearer " + C.TOKEN and r["origin"] is None for r in self.router.requests))
        self.assertTrue(all(r["auth"] == "Bearer " + C.TOKEN and r["origin"] is None for r in self.web.requests))
        # ผิวเต็ม + ด่าน Origin (หน้าของอีกโปรเจกต์อ่านงานของโปรเจกต์นี้ไม่ได้)
        self.assertIn("is done", self.call("/mcp/%s" % self.slug, "research_status", {"id": jid}))
        status, _h, _raw = C.rpc(self.port, fast, "tools/call",
                                 {"name": "local_read", "arguments": {"action": "research_status", "id": jid}},
                                 origin="http://127.0.0.1:8104")
        self.assertEqual(status, 403)
        status, _h, _raw = C.rpc(self.port, fast, "tools/call",
                                 {"name": "local_read", "arguments": {"action": "research_status"}}, token=None)
        self.assertEqual(status, 401)
        self.assertIn("ไม่พบงานค้นคว้า", self.call("/fast/proj-b", "local_read",
                                                     {"action": "research_status", "id": jid},
                                                     origin="http://127.0.0.1:8104"))


if __name__ == "__main__":
    unittest.main()
