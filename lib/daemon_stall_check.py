#!/usr/bin/env python3
"""Once per dispatch cycle: post a loud reply for any daemon-delivered ACTION
whose agent never cleared the card's Action within agent.daemon_stall_min.

This is the async path's completion check — the shell only ever learns "queued",
so a tap whose agent silently died (the 8/23 failure mode) is caught here, not by
an exit code. Only action deliveries are tracked; a comment/dispatch agent's
completion is its own card writes. Runs in the engine env (board/cfg on PATH)."""
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
    r = subprocess.run(["board", "actionof", "--card", card], capture_output=True, text=True)
    return r.stdout.strip()


def _agent_alive(card):
    """Is this card's worker still running? A busy agent is not a stalled one — real card
    work (a login, a page to read, a form) routinely outruns any timeout worth setting,
    and calling that a stall puts a warning on a card that is being handled correctly."""
    try:
        sys.path.insert(0, str(INBOARD / "lib"))
        import agent_deliver as A
        job = A.find_job("inboard-card-" + card.replace("-", ""))
        return bool(job) and job.get("state") in ("working", "running", "adopted")
    except Exception:
        return False          # cannot tell → fall back to the timeout alone


def main():
    stall_min = int(_cfg("agent.daemon_stall_min", "45"))
    stalled = [s for s in P.sweep(_actionof, stall_min * 60)
               if not _agent_alive(s["card"])]
    for s in stalled:
        subprocess.run(["board", "reply", "--card", s["card"], "--text",
                        f"⚠️ Action '{s['action']}' was delivered to this card's agent but it did not "
                        f"finish within {stall_min} min (stalled or died). NOT completed — tap the action "
                        f"again to retry."], capture_output=True)
        print(f"stalled: {s['card'][:8]} '{s['action']}'")
    print(f"daemon stall-check: {len(stalled)} stalled")


if __name__ == "__main__":
    main()
