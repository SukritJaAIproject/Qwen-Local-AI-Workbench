# -*- coding: utf-8 -*-
"""office_helper.py — ตัวคุยกับ Excel/Word/PowerPoint ที่ผู้ใช้เปิดอยู่ ผ่าน COM (สัญญา C2 "Office bridge")

ทำไมต้องแยกเป็นโปรเซส
----------------------
MCP (tools_office.py) รันบน C:\\Python313 ซึ่งไม่มี pywin32 (และห้ามติดตั้งเพิ่ม) ส่วน anaconda ของผู้ใช้มี
win32com อยู่แล้ว ไฟล์นี้จึงถูกเรียกด้วย anaconda python ทีละครั้ง: รับคำขอ JSON หนึ่งก้อนทาง stdin
ตอบ JSON หนึ่งก้อนทาง stdout แล้วจบ — ถ้า Office ค้าง (กล่องโต้ตอบเปิดอยู่) ฝั่ง MCP ฆ่าโปรเซสนี้ทิ้งได้ที่ 30 วินาที
โดยไม่ลาก MCP ทั้งตัวค้างไปด้วย และ COM ของ Office ไม่เคยถูกโหลดเข้าโปรเซสของ MCP เลย

กฎที่ไฟล์นี้ยึด (อ่านก่อนแก้)
-----------------------------
* ไม่เปิด Office เอง: ใช้ GetActiveObject / ROT เท่านั้น ห้าม Dispatch/DispatchEx/GetObject(path) — สามตัวนั้น
  "เปิดโปรแกรม/เปิดไฟล์ให้" ได้ถ้ายังไม่เปิด (ผู้ใช้ไม่ได้ขอ และจะมี EXCEL.EXE ค้างมองไม่เห็นในเครื่อง)
* ไม่บันทึก ไม่ปิด ไม่ Activate เอกสารของผู้ใช้ — ไม่มีคำสั่ง Save/SaveAs/Close/Quit/Activate ในไฟล์นี้เลย
  (เทสต์ test_office_unit.HelperProcessTests ตรวจข้อความในไฟล์นี้ตรงๆ) การเขียนแก้แค่เนื้อหาในหน่วยความจำ ผู้ใช้ตัดสินใจบันทึกเอง
* การเขียน (excel_write / word_write) ต้องมี expect = ลายนิ้วมือของเป้าหมายตอนออก token ถ้าเป้าหมายเปลี่ยน
  (ผู้ใช้แก้เซลล์ เปลี่ยนชื่อชีต แก้เอกสาร ปิดไฟล์) = ไม่เขียนเลย — คนอนุมัติ REVIEW ของสภาพเดิม ไม่ใช่สภาพใหม่
  ด่าน confirm_token/REVIEW อยู่ที่ tools_office + guard (ฝั่ง MCP) ไฟล์นี้ไม่รู้จัก token และไม่ตัดสินสิทธิ์
* ใช้ dynamic dispatch เสมอ: ถ้าเครื่องเคยมี gen_py (makepy) ของ Excel อ็อบเจกต์จะกลายเป็น early-bound
  ซึ่งพฤติกรรมของพร็อพเพอร์ตีที่มีพารามิเตอร์ต่างกัน — และห้ามใช้ Range.Resize/Offset แบบ dynamic
  (เจอจริง: Resize(2,4) ไปเรียก Item(2,4) ได้เซลล์เดียว) ใช้ ws.Range(ws.Cells(..), ws.Cells(..)) แทน
* โหมดเทสต์ (env QWEN_OFFICE_FENCE = path เต็มของเอกสารทดสอบ คั่นด้วย os.pathsep): มองเห็น/แตะได้เฉพาะเอกสารใน
  รายการนี้เท่านั้น แม้ผู้ใช้จะเปิด Excel ของตัวเองอยู่ในอินสแตนซ์เดียวกัน — ตัวแปรนี้ "แคบลง" อย่างเดียว ไม่เคยขยายสิทธิ์
  QWEN_OFFICE_RESOLVE=fence = หาเอกสารจาก ROT ตาม path ในรายการ แทน Active* (ไม่ต้องพึ่งว่าหน้าต่างไหนอยู่หน้า)
"""
from __future__ import annotations

import datetime as _dt
import decimal
import hashlib
import json
import os
import re
import sys
import time

PROGIDS = {"excel": "Excel.Application", "word": "Word.Application", "powerpoint": "PowerPoint.Application"}
EXES = {"excel": "excel.exe", "word": "winword.exe", "powerpoint": "powerpnt.exe"}
APP_NAMES = {"microsoft excel": "excel", "microsoft word": "word", "microsoft powerpoint": "powerpoint"}

# HRESULT ที่แปลว่า "Office ไม่ว่างชั่วคราว" (กำลังแก้ไขเซลล์/มีกล่องโต้ตอบ) — ลองใหม่สั้นๆ ก่อนยอมแพ้
BUSY_HR = {-2147418111,   # RPC_E_CALL_REJECTED
           -2147417846,   # RPC_E_SERVERCALL_RETRYLATER
           -2146777998}   # VBA_E_IGNORE (Excel อยู่ในโหมดแก้ไขเซลล์)
MK_E_UNAVAILABLE = -2147221021
CO_E_CLASSSTRING = -2147221005
BUSY_BUDGET = 8.0          # วินาทีที่ยอมรอ Office ว่าง (ทั้งหมดต้องจบก่อนเพดาน 30 วินาทีของฝั่ง MCP)

# ค่า error ของ Excel ที่ COM ส่งมาเป็น int (CVErr: 0x800A0000 + รหัส)
XL_ERRORS = {2000: "#NULL!", 2007: "#DIV/0!", 2015: "#VALUE!", 2023: "#REF!", 2029: "#NAME?",
             2036: "#NUM!", 2042: "#N/A", 2043: "#GETTING_DATA", 2045: "#SPILL!", 2046: "#CONNECT!",
             2047: "#BLOCKED!", 2048: "#UNKNOWN!", 2049: "#FIELD!", 2050: "#CALC!"}
XL_ERR_BASE = -2146828288   # = 0x800A0000 เป็นจำนวนเต็มมีเครื่องหมาย

# เพดานฝั่งอ่าน (tools_office ส่งค่าที่เล็กกว่านี้มาได้ แต่เกินนี้ไม่ได้ — กันคำขอแปลกๆ ดึงทั้งชีตล้านแถว)
HARD_MAX_CELLS = 5000
HARD_MAX_COLS = 60
HARD_MAX_ROWS = 1000
HARD_MAX_CHARS = 60000
MAX_FORMULAS = 60
WORD_HASH_MAX = 8_000_000   # เอกสารยาวกว่านี้ (ตัวอักษร) ใช้ความยาว+ส่วนหัวท้ายแทนการ hash ทั้งก้อน

_A1_CELL = r"\$?[A-Za-z]{1,3}\$?\d{1,7}"
_A1_RE = re.compile(r"^(?:%s(?::%s)?|\$?[A-Za-z]{1,3}:\$?[A-Za-z]{1,3}|\$?\d{1,7}:\$?\d{1,7})$" % (_A1_CELL, _A1_CELL))

# [fix-office b2b 2026-10-06] ด่านสุดท้ายของสูตรก่อนเขียนลง Excel — ชื่อที่อยู่หน้า "!" ต้องเป็นชีตของสมุดงานนี้เท่านั้น
# ทำไม: ='C:\…\x.xlsx'!Name หรือ ='\\host\share\x.xlsx'!N ไม่มี "[" หรือ "|" จึงหลุดรายการฟังก์ชันปลอดภัยของ tools_docs
# (ผู้ตรวจลองจริง: HasFormula=True, Excel อ่านค่าจากไฟล์ที่ปิดอยู่ได้ และ LinkSources มีไฟล์นั้น) — UNC = Excel ต่อ SMB ไปเครื่อง
# อื่นทันทีที่กดอนุญาต (ส่ง NTLM ออก) และลิงก์ค้างในสมุดงาน; ส่วนสูตรที่อ้างชีตที่ไม่มี Excel เปิดกล่อง "Update Values" ค้างรอคน
# ฝั่ง MCP (tools_office) กันไว้ก่อนออก token แล้ว ไฟล์นี้ตรวจซ้ำกับรายชื่อชีตจริง ณ ตอนเขียน (ชื่อชีตเปลี่ยนระหว่างรออนุมัติได้)
# แหล่งเดียว: tools_office import ฟังก์ชันชุดนี้จากไฟล์นี้ไปใช้ตอนออก token (ระดับโมดูลมีแค่ไลบรารีมาตรฐาน — ห้าม import COM
# ที่ระดับบนสุดของไฟล์นี้ ไม่งั้นโปรเซส MCP จะโหลด pywin32/COM ตาม)
_REF_STOP = frozenset(" \t\r\n=+-*/^&,;(){}<>%!@'\"")
_PATHISH_RE = re.compile(r"[\[\]\\/|?*<>\"]")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_FILE_EXT_RE = re.compile(r"(?i)\.(?:xl[a-z]{0,2}|csv|ods|txt|prn|dif|slk|dbf|xml|html?|mht(?:ml)?|iqy|odc|[dor]qy)$")
_CELLISH_RE = re.compile(r"^\$?[A-Za-z]{1,3}\$?\d{1,7}$|^\$?[A-Za-z]{1,3}$|^\$?\d{1,7}$")
_MACRO_EXT = (".xlsm", ".xlsb", ".xltm", ".xlam", ".xla", ".docm", ".dotm")


def formula_qualifiers(f):
    """ชื่อหน้าเครื่องหมาย ! ทุกตัวในสูตร (ไม่นับในสตริง "...") — None = แยกไม่ได้ (เครื่องหมายคำพูดไม่ครบ / '…' ลอยๆ)"""
    s = str(f or "")
    out, i, n = [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch == '"':
            j = i + 1
            while True:
                k = s.find('"', j)
                if k < 0:
                    return None
                if k + 1 < n and s[k + 1] == '"':
                    j = k + 2
                    continue
                break
            i = k + 1
            continue
        if ch == "'":
            j, parts = i + 1, []
            while True:
                k = s.find("'", j)
                if k < 0:
                    return None
                parts.append(s[j:k])
                if k + 1 < n and s[k + 1] == "'":
                    parts.append("'")
                    j = k + 2
                    continue
                break
            i = k + 1
            if i < n and s[i] == "!":
                out.append("".join(parts))
                i += 1
                continue
            return None                       # '…' ที่ไม่ตามด้วย ! ไม่มีในสูตรปกติ — ไม่เดา
        if ch == "!":
            j = i
            while j > 0 and s[j - 1] not in _REF_STOP:
                j -= 1
            out.append(s[j:i])
        i += 1
    return out


def formula_ref_problem(f, sheets=None) -> str:
    """"" = อ้างแค่ชีตในสมุดงานนี้ | "extref" = อ้างไฟล์/สมุดงาน/เครื่องอื่น | "sheetref" = ชีตที่ไม่มี |
    "malformed" = แยกชื่อหน้า ! ไม่ได้ (ถือว่าไม่ปลอดภัย) — sheets=None = ตรวจแค่รูปแบบ (ยังไม่รู้รายชื่อชีต)"""
    quals = formula_qualifiers(f)
    if quals is None:
        return "malformed"
    names = None if sheets is None else {str(x).casefold() for x in sheets}
    for q in quals:
        if not q.strip() or _PATHISH_RE.search(q) or _DRIVE_RE.match(q):
            return "extref"
        parts = q.split(":")
        if any(_FILE_EXT_RE.search(p.strip()) for p in parts):
            return "extref"
        if names is not None:
            # "A1:Sheet1" = ช่วงต่อจาก Sheet1!… (=Sheet1!A1:Sheet1!B2) ไม่ใช่ 3 มิติ — ส่วนหน้าที่เป็นที่อยู่เซลล์ไม่ใช่ชื่อชีต
            check = parts[1:] if len(parts) > 1 and _CELLISH_RE.match(parts[0]) else parts
            if any(p.casefold() not in names for p in check):
                return "sheetref"
    return ""


def _has_vba(doc):
    """เอกสารมีโปรเจกต์ VBA ไหม (True/False) — อ่านไม่ได้ = None (ผู้เรียกดูนามสกุลแทน)
    HasVBProject ไม่ต้องเปิด "Trust access to the VBA project" (ไม่แตะค่าความปลอดภัยของ Office)"""
    try:
        return bool(doc.HasVBProject)
    except (pywintypes.com_error, AttributeError):
        return None
# [/fix-office b2b]

pythoncom = pywintypes = client = dynamic = None


class Refuse(Exception):
    """ทำต่อไม่ได้ด้วยเหตุผลที่ต้องบอกผู้ใช้ (code ให้ tools_office แปลเป็นข้อความไทยที่ถูกบริบท)"""

    def __init__(self, code: str, msg: str = "", **extra):
        super().__init__(msg or code)
        self.code, self.msg, self.extra = code, msg or code, extra


# ------------------------------------------------------------------ fence (โหมดเทสต์)
def _fence() -> set:
    raw = os.environ.get("QWEN_OFFICE_FENCE") or ""
    return {os.path.normcase(os.path.normpath(p.strip())) for p in raw.split(os.pathsep) if p.strip()}


FENCE = _fence()
RESOLVE_FENCE = bool(FENCE) and (os.environ.get("QWEN_OFFICE_RESOLVE") or "").strip().lower() == "fence"


def _in_fence(full: str) -> bool:
    if not FENCE:
        return True
    try:
        return os.path.normcase(os.path.normpath(str(full or ""))) in FENCE
    except (TypeError, ValueError):
        return False


# ------------------------------------------------------------------ ตัวช่วย COM
def _hr(exc) -> int:
    try:
        return int(exc.args[0])
    except (AttributeError, IndexError, TypeError, ValueError):
        return 0


def _inner_hr(exc) -> int:
    """HRESULT ชั้นใน (excepinfo) — Excel ห่อ VBA_E_IGNORE ไว้ใน DISP_E_EXCEPTION"""
    try:
        info = exc.args[2]
        return int(info[5]) if info and len(info) > 5 and info[5] is not None else 0
    except (AttributeError, IndexError, TypeError, ValueError):
        return 0


def _is_busy(exc) -> bool:
    return _hr(exc) in BUSY_HR or _inner_hr(exc) in BUSY_HR


def _com_text(exc) -> str:
    """ข้อความอธิบายของ com_error (ของ Office เองถ้ามี) ตัดสั้น — ห้ามคืน traceback"""
    try:
        info = exc.args[2]
        if info and len(info) > 2 and info[2]:
            return str(info[2]).strip()[:300]
        return str(exc.args[1])[:300]
    except (AttributeError, IndexError, TypeError):
        return type(exc).__name__


def retry(fn, budget: float = BUSY_BUDGET):
    """เรียก fn ซ้ำขณะ Office ตอบว่าไม่ว่าง — ใช้กับขั้นที่ทำซ้ำได้ปลอดภัยเท่านั้น (อ่าน / ตรวจลายนิ้วมือ / การเขียนครั้งเดียว
    ที่ถูกปฏิเสธทั้งก้อน) ไม่ห่อทั้งขั้นเขียนที่มีหลายคำสั่ง เพราะลองซ้ำหลังเขียนไปครึ่งหนึ่งจะเห็นว่า "เป้าหมายเปลี่ยน" เอง"""
    end = time.monotonic() + budget
    while True:
        try:
            return fn()
        except pywintypes.com_error as exc:
            if not _is_busy(exc) or time.monotonic() > end:
                raise
            time.sleep(0.4)


def _typename(obj) -> str:
    try:
        return str(obj._oleobj_.GetTypeInfo().GetDocumentation(-1)[0]).lstrip("_")
    except Exception:          # noqa: BLE001 — ไม่รู้ชนิดก็แค่ตอบว่าไม่รู้
        return ""


def _dyn(obj):
    """ห่อเป็น dynamic dispatch เสมอ (ดูหัวไฟล์ — ไม่พึ่ง gen_py ที่อาจมี/ไม่มีในเครื่อง)"""
    return dynamic.Dispatch(obj._oleobj_ if hasattr(obj, "_oleobj_") else obj)


_EXE_NAMES: set | None = None    # ชื่อ .exe ของทุกโปรเซส — สำรวจครั้งเดียวต่อคำขอ (ตัวช่วยอายุสั้น ค่าไม่เก่าทัน)


def _toolhelp_names() -> set | None:
    """ชื่อ .exe ทุกโปรเซสจาก snapshot เดียวของ Toolhelp32 (ctypes ล้วน ไม่ต้องเปิดโปรเซสใด)
    วัดจริง 2026-10-06: psutil.process_iter(["name"]) ใช้ ~4 วินาทีต่อครั้งบนเครื่องนี้ (ต้อง OpenProcess ทีละตัว
    แล้วถอยไปทางช้าเมื่อโดนโปรเซสที่ป้องกันไว้) — op=list เรียก 3 ครั้งตอน Office ไม่ได้เปิด = 12-14 วินาที
    เสี่ยงชนเพดาน 30 วินาทีเมื่อเครื่องยุ่ง snapshot นี้ใช้ไม่ถึง 50 ms"""
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        snap = k32.CreateToolhelp32Snapshot(0x2, 0)                  # TH32CS_SNAPPROCESS
        if not snap or snap == ctypes.c_void_p(-1).value:            # INVALID_HANDLE_VALUE
            return None
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            names = set()
            ok = k32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                names.add(str(entry.szExeFile).lower())
                ok = k32.Process32NextW(snap, ctypes.byref(entry))
            return names or None
        finally:
            k32.CloseHandle(snap)
    except Exception:          # noqa: BLE001 — ใช้ไม่ได้ก็ถอยไป psutil
        return None


def _psutil_names() -> set | None:
    try:
        import psutil
        return {(p.info.get("name") or "").lower() for p in psutil.process_iter(["name"])}
    except Exception:          # noqa: BLE001
        return None


def _process_running(kind: str) -> bool | None:
    """มีโปรเซสของโปรแกรมนี้อยู่ไหม (แยก "เปิดอยู่แต่เชื่อมต่อไม่ได้" ออกจาก "ไม่ได้เปิด") — None = ตรวจไม่ได้"""
    global _EXE_NAMES
    if _EXE_NAMES is None:
        _EXE_NAMES = _toolhelp_names() or _psutil_names()
    if _EXE_NAMES is None:
        return None
    return EXES[kind] in _EXE_NAMES


def _rot_fence_docs() -> list:
    """เอกสารในรายการ fence ที่เปิดอยู่จริง หาจาก ROT ด้วยชื่อ moniker (path เต็ม) — ไม่ใช้ GetObject(path)
    เพราะถ้าไฟล์ยังไม่เปิด GetObject จะสั่ง Office เปิดไฟล์ให้เงียบๆ"""
    out = []
    rot = pythoncom.GetRunningObjectTable()
    ctx = pythoncom.CreateBindCtx(0)
    for mk in rot:
        try:
            name = mk.GetDisplayName(ctx, None)
        except pywintypes.com_error:
            continue
        if not _in_fence(name):
            continue
        try:
            obj = rot.GetObject(mk).QueryInterface(pythoncom.IID_IDispatch)
            out.append(dynamic.Dispatch(obj))
        except pywintypes.com_error:
            continue
    return out


def _doc_kind(doc) -> str:
    try:
        return APP_NAMES.get(str(doc.Application.Name).strip().lower(), "")
    except pywintypes.com_error:
        return ""


def get_app(kind: str):
    """(app, state) — state: running | not_running | unreachable | not_installed
    ไม่เปิดโปรแกรมเองเด็ดขาด: GetActiveObject คืน error ถ้าโปรแกรมยังไม่เปิด"""
    if RESOLVE_FENCE:
        for doc in _rot_fence_docs():
            if _doc_kind(doc) == kind:
                return _dyn(doc.Application), "running"
        return None, "not_running"
    try:
        clsid = pywintypes.IID(PROGIDS[kind])
    except pywintypes.com_error:
        return None, "not_installed"
    try:
        obj = pythoncom.GetActiveObject(clsid)
        return dynamic.Dispatch(obj.QueryInterface(pythoncom.IID_IDispatch)), "running"
    except pywintypes.com_error as exc:
        if _hr(exc) == CO_E_CLASSSTRING:
            return None, "not_installed"
        # เปิดอยู่แต่ยังไม่ลงทะเบียนใน ROT (Office ลงทะเบียนตอนหน้าต่างเสียโฟกัสครั้งแรก) หรือรันด้วยสิทธิ์ต่างกัน
        return None, ("unreachable" if _process_running(kind) else "not_running")


def _docs_of(app, kind: str) -> list:
    coll = {"excel": "Workbooks", "word": "Documents", "powerpoint": "Presentations"}[kind]
    items = []
    c = getattr(app, coll)
    for i in range(1, int(c.Count) + 1):
        try:
            items.append(c.Item(i))
        except pywintypes.com_error:
            continue
    return [d for d in items if _in_fence(_full(d))]


def _full(doc) -> str:
    try:
        return str(doc.FullName or "")
    except pywintypes.com_error:
        return ""


def _doc_info(doc) -> dict:
    info = {"name": "", "full": "", "path": "", "saved": None, "readonly": None}
    for key, attr in (("name", "Name"), ("full", "FullName"), ("path", "Path")):
        try:
            info[key] = str(getattr(doc, attr) or "")
        except pywintypes.com_error:
            pass
    for key, attr in (("saved", "Saved"), ("readonly", "ReadOnly")):
        try:
            info[key] = bool(getattr(doc, attr))          # PowerPoint ตอบ msoTrue = -1 ซึ่ง bool() ก็เป็น True
        except pywintypes.com_error:
            pass
    return info


def _active_doc(app, kind: str):
    """เอกสารที่ใช้งานอยู่ (โหมดเทสต์ = เอกสารแรกในรายการ fence ของโปรแกรมนี้) — ต้องอยู่ใน fence เสมอ"""
    if RESOLVE_FENCE:
        docs = _docs_of(app, kind)
        if not docs:
            raise Refuse("no_document")
        return docs[0]
    try:
        doc = {"excel": lambda: app.ActiveWorkbook, "word": lambda: app.ActiveDocument,
               "powerpoint": lambda: app.ActivePresentation}[kind]()
    except pywintypes.com_error as exc:
        if _is_busy(exc):
            raise
        doc = None
    if doc is None:
        pv = 0
        try:
            pv = int(app.ProtectedViewWindows.Count)
        except (pywintypes.com_error, AttributeError, TypeError, ValueError):
            pv = 0
        raise Refuse("protected_view" if pv else "no_document")
    if not _in_fence(_full(doc)):
        raise Refuse("outside_fence")
    return doc


def _find_doc(app, kind: str, full: str):
    """เอกสารตามตัวตนที่บันทึกไว้ตอนออก token (FullName) — ไม่ใช่ "ตัวที่ active ตอนนี้" ผู้ใช้สลับหน้าต่างระหว่างรอได้"""
    for d in _docs_of(app, kind):
        if _full(d) == full:
            return d
    raise Refuse("changed", "document_closed")


# ------------------------------------------------------------------ ค่าในเซลล์
def _iso(v) -> str:
    if v.hour == v.minute == v.second == 0:
        return "%04d-%02d-%02d" % (v.year, v.month, v.day)
    return "%04d-%02d-%02d %02d:%02d:%02d" % (v.year, v.month, v.day, v.hour, v.minute, v.second)


def cell_json(v):
    """ค่าจาก COM -> JSON ที่ยังบอกชนิด: ตัวเลข/ข้อความ/ตรรกะ/ว่าง ตรงตัว วันที่ {"d"} error {"e"}"""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        # ตัวเลขในเซลล์มาเป็น float เสมอ (VT_R8) int คือ VT_ERROR ของ Excel
        return {"e": XL_ERRORS.get(v - XL_ERR_BASE, "#ERR%d" % (v - XL_ERR_BASE))}
    if isinstance(v, float):
        return v if v == v else None
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, _dt.datetime):
        return {"d": _iso(v)}
    return str(v)


def _grid(v, rows: int, cols: int) -> list:
    """Value/Formula ของช่วง 1x1 เป็นค่าเดี่ยว ของช่วงอื่นเป็น tuple ซ้อน — ทำให้เป็นลิสต์ 2 มิติเสมอ"""
    if rows == 1 and cols == 1 and not isinstance(v, tuple):
        return [[v]]
    return [list(r) for r in (v or ())]


def _block(ws, r1: int, c1: int, rows: int, cols: int):
    return ws.Range(ws.Cells(r1, c1), ws.Cells(r1 + rows - 1, c1 + cols - 1))


def _addr(rng) -> str:
    return str(rng.Address).replace("$", "")


def _col_letter(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _worksheet(wb, name: str, allow_index: bool = True):
    """ชีตตามชื่อก่อน (ไม่สนตัวพิมพ์เล็กใหญ่ แบบเดียวกับ Excel) แล้วจึงลำดับ 1.. (เฉพาะเมื่อ allow_index) — ไม่พบ = Refuse
    ฝั่งเขียนปิดลำดับ: probe จริงกับ Qwen3-4B เติม sheet="1" มาเองทั้งที่ผู้ใช้ไม่ได้พูดถึงชีต ถ้าตีเป็นชีตแรกจะเขียนผิดชีต
    (ผู้เรียกฝั่งเขียนใช้ _sheet_or_active: เลขที่ไม่ตรงชื่อชีตใด = ใช้ชีตที่ใช้งานอยู่ และ REVIEW บอกไว้)"""
    name = str(name or "").strip()
    sheets = wb.Worksheets
    n = int(sheets.Count)
    for i in range(1, n + 1):
        s = sheets.Item(i)
        if str(s.Name).lower() == name.lower():
            return s
    if allow_index and name.isdigit() and 1 <= int(name) <= n:
        return sheets.Item(int(name))
    raise Refuse("no_sheet", name[:80], sheets=[str(sheets.Item(i).Name) for i in range(1, min(n, 30) + 1)])


# [fix-office b2b] ชื่อชีตค่าเริ่มต้นของ Excel (อังกฤษ/ไทย) — ใช้ตัดสินว่า sheet ที่ไม่มีอยู่จริงเป็นค่าที่โมเดลเติมเอง
_DEFAULT_SHEET_RE = re.compile(r"^(?:sheet|แผ่นงาน|แผ่น)\s*\d{1,3}$", re.I)
# คำที่โมเดลเล็กชอบใส่ใน cell/range แทนการเว้นว่าง — หมายถึง "ตำแหน่งที่เลือกอยู่" (ค่าเริ่มต้น) ไม่ใช่ที่อยู่
_HERE_WORDS = frozenset(("current", "active", "activecell", "active_cell", "cursor", "here", "selected", "default",
                         "ปัจจุบัน", "ตรงนี้", "เซลล์ที่เลือก"))


def _split_ref(ref: str) -> tuple[str, str]:
    """"Sheet2!B2" / "'My Sheet'!B2" / "B2" -> (ชื่อชีต, ที่อยู่)"""
    ref = str(ref or "").strip()
    if "!" in ref:
        sheet, addr = ref.rsplit("!", 1)
        sheet = sheet.strip()
        if len(sheet) >= 2 and sheet[0] == sheet[-1] == "'":
            sheet = sheet[1:-1].replace("''", "'")
        return sheet, addr.strip()
    return "", ref


def _check_a1(addr: str) -> str:
    """รับเฉพาะรูป A1 ธรรมดา — ไม่รับชื่อที่ตั้งไว้ R1C1 หรืออ้างสมุดงานอื่น ([Book2]..., 'C:\\...\\[x.xlsx]S'!A1)"""
    a = str(addr or "").strip()
    if not _A1_RE.match(a):
        raise Refuse("bad_address", a[:60])
    return a


def _sheet_names(wb) -> list:
    out = []
    try:
        for i in range(1, min(int(wb.Worksheets.Count), 40) + 1):
            out.append(str(wb.Worksheets.Item(i).Name))
    except pywintypes.com_error:
        pass
    return out


# ------------------------------------------------------------------ list
def op_list(req: dict) -> dict:
    apps = {}
    for kind in ("excel", "word", "powerpoint"):
        entry = {"state": "not_running", "docs": []}
        try:
            app, state = get_app(kind)
            entry["state"] = state
            if app is not None:
                entry["docs"] = retry(lambda: _list_docs(app, kind))
        except Refuse as r:
            entry["state"], entry["error"] = "error", r.code
        except pywintypes.com_error as exc:
            entry["state"] = "busy" if _is_busy(exc) else "error"
            entry["error"] = _com_text(exc)
        apps[kind] = entry
    return {"ok": True, "apps": apps, "fence": bool(FENCE)}


def _list_docs(app, kind: str) -> list:
    try:
        active = _full(_active_doc(app, kind))
    except (Refuse, pywintypes.com_error):
        active = ""
    docs = []
    for d in _docs_of(app, kind)[:40]:
        info = _doc_info(d)
        info["active"] = bool(active) and info["full"] == active
        try:
            if kind == "excel":
                # PERSONAL.XLSB และสมุดงานที่ซ่อนหน้าต่างไว้ไม่ใช่ "เอกสารที่ผู้ใช้เปิดดู" — ไม่แสดง
                wins = d.Windows
                if int(wins.Count) and not any(bool(wins.Item(i).Visible) for i in range(1, int(wins.Count) + 1)):
                    continue
                info["sheets"] = int(d.Worksheets.Count)
                ash = d.ActiveSheet
                info["sheet"] = str(ash.Name)
                if _typename(ash) == "Worksheet" and int(wins.Count):
                    info["selection"] = _addr(wins.Item(1).RangeSelection)
            elif kind == "powerpoint":
                info["slides"] = int(d.Slides.Count)
                info["slide"] = _current_slide_index(app, d)
        except pywintypes.com_error:
            pass
        docs.append(info)
    return docs


# ------------------------------------------------------------------ read: Excel
def _excel_target(req: dict, wb):
    """(ชีต, ช่วง, โหมด, เซลล์ที่ active) ตามคำขอ: range ที่ระบุ / used / selection / ค่าเริ่มต้น
    ค่าเริ่มต้น = ช่วงที่เลือกถ้าเลือกมากกว่าหนึ่งเซลล์ ไม่งั้นทั้งช่วงที่มีข้อมูลของชีตที่ใช้งานอยู่"""
    want = str(req.get("range") or "").strip()
    sheet_name = str(req.get("sheet") or "").strip()
    ref_sheet, addr = _split_ref(want)
    sheet_name = ref_sheet or sheet_name
    ws = _worksheet(wb, sheet_name) if sheet_name else wb.ActiveSheet
    if _typename(ws) != "Worksheet":
        raise Refuse("not_worksheet", str(ws.Name))
    is_active_sheet = str(ws.Name) == str(wb.ActiveSheet.Name)
    win = wb.Windows.Item(1) if int(wb.Windows.Count) else None
    active_cell = ""
    sel = None
    if win is not None and is_active_sheet:
        try:
            active_cell = _addr(win.ActiveCell)
            sel = win.RangeSelection
        except pywintypes.com_error:
            sel = None
    low = addr.lower()
    if low in _HERE_WORDS:
        addr = low = ""
    app = wb.Application
    if low in ("used", "all", "usedrange", "ทั้งหมด"):
        return ws, ws.UsedRange, "used", active_cell
    if low in ("selection", "sel", "selected", "ที่เลือก"):
        if sel is None:
            raise Refuse("no_selection")
        return ws, sel, "selection", active_cell
    if addr:
        rng = ws.Range(_check_a1(addr))
        if rng.CountLarge > HARD_MAX_CELLS:
            # คอลัมน์/แถวทั้งเส้น (A:C, 1:5) = ตัดให้เหลือส่วนที่มีข้อมูลจริง
            cut = app.Intersect(rng, ws.UsedRange)
            rng = cut if cut is not None else rng
        return ws, rng, "range", active_cell
    if sel is not None and sel.CountLarge > 1:
        if sel.CountLarge > HARD_MAX_CELLS:
            cut = app.Intersect(sel, ws.UsedRange)
            if cut is not None:
                return ws, cut, "selection", active_cell
        return ws, sel, "selection", active_cell
    return ws, ws.UsedRange, "used", active_cell


def read_excel(req: dict, app) -> dict:
    wb = _active_doc(app, "excel")
    ws, rng, mode, active_cell = _excel_target(req, wb)
    notes = []
    areas = int(rng.Areas.Count)
    if areas > 1:
        notes.append("multi_area")
        rng = rng.Areas.Item(1)
    rows_total, cols_total = int(rng.Rows.Count), int(rng.Columns.Count)
    r1, c1 = int(rng.Row), int(rng.Column)
    max_cells = max(1, min(int(req.get("max_cells") or 2000), HARD_MAX_CELLS))
    cols = max(1, min(cols_total, HARD_MAX_COLS))
    rows = max(1, min(rows_total, HARD_MAX_ROWS, max(1, max_cells // cols)))
    block = _block(ws, r1, c1, rows, cols)
    values = [[cell_json(v) for v in row] for row in _grid(block.Value, rows, cols)]
    formulas = []
    try:
        fgrid = _grid(block.Formula, rows, cols)
        for i, row in enumerate(fgrid):
            for j, f in enumerate(row):
                if isinstance(f, str) and f.startswith("=") and len(formulas) < MAX_FORMULAS:
                    formulas.append(["%s%d" % (_col_letter(c1 + j), r1 + i), f[:500]])
    except pywintypes.com_error:
        notes.append("formulas_unavailable")
    empty = all(v is None or v == "" for row in values for v in row)
    return {"ok": True, "app": "excel", "doc": _doc_info(wb), "sheet": str(ws.Name), "sheets": _sheet_names(wb),
            "mode": mode, "address": _addr(rng), "shown": _addr(block), "first_row": r1, "first_col": c1,
            "rows_total": rows_total, "cols_total": cols_total, "rows": rows, "cols": cols,
            "values": values, "formulas": formulas, "active_cell": active_cell, "empty": empty, "notes": notes}


# ------------------------------------------------------------------ read: Word
def _clean_word(text: str) -> str:
    # \x07 = ท้ายเซลล์ตาราง, \x0b = ขึ้นบรรทัดใหม่ในย่อหน้า, \x0c = แบ่งหน้า, \x13-\x15 = เครื่องหมายฟิลด์
    t = str(text or "").replace("\r\x07", "\t").replace("\x07", "\t")
    t = t.replace("\x0b", "\n").replace("\x0c", "\n").replace("\x1e", "-").replace("\x1f", "")
    return re.sub(r"[\x00-\x08\x0e-\x1d]", "", t)


def _para_index(doc, pos: int) -> int:
    """ลำดับย่อหน้า (นับจาก 1) ที่ตำแหน่ง pos อยู่ — Range(0,pos) นับย่อหน้าก่อนหน้าครบเมื่อ pos อยู่ต้นย่อหน้า"""
    if pos <= 0:
        return 1
    n = int(doc.Range(0, pos).Paragraphs.Count)
    start = int(doc.Range(pos, pos).Paragraphs.Item(1).Range.Start)
    return n + 1 if start == pos else n


def _word_sel(doc):
    try:
        return doc.ActiveWindow.Selection
    except pywintypes.com_error:
        return None


def read_word(req: dict, app) -> dict:
    doc = _active_doc(app, "word")
    want = str(req.get("range") or "").strip().lower()
    max_chars = max(200, min(int(req.get("max_chars") or 12000), HARD_MAX_CHARS))
    sel = _word_sel(doc)
    s = e = 0
    story = 1
    if sel is not None:
        s, e = int(sel.Start), int(sel.End)
        try:
            story = int(sel.StoryType)
        except pywintypes.com_error:
            story = 1
    total = int(doc.Paragraphs.Count)
    content_end = int(doc.Content.End)
    out = {"ok": True, "app": "word", "doc": _doc_info(doc), "total_paragraphs": total, "chars": content_end,
           "sel_start": s, "sel_end": e, "story_main": story == 1, "paragraphs": [], "truncated": False, "notes": []}
    if story != 1:
        # เคอร์เซอร์อยู่ในหัว/ท้ายกระดาษ เชิงอรรถ หรือข้อคิดเห็น — ตำแหน่งไม่ใช่ของเนื้อเรื่องหลัก ใช้ต้นเอกสารแทน
        out["notes"].append("cursor_outside_body")
        s = e = 0
    m = re.fullmatch(r"(\d{1,6})\s*(?:-\s*(\d{1,6}))?", want)
    if want in ("all", "ทั้งหมด", "document", "doc"):
        out["mode"] = "all"
        text = _clean_word(doc.Content.Text)
        paras = text.split("\r")
        used = 0
        for i, p in enumerate(paras, 1):
            if used + len(p) > max_chars:
                out["truncated"] = True
                break
            out["paragraphs"].append({"i": i, "text": p})
            used += len(p) + 1
        return out
    if m:
        a = max(1, int(m.group(1)))
        b = min(total, int(m.group(2) or a), a + 199)
        out["mode"] = "paragraphs"
        if a > total:
            raise Refuse("no_paragraph", str(a), total=total)
        rng = doc.Range(int(doc.Paragraphs.Item(a).Range.Start), int(doc.Paragraphs.Item(b).Range.End))
        _collect_paras(rng, a, out, max_chars, s)
        return out
    if e > s and want not in ("around", "cursor", "รอบเคอร์เซอร์"):
        out["mode"] = "selection"
        text = _clean_word(doc.Range(s, e).Text)
        out["selection"] = text[:max_chars]
        out["truncated"] = len(text) > max_chars
        out["sel_first_para"] = _para_index(doc, s)
        return out
    # ไม่มีข้อความที่เลือก = ย่อหน้าที่เคอร์เซอร์อยู่ + ข้างเคียงฝั่งละ 3 ย่อหน้า (บริบทพอให้เขียนต่อ/แก้ได้)
    out["mode"] = "around"
    idx = _para_index(doc, s)
    a, b = max(1, idx - 3), min(total, idx + 3)
    rng = doc.Range(int(doc.Paragraphs.Item(a).Range.Start), int(doc.Paragraphs.Item(b).Range.End))
    _collect_paras(rng, a, out, max_chars, s)
    out["cursor_para"] = idx
    return out


def _collect_paras(rng, first_index: int, out: dict, max_chars: int, caret: int) -> None:
    used = 0
    paras = rng.Paragraphs
    for k in range(1, int(paras.Count) + 1):
        pr = paras.Item(k).Range
        ps, pe = int(pr.Start), int(pr.End)
        raw = str(pr.Text or "")
        item = {"i": first_index + k - 1, "text": _clean_word(raw).rstrip("\r")}
        if ps <= caret < pe or (caret == pe and k == int(paras.Count)):
            item["caret"] = len(_clean_word(raw[:max(0, caret - ps)]))
        if used + len(item["text"]) > max_chars:
            out["truncated"] = True
            break
        out["paragraphs"].append(item)
        used += len(item["text"]) + 1


# ------------------------------------------------------------------ read: PowerPoint
def _current_slide_index(app, pres) -> int:
    full = _full(pres)
    try:
        for i in range(1, int(app.SlideShowWindows.Count) + 1):
            w = app.SlideShowWindows.Item(i)
            if _full(w.Presentation) == full:
                return int(w.View.Slide.SlideIndex)
    except pywintypes.com_error:
        pass
    try:
        if int(pres.Windows.Count):
            win = pres.Windows.Item(1)
            try:
                return int(win.View.Slide.SlideIndex)
            except pywintypes.com_error:
                return int(win.Selection.SlideRange.Item(1).SlideIndex)
    except pywintypes.com_error:
        pass
    return 1 if int(pres.Slides.Count) else 0


def _shape_items(sh, out: list, depth: int = 0) -> None:
    if depth > 4 or len(out) > 200:
        return
    try:
        stype = int(sh.Type)
    except pywintypes.com_error:
        stype = 0
    name = ""
    try:
        name = str(sh.Name or "")
    except pywintypes.com_error:
        pass
    if stype == 6:                                    # msoGroup
        try:
            g = sh.GroupItems
            for i in range(1, int(g.Count) + 1):
                _shape_items(g.Item(i), out, depth + 1)
        except pywintypes.com_error:
            pass
        return
    try:
        if int(sh.HasTable):
            t = sh.Table
            rows = []
            for r in range(1, min(int(t.Rows.Count), 60) + 1):
                row = []
                for c in range(1, min(int(t.Columns.Count), 20) + 1):
                    try:
                        row.append(_clean_word(t.Cell(r, c).Shape.TextFrame.TextRange.Text))
                    except pywintypes.com_error:
                        row.append("")
                rows.append(row)
            out.append({"kind": "table", "name": name, "rows": rows})
            return
    except pywintypes.com_error:
        pass
    try:
        if int(sh.HasTextFrame) and int(sh.TextFrame.HasText):
            out.append({"kind": "text", "name": name, "text": _clean_word(sh.TextFrame.TextRange.Text)})
            return
    except pywintypes.com_error:
        pass
    try:
        if int(sh.HasChart):
            out.append({"kind": "chart", "name": name})
            return
    except pywintypes.com_error:
        pass
    if stype in (13, 11):                             # msoPicture, msoLinkedPicture
        alt = ""
        try:
            alt = str(sh.AlternativeText or "")
        except pywintypes.com_error:
            pass
        out.append({"kind": "picture", "name": name, "text": alt[:300]})


def _slide_dict(slide) -> dict:
    items = []
    title_name = ""
    try:
        if int(slide.Shapes.HasTitle):
            t = slide.Shapes.Title
            title_name = str(t.Name)
            if int(t.TextFrame.HasText):
                items.append({"kind": "title", "name": title_name, "text": _clean_word(t.TextFrame.TextRange.Text)})
    except pywintypes.com_error:
        pass
    for i in range(1, int(slide.Shapes.Count) + 1):
        sh = slide.Shapes.Item(i)
        try:
            if title_name and str(sh.Name) == title_name:
                continue
        except pywintypes.com_error:
            pass
        _shape_items(sh, items)
    notes = ""
    try:
        if int(slide.HasNotesPage):
            ph = slide.NotesPage.Shapes.Placeholders
            for i in range(1, int(ph.Count) + 1):
                p = ph.Item(i)
                if int(p.PlaceholderFormat.Type) == 2 and int(p.TextFrame.HasText):   # ppPlaceholderBody
                    notes = _clean_word(p.TextFrame.TextRange.Text)
    except pywintypes.com_error:
        pass
    return {"n": int(slide.SlideIndex), "items": items, "notes": notes}


def read_powerpoint(req: dict, app) -> dict:
    pres = _active_doc(app, "powerpoint")
    total = int(pres.Slides.Count)
    want = str(req.get("range") or "").strip().lower()
    cur = _current_slide_index(app, pres)
    out = {"ok": True, "app": "powerpoint", "doc": _doc_info(pres), "slides_total": total, "current": cur,
           "slides": [], "truncated": False}
    if not total:
        out["mode"] = "empty"
        return out
    if want in ("all", "ทั้งหมด"):
        out["mode"] = "all"
        idx = list(range(1, min(total, 60) + 1))
        out["truncated"] = total > 60
    elif re.fullmatch(r"\d{1,4}\s*(-\s*\d{1,4})?", want):
        a, _, b = want.partition("-")
        a, b = int(a), int(b or a)
        if a < 1 or a > total:
            raise Refuse("no_slide", str(a), total=total)
        out["mode"] = "slides"
        idx = list(range(a, min(total, b, a + 29) + 1))
    else:
        out["mode"] = "current"
        idx = [max(1, cur)]
    for n in idx:
        out["slides"].append(_slide_dict(pres.Slides.Item(n)))
    return out


def op_read(req: dict) -> dict:
    kind = str(req.get("app") or "")
    if kind not in PROGIDS:
        raise Refuse("bad_app", kind)
    app, state = get_app(kind)
    if app is None:
        raise Refuse(state)
    fn = {"excel": read_excel, "word": read_word, "powerpoint": read_powerpoint}[kind]
    return retry(lambda: fn(req, app))


# ------------------------------------------------------------------ write: Excel
def _excel_fingerprint(wb, ws, rng) -> tuple[str, list]:
    """ลายนิ้วมือของเป้าหมาย = ไฟล์ + ชีต + ที่อยู่ + Formula ของทุกเซลล์ในช่วง (ค่าคงที่ก็อยู่ใน Formula)
    ใช้ Formula ไม่ใช้ Value: ค่าของสูตรอย่าง =NOW() เปลี่ยนทุกครั้งที่คำนวณใหม่ จะทำให้ "เปลี่ยน" ทั้งที่ไม่มีใครแตะ"""
    rows, cols = int(rng.Rows.Count), int(rng.Columns.Count)
    formulas = [[("" if f is None else str(f)) for f in row] for row in _grid(rng.Formula, rows, cols)]
    blob = json.dumps([_full(wb), str(ws.Name), _addr(rng), formulas], ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest(), formulas


def _excel_block_checks(ws, rng) -> None:
    """เขียนทับสิ่งที่ Excel จะปฏิเสธครึ่งๆ กลางๆ ไม่ได้ — ตรวจก่อนออก token และก่อนเขียนจริงอีกครั้ง"""
    try:
        if bool(ws.ProtectContents) and rng.Locked is not False:
            raise Refuse("sheet_protected", str(ws.Name))
    except pywintypes.com_error:
        pass
    if rng.MergeCells is not False:
        raise Refuse("merged_cells", _addr(rng))
    if rng.HasArray is not False:
        raise Refuse("array_formula", _addr(rng))


def _excel_start(req: dict, wb):
    """(ชีต, แถว, คอลัมน์, ที่มา) ของเซลล์เริ่มต้น: cell ที่ระบุ ("B2", "Sheet2!B2", "B2:D5" = มุมซ้ายบน) หรือเซลล์ที่
    เลือกอยู่ของชีตที่ใช้งานอยู่ — ชีตอื่นที่ไม่ได้ระบุเซลล์เริ่มที่ A1 (ดูเซลล์ที่เลือกของชีตที่ไม่ได้เปิดอยู่ไม่ได้)"""
    ref_sheet, addr = _split_ref(req.get("cell") or "")
    if addr.strip().lower() in _HERE_WORDS or addr.strip().lower() in ("selection", "sel"):
        addr = ""
    sheet_name = ref_sheet or str(req.get("sheet") or "").strip()
    ws = None
    if sheet_name:
        try:
            ws = _worksheet(wb, sheet_name, allow_index=False)
        except Refuse:
            # [fix-office b2b] probe กับ Qwen3-4B (2026-10-06): "ใส่ตาราง … ลง Excel ที่ B2" ได้ sheet="Sheet1" 2/5 ครั้ง ทั้งที่ผู้ใช้
            # ไม่ได้พูดถึงชีต — ชื่อชีตค่าเริ่มต้นที่ไม่มีอยู่จริงถือเป็นค่าที่โมเดลเติมเอง เหมือนเลขลำดับ (REVIEW บอกชีตจริงไว้)
            if not (sheet_name.isdigit() or (not ref_sheet and _DEFAULT_SHEET_RE.match(sheet_name))):
                raise
            req["_sheet_ignored"] = sheet_name          # เลขที่ไม่ใช่ชื่อชีต = ค่าที่โมเดลเติมเอง ใช้ชีตที่ใช้งานอยู่
    ws = ws if ws is not None else wb.ActiveSheet
    if _typename(ws) != "Worksheet":
        raise Refuse("not_worksheet", str(ws.Name))
    if addr:
        top = ws.Range(_check_a1(addr)).Cells(1, 1)
        return ws, int(top.Row), int(top.Column), "cell"
    if str(ws.Name) == str(wb.ActiveSheet.Name) and int(wb.Windows.Count):
        ac = wb.Windows.Item(1).ActiveCell
        return ws, int(ac.Row), int(ac.Column), "active_cell"
    return ws, 1, 1, "sheet_a1"


def op_excel_plan(req: dict) -> dict:
    app, state = get_app("excel")
    if app is None:
        raise Refuse(state)

    def run():
        wb = _active_doc(app, "excel")
        ws, r1, c1, origin = _excel_start(req, wb)
        rows, cols = int(req.get("rows") or 0), int(req.get("cols") or 0)
        if rows < 1 or cols < 1:
            raise Refuse("no_data")
        if r1 + rows - 1 > int(ws.Rows.Count) or c1 + cols - 1 > int(ws.Columns.Count):
            raise Refuse("off_sheet", "%s%d" % (_col_letter(c1), r1))
        rng = _block(ws, r1, c1, rows, cols)
        _excel_block_checks(ws, rng)
        fp, formulas = _excel_fingerprint(wb, ws, rng)
        fmt = None
        try:
            fmt = rng.NumberFormat
        except pywintypes.com_error:
            pass
        # [fix-office b2b] ค่าเดิมแบบมีชนิด: Formula เป็นข้อความเสมอ ("92" ทั้งตัวเลข 92 และข้อความ '92) REVIEW จึงเคยบอกผู้ใช้ว่า
        # เซลล์ตัวเลขเป็นข้อความ — ส่ง Value ไปด้วยให้ tools_office แสดงรูปเดียวกับค่าใหม่ (ตัวเลขไม่มีคำพูด วันที่ วันที่(…))
        try:
            old_values = [[cell_json(v) for v in row] for row in _grid(rng.Value, rows, cols)]
        except pywintypes.com_error:
            old_values = None
        return {"ok": True, "doc": _doc_info(wb), "sheet": str(ws.Name), "address": _addr(rng),
                "first_row": r1, "first_col": c1, "rows": rows, "cols": cols, "origin": origin,
                "old": formulas, "old_values": old_values,
                "general": isinstance(fmt, str) and fmt.lower() == "general",
                "fingerprint": fp, "is_active": True, "sheet_ignored": req.get("_sheet_ignored", ""),
                # [fix-office b2b] รายชื่อชีตทั้งหมด = สูตรที่จะเขียนอ้างได้เฉพาะชีตเหล่านี้; has_vba = เตือนใน REVIEW
                "sheets": _all_sheet_names(wb), "has_vba": _has_vba(wb)}
    return retry(run)


def _all_sheet_names(wb) -> list:
    """ชื่อเวิร์กชีตทั้งหมด (ไม่เกิน 255) — เกินเพดาน = สูตรที่อ้างชีตท้ายๆ ถูกเขียนเป็นข้อความ (ปลอดภัยไว้ก่อน)"""
    sheets = wb.Worksheets
    return [str(sheets.Item(i).Name) for i in range(1, min(int(sheets.Count), 255) + 1)]


def _serial(iso: str) -> float:
    """วันที่ ISO -> เลขวันที่ของ Excel (ระบบ 1900) คำนวณเองจากปฏิทิน — ไม่ส่ง datetime ผ่าน COM ที่มีเรื่องเขตเวลา"""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?", iso)
    if not m:
        raise Refuse("bad_date", iso[:40])
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    days = (_dt.date(y, mo, d) - _dt.date(1899, 12, 30)).days
    secs = int(m.group(4) or 0) * 3600 + int(m.group(5) or 0) * 60 + int(m.group(6) or 0)
    return float(days) + secs / 86400.0


def _com_cell(c: dict):
    """ค่าหนึ่งเซลล์ที่ tools_office เตรียมมา (ชนิดตัดสินแล้วฝั่ง MCP และแสดงใน REVIEW ตรงตามนี้) -> ค่าที่ส่งให้ COM"""
    k, v = c.get("k"), c.get("v")
    if k == "x":
        return None                                   # ล้างเซลล์
    if k == "n":
        return float(v)
    if k == "b":
        return bool(v)
    if k == "d":
        return _serial(str(v))
    if k == "f":
        s = str(v)
        if not s.startswith("="):
            raise Refuse("bad_cell")
        return s
    if k == "s":
        # อะพอสทรอฟีนำหน้า = บอก Excel ว่าเป็นข้อความตรงตัว (ไม่แปลงเป็นตัวเลข/วันที่/สูตร และไม่ถูกเก็บในค่า)
        s = str(v)
        return ("'" + s) if c.get("q") else s
    raise Refuse("bad_cell")


def op_excel_write(req: dict) -> dict:
    app, state = get_app("excel")
    if app is None:
        raise Refuse("changed", "excel_" + state)
    cells = req.get("cells") or []
    rows, cols = len(cells), (len(cells[0]) if cells else 0)
    if not rows or not cols or any(len(r) != cols for r in cells):
        raise Refuse("no_data")
    values = tuple(tuple(_com_cell(c) for c in row) for row in cells)

    def check():
        wb = _find_doc(app, "excel", str(req.get("full") or ""))
        try:
            ws = _worksheet(wb, str(req.get("sheet") or ""))
        except Refuse:
            raise Refuse("changed", "sheet_missing")
        addr = _check_a1(str(req.get("address") or ""))
        rng = ws.Range(addr)
        if int(rng.Rows.Count) != rows or int(rng.Columns.Count) != cols:
            raise Refuse("changed", "shape")
        fp, _ = _excel_fingerprint(wb, ws, rng)
        if fp != req.get("expect"):
            raise Refuse("changed", "cells")
        _excel_block_checks(ws, rng)
        return wb, ws, rng

    wb, ws, rng = retry(check)
    # [fix-office b2b] สูตรต้องอ้างได้แค่ชีตที่มีอยู่จริงในสมุดงานนี้ ณ ตอนนี้ (ดู formula_ref_problem) — ไม่ผ่าน = ไม่เขียนอะไรเลย
    names = retry(lambda: _all_sheet_names(wb))
    for row in cells:
        for c in row:
            if c.get("k") == "f":
                why = formula_ref_problem(c.get("v"), names)
                if why:
                    raise Refuse("unsafe_formula", why)

    def put():
        rng.Value = values
    # [fix-office b2b] ปิดมาโครเหตุการณ์ (Worksheet_Change ฯลฯ) เฉพาะช่วงคำสั่งเขียนคำสั่งเดียว แล้วคืนค่าเดิมทันที
    # ทำไม: ในสมุดงาน .xlsm ที่ผู้ใช้เปิดมาโครไว้ ค่าที่โมเดลเลือกจะไปกระตุ้นโค้ด VBA ของสมุดงานโดยที่คนกดอนุญาตไม่รู้
    # (REVIEW เตือนเรื่องมาโครด้วย) — คืนค่าใน finally เพราะค่านี้เป็นของทั้งโปรแกรม Excel ไม่ใช่ของสมุดงาน
    # ปิดไม่ได้ (Excel ไม่ว่าง) = ยกเลิกทั้งคำขอก่อนเขียน ไม่เขียนแบบที่มาโครยังทำงานอยู่
    events_was = retry(lambda: bool(app.EnableEvents))
    if events_was:
        retry(lambda: setattr(app, "EnableEvents", False))
    try:
        retry(put)                                       # คำสั่งเดียว — ถ้าถูกปฏิเสธคือยังไม่ได้เขียนอะไรเลย ลองซ้ำได้
    finally:
        if events_was:
            _restore_events(app)
    fmt_done, fmt_skipped = 0, 0
    fmts = req.get("formats") or []
    for (i, j, f) in fmts[:400]:
        try:
            ws.Cells(int(rng.Row) + int(i), int(rng.Column) + int(j)).NumberFormat = str(f)
            fmt_done += 1
        except pywintypes.com_error:
            fmt_skipped += 1
    fmt_skipped += max(0, len(fmts) - 400)
    return {"ok": True, "doc": _doc_info(wb), "sheet": str(ws.Name), "address": _addr(rng),
            "cells": rows * cols, "formats": fmt_done, "formats_skipped": fmt_skipped,
            "events_suspended": bool(events_was)}


def _restore_events(app) -> None:
    """เปิดมาโครเหตุการณ์คืน — Excel ไม่ว่างชั่วคราวก็ลองซ้ำ (ค่านี้ค้างเป็น False ไม่ได้: มาโครของผู้ใช้จะหยุดทำงานเงียบๆ)"""
    end = time.monotonic() + BUSY_BUDGET
    while True:
        try:
            app.EnableEvents = True
            return
        except pywintypes.com_error:
            if time.monotonic() > end:
                raise
            time.sleep(0.2)


# ------------------------------------------------------------------ write: Word
def _word_fingerprint(doc) -> tuple[str, int]:
    text = str(doc.Content.Text or "")
    if len(text) > WORD_HASH_MAX:
        text = "%d|%s|%s" % (len(text), text[:200000], text[-200000:])
    blob = json.dumps([_full(doc), int(doc.Content.End), hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest(), int(doc.Content.End)


def op_word_plan(req: dict) -> dict:
    app, state = get_app("word")
    if app is None:
        raise Refuse(state)

    def run():
        doc = _active_doc(app, "word")
        try:
            if int(doc.ProtectionType) != -1:                 # wdNoProtection
                raise Refuse("doc_protected")
        except pywintypes.com_error:
            pass
        sel = _word_sel(doc)
        if sel is None:
            raise Refuse("no_selection")
        if int(sel.StoryType) != 1:                           # wdMainTextStory
            raise Refuse("cursor_outside_body")
        s, e = int(sel.Start), int(sel.End)
        para = doc.Range(s, s).Paragraphs.Item(1).Range
        ps, pe = int(para.Start), int(para.End)
        ptext = str(para.Text or "")
        in_table = False
        try:
            in_table = bool(sel.Information(12))              # wdWithInTable
        except pywintypes.com_error:
            pass
        fp, length = _word_fingerprint(doc)
        sel_text = _clean_word(doc.Range(s, e).Text) if e > s else ""
        return {"ok": True, "doc": _doc_info(doc), "start": s, "end": e, "sel_text": sel_text[:4000],
                "sel_len": len(sel_text), "para_index": _para_index(doc, s), "para_start": ps, "para_end": pe,
                "para_text": _clean_word(ptext).rstrip("\r")[:1500], "caret_in_para": s - ps,
                "end_in_para": min(e, pe) - ps, "in_table": in_table, "fingerprint": fp, "length": length,
                "has_vba": _has_vba(doc)}               # [fix-office b2b] เอกสาร .docm ที่มีมาโคร = เตือนใน REVIEW
    return retry(run)


def op_word_write(req: dict) -> dict:
    app, state = get_app("word")
    if app is None:
        raise Refuse("changed", "word_" + state)
    kind = req.get("kind")
    s, e = int(req.get("start") or 0), int(req.get("end") or 0)
    replace = bool(req.get("replace"))

    def check():
        doc = _find_doc(app, "word", str(req.get("full") or ""))
        fp, length = _word_fingerprint(doc)
        if fp != req.get("expect"):
            raise Refuse("changed", "document")
        if not (0 <= s <= e <= length):
            raise Refuse("changed", "position")
        return doc
    doc = retry(check)
    undo = None
    try:
        undo = app.UndoRecord
        undo.StartCustomRecord("Qwen: insert")          # Ctrl+Z ครั้งเดียวย้อนการแทรกทั้งก้อน
    except (pywintypes.com_error, AttributeError):
        undo = None
    try:
        if replace and e > s:
            rng = doc.Range(s, e)
            rng.Text = ""                                 # ลบข้อความที่เลือก (REVIEW แสดงข้อความนี้ให้คนเห็นแล้ว)
            pos = s
        else:
            pos = e                                       # ต่อท้ายข้อความที่เลือก — ไม่ลบอะไรของผู้ใช้
        if kind == "table":
            end = _word_insert_table(doc, pos, req.get("rows") or [], bool(req.get("header")))
        else:
            text = str(req.get("text") or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r")
            r = doc.Range(pos, pos)
            r.InsertAfter(text)
            end = int(r.End)
        try:
            sel = _word_sel(doc)
            if sel is not None:
                sel.SetRange(end, end)                    # เคอร์เซอร์ไปท้ายสิ่งที่แทรก เหมือนพิมพ์เอง
        except pywintypes.com_error:
            pass
    finally:
        if undo is not None:
            try:
                undo.EndCustomRecord()
            except pywintypes.com_error:
                pass
    return {"ok": True, "doc": _doc_info(doc), "start": pos, "end": end, "para_index": _para_index(doc, pos)}


def _word_insert_table(doc, pos: int, rows: list, header: bool) -> int:
    """แทรกตารางที่ pos: ข้อความคั่นแท็บ -> ConvertToTable (คำสั่งเดียว เร็วกว่าเติมทีละเซลล์หลายสิบเท่า)
    ตารางต้องเป็นย่อหน้าของตัวเอง: กลางย่อหน้าขึ้นย่อหน้าใหม่ก่อน, ท้ายย่อหน้าใช้เครื่องหมายย่อหน้าเดิมปิดแถวสุดท้าย
    (ไม่งั้นเหลือย่อหน้าว่างหลังตาราง — เจอจริงในการทดลอง)"""
    ncols = max(len(r) for r in rows)

    def cell(v):
        return str(v if v is not None else "").replace("\t", " ").replace("\r\n", "\n").replace("\r", "\n") \
            .replace("\n", "\x0b")
    lines = ["\t".join(cell(r[j]) if j < len(r) else "" for j in range(ncols)) for r in rows]
    para = doc.Range(pos, pos).Paragraphs.Item(1).Range
    at_start = pos == int(para.Start)
    at_end = str(doc.Range(pos, pos + 1).Text or "") == "\r"
    lead = "" if at_start else "\r"
    body = "\r".join(lines)
    r = doc.Range(pos, pos)
    if at_end and not at_start:
        r.InsertAfter(lead + body)
        t0 = pos + len(lead)
        span = doc.Range(t0, t0 + len(body) + 1)          # รวมเครื่องหมายย่อหน้าเดิมเป็นท้ายแถวสุดท้าย
    else:
        r.InsertAfter(lead + body + "\r")
        t0 = pos + len(lead)
        span = doc.Range(t0, t0 + len(body) + 1)
    tbl = span.ConvertToTable(1, len(rows), ncols)       # 1 = wdSeparateByTabs
    try:
        tbl.Borders.Enable = True
        if header:
            tbl.Rows.Item(1).Range.Font.Bold = True
    except pywintypes.com_error:
        pass
    return int(tbl.Range.End)


# ------------------------------------------------------------------ main
OPS = {"list": op_list, "read": op_read, "excel_plan": op_excel_plan, "excel_write": op_excel_write,
       "word_plan": op_word_plan, "word_write": op_word_write}


def _reply(obj: dict) -> None:
    data = json.dumps(obj, ensure_ascii=True, default=str).encode("ascii")
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def main() -> int:
    global pythoncom, pywintypes, client, dynamic
    try:
        req = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except ValueError:
        _reply({"ok": False, "code": "bad_request"})
        return 0
    if not isinstance(req, dict) or req.get("op") not in OPS:
        _reply({"ok": False, "code": "bad_request"})
        return 0
    try:
        import pythoncom as _pc
        import pywintypes as _pt
        import win32com.client as _cl
        import win32com.client.dynamic as _dy
    except Exception as exc:       # noqa: BLE001 — ไม่มี pywin32 = บอกกลับไปให้ชัด ไม่ล้มเงียบ
        _reply({"ok": False, "code": "no_pywin32", "error": "%s: %s" % (type(exc).__name__, exc)})
        return 0
    pythoncom, pywintypes, client, dynamic = _pc, _pt, _cl, _dy
    pythoncom.CoInitialize()
    try:
        out = OPS[req["op"]](req)
    except Refuse as r:
        out = dict({"ok": False, "code": r.code, "error": r.msg}, **r.extra)
    except pywintypes.com_error as exc:
        out = {"ok": False, "code": "busy" if _is_busy(exc) else "com_error", "error": _com_text(exc)}
    except Exception as exc:       # noqa: BLE001 — ตอบเป็น JSON เสมอ ฝั่ง MCP แปลเป็นข้อความให้โมเดล
        out = {"ok": False, "code": "error", "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])}
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:          # noqa: BLE001
            pass
    _reply(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
