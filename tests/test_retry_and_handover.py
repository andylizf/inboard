import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RetryAndHandoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, INBOARD_STATE=str(self.root / 'state'),
                        INBOARD_LOGS=str(self.root / 'logs'), INBOARD_HOME=str(ROOT),
                        INBOARD_CONFIG=str(ROOT / 'inboard.config.example.yaml'),
                        TWOFA_COOLDOWN_MIN='90', TWOFA_OUTSTANDING_MIN='10')
        self.state = self.root / 'state/2fa'
        self.state.mkdir(parents=True)

    def gate(self, *args):
        return subprocess.run(['bash', str(ROOT / 'bin/twofa-gate'), *args],
                              env=self.env, capture_output=True, text=True)

    def test_explicit_retry_bypasses_only_cooldown(self):
        cooldown = str(int(time.time())) + '\n'
        (self.state / 'cooldown').write_text(cooldown)
        self.assertEqual(self.gate('acquire', 'google').returncode, 1)
        result = self.gate('acquire', 'google', '--operator-retry')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.state / 'cooldown').read_text(), cooldown)
        self.assertIn('google', (self.state / 'outstanding').read_text())

    def test_explicit_retry_cannot_replace_outstanding_verification(self):
        self.assertEqual(self.gate('acquire', 'github').returncode, 0)
        before = (self.state / 'outstanding').read_text()
        result = self.gate('acquire', 'google', '--operator-retry')
        self.assertEqual(result.returncode, 1)
        self.assertIn('another card', result.stdout)
        self.assertEqual((self.state / 'outstanding').read_text(), before)

    def test_retry_timeout_keeps_future_automatic_attempts_blocked(self):
        self.assertEqual(self.gate('acquire', 'google', '--operator-retry').returncode, 0)
        self.assertEqual(self.gate('release', 'google', 'timeout').returncode, 0)
        self.assertEqual(self.gate('acquire', 'google').returncode, 1)

    def test_unknown_retry_option_does_not_acquire(self):
        self.assertEqual(self.gate('acquire', 'google', '--retry').returncode, 2)
        self.assertFalse((self.state / 'outstanding').exists())

    def test_handover_notice_does_not_queue_a_stop_before_current_request(self):
        driver = self.root / 'handover.sh'
        driver.write_text('''
source "$INBOARD_HOME/engines/_common.sh"
cfg() { case "$1" in agent.delivery) echo daemon;; *) echo "${2:-}";; esac; }
board() { echo 11111111-1111-4111-8111-111111111111; }
python3() {
  case "$2" in
    session) echo 11111111-1111-4111-8111-111111111111;;
    retire) echo retired; echo retire >> "$INBOARD_STATE/calls";;
  esac
}
session_too_big() { return 0; }
deliver_to_daemon() { echo "$3" >> "$INBOARD_STATE/calls"; }
CARD=test-card
prep_session
printf '%s' "$SESSION_NOTICE" > "$INBOARD_STATE/notice"
test ! -e "$INBOARD_STATE/calls" || exit 1
test -f "$INBOARD_STATE/.retiring-test-card" || exit 2
prep_session
test ! -e "$INBOARD_STATE/.retiring-test-card" || exit 3
''')
        result = subprocess.run(['bash', str(driver)], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        notice = (self.root / 'state/notice').read_text()
        self.assertIn('Handle this request now', notice)
        self.assertNotIn('Do NOT start new work', notice)
        self.assertEqual((self.root / 'state/calls').read_text(), 'retire\n')


if __name__ == '__main__':
    unittest.main()
