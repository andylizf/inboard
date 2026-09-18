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
Legacy actions without a delivered token retain `board clear-action` as their receipt.

**The Status is already set when you arrive.** The handler moves the card the moment the chip is tapped,
because a status that waits on you is a status that never changes when you hit your deadline or die.
Continue and 📤 帮我发送 both land in `🔍 Researching`: while you carry the request out the card is
being worked, and it does not sit in `⏸ Needs you` under his name. Keep that state while handling
the request, then set Status from who must act next. A rewritten necessary draft awaits approval
in needs_you; a verified send may leave an external wait, more agent work or a completed matter.

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

When the remaining work is an outward action, put the exact thing he would be approving in `Draft`
before ending the turn or setting needs_you: the precise action, the account, the destination and the
full content. That text is what the click approves and what `board approved-draft` checks, so it is
the whole of what he agreed to — a summary of the action is not it. A card never reaches needs_you
with `Draft` empty: where the open question is whether or how to act, `Draft` holds the course you
recommend and Summary names the others, so his answer is a click or an edit rather than instructions
for you to draft from. This applies during initial handling, Continue, comments, and scheduled checks.
Read the latest relevant sources and check whether the action already happened before asking.
Checks that must hold at the moment of acting are performed then, by you, and a check that cannot
be verified stops the action rather than proceeding on the older reading. A comment and closing a PR remain separate
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
  put the complete deliverable in `Draft` using `board-cli` and let 📤 帮我发送 be his approval of it.
  **Continue and 📤 帮我发送 now do the same mechanical thing — each wakes you with the operation token —
  and differ only in what his press approved.** Continue authorizes continued work and approves no
  outward content, so nothing may go out on it. 📤 帮我发送 approves the `Draft` exactly as it stood
  when he pressed it, and that press is his approval for that one outward action. Reading a
  Continue as an approval to send is the error the unification made easy.
  When blocked, state the observed obstacle and the smallest step only the operator can perform, retain
  ownership of the remaining work, and resume when it clears. A genuine future release can be scheduled;
  resume the substantive work when the material becomes available.
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
  page, and anything optional he is choosing to include or leave out. The reason to be exact is
  that the Draft as it stood at the click is the whole of what he approved.
  **An upload is not a submission until the portal says so.** Read the state back from the page
  afterwards — the assignment or request moving out of its unsubmitted state, with the timestamp and
  filename it now shows — and record that receipt. A successful upload command is not it, and a
  recorded receipt still does not mean the matter is finished.
  The runtime closes the execution operation itself; use ordinary card updates for diagnosis after
  that receipt, without reusing its completed operation token. On failure, inspect whether the action
  partly succeeded, then prepare a corrected version for a new click. Never automatically repeat the
  external action, including after a timeout with no result. Changes to the action, account,
  destination or content require a new staged version and another click. If the action is no longer
  needed, clear its preview and explain why. Once verified sent, clear the consumed Draft, use
  awaiting for an external wait, needs_you for remaining operator work, and done only when no work
  remains. Log a verified send in the configured daily log when available.
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
  waiting on him right now, and leaving it there leaves the column he was clearing. Where it goes
  instead follows from what the card holds, not from a default: `awaiting` for the date or the
  external thing it now waits on, `done` where the check shows nothing is left to do, `cancelled`
  where the matter really is dropped. Name which one you chose.

Action labels are deployment-specific. Use `cfg board.schema.action_status` to distinguish completion
from cancellation; 📤 帮我发送 follows the approved-draft path above. An unknown chip is a
misconfiguration: report it on the card rather than inventing a meaning. Reconcile mail and time
subscriptions using `board-cli` before the final receipt so obsolete reminders do not survive the change.
