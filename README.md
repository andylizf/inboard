# inboard

**Your inbox, on a board.** A self-hosted AI inbox agent that watches your email, triages it, drafts
replies, and surfaces everything that needs you as cards on a **Notion kanban board you drive** — by
tapping an Action or leaving a comment. Nothing important falls through. Powered by **Claude Code**.

> 🚧 Early / pre-release. See [`SPEC.md`](./SPEC.md) for the design and [`DESIGN.md`](./DESIGN.md) for the
> architecture. Currently being de-personalized from a working single-user prototype.

## How it works (one glance)
Two engines around one board:
- **Pull loop** (every few minutes): reads your mail, triages, classifies, and drafts/tracks the important
  ones as cards.
- **Webhook**: you tap a card's Action or comment on it → the agent acts on that card until it's resolved.

Notion is the only surface — you drive everything from the board on your phone or the web.

## Status
Building in phases (see `SPEC.md` §9): (1) de-personalize + config, (2) provider seams, (3) packaging +
setup wizard + docs. License: MIT.
