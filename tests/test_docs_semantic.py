# -*- coding: utf-8 -*-
"""เทสต์คลังความรู้แบบความหมาย (semantic kb) ของ tools_kb — docs2, batch 2a (สัญญา B2 ฝั่ง tools_kb)

ตรวจ
  * บริการ embedding ปลอม (แบบ llama-server --embeddings): ส่ง Bearer token ของเครื่อง, คำค้นเติม
    "Instruct: ...\\nQuery: " ส่วนเอกสารไม่เติม, เก็บเวกเตอร์ float32 ที่ normalize แล้วใน index.db,
    embed เฉพาะก้อนใหม่/ที่เปลี่ยน (ไฟล์แก้ = เฉพาะก้อนของไฟล์นั้น, แตะไฟล์แต่เนื้อเดิม = ไม่ embed ซ้ำ)
  * ล่ม/ช้า/token ผิด/HTTP error -> ค้นแบบคำตรง + หมายเหตุหนึ่งบรรทัด และไม่ลองซ้ำทุกคำค้นช่วง TTL
  * mode=lexical ไม่แตะบริการเลย, mode=semantic เรียงตามเวกเตอร์ (ติดป้าย "ตรงตามความหมาย"), auto = RRF
  * URL ของบริการรับเฉพาะ 127.0.0.1/localhost (token ไม่มีทางออกนอกเครื่อง)
  * ลายนิ้วมือโมเดลเปลี่ยน = ล้างเวกเตอร์เดิมแล้วทำใหม่
  * ก้อนค้างเยอะ = ทำเบื้องหลัง (มีหมายเหตุความครอบคลุม) และหลบให้แชตที่กำลังตอบ (keep_awake ของ hub)
  * /fast: local_read kb รับ mode และลำดับคีย์ query -> k -> mode เขียนได้ภายใต้ grammar
  * ของจริง: Qwen3-Embedding-0.6B บน llama-server พอร์ตสำรอง (token ทดสอบ) กับคำค้นไทยแบบถอดความ
    (ไม่มีคำตรงกับเอกสาร) — ความหมายต้องชนะคำตรงชัดเจน (ข้ามถ้าไม่มี exe/โมเดล หรือ LLM_SKIP_EMBED_LIVE=1)
"""
import hashlib
import json
import math
import os
import socket
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

guard = C.import_local("guard")
extract = C.import_local("extract")
tools_kb = C.import_local("tools_kb")
tools_fast = C.import_local("tools_fast")

CLOSED = "http://127.0.0.1:9"
PREFIX = "Instruct: Given a question, retrieve passages that answer it\nQuery: "

# กลุ่มความหมายของ embedding ปลอม: ข้อความที่มีคำในกลุ่มเดียวกันได้เวกเตอร์ใกล้กัน ทั้งที่ไม่มีคำตรงกันเลย
CONCEPTS = [
    ("ร้อน", "อุณหภูมิ", "heat"),
    ("เงิน", "ค่าบริการ", "บาท", "ราคา"),
    ("ดิน", "ground", "earth"),
    ("บัตร", "การ์ด", "rfid"),
]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeEmbed:
    """/v1/embeddings ปลอม: ตรวจ Bearer, บันทึกทุก input, เวกเตอร์ 64 มิติจากกลุ่มความหมาย + trigram (กำหนดแน่นอน)"""

    def __init__(self, token, delay=0.0, status=200, variant=0):
        self.token, self.delay, self.status, self.variant = token, delay, status, variant
        self.inputs, self.auth, self.requests = [], [], 0
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8"))
                fake.requests += 1
                fake.auth.append(self.headers.get("Authorization", ""))
                if fake.delay:
                    time.sleep(fake.delay)
                if self.headers.get("Authorization") != "Bearer " + fake.token:
                    return self._send(401, {"error": {"code": 401, "message": "Invalid API Key"}})
                if fake.status != 200:
                    return self._send(fake.status, {"error": {"message": "boom"}})
                texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
                fake.inputs.extend(texts)
                data = [{"index": i, "embedding": fake.vec(t)} for i, t in enumerate(texts)]
                self._send(200, {"model": body.get("model"), "data": data, "usage": {}})

            def _send(self, code, obj):
                raw = json.dumps(obj).encode("utf-8")
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except OSError:
                    pass
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def vec(self, text):
        low = text.lower().split("\n", 1)[-1] if text.startswith(PREFIX) is False else text[len(PREFIX):].lower()
        v = [0.0] * 64
        for i, words in enumerate(CONCEPTS):
            if any(w in low for w in words):
                v[i] += 5.0
        for j in range(len(low) - 2):
            h = int(hashlib.md5(low[j:j + 3].encode("utf-8")).hexdigest(), 16)
            v[8 + h % 56] += 0.05
        if self.variant:
            v = list(reversed(v))
        v[63] += 0.01                                  # กันเวกเตอร์ศูนย์
        return v

    def docs(self):
        return [t for t in self.inputs if not t.startswith(PREFIX) and not t.startswith("kb fingerprint")]

    def queries(self):
        return [t for t in self.inputs if t.startswith(PREFIX)]

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class FakeHub:
    def __init__(self, keep_awake=0):
        self.keep_awake = keep_awake
        hub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                raw = json.dumps({"projects": [], "keep_awake": hub.keep_awake}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def _proj(name):
    return "sem-%s-%s" % (name, os.urandom(3).hex())


def _base(project):
    d = os.path.join(C.PROJECT_DATA, guard.project_slug(project))
    os.makedirs(os.path.join(d, "attachments"), exist_ok=True)
    return d


def _put(project, rel, text):
    path = os.path.join(_base(project), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class _EnvCase(unittest.TestCase):
    """ตั้ง URL ของบริการ embedding/hub ต่อเทสต์ แล้วคืนค่าเดิม (เทสต์ไฟล์อื่นในโปรเซสเดียวกันไม่โดนผลกระทบ)"""
    hub_url = CLOSED

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in (tools_kb.EMBED_URL_ENV, tools_kb.HUB_URL_ENV)}
        os.environ[tools_kb.HUB_URL_ENV] = self.hub_url
        tools_kb.reset_embed_state()
        self.fakes = []

    def tearDown(self):
        tools_kb.stop_background()
        for f in self.fakes:
            f.close()
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        tools_kb.reset_embed_state()

    def embed_server(self, **kw):
        f = FakeEmbed(kw.pop("token", C.TOKEN), **kw)
        self.fakes.append(f)
        os.environ[tools_kb.EMBED_URL_ENV] = "http://127.0.0.1:%d" % f.port
        return f

    def kb(self, p, q, **kw):
        with guard.project_scope(p):
            return tools_kb.kb_search(query=q, project=p, **kw)


class SemanticKbTests(_EnvCase):
    def test_hybrid_auth_prefix_and_semantic_only_hit(self):
        fake = self.embed_server()
        p = _proj("hyb")
        _put(p, "attachments/heat.txt", "หัวชาร์จ CCS2 มีอุณหภูมิสูงผิดปกติระหว่างการชาร์จกำลังสูง")
        _put(p, "attachments/rfid.txt", "สมาชิกแตะบัตรแล้วเครื่องอ่านไม่ตอบสนอง")
        out = self.kb(p, "ปลั๊กร้อนเกินไป")
        self.assertIn("ค้นแบบผสม: คำตรง + ความหมาย", out)
        self.assertIn("[1] attachments/heat.txt · ทั้งไฟล์ · ตรงตามความหมาย", out)   # ไม่มีคำตรงกันเลย
        self.assertNotIn("rfid.txt", out)                                          # ต่ำกว่า SEM_MIN
        self.assertTrue(fake.auth and all(a == "Bearer " + C.TOKEN for a in fake.auth))
        self.assertEqual(fake.queries(), [PREFIX + "ปลั๊กร้อนเกินไป"])
        docs = fake.docs()
        self.assertEqual(len(docs), 2)
        self.assertTrue(all(not d.startswith("Instruct") for d in docs))
        self.assertTrue(any(d.startswith("heat.txt · ทั้งไฟล์\n") for d in docs))

    def test_vectors_stored_normalized_float32(self):
        self.embed_server()
        p = _proj("vec")
        _put(p, "attachments/a.txt", "ค่าบริการช่วงกลางคืนหน่วยละ 4.5 บาท")
        self.kb(p, "ราคา")
        con = sqlite3.connect(os.path.join(_base(p), "kb", "index.db"))
        try:
            rows = con.execute("SELECT h, dim, v FROM vecs").fetchall()
        finally:
            con.close()
        self.assertEqual(len(rows), 1)
        h, dim, blob = rows[0]
        self.assertEqual(dim, 64)
        self.assertEqual(len(blob), 4 * 64)
        vals = struct.unpack("<64f", blob)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in vals)), 1.0, places=4)
        self.assertEqual(len(h), 40)

    def test_only_new_or_changed_chunks_are_embedded(self):
        fake = self.embed_server()
        p = _proj("lazy")
        a = _put(p, "attachments/a.txt", "สายดินหลวมที่หลักดิน ALPHA")
        _put(p, "attachments/b.txt", "ค่าบริการ 7.2 บาท BRAVO")
        self.kb(p, "ALPHA")
        self.assertEqual(len(fake.docs()), 2)
        self.kb(p, "BRAVO")
        self.assertEqual(len(fake.docs()), 2)                        # ครั้งที่สอง: embed แค่คำค้น
        self.assertEqual(len(fake.queries()), 2)
        os.utime(a, (time.time() + 5, time.time() + 5))              # แตะไฟล์ (ทำดัชนีใหม่) แต่เนื้อเดิม
        out = self.kb(p, "ALPHA")
        self.assertIn("อัปเดตดัชนี 1 ไฟล์", out)
        self.assertEqual(len(fake.docs()), 2)                        # hash เดิม = ไม่ embed ซ้ำ
        with open(a, "w", encoding="utf-8") as fh:
            fh.write("สายดินหลวม แก้ไขแล้ว CHARLIE")
        self.kb(p, "CHARLIE")
        self.assertEqual(len(fake.docs()), 3)                        # เฉพาะก้อนของไฟล์ที่แก้
        self.assertIn("CHARLIE", fake.docs()[-1])

    def test_mode_lexical_never_calls_service(self):
        fake = self.embed_server()
        p = _proj("lex")
        _put(p, "attachments/a.txt", "รหัส E-217 แรงดันต่ำ")
        out = self.kb(p, "E-217", mode="lexical")
        self.assertEqual(fake.requests, 0)
        self.assertIn("[1] attachments/a.txt", out)
        self.assertNotIn("ค้นแบบผสม", out)
        self.assertNotIn("ความหมายไม่ได้", out)

    def test_mode_semantic_and_aliases(self):
        self.embed_server()
        p = _proj("sem")
        _put(p, "attachments/money.txt", "อัตราค่าบริการช่วงพีคหน่วยละ 7.2 บาท")
        _put(p, "attachments/ground.txt", "ตรวจความต้านทานดินที่หลักดิน")
        out = self.kb(p, "ชาร์จแพงไหม ราคาเท่าไร", mode="semantic")
        self.assertIn("ค้นตามความหมาย (mode=semantic)", out)
        self.assertIn("[1] attachments/money.txt", out)
        self.assertIn("ค้นแบบผสม", self.kb(p, "ราคา", mode="whatever"))   # ค่าแปลก = auto
        self.assertIn("ค้นตามความหมาย", self.kb(p, "ราคา", mode="ความหมาย"))

    def test_exact_code_still_first_in_hybrid(self):
        self.embed_server()
        p = _proj("exact")
        _put(p, "attachments/code.txt", "หน้าจอแสดงรหัส E-217 ให้ตรวจเบรกเกอร์หลัก")
        _put(p, "attachments/heat.txt", "อุณหภูมิหัวชาร์จสูง ร้อนมาก")
        out = self.kb(p, "E-217")
        self.assertIn("[1] attachments/code.txt", out)

    def test_rrf_fusion_unit(self):
        lex = [(3.0, 0.0, 1, "a.txt", "x", "ข้อความ A"), (2.0, 0.0, 2, "b.txt", "x", "ข้อความ B")]
        sem = [(0.9, 2), (0.8, 3)]
        rows = {3: ("c.txt", "x", "ข้อความ C")}
        # _finish ต้องการ base สำหรับดึงก้อนที่มาจาก sem อย่างเดียว — จำลองด้วยการเติม lex แถวที่ 3 ลงไปไม่ได้
        # จึงทดสอบเฉพาะส่วนที่ไม่ต้องอ่านฐานข้อมูล: b อยู่ทั้งสองรายการ = อันดับหนึ่ง
        out = tools_kb._finish(lex, sem, 5, ["ข้อความ"], set(), set())
        self.assertEqual([h["file"] for h in out][:2], ["b.txt", "a.txt"])
        self.assertEqual(out[0]["via"], "both")
        self.assertEqual(out[1]["via"], "lex")
        self.assertTrue(rows)

    def test_fingerprint_change_resets_vectors(self):
        fake = self.embed_server()
        p = _proj("fp")
        _put(p, "attachments/a.txt", "บัตร RFID อ่านไม่ได้")
        self.kb(p, "การ์ด")
        self.assertEqual(len(fake.docs()), 1)
        fake.variant = 1                                             # "เปลี่ยนโมเดล" แล้วรีสตาร์ต MCP
        tools_kb.reset_embed_state()
        self.kb(p, "การ์ด")
        self.assertEqual(len(fake.docs()), 2)                        # เวกเตอร์เดิมถูกล้างแล้ว embed ใหม่


class SemanticFallbackTests(_EnvCase):
    def test_service_down_falls_back_in_one_line(self):
        os.environ[tools_kb.EMBED_URL_ENV] = CLOSED
        p = _proj("down")
        _put(p, "attachments/a.txt", "รหัส E-217 แรงดันไฟฟ้าขาเข้าต่ำ")
        out = self.kb(p, "E-217")
        notes = [ln for ln in out.split("\n") if "ความหมาย" in ln]
        self.assertEqual(len(notes), 1, out)
        self.assertIn("[หมายเหตุ] ค้นตามความหมายไม่ได้ตอนนี้ (ต่อบริการ embedding ที่พอร์ต 9 ไม่ได้) — "
                      "ใช้การค้นแบบคำตรงอย่างเดียว", out)
        self.assertIn("[1] attachments/a.txt", out)

    def test_http_error_not_retried_within_ttl(self):
        fake = self.embed_server(status=500)
        p = _proj("h500")
        _put(p, "attachments/a.txt", "ข้อความ ERR-1")
        self.assertIn("บริการ embedding ตอบ HTTP 500", self.kb(p, "ERR-1"))
        self.assertEqual(fake.requests, 1)
        t0 = time.monotonic()
        out = self.kb(p, "ERR-1")
        self.assertEqual(fake.requests, 1)                           # ช่วง TTL ไม่ลองซ้ำ
        self.assertIn("HTTP 500", out)
        self.assertLess(time.monotonic() - t0, 5)

    def test_wrong_token_401(self):
        fake = self.embed_server(token="0" * 64)                      # บริการใช้ token อื่น
        p = _proj("t401")
        _put(p, "attachments/a.txt", "ข้อความ TOK-1")
        out = self.kb(p, "TOK-1")
        self.assertIn("บริการ embedding ปฏิเสธ token (401)", out)
        self.assertIn("[1] attachments/a.txt", out)
        self.assertEqual(fake.inputs, [])

    def test_slow_service_falls_back(self):
        self.embed_server(delay=3.0)
        p = _proj("slow")
        _put(p, "attachments/a.txt", "ข้อความ SLOW-1")
        old = tools_kb.EMBED_QUERY_TIMEOUT
        tools_kb.EMBED_QUERY_TIMEOUT = 1.0
        try:
            t0 = time.monotonic()
            out = self.kb(p, "SLOW-1")
            secs = time.monotonic() - t0
        finally:
            tools_kb.EMBED_QUERY_TIMEOUT = old
        self.assertIn("บริการ embedding ตอบช้าเกิน 1 วินาที", out)
        self.assertIn("[1] attachments/a.txt", out)
        self.assertLess(secs, 3.0)

    def test_url_is_loopback_only(self):
        default = 8093
        for value, want in (("http://example.com:8093", default), ("http://10.0.0.5:9999", default),
                            ("https://127.0.0.1:8894", default), ("http://127.0.0.1:8894", 8894),
                            ("http://localhost:8895/", 8895), ("", default), ("garbage", default),
                            ("http://127.0.0.1.evil.com:8894", default)):
            os.environ[tools_kb.EMBED_URL_ENV] = value
            self.assertEqual(tools_kb.embed_port(), want, value)


class SemanticBackgroundTests(_EnvCase):
    def setUp(self):
        self.hub = FakeHub(keep_awake=1)                             # แชตกำลังตอบอยู่
        self.hub_url = "http://127.0.0.1:%d" % self.hub.port
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.hub.close()

    def test_backlog_embedded_in_background_and_yields_to_chat(self):
        fake = self.embed_server()
        p = _proj("bg")
        # > EMBED_SYNC_MAX -> ทำเบื้องหลัง (outputs/: docs2 fixer ทำไฟล์แนบค้างไม่เกิน EMBED_SYNC_ATTACH ในคำค้นเลย)
        for i in range(6):
            _put(p, "outputs/n%d.txt" % i, "บันทึกหมายเลข %d ค่าบริการ %d บาท" % (i, i * 10))
        out = self.kb(p, "ราคา")
        self.assertIn("[หมายเหตุ] ดัชนีความหมายมี 0/6 ก้อน กำลังทำส่วนที่เหลือเบื้องหลัง", out)
        time.sleep(1.5)
        self.assertEqual(fake.docs(), [])                            # แชตยังตอบอยู่ = ไม่แย่ง CPU
        self.hub.keep_awake = 0
        tools_kb._HUB_STATE["at"] = 0.0
        self.assertTrue(tools_kb.wait_background(p, 60))
        self.assertEqual(len(fake.docs()), 6)
        self.assertTrue(max(fake.requests, 0) < 1 + 1 + 6)           # รวมหลายก้อนในคำขอเดียว (ไม่ใช่ทีละก้อน)
        out2 = self.kb(p, "ราคา")
        self.assertNotIn("ดัชนีความหมายมี", out2)
        with guard.project_scope(p):
            st = tools_kb.index_status(_base(p))
        self.assertEqual((st["chunks"], st["vectors"]), (6, 6))


class FastSurfaceModeTests(_EnvCase):
    def test_schema_help_and_dispatch(self):
        read = next(t for t in tools_fast.TOOLS if t["name"] == "local_read")
        keys = [k for k in read["inputSchema"]["properties"] if k not in ("action", "project")]
        self.assertIn("mode", keys)
        self.assertLess(keys.index("query"), keys.index("k"))
        self.assertLess(keys.index("k"), keys.index("mode"))
        self.assertIn("kb:query,k,mode", read["description"])
        self.assertIn("mode=auto", tools_fast.help_text())
        self.assertIn("OCR", tools_fast._READ_INDEX["extract"][2])
        fake = self.embed_server()
        p = _proj("fast")
        _put(p, "attachments/a.txt", "ค่าบริการ FAST-1")
        with guard.project_scope(p):
            out = tools_fast.local_read(action="kb", query="FAST-1", mode="lexical", project=p)
            self.assertIn("FAST-1", out)
            self.assertEqual(fake.requests, 0)
            out = tools_fast.local_read(action="kb", query="ราคา", mode="semantic", project=p)
        self.assertIn("ค้นตามความหมาย", out)
        self.assertGreater(fake.requests, 0)
        full = next(t for t in tools_kb.TOOLS if t["name"] == "kb_search")
        self.assertEqual(full["inputSchema"]["properties"]["mode"]["enum"], ["auto", "lexical", "semantic"])


# =================================================================== ของจริง (Qwen3-Embedding-0.6B)
EMBED_MODEL = r"D:\LLM\models-embed\Qwen3-Embedding-0.6B-Q8_0.gguf"
SERVER_EXES = (r"C:\LLM\llama.cpp-b10984\llama-server.exe", r"C:\LLM\llama.cpp\llama-server.exe")

PASSAGES = {
    "P1": "ถ้าตู้ชาร์จตัดการจ่ายไฟพร้อมแจ้งเตือน GroundFailure ให้ตรวจความต่อเนื่องของสายดินและค่าความต้านทานดินที่หลักดิน ค่าที่ยอมรับได้ต้องไม่เกิน 5 โอห์ม",
    "P2": "หัวชาร์จ CCS2 ร้อนผิดปกติระหว่างการชาร์จกำลังสูง มักเกิดจากหน้าสัมผัสสกปรกหรือหลวม เซ็นเซอร์อุณหภูมิในหัวจะลดกระแสลงเมื่อเกิน 90 องศาเซลเซียส",
    "P3": "สมาชิกแตะบัตร RFID แล้วระบบไม่ตอบสนอง ให้ตรวจว่าเครื่องอ่านบัตรได้รับไฟเลี้ยง 12 โวลต์ และหมายเลขบัตรถูกลงทะเบียนในระบบหลังบ้านแล้ว",
    "P4": "ถ้าศูนย์ควบคุมไม่ได้รับข้อความ Heartbeat เกินสามรอบติดต่อกัน สถานะของตู้จะถูกเปลี่ยนเป็นออฟไลน์ ควรตรวจสัญญาณซิม 4G และการตั้งค่า APN",
    "P5": "อัตราค่าบริการช่วงออฟพีคคิดหน่วยละ 4.5 บาท ส่วนช่วงพีคคิดหน่วยละ 7.2 บาท และมีค่าจอดเกินเวลา 100 บาทต่อชั่วโมงหลังชาร์จเสร็จ",
    "P6": "แผนบำรุงรักษาเชิงป้องกันกำหนดให้ทำความสะอาดแผ่นกรองอากาศของตู้ทุกเดือน และตรวจแรงบิดขั้วต่อไฟฟ้าทุกหกเดือน",
    "P7": "ก่อนเริ่มจ่ายไฟ DC ตู้จะทดสอบความเป็นฉนวนของสายชาร์จ หากค่าที่วัดได้ต่ำกว่า 100 กิโลโอห์มต่อโวลต์ ระบบจะหยุดการชาร์จเพื่อความปลอดภัย",
    "P8": "การอัปเดตเฟิร์มแวร์ผ่านคำสั่ง UpdateFirmware ต้องทำในช่วงที่ไม่มีรถเสียบชาร์จ และห้ามตัดไฟระหว่างติดตั้งจนกว่าหน้าจอจะรีสตาร์ตเสร็จ",
    "P9": "เมื่อกดปุ่มหยุดฉุกเฉิน คอนแทคเตอร์หลักจะตัดวงจรทันที ต้องหมุนปุ่มเพื่อปลดล็อกและยืนยันการรีเซ็ตที่หน้าจอก่อนใช้งานต่อ",
    "P10": "แกงเขียวหวานไก่ใช้พริกแกงเขียวหวาน กะทิ มะเขือเปราะ และใบโหระพา เคี่ยวด้วยไฟอ่อนจนน้ำแกงแตกมัน",
    "P11": "เชียงใหม่ในฤดูหนาวมีอากาศเย็นสบาย นักท่องเที่ยวนิยมขึ้นดอยอินทนนท์เพื่อชมทะเลหมอกยามเช้า",
    "P12": "หน้าจอแสดงรหัส E-217 หมายถึงแรงดันไฟฟ้าขาเข้าต่ำกว่าเกณฑ์ ให้ตรวจเบรกเกอร์หลักและแรงดันจากหม้อแปลงของการไฟฟ้า",
}
# คำค้นถอดความ: ไม่ใช้คำเดียวกับเอกสาร (ต่อลงพื้น/สายดิน, ปลั๊ก/หัวชาร์จ, ทาบการ์ด/แตะบัตร ...) + ข้ามภาษา 2 ข้อ
PARAPHRASES = [
    ("เครื่องหยุดชาร์จเพราะระบบต่อลงพื้นมีปัญหา ต้องเช็กอะไร", "P1"),
    ("ปลั๊กที่เสียบรถมีความร้อนสูงเกินไป เกิดจากอะไร", "P2"),
    ("ทาบการ์ดสมาชิกแล้วเครื่องเงียบ ไม่มีอะไรเกิดขึ้น", "P3"),
    ("ทำไมตู้ถึงขาดการติดต่อกับเซิร์ฟเวอร์กลาง", "P4"),
    ("ชาร์จตอนกลางคืนเสียเงินเท่าไหร่", "P5"),
    ("ต้องดูแลรักษาเครื่องบ่อยแค่ไหน", "P6"),
    ("ก่อนปล่อยกระแสตรงเครื่องเช็กความปลอดภัยของสายอย่างไร", "P7"),
    ("ข้อควรระวังตอนลงซอฟต์แวร์เวอร์ชันใหม่ให้เครื่อง", "P8"),
    ("กดสวิตช์แดงหยุดเครื่องไปแล้ว จะเปิดใช้ใหม่ยังไง", "P9"),
    ("ไฟที่เข้าตู้น้อยไปจะขึ้นโค้ดอะไร", "P12"),
    ("How much does it cost to charge at night?", "P5"),
    ("charger trips because of an earth leakage problem", "P1"),
]


def _live_skip_reason() -> str:
    if os.environ.get("LLM_SKIP_EMBED_LIVE") == "1":
        return "LLM_SKIP_EMBED_LIVE=1"
    if not os.path.isfile(EMBED_MODEL):
        return "ไม่มีโมเดล %s" % EMBED_MODEL
    if not any(os.path.isfile(x) for x in SERVER_EXES):
        return "ไม่มี llama-server"
    return ""


def _spare_port() -> int:
    # 8893 = พอร์ตสำรองของบริการ embedding ทดสอบตามสัญญา — ถ้ามีคนใช้อยู่ (agent อื่น) ใช้ 8894-8899
    for port in (8893, 8894, 8895, 8896, 8897, 8898, 8899):
        if not C.port_in_use(port):
            return port
    return _free_port()


@unittest.skipIf(_live_skip_reason(), _live_skip_reason())
class KbFixerTests(_EnvCase):
    """docs2 fixer (ผลตรวจ E2E): ประโยคคำถามไทยค้นแบบคำตรงเจอ, คำอังกฤษทั่วไปไม่สร้างผลขยะ, รายงานเว็บไม่ซ้ำ/ไม่กลบ
    เอกสารของโปรเจกต์, ไฟล์แนบได้เวกเตอร์ก่อน, ผลความหมายที่ห่างจากอันดับหนึ่งมากถูกตัด, บอก "ไม่พบ ≠ ไม่มี" """

    def test_thai_question_sentence_finds_chunk_lexically(self):
        os.environ[tools_kb.EMBED_URL_ENV] = CLOSED
        p = _proj("longq")
        _put(p, "attachments/note.txt", "บันทึกการตรวจสอบประจำเดือน\n3. ค่าแรงดันขาเข้า 398 V กระแส 125 A ความถี่ 50.02 Hz\n")
        _put(p, "attachments/other.txt", "รายงานตรวจตู้ชาร์จ ตู้หมายเลข 7 ตรวจพบคอนแทคเตอร์ DC มีรอยไหม้ที่หน้าสัมผัส\n")
        out = self.kb(p, "ภาพถ่ายบันทึกตรวจตู้วัดแรงดันขาเข้าได้กี่โวลต์", mode="lexical")
        self.assertIn("[1] attachments/note.txt", out)
        both = self.kb(p, "ตู้ที่หน้าสัมผัสไหม้อยู่สถานีไหน และภาพถ่ายบันทึกตรวจตู้วัดแรงดันขาเข้าได้กี่โวลต์",
                       mode="lexical")
        self.assertIn("attachments/note.txt", both)
        self.assertIn("attachments/other.txt", both)

    def test_english_stop_words_do_not_make_lexical_noise(self):
        os.environ[tools_kb.EMBED_URL_ENV] = CLOSED
        p = _proj("stop")
        _put(p, "attachments/lock.txt", "ConnectorLockFailure occurs when the Type 2 socket actuator cannot confirm "
                                        "the locked position. Check the lock motor fuse and clean the pin.")
        _put(p, "attachments/imd.txt", "Insulation monitoring: if isolation is below 100 ohm per volt the session "
                                       "is refused. Dry the handle and test the cable in the workshop.")
        self.assertIn("ไม่พบเนื้อหา", self.kb(p, "best hiking trails in Chiang Mai", mode="lexical"))
        self.assertIn("[1] attachments/lock.txt", self.kb(p, "lock motor fuse", mode="lexical"))
        self.assertFalse(tools_kb._term_in("in", "insulation monitoring"))
        self.assertTrue(tools_kb._term_in("e-204", "รหัส e-204 ไฟตก"))

    def test_research_report_twin_skipped_tagged_and_ranked_after_project_docs(self):
        os.environ[tools_kb.EMBED_URL_ENV] = CLOSED
        import docx
        p = _proj("twin")
        text = "ผลค้นคว้า หัวชาร์จ CCS2 ร้อนเกิน WEBTWIN-1 จากเว็บ"
        _put(p, "outputs/research-2026-10-01-rabc123.md", "# รายงาน\n\n" + text + "\n")
        d = docx.Document()
        d.add_paragraph(text)
        d.save(os.path.join(_base(p), "outputs", "research-2026-10-01-rabc123.docx"))
        _put(p, "attachments/inspect.txt", "บันทึกของทีม: หัวชาร์จ CCS2 ร้อนเกิน WEBTWIN-1 ที่สถานีบางนา")
        out = self.kb(p, "WEBTWIN-1", mode="lexical")
        self.assertIn("[1] attachments/inspect.txt", out)
        self.assertIn("outputs/research-2026-10-01-rabc123.md · ", out)
        self.assertIn("รายงานค้นคว้าจากเว็บ (ไม่ใช่เอกสารของโปรเจกต์)", out)
        self.assertNotIn(".docx", out)
        with guard.project_scope(p):
            st = tools_kb.index_status(_base(p))
        self.assertEqual(st["files"], 2)                                    # .docx คู่ของ .md ไม่ถูกเก็บซ้ำ

    def test_new_attachment_embedded_before_outputs_backlog(self):
        fake = self.embed_server()
        p = _proj("attfirst")
        for i in range(8):
            _put(p, "outputs/r%d.txt" % i, "รายงานเก่าหมายเลข %d เรื่องอื่น" % i)
        _put(p, "attachments/new.txt", "บัตร RFID ใบใหม่ของลูกค้า ATT-FIRST")
        out = self.kb(p, "การ์ดลูกค้า")
        self.assertEqual([d.split("\n", 1)[0] for d in fake.docs()], ["new.txt · ทั้งไฟล์"])   # ในคำค้น: ไฟล์แนบเท่านั้น
        self.assertIn("attachments/new.txt", out)
        self.assertIn("ดัชนีความหมายมี 1/9 ก้อน", out)
        self.assertIn("อย่าสรุปว่าไม่มี", out)

    def test_semantic_only_hits_far_below_best_are_dropped(self):
        self.embed_server()
        p = _proj("floor")
        _put(p, "attachments/a.txt", "ค่าบริการรายเดือน 10 บาท")
        _put(p, "attachments/b.txt", "อุณหภูมิขั้วต่อสูงและค่าบริการซ่อม")              # เงิน + ร้อน: cos ~0.7
        _put(p, "attachments/c.txt", "บัตร RFID อ่านไม่ได้")
        for mode in ("auto", "semantic"):
            out = self.kb(p, "เงิน", mode=mode)
            self.assertIn("[1] attachments/a.txt", out, mode)
            self.assertNotIn("attachments/b.txt", out, mode)
            self.assertNotIn("attachments/c.txt", out, mode)
        self.assertIn("ไม่พบ ≠ ไม่มี", self.kb(p, "ควอนตัมฟิสิกส์", mode="lexical"))


class LiveQwenEmbeddingTests(unittest.TestCase):
    """llama-server --embeddings --pooling last กับ Qwen3-Embedding-0.6B (CPU, -t 4) บนพอร์ตสำรองด้วย token ทดสอบ
    เปิดเองและปิดเองตอนจบ — ไม่แตะบริการจริงที่ 8093"""

    @classmethod
    def setUpClass(cls):
        cls.port = _spare_port()
        exe = next(x for x in SERVER_EXES if os.path.isfile(x))
        cls.log = os.path.join(C.TMP, "embed-live-%d.log" % cls.port)
        root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        env = {"SYSTEMROOT": root, "WINDIR": root, "PATH": os.path.join(root, "System32"),
               "TEMP": C.TMP, "TMP": C.TMP}                           # env สะอาด: ไม่มีตัวแปรลับของผู้เรียก
        cmd = [exe, "--embeddings", "--pooling", "last", "-m", EMBED_MODEL, "-ngl", "0", "--device", "none",
               "-c", "8192", "-t", "4", "--api-key-file", C.TOKEN_FILE, "--host", "127.0.0.1",
               "--port", str(cls.port), "--no-webui", "--cors-origins", "http://127.0.0.1:%d" % cls.port,
               "--no-cors-credentials"]
        cls.logfh = open(cls.log, "wb")
        cls.proc = subprocess.Popen(cmd, cwd=os.path.dirname(exe), env=env, stdout=cls.logfh,
                                    stderr=subprocess.STDOUT,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 90
        ok = False
        while time.monotonic() < deadline and cls.proc.poll() is None:
            try:
                st = C.http("GET", cls.port, "/health")[0]
                if st == 200:
                    ok = True
                    break
            except Exception:                                        # noqa: BLE001
                pass
            time.sleep(0.5)
        if not ok:
            cls.tearDownClass()
            raise unittest.SkipTest("เปิดบริการ embedding ทดสอบไม่สำเร็จ (ดู %s)" % cls.log)
        cls._env = {k: os.environ.get(k) for k in (tools_kb.EMBED_URL_ENV, tools_kb.HUB_URL_ENV)}
        os.environ[tools_kb.EMBED_URL_ENV] = "http://127.0.0.1:%d" % cls.port
        os.environ[tools_kb.HUB_URL_ENV] = CLOSED
        tools_kb.reset_embed_state()
        cls.p = _proj("live")
        for pid, text in PASSAGES.items():
            _put(cls.p, "attachments/%s.txt" % pid, text)
        with guard.project_scope(cls.p):
            tools_kb.kb_search(query="ตู้ชาร์จ", project=cls.p)       # ทำดัชนี + ปลุกงาน embed เบื้องหลัง
        t0 = time.monotonic()
        done = tools_kb.wait_background(cls.p, 600)
        cls.embed_secs = time.monotonic() - t0
        if not done:
            cls.tearDownClass()
            raise unittest.SkipTest("embed เบื้องหลังไม่เสร็จใน 10 นาที (เครื่องยุ่ง?)")

    @classmethod
    def tearDownClass(cls):
        tools_kb.stop_background()
        proc = getattr(cls, "proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(15)
        if getattr(cls, "logfh", None):
            cls.logfh.close()
        for k, v in (getattr(cls, "_env", None) or {}).items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        tools_kb.reset_embed_state()

    def _mrr(self, mode):
        base = _base(self.p)
        total, ranks = 0.0, []
        with guard.project_scope(self.p):
            for q, want in PARAPHRASES:
                hits, _n, info = tools_kb.search_hybrid(base, q, 5, mode)
                self.assertEqual(info["note"], "", info)
                rank = next((i + 1 for i, h in enumerate(hits) if h["file"] == "attachments/%s.txt" % want), None)
                ranks.append(rank)
                total += 1.0 / rank if rank else 0.0
        return total / len(PARAPHRASES), ranks

    def test_semantic_beats_lexical_on_paraphrased_thai(self):
        with guard.project_scope(self.p):
            st = tools_kb.index_status(_base(self.p))
        self.assertEqual(st["vectors"], st["chunks"])
        lex, lex_r = self._mrr("lexical")
        sem, sem_r = self._mrr("semantic")
        auto, auto_r = self._mrr("auto")
        print("\n[semantic-live] port %d, embed %d chunks in %.1fs | MRR lexical %.3f semantic %.3f auto %.3f"
              % (self.port, st["chunks"], self.embed_secs, lex, sem, auto))
        print("[semantic-live] ranks lexical=%s semantic=%s auto=%s" % (lex_r, sem_r, auto_r))
        self.assertGreaterEqual(sem, 0.75)
        self.assertGreaterEqual(sem, lex + 0.4)
        self.assertGreaterEqual(auto, lex + 0.4)
        self.assertGreaterEqual(sum(1 for r in sem_r if r and r <= 3), len(PARAPHRASES) - 1)

    def test_irrelevant_query_finds_nothing_and_exact_code_stays_first(self):
        with guard.project_scope(self.p):
            none = tools_kb.kb_search(query="ควอนตัมฟิสิกส์ดาราศาสตร์", project=self.p)
            code = tools_kb.kb_search(query="E-217", project=self.p)
        self.assertIn("ค้นแบบผสม: คำตรง + ความหมาย", none)
        self.assertIn("ไม่พบเนื้อหา", none)
        self.assertIn("[1] attachments/P12.txt", code)


if __name__ == "__main__":
    unittest.main()
