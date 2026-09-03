---
name: board-cli
description: Every `board` and `email` command with its arguments — the reference you reach for when you need a flag, not a rule. Load it whenever you are about to run a board or email command and are not certain of its exact form. Covers upsert/done/awaiting/subscribe/search/cards/daily, the two drafting helpers and when each is correct, and how the board and the daily log divide the work.
---

## Tools (PATH + proxy + Notion token already set by the runner)
- Gmail per account → `email <account-id> gmail ...` (account ids from `board accounts`). Sends are blocked; drafts only.
  - **Drafting — pick the right helper:**
    - `+reply --draft --message-id <ID>` ONLY when replying to a message SOMEONE ELSE sent (To = that sender, correct).
    - **`+compose-draft --to <addr> --subject S --body TEXT [--cc] [--thread-id T] [--in-reply-to <Message-ID>]`**
      for everything else: a brand-new email to a new recipient, or a follow-up on a thread the OPERATOR
      started (`+reply` there would lock To to the operator themself — wrong recipient). Clean To,
      draft-only by construction. Never hand-roll raw `users drafts create` to work around blocked helpers.
- **Memory** → who the OPERATOR is **and where every tracked matter stands**. The store, its index
  (`omem memory pool`, injected each run) and how to read/write it are already specified in your
  context — not repeated here. What that spec does NOT cover:
  - **The injected index is a fraction of the pool** — most of it is memories you will never see
    unless you ask. **`omem search '<a few words>'`** is how you actually reach it: it returns whole
    matching memories, most relevant first, each stamped with its age. Use it deliberately (see 5c),
    not on every message.
  - **Never ask the operator a personal fact without checking memory first** — their program/role,
    where they study or work, preferences, decisions already made. Asking something already on
    record ("are you a grad student or a postdoc?") reads as never having listened.
  - **Memory carries live matters, not just biography.** Hundreds of its entries are `project`
    records of things in flight — an ongoing dispute, a compliance thread, a deadline already
    scheduled. Such a memory frequently names the REAL source of truth for that matter (a case file,
    a Notion page) and says to read that instead of acting on the memory itself. When you see such a
    pointer, follow it before you decide anything.
  - **The board is this matter's WORK LOG; memory is its STATE across all sessions.** Other sessions
    — and the operator himself — move matters forward without touching the board. If you only read
    the board, you are reading your own notes and calling it the world.
- **Board** → `board` CLI:
  - `board pending` → JSON of cards the operator set an Action on (card, msgid, action, subject, account, status, draft, needs)
  - `board upsert --msgid ID --subject S --account <label> --status STATUS [--sender S] [--draft TXT] [--needs TXT]`
  - **`--subject` is the CARD TITLE — make it a self-contained, scannable one-liner** (so the board reads
    without opening cards): `<core matter> — <deadline if any> → <what they must do / what you did>`. NOT the
    raw email subject. e.g. `Insurance waiver due 6/30 → confirm dental/vision on the portal`.
  - `board clear-action --card CARD_ID` · `board log --card CARD_ID --text TXT` · `board note --card CARD_ID --text TXT`
    (`note` = the 📌 current-state summary, rewritten in place; `log` = append-only timeline — see
    "Card body layout" above)
  - **`board done --card CARD_ID`** → Status→`✅ Done`, clears Action, **clears any Subscription**, **KEEPS the
    card** (it lands in the Done column = a record). **This is how you "take an item off the active board" — NOT archive.**
    Landing in any ending status does this now, `board edit --status` included, so a card cannot end while
    still advertising for mail. **A Subscription is only ever cleared by a card ending, or by being replaced
    with a new one** (`board subscribe`, `board awaiting --desc`) — nothing expires it on a timer, so a matter
    that quietly stops mattering keeps its claim on the inbox until someone closes the card.
  - **`board awaiting --card CARD_ID --desc '<what reply to watch for>'`** → when you SENT/submitted your part
    and now WAIT on the other side: Status→`⏳ Awaiting reply`, clears Action, **keeps/sets a Subscription** so
    their reply routes back to THIS card (not a new one). Use this — NOT `done` — whenever a reply is expected;
    `done` is only for a matter truly closed out. When the awaited reply arrives, route it here (via the
    subscription) AND set the card back to `📥 New` so the operator sees it.
  - `board archive --card CARD_ID` → **trashes** the card (recoverable ~30d). Use ONLY for true cleanup
    (a mistaken/duplicate card), never for normal completion.
  - **`board subscriptions`** → JSON of ACTIVE matters that registered a follow-up subscription
    (`card, subject, subscription, status, sender`). **Read this in the pipeline BEFORE creating any card.**
  - **`board search --query '<words>'`** → substring match across EVERY card, `✅ Done` included, over the
    Subject, Sender, NeedsYou and Subscription **and the card body** — the research, the drafts and the
    decisions live in the body, so a name that was only ever written in a log line is findable. Each hit
    reports `matched` (which fields) and a `snippet` around a body hit. Filters: `--open-only`, `--status`,
    `--account`, `--since YYYY-MM-DD`, `--limit`. Use `--no-body` when you only want a title sweep.
    It still answers "what cards mention this?", never "does this mail belong there" — a bank's name
    matches every card that bank ever appeared on, finished ones included.
  - **`board stale-awaiting --days N`** → JSON of `⏳ Awaiting reply` cards that have gone N+ days with NO reply.
    The follow-up sweep in §A uses it so a sent-but-unanswered matter doesn't rot silently.
  - **`board subscribe --card CARD_ID --desc '<natural language: which follow-up mail belongs here, until when>'`**
    → when a matter will keep getting follow-up mail (recurring reminders / an ongoing thread), register it so
    future matching mail routes onto THIS card's feed instead of spawning a duplicate. `done` auto-clears it.
  - `board daily --type '🚫 Unsubscribe'|'✅ Done'|'✉️ Draft'|'ℹ️ FYI' --subject S --account <label> [--detail D]`
    (only if a daily-log DB is configured; otherwise skip FYI logging).
  - **Two surfaces**: the **board** holds live actionable items (statuses `📥 New` `🔍 Researching`
    `✍️ Draft ready` `⏳ Awaiting reply`) plus the `✅ Done` column for finished items (kept for the record).
    Pure FYI events (unsubscribes) go to the **daily log** via `board daily`, NOT the board.

