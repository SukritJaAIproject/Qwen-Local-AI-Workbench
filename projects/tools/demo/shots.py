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

    def type_text(self, text):
        """type into the focused element like a user would (fires the input events React listens to)"""
        self.ws.call("Input.insertText", {"text": text})
        self.ws.drain(0.3)

    def press_enter(self):
        for kind in ("keyDown", "keyUp"):
            self.ws.call("Input.dispatchKeyEvent", {"type": kind, "key": "Enter", "code": "Enter",
                                                    "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        self.ws.drain(0.3)

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


PANEL_URL = "https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench"   # a public page; the project's own

START_PANEL = """(async () => {
  if (!window.qwenBrowserPanel) return 'no panel api';
  window.qwenBrowserPanel.open();
  await new Promise(r => setTimeout(r, 1200));
  const u = document.getElementById('bpUrl'); u.value = %s;
  document.getElementById('bpUrlForm').requestSubmit();
  return 'submitted';
})()"""

PANEL_STATE = """(() => {
  const st = window.qwenBrowserPanel && window.qwenBrowserPanel.state(), img = document.getElementById('bpImg');
  if (!st) return {ok: false, why: 'no state'};
  const tab = (st.tabs || []).find(t => t.active) || (st.tabs || [])[0];
  return {ok: !!(st.running && img && img.naturalWidth > 0 && tab && /github\\.com/.test(tab.url || '') && !tab.loading),
          running: !!st.running, starting: !!st.starting, error: st.error || null,
          url: tab ? tab.url : null, loading: tab ? tab.loading : null,
          img: img ? img.naturalWidth + 'x' + img.naturalHeight : null};
})()"""

STOP_PANEL = """(async () => {
  try { await fetch('/_qwen/browser/stop', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'}); } catch (e) {}
  if (window.qwenBrowserPanel) window.qwenBrowserPanel.close();
  return 'panel stopped';
})()"""

FOCUS_COMPOSER = frame("""(() => {
  const ta = document.querySelector('.chat-screen-form-wrapper form.conversation-chat-form textarea') || document.querySelector('textarea');
  if (!ta) return 'no textarea';
  ta.focus();
  return 'focused';
})()""")

# send what is in the composer the way the WebUI itself does (submit button), then wait for the reply to start
SEND_FIRST = frame("""(async () => {
  const f = document.querySelector('.chat-screen-form-wrapper form.conversation-chat-form');
  const ta = f && f.querySelector('textarea');
  if (!ta) return 'no form';
  const b = f.querySelector('button[type="submit"]');
  if (b) f.requestSubmit(b);
  else ta.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true}));
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 250));
    if (window.qwenQueue && window.qwenQueue.status().busy) return 'busy after ' + (i * 250) + ' ms';
  }
  return 'not busy: ' + JSON.stringify(window.qwenQueue ? window.qwenQueue.status() : null);
})()""")

QUEUE_STATUS = frame("""(() => {
  const q = document.querySelector('.qw-queue');
  return {status: window.qwenQueue ? window.qwenQueue.status() : null,
          panel: q ? q.innerText.replace(/\\s+/g, ' ').slice(0, 200) : null,
          composer: (document.querySelector('.chat-screen-form-wrapper textarea') || {}).value || ''};
})()""")

# fallback when the synthetic Enter is not accepted: put the waiting messages into the queue's own store
# (sessionStorage) and reload; the reply reattaches through the recovery layer and the queue shows the items
SEED_QUEUE = frame("""(() => {
  const key = %s, items = %s;
  let store; try { store = JSON.parse(sessionStorage.getItem('qwen-message-queue-v1') || '{}'); } catch (e) { store = {}; }
  store.items = store.items || {}; store.paused = store.paused || {};
  store.items[key] = items.map((t, i) => ({id: 'demo-' + i, text: t, at: Date.now() + i}));
  sessionStorage.setItem('qwen-message-queue-v1', JSON.stringify(store));
  return 'seeded ' + items.length;
})()""")

CLEAR_QUEUE = frame("""(() => {
  if (window.qwenQueue) window.qwenQueue.clear();
  sessionStorage.removeItem('qwen-message-queue-v1');
  const stop = [...document.querySelectorAll('.chat-screen-form-wrapper button')].find(x => /stop|หยุด/i.test((x.getAttribute('aria-label') || '') + ' ' + (x.textContent || '')));
  if (stop) stop.click();
  return stop ? 'stopped' : 'no stop button';
})()""")

QUEUE_TEXTS = [
    "Add a week-over-week column and highlight the stations that got worse.",
    "Then draft the Monday e-mail to the maintenance team.",
    "Also export the table as XLSX.",
]


def browser_panel_en(b):
    """the built-in browser panel beside the chat, showing a public page through the egress proxy"""
    prefs("en", "dark")
    b.metrics(1440, 900)
    b.seed(DEMO)
    b.go(DEMO + "/?lang=en", 5)
    print(b.ev(OPEN_CHAT % json.dumps("demo-c1"), 2))
    try:
        print(b.ev(START_PANEL % json.dumps(PANEL_URL), 1))
        st = None
        for _ in range(100):                      # up to ~75 s: Edge start + page load + first screencast frame
            st = b.ev(PANEL_STATE, 0.25)
            if isinstance(st, dict) and (st.get("ok") or st.get("error")):
                break
            time.sleep(0.5)
        print("panel:", st)
        time.sleep(3.0)                           # let the page settle and the screencast catch up
        # scroll the chat to the report table after the panel has taken its width (the chat re-lays out)
        print(b.ev(SCROLL_TO_TEXT.replace("OFFSET", "40") % (json.dumps("Using attachments/charger-faults"), json.dumps("start")), 1))
        b.snap("12-browser-panel-en-dark")
    finally:
        print(b.ev(STOP_PANEL, 1))


def message_queue_en(b):
    """a reply streaming (the demo upstream answers slowly) with two messages waiting in the queue"""
    prefs("en", "light")
    b.metrics(1440, 900, scheme="light")
    b.seed(DEMO)
    b.go(DEMO + "/?lang=en", 5)
    b.ws.call("Emulation.setFocusEmulationEnabled", {"enabled": True})
    print(b.ev(OPEN_CHAT % json.dumps("demo-c1"), 2))
    print(b.ev(FOCUS_COMPOSER, 0.3))
    b.type_text(QUEUE_TEXTS[0])
    print(b.ev(SEND_FIRST, 0.5))
    for text in QUEUE_TEXTS[1:]:
        print(b.ev(FOCUS_COMPOSER, 0.3))
        b.type_text(text)
        b.press_enter()
        time.sleep(0.8)
    st = b.ev(QUEUE_STATUS, 0.3)
    print("after Enter:", st)
    size = ((st or {}).get("status") or {}).get("size", 0) if isinstance(st, dict) else 0
    if size < 2:
        # Enter was not accepted by the page: use the queue's own store instead and reload the chat
        print(b.ev(frame("(() => { const ta = document.querySelector('.chat-screen-form-wrapper textarea'); if (ta) { ta.value = ''; ta.dispatchEvent(new Event('input', {bubbles: true})); } return 'cleared'; })()"), 0.3))
        print(b.ev(SEED_QUEUE % (json.dumps("demo|demo-c1"), json.dumps(QUEUE_TEXTS[1:])), 0.3))
        b.go(DEMO + "/?lang=en", 5)
        print(b.ev(OPEN_CHAT % json.dumps("demo-c1"), 3))
        print("after reload:", b.ev(QUEUE_STATUS, 0.3))
    print(b.ev(SCROLL_FRAME % "1e9", 1))
    b.snap("13-message-queue-en-light")
    print(b.ev(CLEAR_QUEUE, 1))


ALL = [chat_en_dark, start_en_light, artifact_en_light, project_panel_en, usage_en, doctor_en, gpu_en,
       account_menu_en, chat_th_dark, mobile_th, manage_th, browser_panel_en, message_queue_en]


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
