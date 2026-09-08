import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import agent_deliver as A


class DiscoveryTests(unittest.TestCase):
    def test_errors_distinguish_timeout_refusal_and_missing_socket(self):
        for error in (TimeoutError('timed out'), ConnectionRefusedError('refused')):
            with self.subTest(error=error), patch.object(A, '_sock_candidates', return_value=['test.sock']), \
                 patch.object(A, '_call', side_effect=error):
                with self.assertRaisesRegex(A.DaemonError, type(error).__name__):
                    A.live_control_sock()
        with patch.object(A, '_sock_candidates', return_value=[]):
            with self.assertRaisesRegex(A.DaemonError, 'no socket paths found'):
                A.live_control_sock()

    def test_stale_socket_does_not_hide_live_socket(self):
        with patch.object(A, '_sock_candidates', return_value=['stale', 'live']), \
             patch.object(A, '_call', side_effect=[ConnectionRefusedError(), {'ok': True, 'op': 'ping'}]):
            self.assertEqual(A.live_control_sock(), 'live')
