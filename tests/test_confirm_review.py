# -*- coding: utf-8 -*-
"""เทสต์รอบ review (สัญญา R1-R3, R5 — security review อิสระ 2026-09-30)

ปัญหาที่ปิด
  (1) local_confirm รับแค่ token 8 ตัว กล่อง "อนุญาต" ของ WebUI (แสดงอาร์กิวเมนต์ของการเรียก) จึงไม่เคยแสดง
      โค้ด/คำสั่งจริง โมเดลที่โดนหลอกโชว์โค้ดหนึ่งในแชตแล้วยืนยัน token ของอีกโค้ดได้
  (2) ตัวอย่างโค้ดตัดที่ 80 บรรทัด/5,000 ตัวอักษร ช่องว่างยาวซ่อนโค้ดนอกจอได้ และอักขระ bidi/zero-width
      ผ่านไปดิบๆ (Trojan Source)
  (3) token ค้างได้ถึง 200 ตัว
ตรวจ
  R1 ทุก token มีข้อความตรวจทาน (review) ที่เซิร์ฟเวอร์สร้างครบทุกชนิดการกระทำ อักขระซ่อนเป็น «U+XXXX»
     + บรรทัดคำเตือน, บรรทัดยาวตัดพร้อม ↩, ช่องว่างยาวย่อ, เนื้อหาใหญ่ = diff ตัดที่ 400 บรรทัด + hash
  R2 local_confirm(confirm_token, review) — ไม่ส่ง/ไม่ตรง = ปฏิเสธและ token ยังไม่ถูกใช้, ปรับได้แค่ \\r\\n
     กับช่องว่างท้ายบรรทัด, ผลที่ออก token มีบล็อก ```review ให้คัดลอก
  R3 python เกิน 400 บรรทัด/20,000 ตัวอักษร (หลังแสดงผล) ถูกปฏิเสธก่อนออก token, ค้างได้ 5 ตัวต่อโปรเจกต์,
     token python ใหม่ทิ้งตัวเก่าของโปรเจกต์เดียวกัน
  R5 เส้นทางเต็มผ่าน HTTP บนพอร์ตสำรอง (8892 หรือพอร์ตว่างที่ระบบสุ่ม) ด้วย token ทดสอบ
รอบ FIXER (e2e จริงกับ Qwen3-4B + security review รอบสอง)
  * review ขึ้นต้นด้วยช่องว่าง (" [python]") ต้องผ่าน แต่ช่องว่าง/บรรทัดว่างที่ยอมมีเพดาน, ตอบไม่ตรงบอกจุดแรกที่ผิด
    + ขั้นตอนลองใหม่ทันที + ต่ออายุ token (เพดานรวม), review ยาวไม่แนบซ้ำ, token อายุ 10 นาที
  * ไฟล์สคริปต์ที่แสดงครบไม่ได้ (ใหม่/ทับ/edit) ถูกปฏิเสธก่อนออก token, การทับไฟล์ผูกกับ sha ของไฟล์เดิม
  * Default_Ignorable ทั้งชุด (รวม U+180B-180F) + homoglyph แสดงเป็นรหัส, โฮสต์ของ URL มีรูป punycode
  * argv/ค่าหัวข้อที่มี \\n อยู่บรรทัดเดียว, make_file แสดงเนื้อหา, GET SSE ตอบ 405, คำอธิบาย local_do ใหม่
รอบ review-fetch (S1/S2 — e2e จริง: Qwen3-4B ไม่แสดง review ในแชต คัดลอกกลับมาแค่บางส่วน แล้วถามผู้ใช้ซ้ำแทนการลองใหม่)
  S1 GET /review/<slug>?token=... อ่านอย่างเดียว: review ของ token ที่ค้างอยู่ "ของโปรเจกต์นั้น" (ผิวไหนก็ได้) ไม่ใช้/ไม่ต่ออายุ
     token ไม่คืนค่า token, ด่าน Bearer + Origin + Host + ผูก Origin กับ slug เหมือน /mcp, preflight/CORS, จำกัดอัตรา
  S2 local_confirm(confirm_token[, review]) — review ไม่บังคับ (ไม่มีคีย์/null/ว่าง = ใช้ token อย่างเดียว) ส่งมาต้องตรง
     ไม่ตรง = ปฏิเสธ token ยังอยู่ และคำตอบบอกให้เรียกใหม่ทันทีด้วย token อย่างเดียว ไม่แนบ review ให้คัดลอกซ้ำ
     ด่านคนคือกล่องอนุญาตที่ดึง review จาก S1 (webui-enhance.js) — การผูก/ใช้ครั้งเดียว/อายุ/เพดาน ยังอยู่ครบ
รอบ FIXER ของ S1/S2 (review อิสระ + e2e จริง 2026-10-01)
  * token อย่างเดียวรันได้เฉพาะหลังกล่องอนุญาตดึง review ไปแสดง (GET /review ที่มี Origin -> viewed) ไม่งั้นปฏิเสธ
    token ยังอยู่ ครั้งแรกให้ลองใหม่ ครั้งต่อไปให้รีโหลดหน้า / review ที่ตรงยังรันได้โดยไม่ต้อง view
  * จำกัดอัตรา /review: โปรเจกต์จริงนับแยก slug อื่นใช้กองกลาง ยิง slug ใหม่รีเซ็ตตัวนับไม่ได้
  * review ครอบรั้ว ```review ของเซิร์ฟเวอร์หนึ่งชั้นถือว่าตรง (เนื้อในต้องตรงเป๊ะ, ช่องว่างรอบรั้วมีเพดานเดิม)

ไม่เปิด kernel ของ Python และไม่เปิดเบราว์เซอร์ (ทุกกรณีหยุดที่ขั้นขอยืนยัน) ข้อมูลทั้งหมดอยู่ใน temp
"""
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

guard = C.import_local("guard")
server = C.import_local("server")
tools_files = C.import_local("tools_files")
tools_python = C.import_local("tools_python")
tools_fast = C.import_local("tools_fast")
tools_docs = C.import_local("tools_docs")
tools_media = C.import_local("tools_media")
tools_tasks = C.import_local("tools_tasks")
tools_browser = C.import_local("tools_browser")
scheduler = C.import_local("scheduler")

# อักขระทดสอบสร้างด้วย chr() เท่านั้น — ไฟล์เทสต์เองต้องไม่มีอักขระซ่อนดิบ (คนอ่านโค้ดเทสต์ก็ต้องเห็นครบ)
RLO, LRI, PDI = chr(0x202E), chr(0x2066), chr(0x2069)
ZWSP, ZWJ, VS16 = chr(0x200B), chr(0x200D), chr(0xFE0F)
# อักขระที่ต้องไม่หลุดไปถึงกล่องอนุญาตแบบดิบ (แท็บก็ต้องเป็นคำ «TAB» เพราะกว้างไม่แน่นอน)
_HIDDEN_RANGES = ((0x202A, 0x202E), (0x2066, 0x2069), (0x200B, 0x200F), (0x2060, 0x2060),
                  (0xFEFF, 0xFEFF), (0x2028, 0x2029), (0x00A0, 0x00A0), (0x0D, 0x0D), (0x09, 0x09),
                  (0x0B, 0x0C), (0x3164, 0x3164), (0xE0000, 0xE007F), (0x180B, 0x180F))
RAW_HIDDEN = re.compile("[%s]" % "".join("%s-%s" % (re.escape(chr(a)), re.escape(chr(b)))
                                          for a, b in _HIDDEN_RANGES))


def setUpModule():
    server.load_modules()


def _slug(prefix: str) -> str:
    return "%s-%s" % (prefix, os.urandom(3).hex())


def rpc(project: str, name: str, args: dict, fast: bool = True) -> str:
    reply = server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": name, "arguments": args}}, project, fast)
    return reply["result"]["content"][0]["text"]


def _view(project: str, tok: str) -> dict:
    """จำลอง "กล่องอนุญาตของหน้าแชตดึง review ของ token นี้ไปแสดง" (GET /review ที่มี Origin — server จด viewed)
    รอบ FIXER ของ S1/S2: local_confirm แบบ token อย่างเดียวรันได้เฉพาะ token ที่ผ่านขั้นนี้แล้ว"""
    status, body = server.review_lookup(project, "token=" + tok, viewer=True)
    assert status == 200, body
    return body


def _write(p: str, text: str) -> None:
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _read(p: str) -> str:
    # โหมดข้อความ: edit/write ของเครื่องมือเขียน CRLF บน Windows — เทียบเนื้อหา ไม่ใช่ตัวขึ้นบรรทัด
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _pending_count(project: str) -> int:
    with guard._lock:
        return sum(1 for it in guard._pending.values() if it["scope"] == project
                   and it["exp"] >= time.time())


class _ReviewAsserts(unittest.TestCase):
    def assertReviewOk(self, hint: str, project: str | None, *must_contain) -> str:
        """ข้อความขอยืนยันต้องมี token + บล็อก review ที่ตรงกับที่เก็บไว้ ไม่มีอักขระซ่อนดิบ บรรทัดไม่เกิน 201"""
        tok = C.token_from_hint(hint)
        review = C.review_from_hint(hint)
        self.assertTrue(tok, hint[:400])
        self.assertTrue(review, hint[:600])
        with guard.project_scope(project) if project is not None else _nullscope():
            stored = guard.pending_review(tok)
        self.assertEqual(review, stored, "บล็อก review ในผลต้องเป็นข้อความเดียวกับที่ token เก็บไว้")
        self.assertIsNone(RAW_HIDDEN.search(review), repr(review[:300]))
        for ln in review.split("\n"):
            self.assertLessEqual(len(ln), guard.REVIEW_WRAP + 1, ln[:80])
        for s in must_contain:
            self.assertIn(s, review)
        return review


class _nullscope:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


# ============================================================ R1: การแสดงผล
class RenderTests(unittest.TestCase):
    def test_bidi_and_zero_width_escaped_with_warning(self):
        cps = list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)) \
            + list(range(0x200B, 0x2010)) + [0x2060, 0xFEFF]
        for cp in cps:
            with self.subTest(cp="U+%04X" % cp):
                r, st = guard.render_review("a%sb" % chr(cp))
                self.assertIn("a«U+%04X»b" % cp, r)
                self.assertNotIn(chr(cp), r)
                self.assertEqual(st["hidden"], 1)
                self.assertTrue(r.startswith("⚠"), "ต้องมีบรรทัดคำเตือนนำหน้า")
                self.assertIn("Trojan Source", r.split("\n")[0])

    def test_other_invisible_and_line_breaking_chars_escaped(self):
        for cp in (0xE0041, 0xE0100, 0x3164, 0x115F, 0x00A0, 0x2028, 0x2029, 0x0085, 0x0D, 0x0C,
                   0x0B, 0x00AD, 0x2800, 0x1B, 0x061C):
            ch = chr(cp)
            with self.subTest(ch="U+%04X" % ord(ch)):
                r, st = guard.render_review("x%sy" % ch)
                self.assertIn("«U+%04X»" % ord(ch), r)
                self.assertNotIn(ch, r)
                self.assertEqual(st["hidden"], 1)
        # variation selector ต่อท้ายอักษรธรรมดา = ช่องลักลอบซ่อนข้อมูล
        r, st = guard.render_review("a" + chr(0xFE01) + chr(0xFE02))
        self.assertEqual(st["hidden"], 2)

    def test_crlf_thai_and_emoji_are_not_flagged(self):
        emoji = chr(0x2764) + VS16 + " " + chr(0x2714) + VS16 + " ok"
        r, st = guard.render_review("สวัสดีครับ น้ำ กี้\r\n" + emoji)
        self.assertEqual(r, "สวัสดีครับ น้ำ กี้\n" + emoji)
        self.assertEqual(st["hidden"], 0)
        self.assertFalse(r.startswith("⚠"))

    def test_long_line_hard_wrapped_with_visible_markers(self):
        line = "".join(chr(0x61 + i % 26) for i in range(450))
        r, st = guard.render_review(line)
        rows = r.split("\n")
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].endswith("↩") and rows[1].endswith("↩"))
        self.assertTrue(rows[1].startswith("↪") and rows[2].startswith("↪"))
        self.assertTrue(all(len(x) <= guard.REVIEW_WRAP + 1 for x in rows))
        rebuilt = "".join(x.rstrip("↩").lstrip("↪") for x in rows)
        self.assertEqual(rebuilt, line, "ตัดบรรทัดแล้วเนื้อหาต้องครบทุกตัว")
        self.assertEqual(st["wrapped"], 1)
        self.assertEqual(guard.review_measure(line)[0], 3)

    def test_space_padding_collapsed_so_code_stays_on_screen(self):
        r, st = guard.render_review("print('ok')" + " " * 300 + "__import__('os').system('evil')")
        body = r.split("\n")[-1]
        self.assertIn("«300 spaces»__import__('os').system('evil')", body)
        self.assertLess(body.index("system"), 60, "โค้ดหลังช่องว่างต้องอยู่ในจอ")
        self.assertEqual(st["runs"], 1)
        self.assertIn("ช่องว่างยาว", r.split("\n")[0])
        r2, st2 = guard.render_review("x = 1" + " " * 31 + "# ok")
        self.assertEqual(st2["runs"], 0)
        self.assertIn(" " * 31, r2)

    def test_our_marker_chars_in_content_cannot_fake_markers(self):
        r, st = guard.render_review("# comment ↩\n↪ «40 spaces» »")
        self.assertIn("«U+21A9»", r)
        self.assertIn("«U+21AA»", r)
        self.assertIn("«U+00AB»40 spaces«U+00BB»", r)
        self.assertEqual(st["hidden"], 5)

    def test_tab_shown_as_word_without_trojan_warning(self):
        r, st = guard.render_review("a\tb")
        self.assertEqual(r, "a«TAB»b")
        self.assertEqual(st["hidden"], 0)

    def test_stacked_combining_marks_capped(self):
        r, st = guard.render_review("q" + "́" * 6)
        self.assertEqual(st["hidden"], 3)
        self.assertTrue(r.endswith("«U+0301»"))

    def test_capped_block_says_how_many_lines_hidden(self):
        lines = ["line %d" % i for i in range(1000)]
        text, omitted = guard.review_capped(lines, "ab" * 32)
        self.assertEqual(omitted, 1000 - guard.REVIEW_BLOCK_MAX_LINES)
        self.assertIn("(ไม่แสดงอีก %d บรรทัด — %d more lines not shown — content hash sha256:%s…)"
                      % (omitted, omitted, "ab" * 8), text)


class MatchTests(unittest.TestCase):
    def test_only_whitespace_forms_are_normalised(self):
        """ปรับได้แค่ CRLF, ช่องว่างท้ายบรรทัด, ช่องว่างหน้าบรรทัดแรกของทั้งก้อน (FIXER: e2e จริง Qwen3-4B ส่ง
        " [python] ..." ทุกครั้ง) และบรรทัดว่างหัว/ท้าย — อย่างอื่นต่างแม้ตัวเดียวคือไม่ตรง"""
        stored = "⚠ คำเตือน\n[run] x\n1│ echo «U+202E»a\n----- จบ -----"
        ok = [stored, stored.replace("\n", "\r\n"), stored.replace("\n", "   \n") + "\t ",
              stored + "\n\n", "\n" + stored, " " + stored, "\t" + stored, "  " + stored + "\r\n"]
        for g in ok:
            self.assertTrue(guard.review_matches(stored, g), repr(g))
        bad = [stored.replace("«U+202E»", RLO), stored.replace("[run]", "[run] "[:-1] + " x"),
               stored[:-1], stored.split("\n", 1)[1], stored.replace("echo", "echO"),
               stored.replace("\n[run]", "\n [run]"), stored.replace("\n1│", "\n1 │"),
               "", None, 123]
        for g in bad:
            self.assertFalse(guard.review_matches(stored, g), repr(g))
        self.assertFalse(guard.review_matches(None, stored))
        self.assertFalse(guard.review_matches("", ""))

    def test_whitespace_padding_is_bounded(self):
        """FIXER: ช่องว่าง/บรรทัดว่างที่ยอมให้ต่างต้องมีเพดาน — กล่องอนุญาตตัดบรรทัดแบบ break-spaces ช่องว่าง 10,000 ตัว
        ท้ายบรรทัดแรก = พื้นที่ว่างหลายร้อยบรรทัดที่ดันโค้ดจริงลงไปใต้ขอบกล่อง คนกดอนุญาตโดยไม่เห็น"""
        stored = "[python] x\ncwd: C:\\w\n1│ print(1)\n----- จบ -----"
        pad = guard.REVIEW_PAD_MAX
        self.assertTrue(guard.review_matches(stored, " " * pad + stored))
        self.assertTrue(guard.review_matches(stored, stored.replace("\n", " " * pad + "\n", 1)))
        self.assertTrue(guard.review_matches(stored, "\n" * guard.REVIEW_BLANK_MAX + stored
                                             + "\n" * (guard.REVIEW_BLANK_MAX + 1)))
        for g in (" " * (pad + 1) + stored, " " * 10_000 + stored,
                  stored.replace("\n", " " * (pad + 1) + "\n", 1),
                  stored.replace("\n", " " * 10_000 + "\n", 1),
                  stored.replace("\n", "\t" * 50 + "\n", 1),
                  "\n" * (guard.REVIEW_BLANK_MAX + 1) + stored,
                  stored + "\n" * 500, stored + "\n" + " " * 5000):
            self.assertFalse(guard.review_matches(stored, g), repr(g[:40]))

    def test_server_fence_copied_by_model_is_accepted(self):
        """รอบ FIXER (e2e จริง): Qwen3-4B ส่ง review ครอบด้วยรั้ว ```review ของเซิร์ฟเวอร์เอง เนื้อในตรงทุกตัวอักษร
        แต่ถูกปฏิเสธ คนต้องกดอนุญาตสองครั้ง — ถอดรั้วหนึ่งชั้นก่อนเทียบ เนื้อในยังต้องตรงเป๊ะ"""
        stored = "[python] x\ncwd: C:\\w\n1│ print(1)\n----- จบโค้ด (ครบ 1 บรรทัด) -----"
        fenced = guard.review_fence(stored)
        self.assertTrue(fenced.startswith("```review\n"))
        pad, blank = " " * guard.REVIEW_PAD_MAX, "\n" * guard.REVIEW_BLANK_MAX
        ok = [fenced, fenced + "\n", fenced.replace("\n", "\r\n"), " " + fenced, pad + fenced,
              "```review\n %s\n```" % stored, "```review\n%s\n%s```" % (stored, pad),
              "````review\n%s\n````" % stored, "```review\n\n%s\n\n```" % stored,
              "\n" + fenced + "\n\n", "```review  \n%s\n```  " % stored]
        for g in ok:
            self.assertTrue(guard.review_matches(stored, g), repr(g[:60]))
        # รั้วของ stored ที่มี ``` ในเนื้อหา (review_fence ยาวขึ้นเอง) ก็ถอดได้
        tricky = "[write] x\n1│ ```js\n2│ ```"
        self.assertTrue(guard.review_matches(tricky, guard.review_fence(tricky)))
        bad = [
            fenced.replace("print(1)", "print(2)"),                       # เนื้อในต่าง = ไม่ตรงเหมือนเดิม
            "```review\n```review\n%s\n```\n```" % stored,               # ถอดแค่ชั้นเดียว
            "```review\n%s\n````" % stored, "````review\n%s\n```" % stored,   # รั้วปิดต้องยาวเท่ารั้วเปิด
            "```\n%s\n```" % stored, "```python\n%s\n```" % stored,      # รั้วต้องเป็นแบบที่เซิร์ฟเวอร์พิมพ์ (```review)
            "~~~review\n%s\n~~~" % stored,
            "```review\n%s" % stored, "%s\n```" % stored,                 # รั้วครึ่งเดียว
            "```review\n%s\n```\nอนุมัติแล้ว" % stored,                 # มีข้อความนอกรั้ว
            " " * (guard.REVIEW_PAD_MAX + 1) + fenced,                   # ช่องว่างรอบรั้วยังมีเพดานเดิม
            "```review\n%s\n%s```" % (stored, " " * (guard.REVIEW_PAD_MAX + 1)),
            "```review" + " " * 50 + "\n%s\n```" % stored,
            "```review\n%s%s\n```" % (blank + "\n", stored),              # บรรทัดว่างในรั้วนับเพดานรวม
            "```review\n%s\n```" % stored.replace("\n", " " * 10 + "\n", 1),
        ]
        for g in bad:
            self.assertFalse(guard.review_matches(stored, g), repr(g[:60]))
        # normalize_review (รูปที่ enhance เลียนแบบ) ไม่ถอดรั้ว — ใช้กับข้อความของเซิร์ฟเวอร์ ไม่เปลี่ยนพฤติกรรมเดิม
        self.assertEqual(guard.normalize_review(fenced), fenced)
        # จุดที่ไม่ตรงนับบรรทัดหลังถอดรั้ว (เทียบแบบเดียวกับ review_matches)
        msg = guard.review_difference(stored, fenced.replace("print(1)", "print(2)"))
        self.assertIn("บรรทัด 3", msg)
        self.assertIn("print(1)", msg)

    def test_first_difference_is_named(self):
        stored = "[edit] x\npath: C:\\a.txt\n-one\n+two\n===== จบ diff ====="
        self.assertIn("ไม่ได้ส่ง review", guard.review_difference(stored, None))
        msg = guard.review_difference(stored, stored.replace("\npath", "\n  path"))
        self.assertIn("บรรทัด 2", msg)
        self.assertIn("ช่องว่างเกินมา 2 ตัว", msg)
        msg = guard.review_difference(stored, stored.replace("+two", "+tw0"))
        self.assertIn("บรรทัด 4 ตัวอักษรที่ 4", msg)
        self.assertIn('"+two"', msg)
        self.assertIn('"+tw0"', msg)
        msg = guard.review_difference(stored, stored.rsplit("\n", 2)[0])
        self.assertIn("ส่งมาไม่ครบ", msg)
        self.assertIn("บรรทัด 4", msg)
        self.assertIn("มีบรรทัดเกินมา", guard.review_difference(stored, stored + "\nextra"))
        msg = guard.review_difference(stored, stored.replace("-one", "-o" + RLO + "ne"))
        self.assertIn("«U+202E»", msg, "อักขระซ่อนในข้อความตอบกลับต้องเห็นเป็นรหัส")
        self.assertNotIn(RLO, msg)


# ============================================================ R2: local_confirm
class LocalConfirmFlowTests(_ReviewAsserts):
    def setUp(self):
        self.project = _slug("rv-flow")
        self.d = C.new_dir("rvflow")
        self.p = os.path.join(self.d, "a.txt")
        _write(self.p, "one\n")

    def _edit_hint(self, new="two", path=None):
        return rpc(self.project, "local_do", {"action": "edit", "path": path or self.p,
                                              "old": "one", "new": new})

    def test_issuing_result_has_fenced_review_and_instructions(self):
        hint = self._edit_hint()
        self.assertRegex(hint, r"(?m)^```+review$")
        review = self.assertReviewOk(hint, self.project, "[edit]", "path: ", "-one", "+two")
        tok = C.token_from_hint(hint)
        after = hint.split(review, 1)[1]
        # ยังต้องแสดง REVIEW ให้ผู้ใช้และถามก่อน (S2 เปลี่ยนแค่ "ไม่ต้องคัดลอกกลับมา")
        self.assertIn("แสดงบล็อก REVIEW", after)
        self.assertIn("ถามว่าอนุมัติไหม", after)
        # รอบ FIXER (e2e จริง): Qwen3-4B ไม่แสดงบล็อกในแชต — ขั้นที่ 1 บอกเป็นการกระทำที่จับต้องได้ (คัดลอกทั้งบล็อกลงคำตอบ)
        self.assertIn("คัดลอกทั้งบล็อกพร้อมรั้วบนล่างลงในคำตอบ", after)
        self.assertNotIn("```", after.split("ขั้นตอน:", 1)[1],
                         "ข้อความขั้นตอนต้องไม่มีรั้วเอง (ตัวดึงบล็อก REVIEW ของเทสต์/หน้าแชตจับรั้วต้นบรรทัด)")
        # S2: เรียกด้วย token อย่างเดียว — โมเดลเล็กคัดลอกข้อความยาวกลับมาไม่ครบ (e2e จริง)
        self.assertIn('local_confirm(confirm_token="%s")' % tok, after)
        self.assertIn("ไม่ต้องคัดลอก REVIEW", after)
        self.assertIn("review ไม่บังคับ", after)
        self.assertIn("กล่อง \"อนุญาต\"", after)

    def test_token_alone_runs_once(self):
        """S2: ไม่ส่ง review (ไม่มีคีย์ / null / ข้อความว่าง) = ใช้ token อย่างเดียวได้ — คนตรวจ review ของเซิร์ฟเวอร์
        ในกล่องอนุญาต (S3) การผูก action + อาร์กิวเมนต์ + โปรเจกต์ และใช้ได้ครั้งเดียวยังอยู่ครบ
        รอบ FIXER: ต้องหลังกล่องอนุญาตดึง review ไปแสดงแล้ว (_view) — ดู test_token_alone_needs_card_view"""
        for i, extra in enumerate(({}, {"review": None}, {"review": ""}, {"review": "  \n\t "})):
            with self.subTest(extra=extra):
                _write(self.p, "one\n")
                tok = C.token_from_hint(self._edit_hint(new="v%d" % i))
                self.assertTrue(tok)
                _view(self.project, tok)
                out = rpc(self.project, "local_confirm", dict({"confirm_token": tok}, **extra))
                self.assertIn("แก้ไขแล้ว", out)
                self.assertEqual(_read(self.p), "v%d\n" % i)
                out = rpc(self.project, "local_confirm", {"confirm_token": tok})
                self.assertIn("ใช้ไม่ได้", out)                             # ใช้ได้ครั้งเดียวเหมือนเดิม
                self.assertEqual(_read(self.p), "v%d\n" % i)

    def test_token_alone_needs_card_view(self):
        """รอบ FIXER ของ S1/S2 (review อิสระ): เดิม token อย่างเดียวรันทันทีแม้ไม่มีใครเคยเห็น review — การ์ดที่โหลดไม่ได้/
        ยังโหลดอยู่ (ปุ่มอนุญาตแค่จาง) และแท็บรุ่นเก่าที่ไม่ดึง review กดอนุญาตแล้วรันได้ ตอนนี้ต้องมี GET /review จาก
        หน้าเว็บ (viewer) ก่อน: ไม่เคยเห็น = ปฏิเสธ token ยังอยู่ ครั้งแรกบอกให้ลองใหม่ทันที ครั้งต่อไปบอกให้รีโหลดหน้า"""
        tok = C.token_from_hint(self._edit_hint())
        for extra in ({}, {"review": None}, {"review": " \n"}):
            out = rpc(self.project, "local_confirm", dict({"confirm_token": tok}, **extra))
            self.assertTrue(out.startswith("ยังไม่ได้ทำอะไร: "), out[:80])
            # ป้ายของหน้าแชต: "...: review " = review ไม่ตรง — กรณีนี้ต้องไม่ใช่ป้ายนั้น (เป็น "ถูกปฏิเสธ")
            self.assertFalse(out.startswith("ยังไม่ได้ทำอะไร: review "), out[:80])
            self.assertIn("กล่อง \"อนุญาต\"", out)
            self.assertIn("token ยังใช้ได้", out)
            self.assertEqual(_read(self.p), "one\n")
        other = rpc(_slug("unused"), "local_confirm", {"confirm_token": tok})    # โปรเจกต์อื่น = ใช้ไม่ได้ ไม่นับ
        self.assertIn("ใช้ไม่ได้", other)
        # ข้อความตามจำนวนครั้ง: ครั้งแรกให้ลองใหม่ทันที ครั้งต่อไปให้หยุดแล้วบอกผู้ใช้รีโหลดหน้า
        tok2 = C.token_from_hint(self._edit_hint(new="x2"))
        once = rpc(self.project, "local_confirm", {"confirm_token": tok2})
        self.assertIn('local_confirm(confirm_token="%s") ใหม่ทันที' % tok2, once)
        self.assertIn("ไม่ต้องถามผู้ใช้ใหม่", once)
        twice = rpc(self.project, "local_confirm", {"confirm_token": tok2})
        self.assertIn("หยุดเรียก", twice)
        self.assertIn("รีโหลดหน้าแชต", twice)
        self.assertNotIn("ใหม่ทันที", twice)
        # อ่านแบบไม่ใช่หน้าเว็บ (viewer=False — สคริปต์ในเครื่อง) ไม่นับว่าคนเห็น
        self.assertEqual(server.review_lookup(self.project, "token=" + tok)[0], 200)
        self.assertIn("ยังไม่ได้ทำอะไร", rpc(self.project, "local_confirm", {"confirm_token": tok}))
        # ดึงจากโปรเจกต์อื่นไม่ได้ และไม่จด viewed ให้ token ของโปรเจกต์นี้
        self.assertEqual(server.review_lookup(_slug("rv-other"), "token=" + tok, viewer=True)[0], 404)
        self.assertIn("ยังไม่ได้ทำอะไร", rpc(self.project, "local_confirm", {"confirm_token": tok}))
        self.assertEqual(_read(self.p), "one\n")
        with guard._lock:
            self.assertIn(tok, guard._pending, "ปฏิเสธแล้ว token ต้องยังอยู่")
        # กล่องอนุญาตดึง review ไปแสดงแล้ว -> token อย่างเดียวรันได้หนึ่งครั้ง
        _view(self.project, tok)
        out = rpc(self.project, "local_confirm", {"confirm_token": tok})
        self.assertIn("แก้ไขแล้ว", out)
        self.assertEqual(_read(self.p), "two\n")
        self.assertIn("ใช้ไม่ได้", rpc(self.project, "local_confirm", {"confirm_token": tok}))

    def test_matching_review_does_not_need_card_view(self):
        """review ที่ส่งมาและตรงยังรันได้โดยไม่ต้องมี viewed (เหมือนก่อน S2 — การ์ดรุ่นเก่าแสดงข้อความนั้นให้คนเห็น)"""
        args = C.confirm_args(self._edit_hint())
        rpc(self.project, "local_confirm", args)
        self.assertEqual(_read(self.p), "two\n")

    def test_fenced_review_from_small_model_runs_first_time(self):
        """e2e จริง (audit 17:22:04): อาร์กิวเมนต์ review = '```review\\n...\\n```' เนื้อในตรง แต่ถูกปฏิเสธ -> คนกดสองครั้ง"""
        hint = self._edit_hint()
        self.assertRegex(hint, r"(?m)^```review$")
        args = C.confirm_args(hint)
        out = rpc(self.project, "local_confirm", dict(args, review="```review\n%s\n```" % args["review"]))
        self.assertIn("แก้ไขแล้ว", out)
        self.assertEqual(_read(self.p), "two\n")
        self.assertIn("ใช้ไม่ได้", rpc(self.project, "local_confirm", args))       # ใช้ได้ครั้งเดียวเหมือนเดิม
        # เนื้อในรั้วผิด = ยังปฏิเสธ token ยังอยู่
        _write(self.p, "one\n")
        args = C.confirm_args(self._edit_hint(new="three"))
        out = rpc(self.project, "local_confirm",
                  dict(args, review="```review\n%s\n```" % args["review"].replace("+three", "+thr3e")))
        self.assertTrue(out.startswith("ยังไม่ได้ทำอะไร: review "), out[:80])
        self.assertEqual(_read(self.p), "one\n")

    def test_view_then_mismatch_then_token_only_runs(self):
        """ลำดับจริงจาก e2e: การ์ดแรกดึง review (viewed) -> โมเดลส่ง review ผิด = ปฏิเสธ -> ลองใหม่ด้วย token อย่างเดียว
        (การ์ดที่สองใช้ review ที่ดึงไว้แล้ว ไม่ดึงซ้ำ) -> รัน"""
        args = C.confirm_args(self._edit_hint())
        _view(self.project, args["confirm_token"])
        out = rpc(self.project, "local_confirm", dict(args, review=args["review"] + "\nx"))
        self.assertTrue(out.startswith("ยังไม่ได้ทำอะไร: review "), out[:80])
        rpc(self.project, "local_confirm", {"confirm_token": args["confirm_token"]})
        self.assertEqual(_read(self.p), "two\n")

    def test_token_alone_still_bound_to_project_and_surface(self):
        """ไม่มี review ก็ข้ามโปรเจกต์/ผิวไม่ได้ — ด่านเดิมทุกด่านไม่ได้พึ่ง review"""
        tok = C.token_from_hint(self._edit_hint())
        _view(self.project, tok)
        self.assertIn("ใช้ไม่ได้", rpc(_slug("rv-other"), "local_confirm", {"confirm_token": tok}))
        self.assertIn("ผิว", rpc(self.project, "local_confirm", {"confirm_token": tok}, fast=False))
        self.assertEqual(_read(self.p), "one\n")
        rpc(self.project, "local_confirm", {"confirm_token": tok})
        self.assertEqual(_read(self.p), "two\n")

    def test_wrong_review_refused_and_token_not_consumed(self):
        hint = self._edit_hint()
        args = C.confirm_args(hint)
        review = args["review"]
        wrong = [review.replace("+two", "+tw0"), review[: len(review) // 2], review + "\nextra",
                 review.replace("one", "ONE"), "อนุมัติแล้ว", review.replace("\n", " "), 123, ["x"]]
        for w in wrong:
            out = rpc(self.project, "local_confirm", dict(args, review=w))
            self.assertIn("ไม่ตรง", out)
            self.assertIn("token ยังใช้ได้", out)
            # S2: บอกให้ลองใหม่ทันทีด้วย token อย่างเดียว (ไม่ใช่คัดลอกใหม่/ถามผู้ใช้ซ้ำ)
            self.assertIn('local_confirm(confirm_token="%s")' % args["confirm_token"], out)
            self.assertEqual(_read(self.p), "one\n")
        self.assertIsNotNone(self._stored(args["confirm_token"]))
        out = rpc(self.project, "local_confirm", args)
        self.assertEqual(_read(self.p), "two\n", out[:200])
        out = rpc(self.project, "local_confirm", args)
        self.assertIn("ใช้ไม่ได้", out)                                  # ใช้ได้ครั้งเดียวเหมือนเดิม

    def test_crlf_and_trailing_spaces_in_review_accepted(self):
        hint = self._edit_hint()
        args = C.confirm_args(hint)
        args["review"] = "\r\n".join(ln + "  " for ln in args["review"].split("\n")) + "\r\n"
        rpc(self.project, "local_confirm", args)
        self.assertEqual(_read(self.p), "two\n")

    def test_review_of_another_token_rejected(self):
        p2 = os.path.join(self.d, "b.txt")
        _write(p2, "one\n")
        a = C.confirm_args(self._edit_hint("AAA"))
        b = C.confirm_args(self._edit_hint("BBB", path=p2))
        out = rpc(self.project, "local_confirm", {"confirm_token": a["confirm_token"],
                                                  "review": b["review"]})
        self.assertIn("ไม่ตรง", out)
        self.assertEqual((_read(self.p), _read(p2)), ("one\n", "one\n"))
        rpc(self.project, "local_confirm", a)
        self.assertEqual((_read(self.p), _read(p2)), ("AAA\n", "one\n"))

    def test_guard_confirming_review_optional_but_checked_when_given(self):
        """ด่านซ้ำใน guard (กฎ S2 อยู่ที่เดียว): ไม่ส่ง review = เปิดช่องได้, ส่งมาแต่ไม่ตรง = ไม่เปิด แม้ผู้เรียกลืมตรวจ
        token ที่ไม่มีอยู่/หมดอายุเปิดช่องไม่ได้ไม่ว่ากรณีใด"""
        for absent in (None, "", "  \n\t"):
            self.assertFalse(guard.review_provided(absent), repr(absent))
        for given in ("x", 0, [], ["x"], {"a": 1}):
            self.assertTrue(guard.review_provided(given), repr(given))
        with guard.project_scope(self.project):
            tok = guard.need_confirm("exec", "defence-in-depth")
            for bad in ("nope", guard.pending_review(tok) + "x", 123, ["x"]):
                with guard.confirming(tok, bad) as opened:
                    self.assertFalse(opened, repr(bad))
                    self.assertFalse(guard.consume_confirm(tok, "exec", "defence-in-depth"))
            with guard.confirming("deadbeef", None) as opened:
                self.assertFalse(opened, "token ที่ไม่มีอยู่ต้องไม่เปิดช่อง")
            # รอบ FIXER: ไม่ส่ง review = ต้องเคยถูกกล่องอนุญาตดึงไปแสดง (viewed) — ด่านซ้ำอยู่ที่ guard ด้วย
            for absent in (None, "", " \n"):
                with guard.confirming(tok, absent) as opened:
                    self.assertFalse(opened, "ยังไม่มีใครเห็น review ต้องไม่เปิดช่อง: %r" % (absent,))
                    self.assertFalse(guard.consume_confirm(tok, "exec", "defence-in-depth"))
            self.assertFalse(guard.pending_viewed(tok))
            self.assertIsNotNone(guard.pending_view(tok))                 # อ่านเฉยๆ (ไม่ใช่กล่องอนุญาต) ไม่จด
            self.assertFalse(guard.pending_viewed(tok))
            self.assertIsNotNone(guard.pending_view(tok, mark_viewed=True))
            self.assertTrue(guard.pending_viewed(tok))
            with guard.confirming(tok, None) as opened:
                self.assertTrue(opened)
                self.assertTrue(guard.consume_confirm(tok, "exec", "defence-in-depth"))
            tok2 = guard.need_confirm("exec", "d2")
            with guard.confirming(tok2, guard.pending_review(tok2)) as opened:
                self.assertTrue(opened)
                self.assertTrue(guard.consume_confirm(tok2, "exec", "d2"))
            tok3 = guard.need_confirm("exec", "d3")
            with guard._lock:
                guard._pending[tok3]["exp"] = time.time() - 1
            with guard.confirming(tok3, None) as opened:
                self.assertFalse(opened, "token หมดอายุต้องไม่เปิดช่อง")
                self.assertFalse(guard.consume_confirm(tok3, "exec", "d3"))

    def test_wrong_channel_reply_carries_review(self):
        hint = self._edit_hint()
        tok = C.token_from_hint(hint)
        out = rpc(self.project, "local_do", {"action": "edit", "path": self.p, "old": "one",
                                             "new": "two", "confirm_token": tok})
        self.assertEqual(C.review_from_hint(out), C.review_from_hint(hint))
        self.assertEqual(_read(self.p), "one\n")

    def test_audit_logs_review_length_only(self):
        marker = "AUDIT-REVIEW-MARK-%s" % os.urandom(4).hex()
        hint = self._edit_hint(new=marker)
        rpc(self.project, "local_confirm", C.confirm_args(hint))
        self.assertEqual(_read(self.p), marker + "\n")
        with open(C.AUDIT_LOCAL, encoding="utf-8") as fh:
            log = fh.read()
        self.assertNotIn(marker, log)
        rows = [json.loads(x) for x in log.splitlines() if '"local_confirm"' in x and '"call"' in x]
        self.assertTrue(rows)
        self.assertTrue(all(str(r["args"].get("review", "<")).startswith("<") for r in rows))

    def test_service_token_scrubbed_consistently(self):
        """ผลของเครื่องมือผ่าน secrets_util.scrub เสมอ — review ที่เก็บต้องถูกล้างแบบเดียวกัน
        ไม่งั้นโมเดลเห็นแต่ *** แล้วคัดลอกกลับมาไม่มีทางตรง (ยืนยันไม่ได้เลย) และค่าจริงต้องไม่หลุดไปในแชต"""
        p = os.path.join(self.d, "notes.txt")
        _write(p, "old\n")
        hint = rpc(self.project, "local_do", {"action": "write", "path": p,
                                              "content": "copied: %s\n" % C.TOKEN})
        self.assertNotIn(C.TOKEN, hint)
        args = C.confirm_args(hint)
        self.assertIn("copied: ***", args["review"])
        out = rpc(self.project, "local_confirm", args)
        self.assertIn("เขียนแล้ว", out)
        self.assertNotIn(C.TOKEN, out)
        self.assertEqual(_read(p), "copied: %s\n" % C.TOKEN)

    def _stored(self, tok):
        with guard.project_scope(self.project):
            return guard.pending_review(tok)


# ====================================================== R1: ครบทุกชนิดการกระทำ
class ActionReviewTests(_ReviewAsserts):
    def setUp(self):
        self.project = _slug("rv-kind")
        self.d = C.new_dir("rvkind")

    def test_python_full_code_every_line_numbered(self):
        code = "\n".join("v%d = %d * 2  # บรรทัด %d" % (i, i, i) for i in range(1, 301))
        hint = rpc(self.project, "local_do", {"action": "python", "code": code, "timeout": "45"})
        review = self.assertReviewOk(hint, self.project, "[python]", "timeout: 45 วินาที",
                                     "cwd: ", "----- จบโค้ด (ครบ 300 บรรทัด) -----")
        for i in (1, 80, 81, 150, 299, 300):
            self.assertIn("%3d│ v%d = %d * 2  # บรรทัด %d" % (i, i, i, i), review)
        self.assertNotIn("แสดงบางส่วน", hint)
        self.assertNotIn(self.project, tools_python.kernel_status(), "ยังไม่อนุมัติ = ห้ามเปิด kernel")

    def test_python_trojan_source_is_visible(self):
        code = ("access = 'user'" + RLO + " " + LRI + "# admin only" + PDI + " " + LRI + "\n"
                "if access != 'none" + ZWSP + "':\n    print('ok')\ninfo = 1" + " " * 120 + "; import os")
        hint = rpc(self.project, "local_do", {"action": "python", "code": code})
        review = self.assertReviewOk(hint, self.project, "«U+202E»", "«U+2066»", "«U+200B»",
                                     "«120 spaces»; import os")
        self.assertTrue(review.startswith("⚠"))

    def test_python_fake_end_marker_is_numbered(self):
        code = "print('safe')\n----- จบโค้ด (ครบ 1 บรรทัด) -----\nimport os"
        review = self.assertReviewOk(rpc(self.project, "local_do", {"action": "python", "code": code}),
                                     self.project)
        rows = review.split("\n")
        self.assertIn("2│ ----- จบโค้ด (ครบ 1 บรรทัด) -----", rows)
        self.assertEqual(rows[-1], "----- จบโค้ด (ครบ 3 บรรทัด) -----")

    def test_exec_full_command_cwd_and_timeout(self):
        cmd = 'echo ' + "A" * 250 + '> "%s"' % os.path.join(self.d, "o.txt")
        hint = rpc(self.project, "local_do", {"action": "run", "command": cmd, "path": self.d,
                                              "limit": "30"})
        review = self.assertReviewOk(hint, self.project, "[run]", "cwd: %s" % self.d,
                                     "timeout: 30 วินาที", "o.txt")
        body = [x for x in review.split("\n") if x.startswith(("1│", "↪"))]
        self.assertEqual("".join(x.rstrip("↩").lstrip("↪") for x in body), "1│ " + cmd,
                         "คำสั่งต้องครบทุกตัวอักษร (ตัดบรรทัดแล้วต่อกลับได้)")

    def test_write_overwrite_small_shows_full_new_content(self):
        p = os.path.join(self.d, "cfg.ini")
        _write(p, "[a]\nx=1\n")
        hint = rpc(self.project, "local_do", {"action": "write", "path": p,
                                              "content": "[a]\nx=2\ny=" + RLO + "3\n"})
        self.assertReviewOk(hint, self.project, "[write]", "path: %s" % p, "1│ [a]", "2│ x=2",
                            "3│ y=«U+202E»3", "sha256 ", "----- จบเนื้อหา (ครบ 3 บรรทัด) -----")

    def test_write_new_script_shows_full_content(self):
        p = os.path.join(self.d, "run_me.py")
        hint = rpc(self.project, "local_do", {"action": "write", "path": p,
                                              "content": "import os\nos.system('dir')\n"})
        self.assertReviewOk(hint, self.project, "สร้างไฟล์สคริปต์", "1│ import os", "2│ os.system('dir')")
        self.assertFalse(os.path.exists(p))

    def test_write_large_overwrite_diff_capped_with_hash(self):
        p = os.path.join(self.d, "big.txt")
        _write(p, "".join("old %d\n" % i for i in range(600)))
        content = "".join("new %d\n" % i for i in range(600))
        hint = rpc(self.project, "local_do", {"action": "write", "path": p, "content": content})
        review = self.assertReviewOk(hint, self.project, "unified diff", "sha256 ")
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        m = re.search(r"\(ไม่แสดงอีก (\d+) บรรทัด — (\d+) more lines not shown — content hash "
                      r"sha256:([0-9a-f]{16})…\)", review)
        self.assertTrue(m, review[-400:])
        self.assertEqual(m.group(3), sha[:16])
        total = len(tools_files._review_diff("".join("old %d\n" % i for i in range(600)), content, p))
        rows = review.split("\n")
        start = next(i for i, x in enumerate(rows) if x.startswith("===== "))
        end = rows.index("===== จบ diff =====")
        shown = [x for x in rows[start + 1:end] if not x.startswith("(ไม่แสดงอีก")]
        self.assertLessEqual(len(shown), guard.REVIEW_BLOCK_MAX_LINES)
        self.assertEqual(int(m.group(1)), total - len(shown))
        self.assertLessEqual(len(review.split("\n")), guard.REVIEW_MAX_LINES)

    def test_write_large_new_script_refused_before_token(self):
        """FIXER (R3 ขยายถึงไฟล์สคริปต์): เดิมได้ token โดย review แสดงแค่ 400 บรรทัดแรก โค้ดหลังเพดานถูกเขียนลง
        ไฟล์ที่รันได้โดยไม่มีใครเห็น (probe2: MARKER_AFTER_CAP ไม่อยู่ใน review) — ตอนนี้ปฏิเสธก่อนออก token"""
        for name in ("gen.py", "run.bat", "tool.ps1"):
            with self.subTest(name=name):
                p = os.path.join(self.d, name)
                content = "".join("print(%d)\n" % i for i in range(1200)) + "print('MARKER_AFTER_CAP')\n"
                out = rpc(self.project, "local_do", {"action": "write", "path": p, "content": content})
                self.assertTrue(out.startswith("ปฏิเสธ"), out[:200])
                self.assertIn("แบ่ง", out)
                self.assertNotIn("confirm_token=", out)
                self.assertEqual(_pending_count(self.project), 0)
                self.assertFalse(os.path.exists(p))
        # ยาวเท่าเพดานพอดี (แสดงครบ) ยังได้ token ตามปกติ
        p = os.path.join(self.d, "ok.py")
        content = "".join("x%d = 1\n" % i for i in range(guard.REVIEW_BLOCK_MAX_LINES))
        self.assertReviewOk(rpc(self.project, "local_do", {"action": "write", "path": p, "content": content}),
                            self.project, "%d│ x%d = 1" % (guard.REVIEW_BLOCK_MAX_LINES,
                                                           guard.REVIEW_BLOCK_MAX_LINES - 1))

    def test_write_large_script_overwrite_needs_complete_diff(self):
        """ทับไฟล์สคริปต์ใหญ่: diff ที่แสดงได้ครบ = ได้ token / diff ที่ต้องตัด = ปฏิเสธ"""
        p = os.path.join(self.d, "big_tool.py")
        old = ["v%d = %d\n" % (i, i) for i in range(1000)]
        _write(p, "".join(old))
        small = old[:]
        small[500] = "v500 = 'changed'\n"
        review = self.assertReviewOk(rpc(self.project, "local_do",
                                         {"action": "write", "path": p, "content": "".join(small)}),
                                     self.project, "unified diff", "+v500 = 'changed'", "-v500 = 500")
        self.assertNotIn("more lines not shown", review)
        whole = ["w%d = %d\n" % (i, i) for i in range(1000)]
        out = rpc(self.project, "local_do", {"action": "write", "path": p, "content": "".join(whole)})
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:200])
        self.assertNotIn("confirm_token=", out)
        self.assertEqual(_read(p), "".join(old))

    def test_edit_script_with_huge_insertion_refused_text_file_capped(self):
        body = "".join("print(%d)\n" % i for i in range(600))
        py = os.path.join(self.d, "e.py")
        _write(py, "# top\n")
        out = rpc(self.project, "local_do", {"action": "edit", "path": py, "old": "# top", "new": body})
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:200])
        self.assertNotIn("confirm_token=", out)
        txt = os.path.join(self.d, "e.txt")
        _write(txt, "# top\n")
        self.assertReviewOk(rpc(self.project, "local_do", {"action": "edit", "path": txt, "old": "# top",
                                                           "new": body}),
                            self.project, "more lines not shown")

    def test_write_overwrite_token_bound_to_current_file_content(self):
        """FIXER (probe3): review ของการทับไฟล์ใหญ่คือ diff เทียบไฟล์ตอนออก token — ไฟล์ถูกแก้หลังจากนั้น
        ต้องทำให้ token ใช้ไม่ได้ ไม่งั้นการยืนยันทับการแก้ที่ไม่เคยอยู่ใน diff ทิ้งเงียบๆ"""
        p = os.path.join(self.d, "big.txt")
        lines = ["line %d\n" % i for i in range(1500)]
        _write(p, "".join(lines))
        new = lines[:]
        new[10] = "EDITED 10\n"
        args = C.confirm_args(rpc(self.project, "local_do", {"action": "write", "path": p,
                                                             "content": "".join(new)}))
        self.assertTrue(args["confirm_token"])
        later = lines[:]
        later[900] = "USER_EDIT_AFTER_TOKEN\n"
        _write(p, "".join(later))
        out = rpc(self.project, "local_confirm", args)
        self.assertNotIn("เขียนแล้ว", out)
        self.assertIn("ใช้ไม่ได้", out)
        self.assertIn("USER_EDIT_AFTER_TOKEN", _read(p), "การแก้ของผู้ใช้ต้องไม่ถูกทับ")
        # ขอใหม่ (review ใหม่เทียบไฟล์ปัจจุบัน) แล้วยืนยันได้ตามปกติ
        args = C.confirm_args(rpc(self.project, "local_do", {"action": "write", "path": p,
                                                             "content": "".join(new)}))
        self.assertIn("-USER_EDIT_AFTER_TOKEN", args["review"])
        rpc(self.project, "local_confirm", args)
        self.assertEqual(_read(p), "".join(new))

    def test_edit_shows_path_and_unified_diff(self):
        p = os.path.join(self.d, "e.txt")
        _write(p, "a\nb\nc\n")
        self.assertReviewOk(rpc(self.project, "local_do", {"action": "edit", "path": p,
                                                           "old": "b", "new": "B" + ZWJ}),
                            self.project, "[edit]", "path: %s" % p, "-b", "+B«U+200D»",
                            "===== จบ diff =====")

    def test_undo_shows_diff(self):
        p = os.path.join(self.d, "u.txt")
        _write(p, "keep\n")
        with guard.project_scope(self.project):
            tok = C.token_from_hint(tools_files.write_file(p, "oops\n"))
            with C.confirming(guard, tok):
                tools_files.write_file(p, "oops\n", confirm_token=tok)
        self.assertReviewOk(rpc(self.project, "local_do", {"action": "undo", "path": p}),
                            self.project, "[undo]", "path: %s" % p, "-oops", "+keep")

    def test_make_file_overwrite_shows_normalised_parameters(self):
        args = {"action": "make_file", "format": "md", "name": "rep", "content": "v1"}
        self.assertIn("สร้างไฟล์แล้ว", rpc(self.project, "local_do", args))
        self.assertReviewOk(rpc(self.project, "local_do", dict(args, content="v2")), self.project,
                            "[make_file]", "format: md", "rep.md", "content 2 ตัวอักษร", "1│ v2")

    def test_make_file_overwrite_shows_content_so_equal_lengths_differ(self):
        """FIXER: เดิมเห็นแค่ความยาว + hash 16 ตัว — ทับด้วย A หรือ B ที่ยาวเท่ากันดูเหมือนกันทุกอย่าง"""
        args = {"action": "make_file", "format": "md", "name": "same", "content": "# start"}
        rpc(self.project, "local_do", args)
        ra = self.assertReviewOk(rpc(self.project, "local_do", dict(args, content="# AAAA\nsafe")),
                                 self.project, "1│ # AAAA", "2│ safe")
        rb = self.assertReviewOk(rpc(self.project, "local_do", dict(args, content="# BBBB\nevil")),
                                 self.project, "1│ # BBBB", "2│ evil")
        self.assertNotEqual(ra, rb)
        csv_args = {"action": "make_file", "format": "csv", "name": "t",
                    "spec": json.dumps({"sheets": [{"name": "s", "rows": [["a", "b"], [1, 2]]}]})}
        first = rpc(self.project, "local_do", csv_args)
        if "สร้างไฟล์แล้ว" not in first:
            self.skipTest("spec csv รูปแบบนี้ไม่รองรับ: %s" % first[:160])
        spec2 = json.dumps({"sheets": [{"name": "s", "rows": [["a", "b"], [3, 4]]}]})
        review = self.assertReviewOk(rpc(self.project, "local_do", dict(csv_args, spec=spec2)),
                                     self.project, "spec (JSON", "----- จบ spec")
        self.assertIn("3", review)
        big = "\n".join("บรรทัด %d" % i for i in range(3000))
        review = self.assertReviewOk(rpc(self.project, "local_do", dict(args, content=big)), self.project,
                                     "more lines not shown")
        self.assertLessEqual(len(review.split("\n")), guard.REVIEW_BLOCK_MAX_LINES + 20)

    def test_media_overwrite_shows_parameters(self):
        out = os.path.join(self.d, "clip.mp4")
        _write(out, "old")
        tools_media._CTX.token = ""
        tools_media._CTX.op = json.dumps({"tool": "media_trim", "path": "in.mp4", "out": out,
                                          "start": "0", "duration": "5"}, sort_keys=True)
        with guard.project_scope(self.project):
            with self.assertRaises(ValueError) as cm:
                tools_media._write_path(out, True)
        self.assertReviewOk(str(cm.exception), self.project, "[media]", "ไฟล์ที่จะถูกแทนที่: ",
                            "เครื่องมือ: media_trim", 'duration = "5"', 'out = ')

    def test_task_start_shows_argv(self):
        with guard.project_scope(self.project):
            hint = tools_tasks.task_start(command='"%s" -c "print(1)"' % sys.executable, cwd=self.d)
        self.assertReviewOk(hint, self.project, "[task_start]", "cwd: %s" % self.d,
                            "[0] %s" % json.dumps(sys.executable), '[1] "-c"', '[2] "print(1)"')

    def test_task_start_argv_with_newline_stays_on_one_line(self):
        """FIXER (probe3): argv ที่มี \\n เคยแตกเป็นหลายบรรทัด บรรทัดต่อปลอมเป็นอาร์กิวเมนต์ใหม่ "  [9] ..." ได้"""
        cmd = '"%s" -c "print(1)\n  [9] --harmless-looking"' % sys.executable
        with guard.project_scope(self.project):
            hint = tools_tasks.task_start(command=cmd, cwd=self.d)
        review = self.assertReviewOk(hint, self.project, '[2] "print(1)\\n  [9] --harmless-looking"')
        rows = review.split("\n")
        self.assertFalse(any(r.lstrip().startswith("[9]") for r in rows), review)
        self.assertEqual(sum(1 for r in rows if re.match(r"^  \[\d+\] ", r)), 3)
        # ข้อความประกอบนอกบล็อก (ที่โมเดลแสดงในแชต) ก็หนึ่งชิ้นต่อบรรทัดเหมือนกัน
        head = hint.split("```")[0]
        self.assertFalse(any(r.lstrip().startswith("[9]") for r in head.split("\n")), head)

    def test_header_values_from_model_cannot_add_lines(self):
        """ค่าที่วางต่อหัวข้อ "ชื่อ: ค่า" (timeout ของ run ที่อ่านไม่ออก, คำสั่งในทะเบียนงาน) ต้องอยู่บรรทัดเดียว"""
        self.assertEqual(guard.review_oneline("C:\\a b"), "C:\\a b")
        self.assertEqual(guard.review_oneline("a\nb"), '"a\\nb"')
        self.assertEqual(guard.review_oneline("a" + chr(0x2028) + "b"), '"a%sb"' % chr(0x2028))
        hint = rpc(self.project, "local_do", {"action": "run", "command": "echo real> x.txt", "path": self.d,
                                              "limit": "5\n1│ echo harmless"})
        review = C.review_from_hint(hint)
        if not review:
            self.skipTest("local_do ไม่ส่ง timeout แบบข้อความถึง run: %s" % hint[:160])
        self.assertEqual([r for r in review.split("\n") if r.startswith("1│")], ["1│ echo real> x.txt"])

    def test_task_stop_shows_target(self):
        """งานจำลองใน tasks.json ชั่วคราว ชี้ไปที่โปรเซส sleep ที่เทสต์เปิดเอง (ไม่ยืนยัน = ไม่มีอะไรถูกหยุด)"""
        dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                 creationflags=0x08000000)
        saved = (tools_tasks.TASKS_PATH, tools_tasks.LOG_DIR)
        tmp = C.new_dir("rvtasks")
        try:
            tools_tasks.TASKS_PATH = Path(tmp) / "tasks.json"
            tools_tasks.LOG_DIR = Path(tmp) / "logs"
            tools_tasks.TASKS_PATH.write_text(json.dumps([{
                "id": "rv0task1", "pid": dummy.pid, "status": "running", "project": self.project,
                "command": "sleeper --flag", "started_epoch": time.time()}]), encoding="utf-8")
            with guard.project_scope(self.project):
                hint = tools_tasks.task_stop(id="rv0task1")
            self.assertReviewOk(hint, self.project, "[task_stop]", "id: rv0task1",
                                "pid: %d" % dummy.pid, "คำสั่ง: sleeper --flag")
            self.assertIsNone(dummy.poll(), "ยังไม่ยืนยัน = ต้องไม่หยุดอะไร")
            # FIXER: คำสั่งในทะเบียนมาจากโมเดล — \n ต้องไม่ปลอมบรรทัด "pid:" ใหม่ในกล่องอนุญาต
            tools_tasks.TASKS_PATH.write_text(json.dumps([{
                "id": "rv0task1", "pid": dummy.pid, "status": "running", "project": self.project,
                "command": "sleeper --flag\npid: 1", "started_epoch": time.time()}]), encoding="utf-8")
            with guard.project_scope(self.project):
                hint = tools_tasks.task_stop(id="rv0task1")
            review = self.assertReviewOk(hint, self.project, 'คำสั่ง: "sleeper --flag\\npid: 1"')
            self.assertEqual([r for r in review.split("\n") if r.startswith("pid:")], ["pid: %d" % dummy.pid])
        finally:
            tools_tasks.TASKS_PATH, tools_tasks.LOG_DIR = saved
            dummy.kill()
            dummy.wait(10)

    def test_browser_open_shows_full_url(self):
        """โปรไฟล์ชี้ไป temp (ไม่สร้างโฟลเดอร์ใน C:\\LLM\\browser-profile จริง) และไม่ยืนยัน = ไม่เปิดเบราว์เซอร์"""
        url = "http://1.1.1.1/cb?code=SHOW-ME-%s&x=1" % os.urandom(2).hex()
        saved = tools_browser.PROFILE_ROOT
        tools_browser.PROFILE_ROOT = C.new_dir("rvprofiles")
        try:
            with guard.project_scope(self.project):
                hint = tools_browser.browser_open(project=self.project, url=url)
        finally:
            tools_browser.PROFILE_ROOT = saved
        if C.token_from_hint(hint) == "":
            self.skipTest("เปิดขั้นขอยืนยันไม่ได้บนเครื่องนี้ (ไม่มีเบราว์เซอร์?): %s" % hint[:160])
        self.assertReviewOk(hint, self.project, "[browser_open]", "URL เต็ม: %s" % url, "allow_local: False")

    def test_allow_local_fetch_shows_full_url(self):
        url = "http://127.0.0.1:9/p?k=VISIBLE-%s" % os.urandom(2).hex()
        with guard.project_scope(self.project):
            hint = tools_browser.browser_fetch(project=self.project, url=url, allow_local=True)
        self.assertReviewOk(hint, self.project, "allow_local=true", "URL เต็ม: %s" % url)

    def test_scheduler_gets_default_review(self):
        with guard.project_scope(self.project):
            hint = scheduler.schedule_run(job="heartbeat")
        self.assertReviewOk(hint, self.project, "[schedule_run:heartbeat]", "heartbeat")

    def test_every_need_confirm_caller_passes_or_defaults_review(self):
        """เครื่องมือที่ออก token ทุกตัวในโฟลเดอร์ MCP ต้องสร้าง review เอง (ยกเว้น scheduler ที่ใช้ค่าเริ่มต้น)"""
        src_dir = Path(C.MCP_LOCAL)
        for f in sorted(src_dir.glob("*.py")):
            if f.name in ("guard.py", "scheduler.py"):
                continue
            text = f.read_text(encoding="utf-8")
            for m in re.finditer(r"guard\.need_confirm\(", text):
                start = m.end() - 1                      # ตำแหน่งวงเล็บเปิด
                depth, end = 0, start
                for i in range(start, min(len(text), start + 2000)):
                    depth += text[i] == "("
                    depth -= text[i] == ")"
                    if depth == 0:
                        end = i
                        break
                with self.subTest(file=f.name, at=m.start()):
                    self.assertIn("review=", text[start:end + 1])


# ============================================================ R3: เพดาน
class CapTests(_ReviewAsserts):
    def setUp(self):
        self.project = _slug("rv-cap")

    def test_limits_are_small(self):
        self.assertEqual(guard.MAX_PENDING_PER_PROJECT, 5)
        self.assertLessEqual(guard.MAX_PENDING, 64)
        self.assertEqual(tools_python.REVIEW_MAX_LINES, 400)
        self.assertEqual(tools_python.REVIEW_MAX_CHARS, 20_000)

    def test_python_over_400_lines_refused_before_token(self):
        code = "\n".join("x%d = 1" % i for i in range(401))
        out = rpc(self.project, "local_do", {"action": "python", "code": code})
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:200])
        self.assertIn("แบ่ง", out)
        self.assertNotIn("confirm_token=", out)
        self.assertEqual(_pending_count(self.project), 0)

    def test_python_exactly_400_lines_allowed(self):
        code = "\n".join("x%d = 1" % i for i in range(400))
        hint = rpc(self.project, "local_do", {"action": "python", "code": code})
        self.assertReviewOk(hint, self.project, "400│ x399 = 1")

    def test_python_hidden_char_inflation_counts_after_escaping(self):
        code = "s = '" + ZWSP * 2600 + "'"          # ดิบ 2,606 ตัว แสดงผล 20,800+ ตัว
        self.assertLess(len(code), tools_python.REVIEW_MAX_CHARS)
        out = rpc(self.project, "local_do", {"action": "python", "code": code})
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:200])
        self.assertNotIn("confirm_token=", out)

    def test_python_long_lines_count_after_wrapping(self):
        self.assertEqual(guard.review_measure("y" * 1001)[0], 6)
        code = "\n".join("a%d = '%s'" % (i, "z" * 150) for i in range(130))   # ดิบ 130 บรรทัด ~21k ตัว
        out = rpc(self.project, "local_do", {"action": "python", "code": code})
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:200])

    def test_new_python_token_invalidates_older_python_token_only(self):
        d = C.new_dir("rvcap")
        p = os.path.join(d, "keep.txt")
        _write(p, "one\n")
        edit = C.confirm_args(rpc(self.project, "local_do", {"action": "edit", "path": p,
                                                             "old": "one", "new": "two"}))
        first = C.confirm_args(rpc(self.project, "local_do", {"action": "python", "code": "print('A')"}))
        second = C.confirm_args(rpc(self.project, "local_do", {"action": "python", "code": "print('B')"}))
        other = _slug("rv-cap-other")
        foreign = C.confirm_args(rpc(other, "local_do", {"action": "python", "code": "print('C')"}))
        out = rpc(self.project, "local_confirm", first)
        self.assertIn("ใช้ไม่ได้", out, "token python เก่าต้องถูกแทนด้วยตัวใหม่")
        with guard.project_scope(self.project):
            self.assertIsNotNone(guard.pending_review(second["confirm_token"]))
            self.assertIsNotNone(guard.pending_review(edit["confirm_token"]), "token ชนิดอื่นไม่ถูกแตะ")
        with guard.project_scope(other):
            self.assertIsNotNone(guard.pending_review(foreign["confirm_token"]), "โปรเจกต์อื่นไม่ถูกแตะ")
        rpc(self.project, "local_confirm", edit)
        self.assertEqual(_read(p), "two\n")

    def test_pending_tokens_capped_per_project(self):
        d = C.new_dir("rvcap5")
        other = _slug("rv-cap-keep")
        po = os.path.join(d, "other.txt")
        _write(po, "one\n")
        keep = C.confirm_args(rpc(other, "local_do", {"action": "edit", "path": po, "old": "one",
                                                      "new": "two"}))
        issued = []
        for i in range(7):
            p = os.path.join(d, "f%d.txt" % i)
            _write(p, "one\n")
            issued.append((p, C.confirm_args(rpc(self.project, "local_do",
                                                 {"action": "edit", "path": p, "old": "one",
                                                  "new": "two"}))))
        self.assertEqual(_pending_count(self.project), guard.MAX_PENDING_PER_PROJECT)
        for p, args in issued[:2]:
            self.assertIn("ใช้ไม่ได้", rpc(self.project, "local_confirm", args))
            self.assertEqual(_read(p), "one\n")
        for p, args in issued[2:]:
            rpc(self.project, "local_confirm", args)
            self.assertEqual(_read(p), "two\n")
        rpc(other, "local_confirm", keep)
        self.assertEqual(_read(po), "two\n", "เพดานของโปรเจกต์หนึ่งต้องไม่ทิ้ง token ของโปรเจกต์อื่น")

    def test_oversized_review_of_any_kind_is_refused(self):
        d = C.new_dir("rvbig")
        cmd = "echo " + "Q" * 60_000 + '> "%s"' % os.path.join(d, "x.txt")
        out = rpc(self.project, "local_do", {"action": "run", "command": cmd, "path": d})
        self.assertIn("ปฏิเสธ", out)
        self.assertNotIn("confirm_token=", out)
        with self.assertRaises(guard.ReviewTooLarge):
            guard.need_confirm("exec", "x", review="y\n" * (guard.REVIEW_MAX_LINES + 5))


# ============================================= รอบ FIXER: อักขระซ่อนครบชุด + homoglyph
# สำเนาอิสระจาก DerivedCoreProperties.txt ของ Unicode 15.1 (บรรทัด Default_Ignorable_Code_Point ทั้งหมด)
# ไม่อ่านค่าจาก guard เพื่อให้เทสต์จับได้ถ้าตารางใน guard ตกหล่น
_DI_SPEC = ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
            (0x180B, 0x180D), (0x180E, 0x180E), (0x180F, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E),
            (0x2060, 0x2064), (0x2065, 0x2065), (0x2066, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F),
            (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
            (0xE0000, 0xE0000), (0xE0001, 0xE0001), (0xE0002, 0xE001F), (0xE0020, 0xE007F),
            (0xE0080, 0xE00FF), (0xE0100, 0xE01EF), (0xE01F0, 0xE0FFF))
_ANACONDA_PY = os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), "anaconda3", "python.exe")


class HiddenCoverageTests(unittest.TestCase):
    def test_every_default_ignorable_code_point_is_escaped(self):
        """FIXER: U+180B-180D/180F (Mn กว้างศูนย์ ใส่ในชื่อตัวแปร Python ได้) เคยหลุดไปดิบๆ พร้อมไม่มีคำเตือน"""
        cps = [c for lo, hi in _DI_SPEC for c in range(lo, hi + 1)]
        self.assertEqual(len(cps), 4174)
        missed = []
        for cp in cps:
            r, st = guard.render_review("a%sb" % chr(cp))
            if chr(cp) in r or "«U+%04X»" % cp not in r or not r.startswith("⚠"):
                missed.append("U+%04X" % cp)
        self.assertEqual(missed, [])

    def test_mongolian_free_variation_selectors_in_identifiers(self):
        for cp in (0x180B, 0x180C, 0x180D, 0x180F):
            ident = "a" + chr(cp)
            self.assertTrue(ident.isidentifier(), "เป็นชื่อตัวแปรได้จริง = ชื่อที่หน้าตาเหมือน 'a'")
            r, st = guard.render_review("%s = 1\nprint(a)" % ident)
            self.assertIn("a«U+%04X» = 1" % cp, r)
            self.assertIn("Trojan Source", r.split("\n")[0])
            self.assertEqual(st["hidden"], 1)

    def test_table_matches_regex_oracle_if_available(self):
        """เทียบตาราง DI ใน guard กับ \\p{Default_Ignorable_Code_Point} ของโมดูล regex (anaconda) — ข้ามถ้าไม่มี"""
        if not os.path.isfile(_ANACONDA_PY):
            self.skipTest("ไม่มี anaconda")
        code = ("import regex,json\n"
                "s=''.join(chr(c) for c in range(0x110000) if not 0xD800<=c<=0xDFFF)\n"
                "print(json.dumps([ord(m.group()) for m in regex.finditer(r'\\p{Default_Ignorable_Code_Point}', s)]))")
        try:
            out = subprocess.run([_ANACONDA_PY, "-c", code], capture_output=True, text=True, timeout=120,
                                 env=C.clean_env(), creationflags=0x08000000)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest("เรียก anaconda ไม่ได้: %s" % exc)
        if out.returncode != 0:
            self.skipTest("ไม่มีโมดูล regex: %s" % out.stderr[-200:])
        oracle = set(json.loads(out.stdout))
        mine = {c for c in range(0x110000) if guard.is_default_ignorable(c)}
        self.assertEqual(sorted(oracle ^ mine), [])


class ConfusableTests(_ReviewAsserts):
    def test_mixed_script_word_is_escaped_with_warning(self):
        r, st = guard.render_review("pr%snt('ok')" % chr(0x0456))
        self.assertIn("pr«U+0456»nt('ok')", r)
        self.assertEqual((st["confusable"], st["hidden"]), (1, 0))
        self.assertIn("หน้าตาเหมือน", r.split("\n")[0])
        self.assertNotIn(chr(0x0456), r)

    def test_whole_lookalike_word_and_fullwidth_are_escaped(self):
        r, st = guard.render_review("%s = 1" % chr(0x0430))                   # ตัวแปร а ซีริลลิกตัวเดียว
        self.assertIn("«U+0430» = 1", r)
        r, st = guard.render_review("".join(chr(c) for c in (0xFF45, 0xFF58, 0xFF45, 0xFF43)) + "('x')")
        self.assertEqual(st["confusable"], 4)                                  # ｅｘｅｃ = exec หลัง NFKC
        r, st = guard.render_review("x = 1" + chr(0x212A))                    # เครื่องหมายเคลวิน = K
        self.assertEqual(st["confusable"], 1)

    def test_legitimate_text_is_not_flagged(self):
        for s in ("สวัสดีครับ print('ok') ภาษาไทย", "dt = 5  # Δt μs σ²", "привет мир", "café naïve",
                  "ค่า Δ = 3", "π ≈ 3.14", "日本語テキスト"):
            r, st = guard.render_review(s)
            self.assertEqual(st["confusable"], 0, s)
            self.assertEqual(r, s)

    def test_python_review_flags_homoglyph_code(self):
        project = _slug("rv-conf")
        code = "import os\nos.syst%sm('dir')" % chr(0x0435)
        review = self.assertReviewOk(rpc(project, "local_do", {"action": "python", "code": code}), project,
                                     "os.syst«U+0435»m('dir')")
        self.assertTrue(review.startswith("⚠"))

    def test_url_review_shows_punycode_host(self):
        url = "http://ex%smple.com/login" % chr(0x0430)
        lines = guard.review_url_lines(url)
        self.assertIn("โฮสต์แบบ punycode (IDNA): xn--exmple-4nf.com", lines)
        self.assertEqual(guard.review_url_lines("http://example.com/x"), ["โฮสต์ (host): example.com"])
        project = _slug("rv-url")
        with guard.project_scope(project):
            hint = tools_browser._local_confirmed("browser_fetch", project, url, True, "")
        self.assertReviewOk(hint, project, "xn--exmple-4nf.com", "ex«U+0430»mple.com")


# ============================================= รอบ FIXER: ขั้นลองใหม่เมื่อ review ไม่ตรง + อายุ token
class RetryFlowTests(_ReviewAsserts):
    def setUp(self):
        self.project = _slug("rv-retry")
        self.d = C.new_dir("rvretry")
        self.p = os.path.join(self.d, "a.txt")
        _write(self.p, "one\n")

    def _args(self, new="two"):
        return C.confirm_args(rpc(self.project, "local_do", {"action": "edit", "path": self.p,
                                                             "old": "one", "new": new}))

    def test_leading_space_from_small_model_is_accepted(self):
        """e2e จริง: Qwen3-4B ส่ง review ขึ้นต้นด้วย " [python]" / " [run]" ทุกครั้ง คนกดอนุญาตแล้วไม่มีอะไรรัน"""
        args = self._args()
        rpc(self.project, "local_confirm", dict(args, review=" " + args["review"] + "\n"))
        self.assertEqual(_read(self.p), "two\n")

    def test_padding_refused_and_token_kept(self):
        args = self._args()
        rows = args["review"].split("\n")
        padded = "\n".join([rows[0] + " " * 5000] + rows[1:])
        out = rpc(self.project, "local_confirm", dict(args, review=padded))
        self.assertIn("ไม่ตรง", out)
        self.assertIn("ช่องว่าง", out)
        self.assertEqual(_read(self.p), "one\n")
        rpc(self.project, "local_confirm", args)
        self.assertEqual(_read(self.p), "two\n")

    def test_refusal_names_difference_and_says_retry_now(self):
        """S2 (e2e จริง): หลัง review ไม่ตรง Qwen3-4B หันไปถามผู้ใช้ซ้ำแทนการลองใหม่ — คำตอบต้องบอกให้เรียกใหม่ทันที
        ด้วย token อย่างเดียว ไม่ต้องถามใหม่ (กล่องอนุญาตยังถามคนอีกครั้งทุกการเรียก)"""
        args = self._args()
        tok = args["confirm_token"]
        out = rpc(self.project, "local_confirm", dict(args, review=args["review"].replace("+two", "+tw0")))
        # หัวข้อความนี้คือสิ่งที่ป้าย "ไม่ได้รัน — review ไม่ตรง" ของหน้าแชตใช้จัดชนิด (confirmResultKind)
        self.assertTrue(out.startswith("ยังไม่ได้ทำอะไร: review "), out[:80])
        self.assertIn("จุดที่ไม่ตรง: บรรทัด", out)
        self.assertIn('"+two"', out)
        self.assertIn('local_confirm(confirm_token="%s")' % tok, out)
        self.assertIn("ใหม่ทันที", out)
        self.assertIn("ไม่ต้องส่ง review", out)
        self.assertIn("ไม่ต้องถามผู้ใช้ใหม่", out)
        self.assertIn("กล่อง \"อนุญาต\"", out)
        self.assertNotIn("แสดงบล็อก REVIEW", out)
        self.assertNotIn("คัดลอกทั้งบล็อก", out)
        self.assertEqual(C.review_from_hint(out), "", "ไม่แนบ review ให้คัดลอกซ้ำแล้ว — ให้ส่ง token อย่างเดียว")
        _view(self.project, tok)            # การ์ดอนุญาตดึง review ของเซิร์ฟเวอร์ไปแสดง (ในการใช้จริงเกิดตั้งแต่การ์ดแรก)
        rpc(self.project, "local_confirm", {"confirm_token": tok})
        self.assertEqual(_read(self.p), "two\n")

    def test_large_review_not_reattached(self):
        body = "".join("line %d %s\n" % (i, "x" * 40) for i in range(700))
        args = self._args(new=body)
        self.assertGreater(len(args["review"]), 6_000)
        out = rpc(self.project, "local_confirm", dict(args, review=args["review"][:-5]))
        self.assertIn("ไม่ตรง", out)
        self.assertNotIn("```review", out)
        self.assertLess(len(out), 3000)
        _view(self.project, args["confirm_token"])
        rpc(self.project, "local_confirm", {"confirm_token": args["confirm_token"]})
        self.assertTrue(_read(self.p).startswith("line 0 x"))

    def test_ttl_is_ten_minutes_and_hint_says_so(self):
        self.assertEqual(guard.CONFIRM_TTL, 600)
        hint = rpc(self.project, "local_do", {"action": "edit", "path": self.p, "old": "one", "new": "x"})
        self.assertIn("หมดอายุใน 10 นาที", hint)

    def test_mismatch_extends_expiry_with_total_cap(self):
        args = self._args()
        tok = args["confirm_token"]
        now = time.time()
        with guard._lock:
            guard._pending[tok]["exp"] = now + 10
        rpc(self.project, "local_confirm", dict(args, review="wrong"))
        with guard._lock:
            exp = guard._pending[tok]["exp"]
        self.assertGreaterEqual(exp, now + guard.CONFIRM_RETRY_TTL - 5, "ต้องต่อเวลาให้ลองใหม่ทัน")
        # ใกล้เพดานรวมแล้ว: ต่อได้ไม่เกิน issued + CONFIRM_TTL_MAX
        with guard._lock:
            guard._pending[tok]["issued"] = now - guard.CONFIRM_TTL_MAX + 20
            guard._pending[tok]["exp"] = now + 5
        rpc(self.project, "local_confirm", dict(args, review="wrong"))
        with guard._lock:
            exp = guard._pending[tok]["exp"]
        self.assertLessEqual(exp, now + 21)
        # หมดอายุแล้วต่อไม่ได้ และใช้ไม่ได้
        with guard._lock:
            guard._pending[tok]["exp"] = now - 1
        with guard.project_scope(self.project):
            self.assertEqual(guard.extend_confirm(tok), 0)
        self.assertIn("ใช้ไม่ได้", rpc(self.project, "local_confirm", args))
        self.assertEqual(_read(self.p), "one\n")

    def test_extend_is_scoped_to_project(self):
        args = self._args()
        with guard.project_scope(_slug("rv-other")):
            self.assertEqual(guard.extend_confirm(args["confirm_token"]), 0)


class CapConsistencyTests(_ReviewAsserts):
    def test_total_cap_small_but_fits_largest_allowed_blocks(self):
        """FIXER: เพดาน review รวมลดจาก 48,000 เป็น 26,000 (โมเดลต้องคัดลอกทั้งก้อนกลับมา) — ก้อนที่ใหญ่ที่สุด
        ที่เครื่องมือยอม (python 400 บรรทัด/20,000 ตัวอักษร + เลขบรรทัด + การตัดบรรทัด) ต้องยังออก token ได้"""
        self.assertLessEqual(guard.REVIEW_MAX_CHARS, 26_000)
        project = _slug("rv-capfit")
        wide = ["s%03d = '%s'" % (i, "q" * 189) for i in range(100)] + [""] * 100    # เลขบรรทัดดันให้ตัดบรรทัด
        narrow = ["n%03d = '%s'" % (i, "w" * 40) for i in range(400)]
        for code in ("\n".join(wide), "\n".join(narrow)):
            self.assertLessEqual(guard.review_measure(code)[1], tools_python.REVIEW_MAX_CHARS)
            hint = rpc(project, "local_do", {"action": "python", "code": code})
            n = len(guard.review_numbered(code))
            self.assertReviewOk(hint, project, "----- จบโค้ด (ครบ %d บรรทัด) -----" % n)


# ================================================= S1: มุมมอง review อ่านอย่างเดียว (ในโปรเซส)
class ReviewViewTests(_ReviewAsserts):
    """guard.pending_view + server.review_lookup — ขอบเขตโปรเจกต์, ไม่ใช้/ไม่ต่ออายุ token, ไม่คืนค่า token"""

    def setUp(self):
        self.project = _slug("rv-view")
        self.d = C.new_dir("rvview")
        self.p = os.path.join(self.d, "a.txt")
        _write(self.p, "one\n")

    def _hint(self, project=None, fast=True):
        if fast:
            return rpc(project or self.project, "local_do",
                       {"action": "edit", "path": self.p, "old": "one", "new": "two"})
        return rpc(project or self.project, "edit_file",
                   {"path": self.p, "old_string": "one", "new_string": "two"}, fast=False)

    def test_pending_view_scoped_and_read_only(self):
        hint = self._hint()
        tok = C.token_from_hint(hint)
        with guard._lock:
            exp0 = guard._pending[tok]["exp"]
        with guard.project_scope(self.project):
            v = guard.pending_view(tok)
            self.assertEqual(guard.pending_view(" %s\n" % tok), v)
            self.assertIsNone(guard.pending_view(""))
            self.assertIsNone(guard.pending_view(None))
            self.assertIsNone(guard.pending_view("deadbeef"))
        self.assertEqual(set(v), {"action", "review", "expires_in_s"})
        self.assertEqual(v["review"], C.review_from_hint(hint))
        self.assertTrue(v["action"].startswith("edit_file:"), v["action"])
        self.assertTrue(0 < v["expires_in_s"] <= guard.CONFIRM_TTL)
        with guard._lock:
            self.assertEqual(guard._pending[tok]["exp"], exp0, "อ่านแล้วต้องไม่ต่ออายุ")
        with guard.project_scope(_slug("rv-other")):
            self.assertIsNone(guard.pending_view(tok), "โปรเจกต์อื่นต้องไม่เห็น (ไม่บอกด้วยว่ามีอยู่)")
        self.assertIsNone(guard.pending_view(tok), "นอกขอบเขตโปรเจกต์ต้องไม่เห็น")
        with guard.project_scope(_slug("rv-other")):
            self.assertIsNone(guard.pending_view(tok, mark_viewed=True))
        with guard._lock:
            self.assertFalse(guard._pending[tok]["viewed"], "มุมมองของโปรเจกต์อื่น/แบบไม่จด ต้องไม่จด viewed")
            self.assertEqual(guard._pending[tok]["exp"], exp0)
        _view(self.project, tok)
        with guard._lock:
            self.assertEqual(guard._pending[tok]["exp"], exp0, "จด viewed แล้วก็ต้องไม่ต่ออายุ")
        rpc(self.project, "local_confirm", {"confirm_token": tok})
        self.assertEqual(_read(self.p), "two\n", "อ่านไปแล้ว token ยังใช้ได้ตามปกติ")
        with guard.project_scope(self.project):
            self.assertIsNone(guard.pending_view(tok), "ใช้แล้ว = ไม่มีอีก")

    def test_pending_view_expired_and_hidden_chars_in_action(self):
        tok = C.token_from_hint(self._hint())
        with guard._lock:
            guard._pending[tok]["exp"] = time.time() - 1
        with guard.project_scope(self.project):
            self.assertIsNone(guard.pending_view(tok))
            raw = guard.need_confirm("write_file:c:\\x\\a" + RLO + "b.txt", "d")
            v = guard.pending_view(raw)
        self.assertIn("«U+202E»", v["action"])
        self.assertNotIn(RLO, v["action"])

    def test_review_lookup_results(self):
        hint = self._hint()
        tok = C.token_from_hint(hint)
        status, body = server.review_lookup(self.project, "token=%s" % tok)
        self.assertEqual(status, 200, body)
        self.assertEqual(set(body), {"ok", "action", "review", "expires_in_s", "pending"})
        self.assertTrue(body["ok"] is True and body["pending"] is True)
        self.assertEqual(body["review"], C.review_from_hint(hint))
        self.assertNotIn("token", body)
        self.assertNotIn("confirm_token", body)
        # อีกผิวของโปรเจกต์เดียวกัน (/mcp) ก็อ่านได้ — การ์ดอนุญาตไม่รู้ว่า token มาจากผิวไหน
        tok_full = C.token_from_hint(self._hint(fast=False))
        status, body = server.review_lookup(self.project, "token=" + tok_full)
        self.assertEqual(status, 200, body)
        for query, code, reason in (("", 400, "missing_token"), ("token=", 400, "missing_token"),
                                    ("x=1", 400, "missing_token"), ("token=zz%20zz", 400, "bad_token"),
                                    ("token=" + "a" * 65, 400, "bad_token"),
                                    ("token=%s&token=%s" % (tok, tok), 400, "bad_token"),
                                    ("token=deadbeef", 404, "not_pending")):
            with self.subTest(query=query):
                self.assertEqual(server.review_lookup(self.project, query),
                                 (code, {"ok": False, "reason": reason}))
        self.assertEqual(server.review_lookup(_slug("rv-other"), "token=" + tok),
                         (404, {"ok": False, "reason": "not_pending"}))
        with guard._lock:
            self.assertIn(tok, guard._pending, "การอ่านไม่เผา token")

    def test_review_route_and_scope_parse(self):
        self.assertEqual(server.review_route("/review/abc?token=1"), "abc")
        self.assertEqual(server.review_route("/review/%E0%B8%97%E0%B8%94%E0%B8%AA%E0%B8%AD%E0%B8%9A/"), "ทดสอบ")
        self.assertEqual(server.review_route("/review/Some Proj?token=1"), guard.project_slug("Some Proj"))
        for p in ("/review", "/review/", "/review/a/b", "/mcp/abc", "/fast/abc", "/reviewx/abc"):
            self.assertIsNone(server.review_route(p), p)
        self.assertEqual(server.scope_of("/review/abc?token=1"), "abc")
        self.assertEqual(server.scope_of("/fast/abc"), "abc")
        self.assertEqual(server.scope_of("/review"), "default")

    def _rate_isolated(self):
        """ตัวนับเป็นของทั้งโปรเซส — เทสต์ที่ใช้เวลาสมมติต้องไม่ปนกับตัวนับของเทสต์อื่น (คืนค่าเดิมตอนจบ)"""
        with server._REVIEW_RATE_LOCK:
            saved = dict(server._REVIEW_RATE)
            server._REVIEW_RATE.clear()

        def restore():
            with server._REVIEW_RATE_LOCK:
                server._REVIEW_RATE.clear()
                server._REVIEW_RATE.update(saved)
        self.addCleanup(restore)

    def test_rate_limit_per_project(self):
        """ตัวนับแยกต่อโปรเจกต์ที่ hub รู้จัก (projects.json ของเทสต์: sec-http, proj-b) + default"""
        self._rate_isolated()
        slug, other = C.PROJECT_OF_ALLOWED_ORIGIN, "proj-b"
        t0 = 1_000_000.0
        for i in range(server.REVIEW_RATE_MAX):
            self.assertTrue(server._review_rate_ok(slug, now=t0 + i * 0.01), i)
        self.assertFalse(server._review_rate_ok(slug, now=t0 + 5))
        self.assertTrue(server._review_rate_ok(other, now=t0 + 5), "โปรเจกต์อื่นไม่โดนด้วย")
        self.assertTrue(server._review_rate_ok("default", now=t0 + 5), "default มีตัวนับของตัวเอง")
        self.assertTrue(server._review_rate_ok(slug, now=t0 + server.REVIEW_RATE_WINDOW + 1), "พ้นหน้าต่างแล้วใช้ได้อีก")
        self.assertLessEqual(server.REVIEW_RATE_MAX, 300, "จำกัดแบบพอประมาณ")

    def test_rate_limit_cannot_be_reset_by_slug_churn(self):
        """รอบ FIXER (review อิสระ): เดิมตารางเต็ม 256 slug แล้วทิ้งตัวที่เงียบนานสุด — ยิง slug ใหม่ 256+ ตัว (ผู้ถือ Bearer
        ที่ไม่มี Origin หรือ Origin 8099/8100) ไล่ตัวนับของเป้าหมายที่ถูกจำกัดอยู่ออก แล้วได้อีก 120 ครั้งในนาทีเดียวกัน"""
        self._rate_isolated()
        target = "proj-b"
        t0 = 2_000_000.0
        allowed = sum(1 for i in range(200) if server._review_rate_ok(target, now=t0 + i * 0.001))
        self.assertEqual(allowed, server.REVIEW_RATE_MAX)
        for i in range(server._REVIEW_RATE_SLUGS_MAX * 2):
            server._review_rate_ok("churn-%d" % i, now=t0 + 1 + i * 0.0001)
        again = sum(1 for i in range(200) if server._review_rate_ok(target, now=t0 + 2 + i * 0.001))
        self.assertEqual(again, 0, "ตัวนับที่ยังอยู่ในหน้าต่างต้องไม่ถูกไล่ออก/รีเซ็ต")
        # slug ที่ไม่รู้จักทุกตัวใช้ตัวนับกองกลางตัวเดียว — ตารางไม่โตตามจำนวน slug ที่สุ่มมา
        self.assertLessEqual(len(server._REVIEW_RATE), 3)
        self.assertEqual(server._review_rate_key("churn-1"), server._review_rate_key("อื่นๆ"))
        self.assertNotIn(server._review_rate_key("churn-1"), (target, "default", C.PROJECT_OF_ALLOWED_ORIGIN))
        self.assertFalse(server._review_rate_ok("churn-new", now=t0 + 3), "กองกลางเต็มแล้ว = slug สุ่มตัวใหม่ก็โดน")
        self.assertTrue(server._review_rate_ok(C.PROJECT_OF_ALLOWED_ORIGIN, now=t0 + 3),
                        "กองกลางเต็มไม่กระทบหน้าโปรเจกต์จริง")
        # ตัวนับที่หมดหน้าต่างแล้วถูกเก็บกวาดได้ (ไม่เปลี่ยนผลการนับ) — ตัวที่ยังนับอยู่ไม่ถูกแตะ
        later = t0 + server.REVIEW_RATE_WINDOW + 10
        self.assertTrue(server._review_rate_ok(target, now=later))

    def test_review_lookup_scrubs_service_token(self):
        p = os.path.join(self.d, "notes.txt")
        _write(p, "old\n")
        hint = rpc(self.project, "local_do", {"action": "write", "path": p, "content": "x %s\n" % C.TOKEN})
        status, body = server.review_lookup(self.project, "token=" + C.token_from_hint(hint))
        self.assertEqual(status, 200)
        self.assertNotIn(C.TOKEN, json.dumps(body))
        self.assertIn("x ***", body["review"])


class ConfirmSchemaTextTests(unittest.TestCase):
    """S2: schema/คำอธิบาย/กฎย่อที่ถึงโมเดล — review ไม่บังคับ และไม่สั่งให้คัดลอกกลับมาอีก"""

    def test_schema_review_optional_token_first(self):
        s = server.CONFIRM_SCHEMA
        self.assertEqual(list(s["inputSchema"]["properties"]), ["confirm_token", "review"])
        self.assertEqual(s["inputSchema"]["required"], ["confirm_token"])
        self.assertIn("review ไม่บังคับ", s["description"])
        self.assertNotIn("ต้องส่ง confirm_token และ review", s["description"])

    def test_rules_and_instructions_say_token_only(self):
        for text in (server.RULES_SHORT, server.INSTRUCTIONS):
            self.assertIn("local_confirm(confirm_token", text)
            self.assertNotIn("review ตรงตัว", text)
            self.assertNotIn("ทุกตัวอักษร>", text)
        self.assertIn("แสดงบล็อก REVIEW", server.INSTRUCTIONS)
        self.assertIn("ห้ามเดาว่า", server.RULES_SHORT)

    def test_wrong_channel_reply_says_token_only(self):
        with guard.project_scope("rv-wc-%s" % os.urandom(3).hex()) as project:
            tok = guard.need_confirm("exec", "wc")
        out = server._wrong_channel_text("local_do", tok, project)
        self.assertIn('local_confirm(confirm_token="%s")' % tok, out)
        self.assertIn("```review", out)                     # ยังแนบ REVIEW ให้แสดงผู้ใช้ก่อนถาม
        out = server._wrong_channel_text("local_do", "deadbeef", project)
        self.assertIn('confirm_token="deadbeef"', out)
        self.assertIn("ไม่ต้องส่ง review", out)


class FastDescriptionTests(unittest.TestCase):
    def test_help_text_says_review_optional(self):
        h = tools_fast.help_text()
        self.assertIn("local_confirm(confirm_token=...)", h)
        self.assertIn("ไม่บังคับ", h)
        self.assertNotIn("local_confirm(confirm_token=..., review=...)", h)
        self.assertNotIn("local_confirm(confirm_token, review)", h)

    def test_local_do_description_lets_model_request_review(self):
        """FIXER (e2e): "ต้องถามผู้ใช้ก่อนเรียกเสมอ" ทำให้โมเดล 4B ไม่กล้าขอ token เลย หรือไปใช้ run_javascript แทน"""
        desc = next(t for t in tools_fast.TOOLS if t["name"] == "local_do")["description"]
        head = desc.split("พารามิเตอร์: ", 1)[0]
        self.assertFalse(head.startswith("เปลี่ยนแปลงเครื่อง ต้องถามผู้ใช้ก่อนเรียกเสมอ"))
        for s in ("action=python", "run_javascript", "ยังไม่ลงมือตอนเรียก", "confirm_token", "REVIEW",
                  "local_confirm", "ต้องถามผู้ใช้ก่อนเรียก", "ห้ามเดาว่าอนุมัติแล้ว", "remember/forget/path_*"):
            self.assertIn(s, head)


# ============================================================ R5: HTTP เต็มเส้นทาง
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class HttpReviewFlowTests(unittest.TestCase):
    """เซิร์ฟเวอร์จริงบนพอร์ตสำรองด้วย token ทดสอบ (LLM_LOCAL_TOKEN_FILE ชั่วคราว) — ไม่แตะพอร์ต 8792"""

    @classmethod
    def setUpClass(cls):
        port = 8892 if not C.port_in_use(8892) else _free_port()
        cls.srv = C.TestServer(C.MCP_LOCAL, port)
        cls.srv.start()
        cls.port = port

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def call(self, path, name, args, origin=None):
        status, _h, raw = C.rpc(self.port, path, "tools/call", {"name": name, "arguments": args},
                                origin=origin)
        self.assertEqual(status, 200, raw[:200])
        return C.tool_text(raw)

    def test_1_schema_review_optional(self):
        for path in ("/fast/" + C.PROJECT_OF_ALLOWED_ORIGIN, "/mcp/" + C.PROJECT_OF_ALLOWED_ORIGIN):
            status, _h, raw = C.rpc(self.port, path, "tools/list", origin=C.ALLOWED_ORIGIN)
            self.assertEqual(status, 200)
            tool = next(t for t in json.loads(raw)["result"]["tools"] if t["name"] == "local_confirm")
            self.assertEqual(list(tool["inputSchema"]["properties"]), ["confirm_token", "review"])
            self.assertEqual(tool["inputSchema"]["required"], ["confirm_token"])

    def test_2_full_flow_over_http(self):
        path = "/fast/" + C.PROJECT_OF_ALLOWED_ORIGIN
        d = C.new_dir("rvhttp")
        marker = os.path.join(d, "ran.txt")
        cmd = 'echo REVIEW-FLOW-OK> "%s"' % marker
        hint = self.call(path, "local_do", {"action": "run", "command": cmd, "path": d},
                         origin=C.ALLOWED_ORIGIN)
        args = C.confirm_args(hint)
        self.assertTrue(args["confirm_token"] and args["review"], hint[:400])
        self.assertIn(cmd, args["review"], "review ต้องมีคำสั่งเต็ม (สิ่งที่กล่องอนุญาตจะแสดง)")
        self.assertIn("cwd: %s" % d, args["review"])
        # ส่ง review ผิด -> ไม่รัน token ยังอยู่ และไม่แนบ review ให้คัดลอกซ้ำ (ให้ส่ง token อย่างเดียว)
        out = self.call(path, "local_confirm", dict(args, review=args["review"].replace("REVIEW-FLOW-OK", "harmless")),
                        origin=C.ALLOWED_ORIGIN)
        self.assertIn("ยังไม่ได้ทำอะไร", out)
        self.assertIn('local_confirm(confirm_token="%s")' % args["confirm_token"], out)
        self.assertEqual(C.review_from_hint(out), "")
        self.assertFalse(os.path.exists(marker))
        # ถูกต้อง (CRLF จากไคลเอนต์ก็ได้) -> รันจริงหนึ่งครั้ง
        crlf = dict(args, review=args["review"].replace("\n", "\r\n"))
        out = self.call(path, "local_confirm", crlf, origin=C.ALLOWED_ORIGIN)
        self.assertIn("[exit code: 0]", out)
        self.assertTrue(os.path.isfile(marker))
        out = self.call(path, "local_confirm", args, origin=C.ALLOWED_ORIGIN)
        self.assertIn("ใช้ไม่ได้", out)
        # S2: token อย่างเดียว (ไม่มี review) -> รันจริงหนึ่งครั้ง
        marker2 = os.path.join(d, "ran2.txt")
        tok = C.token_from_hint(self.call(path, "local_do", {"action": "run", "path": d,
                                                              "command": 'echo TOKEN-ONLY> "%s"' % marker2},
                                          origin=C.ALLOWED_ORIGIN))
        # รอบ FIXER: กล่องอนุญาตยังไม่ดึง review ไปแสดง = ไม่รัน (token ยังอยู่)
        out = self.call(path, "local_confirm", {"confirm_token": tok}, origin=C.ALLOWED_ORIGIN)
        self.assertTrue(out.startswith("ยังไม่ได้ทำอะไร: "), out[:80])
        self.assertFalse(os.path.exists(marker2))
        # สคริปต์ในเครื่องที่ไม่มี Origin อ่านได้ แต่ไม่นับว่า "กล่องอนุญาตแสดงแล้ว"
        self.assertEqual(self.get_review(C.PROJECT_OF_ALLOWED_ORIGIN, tok, origin=None)[0], 200)
        out = self.call(path, "local_confirm", {"confirm_token": tok}, origin=C.ALLOWED_ORIGIN)
        self.assertTrue(out.startswith("ยังไม่ได้ทำอะไร: "), out[:80])
        self.assertFalse(os.path.exists(marker2))
        # การ์ดอนุญาตของหน้า 8103 ดึง review (มี Origin) -> token อย่างเดียวรันได้
        self.assertEqual(self.get_review(C.PROJECT_OF_ALLOWED_ORIGIN, tok)[0], 200)
        out = self.call(path, "local_confirm", {"confirm_token": tok}, origin=C.ALLOWED_ORIGIN)
        self.assertIn("[exit code: 0]", out)
        self.assertTrue(os.path.isfile(marker2))
        self.assertIn("ใช้ไม่ได้", self.call(path, "local_confirm", {"confirm_token": tok}, origin=C.ALLOWED_ORIGIN))

    def test_3_hidden_chars_over_http(self):
        path = "/fast/rv-http-hidden"
        d = C.new_dir("rvhttp2")
        p = os.path.join(d, "t.txt")
        _write(p, "one\n")
        hint = self.call(path, "local_do", {"action": "edit", "path": p, "old": "one",
                                            "new": "o" + RLO + "ne" + ZWSP})
        args = C.confirm_args(hint)
        self.assertIn("«U+202E»", args["review"])
        self.assertTrue(args["review"].startswith("⚠"))
        # ส่ง review แบบ "ดิบ" (อักขระซ่อนจริงแทนรหัสที่ตาเห็น) = ไม่ตรง
        raw = args["review"].replace("«U+202E»", RLO).replace("«U+200B»", ZWSP)
        out = self.call(path, "local_confirm", dict(args, review=raw))
        self.assertIn("ไม่ตรง", out)
        self.assertEqual(_read(p), "one\n")
        # ตัดบรรทัดคำเตือนทิ้ง = ไม่ตรง
        out = self.call(path, "local_confirm",
                        dict(args, review=args["review"].split("\n", 1)[1]))
        self.assertIn("ไม่ตรง", out)
        self.call(path, "local_confirm", args)
        self.assertEqual(_read(p), "o" + RLO + "ne" + ZWSP + "\n")

    def test_4_python_refusal_and_single_pending_over_http(self):
        path = "/fast/rv-http-py"
        out = self.call(path, "local_do", {"action": "python",
                                           "code": "\n".join("x = %d" % i for i in range(450))})
        self.assertTrue(out.startswith("ปฏิเสธ"), out[:160])
        a = C.confirm_args(self.call(path, "local_do", {"action": "python", "code": "print('A')"}))
        b = C.confirm_args(self.call(path, "local_do", {"action": "python", "code": "print('B')"}))
        self.assertIn("ใช้ไม่ได้", self.call(path, "local_confirm", a))
        self.assertTrue(b["confirm_token"])

    def test_5_get_sse_stream_is_405_not_json(self):
        """FIXER: เดิมตอบ 200 JSON ให้ GET + Accept: text/event-stream — MCP client ของ WebUI ต่อใหม่ทุก ~1.3 วินาที"""
        path = "/fast/" + C.PROJECT_OF_ALLOWED_ORIGIN
        auth = {"Authorization": "Bearer " + C.TOKEN, "Origin": C.ALLOWED_ORIGIN}
        status, hdrs, _raw = C.http("GET", self.port, path, headers=dict(auth, Accept="text/event-stream"))
        self.assertEqual(status, 405)
        self.assertIn("POST", hdrs.get("allow", ""))
        status, _h, raw = C.http("GET", self.port, path, headers=dict(auth, Accept="application/json"))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["status"], "ok")
        status, _h, _raw = C.http("GET", self.port, path, headers={"Accept": "text/event-stream"})
        self.assertEqual(status, 401, "ด่าน token มาก่อนเสมอ")
        status, _h, _raw = C.http("GET", self.port, "/health", headers={"Accept": "text/event-stream"})
        self.assertEqual(status, 200)

    def test_6_leading_space_review_runs_over_http(self):
        path = "/fast/" + C.PROJECT_OF_ALLOWED_ORIGIN
        d = C.new_dir("rvhttp6")
        marker = os.path.join(d, "ran.txt")
        args = C.confirm_args(self.call(path, "local_do", {"action": "run", "command": 'echo OK> "%s"' % marker,
                                                           "path": d}, origin=C.ALLOWED_ORIGIN))
        out = self.call(path, "local_confirm", dict(args, review=" " + args["review"]), origin=C.ALLOWED_ORIGIN)
        self.assertIn("[exit code: 0]", out)
        self.assertTrue(os.path.isfile(marker))

    # ------------------------------------------------ S1: GET /review/<slug>?token=
    def get_review(self, slug, tok, origin=C.ALLOWED_ORIGIN, token=C.TOKEN, host=None, query=None):
        headers = {"Accept": "application/json"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if origin is not None:
            headers["Origin"] = origin
        path = "/review/%s?%s" % (quote(slug), ("token=" + tok) if query is None else query)
        status, hdrs, raw = C.http("GET", self.port, path, headers=headers, host=host)
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = raw
        return status, hdrs, body

    def test_7_review_endpoint_returns_server_review_read_only(self):
        slug = C.PROJECT_OF_ALLOWED_ORIGIN
        d = C.new_dir("rvhttp7")
        marker = os.path.join(d, "ran.txt")
        hint = self.call("/fast/" + slug, "local_do", {"action": "run", "command": 'echo S1> "%s"' % marker,
                                                       "path": d}, origin=C.ALLOWED_ORIGIN)
        args = C.confirm_args(hint)
        tok = args["confirm_token"]
        status, hdrs, body = self.get_review(slug, tok)
        self.assertEqual(status, 200, body)
        self.assertEqual(hdrs.get("access-control-allow-origin"), C.ALLOWED_ORIGIN)
        self.assertIn("no-store", hdrs.get("cache-control", ""))
        self.assertTrue(hdrs.get("content-type", "").startswith("application/json"))
        self.assertEqual(set(body), {"ok", "action", "review", "expires_in_s", "pending"})
        self.assertTrue(body["ok"] is True and body["pending"] is True)
        self.assertEqual(body["review"], args["review"], "ต้องเป็นข้อความตรวจทานของเซิร์ฟเวอร์ตรงตัว")
        self.assertEqual(body["action"], "exec")
        self.assertTrue(0 < body["expires_in_s"] <= guard.CONFIRM_TTL)
        # อ่านซ้ำ: ไม่ต่ออายุ ไม่ลงมือ
        again = self.get_review(slug, tok)[2]
        self.assertLessEqual(again["expires_in_s"], body["expires_in_s"])
        self.assertFalse(os.path.exists(marker))
        # token ยังใช้ได้ตามปกติ (S2: token อย่างเดียว)
        out = self.call("/fast/" + slug, "local_confirm", {"confirm_token": tok}, origin=C.ALLOWED_ORIGIN)
        self.assertIn("[exit code: 0]", out)
        self.assertTrue(os.path.isfile(marker))
        self.assertEqual(self.get_review(slug, tok)[::2], (404, {"ok": False, "reason": "not_pending"}))

    def test_8_review_endpoint_scope_and_auth(self):
        slug = C.PROJECT_OF_ALLOWED_ORIGIN
        d = C.new_dir("rvhttp8")
        p = os.path.join(d, "a.txt")
        _write(p, "one\n")
        # token ของผิวเต็ม (/mcp) อ่านได้เหมือนกัน — ผิวไหนก็ได้ แต่ต้องโปรเจกต์เดียวกัน
        hint = self.call("/mcp/" + slug, "edit_file", {"path": p, "old_string": "one", "new_string": "two"},
                         origin=C.ALLOWED_ORIGIN)
        tok = C.token_from_hint(hint)
        status, _h, body = self.get_review(slug, tok)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["review"], C.review_from_hint(hint))
        # โปรเจกต์อื่น: token ของ proj-b ไม่เห็นผ่าน URL ของ sec-http และหน้า 8103 เรียก URL ของ proj-b ไม่ได้
        tok_b = C.token_from_hint(self.call("/fast/proj-b", "local_do",
                                            {"action": "edit", "path": p, "old": "one", "new": "bbb"},
                                            origin="http://127.0.0.1:8104"))
        self.assertTrue(tok_b)
        self.assertEqual(self.get_review(slug, tok_b)[::2], (404, {"ok": False, "reason": "not_pending"}))
        self.assertEqual(self.get_review("proj-b", tok_b)[0], 403, "Origin 8103 ผูกกับ sec-http (S04)")
        self.assertEqual(self.get_review("proj-b", tok_b, origin="http://localhost:8104")[0], 200)
        self.assertEqual(self.get_review("proj-b", tok_b, origin=None)[0], 200, "ไคลเอนต์ในเครื่องที่ไม่มี Origin")
        # ด่านเดียวกับ /mcp: Bearer + Origin + Host
        self.assertEqual(self.get_review(slug, tok, token=None)[0], 401)
        self.assertEqual(self.get_review(slug, tok, token="0" * 64)[0], 401)
        self.assertEqual(self.get_review(slug, tok, origin=C.EVIL_ORIGIN)[0], 403)
        self.assertEqual(self.get_review(slug, tok, origin="http://127.0.0.1:8150")[0], 403)
        self.assertEqual(self.get_review(slug, tok, host="evil.example:%d" % self.port)[0], 403)
        for st, h, b in (self.get_review(slug, tok, token=None), self.get_review(slug, tok, origin=C.EVIL_ORIGIN)):
            self.assertNotIn("review", b if isinstance(b, dict) else {})
            self.assertNotIn(tok, json.dumps(b, ensure_ascii=False) if b else "")
        # preflight ของ fetch ที่มี Authorization (ไม่ต้องมี token แต่ Origin ต้องอยู่ในรายการ)
        pre = {"Origin": C.ALLOWED_ORIGIN, "Access-Control-Request-Method": "GET",
               "Access-Control-Request-Headers": "authorization"}
        status, hdrs, _raw = C.http("OPTIONS", self.port, "/review/%s?token=%s" % (slug, tok), headers=pre)
        self.assertEqual(status, 204)
        self.assertEqual(hdrs.get("access-control-allow-origin"), C.ALLOWED_ORIGIN)
        self.assertIn("GET", hdrs.get("access-control-allow-methods", ""))
        self.assertIn("Authorization", hdrs.get("access-control-allow-headers", ""))
        status, hdrs, _raw = C.http("OPTIONS", self.port, "/review/" + slug, headers=dict(pre, Origin=C.EVIL_ORIGIN))
        self.assertEqual(status, 403)
        self.assertNotIn("access-control-allow-origin", hdrs)
        # คำขอผิดรูป
        self.assertEqual(self.get_review(slug, "", query="")[::2], (400, {"ok": False, "reason": "missing_token"}))
        self.assertEqual(self.get_review(slug, "", query="token=%3Cscript%3E")[::2],
                         (400, {"ok": False, "reason": "bad_token"}))
        status, _h, body = C.http("GET", self.port, "/review/a/b?token=" + tok,
                                  headers={"Authorization": "Bearer " + C.TOKEN})
        self.assertEqual(status, 400)
        # ไม่ใช่ช่องทาง MCP: POST/DELETE ได้ 405 ไม่ใช่ผลของ tools/list
        status, hdrs, raw = C.rpc(self.port, "/review/" + slug, "tools/list", origin=C.ALLOWED_ORIGIN)
        self.assertEqual(status, 405, raw[:200])
        self.assertIn("GET", hdrs.get("allow", ""))
        status, _h, _raw = C.http("DELETE", self.port, "/review/" + slug,
                                  headers={"Authorization": "Bearer " + C.TOKEN, "Origin": C.ALLOWED_ORIGIN})
        self.assertEqual(status, 405)
        # ทุกอย่างข้างบนไม่ได้ใช้ token: ยังยืนยันได้
        self.call("/mcp/" + slug, "local_confirm", {"confirm_token": tok}, origin=C.ALLOWED_ORIGIN)
        self.assertEqual(_read(p), "two\n")

    def test_9_review_endpoint_thai_slug(self):
        slug = "ทดสอบ-รีวิว"
        d = C.new_dir("rvhttp9")
        p = os.path.join(d, "a.txt")
        _write(p, "one\n")
        hint = self.call("/fast/" + quote(slug), "local_do", {"action": "edit", "path": p, "old": "one", "new": "t"})
        status, _h, body = self.get_review(slug, C.token_from_hint(hint), origin=None)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["review"], C.review_from_hint(hint))

    def test_zz_review_endpoint_rate_limited(self):
        """slug ที่ hub ไม่รู้จักใช้ตัวนับกองกลาง, โปรเจกต์จริงนับแยก และการยิง slug ใหม่รีเซ็ตตัวนับของโปรเจกต์ไม่ได้
        (รอบ FIXER: เดิมยิง slug อื่น 257 ครั้งแล้วเป้าหมายได้อีก 120 ครั้งในนาทีเดียวกัน)"""
        def until_limited(slug, origin=None):
            """ยิงจนโดน 429 — เทสต์ก่อนหน้าในคลาสนี้อาจใช้ตัวนับเดียวกันไปแล้วบางส่วน (อยู่ในหน้าต่าง 60 วินาทีเดียวกัน)"""
            seen = []
            for _ in range(server.REVIEW_RATE_MAX + 5):
                status, hdrs, body = self.get_review(slug, "deadbeef", origin=origin)
                seen.append(status)
                if status == 429:
                    return seen, hdrs, body
            return seen, {}, None

        slug = "rv-rate-%s" % os.urandom(3).hex()
        seen, hdrs, body = until_limited(slug)
        self.assertEqual(seen[-1], 429, seen[-3:])
        self.assertEqual(set(seen[:-1]), {404})
        self.assertLessEqual(len(seen) - 1, server.REVIEW_RATE_MAX)
        self.assertGreaterEqual(len(seen) - 1, server.REVIEW_RATE_MAX - 5)
        self.assertEqual(body, {"ok": False, "reason": "rate_limited"})
        self.assertTrue(hdrs.get("retry-after"))
        self.assertEqual(self.get_review("rv-rate-other", "deadbeef", origin=None)[0], 429,
                         "slug ที่ไม่รู้จักทุกตัวใช้ตัวนับกองกลางเดียวกัน")
        self.assertEqual(self.get_review("proj-b", "deadbeef", origin="http://127.0.0.1:8104")[0], 404,
                         "นับแยกต่อโปรเจกต์จริง — หน้าอื่นยังดึง review ได้")
        # proj-b ถูกจำกัด -> ยิง slug ใหม่ 300 ตัว (หรือ Origin 8100) -> proj-b ยังถูกจำกัดอยู่ในหน้าต่างเดียวกัน
        seen, _h, _b = until_limited("proj-b")
        self.assertEqual(seen[-1], 429, "โปรเจกต์จริงก็ถูกจำกัดที่ %d ครั้งต่อหน้าต่าง" % server.REVIEW_RATE_MAX)
        churn = {self.get_review("churn-%d" % i, "deadbeef", origin="http://127.0.0.1:8100")[0] for i in range(300)}
        self.assertEqual(churn, {429})
        self.assertEqual(self.get_review("proj-b", "deadbeef", origin=None)[0], 429,
                         "ตัวนับของโปรเจกต์ต้องไม่ถูกไล่ออก/รีเซ็ตด้วยการยิง slug อื่น")


if __name__ == "__main__":
    unittest.main()
