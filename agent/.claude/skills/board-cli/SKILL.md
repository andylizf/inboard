---
name: board-cli
description: The `board` and `email` command reference AND the rules bound to specific commands — which drafting helper is correct when, what `done` clears, why `archive` is not completion, how a card's title is written. Load this at the start of every run before your first board or email command, and again whenever you need the exact form of a flag; a confidently-wrong flag costs a deadline the sweep cannot see. Covers every board subcommand, the email helpers including the one path that sends, `cfg`, and how the board and the daily log divide the work.
---

## Tools

`board`, `email` and `cfg` are on PATH; the proxy and the Notion token are already set. `cfg <key>` reads
any value from the deployment's config (`cfg identity.name`, `cfg preferences.calendar_events`).

### Gmail, per account

Account ids come from `board accounts` (each row: `id`, `label`, `address`). Then `email <id> gmail ...`.

- **Read:** `+triage --query '<gmail search>' --max N --format json` → headers only (id, from, subject,
  date). `+read --message-id <ID>` → one message's body and headers, text only — use the `email-images`
  skill when it has a figure or looks empty. Raw API: `users messages list --params '{"userId":"me","q":"from:<addr>","maxResults":20}'`
  for a sender's history.
- **Draft — one command, and it is the only one:** `+draft --card <CARD> --body TEXT` plus either
  `--reply-to-message <msgid>` (To, subject, thread and In-Reply-To come from that message; use it when
  answering mail someone ELSE sent) or `--to <addr> --subject S [--cc] [--thread-id T] [--in-reply-to <Message-ID>]`
  (a new mail, or a follow-up on a thread the OPERATOR started — replying there would address him). It
  creates the Gmail draft, puts the text into the card's Draft field and logs the draft id, in one step.
  A draft that is not on the card cannot be seen by him and cannot be sent, so the raw helpers
  (`+reply`, `+compose-draft`, `users drafts create`) are refused. The Draft field holds the latest draft;
  earlier ones remain in the log with their ids and are still sendable by id.
- **Send:** every send is blocked except `+send-approved --card <CARD> --draft-id <ID>`, which requires the
  operator to have tapped the send chip on that card. Its full procedure, including what to do when it
  fails, is in `card-actions`. Everything else you write is a draft.

### Board

**Reading**
- `board accounts` → the mailboxes to watch. `board whoami` → the integration's own identity.
- `board pending` → cards the operator set an Action on (card, msgid, action, subject, account, status, draft, needs).
- `board actionof --card C` / `board statusof --card C` → one card's current Action / Status.
- **`board subscriptions`** → the watchlist: open cards that wrote down what mail they expect
  (`card, subject, subscription, status, sender`). A hit is the card claiming the mail.
- **`board cards`** → every open card, compactly (`card, status, subject, sender, account, edited`). The
  dispatcher reads this whole; a card agent rarely needs it.
- **`board search --query '<words>'`** → substring match across EVERY card, `✅ Done` included, over Subject,
  Sender, NeedsYou, Subscription **and the card body** — a name written once in a log line is findable. Each
  hit reports `matched` and a body `snippet`. Filters: `--open-only`, `--status`, `--account`,
  `--since YYYY-MM-DD`, `--limit`; `--no-body` for a title-only sweep. It answers "what cards mention
  this?", never "does this mail belong there" — a bank's name matches every card that bank ever appeared on.
- `board schedules --card C` → every pending time trigger, with its id, offset-aware time and action.
- `board comments --card C` → the card's comment thread.

**Creating and editing**
- `board upsert --msgid ID --subject S --account <label> --status STATUS [--sender S] [--draft TXT] [--needs TXT] [--due YYYY-MM-DD]`
  → creates, or updates the card keyed on that msgid. **`--subject` is the CARD TITLE — a self-contained,
  scannable one-liner**: `<core matter> — <deadline if any> → <what he must do / what you did>`, in Chinese
  like everything he reads: `保险 waiver 6/30 截止 → 上门户确认牙科/视力`. Never the raw email subject.
- `board edit --card C [--status S] [--needs TXT] [--subject S] [--draft TXT] [--sender S] [--due D]`
  → change only the fields you pass, by card id. Landing in an ending status (`done`, `unsub`, `expired`, `cancelled`)
  clears Action, Subscription and all time triggers.
- **`--due`** stores the deadline. Passing it flags overdue work; it never completes the matter.
- `board note --card C --text TXT` → the card's single 📌 current-state summary, REWRITTEN in place every
  time, kept under ~1500 characters. Post it first on a new card so it sits at the top. Reading it alone must
  be enough to understand the card.
- `board log --card C --text TXT` → the append-only timeline under the note: research, actions, raw ids.
- `board reply --card C --text TXT` → a comment in the card's thread, where he reads answers to what he asked.
- `board plan --card C --steps 'a|b|c'` (2–5 steps) / `board tick --card C --n <0-based>` → the live checklist.
- `board image --card C --file PATH [--caption TXT]` → upload a screenshot to the card.

**Moving a card**
- **`board done --card C`** → completed work only. When the operator drops a matter use
  `board edit --card C --status cancelled`; when a verified window has shut with no remaining action use
  `--status expired`. All ending statuses keep the card as a record and clear mail/time subscriptions.
- **`board awaiting --card C --desc '<what is awaited>'`** → `⏳ Waiting`: mail, a date, recovery or another
  external condition. Clears NeedsYou and Action, keeps time triggers, and sets the readable Subscription.
  When a trigger arrives, continue working yourself; use `⏸ Needs you` only for a concrete operator action.
- **`board schedule --card C --at '2026-10-01T09:00:00-04:00' --reason '<what to check or do, and where>'`**
  → add a time trigger without replacing the others or changing Status. Use an explicit UTC offset for that
  date. `NextCheck` shows the earliest time; `NextAction` shows every scheduled action. `Wakeups` is internal.
- **`board unschedule --card C --id ID`** or **`--all`** → cancel obsolete triggers. After every mail,
  comment, action or wakeup, read `board schedules` and reconcile the whole plan with current facts.
- **`board wake-ack --card C --token TOKEN`** → after recording results and arranging any further checks,
  acknowledge the scheduled delivery token from the prompt. Removes only that delivery's triggers; keeps
  newly scheduled work. Acknowledging a check does not mark the matter done.
- **`board subscribe --card C --desc '<which follow-up mail belongs here, until when>'`** → register a
  matter that will keep getting mail, so the next reminder lands on this card instead of a new one. Write it
  at the grain he acts on, not the sender's.
- `board clear-action --card C` → reset the chip after handling an Action; the completion receipt.
- `board archive --card C` → **trashes** the card (recoverable ~30 days). Only for a mistaken or duplicate
  card, never for completion.

### The daily log

`board daily --type '🚫 Unsubscribe'|'✅ Done'|'✉️ Draft'|'ℹ️ FYI' --subject S --account <label> [--detail D]`
— only where a daily-log database is configured; otherwise the FYI is simply marked processed.

**Two surfaces.** The board holds what is live (`📥 New` = mail nobody has worked yet, `🔍 Researching`,
`⏳ Waiting` = waiting for mail, time or an external condition, `⏸ Needs you` = his move, a ready draft included) and the `✅ Done` column keeps finished items as a record. Pure FYI events go to the daily log,
where they cost him nothing until he chooses to look.
