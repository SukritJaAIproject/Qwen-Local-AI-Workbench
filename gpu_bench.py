# -*- coding: utf-8 -*-
"""
gpu_bench.py — วัดความเร็วจริงของแต่ละโมเดลผ่าน llama-server router (หลังเสียบ/ถอด eGPU)

ทำไมต้องมี
  gpu_profile.py บอกความเร็วแค่ "ประมาณจากแบนด์วิดท์" ตัวเลขจริงขึ้นกับหลายอย่างที่คำนวณไม่ได้
  (ลิงก์ Thunderbolt, การ throttle ของเครื่อง, kernel ของแต่ละสถาปัตยกรรม) หลังต่อ eGPU แล้ว
  เปิดตัวเปิดใหม่ครั้งหนึ่ง แล้วรันไฟล์นี้เพื่อดูของจริง

ใช้
  C:\\Python313\\python.exe C:\\LLM\\gpu_bench.py                       ทุกโมเดลบน router พอร์ต 8099
  C:\\Python313\\python.exe C:\\LLM\\gpu_bench.py --models Qwen3-4B-Instruct-2507-Q4_K_M --tokens 256
  ผลเก็บที่ C:\\LLM\\logs\\gpu-bench-<เวลา>.json

แต่ละโมเดล: อุ่นเครื่อง 1 ครั้ง (รวมเวลาโหลดโมเดล) + วัดจริง 1 ครั้ง ที่ temperature 0 ปิดโหมดคิด
ไม่ยอมวัดขณะ router กำลังตอบแชตอยู่ (จะทำให้ทั้งแชตและตัวเลขเพี้ยน) เว้นแต่ใส่ --force
ข้อควรรู้: router โหลดได้พร้อมกัน 2 โมเดล การวัดหลายตัวจะปลดโมเดลที่โหลดค้างไว้ออก
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu_profile as gp  # noqa: E402

DEFAULT_PORT = 8099
DEFAULT_TOKENS = 128
GPTOSS_MIN_TOKENS = 512        # gpt-oss คิดก่อนตอบเสมอ (ปิดไม่ได้ ทำได้แค่ reasoning low)
WARMUP_TOKENS = 8
REQUEST_TIMEOUT_S = 1800       # 27B บน CPU: โหลด ~47 วินาที + 128 โทเคนที่ ~1.3 tok/s ≈ 100 วินาที
LOG_DIR = gp.LOG_DIR
EXIT_OK, EXIT_SOME_FAILED, EXIT_NO_ROUTER, EXIT_BUSY = 0, 1, 2, 3

# prompt ยาวพอให้วัดความเร็วอ่าน prompt ได้ (~350 โทเคน) และเนื้อหาชวนให้เขียนยาว
PROMPT = (
    "You are helping a maintenance team that operates a fleet of electric-vehicle DC fast chargers. "
    "Each charger reports its status over OCPP 1.6: heartbeat messages every few minutes, meter values "
    "during a session, status notifications when a connector changes state, and fault codes such as "
    "GroundFailure, HighTemperature, OverCurrentFailure, PowerMeterFailure, ReaderFailure and "
    "InternalError. The team keeps a log of every visit: the date, the charger id, the symptom reported "
    "by drivers, the fault codes seen in the preceding week, the parts that were inspected or replaced "
    "(contactors, power modules, cooling fans, air filters, cable assemblies, RFID readers, meters), "
    "and whether the charger returned to service. Over two years they noticed three patterns. First, "
    "cooling fans clogged by dust lead to HighTemperature faults that appear in the afternoon and "
    "disappear at night, and power output is derated long before a hard fault is raised. Second, worn "
    "contactors cause sessions that stop within the first minute with OverCurrentFailure, often only "
    "on one connector. Third, unstable cellular links show up as long gaps between heartbeats followed "
    "by bursts of queued messages, which are sometimes mistaken for hardware faults. "
    "Write a detailed maintenance guide for new technicians based on this information. Explain each "
    "pattern, how to recognise it from the logs, what to check on site, which parts to bring, and how "
    "to confirm the fix. Use numbered sections and be thorough."
)
WARMUP_PROMPT = "Reply with the single word: ready."


def post_chat(port, body, timeout=REQUEST_TIMEOUT_S):
    t0 = time.perf_counter()
    doc = gp.http_json("http://127.0.0.1:%d/v1/chat/completions" % port, timeout=timeout, body=body)
    return doc, time.perf_counter() - t0


def request_body(model, prompt, max_tokens, measured):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
        # Qwen3.x มีโหมดคิด ปิดไว้ให้เทียบกันได้ (โมเดลที่ไม่มีโหมดนี้จะไม่สนใจ key นี้)
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if "gpt-oss" in model.lower():
        body["reasoning_effort"] = "low"
        body["chat_template_kwargs"]["reasoning_effort"] = "low"
        body["max_tokens"] = max(max_tokens, GPTOSS_MIN_TOKENS)
    if measured:
        # วัดความเร็วอ่าน prompt จริง ไม่ใช้ cache จากรอบอุ่นเครื่อง และสร้างครบจำนวนโทเคนทุกโมเดล
        body["cache_prompt"] = False
        body["ignore_eos"] = True
    return body


def _run_stats(doc, wall):
    t = doc.get("timings") or {}
    usage = doc.get("usage") or {}
    out = {
        "wall_s": round(wall, 2),
        "prompt_n": t.get("prompt_n", usage.get("prompt_tokens")),
        "prompt_ms": t.get("prompt_ms"),
        "prompt_tps": _r(t.get("prompt_per_second")),
        "gen_n": t.get("predicted_n", usage.get("completion_tokens")),
        "gen_ms": t.get("predicted_ms"),
        "gen_tps": _r(t.get("predicted_per_second")),
    }
    if out["gen_tps"] is None and out.get("gen_n") and wall:
        out["gen_tps"] = _r(out["gen_n"] / wall)
    return out


def _median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else round((vals[mid - 1] + vals[mid]) / 2.0, 2)


def bench_model(port, model, tokens, log=print, repeat=1):
    """อุ่นเครื่อง 1 ครั้ง + วัด repeat ครั้ง — ตัวเลขหลัก (gen_tps ฯลฯ) = ค่ากลาง (median) ของทุกรอบ
    batch 2b: repeat > 1 เพราะความเร็วของเครื่องนี้แกว่ง ±15% ระหว่างรอบ (throttle) — รอบเดียวสรุปผิดทางได้"""
    res = {"model": model, "error": None}
    runs = []
    try:
        log("  %s: อุ่นเครื่อง (ถ้ายังไม่ได้โหลด จะรวมเวลาโหลดโมเดลด้วย)..." % model)
        _, warm_s = post_chat(port, request_body(model, WARMUP_PROMPT, WARMUP_TOKENS, measured=False))
        res["warmup_wall_s"] = round(warm_s, 2)
        for i in range(max(1, int(repeat))):
            log("  %s: วัด %d โทเคน (รอบ %d/%d)..." % (model, tokens, i + 1, max(1, int(repeat))))
            doc, wall = post_chat(port, request_body(model, PROMPT, tokens, measured=True))
            runs.append(_run_stats(doc, wall))
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        res["error"] = "HTTP %s %s" % (e.code, detail)
        if runs:
            res["runs"] = runs
        return res
    except (OSError, ValueError, urllib.error.URLError) as e:
        res["error"] = "%s: %s" % (type(e).__name__, e)
        if runs:
            res["runs"] = runs
        return res
    if len(runs) == 1:
        res.update(runs[0])
    else:
        res["runs"] = runs
        for k in ("wall_s", "prompt_n", "prompt_ms", "prompt_tps", "gen_n", "gen_ms", "gen_tps"):
            res[k] = _median([r.get(k) for r in runs])
    res["max_tokens"] = request_body(model, "", tokens, True)["max_tokens"]
    return res


def _r(v):
    return None if v is None else round(float(v), 2)


def load_profile(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def device_names(profile, model):
    if not profile:
        return "?"
    p = (profile.get("placement") or {}).get(model)
    if not p:
        return "?"
    by = {d.get("id"): d.get("short") or d.get("id") for d in profile.get("devices") or []}
    names = [by.get(i, i) for i in p.get("devices") or []]
    s = " + ".join(names) if names else "CPU"
    if names and not p.get("fits_fully"):
        s += " + CPU"
    return s


def print_table(rows, out=print):
    head = ("model", "devices", "est", "prompt tok/s", "gen tok/s", "gen n", "wall s", "load+warm s")
    data = []
    for r in rows:
        if r.get("error"):
            data.append((r["model"], r.get("devices", "?"), r.get("est") or "-", "-", "-", "-", "-",
                         "ERROR: " + r["error"][:60]))
            continue
        data.append((r["model"], r.get("devices", "?"), r.get("est") or "-", _fmt(r.get("prompt_tps")),
                     _fmt(r.get("gen_tps")), str(r.get("gen_n") or "-"), _fmt(r.get("wall_s")),
                     _fmt(r.get("warmup_wall_s"))))
    widths = [max(len(str(x)) for x in col) for col in zip(head, *data)]
    line = "  ".join("%-*s" % (w, h) for w, h in zip(widths, head))
    out(line)
    out("-" * len(line))
    for d in data:
        out("  ".join("%-*s" % (w, x) for w, x in zip(widths, d)))


def _fmt(v):
    if v is None:
        return "-"
    return "%.1f" % v if isinstance(v, (int, float)) else str(v)


# ================================================================ batch 2b (สัญญา C3): เทียบค่าตั้งของโมเดลหลัก
# ทำไม: 27B บนการ์ด 6 GB แบ่งชั้นกับ CPU (-fit) — อะไรที่กิน VRAM เพิ่ม (KV ของ ctx 64K ~1.06 GiB, mmproj F16 0.86 GiB)
# ดันชั้นของโมเดลไป CPU แล้วสร้างข้อความช้าลง ต้องวัดจริงก่อนเปิดดูรูป/ขยาย context ให้ผู้ใช้ทุกคน
# วิธี: เปิด router ตัวทดสอบ (พอร์ต 8199 ปกติ) ทีละค่าตั้ง ด้วย preset = ของ router ตัวจริง + คีย์ของค่าตั้งนั้น
#       วัดแบบเดียวกับข้างบน (ปิดโหมดคิด, temperature 0, ignore_eos) + ถามรูปเล็กๆ ถ้าค่าตั้งนั้นเปิด mmproj
#       เลือกค่าตั้งที่ "ทำได้มากที่สุด" (ดูรูป > context ใหญ่) ที่ความเร็วสร้างข้อความลดไม่ถึง 10% จากค่าเดิม
# กติกาของเครื่องนี้ (หน่วยความจำใช้ร่วมกับงานอื่น): ก่อนโหลดโมเดลแต่ละรอบ commit ที่เหลือต้อง >= --min-free-gb (25)
#   ไม่พอ = ข้ามค่าตั้งนั้นพร้อมเหตุผล ไม่ฝืนโหลด (27B ตัวที่สองกิน ~13-16 GB แล้วงานอื่นล้มด้วย MemoryError ได้)
# router ตัวทดสอบเปิดด้วย env ที่ตัดตัวแปรลับออก + ค่าความปลอดภัยเดียวกับตัวเปิด (127.0.0.1, --api-key-file เป็น path,
# CORS เฉพาะตัวเอง, ไม่มีหน้าเว็บ) และถูกปิดทั้งต้น (router + โมเดลลูก) หลังวัดทุกค่าตั้ง
MMPROJ_27B = r"C:\LLM\models\mmproj-Qwen3.8-27B-F16.gguf"
PRIMARY_27B = "Qwen3.8-27B-UD-Q4_K_M"
VARIANT_SETS = {
    # (ชื่อ, คีย์ที่เพิ่มใน section ของโมเดล) — "base" = ค่าที่ router ตัวจริงใช้อยู่ตอนนี้
    "vision27b": [
        ("base", {}),
        ("a_ctx64k", {"ctx-size": "65536"}),
        ("b_mmproj_gpu", {"mmproj": MMPROJ_27B}),
        ("c_mmproj_cpu", {"mmproj": MMPROJ_27B, "mmproj-device": "none"}),
        ("d_mmproj_img768", {"mmproj": MMPROJ_27B, "image-max-tokens": "768"}),
        ("e_ctx64k_mmproj_cpu", {"ctx-size": "65536", "mmproj": MMPROJ_27B, "mmproj-device": "none"}),
    ],
}
DEFAULT_TEST_PORT = 8199
MIN_FREE_GB = 25.0
MAX_DROP = 0.10
ROUTER_START_S = 30
IMAGE_PROMPT = "What is in this image? Answer in one short sentence."
_SECRET_ENV = re.compile(
    r"^(CLAUDE|ANTHROPIC|OTEL_|SENTRY|BAGGAGE|AI_AGENT)|TOKEN|SECRET|PASSW(OR)?D|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|"
    r"CREDENTIAL|OAUTH|_KEY$", re.I)


def available_commit_gb():
    """commit ที่เหลือ (GiB) = ullAvailPageFile ของ GlobalMemoryStatusEx — หน่วยเดียวกับกติกาของเครื่องนี้
    (Win32_OperatingSystem.FreeVirtualMemory เป็น KB แล้วหาร 1MB) None = อ่านไม่ได้ (ไม่ใช่ Windows) = ถือว่าไม่พอ"""
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        ms = MS()
        ms.dwLength = ctypes.sizeof(MS)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            return None
        return round(ms.ullAvailPageFile / float(1024 ** 3), 1)
    except (ImportError, AttributeError, OSError):
        return None


def clean_env():
    """env สำหรับ router ตัวทดสอบ — ตัดตัวแปรลับ (เชลล์ของเครื่องมือ/เอเจนต์) ออก คง path ไฟล์โทเคนทดสอบไว้"""
    env = {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k) or k == gp.LOCAL_TOKEN_ENV}
    env["CUDA_DEVICE_ORDER"] = gp.CUDA_DEVICE_ORDER
    return env


def token_file_path():
    return (os.environ.get(gp.LOCAL_TOKEN_ENV) or "").strip() or gp.LOCAL_TOKEN_FILE


def effective_section(base_text, model, keys):
    """คีย์ของ section โมเดลหลังใส่ค่าตั้ง (ไม่รวม [*]) — ค่า None = ลบคีย์นั้นออก
    fixer 2026-10-06: preset ของ router ตัวจริงตอนนี้มีค่าที่ merge จาก user.ini แล้ว (ctx 64K + mmproj บน CPU) ค่าตั้งที่ต้อง
    "เอา mmproj-device ออก" (mmproj บน GPU) หรือ "กลับไปค่าเดิมก่อน batch 2b" จึงต้องลบคีย์ได้ ไม่ใช่แค่เพิ่ม/ทับ
    (แบบเดียวกับ "key =" ค่าว่างใน models-preset.user.ini)"""
    sections, _w = gp.parse_ini(base_text or "")
    sec = dict(sections.get(model) or {})
    for k, v in (keys or {}).items():
        if v is None:
            sec.pop(k, None)
        else:
            sec[k] = v
    return sec


def variant_preset_text(base_text, model, keys, label):
    """preset ของค่าตั้งหนึ่ง = preset ของ router ตัวจริง + คีย์ของค่าตั้งนี้ใน section ของโมเดล (ไม่มี BOM)
    ค่า None (null ในไฟล์ JSON) = ลบคีย์นั้นออกจาก section ของโมเดล"""
    sections, _w = gp.parse_ini(base_text or "")
    sections.setdefault("*", {})
    sections[model] = effective_section(base_text, model, keys)
    return gp.render_preset(sections, ["gpu_bench.py --variants: %s (test router only)" % label])


def router_argv(port, preset_path, exe=gp.LLAMA_SERVER, models_dir=gp.DEFAULT_MODELS_DIR):
    """คำสั่งเปิด router ตัวทดสอบ — ค่าความปลอดภัยชุดเดียวกับ Get-RouterArgs ของตัวเปิด (ไม่มี --ui-mcp-proxy,
    CORS เฉพาะพอร์ตตัวเอง, API key เป็น path) + --models-max 1 (ไม่ถือสองโมเดลค้างไว้ในเครื่องที่หน่วยความจำตึง)"""
    return [exe, "--models-dir", models_dir, "--models-max", "1", "-fit", "on", "--host", "127.0.0.1",
            "--port", str(port), "-fa", "on", "--jinja", "--no-warmup", "--no-webui",
            "--cors-origins", "http://127.0.0.1:%d" % port, "--no-cors-credentials",
            "--api-key-file", token_file_path(), "--models-preset", preset_path]


def _port_open(port):
    import socket
    s = socket.socket()
    s.settimeout(1.0)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def start_test_router(port, preset_path, log_path):
    import subprocess
    if _port_open(port):
        raise RuntimeError("พอร์ต %d มีโปรแกรมอื่นใช้อยู่ — ไม่เปิดทับ" % port)
    log = open(log_path, "ab")
    proc = subprocess.Popen(router_argv(port, preset_path), env=clean_env(), stdout=log, stderr=subprocess.STDOUT,
                            cwd=os.path.dirname(gp.LLAMA_SERVER), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.time() + ROUTER_START_S
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("router ทดสอบปิดตัวทันที (ดู %s)" % log_path)
        try:
            if gp.http_json("http://127.0.0.1:%d/health" % port, timeout=3).get("status") == "ok":
                return proc
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(0.5)
    stop_test_router(proc)
    raise RuntimeError("router ทดสอบไม่ตอบ /health ภายใน %d วินาที" % ROUTER_START_S)


def stop_test_router(proc):
    """ปิด router ตัวทดสอบทั้งต้น (router + โมเดลลูกที่มันเปิด) — เฉพาะ PID ที่เราเปิดเอง"""
    import subprocess
    if proc is None or proc.poll() is not None:
        return
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=60,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        proc.wait(30)
    except Exception:          # noqa: BLE001
        pass


def tiny_png():
    """PNG 32x32 สีแดงล้วน สร้างเองด้วย zlib (ไม่ต้องมีไฟล์/ไลบรารีภาพ) — พอให้รู้ว่าเส้นทางดูรูปทำงาน"""
    import struct
    import zlib
    w = h = 32
    raw = b"".join(b"\x00" + b"\xdc\x28\x28" * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def image_check(port, model, png_bytes, timeout=REQUEST_TIMEOUT_S):
    """ถามรูปหนึ่งครั้ง — {image_ok, image_wall_s, image_prompt_n, image_prompt_ms, image_reply, image_error}"""
    import base64
    body = {"model": model, "max_tokens": 48, "temperature": 0, "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png_bytes).decode()}},
                {"type": "text", "text": IMAGE_PROMPT}]}]}
    out = {"image_ok": False}
    try:
        doc, wall = post_chat(port, body, timeout=timeout)
    except urllib.error.HTTPError as e:
        out["image_error"] = "HTTP %s %s" % (e.code, e.read()[:200].decode("utf-8", "replace"))
        return out
    except (OSError, ValueError, urllib.error.URLError) as e:
        out["image_error"] = "%s: %s" % (type(e).__name__, e)
        return out
    msg = ((doc.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    t = doc.get("timings") or {}
    out.update(image_ok=bool(msg.strip()), image_wall_s=round(wall, 2), image_prompt_n=t.get("prompt_n"),
               image_prompt_ms=t.get("prompt_ms"), image_reply=msg.strip()[:200])
    return out


def vram_snapshot():
    """[{"used_mib", "free_mib"}] ต่อ GPU (ลำดับ bus) — None ถ้าอ่านไม่ได้
    ทำไมต้องจด: VRAM เป็นของที่ใช้ร่วมกับบริการอื่น (STT faster-whisper ~1.2 GB, งานของ agent/ผู้ใช้) — ค่าตั้งที่ช้าลง
    อาจเป็นเพราะ "มีคนถือ VRAM อยู่ตอนวัด" ไม่ใช่เพราะค่าตั้งนั้นเอง และ VRAM ที่ 27B ใช้หลังโหลด = VRAM ที่เหลือให้ STT"""
    rows = gp._smi_query("memory.used,memory.free")
    if not rows:
        return None
    out = []
    for used, free in rows:
        try:
            out.append({"used_mib": int(float(used)), "free_mib": int(float(free))})
        except ValueError:
            return None
    return out


def recommend(rows, max_drop=MAX_DROP):
    """ค่าตั้งที่ดีที่สุดที่ความเร็วสร้างข้อความลดไม่ถึง max_drop จาก base — "ดีที่สุด" = ดูรูปได้ก่อน แล้ว context ใหญ่
    แล้วเร็วกว่า; ค่าตั้งที่เปิด mmproj ต้องถามรูปผ่านด้วย  คืน {"name", "keys", "gen_tps", "base_gen_tps", "drop", "why"}
    ไม่มี base / ไม่มีตัวไหนผ่าน = name None (คง preset เดิม ไม่เขียน user.ini)"""
    by = {r["variant"]: r for r in rows}
    base = by.get("base") or {}
    btps = base.get("gen_tps")
    if not btps:
        return {"name": None, "keys": {}, "why": "วัดค่าเดิม (base) ไม่สำเร็จ — เทียบไม่ได้"}
    ok = []
    for r in rows:
        if r["variant"] == "base" or r.get("error") or r.get("skipped") or not r.get("gen_tps"):
            continue
        # ปัดก่อนเทียบ: 1 - 0.90/1.00 = 0.0999… ในทศนิยมของเครื่อง จะหลุดผ่านเกณฑ์ "ลดไม่ถึง 10%" ทั้งที่ลดพอดี 10%
        drop = round(1.0 - float(r["gen_tps"]) / float(btps), 4)
        r["drop"] = drop
        # fixer 2026-10-06: ตัดสินจาก section ที่ใช้จริง (preset ตัวจริง + ค่าตั้ง) ไม่ใช่แค่คีย์ที่ค่าตั้งเพิ่ม — ค่าตั้ง {} บน
        # preset ที่มี mmproj อยู่แล้วก็คือ "ดูรูปได้"
        eff = r.get("effective") if isinstance(r.get("effective"), dict) else r["keys"]
        vision = bool(eff.get("mmproj"))
        if drop >= max_drop or (vision and not r.get("image_ok")):
            continue
        ctx = int(eff.get("ctx-size") or 0)
        ok.append(((1 if vision else 0, ctx, float(r["gen_tps"])), r))
    if not ok:
        return {"name": None, "keys": {}, "base_gen_tps": btps,
                "why": "ไม่มีค่าตั้งไหนช้าลงน้อยกว่า %d%% (หรือถามรูปไม่ผ่าน) — คงค่าเดิม" % int(max_drop * 100)}
    ok.sort(key=lambda x: x[0], reverse=True)
    best = ok[0][1]
    return {"name": best["variant"], "keys": dict(best["keys"]), "gen_tps": best["gen_tps"], "base_gen_tps": btps,
            "drop": best["drop"], "why": "ดีที่สุดที่ช้าลงไม่ถึง %d%%" % int(max_drop * 100)}


def user_ini_text(model, keys, note_lines):
    """เนื้อหา models-preset.user.ini (ไม่มี BOM — INI ที่มี BOM ทำให้ llama-server ปิดตัวทันที)"""
    lines = ["; " + l for l in note_lines] + ["", "[%s]" % model]
    lines += ["%s = %s" % (k, v) for k, v in keys.items()]
    return "\n".join(lines) + "\n"


def write_user_ini(path, model, keys, note_lines):
    """เขียนเฉพาะเมื่อยังไม่มีไฟล์ — ไฟล์เดิมเป็นค่าที่ผู้ใช้แก้เอง ห้ามเขียนทับ (คืน False แล้วให้ผู้ใช้เติมเอง)"""
    if os.path.exists(path):
        return False
    gp._write_atomic(path, user_ini_text(model, keys, note_lines))
    return True


def run_variants(args, log=print):
    """--variants: วัดทีละค่าตั้งบน router ตัวทดสอบ — คืน exit code"""
    variants = VARIANT_SETS.get(args.variants)
    if variants is None:
        try:
            with open(args.variants, "r", encoding="utf-8") as f:
                variants = [(n, dict(k)) for n, k in json.load(f)]
        except (OSError, ValueError, TypeError) as e:
            log("อ่านชุดค่าตั้ง %s ไม่ได้: %s" % (args.variants, e))
            return EXIT_SOME_FAILED
    model = (args.models or [PRIMARY_27B])[0]
    only = set(args.only or [])
    if only:
        variants = [v for v in variants if v[0] in only or v[0] == "base"]
    base_preset = os.path.join(gp.published_dir(gp.DEFAULT_PORT), gp.PRESET_NAME)
    try:
        with open(base_preset, "r", encoding="utf-8-sig") as f:
            base_text = f.read()
    except OSError:
        base_text = "[*]\nctx-size = 32768\ncache-type-k = q8_0\ncache-type-v = q8_0\nthreads = 6\n"
    os.makedirs(args.out_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    work = os.path.join(args.out_dir, "gpu-variants-%s" % stamp)
    os.makedirs(work, exist_ok=True)
    png = tiny_png()
    if args.image:
        with open(args.image, "rb") as f:
            png = f.read()
    rounds = max(1, int(getattr(args, "rounds", 1) or 1))
    if rounds == 1:
        rows = [_measure_variant(args, model, name, keys, base_text, work, png, log) for name, keys in variants]
    else:
        # รอบ 2026-10-06: วัดรอบเดียวต่อค่าตั้งแกว่งเกินเกณฑ์ 10% (mmproj บน CPU ซึ่งไม่แตะ VRAM เลยยัง "ช้าลง" 9% เพราะ
        # เครื่องร้อน/งานอื่นแย่ง CPU ระหว่างวัด) — วัดสลับกันแบบ ABBA (รอบคู่เรียงกลับ) หักล้างการไหลของความเร็วตามเวลา
        # แล้วรวมทุกตัวอย่างของค่าตั้งเดียวกันเป็นค่ากลาง
        parts = {name: [] for name, _k in variants}
        for rnd in range(rounds):
            seq = variants if rnd % 2 == 0 else list(reversed(variants))
            for name, keys in seq:
                parts[name].append(_measure_variant(args, model, name, keys, base_text, work, png, log,
                                                    suffix="-r%d" % (rnd + 1)))
        rows = [merge_rounds(name, keys, model, parts[name]) for name, keys in variants]
    rec = recommend(rows, args.max_drop)
    doc = {"version": 1, "started_at": stamp, "test_port": args.test_port, "tokens": args.tokens,
           "repeat": args.repeat, "rounds": rounds, "base_preset": base_preset, "results": rows,
           "recommendation": rec}
    out_path = work + ".json"
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    log("ผลเทียบ: %s" % out_path)
    log("แนะนำ: %s — %s" % (rec.get("name") or "คงค่าเดิม", rec.get("why")))
    if args.write_user_ini and rec.get("name"):
        note = ["models-preset.user.ini — ค่าที่วัดแล้วด้วย gpu_bench.py --variants (%s)" % stamp,
                "base %s tok/s -> %s %s tok/s (ลด %.0f%%); ผลเต็ม: %s" % (
                    rec.get("base_gen_tps"), rec["name"], rec.get("gen_tps"), 100 * (rec.get("drop") or 0), out_path),
                "ไฟล์นี้ merge ทับ models-preset.ini ทุกครั้งที่เปิดตัวเปิด — ห้ามมี BOM"]
        if write_user_ini(gp.USER_INI, model, rec["keys"], note):
            log("เขียน %s แล้ว — มีผลเมื่อเปิดตัวเปิดครั้งถัดไป (router รีสตาร์ตเมื่อแชตว่าง)" % gp.USER_INI)
        else:
            log("มี %s อยู่แล้ว — ไม่เขียนทับ ให้เติมเองใน section [%s]: %s" % (
                gp.USER_INI, model, ", ".join("%s = %s" % kv for kv in rec["keys"].items())))
    return EXIT_SOME_FAILED if any(r.get("error") or r.get("round_errors") for r in rows) else EXIT_OK


def _measure_variant(args, model, name, keys, base_text, work, png, log, suffix=""):
    """วัดค่าตั้งหนึ่งครั้ง (เปิด router ทดสอบ -> วัด -> ถามรูปถ้ามี mmproj -> ปิด) คืนแถวผล"""
    row = {"variant": name, "keys": keys, "model": model}
    eff = effective_section(base_text, model, keys)
    row["effective"] = eff
    free = available_commit_gb()
    row["free_commit_gb"] = free
    if free is None or free < args.min_free_gb:
        row["skipped"] = "หน่วยความจำ commit เหลือ %s GB < %.0f GB — ไม่โหลดโมเดลรอบนี้" % (free, args.min_free_gb)
        log("  %s: ข้าม — %s" % (name, row["skipped"]))
        return row
    waited = 0
    while True:
        try:
            busy, notes = gp.router_busy(gp.DEFAULT_PORT)
        except (OSError, ValueError, urllib.error.URLError):
            busy, notes = False, []
        if not busy or waited >= args.wait_idle_s:
            break
        time.sleep(10)
        waited += 10
    if busy:
        row["skipped"] = "router ตัวจริงมีแชตกำลังตอบ (%s) — ไม่วัดแข่ง" % "; ".join(notes)
        log("  %s: ข้าม — %s" % (name, row["skipped"]))
        return row
    # fixer 2026-10-06: โมเดลที่ router ตัวจริง (หรือโปรแกรมอื่น) ถืออยู่บน GPU ทำให้ -fit ของ router ทดสอบได้ชั้นน้อยลง
    # ผลจึงวัด "การแย่ง VRAM" ไม่ใช่ค่าตั้ง (รอบแรกของวันนี้: 4B ตัวจริงถูกโหลดกลางรอบ 3.8 GB → 27B ได้แค่ 1.9 GB)
    # --max-vram-used-mib N = รอจน VRAM ที่ใช้อยู่ไม่เกิน N (ไม่เกิน --wait-idle-s) ไม่งั้นข้ามรอบนี้พร้อมเหตุผล
    cap = getattr(args, "max_vram_used_mib", None)
    if cap is not None:
        waited = 0
        while True:
            snap = vram_snapshot()
            used = max((g.get("used_mib") or 0) for g in snap) if snap else None
            if used is None or used <= cap or waited >= args.wait_idle_s:
                break
            time.sleep(10)
            waited += 10
        if used is not None and used > cap:
            row["skipped"] = "GPU มีโปรแกรมอื่นถือ VRAM อยู่ %d MiB > %d MiB — ไม่วัดแข่ง" % (used, cap)
            log("  %s: ข้าม — %s" % (name, row["skipped"]))
            return row
    preset = os.path.join(work, "preset-%s.ini" % name)
    gp._write_atomic(preset, variant_preset_text(base_text, model, keys, name))
    proc = None
    try:
        # VRAM ก่อนเปิด router (มีโปรแกรมอื่นถืออยู่ไหม) และหลังวัด (โมเดลยังโหลดอยู่ = ที่ 27B ใช้จริง)
        row["vram_before"] = vram_snapshot()
        proc = start_test_router(args.test_port, preset, os.path.join(work, "router-%s%s.log" % (name, suffix)))
        row.update(bench_model(args.test_port, model, args.tokens, log=log, repeat=args.repeat))
        # VRAM หลังสร้างข้อความ ก่อนถามรูป: ค่าที่เหลือให้บริการอื่น (STT ต้องว่าง >= 1.5 GB) ตอนแชตข้อความปกติ
        row["vram_after_gen"] = vram_snapshot()
        if eff.get("mmproj") and not row.get("error"):
            row.update(image_check(args.test_port, model, png))
        row["vram_loaded"] = vram_snapshot()
    except RuntimeError as e:
        row["error"] = str(e)
    finally:
        stop_test_router(proc)
    log("  %s%s: gen %s tok/s%s%s%s" % (name, suffix, _fmt(row.get("gen_tps")),
                                        (" · รูป %s" % ("ผ่าน" if row.get("image_ok") else "ไม่ผ่าน"))
                                        if eff.get("mmproj") else "",
                                        " · VRAM ว่าง %s MiB" % ",".join(
                                            str(g.get("free_mib")) for g in (row.get("vram_after_gen") or [])),
                                        (" · " + row["error"]) if row.get("error") else ""))
    return row


def merge_rounds(name, keys, model, parts):
    """รวมผลหลายรอบของค่าตั้งเดียวกัน — gen_tps = ค่ากลางของทุกตัวอย่าง (ทุก repeat ทุกรอบ)
    ดูรูปต้องผ่านทุกรอบที่วัดได้; ไม่มีรอบไหนวัดได้ = ใช้ error/skipped ของรอบแรกที่มี (recommend ข้ามแถวนี้)"""
    row = {"variant": name, "keys": keys, "model": model, "rounds": parts}
    eff = next((p["effective"] for p in parts if isinstance(p.get("effective"), dict)), None)
    if eff is not None:
        row["effective"] = eff
    good = [p for p in parts if not p.get("error") and not p.get("skipped") and p.get("gen_tps")]
    if not good:
        bad = next((p for p in parts if p.get("error") or p.get("skipped")), {})
        for k in ("error", "skipped"):
            if bad.get(k):
                row[k] = bad[k]
        if "error" not in row and "skipped" not in row:
            row["error"] = "ไม่มีรอบที่วัดความเร็วได้"
        return row
    samples = []
    for p in good:
        runs = [r.get("gen_tps") for r in (p.get("runs") or []) if r.get("gen_tps")]
        samples.extend(runs or [p["gen_tps"]])
    row["gen_tps"] = _median(samples)
    row["gen_samples"] = samples
    row["prompt_tps"] = _median([p.get("prompt_tps") for p in good])
    if (eff if eff is not None else keys).get("mmproj"):
        row["image_ok"] = all(p.get("image_ok") for p in good)
        row["image_wall_s"] = _median([p.get("image_wall_s") for p in good])
        row["image_reply"] = good[-1].get("image_reply")
    row["vram_loaded"] = good[-1].get("vram_loaded")
    # VRAM ที่เหลือหลังสร้างข้อความ (ค่าต่ำสุดของทุกรอบ) — STT ใช้ GPU ได้เมื่อว่าง >= 1536 MiB
    frees = [min(g.get("free_mib") or 0 for g in p["vram_after_gen"]) for p in good if p.get("vram_after_gen")]
    if frees:
        row["vram_free_after_gen_mib"] = min(frees)
    errs = [p.get("error") for p in parts if p.get("error")]
    if errs:
        row["round_errors"] = errs
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description="วัดความเร็วของแต่ละโมเดลผ่าน llama-server router")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--models", nargs="+", default=None, help="model id (ชื่อไฟล์ไม่มี .gguf) ไม่ใส่ = ทุกโมเดล")
    ap.add_argument("--tokens", type=int, default=DEFAULT_TOKENS)
    ap.add_argument("--force", action="store_true", help="วัดแม้ router กำลังตอบแชตอยู่")
    # ปกติ = แผนของ router พอร์ตนั้น (8099 → C:\LLM\gpu-profile.json, พอร์ตทดสอบ → C:\LLM\logs\gpu-<port>\)
    # ถ้าอ่านไฟล์กลางตอนวัด router ทดสอบ คอลัมน์ devices จะเป็นแผนของ router ตัวจริง ไม่ใช่ตัวที่วัด
    ap.add_argument("--profile", default=None, help="gpu-profile.json ที่ใช้บอกว่าโมเดลอยู่บน GPU ไหน "
                                                    "(ปกติ = ของ router พอร์ตนั้น)")
    ap.add_argument("--out-dir", default=LOG_DIR)
    # batch 2b (C3): วัดซ้ำหลายรอบ (ใช้ค่ากลาง) + ถามรูป + เทียบค่าตั้งบน router ตัวทดสอบ
    ap.add_argument("--repeat", type=int, default=1, help="วัดกี่รอบต่อโมเดล (รายงานค่ากลาง) — เครื่องนี้แกว่ง ±15%%")
    ap.add_argument("--image", default=None, help="ไฟล์ PNG ที่ใช้ถามรูป (ไม่ใส่ในโหมด --variants = สร้างรูปเล็กเอง)")
    ap.add_argument("--variants", default=None,
                    help="ชุดค่าตั้งที่จะเทียบบน router ตัวทดสอบ: vision27b หรือไฟล์ JSON [[ชื่อ, {คีย์: ค่า}], ...] "
                         "(ค่า null = ลบคีย์นั้นออกจาก preset ตัวจริง เช่น {\"mmproj-device\": null} = mmproj บน GPU)")
    ap.add_argument("--only", nargs="+", default=None, help="วัดเฉพาะค่าตั้งเหล่านี้ (base วัดเสมอ)")
    ap.add_argument("--rounds", type=int, default=1,
                    help="วัดทุกค่าตั้งสลับกันกี่รอบ (ABBA: รอบคู่เรียงกลับ) — หักล้างความเร็วที่ไหลตามเวลา (เครื่องร้อน/งานอื่น)")
    ap.add_argument("--test-port", type=int, default=DEFAULT_TEST_PORT)
    ap.add_argument("--min-free-gb", type=float, default=MIN_FREE_GB,
                    help="commit ที่ต้องเหลือก่อนโหลดโมเดลแต่ละรอบ (ไม่พอ = ข้าม)")
    ap.add_argument("--max-drop", type=float, default=MAX_DROP, help="ความเร็วที่ยอมให้ลดได้ (0.10 = 10%%)")
    ap.add_argument("--wait-idle-s", type=int, default=600, help="รอแชตของ router ตัวจริงเสร็จได้นานเท่านี้ก่อนข้าม")
    ap.add_argument("--max-vram-used-mib", type=int, default=None,
                    help="--variants: ก่อนเปิด router ทดสอบแต่ละรอบ รอจน VRAM ที่ใช้อยู่ไม่เกินเท่านี้ (โมเดลของ router ตัวจริง/"
                         "โปรแกรมอื่นถืออยู่ = ผลเพี้ยน) ไม่ทันใน --wait-idle-s = ข้ามรอบนั้น")
    ap.add_argument("--write-user-ini", action="store_true",
                    help="เขียนค่าที่แนะนำลง models-preset.user.ini (เฉพาะเมื่อยังไม่มีไฟล์นี้)")
    args = ap.parse_args(argv)
    if args.tokens <= 0:
        print("--tokens ต้องมากกว่า 0")
        return EXIT_SOME_FAILED
    if args.variants:
        return run_variants(args)

    try:
        listed = gp.router_models(args.port)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # router เปิดด้วย --api-key-file (ตัวเปิด 2026-09-30) — gp.http_json แนบโทเคนจาก C:\LLM\secrets ให้เอง
            # 401 = อ่านไฟล์โทเคนไม่ได้ หรือไฟล์ถูกสร้างใหม่หลัง router เริ่ม
            print("router พอร์ต %d ปฏิเสธคำขอ (401: ต้องใช้โทเคนของบริการในเครื่อง) — ตรวจว่ามี %s "
                  "และถ้าไฟล์เพิ่งถูกสร้างใหม่ ให้เปิด start-qwen38.ps1 อีกครั้งเพื่อรีสตาร์ต router"
                  % (args.port, gp.LOCAL_TOKEN_FILE))
        else:
            print("router พอร์ต %d ตอบ HTTP %d — เปิดตัวเปิด start-qwen38.ps1 ก่อน" % (args.port, e.code))
        return EXIT_NO_ROUTER
    except (OSError, ValueError, urllib.error.URLError) as e:
        print("ต่อ router พอร์ต %d ไม่ได้ (%s) — เปิดตัวเปิด start-qwen38.ps1 ก่อน" % (args.port, e))
        return EXIT_NO_ROUTER
    try:
        busy, notes = gp.router_busy(args.port)
    except (OSError, ValueError, urllib.error.URLError) as e:
        busy, notes = False, ["อ่านสถานะไม่ได้ (%s)" % e]
    if busy and not args.force:
        print("router พอร์ต %d กำลังทำงานอยู่: %s" % (args.port, "; ".join(notes)))
        print("รอให้แชตตอบเสร็จก่อน หรือใส่ --force ถ้าแน่ใจ")
        return EXIT_BUSY

    ids = [m["id"] for m in listed]
    if args.models:
        wanted = []
        for w in args.models:
            hit = next((i for i in ids if i == w), None) or next((i for i in ids if i.lower() == w.lower()), None)
            if hit:
                wanted.append(hit)
            else:
                print("ข้าม %s — router ไม่มีโมเดลชื่อนี้ (มี: %s)" % (w, ", ".join(ids)))
        ids = wanted
    if not ids:
        print("ไม่มีโมเดลให้วัด")
        return EXIT_SOME_FAILED

    profile_path = args.profile or os.path.join(gp.published_dir(args.port), gp.PROFILE_NAME)
    profile = load_profile(profile_path)
    now_fp = gp.current_fingerprint()
    stale = bool(profile) and now_fp is not None and profile.get("fingerprint") != now_fp
    if profile:
        print("โปรไฟล์ GPU: %s (%s)" % (profile.get("profile"), profile.get("generated_at")))
        if stale:
            print("คำเตือน: GPU ที่ต่ออยู่ตอนนี้ไม่ตรงกับโปรไฟล์ — เปิด start-qwen38.ps1 ใหม่ก่อน ตัวเลขจะได้ตรงกับแผน")
    else:
        print("ไม่พบ %s — คอลัมน์ devices จะเป็น ?" % profile_path)
    print("วัด %d โมเดลบน router พอร์ต %d (router โหลดพร้อมกันได้ 2 ตัว ตัวที่โหลดค้างไว้อาจถูกปลดออก)"
          % (len(ids), args.port))

    rows = []
    started = datetime.datetime.now().astimezone()
    png = None
    if args.image:
        with open(args.image, "rb") as f:
            png = f.read()
    for mid in ids:
        r = bench_model(args.port, mid, args.tokens, repeat=args.repeat)
        if png is not None and not r.get("error"):
            r.update(image_check(args.port, mid, png))
        r["devices"] = device_names(profile, mid)
        p = ((profile or {}).get("placement") or {}).get(mid) or {}
        r["device_ids"] = p.get("devices")
        r["est_gen_tps"] = p.get("est_gen_tps")
        r["est_gen_tps_busy"] = p.get("est_gen_tps_busy")
        # ช่วงเดียวกับที่ตัวเปิดแสดง (ล่าง = CPU มีงานอื่น, บน = เครื่องว่าง) — "?" ถ้าประมาณไม่ได้
        r["est"] = gp._speed_text(p) if p else None
        rows.append(r)
        if r["error"]:
            print("  %s: ผิดพลาด %s" % (mid, r["error"]))
        else:
            print("  %s: gen %.1f tok/s, prompt %s tok/s, %.1f วินาที"
                  % (mid, r["gen_tps"] or 0, _fmt(r["prompt_tps"]), r["wall_s"]))
    print("")
    print_table(rows)

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "gpu-bench-%s.json" % started.strftime("%Y%m%d-%H%M%S"))
    doc = {
        "version": 1,
        "started_at": started.isoformat(timespec="seconds"),
        "port": args.port,
        "tokens": args.tokens,
        "profile_path": profile_path,
        "profile": {k: (profile or {}).get(k) for k in ("profile", "generated_at", "fingerprint", "devices")},
        "current_fingerprint": now_fp,
        "profile_stale": stale,
        "results": rows,
    }
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print("")
    print("บันทึกผล: %s" % out_path)
    return EXIT_SOME_FAILED if any(r["error"] for r in rows) else EXIT_OK


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
