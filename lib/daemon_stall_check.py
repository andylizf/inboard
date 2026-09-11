#!/usr/bin/env python3
"""Investigate overdue action receipts after workers stop, without assuming a failed send.

Only action deliveries are tracked. Active or unobservable workers retain their pending
records; stopped workers receive a destination-verification request, not a resend.
Runs in the engine env (board/cfg on PATH).
"""
import os
import pathlib
import subprocess
import sys

INBOARD = pathlib.Path(os.environ.get("INBOARD_HOME", pathlib.Path.home() / "Projects/inboard"))
sys.path.insert(0, str(INBOARD / "lib"))
import daemon_pending as P  # noqa: E402


def _cfg(key, default):
    r = subprocess.run(["cfg", key], capture_output=True, text=True)
    return (r.stdout.strip() or default)


def _actionof(card):
    r = subprocess.run(["board", "actionof", "--card", card], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def _agent_alive(card):
    """Is this card's worker still running? A busy agent is not a stalled one — real card
    work (a login, a page to read, a form) routinely outruns any timeout worth setting,
    and calling that a stall puts a warning on a card that is being handled correctly."""
    try:
        sys.path.insert(0, str(INBOARD / "lib"))
        import agent_deliver as A
        job = A.find_job("inboard-card-" + card.replace("-", ""))
        if not job:
            return False
        if job.get('state') in ('working', 'running', 'adopted'):
            return True
        import card_hooks as H
        import json
        path = H.session_path(job.get('sessionId', ''))
        if path.exists():
            tasks = json.loads(path.read_text()).get('background_tasks') or []
            if any(t.get('status') not in ('completed', 'failed', 'killed') for t in tasks):
                return True
        return False
    except Exception:
        return None           # unavailable is not evidence that the worker stopped


def main():
    stall_min = int(_cfg("agent.daemon_stall_min", "45"))
    stalled = P.sweep(_actionof, stall_min * 60, busy=_agent_alive)
    for s in stalled:
        import action_runs as A
        import agent_deliver as D
        with A.lock(s['card'], 'dispatch'):
            # A new click may have replaced this action during the sweep.
            if _actionof(s['card']) != s['action']:
                continue
            record = A.read(s['card'])
            token = (record or {}).get('token', '')
            prompt = (f"Investigate missing completion for card {s['card']}, action {s['action']}, "
                      f"operation {token}. The watchdog has no completion receipt after {stall_min} minutes. "
                      "This does not establish whether an external action occurred. Read the current card, "
                      "execution transcript, receipts, and actual destination. This is a verification-only "
                      "recovery: do not send or repeat an external action. If already completed, record its "
                      "verified receipt. If confirmed not completed, finish "
                      "available preparation, retain the complete draft, and report the precise failure. "
                      "If the outcome is unknown, report what cannot be verified; do not recommend resending. "
                      "After all card updates and trigger reconciliation, use board clear-action for verified "
                      "completion or board action-fail --text with the precise failure or unknown outcome. "
                      "Use exactly one final receipt and do not mutate this operation afterward. "
                      "Use the current operation token on card mutations and stop if superseded.")
            try:
                D.ensure_and_deliver('inboard-card-' + s['card'].replace('-', ''),
                                     str(INBOARD / 'agent'), prompt)
            except Exception:
                P.record(s['card'], s['action'])
                raise
            print(f"completion verification queued: {s['card']} '{s['action']}'")
    print(f"daemon stall-check: {len(stalled)} stalled")


if __name__ == "__main__":
    main()
