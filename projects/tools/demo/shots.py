# -*- coding: utf-8 -*-
"""Drive one headless Edge (temp profile in ./tmp) through the demo hub and save README screenshots.

Usage: python shots.py [name ...]     (no names = all; names = the shot functions below)
Raw PNGs -> ./raw/<name>.png ; look at them, then run finalize_shots.py (strips metadata into docs/screenshots).
Needs: demo_hub.py running, Microsoft Edge, and a running llama-server router on 8099 (only for the WebUI files).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

WORK = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(WORK, "tmp")
os.makedirs(TMP, exist_ok=True)
tempfile.tempdir = TMP
sys.path.insert(0, r"C:\LLM\projects\tools")
import shot as S  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = os.path.join(WORK, "raw")
os.makedirs(RAW, exist_ok=True)
FIX = json.load(open(os.path.join(WORK, "fixtures", "demo-en.json"), encoding="utf-8"))
API = "http://127.0.0.1:8171"
DEMO = "http://127.0.0.1:8172"
OCPP = "http://127.0.0.1:8173"
THAI = "http://127.0.0.1:8174"


def prefs(lang, theme):
    with open(os.path.join(WORK, "settings.json"), "w", encoding="utf-8") as fh:
        json.dump({"lang": lang, "theme": theme, "font": "serif"}, fh)


def frame(js):
    """wrap JS to run inside the WebUI iframe (same origin)"""
    return ("(async()=>{const w=document.getElementById('frame').contentWindow;"
            "return await w.eval(%s)})()" % json.dumps(js))


OPEN_CHAT = """(async () => {
  const f = document.getElementById('frame');
  for (let i = 0; i < 80 && !(f.contentWindow && f.contentWindow.qwenEnhance); i++) await new Promise(r => setTimeout(r, 150));
  f.contentWindow.qwenEnhance.openChat(%s);
  await new Promise(r => setTimeout(r, 2500));
  return f.contentWindow.location.hash;
})()"""

SCROLL_FRAME = """(async () => {
  const d = document.getElementById('frame').contentWindow.document;
  const sc = [...d.querySelectorAll('*')].filter(e => e.scrollHeight > e.clientHeight + 40 &&
              /(auto|scroll)/.test(getComputedStyle(e).overflowY)).sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
  if (!sc) return 'no scroller';
  sc.scrollTop = %s;
  await new Promise(r => setTimeout(r, 600));
  return [sc.className.slice(0, 60), sc.scrollTop, sc.scrollHeight];
})()"""

SCROLL_TO_TEXT = """(async () => {
  const d = document.getElementById('frame').contentWindow.document;
  const want = %s;
  const el = [...d.querySelectorAll('h1,h2,h3,p,li,td,code,img,pre')].find(e => (e.textContent || e.alt || '').includes(want) || (e.alt || '').includes(want));
  if (!el) return 'not found';
  el.scrollIntoView({block: %s});
  await new Promise(r => setTimeout(r, 300));
  let sc = el.parentElement; while (sc && !(sc.scrollHeight > sc.clientHeight + 40 && /(auto|scroll)/.test(getComputedStyle(sc).overflowY))) sc = sc.parentElement;
  if (!sc) sc = d.scrollingElement || d.documentElement;
  sc.scrollTop -= OFFSET;
  await new Promise(r => setTimeout(r, 700));
  return 'ok';
})()"""


class Browser:
    def __init__(self, w=1440, h=900):
        edge = next((p for p in S.EDGE_CANDIDATES if os.path.isfile(p)), None)
        self.port = S.free_port()
        self.profile = tempfile.mkdtemp(prefix="qwen-shot-")
        self.proc = subprocess.Popen([
            edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions", "--mute-audio",
            "--remote-debugging-port=%d" % self.port, "--user-data-dir=%s" % self.profile,
            "--window-size=%d,%d" % (w, h), "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(120):
            try:
                tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % self.port, timeout=2).read())
                page = next((t for t in tabs if t.get("type") == "page"), None)
                if page:
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except OSError:
                pass
            time.sleep(0.2)
        self.ws = S.WS(ws_url)
        self.ws.call("Page.enable")
        self.ws.call("Runtime.enable")
        self.seeded = set()
        self.metrics(w, h)

    def metrics(self, w, h, mobile=False, scheme="dark"):
        self.ws.call("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1,
                                                            "mobile": mobile})
        self.ws.call("Emulation.setTouchEmulationEnabled", {"enabled": bool(mobile), "maxTouchPoints": 5})
        self.ws.call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": scheme}]})

    def ev(self, js, settle=0.5):
        v = S.evaluate(self.ws, js)
        self.ws.drain(settle)
        return v

    def go(self, url, settle=4.0):
        S.navigate(self.ws, url, settle=settle)

    def seed(self, origin):
        if origin in self.seeded:
            return
        self.go(origin + "/?ui=1", settle=3.0)
        n = S.evaluate(self.ws, S.SEED_JS % json.dumps(FIX, ensure_ascii=False))
        print("seeded", origin, n)
        self.seeded.add(origin)

    def errors(self):
        out = []
        for e in self.ws.events:
            if e["method"] == "Runtime.exceptionThrown":
                d = e["params"]["exceptionDetails"]
                out.append((d.get("exception") or {}).get("description") or d.get("text"))
        self.ws.events.clear()
        return out

    def snap(self, name):
        shot = self.ws.call("Page.captureScreenshot", {"format": "png"})
        import base64
        p = os.path.join(RAW, name + ".png")
        with open(p, "wb") as fh:
            fh.write(base64.b64decode(shot["data"]))
        errs = self.errors()
        print("saved", p, ("JS errors: %s" % [str(x).splitlines()[0][:160] for x in errs]) if errs else "")

    def close(self):
        S.close_edge(self.proc, self.profile)


# ------------------------------------------------------------------------------------------- shots
def chat_en_dark(b):
    prefs("en", "dark")
    b.metrics(1440, 900)
    b.seed(DEMO)
    b.go(DEMO + "/?lang=en", 5)
    print(b.ev(OPEN_CHAT % json.dumps("demo-c1"), 2))
    print(b.ev(SCROLL_TO_TEXT.replace("OFFSET", "40") % (json.dumps("Using attachments/charger-faults"), json.dumps("start")), 1))
    b.snap("01-chat-en-dark")


def start_en_light(b):
    prefs("en", "light")
    b.metrics(1440, 900, scheme="light")
    b.seed(DEMO)
    b.go(DEMO + "/?lang=en", 6)
    b.snap("02-start-en-light")


def artifact_en_light(b):
    prefs("en", "light")
    b.metrics(1440, 900, scheme="light")
    b.seed(DEMO)
    b.go(DEMO + "/?lang=en", 5)
    print(b.ev(OPEN_CHAT % json.dumps("demo-c1"), 2))
    print(b.ev(SCROLL_TO_TEXT.replace("OFFSET", "0") % (json.dumps("Here is a self-contained page"), json.dumps("start")), 1))
    print(b.ev(frame("""(async () => {
      const btn = [...document.querySelectorAll('.qw-art-btn')].pop();
      if (!btn) return 'no art button';
      btn.click(); await new Promise(r => setTimeout(r, 1800)); return 'clicked';
    })()"""), 2))
    b.snap("03-artifact-panel-en-light")


def project_panel_en(b):
    prefs("en", "dark")
    b.metrics(1440, 900)
    b.seed(DEMO)
    b.go(DEMO + "/?lang=en", 5)
    print(b.ev(OPEN_CHAT % json.dumps("demo-c1"), 2))
    print(b.ev("(async()=>{qwenShellApi.openProjectPanel(); await new Promise(r=>setTimeout(r,2500)); return 1})()", 1))
    b.snap("04-project-panel-en-dark")
    print(b.ev("""(async()=>{const h=document.getElementById('ppKnowH')||document.getElementById('ppFiles');
      if(!h) return 'no files section'; h.scrollIntoView({block:'start'});
      /* the demo keeps its data in a temp folder; show the default location a real install uses */
      const dt=document.getElementById('ppDirTxt'); if(dt) dt.textContent='C:\\\\LLM\\\\projects\\\\data\\\\demo\\\\attachments';
      await new Promise(r=>setTimeout(r,900));
      return 'ok'})()""", 1))
    b.snap("04b-project-files-en-dark")


def usage_en(b):
    prefs("en", "light")
    b.metrics(1440, 900, scheme="light")
    b.go(API + "/?manage=1&theme=light&lang=en#usage", 6)
    b.snap("05-usage-en-light")
    print(b.ev("""(async()=>{const btn=[...document.querySelectorAll('button')].find(x=>/^\\s*30 days\\s*$/.test(x.textContent));
      if(!btn) return 'no 30d'; btn.click(); await new Promise(r=>setTimeout(r,2500)); return 'ok'})()""", 1))
    b.snap("05a-usage-30d-en-light")
    print(b.ev("""(async()=>{const h=[...document.querySelectorAll('*')].find(x=>x.childElementCount<=2&&/^Reply speed/.test(x.textContent||''));
      if(!h) return 'no speed'; h.scrollIntoView({block:'start'}); window.scrollBy(0,-24); await new Promise(r=>setTimeout(r,900));
      return 'ok'})()""", 1))
    b.snap("05b-usage-speed-en-light")


def doctor_en(b):
    prefs("en", "dark")
    b.metrics(1440, 900)
    b.go(API + "/?manage=1&theme=dark&lang=en#doctor", 6)
    b.snap("06-doctor-en-dark")


def gpu_en(b):
    prefs("en", "dark")
    b.metrics(1440, 900)
    b.seed(DEMO)
    b.go(DEMO + "/?lang=en", 5)
    print(b.ev("(async()=>{qwenShellApi.openGpu(); await new Promise(r=>setTimeout(r,6000)); return 1})()", 1))
    b.snap("07-gpu-picker-en-dark")


def account_menu_en(b):
    prefs("en", "light")
    b.metrics(1440, 900, scheme="light")
    b.seed(DEMO)
    b.go(DEMO + "/?lang=en", 6)
    print(b.ev("(async()=>{document.getElementById('acctBtn').click(); await new Promise(r=>setTimeout(r,1500)); return 1})()", 1))
    b.snap("08-account-menu-en-light")


def chat_th_dark(b):
    prefs("th", "dark")
    b.metrics(1440, 900)
    b.seed(THAI)
    b.go(THAI + "/?lang=th", 5)
    print(b.ev(OPEN_CHAT % json.dumps("demo-c7"), 2))
    b.snap("09-chat-th-dark")


def mobile_th(b):
    prefs("th", "light")
    b.metrics(390, 844, mobile=True, scheme="light")
    b.seed(THAI)
    b.go(THAI + "/?lang=th", 6)
    b.snap("10-start-th-mobile")
    b.metrics(1440, 900)


def manage_th(b):
    prefs("th", "light")
    b.metrics(1440, 900, scheme="light")
    b.go(API + "/?manage=1&theme=light&lang=th", 5)
    b.snap("11-manage-projects-th-light")


ALL = [chat_en_dark, start_en_light, artifact_en_light, project_panel_en, usage_en, doctor_en, gpu_en,
       account_menu_en, chat_th_dark, mobile_th, manage_th]


def main():
    want = set(sys.argv[1:])
    b = Browser()
    try:
        for fn in ALL:
            if want and fn.__name__ not in want:
                continue
            print("==", fn.__name__)
            try:
                fn(b)
            except Exception as exc:  # noqa: BLE001
                print("FAILED", fn.__name__, type(exc).__name__, exc)
    finally:
        b.close()
        prefs("en", "dark")


if __name__ == "__main__":
    main()
