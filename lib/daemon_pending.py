#!/usr/bin/env python3
"""Stall detection for the async daemon-delivery path.

Async delivery gives the shell only "queued", not "completed" — so a tap whose
agent silently dies mid-task (the 8/23 failure mode) would go unnoticed. This
records each daemon delivery and, on a later sweep, catches the ones whose agent
never finished: for an action delivery, "finished" means the agent cleared the
card's Action (its documented last step). A record still uncleared past the
timeout is a stall → the caller posts a loud reply and drops it.

State: state/daemon-pending.json, a list of {card, action, ts}, guarded by flock.
Pure w.r.t. Notion — the caller supplies the current-action lookup and the
reply — so this stays testable and side-effect-light.
"""
import json
import os
import pathlib
import time
import fcntl

INBOARD = pathlib.Path(os.environ.get("INBOARD_HOME", pathlib.Path.home() / "Projects/inboard"))
STATE = INBOARD / "state/daemon-pending.json"


def _load(fh):
    fh.seek(0)
    raw = fh.read().strip()
    return json.loads(raw) if raw else []


def record(card: str, action: str, now: float | None = None) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        items = _load(fh)
        items.append({"card": card, "action": action, "ts": now if now is not None else time.time()})
        fh.seek(0); fh.truncate(); fh.write(json.dumps(items, indent=1))
        fcntl.flock(fh, fcntl.LOCK_UN)


def sweep(current_action, stall_secs: int, now: float | None = None):
    """current_action(card) -> the card's live Action string (or "" if cleared).
    Returns (stalled, ...) where stalled is a list of {card, action} whose agent
    never cleared the Action within stall_secs. All resolved/stalled records are
    dropped; records still young and uncleared are kept for the next sweep."""
    now = now if now is not None else time.time()
    stalled, keep = [], []
    if not STATE.exists():
        return stalled
    with open(STATE, "r+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        for rec in _load(fh):
            live = current_action(rec["card"])
            cleared = (not live) or (live != rec["action"])
            if cleared:
                continue  # done — drop silently
            if now - rec["ts"] >= stall_secs:
                stalled.append({"card": rec["card"], "action": rec["action"]})
                continue  # stalled — drop, caller reports
            keep.append(rec)  # still working, still in time — keep
        fh.seek(0); fh.truncate(); fh.write(json.dumps(keep, indent=1))
        fcntl.flock(fh, fcntl.LOCK_UN)
    return stalled


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4 and sys.argv[1] == "record":
        record(sys.argv[2], sys.argv[3]); print("recorded")
