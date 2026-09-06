# Waiting and wakeups implementation plan

**Goal:** Keep unfinished matters open, and resume their card agents when a scheduled check or matching mail arrives.

**Architecture:** Retain the existing semantic mail subscription and per-card worker. Add explicit, independently identified time triggers to each card, with a derived next-check date and readable schedule. A cheap sweep runs before mail triage, delivers due triggers, and retains them until the worker acknowledges completion. Due remains a deadline. Waiting covers replies, time and external recovery; done, expired and cancelled are separate outcomes.

**Tech stack:** Existing Python standard library, Bash runners, Notion API and Claude daemon delivery; locked dependencies unchanged.

1. Extend `bin/board` and `lib/ibconfig.py`: schedule/read/cancel/ack commands, trigger storage, unified waiting display and cancelled status. Clear future triggers on every terminal write, including upsert. Add synthetic lifecycle tests.
2. Add `lib/wakeups.py` and `engines/wake-sweep.py`. Resume the existing worker, group simultaneous triggers per card, persist delivery receipts, retry unacknowledged work after a dead worker, and skip cards with pending operator actions. Hook both pull runners before the mail precheck. Test failure, restart, edited cards, cancellation and multiple triggers.
3. Replace the fixed stale reminder and Lapses close paths. Due sweep only flags overdue obligations. Update directory-scoped instructions and user documentation: reconcile all triggers after every event, check external conditions through a named source, and distinguish incomplete, completed, expired and cancelled matters.
4. Add a resumable deployment migration. Save schema, config and complete page properties before mutation; add wake properties, rename the existing waiting option by id, transfer old Lapses meaning into explicit review triggers, and queue existing waiting cards for one planning pass. Remove Place/Lapses only after backup and per-card checkpointing. Keep all private snapshots and logs outside version control.
5. Run synthetic tests and shell checks, then smoke-test an isolated live card. Deploy the reviewed commit, migrate the live board, and verify a completion receipt from an agent resumed by a scheduled trigger. No email is sent by the migration or smoke test.

Completion: automated checks pass, deployment matches the commit, the live schema has the agreed fields/statuses, and the test card records an acknowledged wakeup. Logs and backups live under the deployment's `logs/waiting-migration-*` directory.
