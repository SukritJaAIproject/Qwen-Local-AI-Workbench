# -*- coding: utf-8 -*-
"""
เทสต์ตัวเปิด/ตัวปิดของ batch 2b สัญญา C3 (owner stack): บริการแปลงเสียงเป็นข้อความ (STT) พอร์ต 8795 (สัญญา C1)

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v
      LLM_STACK_LIVE=1 ... = รัน "ตัวเปิด -SttOnly" จริงบนพอร์ตทดสอบ (LLM_STACK_LIVE_STT_PORT ปกติ 8896) ด้วยโทเคนชั่วคราว
                             เมื่อมี C:\\LLM\\stt\\stt_server.py แล้ว — ปิดเฉพาะ python ที่ฟังพอร์ตนั้นตอนจบ (ไม่แตะบริการจริง)

วิธีเดียวกับ test_stack_b2_launcher: ใช้ parser ของ PowerShell 5.1 ดึงเฉพาะฟังก์ชันจากไฟล์จริงมารันพร้อมตัวแปรทดสอบ +
Test-Port / Get-CimInstance / Stop-Process / Start-CleanProcess ปลอม — ไม่มีโค้ดระดับบนสุดของตัวเปิดถูกรัน ไม่มีโปรเซสจริงถูกเปิด/ปิด
สิ่งที่ตรวจ
  * Get-SttArgs = สคริปต์ของ owner voice + --port <พอร์ต> (ไม่มีโทเคนบน command line), Get-SttEnv = HF_HUB_OFFLINE=1
    (ไม่ออกเน็ต) + CUDA_DEVICE_ORDER + PYTHONIOENCODING ไม่มีตัวแปรลับ
  * Get-SttHealth: 200 ok / 503 loading / 401 auth / ต่อไม่ติด down — แนบ Bearer จากไฟล์โทเคน
  * Invoke-SttStep: -NoStt / รอบทดสอบพอร์ตอื่น / ไม่มีสคริปต์ = ข้าม, ไม่มี python ของ flexxfast / ไม่มีโทเคน = ไม่เปิด,
    พอร์ตว่าง = เปิดผ่าน Start-CleanProcess (WMI env สะอาด) ด้วย python ของ flexxfast + log stt, ตัวของเราที่ปกติดี = ใช้ต่อ,
    โปรแกรมอื่นบนพอร์ต = ไม่แตะ, โทเคนชุดเก่า (401) หรือ -RestartStt = ปิดเฉพาะ PID นั้นแล้วเปิดใหม่
  * โครงของสคริปต์: ขั้น 1e หลัง 1d ก่อนขั้น GPU, ไม่ทำในโหมด -NonInteractive, รายงานความพร้อมก่อน "[4/4] llama-server พร้อม",
    -SttOnly/-RestartStt จบก่อนแตะ MCP/router, ไม่มีผลกับ exit code ของงานเลือก GPU
  * stop-qwen38.ps1 ปิดพอร์ต 8795 เฉพาะเมื่อเป็น python.exe, ยังเป็น UTF-8 BOM + LF และ parse ได้; ตัวเปิดยัง BOM + CRLF
"""
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
import urllib.request
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
$want = @('Get-SttPython', 'Get-SttArgs', 'Get-SttEnv', 'Get-SttHealth', 'Get-SttState', 'Stop-Stt', 'Start-Stt',
          'Invoke-SttStep', 'Test-TokenFileStrict', 'Test-RouterAuth', 'Format-Arg')
$defs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
$found = @()
foreach ($d in $defs) { if ($want -contains $d.Name) { . ([scriptblock]::Create($d.Extent.Text)); $found += $d.Name } }
$scen = Get-Content -LiteralPath $ScenarioFile -Raw -Encoding UTF8 | ConvertFrom-Json
$MainPort = 8099
$LogDir = [string]$scen.log_dir
$SttLogName = 'stt'
$TokenFile = [string]$scen.token_file
$SttScript = [string]$scen.script
$SttPort = 8795
$realPy = Get-SttPython
# ---- ของปลอม (ประกาศทีหลัง = ทับของจริง)
$script:Calls = @(); $script:Stops = @(); $script:PortBusy = $false; $script:Stopped = $false
$script:FakeName = ''; $script:FakeCmd = ''; $script:PyPath = ''
function Get-SttPython { return $script:PyPath }
function Test-Port([int]$p) { return ($script:PortBusy -and -not $script:Stopped) }
function Get-PortPid([int]$p) { return 4242 }
function Get-CimInstance { [pscustomobject]@{ Name = $script:FakeName; CommandLine = $script:FakeCmd } }
function Stop-Process { [CmdletBinding()] param([int]$Id, [switch]$Force) $script:Stops += $Id; $script:Stopped = $true }
function Start-CleanProcess([string]$Exe, [object[]]$ArgList, [string]$WorkDir, [string]$OutLog, [string]$ErrLog,
                            [hashtable]$ChildEnv) {
    $envOut = [ordered]@{}
    foreach ($k in $ChildEnv.Keys) { $envOut[$k] = [string]$ChildEnv[$k] }
    $script:Calls += ,([ordered]@{ exe = $Exe; args = @($ArgList | ForEach-Object { [string]$_ }); wd = $WorkDir
                                   out = $OutLog; err = $ErrLog; env = $envOut })
    return @{ Pid = 1; Proc = $null; Wmi = $true }
}
function Write-Host { }
$out = [ordered]@{ found = $found; parse_errors = $errs.Count; real_py = [string]$realPy }
$sa = Get-SttArgs
$out.args = @($sa | ForEach-Object { [string]$_ })
$e = Get-SttEnv
$out.env = [ordered]@{}
foreach ($k in $e.Keys) { $out.env[$k] = [string]$e[$k] }
$out.health = [ordered]@{}
foreach ($p in $scen.health_ports.PSObject.Properties) { $out.health[$p.Name] = [string](Get-SttHealth ([int]$p.Value)) }
$out.cases = @()
foreach ($c in $scen.cases) {
    $script:Calls = @(); $script:Stops = @(); $script:Stopped = $false
    $NoStt = [bool]$c.no_stt; $RestartStt = [bool]$c.restart; $Port = [int]$c.port; $SttPortGiven = [bool]$c.port_given
    $SttScript = [string]$c.script; $SttPort = [int]$c.stt_port; $TokenFile = [string]$c.token_file
    $script:PyPath = [string]$c.py; $script:PortBusy = [bool]$c.busy
    $script:FakeName = [string]$c.name; $script:FakeCmd = [string]$c.cmd
    $r = Invoke-SttStep
    $out.cases += [ordered]@{ case = [string]$c.case; state = [string]$r.State; has_h = [bool]$r.H
                              calls = @($script:Calls); stops = @($script:Stops) }
}
$out | ConvertTo-Json -Depth 8 -Compress
"""


class _Stt(BaseHTTPRequestHandler):
    """stt_server.py ปลอม: /health ไม่ต้องใช้โทเคน ตอบ code + {"server":"qwen-stt","state":...}
    /v1/status ต้องใช้โทเคน — 200 เฉพาะ Bearer ที่ตรงกับ good ไม่งั้น 401 (โทเคนชุดเก่า)"""
    code = 200
    state = "ready"
    good = ""
    seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        auth = self.headers.get("Authorization") or ""
        type(self).seen.append((self.path, auth))
        if self.path == "/v1/status":
            ok = auth == "Bearer " + type(self).good
            code, body = (200, b'{"model":"large-v3-turbo"}') if ok else (401, b'{"error":"unauthorized"}')
        else:
            code = type(self).code
            body = json.dumps({"status": "ok", "server": "qwen-stt", "state": type(self).state}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(state, good, code=200):
    cls = type("S_%s" % state, (_Stt,), {"code": code, "state": state, "good": good, "seen": []})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), cls)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, cls


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


OURS_CMD = '"C:\\Users\\demo\\anaconda3\\envs\\flexxfast\\python.exe" C:\\LLM\\stt\\stt_server.py --port 8795'


@unittest.skipUnless(os.path.isfile(POWERSHELL), "ไม่มี Windows PowerShell 5.1")
class SttFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="stackb2b-launch-")
        cls.token = secrets.token_hex(32)                   # ค่าทดสอบ ไม่ใช่โทเคนจริง
        cls.tokfile = os.path.join(cls.tmp, "tok token.txt")
        with open(cls.tokfile, "w", newline="\n") as fh:
            fh.write(cls.token + "\n")
        bad_tok = os.path.join(cls.tmp, "bad.token")
        with open(bad_tok, "w", encoding="utf-8-sig") as fh:  # มี BOM = ใช้เป็นคีย์ไม่ได้
            fh.write(cls.token)
        cls.script = os.path.join(cls.tmp, "stt dir", "stt_server.py")
        os.makedirs(os.path.dirname(cls.script))
        with open(cls.script, "w") as fh:
            fh.write("# stub\n")
        cls.py = os.path.join(cls.tmp, "flexxfast", "python.exe")
        cls.srvs = {name: _serve(state, cls.token, code) for name, state, code in (
            ("ready", "ready", 200), ("idle", "idle", 200), ("loading", "loading", 200),
            ("nomodel", "no_model", 200), ("error", "error", 200), ("h503", "loading", 503))}
        cls.srvs["stale"] = _serve("ready", secrets.token_hex(32))     # บริการจำโทเคนชุดอื่น = /v1/status 401
        ok_port = cls.srvs["ready"][0].server_address[1]
        stale_port = cls.srvs["stale"][0].server_address[1]
        base = {"no_stt": False, "restart": False, "port": 8099, "port_given": False, "script": cls.script,
                "stt_port": ok_port, "token_file": cls.tokfile, "py": cls.py, "busy": False, "name": "", "cmd": ""}

        def case(label, **over):
            d = dict(base, case=label)
            d.update(over)
            return d
        scen = {
            "log_dir": os.path.join(cls.tmp, "logs"), "token_file": cls.tokfile, "script": cls.script,
            "health_ports": dict({n: s.server_address[1] for n, (s, _c) in cls.srvs.items() if n != "stale"},
                                 down=_free_port()),
            "cases": [
                case("no_stt", no_stt=True),
                case("test_port", port=8199),
                case("test_port_given", port=8199, port_given=True),
                case("no_script", script=os.path.join(cls.tmp, "missing.py")),
                case("no_python", py=""),
                case("no_token", token_file=bad_tok),
                case("fresh"),
                case("running_ours", busy=True, name="python.exe", cmd=OURS_CMD),
                case("foreign", busy=True, name="node.exe", cmd="node server.js 8795"),
                case("python_not_stt", busy=True, name="python.exe", cmd="python -m http.server 8795"),
                case("stale_token", busy=True, name="python.exe", cmd=OURS_CMD, stt_port=stale_port),
                case("restart", busy=True, name="python.exe", cmd=OURS_CMD, restart=True),
                case("restart_foreign", busy=True, name="node.exe", cmd="node x", restart=True),
            ],
        }
        scen_path = os.path.join(cls.tmp, "scen.json")
        with open(scen_path, "w", encoding="utf-8") as fh:
            json.dump(scen, fh)
        harness = os.path.join(cls.tmp, "harness.ps1")
        with open(harness, "w", encoding="utf-8-sig") as fh:
            fh.write(HARNESS.replace("__LAUNCHER__", LAUNCHER))
        r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", harness,
                            "-ScenarioFile", scen_path], capture_output=True, timeout=240)
        cls.stderr = r.stderr.decode("utf-8", "replace")
        out = r.stdout.decode("utf-8", "replace").strip().splitlines()
        cls.res = json.loads(out[-1]) if out else {}
        cls.cases = {c["case"]: c for c in cls.res.get("cases", [])}

    @classmethod
    def tearDownClass(cls):
        for srv, _c in cls.srvs.values():
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_functions_extracted_from_real_launcher(self):
        self.assertEqual(self.res.get("parse_errors"), 0, self.stderr[-2000:])
        self.assertEqual(sorted(self.res["found"]), sorted([
            'Get-SttPython', 'Get-SttArgs', 'Get-SttEnv', 'Get-SttHealth', 'Get-SttState', 'Stop-Stt', 'Start-Stt',
            'Invoke-SttStep', 'Test-TokenFileStrict', 'Test-RouterAuth', 'Format-Arg']))

    def test_real_python_finder_points_at_flexxfast(self):
        py = self.res["real_py"]
        if py:
            self.assertTrue(py.lower().endswith(r"\envs\flexxfast\python.exe"), py)

    def test_args_and_env(self):
        a = self.res["args"]
        # คำสั่งตามหัวไฟล์ stt_server.py ของ owner voice: python -X utf8 stt_server.py --port <พอร์ต>
        self.assertEqual(a, ["-X", "utf8", self.script, "--port", "8795"])
        self.assertNotIn(self.token, " ".join(a))
        env = self.res["env"]
        self.assertEqual(env.get("HF_HUB_OFFLINE"), "1", "ห้ามดาวน์โหลดโมเดล (สัญญา: ไม่มีเครือข่าย)")
        self.assertEqual(env.get("CUDA_DEVICE_ORDER"), "PCI_BUS_ID")
        self.assertEqual(env.get("PYTHONIOENCODING"), "utf-8")
        for k in env:
            self.assertNotRegex(k, r"(?i)secret|passw|api_?key|^claude|^anthropic", "ห้ามส่งตัวแปรลับ")

    def test_health_states_from_json_state(self):
        self.assertEqual(self.res["health"], {"ready": "ok", "idle": "ok", "loading": "loading", "nomodel": "nomodel",
                                              "error": "down", "h503": "loading", "down": "down"})

    def test_token_only_sent_to_status_endpoint(self):
        for name, (_s, cls) in self.srvs.items():
            for path, auth in cls.seen:
                if path == "/health":
                    self.assertEqual(auth, "", "%s: /health ไม่ต้องใช้โทเคน — ไม่ส่ง" % name)
                else:
                    self.assertEqual((path, auth), ("/v1/status", "Bearer " + self.token), name)
        self.assertIn(("/v1/status", "Bearer " + self.token), self.srvs["stale"][1].seen,
                      "ตรวจโทเคนชุดเก่าที่ /v1/status")

    def test_skip_and_fail_cases_start_nothing(self):
        want = {"no_stt": "skipped", "test_port": "skipped", "no_script": "skipped", "no_python": "failed",
                "no_token": "failed", "foreign": "foreign", "python_not_stt": "foreign", "restart_foreign": "foreign",
                "running_ours": "running"}
        for name, state in want.items():
            c = self.cases[name]
            self.assertEqual(c["state"], state, name)
            self.assertEqual(c["calls"], [], name)
            self.assertEqual(c["stops"], [], "%s: ห้ามปิดโปรเซสใด" % name)

    def test_fresh_start_uses_clean_process_with_flexxfast(self):
        for name in ("fresh", "test_port_given"):
            c = self.cases[name]
            self.assertEqual((c["state"], c["has_h"]), ("started", True), name)
            self.assertEqual(len(c["calls"]), 1)
            call = c["calls"][0]
            self.assertEqual(call["exe"], self.py)
            self.assertEqual(call["args"], ["-X", "utf8", self.script, "--port",
                                            str(self.srvs["ready"][0].server_address[1])])
            self.assertEqual(call["wd"], os.path.dirname(self.script))
            self.assertTrue(call["out"].endswith("\\stt.out.log") and call["err"].endswith("\\stt.err.log"))
            self.assertEqual(call["env"]["HF_HUB_OFFLINE"], "1")

    def test_stale_token_and_restart_replace_only_our_pid(self):
        for name in ("stale_token", "restart"):
            c = self.cases[name]
            self.assertEqual(c["state"], "started", name)
            self.assertEqual(c["stops"], [4242], name)
            self.assertEqual(len(c["calls"]), 1, name)


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
        self.assertRegex(head, r"\[int\]\$SttPort\s*=\s*8795")
        for sw in ("[switch]$NoStt", "[switch]$SttOnly", "[switch]$RestartStt", "[switch]$RestartEmbed,"):
            self.assertIn(sw, head)
        t = self.text
        self.assertIn("if ($RestartStt) { $SttOnly = $true }", t)
        self.assertIn("if ($SttOnly) { $NonInteractive = $true }", t)
        self.assertLess(t.index("if ($SttOnly) { $NonInteractive = $true }"), t.index("if ($NonInteractive) {\n"))

    def test_step_order_and_guards(self):
        t = self.text
        step = t.index("# ---- 1e. บริการแปลงเสียงเป็นข้อความ")
        self.assertLess(t.index("$EmbedH = (Invoke-EmbedStep).H"), step)
        self.assertLess(step, t.index("# ---- 2. ตรวจ GPU + llama-server"))
        self.assertIn("if (-not $NonInteractive) { $SttH = (Invoke-SttStep).H }", t)
        ready = t.index("if ($SttH) { $null = Show-SttReady $SttH 60 }")
        self.assertLess(ready, t.index("if ($ready -and $NonInteractive)"))
        so = t.index("if ($SttOnly) {\n    $so = Invoke-SttStep")
        self.assertLess(so, t.index("# ---- 1. MCP server"))
        self.assertLess(so, t.index("$genOk = New-GpuProfile $GenDir"))
        fn = t[t.index("function Invoke-SttStep"):t.index("New-Item -ItemType Directory -Force -Path $LogDir")]
        self.assertIn("$Port -ne $MainPort -and -not $SttPortGiven", fn)
        self.assertIn("Test-TokenFileStrict", fn)
        self.assertLess(fn.index("-not $ss.Ours"), fn.index("$RestartStt -and"), "สวิตช์เปิดใหม่ต้องอยู่หลังการตรวจว่าเป็นของเรา")
        self.assertNotIn("Set-Outcome", fn, "STT ไม่มีผลกับ exit code ของงานเลือก GPU")
        start_fn = t[t.index("function Start-Stt"):t.index("function Wait-SttReady")]
        self.assertIn("Start-CleanProcess", start_fn, "ต้องเปิดผ่าน WMI (env สะอาด) เหมือนบริการอื่น")

    def test_unattended_full_start_never_prompts(self):
        """fixer 2026-10-06: หลังรีบูต "-NoBrowser -NonInteractive" ขึ้นแค่ router + embedding (โหมดนั้นข้าม MCP/hub/STT โดยตั้งใจ)
        -Unattended = เปิดครบชุดเหมือนไอคอน แต่ไม่มี Read-Host / เบราว์เซอร์ และจบด้วย exit code"""
        t = self.text
        head = t[t.index("param("):t.index("$ErrorActionPreference")]
        self.assertIn("[switch]$Unattended", head)
        blk = t[t.index("if ($Unattended -and -not $NonInteractive) {"):]
        blk = blk[:blk.index("\n}\n")]
        self.assertIn("$NoBrowser = $true", blk)
        self.assertNotIn("$NonInteractive = $true", blk, "ต้องไม่กลายเป็นโหมดที่ข้าม MCP/hub/STT")
        self.assertLess(t.index("if ($Unattended -and -not $NonInteractive) {"), t.index("if ($NonInteractive) {\n"))
        # ทุกจุดที่รอ Enter มีทางออกของ -Unattended ก่อนถึง Read-Host
        code = [ln for ln in t.split("\n") if not ln.lstrip().startswith("#")]
        for i, ln in enumerate(code):
            if "Read-Host" in ln and "'" in ln and not ln.lstrip().startswith("-"):
                ctx = "\n".join(code[max(0, i - 4):i + 1])
                self.assertIn("$NonInteractive -or $Unattended", ctx, ln)
        end = t[t.rindex("if ($NonInteractive -or $Unattended) {"):]
        self.assertIn("exit $rc", end)
        self.assertIn("-Unattended", t[:t.index("param(")], "หัวไฟล์ต้องอธิบายโหมดนี้")

    def test_hub_markers_not_used_in_stt_lines(self):
        lines = [ln for ln in self.text.split("\n") if "แปลงเสียง" in ln and "Write-Host" in ln]
        self.assertTrue(lines)
        for ln in lines:
            for marker in ("กำลังรอให้แชตที่ตอบอยู่เสร็จ", "ไม่ต้องรีสตาร์ต", "ผลลัพธ์:"):
                self.assertNotIn(marker, ln)


class StopScriptTests(unittest.TestCase):
    def test_stop_script_stops_stt_port_only_if_python(self):
        raw = _read(STOPPER)
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r\n", raw, "ไฟล์นี้เป็น LF มาตลอด — คงไว้")
        t = raw.decode("utf-8-sig")
        self.assertRegex(t, r"\$SttPort\s*=\s*8795")
        self.assertRegex(t, r"Stop-ByPort \$SttPort\s+'[^']+'\s+@\('python\.exe'\)")

    @unittest.skipUnless(os.path.isfile(POWERSHELL), "ไม่มี Windows PowerShell 5.1")
    def test_scripts_parse_in_ps51(self):
        for f in (STOPPER, LAUNCHER):
            r = subprocess.run([POWERSHELL, "-NoProfile", "-Command",
                                "$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('%s',"
                                "[ref]$t,[ref]$e);$e.Count" % f], capture_output=True, timeout=120)
            self.assertEqual(r.stdout.decode().strip(), "0", f)


# ---------------------------------------------------------------- สด (ต้องตั้ง LLM_STACK_LIVE=1)
@unittest.skipUnless(os.environ.get("LLM_STACK_LIVE") == "1" and os.path.isfile(POWERSHELL)
                     and os.path.isfile(r"C:\LLM\stt\stt_server.py"),
                     "ตั้ง LLM_STACK_LIVE=1 (และต้องมี stt_server.py) เพื่อรันตัวเปิด -SttOnly จริงบนพอร์ตทดสอบ")
class LiveSttOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = int(os.environ.get("LLM_STACK_LIVE_STT_PORT") or 8896)
        s = socket.socket()
        busy = s.connect_ex(("127.0.0.1", cls.port)) == 0
        s.close()
        if busy:
            raise unittest.SkipTest("พอร์ต %d มีโปรแกรมอื่นใช้อยู่ (เอเจนต์/เทสต์อื่น?)" % cls.port)
        cls.tmp = tempfile.mkdtemp(prefix="stackb2b-live-")
        cls.tok = os.path.join(cls.tmp, "test.token")
        cls.token = secrets.token_hex(32)
        with open(cls.tok, "w", newline="\n") as fh:
            fh.write(cls.token + "\n")

    @classmethod
    def tearDownClass(cls):
        # ปิดเฉพาะ python ที่ฟังพอร์ตทดสอบและรัน stt_server.py (ไม่แตะบริการจริงที่ 8795)
        ps = ("$c = Get-NetTCPConnection -State Listen -LocalPort %d -ErrorAction SilentlyContinue | Select-Object -First 1;"
              " if ($c) { $x = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $c.OwningProcess);"
              " if ($x -and $x.CommandLine -match 'stt_server\\.py') { Stop-Process -Id $x.ProcessId -Force } }" % cls.port)
        subprocess.run([POWERSHELL, "-NoProfile", "-Command", ps], capture_output=True, timeout=60)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_stt_only_starts_and_reports_ready(self):
        env = dict(os.environ, LLM_LOCAL_TOKEN_FILE=self.tok)
        r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", LAUNCHER,
                            "-Port", "8199", "-SttPort", str(self.port), "-SttOnly"],
                           capture_output=True, timeout=300, env=env)
        out = r.stdout.decode("utf-8", "replace")
        self.assertEqual(r.returncode, 0, out[-1500:])
        req = urllib.request.Request("http://127.0.0.1:%d/health" % self.port,
                                     headers={"Authorization": "Bearer " + self.token})
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
        # เปิดซ้ำ = ใช้ตัวเดิม (ไม่เปิดตัวที่สอง)
        r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", LAUNCHER,
                            "-Port", "8199", "-SttPort", str(self.port), "-SttOnly"],
                           capture_output=True, timeout=300, env=env)
        self.assertEqual(r.returncode, 0)
        self.assertIn("เปิดอยู่แล้ว", r.stdout.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
