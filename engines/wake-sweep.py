#!/usr/bin/env python3
"""Run due card checks without starting the mail dispatcher."""
import fcntl
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import wakeups as W


def main():
    logs = Path(os.environ.get("INBOARD_LOGS", str(ROOT / "logs")))
    logs.mkdir(parents=True, exist_ok=True)
    state = Path(os.environ.get("INBOARD_STATE", str(ROOT / "state")))
    state.mkdir(parents=True, exist_ok=True)
    with (state / "wake-sweep.lock").open("a") as lock, (logs / "wake-sweep.log").open("a") as log:
        def emit(card, status, **fields):
            line = json.dumps({"ts": W.now().isoformat(), "card": card, "status": status, **fields}, ensure_ascii=False)
            print(line, file=log, flush=True)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            emit(None, "skip", reason="sweep_running")
            return
        emit(None, "start")
        try:
            W.sweep(W.load_board(), emit)
        except Exception as exc:
            emit(None, "fail", error=str(exc))
            raise
        emit(None, "done")


if __name__ == "__main__":
    main()
