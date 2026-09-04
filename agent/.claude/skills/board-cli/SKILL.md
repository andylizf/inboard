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
- **`board stale-awaiting --days N`** → cards whose last move was ours with nothing back in N+ days. Each row
  carries `pass` (1 = still awaiting, 2 = already nudged and untouched again) and `days_waited`. The sweep
  in `card-actions` runs it every cycle.
- `board comments --card C` → the card's comment thread.

**Creating and editing**
- `board upsert --msgid ID --subject S --account <label> --status STATUS [--sender S] [--draft TXT] [--needs TXT] [--due YYYY-MM-DD --lapses yes|no]`
  → creates, or updates the card keyed on that msgid. **`--subject` is the CARD TITLE — a self-contained,
  scannable one-liner**: `<core matter> — <deadline if any> → <what he must do / what you did>`, in Chinese
  like everything he reads: `保险 waiver 6/30 截止 → 上门户确认牙科/视力`. Never the raw email subject.
- `board edit --card C [--status S] [--needs TXT] [--subject S] [--draft TXT] [--sender S] [--due D --lapses yes|no]`
  → change only the fields you pass, by card id. Landing in an ending status (`done`, `unsub`, `expired`)
  clears Action and Subscription here too.
- **`--due` / `--lapses`**: `yes` = the date passing ENDS the matter (an RSVP, an optional talk, a sale);
  `no` = the date passing makes it WORSE (enrollment, a tax form, a bill). A daily sweep closes the `yes`
  ones and flags the `no` ones overdue — only for cards carrying the date; one living in the title is
  invisible to it. Unsure → `no`.
- `board note --card C --text TXT` → the card's single 📌 current-state summary, REWRITTEN in place every
  time, kept under ~1500 characters. Post it first on a new card so it sits at the top. Reading it alone must
  be enough to understand the card.
- `board log --card C --text TXT` → the append-only timeline under the note: research, actions, raw ids.
- `board reply --card C --text TXT` → a comment in the card's thread, where he reads answers to what he asked.
- `board plan --card C --steps 'a|b|c'` (2–5 steps) / `board tick --card C --n <0-based>` → the live checklist.
- `board image --card C --file PATH [--caption TXT]` → upload a screenshot to the card.

**Moving a card**
- **`board done --card C`** → `✅ Done`, clears Action, **clears the Subscription**, KEEPS the card as a
  record. This is how an item leaves the active board — NOT archive. A Subscription is only ever cleared by
  a card ending or by being replaced (`subscribe`, `awaiting --desc`); nothing expires it on a timer, so a
  matter that quietly stops mattering keeps its claim on the inbox until someone closes the card.
- **`board awaiting --card C --desc '<what reply to watch for>'`** → you sent or submitted your part and now
  wait: `⏳ Awaiting reply`, clears Action, keeps/sets the Subscription so the reply routes back here. Use
  this — not `done` — whenever a reply is expected. When it arrives: move the card to `⏸ Needs you` so he
  sees it, **unless the reply resolves the matter**, in which case close it.
- **`board nudge --card C --days N [--n K]`** → surface a card the sweep found: `⏸ Needs you`, a marked `NeedsYou`
  asking whether to chase (`--n 2` and up words it as a repeat), Subscription kept. The marker is what lets
  the sweep find the card again if he does not act.
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
`⏳ Awaiting reply` = someone else owes the next move, `⏸ Needs you` = his move, a ready draft included) and the `✅ Done` column keeps finished items as a record. Pure FYI events go to the daily log,
where they cost him nothing until he chooses to look.
