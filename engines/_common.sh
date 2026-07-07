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
