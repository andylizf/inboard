#!/usr/bin/env python3
"""Dump a board card's properties as plain text (read-only helper for card agents)."""
import os, sys, json, urllib.request
sys.path.insert(0, os.path.join(os.environ.get("INBOARD_HOME") or "/Users/andyl/Projects/inboard", "lib"))
import ibconfig as C

tok = C.notion_token() if hasattr(C, "notion_token") else None
if not tok:
    for n in ("NOTION_TOKEN", "NOTION_API_KEY"):
        tok = tok or os.environ.get(n)
page = sys.argv[1]
only = sys.argv[2:]
req = urllib.request.Request(f"https://api.notion.com/v1/pages/{page}", headers={
    "Authorization": f"Bearer {tok}", "Notion-Version": "2022-06-28"})
pr = json.load(urllib.request.urlopen(req))["properties"]
for name, v in pr.items():
    if only and name not in only:
        continue
    t = v["type"]
    val = v[t]
    if isinstance(val, list):
        val = "".join(r.get("plain_text", "") for r in val) if val and isinstance(val[0], dict) and "plain_text" in val[0] else json.dumps(val, ensure_ascii=False)
    elif isinstance(val, dict):
        val = val.get("name") or val.get("start") or json.dumps(val, ensure_ascii=False)
    print(f"=== {name} ({t}) ===")
    print(val)
    print()
