# -*- coding: utf-8 -*-
"""
เทสต์กับ llama-server ตัวจริง (router mode) — ปิดไว้เป็นค่าเริ่มต้นเพราะต้องเปิด process

เปิดด้วย:  set GPU_PROFILE_ROUTER_TESTS=1  แล้วรัน  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

ทำไมต้องมี: ชื่อโมเดลที่ gpu_profile.py เขียนเป็น [section] ต้องตรงกับชื่อที่ router ใช้จริงทุกตัวอักษร
ถ้าไม่ตรง router จะสร้าง "โมเดลเสีย" ที่ไม่มี --model ขึ้นมาในรายการ และโมเดลจริงไม่ได้ค่า device ตามแผน
(เคยพลาดมาแล้วกับไฟล์ที่แบ่ง shard: router b10984 แสดง shard ทุกไฟล์ตามชื่อไฟล์เต็ม ไม่รวมเป็นโมเดลเดียว)
อัปเดต llama.cpp เมื่อไหร่ให้รันเทสต์นี้ซ้ำ

ความปลอดภัย: ใช้พอร์ตทดสอบ 8199 เท่านั้น (ห้ามแตะ 8099 ของผู้ใช้) บนโฟลเดอร์โมเดลปลอมขนาดไม่กี่ KB
router ไม่โหลดโมเดลตอนเริ่ม จึงไม่กิน VRAM และเทสต์ปิดเฉพาะ process ที่ตัวเองเปิด
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gpu_profile as gp  # noqa: E402
from test_gpu_profile import RTX1000, RTX4090, gpus, mmproj_meta, plain_meta, write_gguf  # noqa: E402

PORT = 8199
ENABLED = os.environ.get("GPU_PROFILE_ROUTER_TESTS") == "1"


def port_in_use(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


@unittest.skipUnless(ENABLED, "ตั้ง GPU_PROFILE_ROUTER_TESTS=1 เพื่อรันเทสต์ที่เปิด llama-server จริง")
@unittest.skipUnless(os.path.isfile(gp.LLAMA_SERVER), "ไม่มี llama-server.exe")
class RouterListingTests(unittest.TestCase):
    def setUp(self):
        if port_in_use(PORT):
            self.skipTest("พอร์ต %d มีโปรแกรมอื่นใช้อยู่" % PORT)
        self.tmp = tempfile.mkdtemp(prefix="routerlist-")
        self.proc = None

    def tearDown(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()              # เฉพาะ process ที่เทสต์นี้เปิด (ยังไม่มีโมเดลลูกเพราะไม่ได้ขอแชต)
            self.proc.wait(10)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start_router(self, models_dir, preset):
        err = open(os.path.join(self.tmp, "router.err.log"), "wb")
        self.addCleanup(err.close)
        self.proc = subprocess.Popen([gp.LLAMA_SERVER, "--models-dir", models_dir, "--models-preset", preset,
                                      "--host", "127.0.0.1", "--port", str(PORT), "--models-max", "1"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/models" % PORT, timeout=3) as r:
                    return json.loads(r.read().decode("utf-8"))
            except OSError:
                time.sleep(0.5)
        with open(os.path.join(self.tmp, "router.err.log"), encoding="utf-8", errors="replace") as f:
            self.fail("router ไม่ตอบ (exit %s): %s" % (self.proc.poll(), f.read()[-1500:]))

    def test_section_ids_match_router_ids(self):
        mdir = os.path.join(self.tmp, "models")
        os.makedirs(mdir)
        for n in ("Alpha-7B-Q4.gguf", "Big-Split-00001-of-00002.gguf", "Big-Split-00002-of-00002.gguf",
                  "mtp-Alpha-Q4_0.gguf"):
            write_gguf(os.path.join(mdir, n), plain_meta())
        write_gguf(os.path.join(mdir, "mmproj-Alpha-7B-F16.gguf"), mmproj_meta(512))
        out = os.path.join(self.tmp, "out")
        prof = gp.generate(mdir, out, gp.Options(primary="Alpha-7B-Q4"), user_ini=os.path.join(self.tmp, "none.ini"),
                           choice=None, discovery=(gpus(RTX1000, RTX4090), "simulate", None))
        with open(os.path.join(out, gp.PRESET_NAME), encoding="utf-8") as f:
            sections, _ = gp.parse_ini(f.read())
        doc = self.start_router(mdir, os.path.join(out, gp.PRESET_NAME))
        listed = {m["id"]: (m.get("status") or {}).get("args") or [] for m in doc.get("data") or []}
        # ทุก section ของเราต้องเป็นโมเดลที่ router มีอยู่แล้ว (ไม่สร้างรายการเพิ่ม)
        for sid in sections:
            if sid != "*":
                self.assertIn(sid, listed, "section [%s] ไม่ตรงกับโมเดลไหนของ router: %s" % (sid, sorted(listed)))
        # ทุกโมเดลที่ router แสดงต้องมี --model (ไม่มีรายการเสีย) และ mmproj/mtp ไม่ขึ้นเป็นโมเดล
        for mid, args in listed.items():
            self.assertIn("--model", args, mid)
        self.assertNotIn("mtp-Alpha-Q4_0", listed)
        self.assertFalse([m for m in listed if m.lower().startswith("mmproj")])
        # โมเดลที่แผนให้ device ต้องได้ --device ตามนั้นจริง
        for mid, keys in sections.items():
            if mid != "*" and "device" in keys:
                args = listed[mid]
                self.assertEqual(args[args.index("--device") + 1], keys["device"], mid)
        self.assertEqual(set(prof["placement"]), {"Alpha-7B-Q4", "Big-Split-00001-of-00002"})


if __name__ == "__main__":
    unittest.main()
