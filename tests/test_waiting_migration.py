"""Migration checkpoint and deadline preservation using synthetic Notion records."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_wakeups import B, W, ROOT

spec = importlib.util.spec_from_file_location('waiting_migration', ROOT / 'setup/migrate_waiting.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class MigrationTests(unittest.TestCase):
    def test_backup_resume_deadline_and_expiry_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = directory / 'config.yaml'
            config.write_text((ROOT / 'inboard.config.example.yaml').read_text())
            cfg = copy.deepcopy(W.C.load())
            cfg['board']['schema']['status']['awaiting'] = '⏳ Awaiting reply'
            cfg['board']['schema']['action_status'] = {'Ignore': 'done', 'Complete': 'done'}
            pages = {'open': {'id': 'open', 'properties': {
                'Status': {'select': {'name': '⏳ Awaiting reply'}},
                'Due': {'date': {'start': '2026-10-01'}}, 'Lapses': {'checkbox': True},
                'NeedsYou': {'rich_text': []}}},
                'closed': {'id': 'closed', 'properties': {'Status': {'select': {'name': B.S['done']}},
                    'Due': {'date': {'start': '2026-01-01'}}, 'Lapses': {'checkbox': True}}}}
            schema = {'properties': {'Status': {'select': {'options': [
                {'id': 'waiting-option', 'name': '⏳ Awaiting reply', 'color': 'yellow'}]}},
                'Place': {'place': {}}, 'Lapses': {'checkbox': {}}}}
            writes = []

            def api(method, path, body=None):
                if path.startswith('/databases/'):
                    if method == 'GET':
                        return copy.deepcopy(schema)
                    if method == 'POST':
                        return {'results': copy.deepcopy(list(pages.values())), 'has_more': False}
                    for k, v in body['properties'].items():
                        if v is None:
                            schema['properties'].pop(k, None)
                        else:
                            schema['properties'][k] = copy.deepcopy(v)
                    return {}
                card = path.rsplit('/', 1)[1]
                if method == 'GET':
                    return copy.deepcopy(pages[card])
                writes.append(card)
                pages[card]['properties'].update(copy.deepcopy(body['properties']))
                return {}

            with patch.dict(os.environ, INBOARD_CONFIG=str(config), INBOARD_STATE=str(directory / 'state')), \
                    patch.object(W.C, '_CACHE', cfg), patch.object(W, 'load_board', return_value=B), \
                    patch.object(B, 'api', side_effect=api):
                backup = directory / 'backup'
                M.migrate(backup)
                original = (backup / 'snapshot.json').read_bytes()
                self.assertFalse(writes)
                M.migrate(backup, apply=True, remove=True)
                self.assertEqual(writes, ['open'])
                self.assertEqual(pages['open']['properties']['Due']['date']['start'], '2026-10-01')
                self.assertEqual(len(W.read(pages['open'])), 3)
                self.assertTrue(any('Verify the actual cutoff' in r['reason'] for r in W.read(pages['open'])))
                self.assertEqual(pages['closed']['properties']['Status']['select']['name'], B.S['done'])
                self.assertNotIn('Lapses', schema['properties'])
                self.assertNotIn('Place', schema['properties'])
                self.assertEqual(cfg['board']['schema']['action_status']['Ignore'], 'cancelled')
                self.assertEqual(schema['properties']['Status']['select']['options'][0]['id'], 'waiting-option')
                M.migrate(backup, apply=True, remove=True)
                self.assertEqual(writes, ['open'])
                self.assertEqual((backup / 'snapshot.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
