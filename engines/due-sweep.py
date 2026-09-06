#!/usr/bin/env python3
"""Flag overdue cards once per deadline. Due never completes or expires a matter.

Expiry is an explicit scheduled check performed by the card agent. This daily
scan retains obligations and makes a missed deadline visible. Dry-run by default;
--apply writes, with progress in logs/due-sweep.log.
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
TERMINAL = {C.status_name("done"), C.status_name("expired"), C.status_name("unsub"), C.status_name("cancelled")}


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
    to_flag = [(c, d, days) for c, d, days in overdue if marked.get(c["id"]) != d.isoformat()]
    note(f"{len(active)} active · {len(dated)} with a Due · {len(overdue)} overdue "
         f"· {len(to_flag)} to flag{'' if apply else ' (DRY RUN)'}")

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
