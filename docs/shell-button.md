# Execute a prepared script

The ❗执行脚本 button runs a staged Bash script through Claude Code's interactive `!` mode in the card's
existing daemon session. Command output stays in that conversation. Claude Code responds automatically
unless `respondToBashCommands` is disabled.

Prepare a self-contained script, then run:

```bash
board stage-script --card CARD --file ./scripts/action.sh --cwd "$PWD" \
  --description "Action, account, destination and exact content" --input ./payload.pdf
```

Repeat `--input` for each payload or helper file whose bytes must be checked. The Script property shows
the saved script, description, working directory and input hashes. Keep secrets in the project's
credential store, outside this preview. Arbitrary dependencies and remote state are not frozen.

Run `python setup/action_ui.py --apply` to add Script, ActionScript and the request option. Create a
Notion button named ❗执行脚本 with one Edit This page action: copy Script to ActionScript; increment
ActionVersion; set ActionRequested to `❗ Execute script`. When Script is empty, preserve all three
existing values. Show Script in the card layout and hide ActionScript.

A click executes the saved version once. A changed preview, script or declared input blocks execution.
Each attempt retains its script, input hashes, terminal log, output and result under `state/shell-plans`.
A missing result means execution is unconfirmed; inspect the original session and destination before
preparing another version. A zero exit code does not establish that the business task is complete.

After a failure, Claude can diagnose the output and stage a corrected version. Repeating the external
action requires another click. The route does not change Claude's policies about preparing or repairing
a script.
