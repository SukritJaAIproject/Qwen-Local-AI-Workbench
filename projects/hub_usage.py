# -*- coding: utf-8 -*-
"""batch 3 สัญญา D2 (owner hub) — บันทึกการใช้งานต่อคำขอ + สรุปสำหรับ GET /api/usage

ทำไม: ผู้ใช้ไม่รู้ว่าโทเคนหมดไปกับโปรเจกต์ไหน โมเดลไหนเร็ว/ช้าแค่ไหนจริง (27B ~1 tok/s แต่ไม่มีตัวเลขย้อนหลังให้ดู)
hub เป็นทางผ่านเดียวของทุกคำขอแชต จึงจดได้ครบโดยไม่แตะ llama-server

หนึ่งบรรทัด JSON ต่อคำตอบที่ส่งต่อเสร็จ (data\\usage.jsonl):
  {ts, project, model, prompt_tokens, cached_tokens, completion_tokens, prompt_tps, gen_tps, wall_s,
   tools_used (ชื่อเท่านั้น), compacted, error, conv}
  conv = แฮช 12 ตัวของ X-Conversation-Id (id สุ่มของ WebUI ไม่ใช่เนื้อหา) — ใช้จัดกลุ่ม "แชตล่าสุด" เท่านั้น
ห้ามมีเนื้อหาข้อความ/ผลเครื่องมือ/อาร์กิวเมนต์ใดๆ — อ่านเฉพาะตัวเลข timings/usage, ชื่อโมเดล, ชื่อเครื่องมือ
ไฟล์ถึง ~10 MB = เปลี่ยนชื่อเป็น usage-<เวลา>.jsonl แล้วเริ่มไฟล์ใหม่ (ไม่ลบของเก่า — อ่านย้อนหลังได้ตามช่วงวัน)
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

USAGE_NAME = "usage.jsonl"
ROTATE_BYTES = 10 * 1024 * 1024
DAYS_MAX = 90
RECENT_MAX = 50
SESSIONS_MAX = 20
TOOLS_MAX = 20
JSON_BUF_MAX = 4 * 1024 * 1024        # คำตอบแบบไม่สตรีมที่ใหญ่กว่านี้ไม่ parse (ไม่บวมหน่วยความจำ) — ได้แค่ wall/error
_TOOL_NAME_RE = re.compile(r"[A-Za-z0-9_.:\-]{1,64}")
_ROTATED_RE = re.compile(r"usage-\d{8}-\d{6}(?:-\d+)?\.jsonl")
FIELDS = ("ts", "project", "model", "prompt_tokens", "cached_tokens", "completion_tokens", "prompt_tps", "gen_tps",
          "wall_s", "tools_used", "compacted", "error", "conv")


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _int(v):
    v = _num(v)
    return int(v) if v is not None and v >= 0 else None


def conv_hash(conv_id):
    """X-Conversation-Id ของ WebUI = "<id ของแชต>::<โมเดล>" — ตัดโมเดลออก (เปลี่ยนโมเดลกลางแชตยังเป็นแชตเดิม) แล้วแฮช"""
    c = (conv_id or "").split("::", 1)[0].strip()
    return hashlib.sha256(c.encode("utf-8", "replace")).hexdigest()[:12] if c else None


class UsageTap:
    """อ่านคำตอบที่ proxy ส่งต่อ (SSE หรือ JSON ทั้งก้อน) เพื่อเก็บตัวเลข — ไม่แก้ไบต์ที่ส่งต่อ ไม่เก็บเนื้อหา
    Extend Mode ขอคำตอบต่อหลายท่อน: new_segment() ก่อนอ่านท่อนถัดไป (โทเคนคำตอบรวมทุกท่อน, prompt คิดจากท่อนแรก)"""

    def __init__(self, sse=True):
        self.sse = sse
        self._buf = b""
        self._json = bytearray()
        self._json_over = False
        self.segments = [{"timings": None, "usage": None}]
        self.tools = []
        self.model = None
        self.error = False
        self.finished = False
        self.client_gone = False
        self.deltas = 0

    def new_segment(self):
        self.segments.append({"timings": None, "usage": None})

    def feed(self, data):
        if not data:
            return
        if not self.sse:
            if len(self._json) + len(data) <= JSON_BUF_MAX:
                self._json += data
            else:
                self._json_over = True
            return
        self._buf += data
        while True:
            i = self._buf.find(b"\n\n")
            j = self._buf.find(b"\r\n\r\n")
            if i < 0 and j < 0:
                break
            if j >= 0 and (i < 0 or j < i):
                block, self._buf = self._buf[:j], self._buf[j + 4:]
            else:
                block, self._buf = self._buf[:i], self._buf[i + 2:]
            self._block(block)
        if len(self._buf) > JSON_BUF_MAX:          # ไม่มีขอบเหตุการณ์เลย = ไม่ใช่ SSE ที่เรารู้จัก ทิ้ง
            self._buf = b""

    def _block(self, block):
        for line in block.split(b"\n"):
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            raw = line[5:].strip()
            if raw == b"[DONE]":
                self.finished = True
                continue
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError, RecursionError):
                continue
            self.observe(payload)

    def close(self):
        """จบคำตอบ: parse JSON ที่สะสมไว้ (ไม่สตรีม) หรือเศษ SSE ท้ายสุด"""
        if not self.sse:
            if self._json and not self._json_over:
                try:
                    payload = json.loads(bytes(self._json).decode("utf-8"))
                except (ValueError, UnicodeDecodeError, RecursionError):
                    payload = None
                if isinstance(payload, dict):
                    self.observe(payload)
                    if payload.get("choices") or payload.get("output") or payload.get("content"):
                        self.finished = True
            self._json = bytearray()
        elif self._buf.strip():
            self._block(self._buf)
            self._buf = b""

    def _tool(self, name):
        if isinstance(name, str) and _TOOL_NAME_RE.fullmatch(name) and name not in self.tools \
                and len(self.tools) < TOOLS_MAX:
            self.tools.append(name)

    def observe(self, payload):
        if not isinstance(payload, dict):
            return
        seg = self.segments[-1]
        if isinstance(payload.get("model"), str) and not self.model:
            self.model = payload["model"][:120]
        if payload.get("error"):
            self.error = True
        if isinstance(payload.get("timings"), dict):
            seg["timings"] = payload["timings"]
        if isinstance(payload.get("usage"), dict):
            seg["usage"] = payload["usage"]
        typ = payload.get("type")
        if isinstance(typ, str):
            # /v1/responses (Codex) — usage อยู่ใน response.completed, การเรียกเครื่องมืออยู่ใน output item
            resp = payload.get("response") if isinstance(payload.get("response"), dict) else None
            if typ in ("response.completed", "response.done") and resp is not None:
                self.finished = True
                if isinstance(resp.get("usage"), dict):
                    seg["usage"] = resp["usage"]
            elif typ in ("response.failed", "error"):
                self.error = True
            item = payload.get("item") if isinstance(payload.get("item"), dict) else None
            if item is not None and item.get("type") == "function_call":
                self._tool(item.get("name"))
            if typ == "message_stop":
                self.finished = True
        for out in payload.get("output") or [] if isinstance(payload.get("output"), list) else []:
            if isinstance(out, dict) and out.get("type") == "function_call":
                self._tool(out.get("name"))
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            ch = choices[0]
            if ch.get("finish_reason"):
                self.finished = True
            for part in (ch.get("delta"), ch.get("message")):
                if not isinstance(part, dict):
                    continue
                if part.get("content") or part.get("reasoning_content"):
                    self.deltas += 1
                for tc in part.get("tool_calls") or []:
                    if isinstance(tc, dict):
                        self._tool((tc.get("function") or {}).get("name") if isinstance(tc.get("function"), dict) else None)

    def numbers(self):
        """ตัวเลขของคำตอบนี้ (None = ไม่รู้)"""
        first = self.segments[0]
        t0 = first["timings"] or {}
        u0 = first["usage"] or {}
        prompt = cached = None
        if t0:
            pn, cn = _int(t0.get("prompt_n")), _int(t0.get("cache_n"))
            if pn is not None or cn is not None:
                prompt = (pn or 0) + (cn or 0)
            cached = cn
        if prompt is None:
            prompt = _int(u0.get("prompt_tokens"))
            if prompt is None:
                prompt = _int(u0.get("input_tokens"))
        if cached is None:
            det = u0.get("prompt_tokens_details") or u0.get("input_tokens_details") or {}
            cached = _int(det.get("cached_tokens")) if isinstance(det, dict) else None
        comp, gen_ms, gen_steps = 0, 0.0, 0
        have_comp = False
        for seg in self.segments:
            t, u = seg["timings"] or {}, seg["usage"] or {}
            n = _int(t.get("predicted_n"))
            if n is None:
                n = _int(u.get("completion_tokens"))
                if n is None:
                    n = _int(u.get("output_tokens"))
            else:
                ms = _num(t.get("predicted_ms"))
                if ms is not None and ms > 0 and n > 0:
                    gen_ms += ms
                    gen_steps += n - 1
            if n is not None:
                comp += n
                have_comp = True
        pps = _num(t0.get("prompt_per_second")) if t0 else None
        # [fix-hub b3 2026-10-06] ความเร็วเดียวกับ llama-server: predicted_per_second ของมันคือ (n-1)/predicted_ms (โทเคนแรก
        # ออกมาตอนเริ่มนับเวลา — ช่วงเวลามี n-1 ช่วง) เดิม hub ใช้ n/ms จึงสูงเกินจริง n/(n-1) เท่า (ผู้ตรวจวัด: 36 โทเคน 5.46 vs
        # 5.31, คำตอบ 5 โทเคนเกิน 25%) — ท่อนเดียวใช้ตัวเลขของ llama-server ตรงๆ, หลายท่อน (Extend Mode) Σ(n-1)/Σms
        gps = None
        single = len(self.segments) == 1 and t0 and _num(t0.get("predicted_per_second"))
        if single and single > 0:
            gps = single
        elif gen_ms > 0 and gen_steps > 0:
            gps = gen_steps / gen_ms * 1000.0
        if gps is None and t0:
            gps = _num(t0.get("predicted_per_second"))
        return {"prompt_tokens": prompt, "cached_tokens": cached,
                "completion_tokens": comp if have_comp else (self.deltas or None),
                "prompt_tps": round(pps, 2) if pps is not None else None,
                "gen_tps": round(gps, 2) if gps is not None else None}


def make_record(project, model, tap, wall_s, compacted, error, conv=None, now=None):
    nums = tap.numbers() if tap is not None else {k: None for k in ("prompt_tokens", "cached_tokens", "completion_tokens",
                                                                    "prompt_tps", "gen_tps")}
    rec = {"ts": (now or datetime.now().astimezone()).isoformat(timespec="seconds"),
           "project": str(project or "")[:80], "model": str(model or (tap.model if tap else "") or "")[:120]}
    rec.update(nums)
    rec.update(wall_s=round(max(0.0, float(wall_s or 0.0)), 2), tools_used=list(tap.tools) if tap else [],
               compacted=bool(compacted), error=bool(error), conv=conv)
    return rec


class UsageLog:
    """ต่อท้าย data\\usage.jsonl (ล็อกเดียวทุกพอร์ต) + อ่านย้อนหลังตามช่วงวัน (ไฟล์ปัจจุบัน + ไฟล์ที่หมุนไว้)"""

    def __init__(self, folder_fn, rotate_bytes=ROTATE_BYTES):
        self._folder_fn = folder_fn
        self.rotate_bytes = rotate_bytes
        self._lock = threading.Lock()
        self._cache = None                  # (สถานะไฟล์, รายการ) — /api/usage อ่านซ้ำถี่ได้ไม่ต้อง parse ใหม่

    def path(self):
        return Path(self._folder_fn()) / USAGE_NAME

    def append(self, rec):
        line = json.dumps({k: rec.get(k) for k in FIELDS}, ensure_ascii=False) + "\n"
        p = self.path()
        with self._lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                if p.stat().st_size + len(line) > self.rotate_bytes:
                    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    dst = p.with_name("usage-%s.jsonl" % stamp)
                    i = 1
                    while dst.exists():
                        dst = p.with_name("usage-%s-%d.jsonl" % (stamp, i))
                        i += 1
                    os.replace(p, dst)        # เปลี่ยนชื่อ ไม่ลบ — ของเก่ายังอ่านได้ใน /api/usage
            except FileNotFoundError:
                pass
            with open(p, "a", encoding="utf-8", newline="\n") as f:
                f.write(line)

    def _files(self, since_epoch):
        p = self.path()
        out = []
        try:
            for f in p.parent.iterdir():
                if _ROTATED_RE.fullmatch(f.name):
                    try:
                        if f.stat().st_mtime >= since_epoch:
                            out.append(f)
                    except OSError:
                        pass
        except OSError:
            return []
        out.sort(key=lambda f: f.name)
        if p.is_file():
            out.append(p)
        return out

    def read(self, since_epoch):
        files = self._files(since_epoch)
        sig = tuple((str(f), f.stat().st_size, f.stat().st_mtime_ns) for f in files if f.exists())
        with self._lock:
            if self._cache and self._cache[0] == sig:
                return self._cache[1]
        rows = []
        for f in files:
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            r = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(r, dict) and isinstance(r.get("ts"), str):
                            rows.append(r)
            except OSError:
                continue
        with self._lock:
            self._cache = (sig, rows)
        return rows


# ---------------------------------------------------------------- สรุปสำหรับ /api/usage
def _blank():
    return {"requests": 0, "prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0, "errors": 0, "compacted": 0,
            "wall_s": 0.0, "_gen_n": 0, "_gen_s": 0.0, "_pp_n": 0, "_pp_s": 0.0}


def _add(b, r):
    b["requests"] += 1
    pt, ct, cp = _int(r.get("prompt_tokens")) or 0, _int(r.get("cached_tokens")) or 0, _int(r.get("completion_tokens")) or 0
    b["prompt_tokens"] += pt
    b["cached_tokens"] += ct
    b["completion_tokens"] += cp
    b["errors"] += 1 if r.get("error") else 0
    b["compacted"] += 1 if r.get("compacted") else 0
    b["wall_s"] += _num(r.get("wall_s")) or 0.0
    g = _num(r.get("gen_tps"))
    if g and g > 0 and cp:
        b["_gen_n"] += cp
        b["_gen_s"] += cp / g
    p = _num(r.get("prompt_tps"))
    processed = max(0, pt - ct)
    if p and p > 0 and processed:
        b["_pp_n"] += processed
        b["_pp_s"] += processed / p


def _done(b):
    out = {k: v for k, v in b.items() if not k.startswith("_")}
    out["wall_s"] = round(out["wall_s"], 1)
    # ค่าเฉลี่ยถ่วงด้วยจำนวนโทเคน (ไม่ใช่เฉลี่ยของ tok/s ต่อคำขอ — คำตอบสั้นๆ 5 โทเคนจะดึงค่าเพี้ยน)
    out["gen_tps"] = round(b["_gen_n"] / b["_gen_s"], 2) if b["_gen_s"] > 0 else None
    out["prompt_tps"] = round(b["_pp_n"] / b["_pp_s"], 1) if b["_pp_s"] > 0 else None
    out["total_tokens"] = out["prompt_tokens"] + out["completion_tokens"]
    return out


def _short_model(m):
    return re.sub(r"(-UD)?-(I?Q\d\w*|MXFP4\w*|F16|BF16|F32)$", "", m or "", flags=re.I) or (m or "?")


def aggregate(rows, days=7, now=None, project_names=None):
    """{range, totals, per_day[], per_project[], per_model[], recent[], sessions[]} — ดูรูปเต็มใน notes ของ hub"""
    now = now or datetime.now().astimezone()
    days = max(1, min(DAYS_MAX, int(days or 7)))
    first = (now - timedelta(days=days - 1)).date()
    dates = [(first + timedelta(days=i)).isoformat() for i in range(days)]
    dset = set(dates)
    names = project_names or {}
    rows = [r for r in rows if isinstance(r.get("ts"), str) and r["ts"][:10] in dset]
    rows.sort(key=lambda r: r["ts"])
    tot = _blank()
    per_day = {d: {"all": _blank(), "models": {}} for d in dates}
    per_proj, per_model, sessions = {}, {}, {}
    for r in rows:
        d = r["ts"][:10]
        model = str(r.get("model") or "?")
        proj = str(r.get("project") or "?")
        _add(tot, r)
        _add(per_day[d]["all"], r)
        _add(per_day[d]["models"].setdefault(model, _blank()), r)
        _add(per_proj.setdefault(proj, _blank()), r)
        _add(per_model.setdefault(model, _blank()), r)
        conv = r.get("conv")
        if isinstance(conv, str) and conv:
            s = sessions.setdefault((proj, conv), {"b": _blank(), "first": r["ts"], "last": r["ts"], "models": [],
                                                   "tools": []})
            _add(s["b"], r)
            s["last"] = r["ts"]
            if model not in s["models"]:
                s["models"].append(model)
            for t in r.get("tools_used") or []:
                if isinstance(t, str) and t not in s["tools"] and len(s["tools"]) < TOOLS_MAX:
                    s["tools"].append(t)
    out_days = []
    for d in dates:
        e = _done(per_day[d]["all"])
        e["date"] = d
        e["models"] = {m: _done(b) for m, b in sorted(per_day[d]["models"].items())}
        out_days.append(e)
    out_proj = []
    for p, b in per_proj.items():
        e = _done(b)
        e.update(project=p, name=names.get(p) or p)
        out_proj.append(e)
    out_proj.sort(key=lambda e: (-e["total_tokens"], e["project"]))
    out_model = []
    for m, b in per_model.items():
        e = _done(b)
        e.update(model=m, short=_short_model(m))
        out_model.append(e)
    out_model.sort(key=lambda e: (-e["total_tokens"], e["model"]))
    recent = []
    for r in reversed(rows[-RECENT_MAX:]):
        x = {k: r.get(k) for k in FIELDS}
        x["name"] = names.get(x.get("project")) or x.get("project")
        recent.append(x)
    sess = []
    for (proj, conv), s in sorted(sessions.items(), key=lambda kv: kv[1]["last"], reverse=True)[:SESSIONS_MAX]:
        e = _done(s["b"])
        e.update(conv=conv, project=proj, name=names.get(proj) or proj, first_ts=s["first"], last_ts=s["last"],
                 models=s["models"], tools_used=s["tools"])
        sess.append(e)
    totals = _done(tot)
    return {"days": days, "from": dates[0], "to": dates[-1], "generated_at": now.isoformat(timespec="seconds"),
            "totals": totals, "per_day": out_days, "per_project": out_proj, "per_model": out_model,
            "models": [m["model"] for m in out_model], "recent": recent, "sessions": sess}
