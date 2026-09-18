set -euo pipefail
# Runs only from the card's 帮我执行 button: the driver re-checks the approval
# snapshot with `board approved-draft` and refuses to submit without it.
export INBOARD_BROWSER_LANE=cos597c
exec /usr/bin/env python3 /Users/andyl/Projects/inboard/agent/scripts/card-3d12a1a7/enroll_cos597c.py
