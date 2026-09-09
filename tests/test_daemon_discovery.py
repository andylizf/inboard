import sys
from pathlib import Path
import unittest
import tempfile
import shutil
import subprocess
import json
import os
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import agent_deliver as A


class DiscoveryTests(unittest.TestCase):
    def test_spawn_does_not_consume_controller_input(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            stub = root / 'claude'
            stub.write_text('#!/bin/bash\ncat > inherited-input\necho "backgrounded · abcdef12 · test"\n')
            stub.chmod(0o755)
            driver = root / 'driver.py'
            driver.write_text(
                f'import sys\nsys.path.insert(0, {str(Path(A.__file__).parent)!r})\n'
                f'import agent_deliver as A\nprint(A.spawn("test", {td!r}))\n')
            result = subprocess.run([sys.executable, str(driver)], input='controller-only instruction\n',
                                    env=dict(os.environ, PATH=td + os.pathsep + os.environ['PATH']),
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), 'abcdef12')
            self.assertEqual((root / 'inherited-input').read_text(), '')

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

    def test_launch_wrapper_waits_for_existing_supervisor(self):
        root_path = Path(__file__).resolve().parents[1]
        for alive in (True, False):
            with self.subTest(alive=alive), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / '.claude').mkdir()
                (root / 'bin').mkdir()
                stub = root / 'bin/claude'
                stub.write_text('#!/bin/bash\necho spawned\n')
                stub.chmod(0o755)
                (root / '.claude/daemon.status.json').write_text(json.dumps(
                    {'supervisorPid': os.getpid()} if alive else {}))
                shutil.copy(root_path / 'engines/daemon-launch.sh', root / 'daemon-launch.sh')
                (root / '_common.sh').write_text('''
export PATH="$HOME/bin:$PATH"
''')
                # Process mocks must exist before the launcher reads credentials.
                result = subprocess.run(['bash', '-c', '''
ps() { echo /usr/bin/claude; }
sleep() { exit 42; }
export -f ps sleep
exec bash "$1"
''', 'bash', str(root / 'daemon-launch.sh')],
                                        env=dict(os.environ, HOME=td, CLAUDE_CODE_OAUTH_TOKEN='test'),
                                        capture_output=True, text=True)
                if alive:
                    self.assertEqual(result.returncode, 42, result.stderr)
                    self.assertNotIn('spawned', result.stdout)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('spawned', result.stdout)
