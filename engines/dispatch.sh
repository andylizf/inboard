#!/usr/bin/env bash
# ENGINE 1b — the DISPATCH pull loop. An alternative to inbox-agent.sh, selected by `agent.dispatch`.
#
# Why this exists. inbox-agent.sh runs one claude session over the whole batch, which is why a 101-message
# cycle opened 14 bodies: "read every message" is unaffordable at that volume, so the agent silently
# classifies from headers instead. Splitting the work restores the rule instead of quietly suspending it.
#
# The split is BY MATTER, never by message. Grouping happens in phase 1, before anything is handed off, so
# the cross-message view survives — 73 copies of the same CI notification collapse because one mind saw all
# 73. Cut per message and each agent is blind to the other 72.
#
#   phase 1  DISPATCHER (the daily rolling session; the ONLY agent that is not a card)
#            headers + subscriptions only, no bodies. Groups the batch into matters and routes each:
#            an existing card, a new matter, or noise. Emits a JSON plan. Also owns everything
#            cross-card, since no card agent can see past its own matter.
#   phase 2  CARD AGENTS, one per dispatched matter, in parallel, each resuming ITS OWN card session
#            (working-memory continuity across cycles). Each reads only its own few bodies.
#
# The shell owns state/processed.json, not the agents: N agents writing one file would clobber each other,
# and marking a message handled is a fact about whether its agent exited 0 — deterministic, so it belongs
# in deterministic code. A dispatched group is marked only after its agent succeeds, so a crashed agent
# leaves its mail unprocessed and the next cycle retries it.
set -uo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

AGENT_DIR="$INBOARD_HOME/agent"
cd "$AGENT_DIR" || exit 1
[ -f "$INBOARD_STATE/processed.json" ] || echo '{}' > "$INBOARD_STATE/processed.json"

MODEL="$(cfg agent.model sonnet)"
DISPATCH_TURNS="$(cfg agent.dispatch_max_turns 30)"
CARD_TURNS="$(cfg agent.card_max_turns 45)"
PARALLEL="$(cfg agent.dispatch_parallel 4)"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

lock_or_exit "$INBOARD_STATE/.lock" 25 "$INBOARD_LOGS/agent.log" "previous run still going, skip"

# Adaptive catch-up window (identical to inbox-agent.sh — an outage self-heals instead of dropping mail).
WM_FILE="$INBOARD_STATE/last-cycle-success"
if [ -s "$WM_FILE" ]; then
  SINCE="$(cat "$WM_FILE" 2>/dev/null)"
  FLOOR="$(python3 -c 'import datetime;print((datetime.date.today()-datetime.timedelta(days=30)).strftime("%Y/%m/%d"))')"
  [ "$SINCE" \< "$FLOOR" ] && SINCE="$FLOOR"
  MAIL_WINDOW="(in:inbox OR in:sent) after:$SINCE"
  SENT_SINCE="in:sent after:$SINCE"
  INBOX_SINCE="in:inbox after:$SINCE"
else
  MAIL_WINDOW="(in:inbox OR in:sent) newer_than:2d"
  SENT_SINCE="in:sent newer_than:2d"
  INBOX_SINCE="in:inbox newer_than:2d"
fi
export INBOARD_MAIL_WINDOW="$MAIL_WINDOW"

if [ "$DRY" = 0 ]; then
  if WORK=$("$INBOARD_HOME/bin/has-work" 2>>"$INBOARD_LOGS/agent.log"); then
    echo "[$(date)] work? $WORK → dispatch" >> "$INBOARD_LOGS/agent.log"
  else
    echo "[$(date)] work? $WORK → no work, skip" >> "$INBOARD_LOGS/agent.log"; exit 0
  fi
fi

TS=$(date +%Y-%m-%d_%H%M%S)
LOG="$INBOARD_LOGS/dispatch-$TS.log"
PLAN="$INBOARD_STATE/dispatch-plan-$TS.json"
echo "[$(date)] === dispatch cycle start (dry=$DRY) ===" | tee -a "$INBOARD_LOGS/agent.log" >"$LOG"

# ---------- phase 1: the dispatcher ----------
SESS_FILE="$INBOARD_STATE/main-session-$(date +%Y%m%d)"
if [ -f "$SESS_FILE" ]; then DSID=$(cat "$SESS_FILE"); DFLAG=(--resume "$DSID"); DRESUME=1
else DSID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$DSID" >"$SESS_FILE"; DFLAG=(--session-id "$DSID"); DRESUME=0; fi

DPROMPT="You are the DISPATCHER for the inbox board. Read CLAUDE.md in this directory for the board's vocabulary,
but do NOT run the full pipeline yourself — your whole job this cycle is to GROUP and ROUTE.

Do exactly this:
1. \`board accounts\` for the mailbox ids.
2. For EACH account, run TWO triage calls — the header listing carries no label, so which query found a
   message is the only thing that says whether it was received or sent:
     inbound: \`email <id> gmail +triage --query '$INBOX_SINCE' --max 100 --format json\`   → kind='inbox'
     outbound: \`email <id> gmail +triage --query '$SENT_SINCE' --max 100 --format json\`   → kind='sent'
   Headers only. Do NOT open message bodies — reading bodies is the card agents' job, not yours.
3. Subtract ids already in \$INBOARD_STATE/processed.json.
4. \`board subscriptions\` — every active card's own declaration of what belongs to it. This is only the
   FIRST hop and it is far from complete: it returns nothing for a card that never registered a
   subscription, and most of the board is in that state, so a card missing here is NOT evidence the
   matter is new.
4b. For any group you are about to route 'new', run \`board search --query '<sender or key subject words>'\`
   first — it searches every card's Subject and Sender regardless of status or subscription, and it is the
   only way to see the cards step 4 hides. If it returns the matter, route 'card' with that id instead.
   A message that announces itself as a repeat — 'reminder', '2nd notice', 'still awaiting', 'final
   notice' — is by definition not new: search before believing otherwise. Three cards were opened for one
   GitHub App permission request on 2026-08-22 in three consecutive cycles, the third one labelled '3rd
   notice, still no card' by the dispatcher that then opened it anyway.
5. Group the remaining messages into MATTERS. Several messages about one thing are ONE group. This
   grouping is the only place the whole batch is visible at once, so collapse duplicates here.
6. Route each group:
     route='card'  + card=<card id>  — a semantic match to a subscription, or an obvious follow-up.
     route='new'                     — a genuinely new matter that deserves its own card.
     route='noise'                   — nothing to do; no card, no agent. If a noise group looks like a
                                       real unsubscribe candidate, route it 'new' with a matter naming
                                       the sender, and its agent will do the holistic judgement.
   SENT mail routes by the same rules with one exception: a sent group that matches NO card is 'noise',
   never 'new'. inboard only ever saves drafts, so everything in the sent folder was sent by the operator
   or another session — it is news about a matter, not a request to open one. A sent message that DOES
   match a card is the most valuable event on the board: it means the reply the card was waiting for has
   gone out, which nothing else can tell it.
7. Write ONLY this JSON to $PLAN — no prose, no code fence:
{\"groups\":[{\"matter\":\"<short name>\",\"route\":\"card|new|noise\",\"card\":\"<id or null>\",
  \"reason\":\"<one line>\",\"messages\":[{\"id\":\"..\",\"account\":\"<account id>\",\"subject\":\"..\",
  \"from\":\"..\",\"kind\":\"inbox|sent\"}]}]}
   Every field must be copied from the triage output. Do NOT invent a threadId — you never saw one.
Output one short line for the run log, nothing else."
# Cross-card work WRITES, so it is appended only on a real run — a dry run must leave the board untouched.
[ "$DRY" = 0 ] && DPROMPT="$DPROMPT
Then also handle anything CROSS-CARD that this batch makes obvious (two cards that are the same matter, a
card this batch proves is finished) — you are the only agent that can see across cards."

# stdin is closed explicitly: without it the CLI waits 3s for piped input on EVERY invocation, which
# is one stall for the dispatcher plus one per card agent.
run_dispatch() { claude -p "$DPROMPT" "$@" --model "$MODEL" \
  --allowedTools "Bash,Read,Write,WebSearch,WebFetch,Skill" \
  --max-turns "$DISPATCH_TURNS" --output-format text < /dev/null >> "$LOG" 2>&1; }

run_dispatch "${DFLAG[@]}"; RC=$?
if [ "$DRESUME" = 1 ] && [ "$RC" != 0 ]; then
  echo "[$(date)] dispatcher resume failed (rc=$RC) → fresh session, retry once" >>"$LOG"
  DSID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$DSID" >"$SESS_FILE"
  run_dispatch --session-id "$DSID"; RC=$?
fi
DRC=$RC   # the dispatcher's own result; card agents run in subshells and never set this

if [ ! -s "$PLAN" ]; then
  echo "[$(date)] dispatcher produced no plan (rc=$RC) — nothing dispatched" | tee -a "$INBOARD_LOGS/agent.log" >>"$LOG"
  exit 0
fi
python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$PLAN" 2>>"$LOG" || {
  echo "[$(date)] plan is not valid JSON — refusing to dispatch, see $PLAN" | tee -a "$INBOARD_LOGS/agent.log" >>"$LOG"; exit 1; }

SUMMARY=$(python3 "$INBOARD_HOME/engines/dispatch_plan.py" summary "$PLAN")
echo "[$(date)] plan: $SUMMARY" | tee -a "$INBOARD_LOGS/agent.log" >>"$LOG"

if [ "$DRY" = 1 ]; then
  echo "--- DRY RUN: plan written to $PLAN, nothing dispatched ---"
  python3 "$INBOARD_HOME/engines/dispatch_plan.py" show "$PLAN"
  exit 0
fi

# Noise needs no agent: mark it processed here and it never costs another model call.
python3 "$INBOARD_HOME/engines/dispatch_plan.py" mark-noise "$PLAN" "$INBOARD_STATE/processed.json" >>"$LOG" 2>&1

# ---------- phase 2: one agent per matter ----------
run_group() {   # $1 = group index
  local idx="$1" route card matter ids
  route=$(python3 "$INBOARD_HOME/engines/dispatch_plan.py" field "$PLAN" "$idx" route)
  card=$(python3 "$INBOARD_HOME/engines/dispatch_plan.py" field "$PLAN" "$idx" card)
  matter=$(python3 "$INBOARD_HOME/engines/dispatch_plan.py" field "$PLAN" "$idx" matter)
  ids=$(python3 "$INBOARD_HOME/engines/dispatch_plan.py" field "$PLAN" "$idx" pairs)
  local glog="$INBOARD_LOGS/dispatch-$TS-g$idx.log"

  CARD=""; SESS=(); NEWSID=""
  if [ "$route" = "card" ] && valid_uuid "$card"; then
    CARD="$card"
    # Shared with the action/comment handlers, so a dispatch and a tap on the same card serialize.
    local LK="$INBOARD_STATE/.lock-$CARD"
    if ! mkdir "$LK" 2>/dev/null; then
      echo "[$(date)] g$idx card $CARD busy → skip this cycle" >>"$LOG"; return 0
    fi
    trap "rmdir '$LK' 2>/dev/null" RETURN
    prep_session
    PROMPT="You own ONE matter on the inbox board: card $CARD ('$matter'). Follow CLAUDE.md in this directory.
$SESSION_NOTICE
New mail on this matter, as <message-id>(<account>): $ids
Read ONLY these messages' bodies (\`email <account> gmail +read --message-id <ID>\`), then handle them per
CLAUDE.md steps 5c and 6 for THIS card only: ask memory before changing anything, update the card and its
📌 note, write back what memory now needs to know, and set Due/Lapses if a deadline appeared.
Any message marked kind='sent' in the plan is mail that WENT OUT on this matter — sent by the operator or
another session, never by you (you only ever save drafts). So it answers the card rather than asking it:
if the card was waiting for him to send, that wait is over — move it to '⏳ 等回复', clear NeedsYou, and
record what went out. If no reply is expected, close it. Log it to the daily log as a 📤 已发 entry, and
write the fact into memory, because the other sessions that need to know a reply landed cannot read this card.
Do not touch other cards — the dispatcher owns anything cross-card. Do not create a second card for this
matter. NEVER send email (drafts only).
$MORTAL_TRAILER
Output one short line."
  else
    # Mint the id BEFORE the prompt: only the agent learns the card id it creates, so it is the only one
    # that can attach the two. Without this a new matter's card is born with no Session, the next cycle
    # starts it cold, and one-card-one-agent silently does not hold for anything newly created.
    NEWSID=$(python3 -c 'import uuid;print(uuid.uuid4())'); SESS=(--session-id "$NEWSID")
    PROMPT="You own ONE new matter from the inbox: '$matter'. Follow CLAUDE.md in this directory.
Its messages, as <message-id>(<account>): $ids
Read ONLY these messages' bodies, then handle them per CLAUDE.md steps 5b, 5c and 6: check it is really not
an existing card first (\`board search\` too, not just \`board subscriptions\` — most cards have no
subscription and are invisible to the latter), ask memory, then either create ONE card (with 📌 note,
Due/Lapses if a deadline appeared) or — if it turns out to be noise or a clean unsubscribe — do that and
create no card.
If you create a card, \`board subscribe\` it whenever more mail on this matter is even plausible, and
ALWAYS when this message called itself a reminder or a follow-up — that wording is proof the sender will
write again. A card with no subscription cannot be found by the next cycle's first lookup, which is how
one matter becomes three cards. Write the subscription at the grain the OPERATOR acts on, not the grain
the sender uses: 'GitHub App permission approvals' rather than 'installation 77604681', because he
approves them all in one trip and wants one card.
If you DO create a card, attach this conversation to it as the last thing you do:
\`board session --card <the new card id> --set $NEWSID\`. That is what makes the next mail on this matter
resume YOU instead of starting cold — you are the only one who knows the card id.
NEVER send email (drafts only).
$MORTAL_TRAILER
Output one short line."
  fi

  if [ "$route" = "card" ] && valid_uuid "$CARD" && [ "$(cfg agent.delivery inprocess)" = "daemon" ]; then
    # Existing card with a persistent agent: queue new mail to it (async; it updates its own card).
    if deliver_to_daemon "$CARD" "$INBOARD_HOME/agent" "$PROMPT"; then RC=0; else RC=1; fi
    NEWSID=""
    echo "[$(date)] g$idx dispatch delivered to daemon agent $(card_agent_name "$CARD") rc=$RC" >>"$LOG"
  else
    runh() { claude -p "$PROMPT" "$@" --model "$MODEL" \
      --allowedTools "Bash,Read,Write,Task,WebSearch,WebFetch,ToolSearch,Skill" \
      --max-turns "$CARD_TURNS" --output-format text < /dev/null >> "$glog" 2>&1; }
    run_with_selfheal
  fi
  echo "[$(date)] g$idx route=$route card=${CARD:-new} rc=$RC matter='$matter'" >>"$LOG"

  if [ "$RC" = 0 ]; then
    # Only a successful agent gets its mail marked handled; a crash leaves it for the next cycle.
    python3 "$INBOARD_HOME/engines/dispatch_plan.py" mark-done "$PLAN" "$idx" "$INBOARD_STATE/processed.json" >>"$LOG" 2>&1
    [ -n "$NEWSID" ] && [ -n "$CARD" ] && board session --card "$CARD" --set "$NEWSID" >>"$LOG" 2>&1
  else
    # Subshells cannot return a status to the parent, and the watermark below must not advance on a
    # cycle where the mail was never actually handled — that is the signal the liveness watchdog reads.
    : > "$FAILDIR/$idx"
  fi
}

FAILDIR="$INBOARD_STATE/.dispatch-fail-$TS"; mkdir -p "$FAILDIR"
N=$(python3 "$INBOARD_HOME/engines/dispatch_plan.py" count "$PLAN")
i=0; running=0
while [ "$i" -lt "$N" ]; do
  route=$(python3 "$INBOARD_HOME/engines/dispatch_plan.py" field "$PLAN" "$i" route)
  if [ "$route" != "noise" ]; then
    run_group "$i" &
    running=$((running+1))
    [ "$running" -ge "$PARALLEL" ] && { wait -n 2>/dev/null || wait; running=$((running-1)); }
  fi
  i=$((i+1))
done
wait

FAILED=$(find "$FAILDIR" -type f 2>/dev/null | wc -l | tr -d ' '); rmdir "$FAILDIR" 2>/dev/null
# The watermark is "mail actually got handled", not "the dispatcher ran" — the watchdog treats a stale
# watermark WITH work waiting as a stall, so advancing it after every agent failed would hide the outage.
if [ "$DRC" = 0 ] && [ "$FAILED" = 0 ]; then
  python3 -c 'import datetime;print((datetime.date.today()-datetime.timedelta(days=2)).strftime("%Y/%m/%d"))' > "$INBOARD_STATE/last-cycle-success" 2>/dev/null
else
  echo "[$(date)] watermark NOT advanced (dispatcher rc=$DRC, failed groups=$FAILED)" | tee -a "$INBOARD_LOGS/agent.log" >>"$LOG"
fi
# Plans are debugging artifacts, not state anything reads back. Keep the recent ones and drop the
# rest — an unpruned per-cycle file is the same monotonic pile the cards and the sessions were.
ls -1t "$INBOARD_STATE"/dispatch-plan-*.json 2>/dev/null | tail -n +51 | while read -r f; do rm -f "$f"; done
python3 "$INBOARD_HOME/lib/daemon_stall_check.py" >>"$LOG" 2>&1 || true
echo "[$(date)] === dispatch cycle done (failed groups=$FAILED) ===" | tee -a "$INBOARD_LOGS/agent.log" >>"$LOG"
