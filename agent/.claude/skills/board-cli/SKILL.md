---
name: board-cli
description: The `board` and `email` command reference and the rules bound to specific commands — which drafting helper is correct when, what `done` clears, why `archive` is not completion, how a card's title is written. Load this at the start of every run before your first board or email command, and again whenever you need the exact form of a flag. Covers every board subcommand, the email helpers including the one path that sends, `cfg`, and the daily log.
---

## Tools

`board`, `email` and `cfg` are on PATH; the proxy and the Notion token are already set. `cfg <key>` reads
any value from the deployment's config (`cfg identity.name`, `cfg preferences.calendar_events`).

### Drafts and approval

The card's Draft is the preview of a proposed outward action — an email, a GitHub comment, a form
submission. Before writing or editing one, load `writing-for-people`; before publishing it to the card
or Gmail, complete its `writing-reviewer` review and apply the accepted fixes (its one-sentence
instant-reply exception still requires checking the reviewer's tables yourself), and record the reviewed
draft version, findings and fixes — or the exception and self-check — in `board log`, never in Summary
or the email body. Review precedes his approval; a rewrite after approval is a new preview and a new
click, and a rewritten draft is never sent on the old approval.
For non-email actions use `board stage-script` below: include the action and platform, sending account,
exact destination URL or recipient, and the full content or submitted fields. A comment and closing a
PR are separate actions, each shown explicitly, never inferred from the other's wording. The preview
is self-contained — he approves it without
reading the log — and is the operation and nothing else: what went wrong last time is one log line, and
your own tooling and how you tested it reach neither him nor the preview. Publish the preview's
content without the lines that describe the operation. Any change to these details requires a new
📤 帮我发送 click.

Store the complete preview through these commands; they chunk long text and verify Draft by readback.
Summary's 300-character rule does not apply to Draft. A size error requires a smaller explicitly scoped proposal or a reported
storage limitation, never silent truncation or hiding the rest in the log. He reviews and approves on
the card: never send him to an email drafts folder or ask for a comment saying yes. A send failure
describes the operation, not whether the matter is finished.

`board approved-draft --card C --operation TOKEN` returns the approved current preview, or fails if the
operation is stale, is not an approved execution, or the preview changed. For the 📤 帮我发送 button
it requires a running native script with a bound preview. This check does not send anything. The runtime
supplies INBOARD_OPERATION and INBOARD_CARD to the script; use them for guarded sending commands.

### Prepared scripts

`board stage-script --card C --file ./scripts/action.sh --cwd "$PWD" --description TEXT [--input FILE]`
saves a Bash script and publishes its complete preview in Script for the 📤 帮我发送 button. It also
sets Draft to TEXT, the human-readable operation preview. Describe
the action, account, destination and exact outward content. Repeat `--input` for payload and helper
files that must retain their bytes until execution; use absolute paths in the script. Staging does
not execute the script. Keep credentials in the project's secret store, outside the preview.

The button executes the saved version once through Claude Code's native `!` mode. Inspect the saved
result and destination before preparing another version after a failure or an unknown outcome.
Follow `card-actions` for diagnosis and result reporting. Declared inputs are checked by hash;
arbitrary dependencies and remote state are not frozen. Prepare this before asking for approval;
ending your turn never clicks or executes it.

`board stage-email --card C --account ACCOUNT --draft-id ID` binds the current email Draft to a
guarded send script. `email ... +draft` calls this automatically. Use it for an existing Gmail draft
after checking that its account, recipients, subject and body still match the current card preview.

### Gmail, per account

Account ids come from `board accounts` (each row: `id`, `label`, `address`). Then `email <id> gmail ...`.

- **Read:** `+triage --query '<gmail search>' --max N --format json` → headers only (id, from, subject,
  date). `+read --message-id <ID>` → one message's body and headers, text only — use the `email-images`
  skill when it has a figure or looks empty. Raw API: `users messages list --params '{"userId":"me","q":"from:<addr>","maxResults":20}'`
  for a sender's history.
- **Draft — one command, and it is the only one:** `+draft --card <CARD> --body TEXT` plus either
  `--reply-to-message <msgid>` (To, subject, thread and In-Reply-To come from that message; use it when
  answering mail **someone else** sent) or `--to <addr> --subject S [--thread-id T] [--in-reply-to <Message-ID>]`
  (a new mail, or a follow-up on a thread **the operator** started — replying there would address him). It
  creates the Gmail draft, puts the text into Draft, stages the guarded send script and logs the draft id.
  Both forms accept `--cc <addresses>` and `--bcc <addresses>`. The card preview starts with From, To,
  Cc, Bcc and Subject, then a `---` separator and the body. Pass only the email body to `--body`;
  the wrapper adds the preview headers using the selected account and actual recipients.
  A draft that is not on the card cannot be seen by him and cannot be sent, so the raw helpers
  (`+reply`, `+compose-draft`, `users drafts create`) are refused. The Draft field holds the latest draft;
  earlier ones remain in the log for audit. Sending requires the current card preview to match the
  preview bound to the script approved by the operator's latest 📤 帮我发送 click.
- **Send:** the email wrapper blocks every send except `+send-approved --card <CARD> --draft-id <ID> --operation <TOKEN>`, which requires the
  native script launched by 📤 帮我发送. The generated script passes INBOARD_OPERATION as its token.
  Do not invoke it yourself after preparing a draft. Failure handling is in `card-actions`.

### Board

**Reading**
- `board accounts` → the mailboxes to watch. `board whoami` → the integration's own identity.
- `board pending` → cards the operator set an Action on (card, msgid, action, subject, account, status, draft, summary).
- `board actionof --card C` / `board statusof --card C` → one card's current Action / Status.
- **`board subscriptions`** → the watchlist: open cards that wrote down what mail they expect
  (`card, subject, subscription, status, sender`). A hit is the card claiming the mail.
- **`board cards`** → every open card, compactly (`card, status, subject, sender, account, edited`). The
  dispatcher reads this whole; a card agent reads it before settling a title.
- **`board search --query '<words>'`** → substring match across every card, `✅ Done` included, over Subject,
  Sender, Summary, Subscription and the card body. Each hit reports `matched` and a body `snippet`.
  Filters: `--open-only`, `--status`, `--account`, `--since YYYY-MM-DD`, `--limit`; `--no-body` for a
  title-only sweep. It answers "what cards mention this?", never "does this mail belong there".
- `board schedules --card C` → every pending time trigger, with its id, offset-aware time and action.
- `board comments --card C` → the card's comment thread.

**Creating and editing**
- `board upsert --msgid ID --subject S --account <label> --status STATUS [--sender S] [--draft TXT] [--due YYYY-MM-DD]`
  → creates, or updates the card keyed on that msgid. **`--subject` is the card title: the matter and
  nothing else**, at most 25 characters, in Chinese like everything he reads (`保险 waiver 牙科视力确认`);
  deadline, state and what he must do go in Summary and Due. Never the raw email subject.
- `board edit --card C [--status S] [--subject S] [--draft TXT] [--sender S] [--due D]`
  → change only the fields you pass, by card id. Landing in an ending status (`done`, `unsub`, `expired`, `cancelled`)
  clears Action, Subscription and all time triggers.
- **`--due`** stores the deadline. Passing it flags overdue work; it never completes the matter.
- `board note --card C --text TXT` → replaces the `Summary` property: at most 300 characters, first
  sentence the one thing only he can do now or 「不用你做事」, then the current state in two or three
  sentences; rewritten whole whenever facts change. A resolved matter with no material next action is
  complete, not waiting for approval of an optional draft.
- `board log --card C --text TXT` → the audit trail in the body: one line per action taken or fact
  verified, raw ids in parentheses; no research notes, no reasoning.
- `board reply --card C --text TXT` → a comment in the card's thread, where he reads answers to what he asked.
- `board plan --card C --steps 'a|b|c'` (2–5 steps) / `board tick --card C --n <0-based>` → the live checklist;
  a new plan replaces the card's previous one.
- `board image --card C --file PATH [--caption TXT]` → upload a screenshot to the card.

**Moving a card**
- **`board done --card C`** → completed work only. When the operator drops a matter use
  `board edit --card C --status cancelled`; when a verified window has shut with no remaining action use
  `--status expired`. All ending statuses keep the card as a record and clear mail/time subscriptions.
- **`board awaiting --card C --desc '<what is awaited>'`** → `⏳ Waiting`: mail, a date, recovery or another
  external condition. Clears Action, keeps time triggers, and sets the readable Subscription.
  When a trigger arrives, continue working yourself; use `⏸ Needs you` only for a concrete operator action.
- **`board schedule --card C --at '2026-10-01T09:00:00-04:00' --reason '<what to check or do, and where>'`**
  → add a time trigger without replacing the others or changing Status. Use an explicit UTC offset for that
  date. `NextCheck` shows the earliest time; `NextAction` shows every scheduled action. `Wakeups` is internal.
- **`board unschedule --card C --id ID`** or **`--all`** → cancel obsolete triggers. After every mail,
  comment, action or wakeup, read `board schedules` and reconcile the whole plan with current facts.
  Keep a next review on every unfinished card, including Needs you. The sweep fills an empty schedule
  with a default review; replace it with a matter-specific time and sources to check when known.
- **`board wake-ack --card C --token TOKEN`** → after recording results and arranging any further checks,
  acknowledge the scheduled delivery token from the prompt. Removes only that delivery's triggers; keeps
  newly scheduled work and supplies a default review if an unfinished card would have none.
  Acknowledging a check does not mark the matter done.
- **`board subscribe --card C --desc '<which follow-up mail belongs here, until when>'`** → register a
  matter that will keep getting mail, so the next reminder lands on this card instead of a new one. Write it
  at the grain he acts on, not the sender's.
- `board clear-action --card C [--operation TOKEN]` → the completion receipt after handling an Action;
  `board action-fail --card C [--text TXT] [--operation TOKEN]` → the receipt for a failure or unverified outcome.
- `board archive --card C` → **trashes** the card (recoverable ~30 days). Only for a mistaken or duplicate
  card, never for completion.

### The daily log

`board daily --type '🚫 Unsubscribe'|'✅ Done'|'✉️ Draft'|'ℹ️ FYI' --subject S --account <label> [--detail D]`
— only where a daily-log database is configured; otherwise the FYI is simply marked processed.

The board holds what is live (`🔍 Researching` = queued or active agent work, `⏳ Waiting` = waiting for
mail, time or an external condition, `⏸ Needs you` = his required move, including approval of a
necessary draft) and `✅ Done` keeps finished items as a record. Pure FYI events go to the daily log.
