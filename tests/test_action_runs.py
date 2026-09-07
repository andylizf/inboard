import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import action_runs as A


def page(action='Continue', at='2026-09-07T03:00:00.123Z'):
    return {'id': 'test-card', 'properties': {
        A.REQUEST: {'select': {'name': action}}, A.WHEN: {'date': {'start': at}}}}


class ActionRunsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict('os.environ', INBOARD_STATE=self.temp.name)
        self.env.start()
        self.addCleanup(self.env.stop)

    def record(self, source, **updates):
        record = dict(A.intent(source), phase='running', sent=False, **updates)
        A.save(source['id'], record)
        return record

    def test_repeat_click_gets_distinct_receipt(self):
        first = A.intent(page())
        again = A.intent(page(at='2026-09-07T03:00:00.124Z'))
        changed = A.intent(page('Send'))
        self.assertNotEqual(first['token'], again['token'])
        self.assertNotEqual(first['token'], changed['token'])
        self.assertTrue(first['key'].endswith('123|Continue'))

    def test_counter_distinguishes_same_button_within_a_minute(self):
        first = page()
        first['properties'][A.VERSION] = {'number': 1}
        second = copy.deepcopy(first)
        second['properties'][A.VERSION]['number'] = 2
        self.assertEqual(A.intent(first)['key'], '1|Continue')
        self.assertNotEqual(A.intent(first)['token'], A.intent(second)['token'])

    def test_completed_request_does_not_retrigger(self):
        source = page()
        record = self.record(source)
        board = Mock()
        board.api.return_value = source
        A.receipt(board, source['id'], record['token'], 'done', 'Done')
        self.assertEqual(A.effective_action(source), '')
        self.assertEqual(A.effective_action(page('Send')), 'Send')
        patch_payload = board.api.call_args.args[2]['properties']
        self.assertNotIn('Action', patch_payload)
        self.assertNotIn(A.REQUEST, patch_payload)

    def test_old_completion_cannot_write_over_new_request(self):
        old = self.record(page())
        board = Mock()
        board.api.return_value = page('Send')
        with self.assertRaisesRegex(RuntimeError, 'superseded'):
            A.receipt(board, 'test-card', old['token'], 'done', 'Done')
        self.assertEqual(board.api.call_count, 1)

    def test_missing_token_is_rejected_on_modern_card(self):
        source = page()
        self.record(source)
        with self.assertRaises(RuntimeError):
            A.require_current('test-card', None, source)

    def test_late_patch_is_tagged_with_old_key(self):
        old = self.record(page())
        board = Mock()
        A.progress(board, 'test-card', old, 'Done')
        props = board.api.call_args.args[2]['properties']
        self.assertEqual(props[A.HANDLED]['rich_text'][0]['text']['content'], old['key'])
        self.assertNotEqual(old['key'], A.intent(page('Send'))['key'])

    def test_duplicate_webhook_does_not_deliver_twice(self):
        source = page()
        self.record(source)
        board = Mock()
        board.api.return_value = source
        with patch.object(A.W, 'load_board', return_value=board), patch('agent_deliver.ensure_and_deliver') as deliver:
            A.dispatch('test-card', 'Action __ACTION__')
        deliver.assert_not_called()

    def test_empty_or_changed_draft_does_not_interrupt_or_replace_running_operation(self):
        old = self.record(page())
        for current, approved in [('', ''), ('New draft', 'Old draft')]:
            source = page('Send')
            source['properties']['Draft'] = {'rich_text': A.W.text(current)}
            source['properties'][A.APPROVED_DRAFT] = {'rich_text': A.W.text(approved)}
            board = Mock()
            board.api.return_value = source
            with patch.object(A.C, 'get', return_value='Send'), patch.object(A.W, 'load_board', return_value=board), \
                    patch('agent_deliver.interrupt') as interrupt, patch('agent_deliver.ensure_and_deliver') as deliver:
                A.dispatch('test-card', 'Action __ACTION__')
            interrupt.assert_not_called()
            deliver.assert_not_called()
            self.assertEqual(A.read('test-card'), old)


if __name__ == '__main__':
    unittest.main()
