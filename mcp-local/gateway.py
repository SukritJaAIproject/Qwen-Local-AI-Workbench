# -*- coding: utf-8 -*-
"""gateway.py -- Remote Prompt Gateway (ฟีเจอร์ #18 ของสมุดงาน)

เปิดช่องให้ "ส่ง prompt เข้ามาจากนอกหน้าจอแชต" แล้วให้ llama-server ในเครื่องตอบ
โดยยังอยู่ใต้กฎความปลอดภัยชุดเดิม

  POST   /v1/prompt            ส่ง prompt เข้าคิว คืน job id
  GET    /v1/job/<id>          สถานะ + คำตอบเท่าที่ได้ + finish_reason
  POST   /v1/job/<id>/continue ต่อคำตอบที่ถูกตัดกลางคัน อีกหนึ่งท่อน
  GET    /v1/sessions          รายชื่อ session พร้อมจำนวนข้อความและเวลาใช้งานล่าสุด
  DELETE /v1/session/<id>      ลืม session เดียว
  GET    /health               ตรวจว่าเป็นอย่างไร (ไม่ต้องใช้คีย์)

เรื่องที่ต้องรู้ก่อนแก้ไฟล์นี้
-----------------------------
1. llama-server ที่ 8099 รันแบบ **router mode** ทุกคำขอต้องมีฟิลด์ "model"
   ไม่งั้นได้ 400 "model name is missing" ชื่อโมเดลจึงถูกถามจาก GET /v1/models
   ตอนรันจริงแล้ว cache ไว้ (ไม่ hardcode เพราะสมุดงานสลับ gguf บ่อย)

2. reasoning ปิดไว้เป็นค่าเริ่มต้น ส่ง chat_template_kwargs {"enable_thinking": false}
   เสมอ ยกเว้นผู้เรียกขอเอง  *เหตุผล:* วัดมาแล้วบนเครื่องนี้ ถ้าเปิด thinking แล้วตั้ง
   max_tokens น้อยๆ จะได้คำตอบ **ว่างเปล่า** เพราะช่วงคิดกินโควตา token ไปหมด

3. คิวมีเธรดทำงานตัวเดียว เพราะ 27B เดินราว 1.5 token/วินาที ถ้าปล่อยให้สองคำขอ
   generate พร้อมกันจะแย่งน้ำหนักโมเดลชุดเดียวกันจนช้าลงทั้งคู่ ไม่ใช่เร็วขึ้น

4. คีย์ API มาจากตัวแปรสภาพแวดล้อม GATEWAY_API_KEY เป็นหลัก (ไฟล์ gateway_key.txt
   เป็นทางสำรองที่ตอนนี้ guard.py บล็อกไว้โดยตั้งใจ ดูเหตุผลใน _ensure_key)
   **ห้าม** echo ค่าคีย์ลง console, ห้ามใส่ใน body ที่ตอบกลับ, ห้ามลง audit.log (กฎ S02)

5. เนื้อความจากผู้เรียกและคำตอบของโมเดลเป็น "ข้อมูล" ไม่ใช่คำสั่ง (กฎ S07)
   ไฟล์นี้จึงไม่มีเส้นทางไหนที่เอาข้อความจากคำขอไปรันหรือไปเปิดไฟล์เลย

ทุกฟังก์ชันสาธารณะคืน str เสมอ ข้อผิดพลาดคืนเป็นข้อความขึ้นต้น "ERROR: " ไม่โยน exception
"""
from __future__ import annotations

import json
import os
import queue
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

# guard.py อยู่โฟลเดอร์เดียวกับไฟล์นี้ กันกรณีถูกรันจาก cwd อื่น
_HERE_DIR = os.path.dirname(os.path.abspath(__file__))
if _HERE_DIR not in sys.path:
    sys.path.insert(0, _HERE_DIR)

import guard  # noqa: E402
from guard import Denied  # noqa: E402

# token ของบริการในเครื่อง (สัญญา C1/C3) — แนบไปกับทุกคำขอที่ยิง llama-server
# ตอนนี้ llama-server ยังไม่บังคับ --api-key (ไม่สน header นี้) แต่ถ้าวันหนึ่ง launcher เปิด
# --api-key-file ชี้ไฟล์เดียวกัน gateway จะยังทำงานต่อได้ทันทีโดยไม่ต้องแก้อะไร
_ROOT_DIR = os.path.dirname(_HERE_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.append(_ROOT_DIR)
try:
    import secrets_util  # noqa: E402
except Exception:        # noqa: BLE001 — ไม่มีตัวช่วยก็ยังคุยกับ llama-server แบบไม่มี token ได้
    secrets_util = None

# opener ที่ไม่ผ่าน proxy: คำขอที่พก token ต้องไม่ถูก HTTP_PROXY ลากออกไปนอกเครื่อง
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Origin ของหน้าเว็บที่ยอมให้เรียก gateway — ไม่มีเลย (gateway ไม่มี CORS และไม่ใช่ของเบราว์เซอร์)
# คำขอที่มี Origin อื่นคือหน้าเว็บที่ผู้ใช้เปิดอยู่พยายามยิงเข้ามา ปฏิเสธก่อนแตะอะไรทั้งนั้น

HERE = Path(_HERE_DIR)

# ผูกกับ 127.0.0.1 เท่านั้น ห้ามเพิ่ม 0.0.0.0, ngrok, cloudflared หรือ tunnel ใดๆ ในไฟล์นี้
# สมุดงานระบุว่า security baseline ต้องผ่านก่อน จึงจะเปิดออกอินเทอร์เน็ตได้
# และการตัดสินใจเปิดเป็นของผู้ใช้ ไม่ใช่ของเรา
HOST = "127.0.0.1"
PORT = 8780

UPSTREAM = "http://127.0.0.1:8099"
KEY_PATH = HERE / "gateway_key.txt"     # ทางสำรอง ปัจจุบัน guard บล็อกชื่อนี้ไว้ (ดู _ensure_key)
KEY_ENV = "GATEWAY_API_KEY"             # ทางหลัก ไม่มีไฟล์ให้เครื่องมืออ่านไฟล์ไปหยิบ
MIN_KEY_CHARS = 16
PROJECT = "gateway"                 # ข้อมูลทั้งหมดอยู่ใต้ guard.project_dir นี้ (S04)
SESSIONS_NAME = "sessions.json"

MAX_BODY = 256 * 1024               # กัน body ยักษ์กินแรม
MAX_PROMPT_CHARS = 32_000
DEFAULT_MAX_TOKENS = 512
MAX_MAX_TOKENS = 4096
MAX_SEGMENTS = 3                    # เพดาน Extend Mode ห้ามวนไม่จำกัด
MAX_HISTORY_MSGS = 20               # ประวัติต่อ session (คู่ถาม-ตอบ 10 รอบ)
MAX_MSG_CHARS = 4000                # ตัดข้อความยาวก่อนเก็บ กัน sessions.json บวม
MAX_SESSIONS = 50
MAX_JOBS_KEPT = 200
MAX_QUEUED = 32                     # เพดานงานที่รอคิวพร้อมกัน ดู _prompt ว่าทำไมต้องมี
AUDIT_PROMPT_CHARS = 200            # ลง audit ได้ไม่เกินนี้ (สมุดงานกำหนด)

PROBE_TIMEOUT = 5.0                 # แค่เช็คว่า upstream ยังอยู่
GEN_TIMEOUT = 900.0                 # 27B โหลดน้ำหนักครั้งแรกนานมาก ต้องใจเย็น

_LOCK = threading.RLock()           # ครอบ _JOBS/_ORDER
_SESS_LOCK = threading.RLock()      # ครอบ _SESSIONS + ไฟล์ sessions.json
_KEY_LOCK = threading.RLock()
_MODEL_LOCK = threading.RLock()

_JOBS: dict[str, dict] = {}
_ORDER: list[str] = []              # job id ที่ยัง "รอคิว" เรียงตามลำดับส่งเข้ามา
_Q: "queue.Queue[tuple[str, str] | None]" = queue.Queue()
_SESSIONS: dict[str, dict] = {}
_RUNNING: dict[str, str | None] = {"id": None}

_KEY: str = ""
_MODEL: str = ""
_WORKER: threading.Thread | None = None
_STARTED_AT = time.time()


# ------------------------------------------------------------------ utilities
def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _s(v, default: str = "") -> str:
    if v is None:
        return default
    if isinstance(v, str):
        return v
    return str(v)


def _clamp_int(v, low: int, high: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n))


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    return _s(v).strip().lower() in {"1", "true", "yes", "on", "จริง"}


# ------------------------------------------------------------------- API key
def _read_key_file(path: str) -> tuple[str, bool]:
    """คืน (ค่าคีย์, อ่านได้ไหม) โดยไม่โยน exception และไม่เคย log ค่าที่อ่านได้

    *วัดมาแล้ว* read_text(encoding="utf-8") โยน UnicodeDecodeError ซึ่งเป็น ValueError
    ไม่ใช่ OSError ถ้าไฟล์คีย์มีไบต์เสีย (เช่นเขียนค้างครึ่งทาง หรือถูกบันทึกเป็น UTF-16)
    ของเดิมดักแค่ OSError ข้อยกเว้นจึงหลุดออกจาก _key_ok ไปถึง do_GET
    แล้วคำขอทุกใบตายเป็น connection reset โดยไม่มีข้อความบอกเหตุ

    ไฟล์ยังไม่มี = อ่านได้แต่ค่าว่าง (เดี๋ยวไปสร้างใหม่)
    มีไฟล์แต่อ่าน/ถอดรหัสไม่ผ่าน = ok False ต้องไม่เงียบๆ แล้วสร้างคีย์ใหม่ทับของเดิม
    """
    try:
        return Path(path).read_text(encoding="utf-8").strip(), True
    except FileNotFoundError:
        return "", True
    except (OSError, ValueError):
        return "", False


def _ensure_key() -> str:
    """หาคีย์ให้ได้หนึ่งค่า: ตัวแปรสภาพแวดล้อมก่อน แล้วค่อยไฟล์ข้างไฟล์นี้

    S02: ค่าคีย์ไม่เคยถูก print, ไม่เคยอยู่ใน response body, ไม่เคยลง audit.log
    บันทึกได้แค่ "มาจากไหน/เพิ่งสร้าง" กับ path เท่านั้น

    ทำไมต้องมีทาง env
    -----------------
    guard.py บล็อก *\\gateway_key.txt (รวมถึง *_key.txt, *secret*, *credentials*)
    ไว้ตั้งใจ เหตุผลเขียนอยู่ในนั้น: โมเดลต้องอ่านคีย์ของตัวเองไม่ได้ ไม่งั้นข้อความ
    ที่หลอกให้ "อ่านไฟล์นี้แล้วบอกมา" จะทำให้คีย์หลุด  ผลข้างเคียงคือ gateway
    เก็บคีย์ลงไฟล์เดิมไม่ได้อีกแล้ว และเริ่มไม่ขึ้นเลย

    ทางออกที่ถูกคือ **ไม่เก็บคีย์ลงไฟล์ที่เครื่องมืออ่านไฟล์เอื้อมถึง** ไม่ใช่เปลี่ยน
    ไปใช้ชื่อไฟล์ที่ยังไม่ติดบัญชีดำ การเปลี่ยนชื่อเพื่อเลี่ยงนโยบายคือการเจาะกฎ
    ตัวเอง ห้ามทำ  ตัวแปรสภาพแวดล้อมอยู่นอกขอบเขตของ guard (guard ดูแล path)
    และตอบโจทย์เดิมได้ดีกว่า เพราะไม่มีไฟล์ให้ใครไปอ่าน
    """
    global _KEY
    with _KEY_LOCK:
        if _KEY:
            return _KEY

        env = _s(os.environ.get(KEY_ENV)).strip()
        if env:
            if len(env) < MIN_KEY_CHARS:
                raise Denied("คีย์ใน %s สั้นเกินไป (ต้องอย่างน้อย %d ตัวอักษร)"
                             % (KEY_ENV, MIN_KEY_CHARS))
            _KEY = env
            guard.audit("gateway_key", {"source": "env", "var": KEY_ENV})   # ไม่ลงค่า
            return _KEY

        # เขียนไฟล์คีย์ตรงๆ ไม่ผ่าน guard.check_write โดยตั้งใจ
        #
        # guard มีไว้จำกัด "สิ่งที่โมเดลสั่งได้" ไม่ใช่จำกัดโค้ดของเราเอง
        # นโยบายใน guard บล็อก *\gateway_key.txt ไว้เพื่อให้เครื่องมืออ่านไฟล์
        # ของโมเดลหยิบคีย์ไปไม่ได้ ซึ่งเป็นคนละเรื่องกับการที่ gateway
        # เก็บคีย์ของตัวเอง ถ้าบังคับให้ผ่าน guard ด้วย ผลคือ gateway
        # สตาร์ทไม่ขึ้นเลยเพราะนโยบายที่ออกแบบมาปกป้องมันเอง (เจอจริงตอนทดสอบ)
        #
        # path ตรงนี้เป็นค่าคงที่ในโค้ด ไม่มีทางที่โมเดลจะชี้ไปที่อื่นได้
        path = str(KEY_PATH)

        existing, readable = _read_key_file(path)
        if not readable:
            # fail closed: ยอม 401 ทุกใบดีกว่าสร้างคีย์ใหม่ทับของเดิมที่อาจยังมีคนถืออยู่
            raise Denied("อ่านไฟล์คีย์ %s ไม่ได้ (ไฟล์เสียหรือไม่ใช่ UTF-8) "
                         "ให้ลบไฟล์นี้ทิ้งแล้วเริ่ม gateway ใหม่ ระบบจะสร้างคีย์ใหม่ให้" % path)
        if existing:
            _KEY = existing
            guard.audit("gateway_key", {"path": path, "created": False})
            return _KEY

        key = secrets.token_urlsafe(24)
        try:
            # O_EXCL กันเขียนทับคีย์ที่โปรเซสอื่นเพิ่งสร้างในจังหวะเดียวกัน
            # โหมด 0600 เป็นเจตนา ถึงแม้ Windows จะไม่บังคับ POSIX mode จริงจัง
            # ตัวที่กันจริงคือ ACL ที่สืบทอดมาจาก C:\LLM ซึ่งเป็นของผู้ใช้คนเดียว
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            # โปรเซสอื่นชิงสร้างไฟล์ไปก่อนในจังหวะเดียวกัน ใช้ของเขา
            other, ok = _read_key_file(path)
            if not ok or not other:
                raise Denied("ไฟล์คีย์ %s ถูกสร้างพร้อมกันโดยโปรเซสอื่นแต่อ่านไม่ได้" % path)
            _KEY = other
            return _KEY
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(key + "\n")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        _KEY = key
        guard.audit("gateway_key", {"path": path, "created": True})
        return _KEY


def _key_source() -> str:
    """บอกว่าคีย์มาจากไหน โดยไม่บอกค่า (S02) ใช้ในข้อความสถานะเท่านั้น

    ห้ามเรียก guard.check_write ในนี้เด็ดขาด: ฟังก์ชันนี้ถูกเรียกจาก /health ซึ่ง
    **ไม่ต้องใช้คีย์** และจากทุกคำตอบ 401  ถ้าไปเรียก guard แล้ว path ติดบัญชีดำ
    guard จะเขียนแถว "denied" ลง audit.log ให้ทุกครั้ง แปลว่าใครก็ได้ที่ยิง /health
    รัวๆ สั่งให้ไฟล์ audit.log บวมได้โดยไม่ต้องมีคีย์ (ทดสอบแล้วเห็นแถวจริง)
    ดูจากสถานะในหน่วยความจำอย่างเดียวพอ
    """
    if _s(os.environ.get(KEY_ENV)).strip():
        return "ตัวแปรสภาพแวดล้อม %s" % KEY_ENV
    with _KEY_LOCK:
        if _KEY:
            return "ไฟล์ %s" % KEY_PATH
    # เครื่องมือ gateway_status รันในโปรเซส MCP ซึ่งไม่ได้โหลดคีย์ (_KEY ว่าง) จึงเคยรายงานผิดว่า
    # "ยังไม่ได้ตั้งค่า" ทั้งที่ gateway จริงทำงานอยู่ด้วยไฟล์คีย์ — เช็กแค่ "มีไฟล์ไหม" (ไม่อ่านค่า)
    # os.path.isfile ไม่แตะ guard และไม่เปิดไฟล์ จึงไม่เสี่ยงทำให้คีย์หลุดหรือทำให้ audit.log บวม
    try:
        if os.path.isfile(str(KEY_PATH)):
            return "ไฟล์ %s (ยังไม่ได้โหลดในโปรเซสนี้)" % KEY_PATH
    except OSError:
        pass
    return "ยังไม่ได้ตั้งค่า — ตั้ง %s ก่อนเริ่ม gateway" % KEY_ENV


def _key_ok(given: str) -> bool:
    """เทียบแบบ constant-time กัน timing attack ถึงจะอยู่บน loopback ก็ไม่ลดมาตรฐาน

    ดักกว้างไว้เป็นชั้นสุดท้าย: ฟังก์ชันนี้ถูกเรียกจาก _auth() ซึ่งอยู่ใน do_GET/do_POST
    ถ้าปล่อยข้อยกเว้นหลุดออกไป BaseHTTPRequestHandler จะไม่ตอบอะไรเลย ผู้เรียกเห็นแค่
    connection reset ทุกคำขอ ตอบ 401 ไปตรงๆ ยังบอกเหตุได้มากกว่า
    """
    try:
        want = _ensure_key()
    except (Denied, OSError, ValueError):
        return False
    if not want or not given:
        return False
    return secrets.compare_digest(given, want)


# ------------------------------------------------------------ sessions store
def _sessions_path() -> str:
    # path คงที่ของ gateway เอง ถูกเรียกได้ทั้งจากโปรเซส gateway และจากเครื่องมือ gateway_sessions
    # ที่รันใน tools/call ของโปรเจกต์อื่น (ซึ่ง S04 จะปฏิเสธโฟลเดอร์ "gateway") จึงใช้สิทธิ์ internal
    with guard.internal():
        return guard.check_write(os.path.join(guard.project_dir(PROJECT), SESSIONS_NAME))


def _trim_history(msgs: list) -> list:
    out = []
    for m in msgs[-MAX_HISTORY_MSGS:]:
        if not isinstance(m, dict):
            continue
        role = _s(m.get("role"), "user")
        if role not in ("user", "assistant", "system"):
            role = "user"
        out.append({"role": role, "content": _s(m.get("content"))[:MAX_MSG_CHARS]})
    return out


def _load_sessions() -> None:
    """อ่านประวัติจากดิสก์ตอนเริ่ม เพื่อให้ restart แล้วบทสนทนาไม่หาย"""
    global _SESSIONS
    try:
        path = _sessions_path()
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError, Denied):
        data = None
    sessions = data.get("sessions") if isinstance(data, dict) else None
    clean: dict[str, dict] = {}
    if isinstance(sessions, dict):
        for sid, rec in sessions.items():
            if not isinstance(rec, dict):
                continue
            clean[_s(sid)[:64]] = {
                "messages": _trim_history(rec.get("messages") or []),
                "created": _s(rec.get("created"), _utc_iso()),
                "updated": _s(rec.get("updated"), _utc_iso()),
            }
    with _SESS_LOCK:
        _SESSIONS = clean


def _save_sessions() -> None:
    """เขียนแบบ atomic (.tmp แล้ว replace) ถ้าเซิร์ฟเวอร์ถูกปิดกลางคันไฟล์เดิมยังครบ"""
    with _SESS_LOCK:
        # เกินเพดานให้ทิ้งตัวที่ไม่ได้ใช้นานสุดก่อน
        if len(_SESSIONS) > MAX_SESSIONS:
            old = sorted(_SESSIONS.items(), key=lambda kv: _s(kv[1].get("updated")))
            for sid, _rec in old[: len(_SESSIONS) - MAX_SESSIONS]:
                _SESSIONS.pop(sid, None)
        payload = {"version": 1, "saved": _utc_iso(),
                   "sessions": json.loads(json.dumps(_SESSIONS, ensure_ascii=False))}
    try:
        path = _sessions_path()
        # ไฟล์ .tmp ก็เป็น path ที่ถูกเปิดเขียนจริง ต้องผ่าน guard เหมือนกัน (S05)
        # ถึงจะอนุมานมาจาก path ที่ผ่านแล้วก็ไม่ยกเว้น กฎคือ "ทุก path ที่ถึง open()"
        with guard.internal():
            tmp = guard.check_write(path + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except (OSError, Denied):
        pass      # เก็บไม่ได้ก็ยังตอบคำถามต่อได้ ประวัติในแรมยังอยู่


def _session_history(sid: str) -> list:
    if not sid:
        return []
    with _SESS_LOCK:
        rec = _SESSIONS.get(sid)
        return list(rec["messages"]) if rec else []


def _session_commit(job: dict) -> None:
    """เขียนผลของ job ลง session

    ท่อนแรกเพิ่มคู่ user/assistant ส่วนการต่อคำตอบ (/continue หรือ Extend Mode)
    จะ "แทนที่" ข้อความ assistant เดิมด้วยคำตอบเต็มที่ยาวขึ้น ไม่ใช่เพิ่มอันใหม่
    ไม่งั้นประวัติจะมีคำตอบครึ่งๆ ซ้อนกันสองก้อน

    *สำคัญ* แทนที่ได้เฉพาะเมื่อข้อความ assistant ตัวท้ายยังเป็น "ของ job นี้" จริงๆ
    เทียบด้วย committed_text ไม่ใช่แค่เช็คว่า role เป็น assistant
    เคสที่พัง (ทดสอบแล้ว): job A ตอบค้างไว้ในเซสชัน S -> job B ถามเรื่องอื่นในเซสชัน S
    เสร็จเรียบร้อย -> ผู้ใช้สั่ง /continue ที่ job A ของเดิมจะเขียนทับคำตอบของ B
    ด้วยคำตอบของ A ประวัติกลายเป็น "user: B / assistant: คำตอบของ A" เสียหายถาวร
    และทุกเทิร์นถัดไปของเซสชันนั้นก็เห็นประวัติที่ผิด
    ถ้าเซสชันเดินหน้าไปแล้ว ให้ต่อท้ายเป็นคู่ใหม่แทน ประวัติจะยาวขึ้นแต่ไม่โกหก
    """
    sid = job.get("session") or ""
    if not sid:
        return
    answer = job["answer"][:MAX_MSG_CHARS]
    with _SESS_LOCK:
        rec = _SESSIONS.get(sid)
        if rec is None:
            rec = {"messages": [], "created": _utc_iso(), "updated": _utc_iso()}
            _SESSIONS[sid] = rec
        last = rec["messages"][-1] if rec["messages"] else None
        mine = (job.get("committed") and last is not None
                and last["role"] == "assistant"
                and last["content"] == job.get("committed_text"))
        if mine:
            last["content"] = answer
        else:
            rec["messages"].append({"role": "user", "content": job["prompt"][:MAX_MSG_CHARS]})
            rec["messages"].append({"role": "assistant", "content": answer})
            job["committed"] = True
        job["committed_text"] = answer
        rec["messages"] = _trim_history(rec["messages"])
        rec["updated"] = _utc_iso()
    _save_sessions()


# --------------------------------------------------------------- upstream io
def _http_json(url: str, payload: dict | None, timeout: float) -> tuple[dict | None, str]:
    """คืน (ข้อมูล, ข้อความผิดพลาด) — ไม่โยน exception ออกไปหาเธรดคิว"""
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if secrets_util is not None and url.startswith(UPSTREAM):
        try:
            headers.update(secrets_util.auth_headers())
        except Exception:                   # noqa: BLE001 — อ่าน token ไม่ได้ก็ยิงแบบไม่มี token ไปก่อน
            pass
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if payload is not None else "GET")
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        return json.loads(body), ""
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:400]
        except OSError:
            detail = ""
        return None, "HTTP %s จาก llama-server: %s" % (exc.code, detail)
    except urllib.error.URLError as exc:
        return None, "ต่อ llama-server ที่ %s ไม่ได้: %s" % (UPSTREAM, exc.reason)
    except (TimeoutError, OSError) as exc:
        return None, "คุยกับ llama-server ไม่สำเร็จ: %s" % exc
    except ValueError as exc:
        return None, "llama-server ตอบไม่ใช่ JSON: %s" % exc


def _model_name(force: bool = False) -> tuple[str, str]:
    """ถามชื่อโมเดลจาก router แล้ว cache ไว้ คืน (ชื่อ, ข้อความผิดพลาด)

    router mode บังคับให้ทุกคำขอมีฟิลด์ model ถ้าเดาชื่อเองจะได้ 400 ตลอด
    ถ้ามีหลายตัวให้เลือกตัวที่โหลดอยู่แล้วก่อน จะได้ไม่ไปสั่งสลับน้ำหนักโดยไม่ตั้งใจ
    """
    global _MODEL
    with _MODEL_LOCK:
        if _MODEL and not force:
            return _MODEL, ""
    data, err = _http_json(UPSTREAM + "/v1/models", None, PROBE_TIMEOUT)
    if err:
        return "", err
    items = (data or {}).get("data") or []
    loaded, first, preferred = "", "", ""
    # โมเดลหลักของเครื่องนี้คือ Qwen3.8 27B (คู่มือข้อ 1) ตัวอื่นเป็นตัวเสริม
    # ถ้าไม่เลือกให้ชัด รายชื่อเรียงตามตัวอักษรจะทำให้ได้ 4B มาเป็นค่าเริ่มต้น
    want = _s(os.environ.get("GATEWAY_MODEL")).strip().lower() or "qwen3.8"
    for it in items:
        if not isinstance(it, dict):
            continue
        name = _s(it.get("id"))
        if not name:
            continue
        first = first or name
        if want in name.lower() and not preferred:
            preferred = name
        status = it.get("status") if isinstance(it.get("status"), dict) else {}
        if _s(status.get("value")).lower() == "loaded" and not loaded:
            loaded = name
    picked = preferred or loaded or first
    if not picked:
        return "", "llama-server ไม่ได้บอกชื่อโมเดลมาเลย"
    with _MODEL_LOCK:
        _MODEL = picked
    return picked, ""


def _chat(messages: list, max_tokens: int, thinking: bool) -> tuple[str, str, str]:
    """ยิงหนึ่งท่อน คืน (เนื้อหา, finish_reason, ข้อความผิดพลาด)"""
    model, err = _model_name()
    if err:
        return "", "", err
    payload = {
        "model": model,                       # ขาดฟิลด์นี้ router ตอบ 400 ทันที
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
        # ปิด reasoning ไว้ ไม่งั้น max_tokens น้อยๆ จะได้คำตอบว่าง (วัดมาแล้ว)
        "chat_template_kwargs": {"enable_thinking": bool(thinking)},
    }
    data, err = _http_json(UPSTREAM + "/v1/chat/completions", payload, GEN_TIMEOUT)
    if err and err.startswith("HTTP 400"):
        # router อาจถูกสลับ gguf หลังเรา cache ชื่อไว้ ลองถามชื่อใหม่หนึ่งครั้ง
        model, merr = _model_name(force=True)
        if not merr:
            payload["model"] = model
            data, err = _http_json(UPSTREAM + "/v1/chat/completions", payload, GEN_TIMEOUT)
    if err:
        return "", "", err
    choices = (data or {}).get("choices") or []
    if not choices:
        return "", "", "llama-server ไม่ได้ส่ง choices กลับมา"
    ch = choices[0] if isinstance(choices[0], dict) else {}
    msg = ch.get("message") if isinstance(ch.get("message"), dict) else {}
    return _s(msg.get("content")), _s(ch.get("finish_reason")), ""


# -------------------------------------------------------------- job & worker
def _new_job(prompt: str, session: str, max_tokens: int, extend: bool,
             thinking: bool) -> dict:
    job = {
        "id": secrets.token_hex(5),
        "prompt": prompt,
        "session": session,
        "max_tokens": max_tokens,
        "extend": extend,
        "thinking": thinking,
        "status": "queued",
        "answer": "",
        "finish_reason": "",
        "segments": 0,
        "error": "",
        "note": "",
        "history": None,        # snapshot ตอนเริ่มทำจริง ไม่ใช่ตอนเข้าคิว (ดู _process)
        "committed": False,
        "committed_text": "",   # คำตอบก้อนล่าสุดที่ job นี้เขียนลง session (ดู _session_commit)
        "created": _utc_iso(),
        "started": "",
        "finished": "",
        "t0": 0.0,
        "elapsed": 0.0,
    }
    with _LOCK:
        _JOBS[job["id"]] = job
        _ORDER.append(job["id"])
        _prune_jobs()
    return job


def _prune_jobs() -> None:
    """เก็บประวัติ job เท่าที่จำเป็น เรียกใต้ _LOCK เสมอ"""
    if len(_JOBS) <= MAX_JOBS_KEPT:
        return
    done = [j for j in _JOBS.values() if j["status"] in ("done", "error")]
    done.sort(key=lambda j: _s(j.get("finished")))
    for j in done[: len(_JOBS) - MAX_JOBS_KEPT]:
        _JOBS.pop(j["id"], None)


def _queue_position(jid: str) -> int:
    """0 = ไม่ได้รออยู่ในคิวแล้ว, 1 = คิวถัดไปที่จะได้รัน"""
    with _LOCK:
        return (_ORDER.index(jid) + 1) if jid in _ORDER else 0


def _job_public(job: dict) -> dict:
    with _LOCK:
        pos = _queue_position(job["id"])
        elapsed = job["elapsed"] or (time.time() - job["t0"] if job["t0"] else 0.0)
        return {
            "id": job["id"],
            "status": job["status"],
            "session": job["session"] or None,
            "queue_position": pos,
            "answer": job["answer"],
            "finish_reason": job["finish_reason"] or None,
            "truncated": job["finish_reason"] == "length",
            "segments": job["segments"],
            "max_segments": MAX_SEGMENTS if job["extend"] else 1,
            "extend": job["extend"],
            "max_tokens": job["max_tokens"],
            "note": job["note"],
            "error": job["error"],
            "created": job["created"],
            "started": job["started"] or None,
            "finished": job["finished"] or None,
            "elapsed_sec": round(elapsed, 1),
        }


def _messages_for(job: dict) -> list:
    msgs = list(job["history"] or [])
    msgs.append({"role": "user", "content": job["prompt"]})
    if job["answer"]:
        # prefill: ปิดท้ายด้วยข้อความ assistant ที่ยังไม่จบ llama.cpp จะ "เขียนต่อ"
        # จากตรงนั้นแทนที่จะขึ้นเทิร์นใหม่ (ปิดได้ด้วย --no-prefill-assistant ฝั่งเซิร์ฟเวอร์)
        msgs.append({"role": "assistant", "content": job["answer"]})
    return msgs


def _strip_echo(prefill: str, content: str) -> str:
    """ตัดข้อความ prefill ที่ llama-server ส่งกลับมาซ้ำออก เหลือเฉพาะท่อนใหม่

    *วัดมาแล้วบนเครื่องนี้* ถ้าปิดท้ายด้วยข้อความ assistant ที่ยังไม่จบ llama-server
    จะเขียนต่อให้ถูกต้อง แต่ message.content ที่คืนมาคือ "prefill + ท่อนใหม่" ทั้งก้อน
    (usage.completion_tokens นับเฉพาะท่อนใหม่ ยืนยันว่าไม่ได้ generate ซ้ำ)
    ถ้าเอาไปต่อท้ายตรงๆ คำตอบจะซ้ำทวีคูณทุกท่อน
    """
    if not prefill or not content:
        return content
    if content.startswith(prefill):
        return content[len(prefill):]
    trimmed = prefill.rstrip()          # บาง template ตัดช่องว่างท้าย prefill ทิ้งก่อน
    if trimmed and content.startswith(trimmed):
        return content[len(trimmed):]
    return content                      # ไม่ได้ echo มา ก็ถือว่าเป็นท่อนใหม่ล้วน


def _process(job: dict, kind: str) -> None:
    """ทำงานหนึ่งรอบ: ท่อนแรก, Extend Mode หลายท่อน, หรือต่ออีกหนึ่งท่อนจาก /continue"""
    if job["history"] is None:
        # snapshot ประวัติตอนได้คิวจริง คำถามที่ส่งตามมาติดๆ จะได้เห็นคำตอบก่อนหน้า
        job["history"] = _session_history(job["session"])

    # /continue = หนึ่งท่อนพอ (ผู้ใช้สั่งเอง) ส่วน Extend Mode วนได้ถึงเพดาน 3 ท่อน
    budget = 1 if kind == "continue" else (MAX_SEGMENTS if job["extend"] else 1)
    used = 0
    hit_cap = False
    while used < budget:
        prefill = job["answer"]
        content, finish, err = _chat(_messages_for(job), job["max_tokens"], job["thinking"])
        if err:
            job["status"] = "error"
            job["error"] = err
            break
        job["answer"] += _strip_echo(prefill, content)
        job["finish_reason"] = finish or "stop"
        job["segments"] += 1
        used += 1
        if job["finish_reason"] != "length":
            break        # จบเองแล้ว ไม่ต้องต่อ
        if used >= budget:
            hit_cap = budget > 1      # ยังไม่จบแต่ชนเพดาน Extend Mode พอดี
            break

    if job["status"] != "error":
        job["status"] = "done"
        if job["finish_reason"] == "length" and hit_cap:
            job["note"] = ("Extend Mode หยุดที่ %d ท่อนตามเพดาน คำตอบยังไม่จบ "
                           "ถ้าต้องการต่อให้เรียก /v1/job/%s/continue"
                           % (MAX_SEGMENTS, job["id"]))
        elif job["finish_reason"] == "length":
            job["note"] = "คำตอบถูกตัดกลางคัน เรียก /v1/job/%s/continue เพื่อต่อได้" % job["id"]
        else:
            job["note"] = ""
        _session_commit(job)

    job["finished"] = _utc_iso()
    job["elapsed"] = time.time() - job["t0"] if job["t0"] else 0.0
    guard.audit("gateway_job", {"job": job["id"], "session": job["session"] or None,
                                "status": job["status"], "segments": job["segments"],
                                "finish_reason": job["finish_reason"],
                                "answer_chars": len(job["answer"]),
                                "elapsed_sec": round(job["elapsed"], 1),
                                "error": job["error"][:200]})


def _worker_loop() -> None:
    """เธรดเดียวไล่ระบายคิว — 27B รันพร้อมกันสองงานไม่ได้ ดูหมายเหตุหัวไฟล์"""
    while True:
        item = _Q.get()
        try:
            if item is None:
                return
            kind, jid = item
            with _LOCK:
                job = _JOBS.get(jid)
                if jid in _ORDER:
                    _ORDER.remove(jid)
                if job is None:
                    continue
                job["status"] = "running"
                job["started"] = job["started"] or _utc_iso()
                job["t0"] = job["t0"] or time.time()
                _RUNNING["id"] = jid
            try:
                _process(job, kind)
            except Exception as exc:        # เธรดคิวต้องไม่ตาย ไม่ว่าจะเจออะไร
                with _LOCK:
                    job["status"] = "error"
                    job["error"] = "%s: %s" % (type(exc).__name__, exc)
                    job["finished"] = _utc_iso()
                guard.audit("gateway_job", {"job": jid, "status": "error",
                                            "error": job["error"][:200]})
            finally:
                with _LOCK:
                    _RUNNING["id"] = None
        finally:
            _Q.task_done()


def _start_worker() -> None:
    global _WORKER
    with _LOCK:
        if _WORKER and _WORKER.is_alive():
            return
        _WORKER = threading.Thread(target=_worker_loop, name="gateway-worker", daemon=True)
        _WORKER.start()


# ------------------------------------------------------------- HTTP handler
class _Handler(BaseHTTPRequestHandler):
    server_version = "GatewayLocal/1.0"
    protocol_version = "HTTP/1.1"          # ตอบทุกครั้งพร้อม Content-Length เสมอ

    # ---------- helpers ----------
    def log_message(self, fmt, *args):     # noqa: N802
        """เงียบไว้ ให้ audit.log เป็นที่บันทึกที่เดียว กัน header/คีย์หลุดลง console"""
        return

    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass                            # ผู้เรียกปิดไปก่อน ไม่ใช่เรื่องของเรา

    def _audit(self, code: int, extra: dict | None = None) -> None:
        detail = {"method": self.command, "path": urlsplit(self.path).path, "status": code}
        detail.update(extra or {})
        guard.audit("gateway", detail)      # ไม่มีคีย์ ไม่มี header ในนี้ (S02)

    def _drain(self) -> None:
        """อ่าน body ทิ้งให้หมดก่อนจะตอบ error ที่ไม่ได้แตะ body

        *วัดมาแล้ว* protocol_version = HTTP/1.1 แปลว่าคอนเนกชันถูก keep-alive ไว้
        ถ้าตอบ 401/404 โดยไม่ดูด body ที่ค้างอยู่ใน rfile ไบต์ที่เหลือจะถูก parser
        ของคำขอถัดไปอ่านเป็น "บรรทัดคำขอ" ทันที ยิงสองคำขอบนซ็อกเก็ตเดียวได้ผลนี้จริง:

            HTTP/1.1 401 Unauthorized
            HTTP/1.1 400 Bad request syntax ('{"prompt": "AAAA"}GET /health HTTP/1.1')

        คือคำขอที่สองถูกกลืนหายไปกับ body ของคำขอแรก เป็น request-desync เต็มรูปแบบ
        และเกิดได้จากผู้เรียกที่ยังไม่ผ่าน auth ด้วย
        """
        if getattr(self, "_body_done", False):
            return
        self._body_done = True
        if _s(self.headers.get("Transfer-Encoding")).strip():
            self.close_connection = True      # chunked: ไม่รู้ว่ายาวเท่าไร ปิดไปเลย
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.close_connection = True
            return
        if length <= 0:
            return
        if length > MAX_BODY:
            self.close_connection = True      # ไม่ดูดไบต์ยักษ์ทิ้งให้เปลืองแรง
            return
        try:
            self.rfile.read(length)
        except OSError:
            self.close_connection = True

    def _body(self) -> tuple[dict | None, str]:
        if getattr(self, "_body_done", False):
            return {}, ""                     # ถูกดูดทิ้งไปแล้ว ไม่มีอะไรให้อ่าน
        if _s(self.headers.get("Transfer-Encoding")).strip():
            # BaseHTTPRequestHandler ไม่ถอด chunked ให้ ถ้ารับไว้จะ desync เหมือนกัน
            self._body_done = True
            self.close_connection = True
            return None, "ไม่รองรับ Transfer-Encoding ให้ส่งพร้อม Content-Length"
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._body_done = True
            self.close_connection = True
            return None, "Content-Length ไม่ถูกต้อง"
        if length <= 0:
            self._body_done = True
            return {}, ""
        if length > MAX_BODY:
            self._body_done = True
            self.close_connection = True      # ยังไม่ได้อ่าน body ที่ค้าง ต้องไม่ keep-alive ต่อ
            return None, "body ใหญ่เกิน %d ไบต์" % MAX_BODY
        try:
            raw = self.rfile.read(length).decode("utf-8", "replace")
            self._body_done = True
            data = json.loads(raw)
        except (OSError, ValueError) as exc:
            self._body_done = True
            return None, "อ่าน body เป็น JSON ไม่ได้: %s" % exc
        return (data, "") if isinstance(data, dict) else (None, "body ต้องเป็น JSON object")

    def _auth(self) -> bool:
        """ทุก endpoint ยกเว้น /health ต้องมี X-Api-Key ที่ถูกต้อง"""
        if _key_ok(_s(self.headers.get("X-Api-Key")).strip()):
            return True
        self._drain()          # ต้องทิ้ง body ก่อน ไม่งั้นคำขอถัดไปบนคอนเนกชันเดิมเพี้ยน
        self._send(401, {"error": "ต้องมี header X-Api-Key ที่ถูกต้อง",
                         "key_source": _key_source()})     # บอกที่มา ไม่ใช่ค่า (S02)
        self._audit(401, {"reason": "bad_key"})   # ไม่บันทึกค่าที่ส่งมาผิด
        return False

    def _parts(self) -> list[str]:
        path = unquote(urlsplit(self.path).path)
        return [p for p in path.split("/") if p]

    def _browser_blocked(self) -> bool:
        """ปฏิเสธคำขอที่มาจากหน้าเว็บ (มี header Origin) — ผู้เรียกจริงของ gateway คือสคริปต์

        gateway ไม่มี CORS เบราว์เซอร์จึงอ่านคำตอบไม่ได้อยู่แล้ว แต่ POST แบบ "simple request"
        ยังยิงเข้ามาถึงเซิร์ฟเวอร์ได้ ตัดทิ้งตั้งแต่ต้นดีกว่าให้ไปถึงด่านคีย์
        """
        # กัน DNS rebinding: หน้าเว็บที่โดเมนถูกชี้กลับมา 127.0.0.1 ส่ง Host เป็นโดเมนของผู้โจมตี
        # และ GET แบบธรรมดาไม่มี Origin จึงหลุดด่านข้างล่าง (/health เคยตอบสถานะกับหน้าแบบนี้)
        # ใช้พอร์ตที่ socket ฟังอยู่จริง ไม่ใช่ค่าคงที่ เพราะเปิดพอร์ตอื่นได้จาก argv
        port = self.server.server_address[1]
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in ("127.0.0.1:%d" % port, "localhost:%d" % port):
            self._drain()
            self.close_connection = True
            self._send(403, {"error": "Host ไม่ถูกต้อง"})
            self._audit(403, {"reason": "bad_host"})
            return True
        if self.headers.get("Origin") is None:
            return False
        self._drain()
        self.close_connection = True
        self._send(403, {"error": "gateway ไม่รับคำขอจากหน้าเว็บ (มี header Origin)"})
        self._audit(403, {"reason": "browser_origin"})
        return True

    # ---------- routes ----------
    def do_GET(self) -> None:              # noqa: N802
        self._drain()                      # GET ไม่ใช้ body แต่ถ้ามีมาต้องทิ้งให้หมดก่อน
        if self._browser_blocked():
            return
        parts = self._parts()
        if parts == ["health"]:
            return self._health()
        if not self._auth():
            return
        if parts == ["v1", "sessions"]:
            return self._sessions_list()
        if len(parts) == 3 and parts[:2] == ["v1", "job"]:
            return self._job_get(parts[2])
        self._send(404, {"error": "ไม่รู้จัก endpoint นี้"})
        self._audit(404)

    def do_POST(self) -> None:             # noqa: N802
        if self._browser_blocked():
            return
        parts = self._parts()
        if not self._auth():
            return
        if parts == ["v1", "prompt"]:
            return self._prompt()
        if len(parts) == 4 and parts[:2] == ["v1", "job"] and parts[3] == "continue":
            return self._continue(parts[2])
        self._drain()                      # 404 บน POST ก็ยังมี body ค้างอยู่
        self._send(404, {"error": "ไม่รู้จัก endpoint นี้"})
        self._audit(404)

    def do_DELETE(self) -> None:           # noqa: N802
        self._drain()                      # เช่นเดียวกับ GET
        if self._browser_blocked():
            return
        parts = self._parts()
        if not self._auth():
            return
        if len(parts) == 3 and parts[:2] == ["v1", "session"]:
            return self._session_delete(parts[2])
        self._send(404, {"error": "ไม่รู้จัก endpoint นี้"})
        self._audit(404)

    # ---------- handlers ----------
    def _health(self) -> None:
        model, err = _model_name()
        with _LOCK:
            depth, running = len(_ORDER), _RUNNING["id"]
            jobs = len(_JOBS)
        with _SESS_LOCK:
            sessions = len(_SESSIONS)
        out = {
            "status": "ok",
            "upstream": UPSTREAM,
            "upstream_ok": bool(model),
            "model": model or None,
            "upstream_error": err or None,
            "queue_depth": depth,
            "running_job": running,
            "jobs_tracked": jobs,
            "sessions": sessions,
            "bind": "%s:%s" % (HOST, self.server.server_address[1]),
            "key_source": _key_source(),    # บอกแค่ที่มา ไม่ใช่ค่าคีย์ (S02)
            "uptime_sec": round(time.time() - _STARTED_AT, 1),
        }
        self._send(200, out)
        self._audit(200, {"upstream_ok": out["upstream_ok"], "queue_depth": depth})

    def _prompt(self) -> None:
        data, err = self._body()
        if err:
            self._send(400, {"error": err})
            return self._audit(400)
        prompt = _s((data or {}).get("prompt")).strip()
        if not prompt:
            self._send(400, {"error": "ต้องมีฟิลด์ prompt"})
            return self._audit(400)
        if len(prompt) > MAX_PROMPT_CHARS:
            self._send(400, {"error": "prompt ยาวเกิน %d ตัวอักษร" % MAX_PROMPT_CHARS})
            return self._audit(400)
        session = _s((data or {}).get("session")).strip()[:64]
        max_tokens = _clamp_int((data or {}).get("max_tokens"), 1, MAX_MAX_TOKENS,
                                DEFAULT_MAX_TOKENS)
        extend = _truthy((data or {}).get("extend"))
        thinking = _truthy((data or {}).get("thinking"))     # ปิดไว้เป็นค่าเริ่มต้น

        # _prune_jobs ทิ้งได้เฉพาะงานที่จบแล้ว งานที่ยังรอคิวจึงสะสมไม่มีเพดาน
        # ผู้เรียกที่วนลูปพลาด (หรือสคริปต์ที่ retry) ยิงได้เรื่อยๆ จนกิน RAM
        # ที่ prompt ละไม่เกิน 32KB และ 27B เดินราว 1.5 token/วินาที คิว 32 งานก็หลายชั่วโมงแล้ว
        with _LOCK:
            waiting = len(_ORDER)
        if waiting >= MAX_QUEUED:
            self._send(429, {"error": "คิวเต็มแล้ว (รออยู่ %d งาน เพดาน %d) "
                                      "รอให้งานเดิมเสร็จก่อนแล้วค่อยส่งใหม่"
                                      % (waiting, MAX_QUEUED),
                             "queue_depth": waiting})
            return self._audit(429, {"queue_depth": waiting, "reason": "queue_full"})

        job = _new_job(prompt, session, max_tokens, extend, thinking)
        _Q.put(("prompt", job["id"]))
        pos = _queue_position(job["id"])
        pub = _job_public(job)
        pub["message"] = ("เข้าคิวแล้ว ลำดับที่ %d ติดตามผลที่ /v1/job/%s" % (pos, job["id"])
                          if pos else "กำลังทำอยู่ ติดตามผลที่ /v1/job/%s" % job["id"])
        self._send(202, pub)
        # S02/สมุดงาน: ลง audit ได้ไม่เกิน 200 ตัวอักษรแรกของ prompt
        self._audit(202, {"job": job["id"], "session": session or None,
                          "queue_position": pos, "extend": extend,
                          "max_tokens": max_tokens,
                          "prompt": prompt[:AUDIT_PROMPT_CHARS]})

    def _job_get(self, jid: str) -> None:
        with _LOCK:
            job = _JOBS.get(_s(jid).strip())
        if not job:
            self._send(404, {"error": "ไม่พบงาน %s" % jid})
            return self._audit(404, {"job": jid})
        self._send(200, _job_public(job))
        self._audit(200, {"job": job["id"], "job_status": job["status"]})

    def _continue(self, jid: str) -> None:
        data, err = self._body()
        if err:
            self._send(400, {"error": err})
            return self._audit(400, {"job": jid})
        with _LOCK:
            job = _JOBS.get(_s(jid).strip())
            if not job:
                self._send(404, {"error": "ไม่พบงาน %s" % jid})
                return self._audit(404, {"job": jid})
            if job["status"] in ("queued", "running"):
                self._send(409, {"error": "งาน %s ยังทำไม่เสร็จ รอให้จบก่อนแล้วค่อยต่อ" % job["id"]})
                return self._audit(409, {"job": job["id"]})
            if job["status"] == "error":
                self._send(409, {"error": "งาน %s จบด้วยข้อผิดพลาด ต่อไม่ได้" % job["id"]})
                return self._audit(409, {"job": job["id"]})
            force = _truthy((data or {}).get("force"))
            if job["finish_reason"] != "length" and not force:
                # ต่อคำตอบที่จบสมบูรณ์แล้วมักได้ข้อความงอกแปลกๆ ถ้าจงใจให้ส่ง force=true
                self._send(409, {"error": "คำตอบจบสมบูรณ์แล้ว (finish_reason=%s) "
                                          "ถ้ายังต้องการต่อจริงให้ส่ง force=true"
                                          % (job["finish_reason"] or "?")})
                return self._audit(409, {"job": job["id"], "reason": "not_truncated"})
            # ไม่มีการรีเซ็ต segments ตรงนี้: /continue เป็นคำสั่งที่ผู้ใช้กดเอง จึงต่อได้
            # เกินเพดาน 3 ท่อนของ Extend Mode และตัวนับต้องบอกความจริงว่าใช้ไปกี่ท่อนแล้ว
            if _s((data or {}).get("max_tokens")):
                job["max_tokens"] = _clamp_int((data or {}).get("max_tokens"), 1,
                                               MAX_MAX_TOKENS, job["max_tokens"])
            job["status"] = "queued"
            job["note"] = ""
            job["finished"] = ""
            # จับเวลาท่อนใหม่ใหม่หมด ไม่งั้น elapsed_sec จะนับเวลาที่งานนอนรอผู้ใช้กด
            # /continue รวมเข้าไปด้วย แล้วรายงานเวลาที่ไม่ได้ใช้ generate จริง
            job["t0"] = 0.0
            job["elapsed"] = 0.0
            job["started"] = ""     # ให้ started กับ elapsed_sec พูดถึงรอบเดียวกัน
            _ORDER.append(job["id"])
        _Q.put(("continue", job["id"]))
        pub = _job_public(job)
        pub["message"] = "สั่งต่อคำตอบแล้ว อีกหนึ่งท่อน ติดตามที่ /v1/job/%s" % job["id"]
        self._send(202, pub)
        self._audit(202, {"job": job["id"], "session": job["session"] or None,
                          "action": "continue"})

    def _sessions_list(self) -> None:
        with _SESS_LOCK:
            items = [{"id": sid,
                      "messages": len(rec["messages"]),
                      "chars": sum(len(m["content"]) for m in rec["messages"]),
                      "created": rec["created"],
                      "last_activity": rec["updated"]}
                     for sid, rec in _SESSIONS.items()]
        items.sort(key=lambda r: r["last_activity"], reverse=True)
        self._send(200, {"count": len(items), "sessions": items,
                         "max_history_messages": MAX_HISTORY_MSGS})
        self._audit(200, {"sessions": len(items)})

    def _session_delete(self, sid: str) -> None:
        sid = _s(sid).strip()
        with _SESS_LOCK:
            gone = _SESSIONS.pop(sid, None)
        if gone is None:
            self._send(404, {"error": "ไม่พบ session %s" % sid})
            return self._audit(404, {"session": sid})
        _save_sessions()
        self._send(200, {"deleted": sid, "messages_removed": len(gone["messages"])})
        self._audit(200, {"session": sid, "action": "delete",
                          "messages_removed": len(gone["messages"])})


# ------------------------------------------------------------------- public
def gateway_status() -> str:
    """สรุปสถานะสั้นๆ สำหรับเรียกจากโค้ดอื่น (ไม่เปิดเซิร์ฟเวอร์)

    คืน str เสมอตามสัญญาหัวไฟล์ ข้อผิดพลาดคืนเป็นข้อความขึ้นต้น "ERROR: "
    เพราะ server.py เรียกผ่าน tools/call ถ้าโยนออกไปจะกลายเป็น isError ที่อ่านไม่รู้เรื่อง
    """
    try:
        model, err = _model_name()
        with _LOCK:
            depth, jobs, running = len(_ORDER), len(_JOBS), _RUNNING["id"]
        with _SESS_LOCK:
            sessions = len(_SESSIONS)
        lines = [
            "Remote Prompt Gateway",
            "  ผูกที่        : %s:%d (loopback เท่านั้น)" % (HOST, PORT),
            "  llama-server  : %s" % (("พร้อม โมเดล %s" % model) if model else "ไม่พร้อม (%s)" % err),
            "  คิว           : รออยู่ %d งาน, กำลังทำ %s" % (depth, running or "-"),
            "  งานในหน่วยความจำ: %d" % jobs,
            "  session       : %d" % sessions,
            "  คีย์           : %s (ไม่แสดงค่าในนี้)" % _key_source(),
        ]
        return "\n".join(lines)
    except Exception as exc:                 # noqa: BLE001 — สัญญาคือไม่โยน
        return "ERROR: อ่านสถานะ gateway ไม่ได้: %s: %s" % (type(exc).__name__, exc)


def gateway_sessions() -> str:
    """รายชื่อ session ที่ gateway จำไว้ พร้อมจำนวนข้อความและเวลาใช้งานล่าสุด

    อ่านอย่างเดียว ไม่แตะเครื่อง ไม่แสดงเนื้อข้อความ (อาจมีข้อมูลของผู้ใช้อยู่ในนั้น)
    """
    try:
        if not _SESSIONS:
            _load_sessions()                 # โปรเซสนี้อาจไม่ใช่ตัวที่รันเซิร์ฟเวอร์
        with _SESS_LOCK:
            items = sorted(
                ((sid, len(rec["messages"]), _s(rec.get("updated")))
                 for sid, rec in _SESSIONS.items()),
                key=lambda r: r[2], reverse=True)
        if not items:
            return "ยังไม่มี session ใน gateway"
        lines = ["session ของ gateway (%d รายการ)" % len(items)]
        for sid, n, upd in items:
            lines.append("  %-24s %2d ข้อความ  ใช้งานล่าสุด %s" % (sid[:24], n, upd or "-"))
        return "\n".join(lines)
    except Exception as exc:                 # noqa: BLE001
        return "ERROR: อ่านรายชื่อ session ไม่ได้: %s: %s" % (type(exc).__name__, exc)


# server.py วน MODULES แล้วอ่าน TOOLS/IMPL จากแต่ละโมดูล ไฟล์นี้เคยไม่มีทั้งสองตัว
# ผลคือถึงจะใส่ "gateway" ลง MODULES เซิร์ฟเวอร์ก็โหลดผ่านแบบเงียบๆ แล้วได้เครื่องมือ 0 ชิ้น
# เปิดเฉพาะของที่อ่านอย่างเดียว: serve() บล็อกตลอดกาล ห้ามให้โมเดลเรียกเด็ดขาด
# ไม่มีพารามิเตอร์ project เพราะ gateway ผูกกับ project_dir("gateway") ของตัวเองตายตัว (S04)
TOOLS = [
    {"name": "gateway_status",
     "description": ("ดูสถานะ Remote Prompt Gateway: ผูกพอร์ตไหน llama-server ปลายทางพร้อมไหม "
                     "ใช้โมเดลตัวใด มีงานรอคิวกี่งาน กำลังทำงานไหนอยู่ และมี session กี่ชุด "
                     "ใช้ตอบคำถามทำนอง \"gateway ยังรับ prompt จากข้างนอกได้ไหม\""),
     "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "gateway_sessions",
     "description": ("ดูรายชื่อบทสนทนา (session) ที่ gateway จำไว้ พร้อมจำนวนข้อความ "
                     "และเวลาที่ใช้งานล่าสุด ไม่แสดงเนื้อข้อความ"),
     "inputSchema": {"type": "object", "properties": {}, "required": []}},
]

IMPL = {
    "gateway_status": gateway_status,
    "gateway_sessions": gateway_sessions,
}


def serve(port: int = PORT) -> str:
    """เปิดเซิร์ฟเวอร์และบล็อกจนกว่าจะถูกหยุด คืนข้อความสรุปเมื่อปิด"""
    try:
        _ensure_key()
    except Denied as exc:
        return "ERROR: สร้างไฟล์คีย์ไม่ได้: %s" % exc
    _load_sessions()
    _start_worker()
    try:
        httpd = ThreadingHTTPServer((HOST, port), _Handler)
    except OSError as exc:
        return "ERROR: เปิดพอร์ต %d ไม่ได้: %s" % (port, exc)

    bound = httpd.server_address[1]
    guard.audit("gateway_start", {"bind": "%s:%d" % (HOST, bound), "upstream": UPSTREAM})
    print("Remote Prompt Gateway ทำงานที่ http://%s:%d" % (HOST, bound))
    print("llama-server ปลายทาง: %s" % UPSTREAM)
    print("คีย์ API: %s (ไม่แสดงค่าออกหน้าจอ)" % _key_source())
    print("ข้อมูล session: %s" % os.path.join(guard.project_dir(PROJECT), SESSIONS_NAME))
    print("กด Ctrl+C เพื่อหยุด")
    sys.stdout.flush()
    try:
        httpd.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        _save_sessions()
        guard.audit("gateway_stop", {"bind": "%s:%d" % (HOST, bound)})
    return "ปิด gateway ที่พอร์ต %d แล้ว (session ถูกบันทึกลงดิสก์เรียบร้อย)" % bound


if __name__ == "__main__":
    # Thai print() ตายถ้า stdout ถูกไพป์แล้วยังเป็น cp1252 — ตั้งให้ชัวร์ตั้งแต่ต้น
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    _port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(serve(_port))
