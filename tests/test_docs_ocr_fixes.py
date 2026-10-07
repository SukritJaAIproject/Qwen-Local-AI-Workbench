# -*- coding: utf-8 -*-
"""เทสต์รอบแก้ของ docs2 (batch 2a fixer, 2026-10-01) — ผลตรวจ E2E/ความปลอดภัยของ OCR และ kb

ตรวจ
  * ชั้นข้อความไทยที่ "เสีย" จาก glyph สลับรูป (PDF จาก PyMuPDF + Tahoma/Leelawadee) ถอดกลับได้ตรงตัวโดยไม่ OCR
    (เดิม OCR ทั้งหน้า: ช้า และรหัส "สถานี B" กลายเป็น "สถานี 8"), PUA ของ Windows/Mac ซ่อมเฉพาะในบริบทไทย
  * ซ่อมไม่ได้ตรงตัว = คงชั้นข้อความ ซ่อมเฉพาะตัวที่เสียจาก OCR (รหัส/ตัวเลขของชั้นข้อความไม่ถูกแตะ) และหน้าอื่นใน
    ไฟล์เดียวกันซ่อมตามรหัสที่ OCR ยืนยันแล้ว, หน้าที่เสียมากยังใช้ OCR ทั้งหน้า
  * ป้าย OCR: คำที่ไม่แน่ใจ, คำเตือนตรวจรหัสแม้ความมั่นใจสูง, ตัดบรรทัดเศษที่อ่านไม่ออก
  * ภาพเปิดด้วยตัวถอดของชนิดในสัญญาเท่านั้น (WMF/EPS ที่ตั้งชื่อ .png ถูกปฏิเสธก่อนถอด)
  * เรนเดอร์หน้า PDF ในโปรเซสลูกที่ถูกฆ่าเมื่อเกินเวลา (ไม่มี token/env ของ MCP)
  * แคช OCR มี HMAC (ปลอม/ย้ายข้ามหน้า = ไม่ใช้), kb\\ เป็นเขตห้ามเขียนของเครื่องมือแต่ MCP เขียนเองได้,
    index.db ที่ไม่ใช่ฐานข้อมูลถูกย้ายไปข้างๆ (ไม่ลบ) แล้วสร้างใหม่
  * guard: Tesseract / โมเดล embedding / kb ของทุกโปรเจกต์อยู่ในเขตห้ามเขียน + ข้อความคำสั่งต้องห้าม
  * ชื่อไฟล์ไทยที่โมเดลคัดลอกตกหล่น: เสนอชื่อใกล้เคียงเฉพาะใน attachments/outputs ของโปรเจกต์ และใช้ให้เลยเมื่อชัด
"""
import io
import json
import os
import struct
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402
from test_docs_ocr import FakeTess, _Patch, image_only_pdf  # noqa: E402

guard = C.import_local("guard")
extract = C.import_local("extract")
tools_kb = C.import_local("tools_kb")
tools_docs = C.import_local("tools_docs")
tools_fast = C.import_local("tools_fast")

TAHOMA = r"C:\Windows\Fonts\tahoma.ttf"
LEELAWADEE = r"C:\Windows\Fonts\LeelawUI.ttf"
CLOSED = "http://127.0.0.1:9"

STATION_LINES = ["รายงานตรวจตู้ชาร์จสถานี B ประจำเดือนกันยายน",
                 "ตู้หมายเลข 7 หยุดจ่ายไฟกลางคันสามครั้ง ตรวจพบคอนแทคเตอร์ฝั่ง DC มีรอยไหม้ที่หน้าสัมผัส",
                 "จึงเปลี่ยนคอนแทคเตอร์ใหม่และขันขั้วต่อด้วยแรงบิดตามคู่มือ ญูฐุ ปิ่น"]


def _proj(name):
    return "ocrfix-%s-%s" % (name, os.urandom(3).hex())


def _base(project):
    d = os.path.join(C.PROJECT_DATA, guard.project_slug(project))
    os.makedirs(os.path.join(d, "attachments"), exist_ok=True)
    return d


def htmlbox_pdf(path, pages, fontfile):
    """PDF แบบที่ PyMuPDF insert_htmlbox สร้าง (HarfBuzz สลับรูปวรรณยุกต์ แล้ว glyph สลับรูปไม่มีรหัสใน ToUnicode)"""
    import pymupdf as fz
    doc = fz.open()
    css = ("@font-face {font-family: t; src: url(%s);} * {font-family: t; font-size: 13pt;}"
           % os.path.basename(fontfile))
    for lines in pages:
        page = doc.new_page()
        page.insert_htmlbox(fz.Rect(50, 50, 545, 800), "".join("<p>%s</p>" % t for t in lines), css=css,
                            archive=fz.Archive(os.path.dirname(fontfile)))
    doc.save(path)
    doc.close()
    return path


def compact(s):
    return "".join(str(s).split())


# ============================================================ ซ่อมชั้นข้อความตรงตัว
class LosslessRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = C.new_dir("ocrfix-lossless")

    def need(self, font):
        if not os.path.exists(font):
            self.skipTest("ไม่มีฟอนต์ %s" % font)

    def check_font(self, font, name):
        self.need(font)
        path = htmlbox_pdf(os.path.join(self.d, name), [STATION_LINES] * 3, font)
        import pymupdf as fz
        with fz.open(path) as d:
            raw = d[0].get_text()
        self.assertTrue(extract._ODD_NEAR_THAI_RE.search(raw), "fixture ต้องเสียจริง: %r" % raw[:200])
        boom = FakeTess(fail="ไม่ควรถูกเรียก")
        t0 = time.monotonic()
        with _Patch(extract, _tesseract=boom):
            out = extract.extract_text(path, "x.pdf")
        self.assertEqual(boom.calls, [])                               # ไม่ต้อง OCR เลย
        self.assertLess(time.monotonic() - t0, 20)
        body = out.split("--- หน้า 1/3 ---", 1)[1].split("--- หน้า 2/3 ---", 1)[0]
        self.assertEqual(compact(body), compact("".join(STATION_LINES)))  # ตรงต้นฉบับทุกตัว
        self.assertIn("ถอดกลับจากตาราง glyph ของฟอนต์ในไฟล์แล้ว", out)
        self.assertNotIn("[คำเตือน]", out)
        self.assertEqual(out.count("สถานี B"), 3)

    def test_tahoma_variant_glyphs_repaired_without_ocr(self):
        self.check_font(TAHOMA, "tahoma.pdf")

    def test_leelawadee_variant_glyphs_repaired_without_ocr(self):
        self.check_font(LEELAWADEE, "leela.pdf")

    def test_pua_repaired_only_in_thai_context(self):
        fix = extract.repair_thai_layer
        self.assertEqual(fix("ป\uf70bน ท\uf70a\uf718"), ("ป้น ทุ่", 3))   # Windows PUA
        self.assertEqual(fix("ค\uf88eา"), ("ค้า", 1))                           # Mac PUA
        self.assertEqual(fix("icon \uf70b and \uf8ff"), ("icon \uf70b and \uf8ff", 0))   # ฟอนต์ไอคอน
        self.assertEqual(fix("\uf70f\u0e39"), ("\u0e0d\u0e39", 1))               # ญ ตัดเชิงต้นคำ

    def test_unknown_or_mismatched_font_is_not_guessed(self):
        self.assertIsNone(extract._thai_font("ABCDEF+NoSuchFontXYZ-Regular"))
        self.need(TAHOMA)
        self.need(LEELAWADEE)
        path = htmlbox_pdf(os.path.join(self.d, "mismatch.pdf"), [STATION_LINES], TAHOMA)
        leela = extract._thai_font("Leelawadee UI")
        self.assertIsNotNone(leela)
        import pymupdf as fz
        # ฟอนต์ในเครื่องคนละตัว (glyph ของอักษรปกติไม่ตรง) = ไม่ใช้ตาราง แม้ตารางจะมีเลข glyph ที่ตรงกัน
        with fz.open(path) as d, _Patch(extract, _thai_font=lambda name: (leela[0], {0x477: "่", 0x478: "้"})):
            self.assertEqual(extract._layer_fix_map(d[0]), {})


# ============================================================ ซ่อมเฉพาะจุดด้วย OCR
class PatchModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = C.new_dir("ocrfix-patch")

    def setUp(self):
        if not os.path.exists(LEELAWADEE):
            self.skipTest("ไม่มีฟอนต์ Leelawadee UI")

    def test_patch_keeps_layer_codes_and_fixes_whole_file(self):
        from test_docs_extract import thai_pdf_with_cmap
        p1 = "ตรวจครั้งที่สาม สถานี B ตู้ DC-07 ไหม้ที่หน้าสัมผัส เปลี่ยนใหม่ทั้งชุด"
        p2 = "ขั้วสาย ST-204 ปกติดี ตรวจซ้ำเดือนหน้า"                    # เสียตัวเดียว (ต่ำกว่าเกณฑ์เดิม)
        path = thai_pdf_with_cmap(os.path.join(self.d, "two.pdf"), [p1, p2], {0x0E49: 0x0478, 0x0E48: 0x0477})
        # OCR อ่านวรรณยุกต์ถูก แต่รหัสผิด (B -> 8, DC-07 -> 06-07) และหน้า 2 อ่านวรรณยุกต์หาย
        ocr1 = p1.replace("สถานี B", "สถานี 8").replace("DC-07", "06-07")
        ocr2 = p2.replace("ขั้ว", "ขัว")
        fake = FakeTess(texts=[ocr1, ocr2])
        with _Patch(extract, _tesseract=fake):
            out = extract.extract_text(path, "two.pdf")
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("สถานี B", out)
        self.assertIn("DC-07", out)
        self.assertNotIn("สถานี 8", out)
        self.assertNotIn("06-07", out)
        self.assertNotIn("[OCR หน้า", out)
        self.assertIn(compact(p1), compact(out))
        self.assertIn(compact(p2), compact(out))                        # หน้า 2 ซ่อมตามรหัสที่ OCR ยืนยันในหน้า 1
        self.assertNotIn("[คำเตือน]", out)
        self.assertIn("ซ่อมเฉพาะตัวที่เสียจากภาพด้วย OCR", out)

    def test_heavily_garbled_page_still_uses_full_ocr(self):
        from test_docs_extract import thai_pdf_with_cmap
        text = "ที่นี่ น่ะ ค่ะ ก้ ม่ ป่ า"
        path = thai_pdf_with_cmap(os.path.join(self.d, "heavy.pdf"), [text], {0x0E49: 0x0478, 0x0E48: 0x0477})
        fake = FakeTess(texts=["ข้อความจาก OCR ทั้งหน้า HEAVY-OK"])
        with _Patch(extract, _tesseract=fake):
            out = extract.extract_text(path, "heavy.pdf")
        self.assertIn("[OCR หน้า 1 · ", out)
        self.assertIn("HEAVY-OK", out)
        self.assertIn("ชั้นข้อความเสียมาก", out)
        self.assertIn("อ่านใหม่ด้วย OCR แล้ว", out)

    def test_patch_unit(self):
        layer = "ครัѸง ทีѷ สถานี B รหัส E-101"
        new, k = extract._patch_layer(layer, "ครั้ง ที่ สถานี 8 รหัส 5:101")
        self.assertEqual(new, "ครั้ง ที่ สถานี B รหัส E-101")
        self.assertEqual(k, 2)
        # OCR อ่านพยัญชนะรอบๆ ผิดด้วย = แนวไม่ตรง ไม่แตะ
        new2, k2 = extract._patch_layer("ครัѸง", "คร้ง")
        self.assertEqual((new2, k2), ("ครัѸง", 0))


# ============================================================ ป้าย OCR
class OcrHintTests(unittest.TestCase):
    TSV_HEAD = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"

    def row(self, line, word, conf, text):
        return "5\t1\t1\t1\t%d\t%d\t0\t0\t9\t9\t%.2f\t%s\n" % (line, word, conf, text)

    def test_unsure_words_and_stray_lines(self):
        tsv = (self.TSV_HEAD + self.row(1, 1, 95, "ร") + self.row(1, 2, 95, "า") + self.row(1, 3, 50.7, "5:101")
               + self.row(1, 4, 72, "Und") + self.row(1, 5, 78, "เค") + self.row(1, 6, 94, "ิ")
               + self.row(1, 7, 94, "น")
               + self.row(2, 1, 23.6, "4") + self.row(2, 2, 40, "ฉ่")
               + self.row(3, 1, 96, "ต") + self.row(3, 2, 96, "ก"))
        txt = "รา 5:101 Und เคิน\n4       ฉ่\nตก\n\f"
        got = extract._parse_tess(tsv + txt)
        self.assertEqual(got["dropped"], 1)
        self.assertNotIn("ฉ่", got["text"])
        self.assertIn("ตก", got["text"])
        self.assertIn("5:101", got["unsure"])
        self.assertIn("Und", got["unsure"])
        self.assertTrue(any("เค" in w and len(w) > 2 for w in got["unsure"]), got["unsure"])   # มีตัวข้างเคียง

    def test_block_header_carries_hints_on_one_line(self):
        rec = {"text": "ตู้หมายเลข DC-07 อุณหภูมิ 91", "conf": 94.0, "unsure": ["5:101", "Und]x["], "dropped": 2}
        head = extract.ocr_block(1, rec).split("\n", 1)[0]
        self.assertIn("(สูง · ตรวจรหัส/ตัวเลขกับต้นฉบับก่อนยกไปใช้)", head)
        self.assertIn("ไม่แน่ใจ: 5:101, Undx", head)
        self.assertIn("ตัดเศษที่อ่านไม่ออก 2 บรรทัด", head)
        self.assertTrue(extract.OCR_MARK_RE.match(extract.ocr_block(1, rec)))       # kb ยังถอดป้ายทั้งบรรทัดได้
        self.assertIn("(สูง)]", extract.ocr_block(1, {"text": "ไม่มีรหัส", "conf": 94.0}))


# ============================================================ ภาพ: ตัวถอดเฉพาะชนิดในสัญญา
def placeable_wmf() -> bytes:
    head = b"\xd7\xcd\xc6\x9a\x00\x00" + struct.pack("<hhhh", 0, 0, 200, 100) + struct.pack("<H", 1440) + b"\0" * 4
    csum = 0
    for i in range(0, 20, 2):
        csum ^= struct.unpack("<H", head[i:i + 2])[0]
    head += struct.pack("<H", csum)
    std = struct.pack("<HHHIHIH", 1, 9, 0x0300, 12, 0, 3, 0)
    return head + std + struct.pack("<IH", 3, 0)


class ImageFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = C.new_dir("ocrfix-img")

    def write(self, name, data):
        p = os.path.join(self.d, name)
        with open(p, "wb") as fh:
            fh.write(data)
        return p

    def test_wmf_and_eps_named_png_are_refused_before_decoding(self):
        from PIL import Image
        wmf = self.write("disguised-wmf.png", placeable_wmf())
        eps = self.write("disguised-eps.png", b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\nshowpage\n")
        with Image.open(wmf) as im:                                      # fixture ถูกต้อง: Pillow เดาเป็น WMF จริง
            self.assertEqual(im.format, "WMF")
        with Image.open(eps) as im:
            self.assertEqual(im.format, "EPS")
        calls = []
        core = Image.core
        orig = getattr(core, "drawwmf", None)
        if orig is not None:
            core.drawwmf = lambda *a, **k: calls.append(a) or orig(*a, **k)
        try:
            for p in (wmf, eps):
                with _Patch(extract, _tesseract=FakeTess()):
                    with self.assertRaises(extract.ExtractError) as cm:
                        extract.extract_units(p, ocr_dir="")
                self.assertIn("เปิดไฟล์ภาพไม่ได้", str(cm.exception))
        finally:
            if orig is not None:
                core.drawwmf = orig
        self.assertEqual(calls, [])                                     # GDI ไม่เคยเห็นไบต์ของผู้โจมตี

    def test_other_formats_refused_but_misnamed_jpeg_accepted(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("L", (300, 120), 255).save(buf, "GIF")
        gif = self.write("anim.png", buf.getvalue())
        with self.assertRaises(extract.ExtractError):
            extract.extract_units(gif, ocr_dir="")
        buf = io.BytesIO()
        Image.new("RGB", (300, 120), (255, 255, 255)).save(buf, "JPEG")
        jpg = self.write("photo-really-jpeg.png", buf.getvalue())
        fake = FakeTess(texts=["JPEG-OK"])
        with _Patch(extract, _tesseract=fake):
            res = extract.extract_units(jpg, ocr_dir="")
        self.assertIn("JPEG-OK", res.units[0].text)


# ============================================================ เรนเดอร์ในโปรเซสลูก
class RenderIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = C.new_dir("ocrfix-render")
        cls.pdf = image_only_pdf(os.path.join(cls.d, "r.pdf"), 2)

    def test_child_is_isolated_and_renders(self):
        seen = {}
        real = subprocess.Popen

        def spy(cmd, **kw):
            seen["cmd"], seen["kw"] = cmd, kw
            return real(cmd, **kw)
        os.environ["QWEN_FAKE_SECRET_TOKEN"] = "sentinel-should-not-leak"
        try:
            with _Patch(extract.subprocess, Popen=spy), extract._Renderer(self.pdf) as rend:
                w, h, stride, data = rend.gray(1, 0.5, 20)
        finally:
            os.environ.pop("QWEN_FAKE_SECRET_TOKEN", None)
        self.assertGreater(w * h, 0)
        self.assertEqual(len(data), stride * h)
        cmd, kw = seen["cmd"], seen["kw"]
        self.assertEqual(cmd[:3], [sys.executable, "-I", "-c"])
        self.assertIs(kw.get("shell"), False)
        self.assertTrue(set(kw["env"]) <= {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH"})
        self.assertNotIn("sentinel-should-not-leak", repr(kw["env"]))
        self.assertNotIn(C.TOKEN, repr(cmd) + repr(kw["env"]))

    def test_slow_render_is_killed_and_file_given_up(self):
        slow = "import sys, time\nfor line in sys.stdin.buffer:\n    time.sleep(120)\n"
        with _Patch(extract, _RENDER_CHILD=slow), extract._Renderer(self.pdf) as rend:
            t0 = time.monotonic()
            with self.assertRaises(extract._OcrFail) as cm:
                rend.gray(1, 1.0, 1.5)
            self.assertLess(time.monotonic() - t0, 15)
            self.assertIn("เกิน", str(cm.exception))
            with self.assertRaises(extract._OcrFail):
                rend.gray(2, 1.0, 1.5)
            self.assertTrue(rend.broken)                                 # ฆ่าครบ RENDER_KILLS_MAX = เลิกทั้งไฟล์
            t1 = time.monotonic()
            with self.assertRaises(extract._OcrFail):
                rend.gray(1, 1.0, 1.5)
            self.assertLess(time.monotonic() - t1, 1.0)

    def test_extract_notes_render_timeout_and_moves_on(self):
        slow = "import sys, time\nfor line in sys.stdin.buffer:\n    time.sleep(120)\n"
        fake = FakeTess()
        with _Patch(extract, _RENDER_CHILD=slow, RENDER_TIMEOUT=1.5, INK_TIMEOUT=1.0, _tesseract=fake):
            t0 = time.monotonic()
            out = extract.extract_text(self.pdf, "r.pdf")
        self.assertLess(time.monotonic() - t0, 30)
        self.assertEqual(fake.calls, [])
        self.assertIn("OCR หน้า 1 ไม่สำเร็จ", out)


# ============================================================ แคช / kb / guard
class CacheAndGuardTests(unittest.TestCase):
    def test_cache_records_are_signed_and_bound_to_file_and_page(self):
        p = _proj("mac")
        base = _base(p)
        path = image_only_pdf(os.path.join(base, "attachments", "m.pdf"), 2)
        fake = FakeTess(texts=["หน้าแรก MAC-1", "หน้าสอง MAC-2"])
        with guard.project_scope(p), _Patch(extract, _tesseract=fake):
            tools_docs.doc_extract(path="m.pdf", project=p)
        cache = os.path.join(base, "kb", "ocr")
        sha = extract._file_sha256(path)
        with open(os.path.join(cache, "%s-1.json" % sha), encoding="utf-8") as fh:
            rec1 = json.load(fh)
        self.assertIn("mac", rec1)
        self.assertIsNotNone(extract._cache_read(cache, sha, 1))
        # ย้ายระเบียนหน้า 1 ไปแทนหน้า 2 / แก้ข้อความ = ไม่ผ่าน
        with open(os.path.join(cache, "%s-2.json" % sha), "w", encoding="utf-8") as fh:
            json.dump(rec1, fh, ensure_ascii=False)
        self.assertIsNone(extract._cache_read(cache, sha, 2))
        rec1["text"] = "ผลทดสอบ FAIL (ปลอม)"
        with open(os.path.join(cache, "%s-1.json" % sha), "w", encoding="utf-8") as fh:
            json.dump(rec1, fh, ensure_ascii=False)
        self.assertIsNone(extract._cache_read(cache, sha, 1))

    def test_tools_cannot_write_kb_but_mcp_can(self):
        p = _proj("wp")
        base = _base(p)
        target = os.path.join(base, "kb", "ocr", "%s-1.json" % ("0" * 64))
        with guard.project_scope(p):
            self.assertTrue(guard.is_write_protected(target))
            self.assertTrue(guard.is_write_protected(os.path.join(base, "kb", "index.db")))
            with self.assertRaises(guard.Denied):
                guard.check_write(target)
            guard.check_write(os.path.join(base, "attachments", "ok.txt"))       # ไฟล์แนบยังเขียนได้ตามปกติ
            self.assertTrue(extract._cache_write_ok(target))                    # MCP เขียนแคชของตัวเองได้
            other = os.path.join(_base(_proj("other")), "kb", "ocr", "x-1.json")
            self.assertFalse(extract._cache_write_ok(other))                    # S04: โปรเจกต์อื่นไม่ได้
        self.assertFalse(extract._cache_write_ok(r"C:\LLM\mcp-local\x.json"))   # เขตห้ามเขียนอื่นยังห้าม

    def test_planted_index_db_is_moved_aside_and_rebuilt(self):
        p = _proj("idx")
        base = _base(p)
        with open(os.path.join(base, "attachments", "a.txt"), "w", encoding="utf-8") as fh:
            fh.write("เนื้อหาจริง IDX-OK")
        os.makedirs(os.path.join(base, "kb"), exist_ok=True)
        with open(os.path.join(base, "kb", "index.db"), "w", encoding="utf-8") as fh:
            fh.write("not a database " * 100)
        with guard.project_scope(p):
            out = tools_kb.kb_search(query="IDX-OK", project=p, mode="lexical")
        self.assertNotIn("ERROR", out)
        self.assertIn("IDX-OK", out)
        moved = [n for n in os.listdir(os.path.join(base, "kb")) if n.startswith("index.db.bad-")]
        self.assertEqual(len(moved), 1)                                          # ย้าย ไม่ลบ

    def test_stack_components_are_write_protected(self):
        for path in (r"C:\LLM\tools\tesseract\tesseract.exe", r"C:\LLM\tools\tesseract\version.dll",
                     r"C:\LLM\tools\tesseract\tessdata\configs\txt", r"C:\LLM\tools\tesseract\tessdata\tha.config",
                     r"D:\LLM\models-embed", r"D:\LLM\models-embed\Qwen3-Embedding-0.6B-Q8_0.gguf",
                     r"C:\LLM\projects\data\project1\kb\ocr\a-1.json", r"C:\LLM\projects\data\project1\kb\index.db"):
            self.assertTrue(guard.is_write_protected(path), path)
        for path in (r"C:\LLM\projects\data\project1\attachments\kb.txt", r"C:\Users\demo\tools\x.exe"):
            self.assertFalse(guard.is_write_protected(path), path)
        for cmd in (r"copy x C:\LLM\tools\tesseract\tessdata\configs\txt", r"copy x D:/LLM/models-embed/m.gguf",
                    r"move a.json C:\LLM\projects\data\project1\kb\ocr\b-1.json"):
            self.assertEqual(guard.command_text_violation(cmd, False), "protected_path", cmd)
        self.assertIsNone(guard.command_text_violation(r"dir C:\LLM\tools\tesseract", True))

    def test_blank_page_remembered_not_pending(self):
        import pymupdf as fz
        p = _proj("blank")
        base = _base(p)
        path = os.path.join(base, "attachments", "blank.pdf")
        doc = fz.open()
        doc.new_page()
        doc.save(path)
        doc.close()
        fake = FakeTess()
        with guard.project_scope(p), _Patch(extract, _tesseract=fake):
            res = extract.extract_units(path, for_index=True, ocr_budget=0.0)
            res2 = extract.extract_units(path, for_index=True, ocr_budget=0.0)
        self.assertEqual(fake.calls, [])
        self.assertEqual(res.ocr.get("pending", []), [])
        self.assertEqual(res2.ocr.get("pending", []), [])


# ============================================================ ชื่อไฟล์ใกล้เคียง
class NearNameTests(unittest.TestCase):
    def setUp(self):
        self.p = _proj("near")
        self.base = _base(self.p)
        os.makedirs(os.path.join(self.base, "outputs"), exist_ok=True)
        with open(os.path.join(self.base, "attachments", "scan-เหตุขัดข้อง-C03.txt"), "w", encoding="utf-8") as fh:
            fh.write("เนื้อหาเหตุขัดข้อง NEAR-OK")
        with open(os.path.join(self.base, "attachments", "รายงานประจำเดือน-กันยายน.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("รายงาน SEPT")
        with open(os.path.join(self.base, "attachments", "รายงานประจำเดือน-สิงหาคม.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("รายงาน AUG")

    def extract(self, path):
        with guard.project_scope(self.p):
            return tools_fast.local_read(action="extract", path=path, project=self.p)

    def test_close_single_match_is_used_and_said(self):
        out = self.extract("attachments/scan-เหตุข้อง-C03.txt")           # "ขัด" หายไป (เคสจริงใน E2E)
        self.assertTrue(out.startswith("[หมายเหตุ] ไม่พบไฟล์"), out[:200])
        self.assertIn('ใช้ไฟล์ที่ชื่อใกล้ที่สุด "attachments/scan-เหตุขัดข้อง-C03.txt"', out)
        self.assertIn("NEAR-OK", out)
        self.assertIn(extract.BANNER, out)

    def test_ambiguous_match_only_suggests(self):
        out = self.extract("รายงานประจำเดือน.txt")
        self.assertIn("ไม่พบไฟล์", out)
        self.assertIn("หมายถึงไฟล์นี้ไหม:", out)
        self.assertIn("รายงานประจำเดือน-กันยายน.txt", out)
        self.assertNotIn("SEPT", out)                                            # ไม่เดาเปิดให้เอง

    def test_no_suggestions_outside_project_folders(self):
        with guard.project_scope(self.p):
            self.assertEqual(tools_kb.near_names(r"C:\Windows\win.ini", self.p), [])
            self.assertEqual(tools_kb.near_names("../../etc/passwd", self.p), [])
            other = _proj("near-other")
            ob = _base(other)
            with open(os.path.join(ob, "attachments", "scan-เหตุขัดข้อง-C03.txt"), "w", encoding="utf-8") as fh:
                fh.write("ของโปรเจกต์อื่น")
            got = tools_kb.near_names(os.path.join(ob, "attachments", "scan-เหตุข้อง-C03.txt"), self.p)
        self.assertEqual(got, [])                                                # S04: ไม่ช่วยหาในโปรเจกต์อื่น


if __name__ == "__main__":
    unittest.main()
