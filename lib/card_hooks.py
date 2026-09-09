"""Check card handoff at turn end and record failures independently of the model."""
import argparse
import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import sys
import uuid

import ibconfig as C
import wakeups as W


def root():
    return Path(os.environ.get('INBOARD_STATE', str(Path(C.home()) / 'state'))) / 'card-hooks'


def session_path(sid):
    return root() / f'{uuid.UUID(sid)}.json'


def bind_session(name, sid):
    if not name.startswith('inboard-card-') or not sid:
        return
    card = str(uuid.UUID(name.removeprefix('inboard-card-')))
    path = session_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(path.read_text()) if path.exists() else {}
        state['card'] = card
        W.save(path, state)
    W.save(root() / f'card-{card}.json', {'session': sid})


def emit(sid, event, **fields):
    logs = Path(os.environ.get('INBOARD_LOGS', str(Path(C.home()) / 'logs')))
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / 'card-hooks.log').open('a') as log:
        print(json.dumps({'ts': W.now().isoformat(), 'session': sid, 'event': event,
                          **fields}, ensure_ascii=False), file=log, flush=True)


def report_failure(board, state, sid, kind, detail):
    """Keep the failure separate from the matter's business status and summary."""
    key = f'{kind}:{detail}'
    if state.get('reported_failure') == key:
        return
    if C.status_name('researching') == '🔍 研究中':
        text = f'⚠️ 本轮执行受阻（{kind}）：{detail}。这不表示事项已完成。'
    else:
        text = f'⚠️ This run stopped ({kind}): {detail}. The matter is not marked complete.'
    with contextlib.redirect_stdout(io.StringIO()):
        board.log(argparse.Namespace(card=state['card'], text=text))
    state['reported_failure'] = key
    emit(sid, 'failure_reported', card=state['card'], error=kind, detail=detail)


def decide(board, state, payload):
    sid = payload['session_id']
    event = payload['hook_event_name']
    if event not in ('Stop', 'StopFailure'):
        return {}
    page = board.api('GET', f'/pages/{state["card"]}')
    props = page['properties']
    current = board._g(props, 'Session', 'rich_text')
    owner = root() / f'card-{state["card"]}.json'
    if owner.exists():
        # The caller writes Notion's Session after delivery; a fast Stop can beat it.
        current = json.loads(owner.read_text())['session']
    if current and current != sid:
        emit(sid, 'skip', card=state['card'], reason='session_replaced')
        return {}
    if page.get('archived') or board._g(props, 'Status', 'select') in {
            C.status_name(k) for k in board.CLOSED_KEYS}:
        return {}
    if event == 'StopFailure':
        kind = str(payload.get('error') or 'unknown')
        detail = str(payload.get('last_assistant_message') or payload.get('error_details') or kind)
        report_failure(board, state, sid, kind, detail)
        return {}
    if board._g(props, 'Status', 'select') != C.status_name('researching'):
        state['blocks'] = 0
        return {}
    # Verified on Claude Code 2.1.266: this is the current session's runtime snapshot.
    # session_crons is deliberately excluded; a future check is not running work.
    active = [task for task in payload.get('background_tasks', []) if task.get('status') == 'running']
    if active:
        emit(sid, 'background_running', card=state['card'], tasks=active)
        state['blocks'] = 0
        return {}
    if not payload.get('stop_hook_active'):
        state['blocks'] = 0
    if state.get('blocks', 0) >= 2:
        report_failure(board, state, sid, 'handoff_incomplete',
                       'The agent stopped without updating its Researching status after two reminders.')
        return {}
    state['blocks'] = state.get('blocks', 0) + 1
    return {'decision': 'block', 'reason': (
        f'Card {state["card"]} is still Researching, but no running background task was verified. '
        'If work can continue now, continue it. A scheduled review or idle daemon does not count '
        'as running work. Otherwise use board edit to set --status awaiting, needs_you, or a verified terminal '
        'status according to the facts, and record the next step before stopping. '
        'Acknowledge any wakeup or action requested in this turn after recording its outcome. '
        'Do not mark unfinished work complete just to satisfy this check. '
        'Report an inability to update the card explicitly.')}


def handle(payload, board=None):
    sid = payload['session_id']
    path = session_path(sid)
    if not path.exists():
        return {}  # Shared dispatcher sessions have no single card to hand off.
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(path.read_text())
        emit(sid, 'start', card=state['card'], input=payload)
        try:
            if board is None and payload['hook_event_name'] in ('Stop', 'StopFailure'):
                board = W.load_board()
            result = decide(board, state, payload)
        except Exception as exc:
            # A failed Notion request cannot be fixed by repeatedly blocking the same Stop.
            emit(sid, 'fail', card=state['card'], error=str(exc))
            raise
        finally:
            W.save(path, state)
        emit(sid, 'done', card=state['card'], result=result)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind-live', action='store_true', help='Bind existing daemon card sessions after deployment')
    args = parser.parse_args()
    if args.bind_live:
        import agent_deliver
        jobs = sorted(agent_deliver.list_jobs(), key=lambda job: job.get('createdAt', 0))
        for job in jobs:
            bind_session(job.get('name', ''), job.get('sessionId', ''))
        print(json.dumps({'bound': sum(job.get('name', '').startswith('inboard-card-') for job in jobs)}))
    else:
        print(json.dumps(handle(json.load(sys.stdin)), ensure_ascii=False))
