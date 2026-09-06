# Sent follow-ups implementation plan

**Goal:** Track unfinished outgoing mail as cards and surface unanswered cards after the configured waiting period.

**Architecture:** Keep the existing dispatcher and one-card-per-matter routing. Card agents read outgoing bodies to decide whether a reply or an operator commitment remains. Extend `board stale-awaiting` to apply its existing `nudge` operation and call it from the dispatch loop.

**Tech stack:** Bash, Python standard library, existing Notion and email wrappers.

1. Update `engines/dispatcher-role.md`, `engines/dispatch.sh`, `engines/dispatch_plan.py`, and the directory-scoped `mail-pipeline` skill. Unmatched sent groups reach a body-reading agent; finished acknowledgements need no card. Deliver message direction explicitly. Waiting for another party and an operator commitment are separate outcomes. An existing memory does not replace an open todo card.
2. Extend `bin/board`'s existing stale query with `--nudge --exclude-plan`. Skip cards with incoming work, pending actions or daemon deliveries, and use the shared card lock. Re-read each candidate before writing. Log each outcome; fail the sweep on API errors so the next cycle retries. The card itself checkpoints successful nudges.
3. Call the sweep from `engines/dispatch.sh` outside dry runs, and clarify its ownership in `card-actions`. Test overdue, recent, repeated, busy and changed cards using mocked Notion calls, plus message-direction delivery. No live email is sent in tests.
4. Push the reviewed diff, fast-forward the clean deployment checkout, and verify the live read-only stale query and scheduled sweep log. Keep test logs under `logs/` and use only synthetic inputs in committed tests.

Completion: tests and shell syntax checks pass; the running checkout contains the commit; a scheduled cycle records the sweep outcome. Historical mail already marked processed is outside this change.
