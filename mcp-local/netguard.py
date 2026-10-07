# -*- coding: utf-8 -*-
"""netguard.py -- ด่านกัน SSRF ที่ใช้ร่วมกันทุกเครื่องมือที่ดึง URL (ช่องโหว่ V5 รอบ 2026-09-30)

ย้ายมาจาก tools_browser._check_target ให้ mcp-websearch (fetch_url) ใช้ตรรกะชุดเดียวกัน
เดิม fetch_url ไม่มีด่านเลย ยิง 127.0.0.1:8100/8792, 169.254.x, วง LAN และตาม redirect ไปหาได้หมด

สิ่งที่กัน
  1. สคีมอื่นนอกจาก http/https (file://, ftp://, data: ...) — ทั้งตอนเริ่มและทุก redirect
  2. ปลายทางภายใน: loopback, private, link-local, CGNAT 100.64/10, multicast, reserved,
     unspecified, IPv6 ที่ห่อ IPv4 ไว้ (::ffff:, 6to4 2002::, NAT64 64:ff9b::, Teredo)
     รวมถึงรูปเลข IPv4 แบบที่เบราว์เซอร์ยอมรับ (127.1, 2130706433, 0x7f.1, 0177.0.0.1)
  3. DNS rebinding ระหว่าง "ตรวจ" กับ "ต่อจริง": ตัวเชื่อมต่อของเราแปลงชื่อเองแล้วตรวจ IP
     ทุกตัวอีกครั้งตอน connect และต่อไปที่ IP ที่ตรวจแล้วเท่านั้น (ชื่อโฮสต์ยังใช้กับ Host/SNI ตามปกติ)
  4. ไม่ใช้ proxy จากสภาพแวดล้อมเลย เพราะ proxy จะแปลงชื่อเองโดยที่เราตรวจ IP ไม่ได้

allow_local=True (ต้องให้ผู้ใช้อนุมัติที่ต้นทางก่อนเสมอ) เปิดให้เข้าที่อยู่ภายในได้
แต่ยังกันพอร์ตของสแตกนี้เองบน loopback (hub, MCP, gateway, llama-server) และ link-local เสมอ
เพราะเครื่องมือที่ยิงบริการของสแตกเองได้คือทางลัดข้ามทุกด่านที่เหลือ

stdlib ล้วน ไม่ import guard เพื่อให้ mcp-websearch ใช้ได้โดยไม่แตะ audit.log ของ mcp-local
"""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

# พอร์ตของสแตกนี้ (รวมพอร์ตทดสอบ) ห้ามยิงบน loopback แม้ผู้ใช้อนุญาต allow_local
STACK_PORTS = frozenset([8099, 8199, 8780, 8791, 8792, 8891, 8892] + list(range(8100, 8180)))

_IPV4_PART_RE = re.compile(r"^(?:0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)$")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")

_EXTRA_V4 = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "100.64.0.0/10", "192.0.0.0/24", "198.18.0.0/15",
    "240.0.0.0/4", "255.255.255.255/32")]
_NAT64 = [ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48")]


class Blocked(ValueError):
    """ปลายทางนี้ถูกปฏิเสธโดยนโยบาย SSRF"""


def literal_ip(host: str) -> str | None:
    """แปลงชื่อโฮสต์ที่เป็นตัวเลขให้เป็น IP ตามกฎ WHATWG URL (แบบเดียวกับเบราว์เซอร์)

    getaddrinfo() บน Windows ไม่รู้จัก 127.1 / 2130706433 / 0x7f.1 แต่ Chromium รู้จักและต่อจริง
    ถ้าปล่อยให้ DNS ตัดสิน ด่านจะได้รายการ IP ว่างแล้วปล่อยผ่าน (เคยเป็นรูจริงใน tools_browser)
    """
    h = str(host or "").strip().strip("[]")
    if not h:
        return None
    try:
        return str(ipaddress.ip_address(h))
    except ValueError:
        pass
    parts = h.split(".")
    if parts and parts[-1] == "":
        parts = parts[:-1]
    if not 1 <= len(parts) <= 4:
        return None
    nums = []
    for part in parts:
        if not _IPV4_PART_RE.match(part):
            return None
        if part[:2] in ("0x", "0X"):
            nums.append(int(part, 16))
        elif len(part) > 1 and part.startswith("0"):
            nums.append(int(part, 8))
        else:
            nums.append(int(part, 10))
    if any(n > 255 for n in nums[:-1]) or nums[-1] >= 256 ** (5 - len(nums)):
        return None
    total = nums[-1]
    for i, n in enumerate(nums[:-1]):
        total += n << (8 * (3 - i))
    try:
        return str(ipaddress.ip_address(total))
    except ValueError:
        return None


def ip_is_internal(ip) -> bool:
    """True ถ้า IP นี้ไม่ใช่ที่อยู่สาธารณะบนอินเทอร์เน็ต"""
    if isinstance(ip, str):
        ip = ipaddress.ip_address(ip.split("%", 1)[0])
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            return ip_is_internal(ip.ipv4_mapped)
        if ip.sixtofour is not None:
            return ip_is_internal(ip.sixtofour)
        if ip.teredo is not None:
            return True                      # อุโมงค์ Teredo พาออกไปไหนก็ได้ ไม่ยอม
        for net in _NAT64:
            if ip in net:
                return ip_is_internal(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    else:
        if any(ip in net for net in _EXTRA_V4):
            return True
    return (not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def _always_blocked(ip, port: int | None) -> bool:
    """กันแม้ allow_local=True: link-local (metadata) และพอร์ตของสแตกบน loopback/unspecified"""
    if isinstance(ip, str):
        ip = ipaddress.ip_address(ip.split("%", 1)[0])
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_link_local:
        return True
    if (ip.is_loopback or ip.is_unspecified) and port in STACK_PORTS:
        return True
    return False


def _explain(host: str, addr: str) -> str:
    return ("ปฏิเสธเป้าหมายในเครือข่ายภายใน: %s ชี้ไปที่ %s\n"
            "  ที่อยู่ภายใน (localhost, 127.x, 10.x, 192.168.x, 172.16-31.x, 169.254.x, 100.64.x, "
            "IPv6 ภายใน) ถูกกันไว้เพราะโมเดลที่ยิงเข้าเครือข่ายในบ้าน บริการของเครื่องนี้ "
            "หรือ metadata ของ cloud ได้เอง คือช่องโหว่ SSRF" % (host, addr))


def check_addr(host: str, addr: str, port: int | None, allow_local: bool) -> None:
    """ตรวจ IP หนึ่งตัวของปลายทาง โยน Blocked ถ้าไม่ผ่าน"""
    try:
        ip = ipaddress.ip_address(str(addr).split("%", 1)[0])
    except ValueError:
        raise Blocked("อ่านที่อยู่ IP ของ %s ไม่ออก: %r" % (host, addr)) from None
    if _always_blocked(ip, port):
        raise Blocked("ปฏิเสธ: %s (%s พอร์ต %s) เป็นบริการของสแตกนี้เองหรือ link-local "
                      "ซึ่งกันไว้เสมอแม้ผู้ใช้อนุญาตที่อยู่ภายใน" % (host, addr, port))
    if not allow_local and ip_is_internal(ip):
        raise Blocked(_explain(host, str(addr)))


def resolve(host: str, port: int) -> list[str]:
    literal = literal_ip(host)
    if literal is not None:
        return [literal]
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    return sorted({info[4][0] for info in infos})


def check_target(url: str, allow_local: bool = False, add_scheme: bool = True) -> str:
    """ตรวจ URL ก่อนยิง คืน URL ที่ normalize แล้ว หรือโยน Blocked/ValueError

    ตรวจจาก IP ที่ DNS ตอบจริง ไม่ใช่แค่ชื่อ (โดเมนสาธารณะชี้กลับ 127.0.0.1 ได้)
    ส่วนการต่อจริงยังถูกตรวจซ้ำอีกรอบใน _guarded_connect กัน DNS ตอบคนละค่าในจังหวะที่สอง
    """
    raw = str(url or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("ไม่ได้ระบุ url")
    if add_scheme:
        m = _SCHEME_RE.match(raw)
        if not m or re.match(r"^\d+(?:[/?#]|$)", raw[m.end():]):
            raw = "https://" + raw
    parts = urllib.parse.urlsplit(raw)
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise Blocked(
            "รับเฉพาะ http และ https เท่านั้น แต่ได้รับสคีม \"%s\" — file:// และสคีมอื่น "
            "ถูกปฏิเสธเสมอ เพราะจะกลายเป็นช่องอ่านไฟล์ในเครื่องที่เลี่ยงการตรวจ path" % scheme)
    host = parts.hostname
    if not host:
        raise ValueError("URL ไม่มีชื่อโฮสต์: %s" % raw[:200])
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("หมายเลขพอร์ตใน URL ไม่ถูกต้อง: %s" % exc) from None
    try:
        addrs = resolve(host, port)
    except (socket.gaierror, OSError, UnicodeError, ValueError):
        addrs = []       # แปลงชื่อไม่ได้ ปล่อยให้ขั้นเชื่อมต่อรายงานเอง (ซึ่งตรวจซ้ำอยู่แล้ว)
    for addr in addrs:
        check_addr(host, addr, port, allow_local)
    return raw


def _guarded_connect_factory(allow_local: bool):
    """สร้างฟังก์ชันแทน socket.create_connection ที่ตรวจ IP ตอนต่อจริง"""
    def _connect(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None,
                 *args, **kwargs):
        host, port = address[0], int(address[1])
        try:
            addrs = resolve(host, port)
        except (socket.gaierror, UnicodeError) as exc:
            raise OSError("แปลงชื่อ %s ไม่ได้: %s" % (host, exc)) from None
        if not addrs:
            raise OSError("แปลงชื่อ %s ไม่ได้" % host)
        # ตรวจ "ทุก" IP ก่อนต่อตัวไหนเลย ถ้ามีตัวใดเป็นที่อยู่ภายใน ถือว่าทั้งชื่อนี้ไม่น่าไว้ใจ
        for addr in addrs:
            check_addr(host, addr, port, allow_local)
        last = None
        for addr in addrs:
            try:
                return socket.create_connection((addr, port), timeout, source_address)
            except OSError as exc:
                last = exc
        raise last or OSError("ต่อ %s ไม่ได้" % host)
    return _connect


def _connection_classes(allow_local: bool):
    connect = _guarded_connect_factory(allow_local)

    class _PinnedHTTPConnection(http.client.HTTPConnection):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._create_connection = connect

    class _PinnedHTTPSConnection(http.client.HTTPSConnection):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._create_connection = connect

    return _PinnedHTTPConnection, _PinnedHTTPSConnection


class GuardedRedirect(urllib.request.HTTPRedirectHandler):
    """ตรวจทุกจุดที่ถูก redirect ซ้ำ ไม่งั้นหน้าสาธารณะที่ตอบ 302 ไป 127.0.0.1 พาเราเข้าไปเอง"""
    max_redirections = 5

    def __init__(self, allow_local: bool = False):
        self.allow_local = allow_local
        self.hops: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            check_target(newurl, self.allow_local, add_scheme=False)
        except ValueError as exc:
            raise urllib.error.URLError("redirect ถูกปฏิเสธ: %s" % exc) from None
        self.hops.append(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener(allow_local: bool = False) -> urllib.request.OpenerDirector:
    """opener ที่มีแค่ http/https แบบตรวจ IP ตอนต่อ + redirect ที่ตรวจทุกทอด ไม่มี proxy

    ประกอบเองแทน urllib.request.build_opener เพราะตัวนั้นใส่ FTPHandler/FileHandler/DataHandler
    และ ProxyHandler จาก env มาให้อัตโนมัติ ซึ่งแต่ละตัวคือทางอ้อมด่านข้างบน
    """
    http_cls, https_cls = _connection_classes(allow_local)

    class _HTTP(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(http_cls, req)

    class _HTTPS(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(https_cls, req, context=self._context)

    opener = urllib.request.OpenerDirector()
    for handler in (_HTTP(), _HTTPS(), GuardedRedirect(allow_local),
                    urllib.request.HTTPDefaultErrorHandler(),
                    urllib.request.HTTPErrorProcessor(),
                    urllib.request.UnknownHandler()):
        opener.add_handler(handler)
    return opener
