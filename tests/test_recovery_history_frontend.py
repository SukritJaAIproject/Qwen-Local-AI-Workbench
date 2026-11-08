"""Completed transport journals may merge only into the unchanged owning branch."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HELPER = Path(r"C:\LLM\projects\static\recovery-history.js")
NODE = shutil.which("node")

ENV = r"""
const assert = require('node:assert/strict');
var window = {}, location = {origin:'http://127.0.0.1:8105'};
function cp(v){return JSON.parse(JSON.stringify(v));}
function fixture(kind='chat', count=1){
 const conversation={id:'chat-1',name:'Synthetic fixture',currNode:kind==='chat'?'u':'a',lastModified:100};
 const messages=[{id:'r',convId:'chat-1',role:'system',type:'root',parent:null,children:['u'],content:'',timestamp:1},
 {id:'u',convId:'chat-1',role:'user',type:'text',parent:'r',children:kind==='chat'?[]:['a'],content:'Inspect fixture',timestamp:2,extra:[]}];
 if(kind!=='chat')messages.push({id:'a',convId:'chat-1',role:'assistant',type:'text',parent:'u',children:[],content:'Checking',timestamp:3,
 toolCalls:JSON.stringify(Array.from({length:count},(_,i)=>({id:'call-'+i,type:'function',function:{name:'read_file',arguments:JSON.stringify({path:'fixture-'+i})}})))});
 return {conversation,messages};
}
function context(kind='chat',i=0){return {id:'journal-1',chat:'chat-1',project:'demo-b',origin:location.origin,epoch:'0',kind,
 body:JSON.stringify(kind==='chat'?{model:'test',messages:[{role:'user',content:'Inspect fixture'}]}:
 kind==='tools'?{tool:'read_file',params:{path:'fixture-'+i},stream:true}:
 {jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'read_file',arguments:{path:'fixture-'+i}}})};}
function env(){return {chat:'chat-1',project:'demo-b',origin:location.origin,epoch:'0',now:1000};}
function final(content='Complete fixture',reason='stop'){return {status:200,contentType:'text/event-stream',text:
 'data: '+JSON.stringify({choices:[{delta:{content},finish_reason:null}]})+'\n\n'+
 'data: '+JSON.stringify({choices:[{delta:{},finish_reason:reason}]})+'\n\ndata: [DONE]\n\n'};}
function toolOutput(output='File fixture'){return {status:200,contentType:'text/event-stream',text:
 'data: '+JSON.stringify({chunk:output})+'\n\ndata: {"done":true}\n\n'};}
function record(snapshot,kind='chat',i=0){const c=context(kind,i);return {...c,binding:p.capture(snapshot,c)};}
function applied(snapshot,result){const out=cp(snapshot);out.conversation=result.conversation;
 for(const m of result.messages){const i=out.messages.findIndex(x=>x.id===m.id);if(i<0)out.messages.push(m);else out.messages[i]=m;}
 return out;}
function savedTool(snapshot,index=0,content='Previous fixture'){
 const a=snapshot.messages.find(x=>x.id==='a'),id='t-'+index;
 a.children.push(id);snapshot.messages.push({id,convId:'chat-1',role:'tool',type:'text',parent:'a',children:[],content,toolCalls:'',toolCallId:'call-'+index,timestamp:4+index});
 snapshot.conversation.currNode=id;return snapshot;
}
"""


@unittest.skipUnless(NODE, "Node is required")
class RecoveryHistoryFrontendTests(unittest.TestCase):
    def run_js(self, case):
        code = ENV + HELPER.read_text(encoding="utf-8") + "\nconst p=window.qwenRecoveryHistory.planner;\n" + case + "\nconsole.log(JSON.stringify({ok:true}));"
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as script:
            script.write(code)
            name = script.name
        try:
            completed = subprocess.run([NODE, name], capture_output=True, text=True, encoding="utf-8", timeout=20)
        finally:
            Path(name).unlink(missing_ok=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {"ok": True})

    def test_complete_final_answer_is_saved_once_without_another_generation(self):
        self.run_js(r"""
const s=fixture(),r=record(s),before=JSON.stringify(s),out=p.restore(s,r,final(),env());
assert.ok(out.restored);assert.equal(out.continue,false);assert.equal(out.reload,true);
assert.equal(out.messages.at(-1).content,'Complete fixture');assert.equal(out.messages.at(-1).toolCalls,'');
assert.equal(JSON.stringify(s),before);
const restored=applied(s,out),again=p.restore(restored,r,final(),env());
assert.equal(again.already,true);assert.equal(again.continue,false);assert.equal(again.messages,undefined);
""")

    def test_truncated_generation_may_continue_only_on_exact_restored_branch(self):
        self.run_js(r"""
const s=fixture(),r=record(s),out=p.restore(s,r,final('Partial fixture','length'),env()),native=applied(s,out);
assert.equal(out.continue,true);assert.ok(p.canContinue(native,out.continuation,env()));
const moved=cp(native);moved.conversation.currNode='u';assert.equal(p.canContinue(moved,out.continuation,env()),false);
for(const change of [{epoch:'stopped'},{project:'demo-c'},{chat:'other'},{deleted:true},{streaming:true},{stopped:true}])
 assert.equal(p.canContinue(native,out.continuation,{...env(),...change}),false);
""")

    def test_completed_generation_calls_are_archived_and_never_executable(self):
        self.run_js(r"""
const s=fixture(),r=record(s),reply={status:200,contentType:'application/json',text:JSON.stringify({choices:[{message:{content:'Review pending',tool_calls:[{id:'call-0',function:{name:'exec_shell_command',arguments:'{"command":"do not execute"}'}}]},finish_reason:'tool_calls'}]})};
const out=p.restore(s,r,reply,env());assert.ok(out.restored);assert.equal(out.continue,false);assert.equal(out.pendingPermission,true);
assert.equal(out.messages.at(-1).toolCalls,'');assert.match(out.messages.at(-1).content,/not executed/);
""")

    def test_completed_native_command_result_binds_to_original_call(self):
        self.run_js(r"""
const s=fixture('tools'),r=record(s,'tools'),out=p.restore(s,r,toolOutput(),env());
assert.ok(out.restored);assert.equal(out.continue,true);const saved=out.messages.find(x=>x.role==='tool');
assert.equal(saved.parent,'a');assert.equal(saved.toolCallId,'call-0');assert.equal(saved.content,'File fixture');
const native=applied(s,out);assert.ok(p.canContinue(native,out.continuation,env()));
assert.equal(p.restore(native,r,toolOutput(),env()).continue,false);
""")

    def test_a_result_already_saved_by_native_ui_is_not_duplicated(self):
        self.run_js(r"""
const s=fixture('tools'),r=record(s,'tools');savedTool(s,0,'File fixture');
const out=p.restore(s,r,toolOutput(),env());assert.ok(out.restored);assert.equal(out.continue,true);assert.equal(out.messages.length,0);
assert.equal(out.conversation.currNode,'t-0');
const changed=cp(s);changed.messages.at(-1).content='Different result';
assert.equal(p.restore(changed,r,toolOutput(),env()).reason,'tool_result_changed');
""")

    def test_second_call_uses_sibling_results_instead_of_wrong_parent_chain(self):
        self.run_js(r"""
const s=savedTool(fixture('tools',2)),r=record(s,'tools',1);assert.ok(r.binding);
const out=p.restore(s,r,toolOutput(),env());assert.equal(out.continue,true);assert.equal(out.messages.at(-1).toolCallId,'call-1');
assert.deepEqual(out.messages[0].children,['t-0','recovery-journal-1']);
""")

    def test_unapproved_remaining_sibling_call_blocks_automatic_continuation(self):
        self.run_js(r"""
const s=fixture('tools',2),r=record(s,'tools'),out=p.restore(s,r,toolOutput(),env());
assert.ok(out.restored);assert.equal(out.pendingPermission,true);assert.equal(out.continue,false);assert.equal(out.continuation,undefined);
assert.equal(out.messages.filter(x=>x.role==='tool').length,1);
""")

    def test_mcp_text_result_can_be_saved_but_not_attachment_or_error_envelope(self):
        self.run_js(r"""
const s=fixture('mcp'),r=record(s,'mcp');
const response={status:200,contentType:'application/json',text:JSON.stringify({jsonrpc:'2.0',id:1,result:{content:[{type:'text',text:'One'},{type:'text',text:'Two'}]}})};
const out=p.restore(s,r,response,env());assert.equal(out.messages.at(-1).content,'One\nTwo');assert.equal(out.continue,true);
for(const doc of [{error:{code:-1}}, {result:{content:[{type:'image',data:'fake'}]}}]){
 assert.equal(p.restore(s,r,{...response,text:JSON.stringify(doc)},env()).restored,false);
}
""")

    def test_stop_delete_project_route_epoch_and_streaming_changes_block_restore(self):
        self.run_js(r"""
const s=fixture(),r=record(s);
for(const change of [{stopped:true},{deleted:true},{project:'demo-c'},{chat:'other'},{origin:'http://other'},{epoch:'1'},{streaming:true}]){
 const out=p.restore(s,r,final(),{...env(),...change});assert.equal(out.restored,false);assert.equal(out.continue,false);
}
assert.equal(p.restore(s,{...r,stopped:true},final(),env()).restored,false);
""")

    def test_new_user_message_or_branch_cannot_receive_old_completion(self):
        self.run_js(r"""
const s=fixture(),r=record(s),changed=cp(s);
changed.messages.find(m=>m.id==='u').children.push('new');changed.messages.push({id:'new',convId:'chat-1',role:'user',type:'text',parent:'u',children:[],content:'New task'});changed.conversation.currNode='new';
assert.equal(p.restore(changed,r,final(),env()).restored,false);
changed.messages.at(-1).role='assistant';changed.messages.at(-1).content='Complete';
assert.equal(p.restore(changed,r,final(),env()).restored,false);
""")

    def test_changed_user_content_attachment_or_tool_arguments_are_not_overwritten(self):
        self.run_js(r"""
for(const edit of [m=>m.content='Edited task',m=>m.extra=[{type:'image',data:'new fixture'}]]){
 const s=fixture(),r=record(s);edit(s.messages[1]);assert.equal(p.restore(s,r,final(),env()).restored,false);
}
const t=fixture('tools'),r=record(t,'tools');t.messages[2].toolCalls=t.messages[2].toolCalls.replace('fixture-0','fixture-changed');
assert.equal(p.restore(t,r,toolOutput(),env()).restored,false);
""")

    def test_request_body_and_generation_user_must_match_native_owner(self):
        self.run_js(r"""
const s=fixture(),c=context();c.body=JSON.stringify({messages:[{role:'user',content:'Another request'}]});assert.equal(p.capture(s,c),null);
const r=record(s);r.body=r.body.replace('Inspect fixture','Another request');assert.equal(p.restore(s,r,final(),env()).reason,'request_changed');
const t=fixture('tools'),tc=context('tools');tc.body=JSON.stringify({tool:'read_file',params:{path:'another'}});assert.equal(p.capture(t,tc),null);
""")

    def test_incomplete_stream_finish_error_or_non_200_never_looks_complete(self):
        self.run_js(r"""
const s=fixture(),r=record(s),good=final();
for(const response of [{...good,status:500},{...good,text:good.text.replace('data: [DONE]\n\n','')},
 {status:200,contentType:'text/event-stream',text:'data: {"choices":[{"delta":{"content":"partial"}}]}\n\ndata: [DONE]\n\n'},
 {status:200,contentType:'text/event-stream',text:'data: {"error":"failed"}\n\ndata: [DONE]\n\n'}])
 assert.equal(p.restore(s,r,response,env()).restored,false);
const t=fixture('tools'),tr=record(t,'tools'),broken=toolOutput();broken.text=broken.text.replace('data: {"done":true}\n\n','');assert.equal(p.restore(t,tr,broken,env()).restored,false);
""")

    def test_duplicate_call_ids_missing_children_and_broken_chains_pause(self):
        self.run_js(r"""
const s=fixture('tools',2);s.messages[2].toolCalls=s.messages[2].toolCalls.replace('call-1','call-0');assert.equal(record(s,'tools').binding,null);
const missing=fixture('tools');missing.messages[2].children=['absent'];assert.equal(record(missing,'tools').binding,null);
const cycle=fixture();cycle.messages[0].parent='u';assert.equal(record(cycle).binding,null);
const wrong=savedTool(fixture('tools',2));wrong.messages.at(-1).toolCallId='call-1';assert.equal(record(wrong,'tools',1).binding,null);
""")

    def test_sibling_result_changes_and_extra_branches_block_tool_merge(self):
        self.run_js(r"""
const s=savedTool(fixture('tools',2)),r=record(s,'tools',1);s.messages.at(-1).content='Other operation';
assert.equal(p.restore(s,r,toolOutput(),env()).restored,false);
const t=fixture('tools'),tr=record(t,'tools');t.messages[2].children.push('other');t.messages.push({id:'other',convId:'chat-1',role:'assistant',parent:'a',children:[],content:'Other branch'});t.conversation.currNode='other';
assert.equal(p.restore(t,tr,toolOutput(),env()).restored,false);
""")

    def test_fragmented_unicode_sse_and_reasoning_are_preserved(self):
        self.run_js(r"""
const s=fixture(),r=record(s),raw='data: '+JSON.stringify({choices:[{delta:{content:'ข้อมูล ',reasoning_content:'Reasoning '}}]})+'\r\n\r\n'+
 'data: '+JSON.stringify({choices:[{delta:{content:'พร้อมแล้ว',reasoning_content:'saved'},finish_reason:'stop'}]})+'\r\n\r\ndata: [DONE]\r\n\r\n';
const out=p.restore(s,r,{status:200,contentType:'text/event-stream',text:raw},env());assert.equal(out.messages.at(-1).content,'ข้อมูล พร้อมแล้ว');assert.equal(out.messages.at(-1).reasoningContent,'Reasoning saved');
""")

    def test_exact_late_native_final_answer_is_adopted_without_duplicate_node(self):
        self.run_js(r"""
const s=fixture(),r=record(s);s.messages[1].children=['late'];s.messages.push({id:'late',convId:'chat-1',parent:'u',children:[],role:'assistant',type:'text',content:'Complete fixture',toolCalls:'',timestamp:5});s.conversation.currNode='late';
const out=p.restore(s,r,final(),env());assert.equal(out.restored,true);assert.equal(out.messages.length,1);assert.equal(out.messages[0].id,'late');assert.equal(out.continue,false);
""")

    def test_mcp_error_result_is_recorded_as_error_context_without_reexecution(self):
        self.run_js(r"""
const s=fixture('mcp'),r=record(s,'mcp'),out=p.restore(s,r,{status:200,contentType:'application/json',text:JSON.stringify({result:{isError:true,content:[{type:'text',text:'Fixture failed'}]}})},env());
assert.ok(out.restored);assert.match(out.messages.at(-1).content,/Recovered tool error/);assert.equal(out.continue,true);
""")

    def test_delivered_journal_is_not_acknowledged_until_exact_native_save(self):
        self.run_js(r"""
const s=fixture(),r=record(s),reply=final();assert.equal(p.acknowledge(s,r,reply,env()),false);
s.messages[1].children.push('native');s.messages.push({id:'native',convId:'chat-1',parent:'u',children:[],role:'assistant',type:'text',content:'Complete fixture',toolCalls:'',timestamp:5});s.conversation.currNode='native';
assert.equal(p.acknowledge(s,r,reply,env()),true);s.messages.at(-1).content='Partial';assert.equal(p.acknowledge(s,r,reply,env()),false);
""")

    def test_native_saved_tool_generation_is_acknowledged_before_permission_result(self):
        self.run_js(r"""
const s=fixture(),r=record(s),call={id:'call-0',type:'function',function:{name:'read_file',arguments:'{"path":"fixture-0"}'}},reply={status:200,contentType:'application/json',text:JSON.stringify({choices:[{message:{content:'',tool_calls:[call]},finish_reason:'tool_calls'}]})};
assert.equal(p.acknowledge(s,r,reply,env()),false);
s.messages[1].children.push('a');s.messages.push({id:'a',convId:'chat-1',parent:'u',children:[],role:'assistant',type:'text',content:'',toolCalls:JSON.stringify([call]),timestamp:5});s.conversation.currNode='a';
assert.equal(p.acknowledge(s,r,reply,env()),true);
savedTool(s,0,'File fixture');assert.equal(p.acknowledge(s,r,reply,env()),true);
""")

    def test_acknowledgment_accepts_exact_tool_after_agent_advances_but_rejects_changes(self):
        self.run_js(r"""
const s=fixture('tools'),r=record(s,'tools'),reply=toolOutput();assert.equal(p.acknowledge(s,r,reply,env()),false);
savedTool(s,0,'File fixture');s.messages.at(-1).children=['next'];s.messages.push({id:'next',convId:'chat-1',parent:'t-0',children:[],role:'assistant',content:'Final fixture'});s.conversation.currNode='next';
assert.equal(p.acknowledge(s,r,reply,env()),true);
assert.equal(p.acknowledge(s,r,reply,{...env(),epoch:'1'}),false);
s.messages.find(m=>m.id==='t-0').content='Other fixture';assert.equal(p.acknowledge(s,r,reply,env()),false);
""")

    def test_bodyless_authenticated_result_record_uses_capture_digest(self):
        self.run_js(r"""
const s=fixture(),r=record(s);r.requestHash=r.binding.bodyHash;delete r.body;
assert.equal(p.restore(s,r,final(),env()).restored,true);r.requestHash='wrong';assert.equal(p.restore(s,r,final(),env()).restored,false);
""")

    def test_native_mcp_sse_accepts_one_text_reply_and_pauses_ambiguous_replies(self):
        self.run_js(r"""
const s=fixture('mcp'),r=record(s,'mcp'),event={jsonrpc:'2.0',id:1,result:{content:[{type:'text',text:'MCP SSE fixture'}]}},response={status:200,contentType:'text/event-stream',text:'event: message\ndata: '+JSON.stringify(event)+'\n\n'};
const out=p.restore(s,r,response,env());assert.ok(out.restored);assert.equal(out.messages.at(-1).content,'MCP SSE fixture');assert.equal(out.continue,true);
assert.equal(p.restore(s,r,{...response,text:response.text+response.text},env()).restored,false);
assert.equal(p.restore(s,r,{...response,text:'data: '+JSON.stringify({jsonrpc:'2.0',id:1,error:{code:-1,message:'Fixture error'}})+'\n\n'},env()).restored,false);
""")

    def test_live_reattach_uses_exact_generation_tip_and_denies_new_branches(self):
        self.run_js(r"""
const s=fixture(),r=record(s);assert.ok(p.canAttach(s,r.binding,env()));
assert.equal(p.canAttach(s,r.binding,{...env(),epoch:'1'}),false);
s.messages[1].children.push('unknown');s.messages.push({id:'unknown',convId:'chat-1',parent:'u',children:[],role:'assistant',content:'Partial fixture',toolCalls:''});s.conversation.currNode='unknown';
assert.equal(p.canAttach(s,r.binding,env()),false);
""")

    def test_original_partial_assistant_can_update_without_loosening_identity(self):
        self.run_js(r"""
const s=fixture();s.messages[1].children=['partial'];s.messages.push({id:'partial',convId:'chat-1',parent:'u',children:[],role:'assistant',type:'text',content:'',toolCalls:'',timestamp:3});s.conversation.currNode='partial';
const r=record(s);assert.ok(r.binding);s.messages.at(-1).content='Ongoing original response';s.messages.at(-1).timestamp=20;assert.ok(p.canAttach(s,r.binding,env()));
s.messages[1].content='Changed task';assert.equal(p.canAttach(s,r.binding,env()),false);
""")

    def test_tool_reattach_requires_exact_completed_siblings_and_pending_tip(self):
        self.run_js(r"""
const s=savedTool(fixture('tools',2)),r=record(s,'tools',1);assert.ok(p.canAttach(s,r.binding,env()));
const altered=cp(s);altered.messages.at(-1).content='Modified first result';assert.equal(p.canAttach(altered,r.binding,env()),false);
savedTool(s,1,'Second result');assert.equal(p.canAttach(s,r.binding,env()),false);
assert.equal(p.canAttach(s,r.binding,{...env(),deleted:true}),false);
""")


if __name__ == "__main__":
    unittest.main()
