#!/usr/bin/env bash
# Seed the self-hosted runner's omem-transcripts checkout from the copy already on
# this machine, so the consolidate workflow's incremental-fetch path has something to
# fetch into. The cold `git clone` from GitHub cannot finish any more: the tip is
# ~3.3GB and the three attempts on 2026-09-17 died on `curl 56` twice and SIGKILL once
# (run 35229560398). Seeding locally skips the proxy and the 3.3GB index-pack.
#
# Safe to rerun: it builds into a temp directory and only swaps it into place once the
# result has a valid HEAD, so a failure leaves any existing cache untouched.
set -euo pipefail

SOURCE=/Users/andyl/omem-transcripts
RUNNER_REPO=/Users/andyl/actions-runner-omem/_work/omem-data/omem-data
TARGET="$RUNNER_REPO/transcripts"
STAGING="$RUNNER_REPO/.transcripts-seed-$$"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

[ -d "$SOURCE/.git" ] || { log "FATAL: no git repo at $SOURCE"; exit 1; }
[ -d "$RUNNER_REPO" ] || { log "FATAL: no runner checkout at $RUNNER_REPO"; exit 1; }

log "source HEAD: $(git -C "$SOURCE" log -1 --format='%H %ci')"
log "disk before: $(df -h /Users/andyl | tail -1)"

rm -rf "$STAGING"
# APFS copy-on-write: the bytes are shared until one side writes, so this costs
# almost no disk and no network, where a shallow clone would re-pack 3.3GB in RAM.
log "cloning working copy with APFS copy-on-write -> $STAGING"
cp -Rc "$SOURCE" "$STAGING"

# The workflow rewrites the remote with a fresh token every run, so the URL left here
# does not matter; point it at the plain https remote rather than leaving the
# source clone's credentials in place.
git -C "$STAGING" remote set-url origin https://github.com/andylizf/omem-transcripts.git
git -C "$STAGING" config user.name "omem-consolidate"
git -C "$STAGING" config user.email "omem@users.noreply.github.com"

if ! git -C "$STAGING" rev-parse -q --verify HEAD >/dev/null; then
  log "FATAL: staged copy has no valid HEAD; leaving existing cache alone"
  rm -rf "$STAGING"
  exit 1
fi

log "staged HEAD: $(git -C "$STAGING" log -1 --format='%H %ci')"
rm -rf "$TARGET"
mv "$STAGING" "$TARGET"
log "seeded $TARGET"
log "worktree files: $(git -C "$TARGET" ls-files | wc -l | tr -d ' ')"
log "disk after: $(df -h /Users/andyl | tail -1)"
