#!/usr/bin/env bash
# Arena 助学金：把卡片上那条已审阅的私信发给 Melissa Pan。
# 平台 Slack，工作区「AI Lab @ Princeton」，私信 D0BV7M6PWFQ，接在他 9/5 那条对话后面。
# Slack 凭据只存在他的笔记本上，本机经 ssh 触发那边已登录的 slack，凭据不落到 mac-mini。
#
# 这个脚本不是「帮我执行」按钮会去跑的东西 —— 2026-09-18 的提交 a7d4cbf 之后，点按钮是把本卡
# 的 agent 叫醒并交给它做，批准的是那一刻 Draft 里的全文。这里留着的是那件事的既定做法：
# 执行时核对与发送命令都已实测过（不带 --yes 的 dry-run 验过引号与换行）。被叫醒后由 agent
# 自己带上收到的 operation token 运行它：INBOARD_OPERATION=<token> bash 本脚本。
set -euo pipefail

CARD=3c72a1a7-7f3f-8170-851d-da4cc01aebfd
WS=ailab-princeton
DM=D0BV7M6PWFQ
LAPTOP=andys-macbook-pro-1
RPATH='PATH=/etc/profiles/per-user/andyl/bin:$HOME/.local/bin:$PATH'
MSG=/Users/andyl/Projects/inboard/agent/scripts/card-3c72a1a7/melissa-dm-20260917.txt
# 批准时这条对话的最后一条消息（Melissa 2026-09-06 00:04:28 EDT）
LAST_TS=1788667468.380649

echo "== 1/4 核对这次执行确实来自你在卡片上的点击 =="
board approved-draft --card "$CARD" \
  --operation "${INBOARD_OPERATION:?停止：没有执行令牌。这个脚本只能由卡片上的「帮我执行」按钮启动}" >/dev/null
echo "通过：卡片上的预览与本脚本仍然绑在一起"

echo "== 2/4 核对这条私信还没发出去、Melissa 也还没回话 =="
CONV=$(ssh -o ConnectTimeout=20 "$LAPTOP" "$RPATH slack read $WS $DM -n 20 --json")
printf '%s' "$CONV" | python3 -c '
import json, sys
last = 1788667468.380649
msgs = json.load(sys.stdin)
newer = [m for m in msgs if float(m["ts"]) > last]
if newer:
    print("停止：这条对话在你批准之后有了新消息，情况已经变了，没有发送。新消息：")
    for m in newer:
        print("  [%s] %s: %s" % (m["time"], m["user"], m["text"][:200]))
    print("如果是这条私信已经发出去过，就不要重发；如果是 Melissa 回话了，先看她说了什么再决定。")
    sys.exit(1)
print("通过：对话仍停在 Melissa 9/6 那两句，私信没有重复发送的风险")
'

echo "== 3/4 发送 =="
TEXT=$(cat "$MSG")
ssh -o ConnectTimeout=20 "$LAPTOP" "$RPATH slack send $WS $DM \"\$(cat -)\" --literal --yes" <<< "$TEXT"

echo "== 4/4 回读对话，确认真的发出去了 =="
ssh -o ConnectTimeout=20 "$LAPTOP" "$RPATH slack read $WS $DM -n 3"
