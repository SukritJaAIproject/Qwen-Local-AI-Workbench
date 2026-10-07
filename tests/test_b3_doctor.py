# -*- coding: utf-8 -*-
"""
batch 3 สัญญา D3 (owner hub) — ตรวจระบบ: C:\\LLM\\projects\\hub_doctor.py (+ hub.doctor_report ตัวจริงแบบ opt-in)

ใช้บริการปลอมบนพอร์ตสุ่ม (router / MCP / embedding / gateway) + บริการที่ปิดอยู่ (STT) + ไฟล์ปลอมทั้งหมด:
  * สถานะต่อบริการ + latency, โมเดลที่โหลดอยู่, build ของ llama.cpp
  * ไฟล์คีย์บอกแค่มี/ไม่มี — ค่าโทเคนไม่ปรากฏที่ใดในรายงาน (JSON และข้อความ)
  * บรรทัด error ล่าสุดจาก *.err.log: ลบโทเคน/Bearer/api key, ข้ามการตัดสายของผู้ใช้, ไม่เกิน 20 บรรทัด
  * วิธีแก้ที่แนะนำ th/en ตรงกับปัญหา, scheduler ไม่ขยับ, ชุดทดสอบล่าสุดไม่ผ่าน
  * เร็ว: ตัวตรวจที่ค้างไม่ทำให้เกิน 3 วินาที (ขึ้น timeout), แคช 10 วินาที, refresh=1 ไม่ใช้แคช
LLM_B3_LIVE=1: เรียก hub.doctor_report() กับเครื่องจริง (อ่านอย่างเดียว) — ต้อง < 3 วินาทีและไม่มีค่าโทเคน
"""
import importlib.util
import json
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

PROJ = r"C:\LLM\projects"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hd = _load("hub_doctor_b3_under_test", os.path.join(PROJ, "hub_doctor.py"))
TOKEN = secrets.token_hex(32)                     # ค่าทดสอบ ไม่ใช่โทเคนจริง


def make_server(routes):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_GET(self):
            fn = routes.get(self.path.split("?")[0])
            if fn is None:
                code, body = 404, {"error": "nf"}
            else:
                code, body = fn(self)
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    return srv


def authed(ok_body):
    def fn(h):
        if h.headers.get("Authorization") != "Bearer " + TOKEN:
            return 401, {"error": "auth"}
        return 200, ok_body
    return fn


def free_port():
    s = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    p = s.server_address[1]
    s.server_close()
    return p


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b3doc-"))
        self.servers = [
            make_server({"/health": lambda h: (200, {"status": "ok"}),
                         "/models": authed({"data": [{"id": "Qwen3-4B", "status": {"value": "loaded"}},
                                                     {"id": "Qwen3.8-27B", "status": {"value": "unloaded"}}]}),
                         "/props": authed({"build_info": "b10984-test", "max_instances": 2})}),
            make_server({"/mcp": authed({"ok": True, "modules_failed": {}})}),
            make_server({"/mcp": authed({"ok": True, "provider": "builtin"})}),
            make_server({"/health": lambda h: (200, {"status": "ok"})}),
            make_server({"/health": lambda h: (200, {"status": "ok", "upstream_ok": True})}),
        ]
        router, mcpl, mcpw, embed, gw = [s.server_address[1] for s in self.servers]
        (self.tmp / "logs").mkdir()
        (self.tmp / "logs" / "hub.err.log").write_text(
            "Traceback (most recent call last):\n  File x\nConnectionResetError: [WinError 10054] forcibly closed\n"
            "Traceback (most recent call last):\n  File y\nValueError: bad token %s in request\n" % TOKEN
            + "".join("RuntimeError: งานที่ %d ล้มเหลว\n" % i for i in range(30))
            + "ERROR auth header Authorization: Bearer abcdefghijklmnop0123 rejected\n"
              "ERROR config api_key=sk-abcdefghijklmnopqrstuvwxyz used\n", encoding="utf-8")
        (self.tmp / "logs" / "llama.err.log").write_text(
            "1.02.003.004 I srv  load_model: ok\n1.02.003.005 E srv  load_model: failed to open model.gguf\n",
            encoding="utf-8")
        os.utime(self.tmp / "logs" / "llama.err.log", (time.time() - 60, time.time() - 60))   # hub.err.log ใหม่กว่า
        old = self.tmp / "logs" / "old.err.log"
        old.write_text("KeyError: old problem\n", encoding="utf-8")
        os.utime(old, (time.time() - 86400 * 2, time.time() - 86400 * 2))         # 2 วัน = ยังนับ
        # [fix-hub b3] เก่าเกิน ERR_MAX_AGE_S (ผู้ตรวจรับ: บรรทัด encodings จากเทสต์ 2026-09-29 ค้างทั้งสัปดาห์) = ไม่นับ
        stale = self.tmp / "logs" / "gpu-profile-8099.err.log"
        stale.write_text("ModuleNotFoundError: No module named 'encodings'\n", encoding="utf-8")
        os.utime(stale, (time.time() - 86400 * 8, time.time() - 86400 * 8))
        # log ของพอร์ตทดสอบ (router สำรอง 8197) — ใหม่แต่ไม่ใช่บริการจริง
        (self.tmp / "logs" / "gpu-state-8197.err.log").write_text("ValueError: test router only\n", encoding="utf-8")
        os.utime(self.tmp / "logs" / "gpu-state-8197.err.log", (time.time() - 120, time.time() - 120))
        self.state = self.tmp / "scheduler_state.json"
        self.state.write_text(json.dumps({"jobs": {"heartbeat": {"lastRunEpoch": time.time() - 3 * 3600,
                                                                 "lastRunStatus": "ok", "message": "ok 4/4"}},
                                          "runner": {"pid": os.getpid()}}), encoding="utf-8")
        self.token_file = self.tmp / "local-services.token"
        self.token_file.write_text(TOKEN, encoding="ascii")
        (self.tmp / "gateway_key.txt").write_text("gwkey-" + "z" * 20, encoding="ascii")
        (self.tmp / "stt_server.py").write_text("# ติดตั้งแล้วแต่ไม่ได้เปิด (สถานะ down ไม่ใช่ missing)\n", encoding="utf-8")
        (self.tmp / "models").mkdir()
        (self.tmp / "models" / "Qwen3-4B.gguf").write_bytes(b"\0" * 2048)
        (self.tmp / "tests-last.json").write_text(json.dumps({"at": "2026-10-06T10:00:00+07:00", "ran": 10, "ok": False,
                                                              "failures": 1, "errors": 1, "skipped": 0}), encoding="utf-8")
        self.cfg = {
            "upstream_port": router, "hub_port": 8100, "mcp_web_port": mcpw, "mcp_local_port": mcpl,
            "embed_port": embed, "stt_port": free_port(), "gateway_port": gw,
            "embed_model": str(self.tmp / "models" / "Qwen3-4B.gguf"), "stt_script": str(self.tmp / "stt_server.py"),
            "scheduler_state": str(self.state), "router_headers": lambda: {"Authorization": "Bearer " + TOKEN},
            "token": lambda: TOKEN, "projects": lambda: [{"slug": "a", "name": "A", "port": router}],
            "proxies": lambda: [router], "keep_awake": lambda: 0, "pid_alive": lambda pid: pid == os.getpid(),
            "log_dir": str(self.tmp / "logs"), "scrub": lambda s: s.replace(TOKEN, "***"),
            "model_dirs": [str(self.tmp / "models")], "token_file": str(self.token_file),
            "brave_key_file": str(self.tmp / "brave-search.key"), "gateway_key_file": str(self.tmp / "gateway_key.txt"),
            "tests_file": str(self.tmp / "tests-last.json"), "llama_dir_build": "b10984", "hub_version": "test",
            "live_ports": [router, 8099, 8100], "secret_files": [str(self.tmp / "gateway_key.txt"),
                                                                 str(self.tmp / "brave-search.key")],
        }

    def tearDown(self):
        for s in self.servers:
            s.shutdown()
            s.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)        # โฟลเดอร์ชั่วคราวของเทสต์นี้เอง

    def test_report_states_keys_and_fixes(self):
        t0 = time.time()
        rep = hd.Doctor(self.cfg).report()
        self.assertLess(time.time() - t0, 3.0)
        st = {s["id"]: s for s in rep["services"]}
        self.assertEqual(st["router"]["state"], "ok")
        self.assertEqual([m["id"] for m in st["router"]["loaded"]], ["Qwen3-4B"])
        self.assertEqual(rep["versions"]["llama_cpp"], "b10984-test")
        self.assertEqual(st["mcp_local"]["state"], "ok")
        self.assertEqual((st["mcp_web"]["state"], st["mcp_web"]["provider"]), ("ok", "builtin"))
        self.assertEqual(st["embed"]["state"], "ok")
        self.assertEqual(st["stt"]["state"], "down")
        self.assertEqual(st["gateway"]["state"], "ok")
        self.assertEqual(st["scheduler"]["state"], "stale")
        self.assertGreater(st["scheduler"]["heartbeat_age_s"], 3 * 3600 - 60)
        self.assertEqual(st["hub"]["state"], "ok")
        for s in rep["services"]:
            self.assertIn("latency_ms", s)
        self.assertEqual(rep["keys"], {"local_token": True, "brave_key": False, "gateway_key": True})
        self.assertEqual(rep["models"]["files"][0]["name"], "Qwen3-4B.gguf")
        ids = [f["id"] for f in rep["fixes"]]
        for want in ("stt", "scheduler", "brave", "tests"):
            self.assertIn(want, ids)
        stt_fix = next(f for f in rep["fixes"] if f["id"] == "stt")
        self.assertIn("-RestartStt", stt_fix["th"])
        self.assertIn("-RestartStt", stt_fix["en"])
        self.assertEqual(rep["overall"], "warn")
        self.assertIn(rep["docker"]["usable"], (True, False))
        self.assertIsInstance(rep["memory"], dict)
        self.assertTrue(any(d["drive"] == "C:" and d["present"] for d in rep["disks"]))
        self.assertEqual(rep["tests"]["failures"], 1)
        self.assertEqual(rep["tests"]["passed"], 8)
        self.assertIs(rep["brave_key"], False)
        self.assertIn("checked_at", rep)
        loc = hd.localize(rep, "en")
        self.assertEqual({s["id"]: s["name"] for s in loc["services"]}["stt"], "Speech-to-text (STT)")
        self.assertIn("reason", loc["docker"])
        self.assertNotIn("name", rep["services"][0])          # รายงานในแคชไม่ถูกแก้
        # ไม่มีค่าความลับที่ใดเลย
        blob = json.dumps(rep, ensure_ascii=False) + hd.report_text(rep, "th") + hd.report_text(rep, "en")
        for secret in (TOKEN, "abcdefghijklmnop0123", "sk-abcdefghijklmnopqrstuvwxyz", "gwkey-"):
            self.assertNotIn(secret, blob)

    def test_error_lines_redacted_limited_and_benign_skipped(self):
        lines, skipped = hd.error_lines(self.tmp / "logs", scrub=lambda s: s.replace(TOKEN, "***"))
        self.assertEqual(len(lines), 20)
        self.assertGreaterEqual(skipped, 1)
        text = "\n".join(e["line"] for e in lines)
        self.assertNotIn("ConnectionResetError", text)
        self.assertNotIn(TOKEN, text)
        self.assertIn("Bearer ***", text)
        self.assertIn("api_key=***", text)
        self.assertNotIn("Traceback", text)
        self.assertEqual(lines[0]["file"], "hub.err.log")    # ไฟล์ล่าสุดก่อน บรรทัดล่าสุดก่อน
        self.assertIn("api_key", lines[0]["line"])
        # llama-server: บรรทัดระดับ E เท่านั้น
        stats = {}
        lines2, _ = hd.error_lines(self.tmp / "logs", limit=200, live_ports=[8099, 8100], stats=stats)
        llama = [e["line"] for e in lines2 if e["file"] == "llama.err.log"]
        self.assertEqual(llama, ["1.02.003.005 E srv  load_model: failed to open model.gguf"])
        self.assertEqual(lines2[-1]["file"], "old.err.log")
        files = {e["file"] for e in lines2}
        self.assertNotIn("gpu-profile-8099.err.log", files)        # 8 วันก่อน
        self.assertNotIn("gpu-state-8197.err.log", files)          # พอร์ตทดสอบ
        self.assertEqual(stats, {"old_files": 1, "test_logs": 1})
        # ไม่ส่ง live_ports = ไม่กรองตามพอร์ต (สคริปต์เก่าที่เรียกตรง)
        lines3, _ = hd.error_lines(self.tmp / "logs", limit=200)
        self.assertIn("gpu-state-8197.err.log", {e["file"] for e in lines3})

    def test_hanging_probe_hits_deadline_and_cache(self):
        def slow_projects():
            time.sleep(5)
            return []
        cfg = dict(self.cfg, projects=slow_projects)
        doc = hd.Doctor(cfg)
        t0 = time.time()
        rep = doc.report()
        self.assertLess(time.time() - t0, 3.0)
        st = {s["id"]: s for s in rep["services"]}
        self.assertEqual(st["hub"]["state"], "timeout")
        self.assertIn("hub", rep["_meta"]["late"])
        t1 = time.time()
        again = doc.report()
        self.assertLess(time.time() - t1, 0.1)
        self.assertTrue(again["cached"])
        self.assertFalse(rep["cached"])
        fresh = doc.report(refresh=True)
        self.assertFalse(fresh["cached"])

    def test_auth_and_down_router(self):
        cfg = dict(self.cfg, router_headers=lambda: {"Authorization": "Bearer wrong"}, token=lambda: "wrong")
        rep = hd.Doctor(cfg).report()
        st = {s["id"]: s for s in rep["services"]}
        self.assertEqual(st["router"]["state"], "auth")
        self.assertEqual(st["mcp_local"]["state"], "auth")
        ids = [f["id"] for f in rep["fixes"]]
        self.assertIn("router_auth", ids)
        self.assertIn("mcp_auth", ids)
        cfg = dict(self.cfg, upstream_port=free_port())
        rep = hd.Doctor(cfg).report()
        self.assertEqual(rep["services"][0]["state"], "down")
        self.assertEqual(rep["overall"], "error")
        self.assertIn("start-qwen38.ps1 -Unattended", rep["fixes"][0]["en"])

    def test_text_report_both_languages(self):
        rep = hd.Doctor(self.cfg).report()
        th = hd.report_text(rep, "th")
        en = hd.report_text(rep, "en")
        self.assertIn("รายงานตรวจระบบ", th)
        self.assertIn("[วิธีแก้ที่แนะนำ]", th)
        self.assertIn("system check", en)
        self.assertIn("[Suggested fixes]", en)
        self.assertIn("Brave key: no", en)
        self.assertIn("Brave key: ไม่มี", th)

    def test_localize_drops_thai_only_free_text_in_english(self):
        """ข้อความ heartbeat ของ scheduler เป็นภาษาไทยอย่างเดียว — หน้าอังกฤษต้องไม่มีอักษรไทยปน ภาษาไทยยังเห็น"""
        self.state.write_text(json.dumps({"jobs": {"heartbeat": {"lastRunEpoch": time.time() - 60,
                                                                 "lastRunStatus": "ok", "message": "บริการปกติ 4/4"}},
                                          "runner": {"pid": os.getpid()}}), encoding="utf-8")
        rep = hd.Doctor(self.cfg).report(refresh=True)
        en = {s["id"]: s for s in hd.localize(rep, "en")["services"]}
        th = {s["id"]: s for s in hd.localize(rep, "th")["services"]}
        self.assertIsNone(en["scheduler"]["heartbeat_message"])
        self.assertEqual(th["scheduler"]["heartbeat_message"], "บริการปกติ 4/4")
        self.assertEqual(en["scheduler"]["name"], "Scheduler")
        # รายงานในแคชไม่ถูกแก้ (localize คืนสำเนา)
        self.assertEqual({s["id"]: s for s in rep["services"]}["scheduler"]["heartbeat_message"], "บริการปกติ 4/4")

    def test_down_service_has_no_latency(self):
        rep = hd.Doctor(self.cfg).report(refresh=True)
        stt = {s["id"]: s for s in rep["services"]}["stt"]       # STT ในชุดนี้ปิดอยู่ (ต่อไม่ติด)
        self.assertEqual(stt["state"], "down")
        self.assertIsNone(stt["latency_ms"])

    def test_redact_patterns(self):
        for raw, gone in (("Authorization: Bearer abc.def-ghi_123456", "abc.def-ghi_123456"),
                          ("token=" + "f" * 64, "f" * 64), ("password: hunter2hunter2", "hunter2hunter2"),
                          ("key BSA0123456789abcdefghijk", "BSA0123456789abcdefghijk")):
            self.assertNotIn(gone, hd.redact(raw))
        self.assertLessEqual(len(hd.redact("x" * 1000)), hd.LOG_LINE_MAX + 1)

    def test_redact_gateway_style_keys_and_controls(self):
        """[fix-hub b3] ผู้ตรวจ: ค่าแบบ secrets.token_urlsafe(24) (รูปแบบคีย์ของ gateway) หลุดทั้ง 3 รูปแบบนี้"""
        import re
        for _ in range(20):
            v = secrets.token_urlsafe(24)
            if len(re.findall(r"[-_]", v)) > 5:              # ~0.03% ของค่าสุ่ม — นอกขอบเขตกฎไม่มีป้าย (ค่าจริงลบตามค่าอีกชั้น)
                continue
            for raw in ("ERROR gateway rejected client key %s" % v, "ValueError: bad header X-Api-Key %s" % v,
                        "ERROR key=%s" % v, "ERROR got %s from client" % v):
                self.assertNotIn(v, hd.redact(raw), raw)
        # ของที่ไม่ใช่ความลับยังอ่านได้ (ชื่อโมเดล, path, ข้อความทั่วไป)
        for keep in ("Qwen3-4B-Instruct-2507-Q4_K_M", r"C:\LLM\models\Qwen3.8-27B-UD-Q4_K_XL.gguf",
                     "max_tokens=4096", "KeyError: 'model'", "123e4567-e89b-12d3-a456-426614174000"):
            self.assertIn(keep, hd.redact("ERROR loading " + keep), keep)
        # อักขระสลับทิศ/ล่องหนถูกลบ
        self.assertEqual(hd.redact("ERROR a\u202eb\u2066c\u200bd"), "ERROR abcd")

    def test_value_scrubber_hides_gateway_and_brave_values_everywhere(self):
        gw = secrets.token_urlsafe(24)
        brave = "Zq" + secrets.token_hex(12)                       # รูปแบบที่ไม่มีป้าย/คำนำหน้าใดๆ
        (self.tmp / "gateway_key.txt").write_text(gw, encoding="ascii")
        (self.tmp / "brave-search.key").write_text(brave + "\n", encoding="ascii")
        (self.tmp / "logs" / "hub.err.log").write_text("ERROR upstream said %s and %s\n" % (gw, brave), encoding="utf-8")
        self.state.write_text(json.dumps({"jobs": {"heartbeat": {"lastRunEpoch": time.time() - 60, "lastRunStatus": "error",
                                                                 "message": "ล้ม: gateway ส่ง %s" % brave}},
                                          "runner": {"pid": os.getpid()}}), encoding="utf-8")
        (self.tmp / "tests-last.json").write_text(json.dumps({"at": "x", "ran": 3, "failures": 1, "errors": 0, "skipped": 0,
                                                              "failed": ["test_x (%s)" % gw]}), encoding="utf-8")
        rep = hd.Doctor(self.cfg).report(refresh=True)
        blob = json.dumps(rep, ensure_ascii=False) + hd.report_text(rep, "th") + hd.report_text(rep, "en")
        self.assertNotIn(gw, blob)
        self.assertNotIn(brave, blob)
        self.assertTrue(rep["keys"]["brave_key"])

    def test_windows_label_and_stt_device(self):
        self.assertEqual(hd.windows_label(10, 0, 26200), "Windows 11 (10.0.26200)")
        self.assertEqual(hd.windows_label(10, 0, 19045), "Windows 10 (10.0.19045)")
        # STT: /health ว่าง (ยังไม่มีงาน) → ถาม /v1/status ด้วยโทเคน แบบเดียวกับแผงบริการของ hub
        stt = make_server({"/health": lambda h: (200, {"server": "qwen-stt", "state": "idle"}),
                           "/v1/status": authed({"device": "cuda", "state": "idle"})})
        try:
            rep = hd.Doctor(dict(self.cfg, stt_port=stt.server_address[1])).report(refresh=True)
        finally:
            stt.shutdown()
            stt.server_close()
        row = {s["id"]: s for s in rep["services"]}["stt"]
        self.assertEqual((row["state"], row["device"]), ("ok", "gpu"))
        self.assertTrue(rep["versions"]["os"].startswith("Windows"))


@unittest.skipUnless(os.environ.get("LLM_B3_LIVE") == "1", "set LLM_B3_LIVE=1 for the live read-only doctor check")
class LiveDoctorTests(unittest.TestCase):
    def test_live_report_fast_and_secret_free(self):
        sys.path.insert(0, PROJ)
        spec = importlib.util.spec_from_file_location("hub_b3_doctor_live", os.path.join(PROJ, "hub.py"))
        hub = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "argv", ["hub.py"]):
            spec.loader.exec_module(hub)
        t0 = time.time()
        rep = hub.doctor_report(refresh=True)
        took = time.time() - t0
        self.assertLess(took, 3.0)
        tok = hub.local_token()
        blob = json.dumps(rep, ensure_ascii=False) + hd.report_text(rep, "th") + hd.report_text(rep, "en")
        if tok:
            self.assertNotIn(tok, blob)
        ids = {s["id"] for s in rep["services"]}
        self.assertEqual(ids, {"router", "mcp_local", "mcp_web", "embed", "stt", "scheduler", "gateway", "hub"})
        print("\n[doctor-live] %.2fs overall=%s states=%s fixes=%s" % (
            took, rep["overall"], {s["id"]: s["state"] for s in rep["services"]}, [f["id"] for f in rep["fixes"]]))


if __name__ == "__main__":
    unittest.main()
