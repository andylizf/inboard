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
