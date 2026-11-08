"""HTTP integration of the Windows adapter, chat ownership and approval gates."""
import json
import re
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from test_hub_security import _TokenMixin, _req, hub
from test_bypass_permissions_frontend import function


class AgentProxyTests(_TokenMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.folder = tempfile.TemporaryDirectory(prefix='agent proxy quoted ')
        self.addCleanup(self.folder.cleanup)
        self.requests = []
        folder, requests = self.folder.name, self.requests

        class Upstream(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args):
                pass
            def send(self, doc):
                raw = json.dumps(doc).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def do_GET(self):
                self.send({'data': []})
            def do_POST(self):
                doc = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append((self.path, doc))
                if self.path.startswith('/tools'):
                    self.send({'cwd': folder} if doc.get('tool') == 'get_info' else {'unexpected': True})
                else:
                    self.send({'choices': [{'message': {'role': 'assistant', 'content': 'CHECKED'}, 'finish_reason': 'stop'}]})

        self.up = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), hub.make_proxy_handler('agent-test', lambda: [self.project]))
        self.port = self.server.server_address[1]
        self.project = {'slug': 'agent-test', 'name': 'Agent test', 'port': self.port, 'think': 'off', 'extend': False, 'auto_kb': False}
        for setting in (mock.patch.object(hub, 'UPSTREAM_PORT', self.up.server_address[1]),
                        mock.patch.object(hub, 'DATA_ROOT', Path(folder) / 'data'),
                        mock.patch.object(hub, 'ALLOWED_ORIGIN', re.compile(r'^http://(?:127\.0\.0\.1|localhost):\d+$')),
                        mock.patch.object(hub, 'upstream_models', return_value=[]),
                        mock.patch.object(hub, 'COMPACT_ENABLED', False)):
            setting.start()
            self.patches.append(setting)
        hub._agent.REPEATS = hub._agent.RepeatGuard()
        for server in (self.up, self.server):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def tearDown(self):
        for server in (self.server, self.up):
            server.shutdown()
            server.server_close()
        super().tearDown()

    def command(self, command, conversation='one', headers=None):
        h = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.token,
             'X-Conversation-Id': conversation}
        if headers:
            h.update(headers)
        data = json.dumps({'tool': 'exec_shell_command', 'params': {'command': command}}).encode()
        status, _, body = _req(self.port, 'POST', '/tools', h, data)
        return status, json.loads(body)

    def test_real_quoted_command_runs_and_native_broken_executor_is_not_called(self):
        path = Path(self.folder.name) / 'file with spaces.txt'
        path.write_text('NATIVE_ADAPTER_OK', encoding='utf-8')
        status, result = self.command('type "' + str(path) + '"')
        self.assertEqual(status, 200)
        self.assertIn('NATIVE_ADAPTER_OK', result['plain_text_response'])
        self.assertIn('[exit code: 0]', result['plain_text_response'])
        self.assertTrue(all(doc.get('tool') == 'get_info' for _, doc in self.requests))

    def test_native_stream_protocol_returns_output_and_done_for_success_and_plan(self):
        headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.token,
                   'X-Conversation-Id': 'stream-check'}
        payload = json.dumps({'tool': 'exec_shell_command', 'stream': True,
                              'params': {'command': 'echo STREAM_PROTOCOL_OK'}}).encode()
        status, wire_headers, raw = _req(self.port, 'POST', '/tools', headers, payload)
        self.assertEqual(status, 200)
        self.assertIn('text/event-stream', wire_headers['content-type'])
        events = [json.loads(line[6:]) for line in raw.decode().splitlines() if line.startswith('data: ')]
        self.assertIn('STREAM_PROTOCOL_OK', events[0]['chunk'])
        self.assertIn('[exit code: 0]', events[0]['chunk'])
        self.assertTrue(events[-1]['done'])
        headers['X-Qwen-Plan'] = '1'
        _, _, blocked = _req(self.port, 'POST', '/tools', headers, payload)
        self.assertIn('No command was executed', blocked.decode())
        self.assertNotIn('STREAM_PROTOCOL_OK', blocked.decode())

    def test_failures_are_limited_per_chat_and_an_alternative_runs(self):
        for _ in range(3):
            self.assertIn('[exit code: 5]', self.command('exit /b 5')[1]['plain_text_response'])
        self.assertIn('No command was executed', self.command('exit /b 5')[1]['plain_text_response'])
        self.assertIn('[exit code: 5]', self.command('exit /b 5', conversation='two')[1]['plain_text_response'])
        self.assertIn('ALTERNATIVE_OK', self.command('echo ALTERNATIVE_OK')[1]['plain_text_response'])

    def test_auth_origin_host_and_plan_gate_before_any_execution(self):
        cases = [({'Authorization': 'Bearer wrong'}, 401),
                 ({'Origin': 'http://evil.example'}, 403),
                 ({'Origin': 'http://127.0.0.1:' + str(self.port + 1)}, 403),
                 ({'Host': 'evil.example:' + str(self.port)}, 403),
                 ({'Authorization': ''}, 401)]
        with mock.patch.object(hub._agent, 'execute') as execute:
            for headers, expected in cases:
                self.assertEqual(self.command('echo MUST_NOT_RUN', headers=headers)[0], expected)
            status, result = self.command('echo MUST_NOT_RUN', headers={'X-Qwen-Plan': '1'})
            self.assertEqual(status, 200)
            self.assertIn('No command was executed', result['plain_text_response'])
            execute.assert_not_called()

    def test_model_context_keeps_original_request_in_durable_history(self):
        from test_agent_reliability import pair
        messages = [{'role': 'user', 'content': 'Finish the task and verify the file'}]
        messages += sum((pair(call_id=str(i), historical=True) for i in range(10)), [])
        doc = {'model': 'test-model', 'messages': messages, 'max_tokens': 32, 'stream': False}
        headers = {'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:' + str(self.port),
                   'X-Conversation-Id': '00000000-0000-4000-8000-000000000001'}
        status, _, _ = _req(self.port, 'POST', '/v1/chat/completions', headers, json.dumps(doc).encode())
        self.assertEqual(status, 200)
        sent = next(value for path, value in self.requests if path == '/v1/chat/completions')
        self.assertLess(len(sent['messages']), len(messages))
        self.assertIn('verify its result', sent['messages'][0]['content'])
        self.assertTrue(any('10 consecutive attempts' in str(msg.get('content')) for msg in sent['messages']))
        saved = list((Path(self.folder.name) / 'data').rglob('chat-*.json'))
        self.assertTrue(saved)
        stored = [json.loads(path.read_text(encoding='utf-8')) for path in saved]
        self.assertTrue(any(len(item.get('messages', [])) >= len(messages) for item in stored))


class AgentCommandHeadersTests(unittest.TestCase):
    def test_header_owner_signal_body_and_existing_permissions_are_preserved(self):
        source = Path(r'C:\LLM\projects\static\webui-enhance.js').read_text(encoding='utf-8')
        fn = function(source, 'agentCommandRequest')
        code = "const assert=require('node:assert/strict');\n" + r"""
const location={href:'http://127.0.0.1:8102/',origin:'http://127.0.0.1:8102'};
const PLAN_HEADER='X-Qwen-Plan';let plan=false;
function route(){return {name:'chat',id:'current-chat'};}
function planCurrent(){return plan;}
""" + fn + r"""
const signal=new AbortController().signal;
const original={method:'POST',body:'EXACT_PAYLOAD',signal,headers:{Authorization:'Bearer test'}};
const result=agentCommandRequest('/tools',original);
assert.equal(result[1].body,original.body);assert.equal(result[1].signal,signal);
assert.equal(new Headers(result[1].headers).get('Authorization'),'Bearer test');
assert.equal(new Headers(result[1].headers).get('X-Conversation-Id'),'current-chat');
assert.equal(original.headers['X-Conversation-Id'],undefined);
plan=true;assert.equal(agentCommandRequest('/tools',original)[1].headers.get(PLAN_HEADER),'1');
const request=new Request(location.origin+'/tools',{method:'POST',body:'payload',headers:{'X-Conversation-Id':'owning-old-chat'}});
assert.equal(agentCommandRequest(request)[1].headers.get('X-Conversation-Id'),'owning-old-chat');
assert.equal(agentCommandRequest('http://evil.example/tools',original),null);
assert.equal(agentCommandRequest('/tools',{method:'GET'}),null);
assert.equal(agentCommandRequest('/mcp',original),null);
console.log('OK');
"""
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'headers.js'
            script.write_text(code, encoding='utf-8')
            run = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
