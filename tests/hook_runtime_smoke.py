"""Exercise real Claude Code hooks with a loopback model and a synthetic card.

Run with the project Python. Each run keeps its fixtures and logs under logs/.
The model endpoint binds loopback only; no model credentials or Notion writes are used.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import card_hooks as H
import ibconfig as C

CARD = '22222222-2222-4222-8222-222222222222'


class FixtureBoard:
    CLOSED_KEYS = {'done', 'expired', 'cancelled', 'unsub'}

    def __init__(self, path):
        self.path = Path(path)

    def api(self, method, path):
        return json.loads(self.path.read_text())

    def _g(self, props, key, kind):
        if kind == 'select':
            return props.get(key, {}).get(kind, {}).get('name', '')
        return ''.join(x.get('plain_text', '') for x in props.get(key, {}).get(kind, []))

    def log(self, args):
        with self.path.with_suffix('.notices').open('a') as log:
            print(args.text, file=log)


def serve_model(case, run):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if 'messages' not in self.path:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{}')
                return
            calls.append(body)
            (run / f'request-{len(calls)}.json').write_text(json.dumps(body, indent=2))
            if case == 'failure':
                self.send_response(401)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'type': 'error', 'error': {
                    'type': 'authentication_error', 'message': 'Synthetic credential rejected'}}).encode())
                return
            num = len(calls)
            content = [{'type': 'text', 'text': 'Fixture response complete.'}]
            stop = 'end_turn'
            if case == 'background' and num == 1:
                content = [{'type': 'tool_use', 'id': 'toolu_background', 'name': 'Bash',
                            'input': {'command': 'sleep 12', 'run_in_background': True,
                                      'description': 'Run the synthetic background task'}}]
                stop = 'tool_use'
            elif case == 'handoff' and num == 2:
                command = shlex.join([sys.executable, str(Path(__file__).resolve()),
                                      'settle', str(run / 'card.json')])
                content = [{'type': 'tool_use', 'id': 'toolu_settle', 'name': 'Bash',
                            'input': {'command': command, 'description': 'Update the synthetic card'}}]
                stop = 'tool_use'
            message = {'id': f'msg_fixture_{num}', 'type': 'message', 'role': 'assistant',
                       'model': body['model'], 'content': content, 'stop_reason': stop,
                       'stop_sequence': None, 'usage': {'input_tokens': 10, 'output_tokens': 10}}
            self.send_response(200)
            if not body.get('stream'):
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(message).encode())
                return
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()

            def event(name, data):
                self.wfile.write(f'event: {name}\ndata: {json.dumps(data)}\n\n'.encode())
                self.wfile.flush()

            event('message_start', {'type': 'message_start', 'message': {**message, 'content': [],
                                                                      'stop_reason': None}})
            for i, block in enumerate(content):
                empty = {**block, 'text': ''} if block['type'] == 'text' else {**block, 'input': {}}
                event('content_block_start', {'type': 'content_block_start', 'index': i, 'content_block': empty})
                delta = ({'type': 'text_delta', 'text': block['text']} if block['type'] == 'text' else
                         {'type': 'input_json_delta', 'partial_json': json.dumps(block['input'])})
                event('content_block_delta', {'type': 'content_block_delta', 'index': i, 'delta': delta})
                event('content_block_stop', {'type': 'content_block_stop', 'index': i})
            event('message_delta', {'type': 'message_delta', 'delta': {'stop_reason': stop,
                  'stop_sequence': None}, 'usage': {'output_tokens': 10}})
            event('message_stop', {'type': 'message_stop'})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, calls


def run_case(case, parent):
    run = parent / case
    run.mkdir()
    runtime = run / 'runtime'
    (runtime / 'agent/.claude').mkdir(parents=True)
    for name in ('engines', 'lib', 'bin', '.venv'):
        (runtime / name).symlink_to(ROOT / name, target_is_directory=True)
    injection = run / 'fixture-python'
    injection.mkdir()
    (injection / 'sitecustomize.py').write_text(
        f'import sys\nsys.path.insert(0, {str(ROOT / "tests")!r})\n'
        f'from hook_runtime_smoke import FixtureBoard\nimport wakeups\n'
        f'wakeups.load_board = lambda: FixtureBoard({str(run / "card.json")!r})\n')
    sid = str(uuid.uuid4())
    env = {k: v for k, v in os.environ.items() if not k.startswith(('ANTHROPIC_', 'CLAUDE_', 'INBOARD_'))
           and k not in ('HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'https_proxy', 'http_proxy', 'all_proxy')}
    env.update(INBOARD_CONFIG=str(ROOT / 'inboard.config.example.yaml'), INBOARD_HOME=str(runtime),
               INBOARD_STATE=str(run / 'state'), PYTHONPATH=str(injection),
               INBOARD_LOGS=str(run), CLAUDE_CONFIG_DIR=str(run / 'claude'),
               ANTHROPIC_API_KEY='synthetic-local-only', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',
               CLAUDE_CODE_DISABLE_AUTO_MEMORY='1', CLAUDE_CODE_MAX_RETRIES='0',
               NO_PROXY='127.0.0.1,localhost')
    os.environ.update({k: v for k, v in env.items() if k.startswith('INBOARD_')})
    H.bind_session('inboard-card-' + CARD.replace('-', ''), sid)
    (run / 'card.json').write_text(json.dumps({'properties': {
        'Status': {'select': {'name': C.status_name('researching')}},
        'Session': {'rich_text': [{'plain_text': sid}]}}}))
    settings = json.loads((ROOT / 'agent/.claude/settings.json').read_text())
    settings_path = runtime / 'agent/.claude/settings.json'
    settings_path.write_text(json.dumps(settings, indent=2))
    server, calls = serve_model(case, run)
    env['ANTHROPIC_BASE_URL'] = f'http://127.0.0.1:{server.server_port}'
    args = ['claude', '-p', '--input-format', 'stream-json', '--session-id', sid,
            '--setting-sources', '', '--settings', str(settings_path),
            '--model', 'claude-sonnet-4-5', '--tools', 'Bash', '--allowedTools', 'Bash',
            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--system-prompt', 'Follow the synthetic model responses.', '--disable-slash-commands',
            '--verbose', '--output-format', 'stream-json', '--include-hook-events',
            '--debug-file', str(run / 'debug.log')]
    (run / 'input.json').write_text(json.dumps({'argv': args, 'session': sid, 'case': case}, indent=2))
    try:
        with (run / 'cli.log').open('w') as log:
            proc = subprocess.Popen(args, cwd=runtime / 'agent', env=env, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.PIPE, text=True)
            try:
                proc.stdin.write(json.dumps({'type': 'user', 'message': {'role': 'user',
                    'content': 'Exercise the synthetic card handoff.'}}) + '\n')
                proc.stdin.flush()
                # Keep the session alive like the daemon; StopFailure is asynchronous.
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline and proc.poll() is None:
                    hooklog = run / 'card-hooks.log'
                    lines = hooklog.read_text() if hooklog.exists() else ''
                    expected = 'failure_reported' if case == 'failure' else (
                        'background_running' if case == 'background' else '"result": {}')
                    if expected in lines:
                        break
                    time.sleep(0.1)
                proc.stdin.close()
                proc.wait(timeout=15)
                result = proc
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
    finally:
        server.shutdown()
    hooklog = run / 'card-hooks.log'
    events = [json.loads(line) for line in hooklog.read_text().splitlines()] if hooklog.exists() else []
    if case == 'handoff':
        assert any(e.get('result', {}).get('decision') == 'block' for e in events), events
        card = json.loads((run / 'card.json').read_text())
        assert card['properties']['Status']['select']['name'] == C.status_name('awaiting'), card
        assert result.returncode == 0, result.returncode
    elif case == 'background':
        assert any(e['event'] == 'background_running' for e in events), events
    else:
        assert any(e['event'] == 'failure_reported' and e.get('error') == 'authentication_failed'
                   for e in events), events
    print(json.dumps({'case': case, 'passed': True, 'requests': len(calls), 'cli_exit': result.returncode,
                      'logs': str(run)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['run', 'settle'])
    parser.add_argument('path', nargs='?')
    args = parser.parse_args()
    if args.mode == 'settle':
        path = Path(args.path)
        data = json.loads(path.read_text())
        data['properties']['Status']['select']['name'] = C.status_name('awaiting')
        path.write_text(json.dumps(data))
    else:
        os.environ['INBOARD_CONFIG'] = str(ROOT / 'inboard.config.example.yaml')
        parent = ROOT / 'logs' / f'hook-smoke-{uuid.uuid4().hex[:8]}'
        parent.mkdir(parents=True)
        print(f'Logs: {parent}', flush=True)
        for case in ('handoff', 'background', 'failure'):
            run_case(case, parent)
