# -*- coding: utf-8 -*-
"""Skills — แม่แบบพรอมต์จาก C:\\LLM\\skills\\<name>\\SKILL.md เสิร์ฟเป็น MCP prompts (B4)

ทำไมใช้ MCP prompts
--------------------
WebUI ของ llama.cpp (b10984) มีตัวเลือกพรอมต์ในช่องพิมพ์อยู่แล้ว: พิมพ์ "/" -> คำสั่ง "prompt" -> รายการพรอมต์ของ
ทุกเซิร์ฟเวอร์ MCP ที่ประกาศ capabilities.prompts -> ฟอร์มอาร์กิวเมนต์ (ปุ่ม "Use Prompt") -> prompts/get -> ข้อความที่ได้
กลายเป็นชิป "MCP Prompt" แนบไปกับข้อความของผู้ใช้ เราจึงไม่ต้องแตะโค้ดหน้าเว็บเลย แค่ให้เซิร์ฟเวอร์เครื่องนี้ตอบสองเมธอดนี้
(ตรวจจาก bundle ที่ 8099 เสิร์ฟจริง: getAllPrompts() ข้ามเซิร์ฟเวอร์ที่ไม่มี serverCapabilities.prompts,
ช่องอาร์กิวเมนต์ใช้ id="arg-<name>" และ querySelector — ชื่ออาร์กิวเมนต์จึงต้องเป็นตัวอักษรอังกฤษ/ตัวเลข/_ เท่านั้น)

รูปแบบไฟล์ SKILL.md
-------------------
    ---
    name: ocpp-log-analysis          (ต้องตรงกับชื่อโฟลเดอร์ a-z 0-9 -)
    title_th: วิเคราะห์ log OCPP
    title_en: OCPP log analysis
    description: คำอธิบายภาษาไทย
    description_en: English description   (ไม่บังคับ)
    order: 10                        (ไม่บังคับ — ลำดับในรายการ น้อยขึ้นก่อน ค่าเริ่มต้น 100)
    arguments:
      - name: file                     (A-Z a-z 0-9 _ ขึ้นต้นด้วยตัวอักษร)
        description: ชื่อไฟล์ในไฟล์แนบ
        description_en: Attachment file name   (ไม่บังคับ)
        required: false
        default: standard              (ไม่บังคับ — ใช้เมื่อผู้ใช้เว้นว่าง)
        default_en: ...                (ไม่บังคับ — ค่าเริ่มต้นเมื่อหน้าเว็บเป็นภาษาอังกฤษ)
        complete: attachments          (ไม่บังคับ — attachments|outputs = เติมชื่อไฟล์ของโปรเจกต์ให้ตอนพิมพ์
                                        และค่าที่ใส่ถูกทำให้เป็น path ใต้โฟลเดอร์นั้นก่อนแทนค่า — ดู _file_arg
                                        แม่แบบจึงเขียน attachments/{{file}} ได้เสมอ)
    ---
    เนื้อแม่แบบ ใช้ {{file}} แทนค่า
    {{#file}}ส่วนนี้แสดงเมื่อ file ไม่ว่าง{{/file}}  {{^file}}ส่วนนี้แสดงเมื่อ file ว่าง{{/file}}

ชื่อสงวน (ขึ้นต้นด้วย _): _fast (ไม่ว่างเมื่อเรียกผ่านผิวย่อ /fast), _full, _project, _date, _lang, _th, _en,
_attachments, _outputs (path เต็มของโฟลเดอร์โปรเจกต์) — แม่แบบจึงเขียนการเรียกเครื่องมือให้ตรงกับผิวที่ผู้ใช้เปิดอยู่ได้
(ผิวย่อมี local_read/local_do ผิวเต็มมี read_file/doc_extract/... ชื่อไม่เหมือนกัน)

frontmatter เป็น YAML ชุดย่อยที่ตั้งใจให้เล็ก (ไม่พึ่ง PyYAML — ตัวเปิดอาจใช้ Python คนละตัว และพฤติกรรมต้องแน่นอน):
key: value, "สตริงแบบ JSON", 'สตริง', true/false, | และ > (หลายบรรทัด), รายการ "- " ของ mapping หรือ scalar,
และ JSON ในบรรทัดเดียว [..] {..} — ไม่รองรับคอมเมนต์ท้ายบรรทัด (ข้อความไทยมี # ได้ เช่น "ตู้ #3")

ความปลอดภัย
-----------
* C:\\LLM\\skills อยู่ในเขตห้ามเขียนของ guard: โมเดลสร้าง/แก้ skill ไม่ได้ ไม่งั้นข้อความในเว็บ/ไฟล์ที่หลอกโมเดลได้
  จะฝังคำสั่งถาวรลงในพรอมต์ที่ผู้ใช้เลือกใช้เองภายหลัง (skill = ข้อความที่ผู้ใช้เชื่อถือ)
* prompts/get หา skill จาก "ชื่อที่โหลดไว้แล้ว" เท่านั้น ไม่เคยประกอบ path จากคำขอ; โฟลเดอร์ที่ชี้ออกนอก skills (junction)
  ถูกข้าม; ไฟล์ใหญ่เกิน/มีอักขระควบคุมทิศทาง (bidi — "Trojan Source") ถูกปฏิเสธ
* แทนค่าอาร์กิวเมนต์รอบเดียว: ค่าที่ผู้ใช้พิมพ์ซึ่งมี {{...}} ไม่ถูกขยายซ้ำ (ส่วน/ตัวแปรของแม่แบบถูกแก้ก่อนแทนค่า)
* การเติมชื่อไฟล์ (completion/complete) อ่านแค่รายชื่อไฟล์ในโฟลเดอร์ของโปรเจกต์ที่อยู่ใน URL (S04 — ด่าน Origin/slug
  ของ server.py ผูกหน้าโปรเจกต์กับ slug แล้ว) ไม่ตามลิงก์ ไม่แสดงไฟล์ซ่อน/นามสกุลความลับ
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import guard

# ตั้ง env ได้เพื่อให้เทสต์/อินสแตนซ์ทดสอบใช้โฟลเดอร์จำลอง (เหมือน QWEN_MCP_PROJECT_DATA ของ guard)
SKILLS_DIR = Path(os.environ.get("QWEN_SKILLS_DIR") or r"C:\LLM\skills")
# ภาษาของหน้าเว็บอยู่ที่ hub (ทุกโปรเจกต์คนละพอร์ต จึงเก็บฝั่งเซิร์ฟเวอร์) — อ่านอย่างเดียว เอาแค่คีย์ lang
HUB_SETTINGS = Path(os.environ.get("QWEN_HUB_SETTINGS") or r"C:\LLM\projects\settings.json")
ENABLED_NAME = "enabled.json"            # รายการเปิด/ปิด skill ต่อโปรเจกต์ (ไม่บังคับ ไม่มี = เปิดทั้งหมด)

MAX_SKILL_BYTES = 64 * 1024
MAX_SKILLS = 100
MAX_ARGS = 10
MAX_ARG_CHARS = 20_000                   # ช่องอาร์กิวเมนต์ของ WebUI เป็น input บรรทัดเดียว ค่าจริงสั้นกว่านี้มาก
MAX_ARGS_TOTAL = 60_000
MAX_RENDER_CHARS = 120_000
MAX_COMPLETIONS = 20

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ARG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:(?:[ \t]+(.*))?$")
# อักขระควบคุมทิศทาง (Trojan Source) + NUL — ไม่ห้าม U+200B/U+2060 เพราะข้อความไทยใช้ตัดคำ/ยึดคำจริง
_BAD_CHARS_RE = re.compile("[\u202a-\u202e\u2066-\u2069\u200e\u200f\x00]")
_TAG = r"\{\{\s*([#^/])\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}"
_TAG_RE = re.compile(_TAG)
_STANDALONE_RE = re.compile(r"(?m)^[ \t]*(" + _TAG + r")[ \t]*\n")
_SECTION_RE = re.compile(r"\{\{\s*([#^])\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}(.*?)\{\{\s*/\s*\2\s*\}\}", re.S)
_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_ANY_MUSTACHE_RE = re.compile(r"\{\{.*?\}\}", re.S)

RESERVED = ("_fast", "_full", "_project", "_date", "_lang", "_th", "_en", "_attachments", "_outputs")
COMPLETE_KINDS = ("attachments", "outputs")
# เครื่องหมายคำพูดที่ผู้ใช้ติดมาตอนคัดลอกชื่อไฟล์ (จาก Explorer "Copy as path" ได้ "..." / จาก Markdown ได้ `...`)
_QUOTE_PAIRS = ('""', "''", "``", "<>", "“”", "‘’")
# path ที่ชี้ออกนอกโฟลเดอร์ของโปรเจกต์แน่ๆ: ไดรฟ์ (C:...), UNC (//server), โฮม (~/) — ไม่ใช่ "~$งาน.docx" ที่เป็นชื่อไฟล์จริง
_OUTSIDE_RE = re.compile(r"^(?:[A-Za-z]:|//|~(?:/|$))")


class SkillError(ValueError):
    """SKILL.md ผิดรูป — ข้าม skill นั้น (ตัวอื่นยังใช้ได้) และรายงานใน status()"""


class PromptError(Exception):
    """คำขอ prompts/get ใช้ไม่ได้ — server.py ตอบเป็น JSON-RPC error (ค่าเริ่มต้น -32602 invalid params ตามสเปก MCP)"""

    def __init__(self, message: str, code: int = -32602):
        super().__init__(message)
        self.code = code


@dataclass
class Arg:
    name: str
    description: str = ""
    description_en: str = ""
    required: bool = False
    default: str = ""
    default_en: str = ""
    complete: str = ""

    def default_for(self, lang: str) -> str:
        # หน้าเว็บภาษาอังกฤษต้องไม่โชว์/ไม่ใส่ค่าเริ่มต้นภาษาไทย (เช่น "ประมาณ 1 หน้า") ถ้าผู้เขียนให้ฉบับอังกฤษไว้
        return (self.default_en or self.default) if lang == "en" else (self.default or self.default_en)


@dataclass
class Skill:
    name: str
    title_th: str
    title_en: str
    description: str
    description_en: str
    body: str
    arguments: list = field(default_factory=list)
    folder: str = ""
    order: int = 100


# ------------------------------------------------------------------ frontmatter (YAML ชุดย่อย)
def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _next_sig(lines: list, i: int) -> int:
    """ดัชนีของบรรทัดถัดไปที่มีเนื้อหา (ข้ามบรรทัดว่างและบรรทัดคอมเมนต์ที่ขึ้นต้นด้วย #)"""
    while i < len(lines):
        s = lines[i].strip()
        if s and not s.startswith("#"):
            return i
        i += 1
    return i


def _scalar(val: str, ln: int):
    v = val.strip()
    if v.startswith('"'):
        try:
            out = json.loads(v)
        except ValueError:
            raise SkillError("บรรทัด %d: สตริงในเครื่องหมาย \" ไม่ถูกต้อง (ต้องปิดให้ครบ ใช้ \\\" แทน \" ข้างใน)" % ln)
        if not isinstance(out, str):
            raise SkillError("บรรทัด %d: ต้องเป็นสตริง" % ln)
        return out
    if v.startswith("'"):
        if len(v) < 2 or not v.endswith("'"):
            raise SkillError("บรรทัด %d: สตริงในเครื่องหมาย ' ไม่ได้ปิด" % ln)
        inner = v[1:-1]
        if re.search(r"(?<!')'(?!')", inner.replace("''", "")):
            raise SkillError("บรรทัด %d: ใช้ '' แทน ' ข้างในสตริง" % ln)
        return inner.replace("''", "'")
    if v.startswith("[") or v.startswith("{"):
        try:
            return json.loads(v)
        except ValueError:
            raise SkillError("บรรทัด %d: รายการแบบบรรทัดเดียวต้องเป็น JSON ที่ถูกต้อง" % ln)
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~"):
        return None
    return v


def _block_scalar(lines: list, i: int, parent_indent: int, style: str, ln0: int):
    """ค่าแบบหลายบรรทัด | (คงบรรทัด) หรือ > (พับเป็นย่อหน้า) — บรรทัดที่ย่อหน้าลึกกว่า key คือเนื้อ"""
    body = []
    while i < len(lines):
        line = lines[i]
        if line.strip() and _indent(line) <= parent_indent:
            break
        body.append(line)
        i += 1
    real = [b for b in body if b.strip()]
    if not real:
        return "", i
    cut = min(_indent(b) for b in real)
    rows = [b[cut:].rstrip() if b.strip() else "" for b in body]
    while rows and not rows[0]:
        rows.pop(0)
    while rows and not rows[-1]:
        rows.pop()
    if style == "|":
        return "\n".join(rows), i
    paras, cur = [], []
    for r in rows:
        if r:
            cur.append(r.strip())
        else:
            if cur:
                paras.append(" ".join(cur))
            cur = []
    if cur:
        paras.append(" ".join(cur))
    return "\n".join(paras), i


def _parse_map(lines: list, i: int, indent: int, ln0: int):
    out: dict = {}
    while True:
        i = _next_sig(lines, i)
        if i >= len(lines):
            return out, i
        line = lines[i]
        ind = _indent(line)
        if ind < indent:
            return out, i
        if ind > indent:
            raise SkillError("บรรทัด %d: ย่อหน้าไม่ตรงกับบรรทัดก่อนหน้า" % (ln0 + i))
        content = line[ind:].rstrip()
        m = _KEY_RE.match(content)
        if not m:
            if content.startswith("-"):
                return out, i                  # รายการที่ย่อหน้าเท่ากับ key ของมัน (ผู้เรียกจัดการ)
            raise SkillError("บรรทัด %d: ต้องเป็นรูป key: value" % (ln0 + i))
        key, val = m.group(1), (m.group(2) or "").strip()
        if key in out:
            raise SkillError("บรรทัด %d: key '%s' ซ้ำ" % (ln0 + i, key))
        i += 1
        if val in ("|", "|-", "|+", ">", ">-", ">+"):
            out[key], i = _block_scalar(lines, i, indent, val[0], ln0)
        elif val == "":
            j = _next_sig(lines, i)
            # รายการย่อหน้าลึกกว่า key หรือเท่ากับ key ก็ได้ (YAML ยอมทั้งสองแบบ คนเขียนมือใช้ปนกัน)
            if j < len(lines) and _indent(lines[j]) >= indent and lines[j][_indent(lines[j]):].startswith("-"):
                out[key], i = _parse_list(lines, j, _indent(lines[j]), ln0)
            elif j < len(lines) and _indent(lines[j]) > indent:
                raise SkillError("บรรทัด %d: mapping ซ้อนกันไม่รองรับ (ใช้รายการ \"- \" หรือ JSON บรรทัดเดียว)"
                                 % (ln0 + j))
            else:
                out[key] = ""
        else:
            out[key] = _scalar(val, ln0 + i - 1)


def _parse_list(lines: list, i: int, indent: int, ln0: int):
    items: list = []
    kind = None
    while True:
        i = _next_sig(lines, i)
        if i >= len(lines):
            break
        line = lines[i]
        ind = _indent(line)
        content = line[ind:].rstrip()
        if ind != indent or not (content == "-" or content.startswith("- ")):
            if ind > indent:
                raise SkillError("บรรทัด %d: ย่อหน้าในรายการไม่ตรง" % (ln0 + i))
            break
        rest = content[1:].lstrip(" ")
        if not rest:
            raise SkillError("บรรทัด %d: รายการว่าง" % (ln0 + i))
        col = ind + (len(content) - len(rest))
        if _KEY_RE.match(rest):
            if kind == "scalar":
                raise SkillError("บรรทัด %d: รายการผสม mapping กับค่าเดี่ยวไม่ได้" % (ln0 + i))
            kind = "map"
            lines[i] = " " * col + rest       # เขียนบรรทัดนี้ใหม่ให้เป็น key แรกของ mapping ที่คอลัมน์ col
            item, i = _parse_map(lines, i, col, ln0)
            items.append(item)
        else:
            if kind == "map":
                raise SkillError("บรรทัด %d: รายการผสม mapping กับค่าเดี่ยวไม่ได้" % (ln0 + i))
            kind = "scalar"
            items.append(_scalar(rest, ln0 + i))
            i += 1
    return items, i


def parse_frontmatter(text: str):
    """คืน (meta, body) — text ต้องขึ้นต้นด้วยบรรทัด --- และมี --- ปิด"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise SkillError("บรรทัด 1: ต้องขึ้นต้นด้วย --- (frontmatter)")
    end = next((k for k in range(1, len(lines)) if lines[k].strip() == "---"), None)
    if end is None:
        raise SkillError("ไม่พบ --- ปิด frontmatter")
    head = lines[1:end]
    for k, line in enumerate(head):
        if "\t" in line[:_indent(line) + 1] and line.strip():
            raise SkillError("บรรทัด %d: ใช้ช่องว่างย่อหน้า ห้ามใช้แท็บ" % (k + 2))
    meta, i = _parse_map(head, 0, 0, 2)
    i = _next_sig(head, i)
    if i < len(head):
        raise SkillError("บรรทัด %d: อ่าน frontmatter ต่อไม่ได้" % (i + 2))
    return meta, "\n".join(lines[end + 1:])


# ------------------------------------------------------------------ ตรวจความถูกต้อง
def _str(meta: dict, key: str, limit: int, where: str, required: bool = False) -> str:
    v = meta.get(key)
    if v is None or v == "":
        if required:
            raise SkillError("%s: ต้องมี %s" % (where, key))
        return ""
    if not isinstance(v, str):
        raise SkillError("%s: %s ต้องเป็นข้อความ" % (where, key))
    v = v.strip()
    if len(v) > limit:
        raise SkillError("%s: %s ยาวเกิน %d ตัวอักษร" % (where, key, limit))
    return v


def _sections_ok(body: str, names: set) -> None:
    """เปิด/ปิดส่วนต้องจับคู่กันครบ และทุกชื่อที่อ้างต้องมีจริง — จับพิมพ์ผิดตั้งแต่ตอนโหลด ไม่ใช่ตอนผู้ใช้กด"""
    for m in _TAG_RE.finditer(body):
        if m.group(2) not in names:
            raise SkillError("แม่แบบอ้าง {{%s%s}} ซึ่งไม่ใช่อาร์กิวเมนต์หรือชื่อสงวน" % (m.group(1), m.group(2)))
    for m in _VAR_RE.finditer(body):
        if m.group(1) not in names:
            raise SkillError("แม่แบบอ้าง {{%s}} ซึ่งไม่ใช่อาร์กิวเมนต์หรือชื่อสงวน" % m.group(1))
    for truthy in (True, False):
        ctx = {n: ("x" if truthy else "") for n in names}
        left = _resolve_sections(_prep(body), ctx)
        if _TAG_RE.search(left):
            raise SkillError("แท็กส่วน {{#x}} / {{^x}} / {{/x}} เปิด-ปิดไม่ครบคู่ (หรือซ้อนชื่อเดียวกัน)")
        stray = [s for s in _ANY_MUSTACHE_RE.findall(_VAR_RE.sub("", left))]
        if stray:
            raise SkillError("แม่แบบมี %s ที่อ่านไม่ออก" % stray[0][:40])


def build_skill(folder: str, text: str) -> Skill:
    if _BAD_CHARS_RE.search(text):
        raise SkillError("มีอักขระควบคุมทิศทาง (bidi) หรือ NUL — ปฏิเสธเพื่อกันข้อความซ่อน")
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    meta, body = parse_frontmatter(text)
    where = "SKILL.md"
    name = _str(meta, "name", 64, where) or folder
    if not NAME_RE.match(name):
        raise SkillError("name '%s' ต้องเป็น a-z 0-9 - (ยาวไม่เกิน 64)" % name[:70])
    if name != folder:
        raise SkillError("name '%s' ต้องตรงกับชื่อโฟลเดอร์ '%s'" % (name, folder))
    title_th = _str(meta, "title_th", 120, where)
    title_en = _str(meta, "title_en", 120, where)
    if not (title_th or title_en):
        raise SkillError("ต้องมี title_th หรือ title_en อย่างน้อยหนึ่งอย่าง")
    description = _str(meta, "description", 600, where, required=True)
    description_en = _str(meta, "description_en", 600, where)
    # ลำดับในรายการ (น้อยขึ้นก่อน) — WebUI คงลำดับที่เซิร์ฟเวอร์ส่งภายในเซิร์ฟเวอร์เดียวกัน
    order_raw = meta.get("order", 100)
    try:
        order = int(str(order_raw).strip())
    except ValueError:
        raise SkillError("order ต้องเป็นจำนวนเต็ม")
    if not 0 <= order <= 10_000:
        raise SkillError("order ต้องอยู่ระหว่าง 0-10000")
    raw_args = meta.get("arguments")
    if raw_args in (None, ""):
        raw_args = []
    if not isinstance(raw_args, list):
        raise SkillError("arguments ต้องเป็นรายการ")
    if len(raw_args) > MAX_ARGS:
        raise SkillError("arguments เกิน %d ตัว" % MAX_ARGS)
    args, seen = [], set()
    for n, item in enumerate(raw_args, 1):
        w = "arguments[%d]" % n
        if not isinstance(item, dict):
            raise SkillError("%s ต้องเป็น mapping {name, description, required}" % w)
        aname = _str(item, "name", 32, w, required=True)
        if not ARG_RE.match(aname):
            raise SkillError("%s: name '%s' ต้องขึ้นต้นด้วยตัวอักษรอังกฤษ ตามด้วย A-Z a-z 0-9 _ "
                             "(หน้าเว็บใช้เป็น id ของช่องกรอก)" % (w, aname))
        if aname in seen:
            raise SkillError("%s: name '%s' ซ้ำ" % (w, aname))
        seen.add(aname)
        req = item.get("required", False)
        if not isinstance(req, bool):
            raise SkillError("%s: required ต้องเป็น true หรือ false" % w)
        comp = _str(item, "complete", 20, w)
        if comp and comp not in COMPLETE_KINDS:
            raise SkillError("%s: complete ต้องเป็น %s" % (w, " หรือ ".join(COMPLETE_KINDS)))
        args.append(Arg(name=aname, description=_str(item, "description", 300, w),
                        description_en=_str(item, "description_en", 300, w), required=req,
                        default=_str(item, "default", 200, w), default_en=_str(item, "default_en", 200, w),
                        complete=comp))
    body = body.strip("\n")
    if not body.strip():
        raise SkillError("เนื้อแม่แบบว่าง")
    _sections_ok(body, set(seen) | set(RESERVED))
    return Skill(name=name, title_th=title_th, title_en=title_en, description=description,
                 description_en=description_en, body=body, arguments=args, folder=folder, order=order)


# ------------------------------------------------------------------ แม่แบบ
def _prep(body: str) -> str:
    """แท็กส่วนที่อยู่บรรทัดเดียวโดดๆ ไม่ทิ้งบรรทัดว่างไว้ (แบบ mustache "standalone")"""
    return _STANDALONE_RE.sub(r"\1", body + "\n")


def _resolve_sections(text: str, ctx: dict) -> str:
    # วนจนไม่เปลี่ยน: รอบแรกแก้ส่วนนอกสุด ส่วนในที่ชื่อต่างกันถูกแก้รอบถัดไป (เพดานกันวนไม่รู้จบ)
    for _ in range(32):
        new = _SECTION_RE.sub(
            lambda m: m.group(3) if (bool(ctx.get(m.group(2))) == (m.group(1) == "#")) else "", text)
        if new == text:
            return new
        text = new
    return text


def render(body: str, ctx: dict) -> str:
    """แก้ส่วนก่อน แล้วแทนค่าตัวแปร "รอบเดียว" — ค่าที่ผู้ใช้พิมพ์ซึ่งมี {{...}} จึงไม่ถูกขยายซ้ำ"""
    text = _resolve_sections(_prep(body), ctx)
    text = _VAR_RE.sub(lambda m: str(ctx.get(m.group(1), "")), text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ------------------------------------------------------------------ โหลด + cache
_CACHE = {"sig": None, "skills": {}, "errors": {}, "enabled": {}, "enabled_error": ""}
_LOCK = threading.Lock()
_LANG = {"key": None, "lang": "th"}


def _skills_dir() -> Path:
    return Path(SKILLS_DIR)


def _signature(base: Path):
    rows = []
    try:
        entries = sorted(os.scandir(base), key=lambda e: e.name)
    except OSError:
        return ("missing",)
    for e in entries:
        if e.name.startswith((".", "_")):
            continue
        p = os.path.join(e.path, "SKILL.md")
        try:
            st = os.stat(p)
            rows.append((e.name, st.st_mtime_ns, st.st_size))
        except OSError:
            rows.append((e.name, None, None))
    try:
        st = os.stat(base / ENABLED_NAME)
        rows.append(("\x00enabled", st.st_mtime_ns, st.st_size))
    except OSError:
        pass
    return tuple(rows)


def _inside(base: Path, p: str) -> bool:
    try:
        rb = os.path.normcase(os.path.realpath(str(base)))
        rp = os.path.normcase(os.path.realpath(p))
    except OSError:
        return False
    return rp == rb or rp.startswith(rb.rstrip("\\/") + os.sep)


def _load_enabled(base: Path):
    p = base / ENABLED_NAME
    if not p.is_file():
        return {}, ""
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {}, "%s: อ่านไม่ได้ (%s) — เปิดทุก skill" % (ENABLED_NAME, type(exc).__name__)
    out = {}
    if not isinstance(data, dict):
        return {}, "%s: ต้องเป็น object — เปิดทุก skill" % ENABLED_NAME
    rules = dict(data.get("projects") or {}) if isinstance(data.get("projects"), dict) else {}
    if isinstance(data.get("default"), dict):
        rules.setdefault("\x00default", data["default"])
    for key, rule in rules.items():
        if not isinstance(rule, dict):
            continue
        slug = key if key == "\x00default" else guard.project_slug(key)
        ent = {}
        for k in ("enabled", "disabled"):
            v = rule.get(k)
            if isinstance(v, list):
                ent[k] = frozenset(x for x in v if isinstance(x, str))
        if ent:
            out[slug] = ent
    return out, ""


def load_skills(force: bool = False):
    """คืน (skills {name: Skill}, errors {folder: ข้อความ}) — อ่านดิสก์ใหม่เฉพาะเมื่อไฟล์เปลี่ยน"""
    base = _skills_dir()
    sig = (str(base),) + _signature(base)
    with _LOCK:
        if not force and _CACHE["sig"] == sig:
            return _CACHE["skills"], _CACHE["errors"]
    skills, errors = {}, {}
    try:
        entries = sorted(os.scandir(base), key=lambda e: e.name)
    except OSError:
        entries = []
    for e in entries:
        if e.name.startswith((".", "_")):
            continue
        try:
            if not e.is_dir():
                continue
        except OSError:
            continue
        if len(skills) >= MAX_SKILLS:
            errors[e.name] = "เกินจำนวน skill สูงสุด %d" % MAX_SKILLS
            continue
        if not NAME_RE.match(e.name):
            errors[e.name] = "ชื่อโฟลเดอร์ต้องเป็น a-z 0-9 -"
            continue
        md = os.path.join(e.path, "SKILL.md")
        if not os.path.isfile(md):
            errors[e.name] = "ไม่มี SKILL.md"
            continue
        if not _inside(base, md):
            errors[e.name] = "SKILL.md ชี้ออกนอกโฟลเดอร์ skills (ลิงก์/junction) — ข้าม"
            continue
        try:
            if os.path.getsize(md) > MAX_SKILL_BYTES:
                raise SkillError("ไฟล์ใหญ่เกิน %d KB" % (MAX_SKILL_BYTES // 1024))
            with open(md, "rb") as fh:
                raw = fh.read(MAX_SKILL_BYTES + 1)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise SkillError("ต้องเป็น UTF-8")
            skills[e.name] = build_skill(e.name, text)
        except SkillError as exc:
            errors[e.name] = str(exc)
        except OSError as exc:
            errors[e.name] = "อ่านไม่ได้: %s" % type(exc).__name__
    enabled, en_err = _load_enabled(base)
    with _LOCK:
        _CACHE.update(sig=sig, skills=skills, errors=errors, enabled=enabled, enabled_error=en_err)
    return skills, errors


def _allowed(project: str, name: str) -> bool:
    rules = _CACHE.get("enabled") or {}
    rule = rules.get(guard.project_slug(project)) or rules.get("\x00default")
    if not rule:
        return True
    if "enabled" in rule:
        return name in rule["enabled"]
    return name not in rule.get("disabled", frozenset())


def ui_lang() -> str:
    """th|en ตามค่าตั้งของ hub (cache ตาม mtime) — อ่านไม่ได้ = th (ค่าเริ่มต้นของผู้ใช้)"""
    try:
        st = HUB_SETTINGS.stat()
        key = (str(HUB_SETTINGS), st.st_mtime_ns, st.st_size)
    except OSError:
        return "th"
    if _LANG["key"] == key:
        return _LANG["lang"]
    lang = "th"
    try:
        v = json.loads(HUB_SETTINGS.read_text(encoding="utf-8-sig")).get("lang")
        if v in ("th", "en"):
            lang = v
    except (OSError, ValueError, AttributeError):
        pass
    _LANG.update(key=key, lang=lang)
    return lang


def _msg(lang: str, th: str, en: str) -> str:
    return en if lang == "en" else th


def _title(s: Skill, lang: str) -> str:
    return (s.title_en or s.title_th) if lang == "en" else (s.title_th or s.title_en)


def _desc(th: str, en: str, lang: str) -> str:
    return (en or th) if lang == "en" else (th or en)


def _visible(project: str):
    skills, _errors = load_skills()
    return {n: s for n, s in skills.items() if _allowed(project, n)}


# ------------------------------------------------------------------ MCP methods
def list_prompts(project: str, fast: bool) -> list:
    lang = ui_lang()
    out = []
    visible = _visible(project)
    for s in sorted(visible.values(), key=lambda x: (x.order, x.name)):
        item = {"name": s.name, "title": _title(s, lang), "description": _desc(s.description, s.description_en, lang)}
        if s.arguments:
            args = []
            for a in s.arguments:
                d = _desc(a.description, a.description_en, lang)
                dflt = a.default_for(lang)
                if dflt:
                    d = (d + " " if d else "") + _msg(lang, "(ค่าเริ่มต้น: %s)", "(default: %s)") % dflt
                args.append({"name": a.name, "description": d, "required": bool(a.required)})
            item["arguments"] = args
        out.append(item)
    return out


def _context(project: str, fast: bool, lang: str) -> dict:
    slug = guard.project_slug(project)
    base = Path(guard.PROJECT_DATA) / slug
    return {"_fast": "1" if fast else "", "_full": "" if fast else "1", "_project": slug,
            "_date": time.strftime("%Y-%m-%d"), "_lang": lang,
            "_th": "1" if lang == "th" else "", "_en": "1" if lang == "en" else "",
            "_attachments": str(base / "attachments"), "_outputs": str(base / "outputs")}


def _file_arg(value: str, kind: str, project: str, fast: bool, lang: str) -> str:
    """ค่าของอาร์กิวเมนต์ที่มี complete: attachments|outputs -> path "ใต้โฟลเดอร์นั้น" ก่อนแทนลงแม่แบบ

    ทำไม: แม่แบบเขียน path="attachments/{{file}}" (ผิวย่อ) และ {{_attachments}}\\{{file}} (ผิวเต็ม) ไว้เองแล้ว
    ผู้ใช้ที่วาง "attachments/x.pdf" หรือ path เต็มของโฟลเดอร์โปรเจกต์ จึงได้ attachments/attachments/x.pdf ที่หาไม่เจอ
    (integrator พบ) และ Qwen3-4B ไม่แก้ path ให้เอง มันยอมแพ้แล้วถามผู้ใช้ — ต้องแก้ตั้งแต่ตอนแทนค่า
    * ตัดเครื่องหมายคำพูด, แปลง \\ เป็น /, ตัด "./", "<kind>/" และ path เต็มของโฟลเดอร์นี้ของโปรเจกต์นี้ออก
    * path นอกโฟลเดอร์ (ไดรฟ์อื่น/UNC/~/"..") หรือโฟลเดอร์อีกชนิด (outputs/ ในช่อง attachments) -> PromptError ที่บอกวิธีแก้
      แทนการส่ง path ผิดๆ ให้โมเดล (ขอบเขต S04 ยังบังคับโดยเครื่องมือ ข้อนี้แค่ทำให้ผู้ใช้รู้ตั้งแต่ตอนกด)
    * ชื่อที่พิมพ์ตัวพิมพ์เล็ก/ใหญ่ไม่ตรง แต่ตรงกับไฟล์เดียวในโฟลเดอร์ -> ใช้ชื่อจริง (ไม่เดาด้วยความคล้าย: ผิดไฟล์เงียบๆ แย่กว่า)
    ผิวย่อคืน a/b.pdf ผิวเต็มคืน a\\b.pdf ให้ต่อกับ {{_attachments}}\\ ได้ path แบบ Windows ล้วน
    """
    import unicodedata
    v = value
    for _ in range(2):
        if len(v) >= 2 and (v[0] + v[-1]) in _QUOTE_PAIRS:
            v = v[1:-1].strip()
    v = unicodedata.normalize("NFC", v.replace("\\", "/"))
    data = Path(guard.PROJECT_DATA) / guard.project_slug(project)
    data_s = str(data).replace("\\", "/").rstrip("/")
    folder = data / kind
    other = [k for k in COMPLETE_KINDS if k != kind]
    low = v.casefold()
    hint = _msg(lang, "ใส่ชื่อไฟล์ใน %s ของโปรเจกต์นี้ (เลือกจากรายการที่ขึ้นตอนพิมพ์) — ไฟล์ที่อยู่ที่อื่นให้แนบเข้าโปรเจกต์ก่อน",
                "enter the name of a file in this project's %s (pick one from the suggestions) — "
                "attach files from elsewhere to the project first") % kind
    rooted = False
    if low.startswith(data_s.casefold() + "/"):
        v = v[len(data_s) + 1:]
        rooted = True                      # ตอนนี้เทียบกับโฟลเดอร์โปรเจกต์แล้ว ต้องขึ้นต้นด้วย <kind>/
    elif low == data_s.casefold() or _OUTSIDE_RE.match(v):
        raise PromptError(hint)            # รวม path เต็มของ "โปรเจกต์อื่น" — ไม่ส่ง path ข้ามโปรเจกต์ให้โมเดล (S04)
    while v.startswith("./") or v.startswith("/"):
        v = v[2:] if v.startswith("./") else v[1:]
    v = re.sub(r"/{2,}", "/", v).rstrip("/")
    parts = v.split("/")
    if ".." in parts:
        raise PromptError(hint)
    head = parts[0].casefold()

    def exists(p: Path) -> bool:
        try:
            return p.exists()
        except (OSError, ValueError):      # ชื่อที่ Windows ไม่รับ (<>|?*) = ไม่มีไฟล์นั้น ไม่ใช่ error ของพรอมต์
            return False

    if head == kind and (rooted or not exists(folder / v)):
        v = "/".join(parts[1:])            # "attachments/x.pdf" -> "x.pdf" (เว้นแต่มีโฟลเดอร์ชื่อ attachments ข้างในจริง)
    elif rooted or (head in other and len(parts) > 1 and not exists(folder / v)):
        if head in other:
            # ไฟล์อยู่อีกโฟลเดอร์ของโปรเจกต์ แต่แม่แบบนี้อ่านจาก <kind> — บอกตอนกด ดีกว่าให้โมเดลหาไม่เจอแล้วเดา
            raise PromptError(_msg(lang, "ทักษะนี้อ่านไฟล์จาก %s — %s อยู่ใน %s",
                                   "this skill reads files from %s — %s is in %s")
                              % (kind, "/".join(parts[1:])[:120], head))
        raise PromptError(hint)
    if v and "/" not in v:
        # NTFS ไม่สนตัวพิมพ์ ไฟล์จึง "มีอยู่" แม้พิมพ์ SCAN.PDF — แต่ส่งชื่อจริงให้โมเดล จะได้ตรงกับที่ list/kb แสดง
        try:
            names = [e.name for e in os.scandir(folder)]
        except OSError:
            names = []
        if v not in names:
            want = v.casefold()
            same = [n for n in names if unicodedata.normalize("NFC", n).casefold() == want]
            if len(same) == 1:
                v = same[0]
    return v if fast else v.replace("/", "\\")


def get_prompt(project: str, fast: bool, name, arguments) -> dict:
    lang = ui_lang()
    if not isinstance(name, str) or not name:
        raise PromptError(_msg(lang, "ต้องระบุชื่อพรอมต์", "prompt name is required"))
    s = _visible(project).get(name)
    if s is None:
        raise PromptError(_msg(lang, "ไม่รู้จักพรอมต์: %s", "unknown prompt: %s") % name[:80])
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise PromptError(_msg(lang, "arguments ต้องเป็น object", "arguments must be an object"))
    known = {a.name: a for a in s.arguments}
    values, total = {}, 0
    for k, v in arguments.items():
        if k not in known:
            continue                       # ไม่รู้จัก = ข้าม (ไคลเอนต์บางตัวส่งช่องว่างมาครบทุกช่อง)
        if v is None:
            continue
        if not isinstance(v, str):
            raise PromptError(_msg(lang, "ค่าของ %s ต้องเป็นข้อความ", "value of %s must be a string") % k)
        v = v.replace("\x00", "").strip()
        if len(v) > MAX_ARG_CHARS:
            raise PromptError(_msg(lang, "ค่าของ %s ยาวเกิน %d ตัวอักษร — แนบเป็นไฟล์หรือวางในข้อความแทน",
                                   "value of %s is longer than %d characters — attach it or paste it in the message")
                              % (k, MAX_ARG_CHARS))
        total += len(v)
        if v and known[k].complete:
            v = _file_arg(v, known[k].complete, project, fast, lang)
        values[k] = v
    if total > MAX_ARGS_TOTAL:
        raise PromptError(_msg(lang, "อาร์กิวเมนต์รวมกันยาวเกินไป", "arguments are too long in total"))
    missing = [a.name for a in s.arguments if a.required and not values.get(a.name)]
    if missing:
        raise PromptError(_msg(lang, "ต้องกรอก: %s", "missing required argument(s): %s") % ", ".join(missing))
    ctx = _context(project, fast, lang)
    for a in s.arguments:
        ctx[a.name] = values.get(a.name) or a.default_for(lang)
    text = render(s.body, ctx)
    if len(text) > MAX_RENDER_CHARS:
        raise PromptError(_msg(lang, "ผลของพรอมต์ยาวเกินไป", "rendered prompt is too long"))
    return {"description": _desc(s.description, s.description_en, lang),
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}


def _blocked_suffixes() -> tuple:
    try:
        return tuple(guard.DEFAULTS.get("blocked_suffixes") or ())
    except AttributeError:
        return ()


def complete(project: str, fast: bool, ref, argument) -> dict:
    """completion/complete ของอาร์กิวเมนต์ที่มี complete: attachments|outputs — ชื่อไฟล์ของโปรเจกต์นี้ที่ตรงกับที่พิมพ์
    ไม่รู้จัก/ไม่รองรับ = รายการว่าง (หน้าเว็บเรียกทุกครั้งที่พิมพ์ ไม่ควรขึ้น error)"""
    empty = {"completion": {"values": [], "total": 0, "hasMore": False}}
    if not isinstance(ref, dict) or ref.get("type") != "ref/prompt" or not isinstance(argument, dict):
        return empty
    s = _visible(project).get(ref.get("name"))
    if s is None:
        return empty
    arg = next((a for a in s.arguments if a.name == argument.get("name")), None)
    if arg is None or not arg.complete:
        return empty
    value = argument.get("value")
    value = value.strip().casefold() if isinstance(value, str) else ""
    folder = Path(guard.PROJECT_DATA) / guard.project_slug(project) / arg.complete
    bad = _blocked_suffixes()
    names = []
    try:
        for e in os.scandir(folder):
            try:
                if e.name.startswith(".") or not e.is_file(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if bad and e.name.lower().endswith(bad):
                continue
            names.append(e.name)
    except OSError:
        return empty
    hits = [n for n in names if value in n.casefold()]
    hits.sort(key=lambda n: (not n.casefold().startswith(value), n.casefold()))
    return {"completion": {"values": hits[:MAX_COMPLETIONS], "total": len(hits),
                           "hasMore": len(hits) > MAX_COMPLETIONS}}


def status() -> dict:
    """สรุปสำหรับ GET สถานะของ server.py (ต้องมี Bearer) — ชื่อ skill ที่ใช้ได้ และตัวที่โหลดไม่ได้พร้อมเหตุผล"""
    skills, errors = load_skills()
    out = {"dir": str(_skills_dir()), "count": len(skills), "names": sorted(skills), "failed": dict(errors)}
    if _CACHE.get("enabled_error"):
        out["enabled_error"] = _CACHE["enabled_error"]
    return out
