# -*- coding: utf-8 -*-
"""tools_creative.py — สั่ง AI Creative Studio (ComfyUI + Wan 2.2 TI2V 5B) สร้างวิดีโอจากหน้าแชต

ทำไมต้องมีไฟล์นี้ (2026-10-21)
-----------------------------
Creative Studio ติดตั้งแยกเป็นโปรแกรมต่างหาก (D:\\LLM\\creative, ComfyUI ที่พอร์ต 8188) ผู้ใช้ต้องเปิดเองแล้วลาก
workflow เอง — โมเดลแชตสั่งอะไรไม่ได้เลย ไฟล์นี้ให้เครื่องมือสามตัว (ผิวเต็ม /mcp) + สาม action บนผิวย่อ /fast
  creative_video   [ยืนยัน]  ข้อความ -> วิดีโอ หรือ ภาพแนบ -> วิดีโอ (Wan 2.2 TI2V 5B, 24 fps) ลงโฟลเดอร์ outputs ของโปรเจกต์
  creative_status  อ่านอย่างเดียว  สถานะ Creative Studio/GPU/โมเดลที่ติดตั้ง และงานของโปรเจกต์นี้ (เสร็จแล้วได้ลิงก์)
  creative_cancel  [ทันที]  ยกเลิกงานของโปรเจกต์นี้ (แตะแค่งานของตัวเอง จึงไม่มีขั้นยืนยัน — แบบเดียวกับ research_cancel)

กฎที่ยึด
  S03  creative_video เปลี่ยนเครื่องจริง (เปิดโปรเซส ComfyUI, ปลดโมเดลแชตออกจาก GPU, ใช้ GPU หลายนาที, เขียนไฟล์) จึงคืน
       confirm_token + บล็อก REVIEW ที่มีทุกค่าที่จะใช้จริง (prompt เต็ม, ขนาด, เฟรม, seed ที่สุ่มไว้แล้ว, ชื่อไฟล์) ก่อนเสมอ
       token ผูกกับ sha256 ของค่าชุดนั้น — อนุมัติ prompt หนึ่งแล้วเอา token ไปสร้างอีก prompt ไม่ได้
  S04  project มาจาก URL (server.py เติม) ภาพตั้งต้นต้องผ่าน guard.check_read, ผลลัพธ์ลง data\\<slug>\\outputs เท่านั้น
       (ผ่าน guard.check_write + ด่าน "outputs ต้องเป็นโฟลเดอร์จริง" แบบเดียวกับ make_file) งานของโปรเจกต์อื่นมองไม่เห็น
       (บอกได้แค่ว่า GPU ไม่ว่าง) และ URL ของ ComfyUI/router รับเฉพาะ loopback (token ของเครื่องไม่ออกนอกเครื่อง)
  S07  ข้อความผิดพลาดจาก ComfyUI เป็นข้อมูลภายนอก — ตัดอักขระควบคุมและความยาวก่อนส่งให้โมเดล

GPU ใบเดียว (RTX 4090 24 GB) ใช้ร่วมกันระหว่างโมเดลแชตกับ Wan
  Wan 2.2 5B fp16 (10 GB) + umt5-xxl fp8 (6.7 GB) + VAE ต้องการ VRAM ว่างราว 14 GB ตอนทำงาน แต่ 27B ของแชตถือ VRAM เกือบหมด
  ก่อนสั่งงานจึง "ทำที่ว่าง": ปลดโมเดลแชตที่ "ว่าง" (ไม่มี slot กำลังตอบ) ออกจาก router 8099 ด้วย /models/unload (วิธีเดียวกับ
  stt_make_room ของ hub) — ระหว่างเรียกเครื่องมือ โมเดลที่สั่งงานอยู่ไม่ได้ถือ slot (คำขอ completion จบไปแล้ว) จึงปลดได้
  เสร็จงานแล้ว POST /free ให้ ComfyUI คืน VRAM และปลดโมเดลแชตที่ "ถูกโหลดระหว่างงาน" (โหลดตอน VRAM ไม่พอ = ชั้นส่วนใหญ่อยู่
  บน CPU ช้ามาก) ให้ router โหลดใหม่เต็มๆ ตอนคุยครั้งถัดไป (~10-40 วินาที) — ถ้ามีแชตอื่นกำลังตอบอยู่จะไม่แตะโมเดลนั้น
  ถ้า VRAM ยังไม่พอและมีโมเดลที่ปลดไม่ได้ (กำลังตอบ) = ไม่สั่งงาน บอกให้ลองใหม่ทีหลัง (ComfyUI ยังไม่ถูกแตะ)

การรอผล
  หน้าแชตรอผลเครื่องมือได้ราว 5 นาที (mcpRequestTimeoutSeconds ของ WebUI ค่าเริ่มต้น 300) creative_video จึงรอในการเรียก
  ไม่เกิน WAIT_IN_CALL_S (230) ถ้าเสร็จทันคืนลิงก์เลย ไม่ทันคืน id ให้ถาม creative_status (เธรดเฝ้างานทำต่อเอง: คัดลอกไฟล์,
  คืน VRAM) — creative_status ของงานที่ยังทำอยู่หน่วงไว้ STATUS_WAIT_S ก่อนตอบ กันโมเดลวนถามไม่หยุด (บทเรียนจาก research)
  สถานะงานเก็บเป็นไฟล์ data\\<slug>\\creative\\<id>.json — MCP รีสตาร์ตแล้วยังถามต่อได้ (ตรวจ /history ของ ComfyUI แล้วเก็บผลให้)

ผลลัพธ์
  SaveWEBM (vp9, crf 16) ตาม workflow ตัวอย่างของ Creative Studio -> .webm แล้วแปลงเป็น .mp4 (H.264 yuv420p) ด้วย ffmpeg
  ถ้าหาเจอ (เปิดได้ทุกเครื่อง) คืนลิงก์ /_qwen/out/<ชื่อ> ที่ hub เสิร์ฟให้ทุกพอร์ตโปรเจกต์ (สัญญา K2)

ทดสอบ: tests\\test_creative_tools.py (ComfyUI/router ปลอมในโปรเซสเทสต์ ไม่ใช้ GPU/โมเดลจริง)
ตัวแปรสภาพแวดล้อม (ใช้ในเทสต์เป็นหลัก): QWEN_CREATIVE_URL, QWEN_CREATIVE_ROUTER_URL, QWEN_CREATIVE_START_CMD (JSON argv;
"" = ไม่เปิดให้เอง), QWEN_CREATIVE_ROOT, QWEN_CREATIVE_NEED_MIB, QWEN_CREATIVE_WAIT_S, QWEN_CREATIVE_STATUS_WAIT_S
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import secrets as _secrets
import struct
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from urllib.parse import quote, urlsplit

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import guard  # noqa: E402

_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.append(_PARENT)                   # secrets_util อยู่ที่ C:\LLM — ต่อท้าย ไม่แทรกหน้า stdlib
try:
    import secrets_util  # noqa: E402
except Exception:                              # noqa: BLE001 — ไม่มี = ปลดโมเดลแชตไม่ได้ (บอกเหตุผล) แต่ยังสร้างวิดีโอได้
    secrets_util = None

try:
    import tools_docs as _docs  # noqa: E402   (project_dirs / resolve_input / out_link / safe_name — สัญญาเดียวกับ make_file)
except Exception:                              # noqa: BLE001
    _docs = None
try:
    import tools_media as _media  # noqa: E402  (หา ffmpeg)
except Exception:                              # noqa: BLE001
    _media = None

# ------------------------------------------------------------------ ค่าคงที่
COMFY_DEFAULT_URL = "http://127.0.0.1:8188"
ROUTER_DEFAULT_URL = "http://127.0.0.1:8099"
START_SCRIPT = r"C:\LLM\start-creative-studio.ps1"
CREATIVE_ROOT_DEFAULT = r"D:\LLM\creative"
MODELS_SUBDIR = os.path.join("ComfyUI_windows_portable", "ComfyUI", "models")
UNET_FILE = "wan2.2_ti2v_5B_fp16.safetensors"
CLIP_FILE = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
VAE_FILE = "wan2.2_vae.safetensors"
MODEL_FILES = ((UNET_FILE, "diffusion_models"), (CLIP_FILE, "text_encoders"), (VAE_FILE, "vae"))

FPS = 24
DEFAULT_SECONDS = 2.0
MIN_FRAMES, MAX_FRAMES = 13, 121            # Wan: เฟรม = 4k+1 · 121 เฟรม = 5 วินาที (ค่าที่ workflow ตัวอย่างบอกว่าเหมาะสุด)
DEFAULT_SIZE = (1280, 704)
PORTRAIT_SIZE = (704, 1280)
MIN_SIDE, MAX_SIDE, SIDE_STEP = 256, 1280, 32
DEFAULT_STEPS, MIN_STEPS, MAX_STEPS = 30, 4, 50
DEFAULT_CFG, MIN_CFG, MAX_CFG = 5.0, 1.0, 10.0
SHIFT = 8.0
SAMPLER, SCHEDULER = "uni_pc", "simple"
WEBM_CRF = 16.0
MAX_PROMPT_CHARS = 2000
MAX_NEGATIVE_CHARS = 1500
# ข้อความเชิงลบมาตรฐานของ Wan (ตรงกับ workflow ตัวอย่าง 01/02 ของ Creative Studio)
DEFAULT_NEGATIVE = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，"
                    "丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，"
                    "静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走")

IMAGE_EXTS = frozenset((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"))
MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 ** 3

GPU_MIN_TOTAL_MIB = 12000                   # การ์ดในตัว (RTX 1000 Ada 6 GB) สร้างวิดีโอไม่ได้ — ต้องเป็น eGPU 4090
GPU_NEED_MIB = int(os.environ.get("QWEN_CREATIVE_NEED_MIB") or 14000)
ROOM_WAIT_S = 20.0                          # รอ VRAM คืนหลังปลดโมเดล (วัดของ hub: ~1 วินาทีต่อโมเดล)
START_TIMEOUT_S = 150.0                     # start-creative-studio.ps1 รอ ComfyUI พร้อมเองไม่เกิน 120 วินาที
START_LOG = r"C:\LLM\logs\creative-start.log"   # ผลลัพธ์ของตัวเปิด (ต่อท้ายทุกครั้ง) — ห้ามใช้ pipe ดู _run_starter
WAIT_IN_CALL_S = float(os.environ.get("QWEN_CREATIVE_WAIT_S") or 230.0)
STATUS_WAIT_S = float(os.environ.get("QWEN_CREATIVE_STATUS_WAIT_S") or 20.0)
JOB_MAX_S = 45 * 60.0                       # งานที่นานกว่านี้ถือว่าค้าง — interrupt แล้วรายงาน
POLL_S = 2.0
QUEUE_CHECK_S = 10.0                        # ตรวจว่างานยังอยู่ในคิวของ ComfyUI ทุกกี่วินาที (history ว่าง + ไม่อยู่ในคิว = หายไป)
HTTP_TIMEOUT = 8.0
JOB_SUBDIR = "creative"
KEEP_JOBS = 30
ACTION = "creative_video"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_RUN_LOCK = threading.Lock()                # งานเดียวทั้งเครื่อง (GPU ใบเดียว)
_JOBS: dict[str, "Job"] = {}
_JOBS_LOCK = threading.Lock()
_RUNNING: list = []                         # [Job] ที่กำลังทำ (0 หรือ 1 ตัว)
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")
# seed ที่สุ่มให้ / ชื่อไฟล์ที่ตั้งให้ตอนขอ token ต้องเป็นค่าเดิมตอน local_confirm เล่นซ้ำ (เล่นซ้ำด้วยอาร์กิวเมนต์เดิม = ไม่มี seed/name)
# ไม่งั้น detail ที่ token ผูกอยู่ไม่ตรง (เจอจริงใน E2E 2026-10-21: "confirm_token ใช้ไม่ได้" ทุกครั้งที่โมเดลไม่ส่ง seed)
# จำไว้ตามชุดพารามิเตอร์ที่ normalize แล้ว อายุเท่า token (CONFIRM_TTL_MAX) ใช้แล้วทิ้ง = คำขอใหม่เหมือนเดิมได้ seed ใหม่
_MEMO: dict[str, tuple[float, int, str]] = {}
_MEMO_LOCK = threading.Lock()
MEMO_TTL = 960.0


class CreativeError(Exception):
    """ข้อความภาษาไทยพร้อมส่งให้โมเดล"""


# ------------------------------------------------------------------ ตัวช่วยทั่วไป
def _s(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _clean(text, limit: int = 600) -> str:
    """ข้อความจากบริการภายนอก: ตัดอักขระควบคุม/กำหนดทิศทาง และความยาว (S07)"""
    t = _CTRL_RE.sub("", _s(text)).strip()
    return t if len(t) <= limit else t[:limit] + "…"


def _human(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return str(n)


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return "%d:%02d" % (seconds // 60, seconds % 60) if seconds < 3600 else "%d:%02d:%02d" % (
        seconds // 3600, (seconds // 60) % 60, seconds % 60)


def _loopback(url: str, default: str) -> tuple[str, int]:
    """(host, port) ของบริการ — รับเฉพาะ loopback (token ของเครื่องต้องไม่ถูกส่งออกนอกเครื่อง)"""
    u = urlsplit(_s(url).strip() or default)
    host = (u.hostname or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1") or u.scheme not in ("http", ""):
        u = urlsplit(default)
        host = u.hostname
    return host, int(u.port or 80)


def comfy_addr() -> tuple[str, int]:
    return _loopback(os.environ.get("QWEN_CREATIVE_URL", ""), COMFY_DEFAULT_URL)


def router_addr() -> tuple[str, int]:
    return _loopback(os.environ.get("QWEN_CREATIVE_ROUTER_URL", ""), ROUTER_DEFAULT_URL)


def creative_root() -> str:
    return os.environ.get("QWEN_CREATIVE_ROOT") or CREATIVE_ROOT_DEFAULT


def _http(host: str, port: int, method: str, path: str, body=None, headers=None, timeout: float = HTTP_TIMEOUT,
          raw: bool = False, max_bytes: int = 8 * 1024 * 1024):
    """(status, json|bytes|None) — (None, None) เมื่อต่อไม่ติด/หมดเวลา ไม่โยน exception"""
    conn = None
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        h = {"Host": "%s:%d" % (host, port), "Accept": "*/*"}
        if headers:
            h.update(headers)
        data = body
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        blob = r.read(max_bytes + 1)
        if len(blob) > max_bytes:
            return r.status, None
        if raw:
            return r.status, blob
        try:
            return r.status, json.loads(blob.decode("utf-8")) if blob else {}
        except (ValueError, UnicodeDecodeError):
            return r.status, None
    except (OSError, http.client.HTTPException, ValueError):
        return None, None
    finally:
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass


def _comfy(method: str, path: str, body=None, timeout: float = HTTP_TIMEOUT, raw: bool = False, max_bytes=None):
    host, port = comfy_addr()
    kw = {"timeout": timeout, "raw": raw}
    if max_bytes:
        kw["max_bytes"] = max_bytes
    return _http(host, port, method, path, body, **kw)


def _router(method: str, path: str, body=None, timeout: float = HTTP_TIMEOUT):
    if secrets_util is None:
        return None, None
    try:
        headers = dict(secrets_util.auth_headers())
    except Exception:                          # noqa: BLE001 — อ่าน token ไม่ได้ = ถือว่า router ไม่ถึง
        return None, None
    host, port = router_addr()
    return _http(host, port, method, path, body, headers=headers, timeout=timeout)


# ------------------------------------------------------------------ ComfyUI: สถานะ/GPU
def comfy_stats():
    """dict จาก /system_stats หรือ None ถ้า ComfyUI ไม่เปิด"""
    st, doc = _comfy("GET", "/system_stats", timeout=4.0)
    return doc if st == 200 and isinstance(doc, dict) else None


def comfy_device(stats) -> dict | None:
    """{name, total_mib, free_mib} ของการ์ดที่ ComfyUI ใช้ (ตัวแรก) หรือ None"""
    for d in (stats or {}).get("devices") or []:
        if not isinstance(d, dict):
            continue
        try:
            total = int(d.get("vram_total") or 0) // (1024 * 1024)
            free = int(d.get("vram_free") or 0) // (1024 * 1024)
        except (TypeError, ValueError):
            continue
        return {"name": _clean(d.get("name"), 120), "type": _s(d.get("type")), "total_mib": total, "free_mib": free}
    return None


def _nvidia_smi_4090() -> dict | None:
    """ข้อมูลการ์ดจาก nvidia-smi เมื่อ ComfyUI ยังไม่เปิด (เลือก 4090 ก่อน ไม่งั้นใบที่ VRAM มากสุด — กฎเดียวกับ start-creative-studio.ps1)"""
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, errors="replace",
                             timeout=8, creationflags=_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            try:
                rows.append({"index": int(parts[0]), "name": parts[1], "total_mib": int(float(parts[2])),
                             "free_mib": int(float(parts[3]))})
            except ValueError:
                continue
    if not rows:
        return None
    pick = next((r for r in rows if "4090" in r["name"]), None) or max(rows, key=lambda r: r["total_mib"])
    return pick


def installed_models() -> list[tuple[str, bool, int]]:
    """[(ชื่อไฟล์, มีอยู่?, ไบต์)] ของโมเดล Wan 2.2 สามไฟล์ในโฟลเดอร์ของ ComfyUI"""
    base = os.path.join(creative_root(), MODELS_SUBDIR)
    rows = []
    for name, sub in MODEL_FILES:
        p = os.path.join(base, sub, name)
        try:
            size = os.path.getsize(p)
            rows.append((name, True, size))
        except OSError:
            rows.append((name, False, 0))
    return rows


def _start_cmd() -> list[str]:
    raw = os.environ.get("QWEN_CREATIVE_START_CMD")
    if raw is not None:
        raw = raw.strip()
        if not raw:
            return []
        try:
            cmd = json.loads(raw)
            if isinstance(cmd, list) and all(isinstance(x, str) for x in cmd):
                return cmd
        except ValueError:
            pass
        return []
    if os.name != "nt" or not os.path.isfile(START_SCRIPT):
        return []
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", START_SCRIPT, "-NoBrowser"]


def _start_log_path() -> str:
    return os.environ.get("QWEN_CREATIVE_START_LOG") or START_LOG


def _run_starter(cmd: list[str]) -> tuple[int, str]:
    """รันตัวเปิด (PowerShell) -> (รหัสออก, ท้ายผลลัพธ์) — ผลลัพธ์ลงไฟล์ ไม่ใช่ pipe

    ตัวเปิดสร้าง ComfyUI ด้วย Start-Process -RedirectStandard* ซึ่งให้ลูกสืบทอด handle ทุกตัวของ PowerShell
    (bInheritHandles) — ถ้า stdout/stderr ของตัวเปิดเป็น pipe ของเรา ComfyUI จะถือปลายเขียนไว้ตลอดอายุของมัน
    communicate() จึงรอ EOF ไม่มีวันจบ (พบจริง 2026-10-21: งานค้างที่ "starting" แม้ ComfyUI พร้อมแล้ว)
    ใช้ไฟล์ + wait(timeout) แทน: รอแค่ตัวเปิดจบ หมดเวลา = ฆ่าตัวเปิด (ComfyUI ที่มันเปิดไว้ยังอยู่) แล้วไปตรวจ /system_stats ต่อ"""
    path = _start_log_path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        fh = open(path, "a+b")
    except OSError:
        fh = tempfile.TemporaryFile("w+b", prefix="creative-start-")
    with fh:
        fh.write(("\n# %s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), " ".join(cmd))).encode("utf-8"))
        fh.flush()
        pos = fh.tell()
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                                    creationflags=_NO_WINDOW)
        except OSError as exc:
            return 1, _clean(exc, 200)
        try:
            rc = proc.wait(timeout=START_TIMEOUT_S)
            note = ""
        except subprocess.TimeoutExpired:
            proc.kill()
            rc, note = 124, "หมดเวลา %d วินาที · " % int(START_TIMEOUT_S)
        try:
            fh.seek(pos)
            out = fh.read().decode("utf-8", "replace")
        except (OSError, ValueError):
            out = ""
    return rc, _clean(note + out, 400)


def ensure_comfy(log: list) -> dict:
    """ComfyUI พร้อม -> stats · ไม่พร้อม = เปิดด้วย start-creative-studio.ps1 -NoBrowser แล้วรอ ไม่ได้ = CreativeError"""
    stats = comfy_stats()
    if stats is not None:
        return stats
    cmd = _start_cmd()
    if not cmd:
        raise CreativeError("Creative Studio (ComfyUI ที่ %s:%d) ยังไม่เปิด และเปิดให้เองไม่ได้ในสภาพแวดล้อมนี้ — เปิด "
                            "C:\\LLM\\Creative-Studio.cmd แล้วสั่งใหม่" % comfy_addr())
    log.append("เปิด Creative Studio ให้ (start-creative-studio.ps1 -NoBrowser)")
    t0 = time.monotonic()
    rc, tail = _run_starter(cmd)
    deadline = time.monotonic() + max(5.0, START_TIMEOUT_S - (time.monotonic() - t0))
    while time.monotonic() < deadline:
        stats = comfy_stats()
        if stats is not None:
            log.append("Creative Studio พร้อมใน %d วินาที" % int(time.monotonic() - t0))
            return stats
        if rc not in (0, None):
            break
        time.sleep(1.0)
    raise CreativeError("เปิด Creative Studio ไม่สำเร็จ (รหัส %s) %s — ดู C:\\LLM\\logs\\creative-studio.err.log" % (rc, tail))


# ------------------------------------------------------------------ router: ปลดโมเดลแชตให้มีที่ว่าง
def chat_models() -> list[dict] | None:
    st, doc = _router("GET", "/models")
    if st != 200 or not isinstance(doc, dict):
        return None
    rows = []
    for m in doc.get("data") or []:
        if isinstance(m, dict) and isinstance(m.get("id"), str):
            rows.append({"id": m["id"], "state": _s(((m.get("status") or {}).get("value")))})
    return rows


def _model_idle(mid: str) -> bool:
    # /slots?model= ของโมเดลที่โหลดอยู่แล้วไม่ทำให้อะไรถูกโหลด (ต่างจากโมเดลที่ยังไม่โหลด — ห้ามถามแบบนั้น)
    st, slots = _router("GET", "/slots?model=" + quote(mid, safe=""))
    if st != 200 or not isinstance(slots, list):
        return False
    return not any(isinstance(s, dict) and s.get("is_processing") for s in slots)


def unload_idle_models() -> tuple[list[str], list[str], str]:
    """ปลดโมเดลแชตที่โหลดอยู่และว่าง -> (ปลดแล้ว, ปลดไม่ได้เพราะกำลังทำงาน, เหตุผลเมื่อทำอะไรไม่ได้)"""
    rows = chat_models()
    if rows is None:
        return [], [], "router_down"
    unloaded, busy = [], []
    for m in rows:
        if m["state"] == "loading":
            busy.append(m["id"])
            continue
        if m["state"] != "loaded":
            continue
        if not _model_idle(m["id"]):
            busy.append(m["id"])
            continue
        st, _d = _router("POST", "/models/unload", {"model": m["id"]}, timeout=20.0)
        (unloaded if st == 200 else busy).append(m["id"])
    return unloaded, busy, ""


def real_free_mib(dev: dict) -> int:
    """VRAM ว่างจริงของการ์ดที่ ComfyUI ใช้ — ใช้ค่าที่น้อยกว่าระหว่าง /system_stats กับ nvidia-smi

    ComfyUI 0.38 รายงาน vram_free จากมุมมองของตัวเองเท่านั้น ไม่หักที่โปรเซสอื่นถืออยู่ (วัดจริง 2026-10-21:
    llama-server ถือ 22 GB · nvidia-smi ว่าง 1,440 MiB · /system_stats บอกว่าง 22,647 MiB) — ถ้าเชื่อ ComfyUI
    จะไม่ปลดโมเดลแชตเลย แล้ว Wan ต้องทยอยโหลดน้ำหนักผ่าน VRAM ที่เหลือนิดเดียว (ช้า/เสี่ยงหน่วยความจำไม่พอ)"""
    free = dev["free_mib"]
    smi = _nvidia_smi_4090()
    if smi and (abs(smi["total_mib"] - dev["total_mib"]) <= 512 or ("4090" in smi["name"] and "4090" in dev["name"])):
        free = min(free, smi["free_mib"])
    return free


def make_room(log: list) -> tuple[int, list[str]]:
    """VRAM ว่างพอสำหรับ Wan? ไม่พอ = ปลดโมเดลแชตที่ว่าง แล้วรอ — คืน (VRAM ว่าง MiB, โมเดลที่ปลด) หรือ CreativeError"""
    dev = comfy_device(comfy_stats())
    if dev is None:
        raise CreativeError("ComfyUI ไม่รายงาน GPU (อาจกำลังรันแบบ CPU) — ต่อ eGPU RTX 4090 แล้วเปิด Creative Studio ใหม่")
    if dev["total_mib"] < GPU_MIN_TOTAL_MIB:
        raise CreativeError("GPU ที่ Creative Studio ใช้คือ %s (VRAM %s MiB) เล็กเกินสำหรับ Wan 2.2 — ต่อ eGPU RTX 4090 "
                            "แล้วเปิด Creative Studio ใหม่" % (dev["name"], format(dev["total_mib"], ",")))
    free = real_free_mib(dev)
    if free >= GPU_NEED_MIB:
        return free, []
    unloaded, busy, why = unload_idle_models()
    if why == "router_down":
        log.append("ติดต่อ router ของโมเดลแชตไม่ได้ จึงปลดโมเดลให้ไม่ได้")
    if unloaded:
        log.append("ปลดโมเดลแชตที่ว่างออกจาก GPU: %s" % ", ".join(unloaded))
    deadline = time.monotonic() + ROOM_WAIT_S
    while time.monotonic() < deadline:
        d = comfy_device(comfy_stats())
        if d is not None:
            free = real_free_mib(d)
            if free >= GPU_NEED_MIB:
                break
        if not unloaded:
            break
        time.sleep(0.5)
    if free < GPU_NEED_MIB and busy:
        raise CreativeError("VRAM ว่าง %s MiB (ต้องการ %s) และโมเดลแชต %s กำลังตอบอยู่จึงปลดไม่ได้ — รอให้ตอบเสร็จแล้วสั่งใหม่ "
                            "(ยังไม่ได้เริ่มสร้างวิดีโอ)" % (format(free, ","), format(GPU_NEED_MIB, ","), ", ".join(busy)))
    if free < GPU_NEED_MIB:
        log.append("VRAM ว่าง %s MiB น้อยกว่าที่แนะนำ (%s) — ComfyUI จะทยอยโหลด/ปลดโมเดลเอง อาจช้ากว่าปกติ"
                   % (format(free, ","), format(GPU_NEED_MIB, ",")))
    return free, unloaded


def free_comfy_vram(log: list) -> None:
    st, _d = _comfy("POST", "/free", {"unload_models": True, "free_memory": True}, timeout=20.0)
    log.append("คืน VRAM ของ ComfyUI แล้ว" if st == 200 else "สั่ง ComfyUI คืน VRAM ไม่สำเร็จ (%s)" % st)


# ------------------------------------------------------------------ รูปภาพ: ขนาดจาก header (stdlib ล้วน)
def image_size(path: str) -> tuple[int, int] | None:
    try:
        with open(path, "rb") as fh:
            head = fh.read(64 * 1024)
    except OSError:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        w, h = struct.unpack(">II", head[16:24])
        return int(w), int(h)
    if head[:6] in (b"GIF87a", b"GIF89a") and len(head) >= 10:
        w, h = struct.unpack("<HH", head[6:10])
        return int(w), int(h)
    if head[:2] == b"BM" and len(head) >= 26:
        w, h = struct.unpack("<ii", head[18:26])
        return abs(int(w)), abs(int(h))
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP" and len(head) >= 30:
        chunk = head[12:16]
        if chunk == b"VP8X":
            w = 1 + int.from_bytes(head[24:27], "little")
            h = 1 + int.from_bytes(head[27:30], "little")
            return w, h
        if chunk == b"VP8L":
            b = head[21:25]
            w = 1 + (((b[1] & 0x3F) << 8) | b[0])
            h = 1 + (((b[3] & 0x0F) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
            return w, h
        if chunk == b"VP8 ":
            w, h = struct.unpack("<HH", head[26:30])
            return int(w & 0x3FFF), int(h & 0x3FFF)
        return None
    if head[:2] == b"\xff\xd8":
        i = 2
        n = len(head)
        while i + 9 < n:
            if head[i] != 0xFF:
                i += 1
                continue
            marker = head[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", head[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", head[i + 5:i + 9])
                return int(w), int(h)
            i += 2 + seg_len
    return None


# ------------------------------------------------------------------ โฟลเดอร์ของโปรเจกต์ / ไฟล์งาน
def _dirs(project: str):
    if _docs is not None:
        return _docs.project_dirs(project, create_outputs=False)
    base = guard.project_dir(project or guard.current_project() or "default")

    class _D:                                   # noqa: D401 — รูปเดียวกับ tools_docs.Dirs
        pass
    d = _D()
    d.base, d.attachments, d.outputs = base, os.path.join(base, "attachments"), os.path.join(base, "outputs")
    return d


def _job_dir(project: str) -> str:
    d = os.path.join(_dirs(project).base, JOB_SUBDIR)
    d = guard.check_write(d)                    # S04 + เขตห้ามเขียน (อยู่ใต้ data\<slug> ของโปรเจกต์ใน URL เสมอ)
    os.makedirs(d, exist_ok=True)
    return d


def _outputs_target(project: str, fname: str) -> str:
    """path เต็มใน outputs ของโปรเจกต์ — ด่านเดียวกับ make_file (outputs ต้องเป็นโฟลเดอร์จริงใต้โปรเจกต์ ไม่ใช่ลิงก์)"""
    dirs = _dirs(project)
    os.makedirs(dirs.outputs, exist_ok=True)
    target = guard.check_write(os.path.join(dirs.outputs, fname))
    expect = os.path.normcase(os.path.join(os.path.realpath(dirs.base), "outputs"))
    if os.path.normcase(os.path.realpath(dirs.outputs)) != expect or os.path.islink(dirs.outputs):
        raise guard.Denied("ปลายทางต้องอยู่ในโฟลเดอร์ outputs ของโปรเจกต์นี้เท่านั้น (outputs ต้องเป็นโฟลเดอร์จริง ไม่ใช่ลิงก์/junction)")
    return target


def _write_atomic(target: str, data: bytes) -> None:
    folder = os.path.dirname(target)
    tmp = os.path.join(folder, ".~%s.%s.part" % (os.path.basename(target)[:60], _secrets.token_hex(4)))
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    try:
        os.rename(tmp, target)                  # ไม่ทับ: ล้มถ้ามีไฟล์ชื่อนี้โผล่มาระหว่างทาง
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def out_link(name: str) -> str:
    if _docs is not None:
        return _docs.out_link(name)
    return "[%s](/_qwen/out/%s)" % (name.replace("[", "(").replace("]", ")"), quote(name, safe=""))


def _display(path: str, project: str) -> str:
    if _docs is not None:
        return _docs.display_path(path, project)
    return path


_BAD_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')


def _stem(name: str) -> str:
    raw = _CTRL_RE.sub("", _s(name)).strip().strip('"').strip("'")
    raw = re.sub(r"(?i)\.(mp4|webm|mov|mkv|gif)$", "", raw)
    raw = _BAD_NAME_RE.sub("_", raw).strip().rstrip(". ")[:60]
    if not raw or raw in (".", "..") or raw.startswith("."):
        raw = "video-%s-%s" % (datetime.now().strftime("%Y%m%d-%H%M"), _secrets.token_hex(2))
    return raw


def _unique_stem(project: str, stem: str) -> str:
    outputs = _dirs(project).outputs
    cand, n = stem, 1
    while any(os.path.exists(os.path.join(outputs, cand + ext)) for ext in (".webm", ".mp4")):
        n += 1
        cand = "%s-%d" % (stem, n)
        if n > 500:
            raise CreativeError("ตั้งชื่อไฟล์ผลลัพธ์ไม่ได้ (ชื่อซ้ำมากเกินไป) — ส่ง name ใหม่")
    return cand


# ------------------------------------------------------------------ พารามิเตอร์ -> spec
def _num(value, label: str, lo: float, hi: float, default: float, integer: bool = False):
    text = _s(value).strip()
    if not text:
        return int(default) if integer else default
    try:
        v = float(text)
    except ValueError:
        raise CreativeError("%s ต้องเป็นตัวเลข (ได้ %r)" % (label, text[:40])) from None
    if v < lo or v > hi:
        raise CreativeError("%s ต้องอยู่ระหว่าง %s ถึง %s (ได้ %s)" % (label, lo, hi, text[:40]))
    return int(round(v)) if integer else v


def parse_seconds(value) -> tuple[int, float]:
    """วินาที -> (เฟรม 4k+1 ภายใน 13..121, วินาทีจริง = เฟรม/24)"""
    text = _s(value).strip().lower()
    for word in ("วินาที", "วิ", "seconds", "second", "secs", "sec", "s"):
        if text.endswith(word):
            text = text[: -len(word)].strip()
            break
    seconds = _num(text, "seconds (ความยาว)", 0.5, 5.0, DEFAULT_SECONDS)
    frames = int(round(seconds * FPS))
    frames = 4 * int(round((frames - 1) / 4.0)) + 1
    frames = max(MIN_FRAMES, min(MAX_FRAMES, frames))
    return frames, frames / float(FPS)


def _snap(v: int) -> int:
    v = int(round(v / float(SIDE_STEP))) * SIDE_STEP
    return max(MIN_SIDE, min(MAX_SIDE, v))


def parse_size(value, image_wh=None) -> tuple[int, int]:
    text = _s(value).strip().lower().replace("×", "x").replace("*", "x").replace(" ", "")
    if not text:
        if image_wh:
            w, h = image_wh
            if h > w * 1.15:
                return PORTRAIT_SIZE
            if abs(w - h) <= 0.15 * max(w, h):
                return (960, 960)
        return DEFAULT_SIZE
    if text in ("landscape", "แนวนอน", "horizontal", "wide", "16:9", "default"):
        return DEFAULT_SIZE
    if text in ("portrait", "แนวตั้ง", "vertical", "tall", "9:16"):
        return PORTRAIT_SIZE
    if text in ("square", "สี่เหลี่ยม", "จัตุรัส", "1:1"):
        return (960, 960)
    m = re.fullmatch(r"(\d{2,4})x(\d{2,4})(?:p)?", text)
    if not m:
        raise CreativeError("size ต้องเป็น กว้างxสูง เช่น 1280x704 หรือ landscape|portrait|square (ได้ %r)" % text[:40])
    return _snap(int(m.group(1))), _snap(int(m.group(2)))


def parse_seed(value) -> int:
    text = _s(value).strip().lower()
    if text in ("", "-1", "random", "auto", "สุ่ม"):
        return _secrets.randbelow(2 ** 31)
    try:
        v = int(float(text))
    except ValueError:
        raise CreativeError("seed ต้องเป็นจำนวนเต็ม (ได้ %r)" % text[:40]) from None
    if v < 0 or v > 2 ** 53:
        raise CreativeError("seed ต้องอยู่ระหว่าง 0 ถึง 2^53")
    return v


def resolve_image(image, project: str) -> dict | None:
    """ภาพตั้งต้นที่โมเดลส่งมา -> {path, shown, w, h, bytes} ผ่าน guard.check_read (S04/S05) หรือ None ถ้าไม่ได้ส่ง"""
    raw = _s(image).strip()
    if not raw:
        return None
    full = _docs.resolve_input(raw, project) if _docs is not None else raw
    p = guard.check_read(full)
    if not os.path.isfile(p):
        raise CreativeError("ไม่พบไฟล์ภาพ %s (วางไว้ใน attachments ของโปรเจกต์ หรือส่ง path เต็ม)" % raw[:120])
    ext = os.path.splitext(p)[1].lower()
    if ext not in IMAGE_EXTS:
        raise CreativeError("ภาพตั้งต้นต้องเป็น png/jpg/jpeg/webp/bmp/gif (ได้ %s)" % (ext or "ไม่มีนามสกุล"))
    size = os.path.getsize(p)
    if size > MAX_IMAGE_BYTES:
        raise CreativeError("ไฟล์ภาพใหญ่เกิน %s" % _human(MAX_IMAGE_BYTES))
    wh = image_size(p)
    if not wh:
        raise CreativeError("อ่านขนาดของภาพไม่ได้ (ไฟล์อาจเสียหรือไม่ใช่รูปจริง): %s" % raw[:120])
    return {"path": p, "shown": _display(p, project), "w": wh[0], "h": wh[1], "bytes": size}


def build_spec(project: str, prompt="", image="", seconds="", size="", seed="", negative="", name="", steps="",
               cfg="") -> dict:
    """ค่าที่ normalize แล้วทั้งชุด — ใช้ทั้งตอนออก token และตอนใช้ token (ต้องได้ชุดเดิมจากพารามิเตอร์เดิมเสมอ)"""
    text = _CTRL_RE.sub("", _s(prompt)).strip()
    img = resolve_image(image, project)
    if not text and img is None:
        raise CreativeError("ต้องมี prompt (บรรยายวิดีโอที่ต้องการ) หรือ image (ภาพตั้งต้น) อย่างน้อยหนึ่งอย่าง")
    if len(text) > MAX_PROMPT_CHARS:
        raise CreativeError("prompt ยาวเกิน %d ตัวอักษร" % MAX_PROMPT_CHARS)
    neg = _CTRL_RE.sub("", _s(negative)).strip()
    if len(neg) > MAX_NEGATIVE_CHARS:
        raise CreativeError("negative ยาวเกิน %d ตัวอักษร" % MAX_NEGATIVE_CHARS)
    frames, secs = parse_seconds(seconds)
    w, h = parse_size(size, (img["w"], img["h"]) if img else None)
    spec = {
        "project": guard.project_slug(project),
        "prompt": text,
        "negative": neg or DEFAULT_NEGATIVE,
        "negative_default": not neg,
        "image": img["path"] if img else "",
        "image_shown": img["shown"] if img else "",
        "image_wh": [img["w"], img["h"]] if img else None,
        "image_sha256": _sha_file(img["path"]) if img else "",
        "width": w, "height": h, "frames": frames, "seconds": round(secs, 2), "fps": FPS,
        "steps": _num(steps, "steps", MIN_STEPS, MAX_STEPS, DEFAULT_STEPS, integer=True),
        "cfg": _num(cfg, "cfg", MIN_CFG, MAX_CFG, DEFAULT_CFG),
        "sampler": SAMPLER, "scheduler": SCHEDULER, "shift": SHIFT,
    }
    spec["seed"], spec["stem"] = _memo_seed_stem(spec, seed, name, project)
    return spec


def _memo_key(spec: dict, seed, name) -> str:
    keys = ("project", "prompt", "negative", "image_sha256", "width", "height", "frames", "steps", "cfg")
    return json.dumps([{k: spec[k] for k in keys}, _s(seed).strip(), _s(name).strip()], ensure_ascii=False, sort_keys=True)


def _memo_seed_stem(spec: dict, seed, name, project: str) -> tuple[int, str]:
    """seed/stem ของชุดพารามิเตอร์นี้ — ครั้งแรกสุ่ม/ตั้งให้แล้วจำไว้ ครั้งถัดไป (เล่นซ้ำจาก local_confirm) ได้ค่าเดิม"""
    key = _memo_key(spec, seed, name)
    now = time.monotonic()
    with _MEMO_LOCK:
        for k in [k for k, v in _MEMO.items() if now - v[0] > MEMO_TTL]:
            _MEMO.pop(k, None)
        hit = _MEMO.get(key)
        if hit is not None:
            return hit[1], hit[2]
    value = (parse_seed(seed), _unique_stem(project, _stem(name)))
    with _MEMO_LOCK:
        hit = _MEMO.setdefault(key, (now, value[0], value[1]))
    return hit[1], hit[2]


def _memo_forget(spec: dict, seed, name) -> None:
    """token ถูกใช้แล้ว (งานเริ่ม) — คำขอเดิมครั้งถัดไปต้องได้ seed/ชื่อไฟล์ใหม่"""
    with _MEMO_LOCK:
        _MEMO.pop(_memo_key(spec, seed, name), None)


def _sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def spec_detail(spec: dict) -> str:
    """ข้อความที่ token ผูกอยู่ (sha256 ใน guard) — ทุกค่าที่มีผลต่องาน

    prompt/negative ใส่เป็น sha256 ไม่ใช่ตัวข้อความ: guard ลง detail ใน audit.log (confirm_requested) — บันทึกของสแตกต้องไม่มี
    เนื้อหาที่ผู้ใช้พิมพ์ (กฎ S02 แบบเดียวกับ python_exec ที่ผูก token กับ sha256 ของโค้ด) ความแน่นของการผูกเท่าเดิม"""
    keys = ("project", "image_sha256", "width", "height", "frames", "steps", "cfg", "seed", "stem")
    d = {k: spec[k] for k in keys}
    d["prompt_sha256"] = hashlib.sha256(spec["prompt"].encode("utf-8")).hexdigest()
    d["negative_sha256"] = hashlib.sha256(spec["negative"].encode("utf-8")).hexdigest()
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def review_text(spec: dict) -> str:
    lines = ["[creative_video] สร้างวิดีโอด้วย AI Creative Studio (ComfyUI · Wan 2.2 TI2V 5B)",
             "โปรเจกต์: %s" % spec["project"],
             "ข้อความ (prompt): %s" % (spec["prompt"] or "(ไม่มี — ใช้ภาพตั้งต้นอย่างเดียว)"),
             "ข้อความเชิงลบ: %s" % ("(ค่าเริ่มต้นของ Wan) " if spec["negative_default"] else "") + spec["negative"]]
    if spec["image"]:
        lines.append("ภาพตั้งต้น: %s (%dx%d) -> ภาพ→วิดีโอ" % (spec["image_shown"], spec["image_wh"][0], spec["image_wh"][1]))
    else:
        lines.append("ภาพตั้งต้น: ไม่มี -> ข้อความ→วิดีโอ")
    lines.append("ขนาด %dx%d · ความยาว %.1f วินาที (%d เฟรม @%d fps) · steps %d · cfg %g · seed %d"
                 % (spec["width"], spec["height"], spec["seconds"], spec["frames"], spec["fps"], spec["steps"],
                    spec["cfg"], spec["seed"]))
    lines.append("ไฟล์ผลลัพธ์: outputs/%s.mp4 (และ .webm ต้นฉบับ) ของโปรเจกต์นี้" % spec["stem"])
    lines.append("GPU: ปลดโมเดลแชตที่ว่างอยู่ออกจาก VRAM ชั่วคราวระหว่างสร้าง (โหลดกลับเองเมื่อคุยต่อ ~10-40 วินาที) "
                 "และเปิด Creative Studio ให้ถ้ายังไม่เปิด")
    lines.append("เวลาโดยประมาณ 5-7 นาที (วัดจริงบน RTX 4090: ~6 วินาที/step + โหลดโมเดล ~1 นาที · ยาว/ใหญ่/steps มากใช้เวลามากขึ้น)")
    return "\n".join(lines)


# ------------------------------------------------------------------ ComfyUI: workflow (API format) / ส่งงาน
def build_graph(spec: dict, image_name: str = "", prefix: str = "ComfyUI") -> dict:
    """workflow รูปแบบ API ของ ComfyUI — โหนดชุดเดียวกับ 01-Wan2.2-Text-to-Video.json / 02-...-Image-to-Video.json"""
    g = {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET_FILE, "weight_dtype": "default"}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP_FILE, "type": "wan", "device": "default"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_FILE}},
        "48": {"class_type": "ModelSamplingSD3", "inputs": {"shift": spec["shift"], "model": ["37", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": spec["prompt"], "clip": ["38", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": spec["negative"], "clip": ["38", 0]}},
        "55": {"class_type": "Wan22ImageToVideoLatent",
               "inputs": {"width": spec["width"], "height": spec["height"], "length": spec["frames"], "batch_size": 1,
                          "vae": ["39", 0]}},
        "3": {"class_type": "KSampler",
              "inputs": {"seed": spec["seed"], "steps": spec["steps"], "cfg": spec["cfg"], "sampler_name": spec["sampler"],
                         "scheduler": spec["scheduler"], "denoise": 1.0, "model": ["48", 0], "positive": ["6", 0],
                         "negative": ["7", 0], "latent_image": ["55", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["39", 0]}},
        "47": {"class_type": "SaveWEBM",
               "inputs": {"filename_prefix": prefix, "codec": "vp9", "fps": float(spec["fps"]), "crf": WEBM_CRF,
                          "images": ["8", 0]}},
    }
    if image_name:
        g["57"] = {"class_type": "LoadImage", "inputs": {"image": image_name, "upload": "image"}}
        g["55"]["inputs"]["start_image"] = ["57", 0]
    return g


def upload_image(path: str, sha: str) -> str:
    """ส่งภาพตั้งต้นให้ ComfyUI (โฟลเดอร์ input ของมัน) คืนชื่อไฟล์ที่ LoadImage ใช้"""
    ext = os.path.splitext(path)[1].lower() or ".png"
    name = "qwen-%s%s" % (sha[:16], ext)
    with open(path, "rb") as fh:
        blob = fh.read(MAX_IMAGE_BYTES + 1)
    if len(blob) > MAX_IMAGE_BYTES:
        raise CreativeError("ไฟล์ภาพใหญ่เกิน %s" % _human(MAX_IMAGE_BYTES))
    boundary = "----qwen" + _secrets.token_hex(12)
    ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
             ".bmp": "image/bmp", ".gif": "image/gif"}.get(ext, "application/octet-stream")
    parts = [("--%s\r\nContent-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
              % (boundary, name, ctype)).encode("utf-8"), blob, b"\r\n",
             ("--%s\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n" % boundary).encode(),
             ("--%s\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\ninput\r\n" % boundary).encode(),
             ("--%s--\r\n" % boundary).encode()]
    body = b"".join(parts)
    host, port = comfy_addr()
    st, doc = _http(host, port, "POST", "/upload/image", body,
                    headers={"Content-Type": "multipart/form-data; boundary=" + boundary}, timeout=60.0)
    if st != 200 or not isinstance(doc, dict) or not doc.get("name"):
        raise CreativeError("อัปโหลดภาพตั้งต้นให้ ComfyUI ไม่สำเร็จ (สถานะ %s)" % st)
    sub = _s(doc.get("subfolder")).strip()
    return (sub + "/" + doc["name"]) if sub else _s(doc["name"])


def submit(graph: dict, client_id: str) -> str:
    st, doc = _comfy("POST", "/prompt", {"prompt": graph, "client_id": client_id}, timeout=60.0)
    if st == 200 and isinstance(doc, dict) and doc.get("prompt_id"):
        return _s(doc["prompt_id"])
    detail = ""
    if isinstance(doc, dict):
        err = doc.get("error")
        if isinstance(err, dict):
            detail = _clean(err.get("message") or err.get("type"), 200)
        nodes = doc.get("node_errors")
        if isinstance(nodes, dict) and nodes:
            bits = []
            for nid, info in list(nodes.items())[:3]:
                errs = (info or {}).get("errors") if isinstance(info, dict) else None
                msg = ""
                if isinstance(errs, list) and errs and isinstance(errs[0], dict):
                    msg = _clean(errs[0].get("message") or errs[0].get("details"), 160)
                bits.append("%s(%s): %s" % (_clean((info or {}).get("class_type"), 40) if isinstance(info, dict) else "?",
                                            _clean(nid, 8), msg))
            detail = (detail + " · " if detail else "") + "; ".join(bits)
    if st is None:
        raise CreativeError("ส่งงานให้ ComfyUI ไม่ได้ (ต่อไม่ติด)")
    hint = ""
    if "unet_name" in detail or "clip_name" in detail or "vae_name" in detail or "not in list" in detail:
        hint = " — ไฟล์โมเดล Wan 2.2 อาจยังไม่ครบ ตรวจด้วย creative_status"
    raise CreativeError("ComfyUI ปฏิเสธ workflow (สถานะ %s): %s%s" % (st, detail or "ไม่มีรายละเอียด", hint))


def _history(prompt_id: str) -> dict | None:
    st, doc = _comfy("GET", "/history/" + quote(prompt_id, safe=""))
    if st != 200 or not isinstance(doc, dict):
        return None
    entry = doc.get(prompt_id)
    return entry if isinstance(entry, dict) else {}


def _in_queue(prompt_id: str) -> bool | None:
    st, doc = _comfy("GET", "/queue")
    if st != 200 or not isinstance(doc, dict):
        return None
    for key in ("queue_running", "queue_pending"):
        for item in doc.get(key) or []:
            if isinstance(item, list) and len(item) > 1 and item[1] == prompt_id:
                return True
    return False


def _video_outputs(entry: dict) -> list[dict]:
    found = []
    for _nid, out in (entry.get("outputs") or {}).items():
        if not isinstance(out, dict):
            continue
        for key in ("images", "videos", "gifs", "animated"):
            for item in out.get(key) or []:
                if isinstance(item, dict) and _s(item.get("filename")).lower().endswith((".webm", ".mp4")):
                    found.append(item)
    return found


def fetch_output(item: dict) -> bytes:
    q = "/view?filename=%s&subfolder=%s&type=%s" % (quote(_s(item.get("filename")), safe=""),
                                                   quote(_s(item.get("subfolder")), safe=""),
                                                   quote(_s(item.get("type") or "output"), safe=""))
    st, blob = _comfy("GET", q, timeout=120.0, raw=True, max_bytes=MAX_OUTPUT_BYTES)
    if st != 200 or not blob:
        raise CreativeError("ดึงไฟล์ผลลัพธ์จาก ComfyUI ไม่ได้ (สถานะ %s)" % st)
    return blob


def _ffmpeg() -> str | None:
    if _media is None:
        return None
    try:
        return _media._ffmpeg()
    except Exception:                          # noqa: BLE001
        return None


def to_mp4(webm: str, mp4: str, log: list) -> bool:
    ff = _ffmpeg()
    if not ff:
        log.append("ไม่พบ ffmpeg จึงไม่ได้แปลงเป็น .mp4 (ไฟล์ .webm เปิดได้ใน Edge/Chrome)")
        return False
    argv = [ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", webm, "-an", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=180,
                           creationflags=_NO_WINDOW, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        log.append("แปลง .mp4 ไม่สำเร็จ: %s" % _clean(exc, 160))
        return False
    if r.returncode != 0 or not os.path.exists(mp4) or os.path.getsize(mp4) == 0:
        log.append("ffmpeg แปลง .mp4 ไม่สำเร็จ (%s) — ใช้ .webm แทน" % _clean(r.stderr, 200))
        try:
            if os.path.exists(mp4) and os.path.getsize(mp4) == 0:
                os.remove(mp4)                  # ไฟล์เปล่าที่เราสร้างเองไม่สำเร็จ
        except OSError:
            pass
        return False
    return True


# ------------------------------------------------------------------ งาน
class Job:
    def __init__(self, jid: str, project: str, spec: dict):
        self.id = jid
        self.project = project                  # slug จาก URL
        self.spec = spec
        self.prompt_id = ""
        self.state = "starting"                 # starting | running | done | error | cancelled
        self.started = time.time()
        self.finished = 0.0
        self.error = ""
        self.files: list[str] = []              # ชื่อไฟล์ใน outputs (mp4 ก่อน webm)
        self.log: list[str] = []
        self.unloaded: list[str] = []
        self.cancel_ev = threading.Event()
        self.done_ev = threading.Event()
        self.lock = threading.Lock()

    def to_dict(self) -> dict:
        return {"id": self.id, "project": self.project, "prompt_id": self.prompt_id, "state": self.state,
                "started": self.started, "finished": self.finished, "error": self.error, "files": self.files,
                "log": self.log[-20:], "unloaded": self.unloaded,
                "spec": {k: v for k, v in self.spec.items() if k != "image"}}   # path เต็มของภาพไม่ต้องลงไฟล์

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        spec = dict(d.get("spec") or {})
        spec.setdefault("image", "")
        job = cls(_s(d.get("id")), _s(d.get("project")), spec)
        job.prompt_id = _s(d.get("prompt_id"))
        job.state = _s(d.get("state")) or "error"
        job.started = float(d.get("started") or 0)
        job.finished = float(d.get("finished") or 0)
        job.error = _s(d.get("error"))
        job.files = [x for x in (d.get("files") or []) if isinstance(x, str)]
        job.log = [x for x in (d.get("log") or []) if isinstance(x, str)]
        job.unloaded = [x for x in (d.get("unloaded") or []) if isinstance(x, str)]
        if job.state in ("done", "error", "cancelled"):
            job.done_ev.set()
        return job

    def elapsed(self) -> float:
        return (self.finished or time.time()) - self.started


def _save(job: Job) -> None:
    """เขียนไฟล์สถานะแบบ atomic — ล็อกต่อ job (เธรดหลักกับเธรดเฝ้างานบันทึกพร้อมกันได้) และชื่อไฟล์ชั่วคราวไม่ซ้ำ"""
    try:
        with job.lock, guard.project_scope(job.project):
            folder = _job_dir(job.project)
            path = os.path.join(folder, job.id + ".json")
            tmp = os.path.join(folder, ".~%s.%s.part" % (job.id, _secrets.token_hex(3)))
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(job.to_dict(), fh, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
            _prune(folder)
    except Exception:                          # noqa: BLE001 — เก็บสถานะไม่ได้ต้องไม่ล้มงาน
        pass


def _prune(folder: str) -> None:
    try:
        files = sorted((f for f in os.scandir(folder) if f.name.endswith(".json")), key=lambda f: f.stat().st_mtime)
    except OSError:
        return
    for f in files[:-KEEP_JOBS] if len(files) > KEEP_JOBS else []:
        try:
            os.remove(f.path)                   # ไฟล์สถานะของเราเอง (เก็บล่าสุด KEEP_JOBS งาน)
        except OSError:
            pass


def _load(project: str, jid: str) -> Job | None:
    if not re.fullmatch(r"cv-[0-9a-f]{4,12}", jid or ""):
        return None
    with _JOBS_LOCK:
        job = _JOBS.get(jid)
    if job is not None:
        return job if job.project == guard.project_slug(project) else None   # S04: งานของโปรเจกต์อื่นมองไม่เห็น
    path = os.path.join(_dirs(project).base, JOB_SUBDIR, jid + ".json")
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("project") != guard.project_slug(project):
        return None
    job = Job.from_dict(d)
    if job.state in ("starting", "running"):
        # MCP เคยรีสตาร์ตระหว่างงาน: เธรดเฝ้าหายไป ตรวจผลจาก ComfyUI หนึ่งรอบแล้วเก็บให้
        _rehydrate(job)
    with _JOBS_LOCK:
        _JOBS.setdefault(jid, job)
    return job


def _list_jobs(project: str) -> list[Job]:
    folder = os.path.join(_dirs(project).base, JOB_SUBDIR)
    out = []
    try:
        names = sorted((f for f in os.scandir(folder) if f.name.endswith(".json")), key=lambda f: -f.stat().st_mtime)
    except OSError:
        names = []
    for f in names[:8]:
        job = _load(project, f.name[:-5])
        if job is not None:
            out.append(job)
    return out


def _finish(job: Job, state: str, error: str = "") -> None:
    with job.lock:
        job.state = state
        job.error = _clean(error, 400)
        job.finished = time.time()
    with _JOBS_LOCK:
        if job in _RUNNING:
            _RUNNING.remove(job)
    _save(job)
    job.done_ev.set()                           # ประกาศหลังบันทึกสถานะแล้ว (ผู้ถามเห็นไฟล์/ความจำตรงกัน)
    guard.audit("creative_job", {"id": job.id, "project": job.project, "state": state, "elapsed_s": int(job.elapsed()),
                                 "files": job.files, "error": job.error[:200]})


def _collect(job: Job, entry: dict) -> None:
    """ผลลัพธ์จาก /history -> outputs ของโปรเจกต์ (webm จาก ComfyUI + mp4 จาก ffmpeg)"""
    items = _video_outputs(entry)
    if not items:
        raise CreativeError("ComfyUI ทำงานเสร็จแต่ไม่มีไฟล์วิดีโอในผลลัพธ์")
    blob = fetch_output(items[0])
    with guard.project_scope(job.project):
        stem = _unique_stem(job.project, job.spec["stem"])
        if stem != job.spec["stem"]:
            job.log.append("ชื่อ %s ถูกใช้ไประหว่างรอ จึงใช้ %s แทน" % (job.spec["stem"], stem))
        webm = _outputs_target(job.project, stem + ".webm")
        _write_atomic(webm, blob)
        job.files = [stem + ".webm"]
        mp4 = _outputs_target(job.project, stem + ".mp4")
        if to_mp4(webm, mp4, job.log):
            job.files.insert(0, stem + ".mp4")


def _after_gpu(job: Job) -> None:
    """คืน VRAM ให้แชต: /free ของ ComfyUI แล้วปลดโมเดลแชตที่ว่าง (ตัวที่ถูกโหลดระหว่างงานได้ชั้นบน GPU น้อย — โหลดใหม่ดีกว่า)"""
    free_comfy_vram(job.log)
    rows = chat_models() or []
    loaded = [m["id"] for m in rows if m["state"] == "loaded"]
    if not loaded:
        return
    unloaded, busy, _why = unload_idle_models()
    if unloaded:
        job.log.append("ปลดโมเดลแชตที่โหลดระหว่างงาน (%s) ให้ router โหลดใหม่เต็มๆ ตอนคุยครั้งถัดไป" % ", ".join(unloaded))
    if busy:
        job.log.append("โมเดล %s กำลังตอบอยู่ ไม่แตะ" % ", ".join(busy))


def _watch(job: Job) -> None:
    """เธรดเฝ้างาน: รอผลจาก /history แล้วเก็บไฟล์ -> คืน VRAM (/free + ปลดโมเดลแชตที่ว่าง) -> จึงประกาศว่าจบ

    ลำดับสำคัญ: done_ev ต้องถูกตั้ง "หลัง" คืน VRAM แล้ว — ผลเครื่องมือกลับไปถึงหน้าแชตเมื่อไร router จะโหลดโมเดลแชตกลับทันที
    ถ้า ComfyUI ยังถือ VRAM อยู่ตอนนั้น โมเดลแชตจะถูกจัดชั้นลง CPU (ช้ามาก) ไปจนกว่าจะโหลดใหม่"""
    missing = 0
    last_queue_check = time.monotonic()
    state, error = "error", "เฝ้างานจบโดยไม่มีผล"
    try:
        while True:
            if job.cancel_ev.is_set():
                _comfy("POST", "/interrupt", {}, timeout=10.0)
                _comfy("POST", "/queue", {"delete": [job.prompt_id]}, timeout=10.0)
                state, error = "cancelled", "ยกเลิกตามคำสั่ง"
                break
            entry = _history(job.prompt_id)
            if entry:
                status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
                if status.get("status_str") == "error" or (status and status.get("completed") is False):
                    msg = ""
                    for m in status.get("messages") or []:
                        if isinstance(m, list) and len(m) > 1 and m[0] == "execution_error" and isinstance(m[1], dict):
                            msg = "%s: %s" % (_clean(m[1].get("node_type"), 40), _clean(m[1].get("exception_message"), 300))
                    state, error = "error", "ComfyUI ทำงานผิดพลาด — %s" % (msg or "ไม่มีรายละเอียด")
                    break
                try:
                    _collect(job, entry)
                    state, error = "done", ""
                except (CreativeError, guard.Denied, OSError) as exc:
                    state, error = "error", "เก็บไฟล์ผลลัพธ์ไม่สำเร็จ: %s" % exc
                break
            if entry is None:
                missing += 1                    # ComfyUI ไม่ตอบ (ล่ม/ถูกปิด?) — ให้โอกาสราว 1 นาที
                if missing > 30:
                    state, error = "error", "ติดต่อ ComfyUI ไม่ได้ระหว่างรอผล (ถูกปิดไป?)"
                    break
            else:
                missing = 0
                if time.monotonic() - last_queue_check >= QUEUE_CHECK_S:
                    last_queue_check = time.monotonic()
                    if _in_queue(job.prompt_id) is False:
                        time.sleep(POLL_S)      # history อาจตามคิวช้าไปหนึ่งจังหวะ
                        if not _history(job.prompt_id):
                            state, error = "error", "งานหายจากคิวของ ComfyUI โดยไม่มีผล (ถูก interrupt หรือหน่วยความจำไม่พอ)"
                            break
                        continue
            if job.elapsed() > JOB_MAX_S:
                _comfy("POST", "/interrupt", {}, timeout=10.0)
                state, error = "error", "งานนานเกิน %d นาที จึงสั่งหยุด" % int(JOB_MAX_S // 60)
                break
            time.sleep(POLL_S)
    except Exception as exc:                   # noqa: BLE001 — เธรดเฝ้างานต้องจบด้วยสถานะเสมอ
        state, error = "error", "เฝ้างานล้มเหลว: %s: %s" % (type(exc).__name__, exc)
    try:
        _after_gpu(job)
    except Exception:                          # noqa: BLE001
        pass
    _finish(job, state, error)


def _rehydrate(job: Job) -> None:
    """งานที่เธรดเฝ้าหาย (MCP รีสตาร์ต): ตรวจ /history หนึ่งรอบ — เสร็จแล้วก็เก็บไฟล์ให้ ยังไม่เสร็จ/ไม่รู้ = รายงานตามนั้น"""
    if not job.prompt_id:
        _finish(job, "error", "ไม่มีรหัสงานของ ComfyUI (MCP รีสตาร์ตก่อนส่งงาน)")
        return
    entry = _history(job.prompt_id)
    if entry is None:
        job.log.append("ติดต่อ ComfyUI ไม่ได้ จึงยังไม่รู้ผลของงานนี้")
        return
    if not entry:
        if _in_queue(job.prompt_id) is False:
            _finish(job, "error", "งานไม่อยู่ในคิวและไม่มีผลใน ComfyUI (เธรดเฝ้างานหายไประหว่าง MCP รีสตาร์ต)")
        else:
            job.state = "running"
            threading.Thread(target=_watch, args=(job,), daemon=True, name="creative-rehydrate-%s" % job.id).start()
        return
    try:
        _collect(job, entry)
        _finish(job, "done")
    except (CreativeError, guard.Denied, OSError) as exc:
        _finish(job, "error", "เก็บไฟล์ผลลัพธ์ไม่สำเร็จ: %s" % exc)


def run_job(spec: dict, project: str, surface: str) -> str:
    slug = guard.project_slug(project)
    with _JOBS_LOCK:
        if _RUNNING:
            other = _RUNNING[0]
            mine = other.project == slug
            return ("ERROR: GPU กำลังสร้างวิดีโออยู่ (%s) — รอให้เสร็จก่อนแล้วสั่งใหม่%s"
                    % ("งาน %s ของโปรเจกต์นี้ ผ่านไป %s" % (other.id, _mmss(other.elapsed())) if mine else "งานของอีกโปรเจกต์",
                       " ถามสถานะด้วย %s" % _call_hint(surface, "status", other.id) if mine else ""))
        job = Job("cv-" + _secrets.token_hex(2), slug, spec)
        _RUNNING.append(job)
    call_t0 = time.monotonic()                  # งบเวลานับจากต้นการเรียก (หน้าแชตรอผลเครื่องมือได้ ~300 วินาที)
    try:
        _save(job)
        ensure_comfy(job.log)
        _vram_free, job.unloaded = make_room(job.log)
        image_name = ""
        if spec.get("image"):
            image_name = upload_image(spec["image"], spec["image_sha256"])
        graph = build_graph(spec, image_name, prefix="qwen/%s-%s" % (slug[:24], job.id))
        job.prompt_id = submit(graph, "qwen-mcp-" + job.id)
        job.state = "running"
        job.started = time.time()
        _save(job)
        guard.audit("creative_submit", {"id": job.id, "project": slug, "prompt_chars": len(spec["prompt"]),
                                        "image": bool(spec.get("image")), "size": [spec["width"], spec["height"]],
                                        "frames": spec["frames"], "steps": spec["steps"], "seed": spec["seed"],
                                        "unloaded": job.unloaded})
    except (CreativeError, guard.Denied) as exc:
        if job.unloaded:
            job.log.append("โมเดลแชตที่ปลดไว้ (%s) จะถูกโหลดกลับเองเมื่อคุยครั้งถัดไป" % ", ".join(job.unloaded))
        _finish(job, "error", str(exc))
        return "ERROR: %s" % exc + ("\n  [หมายเหตุ] %s" % job.log[-1] if job.unloaded else "")
    except Exception as exc:                   # noqa: BLE001
        _finish(job, "error", "%s: %s" % (type(exc).__name__, exc))
        return "ERROR: creative_video ล้มเหลว: %s: %s" % (type(exc).__name__, exc)
    with _JOBS_LOCK:
        _JOBS[job.id] = job
    threading.Thread(target=_watch, args=(job,), daemon=True, name="creative-watch-%s" % job.id).start()
    job.done_ev.wait(max(2.0, WAIT_IN_CALL_S - (time.monotonic() - call_t0)))
    return status_text(job, surface)


# ------------------------------------------------------------------ ข้อความสถานะ
def _call_hint(surface: str, what: str, jid: str = "") -> str:
    if surface == "fast":
        return {"status": 'local_read action="creative_status" id="%s"' % jid,
                "cancel": 'local_do action="creative_cancel" id="%s"' % jid,
                "list": 'local_read action="creative_status"'}[what]
    return {"status": 'creative_status(id="%s")' % jid, "cancel": 'creative_cancel(id="%s")' % jid,
            "list": "creative_status()"}[what]


def status_text(job: Job, surface: str = "full") -> str:
    sp = job.spec
    head = "%dx%d · %.1f วินาที (%d เฟรม, %d fps) · steps %d · seed %d" % (
        sp.get("width", 0), sp.get("height", 0), float(sp.get("seconds", 0)), sp.get("frames", 0), sp.get("fps", FPS),
        sp.get("steps", 0), sp.get("seed", 0))
    notes = ["[หมายเหตุ] " + n for n in job.log[-6:]]
    if job.state == "done":
        lines = ["สร้างวิดีโอเสร็จแล้ว (งาน %s): %s" % (job.id, out_link(job.files[0]) if job.files else "(ไม่มีไฟล์)"),
                 "  %s · ใช้เวลา %s" % (head, _mmss(job.elapsed()))]
        for extra in job.files[1:]:
            lines.append("  ไฟล์ต้นฉบับจาก ComfyUI: %s" % out_link(extra))
        if sp.get("image_shown"):
            lines.append("  ภาพตั้งต้น: %s" % sp["image_shown"])
        lines.append("  เก็บที่ outputs/ ของโปรเจกต์นี้")
        lines.extend(notes)
        lines.append("ส่งลิงก์ข้างบนให้ผู้ใช้ตามที่เขียนไว้ทุกตัวอักษร (เปิดดู/ดาวน์โหลดได้ทันที)")
        return "\n".join(lines)
    if job.state in ("error", "cancelled"):
        lines = ["%s (งาน %s): %s" % ("ยกเลิกแล้ว" if job.state == "cancelled" else "ERROR: สร้างวิดีโอไม่สำเร็จ", job.id,
                                       job.error or "-"), "  %s · ผ่านไป %s" % (head, _mmss(job.elapsed()))]
        lines.extend(notes)
        return "\n".join(lines)
    lines = ["กำลังสร้างวิดีโอ (งาน %s) — ผ่านไป %s ปกติใช้ 5-7 นาที" % (job.id, _mmss(job.elapsed())),
             "  %s" % head]
    lines.extend(notes)
    lines.append("ถามความคืบหน้าด้วย %s (ยังไม่เสร็จอย่าเรียกซ้ำถี่ๆ บอกผู้ใช้แล้วจบเทิร์นได้) · ยกเลิกด้วย %s"
                 % (_call_hint(surface, "status", job.id), _call_hint(surface, "cancel", job.id)))
    return "\n".join(lines)


def overview_text(project: str, surface: str) -> str:
    lines = ["AI Creative Studio (ComfyUI + Wan 2.2 TI2V 5B) — สถานะ"]
    stats = comfy_stats()
    if stats is None:
        lines.append("  ComfyUI: ยังไม่เปิด (%s:%d) — creative_video จะเปิดให้เองเมื่อสั่งงาน" % comfy_addr())
        gpu = _nvidia_smi_4090()
        if gpu:
            lines.append("  GPU (nvidia-smi): %s · VRAM ว่าง %s / %s MiB%s" % (
                gpu["name"], format(gpu["free_mib"], ","), format(gpu["total_mib"], ","),
                "" if gpu["total_mib"] >= GPU_MIN_TOTAL_MIB else " — เล็กเกินสำหรับ Wan ต้องต่อ eGPU RTX 4090"))
    else:
        dev = comfy_device(stats)
        ver = _clean((stats.get("system") or {}).get("comfyui_version"), 30) if isinstance(stats.get("system"), dict) else ""
        lines.append("  ComfyUI: เปิดอยู่ (%s:%d)%s" % (*comfy_addr(), " · เวอร์ชัน %s" % ver if ver else ""))
        if dev:
            lines.append("  GPU: %s · VRAM ว่าง %s / %s MiB%s" % (
                dev["name"], format(real_free_mib(dev), ","), format(dev["total_mib"], ","),
                "" if dev["total_mib"] >= GPU_MIN_TOTAL_MIB else " — เล็กเกินสำหรับ Wan ต้องต่อ eGPU RTX 4090"))
        else:
            lines.append("  GPU: ComfyUI ไม่รายงานการ์ด (โหมด CPU?)")
    rows = installed_models()
    missing = [n for n, ok, _b in rows if not ok]
    lines.append("  โมเดล Wan 2.2: %s" % ("ครบ 3 ไฟล์ (%s)" % ", ".join("%s %s" % (n, _human(b)) for n, ok, b in rows)
                                         if not missing else "ขาด %s — รัน C:\\LLM\\Download-Missing-Models.cmd" % ", ".join(missing)))
    with _JOBS_LOCK:
        running = list(_RUNNING)
    slug = guard.project_slug(project)
    if running:
        r = running[0]
        lines.append("  GPU กำลังสร้างวิดีโอ: %s" % ("งาน %s ของโปรเจกต์นี้ (ผ่านไป %s)" % (r.id, _mmss(r.elapsed()))
                                                   if r.project == slug else "งานของอีกโปรเจกต์"))
    jobs = _list_jobs(project)
    if jobs:
        lines.append("งานของโปรเจกต์นี้ (ล่าสุดก่อน):")
        for j in jobs:
            when = datetime.fromtimestamp(j.started).strftime("%d/%m %H:%M") if j.started else "?"
            what = {"done": "เสร็จ -> %s" % (out_link(j.files[0]) if j.files else "-"),
                    "error": "ผิดพลาด: %s" % (j.error[:120] or "-"), "cancelled": "ยกเลิก",
                    "running": "กำลังทำ (%s)" % _mmss(j.elapsed()), "starting": "กำลังเริ่ม"}.get(j.state, j.state)
            lines.append("  %s · %s · %s · %s" % (j.id, when, _clean(j.spec.get("prompt"), 60) or "(ภาพ→วิดีโอ)", what))
        lines.append("รายละเอียดงาน: %s" % _call_hint(surface, "status", "<id>"))
    else:
        lines.append("ยังไม่มีงานสร้างวิดีโอในโปรเจกต์นี้")
    return "\n".join(lines)


# ------------------------------------------------------------------ เครื่องมือ
def creative_status(id: str = "", project: str = "", surface: str = "full", **_) -> str:  # noqa: A002
    """อ่านอย่างเดียว: สถานะ Creative Studio + งานของโปรเจกต์นี้ (ใส่ id = งานเดียว รอให้เสร็จได้สูงสุด STATUS_WAIT_S)"""
    try:
        with guard.project_scope(project):
            jid = _s(id).strip().lower()
            guard.audit("creative_status", {"project": guard.project_slug(project), "id": jid[:16]})
            if not jid or jid in ("list", "all"):
                return overview_text(project, surface)
            job = _load(project, jid)
            if job is None:
                return "ไม่พบงาน %s ในโปรเจกต์นี้ — ดูรายการด้วย %s" % (jid[:24], _call_hint(surface, "list"))
            if not job.done_ev.is_set():
                job.done_ev.wait(STATUS_WAIT_S)     # ถามซ้ำถี่ = หน่วงไว้ กันโมเดลวนเรียกไม่หยุด
            return status_text(job, surface)
    except guard.Denied as exc:
        return "ปฏิเสธ: %s" % exc
    except Exception as exc:                   # noqa: BLE001
        return "ERROR: creative_status ล้มเหลว: %s: %s" % (type(exc).__name__, exc)


def creative_cancel(id: str = "", project: str = "", surface: str = "full", **_) -> str:  # noqa: A002
    try:
        with guard.project_scope(project):
            jid = _s(id).strip().lower()
            if not jid:
                return "ERROR: ต้องระบุ id ของงาน (ดูได้จาก %s)" % _call_hint(surface, "list")
            job = _load(project, jid)
            if job is None:
                return "ไม่พบงาน %s ในโปรเจกต์นี้" % jid[:24]
            if job.done_ev.is_set():
                return "งาน %s จบไปแล้ว (%s) ไม่มีอะไรให้ยกเลิก" % (job.id, job.state)
            job.cancel_ev.set()
            guard.audit("creative_cancel", {"id": job.id, "project": job.project})
            job.done_ev.wait(15.0)
            return status_text(job, surface) if job.done_ev.is_set() else "สั่งยกเลิกงาน %s แล้ว กำลังหยุด" % job.id
    except guard.Denied as exc:
        return "ปฏิเสธ: %s" % exc
    except Exception as exc:                   # noqa: BLE001
        return "ERROR: creative_cancel ล้มเหลว: %s: %s" % (type(exc).__name__, exc)


def creative_video(prompt: str = "", image: str = "", seconds: str = "", size: str = "", seed: str = "",
                   negative: str = "", name: str = "", steps: str = "", cfg: str = "", project: str = "",
                   surface: str = "full", confirm_token: str = "", **_) -> str:
    """[ยืนยัน] ข้อความ/ภาพ -> วิดีโอ: ครั้งแรกคืน confirm_token + REVIEW, ผ่าน local_confirm แล้วจึงสั่ง ComfyUI"""
    try:
        with guard.project_scope(project):
            spec = build_spec(project, prompt=prompt, image=image, seconds=seconds, size=size, seed=seed,
                              negative=negative, name=name, steps=steps, cfg=cfg)
            detail = spec_detail(spec)
            token = _s(confirm_token).strip()
            if not token or not guard.consume_confirm(token, ACTION, detail):
                if token:
                    return ("confirm_token ใช้ไม่ได้ (หมดอายุ ไม่ได้ยืนยันผ่าน local_confirm หรือค่าที่ส่งมาเปลี่ยนไป"
                            "หลังขอ — seed ที่สุ่มให้จะเปลี่ยนทุกครั้งที่เรียกใหม่) ยังไม่ได้ทำอะไร — เรียก creative_video "
                            "ใหม่โดยไม่ใส่ token")
                tok = guard.need_confirm(ACTION, detail, review=review_text(spec))
                guard.audit("creative_request", {"project": spec["project"], "prompt_chars": len(spec["prompt"]),
                                                 "image": bool(spec["image"]), "frames": spec["frames"],
                                                 "size": [spec["width"], spec["height"]], "ref": guard.token_ref(tok)})
                human = "%s · %dx%d · %.1f วินาที · outputs/%s.mp4" % (
                    ("ภาพ→วิดีโอ จาก %s" % spec["image_shown"]) if spec["image"] else "ข้อความ→วิดีโอ",
                    spec["width"], spec["height"], spec["seconds"], spec["stem"])
                return guard.confirm_hint(tok, "สร้างวิดีโอด้วย Creative Studio (ใช้ GPU หลายนาที)", human)
            _memo_forget(spec, seed, name)
            return run_job(spec, project, surface)
    except guard.Denied as exc:
        return "ปฏิเสธ: %s" % exc
    except guard.ReviewTooLarge as exc:
        return "ERROR: %s" % exc
    except CreativeError as exc:
        return "ERROR: %s" % exc
    except Exception as exc:                   # noqa: BLE001
        return "ERROR: creative_video ล้มเหลว: %s: %s" % (type(exc).__name__, exc)


# ------------------------------------------------------------------ ผิว /mcp
TOOLS = [
    {"name": "creative_video",
     "description": ("สร้างวิดีโอด้วย AI Creative Studio (ComfyUI · Wan 2.2) จากข้อความ prompt หรือจากภาพแนบ image=ชื่อไฟล์ใน "
                     "attachments (ภาพ→วิดีโอ) seconds=0.5-5 (2) size=1280x704|portrait|square seed=ตัวเลข (ไม่ใส่ = สุ่ม) "
                     "negative=ข้อความเชิงลบ name=ชื่อไฟล์ ผลเป็น .mp4/.webm ใน outputs ของโปรเจกต์ "
                     "ครั้งแรกได้ confirm_token + REVIEW (ยังไม่สร้าง) อนุมัติแล้วใช้ GPU 5-7 นาที (เกินงบรอในครั้งเดียวจะได้ id ไว้ถาม creative_status) "
                     "— ระหว่างสร้างโมเดลแชตที่ว่างถูกปลดจาก GPU ชั่วคราว"),
     "inputSchema": {"type": "object", "required": [], "properties": {
         "name": {"type": "string"}, "image": {"type": "string"}, "seconds": {"type": "string"},
         "size": {"type": "string"}, "seed": {"type": "string"}, "steps": {"type": "string"}, "cfg": {"type": "string"},
         "negative": {"type": "string"}, "prompt": {"type": "string"}, "project": {"type": "string"},
         "confirm_token": {"type": "string"}}}},
    {"name": "creative_status",
     "description": ("สถานะ Creative Studio (ComfyUI เปิดไหม GPU/VRAM โมเดล Wan ครบไหม) และงานสร้างวิดีโอของโปรเจกต์นี้ "
                     "ไม่ใส่ id = ภาพรวม+รายการงาน ใส่ id = งานนั้น (เสร็จแล้วได้ลิงก์วิดีโอ) — ยังไม่เสร็จอย่าเรียกซ้ำถี่ๆ"),
     "inputSchema": {"type": "object", "required": [], "properties": {
         "id": {"type": "string"}, "project": {"type": "string"}}}},
    {"name": "creative_cancel",
     "description": "ยกเลิกงานสร้างวิดีโอของโปรเจกต์นี้ที่กำลังทำ (ลงมือทันที)",
     "inputSchema": {"type": "object", "required": ["id"], "properties": {
         "id": {"type": "string"}, "project": {"type": "string"}}}},
]

IMPL = {"creative_video": creative_video, "creative_status": creative_status, "creative_cancel": creative_cancel}
