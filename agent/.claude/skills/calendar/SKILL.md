---
name: calendar
description: How a concrete date on a matter reaches the operator's calendar, and what each preferences.calendar_events setting does. Load this the moment a date becomes concrete on a card, including a date that surfaced out of your own research rather than out of the mail.
---

## Calendar events
A calendar-worthy date is any concrete date/time the operator must act on, WHENEVER it becomes known — in
the mail itself, or only later, out of your research, a comment exchange, or a decision made on the card.
A date that surfaces mid-work does not look like "a mail with an event", which is exactly how it gets
missed: the test is the matter having a date, not the mail carrying one. The moment the date is concrete,
follow `cfg preferences.calendar_events`:
- `propose` (default) → put the parsed date/time/details in `NeedsYou` so the card reads as wanting him,
  and add it to the calendar only once he says yes. This is the one place the don't-ask default does not
  apply: he set this preference, so asking IS handling the matter under it. A card holding a date with
  nothing in `NeedsYou` is an unfinished step, and nothing else will catch it.
- `auto` → add the event yourself right then with `gws calendar` (`email <account> gws calendar --help`
  for the events subcommand and its fields), and write one line on the card saying it is on the calendar
  (📌 note or log). A card carrying a date with no such line is an unfinished step.
- `off` → don't touch the calendar.
