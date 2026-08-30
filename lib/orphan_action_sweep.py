#!/usr/bin/env python3
"""Recover operator taps that no handler ever ran.

An Action chip is a human tap on Notion, and Notion gives it exactly one
delivery: the webhook fires once, and nothing retries it. If the engines are
down at that moment — an expired credential, a wedged machine, a restart — the
tap is lost in place. The card keeps showing the Action, so from the operator's
side it looks accepted, and nothing on the board ever says otherwise. That is
how a 2026-08-30 tap on a live matter sat unhandled through an OAuth outage
until someone read `board pending` by hand.

A card is orphaned when it still carries an Action but no delivery record
exists for it in daemon-pending.json. Re-running the handler is safe: it
re-reads the Action itself and is the same code the webhook would have run.

Retries are bounded — at most one recovery per card per `agent.orphan_retry_h`
hours (default 6). Without that bound this would fight the stall checker: a
genuinely stalled agent leaves the Action set and its record already dropped,
which looks identical to an orphan from here.
"""
import json
import os
import pathlib
import subprocess
import sys
import time

INBOARD = pathlib.Path(os.environ.get("INBOARD_HOME", pathlib.Path.home() / "Projects/inboard"))
STATE = INBOARD / "state/orphan-recovered.json"
PENDING = INBOARD / "state/daemon-pending.json"


def _cfg(key, default):
    r = subprocess.run(["cfg", key], capture_output=True, text=True)
    return (r.stdout.strip() or default)


def _load(p, fallback):
    try:
        return json.loads(p.read_text() or "null") or fallback
    except Exception:
        return fallback


def main():
    retry_s = float(_cfg("agent.orphan_retry_h", "6")) * 3600
    now = time.time()

    r = subprocess.run(["board", "pending"], capture_output=True, text=True)
    try:
        cards = json.loads(r.stdout or "[]")
    except Exception:
        print(f"orphan-sweep: board pending unreadable ({r.stdout[:80]!r})")
        return

    delivered = {rec.get("card") for rec in _load(PENDING, [])}
    seen = _load(STATE, {})
    recovered = 0

    for c in cards:
        card = c.get("card")
        if not card or card in delivered:
            continue
        if now - float(seen.get(card, 0)) < retry_s:
            continue
        action = c.get("action") or "?"
        print(f"orphan-sweep: recovering '{action}' on {card[:8]} (no delivery record)")
        subprocess.run(["bash", str(INBOARD / "engines/action-handler.sh"), card],
                       capture_output=True)
        seen[card] = now
        recovered += 1

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(seen, indent=1))
    print(f"orphan-sweep: {len(cards)} actioned, {recovered} recovered")


if __name__ == "__main__":
    main()
