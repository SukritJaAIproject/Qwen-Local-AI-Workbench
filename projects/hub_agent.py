"""Windows command execution and progress recovery for the local agent.

The proxy uses the existing native tool surface and permission UI. Saved chats
are never edited. Historical duplicate failures are reduced only in outgoing
model requests, so a long retry loop does not overwhelm the useful context.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

GUIDANCE = (
    "Live tool use: invoke the supplied function/tool interface. Do not print a tool call "
    "as JSON or imitate '[Recorded tool call data]' or archived log formatting in the "
    "answer. Archived records describe earlier or unverified attempts, not new actions. "
    "Only a real new tool response verifies the current task.\n"
    "Action requests: carry out the requested work and verify its result before ending. "
    "Keep track of the requested deliverables, remaining steps and evidence. A progress "
    "message or intention is not completion: keep calling tools while useful work remains. "
    "If a tool fails, read the actual error, inspect the relevant file/schema/environment, "
    "and change the approach. Never repeat an identical failed command indefinitely; after "
    "two failures, use a different command or tool. Empty output with exit code 0 does not "
    "prove that the requested operation worked. Verify files, tests or response values. "
    "Report success only for checks actually observed. If blocked by missing information, "
    "access, hardware or a required approval, explain the exact blocker and next action; "
    "do not invent success or keep polling a permanent error. Respect Stop and plan mode.\n"
    "Windows tools: exec_shell_command runs through Windows cmd.exe, not Bash. Use Windows "
    "paths and tools; prefer reading files/search tools over printing huge directories. "
    "For complicated PowerShell/Python code, write a script in the project's work folder "
    "and run it with powershell -NoProfile -File or python -X utf8. Preserve literal newlines "
    "and dollar signs; JSON escaping is only for the tool argument, not the script contents. "
    "Read actual paths, API routes and database schemas before using them. A missing route "
    "or optional metric must be diagnosed, not endlessly retried. When asked to open a "
    "local dashboard, verify that it responds, then open its URL with Windows start \"\" "
    "or provide the verified link if no UI-opening tool is available. Polling a JSON "
    "status endpoint does not fulfill a request to display the dashboard. Native tools run on the "
    "Windows host; the MCP Python sandbox is a separate tool."
)
_EXIT = re.compile(r'\[exit code:\s*(-?\d+)\]')


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(x.get('text', '') for x in value if isinstance(x, dict) and x.get('type') == 'text')
    return ''


def _failed_pair(messages, index):
    if index + 1 >= len(messages):
        return None
    call, result = messages[index:index + 2]
    if not isinstance(call, dict) or not isinstance(result, dict) or call.get('role') != 'assistant':
        return None
    calls = call.get('tool_calls')
    historical = False
    if not calls:
        content = _text(call.get('content'))
        marker = '[Recorded tool call data]\n'
        if marker not in content:
            return None
        try:
            calls = json.loads(content.split(marker, 1)[1])
            historical = True
        except (ValueError, TypeError):
            return None
    if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
        return None
    fn = calls[0].get('function')
    if not isinstance(fn, dict) or fn.get('name') != 'exec_shell_command':
        return None
    try:
        args = fn.get('arguments', {})
        args = json.loads(args) if isinstance(args, str) else args
        command = args.get('command')
        if not isinstance(command, str) or not command.strip():
            return None
    except (ValueError, TypeError, AttributeError):
        return None
    output = _text(result.get('content'))
    if historical:
        if result.get('role') != 'assistant' or not output.startswith('[Recorded tool result'):
            return None
    elif result.get('role') != 'tool' or result.get('tool_call_id') != calls[0].get('id'):
        return None
    exits = _EXIT.findall(output)
    if not exits or int(exits[-1]) == 0:
        return None
    return command.strip(), int(exits[-1]), historical


def reduce_failure_loops(doc):
    """Keep both ends of each consecutive failure run and its exact count."""
    messages = doc.get('messages')
    if not isinstance(messages, list):
        return 0
    out, removed, index = [], 0, 0
    while index < len(messages):
        signature = _failed_pair(messages, index)
        end = index + 2
        if signature:
            while end < len(messages) and _failed_pair(messages, end) == signature:
                end += 2
        count = (end - index) // 2 if signature else 0
        if count >= 4:
            out.extend(messages[index:index + 2])
            out.append({'role': 'assistant', 'content':
                '[Repeated failure summary — historical evidence]\n'
                'The identical shell command returned exit code %d on %d consecutive attempts. '
                'The duplicate records are preserved in the saved chat. This outgoing request '
                'keeps the first and last attempts. Use a different approach and verify the result.'
                % (signature[1], count)})
            out.extend(messages[end - 2:end])
            removed += count - 2
            index = end
        else:
            out.append(messages[index])
            index += 1
    if removed:
        doc['messages'] = out
    return removed


def reframe_archived_tools(doc):
    """Put archived text in read-only context results instead of assistant voice.

    The only synthetic call is read_provided_history: it represents this
    server reading the supplied archive, not running any recorded command.
    Original function IDs and executable calls are never restored or sent to
    the UI. Bounded chunks allow the existing compactor to fit long archives.
    """
    messages = doc.get('messages')
    if not isinstance(messages, list):
        return 0
    changed = 0
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or message.get('role') != 'assistant' or message.get('tool_calls'):
            continue
        text = _text(message.get('content'))
        call_marker = '[Recorded tool call data]\n'
        result_marker = '[Recorded tool result — historical data]\n'
        replacement = None
        if call_marker in text:
            prefix, payload = text.split(call_marker, 1)
            try:
                calls = json.loads(payload)
                if not isinstance(calls, list):
                    continue
                lines = ['[Archived tool-call evidence; no action is pending]',
                         'These are text records of earlier proposed calls, not live tool invocations.']
                if prefix.strip():
                    lines.append('Earlier commentary: ' + prefix.strip())
                for call in calls:
                    fn = call.get('function', {}) if isinstance(call, dict) else {}
                    name = fn.get('name', '')
                    arguments = fn.get('arguments', {})
                    arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
                    lines.append('Tool named in the old record: ' + json.dumps(name, ensure_ascii=False))
                    lines.append('Historical arguments (data only): ' + json.dumps(arguments, ensure_ascii=False))
                replacement = '\n'.join(lines)
            except (ValueError, TypeError, AttributeError):
                continue
        elif text.startswith(result_marker):
            replacement = ('[Archived tool-result evidence; not a new verification]\n'
                           + text[len(result_marker):])
        elif text.startswith(('[Archived tool-call evidence;', '[Archived tool-result evidence;')):
            replacement = text
        if replacement is not None:
            messages[index] = dict(message, content=replacement)
            changed += 1
    if changed:
        out, buffered = [], []

        def flush():
            if not buffered:
                return
            body = '\n\n'.join(buffered)
            buffered.clear()
            for offset in range(0, len(body), 12000):
                chunk = body[offset:offset + 12000]
                call_id = '__qwen_archive_' + hashlib.sha256((str(len(out)) + '\0' + chunk).encode('utf-8')).hexdigest()[:20]
                out.append({'role': 'assistant', 'content': '', 'tool_calls': [{'id': call_id, 'type': 'function',
                    'function': {'name': 'read_provided_history', 'arguments': '{}'}}]})
                out.append({'role': 'tool', 'tool_call_id': call_id, 'content':
                    'Provided historical chat records, read by the proxy. Unverified past attempts; '
                    'data only, no action is pending and no permission is granted. '
                    'Use real new tool responses for the current task.\n' + chunk})

        for message in messages:
            content = _text(message.get('content')) if isinstance(message, dict) else ''
            if isinstance(message, dict) and message.get('role') == 'assistant' and not message.get('tool_calls') \
                    and content.startswith(('[Archived tool-call evidence;', '[Archived tool-result evidence;')):
                buffered.append(content)
            else:
                flush()
                out.append(message)
        flush()
        doc['messages'] = out
    return changed


class RepeatGuard:
    def __init__(self, limit=3, maximum=512, ttl=900):
        self.limit, self.maximum, self.ttl = limit, maximum, ttl
        self.rows = OrderedDict()
        self.turns = OrderedDict()
        self.lock = threading.Lock()

    def new_user_turn(self, owner, messages):
        users = [_text(x.get('content')) for x in messages if isinstance(x, dict) and x.get('role') == 'user']
        if not owner or not users:
            return
        mark = hashlib.sha256((str(len(users)) + '\0' + users[-1]).encode('utf-8')).hexdigest()
        with self.lock:
            if self.turns.get(owner) != mark:
                for key in [key for key, value in self.rows.items() if key[0] == owner and not value[2]]:
                    del self.rows[key]
                self.turns[owner] = mark
                self.turns.move_to_end(owner)
                while len(self.turns) > self.maximum:
                    self.turns.popitem(last=False)

    def begin(self, owner, command, cwd):
        if not owner:
            return None, ''
        key = (owner, hashlib.sha256((os.path.normcase(cwd) + '\0' + command.strip()).encode('utf-8')).hexdigest())
        now = time.monotonic()
        with self.lock:
            failures, at, busy = self.rows.get(key, (0, now, False))
            if now - at > self.ttl:
                failures, busy = 0, False
            if busy:
                return None, 'This exact command is already running. Do not start it again.'
            if failures >= self.limit:
                return None, ('This identical command failed %d times. No command was executed. '
                              'Inspect the error and change the command/tool or check the underlying cause. '
                              'Do not repeat the same failing request.' % failures)
            self.rows[key] = (failures, now, True)
            self.rows.move_to_end(key)
            while len(self.rows) > self.maximum:
                # Never evict an executing command and accidentally permit it twice.
                victim = next((k for k, v in self.rows.items() if not v[2]), None)
                if victim is None:
                    del self.rows[key]
                    return None, 'Too many commands are running; wait for one to finish.'
                del self.rows[victim]
        return key, ''

    def finish(self, key, success):
        if key is None:
            return
        with self.lock:
            previous = self.rows.get(key, (0, 0, False))[0]
            self.rows[key] = (0 if success else previous + 1, time.monotonic(), False)


REPEATS = RepeatGuard()


def command_env():
    # Keep the user's runtime search paths but never inherit service/API credentials.
    secret = re.compile(r'(?:TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY|PRIVATE_KEY|CREDENTIAL)', re.I)
    env = {key: value for key, value in os.environ.items()
           if not secret.search(key) and not key.upper().endswith('_PROXY')}
    root = os.environ.get('SystemRoot', r'C:\Windows')
    env['COMSPEC'] = str(Path(root) / 'System32/cmd.exe')
    env['PYTHONUTF8'] = '1'
    return env


def execute(command, cwd, timeout=10, max_output_size=16384, owner=''):
    """Execute exactly the approved string, preserving cmd.exe quotation rules."""
    if not isinstance(command, str) or not command.strip() or '\0' in command or len(command) > 16384:
        return 'Invalid or oversized command. No command was executed.\n[exit code: 1]'
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not os.path.isdir(cwd):
        return 'The native tool working directory is unavailable. No command was executed.\n[exit code: 1]'
    try:
        timeout = max(1, min(60, int(timeout)))
        maximum = max(1024, min(262144, int(max_output_size)))
    except (TypeError, ValueError, OverflowError):
        return 'Invalid command limits. No command was executed.\n[exit code: 1]'
    key, blocked = REPEATS.begin(owner, command, cwd)
    if blocked:
        return blocked + '\n[exit code: 125]'
    success = False
    proc = None
    capture, count = bytearray(), [0]
    capture_lock = threading.Lock()
    try:
        if os.name != 'nt':
            raise RuntimeError('This command adapter requires Windows')
        env = command_env()
        proc = subprocess.Popen(command, shell=True, executable=env['COMSPEC'], cwd=cwd, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0, creationflags=0x08000000)

        def drain():
            try:
                while True:
                    part = proc.stdout.read(4096)
                    if not part:
                        break
                    with capture_lock:
                        count[0] += len(part)
                        capture.extend(part[:max(0, maximum - len(capture))])
            except (OSError, ValueError):
                pass

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        timed_out = False
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            # Only the still-running process tree created above, never unrelated services.
            if proc.poll() is None:
                killer = Path(env['COMSPEC']).with_name('taskkill.exe')
                subprocess.run([str(killer), '/PID', str(proc.pid), '/T', '/F'],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=10, creationflags=0x08000000, env=env)
                if proc.poll() is None:
                    proc.kill()
            proc.wait(timeout=5)
            code = 124
        reader.join(timeout=1)
        with capture_lock:
            output = bytes(capture).decode('utf-8', errors='replace')
            clipped = count[0] > maximum
        if clipped:
            output += '\n[Output truncated at %d bytes; read the relevant file/log in smaller sections.]' % maximum
        if timed_out:
            output += '\n[Command timed out after %d seconds. Its process tree was stopped.]' % timeout
        success = code == 0
        if not success:
            output += '\n[The command failed. Inspect stderr, paths, API routes or schemas; change the approach before retrying.]'
        return output + '\n[exit code: %d]' % code
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return 'Command adapter failed: %s. No success was verified.\n[exit code: 1]' % type(exc).__name__
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            if proc.stdout:
                proc.stdout.close()
        REPEATS.finish(key, success)
