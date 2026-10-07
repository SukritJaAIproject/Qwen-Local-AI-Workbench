# -*- coding: utf-8 -*-
r"""เทสต์ถดถอยของรอบแก้ช่องโหว่ 2026-09-30 (รอบ FIXER สำหรับ MCP/GUARD)

ครอบช่องโหว่ที่ audit รอบสองพบ แล้วแก้ในรอบนี้ ทุกเทสต์ "ผ่าน" กับโค้ดปัจจุบัน และ
"ล้ม" กับโค้ดก่อนแก้ (ดูวิธีรันกับ backup ใน test_security_common.py) เรียกฟังก์ชันตรงๆ
ในโปรเซสเดียว ไม่เปิดพอร์ต ไฟล์ทั้งหมดอยู่ในโฟลเดอร์ชั่วคราว ไม่แตะของจริง

หัวข้อ (อ้างชื่อในรายงาน audit)
  F1/F4  audit.log และ C:\\LLM\\logs\\*.log อ่านข้ามโปรเจกต์ได้ (S04)
  F5     where /r และ dir /s เผยชื่อไฟล์ในโฟลเดอร์ต้องห้าม
  F7     FORBIDDEN จับคำว่า "format" ทุกที่ ทำให้ nvidia-smi --format / git log --format ถูกปฏิเสธ
  F8     gateway_status รายงานคีย์ว่า "ยังไม่ได้ตั้งค่า" ทั้งที่มีไฟล์คีย์อยู่
  F9     ข้อความความจำว่างชี้ชื่อเครื่องมือที่ผิวย่อไม่มี (memory_remember)
  F11    wildcard ชื่อ 8.3 (SAMPLE~1.TXT) ข้ามการบล็อกไฟล์รายตัว
  F12    git show/cat-file/grep <rev>:<path> อ่านเนื้อไฟล์ต้องห้ามที่ commit ไว้
  F13    S04 fail-open เมื่อไม่มีขอบเขตโปรเจกต์
  F14    นามสกุลสคริปต์ที่ตกหล่น, .vscode, และคำนำหน้า \\?\ หลุดด่านห้ามเขียน
  F2.4   ไฟล์รายการเล่น (m3u8/ffconcat) ทำให้ ffmpeg ไปเปิดไฟล์อื่น (ข้ามโปรเจกต์/SSRF)

รอบ FIXER ครั้งที่สอง (ของที่รอบแรกยังตกหรือทำให้พังเพิ่ม — ทุกข้อทำซ้ำได้จริงก่อนแก้)
  R1  บล็อก log ของสแตกด้วย fnmatch ลามไปบล็อก .log ที่ผู้ใช้แนบไว้ในโปรเจกต์ตัวเอง
  R2  wildcard: ? ของ DOS ตรงศูนย์ตัวอักษร (sample_key??.txt) และ [ ] ตรงตัว ([a]b*) ยังอ่านไฟล์ต้องห้ามได้
  R3  git show / log -p / diff / show :0:<path> / log -L / show <blob-id> พิมพ์เนื้อไฟล์ต้องห้ามโดยไม่ยืนยัน
  R4  dir /s (ไม่มี /b) และ tree พิมพ์ชื่อไฟล์ในโฟลเดอร์ต้องห้ามแบบกรองไม่ได้, where แบบไม่ /r ไม่ถูกกรอง
  R5  \\.\ และ \\?\Volume{..}\ ไม่ถูกจัดการ
  R6  ffmpeg ไม่มี -protocol_whitelist, manifest DASH/SDP ไม่ถูกดัก
  R7  ขั้นยืนยันผ่านโมเดล (major): ส่ง token กลับให้เครื่องมือเดิมก็ลงมือได้เลย
  R8  Origin ของหน้าโปรเจกต์ A เรียก URL ของโปรเจกต์ B ได้ (token เดียวกันทุกโปรเจกต์)
"""
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

guard = C.import_local("guard")
tools_files = C.import_local("tools_files")
tools_media = C.import_local("tools_media")
tools_memory = C.import_local("tools_memory")
tools_tasks = C.import_local("tools_tasks")
server = C.import_local("server")

HOME = os.path.expanduser("~")


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


class F1SharedLogsTests(unittest.TestCase):
    """audit.log / logs\\*.log / hub.log รวมกิจกรรมของทุกโปรเจกต์ — โปรเจกต์เดียวอ่านไม่ได้"""

    BLOCKED = [
        r"C:\LLM\mcp-local\audit.log",
        r"C:\LLM\mcp-websearch\audit.log",
        r"C:\LLM\mcp-local\server.err.log",
        r"C:\LLM\logs\mcp-local.out.log",
        r"C:\LLM\logs\gateway.out.log",
        r"C:\LLM\projects\hub.log",
    ]

    def test_shared_logs_denied_for_read(self):
        with guard.project_scope("project1"):
            for p in self.BLOCKED:
                with self.assertRaises(guard.Denied, msg=p):
                    guard.check_read(p)

    def test_shared_logs_denied_via_grep_tool(self):
        # grep_search ไม่ควรเดินเข้าไปอ่าน audit.log ของสแตกได้ แม้ pattern ตรง
        with guard.project_scope("project1"):
            out = tools_files.read_file(r"C:\LLM\mcp-local\audit.log")
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:120])


class F5RecursiveScanTests(unittest.TestCase):
    """where /r และ dir /s ยังรันได้ แต่ผลลัพธ์ต้องไม่เผยชื่อไฟล์ในโฟลเดอร์ต้องห้าม"""

    def setUp(self):
        self.d = C.new_dir("f5scan")
        os.makedirs(os.path.join(self.d, ".ssh"), exist_ok=True)
        with open(os.path.join(self.d, ".ssh", "id_rsa"), "w", encoding="utf-8") as fh:
            fh.write("FAKE-KEY-MARKER-9931")
        with open(os.path.join(self.d, "readme.txt"), "w", encoding="utf-8") as fh:
            fh.write("hello")

    def test_where_r_redacts_blocked_paths(self):
        out = tools_files.exec_shell_command("where /r %s id_rsa" % self.d, cwd=self.d)
        self.assertNotIn("id_rsa", out, out[:200])
        self.assertIn("ปิดบัง", out)

    def test_dir_s_redacts_blocked_paths(self):
        out = tools_files.exec_shell_command("dir /s /b %s" % self.d, cwd=self.d)
        self.assertNotIn(os.path.join(self.d, ".ssh", "id_rsa"), out)
        # ไฟล์ปกติในโฟลเดอร์เดียวกันยังต้องเห็น (ไม่ over-redact)
        self.assertIn("readme.txt", out, out[:300])

    def test_dir_s_stays_readonly(self):
        self.assertTrue(tools_files._is_readonly("dir /s /b"))


class F7ForbiddenFormatTests(unittest.TestCase):
    """FORBIDDEN ต้องจับ format เฉพาะตอนเป็นโปรแกรมที่ถูกเรียก ไม่ใช่ --format ของ flag"""

    def test_query_and_format_flags_not_forbidden(self):
        for cmd in ("nvidia-smi --query-gpu=name,memory.used --format=csv",
                    "nvidia-smi --query-gpu=name --format=csv,noheader,nounits",
                    "git log --format=%h -1", "git log --pretty=format:%H -5"):
            self.assertIsNone(tools_files.FORBIDDEN.search(cmd), cmd)

    def test_query_forms_are_readonly(self):
        # C5: nvidia-smi query forms และ git log --format แบบไม่มี metachar ต้องรันทันที
        for cmd in ("nvidia-smi --query-gpu=name,memory.used --format=csv",
                    "nvidia-smi --query-gpu=name --format=csv,noheader,nounits",
                    "git log --format=short -1", "git log --format=oneline"):
            self.assertTrue(tools_files._is_readonly(cmd), cmd)

    def test_format_with_percent_is_confirmable_not_forbidden(self):
        # git log --format=%h มี % (cmd แทนค่าตัวแปร) จึงไม่ใช่อ่านอย่างเดียว แต่ "ต้องไม่ถูกปฏิเสธถาวร"
        # คือได้ขั้นยืนยัน ไม่ใช่โดน FORBIDDEN ตัดทิ้ง (นี่คือแก่นของ F7)
        self.assertIsNone(tools_files.FORBIDDEN.search("git log --format=%h -1"))
        self.assertFalse(tools_files._is_readonly("git log --format=%h -1"))

    def test_real_format_command_still_forbidden(self):
        for cmd in ("format C:", "format c: /q", "dir & format D:", "diskpart"):
            self.assertIsNotNone(tools_files.FORBIDDEN.search(cmd), cmd)


class F8GatewayKeySourceTests(unittest.TestCase):
    """gateway_status ต้องรายงานว่ามีไฟล์คีย์อยู่ ถึงโปรเซสนี้จะยังไม่โหลด _KEY"""

    def test_reports_file_when_key_file_exists(self):
        gw = C.import_local("gateway")
        from pathlib import Path
        d = C.new_dir("gwkey")
        keyfile = os.path.join(d, "gateway_key.txt")
        with open(keyfile, "w", encoding="utf-8") as fh:
            fh.write("not-a-real-key-value\n")
        saved_path, saved_key = gw.KEY_PATH, gw._KEY
        saved_env = os.environ.pop(gw.KEY_ENV, None)
        gw.KEY_PATH, gw._KEY = Path(keyfile), ""
        try:
            src = gw._key_source()
        finally:
            gw.KEY_PATH, gw._KEY = saved_path, saved_key
            if saved_env is not None:
                os.environ[gw.KEY_ENV] = saved_env
        self.assertIn("ไฟล์", src)
        self.assertNotIn("ยังไม่ได้ตั้งค่า", src)

    def test_reports_not_set_when_no_file(self):
        gw = C.import_local("gateway")
        from pathlib import Path
        saved_path, saved_key = gw.KEY_PATH, gw._KEY
        saved_env = os.environ.pop(gw.KEY_ENV, None)
        gw.KEY_PATH, gw._KEY = Path(os.path.join(C.TMP, "no-such-key.txt")), ""
        try:
            src = gw._key_source()
        finally:
            gw.KEY_PATH, gw._KEY = saved_path, saved_key
            if saved_env is not None:
                os.environ[gw.KEY_ENV] = saved_env
        self.assertIn("ยังไม่ได้ตั้งค่า", src)


class F9MemoryHintTests(unittest.TestCase):
    """ข้อความความจำว่างต้องบอก action ที่เรียกได้จริงบนผิวย่อ (local_do action=remember)"""

    def test_recall_hint_names_fast_action(self):
        with guard.project_scope("empty-hint-proj"):
            out = tools_memory.memory_recall(project="empty-hint-proj")
        self.assertIn('local_do', out)
        self.assertIn('remember', out)

    def test_export_hint_names_fast_action(self):
        with guard.project_scope("empty-hint-proj2"):
            out = tools_memory.memory_export(project="empty-hint-proj2")
        self.assertIn('local_do', out)
        self.assertIn('remember', out)


class F11ShortNameGlobTests(unittest.TestCase):
    """wildcard ที่ตรงกับชื่อ 8.3 ของไฟล์ต้องห้าม ต้องถูกปฏิเสธเหมือนตรงกับชื่อยาว"""

    def setUp(self):
        self.d = C.new_dir("f11short")
        self.key = os.path.join(self.d, "sample_key.txt")   # ตรง blocked_glob *_key.txt
        with open(self.key, "w", encoding="utf-8") as fh:
            fh.write("SHORTNAME-LEAK-MARKER-5521")
        self.short = guard._short_name(self.key)

    def test_check_glob_denies_via_short_name(self):
        if not self.short or "~" not in self.short:
            self.skipTest("ไดรฟ์นี้ไม่ได้สร้างชื่อ 8.3 จึงไม่มีอะไรให้ทดสอบ")
        base = os.path.basename(self.short)
        pattern = os.path.join(self.d, base[:-5] + "?" + base[-4:])
        with self.assertRaises(guard.Denied):
            guard.check_glob(pattern)

    def test_exec_type_short_name_does_not_leak(self):
        if not self.short or "~" not in self.short:
            self.skipTest("ไดรฟ์นี้ไม่ได้สร้างชื่อ 8.3")
        base = os.path.basename(self.short)
        out = tools_files.exec_shell_command("type %s" % (base[:-5] + "?" + base[-4:]), cwd=self.d)
        self.assertNotIn("SHORTNAME-LEAK-MARKER-5521", out)
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:120])

    def test_long_name_wildcard_still_denied(self):
        out = tools_files.exec_shell_command("type *.txt", cwd=self.d)
        self.assertNotIn("SHORTNAME-LEAK-MARKER-5521", out)


class F12GitRevPathTests(unittest.TestCase):
    """git <content-sub> <rev>:<path> ที่ path เป็นไฟล์ต้องห้าม ต้องถูกปฏิเสธเด็ดขาด"""

    def test_revpath_to_blocked_file_denied(self):
        for cmd in ("git show HEAD:.env", "git show HEAD:config/secret.pem",
                    "git cat-file -p HEAD:.env", "git show HEAD:sub/id_rsa",
                    "git log -p HEAD:credentials.json"):
            argv = tools_files._argv(cmd)
            self.assertIsNotNone(guard.git_revpath_violation(argv), cmd)

    def test_revpath_to_normal_file_allowed(self):
        for cmd in ("git show HEAD:README.md", "git show HEAD:src/main.py"):
            argv = tools_files._argv(cmd)
            self.assertIsNone(guard.git_revpath_violation(argv), cmd)
        # git show HEAD:README.md ต้องยังนับเป็นอ่านอย่างเดียว (ไม่ถูกทำให้ต้องยืนยัน)
        self.assertTrue(tools_files._is_readonly("git show HEAD:README.md"))

    def test_exec_git_revpath_blocked(self):
        d = C.new_dir("gitrev")
        out = tools_files.exec_shell_command("git show HEAD:.env", cwd=d)
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:160])

    def test_git_grep_and_cat_file_need_confirmation(self):
        for cmd in ("git grep secret", "git cat-file -p HEAD"):
            self.assertFalse(tools_files._is_readonly(cmd), cmd)


class F13ScopeFailClosedTests(unittest.TestCase):
    """ไม่มีขอบเขตโปรเจกต์ + ไม่ใช่โค้ดภายใน = ห้ามแตะข้อมูลของโปรเจกต์ใดๆ (fail closed)"""

    def setUp(self):
        self.other = os.path.join(C.PROJECT_DATA, "victim13")
        os.makedirs(self.other, exist_ok=True)
        with open(os.path.join(self.other, "memory.json"), "w", encoding="utf-8") as fh:
            fh.write("secret")

    def test_no_scope_denies_project_data(self):
        # ยืนยันว่าไม่มีขอบเขต (เรียกนอก project_scope)
        self.assertIsNone(guard.current_project())
        with self.assertRaises(guard.Denied):
            guard.check_read(os.path.join(self.other, "memory.json"))

    def test_internal_still_allowed_without_scope(self):
        with guard.internal():
            self.assertTrue(guard.check_read(os.path.join(self.other, "memory.json")))

    def test_scoped_owner_still_allowed(self):
        with guard.project_scope("victim13"):
            self.assertTrue(guard.check_read(os.path.join(self.other, "memory.json")))


class F14CoverageGapTests(unittest.TestCase):
    """นามสกุลสคริปต์ที่ตกหล่น, .vscode, และคำนำหน้า \\?\\ ต้องถูกด่านห้ามเขียนเห็น"""

    def test_new_handler_scripts_require_confirmation(self):
        d = C.new_dir("f14ext")
        for name in ("x.scf", "x.inf", "x.chm", "x.xll", "x.application", "x.ps1xml", "x.psc1"):
            p = os.path.join(d, name)
            out = tools_files.write_file(p, "payload")
            self.assertIn("confirm_token", out, name)
            self.assertFalse(os.path.exists(p), name)

    def test_vscode_targets_write_protected(self):
        d = C.new_dir("f14vscode")
        for name in ("tasks.json", "settings.json"):
            target = os.path.join(d, ".vscode", name)
            with self.assertRaises(guard.Denied, msg=target):
                guard.check_write(target)
        out = tools_files.write_file(os.path.join(d, ".vscode", "tasks.json"),
                                     "{}", confirm_token="deadbeef")
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:120])

    def test_extended_length_prefix_hits_write_protected(self):
        for raw in (r"\\?\C:\LLM\mcp-local\guard.py", r"\\?\C:\LLM\projects\hub.py",
                    r"\\?\C:\LLM\start-qwen38.ps1"):
            self.assertIsNotNone(guard.write_protected_hit(raw), raw)
            with self.assertRaises(guard.Denied, msg=raw):
                guard.check_write(raw)

    def test_extended_prefix_normalizes_to_real_path(self):
        self.assertEqual(guard._norm(r"\\?\C:\LLM\mcp-local\guard.py"),
                         guard._norm(r"C:\LLM\mcp-local\guard.py"))


class F2MediaIndirectionTests(unittest.TestCase):
    """ไฟล์รายการเล่น/สคริปต์ต่อไฟล์ (m3u8/ffconcat) ต้องถูกปฏิเสธก่อนส่งให้ ffmpeg"""

    def _make(self, name, content):
        d = C.new_dir("f2media")
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)
        return p

    def test_m3u8_rejected_by_extension(self):
        p = self._make("list.m3u8", "#EXTM3U\n#EXTINF:1,\nfile:C:/Windows/win.ini\n")
        out = tools_media.media_probe(path=p)
        self.assertTrue(out.startswith("ERROR"), out[:120])
        self.assertIn("รายการเล่น", out)

    def test_ffconcat_rejected_by_extension(self):
        p = self._make("list.ffconcat", "ffconcat version 1.0\nfile 'x.ts'\n")
        out = tools_media.media_probe(path=p)
        self.assertTrue(out.startswith("ERROR"), out[:120])

    def test_playlist_header_rejected_despite_media_extension(self):
        # นามสกุลปลอมเป็น .mp4 แต่เนื้อในเป็น playlist — ต้องดักที่หัวไฟล์
        p = self._make("fake.mp4", "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:1,\nfile:secret.ts\n")
        out = tools_media.media_probe(path=p)
        self.assertTrue(out.startswith("ERROR"), out[:160])
        self.assertIn("playlist", out.lower())

    def test_real_media_extension_not_rejected_by_indirection(self):
        # ไฟล์ .mp4 ที่ขึ้นต้นด้วยไบต์ไบนารี (มี NUL) ต้องไม่ถูกตีเป็น playlist
        d = C.new_dir("f2ok")
        p = os.path.join(d, "clip.mp4")
        with open(p, "wb") as fh:
            fh.write(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00")
        try:
            tools_media._reject_indirection(p)
        except ValueError:
            self.fail("ไฟล์สื่อจริงไม่ควรถูกปฏิเสธว่าเป็น playlist")


class R1LogBlockScopeTests(unittest.TestCase):
    """บล็อกบันทึกรวมของสแตก ต้องไม่ลามไปบล็อก .log ของผู้ใช้ในโปรเจกต์ตัวเอง"""

    def test_own_project_log_attachment_readable(self):
        d = os.path.join(C.PROJECT_DATA, "r1proj", "attachments")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "charger-ocpp.log")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("R1-OWN-LOG-MARKER")
        with guard.project_scope("r1proj"):
            out = tools_files.read_file(p)
        self.assertIn("R1-OWN-LOG-MARKER", out)
        # รูปเดียวกันกับ path จริงใต้ C:\LLM\projects\data ก็ต้องไม่ถูกบล็อกด้วยรายการของสแตก
        self.assertIsNone(guard._blocked(r"C:\LLM\projects\data\p1\attachments\x.log", guard._load_config()))

    def test_stack_code_still_uses_its_own_state_file(self):
        # scheduler อ่าน/เขียน scheduler_state.json ผ่าน guard ด้วย path คงที่ในโค้ด ถ้าด่านบล็อก
        # สถานะ (รวม pid ของ runner) จะกลายเป็นค่าว่างเงียบๆ — internal() ต้องผ่าน เครื่องมือต้องไม่ผ่าน
        p = r"C:\LLM\mcp-local\scheduler_state.json"
        with guard.project_scope("project1"):
            with self.assertRaises(guard.Denied):
                guard.check_read(p)
        with guard.internal():
            self.assertTrue(guard.check_read(p))
            self.assertTrue(guard.check_write(p + ".tmp"))       # ตรวจอย่างเดียว ไม่ได้เขียนจริง
        sched = C.import_local("scheduler")
        if os.path.exists(p):
            self.assertTrue(sched._load_state().get("jobs"), "scheduler อ่านสถานะของตัวเองไม่ได้")

    def test_cross_project_task_registry_and_logs_denied(self):
        with guard.project_scope("project1"):
            for p in (r"C:\LLM\mcp-local\tasks.json", r"C:\LLM\mcp-local\tasklogs\abcd.log",
                      r"C:\LLM\mcp-local\scheduler_state.json", r"C:\LLM\mcp-local\audit.log.1"):
                with self.assertRaises(guard.Denied, msg=p):
                    guard.check_read(p)


class LegacyTaskVisibilityTests(unittest.TestCase):
    """งานรุ่นเก่าที่ไม่มีฟิลด์ project เคยมองเห็นได้จากทุกโปรเจกต์ (S04) — ตอนนี้เป็นของ default เท่านั้น"""

    def test_legacy_task_only_visible_to_default(self):
        legacy = {"id": "old1", "command": "x"}
        with guard.project_scope("project1"):
            self.assertFalse(tools_tasks._visible(legacy))
            self.assertTrue(tools_tasks._visible({"id": "n1", "project": "project1"}))
            self.assertFalse(tools_tasks._visible({"id": "n2", "project": "ocpp-research"}))
        with guard.project_scope("default"):
            self.assertTrue(tools_tasks._visible(legacy))


class R2DosWildcardTests(unittest.TestCase):
    """cmd ขยาย wildcard ด้วยกติกา DOS — ด่านต้องเห็นผลเดียวกับที่ cmd เห็น (FindFirstFileW)"""

    def setUp(self):
        self.d = C.new_dir("r2dos")
        with open(os.path.join(self.d, "sample_key.txt"), "w", encoding="utf-8") as fh:
            fh.write("R2-DOSQ-MARKER")
        with open(os.path.join(self.d, "[a]b_key.txt"), "w", encoding="utf-8") as fh:
            fh.write("R2-BRACKET-MARKER")
        with open(os.path.join(self.d, "readme.txt"), "w", encoding="utf-8") as fh:
            fh.write("R2-OK")

    def test_dos_question_mark_zero_width(self):
        for pat in ("sample_key??.txt", "sample_ke?????.txt"):
            with self.assertRaises(guard.Denied, msg=pat):
                guard.check_glob(os.path.join(self.d, pat))
            out = tools_files.exec_shell_command("type " + pat, cwd=self.d)
            self.assertNotIn("R2-DOSQ-MARKER", out, pat)

    def test_brackets_are_literal_for_cmd(self):
        with self.assertRaises(guard.Denied):
            guard.check_glob(os.path.join(self.d, "[a]b*"))
        out = tools_files.exec_shell_command("type [a]b*", cwd=self.d)
        self.assertNotIn("R2-BRACKET-MARKER", out)

    def test_normal_wildcard_still_works(self):
        out = tools_files.exec_shell_command("type read*.txt", cwd=self.d)
        self.assertIn("R2-OK", out)


@unittest.skipUnless(shutil.which("git"), "ไม่มี git ในเครื่อง")
class R3GitContentTests(unittest.TestCase):
    """repo จำลองที่ commit .env/credentials.json ไว้ — ทุกรูปที่รันทันทีต้องไม่พิมพ์เนื้อไฟล์ต้องห้าม"""

    MARKS = ("R3-ENV-7710", "R3-CRED-7711", "R3-ENV-7712")

    @classmethod
    def setUpClass(cls):
        cls.repo = C.new_dir("r3repo")
        env = C.clean_env()
        subprocess.run(["git", "init", "-q", cls.repo], check=True, env=env)
        with open(os.path.join(cls.repo, ".env"), "w", encoding="utf-8") as fh:
            fh.write("API_KEY=%s\n" % cls.MARKS[0])
        with open(os.path.join(cls.repo, "credentials.json"), "w", encoding="utf-8") as fh:
            fh.write('{"x":"%s"}\n' % cls.MARKS[1])
        with open(os.path.join(cls.repo, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("R3-README\n")
        subprocess.run(["git", "-C", cls.repo, "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", cls.repo, "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-q", "-m", "init"], check=True, env=env)
        with open(os.path.join(cls.repo, ".env"), "a", encoding="utf-8") as fh:
            fh.write("SECOND=%s\n" % cls.MARKS[2])
        cls.blob = subprocess.run(["git", "-C", cls.repo, "rev-parse", "HEAD:.env"], env=env,
                                  capture_output=True, text=True).stdout.strip()

    def _run(self, cmd):
        return tools_files.exec_shell_command(cmd, cwd=self.repo)

    def test_content_forms_do_not_auto_run(self):
        for cmd in ("git show", "git show HEAD", "git log -p", "git diff", "git diff HEAD",
                    "git status -v", "git show " + self.blob, "git stash show -p",
                    "git log -S API_KEY --name-only", "git log -G KEY", "git whatchanged -p",
                    "git log --cc", "git log -m", "git log --word-diff"):
            out = self._run(cmd)
            for m in self.MARKS:
                self.assertNotIn(m, out, cmd)
            self.assertFalse(tools_files._is_readonly(cmd), cmd)

    def test_blocked_revpath_forms_denied_even_confirmed(self):
        for cmd in ("git show :0:credentials.json", "git show :credentials.json",
                    "git log -L1,1:.env", "git log -L 1,1:.env", "git show HEAD@{0}:.env",
                    "git cat-file -p :0:.env"):
            self.assertIsNotNone(guard.git_revpath_violation(tools_files._argv(cmd)), cmd)
            out = self._run(cmd)
            self.assertTrue(out.startswith("ปฏิเสธ"), "%s -> %s" % (cmd, out[:120]))

    def test_safe_forms_still_auto_run(self):
        for cmd in ("git status", "git log --oneline", "git show --stat", "git diff --stat",
                    "git show HEAD:README.md", "git log --stat -3", "git show --name-only HEAD",
                    "git status -s", "git branch --list", "git ls-files"):
            self.assertTrue(tools_files._is_readonly(cmd), cmd)
            out = self._run(cmd)
            for m in self.MARKS:
                self.assertNotIn(m, out, cmd)
        self.assertIn("R3-README", self._run("git show HEAD:README.md"))

    def test_hex_rev_with_stat_needs_confirmation(self):
        # git show --stat <blob-id> ยังพิมพ์เนื้อ blob ออกมา เลขฐานสิบหกล้วนจึงต้องยืนยัน
        self.assertFalse(tools_files._is_readonly("git show --stat " + self.blob))


class R4ListingTests(unittest.TestCase):
    """รายการชื่อไฟล์แบบลึก: รูปที่กรองได้แน่นอน (path เต็มทุกบรรทัด) รันทันที รูปที่กรองไม่ได้ต้องยืนยัน"""

    def setUp(self):
        self.d = C.new_dir("r4list")
        os.makedirs(os.path.join(self.d, ".ssh"), exist_ok=True)
        with open(os.path.join(self.d, ".ssh", "id_rsa"), "w", encoding="utf-8") as fh:
            fh.write("x")
        with open(os.path.join(self.d, "gw_key.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")

    def test_dir_s_without_bare_and_tree_need_confirmation(self):
        for cmd in ("dir /s", "dir /s %s" % self.d, "dir /a /s", "tree", "tree /f %s" % self.d):
            self.assertFalse(tools_files._is_readonly(cmd), cmd)
            out = tools_files.exec_shell_command(cmd, cwd=self.d)
            self.assertNotIn("id_rsa", out, cmd)
        for cmd in ("dir /s /b", "dir /s/b", "dir /b /s /a"):
            self.assertTrue(tools_files._is_readonly(cmd), cmd)

    def test_plain_where_output_is_filtered(self):
        out = tools_files.exec_shell_command("where %s:*.txt" % self.d, cwd=self.d)
        self.assertNotIn("gw_key.txt", out, out[:200])


class R5DevicePathTests(unittest.TestCase):
    def test_device_namespace_forms(self):
        for p in (r"\\?\Volume{0b1c2d3e-0000-0000-0000-000000000000}\LLM\x.txt",
                  r"\\?\GLOBALROOT\Device\HarddiskVolume3\LLM\x.txt", r"\\.\pipe\foo"):
            with self.assertRaises(guard.Denied, msg=p):
                guard.check_read(p)
        with self.assertRaises(guard.Denied):
            guard.check_write(r"\\.\C:\LLM\mcp-local\guard.py")
        self.assertIsNotNone(guard.write_protected_hit(r"\\.\C:\LLM\projects\hub.py"))
        self.assertEqual(guard._norm(r"\\.\C:\LLM\mcp-local\guard.py"),
                         guard._norm(r"C:\LLM\mcp-local\guard.py"))


class R6MediaProtocolTests(unittest.TestCase):
    def test_protocol_whitelist_added_when_supported(self):
        ff = sys.executable                 # ไฟล์ที่มีอยู่จริง แค่ใช้เป็นกุญแจ cache
        saved_run, saved_cache = tools_media._run, dict(tools_media._PW_CACHE)
        tools_media._PW_CACHE.clear()
        tools_media._run = lambda argv: (0, "", "")
        try:
            base = tools_media._base(ff)
        finally:
            tools_media._run = saved_run
            tools_media._PW_CACHE.clear()
            tools_media._PW_CACHE.update(saved_cache)
        i = base.index("-protocol_whitelist")
        self.assertEqual(base[i + 1], "file")

    def test_old_ffmpeg_without_option_still_works(self):
        ff = sys.executable
        saved_run, saved_cache = tools_media._run, dict(tools_media._PW_CACHE)
        tools_media._PW_CACHE.clear()
        tools_media._run = lambda argv: (1, "", "Unrecognized option 'protocol_whitelist'")
        try:
            base = tools_media._base(ff)
        finally:
            tools_media._run = saved_run
            tools_media._PW_CACHE.clear()
            tools_media._PW_CACHE.update(saved_cache)
        self.assertNotIn("-protocol_whitelist", base)

    def test_manifests_rejected(self):
        d = C.new_dir("r6media")
        for name, content in (("a.mpd", "<MPD></MPD>"), ("b.sdp", "v=0\no=- 0 0 IN IP4 10.0.0.1\n"),
                              ("fake.mp4", '<?xml version="1.0"?>\n<MPD>'),
                              ("fake2.mkv", "v=0\nc=IN IP4 239.1.1.1\n")):
            p = os.path.join(d, name)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(content)
            with self.assertRaises(ValueError, msg=name):
                tools_media._reject_indirection(p)


class R7ConfirmChannelUnitTests(unittest.TestCase):
    """ขั้นยืนยันต้องผ่าน local_confirm (เรียกผ่าน server.handle_rpc ในโปรเซสเดียว)"""

    @classmethod
    def setUpClass(cls):
        server.load_modules()

    def _call(self, project, name, args, fast=True):
        reply = server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": name, "arguments": args}}, project, fast)
        return reply["result"]["content"][0]["text"]

    def test_consume_outside_channel_fails_and_keeps_token(self):
        tok = guard.need_confirm("exec", "r7")
        self.assertFalse(guard.consume_confirm(tok, "exec", "r7"))      # ไม่ได้มาทาง local_confirm
        with guard.confirming(tok, guard.pending_review(tok)):
            self.assertTrue(guard.consume_confirm(tok, "exec", "r7"))   # token ยังไม่ถูกเผา

    def test_local_confirm_replays_recorded_call(self):
        d = C.new_dir("r7rep")
        p = os.path.join(d, "a.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("one")
        hint = self._call("r7proj", "local_do", {"action": "edit", "path": p, "old": "one", "new": "two"})
        tok = C.token_from_hint(hint)
        self.assertIn("local_confirm", hint)
        out = self._call("r7proj", "local_do", {"action": "edit", "path": p, "old": "one",
                                                 "new": "two", "confirm_token": tok})
        self.assertEqual(_read(p), "one", out[:160])
        # รอบ review-fetch (S2): review ไม่บังคับ แต่ถ้าส่งมาต้องตรง (ไม่ตรง = ไม่ทำและไม่เผา token)
        out = self._call("r7proj", guard.CONFIRM_TOOL, {"confirm_token": tok, "review": "ไม่ใช่ข้อความตรวจทาน"})
        self.assertEqual(_read(p), "one", out[:160])
        # รอบ FIXER ของ S1/S2: token อย่างเดียวรันได้เฉพาะหลังกล่องอนุญาตดึง review ไปแสดง (GET /review จากหน้าเว็บ)
        out = self._call("r7proj", guard.CONFIRM_TOOL, {"confirm_token": tok, "new": "EVIL"})
        self.assertEqual(_read(p), "one", out[:160])
        self.assertEqual(server.review_lookup("r7proj", "token=" + tok, viewer=True)[0], 200)
        # เล่นซ้ำของที่บันทึกไว้ตอนขอ — อาร์กิวเมนต์ที่ส่งมากับ local_confirm ไม่มีผล
        out = self._call("r7proj", guard.CONFIRM_TOOL, {"confirm_token": tok, "new": "EVIL"})
        self.assertEqual(_read(p), "two", out[:160])
        out = self._call("r7proj", guard.CONFIRM_TOOL, C.confirm_args(hint))
        self.assertIn("ใช้ไม่ได้", out)                                  # ใช้ได้ครั้งเดียว

    def test_served_schemas_have_confirm_tool_and_no_token_param(self):
        for fast in (True, False):
            reply = server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                      "default", fast)
            tools = {t["name"]: t for t in reply["result"]["tools"]}
            self.assertIn(guard.CONFIRM_TOOL, tools)
            for name, t in tools.items():
                if name != guard.CONFIRM_TOOL:
                    self.assertNotIn("confirm_token", t["inputSchema"].get("properties", {}), name)
            self.assertIn("local_confirm", tools[list(tools)[0]]["description"])


class R8OriginBindingUnitTests(unittest.TestCase):
    def test_mapping_and_mismatch(self):
        v = server.origin_scope_violation
        self.assertIsNone(v(None, "anything"))
        self.assertIsNone(v("http://127.0.0.1:8103", C.PROJECT_OF_ALLOWED_ORIGIN))
        self.assertEqual(v("http://127.0.0.1:8103", "proj-b"), "origin_project_mismatch")
        self.assertEqual(v("http://localhost:8150", "proj-b"), "origin_unknown_project")
        self.assertIsNone(v("http://127.0.0.1:8100", "proj-b"))
        self.assertIsNone(v("http://127.0.0.1:8099", "proj-b"))

    def test_corrupt_projects_file_keeps_last_good_map(self):
        server._project_ports()                      # โหลดผังที่ถูกต้องไว้ก่อน
        with open(C.PROJECTS_JSON, encoding="utf-8") as fh:
            good = fh.read()
        try:
            with open(C.PROJECTS_JSON, "w", encoding="utf-8") as fh:
                fh.write('[{"slug": "sec-http", "po')        # จำลอง hub เขียนไฟล์ไม่จบ
            self.assertIsNone(server.origin_scope_violation("http://127.0.0.1:8103",
                                                            C.PROJECT_OF_ALLOWED_ORIGIN))
        finally:
            with open(C.PROJECTS_JSON, "w", encoding="utf-8") as fh:
                fh.write(good)
        json.loads(good)


if __name__ == "__main__":
    unittest.main()
