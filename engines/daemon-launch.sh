#!/usr/bin/env bash
# launchd must wait for an existing foreground supervisor instead of repeatedly
# starting a second one that exits with "another daemon is already running".
set -uo pipefail
export PATH="/etc/profiles/per-user/$(id -un)/bin:$HOME/.local/bin:$PATH"
while true; do
  supervisor=$(jq -r '.supervisorPid // empty' "$HOME/.claude/daemon.status.json" 2>/dev/null)
  [[ "$supervisor" =~ ^[0-9]+$ ]] || break
  kill -0 "$supervisor" 2>/dev/null || break
  case "$(ps -p "$supervisor" -o comm=)" in
    */claude|claude) sleep 30 ;;
    *) break ;;
  esac
done
# Read credentials after waiting: the operator may rotate them while this launcher waits.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
# Preserve the daemon environment used on this host: routing is provided by TUN.
unset HTTPS_PROXY HTTP_PROXY ALL_PROXY NO_PROXY
if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && ! claude auth status 2>/dev/null | grep -q '"loggedIn":[[:space:]]*true'; then
  echo "[$(date)] no usable Claude credential; refusing unauthenticated daemon" >&2
  exit 1
fi
exec claude daemon run
