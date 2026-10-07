# -*- coding: utf-8 -*-
"""tools_tasks.py -- เครื่องมือเฝ้าดูงานเบื้องหลัง (background task monitor) ของ MCP "Local Computer"

สิ่งที่โมดูลนี้ให้:
  task_start(command, cwd, confirm_token)  เริ่มโปรเซสเบื้องหลัง (ยืนยันสองขั้นตอน)
  task_list()                              ตารางงานทั้งหมดพร้อมสถานะล่าสุด
  task_get(id, tail)                       รายละเอียดงาน + ท้าย log N บรรทัด
  task_stop(id, confirm_token)             สั่งหยุดงาน (ยืนยันสองขั้นตอน)

หลักการที่ยึดไว้
----------------
1. ไม่มี shell=True เด็ดขาด คำสั่งถูกแตกเป็น argv แบบกฎของ Windows (CommandLineToArgvW)
   แล้วส่งเข้า subprocess.Popen เป็น list ดังนั้นตัวดำเนินการของ shell เช่น | > & && ||
   จะไม่ทำงาน ถ้าผู้ใช้ต้องการจริงต้องเขียน cmd /c "..." ให้ชัดเจนด้วยตัวเอง

2. หยุดได้เฉพาะงานที่ registry นี้เป็นคนเริ่ม (กฎสำคัญที่สุดของไฟล์นี้)
   task_stop รับเฉพาะ task id ไม่เคยรับ pid ตรงๆ และก่อนฆ่าจะเทียบชื่ออิมเมจของ pid
   กับชื่อที่บันทึกไว้ตอนเริ่มเสมอ กัน Windows เอา pid เดิมไปใช้ซ้ำแล้วเราฆ่าผิดตัว

3. log มีเพดาน 2 MB ต่อหนึ่งงาน โดยพ่อแม่ถือปลายอ่านของ pipe ไว้เองแล้วมีเธรดคอย
   ระบายข้อมูลทิ้งหลังชนเพดาน (อ่านต่อแต่ไม่เขียนเพิ่ม) ลูกจึงไม่ค้างเพราะ pipe เต็ม
   *เหตุผลที่ไม่ใช้วิธี truncate ไฟล์:* ทดสอบบนเครื่องนี้แล้วพบว่าถ้าให้ลูกเขียนลงไฟล์ตรงๆ
   แล้วพ่อแม่ตัดไฟล์ทิ้ง ตัวชี้ตำแหน่งของลูกไม่ถอยตาม ไฟล์จะโตต่อโดยมีช่อง NUL คั่น
   (ทดสอบ: ตัดที่ 1100 ไบต์ ไฟล์จบที่ 4400 ไบต์ เป็น NUL 1100 ไบต์) คือคุมขนาดไม่ได้จริง
   ฝั่งอ่านจึงยังกรอง NUL ทิ้งเผื่อไฟล์เก่าที่เคยโดนวิธีนั้น

4. สถานะถูกคำนวณใหม่ทุกครั้งที่อ่าน ไม่เชื่อค่าที่ค้างใน tasks.json
   งานที่เริ่มโดยเซิร์ฟเวอร์รอบก่อน (หลัง restart) ยังดูสถานะและสั่งหยุดได้ผ่าน tasklist

ทุกฟังก์ชันสาธารณะคืน str เสมอ ข้อผิดพลาดคืนเป็นข้อความขึ้นต้น "ERROR: " ไม่โยน exception
"""
from __future__ import annotations

import csv
import functools
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# guard.py อยู่โฟลเดอร์เดียวกับไฟล์นี้ กันกรณีเซิร์ฟเวอร์ถูกรันจาก cwd อื่น
_HERE_DIR = os.path.dirname(os.path.abspath(__file__))
if _HERE_DIR not in sys.path:
    sys.path.insert(0, _HERE_DIR)

import guard  # noqa: E402
from guard import Denied  # noqa: E402

HERE = Path(_HERE_DIR)
TASKS_PATH = HERE / "tasks.json"
LOG_DIR = HERE / "tasklogs"

LOG_MAX = 2 * 1024 * 1024          # เพดาน log ต่อหนึ่งงาน
TAIL_READ_BYTES = 256 * 1024       # อ่านท้ายไฟล์แค่ช่วงนี้พอ ไม่โหลดทั้งก้อน
MAX_TASKS_KEPT = 200               # เก็บประวัติงานที่จบแล้วเท่านี้
CREATE_NO_WINDOW = 0x08000000      # ไม่ให้เด้งหน้าต่าง console ใส่หน้าผู้ใช้
DEFAULT_PROJECT = "tasks"          # โฟลเดอร์ทำงานเริ่มต้นเมื่อไม่ระบุ cwd

_ACTIVE = {"running"}

# โปรเซสที่ "เซิร์ฟเวอร์รอบนี้" เป็นคนเริ่ม: id -> Popen  (หลัง restart จะว่าง)
_PROCS: dict[str, subprocess.Popen] = {}
_LOCK = threading.RLock()          # ครอบการอ่าน-เขียน tasks.json ทั้งหมด

_CAP_NOTE = ("\n[log ชนเพดาน %d ไบต์ หยุดบันทึกเพิ่มแล้ว "
             "แต่ยังระบายผลลัพธ์ของโปรเซสต่อไปเพื่อไม่ให้โปรเซสค้าง]\n" % LOG_MAX)

# คำสั่งที่เป็น builtin ของ cmd.exe ล้วนๆ ไม่มีไฟล์ .exe ให้เรียก
_SHELL_BUILTINS = {
    "dir", "echo", "cd", "chdir", "copy", "del", "erase", "type", "set", "cls",
    "move", "ren", "rename", "md", "mkdir", "rd", "rmdir", "pushd", "popd",
    "if", "for", "goto", "call", "exit", "ver", "vol", "title", "path", "assoc",
}


# ------------------------------------------------------------------ utilities
def _now() -> float:
    return time.time()


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe(fn):
    """ครอบทุกเครื่องมือ: ไม่ว่าเกิดอะไรขึ้นก็คืนเป็นสตริง ไม่โยนออกไปหาเซิร์ฟเวอร์"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Denied as exc:
            return "ERROR: ถูกปฏิเสธโดยนโยบายความปลอดภัย: %s" % exc
        except TypeError as exc:
            return "ERROR: อาร์กิวเมนต์ไม่ถูกต้องสำหรับ %s: %s" % (fn.__name__, exc)
        except Exception as exc:                      # noqa: BLE001 - กันทุกกรณี
            return "ERROR: %s ล้มเหลว: %s: %s" % (fn.__name__, type(exc).__name__, exc)
    return wrapper


def _as_int(value, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _dwidth(text: str) -> int:
    """ความกว้างที่ตาเห็น: สระบนล่างและวรรณยุกต์ไทยไม่กินเนื้อที่ในคอลัมน์"""
    return sum(0 if unicodedata.combining(ch) else 1 for ch in text)


def _pad(text: str, width: int, right: bool = False) -> str:
    fill = " " * max(0, width - _dwidth(text))
    return (fill + text) if right else (text + fill)


def _fmt_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "%dวิ" % seconds
    if seconds < 3600:
        return "%dน %dวิ" % (seconds // 60, seconds % 60)
    if seconds < 86400:
        return "%dชม %dน" % (seconds // 3600, (seconds % 3600) // 60)
    return "%dวัน %dชม" % (seconds // 86400, (seconds % 86400) // 3600)


def _started_epoch(task: dict) -> float:
    """เวลาเริ่มเป็น epoch ใช้ค่า mono ที่บันทึกไว้ก่อน ถ้าไม่มีค่อยแปลงจาก ISO"""
    val = task.get("started_epoch")
    if isinstance(val, (int, float)) and val > 0:
        return float(val)
    try:
        return datetime.fromisoformat(task["started_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return _now()


def _elapsed_text(task: dict) -> str:
    end = task.get("ended_epoch")
    if not isinstance(end, (int, float)) or end <= 0:
        end = _now()
    return _fmt_elapsed(end - _started_epoch(task))


# --------------------------------------------------------- command -> argv
def _split_command(command: str) -> list[str]:
    """แตกสตริงคำสั่งตามกฎของ Windows (CommandLineToArgvW)

    backslash เป็นตัว escape เฉพาะเมื่ออยู่หน้าเครื่องหมายคำพูดเท่านั้น
    path อย่าง C:\\Users\\demo\\งาน ไทย.py จึงไม่ถูกกลืน (ต่างจาก shlex แบบ posix)
    """
    argv: list[str] = []
    buf: list[str] = []
    in_quotes = False
    pending_bs = 0
    has_token = False

    def flush_backslashes(count: int) -> None:
        buf.extend("\\" * count)

    for ch in command:
        if ch == "\\":
            pending_bs += 1
            continue
        if ch == '"':
            flush_backslashes(pending_bs // 2)
            if pending_bs % 2:
                buf.append('"')          # \" คือเครื่องหมายคำพูดตัวจริง
            else:
                in_quotes = not in_quotes
            pending_bs = 0
            has_token = True
            continue
        flush_backslashes(pending_bs)
        pending_bs = 0
        if ch in " \t\r\n" and not in_quotes:
            if buf or has_token:
                argv.append("".join(buf))
                buf = []
                has_token = False
            continue
        buf.append(ch)
        has_token = True

    flush_backslashes(pending_bs)
    if buf or has_token:
        argv.append("".join(buf))
    return argv


# backslash ที่ไม่ได้ตามด้วยตัว escape ที่ JSON รู้จัก ถือว่าเป็น backslash ของ path
_LONE_BACKSLASH_RE = re.compile(r'\\(?![\\"/bfnrtu])')


def _parse_command(command: str) -> list[str]:
    """รับได้ทั้งสตริงคำสั่ง และ JSON array เช่น ["python","-u","ไฟล์ ของฉัน.py"]

    แบบ JSON array แม่นยำที่สุดเมื่อ path มีทั้งช่องว่างและ backslash
    """
    text = str(command or "").strip()
    if not text:
        raise ValueError("command ว่าง")
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except ValueError:
            # โมเดลมักเขียน ["C:\Python313\python.exe", ...] ด้วย backslash เดี่ยว
            # ซึ่ง JSON ไม่ยอม ให้โอกาสอีกครั้งโดยเติม backslash ให้อัตโนมัติ
            patched = _LONE_BACKSLASH_RE.sub(r"\\\\", text)
            try:
                parsed = json.loads(patched)
            except ValueError as exc:
                raise ValueError(
                    "command ขึ้นต้นด้วย [ แต่ไม่ใช่ JSON array ที่ถูกต้อง: %s "
                    "(ถ้า path มี backslash ต้องเขียนซ้ำสองตัว เช่น C:\\\\Python313\\\\python.exe)"
                    % exc)
        if not isinstance(parsed, list) or not parsed:
            raise ValueError("JSON array ของ command ต้องไม่ว่าง")
        return [str(x) for x in parsed]
    argv = _split_command(text)
    if not argv:
        raise ValueError("แตกคำสั่งออกมาไม่ได้เลย")
    return argv


def _resolve_exe(argv: list[str], cwd: str) -> tuple[list[str], str]:
    """หาไฟล์จริงของ argv[0] คืน (argv ที่แก้แล้ว, คำเตือน) หรือโยน ValueError"""
    exe = argv[0]
    found = shutil.which(exe)
    if not found and not os.path.isabs(exe):
        # ลองหาในโฟลเดอร์ทำงานด้วย เช่น .\run.bat
        cand = os.path.join(cwd, exe)
        if os.path.isfile(cand):
            found = cand
    if not found and os.path.isfile(exe):
        found = exe
    if not found:
        base = os.path.basename(exe).lower()
        base = base[:-4] if base.endswith(".exe") else base
        if base in _SHELL_BUILTINS:
            raise ValueError(
                "\"%s\" เป็นคำสั่งภายในของ cmd.exe ไม่ใช่โปรแกรม และโมดูลนี้ไม่ใช้ shell "
                "เพื่อความปลอดภัย ถ้าต้องการจริงให้เขียนเต็มว่า: cmd /c \"%s ...\"" % (exe, exe))
        raise ValueError(
            "หาโปรแกรม \"%s\" ไม่เจอทั้งใน PATH และในโฟลเดอร์ทำงาน "
            "ให้ระบุ path เต็ม เช่น C:\\Python313\\python.exe" % exe)
    warn = ""
    low = found.lower()
    asked = os.path.basename(exe).lower()
    asked = asked[:-4] if asked.endswith(".exe") else asked
    if asked in _SHELL_BUILTINS:
        # บนเครื่องนี้ Git for Windows วาง dir/echo/mkdir/rmdir แบบ POSIX ไว้ใน PATH
        # ซึ่งพฤติกรรมไม่เหมือน builtin ของ cmd เลย (dir.EXE ทำงานเหมือน ls)
        warn = ("คำเตือน: \"%s\" ถูกจับคู่กับโปรแกรม %s ซึ่งเป็นเครื่องมือแบบ POSIX "
                "ไม่ใช่คำสั่งภายในของ cmd.exe พฤติกรรมและอาร์กิวเมนต์จะต่างออกไป "
                "ถ้าต้องการคำสั่งของ cmd จริงๆ ให้เขียนว่า cmd /c \"%s ...\""
                % (exe, found, asked))
    elif low.endswith((".bat", ".cmd")):
        warn = ("หมายเหตุ: %s เป็นสคริปต์ batch ซึ่ง Windows จะรันผ่าน cmd.exe ให้เอง "
                "เนื้อหาในไฟล์จึงทำงานได้เต็มรูปแบบ" % os.path.basename(found))
    return [found] + list(argv[1:]), warn


def _guard_argv(argv: list[str], raw: str, work_dir: str) -> None:
    """ตรวจ argv ของงานเบื้องหลังด้วยนโยบายเดียวกับคำสั่ง shell ที่ต้องยืนยัน

    ใช้ตัวช่วยของ tools_files (นโยบายอยู่ที่เดียว) import ตอนเรียกเพื่อไม่ผูกลำดับการโหลดโมดูล
    โยน Denied ออกไป ให้ _safe แปลงเป็นข้อความ "ถูกปฏิเสธ"
    """
    import tools_files                      # noqa: WPS433 — ตั้งใจ import ตอนใช้
    text = " ".join(argv) + "\n" + raw
    reason = guard.command_text_violation(text, readonly=False)
    if reason:
        guard.audit("task_start_denied", {"reason": reason,
                                          "command": guard.scrub_text(raw)[:300]})
        if reason == "secret_path":
            raise Denied("คำสั่งนี้อ้างถึงโฟลเดอร์ความลับของระบบ (secrets/token) จึงรันไม่ได้ไม่ว่ากรณีใด")
        raise Denied("งานเบื้องหลังห้ามแตะโค้ด/ค่าตั้งของระบบหรือจุดที่ทำให้โปรแกรมรันเองอัตโนมัติ "
                     "ถ้าจำเป็นจริงให้ผู้ใช้รันเองใน terminal")
    guard.check_workdir_for_exec(work_dir, readonly=False)
    for arg in argv:
        cand = tools_files._path_of(arg, work_dir)
        if cand is None:
            continue
        if any(c in cand for c in "*?"):
            guard.check_glob(cand)
            continue
        guard.check_read(cand)
        if guard.is_write_protected(cand):
            raise Denied("งานเบื้องหลังห้ามอ้างถึง path ในเขตห้ามเขียน (%s) "
                         "ถ้าจำเป็นจริงให้ผู้ใช้รันเองใน terminal" % cand)


def _visible(task: dict) -> bool:
    """งานของโปรเจกต์อื่นมองไม่เห็น (S04)

    งานรุ่นเก่าที่ไม่มีฟิลด์ project เดิมเห็นได้ "ทุกโปรเจกต์" (ช่องโหว่ที่ audit พบ)
    ตอนนี้ถือว่าเป็นของโปรเจกต์ "default" — เห็นได้เฉพาะจากผิว default เท่านั้น
    mine เป็น None เฉพาะตอนเรียกนอกขอบเขต (เช่น heartbeat จาก CLI) ให้เห็นทั้งหมดได้
    """
    mine = guard.current_project()
    owner = task.get("project") or "default"
    return mine is None or owner == mine


def _argv_item(a: str) -> str:
    """argv หนึ่งชิ้นเป็นสตริง JSON บรรทัดเดียว (รอบ FIXER)

    เดิมพิมพ์ดิบ ชิ้นที่มี \\n จึงแตกเป็นหลายบรรทัด และบรรทัดต่อปลอมเป็นชิ้นใหม่ได้ เช่น
    -c "print(1)\\n  [9] --harmless-looking" ดูเหมือนมีอาร์กิวเมนต์ [9] ทั้งที่เป็นส่วนของ [2]
    JSON ใส่เครื่องหมายคำพูดครอบ (ขอบของแต่ละชิ้นชัด ช่องว่างในชิ้นเห็นได้) และแสดง \\n \\t \\" \\\\ เป็นตัวอักษร
    ใช้ทุกชิ้นเสมอ (ไม่ใช่เฉพาะชิ้นที่มี \\n) ไม่งั้นข้อความที่ "หน้าตาเป็น JSON อยู่แล้ว" จะแยกไม่ออกจากชิ้นที่ถูกแปลง"""
    return json.dumps(str(a), ensure_ascii=False)


def _argv_text(argv: list[str]) -> str:
    """แสดง argv ให้ผู้ใช้เห็นว่าจะรันอะไรจริงๆ ทีละชิ้น (หนึ่งชิ้นต่อบรรทัดเสมอ)"""
    out = []
    for i, a in enumerate(argv):
        out.append("    [%d] %s" % (i, _argv_item(a)))
    return "\n".join(out)


# ------------------------------------------------------------ registry I/O
def _load_tasks() -> list[dict]:
    try:
        raw = TASKS_PATH.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    return [t for t in data if isinstance(t, dict)] if isinstance(data, list) else []


def _save_tasks(tasks: list[dict]) -> None:
    """เขียนแบบ atomic: ลง .tmp ก่อนแล้วค่อย replace กันไฟล์พังตอนเซิร์ฟเวอร์ถูกปิด"""
    keep = [t for t in tasks if t.get("status") in _ACTIVE]
    done = [t for t in tasks if t.get("status") not in _ACTIVE]
    done.sort(key=_started_epoch)
    # ระวัง done[-0:] คือ "ทั้งหมด" ไม่ใช่ "ไม่เอาเลย" จึงต้องแยกกรณี room = 0
    room = max(0, MAX_TASKS_KEPT - len(keep))
    trimmed = keep + (done[-room:] if room else [])
    trimmed.sort(key=_started_epoch)
    tmp = TASKS_PATH.with_suffix(".json.tmp")
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(trimmed, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(str(tmp), str(TASKS_PATH))
    except OSError:
        pass


def _find(tasks: list[dict], task_id: str) -> dict | None:
    key = str(task_id or "").strip().lower()
    if not key:
        return None
    for t in tasks:
        if str(t.get("id", "")).lower() == key:
            return t
    # ยอมให้พิมพ์ id ไม่ครบถ้าไม่กำกวม
    hits = [t for t in tasks if str(t.get("id", "")).lower().startswith(key)]
    return hits[0] if len(hits) == 1 else None


# ------------------------------------------------------- process liveness
def _tasklist_map(pids: list[int]) -> dict[int, str]:
    """คืน {pid: ชื่ออิมเมจ} เฉพาะ pid ที่ยังมีชีวิต ใช้ tasklist ล้วน ไม่พึ่ง psutil

    วัดบนเครื่องนี้: ถามทีละ pid ~0.6 วิ ถามรวดเดียวทั้งเครื่อง ~1.5 วิ
    จึงสลับวิธีตามจำนวน pid ที่ต้องเช็ก
    """
    pids = sorted({int(p) for p in pids if p})
    if not pids:
        return {}
    args = ["tasklist", "/NH", "/FO", "CSV"]
    if len(pids) == 1:
        # ระวัง: /FI หลายอันถูกนำมา "และ" กัน (ทดสอบแล้ว: PID eq A + PID eq B = ไม่เจออะไรเลย)
        # จึงกรองได้เฉพาะตอนมี pid เดียว มากกว่านั้นต้องดึงทั้งเครื่องมากรองเอง
        args += ["/FI", "PID eq %d" % pids[0]]
    try:
        res = subprocess.run(args, capture_output=True, timeout=30,
                             creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return {p: "" for p in pids}      # เช็กไม่ได้ ถือว่ายังอยู่ ดีกว่าแจ้งตายผิด
    out = res.stdout or b""
    text = ""
    for enc in ("mbcs", "utf-8", "cp874"):
        try:
            text = out.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if not text:
        text = out.decode("utf-8", "replace")
    alive: dict[int, str] = {}
    wanted = set(pids)
    try:
        rows = csv.reader(io.StringIO(text))
        for row in rows:
            if len(row) >= 2 and row[1].strip().isdigit():
                pid = int(row[1].strip())
                if pid in wanted:
                    alive[pid] = row[0].strip().lower()
    except (csv.Error, ValueError):
        return {p: "" for p in pids}
    return alive


def _image_matches(task: dict, image: str) -> bool:
    """กัน pid reuse: ชื่ออิมเมจต้องตรงกับที่จดไว้ตอนเริ่ม"""
    expected = str(task.get("image") or "").lower()
    if not expected or not image:
        return True                      # ไม่มีข้อมูลให้เทียบ ก็ไม่กล่าวหา
    return expected == image


def _refresh(tasks: list[dict]) -> bool:
    """คำนวณสถานะใหม่ทุกครั้งที่อ่าน คืน True ถ้ามีอะไรเปลี่ยนจนต้องเซฟ"""
    changed = False
    pending: list[dict] = []
    for t in tasks:
        if t.get("status") not in _ACTIVE:
            continue
        proc = _PROCS.get(t.get("id"))
        if proc is not None:
            rc = proc.poll()
            if rc is not None:
                t["status"] = "stopped" if t.get("stop_requested") else "exited"
                t["exit_code"] = rc
                t.setdefault("ended_at", _utc_iso())
                t.setdefault("ended_epoch", _now())
                changed = True
            continue
        pending.append(t)                 # งานจากเซิร์ฟเวอร์รอบก่อน ต้องถาม Windows

    if pending:
        alive = _tasklist_map([_as_int(t.get("pid"), 0) for t in pending])
        for t in pending:
            pid = _as_int(t.get("pid"), 0)
            if pid in alive and _image_matches(t, alive[pid]):
                continue
            t["status"] = "stopped" if t.get("stop_requested") else "exited"
            if t.get("exit_code") is None:
                t["exit_code"] = None      # เก็บเกี่ยวรหัสจบจากลูกของรอบก่อนไม่ได้
            t["exit_unknown"] = True
            t.setdefault("ended_at", _utc_iso())
            t.setdefault("ended_epoch", _now())
            changed = True
    return changed


def _status_text(task: dict) -> str:
    st = task.get("status")
    if st == "running":
        return "กำลังทำงาน"
    if st == "stopped":
        return "ถูกสั่งหยุด"
    if st == "failed":
        return "เริ่มไม่สำเร็จ"
    if st == "exited":
        if task.get("exit_unknown"):
            return "จบแล้ว (ไม่ทราบรหัส)"
        rc = task.get("exit_code")
        if rc == 0:
            return "จบปกติ (0)"
        return "จบผิดพลาด (%s)" % rc
    return str(st)


# ------------------------------------------------------------- log pumping
def _pump(task_id: str, stream, log_path: str) -> None:
    """เธรดระบาย pipe ของลูก เขียนลง log จนถึงเพดานแล้วอ่านทิ้งต่อ

    ที่ต้องอ่านต่อแม้ชนเพดาน เพราะถ้าหยุดอ่าน pipe จะเต็มแล้วลูกจะค้างตอนเขียน stdout
    """
    written = 0
    capped = False
    fh = None
    try:
        fh = open(log_path, "ab", buffering=0)
        while True:
            try:
                chunk = stream.read1(65536)   # read1 คืนทันทีที่มีข้อมูล ไม่รอเต็มบัฟเฟอร์
            except (ValueError, OSError):
                break
            if not chunk:
                break
            if capped:
                continue
            room = LOG_MAX - written
            if len(chunk) <= room:
                fh.write(chunk)
                written += len(chunk)
                continue
            if room > 0:
                fh.write(chunk[:room])
                written += room
            fh.write(_CAP_NOTE.encode("utf-8", "replace"))
            capped = True
            _mark(task_id, {"log_capped": True})
    except Exception:                          # noqa: BLE001 - เธรดพื้นหลังห้ามล้ม
        pass
    finally:
        for closer in (stream, fh):
            try:
                if closer is not None:
                    closer.close()
            except (OSError, ValueError):
                pass
        _reap(task_id)


def _mark(task_id: str, fields: dict) -> None:
    """อัปเดตฟิลด์ของงานหนึ่งใน registry แบบปลอดภัยต่อหลายเธรด"""
    try:
        with _LOCK:
            tasks = _load_tasks()
            t = _find(tasks, task_id)
            if t is None:
                return
            t.update(fields)
            _save_tasks(tasks)
    except Exception:                          # noqa: BLE001
        pass


def _reap(task_id: str) -> None:
    """pipe ปิดแล้ว = ลูกจบแล้ว เก็บรหัสจบลง registry ให้เรียบร้อย"""
    proc = _PROCS.get(task_id)
    if proc is None:
        return
    try:
        rc = proc.wait(timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        return
    try:
        with _LOCK:
            tasks = _load_tasks()
            t = _find(tasks, task_id)
            if t is not None and t.get("status") in _ACTIVE:
                t["status"] = "stopped" if t.get("stop_requested") else "exited"
                t["exit_code"] = rc
                t["ended_at"] = _utc_iso()
                t["ended_epoch"] = _now()
                _save_tasks(tasks)
    except Exception:                          # noqa: BLE001
        pass
    finally:
        _PROCS.pop(task_id, None)


def _read_tail(log_path: str, lines: int) -> tuple[str, int]:
    """อ่านท้าย log คืน (ข้อความ, ขนาดไฟล์) กรอง NUL ที่อาจค้างจากไฟล์รุ่นเก่า"""
    try:
        size = os.path.getsize(log_path)
    except OSError:
        return ("(ยังไม่มีไฟล์ log)", 0)
    if size == 0:
        return ("(log ยังว่าง)", 0)
    try:
        with open(log_path, "rb") as fh:
            start = max(0, size - TAIL_READ_BYTES)
            fh.seek(start)
            raw = fh.read()
    except OSError as exc:
        return ("(อ่าน log ไม่ได้: %s)" % exc, size)
    raw = raw.replace(b"\x00", b"")
    # โปรแกรมที่ไม่ใช่ Python อาจพ่นข้อความไทยเป็น cp874/ANSI ลองไล่ให้ครบก่อนยอมแพ้
    text = ""
    for enc in ("utf-8", "cp874", "mbcs"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if not text:
        text = raw.decode("utf-8", "replace")
    if start > 0:
        nl = text.find("\n")
        text = text[nl + 1:] if nl >= 0 else text
    rows = text.splitlines()
    tail = rows[-lines:] if lines > 0 else []
    body = "\n".join(tail) if tail else "(log ยังว่าง)"
    return (body, size)


# ------------------------------------------------------------------- tools
@_safe
def task_start(command: str, cwd: str = "", confirm_token: str = "") -> str:
    try:
        argv = _parse_command(command)
    except ValueError as exc:
        guard.audit("task_start_denied", {"command": str(command)[:400],
                                          "reason": "parse_failed", "error": str(exc)})
        return "ERROR: อ่านคำสั่งไม่ออก: %s" % exc

    # หา cwd ก่อน เพราะต้องใช้ตอนค้นหาไฟล์โปรแกรมด้วย
    raw_cwd = str(cwd or "").strip()
    if raw_cwd:
        work_dir = guard.check_read(raw_cwd)
        if not os.path.isdir(work_dir):
            guard.audit("task_start_denied", {"cwd": work_dir, "reason": "no_such_dir"})
            return "ERROR: โฟลเดอร์ทำงานไม่มีอยู่จริง: %s" % work_dir
    else:
        # ไม่ระบุ cwd = โฟลเดอร์ของโปรเจกต์ที่เรียก (S04) ถ้าไม่ได้มาจาก tools/call ใช้ "tasks" แบบเดิม
        try:
            work_dir = guard.project_dir(guard.current_project() or DEFAULT_PROJECT)
        except Denied:
            work_dir = str(HERE)

    try:
        argv, warn = _resolve_exe(argv, work_dir)
    except ValueError as exc:
        guard.audit("task_start_denied", {"command": guard.scrub_text(command)[:400],
                                          "reason": "resolve_failed", "error": str(exc)})
        return "ERROR: %s" % exc

    # ด่านเดียวกับ exec_shell_command (งานเบื้องหลังคือคำสั่งที่เปลี่ยนเครื่องเสมอ):
    # ห้ามแตะโฟลเดอร์ secrets, ห้ามแตะ/รันโค้ดของสแตกหรือจุด persistence, ห้ามใช้ cwd ในเขตห้ามเขียน
    _guard_argv(argv, str(command), work_dir)

    preview = "%s\n(cwd: %s)" % (" ".join(argv), work_dir)

    ok = False
    token_in = str(confirm_token or "").strip()
    if token_in:
        try:
            ok = bool(guard.consume_confirm(token_in, "task_start", preview))
        except Exception:                      # noqa: BLE001
            ok = False
    if not ok:
        # รอบ review (R1): review = argv ทีละชิ้น (สิ่งที่ส่งให้ CreateProcess จริง) + cwd — กล่องอนุญาตแสดงข้อความนี้
        review = "\n".join(["[task_start] เริ่มโปรเซสเบื้องหลัง (ไม่ผ่าน shell — | > && เป็นข้อความธรรมดา)",
                            "cwd: %s" % guard.review_oneline(work_dir),
                            "โปรแกรมและอาร์กิวเมนต์ (argv) ทีละชิ้น เป็นสตริง JSON หนึ่งชิ้นต่อบรรทัด "
                            "= สิ่งที่จะรันจริง:"]
                           + ["  [%d] %s" % (i, _argv_item(a)) for i, a in enumerate(argv)]
                           + (["หมายเหตุ: %s" % guard.review_oneline(warn)] if warn else []))
        token = guard.need_confirm("task_start", preview, review=review)
        guard.audit("task_start_preview", {"command": guard.scrub_text(preview)[:400],
                                           "ref": guard.token_ref(token)})
        head = ("จะเริ่มโปรเซสเบื้องหลังตามนี้ (ยังไม่ได้เริ่ม)\n"
                "  โปรแกรมและอาร์กิวเมนต์ที่จะรันจริง:\n%s\n"
                "  โฟลเดอร์ทำงาน: %s\n"
                "  ผลลัพธ์ทั้ง stdout และ stderr จะถูกบันทึกลงไฟล์ log (เพดาน 2 MB)\n"
                % (_argv_text(argv), work_dir))
        if token_in:
            head = ("(confirm_token ที่ส่งมาใช้ไม่ได้หรือหมดอายุแล้ว จึงยังไม่เริ่ม "
                    "ขอ token ใหม่)\n\n") + head
        if warn:
            head += "  %s\n" % warn
        head += ("  หมายเหตุ: ไม่ได้ใช้ shell ตัวดำเนินการอย่าง | > && จะกลายเป็น "
                 "ข้อความธรรมดาที่ส่งให้โปรแกรม\n\n")
        # อาร์กิวเมนต์มาจากโมเดล: อักขระ bidi/zero-width ในข้อความประกอบก็ต้องแสดงเป็นรหัสเหมือนใน review
        # และบรรทัด "รายละเอียด" ใช้ argv แบบ JSON (preview ดิบที่ token ผูกอยู่มี \n ของ argv ได้ = บรรทัดปลอม)
        shown = "%s\n(cwd: %s)" % (" ".join(_argv_item(a) for a in argv), work_dir)
        return guard.visible(head) + guard.confirm_hint(token, "task_start", shown)

    task_id = secrets.token_hex(4)
    log_path = LOG_DIR / ("%s.log" % task_id)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return "ERROR: สร้างโฟลเดอร์ log ไม่ได้: %s" % exc

    record = {
        "id": task_id,
        "command": " ".join(argv),
        "command_raw": str(command),
        "argv": argv,
        "cwd": work_dir,
        "pid": None,
        "started_at": _utc_iso(),
        "started_epoch": _now(),
        "status": "failed",
        "exit_code": None,
        "log": str(log_path),
        "image": os.path.basename(argv[0]).lower(),
        "owner_pid": os.getpid(),
        "log_capped": False,
        # โปรเจกต์ที่สั่งงานนี้ task_list/get/stop ของโปรเจกต์อื่นจะมองไม่เห็นงานนี้ (S04)
        "project": guard.current_project(),
    }

    try:
        header = ("=== task %s ===\nคำสั่ง: %s\nโฟลเดอร์: %s\nเริ่ม: %s\n%s\n"
                  % (task_id, record["command"], work_dir, record["started_at"], "-" * 60))
        with open(str(log_path), "ab", buffering=0) as fh:
            fh.write(header.encode("utf-8", "replace"))
    except OSError:
        pass

    # stdout ของลูกเป็น pipe ไม่ใช่ console ทำให้ Python ฝั่งลูกเลือก encoding ตาม locale
    # ซึ่งบนเครื่องนี้คือ cp1252 พอสคริปต์ print ภาษาไทยจะตาย UnicodeEncodeError ทันที
    # (ทดสอบแล้วเจอจริง) จึงบังคับ stdio ของลูกเป็น utf-8 ให้ตรงกับที่เราถอดรหัส log
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8:replace"
    for _k in list(child_env):                 # ความลับของสแตกเองห้ามตกไปถึงโปรแกรมของผู้ใช้
        if _k.upper() in ("GATEWAY_API_KEY", "LLM_LOCAL_TOKEN_FILE"):
            child_env.pop(_k, None)

    try:
        proc = subprocess.Popen(
            argv,
            cwd=work_dir,
            env=child_env,
            stdin=subprocess.DEVNULL,          # ไม่ให้ลูกไปค้างรอ input จาก console
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,          # รวม stderr ลง log เดียวกัน
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
        )
    except (OSError, ValueError) as exc:
        record["error"] = "%s: %s" % (type(exc).__name__, exc)
        record["ended_at"] = _utc_iso()
        record["ended_epoch"] = _now()
        with _LOCK:
            tasks = _load_tasks()
            tasks.append(record)
            _save_tasks(tasks)
        guard.audit("task_start_failed", {"id": task_id, "command": record["command"],
                                          "error": record["error"]})
        return "ERROR: เริ่มโปรเซสไม่ได้: %s (บันทึกไว้เป็นงาน %s สถานะ failed)" % (
            record["error"], task_id)

    record["pid"] = proc.pid
    record["status"] = "running"
    _PROCS[task_id] = proc
    with _LOCK:
        tasks = _load_tasks()
        tasks.append(record)
        _save_tasks(tasks)

    threading.Thread(target=_pump, args=(task_id, proc.stdout, str(log_path)),
                     name="tasklog-%s" % task_id, daemon=True).start()

    guard.audit("task_start", {"id": task_id, "command": record["command"],
                               "cwd": work_dir, "pid": proc.pid})
    out = ("เริ่มงานเบื้องหลังแล้ว\n"
           "  id      : %s\n"
           "  คำสั่ง  : %s\n"
           "  โฟลเดอร์: %s\n"
           "  pid     : %d\n"
           "  log     : %s\n\n"
           "ดูความคืบหน้าด้วย task_get(id=\"%s\") หรือดูงานทั้งหมดด้วย task_list()"
           % (task_id, record["command"], work_dir, proc.pid, log_path, task_id))
    if warn:
        out += "\n%s" % warn
    return out


@_safe
def task_list() -> str:
    with _LOCK:
        tasks = _load_tasks()
        if _refresh(tasks):
            _save_tasks(tasks)
        snapshot = [t for t in tasks if _visible(t)]
    guard.audit("task_list", {"count": len(snapshot)})
    if not snapshot:
        return ("ยังไม่มีงานเบื้องหลังในทะเบียน\n"
                "เริ่มงานใหม่ด้วย task_start(command=\"...\")")

    snapshot.sort(key=_started_epoch, reverse=True)
    rows = [("id", "สถานะ", "pid", "ใช้เวลา", "คำสั่ง")]
    for t in snapshot:
        cmd = str(t.get("command", ""))
        if len(cmd) > 58:
            cmd = cmd[:55] + "..."
        if t.get("log_capped"):
            cmd += "  [log เต็ม]"
        rows.append((str(t.get("id", "?")), _status_text(t),
                     str(t.get("pid") or "-"), _elapsed_text(t), cmd))

    widths = [max(_dwidth(r[i]) for r in rows) for i in range(4)]
    lines = []
    for i, r in enumerate(rows):
        lines.append("%s  %s  %s  %s  %s" % (
            _pad(r[0], widths[0]), _pad(r[1], widths[1]),
            _pad(r[2], widths[2], True), _pad(r[3], widths[3], True), r[4]))
        if i == 0:
            lines.append("-" * min(100, _dwidth(lines[0])))
    active = sum(1 for t in snapshot if t.get("status") in _ACTIVE)
    lines.append("")
    lines.append("รวม %d งาน กำลังทำงานอยู่ %d งาน (ดูรายละเอียดด้วย task_get)"
                 % (len(snapshot), active))
    return "\n".join(lines)


@_safe
def task_get(id: str = "", tail: int = 50) -> str:   # noqa: A002 - ชื่อพารามิเตอร์ตาม schema
    n = max(1, min(_as_int(tail, 50), 500))
    with _LOCK:
        tasks = _load_tasks()
        if _refresh(tasks):
            _save_tasks(tasks)
        task = _find(tasks, id)
        task = dict(task) if task and _visible(task) else None
    if task is None:
        guard.audit("task_get_missing", {"id": str(id)[:80]})
        return ("ERROR: ไม่พบงาน id=\"%s\" ในทะเบียน (ดูรายการทั้งหมดด้วย task_list)"
                % str(id))

    guard.audit("task_get", {"id": task["id"], "tail": n})
    body, size = _read_tail(str(task.get("log", "")), n)
    info = [
        "งาน %s" % task["id"],
        "  คำสั่ง    : %s" % task.get("command", ""),
        "  โฟลเดอร์  : %s" % task.get("cwd", ""),
        "  สถานะ     : %s" % _status_text(task),
        "  pid       : %s" % (task.get("pid") or "-"),
        "  เริ่มเมื่อ : %s (UTC)" % task.get("started_at", "?"),
        "  ใช้เวลา   : %s" % _elapsed_text(task),
    ]
    if task.get("ended_at"):
        info.append("  จบเมื่อ    : %s (UTC)" % task["ended_at"])
    if task.get("error"):
        info.append("  ข้อผิดพลาด: %s" % task["error"])
    info.append("  log       : %s (%s ไบต์)" % (task.get("log", "-"), format(size, ",")))
    if task.get("log_capped"):
        info.append("  หมายเหตุ  : log ชนเพดาน 2 MB แล้ว ส่วนที่เกินถูกทิ้ง "
                    "แต่โปรเซสยังทำงานต่อได้ปกติ")
    if task.get("exit_unknown"):
        info.append("  หมายเหตุ  : งานนี้เริ่มโดยเซิร์ฟเวอร์รอบก่อน จึงรู้แค่ว่าโปรเซสหายไปแล้ว "
                    "แต่อ่านรหัสจบไม่ได้")
        if task.get("owner_pid") != os.getpid():
            info.append("             ถ้างานถูกปิดตอนเซิร์ฟเวอร์รีสตาร์ตพอดี สาเหตุน่าจะเป็น "
                        "ท่อรับผลลัพธ์ถูกปิด (broken pipe) งานที่พิมพ์ข้อความออกมาตลอดจะจบไปด้วย "
                        "ส่วนงานที่เงียบๆ จะรอดและยังทำงานต่อ")
    if task.get("status") in _ACTIVE and task.get("owner_pid") != os.getpid():
        info.append("  หมายเหตุ  : เซิร์ฟเวอร์ถูกรีสตาร์ตหลังงานนี้เริ่ม "
                    "การบันทึก log จึงหยุดไว้แค่ตอนรีสตาร์ต (ตัวงานยังทำงานอยู่)")
    info.append("")
    info.append("--- log %d บรรทัดท้าย ---" % n)
    info.append(body)
    return "\n".join(info)


@_safe
def task_stop(id: str = "", confirm_token: str = "") -> str:   # noqa: A002
    with _LOCK:
        tasks = _load_tasks()
        if _refresh(tasks):
            _save_tasks(tasks)
        task = _find(tasks, id)
        snapshot = dict(task) if task and _visible(task) else None
    if snapshot is None:
        guard.audit("task_stop_missing", {"id": str(id)[:80]})
        return ("ERROR: ไม่พบงาน id=\"%s\" ในทะเบียน — หยุดได้เฉพาะงานที่เริ่มผ่าน "
                "task_start เท่านั้น ไม่รับ pid ตรงๆ" % str(id))

    if snapshot.get("status") not in _ACTIVE:
        return ("งาน %s ไม่ได้ทำงานอยู่แล้ว (สถานะ: %s) จึงไม่มีอะไรให้หยุด"
                % (snapshot["id"], _status_text(snapshot)))

    pid = _as_int(snapshot.get("pid"), 0)
    if pid <= 0:
        return "ERROR: งาน %s ไม่มี pid ที่ใช้ได้" % snapshot["id"]

    preview = "งาน %s (pid %d): %s" % (snapshot["id"], pid, snapshot.get("command", ""))

    ok = False
    token_in = str(confirm_token or "").strip()
    if token_in:
        try:
            ok = bool(guard.consume_confirm(token_in, "task_stop", preview))
        except Exception:                      # noqa: BLE001
            ok = False
    if not ok:
        # รอบ review (R1): review = งานที่จะถูกหยุด (id/pid/คำสั่ง) ตามทะเบียน ค่าเดียวกับที่ token ผูกอยู่
        review = "\n".join(["[task_stop] หยุดงานเบื้องหลังพร้อมโปรเซสลูกทั้งหมด",
                            "id: %s" % guard.review_oneline(snapshot["id"]), "pid: %d" % pid,
                            # คำสั่งในทะเบียนมาจากโมเดลตอน task_start — มี \n ได้ ต้องไม่แตกเป็นบรรทัดปลอม
                            "คำสั่ง: %s" % guard.review_oneline(snapshot.get("command", ""))])
        token = guard.need_confirm("task_stop", preview, review=review)
        guard.audit("task_stop_preview", {"id": snapshot["id"], "pid": pid,
                                          "ref": guard.token_ref(token)})
        head = ("จะสั่งหยุดงานนี้ (ยังไม่ได้หยุด)\n"
                "  id      : %s\n"
                "  คำสั่ง  : %s\n"
                "  pid     : %d\n"
                "  ใช้เวลา : %s\n"
                "  จะปิดทั้งโปรเซสนี้และโปรเซสลูกที่มันสร้างไว้ งานที่ค้างอยู่จะไม่ถูกบันทึกต่อ\n\n"
                % (snapshot["id"], snapshot.get("command", ""), pid, _elapsed_text(snapshot)))
        if token_in:
            head = "(confirm_token ใช้ไม่ได้หรือหมดอายุ จึงยังไม่หยุด ขอ token ใหม่)\n\n" + head
        return guard.visible(head) + guard.confirm_hint(token, "task_stop", preview)

    # ด่านสุดท้ายกัน pid reuse: ถ้าอิมเมจไม่ตรงกับตอนเริ่ม แปลว่า Windows เอา pid ไปใช้ซ้ำแล้ว
    alive = _tasklist_map([pid])
    if pid not in alive:
        _mark(snapshot["id"], {"status": "exited", "ended_at": _utc_iso(),
                               "ended_epoch": _now(), "exit_unknown": True})
        return "งาน %s จบไปเองแล้วก่อนจะสั่งหยุด ไม่ได้ทำอะไรเพิ่ม" % snapshot["id"]
    if not _image_matches(snapshot, alive[pid]):
        guard.audit("task_stop_refused", {"id": snapshot["id"], "pid": pid,
                                          "expected": snapshot.get("image"),
                                          "actual": alive[pid], "reason": "pid_reuse"})
        _mark(snapshot["id"], {"status": "exited", "ended_at": _utc_iso(),
                               "ended_epoch": _now(), "exit_unknown": True})
        return ("ERROR: ไม่หยุดให้ เพราะ pid %d ตอนนี้เป็นของโปรแกรมอื่นแล้ว "
                "(คาดว่า %s แต่เจอ %s) งานเดิมคงจบไปแล้วและ Windows เอา pid ไปใช้ซ้ำ "
                "จึงไม่ฆ่าเพื่อความปลอดภัย" % (pid, snapshot.get("image"), alive[pid]))

    _mark(snapshot["id"], {"stop_requested": True})
    try:
        res = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                             capture_output=True, timeout=30,
                             creationflags=CREATE_NO_WINDOW)
        rc = res.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        guard.audit("task_stop_failed", {"id": snapshot["id"], "pid": pid, "error": str(exc)})
        return "ERROR: สั่ง taskkill ไม่สำเร็จ: %s" % exc

    time.sleep(0.4)
    still = _tasklist_map([pid])
    gone = pid not in still or not _image_matches(snapshot, still.get(pid, ""))
    proc = _PROCS.get(snapshot["id"])
    if proc is not None:
        try:
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass
    fields = {"stop_requested": True}
    if gone:
        fields.update({"status": "stopped", "ended_at": _utc_iso(),
                       "ended_epoch": _now()})
        if proc is not None and proc.returncode is not None:
            fields["exit_code"] = proc.returncode
    _mark(snapshot["id"], fields)
    guard.audit("task_stop", {"id": snapshot["id"], "pid": pid,
                              "taskkill_rc": rc, "gone": gone})
    if gone:
        return ("หยุดงาน %s แล้ว (pid %d ปิดพร้อมโปรเซสลูกทั้งหมด)\n"
                "log ที่บันทึกไว้ยังอ่านย้อนหลังได้ด้วย task_get(id=\"%s\")"
                % (snapshot["id"], pid, snapshot["id"]))
    return ("ERROR: สั่งหยุดงาน %s แล้วแต่ pid %d ยังอยู่ (taskkill คืนค่า %d) "
            "อาจเป็นเพราะโปรเซสรันด้วยสิทธิ์สูงกว่าเซิร์ฟเวอร์นี้"
            % (snapshot["id"], pid, rc))


# -------------------------------------------------------------- MCP schema
TOOLS = [
    {"name": "task_start",
     "description": ("เริ่มโปรแกรมเป็นงานเบื้องหลังแล้วเก็บ log ไว้ให้อ่านย้อนหลัง "
                     "ใช้กับงานที่รันนาน เช่น เทรนโมเดล ติดตั้งแพ็กเกจ หรือรันเซิร์ฟเวอร์ "
                     "เป็นการกระทำสองขั้นตอน: เรียกครั้งแรกเพื่อดูคำสั่งที่จะรันและรับ confirm_token "
                     "แล้วถามผู้ใช้ก่อน ผู้ใช้อนุมัติแล้วจึงเรียก local_confirm(confirm_token)"),
     "inputSchema": {"type": "object",
                     "properties": {
                         "command": {"type": "string",
                                     "description": ("คำสั่งที่จะรัน เช่น C:\\Python313\\python.exe -u train.py "
                                                     "ใส่เครื่องหมายคำพูดครอบ path ที่มีช่องว่าง หรือจะส่งเป็น "
                                                     "JSON array เช่น [\"python\",\"-u\",\"ไฟล์ ของฉัน.py\"] ก็ได้ "
                                                     "ไม่ผ่าน shell ตัวดำเนินการ | > && ใช้ไม่ได้")},
                         "cwd": {"type": "string",
                                 "description": "โฟลเดอร์ทำงาน ถ้าเว้นว่างจะใช้โฟลเดอร์ข้อมูลกลางของงาน"},
                         "confirm_token": {"type": "string",
                                           "description": "token ที่ได้จากการเรียกครั้งแรก ใส่เมื่อผู้ใช้อนุมัติแล้ว"}},
                     "required": ["command"]}},
    {"name": "task_list",
     "description": ("แสดงรายการงานเบื้องหลังทั้งหมดพร้อมสถานะล่าสุด pid และเวลาที่ใช้ไป "
                     "ใช้เมื่อผู้ใช้ถามว่ามีอะไรรันอยู่บ้าง หรือก่อนจะไปดู log ของงานใดงานหนึ่ง"),
     "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "task_get",
     "description": ("ดูรายละเอียดงานหนึ่งงานพร้อม log ท้ายสุดตามจำนวนบรรทัดที่ขอ "
                     "ใช้ติดตามความคืบหน้าหรือดูว่างานพังเพราะอะไร"),
     "inputSchema": {"type": "object",
                     "properties": {
                         "id": {"type": "string", "description": "id ของงานที่ได้จาก task_start หรือ task_list"},
                         "tail": {"type": "integer",
                                  "description": "จำนวนบรรทัดท้าย log 1-500 (ค่าเริ่มต้น 50)"}},
                     "required": ["id"]}},
    {"name": "task_stop",
     "description": ("สั่งหยุดงานเบื้องหลังที่เริ่มไว้ด้วย task_start พร้อมโปรเซสลูกทั้งหมด "
                     "หยุดได้เฉพาะงานในทะเบียนนี้เท่านั้น เป็นการกระทำสองขั้นตอนเหมือน task_start"),
     "inputSchema": {"type": "object",
                     "properties": {
                         "id": {"type": "string", "description": "id ของงานที่จะหยุด"},
                         "confirm_token": {"type": "string",
                                           "description": "token ที่ได้จากการเรียกครั้งแรก ใส่เมื่อผู้ใช้อนุมัติแล้ว"}},
                     "required": ["id"]}},
]

IMPL = {
    "task_start": task_start,
    "task_list": task_list,
    "task_get": task_get,
    "task_stop": task_stop,
}
