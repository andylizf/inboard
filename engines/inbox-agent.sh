#!/usr/bin/env bash
# ENGINE 1 — the pull loop. Headless Claude Code + the inboard CLIs, run by the scheduler every N min.
# The board is the durable blackboard (source of truth); this loop runs as ONE rolling claude session per
# day (working memory), so successive cycles keep context cheaply, and the session rotates daily (bounded cost).
set -uo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

AGENT_DIR="$INBOARD_HOME/agent"      # holds CLAUDE.md (standing orders) + skills/
cd "$AGENT_DIR" || exit 1
[ -f "$INBOARD_STATE/processed.json" ] || echo '{}' > "$INBOARD_STATE/processed.json"

MODEL="$(cfg agent.model sonnet)"
MAX_TURNS="$(cfg agent.pull_max_turns 80)"

# Single-instance lock: never overlap runs (the scheduler fires on an interval). Stale-reclaim (>25m).
lock_or_exit "$INBOARD_STATE/.lock" 25 "$INBOARD_LOGS/agent.log" "previous run still going, skip"

# Cheap pre-check (NO LLM): skip the expensive claude run on empty cycles — protects the Claude usage quota.
if WORK=$("$INBOARD_HOME/bin/has-work" 2>>"$INBOARD_LOGS/agent.log"); then
  echo "[$(date)] work? $WORK → run agent" >> "$INBOARD_LOGS/agent.log"
else
  echo "[$(date)] work? $WORK → no work, skip claude" >> "$INBOARD_LOGS/agent.log"; exit 0
fi

TS=$(date +%Y-%m-%d_%H%M%S)
OUT="$INBOARD_LOGS/cycle-$TS.out"; LOG="$INBOARD_LOGS/cycle-$TS.log"
echo "[$(date)] === inbox cycle start ===" | tee -a "$INBOARD_LOGS/agent.log" >"$LOG"

# Daily-rolling main session: same id all day → cycles share working memory; new id each day → bounded cost.
SESS_FILE="$INBOARD_STATE/main-session-$(date +%Y%m%d)"
if [ -f "$SESS_FILE" ]; then MSID=$(cat "$SESS_FILE"); MFLAG=(--resume "$MSID"); RESUMING=1
else MSID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$MSID" >"$SESS_FILE"; MFLAG=(--session-id "$MSID"); RESUMING=0; fi

PROMPT='Run the inbox pipeline NOW, following CLAUDE.md in this directory exactly. First run `board accounts`
to see which mailboxes to check. Find new mail — READ OR UNREAD; do NOT filter by unread, your own
$INBOARD_STATE/processed.json is the seen-ledger — in EVERY configured account (via `email <account-id> gmail ...`),
triage it, and handle every important one (auto-unsubscribe clear noise via One-Click; for substantive mail
dispatch a subagent that researches and saves a Gmail DRAFT reply with `email <id> gmail +reply --draft`).
Update $INBOARD_STATE/processed.json. Output ONLY the short summary, or nothing at all if there is no new mail. Never send any email.'

run_claude() {  # $@ = session flags (kept positional — no bash-4 nameref; launchd may run bash 3.2)
  claude -p "$PROMPT" "$@" \
    --model "$MODEL" --allowedTools "Bash,Read,Write,Task,WebSearch,WebFetch,Skill" \
    --max-turns "$MAX_TURNS" --output-format text > "$OUT" 2>>"$LOG"
}

run_claude "${MFLAG[@]}"; RC=$?
# If resume failed (stale/cleaned session store), self-heal: start a fresh session for today and retry once.
if [ "$RESUMING" = 1 ] && [ "$RC" != 0 ]; then
  echo "[$(date)] resume failed (rc=$RC) → fresh session, retry once" | tee -a "$INBOARD_LOGS/agent.log" >>"$LOG"
  MSID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$MSID" >"$SESS_FILE"; NFLAG=(--session-id "$MSID")
  run_claude "${NFLAG[@]}"; RC=$?
fi

SUMMARY=$(cat "$OUT" 2>/dev/null)
echo "[$(date)] claude exit=$RC, session=$MSID, summary_bytes=$(printf %s "$SUMMARY" | wc -c)" | tee -a "$INBOARD_LOGS/agent.log" >>"$LOG"
[ -n "$SUMMARY" ] && echo "[$(date)] tally: $SUMMARY" >>"$LOG"
echo "[$(date)] === inbox cycle done (rc=$RC) ===" >>"$LOG"
