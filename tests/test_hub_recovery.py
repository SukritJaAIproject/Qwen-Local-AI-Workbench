"""Recovery uses fake localhost handlers only; it never touches live services."""
import http.client
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, r'C:\LLM\projects')
from hub_recovery import Store


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='hub-recovery-test-')
        self.addCleanup(self.folder.cleanup)
        self.store = Store(self.folder.name)
        self.calls = []
        self.release = threading.Event()
        self.started = threading.Event()
        self.piece = b'data: {"choices":[{"delta":{"content":"THAI: \xe0\xb9\x84\xe0\xb8\x97\xe0\xb8\xa2"}}]}\n\n'
        self.done = b'data: [DONE]\n\n'
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_):
                pass
            def do_GET(self):
                owner.store.result(self, 'test-project', self.path.split('/')[-1], dict(self.headers))
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                if self.headers.get('X-Qwen-Recovery-ID'):
                    owner.store.serve(self, 'test-project', self.path, body, dict(self.headers))
                    return
                owner.calls.append((self.path, body, dict(self.headers)))
                owner.started.set()
                if self.path == '/tools':
                    owner.release.wait(3)
                    raw = json.dumps({'plain_text_response': 'APPROVED_TOOL_RESULT'}).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    try:
                        self.wfile.write(raw)
                    except OSError:
                        pass
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Connection', 'close')
                self.end_headers()
                try:
                    self.wfile.write(owner.piece)
                    self.wfile.flush()
                    owner.release.wait(3)
                    if body != b'truncated':
                        self.wfile.write(owner.done)
                        self.wfile.flush()
                except OSError:
                    pass
                self.close_connection = True

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.headers = {'Authorization': 'Bearer TEST_ONLY_CREDENTIAL',
                        'Content-Type': 'application/json', 'X-Conversation-Id': 'test-chat::test-model'}

    def tearDown(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()

    def request(self, request_id, offset=0, body=b'{}', path='/v1/chat/completions', headers=None):
        h = dict(self.headers)
        h.update({'X-Qwen-Recovery-ID': request_id, 'X-Qwen-Recovery-Offset': str(offset)})
        if headers:
            h.update(headers)
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request('POST', path, body=body, headers=h)
        return conn, conn.getresponse()

    def final_status(self, request_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            code, doc = self.store.status('test-project', request_id, self.headers)
            if code == 200 and doc['state'] != 'running':
                return doc
            time.sleep(.01)
        self.fail('worker did not complete')

    def result(self, request_id, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request('GET', '/result/' + request_id, headers=headers or self.headers)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_partial_disconnect_reattaches_at_exact_byte_offset_once(self):
        request_id = str(uuid.uuid4())
        conn, response = self.request(request_id)
        first = response.read(len(self.piece) - 5)
        self.assertEqual(first, self.piece[:-5])
        response.close()
        conn.close()
        self.release.set()
        self.assertEqual(self.final_status(request_id)['state'], 'completed')
        conn, response = self.request(request_id, len(first))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('X-Qwen-Recovery-Offset'), str(len(first)))
        self.assertEqual(first + response.read(), self.piece + self.done)
        conn.close()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(any(k.lower().startswith('x-qwen-recovery-') for k in self.calls[0][2]))

    def test_completed_tool_delivery_replays_after_store_restart_without_effects(self):
        request_id = str(uuid.uuid4())
        self.release.set()
        conn, response = self.request(request_id, path='/tools', body=b'approved_write')
        original = response.read()
        conn.close()
        self.assertIn(b'APPROVED_TOOL_RESULT', original)
        self.store = Store(self.folder.name)
        conn, response = self.request(request_id, path='/tools', body=b'approved_write')
        self.assertEqual(response.read(), original)
        conn.close()
        self.assertEqual(len(self.calls), 1)
        all_metadata = '\n'.join(file.read_text() for file in Path(self.folder.name).rglob('metadata.json'))
        self.assertNotIn('TEST_ONLY_CREDENTIAL', all_metadata)
        self.assertNotIn('approved_write', all_metadata)

    def test_duplicate_subscribers_do_not_dispatch_duplicate_tool(self):
        request_id = str(uuid.uuid4())
        responses = []
        errors = []
        def read():
            try:
                conn, response = self.request(request_id, path='/tools')
                responses.append(response.read())
                conn.close()
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=read) for _ in range(2)]
        for thread in threads:
            thread.start()
        self.assertTrue(self.started.wait(2))
        self.release.set()
        for thread in threads:
            thread.join(5)
        self.assertFalse(errors)
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0], responses[1])
        self.assertEqual(len(self.calls), 1)

    def test_mismatched_body_chat_plan_and_identity_are_rejected(self):
        request_id = str(uuid.uuid4())
        self.release.set()
        conn, response = self.request(request_id)
        response.read()
        conn.close()
        for body, extra in [(b'changed', {}), (b'{}', {'X-Conversation-Id': 'other'}),
                            (b'{}', {'X-Qwen-Plan': '1'}),
                            (b'{}', {'Authorization': 'Bearer OTHER'})]:
            conn, response = self.request(request_id, body=body, headers=extra)
            self.assertEqual(response.status, 409)
            self.assertEqual(json.loads(response.read())['error'], 'recovery_request_mismatch')
            conn.close()
        self.assertEqual(self.store.status('test-project', request_id, {'Authorization': 'Bearer OTHER'})[0], 403)
        self.assertEqual(self.store.cancel('test-project', request_id, {'Authorization': 'Bearer OTHER'})[0], 403)
        self.assertEqual(len(self.calls), 1)

    def test_invalid_ids_offsets_and_future_offsets_do_not_dispatch_new_effect(self):
        for request_id, offset in [('../escape', 0), (str(uuid.uuid4()), '-1'),
                                  (str(uuid.uuid4()), '1.5'), (str(uuid.uuid4()), '99999999999')]:
            conn, response = self.request(request_id, offset)
            self.assertEqual(response.status, 400)
            response.read()
            conn.close()
        self.assertFalse(self.calls)
        conn, response = self.request(str(uuid.uuid4()), 1, path='/tools')
        self.assertEqual(response.status, 416)
        response.read()
        conn.close()
        self.assertFalse(self.calls)
        request_id = str(uuid.uuid4())
        self.release.set()
        conn, response = self.request(request_id)
        response.read()
        conn.close()
        conn, response = self.request(request_id, len(self.piece + self.done) + 1)
        self.assertEqual(response.status, 416)
        response.read()
        conn.close()
        self.assertEqual(len(self.calls), 1)

    def test_interrupted_persisted_tool_is_unknown_and_never_dispatched_again(self):
        request_id = str(uuid.uuid4())
        directory = Path(self.folder.name) / 'recovery' / 'test-project' / request_id
        directory.mkdir(parents=True)
        (directory / 'response.bin').write_bytes(b'partial')
        from hub_recovery import _digest, _identity
        meta = {'id': request_id, 'digest': _digest('/tools', b'{}', self.headers),
                'identity': _identity(self.headers), 'state': 'running', 'size': 7,
                'status': None, 'headers': {}, 'created_at': time.time()}
        (directory / 'metadata.json').write_text(json.dumps(meta))
        conn, response = self.request(request_id, path='/tools')
        self.assertEqual(response.status, 409)
        self.assertEqual(json.loads(response.read())['state'], 'outcome_unknown')
        conn.close()
        self.assertFalse(self.calls)

    def test_missing_metadata_reservation_never_reexecutes(self):
        request_id = str(uuid.uuid4())
        (Path(self.folder.name) / 'recovery' / 'test-project' / request_id).mkdir(parents=True)
        conn, response = self.request(request_id, path='/tools')
        self.assertEqual(response.status, 409)
        self.assertEqual(json.loads(response.read())['state'], 'outcome_unknown')
        conn.close()
        self.assertFalse(self.calls)

    def test_truncated_upstream_never_looks_like_completed_response(self):
        request_id = str(uuid.uuid4())
        self.release.set()
        conn, response = self.request(request_id, body=b'truncated')
        if response.status == 200:
            with self.assertRaises(http.client.IncompleteRead):
                response.read()
        else:
            self.assertEqual(response.status, 409)
            response.read()
        conn.close()
        status = self.final_status(request_id)
        self.assertEqual(status['state'], 'failed')
        self.assertEqual(status['error'], 'upstream_stream_incomplete')
        conn, response = self.request(request_id, body=b'truncated')
        self.assertEqual(response.status, 409)
        response.read()
        conn.close()
        self.assertEqual(len(self.calls), 1)

    def test_cancel_generation_stops_delivery_and_prevents_reexecution(self):
        request_id = str(uuid.uuid4())
        conn, response = self.request(request_id)
        response.read(len(self.piece))
        code, result = self.store.cancel('test-project', request_id, self.headers)
        self.assertEqual(code, 200)
        self.assertEqual(result['state'], 'stopped')
        with self.assertRaises(http.client.IncompleteRead):
            response.read()
        conn.close()
        conn, response = self.request(request_id)
        self.assertEqual(response.status, 409)
        self.assertEqual(json.loads(response.read())['state'], 'stopped')
        conn.close()
        self.assertEqual(len(self.calls), 1)

    def test_response_cap(self):
        self.store = Store(self.folder.name, max_response=8, max_active=1)
        request_id = str(uuid.uuid4())
        self.release.set()
        conn, response = self.request(request_id, path='/tools')
        if response.status == 200:
            with self.assertRaises(http.client.IncompleteRead):
                response.read()
        else:
            self.assertEqual(response.status, 409)
            response.read()
        conn.close()
        self.assertEqual(self.final_status(request_id)['state'], 'failed')
        self.assertEqual(self.final_status(request_id)['error'], 'response_limit_exceeded')

    def test_active_capacity_refuses_second_new_operation(self):
        self.store = Store(self.folder.name, max_active=1)
        request_id = str(uuid.uuid4())
        first_conn, first_response = self.request(request_id)
        first_response.read(len(self.piece))
        conn, response = self.request(str(uuid.uuid4()), path='/tools')
        self.assertEqual(response.status, 429)
        self.assertEqual(json.loads(response.read())['error'], 'recovery_capacity')
        conn.close()
        self.release.set()
        first_response.read()
        first_conn.close()
        self.assertEqual(len(self.calls), 1)

    def test_mcp_target_is_bound_and_preserved_for_validated_bridge(self):
        request_id = str(uuid.uuid4())
        target = 'http://127.0.0.1:8792/fast/test-project'
        self.release.set()
        conn, response = self.request(request_id, path='/_qwen/recovery/mcp/local',
                                      headers={'X-Qwen-Recovery-Target': target})
        if response.status == 200:
            # The fake endpoint emits generation-shaped SSE; MCP validation
            # correctly rejects its missing JSON-RPC result.
            with self.assertRaises(http.client.IncompleteRead):
                response.read()
        else:
            response.read()
        conn.close()
        self.assertEqual(self.calls[0][2].get('X-Qwen-Recovery-Target'), target)
        conn, response = self.request(request_id, path='/_qwen/recovery/mcp/local',
                                      headers={'X-Qwen-Recovery-Target': target + '-other'})
        self.assertEqual(response.status, 409)
        self.assertEqual(json.loads(response.read())['error'], 'recovery_request_mismatch')
        conn.close()
        self.assertEqual(len(self.calls), 1)

    def test_payload_eviction_retains_never_reexecute_tombstones_across_restart(self):
        self.store = Store(self.folder.name, max_rows=1)
        first_id, second_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.release.set()
        conn, response = self.request(first_id, path='/tools')
        response.read()
        conn.close()
        row = self.store.rows[('test-project', first_id)]
        deadline = time.monotonic() + 2
        while (row.live or row.subscribers) and time.monotonic() < deadline:
            time.sleep(.01)
        conn, response = self.request(second_id, path='/tools')
        self.assertEqual(response.status, 200)
        response.read()
        conn.close()
        first_dir = Path(self.folder.name) / 'recovery' / 'test-project' / first_id
        self.assertTrue((first_dir / 'metadata.json').is_file())
        self.assertFalse((first_dir / 'response.bin').exists())
        self.store = Store(self.folder.name, max_rows=1)
        conn, response = self.request(first_id, 1, path='/tools')
        self.assertEqual(response.status, 409)
        payload = json.loads(response.read())
        self.assertEqual(payload['state'], 'expired')
        self.assertEqual(payload['error'], 'response_expired')
        conn.close()
        self.assertEqual(len(self.calls), 2)

    def test_held_subscriber_is_not_evicted(self):
        self.store = Store(self.folder.name, max_rows=1)
        request_id = str(uuid.uuid4())
        self.release.set()
        conn, response = self.request(request_id, path='/tools')
        response.read()
        conn.close()
        row = self.store.rows[('test-project', request_id)]
        with row.condition:
            row.subscribers += 1  # represents an in-progress reconnect subscriber
        try:
            conn, response = self.request(str(uuid.uuid4()), path='/tools')
            self.assertEqual(response.status, 507)
            response.read()
            conn.close()
            self.assertTrue((row.directory / 'response.bin').exists())
            self.assertEqual(len(self.calls), 1)
        finally:
            with row.condition:
                row.subscribers -= 1

    def test_saved_result_without_original_request_body_chat_or_plan_never_executes(self):
        request_id = str(uuid.uuid4())
        self.release.set()
        conn, response = self.request(request_id, path='/tools', body=b'private request',
                                      headers={'X-Qwen-Plan': '1', 'X-Tool-Cwd': r'C:\private'})
        original = response.read()
        conn.close()
        self.store = Store(self.folder.name)
        status, headers, raw = self.result(request_id, {'Authorization': self.headers['Authorization']})
        self.assertEqual((status, raw), (200, original))
        self.assertEqual(headers['X-Qwen-Recovery-Offset'], '0')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.result(request_id, {'Authorization': 'Bearer wrong'})[0], 403)
        self.assertEqual(len(self.calls), 1)

    def test_saved_result_pending_and_expired_are_explicit_and_never_dispatch(self):
        request_id = str(uuid.uuid4())
        conn, response = self.request(request_id)
        response.read(len(self.piece))
        status, _headers, raw = self.result(request_id)
        self.assertEqual((status, json.loads(raw)['error']), (425, 'result_pending'))
        self.release.set()
        response.read()
        conn.close()
        self.assertEqual(self.final_status(request_id)['state'], 'completed')
        row = self.store.rows[('test-project', request_id)]
        with row.condition:
            row.meta.update(state='expired', error='response_expired', size=0)
            row.save()
        self.assertEqual(self.result(request_id)[0], 409)
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__':
    unittest.main()
