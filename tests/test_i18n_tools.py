# -*- coding: utf-8 -*-
"""
เทสต์ชั้นเครื่องมือหลายภาษา (2026-11) — mcp-local/i18n_tools.py + i18n_catalog.py และจุดที่ server/tools ใช้งาน

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

สิ่งที่ตรวจ
  * TR(): ภาษาไทย = ข้อความเดิม, ja/zh/en = คำแปลจากแคตตาล็อก, ไม่มีคำแปล → อังกฤษ → ไทย (ไม่หายไปไหน)
  * แคตตาล็อก: ทุกรายการมี en/ja/zh, placeholder (%s %d %r %.1f) และจำนวนบรรทัดตรงกับต้นฉบับ, ไม่มีอักษรไทยปน
  * ทุก TR("...") / _L(lang, "...", ...) / _msg(lang, "...", ...) ในซอร์สมีรายการในแคตตาล็อก (ลืมแปล = เทสต์แดง)
  * localize_tools(): แปล description ของเครื่องมือและพารามิเตอร์ (ซ้อนกี่ชั้นก็ได้) และหัวกฎ "… ||" ของตัวแรก
  * ภาษาอ่านจาก settings.json ของ hub และตามการเปลี่ยนไฟล์โดยไม่ต้องรีสตาร์ต
  * tools/list ของ server และ help ของ local_read/local_do ไม่เหลืออักษรไทยเมื่อหน้าจอเป็นญี่ปุ่น/จีน
  * tools_research: ตรวจภาษาคำถาม th/en/ja/zh และข้อความคู่ th/en ถอยเป็น ja/zh ผ่านแคตตาล็อก
ไม่เปิดพอร์ต ไม่แตะไฟล์ของผู้ใช้
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

i18n = C.import_local("i18n_tools")
catalog = C.import_local("i18n_catalog")

PROJ = os.environ.get("QWEN_PROJECTS_DIR") or os.path.join(C.LLM_ROOT, "projects")
LANGS = ("th", "en", "ja", "zh")
THAI = re.compile(r"[\u0e00-\u0e7f]")
KANA = re.compile(r"[\u3040-\u30ff]")
HAN = re.compile(r"[\u3400-\u9fff]")
PH = re.compile(r"%(?:\([^)]*\))?[-+ 0#]*\d*(?:\.\d+)?[sdrifgx%]")

# ไฟล์ที่ถูกห่อด้วย TR() — ชื่อฟังก์ชันคู่สองภาษาที่ต้องมีรายการ ja/zh ในแคตตาล็อกด้วย
WRAPPED = [os.path.join(C.MCP_LOCAL, n) for n in (
    "extract.py", "gateway.py", "guard.py", "kernel_runner.py", "netguard.py", "prompts_skills.py", "scheduler.py",
    "server.py", "tools_browser.py", "tools_creative.py", "tools_docs.py", "tools_fast.py", "tools_files.py",
    "tools_kb.py", "tools_media.py", "tools_memory.py", "tools_office.py", "tools_python.py", "tools_research.py",
    "tools_stt.py", "tools_tasks.py")] + [
    os.path.join(C.MCP_WEB, "server.py"), os.path.join(PROJ, "hub_browser.py")]
PAIR_FUNCS = {"_L", "_msg"}


def _const_args(path, names, index):
    """ข้อความคงที่ที่ส่งให้ฟังก์ชัน names ตำแหน่ง index (TR → 0, _L/_msg → 1)"""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names:
            if len(node.args) > index and isinstance(node.args[index], ast.Constant) \
                    and isinstance(node.args[index].value, str):
                out.append((node.lineno, node.args[index].value))
    return out


class TrTests(unittest.TestCase):
    def setUp(self):
        i18n.set_lang(None)
        self._saved = i18n.SETTINGS_FILE

    def tearDown(self):
        i18n.SETTINGS_FILE = self._saved
        i18n._state.update(lang=i18n.DEFAULT_LANG, mtime=None)         # ล้างแคชที่ชี้ไฟล์ชั่วคราว
        i18n.set_lang(None)

    def test_thai_is_returned_verbatim(self):
        i18n.set_lang("th")
        self.assertEqual(i18n.TR("ไม่พบไฟล์: %s"), "ไม่พบไฟล์: %s")
        self.assertEqual(i18n.TR("ข้อความที่ไม่มีในแคตตาล็อก %d"), "ข้อความที่ไม่มีในแคตตาล็อก %d")

    def test_translations_keep_placeholders_and_format(self):
        for lang, want in (("en", "file not found: %s"), ("ja", "ファイルが見つかりません: %s"), ("zh", "未找到文件: %s")):
            i18n.set_lang(lang)
            self.assertEqual(i18n.TR("ไม่พบไฟล์: %s"), want)
            self.assertEqual(i18n.TR("ไม่พบไฟล์: %s") % "a.txt", want % "a.txt")

    def test_missing_translation_falls_back_to_english_then_thai(self):
        row_backup = dict(catalog.CATALOG)
        try:
            catalog.CATALOG["ทดสอบถอยภาษา %s"] = {"en": "fallback test %s"}
            self.assertEqual(i18n.tr_for("ทดสอบถอยภาษา %s", "ja"), "fallback test %s")
            self.assertEqual(i18n.tr_for("ทดสอบถอยภาษา %s", "zh"), "fallback test %s")
            self.assertEqual(i18n.tr_for("ไม่มีในแคตตาล็อกเลย", "ja"), "ไม่มีในแคตตาล็อกเลย")
            self.assertEqual(i18n.tr_for("", "ja"), "")
            self.assertIsNone(i18n.tr_for(None, "ja"))
        finally:
            catalog.CATALOG.clear()
            catalog.CATALOG.update(row_backup)

    def test_norm_lang(self):
        self.assertEqual(i18n.norm_lang("JA"), "ja")
        self.assertEqual(i18n.norm_lang("zh-CN"), "zh")
        self.assertEqual(i18n.norm_lang("zh_TW"), "zh")
        self.assertEqual(i18n.norm_lang("fr"), "th")
        self.assertEqual(i18n.norm_lang(None), "th")
        self.assertIsNone(i18n.norm_lang("xx", None))

    def test_ui_lang_follows_settings_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            i18n.SETTINGS_FILE = path
            i18n._state.update(lang="th", mtime=None, checked=0.0)
            self.assertEqual(i18n.ui_lang(), "th")                    # ไม่มีไฟล์ = ไทย
            path.write_text(json.dumps({"lang": "ja"}), encoding="utf-8")
            i18n._state["checked"] = 0.0
            self.assertEqual(i18n.ui_lang(), "ja")
            path.write_text(json.dumps({"lang": "zh-CN"}), encoding="utf-8")
            os.utime(path, (1, 2))                                      # mtime ใหม่แน่นอน
            i18n._state["checked"] = 0.0
            self.assertEqual(i18n.ui_lang(), "zh")
            path.write_text("{broken", encoding="utf-8")
            os.utime(path, (3, 4))
            i18n._state["checked"] = 0.0
            self.assertEqual(i18n.ui_lang(), "th")                    # ไฟล์เสีย = ไทย ไม่พัง
            path.write_text(json.dumps({"lang": "ja"}), encoding="utf-8")
            os.utime(path, (5, 6))
            i18n._state["checked"] = 0.0
            self.assertEqual(i18n.ui_lang(), "ja")
            i18n.set_lang("en")                                         # override ของโปรเซสชนะไฟล์
            self.assertEqual(i18n.ui_lang(), "en")
            path.write_text(json.dumps({"lang": "zh"}), encoding="utf-8")
            os.utime(path, (7, 8))
            i18n.set_lang(None)                                         # ถอน override = อ่านไฟล์ใหม่ทันที ไม่รอแคช
            self.assertEqual(i18n.ui_lang(), "zh")

    def test_pick_for_thai_english_pairs(self):
        self.assertEqual(i18n.pick("th", "สรุปคำตอบ", "Answer"), "สรุปคำตอบ")
        self.assertEqual(i18n.pick("en", "สรุปคำตอบ", "Answer"), "Answer")
        self.assertEqual(i18n.pick("ja", "สรุปคำตอบ", "Answer"), "回答の要約")
        self.assertEqual(i18n.pick("zh", "สรุปคำตอบ", "Answer"), "答案摘要")
        self.assertEqual(i18n.pick("ja", "ไม่มีในแคตตาล็อก", "English twin"), "English twin")


class CatalogTests(unittest.TestCase):
    def test_every_row_has_three_languages_without_thai(self):
        self.assertGreater(len(catalog.CATALOG), 1500)
        for th, row in catalog.CATALOG.items():
            self.assertTrue(THAI.search(th), "คีย์ต้องเป็นข้อความไทย: %r" % th[:60])
            for lang in ("en", "ja", "zh"):
                tx = row.get(lang)
                self.assertTrue(isinstance(tx, str) and tx, "%s ว่าง: %r" % (lang, th[:60]))
                self.assertFalse(THAI.search(tx), "%s มีอักษรไทยปน: %r" % (lang, tx[:60]))
                self.assertEqual(PH.findall(tx), PH.findall(th), "placeholder %s ไม่ตรง: %r" % (lang, th[:60]))
                self.assertEqual(tx.count("\n"), th.count("\n"), "จำนวนบรรทัด %s ไม่ตรง: %r" % (lang, th[:60]))
                self.assertEqual(tx[:1].isspace(), th[:1].isspace(), "ช่องว่างหน้า %s: %r" % (lang, th[:60]))
                self.assertEqual(tx[-1:].isspace(), th[-1:].isspace(), "ช่องว่างท้าย %s: %r" % (lang, th[:60]))
            if len(THAI.findall(th)) >= 8:            # ข้อความที่มีเนื้อไทยจริง ต้องแปลเป็นอักษรของภาษานั้น
                self.assertTrue(KANA.search(row["ja"]) or HAN.search(row["ja"]), "ja ไม่มีอักษรญี่ปุ่น: %r" % th[:60])
                self.assertTrue(HAN.search(row["zh"]), "zh ไม่มีอักษรจีน: %r" % th[:60])

    def test_coverage_counts(self):
        for lang in ("en", "ja", "zh"):
            done, total = i18n.catalog_coverage(lang)
            self.assertEqual(done, total)

    def test_every_wrapped_literal_in_source_has_a_row(self):
        missing = []
        for path in WRAPPED:
            if not os.path.exists(path):
                self.skipTest("ไม่มีไฟล์ %s" % path)
            for lineno, text in _const_args(path, {"TR"}, 0):
                if THAI.search(text) and text not in catalog.CATALOG:
                    missing.append("%s:%d %r" % (os.path.basename(path), lineno, text[:50]))
            for lineno, text in _const_args(path, PAIR_FUNCS, 1):
                if THAI.search(text) and text not in catalog.CATALOG:
                    missing.append("%s:%d (pair) %r" % (os.path.basename(path), lineno, text[:50]))
        self.assertEqual(missing, [], "ข้อความที่ยังไม่มีคำแปล:\n" + "\n".join(missing))

    def test_tool_descriptions_are_translated(self):
        """description ของเครื่องมือในตาราง TOOLS ของทุกโมดูล (ที่เป็นไทย) ต้องแปลได้ตอนเสิร์ฟ"""
        import importlib
        missing = []
        for name in ("tools_files", "tools_docs", "tools_kb", "tools_media", "tools_memory", "tools_office",
                     "tools_python", "tools_research", "tools_stt", "tools_tasks", "tools_browser", "tools_creative",
                     "tools_fast", "scheduler"):
            try:
                mod = C.import_local(name)
            except Exception as exc:        # noqa: BLE001 — โมดูลที่ import ไม่ได้บนเครื่องเทสต์ (เช่น ไม่มี COM)
                continue
            for schema in getattr(mod, "TOOLS", []) + getattr(mod, "FAST_TOOLS", []):
                for text in _descriptions(schema):
                    if THAI.search(text) and text not in catalog.CATALOG:
                        missing.append("%s/%s: %r" % (name, schema.get("name"), text[:60]))
        self.assertEqual(missing, [], "description ที่ยังไม่มีคำแปล:\n" + "\n".join(missing))


def _descriptions(node):
    if isinstance(node, dict):
        if isinstance(node.get("description"), str):
            yield node["description"]
        for v in node.values():
            yield from _descriptions(v)
    elif isinstance(node, list):
        for v in node:
            yield from _descriptions(v)


class LocalizeToolsTests(unittest.TestCase):
    TOOL = {"name": "make_file",
            "description": "สร้างไฟล์แล้ว",
            "inputSchema": {"type": "object", "properties": {
                "path": {"type": "string", "description": "path เต็มของไฟล์"},
                "fields": {"type": "array", "items": {"type": "object", "properties": {
                    "limit": {"type": "integer", "description": "จำนวนรายการสูงสุด (30)"}}}}}}}

    def test_thai_returns_same_objects(self):
        tools = [dict(self.TOOL)]
        self.assertIs(i18n.localize_tools(tools, "th"), tools)

    def test_descriptions_translated_recursively_and_source_untouched(self):
        tools = [json.loads(json.dumps(self.TOOL))]
        out = i18n.localize_tools(tools, "ja")
        self.assertEqual(out[0]["description"], "ファイルを作成しました")
        self.assertEqual(out[0]["inputSchema"]["properties"]["path"]["description"], "ファイルの完全な path")
        self.assertEqual(out[0]["inputSchema"]["properties"]["fields"]["items"]["properties"]["limit"]["description"],
                         "最大件数 (30)")
        self.assertEqual(tools[0]["description"], "สร้างไฟล์แล้ว")       # ต้นฉบับไม่ถูกแก้
        out_en = i18n.localize_tools(tools, "en")
        self.assertEqual(out_en[0]["description"], "file created")

    def test_rules_prefix_is_translated_in_two_halves(self):
        server = C.import_local("server")
        head = server.RULES_SHORT
        desc = "สร้างไฟล์แล้ว"
        joined = head + " " + desc
        for lang in ("en", "ja", "zh"):
            got = i18n.tr_for(joined, lang)
            self.assertEqual(got, i18n.tr_for(head, lang) + " " + i18n.tr_for(desc, lang))
            self.assertFalse(THAI.search(got))
            self.assertTrue(got.endswith(i18n.tr_for(desc, lang)))
        # ครึ่งหลังไม่มีในแคตตาล็อกก็ยังแปลหัวกฎได้ (ครึ่งหลังคงไว้)
        got = i18n.tr_for(head + " " + "ข้อความใหม่ที่ยังไม่แปล", "ja")
        self.assertTrue(got.startswith(i18n.tr_for(head, "ja")))
        self.assertTrue(got.endswith("ข้อความใหม่ที่ยังไม่แปล"))


class ServerSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = C.import_local("server")
        cls.server.load_modules()

    def setUp(self):
        i18n.set_lang(None)

    def tearDown(self):
        i18n.set_lang(None)

    def _tools(self, fast):
        reply = self.server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, "p", fast=fast)
        return reply["result"]["tools"]

    def test_tools_list_has_no_thai_in_japanese_and_chinese(self):
        for lang, script in (("ja", KANA), ("zh", HAN)):
            i18n.set_lang(lang)
            for fast in (False, True):
                tools = self._tools(fast)
                self.assertTrue(tools)
                texts = [t for s in tools for t in _descriptions(s)]
                thai = [t[:60] for t in texts if THAI.search(t)]
                self.assertEqual(thai, [], "%s fast=%s ยังมีไทย: %s" % (lang, fast, thai[:3]))
                self.assertTrue(script.search(tools[0]["description"]), tools[0]["description"][:80])
                self.assertIn("||", tools[0]["description"])          # หัวกฎยังอยู่หน้าตัวแรก

    def test_tools_list_thai_is_unchanged(self):
        i18n.set_lang("th")
        tools = self._tools(False)
        self.assertTrue(tools[0]["description"].startswith(self.server.RULES_SHORT))

    def test_instructions_translated(self):
        for lang, script in (("ja", KANA), ("zh", HAN), ("en", re.compile(r"[A-Za-z]"))):
            i18n.set_lang(lang)
            reply = self.server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, "p")
            text = reply["result"]["instructions"]
            self.assertFalse(THAI.search(text))
            self.assertTrue(script.search(text))
            self.assertEqual(text.count("\n"), self.server.INSTRUCTIONS.count("\n"))

    def test_fast_help_text_has_no_thai(self):
        tools_fast = C.import_local("tools_fast")
        for lang in ("ja", "zh", "en"):
            i18n.set_lang(lang)
            text = tools_fast.help_text()
            thai = [ln for ln in text.split("\n") if THAI.search(ln)]
            self.assertEqual(thai, [], "%s: %s" % (lang, thai[:3]))
            self.assertIn("local_read(action=...)", text)
        i18n.set_lang("th")
        self.assertTrue(THAI.search(tools_fast.help_text()))

    def test_tool_result_follows_ui_language(self):
        tools_files = C.import_local("tools_files")
        i18n.set_lang("zh")
        text = i18n.TR("ไม่พบไฟล์: %s") % "x"
        self.assertEqual(text, "未找到文件: x")
        self.assertIsNotNone(tools_files)


class ResearchLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = C.import_local("tools_research")

    def test_detect_lang_four_scripts(self):
        d = self.r.detect_lang
        self.assertEqual(d("วิธียืดอายุแบตเตอรี่ EV"), "th")
        self.assertEqual(d("How to extend EV battery life"), "en")
        self.assertEqual(d("EV バッテリーの寿命を延ばす方法"), "ja")
        self.assertEqual(d("如何延长电动车电池寿命"), "zh")
        self.assertEqual(d("OCPP 2.0.1 と 1.6 の違い"), "ja")
        self.assertEqual(d(""), "en")

    def test_pairs_fall_back_through_catalogue(self):
        L = self.r._L
        self.assertEqual(L("th", "สรุปคำตอบ", "Answer"), "สรุปคำตอบ")
        self.assertEqual(L("en", "สรุปคำตอบ", "Answer"), "Answer")
        self.assertEqual(L("ja", "แหล่งอ้างอิง", "Sources"), "出典")
        self.assertEqual(L("zh", "แหล่งอ้างอิง", "Sources"), "参考来源")
        self.assertEqual(L("zh", "ไม่มีในแคตตาล็อก", "English twin"), "English twin")

    def test_report_language_instruction_and_durations(self):
        self.assertIn("日本語", self.r._L("ja", "เขียนรายงานทั้งหมดเป็นภาษาไทย (ชื่อเฉพาะและศัพท์เทคนิคภาษาอังกฤษคงไว้ได้)",
                                           "Write the whole report in English."))
        self.assertIn("简体中文", self.r._L("zh", "เขียนรายงานทั้งหมดเป็นภาษาไทย (ชื่อเฉพาะและศัพท์เทคนิคภาษาอังกฤษคงไว้ได้)",
                                           "Write the whole report in English."))
        self.assertEqual(self.r._dur(3700, "zh"), "1 小时 1 分钟")
        self.assertEqual(self.r._dur(65, "ja"), "1 分 5 秒")
        self.assertEqual(self.r._dur(65, "en"), "1m 5s")
        self.assertEqual(self.r._dur(65, "th"), "1 นาที 5 วินาที")
        for lang in LANGS:
            self.assertIn(lang, self.r.BANNER)
            self.assertIn(lang, self.r._LANG_NAME)
        self.assertEqual(self.r.eta_text("quick", "4b", "ja"), "約 %d-%d 分" % self.r.ETA_MIN[("quick", "4b")])
        self.assertTrue(HAN.search(self.r.eta_text("quick", "4b", "zh")))

    def test_limitations_render_in_report_language(self):
        rows = [{"th": "รายงานบางส่วนอาจไม่ใช่ภาษาของคำถาม", "en": "Parts of the report may not be in the question's language"}]
        self.assertEqual(self.r._L("ja", rows[0]["th"], rows[0]["en"]), "レポートの一部は質問の言語でない可能性があります")
        self.assertEqual(self.r._L("en", rows[0]["th"], rows[0]["en"]), rows[0]["en"])


class PromptsSkillsTests(unittest.TestCase):
    def test_msg_pairs(self):
        ps = C.import_local("prompts_skills")
        self.assertEqual(ps._msg("th", "ต้องระบุชื่อพรอมต์", "prompt name is required"), "ต้องระบุชื่อพรอมต์")
        self.assertEqual(ps._msg("en", "ต้องระบุชื่อพรอมต์", "prompt name is required"), "prompt name is required")
        self.assertEqual(ps._msg("ja", "ต้องระบุชื่อพรอมต์", "prompt name is required"), "プロンプト名が必要です")
        self.assertEqual(ps._msg("zh", "ไม่รู้จักพรอมต์: %s", "unknown prompt: %s") % "x", "未知的提示词: x")


class StandaloneLoadTests(unittest.TestCase):
    """โมดูลที่ถูกโหลดจากนอก mcp-local ต้องหา i18n_tools ข้างตัวเองได้เมื่อ mcp-local ไม่อยู่ใน sys.path:
    hub โหลด tools_memory จาก path (guard เป็น stub), mcp-websearch โหลด netguard จาก path,
    kernel_runner รันด้วย python -I ของ anaconda และ mcp-websearch/server.py เองก็เริ่มได้ (CI ของ PR #13 ล้มตรงนี้)"""

    def _run(self, code, cwd=None):
        env = {k: v for k, v in os.environ.items()
               if k.upper() in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "USERPROFILE", "HOME")}
        env.update({"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
        # -I ไม่อ่าน PYTHON* จาก env (รวม PYTHONIOENCODING) จึงต้อง -X utf8 ให้ stdout พิมพ์ญี่ปุ่น/จีนบน Windows ได้
        r = subprocess.run([sys.executable, "-I", "-X", "utf8", "-c", code], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120, cwd=cwd or tempfile.gettempdir(), env=env)
        self.assertEqual(r.returncode, 0, (r.stdout or "") + (r.stderr or ""))
        return r.stdout

    def test_modules_loaded_by_path_find_the_catalogue(self):
        code = textwrap.dedent("""
            import importlib.util, sys, types
            M = %r
            def load(name, path):
                spec = importlib.util.spec_from_file_location(name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
            assert not any(p.replace("\\\\", "/").rstrip("/").endswith("mcp-local") for p in sys.path), sys.path
            ng = load("netguard", M + "/netguard.py")
            stub = types.ModuleType("guard")
            stub.Denied = type("Denied", (Exception,), {})
            stub.audit = lambda *a, **k: None
            stub.check_read = stub.check_write = stub.project_dir = lambda *a, **k: None
            sys.modules["guard"] = stub
            tm = load("qwen_hub_tools_memory", M + "/tools_memory.py")
            kr = load("qwen_kernel_runner", M + "/kernel_runner.py")
            i18n = sys.modules["i18n_tools"]
            assert ng.TR is tm.TR is kr.TR is i18n.TR, "one i18n_tools for all three"
            i18n.set_lang("zh")
            print(ng.TR("ชื่อโดเมนไม่ถูกต้อง"), "|", kr.TR("บันทึกรูปไม่สำเร็จ: %%s") %% "x")
        """) % os.path.abspath(C.MCP_LOCAL)
        out = self._run(code)
        self.assertIn("域名无效", out)
        self.assertIn("保存图像失败: x", out)

    def test_websearch_server_imports_without_mcp_local_on_sys_path(self):
        code = textwrap.dedent("""
            import importlib.util, sys
            sys.argv = [sys.argv[0]]
            spec = importlib.util.spec_from_file_location("ws_server_standalone", %r)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            assert mod.TR.__module__ == "i18n_tools", mod.TR.__module__
            sys.modules["i18n_tools"].set_lang("ja")
            tools = mod.localize_tools(mod.TOOLS)
            print(mod.TR("ไม่พบผลลัพธ์สำหรับ: %%s%%s") %% ("q", ""), "|", tools[0]["description"][:40])
        """) % os.path.abspath(os.path.join(C.MCP_WEB, "server.py"))
        out = self._run(code, cwd=os.path.abspath(C.MCP_WEB))
        self.assertIn("結果が見つかりません: q", out)
        self.assertFalse(THAI.search(out), out)


if __name__ == "__main__":
    unittest.main()
