# -*- coding: utf-8 -*-
"""เทสต์ HTTP ของ MCP ทั้งสองตัว (ช่องโหว่ V1 + สัญญา C2) บนอินสแตนซ์ทดสอบพอร์ต 8891/8892
(พอร์ตไม่ว่าง = ใช้พอร์ตว่างที่ระบบสุ่มให้แทน ไม่ข้ามทั้งไฟล์)

เปิดเซิร์ฟเวอร์จากโค้ดจริง (หรือจาก backup ถ้าตั้ง SEC_TEST_MCP_LOCAL/SEC_TEST_MCP_WEB)
ด้วย token ทดสอบ, audit.log และข้อมูลโปรเจกต์ในโฟลเดอร์ชั่วคราว แล้วปิดเฉพาะตัวที่เปิดเองตอนจบ
ไม่แตะพอร์ตจริง 8791/8792 และไม่อ่าน token จริง

ตรวจ
  * ไม่มี Authorization / token ผิด -> 401 (เดิม 200 = หน้าเว็บไหนก็สั่งเครื่องมือได้)
  * Origin ภายนอก -> 403 และไม่มี Access-Control-Allow-Origin (เดิมสะท้อนทุก Origin)
  * Host ของโดเมนอื่น (DNS rebinding) -> 403
  * preflight จากหน้าของเราได้ CORS ครบ, GET /health เปิดสาธารณะแต่ไม่บอกรายชื่อเครื่องมือ
  * ผ่านด่านแล้วยังโดนนโยบาย C5: เขียน config.json ไม่ได้, edit ต้องยืนยัน, token ข้ามโปรเจกต์ไม่ได้
  * ค่า token ถูกลบออกจากผลของเครื่องมือเสมอ
  * scheduler/gateway ส่ง token ตอนเรียกบริการในเครื่อง
"""
import json
import os
import socket
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

_SERVERS = {}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def setUpModule():
    # เดิม: พอร์ต 8891/8892 ไม่ว่าง (เช่นอินสแตนซ์ทดสอบของงานอื่นค้างอยู่) = SkipTest ทั้งไฟล์
    # เทสต์ C2 ทั้งชุดหายไปเงียบๆ แต่ผลรวมยังเป็น OK — ตอนนี้ถอยไปใช้พอร์ตว่างที่ระบบสุ่มให้แทน
    # (เซิร์ฟเวอร์ตรวจ Host กับพอร์ตของตัวเอง กฎ Origin ไม่ขึ้นกับพอร์ตของเซิร์ฟเวอร์ ผลจึงเหมือนกัน)
    for key, code, attr in (("local", C.MCP_LOCAL, "LOCAL_PORT"), ("web", C.MCP_WEB, "WEB_PORT")):
        port = getattr(C, attr)
        if C.port_in_use(port):
            port = _free_port()
            setattr(C, attr, port)
        srv = C.TestServer(code, port)
        srv.start()
        _SERVERS[key] = srv


def tearDownModule():
    for srv in _SERVERS.values():
        srv.stop()


class AuthAndCorsTests(unittest.TestCase):
    @property
    def PORTS(self):
        # อ่านตอนรัน ไม่ใช่ตอน import: setUpModule อาจเปลี่ยนไปใช้พอร์ตสุ่ม
        return (C.LOCAL_PORT, C.WEB_PORT)

    def test_servers_really_running(self):
        """กันกรณีเดิม: เซิร์ฟเวอร์ไม่ขึ้นแล้วเทสต์ทั้งไฟล์ถูกข้าม — ต้องมีทั้งสองตัวและตอบ /health"""
        self.assertEqual(sorted(_SERVERS), ["local", "web"])
        for port in self.PORTS:
            status, _h, _b = C.http("GET", port, "/health")
            self.assertEqual(status, 200, port)

    def test_post_without_token_is_401(self):
        for port in self.PORTS:
            status, _h, _b = C.rpc(port, "/mcp", "initialize", token=None)
            self.assertEqual(status, 401, port)
            status, _h, _b = C.rpc(port, "/mcp", "tools/list", token="0" * 64)
            self.assertEqual(status, 401, port)

    def test_get_status_without_token_is_401_but_health_is_public(self):
        for port in self.PORTS:
            status, _h, _b = C.http("GET", port, "/mcp")
            self.assertEqual(status, 401, port)
            status, _h, body = C.http("GET", port, "/health")
            self.assertEqual(status, 200, port)
            data = json.loads(body)
            self.assertEqual(data.get("status"), "ok")
            self.assertNotIn("tools", data, "health สาธารณะต้องไม่บอกรายชื่อเครื่องมือ")

    def test_get_sse_stream_is_405_on_both_servers(self):
        """รอบ FIXER ของ S1-S3 (e2e จริง): WebUI เปิดสตรีม SSE (GET + Accept: text/event-stream) ของ MCP ทุกตัว
        websearch (8791) เคยตอบ 200 JSON -> client นับว่าสตรีมหลุดแล้วต่อใหม่ราววินาทีละครั้ง (425 จาก 500 คำขอใน ~8 นาที)
        สเปก Streamable HTTP: ไม่มีสตรีมฝั่งเซิร์ฟเวอร์ = ตอบ 405 แล้ว client เลิกเปิดเอง (mcp-local แก้ไปก่อนแล้ว)"""
        # Origin ของหน้า hub (8100 ไม่ผูกโปรเจกต์) — /mcp เฉยๆ ของ mcp-local คือขอบเขต default ที่หน้าโปรเจกต์ 8103 เรียกไม่ได้
        hub = "http://127.0.0.1:8100"
        auth = {"Authorization": "Bearer " + C.TOKEN, "Origin": hub}
        for port in self.PORTS:
            status, hdrs, _raw = C.http("GET", port, "/mcp", headers=dict(auth, Accept="text/event-stream"))
            self.assertEqual(status, 405, port)
            self.assertIn("POST", hdrs.get("allow", ""), port)
            self.assertEqual(hdrs.get("access-control-allow-origin"), hub, port)
            # GET แบบอื่น (ดูสถานะ) ยังได้ JSON เหมือนเดิม
            status, _h, raw = C.http("GET", port, "/mcp", headers=dict(auth, Accept="application/json"))
            self.assertEqual(status, 200, port)
            self.assertEqual(json.loads(raw)["status"], "ok", port)
            # ด่าน token มาก่อนเสมอ และ /health ไม่เปลี่ยน
            status, _h, _raw = C.http("GET", port, "/mcp", headers={"Accept": "text/event-stream"})
            self.assertEqual(status, 401, port)
            status, _h, _raw = C.http("GET", port, "/health", headers={"Accept": "text/event-stream"})
            self.assertEqual(status, 200, port)

    def test_foreign_origin_rejected_even_with_token(self):
        for port in self.PORTS:
            status, headers, _b = C.rpc(port, "/mcp", "tools/list", origin=C.EVIL_ORIGIN)
            self.assertEqual(status, 403, port)
            self.assertNotIn("access-control-allow-origin", headers)

    def test_dns_rebinding_host_rejected(self):
        for port in self.PORTS:
            status, _h, _b = C.http("POST", port, "/mcp",
                                    {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                    {"Authorization": "Bearer " + C.TOKEN},
                                    host="attacker.example:%d" % port)
            self.assertEqual(status, 403, port)

    def test_preflight(self):
        for port in self.PORTS:
            status, headers, _b = C.http("OPTIONS", port, "/mcp", headers={
                "Origin": C.EVIL_ORIGIN, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type"})
            self.assertNotEqual(headers.get("access-control-allow-origin"), C.EVIL_ORIGIN)
            self.assertNotEqual(headers.get("access-control-allow-origin"), "*")
            status, headers, _b = C.http("OPTIONS", port, "/mcp", headers={
                "Origin": C.ALLOWED_ORIGIN, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type,mcp-session-id"})
            self.assertEqual(status, 204, port)
            self.assertEqual(headers.get("access-control-allow-origin"), C.ALLOWED_ORIGIN)
            allow = headers.get("access-control-allow-headers", "").lower()
            for h in ("authorization", "content-type", "mcp-session-id", "mcp-protocol-version",
                      "last-event-id"):
                self.assertIn(h, allow)
            self.assertIn("mcp-session-id", headers.get("access-control-expose-headers", "").lower())
            self.assertNotEqual(headers.get("access-control-allow-credentials", "").lower(), "true")

    def test_allowed_origin_with_token_works(self):
        # MCP เครื่องนี้ผูก Origin ของหน้าโปรเจกต์กับ slug ใน URL (8103 = sec-http ใน projects.json จำลอง)
        for port, path in ((C.LOCAL_PORT, "/mcp/" + C.PROJECT_OF_ALLOWED_ORIGIN), (C.WEB_PORT, "/mcp")):
            status, headers, body = C.rpc(port, path, "initialize",
                                          {"protocolVersion": "2025-06-18", "capabilities": {},
                                           "clientInfo": {"name": "t", "version": "1"}},
                                          origin=C.ALLOWED_ORIGIN)
            self.assertEqual(status, 200, port)
            self.assertEqual(headers.get("access-control-allow-origin"), C.ALLOWED_ORIGIN)
            self.assertIn("result", json.loads(body))
        status, _h, body = C.rpc(C.LOCAL_PORT, "/fast/sec-http", "tools/list")
        names = [t["name"] for t in json.loads(body)["result"]["tools"]]
        self.assertEqual(sorted(names), ["local_confirm", "local_do", "local_read"])
        # confirm_token ไม่อยู่ใน schema ของเครื่องมือเดิมอีกแล้ว (ขั้นยืนยันมีทางเดียวคือ local_confirm)
        props = {t["name"]: t["inputSchema"].get("properties", {})
                 for t in json.loads(body)["result"]["tools"]}
        self.assertNotIn("confirm_token", props["local_do"])
        self.assertIn("confirm_token", props["local_confirm"])
        # รอบ review-fetch (S2): review ยังมีใน schema แต่ไม่บังคับ — กล่องอนุญาตดึง review จากเซิร์ฟเวอร์เอง (S1)
        self.assertIn("review", props["local_confirm"])
        confirm = next(t for t in json.loads(body)["result"]["tools"] if t["name"] == "local_confirm")
        self.assertEqual(confirm["inputSchema"]["required"], ["confirm_token"])


class OriginProjectBindingTests(unittest.TestCase):
    """S04 ระดับ HTTP (audit F13): หน้าโปรเจกต์ A ห้ามเรียก URL ของโปรเจกต์ B ถึงจะมี token เดียวกัน"""

    def _status(self, path, origin):
        status, _h, _b = C.rpc(C.LOCAL_PORT, path, "tools/list", origin=origin)
        return status

    def test_origin_must_match_project_slug(self):
        self.assertEqual(self._status("/fast/sec-http", C.ALLOWED_ORIGIN), 200)
        self.assertEqual(self._status("/fast/proj-b", C.ALLOWED_ORIGIN), 403)
        self.assertEqual(self._status("/mcp", C.ALLOWED_ORIGIN), 403)       # default ก็เป็นโปรเจกต์อื่น
        self.assertEqual(self._status("/fast/proj-b", "http://localhost:8104"), 200)

    def test_unknown_project_port_rejected(self):
        self.assertEqual(self._status("/fast/sec-http", "http://127.0.0.1:8150"), 403)

    def test_non_project_pages_and_local_clients_unaffected(self):
        self.assertEqual(self._status("/fast/proj-b", "http://127.0.0.1:8100"), 200)
        self.assertEqual(self._status("/fast/proj-b", None), 200)          # scheduler/เทสต์ ไม่มี Origin

    def test_preflight_not_blocked_by_binding(self):
        status, headers, _b = C.http("OPTIONS", C.LOCAL_PORT, "/fast/proj-b", headers={
            "Origin": C.ALLOWED_ORIGIN, "Access-Control-Request-Method": "POST"})
        self.assertEqual(status, 204)


class PolicyThroughHttpTests(unittest.TestCase):
    """ผ่านด่าน C2 แล้ว นโยบาย C5 ต้องยังทำงานเหมือนเรียกฟังก์ชันตรงๆ"""

    def _call(self, path, name, args):
        status, _h, body = C.rpc(C.LOCAL_PORT, path, "tools/call",
                                 {"name": name, "arguments": args})
        self.assertEqual(status, 200)
        return C.tool_text(body)

    def test_cannot_create_guard_config(self):
        target = r"C:\LLM\mcp-local\config.json"
        if os.path.exists(target):
            self.skipTest("มี config.json อยู่แล้ว")
        # เงื่อนไขปลอดภัยก่อน: เซิร์ฟเวอร์ที่ไม่ตรวจ token คือโค้ดเก่า ห้ามยิงคำสั่งเขียนไปหามัน
        status, _h, _b = C.rpc(C.LOCAL_PORT, "/mcp", "tools/list", token=None)
        self.assertEqual(status, 401)
        out = self._call("/mcp/sec-http", "write_file", {"path": target, "content": "{}"})
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:200])
        self.assertFalse(os.path.exists(target))

    def test_fast_edit_requires_confirmation_and_is_project_bound(self):
        status, _h, _b = C.rpc(C.LOCAL_PORT, "/mcp", "tools/list", token=None)
        self.assertEqual(status, 401)
        d = C.new_dir("httpedit")
        p = os.path.join(d, "a.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("one")
        out = self._call("/fast/proj-a", "local_do",
                         {"action": "edit", "path": p, "old": "one", "new": "two"})
        tok = C.token_from_hint(out)
        self.assertTrue(tok, out[:200])
        self.assertIn("local_confirm", out)
        with open(p, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "one")
        # ส่ง review ถูกต้องด้วย — ที่ต้องกันไว้คือขอบเขตโปรเจกต์ ไม่ใช่เพราะลืม review
        self._call("/fast/proj-b", "local_confirm", C.confirm_args(out))
        with open(p, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "one", "token ของโปรเจกต์หนึ่งต้องใช้กับอีกโปรเจกต์ไม่ได้")
        out = self._call("/fast/proj-a", "local_confirm", C.confirm_args(out))
        with open(p, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "two", out[:200])


class ConfirmChannelTests(unittest.TestCase):
    """audit (major): token อยู่ในผลที่โมเดลอ่าน จึงยืนยันเองได้ด้วยการเรียกเครื่องมือเดิมซ้ำ
    ตอนนี้ขั้นที่สองต้องเป็นเครื่องมือแยก local_confirm ที่ WebUI ถามผู้ใช้ใหม่ (สิทธิ์เดิมไม่ครอบ)"""

    def _call(self, path, name, args):
        status, _h, body = C.rpc(C.LOCAL_PORT, path, "tools/call",
                                 {"name": name, "arguments": args})
        self.assertEqual(status, 200)
        return C.tool_text(body)

    def _edit_file(self):
        d = C.new_dir("chan")
        p = os.path.join(d, "a.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("one")
        return p

    def _read(self, p):
        with open(p, encoding="utf-8") as fh:
            return fh.read()

    def test_resending_token_to_original_tool_does_nothing(self):
        p = self._edit_file()
        args = {"action": "edit", "path": p, "old": "one", "new": "two"}
        hint = self._call("/fast/chan", "local_do", args)
        tok = C.token_from_hint(hint)
        self.assertTrue(tok)
        for key in ("confirm_token", "token"):
            out = self._call("/fast/chan", "local_do", dict(args, **{key: tok}))
            self.assertEqual(self._read(p), "one", "ทางเก่า (%s) ต้องไม่ลงมือ: %s" % (key, out[:120]))
            self.assertIn("local_confirm", out)
        # token เดิมยังไม่ถูกเผา — ผู้ใช้อนุมัติผ่าน local_confirm (พร้อม review ตรงตัว) ได้
        self._call("/fast/chan", "local_confirm", C.confirm_args(hint))
        self.assertEqual(self._read(p), "two")

    def test_full_surface_exec_self_confirm_blocked(self):
        # ตรงกับหลักฐาน G1->G2 ของ audit: ขอ token แล้วส่งกลับไปที่ exec_shell_command ทันที
        d = C.new_dir("chanexec")
        marker = os.path.join(d, "ran.txt")
        cmd = 'python -c "open(r\'%s\',\'w\').write(\'x\')"' % marker
        tok = C.token_from_hint(self._call("/mcp/chan", "exec_shell_command",
                                           {"command": cmd, "cwd": d}))
        self.assertTrue(tok)
        self._call("/mcp/chan", "exec_shell_command", {"command": cmd, "cwd": d, "confirm_token": tok})
        self.assertFalse(os.path.exists(marker), "ส่ง token ให้เครื่องมือเดิมต้องไม่รันคำสั่ง")

    def test_replay_is_exact_single_use_and_surface_bound(self):
        p = self._edit_file()
        hint = self._call("/fast/chan2", "local_do",
                          {"action": "edit", "path": p, "old": "one", "new": "two"})
        args = C.confirm_args(hint)
        self.assertTrue(args["confirm_token"] and args["review"], hint[:300])
        # local_confirm ไม่รับอาร์กิวเมนต์ของการกระทำ — ส่ง new=EVIL มาก็ไม่มีผล (เล่นซ้ำของที่บันทึกไว้)
        out = self._call("/mcp/chan2", "local_confirm", args)
        self.assertEqual(self._read(p), "one", "token จากผิว /fast ต้องยืนยันบนผิว /mcp ไม่ได้: " + out[:80])
        self._call("/fast/chan2", "local_confirm", dict(args, new="EVIL"))
        self.assertEqual(self._read(p), "two")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("one")
        out = self._call("/fast/chan2", "local_confirm", args)
        self.assertEqual(self._read(p), "one", "ใช้ซ้ำไม่ได้: " + out[:80])

    def test_unknown_token_rejected(self):
        out = self._call("/fast/chan3", "local_confirm", {"confirm_token": "deadbeef", "review": "x"})
        self.assertIn("ใช้ไม่ได้", out)

    def test_token_value_scrubbed_from_tool_output(self):
        d = C.new_dir("leak")
        p = os.path.join(d, "notes.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("copied by accident: %s\n" % C.TOKEN)
        out = self._call("/mcp/sec-http", "read_file", {"path": p})
        self.assertIn("copied by accident", out)
        self.assertNotIn(C.TOKEN, out)

    def test_websearch_fetch_url_blocks_loopback_over_http(self):
        srv = C.LocalHTTPServer()
        try:
            status, _h, body = C.rpc(C.WEB_PORT, "/mcp", "tools/call",
                                     {"name": "fetch_url",
                                      "arguments": {"url": "http://127.0.0.1:%d/" % srv.port}})
            self.assertEqual(status, 200)
            self.assertNotIn(C.LocalHTTPServer.MARKER, C.tool_text(body))
        finally:
            srv.close()


class InternalClientsSendTokenTests(unittest.TestCase):
    """scheduler (heartbeat) และ gateway (ยิง llama-server) ต้องแนบ token"""

    def test_scheduler_heartbeat_authenticates(self):
        sched = C.import_local("scheduler")
        saved = sched.CHECKS
        sched.CHECKS = (("mcp_local", "MCP local", "http://127.0.0.1:%d/mcp" % C.LOCAL_PORT,
                         sched._v_status_ok),
                        ("mcp_websearch", "MCP websearch",
                         "http://127.0.0.1:%d/mcp" % C.WEB_PORT, sched._v_status_ok))
        try:
            status, message, extra, _report = sched.job_heartbeat()
        finally:
            sched.CHECKS = saved
        self.assertEqual(status, "ok", message)
        self.assertEqual(extra["checks"]["mcp_local"]["status"], "ok")

    def test_gateway_sends_token_upstream(self):
        gw = C.import_local("gateway")
        fake = C.LocalHTTPServer()
        saved = gw.UPSTREAM
        gw.UPSTREAM = "http://127.0.0.1:%d" % fake.port
        try:
            gw._http_json(gw.UPSTREAM + "/v1/models", None, 5.0)
        finally:
            gw.UPSTREAM = saved
            fake.close()
        self.assertTrue(fake.seen_headers)
        self.assertEqual(fake.seen_headers[-1].get("authorization"), "Bearer " + C.TOKEN)

    def test_gateway_rejects_browser_origin(self):
        import subprocess
        import time
        gwdir = C.MCP_LOCAL
        env = C.clean_env()
        env["GATEWAY_API_KEY"] = "test-gateway-key-" + C.TOKEN[:16]   # คีย์ทดสอบ ไม่ใช่ของจริง
        port = 0
        proc = subprocess.Popen([sys.executable, os.path.join(gwdir, "gateway.py"), "0"],
                                cwd=gwdir, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            deadline = time.time() + 20
            while time.time() < deadline and not port:
                line = proc.stdout.readline().decode("utf-8", "replace")
                if not line:
                    break
                if "http://127.0.0.1:" in line:
                    port = int(line.rsplit(":", 1)[1].strip().split()[0])
            self.assertTrue(port, "gateway ทดสอบไม่ขึ้น")
            status, _h, _b = C.http("POST", port, "/v1/prompt", {"prompt": "hi"},
                                    {"Origin": C.EVIL_ORIGIN, "Content-Type": "text/plain"})
            self.assertEqual(status, 403)
            status, _h, _b = C.http("GET", port, "/v1/sessions")
            self.assertEqual(status, 401)
        finally:
            proc.kill()                     # เฉพาะ gateway ทดสอบที่เปิดเอง
            proc.wait(10)
            proc.stdout.close()


if __name__ == "__main__":
    unittest.main()
