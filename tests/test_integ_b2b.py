# -*- coding: utf-8 -*-
"""
เทสต์ของ integrator batch 2b (2026-10-06) — จุดต่อระหว่างสัญญา C2 (Office bridge) กับ C3 (ค้นเอกสารของโปรเจกต์อัตโนมัติ)

ปัญหาที่เจอใน E2E สด (project1 + Qwen3-4B): ข้อความของชิป Office "อ่านข้อมูลที่เลือกไว้ใน Excel ที่เปิดอยู่ แล้ว…" ได้บล็อก kb
ของไฟล์โปรเจกต์ต่อท้าย แล้ว 4B สรุปจากบล็อกนั้นโดยไม่เรียก local_read action=office = ตอบจากแหล่งผิด
แก้ที่ hub.auto_kb_skip: เจตนา "เอกสาร Office ที่เปิดอยู่ / เขียนลง Excel-Word" = ไม่ค้น kb อัตโนมัติ
เทสต์นี้ไม่แตะบริการจริง: โหลด hub.py เป็นโมดูล (ไม่เปิดพอร์ต) และแทน MCP ด้วยตัวที่ล้มเทสต์ถ้าถูกเรียก
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock

HUB = r"C:\LLM\projects\hub.py"
ENH = r"C:\LLM\projects\static\webui-enhance.js"


def load_hub():
    sys.path.insert(0, os.path.dirname(HUB))
    spec = importlib.util.spec_from_file_location("hub_integ_b2b_under_test", HUB)
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


hub = load_hub()

# ข้อความที่ต้องไม่ค้นเอกสารของโปรเจกต์ (ถามถึงเอกสารที่ผู้ใช้เปิดอยู่ หรือสั่งเขียนลงเอกสารนั้น)
OFFICE_MSGS = (
    "อ่านข้อมูลที่เลือกไว้ใน Excel ที่เปิดอยู่ แล้วสรุปสั้นๆ ว่าตู้ไหนมีปัญหา",
    "ใส่ตาราง [[\"A\",1],[\"B\",2]] ลง Excel ที่ B2",
    "สรุปย่อหน้าที่เคอร์เซอร์อยู่ใน Word",
    "สไลด์ที่เปิดอยู่ใน PowerPoint พูดถึงอะไร",
    "ค่าในเอ็กเซลที่เปิดอยู่คืออะไร",
    "Summarize the selected cells in Excel",
    "Read what's selected in my open Excel workbook, then summarize it",
    "Insert this table into Word",
)
# ข้อความที่ยังต้องค้น (ไฟล์ Excel/Word ที่อยู่ในโปรเจกต์ หรือคำว่า word ทั่วไป) — ห้ามข้ามเกินจำเป็น
PROJECT_MSGS = (
    "สรุปไฟล์ Excel ux4-สถานี.xlsx ในโปรเจกต์",
    "เปิดไฟล์ Word รายงานสถานีB.docx แล้วสรุป",
    "what word did the audit use for the open breaker?",
    "ตอนตรวจรอบเดือน วัดได้กี่โวลต์",
    "what did the audit find?",
)


class OfficeIntentSkipTests(unittest.TestCase):
    def test_office_messages_skip_auto_kb(self):
        for t in OFFICE_MSGS:
            self.assertEqual(hub.auto_kb_skip(t), "office", t)

    def test_project_questions_still_search(self):
        for t in PROJECT_MSGS:
            self.assertIsNone(hub.auto_kb_skip(t), t)

    def test_office_chip_prefills_skip(self):
        """ข้อความเริ่มต้นของชิป Office ใน webui-enhance.js (ทั้งไทย/อังกฤษ) ต้องไม่ได้บล็อก kb"""
        with open(ENH, encoding="utf-8") as f:
            src = f.read()
        found = 0
        for line in src.splitlines():
            if line.strip().startswith('["office", "Office", "'):
                prefill = line.split('"Office", "', 1)[1].split('"', 1)[0]
                found += 1
                self.assertEqual(hub.auto_kb_skip(prefill + "สรุปให้หน่อย"), "office", prefill)
        self.assertGreaterEqual(found, 2)

    def test_no_mcp_call_for_office_message(self):
        """build_project_context ของข้อความ Office: ไม่มีบล็อก และไม่เรียก MCP เลย (เก็บแคชได้)"""
        names = ["attachments/station-b-inspection.pdf", "outputs/รายงานสถานีB.docx"]

        def boom(*a, **k):
            raise AssertionError("MCP must not be called for an Office message")

        with mock.patch.object(hub, "project_file_names", return_value=names), \
                mock.patch.object(hub, "_mcp_fast_call", side_effect=boom):
            block, cacheable = hub.build_project_context("project1", OFFICE_MSGS[0], True)
        self.assertEqual((block, cacheable), ("", True))

    def test_mention_still_wins(self):
        """@ไฟล์ ยังแนบ extract แม้ข้อความพูดถึง Excel ที่เปิดอยู่ (ผู้ใช้ชี้ไฟล์เอง)"""
        names = ["attachments/b.xlsx"]
        calls = []

        def fake(slug, tool, args, timeout):
            calls.append(args)
            return "ok", "| a | b |"

        with mock.patch.object(hub, "project_file_names", return_value=names), \
                mock.patch.object(hub, "_mcp_fast_call", side_effect=fake):
            block, _ = hub.build_project_context("project1", "เทียบ @attachments/b.xlsx กับ Excel ที่เปิดอยู่", True)
        self.assertTrue(calls and calls[0].get("action") == "extract")
        self.assertIn("attachments/b.xlsx", block)


if __name__ == "__main__":
    unittest.main()
