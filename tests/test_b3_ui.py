# -*- coding: utf-8 -*-
"""
เทสต์ของ batch 3 สัญญา D4 (owner ui, 2026-10-06)
  (a) หน้าจัดการ (PAGE, hub 8100): แท็บ "โปรเจกต์ | การใช้งาน | ตรวจระบบ" — กราฟ SVG ที่วาดเอง (โทเค็นต่อวันแยกโมเดล,
      ความเร็ว tok/s แยกโมเดล, โปรเจกต์ที่ใช้มากที่สุด) + ตารางคำขอล่าสุด จาก GET /api/usage?days=7|30 และสถานะระบบจาก
      GET /api/doctor (ตารางบริการ จุดสี วิธีแก้ คัดลอกรายงานที่ล้างความลับแล้ว) · เมนูบัญชีของหน้าแชตมีลิงก์ไปทั้งสองแท็บ
  (b) ป้าย "สรุปช่วงต้นของบทสนทนาแล้ว (n รอบ)" ในแชต: enhance อ่าน header X-Qwen-Compacted ของคำขอแชต (ไม่แตะ body)

ส่วนที่ 1 — รันเสมอ (ไม่เปิดพอร์ต ไม่เปิดเบราว์เซอร์):
  * ข้อความ b3_* ครบสองภาษา ตัวแปร %s/%1.. ตรงกัน ภาษาอังกฤษไม่มีอักษรไทย ทุกคีย์ที่หน้าใช้มีจริง
  * PAGE/SHELL: สคริปต์ inline ผ่าน node --check, ARIA ของแท็บ, ไม่มี innerHTML/URL ภายนอก, ลิงก์ในเมนูบัญชี
  * ฟังก์ชันล้วน _B3_JS ใน node: รับ JSON หลายรูปแบบ (เพราะ owner hub ทำคู่ขนาน รูปแบบยังไม่ตายตัว), สีตามโมเดลคงที่,
    รวม "อื่นๆ" เกิน 5 สี, ค่าของไฟล์คีย์ไม่หลุด, รายงานที่คัดลอกไม่มีโทเค็น/word joiner
  * webui-enhance.js ส่วน batch 3: ตำแหน่ง/การต่อเข้า extrasPass, ตัวห่อ fetch คืน Promise เดิมและไม่อ่าน body,
    ฟังก์ชันล้วนรันใน node, ป้ายทุกคำมีคำแปลไทย · webui-theme.css ส่วน 13 ใช้ token ล้วน
ตรวจไฟล์สำเนาได้: QWEN_ENH_FILE, QWEN_THEME_FILE, QWEN_PARTS_FILE

ส่วนที่ 2 — E2E (ปิดไว้เป็นค่าเริ่มต้น: set QWEN_B3_E2E=1, ต้องมี Edge + router ที่รันอยู่ — 8099 หรือพอร์ตสำรอง
  QWEN_B3_ROUTER_PORT=8199 เมื่อ router ตัวจริงไม่ได้เปิด; ใช้แค่หน้า WebUI ไม่โหลดโมเดล):
  hub สำเนาใน process นี้บนพอร์ตว่างใน 8171-8173 (API + พอร์ตโปรเจกต์) ข้อมูลอยู่ในโฟลเดอร์ชั่วคราวทั้งหมด
  /api/usage และ /api/doctor = ข้อมูลปลอมของเทสต์ (ไม่ถาม hub จริง ไม่อ่าน log จริง) · upstream ปลอม: GET → router
  (หน้า WebUI, GET ที่มี model= ถูกบล็อก) · คำขอแชตตอบเองด้วย SSE ปลอม + X-Qwen-Compacted (ไม่ถึงโมเดลจริง)

โหมดเปิดค้างสำหรับถ่ายภาพ (shot.py): python test_b3_ui.py --serve [--mode ok|healthy|empty|unsupported|real|real-healthy]
  (real = เส้นทาง /api/usage|doctor ตัวจริงของ hub กับ usage.jsonl สังเคราะห์ + hub_doctor._build ของผลตรวจที่จัดไว้)
  [--theme dark|light] [--lang th|en] [--minutes 20] — พิมพ์พอร์ตแล้วรอ (ปิดเองเมื่อครบเวลา)
"""
import datetime
import http.client
import importlib.util
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

ENH = os.environ.get("QWEN_ENH_FILE") or r"C:\LLM\projects\static\webui-enhance.js"
CSS = os.environ.get("QWEN_THEME_FILE") or r"C:\LLM\projects\static\webui-theme.css"
PARTS = os.environ.get("QWEN_PARTS_FILE") or r"C:\LLM\projects\hub_i18n_parts.py"
HUB = r"C:\LLM\projects\hub.py"
TOOLS = r"C:\LLM\projects\tools"
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
HAVE_NODE = os.path.isfile(NODE) if os.path.isabs(NODE) else bool(shutil.which("node"))
THAI = re.compile("[\u0E00-\u0E7F]")
B3_ENH_START = "batch 3 (2026-10-06, owner ui) — สัญญา D4(b)"
FAST = "Qwen3-4B-Instruct-2507-Q4_K_M"
MODELS = [FAST, "Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL", "Qwen3.8-27B-UD-Q4_K_M", "gpt-oss-20b-MXFP4"]
SECRET = "Zx81QmLkTr5uVw3yHs9dPa2eGb7nFc4jRt6"      # สายอักขระที่ต้องไม่โผล่ในหน้า/รายงานเด็ดขาด


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def load_parts():
    spec = importlib.util.spec_from_file_location("hub_i18n_parts_b3_ui", PARTS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_node(code):
    fd, path = tempfile.mkstemp(suffix=".js", prefix="b3ui-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(code)
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True, encoding="utf-8", timeout=60)
    finally:
        os.remove(path)
    if r.returncode != 0:
        raise AssertionError("node failed: %s" % r.stderr[-2500:])
    return json.loads(r.stdout)


def js_function(src, name):
    """ฟังก์ชันระดับบนของ IIFE (ย่อหน้า 2 ช่อง) — จบที่บรรทัด "  }" แรก"""
    m = re.search(r"\n  function %s\(" % re.escape(name), src)
    if not m:
        raise AssertionError("function %s not found" % name)
    end = src.index("\n  }\n", m.start() + 1)
    return src[m.start() + 1:end + 4]


def inline_scripts(tpl):
    return re.findall(r"<script>(.*?)</script>", tpl, re.S)


def hub_strings_en():
    import ast
    for n in ast.parse(read(HUB)).body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "STRINGS":
            return ast.literal_eval(n.value).get("en", {})
    return {}


parts = load_parts()


# ------------------------------------------------------------------------------------------------ ข้อมูลปลอม
PROJECTS = [("uitest", "ทดสอบหน้าจอ"), ("charger", "วินิจฉัยตู้ชาร์จ"), ("ocpp-research", "ocpp-research"),
            ("project1", "project1"), ("demo-b", "demo-b")]


def fake_usage(days, today=None):
    """รูปแบบที่แนะนำให้ hub (D2): per_day = แถวละ (วัน, โปรเจกต์, โมเดล) + recent + totals — ค่าคงที่ทุกครั้ง (seed)"""
    rnd = random.Random(20261006)
    today = today or datetime.date.today()
    speeds = {MODELS[0]: (27.5, 140.0, .75), MODELS[1]: (17.0, 95.0, .22), MODELS[2]: (1.15, 72.0, .3),
              MODELS[3]: (21.0, 120.0, .08)}
    rows = []
    for back in range(30):
        day = today - datetime.timedelta(days=back)
        if back in (3, 11, 12):                              # วันที่ไม่มีการใช้งาน (เส้นความเร็วต้องขาด)
            continue
        for (slug, _), weight in zip(PROJECTS, (1.0, .85, .5, .35, .2)):
            for m in MODELS:
                gen, ptps, share = speeds[m]
                if rnd.random() > share * weight:
                    continue
                req = rnd.randint(1, 8)
                prompt = req * rnd.randint(2500, 9000)
                rows.append({"day": day.isoformat(), "project": slug, "model": m, "requests": req,
                             "prompt_tokens": prompt, "cached_tokens": int(prompt * rnd.uniform(.4, .85)),
                             "completion_tokens": req * rnd.randint(150, 900),
                             "gen_tps": round(gen * rnd.uniform(.85, 1.12), 2),
                             "prompt_tps": round(ptps * rnd.uniform(.8, 1.15), 1),
                             "wall_s": round(req * rnd.uniform(8, 40) * (12 if m == MODELS[2] else 1), 1),
                             "errors": 1 if rnd.random() < .05 else 0, "compacted": 1 if rnd.random() < .08 else 0})
    first = (today - datetime.timedelta(days=days - 1)).isoformat()
    rows = [r for r in rows if r["day"] >= first]
    now = datetime.datetime.now().astimezone()
    recent = []
    for i in range(25):
        m = MODELS[0] if i % 4 else MODELS[2] if i % 8 == 0 else MODELS[1]
        slug = PROJECTS[i % 3][0]
        ts = now - datetime.timedelta(minutes=17 * i + 3)
        recent.append({"ts": ts.isoformat(timespec="seconds"), "project": slug, "model": m,
                       "prompt_tokens": 4000 + 913 * i, "cached_tokens": 3000 + 500 * i if i % 3 else 0,
                       "completion_tokens": 200 + 37 * i, "prompt_tps": 120.5 - i, "gen_tps": 1.1 if m == MODELS[2] else 26.4,
                       "wall_s": 9.5 + i * 3, "tools_used": ["local_read"] if i % 5 == 1 else (["web_search", "local_read"] if i == 2 else []),
                       "compacted": i == 4, "compacted_turns": 12 if i == 4 else 0, "error": i == 7})
    tot = {k: sum(r[k] for r in rows) for k in ("requests", "prompt_tokens", "cached_tokens", "completion_tokens",
                                                   "errors", "compacted", "wall_s")}
    return {"days": days, "from": first, "to": today.isoformat(), "totals": tot, "per_day": rows, "recent": recent}


def fake_doctor(mode="ok"):
    """รูปแบบที่แนะนำให้ hub (D3) — มีปัญหาให้เห็น 2 อย่าง (STT ไม่ทำงาน, ดิสก์ C เหลือน้อย) และสายอักขระลับปลอมใน log
    กับในไฟล์คีย์ เพื่อตรวจว่าหน้าไม่แสดง/รายงานไม่คัดลอกค่าเหล่านั้น"""
    now = datetime.datetime.now().astimezone()
    sick = mode != "healthy"
    return {
        "ts": now.isoformat(timespec="seconds"), "took_ms": 840, "cached": False,
        "services": [
            {"id": "router", "port": 8099, "state": "ok", "latency_ms": 14, "models_loaded": [FAST]},
            {"id": "mcp-local", "port": 8792, "state": "ok", "latency_ms": 31},
            {"id": "websearch", "port": 8791, "state": "ok", "latency_ms": 22, "detail": "provider: builtin"},
            {"id": "embed", "port": 8093, "state": "ok", "latency_ms": 9},
            {"id": "stt", "port": 8795, "state": "down" if sick else "ok", "latency_ms": None if sick else 18,
             "detail": "connection refused" if sick else "gpu"},
            {"id": "scheduler", "state": "ok", "heartbeat_age_s": 42},
            {"id": "gateway", "port": 8780, "state": "ok", "latency_ms": 6},
            {"id": "hub", "port": 8100, "ports": [{"port": p, "ok": True} for p in (8101, 8102, 8103, 8104)]},
        ],
        "fixes": ([{"th": "บริการถอดเสียงไม่ทำงาน → รัน launcher -RestartStt", "en": "STT is not running -> run the launcher with -RestartStt",
                    "severity": "error", "service": "stt"},
                   {"th": "ดิสก์ C: เหลือน้อย (ต่ำกว่า 10%) — ย้าย cache ไป D: หรือ E:", "en": "Disk C: is low (under 10%) — move caches to D: or E:",
                    "severity": "warn"}] if sick else []),
        "gpu": [{"name": "NVIDIA RTX 1000 Ada Generation Laptop GPU", "driver": "596.71", "memory_total_mb": 6141,
                 "memory_used_mb": 5322, "temp_c": 54, "util_pct": 37}],
        "memory": {"ram_total_mb": 32456, "ram_free_mb": 8120, "commit_total_mb": 65536, "commit_free_mb": 27310},
        "disks": [{"drive": "C:", "total_gb": 476.3, "free_gb": 41.2 if sick else 120.5}, {"drive": "D:", "total_gb": 931.5, "free_gb": 402.7},
                  {"drive": "E:", "total_gb": 1863.0, "free_gb": 1210.4}],
        "versions": {"llama_cpp": "b10984", "python": "3.13.1", "hub": "qwen38-hub/1.2"},
        "models": [{"name": "Qwen3.8-27B-UD-Q4_K_M.gguf", "size_bytes": 17_350_000_000},
                   {"name": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "size_bytes": 2_500_000_000},
                   {"name": "Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf", "size_bytes": 17_700_000_000},
                   {"name": "gpt-oss-20b-MXFP4.gguf", "size_bytes": 12_100_000_000}],
        "secrets": {"local-services.token": True, "router.key": SECRET, "brave-search.key": False},
        "brave_key": False,
        "docker": {"ok": False, "reason": "Docker Desktop is not installed correctly"},
        "errors": ([{"file": r"C:\LLM\logs\stt.err.log", "line": "2026-10-06 15:02:11 ERROR stt: CUDA out of memory, falling back to CPU"},
                    {"file": "hub.err.log", "line": "2026-10-06 15:40:02 ERROR proxy: upstream 8099 Authorization: Bearer %s rejected" % SECRET},
                    {"file": "mcp-local.err.log", "line": "ERROR guard: denied write C:\\LLM\\secrets\\x (token=%s)" % SECRET}] if sick else []),
        "tests": {"passed": 1393, "skipped": 38, "failed": 0, "ts": (now - datetime.timedelta(hours=1)).isoformat(timespec="seconds")},
    }


# ------------------------------------------------------------------------------------------------ รูปจริงของ hub (owner hub)
# ทำไม: ตัวแปลงของหน้ารับ JSON ได้หลายแบบเพราะสร้างคู่ขนานกับ owner hub — ชุดนี้ป้อนผลจากโค้ดจริงของ hub
# (hub_usage.aggregate, hub_doctor.Doctor._build + localize) ให้หน้า โดยไม่เปิดพอร์ต/ไม่ถามบริการจริง/ไม่อ่าน log จริง
HUB_USAGE = r"C:\LLM\projects\hub_usage.py"
HUB_DOCTOR = r"C:\LLM\projects\hub_doctor.py"


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def usage_rows(now=None):
    """บรรทัดดิบแบบที่ hub_usage.UsageLog เขียนลง usage.jsonl (ฟิลด์ตาม FIELDS) 30 วันย้อนหลัง — สุ่มแบบคงที่ (seed)
    prompt_tokens รวมส่วนที่มาจากแคชแล้ว (ตาม UsageTap.numbers) · วันที่ 3, 11, 12 ย้อนหลังไม่มีการใช้งาน"""
    rnd = random.Random(1006)
    now = now or datetime.datetime.now().astimezone()
    speeds = {MODELS[0]: (27.5, 140.0, .75), MODELS[1]: (17.0, 95.0, .22), MODELS[2]: (1.15, 72.0, .3),
              MODELS[3]: (21.0, 120.0, .08)}
    rows = []
    for back in range(30):
        if back in (3, 11, 12):
            continue
        day = (now - datetime.timedelta(days=back)).date()
        for (slug, _), weight in zip(PROJECTS, (1.0, .85, .5, .35, .2)):
            for m in MODELS:
                gen, ptps, share = speeds[m]
                if rnd.random() > share * weight:
                    continue
                for _k in range(rnd.randint(1, 4)):
                    if back == 0:      # วันนี้: ก่อนเวลาปัจจุบันเสมอ และยังเป็นวันเดียวกัน
                        mins = now.hour * 60 + now.minute
                        ts = now - datetime.timedelta(minutes=rnd.randint(0, max(0, mins - 1)), seconds=rnd.randint(0, 50))
                    else:
                        ts = datetime.datetime.combine(day, datetime.time(rnd.randint(7, 22), rnd.randint(0, 59), rnd.randint(0, 59)),
                                                       now.tzinfo)
                    prompt = rnd.randint(2500, 9000)
                    comp = rnd.randint(150, 900)
                    g = round(gen * rnd.uniform(.85, 1.12), 2)
                    rows.append({"ts": ts.isoformat(timespec="seconds"), "project": slug, "model": m,
                                 "prompt_tokens": prompt, "cached_tokens": int(prompt * rnd.uniform(.4, .85)),
                                 "completion_tokens": comp, "prompt_tps": round(ptps * rnd.uniform(.8, 1.15), 1), "gen_tps": g,
                                 "wall_s": round(comp / g + rnd.uniform(1, 9), 2),
                                 "tools_used": ["local_read"] if rnd.random() < .2 else [],
                                 "compacted": rnd.random() < .06, "error": rnd.random() < .04,
                                 "conv": "%012x" % rnd.getrandbits(48)})
    rows.sort(key=lambda r: r["ts"])
    return rows


def real_usage(days, rows=None, now=None):
    mod = load_mod("hub_usage_b3_ui", HUB_USAGE)
    return mod.aggregate(rows if rows is not None else usage_rows(now), days, now=now,
                         project_names={s: n for s, n in PROJECTS})


# ดิสก์ของเครื่องจริงตอนตรวจรับ batch 3 (integ 2026-10-06): % ที่ว่างต่ำ (C: 5.5%, E: 5%) แต่เกิน DISK_LOW_GB 10 ของ hub
# = hub ไม่มีคำแนะนำเรื่องดิสก์ — หน้าเคยขึ้นแดง "เหลือน้อย" เองจาก % (สัญญาณขัดกับป้าย "ทุกบริการทำงานปกติ")
LIVE_DISKS = [{"drive": "C:", "present": True, "free_gb": 26.2, "total_gb": 474.1},
              {"drive": "D:", "present": True, "free_gb": 769.9, "total_gb": 931.5},
              {"drive": "E:", "present": True, "free_gb": 11.5, "total_gb": 229.2}]


def real_doctor(tmp, lang="th", sick=True, raw=False, disks=None):
    """รายงานจาก hub_doctor ตัวจริง: _build() ของผลตรวจที่จัดเตรียมไว้ (ไม่รันตัวตรวจที่ถามพอร์ต/nvidia-smi) + localize()
    ไฟล์คีย์/ผลเทสต์เป็นไฟล์ชั่วคราว — ค่า SECRET อยู่ในไฟล์คีย์และใน log เพื่อตรวจว่าไม่หลุดถึงหน้า
    disks = แทนรายการดิสก์ของผลตรวจ (ค่าเริ่มต้น: C: 8.4 GB ตอน sick / 120.5 GB ตอนปกติ)"""
    mod = load_mod("hub_doctor_b3_ui", HUB_DOCTOR)
    tmp = Path(tmp)
    (tmp / "local-services.token").write_text(SECRET, encoding="utf-8")
    (tmp / "tests-last.json").write_text(json.dumps({
        "at": (datetime.datetime.now().astimezone() - datetime.timedelta(hours=2)).isoformat(timespec="seconds"),
        "ran": 1431, "ok": not sick, "failures": 1 if sick else 0, "errors": 0, "skipped": 38,
        "failed": ["test_b3_ui.Demo.test_x (token=%s)" % SECRET] if sick else []}), encoding="utf-8")
    cfg = {"token_file": str(tmp / "local-services.token"), "brave_key_file": str(tmp / "brave-search.key"),
           "gateway_key_file": str(tmp / "gateway_key.txt"), "tests_file": str(tmp / "tests-last.json"),
           "llama_dir_build": "b10984", "hub_version": "2026-10-06 21:00"}
    row = mod._row
    res = {
        "router": row("router", "ตัวจัดการโมเดล (llama-server)", "Model router (llama-server)", 8099, "ok", 12,
                      models=[{"id": m, "state": "loaded" if m == FAST else "unloaded"} for m in MODELS],
                      loaded=[{"id": FAST, "state": "loaded"}], build="b10984-0c7d9b0", max_instances=2),
        "mcp_local": row("mcp_local", "เครื่องมือในเครื่อง (MCP)", "Local tools (MCP)", 8792, "ok", 28),
        "mcp_web": row("mcp_web", "ค้นเว็บ (MCP)", "Web search (MCP)", 8791, "ok", 19, provider="builtin"),
        "embed": row("embed", "ค้นตามความหมาย (embedding)", "Semantic search (embedding)", 8093, "ok", 7),
        "stt": row("stt", "พูดแทนพิมพ์ (STT)", "Speech-to-text (STT)", 8795, "down" if sick else "ok", None if sick else 15,
                   detail="" if sick else "ready", device="" if sick else "gpu"),
        "scheduler": row("scheduler", "ตัวตั้งเวลา (scheduler)", "Scheduler", None, "ok", None, heartbeat_age_s=1260,
                         heartbeat_status="ok", heartbeat_message="ok 4/4", runner_alive=True),
        "gateway": row("gateway", "Remote Prompt Gateway", "Remote prompt gateway", 8780, "ok", 5, upstream_ok=True),
        "hub": row("hub", "ฮับ + พอร์ตโปรเจกต์", "Hub + project ports", 8100, "ok", 0, keep_awake=1,
                   ports=[{"slug": s, "name": n, "port": 8101 + i, "state": "ok", "latency_ms": 1, "in_process": True}
                          for i, (s, n) in enumerate(PROJECTS)]),
        "gpu": ([{"name": "NVIDIA RTX 1000 Ada Generation Laptop GPU", "mem_total_mib": 6141, "mem_used_mib": 5322,
                  "mem_free_mib": 819, "driver": "596.71", "temp_c": 54, "util_pct": 37}], None),
        "logs": ([{"file": "stt.err.log", "file_mtime": "2026-10-06T15:02:11+07:00",
                   "line": "2026-10-06 15:02:11 ERROR stt: CUDA out of memory, falling back to CPU"},
                  {"file": "hub.err.log", "file_mtime": "2026-10-06T15:40:02+07:00",
                   "line": mod.redact("2026-10-06 15:40:02 ERROR proxy: upstream 8099 Authorization: Bearer %s rejected" % SECRET)}]
                 if sick else [], 3),
        "models": [{"name": m + ".gguf", "size_gb": sz, "dir": r"C:\LLM\models"} for m, sz in
                   zip(MODELS, (2.33, 16.47, 16.16, 11.27))],
        "memory": {"ram_total_gb": 31.7, "ram_free_gb": 7.9, "ram_load_pct": 75, "commit_limit_gb": 64.0,
                   "commit_free_gb": 26.7},
        "disks": [dict(x) for x in disks] if disks is not None else [
            {"drive": "C:", "present": True, "free_gb": 8.4 if sick else 120.5, "total_gb": 476.3},
            {"drive": "D:", "present": True, "free_gb": 402.7, "total_gb": 931.5},
            {"drive": "E:", "present": True, "free_gb": 1210.4, "total_gb": 1863.0}],
        "docker": {"usable": False, "reason_th": "ติดตั้ง Docker Desktop ไว้แต่ engine ไม่ทำงาน",
                   "reason_en": "Docker Desktop is installed but its engine is not running"},
    }
    rep = mod.Doctor(cfg)._build(res, [])
    rep["took_ms"], rep["cached"] = 812, False
    return rep if raw else mod.localize(rep, lang)   # raw = แบบที่ hub.doctor_report() คืน (ก่อน localize)


# ------------------------------------------------------------------------------------------------ ข้อความ
class StringsTests(unittest.TestCase):
    def test_th_en_pairs_and_placeholders(self):
        th, en = parts.STRINGS_UI["th"], parts.STRINGS_UI["en"]
        b3 = sorted(k for k in en if k.startswith("b3_"))
        self.assertGreater(len(b3), 120)
        self.assertEqual(sorted(k for k in th if k.startswith("b3_")), b3)
        for k in b3:
            self.assertTrue(th[k].strip() and en[k].strip(), k)
            self.assertFalse(THAI.search(en[k]), k)
            self.assertEqual(sorted(re.findall(r"%(?:\d|s)", th[k])), sorted(re.findall(r"%(?:\d|s)", en[k])), k)
            self.assertNotRegex(th[k], "\u200b", "ห้ามมี ZWSP ในข้อความ (glue() ใส่ word joiner เอง)")

    def test_every_key_used_exists(self):
        known = set(parts.STRINGS_UI["en"]) | set(hub_strings_en())
        for name, tpl in (("PAGE", parts.PAGE), ("SHELL", parts.SHELL)):
            used = set(re.findall(r"__T_([a-z0-9_]+?)__", tpl))
            for s in inline_scripts(tpl):
                used |= set(re.findall(r"\b(?:t|b3T)\('([a-z0-9_]+)'\)", s))
            self.assertEqual(sorted(used - known), [], name)
        # คีย์ที่ประกอบขึ้นตอนทำงาน: ชนิดบริการและสถานะ
        for k in ("router", "mcp", "web", "embed", "stt", "sched", "gateway", "hub"):
            self.assertIn("b3_svc_" + k, known)
        for k in ("ok", "warn", "bad", "off"):
            self.assertIn("b3_st_" + k, known)

    def test_contract_wording(self):
        # สัญญา D4: ชื่อแท็บ "การใช้งาน / Usage" และ "ตรวจระบบ / Doctor"
        th, en = parts.STRINGS_UI["th"], parts.STRINGS_UI["en"]
        self.assertEqual((th["b3_tab_usage"], en["b3_tab_usage"]), ("การใช้งาน", "Usage"))
        self.assertEqual((th["b3_tab_doctor"], en["b3_tab_doctor"]), ("ตรวจระบบ", "Doctor"))
        self.assertEqual((th["b3_menu_usage"], th["b3_menu_doctor"]), ("การใช้งาน", "ตรวจระบบ"))


# ------------------------------------------------------------------------------------------------ PAGE / SHELL
class PageTemplateTests(unittest.TestCase):
    def setUp(self):
        self.page = parts.PAGE

    def test_tabs_markup(self):
        p = self.page
        self.assertIn('role="tablist"', p)
        for name in ("projects", "usage", "doctor"):
            self.assertIn('id="tab-%s" data-tab="%s" aria-controls="pn-%s"' % (name, name, name), p)
            self.assertIn('id="pn-%s" role="tabpanel" aria-labelledby="tab-%s"' % (name, name), p)
        self.assertEqual(p.count('role="tab" '), 3)
        self.assertIn('role="radiogroup"', p)
        self.assertIn('aria-describedby="uKeys"', p)
        self.assertIn('id="uLive" aria-live="polite"', p)
        self.assertIn('id="dLive" aria-live="polite"', p)
        # ก้อนฟังก์ชันล้วนถูกแทนแล้ว และไม่มีคำที่ fill() ของ hub จะไปแทนผิดที่
        self.assertNotIn("__QW_B3__", p)
        for bad in ("__LANG__", "__THEME__", "__FONT__"):
            self.assertNotIn(bad, parts._B3_JS)

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_inline_scripts_parse(self):
        tpl = (self.page.replace("__T_JSON__", "{}").replace("__LANG__", "th").replace("__THEME__", "dark")
               .replace("__FONT__", "serif"))
        tpl = re.sub(r"__T_([a-z0-9_]+?)__", "x", tpl)
        for code in inline_scripts(tpl):
            fd, fn = tempfile.mkstemp(suffix=".js", prefix="b3page-")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(code)
            try:
                r = subprocess.run([NODE, "--check", fn], capture_output=True, text=True, timeout=60)
            finally:
                os.remove(fn)
            self.assertEqual(r.returncode, 0, r.stderr[-1500:])

    def test_safety(self):
        s = "\n".join(inline_scripts(self.page))
        for bad in ("innerHTML", "insertAdjacentHTML", "document.write", "eval(", "XMLHttpRequest", "sendBeacon",
                    "Claude", "Anthropic"):
            self.assertNotIn(bad, s, bad)
        # URL เดียวที่มีคือ namespace ของ SVG (ไม่ใช่การโหลดอะไร) — ข้อมูลมาจาก /api/* ของ origin เดียวกันเท่านั้น
        self.assertEqual(sorted(set(re.findall(r"https?://[^\s'\"]+", s))), ["http://www.w3.org/2000/svg"])
        self.assertIn("api('/api/usage?days=' + days)", s)
        # lang = ภาษาของชื่อบริการ/เหตุผลที่ hub เติมให้, refresh=1 เฉพาะปุ่ม "ตรวจใหม่" (ข้ามแคช 10 วินาทีของ hub)
        self.assertIn("api('/api/doctor?lang=' + LANG + (fresh ? '&refresh=1' : ''))", s)
        # ค่าที่มาจากเซิร์ฟเวอร์ใส่เป็นข้อความ: กราฟไม่มี setAttribute('style' / onclick จากข้อมูล
        self.assertNotRegex(s, r"setAttribute\('on")

    def test_meter_colour_comes_from_hub(self):
        # integ b3: b3Meter เคยตัดสินเองจาก % ที่ว่าง (ff < 0.07 แดง / < 0.15 อำพัน) ขัดกับคำตัดสินของ hub — ต้องไม่กลับมา
        s = "\n".join(inline_scripts(self.page))
        m = re.search(r"function b3Meter\(.*?\n}\n", s, re.S)
        self.assertTrue(m)
        self.assertNotRegex(m.group(0), r"ff\s*<\s*0?\.\d")
        self.assertIn("k.missing, k.level)", s)
        self.assertIn("false, m.level)", s)
        # คำขอล่าสุด: รายการสองบรรทัดใช้แทนตารางเมื่อตารางกว้างกว่าการ์ด
        self.assertIn("#uR.rc-narrow>table{display:none}", self.page)
        self.assertIn("observe($('#uR'))", s)

    def test_chart_palette_both_themes(self):
        p = self.page
        light = re.search(r":root\{(--ch-1:[^}]*)\}", p)
        dark = re.search(r':root\[data-theme="dark"\]\{(--ch-1:[^}]*)\}', p)
        self.assertTrue(light and dark)
        for blk in (light.group(1), dark.group(1)):
            for i in range(1, 6):
                self.assertIn("--ch-%d:" % i, blk)
        self.assertIn("forced-color-adjust:none", p)

    def test_shell_menu_links(self):
        sh = parts.SHELL
        self.assertIn("openManage('usage')", sh)
        self.assertIn("openManage('doctor')", sh)
        self.assertIn("t('b3_menu_usage')", sh)
        self.assertIn("t('b3_menu_doctor')", sh)
        self.assertIn('<symbol id="i-chart"', sh)
        self.assertIn('<symbol id="i-pulse"', sh)
        self.assertIn("(tab === 'usage' || tab === 'doctor' ? '#' + tab : '')", sh)
        # "จัดการโปรเจกต์" เดิมยังเรียก openManage โดยไม่ส่งแท็บ (ไปหน้าโปรเจกต์ตามเดิม)
        self.assertIn("{ label: t('manage_projects'), icon: 'grid', external: true, run: openManage }", sh)


# ------------------------------------------------------------------------------------------------ ฟังก์ชันล้วน (node)
@unittest.skipUnless(HAVE_NODE, "ไม่มี node")
class LibTests(unittest.TestCase):
    def node(self, body):
        return run_node(parts._B3_JS + "\nfunction out(x) { console.log(JSON.stringify(x)); }\n" + body)

    def test_usage_preferred_shape(self):
        d = fake_usage(7, datetime.date(2026, 10, 6))
        r = self.node("var d = %s; var M = b3Usage(d, {days: 7, models: %s});"
                      "out({days: M.days, series: M.series.map(function (s) { return [s.model, s.slot, s.total, s.avgTps]; }),"
                      " stack: M.stack.length, proj: M.projects.map(function (p) { return p.project; }), tot: M.totals,"
                      " recent: M.recent.length, first: M.recent[0], empty: M.empty});" % (json.dumps(d), json.dumps(MODELS)))
        self.assertEqual(r["days"][0], "2026-09-30")
        self.assertEqual(r["days"][-1], "2026-10-06")
        self.assertEqual(len(r["days"]), 7)
        slots = {m: s for m, s, _, _ in r["series"]}
        for m, s in slots.items():
            self.assertEqual(s, MODELS.index(m), "สีตามตำแหน่งในรายชื่อโมเดล ไม่ใช่ตามอันดับการใช้")
        self.assertEqual(r["tot"]["requests"], d["totals"]["requests"])
        self.assertEqual(r["tot"]["prompt"], d["totals"]["prompt_tokens"])
        self.assertEqual(r["recent"], 25)
        self.assertTrue(r["first"]["t"] > 0)
        self.assertFalse(r["empty"])
        # เรียงโปรเจกต์ตามโทเค็นมากไปน้อย
        self.assertEqual(len(r["proj"]), len(set(r["proj"])))

    def test_slots_stable_between_ranges(self):
        d7, d30 = fake_usage(7, datetime.date(2026, 10, 6)), fake_usage(30, datetime.date(2026, 10, 6))
        r = self.node("var a = b3Usage(%s, {days: 7, models: %s}), b = b3Usage(%s, {days: 30, models: %s});"
                      "function m(M) { var o = {}; M.series.forEach(function (s) { o[s.model] = s.slot; }); return o; }"
                      "out([m(a), m(b), b.days.length]);" % (json.dumps(d7), json.dumps(MODELS), json.dumps(d30), json.dumps(MODELS)))
        for k, v in r[0].items():
            self.assertEqual(r[1][k], v, k)
        self.assertEqual(r[2], 30)

    def test_other_shapes(self):
        r = self.node(r"""
var nested = {days: 7, to: '2026-10-06', by_day: {'2026-10-06': {models: {'A-Q4_K_M': {prompt_tokens: 5, completion_tokens: 5, gen_tps: 10},
  'B': {prompt_tokens: 1, completion_tokens: 0}}}, '2026-10-05': {models: [{model: 'A-Q4_K_M', prompt: 2, completion: 2, gen_tps: 30}]}}};
var a = b3Usage(nested, {days: 7});
var flat = {days: 7, to: '2026-10-06', rows: [{date: '2026-10-06', model: 'X', prompt_tokens: 10, completion_tokens: 10, requests: 2}],
  per_project: {p1: {prompt_tokens: 3, completion_tokens: 3, requests: 1}, p2: {prompt_tokens: 30, completion_tokens: 3, requests: 1}}};
var b = b3Usage(flat, {days: 7});
var recOnly = {sessions: [{ts: '2026-10-06T10:00:00+07:00', model: 'Y', project: 'q', prompt_tokens: 3, completion_tokens: 4,
  error: true, compacted: 9}]};
var c = b3Usage(recOnly, {days: 7, today: '2026-10-06'});
var many = {days: 1, to: '2026-10-06', per_day: ['m1','m2','m3','m4','m5','m6','m7'].map(function (m, i) {
  return {day: '2026-10-06', model: m, prompt_tokens: 10 + i, completion_tokens: 0}; })};
var e = b3Usage(many, {days: 1});
out({a: a.series.map(function (s) { return [s.model, s.tokens.slice(-2), s.tps.slice(-2), Math.round(s.avgTps * 100) / 100]; }),
  b: [b.projects.map(function (p) { return p.project; }), b.totals.requests],
  c: [c.totals, c.recent[0].isCompacted, c.recent[0].turns, c.recent[0].isError],
  e: [e.series.map(function (s) { return s.slot; }), e.stack.map(function (s) { return s.model; }), e.stack[5].tokens, e.stack[5].names],
  empty: [b3Usage({}, {days: 7}).empty, b3Usage(null, {days: 30}).days.length, b3Usage({per_day: 'x', recent: 5}, {days: 7}).empty]});
""")
        self.assertEqual(r["a"][0][0], "A-Q4_K_M")
        self.assertEqual(r["a"][0][1], [4, 10])
        self.assertEqual(r["a"][0][2], [30, 10])
        # ค่าเฉลี่ย = โทเค็นรวม ÷ เวลารวม (สูตรเดียวกับ hub_usage._done): 7 / (5/10 + 2/30) — ไม่ใช่เฉลี่ยเลข tok/s ตรงๆ
        self.assertAlmostEqual(r["a"][0][3], round(7 / (5 / 10 + 2 / 30), 2), places=2)
        self.assertEqual(r["a"][1][2], [None, None], "ไม่มีความเร็ว = null ไม่ใช่ 0")
        self.assertEqual(r["b"], [["p2", "p1"], 2])
        self.assertEqual(r["c"][0]["requests"], 1)
        self.assertEqual(r["c"][0]["errors"], 1)
        self.assertEqual(r["c"][0]["compacted"], 1, "บรรทัดดิบที่ย่อ 9 รอบ = นับเป็น 1 ครั้ง")
        self.assertEqual(r["c"][1:], [True, 9, True])
        self.assertEqual(r["e"][0], [0, 1, 2, 3, 4, -1, -1])
        self.assertEqual(r["e"][1], ["m1", "m2", "m3", "m4", "m5", "*"], "เกิน 5 สี = รวมเป็นอื่นๆ ไม่สร้างสีใหม่")
        self.assertEqual(r["e"][2], [31])
        self.assertEqual(r["e"][3], ["m6", "m7"])
        self.assertEqual(r["empty"], [True, 30, True])

    def test_number_helpers(self):
        r = self.node(r"""
var u = {ms: '%s ms', s: '%s s', min: '%s min', h: '%s h'};
out({ticks: [b3Ticks(0), b3Ticks(7), b3Ticks(12345, 4), b3Ticks(0.9, 2), b3Ticks(28.4, 2)],
  fmt: [b3Fmt(12345, 'th'), b3Fmt(1234567, 'en'), b3Fmt(123456, 'en'), b3Fmt(5.25, 'th'), b3Fmt(1234, 'en', 0, true)],
  dur: [b3Dur(0, u), b3Dur(0.4, u), b3Dur(4.25, u), b3Dur(200, u), b3Dur(7300, u)],
  bytes: [b3Bytes(6141 * 1048576), b3Bytes(500e9), b3Bytes(17.3 * 1073741824), b3Bytes(5e6)],
  size: [b3SizeOf({free_gb: 41.2}, 'free'), b3SizeOf({total_mb: 6141}, 'total'), b3SizeOf({total: 6141}, 'total'),
    b3SizeOf({total: 476}, 'total'), b3SizeOf({total: 5e11}, 'total'), b3SizeOf({}, 'total')],
  short: [b3Short('Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL'), b3Short('gpt-oss-20b-MXFP4'), b3Short('Qwen3.8-27B-UD-Q4_K_M'), b3Short('x')],
  days: b3Days(3, '2026-03-01')});
""")
        self.assertEqual(r["ticks"], [[0, 1], [0, 2, 4, 6, 8], [0, 5000, 10000, 15000], [0, 0.5, 1], [0, 20, 40]])
        self.assertEqual(r["fmt"], ["12.3K", "1.2M", "123K", "5.3", "1,234"])
        self.assertEqual(r["dur"], ["", "400 ms", "4.3 s", "3 min", "2 h 2 min"])
        self.assertEqual(r["bytes"], ["6 GB", "466 GB", "17.3 GB", "4.8 MB"])
        self.assertEqual(r["size"][0], 41.2 * 1073741824)
        self.assertEqual(r["size"][1:5], [6141 * 1048576, 6141 * 1048576, 476 * 1073741824, 5e11])
        self.assertIsNone(r["size"][5])
        self.assertEqual(r["short"], ["Qwen3-Coder-30B-A3B-Instruct", "gpt-oss-20b", "Qwen3.8-27B", "x"])
        self.assertEqual(r["days"], ["2026-02-27", "2026-02-28", "2026-03-01"])

    def test_doctor_shapes_and_secrets(self):
        d = fake_doctor()
        r = self.node(r"""
var N = b3Doctor(%s, 'th'), E = b3Doctor(%s, 'en');
var obj = b3Doctor({services: {router: true, 'mcp-local': {ok: false, port: 8792}, x: {status: 'loading'}},
  hub: {state: 'ok', ports: [8101, 8102]}, fixes: {th: ['แก้ ก'], en: ['fix a']}, gpu: {available: false, reason: 'nvidia-smi not found'},
  memory: {ram: {total_gb: 32, free_gb: 8}, commit: {limit_gb: 64, available_gb: 20}}, disks: {C: {total_gb: 100, free_gb: 5}, E: {present: false}},
  secrets: [{name: 'C:\\LLM\\secrets\\a.token', present: 'yes'}, {file: 'b.key', exists: false}], docker: true,
  api_key: 'sk-123', my_token: true, weird: {nested: {password: 'p4ss'}}, unknown_thing: 42}, 'en');
var u = {ms: '%%s ms', s: '%%s s', min: '%%s min', h: '%%s h'};
var rep = b3Report(N, function (k) { return k; }, 'th', u);
out({svc: N.services.map(function (s) { return [s.kind, s.state, s.port, s.latency]; }), issues: N.issues, bad: N.bad,
  fixesTh: N.fixes.map(function (f) { return [f.text, f.level]; }), fixesEn: E.fixes.map(function (f) { return f.text; }),
  keys: N.keys, gpus: N.gpus.length, mem: N.mem.map(function (m) { return m.kind; }), disks: N.disks.map(function (k) { return k.drive; }),
  errs: N.errors, tests: N.tests, json: JSON.stringify(N), rep: rep,
  obj: {svc: obj.services.map(function (s) { return [s.kind || s.id, s.state]; }), fixes: obj.fixes.map(function (f) { return f.text; }),
    gpuReason: obj.gpuReason, mem: obj.mem, disks: obj.disks, keys: obj.keys, docker: obj.docker, extra: obj.extra}});
""" % (json.dumps(d), json.dumps(d)))
        self.assertEqual([s[0] for s in r["svc"]], ["router", "mcp", "web", "embed", "stt", "sched", "gateway", "hub"])
        self.assertEqual(dict((s[0], s[1]) for s in r["svc"])["stt"], "bad")
        self.assertEqual(dict((s[0], s[1]) for s in r["svc"])["hub"], "ok")
        # บริการล่ม 1 + ดิสก์เหลือน้อย (คำแนะนำที่ไม่ใช่บริการ) = 2 ปัญหา ไม่นับซ้ำกับคำแนะนำของบริการที่ล่ม
        self.assertEqual((r["issues"], r["bad"]), (2, True))
        self.assertEqual(r["fixesTh"][0][1], "bad")
        self.assertIn("launcher -RestartStt", r["fixesTh"][0][0])
        self.assertTrue(THAI.search(r["fixesTh"][0][0]))
        self.assertFalse(THAI.search(r["fixesEn"][0]))
        self.assertEqual(r["keys"], [{"name": "local-services.token", "present": True}, {"name": "router.key", "present": True},
                                     {"name": "brave-search.key", "present": False}])
        # ค่าลับไม่อยู่ในผลที่ใช้วาดหน้า และไม่อยู่ในรายงานที่คัดลอก
        self.assertNotIn(SECRET, r["json"])
        self.assertNotIn(SECRET, r["rep"])
        self.assertNotIn("\u2060", r["rep"])
        for e in r["errs"]:
            self.assertNotIn(SECRET, e["text"])
        self.assertEqual(r["errs"][0]["file"], "stt.err.log", "แสดงแค่ชื่อไฟล์ ไม่ใช่ path เต็ม")
        for sec in ("[b3_doc_svc]", "[b3_doc_fixes]", "[b3_doc_machine]", "[b3_doc_soft]", "[b3_doc_errors]"):
            self.assertIn(sec, r["rep"])
        self.assertIn("- local-services.token — b3_doc_present", r["rep"])
        self.assertIn("Qwen3.8-27B-UD-Q4_K_M.gguf", r["rep"])
        self.assertEqual(r["tests"]["passed"], 1393)
        o = r["obj"]
        self.assertEqual(o["svc"], [["router", "ok"], ["mcp", "bad"], ["hub", "ok"], ["x", "warn"]])
        self.assertEqual(o["fixes"], ["fix a"])
        self.assertEqual(o["gpuReason"], "nvidia-smi not found")
        self.assertEqual(o["mem"], [{"kind": "ram", "total": 32 * 1073741824, "free": 8 * 1073741824, "level": ""},
                                    {"kind": "commit", "total": 64 * 1073741824, "free": 20 * 1073741824, "level": ""}])
        self.assertEqual([(x["drive"], x["missing"]) for x in o["disks"]], [("C:", False), ("E:", True)])
        # hub ส่งรายการคำแนะนำมา (ไม่มีเรื่องดิสก์) = hub ตัดสินแล้วว่าดิสก์ปกติ — C: ว่าง 5 GB ก็ไม่ขึ้น "เหลือน้อย" เอง
        self.assertEqual([x["level"] for x in o["disks"]], ["", ""])
        self.assertEqual(o["keys"], [{"name": "a.token", "present": True}, {"name": "b.key", "present": False}])
        self.assertEqual(o["docker"], {"ok": True, "reason": ""})
        extra = dict(o["extra"])
        self.assertEqual(extra["api_key"], {"yes": True})
        self.assertEqual(extra["my_token"], {"yes": True})
        self.assertNotIn("p4ss", extra["weird"]["text"])
        self.assertEqual(extra["unknown_thing"], {"text": "42"})

    def test_real_hub_usage_shape(self):
        """ผลของ hub_usage.aggregate ตัวจริง → ตัวเลขบนหน้าตรงกับของ hub (รวม, รายโมเดล tok/s, รายโปรเจกต์ + ชื่อ)"""
        now = datetime.datetime(2026, 10, 6, 21, 15, tzinfo=datetime.timezone(datetime.timedelta(hours=7)))
        d = real_usage(7, now=now)
        r = self.node("var d = %s; var M = b3Usage(d, {days: 7, models: %s});"
                      "out({days: M.days, tot: M.totals, series: M.series.map(function (s) { return [s.model, s.slot, s.total, s.avgTps, s.avgPtps,"
                      " s.tps.filter(function (x) { return x == null; }).length]; }),"
                      " proj: M.projects.map(function (p) { return [p.project, p.name, p.tokens, p.requests]; }),"
                      " recent: M.recent.length, r0: M.recent[0], empty: M.empty});" % (json.dumps(d), json.dumps(MODELS)))
        self.assertEqual(r["days"], [x["date"] for x in d["per_day"]])
        t = d["totals"]
        self.assertEqual((r["tot"]["requests"], r["tot"]["prompt"], r["tot"]["cached"], r["tot"]["completion"],
                          r["tot"]["errors"], r["tot"]["compacted"]),
                         (t["requests"], t["prompt_tokens"], t["cached_tokens"], t["completion_tokens"], t["errors"], t["compacted"]))
        hub_models = {m["model"]: m for m in d["per_model"]}
        self.assertEqual(sorted(s[0] for s in r["series"]), sorted(hub_models))
        for model, slot, total, avg, pavg, gaps in r["series"]:
            self.assertEqual(slot, MODELS.index(model))
            self.assertEqual(total, hub_models[model]["total_tokens"])
            # ความเร็วเฉลี่ยของหน้า (รวมจากรายวัน) = ของ hub (รวมทั้งช่วง) — สูตรเดียวกัน
            self.assertAlmostEqual(avg, hub_models[model]["gen_tps"], delta=0.02)
            self.assertAlmostEqual(pavg, hub_models[model]["prompt_tps"], delta=0.2)
            self.assertGreaterEqual(gaps, 1, "วันที่ไม่มีข้อมูล = null (เส้นขาด)")
        self.assertEqual([p[0] for p in r["proj"]], [p["project"] for p in d["per_project"]])
        self.assertEqual(r["proj"][0][1], dict(PROJECTS)[r["proj"][0][0]], "ชื่อโปรเจกต์จาก hub ใช้ได้เมื่อไม่อยู่ใน /api/projects")
        self.assertEqual(r["recent"], min(50, len(d["recent"])))
        self.assertTrue(r["r0"]["t"] > 0 and r["r0"]["name"])
        self.assertFalse(r["empty"])
        empty = real_usage(7, rows=[], now=now)
        self.assertTrue(self.node("out(b3Usage(%s, {days: 7}).empty)" % json.dumps(empty)))

    def test_real_hub_doctor_shape(self):
        """ผลของ hub_doctor ตัวจริง (_build + localize) → บริการ 8 แถวตามลำดับ, ระดับคำแนะนำ, ไฟล์คีย์, ไม่มีค่าลับ"""
        with tempfile.TemporaryDirectory(prefix="b3ui-doc-") as tmp:
            sick, well = real_doctor(tmp, "th"), real_doctor(tmp, "en", sick=False)
        self.assertNotIn(SECRET, json.dumps(sick, ensure_ascii=False))
        r = self.node(r"""
var N = b3Doctor(%s, 'th'), W = b3Doctor(%s, 'en');
var u = {ms: '%%s ms', s: '%%s s', min: '%%s min', h: '%%s h'};
function brief(N) { return {svc: N.services.map(function (s) { return [s.kind, s.state, s.raw, s.port, s.loaded, s.age, s.busy, s.provider, s.device,
  s.ports ? s.ports.length : null, s.upstreamOk]; }), fixes: N.fixes.map(function (f) { return [f.id, f.level]; }), issues: N.issues, tips: N.tips,
  overall: N.overall, keys: N.keys, brave: N.brave, docker: N.docker, gpus: N.gpus, mem: N.mem, disks: N.disks.map(function (k) { return [k.drive, k.missing]; }),
  models: N.models, versions: N.versions, tests: N.tests, errors: N.errors, extra: N.extra.map(function (x) { return x[0]; })}; }
out({n: brief(N), w: brief(W), rep: b3Report(N, function (k) { return k; }, 'th', u), json: JSON.stringify(N)});
""" % (json.dumps(sick), json.dumps(well)))
        n, w = r["n"], r["w"]
        self.assertEqual([s[0] for s in n["svc"]], ["router", "mcp", "web", "embed", "stt", "sched", "gateway", "hub"])
        svc = {s[0]: s for s in n["svc"]}
        self.assertEqual(svc["router"][4], ["Qwen3-4B-Instruct-2507"])
        self.assertEqual((svc["stt"][1], svc["stt"][2]), ("bad", "down"))
        self.assertEqual(svc["sched"][5], 1260)
        self.assertEqual((svc["hub"][6], svc["hub"][9]), (1, 5))
        self.assertEqual(svc["web"][7], "builtin")
        self.assertTrue(svc["gateway"][10])
        self.assertEqual({s[0]: s[8] for s in w["svc"]}["stt"], "GPU")
        # ระดับจาก id ของ hub: STT ล่ม = bad ขึ้นก่อน, ดิสก์/เทสต์ = warn, Brave/Docker (รอผู้ใช้ทำเอง) = info ไปท้าย
        self.assertEqual(n["fixes"][0], ["stt", "bad"])
        self.assertEqual([f for f in n["fixes"] if f[1] == "info"], [["brave", "info"], ["docker", "info"]])
        self.assertEqual(n["fixes"][-2:], [["brave", "info"], ["docker", "info"]])
        self.assertIn(["disk", "warn"], n["fixes"])
        self.assertIn(["tests", "warn"], n["fixes"])
        self.assertEqual((n["issues"], n["tips"], n["overall"]), (3, 2, "bad"))
        # ระบบปกติ: hub บอก overall=warn เพราะมีคำแนะนำ Brave/Docker — หน้าเป็นสีเขียว + "มีคำแนะนำ 2 ข้อ"
        self.assertEqual((w["issues"], w["tips"], w["overall"]), (0, 2, "ok"))
        self.assertEqual([k["name"] for k in n["keys"]], ["local_token", "brave_key", "gateway_key"])
        self.assertEqual([k["present"] for k in n["keys"]], [True, False, False])
        self.assertFalse(n["brave"])
        self.assertEqual(n["docker"]["ok"], False)
        self.assertIn("engine", w["docker"]["reason"])
        self.assertTrue(THAI.search(n["docker"]["reason"]))
        self.assertEqual(n["gpus"][0]["total"], 6141 * 1048576)
        self.assertEqual([m["kind"] for m in n["mem"]], ["ram", "commit"])
        self.assertAlmostEqual(n["mem"][1]["free"], 26.7 * 1073741824, delta=1)
        self.assertEqual(n["disks"], [["C:", False], ["D:", False], ["E:", False]])
        self.assertEqual([m["name"] for m in n["models"]], [m + ".gguf" for m in MODELS])
        self.assertEqual(dict(n["versions"])["llama_cpp"], "b10984-0c7d9b0")
        self.assertEqual((n["tests"]["passed"], n["tests"]["failed"], n["tests"]["skipped"]), (1392, 1, 38))
        self.assertEqual([e["file"] for e in n["errors"]], ["stt.err.log", "hub.err.log"])
        self.assertEqual(n["extra"], [], "ทุกคีย์ระดับบนของ hub_doctor มีที่แสดงแล้ว (ไม่ตกไปกล่อง 'ข้อมูลอื่น')")
        for blob in (r["rep"], r["json"]):
            self.assertNotIn(SECRET, blob)
        self.assertIn("- local_token — b3_doc_present", r["rep"])

    def test_meter_levels_follow_hub(self):
        """สีของแถบดิสก์/commit = คำตัดสินของ hub ไม่ใช่ % ที่ว่างที่หน้าคิดเอง (integ b3 2026-10-06: C: 26.2 GB (5.5%) กับ
        E: 11.5 GB ขึ้นแดง "เหลือน้อย" ทั้งที่ hub_doctor ไม่มีคำแนะนำเรื่องดิสก์และสรุป overall=ok)"""
        low_c = [dict(LIVE_DISKS[0], free_gb=8.4)] + LIVE_DISKS[1:]
        with tempfile.TemporaryDirectory(prefix="b3ui-lv-") as tmp:
            well = real_doctor(tmp, "th", sick=False, disks=LIVE_DISKS)
            low = real_doctor(tmp, "en", sick=False, disks=low_c)
        # สมมุติฐานจาก hub ตัวจริง: ชุดแรกไม่มีคำแนะนำเรื่องดิสก์ (ปกติ), ชุดที่สองมีของ C: (ต่ำกว่า DISK_LOW_GB)
        self.assertEqual(well["overall"], "ok")
        self.assertNotIn("disk", [f["id"] for f in well["fixes"]])
        self.assertEqual([f["id"] for f in low["fixes"] if f["id"] == "disk"], ["disk"])
        r = self.node(r"""
function lv(N) { return {disks: N.disks.map(function (k) { return [k.drive, k.level]; }), mem: N.mem.map(function (m) { return [m.kind, m.level]; }),
  keys: N.disks.map(function (k) { return Object.keys(k).sort().join(','); })}; }
var u = {ms: '%%s ms', s: '%%s s', min: '%%s min', h: '%%s h'}, id = function (k) { return k; };
var W = b3Doctor(%s, 'th'), L = b3Doctor(%s, 'en'), F = b3Doctor(%s, 'th');
var hubLevel = b3Doctor({fixes: [], disks: [{drive: 'C:', free_gb: 100, total_gb: 200, level: 'error'},
  {drive: 'D:', free_gb: 1, total_gb: 900, low: false}, {drive: 'E:', free_gb: 50, total_gb: 60, low: true}]}, 'en');
var noFixes = b3Doctor({disks: [{drive: 'C:', free_gb: 9.9, total_gb: 476}, {drive: 'E:', free_gb: 11.5, total_gb: 229},
  {drive: 'F:', present: false}], memory: {ram_total_gb: 32, ram_free_gb: 0.5, commit_limit_gb: 64, commit_free_gb: 6}}, 'th');
var sev = b3Doctor({fixes: [{id: 'disk', severity: 'error', th: 'ดิสก์ E: เหลือ 1.0 GB → ลบไฟล์ (C: pagefile คืนพื้นที่ได้)',
    en: 'Drive E: has 1.0 GB free → free up space (C: pagefile shrinks back)'},
  {id: 'commit', severity: 'warn', th: 'หน่วยความจำ commit เหลือ 6.0 GB', en: 'Only 6.0 GB of commit memory is free'},
  {id: 'brave', severity: 'info', th: 'ยังไม่มี Brave key วางที่ C:\\LLM\\secrets\\brave-search.key', en: 'put it at C:\\LLM\\secrets\\brave-search.key'},
  {th: 'Docker ใช้ไม่ได้ ดู log ที่ D:\\docker', en: 'Docker unusable, see D:\\docker'}],
  disks: [{drive: 'C:', free_gb: 20, total_gb: 476}, {drive: 'D:', free_gb: 5, total_gb: 900}, {drive: 'E:', free_gb: 1, total_gb: 229}],
  memory: {ram_total_gb: 32, ram_free_gb: 1, commit_limit_gb: 64, commit_free_gb: 6}}, 'en');
out({w: lv(W), l: lv(L), f: lv(F), hub: lv(hubLevel), nofix: lv(noFixes), sev: lv(sev),
  repW: b3Report(W, id, 'th', u), repL: b3Report(L, id, 'en', u),
  drive: [b3FixDrive('Drive E: has 9.5 GB free → free up space or reboot (C: pagefile shrinks back ~20 GB)'),
    b3FixDrive('ดิสก์ C: เหลือน้อย (ต่ำกว่า 10%%) — ย้าย cache ไป D: หรือ E:'), b3FixDrive('วาง key เองที่ C:\\LLM\\secrets\\brave-search.key'),
    b3FixDrive('(E:)'), b3FixDrive('ABC: x'), b3FixDrive('')]});
""" % (json.dumps(well), json.dumps(low), json.dumps(fake_doctor())))
        # เครื่องจริงตอนตรวจรับ: % ที่ว่างต่ำแต่ hub บอกปกติ → ไม่มีแถบสี/คำ "เหลือน้อย" เลย
        self.assertEqual(r["w"]["disks"], [["C:", ""], ["D:", ""], ["E:", ""]])
        self.assertEqual(r["w"]["mem"], [["ram", ""], ["commit", ""]])
        self.assertNotIn("b3_doc_low", r["repW"])
        self.assertNotIn("hubLevel", r["w"]["keys"][0], "ค่าระหว่างทางไม่หลุดไปในผลที่ใช้วาดหน้า")
        # hub มีคำแนะนำเรื่อง C: (ระดับ warn) → C: อำพันตัวเดียว ไม่ใช่แดง และรายงานที่คัดลอกบอก "เหลือน้อย" ตรงกัน
        self.assertEqual(r["l"]["disks"], [["C:", "warn"], ["D:", ""], ["E:", ""]])
        self.assertEqual(r["repL"].count("b3_doc_low"), 1)
        # คำแนะนำแบบไม่มี id ("ดิสก์ C: … ย้ายไป D: หรือ E:") = C: เท่านั้น
        self.assertEqual(r["f"]["disks"], [["C:", "warn"], ["D:", ""], ["E:", ""]])
        # ระดับต่อแถวที่ hub ใส่มาเองชนะ (แม้ % ที่ว่างจะบอกตรงข้าม)
        self.assertEqual(r["hub"]["disks"], [["C:", "bad"], ["D:", ""], ["E:", "warn"]])
        # hub ไม่ได้ส่งรายการคำแนะนำมาเลย → เกณฑ์เดียวกับ hub_doctor (10 GB / commit 8 GB) เป็นอำพัน ไม่แดงเองแม้เหลือ 2%
        self.assertEqual(r["nofix"]["disks"], [["C:", "warn"], ["E:", ""], ["F:", ""]])
        self.assertEqual(r["nofix"]["mem"], [["ram", ""], ["commit", "warn"]])
        # ระดับของคำแนะนำ: disk error → แดง เฉพาะไดรฟ์ที่พูดถึง (ไม่ใช่ C: ในวงเล็บ), path ในคำแนะนำอื่นไม่นับเป็นดิสก์
        self.assertEqual(r["sev"]["disks"], [["C:", ""], ["D:", ""], ["E:", "bad"]])
        self.assertEqual(r["sev"]["mem"], [["ram", ""], ["commit", "warn"]])
        self.assertEqual(r["drive"], ["E:", "C:", "", "E:", "", ""])

    def test_scrub(self):
        r = self.node(r"""
out([b3Scrub('Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL C:\\LLM\\models\\Qwen3.8-27B-UD-Q4_K_M.gguf mmproj-Qwen3.8-27B-F16 2026-10-06T16:10:05+07:00'),
  b3Scrub('Authorization: Bearer abcDEF123ghi'), b3Scrub('bearer xyz'), b3Scrub('token=abc123; api_key: "k-9"'),
  b3Scrub('sha 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08 end'),
  b3Scrub('tok Ab3dEf8hIjKlMnOpQrStUvWxYz0123456789_-xyz end'), b3Scrub('mail me@example.com'),
  b3Scrub('http://127.0.0.1:8792/review/p?token=abc&x=1'), b3Scrub(null)]);
""")
        self.assertEqual(r[0], "Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL C:\\LLM\\models\\Qwen3.8-27B-UD-Q4_K_M.gguf "
                               "mmproj-Qwen3.8-27B-F16 2026-10-06T16:10:05+07:00")
        self.assertEqual(r[1], "Authorization: Bearer ***")
        self.assertEqual(r[2], "bearer ***")
        self.assertEqual(r[3], 'token=***; api_key: "***"')
        self.assertEqual(r[4], "sha *** end")
        self.assertEqual(r[5], "tok *** end")
        self.assertEqual(r[6], "mail ***@***")
        self.assertEqual(r[7], "http://127.0.0.1:8792/review/p?token=***&x=1")
        self.assertEqual(r[8], "")


# ------------------------------------------------------------------------------------------------ enhance.js
class EnhanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(ENH)
        a = cls.src.index(B3_ENH_START)
        cls.sec = cls.src[cls.src.rindex("/*", 0, a):]

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_syntax(self):
        r = subprocess.run([NODE, "--check", ENH], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_position_and_hooks(self):
        s = self.src
        a = s.index(B3_ENH_START)
        # หลัง "เริ่มทำงาน" — ไม่ปนกับช่วงที่เทสต์รอบก่อนตัดไปตรวจ (รอบ 4 … API, batch 2b … เริ่มทำงาน)
        self.assertLess(s.index("\n  /* ---- เริ่มทำงาน"), a)
        self.assertTrue(s.rstrip().endswith("})();"))
        ex = js_function(s, "extrasPass")
        self.assertIn("try { b3Pass(r); } catch (e) {}", ex)
        self.assertIn("window.qwenEnhance.compaction = function", self.sec)
        self.assertIn("var B3C_READY = true;", self.sec)
        self.assertIn("if (!B3C_READY) return;", js_function(self.sec, "b3Pass"))

    def test_fetch_wrapper_reads_headers_only(self):
        sec = self.sec
        for bad in ("http://", "https://", "XMLHttpRequest", "WebSocket(", "sendBeacon", "eval(", "Claude", "Anthropic",
                    "insertAdjacentHTML", "document.write", ".clone(", ".text(", ".json(", "getReader", ".body"):
            self.assertNotIn(bad, sec, bad)
        self.assertEqual(re.findall(r"\bfetch\(", sec), [], "ส่วนนี้ไม่เรียกเครือข่ายเอง")
        wrap = sec[sec.index("window.fetch = function (input, init) {"):]
        wrap = wrap[:wrap.index("\n    };\n")]
        self.assertIn("var p = b3cInner.apply(window, arguments);", wrap)
        self.assertEqual(wrap.count("return p;"), 2, "คืน Promise ตัวเดิมเสมอ")
        self.assertIn("function () {});", wrap, "กิ่งข้างจัดการ reject ของตัวเอง")
        for line in sec.splitlines():
            if ".innerHTML" in line:
                self.assertRegex(line, r"\.innerHTML = xIcon\(", line.strip())
        self.assertIn('B3C_KEY = "qwen-compact"', sec)
        self.assertIn('B3C_HDR = "X-Qwen-Compacted"', sec)

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_every_label_has_thai(self):
        blk = self.sec[self.sec.index("var TH_B3 = {"):]
        blk = blk[:blk.index("\n  };\n") + 5]
        th = run_node(blk.replace("var TH_B3 =", "const TH_B3 =", 1) + "\nconsole.log(JSON.stringify(TH_B3));")
        used = set(re.findall(r'\b(?:L3|A3)\(\s*"([^"]+)"\s*\)', self.sec))
        self.assertEqual(len(used), 3)
        self.assertEqual(sorted(used), sorted(th))
        for en, tx in th.items():
            self.assertRegex(tx, THAI, en)
            for ph in re.findall(r"\{[a-z]+\}", en):
                self.assertIn(ph, tx, (en, ph))
        # ถ้อยคำตามสัญญา D4: "สรุปช่วงต้นของบทสนทนาแล้ว (n รอบ)"
        self.assertEqual(th["Earlier part of this chat summarized ({n} turns)"], "สรุปช่วงต้นของบทสนทนาแล้ว ({n} รอบ)")

    @unittest.skipUnless(HAVE_NODE, "ไม่มี node")
    def test_pure_functions(self):
        fns = "\n".join(js_function(self.src, n) for n in ("planConv",)) + "\n" + "\n".join(
            js_function(self.sec, n) for n in ("b3cLoad", "b3cSave", "b3cTurns", "b3cConvOf", "b3cNote"))
        code = r"""
var location = {href: "http://127.0.0.1:8103/?ui=1", origin: "http://127.0.0.1:8103"};
var B3C_KEY = "qwen-compact", B3C_MAX = 3, B3C_HDR = "X-Qwen-Compacted", store = {}, said = [], sched = 0, R = {name: "chat", id: "c1"};
function lsGet(k) { return store[k] == null ? null : store[k]; }
function lsSet(k, v) { store[k] = v; }
function route() { return R; }
function b2Say(m) { said.push(m); }
function A3(s) { return s; }
function schedule() { sched++; }
""" + fns + r"""
var b3cState = {};
function res(h, ok) { return {ok: ok !== false, headers: new Headers(h || {})}; }
var out = {};
out.turns = [b3cTurns("12"), b3cTurns(" 7 "), b3cTurns("0"), b3cTurns("x"), b3cTurns(""), b3cTurns(null), b3cTurns("1e3"), b3cTurns("-3")];
var post = {method: "POST", headers: {"X-Conversation-Id": "c1::m"}};
out.conv = [b3cConvOf("./v1/chat/completions", post), b3cConvOf("./v1/chat/completions", {method: "POST"}),
  b3cConvOf("./v1/chat/completions", {headers: {"X-Conversation-Id": "c1::m"}}), b3cConvOf("/v1/completions", post),
  b3cConvOf("http://evil.example/v1/chat/completions", post), b3cConvOf("./v1/chat/completions/x", post),
  b3cConvOf(new Request("http://127.0.0.1:8103/v1/chat/completions", {method: "POST", headers: {"X-Conversation-Id": "c9::m"}})),
  b3cConvOf(42, post)];
b3cNote("c1", res({"X-Qwen-Compacted": "12"}));
out.a = JSON.parse(JSON.stringify(b3cState)); out.said = said.slice(); out.sched = sched;
b3cNote("c1", res({"X-Qwen-Compacted": "12"}));      // ซ้ำค่าเดิม = ไม่เขียน/ไม่ประกาศซ้ำ
out.sched2 = sched;
b3cNote("c1", res({"X-Qwen-Compacted": "15"}));
out.b = b3cState.c1.n; out.said2 = said.length;
b3cNote("", res({}));                                  // ไม่มี id + ไม่มี header = ไม่แตะ
out.c = !!b3cState.c1;
b3cNote("c1", res({}, false));                         // คำขอผิดพลาด = ไม่แตะ
out.d = !!b3cState.c1;
b3cNote("c1", res({}));                                // แชตเดิมตอบโดยไม่มี header = ไม่ได้ย่อแล้ว → ลบ
out.e = !!b3cState.c1;
b3cNote("", res({"X-Qwen-Compacted": "4"}));           // pre-encode (ไม่มี id) ตั้งให้แชตที่เปิดอยู่ได้
out.f = b3cState.c1 && b3cState.c1.n;
R = {name: "start", id: null};
b3cNote("", res({"X-Qwen-Compacted": "4"}));
b3cNote("zz", res({"X-Qwen-Compacted": "3"})); b3cNote("yy", res({"X-Qwen-Compacted": "3"})); b3cNote("xx", res({"X-Qwen-Compacted": "3"}));
out.g = Object.keys(JSON.parse(store["qwen-compact"])).sort();
store["qwen-compact"] = JSON.stringify({ok: {n: 3, at: 1}, bad1: {n: -1}, bad2: {n: "x"}, bad3: 7, "": {n: 2}, big: {n: 1e9}});
out.load = b3cLoad();
store["qwen-compact"] = "{not json";
out.load2 = b3cLoad();
console.log(JSON.stringify(out));
"""
        r = run_node(code)
        self.assertEqual(r["turns"], [12, 7, 0, 0, 0, 0, 0, 0])
        self.assertEqual(r["conv"], ["c1", "", None, None, None, None, "c9", None])
        self.assertEqual(r["a"]["c1"]["n"], 12)
        self.assertEqual(len(r["said"]), 1, "ประกาศครั้งแรกที่แชตที่เปิดอยู่ถูกย่อ")
        self.assertEqual(r["sched2"], r["sched"])
        self.assertEqual((r["b"], r["said2"]), (15, 1))
        self.assertTrue(r["c"])
        self.assertTrue(r["d"])
        self.assertFalse(r["e"])
        self.assertEqual(r["f"], 4)
        self.assertEqual(r["g"], ["xx", "yy", "zz"], "เก็บไม่เกิน B3C_MAX แชต ทิ้งของเก่าสุดก่อน")
        self.assertEqual(r["load"], {"ok": {"n": 3, "at": 1}})
        self.assertEqual(r["load2"], {})


class ThemeTests(unittest.TestCase):
    def test_section_13(self):
        with open(CSS, "rb") as fh:
            raw = fh.read()
        self.assertNotIn(b"\r\n", raw)
        css = raw.decode("utf-8")
        sec = css[css.index("13. batch 3 (2026-10-06, owner ui)"):]
        for sel in (".qw-compact {", ".qw-compact-rule", ".qw-compact-b {", ".qw-compact-b:focus-visible", ".qw-compact-tip {",
                    ".qw-compact-tip[hidden]", "@media (pointer: coarse)", "@media (forced-colors: active)"):
            self.assertIn(sel, sec, sel)
        code = re.sub(r"/\*.*?\*/", "", sec, flags=re.S)
        self.assertNotRegex(code, r"#[0-9a-fA-F]{3,8}\b")
        self.assertNotRegex(code, r"\brgba?\(")
        for prop, val in re.findall(r"(?<![\w-])(color|background-color|border-color)\s*:\s*([^;]+);", code):
            self.assertIn("var(--qw-", val, (prop, val))


# ------------------------------------------------------------------------------------------------ hub สำเนา (E2E/serve)
E2E = os.environ.get("QWEN_B3_E2E") == "1"
# หลังรีบูตบริการจริงยังไม่เปิด — agent ทดสอบเปิด router ชั่วคราวที่ 8199 (ไม่โหลดโมเดล: upstream ปลอมบล็อก GET ที่มี model=)
ROUTER_PORT = int(os.environ.get("QWEN_B3_ROUTER_PORT") or 8099)


def free_ports(n, cands=(8171, 8172, 8173)):
    out = []
    for p in cands:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", p)) != 0:
                out.append(p)
        if len(out) == n:
            return out
    return None


class _Up(BaseHTTPRequestHandler):
    """upstream ปลอม: GET → router จริง (หน้า WebUI) ยกเว้นมี model= ของโมเดลที่ยังไม่โหลด · แชต = SSE ปลอม · POST อื่น 403
    compacted = ค่าที่ใส่ใน header X-Qwen-Compacted ของคำตอบแชต (None = ไม่ใส่) — แทนส่วนที่ hub (D1) จะใส่เอง"""
    protocol_version = "HTTP/1.1"
    loaded = set()
    compacted = None
    log = []

    def log_message(self, *a):
        pass

    def _send(self, code, obj, extra=None):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _relay(self, method):
        want = (parse_qs(urlparse(self.path).query).get("model") or [""])[0]
        if want and want not in self.loaded:
            self._send(404, {"error": {"code": 404, "message": "blocked by test"}})
            return
        h = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "connection")}
        c = http.client.HTTPConnection("127.0.0.1", ROUTER_PORT, timeout=60)
        try:
            c.request(method, self.path, headers=h)
            r = c.getresponse()
            data = r.read()
        except OSError:
            self._send(502, {"error": "router"})
            return
        finally:
            c.close()
        self.send_response(r.status)
        for k, v in r.getheaders():
            if k.lower() not in ("content-length", "transfer-encoding", "connection"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(data)

    def do_GET(self):
        self._relay("GET")

    def do_HEAD(self):
        self._relay("HEAD")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if not urlparse(self.path).path.endswith("/chat/completions"):
            self._send(403, {"error": "blocked by test"})
            return
        try:
            doc = json.loads(raw.decode("utf-8"))
        except ValueError:
            doc = {}
        type(self).log.append({k.lower(): v for k, v in self.headers.items() if k.lower() != "authorization"})
        extra = {"X-Qwen-Compacted": str(self.compacted)} if self.compacted is not None else {}
        if not doc.get("stream"):
            self._send(200, {"choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]}, extra)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        for k, v in extra.items():
            self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()
        for piece in ("สรุป", "แล้ว"):
            ev = {"choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}], "model": doc.get("model")}
            self.wfile.write(("data: %s\n\n" % json.dumps(ev, ensure_ascii=False)).encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.05)
        fin = {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "model": doc.get("model"),
               "timings": {"prompt_n": 5, "prompt_ms": 5.0, "predicted_n": 2, "predicted_ms": 80.0, "predicted_per_second": 25.0}}
        self.wfile.write(("data: %s\n\ndata: [DONE]\n\n" % json.dumps(fin)).encode("utf-8"))
        self.wfile.flush()
        self.close_connection = True


class Stub:
    """hub สำเนาใน process นี้: API (หน้าจัดการ + /api/usage|doctor ปลอม) + พอร์ตโปรเจกต์ "uitest" + upstream ปลอม
    mode real = เส้นทางจริงของ hub (/api/usage อ่าน usage.jsonl สังเคราะห์ในโฟลเดอร์ชั่วคราว, /api/doctor = hub_doctor._build
    ของผลตรวจที่จัดไว้ผ่าน localize/กฎ Origin ของ hub จริง — ไม่ถามบริการจริง ไม่อ่าน log จริง)"""
    mode = "ok"            # ok | healthy | empty | unsupported | real | real-healthy

    def __init__(self, lang="th", theme="dark"):
        ports = free_ports(2)
        if not ports:
            raise unittest.SkipTest("พอร์ตสำรอง 8171-8173 ว่างไม่พอ")
        self.api_port, self.port = ports
        sys.path.insert(0, TOOLS)
        sys.path.insert(0, os.path.dirname(HUB))
        spec = importlib.util.spec_from_file_location("hub_b3_ui_e2e", HUB)
        hub = importlib.util.module_from_spec(spec)
        self.tmp = tempfile.mkdtemp(prefix="qwen-b3ui-")
        with mock.patch.object(sys, "argv", ["hub.py", str(self.api_port), "8099"]), \
                mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(self.tmp, "none-profile.json"),
                                             "QWEN_GPU_CHOICE": os.path.join(self.tmp, "none-choice.json")}):
            spec.loader.exec_module(hub)
        self.hub = hub
        data = Path(self.tmp) / "data"
        (data / "uitest").mkdir(parents=True, exist_ok=True)
        store = Path(self.tmp) / "projects.json"
        items = [{"slug": "uitest", "name": "ทดสอบหน้าจอ", "port": self.port, "system_prompt": "", "think": "off",
                  "model": FAST, "extend": False}]
        items += [{"slug": s, "name": n, "port": 8160 + i, "system_prompt": "", "think": "off", "model": FAST, "extend": True}
                  for i, (s, n) in enumerate(PROJECTS[1:])]
        store.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        # บันทึกการใช้งานในรูปที่ hub_usage เขียนจริง (ใช้ในโหมด real — โหมดอื่นตอบ /api/usage ด้วยข้อมูลปลอมของเทสต์)
        with open(data / "usage.jsonl", "w", encoding="utf-8", newline="\n") as fh:
            for r in usage_rows():
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        self.settings = Path(self.tmp) / "settings.json"
        self.set_prefs(lang, theme)
        self.patches = [mock.patch.object(hub, "DATA_ROOT", data), mock.patch.object(hub, "STORE", store),
                        mock.patch.object(hub, "SETTINGS", self.settings),
                        mock.patch.object(hub, "mcp_servers", lambda project, with_auth=True: []),
                        # real-healthy ใช้ดิสก์แบบเครื่องจริงตอนตรวจรับ (% ที่ว่างต่ำแต่ hub บอกปกติ) — หน้าต้องไม่ขึ้น "เหลือน้อย"
                        mock.patch.object(hub, "doctor_report", lambda refresh=False: real_doctor(
                            self.tmp, sick=Stub.mode != "real-healthy", raw=True,
                            disks=LIVE_DISKS if Stub.mode == "real-healthy" else None))]
        if hasattr(hub, "stt_probe"):
            self.patches.append(mock.patch.object(hub, "stt_probe", lambda tok=None: {"state": "ok", "port": 8795, "device": "cpu"}))
        if hasattr(hub, "_mcp_fast_call"):
            self.patches.append(mock.patch.object(hub, "_mcp_fast_call", lambda *a, **k: ("down", "")))
        # integ b3 ให้ hub ทิ้ง X-Qwen-* ที่มาจาก upstream (ถึงหน้าได้แต่ header ของ hub เอง) — header ปลอมของ _Up จึงไม่ผ่านแล้ว
        # _Up.compacted = n จึงแปลว่า "hub ย่อแล้ว n รอบ" (ผลของ compact_chat ไม่เรียกโมเดลสรุป — test_4, ภาพป้ายใน --serve)
        # None = compact_chat ตัวจริงของ hub (test_4b)
        real_cc = hub.compact_chat
        self.patches.append(mock.patch.object(hub, "compact_chat", lambda doc, project, headers: hub._compact.Result(
            applied=True, reason="reused", reused=True, turns=_Up.compacted) if _Up.compacted else real_cc(doc, project, headers)))
        for p in self.patches:
            p.start()
        if os.environ.get("QWEN_PARTS_FILE"):
            for p in (mock.patch.object(hub, "_parts", parts), mock.patch.object(hub, "_parts_mtime", Path(PARTS).stat().st_mtime)):
                p.start()
                self.patches.append(p)
            hub._merge_strings()
        try:
            c = http.client.HTTPConnection("127.0.0.1", ROUTER_PORT, timeout=10)
            c.request("GET", "/models", headers=hub.router_auth_headers())
            d = json.loads(c.getresponse().read().decode("utf-8"))
            c.close()
            _Up.loaded = {m.get("id") for m in d.get("data") or [] if (m.get("status") or {}).get("value") == "loaded"}
        except (OSError, ValueError):
            _Up.loaded = set()
        self.up = self._serve(("127.0.0.1", 0), _Up)
        p = mock.patch.object(hub, "UPSTREAM_PORT", self.up.server_address[1])
        p.start()
        self.patches.append(p)
        self.proxy = self._serve(("127.0.0.1", self.port), hub.make_proxy_handler("uitest", hub.load_projects))
        stub = self

        class Api(hub.HubHandler):
            """ข้อมูลของสองเส้นทางใหม่มาจากเทสต์เสมอ (ไม่ใช้ของ hub จริงแม้มีแล้ว: ไม่อ่าน log/ไม่ถามบริการจริง)
            กติกา Host/Origin เดิมของ HubHandler ยังทำงานครบ (parse_request ของคลาสแม่)"""

            def do_GET(self):
                path = urlparse(self.path).path.rstrip("/")
                if path in ("/api/usage", "/api/doctor") and not stub.mode.startswith("real"):
                    if stub.mode == "unsupported":
                        self._json(404, {"error": "not found"})
                    elif path == "/api/usage":
                        q = parse_qs(urlparse(self.path).query)
                        days = int((q.get("days") or ["7"])[0]) if (q.get("days") or ["7"])[0].isdigit() else 7
                        self._json(200, {"days": days, "per_day": [], "recent": []} if stub.mode == "empty" else fake_usage(days))
                    else:
                        self._json(200, fake_doctor(stub.mode))
                    return
                super().do_GET()

        self.api = self._serve(("127.0.0.1", self.api_port), Api)

    def set_prefs(self, lang, theme):
        self.settings.write_text(json.dumps({"lang": lang, "theme": theme, "font": "serif"}), encoding="utf-8")

    @staticmethod
    def _serve(addr, handler):
        srv = ThreadingHTTPServer(addr, handler)
        srv.daemon_threads = True
        srv.handle_error = lambda *a: None          # Edge ปิดซ็อกเก็ตเอง = ConnectionReset ไม่ใช่ความผิดพลาด
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv

    def stop(self):
        for srv in (getattr(self, "proxy", None), getattr(self, "api", None), getattr(self, "up", None)):
            if srv:
                srv.shutdown()
                srv.server_close()
        for p in reversed(getattr(self, "patches", [])):
            try:
                p.stop()
            except RuntimeError:
                pass


@unittest.skipUnless(E2E, "E2E ปิดอยู่ (set QWEN_B3_E2E=1)")
class BrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            with socket.create_connection(("127.0.0.1", ROUTER_PORT), timeout=1):
                pass
        except OSError:
            raise unittest.SkipTest("router %d ไม่ได้รันอยู่ (หน้า WebUI มาจาก router)" % ROUTER_PORT)
        cls.stub = Stub("th", "dark")
        sys.path.insert(0, TOOLS)
        import shot  # noqa: E402
        cls.shot = shot
        edge = next((p for p in shot.EDGE_CANDIDATES if os.path.isfile(p)), None)
        if not edge:
            cls.stub.stop()
            raise unittest.SkipTest("ไม่มี Edge")
        cls.dbg = shot.free_port()
        cls.profile = tempfile.mkdtemp(prefix="qwen-shot-")
        cls.proc = subprocess.Popen([edge, "--headless=new", "--disable-gpu", "--no-first-run", "--mute-audio",
                                     "--no-default-browser-check", "--disable-extensions",
                                     "--remote-debugging-port=%d" % cls.dbg, "--user-data-dir=%s" % cls.profile,
                                     "--window-size=1440,900", "about:blank"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(100):
            try:
                tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % cls.dbg, timeout=2).read())
                page = next((t for t in tabs if t.get("type") == "page"), None)
                if page:
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except OSError:
                pass
            time.sleep(0.15)
        cls.ws = shot.WS(ws_url)
        cls.ws.call("Page.enable")
        cls.ws.call("Runtime.enable")
        cls.ws.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        cls.manage = "http://127.0.0.1:%d/?manage=1&lang=th" % cls.stub.api_port
        cls.chat = "http://127.0.0.1:%d/?lang=th" % cls.stub.port

    @classmethod
    def tearDownClass(cls):
        try:
            cls.shot.close_edge(cls.proc, cls.profile)
        finally:
            cls.stub.stop()

    def ev(self, js):
        return self.shot.evaluate(self.ws, js)

    def frame(self, js):
        return self.ev("(async()=>{const w=document.getElementById('frame').contentWindow;return await w.eval(%s)})()" % json.dumps(js))

    def errors(self):
        out = []
        for e in self.ws.events:
            if e["method"] == "Runtime.exceptionThrown":
                d = e["params"]["exceptionDetails"]
                out.append((d.get("exception") or {}).get("description") or d.get("text"))
        return out

    def wait_composer(self):
        # โปรไฟล์ใหม่ทุกครั้ง: WebUI โหลดครั้งแรกช้า (bundle + IndexedDB) — รอปุ่มส่งจริง ไม่ใช่แค่ qwenEnhance
        return self.wait("(()=>{const w=document.getElementById('frame').contentWindow;return !!(w&&w.qwenEnhance&&"
                         "w.document.querySelector('.chat-screen-form-wrapper form button[type=submit]'))})()", 120)

    def wait(self, js, tries=40, step=0.25):
        v = None
        for _ in range(tries):
            v = self.ev(js)
            if v:
                return v
            self.ws.drain(step)
        return v

    def key(self, name, code, vk):
        base = {"key": name, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
        self.ws.call("Input.dispatchKeyEvent", dict(base, type="rawKeyDown"))
        self.ws.call("Input.dispatchKeyEvent", dict(base, type="keyUp"))
        self.ws.drain(0.3)

    def test_1_usage_tab(self):
        Stub.mode = "ok"
        self.ws.events.clear()
        self.shot.navigate(self.ws, self.manage + "#usage", settle=2.0)
        self.assertTrue(self.wait("document.querySelectorAll('#uC1 svg .band').length === 7"))
        st = self.ev("""({sel: document.getElementById('tab-usage').getAttribute('aria-selected'), proj: document.getElementById('pn-projects').hidden,
          tiles: document.querySelectorAll('#uTiles .tile').length, legend: document.querySelectorAll('#uC1lg li').length,
          minis: document.querySelectorAll('#uC2 .mini svg').length, bars: document.querySelectorAll('#uC3 .pj li').length,
          rows: document.querySelectorAll('#uR tbody tr').length, title: document.title, pill: !!document.querySelector('#uR .pill')})""")
        self.assertEqual(st["sel"], "true")
        self.assertTrue(st["proj"])
        self.assertEqual(st["tiles"], 4)
        self.assertGreaterEqual(st["legend"], 2)
        self.assertGreaterEqual(st["minis"], 2)
        self.assertGreaterEqual(st["bars"], 3)
        self.assertEqual(st["rows"], 20)
        self.assertIn("การใช้งาน", st["title"])
        self.assertTrue(st["pill"])
        # 1440: ตารางพอดีการ์ด = แสดงเป็นตาราง (รายการสองบรรทัดซ่อนอยู่ ไม่ถูกอ่านซ้ำ)
        rc = self.ev("""(() => { const b = document.getElementById('uR'), t = b.querySelector(':scope > table');
          return {narrow: b.classList.contains('rc-narrow'), tw: t.offsetWidth, bw: b.clientWidth,
            list: getComputedStyle(b.querySelector('.rc-list')).display, items: b.querySelectorAll('.rc-list > li').length}; })()""")
        self.assertEqual((rc["narrow"], rc["list"], rc["items"]), (False, "none", 20), rc)
        self.assertLessEqual(rc["tw"], rc["bw"] + 1, rc)
        # ชื่อโปรเจกต์จาก /api/projects (slug → ชื่อไทย) ไม่ใช่ slug
        # (รายชื่อมาจาก refresh() ที่อาจตอบหลังข้อมูลการใช้งาน — หน้าวาดใหม่เองเมื่อรายชื่อมาถึง)
        self.assertTrue(self.wait("document.getElementById('uC3').textContent.includes('วินิจฉัยตู้ชาร์จ')"))
        # 30 วัน: แถบช่วงเวลาเป็น radiogroup — ลูกศรสลับ
        self.ev("document.querySelector('#uRange [data-days=\"7\"]').focus()")
        self.key("ArrowRight", "ArrowRight", 39)
        self.assertTrue(self.wait("document.querySelectorAll('#uC1 svg .band').length === 30"))
        self.assertEqual(self.ev("document.querySelector('#uRange [aria-checked=true]').dataset.days"), "30")
        # คีย์บอร์ดบนกราฟ: ป้ายลอย + live region
        self.ev("document.getElementById('uC1').focus()")
        self.key("End", "End", 35)
        self.assertFalse(self.ev("document.querySelector('#uC1 .tip').hidden"))
        self.assertTrue(self.ev("document.getElementById('uC1').matches(':focus-visible')"), "วงโฟกัสของกราฟต้องเห็นเมื่อใช้คีย์บอร์ด")
        self.ws.drain(0.3)
        self.assertTrue(self.ev("document.getElementById('uLive').textContent.length > 5"))
        self.assertEqual(self.errors(), [])

    def test_1b_no_horizontal_scroll_at_390(self):
        Stub.mode = "ok"
        self.ws.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
        try:
            for tab in ("usage", "doctor", "projects"):
                self.shot.navigate(self.ws, self.manage + "&w=390&t=%s#%s" % (tab, tab), settle=1.5)
                self.wait("!document.getElementById('pn-%s').hidden" % tab)
                self.ws.drain(1.0)
                w = self.ev("[document.documentElement.scrollWidth, innerWidth]")
                self.assertLessEqual(w[0], w[1], (tab, w))
                if tab != "usage":
                    continue
                # คำขอล่าสุด (integ b3: ตาราง 700 px เลื่อนในการ์ด 330 px คอลัมน์ตัวเลข/ป้าย "สรุปแล้ว" อยู่นอกจอ) → รายการ
                # สองบรรทัดที่ทุกอย่างอยู่ในการ์ด ไม่มีอะไรต้องเลื่อนแนวนอน
                self.assertTrue(self.wait("document.getElementById('uR').classList.contains('rc-narrow')"))
                rc = self.ev("""(() => { const b = document.getElementById('uR'), r = b.getBoundingClientRect();
                  const lis = [...b.querySelectorAll('.rc-list > li')];
                  return {table: getComputedStyle(b.querySelector(':scope > table')).display, items: lis.length,
                    over: b.scrollWidth - b.clientWidth,
                    out: [...b.querySelectorAll('.rc-list *')].filter(n => n.getBoundingClientRect().right > r.right + 1).length,
                    pills: b.querySelectorAll('.rc-list .pill').length, text: lis.length ? lis[0].textContent : ''}; })()""")
                self.assertEqual(rc["table"], "none", rc)
                self.assertEqual(rc["items"], 20, rc)
                self.assertLessEqual(rc["over"], 0, rc)
                self.assertEqual(rc["out"], 0, rc)
                self.assertGreaterEqual(rc["pills"], 1, rc)
                self.assertIn("tok/s", rc["text"])
                self.assertIn("พรอมต์", rc["text"].replace("⁠", ""))
        finally:
            self.ws.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})

    def test_2_doctor_tab_and_copy(self):
        Stub.mode = "ok"
        self.ws.events.clear()
        self.shot.navigate(self.ws, self.manage + "#usage", settle=1.5)
        self.ev("document.getElementById('tab-usage').focus()")
        self.key("ArrowRight", "ArrowRight", 39)
        self.assertTrue(self.wait("!document.getElementById('dBody').hidden"))
        self.assertTrue(self.ev("location.hash === '#doctor' && document.activeElement.id === 'tab-doctor'"))
        st = self.ev("""({rows: document.querySelectorAll('#dBody .svc-r:not(.svc-hd)').length, bad: document.querySelectorAll('#dBody .svc .dot.bad').length,
          fixes: document.querySelectorAll('#dBody .fx li').length, sum: document.getElementById('dSumT').textContent,
          text: document.getElementById('pn-doctor').textContent, low: !!document.querySelector('#dBody .mt-b.warn, #dBody .mt-b.bad')})""")
        self.assertEqual(st["rows"], 8)
        self.assertEqual(st["bad"], 1)
        self.assertEqual(st["fixes"], 2)
        self.assertIn("2", st["sum"])
        self.assertNotIn(SECRET, st["text"], "ค่าลับต้องไม่อยู่บนหน้า")
        self.assertTrue(st["low"])
        # คัดลอกรายงาน: ดักที่ writeText (headless อ่านคลิปบอร์ดจริงไม่ได้) — ข้อความที่ส่งต้องไม่มีค่าลับ/word joiner
        self.ev("navigator.clipboard.writeText = function (t) { window.__copied = t; return Promise.resolve(); }; true")
        self.ev("document.getElementById('dCopy').click()")
        txt = self.wait("window.__copied || ''")
        self.assertIn("รายงานตรวจระบบ Qwen3.8", txt)
        self.assertIn("[บริการ]", txt)
        self.assertNotIn(SECRET, txt)
        self.assertNotIn("\u2060", txt)
        self.ws.drain(0.3)
        self.assertEqual(self.ev("document.getElementById('dCopyT').textContent"), "คัดลอกแล้ว")
        self.assertEqual(self.errors(), [])

    def test_3_unsupported_hub(self):
        Stub.mode = "unsupported"
        try:
            self.ws.events.clear()
            # query ต่างจากหน้าที่เปิดอยู่ (manage…#doctor จากเทสต์ก่อน) — URL เดิมต่างแค่ #hash = ไม่โหลดหน้าใหม่
            self.shot.navigate(self.ws, self.manage + "&r=3#doctor", settle=1.5)
            self.assertTrue(self.wait("!document.getElementById('dMsg').hidden"))
            self.assertIn("hub ที่รันอยู่ยังไม่มีข้อมูลส่วนนี้", self.ev("document.getElementById('dMsg').textContent"))
            self.assertTrue(self.ev("document.getElementById('dBody').hidden && document.getElementById('dCopy').disabled"))
            self.ev("document.getElementById('tab-usage').click()")
            self.assertTrue(self.wait("!document.getElementById('uMsg').hidden"))
            self.assertIn("ลองใหม่", self.ev("document.getElementById('uMsg').textContent"))
            self.assertEqual(self.errors(), [])
        finally:
            Stub.mode = "ok"

    def test_3b_real_hub_routes(self):
        """เส้นทางจริงของ hub (GET /api/usage, /api/doctor?lang=) → หน้าวาดได้ครบ ไม่มีค่าลับ ไม่มี JS error"""
        Stub.mode = "real"
        try:
            self.ws.events.clear()
            self.shot.navigate(self.ws, self.manage + "&r=3b#usage", settle=1.5)
            self.assertTrue(self.wait("document.querySelectorAll('#uC1 svg .band').length === 7"))
            st = self.ev("""({tiles: document.querySelectorAll('#uTiles .tile').length, minis: document.querySelectorAll('#uC2 .mini svg').length,
              bars: document.querySelectorAll('#uC3 .pj li').length, rows: document.querySelectorAll('#uR tbody tr').length,
              names: document.getElementById('uC3').textContent})""")
            self.assertEqual(st["tiles"], 4)
            self.assertGreaterEqual(st["minis"], 3)       # gpt-oss อาจไม่มีใน 7 วันล่าสุดของข้อมูลสุ่ม
            self.assertEqual(st["bars"], 5)
            self.assertEqual(st["rows"], 20)
            self.assertIn("วินิจฉัยตู้ชาร์จ", st["names"])
            self.ev("document.getElementById('tab-doctor').click()")
            self.assertTrue(self.wait("!document.getElementById('dBody').hidden"))
            st = self.ev("""({rows: document.querySelectorAll('#dBody .svc-r:not(.svc-hd)').length,
              bad: document.querySelectorAll('#dBody .svc .dot.bad').length, sum: document.getElementById('dSumT').textContent,
              dot: document.getElementById('dDot').className, fx: [...document.querySelectorAll('#dBody .fx li')].map(l => l.className),
              stt: [...document.querySelectorAll('#dBody .svc-r')].find(r => r.textContent.includes('8795')).textContent,
              keys: document.querySelector('#dBody .kv').textContent, text: document.getElementById('pn-doctor').textContent})""")
            self.assertEqual(st["rows"], 8)
            self.assertEqual(st["bad"], 1)
            self.assertIn("พบปัญหา 3 รายการ", st["sum"].replace("⁠", ""))
            self.assertEqual(st["dot"], "dot bad")
            self.assertEqual(st["fx"][0], "bad")
            self.assertEqual(st["fx"][-2:], ["info", "info"])
            self.assertIn("ไม่ทำงาน", st["stt"])
            self.assertIn("โทเค็นของบริการในเครื่อง", st["keys"].replace("⁠", ""))
            self.assertNotIn(SECRET, st["text"])
            # แถบดิสก์ตามคำแนะนำของ hub: C: 8.4 GB (มีคำแนะนำ disk ระดับ warn) = อำพันแถบเดียว ไม่มีแดง
            meters = "[...document.querySelectorAll('#dBody .mt')].map(m => [m.querySelector('.mt-l').textContent, " \
                     "(m.querySelector('.mt-b') || {}).className || '', m.querySelector('.mt-v').textContent])"
            low = [m for m in self.ev(meters) if m[1] != "mt-b"]
            self.assertEqual(len(low), 1, low)
            self.assertEqual(low[0][1], "mt-b warn")
            self.assertIn("C:", low[0][0])
            self.assertIn("เหลือน้อย", low[0][2].replace("⁠", ""))
            # ระบบปกติ (ไม่มีปัญหาจริง เหลือแค่คำแนะนำ Brave/Docker) = จุดเขียว + "มีคำแนะนำ 2 ข้อ"
            Stub.mode = "real-healthy"
            self.ev("document.getElementById('dRe').click()")
            self.assertTrue(self.wait("document.getElementById('dDot').className === 'dot ok'"))
            self.assertIn("มีคำแนะนำ 2 ข้อ", self.ev("document.getElementById('dSumT').textContent").replace("⁠", ""))
            # ดิสก์แบบเครื่องจริง (C: 26.2 GB = 5.5%, E: 11.5 GB = 5%) ที่ hub บอกปกติ: ไม่มีแถบสี/คำ "เหลือน้อย" (integ b3)
            self.assertTrue(self.wait("document.getElementById('dBody').textContent.replace(/\\u2060/g, '').includes('26.2 GB')"))
            ms = self.ev(meters)
            self.assertEqual([m for m in ms if m[1] not in ("", "mt-b")], [], ms)
            self.assertNotIn("เหลือน้อย", self.ev("document.getElementById('dBody').textContent").replace("⁠", ""))
            self.assertEqual(self.errors(), [])
        finally:
            Stub.mode = "ok"

    def test_4b_real_compaction_header(self):
        """D1 → D4 ผ่าน hub จริง: คำขอแชตยาวเกินเพดาน (ctx ถูกบีบเหลือ 6000 ในเทสต์) → hub ย่อ (โมเดลสรุป = upstream ปลอม)
        → header X-Qwen-Compacted ของ hub เอง → enhance ขึ้นป้ายพร้อมจำนวนรอบที่ hub บอก"""
        hub = self.stub.hub
        _Up.compacted = None
        p = mock.patch.object(hub, "model_ctx", lambda model_id: 6000)
        p.start()
        try:
            self.ws.events.clear()
            self.shot.navigate(self.ws, self.chat + "&r=4b", settle=5.0)
            self.assertTrue(self.wait_composer())
            self.frame("qwenEnhance.prefill('เริ่มแชตสำหรับทดสอบการย่อ')")
            self.frame("document.querySelector('.chat-screen-form-wrapper form button[type=submit]').click()")
            for _ in range(60):
                self.ws.drain(0.25)
                if self.frame("qwenEnhance.route().name === 'chat' && !qwenEnhance.isStreaming()"):
                    break
            cid = self.frame("qwenEnhance.route().id")
            self.assertTrue(cid)
            msgs = []
            for i in range(12):
                msgs.append({"role": "user", "content": ("รอบที่ %d: ตู้ชาร์จ C-%02d วัดแรงดันได้ %d โวลต์ " % (i, i, 390 + i)) * 40})
                msgs.append({"role": "assistant", "content": ("บันทึกรอบ %d แล้ว ไฟล์ report-%d.xlsx " % (i, i)) * 40})
            msgs.append({"role": "user", "content": "สรุปตู้ที่แรงดันสูงสุด"})
            body = json.dumps({"model": FAST, "stream": True, "messages": msgs}, ensure_ascii=False)
            got = self.frame("fetch('./v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json','X-Conversation-Id':%s},"
                             "body:%s}).then(r=>r.text().then(()=>r.headers.get('X-Qwen-Compacted')))"
                             % (json.dumps(cid + "::" + FAST), json.dumps(body, ensure_ascii=False)))
            self.assertTrue(got and int(got) > 0, got)
            self.ws.drain(0.6)
            c = self.frame("qwenEnhance.compaction()")
            self.assertEqual((c["turns"], c["shown"]), (int(got), True))
            t = self.frame("document.querySelector('.qw-compact-b').textContent").replace("⁠", "")
            self.assertEqual(t, "สรุปช่วงต้นของบทสนทนาแล้ว (%s รอบ)" % got)
            # โน้ตของ hub สำหรับแชตนี้ (GET /_qwen/usage) ตรงกับ header
            note = self.frame("fetch('./_qwen/usage?conversation=' + encodeURIComponent(%s)).then(r=>r.json())" % json.dumps(cid))
            self.assertEqual((note.get("compaction") or {}).get("turns"), int(got))
            self.assertEqual(self.errors(), [])
        finally:
            p.stop()

    def test_4_compaction_notice(self):
        self.ws.events.clear()
        self.shot.navigate(self.ws, self.chat, settle=5.0)
        self.assertTrue(self.wait_composer())
        # สร้างแชตจริงผ่าน WebUI (ส่งข้อความ → upstream ปลอมตอบ) แล้วค่อยเปิด header
        _Up.compacted = None
        self.frame("qwenEnhance.prefill('ทดสอบป้ายสรุป')")
        self.frame("document.querySelector('.chat-screen-form-wrapper form button[type=submit]').click()")
        for _ in range(60):
            self.ws.drain(0.25)
            if self.frame("qwenEnhance.route().name === 'chat' && !qwenEnhance.isStreaming()"):
                break
        cid = self.frame("qwenEnhance.route().id")
        self.assertTrue(cid)
        self.assertEqual(self.frame("qwenEnhance.compaction().turns"), 0)
        self.assertFalse(self.frame("!!document.querySelector('.qw-compact')"))
        # คำขอแชตของแชตนี้ที่ hub ย่อ (header 12) → ป้ายขึ้นเหนือกล่องพิมพ์
        _Up.compacted = 12
        body = json.dumps({"model": FAST, "stream": True, "messages": [{"role": "user", "content": "x"}]})
        self.frame("fetch('./v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json','X-Conversation-Id':%s},"
                   "body:%s}).then(r=>r.text()).then(()=>1)" % (json.dumps(cid + "::" + FAST), json.dumps(body)))
        self.ws.drain(0.6)
        c = self.frame("qwenEnhance.compaction()")
        self.assertEqual((c["turns"], c["shown"]), (12, True))
        note = self.frame("(()=>{const n=document.querySelector('.qw-compact'),b=n.querySelector('.qw-compact-b');"
                          "return {t:b.textContent,next:n.nextElementSibling.getAttribute('data-slot'),"
                          "desc:document.getElementById(b.getAttribute('aria-describedby')).textContent,role:n.getAttribute('role')}})()")
        self.assertEqual(note["t"].replace("⁠", ""), "สรุปช่วงต้นของบทสนทนาแล้ว (12 รอบ)")
        self.assertIn(note["next"], ("input-area", None))
        self.assertIn("12 รอบ", note["desc"].replace("\u2060", ""))
        self.assertEqual(note["role"], "note")
        # แตะ/คลิก = เปิดคำอธิบายค้าง, คลิกอีกครั้ง = ปิด
        self.frame("document.querySelector('.qw-compact-b').click()")
        self.assertFalse(self.frame("document.querySelector('.qw-compact-tip').hidden"))
        self.frame("document.querySelector('.qw-compact-b').click()")
        self.assertTrue(self.frame("document.querySelector('.qw-compact-tip').hidden"))
        # ไปหน้าเริ่มแชต = ไม่มีป้าย, กลับมา = ป้ายกลับมา (จำใน localStorage)
        self.frame("qwenEnhance.newChat()")
        self.ws.drain(0.8)
        self.assertFalse(self.frame("!!(document.querySelector('.qw-compact')||{}).isConnected"))
        self.frame("qwenEnhance.openChat(%s)" % json.dumps(cid))
        self.ws.drain(1.5)
        self.assertTrue(self.frame("qwenEnhance.compaction().shown"))
        # คำตอบของแชตเดียวกันที่ไม่มี header = ไม่ได้ย่อแล้ว → ป้ายหาย
        _Up.compacted = None
        self.frame("fetch('./v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json','X-Conversation-Id':%s},"
                   "body:%s}).then(r=>r.text()).then(()=>1)" % (json.dumps(cid + "::" + FAST), json.dumps(body)))
        self.ws.drain(0.6)
        self.assertEqual(self.frame("qwenEnhance.compaction().turns"), 0)
        self.assertFalse(self.frame("!!(document.querySelector('.qw-compact')||{}).isConnected"))
        self.assertEqual(self.errors(), [])

    def test_5_shell_menu_links(self):
        self.ws.events.clear()
        self.shot.navigate(self.ws, self.chat, settle=4.0)
        self.ev("document.getElementById('acctBtn').click()")
        self.ws.drain(0.4)
        items = self.ev("[...document.querySelectorAll('#menu .menu-item .mi-l')].map(n=>n.textContent)")
        self.assertIn("การใช้งาน", items)
        self.assertIn("ตรวจระบบ", items)
        # เปิดแท็บใหม่ไปที่ #usage / #doctor ของหน้าจัดการ (ดัก window.open — ไม่เปิดจริง)
        self.ev("window.__opened=[];window.open=function(u){window.__opened.push(u);return null;};true")
        self.ev("[...document.querySelectorAll('#menu .menu-item')].find(b=>b.textContent.includes('ตรวจระบบ')).click()")
        opened = self.ev("window.__opened")
        self.assertEqual(len(opened), 1)
        self.assertRegex(opened[0], r"^http://127\.0\.0\.1:%d/\?manage=1&theme=(dark|light)#doctor$" % self.stub.api_port)
        self.assertEqual(self.errors(), [])


def serve(argv):
    """โหมดเปิดค้างให้ shot.py ถ่ายภาพ — ปิดเองเมื่อครบ --minutes"""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--mode", default="ok", choices=["ok", "healthy", "empty", "unsupported", "real", "real-healthy"])
    ap.add_argument("--lang", default="th", choices=["th", "en"])
    ap.add_argument("--theme", default="dark", choices=["dark", "light"])
    ap.add_argument("--compacted", type=int, default=12)
    ap.add_argument("--minutes", type=float, default=20)
    a = ap.parse_args(argv)
    Stub.mode = a.mode
    _Up.compacted = a.compacted or None
    st = Stub(a.lang, a.theme)
    print(json.dumps({"pid": os.getpid(), "api": st.api_port, "port": st.port, "tmp": st.tmp}), flush=True)
    try:
        end = time.time() + a.minutes * 60
        while time.time() < end:
            time.sleep(1)
    finally:
        st.stop()


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve(sys.argv[1:])
    else:
        unittest.main()
