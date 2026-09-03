---
name: human-gate
description: What to do when something only the operator can clear is blocking a card and it is not on the card itself — a locked credential, a server-side hold. Load this the moment you are blocked off-card. Covers the background readiness probe that notifies you, and the case where no safe probe exists and polling would cause a lockout.
---

## HUMAN GATE → spawn a run_in_background wait, then END your turn (you get auto-notified when it clears)
When you hit something only the operator can clear OFF-card (a locked credential, a server-side hold that must
clear, etc.), do NOT foreground-wait (in `-p` a Bash sleep-loop re-bills your whole context every few minutes)
and do NOT end with a bare "can't". Instead:

**A. There IS a cheap, SAFE readiness signal** — a one-line shell check that confirms it WITHOUT doing the
risky op (a login retried on a timer = account LOCKOUT, so NEVER poll that):
1. `board reply --card <id> --text '<exactly what the operator must do — e.g. approve the credential fetch / the 2FA push>'`
2. Spawn ONE Bash with `run_in_background: true` that polls the signal with its OWN ~30-min timeout, so it always completes and notifies you:
   ```
   for i in $(seq 30); do <cheap probe> && { echo READY; exit 0; }; sleep 60; done; echo TIMEOUT; exit 1
   ```
3. End your turn with one line: "Parked — I'll be auto-notified the moment `<X>` clears, or after 30 min."
4. When the notification arrives, read the background output: `READY` → continue the task from where you were
   (do the real step; if it was a login, enter the credentials NOW, once). `TIMEOUT` → `board reply` that it's
   still blocked and stop.

**B. There is NO cheap safe signal** (e.g. a WRONG password — you can't test it without a login attempt =
lockout risk): do NOT poll. `board reply` the exact fix AND "after you fix it, re-pick the Action on this card
and I'll retry." Then stop — re-picking the Action re-triggers action-handler, which `--resume`s your session
with full context. Never retry a login/2FA on a timer.
