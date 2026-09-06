#!/usr/bin/env python3
"""Back up and migrate an existing board to explicit card wakeups.

The backup directory is the resume checkpoint. Default is read-only; --apply
updates cards/schema/config. --remove-legacy removes Place/Lapses only after
all card checkpoints exist. Private snapshots never belong in version control.
"""
import argparse
import json
import os
from pathlib import Path
import hashlib
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import ibconfig as C
import wakeups as W


def migrate(backup, apply=False, remove=False):
    board = W.load_board()
    backup.mkdir(parents=True, exist_ok=True)
    os.chmod(backup, 0o700)
    with (backup / "migration.log").open("a") as log:
        def event(item, status, **fields):
            print(json.dumps({"ts": W.now().isoformat(), "item": item, "status": status, **fields}), file=log, flush=True)
        source = Path(__file__).read_bytes()
        digest = hashlib.sha256(source).hexdigest()
        saved_source = backup / f"migration-{digest}.py"
        if not saved_source.exists():
            saved_source.write_bytes(source)
        event("migration", "start", apply=apply, remove_legacy=remove, source_sha256=digest)
        snapshot = backup / "snapshot.json"
        if not snapshot.exists():
            schema = board.api("GET", f"/databases/{board.DB}")
            pages, cursor = [], None
            while True:
                query = {"page_size": 100}
                if cursor:
                    query["start_cursor"] = cursor
                result = board.api("POST", f"/databases/{board.DB}/query", query)
                pages.extend(result["results"])
                if not result.get("has_more"):
                    break
                cursor = result["next_cursor"]
            data = {"schema": schema, "pages": pages, "config": C.load(), "captured_at": W.now().isoformat()}
            W.save(snapshot, data)
            (backup / "inboard.config.yaml").write_text(Path(C.config_path()).read_text())
        data = json.loads(snapshot.read_text())
        cfg = data["config"]
        old_status = cfg["board"]["schema"]["status"]
        new_waiting = "⏳ 等待中" if "等" in old_status["awaiting"] else "⏳ Waiting"
        new_cancel = "✖ 已取消" if "等" in old_status["awaiting"] else "✖ Cancelled"
        chinese = "等" in old_status["awaiting"]
        if not apply:
            event("migration", "snapshot_saved", pages=len(data["pages"]))
            print(json.dumps({"backup": str(backup), "pages": len(data["pages"]), "apply": False}))
            return
        # The read-only preflight may precede deployment. Capture newer cards and edits too.
        latest, cursor = [], None
        while True:
            query = {"page_size": 100}
            if cursor:
                query["start_cursor"] = cursor
            result = board.api("POST", f"/databases/{board.DB}/query", query)
            latest.extend(result["results"])
            if not result.get("has_more"):
                break
            cursor = result["next_cursor"]
        W.save(backup / f"pages-{W.now().strftime('%Y%m%dT%H%M%S%f')}.json", latest)
        data["pages"] = latest
        schema = board.api("GET", f"/databases/{board.DB}")
        options = schema["properties"]["Status"]["select"]["options"]
        for option in options:
            if option["name"] == old_status["awaiting"]:
                option["name"] = new_waiting
        if not any(o["name"] == new_cancel for o in options):
            options.append({"name": new_cancel, "color": "gray"})
        board.api("PATCH", f"/databases/{board.DB}", {"properties": {
            "Status": {"select": {"options": options}}, "Wakeups": {"rich_text": {}},
            "NextCheck": {"date": {}}, "NextAction": {"rich_text": {}}}})
        # Updating by option id keeps existing waiting cards and their Notion grouping intact.
        current_cfg = C.load()
        current_cfg["board"]["schema"]["status"].update(awaiting=new_waiting, cancelled=new_cancel)
        current_cfg["board"]["schema"].setdefault("status_aliases", {})[old_status["awaiting"]] = "awaiting"
        actions = current_cfg["board"]["schema"].get("action_status", {})
        for action in actions:
            if "忽略" in action or "ignore" in action.lower() or "cancel" in action.lower():
                actions[action] = "cancelled"
        current_cfg.get("schedule", {}).pop("stale_awaiting_days", None)
        import yaml
        Path(C.config_path()).write_text(yaml.safe_dump(current_cfg, allow_unicode=True, sort_keys=False))
        timezone = ZoneInfo(C.get("identity.timezone") or "UTC")
        initial = datetime.now(timezone)
        closed = {old_status.get(k) for k in ("done", "expired", "unsub", "cancelled")} | {new_cancel}
        checkpoints = backup / "cards"
        checkpoints.mkdir(exist_ok=True)
        for saved in data["pages"]:
            card = saved["id"]
            checkpoint = checkpoints / f"{card}.json"
            event(card, "start")
            if checkpoint.exists():
                event(card, "skip", reason="checkpoint")
                continue
            page = board.api("GET", f"/pages/{card}")
            status = board._g(page["properties"], "Status", "select")
            rules = W.read(page)
            props = {}
            if not page.get("archived") and status not in closed:
                legacy_lapses = page["properties"].get("Lapses", {}).get("checkbox", False)
                due = (page["properties"].get("Due", {}).get("date") or {}).get("start")
                needs = board._g(page["properties"], "NeedsYou", "rich_text") or ""
                if status in (old_status["awaiting"], new_waiting) or needs.startswith("⏳催问："):
                    reason = ("检查这件事的最新进展，继续能做的工作，并安排下一次检查。" if chinese else
                              "Review the waiting matter and latest evidence. Set its next useful check based on the matter; continue any work you can do yourself.")
                    rules = W.add(rules, initial.isoformat(), reason)
                    props["Status"] = {"select": {"name": new_waiting}}
                    if needs.startswith("⏳催问："):
                        props["NeedsYou"] = {"rich_text": []}
                if due:
                    d = datetime.fromisoformat(due.replace("Z", "+00:00"))
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=timezone)
                    before = max(initial, d - timedelta(days=1))
                    reason = ("核实截止时间和未完成事项，继续处理；只有需要本人操作时才提醒。" if chinese else
                              "Review the approaching or missed deadline and remaining work; check the original source for the exact cutoff. Continue work or surface the specific operator action.")
                    rules = W.add(rules, before.isoformat(), reason)
                    if legacy_lapses:
                        after = d + timedelta(days=1) if len(due) == 10 else d
                        reason = ("核实窗口是否已关闭；只有确实过期且没有后续待办，才标记已过期，不能标记完成。" if chinese else
                                  "Verify the actual cutoff and remaining obligations; use expired only if the window has closed and nothing remains. Never mark missed work done.")
                        rules = W.add(rules, max(initial, after).isoformat(), reason)
                if rules != W.read(page) or props:
                    board.api("PATCH", f"/pages/{card}", {"properties": {**props, **W.properties(rules)}})
                board.remember_status(card, props.get("Status", {}).get("select", {}).get("name", status))
            W.save(checkpoint, {"card": card, "before": page, "rules": rules, "completed_at": W.now().isoformat()})
            event(card, "ok", triggers=len(rules))
        if remove:
            if not all((checkpoints / f'{p["id"]}.json').exists() for p in data["pages"]):
                raise RuntimeError("card migration is incomplete; legacy properties retained")
            cursor = None
            while True:
                query = {"page_size": 100}
                if cursor:
                    query["start_cursor"] = cursor
                result = board.api("POST", f"/databases/{board.DB}/query", query)
                W.save(backup / f"before-removal-{W.now().strftime('%Y%m%dT%H%M%S%f')}.json", result)
                if any(not (checkpoints / f'{p["id"]}.json').exists() for p in result["results"]):
                    raise RuntimeError("new cards arrived during migration; resume before removing legacy properties")
                if not result.get("has_more"):
                    break
                cursor = result["next_cursor"]
            live = board.api("GET", f"/databases/{board.DB}")
            changes = {name: None for name in ("Place", "Lapses") if name in live["properties"]}
            if changes:
                board.api("PATCH", f"/databases/{board.DB}", {"properties": changes})
            event("schema", "legacy_removed")
        event("migration", "done", pages=len(data["pages"]))
        print(json.dumps({"backup": str(backup), "pages": len(data["pages"]), "apply": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--remove-legacy", action="store_true")
    args = parser.parse_args()
    migrate(args.backup_dir, args.apply, args.remove_legacy)
