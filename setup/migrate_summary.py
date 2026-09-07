"""Move the legacy state callout into Summary, with private per-card backups and resumable receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import action_runs as A
import wakeups as W


def migrate(backup, apply=False, card=None):
    board = W.load_board()
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = Path(__file__).read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    saved_source = backup / f'migration-{digest}.py'
    if not saved_source.exists():
        saved_source.write_bytes(source)
    with (backup / 'migration.jsonl').open('a') as log:
        def event(card, status, **fields):
            line = dict(time=W.now().isoformat(), card=card, status=status, apply=apply,
                        source_sha256=digest, **fields)
            print(json.dumps(line, ensure_ascii=False), file=log, flush=True)
            print(json.dumps(line, ensure_ascii=False), flush=True)
        pages, cursor = [], None
        if card:
            pages = [board.api('GET', f'/pages/{card}')]
        else:
            while True:
                query = {'page_size': 100}
                if cursor:
                    query['start_cursor'] = cursor
                result = board.api('POST', f'/databases/{board.DB}/query', query)
                pages.extend(result['results'])
                if not result.get('has_more'):
                    break
                cursor = result['next_cursor']
        for page in pages:
            cid = page['id']
            event(cid, 'start')
            receipt = backup / f'{cid}-done.json'
            if apply and receipt.exists():
                event(cid, 'skip', reason='checkpoint')
                continue
            saved = backup / f'{cid}-before.json'
            blocks, cursor = [], None
            while True:
                url = f'/blocks/{cid}/children?page_size=100' + (f'&start_cursor={cursor}' if cursor else '')
                result = board.api('GET', url)
                blocks.extend(result['results'])
                if not result.get('has_more'):
                    break
                cursor = result['next_cursor']
            legacy = next((b for b in blocks if b.get('type') == 'callout' and
                           (b['callout'].get('icon') or {}).get('emoji') == '📌'), None)
            current = A.property_text(page, 'Summary')
            summary = current or (''.join(r.get('plain_text', '') for r in legacy['callout']['rich_text']) if legacy else '')
            snapshot = dict(page=page, blocks=blocks, summary=summary)
            # Every attempt has its own input snapshot; the first backup is never overwritten.
            if saved.exists():
                saved = backup / f'{cid}-{W.now().strftime("%Y%m%dT%H%M%S%f")}.json'
            W.save(saved, snapshot)
            if not summary:
                event(cid, 'skip', reason='no_existing_summary')
                continue
            if apply:
                latest = board.api('GET', f'/pages/{cid}')
                if A.property_text(latest, 'Summary') != current:
                    event(cid, 'skip', reason='summary_changed_during_migration')
                    continue
                if not current:
                    board.api('PATCH', f'/pages/{cid}', {'properties': {'Summary': {'rich_text': W.text(summary)}}})
                after = board.api('GET', f'/pages/{cid}')
                if A.property_text(after, 'Summary') != summary:
                    raise RuntimeError(f'{cid}: Summary readback differs; legacy block retained')
                if legacy:
                    fresh = board.api('GET', f'/blocks/{legacy["id"]}')
                    if fresh.get('callout') != legacy['callout']:
                        raise RuntimeError(f'{cid}: legacy summary changed; block retained')
                    board.api('PATCH', f'/blocks/{legacy["id"]}', {'archived': True})
                W.save(receipt, dict(card=cid, backup=str(saved), verified_at=W.now().isoformat()))
            event(cid, 'migrated' if apply else 'ready', characters=len(summary), legacy=bool(legacy))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--backup-dir', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--card')
    args = parser.parse_args()
    migrate(args.backup_dir, args.apply, args.card)
