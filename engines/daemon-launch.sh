#!/usr/bin/env bash
# Stand down when a foreground supervisor already owns the daemon, instead of starting a
# second one that would exit with "another daemon is already running".
#
# Standing down means exiting, not waiting. KeepAlive plus ThrottleInterval brings this back
# within seconds, so takeover after a supervisor dies is just as prompt — while waiting inside
# the launcher held a process that outlived the throttle window, so launchd killed it and
# respawned it every few seconds. That churn is not free: everything below this point ran
# again each time, including a credential preflight that calls out to the network.
set -uo pipefail
export PATH="/etc/profiles/per-user/$(id -un)/bin:$HOME/.local/bin:$PATH"
supervisor=$(jq -r '.supervisorPid // empty' "$HOME/.claude/daemon.status.json" 2>/dev/null)
if [[ "$supervisor" =~ ^[0-9]+$ ]] && kill -0 "$supervisor" 2>/dev/null; then
  case "$(ps -p "$supervisor" -o comm=)" in
    */claude|claude) exit 0 ;;
  esac
fi
# Read credentials here rather than at the top: the operator may rotate them between the
# launcher standing down and the run that actually starts the daemon.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
# Preserve the daemon environment used on this host: routing is provided by TUN.
unset HTTPS_PROXY HTTP_PROXY ALL_PROXY NO_PROXY
if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && ! claude auth status 2>/dev/null | grep -q '"loggedIn":[[:space:]]*true'; then
  echo "[$(date)] no usable Claude credential; refusing unauthenticated daemon" >&2
  exit 1
fi
# Every card session runs inside this one daemon on one account, so the account is chosen here,
# through the switchboard, and written down: a session that gets refused reports it against this
# name (lib/card_hooks.py), and the wake sweep restarts this launcher once another account is the
# pick. The static token in .env outranks every keychain account, so it is hidden from the pick.
STATE_DIR="${INBOARD_STATE:-${INBOARD_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}/state}"; mkdir -p "$STATE_DIR"
if command -v claude-switchboard >/dev/null 2>&1; then
  account=$( (unset CLAUDE_CODE_OAUTH_TOKEN; claude-switchboard pick) 2>/dev/null) || account=""
  if [ -n "$account" ]; then
    printf '%s\n' "$account" >"$STATE_DIR/daemon-account"
    echo "[$(date)] daemon starting on $account" >&2
    unset CLAUDE_CODE_OAUTH_TOKEN
    exec claude-switchboard run -- claude daemon run
  fi
  echo "[$(date)] switchboard has no usable account → static token" >&2
fi
printf 'static-token\n' >"$STATE_DIR/daemon-account"
exec claude daemon run
