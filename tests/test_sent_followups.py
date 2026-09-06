"""Synthetic mail and Notion fixtures; no network or production state is used."""
import argparse
import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.environ["INBOARD_CONFIG"] = str(ROOT / "inboard.config.example.yaml")
loader = importlib.machinery.SourceFileLoader("board_test", str(ROOT / "bin/board"))
spec = importlib.util.spec_from_loader(loader.name, loader)
board = importlib.util.module_from_spec(spec)
loader.exec_module(board)


def page(card, days, status=None, needs="", action=None):
    return {"id": card, "last_edited_time": (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(),
            "properties": {"Status": {"select": {"name": status or board.S["awaiting"]}},
                           "NeedsYou": {"rich_text": [{"plain_text": needs}]},
                           "Action": {"select": {"name": action} if action else None}}}


class FollowupTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "logs").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "logs")
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        env = patch.dict(os.environ, {"INBOARD_STATE": str(self.state)})
        env.start()
        self.addCleanup(env.stop)
        self.pages = {}
        self.writes = []
        self.fail = set()
        self.before_get = lambda p: p
        mocked = patch.object(board, "api", side_effect=self.api)
        mocked.start()
        self.addCleanup(mocked.stop)

    def api(self, method, path, body=None):
        if method == "POST":
            first_pass = "and" not in body["filter"]
            rows = [copy.deepcopy(p) for p in self.pages.values()
                    if (p["properties"]["Status"]["select"]["name"] == board.S["awaiting"] if first_pass
                        else p["properties"]["Status"]["select"]["name"] == board.S["needs_you"]
                        and p["properties"]["NeedsYou"]["rich_text"][0]["plain_text"].startswith(board.NUDGE_PREFIX))]
            return {"results": rows, "has_more": False}
        card = path.rsplit("/", 1)[1]
        if method == "GET":
            return self.before_get(copy.deepcopy(self.pages[card]))
        if card in self.fail:
            raise RuntimeError("synthetic API failure")
        self.writes.append((card, body))
        self.pages[card]["properties"].update(copy.deepcopy(body["properties"]))
        for item in self.pages[card]["properties"]["NeedsYou"]["rich_text"]:
            item["plain_text"] = item["text"]["content"]
        self.pages[card]["last_edited_time"] = datetime.now(timezone.utc).isoformat()
        return {}

    def sweep(self, apply=True, plan=None):
        output, logs = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(logs):
            board.stale_awaiting(argparse.Namespace(days=3, nudge=apply, exclude_plan=plan))
        return output.getvalue(), logs.getvalue()

    def test_overdue_nudged_recent_untouched_and_second_run_quiet(self):
        self.pages = {"old": page("old", 4), "recent": page("recent", 2)}
        self.sweep()
        self.assertEqual([x[0] for x in self.writes], ["old"])
        self.assertEqual(self.pages["old"]["properties"]["Status"]["select"]["name"], board.S["needs_you"])
        self.sweep()
        self.assertEqual(len(self.writes), 1)

    def test_repeated_reminder_stays_open_and_increments_count(self):
        self.pages = {"repeat": page("repeat", 4, board.S["needs_you"], board.NUDGE_PREFIX + "第 2 次提醒")}
        self.sweep()
        text = self.writes[0][1]["properties"]["NeedsYou"]["rich_text"][0]["text"]["content"]
        self.assertIn("第 3 次提醒", text)
        self.assertNotIn("Subscription", self.writes[0][1]["properties"])

    def test_mail_busy_daemon_and_action_cards_are_skipped(self):
        self.pages = {k: page(k, 5) for k in ("mail", "busy", "daemon", "action")}
        self.pages["action"]["properties"]["Action"] = {"select": {"name": "continue"}}
        (self.state / ".lock-busy").mkdir()
        (self.state / "daemon-pending.json").write_text(json.dumps([{"card": "daemon"}]))
        plan = self.state / "plan.json"
        plan.write_text(json.dumps({"groups": [{"card": "mail", "route": "card"}]}))
        _, logs = self.sweep(plan=str(plan))
        self.assertEqual(self.writes, [])
        for reason in ("mail_in_current_plan", "card_busy", "daemon_delivery_pending", "operator_action_pending"):
            self.assertIn(reason, logs)

    def test_changed_card_is_not_overwritten(self):
        self.pages = {"changed": page("changed", 5)}
        self.before_get = lambda p: {**p, "last_edited_time": datetime.now(timezone.utc).isoformat()}
        _, logs = self.sweep()
        self.assertEqual(self.writes, [])
        self.assertIn("card_changed", logs)

    def test_abandoned_lock_is_reclaimed(self):
        self.pages = {"old": page("old", 4)}
        lock = self.state / ".lock-old"
        lock.mkdir()
        os.utime(lock, (0, 0))
        _, logs = self.sweep()
        self.assertEqual([x[0] for x in self.writes], ["old"])
        self.assertIn("stale_card_lock", logs)
        self.assertFalse(lock.exists())

    def test_failure_is_visible_other_cards_complete_and_failed_card_retries(self):
        self.pages = {k: page(k, 5) for k in ("fail", "ok")}
        self.fail = {"fail"}
        with self.assertRaisesRegex(RuntimeError, "1 follow-up"):
            self.sweep()
        self.assertEqual([x[0] for x in self.writes], ["ok"])
        self.assertFalse((self.state / ".lock-fail").exists())
        self.fail.clear()
        self.sweep()
        self.assertEqual([x[0] for x in self.writes], ["ok", "fail"])

    def test_read_only_query_does_not_nudge(self):
        self.pages = {"old": page("old", 4)}
        output, _ = self.sweep(apply=False)
        self.assertEqual(json.loads(output)[0]["card"], "old")
        self.assertEqual(self.writes, [])

    def test_paginated_stale_cards_are_not_dropped(self):
        responses = [{"results": [page("first", 4)], "has_more": True, "next_cursor": "next"},
                     {"results": [page("second", 4)], "has_more": False},
                     {"results": [], "has_more": False}]
        with patch.object(board, "api", side_effect=responses) as api:
            output, _ = self.sweep(apply=False)
        self.assertEqual([r["card"] for r in json.loads(output)], ["first", "second"])
        self.assertEqual(api.call_args_list[1].args[2]["start_cursor"], "next")

    def test_sent_and_received_directions_reach_card_prompt(self):
        plan = self.state / "plan.json"
        plan.write_text(json.dumps({"groups": [{"messages": [
            {"id": "out", "account": "work", "kind": "sent"},
            {"id": "in", "account": "work", "kind": "inbox"}]}]}))
        result = subprocess.run([sys.executable, str(ROOT / "engines/dispatch_plan.py"),
                                 "field", str(plan), "0", "pairs"], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "out(work,sent) in(work,inbox)")


if __name__ == "__main__":
    unittest.main()
