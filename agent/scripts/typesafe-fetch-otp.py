#!/usr/bin/env python3
"""Wait for TypeSafe's one-time sign-in code in andylizf@gmail.com and print it.

Used only by typesafe-console-signup.sh, which triggers the code first and passes the
epoch second it triggered at; any code older than that is a leftover from an earlier run
and is ignored on purpose (a stale code would fail the form and burn an attempt).
Prints the six digits on stdout and nothing else; exits 1 if none arrives in time.
"""
import json
import re
import subprocess
import sys
import time

SENDER = "login@typesafe.ai"
ACCOUNT = "personal"
CODE_RE = re.compile(r"\b(\d{6})\b")


def gws(*args):
    out = subprocess.run(["email", ACCOUNT, "gmail", *args],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"email {' '.join(args)} failed: {out.stderr.strip()[:400]}")
    return out.stdout


def newest_code(after_epoch):
    raw = gws("users", "messages", "list", "--params",
              json.dumps({"userId": "me", "q": f"from:{SENDER}", "maxResults": 5}))
    msgs = json.loads(raw[raw.index("{"):]).get("messages") or []
    for m in msgs:
        raw_msg = gws("users", "messages", "get", "--params",
                      json.dumps({"userId": "me", "id": m["id"], "format": "metadata",
                                  "metadataHeaders": ["Subject"]}))
        meta = json.loads(raw_msg[raw_msg.index("{"):])
        # internalDate is milliseconds since epoch, set by Gmail on receipt.
        if int(meta.get("internalDate", 0)) / 1000 < after_epoch:
            continue
        body = gws("+read", "--message-id", m["id"])
        hit = CODE_RE.search(body)
        if hit:
            return hit.group(1), m["id"]
    return None, None


def main():
    after_epoch = float(sys.argv[1])
    deadline = time.time() + 180
    while time.time() < deadline:
        code, msgid = newest_code(after_epoch)
        if code:
            print(code)
            print(f"code read from message {msgid}", file=sys.stderr)
            return 0
        time.sleep(5)
    print(f"no code from {SENDER} arrived within 180s of the request", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
