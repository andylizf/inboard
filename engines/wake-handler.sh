#!/usr/bin/env bash
# The sweep holds the shared card lock; this handler reuses normal session handover and delivery.
set -uo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
CARD="$1"
PROMPT="$(cat)"
cd "$INBOARD_HOME/agent" || exit 1
TS=$(date +%Y%m%d_%H%M%S)_$$
prep_session
PROMPT="$PROMPT
$SESSION_NOTICE
$MORTAL_TRAILER"
if [ "$(cfg agent.delivery inprocess)" = "daemon" ]; then
  deliver_to_daemon "$CARD" "$INBOARD_HOME/agent" "$PROMPT"
  RC=$?
  if [ "$RC" = 0 ] && valid_uuid "${DAEMON_SID:-}"; then
    board session --card "$CARD" --set "$DAEMON_SID" >>"$INBOARD_LOGS/wake-handler.log" 2>&1
  fi
else
  MAX_TURNS="$(cfg agent.interactive_max_turns 45)"
  runh() { claude -p "$PROMPT" "$@" --allowedTools "Bash,Read,Write,Task,WebSearch,WebFetch,ToolSearch,Skill" --max-turns "$MAX_TURNS" --output-format text >>"$INBOARD_LOGS/wake-$TS.log" 2>&1; }
  run_with_selfheal
  if [ "$RC" = 0 ] && [ -n "$NEWSID" ]; then board session --card "$CARD" --set "$NEWSID"; fi
fi
exit "$RC"
