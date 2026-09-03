#!/usr/bin/env bash
# Put a hand-dragged Status back.
#
# The board is a state machine whose transitions are the Action chips: each one implies exactly one
# status, and the handler applies it. Dragging a card in Notion bypasses that, and the bypass is
# silent — the engines learn nothing, so the daily log misses it, memory misses it, and until the
# clearing rule landed a card could reach a closed status still advertising for mail.
#
# Notion sends no webhook for a change made by this integration, so every properties_updated event
# here came from a person. `board` records each Status it writes; a mismatch against that record is
# therefore a hand edit, and the record is what to put back.
#
# It declines rather than guesses: no record, or a real Action set (the action path owns the status
# then), means leave it alone.
set -uo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

CARD="${1:-}"; [ -n "$CARD" ] || exit 0
LOG="$INBOARD_LOGS/webhook.log"
REC="$INBOARD_STATE/status/$CARD"
[ -f "$REC" ] || exit 0                       # never seen this card write a status; nothing to restore

WANT=$(cat "$REC" 2>/dev/null)
[ -n "$WANT" ] || exit 0

NOW=$(board statusof --card "$CARD" 2>>"$LOG")
[ -n "$NOW" ] || exit 0
[ "$NOW" = "$WANT" ] && exit 0                # unchanged, or already put back

ACTION_PLACEHOLDER="$(cfg board.schema.action_placeholder '👉 Pick action')"
ACT=$(board actionof --card "$CARD" 2>>"$LOG")
if [ -n "$ACT" ] && [ "$ACT" != "$ACTION_PLACEHOLDER" ]; then
  echo "[$(date)] status-guard: card $CARD moved to '$NOW' with action '$ACT' set — the action path owns it" >>"$LOG"
  exit 0
fi

board edit --card "$CARD" --status "$WANT" >>"$LOG" 2>&1 || exit 0
echo "[$(date)] status-guard: card $CARD dragged '$WANT' -> '$NOW'; restored" >>"$LOG"
board reply --card "$CARD" --text "状态被手动改成「${NOW}」，已经改回「${WANT}」。看板的状态由动作决定，手动拖动这里的engine收不到、日志和记忆都不会更新，卡看着变了其实什么都没发生。用右上角的动作：继续处理＝重做，我已发送＝等回复，忽略/归档 或 ✅ 确认完成＝完成。真要一个动作到不了的状态，跟我说。" >>"$LOG" 2>&1 || true
