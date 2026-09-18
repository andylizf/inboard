#!/usr/bin/env bash
# Creates Zhifei's TypeSafe AI (Jev) account at console.typesafe.ai with andylizf@gmail.com,
# using the emailed one-time code — the same two clicks he would make by hand.
# Card: 3de2a1a7-7f3f-81a0-a350-ccb3986a3b61
#
# Nothing is created until the very last click ("Verify"); every check below aborts before it,
# so a failed run leaves no account and no charge. The script never mints an API key and never
# touches billing.
set -euo pipefail

CARD="${INBOARD_CARD:?INBOARD_CARD not set — this script only runs from the card's execution button}"
OP="${INBOARD_OPERATION:?INBOARD_OPERATION not set — this script only runs from the card's execution button}"

cd /Users/andyl/Projects/inboard/agent

L=tsafesignup
EMAIL='andylizf@gmail.com'
LOGIN_URL="https://console.typesafe.ai/login?waitlist=${EMAIL}"
KEYS_URL='https://console.typesafe.ai/settings/keys'
SHOTDIR=/Users/andyl/Projects/inboard/agent/tmp
SHOT_OTP="$SHOTDIR/typesafe-otp-screen.png"
SHOT_IN="$SHOTDIR/typesafe-signed-in.png"
SHOT_KEYS="$SHOTDIR/typesafe-settings-keys.png"
mkdir -p "$SHOTDIR"

GATE_HELD=0
GATE_RESULT=unused
cleanup() {
  if [ "$GATE_HELD" = 1 ]; then twofa-gate release typesafe "$GATE_RESULT" >/dev/null 2>&1 || true; fi
  web-plane lane "$L" close >/dev/null 2>&1 || true
}
trap cleanup EXIT

snap() { web-plane lane "$L" snapshot 2>/dev/null; }

# `cmd | grep -q` is wrong under `pipefail`: grep exits at the first match, the producer takes
# SIGPIPE, and the pipeline reports failure even though the text WAS found. Match on a captured
# string instead, so a successful check can never read as a failed one.
contains() { case "$2" in *"$1"*) return 0;; *) return 1;; esac; }
has() { contains "$1" "$(snap)"; }

# Click/fill by accessible name against a FRESH snapshot. Refs are not cached: this login is a
# Next.js server-action form that re-renders after every click and renumbers every ref.
act() {
  local role="$1" action="$2" name="$3"; shift 3
  local out
  if ! out=$(web-plane lane "$L" find role "$role" "$action" --name "$name" "$@" 2>&1); then
    echo "ABORT: could not $action the $role named \"$name\"." >&2
    echo "$out" >&2
    exit 1
  fi
  printf '  %s %s: %s\n' "$action" "$name" "$(printf '%s' "$out" | grep -v '"type":"lane-source"' | tail -1)"
}

expect_marker() {
  local marker="$1" label="$2" i
  for i in $(seq 1 15); do
    if has "$marker"; then return 0; fi
    sleep 1
  done
  echo "ABORT: expected to be on $label (marker: $marker); the page never showed it. No account was created." >&2
  web-plane lane "$L" screenshot "$SHOTDIR/typesafe-abort.png" >/dev/null 2>&1 || true
  exit 1
}

echo "== 1/7 verifying the operator approved this exact preview =="
board approved-draft --card "$CARD" --operation "$OP" >/dev/null
echo "approval OK"

echo "== 2/7 checking the invite link is still live =="
CODE=$(curl -sS -o /dev/null -w '%{http_code}' -L "$LOGIN_URL")
[ "$CODE" = 200 ] || { echo "ABORT: $LOGIN_URL returned HTTP $CODE, not 200. Nothing was done." >&2; exit 1; }
PAGE=$(curl -sS -L "$LOGIN_URL")
contains "off the waitlist" "$PAGE" || {
  echo "ABORT: the login page no longer says \"You're off the waitlist\"; the invite may have been withdrawn or the page changed. Nothing was done." >&2; exit 1; }
echo "invite page OK (HTTP 200, still says \"You're off the waitlist\")"

echo "== 3/7 taking the shared verification gate =="
# The gate stops two cards from mailing him competing codes at once. If its local 90-minute
# cooldown is still running (a probe on 09-18 sent a code that was deliberately not used), the
# operator's click on this card's execution button — on a preview that says in plain words that
# TypeSafe will email him a fresh code — is the explicit request that authorizes one new attempt.
if twofa-gate acquire typesafe >/dev/null 2>&1; then
  GATE_HELD=1; echo "gate acquired"
elif twofa-gate acquire typesafe --operator-retry >/dev/null 2>&1; then
  GATE_HELD=1; echo "gate was in local cooldown; acquired once under the operator's execution click"
else
  echo "ABORT: another task currently holds the verification gate, so a second code would compete with it. Nothing was done; try again once that one finishes." >&2
  exit 1
fi

echo "== 4/7 opening the sign-in page =="
web-plane -s=main attach --as "$L" "$LOGIN_URL" >/dev/null
web-plane -s=main hide >/dev/null 2>&1 || true
expect_marker 'button "Email me a code instead"' 'the TypeSafe sign-in page'
# The waitlist= parameter pre-fills the address; confirm it rather than trusting it.
if ! has "$EMAIL"; then
  act textbox fill 'Email' "$EMAIL"
fi
has "$EMAIL" || { echo "ABORT: the email field does not hold $EMAIL. Nothing was submitted." >&2; exit 1; }
echo "email field holds $EMAIL"

echo "== 5/7 asking TypeSafe to email the one-time code =="
REQUESTED_AT=$(python3 -c 'import time; print(time.time())')
act button click 'Email me a code instead'
GATE_RESULT=timeout          # a code is now in flight; only a completed sign-in downgrades this to ok
expect_marker 'textbox "Verification code"' 'the code-entry screen'
web-plane lane "$L" screenshot "$SHOT_OTP" >/dev/null 2>&1 || true
echo "code requested; screen now asks for the 6-digit code"

echo "== 6/7 reading the code out of andylizf@gmail.com =="
OTP=$(python3 /Users/andyl/Projects/inboard/agent/scripts/typesafe-fetch-otp.py "$REQUESTED_AT")
[ ${#OTP} -eq 6 ] || { echo "ABORT: expected a 6-digit code, got ${#OTP} characters. Nothing was submitted." >&2; exit 1; }
echo "code received (6 digits, not printed here)"

echo "== 7/7 entering the code and finishing the account =="
act textbox fill 'Verification code' "$OTP"
# Last gate: Verify must actually be on screen and enabled before the one irreversible click.
has 'button "Verify"' || { echo "ABORT: no Verify button on screen. Nothing was submitted." >&2; exit 1; }
act button click 'Verify'
sleep 5

URL=$(web-plane lane "$L" get url 2>/dev/null | tail -1)
web-plane lane "$L" screenshot "$SHOT_IN" >/dev/null 2>&1 || true

if contains '/login' "$URL"; then
  echo
  echo "VERIFY CLICKED BUT NOT SIGNED IN — still on $URL. Do not click the button again; the agent will read the screenshot ($SHOT_IN) and work out what happened." >&2
  exit 2
fi

GATE_RESULT=ok
echo
echo "ACCOUNT CREATED. Signed in at: $URL"
echo "Screenshot: $SHOT_IN"

echo
echo "-- what the account looks like (read only; no API key was created, billing untouched) --"
web-plane lane "$L" goto "$KEYS_URL" >/dev/null 2>&1 || true
sleep 3
web-plane lane "$L" screenshot "$SHOT_KEYS" >/dev/null 2>&1 || true
echo "API-keys page: $(web-plane lane "$L" get url 2>/dev/null | tail -1)  (screenshot: $SHOT_KEYS)"
snap | grep -iE 'credit|balance|plan|trial|free|key' | head -20 || true
exit 0
