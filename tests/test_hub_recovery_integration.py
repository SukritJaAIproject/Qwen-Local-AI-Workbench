"""Durable recovery integration through an isolated Hub and fake services.

All listeners use random localhost ports; tokens, journals and chat data live in
temporary directories. The production Hub, router, MCPs and model are untouched.
"""
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from test_hub_security import load_hub


class HubRecoveryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = load_hub()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='hub-recovery-integration-')
        self.addCleanup(self.folder.cleanup)
        self.token = secrets.token_hex(32)
        token_file = Path(self.folder.name) / 'test-services.token'
        token_file.write_text(self.token, encoding='ascii')
        self.data = Path(self.folder.name) / 'data'
        self.calls, self.mcp_calls, self.executions = [], [], []
        self.release = threading.Event()
        self.started = threading.Event()
        self.piece = b'data: {"choices":[{"delta":{"content":"RESUMABLE_REPLY"},"finish_reason":null}]}\n\n'
        self.terminal = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        owner = self

        class Upstream(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_):
                pass
            def reply(self, doc):
                raw = json.dumps(doc).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def do_GET(self):
                self.reply({'data': []})
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                doc = json.loads(raw)
                owner.calls.append((self.path, doc, dict(self.headers)))
                if self.path.startswith('/tools'):
                    self.reply({'cwd': owner.folder.name} if doc.get('tool') == 'get_info'
                               else {'plain_text_response': 'NATIVE_READ_RESULT'})
                    return
                owner.started.set()
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Connection', 'close')
                self.end_headers()
                try:
                    self.wfile.write(owner.piece)
                    self.wfile.flush()
                    owner.release.wait(5)
                    if not doc.get('test_truncated'):
                        self.wfile.write(owner.terminal)
                        self.wfile.flush()
                except OSError:
                    pass
                self.close_connection = True

        class MCP(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_):
                pass
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                doc = json.loads(raw)
                owner.mcp_calls.append((self.path, doc, dict(self.headers)))
                result = json.dumps({'jsonrpc': '2.0', 'id': doc.get('id'),
                                     'result': {'content': [{'type': 'text', 'text': 'MCP_TOOL_OK'}]}}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(result)))
                self.end_headers()
                self.wfile.write(result)

        self.upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        self.mcp = ThreadingHTTPServer(('127.0.0.1', 0), MCP)
        self.project = {'slug': 'recovery-integ', 'name': 'Recovery integration',
                        'port': 0, 'think': 'off', 'extend': False, 'auto_kb': False}
        self.server = ThreadingHTTPServer(('127.0.0.1', 0),
                          self.hub.make_proxy_handler(self.project['slug'], lambda: [self.project]))
        self.port = self.server.server_address[1]
        self.project['port'] = self.port
        self.origin = 'http://127.0.0.1:%d' % self.port
        self.patches = [
            mock.patch.dict(os.environ, {'LLM_LOCAL_TOKEN_FILE': str(token_file)}),
            mock.patch.object(self.hub, 'DATA_ROOT', self.data),
            mock.patch.object(self.hub, 'UPSTREAM_PORT', self.upstream.server_address[1]),
            mock.patch.object(self.hub, 'MCP_WEB_PORT', self.mcp.server_address[1]),
            mock.patch.object(self.hub, 'MCP_LOCAL_PORT', self.mcp.server_address[1]),
            mock.patch.object(self.hub, 'ALLOWED_ORIGIN', re.compile(r'^http://(?:127\.0\.0\.1|localhost):\d+$')),
            mock.patch.object(self.hub, 'COMPACT_ENABLED', False),
            mock.patch.object(self.hub, 'upstream_models', return_value=[]),
            mock.patch.object(self.hub, 'record_usage'),
            mock.patch.object(self.hub.KEEP_AWAKE, 'acquire', return_value=False),
            mock.patch.object(self.hub._agent, 'execute', side_effect=self.execute),
        ]
        for patch in self.patches:
            patch.start()
        self.listeners = [self.upstream, self.mcp, self.server]
        for listener in self.listeners:
            listener.daemon_threads = True
            threading.Thread(target=listener.serve_forever, daemon=True).start()

    def tearDown(self):
        self.release.set()
        store = self.hub.recovery_store()
        deadline = time.monotonic() + 3
        while any(row.live for row in store.rows.values()) and time.monotonic() < deadline:
            time.sleep(.01)
        for listener in reversed(self.listeners):
            listener.shutdown()
            listener.server_close()
        for patch in reversed(self.patches):
            patch.stop()

    def execute(self, command, cwd, *_args, **_kwargs):
        self.executions.append((command, cwd))
        return 'APPROVED_COMMAND_RESULT\n[exit code: 0]'

    def open(self, method, path, body=None, headers=None):
        h = {'Origin': self.origin, 'Content-Type': 'application/json'}
        h.update(headers or {})
        # None removes a default header, allowing explicit non-browser tests.
        h = {name: value for name, value in h.items() if value is not None}
        raw = json.dumps(body).encode() if isinstance(body, dict) else body
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=8)
        conn.request(method, path, body=raw, headers=h)
        return conn, conn.getresponse()

    def request(self, method, path, body=None, headers=None):
        conn, response = self.open(method, path, body, headers)
        result = (response.status, dict(response.getheaders()), response.read())
        conn.close()
        return result

    def generation(self, request_id, offset=0, **extras):
        doc = {'model': 'test-model', 'stream': True, 'max_tokens': 20,
               'messages': [{'role': 'user', 'content': 'Finish the approved work'}]}
        doc.update(extras)
        return self.open('POST', '/v1/chat/completions', doc,
                         {'X-Qwen-Recovery-ID': request_id, 'X-Qwen-Recovery-Offset': str(offset),
                          'X-Conversation-Id': '00000000-0000-4000-8000-000000000002::test-model'})

    def status(self, request_id):
        status, _headers, raw = self.request('GET', '/_qwen/recovery/' + request_id)
        return status, json.loads(raw)

    def wait_final(self, request_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            code, doc = self.status(request_id)
            if code == 200 and doc['state'] != 'running':
                return doc
            time.sleep(.01)
        self.fail('journal worker did not complete')

    def test_same_origin_native_command_replays_once_with_canonical_service_identity(self):
        request_id = str(uuid.uuid4())
        body = {'tool': 'exec_shell_command', 'params': {'command': 'approved example'}}
        headers = {'X-Qwen-Recovery-ID': request_id, 'X-Conversation-Id': 'command-chat',
                   'Cookie': 'unrelated-browser-cookie=first'}
        code, _h, raw = self.request('POST', '/tools', body, headers)
        self.assertEqual(code, 200)
        self.assertIn(b'APPROVED_COMMAND_RESULT', raw)
        headers.update({'Authorization': 'Bearer ' + self.token,
                        'Cookie': 'unrelated-browser-cookie=changed'})
        code, _h, replay = self.request('POST', '/tools', body, headers)
        self.assertEqual(code, 200)
        self.assertEqual(replay, raw)
        self.assertEqual(self.executions, [('approved example', self.folder.name)])
        self.assertEqual(len(self.calls), 1)  # native get_info, never broken native exec
        self.assertEqual(self.calls[0][2]['Authorization'], 'Bearer ' + self.token)
        code, doc = self.status(request_id)  # no browser Authorization header
        self.assertEqual((code, doc['state']), (200, 'completed'))
        for metadata in self.data.rglob('metadata.json'):
            self.assertNotIn(self.token, metadata.read_text())

    def test_native_read_tool_replay_and_plan_gate_are_preserved(self):
        request_id = str(uuid.uuid4())
        body = {'tool': 'read_file', 'params': {'path': 'example.txt'}}
        code, _h, raw = self.request('POST', '/tools', body, {'X-Qwen-Recovery-ID': request_id})
        self.assertEqual(code, 200)
        code, _h, replay = self.request('POST', '/tools', body, {'X-Qwen-Recovery-ID': request_id})
        self.assertEqual((code, replay), (200, raw))
        self.assertEqual(len(self.calls), 1)
        body = {'tool': 'exec_shell_command', 'stream': True, 'params': {'command': 'must never run'}}
        code, _h, raw = self.request('POST', '/tools', body,
                           {'X-Qwen-Recovery-ID': str(uuid.uuid4()), 'X-Qwen-Plan': '1'})
        self.assertEqual(code, 200)
        self.assertIn(b'No command was executed', raw)
        self.assertFalse(self.executions)

    def test_generation_disconnect_rejoins_same_stream_and_does_not_regenerate(self):
        request_id = str(uuid.uuid4())
        conn, response = self.generation(request_id)
        first = response.read(len(self.piece))
        self.assertEqual(first, self.piece)
        response.close()
        conn.close()
        self.release.set()
        self.assertEqual(self.wait_final(request_id)['state'], 'completed')
        conn, response = self.generation(request_id, len(first))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('X-Qwen-Recovery-Offset'), str(len(first)))
        self.assertEqual(first + response.read(), self.piece + self.terminal)
        conn.close()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][2]['Authorization'], 'Bearer ' + self.token)

    def test_stop_control_ends_stream_and_replay_stays_stopped(self):
        request_id = str(uuid.uuid4())
        conn, response = self.generation(request_id)
        response.read(len(self.piece))
        code, _headers, raw = self.request('POST', '/_qwen/recovery/' + request_id + '/cancel', {})
        self.assertEqual((code, json.loads(raw)['state']), (200, 'stopped'))
        with self.assertRaises(http.client.IncompleteRead):
            response.read()
        conn.close()
        conn, response = self.generation(request_id)
        self.assertEqual(response.status, 409)
        self.assertEqual(json.loads(response.read())['state'], 'stopped')
        conn.close()
        self.assertEqual(len(self.calls), 1)

    def test_recovery_controls_and_execution_reject_foreign_origin_or_bad_token(self):
        request_id = str(uuid.uuid4())
        body = {'tool': 'exec_shell_command', 'params': {'command': 'must never run'}}
        cases = [({'Origin': 'http://evil.example'}, 403),
                 ({'Origin': 'http://127.0.0.1:%d' % (self.port + 1)}, 403),
                 ({'Authorization': 'Bearer wrong'}, 401),
                 ({'Origin': None}, 401)]
        for extra, expected in cases:
            for method, path, data in [('GET', '/_qwen/recovery', None),
                                       ('GET', '/_qwen/recovery/' + request_id, None),
                                       ('GET', '/_qwen/recovery/' + request_id + '/result', None),
                                       ('POST', '/_qwen/recovery/' + request_id + '/cancel', {}),
                                       ('POST', '/tools', body)]:
                with self.subTest(extra=extra, path=path):
                    headers = dict(extra, **{'X-Qwen-Recovery-ID': request_id})
                    self.assertEqual(self.request(method, path, data, headers)[0], expected)
        self.assertFalse(self.calls)
        self.assertFalse(self.executions)
        self.assertEqual(self.status(request_id)[0], 404)

    def test_mcp_own_project_tool_call_forwards_current_token_once_and_replays(self):
        request_id = str(uuid.uuid4())
        target = 'http://127.0.0.1:%d/fast/%s' % (self.mcp.server_address[1], self.project['slug'])
        body = {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                'params': {'name': 'local_read', 'arguments': {'path': 'example'}}}
        headers = {'X-Qwen-Recovery-ID': request_id, 'X-Qwen-Recovery-Target': target,
                   'Authorization': 'Bearer ' + self.token, 'X-Conversation-Id': 'mcp-chat'}
        code, _h, raw = self.request('POST', '/_qwen/recovery/mcp/local', body, headers)
        self.assertEqual(code, 200)
        self.assertIn(b'MCP_TOOL_OK', raw)
        code, _h, replay = self.request('POST', '/_qwen/recovery/mcp/local', body, headers)
        self.assertEqual((code, replay), (200, raw))
        self.assertEqual(len(self.mcp_calls), 1)
        path, forwarded, wire_headers = self.mcp_calls[0]
        self.assertEqual(path, '/fast/' + self.project['slug'])
        self.assertEqual(forwarded, body)
        self.assertEqual(wire_headers['Authorization'], 'Bearer ' + self.token)
        self.assertNotIn('X-Qwen-Recovery-ID', wire_headers)
        self.assertEqual(self.status(request_id)[1]['state'], 'completed')

    def test_mcp_forbidden_targets_methods_and_mismatched_replay_never_dispatch(self):
        body = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                'params': {'name': 'local_read', 'arguments': {}}}
        port = self.mcp.server_address[1]
        forbidden = ['http://127.0.0.1:%d/fast/other-project' % port,
                     'http://127.0.0.1:22/fast/' + self.project['slug'],
                     'http://192.168.1.1:%d/fast/%s' % (port, self.project['slug']),
                     'http://127.0.0.1:%d/private' % port,
                     'http://127.0.0.1:%d/fast/%s?redirect=1' % (port, self.project['slug']),
                     'http://user:password@127.0.0.1:%d/fast/%s' % (port, self.project['slug'])]
        for target in forbidden:
            headers = {'X-Qwen-Recovery-ID': str(uuid.uuid4()), 'X-Qwen-Recovery-Target': target,
                       'Authorization': 'Bearer ' + self.token}
            self.assertEqual(self.request('POST', '/_qwen/recovery/mcp/local', body, headers)[0], 403)
        valid_target = 'http://127.0.0.1:%d/fast/%s' % (port, self.project['slug'])
        headers = {'X-Qwen-Recovery-ID': str(uuid.uuid4()), 'X-Qwen-Recovery-Target': valid_target,
                   'Authorization': 'Bearer ' + self.token}
        for method in ('initialize', 'tools/list', 'notifications/initialized'):
            self.assertEqual(self.request('POST', '/_qwen/recovery/mcp/local',
                                          dict(body, method=method), headers)[0], 400)
        no_auth = dict(headers)
        no_auth.pop('Authorization')
        self.assertEqual(self.request('POST', '/_qwen/recovery/mcp/local', body, no_auth)[0], 403)
        self.assertFalse(self.mcp_calls)
        self.assertEqual(self.request('POST', '/_qwen/recovery/mcp/local', body, headers)[0], 200)
        changed = dict(headers, **{'X-Qwen-Recovery-Target':
                                  'http://127.0.0.1:%d/mcp/%s' % (port, self.project['slug'])})
        code, _h, raw = self.request('POST', '/_qwen/recovery/mcp/local', body, changed)
        self.assertEqual((code, json.loads(raw)['error']), (409, 'recovery_request_mismatch'))
        self.assertEqual(len(self.mcp_calls), 1)

    def test_incomplete_generation_is_failed_in_plain_and_extend_modes(self):
        self.release.set()
        for extend in (False, True):
            with self.subTest(extend=extend):
                self.project['extend'] = extend
                request_id = str(uuid.uuid4())
                conn, response = self.generation(request_id, test_truncated=True)
                if response.status == 200:
                    with self.assertRaises(http.client.IncompleteRead):
                        response.read()
                else:
                    self.assertEqual(response.status, 409)
                    response.read()
                conn.close()
                state = self.wait_final(request_id)
                self.assertIn(state['state'], ('failed', 'outcome_unknown'))
                conn, response = self.generation(request_id, test_truncated=True)
                self.assertEqual(response.status, 409)
                response.read()
                conn.close()
        self.assertEqual(len(self.calls), 2)

    def test_saved_result_reload_needs_no_original_body_or_model_plan_cwd_headers(self):
        request_id = str(uuid.uuid4())
        body = {'tool': 'exec_shell_command', 'params': {'command': 'approved example'}}
        code, _h, original = self.request('POST', '/tools', body,
                    {'X-Qwen-Recovery-ID': request_id, 'X-Conversation-Id': 'chat::old-model',
                     'X-Tool-Cwd': self.folder.name, 'X-Qwen-Plan': '0', 'Cookie': 'ui=old'})
        self.assertEqual(code, 200)
        # Simulate a page reload: only the recovery ID and current project
        # origin remain; no private prompt/command body is sent again.
        code, headers, raw = self.request('GET', '/_qwen/recovery/' + request_id + '/result',
                                           headers={'Cookie': 'ui=new'})
        self.assertEqual((code, raw), (200, original))
        self.assertEqual(headers.get('X-Qwen-Recovery-Offset'), '0')
        self.assertEqual(len(self.executions), 1)
        self.assertEqual(len(self.calls), 1)

    def test_saved_result_pending_unknown_and_expired_never_start_an_operation(self):
        request_id = str(uuid.uuid4())
        conn, response = self.generation(request_id)
        response.read(len(self.piece))
        code, _h, raw = self.request('GET', '/_qwen/recovery/' + request_id + '/result')
        self.assertEqual((code, json.loads(raw)['error']), (425, 'result_pending'))
        self.release.set()
        response.read()
        conn.close()
        self.assertEqual(self.wait_final(request_id)['state'], 'completed')
        store = self.hub.recovery_store()
        row = store.rows[(self.project['slug'], request_id)]
        deadline = time.monotonic() + 2
        while row.live and time.monotonic() < deadline:
            time.sleep(.01)
        with row.condition:
            row.meta.update(state='running')
            row.save()
        # A fresh Store discovers an interrupted durable record, as on a Hub
        # restart; result retrieval must never redispatch the original request.
        self.hub._RECOVERY_STORES.pop(str(self.data.resolve()))
        code, _h, raw = self.request('GET', '/_qwen/recovery/' + request_id + '/result')
        self.assertEqual((code, json.loads(raw)['state']), (409, 'outcome_unknown'))
        row = self.hub.recovery_store().rows[(self.project['slug'], request_id)]
        with row.condition:
            row.meta.update(state='expired', size=0, error='response_expired')
            row.save()
        code, _h, raw = self.request('GET', '/_qwen/recovery/' + request_id + '/result')
        self.assertEqual((code, json.loads(raw)['error']), (409, 'response_expired'))
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.executions)

    def test_web_mcp_bridge_keeps_exact_tools_call_and_service_identity(self):
        request_id = str(uuid.uuid4())
        body = {'jsonrpc': '2.0', 'id': 15, 'method': 'tools/call',
                'params': {'name': 'web_search', 'arguments': {'query': 'verified example'}}}
        headers = {'X-Qwen-Recovery-ID': request_id,
                   'X-Qwen-Recovery-Target': 'http://127.0.0.1:%d/mcp' % self.mcp.server_address[1],
                   'Authorization': 'Bearer ' + self.token}
        code, _h, raw = self.request('POST', '/_qwen/recovery/mcp/web', body, headers)
        self.assertEqual(code, 200)
        self.assertIn(b'MCP_TOOL_OK', raw)
        code, _h, cached = self.request('GET', '/_qwen/recovery/' + request_id + '/result')
        self.assertEqual((code, cached), (200, raw))
        self.assertEqual(len(self.mcp_calls), 1)
        self.assertEqual(self.mcp_calls[0][0], '/mcp')
        self.assertEqual(self.mcp_calls[0][1], body)
        self.assertEqual(self.mcp_calls[0][2]['Authorization'], 'Bearer ' + self.token)


if __name__ == '__main__':
    unittest.main()
