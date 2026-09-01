---
name: cred-login
description: Fetch a saved login/password and get a site past a login wall using Bitwarden Agent Access (`aac`) — the secret NEVER enters your context. Load this the moment `browser` pauses on a login page, or whenever you need any saved credential. Covers the request-and-approval model, the shell-expansion gotcha, and what to do when the operator's listener is not running.
---

Need a saved login/password? Use **`aac`** (Bitwarden Agent Access). The vault lives on the operator's
laptop, not on this machine. You ask for one credential, they approve it there, and it comes back through
an encrypted tunnel that closes afterwards. This is the ONLY way you may touch a secret.

**Fetch by domain, into a command — never into your own output:**

```sh
aac run --domain <domain> --env-all -- sh -c '<command that uses "$password">'
```

`--env-all` puts the item's fields in the child's environment: `username`, `password`, `totp`, `uri`,
`notes`, `domain`, `credential_id`. Use `--id <vault-item-id>` instead of `--domain` when you know the
exact item; the two flags are mutually exclusive.

**NEVER run `aac connect --domain … --output json`.** That prints the credential to stdout, which is your
context — the one thing this whole mechanism exists to prevent. `aac run` is the only fetch you use.

**The shell-expansion gotcha (the same one that cost a session under the old broker):** `aac run … -- <cmd>`
execs `<cmd>` DIRECTLY, with no shell, so `"$password"` expands only if `<cmd>` IS a shell. Writing
`aac run --domain x.com --env-all -- web-plane lane L fill e5 "$password"` types the literal 9 characters
`$password` into the field — a wrong login that LOOKS right, dots in the box and all, then "password does
not match". Always wrap it:

```sh
aac run --domain x.com --env-all -- sh -c 'web-plane lane L fill e5 "$password"'
```

**Getting a site past a login wall:**
1. Drive the browser to the real login URL (a bare domain often redirects when logged out).
2. Snapshot to get the field refs, then fill username and password through `aac run` as above. If the item
   carries a TOTP, `"$totp"` is a valid code at that moment — fill it in the same command, not a later one.
3. Carry on in the same browser session; it is now logged in, and it stays logged in, so the next task on
   that site needs no credential at all.

**Approval takes as long as it takes.** The operator approves each request in a terminal on their laptop.
Let the command wait — never wrap it in a `timeout`, which kills the request mid-approval.

**When the listener is not running** the request fails rather than hanging: they are asleep, or the laptop
is shut. Do NOT retry in a loop and do NOT treat it as a broken credential. Say so on the card, in one
line, naming what you need — then follow the HUMAN GATE procedure in CLAUDE.md, whose readiness probe here
is a cheap `aac connections list`, never a login attempt.
