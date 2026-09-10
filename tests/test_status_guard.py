"""Status restoration against synthetic Notion events; no live cards or sends."""
import argparse
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from test_wakeups import B


class StatusGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, INBOARD_STATE=self.temp.name)
        env.start()
        self.addCleanup(env.stop)
        self.record = Path(self.temp.name) / 'status' / 'card'
        self.record.parent.mkdir()
        self.record.write_text('Waiting')
        self.page = {'id': 'card', 'last_edited_by': {'id': 'human'},
                     'last_edited_time': '2026-09-01T12:00:00Z',
                     'properties': {'Status': {'id': 'status-id', 'select': {'name': 'Done'}}}}
        self.event = {'type': 'page.properties_updated', 'entity': {'id': 'card'},
                      'authors': [{'id': 'human', 'type': 'person'}],
                      'timestamp': '2026-09-01T12:00:00Z',
                      'data': {'updated_properties': ['status-id']}}
        self.writes = []

    def api(self, method, path, body=None):
        if method == 'GET':
            return copy.deepcopy(self.page)
        self.writes.append(body)
        self.page['properties'].update(body['properties'])
        return copy.deepcopy(self.page)

    def guard(self):
        B.guard_status(argparse.Namespace(card='card', event=json.dumps(self.event)))

    def test_human_status_edit_restored_once(self):
        with patch.object(B, '_api', side_effect=self.api), patch.object(B, 'reply') as reply:
            self.guard()
            self.guard()
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.page['properties']['Status']['select']['name'], 'Waiting')
        reply.assert_called_once()

    def test_bot_agent_missing_and_mixed_authors_never_restore(self):
        for authors in ([], [{'type': 'bot'}], [{'type': 'agent'}],
                        [{'type': 'person'}, {'type': 'bot'}]):
            self.event['authors'] = authors
            with patch.object(B, '_api') as api, patch.object(B, 'reply') as reply:
                self.guard()
                api.assert_not_called()
                reply.assert_not_called()

    def test_unrelated_stale_or_superseded_human_event_never_restores(self):
        for change in ('property', 'time', 'editor', 'action', 'missing-record'):
            with self.subTest(change=change):
                event, page = copy.deepcopy(self.event), copy.deepcopy(self.page)
                if change == 'property':
                    self.event['data']['updated_properties'] = ['title-id']
                elif change == 'time':
                    self.page['last_edited_time'] = '2026-09-01T12:01:00Z'
                elif change == 'editor':
                    self.page['last_edited_by'] = {'id': 'bot'}
                elif change == 'action':
                    self.page['properties']['Action'] = {'select': {'name': 'Continue'}}
                else:
                    self.record.unlink()
                with patch.object(B, '_api', side_effect=self.api), patch.object(B, 'reply') as reply:
                    self.guard()
                    reply.assert_not_called()
                self.assertEqual(self.writes, [])
                self.event, self.page = event, page

    def test_guard_cannot_read_between_agent_write_and_record(self):
        remote_written, release_writer, guard_read = (threading.Event() for _ in range(3))
        errors = []

        def api(method, path, body=None):
            result = self.api(method, path, body)
            if method == 'PATCH':
                remote_written.set()
                if not release_writer.wait(5):
                    raise RuntimeError('test writer timed out')
            else:
                guard_read.set()
            return result

        def run(fn):
            try:
                fn()
            except Exception as exc:
                errors.append(exc)

        with patch.object(B, '_api', side_effect=api), patch.object(B, 'reply') as reply:
            writer = threading.Thread(target=run, args=(lambda: B.api('PATCH', '/pages/card',
                {'properties': {'Status': {'select': {'name': 'Done'}}}}),))
            writer.start()
            self.assertTrue(remote_written.wait(5))
            guard = threading.Thread(target=run, args=(self.guard,))
            guard.start()
            try:
                self.assertFalse(guard_read.wait(0.1))
            finally:
                release_writer.set()
                writer.join(5)
                guard.join(5)
            self.assertFalse(writer.is_alive() or guard.is_alive())
            reply.assert_not_called()
        self.assertEqual(errors, [])
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.record.read_text(), 'Done')

    def test_failed_remote_write_keeps_previous_record(self):
        with patch.object(B, '_api', side_effect=RuntimeError('Notion unavailable')):
            with self.assertRaises(RuntimeError):
                B.api('PATCH', '/pages/card', {'properties': {'Status': {'select': {'name': 'Done'}}}})
        self.assertEqual(self.record.read_text(), 'Waiting')

    def test_failed_record_write_does_not_leave_stale_status(self):
        with patch.object(B.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                B.remember_status('card', 'Done')
        self.assertFalse(self.record.exists())


if __name__ == '__main__':
    unittest.main()
