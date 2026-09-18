#!/usr/bin/env python3
"""Subtract already-processed message ids from this cycle's triage output."""
import json, sys, os

STATE = os.environ.get("INBOARD_STATE", "/Users/andyl/Projects/inboard/state")
PERSONAL = sys.argv[1]
WORK = sys.argv[2]

proc = json.load(open(os.path.join(STATE, "processed.json")))
if isinstance(proc, dict):
    seen = set(proc.get("ids") or proc.keys())
else:
    seen = set(proc)

out = []
for acct, path in (("personal", PERSONAL), ("work", WORK)):
    d = json.load(open(path))
    for m in d["messages"]:
        if m["id"] in seen:
            continue
        out.append({"id": m["id"], "account": acct, "date": m["date"],
                    "from": m["from"], "subject": m["subject"]})

print(f"UNPROCESSED {len(out)}")
for m in sorted(out, key=lambda x: (x["account"], x["from"])):
    print(f'{m["id"]}\t{m["account"]}\t{m["from"]}\t{m["subject"]}')
