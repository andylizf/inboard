import base64
import argparse
import importlib.machinery
import importlib.util
import json
import io
from email import policy
from email.parser import BytesParser
from pathlib import Path
from subprocess import CompletedProcess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('inboard_email', str(ROOT / 'bin/email'))
spec = importlib.util.spec_from_loader(loader.name, loader)
email_cli = importlib.util.module_from_spec(spec)
loader.exec_module(email_cli)


class DraftPreviewTests(unittest.TestCase):
    def test_draft_edit_after_validation_blocks_submission(self):
        import action_runs as A
        import copy
        import tempfile
        first = {'id': 'card-1', 'properties': {
            A.REQUEST: {'select': {'name': 'Send'}}, A.VERSION: {'number': 1},
            A.APPROVED_DRAFT: {'rich_text': A.W.text('Hello')},
            'Draft': {'rich_text': A.W.text('Hello')}}}
        changed = copy.deepcopy(first)
        changed['properties']['Draft'] = {'rich_text': A.W.text('New wording')}
        record = dict(A.intent(first), phase='running', sent=False)
        responses = [first, changed]
        draft = {'message': {'payload': {'mimeType': 'text/plain',
                 'body': {'data': base64.urlsafe_b64encode(b'Hello').decode()}}}}
        with tempfile.TemporaryDirectory() as state, patch.dict('os.environ', NOTION_TOKEN='test', INBOARD_STATE=state), \
                patch.object(email_cli.C, 'get', return_value='Send'), patch.object(A, 'read', return_value=record), \
                patch('urllib.request.urlopen', side_effect=lambda *a, **k: io.BytesIO(json.dumps(responses.pop(0)).encode())), \
                patch('subprocess.run', return_value=CompletedProcess([], 0, json.dumps(draft), '')) as run:
            with self.assertRaisesRegex(RuntimeError, '草稿已修改'):
                email_cli.send_approved({}, 'gws', ['--card', 'card-1', '--draft-id', 'draft-1', '--operation', record['token']])
        self.assertEqual(run.call_count, 1)
        self.assertIn('get', run.call_args.args[0])

    def test_empty_current_draft_never_searches_history_or_calls_gmail(self):
        page = {'properties': {'Action': {'select': {'name': 'Send'}}, 'Draft': {'rich_text': []}}}
        with patch.dict('os.environ', NOTION_TOKEN='test'), patch.object(email_cli.C, 'get', return_value='Send'), \
                patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(page).encode())) as notion, \
                patch('subprocess.run') as run, self.assertRaises(SystemExit):
            email_cli.send_approved({}, 'gws', ['--card', 'card-1', '--draft-id', 'draft-1'])
        run.assert_not_called()
        self.assertEqual(notion.call_count, 1)

    def test_replacement_click_blocks_send_before_submission(self):
        import action_runs as A
        first = {'id': 'card-1', 'properties': {
            A.REQUEST: {'select': {'name': 'Send'}},
            A.WHEN: {'date': {'start': '2026-09-07T03:00:00Z'}},
            A.APPROVED_DRAFT: {'rich_text': [{'plain_text': 'Hello'}]},
            'Draft': {'rich_text': [{'plain_text': 'Hello'}]}}}
        replacement = {'id': 'card-1', 'properties': {
            A.REQUEST: {'select': {'name': 'Continue'}},
            A.WHEN: {'date': {'start': '2026-09-07T03:00:01Z'}}}}
        record = dict(A.intent(first), phase='running', sent=False)
        responses = [first, replacement]
        draft = {'message': {'payload': {'mimeType': 'text/plain',
                 'body': {'data': base64.urlsafe_b64encode(b'Hello').decode()}}}}
        import tempfile
        with tempfile.TemporaryDirectory() as state, patch.dict('os.environ', NOTION_TOKEN='test-token', INBOARD_STATE=state), \
                patch.object(email_cli.C, 'get', return_value='Send'), patch.object(A, 'read', return_value=record), \
                patch('urllib.request.urlopen', side_effect=lambda *a, **k: io.BytesIO(json.dumps(responses.pop(0)).encode())), \
                patch('subprocess.run', return_value=CompletedProcess([], 0, json.dumps(draft), '')) as run:
            with self.assertRaisesRegex(RuntimeError, 'superseded'):
                email_cli.send_approved({}, 'gws', ['--card', 'card-1', '--draft-id', 'draft-1', '--operation', record['token']])
        self.assertEqual(run.call_count, 1)
        self.assertIn('get', run.call_args.args[0])

    def test_approved_send_places_draft_id_in_request_body(self):
        from email.header import Header
        preview = 'From: sender@example.com\nTo: to@example.com\nCc: 无\nBcc: 无\nSubject: 你好\n\n---\n\nHello'
        responses = [
            {'properties': {'Action': {'select': {'name': 'Send'}},
                            'Draft': {'rich_text': [{'plain_text': preview}]}}},
            {}]
        draft = {'message': {'payload': {'mimeType': 'text/plain',
                 'headers': [{'name': 'From', 'value': 'sender@example.com'},
                             {'name': 'To', 'value': 'to@example.com'},
                             {'name': 'Subject', 'value': Header('你好', 'utf-8').encode()}],
                 'body': {'data': base64.urlsafe_b64encode(b'Hello').decode()}}}}
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            return CompletedProcess(cmd, 0, json.dumps(draft) if 'get' in cmd else '{}', '')

        with patch.dict('os.environ', NOTION_TOKEN='test-token'), \
                patch.object(email_cli.C, 'get', return_value='Send'), \
                patch('urllib.request.urlopen', side_effect=lambda *a, **k: io.BytesIO(json.dumps(responses.pop(0)).encode())), \
                patch('subprocess.run', side_effect=run), self.assertRaises(SystemExit) as stop:
            email_cli.send_approved({}, 'gws', ['--card', 'card-1', '--draft-id', 'draft-1'])
        self.assertEqual(stop.exception.code, 0)
        send = next(c for c in calls if 'send' in c)
        self.assertEqual(json.loads(send[send.index('--params') + 1]), {'userId': 'me'})
        self.assertEqual(json.loads(send[send.index('--json') + 1]), {'id': 'draft-1'})
        self.assertFalse(responses)

    def test_long_preview_survives_card_storage(self):
        import wakeups
        board = wakeups.load_board()
        preview = 'From: sender@example.com\nTo: to@example.com\n\n---\n\n' + '正文' * 2000
        args = argparse.Namespace(card='card-1', draft=preview, status=None, needs=None,
                                  subject=None, sender=None, due=None)
        with patch.object(board, 'api') as api:
            board.edit(args)
        runs = api.call_args.args[2]['properties']['Draft']['rich_text']
        self.assertEqual(''.join(r['text']['content'] for r in runs), preview)
        self.assertTrue(all(len(r['text']['content']) <= 2000 for r in runs))

    def create(self, args, original=None):
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            if 'get' in cmd:
                return CompletedProcess(cmd, 0, json.dumps(original), '')
            return CompletedProcess(cmd, 0, '{"id":"draft-1"}', '')

        with patch('subprocess.run', side_effect=run), self.assertRaises(SystemExit) as stop:
            email_cli.draft_for_card({}, 'gws', ['--card', 'card-1', '--body', 'Hello\n\nThanks', *args],
                                     'sender@example.com')
        self.assertEqual(stop.exception.code, 0)
        create = next(c for c in calls if 'create' in c)
        wire = json.loads(create[create.index('--json') + 1])['message']
        message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(wire['raw']))
        edit = next(c for c in calls if 'edit' in c)
        preview = edit[edit.index('--draft') + 1]
        self.assertEqual(message.get_content(), 'Hello\n\nThanks\n')
        self.assertEqual(str(message['From']), 'sender@example.com')
        self.assertEqual(preview.split('\n\n---\n\n', 1)[1], 'Hello\n\nThanks')
        self.assertFalse(any('send' in c for c in calls))
        return message, preview, wire

    def test_all_recipients_visible_but_headers_not_in_body(self):
        message, preview, _ = self.create(['--to', 'to@example.com', '--subject', 'Subject',
                                          '--cc', 'cc@example.com', '--bcc', 'bcc@example.com'])
        self.assertTrue(preview.startswith('From: sender@example.com\nTo: to@example.com\n'))
        for field, address in [('Cc', 'cc@example.com'), ('Bcc', 'bcc@example.com')]:
            self.assertEqual(str(message[field]), address)
            self.assertIn(f'{field}: {address}\n', preview)

    def test_reply_uses_resolved_recipient_and_empty_copy_fields(self):
        original = {'threadId': 'thread-1', 'payload': {'headers': [
            {'name': 'From', 'value': 'author@example.com'},
            {'name': 'Reply-To', 'value': 'reply@example.com'},
            {'name': 'Subject', 'value': 'Question'},
            {'name': 'Message-ID', 'value': '<original@example.com>'}]}}
        message, preview, wire = self.create(['--reply-to-message', 'message-1'], original)
        self.assertEqual(str(message['To']), 'reply@example.com')
        self.assertIn('To: reply@example.com\nCc: 无\nBcc: 无\nSubject: Re: Question', preview)
        self.assertEqual(wire['threadId'], 'thread-1')
        self.assertEqual(str(message['In-Reply-To']), '<original@example.com>')


if __name__ == '__main__':
    unittest.main()
