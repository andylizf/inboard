#!/usr/bin/env bash
# Deploy a reviewed revision while holding the pull loop's existing lock.
set -euo pipefail
REVISION="$1"
RUNTIME="$2"
BACKUP="$3"
cd "$RUNTIME"
source engines/_common.sh
LOCK="$INBOARD_STATE/.lock"
deadline=$((SECONDS + 900))
until mkdir "$LOCK" 2>/dev/null; do
  [ "$SECONDS" -lt "$deadline" ] || { echo "$(date -u) deployment failed: pull loop lock remained busy"; exit 1; }
  sleep 10
done
trap 'rmdir "$LOCK"' EXIT
echo "$(date -u) deployment start revision=$REVISION"
git diff --quiet
git diff --cached --quiet
git fetch origin
git rev-parse --verify "$REVISION^{commit}" >/dev/null
git merge --ff-only "$REVISION"
uv sync --locked
python3 setup/migrate_waiting.py --backup-dir "$BACKUP" --apply --remove-legacy
echo "$(date -u) deployment migrated; running scheduled wake sweep"
python3 engines/wake-sweep.py
echo "$(date -u) deployment done revision=$(git rev-parse HEAD)"
