#!/usr/bin/env bash
# Run hooks with the same credentials and Python environment as the board engines.
set -euo pipefail
umask 077
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
exec python3 "$INBOARD_HOME/lib/card_hooks.py"
