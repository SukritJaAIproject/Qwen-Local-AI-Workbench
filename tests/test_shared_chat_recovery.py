"""Recover text copies without replacing native chats or replaying tool calls."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class SharedChatRecoveryTests(unittest.TestCase):
    def node(self, names, assertions):
        source = Path(r"C:\LLM\projects\static\shared-chats.js").read_text(encoding="utf-8")
        functions = "\n".join(re.search(r"^  (?:async )?function " + name + r"\([^\n]*\) \{.*?^  \}",
                                       source, re.M | re.S).group(0) for name in names)
        with tempfile.TemporaryDirectory(prefix="chat-recovery-test-") as folder:
            script = Path(folder) / "test.js"
            script.write_text("const assert=require('node:assert/strict');\n" + functions + "\n" + assertions,
                              encoding="utf-8")
            result = subprocess.run([r"C:\Program Files\nodejs\node.exe", str(script)],
                                    capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_complete_chain_and_historical_tool_text_cannot_be_pending_actions(self):
        self.node(["recoveredChatRecords"], r"""
const chat={chat_id:'original-id',title:'GPU history',updated_at:1000,messages:[
 {id:'old-user',role:'user',content:'Study the GPU logs',timestamp:10},
 {id:'old-assistant',role:'assistant',content:'[Recorded tool call data]\n{"arguments":"broken',timestamp:11},
 {id:'old-tool',role:'tool',content:'GPU ready',tool_call_id:'unpaired-call',timestamp:12}]};
const before=JSON.stringify(chat);let serial=0;
const recovered=recoveredChatRecords(chat,2000,()=>`new-${serial++}`);
assert.equal(JSON.stringify(chat),before);
assert.equal(recovered.conversation.id,chat.chat_id);
assert.equal(recovered.conversation.name,chat.title);
assert.equal(recovered.messages.length,4);
assert.equal(recovered.messages[0].type,'root');
assert.equal(recovered.messages[0].parent,null);
assert.equal(recovered.messages[1].content,chat.messages[0].content);
assert.equal(recovered.messages[2].content,chat.messages[1].content);
assert.equal(recovered.messages[3].role,'assistant');
assert.ok(recovered.messages[3].content.endsWith(chat.messages[2].content));
assert.ok(recovered.messages.every(m=>m.toolCalls===''&&!m.toolCallId&&!m.tool_calls));
for(let i=1;i<recovered.messages.length;i++){
 assert.equal(recovered.messages[i].parent,recovered.messages[i-1].id);
 assert.deepEqual(recovered.messages[i-1].children,[recovered.messages[i].id]);
 assert.equal(recovered.messages[i].convId,chat.chat_id);
}
assert.equal(recovered.conversation.currNode,recovered.messages.at(-1).id);
const missingTimes={...chat,messages:chat.messages.map(m=>({...m,timestamp:0}))};
const ordered=recoveredChatRecords(missingTimes,2000,()=>`ordered-${serial++}`);
for(let i=1;i<ordered.messages.length;i++) assert.ok(ordered.messages[i].timestamp>ordered.messages[i-1].timestamp);
assert.throws(()=>recoveredChatRecords({...chat,chat_id:'../other-project'},2000));
assert.throws(()=>recoveredChatRecords({...chat,messages:[{role:'user',content:'incomplete',text_truncated:true}]},2000));
assert.throws(()=>recoveredChatRecords({...chat,messages:[{role:'system',content:'Historical approval'}]},2000));
""")

    def test_pages_must_be_complete_and_from_one_snapshot_before_any_write(self):
        self.node(["recoveryCopy"], r"""
let mode='ok',reads=[];
async function api(url){
 const offset=Number(new URL('http://local'+url).searchParams.get('offset'));
 reads.push(offset);
 return {chat_id:mode==='wrong-project'?'different':'source',title:'GPU',updated_at:mode==='changed'&&offset?2000:1000,
  message_count:3,offset,messages:offset===0?[{role:'user',content:'one'},{role:'assistant',content:'two'}]:[
   {role:'assistant',content:'three',text_truncated:mode==='truncated'}],
  next_offset:offset===0?(mode==='gap'?1:2):null};
}
(async()=>{
 const record=await recoveryCopy('source');
 assert.equal(record.messages.length,3);assert.deepEqual(reads,[0,2]);
 for(const invalid of ['changed','gap','truncated','wrong-project']){
  mode=invalid;await assert.rejects(()=>recoveryCopy('source'));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_existing_native_chat_is_returned_without_any_add_or_overwrite(self):
        self.node(["saveRecoveredChat"], r"""
const existing={id:'source',name:'User edited title',currNode:'newest-native-message'};
let closed=false,adds=0;
async function openDB(){return {
 close(){closed=true;},
 transaction(stores,mode){
  assert.deepEqual(stores,['conversations','messages']);assert.equal(mode,'readwrite');
  const tx={objectStore(){return {
   get(){const request={result:existing};queueMicrotask(()=>{request.onsuccess();queueMicrotask(()=>tx.oncomplete());});return request;},
   add(){adds++;throw new Error('Existing chat must not be written');}
  };}};return tx;
 }
};}
(async()=>{
 const restored=await saveRecoveredChat({conversation:{id:'source',name:'Old title'},messages:[{content:'old text'}]});
 assert.equal(restored,existing);assert.equal(adds,0);assert.equal(closed,true);
 assert.equal(existing.name,'User edited title');assert.equal(existing.currNode,'newest-native-message');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


if __name__ == "__main__":
    unittest.main()
