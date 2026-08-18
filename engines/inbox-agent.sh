#!/usr/bin/env bash
# ENGINE 1 — the pull loop. Headless Claude Code + the inboard CLIs, run by the scheduler every N min.
# The board is the durable blackboard (source of truth); this loop runs as ONE rolling claude session per
# day (working memory), so successive cycles keep context cheaply, and the session rotates daily (bounded cost).
set -uo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

# Engine selection. `agent.dispatch: true` routes the cycle through the per-matter dispatcher
# (engines/dispatch.sh) instead of the single-session pipeline below: one agent groups the batch
# from headers, then one agent per matter reads only its own bodies. Handing off here rather than
# in the launchd job keeps the switch to one config line, and the rollback to the same line.
if [ "$(cfg agent.dispatch false)" = "true" ]; then
  exec bash "$INBOARD_HOME/engines/dispatch.sh" "$@"
fi

AGENT_DIR="$INBOARD_HOME/agent"      # holds CLAUDE.md (standing orders) + skills/
cd "$AGENT_DIR" || exit 1
[ -f "$INBOARD_STATE/processed.json" ] || echo '{}' > "$INBOARD_STATE/processed.json"

MODEL="$(cfg agent.model sonnet)"
MAX_TURNS="$(cfg agent.pull_max_turns 80)"

# Single-instance lock: never overlap runs (the scheduler fires on an interval). Stale-reclaim (>25m).
lock_or_exit "$INBOARD_STATE/.lock" 25 "$INBOARD_LOGS/agent.log" "previous run still going, skip"

# --- SELFHEAL-20260726: adaptive catch-up window ---------------------------
# Widen the triage window to cover any downtime so an outage self-heals instead
# of silently dropping mail older than the fixed 2-day window. Watermark =
# last successful cycle (YYYY/MM/DD); floored at 30 days to bound a long gap.
WM_FILE="$INBOARD_STATE/last-cycle-success"
# NOTE: use python3 for date math — mac-mini's PATH `date` is GNU (no BSD -v).
if [ -s "$WM_FILE" ]; then
  SINCE="$(cat "$WM_FILE" 2>/dev/null)"
  FLOOR="$(python3 -c 'import datetime;print((datetime.date.today()-datetime.timedelta(days=30)).strftime("%Y/%m/%d"))')"
  [ "$SINCE" \< "$FLOOR" ] && SINCE="$FLOOR"
  MAIL_WINDOW="in:inbox after:$SINCE"
else
  MAIL_WINDOW="in:inbox newer_than:2d"
fi
export INBOARD_MAIL_WINDOW="$MAIL_WINDOW"
# --- end SELFHEAL-20260726 -------------------------------------------------


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
PROMPT="$PROMPT  SELFHEAL window override: use exactly  $MAIL_WINDOW  as the +triage --query for EVERY account (this adapts to catch up any downtime; do NOT use the default 2-day window)."

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
[ "$RC" = 0 ] && python3 -c 'import datetime;print((datetime.date.today()-datetime.timedelta(days=2)).strftime("%Y/%m/%d"))' > "$INBOARD_STATE/last-cycle-success" 2>/dev/null  # SELFHEAL watermark write
echo "[$(date)] === inbox cycle done (rc=$RC) ===" >>"$LOG"
