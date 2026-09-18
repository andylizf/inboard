#!/usr/bin/env bash
# Run consolidate.py's own frontmatter/conflict validation over every memory file, so a
# file that would abort tonight's dream is found now instead of one per night. The dream
# rolls the WHOLE pass back on the first bad file (no commit, no transcript consumption),
# so one unparseable file costs a full night -- which is how 2026-09-09..11 and
# 2026-09-17 each burned days.
#
# Read-only: it reports, it never edits.
set -euo pipefail
exec python3 /Users/andyl/Projects/inboard/agent/scripts/scan_omem_frontmatter.py "$@"
