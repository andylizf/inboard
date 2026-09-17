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

    def dispatch(self):
        # shell_actions is invoked directly: a button click goes to the card's agent now,
        # so going through AR.dispatch would exercise a route that no longer exists.
        record = dict(AR.intent(self.page), phase='starting', sent=False)
        AR.save(CARD, record)
        with patch.object(AR.W, 'load_board', return_value=self.board), \
                patch('agent_deliver.find_job', return_value=self.job), \
                patch('agent_deliver.shell_input') as shell, \
                patch('agent_deliver.ensure_and_deliver') as model, \
                patch('agent_deliver.interrupt') as interrupt:
            S.dispatch(self.board, self.page, record, self.job)
            model.assert_not_called()
            interrupt.assert_not_called()
            return shell

    def test_button_uses_native_input_and_a_replayed_plan_is_refused(self):
        self.dispatch().assert_called_once()
        with self.assertRaisesRegex(RuntimeError, '已经触发过执行'):
            self.dispatch()

    def test_second_click_cannot_execute_same_plan(self):
        self.dispatch()
        self.page['properties'][AR.VERSION]['number'] += 1
        with self.assertRaisesRegex(RuntimeError, '已经触发'):
            self.dispatch()

    def test_preview_change_blocks_execution(self):
        self.page['properties'][S.SCRIPT] = {'rich_text': AR.W.text('changed')}
        with self.assertRaisesRegex(RuntimeError, '已修改'):
            self.dispatch()
        self.assertFalse((self.plan / 'dispatch.json').exists())

    def test_session_mismatch_blocks_execution(self):
        self.job['sessionId'] = 'different-session'
        with self.assertRaisesRegex(RuntimeError, '会话不一致'):
            self.dispatch()
        self.assertFalse((self.plan / 'dispatch.json').exists())

    def test_mutating_source_does_not_change_frozen_script(self):
        self.script.write_text('echo changed')
        S.approved(self.page)
        self.assertIn('shell-output', (self.plan / 'script.sh').read_text())

    def test_mutating_frozen_script_is_rejected(self):
        (self.plan / 'script.sh').write_text('echo changed')
        with self.assertRaisesRegex(RuntimeError, '脚本发生变化'):
            S.approved(self.page)

    def test_changed_input_is_rejected(self):
        data = S.stage(self.board, CARD, self.script, self.folder, 'Check an input', [self.script])
        self.page['properties'][S.APPROVED] = copy.deepcopy(self.page['properties'][S.SCRIPT])
        self.script.write_text('changed input')
        with self.assertRaisesRegex(RuntimeError, '输入文件已变化'):
            S.approved(self.page)

    def test_operation_preview_is_bound_to_script(self):
        self.assertEqual(AR.property_text(self.page, 'Draft'), 'Print a test marker')
        self.page['properties']['Draft'] = {'rich_text': AR.W.text('Different outward action')}
        with self.assertRaisesRegex(RuntimeError, '操作预览已修改'):
            self.dispatch()
        self.assertFalse((self.plan / 'dispatch.json').exists())

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

    def test_email_approval_requires_script_to_have_started(self):
        self.dispatch()
        record = AR.read(CARD)
        # No staged plan on the record: the ordinary approved-draft gate governs, because the
        # execution action is now an ordinary operation the agent carries out.
        with self.assertRaisesRegex(RuntimeError, '暂无已批准的当前草稿'):
            AR.require_approved_draft(CARD, record['token'], self.page)
        record['shell_plan'] = self.data['plan']
        AR.save(CARD, record)
        with self.assertRaisesRegex(RuntimeError, 'not executing'):
            AR.require_approved_draft(CARD, record['token'], self.page)

    def test_failed_shell_saves_output_exit_and_never_runs_twice(self):
        self.dispatch()
        with patch.object(AR.W, 'load_board', return_value=self.board):
            self.assertEqual(S.run(CARD, self.data['plan']), 7)
            with self.assertRaises(FileExistsError):
                S.run(CARD, self.data['plan'])
        result = json.loads((self.plan / 'result.json').read_text())
        self.assertEqual(result['exit_code'], 7)
        self.assertEqual(result['session'], 'original-session')
        self.assertIn('shell-output', (self.plan / 'output.log').read_text())
        self.assertEqual(AR.read(CARD)['phase'], 'failed')

    def test_successful_shell_receipt_does_not_complete_matter(self):
        self.script.write_text('echo success\n')
        data = S.stage(self.board, CARD, self.script, self.folder, 'Success test', [])
        self.page['properties'][S.APPROVED] = copy.deepcopy(self.page['properties'][S.SCRIPT])
        self.dispatch()
        with patch.object(AR.W, 'load_board', return_value=self.board):
            self.assertEqual(S.run(CARD, data['plan']), 0)
        self.assertNotIn('Status', self.page['properties'])
        self.assertEqual(AR.read(CARD)['phase'], 'done')

    def test_changed_preview_while_queued_prevents_shell_launch(self):
        self.dispatch()
        self.page['properties'][S.SCRIPT] = {'rich_text': AR.W.text('new preview')}
        with patch.object(AR.W, 'load_board', return_value=self.board), patch('subprocess.Popen') as process:
            self.assertEqual(S.run(CARD, self.data['plan']), 1)
        process.assert_not_called()

    def test_uncertain_delivery_cannot_be_retried(self):
        with patch('agent_deliver.shell_input', side_effect=RuntimeError('lost connection')):
            record = dict(AR.intent(self.page), phase='starting')
            with self.assertRaisesRegex(RuntimeError, 'lost connection'):
                S.dispatch(self.board, self.page, record, self.job)
        with self.assertRaisesRegex(RuntimeError, '已经触发'):
            S.approved(self.page)


if __name__ == '__main__':
    unittest.main()
