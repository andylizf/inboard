#!/usr/bin/env bash
# Apply the reviewed revision without restarting agents; settings reload in existing sessions.
set -euo pipefail
RUNTIME="${2:-$HOME/Projects/inboard}"
REVISION="$1"
cd "$RUNTIME"
mkdir -p logs
exec > >(tee -a logs/deploy-hooks.log) 2>&1
echo "$(date -u) deployment start revision=$REVISION"
git diff --quiet
git diff --cached --quiet
echo "$(date -u) rollback revision=$(git rev-parse HEAD)"
git fetch origin
git merge --ff-only "$REVISION"
source engines/_common.sh
python3 lib/card_hooks.py --bind-live
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/hook_runtime_smoke.py run
echo "$(date -u) deployment verified revision=$(git rev-parse HEAD)"
