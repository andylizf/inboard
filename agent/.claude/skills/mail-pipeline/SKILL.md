---
name: mail-pipeline
description: The full new-mail pipeline: what counts as new, how to classify it, how to route a
follow-up onto the matter that already owns it, when to ask memory and what to write back, and how to
record the result. Load this the moment you are handed new mail to handle — it is the procedure, and
working from memory of it instead skips the steps that keep one matter from becoming three cards.
---

## New mail pipeline
1. Read `$INBOARD_STATE/processed.json` (object: id → {...}); missing or empty = `{}`.
2. New mail, read or unread — do not filter by `is:unread`; `processed.json` is your own seen-ledger, so
   mail the operator already opened is still handled — from every account in `board accounts`:
   `email <id> gmail +triage --query '{in:inbox in:sent} newer_than:2d' --max 100 --format json`.
   New = triage ids not in `processed.json`.
3. **Nothing new → output nothing and stop.** No tally, no card touched.
4. For each new message: `email <id> gmail +read --message-id <ID>` → body + headers. `+read` is text
   only: with an image attachment, text that points to a figure ("see below", "attached", "as shown"), or
   a suspiciously thin body, load `email-images` before deciding. Obvious promo/newsletter noise, clear
   from sender and subject, needs no image check.
5. **Classify** `IMPORTANT` (needs reply / deadline / money / key person / real action) vs `NOISE`
   (newsletters, promos, automated notices, social, recruiting blasts).
   - **A reply to the operator is always important.** A message that carries `In-Reply-To`/`References`
     into a thread he took part in, a `Re:` to something he wrote, or a thread holding a message from an
     address in `board accounts` is someone answering him, whatever the sender's address or tone. So is a
     one-to-one mail from a real person addressed to him by name and expecting a reply. When unsure
     whether a mail is a reply to him, read the sent side (`email <id> gmail +triage --query 'in:sent
     to:<addr>'`, or the thread) before calling it noise.
   - **Outgoing mail is work to track.** Read the body and the conversation's latest replies to work out
     whose move remains. A request awaiting a reply or result, or a promise by the operator, is
     IMPORTANT even when the mail is itself a reply; a finished acknowledgement with no remaining action
     needs no card. Never draft a reply to his own outgoing mail; record that it was sent and route it
     under step 6.
   - **CI / build notifications** (`Run failed`, `CI failed`, workflow-run mails) follow
     `cfg preferences.ci_notifications`: `noise` (default) keeps them off the board; `surface` cards them
     although the fork test in 6 would not. Real PRs, issues, @-mentions and review requests are always
     IMPORTANT — read in full and fork-tested, and a mention with no ask still only logs; auto-close
     and stale-bot notices are NOISE.

5b. **Route a follow-up to the existing matter before creating any card.** Two lookups, which answer
    differently:
    - `board subscriptions` — the watchlist: open cards that wrote down which mail they still expect (set
      by `board subscribe` or `board awaiting --desc`, cleared by `board done`). A hit is the card claiming
      this mail; route on it alone.
    - `board search --query '<sender / key subject words>'` — substring matches over every card's
      properties and body, closed cards included. A hit is a candidate, not evidence: read its Status and
      context; an empty Subscription does not mean done.
    Rules for a match:
    - On an open card, same thread is identity: mail carrying the card's `threadId`, or replying to a
      message it tracks, belongs there however old the card is. A semantic resemblance lands on an open
      card only.
    - A closed card is context. Create a new card referencing it only when the incoming mail leaves
      actual work; an acknowledgement or repeated confirmation is FYI. Do not reopen completed work.
    - Mail that belongs to an ongoing matter never gets a new card. Run 5c first, then append
      `board log --card <ID> --text '<one-line update>'` and set Status to match reality: the reply
      resolves it → `board done --card <ID>` (a card he tracks as open never stays open after the reply
      that resolved it; record the resolution in Summary and the log, with a comment only to answer his
      question, deliver a requested report, or surface a newly required action or a material change in
      its urgency or arrangement); it still needs his action → `board edit --card <ID> --status '⏸
      Needs you'` and
      open Summary with that action. The resolution of an open card is never filed to the daily log
      alone. Mark the message `handled`, then finish the Summary, memory and trigger updates in 6–8.
    - Only a genuinely new matter gets a new card. Never `upsert` a follow-up: upsert keys on msgid and
      would duplicate.

5c. **Check memory before working an actionable matter**, new card or existing; noise needs no lookup,
    and a lookup already made for this matter in this event is reused.
    - `omem search '<the matter in a few words>'` — the matter, not the subject line (`ACME storage-quota
      request`, not `Re: FW: ACTION REQUIRED - please respond`). One lookup per thing: several unrelated
      alerts in one batch each get their own search.
    - **"Was this you?"** follows `cfg preferences.identity_alerts` (default `assume-self`): a sign-in
      from a new device or place, a third-party app authorization, a password reset he requested,
      a new API token is a
      notice that an event happened, and he is its cause. Record it (`board daily --type 'ℹ️ FYI'` where a
      daily log is configured; otherwise a one-line `board log` on the nearest related card, or, where no
      related card exists, nothing) and move on; where memory names the app or device, say so, but
      memory's silence is not suspicion.
      Do what else the same mail carries — an appointment, a form, a deadline, a temporary PIN — rather
      than parking it behind the question. Investigate only a concrete problem: an account locked after
      unauthorized access, a transaction blocked pending a response, a change he reports as unauthorized.
      An ordinary payment or transfer is FYI whatever the amount; a new recipient or absence from memory
      is not evidence. Ask "was this you?" only on specific evidence or where he asked for that
      monitoring. A notice that changes an existing matter updates that card rather than opening one.
    - No memory match → keep the routing from 5b and continue to 6.
    - A memory covers the matter → read it, follow any pointer to the real source of truth first, then
      decide whether this mail changes what is known:
      · an outgoing obligation is open with no open card → create the card even if memory records it;
        memory cannot surface a waiting card or remind him of a promise;
      · nothing new, no untracked obligation and no open card for it — a repeat reminder, a status
        already on record, a deadline already scheduled, a decision already made → no card:
        `board daily --type 'ℹ️ FYI' --subject '<one line: what arrived and why it needs nothing>'
        --account <label>`;
      · an existing destination card still gets its reconciliation and state update, memory match or not;
      · new information, a changed deadline, something now blocked on him → step 6.
    - **Write the change back.** Where the matter stands goes to memory whenever Summary changes: update
      the file that tracks it, or create one for a matter that will outlive the card (the write format
      is in your context), with what a reader coming to it cold next week needs, not a running
      commentary. Every
      forward date carries how it is known — `2026-03-05 15:45 (confirmation email)`, `2026-03-05 (their
      target; nothing booked)` — and a confirmed deadline is recorded as a deadline, never as his
      commitment to a date inside it. An operator decision is recorded as settled only on his
      confirmation; an external outcome is recorded from its source.
    - **Repair conflicting records from evidence.** Where a memory and a card disagree, compare their dates
      and sources and correct the stale one; neither wins by itself, and an unresolved conflict is
      recorded as uncertainty. Limit this to records the assigned matter needs.

6. **Handle and record.** Every action is written down: the board records what you did to this matter
   and what he must do next, memory where the matter now stands (5c). Route it:
   - **The fork test, before routing anything: would he do anything about this, including following up
     if a reply or result never arrives?** Not "is it interesting" — would he take an action that changes
     something. Anything he would glance at and move past is not a card, however informative: a
     statement, a notification, a status, an FYI, a bill with nothing owed, a mention of him, a build
     waiting on CI, a notice that something happened → the daily log. When you cannot name the action in a
     short phrase ("send the reply", "pick one of two", "book it before the 21st"), there is none: log it.
     "Do you want to act?" establishes no obligation: optional top-ups, unrequested explanations and
     routine transaction acknowledgements stay information unless he takes them up or concrete
     circumstances require action; related information goes onto an existing card without making it
     Needs you or extending a matter past its actual work. An unpaid amount due or a service
     interruption still needs handling. Only actionable matters get subscriptions and timed reviews; a
     review reapplies this test — a card created for a pure notice has its information preserved in the
     daily log where configured, its triggers cancelled, and is archived, never marked Done; on a mixed
     card only the invented action goes.
   - **Outgoing mail:** waiting for a reply or result is actionable — create or update one card, `board
     awaiting --card <ID> --desc '<who owes what response or result>'`, Summary describing the wait. A
     commitment by the operator (materials promised by Friday) stays `Needs you` with a concrete next
     action, and Due plus scheduled checks when dated; where both sides owe work, keep his next action
     visible and subscribe to the expected reply. Close an existing card only when no action or awaited
     result remains. Record the sent date, recipient and remaining action in Summary and the log; use
     the daily log as `✅ Done` where `cfg board.daily_log_database_id` is set. Never invent a deadline
     from the reminder interval.
   - **Actionable** (a necessary draft awaiting approval, or a required decision only he can make →
     `⏸ Needs you` with the request in Summary; `🔍 Researching` while agent work remains — there is no
     New column) → a board card (`board upsert`). A draft you chose to create establishes no task; an
     upstream alert remaining open matters only where it leaves a concrete risk, restriction or required
     outcome unresolved; an optional suggestion with no decision to track is FYI. A direct invitation
     awaiting acceptance, or an opportunity he asked to track, is `needs_you` when his decision is next,
     however optional its wording and however distant its deadline.
   - **You did his part and now wait on someone else** (a form submitted, a request sent, a reply owed by
     a third party) → `⏳ Waiting` with `board awaiting --desc '<what you are waiting for>'`.
   - **A deadline goes on the card** with `--due YYYY-MM-DD`; schedule a useful pre-deadline check with
     `board schedule`, and an expiry check only where the window shutting ends the matter. On any new
     development reconcile all schedules. Due passing alone never proves completion; overdue
     obligations stay open.
   - **FYI / done event** (unsubscribe, completion) → the daily log (`board daily`, where
     `cfg board.daily_log_database_id` is set;
     otherwise just marked processed), except a completion that closes an open card, which first flips
     that card to `✅ Done` (5b).
   - **Pure noise** → nothing recorded.
   Then, for received mail, by type:
   - **IMPORTANT with a necessary reply under the fork test** → research with all materials, load
     `writing-for-people`, write a considered reply and complete its `writing-reviewer` review before
     saving it (the drafting and review-record rules are in `board-cli`):
     `email <id> gmail +draft --card <CARD> --reply-to-message <ID> --body '<reply>'` puts the draft on the
     card and logs its id. Then `board upsert --msgid <ID> --subject '<subj>' --account <label> --status
     '⏸ Needs you' --sender '<from>'` and `board note` for Summary. Keep the header-bearing Draft
     preview `+draft` wrote; never replace it with the bare body.
   - **IMPORTANT and his decision comes first** (whether to answer at all, who answers, which of two
     courses) → draft anyway: a `⏸ Needs you` card whose action is a reply always carries the Draft,
     written under your own recommendation through `+draft` and complete enough to send, so his move
     is approve, edit or reject rather than dictate. Summary's first sentence is the decision he must
     make; then the assumption the draft rests on, where the wording turns on a fact only he holds,
     and the other courses with what changes under each.
   - **A matter that will keep generating mail** (recurring reminders — holds, enrollment, insurance; a
     thread awaiting replies) → after creating its card, `board subscribe --card <ID> --desc '<which
     follow-up mail belongs here, until when>'`, so the next reminder appends (5b) instead of duplicating.
   - **NOISE — unsubscribe on the whole picture, never on a `List-Unsubscribe` header.** Weigh relevance
     to his work, research, studies, career, finances, life and interests; engagement (a signal, not the
     verdict); volume; sender type (faceless retail/promo machine vs an org, person or community he
     chose). History when useful: `email <id> gmail users messages list --params
     '{"userId":"me","q":"from:<SENDER>","maxResults":20}'`. Unsubscribe only when the whole picture is
     clearly junk — useless, ignored and high-volume promo from a faceless sender — and keep (mark
     `noise`, no card) when any meaningful signal says it could matter or the case is borderline;
     `cfg preferences.unsubscribe` (`conservative` default) sets the bias. Unsubscribing is standard
     One-Click only, never from a message the provider filed as spam: `curl -sS -X POST -d
     'List-Unsubscribe=One-Click' '<https List-Unsubscribe URL>'`, then, where a daily log is configured, `board daily --type '🚫 Unsubscribe' --subject 'Unsub <sender>'
     --account <label> --detail '<why>'`. A mailto-only or non-One-Click sender is never sent anything:
     mark `noise`.
   - **Plain NOISE** → mark processed, no card.
7. Update `$INBOARD_STATE/processed.json`: add every handled id →
   `{"account":...,"status":"drafted|flagged|unsubscribed|noise|done|handled","ts":"<iso>","subject":"<subj>","from":"<sender>","threadId":"<tid>"}`
   and write the file. Status: `drafted` a reply was drafted; `flagged` carded with no draft;
   `unsubscribed`; `noise`; `done` a completion that closed a card or went to the daily log; `handled`
   mail that belonged to an existing card.
8. **Summary is his overview; the body is the audit trail.** `board upsert` returns the card id. Summary
   through `board note`: at most 300 characters, first sentence the one thing only he can do now or
   「不用你做事」, then the current state in two or three sentences, rewritten whole whenever the state
   changes. Each action taken and each draft id is one `board log --card <CARD_ID> --text '...'` line
   (the line `+draft` writes counts); research notes stay in your session.
9. **Output**: one short tally line for the run log — there is no chat or notification surface — e.g.
   `This cycle: drafts N · unsub M · decide K · board updated`, or nothing on an empty cycle.
