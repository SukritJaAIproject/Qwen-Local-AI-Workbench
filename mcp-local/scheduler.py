# -*- coding: utf-8 -*-
"""scheduler.py -- ตัวตั้งเวลาของสแตก qwenlocal (สมุดงานข้อ #22 และ #23)

งานที่ตั้งไว้
  heartbeat        ทุก 30 นาที   ตรวจว่าทั้งสแตกยังตอบอยู่ไหม แล้วบันทึกผล "รายบริการ"
                                 (llama-server, MCP local, MCP websearch, project hub)
  memory_promote   ทุกวัน 03:00  "daily dreaming" ของสมุดงาน — ในที่นี้แปลว่า *งานบ้าน*
                                 ของความจำ ไม่ใช่การให้โมเดลแต่งข้อความใหม่ คือจัดระเบียบ
                                 MEMORY.md ของทุกโปรเจกต์ให้อ่านง่าย ทิ้งของซ้ำและของหมดอายุ

สิ่งที่โมดูลนี้จงใจ "ไม่" ทำ
  1. ไม่เรียก LLM ไม่ว่ากรณีใด และไม่ส่งข้อมูลของโปรเจกต์ออกไปไหนทั้งสิ้น
     heartbeat ยิงแค่ GET ไปที่ endpoint สุขภาพของแต่ละบริการ ไม่เคยส่ง prompt
     (สมุดงานบันทึกไว้ว่า "รอบล่าสุดเคย error จาก context/timeout" — ต้นเหตุคือ heartbeat
      แบบเดิมที่ทักโมเดลจริง ตัวนี้จึงใช้ timeout 5 วินาที และไม่มี prompt เลย)
  2. ไม่แก้ memory.json ของใคร ไฟล์นั้นคือความจริง ส่วน MEMORY.md คือ "มุมมอง" ที่สร้างใหม่ได้
     งานบ้านจึงเขียนทับเฉพาะ MEMORY.md และสำรองของเดิมไว้ที่ MEMORY.md.bak ก่อนเสมอ
  3. ไม่เริ่มเธรดหรือจับเวลาใดๆ ตอน import — server.py import โมดูลนี้เพื่อเอา TOOLS/IMPL
     ถ้า import แล้ววงรอบเริ่มเอง เครื่องนี้จะมีตัวตั้งเวลาสองตัวทันที
     ตัวตั้งเวลาเริ่มทำงานเฉพาะตอนรันเป็น __main__ เท่านั้น

วิธีรัน
  python scheduler.py              รันค้างไว้เป็นตัวตั้งเวลา (ปกติ)
  python scheduler.py status       พิมพ์ตารางสถานะแล้วออก
  python scheduler.py heartbeat    สั่ง heartbeat หนึ่งรอบแล้วออก
  python scheduler.py promote      สั่งงานบ้านความจำหนึ่งรอบแล้วออก

สถานะทั้งหมดอยู่ที่ scheduler_state.json ข้างไฟล์นี้ จึงรอด restart
ทุกฟังก์ชันสาธารณะคืน str เสมอ ข้อผิดพลาดคืนเป็นข้อความขึ้นต้นด้วย "ERROR: " ไม่โยน exception
"""
from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone

import guard
from guard import Denied

# token ของบริการในเครื่อง (สัญญา C1/C2): MCP 8791/8792 ตอบ 401 ถ้าไม่มี Authorization
# secrets_util อยู่ที่ C:\LLM (โฟลเดอร์แม่) ต่อท้าย sys.path ไม่แทรกหน้า กันชื่อไปทับ stdlib
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.append(_ROOT)
try:
    import secrets_util
except Exception:                                # noqa: BLE001 - ไม่มีตัวช่วย = heartbeat ของ MCP จะแดงเอง
    secrets_util = None

# งานบ้านความจำต้องใช้ตัวตรวจจับความลับตัวเดียวกับที่ tools_memory ใช้ตอนเขียน
# ถ้า import ไม่ได้ เราจะ "ไม่แตะไฟล์ใดๆ เลย" ดีกว่าเขียนใหม่โดยไม่มีตัวกรอง S02
try:
    from tools_memory import KIND_TH, MEMORY_JSON, MEMORY_MD, scan_secret
    _MEM_ERR = ""
except Exception as exc:                        # noqa: BLE001 - โมดูลพังแบบไหนก็ต้องรอด
    KIND_TH, MEMORY_JSON, MEMORY_MD, scan_secret = {}, "memory.json", "MEMORY.md", None
    _MEM_ERR = "%s: %s" % (type(exc).__name__, exc)

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "scheduler_state.json")
PROJECT_DATA = r"C:\LLM\projects\data"

HEARTBEAT_EVERY = 30 * 60        # วินาที — สมุดงานข้อ #23
PROMOTE_HOUR, PROMOTE_MINUTE = 3, 0
CATCHUP_AFTER = 24 * 3600        # ถ้าเครื่องดับข้ามคืน ตื่นมาแล้วเกินเท่านี้ให้ตามเก็บหนึ่งรอบ
PROGRESS_MAX_AGE_DAYS = 180      # progress คือของชั่วคราวโดยธรรมชาติ เกินนี้ถือว่าหมดอายุ
HTTP_TIMEOUT = 5.0               # สั้นไว้ เพราะ heartbeat ที่ค้างคือ heartbeat ที่ใช้ไม่ได้
MAX_BODY = 200_000               # อ่านคำตอบแค่นี้พอ กันบริการที่ตอบยาวผิดปกติ
TICK = 15.0                      # วงรอบตื่นมาดูว่ามีงานถึงกำหนดไหม
JOB_NAMES = ("heartbeat", "memory_promote", "gpu_watch")
GPU_WATCH_EVERY = 60            # วินาที — เฝ้าชุด GPU (เสียบ/ถอด eGPU) ตรวจถูก (nvidia-smi ~0.2 วินาที)
GPU_WATCH_CONFIRM = 2           # เห็นชุดใหม่กี่รอบติดกันจึงเชื่อ (eGPU ที่เพิ่งเสียบอาจโผล่/หายวูบ)
GPU_WATCH_COOLDOWN = 300        # วินาที — สั่งจัดแผนซ้ำชุดเดิมไม่ถี่กว่านี้ (กันวนถ้าตัวเปิดล้มซ้ำ)
GPU_APPLY_STALE = 20 * 60       # วินาที — state "running" ของ hub ที่เก่ากว่านี้ถือว่าค้าง
ROUTER_STATE_PATH = r"C:\LLM\logs\router-8099.state.json"
GPU_APPLY_STATE_PATH = r"C:\LLM\logs\gpu-apply.state.json"
HUB_APPLY_URL = "http://127.0.0.1:8100/api/gpu/apply"
GPU_LAUNCHER = r"C:\LLM\start-qwen38.ps1"

# เปิด opener ที่ "ไม่ผ่าน proxy" ไว้ตัวเดียวใช้ตลอด
# ถ้าเครื่องมี HTTP_PROXY/ALL_PROXY ตั้งไว้ urllib จะลากคำขอไป 127.0.0.1 ผ่าน proxy ด้วย
# ผลคือ heartbeat แดงทั้งที่บริการปกติดี — เคยเจอมาแล้วตอนตั้ง mcp-websearch
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

_LOCK = threading.RLock()        # กันสองเธรดในโปรเซสเดียวกันเขียน state ทับกัน


# ------------------------------------------------------------ เครื่องมือภายใน

def _safe(fn):
    """ครอบเครื่องมือทุกตัว: เกิดอะไรขึ้นก็คืนเป็นสตริง ไม่โยนออกไปหาเซิร์ฟเวอร์"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Denied as exc:
            return "ERROR: ถูกปฏิเสธโดยนโยบายความปลอดภัย: %s" % exc
        except TypeError as exc:
            return "ERROR: อาร์กิวเมนต์ไม่ถูกต้องสำหรับ %s: %s" % (fn.__name__, exc)
        except Exception as exc:                # noqa: BLE001 - กันทุกกรณี
            return "ERROR: %s ล้มเหลว: %s: %s" % (fn.__name__, type(exc).__name__, exc)
    return wrapper


def _dwidth(text: str) -> int:
    """ความกว้างที่ตาเห็น: สระบนล่างและวรรณยุกต์ไทยไม่กินเนื้อที่ในคอลัมน์"""
    return sum(0 if unicodedata.combining(ch) else 1 for ch in text)


def _pad(text: str, width: int, right: bool = False) -> str:
    fill = " " * max(0, width - _dwidth(text))
    return (fill + text) if right else (text + fill)


def _table(rows: list[tuple], right: tuple = ()) -> list[str]:
    """จัดคอลัมน์ให้ตรงกัน คอลัมน์สุดท้ายปล่อยยาวได้ (ไม่ต้อง pad)"""
    ncol = len(rows[0])
    widths = [max(_dwidth(str(r[i])) for r in rows) for i in range(ncol - 1)]
    lines = []
    for i, r in enumerate(rows):
        cells = [_pad(str(r[j]), widths[j], j in right) for j in range(ncol - 1)]
        lines.append("  ".join(cells + [str(r[-1])]).rstrip())
        if i == 0:
            lines.append("-" * min(110, _dwidth(lines[0])))
    return lines


def _short(value, limit: int = 120) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fmt_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "%dวิ" % seconds
    if seconds < 3600:
        return "%dน %dวิ" % (seconds // 60, seconds % 60)
    if seconds < 86400:
        return "%dชม %dน" % (seconds // 3600, (seconds % 3600) // 60)
    return "%dวัน %dชม" % (seconds // 86400, (seconds % 86400) // 3600)


def _epoch_or_none(value):
    """คืน float ที่ "ใช้เป็นเวลาได้จริง" เท่านั้น อย่างอื่นคืน None

    scheduler_state.json ถูกเขียนจากสองโปรเซสและผู้ใช้แก้ด้วยมือได้ ถ้าในไฟล์มีตัวเลขเพี้ยน
    (เช่น 1e20 หรือ 9e15) datetime.fromtimestamp จะโยน OverflowError/OSError ออกมา
    ของเดิมปล่อยให้มันหลุดออกจากวงรอบใน run_forever แล้วตัวตั้งเวลาตายทั้งตัวเงียบๆ
    ที่นี่จึงลองแปลงให้ดูก่อน ค่าที่แปลงไม่ได้ให้ถือว่า "ยังไม่เคยรัน" แล้วเดินต่อ
    """
    try:
        epoch = float(value or 0)
    except (TypeError, ValueError):
        return None
    if not epoch:
        return None
    try:
        datetime.fromtimestamp(epoch)
    except (OverflowError, OSError, ValueError):
        return None
    return epoch


def _fmt_when(epoch) -> str:
    """เวลาแบบท้องถิ่น — ผู้ใช้อ่านตารางนี้เทียบกับนาฬิกาบนผนัง ไม่ใช่ UTC"""
    epoch = _epoch_or_none(epoch)
    if epoch is None:
        return "ยังไม่เคยรัน"
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


def _say(text: str) -> None:
    """print ที่ไม่ตายเพราะภาษาไทย (stdout ที่ถูกไพป์ต่อจะเป็น cp1252 บนเครื่องนี้)"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()


# ------------------------------------------------------------------- สถานะ

def _blank_state() -> dict:
    return {"version": 1, "jobs": {}, "runner": {}}


def _load_state() -> dict:
    """อ่านสถานะจากดิสก์ ถ้าไฟล์หายหรือพังให้เริ่มใหม่ ไม่ทำให้ทั้งตัวตั้งเวลาล้ม"""
    try:
        # ไฟล์นี้อยู่ในรายการ "บันทึกรวมของสแตก" ที่เครื่องมือของโมเดลอ่านไม่ได้ (guard.STACK_READ_BLOCKED)
        # แต่เป็นของ scheduler เอง path คงที่ในโค้ด จึงอ่านด้วยสิทธิ์ internal แบบเดียวกับ _save_state
        # (ถ้าไม่ครอบ ด่านจะปฏิเสธเงียบๆ แล้วสถานะทั้งหมด รวม pid ของ runner กลายเป็นค่าว่าง)
        with guard.internal():
            path = guard.check_read(STATE_PATH)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (Denied, OSError, ValueError):
        return _blank_state()
    if not isinstance(data, dict):
        return _blank_state()
    data.setdefault("version", 1)
    if not isinstance(data.get("jobs"), dict):
        data["jobs"] = {}
    if not isinstance(data.get("runner"), dict):
        data["runner"] = {}
    return data


def _save_state(state: dict) -> None:
    """เขียนแบบ atomic เหมือน tools_memory: ไฟล์ชั่วคราวข้างๆ แล้ว replace ทับ

    ทั้งตัวตั้งเวลาและ server.py (ตอนผู้ใช้สั่ง schedule_run) เขียนไฟล์นี้คนละโปรเซส
    os.replace เป็น atomic บน NTFS จึงไม่มีทางอ่านเจอ JSON ครึ่งไฟล์
    """
    # STATE_PATH อยู่ใน C:\LLM\mcp-local ซึ่งเป็นเขตห้ามเขียนของเครื่องมือ (โมเดลห้ามแก้)
    # แต่ไฟล์นี้เป็นของ scheduler เอง path เป็นค่าคงที่ในโค้ด จึงใช้สิทธิ์ internal
    with guard.internal():
        path = guard.check_write(STATE_PATH)
        tmp = guard.check_write(path + ".tmp")     # ไฟล์ชั่วคราวก็ต้องผ่านด่านเดียวกัน
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _record(job: str, status: str, message: str, extra: dict | None = None) -> dict:
    """บันทึกผลของงานหนึ่งรอบ แล้วคืนเรคอร์ดที่บันทึกไป

    อ่าน-แก้-เขียนใหม่ทุกครั้ง (ไม่ถือ state ค้างไว้ในหน่วยความจำ) เพราะอีกโปรเซส
    อาจเพิ่งบันทึกผลของงานอื่นลงไป ถ้าเขียนทับด้วยสำเนาเก่าจะทำให้ผลนั้นหาย
    """
    with _LOCK:
        state = _load_state()
        rec = state["jobs"].get(job) if isinstance(state["jobs"].get(job), dict) else {}
        ok = status == "ok"
        rec.update({
            "lastRun": _utc_now(),
            "lastRunEpoch": time.time(),
            "lastRunStatus": status,
            "message": _short(message, 300),
            # สมุดงานวัดผลด้วย "ต้องมี lastRunStatus ok ติดต่อกัน" จึงต้องนับต่อเนื่องให้เห็น
            "consecutiveOk": int(rec.get("consecutiveOk") or 0) + 1 if ok else 0,
            "runs": int(rec.get("runs") or 0) + 1,
        })
        if not ok:
            rec["lastError"] = rec["lastRun"]
        if extra:
            rec.update(extra)
        state["jobs"][job] = rec
        _save_state(state)
    guard.audit("scheduler_job", {"job": job, "status": status,
                                  "consecutive_ok": rec["consecutiveOk"],
                                  "message": _short(message, 200)})
    return rec


def _last_epoch(state: dict, job: str):
    rec = state.get("jobs", {}).get(job)
    if not isinstance(rec, dict):
        return None
    return _epoch_or_none(rec.get("lastRunEpoch"))


# ------------------------------------------------------- งานที่ 1: heartbeat

def _probe(url: str):
    """GET หนึ่งครั้ง คืน (data, detail, ms) — data เป็น None ถ้าไม่สำเร็จ

    ไม่เก็บ body ดิบไว้ที่ไหนเลย (S02) คืนแต่ค่าที่เราตีความเองแล้วเท่านั้น
    """
    t0 = time.monotonic()
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    # ทุกปลายทางใน CHECKS เป็นบริการของสแตกนี้บน 127.0.0.1 จึงแนบ token ให้ (MCP ต้องใช้, ตัวอื่นไม่สน)
    # _OPENER ไม่ผ่าน proxy อยู่แล้ว token จึงไม่มีทางหลุดออกนอกเครื่อง
    if secrets_util is not None and url.startswith("http://127.0.0.1:"):
        try:
            req.add_header("Authorization", secrets_util.auth_headers()["Authorization"])
        except Exception:                        # noqa: BLE001 - ไม่มี token ก็ยิงต่อ ให้ผลบอกว่า 401
            pass
    try:
        with _OPENER.open(req, timeout=HTTP_TIMEOUT) as resp:
            code = getattr(resp, "status", 0) or 0
            raw = resp.read(MAX_BODY)
    except urllib.error.HTTPError as exc:
        return None, "ตอบ HTTP %s" % exc.code, int((time.monotonic() - t0) * 1000)
    except urllib.error.URLError as exc:
        return None, "ต่อไม่ติด (%s)" % _short(exc.reason, 60), int((time.monotonic() - t0) * 1000)
    except Exception as exc:                    # noqa: BLE001 - timeout/reset/อะไรก็ตาม
        return None, "ผิดพลาด %s" % _short(exc, 60), int((time.monotonic() - t0) * 1000)
    ms = int((time.monotonic() - t0) * 1000)
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return None, "คำตอบไม่ใช่ JSON (HTTP %s)" % code, ms
    return data, "", ms


def _v_status_ok(data) -> tuple[bool, str]:
    """llama-server และ MCP ทั้งสองตัวตอบ {"status": "ok", ...} เหมือนกัน"""
    if not isinstance(data, dict):
        return False, "คำตอบไม่ใช่ออบเจกต์ JSON"
    status = str(data.get("status", "")).strip().lower()
    if status != "ok":
        return False, "status = %s" % (_short(status, 40) or "(ไม่มี)")
    tools = data.get("tools")
    if isinstance(tools, list):
        return True, "status ok · เครื่องมือ %d รายการ" % len(tools)
    return True, "status ok"


def _v_projects(data) -> tuple[bool, str]:
    """hub ไม่มี /health เราจึงถือว่า "ตอบรายการโปรเจกต์ได้" คือยังปกติ"""
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, list):
        return False, "JSON ไม่มีรายการ projects"
    return True, "%d โปรเจกต์" % len(projects)


CHECKS = (
    ("llama", "llama-server", "http://127.0.0.1:8099/health", _v_status_ok),
    ("mcp_local", "MCP local", "http://127.0.0.1:8792/mcp", _v_status_ok),
    ("mcp_websearch", "MCP websearch", "http://127.0.0.1:8791/mcp", _v_status_ok),
    ("hub", "project hub", "http://127.0.0.1:8100/api/projects", _v_projects),
)


def job_heartbeat():
    """ตรวจทุกบริการทีละตัว คืน (status, message, extra, รายงานเป็นข้อความ)

    ทุกการตรวจถูกครอบ try แยกกัน ตัวที่ล้มจึงหยุดได้แค่ตัวเอง อีกสามตัวยังถูกตรวจครบ
    และเราบันทึกผล "รายบริการ" ไม่ใช่ boolean รวม จะได้รู้ว่าใครล้ม ไม่ใช่แค่ว่ามีคนล้ม
    """
    checks, rows, down = {}, [("บริการ", "สถานะ", "เวลา", "รายละเอียด")], []
    for key, label, url, validator in CHECKS:
        try:
            data, err, ms = _probe(url)
            if data is None:
                ok, detail = False, err or "ไม่ทราบสาเหตุ"
            else:
                ok, detail = validator(data)
        except Exception as exc:                # noqa: BLE001 - ห้ามให้ตัวเดียวล้มทั้งรอบ
            ok, detail, ms = False, "ตัวตรวจเองพัง: %s" % _short(exc, 60), 0
        checks[key] = {"label": label, "url": url, "status": "ok" if ok else "error",
                       "ms": ms, "detail": detail}
        rows.append((label, "ok" if ok else "ล้ม", "%dms" % ms, detail))
        if not ok:
            down.append(label)

    good = len(CHECKS) - len(down)
    if down:
        status = "error"
        message = "บริการปกติ %d/%d — ล้ม: %s" % (good, len(CHECKS), ", ".join(down))
    else:
        status = "ok"
        message = "บริการปกติ %d/%d" % (good, len(CHECKS))
    report = "\n".join(["ตรวจสุขภาพสแตก (heartbeat)", ""] + _table(rows, right=(2,)) +
                       ["", message])
    return status, message, {"checks": checks, "up": good, "total": len(CHECKS)}, report


# -------------------------------------------------- งานที่ 2: memory_promote

GROUP_ORDER = ("decision", "requirement", "fact", "todo", "progress")

MD_HEADER = (
    "# MEMORY\n"
    "\n"
    "ไฟล์นี้ถูกจัดระเบียบอัตโนมัติโดย scheduler.py (งาน memory_promote) ทุกวันตอนตีสาม\n"
    "ของจริงอยู่ใน memory.json ไฟล์นี้เป็นมุมมองที่อ่านง่าย เรียงใหม่สุดก่อน แยกตามชนิด\n"
    "รายการที่ถูกลบด้วย memory_forget จะไม่ปรากฏที่นี่ และสำเนาก่อนจัดระเบียบอยู่ที่ MEMORY.md.bak\n"
    "\n"
)


def _load_entries(json_path: str):
    """อ่าน memory.json ตามรูปแบบจริงของ tools_memory — คืน (รายการ, รู้จักรูปแบบไหม)

    รับได้ทั้ง {"version":1,"project":...,"entries":[...]} และลิสต์เปล่าๆ แบบเก่า
    (ผ่อนปรนแบบเดียวกับ tools_memory._load_entries เพื่อให้เห็นรายการชุดเดียวกับ memory_recall)

    ทำไมต้องคืนธงบอกว่า "รู้จักรูปแบบไหม" ด้วย: ไฟล์ที่ parse ผ่านแต่รูปแบบไม่ตรง
    (เช่น {} หรือ {"version":1} ที่ไม่มีคีย์ entries หรือ entries ที่ไม่ใช่ลิสต์)
    ของเดิมคืนลิสต์ว่างเหมือนกับกรณี "ลบรายการหมดแล้วจริงๆ" แยกกันไม่ออก
    ผลคือ MEMORY.md ที่มีเนื้อหาอยู่ถูกเขียนทับจนเหลือแต่หัวไฟล์ โดยไม่มีอะไรเตือน
    """
    with open(json_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        raw = data.get("entries")
    elif isinstance(data, list):
        raw = data
    else:
        raw = None
    if not isinstance(raw, list):
        return [], False
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        tags = item.get("tags")
        out.append({
            "id": str(item.get("id") or ""),
            "kind": str(item.get("kind") or "fact"),
            "text": str(item.get("text") or ""),
            "created": str(item.get("created") or ""),
            "tags": [str(t) for t in tags] if isinstance(tags, list) else [],
        })
    return out, True


def _age_days(created: str, now: datetime):
    """อายุเป็นวัน คืน None ถ้าอ่านเวลาไม่ออก (แล้วเราจะเก็บรายการนั้นไว้ ไม่เดาแล้วลบ)"""
    try:
        dt = datetime.fromisoformat(created.strip())
    except (AttributeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 86400.0


def _promote_entries(entries, now: datetime):
    """คัดรายการที่จะเขียนลง MEMORY.md คืน (รายการที่เก็บ, ตัวนับที่ทิ้ง)

    ลำดับใน memory.json คือลำดับที่บันทึก (เก่าไปใหม่) เราจึงเดินตามลำดับนั้น
    แล้วเก็บ "ตัวแรก" ของของซ้ำ เพื่อให้วันที่ที่แสดงเป็นวันที่รู้เรื่องนั้นครั้งแรก
    ส่วนแท็กของตัวที่ซ้ำถูกยุบรวมเข้าตัวแรก จะได้ไม่เสียข้อมูลไปเปล่าๆ
    """
    kept, seen, counts = [], {}, {"dup": 0, "old_progress": 0, "secret": 0, "empty": 0}
    for entry in entries:
        text = entry["text"].strip()
        if not text:
            counts["empty"] += 1
            continue

        # S02 เข็มขัดเส้นที่สอง: tools_memory ปฏิเสธความลับตั้งแต่ตอนเขียนแล้ว
        # แต่รายการที่ถูกเขียนไว้ "ก่อน" จะมีตัวตรวจนั้นยังค้างอยู่ได้ ห้ามคัดลอกต่อเด็ดขาด
        if scan_secret is not None and scan_secret(text + " " + " ".join(entry["tags"])):
            counts["secret"] += 1
            continue

        key = (entry["kind"], text)             # "ซ้ำเป๊ะ" = ชนิดเดียวกันและข้อความตรงกันทุกตัวอักษร
        if key in seen:
            counts["dup"] += 1
            prev = seen[key]
            for tag in entry["tags"]:
                if tag not in prev["tags"]:
                    prev["tags"].append(tag)
            continue

        if entry["kind"] == "progress":
            age = _age_days(entry["created"], now)
            if age is not None and age > PROGRESS_MAX_AGE_DAYS:
                counts["old_progress"] += 1
                continue
        # decision / requirement / fact (และ todo ที่ยังค้าง) ไม่มีวันหมดอายุ

        item = dict(entry, text=text, tags=list(entry["tags"]))
        seen[key] = item
        kept.append(item)
    return kept, counts


def _md_safe(text: str) -> str:
    """กันรายการเดียวปลอมโครงสร้างของทั้งไฟล์

    เนื้อความใน memory.json โมเดลเป็นคนเขียนเองได้ ถ้าเทลงไฟล์ดิบๆ รายการเดียวสามารถแทรก
    บรรทัด "## ข้อเท็จจริง (99)" หรือ "### 2020-01-01 · id-ปลอม" เข้าไปได้
    แล้ว MEMORY.md ที่ถูกอ่านกลับเข้า context ทุกครั้งที่คุยกันก็จะไม่ตรงกับ memory.json อีกต่อไป
    (ทดสอบแล้วทำได้จริง) ใส่ backslash หน้า # ต้นบรรทัดซึ่งเป็น escape มาตรฐานของ Markdown
    ตัวอักษรยังอยู่ครบทุกตัว แค่ไม่ถูกตีความเป็นหัวข้ออีก
    """
    lines = []
    for line in str(text).split("\n"):
        bare = line.lstrip()
        if bare.startswith("#"):
            lines.append(line[:len(line) - len(bare)] + "\\" + bare)
        else:
            lines.append(line)
    return "\n".join(lines)


def _md_tag(tag: str) -> str:
    """แท็กต้องอยู่บรรทัดเดียว ไม่งั้นแท็กที่มี \\n ก็แทรกหัวข้อปลอมได้เหมือนกัน"""
    return " ".join(str(tag).split())


def _render_md(kept) -> str:
    """สร้างเนื้อ MEMORY.md ใหม่ทั้งไฟล์ แยกตามชนิด ใหม่สุดขึ้นก่อน

    จงใจไม่ใส่ "เวลาที่จัดระเบียบ" ลงในไฟล์ ถ้าใส่ ไฟล์จะเปลี่ยนทุกรอบทั้งที่เนื้อหาเท่าเดิม
    แล้วงานนี้จะไม่ idempotent ตามที่ต้องการ เวลารันเก็บไว้ใน scheduler_state.json แทน
    """
    order = {e["id"]: i for i, e in enumerate(kept)}     # ลำดับเดิมใช้ตัดสินตอนเวลาเท่ากัน
    groups = {}
    for entry in kept:
        groups.setdefault(entry["kind"], []).append(entry)

    kinds = [k for k in GROUP_ORDER if k in groups]
    kinds += sorted(k for k in groups if k not in GROUP_ORDER)   # ชนิดแปลกๆ ต่อท้ายไว้ ไม่ทิ้ง

    parts = [MD_HEADER]
    for kind in kinds:
        items = sorted(groups[kind],
                       key=lambda e: (e["created"], order.get(e["id"], 0)), reverse=True)
        parts.append("## %s (%d)\n\n" % (KIND_TH.get(kind, kind), len(items)))
        for entry in items:
            parts.append("### %s · %s\n\n%s\n" % (_md_tag(entry["created"]),
                                                  _md_tag(entry["id"]),
                                                  _md_safe(entry["text"])))
            if entry["tags"]:
                parts.append("\nแท็ก: %s\n" % ", ".join(_md_tag(t) for t in entry["tags"]))
            parts.append("\n")
    if not kinds:
        parts.append("(ยังไม่มีรายการที่ต้องจำในโปรเจกต์นี้)\n")
    return "".join(parts)


def _project_dirs():
    """คืน (ชื่อโปรเจกต์, โฟลเดอร์) ของทุกโปรเจกต์ใต้ PROJECT_DATA

    โฟลเดอร์ของโปรเจกต์จริงถูกตั้งชื่อด้วย guard.project_slug() เสมอ เราจึงรับเฉพาะโฟลเดอร์ที่
    "ชื่อตรงกับ slug ของตัวเอง" ส่วนโฟลเดอร์แปลกปลอมที่หลุดเข้ามาให้ข้ามไป (S04)

    ห้ามใช้ guard.project_dir() ตรงนี้: ข้างในมัน mkdir อยู่ ทำให้ทุกโฟลเดอร์ที่ชื่อไม่ใช่ slug
    ของตัวเอง (เช่น "Weird Name" หรือชื่อยาวเกิน 40 ตัว) ถูกสร้างโฟลเดอร์ใหม่ขึ้นมาทุกครั้งที่เรียก
    และ schedule_run เรียกฟังก์ชันนี้ตั้งแต่ขั้น *พรีวิว* ซึ่งยังไม่มี confirm_token
    เท่ากับเขียนดิสก์ทั้งที่ผู้ใช้ยังไม่อนุมัติ — ผิดกฎ S03 เต็มๆ ตอนนี้จึงไม่สร้างอะไรเลย
    """
    # งานบ้านเดินทุกโปรเจกต์โดยตั้งใจ (เป็นงานของระบบที่ผู้ใช้อนุมัติแล้ว) จึงข้ามขอบเขต S04 ได้
    # เฉพาะ path ที่คำนวณในโค้ดจาก PROJECT_DATA เท่านั้น
    with guard.internal():
        return _project_dirs_inner()


def _project_dirs_inner():
    root = guard.check_read(PROJECT_DATA)
    out = []
    try:
        names = sorted(os.listdir(root), key=str.lower)
    except OSError:
        return out
    for name in names:
        full = os.path.join(root, name)
        if not os.path.isdir(full):
            continue
        # _trash คือที่เก็บข้อมูลของโปรเจกต์ที่ถูกลบ (hub.py archive_project_data) ไม่ใช่โปรเจกต์
        if name.startswith("_"):
            continue
        if guard.project_slug(name) != name:
            continue
        try:
            out.append((name, guard.check_read(full)))   # คลาย junction + ตรวจนโยบายให้ด้วย
        except Denied:
            continue
    return out


def _promote_one(name: str, folder: str, now: datetime) -> tuple[str, str, dict]:
    """จัดระเบียบความจำของโปรเจกต์เดียว คืน (ผลลัพธ์, ข้อความสรุป, ตัวนับ)

    ผลลัพธ์: "written" เขียนใหม่ / "unchanged" เหมือนเดิม / "skipped" ข้าม / "error" พัง
    """
    with guard.internal():                       # เหตุผลเดียวกับ _project_dirs
        return _promote_one_inner(name, folder, now)


def _promote_one_inner(name: str, folder: str, now: datetime) -> tuple[str, str, dict]:
    json_path = os.path.join(folder, MEMORY_JSON)
    md_path = os.path.join(folder, MEMORY_MD)
    if not os.path.exists(json_path):
        # ไม่มีต้นฉบับก็สร้างมุมมองใหม่ไม่ได้ ถ้ามี MEMORY.md อยู่ห้ามแตะเด็ดขาด
        if os.path.exists(md_path):
            return "skipped", "มี MEMORY.md แต่ไม่มี memory.json จึงไม่แตะ", {}
        return "skipped", "ยังไม่มีความจำ", {}

    entries, recognized = _load_entries(guard.check_read(json_path))
    if not recognized:
        # parse ผ่านแต่ไม่ใช่รูปแบบของ tools_memory ถ้าเดาว่า "0 รายการ" แล้วเขียนต่อ
        # MEMORY.md ที่มีของอยู่จะถูกล้างจนเหลือแต่หัวไฟล์ จึงไม่แตะอะไรเลยและบอกให้คนไปดู
        return "skipped", ("memory.json อ่านได้แต่ไม่มีลิสต์ entries ตามรูปแบบของ tools_memory "
                           "จึงไม่เขียนทับ MEMORY.md (กันข้อมูลหาย)"), {}
    kept, counts = _promote_entries(entries, now)
    content = _render_md(kept)

    old = None
    if os.path.exists(md_path):
        try:
            with open(guard.check_read(md_path), "r", encoding="utf-8") as fh:
                old = fh.read()
        except OSError as exc:
            return "error", "อ่าน MEMORY.md ไม่ได้: %s" % _short(exc, 80), counts

    summary = "%d → %d รายการ (ซ้ำ %d · progress เก่า %d · ความลับ %d)" % (
        len(entries), len(kept), counts["dup"], counts["old_progress"], counts["secret"])

    # หัวใจของความ idempotent: เนื้อหาเท่าเดิมแปลว่าไม่ต้องทำอะไรเลย
    # ไม่เขียนทับ ไม่สร้าง .bak ใหม่ mtime ของไฟล์จึงไม่ขยับด้วย
    if old == content:
        return "unchanged", summary + " ไม่มีอะไรเปลี่ยน", counts

    target = guard.check_write(md_path)
    if old is not None:
        bak = guard.check_write(md_path + ".bak")
        shutil.copy2(target, bak)               # สำรองของเดิมก่อนเสมอ
        # ของเดิมอาจมีความลับที่เขียนไว้ก่อนมีตัวกรอง S02 เราตัดมันออกจาก MEMORY.md ก็จริง
        # แต่ .bak ที่เพิ่งสร้างคือสำเนาใหม่ของความลับก้อนเดิม จะรายงานว่า "ตัดออกแล้ว" เฉยๆ ไม่ได้
        # (ไม่ลบ .bak ทิ้งเอง เพราะมันคือทางกลับทางเดียวของผู้ใช้ — เลือกบอกให้รู้แทน)
        # เตือนเฉพาะตอน "ของเก่ามี แต่ของใหม่ไม่มี" ถ้ามีทั้งคู่แปลว่า .bak ไม่ได้เพิ่มอะไร
        # และจะได้ไม่เตือนซ้ำซากเพราะ md5 หรือ hash ที่ผู้ใช้ตั้งใจจดไว้เอง
        if scan_secret is not None and scan_secret(old) and not scan_secret(content):
            counts["secret_in_bak"] = 1

    tmp = guard.check_write(target + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)

    # audit เก็บแต่ตัวเลข ไม่เคยเก็บเนื้อความของโปรเจกต์ (S02/S04)
    guard.audit("memory_promote", {"project": name, "entries": len(entries),
                                   "kept": len(kept), **counts})
    return "written", summary + (" เขียน MEMORY.md ใหม่" if old is not None
                                 else " สร้าง MEMORY.md"), counts


def job_memory_promote():
    """งานบ้านความจำของทุกโปรเจกต์ คืน (status, message, extra, รายงานเป็นข้อความ)

    "daily dreaming" ในสมุดงานหมายถึงงานบ้าน ไม่ใช่การให้โมเดลแต่งอะไรใหม่
    ที่นี่จึงไม่มีการเรียก LLM และไม่มีการส่งข้อมูลออกนอกเครื่องแม้แต่ไบต์เดียว
    """
    if scan_secret is None:
        msg = "ไม่ทำงาน เพราะ import tools_memory ไม่ได้ (%s) จึงรับประกันการกรองความลับไม่ได้" % _MEM_ERR
        return "error", msg, {}, "งานบ้านความจำ (memory_promote)\n\n" + msg

    now = datetime.now(timezone.utc)
    rows = [("โปรเจกต์", "ผล", "รายละเอียด")]
    tally = {"written": 0, "unchanged": 0, "skipped": 0, "error": 0}
    secrets_dropped = 0
    bak_with_secret = []
    failures = []

    for name, folder in _project_dirs():
        try:
            result, summary, counts = _promote_one(name, folder, now)
        except Denied as exc:
            result, summary, counts = "error", "guard ปฏิเสธ: %s" % _short(exc, 80), {}
        except Exception as exc:                # noqa: BLE001 - โปรเจกต์เดียวพังต้องไม่ล้มทั้งรอบ
            result, summary, counts = "error", "%s: %s" % (type(exc).__name__, _short(exc, 80)), {}
        tally[result] = tally.get(result, 0) + 1
        secrets_dropped += int(counts.get("secret") or 0)
        if counts.get("secret_in_bak"):
            bak_with_secret.append(name)
        if result == "error":
            failures.append(name)
        rows.append((name, {"written": "เขียนใหม่", "unchanged": "เหมือนเดิม",
                            "skipped": "ข้าม", "error": "ผิดพลาด"}[result], summary))

    message = "เขียนใหม่ %d · เหมือนเดิม %d · ข้าม %d · ผิดพลาด %d" % (
        tally["written"], tally["unchanged"], tally["skipped"], tally["error"])
    if secrets_dropped:
        message += " · ตัดรายการที่ดูเหมือนมีความลับออก %d รายการ" % secrets_dropped
    if bak_with_secret:
        message += (" · เตือน: MEMORY.md.bak ของ %s ยังเก็บข้อความที่ดูเหมือนความลับไว้ ควรลบทิ้งเอง"
                    % ", ".join(bak_with_secret))
    status = "error" if failures else "ok"
    extra = {"projects": sum(tally.values()), "secretsDropped": secrets_dropped,
             "written": tally["written"], "unchanged": tally["unchanged"],
             "skipped": tally["skipped"], "failed": failures,
             "bakWithSecret": bak_with_secret}
    body = _table(rows) if len(rows) > 1 else ["(ไม่พบโปรเจกต์ใต้ %s)" % PROJECT_DATA]
    report = "\n".join(["งานบ้านความจำ (memory_promote) — จัดระเบียบอย่างเดียว ไม่เรียก LLM", ""]
                       + body + ["", message])
    return status, message, extra, report


# ------------------------------------------------------------- ตัวจัดการงาน


# ---------------------------------------------- งานที่ 3: gpu_watch (เสียบ/ถอด eGPU)
# ทำไมต้องมี: ตัวเปิด (start-qwen38.ps1) จัดแผน GPU ให้ router ตอนเปิดเท่านั้น เสียบ RTX 4090
# ผ่าน Thunderbolt ทีหลัง router ยังใช้แผน "GPU ในเครื่องอย่างเดียว" จนกว่าจะมีคนกดเปิดใหม่
# งานนี้เทียบ "ลายนิ้วมือชุด GPU ตอนนี้" (nvidia-smi) กับที่ router เริ่มมา (router-8099.state.json)
# ต่างกันติดกัน GPU_WATCH_CONFIRM รอบ → สั่ง hub (POST /api/gpu/apply) ซึ่งรันตัวเปิดแบบ -NonInteractive
# ให้รีสตาร์ตเฉพาะ router ตอนแชตว่าง  hub ไม่อยู่ → รันตัวเปิดเองแบบเดียวกับ hub
# ไม่เรียก LLM ไม่ส่งข้อมูลไปไหน (เหมือน heartbeat) — แค่ GET/POST ในเครื่องกับ nvidia-smi

def _gpu_fingerprint_now():
    """ลายนิ้วมือชุด GPU ตอนนี้ (str) หรือ None ถ้าตรวจไม่ได้ — ใช้ gpu_profile ของตัวเปิดเอง"""
    try:
        import gpu_profile  # อยู่ที่ C:\LLM (sys.path ต่อท้ายไว้แล้วด้านบน)
        fp = gpu_profile.current_fingerprint()
    except Exception:                           # noqa: BLE001 - ไม่มี nvidia-smi / โมดูลพัง = ตรวจไม่ได้
        return None
    return str(fp) if fp else None


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _router_fingerprint():
    doc = _read_json_file(ROUTER_STATE_PATH)
    if not doc:
        return None
    fp = doc.get("fingerprint")
    return str(fp) if fp else None


def _apply_state(now_epoch: float):
    """สถานะงานจัดแผนของ hub: ("running"|"done"|"failed"|"busy"|"stale"|None, อายุเป็นวินาที)"""
    doc = _read_json_file(GPU_APPLY_STATE_PATH) or {}
    st = doc.get("state")
    started = _epoch_or_none(doc.get("started_at")) or _epoch_or_none(doc.get("finished_at"))
    age = (now_epoch - started) if started else None
    if st == "running" and (age is None or age > GPU_APPLY_STALE):
        st = "stale"
    return st, age


def gpu_watch_decide(fp_now, fp_router, pending, apply_state, now_epoch: float):
    """ตัดสินใจอย่างเดียว (ไม่แตะไฟล์/เครือข่าย) → (action, pending_ใหม่, ข้อความ)

    action: "same"      ชุด GPU ตรงกับแผนของ router
            "unknown"   ตรวจ GPU ไม่ได้ / router ไม่มี state (ไม่ทำอะไร)
            "confirm"   เห็นชุดใหม่แต่ยังไม่ครบรอบยืนยัน
            "busy"      hub กำลังจัดแผนอยู่ รอ
            "cooldown"  เพิ่งสั่งชุดนี้ไปไม่นาน รอ
            "apply"     สั่งจัดแผนใหม่
    pending = {"fp": ชุดใหม่ที่เห็น, "seen": กี่รอบติดกัน, "applied_fp": ชุดที่สั่งล่าสุด, "applied_at": epoch}
    """
    pending = dict(pending or {})
    if not fp_now or not fp_router:
        return "unknown", pending, "ตรวจ GPU ไม่ได้ หรือ router ยังไม่มี state"
    if fp_now == fp_router:
        pending.pop("fp", None)
        pending.pop("seen", None)
        return "same", pending, "ชุด GPU ตรงกับแผนของ router"
    seen = int(pending.get("seen") or 0) + 1 if pending.get("fp") == fp_now else 1
    pending.update(fp=fp_now, seen=seen)
    if seen < GPU_WATCH_CONFIRM:
        return "confirm", pending, "ชุด GPU เปลี่ยน (รอยืนยัน %d/%d)" % (seen, GPU_WATCH_CONFIRM)
    if apply_state == "running":
        return "busy", pending, "hub กำลังจัดแผน GPU อยู่"
    applied_at = _epoch_or_none(pending.get("applied_at"))
    if pending.get("applied_fp") == fp_now and applied_at and 0 <= now_epoch - applied_at < GPU_WATCH_COOLDOWN:
        return "cooldown", pending, "เพิ่งสั่งจัดแผนชุดนี้ไป %d วินาทีที่แล้ว" % int(now_epoch - applied_at)
    pending.update(applied_fp=fp_now, applied_at=now_epoch)
    return "apply", pending, "ชุด GPU เปลี่ยน → สั่งจัดแผนใหม่"


def _hub_apply() -> str:
    """POST /api/gpu/apply ของ hub → "started" | "busy" | "error: ..." (ไม่มี Origin = โปรแกรมในเครื่อง)"""
    req = urllib.request.Request(HUB_APPLY_URL, data=b"", method="POST",
                                 headers={"Content-Length": "0", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return "started" if r.status == 200 else "error: http %s" % r.status
    except urllib.error.HTTPError as e:
        return "busy" if e.code == 409 else "error: http %s" % e.code
    except (urllib.error.URLError, OSError, ValueError) as e:
        return "error: %s" % _short(e, 120)


def _launcher_apply() -> str:
    """ทางสำรองเมื่อ hub ไม่ตอบ: รันตัวเปิดแบบเดียวกับ hub (ไม่รอผล ตัวเปิดมีล็อกของมันเอง)"""
    ps = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "WindowsPowerShell", "v1.0",
                      "powershell.exe")
    argv = [ps if os.path.isfile(ps) else "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", GPU_LAUNCHER, "-NoBrowser", "-NonInteractive", "-Port", "8099"]
    log_path = r"C:\LLM\logs\gpu-apply.log"
    try:
        with open(log_path, "ab") as fh:
            fh.write(("#scheduler %s start-qwen38.ps1 -NonInteractive (hub ไม่ตอบ)\n" % _utc_now()).encode("utf-8"))
            fh.flush()
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                             cwd=r"C:\LLM", creationflags=0x08000000)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return "error: %s" % _short(e, 120)
    return "launcher"


def job_gpu_watch():
    now_epoch = time.time()
    state = _load_state()
    rec = state.get("jobs", {}).get("gpu_watch") or {}
    pending = rec.get("pending") if isinstance(rec.get("pending"), dict) else {}
    fp_now = _gpu_fingerprint_now()
    fp_router = _router_fingerprint()
    apply_st, _age = _apply_state(now_epoch)
    action, pending, why = gpu_watch_decide(fp_now, fp_router, pending, apply_st, now_epoch)
    extra = {"pending": pending, "fpNow": fp_now, "fpRouter": fp_router, "action": action, "applyState": apply_st}
    message = why
    status = "ok"
    if action == "apply":
        res = _hub_apply()
        if res.startswith("error"):
            res2 = _launcher_apply()
            message = "%s — hub %s → %s" % (why, res, res2)
            if res2.startswith("error"):
                status = "error"
        elif res == "busy":
            message = "%s — hub กำลังทำอยู่แล้ว" % why
        else:
            message = "%s — สั่ง hub แล้ว" % why
        extra["applyResult"] = message
    lines = ["เฝ้า eGPU (gpu_watch)", "", "GPU ตอนนี้ : %s" % (fp_now or "-"), "แผน router : %s" % (fp_router or "-"),
             "ผล        : %s" % message]
    return status, message, extra, "\n".join(lines)


def _gpu_watch_due(state: dict, now_epoch: float) -> bool:
    last = _last_epoch(state, "gpu_watch")
    if last is None or last > now_epoch:
        return True
    return (now_epoch - last) >= GPU_WATCH_EVERY


JOBS = {
    "heartbeat": {"th": "ตรวจสุขภาพสแตก", "when": "ทุก 30 นาที", "fn": job_heartbeat},
    "memory_promote": {"th": "งานบ้านความจำ",
                       "when": "ทุกวัน %02d:%02d" % (PROMOTE_HOUR, PROMOTE_MINUTE),
                       "fn": job_memory_promote},
    "gpu_watch": {"th": "เฝ้า eGPU (เสียบ/ถอด RTX 4090 แล้วจัดแผน GPU ใหม่ให้)", "when": "ทุก 1 นาที",
                  "fn": job_gpu_watch},
}


def run_job(job: str) -> str:
    """รันงานหนึ่งรอบแล้วบันทึกสถานะ คืนรายงานเป็นข้อความ (ไม่โยน exception)"""
    spec = JOBS.get(job)
    if spec is None:
        return "ERROR: ไม่รู้จักงาน %r (มี: %s)" % (job, ", ".join(JOB_NAMES))
    t0 = time.monotonic()
    try:
        status, message, extra, report = spec["fn"]()
    except Exception as exc:                    # noqa: BLE001 - งานพังก็ยังต้องบันทึกว่าพัง
        status = "error"
        message = "%s: %s" % (type(exc).__name__, _short(exc, 200))
        extra, report = {}, "งาน %s ล้มเหลว: %s" % (job, message)
    extra = dict(extra or {})
    extra["durationMs"] = int((time.monotonic() - t0) * 1000)
    try:
        rec = _record(job, status, message, extra)
        tail = "\n\nสถานะ %s · ok ติดต่อกัน %d รอบ · ใช้เวลา %dms" % (
            status, rec.get("consecutiveOk", 0), extra["durationMs"])
    except (Denied, OSError, ValueError) as exc:
        tail = "\n\n(บันทึกสถานะลง %s ไม่ได้: %s)" % (STATE_PATH, _short(exc, 80))
    return report + tail


# ------------------------------------------------- ตัวรัน (เฉพาะตอน __main__)

def _image_of_pid(pid: int) -> str:
    """ชื่ออิมเมจของ pid หรือ "" ถ้าไม่มีโปรเซสนั้นแล้ว

    ทำไมไม่ใช้ os.kill(pid, 0) แบบยูนิกซ์: บนวินโดวส์ os.kill เรียก TerminateProcess
    สัญญาณ 0 จึง "ฆ่าจริง" ไม่ใช่การถามเฉยๆ ห้ามใช้เด็ดขาด
    และ tasklist ถ้าใส่ /FI หลายตัวมันจะ AND กันจนไม่แมตช์อะไรเลย จึงใส่ตัวเดียวแล้วกรองต่อใน Python
    """
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "PID eq %d" % int(pid), "/FO", "CSV", "/NH"],
            capture_output=True, timeout=10, check=False)
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    text = out.stdout.decode("utf-8", "replace")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith('"'):
            continue
        cells = [c.strip('"') for c in line.split('","')]
        if len(cells) >= 2 and cells[1].strip().isdigit() and int(cells[1]) == int(pid):
            return cells[0]
    return ""


def runner_info(state: dict | None = None) -> tuple[bool, dict]:
    """ตัวตั้งเวลายังรันอยู่ไหม — ดูจาก pid ที่จดไว้ใน state แล้วเช็กกับ tasklist

    เช็กชื่ออิมเมจด้วย เพราะวินโดวส์เอา pid ไปใช้ซ้ำได้ ถ้าไม่เช็กแล้วบังเอิญมีโปรเซสอื่น
    ได้ pid เดิมไป เราจะรายงานผิดว่าตัวตั้งเวลายังอยู่
    """
    state = state if state is not None else _load_state()
    runner = state.get("runner") or {}
    try:
        pid = int(runner.get("pid") or 0)
    except (TypeError, ValueError):
        return False, {}
    if pid <= 0:
        return False, runner
    image = _image_of_pid(pid)
    alive = bool(image) and image.lower().startswith("python")
    return alive, dict(runner, image=image)


def _claim_runner() -> bool:
    """จองสิทธิ์เป็นตัวตั้งเวลาตัวเดียวของเครื่อง คืน False ถ้ามีตัวอื่นรันอยู่แล้ว"""
    with _LOCK:
        state = _load_state()
        alive, info = runner_info(state)
        if alive and int(info.get("pid") or 0) != os.getpid():
            _say("มีตัวตั้งเวลารันอยู่แล้ว (pid %s เริ่มเมื่อ %s) จึงไม่เริ่มซ้ำ"
                 % (info.get("pid"), info.get("started", "?")))
            return False
        state["runner"] = {"pid": os.getpid(), "started": _utc_now(), "host": "127.0.0.1"}
        _save_state(state)
    return True


def _release_runner() -> None:
    with _LOCK:
        state = _load_state()
        if int((state.get("runner") or {}).get("pid") or 0) == os.getpid():
            state["runner"] = {}
            _save_state(state)


def _heartbeat_due(state: dict, now_epoch: float) -> bool:
    """ถึงรอบ heartbeat หรือยัง

    เงื่อนไข last > now_epoch มีไว้กันเคส "เวลาล่าสุดอยู่ในอนาคต" (นาฬิกาเครื่องถูกปรับถอยหลัง
    หรือ state ถูกคัดลอกมาจากเครื่องอื่น) ถ้าไม่ดัก ส่วนต่างจะติดลบตลอดไป
    แล้ว heartbeat จะไม่ทำงานอีกเลยโดยไม่มีใครรู้
    """
    last = _last_epoch(state, "heartbeat")
    if last is None or last > now_epoch:
        return True
    return (now_epoch - last) >= HEARTBEAT_EVERY


def _promote_due(state: dict, now: datetime, startup: bool) -> bool:
    """ถึงเวลาทำงานบ้านหรือยัง — อย่างมากวันละครั้ง

    เงื่อนไขเรียงตามลำดับ
      1. ไม่เคยรันเลย                       -> รันทันที
      2. รันไปแล้ววันนี้ (วันที่ท้องถิ่นเดียวกัน) -> ไม่รันอีก เด็ดขาด
      3. เลย 03:00 ของวันนี้แล้ว              -> รัน (ครอบกรณีเครื่องดับตอนตีสามด้วย)
      4. ตอนเพิ่งสตาร์ต ถ้าห่างจากรอบล่าสุดเกิน 24 ชม -> ตามเก็บหนึ่งรอบ
    """
    last = _last_epoch(state, "memory_promote")
    if last is None:
        return True
    if datetime.fromtimestamp(last).date() == now.date():
        return False
    scheduled = now.replace(hour=PROMOTE_HOUR, minute=PROMOTE_MINUTE, second=0, microsecond=0)
    if now >= scheduled:
        return True
    return startup and (now.timestamp() - last) >= CATCHUP_AFTER


def run_forever(stop: threading.Event | None = None) -> int:
    """วงรอบหลักของตัวตั้งเวลา — เรียกจาก __main__ เท่านั้น

    งานถูกรันเรียงกันในเธรดนี้เธรดเดียว ไม่แตกเธรดใหม่ต่องาน เพราะงานทั้งสองสั้น
    (heartbeat แย่สุด 4 × 5 วินาที) การรันเรียงกันจึงง่ายกว่าและไม่ต้องกังวลเรื่อง race
    """
    stop = stop or threading.Event()
    if not _claim_runner():
        return 1
    guard.audit("scheduler_start", {"pid": os.getpid(), "jobs": list(JOB_NAMES)})
    _say("ตัวตั้งเวลา qwenlocal เริ่มแล้ว (pid %d)" % os.getpid())
    for name in JOB_NAMES:
        _say("  %-15s %s" % (name, JOBS[name]["when"]))
    _say("  สถานะเก็บที่ %s  (Ctrl+C เพื่อหยุด)" % STATE_PATH)

    startup = True
    try:
        while not stop.is_set():
            now = datetime.now()
            # ห้ามให้อะไรในบล็อกนี้ล้มวงรอบทั้งตัว ตัวตั้งเวลาที่ตายเงียบๆ แย่กว่ารอบที่ข้ามไปหนึ่งรอบ
            try:
                state = _load_state()
                due = []
                if _heartbeat_due(state, now.timestamp()):
                    due.append("heartbeat")
                if _promote_due(state, now, startup):
                    due.append("memory_promote")
                if _gpu_watch_due(state, now.timestamp()):
                    due.append("gpu_watch")
            except Exception as exc:            # noqa: BLE001
                _say("[%s] อ่านสถานะไม่ได้ ข้ามรอบนี้: %s: %s"
                     % (now.strftime("%H:%M:%S"), type(exc).__name__, _short(exc, 120)))
                due = []
            startup = False
            for job in due:
                _say("[%s] เริ่มงาน %s" % (now.strftime("%H:%M:%S"), job))
                report = run_job(job)
                _say(report)
                _say("")
                if stop.is_set():
                    break
            stop.wait(TICK)
    except KeyboardInterrupt:
        _say("หยุดตามคำสั่งผู้ใช้")
    finally:
        _release_runner()
        guard.audit("scheduler_stop", {"pid": os.getpid()})
    return 0


# ------------------------------------------------------------ เครื่องมือ MCP

@_safe
def schedule_status() -> str:
    """ตารางสถานะของงานตามเวลา — ใช้ตอบคำถาม "ระบบยังปกติไหม" ได้ทันที"""
    state = _load_state()
    alive, info = runner_info(state)
    lines = ["ตัวตั้งเวลา qwenlocal", ""]
    if alive:
        lines.append("ตัวรัน: กำลังทำงาน pid %s (เริ่ม %s)" % (info.get("pid"), info.get("started", "?")))
    else:
        lines.append("ตัวรัน: ไม่ได้รันอยู่ — งานตามเวลาจะไม่ทำงานเอง "
                     "(สั่งเองได้ด้วย schedule_run หรือรัน python scheduler.py)")
    lines.append("")

    now = time.time()
    rows = [("งาน", "กำหนด", "รันล่าสุด", "สถานะ", "ok ติดต่อกัน", "ข้อความ")]
    for job in JOB_NAMES:
        rec = state.get("jobs", {}).get(job) or {}
        epoch = _epoch_or_none(rec.get("lastRunEpoch"))
        when = _fmt_when(epoch)
        if epoch:
            when += " (%sที่แล้ว)" % _fmt_elapsed(now - epoch)
        rows.append((job, JOBS[job]["when"], when,
                     rec.get("lastRunStatus", "-"),
                     str(rec.get("consecutiveOk", 0)),
                     rec.get("message", "-")))
    lines += _table(rows, right=(4,))

    checks = (state.get("jobs", {}).get("heartbeat") or {}).get("checks")
    if isinstance(checks, dict) and checks:
        lines += ["", "ผลตรวจรายบริการของ heartbeat รอบล่าสุด", ""]
        crows = [("บริการ", "สถานะ", "เวลา", "รายละเอียด")]
        for key, _label, _url, _v in CHECKS:
            item = checks.get(key) or {}
            crows.append((item.get("label", key),
                          "ok" if item.get("status") == "ok" else "ล้ม",
                          "%sms" % item.get("ms", "?"),
                          item.get("detail", "-")))
        lines += _table(crows, right=(2,))

    guard.audit("schedule_status", {"runner_alive": alive})
    return "\n".join(lines)


@_safe
def schedule_run(job: str = "", confirm_token: str = "") -> str:
    """สั่งงานตามเวลาให้ทำงานทันที — สองขั้นตอนตามกฎ S03"""
    job_v = str(job or "").strip().lower()
    if job_v not in JOBS:
        return ("ERROR: ไม่รู้จักงาน %r — ใช้ได้เฉพาะ %s" % (str(job), ", ".join(JOB_NAMES)))

    if job_v == "heartbeat":
        detail = ("รัน heartbeat หนึ่งรอบทันที: ยิง GET ไปที่ %d บริการในเครื่อง "
                  "(timeout 5 วินาที ไม่ส่ง prompt ให้โมเดล) แล้วบันทึกผลลง %s"
                  % (len(CHECKS), STATE_PATH))
    elif job_v == "gpu_watch":
        detail = ("รัน gpu_watch หนึ่งรอบทันที: เทียบชุด GPU ตอนนี้ (nvidia-smi) กับแผนของ router "
                  "ต่างกันจึงสั่ง hub จัดแผนใหม่ (ไม่ส่ง prompt ให้โมเดล)")
    else:
        try:
            count = len(_project_dirs())
        except Denied:
            count = 0
        detail = ("รันงานบ้านความจำทันที: เขียน MEMORY.md ของโปรเจกต์ที่มีความจำใหม่ทั้งไฟล์ "
                  "(สำรองเป็น MEMORY.md.bak ก่อน, ไม่แตะ memory.json, ไม่เรียก LLM) "
                  "ตอนนี้มี %d โปรเจกต์ในทะเบียน" % count)

    # ผูก action เข้ากับชื่องาน token ที่ขอไว้สำหรับ heartbeat จึงเอาไปสั่งงานบ้านไม่ได้
    action = "schedule_run:%s" % job_v
    ok = False
    token_in = str(confirm_token or "").strip()
    if token_in:
        try:
            ok = bool(guard.consume_confirm(token_in, action, detail))
        except Exception:                       # noqa: BLE001
            ok = False
    if not ok:
        token = guard.need_confirm(action, detail)
        head = "จะสั่งงาน %s (%s) ให้ทำงานทันที แต่ยังไม่ได้ทำ\n  %s\n\n" % (
            job_v, JOBS[job_v]["th"], detail)
        if token_in:
            head = "(confirm_token ใช้ไม่ได้หรือหมดอายุแล้ว จึงยังไม่ทำ ขอ token ใหม่)\n\n" + head
        return head + guard.confirm_hint(token, action, detail)

    guard.audit("schedule_run", {"job": job_v, "forced": True})
    return run_job(job_v)


TOOLS = [
    {"name": "schedule_status",
     "description": ("ดูสถานะงานตามเวลาของสแตกนี้: heartbeat ทุก 30 นาที และงานบ้านความจำรายวัน "
                     "บอกว่ารันล่าสุดเมื่อไร ผลเป็นอย่างไร ok ติดต่อกันกี่รอบ และบริการไหนล้ม "
                     "ใช้ตอบคำถามทำนอง \"ระบบยังปกติไหม\" ได้ทันที"),
     "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "schedule_run",
     "description": ("สั่งงานตามเวลาให้ทำงานเดี๋ยวนี้โดยไม่ต้องรอรอบถัดไป "
                     "เป็นการกระทำสองขั้นตอน: เรียกครั้งแรกเพื่อดูว่าจะเกิดอะไรขึ้นและรับ confirm_token "
                     "แล้วถามผู้ใช้ก่อน ผู้ใช้อนุมัติแล้วจึงเรียก local_confirm(confirm_token)"),
     "inputSchema": {"type": "object",
                     "properties": {
                         "job": {"type": "string", "enum": list(JOB_NAMES),
                                 "description": ("heartbeat = ตรวจสุขภาพสแตกหนึ่งรอบ, "
                                                 "memory_promote = จัดระเบียบ MEMORY.md ของทุกโปรเจกต์, "
                                                 "gpu_watch = ตรวจว่าเสียบ/ถอด eGPU แล้วจัดแผน GPU ใหม่")},
                         "confirm_token": {"type": "string",
                                           "description": "token ที่ได้จากการเรียกครั้งแรก ใส่เมื่อผู้ใช้อนุมัติแล้ว"}},
                     "required": ["job"]}},
]

IMPL = {
    "schedule_status": schedule_status,
    "schedule_run": schedule_run,
}


if __name__ == "__main__":
    # import โมดูลนี้จะไม่ทำอะไรทั้งสิ้น ทุกอย่างเริ่มที่นี่เท่านั้น
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if arg in ("", "run", "serve"):
        sys.exit(run_forever())
    if arg == "status":
        _say(schedule_status())
    elif arg in ("heartbeat", "hb"):
        _say(run_job("heartbeat"))
    elif arg in ("promote", "memory_promote", "dream"):
        _say(run_job("memory_promote"))
    else:
        _say("ใช้: python scheduler.py [run|status|heartbeat|promote]")
        sys.exit(2)
