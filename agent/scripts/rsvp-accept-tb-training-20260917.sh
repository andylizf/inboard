#!/usr/bin/env bash
# Accept Yichuan Wang's one-off "Sync TB training" invite (2026-09-17 19:00-19:45 EDT)
# on andylizf@gmail.com, notifying the organizer and all guests.
# Card: 3de2a1a7-7f3f-8166-ae13-f9f132e4ceac
set -euo pipefail

CARD="${INBOARD_CARD:?INBOARD_CARD not set}"
OP="${INBOARD_OPERATION:?INBOARD_OPERATION not set}"
EVENT_ID="304uhqigllo1k8a3q1pma6q4m3"
ACCOUNT="personal"
SELF="andylizf@gmail.com"
EXPECT_START="2026-09-17T19:00:00-04:00"

cd /Users/andyl/Projects/inboard/agent

echo "== 1/4 verifying operator approval of the bound preview =="
board approved-draft --card "$CARD" --operation "$OP" >/dev/null
echo "approval OK"

echo "== 2/4 re-reading the live invite before responding =="
EVENT_JSON="$(email "$ACCOUNT" calendar events get \
  --params "{\"calendarId\":\"primary\",\"eventId\":\"$EVENT_ID\"}")"

PATCH_BODY="$(SELF="$SELF" EXPECT_START="$EXPECT_START" \
  python3 /Users/andyl/Projects/inboard/agent/scripts/rsvp-tb-training-build-patch.py <<<"$EVENT_JSON")"
echo "checks passed; sending acceptance"

echo "== 3/4 sending the RSVP (accept, notify all guests) =="
email "$ACCOUNT" calendar events patch \
  --params "{\"calendarId\":\"primary\",\"eventId\":\"$EVENT_ID\",\"sendUpdates\":\"all\"}" \
  --json "$PATCH_BODY" >/dev/null
echo "RSVP sent"

echo "== 4/4 reading the result back from the calendar =="
email "$ACCOUNT" calendar events get \
  --params "{\"calendarId\":\"primary\",\"eventId\":\"$EVENT_ID\"}" \
  | SELF="$SELF" python3 -c '
import json, os, sys
e = json.load(sys.stdin)
me = [a for a in (e.get("attendees") or []) if a.get("self") or a.get("email") == os.environ["SELF"]]
st = (e.get("start") or {}).get("dateTime")
print("READBACK summary   :", e.get("summary"))
print("READBACK start     :", st, "(美东 19:00-19:45)")
print("READBACK my RSVP   :", me[0].get("responseStatus") if me else "SELF NOT FOUND")
print("READBACK link      :", e.get("htmlLink"))
sys.exit(0 if me and me[0].get("responseStatus") == "accepted" else 1)
'
echo "DONE: accepted and verified."
