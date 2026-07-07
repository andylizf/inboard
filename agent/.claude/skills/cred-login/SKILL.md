---
name: cred-login
description: Fetch a saved login/password and get a site past a login wall using the `cred` broker — the secret NEVER enters your context. Load this the moment `browser` pauses on a login page, or whenever you need any saved credential. Covers cred's progressive-disclosure model, item-scoped unlock, and the $CRED-must-go-to-a-shell gotcha.
---

Need a saved login/password? Use the **`cred`** broker (the secret backend configured for this deployment) — run **`cred help`** first; it carries its own rules and is the ONLY way you may touch a secret. Never handle a password any other way.

**Getting a site past a login wall** (`browser` pauses on login pages):
1. `cred find <site>` → item id + the real login URL (a bare domain often redirects when logged-out; use the saved URL).
2. Log the site in via the broker (password never enters your context). The `browser` Chrome ALREADY exposes CDP on `127.0.0.1:9223` — do NOT start a second Chrome; act on the SAME session. Fill the login form's fields, reading any captcha from a `browser screenshot`.
3. Go back to `browser` — the session is now established in the same Chrome, so it sails through.

**cred is PROGRESSIVE-DISCLOSURE — trust it, don't fight it.** Run `cred with <id> -- <cmd that literally uses $CRED>` plainly and READ its FULL output — NEVER `grep`/filter it away, that's where the instructions are. It self-guides: it will either prompt the operator to approve the fetch (let it WAIT — do NOT wrap it in a `timeout` that kills the approval) or print the exact next step (e.g. `cred unlock <id>`). Just do what the message says; don't re-derive the model, don't add timeouts. When you relay an unlock to the operator, pass the EXACT id — a session-wide `cred unlock` does NOT authorize a fetch (it silently hangs → dies on timeout); only an item-scoped `cred unlock <exact id>` does (fuzzy names mis-match).

**The $CRED-shell gotcha (cost a whole session once):** `cred with -- <cmd>` runs <cmd> DIRECTLY (no shell), so `$CRED` only expands if <cmd> IS a shell (or a program that reads it from the env). `cred with <id> -- browser fill @e5 "$CRED"` injects the LITERAL 5 chars `$CRED` — a wrong login that LOOKS right (the field even shows dots, then "password does not match"). ALWAYS wrap in a shell: `cred with <id> -- bash -c 'browser fill @e5 "$CRED"'`.

`cred get` prints the raw secret → HUMAN-TERMINAL ONLY; agents always use `cred with`.

> Note: `cred` is inboard's default secret backend (see `cfg secrets.backend`) — an external broker you set up
> separately, documented in the inboard README. If your deployment uses a different backend, the login step
> differs but the rule is the same: the raw secret must never enter the agent's context.
