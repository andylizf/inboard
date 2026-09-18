"""The immediate retry after a refused card session, with the daemon and switchboard faked."""
import argparse
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
import refusal_retry as R
import wakeups as W

CARD = '22222222-2222-4222-8222-222222222222'


class Board:
    def __init__(self):
        self.sessions = []

    def session(self, a):
        self.sessions.append(a.set)


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, INBOARD_STATE=self.temp.name, INBOARD_LOGS=self.temp.name)
        env.start()
        self.addCleanup(env.stop)
        self.transcript = Path(self.temp.name) / 't.jsonl'
        rows = [{'type': 'user', 'message': {'content': R.PREFIX + 'Scheduled wakeup for card X. Receipt: tok.'}},
                {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'limit'}]}}]
        self.transcript.write_text('\n'.join(json.dumps(r) for r in rows))
        W.save(W.root() / f'{CARD}.json', {'card': CARD, 'token': 'tok', 'rules': [], 'state': 'failed',
                                            'delivered_at': W.now().isoformat()})
        self.board = Board()
        self.sent = []

    def test_replays_the_last_prompt_without_the_delivery_prefix(self):
        rc = R.retry(CARD, 'old-sid', str(self.transcript), recover=lambda emit: True, wait=lambda not_pid=None: True,
                     send=lambda card, prompt: self.sent.append(prompt) or 'new-sid', board=self.board)
        self.assertEqual(rc, 0)
        self.assertEqual(self.sent, ['Scheduled wakeup for card X. Receipt: tok.'])
        self.assertEqual(self.board.sessions, ['new-sid'])
        rec = json.loads((W.root() / f'{CARD}.json').read_text())
        self.assertEqual((rec['state'], rec['token'], rec['retried_from']), ('pending', 'tok', 'old-sid'))

    def test_after_a_restart_the_wait_excludes_the_old_daemon(self):
        waited = []
        with patch.object(R, 'supervisor_pid', return_value=4242):
            R.retry(CARD, 'old-sid', str(self.transcript), recover=lambda emit: 'restarted',
                    wait=lambda not_pid=None: waited.append(not_pid) or True,
                    send=lambda card, prompt: 'new-sid', board=self.board)
            R.retry(CARD, 'old-sid', str(self.transcript), recover=lambda emit: True,
                    wait=lambda not_pid=None: waited.append(not_pid) or True,
                    send=lambda card, prompt: 'new-sid', board=self.board)
        self.assertEqual(waited, [4242, None])

    def test_busy_daemon_is_waited_for_then_handed_to_the_sweep(self):
        answers = iter(['busy', 'busy', 'restarted'])
        with patch.object(R, 'BUSY_WAIT', 60), patch.object(R.time, 'sleep', lambda s: None):
            rc = R.retry(CARD, 'old-sid', str(self.transcript), recover=lambda emit: next(answers),
                         wait=lambda not_pid=None: True, send=lambda card, prompt: 'new-sid', board=self.board)
        self.assertEqual((rc, self.board.sessions), (0, ['new-sid']))
        with patch.object(R, 'BUSY_WAIT', 0), patch.object(R.time, 'sleep', lambda s: None):
            rc = R.retry(CARD, 'old-sid', str(self.transcript), recover=lambda emit: 'busy',
                         wait=lambda not_pid=None: True, send=lambda card, prompt: 'x', board=self.board)
        self.assertEqual(rc, 1)

    def test_no_other_account_leaves_the_delivery_failed_for_the_sweep(self):
        rc = R.retry(CARD, 'old-sid', str(self.transcript), recover=lambda emit: False, wait=lambda not_pid=None: True,
                     send=lambda card, prompt: self.sent.append(prompt) or 'x', board=self.board)
        self.assertEqual(rc, 1)
        self.assertEqual(self.sent, [])
        self.assertEqual(json.loads((W.root() / f'{CARD}.json').read_text())['state'], 'failed')

    def test_daemon_not_back_is_a_failure_not_a_send(self):
        rc = R.retry(CARD, 'old-sid', str(self.transcript), recover=lambda emit: True, wait=lambda not_pid=None: False,
                     send=lambda card, prompt: self.sent.append(prompt) or 'x', board=self.board)
        self.assertEqual((rc, self.sent), (1, []))


if __name__ == '__main__':
    unittest.main()
