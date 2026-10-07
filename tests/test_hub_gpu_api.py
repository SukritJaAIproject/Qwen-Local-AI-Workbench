# -*- coding: utf-8 -*-
"""
เทสต์ API เลือก GPU ของ hub (GET /api/gpu, PUT /api/gpu/choice, POST /api/gpu/apply)

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v

ปลอดภัยต่อระบบจริง: GPU_CHOICE / GPU_PROFILE ชี้ไปโฟลเดอร์ชั่วคราวทุกเทสต์ (ไม่แตะ C:\\LLM\\gpu-choice.json)
ไม่เรียก nvidia-smi / llama-server (แทน gpu_live / gpu_fingerprint ด้วยค่าปลอม) และงาน "ใช้" แทนตัวเปิดจริง
ด้วย python -c สั้นๆ — ไม่มีทางไปรีสตาร์ต router ตัวจริง  เปิดพอร์ตเฉพาะพอร์ตสุ่มของ OS สำหรับเทสต์ HTTP
"""
import ast
import http.client
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gpu_profile as gp  # noqa: E402

HUB = r"C:\LLM\projects\hub.py"
K4090 = "NVIDIA GeForce RTX 4090"
K1000 = "NVIDIA RTX 1000 Ada Generation Laptop GPU"
ID27 = "Qwen3.8-27B-UD-Q4_K_M"
ID4B = "Qwen3-4B-Instruct-2507-Q4_K_M"


def load_hub():
    sys.path.insert(0, os.path.dirname(HUB))
    spec = importlib.util.spec_from_file_location("hub_api_under_test", HUB)
    mod = importlib.util.module_from_spec(spec)
    tmp = tempfile.gettempdir()
    with mock.patch.object(sys, "argv", ["hub.py"]), \
            mock.patch.dict(os.environ, {"QWEN_GPU_PROFILE": os.path.join(tmp, "none-profile.json"),
                                         "QWEN_GPU_CHOICE": os.path.join(tmp, "none-choice.json")}):
        spec.loader.exec_module(mod)
    return mod


try:
    hub = load_hub() if os.path.isfile(HUB) else None
    HUB_ERR = None if hub else "ไม่มี hub.py"
except Exception as e:      # noqa: BLE001
    hub, HUB_ERR = None, "import hub.py ไม่ได้: %s: %s" % (type(e).__name__, e)


def live(*keys):
    devs = [{"key": k, "id": "CUDA%d" % i, "name": k, "short": k.split("RTX ")[-1], "total_mib": 24564,
             "free_mib": 24000, "budget_mib": 23540, "external": True} for i, k in enumerate(keys)]
    return {"state": "ok", "detecting": False, "devices": devs, "fingerprint": "fp", "detected_at": None, "error": None}


@unittest.skipIf(hub is None, HUB_ERR or "")
class HubGpuApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hubgpuapi-")
        self.choice = Path(self.tmp) / "gpu-choice.json"
        self.patches = [
            mock.patch.object(hub, "GPU_CHOICE", self.choice),
            mock.patch.object(hub, "GPU_PROFILE", Path(self.tmp) / "gpu-profile.json"),
            mock.patch.object(hub, "gpu_live", return_value=live(K4090, K1000)),
            mock.patch.object(hub, "gpu_fingerprint", return_value=(True, "fp")),
            mock.patch.object(hub, "upstream_models", return_value=[ID27, ID4B]),
            mock.patch.object(hub, "gpu_catalog", return_value={}),
        ]
        for p in self.patches:
            p.start()
        hub._gpu_file.update(key=None, doc=None)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- ไฟล์ตัวเลือก
    def test_missing_choice_file_is_all_auto(self):
        doc, info = hub.gpu_choice_read()
        self.assertEqual(doc["models"], {})
        self.assertFalse(info["exists"])
        self.assertEqual(info["name"], "gpu-choice.json")

    def test_broken_choice_file_is_ignored(self):
        self.choice.write_text("{not json", encoding="utf-8")
        doc, info = hub.gpu_choice_read()
        self.assertEqual(doc["models"], {})
        self.assertTrue(info["exists"])
        self.assertFalse(info["valid"])

    def test_save_writes_no_bom_and_drops_auto(self):
        out = hub.gpu_choice_save({ID27: [K4090], ID4B: "auto"})
        self.assertEqual(out["models"], {ID27: [K4090]})
        raw = self.choice.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        doc = json.loads(raw.decode("utf-8"))
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["models"], {ID27: [K4090]})
        self.assertIsNone(gp.read_choice(str(self.choice), []).get("error"))

    def test_save_rejects_unknown_model_gpu_and_shapes(self):
        for bad in ({"nope": "cpu"}, {ID27: ["NVIDIA GeForce RTX 9999"]}, {ID27: []}, {ID27: [K4090, K4090]},
                    {ID27: "gpu"}, {ID27: ["x" * 121]}, {ID27: [K4090] * 9}):
            with self.subTest(bad=bad):
                with self.assertRaises(hub.GpuChoiceError) as cm:
                    hub.gpu_choice_save(bad)
                self.assertTrue(cm.exception.th and cm.exception.en)
        self.assertFalse(self.choice.exists())

    def test_keys_already_in_file_stay_valid_when_unplugged(self):
        # ถอด eGPU ไว้ชั่วคราว: บันทึกค่าเดิมของการ์ดที่ถอดได้ ไม่ต้องล้างทิ้ง
        self.choice.write_text(json.dumps({"version": 1, "models": {ID27: ["NVIDIA GeForce RTX 5090"]}}), encoding="utf-8")
        out = hub.gpu_choice_save({ID27: ["NVIDIA GeForce RTX 5090"], ID4B: "cpu"})
        self.assertEqual(out["models"][ID4B], "cpu")

    def test_local_validator_matches_module_rules(self):
        ids, keys = [ID27, ID4B], [K4090, K1000]
        ok = hub._validate_choice_local({"models": {ID27: [K1000, K4090], ID4B: "CPU"}}, ids, keys)
        self.assertEqual(ok["models"], {ID27: [K1000, K4090], ID4B: "cpu"})
        for bad in ({"nope": "cpu"}, {ID27: [K4090, K4090]}, {ID27: []}, {ID27: ["zzz"]}):
            with self.subTest(bad=bad), self.assertRaises(hub.GpuChoiceError):
                hub._validate_choice_local({"models": bad}, ids, keys)

    # ---- เนื้อ GET /api/gpu
    def test_payload_without_profile(self):
        d = hub.gpu_api_payload(False, False)
        self.assertIsNone(d["profile"])
        self.assertEqual([r["id"] for r in d["models"]], [ID27, ID4B])
        self.assertTrue(d["models"][0]["primary"])
        self.assertEqual(d["models"][0]["choice"], "auto")
        self.assertEqual(d["job"]["state"], hub._gpu_job["state"])
        self.assertIn("devices", d["live"])

    def test_payload_scrubs_paths(self):
        self.assertEqual(hub._scrub(r"python C:\LLM\gpu_bench.py"), "python gpu_bench.py")
        self.assertEqual(hub._scrub(r"merged: C:\LLM\models-preset.user.ini"), "merged: models-preset.user.ini")
        self.assertEqual(hub._scrub(r"at C:\Program Files\x\y.exe done"), "at Program y.exe done")
        self.assertEqual(hub._scrub("12:30 tok/s a/b"), "12:30 tok/s a/b")
        doc = {"choice": {"path": r"C:\Users\x\AppData\gpu-choice.json"}, "summary_th": r"วัดจริง: python C:\LLM\gpu_bench.py"}
        s = hub._scrub_obj(doc)
        self.assertEqual(s["choice"]["path"], "gpu-choice.json")
        flat = json.dumps(s, ensure_ascii=False)
        self.assertNotIn("C:", flat)
        self.assertNotIn("Users", flat)

    # ---- งาน "ใช้" (ไม่มีตัวเปิดจริง)
    def run_job(self, code):
        argv = [sys.executable, "-c", "print('step 1'); print('C:\\\\LLM\\\\logs\\\\x.log'); raise SystemExit(%d)" % code]
        log = Path(self.tmp) / "gpu-apply.log"
        with mock.patch.object(hub, "_gpu_apply_cmd", return_value=(argv, log, True)):
            hub._gpu_job.update(state="idle")
            self.assertTrue(hub.gpu_apply_start())
            self.assertFalse(hub.gpu_apply_start())          # งานเดิมยังทำอยู่ = 409
            for _ in range(100):
                if hub._gpu_job["state"] != "running":
                    break
                time.sleep(0.1)
        return hub.gpu_job_snapshot()

    def test_job_rc_mapping(self):
        for code, state in ((0, "done"), (3, "busy"), (1, "failed")):
            with self.subTest(code=code):
                j = self.run_job(code)
                self.assertEqual(j["state"], state)
                self.assertEqual(j["rc"], code)
                self.assertEqual(j["log"], "gpu-apply.log")
                self.assertIn("step 1", j["tail"])
                self.assertIn("x.log", j["tail"])           # path เหลือแค่ชื่อไฟล์
                self.assertTrue(j["message_th"] and j["message_en"])

    def test_real_mode_argv_is_fixed_and_env_is_clean(self):
        # -Port = router ที่ hub ตัวนี้ส่งต่อให้ (ไม่ส่ง = ตัวเปิดทำงานกับ 8099 เสมอ แม้ hub ต่อ router พอร์ตอื่น)
        with mock.patch.dict(os.environ, {"QWEN_GPU_DRYRUN": ""}), mock.patch.object(hub, "UPSTREAM_PORT", 8111):
            argv, log, dry = hub._gpu_apply_cmd()
        self.assertFalse(dry)
        self.assertEqual(argv[1:], ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(hub.GPU_LAUNCHER),
                                    "-NoBrowser", "-NonInteractive", "-Port", "8111"])
        self.assertEqual(log.name, "gpu-apply.log")
        env = {"PATH": "x", "SystemRoot": r"C:\Windows", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "LOCALAPPDATA": "y",
               "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_TOKEN": "s", "ANTHROPIC_BASE_URL": "u", "GITHUB_TOKEN": "t",
               "OPENAI_API_KEY": "k", "AWS_SECRET_ACCESS_KEY": "k", "QWEN_GPU_SIMULATE": "sim.json", "OTEL_X": "o"}
        with mock.patch.dict(os.environ, env, clear=True):
            child = hub._gpu_child_env()
        # os.environ ของ Windows เก็บชื่อเป็นตัวพิมพ์ใหญ่ — เทียบแบบไม่สนตัวพิมพ์
        self.assertEqual(sorted(k.upper() for k in child),
                         sorted(["PATH", "SYSTEMROOT", "CUDA_DEVICE_ORDER", "LOCALAPPDATA", "PYTHONIOENCODING"]))

    def test_profile_path_follows_upstream_port(self):
        # กฎเดียวกับ gpu_profile.published_dir และ $PubDir ของตัวเปิด
        for port in (8099, 8111, 8199):
            with self.subTest(port=port):
                self.assertEqual(os.path.normcase(str(hub._gpu_published_dir(port))),
                                 os.path.normcase(gp.published_dir(port)))

    # ---- ตัวอ่าน gpu-choice.json ต้องตัดสินแบบเดียวกับตัวเปิด (gp.read_choice)
    def test_choice_reader_matches_launcher_rules(self):
        cases = {
            "version2": ({"version": 2, "models": {ID4B: "cpu"}}, False),
            "dup": ({"version": 1, "models": {ID27: [K4090, K4090]}}, True),
            "blank": ({"version": 1, "models": {ID27: ["   "]}}, True),
            "long": ({"version": 1, "models": {ID27: ["x" * 130]}}, True),
        }
        for name, (doc, valid) in cases.items():
            with self.subTest(case=name):
                self.choice.write_text(json.dumps(doc), encoding="utf-8")
                got, info = hub.gpu_choice_read()
                ref = gp.read_choice(str(self.choice), [])
                self.assertEqual(got["models"], ref["models"])
                self.assertEqual(got["models"], {})
                self.assertEqual(info["valid"], valid)
        # key ขยะในไฟล์ต้องไม่กลายเป็น "GPU ที่รู้จัก" ตอน PUT
        self.choice.write_text(json.dumps({"version": 1, "models": {ID27: ["   "]}}), encoding="utf-8")
        with self.assertRaises(hub.GpuChoiceError):
            hub.gpu_choice_save({ID27: ["   "]})

    def test_choice_reader_survives_deep_nesting(self):
        self.choice.write_text("[" * 200000 + "]" * 200000, encoding="utf-8")
        got, info = hub.gpu_choice_read()
        self.assertEqual(got["models"], {})
        self.assertFalse(info["valid"])
        with mock.patch.object(hub, "_gpu_fn", return_value=None):      # ทางสำรองเมื่อไม่มี read_choice
            got, info = hub.gpu_choice_read()
        self.assertFalse(info["valid"])

    def test_payload_reports_user_ini_keys(self):
        ini = Path(self.tmp) / "models-preset.user.ini"
        ini.write_text("[%s]\nctx-size = 16384\n[%s]\ndevice = CUDA0\nmmproj =\n" % (ID4B, ID27), encoding="utf-8")
        with mock.patch.object(hub, "GPU_USER_INI", ini):
            hub._gpu_uini.update(key=None, sections={})
            rows = {r["id"]: r for r in hub.gpu_api_payload(False, False)["models"]}
        self.assertEqual(rows[ID4B]["user_ini"], {"keys": ["ctx-size"], "ctx": 16384, "vision": None})
        self.assertEqual(rows[ID27]["user_ini"], {"keys": ["device", "mmproj"], "ctx": None, "vision": False})
        hub._gpu_uini.update(key=None, sections={})

    # ---- บันทึกของตัวเปิด → ช่วงงาน / ผลลัพธ์
    def test_log_result_and_phase(self):
        ok = "  ผลลัพธ์: done — เปิด llama-server ด้วยแผน GPU ใหม่แล้ว (exit 0)"
        same = "  ผลลัพธ์: done — GPU และค่าตั้งของทุกโมเดลเหมือนเดิม — ไม่ต้องรีสตาร์ต (exit 0)"
        busy = "  ผลลัพธ์: busy — ยังมีแชตกำลังตอบอยู่ (exit 3)"
        self.assertEqual(hub._gpu_log_result(["x", ok]), ("done", 0, True))
        self.assertEqual(hub._gpu_log_result(["x", same]), ("done", 0, False))
        self.assertEqual(hub._gpu_log_result([busy]), ("busy", 3, False))
        self.assertEqual(hub._gpu_log_result(["no result"]), (None, None, None))
        log = Path(self.tmp) / "gpu-apply.log"
        wait = "        กำลังรอให้แชตที่ตอบอยู่เสร็จ (ต้องว่างต่อเนื่อง ~10 วินาที สูงสุด 180 วินาที)..."
        log.write_text("#qwen-hub x\n  [2/4] ...\n%s\n" % wait, encoding="utf-8")
        with mock.patch.dict(hub._gpu_job, {"state": "running", "log": str(log), "t0": time.monotonic()}):
            j = hub.gpu_job_snapshot()
        self.assertEqual(j["phase"], "waiting")
        self.assertIn("รอ", j["message_th"])
        log.write_text("#qwen-hub x\n%s\n" % same, encoding="utf-8")
        with mock.patch.dict(hub._gpu_job, {"state": "done", "log": str(log), "rc": 0}):
            j = hub.gpu_job_snapshot()
        self.assertIs(j["restarted"], False)
        self.assertEqual(j["message_en"], hub.GPU_JOB_MSG_SAME[1])

    # ---- งานข้ามการเปิด hub ใหม่ / เกินเวลา
    def _restore_from(self, doc, log_text=None):
        state = Path(self.tmp) / hub.GPU_APPLY_STATE_NAME
        state.write_text(json.dumps(doc), encoding="utf-8")
        if log_text is not None:
            (Path(self.tmp) / "gpu-apply.log").write_text(log_text, encoding="utf-8")
        hub._gpu_job.update(state="idle", log=None, pid=None, created=None, proc=None, orphan=False, timeout=False)
        with mock.patch.object(hub, "_gpu_state_path", return_value=state):
            hub.gpu_job_restore()

    def test_restore_follows_a_live_launcher_then_reads_its_result(self):
        code = "import time; time.sleep(1.5); print('  ผลลัพธ์: busy — ยังมีแชต (exit 3)')"
        log = Path(self.tmp) / "gpu-apply.log"
        with open(log, "wb") as fh:
            p = subprocess.Popen([sys.executable, "-c", code], stdout=fh, stderr=subprocess.STDOUT,
                                 env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        try:
            alive, created = hub._proc_info(p.pid)
            self.assertTrue(alive)
            self._restore_from({"state": "running", "pid": p.pid, "created": created, "started_at": hub._now_iso()})
            self.assertEqual(hub.gpu_job_snapshot()["state"], "running")
            self.assertTrue(hub.gpu_job_active())
            with self.assertRaises(hub.GpuJobBusy):          # PUT ระหว่างงาน = 409
                hub.gpu_choice_save({ID27: "cpu"})
            self.assertFalse(hub.gpu_apply_start())          # ห้ามสั่งตัวเปิดตัวที่สองซ้อน
            p.wait(10)
            for _ in range(60):
                if hub._gpu_job["state"] != "running":
                    break
                time.sleep(0.1)
            j = hub.gpu_job_snapshot()
            self.assertEqual((j["state"], j["rc"]), ("busy", 3))
            self.assertFalse(hub.gpu_job_active())
        finally:
            p.kill()
            hub._gpu_job.update(state="idle", pid=None, orphan=False, proc=None)

    def test_restore_of_finished_or_reused_pid(self):
        # pid ที่ยังมีอยู่แต่เวลาเริ่มไม่ตรง (ถูกโปรแกรมอื่นนำกลับมาใช้) = ตัวเปิดจบไปแล้ว → อ่านผลจากบันทึก
        self._restore_from({"state": "running", "pid": os.getpid(), "created": 1, "started_at": hub._now_iso()},
                           "#qwen-hub\n  ผลลัพธ์: done — เปิด llama-server ด้วยแผน GPU ใหม่แล้ว (exit 0)\n")
        self.assertEqual(hub.gpu_job_snapshot()["state"], "done")
        self.assertFalse(hub.gpu_job_active())
        # ไม่มีบรรทัดผลลัพธ์ = ไม่ทราบผล (ไม่ใช่ "ล้ม")
        self._restore_from({"state": "running", "pid": 0, "started_at": hub._now_iso()}, "#qwen-hub\n  [2/4] ...\n")
        self.assertEqual(hub.gpu_job_snapshot()["state"], "unknown")
        hub._gpu_job.update(state="idle", log=None)

    def test_timeout_does_not_allow_a_second_launcher(self):
        argv = [sys.executable, "-c", "import time; time.sleep(2.0)"]
        log = Path(self.tmp) / "gpu-apply.log"
        with mock.patch.object(hub, "_gpu_apply_cmd", return_value=(argv, log, True)), \
                mock.patch.object(hub, "GPU_APPLY_MAX_S", 0.4):
            hub._gpu_job.update(state="idle", proc=None, orphan=False)
            self.assertTrue(hub.gpu_apply_start())
            time.sleep(1.0)
            j = hub.gpu_job_snapshot()
            self.assertEqual(j["state"], "failed")
            self.assertTrue(j["still_running"])
            self.assertFalse(hub.gpu_apply_start())          # โปรเซสเดิมยังไม่จบ
            for _ in range(60):
                if hub._gpu_job["proc"] is None:
                    break
                time.sleep(0.1)
        j = hub.gpu_job_snapshot()
        self.assertEqual((j["state"], j["rc"]), ("done", 0))
        self.assertFalse(j["still_running"])

    def test_job_log_can_be_renamed_while_a_child_holds_it(self):
        # router ที่ตัวเปิดเปิดสืบทอด handle ของบันทึกไปถือไว้ตลอด — ต้องยังลบ/หมุนเวียนไฟล์ได้
        argv = [sys.executable, "-c", "import time; time.sleep(1.5)"]
        log = Path(self.tmp) / "gpu-apply.log"
        with mock.patch.object(hub, "_gpu_apply_cmd", return_value=(argv, log, True)):
            hub._gpu_job.update(state="idle", proc=None, orphan=False)
            self.assertTrue(hub.gpu_apply_start())
            time.sleep(0.3)
            os.replace(str(log), str(log) + ".old")
            for _ in range(60):
                if hub._gpu_job["state"] != "running":
                    break
                time.sleep(0.1)

    def test_dryrun_never_targets_llm_root(self):
        with mock.patch.dict(os.environ, {"QWEN_GPU_DRYRUN": "1", "QWEN_GPU_DRYRUN_OUT": str(hub.LLM_ROOT)}):
            with self.assertRaises(RuntimeError):
                hub._gpu_apply_cmd()


@unittest.skipIf(hub is None, HUB_ERR or "")
class HubGpuHttpTests(unittest.TestCase):
    """Origin: หน้าอื่นสั่งเขียน/รีสตาร์ตไม่ได้ (403) — ทดสอบผ่าน HTTP จริงบนพอร์ตสุ่ม"""

    @classmethod
    def setUpClass(cls):
        cls.srv = hub.ThreadingHTTPServer(("127.0.0.1", 0), hub.HubHandler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def req(self, method, path, origin=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Content-Type": "application/json"}
        if origin:
            h["Origin"] = origin
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, dict(r.getheaders()), data

    def test_foreign_origin_is_forbidden(self):
        started = mock.Mock(side_effect=AssertionError("ต้องไม่ถูกเรียก"))
        with mock.patch.object(hub, "gpu_apply_start", started), \
                mock.patch.object(hub, "gpu_choice_save", started):
            for o in ("http://evil.example", "http://127.0.0.1:8100.evil.com", "null", "http://127.0.0.1:9999"):
                with self.subTest(origin=o):
                    self.assertEqual(self.req("PUT", "/api/gpu/choice", o, {"models": {}})[0], 403)
                    self.assertEqual(self.req("POST", "/api/gpu/apply", o, {})[0], 403)

    def test_preflight_allows_put_for_our_pages(self):
        st, h, _ = self.req("OPTIONS", "/api/gpu/choice", "http://127.0.0.1:8103")
        self.assertEqual(st, 204)
        self.assertEqual(h.get("Access-Control-Allow-Origin"), "http://127.0.0.1:8103")
        self.assertIn("PUT", h.get("Access-Control-Allow-Methods", ""))

    def test_bad_body_is_400_bilingual(self):
        st, _h, data = self.req("PUT", "/api/gpu/choice", "http://127.0.0.1:8103", {"x": 1})
        self.assertEqual(st, 400)
        d = json.loads(data)
        self.assertTrue(d["error_th"] and d["error_en"])

    def test_apply_conflict_is_409(self):
        with mock.patch.object(hub, "gpu_apply_start", return_value=False):
            st, _h, data = self.req("POST", "/api/gpu/apply", "http://127.0.0.1:8103", {})
        self.assertEqual(st, 409)
        self.assertIn("job", json.loads(data))

    def test_put_while_a_job_runs_is_409(self):
        with mock.patch.object(hub, "gpu_choice_save", side_effect=hub.GpuJobBusy()):
            st, _h, data = self.req("PUT", "/api/gpu/choice", "http://127.0.0.1:8103", {"models": {}})
        self.assertEqual(st, 409)
        d = json.loads(data)
        self.assertTrue(d["error_th"] and d["error_en"])

    def raw(self, head, timeout=4):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=timeout)
        try:
            s.sendall(head.encode("latin-1"))
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            return data.split(b"\r\n", 1)[0].decode("latin-1")
        finally:
            s.close()

    def test_bad_content_length_gets_400_not_a_dropped_connection(self):
        for method, path in (("PUT", "/api/gpu/choice"), ("POST", "/api/gpu/apply"), ("PATCH", "/api/projects/x")):
            for cl in ("abc", "-1", "1e3"):
                with self.subTest(method=method, cl=cl):
                    # Host ต้องเป็นพอร์ตของ hub เอง (กัน DNS rebinding) — Host อื่นได้ 403 ก่อนถึงการตรวจ body
                    line = self.raw("%s %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nOrigin: http://127.0.0.1:8103\r\n"
                                    "Content-Length: %s\r\n\r\n" % (method, path, self.port, cl))
                    self.assertIn(" 400 ", line)
        self.assertEqual(hub.content_length({"Content-Length": " 12 "}), 12)
        self.assertEqual(hub.content_length({}), 0)

    def test_refresh_ignored_for_cross_site_subresources(self):
        seen = []

        def fake(refresh, live):
            seen.append(refresh)
            return {"ok": True}
        with mock.patch.object(hub, "gpu_api_payload", side_effect=fake):
            def get(headers):
                c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
                c.request("GET", "/api/gpu?refresh=1", headers=headers)
                c.getresponse().read()
                c.close()
            get({})                                                     # curl / สคริปต์ในเครื่อง
            get({"Origin": "http://127.0.0.1:8103"})                    # หน้าของเรา
            get({"Sec-Fetch-Site": "cross-site"})                       # <img src> จากเว็บอื่น (ไม่มี Origin)
            get({"Origin": "http://evil.example"})
        self.assertEqual(seen, [True, True, False, False])
        # เขียนจากเว็บอื่นแบบไม่มี Origin ก็ไม่ได้
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("POST", "/api/gpu/apply", body="{}", headers={"Sec-Fetch-Site": "cross-site"})
        r = c.getresponse()
        r.read()
        self.assertEqual(r.status, 403)
        self.assertEqual((r.getheader("Connection") or "").lower(), "close")   # body ไม่ได้อ่าน — ต้องปิดสาย
        c.close()


class HubStringsTests(unittest.TestCase):
    """STRINGS_UI ห้ามมี key ซ้ำ — dict literal ใน Python ให้ตัวหลังทับตัวแรกเงียบๆ
    (เคยเกิดจริง: gpu_failed ของ "รีสตาร์ตไม่สำเร็จ" ทับ "ตรวจ GPU ไม่สำเร็จตอนเปิด" เมนูบัญชีจึงบอกว่ารีสตาร์ตล้ม)"""

    def test_no_duplicate_keys(self):
        path = os.path.join(os.path.dirname(HUB), "hub_i18n_parts.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        dups = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                seen = {}
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        if k.value in seen:
                            dups.append((k.value, seen[k.value], k.lineno))
                        seen[k.value] = k.lineno
        self.assertEqual(dups, [])


if __name__ == "__main__":
    unittest.main()
