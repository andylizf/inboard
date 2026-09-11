#!/usr/bin/env bash
# Fired by webhook-server.py on page.properties_updated → if the operator picked an Action on the card (a
# no-typing decision from the select), handle it INSTANTLY. Cheap-gated: a Notion GET decides whether to run
# at all, so claude only spawns when an Action is actually set (no loops, no waste).
set -uo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
cd "$INBOARD_HOME/agent" || exit 1

MAX_TURNS="$(cfg agent.interactive_max_turns 45)"
ACTION_PLACEHOLDER="$(cfg board.schema.action_placeholder '👉 Pick action')"

CARD="${1:-}"; [ -n "$CARD" ] || exit 0

# CHEAP GATE (no claude): only proceed if a REAL Action was picked — empty or the placeholder = no-op.
ACTION=$(board actionof --card "$CARD" 2>>"$INBOARD_LOGS/webhook.log")
{ [ -z "$ACTION" ] || [ "$ACTION" = "$ACTION_PLACEHOLDER" ]; } && exit 0

# Native buttons keep intent separate from the legacy Action field that old agents clear.
if [ -n "$(board action-request --card "$CARD")" ]; then
  PROMPT="The operator picked Action='__ACTION__' on card $CARD.
Read the card and handle this action per the card-actions skill. Use board plan and board tick to show progress.
For Continue/redo, carry out the remaining substantive work and produce the deliverable; do not stop at research, a plan or instructions for the operator. Preserve existing authorization and follow card-actions for any new outward approval.
For the configured send action, follow card-actions: check current facts, validate the approved preview, then execute with the destination's tool. Email uses email gmail +send-approved.
Complete card updates, then use the single final receipt prescribed by card-actions.
$GOAL_TRAILER
$MORTAL_TRAILER"
  python3 "$INBOARD_HOME/lib/action_runs.py" --card "$CARD" --prompt "$PROMPT" >>"$INBOARD_LOGS/webhook.log" 2>&1
  exit $?
fi

TS=$(date +%Y%m%d_%H%M%S)_$$   # +PID: same-second handlers must not share a log file
# Per-card lock (SHARED with comment-handler so an Action + a comment on the same card serialize).
LK="$INBOARD_STATE/.lock-$CARD"
lock_or_exit "$LK" 15 "$INBOARD_LOGS/webhook.log" "$LK busy (same card already handling) → action skip"
# Re-read after locking — Action may have been reset by a run that finished while we waited.
ACTION=$(board actionof --card "$CARD" 2>>"$INBOARD_LOGS/webhook.log")
{ [ -z "$ACTION" ] || [ "$ACTION" = "$ACTION_PLACEHOLDER" ]; } && exit 0

# Move the card NOW, before the agent is asked to do anything. Until this existed the agent was the
# only thing that ever changed a Status, so a run that hit its deadline, died, or read the action
# differently left the card exactly where it was — the operator saw a tap that did nothing. The status
# a tap implies is not a judgement call, so it should not depend on a process staying alive.
# `board status-for` returns nothing for the send action: mail can fail to leave, and only a completed
# send may move a card to awaiting.
NEWSTATUS=$(board status-for --action "$ACTION" 2>>"$INBOARD_LOGS/webhook.log")
if [ -n "$NEWSTATUS" ]; then
  if board edit --card "$CARD" --status "$NEWSTATUS" >>"$INBOARD_LOGS/webhook.log" 2>&1; then
    echo "[$(date)] action '$ACTION' → status $NEWSTATUS (card=$CARD)" >> "$INBOARD_LOGS/webhook.log"
  else
    echo "[$(date)] WARN could not set status $NEWSTATUS on $CARD; agent still runs" >> "$INBOARD_LOGS/webhook.log"
  fi
fi

# Resume the card's per-card session (validate UUID; any garbage → fresh session).
prep_session

# The per-Action semantics (continue/redo, done/ignore, daily-log step) are deliberately NOT
# respelled here — the card-actions skill is the single source of truth; a summary here WILL drift from it
# (it already had: the daily-log step was missing). The prompt names the skill rather than leaving it to the
# model's judgement, which the docs say is not guaranteed to fire in -p mode.
PROMPT="The operator picked Action='$ACTION' on card $CARD (the inbox board) — a no-typing decision from the select.
$SESSION_NOTICE
Read the card (subject, draft, needs, body) before posting a live plan with \`board plan --card $CARD --steps 'step 1|step 2|step 3'\`; tick each step when done.
Handle Action='$ACTION' per the card-actions skill, including its final receipt and configured daily-log procedure.
For Continue/redo, execute the remaining work and produce the deliverable; a reminder or instruction for the operator does not complete it. Preserve existing authorization.
Record the outcome and reply with \`board reply --card $CARD --text '<what happened and what remains>'\`. Complete card updates, then use the single final receipt prescribed by card-actions.
Outward messages and submissions require the send action and the current-facts/approval checks in card-actions. Email uses +send-approved; other destinations use their native tools.
$GOAL_TRAILER
$MORTAL_TRAILER"
if [ "$(cfg agent.delivery inprocess)" = "daemon" ]; then
  # Async path: queue the prompt to the card's persistent daemon agent; it writes results to the card
  # itself. RC here is delivery-acceptance, not task completion — the loud-failure reply below still
  # fires when the daemon could not take it (daemon down / agent unreachable), stranding the tap.
  if deliver_to_daemon "$CARD" "$INBOARD_HOME/agent" "$PROMPT"; then RC=0;
    python3 "$INBOARD_HOME/lib/daemon_pending.py" record "$CARD" "$ACTION" 2>>"$INBOARD_LOGS/webhook.log" || true
  else RC=1; fi
  # Record where the work actually happened. The daemon owns the session, but the CARD is what a
  # human (or a later run) reads to find the transcript, and an unrecorded one is worse than none:
  # it keeps naming a session that has been dead for weeks.
  if [ "$RC" = 0 ] && valid_uuid "${DAEMON_SID:-}" && [ "$DAEMON_SID" != "$SID" ]; then
    board session --card "$CARD" --set "$DAEMON_SID" >>"$INBOARD_LOGS/webhook.log" 2>&1 || true
  fi
  NEWSID=""  # the daemon owns the session id; the line above is what puts it on the card
  echo "[$(date)] action delivered to daemon agent $(card_agent_name "$CARD") rc=$RC (queued, async)" >> "$INBOARD_LOGS/webhook.log"
else
  runh() { claude -p "$PROMPT" "$@" --allowedTools "Bash,Read,Task,WebSearch,WebFetch,ToolSearch,Skill" --max-turns "$MAX_TURNS" --output-format text >> "$INBOARD_LOGS/action-$TS.out" 2>> "$INBOARD_LOGS/action-$TS.log"; }
  run_with_selfheal
  if [ -n "$NEWSID" ] && [ "$RC" = 0 ]; then board session --card "$CARD" --set "$NEWSID" >>"$INBOARD_LOGS/webhook.log" 2>&1; fi
fi
# A silent failure strands the tap: the operator approved an action, nothing happened, and nothing
# said so (found the hard way: a send died at max-turns and sat unnoticed for three days).
if [ "$RC" != 0 ]; then
  board reply --card "$CARD" --text "⚠️ Action '$ACTION' returned an execution error (rc=$RC, log action-$TS). The external outcome is unverified; check the destination before any resend." >>"$INBOARD_LOGS/webhook.log" 2>&1 || true
fi
echo "[$(date)] action-handler done (card=$CARD action='$ACTION' sid=${SID:-${NEWSID:-none}}) rc=$RC" >> "$INBOARD_LOGS/webhook.log"
