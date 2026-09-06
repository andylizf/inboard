"""Card schedules and completion receipts for unattended agent wakeups."""
import argparse
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path
import uuid
from datetime import datetime, timezone

import ibconfig as C


def now():
    return datetime.now(timezone.utc)


def instant(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("wake time needs an explicit UTC offset, e.g. 2026-10-01T09:00:00-04:00")
    return dt


def text(value):
    # Each Notion text run has a size limit; never truncate a stored schedule.
    return [{"type": "text", "text": {"content": value[i:i + 1800]}}
            for i in range(0, len(value), 1800)]


def read(page):
    raw = "".join(t.get("plain_text", t.get("text", {}).get("content", ""))
                  for t in page["properties"].get("Wakeups", {}).get("rich_text", []))
    return json.loads(raw) if raw else []


def properties(rules):
    ordered = sorted(rules, key=lambda r: instant(r["at"]))
    return {"Wakeups": {"rich_text": text(json.dumps(ordered, ensure_ascii=False)) if ordered else []},
            "NextCheck": {"date": {"start": ordered[0]["at"]} if ordered else None},
            "NextAction": {"rich_text": text("\n".join(f'{r["at"]} — {r["reason"]}' for r in ordered))}}


def add(rules, at, reason):
    instant(at)
    if not reason.strip():
        raise ValueError("a wakeup needs the action or source to check")
    # Repeating the same tool call after a lost response must not create another timer.
    if not any(instant(r["at"]) == instant(at) and r["reason"] == reason for r in rules):
        rules = rules + [{"id": uuid.uuid4().hex, "at": at, "reason": reason}]
    return rules


def root():
    return Path(os.environ.get("INBOARD_STATE", str(Path(C.home()) / "state"))) / "wake-deliveries"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.replace(path)


def acknowledge(board, card, token):
    path = root() / f"{card}.json"
    rec = json.loads(path.read_text())
    if rec["token"] != token:
        raise ValueError("wake receipt does not match this delivery")
    page = board.api("GET", f"/pages/{card}")
    fired = {r["id"] for r in rec["rules"]}
    remaining = [r for r in read(page) if r["id"] not in fired]
    board.api("PATCH", f"/pages/{card}", {"properties": {**properties(remaining), **board.touched()}})
    rec.update(state="complete", completed_at=now().isoformat())
    save(path, rec)
    save(root() / f"{card}-{token}-complete.json", rec)
    return rec


def load_board():
    loader = importlib.machinery.SourceFileLoader("wake_board", str(Path(C.home()) / "bin/board"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


def candidates(board):
    cursor = None
    while True:
        query = {"page_size": 100, "filter": {"property": "NextCheck", "date": {"on_or_before": now().isoformat()}},
                 "sorts": [{"property": "NextCheck", "direction": "ascending"}]}
        if cursor:
            query["start_cursor"] = cursor
        result = board.api("POST", f"/databases/{board.DB}/query", query)
        yield from result["results"]
        if not result.get("has_more"):
            break
        cursor = result["next_cursor"]


def deliver(card, prompt, board):
    import subprocess
    # Use the same session rotation and delivery path as mail/actions, including in-process installs.
    result = subprocess.run(["bash", str(Path(C.home()) / "engines/wake-handler.sh"), card],
                            input=prompt, text=True, capture_output=True, timeout=1800)
    if result.returncode:
        raise RuntimeError(f"wake handler failed ({result.returncode}): {result.stderr[-500:]}")


def active(card):
    if C.get("agent.delivery", "inprocess") != "daemon":
        return False
    import agent_deliver as A
    job = A.find_job("inboard-card-" + card.replace("-", ""))
    return bool(job and job.get("state") in ("working", "running", "adopted"))


def sweep(board, emit, send=deliver, busy=active, clock=now):
    failures = 0
    delivered = 0
    for snapshot in candidates(board):
        card = snapshot["id"]
        emit(card, "start")
        lock = Path(os.environ.get("INBOARD_STATE", str(Path(C.home()) / "state"))) / f".lock-{card}"
        acquired = False
        try:
            try:
                lock.mkdir()
                acquired = True
            except FileExistsError:
                # Shared engine locks expire after 25 minutes; live daemon work is checked below.
                if clock().timestamp() - lock.stat().st_mtime <= 25 * 60:
                    emit(card, "skip", reason="card_busy")
                    continue
                lock.rmdir()
                lock.mkdir()
                acquired = True
            page = board.api("GET", f"/pages/{card}")
            status = board._g(page["properties"], "Status", "select")
            if page.get("archived") or status in {C.status_name(k) for k in board.CLOSED_KEYS}:
                emit(card, "skip", reason="closed")
                continue
            action = board._g(page["properties"], "Action", "select")
            if action and action != board.ACTION_PLACEHOLDER:
                emit(card, "skip", reason="operator_action_pending")
                continue
            rules = [r for r in read(page) if instant(r["at"]) <= clock()]
            if not rules:
                emit(card, "skip", reason="schedule_changed")
                continue
            path = root() / f"{card}.json"
            rec = json.loads(path.read_text()) if path.exists() else {}
            if rec.get("state") == "pending":
                if (clock() - instant(rec["delivered_at"])).total_seconds() < 45 * 60:
                    emit(card, "skip", reason="delivery_pending")
                    continue
            if busy(card):
                emit(card, "skip", reason="agent_working")
                continue
            if delivered >= int(C.get("agent.dispatch_parallel", 4)):
                emit(card, "skip", reason="batch_limit")
                continue
            token = uuid.uuid4().hex
            prompt = (f"Scheduled wakeup for card {card}. Receipt: {token}.\n"
                      "Load board-cli. Read the full card and current mail/state before acting.\n"
                      f"Due checks (these are instructions to inspect, not evidence the condition is true): {json.dumps(rules, ensure_ascii=False)}\n"
                      "Continue the work yourself. Reconcile ALL future triggers against the latest facts; cancel obsolete ones. "
                      "If still waiting, set a concrete next check with board schedule and put the card in waiting. "
                      "Only use needs_you when the operator has a concrete action now. "
                      "Due passing alone never proves completion. Record verified results in the card note/log. "
                      "Never send email; prepare drafts only. "
                      f"Finish with board wake-ack --card {card} --token {token}. "
                      "This acknowledges these checks, not completion of the matter.\n")
            rec = {"card": card, "token": token, "rules": rules, "prompt": prompt,
                   "delivered_at": clock().isoformat(), "state": "pending"}
            # Keep every attempt: a failed delivery and its exact input remain inspectable after retry.
            save(root() / f"{card}-{token}.json", rec)
            save(path, rec)
            board.edit(argparse.Namespace(card=card, status="researching", needs=None, subject=None,
                                          draft=None, sender=None, due=None))
            emit(card, "deliver", token=token, rules=rules)
            try:
                send(card, prompt, board)
            except Exception:
                rec["state"] = "failed"
                save(path, rec)
                raise
            emit(card, "accepted", token=token)
            delivered += 1
        except Exception as exc:
            failures += 1
            emit(card, "fail", error=str(exc))
        finally:
            if acquired:
                lock.rmdir()
    if failures:
        raise RuntimeError(f"{failures} card wakeups failed; retained for retry")
