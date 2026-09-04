---
name: card-actions
description: What to do when the operator taps an Action chip on a card, plus the stale-awaiting follow-up sweep that opens every cycle. Load this at the START OF EVERY RUN, not only when an Action is waiting: it opens with the stale-awaiting sweep, which is the only thing that catches a matter that was sent and never answered, and a run that skips it leaves no trace of having done so. Also load it whenever you are handed an Action. Covers each chip's meaning, the send-approved path that is the only way mail leaves, and why the Status is already set before you arrive.
---

## Resume from the board — do this first, every run
**Follow-up sweep FIRST:** run `board stale-awaiting --days <cfg schedule.stale_awaiting_days>`. Every card
returned is one where the last move was ours and nothing has come back in that many days. Each row says
which `pass` it is:
- `pass: 1` — still awaiting, the reply never came. `board nudge --card <CARD> --days <days_waited>`: it
  moves the card to `⏸ Needs you` with a marked `NeedsYou` asking whether to chase, keeps the Subscription so the
  reply still routes here, and is what lets the sweep find the card again. If it is clearly worth chasing,
  also draft the follow-up (draft only — `+compose-draft --thread-id <T> --to <counterparty>`; on a thread
  the operator started, `+reply` would address the draft back to him).
- `pass: 2` — already nudged, and he has not acted for another stretch of days. `board nudge --card <CARD>
  --days <days_waited> --n <nudges_so_far + 1>` restates the ask as a repeat, and `board log` one line
  saying so. Do not close it for him: a matter he has not answered is still his.

Run `board pending`. For each actioned card, act on the operator's request, then `board clear-action` —
**except where the branch below says not to**, which is any failure that left his approval unspent: clearing
it there throws away the tap he made and the retry it was holding open.

**The Status is already set when you arrive.** The handler moves the card the moment the chip is tapped,
because a status that waits on you is a status that never changes when you hit your deadline or die.
So do not re-derive it, and do not set it back — what is left to you is the work and the record: the
research, the draft, the daily-log line, the reply on the card. Move the Status yourself only when the
work changes where the card genuinely belongs (Continue/redo lands on Draft ready when the draft is
written), or for the send action, which the handler deliberately leaves alone.

- **▶️ Continue / redo** → dispatch a subagent with the card's full context (subject, prior draft, open
  question) + re-read the original email by `--message-id <msgid>`; research more / redo per the implied
  feedback; rewrite the Gmail draft (`email <id> gmail +reply --message-id ID --body '...' --draft`);
  `board upsert` the card with the new draft + status `✍️ Draft ready`.
- **Send-it-for-me (`cfg board.schema.send_action`)** → the operator approved THIS card's draft by tapping
  the chip; that tap is his per-item approval and the only thing that unlocks sending. Send it with
  `email <account> gmail +send-approved --card <CARD> --draft-id <GMAIL_DRAFT_ID>` — the sole path by which
  mail can leave. **Do not touch the draft first.** What he approved is the text that was on the card when he
  tapped, so rewriting it — even to improve it — sends something he never read; the guard checks the outgoing
  body against what the card actually shows and will refuse. If it does refuse for that reason, post the FULL
  reply onto the card (`board log`, several calls if long), set the card to `⏸ Needs you` saying why, and let
  him tap again — never work around the check. After a successful send: `board awaiting` if a reply is
  expected, otherwise `board done`; then log it to the daily log under the sent type from
  `cfg board.schema.daily_types.sent`, one line saying what went out and to whom.
  **If the send fails for any other reason** — the draft is gone, Gmail refused, the network — nothing
  left and nothing has changed: the Action stays set, so his approval is not spent and one more tap
  retries it. Say so on the card in plain words (`board reply`: what you tried, what came back, that
  the mail did NOT go out, and that tapping again retries), leave the Status alone, and do NOT clear the
  Action. Never re-send by another route to work around it.
- **📤 Sent — awaiting reply** → `board awaiting --card <CARD> --desc '<the reply you await>'` (and, if a daily
  log is configured, `board daily --type '✅ Done' ...`). Keep the card open so the reply routes back here.
- **✅ Done / ignore** → (if a daily log is configured) `board daily --type '✅ Done' --subject '<one line: what was sent/ignored>' --account <label>`, then `board done --card <CARD>` (keep the card in Done, don't trash it).

The four names above are canonical, not literal. The board's Action chips are display strings the
deployment configures (`cfg board.schema.actions`) and may be in another language, so match the chip you
were handed to the branch it *means* — the Chinese board's `继续处理` is Continue/redo, `我已发送` is
Sent — awaiting reply. Several chips can land on one branch: a board offering both `忽略/归档` (drop it) and
`✅ 确认完成` (you finished it correctly) distinguishes those for the operator, while both close the card
through Done / ignore. A chip you cannot map to any branch is a misconfiguration — say so on the card and
clear the action rather than inventing a fifth behaviour.
