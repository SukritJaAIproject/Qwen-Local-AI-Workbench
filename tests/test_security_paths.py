# -*- coding: utf-8 -*-
"""
เทสต์รูปแบบ path แปลกๆ กับ guard ของ mcp-local (S05 + เขตห้ามเขียนของ C5) — ไม่เปิดไฟล์ต้องห้ามใดๆ

ทำไมต้องมี
  integrator ลองด้วยมือแล้วว่า 8.3 (SECRET~1), \\\\?\\, UNC (\\\\127.0.0.1\\c$), .. และ / ถูกปฏิเสธ แต่ไม่มีเทสต์
  อัตโนมัติ — ถ้า guard ถูกแก้วันหลัง (เช่นเลิก realpath) ช่องพวกนี้จะเปิดกลับมาโดยไม่มีอะไรล้ม

สิ่งที่ตรวจ (เรียกแค่ฟังก์ชันตรวจของ guard / ทางเข้าของเครื่องมือที่ต้องปฏิเสธก่อนแตะไฟล์)
  * อ่านไฟล์โทเคน/โฟลเดอร์ secrets ไม่ได้ทุกรูปแบบ: ตัวพิมพ์, /, 8.3, \\\\?\\, \\\\.\\, UNC, .., จุด/ช่องว่างท้ายชื่อ,
    junction ในโฟลเดอร์ชั่วคราวที่ชี้เข้า C:\\LLM\\secrets
  * เขียนโค้ดของสแตกไม่ได้ทุกรูปแบบเดียวกัน (check_write) และ is_write_protected เห็นรูปที่คลายได้
    (8.3, /, .., จุดท้าย, junction) — \\\\?\\ กับ UNC ถูกปฏิเสธด้วย check_write (อยู่นอก allowed roots)
  * คำสั่งที่เปลี่ยนเครื่องห้ามใช้โฟลเดอร์ของสแตกเป็น cwd ในทุกรูปแบบข้างต้น (ปฏิเสธ ไม่ใช่แค่ขอยืนยัน)
ปลอดภัยต่อระบบจริง: junction สร้างใต้โฟลเดอร์ชั่วคราวของเทสต์ และถูกถอดด้วย os.rmdir (ถอดแค่ตัวลิงก์ ไม่แตะ
ของปลายทาง) ก่อนลบโฟลเดอร์ชั่วคราว — ไม่มีการเปิด/อ่าน/เขียนไฟล์ใน C:\\LLM\\secrets หรือโค้ดของสแตก
"""
import ctypes
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

guard = C.import_local("guard")
tools_files = C.import_local("tools_files")

SECRETS = r"C:\LLM\secrets"
TOKEN_NAME = "local-services.token"
STACK_DIR = r"C:\LLM\mcp-local"
STACK_FILE = STACK_DIR + r"\guard.py"


def short_name(path):
    """ชื่อ 8.3 จาก Windows เอง (None ถ้าไดรฟ์ปิดการสร้างชื่อสั้น หรือชื่อสั้นอยู่แล้ว)"""
    buf = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
    if not n or buf.value.lower() == path.lower():
        return None
    return buf.value


def make_junction(link, target):
    """junction ไม่ต้องใช้สิทธิ์ admin (ต่างจาก symlink) — ใช้ของ _winapi ก่อน ถอยไป mklink /J"""
    try:
        import _winapi
        _winapi.CreateJunction(target, link)
        return True
    except (ImportError, AttributeError, OSError):
        pass
    r = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", link, target], capture_output=True)
    return r.returncode == 0 and os.path.isdir(link)


def denied(fn, path):
    try:
        fn(path)
    except guard.Denied:
        return True
    return False


class _JunctionMixin:
    @classmethod
    def setUpClass(cls):
        cls.jdir = C.new_dir("junctions")
        cls.junctions = []
        for name, target in (("to-secrets", SECRETS), ("to-stack", STACK_DIR)):
            link = os.path.join(cls.jdir, name)
            if os.path.isdir(target) and make_junction(link, target):
                cls.junctions.append(link)

    @classmethod
    def tearDownClass(cls):
        # ถอดเฉพาะตัว junction (os.rmdir บน reparse point ลบแค่ลิงก์) — ห้าม rmtree ผ่านลิงก์
        for link in cls.junctions:
            try:
                os.rmdir(link)
            except OSError:
                pass

    def junction(self, name):
        link = os.path.join(self.jdir, name)
        if link not in self.junctions:
            self.skipTest("สร้าง junction ไม่ได้บนเครื่องนี้")
        return link


class SecretPathVariantTests(_JunctionMixin, unittest.TestCase):
    def variants(self):
        tok = SECRETS + "\\" + TOKEN_NAME
        out = [tok, "c:/llm/SECRETS/" + TOKEN_NAME, tok.upper(), "\\\\?\\" + tok, "\\\\.\\" + tok,
               "\\\\127.0.0.1\\c$\\LLM\\secrets\\" + TOKEN_NAME, "\\\\localhost\\C$\\LLM\\secrets\\" + TOKEN_NAME,
               "\\\\?\\UNC\\127.0.0.1\\c$\\LLM\\secrets\\" + TOKEN_NAME,
               r"C:\LLM\projects\..\secrets" + "\\" + TOKEN_NAME, r"C:\LLM\.\secrets\.\x.txt",
               SECRETS + ".\\" + TOKEN_NAME, SECRETS + " \\" + TOKEN_NAME, tok + ".", tok + " ", tok + "::$DATA",
               SECRETS, SECRETS + "\\", SECRETS + "\\*", "%SystemDrive%\\LLM\\secrets\\" + TOKEN_NAME]
        sn = short_name(SECRETS)
        if sn:
            out.append(sn + "\\" + TOKEN_NAME)
        return out

    def test_every_form_of_the_token_path_is_unreadable(self):
        for p in self.variants():
            with self.subTest(path=p):
                self.assertTrue(denied(guard.check_read, p))
                self.assertTrue(denied(guard.check_write, p))

    def test_junction_into_secrets_is_unreadable(self):
        link = self.junction("to-secrets")
        for p in (link, os.path.join(link, TOKEN_NAME), os.path.join(link, "new.txt")):
            with self.subTest(path=p):
                self.assertTrue(denied(guard.check_read, p))
                self.assertTrue(denied(guard.check_write, p))
        # เครื่องมือจริง: ไม่มีค่าโทเคนทดสอบ/จริงหลุด (อ่านไม่ได้ตั้งแต่ด่าน) — ไม่แสดงผลลัพธ์ใน assert
        out = tools_files.read_file(os.path.join(link, TOKEN_NAME))
        self.assertTrue(out.startswith("ปฏิเสธ"), "read_file ผ่าน junction ต้องถูกปฏิเสธ")


class StackWriteVariantTests(_JunctionMixin, unittest.TestCase):
    def resolvable_variants(self):
        out = [STACK_FILE, "c:/llm/MCP-LOCAL/guard.py", r"C:\LLM\projects\..\mcp-local\guard.py",
               STACK_DIR + r".\guard.py", STACK_DIR + r" \guard.py", STACK_FILE + ".", STACK_FILE + " ",
               r"C:\LLM\start-qwen38.ps1.", r"C:\LLM\projects\hub.py ", r"C:\LLM\projects\static\boot.js",
               r"\\.\C:\LLM\mcp-local\guard.py"]
        for p in (STACK_DIR, r"C:\LLM\start-qwen38.ps1", r"C:\LLM\projects\hub.py"):
            sn = short_name(p)
            if sn:
                out.append(sn + (r"\guard.py" if p == STACK_DIR else ""))
        return out

    def test_stack_code_not_writable_in_any_form(self):
        for p in self.resolvable_variants() + ["\\\\?\\" + STACK_FILE, r"\\127.0.0.1\c$\LLM\mcp-local\guard.py",
                                               r"\\?\UNC\127.0.0.1\c$\LLM\mcp-local\guard.py"]:
            with self.subTest(path=p):
                self.assertTrue(denied(guard.check_write, p))

    def test_write_protection_sees_through_aliases(self):
        for p in self.resolvable_variants():
            with self.subTest(path=p):
                self.assertTrue(guard.is_write_protected(p))

    def test_junction_into_stack_is_write_protected(self):
        link = self.junction("to-stack")
        target = os.path.join(link, "guard.py")
        self.assertTrue(guard.is_write_protected(target))
        self.assertTrue(denied(guard.check_write, target))
        self.assertTrue(denied(guard.check_write, os.path.join(link, "new_module.py")))
        out = tools_files.write_file(os.path.join(link, "new_module.py"), "x = 1", confirm_token="deadbeef")
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:160])
        self.assertFalse(os.path.exists(os.path.join(STACK_DIR, "new_module.py")))

    def test_mutating_command_cannot_run_from_stack_dir_alias(self):
        cwds = [STACK_DIR, "c:/llm/mcp-local/", STACK_DIR + ".", "\\\\?\\" + STACK_DIR, "\\\\.\\" + STACK_DIR]
        sn = short_name(STACK_DIR)
        if sn:
            cwds.append(sn)
        link = os.path.join(self.jdir, "to-stack")
        if link in self.junctions:
            cwds.append(link)
        for cwd in cwds:
            with self.subTest(cwd=cwd):
                out = tools_files.exec_shell_command('python -c "print(1)"', cwd=cwd)
                self.assertTrue(out.startswith("ปฏิเสธ"), "ต้องปฏิเสธ ไม่ใช่ขอยืนยัน: " + out[:120])


if __name__ == "__main__":
    unittest.main()
