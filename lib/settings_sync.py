#!/usr/bin/env python3
"""Pull operator preferences from the Notion settings panel into the files the engines read.

Most settings land in inboard.config.yaml under `preferences:`. `model` lands in
agent/.claude/settings.json instead, because that is the file Claude Code itself reads for every
agent started from agent/ — daemon workers included — and it outranks the machine's user settings.
The panel stays the one place the operator touches; this is what renders it into the right file.

The panel is the source of truth, and this runs every dispatch cycle, so a preference
edited anywhere else is reverted on the next pass — including by an agent, which is the
point: these are the operator's tastes, not a value for the engines to tune. The engines
keep reading the local YAML, so nothing gets slower and a Notion outage changes nothing.

Only keys in SCHEMA are touched and only values the schema allows are written; anything
else is left alone and named in the output, so a bad edit degrades to "ignored and
reported" rather than to an engine reading a value it cannot interpret.
"""
import os
import pathlib
import re
import subprocess
import sys

INBOARD = pathlib.Path(os.environ.get("INBOARD_HOME", pathlib.Path.home() / "Projects/inboard"))
CONFIG = INBOARD / "inboard.config.yaml"
AGENT_SETTINGS = INBOARD / "agent" / ".claude" / "settings.json"

SCHEMA = {
    "calendar_events":  {"auto", "propose", "off"},
    "identity_alerts":  {"assume-self", "ask"},
    "ci_notifications": {"noise", "surface"},
    "unsubscribe":      {"conservative", "aggressive"},
    "model":            {"opus", "sonnet", "haiku"},   # → agent/.claude/settings.json, not the YAML
}
FILE_KEYS = {"model"}   # settings that live in agent/.claude/settings.json rather than the YAML


def _cfg(key, default=""):
    r = subprocess.run(["cfg", key], capture_output=True, text=True)
    return (r.stdout.strip() or default)


def read_panel(db_id):
    sys.path.insert(0, str(INBOARD / "lib"))
    import importlib.machinery, importlib.util
    ld = importlib.machinery.SourceFileLoader("boardmod", str(INBOARD / "bin/board"))
    spec = importlib.util.spec_from_loader("boardmod", ld)
    mod = importlib.util.module_from_spec(spec)
    ld.exec_module(mod)
    out, cursor = {}, None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = mod.api("POST", f"/databases/{db_id}/query", body)
        for p in r.get("results", []):
            pr = p.get("properties", {})
            name = "".join(x.get("plain_text", "") for x in (pr.get("Setting") or {}).get("title") or [])
            val = ((pr.get("Value") or {}).get("select") or {}).get("name")
            if name and val:
                out[name.strip()] = val.strip()
        if not r.get("has_more"):
            break
        cursor = r.get("next_cursor")
    return out


def apply_agent_settings(panel):
    """Write the FILE_KEYS into agent/.claude/settings.json, touching only those keys."""
    import json
    changed, rejected = [], []
    wanted = {k: v for k, v in panel.items() if k in FILE_KEYS}
    if not wanted:
        return changed, rejected
    try:
        current = json.loads(AGENT_SETTINGS.read_text(encoding="utf-8")) if AGENT_SETTINGS.exists() else {}
    except ValueError:
        rejected.append(f"{AGENT_SETTINGS.name} is not valid JSON — left alone")
        return changed, rejected
    for key, want in wanted.items():
        if want not in SCHEMA[key]:
            rejected.append(f"{key}={want} (not one of {sorted(SCHEMA[key])})")
            continue
        if current.get(key) != want:
            changed.append(f"{key}: {current.get(key, '(absent)')} -> {want}")
            current[key] = want
    if changed:
        AGENT_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        AGENT_SETTINGS.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return changed, rejected


def apply(panel):
    text = CONFIG.read_text(encoding="utf-8")
    lines = text.split("\n")
    try:
        start = next(i for i, l in enumerate(lines) if l.rstrip() == "preferences:")
    except StopIteration:
        print("settings-sync: no preferences: block in the config")
        return 0, []
    end = start + 1
    while end < len(lines) and (lines[end].startswith("  ") or not lines[end].strip()):
        end += 1

    changed, rejected = apply_agent_settings(panel)
    for key, want in panel.items():
        if key in FILE_KEYS:
            continue                                   # already handled above
        if key not in SCHEMA:
            rejected.append(f"{key} (unknown setting)")
            continue
        if want not in SCHEMA[key]:
            rejected.append(f"{key}={want} (not one of {sorted(SCHEMA[key])})")
            continue
        pat = re.compile(rf"^(\s+{re.escape(key)}:\s*)(\S+)(.*)$")
        for i in range(start + 1, end):
            mm = pat.match(lines[i])
            if mm:
                if mm.group(2) != want:
                    lines[i] = f"{mm.group(1)}{want}{mm.group(3)}"
                    changed.append(f"{key}: {mm.group(2)} -> {want}")
                break
        else:
            lines.insert(end, f"  {key}: {want}")
            end += 1
            changed.append(f"{key}: (absent) -> {want}")

    if changed:
        CONFIG.write_text("\n".join(lines), encoding="utf-8")
    return changed, rejected


def main():
    db_id = _cfg("board.settings_database_id")
    if not db_id:
        print("settings-sync: board.settings_database_id not configured — skipping")
        return
    panel = read_panel(db_id)
    if not panel:
        print("settings-sync: panel returned nothing — leaving the config alone")
        return
    changed, rejected = apply(panel)
    for c in changed:
        print(f"settings-sync: {c}")
    for r in rejected:
        print(f"settings-sync: IGNORED {r}")
    print(f"settings-sync: {len(panel)} read, {len(changed)} applied, {len(rejected)} ignored")


if __name__ == "__main__":
    main()
