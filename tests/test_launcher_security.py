# -*- coding: utf-8 -*-
"""
เทสต์ความปลอดภัยของตัวเปิด start-qwen38.ps1 (รอบแก้ 2026-09-30 ต่อ: llama-server ต้องใช้ API key)

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

ทำไมต้องเทสต์แบบนี้
  ตัวเปิดเป็นสคริปต์เดียวที่รันทุกอย่างตอนโหลด (เปิดบริการ/router) จึง dot-source ทั้งไฟล์ไม่ได้
  เทสต์นี้ใช้ parser ของ PowerShell 5.1 ดึง "ฟังก์ชัน" ที่ต้องการออกจากไฟล์จริงมารันแยก
  (ไม่มีโค้ดระดับบนสุดของตัวเปิดถูกรันเลย) พร้อมตัวแปรทดสอบ และ Get-CimInstance ปลอม
  = ทดสอบโค้ดที่ผู้ใช้รันจริง ไม่ใช่สำเนา

สิ่งที่ตรวจ
  * ไฟล์ยังเป็น UTF-8 BOM + CRLF และ parse ได้ใน PS 5.1 ไม่มี error
  * Get-RouterArgs ใส่ --api-key-file <path> เมื่อไฟล์โทเคนใช้เป็นคีย์ได้ (hex 64 ตัว + ขึ้นบรรทัด) และไม่ใส่
    เมื่อไฟล์หาย/มี BOM (llama-server ไม่ตัด BOM = คีย์ไม่ตรงกับที่ hub ส่ง ทุกแชต 401) — ไม่มีทางใส่ค่าโทเคนใน argv
  * Get-RouterInsecureReason: router ที่ไม่มี --api-key-file / ปฏิเสธโทเคนปัจจุบัน (401) ถูกสั่งรีสตาร์ต
    router ที่รับโทเคนแล้ว (200) ไม่ถูกแตะ — ใช้เซิร์ฟเวอร์ปลอมบนพอร์ตสุ่มแทน router จริง
  * Get-SecretsBroadAccess เห็นกลุ่มกว้าง (Authenticated Users/Users) บน C:\\ และไม่เห็นบนโฟลเดอร์ส่วนตัว
    (ตรวจอย่างเดียว เทสต์ไม่เปลี่ยน ACL ใดๆ)
ปลอดภัยต่อระบบจริง: โทเคนเป็นค่าทดสอบในโฟลเดอร์ชั่วคราว ไม่อ่าน C:\\LLM\\secrets ไม่เปิดบริการใดๆ
"""
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LAUNCHER = r"C:\LLM\start-qwen38.ps1"
POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                          r"System32\WindowsPowerShell\v1.0\powershell.exe")

# ดึงฟังก์ชันจากไฟล์จริงด้วย AST แล้วนิยามใน scope นี้ — ไม่รันโค้ดระดับบนสุดของตัวเปิด
HARNESS = r"""
param([string]$ScenarioFile)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('__LAUNCHER__', [ref]$tokens, [ref]$errs)
$want = @('Test-TokenFile', 'Test-TokenFileStrict', 'Test-RouterAuth', 'Get-SecretsBroadAccess',
          'Get-CorsOrigins', 'Get-RouterArgs', 'Get-RouterInsecureReason', 'Format-Arg')
$defs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
$found = @()
foreach ($d in $defs) { if ($want -contains $d.Name) { . ([scriptblock]::Create($d.Extent.Text)); $found += $d.Name } }
$scen = Get-Content -LiteralPath $ScenarioFile -Raw -Encoding UTF8 | ConvertFrom-Json
# ตัวแปรที่ฟังก์ชันของตัวเปิดอ่านจาก scope ของสคริปต์
$Port = [int]$scen.port; $HubPort = 8100; $ModelsDir = 'C:\LLM\models'; $UiConfig = 'C:\LLM\ui-config.json'
$Ctx = 32768; $Threads = 6; $Vision = $false; $Mmproj = 'C:\LLM\models\none.gguf'
$script:FakeCmdLine = ''
# แทน cmdlet: ฟังก์ชันชื่อเดียวกันชนะ cmdlet — ให้ command line ของ "router" เป็นค่าที่ตั้งไว้ในแต่ละกรณี
function Get-CimInstance { [pscustomobject]@{ CommandLine = $script:FakeCmdLine } }
$out = [ordered]@{ found = $found; parse_errors = $errs.Count; cases = @() }
foreach ($c in $scen.cases) {
    $TokenFile = $c.token_file
    $r = [ordered]@{ name = $c.name }
    $r.strict = [bool](Test-TokenFileStrict)
    $rargs = Get-RouterArgs $true 'C:\x\models-preset.ini' 6>$null
    $r.argv = @($rargs | ForEach-Object { [string]$_ })
    $script:FakeCmdLine = [string]$c.cmdline
    $r.reason = [string](Get-RouterInsecureReason 1234)
    $out.cases += $r
}
$out.broad_c = [string[]](Get-SecretsBroadAccess 'C:\' '')
$out.broad_private = [string[]](Get-SecretsBroadAccess $scen.private_dir '')
# วิธีเรียกแบบเดียวกับตัวเปิด (นับจำนวนแล้วต่อชื่อ) — กันพลาดแบบ @(,array) ที่ได้ Count = 1 เสมอ
$acc = Get-SecretsBroadAccess 'C:\' ''
$out.launcher_style_count = $acc.Count
$out.launcher_style_join = ($acc -join ', ')
$out | ConvertTo-Json -Depth 5 -Compress
"""


class _FakeRouter(BaseHTTPRequestHandler):
    """router ปลอม: /props ตอบ 200 เฉพาะเมื่อ Bearer ตรงกับ good_token ไม่งั้น 401 (แบบ llama-server --api-key-file)"""
    good_token = ""
    seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        auth = self.headers.get("Authorization") or ""
        type(self).seen.append((self.path, auth.startswith("Bearer ")))
        ok = auth == "Bearer " + type(self).good_token
        body = b'{"ok":true}' if ok else b'{"error":{"code":401}}'
        self.send_response(200 if ok else 401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LauncherFileTests(unittest.TestCase):
    def test_encoding_bom_crlf_and_ps51_parse(self):
        with open(LAUNCHER, "rb") as fh:
            raw = fh.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "ต้องมี BOM (PS 5.1 อ่านภาษาไทยเพี้ยนถ้าไม่มี)")
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), "ต้องเป็น CRLF ทั้งไฟล์")
        text = raw.decode("utf-8-sig")
        # ไวยากรณ์ของ PS 7 (ternary / ?? / && ||) ตรวจด้วย parser ของ PS 5.1 เอง (parse_errors ในเทสต์ถัดไป)
        # ไม่ค้นข้อความ: โค้ด C# ใน Add-Type ของตัวเปิดใช้ && || ได้ตามปกติ
        import re
        self.assertIsNone(re.search(r"['\"]--api-key['\"]", text),
                          "ห้ามส่งค่าคีย์ทาง command line (process อื่นอ่านได้ และ router ส่งต่อให้โมเดลลูก)")


@unittest.skipUnless(os.path.isfile(POWERSHELL), "ไม่มี Windows PowerShell 5.1")
class LauncherRouterAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="launcher-sec-")
        cls.token = secrets.token_hex(32)               # ค่าทดสอบ ไม่ใช่โทเคนจริง
        _FakeRouter.good_token = cls.token
        _FakeRouter.seen = []
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeRouter)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.port = cls.srv.server_address[1]

        def tok(name, data):
            p = os.path.join(cls.tmp, name)
            with open(p, "wb") as fh:
                fh.write(data)
            return p

        good = tok("good.token", (cls.token + "\n").encode("ascii"))
        crlf = tok("crlf.token", (cls.token + "\r\n").encode("ascii"))
        bom = tok("bom.token", b"\xef\xbb\xbf" + cls.token.encode("ascii"))
        other = tok("other.token", (secrets.token_hex(32) + "\n").encode("ascii"))
        missing = os.path.join(cls.tmp, "missing.token")
        private = os.path.join(cls.tmp, "private")
        os.makedirs(private)
        secure = ("llama-server.exe --models-dir C:\\LLM\\models --cors-origins http://127.0.0.1:8100 "
                  "--no-cors-credentials --api-key-file C:\\LLM\\secrets\\local-services.token")
        nokey = "llama-server.exe --models-dir C:\\LLM\\models --cors-origins http://127.0.0.1:8100 --no-cors-credentials"
        cls.cases = [
            {"name": "good", "token_file": good, "cmdline": secure},
            {"name": "crlf", "token_file": crlf, "cmdline": secure},
            {"name": "bom", "token_file": bom, "cmdline": nokey},
            {"name": "missing", "token_file": missing, "cmdline": nokey},
            {"name": "router_without_key", "token_file": good, "cmdline": nokey},
            {"name": "router_old_token", "token_file": other, "cmdline": secure},
            {"name": "router_mcp_proxy", "token_file": good, "cmdline": secure + " --ui-mcp-proxy"},
        ]
        scen = os.path.join(cls.tmp, "scen.json")
        with open(scen, "w", encoding="utf-8") as fh:
            json.dump({"port": cls.port, "cases": cls.cases, "private_dir": private}, fh)
        harness = os.path.join(cls.tmp, "harness.ps1")
        with open(harness, "w", encoding="utf-8-sig") as fh:
            fh.write(HARNESS.replace("__LAUNCHER__", LAUNCHER))
        r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-File", harness, scen], capture_output=True, timeout=120)
        cls.stderr = r.stderr.decode("utf-8", "replace")
        out = r.stdout.decode("utf-8", "replace").strip().splitlines()
        cls.result = json.loads(out[-1]) if out else None
        cls.by = {c["name"]: c for c in (cls.result or {}).get("cases", [])}

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.assertIsNotNone(self.result, "harness ของ PowerShell ไม่คืนผล: " + self.stderr[-800:])

    def test_functions_extracted_from_real_launcher(self):
        for name in ("Test-TokenFileStrict", "Test-RouterAuth", "Get-SecretsBroadAccess",
                     "Get-RouterArgs", "Get-RouterInsecureReason"):
            self.assertIn(name, self.result["found"])
        self.assertEqual(self.result["parse_errors"], 0)

    def _key_file_arg(self, argv):
        if "--api-key-file" not in argv:
            return None
        return argv[argv.index("--api-key-file") + 1]

    def test_router_gets_api_key_file_path_never_value(self):
        for name in ("good", "crlf"):
            c = self.by[name]
            self.assertTrue(c["strict"], name)
            self.assertEqual(self._key_file_arg(c["argv"]), next(x["token_file"] for x in self.cases
                                                                if x["name"] == name), name)
            self.assertNotIn(self.token, " ".join(c["argv"]), "ค่าโทเคนต้องไม่อยู่ใน argv ของ router")
            self.assertNotIn("--api-key", [a for a in c["argv"]])
        # ค่าความปลอดภัยเดิมของ C4 ยังอยู่ครบ
        argv = self.by["good"]["argv"]
        self.assertIn("--no-cors-credentials", argv)
        self.assertIn("--cors-origins", argv)
        self.assertNotIn("--ui-mcp-proxy", argv)
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")

    def test_unusable_token_file_means_no_key_flag(self):
        for name in ("bom", "missing"):
            c = self.by[name]
            self.assertFalse(c["strict"], name)
            self.assertIsNone(self._key_file_arg(c["argv"]), name)
            # ไม่มีไฟล์ที่ใช้เป็นคีย์ได้ = ไม่สั่งรีสตาร์ตเพราะเรื่องคีย์ (รีสตาร์ตไปก็ได้แบบเดิม)
            self.assertEqual(c["reason"], "", name)

    def test_router_without_key_or_with_old_token_is_restarted(self):
        self.assertIn("API key", self.by["router_without_key"]["reason"])
        self.assertIn("โทเคนชุดเก่า", self.by["router_old_token"]["reason"])
        self.assertIn("/cors-proxy", self.by["router_mcp_proxy"]["reason"])

    def test_router_accepting_current_token_is_left_alone(self):
        self.assertEqual(self.by["good"]["reason"], "")
        self.assertEqual(self.by["crlf"]["reason"], "")
        # ตัวตรวจแนบโทเคนไปจริง (ไม่ใช่ผ่านเพราะไม่ได้ถาม)
        self.assertIn(("/props", True), _FakeRouter.seen)

    def test_broad_acl_detection(self):
        self.assertTrue(set(self.result["broad_c"]) & {"Authenticated Users", "Users"},
                        "C:\\ ให้ Authenticated Users/Users อ่านได้เสมอบน Windows ปกติ: %r" % self.result["broad_c"])
        self.assertIn(self.result["broad_private"], ([], None),
                      "โฟลเดอร์ใต้ %TEMP% ของผู้ใช้ไม่ควรมีกลุ่มกว้าง")
        self.assertEqual(self.result["launcher_style_count"], len(self.result["broad_c"]))
        self.assertNotIn("System.", self.result["launcher_style_join"])


if __name__ == "__main__":
    unittest.main()
