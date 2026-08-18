#!/usr/bin/env python3
"""Read/act on a dispatch plan. Called by dispatch.sh; keeps JSON handling out of bash.

Every subcommand that writes state/processed.json takes an exclusive flock first. Card agents run in
parallel and each finishes at its own time, so without the lock two of them read the same ledger and the
second write erases the first's entries — the messages would look unprocessed and be handled twice next
cycle. The lock is on a sidecar file rather than the ledger itself so a crashed holder cannot leave a
half-written ledger behind: the ledger is always replaced atomically via os.replace.

Subcommands:
  count <plan>                        number of groups
  field <plan> <idx> <key>            route | card | matter | ids   (ids = space-separated message ids)
  summary <plan>                      one line for the run log
  show <plan>                         human-readable plan (dry runs)
  mark-noise <plan> <ledger>          mark every noise group's messages processed
  mark-done <plan> <idx> <ledger>     mark one group's messages processed
"""
import datetime
import fcntl
import json
import os
import sys


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def groups(plan_path):
    return load(plan_path).get("groups", [])


def record(ledger_path, messages, status):
    """Merge entries into the ledger under an exclusive lock, then replace atomically."""
    lock_path = ledger_path + ".lock"
    with open(lock_path, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            try:
                with open(ledger_path, encoding="utf-8") as fh:
                    ledger = json.load(fh)
            except Exception:
                ledger = {}
            now = datetime.datetime.now().astimezone().isoformat()
            for m in messages:
                mid = m.get("id")
                if not mid:
                    continue
                ledger[mid] = {"account": m.get("account"), "status": status, "ts": now,
                               "subject": m.get("subject"), "from": m.get("from"),
                               "threadId": m.get("threadId")}
            tmp = ledger_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(ledger, fh, ensure_ascii=False)
            os.replace(tmp, ledger_path)
            return len(messages)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def main() -> int:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, plan_path = sys.argv[1], sys.argv[2]
    gs = groups(plan_path)

    if cmd == "count":
        print(len(gs))
    elif cmd == "field":
        idx, key = int(sys.argv[3]), sys.argv[4]
        g = gs[idx]
        if key == "ids":
            print(" ".join(m.get("id", "") for m in g.get("messages", [])))
        else:
            print(g.get(key) or "")
    elif cmd == "summary":
        by = {}
        msgs = 0
        for g in gs:
            by[g.get("route", "?")] = by.get(g.get("route", "?"), 0) + 1
            msgs += len(g.get("messages", []))
        print(f"{len(gs)} groups / {msgs} messages · " +
              " · ".join(f"{k}={v}" for k, v in sorted(by.items())))
    elif cmd == "show":
        for i, g in enumerate(gs):
            print(f"[{i}] route={g.get('route')} card={g.get('card') or '-'} "
                  f"msgs={len(g.get('messages', []))}  {g.get('matter')}")
            print(f"     {g.get('reason', '')}")
            for m in g.get("messages", [])[:4]:
                print(f"       - {m.get('from', '')[:34]:34}  {m.get('subject', '')[:52]}")
            if len(g.get("messages", [])) > 4:
                print(f"       … {len(g['messages']) - 4} more")
    elif cmd == "mark-noise":
        ledger = sys.argv[3]
        msgs = [m for g in gs if g.get("route") == "noise" for m in g.get("messages", [])]
        print(f"marked {record(ledger, msgs, 'noise')} noise messages processed")
    elif cmd == "mark-done":
        idx, ledger = int(sys.argv[3]), sys.argv[4]
        msgs = gs[idx].get("messages", [])
        print(f"marked {record(ledger, msgs, 'handled')} messages processed (group {idx})")
    else:
        sys.exit(f"unknown subcommand {cmd!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
