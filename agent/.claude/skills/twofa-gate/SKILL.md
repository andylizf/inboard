---
name: twofa-gate
description: The shared gate every second factor goes through before it rings the operator's phone — acquire, release, and what a blocked gate means. Load this before any Duo push, SMS code, authenticator prompt or passkey tap, and whenever a login is about to need one.
---

## Second factors ring a phone — take the gate before you push one

Trying once is right. What is not survivable is several cards each trying once: you see only
your own card, so six agents behaving perfectly still ring the operator six times, and a push
nobody answers counts as a failed attempt at the far end. Princeton's security office locked
his university account over exactly that on 2026-09-01, which cost the mailbox, the VPN and
the cluster until he reset his password.

So anything that sends a push, a code, or an approval prompt to him — Duo, an authenticator,
an SMS code, a passkey tap — goes through the shared gate first:

```sh
twofa-gate acquire <service>     # exit 0 = you hold the only outstanding push; exit 1 = do NOT push
… attempt the login …
twofa-gate release <service> ok        # he answered
twofa-gate release <service> timeout   # he did not — this blocks everyone for a cooldown

**Release on every exit, including an error.** A push you never resolved holds the gate against every other
card until it expires on its own (10 minutes), and until then they all stop. "He did not answer" means the
page stopped waiting — a timed-out prompt, an expired transaction — not that you grew impatient.
```

Blocked means stop, not wait and retry: put one line on the card saying it needs him at his
phone, and end. Release honestly — reporting an unanswered push as `ok` re-opens the gate for
the next agent and rebuilds the pile-up the gate exists to prevent.
