---
name: cred-login
description: Fetch a saved login/password with the `cred` broker — the secret NEVER enters your context. Load this the moment `browser` pauses on a login page, or whenever you need any saved credential. Covers the fetch-into-a-command model, the $CRED-shell gotcha, and what a locked vault looks like.
---

Need a saved login/password? Use the **`cred`** broker. It holds the vault session in memory on this
machine and hands a secret only into a command's environment — never onto your stdout. This is the ONLY
way you may touch a secret.

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

**The $CRED-shell gotcha (it cost a whole session once):** `cred with … -- <cmd>` runs `<cmd>` DIRECTLY,
with no shell, so `"$CRED"` expands only if `<cmd>` IS a shell. Writing
`cred with <id> -- web-plane lane L fill e5 "$CRED"` types the literal 5 characters `$CRED` into the
field — a wrong login that LOOKS right, dots in the box and all, then "password does not match". Always
wrap it:

```sh
cred with <id> -- bash -c 'web-plane lane L fill e5 "$CRED"'
```

`cred get` prints the raw secret and is refused to a non-TTY; agents always use `cred with`.

**Getting a site past a login wall:** drive the browser to the login URL, snapshot for the field refs,
fill username and password through `cred with` as above, then carry on in the same browser session. It
stays logged in afterwards, so the next task on that site needs no credential at all.

**When the vault is locked** every fetch fails until a human unlocks it, and it stays locked until then —
there is no timer that will clear it. Do NOT retry in a loop. Say so on the card in one line and follow
the HUMAN GATE procedure in CLAUDE.md; the cheap readiness probe there is `cred status`, never a login
attempt. The operator unlocks with `ssh -t mac-mini "cred unlock '*'"`.

**Read cred's full output, never grep it away** — it is progressive-disclosure and tells you the exact
next step. One error deserves suspicion rather than belief: `item has no login.password field` can mean
the broker's session has been invalidated rather than that the item is passwordless. If several items
report it at once, the session is dead — relay the unlock, do not conclude anything about the vault.
