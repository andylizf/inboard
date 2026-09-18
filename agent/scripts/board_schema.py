#!/usr/bin/env python3
"""Print the board database's Action/Status select options (read-only)."""
import os, sys, json, urllib.request
sys.path.insert(0, os.path.join(os.environ.get("INBOARD_HOME") or "/Users/andyl/Projects/inboard", "lib"))
import ibconfig as C
tok = C.notion_token() if hasattr(C, "notion_token") else os.environ.get("NOTION_TOKEN")
db = C.get("board.database_id")
req = urllib.request.Request(f"https://api.notion.com/v1/databases/{db}", headers={
    "Authorization": f"Bearer {tok}", "Notion-Version": "2022-06-28"})
props = json.load(urllib.request.urlopen(req))["properties"]
for name in ("Action", "Status"):
    p = props.get(name)
    if not p: continue
    t = p["type"]
    print(name, "=", [o["name"] for o in p[t].get("options", [])])
