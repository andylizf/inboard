#!/usr/bin/env bash
# Shared environment bootstrap for every inboard engine. Source this at the top of each engine/handler:
#     source "$(dirname "$0")/_common.sh"
# Sets INBOARD_HOME/STATE/LOGS, puts the uv venv + bin/ first on PATH, loads secrets (.env) and the
# optional HTTPS proxy from config. Nothing personal is hardcoded — it all comes from inboard.config.yaml.

# Resolve the install root (the dir that contains engines/ and bin/).
INBOARD_HOME="${INBOARD_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export INBOARD_HOME
export INBOARD_STATE="${INBOARD_STATE:-$INBOARD_HOME/state}"
export INBOARD_LOGS="${INBOARD_LOGS:-$INBOARD_HOME/logs}"
mkdir -p "$INBOARD_STATE" "$INBOARD_LOGS"

# .venv/bin FIRST (so `python3` = the uv venv python with PyYAML), then bin/ (so `email` shadows the
# real `gws`, and `board`/`browser`/`has-work` resolve), then the user's normal PATH.
export PATH="$INBOARD_HOME/.venv/bin:$INBOARD_HOME/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"

# Secrets (NOTION_TOKEN, etc.) — kept in a gitignored .env at the install root.
set -a; [ -f "$INBOARD_HOME/.env" ] && . "$INBOARD_HOME/.env"; set +a

# Optional HTTPS proxy (blank = direct).
_PROXY="$(cfg network.https_proxy 2>/dev/null || true)"
if [ -n "${_PROXY:-}" ]; then
  export HTTPS_PROXY="$_PROXY" HTTP_PROXY="$_PROXY" ALL_PROXY="$_PROXY" NO_PROXY="127.0.0.1,localhost"
fi

# ---------- shared engine helpers (single source of truth — do NOT re-implement in engines) ----------

# Goal-mode trailer appended to every event-driven /goal prompt (comment- and action-handler).
# ---- daemon delivery (opt-in via agent.delivery: daemon) ----------------------------------------
# card_agent_name <card-id> — the deterministic name of a card's persistent daemon-hosted agent.
card_agent_name() { echo "inboard-card-${1:0:8}"; }

# deliver_to_daemon <card> <cwd> <prompt> — queue PROMPT to the card's persistent agent through the
# Claude Code daemon (lib/agent_deliver.py). Returns 0 when the daemon ACCEPTED it (queued to a live
# session), non-zero if the daemon is down or the agent could not be reached. "Accepted" is not
# "completed": the agent runs asynchronously and, per the mortality rule, writes its own results to
# the card. Requires a token-carrying Claude Code daemon (see the deployment scripts) to be running.
deliver_to_daemon() {
  python3 "$INBOARD_HOME/lib/agent_deliver.py" deliver \
    --name "$(card_agent_name "$1")" --cwd "$2" --text "$3" >>"$INBOARD_LOGS/webhook.log" 2>&1
}

GOAL_TRAILER="GOAL — keep working toward this; do NOT stop early. Your own WORD is NOT trusted: every attempt and its outcome
must be backed by concrete EVIDENCE — a screenshot, an artifact, a saved draft, uploaded to the card — and a
claim with no evidence ('I tried X and it failed') does NOT count as having actually done it. You have
effectively unlimited reach: whenever you do not yet see a resolution, take the next action toward it (including
REACHING OUT to whoever could help — email the responsible office/support/person, ask, escalate) and EVIDENCE
each one. This is DONE only when EITHER (a) the matter is RESOLVED, PROVEN by concrete evidence, OR (b) the one
remaining step is inherently the operator's OWN — their decision or authority (spending money, an
irreversible/final submit, a value judgment) or something only they can supply (their 2FA approval, their
signature, a secret only they hold) — with everything else prepared and teed up, AND you have EVIDENCE of every
alternative you actually tried on the way there. Handing back on your unproven word, or claiming resolved
without evidence, does NOT count as done."

valid_uuid() { printf '%s' "${1:-}" | grep -qiE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; }

# lock_or_exit <lockdir> <stale-minutes> <logfile> <busy-message>
# mkdir-lock with stale reclaim (a SIGKILLed run can't clean its trap → steal locks older than <stale-minutes>).
# Exits 0 (= skip this event/cycle) when genuinely contended; on success installs an EXIT trap that cleans up.
lock_or_exit() {
  local lk="$1" stale="$2" log="$3" busy="$4"
  if ! mkdir "$lk" 2>/dev/null; then
    if [ -n "$(find "$lk" -prune -mmin +"$stale" 2>/dev/null)" ]; then
      rmdir "$lk" 2>/dev/null; mkdir "$lk" 2>/dev/null \
        && echo "[$(date)] reclaimed stale lock $lk" >> "$log" \
        || { echo "[$(date)] $lk contended, skip" >> "$log"; exit 0; }
    else
      echo "[$(date)] $busy" >> "$log"; exit 0
    fi
  fi
  trap "rmdir '$lk' 2>/dev/null" EXIT
}

# Appended to every per-card agent prompt. The card outlives the agent by design, but that only
# works if the agent behaves accordingly — a send once died at max-turns with its findings held
# only in conversation, and the operator learned nothing for three days.
MORTAL_TRAILER="You are MORTAL: this session can die at any turn (turn cap, crash, rotation) and your successor starts
with NONE of this conversation. The card is the only memory that survives you — write to it AS YOU GO
(board log / note the moment you learn or decide something), never only at the end: anything not on the
card when you die never happened."
# Set by prep_session when a card's session is rotated; every prompt may interpolate it, so it must
# exist even when prep_session was never called (engines run under set -u).
SESSION_NOTICE=""

# session_too_big <session-id> — true when that transcript has outgrown agent.session_rotate_mb.
# The transcript lives under ~/.claude/projects/<cwd with / turned into ->/<id>.jsonl; engines always run
# from $INBOARD_HOME/agent, so the slug comes from the current directory. A missing file is NOT too big:
# an unreadable path must not silently rotate every card on every cycle.
session_too_big() {
  local sid="${1:-}" limit_mb f bytes
  limit_mb="$(cfg agent.session_rotate_mb 1)"
  f="$HOME/.claude/projects/$(pwd | tr '/' '-')/$sid.jsonl"
  [ -f "$f" ] || return 1
  bytes=$(wc -c < "$f" 2>/dev/null | tr -d ' ')
  [ -n "$bytes" ] || return 1
  [ "$bytes" -gt $(( limit_mb * 1024 * 1024 )) ]
}

# session_stale <session-id> — true when that transcript last moved more than
# agent.session_max_idle_days ago. A stale session is invalidated, never deleted: the next touch
# starts fresh (months-old working memory carries assumptions the card has since outgrown), while
# the transcript stays on disk as history. A missing file is NOT stale — the resume-failure path
# owns that case.
session_stale() {
  local sid="${1:-}" days f
  days="$(cfg agent.session_max_idle_days 60)"
  f="$HOME/.claude/projects/$(pwd | tr '/' '-')/$sid.jsonl"
  [ -f "$f" ] || return 1
  [ -n "$(find "$f" -mtime +"$days" -print 2>/dev/null)" ]
}

# prep_session — resume the card's per-card claude session, or mint a fresh id.
# Reads CARD; sets SID, SESS (claude session flags), NEWSID (non-empty only when starting fresh).
# Resume ONLY a well-formed UUID; any garbage must not wedge the card forever — fall through to fresh.
# A transcript over the rotation limit also falls through: the card keeps its identity and its 📌 note,
# and only the working memory turns over — which is the layer the state model says is disposable.
prep_session() {
  SID=$(board session --card "$CARD" 2>>"$INBOARD_LOGS/webhook.log"); SESS=(); NEWSID=""; SESSION_NOTICE=""
  if valid_uuid "$SID" && ! session_too_big "$SID" && ! session_stale "$SID"; then
    SESS=(--resume "$SID")
  else
    local why=""
    if valid_uuid "$SID" && session_too_big "$SID"; then why="its transcript outgrew agent.session_rotate_mb"
    elif valid_uuid "$SID" && session_stale "$SID"; then why="it sat idle past agent.session_max_idle_days"
    fi
    if [ -n "$why" ]; then
      echo "[$(date)] rotating card $CARD session $SID ($why; transcript kept)" >>"$INBOARD_LOGS/webhook.log"
      # The successor must know it IS one: with no notice it reads the card as a cold open and
      # re-derives (or contradicts) decisions its predecessor already logged there.
      SESSION_NOTICE="NOTE: you are a FRESH session taking over an EXISTING matter — the previous session for card $CARD was retired ($why). Nothing it knew carried over: the card (state note + log) is the only surviving memory. Read the card fully before acting."
    fi
    NEWSID=$(python3 -c 'import uuid;print(uuid.uuid4())'); SESS=(--session-id "$NEWSID")
  fi
}

# cap_goal_prompt — /goal hard-caps its condition at 4000 chars and the CLI exits 0 on that error (a SILENT
# no-op run). Never send an oversized goal: degrade to a plain prompt (strip /goal) and WARN loudly instead.
cap_goal_prompt() {
  if [ "${#PROMPT}" -gt 3900 ]; then
    echo "[$(date)] WARN: prompt ${#PROMPT} chars > /goal 4000 cap → stripped /goal, running plain (card=${CARD:-?})" >> "$INBOARD_LOGS/webhook.log"
    PROMPT="${PROMPT#/goal }"
  fi
}

# run_with_selfheal — run the caller-defined runh() with the SESS flags; a --resume of a stale/foreign
# claude session fails ("No conversation found") → self-heal: retry ONCE with a fresh session id.
# Uses/sets caller vars: SESS, NEWSID, RC, CARD.
run_with_selfheal() {
  runh ${SESS[@]+"${SESS[@]}"}; RC=$?
  if [ -z "$NEWSID" ] && [ "$RC" != 0 ]; then
    NEWSID=$(python3 -c 'import uuid;print(uuid.uuid4())')
    echo "[$(date)] resume failed (rc=$RC) card ${CARD:-?} -> fresh session, retry once" >> "$INBOARD_LOGS/webhook.log"
    runh --session-id "$NEWSID"; RC=$?
  fi
}
