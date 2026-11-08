# -*- coding: utf-8 -*-
"""เทสต์ tools_creative.py (creative_video / creative_status / creative_cancel + ผิว /fast) — 2026-10-21

ใช้ ComfyUI ปลอมและ router (llama-server) ปลอมในโปรเซสเทสต์ ไม่แตะ GPU/โมเดล/ComfyUI จริง และไม่เปิดโปรเซสใดๆ
(QWEN_CREATIVE_START_CMD = สคริปต์ Python เล็กๆ ที่ "เปิด" ComfyUI ปลอมผ่าน endpoint ควบคุมของมัน)

ตรวจ
  * S03: creative_video ครั้งแรกคืน confirm_token + REVIEW ที่มี prompt/ขนาด/เฟรม/seed/ชื่อไฟล์ ยังไม่ส่งงาน · token ผูกกับค่าชุดเดิม
    (เปลี่ยน prompt = ใช้ไม่ได้) · ใช้ครั้งเดียว · เล่นซ้ำผ่าน local_confirm ของ server.py ได้ทั้งผิว /fast และ /mcp
  * งานสำเร็จ: workflow ที่ส่งถึง ComfyUI (โหนด/ค่า) ไฟล์ .webm ลง outputs ของโปรเจกต์ ลิงก์ /_qwen/out/ ไฟล์สถานะ data\\<slug>\\creative
    · ภาพ→วิดีโอ: อัปโหลดภาพ + LoadImage + start_image + ขนาดตามสัดส่วนภาพ
  * GPU: VRAM ไม่พอ -> ปลดโมเดลแชตที่ว่างผ่าน router (ไม่แตะตัวที่กำลังตอบ) · โมเดลกำลังตอบและ VRAM ไม่พอ -> ไม่ส่งงาน ·
    เสร็จงาน -> /free + ปลดโมเดลที่ว่าง · การ์ดเล็ก -> ปฏิเสธ · ComfyUI ไม่เปิด -> เปิดให้ (start cmd) หรือบอกเหตุผล
  * งานยาวเกินงบเวลาในการเรียก -> ได้ id แล้ว creative_status รอ/รายงาน/ให้ลิงก์เมื่อเสร็จ · ยกเลิก · ComfyUI ตอบ error ·
    ComfyUI ปฏิเสธ workflow (node_errors) · งานเดียวต่อเครื่อง (อีกโปรเจกต์เห็นแค่ "GPU ไม่ว่าง")
  * S04: งาน/สถานะของโปรเจกต์อื่นมองไม่เห็น · ภาพนอกโปรเจกต์ (path ต้องห้าม) ถูกปฏิเสธ · URL ที่ไม่ใช่ loopback ถูกแทนด้วยค่าเริ่มต้น
  * ผิว /fast: แถวคู่มือ, ลำดับคีย์ใน schema (name ก่อน image ... prompt ท้ายสุด), dispatch, พารามิเตอร์ขาด · ผิว /mcp: schema ไม่มี project
  * hub.py: ASK_TOOLS_FULL / PLAN_KEEP_TOOLS / PLAN_DROP_TOOLS รู้จักเครื่องมือใหม่
"""
import json
import os
import re
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from urllib.parse import parse_qs, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

guard = C.import_local("guard")
if os.name != "nt":
    # แซนด์บ็อกซ์ Linux: guard เทียบ root ด้วย "\\" เท่านั้น — ให้รับ "/" ด้วย (บน Windows ไม่แตะ)
    def _under(path, root):
        pl, rl = path.lower().rstrip("\\/"), guard._norm(root).lower().rstrip("\\/")
        return bool(rl) and (pl == rl or pl.startswith(rl + "\\") or pl.startswith(rl + "/"))
    guard._under = _under
tools_creative = C.import_local("tools_creative")
tools_fast = C.import_local("tools_fast")
server = C.import_local("server")
server.load_modules()

PROJECT = "cv-proj"


def _json(handler, code, obj, raw=None):
    body = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json" if raw is None else "application/octet-stream")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class FakeComfy:
    """ComfyUI ปลอม: /system_stats /prompt /history /queue /interrupt /free /view /upload/image + /_ctl (ควบคุมจากเทสต์)"""

    def __init__(self):
        self.up = True
        self.vram_total = 24 * 1024 ** 3
        self.vram_free = 23 * 1024 ** 3
        self.device_name = "cuda:0 NVIDIA GeForce RTX 4090 : native"
        self.prompts = []               # [(prompt_id, graph)]
        self.history = {}               # prompt_id -> entry
        self.queue = []                 # prompt_id ที่ยังทำอยู่
        self.uploads = []
        self.calls = []
        self.reject = None              # dict ที่จะตอบ 400 แทน
        self.auto_done_after = 0.0      # วินาทีหลัง /prompt แล้วย้ายไป history อัตโนมัติ (0 = ไม่อัตโนมัติ)
        self.video_bytes = b"\x1a\x45\xdf\xa3fake-webm" + b"\0" * 3000
        self.lock = threading.Lock()
        owner = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def do_GET(self):
                u = urlsplit(self.path)
                owner.calls.append(("GET", u.path))
                if u.path == "/_ctl":
                    return _json(self, 200, {"up": owner.up})
                if not owner.up:
                    self.send_error(503)
                    return
                if u.path == "/system_stats":
                    return _json(self, 200, {"system": {"comfyui_version": "0.38.0"},
                                             "devices": [{"name": owner.device_name, "type": "cuda", "index": 0,
                                                          "vram_total": owner.vram_total, "vram_free": owner.vram_free}]})
                if u.path.startswith("/history/"):
                    pid = u.path[len("/history/"):]
                    with owner.lock:
                        e = owner.history.get(pid)
                    return _json(self, 200, {pid: e} if e else {})
                if u.path == "/queue":
                    with owner.lock:
                        running = [[0, pid, {}, {}, []] for pid in owner.queue]
                    return _json(self, 200, {"queue_running": running, "queue_pending": []})
                if u.path == "/view":
                    q = parse_qs(u.query)
                    if q.get("filename", [""])[0].endswith(".webm"):
                        return _json(self, 200, None, raw=owner.video_bytes)
                    self.send_error(404)
                    return
                self.send_error(404)

            def do_POST(self):
                u = urlsplit(self.path)
                body = self._body()
                owner.calls.append(("POST", u.path))
                if u.path == "/_ctl":
                    owner.up = json.loads(body.decode()).get("up", True)
                    return _json(self, 200, {"ok": True})
                if not owner.up:
                    self.send_error(503)
                    return
                if u.path == "/prompt":
                    if owner.reject:
                        return _json(self, 400, owner.reject)
                    doc = json.loads(body.decode("utf-8"))
                    pid = "pid-%d" % (len(owner.prompts) + 1)
                    with owner.lock:
                        owner.prompts.append((pid, doc["prompt"]))
                        owner.queue.append(pid)
                    if owner.auto_done_after:
                        threading.Timer(owner.auto_done_after, owner.finish, args=(pid,)).start()
                    return _json(self, 200, {"prompt_id": pid, "number": len(owner.prompts), "node_errors": {}})
                if u.path == "/interrupt":
                    return _json(self, 200, {})
                if u.path == "/queue":
                    doc = json.loads(body.decode("utf-8"))
                    with owner.lock:
                        for pid in doc.get("delete") or []:
                            if pid in owner.queue:
                                owner.queue.remove(pid)
                    return _json(self, 200, {})
                if u.path == "/free":
                    owner.vram_free = owner.vram_total - 512 * 1024 ** 2
                    return _json(self, 200, {})
                if u.path == "/upload/image":
                    m = re.search(rb'filename="([^"]+)"', body)
                    name = m.group(1).decode() if m else "x.png"
                    owner.uploads.append((name, len(body)))
                    return _json(self, 200, {"name": name, "subfolder": "", "type": "input"})
                self.send_error(404)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def finish(self, pid, error=None, outputs=True):
        with self.lock:
            if pid in self.queue:
                self.queue.remove(pid)
            if error:
                self.history[pid] = {"outputs": {}, "status": {"status_str": "error", "completed": False, "messages": [
                    ["execution_error", {"node_id": "3", "node_type": "KSampler", "exception_message": error}]]}}
            else:
                self.history[pid] = {"outputs": {"47": {"images": [{"filename": "qwen-%s_00001_.webm" % pid,
                                                                     "subfolder": "qwen", "type": "output"}]
                                                        if outputs else []}, "animated": [True]},
                                     "status": {"status_str": "success", "completed": True, "messages": []}}

    def vanish(self, pid):
        with self.lock:
            if pid in self.queue:
                self.queue.remove(pid)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class FakeRouter:
    """llama-server router ปลอม: /models /slots /models/unload ตรวจ Bearer"""

    def __init__(self):
        self.models = {"Qwen3.8-27B": "loaded", "Qwen3-4B": "loaded", "gemma-4": "unloaded"}
        self.busy = set()
        self.unloaded = []
        self.calls = []
        owner = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _auth(self):
                return self.headers.get("Authorization", "") == "Bearer " + C.TOKEN

            def do_GET(self):
                u = urlsplit(self.path)
                owner.calls.append(("GET", u.path))
                if not self._auth():
                    return _json(self, 401, {"error": "bad token"})
                if u.path == "/models":
                    return _json(self, 200, {"data": [{"id": k, "status": {"value": v}} for k, v in owner.models.items()]})
                if u.path == "/slots":
                    mid = parse_qs(u.query).get("model", [""])[0]
                    return _json(self, 200, [{"id": 0, "is_processing": mid in owner.busy}])
                self.send_error(404)

            def do_POST(self):
                u = urlsplit(self.path)
                n = int(self.headers.get("Content-Length") or 0)
                doc = json.loads(self.rfile.read(n).decode() or "{}")
                owner.calls.append(("POST", u.path))
                if not self._auth():
                    return _json(self, 401, {"error": "bad token"})
                if u.path == "/models/unload":
                    owner.models[doc["model"]] = "unloaded"
                    owner.unloaded.append(doc["model"])
                    return _json(self, 200, {"success": True})
                self.send_error(404)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def make_png(path, w=640, h=480):
    png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0) + b"\0" * 4
    with open(path, "wb") as fh:
        fh.write(png)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.comfy = FakeComfy()
        cls.router = FakeRouter()
        cls.env = mock.patch.dict(os.environ, {
            "QWEN_CREATIVE_URL": cls.comfy.url, "QWEN_CREATIVE_ROUTER_URL": "http://127.0.0.1:%d" % cls.router.port,
            "QWEN_CREATIVE_START_CMD": "", "QWEN_CREATIVE_ROOT": tempfile.mkdtemp(prefix="creative-root-"),
            "QWEN_CREATIVE_START_LOG": os.path.join(tempfile.mkdtemp(prefix="creative-log-"), "creative-start.log")})
        cls.env.start()
        cls.saved = (tools_creative.WAIT_IN_CALL_S, tools_creative.STATUS_WAIT_S, tools_creative.POLL_S,
                     tools_creative.ROOM_WAIT_S, tools_creative.QUEUE_CHECK_S)
        # Windows: ThreadingHTTPServer ปลอมตอบช้ากว่า Linux หลายเท่า (เชื่อมต่อใหม่ทุกคำขอ) — งบรอของ status ต้องเผื่อ
        tools_creative.WAIT_IN_CALL_S, tools_creative.STATUS_WAIT_S = 6.0, 8.0
        tools_creative.POLL_S, tools_creative.ROOM_WAIT_S, tools_creative.QUEUE_CHECK_S = 0.2, 1.0, 0.6
        tools_creative._ffmpeg = lambda: None            # ไม่แปลง mp4 ในเทสต์ (ffmpeg จริงทดสอบแยก)
        cls.saved_smi = tools_creative._nvidia_smi_4090
        tools_creative._nvidia_smi_4090 = lambda: None   # เครื่องจริง (Windows) มี nvidia-smi — เทสต์ต้องคุมค่าเอง

    @classmethod
    def tearDownClass(cls):
        (tools_creative.WAIT_IN_CALL_S, tools_creative.STATUS_WAIT_S, tools_creative.POLL_S,
         tools_creative.ROOM_WAIT_S, tools_creative.QUEUE_CHECK_S) = cls.saved
        tools_creative._nvidia_smi_4090 = cls.saved_smi
        cls.env.stop()
        cls.comfy.close()
        cls.router.close()

    def setUp(self):
        # เธรดเฝ้างานของเทสต์ก่อนหน้าต้องจบก่อน (ไม่งั้น /free ของมันมาเปลี่ยน VRAM ปลอมกลางเทสต์นี้)
        for th in threading.enumerate():
            if th.name.startswith("creative-"):
                th.join(timeout=10)
        c = self.comfy
        c.up, c.vram_free, c.vram_total = True, 23 * 1024 ** 3, 24 * 1024 ** 3
        c.device_name = "cuda:0 NVIDIA GeForce RTX 4090 : native"
        c.prompts.clear(); c.history.clear(); c.queue.clear(); c.uploads.clear(); c.calls.clear()
        c.reject, c.auto_done_after = None, 0.0
        r = self.router
        r.models = {"Qwen3.8-27B": "loaded", "Qwen3-4B": "loaded", "gemma-4": "unloaded"}
        r.busy.clear(); r.unloaded.clear(); r.calls.clear()
        with tools_creative._JOBS_LOCK:
            tools_creative._JOBS.clear()
            del tools_creative._RUNNING[:]
        guard._pending.clear()
        self.project = PROJECT + "-" + os.urandom(2).hex()
        with guard.project_scope(self.project):
            self.base = guard.project_dir(self.project)
        os.makedirs(os.path.join(self.base, "attachments"), exist_ok=True)

    # ---- ตัวช่วย: ขอ token แล้วยืนยันผ่าน server.py (local_confirm) ----
    def request(self, fast=True, **params):
        if fast:
            msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "local_do", "arguments": dict(action="creative_video", **params)}}
        else:
            msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "creative_video", "arguments": params}}
        rep = server.handle_rpc(msg, self.project, fast=fast)
        return rep["result"]["content"][0]["text"]

    def confirm(self, text, fast=True):
        m = re.search(r'confirm_token="([0-9a-f]+)"', text)
        self.assertTrue(m, text)
        tok = m.group(1)
        status, _body = server.review_lookup(self.project, "token=" + tok, viewer=True)   # กล่องอนุญาตดึง review ไปแสดงแล้ว (S1)
        self.assertEqual(status, 200)
        msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
               "params": {"name": guard.CONFIRM_TOOL, "arguments": {"confirm_token": tok}}}
        rep = server.handle_rpc(msg, self.project, fast=fast)
        return rep["result"]["content"][0]["text"], tok

    def outputs(self):
        d = os.path.join(self.base, "outputs")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def job_files(self):
        d = os.path.join(self.base, "creative")
        return sorted(f for f in os.listdir(d) if f.endswith(".json")) if os.path.isdir(d) else []


class ConfirmFlowTests(Base):
    def test_first_call_returns_review_and_does_not_submit(self):
        out = self.request(prompt="โดรนบินเหนือภูเขาไฟ", seconds="2", seed="123", name="volcano")
        self.assertIn("confirm_token", out)
        self.assertIn("```review", out)
        for piece in ("โดรนบินเหนือภูเขาไฟ", "1280x704", "49 เฟรม", "seed 123", "outputs/volcano.mp4", "ข้อความ→วิดีโอ",
                      tools_creative.DEFAULT_NEGATIVE[:12]):
            self.assertIn(piece, out)
        self.assertEqual(self.comfy.prompts, [])             # ยังไม่ส่งงาน
        self.assertEqual(self.outputs(), [])
        self.assertEqual(self.router.unloaded, [])           # ยังไม่แตะโมเดลแชต

    def test_bad_params_before_token(self):
        self.assertIn("ขาดพารามิเตอร์: prompt", self.request(prompt="", image=""))      # ผิวย่อดักก่อน
        with guard.project_scope(self.project):
            self.assertIn("ต้องมี prompt", tools_creative.creative_video(prompt="", image="", project=self.project))
        self.assertIn("seconds", self.request(prompt="x", seconds="9"))
        self.assertIn("size", self.request(prompt="x", size="big"))
        self.assertIn("seed", self.request(prompt="x", seed="abc"))
        self.assertIn("ไม่พบไฟล์ภาพ", self.request(prompt="x", image="nope.png"))
        self.assertEqual(self.comfy.prompts, [])

    def test_fast_missing_prompt_gives_usage(self):
        out = tools_fast.local_do(action="creative_video", project=self.project)
        self.assertIn("ยังขาดพารามิเตอร์: prompt", out)

    def test_token_bound_to_values_and_single_use(self):
        out = self.request(prompt="a cat", seed="5", name="cat")
        tok = re.search(r'confirm_token="([0-9a-f]+)"', out).group(1)
        # ส่ง token ให้ local_do ตรงๆ = ทางเก่า ปิดแล้ว
        direct = tools_fast.local_do(action="creative_video", project=self.project, prompt="a cat", seed="5", name="cat",
                                     confirm_token=tok)
        self.assertNotIn("สร้างวิดีโอเสร็จ", direct)
        # ค่าที่ token ผูกอยู่: prompt อื่นต้องไม่ผ่าน consume (เปิดช่อง confirming ได้ต่อเมื่อกล่องอนุญาตดึง review แล้ว)
        self.assertEqual(server.review_lookup(self.project, "token=" + tok, viewer=True)[0], 200)
        with guard.project_scope(self.project), guard.confirming(tok, None):
            spec = tools_creative.build_spec(self.project, prompt="a dog", seed="5", name="cat")
            self.assertFalse(guard.consume_confirm(tok, tools_creative.ACTION, tools_creative.spec_detail(spec)))
            spec = tools_creative.build_spec(self.project, prompt="a cat", seed="5", name="cat")
            self.assertTrue(guard.consume_confirm(tok, tools_creative.ACTION, tools_creative.spec_detail(spec)))
            self.assertFalse(guard.consume_confirm(tok, tools_creative.ACTION, tools_creative.spec_detail(spec)))

    def test_random_seed_fixed_at_request_time(self):
        out = self.request(prompt="x", name="s")
        seed = int(re.search(r"seed (\d+)", out).group(1))
        with guard.project_scope(self.project):
            rep = guard.pending_replay(re.search(r'confirm_token="([0-9a-f]+)"', out).group(1))
        self.assertEqual(rep["name"], "local_do")
        self.assertNotIn("seed", rep["args"])                # seed ไม่ได้มาจากโมเดล -> สุ่มตอนขอ
        self.assertGreaterEqual(seed, 0)


class RunTests(Base):
    def test_text_to_video_success_fast_surface(self):
        self.comfy.auto_done_after = 0.5
        self.comfy.vram_free = 23 * 1024 ** 3
        out = self.request(prompt="โดรนบินเหนือภูเขาไฟ", seconds="2", seed="42", name="volcano")
        done, tok = self.confirm(out)
        self.assertIn("สร้างวิดีโอเสร็จแล้ว", done)
        self.assertIn("[volcano.webm](/_qwen/out/volcano.webm)", done)
        self.assertEqual(self.outputs(), ["volcano.webm"])
        with open(os.path.join(self.base, "outputs", "volcano.webm"), "rb") as fh:
            self.assertEqual(fh.read(), self.comfy.video_bytes)
        pid, graph = self.comfy.prompts[0]
        self.assertEqual(graph["6"]["inputs"]["text"], "โดรนบินเหนือภูเขาไฟ")
        self.assertEqual(graph["7"]["inputs"]["text"], tools_creative.DEFAULT_NEGATIVE)
        self.assertEqual(graph["3"]["inputs"]["seed"], 42)
        self.assertEqual(graph["55"]["inputs"]["length"], 49)
        self.assertEqual((graph["55"]["inputs"]["width"], graph["55"]["inputs"]["height"]), (1280, 704))
        self.assertNotIn("57", graph)
        self.assertNotIn("start_image", graph["55"]["inputs"])
        self.assertEqual(graph["47"]["class_type"], "SaveWEBM")
        self.assertTrue(graph["47"]["inputs"]["filename_prefix"].startswith("qwen/"))
        self.assertEqual(graph["37"]["inputs"]["unet_name"], tools_creative.UNET_FILE)
        # VRAM พออยู่แล้ว -> ไม่ปลดโมเดลก่อนงาน แต่หลังงาน /free + ปลดโมเดลที่ว่างให้โหลดใหม่
        self.assertIn(("POST", "/free"), self.comfy.calls)
        self.assertEqual(sorted(self.router.unloaded), ["Qwen3-4B", "Qwen3.8-27B"])
        # ไฟล์สถานะ
        files = self.job_files()
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.base, "creative", files[0]), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(doc["state"], "done")
        self.assertEqual(doc["files"], ["volcano.webm"])
        self.assertNotIn("image", doc["spec"])
        # audit ไม่มี prompt
        with open(C.AUDIT_LOCAL, encoding="utf-8") as fh:
            audit = fh.read()
        self.assertNotIn("โดรนบินเหนือภูเขาไฟ", audit)
        self.assertIn("creative_submit", audit)
        # status ของงานที่เสร็จแล้ว
        jid = doc["id"]
        st = tools_fast.local_read(action="creative_status", project=self.project, id=jid)
        self.assertIn("สร้างวิดีโอเสร็จแล้ว", st)
        self.assertIn("/_qwen/out/volcano.webm", st)

    def test_replay_without_seed_or_name_keeps_the_values_from_the_request(self):
        """E2E จริง 2026-10-21: โมเดลไม่ส่ง seed/name -> เล่นซ้ำสุ่ม seed ใหม่/ตั้งชื่อไฟล์ใหม่ -> token ไม่ตรง ("confirm_token ใช้ไม่ได้")"""
        self.comfy.auto_done_after = 0.3
        out = self.request(prompt="no seed here")
        seed = int(re.search(r"seed (\d+)", out).group(1))
        stem = re.search(r"outputs/([^ ]+)\.mp4", out).group(1)
        self.assertTrue(stem.startswith("video-"))
        done, _ = self.confirm(out)
        self.assertIn("สร้างวิดีโอเสร็จแล้ว", done)
        self.assertIn("seed %d" % seed, done)
        self.assertEqual(self.outputs(), [stem + ".webm"])
        _pid, graph = self.comfy.prompts[0]
        self.assertEqual(graph["3"]["inputs"]["seed"], seed)
        # คำขอเดิมอีกครั้งหลังงานเริ่มแล้ว = seed ใหม่ ชื่อไฟล์ใหม่ (ไม่ใช่ค่าที่จำไว้)
        out2 = self.request(prompt="no seed here")
        seed2 = int(re.search(r"seed (\d+)", out2).group(1))
        stem2 = re.search(r"outputs/([^ ]+)\.mp4", out2).group(1)
        self.assertNotEqual((seed, stem), (seed2, stem2))
        # ขอซ้ำโดยยังไม่ยืนยัน = ค่าเดิม (token ใหม่ผูกค่าเดียวกัน)
        out3 = self.request(prompt="no seed here")
        self.assertIn("seed %d" % seed2, out3)
        self.assertIn("outputs/%s.mp4" % stem2, out3)

    def test_full_surface_replay(self):
        self.comfy.auto_done_after = 0.3
        out = self.request(fast=False, prompt="sunset", seed="7", name="sun")
        self.assertIn("confirm_token", out)
        done, _tok = self.confirm(out, fast=False)
        self.assertIn("สร้างวิดีโอเสร็จแล้ว", done)
        self.assertIn('creative_status(id="', done) if "ถามความคืบหน้า" in done else None
        self.assertEqual(self.outputs(), ["sun.webm"])

    def test_image_to_video(self):
        self.comfy.auto_done_after = 0.3
        img = os.path.join(self.base, "attachments", "tall.png")
        make_png(img, 600, 1000)
        out = self.request(prompt="", image="tall.png", seed="1", name="tall")
        self.assertIn("ภาพ→วิดีโอ", out)
        self.assertIn("attachments/tall.png (600x1000)", out)
        self.assertIn("704x1280", out)                        # แนวตั้งตามสัดส่วนภาพ
        done, _ = self.confirm(out)
        self.assertIn("สร้างวิดีโอเสร็จแล้ว", done)
        self.assertEqual(len(self.comfy.uploads), 1)
        self.assertTrue(self.comfy.uploads[0][0].startswith("qwen-"))
        _pid, graph = self.comfy.prompts[0]
        self.assertEqual(graph["57"]["class_type"], "LoadImage")
        self.assertEqual(graph["57"]["inputs"]["image"], self.comfy.uploads[0][0])
        self.assertEqual(graph["55"]["inputs"]["start_image"], ["57", 0])
        self.assertEqual((graph["55"]["inputs"]["width"], graph["55"]["inputs"]["height"]), (704, 1280))
        self.assertEqual(graph["6"]["inputs"]["text"], "")

    def test_image_outside_project_denied(self):
        with guard.project_scope("other-proj"):
            other = guard.project_dir("other-proj")
        os.makedirs(os.path.join(other, "attachments"), exist_ok=True)
        img = os.path.join(other, "attachments", "o.png")
        make_png(img)
        out = self.request(prompt="x", image=img)
        self.assertEqual(self.comfy.prompts, [])
        if os.name != "nt":
            self.skipTest("ด่าน S04 ของ guard เทียบ path แบบ Windows — ตรวจบนเครื่องจริง")
        self.assertIn("ปฏิเสธ", out)                                           # S04
        self.assertNotIn("confirm_token", out)

    def test_make_room_unloads_idle_models_only(self):
        self.comfy.auto_done_after = 0.3
        self.comfy.vram_free = 2 * 1024 ** 3                  # 27B ถือ VRAM อยู่
        self.router.busy.add("Qwen3-4B")                      # 4B กำลังตอบ ห้ามแตะ
        orig_unload = self.router.httpd.RequestHandlerClass.do_POST

        def grow(handler):
            orig_unload(handler)
            if handler.path == "/models/unload":
                self.comfy.vram_free = 20 * 1024 ** 3         # ปลดแล้ว VRAM คืน
        self.router.httpd.RequestHandlerClass.do_POST = grow
        try:
            out = self.request(prompt="x", seed="1", name="room")
            done, _ = self.confirm(out)
        finally:
            self.router.httpd.RequestHandlerClass.do_POST = orig_unload
        self.assertIn("สร้างวิดีโอเสร็จแล้ว", done)
        self.assertIn("ปลดโมเดลแชตที่ว่างออกจาก GPU: Qwen3.8-27B", done)
        self.assertNotIn("Qwen3-4B", self.router.unloaded[:1])
        self.assertEqual(self.router.unloaded[0], "Qwen3.8-27B")

    def test_make_room_trusts_nvidia_smi_over_comfy(self):
        """ComfyUI 0.38 บอกว่า VRAM ว่างทั้งใบแม้ llama-server ถือ 22 GB (วัดจริง 2026-10-21) — ต้องดู nvidia-smi ด้วย"""
        self.comfy.auto_done_after = 0.3
        self.comfy.vram_free = 23 * 1024 ** 3                 # ComfyUI มองไม่เห็นโมเดลแชต
        smi = {"index": 1, "name": "NVIDIA GeForce RTX 4090", "total_mib": 24564, "free_mib": 1440}
        orig_unload = self.router.httpd.RequestHandlerClass.do_POST

        def grow(handler):
            orig_unload(handler)
            if handler.path == "/models/unload":
                smi["free_mib"] = 23000                       # ปลดแล้ว nvidia-smi เห็นว่าง
        self.router.httpd.RequestHandlerClass.do_POST = grow
        tools_creative._nvidia_smi_4090 = lambda: dict(smi)
        try:
            out = self.request(prompt="x", seed="1", name="smi")
            done, _ = self.confirm(out)
            ov = tools_fast.local_read(action="creative_status", project=self.project)
        finally:
            self.router.httpd.RequestHandlerClass.do_POST = orig_unload
            tools_creative._nvidia_smi_4090 = lambda: None
        self.assertIn("สร้างวิดีโอเสร็จแล้ว", done)
        self.assertIn("ปลดโมเดลแชตที่ว่างออกจาก GPU: Qwen3.8-27B, Qwen3-4B", done)
        self.assertEqual(self.router.unloaded, ["Qwen3.8-27B", "Qwen3-4B"])
        self.assertIn("VRAM ว่าง 23,000 / 24,576 MiB", ov)   # ภาพรวมก็ใช้ค่าจริง (min ของสองแหล่ง)

    def test_vram_short_and_model_busy_refuses(self):
        self.comfy.vram_free = 2 * 1024 ** 3
        self.router.busy.update({"Qwen3-4B", "Qwen3.8-27B"})
        out = self.request(prompt="x", seed="1", name="busy")
        done, _ = self.confirm(out)
        self.assertIn("ERROR", done)
        self.assertIn("กำลังตอบอยู่", done)
        self.assertEqual(self.comfy.prompts, [])             # ยังไม่ส่งงาน
        self.assertEqual(self.router.unloaded, [])
        self.assertFalse(tools_creative._RUNNING)

    def test_small_gpu_refused(self):
        self.comfy.vram_total, self.comfy.vram_free = 6 * 1024 ** 3, 5 * 1024 ** 3
        self.comfy.device_name = "cuda:0 NVIDIA RTX 1000 Ada"
        out = self.request(prompt="x", seed="1", name="small")
        done, _ = self.confirm(out)
        self.assertIn("ERROR", done)
        self.assertIn("RTX 4090", done)
        self.assertEqual(self.comfy.prompts, [])

    def test_comfy_down_without_start_cmd(self):
        self.comfy.up = False
        out = self.request(prompt="x", seed="1", name="down")
        done, _ = self.confirm(out)
        self.assertIn("ERROR", done)
        self.assertIn("ยังไม่เปิด", done)
        self.assertFalse(tools_creative._RUNNING)

    def test_comfy_auto_start(self):
        self.comfy.up = False
        self.comfy.auto_done_after = 0.3
        script = os.path.join(tempfile.mkdtemp(prefix="cv-start-"), "start.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("import urllib.request, json\n"
                     "req = urllib.request.Request(%r, data=b'{\"up\": true}', method='POST')\n"
                     "urllib.request.urlopen(req).read()\n" % (self.comfy.url + "/_ctl"))
        with mock.patch.dict(os.environ, {"QWEN_CREATIVE_START_CMD": json.dumps([sys.executable, "-I", script])}):
            out = self.request(prompt="x", seed="1", name="auto")
            done, _ = self.confirm(out)
        self.assertIn("สร้างวิดีโอเสร็จแล้ว", done)
        self.assertIn("เปิด Creative Studio ให้", done)

    def test_comfy_auto_start_with_lingering_child(self):
        """ตัวเปิดตัวจริงปล่อย ComfyUI ไว้ (สืบทอด handle ของตัวเปิดทุกตัว) แล้วจบ — ต้องกลับมาทันทีที่ตัวเปิดจบ
        ไม่ใช่รอจนลูกของมันปิด (บั๊กจริง 2026-10-21: capture_output + communicate() ค้างที่ "starting" ตลอดกาล)"""
        self.comfy.up = False
        self.comfy.auto_done_after = 0.3
        d = tempfile.mkdtemp(prefix="cv-start-")
        script, pidfile = os.path.join(d, "start.py"), os.path.join(d, "child.pid")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("import subprocess, sys, urllib.request\n"
                     "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], close_fds=False)\n"
                     "open(%r, 'w').write(str(p.pid))\n"
                     "req = urllib.request.Request(%r, data=b'{\"up\": true}', method='POST')\n"
                     "urllib.request.urlopen(req).read()\n"
                     "print('starter-ok'); sys.stdout.flush()\n" % (pidfile, self.comfy.url + "/_ctl"))
        saved = tools_creative.START_TIMEOUT_S
        tools_creative.START_TIMEOUT_S = 12.0
        t0 = time.monotonic()
        try:
            with mock.patch.dict(os.environ, {"QWEN_CREATIVE_START_CMD": json.dumps([sys.executable, "-I", script])}):
                out = self.request(prompt="x", seed="1", name="linger")
                done, _ = self.confirm(out)
        finally:
            tools_creative.START_TIMEOUT_S = saved
            try:
                with open(pidfile, encoding="utf-8") as fh:
                    os.kill(int(fh.read().strip()), signal.SIGTERM)
            except (OSError, ValueError):
                pass
        self.assertIn("สร้างวิดีโอเสร็จแล้ว", done)
        self.assertIn("เปิด Creative Studio ให้", done)
        self.assertLess(time.monotonic() - t0, 10.0, "ต้องไม่รอลูกที่ตัวเปิดปล่อยไว้ (หรือหมดเวลาของตัวเปิด)")
        with open(os.environ["QWEN_CREATIVE_START_LOG"], encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("# 20", text)                          # หัวบรรทัดเวลา + คำสั่ง
        self.assertIn("starter-ok", text)                    # ผลลัพธ์ของตัวเปิดลงไฟล์ ไม่ใช่ pipe

    def test_long_job_returns_id_then_status_waits_and_links(self):
        tools_creative.WAIT_IN_CALL_S = 1.0
        try:
            out = self.request(prompt="long", seed="1", name="long")
            partial, _ = self.confirm(out)
        finally:
            tools_creative.WAIT_IN_CALL_S = 6.0
        self.assertIn("กำลังสร้างวิดีโอ", partial)
        jid = re.search(r"งาน (cv-[0-9a-f]+)", partial).group(1)
        self.assertIn('local_read action="creative_status" id="%s"' % jid, partial)
        st = tools_fast.local_read(action="creative_status", project=self.project, id=jid)
        self.assertIn("กำลังสร้างวิดีโอ", st)
        # ภาพรวมเห็นงานนี้ + GPU ไม่ว่าง
        ov = tools_fast.local_read(action="creative_status", project=self.project)
        self.assertIn(jid, ov)
        self.assertIn("ของโปรเจกต์นี้", ov)
        # อีกโปรเจกต์: มองไม่เห็นรายละเอียด และสั่งงานใหม่ไม่ได้
        ov2 = tools_fast.local_read(action="creative_status", project="someone-else")
        self.assertNotIn(jid, ov2)
        self.assertIn("อีกโปรเจกต์", ov2)
        st2 = tools_fast.local_read(action="creative_status", project="someone-else", id=jid)
        self.assertIn("ไม่พบงาน", st2)
        busy = tools_fast.local_do(action="creative_video", project="someone-else", prompt="y")
        tok2 = re.search(r'confirm_token="([0-9a-f]+)"', busy)
        self.assertTrue(tok2)                                # ขอ token ได้ (ยังไม่ลงมือ)
        with guard.project_scope("someone-else"), guard.tool_call("fast", "local_do", {}), guard.confirming(tok2.group(1), None):
            spec = tools_creative.build_spec("someone-else", prompt="y")
            self.assertFalse(guard.consume_confirm(tok2.group(1), tools_creative.ACTION, tools_creative.spec_detail(spec)))
        res = tools_creative.run_job(spec, "someone-else", "fast")
        self.assertIn("GPU กำลังสร้างวิดีโออยู่", res)
        self.assertIn("อีกโปรเจกต์", res)
        self.assertNotIn(jid, res)
        # เสร็จแล้ว -> status ได้ลิงก์
        pid = self.comfy.prompts[0][0]
        self.comfy.finish(pid)
        st = tools_fast.local_read(action="creative_status", project=self.project, id=jid)
        self.assertIn("สร้างวิดีโอเสร็จแล้ว", st)
        self.assertIn("/_qwen/out/long.webm", st)
        self.assertEqual(self.outputs(), ["long.webm"])
        self.assertFalse(tools_creative._RUNNING)

    def test_cancel(self):
        tools_creative.WAIT_IN_CALL_S = 0.5
        try:
            out = self.request(prompt="cancel me", seed="1", name="c")
            partial, _ = self.confirm(out)
        finally:
            tools_creative.WAIT_IN_CALL_S = 6.0
        jid = re.search(r"งาน (cv-[0-9a-f]+)", partial).group(1)
        self.assertIn("ไม่พบงาน", tools_fast.local_do(action="creative_cancel", project="other", id=jid))   # S04
        res = tools_fast.local_do(action="creative_cancel", project=self.project, id=jid)
        self.assertIn("ยกเลิกแล้ว", res)
        self.assertIn(("POST", "/interrupt"), self.comfy.calls)
        self.assertEqual(self.outputs(), [])
        self.assertFalse(tools_creative._RUNNING)
        self.assertIn("จบไปแล้ว", tools_fast.local_do(action="creative_cancel", project=self.project, id=jid))

    def test_comfy_execution_error(self):
        tools_creative.WAIT_IN_CALL_S = 0.5
        try:
            out = self.request(prompt="boom", seed="1", name="boom")
            partial, _ = self.confirm(out)
        finally:
            tools_creative.WAIT_IN_CALL_S = 6.0
        jid = re.search(r"งาน (cv-[0-9a-f]+)", partial).group(1)
        self.comfy.finish(self.comfy.prompts[0][0], error="CUDA out of memory \x1b[31m!")
        st = tools_fast.local_read(action="creative_status", project=self.project, id=jid)
        self.assertIn("ERROR", st)
        self.assertIn("KSampler: CUDA out of memory", st)
        self.assertNotIn("\x1b", st)
        self.assertEqual(self.outputs(), [])
        self.assertIn(("POST", "/free"), self.comfy.calls)

    def test_job_vanishes_from_queue(self):
        tools_creative.WAIT_IN_CALL_S = 0.5
        try:
            out = self.request(prompt="gone", seed="1", name="gone")
            partial, _ = self.confirm(out)
        finally:
            tools_creative.WAIT_IN_CALL_S = 6.0
        jid = re.search(r"งาน (cv-[0-9a-f]+)", partial).group(1)
        self.comfy.vanish(self.comfy.prompts[0][0])
        job = tools_creative._JOBS[jid]
        job.done_ev.wait(8)                                   # รอบตรวจคิว (QUEUE_CHECK_S) จับได้ว่าหายไป
        self.assertEqual(job.state, "error")
        self.assertIn("หายจากคิว", job.error)

    def test_workflow_rejected(self):
        self.comfy.reject = {"error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed validation"},
                             "node_errors": {"37": {"class_type": "UNETLoader", "errors": [
                                 {"type": "value_not_in_list", "message": "Value not in list",
                                  "details": "unet_name: 'wan2.2_ti2v_5B_fp16.safetensors' not in []"}]}}}
        out = self.request(prompt="x", seed="1", name="rej")
        done, _ = self.confirm(out)
        self.assertIn("ERROR", done)
        self.assertIn("UNETLoader", done)
        self.assertIn("creative_status", done)                # ชี้ให้ตรวจโมเดล
        self.assertFalse(tools_creative._RUNNING)

    def test_rehydrate_after_restart(self):
        # จำลอง MCP ตายระหว่างงาน: มีไฟล์สถานะ running + prompt_id แต่ไม่มีเธรดเฝ้า/ไม่มีในความจำ
        with guard.project_scope(self.project):
            spec = tools_creative.build_spec(self.project, prompt="restart", seed="1", name="re")
        job = tools_creative.Job("cv-dead", guard.project_slug(self.project), spec)
        job.prompt_id, job.state = "pid-dead", "running"
        tools_creative._save(job)
        self.comfy.queue.append("pid-dead")
        self.comfy.finish("pid-dead")                         # ComfyUI ทำเสร็จระหว่าง MCP ตาย
        st = tools_fast.local_read(action="creative_status", project=self.project, id="cv-dead")
        self.assertIn("สร้างวิดีโอเสร็จแล้ว", st)
        self.assertEqual(self.outputs(), ["re.webm"])
        # งานค้างที่ ComfyUI ไม่รู้จักเลย -> error ไม่ค้าง "กำลังทำ" ตลอดไป
        job2 = tools_creative.Job("cv-10af", guard.project_slug(self.project), spec)
        job2.prompt_id, job2.state = "pid-10af", "running"
        tools_creative._save(job2)
        st2 = tools_fast.local_read(action="creative_status", project=self.project, id="cv-10af")
        self.assertIn("ERROR", st2)
        self.assertIn("ไม่อยู่ในคิว", st2)


class SurfaceTests(Base):
    def test_fast_rows_and_schema_order(self):
        self.assertIn("creative_status", tools_fast._READ_INDEX)
        self.assertIn("creative_video", tools_fast._DO_INDEX)
        self.assertIn("creative_cancel", tools_fast._DO_INDEX)
        self.assertTrue(tools_fast._DO_INDEX["creative_video"][2].startswith("[ยืนยัน]"))
        keys = list(tools_fast.TOOLS[1]["inputSchema"]["properties"])
        idx = [keys.index(k) for k in ("name", "image", "seconds", "size", "seed", "negative", "prompt")]
        self.assertEqual(idx, sorted(idx))
        self.assertEqual(keys[-1], "prompt")
        self.assertIn("creative_video:name,image,seconds,size,seed,negative,prompt", tools_fast.TOOLS[1]["description"])
        self.assertIn("action=creative_video", tools_fast.TOOLS[1]["description"].split("พารามิเตอร์: ")[0] + "พารามิเตอร์: "
                      if False else tools_fast.TOOLS[1]["description"])
        self.assertIn("creative_status", tools_fast.TOOLS[0]["description"])
        self.assertIn("creative_video", tools_fast.help_text())
        self.assertIn("creative_video", tools_fast.TOOLS[1]["inputSchema"]["properties"]["action"]["enum"])

    def test_full_surface_schema(self):
        names = {t["name"] for t in server.TOOLS}
        self.assertTrue({"creative_video", "creative_status", "creative_cancel"} <= names, names)
        for t in server.TOOLS:
            if t["name"].startswith("creative_"):
                self.assertNotIn("project", t["inputSchema"]["properties"])
                self.assertNotIn("confirm_token", t["inputSchema"]["properties"])
        self.assertIn("creative_video", server.NEEDS_PROJECT)

    def test_hub_lists(self):
        hub_path = os.path.join(C.LLM_ROOT, "projects", "hub.py")
        if not os.path.isfile(hub_path):
            self.skipTest("ไม่มี hub.py")
        with open(hub_path, encoding="utf-8") as fh:
            src = fh.read()
        ask = re.search(r"ASK_TOOLS_FULL = \((.*?)\)\n", src, re.S).group(1)
        self.assertIn('"creative_video"', ask)
        self.assertIn('"creative_cancel"', ask)
        keep = re.search(r"PLAN_KEEP_TOOLS = frozenset\(\((.*?)\)\)", src, re.S).group(1)
        self.assertIn('"creative_status"', keep)
        drop = re.search(r"PLAN_DROP_TOOLS = frozenset\(\((.*?)\)\)", src, re.S).group(1)
        self.assertIn('"creative_video"', drop)

    def test_loopback_only(self):
        with mock.patch.dict(os.environ, {"QWEN_CREATIVE_URL": "http://evil.example:8188",
                                          "QWEN_CREATIVE_ROUTER_URL": "http://10.0.0.5:8099"}):
            self.assertEqual(tools_creative.comfy_addr(), ("127.0.0.1", 8188))
            self.assertEqual(tools_creative.router_addr(), ("127.0.0.1", 8099))

    def test_helpers(self):
        self.assertEqual(tools_creative.parse_seconds("5"), (121, 121 / 24.0))
        self.assertEqual(tools_creative.parse_seconds("")[0], 49)
        self.assertEqual(tools_creative.parse_size("portrait"), (704, 1280))
        self.assertEqual(tools_creative.parse_size("1000x600"), (992, 608))
        self.assertEqual(tools_creative.parse_size("", (1000, 1000)), (960, 960))
        self.assertEqual(tools_creative._stem("my clip.mp4"), "my clip")
        self.assertTrue(tools_creative._stem("").startswith("video-"))
        p = os.path.join(self.base, "attachments", "a.png")
        make_png(p, 123, 45)
        self.assertEqual(tools_creative.image_size(p), (123, 45))
        self.assertEqual(tools_creative._clean("a\x00b\u202ec", 3), "abc")
        with mock.patch.dict(os.environ, {"QWEN_CREATIVE_START_CMD": "not json"}):
            self.assertEqual(tools_creative._start_cmd(), [])


if __name__ == "__main__":
    unittest.main()
