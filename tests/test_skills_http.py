# -*- coding: utf-8 -*-
"""เทสต์ Skills (B4) ผ่าน HTTP จริง: เปิด mcp-local จากโค้ดจริงบนพอร์ตสำรอง (8892 หรือพอร์ตว่างที่ระบบสุ่ม)
ด้วย token ทดสอบ แล้วปิดเฉพาะตัวที่เปิดเองตอนจบ — ไม่แตะ 8792 ตัวจริง ไม่อ่าน token จริง

ตรวจว่า prompts/* อยู่หลังด่านเดิมทั้งหมด (สัญญา C2 + S04 ระดับ HTTP)
  * ไม่มี/ผิด Bearer -> 401, Origin ภายนอก -> 403
  * หน้าโปรเจกต์ A (Origin 8103 = sec-http) ขอ prompts ของ /fast/proj-b -> 403
  * ผ่านด่าน: initialize ประกาศ prompts, list ได้ skill ตั้งต้นครบ, get คืนข้อความ, completion เห็นไฟล์ของตัวเอง
  * GET สถานะ (มี Bearer) บอกจำนวน skill และตัวที่โหลดไม่ได้
"""
import json
import os
import socket
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

SKILLS_DIR = r"C:\LLM\skills"
STARTERS = {"ocpp-log-analysis", "charger-incident-report", "python-data-analysis", "long-doc-summary",
            "deep-research", "code-review", "formal-email"}
_SRV = {}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def setUpModule():
    port = C.LOCAL_PORT if not C.port_in_use(C.LOCAL_PORT) else _free_port()
    settings = os.path.join(C.new_dir("skills-http-hub"), "settings.json")
    with open(settings, "w", encoding="utf-8") as fh:
        json.dump({"lang": "th"}, fh)
    att = os.path.join(C.PROJECT_DATA, C.PROJECT_OF_ALLOWED_ORIGIN, "attachments")
    os.makedirs(att, exist_ok=True)
    with open(os.path.join(att, "OCPP-http.log"), "w", encoding="utf-8") as fh:
        fh.write("x")
    env = C.clean_env()
    env.update({"QWEN_SKILLS_DIR": SKILLS_DIR, "QWEN_HUB_SETTINGS": settings})
    log = os.path.join(C.TMP, "skills-server-%d.log" % port)
    out = open(log, "wb")
    proc = subprocess.Popen([sys.executable, os.path.join(C.MCP_LOCAL, "server.py"), str(port)],
                            cwd=C.MCP_LOCAL, env=env, stdout=out, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out.close()
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("เซิร์ฟเวอร์ทดสอบตายตอนเริ่ม ดู %s" % log)
        if C.port_in_use(port):
            break
        time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("เซิร์ฟเวอร์ทดสอบไม่ขึ้น")
    _SRV.update(proc=proc, port=port)


def tearDownModule():
    proc = _SRV.get("proc")
    if proc is not None and proc.poll() is None:
        proc.kill()                          # เฉพาะโปรเซสที่เทสต์นี้เปิดเอง
        proc.wait(10)


def call(method, params=None, path=None, token=C.TOKEN, origin=None):
    path = path or "/fast/%s" % C.PROJECT_OF_ALLOWED_ORIGIN
    return C.rpc(_SRV["port"], path, method, params, token=token, origin=origin)


class SkillsHttpTests(unittest.TestCase):
    def test_needs_bearer(self):
        for tok in (None, "0" * 64):
            status, _h, _b = call("prompts/list", token=tok)
            self.assertEqual(status, 401)
            status, _h, _b = call("prompts/get", {"name": "code-review"}, token=tok)
            self.assertEqual(status, 401)

    def test_foreign_origin_refused(self):
        status, headers, _b = call("prompts/list", origin=C.EVIL_ORIGIN)
        self.assertEqual(status, 403)
        self.assertNotIn("access-control-allow-origin", headers)

    def test_other_projects_page_cannot_use_this_scope(self):
        # Origin 8103 ผูกกับ sec-http — ขอ completion ของ proj-b (เห็นชื่อไฟล์ของอีกโปรเจกต์) ต้องไม่ได้
        status, _h, _b = call("completion/complete",
                              {"ref": {"type": "ref/prompt", "name": "long-doc-summary"},
                               "argument": {"name": "file", "value": ""}},
                              path="/fast/proj-b", origin=C.ALLOWED_ORIGIN)
        self.assertEqual(status, 403)

    def test_initialize_list_get_complete(self):
        for path in ("/fast/%s" % C.PROJECT_OF_ALLOWED_ORIGIN, "/mcp/%s" % C.PROJECT_OF_ALLOWED_ORIGIN):
            status, _h, body = call("initialize", path=path, origin=C.ALLOWED_ORIGIN)
            self.assertEqual(status, 200)
            caps = json.loads(body)["result"]["capabilities"]
            self.assertIn("prompts", caps)
            self.assertIn("completions", caps)
            status, _h, body = call("prompts/list", path=path, origin=C.ALLOWED_ORIGIN)
            self.assertEqual(status, 200)
            names = {p["name"] for p in json.loads(body)["result"]["prompts"]}
            self.assertTrue(STARTERS <= names, names)
        status, _h, body = call("prompts/get", {"name": "formal-email",
                                                "arguments": {"to": "ผู้จัดการ", "purpose": "นัดตรวจตู้"}},
                                origin=C.ALLOWED_ORIGIN)
        self.assertEqual(status, 200)
        text = json.loads(body)["result"]["messages"][0]["content"]["text"]
        self.assertIn("ผู้จัดการ", text)
        self.assertIn("นัดตรวจตู้", text)
        status, _h, body = call("prompts/get", {"name": "formal-email", "arguments": {}}, origin=C.ALLOWED_ORIGIN)
        self.assertEqual(json.loads(body)["error"]["code"], -32602)
        status, _h, body = call("completion/complete",
                                {"ref": {"type": "ref/prompt", "name": "long-doc-summary"},
                                 "argument": {"name": "file", "value": "ocpp"}}, origin=C.ALLOWED_ORIGIN)
        # โฟลเดอร์ข้อมูลชั่วคราวใช้ร่วมกับเทสต์ชุดอื่นในโปรเซสเดียวกัน — ตรวจว่ามีไฟล์ของเรา และทุกชื่อตรงกับที่พิมพ์
        got = json.loads(body)["result"]["completion"]["values"]
        self.assertIn("OCPP-http.log", got)
        self.assertTrue(all("ocpp" in v.casefold() for v in got), got)

    def test_pasted_attachment_path_is_not_doubled_on_either_surface(self):
        # finding batch 2a: "attachments/x" หรือ path เต็มในช่อง file เคยได้ path="attachments/attachments/x"
        att = os.path.join(C.PROJECT_DATA, C.PROJECT_OF_ALLOWED_ORIGIN, "attachments")
        for path in ("/fast/%s" % C.PROJECT_OF_ALLOWED_ORIGIN, "/mcp/%s" % C.PROJECT_OF_ALLOWED_ORIGIN):
            for value in ("attachments/OCPP-http.log", os.path.join(att, "OCPP-http.log")):
                status, _h, body = call("prompts/get", {"name": "ocpp-log-analysis", "arguments": {"file": value}},
                                        path=path, origin=C.ALLOWED_ORIGIN)
                self.assertEqual(status, 200)
                text = json.loads(body)["result"]["messages"][0]["content"]["text"]
                self.assertNotIn("attachments/attachments", text, (path, value))
                self.assertNotIn("attachments\\attachments", text, (path, value))
                if path.startswith("/fast/"):
                    self.assertIn('path="attachments/OCPP-http.log"', text)
                else:
                    self.assertIn(os.path.join(att, "OCPP-http.log"), text)
        status, _h, body = call("prompts/get", {"name": "ocpp-log-analysis", "arguments": {"file": r"D:\x.log"}},
                                origin=C.ALLOWED_ORIGIN)
        self.assertEqual(json.loads(body)["error"]["code"], -32602)

    def test_status_reports_skills(self):
        status, _h, body = C.http("GET", _SRV["port"], "/fast/%s" % C.PROJECT_OF_ALLOWED_ORIGIN,
                                  headers={"Authorization": "Bearer " + C.TOKEN})
        self.assertEqual(status, 200)
        sk = json.loads(body)["skills"]
        self.assertGreaterEqual(sk["count"], len(STARTERS))
        self.assertEqual(sk["failed"], {})


if __name__ == "__main__":
    unittest.main()
