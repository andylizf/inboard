---
name: human-gate
description: Handle an observed blocker requiring the operator or an external condition, including a pending login approval or locked vault. Load after checking available authorized routes; a login form or anticipated verification alone is not a blocker. Use twofa-gate for sending or replacing verification prompts; this skill governs waiting for their result.
---

## Keep ownership while waiting

Record the actual failed step and evidence on the card. Ask for only the action the operator must
perform, and continue independent work. Use needs_you for his action and waiting for an external
condition; a running probe does not change who must act next.

If a read-only signal can detect readiness without submitting credentials, sending a new prompt or
changing account state, run one bounded background probe. Use the runtime's tracked background task,
record its task id, signal and timeout in the card log, and consume its result in this session.
For browser verification, detect changes in the page's challenge state, including a follow-up
button, success or expiry; the URL can remain unchanged after approval. A probe error is not
evidence that the operator has not acted. On a state change, inspect the page and continue the
authorized flow, including steps you can complete yourself, before asking him again.
Choose a timeout that fits the challenge's validity; a vault-status check can wait up to 30 minutes.
Ending the foreground turn while the probe runs is allowed; it is not completion or a reason to
discard the session. On readiness, resume the authorized work immediately. On timeout, record what
remains blocked and reconcile the card's next review without scheduling another login attempt.

Without a safe probe, leave the precise blocker and next step on the card. The operator's next
comment or action can resume the work; do not promise the same session or a start time you cannot
verify. An explicit retry request goes through twofa-gate when verification is involved.
Do not require another confirmation of that retry or treat an old blocker as current evidence.
