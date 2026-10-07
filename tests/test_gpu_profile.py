# -*- coding: utf-8 -*-
"""
เทสต์ของ C:\\LLM\\gpu_profile.py — stdlib unittest ล้วน

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

ส่วนใหญ่ทดสอบ plan() ซึ่งเป็นฟังก์ชันบริสุทธิ์ ด้วยขนาดไฟล์/KV ของโมเดลจริงในเครื่อง
(สร้างไฟล์ 16 GB ปลอมไม่ได้) และมีบางเทสต์ที่อ่านโฟลเดอร์โมเดลจริงแบบอ่านอย่างเดียว
ถ้าไม่มีโฟลเดอร์นั้นเทสต์กลุ่มนั้นจะถูกข้าม ไม่มีเทสต์ไหนแตะ router หรือ GPU จริง
"""
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gpu_profile as gp  # noqa: E402

REAL_MODELS = r"C:\LLM\models"
ID27 = "Qwen3.8-27B-UD-Q4_K_M"
IDCODER = "Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL"
IDOSS = "gpt-oss-20b-MXFP4"
ID4B = "Qwen3-4B-Instruct-2507-Q4_K_M"
MMPROJ = r"C:\LLM\models\mmproj-Qwen3.8-27B-F16.gguf"

RTX1000 = ("NVIDIA RTX 1000 Ada Generation Laptop GPU", 6140)
RTX4090 = ("NVIDIA GeForce RTX 4090", 24564)
RTX4060TI = ("NVIDIA GeForce RTX 4060 Ti", 8188)
A6000 = ("NVIDIA RTX A6000", 49140)


def dev(i, spec, bus=None):
    name, total = spec
    return gp._finish_device({"id": "CUDA%d" % i, "name": name, "total_mib": total, "free_mib": total - 500,
                              "pci_bus_id": bus or "00000000:%02X:00.0" % (i + 1)})


def gpus(*specs):
    return [dev(i, s) for i, s in enumerate(specs)]


def real_models():
    """ตัวเลขจากไฟล์จริง (ขนาดไฟล์ + metadata ที่อ่านด้วย gguf) — ไม่ต้องมีไฟล์ก็เทสต์ได้"""
    return [
        gp.ModelInfo(id=IDOSS, path="x", size_bytes=12109566624, arch="gpt-oss", kv_elems_full=12288,
                     kv_elems_swa=12288, swa_window=128, expert_bytes=10178887680, expert_used=4,
                     expert_count=32, token_embd_bytes=615329280),
        gp.ModelInfo(id=ID4B, path="x", size_bytes=2497281120, arch="qwen3", kv_elems_full=73728,
                     token_embd_bytes=319065600),
        gp.ModelInfo(id=IDCODER, path="x", size_bytes=17665334432, arch="qwen3moe", kv_elems_full=49152,
                     expert_bytes=16634609664, expert_used=8, expert_count=128, token_embd_bytes=175030272),
        gp.ModelInfo(id=ID27, path="x", size_bytes=16464440224, arch="qwen35", basename="Qwen3.8-27B",
                     kv_elems_full=32768, mmproj_path=MMPROJ, mmproj_bytes=927607488,
                     token_embd_bytes=715161600),
    ]


def run_plan(devices, **kw):
    return gp.plan(devices, real_models(), gp.Options(**kw))


def device_keys(res):
    return {k: v.get("device") for k, v in res["sections"].items() if k != "*" and v.get("device")}


def shorts(res, devices, model):
    by = {d["id"]: d["short"] for d in devices}
    return [by[i] for i in res["placement"][model]["devices"]]


# ---------------------------------------------------------------- GGUF ปลอมขนาดเล็ก
_FMT = {4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q"}


def _s(x):
    b = x.encode("utf-8")
    return struct.pack("<Q", len(b)) + b


def write_gguf(path, meta, tensors=()):
    """meta = [(key, type, value)] (type 8 = string, 9 = (elem_type, [values])), tensors = [(name, nbytes)]"""
    buf = bytearray(b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", len(tensors)) + struct.pack("<Q", len(meta)))
    for k, t, v in meta:
        buf += _s(k) + struct.pack("<I", t)
        if t == 8:
            buf += _s(v)
        elif t == 9:
            et, vals = v
            buf += struct.pack("<I", et) + struct.pack("<Q", len(vals))
            for x in vals:
                buf += _s(x) if et == 8 else struct.pack(_FMT[et], x)
        else:
            buf += struct.pack(_FMT[t], v)
    off = 0
    for name, nbytes in tensors:
        buf += _s(name) + struct.pack("<I", 1) + struct.pack("<Q", max(1, nbytes)) + struct.pack("<I", 0) \
            + struct.pack("<Q", off)
        off += (nbytes + 31) // 32 * 32
    buf += b"\0" * ((-len(buf)) % 32)
    buf += b"\0" * off
    with open(path, "wb") as f:
        f.write(bytes(buf))


def plain_meta(arch="llama", layers=4, kv=2, klen=64, extra=()):
    return [("general.architecture", 8, arch), ("%s.block_count" % arch, 4, layers),
            ("%s.attention.head_count" % arch, 4, 8), ("%s.attention.head_count_kv" % arch, 4, kv),
            ("%s.embedding_length" % arch, 4, 512), ("%s.attention.key_length" % arch, 4, klen),
            ("%s.attention.value_length" % arch, 4, klen)] + list(extra)


def mmproj_meta(dim):
    """ส่วนหัวของ mmproj แบบย่อ — projection_dim = ขนาดเวกเตอร์ที่ส่งให้โมเดลภาษา"""
    return [("general.architecture", 8, "clip"), ("general.type", 8, "mmproj"),
            ("clip.has_vision_encoder", 7, True), ("clip.vision.projection_dim", 4, dim)]


class TmpDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gpuprof-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ================================================================ นโยบาย (ผลที่คาดหวังตามสเปก)
class PolicyTests(unittest.TestCase):
    def test_internal_only_reproduces_today(self):
        devs = gpus(RTX1000)
        res = run_plan(devs)
        self.assertEqual(res["profile"], "internal-only")
        self.assertEqual(device_keys(res), {})
        self.assertEqual(res["sections"]["*"], {"ctx-size": "32768", "cache-type-k": "q8_0",
                                                "cache-type-v": "q8_0", "threads": "6"})
        # ไม่มี section ของโมเดลไหนมี key เลย → preset = [*] อย่างเดียว = ค่าเดิมทุกอย่าง
        self.assertTrue(all(not v for k, v in res["sections"].items() if k != "*"))
        self.assertFalse(res["placement"][ID27]["vision"])

    def test_no_gpu_cpu_only(self):
        res = run_plan([])
        self.assertEqual(res["profile"], "cpu-only")
        self.assertEqual(device_keys(res), {})
        self.assertTrue(all(not v for k, v in res["sections"].items() if k != "*"))
        self.assertEqual(res["placement"][ID27]["devices"], [])

    def test_discovery_failed_is_unknown_and_neutral(self):
        res = run_plan(None)
        self.assertEqual(res["profile"], "unknown")
        self.assertEqual(device_keys(res), {})
        self.assertEqual(res["sections"]["*"]["ctx-size"], "32768")

    def test_rtx1000_plus_4090(self):
        devs = gpus(RTX1000, RTX4090)
        res = run_plan(devs)
        self.assertEqual(res["profile"], "egpu-single-fit")
        sec = res["sections"]
        self.assertEqual(sec[ID27], {"device": "CUDA1", "ctx-size": "65536", "mmproj": MMPROJ})
        for m in (IDCODER, IDOSS, ID4B):
            self.assertEqual(sec[m], {"device": "CUDA0"})
        p = res["placement"][ID27]
        self.assertTrue(p["fits_fully"] and p["vision"] and p["primary"])
        self.assertEqual(p["ctx"], 65536)
        self.assertAlmostEqual(p["est_vram_gib"], 19.8, places=1)
        self.assertGreater(p["est_gen_tps"], 25)

    def test_rtx1000_plus_4060ti(self):
        devs = gpus(RTX1000, RTX4060TI)
        res = run_plan(devs)
        self.assertEqual(res["profile"], "egpu-multi")
        for m in (ID27, IDCODER, IDOSS, ID4B):
            self.assertEqual(res["sections"][m].get("device"), "CUDA1,CUDA0")   # 4060 Ti ก่อน
            self.assertNotIn("ctx-size", res["sections"][m])
            self.assertNotIn("mmproj", res["sections"][m])
            self.assertEqual(res["placement"][m]["ctx"], 32768)
        self.assertFalse(res["placement"][ID27]["vision"])

    def test_4060ti_first_in_natural_order_needs_no_device_key(self):
        devs = gpus(RTX4060TI, RTX1000)
        res = run_plan(devs)
        self.assertEqual(device_keys(res), {})
        self.assertEqual(shorts(res, devs, ID27), ["RTX 4060 Ti", "RTX 1000 Ada"])

    def test_rtx1000_plus_4090_plus_4060ti(self):
        devs = gpus(RTX1000, RTX4060TI, RTX4090)
        res = run_plan(devs)
        self.assertEqual(res["sections"][ID27]["device"], "CUDA2")
        for m in (IDCODER, IDOSS, ID4B):
            self.assertEqual(res["sections"][m]["device"], "CUDA1,CUDA0")
        self.assertEqual(shorts(res, devs, ID4B), ["RTX 4060 Ti", "RTX 1000 Ada"])

    def test_4090_index_does_not_matter(self):
        a = gpus(RTX4090, RTX1000)
        b = gpus(RTX1000, RTX4090)
        c = gpus(RTX4090, RTX4060TI, RTX1000)
        d = gpus(RTX1000, RTX4060TI, RTX4090)
        for devs_x, devs_y in ((a, b), (c, d)):
            rx, ry = run_plan(devs_x), run_plan(devs_y)
            for m in (ID27, IDCODER, ID4B):
                self.assertEqual(shorts(rx, devs_x, m), shorts(ry, devs_y, m))
                self.assertEqual(rx["placement"][m]["ctx"], ry["placement"][m]["ctx"])
            self.assertEqual(shorts(rx, devs_x, ID27), ["RTX 4090"])

    def test_two_big_gpus_primary_on_largest(self):
        devs = gpus(RTX4090, A6000)
        res = run_plan(devs)
        self.assertEqual(res["sections"][ID27]["device"], "CUDA1")
        self.assertEqual(res["sections"][ID4B]["device"], "CUDA0")
        # เท่ากันทุกอย่าง: เอาตัวที่เลข CUDA ต่ำกว่า และโมเดลอื่นไปอีกตัว
        devs2 = gpus(RTX4090, RTX4090)
        res2 = run_plan(devs2)
        self.assertEqual(res2["sections"][ID27]["device"], "CUDA0")
        self.assertEqual(res2["sections"][ID4B]["device"], "CUDA1")

    def test_4090_alone_shares_without_device_keys(self):
        devs = [dev(0, RTX4090)]
        res = run_plan(devs)
        self.assertEqual(res["profile"], "egpu-single-fit")
        self.assertEqual(device_keys(res), {})
        self.assertEqual(res["sections"][ID27], {"ctx-size": "65536", "mmproj": MMPROJ})
        self.assertTrue(res["placement"][ID4B]["shared_with_primary"])
        # ใช้การ์ดร่วมกัน: คิดจากที่เหลือหลังหัก 27B (~19.8 จาก 23 GB) ไม่ใช่ทั้งใบ
        coder = res["placement"][IDCODER]
        self.assertFalse(coder["fits_fully"])
        self.assertAlmostEqual(coder["est_gpu_gib"], 3.2, places=1)
        self.assertLess(coder["est_gen_tps"], 60)
        th, en = gp.build_summary(devs, "simulate", res)
        self.assertIn("GPU เดียวกัน", th)
        self.assertIn("the same GPU", en)

    def test_ctx_override_applies_to_every_model(self):
        res = run_plan(gpus(RTX1000, RTX4090), ctx=16384)
        self.assertEqual(res["sections"]["*"]["ctx-size"], "16384")
        for m in (ID27, IDCODER, IDOSS, ID4B):
            self.assertNotIn("ctx-size", res["sections"][m])
            self.assertEqual(res["placement"][m]["ctx"], 16384)
        self.assertEqual(res["sections"][ID27]["device"], "CUDA1")

    def test_primary_override(self):
        devs = gpus(RTX1000, RTX4090)
        res = run_plan(devs, primary=IDCODER)
        self.assertEqual(res["primary"], IDCODER)
        self.assertEqual(res["sections"][IDCODER]["device"], "CUDA1")
        self.assertNotIn("mmproj", res["sections"][IDCODER])            # Coder ไม่มี mmproj
        self.assertEqual(res["sections"][ID27], {"device": "CUDA0"})
        res2 = run_plan(devs, primary=IDCODER.lower())                  # ไม่สนตัวพิมพ์
        self.assertEqual(res2["primary"], IDCODER)

    def test_unknown_primary_falls_back_with_warning(self):
        res = run_plan(gpus(RTX1000, RTX4090), primary="no-such-model")
        self.assertEqual(res["primary"], ID27)
        self.assertTrue(any("no-such-model" in w for w in res["warnings"]))

    def test_no_vision_in_fit_case(self):
        res = run_plan(gpus(RTX1000, RTX4090), vision=False)
        self.assertNotIn("mmproj", res["sections"][ID27])
        self.assertEqual(res["sections"][ID27]["ctx-size"], "65536")
        self.assertFalse(res["placement"][ID27]["vision"])

    def test_vision_forced_when_not_fitting(self):
        res = run_plan(gpus(RTX1000), vision=True)
        self.assertEqual(res["sections"][ID27], {"mmproj": MMPROJ})
        self.assertTrue(res["placement"][ID27]["vision"])
        for m in (IDCODER, IDOSS, ID4B):
            self.assertNotIn("mmproj", res["sections"][m])

    def test_mid_size_gpu_drops_to_32k_but_keeps_vision(self):
        # 20 GB: 27B + vision ที่ 65536 ไม่พอ แต่ 32768 พอ
        res = run_plan(gpus(RTX1000, ("NVIDIA RTX 4000 Ada Generation", 20475)))
        self.assertEqual(res["sections"][ID27].get("device"), "CUDA1")
        self.assertNotIn("ctx-size", res["sections"][ID27])
        self.assertEqual(res["placement"][ID27]["ctx"], 32768)
        self.assertTrue(res["placement"][ID27]["vision"])

    def test_16gb_gpu_does_not_hold_27b(self):
        res = run_plan(gpus(RTX1000, ("NVIDIA GeForce RTX 4080", 16376)))
        self.assertEqual(res["profile"], "egpu-multi")
        self.assertEqual(res["sections"][ID27]["device"], "CUDA1,CUDA0")

    def test_no_primary_model_present(self):
        models = [m for m in real_models() if m.id != ID27]
        res = gp.plan(gpus(RTX1000, RTX4090), models, gp.Options())
        self.assertIsNone(res["primary"])
        self.assertEqual(res["sections"][ID4B]["device"], "CUDA1,CUDA0")

    def test_threads_in_star_section(self):
        res = run_plan(gpus(RTX1000), threads=8)
        self.assertEqual(res["sections"]["*"]["threads"], "8")

    def test_summary_mentions_devices(self):
        devs = gpus(RTX1000, RTX4090)
        res = run_plan(devs)
        th, en = gp.build_summary(devs, "simulate", res)
        self.assertIn("RTX 4090", th)
        self.assertIn("65,536", th)
        self.assertIn("RTX 4090", en)
        stars = [l for l in th.splitlines() if l.startswith("★ ")]
        self.assertEqual(len(stars), 1)
        self.assertTrue(stars[0].startswith("★ " + ID27))
        # บอกวิธีให้โมเดลอื่นใช้ 4090 ด้วย (ค่าปริยายกันการ์ดใหญ่ไว้ให้ 27B)
        self.assertIn("device = CUDA1,CUDA0", th)
        self.assertIn("device = CUDA1,CUDA0", en)


class NumbersTests(unittest.TestCase):
    def test_kv_bytes_per_token_match_known_values(self):
        want = {ID27: 34816, IDCODER: 52224, IDOSS: 13056, ID4B: 78336}
        for m in real_models():
            self.assertEqual(m.kv_bytes_per_token(), want[m.id], m.id)

    def test_swa_counts_only_window(self):
        oss = real_models()[0]
        self.assertEqual(oss.kv_bytes(32768) - oss.kv_bytes(16384), 13056 * 16384)
        self.assertEqual(oss.kv_bytes(1000), int(12288 * 1.0625 * 1000 + 12288 * 1.0625 * 128))

    def test_budget_uses_total_minus_reserve(self):
        d = dev(0, RTX4090)
        d["free_mib"] = 100          # router ตัวจริงถือ VRAM อยู่ ต้องไม่กระทบแผน
        self.assertEqual(gp.budget_bytes(d), (24564 - 1024) * 1024 * 1024)

    def test_internal_speeds_cover_measured(self):
        """ช่วงที่แสดงต้องครอบค่าที่วัดจริงบนเครื่องนี้ ทั้งตอนเครื่องว่างและตอน benchmark ของผู้ใช้รันอยู่"""
        def rng(p):
            return p["est_gen_tps_busy"] * gp.SPEED_RANGE[0], p["est_gen_tps"] * gp.SPEED_RANGE[1]
        res = run_plan(gpus(RTX1000))
        lo, hi = rng(res["placement"][ID27])
        self.assertTrue(lo <= 1.2 and hi >= 2.18, (lo, hi))       # 1.2-1.4 (CPU ยุ่ง), 2.07-2.18 (ว่าง)
        lo, hi = rng(res["placement"][ID4B])
        self.assertTrue(lo <= 27.15 <= hi and lo <= 29.8 <= hi, (lo, hi))
        lo, hi = rng(run_plan([])["placement"][ID4B])
        self.assertTrue(lo <= 13.43 <= hi, (lo, hi))               # 4B บน CPU ล้วน

    def test_short_names_and_internal_flag(self):
        self.assertEqual(gp.short_name(RTX1000[0]), "RTX 1000 Ada")
        self.assertEqual(gp.short_name(RTX4090[0]), "RTX 4090")
        self.assertEqual(gp.short_name(RTX4060TI[0]), "RTX 4060 Ti")
        self.assertFalse(dev(0, RTX1000)["external"])
        self.assertTrue(dev(0, RTX4090)["external"])
        self.assertEqual(gp.bandwidth_gbps(RTX4060TI[0]), 288)
        self.assertEqual(gp.bandwidth_gbps(RTX4090[0]), 1008)


# ================================================================ INI / user override
class IniTests(unittest.TestCase):
    def test_valid_model_id(self):
        for bad in ("a[b", "a]b", "a=b", "a\nb", "a\rb", ";x", "#x", "", " x"):
            self.assertFalse(gp.valid_model_id(bad), repr(bad))
        for good in (ID27, IDOSS, "Model.v2-Q8_0", "ชื่อไทย-Q4"):
            self.assertTrue(gp.valid_model_id(good), good)

    def test_render_and_parse_roundtrip(self):
        res = run_plan(gpus(RTX1000, RTX4090))
        text = gp.render_preset(res["sections"], ["หัวไฟล์ภาษาไทย", "header"])
        parsed, warns = gp.parse_ini(text)
        self.assertEqual(warns, [])
        self.assertEqual(parsed["*"], res["sections"]["*"])
        self.assertEqual(parsed[ID27], res["sections"][ID27])
        self.assertNotIn("\ufeff", text)

    def test_user_override_merge(self):
        res = run_plan(gpus(RTX1000, RTX4090))
        user = ("\ufeff; my overrides\r\n[*]\r\nthreads = 8\r\n\r\n[%s]\r\ndevice =\r\nctx-size = 4096\r\n"
                "[NoSuchModel]\r\nctx-size = 1\r\n[MyCustom]\r\nmodel = C:\\x.gguf\r\n"
                "[%s]\r\nbad key = 1\r\n" % (ID4B, ID27))
        merged, warns = gp.merge_user_overrides(res["sections"], user, [m.id for m in real_models()])
        self.assertEqual(merged["*"]["threads"], "8")
        self.assertEqual(merged["*"]["ctx-size"], "32768")
        self.assertNotIn("device", merged[ID4B])                  # ค่าว่าง = ลบ
        self.assertEqual(merged[ID4B]["ctx-size"], "4096")
        self.assertNotIn("NoSuchModel", merged)                   # จะกลายเป็นโมเดลเสียใน router
        self.assertEqual(merged["MyCustom"], {"model": "C:\\x.gguf"})
        self.assertEqual(merged[ID27]["device"], "CUDA1")
        self.assertTrue(any("NoSuchModel" in w for w in warns))
        self.assertTrue(any("bad key" in w for w in warns))


# ================================================================ อ่าน GGUF
class GgufTests(TmpDir):
    def test_plain_model(self):
        p = os.path.join(self.tmp, "plain.gguf")
        write_gguf(p, plain_meta(layers=4, kv=2, klen=64), [("token_embd.weight", 1000), ("blk.0.attn_q.weight", 64)])
        meta, tensors = gp.read_gguf(p)
        self.assertEqual(gp.kv_layout(meta), (4 * 2 * 128, 0, 0))
        self.assertEqual(dict(tensors)["token_embd.weight"], 1024)     # ปัดตาม alignment 32

    def test_hybrid_ssm_counts_only_attention_layers(self):
        meta = plain_meta("qwen35", layers=65, kv=4, klen=256, extra=[
            ("qwen35.nextn_predict_layers", 4, 1), ("qwen35.full_attention_interval", 4, 4),
            ("qwen35.ssm.state_size", 4, 128)])
        p = os.path.join(self.tmp, "hyb.gguf")
        write_gguf(p, meta)
        full, swa, win = gp.kv_layout(gp.read_gguf(p)[0])
        self.assertEqual((full, swa, win), (16 * 4 * 512, 0, 0))

    def test_sliding_window_known_pattern(self):
        meta = plain_meta("gpt-oss", layers=24, kv=8, klen=64, extra=[("gpt-oss.attention.sliding_window", 4, 128)])
        p = os.path.join(self.tmp, "oss.gguf")
        write_gguf(p, meta)
        self.assertEqual(gp.kv_layout(gp.read_gguf(p)[0]), (12 * 8 * 128, 12 * 8 * 128, 128))

    def test_sliding_window_bool_array_pattern(self):
        meta = plain_meta("xarch", layers=4, kv=1, klen=10, extra=[
            ("xarch.attention.sliding_window", 4, 64),
            ("xarch.attention.sliding_window_pattern", 9, (7, [True, True, True, False]))])
        p = os.path.join(self.tmp, "swa.gguf")
        write_gguf(p, meta)
        self.assertEqual(gp.kv_layout(gp.read_gguf(p)[0]), (20, 60, 64))

    def test_moe_expert_bytes_and_string_arrays(self):
        meta = plain_meta("qwen3moe", extra=[("qwen3moe.expert_count", 4, 8), ("qwen3moe.expert_used_count", 4, 2),
                                            ("tokenizer.ggml.tokens", 9, (8, ["a", "bb", "ccc"] * 2000))])
        p = os.path.join(self.tmp, "moe.gguf")
        write_gguf(p, meta, [("blk.0.ffn_up_exps.weight", 4096), ("blk.0.ffn_down_exps.weight", 4096),
                             ("blk.0.ffn_up_shexp.weight", 64), ("output.weight", 320)])
        w = []
        info = gp.build_model_info("moe", [p], w)
        self.assertEqual(w, [])
        self.assertEqual(info.expert_bytes, 8192)
        self.assertEqual((info.expert_used, info.expert_count), (2, 8))

    def test_truncated_file_is_reported_not_raised(self):
        p = os.path.join(self.tmp, "broken.gguf")
        write_gguf(p, plain_meta())
        with open(p, "r+b") as f:
            f.truncate(40)
        w = []
        info = gp.build_model_info("broken", [p], w)
        self.assertIsNotNone(info.error)
        self.assertTrue(w)

    def test_scan_skips_mmproj_mtp_bad_names_and_uses_router_shard_ids(self):
        mk = lambda n: write_gguf(os.path.join(self.tmp, n), plain_meta())   # noqa: E731
        for n in ("Good-7B-Q4.gguf", "mtp-Good-Q4_0.gguf", "bad[name].gguf",
                  "a=b.gguf", "Big-00001-of-00002.gguf", "Big-00002-of-00002.gguf", "notes.txt"):
            mk(n)
        write_gguf(os.path.join(self.tmp, "mmproj-Good-7B-F16.gguf"), mmproj_meta(512))
        w = []
        models = gp.scan_models(self.tmp, w)
        # router (b10984) แสดง shard ทุกไฟล์ตามชื่อไฟล์เต็ม — id ต้องตรงกับที่ router ใช้ ไม่ใช่ "Big"
        self.assertEqual([m.id for m in models], ["Big-00001-of-00002", "Good-7B-Q4"])
        big = models[0]
        self.assertEqual(big.size_bytes, 2 * os.path.getsize(os.path.join(self.tmp, "Big-00001-of-00002.gguf")))
        self.assertEqual(big.shard_ids, ["Big-00002-of-00002"])
        self.assertTrue(any("Big-00001-of-00002" in x and "2 ไฟล์" in x for x in w), w)
        self.assertEqual(os.path.basename(models[1].mmproj_path), "mmproj-Good-7B-F16.gguf")
        self.assertIsNone(big.mmproj_path)
        self.assertEqual(len([x for x in w if "ข้ามไฟล์" in x]), 2)
        # preset ต้องไม่มี section ชื่อ "Big" เฉยๆ (router จะสร้างโมเดลเสียที่ไม่มี --model)
        res = gp.plan(gpus(RTX1000, RTX4090), models, gp.Options(primary="Good-7B-Q4"))
        self.assertNotIn("Big", res["sections"])
        self.assertEqual(res["sections"]["Big-00001-of-00002"].get("device"), "CUDA0")
        # section ของ shard ที่ 2 ใน user.ini ไม่ถูกเตือนว่า "ไม่มีโมเดลชื่อนี้" (router ก็แสดงชื่อนี้)
        known = [m.id for m in models] + [s for m in models for s in m.shard_ids]
        _, warns = gp.merge_user_overrides(res["sections"], "[Big-00002-of-00002]\nthreads = 4\n", known)
        self.assertEqual(warns, [])

    def _mm(self, name, dim):
        write_gguf(os.path.join(self.tmp, name), mmproj_meta(dim))
        return name

    def test_mmproj_prefix_boundary(self):
        names = [self._mm("mmproj-Qwen3.8-27B2-F16.gguf", 5120), self._mm("mmproj-Qwen3.8-27B-F16.gguf", 5120)]
        m = gp.ModelInfo(id="Qwen3.8-27B-UD-Q4_K_M", path="x", size_bytes=1, basename="Qwen3.8-27B", n_embd=5120)
        self.assertEqual(os.path.basename(gp.find_mmproj(m, self.tmp, names)), "mmproj-Qwen3.8-27B-F16.gguf")
        # ของรุ่นอื่นที่ชื่อขึ้นต้นเหมือนกันต้องไม่ถูกหยิบมาใช้
        self.assertIsNone(gp.find_mmproj(m, self.tmp, ["mmproj-Qwen3.8-27B2-F16.gguf"]))
        m2 = gp.ModelInfo(id="Other-7B-Q4", path="x", size_bytes=1)
        self.assertIsNone(gp.find_mmproj(m2, self.tmp, names))

    def test_mmproj_short_basename_does_not_grab_other_family(self):
        names = [self._mm("mmproj-Qwen3.8-27B-F16.gguf", 5120)]
        # convert_hf_to_gguf เขียน basename สั้นๆ แบบ "Qwen3" ได้ — "mmproj-qwen3" + ".8-27b..." ต้องไม่นับ
        q3 = gp.ModelInfo(id="Qwen3-14B-Q4_K_M", path="x", size_bytes=1, basename="Qwen3", n_embd=5120)
        self.assertIsNone(gp.find_mmproj(q3, self.tmp, names))
        # basename ไม่มีขนาด ("Qwen3.8" ของรุ่น 9B) ผ่านเงื่อนไข "-" แต่มิติไม่ตรง (4096 ≠ 5120) → ไม่ใช้
        q9 = gp.ModelInfo(id="Qwen3.8-9B-Q4_K_M", path="x", size_bytes=1, basename="Qwen3.8", n_embd=4096)
        self.assertIsNone(gp.find_mmproj(q9, self.tmp, names))

    def test_mmproj_exact_name_and_unreadable(self):
        names = [self._mm("mmproj-Good-7B.gguf", 512)]
        good = gp.ModelInfo(id="Good-7B-Q4", path="x", size_bytes=1, n_embd=512)
        self.assertEqual(os.path.basename(gp.find_mmproj(good, self.tmp, names)), "mmproj-Good-7B.gguf")
        with open(os.path.join(self.tmp, "mmproj-Bad-7B-F16.gguf"), "wb") as f:
            f.write(b"not a gguf at all, truncated")
        bad = gp.ModelInfo(id="Bad-7B-Q4", path="x", size_bytes=1, n_embd=512)
        self.assertIsNone(gp.find_mmproj(bad, self.tmp, ["mmproj-Bad-7B-F16.gguf"]))

    def test_nextn_layer_not_counted(self):
        meta = plain_meta("llama", layers=5, kv=2, klen=64, extra=[("llama.nextn_predict_layers", 4, 1)])
        p = os.path.join(self.tmp, "nextn.gguf")
        write_gguf(p, meta)
        self.assertEqual(gp.kv_layout(gp.read_gguf(p)[0]), (4 * 2 * 128, 0, 0))


@unittest.skipUnless(os.path.isfile(os.path.join(REAL_MODELS, ID27 + ".gguf")), "ไม่มีโฟลเดอร์โมเดลจริง")
class RealModelsTests(unittest.TestCase):
    def test_scan_real_models(self):
        w = []
        models = {m.id: m for m in gp.scan_models(REAL_MODELS, w)}
        self.assertEqual(w, [])
        self.assertEqual(set(models), {ID27, IDCODER, IDOSS, ID4B})   # mmproj, mtp ไม่นับ
        want = {ID27: 34816, IDCODER: 52224, IDOSS: 13056, ID4B: 78336}
        for mid, v in want.items():
            self.assertEqual(models[mid].kv_bytes_per_token(), v, mid)
        self.assertEqual(os.path.basename(models[ID27].mmproj_path), "mmproj-Qwen3.8-27B-F16.gguf")
        self.assertIsNone(models[ID4B].mmproj_path)
        self.assertGreater(models[IDCODER].expert_bytes, 15e9)


# ================================================================ ตรวจ GPU
class DiscoveryTests(unittest.TestCase):
    LIST_OUT = ("ggml_cuda_init: found 2 CUDA devices\nAvailable devices:\n"
                "  CUDA0: NVIDIA RTX 1000 Ada Generation Laptop GPU (6140 MiB, 5083 MiB free)\n"
                "  CUDA1: NVIDIA GeForce RTX 4090 (24563 MiB, 23000 MiB free)\n")

    def test_parse_list_devices(self):
        d = gp.parse_list_devices(self.LIST_OUT)
        self.assertEqual([x["id"] for x in d], ["CUDA0", "CUDA1"])
        self.assertEqual(d[1]["total_mib"], 24563)
        self.assertEqual(gp.parse_list_devices("E ggml_cuda_init: failed\nAvailable devices:\n  (none)\n"), [])
        with self.assertRaises(gp.DiscoveryError):
            gp.parse_list_devices("garbage")

    def test_nvidia_smi_missing_gives_none(self):
        self.assertIsNone(gp.current_fingerprint(exe=r"C:\definitely\not\here\nvidia-smi.exe"))

    def test_fingerprint_is_order_independent(self):
        a = gp.fingerprint_from_rows([("A", "1", "b1"), ("B", "2", "b2")])
        b = gp.fingerprint_from_rows([("B", "2", "b2"), ("A", "1", "b1")])
        self.assertEqual(a, b)
        self.assertNotEqual(a, gp.fingerprint_from_rows([("A", "1", "b1")]))

    def test_list_devices_missing_exe(self):
        with self.assertRaises(gp.DiscoveryError):
            gp.list_devices_llama(exe=r"C:\definitely\not\here\llama-server.exe")

    def test_list_devices_hang_times_out(self):
        # ping ค้างราว 30 วินาที — ต้องตัดที่ 1 วินาทีแล้วรายงานเป็น DiscoveryError
        import time as _t
        t0 = _t.monotonic()
        with self.assertRaises(gp.DiscoveryError) as cm:
            gp.list_devices_llama(timeout=1, cmd=["ping", "-n", "30", "127.0.0.1"])
        self.assertLess(_t.monotonic() - t0, 15)
        self.assertIn("ค้าง", str(cm.exception))

    def test_list_devices_fails_falls_back_to_nvidia_smi(self):
        smi = [{"name": RTX4090[0], "total_mib": 24564, "free_mib": 20000, "pci_bus_id": "00000000:3C:00.0"},
               {"name": RTX1000[0], "total_mib": 6141, "free_mib": 4000, "pci_bus_id": "00000000:01:00.0"}]
        with mock.patch.object(gp, "list_devices_llama", side_effect=gp.DiscoveryError("boom")), \
                mock.patch.object(gp, "_smi_devices", return_value=(smi, "fp")):
            w = []
            devices, source, fp = gp.discover(warnings=w)
        self.assertEqual(source, "nvidia-smi")
        self.assertEqual(fp, "fp")
        self.assertEqual([(d["id"], d["short"]) for d in devices], [("CUDA0", "RTX 1000 Ada"), ("CUDA1", "RTX 4090")])
        self.assertTrue(w)

    def test_both_fail_gives_unknown(self):
        with mock.patch.object(gp, "list_devices_llama", side_effect=gp.DiscoveryError("hang")), \
                mock.patch.object(gp, "_smi_devices", return_value=(None, None)):
            devices, source, fp = gp.discover(warnings=[])
        self.assertIsNone(devices)
        self.assertEqual(source, "failed")
        self.assertIsNone(fp)

    def test_fingerprint_from_same_smi_rows(self):
        # fingerprint ต้องคิดจากแถวดิบชุดเดียวกับรายการ GPU (ตรงกับ current_fingerprint ทุกตัวอักษร)
        rows = [["NVIDIA RTX 1000 Ada Generation Laptop GPU", "6141", "5000", "00000000:01:00.0"]]
        with mock.patch.object(gp, "_smi_query", return_value=rows) as q:
            devs, fp = gp._smi_devices()
        self.assertEqual(q.call_count, 1)
        self.assertEqual(devs[0]["total_mib"], 6141)
        self.assertEqual(fp, gp.fingerprint_from_rows([(rows[0][0], "6141", rows[0][3])]))

    def test_masked_gpus_warn(self):
        smi = [{"name": RTX1000[0], "total_mib": 6141, "free_mib": 4000, "pci_bus_id": "00000000:01:00.0"}]
        with mock.patch.object(gp, "list_devices_llama", return_value=[]), \
                mock.patch.object(gp, "_smi_devices", return_value=(smi, "fp")):
            w = []
            devices, source, fp = gp.discover(warnings=w)
        self.assertEqual(devices, [])
        self.assertTrue(any("CUDA_VISIBLE_DEVICES" in x for x in w), w)

    def test_bus_ids_identical_names_use_bus_order(self):
        # การ์ดรุ่นเดียวกันสองใบ: จับคู่ด้วยชื่อไม่ได้ ต้องใช้ลำดับ bus id (= ลำดับ CUDA ภายใต้ PCI_BUS_ID)
        text = ("Available devices:\n  CUDA0: NVIDIA GeForce RTX 4090 (24563 MiB, 23000 MiB free)\n"
                "  CUDA1: NVIDIA GeForce RTX 4090 (24563 MiB, 23000 MiB free)\n")
        devs = [gp._finish_device(d) for d in gp.parse_list_devices(text)]
        smi = [{"name": RTX4090[0], "total_mib": 24564, "free_mib": 1, "pci_bus_id": "00000000:5E:00.0"},
               {"name": RTX4090[0], "total_mib": 24564, "free_mib": 1, "pci_bus_id": "00000000:3C:00.0"}]
        gp._attach_bus_ids(devs, smi)
        self.assertEqual([d["pci_bus_id"] for d in devs], ["00000000:3C:00.0", "00000000:5E:00.0"])

    def test_bus_ids_attached_in_order(self):
        devs = [gp._finish_device(d) for d in gp.parse_list_devices(self.LIST_OUT)]
        smi = [{"name": RTX4090[0], "total_mib": 24564, "free_mib": 1, "pci_bus_id": "00000000:3C:00.0"},
               {"name": RTX1000[0], "total_mib": 6141, "free_mib": 1, "pci_bus_id": "00000000:01:00.0"}]
        gp._attach_bus_ids(devs, smi)
        self.assertEqual([d["pci_bus_id"] for d in devs], ["00000000:01:00.0", "00000000:3C:00.0"])


# ================================================================ CLI ทั้งเส้น (โมเดลจริง + GPU จำลอง)
@unittest.skipUnless(os.path.isfile(os.path.join(REAL_MODELS, ID27 + ".gguf")), "ไม่มีโฟลเดอร์โมเดลจริง")
class CliTests(TmpDir):
    def sim(self, *specs):
        p = os.path.join(self.tmp, "sim.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump([{"id": "CUDA%d" % i, "name": n, "total_mib": t, "free_mib": t - 100,
                        "pci_bus_id": "00000000:%02X:00.0" % (i + 1)} for i, (n, t) in enumerate(specs)], f)
        return p

    def run_cli(self, *extra, user_ini=None, choice="none"):
        # choice ปริยาย = none: ไม่ให้ C:\LLM\gpu-choice.json ตัวจริง (hub เขียนเมื่อผู้ใช้เลือก GPU) มากระทบผลเทสต์
        out = os.path.join(self.tmp, "out")
        argv = ["--write", "--models-dir", REAL_MODELS, "--out-dir", out,
                "--user-ini", user_ini or os.path.join(self.tmp, "no-user.ini"), "--choice", choice] + list(extra)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gp.main(argv)
        with open(os.path.join(out, gp.PRESET_NAME), "rb") as f:
            raw = f.read()
        with open(os.path.join(out, gp.PROFILE_NAME), "r", encoding="utf-8") as f:
            prof = json.load(f)
        return rc, raw, prof, buf.getvalue()

    def test_internal_only_cli_is_legacy_equivalent(self):
        rc, raw, prof, out = self.run_cli("--simulate", self.sim(RTX1000))
        self.assertEqual(rc, 0)
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))       # BOM ทำให้ router ล้ม
        sections, _ = gp.parse_ini(raw.decode("utf-8"))
        self.assertEqual(sections, {"*": {"ctx-size": "32768", "cache-type-k": "q8_0",
                                          "cache-type-v": "q8_0", "threads": "6"}})
        self.assertEqual(prof["profile"], "internal-only")
        for k in ("version", "generated_at", "fingerprint", "cuda_device_order", "profile", "devices",
                  "primary_model", "placement", "summary_th", "summary_en"):
            self.assertIn(k, prof)
        self.assertEqual(prof["version"], 1)
        self.assertEqual(prof["cuda_device_order"], "PCI_BUS_ID")
        self.assertEqual(prof["primary_model"], ID27)
        self.assertEqual(set(prof["devices"][0]) >= {"id", "name", "short", "total_mib", "free_mib", "external"}, True)
        for p in prof["placement"].values():
            for k in ("devices", "ctx", "vision", "fits_fully", "est_vram_gib", "note_th", "note_en"):
                self.assertIn(k, p)
        self.assertIn("RTX 1000 Ada", out)

    def test_cli_4090_and_options(self):
        sim = self.sim(RTX1000, RTX4090)
        rc, raw, prof, _ = self.run_cli("--simulate", sim)
        sec, _ = gp.parse_ini(raw.decode("utf-8"))
        self.assertEqual(sec[ID27]["device"], "CUDA1")
        self.assertEqual(sec[ID27]["ctx-size"], "65536")
        self.assertTrue(sec[ID27]["mmproj"].endswith("mmproj-Qwen3.8-27B-F16.gguf"))
        self.assertEqual(prof["placement"][ID27]["est_vram_gib"], 19.8)
        _, raw2, _, _ = self.run_cli("--simulate", sim, "--no-vision", "--ctx", "8192", "--threads", "4")
        sec2, _ = gp.parse_ini(raw2.decode("utf-8"))
        self.assertNotIn("mmproj", sec2[ID27])
        self.assertNotIn("ctx-size", sec2[ID27])
        self.assertEqual(sec2["*"]["ctx-size"], "8192")
        self.assertEqual(sec2["*"]["threads"], "4")
        _, raw3, prof3, _ = self.run_cli("--simulate", sim, "--primary", ID4B)
        sec3, _ = gp.parse_ini(raw3.decode("utf-8"))
        self.assertEqual(prof3["primary_model"], ID4B)
        self.assertEqual(sec3[ID4B]["device"], "CUDA1")
        _, raw4, _, _ = self.run_cli("--simulate", self.sim(RTX1000), "--vision")
        sec4, _ = gp.parse_ini(raw4.decode("utf-8"))
        self.assertIn("mmproj", sec4[ID27])

    def test_deterministic_output(self):
        sim = self.sim(RTX1000, RTX4060TI)
        _, a, pa, _ = self.run_cli("--simulate", sim)
        _, b, pb, _ = self.run_cli("--simulate", sim)
        self.assertEqual(a, b)
        self.assertEqual(pa["preset_sha1"], pb["preset_sha1"])
        self.assertEqual(pa["fingerprint"], pb["fingerprint"])

    def test_user_override_file(self):
        ui = os.path.join(self.tmp, "user.ini")
        with open(ui, "w", encoding="utf-8-sig") as f:       # Notepad อาจเซฟพร้อม BOM
            f.write("[%s]\nctx-size = 8192\n" % ID4B)
        _, raw, prof, _ = self.run_cli("--simulate", self.sim(RTX1000), user_ini=ui)
        sec, _ = gp.parse_ini(raw.decode("utf-8"))
        self.assertEqual(sec[ID4B], {"ctx-size": "8192"})
        self.assertEqual(prof["user_overrides"], ui)
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))

    def test_missing_models_dir_is_an_error(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gp.main(["--write", "--models-dir", os.path.join(self.tmp, "nope"), "--out-dir", self.tmp,
                          "--simulate", self.sim(RTX1000)])
        self.assertNotEqual(rc, 0)

    def test_bad_simulate_file_is_an_error(self):
        p = os.path.join(self.tmp, "bad.json")
        with open(p, "w") as f:
            f.write("{nope")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gp.main(["--write", "--models-dir", REAL_MODELS, "--out-dir", self.tmp, "--simulate", p])
        self.assertNotEqual(rc, 0)


# ================================================================ เทียบกับ router ที่รันอยู่
LEGACY_ARGS = ["llama-server.exe", "--host", "127.0.0.1", "--jinja", "--port", "59733", "--no-warmup",
               "--alias", ID27, "--ctx-size", "32768", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
               "--flash-attn", "on", "--fit", "on", "--model", r"C:\LLM\models\x.gguf", "--threads", "6"]


def fake_fetch(models, slots=None):
    def fetch(url, timeout=None, body=None):
        if url.endswith("/models"):
            return {"data": [{"id": mid, "status": {"value": st, "args": args}} for mid, st, args in models]}
        if "/slots?model=" in url:
            return (slots or {}).get(url.split("=", 1)[1], [])
        raise OSError("unexpected " + url)
    return fetch


_UNSET = object()


@unittest.skipUnless(os.path.isfile(os.path.join(REAL_MODELS, ID27 + ".gguf")), "ไม่มีโฟลเดอร์โมเดลจริง")
class CompareTests(TmpDir):
    def gen(self, *specs, name="new", fp="fp-real", devices=_UNSET, user=None, **opts):
        out = os.path.join(self.tmp, name)
        if devices is _UNSET:
            devices = [dev(i, s) for i, s in enumerate(specs)]
        ui = os.path.join(self.tmp, name + ".user.ini")
        if user is not None:
            with open(ui, "w", encoding="utf-8") as f:
                f.write(user)
        gp.generate(REAL_MODELS, out, gp.Options(**opts), user_ini=ui, choice=None,
                    discovery=(devices, "simulate" if devices is not None else "failed", fp))
        return out

    def state(self, src_dir, pid=4321, mode="preset", failed=None):
        path = os.path.join(self.tmp, "state.json")
        with mock.patch.object(gp, "current_fingerprint", return_value="fp-real"):
            gp.record_state(8199, pid, mode, src_dir, path, failed)
        return path

    def test_legacy_router_same_settings_is_unchanged(self):
        new = self.gen(RTX1000)
        fetch = fake_fetch([(ID27, "loaded", LEGACY_ARGS), (ID4B, "unloaded", LEGACY_ARGS)])
        changed, lines, keep = gp.compare_running(8199, 1234, os.path.join(self.tmp, "no-state.json"), new, fetch)
        self.assertFalse(changed, lines)
        self.assertFalse(keep)

    def test_legacy_router_vs_4090_is_changed(self):
        new = self.gen(RTX1000, RTX4090)
        fetch = fake_fetch([(ID27, "loaded", LEGACY_ARGS)])
        changed, lines, _ = gp.compare_running(8199, 1234, os.path.join(self.tmp, "no-state.json"), new, fetch)
        self.assertTrue(changed)
        self.assertTrue(any("device" in l and "CUDA1" in l for l in lines), lines)

    def test_state_fingerprint_change_is_changed(self):
        new = self.gen(RTX1000)
        state = self.state(new)
        fetch = fake_fetch([(ID27, "unloaded", LEGACY_ARGS)])
        changed, lines, _ = gp.compare_running(8199, 4321, state, new, fetch)
        self.assertFalse(changed, lines)
        with open(state, encoding="utf-8") as f:
            st = json.load(f)
        st["fingerprint"] = "deadbeef"
        with open(state, "w", encoding="utf-8") as f:
            json.dump(st, f)
        changed, lines, _ = gp.compare_running(8199, 4321, state, new, fetch)
        self.assertTrue(changed)
        self.assertTrue(any("GPU เปลี่ยน" in l for l in lines))
        # state ของ PID อื่น (router ถูกเปิดใหม่ไปแล้ว) ต้องไม่ถูกนำมาใช้
        changed, lines, _ = gp.compare_running(8199, 9999, state, new, fetch)
        self.assertFalse(changed)

    def test_nvidia_smi_failure_is_not_a_change(self):
        # GPU ชุดเดิม preset เดิม แค่ nvidia-smi ล้มตอนเปิดรอบนี้ → ห้ามรีสตาร์ต (ทิ้งโมเดลที่โหลดไว้)
        old = self.gen(RTX1000, name="old", fp="fp-real")
        new = self.gen(RTX1000, name="new", fp=None)
        state = self.state(old)
        fetch = fake_fetch([(ID27, "loaded", LEGACY_ARGS)])
        changed, lines, _ = gp.compare_running(8199, 4321, state, new, fetch)
        self.assertFalse(changed, lines)

    def test_comment_only_difference_is_not_a_change(self):
        old = self.gen(RTX1000, name="old")
        new = self.gen(RTX1000, name="new", user="; แค่คอมเมนต์ ไม่มีค่าอะไร\n")
        with open(os.path.join(old, gp.PRESET_NAME), encoding="utf-8") as a, \
                open(os.path.join(new, gp.PRESET_NAME), encoding="utf-8") as b:
            self.assertNotEqual(a.read(), b.read())          # หัวไฟล์ต่างกัน ("merged: ...")
        state = self.state(old)
        fetch = fake_fetch([(ID27, "loaded", LEGACY_ARGS)])
        changed, lines, _ = gp.compare_running(8199, 4321, state, new, fetch)
        self.assertFalse(changed, lines)

    def test_preset_diff_has_no_bare_lines(self):
        old = self.gen(RTX1000, RTX4090, name="old")
        new = self.gen(RTX1000, RTX4090, name="new", vision=False)
        state = self.state(old)
        changed, lines, _ = gp.compare_running(8199, 4321, state, new, fake_fetch([]))
        self.assertTrue(changed)
        diff = [l.strip() for l in lines if l.startswith("    ")]
        self.assertIn("-mmproj = " + MMPROJ, diff)
        self.assertFalse([l for l in diff if l in ("+", "-")], diff)

    def test_masked_gpu_run_then_normal_run_is_changed(self):
        # รอบก่อนซ่อน GPU (CUDA_VISIBLE_DEVICES=-1) → router เห็น CPU อย่างเดียว ลายนิ้วมือ nvidia-smi เท่าเดิม
        # preset เหมือนกันทุกตัว (ไม่มี device key ทั้งคู่) ต้องยังจับได้ว่า GPU ที่ router เห็นต่างกัน
        old = self.gen(devices=[], name="old")
        new = self.gen(RTX1000, name="new")
        state = self.state(old)
        changed, lines, _ = gp.compare_running(8199, 4321, state, new, fake_fetch([(ID27, "unloaded", LEGACY_ARGS)]))
        self.assertTrue(changed, lines)
        self.assertTrue(any("GPU เปลี่ยน" in l for l in lines))

    def test_unknown_discovery_leaves_router_alone(self):
        new = self.gen(devices=None, fp=None)
        with open(os.path.join(new, gp.PROFILE_NAME), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["profile"], "unknown")
        changed, lines, _ = gp.compare_running(8199, 1, os.path.join(self.tmp, "none.json"), new,
                                               fake_fetch([(ID27, "loaded", LEGACY_ARGS)]))
        self.assertIsNone(changed)

    def test_failed_preset_is_not_retried_every_launch(self):
        # preset ทำให้ router ล้ม → ถอยไปค่าแบบเดิม รอบหน้า preset ชุดเดิมต้องไม่ทำให้รีสตาร์ตวนซ้ำ
        failed = self.gen(RTX1000, RTX4090, name="failed")
        legacy = self.gen(RTX1000, RTX4090, name="legacy", legacy=True, ctx=32768)
        state = self.state(legacy, mode="legacy", failed=os.path.join(failed, gp.PRESET_NAME))
        with open(state, encoding="utf-8") as f:
            self.assertTrue(json.load(f)["preset_failed_sha1"])
        new = self.gen(RTX1000, RTX4090, name="again")
        fetch = fake_fetch([(ID27, "loaded", LEGACY_ARGS)])
        changed, lines, keep = gp.compare_running(8199, 4321, state, new, fetch)
        self.assertFalse(changed, lines)
        self.assertTrue(keep)
        # ผู้ใช้แก้ค่าแล้ว (preset ใหม่ไม่เหมือนชุดที่ล้ม) → ลองใหม่ได้
        fixed = self.gen(RTX1000, RTX4090, name="fixed", vision=False)
        changed, lines, keep = gp.compare_running(8199, 4321, state, fixed, fetch)
        self.assertTrue(changed)
        self.assertFalse(keep)
        # GPU เปลี่ยนต้องชนะเสมอ
        unplugged = self.gen(RTX1000, name="unplugged", fp="fp-other")
        changed, _, keep = gp.compare_running(8199, 4321, state, unplugged, fetch)
        self.assertTrue(changed)

    def test_record_state_fills_missing_fingerprint(self):
        new = self.gen(RTX1000, fp=None)
        path = os.path.join(self.tmp, "s.json")
        with mock.patch.object(gp, "current_fingerprint", return_value="fp-now"):
            st = gp.record_state(8199, 1, "preset", new, path)
        self.assertEqual(st["fingerprint"], "fp-now")
        self.assertTrue(st["devices_known"])
        with mock.patch.object(gp, "current_fingerprint", return_value=None):
            st = gp.record_state(8199, 1, "legacy", new, path)
        self.assertTrue(st["devices"])                      # nvidia-smi ล้มไม่ใช่เหตุผลให้ลืมรายการ GPU

    def test_router_unreachable_without_state_is_undecided(self):
        new = self.gen(RTX1000)

        def boom(url, timeout=None, body=None):
            raise OSError("refused")
        changed, _, _ = gp.compare_running(8199, 1, os.path.join(self.tmp, "none.json"), new, boom)
        self.assertIsNone(changed)

    def test_effective_args_aliases(self):
        eff = gp.effective_from_args(["-c", "4096", "-t", "3", "-dev", "CUDA1", "-mm", "x.gguf"])
        self.assertEqual(eff["ctx-size"], "4096")
        self.assertEqual(eff["threads"], "3")
        self.assertEqual(eff["device"], "CUDA1")
        self.assertEqual(eff["mmproj"], "x.gguf")
        self.assertIsNone(eff["cache-type-k"])


class BusyTests(unittest.TestCase):
    def test_busy_detection(self):
        f = fake_fetch([(ID27, "loaded", []), (ID4B, "unloaded", [])],
                       {ID27: [{"id": 0, "is_processing": True}, {"id": 1, "is_processing": False}]})
        busy, notes = gp.router_busy(8199, f)
        self.assertTrue(busy)
        f2 = fake_fetch([(ID27, "loaded", [])], {ID27: [{"id": 0, "is_processing": False}]})
        self.assertFalse(gp.router_busy(8199, f2)[0])
        f3 = fake_fetch([(ID27, "loading", [])])
        self.assertTrue(gp.router_busy(8199, f3)[0])

    def test_unreadable_slots_counts_as_busy(self):
        def fetch(url, timeout=None, body=None):
            if url.endswith("/models"):
                return {"data": [{"id": ID27, "status": {"value": "loaded", "args": []}}]}
            raise OSError("timed out")
        busy, notes = gp.router_busy(8199, fetch)
        self.assertTrue(busy)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class WaitIdleTests(unittest.TestCase):
    """--wait-idle: ต้องว่างต่อเนื่อง ไม่ใช่แค่ครั้งเดียว และอ่านไม่ได้ = ยังไม่ว่าง"""

    def run_wait(self, script, timeout=60):
        clock = FakeClock()
        calls = {"n": 0}

        def fetch(url, timeout=None, body=None):
            if url.endswith("/models"):
                calls["n"] += 1          # หนึ่งรอบที่ถาม = /models หนึ่งครั้ง ตามด้วย /slots ของโมเดลที่โหลดอยู่
            step = script[min(calls["n"] - 1, len(script) - 1)]
            if url.endswith("/models"):
                if isinstance(step, Exception):
                    raise step
                return {"data": [{"id": ID27, "status": {"value": "loaded", "args": []}}]}
            busy, task = step
            return [{"id": 0, "is_processing": busy, "id_task": task}]
        out = []
        rc = gp.wait_idle(8199, timeout, out.append, fetch=fetch, sleep=clock.sleep, clock=clock)
        return rc, clock.t, out

    def test_busy_then_quiet(self):
        rc, t, out = self.run_wait([(True, 1), (True, 1), (False, 1)])
        self.assertEqual(rc, gp.EXIT_OK)
        self.assertGreaterEqual(t, 2 * gp.IDLE_POLL_S + gp.IDLE_QUIET_S)
        self.assertTrue(any("รอให้แชต" in l for l in out))

    def test_new_task_during_quiet_window_resets(self):
        # เทิร์นใหม่เริ่มแล้วจบระหว่างสองรอบที่ถาม (หลังเครื่องมือ MCP ทำงาน) — id_task เปลี่ยน ต้องนับใหม่
        rc, t, _ = self.run_wait([(False, 1), (False, 1), (False, 2), (False, 2)])
        self.assertEqual(rc, gp.EXIT_OK)
        self.assertGreaterEqual(t, 2 * gp.IDLE_POLL_S + gp.IDLE_QUIET_S)

    def test_unreadable_status_is_busy_until_timeout(self):
        rc, t, out = self.run_wait([OSError("timed out")], timeout=30)
        self.assertEqual(rc, gp.EXIT_BUSY)
        self.assertGreaterEqual(t, 30)

    def test_router_gone_is_idle(self):
        refused = urllib.error.URLError(ConnectionRefusedError(10061, "refused"))
        rc, t, out = self.run_wait([refused])
        self.assertEqual(rc, gp.EXIT_OK)
        self.assertEqual(t, 0)

    def test_always_busy_times_out(self):
        rc, t, _ = self.run_wait([(True, 1)], timeout=12)
        self.assertEqual(rc, gp.EXIT_BUSY)


# ================================================================ กรณีเพิ่มจากการตรวจ (verifier)
class PolicyEdgeTests(unittest.TestCase):
    def test_ctx_larger_than_one_gpu_uses_every_gpu(self):
        # 27B + KV 262144 ≈ 25 GB > งบ 4090 23 GB → การ์ดเดียวไม่พอ ต้องแบ่งลง 4090 + RTX 1000 (ไม่ล้นไป CPU)
        res = run_plan(gpus(RTX1000, RTX4090), ctx=262144)
        self.assertEqual(res["profile"], "egpu-multi")
        self.assertEqual(res["sections"][ID27], {"device": "CUDA1,CUDA0"})
        self.assertFalse(res["placement"][ID27]["vision"])
        self.assertTrue(res["placement"][ID27]["fits_fully"])
        res3 = run_plan(gpus(RTX1000, RTX4060TI, RTX4090), ctx=262144)
        self.assertEqual(res3["sections"][ID27]["device"], "CUDA2,CUDA1,CUDA0")
        self.assertNotIn("mmproj", res3["sections"][ID27])
        alone = run_plan([dev(0, RTX4090)], ctx=262144)
        self.assertEqual(alone["profile"], "egpu-single")
        self.assertEqual(device_keys(alone), {})
        self.assertNotIn("mmproj", alone["sections"][ID27])

    def test_ctx_override_drops_auto_vision_when_mmproj_no_longer_fits(self):
        # 180000: ไม่มีภาพพอดี 4090 (~22.2 GB) แต่รวม mmproj แล้วเกิน → ยังได้ 4090 ทั้งใบ แต่ปิดดูรูป
        res = run_plan(gpus(RTX1000, RTX4090), ctx=180000)
        self.assertEqual(res["sections"][ID27], {"device": "CUDA1"})
        self.assertFalse(res["placement"][ID27]["vision"])
        self.assertTrue(res["placement"][ID27]["fits_fully"])
        # 131072 ยังพอรวม mmproj
        res2 = run_plan(gpus(RTX1000, RTX4090), ctx=131072)
        self.assertEqual(res2["sections"][ID27], {"device": "CUDA1", "mmproj": MMPROJ})
        # สั่ง -Vision เอง: การ์ดเดียวต้องจุรวม mmproj ด้วย ไม่งั้นไปทางทุก GPU
        res3 = run_plan(gpus(RTX1000, RTX4090), ctx=180000, vision=True)
        self.assertEqual(res3["sections"][ID27], {"device": "CUDA1,CUDA0", "mmproj": MMPROJ})

    def test_tiny_remaining_gpu_is_not_a_home_for_other_models(self):
        tiny = ("NVIDIA Quadro P400", 2048)
        for devs in (gpus(RTX4090, tiny), gpus(tiny, RTX4090)):
            res = run_plan(devs)
            fit = next(d["id"] for d in devs if d["short"] == "RTX 4090")
            self.assertEqual(res["sections"][ID27]["device"], fit)
            for m in (IDCODER, IDOSS, ID4B):
                self.assertNotIn("device", res["sections"][m])         # ใช้ร่วมกัน -fit จัดเอง
                self.assertTrue(res["placement"][m]["shared_with_primary"])
            self.assertTrue(res["others_shared"])
        # การ์ด 4 GB (งบ 3 GB) ยังนับว่าใช้ได้
        res = run_plan(gpus(RTX4090, ("NVIDIA T1000", 4096)))
        self.assertEqual(res["sections"][ID4B]["device"], "CUDA1")

    def test_free_memory_warning_when_egpu_drives_display(self):
        devs = gpus(RTX1000, RTX4090)
        devs[1]["free_mib"] = 17500
        res = run_plan(devs)
        self.assertEqual(res["sections"][ID27]["device"], "CUDA1")        # แผนยังใช้หน่วยความจำทั้งหมด
        self.assertEqual(len(res["notices"]), 1)
        th, en = gp.build_summary(devs, "simulate", res)
        self.assertIn("ว่างจริงแค่", th)
        self.assertIn("only", en)
        # มี llama-server ถือ VRAM อยู่ (ค่า free ไม่น่าเชื่อ) → ไม่เตือน
        res2 = gp.plan(devs, real_models(), gp.Options(), free_reliable=False)
        self.assertEqual(res2["notices"], [])
        self.assertEqual(run_plan(gpus(RTX1000, RTX4090))["notices"], [])

    def test_identical_gpus_summary_names_the_other_card(self):
        devs = gpus(RTX4090, RTX4090)
        res = run_plan(devs)
        th, en = gp.build_summary(devs, "simulate", res)
        plan_line = next(l for l in th.splitlines() if l.startswith("แผน:"))
        self.assertNotIn("GPU เดียวกัน", plan_line)
        self.assertFalse(res["placement"][ID4B]["shared_with_primary"])

    def test_unreadable_model_speed_is_unknown(self):
        broken = gp.ModelInfo(id="broken-download", path="x", size_bytes=1500000000, error="ส่วนหัว GGUF ไม่ครบ")
        models = real_models() + [broken]
        devs = gpus(RTX1000, RTX4090)
        res = gp.plan(devs, models, gp.Options())
        self.assertIsNone(res["placement"]["broken-download"]["est_gen_tps"])
        th, en = gp.build_summary(devs, "simulate", res)
        line = next(l for l in th.splitlines() if "broken-download" in l)
        self.assertIn("ราว ? tok/s", line)

    def test_primary_prefers_launcher_default_among_several(self):
        extra = gp.ModelInfo(id="Qwen3.8-27B-Q8_0", path="x", size_bytes=28600000000, arch="qwen35",
                             kv_elems_full=32768)
        models = sorted(real_models() + [extra], key=lambda m: m.id.lower())
        w = []
        self.assertEqual(gp.pick_primary(models, None, w).id, ID27)
        self.assertTrue(any("Qwen3.8-27B-Q8_0" in x and "-Primary" in x for x in w), w)
        res = gp.plan(gpus(RTX1000, RTX4090), models, gp.Options())
        self.assertEqual(res["sections"][ID27]["device"], "CUDA1")       # 27B ตัวที่ใช้อยู่ไม่เสียการ์ดใหญ่
        # ไม่มีตัวปริยาย: เอาตัวแรกแต่ต้องเตือนให้เห็น
        a = gp.ModelInfo(id="Qwen3.8-27B-IQ4_XS", path="x", size_bytes=1)
        b = gp.ModelInfo(id="Qwen3.8-27B-Q8_0", path="x", size_bytes=1)
        w = []
        self.assertEqual(gp.pick_primary([a, b], None, w).id, "Qwen3.8-27B-IQ4_XS")
        self.assertTrue(w)
        w = []
        self.assertEqual(gp.pick_primary([a, b], "Qwen3.8-27B-Q8_0", w).id, "Qwen3.8-27B-Q8_0")
        self.assertEqual(w, [])

    def test_legacy_profile_describes_old_command_line(self):
        devs = gpus(RTX1000, RTX4090)
        res = run_plan(devs, legacy=True, ctx=32768)
        self.assertEqual(res["profile"], "legacy")
        self.assertEqual(device_keys(res), {})
        for m in (ID27, IDCODER, ID4B):
            self.assertEqual(res["placement"][m]["devices"], ["CUDA0", "CUDA1"])     # ลำดับ CUDA ปกติ
        self.assertFalse(res["placement"][ID27]["vision"])
        self.assertTrue(run_plan(devs, legacy=True, vision=True)["placement"][ID27]["vision"])

    def test_published_dir(self):
        self.assertEqual(gp.published_dir(8099), gp.DEFAULT_OUT_DIR)
        self.assertEqual(gp.published_dir(8199), os.path.join(gp.LOG_DIR, "gpu-8199"))


class UserOverrideTests(TmpDir):
    def test_invalid_device_is_dropped_and_generated_value_kept(self):
        res = run_plan(gpus(RTX1000, RTX4090))
        user = "[%s]\ndevice = CUDA3\n[%s]\ndevice = none\n[%s]\ndevice = CUDA1,CUDA0\n" % (ID4B, IDOSS, IDCODER)
        merged, warns = gp.merge_user_overrides(res["sections"], user, [m.id for m in real_models()],
                                                ["CUDA0", "CUDA1"])
        self.assertEqual(merged[ID4B]["device"], "CUDA0")            # ค่าที่จัดให้ ไม่ใช่ CUDA3
        self.assertTrue(any("CUDA3" in w for w in warns), warns)
        self.assertEqual(merged[IDOSS]["device"], "none")
        self.assertEqual(merged[IDCODER]["device"], "CUDA1,CUDA0")
        # internal อย่างเดียว: CUDA1 ไม่มี → ไม่เขียนลง preset (ไม่งั้นโมเดลโหลดไม่ขึ้น HTTP 500)
        res1 = run_plan(gpus(RTX1000))
        merged1, warns1 = gp.merge_user_overrides(res1["sections"], "[%s]\ndevice = CUDA1\n" % ID4B,
                                                  [m.id for m in real_models()], ["CUDA0"])
        self.assertNotIn("device", merged1[ID4B])
        self.assertTrue(warns1)
        # ตรวจ GPU ไม่ได้ → เชื่อผู้ใช้
        merged2, warns2 = gp.merge_user_overrides(res1["sections"], "[%s]\ndevice = CUDA1\n" % ID4B,
                                                  [m.id for m in real_models()], None)
        self.assertEqual(merged2[ID4B]["device"], "CUDA1")

    @unittest.skipUnless(os.path.isfile(os.path.join(REAL_MODELS, ID27 + ".gguf")), "ไม่มีโฟลเดอร์โมเดลจริง")
    def test_json_placement_follows_user_ini(self):
        ui = os.path.join(self.tmp, "user.ini")
        with open(ui, "w", encoding="utf-8") as f:
            f.write("[%s]\ndevice = CUDA1,CUDA0\n[%s]\ndevice = CUDA7\n[%s]\nctx-size = 8192\n"
                    % (IDCODER, ID4B, IDOSS))
        devs = gpus(RTX1000, RTX4090)
        prof = gp.generate(REAL_MODELS, os.path.join(self.tmp, "out"), gp.Options(), user_ini=ui, choice=None,
                           discovery=(devs, "simulate", "fp"))
        pl = prof["placement"]
        self.assertEqual(pl[IDCODER]["devices"], ["CUDA1", "CUDA0"])
        self.assertTrue(pl[IDCODER]["user_override"])
        self.assertTrue(pl[IDCODER]["shared_with_primary"])
        self.assertEqual(pl[ID4B]["devices"], ["CUDA0"])                # CUDA7 ถูกทิ้ง ใช้ค่าที่จัดให้
        self.assertFalse(pl[ID4B]["user_override"])
        self.assertEqual(pl[IDOSS]["ctx"], 8192)
        self.assertTrue(any("CUDA7" in w for w in prof["warnings"]))
        with open(os.path.join(self.tmp, "out", gp.PRESET_NAME), encoding="utf-8") as f:
            sec, _ = gp.parse_ini(f.read())
        self.assertEqual(sec[ID4B]["device"], "CUDA0")
        self.assertIn("user.ini", prof["summary_th"])

    @unittest.skipUnless(os.path.isfile(os.path.join(REAL_MODELS, ID27 + ".gguf")), "ไม่มีโฟลเดอร์โมเดลจริง")
    def test_persistent_vision_via_user_ini(self):
        ui = os.path.join(self.tmp, "user.ini")
        with open(ui, "w", encoding="utf-8") as f:
            f.write("[%s]\nmmproj = %s\n" % (ID27, MMPROJ))
        prof = gp.generate(REAL_MODELS, os.path.join(self.tmp, "out"), gp.Options(), user_ini=ui, choice=None,
                           discovery=(gpus(RTX1000), "simulate", "fp"))
        self.assertTrue(prof["placement"][ID27]["vision"])
        self.assertTrue(prof["placement"][ID27]["user_override"])


@unittest.skipUnless(os.path.isfile(os.path.join(REAL_MODELS, ID27 + ".gguf")), "ไม่มีโฟลเดอร์โมเดลจริง")
class CliGuardTests(TmpDir):
    def test_simulate_refuses_live_out_dir(self):
        live = os.path.join(self.tmp, "live")
        os.makedirs(live)
        sim = os.path.join(self.tmp, "sim.json")
        with open(sim, "w", encoding="utf-8") as f:
            json.dump([{"name": RTX4090[0], "total_mib": RTX4090[1]}], f)
        # จำลองว่า DEFAULT_OUT_DIR คือโฟลเดอร์นี้ — เทสต์ไม่แตะ C:\LLM จริง
        with mock.patch.object(gp, "DEFAULT_OUT_DIR", live), redirect_stdout(io.StringIO()):
            rc = gp.main(["--write", "--models-dir", REAL_MODELS, "--simulate", sim, "--out-dir", live,
                          "--user-ini", os.path.join(self.tmp, "none.ini"), "--choice", "none"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(os.listdir(live), [])

    def test_legacy_cli(self):
        sim = os.path.join(self.tmp, "sim.json")
        with open(sim, "w", encoding="utf-8") as f:
            json.dump([{"name": RTX1000[0], "total_mib": RTX1000[1]}, {"name": RTX4090[0], "total_mib": RTX4090[1]}], f)
        out = os.path.join(self.tmp, "out")
        with redirect_stdout(io.StringIO()):
            rc = gp.main(["--write", "--legacy", "--ctx", "32768", "--models-dir", REAL_MODELS, "--simulate", sim,
                          "--out-dir", out, "--user-ini", os.path.join(self.tmp, "none.ini"), "--choice", "none"])
        self.assertEqual(rc, 0)
        with open(os.path.join(out, gp.PROFILE_NAME), encoding="utf-8") as f:
            prof = json.load(f)
        self.assertEqual(prof["profile"], "legacy")
        self.assertEqual(prof["placement"][ID27]["devices"], ["CUDA0", "CUDA1"])


if __name__ == "__main__":
    unittest.main()
