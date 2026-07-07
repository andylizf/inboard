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


# --- Canonical board schema ------------------------------------------------
# The STABLE part is the KEYS below (new/researching/... , item/date/... ). The DISPLAY strings are
# LOCALE/DEPLOYMENT config under `board.schema.*`, so inboard can drive a board in ANY language (e.g. an
# existing Chinese board) without touching code or the agent's standing orders. Defaults are English.
# `agent/CLAUDE.md` always writes the English canonical names; the `board` CLI translates them to the
# deployment's configured display strings on write (see status_name()/daily_type_name()), and filters/writes
# in bin/board read STATUS/DAILY_* below — so both sides agree in whatever language the board uses.
STATUS_ORDER = ["new", "researching", "draft", "awaiting", "done", "unsub"]
_STATUS_DEFAULT = {
    "new": "📥 New", "researching": "🔍 Researching", "draft": "✍️ Draft ready",
    "awaiting": "⏳ Awaiting reply", "done": "✅ Done", "unsub": "🚫 Unsubscribed",
}
_ACTIONS_DEFAULT = ["▶️ Continue / redo", "📤 Sent — awaiting reply", "✅ Done / ignore"]
# Non-empty placeholder so Notion always renders the Action property as a tappable chip in its lightweight
# preview (it hides EMPTY properties there). Handlers treat it as no-action.
_ACTION_PLACEHOLDER_DEFAULT = "👉 Pick action"
_DAILY_TYPES_DEFAULT = {"unsub": "🚫 Unsubscribe", "done": "✅ Done", "draft": "✉️ Draft", "fyi": "ℹ️ FYI"}
_DAILY_PROPS_DEFAULT = {"item": "Item", "date": "Date", "type": "Type", "account": "Account", "detail": "Detail"}


def _schema(key, default):
    v = get("board.schema." + key)
    return v if v else default


def __getattr__(name):  # PEP 562 — resolve these from config lazily (no config read at import time)
    if name == "STATUS":            return _schema("status", _STATUS_DEFAULT)
    if name == "STATUS_NAMES":      s = _schema("status", _STATUS_DEFAULT); return [s.get(k, k) for k in STATUS_ORDER]
    if name == "ACTIONS":           return _schema("actions", _ACTIONS_DEFAULT)
    if name == "ACTION_PLACEHOLDER":return _schema("action_placeholder", _ACTION_PLACEHOLDER_DEFAULT)
    if name == "DAILY_TYPES":       return _schema("daily_types", _DAILY_TYPES_DEFAULT)
    if name == "DAILY_PROPS":       return _schema("daily_props", _DAILY_PROPS_DEFAULT)
    raise AttributeError(name)


def status_name(v):
    """Resolve a status the agent supplies (a key like 'done', or the English canonical '✅ Done', or an
    already-correct display string) to the deployment's configured Status display value."""
    st = _schema("status", _STATUS_DEFAULT)
    if v in st:                                  # it's a key
        return st[v]
    for k, d in _STATUS_DEFAULT.items():         # it's an English canonical display → map via key
        if v == d:
            return st.get(k, v)
    return v                                     # already a config display, or unknown → pass through


def daily_type_name(v):
    dt = _schema("daily_types", _DAILY_TYPES_DEFAULT)
    if v in dt:
        return dt[v]
    for k, d in _DAILY_TYPES_DEFAULT.items():
        if v == d:
            return dt.get(k, v)
    return v
