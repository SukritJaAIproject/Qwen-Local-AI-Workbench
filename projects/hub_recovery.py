"""Durable, reconnectable response delivery for approved local agent requests.

Integration contract:
  * Run the Hub's Host, own-origin and authorization checks first.
  * For an eligible POST with X-Qwen-Recovery-ID, call
      store.serve(handler, project_slug, handler.path, body, dict(handler.headers))
    after reading/validating the body, before executing or forwarding it.
  * status(project, id, headers) and cancel(project, id, headers) return
    (HTTP status, JSON document); always supply the requesting headers.
  * result(handler, project, id, headers) delivers a completed saved response
    without the original request body, and can never dispatch any operation.

The worker makes one ordinary HTTP request to the same Hub listener with the
recovery headers removed. Existing approval, plan and execution gates therefore
remain in force. A subscriber disconnect never reexecutes that request. Only
response bytes and credential hashes are saved; request bodies and bearer
credentials are never written to this journal. Unknown interrupted operations
are not retried, because their effects may already have happened.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import socket
import threading
import time
from urllib.parse import urlsplit

ID_HEADER = 'X-Qwen-Recovery-ID'
OFFSET_HEADER = 'X-Qwen-Recovery-Offset'
STATE_HEADER = 'X-Qwen-Recovery-State'
_UUID = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
_PROJECT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
_RESPONSE_HEADERS = {'content-type', 'x-qwen-compacted', 'x-qwen-history-recovered',
                     'x-qwen-shared-chats'}
_SKIP_REQUEST = {'host', 'content-length', 'connection', 'transfer-encoding',
                 'accept-encoding', 'proxy-connection', 'keep-alive', 'te',
                 'trailer', 'upgrade'}
_FINAL = {'completed', 'failed', 'stopped', 'outcome_unknown', 'expired'}
_PATHS = {'/v1/chat/completions', '/tools', '/_qwen/recovery/mcp/web',
          '/_qwen/recovery/mcp/local'}


def _headers(headers):
    return {str(k).lower(): str(v) for k, v in headers.items()}


def _identity(headers):
    h = _headers(headers)
    # A hash is retained even for cookie-only browser clients. A request ID is
    # additionally unguessable; it never grants cross-project access.
    value = '\0'.join((h.get('authorization', ''), h.get('cookie', '')))
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _digest(path, body, headers):
    h = _headers(headers)
    digest = hashlib.sha256()
    for value in ('POST', path, h.get('x-conversation-id', ''),
                  h.get('x-qwen-plan', ''), h.get('x-qwen-bypass-permissions', ''),
                  h.get('x-qwen-recovery-target', ''),
                  h.get('content-type', ''), h.get('x-tool-cwd', ''), _identity(headers)):
        digest.update(value.encode('utf-8'))
        digest.update(b'\0')
    digest.update(body)
    return digest.hexdigest()


def _atomic_json(path, doc):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(doc, stream, ensure_ascii=False, separators=(',', ':'))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


class _Row:
    def __init__(self, directory, meta):
        self.directory, self.meta = directory, meta
        self.condition = threading.Condition(threading.RLock())
        self.connection = None
        self.socket = None
        self.live = False
        self.subscribers = 0

    def save(self):
        self.meta['updated_at'] = time.time()
        _atomic_json(self.directory / 'metadata.json', self.meta)

    def public(self):
        result = {k: self.meta.get(k) for k in ('id', 'state', 'size', 'status',
                  'error', 'created_at', 'updated_at', 'cancel_requested')}
        result['http_status'] = self.meta.get('status')
        result['content_type'] = next((value for name, value in self.meta.get('headers', {}).items()
                                      if name.lower() == 'content-type'), '')
        return result


class Store:
    def __init__(self, root, max_response=32 * 1024 * 1024, max_active=8, max_rows=4096):
        self.root = Path(root) / 'recovery'
        self.max_response = int(max_response)
        self.max_active = int(max_active)
        self.max_rows = int(max_rows)
        self.lock = threading.RLock()
        self.rows = {}

    def _key(self, project, request_id):
        if not isinstance(project, str) or not _PROJECT.fullmatch(project):
            raise ValueError('invalid recovery project')
        if not isinstance(request_id, str) or not _UUID.fullmatch(request_id):
            raise ValueError('invalid recovery id')
        return project, request_id.lower()

    def _load(self, key):
        row = self.rows.get(key)
        if row is not None:
            return row
        directory = self.root / key[0] / key[1]
        file = directory / 'metadata.json'
        if not file.is_file():
            # A directory created before a crash is an unknown reservation,
            # never a license to execute the same operation a second time.
            if directory.exists():
                raise RuntimeError('outcome_unknown')
            return None
        try:
            meta = json.loads(file.read_text(encoding='utf-8'))
            if (not isinstance(meta, dict) or meta.get('id') != key[1]
                    or not isinstance(meta.get('size'), int) or meta['size'] < 0
                    or meta['size'] > self.max_response
                    or not isinstance(meta.get('identity'), str)
                    or not isinstance(meta.get('digest'), str)):
                raise ValueError('invalid metadata')
            row = _Row(directory, meta)
            if meta.get('state') == 'expired':
                self.rows[key] = row
                return row
            actual = (directory / 'response.bin').stat().st_size
            if actual != meta['size'] or meta.get('state') not in _FINAL:
                meta['state'], meta['error'] = 'outcome_unknown', 'interrupted_before_durable_completion'
                meta['size'] = min(actual, meta['size'])
                row.save()
            self.rows[key] = row
            return row
        except (OSError, ValueError, TypeError, KeyError):
            raise RuntimeError('outcome_unknown') from None

    def _lookup(self, project, request_id, headers):
        try:
            key = self._key(project, request_id)
        except ValueError:
            return None, (400, {'error': 'invalid_recovery_id'})
        with self.lock:
            try:
                row = self._load(key)
            except RuntimeError:
                return None, (409, {'error': 'outcome_unknown', 'state': 'outcome_unknown'})
        if row is None:
            return None, (404, {'error': 'recovery_not_found'})
        if headers is None or not hmac.compare_digest(row.meta['identity'], _identity(headers)):
            return None, (403, {'error': 'recovery_identity_mismatch'})
        return row, None

    def status(self, project, request_id, headers=None):
        row, error = self._lookup(project, request_id, headers)
        if error:
            return error
        with row.condition:
            return 200, row.public()

    def cancel(self, project, request_id, headers=None):
        row, error = self._lookup(project, request_id, headers)
        if error:
            return error
        connection = transport_socket = None
        with row.condition:
            if row.meta['state'] not in _FINAL:
                row.meta.update(state='stopped', cancel_requested=True, error='user_stopped')
                row.save()
                # A model generation is cancellable. Already approved tools
                # may have committed effects: let their worker retain the
                # eventual result without resuming the agent or rerunning it.
                if row.meta.get('generation'):
                    connection = row.connection
                    transport_socket = row.socket
                row.condition.notify_all()
            result = row.public()
        if connection is not None:
            try:
                if transport_socket:
                    transport_socket.shutdown(socket.SHUT_RDWR)
                elif connection.sock:
                    connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        return 200, result

    def result(self, handler, project, request_id, headers=None):
        """Deliver saved bytes only; no request body, attach or dispatch path."""
        with self.lock:
            row, error = self._lookup(project, request_id, headers)
            if error:
                self._json(handler, *error)
                return True
            with row.condition:
                state = row.meta['state']
                if state != 'completed':
                    if state == 'running':
                        self._json(handler, 425, dict(row.public(), error='result_pending', retryable=True))
                    else:
                        reason = 'response_expired' if state == 'expired' else state
                        self._json(handler, 409, dict(row.public(), error=reason))
                    return True
                row.subscribers += 1
        try:
            return self._serve_row(handler, row, 0)
        finally:
            with row.condition:
                row.subscribers -= 1
                row.condition.notify_all()

    def _make_room(self, project, parent):
        """Evict cached bytes, retaining durable never-reexecute tombstones."""
        payloads = [item for item in parent.iterdir()
                    if item.is_dir() and _UUID.fullmatch(item.name)
                    and (item / 'response.bin').is_file()]
        if len(payloads) < self.max_rows:
            return True
        candidates = []
        for directory in payloads:
            try:
                row = self._load((project, directory.name.lower()))
            except RuntimeError:
                continue
            if row is None:
                continue
            with row.condition:
                if row.live or row.subscribers or row.meta['state'] not in ('completed', 'expired'):
                    continue
                candidates.append((row.meta.get('updated_at', 0), row))
        candidates.sort(key=lambda item: item[0])
        for _, row in candidates:
            with row.condition:
                if row.live or row.subscribers:
                    continue
                payload = row.directory / 'response.bin'
                # Only this exact journal file is removed, after verifying its
                # resolved location remains inside the recovery directory.
                try:
                    payload.resolve().relative_to(self.root.resolve())
                except ValueError:
                    continue
                row.meta.update(state='expired', error='response_expired', size=0)
                row.save()  # durable tombstone precedes deleting cached bytes
                payload.unlink(missing_ok=True)
                row.condition.notify_all()
            payloads.pop()
            if len(payloads) < self.max_rows:
                return True
        return False

    def _attach(self, project, request_id, path, body, headers, port, offset=0):
        key = self._key(project, request_id)
        fingerprint = _digest(path, body, headers)
        with self.lock:
            row = self._load(key)
            if row is not None:
                if not hmac.compare_digest(row.meta['digest'], fingerprint):
                    return None, (409, {'error': 'recovery_request_mismatch'})
                with row.condition:
                    row.subscribers += 1
                return row, None
            if offset:
                return None, (416, {'error': 'recovery_offset_out_of_range', 'size': 0})
            active = sum(1 for item in self.rows.values() if item.live)
            if active >= self.max_active:
                return None, (429, {'error': 'recovery_capacity', 'retryable': True})
            parent = self.root / key[0]
            parent.mkdir(parents=True, exist_ok=True)
            if not self._make_room(project, parent):
                return None, (507, {'error': 'recovery_journal_full'})
            directory = parent / key[1]
            directory.mkdir()  # exclusive durable reservation before dispatch
            now = time.time()
            meta = {'version': 1, 'id': key[1], 'digest': fingerprint,
                    'identity': _identity(headers), 'state': 'running', 'size': 0,
                    'status': None, 'headers': {}, 'created_at': now,
                    'updated_at': now, 'cancel_requested': False,
                    'generation': urlsplit(path).path == '/v1/chat/completions'}
            (directory / 'response.bin').touch(exist_ok=False)
            row = _Row(directory, meta)
            row.save()
            row.live = True
            row.subscribers = 1
            self.rows[key] = row
            worker = threading.Thread(target=self._worker,
                args=(row, port, path, body, dict(headers)), daemon=True,
                name='qwen-recovery-' + key[1][:8])
            try:
                worker.start()
            except RuntimeError:
                row.live = False
                row.meta.update(state='outcome_unknown', error='worker_start_failed')
                row.save()
                raise
            return row, None

    def _worker(self, row, port, path, body, headers):
        conn = None
        tail = bytearray()
        try:
            forwarding = {k: v for k, v in headers.items()
                          if k.lower() not in _SKIP_REQUEST
                          and k.lower() not in {ID_HEADER.lower(), OFFSET_HEADER.lower(), STATE_HEADER.lower()}}
            forwarding.update({'Host': '127.0.0.1:%d' % port,
                               'Content-Length': str(len(body)),
                               'Accept-Encoding': 'identity', 'Connection': 'close'})
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=7200)
            with row.condition:
                row.connection = conn
                if row.meta.get('cancel_requested'):
                    return
            conn.request('POST', path, body=body, headers=forwarding)
            with row.condition:
                row.socket = conn.sock
                if row.meta.get('cancel_requested'):
                    return
            resp = conn.getresponse()
            response_headers = {k: v for k, v in resp.getheaders() if k.lower() in _RESPONSE_HEADERS}
            with row.condition:
                row.meta.update(status=resp.status, headers=response_headers)
                row.save()
                row.condition.notify_all()
            with (row.directory / 'response.bin').open('ab', buffering=0) as out:
                while True:
                    part = resp.read1(8192)
                    if not part:
                        if resp.length not in (None, 0):
                            raise OSError('truncated_content_length')
                        break
                    with row.condition:
                        if row.meta['size'] + len(part) > self.max_response:
                            raise OSError('response_limit_exceeded')
                        out.write(part)
                        os.fsync(out.fileno())
                        row.meta['size'] += len(part)
                        row.save()
                        row.condition.notify_all()
                    tail.extend(part)
                    if len(tail) > 32768:
                        del tail[:-32768]
            ctype = next((v for k, v in response_headers.items() if k.lower() == 'content-type'), '')
            if resp.status == 200 and 'text/event-stream' in ctype:
                if row.meta.get('generation'):
                    terminal = any(line.strip() == b'data: [DONE]' for line in bytes(tail).splitlines())
                else:
                    terminal = False
                    for line in bytes(tail).splitlines():
                        if line.startswith(b'data:'):
                            try:
                                event = json.loads(line[5:].strip())
                                terminal = terminal or (isinstance(event, dict) and (
                                    event.get('done') is True or 'result' in event or 'error' in event))
                            except (ValueError, UnicodeError):
                                pass
                if not terminal:
                    raise OSError('upstream_stream_incomplete')
            with row.condition:
                if not row.meta.get('cancel_requested'):
                    row.meta.update(state='completed', error=None)
                row.save()
                row.condition.notify_all()
        except Exception as exc:
            # This is an isolated delivery worker. Every failure must publish a
            # terminal state; otherwise waiting subscribers could hang forever.
            with row.condition:
                if not row.meta.get('cancel_requested'):
                    # Once the dispatch began, failure does not prove that a
                    # tool did nothing. The same ID will never be dispatched again.
                    row.meta.update(state='failed', error=(str(exc) if str(exc) in {
                        'response_limit_exceeded', 'truncated_content_length',
                        'upstream_stream_incomplete'} else type(exc).__name__))
                try:
                    row.save()
                except OSError:
                    row.meta.update(state='outcome_unknown', error='journal_write_failed')
                row.condition.notify_all()
        finally:
            if conn is not None:
                conn.close()
            with row.condition:
                row.connection = None
                row.socket = None
                row.live = False
                if row.meta['state'] == 'running':
                    row.meta.update(state='outcome_unknown', error='worker_ended_without_completion')
                    try:
                        row.save()
                    except OSError:
                        pass
                row.condition.notify_all()

    @staticmethod
    def _json(handler, code, doc):
        raw = json.dumps(doc, ensure_ascii=False).encode('utf-8')
        handler.send_response(code)
        handler.send_header('Content-Type', 'application/json; charset=utf-8')
        handler.send_header('Cache-Control', 'no-store')
        handler.send_header('Content-Length', str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    def serve(self, handler, project_slug, path, body, upstream_headers=None):
        """Tail one durable response; reusing its ID only replays saved bytes.

        The caller must already have read the complete bounded request body and
        enforced same-origin and existing authorization gates. Only POST is
        accepted. Return True when handled (including a structured error).
        """
        request_headers = dict(upstream_headers if upstream_headers is not None else handler.headers)
        h = _headers(request_headers)
        try:
            if handler.command != 'POST' or not isinstance(body, bytes):
                raise ValueError('invalid request')
            request_id = h.get(ID_HEADER.lower(), '')
            self._key(project_slug, request_id)
            raw_offset = h.get(OFFSET_HEADER.lower(), '0')
            if not re.fullmatch(r'0|[1-9][0-9]{0,9}', raw_offset):
                raise ValueError('invalid offset')
            offset = int(raw_offset)
            if offset > self.max_response:
                raise ValueError('invalid offset')
            if not path.startswith('/') or path.startswith('//') or '\r' in path or '\n' in path:
                raise ValueError('invalid path')
            if urlsplit(path).path not in _PATHS:
                raise ValueError('unsupported recovery path')
            row, error = self._attach(project_slug, request_id, path, body,
                                      request_headers, handler.server.server_address[1], offset)
        except ValueError:
            self._json(handler, 400, {'error': 'invalid_recovery_request'})
            return True
        except (OSError, RuntimeError):
            self._json(handler, 409, {'error': 'outcome_unknown', 'state': 'outcome_unknown'})
            return True
        if error:
            self._json(handler, *error)
            return True
        try:
            return self._serve_row(handler, row, offset)
        finally:
            with row.condition:
                row.subscribers -= 1
                row.condition.notify_all()

    def _serve_row(self, handler, row, offset):
        with row.condition:
            while row.meta['status'] is None and row.meta['state'] == 'running':
                row.condition.wait(0.5)
            if row.meta['state'] in ('failed', 'stopped', 'outcome_unknown', 'expired'):
                error = 'response_expired' if row.meta['state'] == 'expired' else row.meta['state']
                self._json(handler, 409, dict(row.public(), error=error))
                return True
            if offset > row.meta['size']:
                self._json(handler, 416, {'error': 'recovery_offset_out_of_range', 'size': row.meta['size']})
                return True
            status, response_headers = row.meta['status'], dict(row.meta['headers'])
        try:
            handler.send_response(status)
            for name, value in response_headers.items():
                handler.send_header(name, value)
            handler.send_header('Cache-Control', 'no-store')
            handler.send_header('Transfer-Encoding', 'chunked')
            handler.send_header(ID_HEADER, row.meta['id'])
            handler.send_header(OFFSET_HEADER, str(offset))
            handler.send_header(STATE_HEADER, row.meta['state'])
            handler.end_headers()
            with (row.directory / 'response.bin').open('rb') as stream:
                stream.seek(offset)
                while True:
                    with row.condition:
                        while offset >= row.meta['size'] and row.meta['state'] == 'running':
                            row.condition.wait(0.5)
                        available = row.meta['size'] - offset
                        state = row.meta['state']
                    if available:
                        part = stream.read(min(8192, available))
                        if not part:
                            raise OSError('journal_read_failed')
                        handler.wfile.write(b'%x\r\n' % len(part) + part + b'\r\n')
                        handler.wfile.flush()
                        offset += len(part)
                    elif state == 'completed':
                        handler.wfile.write(b'0\r\n\r\n')
                        handler.wfile.flush()
                        break
                    elif state in _FINAL:
                        # Deliberately omit the terminal HTTP chunk. Fetch's
                        # stream reader must observe a network failure rather
                        # than silently accepting an incomplete tool result.
                        handler.close_connection = True
                        break
        except (OSError, ValueError):
            handler.close_connection = True
        return True
