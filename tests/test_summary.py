import argparse
from unittest import TestCase
from unittest.mock import patch
from test_wakeups import B


class SummaryTests(TestCase):
    def test_note_updates_property_without_touching_body_or_truncating(self):
        summary = 'Matter and next step. ' * 200
        with patch.object(B, 'api') as api:
            B.note(argparse.Namespace(card='test-card', text='📌 ' + summary))
        api.assert_called_once()
        method, path, body = api.call_args.args
        self.assertEqual((method, path), ('PATCH', '/pages/test-card'))
        self.assertEqual(''.join(r['text']['content'] for r in body['properties']['Summary']['rich_text']), summary)
        self.assertIn('Updated', body['properties'])
