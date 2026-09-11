---
name: cred-login
description: Use authorized saved credentials to complete a card's login with the `cred` broker. Load when a browser reaches a login page, when a task needs a saved password, or before asking the operator to log in. Covers credential checks, secret injection into commands, and actual authentication blockers.
---

Need a saved login/password? Use the **`cred`** broker. It holds the vault session in memory on this
machine and hands a secret only into a command's environment — never onto your stdout. This is the only
way you may touch a secret. Use credentials it authorizes for the card's task without asking for another
approval. An explicit operator restriction on that account or action still applies.

Try the browser's existing session and autofilled login first, then the site's own vault credential,
then its established identity-provider login. A command-line 401 does not test the browser's cookies.
Do not extract passwords from Chrome's store. For a login form, run `cred status` and `cred find <site>`,
then use the matching item through `cred with`. `UNLOCKED` alone does not prove that an item can be fetched;
record the fetch result and the browser outcome in the card log, without the secret. A login form or an
old note saying "needs login" is not a reason to ask the operator to enter a password you can use.

A missing site credential may mean the account uses Google, Apple or another provider. Check the
operator's instructions, prior verified login records, mail and the site's account-selection flow to
establish which route belongs to this account. Search for the provider credential when that route
is established. A welcome email, a password-reset email or a provider button alone does not prove
which login methods the account supports. If the route could register a new account and you cannot
establish that this is the existing account, obtain approval for registration before completing it.

**Look it up first (free, no secrets):**

```sh
cred find <site>
```

Returns item id, username and the real login URL. Use that URL, not a bare domain — a bare domain often
redirects when logged out.

**Then fetch it INTO a command, never into your own output:**

```sh
cred with <id> -- bash -c '<command that uses "$CRED">'
```

**Shell expansion:** `cred with … -- <cmd>` runs `<cmd>` directly,
with no shell, so `"$CRED"` expands only if `<cmd>` IS a shell. Writing
`cred with <id> -- browser fill @e5 '$CRED'` types the literal 5 characters `$CRED` into the
field — a wrong login that LOOKS right, dots in the box and all, then "password does not match". Always
wrap it:

```sh
cred with <id> -- bash -c 'browser fill @e5 "$CRED"'
```

`cred get` prints the raw secret and is refused to a non-TTY; agents always use `cred with`.

**Getting a site past a login wall:** drive the browser to the login URL, snapshot for the field refs,
fill username and password through `cred with` as above, then carry on in the same browser session.
Follow `web-tasks` and the existing login-attempt limits. Before a login that may send a second factor,
use `twofa-gate`; a gate refusal, rejected credential or pending human approval is an observed blocker.
Reuse a successful session on later tasks and check whether it is still accepted.

**When the vault is locked** every fetch fails until a human unlocks it, and it stays locked until then —
there is no timer that will clear it. Do NOT retry in a loop. Say so on the card in one line and follow
`human-gate`; the safe readiness probe is `cred status`, never a login attempt.
Use the broker's reported unlock procedure on the machine running it.

**Read cred's full output, never grep it away** — it is progressive-disclosure and tells you the exact
next step. One error deserves suspicion rather than belief: `item has no login.password field` can mean
the broker's session has been invalidated rather than that the item is passwordless. Check `cred status`
and the broker's diagnostics; multiple missing-field errors alone do not prove either explanation.
