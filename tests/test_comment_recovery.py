import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
FAILURE = '⚠️ Handling this comment failed (rc=1, log comment-test). Not completed — comment again to retry.'


class CommentRecoveryTests(unittest.TestCase):
    def comments(self, answered=False):
        rows = [dict(id='human-comment', author='human', text='Please proceed'),
                dict(id='failure', author='bot', text=FAILURE)]
        if answered:
            rows.append(dict(id='answer', author='bot', text='Completed the requested work.'))
        return rows

    def test_handler_recovers_failure_but_skips_real_answer(self):
        for answered, failure in ((False, False), (True, False), (False, True)):
            with self.subTest(answered=answered, failure=failure), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                for name in ('agent', 'state', 'logs', 'engines'):
                    (root / name).mkdir()
                rows = self.comments(answered) if not failure else self.comments()[:1]
                (root / 'comments.json').write_text(json.dumps(rows))
                shutil.copy(ROOT / 'engines/comment-handler.sh', root / 'engines/comment-handler.sh')
                (root / 'engines/_common.sh').write_text('''
cfg() { case "$1" in board.bot_user_id) echo bot;; agent.delivery) echo daemon;; *) echo "${2:-}";; esac; }
board() { case "$1" in comments) cat "$INBOARD_HOME/comments.json";; *) echo "$*" >> "$INBOARD_HOME/board-calls";; esac; }
lock_or_exit() { :; }
sleep() { :; }
prep_session() { SID=""; }
card_agent_name() { echo "inboard-card-$1"; }
deliver_to_daemon() { printf '%s' "$3" > "$INBOARD_HOME/delivered"; DAEMON_SID=""; return "${TEST_DELIVERY_RC:-0}"; }
valid_uuid() { return 1; }
SESSION_NOTICE=""; GOAL_TRAILER=""; MORTAL_TRAILER=""
''')
                env = dict(os.environ, INBOARD_HOME=td, INBOARD_STATE=str(root / 'state'),
                           INBOARD_LOGS=str(root / 'logs'), NOTION_TOKEN_V2='',
                           TEST_DELIVERY_RC='1' if failure else '0')
                result = subprocess.run(['bash', str(root / 'engines/comment-handler.sh'),
                                         json.dumps({'entity': {'type': 'page', 'id': 'card'}})],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((root / 'delivered').exists(), not answered)
                if not answered:
                    self.assertIn('target comment id is human-comment', (root / 'delivered').read_text())
                    if failure:
                        self.assertIn('评论交付失败，系统会自动重试。', (root / 'board-calls').read_text())
                        self.assertFalse((root / 'state/.picked-card').exists())
                    else:
                        self.assertTrue((root / 'state/.picked-card').read_text().startswith('human-comment '))

    def test_catchup_selects_original_comment_after_failure(self):
        for answered in (False, True):
            with self.subTest(answered=answered):
                cfg = types.ModuleType('ibconfig')
                cfg.home = lambda: str(ROOT)
                cfg.get = lambda key, default=None: {'board.bot_user_id': 'bot', 'board.database_id': 'board'}.get(key, default)
                comments = [dict(id=c['id'], created_by={'id': c['author']},
                                 created_time=str(i), rich_text=[{'plain_text': c['text']}])
                            for i, c in enumerate(self.comments(answered))]
                def response(request, **kwargs):
                    data = {'results': comments} if '/comments?' in request.full_url else {'results': [{'id': 'card'}]}
                    cm = MagicMock()
                    cm.__enter__.return_value.read.return_value = json.dumps(data).encode()
                    return cm
                with patch.dict(sys.modules, ibconfig=cfg), patch.dict(os.environ, NOTION_TOKEN='test'), \
                     patch('urllib.request.urlopen', side_effect=response), patch('subprocess.Popen') as popen:
                    runpy.run_path(str(ROOT / 'engines/comment-catchup.py'))
                self.assertEqual(popen.call_count, 0 if answered else 1)
                if not answered:
                    event = json.loads(popen.call_args.args[0][-1])
                    self.assertEqual(event['entity']['id'], 'human-comment')


if __name__ == '__main__':
    unittest.main()
