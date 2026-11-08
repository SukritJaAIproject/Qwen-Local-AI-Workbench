"""Prove history survives browser loss, corrupt files, stale clients and streams."""
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, r"C:\LLM\projects")
import hub_chat_history as history
import test_b3_hub as fixture


def native(chat_id="chat", version=1000, answer="GPU ready"):
    return {"conversation": {"id": chat_id, "name": "GPU history", "lastModified": version, "currNode": "answer"},
            "messages": [{"id": "root", "convId": chat_id, "parent": None, "children": ["user"], "role": "system", "type": "root", "content": ""},
                         {"id": "user", "convId": chat_id, "parent": "root", "children": ["answer"], "role": "user", "type": "text", "content": "Review GPU"},
                         {"id": "answer", "convId": chat_id, "parent": "user", "children": [], "role": "assistant", "type": "text", "content": answer,
                          "reasoningContent": "Private reasoning", "extra": [{"type": "image", "data": "SAVED_IMAGE"}]}]}


class DurableVaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="durable-chat-")
        self.vault = history.Vault(self.temp.name, "demo-a", 8102)

    def tearDown(self):
        self.temp.cleanup()

    def test_native_copy_keeps_branches_reasoning_and_attachments_after_restart(self):
        data = native()
        data["messages"].append({"id": "alternate", "convId": "chat", "parent": "user", "children": [], "role": "assistant", "content": "Other branch"})
        before = copy.deepcopy(data)
        self.vault.save_native(data)
        restarted = history.Vault(self.temp.name, "demo-a", 8102)
        copy_ = restarted.read("chat")
        self.assertEqual(data, before)
        self.assertEqual(copy_["conversation"], data["conversation"])
        self.assertEqual({m["id"] for m in copy_["messages"]}, {m["id"] for m in data["messages"]})
        answer = next(m for m in copy_["messages"] if m["id"] == "answer")
        self.assertEqual(answer["reasoningContent"], "Private reasoning")
        self.assertEqual(answer["extra"][0]["data"], "SAVED_IMAGE")

    def test_other_project_and_path_traversal_cannot_read_history(self):
        self.vault.save_native(native())
        other = history.Vault(self.temp.name, "demo-b", 8105)
        with self.assertRaises(KeyError):
            other.read("chat")
        for bad in ("../demo-a", "a/b", "C:\\secret", ""):
            with self.assertRaises(ValueError):
                self.vault.read(bad)

    def test_empty_and_incomplete_browser_copy_cannot_replace_saved_history(self):
        self.vault.save_native(native())
        before = self.vault.read("chat")["revision"]
        empty = native(version=3000)
        empty["messages"] = empty["messages"][:1]
        empty["conversation"]["currNode"] = "root"
        self.assertEqual(self.vault.save_native(empty, before)["state"], "protected-empty")
        self.assertEqual(self.vault.read("chat")["revision"], before)
        invalid = native(version=4000)
        invalid["messages"] = invalid["messages"][:2]
        with self.assertRaises(ValueError):
            self.vault.save_native(invalid, before)
        self.assertEqual(self.vault.read("chat")["revision"], before)

    def test_short_native_copy_cannot_displace_longer_server_history(self):
        self.vault.save_fallback("chat", [{"role": "user", "content": "one"}, {"role": "assistant", "content": "two"},
                                         {"role": "user", "content": "three"}], updated_at=1000)
        self.assertEqual(self.vault.save_native(native(version=3000))["state"], "protected-partial")
        self.assertEqual(len(self.vault.read("chat")["messages"]), 3)

    def test_stale_or_unknown_client_is_preserved_without_overwriting_latest(self):
        first = self.vault.save_native(native())
        changed = self.vault.save_native(native(version=2000, answer="New answer"), first["revision"])
        stale = self.vault.save_native(native(version=1000, answer="Old answer"), changed["revision"])
        self.assertEqual(stale["state"], "conflict")
        self.assertEqual(self.vault.read("chat")["revision"], changed["revision"])
        unknown = self.vault.save_native(native(version=5000, answer="Other browser"))
        self.assertEqual(unknown["state"], "conflict")
        alternate = next(v for v in self.vault.versions("chat")["versions"] if v["conflict"])
        self.assertEqual(self.vault.read("chat", alternate["revision"])["source"], "native")

    def test_corrupt_latest_file_recovers_verified_revision(self):
        self.vault.save_native(native())
        latest = self.vault.folder("chat") / "latest-native.json"
        latest.write_text('{"broken":', encoding="utf-8")
        self.assertEqual(self.vault.read("chat")["title"], "GPU history")
        self.assertEqual(len(self.vault.read("chat")["messages"]), 3)

    def test_archive_hides_chat_but_keeps_copy_and_can_be_recovered(self):
        self.vault.save_native(native())
        self.vault.set_archived("chat", True)
        self.assertEqual(self.vault.list()["total"], 0)
        self.assertEqual(self.vault.list(True)["total"], 1)
        self.assertEqual(self.vault.save_native(native(version=4000))["state"], "archived")
        self.vault.set_archived("chat", False)
        self.assertEqual(self.vault.list()["total"], 1)

    def test_revision_retention_keeps_latest_readable_history(self):
        revision = None
        for i in range(history.KEEP_REVISIONS + 5):
            result = self.vault.save_native(native(version=1000 + i, answer=str(i)), revision)
            revision = result["revision"]
        versions = list((self.vault.folder("chat") / "revisions-native").glob("*.json.gz"))
        self.assertEqual(len(versions), history.KEEP_REVISIONS)
        self.assertEqual(self.vault.read("chat")["revision"], revision)
        self.assertTrue(list((self.vault.folder("chat") / "daily-native").glob("*.json.gz")))

    def test_existing_text_references_are_migrated_without_changing_source(self):
        self.vault.refs.upsert({"id": "original", "name": "Original", "messages": [{"role": "user", "content": "SAVED ORIGINAL"}]})
        path = self.vault.refs.path("original")
        before = path.read_bytes()
        self.assertEqual(self.vault.list()["total"], 1)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.vault.read("original")["messages"][0]["content"], "SAVED ORIGINAL")

    def test_server_capture_saves_last_reply_and_fragmented_tool_arguments(self):
        capture = history.Capture(self.vault, "chat", [{"role": "user", "content": "Question"}], "Title")
        events = [
            {"choices": [{"delta": {"content": "Final "}}]},
            {"choices": [{"delta": {"content": "answer", "tool_calls": [{"index": 0, "id": "call", "function": {"name": "read_file", "arguments": '{"path":'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"file.txt"}'}}]}, "finish_reason": "tool_calls"}]}]
        raw = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events) + b"data: [DONE]\n\n"
        for i in range(0, len(raw), 7):
            capture.feed(raw[i:i + 7])
        capture.commit()
        saved = self.vault.read("chat")
        self.assertEqual(len(saved["messages"]), 2)
        self.assertIn("Final answer", saved["messages"][-1]["content"])
        self.assertIn("file.txt", saved["messages"][-1]["content"])
        self.assertTrue(saved["complete"])

    def test_capture_saves_partial_reply_and_freezes_history_before_prompt_injection(self):
        messages = [{"role": "user", "content": "Original question"}]
        capture = history.Capture(self.vault, "chat", messages, "Title")
        messages[0]["content"] = "Injected document data"
        capture.feed(b'data: {"choices":[{"delta":{"content":"Partial reply"}}]}\n\n')
        capture.commit()
        saved = self.vault.read("chat")
        self.assertEqual(saved["messages"][0]["content"], "Original question")
        self.assertEqual(saved["messages"][-1]["content"], "Partial reply")
        self.assertFalse(saved["complete"])

    def test_late_response_cannot_replace_a_newer_request(self):
        old = history.Capture(self.vault, "chat", [{"role": "user", "content": "Old question"}], "Title", False)
        self.vault.save_fallback("chat", [{"role": "user", "content": "New question"}], "Title")
        old.feed(b'{"choices":[{"message":{"content":"Old reply"},"finish_reason":"stop"}]}')
        old.commit()
        self.assertEqual(self.vault.read("chat")["messages"][0]["content"], "New question")
        self.assertTrue(any(v["conflict"] for v in self.vault.versions("chat")["versions"]))


class DurableProxyTests(fixture._Env):
    ctx = 131072

    def backup_request(self, method, suffix, doc=None, origin=None):
        headers = {"Origin": origin or self.own}
        body = None
        if doc is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(doc).encode()
        return fixture._req(self.port, method, "/_qwen/chats/" + suffix, headers, body)

    def test_native_backup_routes_and_cross_project_guard(self):
        status, _, raw = self.backup_request("POST", "backup", native())
        self.assertEqual(status, 200)
        revision = json.loads(raw)["revision"]
        status, _, raw = self.backup_request("GET", "backups/chat")
        self.assertEqual(json.loads(raw)["revision"], revision)
        self.assertEqual(self.backup_request("GET", "backups/chat", origin="http://127.0.0.1:8102")[0], 403)
        self.assertEqual(self.backup_request("GET", "backups/../other")[0], 400)

    def test_legacy_missing_id_delete_cannot_hide_copy(self):
        self.backup_request("POST", "backup", native())
        self.assertEqual(self.backup_request("DELETE", "chat")[0], 200)
        status, _, raw = self.backup_request("GET", "backups")
        self.assertEqual(json.loads(raw)["total"], 1)
        self.backup_request("POST", "archive", {"id": "chat", "archived": True})
        _, _, raw = self.backup_request("GET", "backups")
        self.assertEqual(json.loads(raw)["total"], 0)
        _, _, raw = self.backup_request("GET", "backups?archived=1")
        self.assertEqual(json.loads(raw)["total"], 1)

    def test_actual_stream_and_plain_response_are_persisted(self):
        for stream, chat_id in ((True, "stream-chat"), (False, "plain-chat")):
            status, _, data = self.chat([{"role": "user", "content": "Original question"}], conv=chat_id, stream=stream)
            self.assertEqual(status, 200)
            # Relay finalization can finish just after the final bytes reach the client.
            vault = history.Vault(self.data, fixture.SLUG, self.port)
            import time
            deadline = time.monotonic() + 2
            while len(vault.read(chat_id)["messages"]) < 2 and time.monotonic() < deadline:
                time.sleep(.01)
            saved = vault.read(chat_id)
            self.assertEqual(saved["messages"][0]["content"], "Original question")
            self.assertGreaterEqual(len(saved["messages"]), 2)
            self.assertTrue(saved["complete"])


class DurableFrontendTests(unittest.TestCase):
    def test_legacy_text_recovery_timestamps_are_fixed_without_changing_content(self):
        source = Path(r"C:\LLM\projects\static\durable-chats.js").read_text(encoding="utf-8")
        function = re.search(r"^  function repairedTextOrder\([^\n]*\) \{.*?^  \}", source, re.M | re.S).group(0)
        code = "const assert=require('node:assert/strict');\n" + function + r"""
const record={conversation:{id:'chat',recoveredFromSharedCopy:{textOnly:true,sourceUpdatedAt:1000}},messages:[
 {id:'last',parent:'user',timestamp:1000,content:'Last answer'},
 {id:'root',parent:null,timestamp:1000,content:''},
 {id:'user',parent:'root',timestamp:1000,content:'First question'}]};
const before=JSON.stringify(record),fixed=repairedTextOrder(record);
assert.equal(JSON.stringify(record),before);
const byId=Object.fromEntries(fixed.messages.map(m=>[m.id,m]));
assert.ok(byId.root.timestamp<byId.user.timestamp);
assert.ok(byId.user.timestamp<byId.last.timestamp);
assert.equal(byId.user.content,'First question');assert.equal(byId.last.content,'Last answer');
assert.equal(repairedTextOrder({...record,conversation:{id:'chat'}}),null);
"""
        with tempfile.TemporaryDirectory(prefix="history-order-test-") as folder:
            script = Path(folder) / "test.js"
            script.write_text(code, encoding="utf-8")
            result = subprocess.run([r"C:\Program Files\nodejs\node.exe", str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_native_recovery_keeps_complete_pairs_and_pauses_pending_actions(self):
        source = Path(r"C:\LLM\projects\static\durable-chats.js").read_text(encoding="utf-8")
        function = re.search(r"^  function nativeRecoveryRecords\([^\n]*\) \{.*?^  \}", source, re.M | re.S).group(0)
        code = "const assert=require('node:assert/strict');const label=(a)=>a;\n" + function + r"""
const complete={id:'done',type:'function',function:{name:'read_file',arguments:'{}'}};
const pending={id:'pending',type:'function',function:{name:'exec_shell_command',arguments:'{}'}};
const copy={chat_id:'chat',conversation:{id:'chat',name:'GPU',currNode:'result'},messages:[
 {id:'root',parent:null,children:['user'],role:'system',type:'root',content:''},
 {id:'user',parent:'root',children:['assistant'],role:'user',content:'Question',extra:[{type:'image',data:'PICTURE'}]},
 {id:'assistant',parent:'user',children:['result','abandoned'],role:'assistant',content:'Answer',reasoningContent:'Private reasoning',toolCalls:JSON.stringify([complete,pending])},
 {id:'result',parent:'assistant',children:[],role:'tool',content:'Done',toolCallId:'done'},
 {id:'abandoned',parent:'assistant',children:[],role:'assistant',content:'Other branch'}]};
const before=JSON.stringify(copy);let serial=0;
const restored=nativeRecoveryRecords(copy,2000,()=>`new-${serial++}`);
assert.equal(JSON.stringify(copy),before);
assert.equal(restored.messages.length,5);
assert.equal(restored.conversation.id,'chat');
const assistant=restored.messages.find(m=>m.reasoningContent);
assert.deepEqual(JSON.parse(assistant.toolCalls).map(c=>c.id),['done']);
assert.ok(assistant.content.includes('pending'));
assert.equal(restored.messages.find(m=>m.role==='user').extra[0].data,'PICTURE');
assert.equal(restored.messages.find(m=>m.role==='tool').toolCallId,'done');
assert.ok(restored.messages.every(m=>m.id.startsWith('new-')));
assert.equal(restored.conversation.currNode,restored.messages.find(m=>m.role==='tool').id);
assert.throws(()=>nativeRecoveryRecords({...copy,conversation:{...copy.conversation,currNode:'missing'}},2000));
"""
        with tempfile.TemporaryDirectory(prefix="native-history-test-") as folder:
            script = Path(folder) / "test.js"
            script.write_text(code, encoding="utf-8")
            result = subprocess.run([r"C:\Program Files\nodejs\node.exe", str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
