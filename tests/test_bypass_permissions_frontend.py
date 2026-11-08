"""Run the actual frontend bypass code under Node without changing user chats or calling tools."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ENH = Path(os.environ.get("QWEN_ENH_FILE", r"C:\LLM\projects\static\webui-enhance.js"))
NODE = shutil.which("node")


def function(src, name):
    start = src.index("  function " + name + "(")
    pos = src.index("{", start)
    depth, quote = 0, None
    while pos < len(src):
        char = src[pos]
        if quote:
            if char == "\\":
                pos += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif src.startswith("//", pos):
            pos = src.index("\n", pos)
            continue
        elif src.startswith("/*", pos):
            pos = src.index("*/", pos) + 2
            continue
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return src[start:pos + 1]
        pos += 1
    raise ValueError("unbalanced function " + name)


ENV = r"""
const assert = require('node:assert/strict');
var location = {origin:'http://127.0.0.1:8105',href:'http://127.0.0.1:8105/?ui=1'};
var store = {}, listeners = {}, cards = [], forwards = [], scheduleCount = 0, confirmed = 0;
var sh = {project:{slug:'demo-b'}}, routeState = {name:'chat',id:'c1'}, currentPlan = false;
var planConvs = new Set(), PLAN_HEADER = 'X-Qwen-Plan', CONFIRM_TOOL = 'local_confirm';
var PROMPT_SEL = '.chat-messages div.rounded-lg.border.bg-card.p-3';
var TH = {'Allow once':'อนุญาตครั้งเดียว','Deny':'ปฏิเสธ'}, RV_TOKEN_OK = /^[A-Za-z0-9_-]{6,80}$/;
var RV_PAD_MAX = 4, RV_BLANK_MAX = 3;
var PY_WS = '\\t\\n\\x0B\\f\\r\\x1C-\\x1F \\x85\\xA0\\u1680\\u2000-\\u200A\\u2028\\u2029\\u202F\\u205F\\u3000';
var PY_STRIP_RE = new RegExp('^['+PY_WS+']+|['+PY_WS+']+$','g');
function hasOwn(o,k){return Object.prototype.hasOwnProperty.call(o,k);}
function shell(){return sh;}
function lsGet(k){return store[k] == null ? null : store[k];}
function lsSet(k,v){store[k]=v;}
function route(){return routeState;}
function planCurrent(){return currentPlan;}
function planFor(conv){return planConvs.has(conv) || (!conv && currentPlan);}
function planConv(s){return String(s||'').split('::')[0].trim();}
function enText(n){return n ? n.textContent || '' : '';}
function hasLabel(t,label){return t.includes(label) || (TH[label] && t.includes(TH[label]));}
function schedule(){scheduleCount++;}
function confirmCards(){confirmed++;}
function composerForm(){return null;}
function composerToolbar(){return null;}
function detach(){}
var window={addEventListener:(t,f)=>{(listeners[t]||(listeners[t]=[])).push(f);},
  fetch:function(input,init){forwards.push({input,init,receiver:this});return Promise.resolve({ok:true});}};
var document={querySelectorAll:()=>cards};
function button(text){return {textContent:text,disabled:false,clicks:0,attrs:{},
  getAttribute(k){return this.attrs[k] || null;},click(){this.clicks++;}};}
function card(tool='read_file',opts={}){
  const allow=button(opts.allow || 'Allow once'), deny=button(opts.deny || 'Deny');
  const names=[{textContent:tool},{textContent:opts.server || 'Local tools'}];
  const head={textContent:opts.head || 'Allow use of '+tool+' from Local tools?',querySelectorAll:()=>names};
  const acts={textContent:allow.textContent+deny.textContent,querySelector:()=>allow,
    querySelectorAll:()=>opts.buttons || [allow,deny],classList:{contains:x=>['flex','items-center'].includes(x)}};
  return {isConnected:true,children:[head,acts],allow,deny,native:opts.native!==false,blocked:!!opts.blocked,
    matches(){return this.native;},closest(s){return s==='.agentic-content'?this.native?{}:null:this.blocked?{}:null;}};
}
function review(c,opts={}){
  c.__qwRv=Object.assign({card:c,good:true,busy:false,bypassCurrent:true,bypassConv:'c1',server:'Local tools',
    r:{status:'ok',callId:'call1',args:{confirm_token:'token_12345'}},
    srv:{state:'ok',tok:'token_12345',review:'print(1)',expAt:Date.now()+50000}},opts);
  return c.__qwRv;
}
"""


@unittest.skipUnless(NODE, "Node is required")
class BypassFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = ENH.read_text(encoding="utf-8")
        start = cls.src.index("  /* ---- Bypass permissions (")
        cls.block = cls.src[start:cls.src.index("  /* ---- 2) ไมค์:", start)]
        names = ("promptInfo", "pyStrip", "pyTruthy", "rvToken", "rvModelDiffers", "rvNormalize")
        cls.helpers = "\n".join(function(cls.src, name) for name in names)

    def run_js(self, case, before="", plan_wrapper=False):
        stack = ""
        if plan_wrapper:
            start = self.src.index("  var nativeFetch = window.fetch;")
            stack = function(self.src, "planRequest") + "\n" + self.src[start:self.src.index("  // จดการกดส่ง", start)]
        code = ENV + self.helpers + before + stack + self.block + "\n(async()=>{\n" + case + "\nconsole.log(JSON.stringify({ok:true}));})().catch(e=>{console.error(e.stack);process.exitCode=1;});"
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as f:
            f.write(code)
            path = f.name
        try:
            p = subprocess.run([NODE, path], capture_output=True, text=True, encoding="utf-8", timeout=25)
        finally:
            os.remove(path)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), {"ok": True})

    def test_default_off_project_persistence_and_port_reuse(self):
        self.run_js(r"""
assert.equal(bypassState().on,false);
assert.equal(bypassState().active,false);
assert.equal(setBypass(true),true);
assert.deepEqual(JSON.parse(store[BYPASS_KEY]),{project:'demo-b',on:true});
bypassProject='';bypassOn=false;assert.equal(bypassState().active,true);
sh.project.slug='other-project';assert.equal(bypassState().active,false);
sh=null;assert.equal(bypassState().ready,false);assert.equal(setBypass(true),false);
sh={project:{slug:'demo-b'}};assert.equal(bypassState().active,true);
store[BYPASS_KEY]='1';bypassProject='';assert.equal(bypassState().active,false);
store[BYPASS_KEY]='{bad';bypassProject='';assert.equal(bypassState().active,false);
""")

    def test_only_native_permission_controls_existing_and_new(self):
        self.run_js(r"""
const pending=card(), markdown=card('read_file',{blocked:true}), fake=card('read_file',{native:false});
const turn=card('read_file',{head:'Agentic turn limit reached. Continue?'});
const wrong=card('read_file',{allow:'Always allow read_file'}), noDeny=card('read_file',{deny:'Cancel'});
cards=[pending,markdown,fake,turn,wrong,noDeny];bypassScan();assert.equal(pending.allow.clicks,0);
setBypass(true);assert.equal(pending.allow.clicks,1);
for(const c of [markdown,fake,turn,wrong,noDeny])assert.equal(c.allow.clicks,0);
bypassScan();bypassScan();assert.equal(pending.allow.clicks,1);
const fresh=card('write_file');cards.push(fresh);bypassScan();assert.equal(fresh.allow.clicks,1);
const thai=card('exec',{allow:'อนุญาตครั้งเดียว',deny:'ปฏิเสธ'});cards.push(thai);
bypassScan();assert.equal(thai.allow.clicks,1);
const disabled=card();disabled.allow.disabled=true;cards=[disabled];bypassScan();assert.equal(disabled.allow.clicks,0);
""")

    def test_local_confirm_valid_current_server_review_only(self):
        self.run_js(r"""
setBypass(true);
const valid=card('local_confirm');review(valid);assert.equal(bypassCard(valid),true);assert.equal(valid.allow.clicks,1);
assert.equal(bypassCard(valid),false);assert.equal(valid.allow.clicks,1);
const badStates=[{good:false},{busy:true},{bypassCurrent:false},{bypassConv:'old'},{server:'Other'},
  {r:{status:'unknown'}},{r:{status:'badargs'}},{srv:null},
  {srv:{state:'loading'}},{srv:{state:'fail'}},{srv:{state:'ok',tok:'other',review:'print(1)',expAt:Date.now()+50000}},
  {srv:{state:'ok',tok:'token_12345',review:'print(1)',expAt:Date.now()-1}},
  {srv:{state:'ok',tok:'token_12345',review:'print(1)',expAt:0}},
  {srv:{state:'ok',tok:'token_12345',review:'',expAt:Date.now()+50000}},
  {r:{status:'ok',args:{confirm_token:'token_12345',review:'different code'}}},
  {r:{status:'ok',args:{confirm_token:'token_12345',review:42}}}];
for(const opts of badStates){const c=card('local_confirm');review(c,opts);assert.equal(bypassCard(c),false,JSON.stringify(opts));assert.equal(c.allow.clicks,0);}
const padded=card('local_confirm');review(padded,{r:{status:'ok',args:{confirm_token:'token_12345',review:'     print(1)'}}});
assert.equal(bypassCard(padded),false);
const normalized=card('local_confirm');review(normalized,{r:{status:'ok',args:{confirm_token:'token_12345',review:' print(1) '}}});
assert.equal(bypassCard(normalized),true);
""")

    def test_off_and_plan_stop_pending_asynchronous_approvals(self):
        self.run_js(r"""
setBypass(true);const c=card('local_confirm');review(c,{srv:{state:'loading'}});cards=[c];bypassScan();
setBypass(false);review(c);bypassCard(c);assert.equal(c.allow.clicks,0);
setBypass(true);const planned=card();cards=[planned];currentPlan=true;
assert.equal(bypassState().on,true);assert.equal(bypassState().paused,true);assert.equal(bypassState().active,false);
bypassScan();assert.equal(planned.allow.clicks,0);
currentPlan=false;bypassScan();assert.equal(planned.allow.clicks,1);
const crossTab=card();cards=[crossTab];store[BYPASS_KEY]=JSON.stringify({project:'demo-b',on:false});
for(const fn of listeners.storage)fn({key:BYPASS_KEY});bypassScan();assert.equal(crossTab.allow.clicks,0);
""")

    def test_header_scoping_removal_and_wrapper_stack(self):
        self.run_js(r"""
setBypass(true);
const init={method:'POST',headers:{'Content-Type':'application/json','X-Conversation-Id':'c1::model'},body:'{"messages":[]}',credentials:'same-origin'};
await window.fetch('/v1/chat/completions',init);
assert.equal(forwards.length,1);let f=forwards.pop();assert.equal(f.receiver,window);
assert.equal(new Headers(f.init.headers).get(BYPASS_HEADER),'1');assert.equal(f.init.body,init.body);assert.equal(f.init.credentials,init.credentials);
assert.equal(init.headers[BYPASS_HEADER],undefined);
for(const url of ['http://other.test/v1/chat/completions','/_qwen/stt','/v1/chat/completions-extra']){
  await window.fetch(url,init);f=forwards.pop();assert.equal(f.init,init);
}
await window.fetch('/v1/chat/completions',{method:'GET'});assert.deepEqual(forwards.pop().init,{method:'GET'});
planConvs.add('c1');await window.fetch('/v1/chat/completions',init);f=forwards.pop();
assert.equal(new Headers(f.init.headers).get(PLAN_HEADER),'1');assert.equal(new Headers(f.init.headers).has(BYPASS_HEADER),false);
planConvs.clear();await window.fetch('/v1/chat/completions',{method:'POST',headers:{'X-Qwen-Plan':'1',[BYPASS_HEADER]:'1'}});
f=forwards.pop();assert.equal(new Headers(f.init.headers).has(BYPASS_HEADER),false);
setBypass(false);const stale={method:'POST',headers:{[BYPASS_HEADER]:'1','X-Test':'keep'},body:'abc'};
await window.fetch('/v1/chat/completions',stale);f=forwards.pop();
assert.equal(new Headers(f.init.headers).has(BYPASS_HEADER),false);assert.equal(new Headers(f.init.headers).get('X-Test'),'keep');
assert.equal(stale.headers[BYPASS_HEADER],'1');assert.equal(f.init.body,'abc');
""", plan_wrapper=True)

    def test_request_override_and_body_are_preserved(self):
        self.run_js(r"""
setBypass(true);
const req=new Request(location.origin+'/v1/chat/completions',{method:'POST',headers:{'X-Test':'request'},body:'payload'});
await window.fetch(req);let f=forwards.pop();assert.equal(f.input,req);assert.equal(req.bodyUsed,false);
assert.equal(new Headers(f.init.headers).get('X-Test'),'request');assert.equal(new Headers(f.init.headers).get(BYPASS_HEADER),'1');
assert.equal(req.headers.has(BYPASS_HEADER),false);
const ctl=new AbortController(),override={headers:new Headers({'X-Test':'override'}),body:'override payload',signal:ctl.signal};
await window.fetch(req,override);f=forwards.pop();assert.equal(f.input,req);assert.equal(f.init.body,override.body);assert.equal(f.init.signal,ctl.signal);
assert.equal(new Headers(f.init.headers).get('X-Test'),'override');assert.equal(override.headers.has(BYPASS_HEADER),false);
const absent=bypassRequest('/v1/chat/completions',{method:'POST'});assert.equal(new Headers(absent[1].headers).get(BYPASS_HEADER),'1');
sh=null;const gone=bypassRequest('/v1/chat/completions',{method:'POST',headers:{[BYPASS_HEADER]:'1'}});
assert.equal(new Headers(gone[1].headers).has(BYPASS_HEADER),false);
""")

    def test_js_syntax(self):
        p = subprocess.run([NODE, "--check", str(ENH)], capture_output=True, text=True, timeout=25)
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
