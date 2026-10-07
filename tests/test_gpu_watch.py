# -*- coding: utf-8 -*-
"""เทสต์ของงาน gpu_watch ใน mcp-local/scheduler.py (เสียบ/ถอด eGPU แล้วจัดแผน GPU ใหม่ให้เอง)

รัน:  C:\\Python313\\python.exe -m unittest tests.test_gpu_watch -v   (จาก C:\\LLM)
ไม่แตะ nvidia-smi / hub / ไฟล์ state จริง — ตรรกะตัดสินใจเป็นฟังก์ชันบริสุทธิ์
"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, os.path.join(ROOT, "mcp-local")):
    if p not in sys.path:
        sys.path.insert(0, p)
import scheduler as sch  # noqa: E402

A, B = "fp-internal-only", "fp-with-4090"


class DecideTests(unittest.TestCase):
    def test_same_clears_pending(self):
        act, pend, _ = sch.gpu_watch_decide(A, A, {"fp": B, "seen": 1}, None, 1000.0)
        self.assertEqual(act, "same")
        self.assertNotIn("fp", pend)

    def test_unknown_when_no_fingerprint_or_state(self):
        self.assertEqual(sch.gpu_watch_decide(None, A, {}, None, 1.0)[0], "unknown")
        self.assertEqual(sch.gpu_watch_decide(B, None, {}, None, 1.0)[0], "unknown")

    def test_needs_confirmation_rounds_then_applies(self):
        act, pend, _ = sch.gpu_watch_decide(B, A, {}, None, 1000.0)
        self.assertEqual((act, pend["fp"], pend["seen"]), ("confirm", B, 1))
        act, pend, _ = sch.gpu_watch_decide(B, A, pend, None, 1060.0)
        self.assertEqual(act, "apply")
        self.assertEqual(pend["applied_fp"], B)
        self.assertEqual(pend["applied_at"], 1060.0)

    def test_flapping_resets_count(self):
        _, pend, _ = sch.gpu_watch_decide(B, A, {}, None, 1.0)
        act, pend, _ = sch.gpu_watch_decide("fp-other", A, pend, None, 2.0)
        self.assertEqual((act, pend["seen"]), ("confirm", 1))

    def test_busy_and_cooldown(self):
        pend = {"fp": B, "seen": 5}
        self.assertEqual(sch.gpu_watch_decide(B, A, pend, "running", 10.0)[0], "busy")
        act, pend, _ = sch.gpu_watch_decide(B, A, pend, "done", 10.0)
        self.assertEqual(act, "apply")
        act, _, _ = sch.gpu_watch_decide(B, A, pend, "failed", 10.0 + sch.GPU_WATCH_COOLDOWN - 1)
        self.assertEqual(act, "cooldown")
        act, _, _ = sch.gpu_watch_decide(B, A, pend, "failed", 10.0 + sch.GPU_WATCH_COOLDOWN + 1)
        self.assertEqual(act, "apply")

    def test_stale_running_does_not_block(self):
        pend = {"fp": B, "seen": 5}
        self.assertEqual(sch.gpu_watch_decide(B, A, pend, "stale", 10.0)[0], "apply")


class JobTests(unittest.TestCase):
    def test_job_calls_hub_when_changed(self):
        with mock.patch.object(sch, "_load_state", return_value={"jobs": {"gpu_watch": {"pending": {"fp": B, "seen": 1}}}}), \
             mock.patch.object(sch, "_gpu_fingerprint_now", return_value=B), \
             mock.patch.object(sch, "_router_fingerprint", return_value=A), \
             mock.patch.object(sch, "_apply_state", return_value=("done", 100)), \
             mock.patch.object(sch, "_hub_apply", return_value="started") as hub, \
             mock.patch.object(sch, "_launcher_apply") as launcher:
            status, message, extra, report = sch.job_gpu_watch()
        self.assertEqual(status, "ok")
        self.assertEqual(extra["action"], "apply")
        self.assertEqual(hub.call_count, 1)
        self.assertEqual(launcher.call_count, 0)
        self.assertIn("hub", message)

    def test_job_falls_back_to_launcher(self):
        with mock.patch.object(sch, "_load_state", return_value={"jobs": {"gpu_watch": {"pending": {"fp": B, "seen": 3}}}}), \
             mock.patch.object(sch, "_gpu_fingerprint_now", return_value=B), \
             mock.patch.object(sch, "_router_fingerprint", return_value=A), \
             mock.patch.object(sch, "_apply_state", return_value=(None, None)), \
             mock.patch.object(sch, "_hub_apply", return_value="error: refused"), \
             mock.patch.object(sch, "_launcher_apply", return_value="launcher") as launcher:
            status, message, extra, _ = sch.job_gpu_watch()
        self.assertEqual(status, "ok")
        self.assertEqual(launcher.call_count, 1)

    def test_job_quiet_when_same(self):
        with mock.patch.object(sch, "_load_state", return_value={"jobs": {}}), \
             mock.patch.object(sch, "_gpu_fingerprint_now", return_value=A), \
             mock.patch.object(sch, "_router_fingerprint", return_value=A), \
             mock.patch.object(sch, "_apply_state", return_value=(None, None)), \
             mock.patch.object(sch, "_hub_apply") as hub:
            status, _, extra, _ = sch.job_gpu_watch()
        self.assertEqual((status, extra["action"]), ("ok", "same"))
        self.assertEqual(hub.call_count, 0)

    def test_registered(self):
        self.assertIn("gpu_watch", sch.JOB_NAMES)
        self.assertIn("gpu_watch", sch.JOBS)
        self.assertTrue(sch._gpu_watch_due({"jobs": {}}, 1.0))
        self.assertFalse(sch._gpu_watch_due({"jobs": {"gpu_watch": {"lastRunEpoch": 100.0}}}, 100.0 + 10))
        self.assertTrue(sch._gpu_watch_due({"jobs": {"gpu_watch": {"lastRunEpoch": 100.0}}}, 100.0 + sch.GPU_WATCH_EVERY))


if __name__ == "__main__":
    unittest.main()
