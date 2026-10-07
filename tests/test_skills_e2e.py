# -*- coding: utf-8 -*-
"""E2E ของ Skills (B4) ในหน้าแชตจริง — ปิดเป็นค่าเริ่มต้น เปิดด้วย set QWEN_UI_E2E=1

ไม่แตะบริการจริงและไม่ส่งข้อความแชต
  * MCP สำรอง (โค้ดปัจจุบัน) บน 8892/8891 ด้วย token ชั่วคราว + projects.json/audit/ข้อมูลโปรเจกต์ชั่วคราว
  * hub สำเนา (import hub.py เป็นโมดูล) เสิร์ฟ project1 บนพอร์ตว่างตัวแรกใน 8171-8177 — เปลี่ยนเฉพาะ MCP
    "เครื่องนี้" ให้ชี้ MCP สำรอง (header เป็น token ชั่วคราว) ส่วนการคุยกับ router ใช้ของ hub ตามปกติ
    "ค้นอินเทอร์เน็ต" ชี้พอร์ตที่ไม่มีใครฟัง (ไม่ยิง 8791 จริงด้วย token ปลอม) และเลือกโมเดล 4B ไว้ (ไม่โหลดอะไร)
  * Edge headless โปรไฟล์ชั่วคราว (ครั้งละหนึ่งตัว): การเขียน /api/settings ของ hub จริงถูกตัดทิ้ง
ขั้นตอนที่ตรวจ: พิมพ์ "/" -> มีคำสั่ง prompt -> Enter -> รายการ skill ครบ 7 ตัว (ชื่อไทย) -> คลิก "สรุปเอกสารยาว"
-> ฟอร์มอาร์กิวเมนต์ 3 ช่อง -> พิมพ์ "ocpp" ในช่อง file ได้คำแนะนำชื่อไฟล์ของโปรเจกต์ -> Enter เลือก -> กรอก focus
-> "Use Prompt" -> ชิป MCP Prompt ในช่องพิมพ์มีข้อความแม่แบบที่แทนค่าแล้ว และ audit มี prompt_get (เก็บแค่ความยาว)
ภาพหน้าจอเก็บที่ C:\\LLM\\projects\\tools\\shots\\skills-e2e-*.png
"""
import base64
import importlib.util
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock

E2E = os.environ.get("QWEN_UI_E2E") == "1"
TOOLS = r"C:\LLM\projects\tools"
HUB = r"C:\LLM\projects\hub.py"
MCP_DIR = r"C:\LLM\mcp-local"
SHOTS = os.path.join(TOOLS, "shots")
TITLES_TH = ["วิเคราะห์ log OCPP", "รายงานเหตุขัดข้องตู้ชาร์จ", "วิเคราะห์ข้อมูลด้วย Python", "สรุปเอกสารยาว",
             "ค้นคว้าเชิงลึก", "รีวิวโค้ด", "เขียนอีเมลทางการ"]


def busy(p):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", p)) == 0


@unittest.skipUnless(E2E, "E2E ปิดอยู่ (set QWEN_UI_E2E=1)")
class SkillsPickerE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, TOOLS)
        # hub.py import hub_i18n_parts จาก sys.path — ต้องเป็นตัวจริงใน C:\LLM\projects เสมอ
        sys.path.insert(0, os.path.dirname(HUB))
        sys.modules.pop("hub_i18n_parts", None)
        import shot  # noqa: E402
        cls.shot = shot
        cls.hubport = next((p for p in range(8171, 8178) if not busy(p)), None)
        cls.mcpport = next((p for p in (8892, 8891) if not busy(p)), None)
        if not cls.hubport or not cls.mcpport:
            raise unittest.SkipTest("พอร์ตสำรองไม่ว่าง")
        edge = next((p for p in shot.EDGE_CANDIDATES if os.path.isfile(p)), None)
        if not edge:
            raise unittest.SkipTest("ไม่มี Edge")
        tmp = tempfile.mkdtemp(prefix="skills-e2e-")
        cls.tmp = tmp
        cls.token = secrets.token_hex(32)
        tokfile = os.path.join(tmp, "token", "local-services.token")
        os.makedirs(os.path.dirname(tokfile))
        with open(tokfile, "w", encoding="ascii", newline="\n") as fh:
            fh.write(cls.token + "\n")
        projects_json = os.path.join(tmp, "projects.json")
        with open(projects_json, "w", encoding="utf-8") as fh:
            json.dump([{"slug": "project1", "name": "project1", "port": cls.hubport}], fh)
        att = os.path.join(tmp, "data", "project1", "attachments")
        os.makedirs(att)
        for n in ("OCPP-CP012-2026-09-30.log", "OCPP-2.0.1-spec.pdf", "tariff-2026.xlsx"):
            open(os.path.join(att, n), "w").close()
        settings = os.path.join(tmp, "settings.json")
        with open(settings, "w", encoding="utf-8") as fh:
            json.dump({"lang": "th"}, fh)
        cls.audit = os.path.join(tmp, "audit.log")
        keep = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE",
                "USERNAME", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "HOMEDRIVE", "HOMEPATH")
        env = {k: v for k, v in os.environ.items() if k.upper() in keep}
        env.update({"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", "LLM_LOCAL_TOKEN_FILE": tokfile,
                    "QWEN_MCP_PROJECTS_JSON": projects_json, "QWEN_MCP_AUDIT_PATH": cls.audit,
                    "QWEN_MCP_PROJECT_DATA": os.path.join(tmp, "data"), "QWEN_SKILLS_DIR": r"C:\LLM\skills",
                    "QWEN_HUB_SETTINGS": settings, "QWEN_WEB_AUDIT_PATH": os.path.join(tmp, "audit-web.log")})
        cls.mcp_log = open(os.path.join(tmp, "mcp.log"), "wb")
        cls.mcp = subprocess.Popen([sys.executable, os.path.join(MCP_DIR, "server.py"), str(cls.mcpport)],
                                   cwd=MCP_DIR, env=env, stdout=cls.mcp_log, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(150):
            if busy(cls.mcpport):
                break
            time.sleep(0.2)
        spec = importlib.util.spec_from_file_location("hub_skills_e2e", HUB)
        hub = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "argv", ["hub.py"]), \
                mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                             "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
            spec.loader.exec_module(hub)
        hub.MCP_LOCAL_PORT = cls.mcpport
        hub.MCP_WEB_PORT = shot.free_port()
        orig = hub.mcp_servers
        token = cls.token

        def mcp_servers_tmp(project, with_auth=True):
            rows = orig(project, with_auth=False)
            if with_auth:
                for r in rows:
                    r["headers"] = json.dumps({"Authorization": "Bearer " + token})
            return rows
        hub.mcp_servers = mcp_servers_tmp
        port = cls.hubport

        def projects():
            return [dict(p, port=port, model="Qwen3-4B-Instruct-2507-Q4_K_M")
                    for p in hub.load_projects() if p["slug"] == "project1"]
        if not projects():
            cls._stop_mcp()
            raise unittest.SkipTest("ไม่มีโปรเจกต์ project1")
        cls.srv = hub.ThreadingHTTPServer(("127.0.0.1", port), hub.make_proxy_handler("project1", projects))
        cls.srv.daemon_threads = True
        cls.srv.handle_error = lambda *a: None
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        dbg = shot.free_port()
        cls.profile = tempfile.mkdtemp(prefix="qwen-shot-")
        cls.proc = subprocess.Popen([edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                                     "--no-default-browser-check", "--disable-extensions", "--mute-audio",
                                     "--remote-debugging-port=%d" % dbg, "--user-data-dir=%s" % cls.profile,
                                     "--window-size=1440,900", "about:blank"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(100):
            try:
                tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % dbg, timeout=2).read())
                page = next((t for t in tabs if t.get("type") == "page"), None)
                if page:
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except OSError:
                pass
            time.sleep(0.15)
        cls.ws = shot.WS(ws_url)
        cls.ws.call("Page.enable")
        cls.ws.call("Runtime.enable")
        cls.ws.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1,
                                                            "mobile": False})
        cls.blocked = []
        # การทดสอบห้ามเปลี่ยนค่าตั้งจริงของผู้ใช้บน hub: GET ผ่าน (shell รอค่านี้ก่อนโหลด iframe) อย่างอื่นตัดทิ้ง
        cls.ws.call("Fetch.enable", {"patterns": [{"urlPattern": "http://127.0.0.1:8100/api/settings*"}]})
        cls._orig_drain = cls.ws.drain
        cls.ws.drain = cls.drain
        shot.navigate(cls.ws, "http://127.0.0.1:%d/?lang=th" % port, settle=4.0)
        for _ in range(60):
            ready = cls.shell("(()=>{const f=document.getElementById('frame');try{const w=f.contentWindow;"
                              "return typeof w.qwenEnhance==='object'&&!!w.document.querySelector('textarea')}"
                              "catch(e){return false}})()")
            if ready:
                break
            cls.ws.drain(1.0)
        cls.ws.drain(3.0)                  # ให้ WebUI ต่อ MCP เสร็จ

    @classmethod
    def _stop_mcp(cls):
        if cls.mcp.poll() is None:
            cls.mcp.kill()                 # เฉพาะโปรเซสที่เทสต์นี้เปิดเอง
            cls.mcp.wait(10)
        cls.mcp_log.close()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.shot.close_edge(cls.proc, cls.profile)
        finally:
            cls.srv.shutdown()
            cls._stop_mcp()

    # ---------------------------------------------------------------- ตัวช่วย CDP
    @classmethod
    def pump(cls):
        rest = []
        for ev in cls.ws.events:
            if ev.get("method") == "Fetch.requestPaused":
                p = ev["params"]
                if p["request"]["method"] in ("GET", "HEAD", "OPTIONS"):
                    cls.ws.call("Fetch.continueRequest", {"requestId": p["requestId"]})
                else:
                    cls.blocked.append(p["request"]["method"])
                    cls.ws.call("Fetch.failRequest", {"requestId": p["requestId"], "errorReason": "BlockedByClient"})
            else:
                rest.append(ev)
        cls.ws.events[:] = rest

    @classmethod
    def drain(cls, seconds):
        end = time.time() + seconds
        while True:
            cls._orig_drain(min(0.3, max(0.0, end - time.time())))
            cls.pump()
            if time.time() >= end:
                break

    @classmethod
    def shell(cls, js):
        cls.pump()
        return cls.shot.evaluate(cls.ws, js)

    @classmethod
    def frame(cls, js):
        cls.pump()
        return cls.shot.evaluate(cls.ws, "(async()=>{const w=document.getElementById('frame').contentWindow;"
                                         "return await w.eval(%s)})()" % json.dumps(js))

    def key(self, k, code, vk):
        for t in ("rawKeyDown", "keyUp"):
            self.ws.call("Input.dispatchKeyEvent", {"type": t, "key": k, "code": code, "windowsVirtualKeyCode": vk})

    def click_frame(self, find_js):
        xy = self.shell("(()=>{const f=document.getElementById('frame'),w=f.contentWindow;const e=w.eval(%s);"
                        "if(!e)return null;e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect(),"
                        "o=f.getBoundingClientRect();return [o.left+r.left+r.width/2,o.top+r.top+r.height/2]})()"
                        % json.dumps(find_js))
        self.assertTrue(xy, find_js)
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.ws.call("Input.dispatchMouseEvent", {"type": t, "x": xy[0], "y": xy[1], "button": "left",
                                                      "clickCount": 1})

    def snap(self, name):
        os.makedirs(SHOTS, exist_ok=True)
        data = self.ws.call("Page.captureScreenshot", {"format": "png"})["data"]
        with open(os.path.join(SHOTS, name), "wb") as fh:
            fh.write(base64.b64decode(data))

    # ---------------------------------------------------------------- เทสต์ (ขั้นตอนเดียวต่อเนื่อง)
    def test_picker_lists_skills_and_inserts_rendered_template(self):
        self.frame("qwenEnhance.focusComposer(); 1")
        self.ws.drain(0.5)
        self.ws.call("Input.insertText", {"text": "/"})
        self.ws.drain(1.5)
        self.assertIn("/prompt", self.frame("document.body.innerText"))
        self.key("Enter", "Enter", 13)
        self.ws.drain(3.0)
        self.snap("skills-e2e-1-prompts.png")
        seen = self.frame("(ts=>{const t=document.body.innerText;return ts.filter(x=>t.includes(x))})(%s)"
                          % json.dumps(TITLES_TH, ensure_ascii=False))
        self.assertEqual(seen, TITLES_TH)
        self.click_frame("(txt=>{const all=[...document.querySelectorAll('button,[role=option],[data-index],div')]"
                         ".filter(e=>e.offsetParent&&(e.innerText||'').includes(txt));all.sort((a,b)=>"
                         "a.innerText.length-b.innerText.length);return all.find(e=>e.matches('button,[role=option],"
                         "[data-index]'))||all[0]||null})('สรุปเอกสารยาว')")
        self.ws.drain(1.5)
        ids = self.frame("[...document.querySelectorAll('input[id^=arg-]')].map(e=>e.id)")
        self.assertEqual(ids, ["arg-file", "arg-focus", "arg-length"])
        self.frame("document.getElementById('arg-file').focus(); 1")
        self.ws.call("Input.insertText", {"text": "ocpp"})
        self.ws.drain(1.8)
        self.snap("skills-e2e-2-complete.png")
        near = self.frame("document.getElementById('arg-file').closest('div').parentElement.innerText")
        self.assertIn("OCPP-CP012-2026-09-30.log", near)
        self.assertNotIn("tariff-2026.xlsx", near)
        self.key("Enter", "Enter", 13)
        self.ws.drain(0.6)
        self.assertEqual(self.frame("document.getElementById('arg-file').value"), "OCPP-2.0.1-spec.pdf")
        self.frame("document.getElementById('arg-focus').focus(); 1")
        self.ws.call("Input.insertText", {"text": "ข้อกำหนดการชาร์จ"})
        self.ws.drain(0.4)
        self.click_frame("document.getElementById('arg-file').closest('form').querySelector('button[type=submit]')")
        self.ws.drain(2.5)
        self.snap("skills-e2e-3-chip.png")
        chip = self.frame("(()=>{const e=[...document.querySelectorAll('[data-slot=input-area] *')].find(x=>"
                          "x.children.length<4&&(x.innerText||'').includes('สรุปเอกสารยาว'));return e?e.innerText:''})()")
        self.assertIn("สรุปเอกสาร `OCPP-2.0.1-spec.pdf`", chip)
        self.assertIn('local_read action="kb" query="ข้อกำหนดการชาร์จ"', chip)
        self.assertIn('path="attachments/OCPP-2.0.1-spec.pdf"', chip)
        self.assertNotIn("{{", chip)
        with open(self.audit, encoding="utf-8") as fh:
            got = [json.loads(x) for x in fh if '"prompt_get"' in x]
        self.assertEqual(got[-1]["prompt"], "long-doc-summary")
        self.assertEqual(got[-1]["args"], {"file": len("OCPP-2.0.1-spec.pdf"), "focus": len("ข้อกำหนดการชาร์จ")})
        self.assertEqual(self.blocked, [])


if __name__ == "__main__":
    unittest.main()
