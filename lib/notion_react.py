#!/usr/bin/env python3
"""React to a board comment with an emoji, as the operator.

The public API has no reactions (checked against the changelog and the Comment object, 2026-09),
so this goes through the private endpoint Notion's own web app uses, authenticated with the
operator's browser session cookie (NOTION_TOKEN_V2 in .env). The reaction therefore shows as the
operator reacting to their own comment — which is the point: a reaction is the one visible "seen"
mark Notion does not notify anyone about, while a bot comment notifies the operator every time.

Private API, so it can change without notice: a failure here is logged by the caller and never
blocks the reply. Request shapes are what the web app sent on 2026-09-05 (captured with a fetch hook):
  POST /api/v3/saveTransactionsFanout   headers x-notion-active-user-header, x-notion-space-id
  new icon on a comment:   set  reaction/<new id> {id, space_id, parent_id: <comment>, parent_table:
                           "comment", icon, created_time, actors: [{table: "notion_user", id}], version: 1}
                           listAfter comment/<comment> path ["reactions"] {id: <reaction id>}
  icon already has a record (the web app leaves one behind, actors emptied, after un-reacting):
                           keyedObjectListAfter reaction/<id> path ["actors"] {value: {table, id}}
The private host is www.notion.so: app.notion.com fronts non-browser clients with a Cloudflare 403.

Usage: notion_react.py --comment <id> [--icon 👀]   → one JSON line {"reaction", "status"}; exit 1 on failure.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

HOST = "https://www.notion.so/api/v3"
NOTION_USER = "notion_user"


def _post(path, body, user=None, space=None):
    tok = os.environ.get("NOTION_TOKEN_V2")
    if not tok:
        raise SystemExit("NOTION_TOKEN_V2 is not set — the operator's session cookie is needed to react")
    h = {"Content-Type": "application/json", "Cookie": f"token_v2={tok}"}
    if user:
        h["x-notion-active-user-header"] = user
    if space:
        h["x-notion-space-id"] = space
    req = urllib.request.Request(f"{HOST}/{path}", data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{path} → HTTP {e.code}: {e.read().decode()[:200]}") from None


def _value(rec):
    v = rec.get("value") or {}
    return v.get("value") if isinstance(v.get("value"), dict) else v   # newer responses nest once more


def _records(table, ids):
    d = _post("syncRecordValues", {"requests": [{"pointer": {"table": table, "id": i}, "version": -1} for i in ids]})
    return {i: _value(rec) for i, rec in ((d.get("recordMap") or {}).get(table) or {}).items()}


def whoami():
    users = (_post("loadUserContent", {}).get("recordMap") or {}).get(NOTION_USER) or {}
    if not users:
        raise SystemExit("loadUserContent returned no user — is NOTION_TOKEN_V2 still a valid session?")
    return next(iter(users))


def react(comment_id, icon):
    me = whoami()
    comment = _records("comment", [comment_id]).get(comment_id)
    if not comment:
        raise SystemExit(f"comment {comment_id} not readable through the private API")
    space = comment["space_id"]
    existing = None
    if comment.get("reactions"):
        for rid, r in _records("reaction", comment["reactions"]).items():
            if r.get("icon") == icon:
                existing = (rid, r)
                break
    actor = {"table": NOTION_USER, "id": me}
    if existing:
        rid, r = existing
        if any(a.get("id") == me for a in r.get("actors") or []):
            return {"reaction": rid, "status": "already"}
        ops = [{"pointer": {"table": "reaction", "id": rid, "spaceId": space}, "path": ["actors"],
                "command": "keyedObjectListAfter", "args": {"value": actor}}]
    else:
        rid = str(uuid.uuid4())
        ops = [{"pointer": {"table": "reaction", "id": rid, "spaceId": space}, "path": [], "command": "set",
                "args": {"id": rid, "space_id": space, "parent_id": comment_id, "parent_table": "comment",
                         "icon": icon, "created_time": int(time.time() * 1000), "actors": [actor], "version": 1}},
               {"pointer": {"table": "comment", "id": comment_id, "spaceId": space}, "path": ["reactions"],
                "command": "listAfter", "args": {"id": rid}}]
    _post("saveTransactionsFanout",
          {"requestId": str(uuid.uuid4()),
           "transactions": [{"id": str(uuid.uuid4()), "spaceId": space,
                             "debug": {"userAction": "inboard.react", "clientCommitTimeMs": int(time.time() * 1000)},
                             "operations": ops}]},
          user=me, space=space)
    return {"reaction": rid, "status": "added"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--comment", required=True)
    ap.add_argument("--icon", default="👀")
    a = ap.parse_args()
    print(json.dumps(react(a.comment, a.icon), ensure_ascii=False))
