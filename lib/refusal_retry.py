"""Retry a refused card session at once: move the daemon to another account and re-send.

Runs detached from the hook that saw the refusal, because the recovery restarts the daemon the
hook itself is running under. The wake sweep does the same recovery on its own timer; this is
the path that does not wait for it.
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ibconfig as C
import wakeups as W

# ensure_and_deliver prepends this to every card delivery; a replayed prompt must not carry two.
PREFIX = ('Read the current CLAUDE.md in your working directory before handling this card. '
          'Read the current files for applicable project skills too; instructions remembered '
          'from an earlier turn may have changed.\n\n')


def log_path():
    return Path(os.environ.get("INBOARD_LOGS", str(Path(C.home()) / "logs"))) / "refusal-retry.log"


def emit(card, status, **fields):
    line = json.dumps({"ts": W.now().isoformat(), "card": card, "status": status, **fields}, ensure_ascii=False)
    with log_path().open("a") as f:
        print(line, file=f, flush=True)


def last_prompt(transcript):
    """The refused session's last user turn, as it was delivered."""
    text = None
    with open(transcript) as f:
        for line in f:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("type") != "user":
                continue
            content = (row.get("message") or {}).get("content")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if isinstance(content, str) and content.strip():
                text = content
    if text and text.startswith(PREFIX):
        text = text[len(PREFIX):]
    return text


def wait_for_daemon(timeout=120):
    import agent_deliver as A
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            A.live_control_sock()
            return True
        except Exception:
            time.sleep(3)
    return False


def deliver(card, prompt):
    import agent_deliver as A
    name = "inboard-card-" + card.replace("-", "")
    result = A.ensure_and_deliver(name, str(Path(C.home()) / "agent"), prompt)
    return result.get("sessionId", "") if isinstance(result, dict) else ""


def retry(card, session, transcript, dry_run=False, recover=W.recover_daemon, wait=wait_for_daemon,
          send=deliver, board=None):
    if not recover(lambda c, s, **f: emit(card, s, **f)):
        emit(card, "held", reason="no other account; the sweep retries when the refusal expires")
        return 1
    if not wait():
        emit(card, "fail", error="daemon did not answer after restart")
        return 1
    prompt = last_prompt(transcript) if transcript and os.path.exists(transcript) else None
    if not prompt:
        emit(card, "fail", error="no prompt to replay", transcript=transcript)
        return 1
    if dry_run:
        emit(card, "dry_run", prompt_chars=len(prompt))
        return 0
    sid = send(card, prompt)
    board = board or W.load_board()
    if sid:
        with contextlib.redirect_stdout(io.StringIO()):
            board.session(argparse.Namespace(card=card, set=sid))
    # A wakeup replayed whole carries its receipt, so the record goes back to pending under the
    # same token: the ack completes it, and the sweep does not send it a second time meanwhile.
    rec_path = W.root() / f"{card}.json"
    if rec_path.exists():
        rec = json.loads(rec_path.read_text())
        if rec.get("state") == "failed":
            rec.update(state="pending", delivered_at=W.now().isoformat(), retried_from=session)
            W.save(rec_path, rec)
    emit(card, "redelivered", session=sid, prompt_chars=len(prompt))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--transcript", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    emit(a.card, "start", session=a.session, dry_run=a.dry_run)
    try:
        return retry(a.card, a.session, a.transcript, a.dry_run)
    except Exception as exc:
        emit(a.card, "fail", error=f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
