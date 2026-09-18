import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
os.environ.setdefault('INBOARD_CONFIG', str(Path(__file__).resolve().parents[1] / 'inboard.config.example.yaml'))
import action_runs as AR
import shell_actions as S

CARD = '00000000-0000-4000-8000-000000000001'


class ShellActionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        env = patch.dict(os.environ, INBOARD_STATE=str(self.folder / 'state'))
        env.start()
        self.addCleanup(env.stop)
        self.page = {'id': CARD, 'properties': {
            AR.REQUEST: {'select': {'name': S.ACTION}}, AR.VERSION: {'number': 1},
            'Session': {'rich_text': AR.W.text('original-session')}}}
        self.board = Mock()

        def api(method, path, body=None):
            if method == 'PATCH':
                self.page['properties'].update(body['properties'])
            return copy.deepcopy(self.page)
        self.board.api.side_effect = api
        self.script = self.folder / 'source.sh'
        self.script.write_text("printf 'shell-output\\n'\nexit 7\n")
        self.data = S.stage(self.board, CARD, self.script, self.folder, 'Print a test marker', [])
        self.plan = S.directory(CARD, self.data['plan'])
        self.page['properties'][S.APPROVED] = copy.deepcopy(self.page['properties'][S.SCRIPT])
        self.job = dict(short='12345678', sessionId='original-session', state='idle')

    def test_email_staging_creates_a_guarded_script_without_sending(self):
        preview = 'From: sender@example.com\nTo: to@example.com\n\n---\n\nHello'
        self.page['properties']['Draft'] = {'rich_text': AR.W.text(preview)}
        with patch('subprocess.run') as execute:
            data = S.stage_email(self.board, CARD, 'personal', 'draft-1')
        execute.assert_not_called()
        script = (S.directory(CARD, data['plan']) / 'script.sh').read_text()
        self.assertIn('personal gmail +send-approved', script)
        self.assertIn('--draft-id draft-1 --operation "$INBOARD_OPERATION"', script)
        self.assertEqual(data['draft'], preview)
        self.assertEqual(AR.property_text(self.page, 'Draft'), preview)
