"""Report every memory file whose frontmatter would abort a dream pass.

Uses consolidate.py's own parsing so the verdict matches the tool rather than an
approximation of it: _expand_omem_conflicts fans each OMEM CONFLICT block out into every
complete side combination, and each combination must parse as valid, duplicate-free YAML.
A key that appears on two different blocks' sides collides only in the combinations that
take both -- which is why a file can look fine by eye and still fail.
"""
import importlib.util
import pathlib
import sys

# Importing consolidate.py from the memory store would leave a __pycache__ directory in
# the operator's memory repo, where a sync daemon commits whatever it finds.
sys.dont_write_bytecode = True

STORE = pathlib.Path("/Users/andyl/omem-data")

spec = importlib.util.spec_from_file_location("omem_consolidate", STORE / "consolidate.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def check(raw: bytes) -> str | None:
    """Return the error a dream pass would raise for this file, or None.

    _repair_previous_metadata is the tool's own entry point: it tries the plain
    frontmatter first and falls back to the conflict-aware path, which is where a key
    duplicated across two blocks' sides surfaces.
    """
    try:
        mod._repair_previous_metadata(raw)
    except ValueError as exc:
        return str(exc)
    return None


def main() -> int:
    bad = []
    files = sorted(p for p in STORE.glob("*.md") if p.name != "MEMORY.md")
    for path in files:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            bad.append((path.name, f"unreadable: {exc}"))
            continue
        err = check(raw)
        if err:
            bad.append((path.name, err))
    print(f"scanned {len(files)} memory files")
    for name, err in bad:
        print(f"FAIL {name}\n     {err}")
    print(f"{len(bad)} would abort a dream pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
