import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
os.environ['INBOARD_CONFIG'] = str(ROOT / 'inboard.config.example.yaml')
import daemon_pending as P
import daemon_stall_check as S
import ibconfig as C


class StallRecoveryTests(unittest.TestCase):
    def test_busy_or_unknown_worker_remains_tracked_then_idle_is_reported(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(P, 'STATE', Path(directory) / 'pending.json'):
            for busy in (True, None):
                P.record('card', 'Send', now=0)
                self.assertEqual(P.sweep(lambda _: 'Send', 10, now=20, busy=lambda _: busy), [])
                self.assertEqual(len(json.loads(P.STATE.read_text())), 1)
            self.assertEqual(P.sweep(lambda _: 'Send', 10, now=21, busy=lambda _: False),
                             [{'card': 'card', 'action': 'Send'}])

    def test_timeout_requests_verification_without_revoking_approval_or_sending(self):
        from contextlib import nullcontext
        import action_runs as A
        with patch.object(S, '_cfg', return_value='45'), \
                patch.object(P, 'sweep', return_value=[{'card': 'card', 'action': 'Send'}]), \
                patch.object(S, '_actionof', return_value='Send'), \
                patch.object(A, 'lock', return_value=nullcontext()), \
                patch.object(A, 'read', return_value={'token': 'approved-token'}), \
                patch('agent_deliver.ensure_and_deliver') as deliver, \
                patch.object(S.subprocess, 'run') as run:
            S.main()
            prompt = deliver.call_args.args[2]
            self.assertIn('verification-only', prompt)
            self.assertIn('do not send', prompt)
            self.assertIn('approved-token', prompt)
            run.assert_not_called()

    def test_legacy_new_values_resolve_to_researching(self):
        for value in ('new', '📥 New', '📥 新'):
            self.assertEqual(C.status_name(value), C.status_name('researching'))
        self.assertNotIn('new', C.STATUS)
        self.assertNotIn('new', C.STATUS_ORDER)


if __name__ == '__main__':
    unittest.main()
