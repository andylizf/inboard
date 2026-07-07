"""inboard config loader + canonical board schema.

Every inboard script (bin/*, engines/*, setup/*) reads its personal/deployment settings
from here so nothing is hardcoded. Depends on PyYAML (a uv-managed dependency — see
pyproject.toml; `inboard init` runs `uv sync`, and the engines put .venv/bin first on PATH
so these CLIs get the venv's python).

Resolution order for the config file:
    $INBOARD_CONFIG  →  $INBOARD_HOME/inboard.config.yaml  →  <repo>/inboard.config.yaml
"""
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def home():
    """Install root (the repo dir). Overridable with $INBOARD_HOME."""
    return os.environ.get("INBOARD_HOME") or os.path.dirname(_THIS_DIR)


def config_path():
    return os.environ.get("INBOARD_CONFIG") or os.path.join(home(), "inboard.config.yaml")


def _parse_yaml(text):
    try:
        import yaml
    except ImportError:
        sys.exit("inboard: PyYAML is not installed — run `uv sync` in the inboard repo "
                 "(or `inboard init`), then retry.")
    return yaml.safe_load(text)


_CACHE = None


def load():
    global _CACHE
    if _CACHE is None:
        p = config_path()
        if not os.path.exists(p):
            sys.exit(f"inboard: config not found at {p} — run `inboard init` "
                     f"(or point $INBOARD_CONFIG at your config file).")
        with open(p) as f:
            _CACHE = _parse_yaml(f.read()) or {}
    return _CACHE


def get(path, default=None):
    """Dotted lookup, e.g. get('board.database_id') or get('schedule.pull_interval_seconds', 300)."""
    cur = load()
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def expand(p):
    return os.path.expanduser(p) if isinstance(p, str) else p


# --- Accounts ---------------------------------------------------------------
def accounts():
    return load().get("accounts") or []


def account(account_id):
    for a in accounts():
        if a.get("id") == account_id:
            return a
    return None


def account_label(account_id):
    a = account(account_id)
    return (a.get("label") or a.get("id")) if a else account_id


def account_labels():
    return [(a.get("label") or a.get("id")) for a in accounts()]


def label_to_id(label):
    """Board's `Account` property stores the human label; map it back to the stable id."""
    for a in accounts():
        if (a.get("label") or a.get("id")) == label or a.get("id") == label:
            return a.get("id")
    return label


# --- Canonical board schema (create_board, the `board` CLI, and CLAUDE.md must agree) ---
STATUS = {
    "new":         "📥 New",
    "researching": "🔍 Researching",
    "draft":       "✍️ Draft ready",
    "awaiting":    "⏳ Awaiting reply",
    "done":        "✅ Done",
    "unsub":       "🚫 Unsubscribed",
}
STATUS_ORDER = ["new", "researching", "draft", "awaiting", "done", "unsub"]
STATUS_NAMES = [STATUS[k] for k in STATUS_ORDER]

# Non-empty placeholder so Notion always renders the Action property as a tappable chip
# in its lightweight preview (it hides EMPTY properties there). Handlers treat it as no-action.
ACTION_PLACEHOLDER = "👉 Pick action"

# The tappable Action chips the operator picks on a card (a no-typing decision → action-handler).
ACTIONS = ["▶️ Continue / redo", "📤 Sent — awaiting reply", "✅ Done / ignore"]

DAILY_TYPES = ["🚫 Unsubscribe", "✅ Done", "✉️ Draft", "ℹ️ FYI"]
