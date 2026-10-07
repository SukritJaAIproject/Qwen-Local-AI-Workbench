# -*- coding: utf-8 -*-
"""เทสต์ Skills (B4): C:\\LLM\\skills\\<name>\\SKILL.md -> MCP prompts/list, prompts/get, completion/complete

ตรวจ
  * ตัวอ่าน frontmatter (YAML ชุดย่อย) — รูปที่รองรับ และข้อผิดพลาดบอกเลขบรรทัด
  * การตรวจ skill ตอนโหลด (ชื่อ/อาร์กิวเมนต์/แม่แบบ/อักขระ bidi) — skill ที่ผิดถูกข้ามแต่ตัวอื่นยังใช้ได้
  * แม่แบบ: ส่วน {{#x}}/{{^x}} ซ้อนกันได้ แทนค่า "รอบเดียว" (ค่าที่ผู้ใช้พิมพ์ไม่ถูกขยายซ้ำ) ค่าเริ่มต้น
  * skill ตั้งต้น 7 ตัวในโฟลเดอร์จริง: โหลดได้ครบ มีชื่อไทย/อังกฤษ แสดงผลได้ทั้งผิว /fast และ /mcp
    และแต่ละผิวอ้างชื่อเครื่องมือของผิวตัวเองเท่านั้น
  * server.handle_rpc: initialize ประกาศ prompts/completions ทั้งสองผิว, error -32602 ตามสเปก, token ถูกลบ,
    audit เก็บแค่ความยาว, completion เห็นเฉพาะไฟล์ของโปรเจกต์ใน URL (S04)
  * guard: C:\\LLM\\skills อยู่ในเขตห้ามเขียน (ทั้ง path และข้อความของคำสั่ง/โค้ด python)
    รวมรูปแฝง (\\\\127.0.0.1\\c$, %SystemDrive%, cd แล้วสัมพัทธ์, Path('C:/LLM') / 'skills', 8.3) และงานปกติไม่โดนปฏิเสธ
  * อาร์กิวเมนต์ชื่อไฟล์ (complete: attachments): "attachments/x", path เต็ม, เครื่องหมายคำพูด -> "x" (ไม่ซ้ำคำนำหน้า)
    path นอกโฟลเดอร์ -> error ที่บอกวิธีแก้, ตัวพิมพ์เล็ก/ใหญ่ -> ชื่อจริง

ไม่แตะของจริง: audit.log/ข้อมูลโปรเจกต์/token ชี้ไปโฟลเดอร์ชั่วคราวผ่าน test_security_common
อ่านโฟลเดอร์ skills จริงอย่างเดียว (ไม่เขียน) — skill ทดสอบอยู่ในโฟลเดอร์ชั่วคราว
"""
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

guard = C.import_local("guard")
ps = C.import_local("prompts_skills")
server = C.import_local("server")
server.load_modules()

REAL_SKILLS = Path(r"C:\LLM\skills")
STARTERS = ["ocpp-log-analysis", "charger-incident-report", "python-data-analysis", "long-doc-summary",
            "deep-research", "code-review", "formal-email"]


def skill_md(name, title_th="ทดสอบ", title_en="Test", description="คำอธิบาย", args="", body="เนื้อ {{_project}}",
             extra=""):
    return ("---\nname: %s\ntitle_th: %s\ntitle_en: %s\ndescription: %s\n%s%s---\n%s\n"
            % (name, title_th, title_en, description, extra, args, body))


class TempSkills:
    """โฟลเดอร์ skills จำลอง + ชี้ prompts_skills ไปที่นั่นชั่วคราว"""

    def __init__(self, files: dict, settings: dict | None = None):
        self.dir = Path(C.new_dir("skills"))
        for rel, text in files.items():
            p = self.dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(text, bytes):
                p.write_bytes(text)
            else:
                p.write_text(text, encoding="utf-8", newline="\n")
        self.settings = Path(C.new_dir("hubset")) / "settings.json"
        self.settings.write_text(json.dumps(settings or {"lang": "th"}), encoding="utf-8")
        self._patches = [mock.patch.object(ps, "SKILLS_DIR", self.dir),
                         mock.patch.object(ps, "HUB_SETTINGS", self.settings)]

    def __enter__(self):
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        # mtime ของ NTFS ละเอียดพอ แต่ขนาดไฟล์อาจเท่าเดิม — เลื่อน mtime ให้ต่างแน่ๆ
        t = time.time() + 5
        os.utime(p, (t, t))


# ------------------------------------------------------------------ frontmatter
class FrontmatterParserTests(unittest.TestCase):
    def parse(self, head, body="x"):
        return ps.parse_frontmatter("---\n%s\n---\n%s" % (head, body))

    def test_scalars_quotes_bools(self):
        meta, body = self.parse('a: plain text ไทย\nb: "q \\"x\\" ok"\nc: \'it\'\'s\'\nd: true\ne: FALSE\nf: null')
        self.assertEqual(meta, {"a": "plain text ไทย", "b": 'q "x" ok', "c": "it's", "d": True, "e": False,
                                "f": None})
        self.assertEqual(body, "x")

    def test_hash_inside_value_is_not_a_comment(self):
        meta, _ = self.parse("title_th: ตู้ #3 ขัดข้อง\n# คอมเมนต์ทั้งบรรทัด\nx: y")
        self.assertEqual(meta, {"title_th": "ตู้ #3 ขัดข้อง", "x": "y"})

    def test_block_scalars(self):
        meta, _ = self.parse("keep: |\n  line 1\n    indented\n\n  line 3\nfold: >\n  a\n  b\n\n  c\nnext: n")
        self.assertEqual(meta["keep"], "line 1\n  indented\n\nline 3")
        self.assertEqual(meta["fold"], "a b\nc")
        self.assertEqual(meta["next"], "n")

    def test_argument_list_indented_and_compact_forms_agree(self):
        a, _ = self.parse("arguments:\n  - name: file\n    required: true\n  - name: focus\n    description: d\nz: 1")
        b, _ = self.parse("arguments:\n- name: file\n  required: true\n- name: focus\n  description: d\nz: 1")
        self.assertEqual(a, b)
        self.assertEqual(a["arguments"], [{"name": "file", "required": True},
                                          {"name": "focus", "description": "d"}])
        self.assertEqual(a["z"], "1")

    def test_block_scalar_inside_list_item(self):
        meta, _ = self.parse("arguments:\n  - name: x\n    description: >\n      ยาว\n      มาก\n  - name: y")
        self.assertEqual(meta["arguments"], [{"name": "x", "description": "ยาว มาก"}, {"name": "y"}])

    def test_flow_json_and_scalar_lists(self):
        meta, _ = self.parse('arguments: [{"name": "q", "required": true}]\ntags:\n  - a\n  - "b c"')
        self.assertEqual(meta["arguments"], [{"name": "q", "required": True}])
        self.assertEqual(meta["tags"], ["a", "b c"])

    def test_errors_name_the_line(self):
        cases = {
            "a: 1\n b: 2": "บรรทัด 3",
            "a: 1\na: 2": "ซ้ำ",
            'a: "open': "บรรทัด 2",
            "a: 'open": "บรรทัด 2",
            "a:\n  b: 1": "mapping ซ้อน",
            "just text": "key: value",
            "list:\n  - a\n  - k: v": "ผสม",
            "\ta: 1": "แท็บ",
            "a: [1,": "JSON",
        }
        for head, needle in cases.items():
            with self.assertRaises(ps.SkillError, msg=head) as cm:
                self.parse(head)
            self.assertIn(needle, str(cm.exception), head)

    def test_frontmatter_fences_required(self):
        with self.assertRaises(ps.SkillError):
            ps.parse_frontmatter("name: x\n---\nbody")
        with self.assertRaises(ps.SkillError):
            ps.parse_frontmatter("---\nname: x\nbody without closing fence")


# ------------------------------------------------------------------ build_skill
class BuildSkillTests(unittest.TestCase):
    def build(self, **kw):
        folder = kw.pop("folder", "demo")
        return ps.build_skill(folder, skill_md(kw.pop("name", "demo"), **kw))

    def test_valid_skill(self):
        s = self.build(args="arguments:\n  - name: file\n    required: true\n    complete: attachments\n"
                            "  - name: focus\n    default: ทั้งหมด\n",
                       body="{{file}} {{#focus}}[{{focus}}]{{/focus}} {{#_fast}}fast{{/_fast}}")
        self.assertEqual(s.name, "demo")
        self.assertEqual([a.name for a in s.arguments], ["file", "focus"])
        self.assertTrue(s.arguments[0].required)
        self.assertEqual(s.arguments[0].complete, "attachments")
        self.assertEqual(s.arguments[1].default, "ทั้งหมด")

    def test_crlf_and_bom_accepted(self):
        text = "\ufeff" + skill_md("demo").replace("\n", "\r\n")
        self.assertEqual(ps.build_skill("demo", text).name, "demo")

    def test_invalid_skills_rejected(self):
        bad = {
            "name mismatch": dict(name="other"),
            "bad name": dict(name="Bad_Name", folder="Bad_Name"),
            "no description": dict(description='""'),
            "no titles": dict(title_th='""', title_en='""'),
            "thai arg name": dict(args="arguments:\n  - name: ไฟล์\n"),
            "digit arg": dict(args="arguments:\n  - name: 1x\n"),
            "underscore arg": dict(args="arguments:\n  - name: _x\n", body="{{_x}}"),
            "dash arg": dict(args="arguments:\n  - name: a-b\n"),
            "dup arg": dict(args="arguments:\n  - name: a\n  - name: a\n"),
            "required yes": dict(args="arguments:\n  - name: a\n    required: yes\n"),
            "bad complete": dict(args="arguments:\n  - name: a\n    complete: C:\\\n"),
            "args not list": dict(args="arguments: x\n"),
            "unknown var": dict(body="{{nope}}"),
            "unknown section": dict(body="{{#nope}}x{{/nope}}"),
            "unclosed section": dict(args="arguments:\n  - name: a\n", body="{{#a}}x"),
            "stray close": dict(args="arguments:\n  - name: a\n", body="x{{/a}}"),
            "same-name nesting": dict(args="arguments:\n  - name: a\n", body="{{#a}}{{#a}}x{{/a}}{{/a}}"),
            "garbage mustache": dict(body="{{ not a var }}"),
            "empty body": dict(body="   "),
            "bad order": dict(extra="order: soon\n"),
            "too many args": dict(args="arguments:\n" + "".join("  - name: a%d\n" % i for i in range(11))),
        }
        for label, kw in bad.items():
            with self.assertRaises(ps.SkillError, msg=label):
                self.build(**kw)

    def test_bidi_and_nul_rejected_but_thai_joiners_allowed(self):
        with self.assertRaises(ps.SkillError):
            ps.build_skill("demo", skill_md("demo", body="ok \u202e evil"))
        with self.assertRaises(ps.SkillError):
            ps.build_skill("demo", skill_md("demo", body="ok \x00"))
        # U+200B/U+2060 เป็นของปกติในข้อความไทย (ตัดคำ/ยึดคำ) ห้ามปฏิเสธ
        self.assertTrue(ps.build_skill("demo", skill_md("demo", body="ตู้\u200bชาร์จ\u2060")))


# ------------------------------------------------------------------ render
class RenderTests(unittest.TestCase):
    def test_sections_nested_and_inverted(self):
        body = "A{{#x}}[x={{x}}{{#y}} y={{y}}{{/y}}]{{/x}}{{^x}}(no x){{/x}}B"
        self.assertEqual(ps.render(body, {"x": "1", "y": "2"}), "A[x=1 y=2]B")
        self.assertEqual(ps.render(body, {"x": "1", "y": ""}), "A[x=1]B")
        self.assertEqual(ps.render(body, {"x": "", "y": "2"}), "A(no x)B")

    def test_standalone_tags_leave_no_blank_lines(self):
        body = "head\n{{#x}}\nline x\n{{/x}}\n{{^x}}\nline no x\n{{/x}}\ntail"
        self.assertEqual(ps.render(body, {"x": "1"}), "head\nline x\ntail")
        self.assertEqual(ps.render(body, {"x": ""}), "head\nline no x\ntail")

    def test_user_values_are_substituted_once(self):
        body = "{{a}}|{{b}}"
        out = ps.render(body, {"a": "{{b}} {{#b}}X{{/b}} {{_project}}", "b": "B"})
        self.assertEqual(out, "{{b}} {{#b}}X{{/b}} {{_project}}|B")

    def test_blank_line_runs_collapsed(self):
        self.assertEqual(ps.render("a\n\n\n\n{{x}}\n\n\n\nb", {"x": ""}), "a\n\nb")


# ------------------------------------------------------------------ loader
class LoaderTests(unittest.TestCase):
    def test_bad_skill_is_skipped_others_load(self):
        files = {"good/SKILL.md": skill_md("good"),
                 "bad/SKILL.md": skill_md("bad", body="{{oops}}"),
                 "Upper/SKILL.md": skill_md("upper"),
                 "empty/readme.txt": "no skill here",
                 "_template/SKILL.md": skill_md("_template"),
                 ".git/SKILL.md": "x",
                 "README.md": "top-level files are ignored",
                 "huge/SKILL.md": skill_md("huge", body="x" * (ps.MAX_SKILL_BYTES + 10)),
                 "latin1/SKILL.md": skill_md("latin1").encode("utf-8") + b"\xff\xfe"}
        with TempSkills(files):
            skills, errors = ps.load_skills()
            self.assertEqual(sorted(skills), ["good"])
            self.assertEqual(sorted(errors), ["Upper", "bad", "empty", "huge", "latin1"])
            self.assertIn("oops", errors["bad"])
            st = ps.status()
            self.assertEqual(st["count"], 1)
            self.assertIn("bad", st["failed"])

    def test_hot_reload_on_change(self):
        with TempSkills({"one/SKILL.md": skill_md("one", body="v1")}) as t:
            self.assertEqual(ps.get_prompt("p", True, "one", {})["messages"][0]["content"]["text"], "v1")
            t.write("one/SKILL.md", skill_md("one", body="v2 changed"))
            t.write("two/SKILL.md", skill_md("two"))
            self.assertEqual(ps.get_prompt("p", True, "one", {})["messages"][0]["content"]["text"], "v2 changed")
            self.assertEqual([p["name"] for p in ps.list_prompts("p", True)], ["one", "two"])

    def test_order_then_name(self):
        files = {"b/SKILL.md": skill_md("b", extra="order: 5\n"), "a/SKILL.md": skill_md("a"),
                 "c/SKILL.md": skill_md("c", extra="order: 5\n")}
        with TempSkills(files):
            self.assertEqual([p["name"] for p in ps.list_prompts("p", True)], ["b", "c", "a"])

    def test_junction_pointing_outside_is_skipped(self):
        try:
            import _winapi
        except ImportError:
            self.skipTest("ไม่มี _winapi")
        outside = Path(C.new_dir("outside-skill"))
        (outside / "SKILL.md").write_text(skill_md("linked"), encoding="utf-8")
        with TempSkills({"ok/SKILL.md": skill_md("ok")}) as t:
            try:
                _winapi.CreateJunction(str(outside), str(t.dir / "linked"))
            except OSError as exc:
                self.skipTest("สร้าง junction ไม่ได้: %s" % exc)
            skills, errors = ps.load_skills(force=True)
            self.assertEqual(sorted(skills), ["ok"])
            self.assertIn("linked", errors)
            os.rmdir(t.dir / "linked")        # ถอดเฉพาะ junction ที่เทสต์สร้าง (ไม่แตะไฟล์ปลายทาง)

    def test_per_project_enable_list(self):
        files = {n + "/SKILL.md": skill_md(n) for n in ("a", "b", "c")}
        files["enabled.json"] = json.dumps({"default": {"disabled": ["c"]},
                                            "projects": {"Proj One": {"enabled": ["a"]},
                                                         "two": {"disabled": ["a", "b"]}}})
        with TempSkills(files):
            names = lambda p: [x["name"] for x in ps.list_prompts(p, True)]  # noqa: E731
            self.assertEqual(names("proj-one"), ["a"])
            self.assertEqual(names("two"), ["c"])
            self.assertEqual(names("other"), ["a", "b"])
            with self.assertRaises(ps.PromptError):
                ps.get_prompt("proj-one", True, "b", {})
            self.assertEqual(ps.complete("proj-one", True, {"type": "ref/prompt", "name": "b"},
                                         {"name": "x", "value": ""})["completion"]["values"], [])

    def test_broken_enable_list_means_all_enabled(self):
        files = {"a/SKILL.md": skill_md("a"), "enabled.json": "{broken"}
        with TempSkills(files):
            self.assertEqual([x["name"] for x in ps.list_prompts("p", True)], ["a"])
            self.assertIn("enabled_error", ps.status())

    def test_language_follows_hub_setting(self):
        md = skill_md("a", title_th="ไทย", title_en="English", description="คำอธิบาย",
                      extra="description_en: Desc EN\n",
                      args="arguments:\n  - name: q\n    description: คำถาม\n    description_en: Question\n"
                           "    default: standard\n",
                      body="{{_lang}} {{#_th}}th{{/_th}}{{#_en}}en{{/_en}} {{q}}")
        with TempSkills({"a/SKILL.md": md}, settings={"lang": "en"}):
            item = ps.list_prompts("p", True)[0]
            self.assertEqual((item["title"], item["description"]), ("English", "Desc EN"))
            self.assertEqual(item["arguments"][0]["description"], "Question (default: standard)")
            self.assertEqual(ps.get_prompt("p", True, "a", {})["messages"][0]["content"]["text"], "en en standard")
            with self.assertRaises(ps.PromptError) as cm:
                ps.get_prompt("p", True, "zzz", {})
            self.assertIn("unknown prompt", str(cm.exception))
        with TempSkills({"a/SKILL.md": md}, settings={"lang": "th"}):
            item = ps.list_prompts("p", True)[0]
            self.assertEqual((item["title"], item["description"]), ("ไทย", "คำอธิบาย"))
            self.assertEqual(item["arguments"][0]["description"], "คำถาม (ค่าเริ่มต้น: standard)")
        with TempSkills({"a/SKILL.md": md}) as t:
            t.settings.unlink()
            self.assertEqual(ps.ui_lang(), "th")

    def test_default_en_used_when_ui_is_english(self):
        md = skill_md("a", args="arguments:\n  - name: n\n    default: ประมาณ 1 หน้า\n    default_en: about 1 page\n",
                      body="len={{n}}")
        for lang, want in (("en", "about 1 page"), ("th", "ประมาณ 1 หน้า")):
            with TempSkills({"a/SKILL.md": md}, settings={"lang": lang}):
                self.assertIn(want, ps.list_prompts("p", True)[0]["arguments"][0]["description"])
                self.assertEqual(ps.get_prompt("p", True, "a", {})["messages"][0]["content"]["text"], "len=" + want)
                self.assertEqual(ps.get_prompt("p", True, "a", {"n": "2 หน้า"})["messages"][0]["content"]["text"],
                                 "len=2 หน้า")

    def test_argument_validation(self):
        md = skill_md("a", args="arguments:\n  - name: q\n    required: true\n  - name: o\n", body="{{q}}|{{o}}")
        with TempSkills({"a/SKILL.md": md}):
            ok = ps.get_prompt("p", True, "a", {"q": "  hi  ", "unknown": "ignored", "o": None})
            self.assertEqual(ok["messages"][0]["content"]["text"], "hi|")
            for args in ({}, {"q": ""}, {"q": "   "}, {"q": 5}, {"q": ["x"]}, "notadict", {"q": "x" * 20_001}):
                with self.assertRaises(ps.PromptError, msg=repr(args)[:40]):
                    ps.get_prompt("p", True, "a", args)
            with self.assertRaises(ps.PromptError):
                ps.get_prompt("p", True, None, {})
            with self.assertRaises(ps.PromptError):
                ps.get_prompt("p", True, "..\\..\\secrets", {})


# ------------------------------------------------------------------ อาร์กิวเมนต์ชื่อไฟล์ (complete: attachments)
PROJ_F = "skills-f-" + os.urandom(3).hex()
PROJ_G = "skills-g-" + os.urandom(3).hex()


class FileArgumentTests(unittest.TestCase):
    """ค่าที่ผู้ใช้วาง/พิมพ์ในช่องชื่อไฟล์ต้องกลายเป็น path ใต้ attachments ก่อนแทนค่า
    (finding ของ integrator: "attachments/x.pdf" -> path="attachments/attachments/x.pdf" หาไม่เจอ และ 4B ยอมแพ้)"""

    @classmethod
    def setUpClass(cls):
        md = skill_md("f", args="arguments:\n  - name: file\n    required: true\n    complete: attachments\n"
                                "  - name: opt\n    complete: attachments\n",
                      body="F={{#_fast}}attachments/{{file}}{{/_fast}}{{^_fast}}{{_attachments}}\\{{file}}{{/_fast}}"
                           "{{#opt}} O={{opt}}{{/opt}}")
        cls.t = TempSkills({"f/SKILL.md": md})
        cls.t.__enter__()
        cls.data = Path(guard.PROJECT_DATA) / PROJ_F
        cls.att = cls.data / "attachments"
        (cls.att / "sub").mkdir(parents=True, exist_ok=True)
        (cls.data / "outputs").mkdir(exist_ok=True)
        for rel in ("scan-เหตุขัดข้อง-C03.pdf", "Report.PDF", "sub/y.log", "~$lock.docx"):
            (cls.att / rel).write_text("x", encoding="utf-8")
        (cls.data / "outputs" / "r.md").write_text("x", encoding="utf-8")
        # โปรเจกต์ที่มีโฟลเดอร์ชื่อ attachments อยู่ใน attachments จริง — ต้องไม่ถูกตัด
        g = Path(guard.PROJECT_DATA) / PROJ_G / "attachments" / "attachments"
        g.mkdir(parents=True, exist_ok=True)
        (g / "z.txt").write_text("x", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.t.__exit__()

    def render(self, file, fast=True, project=PROJ_F, **extra):
        return ps.get_prompt(project, fast, "f", dict(file=file, **extra))["messages"][0]["content"]["text"]

    def test_prefix_quotes_and_full_path_forms_become_the_bare_name(self):
        name = "scan-เหตุขัดข้อง-C03.pdf"
        full = self.att / name
        forms = [name, "attachments/" + name, "attachments\\" + name, "./attachments/" + name, "/attachments/" + name,
                 "Attachments/" + name, '"%s"' % name, "`attachments/%s`" % name, "\u201c%s\u201d" % name,
                 str(full), str(full).replace("\\", "/"), str(full).upper(), "attachments//" + name]
        for v in forms:
            self.assertEqual(self.render(v), "F=attachments/" + name, v)
            self.assertEqual(self.render(v, fast=False), "F=" + str(full), v)

    def test_subfolders_kept_with_the_surface_separator(self):
        self.assertEqual(self.render("attachments/sub/y.log"), "F=attachments/sub/y.log")
        self.assertEqual(self.render("sub\\y.log"), "F=attachments/sub/y.log")
        self.assertEqual(self.render("sub/y.log", fast=False), "F=" + str(self.att / "sub" / "y.log"))
        # attachments\attachments\z.txt มีอยู่จริง = ผู้ใช้หมายถึงโฟลเดอร์ย่อยนั้น ไม่ใช่คำนำหน้าซ้ำ
        self.assertEqual(self.render("attachments/z.txt", project=PROJ_G), "F=attachments/attachments/z.txt")

    def test_case_is_fixed_to_the_real_name_but_never_guessed(self):
        self.assertEqual(self.render("report.pdf"), "F=attachments/Report.PDF")
        self.assertEqual(self.render("REPORT.pdf", fast=False), "F=" + str(self.att / "Report.PDF"))
        # ชื่อที่ไม่มีจริง (เช่น พิมพ์ตกคำ "ขัด") คงตามที่พิมพ์ — ไม่เดาไฟล์ที่ "คล้าย" ให้เงียบๆ
        self.assertEqual(self.render("scan-เหตุข้อง-C03.pdf"), "F=attachments/scan-เหตุข้อง-C03.pdf")
        self.assertEqual(self.render("~$lock.docx"), "F=attachments/~$lock.docx")    # ~ ขึ้นต้นชื่อไฟล์ได้

    def test_paths_outside_the_folder_are_refused_with_a_hint(self):
        other_proj = Path(guard.PROJECT_DATA) / "someone-else" / "attachments" / "x.pdf"
        for v in (r"C:\Users\me\x.pdf", "D:/x.pdf", r"\\server\share\x.pdf", "//127.0.0.1/c$/LLM/skills/a",
                  "~/x.pdf", "~", "../secrets/x", "attachments/../../x", "sub/../../x", str(other_proj),
                  str(self.data), str(self.data / "notes.txt")):
            with self.assertRaises(ps.PromptError, msg=v) as cm:
                self.render(v)
            self.assertIn("attachments", str(cm.exception), v)
            self.assertNotIn("someone-else", str(cm.exception), v)   # ไม่สะท้อน path ของโปรเจกต์อื่นกลับ

    def test_file_in_the_other_project_folder_is_named(self):
        for v in ("outputs/r.md", str(self.data / "outputs" / "r.md"), "outputs\\missing.md"):
            with self.assertRaises(ps.PromptError, msg=v) as cm:
                self.render(v)
            self.assertIn("outputs", str(cm.exception), v)
            self.assertIn(Path(v.replace("\\", "/")).name, str(cm.exception), v)

    def test_folder_only_counts_as_empty(self):
        for v in ("attachments", "attachments/", str(self.att), "./", '""', "``"):
            with self.assertRaises(ps.PromptError, msg=v) as cm:
                self.render(v)
            self.assertIn("file", str(cm.exception), v)                   # ต้องกรอก: file
        self.assertEqual(self.render("x.pdf", opt="attachments/"), "F=attachments/x.pdf")
        self.assertEqual(self.render("x.pdf", opt="attachments/sub/y.log"), "F=attachments/x.pdf O=sub/y.log")

    def test_english_ui_gets_an_english_hint(self):
        with mock.patch.object(ps, "HUB_SETTINGS", self.t.settings.with_name("en.json")):
            self.t.settings.with_name("en.json").write_text('{"lang": "en"}', encoding="utf-8")
            with self.assertRaises(ps.PromptError) as cm:
                self.render("D:/x.pdf")
            self.assertIn("this project's attachments", str(cm.exception))


# ------------------------------------------------------------------ skill ตั้งต้น
class StarterSkillsTests(unittest.TestCase):
    """โฟลเดอร์จริง C:\\LLM\\skills (อ่านอย่างเดียว)"""

    @classmethod
    def setUpClass(cls):
        cls.p = mock.patch.object(ps, "SKILLS_DIR", REAL_SKILLS)
        cls.p.start()
        cls.skills, cls.errors = ps.load_skills(force=True)

    @classmethod
    def tearDownClass(cls):
        cls.p.stop()

    def test_all_starters_load_without_errors(self):
        self.assertEqual(self.errors, {})
        for name in STARTERS:
            self.assertIn(name, self.skills)

    def test_titles_and_descriptions_bilingual(self):
        thai = lambda s: any("\u0e00" <= ch <= "\u0e7f" for ch in s)  # noqa: E731
        for name in STARTERS:
            s = self.skills[name]
            self.assertTrue(thai(s.title_th), name)
            self.assertTrue(s.title_en and s.title_en.isascii(), name)
            self.assertTrue(thai(s.description), name)
            self.assertTrue(s.description_en and s.description_en.isascii(), name)
            for a in s.arguments:
                self.assertRegex(a.name, r"^[A-Za-z][A-Za-z0-9_]*$")
                self.assertTrue(thai(a.description) and a.description_en, (name, a.name))

    def test_contract_titles(self):
        titles = {s.title_th for s in self.skills.values()}
        for t in ("วิเคราะห์ log OCPP", "รายงานเหตุขัดข้องตู้ชาร์จ", "วิเคราะห์ข้อมูลด้วย Python", "รีวิวโค้ด",
                  "สรุปเอกสารยาว", "เขียนอีเมลทางการ", "ค้นคว้าเชิงลึก"):
            self.assertIn(t, titles)

    def test_ocpp_first_in_list(self):
        with mock.patch.object(ps, "HUB_SETTINGS", Path(C.TMP) / "no-settings.json"):
            self.assertEqual(ps.list_prompts("p", True)[0]["name"], "ocpp-log-analysis")

    def render_all(self, name, fast, full_args=True, **over):
        s = self.skills[name]
        sample = {"file": "log 1.txt", "charger": "CP-01", "focus": "หลุด", "station": "บางนา",
                  "incident": "ไม่เริ่มชาร์จ", "when": "1 ต.ค. 10:00", "save": "docx", "question": "อะไร?",
                  "to": "ผู้จัดการ", "purpose": "ขอเข้าตรวจ", "details": "วันที่ 5", "language": "en",
                  "length": "10 บรรทัด", "depth": "quick"}
        sample.update(over)
        args = {a.name: sample[a.name] for a in s.arguments if full_args or a.required}
        return ps.get_prompt("proj", fast, name, args)["messages"][0]["content"]["text"]

    def file_skills(self):
        return [n for n in STARTERS if any(a.name == "file" for a in self.skills[n].arguments)]

    def test_file_argument_never_doubles_the_folder(self):
        # ผู้ใช้วาง "attachments/..." หรือ path เต็ม -> แม่แบบที่เติม attachments/ เองต้องไม่ได้ attachments/attachments/
        base = Path(guard.PROJECT_DATA) / "proj" / "attachments"
        self.assertEqual(len(self.file_skills()), 5)
        for name in self.file_skills():
            for fast in (True, False):
                for v in ("attachments/log 1.txt", "attachments\\log 1.txt", str(base / "log 1.txt")):
                    text = self.render_all(name, fast, file=v)
                    self.assertNotIn("attachments/attachments", text, (name, fast, v))
                    self.assertNotIn("attachments\\attachments", text, (name, fast, v))
                    self.assertNotIn("attachments/C:", text, (name, fast, v))
                    want = 'path="attachments/log 1.txt"' if fast else str(base / "log 1.txt")
                    self.assertIn(want, text, (name, fast, v))

    def test_file_skills_tell_the_model_to_list_when_not_found(self):
        # integrator E2E: 4B คัดลอกชื่อไทยตกคำ ("เหตุข้อง") ได้ "ไม่พบไฟล์" แล้วยอมแพ้ถามผู้ใช้ — ให้ดูรายชื่อแล้วลองใหม่ก่อน
        for name in self.file_skills():
            self.assertIn('local_read action="list" path="attachments"', self.render_all(name, True), name)
            self.assertIn('list_dir path="%s"' % (Path(guard.PROJECT_DATA) / "proj" / "attachments"),
                          self.render_all(name, False), name)
            if not next(a for a in self.skills[name].arguments if a.name == "file").required:
                # ไม่ได้ระบุไฟล์ (วาง log/โค้ดในข้อความ) = ไม่มีบรรทัดนี้ให้โมเดลหลงไปเปิดโฟลเดอร์
                self.assertNotIn('action="list"', self.render_all(name, True, file=""), name)

    def test_every_starter_renders_on_both_surfaces(self):
        fast_only = ("local_read", "local_do")
        full_only = ("read_file", "doc_extract", "python_exec", "kb_search", "grep_search")
        for name in STARTERS:
            for full_args in (True, False):
                f = self.render_all(name, True, full_args)
                m = self.render_all(name, False, full_args)
                for text in (f, m):
                    self.assertNotIn("{{", text, name)
                    self.assertNotIn("\n\n\n", text, name)
                for word in full_only:
                    self.assertNotIn(word, f, (name, word))
                for word in fast_only:
                    self.assertNotIn(word, m, (name, word))

    def test_file_reading_skills_mark_content_as_data(self):
        for name in STARTERS:
            if any(a.name == "file" for a in self.skills[name].arguments) or name == "deep-research":
                self.assertIn("ไม่ใช่คำสั่ง", self.render_all(name, True), name)

    def test_deep_research_calls_contract_actions(self):
        text = self.render_all("deep-research", True, full_args=False)
        self.assertIn('local_do action="research" question="อะไร?" depth="standard"', text)
        self.assertIn('local_read action="research_status"', text)
        self.assertIn('depth="quick"', self.render_all("deep-research", True))
        # ผิวเต็มต้องเรียกชื่อเครื่องมือจริงของ tools_research (ไม่ใช่ "research ถ้ามี" แบบกว้างๆ ที่ 4B เดาชื่อผิด)
        full = self.render_all("deep-research", False, full_args=False)
        self.assertIn('research_start question="อะไร?" depth="standard"', full)
        self.assertIn("research_status", full)

    def test_referenced_tools_exist_on_their_surface(self):
        # กันแม่แบบเก่าเมื่อเจ้าของเครื่องมืออื่นเปลี่ยนชื่อ action/เครื่องมือ: โมเดลเล็กทำตามแม่แบบตามตัวอักษร
        # ชื่อที่ไม่มีจริงจะได้ "ไม่รู้จักเครื่องมือ" แล้ววนถามผู้ใช้ — ตรวจกับทะเบียนจริงของ server.py/tools_fast
        import re
        tf = C.import_local("tools_fast")
        web = {"web_search", "fetch_url"}                 # อยู่ใน MCP ค้นเว็บ (8791) ไม่ใช่ server นี้
        fast_names = {"local_read", "local_do", "max_chars"} | web | set(tf._READ_INDEX) | set(tf._DO_INDEX)
        full_names = set(server.IMPL) | web
        for name in STARTERS:
            for full_args in (True, False):
                f = self.render_all(name, True, full_args)
                for tool, act in re.findall(r'\b(local_read|local_do)\s+action="([a-z_]+)"', f):
                    index = tf._READ_INDEX if tool == "local_read" else tf._DO_INDEX
                    self.assertIn(act, index, (name, tool, act))
                for act in re.findall(r'\baction="([a-z_]+)"', f):
                    self.assertIn(act, set(tf._READ_INDEX) | set(tf._DO_INDEX), (name, act))
                for ident in re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", f):
                    self.assertIn(ident, fast_names, (name, "fast", ident))
                m = self.render_all(name, False, full_args)
                self.assertNotIn("action=", m, name)
                for ident in re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", m):
                    self.assertIn(ident, full_names, (name, "full", ident))

    def test_doc_summary_uses_kb_when_focus_given(self):
        text = self.render_all("long-doc-summary", True)
        self.assertIn('local_read action="kb" query="หลุด"', text)
        self.assertIn('path="attachments/log 1.txt"', text)
        self.assertNotIn('action="kb"', self.render_all("long-doc-summary", True, full_args=False))

    def test_python_skill_uses_absolute_attachment_path(self):
        text = self.render_all("python-data-analysis", True)
        expect = str(Path(guard.PROJECT_DATA) / "proj" / "attachments" / "log 1.txt")
        self.assertIn('r"%s"' % expect, text)


# ------------------------------------------------------------------ server.handle_rpc
# slug เฉพาะของไฟล์นี้: โฟลเดอร์ข้อมูลชั่วคราวใช้ร่วมกับเทสต์ชุดอื่นในโปรเซสเดียวกัน (เช่น kb ใส่ไฟล์ลง sec-http)
PROJ_A = "skills-a-" + os.urandom(3).hex()
PROJ_B = "skills-b-" + os.urandom(3).hex()


def rpc(method, params=None, project=PROJ_A, fast=True, mid=1):
    msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if mid is not None:
        msg["id"] = mid
    return server.handle_rpc(msg, project, fast)


class ServerRpcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        md = skill_md("echo", args="arguments:\n  - name: text\n    required: true\n    complete: attachments\n"
                                   "  - name: plain\n", body="ECHO {{text}}")
        cls.t = TempSkills({"echo/SKILL.md": md})
        cls.t.__enter__()
        data = Path(guard.PROJECT_DATA)
        for slug, names in ((PROJ_A, ["OCPP-a.log", "notes.txt", "k.key", ".hidden"]),
                            (PROJ_B, ["OCPP-b-secret.log"])):
            d = data / slug / "attachments"
            d.mkdir(parents=True, exist_ok=True)
            for n in names:
                (d / n).write_text("x", encoding="utf-8")
        (data / PROJ_A / "attachments" / "OCPP-dir").mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.t.__exit__()

    def test_initialize_advertises_prompts_on_both_surfaces(self):
        for fast in (True, False):
            caps = rpc("initialize", fast=fast)["result"]["capabilities"]
            self.assertIn("tools", caps)
            self.assertEqual(caps["prompts"], {"listChanged": False})
            self.assertIn("completions", caps)

    def test_list_and_get(self):
        for fast in (True, False):
            items = rpc("prompts/list", fast=fast)["result"]["prompts"]
            self.assertEqual([p["name"] for p in items], ["echo"])
            self.assertEqual(items[0]["arguments"][0], {"name": "text", "description": "", "required": True})
        res = rpc("prompts/get", {"name": "echo", "arguments": {"text": "สวัสดี"}})["result"]
        self.assertEqual(res["messages"], [{"role": "user", "content": {"type": "text", "text": "ECHO สวัสดี"}}])

    def test_errors_are_invalid_params(self):
        for params in ({"name": "nope"}, {"name": "echo"}, {"name": "echo", "arguments": {"text": 1}},
                       {"name": "echo", "arguments": []}, {}):
            err = rpc("prompts/get", params)["error"]
            self.assertEqual(err["code"], -32602, params)
        self.assertEqual(rpc("prompts/get", ["not", "a", "dict"])["error"]["code"], -32602)

    def test_notification_gets_no_reply(self):
        self.assertIsNone(rpc("prompts/list", mid=None))

    def test_local_token_scrubbed_from_output(self):
        text = rpc("prompts/get", {"name": "echo", "arguments": {"text": "t=" + C.TOKEN}})[
            "result"]["messages"][0]["content"]["text"]
        self.assertNotIn(C.TOKEN, text)
        self.assertIn("***", text)

    def test_prompt_error_text_is_scrubbed(self):
        # ข้อความ error ยกชื่อไฟล์ที่ผู้ใช้พิมพ์กลับมา (เช่น "... อยู่ใน outputs") — ต้องผ่าน scrub เหมือนผลปกติ
        err = rpc("prompts/get", {"name": "echo", "arguments": {"text": "outputs/" + C.TOKEN}})["error"]
        self.assertEqual(err["code"], -32602)
        self.assertIn("outputs", err["message"])
        self.assertNotIn(C.TOKEN, err["message"])

    def test_audit_logs_lengths_not_values(self):
        secret_words = "ข้อความส่วนตัวของผู้ใช้-7c1e"
        rpc("prompts/get", {"name": "echo", "arguments": {"text": secret_words}})
        with open(C.AUDIT_LOCAL, encoding="utf-8") as fh:
            lines = [json.loads(x) for x in fh if '"prompt_get"' in x]
        self.assertTrue(lines)
        self.assertEqual(lines[-1]["args"], {"text": len(secret_words)})
        with open(C.AUDIT_LOCAL, encoding="utf-8") as fh:
            self.assertNotIn(secret_words, fh.read())

    def test_completion_lists_only_this_projects_files(self):
        def values(value, project=PROJ_A, arg="text", name="echo"):
            res = rpc("completion/complete", {"ref": {"type": "ref/prompt", "name": name},
                                               "argument": {"name": arg, "value": value}}, project=project)
            return res["result"]["completion"]["values"]
        self.assertEqual(values(""), ["notes.txt", "OCPP-a.log"])          # ไม่มีไฟล์ซ่อน/.key/โฟลเดอร์
        self.assertEqual(values("ocpp"), ["OCPP-a.log"])
        self.assertEqual(values("o"), ["OCPP-a.log", "notes.txt"])           # ขึ้นต้นก่อน แล้วค่อยตัวที่มีข้างใน
        self.assertNotIn("OCPP-b-secret.log", values("b"))                  # S04: ไฟล์ของ proj-b
        self.assertEqual(values("", project=PROJ_B), ["OCPP-b-secret.log"])
        self.assertEqual(values("", arg="plain"), [])                        # อาร์กิวเมนต์ที่ไม่ได้ขอเติมคำ
        self.assertEqual(values("", name="nope"), [])
        bad = rpc("completion/complete", {"ref": {"type": "ref/resource", "uri": "file:///C:/"},
                                          "argument": {"name": "text", "value": ""}})
        self.assertEqual(bad["result"]["completion"]["values"], [])

    def test_module_missing_degrades_gracefully(self):
        with mock.patch.object(server, "prompts_skills", None), mock.patch.object(server, "_SKILLS_ERR", "boom"):
            caps = rpc("initialize")["result"]["capabilities"]
            self.assertNotIn("prompts", caps)
            self.assertEqual(rpc("prompts/list")["error"]["code"], -32601)
            # เครื่องมือยังอยู่ครบ
            self.assertTrue(rpc("tools/list")["result"]["tools"])

    def test_internal_error_is_json_rpc_error(self):
        with mock.patch.object(ps, "list_prompts", side_effect=RuntimeError("x")):
            self.assertEqual(rpc("prompts/list")["error"]["code"], -32603)


# ------------------------------------------------------------------ guard
class GuardWriteProtectTests(unittest.TestCase):
    def test_skills_dir_is_write_protected(self):
        for p in (r"C:\LLM\skills", r"C:\LLM\skills\ocpp-log-analysis\SKILL.md", r"c:\llm\SKILLS\new\SKILL.md",
                  "C:/LLM/skills/evil/SKILL.md", r"C:\LLM\skills\enabled.json", r"\\?\C:\LLM\skills\x\SKILL.md"):
            self.assertTrue(guard.is_write_protected(p), p)
        self.assertFalse(guard.is_write_protected(r"C:\Users\demo\skills\SKILL.md"))

    def test_check_write_refuses_even_new_files(self):
        with guard.project_scope("sec-http"):
            with self.assertRaises(guard.Denied):
                guard.check_write(r"C:\LLM\skills\evil\SKILL.md")

    def test_commands_and_python_touching_skills_are_refused(self):
        for cmd in (r"echo x > C:\LLM\skills\a\SKILL.md", "copy evil.md c:/llm/skills/a/SKILL.md",
                    "open(r'C:\\LLM\\skills\\a\\SKILL.md','w').write('x')"):
            self.assertEqual(guard.command_text_violation(cmd, False), "protected_path", cmd)
        self.assertIsNone(guard.command_text_violation(r"type C:\LLM\skills\a\SKILL.md", True))

    def test_reading_skills_is_allowed(self):
        with guard.project_scope("sec-http"):
            guard.check_read(str(REAL_SKILLS / "ocpp-log-analysis" / "SKILL.md"))

    # finding ของตัวตรวจ batch 2a: ด่านข้อความเทียบแค่ "c:\llm\<ชื่อ>" ตรงตัว รูปแฝงเหล่านี้ผ่านไปได้ทั้งที่ชี้ที่เดียวกัน
    # (\\127.0.0.1\c$ เปิดอยู่จริงในเครื่องนี้) — ด่านนี้เป็นตัวเดียวที่ปฏิเสธโค้ด python แม้ผู้ใช้กดอนุญาตแล้ว
    DISGUISED = [
        r"copy x \\127.0.0.1\c$\LLM\skills\a\SKILL.md",
        r"copy x //localhost/C$/LLM/skills/a/SKILL.md",
        r"copy x \\?\UNC\127.0.0.1\c$\LLM\skills\a\SKILL.md",
        "open('\\\\\\\\127.0.0.1\\\\c$\\\\LLM\\\\skills\\\\a\\\\SKILL.md', 'w')",
        r"copy x %SystemDrive%\LLM\skills\a\SKILL.md",
        r"copy x %SYSTEMROOT:~0,2%\LLM\skills\a\SKILL.md",
        r"Copy-Item x $env:SystemDrive\LLM\skills\a\SKILL.md",
        r"Copy-Item x ${env:HOMEDRIVE}/LLM/mcp-local/guard.py",
        r"copy x %USERPROFILE%\..\..\LLM\skills\a\SKILL.md",
        r"copy x %SystemRoot%\..\LLM\tests\t.py",
        r"cd /d C:\LLM && copy x skills\a\SKILL.md",
        r"pushd C:\LLM & copy x mcp-local\guard.py",
        r"cd /d C:\LLM\projects && echo x > static\boot.js",
        r"cd C:\LLM; Set-Content start-qwen38.ps1 x",
        r"set R=C:\LLM&& copy x %R%\skills\a\SKILL.md",
        "import os\nos.chdir(r'C:\\LLM')\nopen('skills/a/SKILL.md','w').write('x')",
        "from pathlib import Path\n(Path('C:/LLM') / 'skills' / 'a' / 'SKILL.md').write_text('x')",
        "from pathlib import Path\n(Path('C:/') / 'LLM' / 'skills' / 'a' / 'SKILL.md').write_text('x')",
        "import os\nopen(os.path.join('C:\\\\', 'LLM', 'skills', 'a', 'SKILL.md'), 'w')",
        "import os\nopen(os.environ['SystemDrive'] + r'\\LLM\\skills\\a\\SKILL.md', 'w')",
        "import os\nopen(os.getenv('SYSTEMDRIVE') + '/LLM/mcp-local/x.py', 'w')",
        "open('C:\\\\LLM' '\\\\skills\\\\a\\\\SKILL.md', 'w')",
        r"copy x C:\LLM\MCP-LO~1\guard.py",
        r"copy x C:\LLM\projects\SETTIN~1.JSO",
        r"copy x C:\LLM\projects\..\skills\a\SKILL.md",
        r"copy x C:\LLM\.\skills\a\SKILL.md",
        r"copy x C:\LLM.\skills\a\SKILL.md",
        r'copy x "C:\LLM \skills\a\SKILL.md"',
        r"copy x C:LLM\skills\a\SKILL.md",
        r"copy x C:\LL^M\sk^ills\a\SKILL.md",
        r'copy x C:\"LLM"\skills\a\SKILL.md',
        r"copy x \LLM\skills\a\SKILL.md",
        "open('../../../skills/a/SKILL.md', 'w')",
    ]
    ORDINARY = [
        r"copy x C:\LLM\projects\data\project1\outputs\a.txt",
        r"python C:\LLM\projects\data\project1\attachments\skills.py",
        r"cd /d C:\LLM\projects\data\project1 && python -m pytest tests",
        r"cd /d C:\LLM\projects\data\project1 && python analyze.py > out.json",
        "import pandas as pd\ndf = pd.read_csv(r'C:\\LLM\\projects\\data\\p1\\attachments\\models.csv')\n"
        "df.to_csv('out.json')",
        "cols = ['llm', 'models', 'tests', 'skills']\nprint(cols)",
        "import os\nprint(os.environ.get('SystemDrive'))\nopen('outputs/skills.txt', 'w').write('x')",
        "print('C:\\\\LLM models are fast')",
        r"echo skills and tests > notes.txt",
        r"copy x ~/LLM/skills/a.md",
        r"copy x E:\data\LLM\skills\a.md",
        "open(r'D:\\\\LLM\\\\datasets\\\\tests\\\\a.csv', 'w')",
        r"set PATH=%PATH%;C:\ffmpeg\bin && ffmpeg -i a.mp4 b.mp3",
        r"curl -s http://127.0.0.1:8099/llm/models -o outputs\m.json",
        r"copy attachments\report.docx outputs\report-final.docx",
        "import re\nprint(re.sub(r'\\.\\d', '', 'a.1'))",
    ]

    def test_disguised_paths_to_protected_dirs_are_refused(self):
        for cmd in self.DISGUISED:
            self.assertEqual(guard.command_text_violation(cmd, False), "protected_path", cmd)
        # ด่านข้อความของเขตห้ามเขียนไม่กันการอ่าน (คำสั่งอ่านอย่างเดียวยังดู skill ได้)
        self.assertIsNone(guard.command_text_violation(r"type \\127.0.0.1\c$\LLM\skills\a\SKILL.md", True))

    def test_disguised_secret_paths_refused_even_read_only(self):
        for cmd in (r"type \\127.0.0.1\c$\LLM\secrets\x", r"type %SystemDrive%\LLM\sec^rets\x",
                    r"type C:\LLM\projects\..\secrets\x"):
            self.assertEqual(guard.command_text_violation(cmd, True), "secret_path", cmd)

    def test_ordinary_project_work_is_not_refused(self):
        for cmd in self.ORDINARY:
            self.assertIsNone(guard.command_text_violation(cmd, False), cmd)


if __name__ == "__main__":
    unittest.main()
