---
name: twofa-gate
description: The shared gate every second factor goes through before it rings the operator's phone, including an explicit request to retry. Covers acquire, release, local cooldown and operator-authorized retries. Load this before any Duo push, SMS code, authenticator prompt or passkey tap, and whenever a login is about to need one.
---

## Second factors ring a phone — take the gate before you push one

The shared gate prevents competing verification requests from different cards.
Anything that sends a push, a code, or an approval prompt to him — Duo, an authenticator,
an SMS code, a passkey tap — goes through the shared gate first:

```sh
twofa-gate acquire <service>     # exit 0 = you hold the only outstanding push; exit 1 = do NOT push
… attempt the login …
twofa-gate release <service> ok        # he answered
twofa-gate release <service> timeout   # he did not — this blocks everyone for a cooldown
```

**Release on every exit, including an error.** A push you never resolved holds the gate against every other
card until it expires on its own (10 minutes), and until then they all stop. "He did not answer" means the
page stopped waiting — a timed-out prompt, an expired transaction — not that you grew impatient.

When the operator explicitly asks to retry this verification, log the authorizing comment or request
and use `twofa-gate acquire <service> --operator-retry` for one new attempt now. Do not reuse that
authorization for another attempt. This skips only the local cooldown; another outstanding verification
still blocks it. A service's actual lockout or rejected credential remains a separate blocker: report
that evidence rather than calling a local timer a service restriction. Never reset shared state or
claim a successful release to obtain permission.
If your own previous challenge is still pending, abandon that challenge and release it honestly before
starting the authorized replacement. Do not release a verification owned by another task.

Without a fresh operator request, a blocked gate means stop, not wait and retry. Record the observed
reason and the operator step needed; do not schedule a later push just because the cooldown will expire.
If another verification is outstanding, identify it and keep this task pending without starting a
competing push. Release honestly: `ok` only after confirmed completion, `timeout` after the challenge
expires or is abandoned. A page still showing a number does not prove its old notification is valid.
After the operator confirms, continue the task now; do not postpone the result to the next daily review.
