#!/usr/bin/env bash
# cheese PR #1169: apply the claude-md-ok sign-off label (the operator's click IS the
# human sign-off the gate is after), wait for review-gate to turn green, then squash-merge.
set -euo pipefail

REPO=SageSeekerSociety/cheese
PR=1169
EXPECTED_SHA=b1bba7f98d78963e2eecb44ecddca174d6a51b96

echo "== 执行前核对 =="
STATE=$(gh pr view "$PR" --repo "$REPO" --json state,headRefOid,files,labels)
echo "$STATE"

python3 - "$EXPECTED_SHA" <<'PY'
import json, subprocess, sys
exp = sys.argv[1]
d = json.loads(subprocess.check_output(
    ["gh","pr","view","1169","--repo","SageSeekerSociety/cheese",
     "--json","state,headRefOid,files,labels"]))
if d["state"] != "OPEN":
    sys.exit(f"停止：PR 已不是 OPEN，当前 {d['state']}（可能已被合并或关闭）")
if d["headRefOid"] != exp:
    sys.exit(f"停止：PR 的最新提交变了（现在 {d['headRefOid']}，批准时是 {exp}），改动已不是你看过的那份")
paths = [f["path"] for f in d["files"]]
if paths != ["CLAUDE.md"]:
    sys.exit(f"停止：改动文件不再只有 CLAUDE.md，现在是 {paths}")
f = d["files"][0]
if (f["additions"], f["deletions"]) != (7, 0):
    sys.exit(f"停止：改动行数变了（+{f['additions']}/-{f['deletions']}，批准时是 +7/-0）")
print("核对通过：仍是那份 7 行改动")
PY

echo "== 打 claude-md-ok 标签 =="
gh pr edit "$PR" --repo "$REPO" --add-label claude-md-ok

echo "== 等 review-gate 转绿（最多 5 分钟） =="
for i in $(seq 1 30); do
  CONC=$(gh api "repos/$REPO/commits/$EXPECTED_SHA/check-runs" \
    --jq '[.check_runs[] | select(.name=="review-gate")] | sort_by(.started_at) | last | .conclusion' 2>/dev/null || echo null)
  echo "  第 $i 次：review-gate = $CONC"
  [ "$CONC" = "success" ] && break
  sleep 10
done
if [ "${CONC:-}" != "success" ]; then
  echo "停止：打完标签后 review-gate 仍未转绿（当前 $CONC），没有合并。标签已打上，可稍后复查。"
  exit 1
fi

echo "== 合并（squash，仓库只允许这一种） =="
gh pr merge "$PR" --repo "$REPO" --squash --delete-branch

echo "== 合并后核实 =="
gh pr view "$PR" --repo "$REPO" --json state,mergedAt,mergeCommit
