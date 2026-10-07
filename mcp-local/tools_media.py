# -*- coding: utf-8 -*-
"""เครื่องมือสื่อ (วิดีโอ/เสียง) สำหรับ MCP server "Local Computer" — ใช้ FFmpeg/FFprobe

stdlib ล้วน ไม่มี third-party import ทุกฟังก์ชันสาธารณะคืนค่าเป็น "สตริง" เสมอ
ถ้าผิดพลาดจะคืนสตริงที่ขึ้นต้นด้วย "ERROR: " ไม่โยน exception ออกไปหาผู้เรียก

ตำแหน่ง FFmpeg ที่แนะนำ
----------------------
  * build "essentials" ของ gyan.dev (64-bit, มี libx264/libx265/libvpx/aac/libmp3lame ครบ)
    แตกไว้ที่ C:\\LLM\\tools\\ffmpeg\\bin\\ (ffmpeg.exe + ffprobe.exe) หรือให้อยู่ใน PATH
  * ตัวสำรองที่อาจเจอบนเครื่อง แต่เก่าและไม่ครบ จึงถูกจัดลำดับไว้ท้ายสุด:
        C:\\KMPlayer\\ffmpeg.exe                     (เวอร์ชัน N-76347 ปี 2015, ไม่มี ffprobe)
        %LOCALAPPDATA%\\Apps\\2.0\\...\\ffmpeg32\\    (เวอร์ชัน 4.0.2, 32-bit, ClickOnce
                                                      path เปลี่ยนเองได้ทุกครั้งที่แอปอัปเดต)

โมดูลนี้จึง "ไม่" ฝังสมมติฐานว่าติดตั้ง ffmpeg ไว้แล้ว แต่จะค้นหาตอนเรียกใช้ทุกครั้ง
ผ่าน _ffmpeg() / _ffprobe() ถ้าหาไม่เจอจะคืนข้อความ ERROR ภาษาไทยพร้อมวิธีติดตั้ง

ถ้าย้ายหรืออัปเกรด ffmpeg ให้ตั้งตัวแปรสภาพแวดล้อมทับได้เลย
    MCP_LOCAL_FFMPEG=D:\\tools\\ffmpeg\\bin\\ffmpeg.exe
    MCP_LOCAL_FFPROBE=D:\\tools\\ffmpeg\\bin\\ffprobe.exe
"""
from __future__ import annotations

import functools
import glob
import inspect
import json
import os
import re
import subprocess
import threading

import guard

# confirm_token ของคำขอปัจจุบัน — _tool ดึงออกจาก kwargs มาเก็บไว้ที่นี่
# เพื่อให้ _write_path เรียกใช้ได้โดยไม่ต้องเพิ่มพารามิเตอร์ให้ทุกเครื่องมือ
_CTX = threading.local()

# ---------------------------------------------------------------------------
# ค่าคงที่
# ---------------------------------------------------------------------------

TIMEOUT = 900          # วินาที ตามข้อกำหนด งานยาวกว่านี้ให้ตัดคลิปให้สั้นลงก่อน
STDERR_TAIL = 1500     # จำนวนตัวอักษรท้าย stderr ที่ส่งกลับเมื่อ ffmpeg ล้มเหลว

# flag ของ Windows กันไม่ให้มีหน้าต่าง console เด้งขึ้นมาตอนรัน ffmpeg
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# โฟลเดอร์ที่จะไล่หา binary เรียงตาม "คุณภาพของ build" จากดีที่สุดไปแย่ที่สุด
# รายการที่มี * จะถูกขยายด้วย glob ตอนเรียกใช้
_CANDIDATE_DIRS = (
    # ตำแหน่งของสแตกนี้ก่อน แล้วค่อยตำแหน่งมาตรฐานทั่วไป
    r"C:\LLM\tools\ffmpeg\bin",
    r"C:\ffmpeg\bin",
    r"C:\ffmpeg",
    r"C:\tools\ffmpeg\bin",
    r"C:\Program Files\ffmpeg\bin",
    r"C:\Program Files (x86)\ffmpeg\bin",
    r"%LOCALAPPDATA%\Microsoft\WinGet\Links",
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*\ffmpeg*\bin",
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*\bin",
    r"%ProgramData%\chocolatey\bin",
    r"%USERPROFILE%\scoop\shims",
    # ของแถมจากโปรแกรมอื่น เก่ากว่ามาก ใช้เป็นทางเลือกสุดท้าย
    r"C:\Program Files\TechSmith\*\*",
    r"C:\KMPlayer",
    r"%LOCALAPPDATA%\Apps\2.0\*\*\*\ffmpeg32",
)

_INSTALL_HINT = (
    "  วิธีทำให้ใช้งานได้ (เลือกอย่างใดอย่างหนึ่ง)\n"
    "    1) ติดตั้งผ่าน winget:  winget install --id Gyan.FFmpeg\n"
    "    2) ดาวน์โหลด build จาก https://www.gyan.dev/ffmpeg/builds/ แล้วแตกไฟล์ไว้ที่ C:\\ffmpeg\\bin\n"
    "    3) ถ้ามี ffmpeg อยู่แล้วที่อื่น ให้ตั้งตัวแปรสภาพแวดล้อม\n"
    "       MCP_LOCAL_FFMPEG / MCP_LOCAL_FFPROBE ชี้ไปที่ไฟล์ .exe โดยตรง\n"
    "  หมายเหตุ: สแตกนี้มองหาที่ C:\\LLM\\tools\\ffmpeg\\bin\\ ก่อนตำแหน่งอื่น"
)

# นามสกุลที่ถือว่าเป็นภาพนิ่ง (ใช้ตัดสินว่าจะ encode ด้วย libx264 หรือไม่)
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}

# แผนที่นามสกุลไฟล์เสียง -> อาร์กิวเมนต์ encoder
_AUDIO_ENC = {
    ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    ".m4a": ["-c:a", "aac", "-b:a", "192k"],
    ".aac": ["-c:a", "aac", "-b:a", "192k"],
    ".wav": ["-c:a", "pcm_s16le"],
    ".flac": ["-c:a", "flac"],
    ".opus": ["-c:a", "libopus", "-b:a", "128k"],
    ".ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    ".mka": ["-c:a", "copy"],
}

# codec ที่ยอมให้ส่งเข้ามาได้ใน media_transcode (กันการยัด flag ปลอมเข้า argv)
_CODEC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+\-]*$")

# รูปแบบเวลาที่ยอมรับ: "12", "12.5", "1:23", "01:02:03.5"
_TIME_RE = re.compile(r"^(?:\d+(?:\.\d+)?|(?:\d{1,2}:)?\d{1,2}:\d{1,2}(?:\.\d+)?)$")

_BIN_CACHE: dict[str, str] = {}


# ---------------------------------------------------------------------------
# การค้นหา binary
# ---------------------------------------------------------------------------

def _which(name: str) -> str | None:
    """หา name.exe ใน PATH โดยไม่ต้องพึ่ง shutil.which ที่อาจเจอ shim แปลกๆ"""
    exe = name if name.lower().endswith(".exe") else name + ".exe"
    for raw in (os.environ.get("PATH") or "").split(os.pathsep):
        raw = raw.strip().strip('"')
        if not raw:
            continue
        try:
            cand = os.path.join(raw, exe)
            if os.path.isfile(cand):
                return os.path.abspath(cand)
        except (OSError, ValueError):
            continue
    return None


def _resolve(name: str, env_var: str) -> str | None:
    """คืน path เต็มของ ffmpeg/ffprobe หรือ None ถ้าไม่พบ

    ลำดับการค้น: ตัวแปรสภาพแวดล้อม -> PATH -> โฟลเดอร์ผู้สมัครตาม _CANDIDATE_DIRS
    ผลลัพธ์ที่ "เจอ" เท่านั้นที่ถูก cache ไว้ ถ้ายังไม่เจอจะค้นใหม่ทุกครั้ง
    เพื่อให้ติดตั้ง ffmpeg ระหว่างที่ server ทำงานอยู่แล้วใช้ได้เลยโดยไม่ต้อง restart
    """
    hit = _BIN_CACHE.get(name)
    if hit and os.path.isfile(hit):
        return hit
    _BIN_CACHE.pop(name, None)

    override = (os.environ.get(env_var) or "").strip().strip('"')
    if override:
        if os.path.isdir(override):
            override = os.path.join(override, name + ".exe")
        if os.path.isfile(override):
            found = os.path.abspath(override)
            _BIN_CACHE[name] = found
            return found

    found = _which(name)
    if found:
        _BIN_CACHE[name] = found
        return found

    exe = name + ".exe"
    for pattern in _CANDIDATE_DIRS:
        expanded = os.path.expandvars(pattern)
        if "%" in expanded:          # ขยายตัวแปรไม่สำเร็จ ข้ามไป
            continue
        try:
            dirs = glob.glob(expanded) if ("*" in expanded or "?" in expanded) else [expanded]
        except (OSError, ValueError):
            continue
        for d in dirs:
            try:
                cand = os.path.join(d, exe)
                if os.path.isfile(cand):
                    found = os.path.abspath(cand)
                    _BIN_CACHE[name] = found
                    return found
            except (OSError, ValueError):
                continue
    return None


def _ffmpeg() -> str | None:
    """คืน path ของ ffmpeg.exe หรือ None — เรียกใหม่ทุกครั้งที่ใช้เครื่องมือ"""
    return _resolve("ffmpeg", "MCP_LOCAL_FFMPEG")


def _ffprobe() -> str | None:
    """คืน path ของ ffprobe.exe หรือ None — เรียกใหม่ทุกครั้งที่ใช้เครื่องมือ"""
    return _resolve("ffprobe", "MCP_LOCAL_FFPROBE")


def _missing(binname: str) -> str:
    return ("ERROR: ไม่พบ %s บนเครื่องนี้ จึงใช้เครื่องมือสื่อไม่ได้\n%s"
            % (binname, _INSTALL_HINT))


# ---------------------------------------------------------------------------
# ตัวช่วยทั่วไป
# ---------------------------------------------------------------------------

def _tail(text: str, limit: int = STDERR_TAIL) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return "...(ตัดส่วนต้นออก)...\n" + text[-limit:]


def _decode(raw: bytes) -> str:
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace")


def _run(argv: list[str]) -> tuple[int, str, str]:
    """รันคำสั่งด้วย argv list (ไม่ใช้ shell=True เด็ดขาด)

    คืน (returncode, stdout, stderr) โดย rc = -1 เมื่อหมดเวลา และ -2 เมื่อรันไม่ขึ้น
    """
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=TIMEOUT,
            creationflags=_NO_WINDOW,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        return -1, _decode(exc.stdout or b""), _decode(exc.stderr or b"")
    except (OSError, ValueError) as exc:
        return -2, "", "%s: %s" % (type(exc).__name__, exc)
    return proc.returncode, _decode(proc.stdout), _decode(proc.stderr)


def _fail(rc: int, stderr: str, what: str) -> str:
    if rc == -1:
        return ("ERROR: %s ใช้เวลาเกิน %d วินาที จึงถูกยกเลิก\n"
                "  ลองตัดคลิปให้สั้นลงด้วย media_trim ก่อน แล้วค่อยประมวลผลทีละท่อน\n"
                "%s" % (what, TIMEOUT, _tail(stderr)))
    if rc == -2:
        return "ERROR: เรียก ffmpeg ไม่สำเร็จ — %s" % _tail(stderr, 500)
    return "ERROR: %s ล้มเหลว (exit code %d)\n--- ffmpeg stderr (ท้ายสุด) ---\n%s" % (
        what, rc, _tail(stderr))


def _human_size(n: float) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.2f %s" % (n, unit))
        n /= 1024.0
    return "?"


def _hms(seconds: float) -> str:
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return "?"
    if seconds < 0:
        return "?"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return "%02d:%02d:%02d.%02d" % (h, m, s, int(round((seconds - int(seconds)) * 100)) % 100)


def _fps(rate: str | None) -> str:
    if not rate or "/" not in str(rate):
        return "?"
    try:
        num, den = str(rate).split("/", 1)
        den_f = float(den)
        if den_f == 0:
            return "?"
        return "%.2f" % (float(num) / den_f)
    except (TypeError, ValueError):
        return "?"


def _time_arg(value, label: str) -> str:
    """ตรวจว่าค่าเวลาเป็นตัวเลขหรือ HH:MM:SS จริง

    สำคัญด้านความปลอดภัย: ค่านี้ถูกส่งเข้า argv ของ ffmpeg ถ้าปล่อยให้เป็น
    "-i" หรือ "-f" ได้ มันจะกลายเป็น flag แทนที่จะเป็นค่าเวลา
    """
    text = str(value).strip()
    if not text:
        raise ValueError("%s ว่างเปล่า" % label)
    if not _TIME_RE.match(text):
        raise ValueError("%s ต้องเป็นวินาที (เช่น 5 หรือ 12.5) หรือรูปแบบ HH:MM:SS "
                         "(เช่น 00:01:30) แต่ได้รับ %r" % (label, text))
    return text


def _positive_number(value, label: str, minimum: float, maximum: float) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s ต้องเป็นตัวเลข แต่ได้รับ %r" % (label, value)) from None
    if not (minimum <= num <= maximum):
        raise ValueError("%s ต้องอยู่ระหว่าง %g ถึง %g แต่ได้รับ %g" % (label, minimum, maximum, num))
    return num


def _codec_arg(value, label: str) -> str:
    text = str(value).strip()
    if not _CODEC_RE.match(text):
        raise ValueError("%s ไม่ถูกต้อง: %r (ใช้ได้เฉพาะชื่อ codec เช่น libx264, libx265, "
                         "aac, libmp3lame, copy)" % (label, text))
    return text


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on", "จริง")
    return bool(value)


# นามสกุล/หัวไฟล์ของ "รายการเล่น/สคริปต์ต่อไฟล์" ที่ ffmpeg จะไล่เปิดไฟล์อื่นต่อให้เอง
# (m3u8/HLS, ffconcat, playlist) — อันตรายด้านความปลอดภัย: ไฟล์ในโปรเจกต์เราชี้ไปดูดไฟล์
# ของโปรเจกต์อื่นหรือไฟล์ในเครื่อง (พิสูจน์แล้วว่า HLS ดึงไฟล์ข้ามโปรเจกต์ได้ — กฎ S04)
# หรือชี้ URL ภายในเครือข่าย (SSRF) เครื่องมือสื่อมีไว้จัดการ "ไฟล์สื่อจริง" ไม่ใช่รายการอ้อม
# เพิ่มรอบ FIXER: manifest ของ DASH (.mpd) / HDS (.f4m) / Smooth (.ism) / SMIL และ SDP (.sdp)
# ซึ่ง ffmpeg ก็ไล่เปิด URL/ไฟล์อื่นต่อเหมือนกัน (SDP เปิดสตรีม RTP/UDP ในเครือข่าย)
_INDIRECT_EXT = {".m3u", ".m3u8", ".ffconcat", ".concat", ".pls", ".asx", ".xspf", ".cue", ".vlc",
                 ".mpd", ".f4m", ".ism", ".isml", ".smil", ".sdp"}
_INDIRECT_HEADERS = ("#EXTM3U", "#EXT-X-", "FFCONCAT", "FILE '", 'FILE "', "[PLAYLIST]",
                     "<ASX", "<PLAYLIST", "#EXTINF", "<?XML", "<MPD", "<SMIL", "<SMOOTHSTREAMING",
                     "V=0")

# -protocol_whitelist file: ffmpeg เปิดได้เฉพาะไฟล์ในเครื่อง ห้ามตาม http/rtp/udp/tcp/concat:/subfile:
# ที่ไฟล์สื่อ (หรือ manifest ที่หลุด _reject_indirection มา) สั่งให้เปิดต่อ — เป็นด่านชั้นที่สองของ
# ข้อ "ffmpeg ไปเปิดไฟล์/URL อื่น" (audit) ffmpeg รุ่นเก่ามาก (ก่อน 3.0 เช่นของ KMPlayer ปี 2015)
# ไม่รู้จักตัวเลือกนี้ จึงลองก่อนหนึ่งครั้งต่อไฟล์ .exe แล้วจำผลไว้ ถ้าไม่รองรับก็เหลือด่านแรกด่านเดียว
_PW_CACHE: dict[str, bool] = {}


def _input_guard(exe: str) -> list[str]:
    """ตัวเลือกขาเข้าที่ต้องใส่ก่อน -i ทุกครั้ง (คืน [] ถ้า ffmpeg/ffprobe ตัวนี้ไม่รองรับ)"""
    try:
        st = os.stat(exe)
        key = "%s|%d|%d" % (os.path.normcase(exe), st.st_mtime_ns, st.st_size)
    except OSError:
        return []
    ok = _PW_CACHE.get(key)
    if ok is None:
        rc, _out, _err = _run([exe, "-hide_banner", "-protocol_whitelist", "file", "-version"])
        ok = rc == 0
        _PW_CACHE[key] = ok
    return ["-protocol_whitelist", "file"] if ok else []


def _reject_indirection(resolved: str) -> None:
    """ปฏิเสธไฟล์ที่เป็นรายการเล่น/สคริปต์ต่อไฟล์ ซึ่งทำให้ ffmpeg ไปเปิดไฟล์อื่นต่อ"""
    ext = os.path.splitext(resolved)[1].lower()
    if ext in _INDIRECT_EXT:
        raise ValueError("ไฟล์ชนิดรายการเล่น/สคริปต์ต่อไฟล์ (%s) ไม่รองรับ เพราะมันสั่งให้ "
                         "ffmpeg ไปเปิดไฟล์อื่นต่อ (ข้ามขอบเขตโปรเจกต์/เข้าถึงไฟล์ในเครื่องได้) "
                         "ให้ใช้ไฟล์สื่อจริงโดยตรง" % (ext or "ไม่มีนามสกุล"))
    try:
        with open(resolved, "rb") as fh:
            head = fh.read(256)
    except OSError:
        return
    if b"\x00" in head:                 # ไฟล์ไบนารี (สื่อจริง) ไม่ใช่รายการเล่นข้อความ
        return
    probe = head.lstrip().decode("ascii", "ignore").upper()
    if any(probe.startswith(sig) or sig in probe[:64] for sig in _INDIRECT_HEADERS):
        raise ValueError("เนื้อไฟล์นี้เป็นรายการเล่น/สคริปต์ต่อไฟล์ (playlist/ffconcat) ซึ่งสั่งให้ "
                         "ffmpeg ไปเปิดไฟล์อื่นต่อ จึงไม่รองรับ ให้ใช้ไฟล์สื่อจริงโดยตรง")


def _read_path(path) -> str:
    """ผ่าน guard.check_read แล้วยืนยันว่าเป็นไฟล์จริง (และไม่ใช่รายการเล่นที่อ้อมไปไฟล์อื่น)"""
    if not str(path or "").strip():
        raise ValueError("ไม่ได้ระบุ path ของไฟล์ต้นทาง")
    resolved = guard.check_read(str(path))
    if not os.path.exists(resolved):
        raise ValueError("ไม่พบไฟล์ต้นทาง: %s" % resolved)
    if not os.path.isfile(resolved):
        raise ValueError("path ต้นทางไม่ใช่ไฟล์: %s" % resolved)
    _reject_indirection(resolved)
    return resolved


def _overwrite_review(resolved: str) -> str:
    """ข้อความตรวจทาน (รอบ review R1) ของการเขียนทับไฟล์สื่อ = พารามิเตอร์ทั้งชุดของการเรียกนี้ที่ normalize แล้ว
    (ชุดเดียวกับที่ token ผูกอยู่ผ่าน _CTX.op) + ไฟล์ที่จะถูกแทนที่ — คนเห็นในกล่องอนุญาตว่าตัด/แปลงอะไร ทับไฟล์ไหน"""
    lines = ["[media] เขียนทับไฟล์สื่อด้วยผลของ ffmpeg",
             "ไฟล์ที่จะถูกแทนที่: %s (%s)" % (resolved, _human_size(_size_of(resolved)))]
    try:
        op = json.loads(getattr(_CTX, "op", "") or "{}")
    except ValueError:
        op = {}
    if isinstance(op, dict) and op:
        lines.append("เครื่องมือ: %s" % op.get("tool", "?"))
        lines.append("พารามิเตอร์:")
        for k in sorted(op):
            if k != "tool":
                lines.append("  %s = %s" % (k, json.dumps(op[k], ensure_ascii=False, default=str)))
    return "\n".join(lines)


def _write_path(out, overwrite, src: str | None = None) -> str:
    """ผ่าน guard.check_write, กันเขียนทับ, กันเขียนทับไฟล์ต้นทาง, สร้างโฟลเดอร์ปลายทาง"""
    if not str(out or "").strip():
        raise ValueError("ไม่ได้ระบุ path ของไฟล์ปลายทาง (out)")
    resolved = guard.check_write(str(out))
    if src and os.path.normcase(os.path.abspath(resolved)) == os.path.normcase(os.path.abspath(src)):
        raise ValueError("ไฟล์ปลายทางซ้ำกับไฟล์ต้นทาง — ffmpeg เขียนทับตัวเองไม่ได้ "
                         "กรุณาตั้งชื่อไฟล์ผลลัพธ์ใหม่")
    if os.path.exists(resolved):
        if not _truthy(overwrite):
            raise ValueError("มีไฟล์ %s อยู่แล้ว จึงไม่เขียนทับ "
                             "ถ้าต้องการเขียนทับจริงให้ส่ง overwrite=true" % resolved)
        # การเขียนทับลบไฟล์เดิมของผู้ใช้ทิ้ง จึงต้องผ่านการยืนยันสองขั้นตาม S03
        action = "media_overwrite:%s" % resolved.lower()
        op_detail = "%s\n%s" % (resolved, getattr(_CTX, "op", ""))
        token = getattr(_CTX, "token", "")
        if not token or not guard.consume_confirm(token, action, op_detail):
            raise ValueError(guard.confirm_hint(
                guard.need_confirm(action, op_detail, review=_overwrite_review(resolved)),
                "เขียนทับไฟล์สื่อ",
                "%s (%s) จะถูกแทนที่ด้วยไฟล์ใหม่" % (resolved, _human_size(_size_of(resolved)))))
    parent = os.path.dirname(resolved)
    if parent:
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as exc:
            raise ValueError("สร้างโฟลเดอร์ปลายทางไม่ได้: %s" % exc) from None
    return resolved


def _size_of(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return -1


def _produced(out: str) -> bool:
    """ffmpeg อาจ exit 0 แต่ได้ไฟล์เปล่า จึงต้องเช็คขนาดด้วย"""
    return _size_of(out) > 0


def _result_line(out: str, src: str | None = None, note: str = "") -> str:
    size = _size_of(out)
    text = "OK: สร้างไฟล์ %s แล้ว (%s)" % (out, _human_size(size))
    if src:
        before = _size_of(src)
        if before > 0 and size > 0:
            pct = (1.0 - (size / float(before))) * 100.0
            text += "\n  ขนาดเดิม %s -> ใหม่ %s (%s %.1f%%)" % (
                _human_size(before), _human_size(size),
                "เล็กลง" if pct >= 0 else "ใหญ่ขึ้น", abs(pct))
    if note:
        text += "\n  " + note
    return text


def _base(ff: str) -> list[str]:
    """อาร์กิวเมนต์พื้นฐานของทุกคำสั่ง ffmpeg

    -nostdin กัน ffmpeg ค้างรอ input, -y ปลอดภัยเพราะเราเช็คการเขียนทับเองไปแล้ว
    -protocol_whitelist (ถ้ารองรับ) เป็นตัวเลือกขาเข้า มีผลกับ -i ตัวถัดไป ซึ่งทุกคำสั่งมีแค่ตัวเดียว
    """
    return [ff, "-hide_banner", "-nostdin", "-loglevel", "warning", "-y"] + _input_guard(ff)


def _describe_args(fn, args, kwargs) -> dict:
    try:
        bound = inspect.signature(fn).bind(*args, **kwargs)
        bound.apply_defaults()
        return {k: (v if isinstance(v, (int, float, bool, type(None))) else str(v))
                for k, v in bound.arguments.items()}
    except (TypeError, ValueError):
        return {"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in kwargs.items()}}


def _tool(fn):
    """ครอบทุกเครื่องมือ: บันทึก audit หนึ่งบรรทัดต่อการเรียกหนึ่งครั้ง
    และแปลงทุก exception เป็นสตริง "ERROR: ..." ไม่ให้หลุดไปหาผู้เรียก
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        _CTX.token = str(kwargs.pop("confirm_token", "") or "")
        detail = _describe_args(fn, args, kwargs)
        # อาร์กิวเมนต์ทั้งชุดของการเรียกนี้ ใช้ผูก confirm_token ของการเขียนทับ
        # (อนุมัติ "ตัดช่วง 0-5 วิ" แล้วเอา token ไปใช้กับ "ตัดช่วงอื่น" ทับไฟล์เดิมไม่ได้)
        _CTX.op = json.dumps({"tool": fn.__name__, **detail}, sort_keys=True,
                             ensure_ascii=False, default=str)
        try:
            text = fn(*args, **kwargs)
        except guard.Denied as exc:
            text = "ERROR: ถูกปฏิเสธการเข้าถึงไฟล์ — %s" % exc
        except ValueError as exc:
            text = "ERROR: %s" % exc
        except Exception as exc:                    # ตาข่ายกันตกชั้นสุดท้าย
            text = "ERROR: %s: %s" % (type(exc).__name__, exc)
        if not isinstance(text, str):
            text = str(text)
        try:
            detail["ok"] = not text.startswith("ERROR:")
            detail["result"] = guard.scrub_text(text)[:300]    # ไม่ให้ confirm_token ตกลง audit.log
            guard.audit(fn.__name__, detail)
        except Exception:
            pass
        return text
    return wrapper


# ---------------------------------------------------------------------------
# เครื่องมือ
# ---------------------------------------------------------------------------

@_tool
def media_probe(path: str) -> str:
    """อ่านข้อมูลไฟล์สื่อ: ความยาว สตรีม codec ความละเอียด บิตเรต ขนาดไฟล์"""
    src = _read_path(path)
    fp = _ffprobe()
    if not fp:
        # เครื่องนี้มีเคสที่มี ffmpeg แต่ไม่มี ffprobe (เช่น C:\KMPlayer)
        # จึงถอยไปอ่านข้อมูลจาก stderr ของ ffmpeg -i แทน ดีกว่าคืน ERROR เปล่าๆ
        ff = _ffmpeg()
        if not ff:
            return _missing("ffprobe และ ffmpeg")
        rc, _, err = _run([ff, "-hide_banner", "-nostdin"] + _input_guard(ff) + ["-i", src])
        if rc == -1 or rc == -2:
            return _fail(rc, err, "การอ่านข้อมูลไฟล์")
        return ("ไม่พบ ffprobe จึงอ่านข้อมูลคร่าวๆ จาก ffmpeg แทน (ข้อมูลอาจไม่ครบ)\n"
                "ไฟล์: %s\nขนาด: %s\n--- ffmpeg ---\n%s"
                % (src, _human_size(_size_of(src)), _tail(err)))

    rc, out, err = _run([fp, "-v", "error"] + _input_guard(fp) + ["-print_format", "json",
                                                                   "-show_format", "-show_streams", src])
    if rc != 0:
        return _fail(rc, err or out, "ffprobe")
    try:
        data = json.loads(out)
    except ValueError:
        return "ERROR: ffprobe คืนข้อมูลที่อ่านไม่ได้\n%s" % _tail(out)

    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    lines = ["ไฟล์: %s" % src,
             "ขนาด: %s (%s bytes)" % (_human_size(fmt.get("size") or _size_of(src)),
                                      fmt.get("size") or _size_of(src)),
             "รูปแบบคอนเทนเนอร์: %s" % (fmt.get("format_long_name")
                                        or fmt.get("format_name") or "?")]
    if fmt.get("duration"):
        lines.append("ความยาว: %s (%.3f วินาที)"
                     % (_hms(fmt["duration"]), float(fmt["duration"])))
    else:
        lines.append("ความยาว: ไม่มี (น่าจะเป็นภาพนิ่งหรือสตรีมที่ไม่ระบุความยาว)")
    if fmt.get("bit_rate"):
        try:
            lines.append("บิตเรตรวม: %d kbps" % (int(fmt["bit_rate"]) // 1000))
        except (TypeError, ValueError):
            pass
    lines.append("จำนวนสตรีม: %d" % len(streams))

    for st in streams:
        kind = st.get("codec_type", "?")
        desc = [st.get("codec_name", "?")]
        if st.get("profile"):
            desc.append("(%s)" % st["profile"])
        if kind == "video":
            desc.append("%sx%s" % (st.get("width", "?"), st.get("height", "?")))
            rate = st.get("avg_frame_rate") or st.get("r_frame_rate")
            if _fps(rate) != "?":
                desc.append("%s fps" % _fps(rate))
            if st.get("pix_fmt"):
                desc.append("pix_fmt=%s" % st["pix_fmt"])
            if st.get("display_aspect_ratio"):
                desc.append("DAR %s" % st["display_aspect_ratio"])
        elif kind == "audio":
            if st.get("sample_rate"):
                desc.append("%s Hz" % st["sample_rate"])
            if st.get("channel_layout"):
                desc.append(str(st["channel_layout"]))
            elif st.get("channels"):
                desc.append("%s ช่อง" % st["channels"])
        if st.get("bit_rate"):
            try:
                desc.append("%d kbps" % (int(st["bit_rate"]) // 1000))
            except (TypeError, ValueError):
                pass
        lang = (st.get("tags") or {}).get("language")
        if lang:
            desc.append("lang=%s" % lang)
        lines.append("  สตรีม %s [%s]: %s" % (st.get("index", "?"), kind, " ".join(desc)))
    return "\n".join(lines)


@_tool
def media_trim(path: str, start: str, duration: str, out: str, overwrite: bool = False) -> str:
    """ตัดคลิปช่วงหนึ่งออกมา พยายามใช้ -c copy (ไม่เข้ารหัสใหม่) ก่อนเสมอ"""
    ff = _ffmpeg()
    if not ff:
        return _missing("ffmpeg")
    src = _read_path(path)
    ss = _time_arg(start, "start")
    dur = _time_arg(duration, "duration")
    dst = _write_path(out, overwrite, src)

    # รอบแรก: คัดลอกสตรีมตรงๆ เร็วและไม่เสียคุณภาพ
    rc, _, err = _run(_base(ff) + ["-ss", ss, "-i", src, "-t", dur,
                                   "-c", "copy", "-avoid_negative_ts", "make_zero", dst])
    if rc == 0 and _produced(dst):
        return _result_line(dst, note="ใช้โหมด -c copy จึงไม่มีการเข้ารหัสใหม่ "
                                      "(จุดตัดจะขยับไปที่ keyframe ที่ใกล้ที่สุด)")
    if rc in (-1, -2):
        return _fail(rc, err, "การตัดคลิป")

    # รอบสอง: คอนเทนเนอร์ปลายทางไม่รับ codec เดิม ต้องเข้ารหัสใหม่
    copy_err = err
    rc2, _, err2 = _run(_base(ff) + ["-ss", ss, "-i", src, "-t", dur,
                                     "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
                                     "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", dst])
    if rc2 != 0 or not _produced(dst):
        return ("ERROR: ตัดคลิปไม่สำเร็จทั้งแบบ copy และแบบเข้ารหัสใหม่\n"
                "--- รอบ copy ---\n%s\n--- รอบเข้ารหัสใหม่ (exit %d) ---\n%s"
                % (_tail(copy_err, 500), rc2, _tail(err2)))
    return _result_line(dst, note="คัดลอกสตรีมตรงๆ ไม่ได้ จึงเข้ารหัสใหม่เป็น H.264/AAC ให้แทน")


@_tool
def media_resize(path: str, width: int, out: str, overwrite: bool = False) -> str:
    """ย่อ/ขยายวิดีโอตามความกว้างที่กำหนด โดยคงสัดส่วนภาพเดิม"""
    ff = _ffmpeg()
    if not ff:
        return _missing("ffmpeg")
    src = _read_path(path)
    w = int(_positive_number(width, "width", 2, 7680))
    if w % 2:                       # H.264 yuv420p ต้องการด้านคู่
        w -= 1
    dst = _write_path(out, overwrite, src)

    if os.path.splitext(src)[1].lower() in _IMAGE_EXT:
        rc, _, err = _run(_base(ff) + ["-i", src, "-vf", "scale=%d:-1" % w, dst])
        if rc != 0 or not _produced(dst):
            return _fail(rc, err, "การย่อขนาดภาพ")
        return _result_line(dst, src, "ย่อภาพนิ่งเป็นความกว้าง %d px" % w)

    # scale=w:-2 คือคงสัดส่วนและบังคับความสูงให้เป็นเลขคู่
    vf = "scale=%d:-2:flags=lanczos" % w
    common = ["-i", src, "-vf", vf, "-c:v", "libx264", "-crf", "23",
              "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    rc, _, err = _run(_base(ff) + common + ["-c:a", "copy", dst])
    if rc == 0 and _produced(dst):
        return _result_line(dst, src, "ความกว้าง %d px คงสัดส่วนเดิม เสียงคัดลอกมาทั้งดุ้น" % w)
    if rc in (-1, -2):
        return _fail(rc, err, "การย่อขนาดวิดีโอ")

    rc2, _, err2 = _run(_base(ff) + common + ["-c:a", "aac", "-b:a", "160k", dst])
    if rc2 != 0 or not _produced(dst):
        return _fail(rc2, err2 or err, "การย่อขนาดวิดีโอ")
    return _result_line(dst, src, "ความกว้าง %d px คงสัดส่วนเดิม (เสียงถูกเข้ารหัสใหม่เป็น AAC)" % w)


@_tool
def media_compress(path: str, out: str, crf: int = 28, overwrite: bool = False) -> str:
    """บีบอัดวิดีโอเป็น H.264 + AAC ค่า crf ยิ่งมากยิ่งเล็กแต่คุณภาพยิ่งลด"""
    ff = _ffmpeg()
    if not ff:
        return _missing("ffmpeg")
    src = _read_path(path)
    q = int(_positive_number(crf, "crf", 0, 51))
    dst = _write_path(out, overwrite, src)

    rc, _, err = _run(_base(ff) + ["-i", src,
                                   "-c:v", "libx264", "-crf", str(q), "-preset", "medium",
                                   "-pix_fmt", "yuv420p",
                                   "-c:a", "aac", "-b:a", "128k",
                                   "-movflags", "+faststart", dst])
    if rc != 0 or not _produced(dst):
        return _fail(rc, err, "การบีบอัดวิดีโอ")
    return _result_line(dst, src, "H.264 crf=%d + AAC 128k" % q)


@_tool
def media_extract_audio(path: str, out: str, overwrite: bool = False) -> str:
    """ดึงเฉพาะเสียงออกจากไฟล์ ชนิดเสียงเลือกจากนามสกุลของไฟล์ปลายทาง"""
    ff = _ffmpeg()
    if not ff:
        return _missing("ffmpeg")
    src = _read_path(path)
    dst = _write_path(out, overwrite, src)
    ext = os.path.splitext(dst)[1].lower()
    enc = _AUDIO_ENC.get(ext)
    if enc is None:
        enc = ["-c:a", "copy"]
        note = "นามสกุล %s ไม่อยู่ในรายการที่รู้จัก จึงคัดลอกสตรีมเสียงเดิมมาตรงๆ" % (ext or "(ไม่มี)")
    else:
        note = "เข้ารหัสเสียงตามนามสกุล %s" % ext

    rc, _, err = _run(_base(ff) + ["-i", src, "-vn", "-sn", "-dn"] + enc + [dst])
    if rc != 0 or not _produced(dst):
        extra = ""
        if "does not contain any stream" in (err or "") or "Output file" in (err or ""):
            extra = "\n  เป็นไปได้ว่าไฟล์ต้นทางไม่มีสตรีมเสียงเลย ลองใช้ media_probe ดูก่อน"
        return _fail(rc, err, "การดึงเสียง") + extra
    return _result_line(dst, note=note)


@_tool
def media_mute(path: str, out: str, overwrite: bool = False) -> str:
    """ทำสำเนาวิดีโอโดยตัดแทร็กเสียงออก ภาพคัดลอกมาตรงๆ ไม่เสียคุณภาพ"""
    ff = _ffmpeg()
    if not ff:
        return _missing("ffmpeg")
    src = _read_path(path)
    dst = _write_path(out, overwrite, src)

    rc, _, err = _run(_base(ff) + ["-i", src, "-an", "-c", "copy", dst])
    if rc == 0 and _produced(dst):
        return _result_line(dst, src, "ตัดเสียงออกแล้ว ภาพใช้ -c copy จึงไม่เสียคุณภาพ")
    if rc in (-1, -2):
        return _fail(rc, err, "การตัดเสียงออก")

    rc2, _, err2 = _run(_base(ff) + ["-i", src, "-an",
                                     "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
                                     "-pix_fmt", "yuv420p", dst])
    if rc2 != 0 or not _produced(dst):
        return _fail(rc2, err2 or err, "การตัดเสียงออก")
    return _result_line(dst, src, "ตัดเสียงออกแล้ว (คัดลอกภาพตรงๆ ไม่ได้ จึงเข้ารหัสใหม่เป็น H.264)")


@_tool
def media_to_gif(path: str, out: str, start: str = "0", duration: float = 3,
                 fps: int = 12, width: int = 480, overwrite: bool = False) -> str:
    """แปลงช่วงหนึ่งของวิดีโอเป็น GIF ด้วยวิธี palettegen/paletteuse ให้สีสวย"""
    ff = _ffmpeg()
    if not ff:
        return _missing("ffmpeg")
    src = _read_path(path)
    ss = _time_arg(start, "start")
    dur = _time_arg(duration, "duration")
    f = int(_positive_number(fps, "fps", 1, 50))
    w = int(_positive_number(width, "width", 16, 1920))
    dst = _write_path(out, overwrite, src)

    warn = ""
    try:
        if float(dur) > 30:
            warn = "\n  หมายเหตุ: ช่วงยาวเกิน 30 วินาที GIF จะไฟล์ใหญ่มาก แนะนำให้สั้นกว่านี้"
    except ValueError:
        pass
    if os.path.splitext(dst)[1].lower() != ".gif":
        warn += "\n  หมายเหตุ: ไฟล์ปลายทางไม่ได้ลงท้ายด้วย .gif แต่เนื้อในเป็น GIF"

    chain = ("fps=%d,scale=%d:-1:flags=lanczos,split[a][b];"
             "[a]palettegen=stats_mode=diff[p];"
             "[b][p]paletteuse=dither=bayer:bayer_scale=3" % (f, w))
    rc, _, err = _run(_base(ff) + ["-ss", ss, "-t", dur, "-i", src,
                                   "-filter_complex", chain,
                                   "-loop", "0", "-f", "gif", dst])
    if rc != 0 or not _produced(dst):
        return _fail(rc, err, "การแปลงเป็น GIF")
    return _result_line(dst, note="เริ่มที่ %s ยาว %s วินาที, %d fps, กว้าง %d px%s"
                                  % (ss, dur, f, w, warn))


@_tool
def media_transcode(path: str, out: str, vcodec: str = "libx264",
                    acodec: str = "aac", overwrite: bool = False) -> str:
    """แปลงไฟล์ไปยัง codec/คอนเทนเนอร์อื่น ระบุ codec เองได้ ใช้ copy เพื่อคัดลอกสตรีมเดิม"""
    ff = _ffmpeg()
    if not ff:
        return _missing("ffmpeg")
    src = _read_path(path)
    vc = _codec_arg(vcodec, "vcodec")
    ac = _codec_arg(acodec, "acodec")
    dst = _write_path(out, overwrite, src)

    argv = _base(ff) + ["-i", src]
    if vc.lower() in ("none", "no", "novideo"):
        argv += ["-vn"]
    else:
        argv += ["-c:v", vc]
        if vc in ("libx264", "libx265"):
            argv += ["-crf", "23", "-preset", "medium", "-pix_fmt", "yuv420p"]
    if ac.lower() in ("none", "no", "noaudio"):
        argv += ["-an"]
    else:
        argv += ["-c:a", ac]
        if ac == "aac":
            argv += ["-b:a", "160k"]
    argv.append(dst)

    rc, _, err = _run(argv)
    if rc != 0 or not _produced(dst):
        hint = ""
        if "Unknown encoder" in (err or "") or "Automatic encoder selection" in (err or ""):
            hint = ("\n  ffmpeg build บนเครื่องนี้อาจไม่มี encoder ตัวนั้น "
                    "ลองใช้ libx264 / libx265 / libvpx-vp9 สำหรับภาพ และ aac / libmp3lame / "
                    "libopus สำหรับเสียง")
        return _fail(rc, err, "การแปลง codec") + hint
    return _result_line(dst, src, "vcodec=%s, acodec=%s" % (vc, ac))


# ---------------------------------------------------------------------------
# ประกาศเครื่องมือให้ server shell
# ---------------------------------------------------------------------------

_OVERWRITE_PROP = {
    "type": "boolean",
    "description": "ถ้าไฟล์ปลายทางมีอยู่แล้วให้เขียนทับหรือไม่ ค่าเริ่มต้นคือ false (ไม่เขียนทับ)",
    "default": False,
}

TOOLS = [
    {
        "name": "media_probe",
        "description": ("อ่านรายละเอียดไฟล์วิดีโอหรือเสียง: ความยาว ขนาดไฟล์ บิตเรต "
                        "และรายการสตรีมพร้อม codec กับความละเอียด "
                        "ใช้ก่อนจะตัด ย่อ หรือบีบอัด เพื่อดูว่าไฟล์เป็นอย่างไร"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "path เต็มของไฟล์สื่อที่ต้องการตรวจสอบ"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "media_trim",
        "description": ("ตัดวิดีโอหรือเสียงเฉพาะช่วงที่ต้องการออกมาเป็นไฟล์ใหม่ "
                        "พยายามคัดลอกสตรีมตรงๆ (-c copy) จึงเร็วและไม่เสียคุณภาพ "
                        "ใช้เมื่อผู้ใช้อยากได้แค่บางช่วงของคลิป"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "path ของไฟล์ต้นทาง"},
                "start": {"type": "string",
                          "description": "จุดเริ่มต้น เป็นวินาที (เช่น \"12.5\") หรือ HH:MM:SS (เช่น \"00:01:30\")"},
                "duration": {"type": "string",
                             "description": "ความยาวที่ต้องการตัด เป็นวินาทีหรือ HH:MM:SS"},
                "out": {"type": "string", "description": "path ของไฟล์ผลลัพธ์ ควรใช้นามสกุลเดียวกับต้นทาง"},
                "overwrite": _OVERWRITE_PROP,
            },
            "required": ["path", "start", "duration", "out"],
        },
    },
    {
        "name": "media_resize",
        "description": ("ย่อหรือขยายวิดีโอให้ได้ความกว้างตามต้องการ โดยคงสัดส่วนภาพเดิม "
                        "และบังคับให้ด้านกว้างกับด้านสูงเป็นเลขคู่ "
                        "งานนี้ต้องเข้ารหัสใหม่จึงใช้เวลานาน ควรใช้กับคลิปสั้น "
                        "ถ้าคลิปยาวให้ใช้ media_trim ตัดก่อน"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "path ของไฟล์ต้นทาง"},
                "width": {"type": "integer",
                          "description": "ความกว้างที่ต้องการเป็นพิกเซล (2-7680) ความสูงคำนวณให้อัตโนมัติ"},
                "out": {"type": "string", "description": "path ของไฟล์ผลลัพธ์"},
                "overwrite": _OVERWRITE_PROP,
            },
            "required": ["path", "width", "out"],
        },
    },
    {
        "name": "media_compress",
        "description": ("บีบอัดวิดีโอให้ไฟล์เล็กลงด้วย H.264 + AAC ใช้เมื่อไฟล์ใหญ่เกินไปจะส่งหรืออัปโหลด "
                        "การบีบอัดกินเวลานาน (หมดเวลาที่ 900 วินาที) ควรใช้กับคลิปสั้น "
                        "ถ้าคลิปยาวให้ตัดด้วย media_trim เป็นท่อนๆ ก่อน"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "path ของไฟล์ต้นทาง"},
                "out": {"type": "string", "description": "path ของไฟล์ผลลัพธ์ แนะนำให้ลงท้ายด้วย .mp4"},
                "crf": {"type": "integer",
                        "description": "คุณภาพ 0-51 ยิ่งมากไฟล์ยิ่งเล็กแต่ภาพยิ่งแตก ค่าเริ่มต้น 28 "
                                       "(ใช้ 23 ถ้าอยากได้คุณภาพสูงกว่านี้)",
                        "default": 28},
                "overwrite": _OVERWRITE_PROP,
            },
            "required": ["path", "out"],
        },
    },
    {
        "name": "media_extract_audio",
        "description": ("ดึงเฉพาะแทร็กเสียงออกจากวิดีโอมาเป็นไฟล์เสียง "
                        "ชนิดเสียงเลือกจากนามสกุลของไฟล์ปลายทาง (.mp3 .m4a .wav .flac .opus .ogg) "
                        "ใช้เมื่อผู้ใช้อยากได้เฉพาะเสียงจากคลิป"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "path ของไฟล์วิดีโอต้นทาง"},
                "out": {"type": "string", "description": "path ของไฟล์เสียงผลลัพธ์ เช่น C:\\temp\\เสียง.mp3"},
                "overwrite": _OVERWRITE_PROP,
            },
            "required": ["path", "out"],
        },
    },
    {
        "name": "media_mute",
        "description": ("ทำสำเนาวิดีโอโดยตัดแทร็กเสียงทิ้ง ภาพถูกคัดลอกมาตรงๆ จึงเร็วและไม่เสียคุณภาพ "
                        "ใช้เมื่อต้องการวิดีโอเงียบ"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "path ของไฟล์วิดีโอต้นทาง"},
                "out": {"type": "string", "description": "path ของไฟล์ผลลัพธ์"},
                "overwrite": _OVERWRITE_PROP,
            },
            "required": ["path", "out"],
        },
    },
    {
        "name": "media_to_gif",
        "description": ("แปลงช่วงสั้นๆ ของวิดีโอเป็นภาพเคลื่อนไหว GIF ด้วยเทคนิค palette ให้สีสวย "
                        "GIF โตเร็วมากตามความยาวและความกว้าง ควรจำกัดไว้ไม่เกิน 5-10 วินาที "
                        "และกว้างไม่เกิน 640 px"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "path ของไฟล์วิดีโอต้นทาง"},
                "out": {"type": "string", "description": "path ของไฟล์ GIF ผลลัพธ์"},
                "start": {"type": "string",
                          "description": "จุดเริ่มต้น เป็นวินาทีหรือ HH:MM:SS ค่าเริ่มต้น \"0\"",
                          "default": "0"},
                "duration": {"type": "number",
                             "description": "ความยาวเป็นวินาที ค่าเริ่มต้น 3", "default": 3},
                "fps": {"type": "integer",
                        "description": "เฟรมต่อวินาทีของ GIF (1-50) ค่าเริ่มต้น 12", "default": 12},
                "width": {"type": "integer",
                          "description": "ความกว้างเป็นพิกเซล คงสัดส่วนเดิม ค่าเริ่มต้น 480",
                          "default": 480},
                "overwrite": _OVERWRITE_PROP,
            },
            "required": ["path", "out"],
        },
    },
    {
        "name": "media_transcode",
        "description": ("แปลงไฟล์สื่อไปเป็น codec หรือคอนเทนเนอร์อื่น เช่น MKV เป็น MP4 หรือ H.264 เป็น H.265 "
                        "ใส่ \"copy\" เพื่อคัดลอกสตรีมเดิมโดยไม่เข้ารหัสใหม่ "
                        "การเข้ารหัสใหม่ใช้เวลานาน ควรใช้กับคลิปสั้น"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "path ของไฟล์ต้นทาง"},
                "out": {"type": "string", "description": "path ของไฟล์ผลลัพธ์ นามสกุลเป็นตัวกำหนดคอนเทนเนอร์"},
                "vcodec": {"type": "string",
                           "description": "codec ภาพ เช่น libx264, libx265, libvpx-vp9, copy "
                                          "หรือ none เพื่อตัดภาพออก ค่าเริ่มต้น libx264",
                           "default": "libx264"},
                "acodec": {"type": "string",
                           "description": "codec เสียง เช่น aac, libmp3lame, libopus, copy "
                                          "หรือ none เพื่อตัดเสียงออก ค่าเริ่มต้น aac",
                           "default": "aac"},
                "overwrite": _OVERWRITE_PROP,
            },
            "required": ["path", "out"],
        },
    },
]

IMPL = {
    "media_probe": media_probe,
    "media_trim": media_trim,
    "media_resize": media_resize,
    "media_compress": media_compress,
    "media_extract_audio": media_extract_audio,
    "media_mute": media_mute,
    "media_to_gif": media_to_gif,
    "media_transcode": media_transcode,
}


# เครื่องมือที่เขียนทับไฟล์ได้ต้องรับ confirm_token ด้วย (กฎ S03)
# ประกาศรวมไว้ที่เดียว จะได้ไม่ตกหล่นเวลาเพิ่มเครื่องมือใหม่
for _schema in TOOLS:
    _props = _schema["inputSchema"]["properties"]
    if "overwrite" in _props:
        _props["confirm_token"] = {
            "type": "string",
            "description": "ใส่เมื่อผู้ใช้อนุมัติการเขียนทับไฟล์เดิมแล้ว "
                           "(ได้มาจากการเรียกครั้งก่อนที่ระบบขอให้ยืนยัน)",
        }
del _schema, _props
