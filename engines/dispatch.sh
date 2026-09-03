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
  MAIL_WINDOW="{in:inbox in:sent} after:$SINCE"
else
  MAIL_WINDOW="{in:inbox in:sent} newer_than:2d"
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

# The standing rules live in engines/dispatcher-role.md and go in as SYSTEM prompt, not here: they are
# true every cycle, so repeating them in the task prompt spends tokens re-teaching a role that never
# changes. System prompt rather than a CLAUDE.md because CLAUDE.md loads for every agent sharing this
# directory, and the card agents have no use for dispatcher rules — and because CLAUDE.md arrives as a
# user message while this lands in the system prompt itself. CLAUDE.md is not named in the prompt
# either: it auto-loads from the working directory, so pointing at it spends tokens on something
# already in context.
DROLE_FILE="$INBOARD_HOME/engines/dispatcher-role.md"

DPROMPT="Dispatch this cycle. Do exactly this:
1. \`board accounts\` for the mailbox ids and addresses.
2. For EACH account, ONE triage call covering received and sent together:
   \`email <id> gmail +triage --query '$MAIL_WINDOW' --max 200 --format json\`
   Mark each message kind='sent' when its From is that account's own address, else kind='inbox'.
3. Subtract ids already in \$INBOARD_STATE/processed.json.
4. \`board subscriptions\`, then \`board cards\`. Read both before deciding anything is new.
5. Group the remaining messages into MATTERS and route each one.
6. Write ONLY this JSON to $PLAN — no prose, no code fence:
{\"groups\":[{\"matter\":\"<short name>\",\"route\":\"card|new|noise\",\"card\":\"<id or null>\",
  \"reason\":\"<one line>\",\"messages\":[{\"id\":\"..\",\"account\":\"<account id>\",\"subject\":\"..\",
  \"from\":\"..\",\"kind\":\"inbox|sent\"}]}]}
   Every field must be copied from the triage output. Do NOT invent a threadId — you never saw one.
Output one short line for the run log, nothing else."
# A dry run must leave the board untouched, and cross-card work WRITES.
[ "$DRY" = 0 ] && DPROMPT="$DPROMPT
Then also do the cross-card work your role describes."

# stdin is closed explicitly: without it the CLI waits 3s for piped input on EVERY invocation, which
# is one stall for the dispatcher plus one per card agent.
run_dispatch() { claude -p "$DPROMPT" "$@" --model "$MODEL" \
  --append-system-prompt-file "$DROLE_FILE" \
  --allowedTools "Bash,Read,Write,WebSearch,WebFetch,Skill" \
  --max-turns "$DISPATCH_TURNS" --output-format text < /dev/null >> "$LOG" 2>&1; }

deadline_run run_dispatch "${DFLAG[@]}"; RC=$?
if [ "$DRESUME" = 1 ] && [ "$RC" != 0 ] && [ "$RC" != 124 ]; then
  echo "[$(date)] dispatcher resume failed (rc=$RC) → fresh session, retry once" >>"$LOG"
  DSID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$DSID" >"$SESS_FILE"
  deadline_run run_dispatch --session-id "$DSID"; RC=$?
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
    PROMPT="You own ONE matter on the inbox board: card $CARD ('$matter').
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
    PROMPT="You own ONE new matter from the inbox: '$matter'.
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
    # Same as the action and comment handlers: record where the work actually ran, or the card keeps
    # naming a session that has not been touched since before daemon delivery existed.
    if [ "$RC" = 0 ] && valid_uuid "${DAEMON_SID:-}" && [ "$DAEMON_SID" != "$SID" ]; then
      board session --card "$CARD" --set "$DAEMON_SID" >>"$LOG" 2>&1 || true
    fi
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
# A tap Notion delivered while the engines were down is never redelivered, so the
# card keeps showing an Action nobody will ever act on. Recover those here.
python3 "$INBOARD_HOME/lib/orphan_action_sweep.py" >>"$LOG" 2>&1 || true
# Priority is derived, not stored: recolour every card from Due/NeedsYou/Status so the
# strip a glance lands on can never disagree with the properties underneath it.
board covers >>"$LOG" 2>&1 || true
# The operator edits preferences in the Notion panel; pull them in each cycle so a
# value changed anywhere else — including by an agent — does not outlive the pass.
python3 "$INBOARD_HOME/lib/settings_sync.py" >>"$LOG" 2>&1 || true

# Keep the card-body index warm. `board search` reads the body, which Notion cannot query, so a cold
# index means fetching every card at the moment an agent is trying to decide where a mail belongs:
# measured at 2m23s cold against 2.7s warm. Refreshing here costs nothing — only cards edited since
# the last cycle are re-fetched — and it keeps that cost off the path where it would be felt.
board search --query '' --warm >>"$LOG" 2>&1 || true
echo "[$(date)] === dispatch cycle done (failed groups=$FAILED) ===" | tee -a "$INBOARD_LOGS/agent.log" >>"$LOG"
