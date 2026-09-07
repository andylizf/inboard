"""Add button request/receipt properties after saving the current schema."""
import argparse
import json
from pathlib import Path
import sys
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import action_runs as A
import wakeups as W


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    board = W.load_board()
    schema = board.api('GET', f'/databases/{board.DB}')
    backup = Path(__file__).resolve().parents[1] / 'logs/action-ui' / datetime.now().strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True)
    (backup / 'schema-before.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2))
    properties = {
        A.REQUEST: {'select': {'options': [{key: opt[key] for key in ('name', 'color')} for opt in schema['properties']['Action']['select']['options']]}},
        A.WHEN: {'date': {}}, A.HANDLED: {'rich_text': {}}, A.PROGRESS: {'rich_text': {}},
        A.DISPLAY: {'formula': {'expression': A.FORMULA}}}
    missing = {name: value for name, value in properties.items() if name not in schema['properties']}
    if args.apply and missing:
        board.api('PATCH', f'/databases/{board.DB}', {'properties': missing})
    after = board.api('GET', f'/databases/{board.DB}') if args.apply else schema
    (backup / 'schema-after.json').write_text(json.dumps(after, ensure_ascii=False, indent=2))
    if args.apply:
        assert all(name in after['properties'] for name in properties)
    print(json.dumps({'backup': str(backup), 'applied': args.apply, 'added': list(missing)}))


if __name__ == '__main__':
    main()
