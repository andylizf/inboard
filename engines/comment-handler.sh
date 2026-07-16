#!/usr/bin/env bash
# Fired by webhook-server.py on a Notion comment.created event → react INSTANTLY to the operator's comment.
# The board is the durable blackboard; each CARD carries a per-card claude session id so comments on the
# SAME card resume the SAME conversation (working-memory continuity). Session is an optimization — if it's
# missing/expired we start fresh and the card body reconstructs context.
set -uo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
cd "$INBOARD_HOME/agent" || exit 1

MODEL="$(cfg agent.model sonnet)"
MAX_TURNS="$(cfg agent.interactive_max_turns 45)"
BOT_UID="$(cfg board.bot_user_id)"   # this integration's Notion user id (created_by on our own comments)

# NOTE: do NOT write ${1:-{}} — bash parses the {} default so the first } closes the expansion and a stray
# } gets appended to $1, corrupting the JSON. Be explicit:
EVENT="$1"; [ -n "$EVENT" ] || EVENT='{}'
TS=$(date +%Y%m%d_%H%M%S)_$$   # +PID: same-second handlers must not share a log file

# --- entity from the event ---
read -r ENT_TYPE ENT_ID < <(printf '%s' "$EVENT" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); e=d.get("entity",{}); print((e.get("type") or "")+" "+(e.get("id") or ""))
except Exception: print(" ")')

# --- resolve the affected CARD (comment → parent page; else the page itself) — BEFORE locking ---
CARD=""
if [ "$ENT_TYPE" = "comment" ] && [ -n "$ENT_ID" ]; then
  CARD=$(board resolve --comment "$ENT_ID" 2>>"$INBOARD_LOGS/webhook.log")
elif [ "$ENT_TYPE" = "page" ] && [ -n "$ENT_ID" ]; then
  CARD="$ENT_ID"
fi

# PER-CARD lock: comments on DIFFERENT cards run concurrently — a busy card never makes us DROP another
# card's comment. Same-card events coalesce safely (the run reads ALL latest comments). Stale-reclaim (>15m).
LK="$INBOARD_STATE/.lock-${CARD:-global}"
lock_or_exit "$LK" 15 "$INBOARD_LOGS/webhook.log" "$LK busy (same card already handling) → coalesced-skip"
sleep 2  # let a same-card burst settle

# Deterministic dedup (NO LLM): only proceed if the NEWEST comment is from a HUMAN, not our own bot reply.
# A self-triggered webhook (our reply fired it) or a duplicate re-delivery leaves the BOT comment newest → skip
# silently so claude is never even invoked (no wasted run, no "duplicate webhook" noise comment).
if [ -n "$CARD" ] && [ -z "$BOT_UID" ]; then
  echo "[$(date)] WARN: board.bot_user_id empty -> self-echo dedup DISABLED (run inboard init or set board.bot_user_id)" >> "$INBOARD_LOGS/webhook.log"
fi
if [ -n "$CARD" ] && [ -n "$BOT_UID" ]; then
  LAST_AUTHOR=$(board comments --card "$CARD" 2>>"$INBOARD_LOGS/webhook.log" | python3 -c 'import json,sys
try: cs=json.load(sys.stdin)
except Exception: cs=[]
print((cs[-1].get("author") or "") if cs else "")' 2>>"$INBOARD_LOGS/webhook.log")
  if [ "$LAST_AUTHOR" = "$BOT_UID" ]; then
    echo "[$(date)] newest comment on $CARD is our own bot reply → self-echo/dup, skip (no LLM)" >> "$INBOARD_LOGS/webhook.log"
    exit 0
  fi
fi

# --- per-card session: resume the same conversation, or open a new one and remember its id ---
SESS=(); NEWSID=""
if [ -n "$CARD" ]; then prep_session; fi

if [ -n "$CARD" ]; then
  TASK="A Notion comment fired on card $CARD (the inbox board). Read CLAUDE.md (this dir).
The card $CARD is the affected item. Read its latest comment(s) with \`board comments --card $CARD\` and its
properties. The newest comment is the operator talking to you — an INSTRUCTION for this item (continue /
redo / send-it / drop) OR a PREFERENCE ('stop surfacing this kind of CI', 'this sender is junk', a tone note).
The ONLY dedup
that counts: after reading the comments, look at the LATEST comment — if it is the operator's and you have NOT
already answered it (no bot reply of yours AFTER it), ANSWER it. Skip ONLY when the newest comment is your OWN
bot reply (nothing new) — and then skip SILENTLY: do NOT post a 'duplicate webhook' comment; that noise looks
exactly like you ignored their question.
FIRST, post a live to-do so they can watch progress in real time:
\`board plan --card $CARD --steps 'step 1|step 2|step 3'\` (2–5 short concrete steps).
Then the MOMENT you finish each step, run \`board tick --card $CARD --n <0-based index>\` before moving on.
Now ACT:
 - instruction → do it (research/redraft → save a Gmail draft with the right helper per CLAUDE.md: \`+reply --draft\`
   only when answering someone ELSE's message, \`+compose-draft\` for new recipients or threads the operator started; move status); update the card.
   If they say it's done/handled/not-important/drop → \`board done --card $CARD\` (keeps the card in the Done column, do NOT archive).
 - preference → apply it now AND record it on the card via \`board log\` so you keep obeying it.
FINISH by (1) refreshing the card's 📌 state note (\`board note --card $CARD --text '<current state, self-contained>'\`)
and (2) replying IN THE COMMENT THREAD so they see it where they asked:
\`board reply --card $CARD --text '<2-4 short sentences, SELF-CONTAINED per CLAUDE.md's writing rules: which
matter this is in plain words, what you did/found, what they must do next — no tool jargon, no raw ids>'\`.
Put longer detail in the body via \`board log\`.
NEVER send email (drafts only)."
else
  TASK="A Notion comment fired but I couldn't resolve the card. Read CLAUDE.md (this dir).
Scan actionable cards (\`board pending\` + read comments on the awaiting/draft cards), find the one with a fresh
comment from the operator, and handle it (instruction or preference). If they say drop/done → \`board done --card <ID>\`
(keep the card, do NOT archive). Reply in-thread with \`board reply --card <ID> --text '<short + self-contained
per CLAUDE.md's writing rules>'\` so they see it, refresh the 📌 note (\`board note\`), and \`board log\` the detail.
NEVER send email (drafts only)."
fi

# NOTE: the full Event JSON is deliberately NOT embedded — /goal hard-caps its condition at 4000 chars
# (CLI prints "Goal condition is limited to 4000 characters" and exits 0 = silent no-op run). The card is
# already resolved above and the run reads live comments itself, so the payload adds nothing but bytes.
PROMPT="/goal $TASK
Event: ${ENT_TYPE:-unknown} ${ENT_ID:-?} (payload omitted; the card above is authoritative)
$GOAL_TRAILER"
cap_goal_prompt
runh() { claude -p "$PROMPT" "$@" --model "$MODEL" --allowedTools "Bash,Read,Task,WebSearch,WebFetch,ToolSearch,Skill" --max-turns "$MAX_TURNS" --output-format text >> "$INBOARD_LOGS/comment-$TS.out" 2>> "$INBOARD_LOGS/comment-$TS.log"; }
run_with_selfheal

# Persist the new session id on the card only after a clean run, so the next comment resumes this thread.
if [ -n "$CARD" ] && [ -n "$NEWSID" ] && [ "$RC" = 0 ]; then
  board session --card "$CARD" --set "$NEWSID" >>"$INBOARD_LOGS/webhook.log" 2>&1
fi
echo "[$(date)] comment-handler done (card=${CARD:-?} sid=${SID:-${NEWSID:-none}}) rc=$RC" >> "$INBOARD_LOGS/webhook.log"
