# -*- coding: utf-8 -*-
"""เทสต์ของ integrator รอบ 4 (2026-09-30) — แก้จุดที่เจอตอนทดสอบ E2E กับโมเดลจริง

* make_file: โมเดล 4B ส่ง spec (JSON แล้วตามด้วย XML) ให้ docx ซ้ำสามรอบ เพราะข้อความ error เดิมบอกแค่ว่าผิด
  ตอนนี้ docx/pdf/md ที่มี spec แต่ไม่มี content ต้องได้คำแนะนำที่บอกให้ส่ง Markdown ใน content พร้อมตัวอย่าง
  และต้องไม่สร้างไฟล์ใดๆ (ทั้ง spec ที่เป็น JSON และที่ไม่ใช่ JSON)
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

guard = C.import_local("guard")
tools_docs = C.import_local("tools_docs")


class MakeFileSpecGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.project = "integ-r4-%s" % os.urandom(3).hex()
        self.outputs = os.path.join(C.PROJECT_DATA, guard.project_slug(self.project), "outputs")

    def make(self, **kw):
        with guard.project_scope(self.project):
            return tools_docs.make_file(project=self.project, **kw)

    def _files(self):
        return sorted(os.listdir(self.outputs)) if os.path.isdir(self.outputs) else []

    def test_text_formats_reject_spec_with_markdown_hint(self):
        specs = [json.dumps({"title": "สถานะ", "content": [{"type": "table", "data": [["1", "ปกติ"]]}]},
                            ensure_ascii=False),
                 "<docx><table><row><cell>ตู้</cell></row></table></docx>",      # ที่โมเดลส่งจริงรอบที่สาม
                 {"title": "x"}]
        for fmt in ("docx", "pdf", "md"):
            for spec in specs:
                r = self.make(format=fmt, name="รายงานทดสอบ", spec=spec)
                self.assertTrue(r.startswith("ERROR: %s ไม่รับ spec" % fmt), r)
                self.assertIn("content", r)
                self.assertIn("|---|", r)                 # มีตัวอย่างตาราง Markdown ให้ลอก
        self.assertEqual(self._files(), [])               # ไม่มีไฟล์ถูกสร้าง

    def test_content_still_wins_and_spec_formats_unchanged(self):
        r = self.make(format="md", name="ok", content="# หัวข้อ\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
                      spec='{"ignored": true}')
        self.assertIn("/_qwen/out/ok.md", r)
        r = self.make(format="csv", name="c", spec={"columns": ["x"], "rows": [["1"]]})
        self.assertIn("/_qwen/out/c.csv", r)
        r = self.make(format="docx", name="bad", spec="")
        self.assertTrue(r.startswith("ERROR: ต้องมี content"), r)   # ว่างทั้งคู่ = ข้อความเดิม


class FastSchemaKeyOrderTests(unittest.TestCase):
    """llama-server บังคับ tool call ด้วย grammar จาก JSON schema ที่ให้คีย์ตามกันได้เฉพาะตามลำดับ properties
    (คีย์ที่ไม่ required) — ลำดับที่คู่มือบอกโมเดลต้องเป็นลำดับที่ grammar ยอมให้เขียนได้จริง"""

    @classmethod
    def setUpClass(cls):
        cls.tf = C.import_local("tools_fast")
        cls.tools = {t["name"]: t for t in cls.tf.TOOLS}

    def _keys(self, tool):
        return [k for k in self.tools[tool]["inputSchema"]["properties"] if k not in ("action", "project")]

    def _map(self, tool):
        desc = self.tools[tool]["description"]
        body = desc.split("พารามิเตอร์: ", 1)[1].split(" · ", 1)[0]
        out = {}
        for part in body.split():
            act, _, names = part.partition(":")
            out[act] = names.split(",") if names else []
        return out

    def assertWritable(self, tool, names):
        keys = self._keys(tool)
        idx = [keys.index(n) for n in names]
        self.assertEqual(idx, sorted(idx), "%s: %s เขียนตามลำดับนี้ไม่ได้ (schema: %s)" % (tool, names, keys))

    def test_description_order_matches_schema(self):
        for tool in ("local_read", "local_do"):
            m = self._map(tool)
            self.assertGreater(len(m), 5)
            for act, names in m.items():
                self.assertWritable(tool, names)

    def test_documented_natural_orders_are_writable(self):
        for names in (["format", "name", "content", "spec"], ["kind", "text", "tags"],
                      ["alias", "path", "kind"], ["command", "path", "limit"], ["path", "content"],
                      ["path", "old", "new", "overwrite"], ["code", "timeout"], ["path", "id"],
                      ["path", "out", "start", "duration", "fps", "width"]):
            self.assertWritable("local_do", names)
        for names in (["pattern", "path", "kind"], ["alias", "path"], ["path", "start", "limit"],
                      ["query", "kind", "limit"], ["path", "pages", "sheet", "max_chars"], ["query", "k"]):
            self.assertWritable("local_read", names)

    def test_no_param_lost_by_reorder(self):
        self.assertEqual(set(self._keys("local_do")), set(self.tf._DO_PARAMS))
        for k in ("content", "code", "spec", "format", "name", "confirm_token", "overwrite", "timeout"):
            self.assertIn(k, self._keys("local_do"))
        self.assertEqual(self.tools["local_do"]["inputSchema"]["properties"]["overwrite"], {"type": "boolean"})
        for k in ("pages", "sheet", "max_chars", "k", "query", "path"):
            self.assertIn(k, self._keys("local_read"))


class FastProjectRelativePathTests(unittest.TestCase):
    """path แบบ attachments/x ที่เครื่องมือรอบนี้แสดงออกมา ต้องใช้ต่อกับ read/list/edit ได้ (เดิมถูกต่อกับ cwd ของ MCP
    = C:\\LLM\\mcp-local แล้วล้มว่าเขตห้ามเขียน) และการแปลงต้องไม่เปิดทางข้ามโปรเจกต์"""

    @classmethod
    def setUpClass(cls):
        cls.tf = C.import_local("tools_fast")

    def setUp(self):
        self.project = "integ-rel-%s" % os.urandom(3).hex()
        self.base = guard.project_dir(self.project)
        os.makedirs(os.path.join(self.base, "attachments"), exist_ok=True)
        self.file = os.path.join(self.base, "attachments", "note.txt")
        with open(self.file, "w", encoding="utf-8") as fh:
            fh.write("สถานะ: ปกติ\n")

    def test_mapping_rules(self):
        rel = self.tf._project_rel
        p = self.project
        self.assertEqual(rel("attachments/note.txt", p), os.path.join(self.base, "attachments/note.txt"))
        self.assertEqual(rel(".\\outputs\\a.docx", p), os.path.join(self.base, "outputs\\a.docx"))
        self.assertEqual(rel("Attachments", p), os.path.join(self.base, "Attachments"))
        for keep in ("note.txt", "C:\\x\\attachments\\a", "\\attachments\\a", "docs/attachments/a",
                     "%TEMP%\\a", "~\\attachments", ""):
            self.assertEqual(rel(keep, p), keep)
        self.assertEqual(rel("attachments/a", ""), "attachments/a")       # ไม่มีโปรเจกต์ = ไม่แตะ

    def test_read_list_edit_use_project_folder(self):
        with guard.project_scope(self.project):
            r = self.tf.local_read(action="read", project=self.project, path="attachments/note.txt")
            self.assertIn("ปกติ", r)
            r = self.tf.local_read(action="list", project=self.project, path="attachments")
            self.assertIn("note.txt", r)
            r = self.tf.local_do(action="edit", project=self.project, path="attachments/note.txt",
                                 old="ปกติ", new="ชำรุด")
        self.assertNotIn("เขตห้ามเขียน", r)
        self.assertIn("confirm_token", r)                 # ยังต้องยืนยันสองขั้นเหมือนเดิม
        with open(self.file, encoding="utf-8") as fh:
            self.assertIn("ปกติ", fh.read())              # ยังไม่ได้แก้จริง

    def test_dotdot_to_other_project_still_denied(self):
        other = "integ-rel-other-%s" % os.urandom(3).hex()
        ob = guard.project_dir(other)
        os.makedirs(os.path.join(ob, "attachments"), exist_ok=True)
        with open(os.path.join(ob, "attachments", "other-note.txt"), "w", encoding="utf-8") as fh:
            fh.write("TOP-SECRET-OTHER")
        sneaky = "attachments/../../%s/attachments/other-note.txt" % guard.project_slug(other)
        with guard.project_scope(self.project):
            r = self.tf.local_read(action="read", project=self.project, path=sneaky)
            w = self.tf.local_do(action="write", project=self.project, path=sneaky, content="x")
        self.assertNotIn("TOP-SECRET-OTHER", r)
        self.assertIn("S04", r)
        self.assertIn("S04", w)
        with open(os.path.join(ob, "attachments", "other-note.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "TOP-SECRET-OTHER")


if __name__ == "__main__":
    unittest.main()
