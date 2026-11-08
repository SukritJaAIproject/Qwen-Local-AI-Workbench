"""Standing consent follows the explicit WebUI toggle and yields to plan mode."""
import copy
import importlib.util
import os
import sys
import unittest
from unittest import mock

HUB_PATH = r"C:\LLM\projects\hub.py"
sys.path.insert(0, os.path.dirname(HUB_PATH))
spec = importlib.util.spec_from_file_location("hub_bypass_under_test", HUB_PATH)
hub = importlib.util.module_from_spec(spec)
with mock.patch.object(sys, "argv", ["hub.py"]):
    spec.loader.exec_module(hub)


class BypassPermissionsTests(unittest.TestCase):
    def headers(self, **extra):
        result = {"Origin": "http://127.0.0.1:8101", hub.BYPASS_PERMISSIONS_HEADER: "1"}
        result.update(extra)
        return result

    def test_standing_consent_requires_explicit_project_webui_header(self):
        self.assertTrue(hub.bypass_permissions_enabled(self.headers()))
        for origin in (None, "https://example.com", "http://127.0.0.1:9999"):
            self.assertFalse(hub.bypass_permissions_enabled(self.headers(Origin=origin)))
        for value in (None, "0", "true", "yes"):
            headers = self.headers()
            headers[hub.BYPASS_PERMISSIONS_HEADER] = value
            self.assertFalse(hub.bypass_permissions_enabled(headers))

    def test_plan_mode_has_priority_over_bypass(self):
        headers = self.headers()
        headers[hub.PLAN_HEADER] = "1"
        self.assertFalse(hub.bypass_permissions_enabled(headers))

    def test_off_does_not_grant_consent_or_change_tools(self):
        doc = {"messages": [{"role": "user", "content": "Read a file"}],
               "tools": [{"type": "function", "function": {"name": "read_file"}}]}
        original = copy.deepcopy(doc)
        self.assertFalse(hub.apply_bypass_permissions(doc, False))
        self.assertEqual(doc, original)

    def test_on_preserves_user_request_and_tool_execution_contract(self):
        messages = [{"role": "user", "content": "Create my report"}]
        tools = [{"type": "function", "function": {"name": "local_confirm"}}]
        doc = {"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)}
        self.assertTrue(hub.apply_bypass_permissions(doc, True))
        self.assertEqual(doc["messages"][1:], messages)
        self.assertEqual(doc["tools"], tools)
        self.assertIn("standing authorization", doc["messages"][0]["content"])
        self.assertIn("genuine confirmation token", doc["messages"][0]["content"])

    def test_retry_is_idempotent_and_off_removes_old_consent(self):
        doc = {"messages": [{"role": "system", "content": "Project instructions"}]}
        hub.apply_bypass_permissions(doc, True)
        expected = copy.deepcopy(doc)
        hub.apply_bypass_permissions(doc, True)
        self.assertEqual(doc, expected)
        hub.apply_bypass_permissions(doc, False)
        self.assertEqual(doc["messages"][0]["content"], "Project instructions")

    def test_multipart_system_content_and_user_text_are_preserved(self):
        image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}
        user = {"role": "user", "content": hub.BYPASS_PERMISSIONS_PROMPT}
        doc = {"messages": [
            {"role": "system", "content": [{"type": "text", "text": "Instructions"}, image]}, user
        ]}
        hub.apply_bypass_permissions(doc, True)
        self.assertEqual(doc["messages"][0]["content"][1], image)
        hub.apply_bypass_permissions(doc, False)
        self.assertEqual(doc["messages"][0]["content"][0]["text"], "Instructions")
        self.assertEqual(doc["messages"][1], user)

    def test_invalid_message_shape_is_left_alone(self):
        for messages in (None, "not a list", {}):
            doc = {"messages": messages}
            self.assertFalse(hub.apply_bypass_permissions(doc, True))
            self.assertEqual(doc["messages"], messages)


if __name__ == "__main__":
    unittest.main()
