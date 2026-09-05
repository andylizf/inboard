#!/usr/bin/env python3
"""ENGINE 3 — the comment catch-up poll (webhook backstop).

inboard's operator comments are delivered by a Notion `comment.created`
webhook (engine 2). That path has no queue: if the webhook is down (outage,
or Notion pausing the subscription after repeated delivery failures), comments
are silently dropped — unlike mail and Action buttons, which the pull loop
polls. This engine polls active cards for threads whose NEWEST comment is the
operator's (i.e. the agent never replied) and drives comment-handler.sh for
each, exactly as the webhook would.

comment-handler self-echo-dedups (skips when the newest comment is the bot's)
and skips a comment it already handed to a live worker (state/.picked-<card>),
so a poll during the run and a poll after the reply both do nothing — safe to
run on a schedule. Run it via `inboard comment-catchup` (which sources
_common.sh for NOTION_TOKEN + the venv on PATH); launchd fires it on a timer.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.environ.get("INBOARD_HOME") or
                                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import ibconfig as C  # noqa: E402

HOME = C.home()
ENGINES = os.path.join(HOME, "engines")
TOKEN = os.environ.get("NOTION_TOKEN")
BOT = C.get("board.bot_user_id")
BOARD = C.get("board.database_id")
# terminal statuses we don't need to poll for new operator comments
SKIP_STATUS = {s for s in (C.get("board.schema.status.done"),
                           C.get("board.schema.status.unsub")) if s}
DEADLINE = time.time() + int(C.get("schedule.comment_catchup_budget_seconds", 900))
H = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28",
     "Content-Type": "application/json"}

if not (TOKEN and BOT and BOARD):
    sys.stderr.write("comment-catchup: missing NOTION_TOKEN / board.bot_user_id / "
                     "board.database_id — is the config initialized?\n")
    sys.exit(2)


def api(method, url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers=H, method=method)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def status_of(p):
    for v in p.get("properties", {}).values():
        if v.get("type") == "status" and v.get("status"):
            return v["status"].get("name", "")
    return ""


def title_of(p):
    for v in p.get("properties", {}).values():
        if v.get("type") == "title":
            return "".join(x.get("plain_text", "") for x in v.get("title", []))
    return "(untitled)"


# 1. active cards (skip terminal statuses)
pages, cur = [], None
while True:
    body = {"page_size": 100}
    if cur:
        body["start_cursor"] = cur
    d = api("POST", f"https://api.notion.com/v1/databases/{BOARD}/query", body)
    pages += d["results"]
    if not d.get("has_more"):
        break
    cur = d.get("next_cursor")
active = [p for p in pages if status_of(p) not in SKIP_STATUS]

# 2. for each active card whose newest comment is the operator's, run the handler.
# Dispatch ALL concurrently, then WAIT (bounded) before exiting: launchd reaps a
# job's children when the job exits, so a fire-and-forget Popen would be killed
# mid-run (no reply → re-fire loop). Waiting keeps the job alive until handlers
# finish; concurrency means a slow card doesn't block the others.
procs = []
for p in active:
    try:
        cs = api("GET", f"https://api.notion.com/v1/comments?block_id={p['id']}").get("results", [])
    except Exception:
        continue
    if not cs:
        continue
    cs.sort(key=lambda x: x.get("created_time", ""))
    last = cs[-1]
    if (last.get("created_by") or {}).get("id") == BOT:
        continue  # already answered
    event = json.dumps({"entity": {"id": last["id"], "type": "comment"}})
    txt = "".join(x.get("plain_text", "") for x in last.get("rich_text", []))[:80]
    print(f"→ catch-up firing on: {title_of(p)[:45]} | comment: {txt}")
    procs.append((subprocess.Popen(["bash", os.path.join(ENGINES, "comment-handler.sh"), event]),
                  title_of(p)[:45]))

done = 0
for proc, ti in procs:
    remaining = max(1, int(DEADLINE - time.time()))
    try:
        proc.wait(timeout=remaining)
        done += 1
    except subprocess.TimeoutExpired:
        print(f"  (still running past budget, left to finish: {ti})")

if procs:
    print(f"comment catch-up: {done}/{len(procs)} handler(s) completed "
          f"(of {len(active)} active cards).")
