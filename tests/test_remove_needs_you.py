"""Removal must preserve requests before deleting their schema property."""
import argparse
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_wakeups import B, W, ROOT

spec = importlib.util.spec_from_file_location('remove_needs', ROOT / 'setup/remove_needs_you.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class RemovalTests(unittest.TestCase):
    def test_resume_after_append_preserves_text_once_before_schema_removal(self):
        request = 'Decision needed. ' * 200
        page = {'id': 'card', 'properties': {'NeedsYou': {'rich_text': [{'plain_text': request}]},
                                           'Summary': {'rich_text': [{'plain_text': 'Current state'}]}}}
        schema = {'properties': {'NeedsYou': {'rich_text': {}}, 'Summary': {'rich_text': {}}}}
        blocks = []
        fail = [True]

        def api(method, path, body=None):
            if path.startswith('/blocks/'):
                if method == 'PATCH':
                    blocks.extend(copy.deepcopy(body['children']))
                    if fail[0]:
                        fail[0] = False
                        raise RuntimeError('lost response after append')
                return {'results': copy.deepcopy(blocks), 'has_more': False}
            if method == 'POST':
                return {'results': [copy.deepcopy(page)], 'has_more': False}
            if method == 'PATCH':
                self.assertEqual(len(blocks), 1)
                self.assertIn(request, ''.join(t['text']['content'] for t in blocks[0]['paragraph']['rich_text']))
                schema['properties'].pop('NeedsYou')
            return copy.deepcopy(schema)

        with tempfile.TemporaryDirectory() as tmp, patch.object(W, 'load_board', return_value=B), \
                patch.object(B, 'api', side_effect=api):
            directory = Path(tmp)
            M.migrate(directory)
            self.assertEqual(blocks, [])
            with self.assertRaisesRegex(RuntimeError, 'lost response'):
                M.migrate(directory, apply=True)
            self.assertIn('NeedsYou', schema['properties'])
            original = (directory / 'schema-before.json').read_bytes()
            M.migrate(directory, apply=True)
            M.migrate(directory, apply=True)
            self.assertEqual(len(blocks), 1)
            self.assertNotIn('NeedsYou', schema['properties'])
            self.assertEqual((directory / 'schema-before.json').read_bytes(), original)
            self.assertEqual(B._g(page['properties'], 'Summary', 'rich_text'), 'Current state')

    def test_legacy_nonempty_request_fails_before_mutation_and_empty_clear_is_safe(self):
        args = argparse.Namespace(card='card', status='done', needs='Please decide', subject=None,
                                  draft=None, sender=None, due=None)
        with patch.object(B, 'api') as api:
            with self.assertRaisesRegex(SystemExit, 'No card changes'):
                B.edit(args)
            api.assert_not_called()
            args.needs = ''
            args.status = None
            B.edit(args)
            api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
