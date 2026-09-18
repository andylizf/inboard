#!/usr/bin/env bash
# Card 3dd2a1a7-7f3f-814c-a14a-e2786d80fda5
# 给 SageSeekerSociety/cheese 的 main 开一个修复 PR：
# 删掉让 box-uptime.yml 整份作废的那行非法权限，并把「读不到就报红」和
# 「读不到就别喊人」这两处一并改掉。
# 只做这一件事：开分支、推分支、开 PR。不合并、不评论、不碰别的分支。
set -euo pipefail

REPO="SageSeekerSociety/cheese"
FIXBRANCH="fix/box-uptime-invalid-permission-scope"
PATCH="/Users/andyl/Projects/inboard/agent/scripts/card-3dd2a1a7/fix.patch"
BODY="/Users/andyl/Projects/inboard/agent/scripts/card-3dd2a1a7/pr-body.md"
WORK="/Users/andyl/Projects/inboard/agent/scripts/card-3dd2a1a7/work-main"

echo "== 1. 执行时复核：main 上那行还在吗 =="
if gh api "repos/$REPO/contents/.github/workflows/box-uptime.yml?ref=main" --jq '.content' \
    | base64 -d | grep -q '^  administration: read$'; then
  echo "main 的 box-uptime.yml 里仍有 administration: read，需要修。"
else
  echo "中止：main 上已经没有这一行，说明有人先修了。不重复推。"
  exit 1
fi

echo "== 2. 同名分支不能已经存在 =="
if gh api "repos/$REPO/git/ref/heads/$FIXBRANCH" >/dev/null 2>&1; then
  echo "中止：远端已有分支 $FIXBRANCH，可能是这个脚本已经跑过一次。"
  echo "先看那条分支和它的 PR，别再推一遍。"
  exit 1
fi

echo "== 3. 取一份干净的 main =="
rm -rf "$WORK"
git clone --quiet --branch main --depth 1 "https://github.com/$REPO.git" "$WORK"
cd "$WORK"
git config user.name "Zhifei Li"
git config user.email "andylizf@outlook.com"
git checkout --quiet -b "$FIXBRANCH"
echo "从 main 的 $(git rev-parse --short HEAD) 开出 $FIXBRANCH"

echo "== 4. 闸门一：补丁必须原样打上 =="
git apply --verbose "$PATCH"
git --no-pager diff --stat

echo "== 5. 闸门二：改动只许落在这两个文件上 =="
changed="$(git --no-pager diff --name-only | sort | tr '\n' ' ')"
echo "实际改到：$changed"
expected=".github/scripts/ci-pool-health.py .github/workflows/box-uptime.yml "
if [ "$changed" != "$expected" ]; then
  echo "中止：改动范围和预览不一致（预览是 $expected）。"
  exit 1
fi

echo "== 6. 闸门三：推之前自己先验一遍 =="
if command -v actionlint >/dev/null 2>&1; then
  actionlint .github/workflows/box-uptime.yml
  echo "actionlint：box-uptime.yml 干净"
else
  echo "中止：本机没有 actionlint，这次改的就是工作流语法，不能不验就推。"
  exit 1
fi
python3 -m unittest discover -s .github/scripts -p 'test_*.py'

echo "== 7. 提交并推分支 =="
git commit --quiet --all --file - <<'MSG'
fix(ci): box-uptime.yml is a file GitHub can parse again

`administration` is not a workflow permission scope. GitHub does not ignore
the unknown key, it refuses to parse the file. Since #1083 landed, every push
to main has produced a box-uptime run with zero jobs and no log, and nothing
in this file has run on its schedule: the heartbeat-age check and the
dev-health probe live here too.

Deleting the line does not buy the runner list back. That endpoint requires
admin access to the repository, which the workflow token cannot be granted,
and box-heartbeat.yml already records the same finding about the check
ci-pool replaces. So ci-pool gets a 403 until it is handed a token that has
that access, and the 403 branch exits red instead of returning 0: a check
that cannot see the pool must not report the pool healthy.

The Feishu step is gated on the check having named a machine. A run that
could not read the pool has nothing to tell the team, and "CI 机器掉了" twice
an hour on a 403 is how an alert channel becomes one people ignore.
MSG

git push --quiet origin "$FIXBRANCH"
echo "分支已推：$FIXBRANCH"

echo "== 8. 开 PR（不合并）=="
url="$(gh pr create --repo "$REPO" --base main --head "$FIXBRANCH" \
  --title 'fix(ci): box-uptime.yml is a file GitHub can parse again' \
  --body-file "$BODY")"
echo "PR 已开：$url"

echo "== 9. 把这个 PR 的检查状态列一下 =="
sleep 20
gh pr checks "$url" --repo "$REPO" 2>&1 | head -20 || true
echo
echo "接下来：这个 PR 和你平时那些一样，检查过了你自己合。"
echo "合进 main 之后，box-uptime.yml 恢复有效，每小时的巡检和站点探活会重新开始跑。"
echo "其中 ci-pool 那一项会红，报 HTTP 403，那是实话：它现在确实读不到机器名单。"
echo "它不会再往飞书发告警，除非它真的点出了是哪一台机器掉了。"
