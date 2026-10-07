# -*- coding: utf-8 -*-
"""kernel_runner.py — ตัวกลางระหว่าง MCP (Python 3.13) กับ Jupyter kernel ของ anaconda (สัญญา K1 python)

ทำไมต้องมีไฟล์นี้
-----------------
MCP server รันบน C:\\Python313 ซึ่งไม่มี jupyter_client/zmq และห้ามติดตั้งแพ็กเกจเพิ่ม
ส่วน anaconda มีครบ (jupyter_client, ipykernel, matplotlib, plotly, pandas) จึงให้สคริปต์นี้
ถูกเปิดด้วย anaconda python หนึ่งตัวต่อโปรเจกต์ แล้วคุยกับ MCP ผ่าน stdin/stdout เป็น JSON ทีละบรรทัด
ตัวสคริปต์ถือ KernelManager + client ไว้ตลอดอายุ ตัวแปรในโค้ดของผู้ใช้จึงคงอยู่ข้ามการเรียก

สิ่งที่ไฟล์นี้ "ไม่" ทำ (อยู่ที่ tools_python.py ฝั่ง MCP ทั้งหมด)
  * ไม่ตัดสินว่าโค้ดไหนรันได้ — การยืนยันสองขั้น (confirm_token + local_confirm) เกิดก่อนถึงที่นี่เสมอ
  * ไม่สร้าง env เอง — MCP ส่ง env ที่คัดแล้ว (ไม่มีความลับ) มาให้ตั้งแต่ตอนเปิดโปรเซสนี้
    และ kernel สืบทอด env ของโปรเซสนี้ต่อ จึงสะอาดทั้งสาย

โปรโตคอล (ASCII ล้วน บรรทัดละหนึ่ง JSON)
  เข้า  {"id": "...", "op": "exec", "code": "...", "timeout": 120, "stamp": "20260930-081500-ab12"}
        {"id": "...", "op": "ping"} / {"id": "...", "op": "shutdown"}
  ออก   "@@QWK@@ " + JSON  — บรรทัดที่ไม่ขึ้นต้นด้วยเครื่องหมายนี้ถูกฝั่ง MCP ทิ้ง
        (กันข้อความหลงจากไลบรารีไปปนโปรโตคอล — stdout ของ kernel เองส่งไป DEVNULL อยู่แล้ว)

อายุของโปรเซส
  * stdin ปิด (MCP ตาย/รีสตาร์ต) -> ปิด kernel แล้วจบ
  * ไม่มีคำขอเกิน --idle วินาที -> ปิด kernel แล้วจบเอง (ฝั่ง MCP ก็มีตัวเก็บกวาดอีกชั้น)
  * kernel ถูกเปิดแบบ "ไม่อิสระ" (JPY_PARENT_PID) ถ้าโปรเซสนี้ถูก kill kernel จะจบตามเองภายในไม่กี่วินาที
"""
from __future__ import annotations

import argparse
import ast
import base64
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time

PREFIX = "@@QWK@@ "
CREATE_NO_WINDOW = 0x08000000

# เพดานในฝั่งนี้กว้างกว่าที่ MCP แสดงจริง (ฝั่ง MCP ตัดอีกรอบ) — แค่กัน RAM บวมจากโค้ดที่พิมพ์ไม่หยุด
CAP_STDOUT = 400_000
CAP_STDERR = 100_000
CAP_RESULT = 100_000
MAX_FILES = 20                  # รูปต่อหนึ่งการรัน
MAX_IMAGE_BYTES = 25 * 1024 * 1024
INTERRUPT_GRACE = 8.0           # วินาทีที่รอหลังส่ง interrupt ก่อนตัดสินใจรีสตาร์ต kernel

# โค้ดที่รันเงียบๆ ใน kernel ตอนเริ่ม: ประกาศตัวช่วยบันทึกรูป matplotlib ที่ยังเปิดค้าง
# ใช้ backend Agg (ตั้งใน env) แทน inline เพราะ inline ใช้พื้นโปร่งใส + dpi 72 ภาพออกมาจางในธีมมืด
# รูปถูกปิดหลังบันทึกทุกครั้ง = พฤติกรรมเดียวกับ notebook (inline ก็ปิดรูปท้ายทุก cell)
STARTUP = r'''
def _qwen_flush_figs(outdir, stamp, start):
    import json as _j, os as _o, sys as _s
    plt = _s.modules.get("matplotlib.pyplot")
    if plt is None:
        return "[]"
    saved = []
    try:
        nums = list(plt.get_fignums())
    except Exception:
        return "[]"
    for i, num in enumerate(nums[:20]):
        try:
            fig = plt.figure(num)
            name = "fig-%s-%d.png" % (stamp, start + i)
            fig.savefig(_o.path.join(outdir, name), dpi=144, bbox_inches="tight", facecolor="white")
            saved.append(name)
        except Exception as exc:
            saved.append("!%s: %s" % (type(exc).__name__, str(exc)[:200]))
    try:
        plt.close("all")
    except Exception:
        pass
    return _j.dumps(saved)
try:
    get_ipython().user_ns_hidden["_qwen_flush_figs"] = _qwen_flush_figs
except Exception:
    pass
'''

# ค่าตั้ง matplotlib ของ kernel (ไฟล์ matplotlibrc ใน runtime + env MATPLOTLIBRC)
# ใช้ไฟล์แทนการ import matplotlib ตอนเริ่ม เพื่อไม่ให้ทุก kernel ต้องจ่ายเวลาโหลดไลบรารีที่อาจไม่ได้ใช้
# ฟอนต์: Leelawadee UI/Tahoma มีอักษรไทย (DejaVu ที่เป็นค่าเริ่มต้นไม่มี = ป้ายกราฟภาษาไทยเป็นกล่องสี่เหลี่ยม)
MPL_RC = """backend: Agg
font.family: sans-serif
font.sans-serif: Leelawadee UI, Tahoma, DejaVu Sans, Arial, sans-serif
axes.unicode_minus: False
figure.dpi: 100
figure.facecolor: white
savefig.dpi: 144
savefig.facecolor: white
savefig.bbox: tight
"""

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


def _log(msg: str) -> None:
    """บันทึกเหตุการณ์ลง stderr (runner.log ในโฟลเดอร์ runtime) — ห้ามใส่เนื้อโค้ดหรือผลลัพธ์ของผู้ใช้"""
    try:
        sys.stderr.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
        sys.stderr.flush()
    except Exception:           # noqa: BLE001
        pass


class Proto:
    """ช่องส่งผลกลับ MCP — ใช้ fd ของ stdout เดิม ส่วน sys.stdout ถูกย้ายไป stderr กันไลบรารีพิมพ์ปน"""

    def __init__(self, stream):
        self.stream = stream
        self.lock = threading.Lock()

    def send(self, obj: dict) -> None:
        line = PREFIX + json.dumps(obj, ensure_ascii=True) + "\n"
        with self.lock:
            self.stream.write(line.encode("ascii"))
            self.stream.flush()


class Runner:
    def __init__(self, args):
        self.a = args
        self.km = None
        self.kc = None
        self.edge_profile = os.path.join(args.runtime, "edge-profile")

    # ------------------------------------------------------------ kernel
    def start(self) -> dict:
        from jupyter_client import KernelManager
        from jupyter_client.kernelspec import KernelSpec, KernelSpecManager

        runtime = self.a.runtime

        class _Spec(KernelSpecManager):
            # ไม่ใช้ kernelspec ที่ติดตั้งในเครื่อง (ของผู้ใช้อาจชี้ไป env อื่น หรือมี env/argv แปลกๆ)
            # สร้าง spec ในโค้ด: python ตัวเดียวกับที่รันสคริปต์นี้ + ipykernel ของ anaconda
            def get_kernel_spec(self, kernel_name):
                return KernelSpec(argv=[sys.executable, "-m", "ipykernel_launcher",
                                        "-f", "{connection_file}"],
                                  display_name="qwen-python", language="python",
                                  resource_dir=runtime, env={}, metadata={})

        rc = os.path.join(runtime, "matplotlibrc")
        try:
            with open(rc, "w", encoding="utf-8") as fh:
                fh.write(MPL_RC)
            os.environ["MATPLOTLIBRC"] = rc        # kernel สืบทอด env ของโปรเซสนี้
        except OSError:
            pass
        conn = os.path.join(runtime, "kernel-%d.json" % os.getpid())
        self.km = KernelManager(kernel_name="qwen-python", kernel_spec_manager=_Spec(),
                                connection_file=conn)
        # stdout ของ kernel ต้องไม่ใช่ pipe ของเรา (ไม่งั้นข้อความระดับ C ของ kernel ปนโปรโตคอล)
        # CREATE_NO_WINDOW: โปรเซสนี้ไม่มีคอนโซล kernel ที่เปิดโดยไม่ใส่ flag จะเด้งหน้าต่างดำใส่ผู้ใช้
        self._klog = open(os.path.join(runtime, "kernel.log"), "wb")
        self.km.start_kernel(cwd=self.a.workdir, stdout=subprocess.DEVNULL, stderr=self._klog,
                             creationflags=CREATE_NO_WINDOW)
        self._connect()
        return {"pid": getattr(self.km.provisioner, "pid", None),
                "python": sys.version.split()[0]}

    def _connect(self) -> None:
        if self.kc is not None:
            try:
                self.kc.stop_channels()
            except Exception:   # noqa: BLE001
                pass
        self.kc = self.km.client()
        self.kc.allow_stdin = False
        self.kc.start_channels()
        self.kc.wait_for_ready(timeout=90)
        self._silent(STARTUP)

    def _silent(self, code: str, user_expressions=None, timeout: float = 30.0) -> dict:
        """รันโค้ดของเราเองแบบเงียบ (ไม่นับ In [n] ไม่ลงประวัติ) คืน content ของ execute_reply"""
        msg_id = self.kc.execute(code, silent=True, store_history=False,
                                 user_expressions=user_expressions or {}, allow_stdin=False)
        return self._reply(msg_id, timeout)

    def _reply(self, msg_id: str, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                msg = self.kc.get_shell_msg(timeout=max(0.1, deadline - time.monotonic()))
            except queue.Empty:
                break
            if msg.get("parent_header", {}).get("msg_id") == msg_id:
                return msg.get("content") or {}
        return {}

    def restart(self) -> None:
        _log("restart kernel")
        self.km.restart_kernel(now=True)
        self._connect()

    def shutdown(self) -> None:
        try:
            if self.kc is not None:
                self.kc.stop_channels()
        except Exception:       # noqa: BLE001
            pass
        try:
            if self.km is not None and self.km.has_kernel:
                self.km.shutdown_kernel(now=False)
        except Exception:       # noqa: BLE001
            try:
                self.km.shutdown_kernel(now=True)
            except Exception:   # noqa: BLE001
                pass

    # ------------------------------------------------------------- exec
    def execute(self, code: str, timeout: float, stamp: str) -> dict:
        out = {"stdout": "", "stderr": "", "result": [], "error": None, "files": [],
               "notes": [], "count": None, "timed_out": False, "restarted": False,
               "died": False}
        t0 = time.monotonic()
        msg_id = self.kc.execute(code, silent=False, store_history=True, allow_stdin=False,
                                 stop_on_error=True)
        deadline = t0 + timeout
        interrupted_at = None
        figs = 0
        while True:
            now = time.monotonic()
            if interrupted_at is None and now > deadline:
                _log("timeout -> interrupt")
                out["timed_out"] = True
                interrupted_at = now
                try:
                    self.km.interrupt_kernel()
                except Exception as exc:     # noqa: BLE001
                    _log("interrupt failed: %s" % type(exc).__name__)
            if interrupted_at is not None and now - interrupted_at > INTERRUPT_GRACE:
                # interrupt ไม่ได้ผล (ติดอยู่ในโค้ด C) — ฆ่าแล้วเปิดใหม่ ตัวแปรหายหมดแต่เครื่องไม่ค้าง
                self.restart()
                out["restarted"] = True
                break
            try:
                msg = self.kc.get_iopub_msg(timeout=0.5)
            except queue.Empty:
                if not self.km.is_alive():
                    _log("kernel died")
                    out["died"] = True
                    self.restart()
                    out["restarted"] = True
                    break
                continue
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            kind = msg.get("msg_type")
            c = msg.get("content") or {}
            if kind == "stream":
                key = "stdout" if c.get("name") == "stdout" else "stderr"
                cap = CAP_STDOUT if key == "stdout" else CAP_STDERR
                if len(out[key]) < cap:
                    out[key] += (c.get("text") or "")[:cap - len(out[key])]
            elif kind in ("execute_result", "display_data"):
                if kind == "execute_result":
                    out["count"] = c.get("execution_count")
                figs += self._data(c.get("data") or {}, out, stamp, figs)
            elif kind == "execute_input":
                out["count"] = c.get("execution_count")
            elif kind == "error":
                tb = "\n".join(c.get("traceback") or [])
                out["error"] = {"ename": c.get("ename") or "", "evalue": c.get("evalue") or "",
                                "traceback": _ANSI_RE.sub("", tb)[-20000:]}
            elif kind == "status" and c.get("execution_state") == "idle":
                break
        if not out["restarted"]:
            self._reply(msg_id, 5.0)            # เก็บ execute_reply ของรอบนี้ออกจากคิว
            try:
                exprs = {"f": "_qwen_flush_figs(%r, %r, %d)" % (self.a.outdir, stamp, figs + 1)}
                rep = self._silent("", user_expressions=exprs, timeout=60.0)
                data = ((rep.get("user_expressions") or {}).get("f") or {}).get("data") or {}
                names = json.loads(ast.literal_eval(data.get("text/plain") or "'[]'"))
                for n in names:
                    if n.startswith("!"):
                        out["notes"].append("บันทึกรูป matplotlib ไม่สำเร็จ %s" % n[1:])
                    elif _SAFE_NAME_RE.match(n):
                        out["files"].append(n)
            except Exception as exc:     # noqa: BLE001
                out["notes"].append("ตรวจรูป matplotlib ไม่สำเร็จ: %s" % type(exc).__name__)
        out["elapsed"] = round(time.monotonic() - t0, 2)
        # pid ปัจจุบันของ kernel (เปลี่ยนหลังรีสตาร์ต) ให้ฝั่ง MCP ใช้ตรวจ/รายงานได้ถูกตัว
        out["pid"] = getattr(self.km.provisioner, "pid", None)
        return out

    def _data(self, data: dict, out: dict, stamp: str, figs: int) -> int:
        """จัดการ mime bundle หนึ่งก้อน คืนจำนวนไฟล์รูปที่บันทึกเพิ่ม"""
        if len(out["files"]) >= MAX_FILES:
            if "text/plain" in data:
                self._text(out, data["text/plain"])
            return 0
        png = data.get("image/png")
        if isinstance(png, str) and png:
            try:
                raw = base64.b64decode(png)
                if len(raw) > MAX_IMAGE_BYTES:
                    out["notes"].append("รูปใหญ่เกิน %d MB ไม่บันทึก" % (MAX_IMAGE_BYTES >> 20))
                    return 0
                name = "fig-%s-%d.png" % (stamp, figs + 1)
                with open(os.path.join(self.a.outdir, name), "wb") as fh:
                    fh.write(raw)
                out["files"].append(name)
                return 1
            except Exception as exc:     # noqa: BLE001
                out["notes"].append("บันทึกรูปไม่สำเร็จ: %s" % type(exc).__name__)
                return 0
        fig = data.get("application/vnd.plotly.v1+json")
        if isinstance(fig, dict):
            name, note = self._plotly(fig, stamp, figs + 1)
            if note:
                out["notes"].append(note)
            if name:
                out["files"].append(name)
                return 1
            return 0
        if "text/plain" in data:
            self._text(out, data["text/plain"])
        return 0

    @staticmethod
    def _text(out: dict, text) -> None:
        text = "" if text is None else str(text)
        used = sum(len(t) for t in out["result"])
        if used < CAP_RESULT:
            out["result"].append(text[:CAP_RESULT - used])

    # ------------------------------------------------------------ plotly
    def _plotly(self, fig: dict, stamp: str, n: int):
        """plotly -> PNG ด้วย Edge แบบ headless (เครื่องนี้ไม่มี kaleido และห้ามติดตั้งเพิ่ม)
        ถ้า Edge ใช้ไม่ได้ บันทึกเป็น HTML แทนแล้วบอกตรงๆ ว่าไม่ใช่ PNG"""
        try:
            import plotly.io as pio
            figure = pio.from_json(json.dumps(fig), skip_invalid=True)
            lay = figure.layout
            w = int(lay.width or 1000)
            h = int(lay.height or 600)
            w, h = max(200, min(w, 2400)), max(150, min(h, 1800))
            html = pio.to_html(figure, include_plotlyjs=True, full_html=True,
                               default_width="%dpx" % w, default_height="%dpx" % h,
                               config={"staticPlot": True, "displayModeBar": False})
            html = html.replace("<head>", "<head><style>html,body{margin:0;background:#fff}</style>", 1)
        except Exception as exc:         # noqa: BLE001
            return None, "แปลงกราฟ plotly ไม่สำเร็จ: %s" % type(exc).__name__
        name = "fig-%s-%d.png" % (stamp, n)
        png_path = os.path.join(self.a.outdir, name)
        edge = self.a.edge
        if edge and os.path.isfile(edge):
            page = os.path.join(self.a.runtime, "plotly-render.html")
            try:
                with open(page, "w", encoding="utf-8") as fh:
                    fh.write(html)
                # ไม่ให้เบราว์เซอร์ออกเน็ตเลย (plotly.js ฝังในหน้าแล้ว) และใช้โปรไฟล์แยกของ runner เท่านั้น
                # host-resolver ปิด DNS แต่ URL ที่เป็น IP ตรง (เช่นรูปใน layout.images ชี้ 127.0.0.1:8100)
                # ยังยิงได้ จึงส่งทุกคำขอ (รวม loopback ด้วย <-loopback>) ไปพร็อกซีที่ไม่มีอยู่จริง
                cmd = [edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                       "--no-default-browser-check", "--disable-extensions", "--mute-audio",
                       "--disable-background-networking", "--disable-component-update",
                       "--disable-sync", "--host-resolver-rules=MAP * ~NOTFOUND",
                       "--proxy-server=http://127.0.0.1:9", "--proxy-bypass-list=<-loopback>",
                       "--user-data-dir=%s" % self.edge_profile,
                       "--window-size=%d,%d" % (w, h), "--virtual-time-budget=5000",
                       "--screenshot=%s" % png_path,
                       "file:///" + page.replace("\\", "/")]
                subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=60,
                               creationflags=CREATE_NO_WINDOW)
                if os.path.isfile(png_path) and os.path.getsize(png_path) > 0:
                    return name, None
            except Exception as exc:     # noqa: BLE001
                _log("edge render failed: %s" % type(exc).__name__)
        # ถอยไปเก็บเป็น HTML (โต้ตอบได้ แต่หน้าแชตอาจเปิดแบบ sandbox จนสคริปต์ไม่ทำงาน)
        hname = "fig-%s-%d.html" % (stamp, n)
        try:
            with open(os.path.join(self.a.outdir, hname), "w", encoding="utf-8") as fh:
                fh.write(html)
            return hname, "แปลงกราฟ plotly เป็น PNG ไม่ได้ (Edge ใช้ไม่ได้) จึงบันทึกเป็น HTML แทน"
        except Exception as exc:         # noqa: BLE001
            return None, "บันทึกกราฟ plotly ไม่สำเร็จ: %s" % type(exc).__name__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--runtime", required=True)
    ap.add_argument("--idle", type=float, default=1200.0)
    ap.add_argument("--edge", default="")
    args = ap.parse_args()

    proto = Proto(sys.stdout.buffer)
    sys.stdout = sys.stderr                # print ของไลบรารีไปลง log ไม่ปนโปรโตคอล
    for d in (args.workdir, args.outdir, args.runtime):
        os.makedirs(d, exist_ok=True)

    inbox: queue.Queue = queue.Queue()

    def _reader():
        # อ่าน stdin ในเธรดแยก เพราะ pipe บน Windows ใช้ select/timeout ไม่ได้
        for raw in sys.stdin.buffer:
            inbox.put(raw)
        inbox.put(None)                    # EOF = MCP ปิดท่อ (ตาย/รีสตาร์ต)

    threading.Thread(target=_reader, daemon=True).start()

    runner = Runner(args)
    try:
        info = runner.start()
    except Exception as exc:               # noqa: BLE001
        _log("start failed: %s: %s" % (type(exc).__name__, exc))
        proto.send({"ready": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])})
        runner.shutdown()
        return 2
    _log("ready pid=%s" % info.get("pid"))
    proto.send(dict(info, ready=True))

    try:
        while True:
            try:
                raw = inbox.get(timeout=max(30.0, args.idle))
            except queue.Empty:
                _log("idle shutdown")
                break
            if raw is None:
                _log("stdin closed")
                break
            try:
                req = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            rid = req.get("id")
            op = req.get("op")
            if op == "ping":
                proto.send({"id": rid, "ok": True, "alive": bool(runner.km.is_alive())})
            elif op == "shutdown":
                proto.send({"id": rid, "ok": True})
                break
            elif op == "exec":
                try:
                    res = runner.execute(str(req.get("code") or ""),
                                         float(req.get("timeout") or 120),
                                         str(req.get("stamp") or time.strftime("%Y%m%d-%H%M%S")))
                    res.update(id=rid, ok=True)
                except Exception as exc:   # noqa: BLE001
                    _log("exec failed: %s" % type(exc).__name__)
                    res = {"id": rid, "ok": False,
                           "error_text": "%s: %s" % (type(exc).__name__, str(exc)[:300])}
                proto.send(res)
            else:
                proto.send({"id": rid, "ok": False, "error_text": "unknown op"})
    finally:
        runner.shutdown()
    return 0


if __name__ == "__main__":
    code = main()
    try:
        sys.stderr.flush()
    except Exception:           # noqa: BLE001
        pass
    # os._exit แทน sys.exit: เธรดอ่าน stdin ยังถือ lock ของ buffer อยู่ ถ้าปล่อยให้ interpreter ปิดตามปกติ
    # จะจบด้วย "Fatal Python error: _enter_buffered_busy" (exit code 0xC0000005) ทุกครั้ง
    os._exit(code)
