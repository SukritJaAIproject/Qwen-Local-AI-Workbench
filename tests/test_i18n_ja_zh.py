# -*- coding: utf-8 -*-
"""
เทสต์ภาษาญี่ปุ่น/จีนตัวย่อ (2026-11) — ชั้น hub: hub_i18n.py, STRINGS ของ hub.py, STRINGS_UI ของ hub_i18n_parts.py,
hub_doctor.py, hub_compact.py และสวิตช์ภาษาสี่ปุ่มในหน้า shell / หน้าจัดการ

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

สิ่งที่ตรวจ
  * ทุกตารางข้อความมีครบ 4 ภาษา (th/en/ja/zh) คีย์ตรงกัน และ placeholder (%s %d %1..) ตรงกับอังกฤษ
  * ข้อความญี่ปุ่น/จีนไม่มีอักษรไทยปน (ยกเว้นชื่อภาษา "ไทย" ของสวิตช์) และมีอักษรของภาษานั้นจริง
  * กติกาถอยภาษา: ไม่มีคำแปล → อังกฤษ → ไทย (pick / complete / localize_fields / _merge_strings)
  * ตรวจภาษาของข้อความผู้ใช้ (hub.ctx_lang, hub_compact.detect_lang) แยก th/en/ja/zh ได้
  * แคตตาล็อกข้อความ API (error_ja/error_zh) แปลทั้งข้อความตรงตัวและแบบ template
  * หน้า shell/จัดการ: ปุ่ม 4 ภาษา, setLang รับ 4 รหัส, Alt+Shift+L วนภาษาถัดไป, แถวภาษาในเมนูบัญชี
ไม่เปิดพอร์ต ไม่แตะไฟล์ของผู้ใช้
"""
import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PROJ = os.environ.get("QWEN_PROJECTS_DIR") or r"C:\LLM\projects"
HUB = os.path.join(PROJ, "hub.py")
LANGS = ("th", "en", "ja", "zh")
THAI = re.compile(r"[\u0e00-\u0e7f]")
KANA = re.compile(r"[\u3040-\u30ff]")
HAN = re.compile(r"[\u4e00-\u9fff]")
PLACEHOLDER = re.compile(r"%[sd1-9]|%\([a-z_]+\)s|%\.\d+f|\{[a-z_0-9]*\}")


def _load(name, filename):
    if PROJ not in sys.path:
        sys.path.insert(0, PROJ)
    spec = importlib.util.spec_from_file_location(name, os.path.join(PROJ, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


i18n = _load("hub_i18n_under_test", "hub_i18n.py")
parts = _load("hub_i18n_parts_i18n_under_test", "hub_i18n_parts.py")
doctor = _load("hub_doctor_i18n_under_test", "hub_doctor.py")
compact = _load("hub_compact_i18n_under_test", "hub_compact.py")


def load_hub():
    spec = importlib.util.spec_from_file_location("hub_i18n_ja_zh_under_test", HUB)
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


hub = load_hub()


def hub_literal(name):
    """ค่าของตัวแปรระดับบนใน hub.py อ่านด้วย ast (ตารางข้อความเป็น literal ล้วน)"""
    with open(HUB, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == name:
            return ast.literal_eval(n.value)
    raise AssertionError("no literal %s in hub.py" % name)


def same_placeholders(tc, en, other, where):
    tc.assertEqual(sorted(PLACEHOLDER.findall(en)), sorted(PLACEHOLDER.findall(other)), where)


class RegistryTests(unittest.TestCase):
    def test_langs_and_meta(self):
        self.assertEqual(i18n.LANGS, LANGS)
        self.assertEqual(sorted(i18n.META), sorted(LANGS))
        for code in LANGS:
            m = i18n.META[code]
            self.assertTrue(m["name"] and m["english"] and m["short"], code)
            self.assertRegex(m["locale"], r"^[a-z]{2}-[A-Z]{2}$")
        self.assertEqual(i18n.locale_of("zh"), "zh-CN")
        self.assertEqual(i18n.english_name("ja"), "Japanese")

    def test_norm_lang(self):
        self.assertEqual(i18n.norm_lang("zh-CN"), "zh")
        self.assertEqual(i18n.norm_lang("JA_jp"), "ja")
        self.assertEqual(i18n.norm_lang(" en "), "en")
        self.assertEqual(i18n.norm_lang("xx"), "th")
        self.assertIsNone(i18n.norm_lang("xx", default=None))
        self.assertEqual(i18n.norm_lang(None), "th")
        self.assertEqual(i18n.norm_lang(5), "th")

    def test_pick_falls_back_to_english_then_thai(self):
        self.assertEqual(i18n.pick({"th": "ท", "en": "e", "ja": "じ"}, "ja"), "じ")
        self.assertEqual(i18n.pick({"th": "ท", "en": "e"}, "ja"), "e")
        self.assertEqual(i18n.pick({"th": "ท"}, "zh"), "ท")
        self.assertEqual(i18n.pick({"th": "ท", "en": "e", "zh": None}, "zh"), "e")     # None = ยังไม่แปล
        self.assertEqual(i18n.pick({}, "en", "dflt"), "dflt")
        self.assertEqual(i18n.pick("not a dict", "en", "dflt"), "dflt")
        self.assertEqual(i18n.tr("zh", th="ท", en="e", zh="中"), "中")
        self.assertEqual(i18n.tr("zh", th="ท", en="e"), "e")

    def test_complete_fills_every_language(self):
        out = i18n.complete({"th": {"a": "ท", "b": "ข"}, "en": {"a": "A"}, "ja": {"a": "あ"}})
        self.assertEqual(sorted(out), sorted(LANGS))
        self.assertEqual(out["ja"], {"a": "あ", "b": "ข"})          # b: ไม่มีอังกฤษ → ไทย
        self.assertEqual(out["zh"], {"a": "A", "b": "ข"})          # a: ไม่มีจีน → อังกฤษ
        self.assertEqual(out["en"], {"a": "A", "b": "ข"})


class ApiCatalogTests(unittest.TestCase):
    def test_every_entry_has_ja_and_zh(self):
        for en, tr in i18n.API_TEXTS.items():
            self.assertTrue(tr.get("ja") and tr.get("zh"), en)
            self.assertTrue(KANA.search(tr["ja"]) or HAN.search(tr["ja"]), en)
            self.assertTrue(HAN.search(tr["zh"]), en)
            self.assertFalse(THAI.search(tr["ja"]) or THAI.search(tr["zh"]), en)
            # %d/%s ต้องไม่มากกว่าอังกฤษ (น้อยกว่าได้: ไม่มี "s" พหูพจน์ใน ja/zh)
            n_en = len(re.findall(r"%[sd]", en))
            for code in ("ja", "zh"):
                self.assertLessEqual(len(re.findall(r"%[sd]", tr[code])), n_en, (en, code))

    def test_exact_and_template_translation(self):
        self.assertEqual(i18n.translate_api("method not allowed", "zh"), "不支持该方法")
        self.assertIsNone(i18n.translate_api("method not allowed", "en"))
        self.assertIsNone(i18n.translate_api("not in the catalog at all", "ja"))
        self.assertEqual(i18n.translate_api("audio larger than 64 MB", "zh"), "音频超过 64 MB")
        self.assertEqual(i18n.translate_api("text is longer than 2000 characters", "ja"), "テキストが 2000 文字を超えています")
        self.assertEqual(i18n.translate_api("Summarizing the earlier part of this chat… (3 turns)", "ja"),
                         "このチャットの前半を要約しています… (3 ターン)")
        self.assertEqual(i18n.translate_api("Summarized the earlier part of this conversation (1 turn)", "zh"),
                         "已总结这段对话的前半部分 (1 轮)")
        # ข้อความซ้อน: "invalid GPU choice: <model>: unknown model" แปลส่วนในด้วย
        self.assertEqual(i18n.translate_api("invalid GPU choice: qwen: unknown model", "zh"), "无效的 GPU 选择：qwen: 未知的模型")
        self.assertEqual(i18n.translate_api(" (code 1)", "ja"), " (コード 1)")

    def test_localize_fields_adds_ja_zh_next_to_en(self):
        body = {"error": "x", "error_th": "ไม่พบ", "error_en": "not found",
                "nested": {"items": [{"message_th": "ก", "message_en": "Restarting the model server…"}]},
                "note_th": "น", "note_en": "nothing in the catalog", "error_ja": "既にある"}
        out = i18n.localize_fields(body)
        self.assertIs(out, body)
        self.assertEqual(out["error_zh"], "未找到")
        self.assertEqual(out["error_ja"], "既にある")                    # ของเดิมชนะ
        self.assertEqual(out["nested"]["items"][0]["message_ja"], "モデルサーバーを再起動しています…")
        self.assertNotIn("note_ja", out)                                # ไม่มีในแคตตาล็อก = ไม่เติม (หน้าถอยไปอังกฤษ)
        self.assertEqual(i18n.localize_fields([1, "x", None]), [1, "x", None])
        self.assertEqual(i18n.localize_fields("plain"), "plain")

    def test_paired(self):
        out = i18n.paired("error", "ja", "ไทย", "invalid id")
        self.assertEqual(out["error_ja"], "id が無効です")
        self.assertEqual(out["error"], "id が無効です")
        self.assertEqual(i18n.paired("error", "en", "ไทย", "invalid id")["error"], "invalid id")
        self.assertEqual(i18n.paired("error", "zh", "ไทย", "no such text")["error"], "no such text")


class HubStringsTests(unittest.TestCase):
    def test_hub_strings_four_languages(self):
        strings = hub_literal("STRINGS")
        self.assertEqual(sorted(strings), sorted(LANGS))
        for code in LANGS:
            self.assertEqual(sorted(strings[code]), sorted(strings["en"]), code)
        for k, en in strings["en"].items():
            for code in ("ja", "zh"):
                v = strings[code][k]
                self.assertTrue(v.strip(), (code, k))
                same_placeholders(self, en, v, (code, k))
                self.assertEqual(("\n" in en), ("\n" in v), (code, k))
                self.assertFalse(THAI.search(v) and k not in ("note4",), (code, k))      # note4 อ้างปุ่ม "ไทย"

    def test_strings_ui_four_languages(self):
        ui = parts.STRINGS_UI
        self.assertEqual(sorted(ui), sorted(LANGS))
        for code in LANGS:
            self.assertEqual(sorted(set(ui[code]) ^ set(ui["en"])), [], code)
        for k, en in ui["en"].items():
            for code in ("ja", "zh"):
                v = ui[code][k]
                self.assertTrue(v.strip(), (code, k))
                same_placeholders(self, en, v, (code, k))
                self.assertFalse(THAI.search(v), (code, k))
        # ป้ายของปุ่มสลับภาษาครบทั้งสี่ในทุกภาษา
        for code in LANGS:
            for tip in ("lang_tip_th", "lang_tip_en", "lang_tip_ja", "lang_tip_zh"):
                self.assertIn("Alt+Shift+L", ui[code][tip], (code, tip))

    def test_ja_zh_really_are_ja_zh(self):
        ui = parts.STRINGS_UI
        ja_cjk = sum(1 for v in ui["ja"].values() if KANA.search(v) or HAN.search(v))
        zh_han = sum(1 for v in ui["zh"].values() if HAN.search(v))
        self.assertGreater(ja_cjk, 0.9 * len(ui["ja"]))
        self.assertGreater(zh_han, 0.9 * len(ui["zh"]))
        # จีนตัวย่อ ไม่ใช่ตัวเต็ม: คำที่พบบ่อยต้องเป็นรูปตัวย่อ
        blob = "\n".join(ui["zh"].values())
        for trad in ("設置", "對話", "檔案", "開啟", "關閉", "語言"):
            self.assertNotIn(trad, blob, trad)

    def test_merged_strings_fall_back_to_english(self):
        # STRINGS ที่ hub รวมแล้ว: ทุกภาษามีทุกคีย์ (hub + parts) — คีย์ที่ภาษานั้นไม่มีได้อังกฤษ ไม่ใช่ชื่อคีย์ดิบ
        for code in LANGS:
            self.assertEqual(sorted(hub.STRINGS[code]), sorted(hub.STRINGS["en"]), code)
        self.assertEqual(hub.T("ja")["projects"], "プロジェクト")
        self.assertEqual(hub.T("zh")["sidebar"], "侧边栏")
        ui = hub._parts.STRINGS_UI          # โมดูลที่ hub ใช้จริง (ไม่ใช่สำเนา parts ของเทสต์นี้)
        removed = ui["ja"].pop("sidebar")
        try:
            hub._merge_strings()
            self.assertEqual(hub.STRINGS["ja"]["sidebar"], hub.STRINGS["en"]["sidebar"])
        finally:
            ui["ja"]["sidebar"] = removed
            hub._merge_strings()
        self.assertEqual(hub.STRINGS["ja"]["sidebar"], "サイドバー")

    def test_lang_setting_accepts_four_codes(self):
        self.assertEqual(hub.lang_preview("lang=ja"), "ja")
        self.assertEqual(hub.lang_preview("lang=zh-CN"), "zh")
        self.assertIsNone(hub.lang_preview("lang=xx"))
        self.assertIsNone(hub.lang_preview(""))
        self.assertEqual(hub.LANGS, LANGS)
        self.assertIn("ja", hub._STT_LANGS)
        self.assertIn("zh", hub._STT_LANGS)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(hub, "SETTINGS", hub.Path(d) / "settings.json"):
                self.assertFalse(hub.set_lang("xx"))
                self.assertFalse(hub.set_lang(None))
                self.assertTrue(hub.set_lang("ZH-cn"))
                self.assertEqual(hub.get_lang(), "zh")
                self.assertEqual(hub.load_settings()["lang"], "zh")
                self.assertTrue(hub.set_lang("ja"))
                self.assertEqual(hub.get_lang(), "ja")

    def test_model_notes_four_languages(self):
        for name in ("S07_BANNER", "S07_END", "KB_HEADS", "KB_TAILS", "MENTION_HEADS", "REPLY_LANG", "OFFICE_NOTES",
                     "CREATIVE_NOTES", "DECISION_NOTES"):
            table = getattr(hub, name)
            self.assertEqual(sorted(table), sorted(LANGS), name)
            for code in ("ja", "zh"):
                same_placeholders(self, table["en"], table[code], (name, code))
                self.assertFalse(THAI.search(table[code]), (name, code))
        self.assertIn("日本語", hub.REPLY_LANG["ja"])
        self.assertIn("简体中文", hub.REPLY_LANG["zh"])
        # เครื่องหมายของหมายเหตุ Office/creative ครบทุกภาษา (กันใส่ซ้ำ)
        for code in LANGS:
            self.assertTrue(any(hub.OFFICE_NOTES[code].startswith(m) for m in hub._OFFICE_NOTE_MARKS), code)
            self.assertTrue(any(hub.CREATIVE_NOTES[code].startswith(m) for m in hub._OFFICE_NOTE_MARKS), code)

    def test_ctx_lang_detects_four_scripts(self):
        cases = {
            "สรุปไฟล์ station-b-inspection.pdf": "th",
            "What does 'ฉนวน' mean?": "en",
            "このファイルを要約して": "ja",
            "東京タワーの高さは？": "ja",
            "请总结这个文件": "zh",
            "北京的人口是多少": "zh",
            "PDFを読んで summary.pdf": "ja",
            "帮我看看 report.docx 里的数据": "zh",
        }
        for text, want in cases.items():
            self.assertEqual(hub.ctx_lang(text), want, text)
        # ไม่มีตัวอักษรเลย = ภาษาของหน้าเว็บ (ทั้งสี่)
        for code in LANGS:
            with mock.patch.object(hub, "get_lang", return_value=code):
                self.assertEqual(hub.ctx_lang("123 456"), code)

    def test_notes_follow_the_users_language(self):
        ja = hub.kb_result_text([{"head": "a.pdf · p1", "snippet": "hello"}], "ja")
        self.assertTrue(ja.startswith(hub.S07_BANNER["ja"]))
        self.assertTrue(ja.endswith(hub.REPLY_LANG["ja"]))
        self.assertIn(hub.KB_TAILS["ja"] % "a.pdf", ja)
        zh = hub.creative_video_note("请生成一个2秒的视频，无人机飞过火山", {"local_do"})
        self.assertTrue(zh.startswith(hub.CREATIVE_NOTES["zh"][:20]), zh[:60])
        self.assertIn('prompt="<场景描述>"', zh)
        self.assertEqual(hub.creative_video_note("この動画を圧縮して", {"local_do"}), "")        # ตัดต่อ ไม่ใช่สร้างใหม่
        ja_note = hub.creative_video_note("短い動画を作ってください。火山の上を飛ぶドローン", {"local_do"})
        self.assertTrue(ja_note.startswith(hub.CREATIVE_NOTES["ja"][:20]), ja_note[:60])
        self.assertEqual(hub.auto_kb_skip("打开的 Excel 中选中的数据，帮我总结一下"), "office")
        self.assertEqual(hub.auto_kb_skip("開いているExcelの選択範囲を要約して"), "office")
        self.assertTrue(hub.office_read_note("打开的 Excel 中选中的数据，帮我总结一下", {"local_read"}).startswith("[系统备注"))
        self.assertEqual(hub.auto_kb_skip("ありがとうございます！"), "smalltalk")
        self.assertEqual(hub.auto_kb_skip("谢谢，知道了。"), "smalltalk")
        self.assertIn("use Japanese", hub.base_system_prompt("qwen3.8", "ja"))
        self.assertIn("use Chinese (Simplified)", hub.base_system_prompt("qwen3.8", "zh"))

    def test_chat_too_large_body_localized(self):
        body = hub.chat_too_large_body("zh")
        self.assertIn("error_zh", body)
        self.assertEqual(body["error"]["message"], body["error_zh"])
        self.assertEqual(body["error"]["code"], 413)
        self.assertEqual(hub.chat_too_large_body("en")["error"]["message"], hub.chat_too_large_body("en")["error_en"])

    def test_gpu_job_snapshot_has_four_messages(self):
        with mock.patch.dict(hub._gpu_job, {"state": "failed", "rc": 3, "log": None, "timeout": False}):
            snap = hub.gpu_job_snapshot()
        self.assertEqual(snap["message_en"], "Restart failed — see gpu-apply.log (code 3)")
        self.assertEqual(snap["message_ja"], "再起動に失敗しました — gpu-apply.log を確認してください (コード 3)")
        self.assertEqual(snap["message_zh"], "重启失败 — 请查看 gpu-apply.log (代码 3)")
        self.assertIn(snap["message"], (snap["message_th"], snap["message_en"], snap["message_ja"], snap["message_zh"]))


NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
HAVE_NODE = os.path.isfile(NODE) if os.path.isabs(NODE) else bool(shutil.which("node"))
STATIC = os.path.join(PROJ, "static")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def js_block(src, start):
    """ข้อความตั้งแต่ start ถึงวงเล็บปีกกา/เหลี่ยมที่ปิดสมดุล (สำหรับดึง var X = {...} ออกมารันใน node)"""
    depth, j = 0, start
    while True:
        c = src[j]
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1


def js_function(src, name):
    m = re.search(r"\n  function %s\(" % re.escape(name), src)
    if not m:
        raise AssertionError("function %s not found" % name)
    return js_block(src, m.start() + 1)


def run_node(code):
    fd, fn = tempfile.mkstemp(suffix=".js", prefix="i18ntest-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(code)
        r = subprocess.run([NODE, fn], capture_output=True, text=True, encoding="utf-8", timeout=60)
    finally:
        os.remove(fn)
    if r.returncode:
        raise AssertionError("node error: " + (r.stderr or "")[-1500:])
    return json.loads(r.stdout)


class WebUILayerTests(unittest.TestCase):
    """ชั้น WebUI (static/*.js): พจนานุกรม ja/zh ครบคีย์เดียวกับไทย กติกา regex ครบสามภาษา และสคริปต์เล็กมีตาราง ja/zh"""

    @classmethod
    def setUpClass(cls):
        cls.src = read(os.path.join(STATIC, "webui-enhance.js"))

    def grab(self, marker, end="\n  };\n"):
        i = self.src.index(marker)
        j = self.src.index(end, i)
        return self.src[i:j + len(end)]

    def dict_code(self):
        s = self.src
        parts = [self.grab("  var TH = {"), self.grab("  var GLUE_RE = new RegExp(", '"g");\n'), js_function(s, "glue"),
                 self.grab("  var JA = {"), self.grab("  var ZH = {"),
                 "  var WORDS = { th: TH, ja: JA, zh: ZH };\n  function hasOwn(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }\n"
                 "  function hasDict(l) { return hasOwn(WORDS, l); }\n  var APP_NAME = \"Qwen3.8\";\n",
                 self.grab("  var STAT_UNIT = {")]
        i = s.index("  var DUR = {")
        parts.append(s[i:s.index("\n  var TH_RE = RULES;", i) + 1])
        parts += [self.grab("  var FRAG = {"), self.grab("  var TITLE_WORDS = {", " };\n"), js_function(s, "titleOf"),
                  "  var THAI = /[\\u0e00-\\u0e7f]/;\n  function txKey(s) { return s.replace(/\\s+/g, \" \").trim().replace(/…/g, \"...\"); }\n",
                  js_function(s, "wordOf")]
        return "\n".join(parts)

    def test_static_shape(self):
        s = self.src
        self.assertIn("var WORDS = { th: TH, ja: JA, zh: ZH };", s)
        self.assertIn("function hasDict(l) { return hasOwn(WORDS, l); }", s)
        self.assertIn("var B2B = { th: TH_B2B, ja: JA_B2B, zh: ZH_B2B };", s)
        self.assertIn("var B3 = { th: TH_B3, ja: JA_B3, zh: ZH_B3 };", s)
        self.assertIn('var LOCALE = { th: "th-TH", en: "en-GB", ja: "ja-JP", zh: "zh-CN" };', s)
        # ไม่มีทางแยกไทย/อังกฤษแบบสองค่าเหลืออยู่ในตัวแปล (ยกเว้น word joiner ที่ใส่เฉพาะไทย)
        for bad in ('l !== "th" ||', 'lang() === "th" ?', 'lang() !== "th") return', 'l === "th" && LETTER',
                    "function thTitle(", "FRAG_TH", "STAT_UNIT_TH", "NO_UNDO_TH", "thVerb("):
            self.assertNotIn(bad, s, bad)
        self.assertIn('var s = d && (d["error_" + lang()] || d.error_en || d.error_th);', s)
        # STR ครบสี่ภาษา
        for code in ("th", "en", "ja", "zh"):
            self.assertRegex(s, r"\n    %s: \{\n      greet: \[" % code)

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_dictionaries_and_rules(self):
        out = run_node(self.dict_code() + r"""
var cjk = /[\u3040-\u30ff\u3400-\u9fff]/, han = /[\u3400-\u9fff]/, thai = /[\u0e00-\u0e7f]/;
var keys = Object.keys(TH).sort();
var out = {
  same: JSON.stringify(keys) === JSON.stringify(Object.keys(JA).sort()) && JSON.stringify(keys) === JSON.stringify(Object.keys(ZH).sort()),
  n: keys.length,
  emptyJa: keys.filter(function (k) { return TH[k] && !JA[k]; }), emptyZh: keys.filter(function (k) { return TH[k] && !ZH[k]; }),
  thaiJa: keys.filter(function (k) { return thai.test(JA[k]); }), thaiZh: keys.filter(function (k) { return thai.test(ZH[k]); }),
  cjkJa: keys.filter(function (k) { return JA[k] && cjk.test(JA[k]); }).length, hanZh: keys.filter(function (k) { return ZH[k] && han.test(ZH[k]); }).length,
  ph: keys.filter(function (k) { var p = (k.match(/\{[a-z]+\}/g) || []).sort().join(); return p !== (JA[k].match(/\{[a-z]+\}/g) || []).sort().join() || p !== (ZH[k].match(/\{[a-z]+\}/g) || []).sort().join(); }),
  rules: RULES.length,
  rulesAll: RULES.every(function (r) { return r[0] instanceof RegExp && typeof r[1].th === "function" && typeof r[1].ja === "function" && typeof r[1].zh === "function"; }),
  settings: ["th", "ja", "zh", "en"].map(function (l) { return wordOf("Settings", l); }),
  speed: ["th", "ja", "zh"].map(function (l) { return wordOf("12.3 tokens/s", l); }),
  dur: ["th", "ja", "zh"].map(function (l) { return wordOf("2min 22s", l); }),
  del: ["th", "ja", "zh"].map(function (l) { return wordOf('Delete "My chat"? This action cannot be undone.', l); }),
  sel: ["th", "ja", "zh"].map(function (l) { return wordOf("Select รายงาน", l); }),
  title: ["th", "ja", "zh"].map(function (l) { return titleOf("Chat - llama-ui", l); }),
  none: wordOf("not a key at all", "ja"),
  frag: ["th", "ja", "zh"].every(function (l) { return FRAG[l]["Are you sure you want to delete"] && FRAG[l]["? This action cannot be undone."]; })
};
console.log(JSON.stringify(out));
""")
        self.assertTrue(out["same"])
        self.assertGreater(out["n"], 700)
        self.assertEqual(out["emptyJa"], [])
        self.assertEqual(out["emptyZh"], [])
        self.assertEqual(out["thaiJa"], [])
        self.assertEqual(out["thaiZh"], [])
        self.assertGreater(out["cjkJa"], 0.95 * out["n"])
        self.assertGreater(out["hanZh"], 0.95 * out["n"])
        self.assertEqual(out["ph"], [])
        self.assertGreaterEqual(out["rules"], 76)
        self.assertTrue(out["rulesAll"])
        self.assertEqual(out["settings"][1:], ["設定", "设置", None])
        self.assertEqual(out["speed"][1:], ["12.3 トークン/秒", "12.3 token/秒"])
        self.assertEqual(out["dur"][1:], ["2 分 22 秒", "2 分 22 秒"])
        self.assertEqual(out["del"][1], '"My chat" を削除しますか？元に戻せません。')
        self.assertEqual(out["del"][2], '删除 "My chat"？无法撤销。')
        self.assertEqual(out["sel"], ["เลือก รายงาน", "รายงาน を選択", "选择 รายงาน"])      # ชื่อแชตคงเดิม
        self.assertEqual(out["title"], ["แชต - Qwen3.8", "チャット - Qwen3.8", "对话 - Qwen3.8"])
        self.assertIsNone(out["none"])
        self.assertTrue(out["frag"])

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_b2b_b3_same_keys(self):
        s = self.src
        code = "\n".join(js_block(s, s.index("var %s = {" % n)).replace("var %s =" % n, "const %s =" % n, 1)
                         for n in ("TH_B2B", "JA_B2B", "ZH_B2B", "TH_B3", "JA_B3", "ZH_B3"))
        out = run_node(code + "\nconsole.log(JSON.stringify({b2b: [Object.keys(TH_B2B), Object.keys(JA_B2B), Object.keys(ZH_B2B)],"
                       " b3: [Object.keys(TH_B3), Object.keys(JA_B3), Object.keys(ZH_B3)], ja: JA_B2B, zh: ZH_B2B}));")
        self.assertEqual(sorted(out["b2b"][0]), sorted(out["b2b"][1]))
        self.assertEqual(sorted(out["b2b"][0]), sorted(out["b2b"][2]))
        self.assertEqual(sorted(out["b3"][0]), sorted(out["b3"][1]))
        self.assertEqual(sorted(out["b3"][0]), sorted(out["b3"][2]))
        for k in out["b2b"][0]:
            for ph in re.findall(r"\{[a-z]+\}", k):
                self.assertIn(ph, out["ja"][k], (k, ph))
                self.assertIn(ph, out["zh"][k], (k, ph))

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_speak_chunks_pick_cjk_voices(self):
        code = ("var THAI_CH = /[\\u0E00-\\u0E7F]/;\nfunction lang() { return 'ja'; }\n" + js_function(self.src, "speakChunks") + r"""
var out = { ja: speakChunks("東京タワーの高さは 333 メートルです。"), zh: speakChunks("北京的人口大约有两千万。"),
  mixed: speakChunks("まず Heartbeat を確認してください then check the WebSocket ping interval twice"), th: speakChunks("สวัสดีครับ ทดสอบ") };
console.log(JSON.stringify(out));
""")
        out = run_node(code)
        self.assertEqual([c["lang"] for c in out["ja"]], ["ja-JP"])
        self.assertEqual([c["lang"] for c in out["zh"]], ["ja-JP"])      # หน้าเป็นญี่ปุ่น: อักษรฮั่นล้วนอ่านด้วยเสียงญี่ปุ่น
        self.assertEqual([c["lang"] for c in out["mixed"]], ["ja-JP", "en-US"])
        self.assertEqual([c["lang"] for c in out["th"]], ["th-TH"])

    def test_small_scripts_have_ja_zh(self):
        # browser-panel.js: ทุกคีย์ของ STR มี 4 ข้อความ [th, en, ja, zh]
        bp = read(os.path.join(STATIC, "browser-panel.js"))
        self.assertIn('var LANG_IDX = { th: 0, en: 1, ja: 2, zh: 3 };', bp)
        block = js_block(bp, bp.index("var STR = {"))
        arrays = re.findall(r"\w+: \[((?:\s*\"(?:[^\"\\]|\\.)*\",?\s*)+)\]", block)
        self.assertGreater(len(arrays), 30)
        for arr in arrays:
            vals = re.findall(r'"(?:[^"\\]|\\.)*"', arr)
            self.assertEqual(len(vals), 4, arr[:60])
        # สคริปต์ที่ใช้คู่ (อังกฤษ, ไทย): ทุกข้อความอังกฤษที่เป็น literal มีคำแปล ja/zh ในตาราง JZ
        for name, fn, order in (("message-queue.js", "T", "th-en"), ("auto-recovery.js", "text", "en-th"),
                                ("shared-chats.js", "label", "en-th"), ("durable-chats.js", "label", "en-th")):
            src = read(os.path.join(STATIC, name))
            jz = json.loads(js_block(src, src.index("var JZ = ") + len("var JZ = ")))
            calls = re.findall(r"\b%s\(\s*(\"(?:[^\"\\]|\\.)*\")\s*,\s*(\"(?:[^\"\\]|\\.)*\")\s*\)" % fn, src, re.S)
            self.assertGreater(len(calls), 5, name)
            for a, b in calls:
                en = json.loads(b if order == "th-en" else a)
                self.assertIn(en, jz, (name, en))
                self.assertEqual(len(jz[en]), 2, (name, en))
                for ph in re.findall(r"\{[a-z]+\}", en):
                    self.assertIn(ph, jz[en][0], (name, en))
                    self.assertIn(ph, jz[en][1], (name, en))
            for en, pair in jz.items():
                self.assertFalse(THAI.search(pair[0]) or THAI.search(pair[1]), (name, en))


class ShellMarkupTests(unittest.TestCase):
    def test_four_buttons_in_both_pages(self):
        for tpl, group in ((parts.SHELL, "langSw"), (parts.PAGE, "lang")):
            m = re.search(r'<div class="lsw" id="%s"[^>]*>(.*?)</div>' % group, tpl, re.S)
            self.assertIsNotNone(m, group)
            codes = re.findall(r'data-lang="([a-z]+)" lang="\1"', m.group(1))
            self.assertEqual(codes, list(LANGS), group)
            for code in LANGS:
                self.assertIn("__T_lang_tip_%s__" % code, m.group(1), (group, code))
            self.assertIn(">日本語</button>", m.group(1))
            self.assertIn(">中文</button>", m.group(1))

    def test_switcher_logic_is_four_way(self):
        for tpl in (parts.SHELL, parts.PAGE):
            self.assertIn("var LANGS = ['th', 'en', 'ja', 'zh'];", tpl)
            self.assertIn("function nextLang(v) { return LANGS[(LANGS.indexOf(v) + 1) % LANGS.length]; }", tpl)
            self.assertIn("if (LANGS.indexOf(v) < 0 || v === LANG || langBusy) return;", tpl)
            self.assertNotIn("v !== 'th' && v !== 'en'", tpl)
            self.assertNotIn("LANG === 'th' ? 'en' : 'th'", tpl)
            self.assertIn("setLang(nextLang(LANG)", tpl)
            # จอแคบแสดงปุ่มของภาษาถัดไปปุ่มเดียว (data-next) — สคริปต์ก่อนวาดภาพแรกตั้งให้ด้วย
            self.assertIn("if (v === n) b.setAttribute('data-next', 'true');", tpl)
        self.assertIn('.lsw button[data-lang][data-next="true"]{display:inline-flex}', parts.SHELL)
        self.assertIn("['ja', '日本語', null, null, 'ja'], ['zh', '中文', null, null, 'zh']", parts.SHELL)
        self.assertIn("b['error_' + LANG] || b.error_en || b.error_th", parts.SHELL)
        self.assertIn("B3_LOCALE = { th: 'th-TH', en: 'en-GB', ja: 'ja-JP', zh: 'zh-CN' }", parts.PAGE)

    def test_fonts_per_language(self):
        with open(os.path.join(PROJ, "static", "tokens.css"), encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn('html[lang="ja"]', css)
        self.assertIn('html[lang="zh"]', css)
        self.assertIn("Yu Gothic UI", css)
        self.assertIn("Microsoft YaHei UI", css)

    def test_webui_layer_accepts_ui_langs(self):
        with open(os.path.join(PROJ, "static", "webui-enhance.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn('var UI_LANGS = ["th", "en", "ja", "zh"];', js)
        self.assertIn("return sh && UI_LANGS.indexOf(sh.lang) >= 0 ? sh.lang : null;", js)


class DoctorTests(unittest.TestCase):
    def test_tables(self):
        self.assertEqual(sorted(doctor.STATE_WORD), sorted(LANGS))
        for code in LANGS:
            self.assertEqual(sorted(doctor.STATE_WORD[code]), sorted(doctor.STATE_WORD["en"]), code)
            self.assertEqual(sorted(doctor.REPORT_TEXT[code]), sorted(doctor.REPORT_TEXT["en"]), code)
            for k, v in doctor.REPORT_TEXT["en"].items():
                same_placeholders(self, v, doctor.REPORT_TEXT[code][k], (code, k))
        self.assertEqual(sorted(doctor.FIX_JA_ZH), sorted(doctor.FIX), "ทุกคำแนะนำต้องมี ja/zh")
        for key, (th, en) in doctor.FIX.items():
            ja, zh = doctor.FIX_JA_ZH[key]
            same_placeholders(self, en, ja, (key, "ja"))
            same_placeholders(self, en, zh, (key, "zh"))
            self.assertFalse(THAI.search(ja) or THAI.search(zh), key)
        for sid in ("router", "mcp_local", "mcp_web", "embed", "stt", "scheduler", "gateway", "hub"):
            self.assertIn(sid, doctor.SERVICE_NAMES)

    def test_fix_texts_and_docker_reason(self):
        t = doctor.fix_texts("disk", ("C:", 3.456))
        self.assertEqual(t["en"], "Drive C: has 3.5 GB free → free up space or reboot (C: pagefile shrinks back ~20 GB)")
        self.assertIn("3.5 GB", t["ja"])
        self.assertIn("3.5 GB", t["zh"])
        dk = {"reason_th": "ยังไม่ได้ติดตั้ง Docker", "reason_en": "Docker is not installed"}
        self.assertEqual(doctor.docker_reason(dk, "ja"), "Docker がインストールされていません")
        self.assertEqual(doctor.docker_reason(dk, "zh"), "未安装 Docker")
        self.assertEqual(doctor.docker_reason(dk, "th"), "ยังไม่ได้ติดตั้ง Docker")
        self.assertEqual(doctor.docker_reason({"reason_en": "something new"}, "zh"), "something new")

    def _rep(self):
        return {
            "overall": "warn", "checked_at": "2026-11-09 10:00",
            "services": [doctor._row("router", "ตัวจัดการโมเดล (llama-server)", "Model router (llama-server)", 8099, "ok", 12,
                                     loaded=[{"id": "qwen3.8"}]),
                         doctor._row("hub", "ฮับ + พอร์ตโปรเจกต์", "Hub + project ports", 8100, "ok", None,
                                     ports=[{"state": "ok"}], keep_awake=0, heartbeat_message="ข้อความไทยจาก scheduler")],
            "versions": {"llama_cpp": "b1", "python": "3.13", "os": "Windows 11"}, "gpu": [],
            "memory": {"ram_free_gb": 10, "ram_total_gb": 64, "commit_free_gb": 5, "commit_limit_gb": 70},
            "disks": [{"drive": "C:", "present": True, "free_gb": 30.5, "total_gb": 500}, {"drive": "E:", "present": False}],
            "keys": {"local_token": True, "brave_key": False, "gateway_key": True},
            "docker": {"usable": False, "off": True, "reason_th": "ปิด Python sandbox ไว้",
                       "reason_en": "the Python sandbox is off · Python code runs on this PC after you approve it"},
            "tests": {"at": "x", "ran": 1860, "failures": 0, "errors": 0, "skipped": 54},
            "fixes": [{"id": "brave", "th": "ท", "en": "e", "ja": "じ", "zh": "中"}, {"id": "new", "th": "ท2", "en": "e2"}],
            "errors": [],
        }

    def test_localize_and_report_text(self):
        rep = self._rep()
        for code in ("ja", "zh"):
            loc = doctor.localize(rep, code)
            self.assertEqual(loc["lang"], code)
            names = {s["id"]: s["name"] for s in loc["services"]}
            self.assertEqual(names["router"], doctor.SERVICE_NAMES["router"][code])
            self.assertIsNone(loc["services"][1]["heartbeat_message"])      # ข้อความไทยของ scheduler ไม่โชว์ปนภาษาอื่น
            self.assertFalse(THAI.search(loc["docker"]["reason"]))
            text = doctor.report_text(rep, code)
            self.assertFalse(THAI.search(text), text)
            self.assertIn("- じ" if code == "ja" else "- 中", text)
            self.assertIn("- e2", text)                                  # คำแนะนำที่ยังไม่มีคำแปล → อังกฤษ
            self.assertIn("qwen3.8", text)
            self.assertIn("30.5/500.0 GB", text)
        self.assertEqual(doctor.localize(rep, "th")["lang"], "th")
        self.assertEqual(doctor.localize(rep, "en")["lang"], "en")
        self.assertIn("Qwen3.8 — system check", doctor.report_text(rep, "en"))
        self.assertIn("Qwen3.8 — รายงานตรวจระบบ", doctor.report_text(rep, "th"))

    def test_fixes_rows_carry_ja_zh(self):
        d = doctor.Doctor({})
        rep = self._rep()
        rep["services"] = [doctor._row(k, k, k, None, "down" if k == "router" else "ok", None)
                           for k in ("router", "mcp_local", "mcp_web", "embed", "stt", "scheduler", "gateway", "hub")]
        rep["docker"] = {"usable": False, "stopped": True, "reason_th": "ติดตั้ง Docker Desktop ไว้แต่ engine ไม่ทำงาน",
                         "reason_en": "Docker Desktop is installed but its engine is not running"}
        rep["_meta"] = {"gpu_error": None}
        rep["tests"] = None
        fixes = {f["id"]: f for f in d._fixes(rep)}
        self.assertEqual(fixes["router"]["ja"], doctor.FIX_JA_ZH["router"][0])
        self.assertEqual(fixes["router"]["zh"], doctor.FIX_JA_ZH["router"][1])
        self.assertIn("Docker Desktop はインストール済みですがエンジンが動いていません", fixes["docker"]["ja"])
        self.assertIn("已安装 Docker Desktop，但引擎未运行", fixes["docker"]["zh"])


class CompactionTests(unittest.TestCase):
    def test_tables(self):
        for name in ("HEADINGS", "LANG_NAME", "DIGEST_LABELS", "BACKFILL_HEADS", "CARRY_HEADS", "ADDED_HEADS", "SUMMARY_HEADS"):
            table = getattr(compact, name)
            self.assertEqual(sorted(table), sorted(LANGS), name)
        for kind in ("partial", "down"):
            self.assertEqual(sorted(compact.DIGEST_HEADS[kind]), sorted(LANGS), kind)
        for code in LANGS:
            self.assertEqual(sorted(compact.DIGEST_LABELS[code]), sorted(compact.DIGEST_LABELS["en"]), code)
            self.assertEqual(compact.HEADINGS[code].count("\n"), compact.HEADINGS["en"].count("\n"), code)
            same_placeholders(self, compact.SUMMARY_HEADS["en"], compact.SUMMARY_HEADS[code], code)
            # หัวข้อของทุกภาษาถูกจัดชนิดได้เหมือนกัน (ตัดสินใจ/ค้าง/อื่นๆ)
            kinds = [compact._heading_kind(h) for h in compact.HEADINGS[code].split("\n")]
            self.assertEqual(kinds, ["decision", "open", "other", "other", "other"], code)
        self.assertEqual(compact._lk("ja"), "ja")
        self.assertEqual(compact._lk("xx"), "en")

    def test_detect_lang(self):
        cases = {"สวัสดีครับ ช่วยสรุปไฟล์": "th", "Hello there, summarize this": "en",
                 "このファイルを要約してください": "ja", "请帮我总结这个文件的内容": "zh",
                 "日本語とEnglishの混在テキスト": "ja", "東京 Tokyo station timetable": "en"}
        for text, want in cases.items():
            self.assertEqual(compact.detect_lang([text]), want, text)
        self.assertEqual(compact.count_kana("カタカナ ひらがな 漢字"), 8)
        self.assertEqual(compact.count_han("漢字 abc 中文"), 4)
        self.assertEqual(compact.count_han("한글"), 0)

    def test_prompt_and_header_in_the_chat_language(self):
        msgs = compact.summary_prompt("", "chunk", "zh")
        system = msgs[0]["content"] if isinstance(msgs, list) else str(msgs)
        self.assertIn("Simplified Chinese", system)
        self.assertIn("## 决定与已约定事项（仍然有效）", system)
        head = compact.summary_message({"turns": 4, "lang": "ja", "summary": "x"})["content"]
        self.assertTrue(head.startswith(compact.LABEL))
        self.assertIn("これまでの 4 ターン", head)
        # บรรทัดการตัดสินใจอ่านได้จากสรุปภาษาญี่ปุ่น/จีน
        summ = "## 決定と合意事項（現在も有効）\n- K2 リレーを 10 月 15 日までに交換\n## 未完了のタスクと質問\n- 見積もり待ち"
        self.assertEqual(compact.decision_lines(summ), ["K2 リレーを 10 月 15 日までに交換"])
        summ = "## 决定与已约定事项（仍然有效）\n- 预算 48,500 泰铢\n## 事实与数字\n- 电压 230 V"
        self.assertEqual(compact.decision_lines(summ), ["预算 48,500 泰铢"])

    def test_open_and_approval_words(self):
        self.assertTrue(compact._OPEN_RE.search("承認待ちです"))
        self.assertTrue(compact._OPEN_RE.search("还没批准"))
        self.assertTrue(compact._PENDING_RE.search("待批准"))
        self.assertTrue(compact._APPROVE_RE.search("用户已批准"))
        self.assertTrue(compact._USER_OK_RE.search("可以，继续"))
        self.assertTrue(compact._USER_OK_RE.search("はい、お願いします"))


if __name__ == "__main__":
    unittest.main()
