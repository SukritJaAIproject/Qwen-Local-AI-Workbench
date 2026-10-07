# -*- coding: utf-8 -*-
"""เทสต์ local_do action="python" / python_exec (สัญญา K1, owner mcp-exec)

สองกลุ่ม
  1) ความปลอดภัย (ส่วนใหญ่ไม่ต้องเปิด kernel):
     * รันไม่ได้เลยถ้าไม่ผ่าน local_confirm — ไม่มี token = คืน token อย่างเดียว ไม่มีโปรเซสใดถูกเปิด
     * token ส่งตรงนอก local_confirm ใช้ไม่ได้, ผูกกับโค้ด/timeout/โปรเจกต์, ใช้ได้ครั้งเดียว
     * ผ่าน server จริง (handle_rpc): local_do + confirm_token = ช่องทางผิด, local_confirm = รันได้
     * โค้ดที่อ้างถึง secrets/token หรือโค้ดของสแตก ถูกปฏิเสธก่อนออก token
     * ไม่มีขอบเขตโปรเจกต์ = ปฏิเสธ (S04 fail-closed)
     * env ของ kernel: ไม่มีความลับ ไม่มี env ของผู้เรียก (sentinel) ไม่มีค่า token ทดสอบ
  2) การทำงาน (kernel จริงของ anaconda หนึ่งตัว ใช้ร่วมกันทั้งคลาส):
     ตัวแปรคงอยู่ข้ามครั้ง, cwd = work\\, รูป matplotlib -> PNG + ลิงก์, ไฟล์ใหม่ใน outputs -> ลิงก์,
     error, timeout แบบ interrupt, plotly -> PNG (หรือ HTML ถ้า Edge ใช้ไม่ได้)

ข้อมูลโปรเจกต์ audit และโฟลเดอร์ runtime ของ kernel อยู่ใน temp ทั้งหมด ปิด kernel ทุกตัวตอนจบ
"""
import json
import os
import re
import sys
import time
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

RUNTIME = os.path.join(C.TMP, "kernel-secrets-rt")
# sentinel ในโปรเซสผู้เรียก — ห้ามไปโผล่ใน kernel เด็ดขาด (ตั้งเฉพาะช่วงที่โมดูลนี้รัน แล้วคืนค่าเดิม)
SENTINELS = {"QWEN_TEST_SENTINEL_SECRET": "sentinel-value-9f3a",
             "ANTHROPIC_API_KEY": "sk-ant-sentinel-000000000000",
             "GATEWAY_API_KEY": "gw-sentinel-111111",
             "OPENAI_API_KEY": "sk-sentinel-222222222222",
             "CLAUDE_CODE_SENTINEL": "agent-env-333",
             "GH_TOKEN": "ghp_sentinel4444444444",
             "QWEN_PY_RUNTIME": RUNTIME}
_SAVED_ENV = {}

guard = C.import_local("guard")
tools_python = C.import_local("tools_python")
tools_fast = C.import_local("tools_fast")
server = C.import_local("server")

HAVE_KERNEL = os.path.isfile(tools_python.KERNEL_PYTHON) and tools_python.RUNNER.is_file()


def setUpModule():
    for k, v in SENTINELS.items():
        _SAVED_ENV[k] = os.environ.get(k)
        os.environ[k] = v
    tools_python.RUNTIME_BASE = Path(RUNTIME)   # runtime ของ kernel อยู่ใน temp (ไม่แตะ LOCALAPPDATA จริง)


def tearDownModule():
    tools_python.shutdown_all()
    for k, v in _SAVED_ENV.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _marker_code(path: str) -> str:
    return "open(%r, 'w').write('ran')\nprint('MARKER-OK')" % path


class ConfirmFlowTests(unittest.TestCase):
    """รันโค้ดไม่ได้เลยถ้าไม่ผ่าน local_confirm — ไม่ต้องเปิด kernel"""

    def setUp(self):
        self.slug = "py-sec-%s" % os.urandom(3).hex()
        self.marker = os.path.join(C.new_dir("pymark"), "ran.txt")

    def test_first_call_only_returns_token(self):
        with guard.project_scope(self.slug):
            out = tools_python.python_exec(code=_marker_code(self.marker))
        self.assertIn("confirm_token", out)
        self.assertIn("local_confirm", out)
        self.assertIn("MARKER-OK", out, "ผู้ใช้ต้องเห็นโค้ดในข้อความขอยืนยัน")
        self.assertIn("sandbox", out)
        self.assertFalse(os.path.exists(self.marker))
        self.assertNotIn(self.slug, tools_python.kernel_status(), "ยังไม่อนุมัติ = ห้ามเปิด kernel")

    def test_every_call_needs_confirmation(self):
        """ไม่มีโค้ดไหนรันทันที แม้แต่ print(1) — Python ตัดสินไม่ได้ว่าโค้ดไหนอ่านอย่างเดียว"""
        with guard.project_scope(self.slug):
            for code in ("print(1)", "1+1", "x = 5", "import os"):
                out = tools_python.python_exec(code=code)
                self.assertIn("confirm_token", out, code)
        self.assertNotIn(self.slug, tools_python.kernel_status())

    def test_token_outside_local_confirm_rejected(self):
        with guard.project_scope(self.slug):
            tok = C.token_from_hint(tools_python.python_exec(code=_marker_code(self.marker)))
            self.assertTrue(tok)
            out = tools_python.python_exec(code=_marker_code(self.marker), confirm_token=tok)
        self.assertIn("ใช้ไม่ได้", out)
        self.assertFalse(os.path.exists(self.marker))
        self.assertNotIn(self.slug, tools_python.kernel_status())

    def test_token_bound_to_code_timeout_and_project(self):
        with guard.project_scope(self.slug):
            tok = C.token_from_hint(tools_python.python_exec(code="print('approved')", timeout=30))
            with C.confirming(guard, tok):
                out = tools_python.python_exec(code=_marker_code(self.marker), timeout=30,
                                               confirm_token=tok)
            self.assertIn("ใช้ไม่ได้", out)
            with C.confirming(guard, tok):
                out = tools_python.python_exec(code="print('approved')", timeout=31, confirm_token=tok)
            self.assertIn("ใช้ไม่ได้", out)
        with guard.project_scope(self.slug + "-other"):
            with C.confirming(guard, tok):
                out = tools_python.python_exec(code="print('approved')", timeout=30, confirm_token=tok)
            self.assertIn("ใช้ไม่ได้", out)
        self.assertFalse(os.path.exists(self.marker))
        self.assertNotIn(self.slug, tools_python.kernel_status())
        self.assertNotIn(self.slug + "-other", tools_python.kernel_status())

    def test_secret_or_stack_code_denied_before_token(self):
        bad = [r"open(r'C:\LLM\secrets\local-services.token').read()",
               "open('C:/LLM/secrets/x').read()",
               "print(open('local-services.token').read())",
               r"open(r'C:\LLM\mcp-local\guard.py', 'w').write('')",
               r"import shutil; shutil.rmtree(r'C:\LLM\mcp-local')",
               r"open(r'C:\LLM\projects\hub.py','a')"]
        with guard.project_scope(self.slug):
            for code in bad:
                out = tools_python.python_exec(code=code)
                self.assertTrue(out.startswith("ปฏิเสธ"), (code, out))
                self.assertNotIn("confirm_token=", out, code)

    def test_no_project_scope_is_denied(self):
        out = tools_python.python_exec(code="print(1)", project="whatever")
        self.assertTrue(out.startswith("ปฏิเสธ"), out)

    def test_empty_and_huge_code(self):
        with guard.project_scope(self.slug):
            self.assertIn("ต้องใส่ code", tools_python.python_exec(code="   "))
            out = tools_python.python_exec(code="#" * (tools_python.MAX_CODE_CHARS + 1))
            self.assertIn("ยาวเกิน", out)

    def test_fast_surface_requires_code_and_confirmation(self):
        with guard.project_scope(self.slug):
            out = tools_fast.local_do(action="python", project=self.slug)
            self.assertIn("ยังขาดพารามิเตอร์", out)
            out = tools_fast.local_do(action="python", project=self.slug,
                                      code=_marker_code(self.marker))
            self.assertIn("confirm_token", out)
        self.assertFalse(os.path.exists(self.marker))

    def test_timeout_is_clamped(self):
        self.assertEqual(tools_python._clamp_timeout("abc"), tools_python.DEFAULT_TIMEOUT)
        # 0 = "ไม่จำกัดเวลา" ซึ่งไม่มีให้ -> เพดาน (เดิมเป็นขั้นต่ำ 5 วินาที ซึ่งตัดโค้ดทิ้งผิดเจตนา)
        self.assertEqual(tools_python._clamp_timeout(0), tools_python.MAX_TIMEOUT)
        self.assertEqual(tools_python._clamp_timeout(99999), 100)      # = 99.999 วินาที (มิลลิวินาที)
        self.assertEqual(tools_python._clamp_timeout(600), tools_python.MAX_TIMEOUT)
        self.assertEqual(tools_python._clamp_timeout(2), tools_python.MIN_TIMEOUT)
        self.assertEqual(tools_python._clamp_timeout("45"), 45)


class TimeoutUnitTests(unittest.TestCase):
    """integrator 2026-09-30: โมเดล 4B ส่ง timeout="30000" (มิลลิวินาที) แล้วถูกหนีบเงียบๆ เป็น 240 วินาที
    ค่าที่ตีความ/หนีบต้องบอกในหน้าขออนุมัติเสมอ และค่าเดิมต้องให้ผลเดิม (local_confirm เล่นซ้ำอาร์กิวเมนต์)"""

    def setUp(self):
        self.slug = "py-tmo-%s" % os.urandom(3).hex()

    def test_parse_units(self):
        P = tools_python._parse_timeout
        # list ไม่ใช่ dict: 30000 กับ 30000.0 เป็นคีย์เดียวกันใน dict
        cases = [("30000", 30), (30000, 30), (30000.0, 30), ("30,000", 30), ("30000ms", 30),
                 ("30000 ms", 30), ("30s", 30), ("30 sec", 30), ("30 วินาที", 30), ("2m", 120),
                 ("2 นาที", 120), ("1.5 min", 90), ("1h", 240), ("2 ชม.", 240), ("999", 240),
                 ("600", 240), ("3000", 5), ("3", 5), ("0", 240), ("-5", 240), ("45", 45), (45, 45),
                 ("240", 240), ("5", 5), ("๓๐", 30), ("", 120), (None, 120), ("   ", 120),
                 ("abc", 120), ("inf", 120), ("nan", 120), ("1e3", 120), (True, 120)]
        for raw, want in cases:
            self.assertEqual(P(raw)[0], want, repr(raw))

    def test_note_only_when_value_differs(self):
        P = tools_python._parse_timeout
        for raw in ("45", 45, "30s", "30 วินาที", "", None, "240", "5"):
            self.assertEqual(P(raw)[1], "", raw)
        self.assertIn("มิลลิวินาที", P("30000")[1])
        self.assertIn("30 วินาที", P("30000")[1])
        self.assertIn("เพดาน", P("600")[1])
        self.assertIn("ขั้นต่ำ", P("3000")[1])
        self.assertIn("ไม่ออก", P("abc")[1])
        self.assertIn("120 วินาที", P("2 นาที")[1])

    def test_note_is_sanitised_and_capped(self):
        note = tools_python._parse_timeout("x\n`" + "y" * 200)[1]
        self.assertNotIn("\n", note)
        self.assertNotIn("`", note)
        self.assertLess(len(note), 200)

    def test_same_input_same_result(self):
        """token ผูกกับวินาทีหลังตีความ: เล่นซ้ำค่าเดิมต้องได้ค่าเดิมทุกครั้ง"""
        for raw in ("30000", "2 นาที", "abc", "600", 30000):
            self.assertEqual(tools_python._parse_timeout(raw), tools_python._parse_timeout(raw))

    def test_preview_states_interpreted_seconds(self):
        with guard.project_scope(self.slug):
            out = tools_python.python_exec(code="print(1)", timeout="30000")
        self.assertIn("เวลาสูงสุด: 30 วินาที", out)
        self.assertIn("หมายเหตุเวลา:", out)
        self.assertIn("มิลลิวินาที", out)
        with guard.project_scope(self.slug):
            out = tools_python.python_exec(code="print(1)", timeout=45)
        self.assertIn("เวลาสูงสุด: 45 วินาที", out)
        self.assertNotIn("หมายเหตุเวลา", out)
        self.assertNotIn(self.slug, tools_python.kernel_status(), "ยังไม่อนุมัติ = ห้ามเปิด kernel")

    def test_fast_surface_passes_units_through(self):
        """เดิม _int ของ tools_fast กลืน "30s" เป็น 120 เงียบๆ ก่อนถึง tools_python"""
        with guard.project_scope(self.slug):
            for raw, want in (("30s", 30), ("30000", 30), ("2 นาที", 120), ("", 120)):
                out = tools_fast.local_do(action="python", project=self.slug, code="print(1)",
                                          timeout=raw)
                self.assertIn("confirm_token", out, raw)
                self.assertIn("เวลาสูงสุด: %d วินาที" % want, out, raw)
            out = tools_fast.local_do(action="python", project=self.slug, code="print(1)")
            self.assertIn("เวลาสูงสุด: 120 วินาที", out)
        self.assertNotIn(self.slug, tools_python.kernel_status())

    def test_token_binds_interpreted_seconds(self):
        """token จาก "30000" ใช้กับค่าที่ได้ 30 วินาทีเท่านั้น — 31 วินาทีหรือ 240 (ของเดิม) ใช้ไม่ได้
        (ไม่เปิด kernel: ทุกกรณีต้องล้มที่ consume_confirm ก่อนถึง _run)"""
        marker = os.path.join(C.new_dir("pytmo"), "ran.txt")
        code = _marker_code(marker)
        with guard.project_scope(self.slug):
            tok = C.token_from_hint(tools_python.python_exec(code=code, timeout="30000"))
            self.assertTrue(tok)
            for other in ("31", "240", 31000):
                with C.confirming(guard, tok):
                    out = tools_python.python_exec(code=code, timeout=other, confirm_token=tok)
                self.assertIn("ใช้ไม่ได้", out, other)
        self.assertFalse(os.path.exists(marker))
        self.assertNotIn(self.slug, tools_python.kernel_status())


class KernelEnvUnitTests(unittest.TestCase):
    def test_env_is_allowlisted_and_scrubbed(self):
        env = tools_python.kernel_env(os.path.join(C.TMP, "rt-unit"))
        for name, value in SENTINELS.items():
            self.assertNotIn(name, env)
            if name != "QWEN_PY_RUNTIME":                 # ค่านี้คือ path ของ runtime ซึ่งตั้งใจส่งเป็น JUPYTER_RUNTIME_DIR
                self.assertNotIn(value, json.dumps(env))
        for name in ("LLM_LOCAL_TOKEN_FILE", "QWEN_MCP_AUDIT_PATH", "QWEN_MCP_PROJECT_DATA",
                     "QWEN_MCP_PROJECTS_JSON", "QWEN_PY_RUNTIME"):
            self.assertNotIn(name, env)
        self.assertNotIn(C.TOKEN, json.dumps(env))
        for k in env:
            self.assertFalse(tools_python._SECRETISH_RE.search(k), k)
        self.assertEqual(env["MPLBACKEND"], "Agg")
        self.assertTrue(env["IPYTHONDIR"].startswith(os.path.join(C.TMP, "rt-unit")))
        # PATH สร้างใหม่ ไม่ใช่ของผู้เรียก
        self.assertTrue(env["PATH"].lower().startswith(
            os.path.dirname(tools_python.KERNEL_PYTHON).lower()))

    def test_runtime_dir_is_unreadable_by_file_tools(self):
        """ไฟล์ connection ของ kernel (คีย์ HMAC) ต้องอยู่ในที่ที่เครื่องมืออ่านไฟล์ของโมเดลเปิดไม่ได้"""
        real = os.path.join(os.environ.get("LOCALAPPDATA") or "", "qwen-kernel-secrets",
                            "project1", "kernel-123.json")
        with guard.project_scope("project1"):
            with self.assertRaises(guard.Denied):
                guard.check_read(real)


@unittest.skipUnless(HAVE_KERNEL, "ไม่มี anaconda python/jupyter_client บนเครื่องนี้")
class ServerConfirmTests(unittest.TestCase):
    """เส้นทางจริงผ่าน server.handle_rpc: ขั้นยืนยันมีทางเดียวคือ local_confirm"""

    @classmethod
    def setUpClass(cls):
        server.load_modules()
        cls.slug = "py-srv-%s" % os.urandom(3).hex()

    def call(self, name, args, fast=True):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": args}}
        return server.handle_rpc(msg, self.slug, fast=fast)["result"]["content"][0]["text"]

    def test_fast_then_full_surface(self):
        work = os.path.join(C.PROJECT_DATA, self.slug, "work")
        code = "open('srv-marker.txt','w').write('x')\nprint('SERVER-RAN', 6*7)"
        hint = self.call("local_do", {"action": "python", "code": code})
        tok = C.token_from_hint(hint)
        self.assertTrue(tok, hint)
        # ทางเก่า: ส่ง token ให้ local_do ตรงๆ = ไม่ทำอะไร
        out = self.call("local_do", {"action": "python", "code": code, "confirm_token": tok})
        self.assertIn("local_confirm", out)
        self.assertFalse(os.path.exists(os.path.join(work, "srv-marker.txt")))
        # token ของผิว /fast ใช้กับ local_confirm ของผิว /mcp ไม่ได้ (แม้ review ถูกต้อง)
        out = self.call("local_confirm", C.confirm_args(hint), fast=False)
        self.assertNotIn("SERVER-RAN", out)
        hint = self.call("local_do", {"action": "python", "code": code})
        out = self.call("local_confirm", C.confirm_args(hint))
        self.assertIn("SERVER-RAN 42", out)
        self.assertTrue(os.path.isfile(os.path.join(work, "srv-marker.txt")), "cwd ต้องเป็น work\\")
        out = self.call("local_confirm", C.confirm_args(hint))
        self.assertIn("ใช้ไม่ได้", out)
        # ผิวเต็ม: python_exec ก็ต้องยืนยันเหมือนกัน และ project มาจาก URL ไม่ใช่จากโมเดล
        out = self.call("python_exec", {"code": "print('FULL', 1+1)", "project": "evil"}, fast=False)
        tok = C.token_from_hint(out)
        self.assertTrue(tok, out)
        self.assertIn(self.slug, out)
        out = self.call("local_confirm", C.confirm_args(out), fast=False)
        self.assertIn("FULL 2", out)


@unittest.skipUnless(HAVE_KERNEL, "ไม่มี anaconda python/jupyter_client บนเครื่องนี้")
class KernelBehaviourTests(unittest.TestCase):
    """kernel จริงหนึ่งตัว — เมธอดตั้งชื่อ test_1.. เพื่อให้รันตามลำดับ (สถานะต่อเนื่อง)"""

    @classmethod
    def setUpClass(cls):
        cls.slug = "py-kern-%s" % os.urandom(3).hex()
        cls.out_dir = os.path.join(C.PROJECT_DATA, cls.slug, "outputs")
        cls.work_dir = os.path.join(C.PROJECT_DATA, cls.slug, "work")

    def run_code(self, code, timeout=60):
        with guard.project_scope(self.slug):
            tok = C.token_from_hint(tools_python.python_exec(code=code, timeout=timeout))
            self.assertTrue(tok)
            with C.confirming(guard, tok):
                return tools_python.python_exec(code=code, timeout=timeout, confirm_token=tok)

    def test_1_state_persists_and_cwd(self):
        out = self.run_code("x = 41\nimport os\nprint(os.getcwd())")
        self.assertIn("เปิด kernel ใหม่", out)
        self.assertIn(os.path.normcase(self.work_dir), os.path.normcase(out))
        out = self.run_code("print('value', x + 1)\nx * 2")
        self.assertIn("value 42", out)
        self.assertIn("[ผลลัพธ์]\n82", out)
        self.assertNotIn("เปิด kernel ใหม่", out)
        self.assertIn("In [2]", out)

    def test_2_kernel_env_has_no_secrets(self):
        out = self.run_code("import os, json\nprint('ENV=' + json.dumps(dict(os.environ)))")
        m = re.search(r"ENV=(\{.*\})", out)
        self.assertTrue(m, out)
        env = json.loads(m.group(1))
        for name, value in SENTINELS.items():
            self.assertNotIn(name, env)
            if name != "QWEN_PY_RUNTIME":
                self.assertNotIn(value, m.group(1))
        self.assertNotIn(C.TOKEN, m.group(1))
        for name in ("LLM_LOCAL_TOKEN_FILE", "QWEN_MCP_AUDIT_PATH", "QWEN_MCP_PROJECT_DATA",
                     "QWEN_PY_RUNTIME", "PYTHONPATH"):
            self.assertNotIn(name, env)
        for k in env:
            self.assertFalse(re.search(r"(?i)(api_?key|token|secret|passw|credential)", k), k)

    def test_3_matplotlib_figure_saved_with_link(self):
        out = self.run_code("import matplotlib.pyplot as plt\n"
                            "plt.plot([1, 2, 3], [2, 1, 3])\nplt.title('กราฟทดสอบ')\nplt.show()")
        m = re.search(r"!\[fig\]\(/_qwen/out/(fig-[\w.-]+\.png)\)", out)
        self.assertTrue(m, out)
        png = os.path.join(self.out_dir, m.group(1))
        with open(png, "rb") as fh:
            self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertNotIn("FigureCanvasAgg", out)
        # รูปถูกปิดหลังบันทึก — รันต่อไม่ได้รูปเดิมซ้ำ
        out = self.run_code("print('no figs')")
        self.assertNotIn("/_qwen/out/fig-", out)

    def test_4_new_output_files_are_linked(self):
        out = self.run_code("import pandas as pd\n"
                            "pd.DataFrame({'a': [1, 2], 'b': ['ไทย', 'x']}).to_csv('../outputs/report.csv')\n"
                            "pd.DataFrame({'a': [1]}).to_csv('../outputs/รายงาน สถานี.csv')\n"
                            "open('../outputs/.hidden', 'w').write('x')\n"
                            "pd.DataFrame({'a': [1, 2]})")
        self.assertIn("[report.csv](/_qwen/out/report.csv)", out)
        import urllib.parse
        self.assertIn("[รายงาน สถานี.csv](/_qwen/out/%s)" % urllib.parse.quote("รายงาน สถานี.csv"), out)
        self.assertNotIn(".hidden", out)
        self.assertIn("[ผลลัพธ์]", out)

    def test_5_error_is_reported_and_kernel_survives(self):
        out = self.run_code("1/0")
        self.assertIn("[error] ZeroDivisionError", out)
        self.assertNotIn("\x1b[", out)
        out = self.run_code("print('still', x)")
        self.assertIn("still 41", out)

    def test_6_timeout_interrupts_busy_loop(self):
        t0 = time.time()
        out = self.run_code("while True:\n    pass", timeout=5)
        self.assertIn("หมดเวลา", out)
        self.assertLess(time.time() - t0, 60)
        # ค่ามิลลิวินาทีจากโมเดล ("5000") ต้องถึง runner เป็น 5 วินาทีจริง — ของเดิมหนีบเป็น 240 (ค้าง 4 นาที)
        t0 = time.time()
        out = self.run_code("while True:\n    pass", timeout="5000")
        self.assertIn("หมดเวลา", out)
        self.assertIn("(5 วินาที)", out)
        self.assertIn("มิลลิวินาที", out, "ผลลัพธ์ต้องบอกว่าตีความหน่วยอย่างไร")
        self.assertLess(time.time() - t0, 60)
        out = self.run_code("print('after', 1)")
        self.assertIn("after 1", out)

    def test_6b_kernel_exit_is_survived(self):
        out = self.run_code("import os\nos._exit(3)", timeout=30)
        self.assertIn("kernel หยุดทำงาน", out)
        self.assertIn("รีสตาร์ต kernel แล้ว", out)
        out = self.run_code("print('alive again', 'x' in globals())")
        self.assertIn("alive again False", out)

    def test_7_plotly_becomes_png_or_html(self):
        out = self.run_code("import plotly.express as px\n"
                            "px.bar(x=['ก', 'ข'], y=[1, 3], title='plotly').show()", timeout=90)
        m = re.search(r"/_qwen/out/(fig-[\w.-]+\.(png|html))", out)
        self.assertTrue(m, out)
        self.assertTrue(os.path.isfile(os.path.join(self.out_dir, m.group(1))))

    def test_8_output_scrubbed_of_service_token(self):
        # ค่า token ทดสอบ (ในโปรเซสนี้คือ token ของบริการ) ห้ามหลุดกลับมาในผล แม้โค้ดจะพิมพ์ออกมาเอง
        code = "print('T=' + %r)" % C.TOKEN
        out = self.run_code(code)
        self.assertNotIn(C.TOKEN, out)

    def test_9_idle_reap_and_parent_death(self):
        k = tools_python._KERNELS[self.slug]
        self.assertTrue(k.alive())
        kernel_pid = k.info.get("pid")
        self.assertTrue(_pid_alive(kernel_pid))
        # (ก) ว่างเกินกำหนด -> ตัวเก็บกวาดปิดทั้ง runner และ kernel แล้วครั้งหน้าเปิดใหม่
        k.last_used -= tools_python.IDLE_SECONDS + 5
        self.assertIn(self.slug, tools_python.reap_idle())
        self.assertFalse(k.alive())
        self.assertTrue(_wait_gone(kernel_pid), "kernel ต้องถูกปิดด้วย")
        out = self.run_code("print('fresh', 'x' in globals())")
        self.assertIn("เปิด kernel ใหม่", out)
        self.assertIn("fresh False", out)
        # (ข) runner ถูก kill กะทันหัน -> kernel จบตามเอง (JPY_PARENT_PID) ไม่ค้างเป็นกำพร้า
        kernel_pid = k.info.get("pid")
        k.proc.kill()
        k.proc.wait(10)
        self.assertTrue(_wait_gone(kernel_pid), "kernel กำพร้าต้องจบเอง")
        out = self.run_code("print('after kill')")
        self.assertIn("เปิด kernel ใหม่", out)
        self.assertIn("after kill", out)


def _pid_alive(pid) -> bool:
    """ตรวจว่าโปรเซสยังอยู่ (ห้ามใช้ os.kill(pid, 0) บน Windows — มันคือ TerminateProcess)"""
    import ctypes
    if not pid:
        return False
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, int(pid))        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
            return False
        return code.value == 259                        # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def _wait_gone(pid, timeout=30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.5)
    return False


if __name__ == "__main__":
    unittest.main()
