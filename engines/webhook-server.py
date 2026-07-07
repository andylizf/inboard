#!/usr/bin/env python3
"""ENGINE 2 — the Notion webhook receiver (runs persistently, e.g. behind a Tailscale Funnel / tunnel).

- Handles Notion's one-time verification handshake (stores the verification_token = signing secret).
- Verifies X-Notion-Signature (HMAC-SHA256 of the raw body) on every event.
- On comment.created / page.properties_updated for the board → fires the matching handler to react instantly.
Responds within Notion's 3s window, then handles asynchronously.
"""
import hashlib
import hmac
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.environ.get("INBOARD_HOME") or
                                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import ibconfig as C  # noqa: E402

HOME = C.home()
ENGINES = os.path.join(HOME, "engines")
STATE = os.environ.get("INBOARD_STATE") or os.path.join(HOME, "state")
LOGS = os.environ.get("INBOARD_LOGS") or os.path.join(HOME, "logs")
SECRET_FILE = os.path.join(STATE, "notion_webhook_secret")
LOG = os.path.join(LOGS, "webhook.log")
PORT = int(C.get("board.webhook_port", 8787))


def log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")


def secret():
    try:
        return open(SECRET_FILE).read().strip()
    except Exception:
        return None


def sig_ok(raw, header):
    s = secret()
    if not s:
        return False
    mac = hmac.new(s.encode(), raw, hashlib.sha256).hexdigest()
    for cand in (mac, "sha256=" + mac):  # tolerate either format
        if hmac.compare_digest(cand, header or ""):
            return True
    return False


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"alive")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); raw = self.rfile.read(n)
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        # 1) verification handshake — store token, ack
        if "verification_token" in data:
            open(SECRET_FILE, "w").write(data["verification_token"]); os.chmod(SECRET_FILE, 0o600)
            log("verification_token stored")
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok"); return
        # 2) verify signature
        if not sig_ok(raw, self.headers.get("X-Notion-Signature", "")):
            log("BAD signature; header=" + str(self.headers.get("X-Notion-Signature"))[:40])
            self.send_response(401); self.end_headers(); return
        # 3) ack fast, then react
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        ev = data.get("type", "")
        log(f"event={ev} entity={json.dumps(data.get('entity', {}))[:120]}")
        # Human comment → comment-handler (instant reaction to what they typed).
        if ev == "comment.created":
            subprocess.Popen(["bash", os.path.join(ENGINES, "comment-handler.sh"), json.dumps(data)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Property change → action-handler. Fires for the agent's OWN edits too, so the handler cheap-gates
        # on whether an Action is actually set (a Notion GET, no claude) — only a user-picked Action runs anything.
        elif ev == "page.properties_updated":
            eid = data.get("entity", {}).get("id")
            if eid:
                subprocess.Popen(["bash", os.path.join(ENGINES, "action-handler.sh"), eid],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    log(f"webhook server starting on 127.0.0.1:{PORT}")
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
