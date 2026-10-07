# -*- coding: utf-8 -*-
"""เทสต์ checkpoint / diff / undo ของ tools_files (สัญญา K1, owner mcp-exec)

ทุกไฟล์อยู่ในโฟลเดอร์ชั่วคราวของ test_security_common (ข้อมูลโปรเจกต์ + audit ก็ชี้ไป temp)
เรียกฟังก์ชันตรงๆ ในโปรเซสเดียว ไม่เปิดพอร์ต ไม่แตะ C:\\LLM\\projects\\data จริง

ตรวจ
  * write/edit เก็บ checkpoint ก่อนลงมือทุกครั้ง (journal: path, tool, sha256 ก่อน/หลัง) และผลมี diff
  * diff ถูกตัดที่ ~200 บรรทัด, ไฟล์ใหม่ตัดสั้นกว่า, ไฟล์ไบนารี/ใหญ่ไม่ทำ diff
  * undo ต้องยืนยันสองขั้นเสมอ (ไม่มี token = ไม่แตะไฟล์, token นอก local_confirm ใช้ไม่ได้)
  * token ของ undo ผูกกับเนื้อไฟล์ปัจจุบัน: ไฟล์เปลี่ยนระหว่างรอ = ใช้ไม่ได้
  * undo ย้อนทีละขั้น, สถานะก่อนย้อนถูกเก็บเสมอ, ย้อน "การย้อน" ได้ด้วย id, undo การสร้างไฟล์ = ย้ายไฟล์เข้า checkpoint
  * เครื่องมือเขียนไฟล์แก้โฟลเดอร์ checkpoints ไม่ได้ (กันปลอมประวัติ) และ undo ยังติดเขตห้ามเขียน
  * checkpoint แยกตามโปรเจกต์ (S04) และ path ต้องห้ามถูกปฏิเสธที่ listing
  * ผิวย่อ local_read checkpoints / local_do undo ส่งต่อถูกตัว และ undo ผ่าน local_confirm ของ server ได้
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

guard = C.import_local("guard")
tools_files = C.import_local("tools_files")
tools_fast = C.import_local("tools_fast")
server = C.import_local("server")


def _read(p):
    with open(p, "rb") as fh:
        return fh.read()


def _write(p, data: bytes):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(data)


def _cp_dir(slug):
    return os.path.join(C.PROJECT_DATA, slug, "checkpoints")


def _entries(slug):
    d = _cp_dir(slug)
    if not os.path.isdir(d):
        return []
    out = []
    for n in sorted(os.listdir(d), reverse=True):
        j = os.path.join(d, n, "journal.json")
        if os.path.isfile(j):
            with open(j, encoding="utf-8") as fh:
                out.append(json.load(fh))
    return out


def _confirmed(fn, tok, **kw):
    """จำลองการกดอนุญาต local_confirm (guard.confirming เปิดช่องให้ token นี้)"""
    with C.confirming(guard, tok):
        return fn(confirm_token=tok, **kw)


class _Scoped(unittest.TestCase):
    """ทุกเทสต์รันในขอบเขตโปรเจกต์ของตัวเอง เหมือนที่ server.py ครอบทุก tools/call"""
    SLUG = "cp-base"

    def setUp(self):
        self.slug = "%s-%s" % (self.SLUG, os.urandom(3).hex())
        self._scope = guard.project_scope(self.slug)
        self._scope.__enter__()
        self.d = C.new_dir("cp")

    def tearDown(self):
        self._scope.__exit__(None, None, None)

    def overwrite(self, p, content):
        out = tools_files.write_file(p, content)
        tok = C.token_from_hint(out)
        self.assertTrue(tok, out)
        return _confirmed(tools_files.write_file, tok, path=p, content=content)

    def edit(self, p, old, new):
        tok = C.token_from_hint(tools_files.edit_file(p, old, new))
        self.assertTrue(tok)
        return _confirmed(tools_files.edit_file, tok, path=p, old_string=old, new_string=new)

    def undo(self, p, id=""):  # noqa: A002
        out = tools_files.undo_file(p, id=id)
        tok = C.token_from_hint(out)
        self.assertTrue(tok, out)
        return _confirmed(tools_files.undo_file, tok, path=p, id=id)


class CheckpointOnWriteTests(_Scoped):
    SLUG = "cp-write"

    def test_new_file_records_creation_and_shows_diff(self):
        p = os.path.join(self.d, "notes.txt")
        out = tools_files.write_file(p, "line one\nline two\n")
        self.assertIn("เขียนแล้ว", out)
        self.assertIn("```diff", out)
        self.assertIn("+line one", out)
        es = _entries(self.slug)
        self.assertEqual(len(es), 1)
        e = es[0]
        self.assertEqual(e["tool"], "write_file")
        self.assertFalse(e["existed"])
        self.assertIsNone(e["blob"])
        self.assertEqual(os.path.normcase(e["path"]), os.path.normcase(os.path.realpath(p)))
        self.assertEqual(e["sha256_after"], tools_files._file_sha(p))
        self.assertIn(e["id"], out)

    def test_overwrite_saves_exact_bytes_and_hashes(self):
        p = os.path.join(self.d, "data.csv")
        original = "a,b\r\n1,ไทย\r\n".encode("utf-8")
        _write(p, original)
        out = self.overwrite(p, "a,b\n1,ใหม่\n")
        self.assertIn("เขียนแล้ว", out)
        self.assertIn("-1,ไทย", out)
        self.assertIn("+1,ใหม่", out)
        e = _entries(self.slug)[0]
        self.assertTrue(e["existed"])
        blob = os.path.join(_cp_dir(self.slug), e["id"], "before.bin")
        self.assertEqual(_read(blob), original)             # ไบต์เดิมทุกตัว รวม CRLF
        self.assertEqual(e["sha256_before"], tools_files._sha_bytes(original))
        self.assertEqual(e["sha256_after"], tools_files._file_sha(p))
        self.assertNotEqual(e["sha256_before"], e["sha256_after"])

    def test_overwrite_preview_contains_diff_before_approval(self):
        p = os.path.join(self.d, "cfg.txt")
        _write(p, b"mode=slow\n")
        out = tools_files.write_file(p, "mode=fast\n")
        self.assertIn("confirm_token", out)
        self.assertIn("-mode=slow", out)
        self.assertIn("+mode=fast", out)
        self.assertEqual(_entries(self.slug), [], "ยังไม่อนุมัติ = ยังไม่มี checkpoint")
        self.assertEqual(_read(p), b"mode=slow\n")

    def test_edit_saves_checkpoint_and_diff(self):
        p = os.path.join(self.d, "calc.txt")
        _write(p, b"x = 1\ny = 2\nz = 3\n")
        out = tools_files.edit_file(p, "y = 2", "y = 20")
        self.assertIn("confirm_token", out)
        self.assertIn("+y = 20", out)                        # diff อยู่ในขั้นขอยืนยันด้วย
        out = self.edit(p, "y = 2", "y = 20")
        self.assertIn("แก้ไขแล้ว", out)
        self.assertIn("```diff", out)
        self.assertIn("-y = 2", out)
        self.assertIn("+y = 20", out)
        e = _entries(self.slug)[0]
        self.assertEqual(e["tool"], "edit_file")
        blob = os.path.join(_cp_dir(self.slug), e["id"], "before.bin")
        self.assertEqual(_read(blob), b"x = 1\ny = 2\nz = 3\n")

    def test_diff_capped_and_new_file_capped_shorter(self):
        p = os.path.join(self.d, "big.txt")
        _write(p, "".join("old %d\n" % i for i in range(400)).encode())
        out = self.overwrite(p, "".join("new %d\n" % i for i in range(400)))
        self.assertIn("ตัด diff ที่ %d บรรทัด" % tools_files.DIFF_MAX_LINES, out)
        body = out.split("```diff", 1)[1].split("```", 1)[0]
        self.assertLessEqual(body.count("\n"), tools_files.DIFF_MAX_LINES + 3)
        p2 = os.path.join(self.d, "fresh.txt")
        out = tools_files.write_file(p2, "".join("n %d\n" % i for i in range(300)))
        self.assertIn("ตัด diff ที่ %d บรรทัด" % tools_files.DIFF_NEW_FILE_LINES, out)

    def test_binary_file_no_diff_but_checkpoint(self):
        p = os.path.join(self.d, "blob.txt")
        _write(p, b"\x00\x01\x02binary")
        out = self.overwrite(p, "text now")
        self.assertIn("ไม่แสดง diff", out)
        e = _entries(self.slug)[0]
        self.assertEqual(_read(os.path.join(_cp_dir(self.slug), e["id"], "before.bin")),
                         b"\x00\x01\x02binary")

    def test_diff_fence_survives_backticks_in_content(self):
        p = os.path.join(self.d, "readme.md")
        out = tools_files.write_file(p, "```python\nprint(1)\n```\n")
        self.assertIn("````diff", out)

    def test_too_large_file_is_not_copied_and_says_so(self):
        p = os.path.join(self.d, "large.txt")
        _write(p, b"x" * 5000)
        saved = tools_files.CHECKPOINT_FILE_CAP
        tools_files.CHECKPOINT_FILE_CAP = 1000
        try:
            out = self.overwrite(p, "small")
        finally:
            tools_files.CHECKPOINT_FILE_CAP = saved
        self.assertIn("เขียนแล้ว", out)
        self.assertIn("undo ไฟล์นี้ไม่ได้", out)
        e = _entries(self.slug)[0]
        self.assertIsNone(e["blob"])
        self.assertEqual(e["note"], "too_large")
        out = tools_files.undo_file(p)
        self.assertNotIn("confirm_token", out)
        self.assertIn("ไม่มีสำเนา", out)
        self.assertEqual(_read(p), b"small")

    def test_budget_exceeded_is_reported(self):
        p = os.path.join(self.d, "b.txt")
        _write(p, b"y" * 3000)
        saved = tools_files.CHECKPOINT_BUDGET
        tools_files.CHECKPOINT_BUDGET = 1000
        try:
            out = self.overwrite(p, "z")
        finally:
            tools_files.CHECKPOINT_BUDGET = saved
        self.assertIn("พื้นที่ checkpoint", out)
        self.assertEqual(_entries(self.slug)[0]["note"], "budget")


class UndoTests(_Scoped):
    SLUG = "cp-undo"

    def test_undo_requires_confirmation(self):
        p = os.path.join(self.d, "u.txt")
        _write(p, b"v0\n")
        self.overwrite(p, "v1\n")
        out = tools_files.undo_file(p)
        self.assertIn("confirm_token", out)
        self.assertIn("-v1", out)
        self.assertIn("+v0", out)
        self.assertEqual(_read(p).replace(b"\r\n", b"\n"), b"v1\n", "ขอยืนยันอย่างเดียวต้องไม่แตะไฟล์")
        tok = C.token_from_hint(out)
        # token ส่งตรงๆ นอก local_confirm (ทางเก่า) = ใช้ไม่ได้ และไฟล์ไม่เปลี่ยน
        out = tools_files.undo_file(p, confirm_token=tok)
        self.assertNotIn("ย้อนแล้ว", out)
        self.assertEqual(_read(p).replace(b"\r\n", b"\n"), b"v1\n")
        out = _confirmed(tools_files.undo_file, tok, path=p)
        self.assertIn("ย้อนแล้ว", out)
        self.assertEqual(_read(p), b"v0\n")
        # token ใช้ซ้ำไม่ได้
        self.overwrite(p, "v2\n")
        out = _confirmed(tools_files.undo_file, tok, path=p)
        self.assertNotIn("ย้อนแล้ว", out)

    def test_undo_token_bound_to_current_content(self):
        p = os.path.join(self.d, "drift.txt")
        _write(p, b"base\n")
        self.overwrite(p, "changed\n")
        tok = C.token_from_hint(tools_files.undo_file(p))
        _write(p, b"someone else edited\n")                 # ไฟล์เปลี่ยนระหว่างรออนุมัติ
        out = _confirmed(tools_files.undo_file, tok, path=p)
        self.assertNotIn("ย้อนแล้ว", out)
        self.assertEqual(_read(p), b"someone else edited\n")

    def test_undo_steps_back_and_can_be_reverted_by_id(self):
        p = os.path.join(self.d, "steps.txt")
        _write(p, b"v0\n")
        self.overwrite(p, "v1\n")
        self.overwrite(p, "v2\n")
        out = self.undo(p)
        self.assertIn("ย้อนแล้ว", out)
        self.assertEqual(_read(p).replace(b"\r\n", b"\n"), b"v1\n")
        redo_id = [e for e in _entries(self.slug) if e["tool"] == "undo"][0]["id"]
        self.assertIn(redo_id, out)
        out = self.undo(p)                                  # ถอยต่ออีกขั้น ไม่เด้งกลับ v2
        self.assertEqual(_read(p), b"v0\n", out)
        # ย้อน "การย้อนครั้งแรก" ด้วย id = กลับไปเป็น v2
        out = self.undo(p, id=redo_id)
        self.assertIn("ย้อนแล้ว", out)
        self.assertEqual(_read(p).replace(b"\r\n", b"\n"), b"v2\n")
        # ไม่มี checkpoint ที่ยังไม่ถูกย้อนแล้ว
        out = tools_files.undo_file(p)
        self.assertNotIn("confirm_token", out)
        self.assertIn("ไม่พบ checkpoint", out)

    def test_undo_creation_moves_file_into_checkpoint(self):
        p = os.path.join(self.d, "created.txt")
        tools_files.write_file(p, "brand new\n")
        self.assertTrue(os.path.isfile(p))
        out = self.undo(p)
        self.assertIn("ย้อนแล้ว", out)
        self.assertFalse(os.path.exists(p))
        e = [x for x in _entries(self.slug) if x["tool"] == "undo"][0]
        blob = os.path.join(_cp_dir(self.slug), e["id"], "before.bin")
        self.assertEqual(_read(blob).replace(b"\r\n", b"\n"), b"brand new\n", "ไฟล์ไม่หาย แค่ย้ายเข้า checkpoint")
        # ย้อนการย้อน = ไฟล์กลับมา
        self.undo(p, id=e["id"])
        self.assertEqual(_read(p).replace(b"\r\n", b"\n"), b"brand new\n")

    def test_undo_nothing_to_do(self):
        p = os.path.join(self.d, "same.txt")
        _write(p, b"a\n")
        self.overwrite(p, "b\n")
        _write(p, b"a\n")                                   # ผู้ใช้แก้กลับเองแล้ว
        out = tools_files.undo_file(p)
        self.assertNotIn("confirm_token", out)
        self.assertIn("ไม่มีอะไรให้ย้อน", out)

    def test_undo_without_any_checkpoint(self):
        p = os.path.join(self.d, "never.txt")
        _write(p, b"x")
        out = tools_files.undo_file(p)
        self.assertIn("ไม่พบ checkpoint", out)

    def test_corrupted_blob_refused(self):
        p = os.path.join(self.d, "c.txt")
        _write(p, b"orig\n")
        self.overwrite(p, "new\n")
        e = _entries(self.slug)[0]
        _write(os.path.join(_cp_dir(self.slug), e["id"], "before.bin"), b"tampered")
        out = tools_files.undo_file(p)
        self.assertIn("เสียหาย", out)
        self.assertNotIn("confirm_token", out)


class TamperAndScopeTests(_Scoped):
    SLUG = "cp-sec"

    def test_file_tools_cannot_write_checkpoints_dir(self):
        p = os.path.join(self.d, "t.txt")
        tools_files.write_file(p, "one")
        e = _entries(self.slug)[0]
        journal = os.path.join(_cp_dir(self.slug), e["id"], "journal.json")
        forged = json.dumps(dict(e, path=r"C:\LLM\mcp-local\guard.py"))
        out = tools_files.write_file(journal, forged, confirm_token="deadbeef")
        self.assertTrue(out.startswith("ปฏิเสธ"), out)
        out = tools_files.write_file(os.path.join(_cp_dir(self.slug), "new.txt"), "x")
        self.assertTrue(out.startswith("ปฏิเสธ"), out)
        out = tools_files.edit_file(journal, '"tool"', '"toolx"')
        self.assertTrue(out.startswith("ปฏิเสธ"), out)
        out = tools_files.undo_file(journal)
        self.assertTrue(out.startswith("ปฏิเสธ"), out)
        self.assertTrue(tools_files.in_checkpoints(journal))
        self.assertFalse(tools_files.in_checkpoints(p))

    def test_forged_journal_cannot_target_protected_path(self):
        # ปลอม checkpoint (ด้วยมือ ไม่ผ่านเครื่องมือ) ให้ชี้ไปโค้ดของสแตก — undo ต้องติดเขตห้ามเขียน
        target = r"C:\LLM\mcp-local\guard.py"
        cid = "20260101-000000-000000-abcd"
        d = os.path.join(_cp_dir(self.slug), cid)
        os.makedirs(d, exist_ok=True)
        _write(os.path.join(d, "before.bin"), b"evil = True\n")
        with open(os.path.join(d, "journal.json"), "w", encoding="utf-8") as fh:
            json.dump({"id": cid, "tool": "write_file", "path": target, "existed": True,
                       "blob": "before.bin",
                       "sha256_before": tools_files._sha_bytes(b"evil = True\n")}, fh)
        out = tools_files.undo_file(target)
        self.assertTrue(out.startswith("ปฏิเสธ"), out)
        self.assertNotIn("confirm_token", out)

    def test_checkpoints_are_per_project(self):
        p = os.path.join(self.d, "shared.txt")
        _write(p, b"A0\n")
        self.overwrite(p, "A1\n")
        self.assertIn("A1", _read(p).decode())
        with guard.project_scope(self.slug + "-other"):
            out = tools_files.list_checkpoints(p)
            self.assertIn("ยังไม่มี checkpoint", out)
            out = tools_files.undo_file(p)
            self.assertIn("ไม่พบ checkpoint", out)
        out = tools_files.list_checkpoints(p)
        self.assertIn("write_file", out)

    def test_other_project_checkpoint_folder_is_unreadable(self):
        p = os.path.join(self.d, "s.txt")
        tools_files.write_file(p, "secret-ish project data")
        e = _entries(self.slug)[0]
        folder = os.path.join(_cp_dir(self.slug), e["id"])
        with guard.project_scope(self.slug + "-spy"):
            with self.assertRaises(guard.Denied):
                guard.check_read(os.path.join(folder, "journal.json"))

    def test_listing_blocked_path_denied(self):
        out = tools_files.list_checkpoints(os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa"))
        self.assertTrue(out.startswith("ปฏิเสธ"), out)

    def test_undo_denied_for_protected_path_even_with_token(self):
        out = tools_files.undo_file(r"C:\LLM\mcp-local\tools_files.py", confirm_token="deadbeef")
        self.assertTrue(out.startswith("ปฏิเสธ"), out)

    def test_listing_shows_flags(self):
        p = os.path.join(self.d, "l.txt")
        _write(p, b"0")
        self.overwrite(p, "1")
        self.undo(p)
        out = tools_files.list_checkpoints(p)
        self.assertIn("ย้อนแล้ว", out)
        self.assertIn("ย้อนจาก", out)
        self.assertIn("undo", out)
        out = tools_files.list_checkpoints()
        self.assertIn(self.slug, out)


class FastSurfaceTests(_Scoped):
    SLUG = "cp-fast"

    def test_rows_and_schema(self):
        read_enum = tools_fast.TOOLS[0]["inputSchema"]["properties"]["action"]["enum"]
        do_enum = tools_fast.TOOLS[1]["inputSchema"]["properties"]["action"]["enum"]
        self.assertIn("checkpoints", read_enum)
        self.assertIn("undo", do_enum)
        self.assertIn("python", do_enum)
        props = tools_fast.TOOLS[1]["inputSchema"]["properties"]
        self.assertIn("code", props)
        self.assertIn("timeout", props)
        help_text = tools_fast.help_text()
        for word in ("checkpoints", "undo", "python"):
            self.assertIn(word, help_text)
        self.assertIn("[ยืนยัน]", dict((r[0], r[2]) for r in tools_fast.DO_ROWS)["python"])
        self.assertIn("[ยืนยัน]", dict((r[0], r[2]) for r in tools_fast.DO_ROWS)["undo"])

    def test_fast_checkpoints_and_undo(self):
        p = os.path.join(self.d, "f.txt")
        tools_fast.local_do(action="write", project=self.slug, path=p, content="first\n")
        out = tools_fast.local_read(action="checkpoints", project=self.slug, path=p)
        self.assertIn("write_file", out)
        out = tools_fast.local_do(action="undo", project=self.slug)
        self.assertIn("ยังขาดพารามิเตอร์", out)
        out = tools_fast.local_do(action="undo", project=self.slug, path=p)
        self.assertIn("confirm_token", out)
        self.assertTrue(os.path.isfile(p))
        tok = C.token_from_hint(out)
        with C.confirming(guard, tok):
            out = tools_fast.local_do(action="undo", project=self.slug, path=p, confirm_token=tok)
        self.assertIn("ย้อนแล้ว", out)
        self.assertFalse(os.path.exists(p))

    def test_undo_through_server_local_confirm(self):
        """เส้นทางจริง: local_do(undo) -> token -> local_confirm เล่นซ้ำ (ส่ง token ให้ local_do ตรงๆ ไม่ได้)"""
        p = os.path.join(self.d, "srv.txt")
        _write(p, b"keep me\n")
        with guard.project_scope(self.slug):
            self.overwrite(p, "oops\n")

        def call(name, args):
            msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": name, "arguments": args}}
            return server.handle_rpc(msg, self.slug, fast=True)["result"]["content"][0]["text"]

        server.load_modules()
        hint = call("local_do", {"action": "undo", "path": p})
        tok = C.token_from_hint(hint)
        self.assertTrue(tok, hint)
        out = call("local_do", {"action": "undo", "path": p, "confirm_token": tok})
        self.assertIn("local_confirm", out)
        self.assertIn("oops", _read(p).decode())
        out = call("local_confirm", C.confirm_args(hint))
        self.assertIn("ย้อนแล้ว", out)
        self.assertEqual(_read(p), b"keep me\n")
        out = call("local_confirm", C.confirm_args(hint))
        self.assertIn("ใช้ไม่ได้", out)


if __name__ == "__main__":
    unittest.main()
