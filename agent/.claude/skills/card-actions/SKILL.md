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
send, prepare the current preview and script for the 帮我执行 button.

**The Status is already set when you arrive.** The handler moves the card the moment the chip is tapped,
because a status that waits on you is a status that never changes when you hit your deadline or die.
Keep that initial state while handling the request, then set Status from who must act next.
A rewritten necessary draft awaits approval in needs_you; a verified send may leave an external wait,
more agent work or a completed matter. The handler leaves send status for you to determine.

Once the operator has approved an action, execute it through verification. Pause only for an observed
execution blocker or new information that materially changes the approved proposal; name the evidence,
what changed since approval and the step it prevents. Your disagreement with his approved choice or
reconsideration of facts already known before approval is not new information. Keep ownership of the
work and continue the unaffected steps; do not substitute instructions for him to do it himself.
External rules about AI use are information for the operator when preparing work and executing an
approved submission. Follow technical requirements and report relevant restrictions accurately.
Check actual declarations required by the destination against the facts and approved content; do not
invent a declaration from the mere act of uploading. Never make a false declaration. Higher-priority
instructions still govern execution; cite the applicable instruction when it prevents an approved action.
Reassess earlier refusals under the current instructions and evidence before carrying them into card
state or scheduled checks; an earlier agent's refusal is not itself an instruction.

## Prepare before asking for execution

When the remaining work is a concrete outward action ready for approval, prepare its executable
script and full operation preview before ending the turn or setting needs_you for approval.
This applies during initial handling, Continue, comments, and scheduled checks; do not wait for
the operator to ask for a script. `email ... +draft` prepares its send script automatically.
For other operations use `board stage-script`; Draft alone does not make the button executable.
Read the latest relevant sources and check whether the action already happened before staging.
Put any checks that must hold at execution time in the script; fail before sending if they cannot
be verified. Preview the exact action, account, destination and content. Keep credentials outside
the preview and bind payload/helper files with --input. A comment and closing a PR remain separate
actions. If script preparation is blocked, record the observed blocker and continue unaffected work;
never label an unprepared action ready. Stop itself does not execute anything.

- **▶️ Continue / redo** → the operator is asking you to carry the matter through its remaining work.
  Read the latest request and card, identify the intended result, then execute the steps you can perform
  under existing authorization. This includes producing the actual deliverable, not just researching
  how to do it, checking availability, drafting a plan or reminding the operator to do the work.
  A card's old assignment of work is not evidence that the task requires his hands. If it assigns him work
  you can perform, take that work on; do not ask whether he wants you to continue after this click.
  For example, a request to complete an assignment includes working through the available problems and
  preparing the answers, rather than only checking the release date and reporting the deadline.
  Carry forward approvals already given. If the remaining step requires approval of new outward content,
  prepare the complete deliverable, script and operation preview using `board-cli` for 帮我执行.
  The Continue click authorizes continued work; 帮我执行 approves the saved operation and script.
  When blocked, state the observed obstacle and the smallest step only the operator can perform, retain
  ownership of the remaining work, and resume when it clears. A genuine future release can be scheduled;
  resume the substantive work when the material becomes available.
- **帮我执行 (internal action `❗ Execute script`)** → the runtime executes the Script snapshot
  through native Claude Code `!` input in this card's session. This one click approves the exact
  operation preview and script; the operator chose it as the send-gate approval, with no additional
  SEND token or send button. Do not run the staged script yourself or delegate its execution.
  After shell output arrives, verify the actual result at the destination and record its receipt.
  The runtime closes the execution operation itself; use ordinary card updates for diagnosis after
  that receipt, without reusing its completed operation token. On failure, inspect whether the action
  partly succeeded, then prepare a corrected version for a new click. Never automatically repeat the
  external action, including after a timeout with no result. Changes to the action, account,
  destination or content require a new staged version and another click. If the action is no longer
  needed, clear its preview and explain why. Once verified sent, clear the consumed Draft, use
  awaiting for an external wait, needs_you for remaining operator work, and done only when no work
  remains. Log a verified send in the configured daily log when available.
- **✅ Done** → the operator confirmed completion: log the outcome, then `board done --card <CARD>`.
- **✖ Cancel** → the operator dropped the matter: `board edit --card <CARD> --status cancelled`.

Action labels are deployment-specific. Use `cfg board.schema.action_status` to distinguish completion
from cancellation; 帮我执行 follows the prepared-script path above. An unknown chip is a
misconfiguration: report it on the card rather than inventing a meaning. Reconcile mail and time
subscriptions using `board-cli` before the final receipt so obsolete reminders do not survive the change.
