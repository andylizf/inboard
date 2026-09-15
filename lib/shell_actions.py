"""Stage a reviewed script and execute it once through Claude Code's native ! input."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
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


def stage(board, card, file, cwd, description, inputs):
    card = str(uuid.UUID(card))
    plan = str(uuid.uuid4())
    source = Path(file).resolve().read_text()
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
    data = dict(card=card, plan=plan, cwd=cwd, preview=preview, inputs=bound,
                script_sha256=digest(script), staged_at=time.time())
    W.save(folder / 'plan.json', data)
    board.api('PATCH', f'/pages/{card}', {'properties': {SCRIPT: {'rich_text': W.text(preview)}}})
    current = board.api('GET', f'/pages/{card}')
    if AR.property_text(current, SCRIPT) != preview:
        raise RuntimeError('Script preview read-back failed')
    return data


def approved(page):
    preview = AR.property_text(page, SCRIPT)
    if not preview or preview != AR.property_text(page, APPROVED):
        raise RuntimeError('脚本尚未确认或已修改，请查看当前脚本后点击 ❗执行脚本。')
    try:
        plan = preview.splitlines()[0].removeprefix('Script version: ')
        folder = directory(page['id'], plan)
        data = json.loads((folder / 'plan.json').read_text())
    except (ValueError, OSError) as exc:
        raise RuntimeError('找不到已准备的脚本版本，请重新准备。') from exc
    if data['preview'] != preview:
        raise RuntimeError('脚本预览与已保存版本不符，请重新准备。')
    validate(folder, data)
    if (folder / 'dispatch.json').exists():
        raise RuntimeError('此版本已经触发过执行；请先核实结果，修复后准备新版本。')
    return folder, data


def validate(folder, data):
    if digest(folder / 'script.sh') != data['script_sha256']:
        raise RuntimeError('已保存的脚本发生变化，请重新准备。')
    for path, expected in data['inputs'].items():
        if digest(path) != expected:
            raise RuntimeError(f'输入文件已变化，请重新准备：{path}')


def dispatch(board, page, record, job):
    import agent_deliver as A
    folder, data = approved(page)
    if not job or job.get('state') in ('stopped', 'blocked'):
        raise RuntimeError('原 Claude 会话不可用；请先恢复会话，再点击执行。')
    session = AR.property_text(page, 'Session')
    if not session or session != job.get('sessionId'):
        raise RuntimeError('卡片与 Claude 会话不一致；请先恢复原会话。')
    # Claim before terminal input: a lost acknowledgement must never cause a second send.
    with (folder / 'dispatch.json').open('x') as fh:
        json.dump(dict(record=record, session=session, dispatched_at=time.time()), fh)
    command = shlex.join([sys.executable, str(Path(__file__).resolve()), 'run',
                          '--card', data['card'], '--plan', data['plan']])
    AR.progress(board, page['id'], record, '⏳ 正在交给 Claude Code ! 执行')
    A.shell_input(job, command, folder / 'terminal.log', folder / 'started.json')


def run(card, plan):
    folder = directory(card, plan)
    data = json.loads((folder / 'plan.json').read_text())
    dispatch = json.loads((folder / 'dispatch.json').read_text())
    record = dispatch['record']
    # Exclusive creation prevents re-running this version even from a repeated terminal input.
    with (folder / 'started.json').open('x') as fh:
        json.dump(dict(started_at=time.time(), pid=os.getpid()), fh)
    result = dict(card=card, plan=plan, started_at=time.time(), inputs=data,
                  session=dispatch['session'], operation=record['token'])
    board = W.load_board()
    code = 1
    with (folder / 'output.log').open('x', buffering=1) as log:
        def emit(message):
            line = f'[{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}] {message}'
            print(line, flush=True)
            log.write(line + '\n')
        emit(f'Starting approved script version {plan}')
        try:
            page = board.api('GET', f'/pages/{card}')
            AR.require_current(card, record['token'], page)
            if any(AR.property_text(page, prop) != data['preview'] for prop in (SCRIPT, APPROVED)):
                raise RuntimeError('Script preview changed before execution; prepare and approve the current version')
            validate(folder, data)
            env = dict(os.environ, INBOARD_OPERATION=record['token'], INBOARD_CARD=card)
            with subprocess.Popen(['bash', str(folder / 'script.sh')], cwd=data['cwd'],
                                  env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, errors='replace') as process:
                for line in process.stdout:
                    emit(line.rstrip('\n'))
                code = process.wait()
            result['exit_code'] = code
        except Exception as exc:
            result['error'] = str(exc)
            emit(f'Execution error: {exc}')
        result['finished_at'] = time.time()
        W.save(folder / 'result.json', result)
        emit(f'Finished: exit={code}. Receipt: {folder / "result.json"}')
        emit('Verify the external result before marking the matter done. If execution failed, '
             'diagnose and prepare a corrected script version for another user click. '
             'Do not automatically repeat the external action.')
        try:
            AR.receipt(board, card, record['token'], 'done' if code == 0 else 'failed',
                       '✅ 脚本执行结束 · 请核实结果' if code == 0 else f'❌ 脚本退出 {code} · 结果已回原会话')
        except Exception as exc:
            emit(f'Card receipt update failed (local result is saved): {exc}')
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['run'])
    parser.add_argument('--card', required=True)
    parser.add_argument('--plan', required=True)
    args = parser.parse_args()
    sys.exit(run(args.card, args.plan))
