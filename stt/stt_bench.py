# -*- coding: utf-8 -*-
"""stt_bench.py — วัดความเร็ว/ความแม่นของบริการถอดเสียงที่รันอยู่ (ใช้ python ตัวไหนก็ได้ มีแต่ stdlib)

    C:\\Python313\\python.exe C:\\LLM\\stt\\stt_bench.py [--url http://127.0.0.1:8795] [--rounds 2] [--json out.json]

ทำอะไร
  1. สังเคราะห์เสียงตัวอย่างด้วยเสียง Windows ในเครื่อง (Microsoft Pattara = ไทย, Zira = อังกฤษ) ผ่าน tts_samples.ps1
     ลงโฟลเดอร์ชั่วคราว — ไม่ดาวน์โหลดอะไร ข้อความต้นฉบับอยู่ในไฟล์นี้ (ตัวเลขเขียนเป็นคำ ตามที่ TTS อ่าน)
  2. ส่งแต่ละไฟล์ให้ /v1/transcribe (Bearer token จาก secrets_util — ไม่พิมพ์ค่า) วัดเวลาทั้งคำขอ + เวลาที่บริการรายงาน
  3. ความแม่น: ไทย = CER (ตัดช่องว่าง/วรรคตอน), อังกฤษ = WER — whisper เขียนตัวเลขเป็นเลขอารบิก ("398") ขณะที่ต้นฉบับ
     เป็นคำ จึงมีค่าผิดพลาดขั้นต่ำจากเรื่องนี้เสมอ (อังกฤษ ~0.09-0.14 แม้ถอดถูกทุกคำ)
รอบแรกของแต่ละไฟล์อาจรวมเวลาโหลดโมเดล (บริการปลดโมเดลตอนว่าง) — ดู round 2 เป็นค่าคงตัว
--gap N = รอ N วินาทีก่อนแต่ละคำขอ: บริการจอดโมเดล GPU ไว้ใน RAM หลังงาน 2 วินาที (คืน VRAM ให้โมเดลแชต) คำขอที่ยิงติดกัน
จึงวัดได้แค่กรณี "ยังถือ GPU อยู่" — ผู้ใช้กดไมค์จริงห่างกันเป็นนาที ใช้ --gap 4 วัดเวลาที่ผู้ใช้เห็นจริง (รวมย้ายกลับ GPU)
"""
from __future__ import annotations

import argparse
import difflib
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(HERE))
import secrets_util  # noqa: E402

SAMPLES = [
    {"name": "th_short", "voice": "Pattara",
     "text": "สวัสดีครับ ช่วยสรุปรายงานการตรวจสอบตู้ชาร์จที่สถานีบางนาให้หน่อย แรงดันไฟฟ้าขาเข้าวัดได้สามร้อยเก้าสิบแปดโวลต์ "
             "และต้องเปลี่ยนรีเลย์ภายในสัปดาห์หน้า"},
    {"name": "en_short", "voice": "Zira",
     "text": "Please summarize the inspection report for the charging station in Bangna. The input voltage was three "
             "hundred ninety eight volts, and the relay must be replaced next week."},
    {"name": "th_long", "voice": "Pattara",
     "text": "วันที่สิบห้ากันยายน เจ้าหน้าที่ได้ตรวจสอบตู้ชาร์จรุ่นดีซีหนึ่งร้อยยี่สิบกิโลวัตต์ พบว่าหน้าจอแสดงรหัสข้อผิดพลาด "
             "ซึ่งหมายถึงแรงดันไฟฟ้าขาเข้าต่ำกว่าเกณฑ์ที่กำหนด สาเหตุเบื้องต้นคือขั้วต่อสายไฟหลวมที่เบรกเกอร์หลัก ทำให้เกิดความร้อนสะสม "
             "ช่างได้ขันขั้วต่อใหม่และวัดค่าความต้านทานฉนวนได้ห้าร้อยห้าสิบเมกะโอห์ม อยู่ในเกณฑ์ปกติ "
             "ข้อแนะนำคือควรตรวจสอบแรงบิดของขั้วต่อทุกสามเดือน และบันทึกค่าอุณหภูมิด้วยกล้องถ่ายภาพความร้อน"},
    {"name": "en_long", "voice": "Zira",
     "text": "On September fifteenth, the technician inspected the one hundred twenty kilowatt DC charger. The display "
             "showed an error code, which means the input voltage was below the required threshold. The initial cause "
             "was a loose terminal at the main breaker, which caused heat to build up. The technician tightened the "
             "terminal and measured an insulation resistance of five hundred fifty megaohms, which is within the normal "
             "range. It is recommended to check the terminal torque every three months and to record the temperature "
             "with a thermal camera."},
]


def _norm_th(t: str) -> str:
    return re.sub(r"[\s\.,!?\"'\-:;()]+", "", unicodedata.normalize("NFC", t).lower())


def _edits(a, b) -> int:
    d = 0
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op != "equal":
            d += max(a2 - a1, b2 - b1)
    return d


def cer(ref: str, hyp: str) -> float:
    r, h = _norm_th(ref), _norm_th(hyp)
    return _edits(r, h) / max(1, len(r))


def wer(ref: str, hyp: str) -> float:
    r = re.sub(r"[^\w\s]", " ", ref.lower()).split()
    h = re.sub(r"[^\w\s]", " ", hyp.lower()).split()
    return _edits(r, h) / max(1, len(r))


def synthesize(outdir: str, samples=SAMPLES) -> dict:
    """{ชื่อ: path WAV} — ใช้ tts_samples.ps1 (Windows PowerShell 5.1, เสียง OneCore ในเครื่อง) ข้ามเสียงที่ไม่มี"""
    spec = os.path.join(outdir, "samples.json")
    with open(spec, "w", encoding="utf-8") as fh:
        json.dump(samples, fh, ensure_ascii=False)
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0",
                      "powershell.exe")
    subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(HERE, "tts_samples.ps1"),
                    "-Spec", spec, "-OutDir", outdir], capture_output=True, timeout=180,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return {s["name"]: os.path.join(outdir, s["name"] + ".wav") for s in samples
            if os.path.isfile(os.path.join(outdir, s["name"] + ".wav"))}


def transcribe(url: str, data: bytes, language: str = "auto", content_type: str = "audio/wav",
               timeout: float = 600.0) -> tuple[int, dict, float]:
    u = urllib.parse.urlsplit(url)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=timeout)
    headers = dict(secrets_util.auth_headers())
    headers.update({"Content-Type": content_type, "Content-Length": str(len(data))})
    t0 = time.perf_counter()
    try:
        conn.request("POST", "/v1/transcribe?" + urllib.parse.urlencode({"language": language}), body=data,
                     headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        took = time.perf_counter() - t0
        try:
            obj = json.loads(body.decode("utf-8") or "{}")
        except ValueError:
            obj = {"raw": body[:200].decode("utf-8", "replace")}
        return resp.status, obj, took
    finally:
        conn.close()


def run(url: str, rounds: int = 2, wavs: dict | None = None, gap: float = 0.0) -> list[dict]:
    refs = {s["name"]: s["text"] for s in SAMPLES}
    out = []
    for rnd in range(1, rounds + 1):
        for name, path in (wavs or {}).items():
            if gap > 0:
                time.sleep(gap)                # ให้บริการจอดโมเดล GPU ก่อน (ดูหัวไฟล์)
            with open(path, "rb") as fh:
                data = fh.read()
            status, obj, took = transcribe(url, data)
            text = obj.get("text", "") if isinstance(obj, dict) else ""
            row = {"round": rnd, "sample": name, "status": status, "audio_s": obj.get("duration"),
                   "request_s": round(took, 2), "service_s": obj.get("elapsed_s"), "language": obj.get("language"),
                   "device": obj.get("device"), "model": obj.get("model"), "text": text}
            if status == 200 and name in refs:
                if name.startswith("th"):
                    row["cer"] = round(cer(refs[name], text), 3)
                else:
                    row["wer"] = round(wer(refs[name], text), 3)
            out.append(row)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8795")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--json", default="")
    ap.add_argument("--gap", type=float, default=0.0, help="seconds to wait before each request (see header)")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                          # noqa: BLE001
        pass
    tmp = tempfile.mkdtemp(prefix="stt-bench-")
    wavs = synthesize(tmp)
    if not wavs:
        print("no TTS voices available - nothing to measure", file=sys.stderr)
        return 2
    rows = run(args.url, args.rounds, wavs, args.gap)
    print("%-6s %-9s %-6s %-7s %-9s %-9s %-4s %-5s %s" % ("round", "sample", "status", "audio", "request", "service",
                                                         "lang", "dev", "CER/WER"))
    for r in rows:
        acc = r.get("cer", r.get("wer", ""))
        print("%-6s %-9s %-6s %-7s %-9s %-9s %-4s %-5s %s" % (r["round"], r["sample"], r["status"], r["audio_s"],
                                                             r["request_s"], r["service_s"], r["language"],
                                                             r["device"], acc))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
