"""Preserve legacy requests in card history, then remove their separate property."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import wakeups as W


def pages(board):
    cursor = None
    while True:
        query = {'page_size': 100}
        if cursor:
            query['start_cursor'] = cursor
        batch = board.api('POST', f'/databases/{board.DB}/query', query)
        yield from batch['results']
        if not batch.get('has_more'):
            return
        cursor = batch['next_cursor']


def history(board, card):
    cursor = None
    while True:
        path = f'/blocks/{card}/children?page_size=100'
        if cursor:
            path += '&start_cursor=' + cursor
        batch = board.api('GET', path)
        for block in batch['results']:
            yield ''.join(r.get('plain_text', r.get('text', {}).get('content', ''))
                          for r in block.get(block['type'], {}).get('rich_text', []))
        if not batch.get('has_more'):
            return
        cursor = batch['next_cursor']


def migrate(backup, apply=False):
    board = W.load_board()
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    schema = board.api('GET', f'/databases/{board.DB}')
    snapshot = backup / 'schema-before.json'
    if not snapshot.exists():
        W.save(snapshot, schema)
    source = Path(__file__).read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    (backup / f'migration-{digest}.py').write_bytes(source)
    with (backup / 'migration.jsonl').open('a') as log:
        def event(**row):
            value = dict(time=W.now().isoformat(), apply=apply, source_sha256=digest, **row)
            print(json.dumps(value), file=log, flush=True)
            print(json.dumps(value), flush=True)
        if 'NeedsYou' not in schema['properties']:
            event(state='already_removed')
            return
        seen = {}
        for page in pages(board):
            card = page['id']
            request = board._g(page['properties'], 'NeedsYou', 'rich_text') or ''
            seen[card] = request
            serialized = json.dumps(page, ensure_ascii=False).encode()
            path = backup / f'{card}-{hashlib.sha256(serialized).hexdigest()}.json'
            if not path.exists():
                path.write_bytes(serialized)
            assert json.loads(path.read_text()) == page
            event(card=card, state='start', snapshot=path.name, characters=len(request))
            if request and apply:
                # Historical text is preserved without reasserting a stale request in Summary.
                record = 'Legacy operator request (historical; current action is in Summary):\n' + request
                if record not in set(history(board, card)):
                    board.api('PATCH', f'/blocks/{card}/children', {'children': [{
                        'object': 'block', 'type': 'paragraph',
                        'paragraph': {'rich_text': W.text(record)}}]})
                if record not in set(history(board, card)):
                    raise RuntimeError(f'History readback failed for {card}; property retained')
            event(card=card, state='preserved' if apply else 'planned')
        if apply:
            current = {p['id']: board._g(p['properties'], 'NeedsYou', 'rich_text') or ''
                       for p in pages(board)}
            if current != seen:
                raise RuntimeError('Cards or requests changed; rerun before removing the property')
            board.api('PATCH', f'/databases/{board.DB}', {'properties': {'NeedsYou': None}})
            after = board.api('GET', f'/databases/{board.DB}')
            assert 'NeedsYou' not in after['properties']
            W.save(backup / 'schema-after.json', after)
        event(state='complete', cards=len(seen), requests=sum(bool(r) for r in seen.values()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    migrate(args.backup_dir, args.apply)
