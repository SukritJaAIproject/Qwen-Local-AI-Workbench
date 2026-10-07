# -*- coding: utf-8 -*-
"""
batch 3 สัญญา D2 (owner hub) — บันทึกการใช้งาน: C:\\LLM\\projects\\hub_usage.py

  * UsageTap อ่าน SSE/JSON ที่ proxy ส่งต่อ: timings ของ llama-server, usage แบบ OpenAI, /v1/responses (Codex),
    ชื่อเครื่องมือ (ชื่อเท่านั้น), ขอบเหตุการณ์ที่ถูกตัดกลางก้อน, CRLF, คำตอบหลายท่อนของ Extend Mode
  * บรรทัดใน usage.jsonl มีเฉพาะฟิลด์ตามสัญญา (+ conv แฮช) ไม่มีเนื้อหา
  * หมุนไฟล์ที่ ~10 MB โดยเปลี่ยนชื่อ (ไม่ลบ) และอ่านย้อนหลังได้ทั้งสองไฟล์
  * aggregate: รายวัน (เติมวันว่าง), รายโปรเจกต์, รายโมเดล, tok/s ถ่วงด้วยจำนวนโทเคน, แชตล่าสุด, รายการล่าสุด
"""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJ = r"C:\LLM\projects"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hu = _load("hub_usage_b3_under_test", os.path.join(PROJ, "hub_usage.py"))
TZ = timezone(timedelta(hours=7))


def sse(*payloads):
    out = b""
    for p in payloads:
        out += b"data: " + (b"[DONE]" if p == "[DONE]" else json.dumps(p, ensure_ascii=False).encode("utf-8")) + b"\n\n"
    return out


class TapTests(unittest.TestCase):
    def test_sse_fed_byte_by_byte(self):
        stream = sse({"choices": [{"delta": {"role": "assistant"}}], "model": "M"},
                     {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "a", "function": {"name": "web_search",
                                                                                                   "arguments": ""}}]}}]},
                     {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\"q\":1}"}}]}}]},
                     {"choices": [{"delta": {"content": "ความลับ"}}],
                      "timings": {"prompt_n": 10, "cache_n": 5, "predicted_n": 1, "predicted_ms": 10}},
                     {"choices": [{"delta": {}, "finish_reason": "tool_calls"}],
                      "timings": {"prompt_n": 10, "cache_n": 5, "prompt_per_second": 123.456, "predicted_n": 8,
                                  "predicted_ms": 400.0, "predicted_per_second": 20.0}},
                     "[DONE]")
        tap = hu.UsageTap(sse=True)
        for i in range(len(stream)):
            tap.feed(stream[i:i + 1])
        tap.close()
        n = tap.numbers()
        self.assertEqual(n, {"prompt_tokens": 15, "cached_tokens": 5, "completion_tokens": 8,
                             "prompt_tps": 123.46, "gen_tps": 20.0})
        self.assertEqual(tap.tools, ["web_search"])
        self.assertTrue(tap.finished)
        self.assertFalse(tap.error)
        self.assertEqual(tap.model, "M")

    def test_crlf_and_usage_fallback(self):
        raw = (b'data: {"choices":[{"delta":{"content":"x"}}]}\r\n\r\n'
               b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":40,'
               b'"completion_tokens":3,"prompt_tokens_details":{"cached_tokens":30}}}\r\n\r\ndata: [DONE]\r\n\r\n')
        tap = hu.UsageTap()
        tap.feed(raw)
        tap.close()
        n = tap.numbers()
        self.assertEqual((n["prompt_tokens"], n["cached_tokens"], n["completion_tokens"]), (40, 30, 3))
        self.assertIsNone(n["gen_tps"])

    def test_error_payload_and_unfinished(self):
        tap = hu.UsageTap()
        tap.feed(sse({"error": {"code": 400, "message": "context too long"}}))
        tap.close()
        self.assertTrue(tap.error)
        tap2 = hu.UsageTap()
        tap2.feed(sse({"choices": [{"delta": {"content": "a"}}]}))
        tap2.close()
        self.assertFalse(tap2.finished)
        self.assertEqual(tap2.numbers()["completion_tokens"], 1)      # ไม่มี timings = นับจากจำนวนก้อนเนื้อหา

    def test_responses_api(self):
        tap = hu.UsageTap()
        tap.feed(b"event: response.output_item.added\n" + sse({"type": "response.output_item.added",
                                                               "item": {"type": "function_call", "name": "exec_shell"}}))
        tap.feed(sse({"type": "response.completed", "response": {"usage": {
            "input_tokens": 500, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 400}}}}))
        tap.close()
        n = tap.numbers()
        self.assertEqual((n["prompt_tokens"], n["cached_tokens"], n["completion_tokens"]), (500, 400, 20))
        self.assertEqual(tap.tools, ["exec_shell"])
        self.assertTrue(tap.finished)

    def test_nonstream_json_and_oversize(self):
        body = {"choices": [{"message": {"content": "hi", "tool_calls": [{"function": {"name": "local_read"}}]},
                             "finish_reason": "stop"}], "usage": {"prompt_tokens": 9, "completion_tokens": 2}}
        tap = hu.UsageTap(sse=False)
        raw = json.dumps(body).encode()
        tap.feed(raw[:10])
        tap.feed(raw[10:])
        tap.close()
        self.assertEqual(tap.numbers()["prompt_tokens"], 9)
        self.assertEqual(tap.tools, ["local_read"])
        big = hu.UsageTap(sse=False)
        big.feed(b"x" * (hu.JSON_BUF_MAX + 10))
        big.close()
        self.assertIsNone(big.numbers()["prompt_tokens"])

    def test_bad_tool_names_ignored(self):
        tap = hu.UsageTap()
        tap.feed(sse({"choices": [{"delta": {"tool_calls": [{"function": {"name": "rm -rf /; echo"}}]}}]}))
        tap.feed(sse({"choices": [{"delta": {"tool_calls": [{"function": {"name": "x" * 200}}]}}]}))
        tap.close()
        self.assertEqual(tap.tools, [])

    def test_segments(self):
        tap = hu.UsageTap()
        tap.feed(sse({"choices": [{"delta": {}, "finish_reason": "length"}],
                      "timings": {"prompt_n": 100, "cache_n": 0, "prompt_per_second": 50.0, "predicted_n": 30,
                                  "predicted_ms": 3000.0}}))
        tap.new_segment()
        tap.feed(sse({"choices": [{"delta": {}, "finish_reason": "stop"}],
                      "timings": {"prompt_n": 2, "cache_n": 130, "predicted_n": 10, "predicted_ms": 1000.0}}))
        tap.close()
        n = tap.numbers()
        # [fix-hub b3] ความเร็วแบบ llama-server: Σ(n-1)/Σms = (29 + 9) / 4.0 วินาที (เดิม 40/4.0 = 10.0 สูงเกินจริง)
        self.assertEqual((n["prompt_tokens"], n["completion_tokens"], n["gen_tps"], n["prompt_tps"]), (100, 40, 9.5, 50.0))

    def test_single_segment_uses_llama_rate(self):
        """[fix-hub b3] ท่อนเดียว = predicted_per_second ของ llama-server ตรงๆ (ผู้ตรวจวัด: 36 โทเคน / 6587.5 ms → 5.313
        ของ llama-server แต่ hub บันทึก 5.46 เพราะใช้ n/ms) ไม่มีค่านั้นก็คำนวณ (n-1)/ms แบบเดียวกัน"""
        tap = hu.UsageTap()
        tap.feed(sse({"choices": [{"delta": {}, "finish_reason": "stop"}],
                      "timings": {"prompt_n": 13687, "cache_n": 0, "predicted_n": 36, "predicted_ms": 6587.5,
                                  "predicted_per_second": 5.313}}))
        tap.close()
        self.assertEqual(tap.numbers()["gen_tps"], 5.31)
        tap = hu.UsageTap()
        tap.feed(sse({"choices": [{"delta": {}, "finish_reason": "stop"}],
                      "timings": {"prompt_n": 10, "predicted_n": 5, "predicted_ms": 1000.0}}))
        tap.close()
        self.assertEqual(tap.numbers()["gen_tps"], 4.0)


class RecordAndLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b3usage-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)        # โฟลเดอร์ชั่วคราวของเทสต์นี้เอง

    def test_record_fields_only(self):
        tap = hu.UsageTap()
        tap.feed(sse({"choices": [{"delta": {"content": "เนื้อหาลับ"}, "finish_reason": "stop"}]}))
        rec = hu.make_record("p", "M", tap, 1.234, True, False, conv=hu.conv_hash("abc::M"))
        self.assertEqual(set(rec), set(hu.FIELDS))
        self.assertNotIn("เนื้อหาลับ", json.dumps(rec, ensure_ascii=False))
        self.assertEqual(rec["wall_s"], 1.23)
        self.assertEqual(hu.conv_hash("abc::M"), hu.conv_hash("abc::OTHER"))
        self.assertIsNone(hu.conv_hash(""))
        self.assertEqual(len(hu.conv_hash("abc")), 12)

    def test_append_rotate_and_read_back(self):
        log = hu.UsageLog(lambda: self.tmp, rotate_bytes=600)
        now = datetime.now(TZ)
        for i in range(12):
            log.append({"ts": now.isoformat(timespec="seconds"), "project": "p", "model": "M", "prompt_tokens": i,
                        "extra_content_field": "ต้องไม่ถูกเขียน"})
        files = sorted(f.name for f in self.tmp.iterdir())
        self.assertIn("usage.jsonl", files)
        rotated = [f for f in files if f.startswith("usage-") and f.endswith(".jsonl")]
        self.assertGreaterEqual(len(rotated), 1)
        rows = log.read(0)
        self.assertEqual(sorted(r["prompt_tokens"] for r in rows), list(range(12)))   # ไม่มีบรรทัดหาย
        self.assertNotIn("ต้องไม่ถูกเขียน", "".join(f.read_text(encoding="utf-8") for f in self.tmp.iterdir()))
        # อ่านซ้ำโดยไฟล์ไม่เปลี่ยน = ได้จากแคช (ผลเดียวกัน)
        self.assertEqual(log.read(0), rows)


class AggregateTests(unittest.TestCase):
    def rec(self, day_offset, **kw):
        ts = (datetime(2026, 10, 6, 12, 0, tzinfo=TZ) - timedelta(days=day_offset)).isoformat(timespec="seconds")
        r = {"ts": ts, "project": "p1", "model": "Qwen3.8-27B-UD-Q4_K_M", "prompt_tokens": 1000, "cached_tokens": 0,
             "completion_tokens": 100, "prompt_tps": 100.0, "gen_tps": 1.0, "wall_s": 110.0, "tools_used": [],
             "compacted": False, "error": False, "conv": "c1"}
        r.update(kw)
        return r

    def test_shape_and_weighting(self):
        now = datetime(2026, 10, 6, 23, 0, tzinfo=TZ)
        rows = [self.rec(0, completion_tokens=100, gen_tps=10.0),
                self.rec(0, completion_tokens=10, gen_tps=100.0, model="Qwen3-4B-Instruct-2507-Q4_K_M", project="p2",
                         conv="c2", tools_used=["web_search"]),
                self.rec(2, error=True, compacted=True),
                self.rec(10)]                          # นอกช่วง 7 วัน
        d = hu.aggregate(rows, 7, now=now, project_names={"p1": "หนึ่ง"})
        self.assertEqual((d["days"], d["from"], d["to"]), (7, "2026-09-30", "2026-10-06"))
        self.assertEqual([x["date"] for x in d["per_day"]][-1], "2026-10-06")
        self.assertEqual(len(d["per_day"]), 7)
        self.assertEqual(d["per_day"][0]["requests"], 0)          # วันว่างถูกเติม (กราฟไม่ขาด)
        today = d["per_day"][-1]
        self.assertEqual(today["requests"], 2)
        # ถ่วงด้วยโทเคน: 110 โทเคน / (10 + 0.1 วินาที)
        self.assertAlmostEqual(today["gen_tps"], round(110 / 10.1, 2))
        self.assertEqual(set(today["models"]), {"Qwen3.8-27B-UD-Q4_K_M", "Qwen3-4B-Instruct-2507-Q4_K_M"})
        self.assertEqual(d["totals"]["requests"], 3)
        self.assertEqual((d["totals"]["errors"], d["totals"]["compacted"]), (1, 1))
        self.assertEqual(d["totals"]["total_tokens"], d["totals"]["prompt_tokens"] + d["totals"]["completion_tokens"])
        p1 = next(p for p in d["per_project"] if p["project"] == "p1")
        self.assertEqual(p1["name"], "หนึ่ง")
        p2 = next(p for p in d["per_project"] if p["project"] == "p2")
        self.assertEqual(p2["name"], "p2")
        m = {x["model"]: x for x in d["per_model"]}
        self.assertEqual(m["Qwen3.8-27B-UD-Q4_K_M"]["short"], "Qwen3.8-27B")
        self.assertEqual(d["recent"][0]["ts"][:10], "2026-10-06")
        self.assertGreaterEqual(d["recent"][0]["ts"], d["recent"][-1]["ts"])
        self.assertEqual({s["conv"] for s in d["sessions"]}, {"c1", "c2"})
        s2 = next(s for s in d["sessions"] if s["conv"] == "c2")
        self.assertEqual(s2["tools_used"], ["web_search"])

    def test_days_clamped_and_empty(self):
        d = hu.aggregate([], -3, now=datetime(2026, 10, 6, tzinfo=TZ))
        self.assertEqual(d["days"], 1)
        self.assertEqual(hu.aggregate([], 0, now=datetime(2026, 10, 6, tzinfo=TZ))["days"], 7)   # ไม่ระบุ = 7 วัน
        self.assertIsNone(d["totals"]["gen_tps"])
        d = hu.aggregate([], 500, now=datetime(2026, 10, 6, tzinfo=TZ))
        self.assertEqual(d["days"], hu.DAYS_MAX)

    def test_recent_capped(self):
        rows = [self.rec(0, prompt_tokens=i) for i in range(80)]
        d = hu.aggregate(rows, 1, now=datetime(2026, 10, 6, 23, 0, tzinfo=TZ))
        self.assertEqual(len(d["recent"]), hu.RECENT_MAX)


if __name__ == "__main__":
    unittest.main()
