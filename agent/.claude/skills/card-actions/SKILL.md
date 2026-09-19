---
name: card-actions
description: Handle an operator Action chip, with or without a delivered operation token. Covers each chip's meaning, the approved-send path, and the Status already set before the card agent arrives. The dispatch engine runs the follow-up sweep itself; per-card agents handle only their assigned card.
---

## Resume from the board
The engine delivers scheduled checks to their card agents before mail triage. A per-card agent handles
only its assigned card; a run that received no `--operation` token uses `board pending` to find
operator actions.

For each assigned actioned card, act on the request, record the outcome, reply and reconcile mail/time
triggers before the final receipt. While an operation is open, pass its `--operation` token on every
card mutation; a superseded operation must stop. The receipt for a Continue, or for a run with no
token, is `board clear-action` on completion or `board action-fail` on failure or an unverified
outcome, never both; a 📤 帮我发送 execution is closed by the runtime itself (below). A receipt ends
operation-scoped writes. A blocker record, wherever it is written, names the evidence, what changed
since approval, the step it prevents, and the smallest step only he can perform; unaffected work
continues and the remaining work stays yours.

**The Status is already set when you arrive.** The handler moves the card the moment the chip is tapped:
Continue and 📤 帮我发送 both land in `🔍 Researching`. Keep that state while handling the request, then
set Status from who must act next: a rewritten necessary draft awaits approval in needs_you; a verified
send may leave an external wait, more agent work or a completed matter.

Once the operator has approved an action, execute it through verification and keep going until it is
done. A failure in your own means — a bug in a script you wrote, a click the page swallowed, a browser
timeout, a stale selector — is not a blocker and does not spend his approval: fix it and continue in
the same run, as many times as it takes, as long as what he approved (the action, the account, the
destination, the content) is unchanged; never re-stage and ask for another press because your tool
broke. Pause only for an observed execution blocker outside your means — a refusal by the
destination, a lockout, a step only he can do, a rule that names the stop — or new information that
materially changes the approved proposal. Your disagreement with his approved choice, or facts
already known before approval, is not new information. Never substitute instructions for him to do it.
External rules about AI use are information for the operator, reported accurately while preparing and
executing; technical requirements are followed. Check the declarations the destination actually
requires against the facts and approved content; never invent one from the act of uploading, and never
make a false one; a field the form requires is content for the preview, not a disclosure you add.
Higher-priority instructions still govern execution; cite the one that prevents an
approved action. Reassess an earlier agent's refusal under current instructions and evidence before
carrying it into card state or scheduled checks; it is not itself an instruction.

## Prepare before asking for execution

When the remaining work is an outward action, put the exact thing he would be approving in `Draft`
before ending the turn or setting needs_you: the precise action, the account, the destination and the
full content. That text is what the click approves and what `board approved-draft` checks, so it is
the whole of what he agreed to — a summary of the action is not it. A card never reaches needs_you
with `Draft` empty: where the open question is whether or how to act, `Draft` holds the course you
recommend and Summary names the others, so his answer is a click or an edit rather than instructions
for you to draft from. This applies during initial handling, Continue, comments, and scheduled checks.
Read the latest relevant sources and check whether the action already happened before asking.
Checks that must hold at the moment of acting are performed then, by you, and a check that cannot
be verified stops the action rather than proceeding on the older reading. A comment and closing a PR
remain separate actions, never inferred from each other's wording. If script preparation is blocked,
record the blocker; never label an unprepared action ready. Ending your turn runs nothing.

- **▶️ Continue / redo** → the operator is asking you to carry the matter through its remaining work.
  Read the latest request and card, identify the intended result, then execute the steps you can perform
  under existing authorization — the actual deliverable (for an assignment, the worked problems and
  prepared answers), not research on how to do it, a plan, an availability check or a reminder to him.
  A card's old assignment of work to him is not evidence that it needs his hands: where you can do it,
  do it, and do not ask whether he wants you to continue after this click. Carry forward approvals
  already given; where the remaining step needs approval of new outward content, put the complete
  deliverable in `Draft` (`board-cli`) and let 📤 帮我发送 be his approval of it.
  **Continue and 📤 帮我发送 wake you the same way, with the operation token, and differ only in what
  his press approved.** Continue authorizes continued work and approves no outward content, so nothing
  goes out on it; 📤 帮我发送 approves the `Draft` exactly as it stood when he pressed it, for that one
  outward action. When blocked, record the blocker and resume when it clears; when the material is
  genuinely not yet released, `board schedule` a check for its release date and resume then.
- **📤 帮我发送 (internal action `❗ Execute script`)** → the click wakes this card's agent with the
  operation token and you carry the action out yourself. It approves the `Draft` as it stood when he
  pressed it, and it is the whole of his approval for that action: nothing else is required of him
  and there is no separate send button. Run `board approved-draft` with this card and operation before
  an outward send: it fails if `Draft` no longer matches what he approved, and that failure is the
  gate working, not an obstacle to route around. Afterwards verify the actual result at the
  destination and record its receipt.
- **An upload or a form the browser profile can already reach is offered as one click, not handed
  back.** Where the remaining step is submitting a file or a form to a portal, check first whether
  the profile is signed into it — `web-plane profiles` lists hosts, and a host it does not list is
  undetected rather than absent, so open the page and look. A portal that opens without a login is
  a portal you can submit through: make it the 📤 帮我发送 action instead of telling him to do it by
  hand, and say in `Draft` exactly what goes where — the file's full path and size, the destination
  page, and anything optional he is choosing to include or leave out.
  **An upload is not a submission until the portal says so.** Read the state back from the page
  afterwards — the assignment or request moving out of its unsubmitted state, with the timestamp and
  filename it now shows — and record that confirmation. A successful upload command is not it, and a
  recorded confirmation still does not mean the matter is finished.
  The runtime closes the execution operation itself; use ordinary card updates for diagnosis after
  that, without reusing its completed operation token. On failure, inspect whether the action
  partly succeeded, then prepare a corrected version for a new click. Never automatically repeat the
  external action, including after a timeout with no result. Changes to the action, account,
  destination or content require a new staged version and another click. If the action is no longer
  needed, clear its preview and explain why. Once verified sent, clear the consumed Draft, use
  awaiting for an external wait, needs_you for remaining operator work, and done only when no work
  remains. Log a verified send in the daily log as `✅ Done` where `cfg board.daily_log_database_id`
  is set.
- **✅ Done and ✖ Cancel say what he wants, not what is true of the matter.** The handler writes the
  terminal status from the label before you arrive, so your first job is to check it against what
  the card itself still carries, and to put it back where the card contradicts it.
  **Done** on a card that still holds an unfulfilled obligation most often means the step you were
  chasing is finished, or that he did it himself — find out which, and close only what the evidence
  closes. **Cancel** on a card with a live deadline or something not yet delivered most often means
  not now, or not this way, rather than drop it: a pickup he would rather fold into a later
  delivery, a reply he would rather send after something else lands. Take the reading that loses
  nothing — keep the matter, move its next check to the date the card already names for the thing
  he is deferring to, and write one line saying which reading you took and how he gets the other
  («你点了取消，我读成暂时不办而不是不办了，因为 X 还在；要真销掉在卡上说一句»).
  **Whichever reading you take, the card does not stay in `needs_you`** — his press says it is not
  waiting on him right now. Where it goes
  instead follows from what the card holds, not from a default: `awaiting` for the date or the
  external thing it now waits on, `done` where the check shows nothing is left to do, `cancelled`
  where the matter really is dropped. Name which one you chose.

Action labels are deployment-specific. Use `cfg board.schema.action_status` to distinguish completion
from cancellation; 📤 帮我发送 follows the approved-draft path above. An unknown chip is a
misconfiguration: report it on the card rather than inventing a meaning. Reconcile mail and time
subscriptions using `board-cli` before the final receipt so obsolete reminders do not survive the change.
