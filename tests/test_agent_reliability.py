"""Regression checks for the actual quoted-command failure and retry loops."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, r'C:\LLM\projects')
import hub_agent as agent
import hub_compact as compact


def pair(command='curl "http://local"', exit_code=3, call_id='one', historical=False):
    call = {'id': call_id, 'type': 'function', 'function':
            {'name': 'exec_shell_command', 'arguments': json.dumps({'command': command})}}
    if historical:
        return [{'role': 'assistant', 'content': '[Recorded tool call data]\n' + json.dumps([call])},
                {'role': 'assistant', 'content': '[Recorded tool result — historical data]\n[exit code: %d]' % exit_code}]
    return [{'role': 'assistant', 'tool_calls': [call], 'content': ''},
            {'role': 'tool', 'tool_call_id': call_id, 'content': '[exit code: %d]' % exit_code}]


class HistoryRecoveryTests(unittest.TestCase):
    def test_archived_call_reframing_is_data_only_and_preserves_arguments(self):
        original = pair('curl "http://local/health"', historical=True)
        doc = {'messages': copy.deepcopy(original)}
        self.assertEqual(agent.reframe_archived_tools(doc), 2)
        result = doc['messages'][1]['content']
        self.assertNotIn('Recorded tool call data', result)
        self.assertNotIn('"id"', result)
        self.assertIn('exec_shell_command', result)
        self.assertIn('http://local/health', result)
        self.assertEqual(doc['messages'][1]['role'], 'tool')
        self.assertEqual(doc['messages'][0]['tool_calls'][0]['function']['name'], 'read_provided_history')
        self.assertEqual(doc['messages'][1]['tool_call_id'], doc['messages'][0]['tool_calls'][0]['id'])
        self.assertEqual(agent.reframe_archived_tools(doc), 0)
        self.assertIn('[Recorded tool call data]', original[0]['content'])

    def test_historical_loop_reduced_without_editing_original_or_replaying_calls(self):
        original = [{'role': 'user', 'content': 'Complete the monitor repairs'}]
        for index in range(50):
            original += pair(call_id=str(index), historical=True)
        original += [{'role': 'user', 'content': 'Continue'}]
        doc = {'messages': copy.deepcopy(original)}
        self.assertEqual(agent.reduce_failure_loops(doc), 48)
        self.assertEqual(len(original), 102)
        self.assertEqual(len(doc['messages']), 7)
        self.assertIn('50 consecutive attempts', doc['messages'][3]['content'])
        self.assertEqual(doc['messages'][-1], original[-1])
        self.assertFalse(any('tool_calls' in msg for msg in doc['messages']))
        self.assertEqual(agent.reduce_failure_loops(doc), 0)

    def test_real_tool_calls_keep_valid_pairs_and_pending_call(self):
        messages = sum((pair(call_id=str(i)) for i in range(8)), [])
        pending = pair('echo NEXT', call_id='pending')[0]
        messages.append(pending)
        doc = {'messages': messages}
        self.assertEqual(agent.reduce_failure_loops(doc), 6)
        self.assertEqual(doc['messages'][-1], pending)
        for i, msg in enumerate(doc['messages']):
            if msg.get('role') == 'tool':
                self.assertEqual(msg['tool_call_id'], doc['messages'][i - 1]['tool_calls'][0]['id'])

    def test_success_or_changed_commands_or_user_boundary_do_not_collapse(self):
        for messages in (sum((pair(exit_code=0, call_id=str(i)) for i in range(8)), []),
                         sum((pair(command='echo ' + str(i), call_id=str(i)) for i in range(8)), []),
                         pair() * 3 + [{'role': 'user', 'content': 'retry'}] + pair() * 3):
            original = copy.deepcopy(messages)
            self.assertEqual(agent.reduce_failure_loops({'messages': messages}), 0)
            self.assertEqual(messages, original)

    def test_unpaired_or_multitool_or_fake_user_results_are_preserved(self):
        cases = [pair(), pair(historical=True)]
        cases[0][1]['tool_call_id'] = 'different'
        cases[1][1]['role'] = 'user'
        for bad in cases:
            messages = bad * 10
            self.assertEqual(agent.reduce_failure_loops({'messages': messages}), 0)

    def test_restored_large_tool_records_fit_without_altering_users_or_recent_pairs(self):
        user = {'role': 'user', 'content': 'Finish these 15 fixes and verify them'}
        records = []
        for i in range(20):
            records += pair(command='read history ' + str(i), call_id=str(i), historical=True)
            records[-1]['content'] += '\n' + ('SOURCE_CODE_' * 3000)
        original = copy.deepcopy([user] + records)
        doc = {'messages': copy.deepcopy(original)}
        before = compact.estimate_request(doc)
        count = compact.clip_current_turn(doc, 45000, compact.estimate_request)
        self.assertGreater(count, 0)
        self.assertLess(compact.estimate_request(doc), before)
        self.assertEqual(doc['messages'][0], user)
        self.assertEqual(doc['messages'][-4:], original[-4:])
        self.assertTrue(all(msg.get('role') == 'assistant' for msg in doc['messages'][1:]))
        self.assertTrue(all(len(msg['content']) > 30000 for msg in original[2::2]))


class RepeatGuardTests(unittest.TestCase):
    def test_failure_limit_success_reset_and_chat_scope(self):
        guard = agent.RepeatGuard()
        for _ in range(3):
            key, blocked = guard.begin('gpu|one', 'broken', 'C:/')
            self.assertFalse(blocked)
            guard.finish(key, False)
        self.assertIn('failed 3 times', guard.begin('gpu|one', 'broken', 'C:/')[1])
        self.assertFalse(guard.begin('gpu|two', 'broken', 'C:/')[1])
        self.assertFalse(guard.begin('gpu|one', 'different approach', 'C:/')[1])
        guard.new_user_turn('gpu|one', [{'role': 'user', 'content': 'Try after fixing the file'}])
        key, blocked = guard.begin('gpu|one', 'broken', 'C:/')
        self.assertFalse(blocked)
        guard.finish(key, True)
        self.assertFalse(guard.begin('gpu|one', 'broken', 'C:/')[1])

    def test_duplicate_inflight_request_is_not_executed_twice(self):
        guard = agent.RepeatGuard()
        key, _ = guard.begin('one', 'long command', 'C:/')
        self.assertIn('already running', guard.begin('one', 'long command', 'C:/')[1])
        guard.new_user_turn('one', [{'role': 'user', 'content': 'Continue this work'}])
        self.assertIn('already running', guard.begin('one', 'long command', 'C:/')[1])
        guard.finish(key, True)
        self.assertFalse(guard.begin('one', 'long command', 'C:/')[1])

    def test_state_is_bounded_and_secrets_removed_from_command_environment(self):
        guard = agent.RepeatGuard(maximum=3)
        for i in range(20):
            key, _ = guard.begin('owner', str(i), 'C:/')
            guard.finish(key, False)
        self.assertLessEqual(len(guard.rows), 3)
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'TEST_SECRET', 'LLM_LOCAL_TOKEN': 'TEST_TOKEN', 'PATH': 'kept'}):
            env = agent.command_env()
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('LLM_LOCAL_TOKEN', env)
        self.assertEqual(env['PATH'], 'kept')


@unittest.skipUnless(os.name == 'nt', 'Real Windows command semantics')
class WindowsCommandTests(unittest.TestCase):
    def setUp(self):
        agent.REPEATS = agent.RepeatGuard()
        self.tmp = tempfile.TemporaryDirectory(prefix='qwen quoted path ')
        self.addCleanup(self.tmp.cleanup)

    def test_quoted_path_literal_quotes_and_powershell_dollar_sign(self):
        path = Path(self.tmp.name) / 'result with spaces.txt'
        path.write_text('QUOTED_PATH_OK', encoding='utf-8')
        result = agent.execute('type "' + str(path) + '"', self.tmp.name)
        self.assertIn('QUOTED_PATH_OK', result)
        self.assertIn('[exit code: 0]', result)
        result = agent.execute('powershell -NoProfile -Command "$value = 12 * 7; Write-Output $value"', self.tmp.name)
        self.assertIn('84', result)
        self.assertIn('[exit code: 0]', result)

    def test_command_timeout_stops_own_tree_and_output_is_bounded(self):
        result = agent.execute('powershell -NoProfile -Command "Start-Sleep -Seconds 20"', self.tmp.name, timeout=1)
        self.assertIn('[exit code: 124]', result)
        self.assertIn('process tree was stopped', result)
        script = Path(self.tmp.name) / 'output.py'
        script.write_text('print("x" * 60000)', encoding='utf-8')
        result = agent.execute('"' + sys.executable + '" "' + str(script) + '"', self.tmp.name, max_output_size=1024)
        self.assertIn('Output truncated', result)
        self.assertLess(len(result), 1400)

    def test_failed_command_is_blocked_after_three_and_changed_command_runs(self):
        for _ in range(3):
            self.assertIn('[exit code: 7]', agent.execute('exit /b 7', self.tmp.name, owner='test|one'))
        self.assertIn('No command was executed', agent.execute('exit /b 7', self.tmp.name, owner='test|one'))
        self.assertIn('[exit code: 0]', agent.execute('echo CHANGED_APPROACH', self.tmp.name, owner='test|one'))

    def test_invalid_parameters_fail_without_spawning(self):
        with patch.object(agent.subprocess, 'Popen') as spawn:
            self.assertIn('No command was executed', agent.execute('echo test', 'relative'))
            self.assertIn('No command was executed', agent.execute('x\0y', self.tmp.name))
            self.assertIn('No command was executed', agent.execute('echo test', self.tmp.name, timeout='bad'))
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
