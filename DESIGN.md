# inboard — Design

Self-hosted proactive inbox agent: headless **Claude Code** + Gmail (the `email` CLI) + Notion (the
`board` CLI) + a scheduler (launchd). **The board is the only human surface** — no chat, no separate app.
This doc is the architecture and the *why* behind the rules. The operating orders live in
`agent/CLAUDE.md` (lean, loaded every run); situational procedures live in `agent/.claude/skills/*`
(loaded on demand). Nothing personal is hardcoded — it all comes from `inboard.config.yaml` (see
[`SPEC.md`](./SPEC.md) §4).

## Goal
Nothing important falls through. Mail is triaged near arrival and the important ones are actually
*handled* (researched, drafted, tracked) — and every matter you're tracking stays visible until it's
truly resolved.

## Architecture — two engines, one board, one memory

```
        Email accounts (EmailProvider; v1 = Gmail via the `email` CLI, one per config account)
             │
  ┌──────────┼──────── ENGINE 1: pull loop ────────────────┐   mail → board (inbound)
  │ scheduler every N min → engines/inbox-agent.sh           │
  │   has-work precheck (no LLM): new inbox mail? pending    │
  │     Action? stale-awaiting card? → else skip (cheap)     │
  │   claude -p runs the pipeline (agent/CLAUDE.md §B):      │
  │     triage → classify → dedup → route/card/draft/unsub  │
  └──────────┬───────────────────────────────────────────────┘
             ▼
   📋 Notion board  (card = one matter)   +   📓 daily log (optional audit)
             ▲
  ┌──────────┼──────── ENGINE 2: webhook ───────────────────┐   your tap → agent acts (interactive)
  │ engines/webhook-server.py → comment / action handlers    │
  │   you tap an Action chip or comment on a card →          │
  │   claude -p (with /goal) works THAT card to resolution   │
  └──────────┬───────────────────────────────────────────────┘
             ▼
            You (board on phone / web)
```

**Board.** One card per matter. Properties: `Subject` (a scannable one-liner title), `Sender`, `Account`,
`Status`, `NeedsYou` (what *you* must do / the open question), `Draft`, `Action` (the tappable chip that
fires engine 2), `Subscription` (natural-language "which follow-up mail belongs here"), `MsgID`, plus
internal `Session` / `StepBlocks`. **Statuses (6):** `📥 New` · `🔍 Researching` · `✍️ Draft ready` ·
`⏳ Awaiting reply` · `✅ Done` · `🚫 Unsubscribed`. A `📥 New` card with a filled `NeedsYou` = "decide this".
The canonical status/action names live in `lib/ibconfig.py`, so the board creator, the `board` CLI, and
`agent/CLAUDE.md` cannot drift apart.

**Memory (3 layers).**
- `state/processed.json` — the agent's own *seen-ledger* (id → status). This, NOT Gmail's read flag,
  defines "handled".
- Per-card Claude session (`--resume`) — each card remembers its own thread across triggers.
- **Memory backend** (`cfg memory.backend`) — durable cross-session preferences/facts. Default `file`
  (zero-setup, local markdown); `omem` (a git-synced store, an external dependency) or `none` are also
  selectable. Whatever an agent *says* it recorded, the backend is where a preference actually lands.

**What goes where.** The three layers are separated by **lifespan**, not by content type. A session is
working memory and is meant to be thrown away; a card is its matter's short-term store and dies with the
matter (`✅ Done`, or `Due` passing); the memory backend holds facts that outlive any single matter and are
read by other sessions on other machines. So the routing question for any fact is *would this still matter
if this card did not exist?* — no, and it belongs on the card; yes, and it belongs in the backend. A
decision usually lands in both, written differently: the card records the transaction, the backend records
the resulting state of the world.

That is also why a card body is a **maintained document rather than a transcript**. The 📌 note is the
layer an agent reads to reconstitute itself after its session is discarded, so it carries a size cap and
is rewritten in place; the append-only log underneath is unbounded. The published guidance on agent
context converges on the same split — a per-task notes file for state tied to one task, a durable store
for what is reused across tasks, and never one artifact doing both jobs, because the two have different
capacities and different failure modes.

## Engine 1b — dispatch (opt-in, `agent.dispatch`)

Engine 1 runs one session over the whole batch, and that stops scaling before the mail does: a
101-message cycle opened 14 bodies, because "read every message" is unaffordable at that volume and the
agent silently classifies from headers instead. Dispatch restores the rule rather than suspending it.

```
  phase 1  DISPATCHER — the daily rolling session, the only agent that is not a card.
           Headers + `board subscriptions` only, never a body. Groups the batch into MATTERS,
           routes each (existing card / new / noise), emits a JSON plan. Also owns anything
           cross-card, since no card agent can see past its own matter.
  phase 2  CARD AGENTS — one per dispatched matter, in parallel, each resuming that card's own
           `Session` so the matter keeps its working memory across cycles. Reads only its own bodies.
```

**Grouped by matter, never by message.** Grouping happens before any hand-off, so the cross-message view
survives: 73 copies of one CI notification collapse because a single agent saw all 73. Split per message
and each agent is blind to the other 72.

**The shell owns `state/processed.json`, not the agents.** N agents writing one ledger would clobber each
other, and "was this handled" is a fact about an exit code — deterministic, so it belongs in deterministic
code. A dispatched group is marked only after its agent exits 0, so a crashed agent leaves its mail
unprocessed and the next cycle retries it. For the same reason the success watermark advances only when
the dispatcher *and* every group succeeded: it is the signal the liveness watchdog reads as "mail is
actually being handled", and advancing it after a failed cycle would hide the outage.

## Autonomy principle
Act autonomously on everything **except** what genuinely spends resources or is irreversible /
outward-facing — those are gated on *your approval* (but then agent-executed, not handed back).
- **Auto:** read mail/calendar, research, classify, label, save Gmail **drafts**, One-Click unsubscribe,
  update the board, drive a browser, log in via the secret broker.
- **Gated (approval → then the agent does it):** **sending** email, spending money, destructive deletes,
  any irreversible/final submit, and **auth/account-change confirmation links** (auto-confirming one could
  complete an account takeover). The gate is your *approval*, not your *hands*. The `email` wrapper
  physically blocks sends, so "drafts only" is enforced by the tool, not just the prompt.

## Key mechanisms — and why
- **Webhook events never echo the integration's own writes** (verified: an unsigned probe POST is
  logged instantly; a board-CLI write produces no event at all). *Why it matters:* engine 2 fires on
  the operator's edits only — engine-side code must never wait for a webhook echo, and a quiet
  webhook log during heavy agent activity is normal, not an outage.
- **Sessions expire; transcripts don't.** A session past `session_rotate_kb`, or idle past
  `session_max_idle_days`, is invalidated: the next touch starts fresh (told, via prompt, that it is
  a successor and that the card holds the surviving memory), while the old transcript stays on disk
  as history. *Why it matters:* rotation exists to shed stale working memory; deleting would also
  destroy the audit trail. Mind the host: Claude Code's own retention sweep (`cleanupPeriodDays`,
  default 30 days) deletes idle transcripts wholesale — a deployment that wants its history must
  raise it in `~/.claude/settings.json`.
- **Every per-card prompt says the agent is mortal.** The session can die mid-matter (turn cap,
  crash, rotation), so prompts instruct writing state to the card as it is learned, never only at
  the end. *Why:* a send once died at its turn cap with everything held in conversation — the
  operator saw nothing for three days.
- **Scan read *and* unread** (`in:inbox newer_than:2d`, diffed against `processed.json`), not `is:unread`.
  *Why:* you often read a mail before the next cycle; keying on Gmail's read flag made those invisible.
  The seen-ledger is the source of truth.
- **A reply to YOU is always important, never noise** (detected via `In-Reply-To`/`References` or a
  same-thread message from an address you own). *Why:* a 1-to-1 reply from an unknown/informal sender was
  being dumped as noise.
- **See images** via the `email-images` skill. *Why:* `+read` is text-only; a mail whose content is a
  figure/screenshot looked empty and risked being called noise.
- **Dedup: subscriptions + search.** Before creating a card, check `board subscriptions` (active matters)
  and, if the sender/subject looks familiar, `board search` (ALL cards incl. `Done`). *Why:* route a
  follow-up onto its existing card instead of spawning duplicates.
- **`⏳ Awaiting reply` + stale sweep.** "Sent my part, awaiting their reply" keeps a subscription (so the
  reply routes back) instead of going `Done`. A per-cycle `board stale-awaiting` resurfaces any card
  with no reply for N+ days. *Why:* a sent-but-unanswered matter must not rot silently.
- **A reply that resolves an OPEN card must flip it to `✅ Done` on the board** (not just the audit log).
  *Why:* a card you were tracking as unfinished must visibly close so Notion pushes it to you.
- **Deterministic comment dedup** (engine 2). The shell checks the newest comment's author *before*
  invoking the LLM: if it's our own bot reply (a self-triggered/duplicate webhook) → skip silently, no
  LLM, no output; only a *human's* newest comment invokes claude. *Why:* Notion re-delivers webhooks
  (`attempt_number`), and a naive agent mis-dismisses real questions as "duplicates".
- **Cheap precheck before the LLM** (`bin/has-work`): a no-LLM query for new mail / pending Action /
  stale card. Empty cycles never spend a Claude run. *Why:* the scheduler fires often; most cycles are empty.

## Progressive disclosure — skills
Situational procedures are `agent/.claude/skills/*/SKILL.md`: their *descriptions* are always in context
(cheap) and the *body* loads only when the situation matches.
- **`web-tasks`** — drive the real headed Chrome (`browser` CLI: snapshot/fill/click/eval, screenshot at
  every checkpoint, re-snapshot after reloads).
- **`cred-login`** — get past a login wall with the secret broker (the secret never enters context); the
  broker's progressive-disclosure model + the `$CRED`-must-go-to-a-shell gotcha.
- **`email-images`** — fetch + view an email's images (`mail-images`).

## Components
- `lib/ibconfig.py` — config loader (PyYAML, uv-managed) + canonical board schema (statuses/actions/daily types).
- `engines/inbox-agent.sh` — engine-1 runner; `engines/_common.sh` bootstraps env (paths, PATH, `.env`, proxy).
- `engines/webhook-server.py` + `comment-handler.sh` + `action-handler.sh` — engine 2 (Notion → agent).
- `agent/CLAUDE.md` — the agent's lean standing orders. `agent/.claude/skills/*` — on-demand procedures.
- `bin/board` — the Notion board/log CLI (upsert/search/awaiting/stale-awaiting/done/reply/comments/…).
- `bin/email` — the send-guarded per-account Gmail wrapper. `bin/mail-images` — email image fetcher.
  `bin/browser` — agent-browser wrapper. `bin/has-work` — the no-LLM precheck. `bin/cfg` — config reader.
- `bin/inboard` — top-level entry (`init` / `run` / `webhook` / passthroughs).
- `setup/create_board.py` — parameterized Notion DB creator. `setup/init.sh` — the setup wizard.
- `state/`, `logs/`, `.env`, `inboard.config.yaml` — runtime + secrets (all git-ignored).

## Seams for later (see SPEC §3)
Everything except Claude Code sits behind an interface — `EmailProvider` (Gmail today), `BoardProvider`
(Notion today), `SecretBackend` (cred today), `MemoryBackend` (file/omem). v1 ships one implementation
each; new providers are a later phase, not a blocker.

## Not here (deliberately)
- No chat/notification surface — the board is the surface.
- Not a hosted SaaS, not a full email client — inboard drives Gmail + Notion, it doesn't replace them.


## One matter, one card, one agent — and why it is shaped this way

Moved out of `agent/CLAUDE.md` on 2026-09-04. It explains the design rather than telling an agent what
to do on a turn, and it was being re-read by every card agent on every run.

One matter is one card, for the life of the matter. One card is one agent, whose name is the card's own
id (`inboard-card-<32 hex>`), so the mail that arrives on a matter in October reaches the same agent that
worked it in July. Above both sits **one dispatcher session per day**, the only agent that is not a card:
it reads the new mail, decides which matter each piece belongs to, and hands off. It does not develop a
matter itself — deciding *where* something goes and deciding *what to do about it* are different jobs, and
the second one belongs to whoever already holds the history.

That agent is not immortal, and being replaced is normal rather than a failure. In the shell path a
transcript that outgrows `agent.session_rotate_kb`, or sits idle past `agent.session_max_idle_days`, is
retired, and **the successor is told so, and told which card it inherits** — the alternative is worse than
starting cold, because it would read the card as a fresh matter and quietly re-decide questions its
predecessor had already settled there. Under `agent.delivery: daemon` those two thresholds do not decide
anything: the daemon keeps one worker per agent name, and the session lasts exactly as long as that worker.
A worker that was reaped, or a daemon that restarted, means the next delivery spawns a cold agent — with no
notice, because nothing measured a transcript to trigger one.

So do not read the card's `Session` as a promise of continuity. It records where the run happening NOW is,
for whoever needs to find that transcript; it does not tell you whether you are that run's continuation.
`PastSessions` holds the ones before it, oldest first — overwriting `Session` is what keeps it pointing at
something live, and appending to `PastSessions` is what stops the earlier transcripts becoming unreachable,
since they sit on disk named only by that id. **The
card body is what tells you, and it is the only thing that does.** Read the 📌 note and the log before
acting on any matter you do not remember working — and if you do not remember it, assume you are new to it,
whatever the card's `Session` says.

So, concretely, when you begin a turn:

- **A notice says you are a fresh session taking over card X.** Everything the previous agent knew is gone
  and the card is all that survived. Read the card fully — the 📌 note first, then the log — before you
  touch anything, and continue from where it says the matter stands. Do not re-derive; do not contradict.
- **No notice.** You are the same agent that worked this card before, with your own history intact. The
  card is still the record, but you are not starting cold.

Either way the card id is in your prompt. It is the only durable name you have: your session can end
between any two tool calls, but the card is still there afterwards, which is why anything worth surviving
goes onto the card at the moment you learn it, not at the end of the run.

**Worked example — the ICBC card.** July 29: mail from the bank asks for compliance details. A card opens,
its agent researches, drafts a reply, and sets a Subscription saying it now awaits the bank's answer.
September 1, five weeks later: the bank replies in the same thread. The dispatcher sees a thread the card
already tracks, routes it there rather than opening a second ICBC card, and hands it to that card's agent —
which reads its own July notes, appends what changed (account converted, a $15 monthly fee now accruing,
two new compliance questions), rewrites the 📌 note, and sets the card back to needing the operator. One
matter, one card, five weeks apart, and nothing had to be reconstructed.

**The same example, gone wrong in three ways worth recognising:**

- *A second card.* The reply is treated as new mail about a new subject, so the board now shows two ICBC
  cards and neither one tells the whole story. The Subscription exists to prevent exactly this.
- *A stranger writing on the card.* The dispatcher appends the update itself instead of handing off. The
  line lands on the right card, so it looks fine — but the agent holding five weeks of context on that
  matter never learns its reply arrived, and the next thing it does is act on a stale picture.
- *A silent append.* The update lands and nothing about the card's appearance changes, because it was
  already in the same column. It is on the board and still effectively invisible. `board log` and
  `board edit` stamp `Updated` for this reason; a matter that moved today must be distinguishable from
  thirty that have not moved in weeks.

**Card or memory? One test: would this fact still matter if this card did not exist?**
- **No → the card.** What has been done, what is being waited on, the draft text, thread ids, research
  notes, the next step. It dies with the matter, and that is correct.
- **Yes → memory.** Facts about the world that outlive this matter: who a counterparty is and what they
  are responsible for, an account id, a policy, a decision other matters will cite. Other sessions read
  these long after the card they came from is gone.
- **A decision usually goes to BOTH, written differently.** The card records the transaction — "they
  offered A or B, we chose B on <date>". Memory records the resulting state of the world — "this
  project's storage plan is B".

**The 📌 note is capped; the log is not.** Keep the note under ~1500 characters and REWRITE it: when it
is full, delete what no longer decides anything instead of appending. The cap is what forces that edit —
without one the note quietly becomes a second log and stops being readable in one pass, which is the only
property that made it worth writing. Detail you cannot bear to delete goes to `board log`, which is
append-only and unbounded on purpose.

