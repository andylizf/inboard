---
name: web-tasks
description: Drive a real headed Chrome for ANY web task on a card — click a button, fill/submit a form, read a gated page, complete a portal action. Load this whenever handling a card requires browser automation. Covers the `browser` CLI (snapshot/click/fill/eval), staying on the right page, and the screenshot-at-every-checkpoint rule.
---

For ANY web task use the **`browser`** command. It drives a persistent REAL HEADED Chrome (its own dedicated profile, launched in the GUI session so it keeps GPU + Keychain, CDP on 127.0.0.1:9223). Do NOT spawn another claude and do NOT use headless Playwright (brittle: bot-detection / cookie / JS breakage). Snapshot FIRST, act on refs, re-snapshot after the page changes:

- `browser open <url>` — navigate
- `browser snapshot -i` — list interactive elements, each with a stable ref like `@e1` (primary way to see the page)
- `browser click @e1` / `browser fill @e2 "text"` / `browser type @e2 "text"` / `browser press Enter` / `browser select @e2 <val>` — act by ref
- `browser eval <js>` — run JavaScript (read a value, or `document.querySelector('input[name=x]').form.submit()` when a ref-click won't submit the form)
- `browser read <url>` — page as text/markdown, cheapest for pure reading
- `browser screenshot <path>` — capture the current page
- `browser get url` — confirm where you actually ARE (a login redirect / stale tab can silently land you elsewhere)

**Refs go STALE across page reloads.** After any submit/navigation, re-snapshot before acting again — reusing old refs silently fills detached nodes and the form submits empty.

The Chrome keeps saved logins in its profile, so once a site is logged in it just works across cycles.
**`browser` will NOT log in** — it pauses on login pages. The moment you hit a login wall, load the **`cred-login`** skill.

**SCREENSHOT AT EVERY CHECKPOINT** — not just the final result. Your TEXT summaries are NOT trusted (they have been contradictory/wrong before, e.g. "login succeeded" and "authentication failed" for the same step). The screenshot is the ground truth the operator checks. Take + upload a screenshot at EACH of: after every login attempt (success OR the exact on-screen error), the instant you hit any gate (2FA, "Authentication failed", a hold/consent page), any error, the pre-submit confirm screen, and the final success/failure. NEVER claim a step succeeded or failed without the screenshot that proves it. Upload with:
`board image --card <id> --file <screenshot.png> --caption '<one line>'` — NEVER paste a local file path in text (Notion can't render it). Then VERIFY before claiming success.

An irreversible final submit (decline / pay / delete): autonomously ONLY if the operator approved THIS card; otherwise stop at the confirm screen, screenshot it, and ask.

**A web-form action you cannot verify is a FLAG, not a retry.** If you attempt a sign-up / form submit (a webinar registration, a Google/Qualtrics form, a portal action) and cannot confirm success (the confirmation page text AND the confirmation email actually arriving), do NOT claim success and do NOT loop to max-turns — put the link on the card, set it `📥 New` with the exact ask in `--needs`, and say it's unverified / needs their click.
