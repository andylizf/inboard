---
name: card-actions
description: Handle an operator Action chip or a legacy inbox cycle. Covers each chip's meaning, the approved-send path, and why the Status is already set before the card agent arrives. The dispatch engine runs the follow-up sweep itself; per-card agents handle only their assigned card.
---

## Resume from the board
The engine delivers scheduled checks to their card agents before mail triage. A per-card agent handles
only its assigned card; the legacy whole-inbox runner uses `board pending` to find operator actions.

For each assigned actioned card, act on the operator's request, then `board clear-action` —
**except where the branch below says not to**, which is any failure that left his approval unspent: clearing
it there throws away the tap he made and the retry it was holding open.

**The Status is already set when you arrive.** The handler moves the card the moment the chip is tapped,
because a status that waits on you is a status that never changes when you hit your deadline or die.
So do not re-derive it, and do not set it back — what is left to you is the work and the record: the
research, the draft, the daily-log line, the reply on the card. Move the Status yourself only when the
work changes where the card genuinely belongs (Continue/redo lands back in Needs you once the draft is
rewritten), or for the send action, which the handler deliberately leaves alone.

- **▶️ Continue / redo** → dispatch a subagent with the card's full context (subject, prior draft, open
  question) + re-read the original email by `--message-id <msgid>`; research more / redo per the implied
  feedback; rewrite the draft (`email <id> gmail +draft --card <CARD> --reply-to-message <msgid> --body '...'`);
  `board upsert` the card with the new draft + status `⏸ Needs you` and a `--needs` saying the draft awaits his
  send or redo.
- **Send-it-for-me (`cfg board.schema.send_action`)** → the operator approved THIS card's draft by tapping
  the chip; that tap is his per-item approval and the only thing that unlocks sending. Send it with
  `email <account> gmail +send-approved --card <CARD> --draft-id <GMAIL_DRAFT_ID>` — the sole path by which
  mail can leave. **Do not touch the draft first.** What he approved is the text that was on the card when he
  tapped, so rewriting it — even to improve it — sends something he never read; the guard checks the outgoing
  body against what the card actually shows and will refuse. If it does refuse for that reason, post the FULL
  reply onto the card (`board log`, several calls if long), set the card to `⏸ Needs you` saying why, and let
  him tap again — never work around the check. After a successful send, check all remaining obligations and results: use `board awaiting` for an external
  wait, `needs_you` for an operator commitment, and `board done` only when the matter has no remaining work; then log it to the daily log under the sent type from
  `cfg board.schema.daily_types.sent`, one line saying what went out and to whom.
  **If the send fails for any other reason** — the draft is gone, Gmail refused, the network — nothing
  left and nothing has changed: the Action stays set, so his approval is not spent and one more tap
  retries it. Say so on the card in plain words (`board reply`: what you tried, what came back, that
  the mail did NOT go out, and that tapping again retries), leave the Status alone, and do NOT clear the
  Action. Never re-send by another route to work around it.
- **✅ Done** → the operator confirmed completion: log the outcome, then `board done --card <CARD>`.
- **✖ Cancel** → the operator dropped the matter: `board edit --card <CARD> --status cancelled --needs ''`.

Action labels are deployment-specific. Use `cfg board.schema.action_status` to distinguish completion
from cancellation; the send action has its separate guarded path above. An unknown chip is a
misconfiguration: report it on the card rather than inventing a meaning. After handling any action,
reconcile mail and time subscriptions using `board-cli` so obsolete reminders do not survive the change.
