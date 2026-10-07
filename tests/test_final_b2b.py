# -*- coding: utf-8 -*-
"""
เทสต์ของผู้ตรวจรับรอบสุดท้าย batch 2b (2026-10-06) — hub.apply_office_note

ปัญหา (วัดสดกับ Qwen3-4B, project1): ชิป Office "อ่านข้อมูลที่เลือกไว้ใน Excel ที่เปิดอยู่ แล้ว…" เมื่อหน้าเว็บเป็นภาษาอังกฤษ
4B ไม่เรียก local_read action=office 2/5 ครั้ง (ตอบว่า "ไม่มีไฟล์ Excel เปิดอยู่" เป็นภาษาอังกฤษ) — ใส่หมายเหตุของ hub ท้ายข้อความ
ผู้ใช้ล่าสุดแล้วได้ 5/5 เทสต์นี้ตรึงเงื่อนไขของหมายเหตุ (ใส่เมื่อไร / ไม่ใส่เมื่อไร / ภาษา / ชื่อเครื่องมือ / ไม่ใส่ซ้ำ)
ไม่แตะบริการจริง: โหลด hub.py เป็นโมดูล (ไม่เปิดพอร์ต)
"""
import copy
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
    spec = importlib.util.spec_from_file_location("hub_final_b2b_under_test", HUB)
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


hub = load_hub()

FAST_TOOLS = [{"type": "function", "function": {"name": n, "parameters": {"type": "object"}}}
              for n in ("local_read", "local_do", "local_confirm", "web_search", "fetch_url")]
FULL_TOOLS = [{"type": "function", "function": {"name": n, "parameters": {"type": "object"}}}
              for n in ("read_file", "office_read", "office_write", "kb_search")]


def chat(text, tools=FAST_TOOLS, extra=()):
    return {"model": "Qwen3-4B-Instruct-2507-Q4_K_M",
            "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": text}] + list(extra),
            "tools": copy.deepcopy(tools)}


class OfficeNoteTests(unittest.TestCase):
    def test_chip_prefills_get_note_in_their_own_language(self):
        """ข้อความของชิป Office (ไทย/อังกฤษใน webui-enhance.js) ได้หมายเหตุภาษาเดียวกับข้อความ ชี้ local_read office excel"""
        with open(ENH, encoding="utf-8") as f:
            src = f.read()
        found = 0
        for line in src.splitlines():
            if line.strip().startswith('["office", "Office", "'):
                prefill = line.split('"Office", "', 1)[1].split('"', 1)[0]
                prefill += "สรุปสั้นๆ" if "เลือก" in prefill else "summarize it"     # ผู้ใช้พิมพ์ต่อท้ายชิป
                found += 1
                note = hub.office_read_note(prefill, {"local_read", "local_do"})
                self.assertIn('local_read action="office" what="excel"', note, prefill)
                if "เลือก" in prefill:
                    self.assertTrue(note.startswith("[หมายเหตุจากระบบ"), note)
                    self.assertIn("ภาษาไทย", note)
                else:
                    self.assertTrue(note.startswith("[Note from the system"), note)
                    self.assertIn("in English", note)
        self.assertGreaterEqual(found, 2)

    def test_app_follows_the_message(self):
        self.assertIn('what="word"', hub.office_read_note("สรุปย่อหน้าที่เคอร์เซอร์อยู่ในเอกสาร Word ที่เปิดอยู่ให้หน่อย",
                                                          {"local_read"}))
        self.assertIn('what="powerpoint"', hub.office_read_note("สไลด์ PowerPoint ที่เปิดอยู่ตอนนี้พูดถึงอะไร",
                                                                {"local_read"}))
        self.assertIn('what="excel"', hub.office_read_note("ค่าในเอ็กเซลที่เปิดอยู่คืออะไร", {"local_read"}))

    def test_no_note_for_write_mention_project_file_or_plain_question(self):
        for t in ('ใส่ตาราง [["A",1],["B",2]] ลง Excel ที่ B2',          # เขียน = ไม่ใส่ (วัดแล้ว: มีหมายเหตุ = อ่านแทนเขียน)
                  "Insert this table into Word",
                  "เทียบ @attachments/b.xlsx กับ Excel ที่เปิดอยู่",       # ผู้ใช้ชี้ไฟล์ของโปรเจกต์เอง
                  "สรุปไฟล์ Excel ux4-สถานี.xlsx ในโปรเจกต์",              # ไฟล์ในโปรเจกต์ ไม่ใช่เอกสารที่เปิด
                  "เปิดไฟล์ Word รายงานสถานีB.docx แล้วสรุป",
                  "ตอนตรวจรอบเดือน วัดแรงดันขาเข้าได้กี่โวลต์",
                  "what word did the audit use for the open breaker?",
                  "ค้นเว็บ ราคา Excel 365 ที่เปิดขายอยู่"):                 # สั่งค้นเว็บ
            self.assertEqual(hub.office_read_note(t, {"local_read", "local_do"}), "", t)

    def test_tool_name_follows_the_request(self):
        t = "Summarize the cells I selected in the Excel workbook I have open."
        self.assertIn('office_read what="excel"', hub.office_read_note(t, {"office_read", "office_write"}))
        self.assertEqual(hub.office_read_note(t, {"web_search"}), "")        # ไม่มีเครื่องมืออ่าน Office = ไม่สั่ง
        self.assertEqual(hub.office_read_note(t, set()), "")

    def test_apply_appends_to_latest_user_message_only_once(self):
        doc = chat("อ่านข้อมูลที่เลือกไว้ใน Excel ที่เปิดอยู่ แล้วสรุปสั้นๆ ว่าตู้ไหนมีปัญหา")
        self.assertTrue(hub.apply_office_note(doc))
        user = doc["messages"][1]["content"]
        self.assertTrue(user.startswith("อ่านข้อมูลที่เลือกไว้"))
        self.assertTrue(user.endswith("เป็นภาษาไทย]"))
        self.assertEqual(doc["messages"][0]["content"], "sys")                # ไม่แตะ system (prompt cache)
        again = copy.deepcopy(doc)
        self.assertFalse(hub.apply_office_note(again))                        # ผ่าน hub มาแล้ว = ไม่ใส่ซ้ำ
        self.assertEqual(again, doc)

    def test_same_text_on_every_tool_step(self):
        """ขั้นถัดไปของรอบเครื่องมือ (ผลของ local_read ต่อท้าย) ได้ข้อความผู้ใช้ + หมายเหตุเดิมทุกตัวอักษร"""
        q = "Read what's selected in my open Excel workbook, then summarize it"
        first = chat(q)
        hub.apply_office_note(first)
        step = chat(q, extra=[
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {
                "name": "local_read", "arguments": '{"action": "office", "what": "excel"}'}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "| A | B |"}])
        self.assertTrue(hub.apply_office_note(step))
        self.assertEqual(step["messages"][1], first["messages"][1])
        self.assertEqual(step["messages"][3]["content"], "| A | B |")         # ผลของเครื่องมือไม่ถูกแตะ

    def test_list_content_with_image(self):
        doc = chat([{"type": "text", "text": "Summarize the selected cells in Excel"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}])
        self.assertTrue(hub.apply_office_note(doc))
        parts = doc["messages"][1]["content"]
        self.assertEqual(parts[1]["type"], "image_url")
        self.assertIn("Note from the system", parts[-1]["text"])

    def test_plan_mode_keeps_the_read_tool(self):
        """โหมดวางแผนยังมีเครื่องมืออ่าน (local_read) — หมายเหตุไม่สั่งให้ใช้เครื่องมือที่ถูกถอด"""
        doc = chat("Summarize the selected cells in Excel")
        hub.apply_office_note(doc)
        hub.apply_plan_mode(doc)
        names = {t["function"]["name"] for t in doc["tools"]}
        self.assertIn("local_read", names)
        self.assertNotIn("local_do", names)


if __name__ == "__main__":
    unittest.main()
