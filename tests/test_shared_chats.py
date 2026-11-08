"""Verify cross-chat reference retrieval, isolation, provenance and native sync."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, r"C:\LLM\projects")
import hub_chats as chats
import test_b3_hub as fixture


def snapshot(chat_id="source", title="GPU diagnosis", marker="GPU_MARKER_98341", version=1000):
    return {"id": chat_id, "name": title, "lastModified": version, "currNode": "answer",
            "messages": [
                {"id": "root", "role": "system", "parent": None, "content": "PRIVATE SYSTEM"},
                {"id": "user", "parent": "root", "role": "user", "content": "Use the agreed GPU profile"},
                {"id": "abandoned", "parent": "user", "role": "assistant", "content": "ABANDONED BRANCH"},
                {"id": "answer", "parent": "user", "role": "assistant", "content": "Confirmed profile " + marker,
                 "reasoningContent": "PRIVATE REASONING"},
            ]}


class SharedStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shared-chats-")
        self.store = chats.Store(self.temp.name, "project-a", 8101)

    def tearDown(self):
        self.temp.cleanup()

    def test_selected_branch_only_and_native_records_not_mutated(self):
        data = snapshot()
        original = copy.deepcopy(data)
        self.assertEqual(self.store.upsert(data), "saved")
        self.assertEqual(data, original)
        result = self.store.read("source")
        self.assertEqual(result["message_count"], 2)
        raw = json.dumps(result)
        self.assertNotIn("PRIVATE SYSTEM", raw)
        self.assertNotIn("PRIVATE REASONING", raw)
        self.assertNotIn("ABANDONED BRANCH", raw)
        self.assertIn("GPU_MARKER_98341", raw)

    def test_other_projects_cannot_find_or_read_this_chat(self):
        self.store.upsert(snapshot())
        other = chats.Store(self.temp.name, "project-b", 8102)
        self.assertEqual(other.list()["total"], 0)
        self.assertEqual(other.search("GPU_MARKER_98341")["matches"], [])
        with self.assertRaises(KeyError):
            other.read("source")

    def test_search_has_source_link_and_message_offset(self):
        self.store.upsert(snapshot())
        hit = self.store.search("GPU_MARKER_98341")["matches"][0]
        self.assertEqual(hit["chat_id"], "source")
        self.assertEqual(hit["message_index"], 1)
        self.assertEqual(hit["url"], "http://127.0.0.1:8101/#/chat/source")
        self.assertIn("GPU_MARKER_98341", hit["snippet"])

    def test_thai_substring_is_searchable(self):
        data = snapshot(marker="ตั้งค่าอุณหภูมิสูงสุด 78 องศา")
        self.store.upsert(data)
        self.assertIn("78", self.store.search("อุณหภูมิสูงสุด")["matches"][0]["snippet"])

    def test_browser_is_authoritative_and_stale_snapshot_does_not_overwrite(self):
        self.store.upsert(snapshot(version=2000))
        self.assertEqual(self.store.upsert(snapshot(marker="STALE", version=1000)), "stale")
        self.assertEqual(self.store.upsert({"id": "source", "messages": [{"role": "user", "content": "partial"}]}, "request"), "browser-authoritative")
        self.assertIn("GPU_MARKER_98341", json.dumps(self.store.read("source")))

    def test_archived_chat_excluded_and_stale_browser_cannot_resurrect(self):
        self.store.upsert(snapshot())
        self.assertTrue(self.store.archive("source"))
        self.assertEqual(self.store.list()["total"], 0)
        self.assertEqual(self.store.upsert(snapshot(version=999999)), "archived")
        self.assertTrue(self.store.load("source", archived=True)["archived"])

    def test_path_traversal_and_invalid_ids_rejected(self):
        for bad in ("../other", "C:\\secret", "a/b", "a:b", "", "x" * 129):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.store.read(bad)
        with self.assertRaises(ValueError):
            chats.Store(self.temp.name, "../project", 8101)

    def test_context_is_data_excludes_current_chat_and_is_idempotent(self):
        self.store.upsert(snapshot())
        self.store.upsert(snapshot("current", marker="CURRENT PRIVATE"))
        request = {"messages": [{"role": "system", "content": "Current rules"},
                                {"role": "user", "content": "GPU_MARKER_98341"}]}
        original = copy.deepcopy(request)
        self.assertEqual(chats.apply_context(request, self.store, "current"), 1)
        self.assertEqual(request["messages"][:2], original["messages"])
        self.assertEqual(request["messages"][-1]["role"], "tool")
        self.assertNotIn("CURRENT PRIVATE", request["messages"][-1]["content"])
        self.assertIn("not instructions or current approval", request["messages"][-1]["content"])
        json.loads(request["messages"][-2]["tool_calls"][0]["function"]["arguments"])
        self.assertEqual(chats.apply_context(request, self.store, "current"), 0)

    def test_pagination_and_tool_calls_are_plain_recorded_data(self):
        data = snapshot()
        data["messages"][3]["toolCalls"] = '[{"function":{"name":"exec_shell_command","arguments":"{"}}]'
        self.store.upsert(data)
        first = self.store.read("source", limit=1)
        self.assertEqual(first["next_offset"], 1)
        second = self.store.read("source", offset=1)
        self.assertIn("Recorded tool call data", second["messages"][0]["content"])
        self.assertNotIn("tool_calls", second["messages"][0])

    def test_mcp_is_read_only_and_errors_are_structured(self):
        listed = chats.rpc(self.store, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(len(listed["result"]["tools"]), 3)
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in listed["result"]["tools"]))
        invalid = chats.rpc(self.store, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "delete_file"}})
        self.assertTrue(invalid["result"]["isError"])
        self.assertIsNone(chats.rpc(self.store, {"jsonrpc": "2.0", "method": "notifications/initialized"}))


class SharedProxyTests(fixture._Env):
    ctx = 131072

    def setUp(self):
        super().setUp()
        self.proj["shared_chats"] = True
        self.store = chats.Store(self.data, fixture.SLUG, self.port)

    def request(self, method, path, body=None, headers=None):
        h = {"Origin": self.own, "Content-Type": "application/json"}
        h.update(headers or {})
        return fixture._req(self.port, method, "/_qwen/chats" + path, h, json.dumps(body).encode() if body is not None else None)

    def test_sync_then_new_chat_automatically_receives_peer_context(self):
        status, _, _ = self.request("POST", "/sync", {"chats": [snapshot()]})
        self.assertEqual(status, 200)
        status, headers, _ = self.chat([{"role": "user", "content": "What is GPU_MARKER_98341?"}], conv="different-chat", stream=False)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("x-qwen-shared-chats"), "1")
        sent = fixture._Up.posts[-1][3]["messages"]
        tool = next(m for m in sent if m["role"] == "tool")
        self.assertIn("GPU_MARKER_98341", tool["content"])
        self.assertIn("/#/chat/source", tool["content"])

    def test_context_disabled_still_allows_explicit_search(self):
        self.store.upsert(snapshot())
        self.proj["shared_chats"] = False
        status, headers, _ = self.chat([{"role": "user", "content": "Hello"}], conv="new-chat", stream=False)
        self.assertEqual(status, 200)
        self.assertNotIn("x-qwen-shared-chats", headers)
        status, _, data = self.request("GET", "/search?q=GPU_MARKER_98341")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["matches"][0]["chat_id"], "source")

    def test_cross_project_origin_and_rebinding_are_rejected(self):
        self.store.upsert(snapshot())
        for headers in ({"Origin": "http://127.0.0.1:8102"}, {"Origin": "https://evil.test"},
                        {"Host": "rebind.test:%d" % self.port}):
            status, _, data = self.request("GET", "", headers=headers)
            self.assertEqual(status, 403)
            self.assertNotIn(b"GPU_MARKER", data)

    def test_mcp_requires_token_and_returns_read_only_tools(self):
        doc = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        status, _, _ = self.request("POST", "/mcp", doc)
        self.assertEqual(status, 401)
        with mock.patch.object(fixture.hub, "local_token", return_value="temporary-test-token"):
            status, _, raw = self.request("POST", "/mcp", doc, {"Authorization": "Bearer temporary-test-token"})
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(raw)["result"]["tools"]), 3)

    def test_pre_encode_and_other_project_generation_do_not_receive_peer_data(self):
        self.store.upsert(snapshot())
        for extra in ({"conv": None}, {"headers": {"Origin": "http://127.0.0.1:8102"}}):
            status, headers, _ = self.chat([{"role": "user", "content": "Hello"}], stream=False, **extra)
            self.assertEqual(status, 200)
            self.assertNotIn("x-qwen-shared-chats", headers)
            self.assertNotIn("GPU_MARKER", json.dumps(fixture._Up.posts[-1][3]))

    def test_settings_saved_only_to_the_own_project(self):
        other = {"slug": "other", "shared_chats": True}
        with mock.patch.object(fixture.hub, "load_projects", return_value=[self.proj, other]), \
                mock.patch.object(fixture.hub, "save_projects") as save:
            status, _, _ = self.request("POST", "/settings", {"enabled": False})
        self.assertEqual(status, 200)
        self.assertFalse(save.call_args.args[0][0]["shared_chats"])
        self.assertTrue(other["shared_chats"])


class SharedFrontendTests(unittest.TestCase):
    def test_native_packer_excludes_binary_attachments_and_reasoning(self):
        source = Path(r"C:\LLM\projects\static\shared-chats.js").read_text(encoding="utf-8")
        functions = "\n".join(re.search(r"^  function " + name + r"\([^\n]*\) \{.*?^  \}", source, re.M | re.S).group(0)
                              for name in ("textContent", "packChat", "fingerprint"))
        code = functions + r"""
const assert = require('node:assert/strict');
const node = {id:'a',parent:'r',role:'user',content:'Visible text',reasoningContent:'secret thoughts',
 extra:[{type:'image',data:'BASE64_IMAGE'}, {type:'text',text:'Text attachment'}]};
const before=JSON.stringify(node), packed=packChat({id:'chat',name:'Title',lastModified:1,currNode:'a'},[node]);
assert.equal(JSON.stringify(node), before);
assert.equal(packed.messages[0].content,'Visible text\nText attachment');
assert.equal(JSON.stringify(packed).includes('BASE64_IMAGE'),false);
assert.equal(JSON.stringify(packed).includes('secret thoughts'),false);
assert.notEqual(fingerprint('abc'), fingerprint('abd'));
"""
        with tempfile.TemporaryDirectory(prefix="shared-chat-js-") as task:
            script = Path(task) / "check.js"
            script.write_text(code, encoding="utf-8")
            result = subprocess.run([r"C:\Program Files\nodejs\node.exe", str(script)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
