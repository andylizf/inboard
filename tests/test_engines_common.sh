#!/usr/bin/env bash
# Unit tests for the shared helpers in engines/_common.sh — run against a throwaway INBOARD_STATE/LOGS
# so nothing touches production state. Exercises: valid_uuid, lock_or_exit, cap_goal_prompt,
# run_with_selfheal, and GOAL_TRAILER integrity.
set -u
T=$(mktemp -d)
export INBOARD_HOME="${INBOARD_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}" INBOARD_STATE="$T/state" INBOARD_LOGS="$T/logs"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${COMMON_SH:-$REPO/engines/_common.sh}"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok: $1"; }
bad() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# --- valid_uuid ---
valid_uuid "8658e3d7-adf5-4ee2-8c8b-40c4e3fb365f" && ok "uuid accepts well-formed" || bad "uuid rejects well-formed"
valid_uuid "not-a-uuid" && bad "uuid accepts garbage" || ok "uuid rejects garbage"
valid_uuid "" && bad "uuid accepts empty" || ok "uuid rejects empty"

# --- lock_or_exit: acquire, busy-skip, stale-reclaim (in subshells so exit 0 doesn't kill us) ---
LOG="$T/lock.log"
( lock_or_exit "$T/lk1" 15 "$LOG" "busy-msg" && touch "$T/acquired" )
[ -e "$T/acquired" ] && ok "lock acquired when free" || bad "lock not acquired when free"
[ -d "$T/lk1" ] && bad "EXIT trap did not clean lock" || ok "EXIT trap cleaned lock on exit"
mkdir "$T/lk2"   # fresh contender
( lock_or_exit "$T/lk2" 15 "$LOG" "busy-msg"; touch "$T/should-not-exist" )
[ -e "$T/should-not-exist" ] && bad "busy lock did not skip" || ok "busy lock skips (exit 0)"
grep -q "busy-msg" "$LOG" && ok "busy message logged" || bad "busy message not logged"
mkdir "$T/lk3"; touch -t 202601010101 "$T/lk3"   # stale contender (way older than 15 min)
( lock_or_exit "$T/lk3" 15 "$LOG" "busy-msg" && touch "$T/reclaimed" )
[ -e "$T/reclaimed" ] && ok "stale lock reclaimed" || bad "stale lock not reclaimed"

# --- cap_goal_prompt ---
CARD="test-card"
PROMPT="/goal $(printf 'x%.0s' $(seq 1 4100))"
cap_goal_prompt
case "$PROMPT" in "/goal"*) bad "oversize prompt kept /goal";; *) ok "oversize prompt stripped /goal";; esac
grep -q "4000 cap" "$INBOARD_LOGS/webhook.log" && ok "cap WARN logged" || bad "cap WARN not logged"
PROMPT="/goal short"
cap_goal_prompt
case "$PROMPT" in "/goal short") ok "small prompt untouched";; *) bad "small prompt mutated";; esac

# --- run_with_selfheal: resume fails once -> fresh retry once ---
CALLS="$T/calls"; : > "$CALLS"
runh() { echo "runh $*" >> "$CALLS"; case "$*" in *--resume*) return 1;; *) return 0;; esac; }
SESS=(--resume "dead-session"); NEWSID=""
run_with_selfheal
[ "$RC" = 0 ] && ok "selfheal recovered rc=0" || bad "selfheal rc=$RC"
[ "$(wc -l < "$CALLS")" = 2 ] && ok "exactly 2 attempts" || bad "attempts: $(cat "$CALLS")"
grep -q -- "--session-id" "$CALLS" && ok "retry used fresh session id" || bad "retry lacked fresh session"
grep -q "resume failed" "$INBOARD_LOGS/webhook.log" && ok "selfheal logged" || bad "selfheal not logged"
# fresh session that fails must NOT retry
: > "$CALLS"; runh() { echo "runh $*" >> "$CALLS"; return 3; }
SESS=(--session-id "new-id"); NEWSID="new-id"
run_with_selfheal
[ "$RC" = 3 ] && [ "$(wc -l < "$CALLS")" = 1 ] && ok "fresh-session failure not retried" || bad "fresh failure retried (rc=$RC)"

# --- GOAL_TRAILER integrity ---
[ "${#GOAL_TRAILER}" -gt 1000 ] && ok "trailer present (${#GOAL_TRAILER} chars)" || bad "trailer too short"
case "$GOAL_TRAILER" in *"does NOT count as done."*) ok "trailer ends intact";; *) bad "trailer tail corrupted";; esac

echo "---- PASS=$PASS FAIL=$FAIL"
rm -rf "$T"
[ "$FAIL" = 0 ]
