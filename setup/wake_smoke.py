#!/usr/bin/env python3
"""Exercise scheduled delivery and acknowledgement on one synthetic live card.

Only additive schema changes are made. The test card is backed up then archived.
The worker is restricted to this fixture; no mail, login or outside service is used.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import sys
import time
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import wakeups as W


def main(output, runtime):
    output.mkdir(parents=True, exist_ok=True)
    if (output / "fixture.json").exists():
        raise RuntimeError("choose a new output directory; the previous smoke result is retained")
    os.environ["INBOARD_STATE"] = str(output / "state")
    Path(os.environ["INBOARD_STATE"]).mkdir(exist_ok=True)
    os.environ["INBOARD_LOGS"] = str(output)
    board = W.load_board()
    with (output / "smoke.log").open("a") as log:
        def emit(card, status, **fields):
            print(json.dumps({"ts": W.now().isoformat(), "card": card, "status": status, **fields}), file=log, flush=True)
        emit(None, "start")
        board.api("PATCH", f"/databases/{board.DB}", {"properties": {
            "Wakeups": {"rich_text": {}}, "NextCheck": {"date": {}}, "NextAction": {"rich_text": {}}}})
        rules = W.add([], (W.now() - timedelta(minutes=1)).isoformat(), "Synthetic check: record that this scheduled agent ran.")
        rules = W.add(rules, (W.now() + timedelta(days=1)).isoformat(), "Synthetic future check; preserve it when acknowledging this run.")
        page = board.api("POST", "/pages", {"parent": {"database_id": board.DB}, "properties": {
            "Subject": {"title": W.text("[TEST] Scheduled wakeup smoke — synthetic, no external actions")},
            "Status": {"select": {"name": board.S["awaiting"]}}, **W.properties(rules)}})
        card = page["id"]
        W.save(output / "fixture.json", page)
        wrapper = output / "board.sh"
        wrapper.write_text("#!/usr/bin/env bash\nset -e\nsource " + shlex.quote(str(runtime / "engines/_common.sh")) + "\n"
                           + "export INBOARD_HOME=" + shlex.quote(str(ROOT)) + "\n"
                           + "export INBOARD_CONFIG=" + shlex.quote(os.environ["INBOARD_CONFIG"]) + "\n"
                           + "export INBOARD_STATE=" + shlex.quote(os.environ["INBOARD_STATE"]) + "\n"
                           + 'exec python3 "$INBOARD_HOME/bin/board" "$@"\n')
        def send(card, prompt, board):
            command = "bash " + shlex.quote(str(wrapper))
            prompt = prompt.replace("board ", command + " ")
            prompt += (f"\nSYNTHETIC TEST. Work ONLY on card {card}. Do not read mail, memory or other cards; do not log in or contact anyone. "
                       f"The supplied fixture is the full task: use {command} log --card {card} --text 'Synthetic scheduled wakeup executed successfully.' "
                       f"Then {command} awaiting --card {card} --desc 'Synthetic future check pending'. "
                       "Keep the future trigger unchanged, then run the wake-ack command above. Use the wrapper for every board command. Stop after the receipt.")
            W.deliver(card, prompt, board)
        original = W.candidates
        try:
            W.candidates = lambda board: [page]
            W.sweep(board, emit, send=send)
        finally:
            W.candidates = original
        deadline = time.monotonic() + 600
        receipt = W.root() / f"{card}.json"
        while time.monotonic() < deadline:
            rec = json.loads(receipt.read_text())
            if rec.get("state") == "complete":
                result = board.api("GET", f"/pages/{card}")
                remaining = W.read(result)
                if len(remaining) != 1 or remaining[0]["id"] != rules[1]["id"]:
                    raise RuntimeError("acknowledgement changed the future trigger")
                W.save(output / "result.json", {"receipt": rec, "page": result})
                board.done(argparse.Namespace(card=card))
                board.api("PATCH", f"/pages/{card}", {"archived": True})
                if W.C.get("agent.delivery", "inprocess") == "daemon":
                    import agent_deliver
                    agent_deliver.retire("inboard-card-" + card.replace("-", ""))
                emit(card, "verified", receipt=rec["token"], future_trigger_preserved=True, archived=True)
                print(json.dumps({"card": card, "verified": True, "output": str(output)}))
                return
            time.sleep(5)
        emit(card, "fail", reason="no completion receipt within 10 minutes")
        raise RuntimeError("smoke worker did not acknowledge; inspect its session before retrying")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    main(args.output, args.runtime)
