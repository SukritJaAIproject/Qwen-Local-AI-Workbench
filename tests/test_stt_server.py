# -*- coding: utf-8 -*-
"""เทสต์บริการถอดเสียง C:\\LLM\\stt\\stt_server.py (batch 2b สัญญา C1, owner voice) — ไม่โหลดโมเดลจริง

ตรวจ (ด้วย engine/decoder ปลอม รันได้บน C:\\Python313 ที่ไม่มี PyAV/faster-whisper)
  * ด่าน HTTP: /health สาธารณะ (ไม่บอกอะไรนอกจากสถานะ), ที่เหลือต้องมี Bearer, Host ต้องเป็นของพอร์ตนี้ (DNS rebinding),
    Origin แปลกปลอม = 403, ไม่มี header CORS เลยแม้ Origin ของเรา, OPTIONS = 405
  * body: เกิน --max-bytes = 413 โดยไม่อ่าน, chunked = 411, ไม่มี Content-Length = 411, multipart/raw ได้ไฟล์เดียวกัน
    ทุกไบต์ (ไบต์ \\r\\n กลางข้อมูลไม่เพี้ยน), ช่อง language/max_seconds, language ผิดรูป = 400
  * ผลผิดพลาดของ decoder/engine -> 415/413/503(+Retry-After)/500 (ไม่มีรายละเอียดภายในในคำตอบ)
  * log ไม่มีข้อความที่ถอดได้และไม่มี token
  * Engine: คิวเต็ม = busy, ปลดโมเดลตอนว่าง, GPU พังกลางงาน = ถอดซ้ำบน CPU ในคำขอเดียว, multilingual เมื่อตรวจภาษาเอง
  * หาโมเดลจากโฟลเดอร์จริงเท่านั้น (ไฟล์ขาด/ว่าง = ข้าม), เลือกอุปกรณ์ตามเกณฑ์ VRAM 1.5 GB
  * ผูกเฉพาะ 127.0.0.1 + SO_EXCLUSIVEADDRUSE (โปรเซสที่สองผูกพอร์ตซ้ำไม่ได้), ปิดการต่อออกนอกเครื่อง (โปรเซสลูก)
"""
import http.client
import json
import os
import subprocess
import sys
import threading
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_security_common as C  # noqa: E402

STT_DIR = r"C:\LLM\stt"


def load_server():
    """import stt_server โดยไม่ทิ้งผลข้างเคียงไว้ในโปรเซสเทสต์ (มันตั้ง HF_* และบล็อก torch ใน sys.modules ตอน import)"""
    saved_env = dict(os.environ)
    saved_mods = {k: sys.modules.get(k, "__absent__") for k in
                  ("torch", "transformers", "tensorflow", "torchaudio", "torchvision", "jax", "flax")}
    if STT_DIR not in sys.path:
        sys.path.insert(0, STT_DIR)
    try:
        import stt_server
    finally:
        os.environ.clear()
        os.environ.update(saved_env)
        for k, v in saved_mods.items():
            if v == "__absent__":
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return stt_server


S = load_server()


class FakeEngine:
    """แทน Engine จริง: จำอาร์กิวเมนต์ล่าสุด และโยน error ตามที่เทสต์ตั้ง"""

    def __init__(self):
        self.calls = []
        self.hints = []
        self.warms = 0
        self.raise_exc = None
        self.text = "สวัสดีครับ ทดสอบ"
        self.state = "ready"
        self.block = None                       # threading.Event: transcribe รอจนกว่าเทสต์ปล่อย (เทสต์คิวเต็ม)

    def transcribe(self, audio, duration, language, hint=None):
        self.calls.append((audio, duration, language))
        self.hints.append(hint)
        if self.block is not None:
            self.block.wait(10)
        if self.raise_exc:
            raise self.raise_exc
        return {"text": self.text, "language": language or "th", "language_probability": 0.9,
                "duration": duration, "segments": [{"start": 0.0, "end": duration, "text": self.text}],
                "model": "fake", "device": "cpu", "compute_type": "int8", "elapsed_s": 0.01}

    def public_state(self):
        return self.state

    def status(self):
        return {"state": self.state, "model": "fake"}

    def warm(self):
        self.warms += 1
        return "loading"


class FakeDecoder:
    def __init__(self):
        self.calls = []
        self.raise_exc = None

    def __call__(self, data, max_seconds):
        self.calls.append((data, max_seconds))
        if self.raise_exc:
            raise self.raise_exc
        return ("PCM", 3.5)


def wav_bytes(seconds=0.5, rate=16000):
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\r\n\x00\n" * int(seconds * rate / 2))   # ไบต์ CR/LF ปนในข้อมูลเสียงโดยตั้งใจ
    return buf.getvalue()


class HttpBase(unittest.TestCase):
    MAX_BYTES = 200_000

    def setUp(self):
        self.engine = FakeEngine()
        self.decoder = FakeDecoder()
        self.logs = []
        self._orig_log = S.log
        S.log = lambda msg: self.logs.append(str(msg))
        self.srv = S.make_server(self.engine, 0, max_bytes=self.MAX_BYTES, max_seconds=600, decoder=self.decoder)
        self.port = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self.t.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        S.log = self._orig_log

    def req(self, method, path, body=None, headers=None, token=C.TOKEN, host=None):
        hdrs = dict(headers or {})
        if token is not None:
            hdrs["Authorization"] = "Bearer " + token
        return C.http(method, self.port, path, body, hdrs, host=host)


class HttpGateTests(HttpBase):
    def test_health_is_public_and_minimal(self):
        st, h, raw = self.req("GET", "/health", token=None)
        self.assertEqual(st, 200)
        body = json.loads(raw)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["state"], "ready")
        self.assertTrue(body["ready"])
        self.assertNotIn("model_path", body)          # รายละเอียดอยู่หลัง token เท่านั้น
        self.assertNotIn("access-control-allow-origin", h)

    def test_status_requires_token(self):
        self.assertEqual(self.req("GET", "/v1/status", token=None)[0], 401)
        self.assertEqual(self.req("GET", "/v1/status", token="0" * 64)[0], 401)
        st, _h, raw = self.req("GET", "/v1/status")
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(raw)["server"], "qwen-stt")

    def test_host_and_origin_checks(self):
        self.assertEqual(self.req("GET", "/health", host="evil.example:%d" % self.port)[0], 403)
        self.assertEqual(self.req("GET", "/v1/status", host="127.0.0.1:1")[0], 403)
        self.assertEqual(self.req("GET", "/v1/status", headers={"Origin": C.EVIL_ORIGIN})[0], 403)
        st, h, _ = self.req("GET", "/v1/status", headers={"Origin": C.ALLOWED_ORIGIN})
        self.assertEqual(st, 200)
        # ไม่มี CORS เลย: เบราว์เซอร์อ่านผลตรงไม่ได้ ทางของหน้าแชตคือ hub /_qwen/stt
        self.assertNotIn("access-control-allow-origin", h)

    def test_options_not_supported(self):
        st, h, _ = self.req("OPTIONS", "/v1/transcribe", token=None,
                            headers={"Origin": C.ALLOWED_ORIGIN, "Access-Control-Request-Method": "POST"})
        self.assertEqual(st, 405)
        self.assertNotIn("access-control-allow-origin", h)

    def test_post_without_token_is_rejected_before_reading(self):
        st, _h, _ = self.req("POST", "/v1/transcribe", body=wav_bytes(), token=None,
                             headers={"Content-Type": "audio/wav"})
        self.assertEqual(st, 401)
        self.assertEqual(self.decoder.calls, [])
        self.assertEqual(self.engine.calls, [])

    def test_unknown_routes(self):
        self.assertEqual(self.req("GET", "/v1/other")[0], 404)
        self.assertEqual(self.req("POST", "/v1/other", body=b"x", headers={"Content-Type": "audio/wav"})[0], 404)
        self.assertEqual(self.req("DELETE", "/v1/transcribe")[0], 405)


class HttpBodyTests(HttpBase):
    def test_raw_audio_roundtrip(self):
        data = wav_bytes()
        st, h, raw = self.req("POST", "/v1/transcribe", body=data, headers={"Content-Type": "audio/wav"})
        self.assertEqual(st, 200, raw)
        body = json.loads(raw)
        self.assertEqual(body["text"], "สวัสดีครับ ทดสอบ")
        self.assertEqual(body["segments"][0]["text"], "สวัสดีครับ ทดสอบ")
        self.assertEqual(self.decoder.calls[0][0], data)
        self.assertEqual(self.decoder.calls[0][1], 600.0)
        self.assertIsNone(self.engine.calls[0][2])       # auto
        self.assertIn("application/json", h["content-type"])

    def test_language_and_max_seconds_query(self):
        st, _h, _ = self.req("POST", "/v1/transcribe?language=TH&max_seconds=30", body=wav_bytes(),
                             headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(st, 200)
        self.assertEqual(self.engine.calls[-1][2], "th")
        self.assertEqual(self.decoder.calls[-1][1], 30.0)
        # เพิ่มเกินเพดานของเซิร์ฟเวอร์ไม่ได้
        self.req("POST", "/v1/transcribe?max_seconds=99999", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
        self.assertEqual(self.decoder.calls[-1][1], 600.0)
        self.req("POST", "/v1/transcribe?language=auto", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
        self.assertIsNone(self.engine.calls[-1][2])

    def test_bad_language(self):
        for lang in ("thai-lang", "../x", "t%20h"):
            st, _h, raw = self.req("POST", "/v1/transcribe?language=" + lang, body=wav_bytes(),
                                   headers={"Content-Type": "audio/wav"})
            self.assertEqual(st, 400, lang)
            self.assertEqual(json.loads(raw)["error"], "bad_language")

    def test_multipart_is_byte_exact(self):
        data = wav_bytes() + b"\r\n--notboundary\r\n\n\r"
        boundary = "----qwenTestBoundary7MA4YWxk"
        body = ("--%s\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nen\r\n"
                "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"rec.webm\"\r\n"
                "Content-Type: audio/webm\r\n\r\n" % (boundary, boundary)).encode() + data + \
               ("\r\n--%s--\r\n" % boundary).encode()
        st, _h, raw = self.req("POST", "/v1/transcribe", body=body,
                               headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
        self.assertEqual(st, 200, raw)
        self.assertEqual(self.decoder.calls[-1][0], data)
        self.assertEqual(self.engine.calls[-1][2], "en")

    def test_multipart_quoted_boundary_and_fallback_part(self):
        data = wav_bytes(0.2)
        b = "abc def"
        body = ("--%s\r\nContent-Disposition: form-data; name=\"blob\"; filename=\"a.wav\"\r\n\r\n" % b).encode() \
            + data + ("\r\n--%s--\r\n" % b).encode()
        st, _h, _ = self.req("POST", "/v1/transcribe", body=body,
                             headers={"Content-Type": "multipart/form-data; boundary=\"%s\"" % b})
        self.assertEqual(st, 200)
        self.assertEqual(self.decoder.calls[-1][0], data)

    def test_multipart_without_file(self):
        b = "zz"
        body = ("--%s\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nth\r\n--%s--\r\n" % (b, b)).encode()
        st, _h, raw = self.req("POST", "/v1/transcribe", body=body,
                               headers={"Content-Type": "multipart/form-data; boundary=%s" % b})
        self.assertEqual(st, 400)
        self.assertEqual(json.loads(raw)["error"], "no_file")

    def test_too_large_rejected_without_reading(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/v1/transcribe")
        conn.putheader("Authorization", "Bearer " + C.TOKEN)
        conn.putheader("Content-Type", "audio/wav")
        conn.putheader("Content-Length", str(self.MAX_BYTES + 1))
        conn.endheaders()                                 # ไม่ส่ง body เลย — เซิร์ฟเวอร์ต้องตอบทันที ไม่รออ่าน
        resp = conn.getresponse()
        self.assertEqual(resp.status, 413)
        self.assertEqual(json.loads(resp.read())["error"], "too_large")
        conn.close()
        self.assertEqual(self.decoder.calls, [])

    def test_chunked_and_missing_length(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/v1/transcribe")
        conn.putheader("Authorization", "Bearer " + C.TOKEN)
        conn.putheader("Transfer-Encoding", "chunked")
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 411)
        conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/v1/transcribe")
        conn.putheader("Authorization", "Bearer " + C.TOKEN)
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 411)
        conn.close()

    def test_decoder_errors_map_to_status(self):
        for exc, code in ((S.AudioError(415, "unsupported_format", "x"), 415),
                          (S.AudioError(413, "too_long", "x"), 413),
                          (S.AudioError(400, "decode_failed", "x"), 400)):
            self.decoder.raise_exc = exc
            st, _h, raw = self.req("POST", "/v1/transcribe", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
            self.assertEqual(st, code)
            self.assertEqual(json.loads(raw)["error"], exc.code)
        self.assertEqual(self.engine.calls, [])

    def test_engine_errors(self):
        self.engine.raise_exc = S.EngineBusy("queue full")
        st, h, raw = self.req("POST", "/v1/transcribe", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
        self.assertEqual((st, json.loads(raw)["error"]), (503, "busy"))
        self.assertIn("retry-after", h)
        self.engine.raise_exc = S.EngineUnavailable("no model")
        st, _h, raw = self.req("POST", "/v1/transcribe", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
        self.assertEqual((st, json.loads(raw)["error"]), (503, "unavailable"))
        self.engine.raise_exc = ValueError("secret internal detail C:\\path")
        st, _h, raw = self.req("POST", "/v1/transcribe", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
        self.assertEqual(st, 500)
        self.assertNotIn("secret internal detail", raw.decode("utf-8"))

    def test_logs_have_no_text_or_token(self):
        self.engine.text = "ข้อความลับของผู้ใช้ XYZZY"
        self.req("POST", "/v1/transcribe", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
        self.req("GET", "/v1/status", token="f" * 64)
        joined = "\n".join(self.logs)
        self.assertIn("200", joined)
        self.assertNotIn("XYZZY", joined)
        self.assertNotIn(C.TOKEN, joined)
        self.assertNotIn("f" * 64, joined)


class HelperTests(unittest.TestCase):
    def test_sniff_format(self):
        cases = {
            b"RIFF\x00\x00\x00\x00WAVEfmt ": "wav", b"OggS\x00\x02" + b"\x00" * 10: "ogg",
            b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81": "matroska", b"\x00\x00\x00\x20ftypM4A ": "mov",
            b"fLaC\x00\x00\x00\x22": "flac", b"ID3\x04\x00\x00": "mp3", b"\xff\xfb\x90\x64": "mp3",
            b"\xff\xf1\x50\x80": "aac", b"#EXTM3U\n#EXT-X-VERSION:3": None, b"ffconcat version 1.0": None,
            b"<?xml version": None, b"": None,
        }
        for head, want in cases.items():
            self.assertEqual(S.sniff_format(head), want, head)

    def test_decode_rejects_unknown_before_pyav(self):
        # รายการเล่น HLS ต้องถูกปฏิเสธจาก magic bytes ก่อนถึง PyAV/ffmpeg (ที่อาจไปเปิดไฟล์/URL อื่นต่อ)
        fake_av = types.ModuleType("av")
        fake_av.open = lambda *a, **k: (_ for _ in ()).throw(AssertionError("PyAV must not be called"))
        saved = sys.modules.get("av")
        sys.modules["av"] = fake_av
        try:
            with self.assertRaises(S.AudioError) as cm:
                S.decode_audio(b"#EXTM3U\n#EXTINF:1,\nhttp://127.0.0.1:8100/x\n", 60)
            self.assertEqual(cm.exception.status, 415)
            with self.assertRaises(S.AudioError) as cm:
                S.decode_audio(b"", 60)
            self.assertEqual(cm.exception.status, 400)
        finally:
            if saved is None:
                sys.modules.pop("av", None)
            else:
                sys.modules["av"] = saved

    def test_find_model_only_real_folders(self):
        root = C.new_dir("sttmodels")
        good = os.path.join(root, "large-v3-turbo")
        bad = os.path.join(root, "small")
        for d in (good, bad):
            os.makedirs(d)
        with open(os.path.join(good, "model.bin"), "wb") as fh:
            fh.write(b"\x01" * (1024 * 1024 + 10))
        for n in ("config.json", "tokenizer.json"):
            with open(os.path.join(good, n), "w") as fh:
                fh.write("{}")
            with open(os.path.join(bad, n), "w") as fh:
                fh.write("{}")
        with open(os.path.join(bad, "model.bin"), "wb"):
            pass                                          # ไฟล์ว่าง = ไม่ใช่โมเดลที่ใช้ได้
        old = os.environ.get("QWEN_STT_MODELS_DIR")
        os.environ["QWEN_STT_MODELS_DIR"] = root
        try:
            self.assertEqual(S.find_model("large-v3-turbo"), ("large-v3-turbo", good))
            got = S.find_model("small")
            self.assertTrue(got is None or os.path.normcase(got[1]) != os.path.normcase(bad))
            self.assertEqual(S.find_model(good), ("large-v3-turbo", good))
            self.assertIsNone(S.find_model(bad))
            self.assertIsNone(S.find_model(os.path.join(root, "missing")))
        finally:
            if old is None:
                os.environ.pop("QWEN_STT_MODELS_DIR", None)
            else:
                os.environ["QWEN_STT_MODELS_DIR"] = old

    def test_choose_device_threshold(self):
        fake_ct2 = types.ModuleType("ctranslate2")
        fake_ct2.get_cuda_device_count = lambda: 1
        saved = sys.modules.get("ctranslate2")
        sys.modules["ctranslate2"] = fake_ct2
        orig_free, orig_prep = S.gpu_free_mb, S.prepare_cuda
        try:
            S.prepare_cuda = lambda: True
            S.gpu_free_mb = lambda timeout=8.0: 1825
            self.assertEqual(S.choose_device("auto", 1536)[:2], ("cuda", "int8_float16"))
            S.gpu_free_mb = lambda timeout=8.0: 1400
            self.assertEqual(S.choose_device("auto", 1536)[:2], ("cpu", "int8"))
            S.gpu_free_mb = lambda timeout=8.0: None
            self.assertEqual(S.choose_device("auto", 1536)[:2], ("cpu", "int8"))
            self.assertEqual(S.choose_device("cpu", 0)[:2], ("cpu", "int8"))
            S.gpu_free_mb = lambda timeout=8.0: 5000
            S.prepare_cuda = lambda: False                 # หา cuBLAS ไม่เจอ = GPU ใช้ไม่ได้จริง
            self.assertEqual(S.choose_device("auto", 1536)[:2], ("cpu", "int8"))
            fake_ct2.get_cuda_device_count = lambda: 0
            S.prepare_cuda = lambda: True
            self.assertEqual(S.choose_device("auto", 1536)[:2], ("cpu", "int8"))
        finally:
            S.gpu_free_mb, S.prepare_cuda = orig_free, orig_prep
            if saved is None:
                sys.modules.pop("ctranslate2", None)
            else:
                sys.modules["ctranslate2"] = saved

    def test_dropped_connections_are_not_logged_as_errors(self):
        srv = S.make_server(FakeEngine(), 0)
        logs = []
        orig = S.log
        S.log = lambda m: logs.append(m)
        try:
            for exc in (ConnectionResetError(10054, "reset"), ConnectionAbortedError(), TimeoutError()):
                try:
                    raise exc
                except Exception:              # noqa: BLE001
                    srv.handle_error(None, ("127.0.0.1", 1))
            self.assertEqual(logs, [])
            try:
                raise ValueError("unexpected")
            except ValueError:
                srv.handle_error(None, ("127.0.0.1", 1))
            self.assertEqual(len(logs), 1)
        finally:
            S.log = orig
            srv.server_close()

    def test_binds_loopback_exclusively(self):
        srv = S.make_server(FakeEngine(), 0)
        try:
            self.assertEqual(srv.server_address[0], "127.0.0.1")
            with self.assertRaises(OSError):
                S.make_server(FakeEngine(), srv.server_address[1]).server_close()
        finally:
            srv.server_close()

    def test_forbid_outbound_in_child(self):
        code = (
            "import sys, socket\n"
            "sys.path.insert(0, %r)\n"
            "import stt_server as S\n"
            "S.forbid_outbound()\n"
            "srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1)\n"
            "c = socket.create_connection(srv.getsockname(), timeout=2); c.close()\n"
            "try:\n"
            "    socket.create_connection(('192.0.2.1', 80), timeout=2)\n"
            "    print('LEAK')\n"
            "except OSError as e:\n"
            "    print('BLOCKED' if 'disabled' in str(e) else 'OTHER ' + str(e))\n"
            "s = socket.socket(); print('EX', s.connect_ex(('192.0.2.1', 80)))\n" % STT_DIR)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                           env=C.clean_env(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertIn("BLOCKED", r.stdout, r.stderr)
        self.assertIn("EX 10013", r.stdout)

    def test_import_blocks_torch_only_in_service(self):
        # บริการต้องไม่ลาก torch/transformers (79 วินาที + 1.5 GB) — ตรวจในโปรเซสลูก ไม่ใช่โปรเซสเทสต์
        code = ("import sys; sys.path.insert(0, %r)\nimport stt_server\n"
                "print(sys.modules.get('torch', 'missing') is None, sys.modules.get('transformers', 'm') is None)\n"
                % STT_DIR)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                           env=C.clean_env(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(r.stdout.strip(), "True True", r.stderr)


class FakeInner:
    """ctranslate2.models.Whisper ปลอม: ย้ายน้ำหนักระหว่าง GPU/RAM (จอด/ย้ายกลับ) + โยน error ได้"""

    def __init__(self):
        self.unloads, self.loads = [], 0
        self.fail_unload = self.fail_load = None

    def unload_model(self, to_cpu=False):
        if self.fail_unload:
            raise self.fail_unload
        self.unloads.append(to_cpu)

    def load_model(self, keep_cache=False):
        if self.fail_load:
            raise self.fail_load
        self.loads += 1


class FakeWhisper:
    """โมเดล faster-whisper ปลอม: จำอาร์กิวเมนต์ + โยน error ได้"""

    def __init__(self, fail=None, detected="th", prob=0.91):
        self.fail = fail
        self.detected = detected
        self.prob = prob
        self.kwargs = []
        self.model = FakeInner()

    def transcribe(self, audio, **kw):
        self.kwargs.append(kw)
        if self.fail:
            raise self.fail
        seg = types.SimpleNamespace(start=0.0, end=1.5, text="  สวัสดี  ครับ ")
        lang = kw.get("language") or self.detected
        # เหมือน faster-whisper 1.2: ภาษาที่สั่งเอง = prob 1, ไม่มี all_language_probs; ตรวจเอง = มีทั้งรายการ
        if kw.get("language"):
            return iter([seg]), types.SimpleNamespace(language=lang, language_probability=1.0,
                                                      all_language_probs=None)
        probs = {"th": 0.001, "en": 0.05}
        probs[self.detected] = self.prob
        allp = sorted(probs.items(), key=lambda kv: -kv[1])
        return iter([seg]), types.SimpleNamespace(language=lang, language_probability=self.prob,
                                                  all_language_probs=allp)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self._orig_log = S.log
        self.logs = []
        S.log = lambda msg: self.logs.append(str(msg))

    def tearDown(self):
        S.log = self._orig_log

    def make(self, **kw):
        eng = S.Engine.__new__(S.Engine)
        S.Engine.__init__(eng, model=r"C:\definitely\missing\model", **kw)
        eng.path, eng.name = "fake-path", "fake"
        eng.state = "idle"
        loads = []

        def fake_load(choice=None):
            loads.append(eng.force_cpu)
            eng.model = FakeWhisper()
            eng.parked = False
            if eng.force_cpu:
                eng.device = "cpu"
            elif choice is not None:
                eng.device = choice[0]
            else:
                eng.device = getattr(eng, "_next_device", "cpu")
            eng.state = "ready"
        eng.load = fake_load
        eng._loads = loads
        return eng

    def test_transcribe_cleans_text_and_language_strategy(self):
        eng = self.make()
        out = eng.transcribe("pcm", 1.5, None)
        self.assertEqual(out["text"], "สวัสดี ครับ")
        self.assertEqual(out["segments"], [{"start": 0.0, "end": 1.5, "text": "สวัสดี ครับ"}])
        self.assertEqual(len(eng.model.kwargs), 1)
        self.assertFalse(eng.model.kwargs[-1]["multilingual"])
        self.assertTrue(eng.model.kwargs[-1]["vad_filter"])
        self.assertFalse(eng.model.kwargs[-1]["condition_on_previous_text"])
        self.assertEqual(eng.model.kwargs[-1]["beam_size"], 1)       # CPU: beam 1 (วัดแล้วแม่นเท่า beam 5)
        # คลิปยาว 30 วินาทีแรกเป็นไทย = ล็อกไทย ถอดรอบเดียว
        eng.model.kwargs.clear()
        eng.transcribe("pcm", 90.0, None)
        self.assertEqual(len(eng.model.kwargs), 1)
        # คลิปยาวที่ขึ้นต้นด้วยภาษาอื่น = ถอดใหม่แบบ multilingual (ช่วงไทยที่ตามมาไม่ถูกบังคับเป็นอังกฤษ)
        eng.model.detected = "en"
        eng.model.kwargs.clear()
        out = eng.transcribe("pcm", 90.0, None)
        self.assertEqual([k["multilingual"] for k in eng.model.kwargs], [False, True])
        self.assertEqual(out["language"], "en")
        # คลิปสั้น (หน้าต่างเดียว) ไม่ถอดซ้ำ, ภาษาที่ระบุเองไม่ตรวจซ้ำ
        eng.model.kwargs.clear()
        eng.transcribe("pcm", 20.0, None)
        eng.transcribe("pcm", 90.0, "en")
        self.assertEqual([k["multilingual"] for k in eng.model.kwargs], [False, False])
        self.assertEqual(eng.model.kwargs[-1]["language"], "en")

    def test_silence_short_circuit(self):
        eng = self.make()
        out = eng.transcribe("pcm", 0.0, None)
        self.assertEqual(out["text"], "")
        self.assertEqual(out["segments"], [])

    def test_queue_full_is_busy(self):
        eng = self.make(queue_max=0, queue_wait=0.2)
        eng._run.acquire()
        try:
            with self.assertRaises(S.EngineBusy):
                eng.transcribe("pcm", 1.0, None)          # ช่องเดียวถูกงานนี้ถือ แต่ _run ถูกถือ -> รอ 0.2 วิแล้ว busy
            eng2 = self.make(queue_max=0, queue_wait=5)
            eng2._slots.acquire()
            t0 = time.monotonic()
            with self.assertRaises(S.EngineBusy):
                eng2.transcribe("pcm", 1.0, None)         # ไม่มีช่องว่างเลย = busy ทันที ไม่รอ
            self.assertLess(time.monotonic() - t0, 1.0)
        finally:
            eng._run.release()

    def test_gpu_failure_retries_on_cpu_in_same_request(self):
        eng = self.make()
        eng._next_device = "cuda"
        eng.load()
        eng.model = FakeWhisper(fail=RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"))
        out = eng.transcribe("pcm", 1.5, None)
        self.assertEqual(out["text"], "สวัสดี ครับ")
        self.assertTrue(eng.force_cpu)
        self.assertEqual(eng.device, "cpu")
        self.assertEqual(eng._loads[-1], True)
        # ปลดตอนว่างแล้วล้าง force_cpu (รอบหน้าเลือกอุปกรณ์ใหม่ตาม VRAM)
        self.assertTrue(eng.unload("idle"))
        self.assertFalse(eng.force_cpu)
        self.assertIsNone(eng.model)

    def test_cpu_failure_propagates(self):
        eng = self.make()
        eng.load()
        eng.model = FakeWhisper(fail=RuntimeError("boom"))
        with self.assertRaises(RuntimeError):
            eng.transcribe("pcm", 1.5, None)

    def test_idle_unload(self):
        eng = self.make(idle_unload_min=0.001)
        eng.load()
        eng.last_used = time.monotonic() - 10
        eng.idle_tick()
        self.assertIsNone(eng.model)
        self.assertEqual(eng.public_state(), "idle")
        eng.transcribe("pcm", 1.0, None)                  # โหลดใหม่เองเมื่อมีงาน
        self.assertIsNotNone(eng.model)
        eng0 = self.make(idle_unload_min=0)
        eng0.load()
        eng0.last_used = time.monotonic() - 10 ** 6
        eng0.idle_tick()
        self.assertIsNotNone(eng0.model)                  # 0 = ไม่ปลด

    def test_no_model_state(self):
        eng = S.Engine(model=r"C:\definitely\missing\model")
        self.assertEqual(eng.public_state(), "no_model")
        with self.assertRaises(S.EngineUnavailable):
            eng.load()


class EngineParkTests(unittest.TestCase):
    """จอดน้ำหนักโมเดล GPU ไว้ใน RAM หลังงาน (คืน VRAM ให้ -fit ของโมเดลแชต) และเลือกอุปกรณ์ใหม่ทุกงานตาม VRAM ที่ว่าง
    (ไม่สืบทอด EngineTests — เทสต์ชุดนั้นคาดว่าเป็น CPU แต่ที่นี่ choose_device ปลอมตอบ GPU)"""

    GPU_OK = ("cuda", "int8_float16", "free VRAM 5000 MB >= 1536")
    GPU_FULL = ("cpu", "int8", "free VRAM 900 MB < 1536")
    make = EngineTests.make

    def setUp(self):
        self._orig_log = S.log
        self.logs = []
        S.log = lambda msg: self.logs.append(str(msg))
        self._orig_choose = S.choose_device
        self.choice = self.GPU_OK
        self.choose_calls = []

        def fake_choose(requested, min_free_mb):
            self.choose_calls.append(requested)
            return self.choice
        S.choose_device = fake_choose

    def tearDown(self):
        S.choose_device = self._orig_choose
        S.log = self._orig_log

    def gpu_engine(self, **kw):
        eng = self.make(**kw)
        eng.transcribe("pcm", 1.5, None)                   # โหลดครั้งแรกตาม VRAM ที่ว่าง -> GPU
        self.assertEqual((eng.device, eng.parked, len(eng._loads)), ("cuda", False, 1))
        return eng

    def idle(self, eng, seconds=10.0):
        eng.last_used = time.monotonic() - seconds
        eng.idle_tick()

    def test_parks_after_hold_and_resumes_without_reload(self):
        eng = self.gpu_engine(gpu_hold_s=2.0)
        inner = eng.model.model
        self.idle(eng, 0.5)
        self.assertFalse(eng.parked)                        # ยังอยู่ในช่วง hold (ท่อนถัดไปของ MCP มาใน ~1 วิ)
        self.idle(eng, 3.0)
        self.assertTrue(eng.parked)
        self.assertEqual(inner.unloads, [True])             # to_cpu=True = เก็บน้ำหนักไว้ใน RAM ไม่ใช่ทิ้ง
        self.assertEqual(eng.public_state(), "ready")       # จอดอยู่ก็ยังพร้อม (/health ready)
        self.assertTrue(eng.status()["parked"])
        self.idle(eng, 5.0)
        self.assertEqual(inner.unloads, [True])             # จอดซ้ำไม่ได้
        out = eng.transcribe("pcm", 1.5, None)
        self.assertEqual(out["device"], "cuda")
        self.assertEqual(inner.loads, 1)                    # ย้ายกลับ GPU (~0.25 วิ) ไม่โหลดไฟล์ใหม่
        self.assertEqual(len(eng._loads), 1)
        self.assertFalse(eng.parked)
        self.assertEqual(eng.parks, 1)

    def test_no_vram_check_while_still_holding_gpu(self):
        eng = self.gpu_engine(gpu_hold_s=60)
        n = len(self.choose_calls)
        eng.transcribe("pcm", 1.5, None)
        # ยังถือ VRAM อยู่: ค่าว่างที่อ่านได้ตอนนี้ไม่นับส่วนของเราเอง จะได้ "ไม่พอ" ผิดๆ แล้วสลับไป CPU เปล่าๆ
        self.assertEqual(len(self.choose_calls), n)
        self.assertEqual(eng.device, "cuda")

    def test_parked_and_vram_taken_switches_to_cpu(self):
        eng = self.gpu_engine(gpu_hold_s=0)
        self.idle(eng, 1.0)
        self.assertTrue(eng.parked)
        self.choice = self.GPU_FULL                          # โมเดลแชต (เช่น 27B) โหลดเต็ม VRAM ระหว่างนั้น
        out = eng.transcribe("pcm", 1.5, None)
        self.assertEqual(out["device"], "cpu")
        self.assertEqual(len(eng._loads), 2)                 # ทิ้งตัวที่จอดไว้ก่อน (ไม่ถือสองตัว = RAM ~6.5 GB)
        self.assertFalse(eng.parked)
        self.idle(eng, 5.0)
        self.assertEqual(eng.device, "cpu")                  # CPU ไม่มีอะไรต้องจอด
        # VRAM กลับมาว่าง (ปลดโมเดลแชต) -> งานถัดไปสลับขึ้น GPU เอง
        self.choice = self.GPU_OK
        out = eng.transcribe("pcm", 1.5, None)
        self.assertEqual(out["device"], "cuda")
        self.assertEqual(len(eng._loads), 3)

    def test_cpu_stays_cpu_while_vram_is_short(self):
        self.choice = self.GPU_FULL
        eng = self.make()
        eng.transcribe("pcm", 1.5, None)
        eng.transcribe("pcm", 1.5, None)
        self.assertEqual((eng.device, len(eng._loads)), ("cpu", 1))   # ไม่โหลดซ้ำทุกงาน

    def test_forced_cpu_skips_vram_checks(self):
        eng = self.make(device="cpu")
        self.choice = ("cpu", "int8", "requested cpu")
        eng.transcribe("pcm", 1.5, None)
        n = len(self.choose_calls)
        eng.transcribe("pcm", 1.5, None)
        self.assertEqual(len(self.choose_calls), n)

    def test_negative_hold_never_parks(self):
        eng = self.gpu_engine(gpu_hold_s=-1)
        self.idle(eng, 600.0)
        self.assertFalse(eng.parked)

    def test_no_park_while_a_job_runs(self):
        eng = self.gpu_engine(gpu_hold_s=0)
        eng._run.acquire()
        try:
            self.idle(eng, 5.0)
            self.assertFalse(eng.parked)
        finally:
            eng._run.release()
        self.idle(eng, 5.0)
        self.assertTrue(eng.parked)

    def test_park_failure_unloads_fully(self):
        eng = self.gpu_engine(gpu_hold_s=0)
        eng.model.model.fail_unload = RuntimeError("cannot move")
        self.idle(eng, 1.0)
        self.assertIsNone(eng.model)                         # เป้าหมายคือไม่ถือ VRAM ตอนว่าง
        self.assertFalse(eng.parked)
        self.assertEqual(eng.public_state(), "idle")
        eng.transcribe("pcm", 1.5, None)                     # โหลดใหม่ได้ตามปกติ
        self.assertEqual(len(eng._loads), 2)

    def test_resume_failure_falls_back_to_cpu(self):
        eng = self.gpu_engine(gpu_hold_s=0)
        self.idle(eng, 1.0)
        eng.model.model.fail_load = RuntimeError("CUDA failed with error out of memory")
        out = eng.transcribe("pcm", 1.5, None)
        self.assertEqual(out["device"], "cpu")
        self.assertEqual(len(eng._loads), 2)

    def test_idle_unload_also_drops_parked_model(self):
        eng = self.gpu_engine(gpu_hold_s=0, idle_unload_min=1)
        self.idle(eng, 1.0)
        self.assertTrue(eng.parked)
        self.idle(eng, 120.0)
        self.assertIsNone(eng.model)
        self.assertFalse(eng.parked)


# =============================================================== รอบแก้ 2026-10-06 (fixer voice)
class LanguageChoiceTests(unittest.TestCase):
    """คำไทยสั้นถูก whisper ตรวจเป็นเกาหลี/ญี่ปุ่น/เวียดนาม/อังกฤษไม่มั่นใจ -> ต้องถอดเป็นไทย (ภาษาสำรอง) ไม่ใช่อักษรอื่น
    ตัวเลขในเคสมาจากการวัดจริง (เสียง Pattara/Zira 1-2 วินาที, large-v3-turbo)"""

    ALLOWED = ("th", "en")

    def pick(self, det, prob, dur=1.4, fallback="th"):
        return S.choose_language(det, prob, dur, self.ALLOWED, fallback, "th")[0]

    def test_short_clip_matrix(self):
        self.assertEqual(self.pick("ko", 0.38), "th")      # "โอเค" -> "오케이." (ผลจริงของผู้รีวิว)
        self.assertEqual(self.pick("ja", 0.375), "th")     # "โอเค" -> "OK"
        self.assertEqual(self.pick("vi", 0.973), "th")     # "ไม่ใช่" -> "Mời chạy." (มั่นใจแต่อยู่นอกชุด)
        self.assertEqual(self.pick("en", 0.753), "th")     # "ครับ" -> "Crap."
        self.assertEqual(self.pick("en", 0.625), "th")     # "ไม่" -> "Bye."
        self.assertEqual(self.pick("en", 0.965), "en")     # "Okay." (อังกฤษจริงที่ต่ำที่สุดในชุดวัด)
        self.assertEqual(self.pick("en", 1.0), "en")
        self.assertEqual(self.pick("th", 0.2), "th")
        self.assertEqual(self.pick("", 0.0), "th")
        # หน้าจอภาษาอังกฤษ (hint=en): ภาษาสำรองเป็นอังกฤษ
        self.assertEqual(self.pick("ko", 0.38, fallback="en"), "en")
        self.assertEqual(self.pick("en", 0.6, fallback="en"), "en")
        self.assertEqual(self.pick("th", 0.5, fallback="en"), "en")
        self.assertEqual(self.pick("th", 0.95, fallback="en"), "th")

    def test_long_clip_keeps_multilingual_strategy(self):
        self.assertEqual(self.pick("th", 0.5, dur=90), "th")          # ล็อกภาษาหลัก
        self.assertIsNone(self.pick("en", 0.99, dur=90))               # อีกภาษาในชุด = multilingual (เหมือนเดิม)
        self.assertIsNone(self.pick("en", 0.6, dur=90))
        self.assertEqual(self.pick("ko", 0.9, dur=90), "th")           # นอกชุด = ภาษาสำรอง
        self.assertEqual(self.pick("ko", 0.9, dur=90, fallback="en"), "en")

    def test_no_limit_behaves_like_before(self):
        self.assertEqual(S.choose_language("ko", 0.4, 1.4, (), "th", "th")[0], "ko")
        self.assertIsNone(S.choose_language("ko", 0.4, 90, (), "th", "th")[0])
        self.assertEqual(S.choose_language("th", 0.4, 90, (), "th", "th")[0], "th")


class EngineLanguageTests(unittest.TestCase):
    make = EngineTests.make
    setUp = EngineTests.setUp
    tearDown = EngineTests.tearDown

    def engine(self, detected, prob, **kw):
        eng = self.make(**kw)
        eng.load()
        eng.model = FakeWhisper(detected=detected, prob=prob)
        return eng

    def test_outside_set_reruns_in_primary(self):
        eng = self.engine("ko", 0.38)
        out = eng.transcribe("pcm", 1.4, None)
        self.assertEqual([k["language"] for k in eng.model.kwargs], [None, "th"])
        self.assertEqual(out["language"], "th")
        self.assertEqual(out["language_probability"], 0.001)          # ของตัวตรวจ ไม่ใช่ 1.0 ที่สั่งเอง
        self.assertEqual(out["detected"]["language"], "ko")
        self.assertIn("outside", out["detected"]["rule"])
        self.assertTrue(any("language auto ko" in m for m in self.logs))
        self.assertFalse(any("สวัสดี" in m for m in self.logs))      # log ไม่มีข้อความที่ถอดได้

    def test_unsure_english_short_clip(self):
        eng = self.engine("en", 0.75)
        out = eng.transcribe("pcm", 1.1, None)
        self.assertEqual(out["language"], "th")
        eng = self.engine("en", 0.97)
        out = eng.transcribe("pcm", 1.1, None)
        self.assertEqual((out["language"], len(eng.model.kwargs)), ("en", 1))   # มั่นใจ = ไม่ถอดซ้ำ

    def test_hint_and_explicit_language(self):
        eng = self.engine("ko", 0.38)
        out = eng.transcribe("pcm", 1.4, None, hint="en")
        self.assertEqual(out["language"], "en")
        eng = self.engine("ko", 0.38)
        out = eng.transcribe("pcm", 1.4, None, hint="ko")              # hint นอกชุด = ไม่สนใจ ใช้ภาษาหลัก
        self.assertEqual(out["language"], "th")
        eng = self.engine("ko", 0.38)
        out = eng.transcribe("pcm", 1.4, "ko")                          # สั่งภาษาเอง = ไม่ตรวจ ไม่จำกัด
        self.assertEqual([k["language"] for k in eng.model.kwargs], ["ko"])
        self.assertNotIn("detected", out)

    def test_long_clip_outside_set_locks_fallback(self):
        eng = self.engine("ko", 0.9)
        eng.transcribe("pcm", 90.0, None)
        self.assertEqual([(k["language"], k["multilingual"]) for k in eng.model.kwargs], [(None, False), ("th", False)])

    def test_languages_option(self):
        eng = self.make(languages=("en",), primary_language="th")
        self.assertEqual(eng.languages, ("th", "en"))                  # ภาษาหลักอยู่ในชุดเสมอ
        eng = self.make(languages=(), primary_language="th")
        eng.load()
        eng.model = FakeWhisper(detected="ko", prob=0.38)
        self.assertEqual(eng.transcribe("pcm", 1.4, None)["language"], "ko")   # ไม่จำกัด = แบบเดิม

    def test_speed_window_average(self):
        eng = self.make()
        self.assertEqual(eng.window_s["cpu"], S.WINDOW_S_DEFAULT["cpu"])
        eng._note_speed("cpu", 3.0, 40.0)                              # คลิปสั้น = 1 หน้าต่าง
        self.assertEqual(eng.window_s["cpu"], 40.0)
        eng._note_speed("cpu", 60.0, 40.0)                             # 2 หน้าต่าง = 20 วิ/หน้าต่าง
        self.assertEqual(eng.window_s["cpu"], 34.0)
        st = eng.status()
        self.assertEqual(st["window_s"]["cpu"], 34.0)
        self.assertTrue(st["window_measured"]["cpu"])
        self.assertEqual(st["languages"], ["th", "en"])


class EngineWarmTests(unittest.TestCase):
    """POST /v1/warm: โหลดโมเดลเบื้องหลังตอนผู้ใช้เริ่มอัด (ตัดเวลาโหลดหลังปลดตอนว่าง 13-23 วิ ออกจากเวลารอ)"""
    GPU_OK, GPU_FULL = EngineParkTests.GPU_OK, EngineParkTests.GPU_FULL
    make = EngineTests.make
    setUp = EngineParkTests.setUp
    tearDown = EngineParkTests.tearDown

    def wait_warm(self, eng):
        t0 = time.monotonic()
        while eng._warming and time.monotonic() - t0 < 5:
            time.sleep(0.02)
        self.assertFalse(eng._warming)

    def test_warm_loads_then_parks_on_gpu(self):
        eng = self.make(gpu_hold_s=2.0)
        self.assertEqual(eng.warm(), "loading")
        self.wait_warm(eng)
        self.assertIsNotNone(eng.model)
        self.assertEqual(eng.device, "cuda")
        self.assertTrue(eng.parked)                                    # ไม่ถือ VRAM ระหว่างผู้ใช้พูด
        self.assertEqual(eng.model.model.unloads, [True])
        self.assertEqual(eng.warm(), "parked")                         # เรียกซ้ำ = ไม่ทำอะไร
        out = eng.transcribe("pcm", 1.5, None)                         # งานจริง: ย้ายกลับ GPU ไม่โหลดใหม่
        self.assertEqual((out["device"], len(eng._loads), eng.model.model.loads), ("cuda", 1, 1))

    def test_warm_on_cpu_and_negative_hold(self):
        self.choice = self.GPU_FULL
        eng = self.make()
        eng.warm()
        self.wait_warm(eng)
        self.assertEqual((eng.device, eng.parked), ("cpu", False))
        n = len(eng._loads)
        self.assertEqual(eng.warm(), "ready")                          # CPU: ตรวจว่า VRAM ว่างแล้วหรือยัง
        self.wait_warm(eng)
        self.assertEqual(len(eng._loads), n)                           # ยังไม่ว่าง = ไม่โหลดซ้ำ
        self.choice = self.GPU_OK
        eng.warm()
        self.wait_warm(eng)
        self.assertEqual((eng.device, eng.parked), ("cuda", True))     # ว่างแล้ว = สลับขึ้น GPU แล้วจอด
        eng2 = self.make(gpu_hold_s=-1)
        eng2.warm()
        self.wait_warm(eng2)
        self.assertEqual((eng2.device, eng2.parked), ("cuda", False))  # ค่าลบ = ไม่จอดเลย (ตามที่ผู้ดูแลสั่ง)

    def test_warm_skips_while_a_job_runs_and_no_model(self):
        eng = self.make()
        eng._run.acquire()
        try:
            eng.warm()
            self.wait_warm(eng)
            self.assertIsNone(eng.model)                               # งานที่ถืออยู่จะโหลดเอง
        finally:
            eng._run.release()
        none = S.Engine(model=r"C:\definitely\missing\model")
        self.assertEqual(none.warm(), "no_model")

    def test_expect_device(self):
        eng = self.make()
        self.assertEqual(eng.expect_device()[0], "cuda")
        self.choice = self.GPU_FULL
        self.assertEqual(eng.expect_device()[0], "cuda")               # จำผล nvidia-smi ไว้ 5 วิ
        eng._expect = (0.0, "", "")
        self.assertEqual(eng.expect_device()[0], "cpu")
        st = eng.status_full()
        self.assertEqual((st["expect_device"], st["state"]), ("cpu", "idle"))


class HttpFixTests(HttpBase):
    def test_hint_is_passed_and_sanitized(self):
        self.req("POST", "/v1/transcribe?hint=EN", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
        self.assertEqual(self.engine.hints[-1], "en")
        self.req("POST", "/v1/transcribe?hint=../x", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
        self.assertIsNone(self.engine.hints[-1])
        b = "hb"
        body = ("--%s\r\nContent-Disposition: form-data; name=\"hint\"\r\n\r\nth\r\n--%s\r\nContent-Disposition: "
                "form-data; name=\"file\"; filename=\"a.webm\"\r\n\r\n" % (b, b)).encode() + wav_bytes() + \
            ("\r\n--%s--\r\n" % b).encode()
        st, _h, _ = self.req("POST", "/v1/transcribe", body=body,
                             headers={"Content-Type": "multipart/form-data; boundary=%s" % b})
        self.assertEqual((st, self.engine.hints[-1]), (200, "th"))

    def test_warm_needs_token_and_answers_fast(self):
        self.assertEqual(self.req("POST", "/v1/warm", token=None)[0], 401)
        self.assertEqual(self.req("POST", "/v1/warm", headers={"Origin": C.EVIL_ORIGIN})[0], 403)
        st, _h, raw = self.req("POST", "/v1/warm")                    # ไม่มี body / Content-Length
        self.assertEqual((st, json.loads(raw)["action"]), (200, "loading"))
        st, _h, raw = self.req("POST", "/v1/warm", body=b"{}", headers={"Content-Type": "application/json"})
        self.assertEqual(st, 200)
        self.assertEqual(self.req("POST", "/v1/warm", body=b"x" * 5000)[0], 413)
        self.assertEqual(self.engine.warms, 2)
        self.assertEqual(self.engine.calls, [])

    def test_health_shows_device_only(self):
        self.engine.model, self.engine.device, self.engine.parked = object(), "cpu", False
        st, _h, raw = self.req("GET", "/health", token=None)
        body = json.loads(raw)
        self.assertEqual((body["device"], body["parked"]), ("cpu", False))
        self.assertNotIn("model_path", body)
        self.assertNotIn("device_reason", body)

    def test_inflight_cap_drains_and_answers_busy(self):
        # คำขอที่ถือ body ในหน่วยความจำพร้อมกันได้ไม่เกินช่องคิว: เกิน = อ่าน body ทิ้งแล้ว 503 (คอนเนกชันใช้ต่อได้)
        self.srv.shutdown()
        self.srv.server_close()
        self.srv = S.make_server(self.engine, 0, max_bytes=self.MAX_BYTES, max_seconds=600, decoder=self.decoder,
                                 inflight=1)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
        self.engine.block = threading.Event()
        first = threading.Thread(target=self.req, args=("POST", "/v1/transcribe"),
                                 kwargs={"body": wav_bytes(), "headers": {"Content-Type": "audio/wav"}})
        first.start()
        t0 = time.monotonic()
        while not self.engine.calls and time.monotonic() - t0 < 5:
            time.sleep(0.02)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            for _ in range(2):                                         # คอนเนกชันเดิมสองรอบ = body ถูกอ่านทิ้งครบ
                conn.request("POST", "/v1/transcribe", body=wav_bytes(), headers={
                    "Authorization": "Bearer " + C.TOKEN, "Content-Type": "audio/wav",
                    "Host": "127.0.0.1:%d" % self.port})
                resp = conn.getresponse()
                self.assertEqual((resp.status, json.loads(resp.read())["error"]), (503, "busy"))
                self.assertEqual(resp.getheader("Retry-After"), "10")
        finally:
            conn.close()
            self.engine.block.set()
            first.join(10)
        self.assertEqual(len(self.decoder.calls), 1)
        st, _h, _ = self.req("POST", "/v1/transcribe", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
        self.assertEqual(st, 200)                                      # ช่องว่างแล้วใช้ได้ตามปกติ

    def test_decoder_gate_busy(self):
        gate = self.srv.RequestHandlerClass.decode_gate
        self.srv.RequestHandlerClass.decode_wait = 0.2
        acquired = [gate.acquire(blocking=False) for _ in range(S.DECODE_CONCURRENCY)]
        try:
            st, h, raw = self.req("POST", "/v1/transcribe", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
            self.assertEqual((st, json.loads(raw)["error"]), (503, "busy"))
            self.assertEqual(self.decoder.calls, [])
        finally:
            for ok in acquired:
                if ok:
                    gate.release()
        st, _h, _ = self.req("POST", "/v1/transcribe", body=wav_bytes(), headers={"Content-Type": "audio/wav"})
        self.assertEqual(st, 200)


FLEXX = os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), "anaconda3", "envs", "flexxfast", "python.exe")

_DECODE_CHILD = r'''
import ctypes, ctypes.wintypes as W, io, json, sys, wave
sys.path.insert(0, %(stt)r)
import stt_server as S
import av, numpy  # noqa: F401  โหลดไลบรารีก่อนวัด ให้ peak สะท้อนแค่การถอดรหัส

class PMC(ctypes.Structure):
    _fields_ = [("cb", W.DWORD), ("PageFaultCount", W.DWORD)] + [(n, ctypes.c_size_t) for n in (
        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
        "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
k32 = ctypes.WinDLL("kernel32")
k32.GetCurrentProcess.restype = W.HANDLE
k32.K32GetProcessMemoryInfo.argtypes = [W.HANDLE, ctypes.POINTER(PMC), W.DWORD]
def peak_mb():
    c = PMC(); c.cb = ctypes.sizeof(PMC)
    k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.PeakPagefileUsage / 2 ** 20

def wav(rate, ch, seconds):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x01\x00" * ch * max(1, int(rate * seconds)))
    return b.getvalue()

cases = [("rate16", wav(16, 1, 200.0), 600), ("rate8k", wav(8000, 1, 1.0), 600), ("rate200k", wav(200000, 1, 0.1), 600),
         ("ch9", wav(16000, 9, 0.2), 600), ("long", wav(8000, 1, 5.0), 1)]
if len(sys.argv) > 1:
    cases.append(("flac16", open(sys.argv[1], "rb").read(), 600))
out = {}
for name, data, maxs in cases:
    before = peak_mb()
    try:
        a, d = S.decode_audio(data, maxs)
        res = "ok %%.1f" %% d
    except S.AudioError as exc:
        res = "%%d %%s" %% (exc.status, exc.code)
    out[name] = [res, round(peak_mb() - before)]
print(json.dumps(out))
'''


@unittest.skipUnless(os.path.isfile(FLEXX), "ไม่มี python ของ flexxfast (PyAV)")
class DecodeCapTests(unittest.TestCase):
    """decode_audio จริงด้วย PyAV (python ของ flexxfast ในโปรเซสลูก): อัตราสุ่มต่ำ/สูง/ช่องมากเกิน = 415 ก่อน resample
    FLAC 8 KB อัตรา 16 Hz (frame 65535) เดิมขยายเป็น +1.25 GB ก่อนถึงเพดานเวลา — ต้องเหลือไม่กี่ MB"""

    def test_rate_channel_caps_and_no_amplification(self):
        argv = [FLEXX, "-X", "utf8", "-c", _DECODE_CHILD % {"stt": STT_DIR}]
        ff = None
        try:
            ff = C.import_local("tools_media")._ffmpeg()
        except Exception:                                              # noqa: BLE001
            ff = None
        if ff:
            flac = os.path.join(C.new_dir("sttlowrate"), "lowrate16.flac")
            r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                                "anullsrc=r=16:cl=mono", "-t", "8192", "-c:a", "flac", "-frame_size", "65535", flac],
                               capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode == 0 and os.path.isfile(flac):
                argv.append(flac)
        r = subprocess.run(argv, capture_output=True, text=True, timeout=120, env=C.clean_env(),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["rate16"][0], "415 unsupported_rate")
        self.assertEqual(out["rate8k"][0], "ok 1.0")
        self.assertEqual(out["rate200k"][0], "415 unsupported_rate")
        self.assertEqual(out["ch9"][0], "415 too_many_channels")
        self.assertEqual(out["long"][0], "413 too_long")
        for name, (_res, grew) in out.items():
            self.assertLess(grew, 150, (name, out))                    # ไม่มีเคสไหนขยายหน่วยความจำเป็นร้อย MB
        if "flac16" in out:
            self.assertEqual(out["flac16"][0], "415 unsupported_rate")


if __name__ == "__main__":
    unittest.main()
