"""Turn handoff checks using the runtime task snapshot, separate from future schedules."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.environ['INBOARD_CONFIG'] = str(ROOT / 'inboard.config.example.yaml')
sys.path.insert(0, str(ROOT / 'lib'))
import card_hooks as H
import ibconfig as C

SID = '11111111-1111-4111-8111-111111111111'
CARD = '22222222-2222-4222-8222-222222222222'


class Board:
    CLOSED_KEYS = {'done', 'expired', 'cancelled', 'unsub'}

    def __init__(self):
        self.page = {'properties': {'Status': {'select': {'name': C.status_name('researching')}},
                                   'Session': {'rich_text': [{'plain_text': SID}]}}}
        self.logs = []

    def api(self, method, path):
        return copy.deepcopy(self.page)

    def _g(self, props, key, kind):
        if kind == 'select':
            return props.get(key, {}).get(kind, {}).get('name', '')
        return ''.join(x.get('plain_text', '') for x in props.get(key, {}).get(kind, []))

    def log(self, args):
        self.logs.append(args.text)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, INBOARD_STATE=self.temp.name, INBOARD_LOGS=self.temp.name)
        env.start()
        self.addCleanup(env.stop)
        self.board = Board()
        self.state = {'card': CARD}

    def payload(self, event='Stop', **kwargs):
        return {'session_id': SID, 'hook_event_name': event, 'stop_hook_active': False,
                'background_tasks': [], **kwargs}

    def stop(self, **kwargs):
        return H.decide(self.board, self.state, self.payload(**kwargs))

    def test_researching_without_work_blocks_and_does_not_choose_business_status(self):
        before = copy.deepcopy(self.board.page)
        result = self.stop()
        self.assertEqual(result['decision'], 'block')
        self.assertIn('continue', result['reason'])
        self.assertEqual(self.board.page, before)

    def test_waiting_needs_you_and_closed_allow_stop(self):
        for status in ('awaiting', 'needs_you', 'done', 'expired', 'cancelled'):
            self.board.page['properties']['Status']['select']['name'] = C.status_name(status)
            self.assertEqual(self.stop(), {})

    def test_future_wakeup_and_idle_worker_are_not_work(self):
        self.state.update(NextCheck='2099-01-01', worker={'state': 'idle', 'pid': os.getpid()})
        self.assertEqual(self.stop()['decision'], 'block')

    def test_running_shell_or_agent_allows_stop(self):
        for kind in ('shell', 'agent'):
            self.assertEqual(self.stop(background_tasks=[{'id': 'task', 'type': kind,
                                                         'status': 'running'}]), {})

    def test_finished_pending_idle_and_failed_tasks_do_not_count(self):
        for status in ('completed', 'failed', 'killed', 'pending', 'idle'):
            self.assertEqual(self.stop(background_tasks=[{'id': 'task', 'status': status}])['decision'], 'block')

    def test_session_crons_do_not_count(self):
        self.assertEqual(self.stop(session_crons=[{'id': 'later', 'cron': '* * * * *'}])['decision'], 'block')

    def test_runtime_without_task_snapshot_does_not_invent_running_work(self):
        payload = self.payload()
        del payload['background_tasks']
        self.assertEqual(H.decide(self.board, self.state, payload)['decision'], 'block')

    def test_missing_handoff_stops_reprompting_and_reports_once(self):
        self.stop()
        self.stop(stop_hook_active=True)
        self.assertEqual(self.stop(stop_hook_active=True), {})
        self.assertEqual(self.stop(stop_hook_active=True), {})
        self.assertEqual(len(self.board.logs), 1)
        self.assertIn('handoff_incomplete', self.board.logs[0])

    def test_failure_preserves_raw_error_and_kind_without_blocking(self):
        payload = self.payload('StopFailure', error='oauth_org_not_allowed',
                               last_assistant_message='Organization disabled subscription access')
        before = copy.deepcopy(self.board.page)
        self.assertEqual(H.decide(self.board, self.state, payload), {})
        self.assertIn('oauth_org_not_allowed', self.board.logs[0])
        self.assertIn('Organization disabled', self.board.logs[0])
        self.assertEqual(self.board.page, before)

    def test_old_session_cannot_modify_replacement_card(self):
        self.board.page['properties']['Session']['rich_text'][0]['plain_text'] = 'new-session'
        self.assertEqual(self.stop(), {})
        self.assertFalse(self.board.logs)

    def test_fast_stop_uses_delivery_binding_before_notion_session_catches_up(self):
        H.bind_session('inboard-card-' + CARD.replace('-', ''), SID)
        self.board.page['properties']['Session']['rich_text'][0]['plain_text'] = 'previous-session'
        self.assertEqual(self.stop()['decision'], 'block')
        H.bind_session('inboard-card-' + CARD.replace('-', ''), '33333333-3333-4333-8333-333333333333')
        self.assertEqual(self.stop(), {})

    def test_not_bound_dispatcher_skips_notion(self):
        with patch.object(H.W, 'load_board', side_effect=AssertionError('unexpected Notion request')):
            self.assertEqual(H.handle(self.payload()), {})

    def test_binding_and_events_survive_separate_hook_processes(self):
        H.bind_session('inboard-card-' + CARD.replace('-', ''), SID)
        H.handle(self.payload('UserPromptSubmit'), self.board)
        self.assertEqual(H.handle(self.payload(), self.board)['decision'], 'block')
        saved = json.loads(H.session_path(SID).read_text())
        self.assertEqual(saved['blocks'], 1)
        self.assertEqual(saved['card'], CARD)

    def test_retirement_keeps_waiting_worker_until_background_completion(self):
        import agent_deliver as A
        H.bind_session('inboard-card-' + CARD.replace('-', ''), SID)
        self.board.page['properties']['Status']['select']['name'] = C.status_name('needs_you')
        job = {'short': 'worker', 'sessionId': SID, 'state': 'idle'}
        with patch.object(A, 'find_job', return_value=job), patch.object(A.subprocess, 'run') as run:
            for tasks in (None, [{'id': 'watcher', 'status': 'running'}],
                          [{'id': 'result', 'status': 'pending'}]):
                H.handle(self.payload(background_tasks=tasks), self.board)
                self.assertFalse(A.retire('inboard-card-' + CARD.replace('-', '')))
                run.assert_not_called()
            H.handle(self.payload(background_tasks=[{'id': 'watcher', 'status': 'completed'}]), self.board)
            self.assertTrue(A.retire('inboard-card-' + CARD.replace('-', '')))
            self.assertEqual([c.args[0][:2] for c in run.call_args_list],
                             [['claude', 'stop'], ['claude', 'rm']])

    def test_new_delivery_and_new_user_turn_invalidate_retirement_snapshot(self):
        name = 'inboard-card-' + CARD.replace('-', '')
        H.bind_session(name, SID)
        self.board.page['properties']['Status']['select']['name'] = C.status_name('awaiting')
        H.handle(self.payload(), self.board)
        self.assertTrue(H.retirement_ready(SID))
        H.bind_session(name, SID, pending=True)
        self.assertFalse(H.retirement_ready(SID))
        H.handle(self.payload(), self.board)
        H.handle(self.payload('UserPromptSubmit'), self.board)
        self.assertFalse(H.retirement_ready(SID))

    def test_missing_snapshot_failed_or_blocked_stop_never_allows_retirement(self):
        self.assertFalse(H.retirement_ready(SID))
        H.bind_session('inboard-card-' + CARD.replace('-', ''), SID)
        H.handle(self.payload(), self.board)
        self.assertFalse(H.retirement_ready(SID))
        H.handle(self.payload('StopFailure', error='offline'), self.board)
        self.assertFalse(H.retirement_ready(SID))

    def test_working_session_is_not_retired_even_with_previous_clear_snapshot(self):
        import agent_deliver as A
        with patch.object(A, 'find_job', return_value={'state': 'working'}), \
                patch.object(A.subprocess, 'run') as run:
            self.assertFalse(A.retire('worker'))
            run.assert_not_called()

    def test_failed_notion_write_is_logged_and_not_falsely_acknowledged(self):
        H.bind_session('inboard-card-' + CARD.replace('-', ''), SID)
        with patch.object(self.board, 'log', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                H.handle(self.payload('StopFailure', error='billing_error'), self.board)
        saved = json.loads(H.session_path(SID).read_text())
        self.assertNotIn('reported_failure', saved)
        self.assertIn('offline', (Path(self.temp.name) / 'card-hooks.log').read_text())


if __name__ == '__main__':
    unittest.main()
