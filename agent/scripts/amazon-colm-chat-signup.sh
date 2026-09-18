#!/usr/bin/env bash
# Submits Zhifei's sign-up for Amazon's 15-minute research chats at COLM 2026.
# Form: https://pulse.amazon/survey/ELOQ7CMN?p=0  (7 pages, no login, nothing stored until the final Submit)
# Every step is verified; any mismatch aborts BEFORE the final Submit, so a failure submits nothing.
set -euo pipefail

CARD="${INBOARD_CARD:?INBOARD_CARD not set — this script only runs from the card's execution button}"
OP="${INBOARD_OPERATION:?INBOARD_OPERATION not set — this script only runs from the card's execution button}"
cd /Users/andyl/Projects/inboard/agent

# Refuse to run unless the preview the operator approved is still the current one.
board approved-draft --card "$CARD" --operation "$OP" > /dev/null

L=amzcolm
URL='https://pulse.amazon/survey/ELOQ7CMN?p=0'
SHOT=/Users/andyl/Projects/inboard/agent/tmp/amzcolm-submitted.png
mkdir -p /Users/andyl/Projects/inboard/agent/tmp

w() { web-plane lane "$L" "$@" 2>&1 | grep -v '"type":"lane-source"' || true; }
snap() { web-plane lane "$L" snapshot 2>/dev/null; }

# Abort unless the page we are about to act on is the page we expect.
expect_page() {
  local marker="$1" label="$2" i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if snap | grep -qF "$marker"; then return 0; fi
    sleep 1
  done
  echo "ABORT: expected to be on $label (marker: $marker) but the page never showed it. Nothing was submitted." >&2
  web-plane lane "$L" screenshot "$SHOT" >/dev/null 2>&1 || true
  exit 1
}

# Click/fill by accessible name against a FRESH snapshot, and fail loudly if the control is gone.
act() {
  local role="$1" action="$2" name="$3"; shift 3
  local out
  if ! out=$(web-plane lane "$L" find role "$role" "$action" --name "$name" "$@" 2>&1); then
    echo "ABORT: could not $action the $role named \"$name\". Nothing was submitted." >&2
    echo "$out" >&2
    exit 1
  fi
  printf '  %s %s: %s\n' "$action" "$name" "$(printf '%s' "$out" | grep -v '"type":"lane-source"' | tail -1)"
}

echo "Opening the Amazon COLM research-chat form..."
web-plane -s=main attach --as "$L" "$URL" >/dev/null
trap 'web-plane lane "$L" close >/dev/null 2>&1 || true' EXIT

echo "Page 1 of 7 — name, email, university, year"
expect_page 'textbox "Full Name"' 'page 1'
act textbox fill 'Full Name'    'Zhifei Li'
act textbox fill 'Email Address' 'andylizf@gmail.com'
act textbox fill 'University'    'Princeton University'
act radio   click '1st year'
act radio   click '2030+'
act button  click 'Next'

echo "Page 2 of 7 — research areas, presenting or not"
expect_page 'checkbox "Optimization / ML Systems"' 'page 2'
act checkbox click 'Optimization / ML Systems'
act checkbox click 'AI Agents / Code Generation'
act checkbox click 'LLMs / Foundation Models / Post-training'
act checkbox click 'Yes - poster'
act button   click 'Next'

echo "Page 3 of 7 — paper links"
expect_page 'textbox "Link to COLM paper"' 'page 3'
act textbox fill 'Link to COLM paper' 'https://openreview.net/forum?id=puRQNPwKs1 (EvoX) and https://openreview.net/forum?id=EGl9L6K5ob (CocoaBench)'
act button  click 'Next'

echo "Page 4 of 7 — days at COLM and preferred time windows"
expect_page 'checkbox "Tuesday, Oct 6 (Main Conference Day 1)"' 'page 4'
act checkbox click 'Tuesday, Oct 6 (Main Conference Day 1)'
act checkbox click 'Wednesday, Oct 7 (Main Conference Day 2)'
act checkbox click 'Thursday, Oct 8 (Main Conference Day 3)'
act checkbox click 'Friday, Oct 9 (Workshops)'
act checkbox click 'Morning (9:00–11:30 AM)'
act checkbox click 'Midday (11:30 AM–1:30 PM)'
act checkbox click 'Afternoon (1:30–4:00 PM)'
act button   click 'Next'

echo "Page 5 of 7 — internship interest"
expect_page 'radio "Maybe – open to learning more"' 'page 5'
act radio  click 'Maybe – open to learning more'
act button click 'Next'

echo "Page 6 of 7 — internship timing (deliberately left blank; it is optional)"
expect_page 'checkbox "Summer 2027"' 'page 6'
act button click 'Next'

echo "Page 7 of 7 — comments, then submit"
expect_page 'textbox "Questions/Comments"' 'page 7'
act textbox fill 'Questions/Comments' 'I have two posters in Poster Session 5 on Thursday, Oct 8. Any slot outside that session works.'

# Last gate: the Submit button must actually be the one on screen.
if ! snap | grep -qF 'button "Submit"'; then
  echo "ABORT: page 7 has no Submit button. Nothing was submitted." >&2
  exit 1
fi

echo "Submitting..."
act button click 'Submit'
sleep 3

web-plane lane "$L" screenshot "$SHOT" >/dev/null 2>&1 || true
PAGE=$(snap || true)
if printf '%s' "$PAGE" | grep -qiF 'calendar invite with your chat details'; then
  echo
  echo "SUBMITTED. Amazon's confirmation reads: \"Thanks! You'll receive a calendar invite with your chat details by Oct 2.\""
  echo "Screenshot of the confirmation: $SHOT"
  exit 0
fi

echo
echo "SUBMIT CLICKED BUT NOT CONFIRMED — the page did not show Amazon's confirmation text." >&2
echo "Do not click again. Screenshot saved to $SHOT; the agent will check what actually happened." >&2
exit 2
