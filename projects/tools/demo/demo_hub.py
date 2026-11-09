# -*- coding: utf-8 -*-
"""A throw-away copy of the hub for screenshots, on spare ports, with synthetic data only.

  * imports C:\\LLM\\projects\\hub.py as a module (the real hub on 8100 is not touched)
  * DATA_ROOT / projects.json / settings.json -> this work folder (make_demo_data.py)
  * GPU: simulated RTX 1000 Ada + RTX 4090 (QWEN_GPU_SIMULATE), profile generated from it, apply = dry run
  * doctor: hub_doctor's real report builder fed with synthetic probe results (no live probes, no real logs)
  * upstream: a fake llama-server -- GET is relayed to the live router only for the WebUI files / model list
    (requests naming a model are refused, so nothing is ever loaded); chat requests get a canned reply
  * MCP servers are hidden from the page (no token is put into the page)

Usage: python demo_hub.py [--minutes 40]      API on 8171, project ports from projects.json (8172-8174, 8176-8177)
"""
import datetime
import http.client
import importlib.util
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

WORK = Path(__file__).resolve().parent
# QWEN_DEMO_HUB: take the hub from a clone (e.g. a branch that is not installed yet) instead of the live install
HUB = os.environ.get("QWEN_DEMO_HUB") or r"C:\LLM\projects\hub.py"
if os.environ.get("QWEN_DEMO_HUB"):
    # a clone has no secrets of its own: read the live install's local-services token in place (no copy), the one
    # the router on 8099 accepts — otherwise the clone's hub makes a new token and the WebUI gets "access denied"
    os.environ.setdefault("LLM_LOCAL_TOKEN_FILE", r"C:\LLM\secrets\local-services.token")
API_PORT = 8171
ROUTER_PORT = 8099
SERVE_SLUGS = ("demo", "ocpp-research", "thai-docs", "ja-docs", "zh-docs")
FAST = "Qwen3-4B-Instruct-2507-Q4_K_M"
MODELS = [FAST, "Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL", "Qwen3.8-27B-UD-Q4_K_M", "gpt-oss-20b-MXFP4"]

# Synthetic reply for the message-queue screenshot (continues the "Weekly charger uptime report" demo chat).
DEMO_REPLY = """Here is the table with a week-over-week column, from `attachments/charger-faults-week39.csv` and last week's report.

| Station | Uptime W38 | Uptime W39 | Change |
|---|---:|---:|---:|
| CP-01 | 99.5% | 99.7% | +0.2 |
| CP-02 | 99.4% | 99.3% | -0.1 |
| CP-03 | 98.0% | 96.1% | **-1.9** |
| CP-04 | 98.6% | 98.4% | -0.2 |
| CP-05 | 95.9% | 91.8% | **-4.1** |

Two stations got worse. **CP-05** lost 4.1 points to the stuck contactor (14 faults), and **CP-03** lost 1.9 points
to over-temperature trips in the afternoon. CP-01 improved slightly and the other two are within normal variation.

I will keep this table in `outputs/weekly-report-w39.md` and continue with the next request."""

os.environ["QWEN_GPU_SIMULATE"] = str(WORK / "gpu" / "sim.json")
os.environ["QWEN_GPU_PROFILE"] = str(WORK / "gpu" / "gpu-profile.json")
os.environ["QWEN_GPU_CHOICE"] = str(WORK / "gpu" / "gpu-choice.json")
os.environ["QWEN_GPU_USER_INI"] = str(WORK / "gpu" / "none-user.ini")
os.environ["QWEN_GPU_DRYRUN"] = "1"
os.environ["QWEN_GPU_DRYRUN_OUT"] = str(WORK / "gpu" / "dryrun")


class Up(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    loaded = set()

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _relay(self, method):
        q = parse_qs(urlparse(self.path).query)
        want = (q.get("model") or [""])[0]
        if want and want not in self.loaded:
            self._send(404, {"error": {"code": 404, "message": "demo: model probes are not relayed"}})
            return
        h = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "connection")}
        c = http.client.HTTPConnection("127.0.0.1", ROUTER_PORT, timeout=60)
        try:
            c.request(method, self.path, headers=h)
            r = c.getresponse()
            data = r.read()
        except OSError:
            self._send(502, {"error": "router"})
            return
        finally:
            c.close()
        self.send_response(r.status)
        for k, v in r.getheaders():
            if k.lower() not in ("content-length", "transfer-encoding", "connection"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(data)

    def do_GET(self):
        self._relay("GET")

    def do_HEAD(self):
        self._relay("HEAD")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if urlparse(self.path).path.endswith("/chat/completions"):
            self._demo_reply(body)
            return
        self._send(403, {"error": "demo: no generation"})

    def _demo_reply(self, body):
        """A canned reply, streamed slowly (about 25 s) so the chat is visibly "working" for the
        message-queue screenshot. No model is involved; the text is synthetic like the rest of the demo."""
        try:
            doc = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            doc = {}
        model = (doc.get("model") if isinstance(doc, dict) else None) or MODELS[2]
        base = {"id": "demo-reply", "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
        if not (isinstance(doc, dict) and doc.get("stream")):
            self._send(200, dict(base, object="chat.completion",
                                 choices=[{"index": 0, "finish_reason": "stop",
                                           "message": {"role": "assistant", "content": DEMO_REPLY}}],
                                 usage={"prompt_tokens": 1842, "completion_tokens": 190, "total_tokens": 2032}))
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def chunk(delta, finish=None, extra=None):
            d = dict(base, choices=[{"index": 0, "delta": delta, "finish_reason": finish}])
            if extra:
                d.update(extra)
            self.wfile.write(("data: " + json.dumps(d, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.flush()

        pieces = [p for p in DEMO_REPLY.replace("\n", " \n").split(" ") if p != ""]
        try:
            chunk({"role": "assistant", "content": ""})
            for i, p in enumerate(pieces):
                chunk({"content": p + ("" if p.endswith("\n") else " ")})
                time.sleep(0.22)
            chunk({}, "stop", {"timings": {"prompt_n": 1842, "prompt_ms": 2590.0, "predicted_n": len(pieces),
                                            "predicted_ms": 220.0 * len(pieces)}})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass            # the page stopped the reply or navigated away
        finally:
            self.close_connection = True


def serve(addr, handler):
    srv = ThreadingHTTPServer(addr, handler)
    srv.daemon_threads = True
    srv.handle_error = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def load_hub():
    sys.path.insert(0, os.path.dirname(HUB))
    spec = importlib.util.spec_from_file_location("hub_demo_shots", HUB)
    hub = importlib.util.module_from_spec(spec)
    with mock.patch.object(sys, "argv", ["hub.py", str(API_PORT), str(ROUTER_PORT)]):
        spec.loader.exec_module(hub)
    return hub


def doctor_raw(hub):
    mod = hub._doctor
    tmp = WORK / "doctor"
    tmp.mkdir(exist_ok=True)
    (tmp / "local-services.token").write_text("0" * 64, encoding="utf-8")       # dummy, not a real token
    (tmp / "tests-last.json").write_text(json.dumps({
        "at": (datetime.datetime.now().astimezone() - datetime.timedelta(hours=3)).isoformat(timespec="seconds"),
        "ran": 1860, "ok": True, "failures": 0, "errors": 0, "skipped": 54, "failed": []}), encoding="utf-8")
    cfg = {"token_file": str(tmp / "local-services.token"), "brave_key_file": str(tmp / "brave-search.key"),
           "gateway_key_file": str(tmp / "gateway_key.txt"), "tests_file": str(tmp / "tests-last.json"),
           "llama_dir_build": "b10984", "hub_version": "2026-11-07 23:29"}
    row = mod._row
    projects = json.loads((WORK / "projects.json").read_text(encoding="utf-8"))
    res = {
        "router": row("router", "ตัวจัดการโมเดล (llama-server)", "Model router (llama-server)", 8099, "ok", 11,
                      models=[{"id": m, "state": "loaded" if m in (FAST, MODELS[2]) else "unloaded"} for m in MODELS],
                      loaded=[{"id": FAST, "state": "loaded"}, {"id": MODELS[2], "state": "loaded"}],
                      build="b10984", max_instances=2),
        "mcp_local": row("mcp_local", "เครื่องมือในเครื่อง (MCP)", "Local tools (MCP)", 8792, "ok", 24),
        "mcp_web": row("mcp_web", "ค้นเว็บ (MCP)", "Web search (MCP)", 8791, "ok", 17, provider="ddgs"),
        "embed": row("embed", "ค้นตามความหมาย (embedding)", "Semantic search (embedding)", 8093, "ok", 6),
        "stt": row("stt", "พูดแทนพิมพ์ (STT)", "Speech-to-text (STT)", 8795, "ok", 14, detail="ready", device="gpu"),
        "scheduler": row("scheduler", "ตัวตั้งเวลา (scheduler)", "Scheduler", None, "ok", None, heartbeat_age_s=420,
                         heartbeat_status="ok", heartbeat_message="ok 4/4", runner_alive=True),
        "gateway": row("gateway", "Remote Prompt Gateway", "Remote prompt gateway", 8780, "ok", 5, upstream_ok=True),
        "hub": row("hub", "ฮับ + พอร์ตโปรเจกต์", "Hub + project ports", 8100, "ok", 0, keep_awake=0,
                   ports=[{"slug": p["slug"], "name": p["name"], "port": 8101 + i, "state": "ok", "latency_ms": 1,
                           "in_process": True} for i, p in enumerate(projects)]),
        "gpu": ([{"name": "NVIDIA GeForce RTX 4090", "mem_total_mib": 24564, "mem_used_mib": 19870,
                  "mem_free_mib": 4694, "driver": "596.71", "temp_c": 51, "util_pct": 12},
                 {"name": "NVIDIA RTX 1000 Ada Generation Laptop GPU", "mem_total_mib": 6141, "mem_used_mib": 3480,
                  "mem_free_mib": 2661, "driver": "596.71", "temp_c": 47, "util_pct": 3}], None),
        "logs": ([], 0),
        "models": [{"name": m + ".gguf", "size_gb": sz, "dir": r"C:\LLM\models"} for m, sz in
                   zip(MODELS, (2.33, 16.47, 16.16, 11.27))],
        "memory": {"ram_total_gb": 63.6, "ram_free_gb": 21.4, "ram_load_pct": 66, "commit_limit_gb": 89.1,
                   "commit_free_gb": 31.3},
        "disks": [{"drive": "C:", "present": True, "free_gb": 118.6, "total_gb": 474.1},
                  {"drive": "D:", "present": True, "free_gb": 763.0, "total_gb": 931.5}],
        # same shape as hub_doctor.docker_status() when the optional Python sandbox is left off
        "docker": {"usable": False, "off": True,
                   "reason_th": "ปิด Python sandbox ไว้ · โค้ด Python รันบนเครื่องหลังผู้ใช้กดอนุญาต",
                   "reason_en": "the Python sandbox is off · Python code runs on this PC after you approve it"},
    }
    rep = mod.Doctor(cfg)._build(res, [])
    rep["took_ms"], rep["cached"] = 214, False
    return rep


def main():
    minutes = 40
    if "--minutes" in sys.argv:
        minutes = float(sys.argv[sys.argv.index("--minutes") + 1])
    hub = load_hub()
    projects = json.loads((WORK / "projects.json").read_text(encoding="utf-8"))
    rep = doctor_raw(hub)
    patches = [
        mock.patch.object(hub, "DATA_ROOT", WORK / "data"),
        mock.patch.object(hub, "STORE", WORK / "projects.json"),
        mock.patch.object(hub, "SETTINGS", WORK / "settings.json"),
        mock.patch.object(hub, "mcp_servers", lambda project, with_auth=True: []),
        mock.patch.object(hub, "doctor_report", lambda refresh=False: json.loads(json.dumps(rep))),
    ]
    if hasattr(hub, "stt_probe"):
        patches.append(mock.patch.object(hub, "stt_probe", lambda tok=None: {"state": "ok", "port": 8795, "device": "gpu"}))
    if hasattr(hub, "_mcp_fast_call"):
        patches.append(mock.patch.object(hub, "_mcp_fast_call", lambda *a, **k: ("down", "")))
    for p in patches:
        p.start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", ROUTER_PORT, timeout=10)
        c.request("GET", "/models", headers=hub.router_auth_headers())
        d = json.loads(c.getresponse().read().decode("utf-8"))
        c.close()
        Up.loaded = {m.get("id") for m in d.get("data") or [] if (m.get("status") or {}).get("value") == "loaded"}
    except (OSError, ValueError):
        Up.loaded = set()
    up = serve(("127.0.0.1", 0), Up)
    p = mock.patch.object(hub, "UPSTREAM_PORT", up.server_address[1])
    p.start()
    servers = [up]
    for pr in projects:
        if pr["slug"] in SERVE_SLUGS:
            servers.append(serve(("127.0.0.1", pr["port"]), hub.make_proxy_handler(pr["slug"], hub.load_projects)))
    class DemoApi(hub.HubHandler):
        """same handler; only the displayed router port is the real one (8099), not the fake upstream's"""

        def _json(self, code, obj, *a, **k):
            if isinstance(obj, dict) and "upstream_port" in obj:
                obj = dict(obj, upstream_port=ROUTER_PORT)
            return super()._json(code, obj, *a, **k)

    servers.append(serve(("127.0.0.1", API_PORT), DemoApi))
    print("demo hub ready: api %d, projects %s" % (API_PORT, ", ".join("%s:%d" % (x["slug"], x["port"])
                                                                         for x in projects if x["slug"] in SERVE_SLUGS)),
          flush=True)
    end = time.time() + minutes * 60
    try:
        while time.time() < end and not (WORK / "STOP").exists():
            time.sleep(1)
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()
        print("demo hub stopped", flush=True)


if __name__ == "__main__":
    main()
