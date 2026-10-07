# -*- coding: utf-8 -*-
"""
เทสต์ gpu_bench.py ส่วนที่เพิ่มใน batch 2b สัญญา C3 (owner stack): เทียบค่าตั้ง vision/context ของ 27B บน router ตัวทดสอบ

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

ไม่เปิด llama-server จริงเลย (start/stop/bench/image ถูกแทนด้วยของปลอม) — ตรวจ:
  * preset ของแต่ละค่าตั้ง = preset ของ router ตัวจริง + คีย์ของค่าตั้งนั้นใน section ของโมเดล ([*] คงเดิม, ไม่มี BOM)
  * คำสั่งเปิด router ตัวทดสอบมีค่าความปลอดภัยชุดเดียวกับตัวเปิด (127.0.0.1, API key เป็น path, CORS เฉพาะตัวเอง,
    ไม่มี --ui-mcp-proxy, --models-max 1) และ env ไม่มีตัวแปรลับ
  * ด่านหน่วยความจำ: commit เหลือน้อยกว่า --min-free-gb = ข้ามทุกค่าตั้ง ไม่เปิด router เลย ไม่เขียน user.ini
  * router ตัวจริงมีแชตกำลังตอบ = ไม่วัดแข่ง
  * เลือกค่าตั้ง: ช้าลง < 10% เท่านั้น, ดูรูปต้องถามรูปผ่าน, ดูรูปก่อน context ใหญ่, ไม่มี base = ไม่แนะนำ
  * --write-user-ini เขียนเฉพาะเมื่อยังไม่มีไฟล์ (ไม่มี BOM, section ของโมเดล) — ไฟล์เดิมของผู้ใช้ไม่ถูกทับ
  * --repeat รายงานค่ากลาง; รูป PNG ที่สร้างเองถูกต้อง
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, r"C:\LLM")
import gpu_bench as gb  # noqa: E402
import gpu_profile as gp  # noqa: E402

BASE_PRESET = ("; generated\n\n[*]\nctx-size = 32768\ncache-type-k = q8_0\ncache-type-v = q8_0\nthreads = 6\n\n"
               "[Qwen3-4B-Instruct-2507-Q4_K_M]\ndevice = CUDA0\n")


def row(name, tps, image_ok=None, error=None, skipped=None):
    keys = dict(dict(gb.VARIANT_SETS["vision27b"])[name])
    r = {"variant": name, "keys": keys, "gen_tps": tps}
    if image_ok is not None:
        r["image_ok"] = image_ok
    if error:
        r["error"] = error
    if skipped:
        r["skipped"] = skipped
    return r


class PresetAndArgvTests(unittest.TestCase):
    def test_variant_preset_merges_into_model_section_only(self):
        keys = {"mmproj": gb.MMPROJ_27B, "mmproj-device": "none"}
        text = gb.variant_preset_text(BASE_PRESET, gb.PRIMARY_27B, keys, "c_mmproj_cpu")
        self.assertFalse(text.startswith("\ufeff"))
        sec, warn = gp.parse_ini(text)
        self.assertEqual(warn, [])
        self.assertEqual(sec["*"], {"ctx-size": "32768", "cache-type-k": "q8_0", "cache-type-v": "q8_0", "threads": "6"})
        self.assertEqual(sec[gb.PRIMARY_27B], keys)
        self.assertEqual(sec["Qwen3-4B-Instruct-2507-Q4_K_M"], {"device": "CUDA0"})
        base = gp.parse_ini(gb.variant_preset_text(BASE_PRESET, gb.PRIMARY_27B, {}, "base"))[0]
        self.assertEqual({k: v for k, v in base.items() if v}, {k: v for k, v in gp.parse_ini(BASE_PRESET)[0].items()})

    def test_variant_set_matches_contract(self):
        names = [n for n, _k in gb.VARIANT_SETS["vision27b"]]
        self.assertEqual(names[0], "base")
        keys = dict(gb.VARIANT_SETS["vision27b"])
        self.assertEqual(keys["a_ctx64k"], {"ctx-size": "65536"})
        self.assertEqual(keys["b_mmproj_gpu"], {"mmproj": gb.MMPROJ_27B})
        self.assertEqual(keys["c_mmproj_cpu"]["mmproj-device"], "none")
        self.assertEqual(keys["d_mmproj_img768"]["image-max-tokens"], "768")

    def test_router_argv_is_locked_down(self):
        with mock.patch.dict(os.environ, {gp.LOCAL_TOKEN_ENV: r"C:\tmp\test.token"}):
            a = gb.router_argv(8199, r"C:\tmp\p.ini")
        s = " ".join(a)

        def after(flag):
            return a[a.index(flag) + 1]
        self.assertEqual(after("--host"), "127.0.0.1")
        self.assertEqual(after("--port"), "8199")
        self.assertEqual(after("--models-max"), "1")
        self.assertEqual(after("--api-key-file"), r"C:\tmp\test.token")
        self.assertEqual(after("--cors-origins"), "http://127.0.0.1:8199")
        self.assertEqual(after("--models-preset"), r"C:\tmp\p.ini")
        for f in ("--no-cors-credentials", "--no-webui", "--jinja"):
            self.assertIn(f, a)
        for bad in ("--ui-mcp-proxy", "--api-key ", "0.0.0.0", " -c ", "--ctx-size"):
            self.assertNotIn(bad, s + " ")

    def test_clean_env_drops_secrets_keeps_token_path(self):
        fake = {"PATH": "x", "CLAUDE_CODE_MESSAGING_TOKEN": "s", "MY_API_KEY": "s", "GITHUB_TOKEN": "s",
                gp.LOCAL_TOKEN_ENV: r"C:\t\tok", "OTEL_X": "s"}
        with mock.patch.dict(os.environ, fake, clear=True):
            env = gb.clean_env()
        self.assertEqual(env.get(gp.LOCAL_TOKEN_ENV), r"C:\t\tok")
        self.assertEqual(env.get("CUDA_DEVICE_ORDER"), "PCI_BUS_ID")
        for k in ("CLAUDE_CODE_MESSAGING_TOKEN", "MY_API_KEY", "GITHUB_TOKEN", "OTEL_X"):
            self.assertNotIn(k, env)

    def test_tiny_png(self):
        import struct
        p = gb.tiny_png()
        self.assertEqual(p[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", p[16:24]), (32, 32))


class RecommendTests(unittest.TestCase):
    def test_prefers_vision_then_context_within_budget(self):
        rows = [row("base", 1.30), row("a_ctx64k", 1.20), row("b_mmproj_gpu", 1.10, True),
                row("c_mmproj_cpu", 1.28, True), row("d_mmproj_img768", 1.25, False),
                row("e_ctx64k_mmproj_cpu", 1.19, True)]
        rec = gb.recommend(rows)
        self.assertEqual(rec["name"], "e_ctx64k_mmproj_cpu")
        self.assertEqual(rec["keys"]["ctx-size"], "65536")
        self.assertAlmostEqual(rec["drop"], 1 - 1.19 / 1.30, places=3)

    def test_drop_at_or_over_budget_rejected(self):
        rows = [row("base", 1.00), row("a_ctx64k", 0.90), row("b_mmproj_gpu", 0.85, True),
                row("c_mmproj_cpu", 0.95, False)]
        rec = gb.recommend(rows)
        self.assertIsNone(rec["name"], "ลด 10% พอดีไม่ผ่าน, ดูรูปที่ถามรูปไม่ผ่านไม่นับ")
        rows.append(row("d_mmproj_img768", 0.91, True))
        self.assertEqual(gb.recommend(rows)["name"], "d_mmproj_img768")

    def test_context_only_when_no_vision_qualifies(self):
        rows = [row("base", 1.00), row("a_ctx64k", 0.97), row("b_mmproj_gpu", 0.80, True),
                row("c_mmproj_cpu", None, error="HTTP 500"), row("d_mmproj_img768", 0.99, skipped="mem")]
        self.assertEqual(gb.recommend(rows)["name"], "a_ctx64k")

    def test_no_base(self):
        self.assertIsNone(gb.recommend([row("base", None, error="x"), row("a_ctx64k", 1.0)])["name"])


class RunVariantsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="stackb2b-bench-")
        self.user_ini = os.path.join(self.tmp, "models-preset.user.ini")
        self.patches = [mock.patch.object(gp, "USER_INI", self.user_ini),
                        mock.patch.object(gp, "published_dir", return_value=self.tmp),
                        mock.patch.object(gp, "router_busy", return_value=(False, []))]
        for p in self.patches:
            p.start()
        with open(os.path.join(self.tmp, gp.PRESET_NAME), "w", encoding="utf-8", newline="\n") as f:
            f.write(BASE_PRESET)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def args(self, **over):
        a = argparse.Namespace(variants="vision27b", models=None, only=None, out_dir=self.tmp, image=None,
                               test_port=8199, tokens=16, repeat=1, min_free_gb=25.0, max_drop=0.10,
                               wait_idle_s=0, write_user_ini=True)
        for k, v in over.items():
            setattr(a, k, v)
        return a

    def test_memory_gate_skips_everything(self):
        with mock.patch.object(gb, "available_commit_gb", return_value=13.1), \
                mock.patch.object(gb, "start_test_router") as start:
            rc = gb.run_variants(self.args(), log=lambda *a: None)
        start.assert_not_called()
        self.assertEqual(rc, gb.EXIT_OK)
        self.assertFalse(os.path.exists(self.user_ini))
        path = [os.path.join(self.tmp, f) for f in os.listdir(self.tmp) if f.endswith(".json")][0]
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertTrue(all(r.get("skipped") for r in doc["results"]))
        self.assertIsNone(doc["recommendation"]["name"])

    def test_busy_live_router_not_measured(self):
        with mock.patch.object(gb, "available_commit_gb", return_value=40.0), \
                mock.patch.object(gp, "router_busy", return_value=(True, ["slot 0 กำลังสร้างข้อความ"])), \
                mock.patch.object(gb, "start_test_router") as start:
            gb.run_variants(self.args(), log=lambda *a: None)
        start.assert_not_called()

    def fake_bench(self, speeds):
        def bench(port, model, tokens, log=None, repeat=1):
            return {"model": model, "error": None, "gen_tps": speeds.pop(0)}
        return bench

    def test_full_run_writes_user_ini_once_without_bom(self):
        speeds = [1.30, 1.20, 1.05, 1.27, 1.06, 1.18]
        started = []
        with mock.patch.object(gb, "available_commit_gb", return_value=40.0), \
                mock.patch.object(gb, "start_test_router", side_effect=lambda p, pr, lg: started.append(pr) or object()), \
                mock.patch.object(gb, "stop_test_router"), \
                mock.patch.object(gb, "bench_model", side_effect=self.fake_bench(list(speeds))), \
                mock.patch.object(gb, "image_check", return_value={"image_ok": True}):
            rc = gb.run_variants(self.args(), log=lambda *a: None)
        self.assertEqual(rc, gb.EXIT_OK)
        self.assertEqual(len(started), 6)
        for pr in started:
            with open(pr, "rb") as f:
                self.assertFalse(f.read(3) == b"\xef\xbb\xbf")
        with open(self.user_ini, "rb") as f:
            raw = f.read()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "INI ที่มี BOM ทำให้ llama-server ปิดตัวทันที")
        sec, warn = gp.parse_ini(raw.decode("utf-8"))
        self.assertEqual(warn, [])
        self.assertEqual(sec, {gb.PRIMARY_27B: {"ctx-size": "65536", "mmproj": gb.MMPROJ_27B,
                                                "mmproj-device": "none"}})
        # รอบสอง: มีไฟล์แล้ว = ไม่ทับ
        with open(self.user_ini, "w", encoding="utf-8") as f:
            f.write("; ของผู้ใช้\n")
        with mock.patch.object(gb, "available_commit_gb", return_value=40.0), \
                mock.patch.object(gb, "start_test_router", return_value=object()), \
                mock.patch.object(gb, "stop_test_router"), \
                mock.patch.object(gb, "bench_model", side_effect=self.fake_bench(list(speeds))), \
                mock.patch.object(gb, "image_check", return_value={"image_ok": True}):
            gb.run_variants(self.args(), log=lambda *a: None)
        with open(self.user_ini, encoding="utf-8") as f:
            self.assertEqual(f.read(), "; ของผู้ใช้\n")

    def test_router_failure_is_reported_and_stopped(self):
        with mock.patch.object(gb, "available_commit_gb", return_value=40.0), \
                mock.patch.object(gb, "start_test_router", side_effect=RuntimeError("router ทดสอบปิดตัวทันที")), \
                mock.patch.object(gb, "stop_test_router") as stop:
            rc = gb.run_variants(self.args(only=["a_ctx64k"]), log=lambda *a: None)
        self.assertEqual(rc, gb.EXIT_SOME_FAILED)
        self.assertEqual(stop.call_count, 2)
        self.assertFalse(os.path.exists(self.user_ini))


class VramSnapshotTests(unittest.TestCase):
    # รอบ 2026-10-06: จด VRAM ก่อน/หลังโหลดต่อค่าตั้ง — แยก "ค่าตั้งช้า" ออกจาก "มีโปรแกรมอื่นถือ VRAM ตอนวัด"
    def test_parses_rows_and_fails_soft(self):
        with mock.patch.object(gp, "_smi_query", return_value=[["4410", "1731"], ["0", "8188"]]):
            self.assertEqual(gb.vram_snapshot(), [{"used_mib": 4410, "free_mib": 1731},
                                                  {"used_mib": 0, "free_mib": 8188}])
        with mock.patch.object(gp, "_smi_query", return_value=None):
            self.assertIsNone(gb.vram_snapshot())
        with mock.patch.object(gp, "_smi_query", return_value=[["[N/A]", "1"]]):
            self.assertIsNone(gb.vram_snapshot())

    def test_run_records_before_and_loaded(self):
        tmp = tempfile.mkdtemp(prefix="stackb2b-vram-")
        self.addCleanup(shutil.rmtree, tmp, True)
        args = argparse.Namespace(variants="vision27b", models=None, only=["a_ctx64k"], out_dir=tmp, image=None,
                                  test_port=8199, tokens=16, repeat=1, min_free_gb=25.0, max_drop=0.10,
                                  wait_idle_s=0, write_user_ini=False)
        # ก่อนเปิด router / หลังสร้างข้อความ (fixer: VRAM ที่เหลือให้ STT) / ก่อนปิด — ต่อค่าตั้ง (base + a_ctx64k)
        snaps = iter([[{"used_mib": 0, "free_mib": 5923}], [{"used_mib": 4000, "free_mib": 1900}],
                      [{"used_mib": 4100, "free_mib": 1800}]] * 2)
        with mock.patch.object(gp, "published_dir", return_value=tmp), \
                mock.patch.object(gp, "router_busy", return_value=(False, [])), \
                mock.patch.object(gb, "available_commit_gb", return_value=40.0), \
                mock.patch.object(gb, "start_test_router", return_value=object()), \
                mock.patch.object(gb, "stop_test_router"), \
                mock.patch.object(gb, "bench_model", return_value={"error": None, "gen_tps": 1.3}), \
                mock.patch.object(gb, "vram_snapshot", side_effect=lambda: next(snaps)):
            gb.run_variants(args, log=lambda *a: None)
        path = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(".json")][0]
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)["results"]
        self.assertEqual(rows[0]["vram_before"], [{"used_mib": 0, "free_mib": 5923}])
        self.assertEqual(rows[0]["vram_after_gen"], [{"used_mib": 4000, "free_mib": 1900}])
        self.assertEqual(rows[0]["vram_loaded"], [{"used_mib": 4100, "free_mib": 1800}])


class EffectiveSectionTests(unittest.TestCase):
    """fixer 2026-10-06: preset ตัวจริงมีค่าจาก user.ini แล้ว — ค่าตั้งต้อง "ลบคีย์" ได้ (null) และคำแนะนำตัดสินจาก section ที่ใช้จริง"""
    BASE = ("[*]\nctx-size = 32768\nthreads = 6\n\n[Qwen3.8-27B-UD-Q4_K_M]\nctx-size = 65536\n"
            "mmproj = C:\\LLM\\models\\mmproj-Qwen3.8-27B-F16.gguf\nmmproj-device = none\nimage-max-tokens = 768\n")

    def test_null_removes_key_and_value_overrides(self):
        eff = gb.effective_section(self.BASE, gb.PRIMARY_27B, {"mmproj-device": None, "fit-target": "1700"})
        self.assertNotIn("mmproj-device", eff)
        self.assertEqual(eff["fit-target"], "1700")
        self.assertEqual(eff["ctx-size"], "65536")
        text = gb.variant_preset_text(self.BASE, gb.PRIMARY_27B, {"mmproj-device": None}, "ab")
        sections, _w = gp.parse_ini(text)
        self.assertNotIn("mmproj-device", sections[gb.PRIMARY_27B])
        self.assertEqual(sections["*"]["ctx-size"], "32768", "[*] ไม่ถูกแตะ")
        self.assertFalse(text.startswith("\ufeff"))
        orig = gb.effective_section(self.BASE, gb.PRIMARY_27B, {k: None for k in (
            "ctx-size", "mmproj", "mmproj-device", "image-max-tokens")})
        self.assertEqual(orig, {})

    def test_recommend_uses_effective_section(self):
        rows = [{"variant": "base", "keys": {}, "effective": {}, "gen_tps": 1.0},
                {"variant": "e_now", "keys": {}, "gen_tps": 0.95, "image_ok": True,
                 "effective": {"ctx-size": "65536", "mmproj": "m.gguf", "mmproj-device": "none"}},
                {"variant": "ab", "keys": {"mmproj-device": None}, "gen_tps": 0.97, "image_ok": True,
                 "effective": {"ctx-size": "65536", "mmproj": "m.gguf"}},
                {"variant": "slow", "keys": {}, "gen_tps": 0.80, "image_ok": True,
                 "effective": {"ctx-size": "65536", "mmproj": "m.gguf"}}]
        rec = gb.recommend(rows)
        self.assertEqual(rec["name"], "ab", "ดูรูปได้ + ctx เท่ากัน = เลือกตัวที่เร็วกว่า (ลดไม่ถึง 10%)")
        rows[2]["image_ok"] = False
        self.assertEqual(gb.recommend(rows)["name"], "e_now")

    def test_vram_guard_skips_when_gpu_is_busy(self):
        """--max-vram-used-mib: โมเดลของ router ตัวจริงถือ VRAM อยู่ = ไม่วัด (ผลจะวัดการแย่ง VRAM ไม่ใช่ค่าตั้ง)"""
        tmp = tempfile.mkdtemp(prefix="stackb2b-vguard-")
        self.addCleanup(shutil.rmtree, tmp, True)
        args = argparse.Namespace(variants="vision27b", models=None, only=["a_ctx64k"], out_dir=tmp, image=None,
                                  test_port=8199, tokens=16, repeat=1, min_free_gb=25.0, max_drop=0.10,
                                  wait_idle_s=0, write_user_ini=False, max_vram_used_mib=500)
        with mock.patch.object(gp, "published_dir", return_value=tmp), \
                mock.patch.object(gp, "router_busy", return_value=(False, [])), \
                mock.patch.object(gb, "available_commit_gb", return_value=40.0), \
                mock.patch.object(gb, "start_test_router") as start, \
                mock.patch.object(gb, "stop_test_router"), \
                mock.patch.object(gb, "vram_snapshot", return_value=[{"used_mib": 3900, "free_mib": 2000}]):
            gb.run_variants(args, log=lambda *a: None)
        start.assert_not_called()
        path = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(".json")][0]
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)["results"]
        self.assertTrue(all("3900 MiB" in r.get("skipped", "") for r in rows))

    def test_merge_rounds_keeps_effective_and_min_free_vram(self):
        eff = {"mmproj": "m.gguf"}
        parts = [{"gen_tps": 1.0, "image_ok": True, "effective": eff,
                  "vram_after_gen": [{"used_mib": 4000, "free_mib": 1900}]},
                 {"gen_tps": 1.2, "image_ok": True, "effective": eff,
                  "vram_after_gen": [{"used_mib": 4400, "free_mib": 1500}]}]
        row = gb.merge_rounds("x", {}, gb.PRIMARY_27B, parts)
        self.assertEqual(row["effective"], eff)
        self.assertTrue(row["image_ok"], "mmproj มาจาก preset ตัวจริง (คีย์ของค่าตั้งว่าง) ก็ต้องรวมผลถามรูป")
        self.assertEqual(row["vram_free_after_gen_mib"], 1500)


class RoundsTests(unittest.TestCase):
    # รอบ 2026-10-06: --rounds วัดสลับกันแบบ ABBA แล้วรวมตัวอย่างเป็นค่ากลาง (เครื่องนี้ความเร็วไหลตามเวลา)
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="stackb2b-rounds-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def args(self, **over):
        a = argparse.Namespace(variants="vision27b", models=None, only=["c_mmproj_cpu"], out_dir=self.tmp, image=None,
                               test_port=8199, tokens=16, repeat=2, rounds=2, min_free_gb=25.0, max_drop=0.10,
                               wait_idle_s=0, write_user_ini=False)
        for k, v in over.items():
            setattr(a, k, v)
        return a

    def run_with(self, speeds, images=None, errors=None):
        order = []
        logs = []
        out = tempfile.mkdtemp(dir=self.tmp)      # ผลแต่ละครั้งแยกโฟลเดอร์ (ชื่อไฟล์ผลมีเวลาแค่ระดับวินาที)

        def start(port, preset, logp):
            order.append(os.path.basename(logp))
            return object()

        def bench(port, model, tokens, log=None, repeat=1):
            name = order[-1]
            if errors and name in errors:
                return {"model": model, "error": errors[name]}
            vals = speeds[name]
            return {"model": model, "error": None, "gen_tps": sorted(vals)[len(vals) // 2],
                    "runs": [{"gen_tps": v} for v in vals]}
        with mock.patch.object(gp, "published_dir", return_value=self.tmp), \
                mock.patch.object(gp, "router_busy", return_value=(False, [])), \
                mock.patch.object(gb, "available_commit_gb", return_value=40.0), \
                mock.patch.object(gb, "start_test_router", side_effect=start), \
                mock.patch.object(gb, "stop_test_router"), \
                mock.patch.object(gb, "vram_snapshot", return_value=None), \
                mock.patch.object(gb, "bench_model", side_effect=bench), \
                mock.patch.object(gb, "image_check",
                                  side_effect=lambda *a: {"image_ok": (images or {}).get(order[-1], True)}):
            rc = gb.run_variants(self.args(out_dir=out), log=logs.append)
        path = [os.path.join(out, f) for f in os.listdir(out) if f.endswith(".json")][0]
        with open(path, encoding="utf-8") as fh:
            return rc, order, json.load(fh)

    def test_abba_order_and_pooled_median(self):
        speeds = {"router-base-r1.log": [1.00, 1.10], "router-c_mmproj_cpu-r1.log": [0.96, 0.98],
                  "router-c_mmproj_cpu-r2.log": [1.08, 1.12], "router-base-r2.log": [1.02, 1.04]}
        rc, order, doc = self.run_with(speeds)
        self.assertEqual(rc, gb.EXIT_OK)
        self.assertEqual(order, ["router-base-r1.log", "router-c_mmproj_cpu-r1.log",
                                 "router-c_mmproj_cpu-r2.log", "router-base-r2.log"])
        rows = {r["variant"]: r for r in doc["results"]}
        self.assertEqual(doc["rounds"], 2)
        self.assertEqual(rows["base"]["gen_tps"], 1.03)            # ค่ากลางของ 1.00 1.02 1.04 1.10
        self.assertEqual(rows["c_mmproj_cpu"]["gen_tps"], 1.03)    # 0.96 0.98 1.08 1.12
        self.assertEqual(len(rows["c_mmproj_cpu"]["rounds"]), 2)
        self.assertTrue(rows["c_mmproj_cpu"]["image_ok"])
        self.assertEqual(doc["recommendation"]["name"], "c_mmproj_cpu")

    def test_image_must_pass_every_round_and_partial_error_reported(self):
        speeds = {"router-base-r1.log": [1.0, 1.0], "router-base-r2.log": [1.0, 1.0],
                  "router-c_mmproj_cpu-r1.log": [1.0, 1.0], "router-c_mmproj_cpu-r2.log": [1.0, 1.0]}
        _rc, _o, doc = self.run_with(speeds, images={"router-c_mmproj_cpu-r2.log": False})
        self.assertIsNone(doc["recommendation"]["name"], "ถามรูปไม่ผ่านรอบใดรอบหนึ่ง = ไม่แนะนำ")
        rc, _o, doc = self.run_with(speeds, errors={"router-c_mmproj_cpu-r1.log": "HTTP 500"})
        rows = {r["variant"]: r for r in doc["results"]}
        self.assertEqual(rows["c_mmproj_cpu"]["round_errors"], ["HTTP 500"])
        self.assertEqual(rows["c_mmproj_cpu"]["gen_tps"], 1.0)
        self.assertEqual(rc, gb.EXIT_SOME_FAILED)

    def test_all_rounds_failed_keeps_error(self):
        row = gb.merge_rounds("a_ctx64k", {"ctx-size": "65536"}, gb.PRIMARY_27B,
                              [{"error": "x"}, {"skipped": "mem"}])
        self.assertEqual(row["error"], "x")
        self.assertNotIn("gen_tps", row)


class RepeatTests(unittest.TestCase):
    def test_median_of_runs(self):
        docs = iter([({}, 1.0)] + [({"timings": {"predicted_per_second": v, "predicted_n": 16}}, 10.0)
                                   for v in (1.0, 3.0, 2.0)])
        with mock.patch.object(gb, "post_chat", side_effect=lambda *a, **k: next(docs)):
            r = gb.bench_model(1, "m", 16, log=lambda *a: None, repeat=3)
        self.assertEqual(r["gen_tps"], 2.0)
        self.assertEqual(len(r["runs"]), 3)
        self.assertIsNone(r["error"])


if __name__ == "__main__":
    unittest.main()
