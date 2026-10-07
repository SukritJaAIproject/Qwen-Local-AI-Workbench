# -*- coding: utf-8 -*-
"""batch 3 สัญญา D3 (owner hub) — รันชุดทดสอบ C:\\LLM\\tests แล้วจดผลสรุปลง C:\\LLM\\logs\\tests-last.json

ทำไม: หน้า "ตรวจระบบ" (GET /api/doctor) บอกได้ว่าชุดทดสอบรอบล่าสุดผ่านไหม — แต่ unittest ไม่จดผลไว้ที่ไหนเลย
ไฟล์ผลมีแค่ตัวเลข + ชื่อเทสต์ที่ไม่ผ่าน (ไม่มีข้อความ log/traceback ซึ่งอาจมีข้อมูลของเครื่อง)

รัน:  C:\\Python313\\python.exe C:\\LLM\\projects\\record_tests.py [--pattern "test_b3_*.py"]
exit 0 = ผ่านทั้งหมด, 1 = มีข้อที่ไม่ผ่าน
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

TESTS = Path(r"C:\LLM\tests")
OUT = Path(r"C:\LLM\logs") / "tests-last.json"
FAILED_MAX = 20


def write_result(doc, out=OUT):
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tests-", suffix=".json", dir=str(out.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out)        # เขียนแบบ atomic — hub อ่านได้ระหว่างนี้โดยไม่เจอไฟล์ครึ่งๆ


def main(argv):
    pattern = "test*.py"
    if "--pattern" in argv:
        i = argv.index("--pattern")
        pattern = argv[i + 1] if i + 1 < len(argv) else pattern
    suite = unittest.TestLoader().discover(str(TESTS), pattern=pattern)
    t0 = time.time()
    res = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(suite)
    failed = [t.id() for t, _tb in (res.failures + res.errors)][:FAILED_MAX]
    doc = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), "ran": res.testsRun,
           "ok": res.wasSuccessful(), "failures": len(res.failures), "errors": len(res.errors),
           "skipped": len(res.skipped), "duration_s": round(time.time() - t0, 1), "python": sys.version.split()[0],
           "pattern": pattern, "failed": failed}
    write_result(doc)
    print("recorded %s: ran %d, failures %d, errors %d, skipped %d" % (OUT, doc["ran"], doc["failures"], doc["errors"],
                                                                       doc["skipped"]))
    return 0 if doc["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
