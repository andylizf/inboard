"""Back up and fold the legacy New status into Researching."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ibconfig as C
import wakeups as W


def migrate(backup, apply=False):
    board = W.load_board()
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    schema = board.api('GET', f'/databases/{board.DB}')
    old = {'📥 New', '📥 新', C.get('board.schema.status.new')}
    options = schema['properties']['Status']['select']['options']
    removed = [o for o in options if o['name'] in old]
    before = backup / 'schema-before.json'
    if not before.exists():
        W.save(before, schema)
    count = 0
    with (backup / 'migration.jsonl').open('a') as log:
        def event(**fields):
            row = dict(time=W.now().isoformat(), apply=apply, **fields)
            print(json.dumps(row, ensure_ascii=False), file=log, flush=True)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        for option in removed:
            cursor = None
            while True:
                query = {'filter': {'property': 'Status', 'select': {'equals': option['name']}}, 'page_size': 100}
                if cursor:
                    query['start_cursor'] = cursor
                result = board.api('POST', f'/databases/{board.DB}/query', query)
                for page in result['results']:
                    card = page['id']
                    path = backup / f'{card}.json'
                    if not path.exists():
                        W.save(path, page)
                    event(card=card, state='start')
                    if apply:
                        board.api('PATCH', f'/pages/{card}', {'properties': {
                            'Status': {'select': {'name': C.status_name('researching')}}}})
                        after = board.api('GET', f'/pages/{card}')
                        assert board._g(after['properties'], 'Status', 'select') == C.status_name('researching')
                    count += 1
                    event(card=card, state='done' if apply else 'planned')
                if not result.get('has_more'):
                    break
                cursor = result['next_cursor']
        if apply:
            for option in removed:
                result = board.api('POST', f'/databases/{board.DB}/query', {
                    'filter': {'property': 'Status', 'select': {'equals': option['name']}}, 'page_size': 1})
                if result['results']:
                    raise RuntimeError('New cards arrived; rerun before removing the option.')
            if removed:
                board.api('PATCH', f'/databases/{board.DB}', {'properties': {'Status': {'select': {
                    'options': [o for o in options if o['name'] not in old]}}}})
            after = board.api('GET', f'/databases/{board.DB}')
            assert not any(o['name'] in old for o in after['properties']['Status']['select']['options'])
            W.save(backup / 'schema-after.json', after)
        event(state='complete', cards=count, removed=[o['name'] for o in removed], backup=str(backup))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    migrate(args.backup_dir, args.apply)
