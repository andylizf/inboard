"""Stage the content of an outward action, and its preview, on the card.

What runs the action is the card's own agent, woken by the operator's click. This file
only prepares and publishes what he is approving; it executes nothing.
"""
import hashlib
from pathlib import Path
import shlex
import sys
import time
import uuid

import action_runs as AR
import wakeups as W

ACTION = '❗ Execute script'
SCRIPT = 'Script'
APPROVED = 'ActionScript'


def directory(card, plan):
    # Both values become path components supplied by the board or command line.
    return AR.root().parent / 'shell-plans' / str(uuid.UUID(card)) / str(uuid.UUID(plan))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stage(board, card, file, cwd, description, inputs, *, source=None):
    card = str(uuid.UUID(card))
    plan = str(uuid.uuid4())
    if source is None:
        source = Path(file).resolve().read_text()
    if not description.strip():
        raise ValueError('An operation preview is required')
    cwd = str(Path(cwd).resolve(strict=True))
    if not Path(cwd).is_dir():
        raise ValueError('Working directory is not a directory')
    bound = {str(Path(p).resolve(strict=True)): digest(p) for p in inputs}
    preview = (f'Script version: {plan}\n{description}\nWorking directory: {cwd}\n'
               + ''.join(f'Input: {p} (sha256 {h})\n' for p, h in bound.items())
               + '\n' + source)
    if len(preview) > 18000:
        raise ValueError('Script preview exceeds 18000 characters; use a smaller self-contained script')
    folder = directory(card, plan)
    folder.mkdir(parents=True)
    script = folder / 'script.sh'
    script.write_text(source)
    data = dict(card=card, plan=plan, cwd=cwd, preview=preview, draft=description, inputs=bound,
                script_sha256=digest(script), staged_at=time.time())
    W.save(folder / 'plan.json', data)
    board.api('PATCH', f'/pages/{card}', {'properties': {
        SCRIPT: {'rich_text': W.text(preview)}, 'Draft': {'rich_text': W.text(description)}}})
    current = board.api('GET', f'/pages/{card}')
    if AR.property_text(current, SCRIPT) != preview or AR.property_text(current, 'Draft') != description:
        raise RuntimeError('Script preview read-back failed')
    return data


def stage_email(board, card, account, draft_id):
    description = AR.property_text(board.api('GET', f'/pages/{card}'), 'Draft')
    command = shlex.join([sys.executable, str(Path(AR.C.home()) / 'bin/email'), account,
                          'gmail', '+send-approved', '--card', card, '--draft-id', draft_id])
    source = 'set -euo pipefail\nexec ' + command + ' --operation "$INBOARD_OPERATION"\n'
    return stage(board, card, None, str(Path(AR.C.home()) / 'agent'), description, [], source=source)
