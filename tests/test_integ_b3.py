# -*- coding: utf-8 -*-
"""
batch 3 — เทสต์ของผู้ integrate (2026-10-06): สิ่งที่แก้ระหว่างตรวจรับบนเครื่องจริง

1. hub_doctor: heartbeat ของ scheduler ที่ "ล้ม" เพราะรอบแรกยิงก่อน router/hub เปิด (ตัวเปิดสั่ง scheduler ขั้น 1 ก่อนขั้น 2-3)
   ต้องไม่ทำให้แถว scheduler เป็นสีเหลืองพร้อมข้อความว่า router/hub ล้ม ในเมื่อการตรวจสดเห็นทั้ง 4 บริการปกติ
   — แต่ถ้าการตรวจสดเห็นบริการในชุดนั้นล้มจริงด้วย ต้องคง warn (สองแหล่งตรงกัน)
2. hub: X-Qwen-* จากต้นทาง (llama-server) ไม่ถูกส่งต่อ — header ของ hub เท่านั้นที่ถึงหน้าเว็บ
"""
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_b3_doctor as tbd    # noqa: E402 — ใช้ setUp/บริการปลอมของเทสต์ hub owner (import เป็นโมดูล: ไม่รันคลาสของมันซ้ำ)

HUB = r"C:\LLM\projects\hub.py"


def load_hub():
    sys.path.insert(0, os.path.dirname(HUB))
    spec = importlib.util.spec_from_file_location("hub_integ_b3_under_test", HUB)
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


class SchedulerHeartbeatSupersededTests(unittest.TestCase):
    setUp = tbd.DoctorTests.setUp
    tearDown = tbd.DoctorTests.tearDown

    def _heartbeat(self, status, message, age_s=60):
        self.state.write_text(json.dumps({"jobs": {"heartbeat": {"lastRunEpoch": time.time() - age_s,
                                                                 "lastRunStatus": status, "message": message}},
                                          "runner": {"pid": os.getpid()}}, ensure_ascii=False), encoding="utf-8")

    def test_stale_failure_from_before_the_stack_started_is_not_a_warning(self):
        # สถานการณ์จริงหลังรีบูต: heartbeat ยิงตอน router/hub ยังไม่เปิด แล้วทุกอย่างเปิดครบ
        self._heartbeat("error", "บริการปกติ 2/4 — ล้ม: llama-server, project hub")
        rep = tbd.hd.Doctor(self.cfg).report()
        st = {s["id"]: s for s in rep["services"]}
        for k in ("router", "mcp_local", "mcp_web", "hub"):
            self.assertEqual(st[k]["state"], "ok", k)
        self.assertEqual(st["scheduler"]["state"], "ok")
        self.assertIsNone(st["scheduler"]["heartbeat_message"])          # ข้อความเก่าที่ขัดกับผลสดไม่ถูกโชว์
        self.assertEqual(st["scheduler"]["heartbeat_status"], "error")   # ข้อมูลดิบยังอยู่
        self.assertTrue(st["scheduler"]["heartbeat_superseded"])
        self.assertNotIn("scheduler", [f["id"] for f in rep["fixes"]])
        self.assertNotIn("ล้ม: llama-server", tbd.hd.report_text(rep, "th"))

    def test_failure_confirmed_by_live_check_stays_a_warning(self):
        self._heartbeat("error", "บริการปกติ 3/4 — ล้ม: MCP local")
        self.servers[1].shutdown()               # MCP local ปลอมปิดจริง — การตรวจสดเห็นตรงกับ heartbeat
        self.servers[1].server_close()
        self.servers = [s for i, s in enumerate(self.servers) if i != 1]
        rep = tbd.hd.Doctor(self.cfg).report()
        st = {s["id"]: s for s in rep["services"]}
        self.assertEqual(st["mcp_local"]["state"], "down")
        self.assertEqual(st["scheduler"]["state"], "warn")
        self.assertEqual(st["scheduler"]["heartbeat_message"], "บริการปกติ 3/4 — ล้ม: MCP local")
        self.assertNotIn("heartbeat_superseded", st["scheduler"])

    def test_ok_and_stale_heartbeats_unchanged(self):
        self._heartbeat("ok", "บริการปกติ 4/4")
        st = {s["id"]: s for s in tbd.hd.Doctor(self.cfg).report()["services"]}
        self.assertEqual((st["scheduler"]["state"], st["scheduler"]["heartbeat_message"]), ("ok", "บริการปกติ 4/4"))
        self._heartbeat("error", "บริการปกติ 2/4 — ล้ม: llama-server, project hub", age_s=3 * 3600)
        st = {s["id"]: s for s in tbd.hd.Doctor(self.cfg).report(refresh=True)["services"]}
        self.assertEqual(st["scheduler"]["state"], "stale")    # scheduler ไม่ขยับเลย = ปัญหาของตัวมันเอง ยังเตือน


class BenignLogLineTests(unittest.TestCase):
    def test_client_cancel_from_llama_server_is_not_an_error(self):
        # ผู้ใช้กดหยุด / hub ปิดสายโมเดลสรุปตอนครบงบเวลา — ไม่ใช่ข้อผิดพลาดของระบบ (แต่ E อื่นของ llama-server ยังนับ)
        with tempfile.TemporaryDirectory(prefix="integb3-log-") as d:
            p = os.path.join(d, "llama.err.log")
            with open(p, "w", encoding="utf-8") as f:
                f.write("19.40.900.733 E srv    operator(): http client error: Connection handling canceled\n"
                        "19.41.000.001 E srv  load_model: failed to open model.gguf\n")
            lines, skipped = tbd.hd.error_lines(d)
        self.assertEqual([x["line"] for x in lines], ["19.41.000.001 E srv  load_model: failed to open model.gguf"])
        self.assertEqual(skipped, 1)


class FixSeverityTests(unittest.TestCase):
    """คำแนะนำมีระดับจาก hub เอง (ตรงกับ B3_FIX_LEVEL ของหน้า) และ overall ไม่นับคำแนะนำระดับ info"""
    setUp = tbd.DoctorTests.setUp
    tearDown = tbd.DoctorTests.tearDown

    def test_severity_matches_page_map_and_tips_do_not_warn(self):
        rep = tbd.hd.Doctor(self.cfg).report()
        lv = {f["id"]: f["severity"] for f in rep["fixes"]}
        self.assertEqual(lv["stt"], "error")
        self.assertEqual(lv["tests"], "warn")
        self.assertEqual(lv["brave"], "info")
        self.assertEqual(lv["docker"] if "docker" in lv else "info", "info")
        self.assertEqual(rep["overall"], "warn")             # STT ล่ม + เทสต์ไม่ผ่าน = ยังเตือน

    def test_healthy_machine_with_only_tips_is_ok(self):
        # ทุกบริการปกติ (STT ปลอมเปิด, heartbeat ใหม่และ ok, เทสต์ล่าสุดผ่าน) — เหลือแค่ Brave key/Docker ที่รอผู้ใช้ทำเอง
        stt = tbd.make_server({"/health": lambda h: (200, {"server": "qwen-stt", "state": "ready", "device": "cuda"})})
        self.servers.append(stt)
        self.cfg["stt_port"] = stt.server_address[1]
        self.state.write_text(json.dumps({"jobs": {"heartbeat": {"lastRunEpoch": time.time() - 60, "lastRunStatus": "ok",
                                                                 "message": "ok 4/4"}}, "runner": {"pid": os.getpid()}}),
                              encoding="utf-8")
        (self.tmp / "tests-last.json").write_text(json.dumps({"at": "x", "ran": 10, "ok": True, "failures": 0, "errors": 0,
                                                              "skipped": 0}), encoding="utf-8")
        # ค่าของเครื่อง (ดิสก์/หน่วยความจำ/GPU/Docker) คงที่ — ไม่ให้ผลขึ้นกับเครื่องที่รันเทสต์
        with mock.patch.object(tbd.hd, "disks", lambda: [{"drive": d, "present": True, "free_gb": 100.0, "total_gb": 500.0}
                                                         for d in ("C:", "D:", "E:")]), \
                mock.patch.object(tbd.hd, "memory_status", lambda: {"ram_total_gb": 64.0, "ram_free_gb": 30.0,
                                                                     "ram_load_pct": 50, "commit_limit_gb": 78.0,
                                                                     "commit_free_gb": 40.0}), \
                mock.patch.object(tbd.hd, "gpu_info", lambda timeout=2.2: ([{"name": "g", "temp_c": 50}], None)), \
                mock.patch.object(tbd.hd, "docker_status", lambda: {"usable": False, "reason_th": "ไม่ทำงาน",
                                                                    "reason_en": "not running"}):
            rep = tbd.hd.Doctor(self.cfg).report()
        self.assertEqual({s["id"]: s["state"] for s in rep["services"]},
                         {k: "ok" for k in ("router", "mcp_local", "mcp_web", "embed", "stt", "scheduler", "gateway", "hub")})
        self.assertEqual([(f["id"], f["severity"]) for f in rep["fixes"]], [("brave", "info"), ("docker", "info")])
        self.assertEqual(rep["overall"], "ok")
        self.assertIn("(overall: ok)", tbd.hd.report_text(rep, "en"))


class UpstreamQwenHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = load_hub()

    def test_upstream_x_qwen_headers_are_dropped(self):
        skip = self.hub._upstream_header_skip
        for h in ("X-Qwen-Compacted", "x-qwen-compacted", "X-Qwen-Plan", "X-QWEN-ANYTHING"):
            self.assertTrue(skip(h), h)
        for h in ("Content-Type", "X-Request-Id", "Server", "Date"):
            self.assertFalse(skip(h), h)
        self.assertTrue(skip("Access-Control-Allow-Origin"))   # กติกาเดิมยังอยู่
        self.assertTrue(skip("Transfer-Encoding"))


if __name__ == "__main__":
    unittest.main()
