"""Fault-injection tests for the exact shipped durable browser recovery wrapper.

No real project, browser profile, model, command, or MCP service is used.  The
fake server journals one action per recovery UUID and can lose its response at
any byte; assertions deliberately avoid printing prompts or request bodies.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(os.environ.get("QWEN_RECOVERY_FILE", r"C:\LLM\projects\static\auto-recovery.js"))
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"

ENV = r"""
const assert=require('node:assert/strict');
const crypto=require('node:crypto').webcrypto;
const realTimeout=globalThis.setTimeout.bind(globalThis);
const listeners={},intervals=[],requests=[],journal=new Map();
const localData={},sessionData={};
function storage(data){return {getItem:k=>data[k]??null,setItem:(k,v)=>{data[k]=String(v)},removeItem:k=>{delete data[k]}};}
let current={name:'chat',id:'chat-one'},settings={on:true,active:true,project:'test-project',stopped:false},plan=false;
let behavior=null,executions=0,invalidations=0,captures=0,restores=0;
const location=new URL('http://127.0.0.1:8178/#/chat/chat-one');
const navigator={onLine:true};
function element(){return {hidden:false,textContent:'',style:{},setAttribute(){},appendChild(){}};}
const document={readyState:'complete',documentElement:{lang:'en'},body:{appendChild(){}},createElement:element,
 addEventListener:(kind,fn)=>{(listeners[kind]??=[]).push(fn)}};
function emit(kind,event={}){for(const fn of listeners[kind]||[])fn({...event,type:kind});}
function pause(ms=15){return new Promise(resolve=>realTimeout(resolve,ms));}
function bytes(value){return new TextEncoder().encode(value);}
const GOOD='data: {"choices":[{"delta":{"content":"สวัสดี 🌏"},"finish_reason":null}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n';
function response(raw,offset=0,opts={}){
 const data=typeof raw==='string'?bytes(raw):raw;
 const pieces=opts.pieces||[data];let index=0;
 const stream=new ReadableStream({pull(c){if(index<pieces.length){c.enqueue(pieces[index++]);return;}
  if(opts.error)c.error(new TypeError('simulated connection lost'));else c.close();}},{highWaterMark:0});
 return new Response(stream,{status:opts.status||200,headers:{'Content-Type':opts.type||'text/event-stream',
  ...(opts.missingOffset?{}:{'X-Qwen-Recovery-Offset':String(opts.returnedOffset??offset)})}});
}
function requestInfo(url,init){const h=new Headers(init?.headers);return {url:String(url),offset:Number(h.get('X-Qwen-Recovery-Offset')||0),
 id:h.get('X-Qwen-Recovery-ID'),target:h.get('X-Qwen-Recovery-Target'),headers:h,init};}
async function transport(url,init){
 const req=requestInfo(url,init);requests.push(req);
 if(behavior)return behavior(req);
 return response(GOOD,req.offset);
}
const window={crypto,navigator,sessionStorage:storage(sessionData),localStorage:storage(localData),fetch:transport,
 addEventListener:(kind,fn)=>{(listeners[kind]??=[]).push(fn)},
 qwenEnhance:{autoContinue:()=>({...settings}),route:()=>({...current}),plan:()=>({on:plan}),isStreaming:()=>false},
 qwenRecoveryHistory:{async capture(op){captures++;return {id:op.id,marker:'native-binding',bodyHash:'fixture-hash'}},
  async restore(record,result){restores++;assert.ok(record.binding);return {restored:true,continue:false,reload:false}},
  async canAttach(){return true;},
  invalidate(){invalidations++}}
};
function setTimeout(fn,ms){return realTimeout(fn,Math.min(ms,5));}
function clearTimeout(id){globalThis.clearTimeout(id);}
function setInterval(fn){intervals.push(fn);return intervals.length;}
function stopButton(){const f={};return {textContent:'Stop',classList:{contains:()=>false},getAttribute:()=>null,
 closest(selector){if(selector==='button')return this;if(selector==='.chat-screen-form-wrapper form')return f;return null;}};}
function sendButton(){const f={};return {tagName:'BUTTON',closest(selector){if(selector==='.chat-screen-form-wrapper form')return f;
 if(selector==='button[type="submit"]')return this;return null;}};}
function config(extra={}){return {method:'POST',headers:{'Content-Type':'application/json','X-Conversation-Id':'chat-one'},
 body:JSON.stringify({model:'fixture-model',stream:true,messages:[{role:'user',content:'fixture'}]}),...extra};}
function server(req,opts={}){
 if(req.id&&!journal.has(req.id)){journal.set(req.id,{raw:opts.raw||GOOD});executions++;}
 const raw=bytes(journal.get(req.id)?.raw||opts.raw||GOOD);
 return response(raw.slice(req.offset),req.offset,opts);
}
async function readAll(response){return new Uint8Array(await response.arrayBuffer());}
"""


@unittest.skipUnless(Path(NODE).exists() or shutil.which(NODE), "Node is required")
class AutoRecoveryFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def run_js(self, case, pre=""):
        source = ENV + "\n" + pre + "\n" + self.source + "\n(async()=>{\n" + case + r"""
 console.log(JSON.stringify({ok:true}));
})().catch(e=>{console.error(e.stack||String(e));process.exitCode=1;});
"""
        with tempfile.TemporaryDirectory(prefix="auto-recovery-test-") as directory:
            script = Path(directory) / "case.js"
            script.write_text(source, encoding="utf-8")
            result = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr[-6000:])
        self.assertEqual(json.loads(result.stdout), {"ok": True})

    def test_clean_stream_preserves_exact_bytes_and_headers_without_retry(self):
        self.run_js(r"""
behavior=req=>server(req);
const out=await window.fetch('/v1/chat/completions',config());
assert.equal(out.status,200);assert.match(out.headers.get('Content-Type'),/event-stream/);
assert.deepEqual(await readAll(out),bytes(GOOD));
assert.equal(requests.length,1);assert.equal(executions,1);assert.equal(captures,1);
assert.equal(window.qwenRecovery.status().operations[0].state,'delivered');
""")

    def test_unbound_native_ui_directory_lookup_does_not_create_a_recovery_task(self):
        self.run_js(r"""
window.qwenRecoveryHistory.capture=async()=>null;
behavior=req=>response('{"entries":[],"base":"fixture"}',0,{type:'application/json'});
const body='{"tool":"list_dir","params":{"path":"fixture"}}';
const result=await window.fetch('/tools',config({body}));
assert.deepEqual(await result.json(),{entries:[],base:'fixture'});
assert.equal(requests.length,1);assert.equal(requests[0].url,'/tools');
assert.equal(requests[0].id,null);assert.equal(requests[0].init.body,body);
assert.equal(window.qwenRecovery.status().active,0);assert.equal(window.qwenRecovery.status().pending,0);
""")

    def test_unbound_mcp_ui_call_preserves_original_endpoint_and_auth(self):
        self.run_js(r"""
window.qwenRecoveryHistory.capture=async()=>null;
behavior=req=>response('{"jsonrpc":"2.0","id":7,"result":{"content":[]}}',0,{type:'application/json'});
const endpoint='http://127.0.0.1:8791/mcp';
const result=await window.fetch(endpoint,config({headers:{Authorization:'Bearer fixture-only'},
 body:'{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"fixture"}}'}));
assert.equal((await result.json()).id,7);assert.equal(requests.length,1);
assert.equal(requests[0].url,endpoint);assert.equal(requests[0].id,null);
assert.equal(requests[0].headers.get('Authorization'),'Bearer fixture-only');
assert.equal(window.qwenRecovery.status().pending,0);
""")

    def test_lost_headers_reattaches_same_server_operation_and_executes_once(self):
        self.run_js(r"""
behavior=req=>{const result=server(req);if(requests.length===1)throw new TypeError('lost headers');return result;};
assert.deepEqual(await readAll(await window.fetch('/tools',config({body:'{"tool":"exec_shell_command","stream":true,"params":{"command":"fixture"}}'}))),bytes(GOOD));
assert.equal(requests.length,2);assert.equal(executions,1);
assert.equal(requests[0].id,requests[1].id);assert.equal(requests[1].offset,0);
""")

    def test_mid_utf8_disconnect_resumes_raw_byte_offset_without_duplicate_text(self):
        self.run_js(r"""
const full=bytes(GOOD),cut=full.findIndex((b,i)=>b>=224&&full[i+1]>=128)+1;
behavior=req=>{if(requests.length===1){server(req);return response(full.slice(0,cut),0,{error:true});}return server(req);};
const out=await readAll(await window.fetch('/v1/chat/completions',config()));
assert.deepEqual(out,full);assert.equal(requests[1].offset,cut);
assert.equal(executions,1);assert.equal(new Set(requests.map(r=>r.id)).size,1);
""")

    def test_tool_response_lost_after_execution_is_not_reexecuted(self):
        self.run_js(r"""
const raw='data: {"chunk":"fixture result"}\n\ndata: {"done":true}\n\n';
behavior=req=>{if(requests.length===1){server(req,{raw});return response(bytes(raw).slice(0,13),0,{error:true});}return server(req,{raw});};
assert.deepEqual(await readAll(await window.fetch('/tools',config({body:'{"tool":"exec_shell_command","stream":true,"params":{"command":"fixture"}}'}))),bytes(raw));
assert.equal(executions,1);assert.equal(requests[1].offset,13);
""")

    def test_unintended_abort_reconnects_using_fresh_transport_signal(self):
        self.run_js(r"""
const original=new AbortController();
behavior=req=>server(req);
const response=await window.fetch('/v1/chat/completions',config({signal:original.signal}));
original.abort();
assert.deepEqual(await readAll(response),bytes(GOOD));
assert.equal(executions,1);assert.equal(requests.length,2);
assert.notEqual(requests[0].init.signal,original.signal);
assert.notEqual(requests[0].init.signal,requests[1].init.signal);
""")

    def test_explicit_stop_cancels_worker_and_survives_page_reload(self):
        self.run_js(r"""
behavior=req=>req.url.endsWith('/cancel')?new Response('{}'):server(req);
const out=await window.fetch('/v1/chat/completions',config());
const button=stopButton();emit('pointerdown',{isTrusted:true,target:button});
await assert.rejects(()=>out.arrayBuffer(),/paused|Stopped/);
const cancel=requests.filter(r=>r.url.endsWith('/cancel'));assert.equal(cancel.length,1);
const marks=JSON.parse(sessionData['qwen-stream-recovery-stops-v1']);assert.ok(marks['test-project|chat-one']);
assert.equal(invalidations,1);
assert.equal(window.qwenRecovery.status().operations[0].state,'stopped');
""")

    def test_untrusted_stop_and_permission_buttons_cannot_cancel_recovery(self):
        self.run_js(r"""
behavior=req=>server(req);const out=await window.fetch('/v1/chat/completions',config());
emit('click',{isTrusted:false,target:stopButton()});
const allow=stopButton();allow.textContent='Allow once';emit('click',{isTrusted:true,target:allow});
assert.deepEqual(await readAll(out),bytes(GOOD));
assert.equal(requests.filter(r=>r.url.endsWith('/cancel')).length,0);assert.equal(invalidations,0);
""")

    def test_offline_recovery_waits_then_online_reconnects_once(self):
        self.run_js(r"""
behavior=req=>{server(req);if(requests.length===1){navigator.onLine=false;throw new TypeError('offline');}return server(req);};
const pending=window.fetch('/v1/chat/completions',config());await pause(25);
assert.equal(requests.length,1);navigator.onLine=true;emit('online');
assert.deepEqual(await readAll(await pending),bytes(GOOD));assert.equal(executions,1);
""")

    def test_route_switch_and_plan_mode_pause_reconnect_until_same_chat_returns(self):
        self.run_js(r"""
behavior=req=>{server(req);if(requests.length===1){current.id='chat-two';throw new TypeError('navigate');}return server(req);};
const pending=window.fetch('/v1/chat/completions',config());await pause(20);assert.equal(requests.length,1);
current.id='chat-one';plan=true;emit('hashchange');await pause(20);assert.equal(requests.length,1);
plan=false;emit('online');assert.deepEqual(await readAll(await pending),bytes(GOOD));assert.equal(executions,1);
""")

    def test_new_human_message_invalidates_prior_reconnect(self):
        self.run_js(r"""
behavior=req=>server(req);const out=await window.fetch('/v1/chat/completions',config());
emit('click',{isTrusted:true,target:sendButton()});
await assert.rejects(()=>out.arrayBuffer(),/paused/);
assert.equal(window.qwenRecovery.status().operations[0].state,'superseded');
assert.equal(invalidations,1);assert.equal(executions,1);
""")

    def test_message_sent_while_reply_runs_is_queued_without_cancelling_it(self):
        # 2026-10-19: the WebUI (or message-queue.js) queues a message typed while the chat is still
        # working. The running reply must keep streaming: nothing superseded, aborted or invalidated.
        self.run_js(r"""
behavior=req=>server(req);const out=await window.fetch('/v1/chat/completions',config());
function runningForm(label){const stop={getAttribute:k=>null,closest:()=>null,classList:{contains:()=>false},
 querySelector:sel=>sel==='.sr-only'?{textContent:label}:null};return {querySelectorAll:sel=>sel==='button'?[stop]:[]};}
for(const label of ['Stop','หยุด','Skip reasoning']){
 const form=runningForm(label),send={tagName:'TEXTAREA',closest(sel){return sel==='.chat-screen-form-wrapper form'?form:null;}};
 emit('keydown',{isTrusted:true,target:send,key:'Enter'});
}
assert.deepEqual(await readAll(out),bytes(GOOD));
assert.equal(invalidations,0);assert.equal(executions,1);
assert.notEqual(window.qwenRecovery.status().operations.map(o=>o.state).join(),'superseded');
""")

    def test_queue_dispatch_hook_starts_a_new_turn_only_when_idle(self):
        self.run_js(r"""
behavior=req=>server(req);const out=await window.fetch('/v1/chat/completions',config());
document.querySelector=sel=>null;
window.qwenRecovery.noteSend();
await assert.rejects(()=>out.arrayBuffer(),/paused/);
assert.equal(window.qwenRecovery.status().operations[0].state,'superseded');assert.equal(invalidations,1);
""")

    def test_conflict_and_auth_errors_never_create_new_operation(self):
        for status in (400, 401, 403, 409):
            with self.subTest(status=status):
                self.run_js(r"""
behavior=req=>response('{}',0,{status:STATUS,type:'application/json'});
await assert.rejects(()=>window.fetch('/tools',config()),e=>e.status===STATUS);
assert.equal(requests.length,1);assert.equal(window.qwenRecovery.status().pending,1);
""".replace("STATUS", str(status)))

    def test_transient_http_response_retries_same_identity(self):
        self.run_js(r"""
behavior=req=>requests.length===1?response('{}',0,{status:503,type:'application/json'}):server(req);
assert.deepEqual(await readAll(await window.fetch('/v1/chat/completions',config())),bytes(GOOD));
assert.equal(requests.length,2);assert.equal(requests[0].id,requests[1].id);assert.equal(executions,1);
""")

    def test_cached_server_error_is_terminal_and_never_retried(self):
        self.run_js(r"""
behavior=req=>new Response('{}',{status:503,headers:{'Content-Type':'application/json','X-Qwen-Recovery-ID':req.id,'X-Qwen-Recovery-Offset':'0'}});
await assert.rejects(()=>window.fetch('/tools',config()),/saved an error response/);
assert.equal(requests.length,1);assert.equal(window.qwenRecovery.status().operations[0].state,'needs_attention');
""")

    def test_changed_native_branch_rejects_abort_replay(self):
        self.run_js(r"""
behavior=req=>server(req);const controller=new AbortController();
const out=await window.fetch('/v1/chat/completions',config({signal:controller.signal}));
window.qwenRecoveryHistory.canAttach=async()=>false;controller.abort();
await assert.rejects(()=>readAll(out),/branch changed/);
assert.equal(requests.length,1);assert.equal(executions,1);
""")

    def test_unknown_branch_binding_never_reconnects_blindly(self):
        self.run_js(r"""
window.qwenRecoveryHistory.capture=async()=>null;
behavior=req=>{server(req);throw new TypeError('lost');};
await assert.rejects(()=>window.fetch('/v1/chat/completions',config()),/branch changed/);
assert.equal(requests.length,1);assert.equal(executions,1);
""")

    def test_unbound_tool_transport_failure_is_never_replayed(self):
        self.run_js(r"""
window.qwenRecoveryHistory.capture=async()=>null;
let effects=0;
behavior=req=>{effects++;throw new TypeError('lost original response');};
await assert.rejects(()=>window.fetch('/tools',config()),/lost original response/);
assert.equal(effects,1);assert.equal(requests.length,1);assert.equal(requests[0].id,null);
assert.equal(window.qwenRecovery.status().active,0);assert.equal(window.qwenRecovery.status().pending,0);
""")

    def test_trusted_native_regenerate_detaches_old_response(self):
        self.run_js(r"""
behavior=req=>server(req);const out=await window.fetch('/v1/chat/completions',config());
const control={textContent:'Regenerate',getAttribute:()=>null,
 closest(selector){if(selector==='button,[role=\'menuitem\']')return this;
 if(selector==='.chat-message,.chat-messages,[role=\'menu\'],[role=\'dialog\']')return {};return null;}};
emit('click',{isTrusted:true,target:control});
await assert.rejects(()=>readAll(out),/paused/);assert.equal(invalidations,1);
assert.equal(executions,1);assert.equal(requests.filter(r=>r.url.endsWith('/cancel')).length,0);
""")

    def test_half_open_header_wait_reconnects_same_operation(self):
        self.run_js(r"""
behavior=req=>{const saved=server(req);return requests.length===1?new Promise(()=>{}):saved;};
assert.deepEqual(await readAll(await window.fetch('/tools',config())),bytes(GOOD));
assert.equal(requests.length,2);assert.equal(executions,1);assert.equal(requests[0].id,requests[1].id);
assert.equal(requests[0].init.signal.aborted,true);
""")

    def test_half_open_body_reader_reconnects_same_operation(self):
        self.run_js(r"""
behavior=req=>{server(req);if(requests.length!==1)return server(req);
 return new Response(new ReadableStream({pull(){return new Promise(()=>{});}}),{headers:{'Content-Type':'text/event-stream','X-Qwen-Recovery-Offset':'0'}});};
assert.deepEqual(await readAll(await window.fetch('/tools',config())),bytes(GOOD));
assert.equal(requests.length,2);assert.equal(executions,1);assert.equal(requests[1].offset,0);
""")

    def test_stop_interrupts_header_wait_without_waiting_for_watchdog(self):
        self.run_js(r"""
behavior=req=>req.url.endsWith('/cancel')?new Response('{}'):(server(req),new Promise(()=>{}));
const pending=window.fetch('/tools',config()).then(()=>({ok:true}),error=>({error}));
await pause(1);emit('click',{isTrusted:true,target:stopButton()});
const outcome=await pending;assert.equal(outcome.error.name,'AbortError');
assert.equal(requests.filter(r=>!r.url.endsWith('/cancel')).length,1);
assert.equal(requests.filter(r=>r.url.endsWith('/cancel')).length,1);
""")

    def test_missing_or_mismatched_offset_fails_without_repeating(self):
        for option in ("missingOffset:true", "returnedOffset:4"):
            with self.subTest(option=option):
                self.run_js(r"""
behavior=req=>response(GOOD,0,{OPTION});
await assert.rejects(()=>window.fetch('/v1/chat/completions',config()),/byte position/);
assert.equal(requests.length,1);
""".replace("OPTION", option))

    def test_clean_eof_without_sse_completion_is_visible_and_never_regenerates(self):
        self.run_js(r"""
behavior=req=>server(req,{raw:'data: {"choices":[{"delta":{"content":"partial"},"finish_reason":null}]}\n\n'});
await assert.rejects(()=>readAllResult(),/before completion/);
async function readAllResult(){return readAll(await window.fetch('/v1/chat/completions',config()));}
assert.equal(requests.length,1);assert.equal(executions,1);
assert.equal(window.qwenRecovery.status().operations[0].state,'needs_attention');
""")

    def test_complete_finish_reason_without_done_is_not_retried(self):
        self.run_js(r"""
const raw='data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n';
behavior=req=>server(req,{raw});assert.deepEqual(await readAll(await window.fetch('/v1/chat/completions',config())),bytes(raw));
assert.equal(requests.length,1);
""")

    def test_mcp_tools_call_uses_strict_bridge_and_same_identity(self):
        self.run_js(r"""
const raw='{"jsonrpc":"2.0","id":1,"result":{"content":[]}}';
behavior=req=>server(req,{raw,type:'application/json'});
const init=config({body:'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"fixture","arguments":{}}}'});
assert.deepEqual(await readAll(await window.fetch('http://127.0.0.1:8792/fast/test-project',init)),bytes(raw));
assert.equal(requests[0].url,location.origin+'/_qwen/recovery/mcp/local');
assert.equal(requests[0].target,'http://127.0.0.1:8792/fast/test-project');assert.equal(executions,1);
""")

    def test_mcp_non_tool_and_untrusted_destinations_are_untouched(self):
        self.run_js(r"""
behavior=req=>new Response('{}',{headers:{'Content-Type':'application/json'}});
const tool=config({body:'{"method":"tools/call"}'});
for(const url of ['https://external.invalid/tools','http://127.0.0.1:8792/fast/another-project','http://127.0.0.1:8791/mcp?x=1']){
 await (await window.fetch(url,tool)).text();assert.equal(requests.at(-1).id,null);
}
await (await window.fetch('http://127.0.0.1:8791/mcp',config({body:'{"method":"tools/list"}'}))).text();
assert.equal(requests.at(-1).id,null);assert.equal(captures,0);
""")

    def test_disabled_auto_continue_and_plan_preserve_original_fetch(self):
        self.run_js(r"""
behavior=req=>new Response('{}');settings.on=false;
await (await window.fetch('/tools',config())).text();assert.equal(requests.at(-1).id,null);
settings.on=true;plan=true;
await (await window.fetch('/tools',config())).text();assert.equal(requests.at(-1).id,null);
""")

    def test_session_records_never_persist_auth_headers(self):
        self.run_js(r"""
behavior=req=>server(req);
const out=await window.fetch('/tools',config({headers:{'Content-Type':'application/json','Authorization':'Bearer fixture-secret',
 'Cookie':'fixture-cookie','X-Api-Key':'fixture-api-key'}}));
const stored=sessionData['qwen-stream-recovery-v1'];
for(const secret of ['fixture-secret','fixture-cookie','fixture-api-key','Authorization','Cookie','X-Api-Key']) assert.equal(stored.includes(secret),false);
assert.equal(JSON.parse(stored)[requests[0].id].binding.marker,'native-binding');
assert.equal(Object.hasOwn(JSON.parse(stored)[requests[0].id],'body'),false);
await readAll(out);
""")

    def test_saved_complete_job_restores_by_same_uuid_without_execution(self):
        pre = r"""
sessionData['qwen-stream-recovery-v1']=JSON.stringify({'old-id':{id:'old-id',project:'test-project',chat:'chat-one',kind:'chat',
 url:location.origin+'/v1/chat/completions',body:'{}',contentType:'application/json',offset:3,state:'pending',createdAt:1,binding:{marker:'native-binding'}}});
"""
        self.run_js(r"""
behavior=req=>req.url.endsWith('/old-id')?new Response('{"state":"completed","size":42}',{headers:{'Content-Type':'application/json'}}):response(GOOD,0);
await window.qwenRecovery.restore();
assert.equal(restores,1);assert.equal(window.qwenRecovery.status().pending,0);
assert.equal(requests.filter(r=>r.init?.method==='POST').length,0);assert.equal(executions,0);
assert.equal(requests.at(-1).url,'/_qwen/recovery/old-id/result');
""", pre=pre)

    def test_unknown_saved_outcome_never_reposts_or_restores(self):
        pre = r"""
sessionData['qwen-stream-recovery-v1']=JSON.stringify({'old-id':{id:'old-id',project:'test-project',chat:'chat-one',kind:'tools',
 url:location.origin+'/tools',body:'{}',offset:3,state:'pending',createdAt:1,binding:{marker:'native-binding'}}});
"""
        self.run_js(r"""
behavior=req=>new Response('{"state":"outcome_unknown","size":10}',{headers:{'Content-Type':'application/json'}});
await window.qwenRecovery.restore();assert.equal(restores,0);assert.equal(requests.length,1);
assert.equal(requests[0].init?.method,undefined);assert.equal(window.qwenRecovery.status().pending,1);
""", pre=pre)

    def test_live_eof_marker_survives_until_native_history_acknowledges(self):
        self.run_js(r"""
behavior=req=>server(req);const out=await window.fetch('/v1/chat/completions',config());
await readAll(out);const id=requests[0].id;
assert.equal(window.qwenRecovery.status().operations[0].state,'delivered');
window.qwenRecoveryHistory.acknowledge=async(record,result)=>record.id===id&&result.text===GOOD;
behavior=req=>req.url.endsWith('/result')?response(GOOD,0):new Response('{"state":"completed"}',{headers:{'Content-Type':'application/json'}});
await window.qwenRecovery.restore();assert.equal(window.qwenRecovery.status().pending,0);assert.equal(restores,0);
assert.ok(requests.slice(1).every(r=>r.init?.method===undefined));
""")

    def test_native_ack_gap_keeps_marker_when_restore_cannot_be_proven(self):
        pre = r"""
sessionData['qwen-stream-recovery-v1']=JSON.stringify({'old-id':{id:'old-id',project:'test-project',chat:'chat-one',kind:'chat',
 state:'delivered',createdAt:1,requestHash:'fixture-hash',binding:{marker:'native-binding'}}});
window.qwenRecoveryHistory.acknowledge=async()=>false;
window.qwenRecoveryHistory.restore=async()=>({restored:false,reason:'context_changed'});
"""
        self.run_js(r"""
behavior=req=>req.url.endsWith('/result')?response(GOOD,0):new Response('{"state":"completed"}',{headers:{'Content-Type':'application/json'}});
await window.qwenRecovery.restore();assert.equal(window.qwenRecovery.status().pending,1);
assert.equal(requests.filter(r=>r.init?.method==='POST').length,0);
""", pre=pre)

    def composer_pre(self, phase="continue", draft=""):
        return r"""
let submissions=0,reloads=0;
class HTMLTextAreaElement{constructor(){this._value=DRAFT;}dispatchEvent(){}}
Object.defineProperty(HTMLTextAreaElement.prototype,'value',{get(){return this._value},set(v){this._value=v}});
const area=new HTMLTextAreaElement(),send={disabled:false,getAttribute:()=>null,click(){submissions++}};
const form={querySelector:selector=>selector==='textarea'?area:send,requestSubmit(){submissions++}};
document.querySelector=selector=>selector==='.chat-screen-form-wrapper form.conversation-chat-form'?form:null;
location.reload=()=>{reloads++};
window.qwenRecoveryHistory.canContinue=async()=>true;
sessionData['qwen-stream-recovery-refresh-v1']=JSON.stringify({project:'test-project',chat:'chat-one',ticket:{id:'known-result'},at:Date.now(),phase:PHASE});
""".replace("DRAFT", json.dumps(draft)).replace("PHASE", json.dumps(phase))

    def test_completed_tool_resume_sends_native_continue_once(self):
        self.run_js(r"""
await window.qwenRecovery.resume();await window.qwenRecovery.resume();
assert.equal(submissions,1);assert.equal(sessionData['qwen-stream-recovery-refresh-v1'],undefined);
assert.match(area.value,/recovered result/);
""", pre=self.composer_pre())

    def test_restore_refreshes_native_state_once_before_continuation(self):
        self.run_js(r"""
await window.qwenRecovery.resume();await window.qwenRecovery.resume();
assert.equal(reloads,1);assert.equal(submissions,0);
assert.equal(JSON.parse(sessionData['qwen-stream-recovery-refresh-v1']).phase,'continue');
""", pre=self.composer_pre(phase="refresh"))

    def test_draft_plan_stop_or_changed_ticket_prevents_auto_continue(self):
        cases = [(self.composer_pre(draft="User draft"), ""), (self.composer_pre(), "plan=true;"),
                 (self.composer_pre(), "settings.stopped=true;"),
                 (self.composer_pre(), "window.qwenRecoveryHistory.canContinue=async()=>false;")]
        for pre, setup in cases:
            with self.subTest(setup=setup, draft="User draft" in pre):
                self.run_js(setup + r"""
await window.qwenRecovery.resume();assert.equal(submissions,0);assert.equal(reloads,0);
assert.ok(sessionData['qwen-stream-recovery-refresh-v1']);
""", pre=pre)

    def test_other_tab_lease_pauses_then_expired_lease_resumes(self):
        self.run_js(r"""
let first=true;
behavior=req=>{server(req);if(first){first=false;localData['qwen-stream-recovery-lease:'+req.id]=JSON.stringify({owner:'other-tab',until:Date.now()+60000});throw new TypeError('lost');}return server(req);};
const pending=window.fetch('/tools',config());await pause(25);assert.equal(requests.length,1);
const id=requests[0].id;localData['qwen-stream-recovery-lease:'+id]=JSON.stringify({owner:'other-tab',until:Date.now()-1});emit('storage');
assert.deepEqual(await readAll(await pending),bytes(GOOD));assert.equal(executions,1);
""")


if __name__ == "__main__":
    unittest.main()
