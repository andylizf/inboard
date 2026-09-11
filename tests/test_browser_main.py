import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class MainBrowserTests(unittest.TestCase):
    def test_wrapper_creates_isolated_main_lane_and_reuses_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            tool = directory / 'web-plane'
            tool.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$CALLS"
if [[ "$1" == lane && "$3" == get && ! -f "$READY" ]]; then
  echo "web-plane: lane '$2' has no web-plane session mapping"
  exit 1
fi
if [[ "$1" == -s=main && "$2" == attach ]]; then touch "$READY"; fi
''')
            tool.chmod(0o755)
            env = dict(os.environ, PATH=f'{tmp}:{os.environ["PATH"]}',
                       CALLS=f'{tmp}/calls', READY=f'{tmp}/ready',
                       INBOARD_BROWSER_LANE='card-one')
            for args in [('open', 'https://example.com'), ('snapshot', '-i')]:
                subprocess.run(['bash', str(ROOT / 'bin/browser'), *args], env=env, check=True)
            calls = (directory / 'calls').read_text().splitlines()
            self.assertEqual(calls.count('-s=main attach --as inboard-card-one about:blank'), 1)
            self.assertIn('lane inboard-card-one open https://example.com', calls)
            self.assertIn('lane inboard-card-one snapshot -i', calls)

    def test_main_discovery_ignores_helpers_and_other_profiles(self):
        loader = importlib.machinery.SourceFileLoader('test_shim', str(ROOT / 'bin/webauthn-shim'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        with patch('sys.argv', ['webauthn-shim', 'main']):
            loader.exec_module(module)
        profile = os.path.expanduser('~/.web-plane/profiles/main')
        commands = (f'Chrome --type=renderer --user-data-dir={profile} --remote-debugging-port=1\n'
                    f'Chrome --user-data-dir={profile}-other --remote-debugging-port=2\n'
                    f'Chrome --user-data-dir={profile} --remote-debugging-port=60664\n')
        with patch.object(module.subprocess, 'check_output', return_value=commands):
            self.assertEqual(module.main_port(), 60664)
        with patch.object(module.subprocess, 'check_output', return_value=''):
            self.assertIsNone(module.main_port())
