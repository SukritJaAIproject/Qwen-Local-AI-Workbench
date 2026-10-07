# -*- coding: utf-8 -*-
"""ชั้นความปลอดภัยของ Local Computer MCP

บังคับกฎจากคู่มือ Qwen Addon Replication Guide
  S05  บล็อก sensitive path (credential folders, app databases, คีย์, token)
  S03  การกระทำที่เปลี่ยนเครื่องต้องผ่านสองขั้น preview -> confirm
  S04  ข้อมูลแต่ละ Project แยกกัน ห้ามข้าม

ทำไมต้องมีชั้นนี้
-----------------
เครื่องมือในตัวของ llama-server (`--tools all`) **ไม่มีการจำกัด path เลย**
ทดสอบแล้วอ่าน %USERPROFILE%\\.ssh และไฟล์ credential ของ Claude ได้จริง
และ exec_shell_command รันทันทีโดยไม่ถาม โมดูลนี้จึงมีไว้แทนที่เครื่องมือชุดนั้น
ให้ยังเข้าถึงทั้งเครื่องได้เหมือนเดิม แต่กันเฉพาะจุดที่เป็นความลับ

รอบแก้ความปลอดภัย 2026-09-30 (ช่องโหว่ V2/V3/V6 จากการ audit)
------------------------------------------------------------------
* config.json เคย "แทนที่" ค่าเริ่มต้นทั้งก้อน และเครื่องมือ write_file สร้างไฟล์นั้นได้เอง
  เรียกครั้งเดียวก็ปิด S05 ทั้งระบบ ตอนนี้ค่าจากไฟล์ถูก "รวม" เข้ากับค่าเริ่มต้นเท่านั้น
  (เพิ่มได้ ลบรายการที่ฝังไว้ไม่ได้) และตัวไฟล์อยู่ในเขตห้ามเขียน
* WRITE_PROTECTED: โค้ด/ค่าตั้งของสแตก, โฟลเดอร์ secrets, Startup, PowerShell profile,
  .git, rc ของ shell ฯลฯ ห้ามเขียนผ่านเครื่องมือแม้มี confirm_token — ทางเดียวที่แก้ได้คือผู้ใช้แก้เอง
* ขอบเขตโปรเจกต์ (S04) ผูกกับเธรดของคำขอ: server.py ตั้ง project_scope(slug) จาก URL
  แล้ว path ใต้ข้อมูล/โปรไฟล์เบราว์เซอร์ของโปรเจกต์อื่นจะถูกปฏิเสธทั้งอ่านและเขียน
* confirm_token ผูกกับ action + รายละเอียดของการกระทำ (hash) + โปรเจกต์ ใช้ได้ครั้งเดียว
  และ audit.log ไม่เก็บค่า token อีกแล้ว (เก็บแค่รหัสอ้างอิงที่ย้อนกลับเป็น token ไม่ได้)

รอบ FIXER (audit รอบสอง)
------------------------
* ขั้นยืนยันต้องผ่านเครื่องมือ local_confirm เท่านั้น (ดู "ช่องทางยืนยัน" ข้างล่าง)
* บันทึกรวมของสแตกอ่านไม่ได้ (STACK_READ_BLOCKED) โดยไม่ลามไปบล็อก .log ในโปรเจกต์ของผู้ใช้
* wildcard ขยายด้วย FindFirstFileW ของ OS (กติกาเดียวกับ cmd: ชื่อ 8.3, ? ของ DOS, [ ] ตรงตัว)
* path แบบ device namespace (\\\\.\\ และ \\\\?\\) ที่ไม่ใช่ไดรฟ์ถูกปฏิเสธ
* <rev>:<path> ของ git แยกได้ครบทุกรูป (:0:x, -L..:x)

รอบ review (R1-R3, security review อิสระ 2026-09-30)
----------------------------------------------------
* ทุก token เก็บ "ข้อความตรวจทาน" (review) ที่เซิร์ฟเวอร์สร้างเอง: โค้ดเต็ม/คำสั่งเต็ม+cwd/เนื้อไฟล์หรือ diff
  อักขระซ่อนแสดงเป็น «U+XXXX» บรรทัดยาวตัดพร้อม ↩ — local_confirm ต้องส่งข้อความนี้กลับมาตรงตัว
  (confirming(token, review)) กล่องอนุญาตของ WebUI จึงแสดงของจริงตอนคนกด (ดู "ข้อความตรวจทาน")
* token ค้างได้ไม่เกิน 5 ตัวต่อโปรเจกต์ และ python มี token รอได้ทีละอัน (supersede)

รอบ FIXER ของรอบ review (e2e จริง + security review รอบสอง)
------------------------------------------------------------
* อักขระซ่อน = Default_Ignorable_Code_Point ทั้งชุดของ Unicode (เดิมเลือกเองแล้วหลุด U+180B-180F)
  + อักษรหน้าตาเหมือนละติน/ASCII (homoglyph) แสดงเป็น «U+XXXX» พร้อมบรรทัดคำเตือนของตัวเอง
* review_matches ยอมช่องว่างหน้าบรรทัดแรก (โมเดล 4B เขียน " [python]" เสมอ) แต่ช่องว่าง/บรรทัดว่างที่ตัดทิ้ง
  มีเพดาน (กันการเติมช่องว่างดันโค้ดออกจากกล่องอนุญาต) ตอบไม่ตรง = บอกจุดแรกที่ผิด + ต่ออายุ token (เพดาน 15 นาที)
* token อายุ 10 นาที (ขั้นตอน แสดง REVIEW -> ถาม -> คัดลอกกลับ บนเครื่องนี้ใช้เวลาหลายนาที)

รอบ review-fetch (S1/S2, 2026-09-30 ดึก — e2e จริงกับ Qwen3-4B)
------------------------------------------------------------------
* โมเดล 4B ไม่แสดง review ในแชต คัดลอกกลับมาแค่บางส่วน (ไม่ตรง = ไม่รัน) แล้วหันไปถามผู้ใช้ซ้ำแทนการลองใหม่
  การให้โมเดลเล็ก "ท่องข้อความยาวกลับมาตรงตัว" จึงเป็นด่านที่พังเองมากกว่าจะกันอะไร
* ตอนนี้กล่องอนุญาตดึง review "จากเซิร์ฟเวอร์" เอง (server.py GET /review/<slug> -> pending_view) คนจึงเห็น
  ของจริงโดยไม่พึ่งโมเดล review ใน local_confirm จึงไม่บังคับ (review_provided) — ถ้าส่งมายังต้องตรงเหมือนเดิม
* ที่ไม่เปลี่ยน: token ผูก action + digest ของอาร์กิวเมนต์ + โปรเจกต์ + ผิว ใช้ได้ครั้งเดียว อายุ/เพดาน/จำนวนค้างเท่าเดิม

รอบ FIXER ของ S1/S2 (review อิสระ + e2e จริง 2026-10-01)
------------------------------------------------------------
* token อย่างเดียวรันได้เฉพาะเมื่อกล่องอนุญาต "ดึง review ไปแสดงสำเร็จแล้ว" (pending_view(mark_viewed=True) จด viewed)
  เดิมเซิร์ฟเวอร์รันทันทีแม้การ์ดโหลดไม่สำเร็จ/ยังโหลดอยู่ หรือแท็บเก่าที่ไม่ดึง review เลย — ด่านคนอยู่แค่ในเบราว์เซอร์
  ไม่เคยเห็น = ปฏิเสธโดยไม่ใช้ token (note_unviewed นับครั้งเพื่อเลือกข้อความ) review ที่ส่งมาและตรงยังผ่านได้เหมือนเดิม
* review ที่ส่งมาครอบด้วยรั้ว ```review ของเซิร์ฟเวอร์เองหนึ่งชั้น = ถอดรั้วก่อนเทียบ (_review_norm unfence) เนื้อในต้องตรงเป๊ะ

แก้ค่าได้ที่ config.json ข้างไฟล์นี้ (ผู้ใช้แก้เองเท่านั้น) ถ้าไฟล์หายจะใช้ค่าปลอดภัยที่ฝังไว้
"""
from __future__ import annotations

import copy
import ctypes
import fnmatch
import glob as _glob
import hashlib
import json
import os
import re
import secrets
import sys
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.json"
# สองค่านี้ตั้งผ่าน env ได้ เพื่อให้อินสแตนซ์ทดสอบ (พอร์ต 8892) ไม่ไปปน audit.log และข้อมูลโปรเจกต์จริง
AUDIT_PATH = Path(os.environ.get("QWEN_MCP_AUDIT_PATH") or (HERE / "audit.log"))
PROJECT_DATA = Path(os.environ.get("QWEN_MCP_PROJECT_DATA") or r"C:\LLM\projects\data")
BROWSER_PROFILES = Path(r"C:\LLM\browser-profile")
PROJECTS_JSON = Path(r"C:\LLM\projects\projects.json")

# รอบ FIXER (e2e ของรอบ review): เดิม 5 นาที แต่ขั้นตอนใหม่ทั้งรอบบนเครื่องนี้ (โมเดล ~5 โทเคน/วินาที) คือ
# โมเดลแสดง REVIEW ในแชต -> คนอ่านและตอบ -> โมเดลคัดลอก REVIEW ทั้งก้อนกลับมาใน local_confirm
# แค่ review 6 บรรทัดก็ใช้ไป ~3 นาทีกว่าจะถึง local_confirm ครั้งแรก พอพลาดหนึ่งครั้ง token ก็หมดอายุก่อนลองใหม่ได้
# จึงขยายเป็น 10 นาที และเมื่อ review ไม่ตรง (token ไม่ถูกใช้) ต่อเวลาให้อีกไม่เกิน 5 นาที แต่รวมแล้วไม่เกิน
# 15 นาทีนับจากตอนออก — การผูก action + digest + โปรเจกต์ + ใช้ครั้งเดียว + กล่องอนุญาตที่แสดง review ยังอยู่ครบ
CONFIRM_TTL = 600.0        # วินาที — อายุของ token ตอนออก
CONFIRM_RETRY_TTL = 300.0  # review ไม่ตรง: ต่อให้เหลืออย่างน้อยเท่านี้ (เพื่อให้คัดลอกใหม่ทัน)
CONFIRM_TTL_MAX = 900.0    # เพดานอายุรวมนับจากตอนออก ต่อเวลากี่ครั้งก็เกินนี้ไม่ได้
# รอบ review (R3): เดิมค้างได้ถึง 200 token ต่อเครื่อง โมเดลจึงถือ token ที่ยังไม่ได้ให้คนดูไว้ได้เป็นกอง
# แล้วเลือกยืนยันตัวที่ไม่ตรงกับที่โชว์ในแชต — ตอนนี้ต่อโปรเจกต์ค้างได้แค่ 5 ตัว (เกินแล้วทิ้งตัวเก่าสุด)
# และทั้งเครื่องไม่เกิน MAX_PENDING (กันหลายโปรเจกต์รวมกันแล้วบวม)
MAX_PENDING = 64
MAX_PENDING_PER_PROJECT = 5
# แต่ละรายการเก็บอาร์กิวเมนต์ของการเรียกไว้เล่นซ้ำ (write_file มีเนื้อไฟล์ได้ถึง 16 MB ต่อคำขอ)
# จำกัดขนาดรวม ไม่งั้นการขอ token รัวๆ 200 ครั้งจะกิน RAM หลาย GB — เกินแล้วทิ้งรายการเก่าสุดก่อน
MAX_PENDING_BYTES = 64 * 1024 * 1024

_lock = threading.RLock()
_pending: dict[str, dict] = {}   # token -> {action, digest, scope, exp, issued, review, replay}
_ctx = threading.local()         # project / internal ของคำขอปัจจุบัน (หนึ่งเธรดต่อคำขอ)

def _user_home_roots() -> list[dict]:
    """โฟลเดอร์ของบัญชีที่รันอยู่ (%USERPROFILE%) เป็น root เขียนได้ — ไม่ฝังชื่อบัญชีไว้ในโค้ด

    รับเฉพาะรูป <ไดรฟ์>:\\Users\\<ชื่อ> กัน env แปลกๆ (เช่น systemprofile ของบริการ หรือ "~" ที่ขยายไม่ได้)
    กลายเป็น root เขียนได้ — หาไม่เจอ = ไม่เพิ่ม (C:\\ ที่เหลือยังเป็นอ่านอย่างเดียวตามเดิม)
    """
    home = (os.environ.get("USERPROFILE") or "").strip() or os.path.expanduser("~")
    if not home or home.startswith("~") or not os.path.isabs(home):
        return []
    home = os.path.normpath(home)
    parent = os.path.dirname(home)
    drive_root = os.path.splitdrive(home)[0] + "\\"
    if os.path.basename(parent).lower() == "users" and os.path.dirname(parent) == drive_root:
        return [{"path": home, "mode": "read_write"}]
    return []


# ---------------------------------------------------------------- ค่าเริ่มต้น
# อนุญาตกว้าง (ผู้ใช้ขอให้เข้าถึงได้ทุก path) แต่เขียนได้เฉพาะพื้นที่ของผู้ใช้กับไดรฟ์ข้อมูล
# ส่วน C:\ ที่เหลืออ่านได้อย่างเดียว กัน Windows/Program Files ถูกแก้โดยไม่ตั้งใจ
# D:\ E:\ F:\ ทั้งไดรฟ์เขียนได้โดยค่าเริ่มต้น — ปรับเป็นอ่านอย่างเดียวได้ใน config.json:
#   {"allowed_roots": [{"path": "D:\\", "mode": "read_only"}]}
DEFAULTS = {
    "allowed_roots": _user_home_roots() + [
        {"path": r"C:\LLM", "mode": "read_write"},
        {"path": "D:\\", "mode": "read_write"},
        {"path": "E:\\", "mode": "read_write"},
        {"path": "F:\\", "mode": "read_write"},
        {"path": "C:\\", "mode": "read_only"},
    ],
    # เทียบแบบ case-insensitive กับ path เต็มที่ normalize แล้ว (fnmatch: * ข้าม \ ได้)
    "blocked_globs": [
        # --- คีย์และ credential ของผู้ใช้ ---
        # บล็อกตัวโฟลเดอร์เองด้วย ไม่ใช่แค่ไฟล์ข้างใน ไม่งั้นยังตั้ง alias ชี้เข้าไป
        # หรือ list ดูว่ามีไฟล์อะไรอยู่ได้ ซึ่งเป็นการยืนยันว่ามีอะไรให้ขโมย
        r"*\.ssh", r"*\.aws", r"*\.azure", r"*\.gnupg", r"*\.gnupg\*",
        r"*\.ssh\*", r"*\.aws\*", r"*\.azure\*", r"*\.docker\config.json",
        r"*\.kube\*", r"*\.netrc", r"*\_netrc",
        r"*\.config\gh\*", r"*\.config\gcloud\*",
        # GitHub CLI บน Windows เก็บ token ไว้ที่ %APPDATA%\GitHub CLI\hosts.yml (ตรวจแล้วมีไฟล์อยู่จริง)
        r"*\AppData\Roaming\GitHub CLI", r"*\AppData\Roaming\GitHub CLI\*",
        r"*\AppData\Roaming\gcloud\*",
        # ไฟล์ที่เก็บ token ของ git/npm/pip ได้ในตัว (url มี user:token, _authToken, index-url)
        r"*\.git-credentials", r"*\.npmrc", r"*\.pypirc", r"*\pip\pip.ini", r"*\pip.ini",
        # --- OAuth / token ของเครื่องมือ AI ---
        r"*\.claude\.credentials.json", r"*\.claude\*credential*",
        r"*\.codex\auth*", r"*\.codex\*token*", r"*\.codex\*credential*",
        # ทั้งโฟลเดอร์: มีบันทึกบทสนทนา ความจำ และข้อมูลบัญชีของเครื่องมือ AI ตัวอื่น
        # (~\.claude.json มีข้อมูล OAuth ของบัญชี) — โมเดลในเครื่องไม่มีเหตุต้องอ่าน
        r"*\.claude", r"*\.claude\*", r"*\.claude.json", r"*\.claude.json.*",
        r"*\.codex", r"*\.codex\*",
        r"*\AppData\Roaming\Claude\*credential*",
        r"*\AppData\Local\OpenAI\*credential*", r"*\AppData\Local\OpenAI\*token*",
        # --- ฐานข้อมูลของแอป (รหัสผ่าน คุกกี้ ประวัติ) ---
        r"*\User Data\*Login Data*", r"*\User Data\*Cookies*", r"*\User Data\*Web Data*",
        r"*\User Data\*Local State*", r"*\User Data\*Login Data For Account*",
        # โปรไฟล์แยกของ tools_browser ไม่มีคำว่า "User Data" ใน path จึงต้องดักชื่อไฟล์ตรงๆ ด้วย
        r"*\Network\Cookies", r"*\Network\Cookies-journal", r"*\Login Data",
        r"*\Login Data-journal", r"*\Web Data", r"*\Web Data-journal",
        r"*\browser-profile\*\Local State",
        # ประวัติการท่องเว็บ/เซสชันที่เปิดค้าง (Chromium) และโปรไฟล์ Firefox ทั้งก้อน (logins.json, key4.db)
        r"*\User Data\*\History", r"*\User Data\*\History-journal",
        r"*\User Data\*\Sessions\*", r"*\User Data\*\Current Session", r"*\User Data\*\Last Session",
        r"*\Mozilla\Firefox\Profiles\*",
        # สถานะของ VS Code (มี token ของ extension/บัญชีที่ลงชื่อเข้าไว้)
        r"*\Code\User\globalStorage\state.vscdb*", r"*\Code\User\globalStorage\*\*token*",
        r"*\AppData\Roaming\LINE\*", r"*\AppData\Local\LINE\*",
        r"*\AppData\Roaming\Telegram Desktop\tdata\*",
        r"*\AppData\Roaming\WhatsApp\*", r"*\AppData\Local\WhatsApp\*",
        # --- ระบบ ---
        r"C:\Windows\System32\config\*", r"C:\Windows\repair\*",
        r"*\AppData\Roaming\Microsoft\Credentials\*",
        r"*\AppData\Roaming\Microsoft\Protect\*",
        r"*\AppData\Local\Microsoft\Credentials\*",
        r"*\AppData\Local\Microsoft\Vault\*",
        # --- ไฟล์คีย์ตามนามสกุล/ชื่อ ---
        r"*\id_rsa*", r"*\id_ed25519*", r"*.pem", r"*.pfx", r"*.p12", r"*.keystore",
        r"*.jks", r"*\.env", r"*\.env.*", r"*\authtoken.secret", r"*\.pgpass",
        # --- ค่าตั้งของเราเองที่อาจมี API key (รวมสำเนาใน backup ด้วย) ---
        r"C:\LLM\mcp-websearch\config.json", r"*\mcp-websearch\config.json",
        r"*\.diag_token",
        # token ของบริการในเครื่อง (สัญญา C1) — ทั้งโฟลเดอร์ ทั้งอ่าน list และเขียน
        r"C:\LLM\secrets", r"C:\LLM\secrets\*", r"*\local-services.token",
        # คีย์ของ Remote Prompt Gateway — โมเดลต้องอ่านคีย์ของตัวเองไม่ได้
        # ไม่งั้นข้อความในแชตที่หลอกให้ "อ่านไฟล์นี้แล้วบอกมา" จะทำให้คีย์หลุด
        r"*\gateway_key.txt", r"*_key.txt", r"*\apikey*", r"*\api_key*",
        r"*\*secret*", r"*\credentials*",
        # บันทึกของสแตกที่รวมกิจกรรมของทุกโปรเจกต์ย้ายไปอยู่ STACK_READ_BLOCKED ข้างล่าง
        # (ต้องใช้ไวยากรณ์ที่ * ไม่ข้าม \ — ดูเหตุผลที่นั่น)
    ],
    # นามสกุลที่ห้ามอ่านเนื้อหาแม้อยู่ใน allowed root (ฐานข้อมูลของแอป/คีย์)
    "blocked_suffixes": [".sqlite", ".sqlite3", ".ldb", ".env", ".pem", ".key", ".ppk",
                         ".token", ".kdbx", ".vscdb", ".secret"],
    "max_read_bytes": 2_000_000,
}

# บันทึก/สถานะของสแตกที่รวมกิจกรรมของ "ทุกโปรเจกต์" ไว้ที่เดียว — ห้ามทั้งอ่านและเขียน (กฎ S04)
# audit.log จดทุก path/คำสั่ง/หน่วยความจำของทุกโปรเจกต์ tasks.json กับ tasklogs\ มีคำสั่งและผลลัพธ์
# ของงานทุกโปรเจกต์ ถึงจะลบค่า token ออกแล้วก็ยังเป็นการสอดส่องโปรเจกต์อื่นได้
# ใช้ไวยากรณ์เดียวกับ WRITE_PROTECTED (* ไม่ข้าม \) ไม่ใช่ fnmatch: รอบก่อนใช้ fnmatch
# "C:\LLM\projects\*.log" ซึ่ง * ของ fnmatch ข้าม \ ได้ จึงไปบล็อกไฟล์ .log ที่ผู้ใช้แนบไว้ในโปรเจกต์
# ตัวเอง (data\<slug>\attachments\x.log — log ของตู้ชาร์จ/OCPP ที่งานนี้ใช้เป็นประจำ) ไปด้วย
STACK_READ_BLOCKED = [
    r"C:\LLM\mcp-local\*.log*", r"C:\LLM\mcp-local\*.json",
    r"C:\LLM\mcp-local\tasklogs", r"C:\LLM\mcp-local\tasklogs\**",
    r"C:\LLM\mcp-websearch\*.log*",
    r"C:\LLM\logs", r"C:\LLM\logs\**",
    r"C:\LLM\projects\*.log*",
]

# เขตห้ามเขียน — ปฏิเสธแม้ผู้ใช้ส่ง confirm_token มา และ config.json ลบออกไม่ได้
# ไวยากรณ์ของตัวเอง (ไม่ใช่ fnmatch): ** = อะไรก็ได้รวม \   * = อะไรก็ได้ยกเว้น \
# ต้องแยกกันเพราะ "*.py ตรงใต้ C:\LLM" ต้องไม่ลามไปกินทุก .py ในโฟลเดอร์ย่อยของผู้ใช้
WRITE_PROTECTED = [
    # --- โค้ดและค่าตั้งของสแตกนี้เอง (แก้ได้ = ปิดด่านทั้งหมดได้) ---
    r"C:\LLM\mcp-local", r"C:\LLM\mcp-local\**",
    r"C:\LLM\mcp-websearch", r"C:\LLM\mcp-websearch\**",
    r"C:\LLM\projects\*.py", r"C:\LLM\projects\*.json",
    r"C:\LLM\projects\static", r"C:\LLM\projects\static\**",
    r"C:\LLM\projects\tools", r"C:\LLM\projects\tools\**",
    r"C:\LLM\projects\backup", r"C:\LLM\projects\backup\**",
    r"C:\LLM\projects\__pycache__\**",
    r"C:\LLM\*.ps1", r"C:\LLM\*.psm1", r"C:\LLM\*.cmd", r"C:\LLM\*.bat",
    r"C:\LLM\*.ini", r"C:\LLM\*.py", r"C:\LLM\*.json", r"C:\LLM\*.vbs",
    r"C:\LLM\__pycache__\**",
    r"C:\LLM\tests", r"C:\LLM\tests\**",
    # [skills] B4: แม่แบบพรอมต์ที่ผู้ใช้เลือกส่งให้โมเดลเอง — ถ้าเครื่องมือเขียนได้ ข้อความในเว็บ/ไฟล์ที่หลอกโมเดล
    # จะฝังคำสั่งถาวรลงใน skill ที่ผู้ใช้ไว้ใจได้ (persistence ทางพรอมต์) แก้ได้เฉพาะผู้ใช้เอง
    r"C:\LLM\skills", r"C:\LLM\skills\**",
    r"C:\LLM\secrets", r"C:\LLM\secrets\**",
    r"C:\LLM\llama.cpp", r"C:\LLM\llama.cpp\**",
    r"C:\LLM\llama.cpp-*", r"C:\LLM\llama.cpp-*\**",
    r"C:\LLM\models\**", r"D:\LLM\models\**",
    # [docs2] batch 2a fixer: ของที่สแตกรัน/โหลดเองอัตโนมัติรอบนี้ — tesseract.exe (+DLL, tessdata\configs ที่มี
    # debug_file ฯลฯ) ถูก MCP เรียกเองแม้จากงานเบื้องหลังของ kb; โมเดล embedding ถูก launcher โหลด
    # เขียนทับ/วาง DLL ได้ = โค้ดรันในโปรเซสของสแตกทุกครั้งที่ OCR จึงห้ามเหมือน llama.cpp/models (แม้มี confirm)
    r"C:\LLM\tools", r"C:\LLM\tools\**",
    r"D:\LLM\models-embed", r"D:\LLM\models-embed\**",
    # [docs2] ดัชนี/แคช OCR ของ kb (data\<slug>\kb) — MCP เขียนเองผ่านทางภายใน (tools_kb/extract ไม่ผ่านด่านนี้)
    # เครื่องมือห้ามเขียน: แคช OCR ปลอม = เนื้อหาปลอมของเอกสารผู้ใช้ที่ติดป้ายความมั่นใจสูง, index.db ปลอม = kb พัง
    str(PROJECT_DATA) + r"\*\kb", str(PROJECT_DATA) + r"\*\kb\**",
    r"C:\LLM\projects\data\*\kb", r"C:\LLM\projects\data\*\kb\**",
    # [/docs2]
    # [voice] batch 2b: บริการถอดเสียง (stt_server.py ที่ launcher รันเองทุกครั้งที่เปิดสแตก + สำเนาโมเดลในเครื่อง
    # ใต้ stt\models) — แก้โค้ด/วางโมเดลปลอมได้ = โค้ดรันถาวรในโปรเซสที่ถือ token และได้ยินเสียงผู้ใช้ จึงห้ามแม้มี confirm
    r"C:\LLM\stt", r"C:\LLM\stt\**",
    # [/voice]
    # โปรไฟล์เบราว์เซอร์แยก: เบราว์เซอร์เขียนเอง เครื่องมือไฟล์ห้ามยัด extension/ค่าตั้งเข้าไป
    r"C:\LLM\browser-profile\**",
    # --- จุดที่ทำให้โค้ดรันเองตอนเปิดเครื่อง/เปิด shell (persistence) ---
    r"**\Start Menu\Programs\Startup", r"**\Start Menu\Programs\Startup\**",
    r"**\Documents\WindowsPowerShell\**", r"**\Documents\PowerShell\**",
    r"**\*profile.ps1",
    r"**\.git", r"**\.git\**", r"**\.gitconfig", r"**\.config\git\**",
    r"**\.bashrc", r"**\.bash_profile", r"**\.bash_login", r"**\.profile",
    r"**\.zshrc", r"**\.zprofile",
    r"**\.claude\**", r"**\.claude.json",
    r"**\site-packages\*.pth", r"**\sitecustomize.py", r"**\usercustomize.py",
    r"**\__pycache__\**", r"**\*.pyc",
    r"**\Microsoft\Word\STARTUP\**", r"**\Microsoft\Excel\XLSTART\**",
    r"**\Microsoft\Templates\Normal.dotm",
    r"**\Packages\Microsoft.WindowsTerminal*\LocalState\**",
    r"**\AppData\Local\Microsoft\WindowsApps\**",
    r"**\.npmrc", r"**\pip\pip.ini", r"**\.condarc",
    # .vscode\tasks.json มี runOn:folderOpen (รันคำสั่งเองตอนเปิดโฟลเดอร์) และ settings.json
    # ตั้ง interpreter/terminal ที่รันโปรแกรมได้ = จุด persistence เช่นกัน (ช่องโหว่ที่ audit พบ)
    r"**\.vscode", r"**\.vscode\**",
]

# นามสกุลที่ "สร้างไฟล์ใหม่" แล้วต้องยืนยันก่อน (ไฟล์พวกนี้รันได้หรือถูกโหลดเป็นโค้ด)
SCRIPT_EXTS = frozenset((
    ".py", ".pyw", ".ps1", ".psm1", ".psd1", ".bat", ".cmd", ".js", ".jse", ".mjs", ".cjs",
    ".vbs", ".vbe", ".wsf", ".wsh", ".ws", ".lnk", ".exe", ".dll", ".reg", ".scr", ".hta",
    ".com", ".pif", ".cpl", ".msi", ".msc", ".jar", ".sh", ".pth", ".url", ".appref-ms",
    ".settingcontent-ms", ".library-ms", ".sys", ".ocx",
    # เพิ่มรอบ audit: นามสกุลที่ถูกรัน/โหลดเป็น handler ได้เช่นกัน แต่เดิมตกหล่น
    #   .scf (Shell Command File รันตอนโฟลเดอร์ถูกเปิด/พรีวิว), .inf (สั่ง RunOnce ได้),
    #   .chm (คอมไพล์ HTML Help รันสคริปต์ได้), .xll (Excel add-in = DLL),
    #   .application/.appref-ms (ClickOnce), .ps1xml/.psc1 (โหลดเข้า PowerShell)
    ".scf", ".inf", ".chm", ".xll", ".application", ".ps1xml", ".psc1",
))

_cfg_cache: dict = {"key": None, "cfg": None}


def _merge_config(user: dict) -> dict:
    """รวมค่าของผู้ใช้เข้ากับค่าเริ่มต้น — เพิ่มได้ แต่ลบของที่ฝังไว้ไม่ได้

    ของเดิม `cfg[k] = v` แปลว่าไฟล์ที่มีแค่ {"blocked_globs": []} ปิดการบล็อกทั้งหมดได้ (V2)
    """
    cfg = copy.deepcopy(DEFAULTS)
    if not isinstance(user, dict):
        return cfg
    roots = {os.path.normcase(r["path"]).rstrip("\\"): dict(r) for r in cfg["allowed_roots"]}
    builtin = set(roots)
    for r in user.get("allowed_roots") or []:
        if isinstance(r, dict) and isinstance(r.get("path"), str) and r["path"].strip():
            key = os.path.normcase(r["path"]).rstrip("\\")
            mode = "read_write" if r.get("mode") == "read_write" else "read_only"
            if key in builtin and roots[key]["mode"] == "read_only":
                mode = "read_only"          # root ที่ฝังไว้แบบอ่านอย่างเดียว (C:\) ผู้ใช้ปลดเป็นเขียนได้ไม่ได้
            roots[key] = {"path": r["path"], "mode": mode}
    cfg["allowed_roots"] = list(roots.values())
    for key in ("blocked_globs", "blocked_suffixes"):
        extra = [x for x in (user.get(key) or []) if isinstance(x, str) and x.strip()]
        cfg[key] = cfg[key] + [x for x in extra if x not in cfg[key]]
    extra_wp = [x for x in (user.get("write_protected") or []) if isinstance(x, str) and x.strip()]
    cfg["write_protected"] = WRITE_PROTECTED + [x for x in extra_wp if x not in WRITE_PROTECTED]
    try:
        cfg["max_read_bytes"] = max(1024, min(int(user.get("max_read_bytes",
                                                          cfg["max_read_bytes"])), 50_000_000))
    except (TypeError, ValueError):
        pass
    return cfg


def _load_config() -> dict:
    """อ่าน config.json (ถ้ามี) แล้วรวมกับค่าเริ่มต้น cache ตาม mtime กันอ่านดิสก์ทุกครั้งที่ตรวจ path"""
    try:
        st = CONFIG_PATH.stat()
        key = (str(CONFIG_PATH), st.st_mtime_ns, st.st_size)
    except OSError:
        key = (str(CONFIG_PATH), None, None)
    with _lock:
        if _cfg_cache["key"] == key and _cfg_cache["cfg"] is not None:
            return _cfg_cache["cfg"]
    user = {}
    if key[1] is not None:
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                user = {k: v for k, v in raw.items() if not str(k).startswith("_")}
        except (OSError, ValueError):
            user = {}
    cfg = _merge_config(user)
    with _lock:
        _cfg_cache["key"], _cfg_cache["cfg"] = key, cfg
    return cfg


class Denied(Exception):
    """path หรือการกระทำนี้ถูกปฏิเสธโดยนโยบายความปลอดภัย"""


# ------------------------------------------------------------------- audit
_SCRUB_RES = (
    (re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/\s@]+@"), r"\1***@"),
    (re.compile(r"(?i)((?:access_token|id_token|refresh_token|api[-_]?key|token|password|secret|"
                r"authorization)\s*[=:]\s*(?:bearer\s+)?)([^\s&#\"']+)"), r"\1***"),
    (re.compile(r"(?i)\b(sk-|ghp_|gho_|github_pat_|xox[baprs]-|AKIA|AIza)[A-Za-z0-9_\-]{8,}"), r"\1***"),
    (re.compile(r"\b[0-9a-fA-F]{64}\b"), "***"),
    # confirm_token ที่อยู่ในข้อความตอบกลับ (เช่น ผลของเครื่องมือที่ถูกบันทึกบางส่วน)
    (re.compile(r"(?i)(confirm_token\s*[=:]\s*\"?)[0-9a-f]{6,}"), r"\1***"),
)


def scrub_text(text) -> str:
    """ลบรูปแบบที่ดูเหมือนความลับออกจากข้อความก่อนลงบันทึก (hex 64 ตัว = รูปแบบของ token C1)"""
    out = str(text)
    for rx, rep in _SCRUB_RES:
        out = rx.sub(rep, out)
    return out


def audit(kind: str, detail: dict) -> None:
    """บันทึกทุกการเรียกเครื่องมือ ไม่มีวันโยน exception ออกไปรบกวนผู้เรียก"""
    line = json.dumps(
        {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "kind": kind, **detail},
        ensure_ascii=False, default=str)
    try:
        with AUDIT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------- ขอบเขตของคำขอปัจจุบัน
_SLUG_RE = re.compile(r"[^\w\u0E00-\u0E7F-]+", re.UNICODE)


def project_slug(project: str) -> str:
    s = unicodedata.normalize("NFKD", str(project or "").strip())
    s = _SLUG_RE.sub("-", s).strip("-").lower()
    return s[:40] or "default"


def current_project() -> str | None:
    """slug ของโปรเจกต์ที่คำขอนี้ทำงานอยู่ หรือ None ถ้าไม่ได้มาจาก tools/call"""
    return getattr(_ctx, "project", None)


@contextmanager
def project_scope(project: str):
    """server.py ครอบทุก tools/call ด้วยตัวนี้ slug มาจาก URL เสมอ ไม่ใช่จากโมเดล"""
    prev = getattr(_ctx, "project", None)
    _ctx.project = project_slug(project)
    try:
        yield _ctx.project
    finally:
        _ctx.project = prev


@contextmanager
def internal():
    """สำหรับโค้ดของเราเองที่อ่าน/เขียน path คงที่ (state ของ scheduler, session ของ gateway)

    ข้ามเขตห้ามเขียนและขอบเขตโปรเจกต์ แต่ยังเคารพ blocked_globs กับ allowed_roots
    ห้ามครอบโค้ดที่ส่ง path จากโมเดลเข้ามา — ใช้กับค่าคงที่ในโค้ดเท่านั้น
    """
    prev = getattr(_ctx, "internal", 0)
    _ctx.internal = prev + 1
    try:
        yield
    finally:
        _ctx.internal = prev


def _is_internal() -> bool:
    return getattr(_ctx, "internal", 0) > 0


# -------------------------------------------------------------- path guard
# \\?\ (extended-length) และ \\.\ (device namespace) — ทั้งคู่เปิดไฟล์เดียวกับ path ปกติได้
_EXTENDED_PREFIX_RE = re.compile(r'^[\\/]{2}[?.][\\/]+(?:UNC[\\/]+)?', re.IGNORECASE)
_DRIVE_OR_UNC_RE = re.compile(r'^(?:[A-Za-z]:(?:[\\/]|$)|[\\/]{2}[^\\/?.])')


def _strip_extended_prefix(path: str) -> str:
    r"""ตัดคำนำหน้า \\?\ \\.\ หรือ \\?\UNC\ ของ Windows ออกก่อนเทียบ path

    ทำไม: \\?\C:\LLM\mcp-local\guard.py (และ \\.\C:\...) ชี้ไฟล์เดียวกับ C:\LLM\mcp-local\guard.py
    แต่ write_protected_hit/allowed_roots เทียบสตริงตรงๆ จึงมองไม่เห็นรูปนี้
    เดิมมันถูกปฏิเสธด้วยเหตุบังเอิญ (นอก allowed_roots) ตอนนี้ทำให้ด่านห้ามเขียนเห็นตรงๆ
    UNC (\\?\UNC\server\share) แปลงกลับเป็น \\server\share
    รูปที่ไม่ใช่ไดรฟ์หรือ UNC หลังตัดคำนำหน้า (\\?\Volume{..}\, \\.\GLOBALROOT\, \\.\pipe\)
    ถูกปฏิเสธใน _check — ถ้าปล่อยผ่านมันจะกลายเป็น path สัมพัทธ์ที่ถูกต่อกับ cwd แบบผิดความหมาย
    """
    s = str(path or "")
    m = _EXTENDED_PREFIX_RE.match(s)
    if not m:
        return s
    rest = s[m.end():]
    return ("\\\\" + rest) if m.group(0).rstrip("\\/").lower().endswith("unc") else rest


def _abs(path: str) -> str:
    p = os.path.expandvars(os.path.expanduser(_strip_extended_prefix(str(path or "").strip().strip('"'))))
    return os.path.normpath(os.path.abspath(p)) if p else ""


def _norm(path: str) -> str:
    """ทำให้ path เทียบได้แน่นอน: absolute, แก้ .. , แปลง / เป็น \\ , คลาย symlink"""
    p = _abs(path)
    if not p:
        return ""
    try:
        # คลาย junction/symlink กัน bypass ด้วยลิงก์ที่ชี้ออกนอก allowed root
        p = os.path.realpath(p)
    except OSError:
        pass
    return os.path.normpath(p)


def _under(path: str, root: str) -> bool:
    path_l, root_l = path.lower().rstrip("\\"), _norm(root).lower().rstrip("\\")
    if not root_l:
        return False
    return path_l == root_l or path_l.startswith(root_l + "\\")


def _blocked(path: str, cfg: dict, stack: bool = True) -> str | None:
    low = path.lower()
    for pat in cfg["blocked_globs"]:
        if fnmatch.fnmatch(low, pat.lower()):
            return pat
    for suf in cfg["blocked_suffixes"]:
        if low.endswith(suf.lower()):
            return "*" + suf
    # บันทึก/สถานะของสแตกห้าม "เครื่องมือ" แตะ แต่โค้ดของสแตกเองต้องอ่านเขียนไฟล์ของตัวเองได้
    # (scheduler_state.json ของ scheduler) — ผู้เรียกใน internal() ใช้ path คงที่ในโค้ดเท่านั้น
    if stack:
        for pat in STACK_READ_BLOCKED:
            if _wp_regex(pat).match(path):
                return pat
    return None


_wp_cache: dict[str, re.Pattern] = {}


def _wp_regex(pattern: str) -> re.Pattern:
    rx = _wp_cache.get(pattern)
    if rx is None:
        out, i = [], 0
        while i < len(pattern):
            if pattern.startswith("**", i):
                out.append(".*")
                i += 2
            elif pattern[i] == "*":
                out.append(r"[^\\]*")
                i += 1
            elif pattern[i] == "?":
                out.append(r"[^\\]")
                i += 1
            else:
                out.append(re.escape(pattern[i]))
                i += 1
        rx = re.compile("^" + "".join(out) + "$", re.IGNORECASE)
        _wp_cache[pattern] = rx
    return rx


def write_protected_hit(path: str, cfg: dict | None = None) -> str | None:
    """คืนรูปแบบที่ชน ถ้า path (แบบคลายลิงก์แล้วหรือยังไม่คลายก็ตาม) อยู่ในเขตห้ามเขียน"""
    cfg = cfg or _load_config()
    pats = cfg.get("write_protected") or WRITE_PROTECTED
    for cand in {_norm(path), _abs(path)}:
        if not cand:
            continue
        for pat in pats:
            if _wp_regex(pat).match(cand):
                return pat
    return None


def is_write_protected(path: str) -> bool:
    return write_protected_hit(path) is not None


def is_script_path(path: str) -> bool:
    return os.path.splitext(str(path))[1].lower() in SCRIPT_EXTS


def _nfkd_low(text: str) -> str:
    return unicodedata.normalize("NFKD", text).lower()


_forms_cache: dict[str, tuple] = {}


def _forms(path: str) -> tuple:
    """รูปเทียบได้ของ path คงที่ (ทั้งแบบคลายลิงก์และไม่คลาย) cache ไว้ เพราะ list_dir ตรวจทีละไฟล์"""
    got = _forms_cache.get(path)
    if got is None:
        got = tuple({_nfkd_low(f).rstrip("\\") for f in (_norm(path), _abs(path)) if f})
        _forms_cache[path] = got
    return got


def _scope_violation(p: str) -> str | None:
    """S04: ภายในคำขอของโปรเจกต์ X ห้ามแตะข้อมูลของโปรเจกต์อื่น

    fail closed: ถ้าไม่มีขอบเขตโปรเจกต์ (current_project() is None) และไม่ใช่โค้ดภายใน
    ห้ามแตะ path ใต้ข้อมูล/โปรไฟล์เบราว์เซอร์ของโปรเจกต์ใดๆ เลย เดิมปล่อยผ่าน (fail open)
    เธรด/โค้ดที่เรียก guard นอก project_scope จึงข้าม S04 ได้ทั้งหมด — โค้ดของเราเองที่
    ต้องแตะ path เหล่านี้ต้องครอบด้วย guard.internal() (ค่าคงที่ในโค้ด) อย่างชัดเจนอยู่แล้ว
    """
    if _is_internal():
        return None
    slug = current_project()
    mine = _nfkd_low(slug) if slug is not None else None
    low = _nfkd_low(p)
    for root in (PROJECT_DATA, BROWSER_PROFILES):
        for r in _forms(str(root)):
            if low.startswith(r + "\\"):
                if mine is None:
                    return "no_project_scope"
                first = low[len(r) + 1:].split("\\", 1)[0]
                if first != mine:
                    return "other_project"
    if low in _forms(str(PROJECTS_JSON)):
        return "hub_project_list"      # มี system prompt ของทุกโปรเจกต์รวมกันอยู่
    return None


def _device_path_violation(path: str) -> bool:
    r"""True ถ้าเป็น \\?\ หรือ \\.\ ที่ข้างในไม่ใช่ไดรฟ์/UNC (Volume GUID, GLOBALROOT, pipe, อุปกรณ์)"""
    s = str(path or "").strip().strip('"')
    if not _EXTENDED_PREFIX_RE.match(s):
        return False
    return not _DRIVE_OR_UNC_RE.match(_strip_extended_prefix(s))


def _check(path: str, need_write: bool) -> str:
    cfg = _load_config()
    if _device_path_violation(path):
        audit("denied", {"path": scrub_text(str(path))[:200], "reason": "device_namespace",
                         "write": need_write})
        raise Denied("path รูปแบบอุปกรณ์ของ Windows (\\\\?\\ หรือ \\\\.\\ ที่ไม่ใช่ไดรฟ์) ไม่อนุญาต")
    p = _norm(path)
    if not p or len(p) < 3:
        raise Denied("path ไม่ถูกต้อง")

    raw = _abs(path)
    # NTFS alternate data stream (x.pem::$DATA, Cookies:$DATA) เปิดอ่านเนื้อไฟล์เดิมได้จริง
    # แต่ชื่อไม่ลงท้ายด้วย .pem/.key/Cookies แล้ว ด่านนามสกุล/ชื่อไฟล์จึงมองไม่เห็น — ปฏิเสธทั้งหมด
    for form in (p, raw):
        if form and ":" in os.path.splitdrive(form)[1]:
            audit("denied", {"path": p, "reason": "alternate_data_stream", "write": need_write})
            raise Denied("path ที่มี ':' (alternate data stream ของ NTFS) ไม่อนุญาต")
    stack = not _is_internal()
    hit = _blocked(p, cfg, stack) or (_blocked(raw, cfg, stack) if raw else None)
    if hit:
        audit("denied", {"path": p, "reason": "blocked", "pattern": hit,
                         "write": need_write})
        raise Denied("path นี้อยู่ในรายการต้องห้าม (credential/ฐานข้อมูลแอป/ไฟล์ระบบ) "
                     "จึงเข้าถึงไม่ได้")

    scope = _scope_violation(p) or (_scope_violation(raw) if raw else None)
    if scope:
        audit("denied", {"path": p, "reason": scope, "project": current_project(),
                         "write": need_write})
        raise Denied("path นี้เป็นข้อมูลของโปรเจกต์อื่น (กฎ S04) โปรเจกต์นี้เข้าถึงไม่ได้")

    best = None
    for root in cfg["allowed_roots"]:
        rp = _norm(root["path"])
        if _under(p, rp):
            # เลือก root ที่เจาะจงที่สุด (ยาวสุด) เพื่อให้ read_write ชนะ read_only ของ C:\
            if best is None or len(rp) > len(_norm(best["path"])):
                best = root
    if best is None:
        audit("denied", {"path": p, "reason": "outside_roots", "write": need_write})
        raise Denied("path อยู่นอกพื้นที่ที่อนุญาต")

    if need_write and best.get("mode") != "read_write":
        audit("denied", {"path": p, "reason": "read_only_root",
                         "root": best["path"]})
        raise Denied("พื้นที่นี้เปิดให้อ่านอย่างเดียว (%s) เขียนไม่ได้" % best["path"])

    if need_write and not _is_internal():
        wp = write_protected_hit(path, cfg)
        if wp:
            audit("denied", {"path": p, "reason": "write_protected", "pattern": wp})
            raise Denied("path นี้อยู่ในเขตห้ามเขียน (โค้ด/ค่าตั้งของระบบ หรือจุดที่ทำให้โปรแกรม"
                         "รันเองอัตโนมัติ) เครื่องมือแก้ไม่ได้แม้ผู้ใช้อนุมัติ "
                         "ถ้าจำเป็นจริงให้ผู้ใช้แก้เอง")
    return p


def check_read(path: str) -> str:
    return _check(path, need_write=False)


def check_write(path: str) -> str:
    return _check(path, need_write=True)


def _short_name(path: str) -> str:
    """คืนชื่อ 8.3 (short name) ของไฟล์ เช่น SAMPLE~1.TXT หรือ "" ถ้าไม่มี/เรียกไม่ได้"""
    try:
        buf = ctypes.create_unicode_buffer(260)
        n = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 260)  # type: ignore[attr-defined]
        if n and n < 260:
            return buf.value
    except Exception:      # noqa: BLE001 — ไม่ใช่ Windows/ไม่รองรับ 8.3 ก็แค่ไม่มีชื่อสั้น
        pass
    return ""


def _find_win32(pattern: str, limit: int) -> list[str] | None:
    r"""ขยาย wildcard ขององค์ประกอบสุดท้ายด้วย FindFirstFileW — ตัวเดียวกับที่ cmd/type/dir/findstr ใช้

    คืน None ถ้าเรียก API ไม่ได้ (ไม่ใช่ Windows) ให้ผู้เรียกถอยไปใช้ fnmatch เอง
    ทำไมต้องใช้ของ OS แทนการเลียนแบบ (ช่องโหว่ที่ audit พบ + ที่พบเพิ่มรอบนี้):
      * cmd เทียบชื่อ 8.3 ด้วย: SAMPLE~?.TXT เปิด sample_key.txt ได้
      * ? ของ DOS ตรง "ศูนย์ตัวอักษร" ได้ที่ท้ายชื่อ/หน้าจุด: sample_key??.txt เปิด sample_key.txt
      * [ ] เป็นตัวอักษรธรรมดา ไม่ใช่ character class: [a]b* เปิดไฟล์ชื่อ "[a]b_key.txt"
    กติกาพวกนี้อยู่ในไดรเวอร์ระบบไฟล์ เลียนแบบเองยังไงก็พลาดสักกรณี จึงถาม OS ตรงๆ
    """
    try:
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    except Exception:          # noqa: BLE001 — ไม่ใช่ Windows
        return None
    find_first = k32.FindFirstFileW
    find_first.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.WIN32_FIND_DATAW)]
    find_first.restype = wintypes.HANDLE
    find_next = k32.FindNextFileW
    find_next.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.WIN32_FIND_DATAW)]
    find_next.restype = wintypes.BOOL
    k32.FindClose.argtypes = [wintypes.HANDLE]
    invalid = wintypes.HANDLE(-1).value
    data = wintypes.WIN32_FIND_DATAW()
    handle = find_first(pattern, ctypes.byref(data))
    if handle is None or handle == invalid:
        return []
    head = os.path.dirname(pattern)
    out = []
    try:
        while True:
            name = data.cFileName
            if name not in (".", ".."):
                out.append(os.path.join(head, name))
                if len(out) > limit:
                    break
            if not find_next(handle, ctypes.byref(data)):
                break
    finally:
        k32.FindClose(handle)
    return out


def _glob_last_component(base: str, limit: int = 2000) -> list[str]:
    r"""หาไฟล์ที่ตรง wildcard "ในองค์ประกอบสุดท้าย" ด้วยกติกาของ cmd (ชื่อ 8.3, ? ของ DOS, [ ] ตรงตัว)

    โฟลเดอร์ต้นทางที่มี wildcard (ซึ่ง cmd เองไม่รองรับ แต่เครื่องมือแบบ MSYS รองรับ)
    ขยายด้วย glob ก่อน แล้วค่อยถาม OS ทีละโฟลเดอร์
    """
    head, tail = os.path.split(base)
    if not tail or not any(c in tail for c in "*?"):
        return []
    heads = [head]
    if head and any(c in head for c in "*?["):
        heads = [h for h in _glob.glob(head, include_hidden=True) if os.path.isdir(h)][:limit]
    found: list[str] = []
    for h in heads:
        got = _find_win32(os.path.join(h, tail), limit)
        if got is None:              # ไม่ใช่ Windows: เทียบเองทั้งชื่อยาวและชื่อ 8.3 (ถ้ามี)
            got = []
            try:
                with os.scandir(h or ".") as it:
                    for e in it:
                        names = [e.name]
                        sp = _short_name(e.path)
                        if sp:
                            names.append(os.path.basename(sp))
                        if any(fnmatch.fnmatch(nm.lower(), tail.lower()) for nm in names):
                            got.append(e.path)
            except OSError:
                pass
        found.extend(got)
        if len(found) > limit:
            break
    return found


def check_glob(pattern: str, need_write: bool = False, limit: int = 2000) -> list[str]:
    """ขยาย wildcard ใน path แล้วตรวจทุกไฟล์ที่ตรง — ใช้กับอาร์กิวเมนต์ของคำสั่ง shell

    `type C:\\LLM\\secre*\\*` ไม่มีคำว่า secrets ให้จับ แต่ cmd ขยายแล้วอ่านไฟล์ token ได้จริง
    จึงต้องดูผลการขยายจริง ไม่ใช่ข้อความ  เราไม่รู้ว่าโปรแกรมปลายทางขยาย wildcard แบบไหน
    (cmd = กติกา DOS, MSYS/Python = กติกา glob ที่ [ ] เป็น class) จึงเอา "ผลรวม" ของทุกแบบมาตรวจ
    """
    base = _abs(pattern)
    # include_hidden: cmd/MSYS ขยาย * ให้รวมโฟลเดอร์ที่ขึ้นต้นด้วยจุดด้วย (.ssh) ด่านต้องเห็นเท่ากัน
    hits = list(_glob.glob(base, include_hidden=True))
    if "[" in base:
        # [ ] ตรงตัวแบบ cmd — escape แบบ glob คือห่อ [ ด้วย [[]
        hits += _glob.glob(base.replace("[", "[[]"), include_hidden=True)
    hits += _glob_last_component(base, limit)
    uniq, seen = [], set()
    for h in hits:
        key = os.path.normcase(h)
        if key not in seen:
            seen.add(key)
            uniq.append(h)
    hits = uniq
    if len(hits) > limit:
        raise Denied("wildcard %s ตรงกับไฟล์มากเกิน %d รายการ ระบุให้แคบลง" % (pattern, limit))
    out = []
    for h in hits:
        out.append(_check(h, need_write))
    # ตัว pattern เองก็ต้องไม่ชี้เข้าเขตต้องห้าม แม้ตอนนี้ยังไม่มีไฟล์ที่ตรง
    parent = os.path.dirname(base)
    while parent and any(ch in parent for ch in "*?"):
        parent = os.path.dirname(parent)
    if parent:
        _check(parent, False)
    return out


def max_read_bytes() -> int:
    return int(_load_config().get("max_read_bytes", 2_000_000))


# ---------------------------------------------- คำสั่ง shell: ข้อความต้องห้าม
# ตรวจ "ตัวข้อความ" ของคำสั่ง เป็นด่านเสริมจากการตรวจ path ทีละโทเคน
# ด่านนี้จับได้แม้ path ถูกเขียนแบบ / หรือซ่อนอยู่ในโค้ดของ -c
_SECRET_TEXT_RE = re.compile(r"(?i)(llm[\\/]+secrets\b|local-services\.token|gateway_key)")
_PROTECTED_TEXT_RE = re.compile(
    r"(?i)("
    r"c:[\\/]+llm[\\/]+(mcp-local|mcp-websearch|tests|llama\.cpp|models|browser-profile|skills)\b|"
    r"c:[\\/]+llm[\\/]+projects[\\/]+(static|tools|backup|hub[^\\/\s\"']*\.py|[^\\/\s\"']+\.json)|"
    r"c:[\\/]+llm[\\/]+[^\\/\s\"']+\.(ps1|psm1|cmd|bat|ini|py|json|vbs)\b|"
    r"\.git[\\/]+(hooks|config)\b|start menu[\\/]+programs[\\/]+startup|"
    r"windowspowershell|documents[\\/]+powershell|profile\.ps1|"
    r"\.bashrc|\.bash_profile|\.gitconfig|\.claude\b|\.claude\.json|"
    # [docs2] Tesseract/เครื่องมือของสแตก, โมเดล embedding (และโมเดลแชตบน D:), ดัชนี/แคช OCR ของ kb ทุกโปรเจกต์
    r"c:[\\/]+llm[\\/]+tools\b|d:[\\/]+llm[\\/]+models(-embed)?\b|"
    r"llm[\\/]+projects[\\/]+data[\\/]+[^\\/\s\"']+[\\/]+kb\b|"
    # [voice] batch 2b: โค้ด/โมเดลของบริการถอดเสียง
    r"c:[\\/]+llm[\\/]+stt\b|"
    # ไม่ใส่ .pth ตรงนี้ เพราะ checkpoint ของ PyTorch ก็ชื่อ .pth (งาน ML ของผู้ใช้ใช้บ่อย)
    # .pth ที่อันตรายคือที่อยู่ใน site-packages ซึ่งอยู่ในเขตห้ามเขียนอยู่แล้ว
    r"sitecustomize|usercustomize|currentversion[\\/]+run"
    r")")


# ===== [skills] ด่านข้อความเสริม: รูปแฝงของ C:\LLM\... (เจ้าของบล็อก: skills — finding ของตัวตรวจ batch 2a) =====
# ทำไม: regex สองตัวข้างบนเป็นด่านเดียวที่ "ปฏิเสธถาวร" คำสั่ง/โค้ด python ที่แตะเขตห้ามเขียน แม้ผู้ใช้กดอนุญาต
# (โค้ด python ไม่มีการตรวจ path ทีละโทเคน) แต่เทียบข้อความตรงตัว — ตัวตรวจเขียน C:\LLM\skills ได้ผ่าน
# \\127.0.0.1\c$\LLM\... (admin share เปิดอยู่จริงในเครื่องนี้), %SystemDrive%\LLM\..., "cd /d C:\LLM" แล้วใช้ path สัมพัทธ์,
# และ Path('C:/LLM') / 'skills' — บล็อกนี้สร้าง "มุมมอง" ของข้อความที่แปลงรูปแฝงกลับเป็น c:\llm\... แล้วเทียบด้วย
# regex ชุดเดิม (ของที่เจ้าของอื่นเพิ่มใน _PROTECTED_TEXT_RE ได้ผลในมุมมองเหล่านี้ด้วยอัตโนมัติ) + รูป 8.3/สัมพัทธ์
# ยังเป็น best-effort (ข้อความประกอบ path ได้ไม่จำกัดวิธี) ด่านหลักคือการยืนยันที่ผู้ใช้เห็นโค้ด/คำสั่งเต็ม
# ข้อความที่แปลงแล้วใช้เทียบเท่านั้น ไม่ถูกบันทึกหรือส่งออกไปไหน
_TXT_ENV_DIRS = {  # ตัวแปรที่เป็น "โฟลเดอร์เดียว" ใช้ไต่ .. ขึ้นไปหา C:\LLM ได้ (ไม่ขยาย PATH — มีหลายโฟลเดอร์ ทำให้เทียบผิด)
    "SYSTEMDRIVE": "C:", "HOMEDRIVE": "C:", "SYSTEMROOT": "C:\\Windows", "WINDIR": "C:\\Windows",
    "USERPROFILE": "", "HOMEPATH": "", "PUBLIC": "", "PROGRAMDATA": "", "ALLUSERSPROFILE": "", "APPDATA": "",
    "LOCALAPPDATA": "", "TEMP": "", "TMP": "", "PROGRAMFILES": "", "PROGRAMFILES(X86)": "", "PROGRAMW6432": "",
    "COMMONPROGRAMFILES": "", "ONEDRIVE": ""}
_TXT_PS_ENV_RE = re.compile(r"(?i)\$\{env:([a-z_][\w()]*)\}|\$env:([a-z_]\w*)")
_TXT_PY_ENV_RE = re.compile(r"(?i)os\s*\.\s*(?:environ\s*\[|environ\s*\.\s*get\s*\(|getenv\s*\()\s*[rbu]?"
                            r"([\"'])([a-z_][\w()]*)\1[^\])\n]{0,80}[\])]")
_TXT_CMD_ENV_RE = re.compile(r"(?i)%([a-z_][\w()]*)(?::~(-?\d+)(?:,(-?\d+))?)?%")
# \\host\c$\  //host/c$/  \\?\UNC\host\c$\  -> c:
_TXT_UNC_RE = re.compile(r"(?i)[\\/]{2}(?:[?.][\\/]+(?:unc[\\/]+)?)?[^\\/\s\"'`]+[\\/]+([a-z])\$(?=[\\/\s\"'`]|$)")
# \LLM\x (ไดรฟ์ปัจจุบัน = C:) -> c:\LLM\x · ต้นของกลุ่ม / \ ต้องไม่ต่อจากชื่ออื่น (D:\\LLM ใน python ไม่ใช่ C:)
_TXT_ROOTLESS_RE = re.compile(r"(?i)(?<![\w.~$:\\/-])([\\/]+)(?=llm[\\/])")
_TXT_DRIVEREL_RE = re.compile(r"(?i)(?<!\w)c:(?=llm[\\/])")                 # C:LLM\x -> c:\LLM\x
# Win32 ตัดจุดท้ายชื่อ: LLM.\ = LLM\ — ต้องต่อจากตัวอักษรของชื่อ ไม่งั้น '../ (ขึ้นโฟลเดอร์แม่) จะหายไปด้วย
_TXT_TRAIL_DOTS_RE = re.compile(r"(?<=[^\\/\s.\"'`=(,<>|&;:+*?])\.+(?=[\\/])")
_TXT_DOT_SEG_RE = re.compile(r"[\\/]\.(?=[\\/])")                            # \.\ -> \
_TXT_DOTDOT_RE = re.compile(r"[\\/]+(?!\.\.?(?:[\\/\s\"'`]|$))[^\\/\s\"'`<>|*?]+[\\/]+\.\.(?=[\\/\s\"'`]|$)")
_TXT_STRIP_RE = re.compile(r"[\"'^`]")        # cmd ตัด ^ และ "..." กลางคำ (C:\LL^M, C:\"LLM"), PS ใช้ ` เป็น escape
_TXT_TRAIL_SP_RE = re.compile(r"(?<=[^\\/\s]) +(?=[\\/])")                  # "C:\LLM \skills" (Win32 ตัดช่องว่างท้ายชื่อ)
_TXT_PYPREFIX_RE = re.compile(r"(?<!\w)[rRbBuUfF]{1,2}(?=[\"'])")
_TXT_LOOSE_RE = re.compile(r"[\s\"'`+,()\[\]/\\]+")
_TXT_SHORT_RE = re.compile(r"(?i)c:[\\/]+llm[\\/]+(?:projects[\\/]+)?[^\\/\s\"'`]*~\d")   # 8.3: C:\LLM\MCP-LO~1
_TXT_CLIMB_RE = re.compile(r"(?i)(?:\.\.[\\/]+){3,}(?:skills|secrets|mcp-local|mcp-websearch|llama\.cpp|browser-profile)\b")
_TXT_VAR_RE = re.compile(r"%[\w()]+%|\$\{[^}\s]{1,64}\}|\$\w+(?::\w+)?")
# ราก C:\LLM (หรือ C:\LLM\projects) ที่ "จบตรงนั้น" = กำลัง cd เข้าไป/เก็บไว้ต่อ path — แล้วมีชื่อที่ห้ามเขียนแบบสัมพัทธ์
_TXT_BASE_END_RE = re.compile(r"(?i)c:[\\/]*llm([\\/]+projects)?[\\/]*(?=[\s\"'`),;&|+]|$)")
_TXT_REL_PRE = r"(?i)(?:^|(?<=[\s\"'`=(,>|&;:+]))(?:\.[\\/]+)?[\\/]*"
# ชื่อโฟลเดอร์เปล่าๆ (skills, tests) ต้องตามด้วยตัวคั่น path/สตริง/คำสั่ง — "C:\LLM models are fast" ในข้อความธรรมดาไม่นับ
# ชื่อไฟล์ที่มีนามสกุล/ชื่อ 8.3 เจาะจงพอ ตามด้วยอาร์กิวเมนต์อื่นได้ (Set-Content start-qwen38.ps1 x)
_TXT_REL_END = r"(?=\s*(?:[\\/\"'`),;&|<>]|$))"
_TXT_REL_END_FILE = r"(?=[\\/\s\"'`),;&|<>]|$)"
_TXT_NAME = r"[^\\/\s\"'`=(,<>|&;:+*?]+"
_TXT_FILE_ALTS = _TXT_NAME + r"~\d[^\\/\s\"'`]*|" + _TXT_NAME + r"\.(?:ps1|psm1|cmd|bat|ini|py|json|vbs)"
_TXT_REL_ROOT_RE = re.compile(
    _TXT_REL_PRE + r"(?:(?:skills|secrets|mcp-local|mcp-websearch|tests|tools|models|browser-profile|__pycache__|"
    r"llama\.cpp[^\\/\s\"'`]*)" + _TXT_REL_END + r"|(?:" + _TXT_FILE_ALTS + r"|projects[\\/]+(?:static|tools|backup|"
    r"__pycache__|hub[^\\/\s\"'`]*\.py|" + _TXT_NAME + r"\.(?:json|py)))" + _TXT_REL_END_FILE + r")")
_TXT_REL_PROJ_RE = re.compile(
    _TXT_REL_PRE + r"(?:(?:static|tools|backup|__pycache__)" + _TXT_REL_END + r"|(?:" + _TXT_NAME + r"~\d[^\\/\s\"'`]*|"
    + _TXT_NAME + r"\.(?:json|py))" + _TXT_REL_END_FILE + r")")


def _txt_env(name: str, lo=None, n=None):
    key = name.upper()
    if key not in _TXT_ENV_DIRS:
        return None
    val = os.environ.get(key) or _TXT_ENV_DIRS[key]
    if not val or ";" in val:
        return None
    if lo is not None:                                  # %VAR:~start[,len]% ของ cmd (เช่น %SystemRoot:~0,2% = C:)
        a = int(lo)
        a = max(0, len(val) + a) if a < 0 else a
        if n is None:
            val = val[a:]
        else:
            b = int(n)
            val = val[a:a + b] if b >= 0 else val[a:len(val) + b]
    return val


def _txt_norm(t: str) -> str:
    t = _TXT_PS_ENV_RE.sub(lambda m: "%" + (m.group(1) or m.group(2)) + "%", t)
    t = _TXT_PY_ENV_RE.sub(lambda m: _txt_env(m.group(2)) or m.group(0), t)
    t = _TXT_CMD_ENV_RE.sub(lambda m: _txt_env(m.group(1), m.group(2), m.group(3)) or m.group(0), t)
    t = _TXT_UNC_RE.sub(lambda m: m.group(1) + ":", t)
    t = _TXT_ROOTLESS_RE.sub(lambda m: "c:" + m.group(1), t)
    t = _TXT_DRIVEREL_RE.sub("c:\\\\", t)
    t = _TXT_TRAIL_DOTS_RE.sub("", t)
    t = _TXT_DOT_SEG_RE.sub("", t)
    for _ in range(16):                                  # C:\LLM\projects\..\skills, %USERPROFILE%\..\..\LLM
        new = _TXT_DOTDOT_RE.sub("", t)
        if new == t:
            break
        t = new
    return t


def _txt_extra_violation(text: str, readonly: bool) -> str | None:
    n = _txt_norm(text)
    s = _txt_norm(_TXT_TRAIL_SP_RE.sub("", _TXT_STRIP_RE.sub("", text)))
    if _SECRET_TEXT_RE.search(n) or _SECRET_TEXT_RE.search(s):
        return "secret_path"
    if readonly:
        return None
    for v in (n, s):
        if _PROTECTED_TEXT_RE.search(v) or _TXT_SHORT_RE.search(v) or _TXT_CLIMB_RE.search(v):
            return "protected_path"
    # มุมมองหลวม: ตัวคั่นของการต่อสตริง/อาร์กิวเมนต์ ('C:/', 'LLM', 'skills' / Path(..) / '..') กลายเป็น \ —
    # นับเฉพาะรูปที่ขึ้นต้นด้วยไดรฟ์ ไม่งั้นรายการธรรมดาอย่าง ["llm", "models"] ในโค้ดวิเคราะห์ข้อมูลจะโดนปฏิเสธ
    loose = _TXT_LOOSE_RE.sub(lambda m: "\\" if m.group().strip() else m.group(), _TXT_PYPREFIX_RE.sub("", n))
    if _TXT_SHORT_RE.search(loose) or any(re.match(r"[a-z]:", m.group(0), re.I) or
                                          re.search(r"(?i)[a-z]:\\$", loose[max(0, m.start() - 3):m.start()])
                                          for m in _PROTECTED_TEXT_RE.finditer(loose)):
        return "protected_path"
    nv = _TXT_VAR_RE.sub("", n)                          # %R%\skills, $R\skills หลัง set R=C:\LLM
    for m in _TXT_BASE_END_RE.finditer(nv):
        if (_TXT_REL_PROJ_RE if m.group(1) else _TXT_REL_ROOT_RE).search(nv):
            return "protected_path"
    return None
# ===== [/skills] =====


def command_text_violation(command: str, readonly: bool) -> str | None:
    """คืนเหตุผลถ้าตัวข้อความของคำสั่งแตะของต้องห้าม (ใช้ทั้ง exec_shell_command และ task_start)

    * ชื่อโฟลเดอร์ secrets / ไฟล์ token: ปฏิเสธทุกกรณี แม้เป็นคำสั่งอ่านอย่างเดียว
    * โค้ด/ค่าตั้งของสแตกและจุด persistence: ปฏิเสธเฉพาะคำสั่งที่ไม่ใช่อ่านอย่างเดียว
      (คำสั่งแบบนั้นแก้ไฟล์ได้ด้วยวิธีที่ด่านทีละโทเคนมองไม่เห็น)
    """
    text = str(command or "")
    if _SECRET_TEXT_RE.search(text):
        return "secret_path"
    if not readonly and _PROTECTED_TEXT_RE.search(text):
        return "protected_path"
    return _txt_extra_violation(text, readonly)  # [skills] รูปแฝง: UNC c$, %SystemDrive%, cd แล้วสัมพัทธ์, Path(..)/..


# git อ่านเนื้อไฟล์จาก object store ด้วยรูป <rev>:<path> (เช่น git show HEAD:.env)
# ซึ่ง path ในนั้นเป็น path "ในรีโป" ไม่ผ่านด่านตรวจ path ปกติ จึงพิมพ์ไฟล์ที่ถูกบล็อก
# (.env / *.pem / *_key.txt / credentials) ที่ commit ไว้ออกมาได้โดยไม่มีการตรวจ
_GIT_CONTENT_SUBS = frozenset((
    "show", "cat-file", "log", "diff", "whatchanged", "rev-list", "ls-tree", "grep", "blame",
    "difftool", "range-diff"))


def _split_revpath(arg: str) -> str | None:
    """แยกส่วน path ในรีโปออกจากรูป <rev>:<path> ของ git คืน None ถ้าไม่ใช่รูปนี้

    รองรับทุกรูปที่ git ใช้อ่าน blob:  HEAD:x  abc123:x  :x (index)  :0:x ถึง :3:x (stage)
    HEAD@{10:00}:x (':' ใน {} ไม่ใช่ตัวคั่น)  ส่วน :/ข้อความ คือค้นข้อความ commit ไม่ใช่ path
    รอบก่อนตัดที่ ':' ตัวแรกเสมอ ":0:credentials.json" จึงกลายเป็น path "0:credentials.json"
    ซึ่งไม่ตรง *\\credentials* แล้ว git ก็พิมพ์ไฟล์ต้องห้ามออกมา (พิสูจน์แล้วใน repo ทดสอบ)
    """
    if arg.startswith(":"):
        rest = arg[1:]
        if rest.startswith("/"):
            return None
        if len(rest) >= 2 and rest[0] in "0123" and rest[1] == ":":
            rest = rest[2:]
        return rest
    depth = 0
    for i, ch in enumerate(arg):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == ":" and depth == 0:
            return arg[i + 1:]
    return None


def git_revpath_violation(argv: list[str]) -> str | None:
    """คืน argument ที่ชี้ไฟล์ต้องห้ามในรูป <rev>:<path> (หรือ -L...:<file>) ของ git หรือ None ถ้าไม่มี"""
    if not argv or os.path.basename(argv[0]).lower().split(".")[0] != "git":
        return None
    cfg = _load_config()
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        if argv[i] == "-C" and i + 1 < len(argv):
            i += 2
            continue
        i += 1
    if i >= len(argv):
        return None
    if argv[i] not in _GIT_CONTENT_SUBS:
        return None
    rest_args = argv[i + 1:]
    for n, a in enumerate(rest_args):
        repo_path = None
        if a.startswith("-L"):
            # log -L<ช่วง>:<ไฟล์> / -L :<ฟังก์ชัน>:<ไฟล์> / -L <ช่วง>:<ไฟล์> พิมพ์เนื้อไฟล์ช่วงนั้นออกมา
            spec = a[2:] or (rest_args[n + 1] if n + 1 < len(rest_args) else "")
            if ":" in spec:
                repo_path = spec.rsplit(":", 1)[1]
        elif a.startswith("-") or ":" not in a:
            continue
        else:
            drive, _rest = os.path.splitdrive(a)
            if drive:
                continue                      # C:\... เป็น path จริง ตรวจที่ด่าน path ปกติ
            repo_path = _split_revpath(a)
        repo_path = (repo_path or "").strip().replace("/", "\\")
        if not repo_path:
            continue
        # ส่วนนี้คือ path ในรีโป — เทียบกับ blocked_globs/suffixes ผ่าน path สมมติ
        synthetic = os.path.normpath("C:\\__gitrepo__\\" + repo_path.lstrip("\\"))
        if _blocked(synthetic.lower(), cfg):
            return a
    return None


def check_workdir_for_exec(workdir: str, readonly: bool) -> None:
    """คำสั่งที่เปลี่ยนเครื่องห้ามรันโดยมีโฟลเดอร์ทำงานอยู่ในเขตห้ามเขียน

    เช่น cwd=C:\\LLM\\mcp-local แล้วสั่ง `python -c "...open('guard.py','w')..."`
    ในข้อความไม่มี path เต็มให้จับเลย แต่ไฟล์ที่ถูกเขียนคือโค้ดของด่านเอง
    """
    if readonly:
        return
    # C:\LLM กับ C:\LLM\projects เองไม่ได้อยู่ในเขตห้ามเขียน (โฟลเดอร์ย่อยบางตัวเขียนได้)
    # แต่ไฟล์ตรงใต้สองโฟลเดอร์นี้คือ launcher/hub ถ้าเป็น cwd แล้ว `del hub.py` ในโค้ด -c จะมองไม่เห็น
    parents = {os.path.normcase(r"C:\LLM"), os.path.normcase(r"C:\LLM\projects")}
    if os.path.normcase(_norm(workdir)).rstrip("\\") in parents or is_write_protected(workdir):
        raise Denied("โฟลเดอร์ทำงานนี้อยู่ในเขตห้ามเขียน จึงรันคำสั่งที่เปลี่ยนแปลงเครื่องในนี้ไม่ได้ "
                     "ถ้าจำเป็นจริงให้ผู้ใช้รันเองใน terminal")


# ------------------------------------------------- two-step confirmation
# ช่องทางยืนยัน (ช่องโหว่ "สองขั้นตอนผ่านโมเดล" ที่ audit พบ — ระดับ major)
# ------------------------------------------------------------------------
# เดิมขั้นที่สองคือ "เรียกเครื่องมือเดิมซ้ำพร้อม confirm_token" ซึ่ง token อยู่ในผลของเครื่องมือที่โมเดลอ่าน
# โมเดลที่โดนหลอกด้วยเนื้อหาเว็บ/ไฟล์ (prompt injection) จึงยืนยันเองได้ในสองการเรียก ด่านเดียวที่เหลือ
# คือกล่อง "อนุญาต" ของ WebUI ซึ่งจะไม่ถามเลยถ้าผู้ใช้เคยกด "อนุญาตเสมอ" ให้ local_do ไว้
# ตอนนี้ token ใช้ได้ "เฉพาะผ่านเครื่องมือ local_confirm" (server.py) ที่เล่นซ้ำการกระทำที่บันทึกไว้เท่านั้น
#   * WebUI เก็บสิทธิ์ "อนุญาตเสมอ" เป็นรายชื่อเครื่องมือ ณ ตอนกด (ไม่ใช่ wildcard — ตรวจจาก bundle b10984)
#     local_confirm เป็นเครื่องมือใหม่ สิทธิ์ที่ผู้ใช้เคยให้ไว้ทั้งหมดจึงไม่ครอบมัน กล่องอนุญาตกลับมาถามคนเสมอ
#   * การเล่นซ้ำใช้เครื่องมือ + อาร์กิวเมนต์ "ที่บันทึกไว้ตอนขอ" ไม่ใช่ที่โมเดลส่งมาใหม่ จึงสลับของไม่ได้
#   * ส่ง confirm_token ให้เครื่องมือเดิมตรงๆ = consume_confirm ปฏิเสธ (ไม่เผา token ทิ้ง)
CONFIRM_TOOL = "local_confirm"


@contextmanager
def tool_call(surface: str, name: str, args: dict):
    """server.py ครอบทุก tools/call: จำว่าการเรียกนี้คือเครื่องมืออะไร ด้วยอาร์กิวเมนต์อะไร
    need_confirm จะเก็บสำเนาไว้กับ token เพื่อให้ local_confirm เล่นซ้ำได้ตรงตัว"""
    prev = getattr(_ctx, "call", None)
    _ctx.call = {"surface": str(surface), "name": str(name),
                 "args": copy.deepcopy({k: v for k, v in (args or {}).items()
                                        if k not in ("confirm_token",)})}
    try:
        yield
    finally:
        _ctx.call = prev


def review_provided(review) -> bool:
    """local_confirm ส่ง review มาจริงหรือไม่ (รอบ review-fetch S2: review ไม่บังคับแล้ว)

    ไม่มีคีย์ / null / ข้อความว่างหรือมีแต่ช่องว่าง = "ไม่ได้ส่ง" — ไม่มีเนื้อหาให้เทียบ และคนเห็น review ของ
    เซิร์ฟเวอร์ในกล่องอนุญาตอยู่แล้ว (โมเดลเล็กบางทีเติมคีย์ว่างมาเอง ไม่ควรทำให้การกดอนุญาตของคนสูญเปล่า)
    ค่าชนิดอื่นทุกแบบ (ตัวเลข/ลิสต์/อ็อบเจกต์) = "ส่งมา" แล้วต้องตรง ซึ่งไม่มีทางตรง -> ปฏิเสธ"""
    if review is None:
        return False
    if isinstance(review, str):
        return bool(review.strip())
    return True


@contextmanager
def confirming(token: str, review):
    """เปิดช่องให้ consume_confirm รับ token นี้ — server.py ใช้ตอนเล่นซ้ำจาก local_confirm เท่านั้น

    รอบ review (R2): เดิมบังคับส่ง "ข้อความตรวจทาน" มาด้วยเสมอ
    รอบ review-fetch (S2): review ไม่บังคับ — ด่านคนย้ายไปอยู่ที่กล่องอนุญาตซึ่งดึง review จากเซิร์ฟเวอร์เอง (S1/S3)
      * ไม่ได้ส่ง (review_provided เป็นเท็จ) = เปิดช่องได้ ถ้า token ยังค้างอยู่จริง ยังไม่หมดอายุ และ review ของมัน
        "ถูกกล่องอนุญาตดึงไปแสดงแล้ว" (viewed — รอบ FIXER ข้างล่าง)
      * ส่งมา = ต้องตรงกับที่เก็บไว้กับ token (review_matches) ไม่ตรง = ไม่เปิดช่อง consume_confirm จึงปฏิเสธเอง
    รอบ FIXER ของ S1/S2 (review อิสระ): ถ้า token อย่างเดียวพอเสมอ ด่านคนมีอยู่แค่ในเบราว์เซอร์ — การ์ดที่โหลดไม่สำเร็จ/
    ยังโหลดอยู่ยังกด "อนุญาต" ได้ (แค่จาง) และแท็บที่เปิดไว้ก่อนอัปเดต enhance ไม่ดึง review เลย (การ์ดเก่าแสดง "ไม่มี
    review ให้กดปฏิเสธ" แต่เซิร์ฟเวอร์รันถ้าคนกดอนุญาต) ตอนนี้ token อย่างเดียวต้องมี viewed ที่เซิร์ฟเวอร์จดเองตอน GET
    /review สำเร็จ (Bearer + Origin ของหน้าเรา) — โมเดลไปถึง /review ไม่ได้ จึงทำได้แค่ลองใหม่ ส่วน review ที่ส่งมาและตรง
    ยังผ่านได้เหมือนก่อน S2 (การ์ดรุ่นเก่าแสดงข้อความนั้นให้คนเห็น)
    server ตรวจก่อนแล้วเพื่อให้ข้อความตอบกลับชัด ตรงนี้คือด่านซ้ำที่ผูกกฎไว้ที่ guard ที่เดียว
    (โค้ดใหม่ในอนาคตที่ลืมตรวจ review ก็ยังลงมือด้วย review ที่ไม่ตรง หรือ token ที่ยังไม่มีใครเห็นไม่ได้)
    การผูก action/digest/โปรเจกต์ และใช้ได้ครั้งเดียว ยังบังคับที่ consume_confirm เหมือนเดิมทุกกรณี
    yield True/False ให้ผู้เรียกรู้ว่าเปิดช่องจริงหรือไม่
    """
    tok = str(token or "").strip()
    # เทียบกับ review ของ token นี้โดยไม่ดูขอบเขตโปรเจกต์ตรงนี้ — ขอบเขตถูกบังคับที่ consume_confirm อยู่แล้ว
    # (และ server เรียกจากใน project_scope เสมอ) ตรงนี้ตัดสินแค่ "token ค้างอยู่จริง และถ้าส่ง review มาต้องตรง
    # ไม่ส่งมาต้องเคยถูกแสดงในกล่องอนุญาต"
    with _lock:
        item = _pending.get(tok) if tok else None
        live = bool(item) and item["exp"] >= time.time()
        stored = item.get("review") if live else None
        viewed = bool(item.get("viewed")) if live else False
    if not tok or not isinstance(stored, str) or not stored:
        ok = False
    elif review_provided(review):
        ok = review_matches(stored, review)
    else:
        ok = viewed
    prev = getattr(_ctx, "confirming", None)
    _ctx.confirming = tok if ok else None
    try:
        yield ok
    finally:
        _ctx.confirming = prev


# ------------------------------------------------ ข้อความตรวจทาน (review) — รอบ R1-R3
# ปัญหาที่ security review อิสระยืนยันแล้ว (2026-09-30):
#  (1) local_confirm รับแค่ token 8 ตัวอักษร กล่อง "อนุญาต" ของ WebUI (ซึ่งโชว์อาร์กิวเมนต์ของการเรียก)
#      จึงโชว์แค่ token ไม่เคยโชว์โค้ด/คำสั่ง โมเดลที่โดนเนื้อหาฉีดหลอกโชว์โค้ด A ในแชต แล้วยืนยัน token
#      ของโค้ด B ได้ — คนกดอนุญาตโดยไม่เคยเห็นของที่จะรันจริง
#  (2) ตัวอย่างโค้ดตัดที่ 80 บรรทัด/5,000 ตัวอักษร บรรทัดที่เติมช่องว่างยาวๆ ซ่อนโค้ดไว้นอกจอได้
#      และอักขระ bidi/zero-width ผ่านไปดิบๆ (Trojan Source: ตาเห็นอย่างหนึ่ง เครื่องรันอีกอย่าง)
#  (3) token ค้างได้ถึง 200 ตัว
# ทางแก้: ทุก token เก็บ "ข้อความตรวจทาน" ที่เซิร์ฟเวอร์สร้างเองจากอาร์กิวเมนต์ที่ normalize แล้ว (ไม่ใช่ข้อความ
# ของโมเดล) บอกครบว่าจะเกิดอะไร local_confirm ต้องส่งข้อความนี้กลับมาตรงตัว กล่องอนุญาตจึงโชว์ของจริงตอนคนกด
# อักขระที่มองไม่เห็น/กำกวมถูกแปลงเป็น «U+XXXX» ที่ตาเห็น บรรทัดยาวถูกตัดพร้อม ↩ ช่องว่างยาวถูกย่อ
# รอบ review-fetch (S1/S2): กล่องอนุญาตดึงข้อความนี้จากเซิร์ฟเวอร์เอง (pending_view) ไม่ต้องให้โมเดลส่งกลับแล้ว
# (ส่งมาได้ แต่ต้องตรง) — กฎการแสดงผลข้างล่างจึงสำคัญยิ่งขึ้น: นี่คือสิ่งเดียวที่คนเห็นก่อนกด
REVIEW_WRAP = 200               # บรรทัดยาวกว่านี้ถูกตัดขึ้นบรรทัดใหม่ (กันโค้ดหลบไปอยู่นอกจอทางขวา)
REVIEW_SPACE_RUN = 32           # ช่องว่างติดกันตั้งแต่เท่านี้ย่อเป็น «N spaces» (กันการเติมช่องว่างดันโค้ดออกนอกจอ)
REVIEW_MAX_MARKS = 3            # สระ/วรรณยุกต์ซ้อนบนอักษรเดียวได้เท่านี้ (ไทยซ้อนจริงไม่เกิน 2) เกิน = Zalgo บังบรรทัดอื่น
# ก้อนโค้ด/เนื้อหาที่คน "อ่านทันจริง" ในกล่องอนุญาต — python เกินนี้ถูกปฏิเสธ, เนื้อไฟล์เกินนี้แสดง diff แบบตัด
REVIEW_BLOCK_MAX_LINES = 400
REVIEW_BLOCK_MAX_CHARS = 20_000
# เพดานของ review ทั้งก้อน (หัว + เนื้อหา) — เกินแล้วไม่ออก token เลย (ReviewTooLarge) กันกล่องอนุญาต/บริบทโมเดลบวม
# รอบ FIXER: เดิม 48,000 ตัวอักษร แต่โมเดลต้องได้ review ในผลเครื่องมือ แสดงในแชต แล้วคัดลอกกลับมาทั้งก้อนอีกรอบ
# (สามเท่าของขนาด) บริบท 8K-32K โทเคนของโมเดลในเครื่องนี้รับ 48K ไม่ไหว ก้อนเนื้อหาที่ใหญ่ที่สุดที่เครื่องมือสร้าง
# คือ 20,000 (REVIEW_BLOCK_MAX_CHARS) + เลขบรรทัด/เครื่องหมายตัดบรรทัด/หัวข้อ จึงเหลือเพดาน 26,000 ที่พอดีกับของจริง
# (คำสั่ง run ยาว 26K-48K ที่เคยผ่านไม่มีใครอ่านทันอยู่แล้ว)
REVIEW_MAX_LINES = 700
REVIEW_MAX_CHARS = 26_000
# review ที่ส่งกลับมาต่างจากของจริงได้แค่ "ช่องว่างที่ตาไม่เห็นความหมาย" และต้องไม่มากจนดันเนื้อหาออกจากกล่องอนุญาต
# (กล่องของ enhance ตัดบรรทัดแบบ break-spaces: ช่องว่างท้ายบรรทัด 10,000 ตัว = พื้นที่ว่างหลายร้อยบรรทัด
#  โค้ดจริงถูกดันลงไปใต้ขอบกล่องจนคนกดอนุญาตโดยไม่เห็น) จึงยอมแค่จำนวนน้อยที่เกิดจากการคัดลอกจริงๆ
REVIEW_PAD_MAX = 4              # ช่องว่าง/แท็บเกินต่อบรรทัด (ท้ายบรรทัด และหน้าบรรทัดแรกของทั้งก้อน)
REVIEW_BLANK_MAX = 3            # บรรทัดว่างเกินที่หัว/ท้ายของทั้งก้อน
REVIEW_WRAP_MARK = "↩"          # ท้ายบรรทัดที่ถูกตัด
REVIEW_CONT_MARK = "↪"          # หัวบรรทัดต่อ — สองทางกันการปลอม "บรรทัดใหม่" ด้วยการจัดตำแหน่งให้พอดีจุดตัด
# อักขระที่เราใช้เป็นเครื่องหมายเอง ถ้ามาจากเนื้อหาต้องแสดงเป็นรหัส ไม่งั้นปลอมเครื่องหมายได้
# (เช่น ใส่ ↩ ท้ายคอมเมนต์ให้บรรทัดถัดไปที่เป็นโค้ดจริงดูเหมือน "ส่วนต่อของคอมเมนต์")
_REVIEW_MARKS = frozenset("«»" + REVIEW_WRAP_MARK + REVIEW_CONT_MARK)
# อักษรที่ "มองไม่เห็น" แต่ไม่ใช่ Default_Ignorable และไม่อยู่ในหมวด Cf/Zs: อักษรเบรลล์ว่าง
_REVIEW_EXTRA_HIDDEN = frozenset((0x2800,))
# รอบ FIXER: เดิมเลือกอักขระล่องหนเองทีละตัว แล้วตกหล่น U+180B-180D/180F (ตัวเลือกรูปแบบอิสระของมองโกเลีย —
# หมวด Mn กว้างศูนย์ และเป็นส่วนของชื่อตัวแปร Python ได้: 'a'+U+180B เป็น identifier ที่หน้าตาเหมือน 'a' ทุกประการ)
# ตอนนี้ใช้คุณสมบัติ Default_Ignorable_Code_Point ของ Unicode ทั้งชุด (DerivedCoreProperties.txt) ซึ่งนิยามว่า
# "ไม่ต้องแสดงผลเมื่อไม่รู้จัก" = ช่องที่ตาไม่เห็นตามมาตรฐานเลย คัดลอกช่วงจากไฟล์มาตรฐาน (Unicode 15.1/16.0 ตรงกัน
# 4,174 ตัว เทสต์ตรวจเทียบกับโมดูล regex \p{Default_Ignorable_Code_Point} ของ anaconda ถ้ามี)
# ในนี้มีตัวเติมฮันกึล (ชื่อตัวแปรล่องหน), CGJ, สระแฝงของเขมร, bidi, zero-width, BOM, tag, variation selector
_DEFAULT_IGNORABLE = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
    (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164),
    (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF),
)


def is_default_ignorable(o: int) -> bool:
    for lo, hi in _DEFAULT_IGNORABLE:
        if o < lo:
            return False
        if o <= hi:
            return True
    return False


# ---- อักษรหน้าตาเหมือน (homoglyph) — รอบ FIXER
# Cyrillic/Greek ฯลฯ ที่หน้าตาเหมือนอักษรละตินทุกประการ: "prіnt" (і = U+0456) ในโค้ด หรือโดเมน "exаmple.com"
# (а = U+0430) ดูเหมือนของจริงในกล่องอนุญาต แต่เป็นชื่อ/โดเมนคนละตัว ไม่ได้ escape อักษรพวกนี้ทุกตัว (ข้อความ
# ภาษารัสเซีย/กรีกจริงต้องอ่านได้ และไม่แตะภาษาไทยเลย) แต่แสดงเป็น «U+XXXX» เฉพาะเมื่อ
#   (1) เป็นอักษรที่ "เหมือนละตินทุกประการ" และอยู่ใน "คำ" (ลำดับ \w) เดียวกับอักษร ASCII — คำจริงแทบไม่เคยผสม
#       ละติน+ซีริลลิกในคำเดียว (อักษรที่หน้าตาต่างชัดเช่น Δ μ σ ใน "Δt" "μs" ไม่ถูกแตะ คนเห็นอยู่แล้วว่าไม่ใช่ละติน)
#   (2) ทั้งคำประกอบด้วยอักษรหน้าตาเหมือนละตินล้วน เช่นตัวแปร "а" หรือ "ехес" ที่เป็นซีริลลิกทั้งคำ
#   (3) อักษร/ตัวเลขเต็มความกว้าง, อักษรคณิตศาสตร์, เครื่องหมายเคลวิน — NFKC แปลงเป็น ASCII ซึ่ง Python ทำกับ
#       ชื่อตัวแปรเสมอ ("ｅｘｅｃ" คือ exec) ตาเห็นอย่างหนึ่ง ตัวแปลภาษาเห็นอีกอย่าง
# อักษรที่ "เหมือนละตินทุกประการ" ในฟอนต์ทั่วไป (ยกจาก confusables ของ Unicode เฉพาะตัวที่แยกไม่ออกด้วยตา)
# + Cherokee และ Lisu ทั้งชุด (ตัวใหญ่ของสองระบบนี้หน้าตาเหมือนละตินแทบทุกตัว และไม่มีใครใช้ในงานของเครื่องนี้)
_LATIN_LOOKALIKE = frozenset(
    [0x0430, 0x0441, 0x0435, 0x043E, 0x0440, 0x0445, 0x0443, 0x0456, 0x0458, 0x0455, 0x04BB,
     0x0501, 0x051B, 0x051D, 0x04CF, 0x04AF,                              # Cyrillic ตัวเล็ก
     0x0410, 0x0412, 0x0415, 0x041A, 0x041C, 0x041D, 0x041E, 0x0420, 0x0421, 0x0422, 0x0425,
     0x0406, 0x0408, 0x0405, 0x04AE, 0x051A, 0x051C, 0x04C0,              # Cyrillic ตัวใหญ่
     0x03BF, 0x03BD, 0x03F2, 0x03F3,                                      # Greek ตัวเล็ก ο ν ϲ ϳ
     0x0391, 0x0392, 0x0395, 0x0396, 0x0397, 0x0399, 0x039A, 0x039C, 0x039D, 0x039F, 0x03A1,
     0x03A4, 0x03A5, 0x03A7, 0x03F9,                                      # Greek ตัวใหญ่
     0x0585, 0x057D, 0x0570, 0x0578, 0x0566]                              # Armenian օ ս հ ո զ
    + list(range(0x13A0, 0x1400)) + list(range(0xAB70, 0xABC0)) + list(range(0xA4D0, 0xA500)))
_NFKC_ASCII = ((0x212A, 0x212A), (0xFF10, 0xFF19), (0xFF21, 0xFF3A), (0xFF41, 0xFF5A),
               (0x1D400, 0x1D7FF))
_ASCII_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_WORD_RE = re.compile(r"\w+")


def _in_ranges(o: int, ranges) -> bool:
    return any(lo <= o <= hi for lo, hi in ranges)


def _confusable_positions(line: str) -> set:
    """ตำแหน่งในบรรทัดที่ต้องแสดงเป็น «U+XXXX» เพราะหน้าตาเหมือนอักษรละติน/ASCII (กติกา 1-3 ข้างบน)"""
    if line.isascii():
        return set()
    out: set = set()
    for m in _WORD_RE.finditer(line):
        word = m.group()
        if word.isascii():
            continue
        has_ascii = False
        lookalike_only = True
        idx = []
        for j, c in enumerate(word):
            o = ord(c)
            if c in _ASCII_LETTERS:
                has_ascii = True
            elif _in_ranges(o, _NFKC_ASCII):
                out.add(m.start() + j)
            elif o in _LATIN_LOOKALIKE:
                idx.append(m.start() + j)
            elif c.isalpha():
                lookalike_only = False      # คำที่มีอักษรระบบอื่น (เช่นไทย) ไม่ใช่คำปลอมแบบ (2)
        if idx and (has_ascii or lookalike_only):
            out.update(idx)
    return out


class ReviewTooLarge(Denied):
    """การกระทำนี้ยาวเกินกว่าที่คนจะตรวจทานได้ในกล่องอนุญาต — ไม่ออก token"""


def _review_hidden(ch: str) -> bool:
    """True = ต้องแสดงเป็น «U+XXXX» (มองไม่เห็น เปลี่ยนทิศข้อความ ขึ้นบรรทัดแฝง หรือหน้าตาเหมือนช่องว่าง)"""
    o = ord(ch)
    if ch in _REVIEW_MARKS or o in _REVIEW_EXTRA_HIDDEN:
        return True
    if is_default_ignorable(o):
        # รวม variation selector (ช่องลักลอบซ่อนข้อมูลแบบ ASCII smuggling) — ข้อยกเว้นเดียวคือ VS15/VS16
        # ต่อท้ายอีโมจิหนึ่งตัว ซึ่ง _review_units จัดการก่อนมาถึงตรงนี้
        return True
    cat = unicodedata.category(ch)
    if cat == "Zs":
        return ch != " "        # NBSP/ช่องว่างกว้างพิเศษหน้าตาเหมือน space แต่ไม่ใช่
    # Cc = ควบคุม (\r เดี่ยวคือขึ้นบรรทัดใหม่ของ Python), Cf = bidi/zero-width/BOM/tag,
    # Zl/Zp = ตัวขึ้นบรรทัดของ Unicode, Co/Cn/Cs = ไม่มีหน้าตาแน่นอน
    return cat in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")


def _escape(ch: str) -> str:
    return "«U+%04X»" % ord(ch)


def _review_units(line: str, stats: dict) -> list[str]:
    """แตกหนึ่งบรรทัดเป็น "หน่วยที่ตาเห็น" (อักษร+เครื่องหมายกำกับ, รหัส «U+..», «N spaces») ให้ตัดบรรทัดได้โดยไม่ผ่ากลาง"""
    units: list[str] = []
    spaces = 0
    base = False            # หน่วยล่าสุดเป็นอักษรปกติที่รับสระ/วรรณยุกต์ต่อได้
    marks = 0
    lookalike = _confusable_positions(line)

    def flush() -> None:
        if spaces >= REVIEW_SPACE_RUN:
            units.append("«%d spaces»" % spaces)
            stats["runs"] += 1
        else:
            units.extend(" " * spaces)

    for i, ch in enumerate(line):
        if i in lookalike:
            if spaces:
                flush()
                spaces = 0
            # อักษรหน้าตาเหมือนละติน/ASCII (homoglyph) — นับแยกจากอักขระซ่อน มีคำเตือนของตัวเอง
            units.append(_escape(ch))
            stats["confusable"] += 1
            base = False
            continue
        if ch == " ":
            spaces += 1
            continue
        if spaces:
            flush()
            spaces, base = 0, False
        if ch == "\t":
            # แท็บกว้างไม่แน่นอน (ดันโค้ดออกนอกจอได้) และโมเดลมักคัดลอกแท็บเป็นช่องว่าง -> แสดงเป็นคำ
            units.append("«TAB»")
            stats["tabs"] += 1
            base = False
            continue
        o = ord(ch)
        if o in (0xFE0E, 0xFE0F) and base and marks == 0 \
                and unicodedata.category(units[-1][0]) == "So":
            units[-1] += ch     # ตัวเลือกหน้าตาอีโมจิหนึ่งตัวหลังอีโมจิ เป็นของปกติ ไม่ใช่การซ่อน
            marks = REVIEW_MAX_MARKS
            continue
        if _review_hidden(ch):
            units.append(_escape(ch))
            stats["hidden"] += 1
            base = False
            continue
        if unicodedata.category(ch) in ("Mn", "Mc", "Me"):
            if base and marks < REVIEW_MAX_MARKS:
                units[-1] += ch
                marks += 1
            else:
                # เครื่องหมายกำกับที่ไม่มีอักษรฐานหรือซ้อนเกิน (Zalgo) ลอยไปบังอักษร/บรรทัดข้างเคียงได้
                units.append(_escape(ch))
                stats["hidden"] += 1
                base = False
            continue
        units.append(ch)
        base, marks = True, 0
    if spaces:
        flush()
    return units


def _review_wrap(units: list[str]) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    width = 0
    for u in units:
        if cur and width + len(u) > REVIEW_WRAP:
            out.append("".join(cur) + REVIEW_WRAP_MARK)
            cur, width = [REVIEW_CONT_MARK], len(REVIEW_CONT_MARK)
        cur.append(u)
        width += len(u)
    out.append("".join(cur))
    return out


def _review_lines(text) -> tuple[list[str], dict]:
    stats = {"hidden": 0, "tabs": 0, "runs": 0, "wrapped": 0, "confusable": 0}
    out: list[str] = []
    # \r\n = ขึ้นบรรทัดปกติ ส่วน \r เดี่ยวเหลือไว้ให้ถูกแสดงเป็นรหัส (Python นับเป็นบรรทัดใหม่ที่ตาไม่เห็น)
    for line in str(text if text is not None else "").replace("\r\n", "\n").split("\n"):
        segs = _review_wrap(_review_units(line, stats))
        if len(segs) > 1:
            stats["wrapped"] += 1
        out.extend(s.rstrip(" ") for s in segs)
    return out, stats


def render_review(text) -> tuple[str, dict]:
    """ข้อความดิบ -> ข้อความตรวจทานที่ "ตาเห็นครบ" + สถิติ (hidden/confusable/tabs/runs/wrapped/lines/chars)

    อักขระซ่อน/กำกวม -> «U+XXXX», อักษรหน้าตาเหมือนละติน/ASCII (homoglyph) -> «U+XXXX»,
    แท็บ -> «TAB», ช่องว่าง >= 32 ตัว -> «N spaces»,
    บรรทัดยาวเกิน 200 -> ตัดพร้อม ↩ ท้ายบรรทัดและ ↪ หัวบรรทัดต่อ, ช่องว่างท้ายบรรทัดถูกตัด (ตาไม่เห็นอยู่แล้ว)
    ถ้ามีอักขระซ่อน อักษรหน้าตาเหมือน หรือช่องว่างยาว จะมีบรรทัดคำเตือนนำหน้า lines/chars ไม่นับบรรทัดคำเตือน
    """
    lines, stats = _review_lines(text)
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)
    stats["lines"], stats["chars"] = len(lines), sum(len(x) + 1 for x in lines)
    warn = []
    if stats["hidden"]:
        warn.append("⚠ คำเตือน (WARNING): พบอักขระซ่อน/กำกวม %d ตัว แสดงเป็น «U+XXXX» "
                    "(อาจเป็นการซ่อนโค้ดแบบ Trojan Source) — ตรวจให้ดีก่อนอนุญาต" % stats["hidden"])
    if stats["confusable"]:
        warn.append("⚠ คำเตือน (WARNING): พบอักษรหน้าตาเหมือนอักษรละติน/ASCII %d ตัว แสดงเป็น «U+XXXX» "
                    "(เช่น Cyrillic/Greek ปนในคำภาษาอังกฤษ หรืออักษรเต็มความกว้าง) — ชื่อ/โดเมนนี้อาจไม่ใช่ตัวที่ตาเห็น"
                    % stats["confusable"])
    if stats["runs"]:
        warn.append("⚠ คำเตือน (WARNING): ช่องว่างยาวผิดปกติ %d จุด ย่อแสดงเป็น «N spaces» "
                    "(อาจใช้ดันโค้ดออกไปนอกจอ)" % stats["runs"])
    return "\n".join(warn + lines), stats


def review_measure(text) -> tuple[int, int]:
    """(จำนวนบรรทัด, จำนวนตัวอักษร) หลังแสดงอักขระซ่อนและตัดบรรทัดแล้ว — ขนาดที่คนต้องอ่านจริง"""
    lines, _stats = _review_lines(text)
    return len(lines), sum(len(x) + 1 for x in lines)


def review_fit(lines, max_lines: int = REVIEW_BLOCK_MAX_LINES,
               max_chars: int = REVIEW_BLOCK_MAX_CHARS) -> int:
    """แสดงได้กี่บรรทัดแรกของ lines (ดิบ) ก่อนเกินเพดาน นับขนาดหลังแสดงผลแล้ว (บรรทัดยาวถูกตัดเป็นหลายบรรทัด)"""
    used_l = used_c = 0
    for i, ln in enumerate(lines):
        n_l, n_c = review_measure(ln)
        if used_l + n_l > max_lines or used_c + n_c > max_chars:
            return i
        used_l += n_l
        used_c += n_c
    return len(lines)


def review_numbered(text) -> list[str]:
    """เนื้อหาเป็นบรรทัดพร้อมเลขกำกับ "12│ ..." — ข้อความในเนื้อหาจึงปลอมบรรทัดหัว/ท้ายของ review ไม่ได้
    (บรรทัดปลอมจะมีเลขนำหน้าเสมอ) บรรทัดว่างท้ายสุดจากการขึ้นบรรทัดสุดท้ายไม่นับ"""
    lines = str(text if text is not None else "").replace("\r\n", "\n").split("\n")
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()
    width = len(str(len(lines)))
    return ["%*d│ %s" % (width, i + 1, ln) for i, ln in enumerate(lines)]


def review_capped(lines, sha_hex: str, max_lines: int = REVIEW_BLOCK_MAX_LINES,
                  max_chars: int = REVIEW_BLOCK_MAX_CHARS) -> tuple[str, int]:
    """บรรทัดดิบที่ตัดให้พอดีเพดาน + บรรทัดบอกชัดว่าไม่แสดงอีกกี่บรรทัดพร้อม hash ของเนื้อหาเต็ม
    คืน (ข้อความ, จำนวนบรรทัดที่ไม่แสดง)"""
    lines = list(lines)
    k = review_fit(lines, max_lines, max_chars)
    shown = lines[:k]
    omitted = len(lines) - k
    if omitted:
        shown.append("(ไม่แสดงอีก %d บรรทัด — %d more lines not shown — content hash sha256:%s…)"
                     % (omitted, omitted, str(sha_hex or "")[:16]))
    return "\n".join(shown), omitted


# รั้วแบบที่ review_fence พิมพ์เอง: บรรทัดแรก ```review (backtick 3 ตัวขึ้นไป) — ช่องว่างนำหน้ามีเพดานเดียวกับหัวก้อน
_REVIEW_FENCE_OPEN_RE = re.compile(r"^([ \t]*)(`{3,})review$")


def _review_norm(text, unfence: bool = False) -> tuple[str, bool]:
    """(รูปที่ใช้เทียบ, ช่องว่างที่ตัดทิ้งอยู่ในขอบเขตหรือไม่) — ดู normalize_review

    unfence=True (ใช้กับ review ที่ "ส่งมา" เท่านั้น — review_matches/review_difference): ถอดรั้ว ```review ... ```
    ที่ครอบทั้งก้อน "หนึ่งชั้น" ก่อนเทียบ รอบ FIXER (e2e จริง): Qwen3-4B คัดลอกบล็อก REVIEW มาทั้งรั้วของเซิร์ฟเวอร์เอง
    เนื้อในตรงทุกตัวอักษรแต่ถูกปฏิเสธ คนต้องกดอนุญาตสองครั้ง รั้วไม่ใช่เนื้อหา (review ของเซิร์ฟเวอร์ขึ้นต้นด้วย "[" หรือ
    "⚠" เสมอ ไม่มีทางขึ้นต้นด้วยรั้ว) เนื้อในยังต้องตรงเป๊ะเหมือนเดิม ความปลอดภัยจึงไม่เปลี่ยน — ถอดแค่ชั้นเดียว รั้วปิด
    ต้องยาวเท่ารั้วเปิด และช่องว่าง/บรรทัดว่างรอบรั้วยังนับเพดานเดิมทั้งหมด"""
    padded_ok = True
    lines = []
    for ln in str(text).replace("\r\n", "\n").split("\n"):
        s = ln.rstrip(" \t\r")
        if len(ln) - len(s) > REVIEW_PAD_MAX:
            padded_ok = False
        lines.append(s)
    trail = 0
    while lines and not lines[-1]:
        lines.pop()
        trail += 1
    lead = 0
    while lines and not lines[0]:
        lines.pop(0)
        lead += 1
    if unfence and len(lines) >= 2:
        m = _REVIEW_FENCE_OPEN_RE.match(lines[0])
        close = lines[-1].lstrip(" \t")
        if m and close == m.group(2):
            if len(m.group(1)) > REVIEW_PAD_MAX or len(lines[-1]) - len(close) > REVIEW_PAD_MAX:
                padded_ok = False
            lines = lines[1:-1]
            while lines and not lines[-1]:
                lines.pop()
                trail += 1
            while lines and not lines[0]:
                lines.pop(0)
                lead += 1
    if lead > REVIEW_BLANK_MAX or trail > REVIEW_BLANK_MAX + 1:     # +1 = บรรทัดสุดท้ายหลัง \n ปิดท้าย
        padded_ok = False
    if lines:
        # รอบ FIXER (e2e จริงกับ Qwen3-4B): โมเดลเขียน review เป็น " [python] ..." ทุกครั้ง — tokenizer ชอบโทเคน
        # ' [' ต่อจากเครื่องหมายคำพูดเปิดของ JSON คนเห็นโค้ดถูก กดอนุญาตแล้ว แต่ไม่มีอะไรรันเพราะเทียบไม่ตรง
        # ตัดช่องว่างหน้า "บรรทัดแรกของทั้งก้อน" ได้อย่างปลอดภัย: review ที่เซิร์ฟเวอร์สร้างขึ้นต้นด้วย "[การกระทำ]"
        # หรือ "⚠" เสมอ ช่องว่างตรงนั้นไม่มีความหมาย (การเล่นซ้ำใช้อาร์กิวเมนต์ที่เก็บไว้ ไม่ใช่ข้อความนี้)
        # ส่วนช่องว่างหน้าบรรทัดอื่นยังต้องตรงเป๊ะ (ย่อหน้าของโค้ดใน diff/บริบทมีความหมายต่อคนอ่าน)
        first = lines[0].lstrip(" \t")
        if len(lines[0]) - len(first) > REVIEW_PAD_MAX:
            padded_ok = False
        lines[0] = first
    return "\n".join(lines), padded_ok


def normalize_review(text) -> str:
    """รูปที่ใช้เทียบ: \\r\\n -> \\n, ตัดช่องว่างท้ายบรรทัด, ตัดช่องว่างหน้าบรรทัดแรกของทั้งก้อน
    (+ บรรทัดว่างหัว/ท้ายทั้งก้อน) เท่านั้น ไม่แตะอย่างอื่นเลย — อักขระที่ต่างกันแม้ตัวเดียวคือข้อความคนละอัน"""
    return _review_norm(text)[0]


def review_matches(stored, given) -> bool:
    """given ตรงกับ stored หรือไม่ — ต่างกันได้แค่รูปแบบใน normalize_review และช่องว่างที่ตัดทิ้งต้องไม่เกิน
    REVIEW_PAD_MAX ต่อบรรทัด / บรรทัดว่างไม่เกิน REVIEW_BLANK_MAX (กันการเติมช่องว่างดันโค้ดออกจากกล่องอนุญาต)"""
    if not isinstance(stored, str) or not isinstance(given, str):
        return False
    want = normalize_review(stored)
    # unfence: ยอมรั้ว ```review ที่ครอบทั้งก้อนหนึ่งชั้น (โมเดลคัดลอกทั้งบล็อกมา) — เนื้อในยังต้องตรงทุกตัวอักษร
    got, padded_ok = _review_norm(given, unfence=True)
    return bool(want) and padded_ok and got == want


def _snip(text: str, col: int, width: int = 36) -> str:
    """ช่วงสั้นๆ รอบตำแหน่ง col ในรูปสตริง JSON (ช่องว่าง/อักขระควบคุมเห็นชัด) อักขระซ่อนแสดงเป็นรหัส"""
    start = max(0, col - width // 3)
    part = text[start:start + width]
    shown = json.dumps(part, ensure_ascii=False)
    return visible(("…" if start else "") + shown + ("…" if start + width < len(text) else ""))


def review_difference(stored, given) -> str:
    """บอก "จุดแรก" ที่ review ที่ส่งมาต่างจากของจริงแบบเจาะจง (บรรทัด/ตำแหน่ง/ต้องเป็นอะไร/ได้อะไร)

    รอบ FIXER: เดิมตอบแค่ว่า "ไม่ตรง" แล้วแนบ review ทั้งก้อนมาใหม่ โมเดล 4B เลยแสดงทั้งก้อนให้ผู้ใช้อีกรอบ
    (2 นาทีครึ่ง) จน token หมดอายุโดยไม่ได้ลองใหม่เลย บอกจุดที่ผิดตรงๆ ให้แก้ได้ในการเรียกครั้งถัดไป
    ข้อความ stored โมเดลได้เห็นอยู่แล้วตอนขอ token จึงไม่มีอะไรรั่วเพิ่ม"""
    if not isinstance(given, str) or not given.strip():
        return "ไม่ได้ส่ง review มา (ต้องใส่ข้อความในบล็อก REVIEW ทั้งก้อน)"
    want = normalize_review(stored).split("\n")
    got_text, padded_ok = _review_norm(given, unfence=True)       # เทียบแบบเดียวกับ review_matches
    got = got_text.split("\n")
    if got == want and not padded_ok:
        return ("ข้อความตรงกันแต่มีช่องว่าง/บรรทัดว่างเกินมามากผิดปกติ (หัวข้อความ ท้ายบรรทัด หรือหัว/ท้ายทั้งก้อน) "
                "— ส่งตามบล็อกโดยไม่เติมช่องว่าง")
    for i, (w, g) in enumerate(zip(want, got)):
        if w == g:
            continue
        if g.lstrip(" \t") == w:
            return ("บรรทัด %d ของที่ส่งมาขึ้นต้นด้วยช่องว่างเกินมา %d ตัว — บรรทัดนี้ต้องขึ้นต้นด้วย %s"
                    % (i + 1, len(g) - len(w), _snip(w, 0)))
        if w.lstrip(" \t") == g:
            return ("บรรทัด %d ของที่ส่งมาขาดช่องว่างหน้าบรรทัด %d ตัว — บรรทัดนี้ต้องเป็น %s"
                    % (i + 1, len(w) - len(g), _snip(w, 0)))
        col = next((k for k, (a, b) in enumerate(zip(w, g)) if a != b), min(len(w), len(g)))
        return ("บรรทัด %d ตัวอักษรที่ %d ไม่ตรง: ต้องเป็น %s แต่ส่งมาเป็น %s"
                % (i + 1, col + 1, _snip(w, col), _snip(g, col)))
    if len(got) < len(want):
        return ("ส่งมาไม่ครบ: มี %d บรรทัด ต้องมี %d บรรทัด — บรรทัดแรกที่ขาดคือบรรทัด %d %s"
                % (len(got), len(want), len(got) + 1, _snip(want[len(got)], 0)))
    return ("มีบรรทัดเกินมา: ส่งมา %d บรรทัด ต้องมี %d บรรทัด — บรรทัดที่เกินเริ่มที่บรรทัด %d %s"
            % (len(got), len(want), len(want) + 1, _snip(got[len(want)], 0)))


def review_oneline(value) -> str:
    """ค่าหนึ่งค่าที่จะวางต่อท้ายหัวข้อ "ชื่อ: ค่า" ใน review ต้องอยู่บรรทัดเดียวเสมอ

    รอบ FIXER: ค่าจากโมเดลที่มี \\n (argv ของ task_start, คำสั่งในทะเบียนงาน, timeout ที่อ่านไม่ออก, path แปลกๆ)
    เดิมถูกพิมพ์ต่อเป็นหลายบรรทัด บรรทัดต่อจึงปลอมเป็นหัวข้อ/อาร์กิวเมนต์ใหม่ได้ (เช่น "  [9] --flag")
    ค่าที่มีตัวขึ้นบรรทัดจึงแสดงเป็นสตริง JSON ในเครื่องหมายคำพูด (\\n เห็นเป็นตัวอักษร) ค่าปกติแสดงตามเดิม"""
    s = "" if value is None else str(value)
    if any(c in s for c in "\n\r\x0b\x0c\x85  "):
        return json.dumps(s, ensure_ascii=False)
    return s


def review_url_lines(url) -> list[str]:
    """บรรทัดประกอบ URL ใน review: โฮสต์แยกให้เห็นชัด + รูป punycode (IDNA) เมื่อชื่อโดเมนมีอักษรที่ไม่ใช่ ASCII

    รอบ FIXER (homoglyph): "exаmple.com" ที่ใช้ а ซีริลลิก หน้าตาเหมือนของจริงทุกประการ แต่ punycode
    "xn--exmple-4nf.com" ต่างชัด — คนเห็นทั้งสองรูปก่อนกดอนุญาต"""
    try:
        from urllib.parse import urlsplit
        host = urlsplit(str(url or "")).hostname or ""
    except ValueError:
        host = ""
    if not host:
        return []
    out = ["โฮสต์ (host): %s" % host]
    if not host.isascii():
        try:
            puny = host.encode("idna").decode("ascii")
        except UnicodeError:
            puny = "(แปลงเป็น punycode ไม่ได้ — ชื่อโดเมนผิดรูปแบบ)"
        out.append("โฮสต์แบบ punycode (IDNA): %s" % puny)
        out.append("⚠ ชื่อโดเมนมีอักษรที่ไม่ใช่ ASCII — ตรวจว่าไม่ใช่โดเมนปลอมที่หน้าตาเหมือนของจริง")
    return out


def visible(text) -> str:
    """แสดงอักขระซ่อนเป็น «U+XXXX» แบบไม่ตัดบรรทัด — ใช้กับข้อความประกอบนอกบล็อก review
    (path/URL/ชื่อแท็บที่มาจากโมเดลหรือหน้าเว็บ) ขึ้นบรรทัดและแท็บคงไว้ตามเดิม"""
    out = []
    for ch in str(text if text is not None else ""):
        if ch in "\n\t" or ch in _REVIEW_MARKS or not _review_hidden(ch):
            out.append(ch)
        else:
            out.append(_escape(ch))
    return "".join(out)


def review_fence(text: str) -> str:
    """รั้ว ``` ที่ยาวกว่าลำดับ backtick ใดๆ ในข้อความ — เนื้อหาหลุดออกจากบล็อกไปปลอมข้อความนอกบล็อกไม่ได้"""
    fence = "```"
    while fence in text:
        fence += "`"
    return "%sreview\n%s\n%s" % (fence, text, fence)


def _scrub_service_token(text: str) -> str:
    """ลบค่า token ของบริการในเครื่องออกจาก review ก่อนเก็บ

    ผลของเครื่องมือทุกอันผ่าน secrets_util.scrub ก่อนถึงโมเดล ถ้า review ที่เก็บไว้ยังมีค่าจริง
    โมเดลจะเห็นแต่ *** แล้วคัดลอกกลับมาไม่มีทางตรง = ยืนยันไม่ได้เลย จึงต้องล้างแบบเดียวกันตั้งแต่ตอนเก็บ
    ใช้เฉพาะเมื่อ server/เครื่องมือ import secrets_util ไว้แล้ว (guard ไม่ import เอง กันไปสร้างไฟล์ token)
    """
    mod = sys.modules.get("secrets_util")
    if mod is None:
        return text
    try:
        return mod.scrub(text)
    except Exception:          # noqa: BLE001 — ล้างไม่ได้ก็ยังต้องออก token ได้
        return text


def default_review(action: str, detail: str) -> str:
    """review ของผู้เรียกที่ไม่ได้สร้างเอง (เช่น scheduler) = การกระทำ + รายละเอียดที่ token ผูกอยู่"""
    return "[%s]\n%s" % (action, detail)


def _digest(detail: str) -> str:
    return hashlib.sha256(str(detail).encode("utf-8", "replace")).hexdigest()


def token_ref(token: str) -> str:
    """รหัสอ้างอิงของ confirm_token สำหรับ audit.log — ย้อนกลับเป็น token ไม่ได้"""
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()[:10]


def need_confirm(action: str, detail: str, review: str | None = None,
                 supersede: bool = False) -> str:
    """ลงทะเบียนการกระทำที่รอการยืนยัน คืน token สั้นๆ ให้ผู้ใช้ส่งกลับมา

    token ผูกกับ (action, hash ของ detail, โปรเจกต์ปัจจุบัน) ผู้เรียกต้องสร้าง detail
    จากอาร์กิวเมนต์ที่ normalize แล้วแบบเดียวกันทั้งตอนขอและตอนใช้ ไม่งั้นจะยืนยันไม่ผ่าน
    และเก็บ "การเรียกเครื่องมือ" ปัจจุบันไว้ด้วย (ถ้ามาจาก server) ให้ local_confirm เล่นซ้ำ

    รอบ review:
      * review = ข้อความดิบที่ผู้เรียกสร้างจากอาร์กิวเมนต์จริง (โค้ดเต็ม/คำสั่งเต็ม/diff) ถูกแปลงด้วย
        render_review แล้วเก็บไว้กับ token — local_confirm ต้องส่งข้อความนี้กลับมาตรงตัว
        ไม่ส่ง review = ใช้ default_review(action, detail) (สิ่งที่ token ผูกอยู่นั่นเอง)
      * review ยาวเกินเพดาน = ReviewTooLarge (ไม่ออก token) — กล่องอนุญาตที่ยาวจนไม่มีใครอ่านคือการอนุมัติแบบตาบอด
      * supersede=True: ทิ้ง token ที่ยังค้างของ action เดียวกันในโปรเจกต์เดียวกันก่อน (python ใช้ — มี token
        รอได้ทีละอัน โมเดลจึงเลือกยืนยันโค้ดอื่นที่ไม่ได้โชว์ล่าสุดไม่ได้)
      * ต่อโปรเจกต์ค้างได้ไม่เกิน MAX_PENDING_PER_PROJECT (ทิ้งตัวเก่าสุดก่อน)
    """
    raw = default_review(action, detail) if review is None else str(review)
    text, stats = render_review(_scrub_service_token(raw))
    text = _scrub_service_token(text)
    if not text.strip() or stats["lines"] > REVIEW_MAX_LINES or stats["chars"] > REVIEW_MAX_CHARS:
        audit("confirm_review_too_large", {"action": scrub_text(action)[:300],
                                           "lines": stats["lines"], "chars": stats["chars"],
                                           "project": current_project()})
        raise ReviewTooLarge(
            "การกระทำนี้ยาวเกินกว่าที่คนจะตรวจทานได้ในกล่องอนุญาต (%d บรรทัด / %d ตัวอักษร เพดาน %d / %d) "
            "จึงไม่ออก confirm_token — แบ่งเป็นหลายครั้งให้เล็กลง"
            % (stats["lines"], stats["chars"], REVIEW_MAX_LINES, REVIEW_MAX_CHARS))
    token = secrets.token_hex(4)
    scope = current_project()
    call = getattr(_ctx, "call", None)
    try:
        size = len(json.dumps(call, ensure_ascii=False, default=str)) if call else 0
    except (TypeError, ValueError):
        size = 0
    size += len(text.encode("utf-8", "replace"))
    dropped = 0
    with _lock:
        now = time.time()
        for t in [t for t, it in _pending.items() if it["exp"] < now]:
            _pending.pop(t, None)
        if supersede:
            for t in [t for t, it in _pending.items()
                      if it["scope"] == scope and it["action"] == action]:
                _pending.pop(t, None)
                dropped += 1
        mine = [t for t, it in _pending.items() if it["scope"] == scope]
        while len(mine) >= MAX_PENDING_PER_PROJECT:
            oldest = min(mine, key=lambda t: _pending[t]["exp"])
            _pending.pop(oldest, None)
            mine.remove(oldest)
        while _pending and (len(_pending) >= MAX_PENDING or
                            sum(it.get("size", 0) for it in _pending.values()) + size
                            > MAX_PENDING_BYTES):
            oldest = min(_pending, key=lambda t: _pending[t]["exp"])
            _pending.pop(oldest, None)
        # viewed = เวลาที่กล่องอนุญาตของหน้าแชตดึง review ของ token นี้ไปแสดงสำเร็จ (0 = ยังไม่เคย) — mark_viewed
        # unviewed = จำนวนครั้งที่ local_confirm แบบ token อย่างเดียวถูกปฏิเสธเพราะยังไม่มีใครเห็น review (ใช้เลือกข้อความตอบ)
        _pending[token] = {"action": action, "digest": _digest(detail),
                           "scope": scope, "exp": now + CONFIRM_TTL, "issued": now, "size": size,
                           "review": text, "viewed": 0.0, "unviewed": 0,
                           "replay": copy.deepcopy(call) if call else None}
    audit("confirm_requested", {"action": scrub_text(action)[:300],
                                "detail": scrub_text(detail)[:400],
                                "project": scope, "ref": token_ref(token),
                                "tool": (call or {}).get("name"),
                                "review_lines": stats["lines"], "review_hidden": stats["hidden"],
                                "superseded": dropped})
    return token


def pending_review(token: str) -> str | None:
    """ข้อความตรวจทานของ token นี้ (ของโปรเจกต์ปัจจุบัน) หรือ None ถ้าไม่มี/หมดอายุ/เป็นของโปรเจกต์อื่น"""
    tok = str(token or "").strip()
    if not tok:
        return None
    with _lock:
        item = _pending.get(tok)
        if not item or item["exp"] < time.time() or item["scope"] != current_project():
            return None
        return item.get("review")


def pending_view(token: str, mark_viewed: bool = False) -> dict | None:
    """มุมมองอ่านอย่างเดียวของ token ที่ค้างอยู่ (ของโปรเจกต์ปัจจุบัน ผิวไหนก็ได้) สำหรับกล่องอนุญาต — รอบ review-fetch S1

    คืน {action, review, expires_in_s} หรือ None ถ้าไม่มี/หมดอายุ/ใช้ไปแล้ว/เป็นของโปรเจกต์อื่น
    (ทุกกรณีตอบเหมือนกัน — ไม่บอกว่า token ของโปรเจกต์อื่นมีอยู่)
    ไม่ใช้ ไม่ต่ออายุ ไม่คืนค่า token และไม่คืนอาร์กิวเมนต์ที่จะเล่นซ้ำ — แค่ข้อความที่คนต้องเห็นก่อนกด
    action มี path ที่มาจากโมเดล จึงแสดงอักขระซ่อนเป็น «U+XXXX» แบบเดียวกับ confirm_hint

    รอบ FIXER ของ S1/S2: mark_viewed=True (server ส่งมาเมื่อคำขอมาจากหน้าเว็บ = กล่องอนุญาตของหน้าแชต) จดว่า
    review ของ token นี้ถูกดึงไปแสดงแล้ว — local_confirm แบบ token อย่างเดียวรันได้เฉพาะ token ที่ถูกดึงไปแสดงแล้วเท่านั้น
    (ดู confirming) การจดไม่เปลี่ยนอายุ/สิ่งที่ token ผูกอยู่ และยังใช้ได้ครั้งเดียวเหมือนเดิม"""
    tok = str(token or "").strip()
    if not tok:
        return None
    with _lock:
        item = _pending.get(tok)
        now = time.time()
        if not item or item["exp"] < now or item["scope"] != current_project():
            return None
        review = item.get("review")
        action = item.get("action")
        left = item["exp"] - now
        if mark_viewed and isinstance(review, str) and review:
            item["viewed"] = now
    if not isinstance(review, str) or not review:
        return None
    return {"action": visible(action), "review": review, "expires_in_s": max(1, int(left))}


def pending_viewed(token: str) -> bool:
    """review ของ token นี้ (ของโปรเจกต์ปัจจุบัน ยังไม่หมดอายุ) เคยถูกกล่องอนุญาตดึงไปแสดงสำเร็จหรือยัง"""
    tok = str(token or "").strip()
    if not tok:
        return False
    with _lock:
        item = _pending.get(tok)
        if not item or item["exp"] < time.time() or item["scope"] != current_project():
            return False
        return bool(item.get("viewed"))


def note_unviewed(token: str) -> int:
    """นับครั้งที่ local_confirm แบบ token อย่างเดียวถูกปฏิเสธเพราะ review ยังไม่เคยถูกแสดง คืนจำนวนหลังนับ (0 = ไม่มี token)
    server ใช้เลือกข้อความ: ครั้งแรกบอกให้ลองใหม่ทันที ครั้งต่อไปบอกให้หยุดแล้วให้ผู้ใช้รีโหลดหน้าแชต (กันโมเดลวนไม่รู้จบ)"""
    tok = str(token or "").strip()
    with _lock:
        item = _pending.get(tok) if tok else None
        if not item or item["exp"] < time.time() or item["scope"] != current_project():
            return 0
        item["unviewed"] = int(item.get("unviewed") or 0) + 1
        return item["unviewed"]


def pending_replay(token: str) -> dict | None:
    """การเรียกเครื่องมือที่รอยืนยันด้วย token นี้ (ของโปรเจกต์ปัจจุบัน) หรือ None ถ้าไม่มี/หมดอายุ
    ไม่เผา token — consume_confirm ของเครื่องมือปลายทางเป็นคนเผาตอนลงมือจริง"""
    tok = str(token or "").strip()
    if not tok:
        return None
    with _lock:
        item = _pending.get(tok)
        if not item or item["exp"] < time.time() or item["scope"] != current_project():
            return None
        return copy.deepcopy(item.get("replay"))


def extend_confirm(token: str) -> int:
    """review ไม่ตรง/ไม่ได้ส่ง (token ยังไม่ถูกใช้): ต่ออายุให้เหลืออย่างน้อย CONFIRM_RETRY_TTL
    แต่รวมแล้วไม่เกิน CONFIRM_TTL_MAX นับจากตอนออก คืนจำนวนวินาทีที่เหลือ (0 = ไม่มี/หมดอายุ/โปรเจกต์อื่น)

    ไม่เปลี่ยนสิ่งที่ token ผูกอยู่ (action/digest/โปรเจกต์/review) และยังใช้ได้ครั้งเดียวเหมือนเดิม
    เพดานรวมกันการยื้อ token ไว้ไม่รู้จบด้วยการส่ง review ผิดซ้ำๆ"""
    tok = str(token or "").strip()
    now = time.time()
    with _lock:
        item = _pending.get(tok) if tok else None
        if not item or item["exp"] < now or item["scope"] != current_project():
            return 0
        cap = item.get("issued", item["exp"] - CONFIRM_TTL) + CONFIRM_TTL_MAX
        item["exp"] = max(item["exp"], min(cap, now + CONFIRM_RETRY_TTL))
        return max(0, int(item["exp"] - now))


def discard_confirm(token: str) -> None:
    """ทิ้ง token หลัง local_confirm เล่นซ้ำไปแล้วหนึ่งครั้ง ไม่ว่าเครื่องมือปลายทางจะ consume หรือไม่
    (เช่นสถานะเปลี่ยนจนไม่ต้องยืนยันแล้ว) — กันการเล่นซ้ำการกระทำเดิมสองรอบ"""
    with _lock:
        _pending.pop(str(token or "").strip(), None)


def consume_confirm(token: str, action: str, detail: str) -> bool:
    """ใช้ token ได้ครั้งเดียว ต้องตรงทั้ง action, รายละเอียด และโปรเจกต์เดิม
    และต้องมาทางช่อง local_confirm เท่านั้น (confirming(token, review) ครอบอยู่: review ตรง หรือไม่ส่ง review แต่
    กล่องอนุญาตดึง review ของ token นี้ไปแสดงแล้ว)

    token ที่ไม่ตรงจะไม่ถูกเผาทิ้ง (ผู้ใช้อาจอนุมัติการกระทำเดิมอยู่) แต่ก็ใช้กับอย่างอื่นไม่ได้
    """
    tok = str(token or "").strip()
    if not tok:
        return False
    if getattr(_ctx, "confirming", None) != tok:
        audit("confirm_wrong_channel", {"action": scrub_text(action)[:300],
                                        "ref": token_ref(tok)})
        return False
    with _lock:
        item = _pending.get(tok)
        if not item:
            return False
        if item["exp"] < time.time():
            _pending.pop(tok, None)
            return False
        if (item["action"] != action or item["digest"] != _digest(detail)
                or item["scope"] != current_project()):
            audit("confirm_mismatch", {"action": scrub_text(action)[:300],
                                       "ref": token_ref(tok)})
            return False
        _pending.pop(tok, None)
    audit("confirm_used", {"action": scrub_text(action)[:300], "ref": token_ref(tok)})
    return True


def confirm_call_text(token: str) -> str:
    """รูปการเรียกขั้นที่สองที่บอกโมเดล — token อย่างเดียว (รอบ review-fetch S2)
    รูป local_confirm(confirm_token="xxxx") คงไว้ตรงตัว: เทสต์/ตัวดึง token ของหน้าแชตจับรูป confirm_token="..." นี้"""
    return "%s(confirm_token=\"%s\")" % (CONFIRM_TOOL, token)


def review_steps(token: str, retry: bool = False) -> str:
    """ขั้นตอนหลังได้ token (retry=False) และหลัง local_confirm ตอบว่า review ไม่ตรง (retry=True)

    รอบ FIXER: ตอนตอบว่าไม่ตรง ขั้นที่ 1 เดิม "แสดง REVIEW ให้ผู้ใช้แล้วถาม" ทำให้โมเดล 4B แสดงทั้งก้อนซ้ำ
    แล้วจบเทิร์นโดยไม่ลองใหม่ ทั้งที่ผู้ใช้อนุมัติไปแล้ว
    รอบ review-fetch (S2, e2e จริง): โมเดล 4B คัดลอก REVIEW ยาวกลับมาไม่ครบ แล้วถามผู้ใช้ซ้ำแทนการลองใหม่
    ตอนนี้ไม่ขอให้คัดลอกกลับมาอีก — เรียก local_confirm ด้วย token อย่างเดียว กล่อง "อนุญาต" ของหน้าแชตดึง REVIEW
    จากเซิร์ฟเวอร์มาแสดงเอง (ไม่พึ่งข้อความของโมเดล) จึงเป็นด่านคนที่แท้จริง ส่วนการ "แสดงให้ผู้ใช้และถามก่อน" ยังอยู่
    ตอน retry บอกให้ลองใหม่ทันทีโดยไม่ถามซ้ำ: การเรียก local_confirm ที่ถูกปฏิเสธผ่านกล่องอนุญาตมาแล้วหนึ่งครั้ง
    (คนกดอนุญาตแล้ว) และการเรียกใหม่ก็ต้องผ่านกล่องอนุญาตอีกครั้งเสมอ — ไม่มีขั้นไหนข้ามคน"""
    call = confirm_call_text(token)
    if retry:
        return ("1. ให้เรียก %s ใหม่ทันที โดยไม่ต้องส่ง review — ไม่ต้องคัดลอก REVIEW ไม่ต้องแสดงซ้ำ "
                "และไม่ต้องถามผู้ใช้ใหม่ (ไม่ต้องเรียกเครื่องมือเดิมซ้ำ)\n"
                "2. กล่อง \"อนุญาต\" ของหน้าแชตจะแสดง REVIEW จากเซิร์ฟเวอร์ให้ผู้ใช้ตรวจแล้วกดเองอีกครั้ง "
                "— นั่นคือสิ่งที่จะรันจริง"
                % call)
    # รอบ FIXER (e2e จริง 2026-10-01): Qwen3-4B ไม่เคยแสดงบล็อก REVIEW ตอบแค่คำถามบรรทัดเดียว — คำสั่งนามธรรม
    # "แสดงให้ผู้ใช้ดู" ไม่พอสำหรับโมเดลเล็ก จึงบอกเป็นการกระทำที่จับต้องได้: คัดลอกทั้งบล็อก (พร้อมรั้ว) ลงในคำตอบ
    # (ถ้าโมเดลเผลอส่งบล็อกพร้อมรั้วกลับมาใน local_confirm ก็ยังตรง — review_matches ถอดรั้วหนึ่งชั้น)
    # กล่องอนุญาตยังเป็นด่านจริง (เซิร์ฟเวอร์บังคับว่าต้องถูกแสดงในกล่องก่อน) ส่วนนี้คือให้คนเห็นในแชตด้วย
    return ("1. ตอบผู้ใช้โดยแสดงบล็อก REVIEW ข้างบนครบทุกบรรทัด — คัดลอกทั้งบล็อกพร้อมรั้วบนล่างลงในคำตอบตรงตัว "
            "(ห้ามย่อ ห้ามสรุปแทน ห้ามแก้) แล้วถามว่าอนุมัติไหม\n"
            "2. ถ้าผู้ใช้อนุมัติ ให้เรียก %s — ส่ง token อย่างเดียวพอ ไม่ต้องคัดลอก REVIEW กลับมา "
            "(review ไม่บังคับ ถ้าส่งต้องตรงทุกตัวอักษร) และไม่ต้องเรียกเครื่องมือเดิมซ้ำ\n"
            "3. หน้าแชตจะแสดง REVIEW จากเซิร์ฟเวอร์ในกล่อง \"อนุญาต\" ให้ผู้ใช้ตรวจอีกครั้ง — นั่นคือสิ่งที่จะรันจริง"
            % call)


def confirm_hint(token: str, action: str, detail: str) -> str:
    """ข้อความมาตรฐานที่ส่งกลับไปให้โมเดลแสดงต่อผู้ใช้ตอนรอการยืนยัน

    รอบ review: แนบบล็อก REVIEW (ข้อความตรวจทานที่เก็บไว้กับ token) ไว้ในรั้ว
    บรรทัด "การกระทำ/รายละเอียด" เป็นแค่ข้อความประกอบ — ของจริงคือบล็อก REVIEW
    รอบ review-fetch (S2): บล็อกนี้มีไว้ "แสดงให้ผู้ใช้ดู" ไม่ใช่ให้คัดลอกกลับ (local_confirm ใช้ token อย่างเดียว)
    """
    with _lock:
        review = (_pending.get(str(token or "").strip()) or {}).get("review")
    block = review_fence(review) if review else "(ไม่พบข้อความตรวจทานของ token นี้ — ขอ token ใหม่)"
    return (
        "ต้องยืนยันก่อนทำจริง (กฎ S03 สองขั้นตอน)\n"
        "  การกระทำ : %s\n"
        "  รายละเอียด: %s\n\n"
        "REVIEW — ข้อความตรวจทานที่เซิร์ฟเวอร์สร้างจากอาร์กิวเมนต์จริง คือสิ่งที่จะเกิดขึ้นทุกตัวอักษร "
        "(แสดงบล็อกนี้ให้ผู้ใช้ดู):\n%s\n\n"
        "ขั้นตอน:\n%s\n"
        "token นี้ใช้ได้ครั้งเดียว ผูกกับการกระทำนี้เท่านั้น และหมดอายุใน %d นาที\n"
        "ห้ามเดาว่าผู้ใช้อนุมัติแล้ว ต้องถามก่อนเสมอ"
        % (visible(action), visible(detail), block, review_steps(token), int(CONFIRM_TTL // 60))
    )


# ------------------------------------------------------- project isolation
def project_dir(project: str) -> str:
    """โฟลเดอร์ข้อมูลของโปรเจกต์ สร้างให้ถ้ายังไม่มี

    ทุกเครื่องมือที่เก็บสถานะต้องอ้างผ่านฟังก์ชันนี้เท่านั้น เพื่อให้ S04 เป็นจริง
    คือโปรเจกต์หนึ่งมองไม่เห็นข้อมูลของอีกโปรเจกต์
    """
    d = PROJECT_DATA / project_slug(project)
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Denied("สร้างโฟลเดอร์โปรเจกต์ไม่ได้: %s" % exc) from exc
    return str(d)


# --------------------------------------------------------------- self-test
def policy_summary() -> str:
    cfg = _load_config()
    lines = ["นโยบายความปลอดภัยที่ใช้อยู่", "", "พื้นที่ที่อนุญาต:"]
    for r in cfg["allowed_roots"]:
        lines.append("  %-28s %s" % (r["path"], r.get("mode", "read_only")))
    lines.append("")
    lines.append("รูปแบบ path ที่ถูกบล็อก: %d รายการ (credential, ฐานข้อมูลแอป, ไฟล์ระบบ, คีย์)"
                 % len(cfg["blocked_globs"]))
    lines.append("นามสกุลที่ห้ามอ่าน: %s" % ", ".join(cfg["blocked_suffixes"]))
    lines.append("เขตห้ามเขียน: %d รูปแบบ (โค้ด/ค่าตั้งของสแตก, Startup, PowerShell profile, "
                 ".git, rc ของ shell) — ปฏิเสธแม้มี confirm_token" % len(cfg["write_protected"]))
    lines.append("อ่านไฟล์ได้สูงสุด %s ไบต์ต่อครั้ง" % format(cfg.get("max_read_bytes", 0), ","))
    lines.append("")
    lines.append("การกระทำที่เปลี่ยนเครื่อง (รันคำสั่ง แก้ไฟล์ ทับไฟล์ สร้างไฟล์สคริปต์ เปิด/หยุดงาน) "
                 "ต้องยืนยันสองขั้นเสมอ ขั้นที่สองทำได้ทาง %s เท่านั้น" % CONFIRM_TOOL)
    lines.append("กล่องอนุญาตของหน้าแชตดึงข้อความตรวจทาน (review) ที่เซิร์ฟเวอร์สร้างมาแสดงเอง = โค้ด/คำสั่งจริง "
                 "(อักขระซ่อนแสดงเป็น «U+XXXX») ขั้นที่สองส่ง token อย่างเดียวได้ ถ้าส่ง review มาต้องตรงตัว "
                 "token ค้างได้ไม่เกิน %d ตัวต่อโปรเจกต์" % MAX_PENDING_PER_PROJECT)
    lines.append("บันทึก/สถานะรวมของสแตก (audit.log, C:\\LLM\\logs, tasks) อ่านจากเครื่องมือไม่ได้")
    lines.append("ข้อมูลของโปรเจกต์อื่นเข้าถึงไม่ได้ (กฎ S04)")
    lines.append("ทุกการเรียกเครื่องมือถูกบันทึกที่ %s" % AUDIT_PATH)
    return "\n".join(lines)
