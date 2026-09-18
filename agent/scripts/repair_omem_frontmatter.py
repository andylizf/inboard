"""Repair the three memory files that would abort a dream pass (2026-09-18).

Two distinct faults, both fixed without changing a single character of meaning:

1. An unquoted `description:` whose value contains a `colon + space`, which YAML reads as
   a nested mapping. Fix: wrap the value in double quotes, text preserved byte for byte.
   Same fault as 2026-09-09..11 (project-omem-consolidate-oauth-token-401-20260909).

2. `title:` sitting inside TWO different OMEM CONFLICT blocks, on sides that can be taken
   together. consolidate.py fans the blocks out into every side combination, so the
   combination taking both sees metadata with a duplicate key. Both sides carry the SAME
   value -- the machines disagreed about where the line sits, not what it says -- so the
   fix hoists that one line out to an unconditional position and leaves every genuine
   disagreement (description, project, event_time) inside its block for the dream to
   adjudicate. Conflict blocks are content to merge, never cleanup
   (project-omem-host-write-clobbers-conflict-block).
"""
import pathlib
import sys

STORE = pathlib.Path("/Users/andyl/omem-data")


def quote_description(path: pathlib.Path) -> str:
    text = path.read_text()
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not line.startswith("description: "):
            continue
        value = line[len("description: "):]
        if value[:1] in {'"', "'"}:
            return f"{path.name}: description already quoted, skipped"
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines[i] = f'description: "{escaped}"'
        path.write_text("\n".join(lines))
        return f"{path.name}: quoted description ({len(value)} chars preserved)"
    return f"{path.name}: no top-level description line found"


def hoist_duplicate_title(path: pathlib.Path) -> str:
    text = path.read_text()
    lines = text.split("\n")
    title_idx = [i for i, l in enumerate(lines) if l.startswith("  title: ")]
    if len(title_idx) != 2:
        return f"{path.name}: expected 2 title lines, found {len(title_idx)}"
    values = {lines[i] for i in title_idx}
    if len(values) != 1:
        return f"{path.name}: the two title lines DIFFER, not safe to hoist: {values}"
    title_line = lines[title_idx[0]]
    for i in reversed(title_idx):
        del lines[i]
    anchor = next(i for i, l in enumerate(lines) if l == "  type: project")
    lines.insert(anchor + 1, title_line)
    path.write_text("\n".join(lines))
    return f"{path.name}: hoisted the identical title out of both conflict blocks"


def main() -> int:
    print(quote_description(STORE / "project-cheesex-box-uptime-heartbeat-redesign.md"))
    print(quote_description(STORE / "reference-laptop-google-drive-mount.md"))
    print(hoist_duplicate_title(STORE / "project-aws-account-hold-990467762750.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
