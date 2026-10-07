# -*- coding: utf-8 -*-
"""เครื่องมือไฟล์และคำสั่งระบบที่ผ่านชั้นป้องกัน

มาแทนที่ `--tools all` ของ llama-server ซึ่งเข้าถึงได้ทุก path โดยไม่มีการตรวจสอบ
ชุดนี้ให้ความสามารถเท่าเดิม (อ่าน เขียน แก้ ค้น รันคำสั่ง) แต่ทุกทางเข้าออก
ต้องผ่าน guard.check_read / guard.check_write ก่อน และคำสั่งระบบต้องยืนยันสองขั้น

ทุกฟังก์ชันคืน str เสมอ และไม่โยน exception ออกไป เพราะ MCP client
จะตัดการเชื่อมต่อถ้าเครื่องมือพัง
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import guard

# secrets_util อยู่ที่ C:\LLM (โฟลเดอร์แม่) — ต่อท้าย sys.path ไม่แทรกหน้า กันชื่อไปทับ stdlib
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.append(_ROOT)
try:
    import secrets_util  # noqa: E402
except Exception:        # noqa: BLE001 — ไม่มีตัวช่วยก็ยังต้องทำงาน แค่ไม่มีด่านลบ token ในผลลัพธ์
    secrets_util = None

MAX_HITS = 200
MAX_LINE = 400
EXEC_TIMEOUT = 120


def _err(exc: Exception) -> str:
    if isinstance(exc, guard.Denied):
        return "ปฏิเสธ: %s" % exc
    return "ผิดพลาด: %s: %s" % (type(exc).__name__, exc)


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "%.0f %s" % (n, unit) if unit == "B" else "%.1f %s" % (n, unit)
        n /= 1024
    return str(n)


def _is_binary(chunk: bytes) -> bool:
    return b"\x00" in chunk


# --------------------------------------------------------------------- read
def read_file(path: str, offset: int = 0, limit: int = 2000, **_) -> str:
    try:
        p = guard.check_read(path)
        guard.audit("read_file", {"path": p, "offset": offset, "limit": limit})
        f = Path(p)
        if not f.exists():
            return "ไม่พบไฟล์: %s" % p
        if f.is_dir():
            return list_dir(p)
        size = f.stat().st_size
        cap = guard.max_read_bytes()
        with f.open("rb") as fh:
            head = fh.read(4096)
        if _is_binary(head):
            return "ไฟล์นี้เป็นไบนารี (%s) อ่านเป็นข้อความไม่ได้\n%s" % (_human(size), p)
        if size > cap:
            return ("ไฟล์ใหญ่เกินกำหนด %s (สูงสุด %s) ใช้ grep_search หรือระบุ offset/limit แทน"
                    % (_human(size), _human(cap)))
        text = f.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        off = max(0, int(offset))
        lim = max(1, min(int(limit), 5000))
        window = lines[off:off + lim]
        out = ["%6d\t%s" % (off + i + 1, ln[:MAX_LINE]) for i, ln in enumerate(window)]
        if off + lim < len(lines):
            out.append("... (อีก %d บรรทัด จากทั้งหมด %d)" % (len(lines) - off - lim, len(lines)))
        return "\n".join(out) if out else "(ไฟล์ว่าง)"
    except Exception as exc:
        return _err(exc)


def list_dir(path: str, **_) -> str:
    try:
        p = guard.check_read(path)
        guard.audit("list_dir", {"path": p})
        d = Path(p)
        if not d.is_dir():
            return "ไม่ใช่โฟลเดอร์: %s" % p
        rows, hidden = [], 0
        for item in sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                guard.check_read(str(item))
            except guard.Denied:
                hidden += 1
                continue
            try:
                st = item.stat()
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
                rows.append("%-19s %10s  %s%s" % (
                    when, "<DIR>" if item.is_dir() else _human(st.st_size),
                    item.name, "\\" if item.is_dir() else ""))
            except OSError:
                rows.append("%-19s %10s  %s" % ("?", "?", item.name))
            if len(rows) >= 500:
                rows.append("... (แสดง 500 รายการแรก)")
                break
        head = "%s  (%d รายการ)" % (p, len(rows))
        if hidden:
            head += "  [ซ่อน %d รายการตามนโยบายความปลอดภัย]" % hidden
        return head + "\n" + "\n".join(rows)
    except Exception as exc:
        return _err(exc)


def get_info(path: str = "", **_) -> str:
    """ข้อมูลไฟล์/โฟลเดอร์ หรือถ้าไม่ระบุ path จะสรุปนโยบายความปลอดภัยที่ใช้อยู่"""
    if not str(path).strip():
        return guard.policy_summary()
    try:
        p = guard.check_read(path)
        guard.audit("get_info", {"path": p})
        f = Path(p)
        if not f.exists():
            return "ไม่พบ: %s" % p
        st = f.stat()
        kind = "โฟลเดอร์" if f.is_dir() else "ไฟล์"
        lines = [
            "path      %s" % p,
            "ชนิด      %s" % kind,
            "ขนาด      %s (%s ไบต์)" % (_human(st.st_size), format(st.st_size, ",")),
            "แก้ล่าสุด %s" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
            "สร้างเมื่อ %s" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_ctime)),
        ]
        if f.is_dir():
            try:
                lines.append("ภายใน     %d รายการ" % sum(1 for _ in f.iterdir()))
            except OSError:
                pass
        else:
            try:
                guard.check_write(p)
                lines.append("สิทธิ์     เขียนได้")
            except guard.Denied:
                lines.append("สิทธิ์     อ่านอย่างเดียว")
        return "\n".join(lines)
    except Exception as exc:
        return _err(exc)


# -------------------------------------------------------------------- write
def _sha(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8", "replace")).hexdigest()


def _snippet(text: str, limit: int = 300) -> str:
    """ตัวอย่างข้อความสั้นๆ ให้ผู้ใช้เห็นก่อนอนุมัติ (บรรทัดใหม่แสดงเป็น ⏎)"""
    flat = str(text).replace("\r\n", "\n").replace("\n", " ⏎ ")
    return flat if len(flat) <= limit else flat[:limit] + " …(ตัดที่ %d ตัวอักษร)" % limit


def _bad_token_msg() -> str:
    return ("confirm_token ใช้ไม่ได้ (หมดอายุ ไม่ได้ยืนยันผ่าน local_confirm หรือไฟล์/สถานะเปลี่ยนไปหลังขอ) "
            "ยังไม่ได้ทำอะไร — ขอใหม่โดยเรียกเครื่องมือนี้อีกครั้งโดยไม่ใส่ token")


# ============================================================ checkpoints / diff / undo
# (ส่วนของ owner "mcp-exec" — สัญญา K1 undo/checkpoints) import อยู่ตรงนี้เพื่อให้ทั้งบล็อกแยกจากโค้ดเดิม
#
# ทุกการเขียน/แก้/ทับไฟล์ผ่านเครื่องมือ เก็บสำเนา "ก่อนแก้" ไว้ที่ data\<slug>\checkpoints\<id>\ ก่อนลงมือ
#   journal.json = path, เครื่องมือ, sha256 ก่อน/หลัง, ขนาด, มีไฟล์อยู่ก่อนไหม, ถูกย้อนไปแล้วหรือยัง
#   before.bin   = ไบต์เดิมทั้งไฟล์ — นามสกุล .bin เสมอ (ไม่ใช่ .py/.ps1) สำเนาต้องไม่ถูกรัน/โหลดโดยบังเอิญ
# undo = คืนไบต์จาก checkpoint ล่าสุดของไฟล์นั้น (ยืนยันสองขั้น) และก่อนคืนจะเก็บ checkpoint ของสถานะ
# ปัจจุบันไว้อีกชั้น (tool="undo") การย้อนจึงย้อนกลับได้อีก ไม่มีข้อมูลหายระหว่างทาง
# การ undo "การสร้างไฟล์ใหม่" = ย้ายไฟล์เข้า checkpoint (ไม่ลบทิ้งที่ไหนเลย)
# ไม่มีการลบ checkpoint อัตโนมัติ: ดิสก์ C: ของเครื่องนี้แทบเต็ม จึงใช้เพดานแทน — เกินแล้วไม่เก็บสำเนา
# และบอกผู้ใช้ตรงๆ ในผลลัพธ์ การลบของเก่าเป็นการตัดสินใจของผู้ใช้เอง
# checkpoint เป็นของโปรเจกต์ที่ทำการเขียน (S04: โปรเจกต์อื่นมองไม่เห็น) แม้ไฟล์เป้าหมายจะอยู่นอกโปรเจกต์
import difflib as _difflib            # noqa: E402
import json as _json                  # noqa: E402
import secrets as _secrets            # noqa: E402
import shutil as _shutil              # noqa: E402
import threading as _threading        # noqa: E402

CHECKPOINT_DIRNAME = "checkpoints"
CHECKPOINT_FILE_CAP = 20 * 1024 * 1024        # ไฟล์ใหญ่กว่านี้ไม่เก็บสำเนา (write_file รับได้สูงสุด ~16 MB อยู่แล้ว)
CHECKPOINT_BUDGET = 300 * 1024 * 1024         # รวมทุก checkpoint ของหนึ่งโปรเจกต์
DIFF_MAX_LINES = 200                          # diff ในผลลัพธ์ของ write/edit
DIFF_NEW_FILE_LINES = 40                      # ไฟล์ใหม่: diff คือเนื้อที่โมเดลเพิ่งเขียนเอง ไม่ต้องสะท้อนยาว
DIFF_PREVIEW_LINES = 60                       # diff ในข้อความขอยืนยัน
DIFF_MAX_BYTES = 2_000_000                    # ใหญ่กว่านี้ไม่ทำ diff (difflib ช้าแบบกำลังสอง)
_CP_ID_RE = re.compile(r"^\d{8}-\d{6}-\d{6}-[0-9a-f]{4}$")
_CP_LOCK = _threading.Lock()


def _cp_root() -> Path:
    return Path(guard.project_dir(guard.current_project() or "default")) / CHECKPOINT_DIRNAME


def in_checkpoints(path: str) -> bool:
    """path อยู่ใต้ data\\<โปรเจกต์ใดก็ได้>\\checkpoints\\ หรือไม่

    เครื่องมือเขียนไฟล์ห้ามแตะโฟลเดอร์นี้: ถ้าเขียน journal.json ปลอมได้ ประวัติ undo ก็ถูกบิดได้
    (undo ยังต้องยืนยันและผ่าน check_write ของไฟล์เป้าหมายอยู่ดี แต่ประวัติควรเชื่อถือได้)
    """
    try:
        base = os.path.normcase(os.path.realpath(str(guard.PROJECT_DATA)))
        rel = os.path.relpath(os.path.normcase(os.path.realpath(str(path))), base)
    except (ValueError, OSError):
        return False                   # คนละไดรฟ์ = ไม่ได้อยู่ใต้ PROJECT_DATA แน่นอน
    parts = rel.split(os.sep)
    return len(parts) >= 2 and parts[0] not in ("..", ".", "") and parts[1] == CHECKPOINT_DIRNAME


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cp_used(root: Path) -> int:
    total = 0
    try:
        with os.scandir(root) as it:
            for e in it:
                if e.is_dir(follow_symlinks=False):
                    try:
                        total += os.path.getsize(os.path.join(e.path, "before.bin"))
                    except OSError:
                        pass
    except OSError:
        pass
    return total


def _journal_write(d: Path, entry: dict) -> None:
    """เขียนแบบ atomic (ไฟล์ชั่วคราว + os.replace) ผู้อ่านไม่มีทางเห็น journal ครึ่งไฟล์"""
    data = {k: v for k, v in entry.items() if not str(k).startswith("_")}
    tmp = d / ("journal.%s.tmp" % _secrets.token_hex(3))
    tmp.write_text(_json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, d / "journal.json")


def _journal_read(d: Path) -> dict | None:
    try:
        data = _json.loads((d / "journal.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("id") != d.name:
        return None                    # journal ที่ id ไม่ตรงชื่อโฟลเดอร์ = ถูกย้าย/ปลอม ไม่ใช้
    return data


def _cp_entries(root: Path, limit: int = 5000) -> list[dict]:
    """checkpoint ของโปรเจกต์นี้ ใหม่สุดก่อน (ชื่อโฟลเดอร์คือเวลา เรียงตามชื่อได้เลย)"""
    try:
        names = sorted((n for n in os.listdir(root) if _CP_ID_RE.match(n)), reverse=True)
    except OSError:
        return []
    out = []
    for n in names[:limit]:
        e = _journal_read(root / n)
        if e is not None:
            out.append(e)
    return out


def checkpoint_before(path: str, tool: str, move: bool = False) -> dict:
    """เก็บสำเนาไฟล์ก่อนแก้ — เรียกหลังผ่าน guard.check_write และหลังยืนยันแล้วเท่านั้น (ไม่โยน exception)

    path ต้องเป็นค่าที่ guard คืนมา (normalize แล้ว) move=True ย้ายไฟล์เข้า checkpoint แทนการคัดลอก
    (ใช้ตอน undo การสร้างไฟล์) คืน entry ไว้ส่งต่อให้ checkpoint_after หลังเขียนเสร็จ
    ฟังก์ชันสาธารณะ: เครื่องมืออื่นที่เขียนทับไฟล์ (เช่น make_file) เรียกใช้ได้เหมือนกัน
    """
    now = time.time()
    entry = {"version": 1, "id": "", "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
             "tool": str(tool), "path": str(path), "project": guard.current_project() or "default",
             "existed": False, "size_before": None, "sha256_before": None, "blob": None,
             "note": "", "sha256_after": None, "size_after": None, "undone_by": None,
             "restores": None}
    try:
        root = _cp_root()
        with _CP_LOCK:
            cid = "%s-%06d-%s" % (time.strftime("%Y%m%d-%H%M%S", time.localtime(now)),
                                  int((now % 1) * 1_000_000), _secrets.token_hex(2))
            d = root / cid
            d.mkdir(parents=True, exist_ok=False)
        entry["id"], entry["_dir"] = cid, d
        if os.path.isfile(path):
            size = os.path.getsize(path)
            entry["existed"], entry["size_before"] = True, size
            if size > CHECKPOINT_FILE_CAP:
                entry["note"] = "too_large"
            elif _cp_used(root) + size > CHECKPOINT_BUDGET:
                entry["note"] = "budget"
            else:
                blob = d / "before.bin"
                if move:
                    _shutil.move(str(path), str(blob))
                else:
                    _shutil.copyfile(str(path), str(blob))
                entry["blob"] = "before.bin"
                entry["sha256_before"] = _file_sha(blob)
        _journal_write(d, entry)
    except Exception as exc:          # noqa: BLE001 — checkpoint พังต้องไม่ทำให้เครื่องมือพัง
        entry["note"] = entry["note"] or "error:%s" % type(exc).__name__
        entry["_error"] = True
    return entry


def checkpoint_after(entry: dict, path: str) -> None:
    """บันทึก sha256/ขนาดหลังเขียน ลง journal ของ checkpoint เดิม (ไม่โยน exception)"""
    d = entry.get("_dir")
    if not d or entry.get("_error"):
        return
    try:
        if os.path.isfile(path):
            entry["size_after"] = os.path.getsize(path)
            entry["sha256_after"] = _file_sha(path) if entry["size_after"] <= 4 * CHECKPOINT_FILE_CAP else None
        else:
            entry["size_after"], entry["sha256_after"] = None, None
        _journal_write(Path(d), entry)
    except Exception:                 # noqa: BLE001
        pass


def checkpoint_note(entry: dict) -> str:
    """บรรทัดสั้นๆ ต่อท้ายผลของเครื่องมือ: เก็บ checkpoint ได้ไหม ย้อนยังไง"""
    if entry.get("_error"):
        return "คำเตือน: เก็บ checkpoint ไม่สำเร็จ (%s) — ย้อนการเปลี่ยนแปลงนี้ด้วย undo ไม่ได้" % entry.get("note")
    note = entry.get("note")
    if note == "too_large":
        return ("หมายเหตุ: ไฟล์เดิมใหญ่เกิน %d MB จึงไม่ได้เก็บสำเนาไว้ — undo ไฟล์นี้ไม่ได้"
                % (CHECKPOINT_FILE_CAP >> 20))
    if note == "budget":
        return ("หมายเหตุ: พื้นที่ checkpoint ของโปรเจกต์เต็ม (%d MB) จึงไม่ได้เก็บสำเนาไว้ — undo ไม่ได้ "
                "(ผู้ใช้ลบ checkpoint เก่าเองได้ที่ %s)" % (CHECKPOINT_BUDGET >> 20, _cp_root()))
    return "checkpoint %s (ย้อนกลับได้ด้วย undo)" % entry.get("id")


def _diff_text(data) -> str | None:
    """ไบต์ -> ข้อความสำหรับ diff (None = ใหญ่เกิน/ไบนารี, b"" หรือ None ขาเข้า = ไฟล์ว่าง/ไม่มีไฟล์)"""
    if data is None:
        return ""
    if len(data) > DIFF_MAX_BYTES or b"\x00" in data[:8192]:
        return None
    return data.decode("utf-8", "replace")


def unified_diff(before, after, path: str, max_lines: int = DIFF_MAX_LINES) -> str:
    """unified diff (difflib) ในรั้ว ```diff ตัดที่ max_lines — before/after เป็นข้อความ, None = ทำ diff ไม่ได้"""
    if before is None or after is None:
        return "(ไม่แสดง diff: ไฟล์ใหญ่เกิน %d MB หรือเป็นไฟล์ไบนารี)" % (DIFF_MAX_BYTES // 1_000_000)
    # ปรับ CRLF เป็น LF ทั้งสองฝั่ง: write_text บน Windows เขียน CRLF แต่ content ที่โมเดลส่งมาเป็น LF
    # ไม่งั้นทุกบรรทัดจะดูเหมือนถูกแก้ทั้งไฟล์
    a = str(before).replace("\r\n", "\n").splitlines()
    b = str(after).replace("\r\n", "\n").splitlines()
    name = os.path.basename(str(path)) or str(path)
    lines = list(_difflib.unified_diff(a, b, "a/" + name, "b/" + name, n=3, lineterm=""))
    if not lines:
        return "(เนื้อหาไม่เปลี่ยน)"
    shown = [ln if len(ln) <= MAX_LINE else ln[:MAX_LINE] + " …" for ln in lines[:max_lines]]
    body = "\n".join(shown)
    if len(lines) > max_lines:
        body += "\n... (ตัด diff ที่ %d บรรทัด จากทั้งหมด %d บรรทัด)" % (max_lines, len(lines))
    fence = "```"
    while fence in body:
        fence += "`"
    return "%sdiff\n%s\n%s" % (fence, body, fence)


# ------------------------------------------------------ ข้อความตรวจทาน (review) — สัญญา R1 รอบ review
# review คือสิ่งที่คนเห็นในกล่อง "อนุญาต" ตอนกด local_confirm จึงต้องครบและตรงกับสิ่งที่จะเกิดจริง:
#   * ไม่ใช้ unified_diff ข้างบน (ตัดบรรทัดยาวที่ 400 ตัวอักษรด้วย " …" = ซ่อนท้ายบรรทัดได้, splitlines ยัง
#     กิน \x0c กับ U+2028 เป็นตัวขึ้นบรรทัดจนตาไม่เห็น) — แตกบรรทัดที่ \n เท่านั้น แล้วให้ guard แสดงอักขระซ่อน/ตัดบรรทัด
#   * เนื้อหาเล็ก = แสดงทั้งไฟล์พร้อมเลขบรรทัด / ใหญ่ = ขนาด + sha256 + diff ไม่เกิน 400 บรรทัด
#     + บรรทัดบอกชัดว่าไม่แสดงอีกกี่บรรทัดพร้อม hash ของเนื้อหาเต็ม
#   * เครื่องหมายหัว/ท้ายของบล็อก diff ขึ้นต้นด้วย "=" ซึ่งบรรทัดของ diff ไม่มีทางขึ้นต้นได้ (ปลอมจบบล็อกไม่ได้)
_REVIEW_BIG_FACTOR = 4          # ดิบยาวเกินเพดาน x4 = ใหญ่แน่นอน ไม่ต้องไล่วัดทั้งไฟล์ (write รับได้ถึง 16 MB)


def _review_split(text: str) -> list[str]:
    lines = str(text).replace("\r\n", "\n").split("\n")
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()
    return lines


def _review_diff(before: str, after: str, path: str) -> list[str]:
    name = os.path.basename(str(path)) or str(path)
    return list(_difflib.unified_diff(_review_split(before), _review_split(after),
                                      "a/" + name, "b/" + name, n=3, lineterm=""))


def _review_fits_whole(numbered: list[str], raw: str) -> bool:
    if len(raw) > _REVIEW_BIG_FACTOR * guard.REVIEW_BLOCK_MAX_CHARS \
            or len(numbered) > _REVIEW_BIG_FACTOR * guard.REVIEW_BLOCK_MAX_LINES:
        return False
    n_l, n_c = guard.review_measure("\n".join(numbered))
    return n_l <= guard.REVIEW_BLOCK_MAX_LINES and n_c <= guard.REVIEW_BLOCK_MAX_CHARS


def _diff_block(title: str, lines: list[str], sha: str) -> tuple[list[str], int]:
    """(บรรทัดของบล็อก diff, จำนวนบรรทัด diff ที่ไม่ได้แสดงเพราะเกินเพดาน)"""
    body, omitted = guard.review_capped(lines, sha)
    return ["===== %s =====" % title, body or "(เนื้อหาไม่เปลี่ยน)", "===== จบ diff ====="], omitted


# รอบ FIXER (R3 ขยายไปถึงไฟล์สคริปต์): เดิมไฟล์ .py/.bat/.ps1 ใหม่ที่ยาวเกิน 400 บรรทัดยังได้ token โดย review
# แสดงแค่ 400 บรรทัดแรก + "(ไม่แสดงอีก N บรรทัด — hash …)" โค้ดหลังเพดานถูกเขียนลงไฟล์ที่รันได้โดยไม่มีคนเห็น
# แล้วโมเดลก็สั่งรันไฟล์นั้นต่อได้ = ทางอ้อมของกฎ "โค้ดที่ยาวเกินจะตรวจทันต้องถูกปฏิเสธก่อนออก token" ของ python
# ตอนนี้โค้ดที่จะลงไฟล์สคริปต์ (write ทั้งใหม่และทับ, edit) ต้องแสดงได้ครบทุกบรรทัดใน review ไม่งั้นไม่ออก token
# (ไฟล์ข้อมูลทั่วไปยังใช้ diff แบบตัดพร้อม hash ได้ตามสัญญา R1 — ไม่ถูกรันเป็นโค้ด)
# undo ไม่อยู่ในกฎนี้: เนื้อที่คืนคือไบต์เดิมที่เคยอยู่บนดิสก์ (ไม่ใช่โค้ดที่โมเดลเพิ่งแต่ง) และการย้อนไฟล์ใหญ่ต้องทำได้
def _script_too_large(p: str, what: str) -> guard.ReviewTooLarge:
    return guard.ReviewTooLarge(
        "%s ของไฟล์สคริปต์/โปรแกรม %s ยาวเกินกว่าที่คนจะตรวจได้ครบในกล่องอนุญาต (เพดาน %d บรรทัด / %d ตัวอักษร "
        "หลังแสดงอักขระซ่อนและตัดบรรทัด) จึงไม่ออก confirm_token — โค้ดที่จะลงไฟล์ที่รันได้ต้องแสดงครบทุกบรรทัด "
        "ให้แบ่งเป็นหลายไฟล์/โมดูลที่เล็กลง หรือเขียนส่วนแรกก่อนแล้วเพิ่มทีละส่วนด้วย edit"
        % (what, p, guard.REVIEW_BLOCK_MAX_LINES, guard.REVIEW_BLOCK_MAX_CHARS))


def _write_review(p: str, content: str, exists: bool, old_size: int, old_text,
                  script: bool = False, old_sha: str = "") -> str:
    """review ของ write_file: path + เนื้อหาใหม่ทั้งไฟล์ (หรือถ้าใหญ่: ขนาด + sha256 + diff/ช่วงต้นแบบตัด)
    old_text = เนื้อเดิมเป็นข้อความ, None = ทำ diff ไม่ได้ (ใหญ่/ไบนารี)
    script=True: ห้ามตัด — แสดงครบไม่ได้ = ReviewTooLarge (ไม่ออก token)"""
    size = len(content.encode("utf-8"))
    sha = _sha(content)
    head = ["[write] %s" % ("เขียนทับไฟล์เดิมทั้งไฟล์" if exists else "สร้างไฟล์สคริปต์/โปรแกรมใหม่ (รันได้)"),
            "path: %s" % guard.review_oneline(p),
            "ขนาดใหม่: %s (%d ไบต์) · sha256 %s…" % (_human(size), size, sha[:16])]
    if exists:
        head.append("ไฟล์เดิม: %s · sha256 %s… — ถูกแทนที่ทั้งไฟล์ (เก็บ checkpoint ไว้ undo ได้)"
                    % (_human(old_size), (old_sha or "?")[:16]))
    numbered = guard.review_numbered(content)
    if _review_fits_whole(numbered, content):
        return "\n".join(head + ["----- เนื้อหาใหม่ทั้งไฟล์ %d บรรทัด = สิ่งที่จะเขียนจริง -----" % len(numbered)]
                         + numbered + ["----- จบเนื้อหา (ครบ %d บรรทัด) -----" % len(numbered)])
    if exists and old_text is not None and size <= DIFF_MAX_BYTES:
        block, omitted = _diff_block(
            "เนื้อหาใหญ่เกินจะแสดงทั้งไฟล์: unified diff เทียบไฟล์เดิม (ไม่เกิน %d บรรทัด)"
            % guard.REVIEW_BLOCK_MAX_LINES, _review_diff(old_text, content, p), sha)
        if script and omitted:
            raise _script_too_large(p, "diff ของการเขียนทับ")
        return "\n".join(head + block)
    if script:
        raise _script_too_large(p, "เนื้อหา" if not exists else "เนื้อหา (ทำ diff กับไฟล์เดิมไม่ได้)")
    body, _omitted = guard.review_capped(numbered, sha)
    why = ("ทำ diff กับไฟล์เดิมไม่ได้ (ใหญ่/ไบนารี) " if exists else "") + "เนื้อหาใหญ่เกินจะแสดงทั้งไฟล์"
    return "\n".join(head + ["----- %s: เนื้อหาใหม่ช่วงต้น (ไม่เกิน %d บรรทัด) -----"
                             % (why, guard.REVIEW_BLOCK_MAX_LINES), body, "----- จบส่วนที่แสดง -----"])


def _edit_review(p: str, count: int, replace_all: bool, old_string: str, new_string: str,
                 text: str, new_text: str, small: bool, script: bool = False) -> str:
    """review ของ edit_file: path + unified diff ของสิ่งที่จะเปลี่ยนจริง (ไฟล์ใหญ่เกินทำ diff = ข้อความเดิม/ใหม่เต็ม)
    script=True: diff/ข้อความที่ต้องตัดทิ้ง = ReviewTooLarge (ไม่ออก token)"""
    head = ["[edit] แก้ไขไฟล์: แทนที่ข้อความ %d ตำแหน่ง%s" % (count, " (replace_all)" if replace_all else ""),
            "path: %s" % guard.review_oneline(p),
            "sha256 ทั้งไฟล์: ก่อนแก้ %s… -> หลังแก้ %s…" % (_sha(text)[:16], _sha(new_text)[:16])]
    if small:
        block, omitted = _diff_block("unified diff = สิ่งที่จะเปลี่ยนจริง",
                                     _review_diff(text, new_text, p), _sha(new_text))
        if script and omitted:
            raise _script_too_large(p, "diff ของการแก้ไข")
        return "\n".join(head + block)
    half_l, half_c = guard.REVIEW_BLOCK_MAX_LINES // 2, guard.REVIEW_BLOCK_MAX_CHARS // 2
    old_b, o_omit = guard.review_capped(guard.review_numbered(old_string), _sha(old_string), half_l, half_c)
    new_b, n_omit = guard.review_capped(guard.review_numbered(new_string), _sha(new_string), half_l, half_c)
    if script and (o_omit or n_omit):
        raise _script_too_large(p, "ข้อความเดิม/ใหม่ของการแก้ไข")
    return "\n".join(head + ["(ไฟล์ใหญ่เกิน %d MB ทำ diff ไม่ได้ — แสดงข้อความที่ถูกแทนที่และข้อความใหม่)"
                             % (DIFF_MAX_BYTES // 1_000_000),
                             "----- ข้อความเดิม (old) -----", old_b,
                             "----- ข้อความใหม่ (new) -----", new_b, "----- จบ -----"])


def _exec_review(cmd: str, workdir: str, timeout) -> str:
    """review ของ run: คำสั่งเต็มทุกตัวอักษร + cwd + timeout ที่จะใช้จริง (ค่าเดียวกับตอนรัน)"""
    try:
        t = "%d วินาที" % max(5, min(int(timeout), 600))
    except (TypeError, ValueError):
        # ค่าจากโมเดล: ถ้ามี \n ต้องไม่แตกเป็นบรรทัดใหม่ที่ปลอมเป็นบรรทัดคำสั่งได้ (review_oneline)
        t = "ค่าไม่ถูกต้อง (%s) — คำสั่งจะล้มก่อนรัน" % guard.review_oneline(str(timeout)[:40])
    body = guard.review_numbered(cmd)
    return "\n".join(["[run] รันคำสั่งระบบผ่าน cmd.exe (shell)", "cwd: %s" % guard.review_oneline(workdir),
                      "timeout: %s" % t,
                      "----- คำสั่งเต็ม %d บรรทัด = สิ่งที่จะรันจริง -----" % len(body)]
                     + body + ["----- จบคำสั่ง -----"])


def _read_small(p: str):
    """ไบต์ของไฟล์สำหรับทำ diff — None ถ้าไม่มีไฟล์หรือใหญ่เกินจะทำ diff"""
    try:
        if not os.path.isfile(p) or os.path.getsize(p) > DIFF_MAX_BYTES:
            return None
        with open(p, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _checkpoints_denied() -> str:
    return ("ปฏิเสธ: โฟลเดอร์ checkpoints เป็นประวัติสำหรับ undo แก้ผ่านเครื่องมือไม่ได้ "
            "(ดูได้ด้วย checkpoints / ย้อนด้วย undo)")


def list_checkpoints(path: str = "", limit: int = 30, **_) -> str:
    """รายการ checkpoint ของโปรเจกต์นี้ ใหม่สุดก่อน ใส่ path = เฉพาะไฟล์นั้น"""
    try:
        want = ""
        if str(path or "").strip():
            want = os.path.normcase(guard.check_read(path))
        root = _cp_root()
        guard.audit("list_checkpoints", {"path": want, "project": guard.current_project()})
        try:
            lim = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            lim = 30
        rows, total = [], 0
        for e in _cp_entries(root):
            if want and os.path.normcase(str(e.get("path") or "")) != want:
                continue
            total += 1
            if len(rows) >= lim:
                continue
            before = ("(ไม่มีไฟล์)" if not e.get("existed")
                      else _human(e.get("size_before") or 0))
            after = "(ไม่มีไฟล์)" if e.get("size_after") is None else _human(e["size_after"])
            flags = []
            if e.get("existed") and not e.get("blob"):
                flags.append("ไม่มีสำเนา:%s" % (e.get("note") or "?"))
            if e.get("undone_by"):
                flags.append("ย้อนแล้ว")
            if e.get("restores"):
                flags.append("ย้อนจาก %s" % e["restores"])
            rows.append("%s  %s  %-10s %s  %s -> %s%s" % (
                e.get("id"), e.get("ts"), e.get("tool"), e.get("path"), before, after,
                ("  [%s]" % ", ".join(flags)) if flags else ""))
        if not rows:
            return ("ยังไม่มี checkpoint%s ของโปรเจกต์นี้"
                    % ((" ของ %s" % path) if want else ""))
        head = "checkpoint ของโปรเจกต์ %s (%d รายการ%s ใหม่สุดก่อน)" % (
            guard.current_project() or "default", total,
            (", แสดง %d" % len(rows)) if total > len(rows) else "")
        tail = ("ย้อนไฟล์: undo path=<ไฟล์> (ย้อน checkpoint ล่าสุดที่ยังไม่ถูกย้อน) "
                "หรือ undo path=<ไฟล์> id=<id> เพื่อเลือกจุดเอง — ต้องยืนยันก่อนเสมอ")
        return "\n".join([head] + rows + ["", tail])
    except Exception as exc:
        return _err(exc)


def undo_file(path: str = "", id: str = "", confirm_token: str = "", **_) -> str:   # noqa: A002
    """ย้อนไฟล์กลับเป็นสถานะใน checkpoint (ล่าสุดที่ยังไม่ถูกย้อน หรือ id ที่ระบุ) — ยืนยันสองขั้นเสมอ

    token ผูกกับ path + checkpoint + sha256 ของเนื้อปัจจุบัน + sha256 ของเนื้อที่จะคืน
    ถ้าไฟล์เปลี่ยนระหว่างรออนุมัติ token ใช้ไม่ได้ (ผู้ใช้อนุมัติ diff ที่เห็น ไม่ใช่อย่างอื่น)
    """
    try:
        p = guard.check_write(path)
        if in_checkpoints(p):
            return _checkpoints_denied()
        f = Path(p)
        if f.is_dir():
            return "ผิดพลาด: %s เป็นโฟลเดอร์ undo ได้เฉพาะไฟล์" % p
        root = _cp_root()
        want, cid = os.path.normcase(p), str(id or "").strip()
        target = None
        for e in _cp_entries(root):
            if os.path.normcase(str(e.get("path") or "")) != want:
                continue
            if cid:
                if e.get("id") == cid:
                    target = e
                    break
                continue
            if e.get("tool") == "undo" or e.get("undone_by"):
                continue                 # ค่าเริ่มต้น: ถอยไปทีละขั้น ไม่เด้งกลับไปมา
            target = e
            break
        if target is None:
            return ("ไม่พบ checkpoint%s ของ %s ในโปรเจกต์นี้ — ดูรายการด้วย checkpoints path=<ไฟล์>"
                    % ((" id=%s" % cid) if cid else " ที่ยังย้อนได้", p))
        if target.get("existed") and not target.get("blob"):
            return ("checkpoint %s ไม่มีสำเนาไฟล์เดิม (%s) จึงย้อนไม่ได้"
                    % (target.get("id"), target.get("note") or "ไม่ได้เก็บ"))
        data = None
        if target.get("existed"):
            data = (root / target["id"] / "before.bin").read_bytes()
            if _sha_bytes(data) != target.get("sha256_before"):
                return "checkpoint %s เสียหาย (sha256 ไม่ตรงกับ journal) จึงไม่ย้อน" % target.get("id")
        cur = None
        if f.is_file():
            if f.stat().st_size > CHECKPOINT_FILE_CAP:
                return ("ไฟล์ปัจจุบันใหญ่เกิน %d MB เก็บสำเนาก่อนย้อนไม่ได้ จึงไม่ย้อน (กันข้อมูลหาย)"
                        % (CHECKPOINT_FILE_CAP >> 20))
            cur = f.read_bytes()
        if data is None and cur is None:
            return "ไม่มีอะไรให้ย้อน: ตอนนี้ไม่มีไฟล์ %s อยู่แล้ว ตรงกับสถานะก่อน checkpoint" % p
        cur_sha = _sha_bytes(cur) if cur is not None else "missing"
        new_sha = _sha_bytes(data) if data is not None else "absent"
        if cur_sha == new_sha:
            return "ไม่มีอะไรให้ย้อน: เนื้อไฟล์ตอนนี้ตรงกับ checkpoint %s อยู่แล้ว" % target.get("id")
        action = "undo_file:%s" % p.lower()
        detail = "%s\ncheckpoint=%s\ncurrent=%s\nrestore=%s" % (p, target.get("id"), cur_sha, new_sha)
        if not confirm_token:
            if data is None:
                what = "ไฟล์นี้ถูกสร้างใหม่ใน checkpoint นั้น — ย้อน = ย้ายไฟล์ออกไปเก็บใน checkpoint (ไม่ลบทิ้ง)"
            elif cur is None:
                what = "ตอนนี้ไม่มีไฟล์ — ย้อน = สร้างไฟล์กลับมาด้วยเนื้อเดิม"
            else:
                what = "คืนเนื้อไฟล์เป็นสถานะก่อน %s" % target.get("tool")
            drift = ""
            if target.get("sha256_after") and cur_sha != target.get("sha256_after") \
                    and target.get("tool") != "undo":
                drift = "\n  คำเตือน: ไฟล์ถูกแก้อีกหลัง checkpoint นี้ การย้อนจะทับการแก้นั้นด้วย (แต่เก็บสำเนาไว้ก่อน)"
            human = "%s\n  checkpoint: %s (%s เมื่อ %s)\n  %s%s\n%s" % (
                p, target.get("id"), target.get("tool"), target.get("ts"), what, drift,
                unified_diff(_diff_text(cur), _diff_text(data), p, DIFF_PREVIEW_LINES))
            # R1: review = path + checkpoint + diff "ปัจจุบัน -> สิ่งที่จะคืน" (ตัดที่เพดานพร้อม hash)
            rv = ["[undo] ย้อนไฟล์ตาม checkpoint %s (%s เมื่อ %s)"
                  % (target.get("id"), target.get("tool"), target.get("ts")),
                  "path: %s" % guard.review_oneline(p), what.replace("\n", " ") + drift.replace("\n", " "),
                  "sha256: ปัจจุบัน %s -> หลังย้อน %s" % (cur_sha[:16], new_sha[:16])]
            cur_t, new_t = _diff_text(cur), _diff_text(data)
            if cur_t is None or new_t is None:
                rv.append("(ไม่แสดง diff: ไฟล์ใหญ่เกิน %d MB หรือเป็นไฟล์ไบนารี)" % (DIFF_MAX_BYTES // 1_000_000))
            else:
                rv += _diff_block("unified diff: ปัจจุบัน -> หลังย้อน", _review_diff(cur_t, new_t, p),
                                  new_sha if data is not None else "absent")[0]
            tok = guard.need_confirm(action, detail, review="\n".join(rv))
            return guard.confirm_hint(tok, "ย้อนไฟล์กลับตาม checkpoint (undo)", human)
        if not guard.consume_confirm(confirm_token, action, detail):
            return _bad_token_msg()
        # เก็บสถานะปัจจุบันก่อนเสมอ ถ้าเก็บไม่ได้ = ไม่ย้อน (การย้อนต้องไม่ทำให้ข้อมูลหาย)
        new_cp = checkpoint_before(p, "undo", move=(data is None))
        if cur is not None and not new_cp.get("blob"):
            return ("ยังไม่ได้ย้อน: เก็บสำเนาสถานะปัจจุบันไม่สำเร็จ (%s) จึงไม่แตะไฟล์"
                    % (new_cp.get("note") or "ไม่ทราบสาเหตุ"))
        new_cp["restores"] = target.get("id")
        if data is not None:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        checkpoint_after(new_cp, p)
        target["undone_by"] = new_cp.get("id")
        try:
            _journal_write(root / target["id"], target)
        except OSError:
            pass
        guard.audit("undo_file", {"path": p, "checkpoint": target.get("id"),
                                  "saved_as": new_cp.get("id"), "removed": data is None})
        if data is None:
            done = "ย้อนแล้ว: ย้าย %s ออกไปเก็บใน checkpoint %s (ไฟล์ถูกสร้างใหม่ในจุดที่ย้อน)" % (
                p, new_cp.get("id"))
        else:
            done = "ย้อนแล้ว %s กลับเป็นสถานะก่อน %s เมื่อ %s (%s)" % (
                p, target.get("tool"), target.get("ts"), _human(len(data)))
        return (done + "\nสถานะก่อนย้อนเก็บไว้ที่ checkpoint %s — ถ้าต้องการกลับไปแบบนั้น: "
                "undo path=<ไฟล์เดิม> id=%s" % (new_cp.get("id"), new_cp.get("id")))
    except Exception as exc:
        return _err(exc)
# ======================================================== จบส่วน checkpoints / diff / undo


def write_file(path: str, content: str = "", confirm_token: str = "", **_) -> str:
    """เขียนไฟล์ — ทับไฟล์เดิม หรือสร้างไฟล์สคริปต์/โปรแกรมใหม่ ต้องยืนยันสองขั้น

    ทำไมไฟล์สคริปต์ใหม่ต้องยืนยัน (V3/V4): เดิมสร้าง .py ได้ทันทีแล้วสั่ง `python x.py`
    ซึ่งนับเป็นคำสั่งอ่านอย่างเดียว = รันโค้ดอะไรก็ได้โดยผู้ใช้ไม่ได้อนุมัติสักครั้ง
    token ผูกกับ path + hash ของเนื้อหา อนุมัติเนื้อหาหนึ่งแล้วเอาไปเขียนอีกเนื้อหาไม่ได้
    """
    try:
        content = "" if content is None else str(content)
        p = guard.check_write(path)
        if in_checkpoints(p):                                   # mcp-exec: ประวัติ undo แก้ไม่ได้
            return _checkpoints_denied()
        f = Path(p)
        if f.is_dir():
            return "ผิดพลาด: %s เป็นโฟลเดอร์ ไม่ใช่ไฟล์" % p
        exists = f.exists()
        script = guard.is_script_path(p)
        size = len(content.encode("utf-8"))
        if exists or script:
            action = "write_file:%s" % p.lower()
            # รอบ FIXER: ผูกกับ sha256 ของไฟล์เดิมด้วย (แบบเดียวกับ edit/undo/make_file) — review ของการทับไฟล์ใหญ่
            # คือ diff เทียบไฟล์ "ตอนออก token" ถ้าไฟล์ถูกแก้หลังจากนั้น การยืนยันเดิมจะทับการแก้ที่ไม่เคยอยู่ใน diff
            # ที่คนอนุมัติทิ้งเงียบๆ ตอนนี้ไฟล์เปลี่ยน = token ใช้ไม่ได้ ต้องขอ review ใหม่
            old_sha = _file_sha(p) if exists else "missing"
            detail = "%s\nsha256=%s\nbytes=%d\nexists=%s\nbefore=%s" % (p, _sha(content), size, exists, old_sha)
            if not confirm_token:
                old_size = f.stat().st_size if exists else 0
                old_text = (_diff_text(_read_small(p)) if old_size <= DIFF_MAX_BYTES else None) \
                    if exists else ""
                if exists:
                    label = "เขียนทับไฟล์"
                    human = "%s\n  ขนาดเดิม %s -> ใหม่ %s\n%s" % (
                        p, _human(old_size), _human(size),
                        unified_diff(old_text, content, p, DIFF_PREVIEW_LINES))
                else:
                    label = "สร้างไฟล์สคริปต์/โปรแกรมใหม่ (รันได้)"
                    human = "%s (%s)\n  เนื้อหาตอนต้น: %s" % (p, _human(size), _snippet(content))
                # R1: review = path + เนื้อหาใหม่ทั้งไฟล์ (ใหญ่: ขนาด + sha256 + diff แบบตัดพร้อมบอกจำนวนที่ไม่แสดง)
                tok = guard.need_confirm(action, detail,
                                         review=_write_review(p, content, exists, old_size, old_text,
                                                              script=script, old_sha=old_sha))
                return guard.confirm_hint(tok, label, human)
            if not guard.consume_confirm(confirm_token, action, detail):
                return _bad_token_msg()
        f.parent.mkdir(parents=True, exist_ok=True)
        # mcp-exec: เก็บ checkpoint (และเนื้อเดิมไว้ทำ diff) ก่อนลงมือเขียนจริงเสมอ
        old_text = _diff_text(_read_small(p)) if exists else ""
        if exists and os.path.getsize(p) > DIFF_MAX_BYTES:
            old_text = None
        cp = checkpoint_before(p, "write_file")
        f.write_text(content, encoding="utf-8")
        checkpoint_after(cp, p)
        guard.audit("write_file", {"path": p, "bytes": size, "overwrote": exists,
                                   "script": script, "checkpoint": cp.get("id")})
        diff = unified_diff(old_text, content if size <= DIFF_MAX_BYTES else None, p,
                            DIFF_MAX_LINES if exists else DIFF_NEW_FILE_LINES)
        return "เขียนแล้ว %s (%s)\n%s\n%s" % (p, _human(size), checkpoint_note(cp), diff)
    except Exception as exc:
        return _err(exc)


def edit_file(path: str, old_string: str = "", new_string: str = "",
              replace_all: bool = False, confirm_token: str = "", **_) -> str:
    """แทนที่ข้อความในไฟล์ ต้องตรงแบบเป๊ะ ไม่กำกวม และต้องยืนยันสองขั้นเสมอ

    เดิม edit_file ลงมือทันที (V3) โมเดลจึงแก้ guard.py / hub.py / สคริปต์ launcher ได้เงียบๆ
    ตอนนี้ขอ confirm_token ทุกครั้ง ผูกกับ path + hash ของ old/new/replace_all + เนื้อไฟล์ก่อนแก้
    ถ้าไฟล์เปลี่ยนระหว่างรออนุมัติ token จะใช้ไม่ได้ (ผู้ใช้อนุมัติสิ่งที่เห็น ไม่ใช่สิ่งอื่น)
    """
    try:
        p = guard.check_write(path)
        if in_checkpoints(p):                                   # mcp-exec: ประวัติ undo แก้ไม่ได้
            return _checkpoints_denied()
        f = Path(p)
        if not f.exists():
            return "ไม่พบไฟล์: %s" % p
        text = f.read_text(encoding="utf-8", errors="replace")
        old_string = "" if old_string is None else str(old_string)
        new_string = "" if new_string is None else str(new_string)
        if not old_string:
            return "ต้องระบุ old_string"
        n = text.count(old_string)
        if n == 0:
            return "ไม่พบข้อความที่ต้องการแทนที่ในไฟล์ (ต้องตรงทุกตัวอักษรรวมช่องว่าง)"
        if n > 1 and not replace_all:
            return ("พบ %d ตำแหน่ง ข้อความกำกวม — เพิ่มบริบทรอบๆ ให้ยาวขึ้น "
                    "หรือส่ง replace_all=true" % n)
        count = n if replace_all else 1
        action = "edit_file:%s" % p.lower()
        detail = "%s\nold=%s\nnew=%s\nall=%s\nbefore=%s" % (
            p, _sha(old_string), _sha(new_string), bool(replace_all), _sha(text))
        new_text = text.replace(old_string, new_string)
        small = len(text) <= DIFF_MAX_BYTES and len(new_text) <= DIFF_MAX_BYTES
        if not confirm_token:
            human = "%s (%d ตำแหน่ง)\n  เดิม: %s\n  ใหม่: %s\n%s" % (
                p, count, _snippet(old_string), _snippet(new_string),
                unified_diff(text if small else None, new_text, p, DIFF_PREVIEW_LINES))
            tok = guard.need_confirm(action, detail, review=_edit_review(
                p, count, bool(replace_all), old_string, new_string, text, new_text, small,
                script=guard.is_script_path(p)))
            return guard.confirm_hint(tok, "แก้ไขไฟล์", human)
        if not guard.consume_confirm(confirm_token, action, detail):
            return _bad_token_msg()
        cp = checkpoint_before(p, "edit_file")                  # mcp-exec: สำเนาก่อนแก้เสมอ
        f.write_text(new_text, encoding="utf-8")
        checkpoint_after(cp, p)
        guard.audit("edit_file", {"path": p, "count": count, "checkpoint": cp.get("id")})
        return "แก้ไขแล้ว %s (%d ตำแหน่ง)\n%s\n%s" % (
            p, count, checkpoint_note(cp), unified_diff(text if small else None, new_text, p))
    except Exception as exc:
        return _err(exc)


# ------------------------------------------------------------------- search
def file_glob_search(pattern: str, path: str = "", **_) -> str:
    """ค้นไฟล์ตามรูปแบบชื่อ เช่น **/*.py"""
    try:
        root = guard.check_read(path or "C:\\")
        guard.audit("file_glob_search", {"root": root, "pattern": pattern})
        base = Path(root)
        if not base.is_dir():
            base = base.parent
        hits, skipped = [], 0
        for item in base.rglob("*"):
            if len(hits) >= MAX_HITS:
                break
            try:
                if not item.is_file():
                    continue
                rel = str(item.relative_to(base))
                if not (fnmatch.fnmatch(rel.lower(), pattern.lower())
                        or fnmatch.fnmatch(item.name.lower(), pattern.lower())):
                    continue
                guard.check_read(str(item))
                hits.append(str(item))
            except guard.Denied:
                skipped += 1
            except (OSError, ValueError):
                continue
        if not hits:
            return "ไม่พบไฟล์ที่ตรงกับ %s ใน %s" % (pattern, root)
        out = "\n".join(hits)
        if skipped:
            out += "\n\n(ข้าม %d ไฟล์ที่อยู่ในพื้นที่ต้องห้าม)" % skipped
        if len(hits) >= MAX_HITS:
            out += "\n(แสดง %d รายการแรก)" % MAX_HITS
        return out
    except Exception as exc:
        return _err(exc)


def grep_search(pattern: str, path: str = "", glob: str = "*",
                ignore_case: bool = True, **_) -> str:
    """ค้นข้อความในไฟล์ด้วย regular expression"""
    try:
        root = guard.check_read(path or "C:\\")
        guard.audit("grep_search", {"root": root, "pattern": pattern, "glob": glob})
        try:
            rx = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as exc:
            return "รูปแบบ regex ไม่ถูกต้อง: %s" % exc
        base = Path(root)
        if base.is_file():
            files = [base]
        else:
            files = (f for f in base.rglob(glob) if f.is_file())
        hits, scanned, skipped = [], 0, 0
        for f in files:
            if len(hits) >= MAX_HITS or scanned > 20000:
                break
            scanned += 1
            try:
                guard.check_read(str(f))
                if f.stat().st_size > 5_000_000:
                    continue
                with f.open("rb") as fh:
                    if _is_binary(fh.read(2048)):
                        continue
                for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        hits.append("%s:%d: %s" % (f, i, line.strip()[:MAX_LINE]))
                        if len(hits) >= MAX_HITS:
                            break
            except guard.Denied:
                skipped += 1
            except (OSError, ValueError):
                continue
        if not hits:
            return "ไม่พบ %s (ค้น %d ไฟล์)" % (pattern, scanned)
        out = "\n".join(hits)
        if skipped:
            out += "\n\n(ข้าม %d ไฟล์ที่อยู่ในพื้นที่ต้องห้าม)" % skipped
        return out
    except Exception as exc:
        return _err(exc)


# ---------------------------------------------------------------- shell
# คำสั่งอ่านอย่างเดียวที่รันได้ทันทีโดยไม่ต้องยืนยัน — ตรวจ "ระดับอาร์กิวเมนต์" ไม่ใช่แค่ชื่อคำสั่ง
#
# ทำไมต้องละเอียดขนาดนี้ (V4 จากการ audit): ของเดิมดูแค่คำแรก จึงปล่อยผ่าน
#   python script.py / python -m pip install / node -e / npm run / curl -o / wmic process call create
#   git -c core.pager=... log / git clone / git config  ซึ่งทั้งหมดคือ "รันโค้ดอะไรก็ได้" หรือเขียนดิสก์
# ตอนนี้คำสั่งที่ไม่อยู่ในรายการข้างล่าง "แบบตรงอาร์กิวเมนต์" ต้องผ่าน confirm_token ทั้งหมด
SAFE_CMDS = {"dir", "type", "echo", "where", "whoami", "hostname", "date", "time", "ver",
             "vol", "systeminfo", "tasklist", "ipconfig", "findstr", "tree", "nvidia-smi",
             "git", "python", "python3", "py", "pip", "pip3", "node", "npm"}
# คำสั่งอันตรายที่ปฏิเสธเสมอ ไม่มีทางยืนยันผ่าน
# หมายเหตุ (แก้รอบ audit): เดิม \bformat จับคำว่า "format" ที่ไหนก็ได้ในคำสั่ง จึงปฏิเสธ
#   nvidia-smi --format=csv และ git log --format=... ทั้งที่เป็นคำสั่งอ่านอย่างเดียวตามสัญญา C5
#   ตอนนี้จับ format เฉพาะตอนเป็น "โปรแกรมที่ถูกเรียก" (ต้นคำสั่งหรือหลังตัวคั่น & | ;)
FORBIDDEN = re.compile(
    r"((^|[&|;]\s*)format(\.com)?(\s|$)|"
    r"\b(diskpart|bcdedit|vssadmin|cipher\s*/w|reg\s+(delete|add|import|load|restore|unload)|"
    r"regedit|net\s+user|sc\s+(delete|config|create)|takeown|icacls|"
    r"schtasks\s+/(create|change|delete)|"
    r"(set|new)-itemproperty\b.*\\run(once)?\b|(add|set)-mppreference|"
    r"netsh\s+(advfirewall|firewall)|wevtutil\s+cl|clear-eventlog|"
    r"rd\s+/s\s+/q\s+[a-z]:\\?\s*$|del\s+/[sqf]+\s+[a-z]:\\?\s*$|"
    r"rm\s+-rf\s+/|shutdown|Remove-Item.*-Recurse.*-Force.*[A-Z]:\\?\s*$))",
    re.IGNORECASE)

# อักขระที่ทำให้ cmd.exe ทำมากกว่า "รันหนึ่งโปรแกรมด้วยอาร์กิวเมนต์ตรงๆ"
# ตรวจทั้งสตริงไม่สนเครื่องหมายคำพูด เพราะ cmd ไม่มี escape ใน "..." (เช่น "\" & calc & ")
# และไม่ถือ '...' เป็นเครื่องหมายคำพูดเลย — ระวังไว้ก่อนดีกว่าตีความผิด
_META_ANYWHERE = set("&|<>^%!\r\n\x00`")
_META_OUTSIDE_QUOTES = set("()")


def _argv(cmd: str) -> list[str]:
    """แตกคำสั่งตามกฎ CommandLineToArgvW (แบบที่โปรแกรมบน Windows ได้รับจริง)"""
    argv, buf, in_q, bs, has = [], [], False, 0, False
    for ch in cmd:
        if ch == "\\":
            bs += 1
            continue
        if ch == '"':
            buf.extend("\\" * (bs // 2))
            if bs % 2:
                buf.append('"')
            else:
                in_q = not in_q
            bs, has = 0, True
            continue
        buf.extend("\\" * bs)
        bs = 0
        if ch in " \t" and not in_q:
            if buf or has:
                argv.append("".join(buf))
                buf, has = [], False
            continue
        buf.append(ch)
        has = True
    buf.extend("\\" * bs)
    if buf or has:
        argv.append("".join(buf))
    return argv


def _has_meta(cmd: str) -> bool:
    if any(c in _META_ANYWHERE for c in cmd):
        return True
    in_q = False
    for c in cmd:
        if c == '"':
            in_q = not in_q
        elif not in_q and c in _META_OUTSIDE_QUOTES:
            return True
    return False


def _switch_letters(arg: str) -> str:
    """ตัวอักษรของสวิตช์แบบ /x ของ cmd (รองรับการรวม เช่น /spin) ส่วนหลัง : ไม่นับ"""
    return arg[1:].split(":", 1)[0].lower() if arg.startswith("/") else ""


# หมายเหตุ (แก้รอบ audit F12): git อ่าน "เนื้อไฟล์" จาก object store ได้หลายทาง ซึ่งไม่ผ่าน blocked_globs
# เลย ทดสอบใน repo จำลองที่ commit .env/credentials.json ไว้ คำสั่งเหล่านี้พิมพ์เนื้อไฟล์ต้องห้ามออกมา
# โดยไม่ต้องยืนยัน:  git show / git log -p / git diff / git show :0:credentials.json /
#   git log -L1,1:.env / git show <blob-id ที่ได้จาก ls-tree>  (git grep, cat-file, blame ก็เช่นกัน)
# ตอนนี้แต่ละ subcommand มี allowlist ของตัวเลือก — รันทันทีได้เฉพาะรูปที่แสดงแค่ชื่อไฟล์/สถิติ/ข้อความ commit
#   * show/diff ต้องมีตัวเลือกแบบ "ไม่พิมพ์ patch" (--stat, --name-only ...) ยกเว้น show <rev>:<path>
#     ที่ guard.git_revpath_violation ตรวจ path แล้ว (path ต้องห้าม = ปฏิเสธเด็ดขาดแม้ยืนยัน)
#   * log/whatchanged/reflog/shortlog: ตัวเลือกที่ทำให้พิมพ์เนื้อไฟล์ (-p -u -L -S -G --cc -m
#     --word-diff ...) ไม่อยู่ในรายการ จึงต้องยืนยัน (-S/-G คือค้นเนื้อไฟล์ = ใช้ทายเนื้อทีละตัวได้)
#   * status -v พิมพ์ diff ของไฟล์ที่ stage ไว้ จึงต้องยืนยัน, blame/grep/cat-file ต้องยืนยันเสมอ
# รูปที่ต้องยืนยัน = ผู้ใช้เห็นคำสั่งก่อน ไม่ใช่ปฏิเสธถาวร ส่วน <rev>:<path> ต้องห้ามปฏิเสธเสมอ
_GIT_RO = {"status", "log", "diff", "show", "rev-parse", "ls-files", "ls-tree",
           "describe", "shortlog", "count-objects", "version", "branch",
           "tag", "remote", "stash", "reflog", "show-ref", "for-each-ref", "name-rev",
           "merge-base", "rev-list", "whatchanged"}
# ตัวเลือกที่จำกัดผลของ show/diff ให้เหลือแค่ชื่อไฟล์/สถิติ ไม่มีเนื้อ patch
_GIT_NOPATCH = {"--stat", "--shortstat", "--numstat", "--name-only", "--name-status", "--summary",
                "--compact-summary", "-s", "--no-patch", "--dirstat", "--raw", "--quiet"}
_GIT_NOPATCH_PREFIX = ("--stat=", "--dirstat=")
# ตัวเลือกของ log/show/diff ที่ไม่ทำให้พิมพ์เนื้อไฟล์และไม่รันโปรแกรมอื่น (ตัวพิมพ์เล็กใหญ่มีความหมาย:
# -C = หาไฟล์ที่คัดลอก แต่ -c = combined diff ซึ่งพิมพ์เนื้อไฟล์ / -M = หาการเปลี่ยนชื่อ แต่ -m = diff ของ merge)
_GIT_VIEW_FLAGS = {
    "--oneline", "--graph", "--all", "--branches", "--tags", "--remotes", "--decorate",
    "--no-decorate", "--first-parent", "--no-merges", "--merges", "--reverse", "--abbrev-commit",
    "--no-abbrev-commit", "--no-abbrev", "--relative-date", "--topo-order", "--date-order",
    "--author-date-order", "--no-walk", "--boundary", "--left-right", "--cherry-pick",
    "--cherry-mark", "--cherry", "--ancestry-path", "--simplify-by-decoration", "--source",
    "--parents", "--children", "--no-color", "--mailmap", "--use-mailmap", "--no-mailmap",
    "--no-use-mailmap", "--no-notes", "-g", "--walk-reflogs", "--not", "-i",
    "--regexp-ignore-case", "--invert-grep", "--all-match", "-E", "--extended-regexp", "-F",
    "--fixed-strings", "--basic-regexp", "-P", "--perl-regexp", "--follow", "--no-renames", "-M",
    "-C", "--find-renames", "--find-copies", "--find-copies-harder", "-z", "--full-history",
    "--dense", "--sparse", "--simplify-merges", "--show-pulls", "--in-commit-order",
    "--expand-tabs", "--no-expand-tabs", "--pretty", "--no-ext-diff", "--no-textconv", "--cached",
    "--staged", "-R", "--relative", "--no-relative", "--merge-base", "--minimal", "--patience",
    "--histogram", "--full-index", "--i-still-use-this"}
_GIT_VIEW_PREFIX = (
    "--max-count=", "--skip=", "--since=", "--after=", "--until=", "--before=", "--author=",
    "--committer=", "--grep=", "--date=", "--pretty=", "--format=", "--abbrev=", "--decorate=",
    "--exclude=", "--glob=", "--branches=", "--tags=", "--remotes=", "--since-as-filter=",
    "--diff-filter=", "--find-renames=", "--find-copies=", "--relative=", "--decorate-refs=",
    "--decorate-refs-exclude=", "--max-parents=", "--min-parents=", "--stat-width=",
    "--stat-name-width=", "--stat-count=", "--stat-graph-width=")
_GIT_STATUS_FLAGS = {"-s", "--short", "-b", "--branch", "--long", "--show-stash", "-z",
                     "--no-column", "--column", "--ahead-behind", "--no-ahead-behind", "--renames",
                     "--no-renames", "--porcelain", "-u", "--untracked-files", "--ignored"}
_GIT_STATUS_PREFIX = ("--porcelain=", "-u", "--untracked-files=", "--ignored=",
                      "--ignore-submodules", "--column=", "--find-renames")
_GIT_SHORTLOG_FLAGS = {"-n", "--numbered", "-s", "--summary", "-e", "--email", "-c", "--committer"}
_HEX_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")
# ชื่อ rev ที่ "เป็น commit แน่ๆ" สำหรับ show แบบ --stat: ไม่มี ':' '{' และไม่ใช่เลขฐานสิบหกล้วน
# (เลขฐานสิบหกล้วนอาจเป็น blob id จาก ls-tree — git show --stat <blob> ยังพิมพ์เนื้อ blob ออกมา)
_SAFE_REV_RE = re.compile(r"^[A-Za-z0-9._/~^!+\-]+$")
_STASH_REF_RE = re.compile(r"^(stash@\{\d+\}|\d+)$")


def _git_view_args(args: list[str], extra_flags=frozenset()) -> tuple | None:
    """แยกอาร์กิวเมนต์ของ log/show/diff เป็น (positionals, paths หลัง --, มีตัวเลือก no-patch ไหม)
    คืน None ถ้ามีตัวเลือกที่ไม่อยู่ใน allowlist (= ไม่ใช่อ่านอย่างเดียว ต้องยืนยัน)"""
    pos, paths, nopatch, after_dd, i = [], [], False, False, 0
    while i < len(args):
        a = args[i]
        if after_dd:
            paths.append(a)
        elif a == "--":
            after_dd = True
        elif a.startswith("-") and a != "-":
            if a in _GIT_NOPATCH or a.startswith(_GIT_NOPATCH_PREFIX):
                nopatch = True
            elif (a in _GIT_VIEW_FLAGS or a in extra_flags or a.startswith(_GIT_VIEW_PREFIX)
                  or re.match(r"^-\d+$", a) or re.match(r"^-n\d+$", a)):
                pass
            elif a == "-n" and i + 1 < len(args) and args[i + 1].isdigit():
                i += 1
            else:
                return None
        else:
            pos.append(a)
        i += 1
    return pos, paths, nopatch


def _ro_git_show(rest: list[str]) -> bool:
    parsed = _git_view_args(rest)
    if parsed is None:
        return False
    pos, paths, nopatch = parsed
    revpaths = [a for a in pos if guard._split_revpath(a) is not None]
    others = [a for a in pos if a not in revpaths]
    if revpaths and not others and not paths:
        return True                      # show <rev>:<path> — path ถูกตรวจโดย git_revpath_violation แล้ว
    if not nopatch:
        return False                     # show ธรรมดาพิมพ์ patch เต็มของ commit = เนื้อไฟล์ทุกไฟล์ที่แก้
    return all(_SAFE_REV_RE.match(a) and not _HEX_RE.match(a) for a in others)


def _ro_git_log(rest: list[str], extra=frozenset()) -> bool:
    return _git_view_args(rest, extra) is not None
# ตัวเลือกที่เขียนไฟล์ (--output) รันโปรแกรมอื่น (-O/--open-files-in-pager, --ext-diff, --exec)
# หรือคุยกับเซิร์ฟเวอร์ด้วยโปรแกรมที่กำหนดเอง (--upload-pack)
_GIT_BAD_PREFIX = ("--output", "--ext-diff", "--open-files-in-pager", "--exec",
                   "--upload-pack", "--receive-pack", "--config-env")
_GIT_BRANCH_FLAGS = {"-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose", "--list",
                     "-l", "--show-current", "--color", "--no-color", "--column",
                     "--no-column", "-i", "--ignore-case", "--omit-empty"}
_GIT_BRANCH_PREFIX = ("--sort=", "--format=", "--contains", "--no-contains", "--merged",
                      "--no-merged", "--points-at", "--color=", "--column=", "--abbrev")


def _ro_git(args: list[str]) -> bool:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] in ("--no-pager", "--version"):
            i += 1
            continue
        if args[i] == "-C" and i + 1 < len(args):
            i += 2                       # โฟลเดอร์ถูกตรวจด้วย _guard_command อยู่แล้ว
            continue
        return False                     # -c, --exec-path, --git-dir, -p ... ไม่ใช่อ่านอย่างเดียว
    if i >= len(args):
        return True
    sub, rest = args[i], args[i + 1:]
    if sub not in _GIT_RO:
        return False
    for a in rest:
        if a.lower().startswith(_GIT_BAD_PREFIX):
            return False
    if sub == "show":
        return _ro_git_show(rest)
    if sub == "diff":
        parsed = _git_view_args(rest)
        return parsed is not None and parsed[2]       # diff อัตโนมัติได้เฉพาะแบบสถิติ/ชื่อไฟล์
    if sub in ("log", "whatchanged"):
        return _ro_git_log(rest)
    if sub == "shortlog":
        return _ro_git_log(rest, _GIT_SHORTLOG_FLAGS)
    if sub == "status":
        return all(not a.startswith("-") or a in _GIT_STATUS_FLAGS
                   or a.startswith(_GIT_STATUS_PREFIX) for a in rest)   # ไม่มี -v (พิมพ์ diff)
    if sub in ("branch", "tag"):
        listing = any(a in ("--list", "-l") for a in rest)
        for a in rest:
            if a.startswith("-"):
                if sub == "tag" and re.match(r"^-n\d*$", a):
                    continue             # tag -n / -n5 = แสดงข้อความกำกับ ไม่ได้สร้างอะไร
                if a not in _GIT_BRANCH_FLAGS and not a.startswith(_GIT_BRANCH_PREFIX):
                    return False
            elif not listing:
                return False             # ชื่อเปล่าๆ = สร้าง branch/tag ใหม่
        return True
    if sub == "remote":
        return rest in ([], ["-v"], ["--verbose"])
    if sub == "stash":
        if rest and rest[0] == "list":
            return _ro_git_log(rest[1:])
        if rest and rest[0] == "show":
            parsed = _git_view_args([a for a in rest[1:] if not _STASH_REF_RE.match(a)])
            # stash show ค่าเริ่มต้นคือ --stat (บังคับ stash.showPatch=false ใน env ด้วย) -p ไม่อยู่ใน allowlist
            return parsed is not None and not parsed[0] and not parsed[1]
        return False
    if sub == "reflog":
        if rest and rest[0] in ("expire", "delete", "drop", "write", "exists"):
            return False
        return _ro_git_log(rest[1:] if rest and rest[0] in ("show", "list") else rest)
    return True


_NVSMI_FLAGS = {"-L", "--list-gpus", "-q", "--query", "-x", "--xml-format", "-h", "--help",
                "-u", "--unit"}
_NVSMI_PREFIX = ("--query-gpu=", "--query-compute-apps=", "--query-accounted-apps=",
                 "--format=", "--id=", "--display=", "-i=", "-d=")


def _ro_nvidia(args: list[str]) -> bool:
    i = 0
    while i < len(args):
        a = args[i]
        if a in _NVSMI_FLAGS or a.startswith(_NVSMI_PREFIX):
            i += 1
        elif a in ("-i", "-d") and i + 1 < len(args):
            i += 2
        else:
            return False                 # -f (เขียนไฟล์), -pl/-pm/-r (ตั้งค่า GPU), -l (วนไม่จบ)
    return True


_PIP_FLAGS = {"--outdated", "-o", "--uptodate", "-u", "--not-required", "-l", "--local",
              "--user", "-v", "--verbose", "-q", "--quiet", "-f", "--files", "--all",
              "--exclude-editable", "--include-editable", "--no-color",
              "--disable-pip-version-check", "--no-input", "--version", "-V", "--help", "-h"}
_PIP_PREFIX = ("--format=", "--exclude=")
_PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")


def _ro_pip(args: list[str]) -> bool:
    if args in (["--version"], ["-V"]):
        return True
    if not args or args[0] not in ("list", "show", "freeze", "check"):
        return False                     # install/uninstall/download/wheel/config/cache ...
    for a in args[1:]:
        if a.startswith("-"):
            if a not in _PIP_FLAGS and not a.startswith(_PIP_PREFIX):
                return False             # --log (เขียนไฟล์), --python, --config ...
        elif not _PKG_RE.match(a):
            return False
    return True


def _cmd_switches(args: list[str]) -> set[str]:
    """ตัวอักษรสวิตช์ของคำสั่ง cmd รวมแบบติดกัน (/s/b) และแบบมีค่า (/o:-s = o)"""
    out = set()
    for a in args:
        if a.startswith("/"):
            for part in a.split("/")[1:]:
                if part:
                    out.add(part[0].lower())
    return out


def _ro_args(head: str, args: list[str]) -> bool:
    """ตัดสินว่าอาร์กิวเมนต์ชุดนี้ของคำสั่งนี้อ่านอย่างเดียวจริงไหม (path ถูกตรวจแยกอีกชั้น)"""
    if head == "dir":
        # dir /s แบบไม่มี /b พิมพ์ "Directory of <path>" แล้วตามด้วยชื่อไฟล์เปล่าๆ ทีละบรรทัด
        # ชื่อไฟล์ในโฟลเดอร์ต้องห้าม (เช่น local-services.token ใต้ C:\LLM\secrets) จึงหลุดโดยกรองไม่ได้
        # รูป /s /b พิมพ์ path เต็มทุกบรรทัด กรองทิ้งได้แน่นอน (ดู _redact_blocked_lines) จึงยังรันทันที
        sw = _cmd_switches(args)
        return "s" not in sw or "b" in sw
    if head == "tree":
        return False                     # ผลเป็นแผนผังชื่อที่ไม่มี path เต็ม กรองชื่อในโฟลเดอร์ต้องห้ามไม่ได้
    if head in ("type", "where", "echo", "vol", "ver"):
        return True
    if head == "findstr":
        for a in args:
            letters = _switch_letters(a)
            if not letters:
                continue
            if "s" in letters or letters[:1] in ("g", "f", "d"):
                return False             # /s เดินทั้งต้นไม้ /g: /f: /d: อ่านรายชื่อไฟล์จากที่อื่น
        return True
    if head == "whoami":
        return all(a.startswith("/") for a in args)
    if head == "hostname":
        return not args                  # hostname <ชื่อ> คือพยายามเปลี่ยนชื่อเครื่อง
    if head in ("date", "time"):
        return [a.lower() for a in args] == ["/t"]   # ไม่มี /t = ถามให้ตั้งเวลาใหม่และรอ input
    if head == "systeminfo":
        return all(a.lower() in ("/fo", "table", "list", "csv", "/nh") for a in args)
    if head == "tasklist":
        return not any(a.lower() in ("/s", "/u", "/p") for a in args)
    if head == "ipconfig":
        return [a.lower() for a in args] in ([], ["/all"], ["/displaydns"], ["/?"])
    if head == "nvidia-smi":
        return _ro_nvidia(args)
    if head == "git":
        return _ro_git(args)
    if head in ("python", "python3", "py"):
        if args in (["--version"], ["-V"], ["-VV"]) or (head == "py" and args in (["-0"], ["-0p"])):
            return True
        return len(args) >= 2 and args[:2] == ["-m", "pip"] and _ro_pip(args[2:])
    if head in ("pip", "pip3"):
        return _ro_pip(args)
    if head == "node":
        return args in (["--version"], ["-v"])
    if head == "npm":
        if args in (["--version"], ["-v"]):
            return True
        if args and args[0] in ("ls", "list", "ll", "la"):
            return all(a.startswith("-") and ("=" not in a or a.startswith(("--depth=", "--omit=")))
                       for a in args[1:])
        return False
    return False


def _is_readonly(cmd: str) -> bool:
    """True เฉพาะคำสั่งที่อยู่ในรายการอ่านอย่างเดียว "แบบตรงอาร์กิวเมนต์" และไม่มีอักขระพิเศษของ shell"""
    cmd = str(cmd or "").strip()
    if not cmd or _has_meta(cmd):
        return False
    argv = _argv(cmd)
    if not argv:
        return False
    first = argv[0]
    # ต้องเป็นชื่อเปล่าๆ ถ้ามี path นำหน้า (C:\evil\git.exe) ชื่อไม่ได้บอกอะไรเลยว่าจะรันอะไร
    if any(sep in first for sep in ("\\", "/", ":")):
        return False
    head = first.lower()
    head = head[:-4] if head.endswith(".exe") else head
    if head not in SAFE_CMDS:
        return False
    return _ro_args(head, argv[1:])


def _tokens(cmd: str) -> list[tuple[str, bool]]:
    """แยกคำสั่งเป็นโทเคน คืน (ข้อความ, เป็นเป้าหมายของการเขียนหรือไม่)

    เขียนเองเพราะ shlex ใช้กฎ POSIX ที่ตีความ \\ เป็น escape ซึ่งผิดสำหรับ path
    ของ Windows ที่นี่สนใจแค่ขอบเขตของโทเคนกับเครื่องหมายคำพูดเท่านั้น
    """
    out, cur, quote, redirect = [], "", "", False
    i = 0
    while i < len(cmd):
        c = cmd[i]
        if quote:
            if c == quote:
                quote = ""
            else:
                cur += c
        elif c in "\"'":
            quote = c
        elif c in " \t":
            if cur:
                out.append((cur, redirect))
                cur, redirect = "", False
        elif c == ">":
            if cur:
                out.append((cur, False))
                cur = ""
            if cmd[i:i + 2] == ">>":
                i += 1
            redirect = True
        elif c in "|&;":
            if cur:
                out.append((cur, redirect))
                cur, redirect = "", False
        else:
            cur += c
        i += 1
    if cur:
        out.append((cur, redirect))
    return out


_SWITCH_VALUE_RE = re.compile(r"^(?:--?[A-Za-z][\w\-]*=|/[A-Za-z]+:)(.+)$")


def _path_of(tok: str, workdir: str) -> str | None:
    """คืน path เต็มถ้าโทเคนนี้ดูเป็น path (รวมค่าหลังสวิตช์ เช่น --contents=C:\\x หรือ /f:x)"""
    if tok.startswith("-") or tok.startswith("/"):
        m = _SWITCH_VALUE_RE.match(tok)
        if not m:
            return None                  # สวิตช์ล้วน ไม่มีค่าที่เป็น path
        tok = m.group(1)
    if not tok:
        return None
    if tok.lower().startswith("file:"):
        # file:///C:/x คือ path ในเครื่องที่ curl/เบราว์เซอร์อ่านได้ ต้องตรวจเหมือน path ปกติ
        tok = urllib.parse.unquote(re.sub(r"(?i)^file:/*", "", tok))
        if not re.match(r"^[A-Za-z]:", tok):
            return None
    elif "://" in tok:
        return None                      # URL เครือข่าย ไม่ใช่ path (ด่านเครือข่ายอยู่ที่ netguard)
    else:
        # "ไฟล์:สตรีม" (NTFS alternate data stream) หรือ rev:path ของ git — ตรวจที่ตัวไฟล์หน้า ':'
        # ไม่งั้น `type key.pem::$DATA` อ่านไฟล์ที่ถูกบล็อกด้วยนามสกุลได้ เพราะชื่อไม่ลงท้าย .pem แล้ว
        drive, rest = os.path.splitdrive(tok)
        if ":" in rest:
            tok = drive + rest.split(":", 1)[0]
            if not tok:
                return None
    if tok.startswith("~"):
        return os.path.expanduser(tok)   # เครื่องมือแบบ MSYS ขยาย ~ เอง ต้องตรวจที่ปลายทางจริง
    looks_like_path = (re.match(r"^[A-Za-z]:[\\/]", tok) or tok.startswith("\\\\")
                       or "\\" in tok or "/" in tok)
    candidate = tok if os.path.isabs(tok) else os.path.join(workdir, tok)
    if not looks_like_path and not os.path.exists(candidate) and not any(c in tok for c in "*?"):
        return None                      # คำธรรมดา เช่น ชื่อคำสั่งหรือคำค้น
    return candidate


def _guard_command(cmd: str, workdir: str, readonly: bool | None = None) -> None:
    """ตรวจ path ที่ฝังอยู่ในคำสั่ง ไม่ใช่แค่ cwd

    ทำไมต้องมี: คำสั่งอ่านอย่างเดียวอย่าง `type` `more` `findstr` รับชื่อไฟล์
    เป็นอาร์กิวเมนต์ ถ้าไม่ตรวจตรงนี้ `type C:\\Users\\...\\.ssh\\known_hosts`
    จะอ่านไฟล์ที่ทุกเครื่องมืออื่นปฏิเสธได้สบายๆ (ทดสอบแล้วว่าอ่านได้จริง)
    เท่ากับ S05 ถูกข้ามทั้งข้อผ่านทางเดียวคือ shell

    เพิ่มเติมรอบ 2026-09-30
      * wildcard ถูกขยายจริงแล้วตรวจทุกไฟล์ที่ตรง (type C:\\LLM\\secre*\\* อ่าน token ได้ถ้าไม่ทำ)
      * ข้อความของคำสั่งห้ามพูดถึงโฟลเดอร์ secrets ไม่ว่ากรณีใด
      * คำสั่งที่เปลี่ยนเครื่องห้ามแตะเขตห้ามเขียน (โค้ดของสแตก, Startup, .git ฯลฯ) และห้ามรันใน cwd ที่อยู่ในเขตนั้น
    """
    if readonly is None:
        readonly = _is_readonly(cmd)
    reason = guard.command_text_violation(cmd, readonly)
    if reason:
        guard.audit("denied", {"kind": "exec", "reason": reason,
                               "command": guard.scrub_text(cmd)[:300]})
        if reason == "secret_path":
            raise guard.Denied("คำสั่งนี้อ้างถึงโฟลเดอร์ความลับของระบบ (secrets/token) จึงรันไม่ได้ไม่ว่ากรณีใด")
        raise guard.Denied("คำสั่งที่เปลี่ยนแปลงเครื่องห้ามแตะโค้ด/ค่าตั้งของระบบหรือจุดที่ทำให้โปรแกรมรันเองอัตโนมัติ "
                           "ถ้าจำเป็นจริงให้ผู้ใช้รันเองใน terminal")
    # git show/cat-file/log ... HEAD:<path> ที่ path เป็นไฟล์ต้องห้าม = อ่านเนื้อไฟล์ที่บล็อกไว้
    hit = guard.git_revpath_violation(_argv(cmd))
    if hit:
        guard.audit("denied", {"kind": "exec", "reason": "git_revpath_blocked",
                               "command": guard.scrub_text(cmd)[:300]})
        raise guard.Denied("คำสั่ง git นี้ชี้ไปที่ไฟล์ต้องห้ามในรูป <rev>:<path> (เช่น credential/คีย์) "
                           "จึงอ่านเนื้อไฟล์นั้นจาก git ไม่ได้")
    guard.check_workdir_for_exec(workdir, readonly)
    seen = set()
    tokens = list(_tokens(cmd)) + [(t, False) for t in _argv(cmd)]
    for tok, is_write in tokens:
        if (tok, is_write) in seen:
            continue
        seen.add((tok, is_write))
        candidate = _path_of(tok, workdir)
        if candidate is None:
            continue
        if any(c in candidate for c in "*?"):
            guard.check_glob(candidate, need_write=is_write)
            continue
        (guard.check_write if is_write else guard.check_read)(candidate)
        if not readonly and guard.is_write_protected(candidate):
            raise guard.Denied("คำสั่งที่เปลี่ยนแปลงเครื่องห้ามอ้างถึง path ในเขตห้ามเขียน (%s) "
                               "ถ้าจำเป็นจริงให้ผู้ใช้รันเองใน terminal" % candidate)


def _child_env(readonly: bool) -> dict:
    """env ของคำสั่งลูก: ตัดของที่เป็นความลับของสแตก และปิดช่องรันโค้ดแฝงของคำสั่งอ่านอย่างเดียว"""
    env = os.environ.copy()
    for k in list(env):
        if k.upper() in ("GATEWAY_API_KEY", "LLM_LOCAL_TOKEN_FILE"):
            env.pop(k, None)
    if readonly:
        # cmd.exe ค้นโปรแกรมในโฟลเดอร์ปัจจุบันก่อน PATH — git.bat ที่ถูกวางไว้ใน cwd จะถูกรันแทน git จริง
        env["NoDefaultCurrentDirectoryInExePath"] = "1"
        # git status อ่าน core.fsmonitor แล้ว "รันโปรแกรมนั้น" และ git ยอมเปิด bare repo ที่ใครก็สร้างได้
        # (ไฟล์ HEAD/config/objects ธรรมดาในโฟลเดอร์ผู้ใช้) จึงบังคับค่าปลอดภัยผ่าน env ซึ่งชนะ config ในไฟล์
        # stash.showPatch=true ทำให้ "git stash show" (ซึ่งรันทันที) พิมพ์ patch เต็ม และ
        # log.showSignature=true ทำให้ git log เรียก gpg.program จาก config ของ repo — บังคับปิดทั้งคู่
        pairs = (("core.fsmonitor", "false"), ("safe.bareRepository", "explicit"),
                 ("stash.showPatch", "false"), ("log.showSignature", "false"))
        env["GIT_CONFIG_COUNT"] = str(len(pairs))
        for n, (k, v) in enumerate(pairs):
            env["GIT_CONFIG_KEY_%d" % n] = k
            env["GIT_CONFIG_VALUE_%d" % n] = v
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


_URL_CRED_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/\s@:]+:[^/\s@]+@")


def _clean_output(text: str) -> str:
    """ลบ token ของบริการในเครื่องและรหัสผ่านใน URL ออกจากผลลัพธ์ก่อนถึงมือโมเดล"""
    text = _URL_CRED_RE.sub(r"\1***@", text)
    if secrets_util is not None:
        text = secrets_util.scrub(text)
    return text


# คำสั่งค้นแบบ "เดินลึกลงทั้งต้นไม้" ที่ root อาจครอบโฟลเดอร์ต้องห้าม (เช่น C:\LLM ครอบ secrets)
# where /r และ dir /s เป็นคำสั่งอ่านอย่างเดียว จึงรันทันที แต่ผลลัพธ์เผยชื่อไฟล์ในโฟลเดอร์ที่บล็อก
# (ยืนยันการมีอยู่ของไฟล์ token ได้ ถึงจะอ่านเนื้อในไม่ได้) — จึงกรองบรรทัดที่อ้าง path ต้องห้ามทิ้ง
_WINPATH_RE = re.compile(r"(?:[A-Za-z]:\\|\\\\)[^\r\n\"<>|]*")


def _is_recursive_scan(cmd: str) -> bool:
    """คำสั่งที่ผลลัพธ์เป็นรายการ path ซึ่งอาจอยู่ในพื้นที่ต้องห้าม ต้องกรองก่อนส่งให้โมเดล

    where ทุกรูป (ไม่ใช่แค่ /r): where $USERPROFILE:*.pem หรือ where <โฟลเดอร์>:<pattern> ก็พ่นชื่อไฟล์ได้
    """
    argv = _argv(cmd)
    if not argv:
        return False
    head = argv[0].lower()
    head = head[:-4] if head.endswith(".exe") else head
    sw = _cmd_switches(argv[1:])
    if head == "where":
        return True
    if head == "dir" and "s" in sw:
        return True
    if head == "tree":
        return True
    if head == "findstr" and any(a.startswith("/") and "s" in _switch_letters(a) for a in argv[1:]):
        return True
    return False


def _redact_blocked_lines(text: str) -> str:
    """แทนบรรทัดที่อ้าง path ในโฟลเดอร์ต้องห้ามด้วยเครื่องหมายปิดบัง (ใช้กับผลของคำสั่งค้นแบบลึก)"""
    out = []
    for line in text.splitlines():
        blocked = False
        for m in _WINPATH_RE.finditer(line):
            cand = m.group(0).strip().rstrip("\\")
            if len(cand) < 3:
                continue
            try:
                guard.check_read(cand)
            except guard.Denied:
                blocked = True
                break
            except Exception:      # noqa: BLE001 — path แปลกๆ ในบรรทัด ไม่ถือเป็นการบล็อก
                continue
        out.append("  [ปิดบัง 1 บรรทัดที่อ้างถึง path ในพื้นที่ต้องห้าม]" if blocked else line)
    return "\n".join(out)


def exec_shell_command(command: str, cwd: str = "", confirm_token: str = "",
                       timeout: int = EXEC_TIMEOUT, **_) -> str:
    """รันคำสั่งระบบ — คำสั่งที่เปลี่ยนเครื่องต้องยืนยันสองขั้นตาม S03"""
    cmd = str(command or "").strip()
    if not cmd:
        return "ต้องระบุคำสั่ง"
    if FORBIDDEN.search(cmd):
        guard.audit("denied", {"kind": "exec", "command": guard.scrub_text(cmd)[:300],
                               "reason": "forbidden_pattern"})
        return ("ปฏิเสธ: คำสั่งนี้อยู่ในกลุ่มที่ทำลายระบบ เปลี่ยนสิทธิ์ หรือฝังตัวให้รันเองอัตโนมัติ "
                "(format/diskpart/reg/net user/schtasks/shutdown ฯลฯ) จึงรันไม่ได้ไม่ว่ากรณีใด "
                "ถ้าจำเป็นจริง ให้ผู้ใช้รันเองใน terminal")
    readonly = _is_readonly(cmd)
    try:
        # ไม่ระบุ cwd = โฟลเดอร์ของโปรเจกต์นี้ (เดิมคือ C:\LLM ซึ่งมีโค้ดของ launcher/hub อยู่ตรงนั้นเลย)
        workdir = (guard.check_read(cwd) if cwd
                   else guard.project_dir(guard.current_project() or "default"))
        _guard_command(cmd, workdir, readonly)
    except Exception as exc:
        return _err(exc)

    if not readonly:
        action = "exec"
        detail = "%s\n(cwd: %s)" % (cmd, workdir)
        if not confirm_token:
            try:
                # R1: review = คำสั่งเต็ม + cwd + timeout (คำสั่งยาวเกินจะอ่านทัน = ReviewTooLarge ไม่ออก token)
                tok = guard.need_confirm(action, detail, review=_exec_review(cmd, workdir, timeout))
            except guard.Denied as exc:
                return _err(exc)
            return guard.confirm_hint(tok, "รันคำสั่งระบบ", "%s\n  โฟลเดอร์: %s" % (cmd, workdir))
        if not guard.consume_confirm(confirm_token, action, detail):
            return _bad_token_msg()

    guard.audit("exec_shell_command", {"command": guard.scrub_text(cmd)[:500], "cwd": workdir,
                                       "readonly": readonly,
                                       "confirmed": not readonly})
    try:
        # shell=True จำเป็นสำหรับคำสั่ง built-in ของ cmd (dir, type) แต่เราคัดกรองมาแล้ว
        # stdin=DEVNULL: คำสั่งที่รอ input (date/time/more/pause) ต้องจบทันที ไม่ค้างจน timeout
        proc = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True,
                              stdin=subprocess.DEVNULL, env=_child_env(readonly),
                              timeout=max(5, min(int(timeout), 600)))
    except subprocess.TimeoutExpired:
        return "คำสั่งใช้เวลาเกิน %d วินาที จึงถูกยกเลิก" % timeout
    except Exception as exc:
        return _err(exc)

    def dec(b: bytes) -> str:
        for enc in ("utf-8", "cp874", "cp1252"):
            try:
                return b.decode(enc)
            except UnicodeDecodeError:
                continue
        return b.decode("utf-8", "replace")

    out = dec(proc.stdout).strip()
    err = dec(proc.stderr).strip()
    # คำสั่งค้นแบบลึก (where /r, dir /s, tree, findstr /s) อาจพ่นชื่อไฟล์ในโฟลเดอร์ต้องห้าม
    # ออกมา ถึงจะอ่านเนื้อในไม่ได้ก็ยังยืนยันการมีอยู่ได้ — กรองบรรทัดที่อ้าง path ต้องห้ามทิ้ง
    if _is_recursive_scan(cmd):
        out = _redact_blocked_lines(out)
        err = _redact_blocked_lines(err)
    parts = []
    if out:
        parts.append(out[:20000])
    if err:
        parts.append("[stderr]\n" + err[:4000])
    parts.append("[exit code: %d]" % proc.returncode)
    return _clean_output("\n".join(parts))


# ------------------------------------------------------------------- schema
TOOLS = [
    {"name": "read_file",
     "description": "อ่านเนื้อหาไฟล์ข้อความ คืนเลขบรรทัดกำกับ ถ้าชี้ไปที่โฟลเดอร์จะแสดงรายการไฟล์แทน",
     "inputSchema": {"type": "object", "required": ["path"], "properties": {
         "path": {"type": "string", "description": "path เต็มของไฟล์"},
         "offset": {"type": "integer", "description": "เริ่มที่บรรทัดที่เท่าไร (นับจาก 0)"},
         "limit": {"type": "integer", "description": "อ่านกี่บรรทัด ค่าเริ่มต้น 2000"}}}},
    {"name": "list_dir",
     "description": "แสดงรายการไฟล์และโฟลเดอร์ พร้อมขนาดและเวลาแก้ไขล่าสุด",
     "inputSchema": {"type": "object", "required": ["path"], "properties": {
         "path": {"type": "string"}}}},
    {"name": "get_info",
     "description": "ดูรายละเอียดไฟล์หรือโฟลเดอร์ (ขนาด เวลา สิทธิ์เขียน) ถ้าเว้น path ว่างจะสรุปนโยบายความปลอดภัยที่ใช้อยู่",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "write_file",
     "description": ("เขียนไฟล์ใหม่ ถ้าไฟล์มีอยู่แล้ว หรือเป็นไฟล์สคริปต์/โปรแกรม (.py .ps1 .bat .js ฯลฯ) "
                     "จะคืน confirm_token ให้ถามผู้ใช้ก่อนแล้วยืนยันด้วย local_confirm "
                     "โค้ด/ค่าตั้งของระบบเขียนไม่ได้เลย"),
     "inputSchema": {"type": "object", "required": ["path", "content"], "properties": {
         "path": {"type": "string"}, "content": {"type": "string"},
         "confirm_token": {"type": "string", "description": "ใส่เมื่อผู้ใช้อนุมัติแล้ว"}}}},
    {"name": "edit_file",
     "description": ("แทนที่ข้อความเดิมด้วยข้อความใหม่ในไฟล์ ต้องตรงทุกตัวอักษรและไม่กำกวม "
                     "คืน confirm_token เสมอ ต้องถามผู้ใช้ก่อนแล้วยืนยันด้วย local_confirm"),
     "inputSchema": {"type": "object", "required": ["path", "old_string", "new_string"],
                     "properties": {
         "path": {"type": "string"}, "old_string": {"type": "string"},
         "new_string": {"type": "string"},
         "replace_all": {"type": "boolean", "description": "แทนที่ทุกตำแหน่งที่พบ"},
         "confirm_token": {"type": "string", "description": "ใส่เมื่อผู้ใช้อนุมัติแล้ว"}}}},
    {"name": "file_glob_search",
     "description": "ค้นหาไฟล์จากรูปแบบชื่อ เช่น *.py หรือ **/test_*.json",
     "inputSchema": {"type": "object", "required": ["pattern"], "properties": {
         "pattern": {"type": "string"}, "path": {"type": "string", "description": "โฟลเดอร์ที่เริ่มค้น"}}}},
    {"name": "grep_search",
     "description": "ค้นข้อความในไฟล์ด้วย regular expression คืน path:บรรทัด:เนื้อหา",
     "inputSchema": {"type": "object", "required": ["pattern"], "properties": {
         "pattern": {"type": "string"}, "path": {"type": "string"},
         "glob": {"type": "string", "description": "จำกัดชนิดไฟล์ เช่น *.py"},
         "ignore_case": {"type": "boolean"}}}},
    {"name": "exec_shell_command",
     "description": ("รันคำสั่งบน Windows เฉพาะคำสั่งอ่านอย่างเดียวในรายการ (dir, type, git status/log, "
                     "git diff --stat, pip list, --version) ที่รันได้ทันที คำสั่งอื่นทั้งหมด (รวม python "
                     "script.py, git diff/show ที่พิมพ์ patch) จะคืน confirm_token ให้ถามผู้ใช้ก่อน "
                     "แล้วยืนยันด้วย local_confirm"),
     "inputSchema": {"type": "object", "required": ["command"], "properties": {
         "command": {"type": "string"}, "cwd": {"type": "string"},
         "confirm_token": {"type": "string"},
         "timeout": {"type": "integer", "description": "วินาที ค่าเริ่มต้น 120"}}}},
]

IMPL = {
    "read_file": read_file,
    "list_dir": list_dir,
    "get_info": get_info,
    "write_file": write_file,
    "edit_file": edit_file,
    "file_glob_search": file_glob_search,
    "grep_search": grep_search,
    "exec_shell_command": exec_shell_command,
}

# --- mcp-exec: checkpoint/undo บนผิวเต็ม (/mcp) — ผิวย่อเรียกผ่าน local_read checkpoints / local_do undo ---
TOOLS += [
    {"name": "list_checkpoints",
     "description": ("รายการ checkpoint (สำเนาก่อนแก้ที่เก็บอัตโนมัติทุกครั้งที่ write_file/edit_file ลงมือ) "
                     "ของโปรเจกต์นี้ ใหม่สุดก่อน ใส่ path เพื่อดูเฉพาะไฟล์นั้น อ่านอย่างเดียว"),
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string"},
         "limit": {"type": "integer", "description": "จำนวนรายการสูงสุด (30)"}}}},
    {"name": "undo_file",
     "description": ("ย้อนไฟล์กลับเป็นสถานะใน checkpoint ล่าสุดที่ยังไม่ถูกย้อน (หรือ id ที่ระบุ) "
                     "คืน confirm_token พร้อม diff เสมอ ต้องถามผู้ใช้ก่อนแล้วยืนยันด้วย local_confirm "
                     "สถานะก่อนย้อนถูกเก็บเป็น checkpoint ใหม่ จึงย้อนกลับได้อีก"),
     "inputSchema": {"type": "object", "required": ["path"], "properties": {
         "path": {"type": "string"},
         "id": {"type": "string", "description": "id ของ checkpoint (ดูจาก list_checkpoints)"},
         "confirm_token": {"type": "string"}}}},
]
IMPL.update({"list_checkpoints": list_checkpoints, "undo_file": undo_file})
