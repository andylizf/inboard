"""Synthetic card lifecycle tests. No live Notion or agent calls."""
import argparse
import copy
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.environ['INBOARD_CONFIG'] = str(ROOT / 'inboard.config.example.yaml')
sys.path.insert(0, str(ROOT / 'lib'))
import wakeups as W

loader = importlib.machinery.SourceFileLoader('test_wake_board', str(ROOT / 'bin/board'))
spec = importlib.util.spec_from_loader(loader.name, loader)
B = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = B
loader.exec_module(B)


class WakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, INBOARD_STATE=self.temp.name)
        env.start()
        self.addCleanup(env.stop)
        self.time = datetime.now(timezone.utc)
        self.past = (self.time - timedelta(hours=1)).isoformat()
        self.future = (self.time + timedelta(days=1)).isoformat()
        self.pages = {}
        self.events = []
        self.sent = []
        self.fail = False
        mock = patch.object(B, 'api', side_effect=self.api)
        mock.start()
        self.addCleanup(mock.stop)

    def page(self, card='card', status='awaiting', rules=None):
        p = {'id': card, 'properties': {'Status': {'select': {'name': B.S[status]}},
             'Action': {'select': None}, 'Subscription': {'rich_text': W.text('Await the response')},
             **W.properties(rules or [])}}
        self.pages[card] = p
        return p

    def api(self, method, path, body=None):
        if method == 'POST':
            return {'results': [copy.deepcopy(p) for p in self.pages.values()
                                if not p['properties']['NextCheck']['date'] or
                                any(W.instant(r['at']) <= self.time for r in W.read(p))], 'has_more': False}
        card = path.rsplit('/', 1)[1]
        if method == 'GET':
            return copy.deepcopy(self.pages[card])
        self.pages[card]['properties'].update(copy.deepcopy(body['properties']))
        return {}

    def send(self, card, prompt, board):
        if self.fail:
            raise RuntimeError('synthetic daemon outage')
        self.sent.append((card, prompt))

    def emit(self, card, status, **fields):
        self.events.append((card, status, fields))

    def sweep(self, busy=lambda card: False):
        W.sweep(B, self.emit, send=self.send, busy=busy, clock=lambda: self.time)

    def test_multiple_due_triggers_deliver_once_ack_keeps_future_and_new_schedule(self):
        rules = W.add(W.add([], self.past, 'Check the portal'), self.past, 'Check for mail')
        rules = W.add(rules, self.future, 'Deadline review')
        self.page(rules=rules)
        self.sweep()
        self.sweep()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(W.read(self.pages['card'])), 3)
        record = json.loads((W.root() / 'card.json').read_text())
        self.assertEqual(len(record['rules']), 2)
        B.schedule(argparse.Namespace(card='card', at=self.future, reason='Check again after recovery'))
        W.acknowledge(B, 'card', record['token'])
        remaining = W.read(self.pages['card'])
        self.assertEqual({r['reason'] for r in remaining}, {'Deadline review', 'Check again after recovery'})
        self.assertEqual(self.pages['card']['properties']['NextCheck']['date']['start'], self.future)

    def test_failed_delivery_retries_without_losing_rules(self):
        self.page(rules=W.add([], self.past, 'Check recovery'))
        self.fail = True
        with self.assertRaisesRegex(RuntimeError, '1 card wakeups failed'):
            self.sweep()
        self.assertEqual(len(W.read(self.pages['card'])), 1)
        self.fail = False
        self.sweep()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(list(W.root().glob('card-*.json'))), 2)

    def test_dead_worker_retries_but_live_worker_does_not(self):
        self.page(rules=W.add([], self.past, 'Review reply'))
        self.sweep()
        self.time += timedelta(hours=1)
        self.sweep(busy=lambda card: True)
        self.assertEqual(len(self.sent), 1)
        self.sweep()
        self.assertEqual(len(self.sent), 2)

    def test_operator_action_and_closed_card_never_wake(self):
        p = self.page('action', rules=W.add([], self.past, 'Check'))
        p['properties']['Action'] = {'select': {'name': 'Continue'}}
        self.page('closed', status='cancelled', rules=W.add([], self.past, 'Check'))
        self.sweep()
        self.assertFalse(self.sent)

    def test_early_mail_cancels_timer(self):
        self.page(rules=W.add([], self.past, 'Chase if unanswered'))
        B.unschedule(argparse.Namespace(card='card', all=True, id=None))
        self.sweep()
        self.assertFalse(self.sent)
        self.assertEqual(len(W.read(self.pages['card'])), 1)
        self.assertGreater(W.instant(W.read(self.pages['card'])[0]['at']), self.time)

    def test_missing_review_is_repaired_without_dispatch_or_status_change(self):
        p = self.page(status='needs_you')
        self.sweep()
        self.sweep()
        self.assertFalse(self.sent)
        self.assertEqual(p['properties']['Status']['select']['name'], B.S['needs_you'])
        self.assertEqual(len(W.read(p)), 1)
        self.assertEqual(W.instant(W.read(p)[0]['at']), self.time + timedelta(days=3))
        self.assertEqual(len(list(W.root().glob('*-schedule.json'))), 1)

    def test_ack_last_check_retains_review_for_needs_you_but_not_closed(self):
        for status in ('needs_you', 'done'):
            self.page(rules=W.add([], self.past, 'Inspect external state'))
            self.sweep()
            record = json.loads((W.root() / 'card.json').read_text())
            self.pages['card']['properties']['Status'] = {'select': {'name': B.S[status]}}
            W.acknowledge(B, 'card', record['token'])
            self.assertEqual(bool(W.read(self.pages['card'])), status == 'needs_you')

    def test_pending_button_blocks_review_and_repair(self):
        p = self.page(status='needs_you')
        p['properties'].update(ActionRequested={'select': {'name': 'Continue'}}, ActionVersion={'number': 1})
        self.sweep()
        self.assertFalse(W.read(p))
        self.assertFalse(self.sent)

    def test_near_deadline_review_is_earlier_than_default(self):
        p = self.page(status='needs_you')
        p['properties']['Due'] = {'date': {'start': (self.time + timedelta(hours=12)).isoformat()}}
        self.sweep()
        self.assertEqual(W.instant(W.read(p)[0]['at']), self.time + timedelta(hours=1))

    def test_repair_only_does_not_dispatch_due_checks(self):
        self.page(rules=W.add([], self.past, 'Inspect'))
        W.sweep(B, self.emit, send=self.send, busy=lambda _: False, repair_only=True)
        self.assertFalse(self.sent)

    def test_terminal_writes_clear_mail_and_time_subscriptions(self):
        for status in B.CLOSED_KEYS:
            self.page(rules=W.add([], self.past, 'Check'))
            B.edit(argparse.Namespace(card='card', status=status, needs=None, subject=None, draft=None,
                                      sender=None, due=None))
            self.assertEqual(W.read(self.pages['card']), [])
            self.assertEqual(self.pages['card']['properties']['Subscription']['rich_text'], [])
        self.page(rules=W.add([], self.past, 'Check'))
        B.done(argparse.Namespace(card='card'))
        self.assertEqual(W.read(self.pages['card']), [])

    def test_waiting_clears_operator_request_but_keeps_triggers(self):
        p = self.page(status='needs_you', rules=W.add([], self.future, 'Check'))
        p['properties']['NeedsYou'] = {'rich_text': W.text('Send materials')}
        B.awaiting(argparse.Namespace(card='card', desc='Wait for recovery'))
        self.assertEqual(len(W.read(p)), 1)
        self.assertEqual(p['properties']['NeedsYou']['rich_text'], [])

    def test_no_silent_timestamp_guess_or_text_truncation(self):
        with self.assertRaisesRegex(ValueError, 'explicit UTC offset'):
            W.add([], '2026-10-01T09:00:00', 'Check')
        reason = 'A' * 2400
        rules = W.add([], self.future, reason)
        self.assertEqual(W.read({'properties': W.properties(rules)})[0]['reason'], reason)
        self.assertEqual(len(W.add(rules, self.future, reason)), 1)

    def test_wrong_receipt_cannot_remove_schedule(self):
        self.page(rules=W.add([], self.past, 'Check'))
        self.sweep()
        with self.assertRaisesRegex(ValueError, 'does not match'):
            W.acknowledge(B, 'card', 'wrong')
        self.assertEqual(len(W.read(self.pages['card'])), 1)

    def test_card_edited_after_query_uses_current_schedule(self):
        p = self.page(rules=W.add([], self.past, 'Old check'))
        old = copy.deepcopy(p)
        p['properties'].update(W.properties(W.add([], self.future, 'New check')))
        with patch.object(W, 'candidates', return_value=[old]):
            self.sweep()
        self.assertFalse(self.sent)

    def test_schedule_cannot_reopen_cancelled_matter(self):
        self.page(status='cancelled')
        with self.assertRaises(SystemExit):
            B.schedule(argparse.Namespace(card='card', at=self.future, reason='Check'))


if __name__ == '__main__':
    unittest.main()
