#!/usr/bin/env bash
# Finishes what the 2026-09-18 run started. The Daytona account for al9080@princeton.edu now EXISTS
# (WorkOS code mail 17:24:58 UTC, welcome mail 17:27:38 UTC, dashboard reachable while still signed
# in on 2026-09-19), but the organization, the coupon redemption and the invitation never happened:
# the org switcher shows only the built-in "Personal" org and its wallet holds the $100 sign-up
# credit, not $10,000. This script does ONLY the remaining steps, and skips any step the live page
# shows as already done. Coupon DAYTONA_STARTUP_BT82RO0X, $10,000, expires 2026-10-12.
# Card: 3b62a1a7-7f3f-81a8-8279-fea37a8e407d. Runs only from that card's 📤 帮我发送 button.
#
# Never links a bank card, never pays, never mints an API key, never creates a second account, and
# never touches the existing andylizf@gmail.com Daytona account or the terminal-rl config.
set -euo pipefail

# No apostrophe inside "${VAR:?word}": bash still treats ' as a quote there, and a pair of them
# across two lines swallowed the next assignment whole in v1. (Found 2026-09-19.)
CARD="${INBOARD_CARD:?INBOARD_CARD not set — this script only runs from the card send button}"
OP="${INBOARD_OPERATION:?INBOARD_OPERATION not set — this script only runs from the card send button}"

cd /Users/andyl/Projects/inboard/agent

EMAIL='al9080@princeton.edu'
ORG='Terminal-Agent RL (Princeton University)'
COUPON='DAYTONA_STARTUP_BT82RO0X'
INVITE='andylizf@gmail.com'
PWFILE=/Users/andyl/Projects/inboard/agent/tmp/.daytona-signup-password
SHOTDIR=/Users/andyl/Projects/inboard/agent/tmp
mkdir -p "$SHOTDIR"

snap()  { browser snapshot -i 2>/dev/null | grep -v '"type":"lane-source"'; }
text()  { browser eval 'document.body.innerText' 2>/dev/null | grep -v '"type":"lane-source"'; }
shot()  { browser screenshot "$SHOTDIR/daytona-v2-$1.png" >/dev/null 2>&1 || true; echo "$SHOTDIR/daytona-v2-$1.png"; }
# `cmd | grep -q` is wrong under pipefail: grep exits at the first match, the producer takes SIGPIPE,
# and a check that DID find its text reports failure. Match on a captured string instead.
contains() { case "$2" in *"$1"*) return 0;; *) return 1;; esac; }
post()  { board image --card "$CARD" --file "$(shot "$1")" --caption "$2" >/dev/null 2>&1 || true; }

fail() {
  post "fail-$(date +%H%M%S)" "中止时的页面：$1"
  board action-fail --card "$CARD" --operation "$OP" --text "未完成：$1" >/dev/null 2>&1 || true
  echo "ABORT: $1" >&2
  exit 1
}

# v1 died on a bare `browser open` that timed out once while auth.daytona.io was slow, and `set -e`
# killed the script before its own fail() could report anything. Give navigation a second chance.
go() {
  browser open "$1" >/dev/null 2>&1 || { sleep 5; browser open "$1" >/dev/null 2>&1 || true; }
  sleep 4
}

echo '== 1/7 确认他批准的就是卡片上这一版提案 =='
board approved-draft --card "$CARD" --operation "$OP" >/dev/null
echo 'approval OK'

echo '== 2/7 打开后台，确认还是昨晚那个账号、且仍是登录状态 =='
go 'https://app.daytona.io/dashboard'
PAGE=$(text)
if contains 'Sign in' "$PAGE" || contains 'Sign up' "$PAGE" || contains 'Welcome back' "$PAGE"; then
  echo '   会话已过期，用卡片上那个密码重新登录'
  contains 'primary or work email' "$PAGE" \
    && fail 'Daytona 的闸又一次拒绝了 al9080@princeton.edu（页面原文 "Please use your primary or work email address!"）。按约定不重试，改写信给 Borna Perak。账号未改动。'
  [ -s "$PWFILE" ] || fail "会话过期需要重新登录，但密码文件 $PWFILE 不在了。卡片留言里有这个密码，写回该文件（chmod 600）后再点一次按钮。账号未改动。"
  browser find role textbox fill --name 'Email' "$EMAIL" >/dev/null 2>&1 || true
  browser find role button click --name 'Continue' >/dev/null 2>&1 || true
  sleep 4
  # Feed the password through the environment only — never argv, so it never shows up in `ps`.
  CRED="$(cat "$PWFILE")" bash -c 'browser find role textbox fill --name "Password" "$CRED"' >/dev/null
  browser find role button click --name 'Continue' >/dev/null
  sleep 8
  PAGE=$(text)
  contains 'primary or work email' "$PAGE" \
    && fail 'Daytona 在提交密码这一刻拒绝了 al9080@princeton.edu。按约定不重试，改写信给 Borna Perak。'
  # A fresh sign-in can ask for a one-time code by mail; take it from his Princeton inbox.
  if contains 'code' "$PAGE" && contains 'verif' "$(printf '%s' "$PAGE" | tr 'A-Z' 'a-z')"; then
    CODE=''
    for i in $(seq 1 10); do
      sleep 12
      MID=$(email work gmail +triage --query 'from:daytona.io OR from:workos newer_than:1d' --max 5 --format json 2>/dev/null \
            | python3 -c 'import sys,json; m=json.load(sys.stdin)["messages"]; print(m[0]["id"] if m else "")' 2>/dev/null || true)
      [ -n "$MID" ] || continue
      CODE=$(email work gmail +read --message-id "$MID" 2>/dev/null | grep -oE '\b[0-9]{6}\b' | head -1 || true)
      [ -n "$CODE" ] && break
    done
    [ -n "$CODE" ] || fail '登录要邮箱验证码，两分钟内没能在 Princeton 邮箱里取到。账号未改动。'
    browser find role textbox fill --name 'Code' "$CODE" >/dev/null 2>&1 \
      || browser find role textbox fill --name 'Verification code' "$CODE" >/dev/null
    browser find role button click --name 'Continue' >/dev/null
    sleep 6
  fi
  post signed-in '重新登录后的后台页'
fi
echo 'dashboard OK'

echo '== 3/7 点掉挡住整个后台的 Privacy Policy 弹窗 =='
# Daytona blocks every dashboard control behind "To continue using Daytona, please review and accept
# our Privacy Policy". Nothing below can be done without it, so accepting it is part of this proposal.
if contains 'accept our Privacy Policy' "$(text)"; then
  browser find role button click --name 'Accept and continue' >/dev/null \
    || fail '有 Privacy Policy 弹窗挡着，但没点到 "Accept and continue"。后台仍然用不了，没做任何改动。'
  sleep 3
  post privacy-accepted '接受 Privacy Policy 之后的后台'
fi
# The "Set Default Region" dialog sitting underneath is optional; close it rather than choose for him.
browser find role button click --name 'Cancel' >/dev/null 2>&1 || true
sleep 2

echo '== 4/7 建组织（已存在就跳过） =='
go 'https://app.daytona.io/dashboard'
if contains "$ORG" "$(text)$(snap)"; then
  echo "   组织 \"$ORG\" 已存在，跳过"
else
  # "Create Organization" lives inside the org switcher popover at the top left, which on 2026-09-19
  # listed exactly two entries: "Personal" and "Create Organization". Open it before looking.
  browser find role button click --name 'Personal' >/dev/null 2>&1 \
    || browser find role combobox click --name 'Personal' >/dev/null 2>&1 || true
  sleep 2
  browser find role button click --name 'Create Organization' >/dev/null 2>&1 \
    || browser find role link click --name 'Create Organization' >/dev/null 2>&1 \
    || browser find role menuitem click --name 'Create Organization' >/dev/null 2>&1 \
    || fail '没找到建组织的入口（组织切换器里应有 "Create Organization"）。组织尚未创建，优惠码未兑换，账号其他部分未改动。看截图后再决定下一步，不要重跑。'
  sleep 2
  browser find role textbox fill --name 'Name' "$ORG" >/dev/null
  browser find role button click --name 'Create' >/dev/null
  sleep 6
  contains "$ORG" "$(text)$(snap)" || fail "建组织后页面上读不到 \"$ORG\"。优惠码未兑换。看截图确认组织到底建没建成，不要直接重跑。"
  post org-created "组织 $ORG 已建成"
fi

echo '== 5/7 在这个组织的 Wallet 里兑换优惠码 =='
go 'https://app.daytona.io/dashboard/billing/wallet'
WALLET=$(text)
if contains '10,000' "$WALLET" || contains '10000' "$WALLET"; then
  echo '   钱包里已经有 $10,000，说明已兑换过，跳过'
  post wallet-already '兑换前就已查到钱包里有 $10,000'
else
  browser find role button click --name 'Redeem' >/dev/null 2>&1 \
    || browser find role link click --name 'Redeem coupon' >/dev/null 2>&1 \
    || { go 'https://app.daytona.io/dashboard/billing'
         browser find role button click --name 'Redeem' >/dev/null 2>&1 \
         || fail "组织已就绪，但 Wallet 和 Billing 页上都没找到兑换入口。优惠码 $COUPON 仍未兑换，也仍未作废。"; }
  sleep 2
  browser find role textbox fill --name 'Coupon' "$COUPON" >/dev/null 2>&1 \
    || browser find role textbox fill --name 'Enter coupon code' "$COUPON" >/dev/null 2>&1 \
    || browser find role textbox fill --name 'Code' "$COUPON" >/dev/null
  browser find role button click --name 'Redeem' >/dev/null
  sleep 8
  WALLET=$(text)
  contains '10,000' "$WALLET" || contains '10000' "$WALLET" \
    || fail "点了兑换，但钱包页上读不到 \$10,000 的余额。优惠码 $COUPON 的状态不明——先去 Wallet 页看一眼再决定，绝不要直接重兑。"
  post wallet-redeemed '兑换后的钱包余额'
fi

echo '== 6/7 邀请他常用的 gmail 当 Owner =='
go 'https://app.daytona.io/dashboard/members'
if contains "$INVITE" "$(text)"; then
  echo '   已经在成员名单里，跳过'
elif browser find role button click --name 'Invite' >/dev/null 2>&1; then
  sleep 2
  browser find role textbox fill --name 'Email' "$INVITE" >/dev/null 2>&1 || true
  browser find role combobox select --name 'Role' 'Owner' >/dev/null 2>&1 || true
  browser find role button click --name 'Send' >/dev/null 2>&1 \
    || browser find role button click --name 'Invite' >/dev/null 2>&1 || true
  sleep 4
  post members "邀请 $INVITE 之后的成员页"
else
  echo 'WARN: 没找到邀请入口；钱已到账，这一步留到下一轮。' >&2
  post members-noentry '成员页上没找到邀请入口'
fi

echo '== 7/7 记下兑换后的实际算力档位 =='
go 'https://app.daytona.io/dashboard/limits'
post limits '兑换后的实际算力档位（后台限额页）'
board log --card "$CARD" --text "09-19 执行结果：组织／兑换／邀请三步的实际状态见上面几张截图。限额页原文前 40 行：
$(text | head -40)" >/dev/null 2>&1 || true

echo 'DONE: 剩余步骤已执行，余额与档位截图已传到卡片。'
