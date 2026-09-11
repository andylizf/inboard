---
name: calendar
description: Create and reconcile calendar entries for a card. Load when a relevant date becomes concrete, when editing a linked event, or when new facts change whether an existing reminder is needed, including completion or cancellation. Covers preferences.calendar_events and obsolete reminders.
---

## Calendar events
A calendar entry represents the operator's attendance, an action or deadline he needs to track, or an
entry he explicitly requested. An agent's own check or wait belongs in `board schedule`; a date alone
does not justify a calendar entry. Apply this test to dates learned from mail, research or card updates,
then follow `cfg preferences.calendar_events` for an eligible entry:
- `propose` (default) → put the parsed date/time/details at the start of Summary and set `needs_you`,
  and add it to the calendar only once he approves those details. This is the one place the don't-ask default does not
  apply: he set this preference, so asking IS handling the matter under it. An eligible entry with
  no approval request in Summary is an unfinished step, and nothing else will catch it.
- `auto` → add the event yourself right then with `gws calendar` (`email <account> gws calendar --help`
  for the events subcommand and its fields), and write one line on the card saying it is on the calendar
  (📌 note or log). An eligible entry with no such line is an unfinished step.
- `off` → don't touch the calendar unless the operator requests a specific correction.

## Reconcile existing reminders
When the matter changes, read its linked event and check whether the operator still needs that reminder.
Under an enabled calendar preference, remove an agent-created task reminder once its action is verified
complete, cancelled or unnecessary. An explicit correction request also authorizes removal of its named
obsolete reminder. Save the event's original details
and id in the card log before removal, then read back its cancelled or absent state and record the result.
Do not keep its time slot and notification by renaming it to say that nothing needs doing. Keep the
outcome on the card and any remaining agent checks in `board schedule`.

Establish ownership from the recorded event-creation result, or use the operator's explicit correction
request for the named event; a linked event id alone does not prove who created it. Preserve unrelated
events, and do not delete a recurring series to remove one occurrence. A real appointment, a remaining
deadline or an informational entry the operator explicitly requested stays while still relevant.
State recommendations as recommendations; a calendar title must not tell him what he ought to choose.

These preferences cover his own calendar entries. Inviting attendees or registering with an organizer
is a separate outward action under `card-actions`; a calendar entry does not establish registration.
Before reporting an entry created or changed, read it back and record its time, timezone and link on the card.
