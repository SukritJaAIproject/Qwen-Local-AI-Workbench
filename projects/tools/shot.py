# -*- coding: utf-8 -*-
"""ถ่ายภาพหน้าจอ UI ของ Qwen3.8 ด้วย Edge แบบ headless ผ่าน DevTools Protocol

ทำไมไม่ใช้เบราว์เซอร์ตัวเดียวกันทั้งหมด:
  หลายคนตรวจงานพร้อมกันได้ ถ้าแต่ละครั้งใช้โปรไฟล์ชั่วคราวของตัวเอง
  (IndexedDB/localStorage ว่างทุกครั้ง = ทดสอบแบบผู้ใช้เปิดครั้งแรก) และไม่ต้องแย่งหน้าต่างกัน

ตัวอย่าง:
  python shot.py http://127.0.0.1:8101/ out.png
  python shot.py http://127.0.0.1:8101/ out.png --theme light --w 390 --h 844 --mobile
  python shot.py "http://127.0.0.1:8101/#chat={conv0}" out.png --seed fixtures/rich.json
  python shot.py http://127.0.0.1:8101/ out.png --eval "document.querySelector('#x').click()"
  python shot.py http://127.0.0.1:8101/ out.png --dom "#sidebar"      (พิมพ์ outerHTML แทน)

--seed   ใส่บทสนทนาจากไฟล์ fixture ลง IndexedDB ของ origin นั้นก่อนเปิดหน้า
         {conv0} ใน URL ถูกแทนด้วย id ของบทสนทนาแรกใน fixture
--eval   JS ที่รันในหน้าบนสุดหลังโหลด (เข้าถึง iframe ได้เพราะ origin เดียวกัน)
--frame-eval  JS ที่รันใน iframe#frame (หน้าแชตของ WebUI)
--wait   มิลลิวินาทีที่รอหลังโหลดก่อนถ่าย (ค่าเริ่มต้น 3000)
พิมพ์ error ของ JavaScript ที่เกิดระหว่างโหลดออกมาด้วย ใช้จับบั๊กได้
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlparse

EDGE_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WS:
    """websocket ขั้นต่ำสำหรับ CDP (handshake, text frame แบบ mask, อ่าน continuation)"""

    def __init__(self, url, timeout=30.0):
        rest = url.split("://", 1)[-1]
        hostport, _, path = rest.partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port)), timeout)
        self.sock.settimeout(timeout)
        self.buf = b""
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(("GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
                           "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                           "Sec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key)).encode())
        while b"\r\n\r\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise OSError("handshake ล้มเหลว")
            self.buf += chunk
        head, _, self.buf = self.buf.partition(b"\r\n\r\n")
        if b" 101" not in head.split(b"\r\n", 1)[0]:
            raise OSError("handshake ล้มเหลว: %r" % head[:80])
        self.next_id = 0
        self.events = []

    def _exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise OSError("การเชื่อมต่อถูกปิด")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        p = text.encode()
        n = len(p)
        hdr = bytes([0x81, 0x80 | n]) if n < 126 else (
            bytes([0x81, 0xFE]) + struct.pack(">H", n) if n < 65536 else
            bytes([0x81, 0xFF]) + struct.pack(">Q", n))
        m = os.urandom(4)
        self.sock.sendall(hdr + m + bytes(b ^ m[i % 4] for i, b in enumerate(p)))

    def recv(self):
        parts = []
        while True:
            b0, b1 = self._exact(2)
            op, size = b0 & 0x0F, b1 & 0x7F
            if size == 126:
                size = struct.unpack(">H", self._exact(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", self._exact(8))[0]
            mask = self._exact(4) if b1 & 0x80 else b""
            data = self._exact(size) if size else b""
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 0x8:
                raise OSError("close frame")
            if op == 0x9:
                self.sock.sendall(bytes([0x8A, 0x80]) + os.urandom(4))
                continue
            if op == 0xA:
                continue
            parts.append(data)
            if b0 & 0x80:
                return b"".join(parts).decode("utf-8", "replace")

    def call(self, method, params=None, timeout=60):
        self.next_id += 1
        mid = self.next_id
        self.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("%s: %s" % (method, msg["error"]))
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)
        raise TimeoutError(method)

    def drain(self, seconds):
        """เก็บ event ระหว่างรอ (ใช้จับ error ของ JavaScript)"""
        end = time.time() + seconds
        self.sock.settimeout(0.25)
        try:
            while time.time() < end:
                try:
                    msg = json.loads(self.recv())
                    if "method" in msg:
                        self.events.append(msg)
                except (socket.timeout, TimeoutError):
                    continue
        finally:
            self.sock.settimeout(30)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def evaluate(ws, expr, await_promise=True):
    r = ws.call("Runtime.evaluate", {"expression": expr, "awaitPromise": await_promise,
                                     "returnByValue": True, "userGesture": True})
    if r.get("exceptionDetails"):
        d = r["exceptionDetails"]
        msg = (d.get("exception") or {}).get("description") or d.get("text")
        raise RuntimeError("JS error: %s" % msg)
    return (r.get("result") or {}).get("value")


def navigate(ws, url, settle=1.5):
    ws.call("Page.navigate", {"url": url})
    ws.drain(settle)


SEED_JS = r"""
(async (fx) => {
  // รอให้ Dexie ของ WebUI สร้างฐานข้อมูลเองก่อน (schema รุ่น 10) ห้ามเปิดก่อนมันสร้าง
  // indexedDB.open ของฐานที่ยังไม่มี = สร้างฐานเปล่ารุ่น 1 แล้ว WebUI จะพัง
  // เครื่องที่งานหนักใช้เวลาเกิน 3 วินาทีได้ จึงวนเช็ก ไม่ใช่รอเวลาตายตัว
  const deadline = Date.now() + 20000;
  for (;;) {
    const list = indexedDB.databases ? await indexedDB.databases() : [];
    if (list.find(d => d.name === 'LlamaUi' && d.version >= 10)) break;
    if (Date.now() > deadline) throw new Error('LlamaUi DB was not created by the WebUI within 20s');
    await new Promise(r => setTimeout(r, 250));
  }
  const db = await new Promise((ok, no) => {
    const q = indexedDB.open('LlamaUi');
    q.onupgradeneeded = () => q.transaction.abort();   // ไม่สร้างฐานเองเด็ดขาด
    q.onsuccess = () => ok(q.result); q.onerror = () => no(q.error);
  });
  if (!db.objectStoreNames.contains('conversations') || !db.objectStoreNames.contains('messages')) {
    db.close(); throw new Error('LlamaUi exists but stores are missing');
  }
  const now = Date.now();
  const tx = db.transaction(['conversations', 'messages'], 'readwrite');
  (fx.conversations || []).forEach((c, i) => tx.objectStore('conversations').put(Object.assign({}, c, { lastModified: now - i * 3600e3 })));
  (fx.messages || []).forEach(m => tx.objectStore('messages').put(m));
  await new Promise((ok, no) => { tx.oncomplete = ok; tx.onerror = () => no(tx.error); });
  db.close();
  return (fx.conversations || []).length;
})(%s)
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--sweep-temp", action="store_true",
                    help="ลบโปรไฟล์ทดสอบเก่า (qwen-shot-*/qwen-verify-*) ใน %%TEMP%% ที่เกิน 10 นาที")
    ap.add_argument("--w", type=int, default=1440)
    ap.add_argument("--h", type=int, default=900)
    ap.add_argument("--mobile", action="store_true")
    ap.add_argument("--theme", choices=["dark", "light", "system"], default=None)
    ap.add_argument("--scheme", choices=["dark", "light"], default="dark",
                    help="prefers-color-scheme ที่จำลอง")
    ap.add_argument("--font", choices=["serif", "sans"], default=None)
    ap.add_argument("--seed", default=None)
    ap.add_argument("--wait", type=int, default=3000)
    ap.add_argument("--eval", dest="js", default=None)
    ap.add_argument("--frame-eval", dest="fjs", default=None)
    ap.add_argument("--dom", default=None, help="พิมพ์ outerHTML ของ selector แทนการถ่ายภาพ")
    ap.add_argument("--full", action="store_true", help="ถ่ายทั้งหน้า ไม่ใช่แค่ viewport")
    a = ap.parse_args()
    if a.sweep_temp:
        sweep_temp()
        if not a.url:
            return
    if not (a.url and a.out):
        ap.error("ต้องระบุ url และ out (หรือใช้ --sweep-temp อย่างเดียว)")

    edge = next((p for p in EDGE_CANDIDATES if os.path.isfile(p)), None)
    if not edge:
        sys.exit("ไม่พบ msedge.exe")
    port = free_port()
    profile = tempfile.mkdtemp(prefix="qwen-shot-")
    proc = subprocess.Popen([
        edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
        "--no-default-browser-check", "--disable-extensions", "--mute-audio",
        "--remote-debugging-port=%d" % port, "--user-data-dir=%s" % profile,
        "--window-size=%d,%d" % (a.w, a.h), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(100):
            try:
                tabs = json.loads(urllib.request.urlopen(
                    "http://127.0.0.1:%d/json/list" % port, timeout=2).read())
                page = next((t for t in tabs if t.get("type") == "page"), None)
                if page:
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except OSError:
                pass
            time.sleep(0.15)
        if not ws_url:
            sys.exit("Edge ไม่เปิด DevTools")
        ws = WS(ws_url)
        ws.call("Page.enable")
        ws.call("Runtime.enable")
        ws.call("Emulation.setDeviceMetricsOverride", {
            "width": a.w, "height": a.h, "deviceScaleFactor": 1, "mobile": a.mobile})
        if a.mobile:
            ws.call("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
        ws.call("Emulation.setEmulatedMedia", {"features": [
            {"name": "prefers-color-scheme", "value": a.scheme}]})

        u = urlparse(a.url)
        origin = "%s://%s" % (u.scheme, u.netloc)
        target = a.url
        fixture = None
        if a.seed:
            with open(a.seed, encoding="utf-8") as fh:
                fixture = json.load(fh)
            convs = fixture.get("conversations") or []
            if convs:
                target = target.replace("{conv0}", convs[0]["id"])
                a.js = a.js.replace("{conv0}", convs[0]["id"]) if a.js else a.js
                a.fjs = a.fjs.replace("{conv0}", convs[0]["id"]) if a.fjs else a.fjs

        need_origin = a.seed or a.theme or a.font
        if need_origin:
            # ต้องอยู่ใน origin เดียวกันก่อนถึงจะเขียน localStorage / IndexedDB ของมันได้
            # เปิดหน้าแชตของ WebUI ก่อนเพื่อให้ Dexie สร้างฐานข้อมูลด้วย schema ที่ถูกต้อง
            navigate(ws, origin + "/?ui=1", settle=3.0)
            if a.theme:
                evaluate(ws, "localStorage.setItem('qwen-theme', %s); "
                             "localStorage.setItem('mode-watcher-mode', %s); true"
                         % (json.dumps(a.theme), json.dumps(a.theme)))
            if a.font:
                evaluate(ws, "localStorage.setItem('qwen-font', %s); true" % json.dumps(a.font))
            if fixture:
                n = evaluate(ws, SEED_JS % json.dumps(fixture, ensure_ascii=False))
                print("seeded %s conversations" % n)

        ws.events.clear()
        if a.theme or a.font:
            # ธีม/ฟอนต์เป็นค่าของ hub (boot.js เขียนค่าจากเซิร์ฟเวอร์ทับ localStorage ทุกครั้ง)
            # จึงต้องสั่งผ่าน qwenBoot หลังโหลด และดัก PATCH ไปที่ hub ไม่ให้ถึงจริง
            # ไม่งั้นการถ่ายภาพทดสอบจะไปเปลี่ยนค่าจริงของผู้ใช้ทุกโปรเจกต์
            ws.call("Fetch.enable", {"patterns": [
                {"urlPattern": "http://127.0.0.1:8100/api/settings*"}]})
        navigate(ws, target, settle=a.wait / 1000.0)
        if a.theme or a.font:
            print("prefs ->", evaluate(ws, """(() => {
              const b = window.qwenBoot; if (!b) return 'no qwenBoot (standalone page)';
              %s %s
              const f = document.getElementById('frame'); const e = f && f.contentWindow.qwenEnhance;
              if (e) { try { e.applyTheme && e.applyTheme(); e.setFont && %s; } catch (x) {} }
              return document.documentElement.dataset.theme;
            })()""" % ("b.setTheme(%s);" % json.dumps(a.theme) if a.theme else "",
                       "b.setFont(%s);" % json.dumps(a.font) if a.font else "",
                       "e.setFont(%s)" % json.dumps(a.font) if a.font else "0")))
            ws.drain(1.5)
        if a.js:
            print("eval ->", json.dumps(evaluate(ws, a.js), ensure_ascii=False)[:500])
            ws.drain(0.8)
        if a.fjs:
            wrapped = ("(async()=>{const w=document.getElementById('frame').contentWindow;"
                       "return await w.eval(%s)})()" % json.dumps(a.fjs))
            print("frame-eval ->", json.dumps(evaluate(ws, wrapped), ensure_ascii=False)[:500])
            ws.drain(0.8)

        errors = []
        for ev in ws.events:
            if ev["method"] == "Runtime.exceptionThrown":
                d = ev["params"]["exceptionDetails"]
                errors.append((d.get("exception") or {}).get("description") or d.get("text"))
            elif ev["method"] == "Runtime.consoleAPICalled" and ev["params"].get("type") == "error":
                errors.append(" ".join(str(x.get("value", x.get("description", "")))
                                       for x in ev["params"].get("args", [])))
        for e in errors[:12]:
            print("JS ERROR:", str(e).splitlines()[0][:300])

        if a.dom:
            html = evaluate(ws, "(document.querySelector(%s)||{}).outerHTML||null" % json.dumps(a.dom))
            print(html if html else "(ไม่พบ %s)" % a.dom)
            return
        params = {"format": "png"}
        if a.full:
            m = ws.call("Page.getLayoutMetrics")
            cs = m.get("cssContentSize") or m.get("contentSize")
            params.update({"captureBeyondViewport": True, "clip": {
                "x": 0, "y": 0, "width": cs["width"], "height": cs["height"], "scale": 1}})
        shot = ws.call("Page.captureScreenshot", params)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        with open(a.out, "wb") as fh:
            fh.write(base64.b64decode(shot["data"]))
        print("saved %s (%dx%d%s)" % (a.out, a.w, a.h, ", errors=%d" % len(errors) if errors else ""))
    finally:
        close_edge(proc, profile)


def sweep_temp(min_age_s=600):
    """ลบโปรไฟล์ทดสอบที่ค้างอยู่ใน %TEMP% — เลือกเฉพาะที่เป็นโปรไฟล์ของเบราว์เซอร์จริง

    ปิด Edge แล้วบางครั้ง Windows ยังรื้อโปรเซสไม่เสร็จ ไฟล์ LevelDB ในโปรไฟล์ถูกล็อกอยู่
    อีกพักหนึ่ง ลบทันทีหลังถ่ายภาพจึงไม่สำเร็จเสมอ ต้องกลับมากวาดของเก่าทีหลัง
    ลบเฉพาะโฟลเดอร์ชื่อ qwen-shot-*/qwen-verify-* ที่มีไฟล์ "Local State" (ลายเซ็นของโปรไฟล์
    Chromium หรือโฟลเดอร์ Default) และเก่ากว่า min_age_s — โฟลเดอร์ที่ยังใช้อยู่หรือไม่ใช่โปรไฟล์จะไม่ถูกแตะ
    """
    import glob
    tmp = tempfile.gettempdir()
    now = time.time()
    removed = kept = 0
    freed = 0
    for d in glob.glob(os.path.join(tmp, "qwen-shot-*")) + glob.glob(os.path.join(tmp, "qwen-verify-*")):
        # ลายเซ็นของโปรไฟล์ Chromium: "Local State" หรือโฟลเดอร์ "Default"
        # (รอบที่ลบค้างครึ่งทาง Local State หายไปแล้วแต่ Default ยังอยู่)
        if not os.path.isdir(d) or not (os.path.isfile(os.path.join(d, "Local State"))
                                        or os.path.isdir(os.path.join(d, "Default"))):
            continue
        if now - os.path.getmtime(d) < min_age_s:
            continue
        size = 0
        for root_, _dirs, files in os.walk(d):
            for f in files:
                try:
                    size += os.path.getsize(os.path.join(root_, f))
                except OSError:
                    pass
        shutil.rmtree(d, ignore_errors=True)
        if os.path.exists(d):
            kept += 1
        else:
            removed += 1
            freed += size
    print("sweep: removed %d old test profiles (%.0f MB), %d still locked" % (removed, freed / 1e6, kept))


def close_edge(proc, profile):
    """ปิด Edge ของโปรไฟล์ชั่วคราวนี้ให้หมดแล้วลบโปรไฟล์ทิ้ง

    msedge.exe เปิดตัวเองใหม่ตอนเริ่ม pid ที่เราได้จาก Popen จึงไม่ใช่เบราว์เซอร์ตัวจริง
    ทั้ง proc.kill() และ taskkill /T บน pid นั้นพลาดตัวจริงที่ยังถือไฟล์ในโปรไฟล์อยู่
    rmtree จึงล้มเงียบๆ ทุกครั้ง (เคยค้างใน %TEMP% กว่า 500 โฟลเดอร์ ~1 GB บน C: ที่เกือบเต็ม)
    หาโปรเซสจาก path ของโปรไฟล์แทน — ชื่อสุ่มไม่ซ้ำ จึงไม่มีทางไปโดน Edge ตัวที่ผู้ใช้เปิดอยู่
    """
    try:
        proc.kill()
    except Exception:
        pass
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | "
          "Where-Object { $_.CommandLine -like '*%s*' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
          % os.path.basename(profile))
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except Exception:
        pass
    for _ in range(40):
        shutil.rmtree(profile, ignore_errors=True)
        if not os.path.exists(profile):
            return
        time.sleep(0.25)
    print("warning: temp profile not removed: %s" % profile)


if __name__ == "__main__":
    main()
