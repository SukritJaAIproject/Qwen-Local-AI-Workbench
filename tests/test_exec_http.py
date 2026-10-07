# -*- coding: utf-8 -*-
"""เทสต์ปลายทางถึงปลายทางของ python / undo บนอินสแตนซ์ MCP ทดสอบ (พอร์ต 8892 หรือพอร์ตว่างที่ระบบสุ่ม)

เปิด server.py จากโค้ดจริงด้วย token ทดสอบ + ข้อมูลโปรเจกต์/audit/runtime ของ kernel ใน temp
ยิงผ่าน HTTP แบบเดียวกับหน้าแชต (Origin ของพอร์ตโปรเจกต์ + Bearer token) แล้วปิดเฉพาะตัวที่เปิดเอง
ตรวจว่าหลังปิดเซิร์ฟเวอร์ ไม่มี runner/kernel ค้าง (stdin ของ runner ปิด -> ปิด kernel เอง)
"""
import json
import os
import re
import socket
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

KERNEL_PYTHON = os.environ.get("QWEN_PY_KERNEL_PYTHON") or os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), "anaconda3", "python.exe")
RUNTIME = os.path.join(C.TMP, "http-kernel-secrets")
SLUG = C.PROJECT_OF_ALLOWED_ORIGIN          # พอร์ต 8103 ผูกกับ slug นี้ใน projects.json จำลอง
_STATE = {}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _runner_pids() -> list[int]:
    """pid ของ kernel_runner/ipykernel ที่ใช้โฟลเดอร์ runtime ของเทสต์นี้ (ไม่แตะของจริง)"""
    # นับเฉพาะ python*.exe และไม่นับตัว powershell ที่ถามเอง (บรรทัดคำสั่งของมันก็มี path นี้อยู่)
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and "
          "$_.Name -like 'python*' -and $_.CommandLine -and "
          "$_.CommandLine.Contains('%s') } | ForEach-Object { $_.ProcessId }" % RUNTIME.replace("'", "''"))
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True,
                           text=True, timeout=60, creationflags=0x08000000)
        return [int(x) for x in r.stdout.split() if x.strip().isdigit()]
    except Exception:          # noqa: BLE001
        return []


def setUpModule():
    if not os.path.isfile(KERNEL_PYTHON):
        raise unittest.SkipTest("ไม่มี anaconda python")
    port = 8892 if not C.port_in_use(8892) else _free_port()
    env = C.clean_env()
    env["QWEN_PY_RUNTIME"] = RUNTIME
    log = os.path.join(C.TMP, "exec-server-%d.log" % port)
    out = open(log, "wb")
    proc = subprocess.Popen([sys.executable, os.path.join(C.MCP_LOCAL, "server.py"), str(port)],
                            cwd=C.MCP_LOCAL, env=env, stdout=out, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=0x08000000)
    out.close()
    deadline = time.time() + 30
    while time.time() < deadline and not C.port_in_use(port):
        if proc.poll() is not None:
            raise RuntimeError("เซิร์ฟเวอร์ทดสอบตายตอนเริ่ม ดู %s" % log)
        time.sleep(0.2)
    _STATE.update(port=port, proc=proc)


def tearDownModule():
    proc = _STATE.get("proc")
    if proc is not None and proc.poll() is None:
        proc.kill()                            # เฉพาะเซิร์ฟเวอร์ที่เทสต์นี้เปิดเอง
        proc.wait(10)


def call(name, args, path="/fast/" + SLUG, origin=C.ALLOWED_ORIGIN):
    status, _h, raw = C.rpc(_STATE["port"], path, "tools/call",
                            {"name": name, "arguments": args}, origin=origin)
    assert status == 200, (status, raw[:300])
    return C.tool_text(raw)


class ExecOverHttpTests(unittest.TestCase):
    def test_1_tools_list_advertises_actions(self):
        status, _h, raw = C.rpc(_STATE["port"], "/fast/" + SLUG, "tools/list", origin=C.ALLOWED_ORIGIN)
        self.assertEqual(status, 200)
        tools = {t["name"]: t for t in json.loads(raw)["result"]["tools"]}
        self.assertIn("python", tools["local_do"]["inputSchema"]["properties"]["action"]["enum"])
        self.assertIn("undo", tools["local_do"]["inputSchema"]["properties"]["action"]["enum"])
        self.assertIn("checkpoints", tools["local_read"]["inputSchema"]["properties"]["action"]["enum"])
        self.assertNotIn("confirm_token", tools["local_do"]["inputSchema"]["properties"])
        status, _h, raw = C.rpc(_STATE["port"], "/mcp/" + SLUG, "tools/list", origin=C.ALLOWED_ORIGIN)
        names = [t["name"] for t in json.loads(raw)["result"]["tools"]]
        for n in ("python_exec", "undo_file", "list_checkpoints"):
            self.assertIn(n, names)

    def test_2_python_needs_local_confirm_and_runs(self):
        out = call("local_do", {"action": "python",
                                "code": "import matplotlib.pyplot as plt\nv = 6 * 7\nprint('HTTP-RAN', v)\n"
                                        "plt.bar(['ก', 'ข'], [1, 2]); plt.title('สถานี')"})
        tok = C.token_from_hint(out)
        self.assertTrue(tok, out)
        self.assertNotIn("HTTP-RAN 42", out)
        args = C.confirm_args(out)
        # หน้าของโปรเจกต์อื่น (8104 = proj-b) ยืนยันแทนไม่ได้ — ถูกปัดตั้งแต่ด่าน HTTP
        status, _h, _raw = C.rpc(_STATE["port"], "/fast/" + SLUG, "tools/call",
                                 {"name": "local_confirm", "arguments": args},
                                 origin="http://127.0.0.1:8104")
        self.assertEqual(status, 403)
        out = call("local_confirm", args)
        self.assertIn("HTTP-RAN 42", out)
        self.assertRegex(out, r"!\[fig\]\(/_qwen/out/fig-[\w.-]+\.png\)")
        out = call("local_confirm", args)
        self.assertIn("ใช้ไม่ได้", out)
        # ตัวแปรคงอยู่ในครั้งถัดไป
        out = call("local_confirm", C.confirm_args(
            call("local_do", {"action": "python", "code": "print('again', v)"})))
        self.assertIn("again 42", out)

    def test_3_write_then_undo_over_http(self):
        target = os.path.join(C.new_dir("http-undo"), "cfg.ini")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("[a]\nx=1\n")
        out = call("local_do", {"action": "write", "path": target, "content": "[a]\nx=2\n"})
        self.assertIn("-x=1", out)
        out = call("local_confirm", C.confirm_args(out))
        self.assertIn("เขียนแล้ว", out)
        self.assertIn("+x=2", out)
        out = call("local_read", {"action": "checkpoints", "path": target})
        self.assertIn("write_file", out)
        out = call("local_confirm", C.confirm_args(call("local_do", {"action": "undo", "path": target})))
        self.assertIn("ย้อนแล้ว", out)
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "[a]\nx=1\n")

    def test_4_audit_has_no_secret_values(self):
        with open(C.AUDIT_LOCAL, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('"kind": "python_exec"', text)
        self.assertNotIn(C.TOKEN, text)
        self.assertIsNone(re.search(r'confirm_token"?\s*[:=]\s*"?[0-9a-f]{8}\b', text))

    def test_5_timeout_in_ms_is_interpreted_and_replayed(self):
        """integrator 2026-09-30: โมเดล 4B ส่ง timeout="30000" (มิลลิวินาที) ของเดิมหนีบเงียบๆ เป็น 240 วินาที
        หน้าขออนุมัติต้องบอก 30 วินาที และ local_confirm ที่เล่นซ้ำอาร์กิวเมนต์เดิมต้องตรงกับ token"""
        out = call("local_do", {"action": "python", "code": "print('TMO', 2 + 3)", "timeout": "30000"})
        self.assertIn("เวลาสูงสุด: 30 วินาที", out)
        self.assertIn("มิลลิวินาที", out)
        tok = C.token_from_hint(out)
        self.assertTrue(tok, out)
        out = call("local_confirm", C.confirm_args(out))
        self.assertIn("TMO 5", out)
        self.assertIn("เวลาสูงสุดของครั้งนี้", out)
        # หน่วยที่เขียนเป็นคำก็ผ่านผิว /fast ถึงปลายทางได้ (เดิมถูก _int กลืนเป็น 120)
        out = call("local_do", {"action": "python", "code": "print(1)", "timeout": "45s"})
        self.assertIn("เวลาสูงสุด: 45 วินาที", out)

    def test_9_no_orphans_after_server_stops(self):
        before = _runner_pids()
        self.assertTrue(before, "ควรมี runner/kernel ของเทสต์นี้ทำงานอยู่ก่อนปิดเซิร์ฟเวอร์")
        tearDownModule()
        deadline = time.time() + 45
        left = before
        while time.time() < deadline:
            left = _runner_pids()
            if not left:
                break
            time.sleep(1.5)
        self.assertEqual(left, [], "runner/kernel ต้องจบเองเมื่อ MCP ปิด")


if __name__ == "__main__":
    unittest.main()
