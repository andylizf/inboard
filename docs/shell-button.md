# Execute a prepared action

The 帮我执行 button approves the operation preview and runs its saved Bash script through Claude Code's
native `!` mode in the card's existing session. Output returns to that session for verification and
diagnosis. Claude responds automatically unless `respondToBashCommands` is disabled. Stop hooks do
not execute scripts.

Prepare scripts before asking for approval. `email ACCOUNT gmail +draft ...` creates the mail draft,
publishes its complete preview and stages the guarded send script automatically. For an existing
draft, verify its current content, then use:

```bash
board stage-email --card CARD --account ACCOUNT --draft-id ID
```

For other actions, prepare a self-contained script and run:

```bash
board stage-script --card CARD --file ./scripts/action.sh --cwd "$PWD" \
  --description "Action, account, destination and exact content" --input ./payload.pdf
```

Draft holds the human-readable operation preview; Script includes that preview, the saved source,
working directory and input hashes. Repeat `--input` for each payload or helper file. Keep credentials
outside the preview. Arbitrary dependencies and remote state are not frozen.

Run `python setup/action_ui.py --apply`. In Notion, keep one execution button named 帮我执行. Its
Edit This page action copies Script to ActionScript, increments ActionVersion and sets ActionRequested
to `❗ Execute script`. Empty Script preserves all three values. Back up the old automation settings
and remove the separate send button. Show Draft and Script; hide ActionScript.

Each saved version executes at most once. Changed operation text, script or declared inputs block
execution. Email also checks the live Gmail draft headers and body against the preview saved with
the script before sending. Execution records remain under `state/shell-plans`. A missing result means
execution is unconfirmed; inspect the original session and destination before preparing another
version. A zero exit code does not prove the task is complete.

After a failure, diagnose and stage the corrected version for another click of the same button.
The route does not change Claude's policies about preparing or repairing scripts.
