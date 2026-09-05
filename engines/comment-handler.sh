#!/usr/bin/env bash
# Fired by webhook-server.py on a Notion comment.created event → react INSTANTLY to the operator's comment.
# The board is the durable blackboard; each CARD carries a per-card claude session id so comments on the
# SAME card resume the SAME conversation (working-memory continuity). Session is an optimization — if it's
# missing/expired we start fresh and the card body reconstructs context.
set -uo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
cd "$INBOARD_HOME/agent" || exit 1

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
  read -r LAST_AUTHOR LAST_ID < <(board comments --card "$CARD" 2>>"$INBOARD_LOGS/webhook.log" | python3 -c 'import json,sys
try: cs=json.load(sys.stdin)
except Exception: cs=[]
c=cs[-1] if cs else {}
print((c.get("author") or "-"), (c.get("id") or "-"))' 2>>"$INBOARD_LOGS/webhook.log")
  if [ "$LAST_AUTHOR" = "$BOT_UID" ]; then
    echo "[$(date)] newest comment on $CARD is our own bot reply → self-echo/dup, skip (no LLM)" >> "$INBOARD_LOGS/webhook.log"
    exit 0
  fi
  # The newest comment is the operator's. Whether a worker is already on it is kept HERE, not on the
  # card: anything posted there notifies him, so a pickup mark plus the real answer is two notifications
  # for one reply. .picked-<card> = the id of the comment last handed to a worker, and when (written on a
  # successful hand-over below). Same comment, younger than the agent deadline, worker still alive → in
  # progress, skip. Anything else — a newer comment, a dead or retired worker, the deadline passed with no
  # answer — is handed over again. With inprocess delivery the per-card lock above already covers the run.
  MARK="$INBOARD_STATE/.picked-$CARD"
  if [ -f "$MARK" ]; then
    read -r PICKED_ID PICKED_TS < "$MARK"
    if [ "$PICKED_ID" = "$LAST_ID" ]; then
      AGE=$(( ($(date +%s) - ${PICKED_TS:-0}) / 60 ))
      LIVE=""; [ "$(cfg agent.delivery inprocess)" = "daemon" ] && \
        LIVE=$(python3 "$INBOARD_HOME/lib/agent_deliver.py" session --name "$(card_agent_name "$CARD")" 2>/dev/null)
      if [ "$AGE" -lt "$(cfg agent.daemon_stall_min 45)" ] && [ -n "$LIVE" ]; then
        echo "[$(date)] comment $LAST_ID on $CARD was handed to $LIVE ${AGE}m ago, no answer yet → in progress, skip (no LLM)" >> "$INBOARD_LOGS/webhook.log"
        exit 0
      fi
      echo "[$(date)] comment $LAST_ID on $CARD was handed over ${AGE}m ago (live worker: ${LIVE:-none}) and never answered → re-run" >> "$INBOARD_LOGS/webhook.log"
    fi
  fi
fi

# --- per-card session: resume the same conversation, or open a new one and remember its id ---
SESS=(); NEWSID=""
if [ -n "$CARD" ]; then prep_session; fi

if [ -n "$CARD" ]; then
  TASK="A Notion comment fired on card $CARD (the inbox board).
The card $CARD is the affected item. Read its latest comment(s) with \`board comments --card $CARD\` and its
properties. The newest comment is the operator talking to you — an INSTRUCTION for this item (continue /
redo / send-it / drop) OR a PREFERENCE ('stop surfacing this kind of CI', 'this sender is junk', a tone note).
If a comment has a non-empty \"attachments\" list (the operator pasted a screenshot), run
\`comment-images --card $CARD\` and Read the returned local paths BEFORE answering — they are
usually asking about what is IN that image, and answering without looking reads as ignoring them.
The ONLY dedup
that counts: after reading the comments, look at the LATEST comment — if it is the operator's and you have NOT
already answered it (no bot reply of yours AFTER it), ANSWER it. Skip ONLY when the newest comment is your OWN
bot reply (nothing new) — and then skip SILENTLY: do NOT post a 'duplicate webhook' comment; that noise looks
exactly like you ignored their question.
FIRST, post a live to-do so they can watch progress in real time:
\`board plan --card $CARD --steps 'step 1|step 2|step 3'\` (2–5 short concrete steps).
Then the MOMENT you finish each step, run \`board tick --card $CARD --n <0-based index>\` before moving on.
Now ACT:
 - instruction → do it (research/redraft → \`email <id> gmail +draft --card $CARD ...\`, which makes the Gmail
   draft AND puts it on the card AND logs its id in one step — it is the only way to make a draft; move status); update the card.
   If they say it's done/handled/not-important/drop → \`board done --card $CARD\` (keeps the card in the Done column, do NOT archive).
 - preference → apply it now AND record it on the card via \`board log\` so you keep obeying it.
FINISH by (1) refreshing the card's 📌 state note (\`board note --card $CARD --text '<current state, self-contained>'\`)
and (2) replying IN THE COMMENT THREAD so they see it where they asked:
\`board reply --card $CARD --text '<2-4 short sentences, SELF-CONTAINED per CLAUDE.md's writing rules: which
matter this is in plain words, what you did/found, what they must do next — no tool jargon, no raw ids>'\`.
Put longer detail in the body via \`board log\`.
NEVER send email (drafts only)."
else
  TASK="A Notion comment fired but I couldn't resolve the card.
Scan actionable cards (\`board pending\` + read comments on the awaiting/draft cards), find the one with a fresh
comment from the operator, and handle it (instruction or preference). If they say drop/done → \`board done --card <ID>\`
(keep the card, do NOT archive). Reply in-thread with \`board reply --card <ID> --text '<short + self-contained
per CLAUDE.md's writing rules>'\` so they see it, refresh the 📌 note (\`board note\`), and \`board log\` the detail.
NEVER send email (drafts only)."
fi

# NOTE: the full Event JSON is deliberately NOT embedded — the prompt is already near the size
# (CLI prints "Goal condition is limited to 4000 characters" and exits 0 = silent no-op run). The card is
# already resolved above and the run reads live comments itself, so the payload adds nothing but bytes.
PROMPT="$TASK
Event: ${ENT_TYPE:-unknown} ${ENT_ID:-?} (payload omitted; the card above is authoritative)
$SESSION_NOTICE
$GOAL_TRAILER
$MORTAL_TRAILER"
if [ -n "${CARD:-}" ] && [ "$(cfg agent.delivery inprocess)" = "daemon" ]; then
  # Async: queue to the card's persistent daemon agent (it writes its own reply to the card).
  if deliver_to_daemon "$CARD" "$INBOARD_HOME/agent" "$PROMPT"; then RC=0; else RC=1; fi
  # Hand-over succeeded: record which comment this worker now owes an answer to (the gate above), and
  # put a 👀 on the comment so the operator sees it was picked up. A reaction, not a comment: Notion
  # notifies on every comment and never on a reaction, and the public API has no reactions, so this goes
  # through the operator's own session (NOTION_TOKEN_V2 in .env, see lib/notion_react.py). Cosmetic —
  # a failure is logged and the reply still comes from the agent.
  if [ "$RC" = 0 ] && [ -n "${LAST_ID:-}" ]; then
    printf '%s %s\n' "$LAST_ID" "$(date +%s)" > "$INBOARD_STATE/.picked-$CARD"
    if [ -n "${NOTION_TOKEN_V2:-}" ]; then
      python3 "$INBOARD_HOME/lib/notion_react.py" --comment "$LAST_ID" >>"$INBOARD_LOGS/webhook.log" 2>&1 \
        || echo "[$(date)] WARN: 👀 reaction on $LAST_ID failed (see above) — operator session cookie expired?" >> "$INBOARD_LOGS/webhook.log"
    else
      echo "[$(date)] no NOTION_TOKEN_V2 → no 👀 reaction on $LAST_ID (comment still handled)" >> "$INBOARD_LOGS/webhook.log"
    fi
  fi
  # Same reason as in action-handler: the card is where a human looks for the transcript, so it has
  # to name the session the work actually ran in, not the one that ran it before daemon delivery.
  if [ "$RC" = 0 ] && valid_uuid "${DAEMON_SID:-}" && [ "$DAEMON_SID" != "$SID" ]; then
    board session --card "$CARD" --set "$DAEMON_SID" >>"$INBOARD_LOGS/webhook.log" 2>&1 || true
  fi
  NEWSID=""
  echo "[$(date)] comment delivered to daemon agent $(card_agent_name "$CARD") rc=$RC (queued, async)" >> "$INBOARD_LOGS/webhook.log"
else
  runh() { claude -p "$PROMPT" "$@" --allowedTools "Bash,Read,Task,WebSearch,WebFetch,ToolSearch,Skill" --max-turns "$MAX_TURNS" --output-format text >> "$INBOARD_LOGS/comment-$TS.out" 2>> "$INBOARD_LOGS/comment-$TS.log"; }
  run_with_selfheal
fi

# Persist the new session id on the card only after a clean run, so the next comment resumes this thread.
if [ -n "$CARD" ] && [ -n "$NEWSID" ] && [ "$RC" = 0 ]; then
  board session --card "$CARD" --set "$NEWSID" >>"$INBOARD_LOGS/webhook.log" 2>&1
fi
if [ -n "$CARD" ] && [ "$RC" != 0 ]; then
  board reply --card "$CARD" --text "⚠️ Handling this comment failed (rc=$RC, log comment-$TS). Not completed — comment again to retry." >>"$INBOARD_LOGS/webhook.log" 2>&1 || true
fi
echo "[$(date)] comment-handler done (card=${CARD:-?} sid=${SID:-${NEWSID:-none}}) rc=$RC" >> "$INBOARD_LOGS/webhook.log"
