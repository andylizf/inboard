"""Execution-time guard for the 2026-09-17 "Sync TB training" RSVP.

Reads the live event JSON on stdin. Refuses to produce a patch body unless the
invite is still the one the operator approved; otherwise prints {"attendees":[...]}
with only this account's responseStatus flipped to "accepted".
"""
import json, os, sys

self_addr = os.environ["SELF"]
expect = os.environ["EXPECT_START"]


def die(msg):
    sys.stderr.write("EXECUTION-TIME CHECK FAILED: %s\n" % msg)
    sys.exit(1)


e = json.load(sys.stdin)

if e.get("status") != "confirmed":
    die("event status is %r, not 'confirmed' (organizer may have cancelled it)" % e.get("status"))

start = (e.get("start") or {}).get("dateTime")
if start != expect:
    die("start time moved: expected %s, event now says %s" % (expect, start))

att = e.get("attendees") or []
me = [a for a in att if a.get("self") or a.get("email") == self_addr]
if len(me) != 1:
    die("expected exactly one self attendee, found %d" % len(me))
if me[0].get("responseStatus") == "accepted":
    die("already accepted - nothing to send")

for a in att:
    if a.get("self") or a.get("email") == self_addr:
        a["responseStatus"] = "accepted"

print(json.dumps({"attendees": att}))
