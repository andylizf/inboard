#!/usr/bin/env bash
# The board CLI checks event authors and serializes restoration with agent status writes.
set -uo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

CARD="${1:-}"; EVENT="${2:-}"
[ -n "$CARD" ] && [ -n "$EVENT" ] || exit 0
board guard-status --card "$CARD" --event "$EVENT" >>"$INBOARD_LOGS/webhook.log" 2>&1
