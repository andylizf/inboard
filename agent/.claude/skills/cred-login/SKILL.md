---
name: cred-login
description: Use authorized saved credentials to complete a card's login with the `cred` broker. Load when a browser reaches a login page, when a task needs a saved password, or before asking the operator to log in. Covers credential checks, secret injection into commands, and actual authentication blockers.
---

Need a saved login/password? Use the **`cred`** broker. It holds the vault session in memory on this
machine and hands a secret only into a command's environment — never onto your stdout. This is the only
way you may touch a secret. Use credentials it authorizes for the card's task without asking for another
approval. An explicit operator restriction on that account or action still applies.

Check the browser's existing session and available autofill, then the site's own vault credential,
then its established identity-provider route. Choose the account's route before submitting once;
after a rejected login, do not try another route without an explicit operator retry request.
A command-line 401 does not test the browser's cookies.
Continue the authorized login through the actual browser flow; a provider button or a remembered Duo
requirement does not show that this attempt needs his phone. Do not reduce the authorized login to
inspection or prohibit its permitted challenge, whether doing it yourself or delegating it, unless the
operator or an applicable instruction imposed that limit. The
operator's possible future login is not a reason to stop your present task or ask him to finish it.
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
Follow `web-tasks` and the existing login-attempt limits. Acquire `twofa-gate` before the step that can
send a second factor, including credential submission when it can auto-push. Under the existing task
authorization, proceed with one allowed challenge without asking for separate permission to start it.
Ask for his part when the service actually requests an action only he can perform, using the current
challenge's evidence; then monitor it under `human-gate` and continue after confirmation. A real gate
refusal or rejected credential remains a blocker under the attempt limits.
After verification, complete the site's remaining login steps. When offered on the operator's
own persistent browser profile, select the option to remember or trust this device unless he
restricted it; do not select it on a temporary profile or one shared with other people. Record the observed result
and verify access to the destination before reporting login success. Reuse that profile on
later tasks and check whether the session is still accepted.

**When the vault is locked** every fetch fails until a human unlocks it, and it stays locked until then —
there is no timer that will clear it. Do NOT retry in a loop. Say so on the card in one line and follow
`human-gate`; the safe readiness probe is `cred status`, never a login attempt.
Use the broker's reported unlock procedure on the machine running it.

**Read cred's full output, never grep it away** — it is progressive-disclosure and tells you the exact
next step. One error deserves suspicion rather than belief: `item has no login.password field` can mean
the broker's session has been invalidated rather than that the item is passwordless. Check `cred status`
and the broker's diagnostics; multiple missing-field errors alone do not prove either explanation.
