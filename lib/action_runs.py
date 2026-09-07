"""Latest button intent and per-request execution receipts."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time

import ibconfig as C
import wakeups as W

REQUEST = 'ActionRequested'
WHEN = 'ActionRequestedAt'
VERSION = 'ActionVersion'
APPROVED_DRAFT = 'ActionDraft'
HANDLED = 'ActionHandled'
PROGRESS = 'ActionProgress'
DISPLAY = '操作状态'
_LEGACY_FORMULA = ('if(empty(prop("ActionRequestedAt")), "", '
           'if(format(timestamp(prop("ActionRequestedAt"))) + "|" + format(prop("ActionRequested")) '
           '!= prop("ActionHandled"), "⏳ 已收到 · " + format(prop("ActionRequested")), prop("ActionProgress")))')
_STATUS_FORMULA = ('if(empty(prop("ActionVersion")), ' + _LEGACY_FORMULA + ', '
           'if(format(prop("ActionVersion")) + "|" + format(prop("ActionRequested")) != prop("ActionHandled"), '
           '"⏳ 已收到 · " + format(prop("ActionRequested")), prop("ActionProgress")))')
FORMULA = ('lets(state, ' + _STATUS_FORMULA + ', if(empty(trim(prop("Draft"))), '
           'if(empty(state), "暂无可发送草稿", state + " · 暂无可发送草稿"), state))')


def property_text(page, name):
    return ''.join(run.get('plain_text', run.get('text', {}).get('content', ''))
                   for run in page.get('properties', {}).get(name, {}).get('rich_text', []))


def approved_draft(page):
    draft = property_text(page, 'Draft')
    approved = property_text(page, APPROVED_DRAFT)
    if not draft.strip() or not approved.strip():
        raise RuntimeError('暂无已批准的当前草稿，请查看草稿后重新点击发送。')
    if draft != approved:
        raise RuntimeError('草稿已修改，请查看当前版本后重新点击发送。')
    return approved


def intent(page):
    props = page.get('properties', {})
    action = (props.get(REQUEST, {}).get('select') or {}).get('name')
    at = (props.get(WHEN, {}).get('date') or {}).get('start')
    version = props.get(VERSION, {}).get('number')
    if not action or (not at and not version):
        return None
    # Time triggered rounds to a minute. Existing clicks retain that receipt until the next counter-based click.
    sequence = int(version) if version else round(datetime.fromisoformat(at.replace('Z', '+00:00')).timestamp() * 1000)
    key = str(sequence) + '|' + action
    return dict(action=action, key=key, token=hashlib.sha256(key.encode()).hexdigest()[:24])


def root():
    return Path(os.environ.get('INBOARD_STATE', str(Path(C.home()) / 'state'))) / 'action-runs'


def read(card):
    path = root() / (card + '.json')
    return json.loads(path.read_text()) if path.exists() else None


def save(card, record):
    W.save(root() / (card + '.json'), record)


@contextmanager
def lock(card, name='state'):
    root().mkdir(parents=True, exist_ok=True)
    with (root() / f'{card}.{name}.lock').open('a') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def effective_action(page):
    request = intent(page)
    if not request:
        return (page.get('properties', {}).get('Action', {}).get('select') or {}).get('name') or ''
    record = read(page['id'])
    if record and record['token'] == request['token'] and record['phase'] in ('done', 'failed'):
        return ''
    return request['action']


def require_current(card, token, page):
    request = intent(page)
    record = read(card)
    if not request or not record or token != request['token'] or token != record['token']:
        raise RuntimeError('This operation was superseded. Stop; do not overwrite the newer request.')
    if record['phase'] not in ('starting', 'running'):
        raise RuntimeError('This operation is no longer active.')
    return record


def progress(board, card, record, message):
    # Results carry their request key. A later click stays visible even if it races this PATCH.
    board.api('PATCH', f'/pages/{card}', {'properties': {
        HANDLED: {'rich_text': W.text(record['key'])},
        PROGRESS: {'rich_text': W.text(message)}}})


def receipt(board, card, token, phase, message):
    with lock(card):
        page = board.api('GET', f'/pages/{card}')
        record = require_current(card, token, page)
        if phase == 'running':
            message += ' · ' + record['action']
        progress(board, card, record, message)
        record.update(phase=phase, updated_at=time.time())
        save(card, record)


def dispatch(card, prompt):
    import agent_deliver as A
    board = W.load_board()
    # Webhook duplicates wait and re-read the latest intent; they never drop a replacement click.
    with lock(card, 'dispatch'):
        while True:
            page = board.api('GET', f'/pages/{card}')
            request = intent(page)
            if not request:
                return
            if request['action'] == C.get('board.schema.send_action', ''):
                try:
                    approved_draft(page)
                except RuntimeError as exc:
                    # Reject before claiming or interrupting the worker: an unavailable send is not new work.
                    progress(board, card, request, '❌ ' + str(exc))
                    return
            with lock(card):
                previous = read(card)
                if previous and previous['token'] == request['token']:
                    return
                record = dict(request, phase='starting', updated_at=time.time(), sent=False)
                save(card, record)
            print(json.dumps(dict(time=time.time(), event='operation_claimed', card=card,
                                  operation=record['token'], action=record['action'])), flush=True)
            name = 'inboard-card-' + card.replace('-', '')
            try:
                job = A.find_job(name)
                if job and job.get('state') not in ('stopped', 'blocked'):
                    progress(board, card, record, '⏳ 正在切换 · ' + request['action'])
                    stopped = A.interrupt(job)
                    print(json.dumps(dict(time=time.time(), event='operation_interrupted', card=card,
                                          operation=record['token'], result=stopped)), flush=True)
                latest = intent(board.api('GET', f'/pages/{card}'))
                if not latest or latest['token'] != record['token']:
                    continue
                status = C.ACTION_STATUS.get(request['action'])
                if status:
                    board.api('PATCH', f'/pages/{card}', {'properties': {'Status': {'select': {'name': C.status_name(status)}}}})
                    board.remember_status(card, C.status_name(status))
                progress(board, card, record, '⏳ 正在启动 · ' + request['action'])
                token = request['token']
                instructions = (f"\nCURRENT OPERATION {token}: this replaces any older button request. "
                    f"FIRST run `board action-start --card {card} --operation {token}`. "
                    f"Pass `--operation {token}` on every board command that changes this card and on "
                    "`email ... gmail +send-approved`. Stop immediately if a tool says superseded. "
                    f"Finish with `board clear-action --card {card} --operation {token}`. "
                    "If unable to complete the operation, use `board action-fail` with the same card/operation "
                    "and --text describing the problem. Completing an operation does not mean the matter is done.\n")
                result = A.ensure_and_deliver(name, str(Path(C.home()) / 'agent'), prompt.replace('__ACTION__', request['action']) + instructions)
                import daemon_pending
                daemon_pending.record(card, request['action'])
                if result.get('sessionId'):
                    board.api('PATCH', f'/pages/{card}', {'properties': {'Session': {'rich_text': W.text(result['sessionId'])}}})
                print(json.dumps(dict(card=card, operation=token, delivered=True)), flush=True)
            except Exception as exc:
                with lock(card):
                    current = read(card)
                    if current and current['token'] == record['token']:
                        progress(board, card, record, '❌ 操作未完成 · ' + str(exc)[:180])
                        current.update(phase='failed', updated_at=time.time())
                        save(card, current)
                raise
            # A new click may have arrived while the daemon accepted this delivery.
            latest = intent(board.api('GET', f'/pages/{card}'))
            if latest and latest['token'] != record['token']:
                continue
            return


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--card', required=True)
    parser.add_argument('--prompt', required=True)
    args = parser.parse_args()
    dispatch(args.card, args.prompt)
