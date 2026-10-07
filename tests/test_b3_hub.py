# -*- coding: utf-8 -*-
"""
batch 3 (owner hub) — สายไฟของ D1/D2/D3 ใน hub.py ผ่าน proxy จริง (พอร์ตสุ่ม) + llama-server ปลอม

  D1  แชตจากหน้าเว็บที่ยาวเกินเพดานถูกย่อก่อนส่งต่อ, header X-Qwen-Compacted, โน้ตใน GET /_qwen/usage,
      เทิร์นถัดไปใช้สรุปเดิม (ไบต์ต้นคำขอเหมือนเดิม), client ที่ไม่ใช่หน้าเว็บไม่ถูกแตะ, คำขอเล็กไม่ถูกแตะ,
      POST /_qwen/compact (สั่งย่อเอง), โมเดลสรุปล่ม = ยังตอบได้ (สรุปตัดตอน), กฎ Origin ของ /_qwen/usage|compact
  D2  หนึ่งบรรทัดต่อคำตอบใน data\\usage.jsonl (ทั้งทาง Extend Mode และทางส่งต่อปกติ), ตัวเลขจาก timings, ชื่อเครื่องมือ,
      ไม่มีเนื้อหาข้อความ, pre-encode ไม่ถูกนับ, upstream error = error true, ผู้ใช้ตัดสาย = ไม่ใช่ error
      GET /api/usage บน hub (กฎ Origin)
  D3  GET /api/doctor บน hub (กฎ Origin, format=text) — ตัวตรวจจริงอยู่ใน test_b3_doctor.py

ปลอดภัยต่อระบบจริง: DATA_ROOT / settings.json / โทเคน ชี้โฟลเดอร์ชั่วคราว, upstream เป็นเซิร์ฟเวอร์ปลอม,
โมเดลสรุปเป็นตัวปลอม, ctx ของโมเดลถูกแทนเป็นค่าเล็ก, auto_kb ปิด (ไม่เรียก MCP จริง)
"""
import copy
import http.client
import importlib.util
import json
import os
import re
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HUB = r"C:\LLM\projects\hub.py"
TOKEN_ENV = "LLM_LOCAL_TOKEN_FILE"
HERE = os.path.dirname(os.path.abspath(__file__))


def load_hub():
    sys.path.insert(0, os.path.dirname(HUB))
    spec = importlib.util.spec_from_file_location("hub_b3_under_test", HUB)
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hub = load_hub()
fx = _load("b3_fixture_for_hub", os.path.join(HERE, "test_b3_fixture.py"))
SLUG = "b3test"
MODEL = "Qwen3-4B-Instruct-2507-Q4_K_M"
SECRET_TEXT = "ZEBRA-CONTENT-7731"          # ห้ามโผล่ใน usage.jsonl
TIMINGS = {"cache_n": 100, "prompt_n": 900, "prompt_ms": 1000.0, "prompt_per_second": 900.0,
           "predicted_n": 42, "predicted_ms": 2000.0, "predicted_per_second": 21.0}


def ev(text=None, fin=None, timings=None, tool=None):
    d = {}
    if text is not None:
        d["content"] = text
    if tool:
        d["tool_calls"] = [{"index": 0, "id": "call_x", "type": "function", "function": {"name": tool, "arguments": ""}}]
    e = {"choices": [{"delta": d, "finish_reason": fin}], "model": MODEL}
    if timings:
        e["timings"] = timings
    return e


DEFAULT_SCRIPT = [ev(tool="local_read"), ev("ตอบ " + SECRET_TEXT, timings=dict(TIMINGS, predicted_n=1)),
                  ev(None, "stop", timings=TIMINGS), "[DONE]"]


class _Up(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    posts = []          # (path, headers, raw bytes, doc)
    scripts = []
    gate = None
    status = 200

    def log_message(self, *a):
        pass

    def do_GET(self):
        data = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        cls = type(self)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        try:
            doc = json.loads(raw.decode("utf-8"))
        except ValueError:
            doc = None
        cls.posts.append((self.path, {k.lower(): v for k, v in self.headers.items()}, raw, doc))
        if cls.status != 200:
            data = json.dumps({"error": {"code": cls.status, "message": "boom"}}).encode()
            self.send_response(cls.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if isinstance(doc, dict) and doc.get("stream"):
            idx = len([p for p in cls.posts if isinstance(p[3], dict) and p[3].get("stream")])
            events = cls.scripts[idx - 1] if idx - 1 < len(cls.scripts) else DEFAULT_SCRIPT
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for e in events:
                    if e == "WAIT":
                        cls.gate.wait(10)
                        continue
                    if isinstance(e, tuple) and e[0] == "SLEEP":       # [fix-hub b3] โมเดลที่เขียนช้า
                        time.sleep(e[1])
                        continue
                    data = b"data: " + (b"[DONE]" if e == "[DONE]" else json.dumps(e, ensure_ascii=False).encode()) + b"\n\n"
                    self.wfile.write(b"%x\r\n" % len(data) + data + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
            except OSError:
                pass
            return
        body = {"choices": [{"message": {"role": "assistant", "content": "ok " + SECRET_TEXT}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 77, "completion_tokens": 5}, "timings": dict(TIMINGS, predicted_n=5)}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Stub:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
        self.delay = 0.0

    def __call__(self, messages, timeout_s=None, model_id=None):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise OSError("down")
        return "## งานหรือคำถามที่ยังค้าง\n- สั่งซื้อฟิวส์ 125 A 6 ตัว\n## ข้อเท็จจริงและตัวเลข\n- C-03 92 °C 398 V"


def _req(port, method, path, headers=None, body=None, timeout=20):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, data


class _Env(unittest.TestCase):
    ctx = 6000
    extend = True

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b3hub-"))
        self.data = self.tmp / "data"
        self.data.mkdir()
        settings = self.tmp / "settings.json"
        settings.write_text(json.dumps({"lang": "th", "theme": "dark", "font": "serif"}), encoding="utf-8")
        tok = self.tmp / "local-services.token"
        tok.write_text(secrets.token_hex(32), encoding="ascii")        # ค่าทดสอบ ไม่ใช่โทเคนจริง
        self.stub = Stub()
        hub._router_tbl.update(at=0.0, table=None)
        self.patches = [mock.patch.dict(os.environ, {TOKEN_ENV: str(tok)}),
                        mock.patch.object(hub, "DATA_ROOT", self.data),
                        mock.patch.object(hub, "SETTINGS", settings),
                        mock.patch.object(hub, "upstream_models", return_value=[]),
                        mock.patch.object(hub, "upstream_model", return_value=""),
                        mock.patch.object(hub, "model_ctx", side_effect=lambda m: self.ctx),
                        mock.patch.object(hub, "_summarize_via_router", side_effect=lambda *a, **k: self.stub(*a, **k)),
                        mock.patch.dict(hub._compact_notes, {}, clear=True),
                        mock.patch.dict(hub._force_compact, {}, clear=True),
                        mock.patch.dict(hub._calib, {}, clear=True)]
        for p in self.patches:
            p.start()
        _Up.posts, _Up.scripts, _Up.status = [], [], 200
        _Up.gate = threading.Event()
        self.up = ThreadingHTTPServer(("127.0.0.1", 0), _Up)
        self.up.daemon_threads = True
        self.up.handle_error = lambda *a: None
        threading.Thread(target=self.up.serve_forever, daemon=True).start()
        p = mock.patch.object(hub, "UPSTREAM_PORT", self.up.server_address[1])
        p.start()
        self.patches.append(p)
        self.proj = {"slug": SLUG, "name": "ทดสอบ b3", "port": 0, "system_prompt": "", "think": "off",
                     "extend": self.extend, "auto_kb": False, "model": ""}
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), hub.make_proxy_handler(SLUG, lambda: [self.proj]))
        self.srv.daemon_threads = True
        self.srv.handle_error = lambda *a: None
        self.port = self.srv.server_address[1]
        self.proj["port"] = self.port
        self.own = "http://127.0.0.1:%d" % self.port
        p = mock.patch.object(hub, "ALLOWED_ORIGIN", re.compile(
            r"^http://(127\.0\.0\.1|localhost):(8100|81[0-7][0-9]|%d)$" % self.port))
        p.start()
        self.patches.append(p)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        _Up.gate.set()
        self.srv.shutdown()
        self.srv.server_close()
        self.up.shutdown()
        self.up.server_close()
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)        # โฟลเดอร์ชั่วคราวของเทสต์นี้เอง

    def chat(self, messages, origin=True, conv="conv-1", extra=None, headers=None, **doc_extra):
        doc = {"model": MODEL, "stream": True, "messages": messages, "tools": fx.TOOLS}
        doc.update(doc_extra)
        h = {"Content-Type": "application/json"}
        if origin:
            h["Origin"] = self.own
        if conv:
            h["X-Conversation-Id"] = conv + "::" + MODEL
        h.update(headers or {})
        return _req(self.port, "POST", "/v1/chat/completions", h, json.dumps(doc, ensure_ascii=False).encode("utf-8"))

    def usage_rows(self):
        p = self.data / "usage.jsonl"
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    def wait_rows(self, n, timeout=5):
        end = time.time() + timeout
        while time.time() < end:
            rows = self.usage_rows()
            if len(rows) >= n:
                return rows
            time.sleep(0.05)
        return self.usage_rows()

    def get_usage(self, conv=None, origin="own", site=None):
        h = {}
        if origin == "own":
            h["Origin"] = self.own
        elif origin:
            h["Origin"] = origin
        if site:
            h["Sec-Fetch-Site"] = site
        st, hd, data = _req(self.port, "GET", "/_qwen/usage" + ("?conversation=" + conv if conv else ""), h)
        return st, (json.loads(data) if data and st == 200 else None)


class CompactionHubTests(_Env):
    def test_long_webui_chat_compacted_with_header_note_and_usage(self):
        msgs = fx.build_long_conversation()
        st, hd, data = self.chat(msgs)
        self.assertEqual(st, 200)
        self.assertIn("x-qwen-compacted", hd)
        n = int(hd["x-qwen-compacted"])
        self.assertGreater(n, 0)
        self.assertEqual(self.stub.calls, 1)
        sent = _Up.posts[-1][3]["messages"]
        self.assertTrue(sent[0]["content"].startswith("You are"))      # base prompt ของ hub ยังอยู่ที่ system
        self.assertEqual(sent[1], msgs[1])
        self.assertTrue(sent[2]["content"].startswith(hub._compact.LABEL))
        self.assertEqual(sent[-1], msgs[-1])
        self.assertLess(len(sent), len(msgs))
        self.assertIn(b"data: [DONE]", data)
        # โน้ตให้หน้าเว็บ
        st, note = self.get_usage("conv-1")
        self.assertEqual(st, 200)
        self.assertEqual(note["compaction"]["turns"], n)
        self.assertIn("(%d รอบ)" % n, note["compaction"]["message_th"])
        self.assertIn("%d turn" % n, note["compaction"]["message_en"])
        self.assertIn("tooltip_th", note["compaction"])
        self.assertLess(note["compaction"]["after_tokens"], note["compaction"]["before_tokens"])
        self.assertNotIn("สั่งซื้อฟิวส์", json.dumps(note, ensure_ascii=False))       # ไม่มีเนื้อหาของสรุปในโน้ต
        # บันทึกการใช้งาน
        rows = self.wait_rows(1)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(set(r), set(hub._usage.FIELDS))
        self.assertEqual((r["project"], r["model"], r["prompt_tokens"], r["cached_tokens"], r["completion_tokens"]),
                         (SLUG, MODEL, 1000, 100, 42))
        self.assertEqual((r["prompt_tps"], r["gen_tps"]), (900.0, 21.0))
        self.assertEqual(r["tools_used"], ["local_read"])
        self.assertTrue(r["compacted"])
        self.assertFalse(r["error"])
        self.assertEqual(r["conv"], hub._usage.conv_hash("conv-1"))
        self.assertNotIn(SECRET_TEXT, (self.data / "usage.jsonl").read_text(encoding="utf-8"))
        st, note2 = self.get_usage()
        self.assertEqual(note2["last"]["completion_tokens"], 42)
        self.assertEqual(note2["compaction"]["turns"], n)                 # ไม่ระบุแชต = ครั้งล่าสุดของโปรเจกต์

    def test_next_turn_reuses_summary_and_prefix_bytes(self):
        msgs = fx.build_long_conversation()
        st1, hd1, _ = self.chat(msgs)
        raw1 = _Up.posts[-1][2]
        msgs2 = msgs + [{"role": "assistant", "content": "สรุปงานสัปดาห์หน้า: เปลี่ยนรีเลย์ K2"},
                        {"role": "user", "content": "ขอบคุณ แล้วงบเหลือเท่าไร"}]
        st2, hd2, _ = self.chat(msgs2)
        raw2 = _Up.posts[-1][2]
        self.assertEqual(self.stub.calls, 1)
        self.assertEqual(hd1["x-qwen-compacted"], hd2["x-qwen-compacted"])
        common = len(os.path.commonprefix([raw1, raw2]))
        last_user = json.dumps(msgs[-1], ensure_ascii=False).encode("utf-8")
        self.assertIn(last_user, raw1)
        # ทุกไบต์จนถึงข้อความสุดท้ายของรอบก่อนเหมือนเดิม = llama.cpp ใช้ KV cache ต่อได้
        self.assertGreater(common, raw1.index(last_user) + len(last_user) - 2)
        st, note = self.get_usage("conv-1")
        self.assertTrue(note["compaction"]["reused"])

    def test_non_webui_client_and_small_chat_untouched(self):
        msgs = fx.build_long_conversation()
        st, hd, _ = self.chat(msgs, origin=False, conv=None)
        self.assertNotIn("x-qwen-compacted", hd)
        self.assertEqual(len(_Up.posts[-1][3]["messages"]), len(msgs))     # ไม่แตะ prompt ของสคริปต์
        st, hd, _ = self.chat(msgs[:5] + [{"role": "user", "content": "สั้นๆ"}])
        self.assertNotIn("x-qwen-compacted", hd)
        self.assertEqual(self.stub.calls, 0)
        rows = self.wait_rows(2)
        self.assertEqual([r["compacted"] for r in rows], [False, False])
        self.assertIsNone(rows[0]["conv"])
        self.assertFalse((self.data / SLUG / "compaction").exists())
        self.assertFalse((self.data / hub.COMPACT_CACHE_DIR).exists())

    def test_preencode_compacted_but_not_logged(self):
        msgs = fx.build_long_conversation()
        st, hd, data = self.chat(msgs, conv=None, stream=False, n_predict=0)
        self.assertEqual(st, 200)
        self.assertIn("x-qwen-compacted", hd)
        self.assertTrue(_Up.posts[-1][3]["messages"][2]["content"].startswith(hub._compact.LABEL))
        st, hd, _ = self.chat(msgs)                       # คำขอจริงตามมา (มี X-Conversation-Id) = ใช้สรุปเดียวกัน
        self.assertEqual(self.stub.calls, 1)
        rows = self.wait_rows(1)
        time.sleep(0.2)
        self.assertEqual(len(self.usage_rows()), 1)       # pre-encode ไม่ถูกนับ

    def test_manual_compact_request(self):
        msgs = fx.build_long_conversation()[:12] + [{"role": "user", "content": "ต่อ"}]
        h = {"Origin": self.own}
        st, _, _ = _req(self.port, "POST", "/_qwen/compact", dict(h, **{"Content-Type": "text/plain"}),
                        b'{"conversation":"conv-9"}')
        self.assertEqual(st, 415)
        st, _, _ = _req(self.port, "POST", "/_qwen/compact", dict(h, **{"Content-Type": "application/json"}), b'{}')
        self.assertEqual(st, 400)
        st, _, data = _req(self.port, "POST", "/_qwen/compact", dict(h, **{"Content-Type": "application/json"}),
                           b'{"conversation":"conv-9"}')
        self.assertEqual(st, 202)
        self.assertTrue(json.loads(data)["scheduled"])
        st, hd, _ = self.chat(msgs, conv="conv-other")    # แชตอื่นไม่โดน
        self.assertNotIn("x-qwen-compacted", hd)
        st, hd, _ = self.chat(msgs, conv="conv-9")
        self.assertIn("x-qwen-compacted", hd)
        st, note = self.get_usage("conv-9")
        self.assertTrue(note["compaction"]["forced"])

    def test_summarizer_down_still_answers(self):
        self.stub.fail = True
        st, hd, data = self.chat(fx.build_long_conversation())
        self.assertEqual(st, 200)
        self.assertIn("x-qwen-compacted", hd)
        st, note = self.get_usage("conv-1")
        self.assertTrue(note["compaction"]["fallback"])

    def test_cache_lives_outside_project_folder(self):
        """[fix-hub b3] แคชสรุปอยู่ data\\_compaction.cache\\<slug> (guard ปฏิเสธเครื่องมือของทุกโปรเจกต์ — S04 other_project)
        ไม่ใช่ data\\<slug>\\compaction ที่เครื่องมือของโปรเจกต์อ่าน/เขียนได้"""
        self.chat(fx.build_long_conversation())
        files = list((self.data / hub.COMPACT_CACHE_DIR / SLUG).glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertFalse((self.data / SLUG / "compaction").exists())
        self.assertIn(".", hub.COMPACT_CACHE_DIR)                        # slug ไม่มีทางมี "." — ชนกับโปรเจกต์ไม่ได้
        self.assertNotEqual(hub.data_slug(hub.COMPACT_CACHE_DIR), hub.COMPACT_CACHE_DIR)
        # ลบโปรเจกต์ = ย้ายแคชไปถังขยะด้วย (ย้าย ไม่ลบ)
        (self.data / SLUG).mkdir(exist_ok=True)
        dst = Path(hub.archive_project_data(SLUG))
        self.assertTrue((dst / "compaction-cache").is_dir())
        self.assertFalse((self.data / hub.COMPACT_CACHE_DIR / SLUG).exists())

    def test_in_progress_note_while_summarizing(self):
        """[fix-hub b3] ระหว่างรอโมเดลสรุป หน้าเว็บถาม /_qwen/usage ได้ว่า "กำลังสรุป…" (เดิมเห็นแค่วงหมุนเงียบ 3 นาที)"""
        self.stub.delay = 1.5
        out = {}
        t = threading.Thread(target=lambda: out.setdefault("r", self.chat(fx.build_long_conversation())))
        t.start()
        note = None
        end = time.time() + 5
        while time.time() < end and not note:
            time.sleep(0.1)
            st, d = self.get_usage("conv-1")
            note = (d or {}).get("in_progress")
        t.join(20)
        self.assertIsNotNone(note)
        self.assertEqual(note["state"], "summarizing")
        self.assertIn("กำลังสรุป", note["message_th"])
        self.assertIn("Summarizing", note["message_en"])
        self.assertGreater(note["turns"], 0)
        self.assertNotIn("_t0", note)
        st, d = self.get_usage("conv-1")
        self.assertIsNone(d["in_progress"])                              # จบแล้ว = หายไป
        self.assertEqual(out["r"][0], 200)

    def test_summary_text_route(self):
        st, _, _ = _req(self.port, "GET", "/_qwen/compact/summary?conversation=conv-1", {"Origin": self.own})
        self.assertEqual(st, 404)                                         # ยังไม่มี
        self.chat(fx.build_long_conversation())
        st, _, data = _req(self.port, "GET", "/_qwen/compact/summary?conversation=conv-1", {"Origin": self.own})
        self.assertEqual(st, 200)
        d = json.loads(data)
        self.assertIn("C-03", d["summary"])
        self.assertGreater(d["turns"], 0)
        st, _, _ = _req(self.port, "GET", "/_qwen/compact/summary?conversation=conv-1",
                        {"Origin": "http://127.0.0.1:8101"})
        self.assertEqual(st, 403)                                         # หน้าของโปรเจกต์อื่นอ่านไม่ได้
        st, _, _ = _req(self.port, "GET", "/_qwen/compact/summary?conversation=other", {"Origin": self.own})
        self.assertEqual(st, 404)
        st, _, _ = _req(self.port, "GET", "/_qwen/compact/summary?conversation=bad%20id%3C", {"Origin": self.own})
        self.assertEqual(st, 400)

    def test_decision_note_follows_project_kb_result(self):
        """[fix-hub b3] แชตที่ย่อแล้ว + ผลค้นเอกสารสังเคราะห์ของ hub: ท้ายผลค้นมีบรรทัด "สิ่งที่ตกลงแล้ว" จากสรุป (วัด 4B: 3/3 vs 0/3)"""
        msgs = fx.build_long_conversation()
        q = msgs[-1]["content"]
        kb = hub.context_messages([{"kind": "kb", "arg": q, "result": "ผลค้น: ควรเปลี่ยนรีเลย์ภายในไตรมาสนี้"}], {"local_read"})
        decided = ("## การตัดสินใจและสิ่งที่ตกลงแล้ว (ยังมีผล)\n- เปลี่ยนรีเลย์ K2 ของตู้ C-03 ภายในวันที่ 15 ต.ค. 2569\n"
                   "## ข้อเท็จจริงและตัวเลข\n- C-03 92 °C 398 V")
        with mock.patch.object(hub, "_summarize_via_router", side_effect=lambda *a, **k: decided), \
                mock.patch.object(hub, "apply_project_context",
                                  side_effect=lambda doc, proj: doc["messages"].extend(copy.deepcopy(kb)) or True):
            st, hd, _ = self.chat(msgs)
        self.assertIn("x-qwen-compacted", hd)
        sent = _Up.posts[-1][3]["messages"]
        last_tool = sent[-1]
        self.assertEqual(last_tool["role"], "tool")
        self.assertTrue(last_tool["content"].startswith("ผลค้น:"))
        self.assertIn("สิ่งที่ผู้ใช้ตกลงไว้แล้วในแชตนี้", last_tool["content"])
        self.assertIn("- เปลี่ยนรีเลย์ K2 ของตู้ C-03 ภายในวันที่ 15 ต.ค. 2569", last_tool["content"])
        # ไม่มีผลค้นของ hub = ไม่แตะ (ไม่ต่อท้ายข้อความผู้ใช้/ผลเครื่องมืออื่น)
        doc = {"messages": [{"role": "user", "content": "q"}, {"role": "assistant", "content": hub._compact.LABEL + "\n" + decided},
                            {"role": "user", "content": "q2"}]}
        self.assertFalse(hub.apply_decision_note(doc))

    def test_compact_scrub_removes_key_shapes_and_local_token(self):
        tok = Path(os.environ[TOKEN_ENV]).read_text(encoding="ascii").strip()      # โทเคนทดสอบของเทสต์นี้
        hub._compact_scrub_fn.update(loaded=False, fn=None)
        try:
            raw = ("โทเคน %s คีย์ sk-%s ghp_%s Authorization: Bearer %s api_key=%s sha256 %s"
                   % (tok, "a" * 24, "b" * 30, "c" * 20, "d" * 12, "e" * 64))
            out = hub.compact_scrub(raw)
        finally:
            hub._compact_scrub_fn.update(loaded=False, fn=None)
        for gone in (tok, "a" * 24, "b" * 30, "c" * 20, "d" * 12):
            self.assertNotIn(gone, out)
        self.assertIn("e" * 64, out)                                     # sha256 ของไฟล์เป็นข้อเท็จจริง ไม่ใช่ความลับ

    def test_usage_and_compact_routes_are_own_origin_only(self):
        st, _ = self.get_usage(origin="http://127.0.0.1:8101")
        self.assertEqual(st, 403)
        st, _ = self.get_usage(origin=None, site="cross-site")
        self.assertEqual(st, 403)
        st, _ = self.get_usage(origin="https://evil.example")
        self.assertEqual(st, 403)
        st, _ = self.get_usage(origin=None)                   # สคริปต์ในเครื่อง
        self.assertEqual(st, 200)
        st, _, _ = _req(self.port, "POST", "/_qwen/compact", {"Origin": "http://127.0.0.1:8101",
                                                               "Content-Type": "application/json"},
                        b'{"conversation":"x"}')
        self.assertEqual(st, 403)
        self.assertEqual([p for p in _Up.posts if "/_qwen/" in p[0]], [])   # ไม่ถูกส่งต่อไป llama-server


class UsageHubTests(_Env):
    def test_upstream_error_and_nonstream(self):
        _Up.status = 500
        st, hd, _ = self.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(st, 500)
        _Up.status = 200
        st, hd, data = self.chat([{"role": "user", "content": "hi " + SECRET_TEXT}], stream=False)
        self.assertEqual(st, 200)
        rows = self.wait_rows(2)
        self.assertTrue(rows[0]["error"])
        self.assertFalse(rows[1]["error"])
        self.assertEqual(rows[1]["prompt_tokens"], 1000)          # timings ชนะ usage (นับ cache ด้วย)
        self.assertEqual(rows[1]["completion_tokens"], 5)
        self.assertNotIn(SECRET_TEXT, (self.data / "usage.jsonl").read_text(encoding="utf-8"))

    def test_extend_mode_segments_are_summed(self):
        seg1 = [ev("ส่วนแรก"), ev(None, "length", timings=dict(TIMINGS, predicted_n=30, predicted_ms=1500.0)), "[DONE]"]
        seg2 = [ev("ส่วนต่อ"), ev(None, "stop", timings=dict(TIMINGS, prompt_n=5, cache_n=1000, predicted_n=20,
                                                              predicted_ms=500.0)), "[DONE]"]
        _Up.scripts = [seg1, seg2]
        st, hd, data = self.chat([{"role": "user", "content": "เขียนยาวๆ"}], max_tokens=30)
        self.assertEqual(st, 200)
        self.assertEqual(len(_Up.posts), 2)
        rows = self.wait_rows(1)
        r = rows[0]
        self.assertEqual(r["completion_tokens"], 50)
        self.assertEqual(r["prompt_tokens"], 1000)                  # คิดจากท่อนแรก
        self.assertEqual(r["gen_tps"], 24.0)                        # [fix-hub b3] (29 + 19) ช่วง / 2.0 วินาที แบบ llama-server
        self.assertFalse(r["error"])

    def test_client_abort_is_not_error(self):
        _Up.scripts = [[ev("เริ่ม"), "WAIT", ev("ต่อ"), ev(None, "stop", timings=TIMINGS), "[DONE]"]]
        doc = {"model": MODEL, "stream": True, "messages": [{"role": "user", "content": "x"}]}
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        body = json.dumps(doc).encode()
        s.sendall(b"POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nOrigin: %s\r\n"
                  b"Content-Type: application/json\r\nContent-Length: %d\r\n\r\n" % (self.port, self.own.encode(), len(body))
                  + body)
        s.recv(200)
        s.close()                                                   # ผู้ใช้กดหยุด
        time.sleep(0.3)
        _Up.gate.set()
        rows = self.wait_rows(1, timeout=8)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["error"])


class GenericPathTests(_Env):
    extend = False                    # ปิด Extend Mode = คำตอบสตรีมวิ่งทางส่งต่อปกติ (read1)

    def test_generic_stream_path_header_and_usage(self):
        st, hd, data = self.chat(fx.build_long_conversation())
        self.assertEqual(st, 200)
        self.assertIn("x-qwen-compacted", hd)
        rows = self.wait_rows(1)
        self.assertEqual((rows[0]["prompt_tokens"], rows[0]["completion_tokens"], rows[0]["tools_used"]),
                         (1000, 42, ["local_read"]))
        self.assertTrue(rows[0]["compacted"])


class SummarizerCallTests(unittest.TestCase):
    """_summarize_via_router ตัวจริงกับ llama-server ปลอม: ชน max_tokens = PartialText (บรรทัดท้ายที่ยังไม่จบถูกตัด)"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b3sum-"))
        tok = self.tmp / "local-services.token"
        tok.write_text(secrets.token_hex(32), encoding="ascii")        # ค่าทดสอบ ไม่ใช่โทเคนจริง
        _Up.posts, _Up.scripts, _Up.status = [], [], 200
        _Up.gate = threading.Event()
        self.up = ThreadingHTTPServer(("127.0.0.1", 0), _Up)
        self.up.daemon_threads = True
        self.up.handle_error = lambda *a: None
        threading.Thread(target=self.up.serve_forever, daemon=True).start()
        self.patches = [mock.patch.dict(os.environ, {TOKEN_ENV: str(tok)}),
                        mock.patch.object(hub, "UPSTREAM_PORT", self.up.server_address[1]),
                        mock.patch.object(hub, "upstream_models", return_value=[MODEL])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        _Up.gate.set()
        self.up.shutdown()
        self.up.server_close()
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)        # โฟลเดอร์ชั่วคราวของเทสต์นี้เอง

    def test_length_finish_is_partial_and_drops_unfinished_line(self):
        _Up.scripts = [[ev("## งานค้าง\n- สั่งฟิวส์\n## ข้อเท็จจริง\n- C-03 92 °C\n- ตู้ R-0"), ev(None, "length"), "[DONE]"]]
        out = hub._summarize_via_router([{"role": "user", "content": "x"}], timeout_s=20)
        self.assertTrue(getattr(out, "partial", False))
        self.assertTrue(out.endswith("- C-03 92 °C"))
        sent = _Up.posts[-1][3]
        self.assertEqual(sent["model"], MODEL)
        self.assertEqual(sent["max_tokens"], hub._compact.SUMMARY_CALL_MAX_TOKENS)
        self.assertTrue(sent["stream"])

    def test_stop_finish_is_complete(self):
        _Up.scripts = [[ev("## งานค้าง\n- สั่งฟิวส์"), ev(None, "stop"), "[DONE]"]]
        out = hub._summarize_via_router([{"role": "user", "content": "x"}], timeout_s=20)
        self.assertFalse(getattr(out, "partial", False))
        self.assertEqual(out, "## งานค้าง\n- สั่งฟิวส์")

    def test_http_error_raises(self):
        _Up.status = 503
        with self.assertRaises(OSError):
            hub._summarize_via_router([{"role": "user", "content": "x"}], timeout_s=20)

    def test_slow_model_stops_early(self):
        """[fix-hub b3] โมเดลเขียน ~4 โทเคน/วินาที คาดว่าไม่จบใน 20 วินาที (ต้อง ≥ 250 โทเคน) — หยุดหลังวัดความเร็วได้ ไม่รอจนเส้นตาย"""
        events = []
        for i in range(200):
            events += [("SLEEP", 0.25), ev("- ข้อ %d\n" % i)]
        _Up.scripts = [events + [ev(None, "stop"), "[DONE]"]]
        t0 = time.monotonic()
        out = hub._summarize_via_router([{"role": "user", "content": "x"}], timeout_s=20)
        took = time.monotonic() - t0
        self.assertLess(took, 12)
        self.assertTrue(getattr(out, "partial", False))
        self.assertEqual(out.reason, "slow")
        self.assertTrue(out.startswith("- ข้อ 0"))

    def test_slow_prompt_phase_stops_before_first_token(self):
        """[fix-hub b3] อ่านพรอมต์ 500 โทเคน/วินาที เหลือ 18,000 = ~36 วินาที เกินงบ 20 — หยุดตั้งแต่ช่วงอ่านพรอมต์ (ก่อนโทเคนแรก)
        เหตุการณ์จริง 2026-10-07: GPU หายกลางทาง 4B ไม่ส่งโทเคนเลยตลอด 180 วินาที"""
        events = []
        for i in range(1, 40):
            events += [("SLEEP", 0.5), {"choices": [{"delta": {}, "finish_reason": None}],
                                        "prompt_progress": {"total": 20000, "cache": 0, "processed": 250 * i,
                                                            "time_ms": 500.0 * i}}]
        _Up.scripts = [events + [ev("- ข้อ 1\n"), ev(None, "stop"), "[DONE]"]]
        t0 = time.monotonic()
        out = hub._summarize_via_router([{"role": "user", "content": "x"}], timeout_s=20)
        self.assertLess(time.monotonic() - t0, 8)
        self.assertEqual((getattr(out, "reason", ""), str(out)), ("slow", ""))
        self.assertTrue(_Up.posts[-1][3]["return_progress"])

    def test_fast_prompt_phase_continues(self):
        events = [{"choices": [{"delta": {}, "finish_reason": None}],
                   "prompt_progress": {"total": 2000, "cache": 0, "processed": 500 * i, "time_ms": 1000.0 * i}}
                  for i in range(1, 5)]
        _Up.scripts = [events + [ev("- ข้อ 1\n"), ev(None, "stop"), "[DONE]"]]
        out = hub._summarize_via_router([{"role": "user", "content": "x"}], timeout_s=20)
        self.assertFalse(getattr(out, "partial", False))
        self.assertEqual(out, "- ข้อ 1\n")

    def test_fast_model_is_not_stopped(self):
        events = [ev("- ข้อ %d\n" % i) for i in range(60)]
        _Up.scripts = [events + [ev(None, "stop"), "[DONE]"]]
        out = hub._summarize_via_router([{"role": "user", "content": "x"}], timeout_s=20)
        self.assertFalse(getattr(out, "partial", False))
        self.assertIn("- ข้อ 59", out)


class HubApiTests(unittest.TestCase):
    """GET /api/usage และ /api/doctor บน HubHandler (พอร์ตสุ่ม)"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b3api-"))
        self.patches = [mock.patch.object(hub, "DATA_ROOT", self.tmp),
                        mock.patch.object(hub, "load_projects", return_value=[{"slug": "p1", "name": "โปรเจกต์หนึ่ง", "port": 8101}])]
        for p in self.patches:
            p.start()
        log = hub._usage.UsageLog(lambda: self.tmp)
        for i in range(3):
            log.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"), "project": "p1", "model": MODEL,
                        "prompt_tokens": 1000, "cached_tokens": 100, "completion_tokens": 50, "prompt_tps": 500.0,
                        "gen_tps": 25.0, "wall_s": 3.0, "tools_used": ["web_search"], "compacted": i == 2,
                        "error": False, "conv": "abc"})
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), hub.HubHandler)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_usage_api_and_origin_rules(self):
        st, hd, data = _req(self.port, "GET", "/api/usage?days=7", {"Origin": "http://127.0.0.1:8100"})
        self.assertEqual(st, 200)
        self.assertEqual(hd.get("access-control-allow-origin"), "http://127.0.0.1:8100")
        d = json.loads(data)
        self.assertEqual(d["totals"]["requests"], 3)
        self.assertEqual(d["totals"]["compacted"], 1)
        self.assertEqual(len(d["per_day"]), 7)
        self.assertEqual(d["per_project"][0]["name"], "โปรเจกต์หนึ่ง")
        self.assertEqual(d["per_model"][0]["gen_tps"], 25.0)
        self.assertEqual(d["sessions"][0]["requests"], 3)
        for h in ({"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}, {"Origin": "null"}):
            st, _, _ = _req(self.port, "GET", "/api/usage", h)
            self.assertEqual(st, 403, h)
        st, _, data = _req(self.port, "GET", "/api/usage?days=abc", {})
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(data)["days"], 7)
        st, _, data = _req(self.port, "GET", "/api/usage?days=999", {})
        self.assertEqual(json.loads(data)["days"], 90)

    def test_doctor_api(self):
        canned = {"checked_at": "2026-10-06T10:00:00+07:00", "overall": "ok",
                  "services": [{"id": "stt", "name_th": "พูดแทนพิมพ์", "name_en": "Speech-to-text", "state": "down"}],
                  "models": {}, "versions": {}, "gpu": [], "memory": None, "disks": [], "keys": {}, "brave_key": False,
                  "docker": {"usable": False, "reason_th": "ไม่ได้ติดตั้ง", "reason_en": "not installed"}, "errors": [],
                  "tests": None, "_meta": {"late": [], "gpu_error": None, "errors_skipped": 0},
                  "fixes": [{"id": "stt", "th": "เปิด STT", "en": "start STT"}], "took_ms": 5, "cached": False}
        with mock.patch.object(hub, "doctor_report", return_value=dict(canned)) as m:
            st, hd, data = _req(self.port, "GET", "/api/doctor?lang=en", {"Origin": "http://127.0.0.1:8103"})
            self.assertEqual(st, 200)
            d = json.loads(data)
            self.assertNotIn("text", d)                       # ข้อความรายงานเฉพาะเมื่อขอ (text=1 / format=text)
            self.assertEqual(d["lang"], "en")
            self.assertEqual(d["services"][0]["name"], "Speech-to-text")
            self.assertEqual(d["docker"]["reason"], "not installed")
            st, hd, data = _req(self.port, "GET", "/api/doctor?lang=th&text=1", {"Origin": "http://127.0.0.1:8100"})
            d = json.loads(data)
            self.assertIn("เปิด STT", d["text"])
            self.assertEqual(d["services"][0]["name"], "พูดแทนพิมพ์")
            st, hd, data = _req(self.port, "GET", "/api/doctor?format=text&lang=th&refresh=1", {})
            self.assertEqual(st, 200)
            self.assertTrue(hd["content-type"].startswith("text/plain"))
            self.assertIn("เปิด STT", data.decode("utf-8"))
            self.assertEqual(m.call_args.kwargs.get("refresh"), True)
            for h in ({"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "same-site"}):
                st, _, _ = _req(self.port, "GET", "/api/doctor", h)
                self.assertEqual(st, 403, h)


if __name__ == "__main__":
    unittest.main()
