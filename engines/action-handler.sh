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

TS=$(date +%Y%m%d_%H%M%S)
# Per-card lock (SHARED with comment-handler so an Action + a comment on the same card serialize).
LK="$INBOARD_STATE/.lock-$CARD"
if ! mkdir "$LK" 2>/dev/null; then
  if [ -n "$(find "$LK" -prune -mmin +15 2>/dev/null)" ]; then
    rmdir "$LK" 2>/dev/null; mkdir "$LK" 2>/dev/null || exit 0
  else exit 0; fi
fi
trap 'rmdir "$LK" 2>/dev/null' EXIT
# Re-read after locking — Action may have been reset by a run that finished while we waited.
ACTION=$(board actionof --card "$CARD" 2>>"$INBOARD_LOGS/webhook.log")
{ [ -z "$ACTION" ] || [ "$ACTION" = "$ACTION_PLACEHOLDER" ]; } && exit 0

# Resume the card's per-card session (validate UUID; any garbage → fresh session).
SID=$(board session --card "$CARD" 2>>"$INBOARD_LOGS/webhook.log"); SESS=(); NEWSID=""
if printf '%s' "$SID" | grep -qiE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
  SESS=(--resume "$SID")
else
  NEWSID=$(python3 -c 'import uuid;print(uuid.uuid4())'); SESS=(--session-id "$NEWSID")
fi

PROMPT="/goal The operator picked Action='$ACTION' on card $CARD (the inbox board) — a no-typing decision from the select. Read CLAUDE.md (this dir).
FIRST post a live plan so they can watch: \`board plan --card $CARD --steps 'step 1|step 2|step 3'\` (2–5 steps); \`board tick --card $CARD --n <0-based>\` the instant each step is done.
Then handle the Action for card $CARD per CLAUDE.md §A — read the card (subject, draft, needs, body) and ACT on what '$ACTION' means:
  Continue/redo → research/redraft → save Gmail draft (\`email <id> gmail +reply --draft\`) → status 'Draft ready';
  Sent (you SENT/submitted your part, now AWAITING their reply) → \`board awaiting --card $CARD --desc '<the reply you are waiting for>'\` (NOT done — keep the thread open so the reply routes back to THIS card);
  Ignore/archive/confirm-done → \`board done --card $CARD\` (keep card in the Done column).
Finish: \`board clear-action --card $CARD\` (so it can be re-triggered), then \`board reply --card $CARD --text '<one line: what you did>'\` so they see it in the thread.
⚠️ Only claim success you actually verified. NEVER send email (drafts only).
GOAL — keep working toward this; do NOT stop early. Your own WORD is NOT trusted: every attempt and its outcome must be backed by concrete EVIDENCE — a screenshot, an artifact, a saved draft, uploaded to the card — and a claim with no evidence ('I tried X and it failed') does NOT count as having actually done it. You have effectively unlimited reach: whenever you do not yet see a resolution, take the next action toward it (including REACHING OUT to whoever could help — email the responsible office/support/person, ask, escalate) and EVIDENCE each one. This is DONE only when EITHER (a) the matter is RESOLVED, PROVEN by concrete evidence, OR (b) the one remaining step is inherently the operator's OWN — their decision or authority (spending money, an irreversible/final submit, a value judgment) or something only they can supply (their 2FA approval, their signature, a secret only they hold) — with everything else prepared and teed up, AND you have EVIDENCE of every alternative you actually tried on the way there. Handing back on your unproven word, or claiming resolved without evidence, does NOT count as done."
runh() { claude -p "$PROMPT" "$@" --model "$MODEL" --allowedTools "Bash,Read,Task,WebSearch,WebFetch,ToolSearch,Skill" --max-turns "$MAX_TURNS" --output-format text >> "$INBOARD_LOGS/action-$TS.out" 2>> "$INBOARD_LOGS/action-$TS.log"; }
runh ${SESS[@]+"${SESS[@]}"}; RC=$?
# self-heal: a --resume of a stale/foreign claude session fails ("No conversation found") -> retry once fresh.
if [ -z "$NEWSID" ] && [ "$RC" != 0 ]; then
  NEWSID=$(python3 -c 'import uuid;print(uuid.uuid4())')
  echo "[$(date)] resume failed (rc=$RC) card ${CARD:-?} -> fresh session, retry once" >> "$INBOARD_LOGS/webhook.log"
  runh --session-id "$NEWSID"; RC=$?
fi
if [ -n "$NEWSID" ] && [ "$RC" = 0 ]; then board session --card "$CARD" --set "$NEWSID" >>"$INBOARD_LOGS/webhook.log" 2>&1; fi
echo "[$(date)] action-handler done (card=$CARD action='$ACTION' sid=${SID:-${NEWSID:-none}}) rc=$RC" >> "$INBOARD_LOGS/webhook.log"
