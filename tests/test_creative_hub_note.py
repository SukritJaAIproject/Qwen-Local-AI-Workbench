# -*- coding: utf-8 -*-
"""
เทสต์ hub.apply_creative_note (2026-10-21) — หมายเหตุท้ายข้อความผู้ใช้ "สร้างวิดีโอ = ใช้ creative_video ไม่ใช่ ffmpeg/สคริปต์"

ปัญหา (E2E จริงกับ Qwen3.8-27B, โปรเจกต์ creative-test): "ช่วยสร้างวิดีโอสั้น 2 วินาที ฉากโดรนบินเหนือภูเขาไฟ..." โมเดลเลือก
exec_shell_command ของ llama-server (where ffmpeg -> imageio_ffmpeg -> ffmpeg testsrc2) ทำวิดีโอลายทดสอบแทน ทั้งที่ local_do
มี action=creative_video — เทสต์นี้ตรึงเงื่อนไขของหมายเหตุ (ใส่เมื่อไร / ไม่ใส่เมื่อไร / ภาษา / ชื่อเครื่องมือ / ไม่ใส่ซ้ำ)
ไม่แตะบริการจริง: โหลด hub.py เป็นโมดูล (ไม่เปิดพอร์ต)
"""
import copy
import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock

HUB = os.path.join(r"C:\LLM", "projects", "hub.py")


def load_hub():
    sys.path.insert(0, os.path.dirname(HUB))
    spec = importlib.util.spec_from_file_location("hub_creative_note_under_test", HUB)
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


hub = load_hub()

FAST = {"local_read", "local_do", "local_confirm", "web_search", "fetch_url", "exec_shell_command", "run_javascript"}
FULL = {"read_file", "creative_video", "creative_status", "creative_cancel", "kb_search"}
FAST_TOOLS = [{"type": "function", "function": {"name": n, "parameters": {"type": "object"}}} for n in sorted(FAST)]


def chat(text, tools=FAST_TOOLS, extra=()):
    return {"model": "Qwen3.8-27B-UD-Q4_K_M",
            "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": text}] + list(extra),
            "tools": copy.deepcopy(tools)}


class CreativeNoteTests(unittest.TestCase):
    def test_make_video_requests_get_note_in_their_language(self):
        th = "ช่วยสร้างวิดีโอสั้น 2 วินาที ฉากโดรนบินเหนือภูเขาไฟที่กำลังระเบิดมีลาวาไหล ตั้งชื่อไฟล์ว่า volcano-test"
        note = hub.creative_video_note(th, FAST)
        self.assertIn('local_do action="creative_video" prompt="<คำบรรยายฉาก>"', note)
        self.assertTrue(note.startswith("[หมายเหตุจากระบบ ไม่ใช่ข้อความของผู้ใช้:"), note)
        self.assertIn("ffmpeg", note)
        for en in ("Generate a 3-second video of a cat walking on the beach at sunset",
                   "make me a short clip of rain on a window",
                   "Can you create an animation from this photo? use cover.png",
                   "render a video: drone shot over a volcano"):
            note = hub.creative_video_note(en, FAST)
            self.assertTrue(note.startswith("[Note from the system, not written by the user:"), en)
            self.assertIn('local_do action="creative_video" prompt="<scene description>"', note)
        for th2 in ("ทำคลิปสั้นๆ แมวเดินบนชายหาด", "เจนวิดีโอจากรูป cover.png ให้หน่อย", "สร้างแอนิเมชันโลโก้หมุน 3 วิ",
                    "สร้างวิดีโอจาก @attachments/a.png"):             # @ อ้างไฟล์ภาพ = ภาพ→วิดีโอ (ต่างจาก Office ที่ไม่ใส่)
            note = hub.creative_video_note(th2, FAST)
            self.assertIn("creative_video", note, th2)
            self.assertIn("image=ชื่อไฟล์ใน attachments", note)

    def test_tool_name_follows_the_request(self):
        t = "สร้างวิดีโอ โดรนบินเหนือทะเล"
        self.assertIn('local_do action="creative_video"', hub.creative_video_note(t, FAST))
        full = hub.creative_video_note(t, FULL)
        self.assertIn("ผ่านเครื่องมือ creative_video", full)
        self.assertNotIn("local_do", full)
        self.assertEqual(hub.creative_video_note(t, {"web_search", "exec_shell_command"}), "")   # ไม่มีเครื่องมือ = ไม่สั่ง
        self.assertEqual(hub.creative_video_note(t, set()), "")

    def test_no_note_for_editing_questions_mentions_or_other_requests(self):
        for t in ("ตัดต่อวิดีโอนี้ให้สั้นลงเหลือ 10 วินาที",            # ตัดต่อไฟล์ที่มี = media_*
                  "แปลงวิดีโอ a.mov เป็น mp4",
                  "ช่วยย่อขนาดคลิปนี้ให้เล็กลง",
                  "ถอดเสียงจากวิดีโอประชุมให้หน่อย",
                  "trim the video to the first 5 seconds and make a gif",
                  "compress the clip for email",
                  "extract the audio from this video",
                  "วิดีโอที่ดีควรมีองค์ประกอบอะไรบ้าง",                    # ไม่มีเจตนาสร้าง
                  "สร้างรายงานสรุปยอดขายให้หน่อย",                       # ไม่ใช่วิดีโอ
                  "what makes a video go viral?",
                  "สรุปสิ่งที่พูดในคลิปนี้"):
            self.assertEqual(hub.creative_video_note(t, FAST), "", t)

    def test_apply_appends_to_latest_user_message_only_once(self):
        doc = chat("ช่วยสร้างวิดีโอสั้น 2 วินาที ฉากโดรนบินเหนือภูเขาไฟ")
        self.assertTrue(hub.apply_creative_note(doc))
        user = doc["messages"][1]["content"]
        self.assertTrue(user.startswith("ช่วยสร้างวิดีโอสั้น"))
        self.assertTrue(user.endswith("สร้างวิดีโอแทน]"), user)
        self.assertEqual(doc["messages"][0]["content"], "sys")                # ไม่แตะ system (prompt cache)
        again = copy.deepcopy(doc)
        self.assertFalse(hub.apply_creative_note(again))                      # มีหมายเหตุแล้ว = ไม่ใส่ซ้ำ
        self.assertEqual(again, doc)
        # รอบเครื่องมือ: ข้อความผู้ใช้เดิม + assistant/tool ต่อท้าย — หมายเหตุยังไปที่ข้อความผู้ใช้ล่าสุดตัวเดิม (ข้อความเดิมทุกตัวอักษร)
        doc2 = chat("ช่วยสร้างวิดีโอสั้น 2 วินาที ฉากโดรนบินเหนือภูเขาไฟ",
                    extra=[{"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "local_do", "arguments": "{}"}}]},
                           {"role": "tool", "tool_call_id": "c1", "content": "REVIEW ..."}])
        self.assertTrue(hub.apply_creative_note(doc2))
        self.assertEqual(doc2["messages"][1]["content"], user)
        self.assertEqual(doc2["messages"][2]["content"], "")

    def test_content_as_parts_and_office_note_do_not_collide(self):
        doc = chat("x")
        doc["messages"][1]["content"] = [{"type": "text", "text": "Generate a video of a sunrise over Bangkok"},
                                         {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
        self.assertTrue(hub.apply_creative_note(doc))
        parts = doc["messages"][1]["content"]
        self.assertEqual(parts[0]["text"], "Generate a video of a sunrise over Bangkok")
        self.assertTrue(parts[-1]["text"].strip().startswith("[Note from the system"))
        office = "อ่านข้อมูลที่เลือกไว้ใน Excel ที่เปิดอยู่ แล้วสรุปสั้นๆ"
        self.assertEqual(hub.creative_video_note(office, FAST), "")
        self.assertNotEqual(hub.office_read_note(office, FAST), "")

    def test_pipeline_hook_present(self):
        with open(HUB, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("touched = apply_creative_note(doc) or touched", src)
        self.assertLess(src.index("touched = apply_office_note(doc) or touched"),
                        src.index("touched = apply_creative_note(doc) or touched"))


if __name__ == "__main__":
    unittest.main()
