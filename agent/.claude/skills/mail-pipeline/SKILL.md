---
name: mail-pipeline
description: The full new-mail pipeline: what counts as new, how to classify it, how to route a follow-up onto the matter that already owns it, when to ask memory and what to write back, and how to record the result. Load this the moment you are handed new mail to handle — it is the procedure, and working from memory of it instead skips the steps that keep one matter from becoming three cards.
---

## New mail pipeline
1. Read `$INBOARD_STATE/processed.json` (object: id → {...}). Missing/empty = `{}`. (State dir = `$INBOARD_STATE`.)
2. New mail (READ **or** UNREAD — do NOT filter by `is:unread`; `processed.json` is the agent's own
   seen-ledger, so mail the operator already opened is still handled), EVERY account from `board accounts`:
   `email <id> gmail +triage --query 'in:inbox newer_than:2d' --max 100 --format json`.
   NEW = triage ids not in `processed.json`.
3. **Nothing new after step 2 → output NOTHING and stop.** An empty cycle is silent; there is no tally to
   post and no card to touch.
4. For each NEW message: `email <id> gmail +read --message-id <ID>` → body + headers.
   - **Has an image, or looks empty?** If it has an image attachment, its text points to a figure (`see below` /
     `attached` / `as shown`), OR the text body is suspiciously empty/thin → use the **`email-images`** skill
     before deciding (`+read` is text-only). Obvious promo/newsletter noise (clear from sender+subject) needs no image check.
5. **Classify**: `IMPORTANT` (needs reply / deadline / money / key-person / real action) vs `NOISE`
   (newsletters, promos, automated notices, social, recruiting blasts).
   - **A reply to YOU is ALWAYS important — never noise.** If an inbox message is a reply into a thread you (the
     operator) took part in — it carries `In-Reply-To`/`References`, its subject is a `Re:` to something you
     wrote, or its thread contains a message from an address you own (see `board accounts`) — then someone is
     replying to something YOU sent → IMPORTANT, full stop, however unfamiliar the sender's address or however
     casual it looks. Likewise a genuine one-to-one email from a real human, addressed to you by name and
     expecting a reply, is IMPORTANT even from an unknown sender. **Never let an odd sender name or casual
     address push a real personal message into NOISE.** When unsure whether an inbox item is a reply to you,
     look up the sent side (`email <id> gmail +triage --query 'in:sent to:<addr>'`, or read the thread) BEFORE
     calling it noise. (Triage stays inbox-only for ITEMS, but you MAY read sent mail as a classification CLUE.)
   - **CI / build notifications** (`Run failed`, `CI failed`, workflow-run emails): treat per
     `cfg preferences.ci_notifications` — `noise` (default) = do NOT put them on the board; `surface` = card them
     even though the fork test in 6 would not, because he chose to see them.
     Real PRs / issues / @-mentions / review requests are always IMPORTANT. Auto-close/stale-bot notices = NOISE.
5b. **Dedup — route follow-ups to an EXISTING matter first** (before creating ANY card):
    - **Find it — and notice which of the two you got, because they are not the same kind of answer.**
      · `board subscriptions` — the **watchlist**: open cards that have written down, in their own words,
        what mail they are still expecting (set by `board subscribe` or `board awaiting --desc`, cleared by
        `board done`). A hit here is a card saying *this mail is mine*, so it decides on its own.
      · `board search --query '<sender / key subject words>'` — a **substring match** on Subject and Sender
        over every card, closed ones included. It produces candidates, not evidence: a bank's name matches
        every card that bank ever appeared on, and a hit whose Subscription is empty is a matter that
        already declared itself finished.
      So route straight off a watchlist hit. A search hit still has to earn it under the rules below.
    - **A closed card is context, never a destination — thread or no thread.** Read it, then open a new card
      that names it in the first line and carries the thread forward. Reopening a matter he finished, and had
      stopped thinking about, costs him more than a second card ever would, and `✅ Done` has to mean done.
    - **If it belongs to an ongoing matter** (semantic match to a subscription — a reminder / follow-up for
      something tracked, or a continuing reply thread) → do **NOT** open a new card. Append to it:
      `board log --card <ID> --text '<one-line update>'`, then set that card's Status to match reality:
      · **the reply RESOLVES it** (handled / no further action) → `board done --card <ID>` so the card they
        tracked as UNFINISHED visibly flips to `✅ Done` (**NEVER** leave a card they think is open sitting open
        after a reply resolved it); note what resolved it via `board reply --card <ID> --text '...'`.
      · **it still needs their action** → `board edit --card <ID> --status '⏸ Needs you' --needs '<what they must do>'`.
      · **NEVER** file the resolution of an OPEN card to the daily log only — an open card MUST close on the board.
      Then mark the message processed as `handled` — the disposition for mail that belonged to an
      existing card — and move on.
    - **On an open card, same thread is identity.** Mail carrying the card's `threadId`, or replying to a
      message it tracks, belongs there however old the card is: a bank answering in October the question you
      asked in July is that conversation. A *semantic* resemblance is a weaker claim — that the mail looks
      like the matter — and lands on an open card only.
    - Only a **genuinely-new** matter gets a new card. **Never `upsert` a follow-up** (upsert keys on msgid → duplicate).
5c. **Ask memory before opening ANY new card.** Only for mail that survived triage as important or
    actionable — never for noise, and never when 5b already routed it to an existing card.
    - **`omem search '<the matter in a few words>'`** — the matter, not the email subject
      (`ACME storage-quota request`, not `Re: FW: ACTION REQUIRED - please respond`).
    - **One lookup per thing, not per group.** If several unrelated alerts arrived together, each
      needs its own search. Answering the first and carding the rest looks exactly like having
      followed this step.
    - **"Was this you?" — per `cfg preferences.identity_alerts` (default `assume-self`): assume it was him
      and do not ask.** A sign-in from a new device or place, a third-party app authorization, a password
      reset he requested, a new API token — these are notices that an event happened, and
      the operator is the overwhelmingly likely cause of every one. Record it (`board daily --type 'ℹ️ FYI'`
      where a daily log is configured; otherwise a one-line `board log` on the nearest related card, or
      nothing if there is none — but never a card)
      and move on. If memory happens to name the app or device, say so in the log line; do NOT make the
      lookup a precondition, because memory cannot hold every service he has ever touched and its silence
      is not suspicion.
      · **Never let a confirmation question gate the work.** If the same mail also carries something
        actionable — an appointment, a form, a deadline, a temporary PIN — do that part. Putting "was
        that you?" in `NeedsYou` blocks everything else on the card behind a question whose answer is
        almost always yes.
      · **Escalate only when the message reports an OUTCOME, not an event.** "A new device signed in" is
        an event. "We locked your account after unauthorised access", "your password/recovery email was
        changed" (when he did not ask), "we blocked a transaction", money that actually moved — those are
        outcomes, and they are his to rule on. The test is whether the sender is telling him something
        BAD ALREADY HAPPENED, not whether something merely happened.
      · **The test is what the message reports, never who sent it.** A bank, a password manager, a
        government portal or a broker sending a notification is still sending a notification. "It
        involves money" is not the trigger — money HAVING MOVED is. Reaching for the sender's category
        to justify a card is how this rule gets quietly suspended — a bank reporting that a new phone was
        set up is still reporting an event, even when it is a bank.
    - **Nothing relevant comes back** → it is genuinely new; continue to 6.
    - **A memory covers this matter** → read it, and follow any pointer it gives to the real source of
      truth first. Then answer the ONE question that decides everything: **does this mail change what
      is already known?**
      · **No** — a repeat reminder, a status already on record, a deadline already scheduled, a
        decision already made → **do NOT open a card.** `board daily --type 'ℹ️ FYI' --subject
        '<one line: what arrived and why it needs nothing>' --account <label>` and move on. A card
        that hands back something already settled costs the operator attention twice: once to read
        it, once to remember why he can ignore it. Enough of those and he stops trusting the board.
      · **Yes** — new information, a changed deadline, something now genuinely blocked on him →
        handle it per 6.
    - **Write the change back.** Whenever this cycle moved a matter that memory tracks — a date got
      set, a reply landed, a decision was made, a blocker cleared — update that memory file (the
      write format is in your context). Not a running commentary: record what a reader coming to this
      matter cold next week needs to know.
      · **Every date you write forward must carry how it is known.** Not `2026-03-05`, but
        `2026-03-05 15:45 (confirmation email)` or `2026-03-05 (their target; nothing booked)`. A proposal, an
        invitation, and a booking are all just dates once the qualifier is gone, and the next
        reader cannot recover the difference, and a bare date gets restated as a commitment by the next
        file that copies it. Someone confirming a DEADLINE is never evidence the
        operator has committed to a date inside it — record the deadline as a deadline.
      · **Never state as settled anything the operator has not confirmed.** If the card says you
        are waiting on him, the memory says you are waiting on him.
    - **Also repair staleness, not just changes.** If the memory you just read disagrees with the
      card you just read — the card knows a date, an outcome, a reply that the memory does not —
      write the card's side back into the memory, EVEN IF this mail changed nothing — that disagreement
      is common, not an anomaly. Only do this for the memory and card you already
      opened for this message; never go scanning for others. The cost of skipping it is concrete: a
      memory still reading "two items outstanding, ball in their court", while the card has held a
      confirmed appointment for days, briefs every other session on a status that expired.

6. **Handle & record.** ⚠️ Write EVERY action down or it didn't happen — in BOTH places, they answer
   different questions: the board records what you DID to this matter and what the operator must do
   next; memory records where the matter now STANDS for whoever picks it up next (5c). A board-only
   record is stale the moment another session touches the same matter. Route it:
   - **The fork test, before you route anything: would he DO anything about this?** Not "is it
     interesting", not "might he want to see it" — would he take an action that changes something.
     **Anything he would glance at and move past is NOT a card**, however genuinely informative: a
     statement, a notification, a status, an FYI, a bill with nothing owed, someone mentioning him
     somewhere, a build waiting on CI, a notice that something happened. Those go to the daily log,
     where they cost him nothing until he chooses to look. A card costs him twice — once to read it,
     once to work out that it needed nothing — and a board where most cards cost that is a board he
     stops trusting. When you cannot name the action in a short phrase ("send the reply", "pick one of
     two", "book it before the 21st"), there isn't one: log it.
   - **Actionable** (a draft for him to send, or a decision only he can make = `⏸ Needs you` + NeedsYou / in progress) → a BOARD card (`board upsert`).
     **Optional, no deadline, "if you want", "feel free" = FYI, never a card**, however official the sender —
     a card for something he may ignore is the card that teaches him to ignore cards.
   - **You did his part and now wait on someone else** (a form submitted, a request sent, a reply owed by a
     third party) → the card goes to `⏳ Awaiting reply` with `board awaiting --desc '<what you are waiting
     for>'`, never left in `📥 New`: New is mail nobody has worked yet, and you just worked it.
   - **If the matter has a deadline, put it on the card**: `--due YYYY-MM-DD` plus
     `--lapses yes|no`. `yes` = the date passing ENDS the matter (an optional talk, an RSVP, an
     invitation that expires, a sale). `no` = the date passing makes it WORSE (enrollment, a tax
     form, mandatory training, a bill). A daily sweep closes the `yes` ones on its own and flags
     the `no` ones as overdue instead — but only for cards that carry the date, and a deadline
     living in the subject line is invisible to it. **When unsure use `no`**: a wrong `no` leaves a
     dead card on the board, a wrong `yes` closes a live obligation with nobody watching.
   - **FYI / done event** (unsubscribe, completion) → the DAILY LOG (`board daily`, where one is configured;
     otherwise it is simply marked processed), NOT the board — EXCEPT a
     completion that closes an OPEN card, which must FIRST flip that card to `✅ Done` (see 5b).
   - **Pure noise, no action** → nothing recorded (the only exception).
   Then handle by type:
   - **IMPORTANT & substantive** → subagent: research with all materials, write a considered reply, save it
     `email <id> gmail +reply --message-id <ID> --body '<reply>' --draft`. Then
     `board upsert --msgid <ID> --subject '<subj>' --account <label> --status '⏸ Needs you' --sender '<from>' --draft '<reply>' --needs '<what he does with it: send it, or the open question>'`.
   - **IMPORTANT but you need their input first** → don't draft blind:
     `board upsert ... --status '⏸ Needs you' --needs '<the specific question they must answer>'`. `⏸ Needs you`
     is the column that means his move; `📥 New` is mail nobody has worked yet, and a card should not sit
     there once you have.
   - **If the matter will keep generating mail** (recurring reminders — holds/enrollment/insurance, an ongoing
     thread awaiting replies) → after creating its card, `board subscribe --card <ID> --desc '<which follow-up
     mail belongs here, until when>'`. The next reminder appends to this card (5b) instead of duplicating.
   - **NOISE — unsubscribe is HOLISTIC, never reflexive.** A `List-Unsubscribe` header is NOT a reason. Weigh
     ALL signals together (no single one decides): usefulness/relevance to their work, research, studies,
     career, finances, life, interests; engagement (do they open or ignore it? — a signal, not the verdict);
     volume/frequency; sender type (faceless retail/promo machine vs a real org/person/community they chose).
     Pull history when useful: `email <id> gmail users messages list --params '{"userId":"me","q":"from:<SENDER>","maxResults":20}'`.
     **Unsubscribe only when the whole picture is clearly junk** (useless AND ignored AND high-volume promo from
     a faceless sender). **Keep (mark `noise`, no card) when any meaningful signal says it could matter.** When
     borderline → keep; bias hard toward NOT unsubscribing (it's semi-irreversible). Bias per
     `cfg preferences.unsubscribe` (`conservative` default = keep more). When you DO unsubscribe (standard
     One-Click only): `curl -sS -X POST -d 'List-Unsubscribe=One-Click' '<https List-Unsubscribe URL>'`, then
     (if a daily log is configured) `board daily --type '🚫 Unsubscribe' --subject 'Unsub <sender>' --account <label> --detail '<why>'`.
     mailto-only / non-one-click → never send; just mark `noise`.
   - **plain NOISE** (no unsubscribe action) → just mark processed, no card.
7. Update `$INBOARD_STATE/processed.json`: add every handled id →
   `{"account":...,"status":"drafted|flagged|unsubscribed|noise|done|handled","ts":"<iso>","subject":"<subj>","from":"<sender>","threadId":"<tid>"}`.
   Write the file. (subject/from/threadId make past dispositions searchable without re-hitting Gmail.)
8. **Card body = that item's working directory + audit.** `board upsert` returns the card id. FIRST post the
   📌 state note (`board note` — the single current-state summary, rewritten in place, under ~1500
   characters), then append your **research notes, the drafted
   reply, and what you did/decided** underneath: `board log --card <CARD_ID> --text '...'` (call it several
   times). Refresh the 📌 note whenever the state changes. The card body is the only record of this
   item's research and drafts — where the matter STANDS goes to memory as well (see 5c/6).
9. **Output**: ONE short tally line for the run log only — there is no chat/notification surface. e.g.
   `This cycle: drafts N · unsub M · decide K · board updated` (or nothing on an empty cycle).

