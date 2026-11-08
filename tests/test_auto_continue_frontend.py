"""Exercise the shipped Auto Continue code, native card structure, and timer races."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_bypass_permissions_frontend import function

ENH = Path(os.environ.get("QWEN_ENH_FILE", r"C:\LLM\projects\static\webui-enhance.js"))
NODE = shutil.which("node")

ENV = r"""
const assert = require('node:assert/strict');
var store = {}, listeners = {}, cards = [], jobs = new Map(), nextJob = 0;
var sh = {project:{slug:'demo-a'}}, routeState = {name:'chat',id:'c1'}, currentPlan = false, form = null;
var uiLang = 'en';
function lang(){return uiLang;}
var PROMPT_SEL = '.chat-messages div.rounded-lg.border.bg-card.p-3';
var TH = {'Agentic turn limit reached. Continue?':'ถึงจำนวนรอบเอเจนต์สูงสุดแล้ว ทำต่อไหม?',
  'Continue':'ทำต่อ','Stop':'หยุด','Stop generation':'หยุดสร้างคำตอบ'};
function hasOwn(o,k){return Object.prototype.hasOwnProperty.call(o,k);}
function shell(){return sh;}
function lsGet(k){return store[k] == null ? null : store[k];}
function lsSet(k,v){store[k]=v;}
function route(){return routeState;}
function planCurrent(){return currentPlan;}
function enText(n){return n ? n.textContent || '' : '';}
function schedule(){}
function composerForm(){return form;}
function composerToolbar(){return null;}
function detach(){}
function setTimeout(fn){const id=++nextJob;jobs.set(id,fn);return id;}
function clearTimeout(id){jobs.delete(id);}
function flush(){const batch=[...jobs];jobs.clear();for(const [id,fn] of batch)fn();}
var window={addEventListener:(t,f)=>{(listeners[t]||(listeners[t]=[])).push(f);}};
var document={querySelectorAll:()=>cards,querySelector:()=>null};
function enAttr(n,k){return n.getAttribute(k)||'';}
function button(text){return {textContent:text,disabled:false,clicks:0,attrs:{},card:null,
  classList:{contains:()=>false},getAttribute(k){return this.attrs[k] || null;},
  closest(s){return s==='button'?this:s===PROMPT_SEL?this.card:null;},
  click(){this.clicks++;if(this.onClick)this.onClick();}};}
function card(opts={}){
  const next=button(opts.next || 'Continue'), stop=button(opts.stop || 'Stop');
  const head={textContent:opts.head || 'Agentic turn limit reached. Continue?'};
  const acts={querySelectorAll:()=>opts.buttons || [next,stop],
    classList:{contains:x=>!opts.badActions&&['flex','items-center'].includes(x)}};
  const c={isConnected:true,children:[head,acts],next,stop,
    matches(){return opts.native!==false;},
    closest(s){return s==='.agentic-content'?opts.native!==false?{}:null:opts.blocked?{}:null;}};
  next.card=stop.card=c;if(opts.extra)c.children.splice(1,0,{});return c;
}
function stopEvent(b,type='pointerdown',key){return {isTrusted:true,target:b,type,key};}
"""


@unittest.skipUnless(NODE, "Node is required")
class AutoContinueFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = ENH.read_text(encoding="utf-8")
        start = cls.src.index("  /* ---- Auto Continue (")
        cls.block = cls.src[start:cls.src.index("  /* ---- Bypass permissions (", start)]
        cls.helpers = "\n".join(function(cls.src, n) for n in ("bypassIdentity", "bypassExact", "isStreaming", "L", "A"))
        start_dict = cls.src.index("  var TH_B2B = {")
        cls.helpers += "\n" + cls.src[start_dict:cls.src.index("  // พจนานุกรมแยกจาก TH", start_dict)]

    def run_js(self, case):
        code = ENV + self.helpers + self.block + "\n" + case + "\nconsole.log(JSON.stringify({ok:true}));"
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as f:
            f.write(code)
            name = f.name
        try:
            p = subprocess.run([NODE, name], capture_output=True, text=True, encoding="utf-8", timeout=20)
        finally:
            os.remove(name)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), {"ok": True})

    def test_default_on_and_project_preference(self):
        self.run_js(r"""
assert.equal(autoContinueState().active,true);
setAutoContinue(false);assert.equal(autoContinueState().active,false);
assert.deepEqual(JSON.parse(store[AUTO_CONTINUE_KEY]),{project:'demo-a',on:false});
autoContinueProject='';assert.equal(autoContinueState().on,false);
sh.project.slug='demo-b';assert.equal(autoContinueState().active,true);
routeState={name:'start',id:null};assert.equal(autoContinueState().active,false);
sh=null;assert.equal(autoContinueState().ready,false);assert.equal(setAutoContinue(true),false);
""")

    def test_auto_continue_tooltip_does_not_mark_chat_as_streaming(self):
        self.run_js(r"""
const chip=button('Auto Continue: ON');chip.attrs.title=AUTO_CONTINUE_TIP;
chip.classList.contains=x=>x==='qw-auto-continue';chip.querySelector=()=>null;
form={querySelectorAll:()=>[chip]};assert.equal(isStreaming(),false);
const stop=button('Stop');stop.querySelector=()=>({textContent:'Stop'});
form.querySelectorAll=()=>[chip,stop];assert.equal(isStreaming(),true);
""")

    def test_auto_continue_labels_use_chip_translation_dictionary(self):
        self.run_js(r"""
assert.equal(A('Auto Continue: ON'),'Auto Continue: ON');
uiLang='th';assert.equal(A('Auto Continue: ON'),'ทำต่ออัตโนมัติ: เปิด');
assert.equal(A('Auto Continue: OFF'),'ทำต่ออัตโนมัติ: ปิด');
assert.equal(A('Auto Continue: PAUSED'),'ทำต่ออัตโนมัติ: พัก');
assert.equal(A(AUTO_CONTINUE_TIP).includes('ทำต่ออัตโนมัติ'),true);
""")

    def test_native_continue_once_and_subsequent_limit(self):
        self.run_js(r"""
const c=card();cards=[c];autoContinueScan();autoContinueScan();assert.equal(jobs.size,1);
assert.equal(c.next.clicks,0);assert.equal(autoContinueHandling(c),true);
flush();assert.equal(c.next.clicks,1);assert.equal(c.stop.clicks,0);
autoContinueScan();flush();assert.equal(c.next.clicks,1);
const c2=card();cards=[c2];autoContinueScan();flush();assert.equal(c2.next.clicks,1);
""")

    def test_wait_for_project_metadata_before_binding_prompt(self):
        self.run_js(r"""
const c=card();cards=[c];sh=null;autoContinueScan();flush();assert.equal(c.next.clicks,0);
sh={project:{slug:'demo-a'}};autoContinueScan();flush();assert.equal(c.next.clicks,1);
""")

    def test_ignore_permissions_and_lookalikes_and_support_thai(self):
        self.run_js(r"""
const bad=[card({head:'Allow use of read_file?',next:'Allow once',stop:'Deny'}),
  card({head:'Quoted: Agentic turn limit reached. Continue?'}),card({native:false}),
  card({blocked:true}),card({extra:true}),card({badActions:true}),
  card({next:'Continue generation'}),card({buttons:[button('Continue'),button('Continue'),button('Stop')]})];
cards=bad;autoContinueScan();flush();for(const c of bad)assert.equal(c.next.clicks,0);
const th=card({head:TH['Agentic turn limit reached. Continue?'],next:TH.Continue,stop:TH.Stop});
cards=[th];autoContinueScan();flush();assert.equal(th.next.clicks,1);
""")

    def test_off_and_cross_tab_storage_cancel_pending_timer(self):
        self.run_js(r"""
const c=card();cards=[c];autoContinueScan();setAutoContinue(false);flush();assert.equal(c.next.clicks,0);
setAutoContinue(true);assert.equal(jobs.size,1);
store[AUTO_CONTINUE_KEY]=JSON.stringify({project:'demo-a',on:false});
for(const fn of listeners.storage)fn({key:AUTO_CONTINUE_KEY});flush();assert.equal(c.next.clicks,0);
""")

    def test_route_and_project_races_do_not_resume_old_chat(self):
        self.run_js(r"""
const old=card();cards=[old];autoContinueScan();routeState.id='c2';flush();assert.equal(old.next.clicks,0);
autoContinueScan();flush();assert.equal(old.next.clicks,0);
const fresh=card();cards=[fresh];autoContinueScan();
for(const fn of listeners.hashchange)fn({});flush();assert.equal(fresh.next.clicks,0);
autoContinueScan();sh.project.slug='other';flush();assert.equal(fresh.next.clicks,0);
""")

    def test_stop_cancels_run_until_new_send(self):
        self.run_js(r"""
const c=card();cards=[c];autoContinueScan();autoContinueNoteStop(stopEvent(c.stop));
flush();autoContinueScan();flush();assert.equal(c.next.clicks,0);assert.equal(autoContinueState().paused,true);
cards=[];const send=button('Send');send.closest=s=>s==='button[type="submit"]'?send:null;
form={contains:n=>n===send};autoContinueNoteSend({type:'click',target:send});
assert.equal(autoContinueState().active,true);
const next=card();cards=[next];autoContinueScan();flush();assert.equal(next.next.clicks,1);
""")

    def test_composer_stop_keyboard_and_explicit_resume(self):
        self.run_js(r"""
const c=card();cards=[c];autoContinueScan();const stop=button('หยุด');form={contains:n=>n===stop};
autoContinueNoteStop(stopEvent(stop,'keydown','Enter'));flush();assert.equal(c.next.clicks,0);
setAutoContinue(false);setAutoContinue(true);flush();assert.equal(c.next.clicks,1);
autoContinueNoteStop({isTrusted:false,target:stop,type:'click'});assert.equal(autoContinueState().stopped,false);
""")

    def test_plan_disabled_disconnected_and_replaced_controls_rechecked(self):
        self.run_js(r"""
const c=card();cards=[c];autoContinueScan();currentPlan=true;flush();assert.equal(c.next.clicks,0);
currentPlan=false;autoContinueScan();c.next.disabled=true;flush();assert.equal(c.next.clicks,0);
c.next.disabled=false;autoContinueScan();c.isConnected=false;flush();assert.equal(c.next.clicks,0);
c.isConnected=true;autoContinueScan();const previous=c.next, replacement=button('Continue');
c.children[1].querySelectorAll=()=>[replacement,c.stop];flush();assert.equal(previous.clicks,0);
autoContinueScan();flush();assert.equal(replacement.clicks,1);
""")


if __name__ == "__main__":
    unittest.main()
