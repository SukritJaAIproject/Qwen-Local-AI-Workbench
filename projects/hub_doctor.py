# -*- coding: utf-8 -*-
"""batch 3 สัญญา D3 (owner hub) — GET /api/doctor: รายงานสุขภาพของทั้งสแตกในคำขอเดียว

ทำไม: เวลามีอะไรเสีย ผู้ใช้ต้องไล่เปิด log หลายไฟล์ เดาว่าบริการไหนล้ม (router / MCP / embedding / STT / scheduler /
gateway) ดิสก์เต็มไหม VRAM เหลือเท่าไร — หน้า "ตรวจระบบ" รวมทั้งหมดไว้ที่เดียวพร้อมวิธีแก้ที่สั่งได้จริง
กติกา: ถูก (< 3 วินาที: ตรวจทุกอย่างขนานกันมีเส้นตาย, แคช 10 วินาที), อ่านอย่างเดียว (ไม่สั่งโหลดโมเดล — ไม่ถาม /props
หรือ /models พร้อม ?model=, ไม่แฮชไฟล์โมเดล), ไม่มีความลับ (ไฟล์คีย์บอกแค่มี/ไม่มี, บรรทัด log ผ่านการลบโทเคนก่อน)
"""
from __future__ import annotations

import ctypes
import http.client
import json
import math
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

CACHE_S = 10.0
DEADLINE_S = 2.6
PROBE_TIMEOUT = 1.2
LOG_TAIL_BYTES = 192 * 1024
LOG_LINES = 20
LOG_LINE_MAX = 300
# [fix-hub b3 2026-10-06] ไฟล์ *.err.log ที่ไม่ได้เขียนมาเกินเท่านี้ไม่นับเป็น "ข้อผิดพลาดล่าสุด" — ผู้ตรวจรับเห็นบรรทัด
# "ModuleNotFoundError: No module named encodings" จากการทดสอบเมื่อ 2026-09-29 ค้างในหน้าตรวจระบบของเครื่องที่ปกติดีอยู่ทั้งสัปดาห์
ERR_MAX_AGE_S = 3 * 86400
# log ของบริการชุดทดสอบที่รันบนพอร์ตสำรอง (llama-8199.err.log, gpu-state-8197.err.log, embed-8893.err.log, stt-8896…)
# ไม่ใช่ปัญหาของบริการที่ใช้งานจริง — พอร์ตต่อท้ายชื่อที่ไม่ใช่พอร์ตจริงของสแตก (cfg live_ports) = ข้าม
_PORT_LOG_RE = re.compile(r"^[A-Za-z][\w-]*?-(\d{4,5})(?:\.[\w-]+)?\.err\.log$")
HEARTBEAT_STALE_S = 45 * 60      # scheduler ยิง heartbeat ทุก 30 นาที — เกิน 45 นาที = ไม่ทำงานแล้ว
DISK_LOW_GB = 10.0
COMMIT_LOW_GB = 8.0
GPU_HOT_C = 87
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# บรรทัด log ที่นับเป็นข้อผิดพลาด: llama-server ("<เวลา> E <โมดูล>") / Python (Traceback, XxxError:, ERROR, CRITICAL)
_LLAMA_ERR_RE = re.compile(r"^\s*\d+\.\d+\.\d+\.\d+ E ")
_PY_ERR_RE = re.compile(r"Traceback \(most recent call last\)|^\s*[A-Za-z_][\w.]*(Error|Exception)\b[:\s]|"
                        r"\b(ERROR|CRITICAL|FATAL)\b|ผิดพลาด|ล้มเหลว")
# ผู้ใช้ปิดแท็บ/ตัดสายระหว่างตอบ — Windows รายงานเป็น ConnectionReset/Aborted ทุกครั้ง ไม่ใช่ปัญหาของระบบ
# [integ b3 2026-10-06] + "Connection handling canceled" = llama-server บอกว่าฝั่งผู้เรียกปิดสายกลางสตรีม — เกิดทุกครั้งที่ผู้ใช้กดหยุด
# และทุกครั้งที่ hub หยุดอ่านโมเดลสรุปเมื่อครบงบเวลา (D1, ตั้งใจ) วัดสด 22:35 ตอนย่อบทสนทนาจริง: บรรทัด E นี้ขึ้นในหน้าตรวจระบบเป็น "ข้อผิดพลาด"
_BENIGN_RE = re.compile(r"ConnectionResetError|ConnectionAbortedError|BrokenPipeError|WinError 1005[34]|"
                        r"forcibly closed|An established connection was aborted|Connection handling canceled")
# ลบความลับรูปแบบที่รู้จัก (โทเคน 64 hex ของบริการในเครื่อง, Bearer, api key=..., sk-...) — ชั้นที่สองต่อจาก secrets_util.scrub
_REDACT = [
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 ***"),
    # (?!Bearer|***) — "Authorization: Bearer xxx" ให้เหลือ "Authorization: Bearer ***" (บอกชนิดได้ ค่าหายแล้วจากแถวบน)
    (re.compile(r"(?i)\b(api[_-]?key|x-api-key|token|password|passwd|secret|authorization)(\s*[=:]\s*)"
                r"(?!bearer\b|\*\*\*)[\"']?[^\s\"',;]{4,}"),
     r"\1\2***"),
    # [fix-hub b3 2026-10-06] ป้ายที่ตามด้วยช่องว่าง ("client key <ค่า>", "X-Api-Key <ค่า>") และป้ายผสม (gateway_key, apikey…)
    # — ผู้ตรวจพบว่าค่าแบบ secrets.token_urlsafe (รูปแบบคีย์ของ gateway: ไม่ใช่ hex ไม่ขึ้นต้น sk-/BSA) หลุดทั้ง 3 รูปแบบ
    (re.compile(r"(?i)\b([\w-]*(?:key|token|secret|passw\w*|credential\w*))\b(\s*[:= ]\s*)"
                r"(?!bearer\b|\*\*\*)[\"']?[^\s\"',;]{6,}"),
     r"\1\2***"),
    (re.compile(r"\b[0-9a-fA-F]{40,}\b"), "***"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "***"),
    (re.compile(r"\bBSA[A-Za-z0-9_-]{16,}\b"), "***"),
]
# ก้อนตัวอักษรแบบ base64url ยาว ≥ 24 ที่ "ดูสุ่ม" (มีทั้งตัวพิมพ์ใหญ่และเล็ก เอนโทรปีสูง มี -/_ ไม่เกิน 5 ตัว)
# — ชั้นสุดท้ายสำหรับคีย์ที่ไม่มีป้ายนำหน้า (ค่าจริงของ gateway/Brave key ถูกลบตามค่าอีกชั้นแล้ว — value_scrubber)
# ชื่อโมเดล (Qwen3-4B-Instruct-2507-Q4_K_M มี -/_ 6 ตัว), ชื่อตัวแปร (ตัวเล็กล้วน), GUID (มีขีด 4 แต่ตัวเล็กล้วน) จึงไม่โดน
_TOKENISH_RE = re.compile(r"(?<![\w-])[A-Za-z0-9_-]{24,}(?![\w-])")
# อักขระควบคุม / สลับทิศ / ล่องหน — บรรทัด log ที่ถูกยัดอักขระพวกนี้แสดงผลต่างจากที่อ่านจริง (หน้าตรวจระบบโชว์ errors[] ตรงๆ)
_CTRL_INVISIBLE_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁠-⁤⁦-⁩﻿]")


def _entropy(s):
    n = float(len(s))
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _tokenish(m):
    s = m.group(0)
    if not (re.search(r"[A-Z]", s) and re.search(r"[a-z]", s)):
        return s
    if len(re.findall(r"[-_]", s)) > 5 or _entropy(s) < 4.1:
        return s
    return "***"


def redact(line, scrub=None):
    s = line
    if scrub is not None:
        try:
            s = scrub(s)
        except Exception:                  # noqa: BLE001 — ตัวลบของ secrets_util พังต้องไม่ทำให้รายงานล้ม (ยังมีชั้นข้างล่าง)
            pass
    for rx, rep in _REDACT:
        s = rx.sub(rep, s)
    s = _TOKENISH_RE.sub(_tokenish, s)
    s = _CTRL_INVISIBLE_RE.sub("", s)
    return s[:LOG_LINE_MAX] + ("…" if len(s) > LOG_LINE_MAX else "")


def value_scrubber(paths, base=None):
    """[fix-hub b3] ตัวลบ "ตามค่า" ของคีย์อื่นนอกจากโทเคนในเครื่อง (gateway key, Brave key) — อ่านไฟล์ในโปรเซสตอนสร้างรายงาน
    แล้วแทนค่าที่พบด้วย *** (ไม่เคยใส่ค่าลงรายงาน/log) base = secrets_util.scrub (โทเคนในเครื่อง) ทำก่อน"""
    vals = []
    for p in paths or ():
        try:
            fp = Path(p)
            if fp.is_file() and fp.stat().st_size <= 4096:
                v = fp.read_text(encoding="utf-8", errors="ignore").strip()
                if len(v) >= 8:
                    vals.append(v)
        except OSError:
            pass

    def scrub(s):
        if base is not None:
            try:
                s = base(s)
            except Exception:              # noqa: BLE001
                pass
        for v in vals:
            if v in s:
                s = s.replace(v, "***")
        return s
    return scrub


def _http(port, path, headers=None, timeout=PROBE_TIMEOUT):
    """(status, body bytes ≤ 256 KB, ms) — status None = ต่อไม่ติด/หมดเวลา"""
    t0 = time.perf_counter()
    conn = None
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        h = {"Host": "127.0.0.1:%d" % port, "Accept": "application/json"}
        h.update(headers or {})
        conn.request("GET", path, headers=h)
        r = conn.getresponse()
        body = r.read(256 * 1024)
        return r.status, body, round((time.perf_counter() - t0) * 1000)
    except (OSError, http.client.HTTPException, ValueError):
        # ต่อไม่ติด = ไม่มีเวลาตอบ (เดิมคืนเวลาที่รอจนหมด ~1,200 ms หน้าตรวจระบบเลยโชว์ "ไม่ทำงาน 1215 ms" ชวนเข้าใจผิด)
        return None, b"", None
    finally:
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass


def _j(raw):
    try:
        d = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, AttributeError, RecursionError):
        return None
    return d


def _tcp_ms(port, timeout=0.5):
    t0 = time.perf_counter()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return round((time.perf_counter() - t0) * 1000)
    except OSError:
        return None


class _MEMSTAT(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def memory_status():
    """RAM + commit (หน่วยความจำที่จองได้ทั้งหมด = RAM + pagefile) เป็น GB — None ถ้าไม่ใช่ Windows"""
    try:
        st = _MEMSTAT()
        st.dwLength = ctypes.sizeof(_MEMSTAT)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return None
    except (AttributeError, OSError):
        return None
    g = 1024.0 ** 3
    return {"ram_total_gb": round(st.ullTotalPhys / g, 1), "ram_free_gb": round(st.ullAvailPhys / g, 1),
            "ram_load_pct": int(st.dwMemoryLoad), "commit_limit_gb": round(st.ullTotalPageFile / g, 1),
            "commit_free_gb": round(st.ullAvailPageFile / g, 1)}


def disks(letters=("C", "D", "E")):
    out = []
    for d in letters:
        try:
            u = shutil.disk_usage("%s:\\" % d)
        except OSError:
            out.append({"drive": d + ":", "present": False})
            continue
        out.append({"drive": d + ":", "present": True, "free_gb": round(u.free / 1024.0 ** 3, 1),
                    "total_gb": round(u.total / 1024.0 ** 3, 1)})
    return out


def gpu_info(timeout=2.2):
    exe = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"
    fields = "name,memory.total,memory.used,memory.free,driver_version,temperature.gpu,utilization.gpu"
    try:
        r = subprocess.run([exe, "--query-gpu=" + fields, "--format=csv,noheader,nounits"], capture_output=True,
                           text=True, timeout=timeout, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, type(exc).__name__
    if r.returncode != 0:
        return None, "nvidia-smi exit %d" % r.returncode
    rows = []
    for line in (r.stdout or "").splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) != 7:
            continue

        def num(v):
            try:
                return int(float(v))
            except ValueError:
                return None
        rows.append({"name": p[0][:80], "mem_total_mib": num(p[1]), "mem_used_mib": num(p[2]), "mem_free_mib": num(p[3]),
                     "driver": p[4][:20], "temp_c": num(p[5]), "util_pct": num(p[6])})
    return rows, None


def docker_status():
    """ใช้ Docker ได้ไหม (CLI + engine pipe) — ไม่รันคำสั่ง docker (อาจค้างหลายวินาทีถ้า engine ไม่ตอบ)"""
    cli = shutil.which("docker")
    desktop = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Docker" / "Docker" / "Docker Desktop.exe"
    pipe = os.path.exists(r"\\.\pipe\docker_engine")
    if cli and pipe:
        return {"usable": True, "reason_th": "พร้อมใช้", "reason_en": "ready"}
    if not cli and not desktop.is_file():
        return {"usable": False, "reason_th": "ยังไม่ได้ติดตั้ง Docker", "reason_en": "Docker is not installed"}
    if not pipe:
        return {"usable": False, "reason_th": "ติดตั้ง Docker Desktop ไว้แต่ engine ไม่ทำงาน",
                "reason_en": "Docker Desktop is installed but its engine is not running"}
    return {"usable": False, "reason_th": "ไม่พบคำสั่ง docker ใน PATH", "reason_en": "the docker CLI is not on PATH"}


def error_lines(log_dir, scrub=None, limit=LOG_LINES, live_ports=None, max_age_s=ERR_MAX_AGE_S, stats=None,
                now=None):
    """บรรทัดข้อผิดพลาดล่าสุดจาก *.err.log (ไฟล์ใหม่สุดก่อน อ่านแค่ท้ายไฟล์) — ตัดของปกติ (ผู้ใช้ตัดสาย) และลบความลับ
    [fix-hub b3] ข้ามไฟล์ที่ไม่ได้เขียนมาเกิน max_age_s และ log ของพอร์ตทดสอบ (ชื่อลงท้าย -<พอร์ต> ที่ไม่อยู่ใน live_ports)
    stats (dict) = นับไฟล์ที่ข้าม {"old_files", "test_logs"} ให้หน้าเว็บบอกได้ว่ามีของเก่าซ่อนอยู่"""
    try:
        files = [f for f in Path(log_dir).glob("*.err.log") if f.is_file()]
    except OSError:
        return [], 0
    now = time.time() if now is None else now
    live = {int(p) for p in (live_ports or ()) if p}
    kept = []
    for f in files:
        try:
            mt = f.stat().st_mtime
        except OSError:
            continue
        m = _PORT_LOG_RE.match(f.name)
        if live_ports is not None and m and int(m.group(1)) not in live:
            if stats is not None:
                stats["test_logs"] = stats.get("test_logs", 0) + 1
            continue
        if max_age_s and now - mt > max_age_s:
            if stats is not None:
                stats["old_files"] = stats.get("old_files", 0) + 1
            continue
        kept.append((mt, f))
    files = [f for _mt, f in sorted(kept, key=lambda x: x[0], reverse=True)]
    out, skipped = [], 0
    for f in files:
        try:
            size = f.stat().st_size
            with open(f, "rb") as fh:
                if size > LOG_TAIL_BYTES:
                    fh.seek(size - LOG_TAIL_BYTES)
                data = fh.read()
            mtime = datetime.fromtimestamp(f.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        except OSError:
            continue
        text = data.decode("utf-8", "replace")
        lines = text.splitlines()
        hits = []
        for ln in lines:
            if not (_LLAMA_ERR_RE.search(ln) or _PY_ERR_RE.search(ln)):
                continue
            if _BENIGN_RE.search(ln):
                skipped += 1
                continue
            if ln.strip().startswith("Traceback"):
                continue                  # ตัวบรรทัดที่บอกชนิดข้อผิดพลาดตามมาข้างล่างอยู่แล้ว
            hits.append(ln.strip())
        for ln in reversed(hits):
            out.append({"file": f.name, "file_mtime": mtime, "line": redact(ln, scrub)})
            if len(out) >= limit:
                return out, skipped
    return out, skipped


def models_present(dirs):
    """ไฟล์ .gguf ที่มีอยู่ (ชื่อ + ขนาด) — stat อย่างเดียว ไม่อ่าน/แฮชเนื้อไฟล์"""
    out = []
    for d in dirs:
        try:
            for f in sorted(Path(d).glob("*.gguf")):
                try:
                    out.append({"name": f.name, "size_gb": round(f.stat().st_size / 1024.0 ** 3, 2), "dir": str(d)})
                except OSError:
                    pass
        except OSError:
            pass
    return out


_OS_NAME = None


def windows_label(major, minor, build):
    """[fix-hub b3] Windows 11 รายงานตัวเองเป็น 10.0 (build ≥ 22000) — เดิมหน้าตรวจระบบเขียน "Windows-10.0.26200" บนเครื่อง
    Windows 11 Pro ผู้ใช้อ่านเป็น Windows 10"""
    if major == 10 and minor == 0:
        return "Windows %s (%d.%d.%d)" % ("11" if build >= 22000 else "10", major, minor, build)
    return "Windows %d.%d.%d" % (major, minor, build)


def os_name():
    """ชื่อ OS แบบถูก — platform.platform() บน Windows เรียก "cmd /c ver" สองครั้ง (~1 วินาทีครั้งแรก, วัด 2026-10-06)
    กินงบ 3 วินาทีของรายงานไปครึ่งหนึ่ง จึงอ่านเลขเวอร์ชันจาก sys.getwindowsversion() ตรงๆ แล้วจำไว้"""
    global _OS_NAME
    if _OS_NAME is None:
        try:
            v = sys.getwindowsversion()
            _OS_NAME = windows_label(v.major, v.minor, v.build)
        except AttributeError:
            _OS_NAME = "%s-%s" % (platform.system(), platform.release())
    return _OS_NAME


def _row(sid, th, en, port, state, ms=None, **detail):
    r = {"id": sid, "name_th": th, "name_en": en, "port": port, "state": state, "latency_ms": ms}
    r.update(detail)
    return r


FIX = {
    "router": ("ตัวจัดการโมเดล (8099) ไม่ทำงาน → เปิดใหม่ทั้งชุด: powershell -File C:\\LLM\\start-qwen38.ps1 -Unattended "
               "(หรือดับเบิลคลิกไอคอน Qwen3.8)",
               "Model router (8099) is down → restart the stack: powershell -File C:\\LLM\\start-qwen38.ps1 -Unattended "
               "(or double-click the Qwen3.8 icon)"),
    "router_auth": ("router ไม่รับโทเคนของ hub → เปิดตัวเปิดใหม่ (start-qwen38.ps1 -Unattended) ให้ทุกบริการใช้โทเคนชุดเดียวกัน",
                    "The router rejects the hub's token → run the launcher again (start-qwen38.ps1 -Unattended)"),
    "mcp_local": ("เครื่องมือในเครื่อง (MCP 8792) ไม่ทำงาน → powershell -File C:\\LLM\\projects\\tools\\restart_svc.ps1 -Name mcp-local",
                  "Local tools (MCP 8792) are down → powershell -File C:\\LLM\\projects\\tools\\restart_svc.ps1 -Name mcp-local"),
    "mcp_web": ("ค้นเว็บ (MCP 8791) ไม่ทำงาน → powershell -File C:\\LLM\\projects\\tools\\restart_svc.ps1 -Name websearch",
                "Web search (MCP 8791) is down → powershell -File C:\\LLM\\projects\\tools\\restart_svc.ps1 -Name websearch"),
    "mcp_auth": ("MCP ไม่รับโทเคน → รีสตาร์ต MCP ด้วย restart_svc.ps1 (โทเคนถูกสร้างใหม่หลังบริการเปิด)",
                 "MCP rejects the token → restart it with restart_svc.ps1 (the token changed after it started)"),
    "embed": ("ค้นตามความหมาย (embedding 8093) ไม่ทำงาน → powershell -File C:\\LLM\\start-qwen38.ps1 -EmbedOnly",
              "Semantic search (embedding 8093) is down → powershell -File C:\\LLM\\start-qwen38.ps1 -EmbedOnly"),
    "embed_absent": ("ไม่มีไฟล์โมเดล embedding ที่ D:\\LLM\\models-embed — ค้นเอกสารได้แค่แบบคำตรง",
                     "The embedding model file is missing (D:\\LLM\\models-embed) — document search is keyword-only"),
    "stt": ("พูดแทนพิมพ์ (STT 8795) ไม่ทำงาน → powershell -File C:\\LLM\\start-qwen38.ps1 -RestartStt",
            "Speech-to-text (STT 8795) is down → powershell -File C:\\LLM\\start-qwen38.ps1 -RestartStt"),
    "stt_model": ("STT หาโมเดลไม่เจอ — ต่อดิสก์ E: (USB) ที่เก็บโมเดลไว้ แล้วสั่ง start-qwen38.ps1 -RestartStt",
                  "STT cannot find its model — plug in drive E: (USB) and run start-qwen38.ps1 -RestartStt"),
    "scheduler": ("ตัวตั้งเวลา (heartbeat/จัดความจำ) ไม่ทำงาน → powershell -File C:\\LLM\\projects\\tools\\restart_svc.ps1 -Name scheduler",
                  "The scheduler (heartbeat/memory jobs) is not running → restart_svc.ps1 -Name scheduler"),
    "gateway": ("Remote Prompt Gateway (8780) ไม่ทำงาน → เปิดตัวเปิดใหม่ (start-qwen38.ps1 -Unattended)",
                "The remote prompt gateway (8780) is down → run the launcher again (start-qwen38.ps1 -Unattended)"),
    "hub_port": ("พอร์ตโปรเจกต์บางพอร์ตไม่ตอบ → powershell -File C:\\LLM\\projects\\tools\\restart_svc.ps1 -Name hub "
                 "(รอให้แชตที่ตอบอยู่เสร็จก่อน)",
                 "Some project ports do not answer → restart_svc.ps1 -Name hub (wait for running replies to finish first)"),
    "disk": ("ดิสก์ %s เหลือ %.1f GB → ลบ/ย้ายไฟล์ที่ไม่ใช้ หรือรีบูต (pagefile ของ C: คืนพื้นที่ได้ ~20 GB)",
             "Drive %s has %.1f GB free → free up space or reboot (C: pagefile shrinks back ~20 GB)"),
    "drive_e": ("ไม่พบดิสก์ E: (USB) — log OCPP, HF cache และโมเดล STT อยู่ที่นั่น ต่อดิสก์ก่อนใช้พูดแทนพิมพ์",
                "Drive E: (USB) is missing — OCPP logs, the HF cache and the STT model live there"),
    "commit": ("หน่วยความจำ commit เหลือ %.1f GB → ปิดโปรแกรมที่ไม่ใช้ หรือปลดโมเดลที่ไม่ได้ใช้ (งานขนานอาจตายด้วย MemoryError)",
               "Only %.1f GB of commit memory is free → close programs or unload idle models (parallel jobs may fail)"),
    "gpu_hot": ("GPU ร้อน %d °C → ตรวจการระบายอากาศ/ลดงาน (เครื่องจะลดความเร็วเอง)",
                "GPU is at %d °C → check cooling / reduce load (the machine throttles itself)"),
    "gpu_missing": ("ไม่พบ GPU จาก nvidia-smi → ตรวจไดรเวอร์ NVIDIA (โมเดลจะรันบน CPU ช้ามาก)",
                    "nvidia-smi found no GPU → check the NVIDIA driver (models fall back to the slow CPU)"),
    "token": ("ไม่มีไฟล์โทเคนของบริการในเครื่อง → เปิดตัวเปิด (start-qwen38.ps1) เพื่อสร้างใหม่",
              "The local services token file is missing → run the launcher (start-qwen38.ps1) to create it"),
    "brave": ("ยังไม่มี Brave Search key → ค้นเว็บใช้ได้แค่แหล่งพื้นฐาน วาง key เองที่ C:\\LLM\\secrets\\brave-search.key",
              "No Brave Search key → web search is limited; put your key in C:\\LLM\\secrets\\brave-search.key"),
    "docker": ("Docker ใช้ไม่ได้ (%s) → ติดตั้ง Docker Desktop ใหม่เอง (ต้องกด UAC/ยอมรับเงื่อนไข) — ระหว่างนี้ python รันบนเครื่องพร้อมขอยืนยัน",
               "Docker is not usable (%s) → reinstall Docker Desktop yourself (UAC + licence); python runs on the host with approval meanwhile"),
    "tests": ("ชุดทดสอบรอบล่าสุดไม่ผ่าน %d ข้อ → C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests",
              "The last test run had %d failures → C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests"),
}


# [integ b3 2026-10-06] ระดับของคำแนะนำ — ตรงกับ B3_FIX_LEVEL ของหน้า "ตรวจระบบ" (hub_i18n_parts.py, owner ui) ที่เดิมต้องเดาจาก id
# บริการล่ม = error, สิ่งที่รอผู้ใช้ทำเอง (วาง Brave key, ติดตั้ง Docker ใหม่) = info, อื่นๆ = warn
# info ไม่นับใน overall: เครื่องที่ทุกบริการปกติแต่ยังไม่มี Brave key/Docker เคยได้ overall=warn ตลอดกาล ขณะที่หน้าเว็บขึ้นเขียว
# (รายงานข้อความ/สคริปต์ที่อ่าน overall จึงบอก "มีข้อสังเกต" ทั้งที่ไม่มีปัญหา)
FIX_SEVERITY = {"router": "error", "router_auth": "error", "mcp_local": "error", "mcp_web": "error", "mcp_auth": "error",
                "embed": "error", "stt": "error", "scheduler": "error", "gateway": "error", "brave": "info", "docker": "info"}


class Doctor:
    """cfg: dict ของค่าคงที่/ฟังก์ชันจาก hub (ดู hub.doctor_config()) — แยกไว้ให้ชุดทดสอบใส่ของปลอมได้ทุกตัว"""

    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._cache = None               # (monotonic, report)
        self._scrub = cfg.get("scrub")
        self._log_stats = {}

    # ---------------------------------------------------------------- ตัวตรวจทีละเรื่อง
    def _router(self):
        port = self.cfg["upstream_port"]
        st, raw, ms = _http(port, "/health")
        if st is None:
            return _row("router", "ตัวจัดการโมเดล (llama-server)", "Model router (llama-server)", port, "down", ms)
        if st == 503:
            return _row("router", "ตัวจัดการโมเดล (llama-server)", "Model router (llama-server)", port, "loading", ms)
        hdr = self.cfg["router_headers"]() or {}
        st2, raw2, _ = _http(port, "/models", hdr)          # ไม่มี ?model= — ไม่ทำให้โหลดอะไร
        models, loaded = [], []
        if st2 in (401, 403):
            return _row("router", "ตัวจัดการโมเดล (llama-server)", "Model router (llama-server)", port, "auth", ms)
        d = _j(raw2) if st2 == 200 else None
        for m in (d or {}).get("data") or [] if isinstance(d, dict) else []:
            if not isinstance(m, dict):
                continue
            state = ((m.get("status") or {}).get("value")) if isinstance(m.get("status"), dict) else None
            models.append({"id": str(m.get("id"))[:120], "state": state})
            if state in ("loaded", "loading"):
                loaded.append({"id": str(m.get("id"))[:120], "state": state})
        st3, raw3, _ = _http(port, "/props", hdr)
        p = _j(raw3) if st3 == 200 else None
        build = str((p or {}).get("build_info") or "")[:40] if isinstance(p, dict) else ""
        return _row("router", "ตัวจัดการโมเดล (llama-server)", "Model router (llama-server)", port,
                    "ok" if st == 200 else "down", ms, models=models, loaded=loaded, build=build,
                    max_instances=(p or {}).get("max_instances") if isinstance(p, dict) else None)

    def _mcp(self, sid, th, en, port):
        tok = self.cfg["token"]()
        st, raw, ms = _http(port, "/mcp", {"Authorization": "Bearer " + tok} if tok else None)
        state = "ok" if st == 200 else ("auth" if st in (401, 403) else "down")
        extra = {}
        d = _j(raw) if st == 200 else None
        if isinstance(d, dict):
            if isinstance(d.get("provider"), str) and re.fullmatch(r"[a-z0-9_-]{1,24}", d["provider"]):
                extra["provider"] = d["provider"]
            if isinstance(d.get("modules_failed"), dict) and d["modules_failed"]:
                extra["modules_failed"] = sorted(str(k)[:40] for k in d["modules_failed"])[:10]
        return _row(sid, th, en, port, state, ms, **extra)

    def _embed(self):
        port = self.cfg["embed_port"]
        st, _raw, ms = _http(port, "/health")
        if st == 200:
            state = "ok"
        elif st == 503:
            state = "loading"
        elif st is None and not Path(self.cfg["embed_model"]).is_file():
            state = "absent"
        else:
            state = "down"
        return _row("embed", "ค้นตามความหมาย (embedding)", "Semantic search (embedding)", port, state, ms)

    def _stt(self):
        port = self.cfg["stt_port"]
        st, raw, ms = _http(port, "/health")
        d = _j(raw) if st == 200 else None
        detail, device = "", ""
        if isinstance(d, dict) and d.get("server") == "qwen-stt":
            detail = str(d.get("state") or "")[:20]
            state = {"ready": "ok", "idle": "ok", "loading": "loading", "no_model": "missing"}.get(detail, "down")
            device = {"cuda": "gpu", "gpu": "gpu", "cpu": "cpu"}.get(str(d.get("device") or "").lower(), "")
            if not device and state == "ok":
                # [fix-hub b3] /health ว่างจนกว่าจะมีงานแรก — ถาม /v1/status (ต้องใช้โทเคน) แบบเดียวกับแผงบริการของ hub
                # (hub.stt_probe) ไม่งั้นหน้าตรวจระบบโชว์อุปกรณ์ว่างขณะที่ /api/projects บอก gpu ในเวลาเดียวกัน
                tok = self.cfg["token"]()
                if tok:
                    st2, raw2, _ = _http(port, "/v1/status", {"Authorization": "Bearer " + tok})
                    d2 = _j(raw2) if st2 == 200 else None
                    if isinstance(d2, dict):
                        device = {"cuda": "gpu", "gpu": "gpu", "cpu": "cpu"}.get(str(d2.get("device") or "").lower(), "")
        elif st is None and not Path(self.cfg["stt_script"]).is_file():
            state = "missing"
        else:
            state = "down"
        return _row("stt", "พูดแทนพิมพ์ (STT)", "Speech-to-text (STT)", port, state, ms, detail=detail, device=device)

    def _gateway(self):
        port = self.cfg["gateway_port"]
        st, raw, ms = _http(port, "/health")
        d = _j(raw) if st == 200 else None
        up = d.get("upstream_ok") if isinstance(d, dict) else None
        return _row("gateway", "Remote Prompt Gateway", "Remote prompt gateway", port,
                    "ok" if st == 200 else "down", ms, upstream_ok=up if isinstance(up, bool) else None)

    def _scheduler(self):
        path = Path(self.cfg["scheduler_state"])
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _row("scheduler", "ตัวตั้งเวลา (scheduler)", "Scheduler", None, "down", None, heartbeat_age_s=None)
        hb = ((d.get("jobs") or {}).get("heartbeat") or {}) if isinstance(d, dict) else {}
        last = hb.get("lastRunEpoch") if isinstance(hb.get("lastRunEpoch"), (int, float)) else None
        age = round(time.time() - last) if last else None
        pid = ((d.get("runner") or {}).get("pid")) if isinstance(d.get("runner"), dict) else None
        alive = self.cfg["pid_alive"](pid) if pid else None
        if alive is False:
            state = "down"
        elif age is None or age > HEARTBEAT_STALE_S:
            state = "stale"
        else:
            state = "ok" if hb.get("lastRunStatus") in ("ok", None) else "warn"
        return _row("scheduler", "ตัวตั้งเวลา (scheduler)", "Scheduler", None, state, None, heartbeat_age_s=age,
                    heartbeat_status=str(hb.get("lastRunStatus") or "")[:20] or None,
                    heartbeat_message=redact(str(hb.get("message") or ""), self._scrub)[:160] or None,
                    runner_alive=alive)

    def _hub_ports(self):
        rows = []
        live = set(self.cfg["proxies"]())
        projs = [p for p in self.cfg["projects"]() if isinstance(p.get("port"), int)]
        # ตรวจทุกพอร์ตพร้อมกัน: บน Windows การต่อพอร์ตที่ไม่มีใครฟังไม่ได้ RST ทันที (ลองซ้ำจนหมดเวลา 0.5 วินาที)
        # ทีละพอร์ต 14 โปรเจกต์ที่ล่มหมด = 2-7 วินาที เกินเส้นตาย 3 วินาทีของรายงาน (วัด 2026-10-06 ตอน hub ไม่ทำงาน: 2.0 วินาที)
        lat = {}

        def probe(port):
            lat[port] = _tcp_ms(port)
        ths = [threading.Thread(target=probe, args=(p["port"],), daemon=True) for p in projs[:80]]
        for t in ths:
            t.start()
        for t in ths:
            t.join(1.0)
        for p in projs[:80]:
            port = p["port"]
            ms = lat.get(port)
            rows.append({"slug": p.get("slug"), "name": p.get("name"), "port": port,
                         "state": "ok" if ms is not None else "down",
                         "latency_ms": ms, "in_process": port in live})
        bad = [r for r in rows if r["state"] != "ok"]
        return _row("hub", "ฮับ + พอร์ตโปรเจกต์", "Hub + project ports", self.cfg["hub_port"], "ok" if not bad else "warn",
                    0, ports=rows, keep_awake=self.cfg["keep_awake"]())

    # ---------------------------------------------------------------- ประกอบรายงาน
    def _run_all(self):
        jobs = {
            "router": self._router,
            "mcp_web": lambda: self._mcp("mcp_web", "ค้นเว็บ (MCP)", "Web search (MCP)", self.cfg["mcp_web_port"]),
            "mcp_local": lambda: self._mcp("mcp_local", "เครื่องมือในเครื่อง (MCP)", "Local tools (MCP)",
                                           self.cfg["mcp_local_port"]),
            "embed": self._embed, "stt": self._stt, "gateway": self._gateway, "scheduler": self._scheduler,
            "hub": self._hub_ports,
            "gpu": lambda: gpu_info(),
            "logs": lambda: error_lines(self.cfg["log_dir"], self._scrub, live_ports=self.cfg.get("live_ports"),
                                        stats=self._log_stats),
            "models": lambda: models_present(self.cfg["model_dirs"]),
            "memory": memory_status, "disks": disks, "docker": docker_status,
        }
        results = {}

        def run(name, fn):
            try:
                results[name] = fn()
            except Exception as exc:       # noqa: BLE001 — ตัวตรวจตัวเดียวพังต้องไม่ทำให้ทั้งรายงานล้ม
                results[name] = {"error": type(exc).__name__}

        threads = [threading.Thread(target=run, args=(k, f), daemon=True, name="doctor-" + k) for k, f in jobs.items()]
        for t in threads:
            t.start()
        deadline = time.monotonic() + DEADLINE_S
        for t in threads:
            t.join(max(0.0, deadline - time.monotonic()))
        return results, [k for k in jobs if k not in results]

    def report(self, refresh=False):
        with self._lock:
            now = time.monotonic()
            if self._cache and not refresh and now - self._cache[0] < CACHE_S:
                rep = dict(self._cache[1])
                rep["cached"] = True
                return rep
            t0 = time.perf_counter()
            # [fix-hub b3] ตัวลบความลับต่อรายงาน: secrets_util.scrub (โทเคนในเครื่อง) + ค่าจริงของ gateway/Brave key — ใช้กับ
            # ทุกข้อความอิสระในรายงาน (log, heartbeat, ชื่อเทสต์ที่ล้ม) ไม่ใช่แค่ log อย่างเดิม
            self._scrub = value_scrubber(self.cfg.get("secret_files"), self.cfg.get("scrub"))
            self._log_stats = {}
            res, late = self._run_all()
            rep = self._build(res, late)
            rep["took_ms"] = round((time.perf_counter() - t0) * 1000)
            rep["cached"] = False
            self._cache = (time.monotonic(), rep)
            return dict(rep)

    def _keys(self):
        def present(p):
            try:
                return Path(p).is_file() and Path(p).stat().st_size > 0
            except OSError:
                return False
        return {"local_token": present(self.cfg["token_file"]), "brave_key": present(self.cfg["brave_key_file"]),
                "gateway_key": present(self.cfg["gateway_key_file"])}

    def _tests(self):
        try:
            d = json.loads(Path(self.cfg["tests_file"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(d, dict):
            return None
        keep = ("at", "ran", "ok", "failures", "errors", "skipped", "duration_s", "python", "pattern")
        out = {k: d.get(k) for k in keep if k in d}
        if isinstance(d.get("failed"), list):
            out["failed"] = [redact(str(x), self._scrub)[:160] for x in d["failed"][:10]]
        nums = [d.get(k) for k in ("ran", "failures", "errors", "skipped")]
        if all(isinstance(x, int) for x in nums):
            out["passed"] = max(0, nums[0] - nums[1] - nums[2] - nums[3])
        return out

    # บริการที่งาน heartbeat ของ scheduler ตรวจ (mcp-local\scheduler.py CHECKS: llama-server, MCP local, MCP websearch, project hub)
    HEARTBEAT_COVERS = ("router", "mcp_local", "mcp_web", "hub")

    @classmethod
    def _supersede_heartbeat(cls, services):
        """[integ b3 2026-10-06] ผล heartbeat ที่ "ล้ม" แต่การตรวจสดของรายงานนี้เห็นทุกบริการที่มันตรวจปกติ = ผลเก่า ไม่ใช่ปัญหา
        heartbeat รอบแรกยิงทันทีที่ scheduler เปิด และตัวเปิด (start-qwen38.ps1) เปิด scheduler ในขั้น 1 ก่อน router/hub (ขั้น 2-3)
        ผลจึงเป็น "บริการปกติ 2/4 — ล้ม: llama-server, project hub" ค้างไปอีก 30 นาทีหลังเปิดเครื่องทุกครั้ง (วัดสด 22:15 หลังรีบูต)
        หน้า "ตรวจระบบ" เลยขึ้นแถว scheduler สีเหลืองพร้อมข้อความว่า router/hub ล้ม ขัดกับแถว router/hub สีเขียวข้างบน
        ตัว scheduler เองปกติ (โปรเซสยังอยู่ heartbeat ยังใหม่) — ให้ ok และไม่โชว์ข้อความเก่า (heartbeat_status ยังอยู่ใน JSON)
        ถ้าการตรวจสดเห็นบริการใดในชุดนั้นไม่ปกติด้วย คงสถานะ warn ตามเดิม (สองแหล่งเห็นตรงกัน)"""
        st = {s.get("id"): s for s in services}
        sch = st.get("scheduler")
        if not sch or sch.get("state") != "warn" or sch.get("heartbeat_status") in (None, "ok"):
            return
        if all((st.get(k) or {}).get("state") == "ok" for k in cls.HEARTBEAT_COVERS):
            sch["state"] = "ok"
            sch["heartbeat_message"] = None
            sch["heartbeat_superseded"] = True

    def _build(self, res, late):
        services = []
        for k in ("router", "mcp_local", "mcp_web", "embed", "stt", "scheduler", "gateway", "hub"):
            r = res.get(k)
            if not isinstance(r, dict) or "state" not in r:
                names = {"router": ("ตัวจัดการโมเดล", "Model router"), "mcp_local": ("เครื่องมือในเครื่อง", "Local tools"),
                         "mcp_web": ("ค้นเว็บ", "Web search"), "embed": ("embedding", "Embedding"), "stt": ("STT", "STT"),
                         "scheduler": ("ตัวตั้งเวลา", "Scheduler"), "gateway": ("Gateway", "Gateway"),
                         "hub": ("ฮับ", "Hub")}[k]
                r = _row(k, names[0], names[1], None, "timeout" if k in late else "error", None)
            services.append(r)
        self._supersede_heartbeat(services)
        gpu_rows, gpu_err = (res.get("gpu") if isinstance(res.get("gpu"), tuple) else (None, "timeout"))
        logs = res.get("logs") if isinstance(res.get("logs"), tuple) else ([], 0)
        models = res.get("models") if isinstance(res.get("models"), list) else []
        mem = res.get("memory") if isinstance(res.get("memory"), dict) and "error" not in res.get("memory") else None
        dsk = res.get("disks") if isinstance(res.get("disks"), list) else []
        dock = res.get("docker") if isinstance(res.get("docker"), dict) and "usable" in res.get("docker") else \
            {"usable": False, "reason_th": "ตรวจไม่ได้", "reason_en": "check failed"}
        router = services[0]
        keys = self._keys()
        tests = self._tests()
        # ชื่อฟิลด์ระดับบนเลือกให้ตัวแปลงของหน้า "ตรวจระบบ" (hub_i18n_parts.py, owner ui) อ่านได้ตรงๆ — ค่าประกอบที่หน้าไม่ต้อง
        # แสดงอยู่ใต้ _meta (หน้านั้นซ่อนคีย์ที่ขึ้นต้นด้วย "_" ไม่เอาไปโชว์เป็นแถว "อื่นๆ")
        rep = {
            "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "services": services,
            "models": {"loaded": router.get("loaded") or [], "available": router.get("models") or [], "files": models},
            "versions": {"llama_cpp": router.get("build") or self.cfg.get("llama_dir_build") or None,
                         "python": sys.version.split()[0], "os": os_name()[:60],
                         "hub": self.cfg.get("hub_version")},
            "gpu": gpu_rows, "memory": mem, "disks": dsk, "keys": keys, "brave_key": bool(keys.get("brave_key")),
            "docker": dock, "errors": logs[0], "tests": tests,
            "_meta": {"gpu_error": gpu_err, "errors_skipped": logs[1], "late": late,
                      # [fix-hub b3] ไฟล์ log ที่ไม่นับ: เก่ากว่า ERR_MAX_AGE_S / ของพอร์ตทดสอบ
                      "errors_old_files": int(self._log_stats.get("old_files", 0)),
                      "errors_test_logs": int(self._log_stats.get("test_logs", 0)),
                      "errors_max_age_days": round(ERR_MAX_AGE_S / 86400.0, 1)},
        }
        rep["fixes"] = self._fixes(rep)
        bad = [s for s in services if s["state"] in ("down", "auth", "timeout", "error", "missing")]
        warn = [s for s in services if s["state"] in ("warn", "stale", "loading", "absent")]
        real_fixes = [f for f in rep["fixes"] if f.get("severity") != "info"]
        rep["overall"] = "error" if any(s["id"] in ("router", "hub") for s in bad) else (
            "warn" if bad or warn or real_fixes else "ok")
        return rep

    def _fixes(self, rep):
        out = []

        def add(key, *args):
            th, en = FIX[key]
            out.append({"id": key, "severity": FIX_SEVERITY.get(key, "warn"),
                        "th": th % args if args else th, "en": en % args if args else en})
        st = {s["id"]: s for s in rep["services"]}
        r = st["router"]["state"]
        if r in ("down", "timeout", "error"):
            add("router")
        elif r == "auth":
            add("router_auth")
        for sid, key in (("mcp_local", "mcp_local"), ("mcp_web", "mcp_web")):
            if st[sid]["state"] in ("down", "timeout", "error"):
                add(key)
            elif st[sid]["state"] == "auth":
                add("mcp_auth")
        if st["embed"]["state"] in ("down", "timeout", "error"):
            add("embed")
        elif st["embed"]["state"] == "absent":
            add("embed_absent")
        if st["stt"]["state"] in ("down", "timeout", "error"):
            add("stt")
        elif st["stt"]["state"] == "missing":
            add("stt_model")
        if st["scheduler"]["state"] in ("down", "stale"):
            add("scheduler")
        if st["gateway"]["state"] in ("down", "timeout", "error"):
            add("gateway")
        if st["hub"]["state"] == "warn":
            add("hub_port")
        for d in rep["disks"]:
            if d.get("present") and d.get("free_gb") is not None and d["free_gb"] < DISK_LOW_GB:
                add("disk", d["drive"], d["free_gb"])
            if d.get("drive") == "E:" and not d.get("present"):
                add("drive_e")
        m = rep["memory"]
        if m and m.get("commit_free_gb") is not None and m["commit_free_gb"] < COMMIT_LOW_GB:
            add("commit", m["commit_free_gb"])
        if rep["gpu"] == [] or (rep["gpu"] is None and rep["_meta"]["gpu_error"] not in ("timeout",)):
            add("gpu_missing")
        for g in rep["gpu"] or []:
            if isinstance(g.get("temp_c"), int) and g["temp_c"] >= GPU_HOT_C:
                add("gpu_hot", g["temp_c"])
        if not rep["keys"]["local_token"]:
            add("token")
        if not rep["keys"]["brave_key"]:
            add("brave")
        if not rep["docker"].get("usable"):
            out.append({"id": "docker", "severity": FIX_SEVERITY["docker"],
                        "th": FIX["docker"][0] % rep["docker"].get("reason_th", ""),
                        "en": FIX["docker"][1] % rep["docker"].get("reason_en", "")})
        t = rep["tests"]
        if t and ((t.get("failures") or 0) + (t.get("errors") or 0)) > 0:
            add("tests", (t.get("failures") or 0) + (t.get("errors") or 0))
        return out


def localize(rep, lang="th"):
    """สำเนาของรายงานที่เติมข้อความภาษาเดียวของหน้า: services[].name, docker.reason (รายงานในแคชเป็นสองภาษา ไม่แตะ)"""
    th = lang == "th"
    out = dict(rep)
    out["services"] = [dict(s, name=s.get("name_th" if th else "name_en") or s.get("id")) for s in rep.get("services") or []]
    if not th:
        # ข้อความ heartbeat มาจาก scheduler (เขียนเป็นภาษาไทยอย่างเดียว) — หน้าอังกฤษไม่โชว์ข้อความไทยปน (ภาพ 1440 en 2026-10-06)
        for s in out["services"]:
            if isinstance(s.get("heartbeat_message"), str) and re.search("[฀-๿]", s["heartbeat_message"]):
                s["heartbeat_message"] = None
    if isinstance(rep.get("docker"), dict):
        out["docker"] = dict(rep["docker"], reason=rep["docker"].get("reason_th" if th else "reason_en") or "")
    out["lang"] = "th" if th else "en"
    return out


STATE_WORD = {"th": {"ok": "ปกติ", "down": "ไม่ทำงาน", "auth": "โทเคนไม่ตรง", "loading": "กำลังโหลด", "missing": "ไม่มี",
                     "absent": "ไม่มีไฟล์โมเดล", "stale": "ไม่ขยับ", "warn": "มีข้อสังเกต", "timeout": "ตรวจไม่ทัน",
                     "error": "ตรวจไม่ได้"},
              "en": {"ok": "ok", "down": "down", "auth": "token rejected", "loading": "loading", "missing": "missing",
                     "absent": "model file missing", "stale": "stale", "warn": "warning", "timeout": "timed out",
                     "error": "check failed"}}


def report_text(rep, lang="th"):
    """รายงานแบบข้อความสำหรับปุ่ม "คัดลอกรายงาน" — มาจาก JSON ที่ลบความลับแล้ว ไม่มีโทเคน/คีย์ (บอกแค่มี/ไม่มี)"""
    th = lang == "th"
    W = STATE_WORD["th" if th else "en"]
    L = []
    overall = {"ok": W["ok"], "warn": W["warn"], "error": "มีปัญหา" if th else "problem"}.get(rep.get("overall"), "?")
    L.append(("Qwen3.8 — รายงานตรวจระบบ %s (รวม: %s)" if th else "Qwen3.8 — system check %s (overall: %s)")
             % (rep.get("checked_at"), overall))
    L.append("")
    L.append("[บริการ]" if th else "[Services]")
    for s in rep.get("services") or []:
        name = s.get("name_th" if th else "name_en")
        extra = []
        if s.get("latency_ms") is not None and s["id"] != "hub":
            extra.append("%d ms" % s["latency_ms"])
        if s["id"] == "router" and s.get("loaded"):
            extra.append(("โหลดอยู่: " if th else "loaded: ") + ", ".join(m["id"] for m in s["loaded"]))
        if s["id"] == "scheduler" and s.get("heartbeat_age_s") is not None:
            extra.append(("heartbeat %d นาทีก่อน" if th else "heartbeat %d min ago") % (s["heartbeat_age_s"] // 60))
        if s["id"] == "stt" and s.get("device"):
            extra.append(s["device"].upper())
        if s["id"] == "hub":
            ports = s.get("ports") or []
            extra.append(("พอร์ตโปรเจกต์ %d/%d ตอบ" if th else "project ports %d/%d up")
                         % (len([p for p in ports if p["state"] == "ok"]), len(ports)))
            extra.append(("แชตที่กำลังตอบ %s" if th else "streams %s") % s.get("keep_awake"))
        port = (" (:%s)" % s["port"]) if s.get("port") else ""
        L.append("- %s%s: %s%s" % (name, port, W.get(s.get("state"), s.get("state")),
                                    (" (" + "; ".join(extra) + ")") if extra else ""))
    v = rep.get("versions") or {}
    L.append("")
    L.append("[เวอร์ชัน]" if th else "[Versions]")
    L.append("- llama.cpp %s · Python %s · %s" % (v.get("llama_cpp"), v.get("python"), v.get("os")))
    files = (rep.get("models") or {}).get("files") or []
    if files:
        L.append(("- ไฟล์โมเดล %d ไฟล์: " if th else "- %d model files: ") % len(files)
                 + ", ".join("%s (%.1f GB)" % (f["name"], f["size_gb"]) for f in files))
    L.append("")
    L.append("[ฮาร์ดแวร์]" if th else "[Hardware]")
    for g in rep.get("gpu") or []:
        L.append("- GPU %s: VRAM %s/%s MiB, %s °C, driver %s" % (g.get("name"), g.get("mem_used_mib"),
                                                                 g.get("mem_total_mib"), g.get("temp_c"), g.get("driver")))
    if not rep.get("gpu"):
        gerr = (rep.get("_meta") or {}).get("gpu_error")
        L.append("- GPU: " + ("ไม่พบ" if th else "not found") + (" (%s)" % gerr if gerr else ""))
    m = rep.get("memory") or {}
    if m:
        L.append(("- RAM ว่าง %.1f/%.1f GB · commit ว่าง %.1f/%.1f GB" if th else "- RAM free %.1f/%.1f GB · commit free %.1f/%.1f GB")
                 % (m["ram_free_gb"], m["ram_total_gb"], m["commit_free_gb"], m["commit_limit_gb"]))
    for d in rep.get("disks") or []:
        if d.get("present"):
            L.append(("- ดิสก์ %s ว่าง %.1f/%.1f GB" if th else "- Drive %s free %.1f/%.1f GB") % (d["drive"], d["free_gb"], d["total_gb"]))
        else:
            L.append(("- ดิสก์ %s ไม่พบ" if th else "- Drive %s not present") % d["drive"])
    k = rep.get("keys") or {}
    yn = (lambda b: "มี" if b else "ไม่มี") if th else (lambda b: "yes" if b else "no")
    L.append(("- ไฟล์โทเคนบริการ: %s · Brave key: %s · Gateway key: %s" if th else
              "- Local token file: %s · Brave key: %s · Gateway key: %s")
             % (yn(k.get("local_token")), yn(k.get("brave_key")), yn(k.get("gateway_key"))))
    dk = rep.get("docker") or {}
    L.append("- Docker: %s (%s)" % (yn(dk.get("usable")), dk.get("reason_th" if th else "reason_en")))
    t = rep.get("tests")
    if t:
        L.append(("- ชุดทดสอบล่าสุด %s: รัน %s ข้อ ไม่ผ่าน %s ผิดพลาด %s ข้าม %s" if th else
                  "- Last test run %s: ran %s, failures %s, errors %s, skipped %s")
                 % (t.get("at"), t.get("ran"), t.get("failures"), t.get("errors"), t.get("skipped")))
    fixes = rep.get("fixes") or []
    if fixes:
        L.append("")
        L.append("[วิธีแก้ที่แนะนำ]" if th else "[Suggested fixes]")
        for f in fixes:
            L.append("- " + f["th" if th else "en"])
    errs = rep.get("errors") or []
    if errs:
        L.append("")
        L.append("[ข้อผิดพลาดล่าสุดใน log (ลบความลับแล้ว)]" if th else "[Latest log errors (redacted)]")
        for e in errs:
            L.append("- %s: %s" % (e["file"], e["line"]))
    return "\n".join(L) + "\n"
