# -*- coding: utf-8 -*-
"""Build a fully synthetic demo data set for screenshots (no real chats, projects or user data).

Creates under WORK:
  fixtures/demo-en.json            WebUI IndexedDB fixture (English chats + one Thai title)
  projects.json, settings.json     demo projects / prefs for a demo hub instance
  data/<slug>/attachments|outputs  synthetic project files, memory.json, research jobs
  data/usage.jsonl                 synthetic usage log (30 days)
  gpu/                             simulated GPU list (RTX 1000 Ada + RTX 4090) + generated profile
"""
import datetime
import json
import os
import random
import subprocess
import sys

WORK = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WORK, "data")
FAST = "Qwen3-4B-Instruct-2507-Q4_K_M"
BIG = "Qwen3.8-27B-UD-Q4_K_M"
CODER = "Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL"
OSS = "gpt-oss-20b-MXFP4"

PROJECTS = [
    {"slug": "demo", "name": "Demo", "port": 8172, "think": "off", "model": BIG, "extend": True,
     "system_prompt": "You help an EV-charging operations team. Be concise, use tables for numbers, "
                      "and cite project file names when you use them."},
    {"slug": "ocpp-research", "name": "OCPP research", "port": 8173, "think": "auto", "model": BIG, "extend": True,
     "system_prompt": "Answer with references to the OCPP 1.6J / 2.0.1 specifications where relevant."},
    {"slug": "thai-docs", "name": "เอกสารภาษาไทย", "port": 8174, "think": "off", "model": BIG, "extend": True,
     "system_prompt": "ตอบเป็นภาษาไทย กระชับ อ้างอิงชื่อไฟล์ของโปรเจกต์เมื่อใช้ข้อมูลจากไฟล์"},
    {"slug": "data-analysis", "name": "Data analysis", "port": 8175, "think": "off", "model": CODER, "extend": True,
     "system_prompt": "Prefer pandas and matplotlib. Show the code you ran."},
]

T0 = 1791100000000  # fixed ms timestamp base for fixture ids/timestamps


def w(path, text, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# ----------------------------------------------------------------------------------- fixture (IndexedDB)
def chain(cid, name, turns, system=None, model=BIG, tps=42.6):
    """turns = [(role, content)], linear branch. Returns (conversation, messages)."""
    msgs = []
    ids = []
    root = "%s-root" % cid
    seq = []
    if system:
        seq.append(("system", system))
    seq.extend(turns)
    prev = root
    t = T0
    for i, (role, content) in enumerate(seq):
        mid = "%s-m%02d" % (cid, i)
        ids.append(mid)
        m = {"id": mid, "convId": cid, "type": "system" if role == "system" else "text", "role": role,
             "content": content, "parent": prev, "children": [], "timestamp": t + i * 1000}
        if role in ("user", "assistant"):
            m["toolCalls"] = ""
        if role == "user":
            m["extra"] = []
        if role == "assistant":
            n = max(40, len(content) // 4)
            m["model"] = model
            m["timings"] = {"prompt_n": 900 + 37 * i, "prompt_ms": round((900 + 37 * i) / 0.7, 1),
                            "predicted_n": n, "predicted_ms": round(n / tps * 1000, 1),
                            "predicted_per_second": tps}
        msgs.append(m)
        prev = mid
    for a, b in zip(msgs, msgs[1:]):
        a["children"] = [b["id"]]
    rootm = {"id": root, "convId": cid, "type": "root", "role": "system", "content": "", "parent": None,
             "children": [msgs[0]["id"]] if msgs else [], "timestamp": T0, "toolCalls": ""}
    conv = {"id": cid, "name": name, "lastModified": T0, "currNode": msgs[-1]["id"], "reasoningEffort": "default"}
    return conv, [rootm] + msgs


REPORT = """Here is the week 39 summary from `attachments/charger-faults-week39.csv`.

## Uptime by station

| Station | Sessions | Faults | Uptime | Main fault |
|---|---:|---:|---:|---|
| CP-01 | 412 | 1 | 99.7% | — |
| CP-02 | 388 | 2 | 99.3% | Ground fault (cleared) |
| CP-03 | 305 | 9 | 96.1% | Over-temperature (92 °C) |
| CP-04 | 351 | 4 | 98.4% | Lost WebSocket connection |
| CP-05 | 127 | 14 | 91.8% | Contactor stuck |

## What to fix first

1. **CP-05** — the contactor fault repeats every 9-12 sessions. Replace the contactor before the weekend peak.
2. **CP-03** — over-temperature trips start above 90 °C. Clean the cabinet air filter and check fan current.
3. **CP-04** — reconnects cluster around 02:00, which matches the router reboot window. Move the reboot or raise the OCPP heartbeat timeout.

> The other two stations are within the 99% target.

I used this snippet to compute the table:

```python
import pandas as pd

df = pd.read_csv("attachments/charger-faults-week39.csv", parse_dates=["start"])
summary = (df.groupby("station")
             .agg(sessions=("session_id", "nunique"),
                  faults=("fault", "count"),
                  downtime_min=("downtime_min", "sum")))
summary["uptime"] = 1 - summary.downtime_min / (7 * 24 * 60)
print(summary.sort_values("uptime"))
```

![Uptime by station, week 39](/_qwen/out/uptime-week39.png)
"""

DASHBOARD = """Here is a self-contained page — open it in the side panel with the **Open** button on the code block.

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>Week 39 · Charger fleet</title>
<style>
  body{font-family:system-ui,sans-serif;margin:0;padding:20px;background:#faf9f5;color:#1f1e1d}
  h1{font-size:18px;margin:0 0 14px}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px}
  .k{background:#fff;border:1px solid #e6e2d8;border-radius:12px;padding:12px}
  .k b{display:block;font-size:22px;margin-top:4px}
  .bar{height:10px;border-radius:5px;background:#d97757}
  table{width:100%;border-collapse:collapse;font-size:13px}
  td,th{padding:6px 4px;border-bottom:1px solid #eee;text-align:left}
</style></head>
<body>
  <h1>Charger fleet · week 39</h1>
  <div class="grid">
    <div class="k">Sessions<b>1,583</b></div>
    <div class="k">Fleet uptime<b>97.1%</b></div>
    <div class="k">Open faults<b>3</b></div>
  </div>
  <table>
    <tr><th>Station</th><th>Uptime</th><th style="width:45%"></th></tr>
    <tr><td>CP-01</td><td>99.7%</td><td><div class="bar" style="width:99.7%"></div></td></tr>
    <tr><td>CP-02</td><td>99.3%</td><td><div class="bar" style="width:99.3%"></div></td></tr>
    <tr><td>CP-03</td><td>96.1%</td><td><div class="bar" style="width:96.1%"></div></td></tr>
    <tr><td>CP-04</td><td>98.4%</td><td><div class="bar" style="width:98.4%"></div></td></tr>
    <tr><td>CP-05</td><td>91.8%</td><td><div class="bar" style="width:91.8%"></div></td></tr>
  </table>
</body></html>
```
"""

OCPP = """In short: **1.6J** is what most chargers in the field speak today; **2.0.1** is the better long-term target.

| | OCPP 1.6J | OCPP 2.0.1 |
|---|---|---|
| Transport | JSON over WebSocket | JSON over WebSocket |
| Security | Profiles added later (whitepaper) | Security profiles 1-3 built in |
| Device model | Flat configuration keys | Component/variable device model |
| Transactions | Start/StopTransaction | Unified `TransactionEvent` |
| Smart charging | Charging profiles | Profiles + ISO 15118 integration |

A CSMS usually has to support both during a migration, charger by charger.
"""

MXFP4 = """**MXFP4** is a 4-bit *microscaling* floating-point format from the OCP MX specification.

- Weights are stored as 4-bit FP values (E2M1: 1 sign, 2 exponent, 1 mantissa bit).
- Every block of **32** values shares one 8-bit power-of-two scale (E8M0).
- Effective size is about **4.25 bits per weight**, close to Q4 integer formats, but the shared exponent keeps more dynamic range.

That is why `gpt-oss-20b-MXFP4.gguf` fits in ~12 GB and still runs at full speed on an RTX 4090.
"""

EMAIL = """**Subject:** Planned maintenance — charging site B, Saturday 08:00-10:00

Dear customers,

We will carry out planned maintenance at charging site B on **Saturday, 11 October, 08:00-10:00**. Chargers CP-04 and CP-05 will be unavailable during this window; CP-01 to CP-03 stay in service.

We apologise for the inconvenience and thank you for your patience.

Kind regards,
Operations team
"""

PLOT = """```python
import matplotlib.pyplot as plt
import pandas as pd

df = pd.read_csv("attachments/sessions.csv", parse_dates=["day"])
weekly = df.resample("W", on="day")["sessions"].sum()
ax = weekly.plot(kind="bar", color="#d97757", figsize=(8, 3))
ax.set_ylabel("sessions")
plt.tight_layout()
plt.savefig("outputs/weekly-sessions.png", dpi=150)
```
"""

REGEX = r"""Thai mobile numbers start with 06, 08 or 09 and have 10 digits:

```regex
^0[689]\d-?\d{3}-?\d{4}$
```

`\d` matches the digits, and the optional `-` accepts both `0812345678` and `081-234-5678`.
"""

THAI = """สรุปผลตรวจสถานีประจำเดือนกันยายน (จาก `attachments/site-inspection-2026-09.pdf`)

## ประเด็นสำคัญ

- ตู้ **CP-03** อุณหภูมิตู้สูงสุด 92 °C ควรล้างแผ่นกรองอากาศ
- ตู้ **CP-05** คอนแทคเตอร์ค้าง 3 ครั้ง แนะนำให้เปลี่ยนก่อนสุดสัปดาห์
- แรงดันขาเข้าเฉลี่ย 398 V อยู่ในเกณฑ์ปกติ

| ตู้ | สถานะ | สิ่งที่ต้องทำ |
|---|---|---|
| CP-03 | เฝ้าระวัง | ล้างแผ่นกรอง ตรวจพัดลม |
| CP-05 | ต้องซ่อม | เปลี่ยนคอนแทคเตอร์ |
"""


def fixture():
    convs, msgs = [], []
    items = [
        chain("demo-c1", "Weekly charger uptime report", [
            ("user", "Using attachments/charger-faults-week39.csv, summarize uptime per station and tell me what to fix first."),
            ("assistant", REPORT),
            ("user", "Turn it into a small HTML dashboard I can open in the side panel."),
            ("assistant", DASHBOARD),
        ], system="Answer concisely. Use the project files when relevant."),
        chain("demo-c2", "Compare OCPP 1.6J and 2.0.1", [
            ("user", "Compare OCPP 1.6J and 2.0.1 briefly."), ("assistant", OCPP)]),
        chain("demo-c3", "Explain MXFP4 quantization", [
            ("user", "What is MXFP4 and why is it used for gpt-oss?"), ("assistant", MXFP4)], tps=79.7, model=FAST),
        chain("demo-c4", "Draft a maintenance notice email", [
            ("user", "Draft a short customer notice about Saturday maintenance at site B."), ("assistant", EMAIL)]),
        chain("demo-c5", "Plot weekly charging sessions", [
            ("user", "Plot weekly charging sessions from attachments/sessions.csv."), ("assistant", PLOT)],
            model=CODER, tps=91.0),
        chain("demo-c6", "Regex for Thai phone numbers", [
            ("user", "Regex for Thai mobile phone numbers?"), ("assistant", REGEX)], model=FAST, tps=79.7),
        chain("demo-c7", "สรุปผลตรวจสถานีประจำเดือน", [
            ("user", "สรุปผลตรวจสถานีเดือนกันยายนจากไฟล์ในโปรเจกต์ให้หน่อย"), ("assistant", THAI)]),
    ]
    for c, m in items:
        convs.append(c)
        msgs.extend(m)
    return {"conversations": convs, "messages": msgs}


# ----------------------------------------------------------------------------------- project files
CSV = ["station,session_id,start,fault,downtime_min"]


def make_files():
    rnd = random.Random(39)
    rows = ["station,session_id,start,fault,downtime_min"]
    for i in range(1, 160):
        st = "CP-0%d" % rnd.randint(1, 5)
        fault = rnd.choice(["", "", "", "", "OverTemperature", "GroundFailure", "ConnectorLockFailure"])
        rows.append("%s,S%05d,2026-09-%02d %02d:%02d,%s,%d" % (st, 1000 + i, rnd.randint(22, 28), rnd.randint(0, 23),
                                                            rnd.randint(0, 59), fault, rnd.randint(4, 40) if fault else 0))
    demo = os.path.join(DATA, "demo")
    w(os.path.join(demo, "attachments", "charger-faults-week39.csv"), "\n".join(rows) + "\n")
    w(os.path.join(demo, "attachments", "sessions.csv"),
      "day,sessions\n" + "".join("2026-09-%02d,%d\n" % (d, 180 + (d * 37) % 90) for d in range(1, 29)))
    w(os.path.join(demo, "attachments", "ocpp-log-CP-04.txt"),
      '[2,"19223201","BootNotification",{"chargePointVendor":"Demo","chargePointModel":"DC-60"}]\n'
      '[3,"19223201",{"status":"Accepted","interval":300}]\n'
      '[2,"19223202","StatusNotification",{"connectorId":1,"status":"Faulted","errorCode":"OtherError"}]\n')
    w(os.path.join(demo, "attachments", "maintenance-checklist.md"),
      "# Monthly checklist\n\n- Air filter\n- Fan current\n- Contactor cycles\n- Cable insulation\n")
    # small valid PDF via PIL
    try:
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (620, 877), "white")
        d = ImageDraw.Draw(im)
        d.text((40, 40), "Site inspection - September 2026 (synthetic demo file)", fill="black")
        for k, line in enumerate(["CP-03 cabinet 92 C - clean air filter", "CP-05 contactor stuck x3",
                                  "Input voltage 398 V - normal"]):
            d.text((40, 90 + 24 * k), line, fill="black")
        im.save(os.path.join(demo, "attachments", "site-inspection-2026-09.pdf"))
    except Exception as exc:  # noqa: BLE001
        print("pdf skipped:", exc)
    w(os.path.join(demo, "outputs", "weekly-report-w39.md"), "# Week 39\n\nFleet uptime 97.1 %.\n")
    w(os.path.join(demo, "outputs", "research-2026-10-05-r7c21aa.md"),
      "# DC fast-charger thermal derating\n\nSynthetic demo report.\n")
    # memory
    now = datetime.datetime.now(datetime.timezone.utc)
    ents = [
        ("decision", "Uptime target is 99% per station per week.", ["pinned"], 9),
        ("requirement", "Reports go out every Monday 09:00 as DOCX and Markdown.", [], 6),
        ("fact", "CP-05 contactor was replaced on 2026-08-14; check cycle count before replacing again.", [], 4),
        ("todo", "Ask the site team for fan current readings on CP-03.", [], 1),
    ]
    entries = []
    for i, (kind, text, tags, days) in enumerate(ents):
        e = {"id": "m%04d" % (i + 1), "kind": kind, "text": text,
             "created": (now - datetime.timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z"),
             "tags": tags}
        if "pinned" in tags:
            e["pinned"] = True
        entries.append(e)
    w(os.path.join(demo, "memory.json"), json.dumps({"version": 1, "project": "demo", "entries": entries},
                                                     ensure_ascii=False, indent=2))
    # research jobs
    t = now.timestamp()
    w(os.path.join(demo, "research", "r7c21aa.json"), json.dumps({
        "question": "How do DC fast chargers derate power at high cabinet temperature?",
        "status": "done", "phase": "done", "depth": "standard", "model": "Qwen3.8-27B",
        "created": t - 2 * 86400, "finished": t - 2 * 86400 + 410, "progress": 1.0,
        "counts": {"sources_read": 7, "claims": 18}, "limits": {"sources": 8},
        "report": {"md": "research-2026-10-05-r7c21aa.md"}}, indent=1))
    w(os.path.join(demo, "research", "r3b90e1.json"), json.dumps({
        "question": "Compare connector lock failure causes across CCS2 chargers",
        "status": "running", "phase": "read", "depth": "standard", "model": "Qwen3.8-27B",
        "created": t - 140, "updated": t - 5, "progress": 0.45, "eta_left_s": 260,
        "counts": {"sources_read": 3}, "limits": {"sources": 8},
        "message": {"th": "กำลังอ่านแหล่งที่ 4 จาก 8", "en": "Reading source 4 of 8"}}, indent=1))
    for p in PROJECTS[1:]:
        os.makedirs(os.path.join(DATA, p["slug"], "attachments"), exist_ok=True)
    w(os.path.join(DATA, "thai-docs", "attachments", "site-inspection-2026-09.pdf"), "", mode="w")


def make_chart():
    """Synthetic bar chart rendered with anaconda's matplotlib (PIL fallback)."""
    out = os.path.join(DATA, "demo", "outputs", "uptime-week39.png")
    code = r'''
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
st = ["CP-01", "CP-02", "CP-03", "CP-04", "CP-05"]
up = [99.7, 99.3, 96.1, 98.4, 91.8]
fig, ax = plt.subplots(figsize=(7, 2.8), dpi=110)
cols = ["#d97757" if u < 99 else "#8a8578" for u in up]
ax.barh(st[::-1], up[::-1], color=cols[::-1])
ax.axvline(99, color="#555", lw=1, ls="--")
ax.set_xlim(85, 100)
ax.set_xlabel("uptime %  (dashed = 99% target)")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(r"__OUT__", metadata={"Software": None})
'''.replace("__OUT__", out)
    try:
        import matplotlib  # noqa: F401
        py = sys.executable
    except ImportError:     # C:\Python313 has no matplotlib; the Anaconda python of the Python tool does
        py = os.environ.get("QWEN_DEMO_PLOT_PYTHON") or os.path.expandvars(r"%USERPROFILE%\anaconda3\python.exe")
    r = subprocess.run([py, "-c", code], capture_output=True, text=True)
    print("chart:", r.returncode, r.stderr[-300:])


# ----------------------------------------------------------------------------------- usage log
def usage_rows():
    rnd = random.Random(20261007)
    now = datetime.datetime.now().astimezone()
    # last 7 days on the RTX 4090 eGPU, earlier days on the laptop RTX 1000 Ada (speeds measured with gpu_bench)
    fast = {BIG: (42.7, 690), FAST: (79.7, 4400), CODER: (91.0, 476), OSS: (68.4, 1336)}
    slow = {BIG: (1.3, 65), FAST: (28.0, 1100), CODER: (9.5, 140), OSS: (11.0, 210)}
    share = {BIG: .55, FAST: .8, CODER: .25, OSS: .12}
    rows = []
    for back in range(30):
        if back in (5, 13, 20):
            continue
        day = (now - datetime.timedelta(days=back)).date()
        speeds = fast if back < 7 else slow
        for p, weight in zip(PROJECTS, (1.0, .7, .45, .3)):
            for m in (BIG, FAST, CODER, OSS):
                if rnd.random() > share[m] * weight:
                    continue
                for _k in range(rnd.randint(1, 4 if back < 7 else 2)):
                    if back == 0:
                        mins = now.hour * 60 + now.minute
                        ts = now - datetime.timedelta(minutes=rnd.randint(0, max(0, mins - 1)))
                    else:
                        ts = datetime.datetime.combine(day, datetime.time(rnd.randint(8, 21), rnd.randint(0, 59)),
                                                       now.tzinfo)
                    gen, ptps = speeds[m]
                    g = round(gen * rnd.uniform(.88, 1.08), 2)
                    prompt = rnd.randint(1800, 9000)
                    comp = rnd.randint(120, 900)
                    rows.append({"ts": ts.isoformat(timespec="seconds"), "project": p["slug"], "model": m,
                                 "prompt_tokens": prompt, "cached_tokens": int(prompt * rnd.uniform(.4, .85)),
                                 "completion_tokens": comp, "prompt_tps": round(ptps * rnd.uniform(.85, 1.1), 1),
                                 "gen_tps": g, "wall_s": round(comp / g + rnd.uniform(.5, 4), 2),
                                 "tools_used": rnd.choice([[], [], ["local_read"], ["local_do"], ["web_search"]]),
                                 "compacted": rnd.random() < .04, "error": False,
                                 "conv": "%012x" % rnd.getrandbits(48)})
    rows.sort(key=lambda r: r["ts"])
    with open(os.path.join(DATA, "usage.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print("usage rows:", len(rows))


# ----------------------------------------------------------------------------------- GPU simulation
SIM = [
    {"name": "NVIDIA RTX 1000 Ada Generation Laptop GPU", "total_mib": 6140, "free_mib": 5083,
     "pci_bus_id": "00000000:01:00.0", "id": "CUDA0"},
    {"name": "NVIDIA GeForce RTX 4090", "total_mib": 24564, "free_mib": 24080,
     "pci_bus_id": "00000000:2E:00.0", "id": "CUDA1"},
]


def make_gpu():
    g = os.path.join(WORK, "gpu")
    os.makedirs(g, exist_ok=True)
    sim = os.path.join(g, "sim.json")
    w(sim, json.dumps(SIM, indent=1))
    r = subprocess.run([r"C:\Python313\python.exe", "-X", "utf8", r"C:\LLM\gpu_profile.py", "--write", "--simulate", sim,
                        "--out-dir", g, "--user-ini", os.path.join(g, "none-user.ini"), "--choice", "none"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("gpu_profile rc", r.returncode)
    print(r.stdout[-1500:])
    print(r.stderr[-800:])


def main():
    os.makedirs(DATA, exist_ok=True)
    w(os.path.join(WORK, "fixtures", "demo-en.json"), json.dumps(fixture(), ensure_ascii=False, indent=1))
    for x, c in zip(PROJECTS, ("2026-09-02T08:10:00+00:00", "2026-09-10T03:22:00+00:00", "2026-09-18T06:40:00+00:00",
                                "2026-09-27T09:05:00+00:00")):
        x["created"] = c
    w(os.path.join(WORK, "projects.json"), json.dumps(PROJECTS, ensure_ascii=False, indent=2))
    w(os.path.join(WORK, "settings.json"), json.dumps({"lang": "en", "theme": "dark", "font": "serif"}))
    for p in PROJECTS:
        os.makedirs(os.path.join(DATA, p["slug"]), exist_ok=True)
    make_files()
    make_chart()
    usage_rows()
    if "--no-gpu" not in sys.argv:
        make_gpu()


if __name__ == "__main__":
    main()
