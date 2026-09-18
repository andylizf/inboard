#!/usr/bin/env python3
"""Dump a board card's body blocks as plain text (read-only helper for card agents)."""
import os, sys, json, urllib.request
sys.path.insert(0, os.path.join(os.environ.get("INBOARD_HOME") or "/Users/andyl/Projects/inboard", "lib"))
import ibconfig as C

tok = C.notion_token() if hasattr(C, "notion_token") else None
if not tok:
    for n in ("NOTION_TOKEN", "NOTION_API_KEY"):
        tok = tok or os.environ.get(n)
if not tok:
    cfg = C.load() if hasattr(C, "load") else {}
    tok = (cfg.get("notion") or {}).get("token")
page = sys.argv[1]

def get(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok}", "Notion-Version": "2022-06-28"})
    return json.load(urllib.request.urlopen(req))

def walk(bid, depth=0):
    cur = None
    while True:
        u = f"https://api.notion.com/v1/blocks/{bid}/children?page_size=100"
        if cur: u += f"&start_cursor={cur}"
        d = get(u)
        for b in d["results"]:
            t = b["type"]
            rt = b.get(t, {}).get("rich_text") or []
            txt = "".join(r.get("plain_text", "") for r in rt)
            if t == "to_do":
                txt = ("[x] " if b[t].get("checked") else "[ ] ") + txt
            print("  " * depth + (txt if txt else f"<{t}>"))
            if b.get("has_children"):
                walk(b["id"], depth + 1)
        if not d.get("has_more"): break
        cur = d["next_cursor"]

walk(page)
