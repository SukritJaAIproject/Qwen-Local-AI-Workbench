# -*- coding: utf-8 -*-
"""ความจำรายโปรเจกต์ + ตัวจัดการ path alias สำหรับ MCP server "Local Computer"

โมดูลนี้เก็บของไว้ในโฟลเดอร์ของแต่ละโปรเจกต์เท่านั้น (guard.project_dir)
  <project_dir>/MEMORY.md     บันทึกอ่านง่าย เขียนต่อท้ายอย่างเดียว ไม่ลบของเก่า
  <project_dir>/memory.json   รายการแบบมีโครงสร้าง (ใช้ค้นหา/ลบ)
  <project_dir>/paths.json    ทะเบียนชื่อย่อของ path ในโปรเจกต์นี้

หลักการที่ยึดไว้
----------------
1. แยกโปรเจกต์เด็ดขาด ทุก path คำนวณจาก guard.project_dir(project) เสมอ
   ไม่มีทางที่โปรเจกต์ A จะอ่านหรือเขียนไฟล์ของโปรเจกต์ B ได้
2. ไม่เก็บความลับ ข้อความที่ดูเหมือนมี API key / รหัสผ่าน / token / private key
   หรือก้อน base64-hex ยาวๆ จะถูกปฏิเสธตั้งแต่ยังไม่เขียนลงดิสก์ และไม่ถูก
   บันทึกลง audit.log ด้วย (audit เก็บแค่ metadata เช่นจำนวนตัวอักษร)
3. ทุกฟังก์ชันคืนค่าเป็นสตริงเสมอ ข้อผิดพลาดคืนเป็นข้อความขึ้นต้นด้วย "ERROR: "
   ไม่โยน exception ออกไปหาผู้เรียก และไม่ print อะไรทั้งสิ้น
4. path_add ต้องผ่าน guard.check_read / guard.check_write ก่อนเสมอ
   path_resolve ก็ตรวจซ้ำอีกรอบ เพราะสิทธิ์อาจเปลี่ยนหลังจากเพิ่ม alias ไปแล้ว
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone

from guard import Denied, audit, check_read, check_write, project_dir

# ---------------------------------------------------------------- ค่าคงที่

KINDS = ("decision", "requirement", "fact", "progress", "todo")
KIND_TH = {
    "decision": "การตัดสินใจ",
    "requirement": "ความต้องการ",
    "fact": "ข้อเท็จจริง",
    "progress": "ความคืบหน้า",
    "todo": "สิ่งที่ต้องทำ",
}
MODES = ("read_only", "read_write")
MAX_TEXT = 8000          # ตัวอักษรต่อหนึ่งรายการ
MAX_ENTRIES = 5000       # กันไฟล์บวมจนอ่านช้า
MAX_EXPORT = 60000       # ตัดความยาวตอน export เพื่อไม่ให้ทะลุ context ของโมเดล
MEMORY_MD = "MEMORY.md"
MEMORY_JSON = "memory.json"
PATHS_JSON = "paths.json"


# ---------------------------------------------------------- เครื่องมือภายใน

def _now() -> str:
    """เวลา UTC แบบ ISO ลงท้ายด้วย Z"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_id(taken) -> str:
    for _ in range(64):
        cand = uuid.uuid4().hex[:8]
        if cand not in taken:
            return cand
    return uuid.uuid4().hex[:8]


def _s(value, default: str = "") -> str:
    """แปลงอาร์กิวเมนต์ที่โมเดลส่งมาให้เป็นสตริงเสมอ (อาจได้ None หรือตัวเลข)"""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _int(value, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _base(project: str) -> str:
    """โฟลเดอร์ของโปรเจกต์ — จุดเดียวที่ path ทั้งโมดูลนี้งอกออกมา"""
    name = _s(project).strip()
    if not name:
        raise ValueError("ต้องระบุชื่อโปรเจกต์")
    return project_dir(name)


def _file(project: str, filename: str) -> str:
    return os.path.join(_base(project), filename)


def _read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return default
    return data


def _write_json(path: str, data) -> None:
    """เขียนแบบ atomic: เขียนไฟล์ชั่วคราวข้างๆ แล้วค่อย replace ทับ

    ถ้าไฟฟ้าดับกลางทาง ไฟล์เดิมยังอยู่ครบ ไม่กลายเป็น JSON พังครึ่งไฟล์
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _append_md(path: str, block: str) -> None:
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        if new:
            fh.write("# MEMORY\n\n"
                     "ไฟล์นี้เขียนต่อท้ายอย่างเดียว ของเก่าไม่ถูกแก้หรือถูกลบ\n"
                     "ถ้ารายการถูกลบออกจาก memory.json จะมีบรรทัดบอกไว้ด้านล่างแทน\n\n")
        fh.write(block)


def _load_entries(project: str):
    data = _read_json(_file(project, MEMORY_JSON), None)
    if isinstance(data, dict):
        entries = data.get("entries")
    elif isinstance(data, list):
        entries = data
    else:
        entries = None
    if not isinstance(entries, list):
        return []
    out = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        tags = item.get("tags")
        out.append({
            "id": _s(item.get("id")),
            "kind": _s(item.get("kind"), "fact"),
            "text": _s(item.get("text")),
            "created": _s(item.get("created")),
            "tags": [_s(t) for t in tags] if isinstance(tags, list) else [],
        })
    return out


def _save_entries(project: str, entries) -> None:
    _write_json(_file(project, MEMORY_JSON),
                {"version": 1, "project": _s(project).strip(), "entries": entries})


def _load_paths(project: str):
    data = _read_json(_file(project, PATHS_JSON), None)
    aliases = data.get("aliases") if isinstance(data, dict) else None
    if not isinstance(aliases, dict):
        return {}
    out = {}
    for alias, rec in aliases.items():
        if not isinstance(rec, dict):
            continue
        mode = _s(rec.get("mode"), "read_only")
        out[_s(alias)] = {
            "path": _s(rec.get("path")),
            "mode": mode if mode in MODES else "read_only",
            "added": _s(rec.get("added")),
        }
    return out


def _save_paths(project: str, aliases) -> None:
    _write_json(_file(project, PATHS_JSON),
                {"version": 1, "project": _s(project).strip(), "aliases": aliases})


# ------------------------------------------------- ตัวตรวจจับความลับ (secret)

_SECRET_WORD = (r"api[_\-]?keys?|secret[_\-]?key|client[_\-]?secret|secrets?|"
                r"passwords?|passwd|pwd|access[_\-]?tokens?|refresh[_\-]?tokens?|"
                r"tokens?|bearer|authorization|auth[_\-]?tokens?|"
                r"private[_\-]?key|credentials?")
# คำว่า secret/token ตามด้วยตัวคั่นแล้วค่อยเป็นค่า เช่น  api_key: sk-abc123...
# ค่ารับอักขระ ASCII ที่ไม่ใช่ช่องว่างทุกตัว (รหัสผ่านจริงมักมี @ ! # $ ปนอยู่)
# ตัวคัดกรองว่าค่านั้น "ดูเหมือนความลับ" อยู่ที่ _looks_like_value อีกชั้น
_RE_KV = re.compile(r"(?i)\b(" + _SECRET_WORD + r")\b\s*(?:[:=]|==>|=>|->|is|คือ|:=)?\s*"
                    r"[\"'`]?([^\s\"'`,;]{8,})[\"'`]?")
# bearer <token>  โดยไม่มีตัวคั่น
_RE_BEARER = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9_\-\.\+/=]{12,})")
_RE_PEM = re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")
# ก้อน hex ยาว เช่น hash หรือ key ที่แปะมาดิบๆ
_RE_HEX = re.compile(r"\b[A-Fa-f0-9]{32,}\b")
# ก้อน base64 ยาว (ต้องมีทั้งตัวเลขและตัวอักษรถึงจะนับ กันคำภาษาอังกฤษยาวๆ)
_RE_B64 = re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b")
# รูปแบบ key ที่รู้จักกันดี ต่อให้ไม่มีคำว่า key นำหน้าก็ต้องปฏิเสธ
_RE_KNOWN = re.compile(r"(?i)\b("
                       r"sk-[A-Za-z0-9_\-]{16,}|"
                       r"xox[abprs]-[A-Za-z0-9\-]{10,}|"
                       r"gh[pousr]_[A-Za-z0-9]{20,}|"
                       r"AKIA[0-9A-Z]{12,}|"
                       r"AIza[0-9A-Za-z_\-]{20,}|"
                       r"tvly-[A-Za-z0-9]{12,}|"
                       r"BSA[A-Za-z0-9_\-]{16,}|"
                       r"ey[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"
                       r")\b")

# คำที่ตามหลัง keyword แล้วชัดเจนว่าไม่ใช่ค่าความลับ เช่น "password manager"
_INNOCENT = {
    "manager", "managers", "management", "policy", "policies", "reset", "resets",
    "field", "fields", "form", "forms", "prompt", "prompts", "protected",
    "required", "expired", "rotation", "rotate", "storage", "store", "vault",
    "hashing", "hashed", "based", "strength", "checker", "generator", "length",
    "authentication", "auth", "header", "headers", "handling", "handler",
    "missing", "invalid", "expiry", "expires", "refresh", "endpoint", "example",
    "placeholder", "redacted", "unknown", "value", "values", "config",
    "configuration", "setting", "settings", "variable", "variables", "template",
}


def _looks_like_value(candidate: str) -> bool:
    """ค่าที่ดักได้ดูเหมือนความลับจริงไหม (กัน false positive ที่น่ารำคาญ)"""
    candidate = candidate.strip("\"'`").rstrip(".,;:)]}")
    low = candidate.lower()
    if not low or low in _INNOCENT:
        return False
    # ข้อความไทย/ยูนิโคดหลังคำว่า password ฯลฯ คือประโยคบรรยาย ไม่ใช่ตัวความลับ
    if any(ord(c) > 127 for c in candidate):
        return False
    if low.split("_")[0] in _INNOCENT or low.split("-")[0] in _INNOCENT:
        return False
    if low in {"none", "null", "empty", "xxx", "xxxx", "todo", "tbd", "n/a", "na",
               "true", "false", "yes", "no", "hidden", "***", "...", "<redacted>"}:
        return False
    if set(low) <= {"x", "*", ".", "-", "_"}:          # ค่าที่ถูกปิดบังไว้แล้ว
        return False
    has_digit = any(c.isdigit() for c in candidate)
    has_alpha = any(c.isalpha() for c in candidate)
    has_sym = any(c in "-_./+=~" for c in candidate)
    if len(candidate) >= 20:
        return True
    if has_digit and has_alpha:
        return True
    if has_sym and (has_digit or len(candidate) >= 12):
        return True
    return False


def _mixed(blob: str) -> bool:
    return any(c.isdigit() for c in blob) and any(c.isalpha() for c in blob)


def scan_secret(text: str):
    """คืนชื่อรูปแบบความลับที่เจอ (ภาษาไทย) หรือ None ถ้าสะอาด

    ตั้งใจให้เข้มไว้ก่อน ยอมปฏิเสธเกินดีกว่าปล่อยให้ความลับตกลงไปอยู่ในไฟล์
    ที่ถูกอ่านซ้ำทุกครั้งที่คุยกับโมเดล ฟังก์ชันนี้ไม่คืนค่าที่ตรวจเจอออกมา
    """
    if _RE_PEM.search(text):
        return "private key แบบ PEM (BEGIN ... PRIVATE KEY)"
    if _RE_KNOWN.search(text):
        return "คีย์ที่มีรูปแบบชัดเจน (เช่น sk-, ghp_, AKIA, AIza, JWT)"
    m = _RE_BEARER.search(text)
    if m and _looks_like_value(m.group(1)):
        return "bearer token"
    for m in _RE_KV.finditer(text):
        if _looks_like_value(m.group(2)):
            return "คำว่า %s ตามด้วยค่า" % m.group(1).lower()
    for m in _RE_HEX.finditer(text):
        return "ก้อน hex ยาว %d ตัวอักษร" % len(m.group(0))
    for m in _RE_B64.finditer(text):
        if _mixed(m.group(0)):
            return "ก้อน base64 ยาว %d ตัวอักษร" % len(m.group(0))
    return None


_REFUSE_TEMPLATE = (
    "ERROR: ไม่บันทึกให้ เพราะข้อความมีสิ่งที่ดูเหมือนความลับ: %s\n"
    "ความจำโปรเจกต์เป็นไฟล์ข้อความธรรมดาที่ถูกอ่านซ้ำทุกครั้งที่คุยกัน "
    "จึงไม่ใช่ที่เก็บรหัสผ่าน คีย์ หรือโทเคน\n"
    "ทางออก: เก็บของจริงไว้ใน password manager หรือ environment variable "
    "แล้วบันทึกแค่ 'ชื่อ' ของมัน เช่น \"คีย์ Brave อยู่ใน config.json ของ mcp-websearch\" "
    "โดยไม่ต้องใส่ตัวคีย์ลงไป"
)


# ------------------------------------------------------------ เครื่องมือ memory

def memory_remember(project: str, kind: str, text: str, tags: str = "") -> str:
    """เพิ่มหนึ่งรายการลงความจำของโปรเจกต์"""
    try:
        kind_v = _s(kind).strip().lower()
        text_v = _s(text).strip()
        tags_v = [t.strip() for t in _s(tags).replace("，", ",").split(",") if t.strip()]

        if kind_v not in KINDS:
            return ("ERROR: kind ต้องเป็นอย่างใดอย่างหนึ่งใน %s (ได้รับ %r)"
                    % (", ".join(KINDS), _s(kind)))
        if not text_v:
            return "ERROR: text ว่าง ไม่มีอะไรให้จำ"
        if len(text_v) > MAX_TEXT:
            return ("ERROR: ข้อความยาว %d ตัวอักษร เกินเพดาน %d "
                    "ช่วยสรุปให้สั้นลงหรือแบ่งเป็นหลายรายการ" % (len(text_v), MAX_TEXT))

        found = scan_secret(text_v + " " + " ".join(tags_v))
        if found:
            audit("memory_remember_refused",
                  {"project": _s(project), "kind": kind_v,
                   "chars": len(text_v), "reason": found})
            return _REFUSE_TEMPLATE % found

        base = _base(project)
        entries = _load_entries(project)
        if len(entries) >= MAX_ENTRIES:
            return ("ERROR: โปรเจกต์นี้มี %d รายการแล้ว ถึงเพดาน %d "
                    "ลบของเก่าด้วย memory_forget ก่อน" % (len(entries), MAX_ENTRIES))

        entry = {
            "id": _new_id({e["id"] for e in entries}),
            "kind": kind_v,
            "text": text_v,
            "created": _now(),
            "tags": tags_v,
        }
        entries.append(entry)
        _save_entries(project, entries)

        block = "## %s · %s · %s\n\n%s\n" % (
            entry["created"], KIND_TH.get(kind_v, kind_v), entry["id"], text_v)
        if tags_v:
            block += "\nแท็ก: %s\n" % ", ".join(tags_v)
        block += "\n"
        _append_md(os.path.join(base, MEMORY_MD), block)

        audit("memory_remember", {"project": _s(project), "kind": kind_v,
                                  "id": entry["id"], "chars": len(text_v),
                                  "tags": tags_v})
        return "จำแล้ว [%s] %s · id %s\n%s" % (
            KIND_TH.get(kind_v, kind_v), entry["created"], entry["id"], text_v)
    except Denied as exc:
        return "ERROR: guard ปฏิเสธ — %s" % exc
    except (OSError, ValueError) as exc:
        return "ERROR: บันทึกความจำไม่สำเร็จ — %s" % exc


def memory_recall(project: str, query: str = "", kind: str = "", limit: int = 20) -> str:
    """ค้นความจำของโปรเจกต์ ใหม่สุดขึ้นก่อน"""
    try:
        q = _s(query).strip().lower()
        kind_v = _s(kind).strip().lower()
        n = _int(limit, 20)
        if n <= 0:
            n = 20
        n = min(n, 200)
        if kind_v and kind_v not in KINDS:
            return ("ERROR: kind ต้องเป็นอย่างใดอย่างหนึ่งใน %s หรือเว้นว่างเพื่อเอาทุกชนิด"
                    % ", ".join(KINDS))

        entries = _load_entries(project)
        picked = []
        for e in entries:
            if kind_v and e["kind"] != kind_v:
                continue
            if q:
                hay = (e["text"] + " " + " ".join(e["tags"])).lower()
                if q not in hay:
                    continue
            picked.append(e)
        # ใหม่สุดก่อน: เรียงตามเวลา แล้วตามลำดับที่เพิ่มเข้ามา (index) เป็นตัวตัดสินเสมอกัน
        order = {id(e): i for i, e in enumerate(entries)}
        picked.sort(key=lambda e: (e["created"], order.get(id(e), 0)), reverse=True)
        total = len(picked)
        picked = picked[:n]

        audit("memory_recall", {"project": _s(project), "query": q,
                                "kind": kind_v, "hits": total, "shown": len(picked)})
        if not entries:
            # ผิวแบบย่อ (/fast ค่าเริ่มต้นของหน้าแชต) ไม่มีเครื่องมือชื่อ memory_remember
            # เรียกจริงคือ local_do action="remember" — บอกทั้งสองผิวไม่ให้โมเดลเล็กเรียกผิดตัว
            return ('ยังไม่มีความจำในโปรเจกต์ %s เลย บันทึกด้วย local_do action="remember" '
                    "(ผิวเต็ม: เครื่องมือ memory_remember)" % _s(project))
        if not picked:
            return "ไม่พบรายการที่ตรงกับเงื่อนไข (มีทั้งหมด %d รายการในโปรเจกต์นี้)" % len(entries)

        head = "พบ %d รายการ แสดง %d รายการ (ใหม่สุดก่อน)" % (total, len(picked))
        lines = [head, ""]
        for e in picked:
            tag = (" · แท็ก: " + ", ".join(e["tags"])) if e["tags"] else ""
            lines.append("[%s] %s · %s%s" % (
                e["id"], KIND_TH.get(e["kind"], e["kind"]), e["created"], tag))
            for ln in e["text"].splitlines() or [""]:
                lines.append("    " + ln)
            lines.append("")
        return "\n".join(lines).rstrip()
    except Denied as exc:
        return "ERROR: guard ปฏิเสธ — %s" % exc
    except (OSError, ValueError) as exc:
        return "ERROR: ค้นความจำไม่สำเร็จ — %s" % exc


def memory_forget(project: str, id: str = "") -> str:
    """ลบหนึ่งรายการออกจาก memory.json (MEMORY.md ยังคงประวัติไว้ตามหลัก append-only)"""
    try:
        target = _s(id).strip().lower()
        if not target:
            return "ERROR: ต้องระบุ id ของรายการที่จะลบ ดู id ได้จาก memory_recall"

        base = _base(project)
        entries = _load_entries(project)
        hit = [e for e in entries if e["id"].lower() == target]
        if not hit:
            partial = [e for e in entries if e["id"].lower().startswith(target)]
            if len(partial) == 1:
                hit = partial
            elif len(partial) > 1:
                return ("ERROR: id %r ตรงกับหลายรายการ (%s) ใส่ให้ครบ 8 ตัว"
                        % (_s(id), ", ".join(e["id"] for e in partial)))
            else:
                return ("ERROR: ไม่พบรายการ id %r ในโปรเจกต์ %s"
                        % (_s(id), _s(project)))

        gone = hit[0]
        entries = [e for e in entries if e is not gone]
        _save_entries(project, entries)
        _append_md(os.path.join(base, MEMORY_MD),
                   "## %s · ลบรายการ · %s\n\nรายการนี้ถูกลบออกจาก memory.json แล้ว "
                   "ข้อความเดิมยังอยู่ด้านบนของไฟล์นี้ตามหลักเขียนต่อท้ายอย่างเดียว\n\n"
                   % (_now(), gone["id"]))

        audit("memory_forget", {"project": _s(project), "id": gone["id"],
                                "kind": gone["kind"], "remaining": len(entries)})
        preview = gone["text"].splitlines()[0] if gone["text"] else ""
        if len(preview) > 120:
            preview = preview[:120] + "…"
        return "ลบแล้ว id %s [%s] %s\nเหลือ %d รายการในโปรเจกต์นี้" % (
            gone["id"], KIND_TH.get(gone["kind"], gone["kind"]), preview, len(entries))
    except Denied as exc:
        return "ERROR: guard ปฏิเสธ — %s" % exc
    except (OSError, ValueError) as exc:
        return "ERROR: ลบความจำไม่สำเร็จ — %s" % exc


def memory_export(project: str) -> str:
    """คืนเนื้อไฟล์ MEMORY.md ของโปรเจกต์ทั้งก้อน"""
    try:
        path = _file(project, MEMORY_MD)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except FileNotFoundError:
            audit("memory_export", {"project": _s(project), "chars": 0, "exists": False})
            return ("ยังไม่มีไฟล์ MEMORY.md ในโปรเจกต์ %s (ยังไม่เคยบันทึกอะไรเลย)\n"
                    'ไฟล์จะอยู่ที่ %s เมื่อเริ่มบันทึกด้วย local_do action="remember" '
                    "(ผิวเต็ม: เครื่องมือ memory_remember)" % (_s(project), path))

        audit("memory_export", {"project": _s(project), "chars": len(content),
                                "exists": True})
        note = "ไฟล์: %s (%d ตัวอักษร)\n\n" % (path, len(content))
        if len(content) > MAX_EXPORT:
            keep = content[-MAX_EXPORT:]
            return (note + "…ตัดส่วนต้นออกเพราะยาวเกิน %d ตัวอักษร แสดงเฉพาะส่วนท้าย…\n\n"
                    % MAX_EXPORT) + keep
        return note + content
    except Denied as exc:
        return "ERROR: guard ปฏิเสธ — %s" % exc
    except (OSError, ValueError) as exc:
        return "ERROR: อ่าน MEMORY.md ไม่สำเร็จ — %s" % exc


# ------------------------------------------------------------- เครื่องมือ path

def _clean_alias(alias: str) -> str:
    return _s(alias).strip().strip("\\/").strip()


def _norm(path: str) -> str:
    return os.path.normpath(_s(path).strip().strip('"').strip())


def path_add(project: str, alias: str, path: str, mode: str = "read_only") -> str:
    """ผูกชื่อย่อเข้ากับโฟลเดอร์หรือไฟล์จริง ต้องผ่าน guard ก่อนเสมอ"""
    try:
        alias_v = _clean_alias(alias)
        mode_v = _s(mode).strip().lower() or "read_only"
        raw = _norm(path)

        if not alias_v:
            return "ERROR: ต้องตั้งชื่อย่อ (alias) ที่ไม่ว่าง"
        if len(alias_v) > 64:
            return "ERROR: ชื่อย่อยาวเกิน 64 ตัวอักษร"
        if not raw:
            return "ERROR: ต้องระบุ path ที่จะผูกกับชื่อย่อนี้"
        if mode_v not in MODES:
            return "ERROR: mode ต้องเป็น read_only หรือ read_write (ได้รับ %r)" % _s(mode)

        # ให้ guard เป็นคนตัดสินว่าเข้าถึงได้ไหม และคืน path ที่ normalise แล้ว
        try:
            resolved = check_write(raw) if mode_v == "read_write" else check_read(raw)
        except Denied as exc:
            audit("path_add_denied", {"project": _s(project), "alias": alias_v,
                                      "path": raw, "mode": mode_v, "reason": str(exc)})
            return ("ERROR: guard ไม่อนุญาตให้เข้าถึง %s ด้วยสิทธิ์ %s — %s\n"
                    "ถ้าจำเป็นต้องใช้จริง ต้องไปเพิ่ม root ที่อนุญาตในการตั้งค่าของ guard ก่อน"
                    % (raw, mode_v, exc))

        if not os.path.exists(resolved):
            return ("ERROR: ไม่พบ %s บนดิสก์ ตรวจตัวสะกดอีกครั้ง "
                    "(ยังไม่ผูกชื่อย่อให้ เพราะ alias ที่ชี้ไปที่ว่างจะทำให้สับสนภายหลัง)"
                    % resolved)

        aliases = _load_paths(project)
        old = aliases.get(alias_v)
        aliases[alias_v] = {"path": resolved, "mode": mode_v, "added": _now()}
        _save_paths(project, aliases)

        audit("path_add", {"project": _s(project), "alias": alias_v,
                           "path": resolved, "mode": mode_v,
                           "replaced": bool(old)})
        kindword = "โฟลเดอร์" if os.path.isdir(resolved) else "ไฟล์"
        msg = "ผูกชื่อย่อ %r -> %s (%s, สิทธิ์ %s) ในโปรเจกต์ %s" % (
            alias_v, resolved, kindword, mode_v, _s(project))
        if old:
            msg += "\n(ชื่อย่อนี้เคยชี้ไป %s สิทธิ์ %s ตอนนี้ถูกเขียนทับแล้ว)" % (
                old["path"], old["mode"])
        return msg
    except Denied as exc:
        return "ERROR: guard ปฏิเสธ — %s" % exc
    except (OSError, ValueError) as exc:
        return "ERROR: เพิ่มชื่อย่อไม่สำเร็จ — %s" % exc


def path_list(project: str) -> str:
    """แสดงชื่อย่อทั้งหมดของโปรเจกต์นี้"""
    try:
        aliases = _load_paths(project)
        audit("path_list", {"project": _s(project), "count": len(aliases)})
        if not aliases:
            return ("โปรเจกต์ %s ยังไม่มีชื่อย่อ path เลย ใช้ path_add เพื่อเพิ่ม"
                    % _s(project))
        lines = ["ชื่อย่อ path ของโปรเจกต์ %s (%d รายการ)" % (_s(project), len(aliases)), ""]
        for alias in sorted(aliases, key=str.lower):
            rec = aliases[alias]
            status = "" if os.path.exists(rec["path"]) else "  [หาไม่เจอแล้ว]"
            lines.append("%-20s %s  (%s)%s" % (alias, rec["path"], rec["mode"], status))
        return "\n".join(lines)
    except Denied as exc:
        return "ERROR: guard ปฏิเสธ — %s" % exc
    except (OSError, ValueError) as exc:
        return "ERROR: อ่านรายการชื่อย่อไม่สำเร็จ — %s" % exc


def path_remove(project: str, alias: str) -> str:
    """ลบเฉพาะชื่อย่อออกจากทะเบียน ไม่แตะไฟล์หรือโฟลเดอร์จริงเลย"""
    try:
        alias_v = _clean_alias(alias)
        if not alias_v:
            return "ERROR: ต้องระบุชื่อย่อที่จะลบ"

        aliases = _load_paths(project)
        if alias_v not in aliases:
            match = [a for a in aliases if a.lower() == alias_v.lower()]
            if len(match) == 1:
                alias_v = match[0]
            else:
                return ("ERROR: ไม่พบชื่อย่อ %r ในโปรเจกต์ %s (มีอยู่: %s)"
                        % (_s(alias), _s(project),
                           ", ".join(sorted(aliases)) if aliases else "ไม่มีเลย"))

        rec = aliases.pop(alias_v)
        _save_paths(project, aliases)
        audit("path_remove", {"project": _s(project), "alias": alias_v,
                              "path": rec["path"]})
        return ("ลบชื่อย่อ %r ออกจากทะเบียนของโปรเจกต์ %s แล้ว\n"
                "ไฟล์และโฟลเดอร์ที่ %s ยังอยู่ครบ ไม่ถูกลบหรือแก้ไขใดๆ "
                "เครื่องมือนี้ลบแค่ชื่อย่อเท่านั้น"
                % (alias_v, _s(project), rec["path"]))
    except Denied as exc:
        return "ERROR: guard ปฏิเสธ — %s" % exc
    except (OSError, ValueError) as exc:
        return "ERROR: ลบชื่อย่อไม่สำเร็จ — %s" % exc


def path_resolve(project: str, alias: str, subpath: str = "") -> str:
    """แปลงชื่อย่อ (+ subpath) เป็น path เต็ม โดยตรวจสิทธิ์กับ guard ซ้ำอีกครั้ง"""
    try:
        alias_v = _clean_alias(alias)
        sub = _s(subpath).strip().strip('"').strip()
        if not alias_v:
            return "ERROR: ต้องระบุชื่อย่อ"

        aliases = _load_paths(project)
        rec = aliases.get(alias_v)
        if rec is None:
            match = [a for a in aliases if a.lower() == alias_v.lower()]
            if len(match) == 1:
                alias_v = match[0]
                rec = aliases[alias_v]
            else:
                return ("ERROR: ไม่พบชื่อย่อ %r ในโปรเจกต์ %s (มีอยู่: %s)"
                        % (_s(alias), _s(project),
                           ", ".join(sorted(aliases)) if aliases else "ไม่มีเลย"))

        root = os.path.normpath(rec["path"])
        target = root
        if sub:
            sub_n = sub.replace("/", "\\").lstrip("\\")
            if os.path.isabs(sub) or os.path.splitdrive(sub)[0]:
                return ("ERROR: subpath ต้องเป็น path ย่อยแบบสัมพัทธ์ ไม่ใช่ path เต็ม "
                        "(ได้รับ %r) ถ้าจะใช้ path เต็ม ให้เพิ่มเป็นชื่อย่อใหม่ด้วย path_add" % sub)
            target = os.path.normpath(os.path.join(root, sub_n))
            base_cmp = root.rstrip("\\").lower() + "\\"
            if target.lower() != root.rstrip("\\").lower() and not target.lower().startswith(base_cmp):
                audit("path_resolve_escape", {"project": _s(project), "alias": alias_v,
                                              "subpath": sub, "target": target})
                return ("ERROR: subpath %r พาออกไปนอกขอบเขตของชื่อย่อ %r "
                        "(เช่นการใช้ ..) ไม่อนุญาต" % (sub, alias_v))

        try:
            final = check_write(target) if rec["mode"] == "read_write" else check_read(target)
        except Denied as exc:
            audit("path_resolve_denied", {"project": _s(project), "alias": alias_v,
                                          "target": target, "reason": str(exc)})
            return ("ERROR: guard ไม่อนุญาตให้เข้าถึง %s แล้ว — %s\n"
                    "ชื่อย่อนี้อาจถูกเพิ่มไว้ตอนที่กติกาของ guard ยังต่างจากตอนนี้"
                    % (target, exc))

        audit("path_resolve", {"project": _s(project), "alias": alias_v,
                               "subpath": sub, "path": final, "mode": rec["mode"]})
        exists = "มีอยู่จริง" if os.path.exists(final) else "ยังไม่มีไฟล์นี้บนดิสก์"
        return "%s\n(ชื่อย่อ %s สิทธิ์ %s · %s)" % (final, alias_v, rec["mode"], exists)
    except Denied as exc:
        return "ERROR: guard ปฏิเสธ — %s" % exc
    except (OSError, ValueError) as exc:
        return "ERROR: แปลงชื่อย่อไม่สำเร็จ — %s" % exc


# ------------------------------------------------------------------ schema MCP

_PROJECT_PROP = {"type": "string",
                 "description": "ชื่อโปรเจกต์ ใช้แยกพื้นที่เก็บของ ข้อมูลข้ามโปรเจกต์กันไม่ได้"}

TOOLS = [
    {
        "name": "memory_remember",
        "description": ("บันทึกสิ่งที่ต้องจำระยะยาวของโปรเจกต์หนึ่ง เช่น ข้อตกลง ข้อกำหนด "
                        "ข้อเท็จจริง ความคืบหน้า หรือสิ่งที่ค้างอยู่ ใช้เมื่อผู้ใช้บอกอะไรที่ "
                        "ควรจำข้ามบทสนทนา ห้ามใช้เก็บรหัสผ่านหรือคีย์ ระบบจะปฏิเสธเอง"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "kind": {"type": "string", "enum": list(KINDS),
                         "description": "ชนิดของรายการ: decision การตัดสินใจ, requirement ความต้องการ, "
                                        "fact ข้อเท็จจริง, progress ความคืบหน้า, todo สิ่งที่ต้องทำ"},
                "text": {"type": "string", "description": "เนื้อความที่จะจำ เขียนให้เข้าใจได้ด้วยตัวเอง"},
                "tags": {"type": "string", "default": "",
                         "description": "แท็กคั่นด้วยจุลภาค เช่น \"ติดตั้ง,gpu\" เว้นว่างได้"},
            },
            "required": ["project", "kind", "text"],
        },
    },
    {
        "name": "memory_recall",
        "description": ("ค้นความจำของโปรเจกต์ด้วยคำค้น (ไม่สนตัวพิมพ์ใหญ่เล็ก ค้นทั้งเนื้อความและแท็ก) "
                        "ใช้ก่อนตอบคำถามที่อาจเคยคุยกันไว้แล้ว เว้น query ว่างเพื่อดูรายการล่าสุดทั้งหมด"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "query": {"type": "string", "default": "",
                          "description": "คำค้นแบบ substring เว้นว่างได้เพื่อเอาทุกรายการ"},
                "kind": {"type": "string", "default": "",
                         "description": "กรองเฉพาะชนิดนี้ (%s) เว้นว่างเพื่อเอาทุกชนิด"
                                        % ", ".join(KINDS)},
                "limit": {"type": "integer", "default": 20,
                          "description": "จำนวนรายการสูงสุดที่จะแสดง (ค่าเริ่มต้น 20 สูงสุด 200)"},
            },
            "required": ["project"],
        },
    },
    {
        "name": "memory_forget",
        "description": ("ลบความจำหนึ่งรายการด้วย id (ดู id ได้จาก memory_recall) "
                        "ใช้เมื่อข้อมูลเดิมผิดหรือหมดอายุแล้ว"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "id": {"type": "string", "description": "id 8 หลักของรายการที่จะลบ"},
            },
            "required": ["project", "id"],
        },
    },
    {
        "name": "memory_export",
        "description": ("คืนเนื้อไฟล์ MEMORY.md ของโปรเจกต์ทั้งไฟล์ ใช้เมื่อต้องการทบทวนบันทึกทั้งหมด "
                        "หรือจะคัดลอกไปที่อื่น"),
        "inputSchema": {
            "type": "object",
            "properties": {"project": _PROJECT_PROP},
            "required": ["project"],
        },
    },
    {
        "name": "path_add",
        "description": ("ตั้งชื่อย่อให้โฟลเดอร์หรือไฟล์ที่ใช้บ่อยในโปรเจกต์นี้ จะได้เรียกด้วยชื่อสั้นๆ แทนการพิมพ์ path ยาว "
                        "ระบบตรวจสิทธิ์ก่อนเสมอ ถ้า path อยู่นอกขอบเขตที่อนุญาตจะถูกปฏิเสธ"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "alias": {"type": "string", "description": "ชื่อย่อ เช่น \"โค้ด\" หรือ \"logs\""},
                "path": {"type": "string", "description": "path เต็มบนเครื่อง เช่น C:\\LLM\\projects"},
                "mode": {"type": "string", "enum": list(MODES), "default": "read_only",
                         "description": "read_only อ่านอย่างเดียว (ค่าเริ่มต้น) หรือ read_write เขียนได้ด้วย"},
            },
            "required": ["project", "alias", "path"],
        },
    },
    {
        "name": "path_list",
        "description": "แสดงชื่อย่อ path ทั้งหมดของโปรเจกต์นี้ พร้อม path จริงและสิทธิ์ ใช้เมื่อลืมว่าตั้งชื่ออะไรไว้บ้าง",
        "inputSchema": {
            "type": "object",
            "properties": {"project": _PROJECT_PROP},
            "required": ["project"],
        },
    },
    {
        "name": "path_remove",
        "description": ("ลบเฉพาะ 'ชื่อย่อ' ออกจากทะเบียนของโปรเจกต์ ไม่ลบไฟล์หรือโฟลเดอร์จริงแม้แต่ไฟล์เดียว "
                        "ใช้เมื่อชื่อย่อไม่ได้ใช้แล้วหรือตั้งผิด"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "alias": {"type": "string", "description": "ชื่อย่อที่จะถอดออกจากทะเบียน"},
            },
            "required": ["project", "alias"],
        },
    },
    {
        "name": "path_resolve",
        "description": ("แปลงชื่อย่อ (บวก subpath ถ้ามี) ให้เป็น path เต็มที่ผ่านการตรวจสิทธิ์แล้ว "
                        "ใช้ก่อนส่ง path ต่อให้เครื่องมืออ่าน/เขียนไฟล์"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "alias": {"type": "string", "description": "ชื่อย่อที่เคยเพิ่มไว้ด้วย path_add"},
                "subpath": {"type": "string", "default": "",
                            "description": "path ย่อยข้างในแบบสัมพัทธ์ เช่น \"logs\\\\run.log\" ห้ามใช้ .. ออกนอกขอบเขต"},
            },
            "required": ["project", "alias"],
        },
    },
]

IMPL = {
    "memory_remember": memory_remember,
    "memory_recall": memory_recall,
    "memory_forget": memory_forget,
    "memory_export": memory_export,
    "path_add": path_add,
    "path_list": path_list,
    "path_remove": path_remove,
    "path_resolve": path_resolve,
}
