# -*- coding: utf-8 -*-
"""
เทสต์หน้าเว็บของ batch 2a สัญญา B5 (owner stack): ส่วน "งานค้นคว้า" ในแผงโปรเจกต์, ก้อน "บริการ" ในเมนูบัญชี,
รายการ "ค้นคว้าเชิงลึก" ในเมนู "+" ของกล่องพิมพ์ (webui-enhance.js)

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

สิ่งที่ตรวจ
  * ข้อความใหม่มีครบทั้งไทยและอังกฤษ และทุก t('…') ในสคริปต์ของ shell มีคีย์ในทั้งสองภาษา (คีย์ที่ประกอบด้วย
    'res_st_' + สถานะ / 'res_ph_' + ช่วงงาน ครบทุกค่าที่ hub ส่ง)
  * หน้า shell ที่ hub สร้างจริงมีส่วนงานค้นคว้า ไม่มี placeholder ค้าง และข้อความตรงภาษา
  * ข้อความเติมคำขอของ shell (res_prefill) และของ enhance (researchPrefill) ตรงกันทุกตัวอักษรทั้งสองภาษา — ผู้ใช้กด
    จากแผงหรือจากเมนู "+" ต้องได้คำขอเดียวกัน (ไม่งั้นการตรวจ "มีคำนำหน้าอยู่แล้ว" จะเติมซ้ำ)
  * enhance.js: node --check ผ่าน, ต่อ researchMenu เข้ากับ observer ของ body, รายการที่ใส่มี data-qw-no-tx
  * สคริปต์ของ shell ไม่ใช้ innerHTML กับข้อมูลงานค้นคว้า (ข้อมูลจากไฟล์ที่ MCP เขียน = ไว้ใจไม่ได้)
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HUB = r"C:\LLM\projects\hub.py"
ENHANCE = r"C:\LLM\projects\static\webui-enhance.js"


def load_hub():
    sys.path.insert(0, os.path.dirname(HUB))
    spec = importlib.util.spec_from_file_location("hub_stack_b2_shell", HUB)
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


hub = load_hub()
SHELL, _PAGE = hub.templates()


def node_exe():
    for p in (shutil.which("node"), r"C:\Program Files\nodejs\node.exe"):
        if p and os.path.isfile(p):
            return p
    return None


def enhance_src():
    with open(ENHANCE, encoding="utf-8") as fh:
        return fh.read()


def research_block():
    s = SHELL.index("/* ---------------------------------------------------------------- งานค้นคว้าเชิงลึก (batch 2a")
    e = SHELL.index("$('#ppResNew').addEventListener", s)
    return SHELL[s:e]


class StringsTests(unittest.TestCase):
    def test_new_keys_in_both_languages(self):
        for lang in ("th", "en"):
            keys = [k for k in hub.STRINGS[lang] if k.startswith(("res_", "svc_"))]
            self.assertGreater(len(keys), 50, lang)
        th = {k for k in hub.STRINGS["th"] if k.startswith(("res_", "svc_"))}
        en = {k for k in hub.STRINGS["en"] if k.startswith(("res_", "svc_"))}
        self.assertEqual(th, en)
        for k in th:
            self.assertTrue(hub.STRINGS["th"][k].strip() and hub.STRINGS["en"][k].strip(), k)

    def test_every_shell_key_exists(self):
        used = set(re.findall(r"\bt(?:Raw)?\('([a-z0-9_]+)'\)", SHELL))
        for lang in ("th", "en"):
            missing = sorted(k for k in used if k not in hub.STRINGS[lang])
            self.assertEqual(missing, [], lang)

    def test_dynamic_status_and_phase_keys_cover_hub_values(self):
        states = set(hub._RESEARCH_STATE.values()) | {"unknown"}
        phases = set(hub._RESEARCH_PHASE.values())
        for lang in ("th", "en"):
            S = hub.STRINGS[lang]
            for st in states:
                self.assertIn("res_st_" + st, S, (lang, st))
            for ph in phases:
                self.assertIn("res_ph_" + ph, S, (lang, ph))
            for d in ("quick", "standard"):
                self.assertIn("res_depth_" + d, S)

    def test_english_page_has_no_thai_in_new_strings(self):
        thai = re.compile("[\u0e00-\u0e7f]")
        for k, v in hub.STRINGS["en"].items():
            if k.startswith(("res_", "svc_")):
                self.assertIsNone(thai.search(v), k)

    def test_prefill_text_is_identical_in_shell_and_enhance(self):
        src = enhance_src()
        # STR ของ enhance เรียง th แล้ว en
        self.assertEqual(re.findall(r'researchPrefill: "([^"]*)"', src),
                         [hub.STRINGS["th"]["res_prefill"], hub.STRINGS["en"]["res_prefill"]])
        labels = re.findall(r'\bresearch: "([^"]*)"', src)
        self.assertEqual(labels, [hub.STRINGS["th"]["svc_research"], hub.STRINGS["en"]["svc_research"]])


class ShellPageTests(unittest.TestCase):
    def build(self, lang):
        proj = {"slug": "p", "name": "P", "port": 8101, "system_prompt": "", "think": "off", "extend": True}
        with mock.patch.object(hub, "upstream_models", return_value=[]), \
                mock.patch.object(hub, "local_token", return_value=None):
            return hub.build_shell(proj, [proj], "", lang)

    def test_page_has_research_section_in_each_language(self):
        for lang in ("th", "en"):
            page = self.build(lang)
            for needle in ('id="ppRes"', 'id="ppResNew"', 'id="ppResList"', 'id="ppResAll"'):
                self.assertIn(needle, page, (lang, needle))
            self.assertNotIn("__T_res_", page)
            self.assertIn(hub.html.escape(hub.STRINGS[lang]["res_title"]), page)
            self.assertIn(hub.html.escape(hub.STRINGS[lang]["res_new"]), page)
        # ส่วนงานค้นคว้าอยู่ระหว่าง "ไฟล์ที่ Qwen สร้าง" กับ "การตั้งค่า"
        page = self.build("th")
        self.assertLess(page.index('id="ppOut"'), page.index('id="ppRes"'))
        self.assertLess(page.index('id="ppRes"'), page.index('aria-labelledby="ppSetH"'))

    def test_shell_api_and_menu_hooks(self):
        self.assertIn("startResearch: function", SHELL)
        self.assertIn("openResearch: function", SHELL)
        self.assertIn("var svc = svcNode();", SHELL)
        self.assertIn("describedby: svc ? 'menuHead mhSvc' : 'menuHead'", SHELL)
        self.assertIn("SVC = d.services && typeof d.services === 'object' ? d.services : null;", SHELL)
        self.assertIn("loadResearch();", SHELL[SHELL.index("function openPanel()"):SHELL.index("function closePanel(")])

    def test_research_ui_never_uses_innerhtml(self):
        block = research_block()
        self.assertNotIn("innerHTML", block)
        self.assertNotIn("insertAdjacentHTML", block)
        svc = SHELL[SHELL.index("function svcNode()"):SHELL.index("/* ---------------------------------------------------------------- หน้าต่างเลือก GPU")]
        self.assertNotIn("innerHTML", svc)
        # ลิงก์ไฟล์ผ่าน outUrl() (ยอมรับเฉพาะ /_qwen/out/<ชื่อ>) ไม่ใช้ URL จากข้อมูลตรงๆ
        self.assertIn("href: outUrl(f)", block)
        self.assertNotIn("href: f.url", block)

    @unittest.skipUnless(node_exe(), "ไม่มี node")
    def test_shell_scripts_parse(self):
        page = self.build("th")
        scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
        self.assertTrue(scripts)
        tmp = tempfile.mkdtemp(prefix="stackb2-shell-")
        try:
            for i, s in enumerate(scripts):
                f = os.path.join(tmp, "s%d.js" % i)
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(s)
                r = subprocess.run([node_exe(), "--check", f], capture_output=True, timeout=60)
                self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-1500:])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class EnhanceTests(unittest.TestCase):
    @unittest.skipUnless(node_exe(), "ไม่มี node")
    def test_enhance_parses(self):
        r = subprocess.run([node_exe(), "--check", ENHANCE], capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-1500:])

    def test_research_menu_is_wired_and_safe(self):
        src = enhance_src()
        self.assertIn("try { researchMenu(recs); } catch (e) {}", src)
        fn = src[src.index("function researchItem("):src.index("function researchMenu(")]
        self.assertIn('setAttribute("data-qw-no-tx", "")', fn)
        self.assertIn('span.textContent = STR[l].research', fn)
        self.assertIn('removeAttribute("id")', fn, "โคลนต้องไม่มี id ซ้ำกับรายการเดิม")
        # ใส่เฉพาะในเมนู "+" (มีรายการ System Message) และไม่ใส่ซ้ำ
        menu = src[src.index("function researchMenu("):src.index("function researchMenu(") + 1400]
        self.assertIn('scope.querySelector("[data-qw-research]")', menu)
        self.assertIn("plusMenuTemplate(scope)", menu)
        self.assertIn('closest(".chat-messages")', menu, "ต้องข้ามการเปลี่ยนแปลงในข้อความแชต (ระหว่างสตรีม)")

    def test_enhance_keeps_lf_and_no_bom(self):
        with open(ENHANCE, "rb") as fh:
            raw = fh.read()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r\n", raw)


if __name__ == "__main__":
    unittest.main()
