#!/usr/bin/env bash
# Card 3dd2a1a7-7f3f-814c-a14a-e2786d80fda5
# 推一个提交到 SageSeekerSociety/cheese 的分支
# feat/the-pool-says-which-machine-is-missing（PR #1083）。
# 只做这一件事：不评论、不审查、不合并、不碰 main。
set -euo pipefail

REPO="SageSeekerSociety/cheese"
BRANCH="feat/the-pool-says-which-machine-is-missing"
PREVIEW_HEAD="012a32e995acdaacdf572dffbd662b49a5b7d748"
PATCH="/Users/andyl/Projects/inboard/agent/scripts/card-3dd2a1a7/fix.patch"
WORK="/Users/andyl/Projects/inboard/agent/scripts/card-3dd2a1a7/work"

echo "== 1. 执行时复核：PR 还开着吗，分支头还是不是准备预览时的那一个 =="
state="$(gh pr view 1083 --repo "$REPO" --json state --jq '.state')"
echo "PR #1083 状态：$state"
if [ "$state" != "OPEN" ]; then
  echo "中止：PR #1083 已经不是打开状态，改动不该再推。"
  exit 1
fi

actual="$(gh api "repos/$REPO/git/ref/heads/$BRANCH" --jq '.object.sha')"
echo "远端 $BRANCH 现在指向 $actual"
if [ "$actual" != "$PREVIEW_HEAD" ]; then
  echo "注意：这条分支在准备这次操作之后又被推过（预览时是 $PREVIEW_HEAD）。"
  echo "不直接中止，改由下面三道闸门判断这个改动还成不成立："
  echo "补丁要能原样打上、打完 actionlint 要干净、改动只许落在那两个文件上。"
fi

echo "== 2. 取一份干净的分支副本 =="
rm -rf "$WORK"
git clone --quiet --branch "$BRANCH" --depth 1 \
  "https://github.com/$REPO.git" "$WORK"
cd "$WORK"
git config user.name "Zhifei Li"
git config user.email "andylizf@outlook.com"

echo "== 3. 闸门一：补丁必须原样打上（对不上就说明分支内容变了，不盲推）=="
git apply --verbose "$PATCH"
git --no-pager diff --stat

echo "== 4. 闸门二：改动只许落在这两个文件上 =="
changed="$(git --no-pager diff --name-only | sort | tr '\n' ' ')"
echo "实际改到：$changed"
expected=".github/scripts/ci-pool-health.py .github/workflows/box-uptime.yml "
if [ "$changed" != "$expected" ]; then
  echo "中止：改动范围和预览不一致（预览是 $expected）。"
  exit 1
fi

echo "== 5. 闸门三：推之前自己先验一遍 =="
if command -v actionlint >/dev/null 2>&1; then
  actionlint .github/workflows/box-uptime.yml
  echo "actionlint：box-uptime.yml 干净"
else
  echo "中止：本机没有 actionlint，这次改的就是工作流语法，不能不验就推。"
  exit 1
fi
python3 -m unittest discover -s .github/scripts -p 'test_*.py'

echo "== 6. 提交并推送 =="
git commit --quiet --all --file - <<'MSG'
fix(ci): drop the permission scope that voids box-uptime.yml

`administration` is not a workflow permission scope. GitHub does not ignore
the unknown key, it refuses to parse the file. That is why every push on this
branch produced a box-uptime run with zero jobs and no log while the PR's own
checks stayed green, and why merging as it stands would have stopped the hourly
heartbeat check that lives in this same file, without a red mark anywhere.

Removing the line does not buy the runner list back. That endpoint requires
admin access to the repository, which the workflow token cannot be granted.
box-heartbeat.yml already records the same finding about the check this one
replaces. So `ci-pool` gets a 403 until it is handed a token that has that
access, and the 403 branch now exits red instead of returning 0: a check that
cannot see the pool must not report the pool healthy.
MSG

git push origin "HEAD:$BRANCH"
new_sha="$(git rev-parse HEAD)"
echo "已推送：https://github.com/$REPO/commit/$new_sha"

echo "== 7. 等 GitHub 解析这次推送，看工作流是不是真的活了 =="
sleep 45
gh run list --repo "$REPO" --workflow box-uptime.yml --branch "$BRANCH" \
  --limit 3 --json status,conclusion,createdAt,url \
  --template '{{range .}}{{.createdAt}}  {{.status}}  {{.conclusion}}  {{.url}}{{"\n"}}{{end}}'
echo
echo "看这一行：这次推送对应的运行如果列出了 job（不再是 0 秒 0 job），文件就恢复有效了。"
echo "其中 ci-pool 那一项预计会红，报 HTTP 403，那是对的：它现在确实读不到机器名单。"
