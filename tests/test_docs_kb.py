# -*- coding: utf-8 -*-
"""เทสต์คลังความรู้ (kb) + ด่านความปลอดภัยของเครื่องมือเอกสาร + การต่อสายเข้ากับ /fast และ server

ตรวจ
  * kb ค้นภาษาไทยที่ไม่มีช่องว่างได้ (trigram) ทั้งคำตรงตัวและคำที่ตรงบางส่วน, คำสั้น (EV) ด้วย LIKE,
    ผลบอกไฟล์ + หน้า/ชีต, ตารางใส่ชื่อคอลัมน์ในทุกก้อน, อัปเดตเฉพาะไฟล์ที่เปลี่ยน/หายไป
  * ไทย (fixer 2026-09-30): "ำ" กับ "ํา" ค้นเจอกันและกัน, ดัชนีรุ่นเก่าสร้างใหม่เอง, ผลจาก PDF ที่ชั้นข้อความ
    เสียมีหมายเหตุบอก
  * S04: คลังของโปรเจกต์หนึ่งไม่เห็นไฟล์ของอีกโปรเจกต์ / extract ข้ามโปรเจกต์ถูกปฏิเสธ
  * S05: ไฟล์ชื่อต้องห้ามในโฟลเดอร์แนบไม่ถูกเก็บเข้าคลัง / extract ไฟล์ต้องห้ามถูกปฏิเสธ
  * ไม่มีขอบเขตโปรเจกต์ = ปฏิเสธ (fail closed)
  * /fast: extract/kb/make_file อยู่ใน enum, help และ schema / เขียนทับผ่าน local_confirm (เล่นซ้ำ) ได้
    ส่ง token ให้ local_do ตรงๆ ใช้ไม่ได้
  * อินสแตนซ์ HTTP จริงบนพอร์ตสำรอง (8892 หรือพอร์ตว่าง) ด้วย token ทดสอบ
"""
import json
import os
import socket
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

guard = C.import_local("guard")
tools_kb = C.import_local("tools_kb")
tools_docs = C.import_local("tools_docs")
tools_fast = C.import_local("tools_fast")
extract = C.import_local("extract")


def _proj(name):
    return "kb-%s-%s" % (name, os.urandom(3).hex())


def _base(project):
    d = os.path.join(C.PROJECT_DATA, guard.project_slug(project))
    os.makedirs(os.path.join(d, "attachments"), exist_ok=True)
    return d


def _put(project, rel, text, encoding="utf-8"):
    path = os.path.join(_base(project), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=encoding) as fh:
        fh.write(text)
    return path


def kb(project, query, k=None):
    with guard.project_scope(project):
        return tools_kb.kb_search(query=query, k=k, project=project)


class KnowledgeBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = _proj("main")
        _put(cls.p, "attachments/manual.txt",
             "บทที่ 1 การติดตั้ง\nตู้ชาร์จต้องต่อสายดินก่อนจ่ายไฟ\n\n" + ("ข้อความประกอบ " * 200) +
             "\n\nบทที่ 7 การแก้ปัญหา\nถ้าหน้าจอแสดงรหัส E-217 แปลว่าแรงดันไฟฟ้าขาเข้าต่ำกว่าเกณฑ์ ให้ตรวจเบรกเกอร์หลัก\n"
             "รองรับรถ EV ทุกรุ่นที่ใช้หัว CCS2\n")
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "สถานี"
        ws.append(["รหัสสถานี", "จังหวัด", "สถานะ"])
        ws.append(["ST-101", "เชียงใหม่", "ปกติ"])
        ws.append(["ST-202", "ภูเก็ต", "รอซ่อมคอนแทคเตอร์"])
        wb.save(os.path.join(_base(cls.p), "attachments", "stations.xlsx"))
        with guard.project_scope(cls.p):
            tools_docs.make_file(format="md", name="สรุปประชุม", project=cls.p,
                                 content="# สรุปประชุม\n\nมติ: เปลี่ยนผู้รับเหมาบำรุงรักษาภายในไตรมาสหน้า\n")

    def test_exact_thai_phrase_inside_long_text(self):
        out = kb(self.p, "แรงดันไฟฟ้าขาเข้าต่ำ")
        self.assertTrue(out.startswith("[ข้อมูลจากไฟล์"))
        self.assertIn("[1] attachments/manual.txt", out)
        self.assertIn("E-217", out)
        self.assertTrue(out.rstrip().endswith("[จบข้อมูลจากไฟล์]"))

    def test_fuzzy_query_without_spaces(self):
        # ไม่มีข้อความนี้ตรงตัวในไฟล์ แต่ trigram ส่วนใหญ่ตรง ("รหัส E-217" + "แรงดันไฟฟ้า")
        out = kb(self.p, "รหัสE-217แรงดันไฟฟ้า")
        self.assertIn("attachments/manual.txt", out)

    def test_short_term_uses_like(self):
        self.assertIn("CCS2", kb(self.p, "EV"))

    def test_sheet_rows_carry_column_names(self):
        out = kb(self.p, "ภูเก็ต")
        self.assertIn("attachments/stations.xlsx · ชีต สถานี", out)
        self.assertIn("จังหวัด: ภูเก็ต", out)
        self.assertIn("รหัสสถานี: ST-202", out)

    def test_outputs_are_indexed(self):
        out = kb(self.p, "ผู้รับเหมาบำรุงรักษา")
        self.assertIn("outputs/สรุปประชุม.md", out)

    def test_no_match_and_k(self):
        self.assertIn("ไม่พบเนื้อหา", kb(self.p, "ควอนตัมฟิสิกส์ดาราศาสตร์"))
        out = kb(self.p, "ตู้ชาร์จ", k=1)
        self.assertIn("[1]", out)
        self.assertNotIn("[2]", out)

    def test_index_lives_in_project_kb_folder(self):
        kb(self.p, "ตู้ชาร์จ")
        self.assertTrue(os.path.isfile(os.path.join(_base(self.p), "kb", "index.db")))

    def test_incremental_update_and_removal(self):
        p = _proj("inc")
        path = _put(p, "attachments/a.txt", "เนื้อหาเดิม ALPHA-ONE")
        self.assertIn("ALPHA-ONE", kb(p, "ALPHA-ONE"))
        again = kb(p, "ALPHA-ONE")
        self.assertNotIn("อัปเดตดัชนี", again)                 # ไม่มีอะไรเปลี่ยน = ไม่ทำดัชนีซ้ำ
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("เนื้อหาใหม่ BRAVO-TWO ยาวขึ้นนิดหน่อย")
        out = kb(p, "BRAVO-TWO")
        self.assertIn("อัปเดตดัชนี 1 ไฟล์", out)
        self.assertIn("BRAVO-TWO", out)
        self.assertIn("ไม่พบ", kb(p, "ALPHA-ONE"))
        # ไฟล์หายไปจากคลัง (เปลี่ยนเป็นนามสกุลที่ไม่รองรับ แทนการลบไฟล์) -> ก้อนของมันต้องหายด้วย
        os.replace(path, path + ".bak")
        out = kb(p, "BRAVO-TWO")
        self.assertIn("ลบ 1", out)
        self.assertIn("ยังไม่มีไฟล์ในคลัง", out)

    def test_empty_query_and_empty_project(self):
        self.assertIn("ERROR", kb(self.p, "  "))
        p = _proj("empty")
        _base(p)
        self.assertIn("ยังไม่มีไฟล์ในคลัง", kb(p, "อะไรก็ได้"))

    def test_sara_am_forms_find_each_other(self):
        # fixer 2026-09-30: PDF หลายตัวถอด "ำ" เป็น "ํ" + "า" — ค้นด้วยรูปไหนก็ต้องเจอทั้งสองไฟล์
        p = _proj("am")
        nik, aa = chr(0x0E4D), chr(0x0E32)
        _put(p, "attachments/word-am.txt", "ตู้ชาร์จชำรุดประจำสัปดาห์ รหัส AM-1")
        _put(p, "attachments/decomposed-am.txt", "ตู้ชาร์จช" + nik + aa + "รุดประจ" + nik + aa + "สัปดาห์ รหัส AM-2")
        for q in ("ชำรุด", "ช" + nik + aa + "รุด", "จำ"):
            out = kb(p, q)
            self.assertIn("attachments/word-am.txt", out, q)
            self.assertIn("attachments/decomposed-am.txt", out, q)
            self.assertNotIn(nik, out.split("\n", 2)[2])                  # ผลค้นแสดงรูปมาตรฐาน

    def test_old_index_version_is_rebuilt(self):
        # ดัชนีรุ่นก่อนเก็บ "ํา" แยกส่วนไว้ — เปลี่ยนรุ่นแล้วต้องสร้างใหม่เอง ไม่ค้างของเก่า
        import sqlite3
        p = _proj("ver")
        _put(p, "attachments/a.txt", "ข้อมูลใหม่ VER-OK")
        kb(p, "VER-OK")
        db = os.path.join(_base(p), "kb", "index.db")
        con = sqlite3.connect(db)
        con.execute("UPDATE meta SET value='1' WHERE key='version'")
        con.execute("INSERT INTO chunks(text, file, loc) VALUES ('ของค้าง STALE-CHUNK', 'attachments/gone.txt', 'x')")
        con.commit()
        con.close()
        self.assertEqual(tools_kb.SCHEMA_VERSION, "2")
        self.assertIn("ไม่พบ", kb(p, "STALE-CHUNK"))
        self.assertIn("VER-OK", kb(p, "VER-OK"))

    def test_broken_pdf_hit_carries_note(self):
        from test_docs_extract import LEELAWADEE, thai_pdf_with_cmap
        if not os.path.exists(LEELAWADEE):
            self.skipTest("ไม่มีฟอนต์ Leelawadee UI")
        p = _proj("brk")
        path = os.path.join(_base(p), "attachments", "insp.pdf")
        thai_pdf_with_cmap(path, ["ตรวจคอนแทคเตอร์สามครั" + chr(0x0E49) + "ง BRK-PDF"], {0x0E49: 0x0478})
        _put(p, "attachments/ok.txt", "คอนแทคเตอร์ปกติ BRK-OK")
        out = kb(p, "คอนแทคเตอร์")
        self.assertIn("attachments/insp.pdf", out)
        self.assertIn("[หมายเหตุ] %s: ข้อความไทยใน attachments/insp.pdf" % extract.BROKEN_TEXT_TAG, out)
        self.assertNotIn("ใน attachments/ok.txt", out)

    def test_split_prefers_whitespace_and_overlaps(self):
        text = " ".join("คำที่%d" % i for i in range(600))
        pieces = tools_kb._split(text)
        self.assertGreater(len(pieces), 2)
        self.assertTrue(all(len(x) <= tools_kb.CHUNK for x in pieces))
        self.assertTrue(pieces[1].startswith("คำที่"))              # ไม่เริ่มก้อนกลางคำ


class DocsIsolationTests(unittest.TestCase):
    def test_kb_does_not_see_other_project(self):
        a, b = _proj("a"), _proj("b")
        _put(a, "attachments/a.txt", "ของโปรเจกต์ A: รหัสลับทางธุรกิจ AAA-778")
        _put(b, "attachments/b.txt", "ของโปรเจกต์ B: รหัสลับทางธุรกิจ BBB-889")
        out = kb(a, "รหัสลับทางธุรกิจ")
        self.assertIn("AAA-778", out)
        self.assertNotIn("BBB-889", out)

    def test_extract_other_project_is_denied(self):
        a, b = _proj("xa"), _proj("xb")
        target = _put(b, "attachments/secret-free.txt", "ข้อมูลของ B")
        with guard.project_scope(a):
            r1 = tools_docs.doc_extract(path=target, project=a)
            r2 = tools_docs.doc_extract(path=r"..\%s\attachments\secret-free.txt" % guard.project_slug(b),
                                        project=a)
        for r in (r1, r2):
            self.assertIn("ปฏิเสธ", r)
            self.assertNotIn("ข้อมูลของ B", r)

    def test_blocked_names_not_extracted_or_indexed(self):
        p = _proj("blk")
        _put(p, "attachments/api_key.txt", "BLOCKED-CONTENT-KEY-5521")
        _put(p, "attachments/team-secret-notes.txt", "BLOCKED-CONTENT-SECRET-7731")
        _put(p, "attachments/.env", "TOKEN=abc")
        _put(p, "attachments/ok.txt", "เอกสารปกติ OK-CONTENT-1")
        with guard.project_scope(p):
            for name in ("api_key.txt", "team-secret-notes.txt", ".env"):
                r = tools_docs.doc_extract(path=name, project=p)
                self.assertIn("ปฏิเสธ", r, name)
        out = kb(p, "BLOCKED-CONTENT")
        self.assertNotIn("5521", out)
        self.assertNotIn("7731", out)
        self.assertIn("OK-CONTENT-1", kb(p, "OK-CONTENT"))

    def test_relative_paths_resolve_inside_project(self):
        p = _proj("rel")
        _put(p, "attachments/spec.txt", "สเปก SPEC-42")
        with guard.project_scope(p):
            self.assertIn("SPEC-42", tools_docs.doc_extract(path="spec.txt", project=p))
            self.assertIn("SPEC-42", tools_docs.doc_extract(path="attachments/spec.txt", project=p))
            tools_docs.make_file(format="md", name="made", content="MADE-7", project=p)
            self.assertIn("MADE-7", tools_docs.doc_extract(path="/_qwen/out/made.md", project=p))
            self.assertIn("ไม่พบไฟล์", tools_docs.doc_extract(path="nope.pdf", project=p))

    def test_no_project_scope_fails_closed(self):
        p = _proj("ns")
        path = _put(p, "attachments/x.txt", "x")
        self.assertIn("ปฏิเสธ", tools_docs.doc_extract(path=path, project=p))
        self.assertIn("ปฏิเสธ", tools_kb.kb_search(query="x", project=p))

    def test_kb_folder_junction_refused(self):
        p = _proj("kbj")
        base = _base(p)
        _put(p, "attachments/x.txt", "JUNCTION-TEST")
        elsewhere = C.new_dir("kb-junction-target")
        rc = subprocess.run(["cmd", "/c", "mklink", "/J", os.path.join(base, "kb"), elsewhere],
                            capture_output=True).returncode
        if rc != 0:
            self.skipTest("สร้าง junction ไม่ได้")
        self.assertIn("ปฏิเสธ", kb(p, "JUNCTION-TEST"))
        self.assertEqual(os.listdir(elsewhere), [])


class FastSurfaceTests(unittest.TestCase):
    def test_actions_in_help_enum_and_schema(self):
        read = next(t for t in tools_fast.TOOLS if t["name"] == "local_read")
        do = next(t for t in tools_fast.TOOLS if t["name"] == "local_do")
        self.assertIn("extract", read["inputSchema"]["properties"]["action"]["enum"])
        self.assertIn("kb", read["inputSchema"]["properties"]["action"]["enum"])
        self.assertIn("make_file", do["inputSchema"]["properties"]["action"]["enum"])
        for k in ("pages", "sheet", "max_chars", "k"):
            self.assertIn(k, read["inputSchema"]["properties"])
        for k in ("format", "name", "spec", "content"):
            self.assertIn(k, do["inputSchema"]["properties"])
        h = tools_fast.help_text()
        for word in ("extract", "kb", "make_file"):
            self.assertIn(word, h)
        self.assertNotIn("tools_docs", h)                      # ไม่มีคำเตือนว่าโมดูลโหลดไม่ได้
        self.assertNotIn("tools_kb", h)

    def test_dispatch(self):
        p = _proj("fast")
        _put(p, "attachments/n.txt", "FAST-NOTE ข้อความทดสอบ")
        with guard.project_scope(p):
            self.assertIn("FAST-NOTE", tools_fast.local_read(action="extract", path="n.txt", project=p))
            self.assertIn("ยังขาดพารามิเตอร์", tools_fast.local_read(action="extract", project=p))
            self.assertIn("ยังขาดพารามิเตอร์", tools_fast.local_read(action="kb", project=p))
            self.assertIn("FAST-NOTE", tools_fast.local_read(action="kb", query="FAST-NOTE", project=p))
            r = tools_fast.local_do(action="make_file", format="docx", name="f", content="# ก", project=p)
            self.assertIn("(/_qwen/out/f.docx)", r)


class ServerReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = C.import_local("server")
        cls.server.load_modules()

    def call(self, project, name, args, rid=1):
        msg = {"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": name, "arguments": args}}
        reply = self.server.handle_rpc(msg, project, fast=True)
        return reply["result"]["content"][0]["text"]

    def test_overwrite_via_local_confirm_replay(self):
        p = _proj("srv")
        args = {"action": "make_file", "format": "md", "name": "r", "content": "เวอร์ชัน 1"}
        self.assertIn("สร้างไฟล์แล้ว", self.call(p, "local_do", args))
        hint = self.call(p, "local_do", dict(args, content="เวอร์ชัน 2"))
        tok = C.token_from_hint(hint)
        self.assertTrue(tok, hint)
        path = os.path.join(_base(p), "outputs", "r.md")
        # ทางเก่า: ส่ง token ให้ local_do ตรงๆ -> ไม่ทำอะไร
        wrong = self.call(p, "local_do", dict(args, content="เวอร์ชัน 2", confirm_token=tok))
        self.assertIn("ยังไม่ได้ทำอะไร", wrong)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "เวอร์ชัน 1")
        # token ของโปรเจกต์นี้ใช้จากโปรเจกต์อื่นไม่ได้ (แม้ส่ง review ถูกต้องมาด้วย)
        args = C.confirm_args(hint)
        self.assertIn("ใช้ไม่ได้", self.call(_proj("other"), "local_confirm", args))
        done = self.call(p, "local_confirm", args)
        self.assertIn("เขียนทับแล้ว", done)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "เวอร์ชัน 2")
        self.assertIn("ใช้ไม่ได้", self.call(p, "local_confirm", args))  # ใช้ได้ครั้งเดียว

    def test_full_surface_tools_registered(self):
        names = {t["name"] for t in self.server.TOOLS}
        self.assertTrue({"doc_extract", "make_file", "kb_search"} <= names)
        mk = next(t for t in self.server.TOOLS if t["name"] == "make_file")
        self.assertNotIn("project", mk["inputSchema"]["properties"])       # เติมจาก URL เท่านั้น
        self.assertNotIn("confirm_token", mk["inputSchema"]["properties"])  # ยืนยันผ่าน local_confirm เท่านั้น
        self.assertIn("make_file", self.server.NEEDS_PROJECT)
        self.assertIn("doc_extract", self.server.NEEDS_PROJECT)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SparePortHTTPTests(unittest.TestCase):
    """เซิร์ฟเวอร์จริงบนพอร์ตสำรองด้วย token ทดสอบ (ข้อมูลใน temp) — ปิดเฉพาะตัวที่เปิดเองตอนจบ"""

    @classmethod
    def setUpClass(cls):
        port = C.LOCAL_PORT if not C.port_in_use(C.LOCAL_PORT) else _free_port()
        cls.srv = C.TestServer(C.MCP_LOCAL, port)
        cls.srv.start()
        cls.port = port
        cls.slug = C.PROJECT_OF_ALLOWED_ORIGIN
        _put(cls.slug, "attachments/ocpp-spec.txt", "HTTP-KB-MARKER: ค่า HeartbeatInterval เริ่มต้น 300 วินาที")

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def call(self, name, args, origin=None):
        status, _h, raw = C.rpc(self.port, "/fast/%s" % self.slug, "tools/call",
                                {"name": name, "arguments": args}, origin=origin)
        self.assertEqual(status, 200, raw[:300])
        return C.tool_text(raw)

    def test_tools_list_has_new_actions(self):
        status, _h, raw = C.rpc(self.port, "/fast/%s" % self.slug, "tools/list")
        self.assertEqual(status, 200)
        tools = json.loads(raw)["result"]["tools"]
        read = next(t for t in tools if t["name"] == "local_read")
        self.assertIn("kb", read["inputSchema"]["properties"]["action"]["enum"])

    def test_extract_kb_and_make_file_over_http(self):
        self.assertIn("HTTP-KB-MARKER", self.call("local_read", {"action": "extract", "path": "ocpp-spec.txt"}))
        out = self.call("local_read", {"action": "kb", "query": "HeartbeatInterval"}, origin=C.ALLOWED_ORIGIN)
        self.assertIn("attachments/ocpp-spec.txt", out)
        made = self.call("local_do", {"action": "make_file", "format": "xlsx", "name": "http-sheet",
                                      "content": "| a | b |\n|---|---|\n| 1 | ๒ |\n"})
        self.assertIn("(/_qwen/out/http-sheet.xlsx)", made)
        self.assertTrue(os.path.isfile(os.path.join(_base(self.slug), "outputs", "http-sheet.xlsx")))

    def test_without_token_is_401(self):
        status, _h, _raw = C.rpc(self.port, "/fast/%s" % self.slug, "tools/call",
                                 {"name": "local_read", "arguments": {"action": "kb", "query": "x"}}, token=None)
        self.assertEqual(status, 401)

    def test_other_project_origin_is_403(self):
        status, _h, _raw = C.rpc(self.port, "/fast/proj-b", "tools/call",
                                 {"name": "local_read", "arguments": {"action": "extract", "path": "x.txt"}},
                                 origin=C.ALLOWED_ORIGIN)
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
