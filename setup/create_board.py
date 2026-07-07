#!/usr/bin/env python3
"""Create the inboard Notion kanban database (and, optionally, a daily-log DB) under a parent page you've
shared with the integration. Idempotent-ish: pass --parent-page to pick the page; the DB is created fresh.

Reads the Notion token from the env var named by config `board.token_env` (default NOTION_TOKEN), and the
Account select options + canonical statuses/actions from the inboard config/schema. Prints JSON:
    {"database_id": ..., "daily_log_database_id": ...|null, "bot_user_id": ..., "url": ...}
`inboard init` consumes this and writes the ids back into inboard.config.yaml.

Usage:
    python3 setup/create_board.py [--parent-page "<title or page id>"] [--with-daily]
"""
import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.environ.get("INBOARD_HOME") or
                                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import ibconfig as C  # noqa: E402

STATUS_COLORS = {"📥 New": "gray", "🔍 Researching": "blue", "✍️ Draft ready": "green",
                 "⏳ Awaiting reply": "yellow", "✅ Done": "default", "🚫 Unsubscribed": "red"}
ACCOUNT_COLORS = ["blue", "orange", "green", "purple", "pink", "brown"]


def notion(method, path, token, body=None):
    req = urllib.request.Request(
        "https://api.notion.com/v1" + path,
        data=json.dumps(body).encode() if body is not None else None, method=method,
        headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def page_title(p):
    for v in p.get("properties", {}).values():
        if v.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in v.get("title", []))
    return ""


def find_parent(token, wanted):
    res = notion("POST", "/search", token, {"filter": {"property": "object", "value": "page"}})["results"]
    if wanted:
        for p in res:
            if p["id"] == wanted or wanted.lower() in page_title(p).lower() or wanted in (p.get("url") or ""):
                return p
        sys.exit(f"create_board: no shared page matching '{wanted}' — share it with the integration first.")
    if len(res) == 1:
        return res[0]
    if not res:
        sys.exit("create_board: no page shared with the integration — create a page and share it, then pass --parent-page.")
    titles = ", ".join(page_title(p) or "(untitled)" for p in res[:8])
    sys.exit(f"create_board: multiple shared pages ({titles}...) — disambiguate with --parent-page \"<title>\".")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent-page", default=None)
    ap.add_argument("--with-daily", action="store_true")
    a = ap.parse_args()

    token_env = C.get("board.token_env", "NOTION_TOKEN") or "NOTION_TOKEN"
    token = os.environ.get(token_env)
    if not token:
        sys.exit(f"create_board: ${token_env} not set — put the Notion integration token in .env.")

    me = notion("GET", "/users/me", token)
    bot_id = me.get("id") or ""

    parent = find_parent(token, a.parent_page)

    account_opts = [{"name": lbl, "color": ACCOUNT_COLORS[i % len(ACCOUNT_COLORS)]}
                    for i, lbl in enumerate(C.account_labels())] or [{"name": "Personal", "color": "blue"}]
    status_opts = [{"name": s, "color": STATUS_COLORS.get(s, "default")} for s in C.STATUS_NAMES]
    action_opts = [{"name": C.ACTION_PLACEHOLDER, "color": "default"}] + \
                  [{"name": x, "color": c} for x, c in zip(C.ACTIONS, ["green", "blue", "gray"])]

    db = notion("POST", "/databases", token, {
        "parent": {"type": "page_id", "page_id": parent["id"]},
        "title": [{"type": "text", "text": {"content": "📬 inboard"}}],
        "properties": {
            "Subject":      {"title": {}},
            "Status":       {"select": {"options": status_opts}},
            "Account":      {"select": {"options": account_opts}},
            "Sender":       {"rich_text": {}},
            "Action":       {"select": {"options": action_opts}},
            "Draft":        {"rich_text": {}},
            "NeedsYou":     {"rich_text": {}},
            "Subscription": {"rich_text": {}},
            "MsgID":        {"rich_text": {}},
            "Session":      {"rich_text": {}},
            "StepBlocks":   {"rich_text": {}},
            "Updated":      {"date": {}},
        },
    })

    daily_id = None
    if a.with_daily:
        daily = notion("POST", "/databases", token, {
            "parent": {"type": "page_id", "page_id": parent["id"]},
            "title": [{"type": "text", "text": {"content": "📓 inboard — daily log"}}],
            "properties": {
                "Item":    {"title": {}},
                "Date":    {"date": {}},
                "Type":    {"select": {"options": [{"name": t, "color": "default"} for t in C.DAILY_TYPES]}},
                "Account": {"select": {"options": account_opts}},
                "Detail":  {"rich_text": {}},
            },
        })
        daily_id = daily["id"]

    print(json.dumps({"database_id": db["id"], "daily_log_database_id": daily_id,
                      "bot_user_id": bot_id, "url": db.get("url"),
                      "parent_page": parent["id"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
