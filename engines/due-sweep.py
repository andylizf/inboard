#!/usr/bin/env python3
"""Daily sweep over inboard cards whose `Due` date has passed.

The whole point of the two-property design is that this script does TWO
different things, because a passed deadline means two different things:

  Lapses = true   the opportunity is gone, so there is nothing left to do
                  -> status `expired`, with the reason logged on the card.

  Lapses = false  the deadline passing made the matter WORSE, not finished
                  -> never closed. Logged once as overdue so it is visible as
                     overdue, and left demanding attention.

Auto-closing the second class is the failure this design exists to prevent:
an enrollment whose window shut is not a card to tidy away, it is a card whose
passed date is the problem.

A card already in a terminal status (done / expired / unsubscribed) is out of
scope entirely: sweeping it again would append the same "expired" verdict to
its log every single day.

Idempotence for the overdue flag comes from a small state file rather than from
writing a marker onto the card: the board is what the operator reads, and a
sweep that appends "still overdue" to a card every single day turns the card's
own audit log into noise. If `Due` is later changed, the card is marked again —
a new deadline is a new fact, not a repeat of the old one.

Runs under `uv run python` from $INBOARD_HOME so lib/ibconfig.py and its deps
resolve. Dry-run by default; --apply writes. Every run appends to
logs/due-sweep.log so a scheduled run is inspectable after the fact.
"""
import datetime
from zoneinfo import ZoneInfo
import json
import os
import pathlib
import subprocess
import sys
import urllib.request

INBOARD = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(INBOARD / "lib"))
import ibconfig as C  # noqa: E402

STATE = INBOARD / "state/due-sweep-marked.json"
LOGFILE = INBOARD / "logs/due-sweep.log"
DB = C.get("board.database_id") or sys.exit("board.database_id not configured")
TERMINAL = {C.status_name("done"), C.status_name("expired"), C.status_name("unsub")}


def api(path, payload=None):
    token = os.environ.get("NOTION_TOKEN") or sys.exit("NOTION_TOKEN not set")
    req = urllib.request.Request(
        "https://api.notion.com/v1/" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": "Bearer " + token,
                 "Notion-Version": "2022-06-28",
                 "Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=60))


def title_of(props):
    for v in props.values():
        if v.get("type") == "title":
            return "".join(x["plain_text"] for x in v["title"])
    return ""


def status_of(props):
    v = props.get("Status") or {}
    return (v.get("status") or {}).get("name", "") or (v.get("select") or {}).get("name", "")


def due_of(props):
    v = props.get("Due") or {}
    return ((v.get("date") or {}) or {}).get("start") or ""


def board(*args):
    return subprocess.run(["uv", "run", "./bin/board", *args],
                          cwd=INBOARD, capture_output=True, text=True)


def note(line):
    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    print(line)
    LOGFILE.parent.mkdir(parents=True, exist_ok=True)
    with LOGFILE.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {line}\n")


def main() -> int:
    apply = "--apply" in sys.argv
    # Whose day it is: the operator's, not the machine's. The two can sit half a
    # world apart, and asking the machine turns deadlines over mid-evening.
    tz = C.get("identity.timezone", "")
    today = datetime.datetime.now(ZoneInfo(tz) if tz else None).date()
    note(f"judging against {tz or 'machine local time'}; today there is {today}")

    cards, cursor = [], None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        page = api(f"databases/{DB}/query", payload)
        cards += page["results"]
        if not page.get("has_more"):
            break
        cursor = page["next_cursor"]

    active = [c for c in cards if status_of(c["properties"]) not in TERMINAL]
    dated = [c for c in active if due_of(c["properties"])]

    overdue = []
    for c in dated:
        raw = due_of(c["properties"])
        try:
            d = datetime.date.fromisoformat(raw[:10])
        except ValueError:
            note(f"skip [{c['id'][:8]}] unparseable Due {raw!r}")
            continue
        if d < today:
            overdue.append((c, d, (today - d).days))

    marked = json.loads(STATE.read_text()) if STATE.exists() else {}
    to_close, to_flag = [], []
    for c, d, days in overdue:
        if (c["properties"].get("Lapses") or {}).get("checkbox"):
            to_close.append((c, d, days))
        elif marked.get(c["id"]) != d.isoformat():
            to_flag.append((c, d, days))

    note(f"{len(active)} active · {len(dated)} with a Due · {len(overdue)} overdue "
         f"· {len(to_close)} to close · {len(to_flag)} to flag"
         f"{'' if apply else '  (DRY RUN)'}")

    for c, d, days in to_close:
        title = title_of(c["properties"])[:60]
        if not apply:
            note(f"  would close  [{c['id'][:8]}] Due {d} (+{days}d, lapses) {title}")
            continue
        reason = (f"Marked expired by due-sweep {today}: Due {d} passed {days} days ago and this "
                  f"matter was marked as lapsing — the window is shut. Recorded as expired rather "
                  f"than complete: it was never done.")
        r1 = board("log", "--card", c["id"], "--text", reason)
        # `expired`, not `done`: the window shut without being used, and marking that complete
        # writes something into the record that never happened. The subscription stays — a
        # follow-up about the thing that was missed still belongs on this card.
        r2 = board("edit", "--card", c["id"], "--status", "expired", "--needs", "")
        r3 = board("clear-action", "--card", c["id"])
        ok = r1.returncode == 0 and r2.returncode == 0
        note(f"  {'expired' if ok else 'FAILED'} [{c['id'][:8]}] Due {d} (+{days}d) {title}"
             + ("" if ok else f" :: {(r1.stderr + r2.stderr).strip()[:160]}"))

    for c, d, days in to_flag:
        title = title_of(c["properties"])[:60]
        if not apply:
            note(f"  would flag   [{c['id'][:8]}] Due {d} (+{days}d, hard) {title}")
            continue
        line = (f"⚠️ Overdue by {days} days (Due {d}) — the deadline passing made this matter "
                f"worse, not finished, so this card will not auto-close.")
        r = board("log", "--card", c["id"], "--text", line)
        ok = r.returncode == 0
        if ok:
            marked[c["id"]] = d.isoformat()
        note(f"  {'flagged' if ok else 'FAILED'} [{c['id'][:8]}] Due {d} (+{days}d) {title}"
             + ("" if ok else f" :: {r.stderr.strip()[:160]}"))

    if apply:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(marked, indent=1, sort_keys=True), encoding="utf-8")
    else:
        note("dry run — re-run with --apply to write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
