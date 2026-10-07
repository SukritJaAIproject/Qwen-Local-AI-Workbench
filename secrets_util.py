# -*- coding: utf-8 -*-
"""secrets_util.py -- token ของบริการในเครื่อง (สัญญา C1/C2 ของรอบแก้ความปลอดภัย 2026-09-30)

ทำไมต้องมีไฟล์นี้
-----------------
เดิม MCP 8791/8792 รับคำขอจากใครก็ได้ และสะท้อน Origin ทุกค่ากลับไปใน CORS
หน้าเว็บใดๆ ที่ผู้ใช้เปิด (หรือหน้าที่ใช้ DNS rebinding) จึงสั่งเครื่องมือในเครื่องได้เลย
ทางแก้คือทุกคำขอต้องถือ token ที่อยู่ในไฟล์ที่เบราว์เซอร์อ่านไม่ได้ และต้องมาจาก Origin/Host ของเราเอง

ไฟล์ token
  C:\\LLM\\secrets\\local-services.token   hex 64 ตัว บรรทัดเดียว ไม่มี BOM
  launcher สร้างให้ถ้ายังไม่มี และ get_token() ที่นี่ก็สร้างแบบ atomic ได้เองเช่นกัน
  (ใครขึ้นก่อนก็ได้ ไม่มีทางได้สองค่าเพราะใช้ rename ที่ล้มถ้าปลายทางมีอยู่แล้ว)

กติกาที่ห้ามละเมิด
  * ห้าม print/log ค่า token ทุกกรณี ฟังก์ชันในไฟล์นี้จึงไม่มีตัวไหนคืนค่าออกไปทาง log
  * โฟลเดอร์ C:\\LLM\\secrets ถูก guard.py บล็อกทั้งอ่านและเขียนสำหรับเครื่องมือของโมเดล
  * เทียบ token แบบ constant-time เสมอ

ตัวแปรสภาพแวดล้อม LLM_LOCAL_TOKEN_FILE ใช้ชี้ไฟล์อื่นได้ มีไว้ให้เทสต์ใช้ token ทดสอบ
แทนการแตะไฟล์จริง (ผู้ที่ตั้ง env ของโปรเซสได้ก็คุมโปรเซสนั้นอยู่แล้ว จึงไม่ได้เปิดช่องใหม่)

stdlib ล้วน ใช้ได้ทั้ง hub, scheduler, gateway และ MCP ทั้งสองตัว
"""
from __future__ import annotations

import hmac
import os
import re
import secrets
import threading
import time
from pathlib import Path

SECRETS_DIR = Path(r"C:\LLM\secrets")
TOKEN_PATH = SECRETS_DIR / "local-services.token"
TOKEN_ENV = "LLM_LOCAL_TOKEN_FILE"

# Origin ที่ยอมรับ: หน้า WebUI ของแต่ละโปรเจกต์ (8101-8179), หน้า hub (8100)
# และ llama-server (8099) เผื่อ WebUI ยิงผ่าน --ui-mcp-proxy
ALLOWED_ORIGIN_RE = re.compile(r"^http://(127\.0\.0\.1|localhost):(8099|8100|81[0-7][0-9])$")
_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{64}$")

_lock = threading.Lock()
_cache: dict = {"key": None, "value": ""}


class TokenError(RuntimeError):
    """ไฟล์ token เสียหรืออ่านไม่ได้ — fail closed ไม่สร้างใหม่ทับของเดิม"""


def token_path() -> Path:
    override = os.environ.get(TOKEN_ENV, "").strip()
    return Path(override) if override else TOKEN_PATH


def _read_valid(path: Path) -> str:
    raw = path.read_bytes()
    # launcher เขียนด้วย PowerShell 5.1 อาจติด CRLF มา ส่วน BOM ไม่ควรมีแต่ทนไว้ก่อน
    text = raw.decode("utf-8-sig", "replace").strip()
    if not _TOKEN_RE.match(text):
        raise TokenError("ไฟล์ token %s ไม่ใช่ hex 64 ตัว" % path)
    return text


def _create(path: Path) -> None:
    """สร้างไฟล์ token แบบ atomic: เขียนไฟล์ชั่วคราวให้เสร็จก่อน แล้ว rename

    os.rename บน Windows ล้มถ้าปลายทางมีอยู่แล้ว จึงเป็น "สร้างเฉพาะตอนยังไม่มี" ในตัว
    ผู้อ่านไม่มีทางเห็นไฟล์ครึ่งไฟล์ และสองโปรเซสที่ขึ้นพร้อมกันได้ค่าเดียวกันแน่นอน
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("%s.%d.%s.tmp" % (path.name, os.getpid(), secrets.token_hex(4)))
    with open(tmp, "w", encoding="ascii", newline="\n") as fh:
        fh.write(secrets.token_hex(32) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    try:
        os.rename(tmp, path)
    except FileExistsError:
        pass                        # อีกโปรเซสชิงสร้างไปก่อน ใช้ของเขา
    finally:
        try:
            if tmp.exists():
                tmp.unlink()        # ไฟล์ชั่วคราวของเราเอง (มีค่าที่ไม่ได้ใช้) ต้องไม่ค้าง
        except OSError:
            pass


def get_token() -> str:
    """คืน token ของบริการในเครื่อง สร้างไฟล์ให้ถ้ายังไม่มี

    อ่านใหม่เมื่อ mtime/ขนาดไฟล์เปลี่ยน (ผู้ใช้หมุน token ได้โดยไม่ต้องรีสตาร์ตทุกตัว)
    ถ้าไฟล์มีอยู่แต่ผิดรูปแบบ ให้รอสั้นๆ เผื่อ launcher กำลังเขียนอยู่ แล้วค่อยยอมแพ้ด้วย TokenError
    """
    path = token_path()
    deadline = time.monotonic() + 2.0
    while True:
        try:
            st = path.stat()
        except FileNotFoundError:
            _create(path)
            continue
        key = (str(path), st.st_mtime_ns, st.st_size)
        with _lock:
            if _cache["key"] == key and _cache["value"]:
                return _cache["value"]
        try:
            value = _read_valid(path)
        except TokenError:
            if time.monotonic() < deadline:
                time.sleep(0.1)     # launcher (Set-Content) อาจสร้างไฟล์ว่างก่อนแล้วค่อยเขียน
                continue
            raise
        except OSError as exc:
            raise TokenError("อ่านไฟล์ token %s ไม่ได้: %s" % (path, type(exc).__name__)) from None
        with _lock:
            _cache["key"], _cache["value"] = key, value
        return value


def token_matches(given: str) -> bool:
    """เทียบแบบ constant-time อ่าน token ไม่ได้ = ปฏิเสธ (fail closed)"""
    try:
        want = get_token()
    except (TokenError, OSError):
        return False
    given = (given or "").strip()
    if not given:
        return False
    return hmac.compare_digest(given.encode("utf-8"), want.encode("utf-8"))


def bearer_from_header(value: str) -> str:
    """ดึง token จาก header Authorization แบบ "Bearer <token>" (ชื่อ scheme ไม่สนตัวพิมพ์)"""
    parts = (value or "").strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return ""


def auth_headers() -> dict:
    """header สำหรับไคลเอนต์ภายใน (scheduler, gateway) ที่เรียกบริการในเครื่อง"""
    return {"Authorization": "Bearer " + get_token()}


def origin_allowed(origin: str) -> bool:
    return bool(ALLOWED_ORIGIN_RE.match((origin or "").strip()))


def host_allowed(host: str, port: int) -> bool:
    """กัน DNS rebinding: เบราว์เซอร์ที่โดนหลอกจะส่ง Host เป็นชื่อโดเมนของผู้โจมตี"""
    host = (host or "").strip().lower()
    return host in ("127.0.0.1:%d" % port, "localhost:%d" % port)


def check_request(method: str, path: str, headers, port: int,
                  public_paths: tuple = ("/health",)) -> tuple[int, str] | None:
    """ตัดสินคำขอ HTTP ตามสัญญา C2 คืน None ถ้าผ่าน หรือ (status, เหตุผล) ถ้าไม่ผ่าน

    ลำดับ: Host -> Origin -> (OPTIONS/สาธารณะ ผ่าน) -> Bearer token
    เหตุผลที่คืนไปห้ามมีค่า token หรือค่าที่ผู้เรียกส่งมา
    """
    if not host_allowed(headers.get("Host", ""), port):
        return 403, "host_not_allowed"
    origin = headers.get("Origin")
    if origin is not None and not origin_allowed(origin):
        return 403, "origin_not_allowed"
    if method == "OPTIONS":
        return None
    route = (path or "").split("?", 1)[0].rstrip("/") or "/"
    if method == "GET" and route in public_paths:
        return None
    if not token_matches(bearer_from_header(headers.get("Authorization", ""))):
        return 401, "missing_or_bad_token"
    return None


CORS_ALLOW_HEADERS = ("Authorization, Content-Type, Mcp-Session-Id, "
                      "Mcp-Protocol-Version, Last-Event-ID")


def cors_headers(origin: str | None) -> list[tuple[str, str]]:
    """header CORS ที่ส่งกลับ — echo เฉพาะ Origin ที่อยู่ในรายการเท่านั้น ไม่มี credentials"""
    out = [("Vary", "Origin")]
    if origin and origin_allowed(origin):
        out += [("Access-Control-Allow-Origin", origin.strip()),
                ("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS"),
                ("Access-Control-Allow-Headers", CORS_ALLOW_HEADERS),
                ("Access-Control-Expose-Headers", "Mcp-Session-Id"),
                ("Access-Control-Max-Age", "600")]
    return out


def scrub(text: str) -> str:
    """ลบค่า token ออกจากข้อความ ก่อนส่งผลของเครื่องมือกลับไปให้โมเดล

    ด่านสุดท้ายกันกรณีที่คำสั่งซึ่งผู้ใช้อนุมัติแล้ว (เช่น findstr /s ทั้ง C:\\LLM)
    บังเอิญอ่านไฟล์ token ออกมา — โมเดลจะไม่มีวันเห็นค่าจริง
    """
    if not text:
        return text
    try:
        tok = get_token()
    except (TokenError, OSError):
        return text
    if tok in text:
        text = text.replace(tok, "***")
    low, up = tok.lower(), tok.upper()
    if low != tok and low in text:
        text = text.replace(low, "***")
    if up != tok and up in text:
        text = text.replace(up, "***")
    return text


if __name__ == "__main__":
    # ตัวเปิด (start-qwen38.ps1 ขั้น [0/4]) เรียก "secrets_util.py --ensure" ก่อนเปิด MCP/hub
    # เดิมไม่มีทางเข้านี้ ตัวเปิดจึงต้องถอยไปเรียก get_token() ผ่าน python -c ทุกครั้ง
    # พิมพ์แค่สถานะ ห้ามพิมพ์ค่า token (ตัวเปิดทิ้ง stdout อยู่แล้ว แต่คนรันเองก็ต้องไม่เห็นค่า)
    import sys
    if sys.argv[1:] == ["--ensure"]:
        try:
            get_token()
        except (TokenError, OSError) as exc:
            print("token: error %s" % type(exc).__name__, file=sys.stderr)
            sys.exit(1)
        print("token: ready")
        sys.exit(0)
    print("ใช้: python secrets_util.py --ensure   (สร้างไฟล์ token ถ้ายังไม่มี ไม่แสดงค่า)", file=sys.stderr)
    sys.exit(2)
