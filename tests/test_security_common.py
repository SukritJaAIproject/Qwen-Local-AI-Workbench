# -*- coding: utf-8 -*-
"""ตัวช่วยร่วมของเทสต์ความปลอดภัย (รอบแก้ 2026-09-30, ช่องโหว่ V1-V7)

ไฟล์นี้ไม่มีเทสต์ของตัวเอง มีแต่การเตรียมสภาพแวดล้อมให้ test_security_*.py ใช้ร่วมกัน

หลักการที่ห้ามละเมิด
  * ไม่แตะข้อมูลจริง: audit.log, ข้อมูลโปรเจกต์ และไฟล์ token ถูกชี้ไปที่โฟลเดอร์ชั่วคราวผ่าน env
    (QWEN_MCP_AUDIT_PATH, QWEN_MCP_PROJECT_DATA, QWEN_WEB_AUDIT_PATH, LLM_LOCAL_TOKEN_FILE)
    และแก้ attribute ของ guard ซ้ำอีกชั้น เผื่อรันกับโค้ดรุ่นเก่าที่ยังไม่รู้จัก env เหล่านี้
  * token ที่ใช้คือ token ทดสอบที่สุ่มขึ้นใหม่ทุกครั้ง ไม่อ่าน C:\\LLM\\secrets จริงเลย
  * เซิร์ฟเวอร์ทดสอบใช้พอร์ตสำรอง 8891 (websearch) และ 8892 (local) — ถ้าไม่ว่าง test_security_http
    ถอยไปใช้พอร์ตว่างที่ระบบสุ่มให้ (แก้ LOCAL_PORT/WEB_PORT ของโมดูลนี้) ไม่ข้ามเทสต์ทั้งไฟล์
    เปิดด้วย env ที่คัดมาแค่ตัวที่จำเป็น (ไม่ส่งต่อ env ของผู้รันเทสต์ซึ่งอาจมีความลับ)

รันกับโค้ดรุ่นเก่าเพื่อพิสูจน์ว่าเทสต์จับช่องโหว่ได้จริง:
  set SEC_TEST_MCP_LOCAL=C:\\LLM\\projects\\backup\\sec-20260930-045133\\mcp-local
  set SEC_TEST_MCP_WEB=C:\\LLM\\projects\\backup\\sec-20260930-045133\\mcp-websearch
  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -p "test_security_*.py"
เทสต์ที่ "ต้องล้ม" กับโค้ดเก่าถูกเขียนให้ตรวจเงื่อนไขปลอดภัยก่อนทุกครั้ง ก่อนจะลองอะไรที่
โค้ดเก่าจะทำจริง (เช่นเขียน C:\\LLM\\mcp-local\\config.json) — จึงไม่มีทางทำลายระบบจริง
"""
from __future__ import annotations

import atexit
import importlib
import importlib.util
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

LLM_ROOT = r"C:\LLM"
MCP_LOCAL = os.environ.get("SEC_TEST_MCP_LOCAL") or os.path.join(LLM_ROOT, "mcp-local")
MCP_WEB = os.environ.get("SEC_TEST_MCP_WEB") or os.path.join(LLM_ROOT, "mcp-websearch")
# โหมดรันกับโค้ดรุ่นเก่า: เทสต์ที่ถ้าโค้ดมีช่องโหว่จะ "ยิงบริการจริง/วง LAN" ต้องข้าม
# (เช่น fetch ไปที่ 127.0.0.1:8100 ของ hub จริง หรือ 192.168.1.1 ของเราเตอร์) — พิสูจน์ช่องโหว่ได้
# ด้วยเป้าหมายจำลองบน 127.0.0.1 พอร์ตสุ่มอยู่แล้ว ไม่ต้องไปแตะของจริง
OLD_CODE_MODE = (os.path.normcase(MCP_LOCAL) != os.path.normcase(os.path.join(LLM_ROOT, "mcp-local"))
                 or os.path.normcase(MCP_WEB) != os.path.normcase(os.path.join(LLM_ROOT, "mcp-websearch")))
LOCAL_PORT = 8892
WEB_PORT = 8891
ALLOWED_ORIGIN = "http://127.0.0.1:8103"
EVIL_ORIGIN = "http://evil.example"

# โฟลเดอร์ชั่วคราวหนึ่งชุดต่อโปรเซสเทสต์ ต้องอยู่ใต้ %USERPROFILE% (root ที่ guard ให้เขียน — %TEMP% ปกติอยู่ใต้นั้น)
_BASE = tempfile.mkdtemp(prefix="sec-tests-")
TMP = os.path.realpath(_BASE)
PROJECT_DATA = os.path.join(TMP, "projdata")
AUDIT_LOCAL = os.path.join(TMP, "audit-local.log")
AUDIT_WEB = os.path.join(TMP, "audit-web.log")
TOKEN_FILE = os.path.join(TMP, "token", "local-services.token")
TOKEN = secrets.token_hex(32)          # token ทดสอบ ไม่ใช่ของจริง
# ผังพอร์ต -> โปรเจกต์จำลอง (แทน C:\LLM\projects\projects.json ของ hub) ใช้ทดสอบการผูก Origin กับ slug
# 8103 = ALLOWED_ORIGIN ของเทสต์ ผูกกับ "sec-http" / 8104 ผูกกับ "proj-b" / 8150 ไม่มีโปรเจกต์
PROJECTS_JSON = os.path.join(TMP, "projects.json")
PROJECT_OF_ALLOWED_ORIGIN = "sec-http"
os.makedirs(PROJECT_DATA, exist_ok=True)
os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
with open(TOKEN_FILE, "w", encoding="ascii", newline="\n") as _fh:
    _fh.write(TOKEN + "\n")
with open(PROJECTS_JSON, "w", encoding="utf-8") as _fh:
    json.dump([{"slug": PROJECT_OF_ALLOWED_ORIGIN, "name": "t", "port": 8103},
               {"slug": "proj-b", "name": "b", "port": 8104}], _fh)

os.environ["QWEN_MCP_AUDIT_PATH"] = AUDIT_LOCAL
os.environ["QWEN_MCP_PROJECT_DATA"] = PROJECT_DATA
os.environ["QWEN_WEB_AUDIT_PATH"] = AUDIT_WEB
os.environ["LLM_LOCAL_TOKEN_FILE"] = TOKEN_FILE
os.environ["QWEN_MCP_PROJECTS_JSON"] = PROJECTS_JSON

for _p in (MCP_LOCAL,):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if LLM_ROOT not in sys.path:
    sys.path.append(LLM_ROOT)


@atexit.register
def _cleanup():
    shutil.rmtree(_BASE, ignore_errors=True)


def import_local(name: str):
    """import โมดูลของ mcp-local (จากโฟลเดอร์ที่เลือกด้วย SEC_TEST_MCP_LOCAL) แล้วชี้ path ไปที่ temp"""
    saved = sys.argv
    sys.argv = [saved[0]]              # server.py อ่าน sys.argv[1] เป็นพอร์ตตอน import
    try:
        mod = importlib.import_module(name)
    finally:
        sys.argv = saved
    guard = importlib.import_module("guard")
    from pathlib import Path
    guard.AUDIT_PATH = Path(AUDIT_LOCAL)
    guard.PROJECT_DATA = Path(PROJECT_DATA)
    return mod


_WS = {}


def import_websearch():
    """โหลด server.py ของ mcp-websearch ด้วยชื่ออื่น (กันชนกับ server ของ mcp-local)"""
    if "mod" not in _WS:
        saved = sys.argv
        sys.argv = [saved[0]]
        try:
            spec = importlib.util.spec_from_file_location("ws_server_under_test",
                                                          os.path.join(MCP_WEB, "server.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            sys.argv = saved
        from pathlib import Path
        mod.AUDIT = Path(AUDIT_WEB)
        _WS["mod"] = mod
    return _WS["mod"]


def new_dir(name: str) -> str:
    d = os.path.join(TMP, "%s-%s" % (name, secrets.token_hex(3)))
    os.makedirs(d, exist_ok=True)
    return d


def token_from_hint(text: str) -> str:
    """ดึง confirm_token ออกจากข้อความขอยืนยัน (รูปแบบเดิมและใหม่ใช้ confirm_token=\"xxxx\")"""
    import re
    m = re.search(r'confirm_token="([0-9a-f]+)"', text or "")
    return m.group(1) if m else ""


def review_from_hint(text: str) -> str:
    """ดึงข้อความในบล็อก REVIEW (รั้ว ```review ... ```) ออกจากข้อความขอยืนยัน — สิ่งที่โมเดลต้องส่งให้ local_confirm
    รั้วยาวกว่า backtick ใดๆ ในเนื้อหาเสมอ จึงจับคู่รั้วเปิด/ปิดที่ยาวเท่ากัน"""
    import re
    m = re.search(r"(?m)^(`{3,})review\n(.*?)\n\1$", text or "", re.S)
    return m.group(2) if m else ""


def confirm_args(text: str) -> dict:
    """อาร์กิวเมนต์ของ local_confirm จากข้อความขอยืนยัน: token + review ตรงตัว (สิ่งที่โมเดลที่ทำถูกจะส่ง)"""
    return {"confirm_token": token_from_hint(text), "review": review_from_hint(text)}


def confirming(guard_mod, tok: str):
    """จำลอง "ผู้ใช้กดอนุญาต local_confirm" สำหรับเทสต์ที่เรียกฟังก์ชันเครื่องมือตรงๆ

    ตั้งแต่รอบ FIXER token ใช้ได้เฉพาะภายใน guard.confirming(token) (ที่ server.py เปิดให้ตอนเล่นซ้ำ)
    รอบ review: guard.confirming(token, review) ต้องได้ข้อความตรวจทานที่ตรงกับที่เก็บไว้ — ตัวช่วยนี้จำลอง
    โมเดลที่ทำถูก (ส่ง review ของ token นั้นตรงตัว) ขอบเขตโปรเจกต์ยังถูกบังคับที่ consume_confirm ตามเดิม
    โค้ดรุ่นเก่าไม่มีฟังก์ชันนี้ จึงคืน context เปล่า เพื่อให้เทสต์ชุดเดิมยังเทียบโค้ดเก่าได้
    """
    import contextlib
    fn = getattr(guard_mod, "confirming", None)
    if not fn:
        return contextlib.nullcontext()
    if getattr(guard_mod, "pending_review", None) is None:
        return fn(tok)                                  # โค้ดรุ่นก่อนรอบ review
    item = getattr(guard_mod, "_pending", {}).get(str(tok or "").strip()) or {}
    return fn(tok, item.get("review"))


# ------------------------------------------------------------- เซิร์ฟเวอร์ทดสอบ
def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def clean_env() -> dict:
    """env ขั้นต่ำสำหรับโปรเซสลูก — ไม่ส่งต่อ env ของผู้รันเทสต์ทั้งก้อน"""
    keep = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP",
            "USERPROFILE", "USERNAME", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "HOMEDRIVE",
            "HOMEPATH", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS",
            "PROGRAMFILES", "PROGRAMFILES(X86)", "COMMONPROGRAMFILES")
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1",
                "QWEN_MCP_AUDIT_PATH": AUDIT_LOCAL, "QWEN_MCP_PROJECT_DATA": PROJECT_DATA,
                "QWEN_WEB_AUDIT_PATH": AUDIT_WEB, "LLM_LOCAL_TOKEN_FILE": TOKEN_FILE,
                "QWEN_MCP_PROJECTS_JSON": PROJECTS_JSON})
    return env


class TestServer:
    """เปิดเซิร์ฟเวอร์ MCP หนึ่งตัวบนพอร์ตทดสอบ แล้วปิดเฉพาะตัวที่เปิดเองตอนจบ"""

    def __init__(self, code_dir: str, port: int):
        self.code_dir, self.port, self.proc = code_dir, port, None
        self.log = os.path.join(TMP, "server-%d.log" % port)

    def start(self, timeout: float = 30.0) -> None:
        if port_in_use(self.port):
            raise RuntimeError("พอร์ต %d มีโปรแกรมอื่นใช้อยู่" % self.port)
        out = open(self.log, "wb")
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(self.code_dir, "server.py"), str(self.port)],
            cwd=self.code_dir, env=clean_env(), stdout=out, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out.close()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("เซิร์ฟเวอร์ทดสอบพอร์ต %d ตายตอนเริ่ม ดู %s" % (self.port, self.log))
            if port_in_use(self.port):
                return
            time.sleep(0.2)
        raise RuntimeError("เซิร์ฟเวอร์ทดสอบพอร์ต %d ไม่ขึ้นใน %ds" % (self.port, timeout))

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()                # เฉพาะโปรเซสที่เทสต์นี้เปิดเอง
            self.proc.wait(10)


def http(method: str, port: int, path: str, body=None, headers=None, host=None,
         timeout: float = 30.0):
    """ยิง HTTP ด้วย http.client ตรงๆ (คุม Host/Origin ได้เอง) คืน (status, headers dict, body)"""
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host or "127.0.0.1:%d" % port)
        for k, v in hdrs.items():
            conn.putheader(k, v)
        if data is not None:
            conn.putheader("Content-Length", str(len(data)))
        conn.endheaders(data)
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, raw
    finally:
        conn.close()


def rpc(port: int, path: str, method: str, params=None, token: str | None = TOKEN,
        origin: str | None = None, rid: int = 1):
    headers = {"Accept": "application/json, text/event-stream"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if origin is not None:
        headers["Origin"] = origin
    return http("POST", port, path, {"jsonrpc": "2.0", "id": rid, "method": method,
                                     "params": params or {}}, headers)


def tool_text(raw: bytes) -> str:
    data = json.loads(raw.decode("utf-8"))
    return data["result"]["content"][0]["text"]


class LocalHTTPServer:
    """เว็บเซิร์ฟเวอร์เล็กๆ บน 127.0.0.1 พอร์ตสุ่ม ใช้เป็น "เป้าหมายภายใน" ของเทสต์ SSRF"""

    MARKER = "INTERNAL-ONLY-MARKER-7f3a"

    def __init__(self):
        import http.server
        import threading
        marker = self.MARKER
        self.seen_headers = []
        seen = self.seen_headers

        class _H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                seen.append({k.lower(): v for k, v in self.headers.items()})
                body = ("<html><title>t</title><body>%s</body></html>" % marker).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
