# -*- coding: utf-8 -*-
"""
เทสต์ตัวเปิด/ตัวปิดของ batch 2a สัญญา B5 (owner stack): บริการ embedding พอร์ต 8093 (สัญญา B2)

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v
      LLM_STACK_LIVE=1 ... = รันตัวเปิดจริงบนพอร์ตทดสอบ (router 8199 + embedding LLM_STACK_LIVE_EMBED_PORT ปกติ 8893)
                             ด้วยโทเคนชั่วคราว แล้วปิดเฉพาะ llama-server บนสองพอร์ตนั้น (ไม่แตะบริการจริง)

วิธีเดียวกับ test_launcher_security: ตัวเปิดรันทุกอย่างตอนโหลด จึงใช้ parser ของ PowerShell 5.1 ดึงเฉพาะฟังก์ชันจาก
ไฟล์จริงมารันแยกพร้อมตัวแปรทดสอบ + Get-CimInstance/Get-PortPid ปลอม — ไม่มีโค้ดระดับบนสุดของตัวเปิดถูกรัน
สิ่งที่ตรวจ
  * Get-EmbedArgs: ค่าตามสัญญา (--embeddings --pooling last -ngl 0 -c 8192 -t 4 127.0.0.1) + CPU ล้วน (--device none)
    + ปิด /slots, WebUI, เน็ต + CORS จำกัด + --api-key-file เป็น path (ไม่มีทางส่งค่าคีย์ทาง command line)
  * Get-EmbedHealth: 200 = ok, 503 = loading (กำลังโหลดโมเดล), ต่อไม่ติด = down
  * Get-EmbedState: โปรแกรมอื่น/llama-server ที่ไม่ใช่โหมด embedding = ไม่ใช่ของเรา (ห้ามปิด), ค่าความปลอดภัยแบบเก่า
    หรือโทเคนชุดเก่า (401) = ต้องเปิดใหม่, ค่าปัจจุบันครบ + รับโทเคน = ใช้ต่อ
  * โครงของสคริปต์: ขั้น 1d อยู่ก่อนขั้น GPU, รอบทดสอบ (-Port อื่น) ข้ามถ้าไม่ใส่ -EmbedPort, เปิดผ่าน Start-CleanProcess
    (WMI env สะอาด), รายงานความพร้อมก่อนบรรทัด "[4/4] llama-server พร้อม" (hub แสดงแค่บรรทัดท้าย) และไม่แตะ exit code
  * -EmbedOnly จบก่อนแตะ MCP/router และไม่ถาม Read-Host (สด: ไม่เปิด router ทดสอบเลย แล้วตัวเปิดเต็มใช้ตัวเดิมต่อ)
  * stop-qwen38.ps1 ปิดพอร์ต 8093 เฉพาะเมื่อเป็น llama-server.exe, ยังเป็น UTF-8 BOM + LF และ parse ได้
"""
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LAUNCHER = r"C:\LLM\start-qwen38.ps1"
STOPPER = r"C:\LLM\stop-qwen38.ps1"
POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                          r"System32\WindowsPowerShell\v1.0\powershell.exe")

HARNESS = r"""
param([string]$ScenarioFile)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('__LAUNCHER__', [ref]$tokens, [ref]$errs)
$want = @('Get-EmbedArgs', 'Get-EmbedHealth', 'Get-EmbedState', 'Test-RouterAuth', 'Test-TokenFileStrict', 'Format-Arg')
$defs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
$found = @()
foreach ($d in $defs) { if ($want -contains $d.Name) { . ([scriptblock]::Create($d.Extent.Text)); $found += $d.Name } }
$scen = Get-Content -LiteralPath $ScenarioFile -Raw -Encoding UTF8 | ConvertFrom-Json
$EmbedModel = 'D:\LLM\models-embed\Qwen3-Embedding-0.6B-Q8_0.gguf'
$TokenFile = [string]$scen.token_file
$EmbedPort = [int]$scen.auth_port
$script:FakeName = ''; $script:FakeCmd = ''
function Get-PortPid([int]$p) { return 4242 }
function Get-CimInstance { [pscustomobject]@{ Name = $script:FakeName; CommandLine = $script:FakeCmd } }
$out = [ordered]@{ found = $found; parse_errors = $errs.Count }
# แบบเดียวกับตัวเปิด: ฟังก์ชันคืน ,array (ก้อนเดียว) — กำหนดค่าก่อนแล้วค่อยไล่ (pipe ตรงๆ จะได้ array ทั้งก้อนเป็นหนึ่งค่า)
$ea = Get-EmbedArgs
$out.args = @($ea | ForEach-Object { [string]$_ })
$out.health = [ordered]@{}
foreach ($p in $scen.health_ports.PSObject.Properties) { $out.health[$p.Name] = [string](Get-EmbedHealth ([int]$p.Value)) }
$out.states = @()
foreach ($c in $scen.state_cases) {
    $script:FakeName = [string]$c.name; $script:FakeCmd = [string]$c.cmd
    $s = Get-EmbedState $EmbedPort
    $out.states += [ordered]@{ case = [string]$c.case; ours = [bool]$s.Ours; why = [string]$s.Why; pid = [int]$s.Pid }
}
$out | ConvertTo-Json -Depth 5 -Compress
"""


class _Health(BaseHTTPRequestHandler):
    code = 200

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = b'{"status":"ok"}' if type(self).code == 200 else b'{"error":{"code":503}}'
        self.send_response(type(self).code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Auth(BaseHTTPRequestHandler):
    """llama-server --api-key-file ปลอม: /v1/models 200 เฉพาะ Bearer ที่ถูก ไม่งั้น 401"""
    good = ""

    def log_message(self, *a):
        pass

    def do_GET(self):
        ok = self.path == "/v1/models" and (self.headers.get("Authorization") or "") == "Bearer " + type(self).good
        body = b'{"data":[]}' if ok else b'{"error":{"code":401}}'
        self.send_response(200 if ok else 401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


GOOD_CMD = ('"C:\\LLM\\llama.cpp-b10984\\llama-server.exe" --embeddings --pooling last -m D:\\LLM\\models-embed\\x.gguf '
            '-ngl 0 --device none -c 8192 -t 4 --host 127.0.0.1 --port 8093 --no-webui --no-slots --offline '
            '--cors-origins http://127.0.0.1:8093 --no-cors-credentials --api-key-file C:\\t\\tok')


@unittest.skipUnless(os.path.isfile(POWERSHELL), "ไม่มี Windows PowerShell 5.1")
class EmbedFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="stackb2-launch-")
        cls.token = secrets.token_hex(32)                   # ค่าทดสอบ ไม่ใช่โทเคนจริง
        tok = os.path.join(cls.tmp, "tok token.txt")        # มีช่องว่างใน path — Format-Arg ต้องครอบ ""
        with open(tok, "w", newline="\n") as fh:
            fh.write(cls.token + "\n")
        ok_cls = type("H200", (_Health,), {"code": 200})
        busy_cls = type("H503", (_Health,), {"code": 503})
        auth_cls = type("Auth", (_Auth,), {"good": cls.token})
        cls.srvs = [_serve(ok_cls), _serve(busy_cls), _serve(auth_cls)]
        auth_port = cls.srvs[2].server_address[1]
        stale_port_auth = auth_port
        scen = {
            "token_file": tok, "auth_port": stale_port_auth,
            "health_ports": {"ok": cls.srvs[0].server_address[1], "loading": cls.srvs[1].server_address[1],
                             "down": _free_port()},
            "state_cases": [
                {"case": "other_program", "name": "python.exe", "cmd": "python.exe -m http.server 8093"},
                {"case": "llama_not_embed", "name": "llama-server.exe",
                 "cmd": '"C:\\LLM\\llama.cpp-b10984\\llama-server.exe" --models-dir C:\\LLM\\models --port 8093'},
                {"case": "no_key", "name": "llama-server.exe", "cmd": GOOD_CMD.replace(" --api-key-file C:\\t\\tok", "")},
                {"case": "wide_cors", "name": "llama-server.exe",
                 "cmd": GOOD_CMD.replace(" --cors-origins http://127.0.0.1:8093 --no-cors-credentials", "")},
                {"case": "slots_open", "name": "llama-server.exe", "cmd": GOOD_CMD.replace(" --no-slots", "")},
                {"case": "current", "name": "llama-server.exe", "cmd": GOOD_CMD},
            ],
        }
        scen_path = os.path.join(cls.tmp, "scen.json")
        with open(scen_path, "w", encoding="utf-8") as fh:
            json.dump(scen, fh)
        harness = os.path.join(cls.tmp, "harness.ps1")
        with open(harness, "w", encoding="utf-8-sig") as fh:
            fh.write(HARNESS.replace("__LAUNCHER__", LAUNCHER))
        r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", harness,
                            "-ScenarioFile", scen_path], capture_output=True, timeout=180)
        cls.stderr = r.stderr.decode("utf-8", "replace")
        out = r.stdout.decode("utf-8", "replace").strip().splitlines()
        cls.res = json.loads(out[-1]) if out else {}
        cls.tok = tok

        # โทเคนชุดใหม่ในไฟล์ (router/embedding ยังจำชุดเก่า) — router ปลอมตัวเดิมรับแค่ชุดเก่า = 401
        with open(tok, "w", newline="\n") as fh:
            fh.write(secrets.token_hex(32) + "\n")
        scen["state_cases"] = [{"case": "old_token", "name": "llama-server.exe", "cmd": GOOD_CMD}]
        with open(scen_path, "w", encoding="utf-8") as fh:
            json.dump(scen, fh)
        r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", harness,
                            "-ScenarioFile", scen_path], capture_output=True, timeout=180)
        out = r.stdout.decode("utf-8", "replace").strip().splitlines()
        cls.res_old = json.loads(out[-1]) if out else {}

    @classmethod
    def tearDownClass(cls):
        for s in cls.srvs:
            s.shutdown()
            s.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_functions_extracted_from_real_launcher(self):
        self.assertEqual(self.res.get("parse_errors"), 0, self.stderr[-2000:])
        self.assertEqual(sorted(self.res["found"]), sorted(['Get-EmbedArgs', 'Get-EmbedHealth', 'Get-EmbedState',
                                                             'Test-RouterAuth', 'Test-TokenFileStrict', 'Format-Arg']))

    def test_embed_args_follow_contract_and_are_locked_down(self):
        a = self.res["args"]
        s = " ".join(a)

        def after(flag):
            return a[a.index(flag) + 1]
        self.assertIn("--embeddings", a)
        self.assertEqual(after("--pooling"), "last")
        self.assertEqual(after("-m"), r"D:\LLM\models-embed\Qwen3-Embedding-0.6B-Q8_0.gguf")
        self.assertEqual((after("-ngl"), after("--device"), after("-c"), after("-t")), ("0", "none", "8192", "4"))
        self.assertEqual(after("--host"), "127.0.0.1")
        self.assertEqual(after("--port"), str(self.res_port()))
        for f in ("--no-webui", "--no-slots", "--offline", "--no-cors-credentials"):
            self.assertIn(f, a)
        self.assertEqual(after("--cors-origins"), "http://127.0.0.1:%d" % self.res_port())
        self.assertEqual(after("--api-key-file"), self.tok)
        self.assertNotIn("--api-key", a, "ค่าคีย์ห้ามอยู่บน command line")
        self.assertNotIn(self.token, s)
        self.assertNotIn("0.0.0.0", s)

    def res_port(self):
        return int(self.res["args"][self.res["args"].index("--port") + 1])

    def test_health_states(self):
        self.assertEqual(self.res["health"], {"ok": "ok", "loading": "loading", "down": "down"})

    def test_state_decisions(self):
        st = {x["case"]: x for x in self.res["states"]}
        self.assertFalse(st["other_program"]["ours"], "โปรแกรมอื่นบนพอร์ตนี้ห้ามถูกปิด")
        self.assertFalse(st["llama_not_embed"]["ours"], "llama-server ที่ไม่ใช่โหมด embedding ห้ามถูกปิด")
        for case in ("no_key", "wide_cors", "slots_open"):
            self.assertTrue(st[case]["ours"], case)
            self.assertTrue(st[case]["why"], case)
        self.assertTrue(st["current"]["ours"])
        self.assertEqual(st["current"]["why"], "", "ค่าปัจจุบันครบ + รับโทเคน = ใช้ต่อ ไม่เปิดใหม่")
        self.assertEqual(st["current"]["pid"], 4242)
        old = self.res_old["states"][0]
        self.assertTrue(old["ours"])
        self.assertIn("โทเคนชุดเก่า", old["why"])


class LauncherStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = _read(LAUNCHER)
        cls.raw = raw
        cls.text = raw.decode("utf-8-sig").replace("\r\n", "\n")

    def test_encoding_bom_crlf(self):
        self.assertTrue(self.raw.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(self.raw.count(b"\n"), self.raw.count(b"\r\n"))

    def test_parameters(self):
        head = self.text[self.text.index("param("):self.text.index("$ErrorActionPreference")]
        self.assertRegex(head, r"\[int\]\$EmbedPort\s*=\s*8093")
        self.assertIn("[switch]$NoEmbed", head)
        self.assertIn("[switch]$RestartEmbed", head)       # batch 2a (fix) — ดู test_stack_b2_fix.RestartEmbedTests

    def test_step_order_and_guards(self):
        t = self.text
        step = t.index("# ---- 1d. บริการ embedding")
        self.assertLess(step, t.index("# ---- 2. ตรวจ GPU + llama-server"))
        self.assertIn("$EmbedH = (Invoke-EmbedStep).H", t[step:t.index("# ---- 2. ตรวจ GPU + llama-server")])
        fn = t[t.index("function Invoke-EmbedStep"):t.index("function Show-EmbedReady")]
        # รอบทดสอบบนพอร์ตอื่นต้องไม่ไปเปิด/ปิดตัวจริงที่ 8093
        self.assertIn("$Port -ne $MainPort -and -not $EmbedPortGiven", fn)
        self.assertIn("Test-TokenFileStrict", fn, "ไม่มีโทเคนที่ใช้เป็นคีย์ได้ = ไม่เปิดแบบไม่มีคีย์")
        self.assertIn("-not $es.Ours", fn)
        self.assertNotIn("Set-Outcome", fn, "embedding ไม่มีผลกับ exit code ของงานเลือก GPU")
        ready = t.index("$embedState = Show-EmbedReady $EmbedH")
        self.assertLess(ready, t.index("if ($ready -and $NonInteractive)"))
        # -EmbedOnly จบก่อนแตะ MCP (ขั้น 1) และ router (ขั้น 2) และไม่ถาม Read-Host (ถือเป็น -NonInteractive)
        eo = t.index("if ($EmbedOnly) {\n    $eo = Invoke-EmbedStep")
        self.assertLess(eo, t.index("# ---- 1. MCP server"))
        self.assertLess(eo, t.index("$genOk = New-GpuProfile $GenDir"))
        self.assertIn("if ($EmbedOnly) { $NonInteractive = $true }", t)
        start_fn = t[t.index("function Start-Embed"):t.index("function Wait-EmbedReady")]
        self.assertIn("Start-CleanProcess", start_fn, "ต้องเปิดผ่าน WMI (env สะอาด) เหมือนบริการอื่น")
        self.assertIn("$EmbedLogName", start_fn)
        self.assertIn("$EmbedLogName = 'embed'", t)

    def test_hub_markers_not_used_in_embed_lines(self):
        # hub อ่านบรรทัดท้ายของ log งานเลือก GPU: สองวลีนี้มีความหมายพิเศษ ห้ามโผล่ในข้อความของขั้น embedding
        embed_lines = [ln for ln in self.text.split("\n") if "embedding" in ln and "Write-Host" in ln]
        self.assertTrue(embed_lines)
        for ln in embed_lines:
            self.assertNotIn("กำลังรอให้แชตที่ตอบอยู่เสร็จ", ln)
            self.assertNotIn("ไม่ต้องรีสตาร์ต", ln)
            self.assertNotIn("ผลลัพธ์:", ln)


class StopScriptTests(unittest.TestCase):
    def test_stop_script(self):
        raw = _read(STOPPER)
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r\n", raw, "ไฟล์นี้เป็น LF มาตลอด — คงไว้")
        t = raw.decode("utf-8-sig")
        self.assertRegex(t, r"\$EmbedPort\s*=\s*8093")
        self.assertRegex(t, r"Stop-ByPort \$EmbedPort\s+'[^']+'\s+@\('llama-server\.exe'\)")

    @unittest.skipUnless(os.path.isfile(POWERSHELL), "ไม่มี Windows PowerShell 5.1")
    def test_scripts_parse_in_ps51(self):
        for f in (STOPPER, LAUNCHER):
            r = subprocess.run([POWERSHELL, "-NoProfile", "-Command",
                                "$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('%s',"
                                "[ref]$t,[ref]$e);$e.Count" % f], capture_output=True, timeout=120)
            self.assertEqual(r.stdout.decode().strip(), "0", f)


# ---------------------------------------------------------------- สด (ต้องตั้ง LLM_STACK_LIVE=1)
@unittest.skipUnless(os.environ.get("LLM_STACK_LIVE") == "1" and os.path.isfile(POWERSHELL),
                     "ตั้ง LLM_STACK_LIVE=1 เพื่อรันตัวเปิดจริงบนพอร์ตทดสอบ")
class LiveLauncherTests(unittest.TestCase):
    ROUTER = 8199

    @classmethod
    def setUpClass(cls):
        cls.embed = int(os.environ.get("LLM_STACK_LIVE_EMBED_PORT") or 8893)
        for p in (cls.ROUTER, cls.embed):
            s = socket.socket()
            busy = s.connect_ex(("127.0.0.1", p)) == 0
            s.close()
            if busy:
                raise unittest.SkipTest("พอร์ต %d มีโปรแกรมอื่นใช้อยู่ (เอเจนต์/เทสต์อื่น?)" % p)
        cls.tmp = tempfile.mkdtemp(prefix="stackb2-live-")
        cls.tok = os.path.join(cls.tmp, "test.token")
        with open(cls.tok, "w", newline="\n") as fh:
            fh.write(secrets.token_hex(32) + "\n")

    @classmethod
    def tearDownClass(cls):
        # ปิดเฉพาะ llama-server ที่ฟังพอร์ตทดสอบสองพอร์ตนี้ (router ทดสอบไม่มีโมเดลลูก เพราะไม่มีใครขอ)
        ps = ("foreach ($p in %d,%d) { $c = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue"
              " | Select-Object -First 1; if ($c) { $x = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue;"
              " if ($x -and $x.ProcessName -eq 'llama-server') { Stop-Process -Id $x.Id -Force } } }" % (cls.ROUTER, cls.embed))
        subprocess.run([POWERSHELL, "-NoProfile", "-Command", ps], capture_output=True, timeout=60)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_launcher(self, *extra):
        env = dict(os.environ, LLM_LOCAL_TOKEN_FILE=self.tok)
        r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", LAUNCHER,
                            "-Port", str(self.ROUTER), "-EmbedPort", str(self.embed), "-NoBrowser"] + list(extra),
                           capture_output=True, timeout=600, env=env)
        return r.returncode, r.stdout.decode("utf-8", "replace")

    def listening(self, port):
        s = socket.socket()
        try:
            return s.connect_ex(("127.0.0.1", port)) == 0
        finally:
            s.close()

    def test_embed_only_then_full_launcher_reuses_it(self):
        # 1) -EmbedOnly: เปิดเฉพาะ embedding — router ทดสอบต้องไม่ถูกเปิด
        rc, out = self.run_launcher("-EmbedOnly")
        self.assertEqual(rc, 0, out[-3000:])
        self.assertIn("บริการ embedding: กำลังเปิด (พอร์ต %d" % self.embed, out)
        self.assertIn("[4/4] บริการ embedding พร้อม (พอร์ต %d)" % self.embed, out)
        self.assertFalse(self.listening(self.ROUTER), "-EmbedOnly ต้องไม่แตะ router")
        rc, out = self.run_launcher("-EmbedOnly")
        self.assertEqual(rc, 0, out[-3000:])
        self.assertIn("บริการ embedding: เปิดอยู่แล้ว (พอร์ต %d)" % self.embed, out)
        # 2) ตัวเปิดเต็ม (-NonInteractive แบบที่ hub เรียก): ใช้ embedding ตัวเดิม บรรทัดสุดท้ายยังเป็นผลลัพธ์ของงาน GPU
        rc, out = self.run_launcher("-NonInteractive")
        self.assertEqual(rc, 0, out[-3000:])
        self.assertIn("บริการ embedding: เปิดอยู่แล้ว (พอร์ต %d)" % self.embed, out)
        lines = [ln for ln in out.splitlines() if ln.strip()]
        self.assertTrue(lines[-1].strip().startswith("ผลลัพธ์:"), "บรรทัดสุดท้ายต้องเป็นผลลัพธ์ของงานเลือก GPU")


if __name__ == "__main__":
    unittest.main()
