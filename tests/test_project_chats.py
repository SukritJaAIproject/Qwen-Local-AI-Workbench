"""Exercise project chat creation and nested sidebar behavior without user data."""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

PARTS = Path(r"C:\LLM\projects\hub_i18n_parts.py")
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
spec = importlib.util.spec_from_file_location("project_chat_parts", PARTS)
parts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parts)


def js_function(name):
    match = re.search(r"^function " + re.escape(name) + r"\([^\n]*\) \{.*?^\}", parts.SHELL, re.M | re.S)
    if not match:
        raise AssertionError("missing function " + name)
    return match.group(0)


def run_js(code):
    with tempfile.TemporaryDirectory(prefix="project-chat-test-") as task_dir:
        source = Path(task_dir) / "test.js"
        source.write_text("const assert = require('node:assert/strict');\n" + code, encoding="utf-8")
        result = subprocess.run([NODE, str(source)], capture_output=True, text=True, encoding="utf-8", timeout=20)
    if result.returncode:
        raise AssertionError(result.stderr)


ENV = r"""
var ME=8105, PROJECTS=[{slug:'demo-b',name:'Demo B',port:8105},{slug:'other',name:'Other',port:8106}];
var CONVS=[{id:'existing',name:'Existing'}], projectChatBusy=false, lastRecSig='', uiStale=false;
var assignments=[], calls=[], buttons=[{disabled:false}], enteredName='Named chat', shouldFail=false;
var location={assign:u=>assignments.push(u)};
function portUrl(p){return 'http://127.0.0.1:'+p+'/';}
function closeMenu(){calls.push('closeMenu');}
function fmt(s,v){return s.replace('%s',v);}
function t(k){return k==='project_new_chat_title'?'Create chat in %s':k;}
function tRaw(k){return k;}
function openDialog(o){calls.push(o);return Promise.resolve(enteredName);}
var projList={querySelectorAll:()=>buttons};
function saveProjectChat(name){calls.push(['save',name]);return shouldFail?Promise.reject(new Error('quota')):Promise.resolve({id:'new-id',name:name});}
function expandProjectChats(on){calls.push(['expand',on]);}
function openChat(id){calls.push(['open',id]);}
function renderRecents(){calls.push('render');}
function streaming(){return false;}
function hasDraft(){return false;}
function reloadFrame(h){calls.push(['reload',h]);}
function callEnh(){}
function setTimeout(){}
function toast(msg,bad){calls.push(['toast',msg,!!bad]);}
"""


class ProjectChatTests(unittest.TestCase):
    def test_project_disclosure_uses_current_shell_metadata_and_persists(self):
        run_js(js_function("projectChatsExpanded") + "\n" + js_function("expandProjectChats") + r"""
var PROJ={slug:'demo-b'}, values={}, renders=0, lastProjSig='old';
var localStorage={getItem:k=>values[k]||null,setItem:(k,v)=>{values[k]=v;}};
function renderProjects(){renders++;}
assert.equal(projectChatsExpanded(),true);
expandProjectChats(false);
assert.equal(projectChatsExpanded(),false);
assert.equal(values['qwen-project-chats-collapsed:demo-b'],'1');
PROJ.name='Renamed';assert.equal(projectChatsExpanded(),false);
PROJ.slug='other';assert.equal(projectChatsExpanded(),true);
PROJ.slug='demo-b';expandProjectChats(true);
assert.equal(projectChatsExpanded(),true);assert.equal(renders,2);
assert.equal(lastProjSig,'');
""")

    def test_destination_request_waits_for_frame_and_runs_once_for_that_project(self):
        run_js(js_function("consumeProjectChatRequest") + r"""
var PROJ={slug:'destination'}, projectChatRequested=true, callbacks=[], created=[];
function setTimeout(fn){callbacks.push(fn);}
function newProjectChat(slug){created.push(slug);}
assert.equal(consumeProjectChatRequest(false),false);
assert.equal(projectChatRequested,true);assert.equal(callbacks.length,0);
assert.equal(consumeProjectChatRequest(true),true);
assert.equal(projectChatRequested,false);
assert.equal(consumeProjectChatRequest(true),false);
assert.equal(callbacks.length,1);callbacks[0]();
assert.deepEqual(created,['destination']);
""")

    def test_empty_chat_has_native_root_and_stable_name(self):
        run_js(js_function("projectChatRecords") + r"""
const r=projectChatRecords('แชต <script>name</script>',123,['c','root','sys'],{},{});
assert.deepEqual(r.conversation,{id:'c',name:'แชต <script>name</script>',lastModified:123,currNode:'root'});
assert.equal(r.messages.length,1);
assert.deepEqual(r.messages[0],{id:'root',convId:'c',parent:null,children:[],content:'',role:'system',type:'root',timestamp:123,toolCalls:''});
""")

    def test_system_prompt_and_tool_preferences_survive_creation(self):
        run_js(js_function("projectChatRecords") + r"""
const config={systemMessage:'  Keep the project instructions.  '};
const policy={disabledTools:['server:exec_shell_command'],disabledToolCategories:['browser'],reasoningEffort:'high'};
const before=JSON.stringify({config,policy});
const r=projectChatRecords('Named',456,['c','root','sys'],config,policy);
assert.equal(JSON.stringify({config,policy}),before);
assert.equal(r.conversation.currNode,'sys');
assert.deepEqual(r.conversation.disabledTools,['server:exec_shell_command']);
assert.deepEqual(r.conversation.disabledToolCategories,['browser']);
assert.equal(r.conversation.reasoningEffort,'high');
assert.deepEqual(r.messages[0].children,['sys']);
assert.equal(r.messages[1].parent,'root');
assert.equal(r.messages[1].convId,'c');
assert.equal(r.messages[1].content,'Keep the project instructions.');
assert.deepEqual(r.messages[1].children,[]);
assert.equal(r.messages[1].type,'system');
""")

    def test_settings_use_native_keys_and_handle_invalid_storage(self):
        run_js(js_function("projectChatSettings") + r"""
var values={'LlamaUi.config':'{"systemMessage":"Saved prompt"}','LlamaUi.disabledToolKeys':'["server:write_file"]',
 'LlamaUi.disabledToolCategories':'["browser"]','LlamaUi.reasoningEffortDefault':'"off"'};
var localStorage={getItem:k=>values[k]||null};
assert.deepEqual(projectChatSettings(),{config:{systemMessage:'Saved prompt'},policy:{disabledTools:['server:write_file'],disabledToolCategories:['browser'],reasoningEffort:'off'}});
values={'LlamaUi.config':'{broken','LlamaUi.disabledToolKeys':'invalid'};
assert.deepEqual(projectChatSettings(),{config:{},policy:{disabledTools:[],disabledToolCategories:[],reasoningEffort:'default'}});
""")

    def test_creation_adds_conversation_and_messages_in_one_transaction(self):
        run_js(js_function("projectChatRecords") + "\n" + js_function("saveProjectChat") + r"""
var crypto={randomUUID:(()=>{let i=0;return()=>['new-conv','root','sys'][i++];})()};
var writes=[], transactions=[], existing={id:'existing',name:'Do not replace'};
function projectChatSettings(){return {config:{systemMessage:'System'},policy:{}};}
function txDone(tx){return Promise.resolve();}
function reqP(r){return r;}
var db={objectStoreNames:{contains:()=>true},transaction:(names,mode)=>{
 transactions.push([names,mode]);return {objectStore:name=>({add:value=>{writes.push([name,value]);return Promise.resolve(value.id);}})};
}};
function withDB(fn){return Promise.resolve().then(()=>fn(db));}
(async()=>{
 const c=await saveProjectChat('Saved');
 assert.equal(c.name,'Saved');
 assert.deepEqual(transactions,[[['conversations','messages'],'readwrite']]);
 assert.deepEqual(writes.map(w=>w[0]),['conversations','messages','messages']);
 assert.equal(writes[0][1].id,'new-conv');
 assert.equal(writes[1][1].convId,c.id);
 assert.equal(writes[2][1].convId,c.id);
 assert.deepEqual(existing,{id:'existing',name:'Do not replace'});
 db.objectStoreNames.contains=()=>false;
 await assert.rejects(()=>saveProjectChat('Not ready'),/not ready/);
 assert.equal(transactions.length,1);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_foreign_project_navigates_before_any_write_or_dialog(self):
        run_js(ENV + js_function("newProjectChat") + r"""
(async()=>{
 assert.equal(await newProjectChat('other'),true);
 assert.deepEqual(assignments,['http://127.0.0.1:8106/?newchat=1']);
 assert.deepEqual(calls,[]);
 assert.deepEqual(CONVS,[{id:'existing',name:'Existing'}]);
 assert.equal(await newProjectChat('missing'),false);
 assert.equal(assignments.length,1);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_cancel_failure_and_busy_do_not_create_or_open_chat(self):
        run_js(ENV + js_function("newProjectChat") + r"""
(async()=>{
 enteredName=null;
 assert.equal(await newProjectChat('demo-b'),false);
 assert.ok(!calls.some(v=>Array.isArray(v)&&['save','open'].includes(v[0])));
 assert.equal(projectChatBusy,false);assert.equal(buttons[0].disabled,false);
 calls=[];enteredName='Name';shouldFail=true;
 assert.equal(await newProjectChat('demo-b'),false);
 assert.ok(!calls.some(v=>Array.isArray(v)&&v[0]==='open'));
 assert.deepEqual(CONVS,[{id:'existing',name:'Existing'}]);
 assert.ok(calls.some(v=>Array.isArray(v)&&v[0]==='toast'&&v[2]===true));
 calls=[];projectChatBusy=true;
 assert.equal(await newProjectChat('demo-b'),false);assert.deepEqual(calls,[]);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_success_preserves_existing_history_and_selects_new_chat(self):
        run_js(ENV + js_function("newProjectChat") + r"""
(async()=>{
 enteredName='  ชื่อแชต  ';
 assert.equal(await newProjectChat('demo-b'),'new-id');
 assert.deepEqual(CONVS,[{id:'new-id',name:'ชื่อแชต'},{id:'existing',name:'Existing'}]);
 assert.ok(calls.some(v=>Array.isArray(v)&&v[0]==='open'&&v[1]==='new-id'));
 assert.ok(calls.some(v=>Array.isArray(v)&&v[0]==='expand'&&v[1]===true));
 assert.equal(projectChatBusy,false);assert.equal(buttons[0].disabled,false);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_nested_keyboard_lists_keep_independent_tab_stops(self):
        run_js(js_function("listNodes") + "\n" + js_function("setRoving") + r"""
function link(owner,on=false){return {owner,tab:null,closest:()=>owner,classList:{contains:()=>on}};}
function setAttr(n,k,v){n.tab=v;}
var parent={querySelectorAll:()=>[p1,p2,c1]},child={querySelectorAll:()=>[c1,c2]};
var p1=link(parent),p2=link(parent,true),c1=link(child,true),c2=link(child);
setRoving(parent,null);assert.equal(p1.tab,'-1');assert.equal(p2.tab,'0');assert.equal(c1.tab,null);
setRoving(child,null);assert.equal(c1.tab,'0');assert.equal(c2.tab,'-1');assert.equal(p2.tab,'0');
setRoving(parent,c1);assert.equal(p2.tab,'0');assert.equal(c1.tab,'0');
""")


if __name__ == "__main__":
    unittest.main()
