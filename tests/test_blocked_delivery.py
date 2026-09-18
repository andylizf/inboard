"""A worker blocked on the operator keeps its session when his reply arrives; only one that
never runs the delivery is replaced."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.environ['INBOARD_CONFIG'] = str(ROOT / 'inboard.config.example.yaml')
sys.path.insert(0, str(ROOT / 'lib'))
import agent_deliver as A
import card_hooks as H
import wakeups as W

NAME = 'inboard-card-33333333333343338333333333333333'
SID = '44444444-4444-4444-8444-444444444444'
NEW_SID = '55555555-5555-4555-8555-555555555555'
BLOCKED = {'short': 'aaaa1111', 'sessionId': SID, 'state': 'blocked', 'tempo': 'blocked',
           'needs': 'review the email on the card and click 📤 to send', 'name': NAME}
FRESH = {'short': 'bbbb2222', 'sessionId': NEW_SID, 'state': 'idle', 'name': NAME}


class BlockedDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'INBOARD_STATE': self.temp.name})
        env.start()
        self.addCleanup(env.stop)

    def prompt_hook(self, sid):
        H.session_path(sid).parent.mkdir(parents=True, exist_ok=True)
        H.session_path(sid).write_text(json.dumps({'card': 'x'}))
        H.handle({'session_id': sid, 'hook_event_name': 'UserPromptSubmit'})

    def test_hook_stamps_prompt_time_and_taken_up_reads_it(self):
        since = time.time()
        self.assertFalse(A._taken_up(NAME, SID, since, timeout=0.2))
        self.prompt_hook(SID)
        self.assertTrue(A._taken_up(NAME, SID, since, timeout=0.2))
        # A stamp older than the delivery is a previous turn, not this one.
        self.assertFalse(A._taken_up(NAME, SID, time.time() + 1, timeout=0.2))

    def test_reply_to_operator_blocked_worker_keeps_its_session(self):
        with patch.object(A, 'live_control_sock', return_value='sock'), \
                patch.object(A, 'find_job', return_value=dict(BLOCKED)), \
                patch.object(A, '_reply_with_retry', return_value={'ok': True, 'op': 'reply'}) as reply, \
                patch.object(A, '_taken_up', return_value=True), \
                patch.object(A, '_respawn') as respawn, \
                patch.object(A.subprocess, 'run') as run:
            r = A.ensure_and_deliver(NAME, '/cwd', 'he commented')
        self.assertEqual(r['sessionId'], SID)
        self.assertEqual(r['delivery'], 'blocked-worker-resumed')
        respawn.assert_not_called()
        run.assert_not_called()
        self.assertEqual(reply.call_args[0][0], 'aaaa1111')

    def test_worker_that_never_runs_the_delivery_is_replaced_and_redelivered(self):
        with patch.object(A, 'live_control_sock', return_value='sock'), \
                patch.object(A, 'find_job', return_value=dict(BLOCKED)), \
                patch.object(A, '_reply_with_retry', return_value={'ok': True, 'op': 'reply'}) as reply, \
                patch.object(A, '_taken_up', return_value=False), \
                patch.object(A, '_respawn', return_value=(dict(FRESH), 'bbbb2222')) as respawn:
            r = A.ensure_and_deliver(NAME, '/cwd', 'he commented')
        self.assertEqual(r['sessionId'], NEW_SID)
        self.assertEqual(r['delivery'], 'blocked-worker-replaced')
        respawn.assert_called_once()
        self.assertEqual([c[0][0] for c in reply.call_args_list], ['aaaa1111', 'bbbb2222'])

    def test_replacement_still_blocked_is_the_daemon_itself(self):
        with patch.object(A, 'live_control_sock', return_value='sock'), \
                patch.object(A, 'find_job', return_value=dict(BLOCKED)), \
                patch.object(A, '_reply_with_retry', return_value={'ok': True}), \
                patch.object(A, '_taken_up', return_value=False), \
                patch.object(A, '_respawn', return_value=(dict(BLOCKED, sessionId=NEW_SID), 'cccc3333')):
            with self.assertRaises(A.DaemonError):
                A.ensure_and_deliver(NAME, '/cwd', 'he commented')


if __name__ == '__main__':
    unittest.main()
