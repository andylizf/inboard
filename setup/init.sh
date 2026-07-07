#!/usr/bin/env bash
# `inboard init` — the setup wizard (macOS / launchd, v1).
# Idempotent-ish: safe to re-run. It (1) checks dependencies, (2) `uv sync`s the venv, (3) collects your
# identity + accounts + Notion token, (4) creates the Notion board, (5) writes config + .env, (6) installs
# the launchd pull loop, (7) smoke-tests. Nothing personal is baked into code — it all lands in config.
set -uo pipefail
INBOARD_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export INBOARD_HOME
cd "$INBOARD_HOME"

CONFIG="$INBOARD_HOME/inboard.config.yaml"
EXAMPLE="$INBOARD_HOME/inboard.config.example.yaml"
ENVFILE="$INBOARD_HOME/.env"
say() { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m⚠ %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
ask() { local p="$1" d="${2:-}" v; if [ -n "$d" ]; then read -r -p "$p [$d]: " v; echo "${v:-$d}"; else read -r -p "$p: " v; echo "$v"; fi; }

say "inboard init — checking dependencies"
command -v uv      >/dev/null || die "uv not found — install it: https://docs.astral.sh/uv/ (brew install uv)"
command -v claude  >/dev/null || die "Claude Code CLI (claude) not found — inboard's agent runtime. Install it first."
command -v gws     >/dev/null || warn "gws (google-workspace CLI) not on PATH — needed to read mail. Install + auth before first run."
command -v cred    >/dev/null || warn "cred broker not on PATH — the default secret backend (for logins). Optional but recommended."
[ -x "$HOME/.local/bin/agent-browser" ] || warn "agent-browser not found (~/.local/bin) — needed only for web-task cards."

say "Syncing Python venv (uv sync)"
uv sync || die "uv sync failed"

# --- collect identity + accounts (only if no config yet) ---
if [ -f "$CONFIG" ]; then
  say "Config already exists at $CONFIG — keeping identity/accounts, will refresh board ids."
else
  say "Let's set up your identity and mailboxes."
  NAME="$(ask 'Your name (how the agent signs drafts)' "$(id -F 2>/dev/null || echo '')")"
  TZ="$(ask 'Your timezone' "$(readlink /etc/localtime 2>/dev/null | sed 's#.*/zoneinfo/##' || echo 'America/New_York')")"
  NACC="$(ask 'How many mail accounts to watch?' '1')"
  ACCOUNTS="[]"
  for i in $(seq 1 "$NACC"); do
    echo "  — account $i —"
    AID="$(ask '  id (short key, e.g. personal)' "acct$i")"
    ALABEL="$(ask '  label (shown on the board)' "Account $i")"
    AADDR="$(ask '  email address' '')"
    ACAL="$(ask '  has Google Calendar access? (true/false)' 'false')"
    ACFG=""; AKR=""
    if [ "$i" -gt 1 ]; then
      ACFG="$(ask '  isolated gws config dir (blank = default)' "$HOME/.config/gws-$AID")"
      AKR="$(ask '  gws keyring backend (blank = default; file for a 2nd account)' 'file')"
    fi
    ACCOUNTS="$(python3 -c "import json,sys; a=json.loads(sys.argv[1]); a.append({'id':sys.argv[2],'label':sys.argv[3],'provider':'gmail','address':sys.argv[4],'calendar':sys.argv[5].lower()=='true','gws_config_dir':sys.argv[6],'gws_keyring_backend':sys.argv[7]}); print(json.dumps(a))" "$ACCOUNTS" "$AID" "$ALABEL" "$AADDR" "$ACAL" "$ACFG" "$AKR")"
  done
  python3 "$INBOARD_HOME/setup/apply_config.py" --base "$EXAMPLE" --out "$CONFIG" \
    --set "identity.name=$NAME" --set "identity.timezone=$TZ" --accounts "$ACCOUNTS" \
    || die "failed to write config"
fi

# --- Notion token → .env ---
if [ ! -f "$ENVFILE" ] || ! grep -q '^NOTION_TOKEN=' "$ENVFILE" 2>/dev/null; then
  say "Notion integration token (create one at https://www.notion.so/my-integrations, share your target page with it)."
  TOK="$(ask 'NOTION_TOKEN (secret_...)' '')"
  [ -n "$TOK" ] || die "a Notion token is required"
  touch "$ENVFILE"; chmod 600 "$ENVFILE"
  grep -q '^NOTION_TOKEN=' "$ENVFILE" 2>/dev/null \
    && python3 - "$ENVFILE" "$TOK" <<'PY'
import re,sys
p,tok=sys.argv[1],sys.argv[2]
s=open(p).read(); s=re.sub(r'^NOTION_TOKEN=.*$', 'NOTION_TOKEN='+tok, s, flags=re.M)
open(p,'w').write(s)
PY
  grep -q '^NOTION_TOKEN=' "$ENVFILE" 2>/dev/null || printf 'NOTION_TOKEN=%s\n' "$TOK" >> "$ENVFILE"
fi
set -a; . "$ENVFILE"; set +a
export PATH="$INBOARD_HOME/.venv/bin:$PATH"

# --- create the board ---
say "Creating the Notion board (share your target page with the integration first if you haven't)."
PARENT="$(ask 'Parent page title or id (blank = the only page you shared)' '')"
DAILY_FLAG=""
[ "$(ask 'Also create a daily-log DB for FYI/unsubscribe records? (true/false)' 'true')" = "true" ] && DAILY_FLAG="--with-daily"
PARG=(); [ -n "$PARENT" ] && PARG=(--parent-page "$PARENT")
RESULT="$(python3 "$INBOARD_HOME/setup/create_board.py" "${PARG[@]}" $DAILY_FLAG)" || die "board creation failed"
echo "$RESULT"
DBID="$(echo "$RESULT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["database_id"])')"
DAILYID="$(echo "$RESULT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("daily_log_database_id") or "")')"
BOTID="$(echo "$RESULT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("bot_user_id") or "")')"

python3 "$INBOARD_HOME/setup/apply_config.py" --base "$CONFIG" --out "$CONFIG" \
  --set "board.database_id=$DBID" --set "board.daily_log_database_id=$DAILYID" --set "board.bot_user_id=$BOTID" \
  || die "failed to write board ids"

# --- install the launchd pull loop ---
say "Installing the launchd pull loop"
PLIST_DST="$HOME/Library/LaunchAgents/local.inboard-agent.plist"
INTERVAL="$(python3 "$INBOARD_HOME/bin/cfg" schedule.pull_interval_seconds 300)"
sed -e "s#__INBOARD_HOME__#$INBOARD_HOME#g" -e "s#__PULL_INTERVAL__#$INTERVAL#g" \
  "$INBOARD_HOME/setup/local.inboard-agent.plist.template" > "$PLIST_DST"
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST" && say "launchd job loaded (fires every ${INTERVAL}s)." || warn "launchctl load failed — load $PLIST_DST manually."

# --- smoke test ---
say "Smoke test: board whoami + accounts"
"$INBOARD_HOME/bin/board" whoami && "$INBOARD_HOME/bin/board" accounts || warn "smoke test failed — check .env token + config."

say "Done. Next: the webhook engine (engines/webhook-server.py) for instant comment/action reactions —"
say "run it behind a tunnel and register the URL in your Notion integration. See README.md."
