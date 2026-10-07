# -*- coding: utf-8 -*-
"""เทสต์สดของบริการถอดเสียง (โมเดลจริง) — รันเฉพาะเมื่อ LLM_STT_LIVE=1 (โหลด large-v3-turbo ~1-3.5 GB, ใช้ GPU ถ้า VRAM ว่าง)

    set LLM_STT_LIVE=1 && C:\\Python313\\python.exe -m unittest C:\\LLM\\tests\\test_stt_live.py

เปิด stt_server.py ด้วย python ของ flexxfast ที่พอร์ตทดสอบ 8896 (token ทดสอบ, env คัดแล้ว) แล้วปิดเฉพาะตัวที่เปิดเอง
ตรวจ: ไทย/อังกฤษจากเสียงสังเคราะห์ Windows (Pattara/Zira) แม่นพอ (CER/WER ต่ำกว่าเกณฑ์), webm/opus (แบบที่ MediaRecorder
ส่ง) mp3 m4a ถอดได้, ไฟล์ที่ไม่ใช่เสียง = 415, เสียงยาวเกินเพดาน = 413, /health ready, /v1/status บอกโมเดล/อุปกรณ์,
งานบน GPU แล้วน้ำหนักถูกจอดไว้ใน RAM (คืน VRAM) และงานถัดไปย้ายกลับได้, และทางเต็มผ่าน MCP จริง (พอร์ตว่าง, token ทดสอบ):
/fast/<slug> local_read transcribe ของ mp3/mp4 ในไฟล์แนบ -> แคช -> kb ค้นข้อความที่ถอดแล้วเจอ, audit ไม่มีข้อความที่ถอดได้
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

LIVE = os.environ.get("LLM_STT_LIVE") == "1"
FLEXX = os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), "anaconda3", "envs", "flexxfast", "python.exe")
SERVER = r"C:\LLM\stt\stt_server.py"
PORT = 8896


def _bench():
    if r"C:\LLM\stt" not in sys.path:
        sys.path.insert(0, r"C:\LLM\stt")
    import stt_bench
    return stt_bench


@unittest.skipUnless(LIVE, "ตั้ง LLM_STT_LIVE=1 เพื่อรันเทสต์สดของบริการถอดเสียง")
class LiveSttTests(unittest.TestCase):
    proc = None

    @classmethod
    def setUpClass(cls):
        global PORT
        if not os.path.isfile(FLEXX):
            raise unittest.SkipTest("ไม่มี python ของ flexxfast")
        if C.port_in_use(PORT):
            # 8896 เป็นพอร์ตทดสอบร่วมของหลาย agent (เจอจริง: เทสต์ของ launcher เปิดตัวเองไว้ด้วย token อื่น) — ใช้พอร์ตว่างแทน
            import socket
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                PORT = s.getsockname()[1]
        cls.log = os.path.join(C.TMP, "stt-live.log")
        env = C.clean_env()
        out = open(cls.log, "wb")
        cls.proc = subprocess.Popen([FLEXX, "-X", "utf8", SERVER, "--port", str(PORT), "--max-seconds", "60"],
                                    cwd=r"C:\LLM\stt", env=env, stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out.close()
        deadline = time.time() + 300
        state = ""
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                raise RuntimeError("stt_server ตายตอนเริ่ม ดู %s" % cls.log)
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/health" % PORT, timeout=5) as r:
                    state = json.loads(r.read())["state"]
            except OSError:
                state = ""
            if state in ("ready", "no_model", "error"):
                break
            time.sleep(1)
        if state != "ready":
            cls.tearDownClass()
            raise unittest.SkipTest("โมเดลไม่พร้อม (%s) — ดิสก์ E: ถูกถอด? ดู %s" % (state, cls.log))
        # ตัวที่ตอบต้องเป็นโปรเซสของเราเอง (token ทดสอบของเราใช้ได้) ไม่ใช่บริการของคนอื่นที่แย่งพอร์ตไปก่อน
        st, _h, _raw = C.http("GET", PORT, "/v1/status", headers={"Authorization": "Bearer " + C.TOKEN})
        if cls.proc.poll() is not None or st != 200:
            cls.tearDownClass()
            raise RuntimeError("พอร์ต %d ไม่ใช่เซิร์ฟเวอร์ของเทสต์นี้ (status %s) ดู %s" % (PORT, st, cls.log))
        cls.tmp = tempfile.mkdtemp(prefix="stt-live-", dir=C.TMP)
        cls.bench = _bench()
        cls.wavs = cls.bench.synthesize(cls.tmp)
        cls.url = "http://127.0.0.1:%d" % PORT
        os.environ["LLM_LOCAL_TOKEN_FILE"] = C.TOKEN_FILE

    @classmethod
    def tearDownClass(cls):
        if cls.proc is not None and cls.proc.poll() is None:
            cls.proc.kill()                        # เฉพาะโปรเซสที่เทสต์นี้เปิดเอง
            cls.proc.wait(20)

    def post(self, data, ctype="audio/wav", language="auto"):
        return self.bench.transcribe(self.url, data, language=language, content_type=ctype)

    def test_status_reports_model(self):
        st, _h, raw = C.http("GET", PORT, "/v1/status", headers={"Authorization": "Bearer " + C.TOKEN})
        self.assertEqual(st, 200)
        body = json.loads(raw)
        self.assertEqual(body["state"], "ready")
        self.assertIn(body["device"], ("cuda", "cpu"))
        self.assertTrue(body["model"])

    def test_thai_and_english_accuracy(self):
        if "th_short" not in self.wavs or "en_short" not in self.wavs:
            self.skipTest("ไม่มีเสียง Pattara/Zira ในเครื่อง")
        refs = {s["name"]: s["text"] for s in self.bench.SAMPLES}
        for name, limit in (("th_short", 0.35), ("en_short", 0.2)):
            with open(self.wavs[name], "rb") as fh:
                st, obj, took = self.post(fh.read())
            self.assertEqual(st, 200, obj)
            self.assertEqual(obj["language"], name[:2])
            score = (self.bench.cer if name.startswith("th") else self.bench.wer)(refs[name], obj["text"])
            self.assertLess(score, limit, "%s: %s" % (name, obj["text"]))
            self.assertTrue(obj["segments"])
            for s in obj["segments"]:
                self.assertLessEqual(s["start"], s["end"])

    def test_browser_and_file_formats(self):
        if "en_short" not in self.wavs:
            self.skipTest("ไม่มีเสียง Zira")
        ff = C.import_local("tools_media")._ffmpeg()
        if not ff:
            self.skipTest("ไม่มี ffmpeg สำหรับแปลงไฟล์ทดสอบ")
        src = self.wavs["en_short"]
        for ext, args, ctype in ((".webm", ["-c:a", "libopus", "-b:a", "32k"], "audio/webm"),
                                 (".mp3", ["-c:a", "libmp3lame", "-q:a", "4"], "audio/mpeg"),
                                 (".m4a", ["-c:a", "aac", "-b:a", "64k"], "audio/mp4"),
                                 (".ogg", ["-c:a", "libopus", "-b:a", "24k"], "audio/ogg")):
            dst = os.path.join(self.tmp, "fmt" + ext)
            subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", src] + args + [dst],
                           check=True, capture_output=True, timeout=120)
            with open(dst, "rb") as fh:
                st, obj, _t = self.post(fh.read(), ctype)
            self.assertEqual(st, 200, (ext, obj))
            self.assertIn("inspection report", obj["text"].lower(), ext)

    def test_rejects_bad_input(self):
        st, obj, _t = self.post(b"#EXTM3U\n#EXTINF:1,\nfile:///C:/LLM/secrets/x\n", "application/octet-stream")
        self.assertEqual(st, 415, obj)
        st, obj, _t = self.post(b"RIFF\x00\x00\x00\x00WAVEgarbage" * 10)
        self.assertIn(st, (400, 415), obj)
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:                  # 70 วินาที > --max-seconds 60 ของเซิร์ฟเวอร์ทดสอบ
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 16000 * 70)
        st, obj, _t = self.post(buf.getvalue())
        self.assertEqual((st, obj.get("error")), (413, "too_long"))
        st, _h, _raw = C.http("POST", PORT, "/v1/transcribe", body=b"x", headers={"Content-Type": "audio/wav"})
        self.assertEqual(st, 401)

    def status(self):
        st, _h, raw = C.http("GET", PORT, "/v1/status", headers={"Authorization": "Bearer " + C.TOKEN})
        self.assertEqual(st, 200)
        return json.loads(raw)

    # ---- [fix 2026-10-06 voice] คำไทยสั้นต้องออกมาเป็นอักษรไทย (เดิม "โอเค" -> "오케이." ko), warm, อัตราสุ่มต่ำ = 415
    SHORT = [{"name": "th_ok", "voice": "Pattara", "text": "โอเค"},
             {"name": "th_khrap", "voice": "Pattara", "text": "ครับ"},
             {"name": "th_sawasdee", "voice": "Pattara", "text": "สวัสดี"},
             {"name": "en_yes", "voice": "Zira", "text": "Yes."}]

    def test_short_words_language(self):
        import re
        tmp = tempfile.mkdtemp(prefix="stt-short-", dir=C.TMP)
        wavs = self.bench.synthesize(tmp, self.SHORT)
        if len(wavs) < len(self.SHORT):
            self.skipTest("ไม่มีเสียง Pattara/Zira ในเครื่อง")
        for name, path in sorted(wavs.items()):
            with open(path, "rb") as fh:
                st, obj, _t = self.post(fh.read())
            self.assertEqual(st, 200, obj)
            self.assertEqual(obj["language"], name[:2], (name, obj))
            self.assertIn("detected", obj)
            if name.startswith("th"):
                self.assertRegex(obj["text"], r"[฀-๿]", (name, obj["text"]))
                self.assertIsNone(re.search(r"[가-힯぀-ヿ一-鿿]", obj["text"]), obj["text"])
            else:
                self.assertIn("yes", obj["text"].lower())
        with open(wavs["th_ok"], "rb") as fh:                       # ภาษาที่หน้าจอบอก (hint) ใช้เมื่อตรวจแล้วไม่แน่ใจ
            data = fh.read()
        conn_url = "/v1/transcribe?hint=en"
        st, _h, raw = C.http("POST", PORT, conn_url, body=data,
                             headers={"Authorization": "Bearer " + C.TOKEN, "Content-Type": "audio/wav"},
                             timeout=300)
        self.assertEqual((st, json.loads(raw)["language"]), (200, "en"))

    def test_warm_status_and_low_rate(self):
        import io
        import wave
        st, _h, raw = C.http("POST", PORT, "/v1/warm", headers={"Authorization": "Bearer " + C.TOKEN})
        self.assertEqual(st, 200, raw)
        self.assertIn(json.loads(raw)["action"], ("ready", "parked", "loading"))
        self.assertEqual(C.http("POST", PORT, "/v1/warm")[0], 401)
        body = self.status()
        self.assertIn(body["expect_device"], ("cuda", "cpu"))
        self.assertEqual(sorted(body["window_s"]), ["cpu", "cuda"])
        self.assertEqual(body["languages"], ["th", "en"])
        st, _h, raw = C.http("GET", PORT, "/health")
        self.assertIn(json.loads(raw)["device"], ("cuda", "cpu", ""))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:                              # 16 Hz: เดิมแปลงขึ้น 16 kHz = ขยาย 1,000 เท่า
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16)
            w.writeframes(b"\x01\x00" * 3000)
        st, obj, _t = self.post(buf.getvalue())
        self.assertEqual((st, obj.get("error")), (415, "unsupported_rate"))

    def test_gpu_weights_parked_after_job(self):
        # router ใช้ -fit on: VRAM ที่ STT ถือค้างตอนโมเดลแชตโหลด = โมเดลแชตได้ชั้นบน GPU น้อยลงทั้ง session
        if "en_short" not in self.wavs:
            self.skipTest("ไม่มีเสียง Zira")
        with open(self.wavs["en_short"], "rb") as fh:
            data = fh.read()
        st, obj, _t = self.post(data)
        self.assertEqual(st, 200, obj)
        if obj.get("device") != "cuda":
            self.skipTest("บริการรันบน CPU (VRAM ว่างไม่ถึง 1.5 GB ตอนนี้)")
        deadline = time.time() + 15
        while time.time() < deadline and not self.status().get("parked"):
            time.sleep(0.5)
        body = self.status()
        self.assertTrue(body["parked"], body)
        self.assertEqual(body["state"], "ready")
        parks = body["parks"]
        st, obj, _t = self.post(data)
        self.assertEqual(st, 200, obj)
        self.assertIn("inspection report", obj["text"].lower())
        if obj.get("device") == "cuda":
            self.assertFalse(self.status()["parked"])        # ย้ายกลับ GPU แล้ว ยังอยู่ในช่วง hold
        deadline = time.time() + 15
        while time.time() < deadline and self.status().get("parks", 0) <= parks and obj.get("device") == "cuda":
            time.sleep(0.5)
        if obj.get("device") == "cuda":
            self.assertGreater(self.status()["parks"], parks)

    def test_mcp_fast_transcribe_cache_and_kb(self):
        """ทางเต็ม: MCP server.py จริงบนพอร์ตว่าง -> tools_stt -> ffmpeg ตัดท่อน -> บริการถอดเสียงจริง -> แคช -> kb"""
        if "th_long" not in self.wavs or "en_short" not in self.wavs:
            self.skipTest("ไม่มีเสียง Pattara/Zira ในเครื่อง")
        ff = C.import_local("tools_media")._ffmpeg()
        if not ff:
            self.skipTest("ไม่มี ffmpeg")
        extract = C.import_local("extract")
        slug = "stt-live-" + os.urandom(3).hex()
        att = os.path.join(C.PROJECT_DATA, slug, "attachments")
        os.makedirs(att, exist_ok=True)
        mp3 = os.path.join(att, "ประชุม หน้างาน.mp3")
        mp4 = os.path.join(att, "site clip.mp4")
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", self.wavs["th_long"], "-c:a",
                        "libmp3lame", "-q:a", "4", mp3], check=True, capture_output=True, timeout=120)
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "color=c=black:s=64x64:d=11", "-i", self.wavs["en_short"], "-shortest", "-c:v", "libx264",
                        "-c:a", "aac", mp4], check=True, capture_output=True, timeout=120)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            mport = s.getsockname()[1]
        env = C.clean_env()
        env["QWEN_STT_URL"] = "http://127.0.0.1:%d" % PORT
        env["QWEN_KB_EMBED_URL"] = "http://127.0.0.1:9"      # ไม่แตะบริการ embedding จริง (kb ใช้ lexical)
        log = os.path.join(C.TMP, "mcp-stt-live.log")
        with open(log, "wb") as out:
            mcp = subprocess.Popen([sys.executable, os.path.join(C.MCP_LOCAL, "server.py"), str(mport)],
                                   cwd=C.MCP_LOCAL, env=env, stdout=out, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            deadline = time.time() + 60
            while time.time() < deadline and not C.port_in_use(mport):
                self.assertIsNone(mcp.poll(), "MCP ตายตอนเริ่ม ดู %s" % log)
                time.sleep(0.3)

            def call(args, timeout=300):
                st, _h, raw = C.http("POST", mport, "/fast/%s" % slug,
                                     {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": "local_read", "arguments": args}},
                                     {"Authorization": "Bearer " + C.TOKEN,
                                      "Accept": "application/json, text/event-stream"}, timeout=timeout)
                self.assertEqual(st, 200, raw[:300])
                return C.tool_text(raw)

            t0 = time.time()
            th = call({"action": "transcribe", "path": "ประชุม หน้างาน.mp3"})
            first_s = time.time() - t0
            self.assertTrue(th.startswith(extract.BANNER), th[:300])
            self.assertTrue(th.rstrip().endswith(extract.END_MARK))
            self.assertIn("ไฟล์: attachments/ประชุม หน้างาน.mp3", th)
            self.assertIn("ภาษา: ไทย (th)", th)
            self.assertIn("[00:00:00–", th)
            self.assertIn("กล้องถ่ายภาพความร้อน", th)
            t0 = time.time()
            again = call({"action": "transcribe", "path": "attachments/ประชุม หน้างาน.mp3"})
            self.assertEqual(again, th)
            self.assertLess(time.time() - t0, min(5.0, first_s))   # แคช kb\stt: ไม่ถอดใหม่
            en = call({"action": "transcribe", "path": "site clip.mp4"})
            self.assertIn("inspection report", en.lower())
            self.assertIn("ภาษา: อังกฤษ (en)", en)
            kb = call({"action": "kb", "query": "กล้องถ่ายภาพความร้อน", "mode": "lexical"})
            self.assertIn("ประชุม หน้างาน.mp3", kb)
            self.assertIn("(ถอดเสียง)", kb)
            with open(C.AUDIT_LOCAL, encoding="utf-8") as fh:
                audit = fh.read()
            self.assertIn("stt_transcribe", audit)
            self.assertNotIn("inspection report", audit.lower())     # audit มีแค่ path/sha/เวลา ไม่มีข้อความที่ถอดได้
            self.assertNotIn(C.TOKEN, audit)
        finally:
            if mcp.poll() is None:
                mcp.kill()                                   # เฉพาะโปรเซสที่เทสต์นี้เปิดเอง
                mcp.wait(20)


if __name__ == "__main__":
    unittest.main()
