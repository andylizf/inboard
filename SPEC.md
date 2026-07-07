# inboard — Design Spec (v0.1)

> **inboard** is a self-hosted, open-source AI inbox agent. It watches your email, triages it, drafts
> replies, and surfaces everything that needs you as **cards on a Notion kanban board you drive** — by
> tapping an Action or leaving a comment. Nothing important falls through. Powered by **Claude Code**.

*Positioning: "Your inbox, on a board. An AI agent triages, drafts, and tracks — you just tap."*

This spec is the agreed design before Phase 1 (de-personalizing the working prototype into a config-driven
product). It formalizes the strawman: the architecture is generic; only the personal layer is stripped
and parameterized.

---

## 1. Goals / non-goals

**Goals**
- Nothing important falls through ("事事有回应"): mail is triaged near arrival and important items are
  actually *handled* (researched, drafted, tracked) — visible until truly resolved.
- Self-hosted, single-user, runs on your own machine. Your data stays yours.
- A new user gets running from a **config file + one `init` command**.

**Non-goals (v1)**
- Not a hosted SaaS. Not a full email client (it drives Gmail + Notion, doesn't replace them).
- Not yet provider-agnostic — Gmail + Notion + Claude Code, with clean seams for later providers.

---

## 2. Architecture — two engines, one board, one memory

```
        Email accounts (via an EmailProvider; v1 = Gmail OAuth)
             │
  ┌──────────┼──── ENGINE 1: pull loop ─────────────────────┐   mail → board (inbound)
  │ scheduler (launchd / systemd) every N min                │
  │   has-work precheck (no LLM): new mail? pending Action?   │
  │     stale-awaiting card? → else skip (cheap)              │
  │   Claude Code (-p) runs the pipeline (agent/CLAUDE.md):   │
  │     triage → classify → dedup → route / card / draft      │
  └──────────┬───────────────────────────────────────────────┘
             ▼
   📋 Kanban board (BoardProvider; v1 = Notion)  +  audit log
             ▲
  ┌──────────┼──── ENGINE 2: webhook ───────────────────────┐   your tap → agent acts (interactive)
  │ webhook server → comment / action handlers               │
  │   you tap an Action chip or comment on a card →           │
  │   Claude Code (-p, /goal) works THAT card to resolution   │
  └──────────┬───────────────────────────────────────────────┘
             ▼
            You (board on phone / web)
```

**Board.** One card per matter. Properties: `Subject` (scannable title), `Sender`, `Account`, `Status`,
`NeedsYou`, `Draft`, `Action` (tappable), `Subscription`, `MsgID`. Statuses: `📥 新` `🔍 研究中`
`✍️ 草稿就绪` `⏳ 等回复` `✅ 完成` `🚫 已退订`. A `📥 新` card with a filled `NeedsYou` = "decide this".

**Memory (3 layers).** Own seen-ledger (`processed.json`), per-card session, and a cross-session memory
store (learned preferences/facts, injected each run, extracted after). See §7 on the memory backend.

---

## 3. Required stack — batteries-included, with seams

| Layer | v1 implementation | Future seam (interface) |
|---|---|---|
| **Agent runtime** | **Claude Code** (hard dependency — it provides the headless agent + tools + skills + MCP) | — |
| **Email** | **Gmail** (OAuth, via a `gws`-style CLI) | `EmailProvider` (IMAP / other) |
| **Board** | **Notion** (via the board CLI; DB created by `init`) | `BoardProvider` (Linear / Trello / GitHub Projects) |
| **Secrets** | **cred broker** — an EXTERNAL dependency the user sets up (a socket daemon that injects secrets, never exposing them); documented, not bundled | `SecretBackend` (env / OS keychain) |
| **Memory** | **omem** — EXTERNAL, documented (or a bundled `file` no-sync default) | `MemoryBackend` (file / none / omem) |

Everything except Claude Code is behind an interface; v1 ships one implementation each. New providers are a
later phase, not a v1 blocker.

---

## 4. Config — everything personal lives here

`inboard.config.yaml` (nothing personal hardcoded in the agent):

```yaml
identity:
  name: "Your Name"          # how the agent addresses you / signs drafts
  timezone: "America/New_York"

accounts:
  - id: personal
    provider: gmail
    address: "you@gmail.com"
  - id: work
    provider: gmail
    address: "you@org.edu"
    calendar: false          # e.g. this account has no Calendar scope

board:
  provider: notion
  database_id: "<created by inboard init>"
  token_env: NOTION_TOKEN

schedule:
  pull_interval_seconds: 300
  stale_awaiting_days: 3

preferences:                 # user-editable DEFAULTS; nuanced/learned prefs live in memory
  calendar_events: propose   # propose | auto | off   (see decision B — default: propose)
  ci_notifications: noise
  unsubscribe: conservative

secrets:  { backend: cred }  # cred | env | keychain
memory:   { backend: omem }  # omem | file | none
```

---

## 5. Repo layout

```
inboard/
  bin/                     # CLIs: inboard, board, email, browser, mail-images, has-work, cfg
  lib/                     # ibconfig.py — config loader + canonical board schema
  engines/                 # inbox-agent.sh (pull loop), webhook-server.py, {comment,action}-handler.sh
  agent/
    CLAUDE.md              # lean standing orders (loaded every run)
    .claude/skills/        # web-tasks, cred-login, email-images (auto-discovered by Claude Code)
  setup/
    init.sh               # the `inboard init` wizard
    create_board.py       # parameterized Notion DB creator
  inboard.config.example.yaml
  DESIGN.md  SPEC.md  README.md  LICENSE (MIT)
```

---

## 6. De-personalization map (prototype → inboard)

| Personal today (morning-briefing) | → in inboard |
|---|---|
| Names, email addresses | `config.identity`, `config.accounts` |
| Notion board id + token | `config.board`, env |
| Absolute machine paths (`/Users/andyl/…`) | install-dir-relative / configurable |
| Domain-specific prefs (school/visa/specific senders) | removed from CLAUDE.md; user `config.preferences` + learned memory |
| cred broker personal setup | bundled component + `init` sets it up |
| omem personal store | optional `MemoryBackend` |

---

## 7. Memory backend (informed by the sync discussion)

v1 ships an omem-style git-synced markdown store as the default `MemoryBackend`, because markdown+git keeps
memories human-readable and grep-able. Known limitation (documented, deferred to v2): concurrent
multi-machine sync can conflict. The clean fix identified: **(a) machines write append-only, a single
consolidate pass is the only mutator (kills content conflicts); (b) use `jj` for the push/sync layer so an
interrupted rebase self-heals instead of wedging.** v1 targets single-machine use where this doesn't bite;
the interface lets a `file` (no-sync) or hardened backend drop in later.

---

## 8. Setup flow — `inboard init`

1. Ask identity + timezone.
2. Connect Gmail account(s) via OAuth.
3. Create the Notion kanban database (`setup/create_board.py`) → write `database_id` to config.
4. Choose + set up the secret backend (cred by default; wizard bootstraps the cred daemon).
5. Write `inboard.config.yaml`; install the scheduler (launchd on macOS / systemd on Linux).
6. Smoke-test one cycle end-to-end.

---

## 9. Phasing (this is multi-session)

- **Phase 1 — de-personalize + config-ify.** Turn the working prototype into a config-driven `inboard`
  that a new user runs from a config + `init`. All PII/personal → config. *This is the foundation and the
  first push to the (private) repo.*
- **Phase 2 — provider seams + backends.** Extract `EmailProvider` / `BoardProvider` / `SecretBackend` /
  `MemoryBackend` interfaces (still one impl each), harden secrets/memory.
- **Phase 3 — packaging + polish.** `init` wizard, cross-platform scheduler, docs, tests; distribution
  (git-clone+init for v1 → brew/npm/docker later). Flip the repo public.

---

## 10. Decisions locked / open

**All locked (2026-07):**
- Name **`inboard`**; **Claude Code** as a hard dependency; **MIT** license.
- **Platform: macOS only for v1** (launchd; Linux/systemd is a later phase).
- **Distribution: `git clone` + `inboard init`** for v1 (a packaged installer — brew/npm/docker — is later).
- **cred + memory (omem) are EXTERNAL dependencies, DOCUMENTED, not bundled** — inboard requires them present and talks to them via the `SecretBackend` / `MemoryBackend` interfaces (a `file` no-sync memory backend ships as the zero-setup default).
- **Board: Notion-only for v1** (the `BoardProvider` seam exists for later providers).
- Repo starts **private**, flips **public** after Phase 1 de-personalization.
- Calendar-events default = **`propose`** (decision B).
