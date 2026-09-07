# Button feedback implementation plan

Goal: Show the latest click immediately and interrupt the old response before delivering its replacement.

1. Verify native button label controls in the current Notion UI. Use a fixed label plus a formula status if there is no per-card dynamic label.
2. Keep button intent in ActionRequested and an incrementing ActionVersion. Store execution results separately so an old completion cannot erase a later click. Preserve the earlier timestamp receipt only until each card's next button click; Notion's Time triggered rounded to a minute in the live test.
3. Add serialized request handling in lib/action_runs.py and confirmed terminal interruption in lib/agent_deliver.py. Route modern button events from engines/action-handler.sh through it.
4. Add current-operation checks to board receipts and approved sends. Preserve legacy cards until they receive their first modern button click.
5. Add the schema with a backup, configure the four native buttons, and pin only the visible status. Hide implementation properties.
6. Verify duplicate events, stale completion, canceled send approval, and real test-card replacement. Never send test mail from a real card.

## Send availability and Summary

The send button submits a request only when Draft contains text. It captures Draft at the click; dispatch and submission reject a missing or changed preview before sending. Empty-draft clicks preserve the current request and worker. The status formula explains when no draft is available.

`board note` replaces the Summary property. A resumable migration backs up each card, copies its existing state callout into Summary, verifies the copy, and archives the old callout. Card search includes Summary. Update the card layout to show Summary before Draft.

Verify empty-draft clicks, changed-draft rejection, existing summary migration, and real Notion readback. Use an isolated test card without sending mail.
