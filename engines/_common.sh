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

# prep_session — resume the card's per-card claude session, or mint a fresh id.
# Reads CARD; sets SID, SESS (claude session flags), NEWSID (non-empty only when starting fresh).
# Resume ONLY a well-formed UUID; any garbage must not wedge the card forever — fall through to fresh.
prep_session() {
  SID=$(board session --card "$CARD" 2>>"$INBOARD_LOGS/webhook.log"); SESS=(); NEWSID=""
  if valid_uuid "$SID"; then SESS=(--resume "$SID")
  else NEWSID=$(python3 -c 'import uuid;print(uuid.uuid4())'); SESS=(--session-id "$NEWSID"); fi
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
