# inboard

**Your inbox, on a board.** A self-hosted AI inbox agent that watches your email, triages it, drafts
replies, and surfaces everything that needs you as cards on a **Notion kanban board you drive** — by
tapping an Action or leaving a comment. Nothing important falls through. Powered by **Claude Code**.

> 🚧 Early / pre-release, single-user, macOS-only for v1. See [`DESIGN.md`](./DESIGN.md) for the
> architecture and [`SPEC.md`](./SPEC.md) for the design decisions.

## How it works

Two engines around one board:

- **Pull loop** (every few minutes): reads your mail across every configured account, triages, classifies
  noise vs. important, dedups against what it's already tracking, and for each important item either drafts
  a reply or opens a card asking you to decide. A cheap no-LLM precheck skips empty cycles.
- **Webhook**: you tap a card's **Action** chip or **comment** on it → the agent picks up *that* card and
  works it to resolution (research, redraft, follow up), replying in the card's thread.

Notion is the only surface — you drive everything from the board on your phone or the web. The agent
**never sends mail**: it saves Gmail drafts and you send. Irreversible or account-changing actions are
gated on your approval, then executed for you.

### The board

One card per matter, with a scannable one-line `Subject`, the `Draft`, `NeedsYou` (what you must decide),
and a tappable `Action`. Statuses:

`📥 New` → `🔍 Researching` → `✍️ Draft ready` → `⏳ Awaiting reply` → `✅ Done` (· `🚫 Unsubscribed`)

A `📥 New` card whose `NeedsYou` is filled is the "decide this" signal. `⏳ Awaiting reply` keeps a
subscription so the other party's reply routes back to the same card; a per-cycle stale sweep resurfaces
anything that's gone quiet too long.

## Requirements

- **macOS** (launchd). Linux/systemd is a later phase.
- **[Claude Code](https://docs.claude.com/en/docs/claude-code)** (`claude`) — the agent runtime (hard dependency).
- **[uv](https://docs.astral.sh/uv/)** — manages the Python venv (`brew install uv`).
- **[google-workspace CLI](https://pypi.org/project/google-workspace-cli/)** (`gws`) — reads Gmail; authenticate each account before first run.
- A **Notion** account + an internal integration token, and a page shared with it (the board is created under it).
- *Optional:* a secret broker (`cred`) for logins behind walls, and `agent-browser` for web-task cards.

## Quick start

```sh
git clone https://github.com/andylizf/inboard && cd inboard
uv sync                 # create the venv + install deps
./bin/inboard init      # wizard: identity, accounts, Notion token → creates the board + config + launchd
```

`inboard init` walks you through your name/timezone, each mail account, and your Notion token; creates the
kanban database under a page you've shared with the integration; writes `inboard.config.yaml` + `.env`; and
installs the pull-loop launchd job. Then, for instant reactions to taps/comments, run the webhook engine
behind a tunnel and register its URL in your Notion integration:

```sh
./bin/inboard webhook    # foreground; put it behind a persistent tunnel (e.g. Tailscale Funnel)
```

Useful commands: `inboard run` (one pull cycle now), `inboard board accounts`, `inboard cfg <key>`.

## Configuration

Everything personal lives in `inboard.config.yaml` (nothing is hardcoded in the code). See
[`inboard.config.example.yaml`](./inboard.config.example.yaml) for the fully-commented template —
`identity`, `accounts`, `board`, `schedule`, `agent` (model + turn budgets), `network` (optional proxy),
`preferences` (calendar / CI / unsubscribe defaults), and the `secrets` / `memory` backends. Secrets
(the Notion token) live in a gitignored `.env`.

## Layout

```
inboard/
  bin/          inboard, board, email, browser, mail-images, has-work, cfg
  lib/          ibconfig.py — config loader + canonical board schema
  engines/      _common.sh + inbox-agent.sh (pull loop), webhook-server.py, {comment,action}-handler.sh
  agent/        CLAUDE.md (standing orders) + .claude/skills/ (web-tasks, cred-login, email-images)
  setup/        create_board.py, init.sh, launchd template
  inboard.config.example.yaml   DESIGN.md   SPEC.md   README.md   LICENSE
```

## Security model

- **Never sends mail** — the `email` wrapper physically blocks every send op; the agent only saves drafts.
- **Secrets never enter the agent's context** — logins go through the secret broker, which injects the
  credential into a subprocess without exposing it.
- **Approval-gated, then agent-executed** — sending, payments, deletes, and auth/account-change links are
  never done autonomously; once you approve (a tap or comment), the agent does it for you.

## Status & license

Phased (see `SPEC.md` §9): **(1) de-personalize + config — landed**, (2) provider seams
(`EmailProvider` / `BoardProvider` / `SecretBackend` / `MemoryBackend`), (3) packaging + polish. MIT.
