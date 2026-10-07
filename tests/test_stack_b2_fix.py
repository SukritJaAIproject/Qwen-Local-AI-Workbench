# -*- coding: utf-8 -*-
"""
เทสต์รอบแก้ของ batch 2a (owner stack) หลังผลตรวจของ integrator

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

สิ่งที่ตรวจ
  * ลิงก์รายงานในแผงงานค้นคว้า (hub._res_files) ตามสัญญาของ tools_research: อ่านเฉพาะ report{md, docx}, ชื่อต้องเป็น
    research-<วันที่>-<รหัสงานนี้>[-n].md|docx (รหัสงานตรงกับชื่อไฟล์สถานะ, นามสกุลตรงกับคีย์) และมีไฟล์อยู่จริงใน outputs\\
    — ไฟล์สถานะที่ถูกปลอม (โมเดลเขียน .json ใหม่ได้) ทำให้แผงแสดงไฟล์อื่นของโปรเจกต์เป็น "รายงานค้นคว้า" ไม่ได้อีก
  * system message ของโปรเจกต์ (hub.project_system_message) บอกให้เรียก local_read action="kb" ก่อนเมื่อถามเรื่องไฟล์
    (วัดจริงผ่าน hub 8103 กับ Qwen3-4B: เดิม 0/7 → 13/14) เป็นอังกฤษล้วน และไม่มีเวลา (KV cache ของต้นบทสนทนาใช้ซ้ำได้)
  * ตัวเปิด -RestartEmbed: ฟังก์ชัน Invoke-EmbedStep จริง (ดึงด้วย parser ของ PowerShell 5.1 + ฟังก์ชันรอบข้างปลอม)
    ปิดแล้วเปิดใหม่เฉพาะบริการ embedding ของเรา — โปรแกรมอื่นบนพอร์ตไม่ถูกแตะ, รอบทดสอบพอร์ตอื่น/-NoEmbed ยังข้าม
  * enhance: แชตที่เริ่มจากชิปสกิล (MCP prompt, เนื้อความว่าง) ได้ชื่อ "ชื่อสกิล · อาร์กิวเมนต์แรก" (รันฟังก์ชันจริงด้วย node),
    รูปแบบชื่อชั่วคราวตรงกับของ shell, เขียนเฉพาะตอนชื่อยังเป็นชื่อชั่วคราว (ตรวจในทรานแซกชันเดียวกับที่เขียน)
  * theme: utility สีม่วงทุกตัวที่ WebUI ใช้กับชิปพรอมต์ถูกแปลงเป็นโทเคนสีเน้น ด้วย selector ที่ชนะ .dark\\:…:is(.dark *)
ปลอดภัยต่อระบบจริง: DATA_ROOT ชี้โฟลเดอร์ชั่วคราว ไม่เปิดเซิร์ฟเวอร์/บริการใด ไม่แตะ IndexedDB ของเบราว์เซอร์จริง
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HUB = r"C:\LLM\projects\hub.py"
ENHANCE = r"C:\LLM\projects\static\webui-enhance.js"
THEME = r"C:\LLM\projects\static\webui-theme.css"
LAUNCHER = r"C:\LLM\start-qwen38.ps1"
POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                          r"System32\WindowsPowerShell\v1.0\powershell.exe")
SLUG = "b5fixtest"


def load_hub():
    sys.path.insert(0, os.path.dirname(HUB))
    spec = importlib.util.spec_from_file_location("hub_stack_b2_fix", HUB)
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


hub = load_hub()


def node_exe():
    for p in (shutil.which("node"), r"C:\Program Files\nodejs\node.exe"):
        if p and os.path.isfile(p):
            return p
    return None


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


class _TmpData(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stackb2fix-"))
        self.data = self.tmp / "data"
        self.data.mkdir()
        self.patches = [mock.patch.object(hub, "DATA_ROOT", self.data),
                        mock.patch.object(hub, "get_lang", return_value="th")]
        for p in self.patches:
            p.start()
        self.odir = self.data / SLUG / "outputs"
        self.odir.mkdir(parents=True)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def out(self, *names):
        for n in names:
            (self.odir / n).write_bytes(b"x")


# ============================================================================ ลิงก์รายงานตามสัญญา
class ReportLinkContractTests(_TmpData):
    JID = "rabc123"
    MD = "research-2026-10-01-rabc123.md"

    def job(self, jid=None, **over):
        doc = {"schema": 1, "kind": "qwen-research", "id": jid or self.JID, "question": "q", "status": "done"}
        doc.update(over)
        return hub.research_job_public(SLUG, jid or self.JID, doc)

    def test_own_reports_are_linked_and_urls_rebuilt(self):
        self.out(self.MD, "research-2026-10-01-rabc123-1.docx", "ok.md")
        j = self.job(report={"md": self.MD, "docx": "research-2026-10-01-rabc123-1.docx",
                             "md_link": "/_qwen/out/ok.md", "docx_link": "javascript:alert(1)"})
        self.assertEqual([(f["name"], f["kind"]) for f in j["files"]],
                         [(self.MD, "md"), ("research-2026-10-01-rabc123-1.docx", "docx")])
        self.assertEqual(j["report"], "/_qwen/out/" + self.MD)                 # ไม่ใช้ md_link ในไฟล์
        self.assertEqual(j["files"][1]["url"], "/_qwen/out/research-2026-10-01-rabc123-1.docx")

    def test_forged_names_are_never_linked(self):
        self.out(self.MD, "research-2026-10-01-rabc123.docx", "research-2026-10-01-rdef456.md", "ok.md",
                 "รายงานสถานีB.docx", "notes.txt", "page.html", "research-๒๐๒๖-10-01-rabc123.md")
        forged = [
            {"md": "ok.md"},                                        # ไฟล์อื่นของโปรเจกต์
            {"docx": "รายงานสถานีB.docx"},
            {"md": "notes.txt"}, {"md": "page.html"},
            {"md": "research-2026-10-01-rdef456.md"},               # รายงานของงานอื่น
            {"md": "research-2026-10-01-rabc123.docx"},             # นามสกุลไม่ตรงกับคีย์
            {"docx": self.MD},
            {"md": "/_qwen/out/" + self.MD},                        # ลิงก์ ไม่ใช่ชื่อ (สัญญาเก็บชื่อ)
            {"md": "../" + self.MD}, {"md": "outputs/" + self.MD}, {"md": "C:\\x\\outputs\\" + self.MD},
            {"md": self.MD.upper()}, {"md": self.MD + " "}, {"md": self.MD + "\u202e"}, {"md": self.MD + ".exe"},
            {"md": "research-\u0e52\u0e50\u0e52\u0e56-10-01-rabc123.md"},               # \u0e40\u0e25\u0e02\u0e44\u0e17\u0e22 (\d \u0e02\u0e2d\u0e07 Python \u0e23\u0e31\u0e1a) \u2014 \u0e15\u0e49\u0e2d\u0e07\u0e40\u0e1b\u0e47\u0e19 0-9
            {"md": "research-2026-10-01-rabc123-2.md"},             # รูปแบบถูกแต่ไม่มีไฟล์
            {"md": [self.MD]}, {"md": {"name": self.MD}}, {"md": 1},
        ]
        for rep in forged:
            j = self.job(report=rep)
            self.assertEqual(j["files"], [], rep)
            self.assertIsNone(j["report"], rep)
        self.assertEqual(self.job(report=self.MD)["files"], [])             # report ต้องเป็น dict

    def test_other_keys_are_ignored(self):
        self.out(self.MD, "ok.md")
        link = "/_qwen/out/" + self.MD
        j = self.job(status=None, report=None, result=[link, "[r](/_qwen/out/ok.md)"], files=[self.MD, "ok.md"],
                     output=link, outputs=[link], link=link, links=[link], path="C:\\x\\outputs\\" + self.MD,
                     md=self.MD, docx=self.MD, report_md=self.MD, report_path=link)
        self.assertEqual(j["files"], [])
        self.assertIsNone(j["report"])
        self.assertEqual(j["status"], "unknown", "ไม่มีสถานะและไม่มีรายงาน = ไม่รู้ ไม่ใช่ 'เสร็จ'")

    def test_job_id_must_follow_contract(self):
        # ชื่อไฟล์สถานะที่ไม่ใช่รหัสงานของ tools_research (r + hex) ลิงก์รายงานใดไม่ได้เลย
        for jid in ("job-1", "R3FA9C1", "rabc12", "rabc123x"):
            self.out("research-2026-10-01-%s.md" % jid)
            j = self.job(jid, report={"md": "research-2026-10-01-%s.md" % jid})
            self.assertEqual(j["files"], [], jid)

    def test_listing_uses_the_contract_too(self):
        self.out(self.MD, "ok.md")
        rdir = self.data / SLUG / "research"
        rdir.mkdir()
        (rdir / "rabc123.json").write_text(json.dumps({"id": "rabc123", "question": "q", "status": "done",
                                                       "report": {"md": self.MD}}), encoding="utf-8")
        (rdir / "r999999.json").write_text(json.dumps({"id": "r999999", "question": "q", "status": "done",
                                                       "report": {"md": "ok.md"}}), encoding="utf-8")
        jobs = {j["id"]: j for j in hub.research_list(SLUG)["jobs"]}
        self.assertEqual(jobs["rabc123"]["report"], "/_qwen/out/" + self.MD)
        self.assertIsNone(jobs["r999999"]["report"])

    def test_regex_matches_tools_research(self):
        src = read(r"C:\LLM\mcp-local\tools_research.py")
        m = re.search(r'_REPORT_NAME_RE = re\.compile\(r"\^(.*)\$"\)', src)
        self.assertIsNotNone(m, "tools_research._REPORT_NAME_RE หายหรือเปลี่ยนรูป — ตรวจสัญญาชื่อรายงานใหม่")
        theirs = re.compile(m.group(1))
        for name in (self.MD, "research-2026-10-01-rabc123-1.docx", "research-2026-12-31-r0123456789ab.md"):
            self.assertTrue(theirs.fullmatch(name) and hub._RESEARCH_REPORT_NAME_RE.fullmatch(name), name)
        for name in ("research-2026-10-01-rabc12.md", "research-2026-10-01-rabc123.pdf", "ok.md"):
            self.assertFalse(theirs.fullmatch(name) or hub._RESEARCH_REPORT_NAME_RE.fullmatch(name), name)


# ============================================================================ system message: kb ก่อน
class ProjectSystemMessageTests(_TmpData):
    def test_kb_first_hint(self):
        msg = hub.project_system_message({"slug": SLUG, "system_prompt": ""})
        for needle in ('local_read', 'action="kb"', 'action="extract"', 'action="list"', "FIRST", "OCR",
                       "scanned PDFs and photos", "outputs/", str(self.data / SLUG / "attachments")):
            self.assertIn(needle, msg)
        self.assertLess(msg.index('action="kb"'), msg.index('action="extract"'))
        self.assertLess(msg.index('action="extract"'), msg.index('action="list"'))
        self.assertIn("before saying the information is missing", msg)
        self.assertIn("writing a tool call as text", msg)

    def test_english_stable_and_after_project_prompt(self):
        a = hub.project_system_message({"slug": SLUG, "system_prompt": "ตอบเป็นภาษาไทย"})
        b = hub.project_system_message({"slug": SLUG, "system_prompt": "ตอบเป็นภาษาไทย"})
        self.assertEqual(a, b, "ข้อความเดิมทุกครั้ง (KV cache ของต้นบทสนทนาใช้ซ้ำได้)")
        self.assertTrue(a.startswith("ตอบเป็นภาษาไทย\n\n"), "คำสั่งของผู้ใช้มาก่อนเสมอ")
        note = hub.project_system_message({"slug": SLUG, "system_prompt": ""})
        self.assertIsNone(re.search("[\u0e00-\u0e7f]", note), "หมายเหตุต้องเป็นอังกฤษ (ไม่ดึงคำตอบไปเป็นไทย)")
        self.assertLess(len(note), 1000, "อยู่หน้าทุกบทสนทนา — สั้นไว้")


# ============================================================================ ตัวเปิด -RestartEmbed
STEP_HARNESS = r"""
param([string]$ScenarioFile)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('__LAUNCHER__', [ref]$tokens, [ref]$errs)
$defs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
$found = 0
foreach ($d in $defs) { if ($d.Name -eq 'Invoke-EmbedStep') { . ([scriptblock]::Create($d.Extent.Text)); $found++ } }
$scen = Get-Content -LiteralPath $ScenarioFile -Raw -Encoding UTF8 | ConvertFrom-Json
$EmbedModel = [string]$scen.model_file
$MainPort = 8099; $EmbedPort = 8093
function Test-TokenFileStrict { return $true }
function Test-Port([int]$p) { return [bool]$script:Busy }
function Get-EmbedState([int]$p) { return @{ Ours = [bool]$script:Ours; Pid = 4242; Name = [string]$script:PName; Why = [string]$script:Why } }
function Stop-Embed([int]$OwnerPid) { $script:Calls += ('stop:' + $OwnerPid); return $true }
function Start-Embed { $script:Calls += 'start'; return 'H' }
$out = @()
foreach ($c in $scen.cases) {
    $RestartEmbed = [bool]$c.restart; $NoEmbed = [bool]$c.noembed
    $Port = [int]$c.port; $EmbedPortGiven = [bool]$c.port_given
    $script:Busy = [bool]$c.busy; $script:Ours = [bool]$c.ours; $script:PName = [string]$c.pname; $script:Why = [string]$c.why
    $script:Calls = @()
    $r = Invoke-EmbedStep
    $out += [ordered]@{ case = [string]$c.case; state = [string]$r.State; calls = @($script:Calls) }
}
[ordered]@{ found = $found; parse_errors = $errs.Count; results = $out } | ConvertTo-Json -Depth 6 -Compress
"""


class RestartEmbedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = read_bytes(LAUNCHER)
        cls.raw = raw
        cls.text = raw.decode("utf-8-sig").replace("\r\n", "\n")

    def test_switch_implies_embed_only_and_sits_after_ownership_check(self):
        t = self.text
        self.assertTrue(self.raw.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(self.raw.count(b"\n"), self.raw.count(b"\r\n"), "ตัวเปิดเป็น CRLF ทั้งไฟล์")
        head = t[t.index("param("):t.index("$ErrorActionPreference")]
        self.assertIn("[switch]$RestartEmbed", head)
        self.assertLess(t.index("if ($RestartEmbed) { $EmbedOnly = $true }"),
                        t.index("if ($EmbedOnly) { $NonInteractive = $true }"),
                        "-RestartEmbed ต้องจบที่ขั้น 1d เหมือน -EmbedOnly (ไม่ลามไป router/MCP/hub)")
        fn = t[t.index("function Invoke-EmbedStep"):t.index("function Show-EmbedReady")]
        self.assertLess(fn.index("-not $es.Ours"), fn.index("$RestartEmbed"),
                        "สวิตช์นี้ต้องอยู่หลังการตรวจว่าเป็นบริการของเรา")
        self.assertLess(fn.index("$RestartEmbed"), fn.index("if (-not $es.Why)"))
        self.assertIn("-RestartEmbed", t[:t.index("#>")], "หัวไฟล์ต้องอธิบายสวิตช์ใหม่")

    @unittest.skipUnless(os.path.isfile(POWERSHELL), "ไม่มี Windows PowerShell 5.1")
    def test_step_decisions(self):
        tmp = tempfile.mkdtemp(prefix="stackb2fix-ps-")
        try:
            model = os.path.join(tmp, "model.gguf")
            open(model, "wb").close()
            base = {"restart": False, "noembed": False, "port": 8099, "port_given": False, "busy": True,
                    "ours": True, "pname": "llama-server.exe", "why": ""}
            cases = [
                dict(base, case="restart_ours", restart=True),
                dict(base, case="restart_foreign", restart=True, ours=False, pname="python.exe"),
                dict(base, case="keep_ours"),
                dict(base, case="old_flags_still_restart", why="old"),
                dict(base, case="restart_free_port", restart=True, busy=False),
                dict(base, case="restart_noembed", restart=True, noembed=True),
                dict(base, case="restart_test_port", restart=True, port=8199),
                dict(base, case="restart_test_port_given", restart=True, port=8199, port_given=True),
            ]
            scen = os.path.join(tmp, "scen.json")
            with open(scen, "w", encoding="utf-8") as fh:
                json.dump({"model_file": model, "cases": cases}, fh)
            harness = os.path.join(tmp, "harness.ps1")
            with open(harness, "w", encoding="utf-8-sig") as fh:
                fh.write(STEP_HARNESS.replace("__LAUNCHER__", LAUNCHER))
            r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", harness,
                                "-ScenarioFile", scen], capture_output=True, timeout=180)
            lines = r.stdout.decode("utf-8", "replace").strip().splitlines()
            self.assertTrue(lines, r.stderr.decode("utf-8", "replace")[-2000:])
            res = json.loads(lines[-1])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual((res["found"], res["parse_errors"]), (1, 0))
        got = {x["case"]: (x["state"], list(x["calls"] or [])) for x in res["results"]}
        self.assertEqual(got["restart_ours"], ("started", ["stop:4242", "start"]))
        self.assertEqual(got["restart_foreign"], ("foreign", []), "โปรแกรมอื่นบนพอร์ตห้ามถูกปิด")
        self.assertEqual(got["keep_ours"], ("running", []), "ไม่มีสวิตช์ = ใช้ตัวเดิมต่อเหมือนเดิม")
        self.assertEqual(got["old_flags_still_restart"], ("started", ["stop:4242", "start"]))
        self.assertEqual(got["restart_free_port"], ("started", ["start"]))
        self.assertEqual(got["restart_noembed"], ("skipped", []))
        self.assertEqual(got["restart_test_port"], ("skipped", []), "รอบทดสอบพอร์ตอื่นห้ามแตะตัวจริงที่ 8093")
        self.assertEqual(got["restart_test_port_given"], ("started", ["stop:4242", "start"]))


# ============================================================================ ชื่อแชตจากชิปสกิล (shell เขียน, enhance แค่สั่ง)
NODE_DRIVER = r"""
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
var log = {closed: 0, aborted: 0, modes: [], puts: [], refresh: 0, opened: 0, created: 0};
var lastRecSig = 'x';
function convById(id) { return null; }
function refreshRecents() { log.refresh++; return Promise.resolve(); }
var IDBKeyRange = {only: function (v) { return {only: v}; }};
function later(f) { setTimeout(f, 1); }
function makeDb(stores) {
  return {
    objectStoreNames: {contains: function (n) { return Object.prototype.hasOwnProperty.call(stores, n); }},
    close: function () { log.closed++; },
    createObjectStore: function () { log.created++; },
    transaction: function (names, mode) {
      log.modes.push(mode);
      var tx = {pending: 0, done: false};
      function settle() {
        setTimeout(function () {
          if (tx.pending === 0 && !tx.done) { tx.done = true; if (tx.oncomplete) tx.oncomplete(); }
        }, 5);
      }
      function req(fn) {
        var r = {};
        tx.pending++;
        later(function () { r.result = fn(); tx.pending--; if (r.onsuccess) r.onsuccess(); settle(); });
        return r;
      }
      tx.objectStore = function (n) {
        var st = stores[n];
        return {
          get: function (id) { return req(function () { return st[id] ? JSON.parse(JSON.stringify(st[id])) : undefined; }); },
          put: function (v) { log.puts.push(v.id); return req(function () { st[v.id] = v; return v.id; }); },
          indexNames: {contains: function (x) { return x === 'convId'; }},
          index: function () { return {getAll: function (range) { return req(function () {
            return Object.keys(st).map(function (k) { return st[k]; }).filter(function (m) { return m.convId === range.only; });
          }); }}; }
        };
      };
      return tx;
    }
  };
}
function fakeIdb(db) {
  return {open: function (name, ver) {
    log.name = name; log.ver = ver; log.opened++;
    var req = {};
    later(function () {
      if (!db) {
        req.result = makeDb({});
        req.transaction = {abort: function () { log.aborted++; later(function () { if (req.onerror) req.onerror(); }); }};
        if (req.onupgradeneeded) req.onupgradeneeded();
        return;
      }
      req.result = db;
      if (req.onsuccess) req.onsuccess();
    });
    return req;
  }};
}
var indexedDB;
__FUNCS__
(async function () {
  var out = {titles: input.cases.map(function (c) { return skillChatTitle(c); }),
             defs: input.names.map(function (n) { return DEF_NAME.test(n); })};
  var stores = input.stores;
  indexedDB = fakeIdb(makeDb(stores));
  out.renamed = await nameSkillChat('c1');
  var opened = log.opened;
  out.again = await nameSkillChat('c1');
  out.againOpened = log.opened - opened;
  out.userNamed = await nameSkillChat('c2');
  out.hasText = await nameSkillChat('c3');
  out.noUserYet = await nameSkillChat('c4');
  opened = log.opened;
  out.noUserYet2 = await nameSkillChat('c4');
  out.noUserYetReopened = log.opened - opened;
  out.missing = await nameSkillChat('nope');
  out.badId = await nameSkillChat({});
  out.names = {c1: stores.conversations.c1.name, c2: stores.conversations.c2.name, c3: stores.conversations.c3.name,
               c4: stores.conversations.c4.name};
  indexedDB = fakeIdb(null);
  out.noDb = await nameSkillChat('c9');
  out.lastRecSig = lastRecSig;
  out.log = log;
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
})();
"""


class SkillTitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(ENHANCE)
        cls.shell = hub.templates()[0]

    def funcs(self):
        s = self.shell
        idb = s[s.index("function idbOpen() {"):s.index("function listConvs() {")]
        d = s.index("var DEF_NAME = ")
        skill = s[s.index("var SKILL_NAMED = {};"):s.index("function deleteChat(id) {")]
        return idb + "\n" + s[d:s.index("\n", d)] + "\n" + skill

    def run_node(self, payload):
        tmp = tempfile.mkdtemp(prefix="stackb2fix-node-")
        try:
            drv = os.path.join(tmp, "drv.js")
            with open(drv, "w", encoding="utf-8") as fh:
                fh.write(NODE_DRIVER.replace("__FUNCS__", self.funcs()))
            inp = os.path.join(tmp, "in.json")
            with open(inp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
            r = subprocess.run([node_exe(), drv, inp], capture_output=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-1500:])
            return json.loads(r.stdout.decode("utf-8"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def chip(name="สรุปเอกสารยาว", args=None, **over):
        x = {"type": "MCP_PROMPT", "name": name, "promptName": "long-doc-summary", "serverName": "qwen38-local-fast",
             "content": "…", "arguments": args if args is not None else
             {"file": "scan-เหตุขัดข้อง-C03.pdf", "focus": "", "length": "สั้น"}}
        x.update(over)
        return x

    @unittest.skipUnless(node_exe(), "ไม่มี node")
    def test_title_rules_and_guarded_write(self):
        root = {"id": "r", "type": "root", "role": "system", "content": "", "timestamp": 1}
        sysm = {"id": "s", "type": "system", "role": "system", "content": "Project files…", "timestamp": 2}
        user = {"id": "u", "type": "text", "role": "user", "content": "", "timestamp": 3, "extra": [self.chip()]}
        asst = {"id": "a", "type": "text", "role": "assistant", "content": "ok", "timestamp": 4}
        cwd = {"id": "c", "type": "text", "role": "user", "content": "cwd: C:\\x", "timestamp": 2.5, "isSynthetic": True}
        later = dict(user, id="u2", content="ต่อ", timestamp=9, extra=[])
        cases = [
            [asst, user, sysm, root],                                                   # ลำดับใดก็ได้
            [root, sysm, dict(user, extra=[self.chip(args={})])],                       # ไม่มีอาร์กิวเมนต์
            [root, sysm, dict(user, content="ช่วยสรุปไฟล์นี้")],                          # มีเนื้อความ = WebUI ตั้งเอง
            [root, sysm, cwd, user, later],                                             # ข้ามข้อความสังเคราะห์
            [root, sysm],                                                               # ยังไม่มีข้อความผู้ใช้
            [root, dict(user, extra=[{"type": "TEXT", "name": "a.txt", "content": "x"}])],
            [root, dict(user, extra=[self.chip(name="\u202eevil\u0007 name\u200b " + "ก" * 90,
                                               args={"file": "x\u202e" + "y" * 80})])],
            [root, dict(user, extra=[self.chip(name="", promptName="code-review", args={"a": 5, "b": " "})])],
            [root, dict(user, extra="not-a-list")],
            "not-a-list",
        ]
        names = ["Chat 9/29/2026, 12:52:23 PM", "Chat 29/9/2569 12:52:23", "Chat 2026. 9. 29. 오후 1:05:09",
                 "Chat 10/1/2026, 3:08:00 AM", "สรุปเอกสารยาว · scan.pdf", "Chat", "Chat about OCPP"]
        default = "Chat 10/1/2026, 3:08:00 AM"

        def conv_msgs(cid, first):
            out = {}
            for m in ([dict(root, id=cid + "r")] + ([dict(first, id=cid + "u")] if first else [])):
                out[m["id"]] = dict(m, convId=cid)
            return out
        messages = {}
        for cid, first in (("c1", user), ("c2", user), ("c3", dict(user, content="สรุปไฟล์นี้")), ("c4", None)):
            messages.update(conv_msgs(cid, first))
        stores = {"conversations": {"c1": {"id": "c1", "name": default}, "c2": {"id": "c2", "name": "งานของฉัน"},
                                    "c3": {"id": "c3", "name": default}, "c4": {"id": "c4", "name": default}},
                  "messages": messages}
        res = self.run_node({"cases": cases, "names": names, "stores": stores})
        t = res["titles"]
        self.assertEqual(t[0], {"done": True, "name": "สรุปเอกสารยาว · scan-เหตุขัดข้อง-C03.pdf"})
        self.assertEqual(t[1], {"done": True, "name": "สรุปเอกสารยาว"})
        self.assertEqual(t[2], {"done": True, "name": ""})
        self.assertEqual(t[3]["name"], "สรุปเอกสารยาว · scan-เหตุขัดข้อง-C03.pdf")
        self.assertEqual(t[4], {"done": False, "name": ""}, "ยังตัดสินไม่ได้ = ลองใหม่ตอนตอบจบ")
        self.assertEqual(t[5], {"done": True, "name": ""})
        hostile = t[6]["name"]
        self.assertNotRegex(hostile, "[\u0000-\u001f\u200b-\u200f\u202a-\u202e]")
        title, arg = hostile.split(" \u00b7 ")
        self.assertTrue(title.startswith("evil name ก") and title.endswith("\u2026") and len(title) == 60, title)
        self.assertTrue(arg.startswith("x y") and len(arg) == 40, arg)
        self.assertEqual(t[7]["name"], "code-review", "ไม่มี title = ใช้ชื่อพรอมต์ อาร์กิวเมนต์ที่ไม่ใช่ข้อความถูกข้าม")
        self.assertEqual(t[8], {"done": True, "name": ""})
        self.assertEqual(t[9], {"done": False, "name": ""})
        self.assertEqual(res["defs"], [True, True, True, True, False, False, False])
        # การเขียนผ่านฐานข้อมูล (IndexedDB ปลอม): เขียนเฉพาะ c1 ครั้งเดียว ไม่ทับชื่อที่ตั้งแล้ว ไม่สร้างฐานว่าง ปิดทุกครั้ง
        self.assertEqual(res["renamed"], "สรุปเอกสารยาว · scan-เหตุขัดข้อง-C03.pdf")
        self.assertEqual((res["again"], res["againOpened"]), ("", 0), "ตัดสินแล้วไม่เปิดฐานข้อมูลซ้ำ")
        self.assertEqual((res["userNamed"], res["hasText"], res["noUserYet"], res["missing"], res["badId"]),
                         ("", "", "", "", ""))
        self.assertEqual(res["noUserYetReopened"], 1, "ยังไม่มีข้อความผู้ใช้ = ลองใหม่ได้")
        self.assertEqual(res["names"], {"c1": "สรุปเอกสารยาว · scan-เหตุขัดข้อง-C03.pdf", "c2": "งานของฉัน",
                                        "c3": default, "c4": default})
        self.assertEqual(res["noDb"], "")
        lg = res["log"]
        self.assertEqual(lg["puts"], ["c1"])
        self.assertEqual((lg["name"], lg.get("ver"), lg["aborted"], lg["created"]), ("LlamaUi", None, 1, 0))
        self.assertEqual(lg["closed"], lg["opened"] - 1, "ปิดการเชื่อมต่อทุกครั้งที่เปิดสำเร็จ")
        self.assertEqual(set(lg["modes"]), {"readwrite"})
        self.assertGreaterEqual(lg["refresh"], 1, "ตั้งชื่อแล้วให้ Recents/หัวแชตอ่านใหม่")
        self.assertEqual(res["lastRecSig"], "")

    def test_shell_write_is_guarded_and_exposed(self):
        s = self.shell
        fx = s[s.index("function nameSkillChat("):s.index("function deleteChat(id) {")]
        # ชื่อถูกตรวจในทรานแซกชันเขียนเดียวกัน ก่อน put — ไม่ทับชื่อที่ผู้ใช้/WebUI ตั้งไว้
        self.assertIn("db.transaction(['conversations', 'messages'], 'readwrite')", fx)
        self.assertLess(fx.index("DEF_NAME.test("), fx.index("cs.put(c)"))
        for bad in ("innerHTML", "insertAdjacentHTML", ".delete(", ".clear("):
            self.assertNotIn(bad, fx)
        self.assertIn("nameSkillChat: function (id) { try { return nameSkillChat(id); }", s)
        self.assertIsNone(re.search("[\u200b-\u200f\u202a-\u202e\u2066-\u2069]",
                                    s[s.index("var SKILL_NAMED = {};"):s.index("function deleteChat(id) {")]),
                          "ห้ามมีอักขระสลับทิศทาง/ล่องหนตัวจริงในโค้ด (ใช้ escape)")

    def test_enhance_only_asks_the_shell(self):
        s = self.src
        self.assertIn("onStreamEnd(); skillTitleSoon(0); }", s)
        self.assertIn("onStreamStart(); skillTitleSoon(1500); }", s)
        fn = s[s.index("function skillTitleSoon("):s.index("/* ---- รวมทุกส่วน: เรียกท้าย pass()")]
        self.assertIn("api.nameSkillChat(r.id)", fn)
        self.assertIn('typeof api.nameSkillChat !== "function"', fn, "shell รุ่นเก่า/ไม่มี shell = ไม่ทำอะไร")
        for bad in ("indexedDB", "readwrite", ".put("):
            self.assertNotIn(bad, fn, "enhance ไม่เขียนฐานข้อมูลของ WebUI (สัญญารอบ 4)")


class ShellHotReloadTests(unittest.TestCase):
    """hub โหลด hub_i18n_parts.py ใหม่เมื่อไฟล์ถูกแก้ — รวมกรณีแก้หลัง hub เริ่มแต่ก่อนมีคำขอหน้า shell แรก
    (เดิม _parts_mtime เริ่มที่ 0: คำขอแรกแค่จำ mtime ไม่โหลดใหม่ → เสิร์ฟ shell เก่าจนกว่าจะแก้ไฟล์อีกรอบ)"""

    def test_mtime_is_known_from_import(self):
        self.assertGreater(hub._parts_mtime, 0.0)

    def test_first_request_after_edit_reloads(self):
        with mock.patch.object(hub, "_parts_mtime", 1.0), mock.patch.object(hub.importlib, "reload") as rl:
            hub.templates()
        rl.assert_called_once_with(hub._parts)
        with mock.patch.object(hub, "_parts_mtime", os.stat(hub._parts.__file__).st_mtime), \
                mock.patch.object(hub.importlib, "reload") as rl:
            hub.templates()
        rl.assert_not_called()


# ============================================================================ theme: ชิปพรอมต์ไม่ม่วง
class PromptChipThemeTests(unittest.TestCase):
    # utility สีม่วงทุกตัวที่ WebUI b10984 ใช้ (ดึงจาก bundle ที่เสิร์ฟจริง: ชิปพรอมต์ ป้ายอาร์กิวเมนต์ ไฮไลต์ ป้าย prompts)
    USED = ["border-purple-200", "dark\\:border-purple-800", "bg-purple-500\\/10", "dark\\:bg-purple-500\\/20",
            "bg-purple-200\\/60", "dark\\:bg-purple-800\\/40", "bg-purple-300\\/50", "dark\\:bg-purple-700\\/50",
            "text-purple-700", "dark\\:text-purple-300", "text-purple-900", "dark\\:text-purple-100",
            "bg-purple-50", "dark\\:bg-purple-950", "text-purple-600", "dark\\:text-purple-400"]

    @classmethod
    def setUpClass(cls):
        raw = read_bytes(THEME)
        cls.raw = raw
        css = raw.decode("utf-8")
        at = css.index("batch 2a (fix, owner stack): ชิปสกิล (MCP prompt)")
        # เฉพาะโค้ด (ตัดคอมเมนต์ออก — คอมเมนต์อ้างชื่อคลาสม่วงของ WebUI เพื่ออธิบาย)
        cls.block = re.sub(r"/\*.*?\*/", "", css[css.rindex("/*", 0, at):], flags=re.S)

    def test_every_used_class_is_mapped_with_winning_selector(self):
        for cls_ in self.USED:
            self.assertIn("html:root ." + cls_ + "\n", self.block.replace(",\n", "\n").replace(" {\n", "\n"), cls_)
        self.assertNotIn("purple-", re.sub(r"(html:root \.[^\s,{]+|--color-purple-\d+)", "", self.block),
                         "ไม่มีค่าสีม่วงเหลือในบล็อก")
        for n in (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950):
            self.assertIn("--color-purple-%d:" % n, self.block)

    def test_colors_are_tokens_and_text_is_ink(self):
        decls = re.findall(r"(color|background-color|border-color)\s*:\s*([^;]+);", self.block)
        self.assertTrue(decls)
        for prop, val in decls:
            self.assertIn("var(--qw-", val, (prop, val))
            self.assertNotRegex(val, r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|oklch\(", "ไม่ฮาร์ดโค้ดสี")
        text_rule = self.block[self.block.index("html:root .text-purple-700"):]
        self.assertEqual(re.search(r"color:\s*([^;]+);", text_rule).group(1).strip(), "var(--qw-text)",
                         "ตัวอักษร 10px ของป้ายใช้สีหมึก (AA ทั้งสองธีม)")

    def test_theme_keeps_lf(self):
        self.assertNotIn(b"\r\n", self.raw)


if __name__ == "__main__":
    unittest.main()
