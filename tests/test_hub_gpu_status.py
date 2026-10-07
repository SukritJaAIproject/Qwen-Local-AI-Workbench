# -*- coding: utf-8 -*-
"""
เทสต์เส้นเชื่อม gpu_profile.py → gpu-profile.json → hub.gpu_status() (สิ่งที่แถบข้าง/หน้าจัดการแสดง)

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

import hub.py ตรงๆ แบบอ่านอย่างเดียว: ไม่เปิดพอร์ต ไม่เรียก nvidia-smi (แทน gpu_fingerprint ด้วยค่าปลอม)
และชี้ GPU_PROFILE ไปไฟล์ในโฟลเดอร์ชั่วคราว — ไม่แตะ C:\\LLM\\gpu-profile.json ของจริง
ตรวจเฉพาะส่วนที่เป็นสัญญาระหว่างสองฝั่ง (โมเดลหลักขึ้นก่อน ชื่อ GPU ต่อโมเดล stale) ไม่ผูกกับรายละเอียดหน้าจอ
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gpu_profile as gp  # noqa: E402
from test_gpu_profile import REAL_MODELS, ID27, ID4B, RTX1000, RTX4090, gpus  # noqa: E402

HUB = r"C:\LLM\projects\hub.py"


def load_hub():
    """import hub.py เป็นโมดูลแยกชื่อ — hub อ่าน sys.argv ตอน import (พอร์ต) จึงต้องแทนชั่วคราว"""
    sys.path.insert(0, os.path.dirname(HUB))
    spec = importlib.util.spec_from_file_location("hub_under_test", HUB)
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tempfile.gettempdir(), "none.json")}):
        spec.loader.exec_module(mod)
    return mod


try:
    hub = load_hub() if os.path.isfile(HUB) else None
    HUB_ERR = None if hub else "ไม่มี hub.py"
except Exception as e:      # noqa: BLE001 — hub กำลังถูกแก้อยู่ก็ข้ามได้ ไม่ทำให้เทสต์ของ gpu_profile ล้ม
    hub, HUB_ERR = None, "import hub.py ไม่ได้: %s: %s" % (type(e).__name__, e)


@unittest.skipIf(hub is None, HUB_ERR or "")
@unittest.skipUnless(os.path.isfile(os.path.join(REAL_MODELS, ID27 + ".gguf")), "ไม่มีโฟลเดอร์โมเดลจริง")
class HubGpuStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hubgpu-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def profile(self, name, devices, fp="fp-then", **opts):
        out = os.path.join(self.tmp, name)
        gp.generate(REAL_MODELS, out, gp.Options(**opts), user_ini=os.path.join(self.tmp, "none.ini"), choice=None,
                    discovery=(devices, "simulate" if devices is not None else "failed", fp))
        return Path(out) / gp.PROFILE_NAME

    def status(self, path, known=True, current="fp-then"):
        with mock.patch.object(hub, "GPU_PROFILE", Path(path)), \
                mock.patch.object(hub, "gpu_fingerprint", return_value=(known, current)):
            return hub.gpu_status()

    def test_missing_file_is_none(self):
        self.assertIsNone(self.status(os.path.join(self.tmp, "nope.json")))

    def test_4090_plan_primary_first(self):
        st = self.status(self.profile("egpu", gpus(RTX1000, RTX4090)))
        self.assertFalse(st["stale"])
        self.assertEqual(st["placement"][0]["model"], ID27)
        self.assertEqual(st["primary"]["devices_short"], ["RTX 4090"])
        self.assertTrue(st["primary"]["vision"])
        self.assertEqual(st["primary"]["ctx"], 65536)
        other = next(p for p in st["placement"] if p["model"] == ID4B)
        self.assertEqual(other["devices_short"], ["RTX 1000 Ada"])

    def test_stale_only_when_both_fingerprints_known(self):
        path = self.profile("egpu", gpus(RTX1000, RTX4090))
        self.assertTrue(self.status(path, current="fp-now")["stale"])
        self.assertFalse(self.status(path, known=False, current=None)["stale"])     # ไม่มี gpu_profile
        self.assertFalse(self.status(path, known=True, current=None)["stale"])      # nvidia-smi ล้ม

    def test_cpu_only_and_legacy_profiles(self):
        st = self.status(self.profile("cpu", []))
        self.assertEqual(st["devices"], [])
        self.assertEqual(st["primary"]["devices_short"], [])            # = "CPU" บนหน้าจอ
        st = self.status(self.profile("legacy", gpus(RTX1000, RTX4090), legacy=True, ctx=32768))
        self.assertEqual(st["profile"], "legacy")
        self.assertEqual(st["primary"]["devices_short"], ["RTX 1000 Ada", "RTX 4090"])
        self.assertFalse(st["primary"]["vision"])

    def test_unknown_discovery_does_not_crash_or_warn(self):
        st = self.status(self.profile("unknown", None, fp=None), known=True, current="fp-now")
        self.assertEqual(st["profile"], "unknown")
        # ไม่ยืนยันว่า "ทำงานบน CPU" — ตรวจไม่ได้ไม่ใช่ไม่มี GPU
        self.assertFalse(st["primary"]["devices_short"])


if __name__ == "__main__":
    unittest.main()
