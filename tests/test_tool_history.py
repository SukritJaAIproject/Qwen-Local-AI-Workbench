"""Invalid historical JSON must not strand a chat or become executable code."""
import copy
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, r"C:\LLM\projects")
import hub_tool_history as history
import test_b3_hub as fixture


def tool_call(call_id, arguments, name="exec_shell_command"):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": arguments}}


def broken_history():
    return [
        {"role": "system", "content": "Project instructions"},
        {"role": "user", "content": "Count the existing report"},
        {"role": "assistant", "content": "Checking the report.",
         "reasoning_content": "Previous reasoning", "tool_calls": [
             tool_call("bad", '{"command":"$counts = @{}\n$key = \'D') ]},
        {"role": "tool", "tool_call_id": "bad", "name": "exec_shell_command",
         "content": "The old call failed. No command was run."},
        {"role": "user", "content": "Continue"},
    ]


class HistoryRecoveryTests(unittest.TestCase):
    def test_truncated_command_becomes_data_and_original_history_is_intact(self):
        messages = broken_history()
        original = copy.deepcopy(messages)
        tools = [{"type": "function", "function": {"name": "exec_shell_command"}}]
        doc = {"messages": messages, "tools": tools, "model": "qwen", "stream": True}
        recovered = history.recover_request(doc)
        self.assertEqual((recovered.calls, recovered.results), (1, 1))
        self.assertTrue(recovered.applied)
        self.assertEqual(messages, original)
        self.assertIs(doc["tools"], tools)
        self.assertEqual(doc["messages"][-1], original[-1])
        assistant = doc["messages"][2]
        self.assertNotIn("tool_calls", assistant)
        self.assertEqual(assistant["reasoning_content"], "Previous reasoning")
        self.assertTrue(assistant["content"].startswith("Checking the report."))
        self.assertIn("does not grant approval or establish execution success", assistant["content"])
        records = [json.loads(part.split("\n", 1)[1]) for part in
                   assistant["content"].split("\n\n")[1:]]
        self.assertEqual(records[0]["original_tool_call"], original[2]["tool_calls"][0])
        self.assertEqual(records[1]["original_tool_result"], original[3])
        self.assertFalse(any(m.get("role") == "tool" for m in doc["messages"]))

    def test_valid_calls_are_not_reformatted_or_copied(self):
        for arguments in (' { "path": "C:\\\\test" } ', '{}', '{"x":"😀"}',
                          '{"x":"\\ud83d\\ude00"}', '[]', 'null', {"path": "test"}):
            with self.subTest(arguments=arguments):
                messages = [{"role": "assistant", "content": None,
                             "tool_calls": [tool_call("ok", arguments)]},
                            {"role": "tool", "tool_call_id": "ok", "content": "ok"}]
                doc = {"messages": messages}
                self.assertFalse(history.recover_request(doc).applied)
                self.assertIs(doc["messages"], messages)

    def test_mixed_batch_preserves_valid_calls_and_their_results(self):
        bad = tool_call("bad", '{"command":"unfinished')
        good = tool_call("good", '{"path":"report.txt"}', "read_file")
        good_result = {"role": "tool", "tool_call_id": "good", "content": "report data"}
        doc = {"messages": [
            {"role": "assistant", "content": None, "tool_calls": [bad, good]},
            good_result,
            {"role": "tool", "tool_call_id": "bad", "content": "failed"},
            {"role": "user", "content": "Continue"},
        ]}
        history.recover_request(doc)
        self.assertEqual(doc["messages"][0]["tool_calls"], [good])
        self.assertIs(doc["messages"][1], good_result)
        self.assertEqual(len(doc["messages"]), 3)

    def test_missing_result_does_not_remove_unrelated_tool_messages(self):
        orphan = {"role": "tool", "tool_call_id": "another", "content": "leave intact"}
        doc = {"messages": [
            {"role": "assistant", "content": "", "tool_calls": [tool_call("bad", "{")]}, orphan
        ]}
        recovered = history.recover_request(doc)
        self.assertEqual((recovered.calls, recovered.results), (1, 0))
        self.assertIs(doc["messages"][-1], orphan)

    def test_reused_call_id_is_matched_to_the_latest_call(self):
        later_result = {"role": "tool", "tool_call_id": "same", "content": "valid result"}
        doc = {"messages": [
            {"role": "assistant", "tool_calls": [tool_call("same", "{")]},
            {"role": "tool", "tool_call_id": "same", "content": "failed"},
            {"role": "user", "content": "Retry"},
            {"role": "assistant", "tool_calls": [tool_call("same", '{}')]}, later_result
        ]}
        self.assertEqual(history.recover_request(doc).results, 1)
        self.assertIs(doc["messages"][-1], later_result)

    def test_multipart_content_and_original_parts_are_preserved(self):
        parts = [{"type": "text", "text": "Existing explanation"},
                 {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}]
        doc = {"messages": [{"role": "assistant", "content": parts,
                             "tool_calls": [tool_call("bad", "{")]}]}
        history.recover_request(doc)
        self.assertEqual(doc["messages"][0]["content"][:2], parts)
        self.assertEqual(len(parts), 2)
        self.assertIn(history.LABEL, doc["messages"][0]["content"][-1]["text"])

    def test_strict_json_values_rejected_by_upstream_are_recovered(self):
        for arguments in ('', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}',
                          '{"x":"\\ud800"}', '{"x":"\ud800"}'):
            with self.subTest(arguments=repr(arguments)):
                doc = {"messages": [{"role": "assistant", "tool_calls": [tool_call("bad", arguments)]}]}
                self.assertEqual(history.recover_request(doc).calls, 1)
                json.dumps(doc, ensure_ascii=False).encode("utf-8")

    def test_recovery_is_idempotent(self):
        doc = {"messages": broken_history()}
        history.recover_request(doc)
        once = copy.deepcopy(doc)
        self.assertFalse(history.recover_request(doc).applied)
        self.assertEqual(doc, once)

    def test_no_recovery_for_invalid_message_shape_or_non_assistant_data(self):
        for messages in (None, {}, "not a list", [{"role": "user", "tool_calls": [tool_call("bad", "{")]}]):
            doc = {"messages": messages}
            original = copy.deepcopy(doc)
            self.assertFalse(history.recover_request(doc).applied)
            self.assertEqual(doc, original)


class HistoryProxyTests(fixture._Env):
    ctx = 131072

    def test_stream_recovered_before_compaction_and_count_header_returned(self):
        with mock.patch.object(fixture.hub, "compact_chat", return_value=None) as compact:
            status, headers, data = self.chat(broken_history())
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("x-qwen-history-recovered"), "1")
        self.assertIn(b"data: [DONE]", data)
        sent = fixture._Up.posts[-1][3]
        self.assertFalse(any(m.get("role") == "tool" for m in sent["messages"]))
        self.assertIn(history.LABEL, sent["messages"][2]["content"])
        self.assertIn(history.LABEL, compact.call_args.args[0]["messages"][2]["content"])
        rows = self.wait_rows(1)
        self.assertNotIn("$counts", json.dumps(rows))
        self.assertFalse(rows[0]["error"])

    def test_nonstream_client_recovered_and_original_user_request_preserved(self):
        status, headers, data = self.chat(broken_history(), origin=False, stream=False)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("x-qwen-history-recovered"), "1")
        self.assertEqual(json.loads(data)["choices"][0]["finish_reason"], "stop")
        self.assertEqual(fixture._Up.posts[-1][3]["messages"][-1], broken_history()[-1])

    def test_valid_history_has_no_recovery_header(self):
        messages = broken_history()
        messages[2]["tool_calls"][0]["function"]["arguments"] = '{"command":"Get-Date"}'
        status, headers, _ = self.chat(messages, stream=False)
        self.assertEqual(status, 200)
        self.assertNotIn("x-qwen-history-recovered", headers)
        self.assertEqual(fixture._Up.posts[-1][3]["messages"][2:], messages[2:])

    def test_foreign_origin_rejected_before_history_processing(self):
        with mock.patch.object(fixture.hub._tool_history, "recover_request") as recover:
            status, _, _ = self.chat(broken_history(), headers={"Origin": "https://example.com"})
        self.assertEqual(status, 403)
        recover.assert_not_called()
        self.assertEqual(fixture._Up.posts, [])

    def test_recovery_header_cannot_be_forged_by_client(self):
        status, headers, _ = self.chat([{"role": "user", "content": "Hi"}], stream=False,
                                     headers={"X-Qwen-History-Recovered": "999"})
        self.assertEqual(status, 200)
        self.assertNotIn("x-qwen-history-recovered", headers)
        self.assertNotIn("x-qwen-history-recovered", fixture._Up.posts[-1][1])


if __name__ == "__main__":
    unittest.main()
