---
name: web-tasks
description: Complete browser work for a card, including login and verification. Load whenever browser automation is needed. The installed browser skill owns setup and challenge handling; cred-login owns saved credentials, twofa-gate owns second-factor prompts, and card-actions owns outward submission approval.
---

Load the installed `browser` skill and use its managed browser and current commands. Keep its window
hidden unless the operator needs a specific step. Reuse the authorized session; do not launch another
profile or worker to evade login limits. Snapshot before acting and refresh references after navigation:

- `browser open <url>` — navigate
- `browser snapshot -i` — list interactive elements, each with a stable ref like `@e1` (primary way to see the page)
- `browser click @e1` / `browser fill @e2 "text"` / `browser type @e2 "text"` / `browser press Enter` / `browser select @e2 <val>` — act by ref
- `browser eval <js>` — run JavaScript (read a value, or `document.querySelector('input[name=x]').form.submit()` when a ref-click won't submit the form)
- `browser read <url>` — page as text/markdown, cheapest for pure reading
- `browser screenshot <path>` — capture the current page
- `browser get url` — confirm where you actually ARE (a login redirect / stale tab can silently land you elsewhere)

**Refs go STALE across page reloads.** After any submit/navigation, re-snapshot before acting again — reusing old refs silently fills detached nodes and the form submits empty.

The Chrome keeps saved logins in its profile, so once a site is logged in it just works across cycles.
When navigation lands on a login form, load **`cred-login`** and continue with available credentials;
the browser command does not fill them automatically. A read-only status check can require a login.
Before a login that may send a second factor, follow **`twofa-gate`**: acquire the gate, proceed once if
allowed, tell the operator what to approve and any displayed matching code, then continue after approval.
An actual credential or authentication blocker goes through **`human-gate`**; a login form by itself does not.

Attempt verification challenges during an authorized login under the installed browser skill's
procedure and applicable higher-priority rules. Do not decline merely because it is an image question
or because you speculate about an account penalty. If a rule or tool blocks the attempt, name that
rule or error and the specific step; request only the remaining human action. Distinguish a checkbox
passing without a puzzle from actually solving an image challenge.

Capture and upload evidence at login outcomes, verification gates, errors, pre-submit confirmation
and the final result with `board image --card C --file PATH --caption TEXT`. Inspect screenshots for
secrets before uploading; use a redacted image or non-secret receipt when the screen exposes one.
A screenshot must show the claimed state; a pending page or absence of an error proves no success.

For outward submissions, stage the complete proposal in Draft and execute the approved operation
under `card-actions`. Approval of the general task does not approve an unspecified submission.

Check the destination's confirmation or authoritative record after submission; check email when the
service uses it as the receipt. Do not require email from a service that sends none. An ambiguous
result requires investigation, not another click by the operator. Keep responsibility for checking
it and report precisely which evidence remains unavailable before considering a retry.
