#!/usr/bin/env bash
# Archive-then-delete inboard per-run spool logs older than N days (default 30).
#
# Only the per-run families (cycle-* dispatch-* comment-<date>* action-* backfill-*):
# the long-lived logs (webhook.log, agent.log, due-sweep.log, comment-catchup.*) are
# never touched. Nothing is unrecoverable — each pruned batch is tarred into
# logs/archive/ first, and the delete only runs if the tar succeeded.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RETAIN="${1:-30}"

cd logs
OLD=$(find . -maxdepth 1 \( -name 'cycle-*' -o -name 'dispatch-*' -o -name 'comment-2*' \
      -o -name 'action-*' -o -name 'backfill-*' \) -type f -mtime +"$RETAIN" | sed 's|^\./||')
[ -n "$OLD" ] || exit 0

mkdir -p archive
STAMP=$(date +%Y%m%d_%H%M%S)
# shellcheck disable=SC2086 — spool names never contain spaces
tar czf "archive/prune-$STAMP.tar.gz" $OLD
rm -- $OLD
N=$(echo "$OLD" | wc -l | tr -d ' ')
echo "[$(date)] pruned $N run logs older than ${RETAIN}d → logs/archive/prune-$STAMP.tar.gz"
