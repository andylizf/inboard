# Execute a prepared action

A press of 📤 帮我发送 wakes the card's agent with an operation token; the agent then carries the
action out itself and writes exactly one receipt (`board clear-action` when the outcome is verified,
`board action-fail --text` with the precise failure or unknown outcome otherwise). Nothing runs a
script mechanically on a press: the earlier route, which replayed a frozen script through Claude
Code's `!` input, was removed on 2026-09-18 because it needed a staged script and a live session id
to match at once, and neither survived a daemon restart.

What the press approves is the card's `Draft` as it stood at the click. `board approved-draft`
fails when the current `Draft` no longer matches that snapshot, and `email +send-approved` refuses
to send on that failure, so an edited draft needs a fresh press.

Staging is how the agent publishes what he is approving. `email ACCOUNT gmail +draft ...` creates
the mail draft and publishes its complete preview. For anything that is not an email, the agent
prepares its own script under `agent/scripts/card-<id>/` and stages it:

```bash
board stage-script --card CARD --file ./scripts/action.sh --cwd "$PWD" \
  --description "Action, account, destination and exact content" --input ./payload.pdf
```

`Draft` holds the human-readable preview; `Script` records the preview, the saved source, working
directory and input hashes, so a later reader can see what the agent intended to run. That script
is the agent's own tool for the job, not a mechanism of the board: a failure inside it ("脚本缺陷")
is a bug in the agent's automation, which the agent repairs and re-stages before asking for
another press.

Run `python setup/action_ui.py --apply`. In Notion, keep one execution button named 📤 帮我发送. Its
Edit This page action copies Script to ActionScript, increments ActionVersion and sets ActionRequested
to `❗ Execute script`. Empty Script preserves all three values. Show Draft and Script; hide ActionScript.

A missing receipt means execution is unconfirmed; the stall check (`lib/daemon_stall_check.py`)
wakes the card's agent to verify the destination, never to resend. A zero exit code from the
agent's script does not prove the task is complete.
