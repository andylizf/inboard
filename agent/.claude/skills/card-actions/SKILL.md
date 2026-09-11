---
name: card-actions
description: Handle an operator Action chip or a legacy inbox cycle. Covers each chip's meaning, the approved-send path, and why the Status is already set before the card agent arrives. The dispatch engine runs the follow-up sweep itself; per-card agents handle only their assigned card.
---

## Resume from the board
The engine delivers scheduled checks to their card agents before mail triage. A per-card agent handles
only its assigned card; the legacy whole-inbox runner uses `board pending` to find operator actions.

For each assigned actioned card, act on the request, record the outcome, reply and reconcile mail/time
triggers before the final receipt. Use `board clear-action` for a completed operation or `board action-fail`
for failure or an unverified outcome, never both. Either receipt ends operation-scoped writes.
Pass the delivered `--operation` token on every card mutation; a superseded operation must stop.
Legacy actions without a delivered token retain `board clear-action` as their receipt. For a legacy
send, stage the preview for approval with the current send button to obtain its snapshot and token.

**The Status is already set when you arrive.** The handler moves the card the moment the chip is tapped,
because a status that waits on you is a status that never changes when you hit your deadline or die.
Keep that initial state while handling the request, then set Status from who must act next.
A rewritten necessary draft awaits approval in needs_you; a verified send may leave an external wait,
more agent work or a completed matter. The handler leaves send status for you to determine.

- **▶️ Continue / redo** → re-read the relevant source thread and the card's context, then research or
  revise per the feedback. Stage the full proposed action in Draft using `board-cli`: Gmail uses
  `email ... gmail +draft`; other destinations use `board edit --draft`. A necessary draft awaiting
  approval belongs in `needs_you`, with `--needs` naming what the click will do.
- **Send-it-for-me (`cfg board.schema.send_action`)** → the tap approves the exact action, account,
  destination and content displayed in this card's Draft snapshot for this operation. The operator chose
  this GUI click as the send-gate approval for that preview; do not ask for an additional SEND token.
  This covers email, GitHub comments and other outward submissions, using the same card mechanism.
  Before sending, read the latest relevant thread and business state, including whether this action has
  already happened. Log the sources checked and what they mean for this draft's applicability.
  If it still applies, run `board approved-draft --card <CARD> --operation <TOKEN>` immediately before
  execution and use exactly the returned preview. Check that it specifies the action, account, destination
  and full content, and that the actual sending tool uses them. The command checks approval freshness;
  native platform tools do not enforce that check for you. Email still uses
  `email <account> gmail +send-approved --card <CARD> --draft-id <ID> --operation <TOKEN>`;
  other actions use the available native tool, such as `gh` or the browser. Do not route a GitHub comment
  through a Gmail draft unless email is the approved route. Approval to post a comment does not also
  authorize closing a PR, even if the comment says it will be closed.
  If facts require changing the action, account, destination or content, stage a complete new preview,
  explain the change and set `needs_you` for a new click; never revise and reuse the old approval.
  If the action is no longer needed, do not send: explain why and update the matter's status.
  If current facts cannot be checked, report the unavailable check and fail this operation without sending.
  Log the intended submission before invoking the native tool, then verify the result at the destination
  and record its link or receipt on the card. Only the assigned card agent executes this operation;
  do not delegate its send to another worker.
  A timeout or error does not prove nothing happened: inspect the destination before any retry, including
  after a new click, and do not resend while the outcome remains unknown. Report confirmed failure and
  unknown outcome distinctly via `board reply` and `board action-fail`.
  Once verified sent, clear the consumed Draft, then use `board awaiting` for an external wait,
  `needs_you` for a concrete remaining operator action, and `board done` only when no work remains.
  When a daily log is configured, log what went out and to whom under `cfg board.schema.daily_types.sent`.
- **✅ Done** → the operator confirmed completion: log the outcome, then `board done --card <CARD>`.
- **✖ Cancel** → the operator dropped the matter: `board edit --card <CARD> --status cancelled --needs ''`.

Action labels are deployment-specific. Use `cfg board.schema.action_status` to distinguish completion
from cancellation; the send action has its separate guarded path above. An unknown chip is a
misconfiguration: report it on the card rather than inventing a meaning. Reconcile mail and time
subscriptions using `board-cli` before the final receipt so obsolete reminders do not survive the change.
