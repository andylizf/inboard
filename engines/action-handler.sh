#!/usr/bin/env bash
# Fired by webhook-server.py on page.properties_updated → if the operator picked an Action on the card (a
# no-typing decision from the select), handle it INSTANTLY. Cheap-gated: a Notion GET decides whether to run
# at all, so claude only spawns when an Action is actually set (no loops, no waste).
set -uo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
cd "$INBOARD_HOME/agent" || exit 1

MODEL="$(cfg agent.model sonnet)"
MAX_TURNS="$(cfg agent.interactive_max_turns 45)"
ACTION_PLACEHOLDER="$(cfg board.schema.action_placeholder '👉 Pick action')"

CARD="${1:-}"; [ -n "$CARD" ] || exit 0

# CHEAP GATE (no claude): only proceed if a REAL Action was picked — empty or the placeholder = no-op.
ACTION=$(board actionof --card "$CARD" 2>>"$INBOARD_LOGS/webhook.log")
{ [ -z "$ACTION" ] || [ "$ACTION" = "$ACTION_PLACEHOLDER" ]; } && exit 0

TS=$(date +%Y%m%d_%H%M%S)_$$   # +PID: same-second handlers must not share a log file
# Per-card lock (SHARED with comment-handler so an Action + a comment on the same card serialize).
LK="$INBOARD_STATE/.lock-$CARD"
lock_or_exit "$LK" 15 "$INBOARD_LOGS/webhook.log" "$LK busy (same card already handling) → action skip"
# Re-read after locking — Action may have been reset by a run that finished while we waited.
ACTION=$(board actionof --card "$CARD" 2>>"$INBOARD_LOGS/webhook.log")
{ [ -z "$ACTION" ] || [ "$ACTION" = "$ACTION_PLACEHOLDER" ]; } && exit 0

# Resume the card's per-card session (validate UUID; any garbage → fresh session).
prep_session

# The per-Action semantics (continue/redo, sent-awaiting, done/ignore, daily-log step) are deliberately NOT
# respelled here — CLAUDE.md §A is the single source of truth; a summary here WILL drift from it (it already
# had: the daily-log step was missing).
PROMPT="/goal The operator picked Action='$ACTION' on card $CARD (the inbox board) — a no-typing decision from the select. Read CLAUDE.md (this dir).
$SESSION_NOTICE
FIRST post a live plan so they can watch: \`board plan --card $CARD --steps 'step 1|step 2|step 3'\` (2–5 steps); \`board tick --card $CARD --n <0-based>\` the instant each step is done.
Then read the card (subject, draft, needs, body) and handle Action='$ACTION' EXACTLY per CLAUDE.md §A — the actioned-card playbook there (including its daily-log step when a daily log is configured) is the single source of truth; do not improvise a different flow.
Finish: \`board clear-action --card $CARD\` (so it can be re-triggered), then \`board reply --card $CARD --text '<one line: what you did>'\` so they see it in the thread.
Email may leave ONLY when this Action is the send action, and ONLY via the +send-approved path in §A; for every other action, drafts only — never send.
$GOAL_TRAILER
$MORTAL_TRAILER"
cap_goal_prompt
if [ "$(cfg agent.delivery inprocess)" = "daemon" ]; then
  # Async path: queue the prompt to the card's persistent daemon agent; it writes results to the card
  # itself. RC here is delivery-acceptance, not task completion — the loud-failure reply below still
  # fires when the daemon could not take it (daemon down / agent unreachable), stranding the tap.
  if deliver_to_daemon "$CARD" "$INBOARD_HOME/agent" "$PROMPT"; then RC=0; else RC=1; fi
  NEWSID=""  # the daemon owns the card's session; nothing for the shell to persist
  echo "[$(date)] action delivered to daemon agent $(card_agent_name "$CARD") rc=$RC (queued, async)" >> "$INBOARD_LOGS/webhook.log"
else
  runh() { claude -p "$PROMPT" "$@" --model "$MODEL" --allowedTools "Bash,Read,Task,WebSearch,WebFetch,ToolSearch,Skill" --max-turns "$MAX_TURNS" --output-format text >> "$INBOARD_LOGS/action-$TS.out" 2>> "$INBOARD_LOGS/action-$TS.log"; }
  run_with_selfheal
  if [ -n "$NEWSID" ] && [ "$RC" = 0 ]; then board session --card "$CARD" --set "$NEWSID" >>"$INBOARD_LOGS/webhook.log" 2>&1; fi
fi
# A silent failure strands the tap: the operator approved an action, nothing happened, and nothing
# said so (found the hard way: a send died at max-turns and sat unnoticed for three days).
if [ "$RC" != 0 ]; then
  board reply --card "$CARD" --text "⚠️ Action '$ACTION' failed (rc=$RC, log action-$TS). It was NOT completed — tap the action again to retry." >>"$INBOARD_LOGS/webhook.log" 2>&1 || true
fi
echo "[$(date)] action-handler done (card=$CARD action='$ACTION' sid=${SID:-${NEWSID:-none}}) rc=$RC" >> "$INBOARD_LOGS/webhook.log"
