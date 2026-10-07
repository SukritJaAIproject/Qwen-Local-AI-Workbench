# -*- coding: utf-8 -*-
"""
batch 3 สัญญา D1/D2 (owner hub) — เทสต์สดกับ router จริง (8099) + Qwen3-4B จริง  [ปิดเป็นค่าเริ่มต้น]

เปิดด้วย LLM_B3_LIVE=1 — ใช้เฉพาะ Qwen3-4B-Instruct-2507-Q4_K_M (โหลดเองเฉพาะเมื่อ commit ว่าง ≥ 25 GB ไม่งั้นข้าม)
ไม่แตะ hub ตัวจริง: import hub.py เป็นโมดูล เปิด proxy ของโปรเจกต์ทดสอบบนพอร์ตสำรอง 8171-8177 (ตัวแรกที่ว่าง)
DATA_ROOT ชั่วคราว (usage.jsonl / แคชสรุปไม่ปนของจริง) และปิดเองตอนจบ

  1) ความซื่อตรงของสรุปจาก 4B: ส่วนที่ถูกย่อของบทสนทนาสังเคราะห์ → ตรวจตัวเลข/ชื่อไฟล์/การตัดสินใจ/งานค้าง (FACTS)
     และข้อความหลอกสั่งงานในผลเว็บต้องไม่ถูกคัดลอกเป็นคำสั่ง
  2) E2E ผ่าน proxy: เทิร์นแรกถูกย่อ (X-Qwen-Compacted) แล้ว 4B ตอบจากคำขอที่ย่อแล้ว, เทิร์นถัดไปใช้สรุปเดิม
     (llama.cpp ใช้ KV cache ของต้นคำขอ: cached_tokens สูง) และ 4B ตอบคำถามที่คำตอบอยู่ในช่วงที่ถูกย่อได้ถูก
"""
import ctypes
import http.client
import importlib.util
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HUB = r"C:\LLM\projects\hub.py"
HERE = os.path.dirname(os.path.abspath(__file__))
M4 = "Qwen3-4B-Instruct-2507-Q4_K_M"
LIVE = os.environ.get("LLM_B3_LIVE") == "1"


# พอร์ตของ router ที่ใช้ทดสอบ: ค่าเริ่มต้น 8099 (ตัวจริง) — agent ที่สร้างงานทดสอบบน router สำรองตั้ง LLM_B3_ROUTER_PORT=8199
# (คู่กับ LLM_LOCAL_TOKEN_FILE = โทเคนทดสอบของ router ตัวนั้น) จะได้ไม่ต้องแตะ router ตัวจริงหรือโทเคนจริงเลย
ROUTER_PORT = os.environ.get("LLM_B3_ROUTER_PORT") or "8099"


def _load(name, path, argv=False):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    if argv:
        sys.path.insert(0, os.path.dirname(path))
        with mock.patch.object(sys, "argv", ["hub.py", "8100", ROUTER_PORT]):
            spec.loader.exec_module(mod)
    else:
        spec.loader.exec_module(mod)
    return mod


def commit_free_gb():
    class M(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
            (n, ctypes.c_ulonglong) for n in ("tp", "ap", "tpf", "apf", "tv", "av", "aev")]
    m = M()
    m.dwLength = ctypes.sizeof(M)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.apf / 1024.0 ** 3


@unittest.skipUnless(LIVE, "set LLM_B3_LIVE=1 to run the live 4B compaction tests")
class LiveCompactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = _load("hub_b3_live", HUB, argv=True)
        cls.fx = _load("b3_fixture_live", os.path.join(HERE, "test_b3_fixture.py"))
        table = cls.hub.router_model_table(max_age=0) or {}
        if M4 not in table:
            raise unittest.SkipTest("router ไม่มี %s" % M4)
        if table[M4].get("state") != "loaded" and commit_free_gb() < 25:
            raise unittest.SkipTest("4B ยังไม่โหลดและ commit ว่าง < 25 GB — ไม่โหลดโมเดลเพิ่ม")
        api = cls.hub._router_json("GET", "/models")[1] or {}
        busy = [m["id"] for m in api.get("data") or [] if (m.get("status") or {}).get("value") == "loading"]
        if busy:
            raise unittest.SkipTest("router กำลังโหลดโมเดล %s" % busy)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b3live-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)        # โฟลเดอร์ชั่วคราวของเทสต์นี้เอง

    def test_4b_summary_is_faithful(self):
        hub, fx = self.hub, self.fx
        msgs = fx.build_long_conversation()
        doc = fx.build_request(msgs)
        times = []

        def summarize(messages, timeout_s=None):
            t0 = time.time()
            out = hub._summarize_via_router(messages, timeout_s=1500)
            times.append(round(time.time() - t0, 1))
            return out
        comp = hub._compact.Compactor(hub._compact.Store(lambda slug: self.tmp / slug), hub._compact.estimate_request,
                                      summarize, log=print, budget_s=1800)
        # เทสต์นี้วัด "4B เขียนสรุปได้ซื่อตรงไหม" — ให้เวลาเขียนจนจบ (เครื่องที่มีงานอื่นแย่ง CPU 4B เขียนได้แค่ ~2-4 โทเคน/วินาที
        # เพดานปกติ 300 วินาทีต่อครั้งจะตัดกลางคัน แล้วส่วนที่ขาดถูกเติมแบบตัดตอน = ไม่ได้วัดตัวโมเดล)
        with mock.patch.object(hub, "COMPACT_SUMMARY_TIMEOUT", 1500.0):
            res = comp.apply(doc, "live", 8192)
        self.assertTrue(res.applied)
        self.assertFalse(res.fallback, "4B ตอบไม่ได้ — ได้สรุปแบบตัดตอนแทน")
        self.assertFalse(res.partial, "4B เขียนไม่จบใน %s วินาที" % times)
        summ = doc["messages"][2]["content"]
        kept = [f for f, _ in fx.FACTS if f in summ]
        missing = [f for f, _ in fx.FACTS if f not in summ]
        print("\n[b3-live] summary %d tokens in %s s, facts %d/%d missing %s, unsupported numbers %d"
              % (res.summary_tokens, times, len(kept), len(fx.FACTS), missing, res.unsupported))
        print(summ)
        self.assertGreaterEqual(len(kept), len(fx.FACTS) - 2, "สรุปทำข้อเท็จจริงหายเกิน 2 จาก %d: %s" % (len(fx.FACTS), missing))
        self.assertIn(fx.OPEN_TASK[0], summ)                     # งานค้าง (ฟิวส์ยังไม่ได้สั่ง)
        self.assertNotIn("IGNORE ALL PREVIOUS", summ.upper())   # ข้อความหลอกในผลเว็บไม่ถูกคัดลอกเป็นคำสั่ง
        self.assertLessEqual(res.unsupported, 2)
        self.assertLessEqual(res.summary_tokens, hub._compact.SUMMARY_MAX_TOKENS + 10)

    def test_e2e_proxy_compacts_reuses_and_answers_from_summary(self):
        hub, fx = self.hub, self.fx
        port = None
        for p in range(8171, 8178):
            with socket.socket() as s:
                try:
                    s.bind(("127.0.0.1", p))
                    port = p
                    break
                except OSError:
                    continue
        if port is None:
            self.skipTest("พอร์ตสำรอง 8171-8177 ไม่ว่าง")
        data = self.tmp / "data"
        data.mkdir()
        settings = self.tmp / "settings.json"
        settings.write_text(json.dumps({"lang": "th", "theme": "dark", "font": "serif"}), encoding="utf-8")
        proj = {"slug": "b3live", "name": "b3 live", "port": port, "system_prompt": "", "think": "off", "extend": True,
                "auto_kb": False, "model": M4}
        patches = [mock.patch.object(hub, "DATA_ROOT", data), mock.patch.object(hub, "SETTINGS", settings),
                   mock.patch.object(hub, "model_ctx", side_effect=lambda m: 8192)]
        for p in patches:
            p.start()
        srv = ThreadingHTTPServer(("127.0.0.1", port), hub.make_proxy_handler("b3live", lambda: [proj]))
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        own = "http://127.0.0.1:%d" % port
        try:
            def chat(messages):
                body = {"model": M4, "stream": True, "max_tokens": 220, "messages": messages,
                        "timings_per_token": True, "return_progress": True}
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=1800)
                t0 = time.time()
                c.request("POST", "/v1/chat/completions", body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          headers={"Content-Type": "application/json", "Origin": own,
                                   "X-Conversation-Id": "b3-live-conv::" + M4})
                r = c.getresponse()
                raw = r.read()
                c.close()
                text = ""
                for line in raw.split(b"\n"):
                    if line.startswith(b"data: {"):
                        d = json.loads(line[6:])
                        text += ((d.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                return r.status, {k.lower(): v for k, v in r.getheaders()}, text, round(time.time() - t0, 1)

            msgs = fx.build_long_conversation()
            st, hd1, ans1, t1 = chat(msgs)
            self.assertEqual(st, 200)
            self.assertIn("x-qwen-compacted", hd1)
            self.assertTrue(ans1.strip())
            q2 = "ตกลงเราจะเปลี่ยนรีเลย์ตัวไหนของตู้ไหน ภายในวันไหน และงบไม่เกินเท่าไร ตอบสั้นๆ"
            msgs2 = msgs + [{"role": "assistant", "content": ans1}, {"role": "user", "content": q2}]
            st, hd2, ans2, t2 = chat(msgs2)
            self.assertEqual(st, 200)
            self.assertEqual(hd2.get("x-qwen-compacted"), hd1["x-qwen-compacted"])
            # บรรทัด usage ถูกเขียนใน finally ของ handler หลังส่งคำตอบครบ — client อ่านจบก่อนได้ รอสั้นๆ
            rows, end = [], time.time() + 10
            while time.time() < end:
                rows = [json.loads(l) for l in (data / "usage.jsonl").read_text(encoding="utf-8").splitlines()
                        if l.strip()]
                if len(rows) >= 2:
                    break
                time.sleep(0.1)
            note = hub.compaction_note("b3live", "b3-live-conv")
            print("\n[b3-live e2e] port %d | turn1 %.1fs compacted %s turns | turn2 %.1fs reused=%s"
                  % (port, t1, hd1["x-qwen-compacted"], t2, note and note["reused"]))
            for r in rows:
                print("   usage:", json.dumps(r, ensure_ascii=False))
            print("   answer2:", ans2.strip()[:400])
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(r["compacted"] and not r["error"] for r in rows))
            self.assertLess(rows[0]["prompt_tokens"], 8192)
            self.assertGreater(rows[0]["completion_tokens"], 0)
            # เทิร์นสองใช้ต้นคำขอเดิม: llama.cpp ดึงจาก KV cache เกือบทั้งหมด (สรุป + เทิร์นที่เก็บ + คำตอบรอบแรก)
            self.assertGreater(rows[1]["cached_tokens"], 0.6 * rows[0]["prompt_tokens"])
            self.assertTrue(note and note["reused"])
            hits = [w for w in ("K2", "C-03", "48,500", "48500", "15") if w in ans2]
            self.assertGreaterEqual(len(hits), 2, "4B ไม่ได้ตอบจากสรุป: %r" % ans2[:300])
        finally:
            srv.shutdown()
            srv.server_close()
            for p in reversed(patches):
                p.stop()


if __name__ == "__main__":
    unittest.main()
