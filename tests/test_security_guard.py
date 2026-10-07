# -*- coding: utf-8 -*-
"""เทสต์ถดถอยของ guard/เครื่องมือไฟล์/คำสั่ง shell (ช่องโหว่ V2 V3 V4 V6 V7 + การผูก confirm_token)

ทุกเทสต์ในไฟล์นี้ "ล้ม" กับโค้ดก่อนแก้ (ดูวิธีรันกับ backup ใน test_security_common.py)
และ "ผ่าน" กับโค้ดปัจจุบัน เรียกฟังก์ชันตรงๆ ในโปรเซสเดียว ไม่เปิดพอร์ตใดๆ
ทุกไฟล์ที่เทสต์สร้างอยู่ในโฟลเดอร์ชั่วคราว — path จริงของระบบถูกใช้แค่กับฟังก์ชันตรวจ (ไม่เขียนจริง)
"""
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

guard = C.import_local("guard")
tools_files = C.import_local("tools_files")
tools_fast = C.import_local("tools_fast")
server = C.import_local("server")

HOME = os.path.expanduser("~")


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


class V2ConfigMergeTests(unittest.TestCase):
    """V2: config.json เคยแทนที่ค่าเริ่มต้นทั้งก้อน และเครื่องมือสร้างไฟล์นั้นได้เอง"""

    def test_user_config_cannot_remove_builtin_blocks(self):
        d = C.new_dir("cfg")
        cfg = os.path.join(d, "config.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"blocked_globs": [], "blocked_suffixes": [], "write_protected": [],
                       "allowed_roots": [{"path": "C:\\", "mode": "read_write"}]}, fh)
        from pathlib import Path
        saved = guard.CONFIG_PATH
        guard.CONFIG_PATH = Path(cfg)
        try:
            with self.assertRaises(guard.Denied):
                guard.check_read(os.path.join(HOME, ".ssh", "id_rsa"))
            with self.assertRaises(guard.Denied):
                guard.check_write(r"C:\LLM\mcp-local\guard.py")
        finally:
            guard.CONFIG_PATH = saved

    def test_guard_config_is_write_protected(self):
        for p in (r"C:\LLM\mcp-local\config.json", r"C:\LLM\mcp-websearch\config.json"):
            with self.assertRaises(guard.Denied, msg=p):
                guard.check_write(p)

    def test_write_file_cannot_create_guard_config(self):
        target = r"C:\LLM\mcp-local\config.json"
        if os.path.exists(target):
            self.skipTest("มี config.json อยู่แล้ว (ผู้ใช้สร้างเอง) จึงไม่ทดสอบทับ")
        # ตรวจเงื่อนไขปลอดภัยก่อนเสมอ: ถ้าโค้ดยังมีช่องโหว่ เทสต์ล้มตรงนี้ก่อนจะเขียนไฟล์จริง
        with self.assertRaises(guard.Denied):
            guard.check_write(target)
        out = tools_files.write_file(target, '{"blocked_globs": []}')
        self.assertTrue(out.startswith("ปฏิเสธ"), out)
        self.assertFalse(os.path.exists(target))


class V3EditAndPersistenceTests(unittest.TestCase):
    """V3: edit_file ไม่เคยขอยืนยัน, ไฟล์ใหม่ที่ไหนก็ได้ไม่ต้องยืนยัน (Startup, profile, .git/hooks)"""

    def test_edit_file_requires_confirmation(self):
        d = C.new_dir("edit")
        p = os.path.join(d, "a.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("hello world")
        out = tools_files.edit_file(p, "hello", "bye")
        self.assertIn("confirm_token", out)
        self.assertEqual(_read(p), "hello world")

    def test_edit_token_is_bound_to_arguments(self):
        d = C.new_dir("edit2")
        p = os.path.join(d, "a.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("hello world")
        tok = C.token_from_hint(tools_files.edit_file(p, "hello", "bye"))
        self.assertTrue(tok)
        # ใช้ token เดียวกันกับการแก้คนละแบบ -> ต้องไม่ผ่าน และไฟล์ต้องไม่เปลี่ยน
        with C.confirming(guard, tok):
            out = tools_files.edit_file(p, "hello", "EVIL", confirm_token=tok)
        self.assertNotIn("แก้ไขแล้ว", out)
        self.assertEqual(_read(p), "hello world")
        with C.confirming(guard, tok):
            out = tools_files.edit_file(p, "hello", "bye", confirm_token=tok)
        self.assertIn("แก้ไขแล้ว", out)
        self.assertEqual(_read(p), "bye world")
        # ใช้ซ้ำไม่ได้
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("hello world")
        with C.confirming(guard, tok):
            out = tools_files.edit_file(p, "hello", "bye", confirm_token=tok)
        self.assertNotIn("แก้ไขแล้ว", out)

    def test_fast_edit_requires_confirmation(self):
        d = C.new_dir("fastedit")
        p = os.path.join(d, "a.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("x = 1")
        out = tools_fast.local_do(action="edit", project="p", path=p, old="x = 1", new="x = 2")
        self.assertIn("confirm_token", out)
        self.assertEqual(_read(p), "x = 1")
        tok = C.token_from_hint(out)
        with C.confirming(guard, tok):
            out = tools_fast.local_do(action="edit", project="p", path=p, old="x = 1", new="x = 2",
                                      confirm_token=tok)
        self.assertEqual(_read(p), "x = 2", out)

    def test_protected_targets_denied_even_with_token(self):
        appdata = os.environ.get("APPDATA") or os.path.join(HOME, "AppData", "Roaming")
        targets = [
            r"C:\LLM\mcp-local\guard.py", r"C:\LLM\mcp-local\tools_files.py",
            r"C:\LLM\mcp-local\new_module.py", r"C:\LLM\mcp-websearch\server.py",
            r"C:\LLM\projects\hub.py", r"C:\LLM\projects\projects.json",
            r"C:\LLM\projects\static\boot.js", r"C:\LLM\projects\tools\shot.py",
            r"C:\LLM\start-qwen38.ps1", r"C:\LLM\Qwen38.cmd", r"C:\LLM\models-preset.ini",
            r"C:\LLM\secrets_util.py", r"C:\LLM\secrets\x.txt", r"C:\LLM\tests\test_x.py",
            r"C:\LLM\llama.cpp-b10984\llama-server.exe",
            os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup\evil.bat"),
            os.path.join(HOME, r"Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"),
            os.path.join(HOME, r"Documents\PowerShell\profile.ps1"),
            os.path.join(C.TMP, r"repo\.git\hooks\pre-commit"),
            os.path.join(C.TMP, r"repo\.git\config"),
            os.path.join(HOME, ".bashrc"), os.path.join(HOME, ".gitconfig"),
            os.path.join(HOME, r".claude\settings.json"),
        ]
        for t in targets:
            with self.assertRaises(guard.Denied, msg=t):
                guard.check_write(t)
        # ผ่าน write_file พร้อม token ปลอมก็ต้องปฏิเสธ (ไม่ใช่ขอ token)
        out = tools_files.write_file(os.path.join(C.TMP, r"repo2\.git\hooks\post-checkout"),
                                     "calc", confirm_token="deadbeef")
        self.assertTrue(out.startswith("ปฏิเสธ"), out)

    def test_normal_user_file_still_writable(self):
        d = C.new_dir("normal")
        self.assertTrue(guard.check_write(os.path.join(d, "notes.txt")))
        p = os.path.join(C.TMP, "projects-under-llm-like", "sub", "x.py")
        # .py ใต้โฟลเดอร์ย่อยทั่วไปไม่ใช่เขตห้ามเขียน (* ไม่ข้าม \) แค่ต้องยืนยันเพราะเป็นสคริปต์
        self.assertTrue(guard.check_write(p))
        out = tools_files.write_file(os.path.join(d, "notes.txt"), "hi")
        self.assertIn("เขียนแล้ว", out)

    def test_new_script_file_requires_confirmation(self):
        d = C.new_dir("script")
        for name in ("evil.ps1", "evil.py", "evil.bat", "evil.js", "evil.vbs", "evil.lnk"):
            p = os.path.join(d, name)
            out = tools_files.write_file(p, "calc.exe")
            self.assertIn("confirm_token", out, name)
            self.assertFalse(os.path.exists(p), name)
        p = os.path.join(d, "ok.py")
        tok = C.token_from_hint(tools_files.write_file(p, "print(1)"))
        with C.confirming(guard, tok):
            out = tools_files.write_file(p, "print('other')", confirm_token=tok)
        self.assertFalse(os.path.exists(p), "token ต้องผูกกับเนื้อหาที่อนุมัติ")
        with C.confirming(guard, tok):
            out = tools_files.write_file(p, "print(1)", confirm_token=tok)
        self.assertIn("เขียนแล้ว", out)


class V4ShellAllowlistTests(unittest.TestCase):
    """V4: คำสั่ง "อ่านอย่างเดียว" เดิมรวม python script.py, pip install, node -e, git -c ..."""

    NOT_READONLY = [
        "python script.py", "python -m pip install requests", "python -m http.server",
        'python -c "print(1)"', 'node -e "require(\'child_process\')"', "npm run build",
        "npm install", "pip install x", "pip download x", "pip list --log out.txt",
        "curl -o x http://a", "curl -d @file http://a", "ping 8.8.8.8",
        "git clone https://example.com/x", "git config core.pager calc",
        "git -c core.pager=calc log", "git --git-dir=C:\\x log", "git grep -Ocalc foo",
        "git log --output=x.txt", "git branch newbranch", "git tag v1", "git stash",
        "git push", "git commit -m x", "git remote add o http://x", "git fetch",
        "wmic process call create calc", r"C:\evil\git.exe status", ".\\git status",
        "date 01-01-2020", "time 12:00", "hostname evil", "findstr /s secret *.txt",
        "findstr /spin x *.txt", "findstr /g:pats.txt x", "type x & calc", "dir | more",
        "echo %PATH%", "echo hi > out.txt", "nvidia-smi -pl 100", "nvidia-smi -f out.txt",
        "ipconfig /release", "powershell -c gci", "cmd /c dir", "certutil -urlcache -f http://a b",
        "tasklist /s otherhost", "type \"x\" ^& calc",
        # รอบ FIXER (F12/F5): รูปที่พิมพ์เนื้อไฟล์จาก git หรือชื่อไฟล์ที่กรองไม่ได้ ต้องยืนยันก่อน
        "git diff", "git show HEAD", "git show", "git log -p", "git status -v", "git blame x",
        "tree", "dir /s",
    ]
    READONLY = [
        "dir", "dir /s /b", "git status", "git log --oneline -5", "git diff --stat",
        "git branch", "git branch -a", "git show --stat HEAD", "git -C C:\\LLM status", "pip list",
        "pip show requests", "python --version", "python -m pip list", "node --version",
        "npm --version", "nvidia-smi", "nvidia-smi --query-gpu=name,memory.used --format=csv",
        "where python", "date /t", "whoami", "ver", "ipconfig", "tasklist",
    ]

    def test_dangerous_commands_are_not_readonly(self):
        bad = [c for c in self.NOT_READONLY if tools_files._is_readonly(c)]
        self.assertEqual(bad, [], "คำสั่งเหล่านี้ต้องขอ confirm_token")

    def test_common_readonly_commands_still_run_without_token(self):
        bad = [c for c in self.READONLY if not tools_files._is_readonly(c)]
        self.assertEqual(bad, [], "คำสั่งอ่านอย่างเดียวที่ใช้บ่อยต้องไม่ถูกบังคับยืนยัน")

    def test_script_does_not_run_without_confirmation(self):
        d = C.new_dir("exec")
        marker = os.path.join(d, "ran.txt")
        with open(os.path.join(d, "payload.py"), "w", encoding="utf-8") as fh:
            fh.write("open(r'%s','w').write('x')\n" % marker)
        out = tools_files.exec_shell_command("python payload.py", cwd=d)
        self.assertIn("confirm_token", out)
        time.sleep(0.3)
        self.assertFalse(os.path.exists(marker), "สคริปต์ต้องไม่ถูกรันก่อนผู้ใช้อนุมัติ")

    def test_wildcard_cannot_reach_blocked_file(self):
        d = C.new_dir("glob")
        os.makedirs(os.path.join(d, ".ssh"))
        with open(os.path.join(d, ".ssh", "id_rsa"), "w", encoding="utf-8") as fh:
            fh.write("FAKE-PRIVATE-KEY-5521")
        out = tools_files.exec_shell_command("type %s" % os.path.join(d, ".s*", "id_rsa"), cwd=d)
        self.assertNotIn("FAKE-PRIVATE-KEY-5521", out)

    def test_alternate_data_stream_cannot_bypass_suffix_block(self):
        d = C.new_dir("ads")
        key = os.path.join(d, "server.pem")
        with open(key, "w", encoding="utf-8") as fh:
            fh.write("FAKE-PEM-CONTENT-8812")
        for path in (key + "::$DATA", key + ":$DATA"):
            self.assertNotIn("FAKE-PEM-CONTENT-8812", tools_files.read_file(path), path)
        out = tools_files.exec_shell_command("type server.pem::$DATA", cwd=d)
        self.assertNotIn("FAKE-PEM-CONTENT-8812", out)
        # git rev:path ยังต้องใช้ได้ตามปกติ (ไม่ถูกตีความเป็น ADS จนโดนปฏิเสธ)
        self.assertTrue(tools_files._is_readonly("git show HEAD:README.md"))
        self.assertIsNone(tools_files._path_of("HEAD:README.md", d))

    def test_urls_in_confirmed_commands_are_not_paths(self):
        d = C.new_dir("url")
        self.assertIsNone(tools_files._path_of("https://example.com/a/b", d))
        out = tools_files.exec_shell_command("curl https://example.com/x", cwd=d)
        self.assertIn("confirm_token", out)

    @unittest.skipIf(C.OLD_CODE_MODE, "โค้ดเก่าจะรัน type กับไฟล์ token จริง — ห้ามรันในโหมดเทียบโค้ดเก่า")
    def test_secret_folder_never_in_command(self):
        for cmd in (r"type C:\LLM\secrets\local-services.token",
                    "dir C:/LLM/secrets", r"findstr x C:\LLM\secrets\*"):
            out = tools_files.exec_shell_command(cmd, confirm_token="")
            # ข้อความ assert ห้ามมีผลลัพธ์ของคำสั่ง (ถ้าพลาดขึ้นมา จะกลายเป็นช่องที่ token หลุดลง log เทสต์)
            self.assertTrue(out.startswith("ปฏิเสธ"), cmd)

    def test_mutating_command_cannot_touch_stack_code(self):
        for cmd, cwd in ((r"copy nul C:\LLM\mcp-local\guard.py", ""),
                         ('python -c "open(\'guard.py\',\'w\')"', r"C:\LLM\mcp-local"),
                         ('python -c "import os"', r"C:\LLM")):
            out = tools_files.exec_shell_command(cmd, cwd=cwd)
            self.assertTrue(out.startswith("ปฏิเสธ"), "%s -> %s" % (cmd, out[:160]))

    def test_task_start_token_bound_to_command(self):
        """เดิม consume_confirm(token, "task_start") ไม่ดูว่าคำสั่งอะไร: อนุมัติ A แล้วเอา token ไปรัน B ได้"""
        tools_tasks = C.import_local("tools_tasks")
        d = C.new_dir("task")
        marker = os.path.join(d, "b-ran.txt")
        with open(os.path.join(d, "b.py"), "w", encoding="utf-8") as fh:
            fh.write("open(r'%s','w').write('x')\n" % marker)
        hint = tools_tasks.task_start(command="python --version", cwd=d)
        tok = C.token_from_hint(hint)
        self.assertTrue(tok, hint[:200])
        with C.confirming(guard, tok):
            out = tools_tasks.task_start(command="python b.py", cwd=d, confirm_token=tok)
        time.sleep(1.5)
        self.assertFalse(os.path.exists(marker), "token ของคำสั่ง A ต้องใช้เริ่มคำสั่ง B ไม่ได้")
        self.assertNotIn("เริ่มงานเบื้องหลังแล้ว", out)

    @unittest.skipIf(C.OLD_CODE_MODE, "โค้ดเก่าจะขอ token แทนการปฏิเสธ (ไม่มีอะไรรัน) — ทดสอบเฉพาะโค้ดใหม่")
    def test_task_start_denies_stack_and_secrets(self):
        tools_tasks = C.import_local("tools_tasks")
        for cmd, cwd in (('python -c "print(1)"', r"C:\LLM\mcp-local"),
                         (r"cmd /c type C:\LLM\secrets\local-services.token", ""),
                         (r"python C:\LLM\gpu_profile.py", "")):
            out = tools_tasks.task_start(command=cmd, cwd=cwd)
            self.assertIn("ปฏิเสธ", out, cmd)
            self.assertNotIn("confirm_token", out, cmd)

    def test_readonly_git_runs_with_hardened_env(self):
        env = tools_files._child_env(True)
        self.assertEqual(env.get("NoDefaultCurrentDirectoryInExePath"), "1")
        pairs = {env.get("GIT_CONFIG_KEY_%d" % i): env.get("GIT_CONFIG_VALUE_%d" % i)
                 for i in range(int(env.get("GIT_CONFIG_COUNT", "0")))}
        self.assertEqual(pairs.get("core.fsmonitor"), "false")
        self.assertEqual(pairs.get("safe.bareRepository"), "explicit")
        # รอบ FIXER: git stash show / git log ที่รันทันทีต้องไม่พิมพ์ patch หรือเรียก gpg จาก config ของ repo
        if hasattr(tools_files, "_git_view_args"):
            self.assertEqual(pairs.get("stash.showPatch"), "false")
            self.assertEqual(pairs.get("log.showSignature"), "false")


class V6ProjectIsolationTests(unittest.TestCase):
    """V6: เครื่องมือไฟล์ของโปรเจกต์หนึ่งอ่านความจำ/ไฟล์แนบของอีกโปรเจกต์ได้"""

    @classmethod
    def setUpClass(cls):
        server.load_modules()
        cls.alpha = os.path.join(C.PROJECT_DATA, "alpha-v6")
        cls.beta = os.path.join(C.PROJECT_DATA, "beta-v6")
        for d in (cls.alpha, cls.beta, os.path.join(cls.alpha, "attachments")):
            os.makedirs(d, exist_ok=True)
        with open(os.path.join(cls.alpha, "memory.json"), "w", encoding="utf-8") as fh:
            fh.write('{"entries": [{"text": "ALPHA-ONLY-NOTE-9931"}]}')
        with open(os.path.join(cls.alpha, "attachments", "doc.txt"), "w", encoding="utf-8") as fh:
            fh.write("ALPHA-ATTACHMENT-4410")

    def _call(self, project, name, args, fast=False):
        reply = server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": name, "arguments": args}}, project, fast)
        return reply["result"]["content"][0]["text"]

    def test_other_project_memory_not_readable(self):
        out = self._call("beta-v6", "read_file", {"path": os.path.join(self.alpha, "memory.json")})
        self.assertNotIn("ALPHA-ONLY-NOTE-9931", out)
        out = self._call("beta-v6", "read_file",
                         {"path": os.path.join(self.alpha, "attachments", "doc.txt")})
        self.assertNotIn("ALPHA-ATTACHMENT-4410", out)

    def test_other_project_not_visible_via_grep_list_or_fast(self):
        out = self._call("beta-v6", "grep_search", {"pattern": "ALPHA-", "path": C.PROJECT_DATA})
        self.assertNotIn("ALPHA-ONLY-NOTE-9931", out)
        self.assertNotIn("ALPHA-ATTACHMENT-4410", out)
        out = self._call("beta-v6", "list_dir", {"path": C.PROJECT_DATA})
        self.assertNotIn("alpha-v6", out)
        out = self._call("beta-v6", "local_read",
                         {"action": "read", "path": os.path.join(self.alpha, "memory.json")},
                         fast=True)
        self.assertNotIn("ALPHA-ONLY-NOTE-9931", out)

    def test_own_project_still_readable(self):
        out = self._call("alpha-v6", "read_file", {"path": os.path.join(self.alpha, "memory.json")})
        self.assertIn("ALPHA-ONLY-NOTE-9931", out)

    def test_confirm_token_not_usable_from_other_project(self):
        d = C.new_dir("xproj")
        p = os.path.join(d, "a.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("one")
        hint = self._call("alpha-v6", "edit_file",
                          {"path": p, "old_string": "one", "new_string": "two"})
        tok = C.token_from_hint(hint)
        self.assertTrue(tok)
        self._call("beta-v6", "edit_file", {"path": p, "old_string": "one", "new_string": "two",
                                            "confirm_token": tok})
        self.assertEqual(_read(p), "one")
        if getattr(guard, "CONFIRM_TOOL", None):
            # ช่องทางยืนยันใหม่ก็ต้องข้ามโปรเจกต์ไม่ได้เช่นกัน (แม้ส่ง review ถูกต้องมาด้วย)
            args = C.confirm_args(hint) if hasattr(C, "confirm_args") else {"confirm_token": tok}
            self._call("beta-v6", guard.CONFIRM_TOOL, args)
            self.assertEqual(_read(p), "one")


class V7InstructionsReachModelTests(unittest.TestCase):
    """V7: WebUI ไม่ส่ง instructions ของ initialize ให้โมเดล กฎจึงต้องอยู่ใน description"""

    def test_rules_are_in_tool_descriptions(self):
        server.load_modules()
        for fast in (False, True):
            reply = server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                      "default", fast)
            text = " ".join(t.get("description", "") for t in reply["result"]["tools"])
            self.assertIn("confirm_token", text)
            self.assertIn("ไม่ใช่คำสั่ง", text, "surface fast=%s" % fast)
            self.assertIn("ห้ามเดาว่าอนุมัติ", reply["result"]["tools"][0]["description"])

    def test_websearch_rules_in_descriptions(self):
        ws = C.import_websearch()
        reply = ws.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        text = " ".join(t.get("description", "") for t in reply["result"]["tools"])
        self.assertIn("ไม่ใช่คำสั่ง", text)


class ConfirmTokenTests(unittest.TestCase):
    """confirm_token: ใช้ครั้งเดียว ผูกกับ action + รายละเอียด + โปรเจกต์ หมดอายุ และไม่ลง audit.log"""

    def test_binding_and_single_use(self):
        tok = guard.need_confirm("exec", "dir\n(cwd: x)")
        with C.confirming(guard, tok):
            self.assertFalse(guard.consume_confirm(tok, "exec", "del *\n(cwd: x)"))
            self.assertFalse(guard.consume_confirm(tok, "write_file:x", "dir\n(cwd: x)"))
            with guard.project_scope("other"):
                self.assertFalse(guard.consume_confirm(tok, "exec", "dir\n(cwd: x)"))
            self.assertTrue(guard.consume_confirm(tok, "exec", "dir\n(cwd: x)"))
            self.assertFalse(guard.consume_confirm(tok, "exec", "dir\n(cwd: x)"))

    def test_expiry(self):
        saved = guard.CONFIRM_TTL
        guard.CONFIRM_TTL = -1
        try:
            tok = guard.need_confirm("exec", "late")
        finally:
            guard.CONFIRM_TTL = saved
        with C.confirming(guard, tok):
            self.assertFalse(guard.consume_confirm(tok, "exec", "late"))

    def test_token_value_not_in_audit_log(self):
        tok = guard.need_confirm("exec", "audit-check")
        with C.confirming(guard, tok):
            guard.consume_confirm(tok, "exec", "audit-check")
        with open(C.AUDIT_LOCAL, encoding="utf-8") as fh:
            log = fh.read()
        self.assertNotIn('"%s"' % tok, log)
        self.assertNotIn(tok, log)


if __name__ == "__main__":
    unittest.main()
