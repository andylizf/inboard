"""Synthetic delivery-direction regression; no live mail is sent."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SentDirectionTests(unittest.TestCase):
    def test_sent_and_received_directions_reach_card_prompt(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        plan = Path(temp.name) / "plan.json"
        plan.write_text(json.dumps({"groups": [{"messages": [
            {"id": "out", "account": "work", "kind": "sent"},
            {"id": "in", "account": "work", "kind": "inbox"}]}]}))
        result = subprocess.run([sys.executable, str(ROOT / "engines/dispatch_plan.py"),
                                 "field", str(plan), "0", "pairs"], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "out(work,sent) in(work,inbox)")
