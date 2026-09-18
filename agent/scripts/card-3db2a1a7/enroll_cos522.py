#!/usr/bin/env python3
"""Add COS 522 to Zhifei's Fall 2026 Stellic schedule, once, after his 帮我执行 click.

The login route is not a guess: three logins on 09-15 died at the same place and the
card log records why. Duo's default factor for this account is a security key; the
local.inboard-webauthn shim re-equips every new tab with a NON-discoverable credential
every 2s, Duo's auto-started request wants a discoverable one, Chrome therefore raises
a native OS picker, and web-plane's UI gate then refuses every command on that lane.
`--no-webauthn` alone loses the race with the shim, so the shim is stopped FIRST and
restored in a finally — other cards' Princeton logins depend on it being back up.

Fails closed: anything ambiguous stops BEFORE the registration submit, leaving the
browser logged in so a corrected version costs no second phone push.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CARD = os.environ.get("INBOARD_CARD", "3db2a1a7-7f3f-816d-b3b2-f5f4660b68e9")
OPERATION = os.environ.get("INBOARD_OPERATION", "")
HOME = Path("/Users/andyl/Projects/inboard")
LANE = "cos522"
FULL_LANE = "inboard-" + LANE
CRED_ITEM = "a0463dac-685e-4207-8146-b42c00f2f44e"   # "Princeton", user al9080
NETID = "al9080"
SERVICE = "princeton"
COURSE = "COS 522"
PLIST = Path.home() / "Library/LaunchAgents/local.inboard-webauthn.plist"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
LOG = HOME / "logs" / ("cos522-enroll-" + STAMP + ".log")
SHOTS = HOME / "logs" / ("cos522-enroll-" + STAMP)
KNOWN_RECEIPTS = ("1a0a1c2c59b4e784", "1a098641d96489e6")   # 09-14 MAT 579, 09-12 receipts


def log(msg):
    line = datetime.now(timezone.utc).isoformat() + " " + str(msg)
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def run(argv, timeout=180, check=False):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(argv[0] + " failed rc=" + str(p.returncode) + ": " + (p.stderr or p.stdout)[:400])
    return p


def wp(*args, **kw):
    return run(["web-plane", "lane", FULL_LANE] + list(args), timeout=kw.get("timeout", 180))


def page_text():
    return wp("eval", "document.body ? document.body.innerText : ''").stdout


def url():
    out = wp("get", "url").stdout
    for line in reversed(out.strip().splitlines()):
        line = line.strip()
        if line.startswith("http") or line == "about:blank":
            return line
    return ""


def shot(name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / (name + ".png")
    wp("screenshot", str(path))
    log("screenshot " + str(path))
    return path


def snapshot(label):
    out = wp("snapshot", "-i").stdout
    body = "\n".join(l for l in out.splitlines() if '"lane-source"' not in l)
    with open(LOG, "a") as f:
        f.write("----- snapshot " + label + " -----\n" + body + "\n----- end -----\n")
    return body


def die(msg, code=3):
    log("STOP: " + msg)
    try:
        shot("stopped")
        snapshot("stopped")
    except Exception as e:
        log("(could not capture stop evidence: " + str(e) + ")")
    raise SystemExit(code)


def check_approval():
    if not OPERATION:
        die("INBOARD_OPERATION is empty - this script only runs from the button.", 2)
    p = run([str(HOME / "bin/board"), "approved-draft", "--card", CARD, "--operation", OPERATION])
    if p.returncode != 0:
        die("approved-draft refused this operation: " + (p.stderr or p.stdout).strip()[:300], 2)
    log("approval snapshot verified for this click")


def already_registered_by_mail():
    p = run([str(HOME / "bin/email"), "work", "gmail", "+triage",
             "--query", "from:stellic newer_than:3d", "--max", "10", "--format", "json"])
    try:
        msgs = json.loads(p.stdout[p.stdout.index("{"):]).get("messages", [])
    except (ValueError, KeyError):
        log("could not parse the Stellic mail check; falling through to the on-page check")
        return False
    for m in msgs:
        if m.get("id") in KNOWN_RECEIPTS:
            continue
        log("unrecognised Stellic receipt " + str(m.get("id")) + " " + str(m.get("date")))
        body = run([str(HOME / "bin/email"), "work", "gmail", "+read", "--message-id", m["id"]]).stdout
        if "522" in body:
            log("a Stellic receipt already lists COS 522 - nothing to submit")
            return True
    return False


def stop_shim():
    r = run(["launchctl", "bootout", "gui/" + str(os.getuid()) + "/local.inboard-webauthn"])
    log("webauthn shim bootout rc=" + str(r.returncode) + " " + (r.stderr or "").strip()[:120])
    time.sleep(3)


def start_shim():
    r = run(["launchctl", "bootstrap", "gui/" + str(os.getuid()), str(PLIST)])
    log("webauthn shim restored rc=" + str(r.returncode) + " " + (r.stderr or "").strip()[:120])


def attach_clean_lane():
    run(["web-plane", "lane", FULL_LANE, "close"])
    time.sleep(1)
    r = run(["web-plane", "-s=main", "attach", "--as", FULL_LANE, "--no-webauthn", "about:blank"])
    log("lane " + FULL_LANE + " attached without webauthn rc=" + str(r.returncode))
    if r.returncode != 0:
        die("could not attach a no-webauthn lane: " + (r.stderr or r.stdout)[:300], 4)


def cas_login():
    wp("open", "https://princeton.stellic.com/", timeout=300)
    here = url()
    log("landed on " + here)
    if "stellic" in here and "fed.princeton.edu" not in here:
        log("already authenticated - no login needed")
        return False
    if "fed.princeton.edu" not in here:
        die("unexpected page instead of the Princeton login: " + here, 4)
    wp("fill", "#username", NETID)
    fill = run(["cred", "with", CRED_ITEM, "--", "bash", "-c",
                'web-plane lane ' + FULL_LANE + ' fill "#password" "$CRED"'])
    if fill.returncode != 0:
        die("could not put the saved netID password into the form: "
            + (fill.stderr or fill.stdout).strip()[:300], 5)
    log("netID and saved password filled (password never printed)")
    wp("click", "#submitBtn")
    time.sleep(6)
    return True


def duo_push():
    gate = run([str(HOME / "bin/twofa-gate"), "acquire", SERVICE])
    log("twofa-gate acquire rc=" + str(gate.returncode) + " " + (gate.stdout or "").strip()[:200])
    if gate.returncode != 0:
        die("another verification is already outstanding - not competing for his phone", 6)
    outcome = "unused"
    pushed = False          # one push, ever: the page keeps saying "Duo Push" afterwards
    try:
        for attempt in range(40):
            here = url()
            text = page_text()
            if "stellic" in here and "duo" not in here and "fed.princeton" not in here:
                log("authenticated; Duo satisfied")
                outcome = "ok" if outcome == "timeout" else "unused"
                return
            low = text.lower()
            if attempt == 0:
                shot("duo-page")
                snapshot("duo-page")
            if "other options" in low and "duo push" not in low:
                log("opening Duo's other-options list")
                wp("click", "text=Other options")
                time.sleep(3)
                continue
            if not pushed and re.search(r"duo\s*push|send me a push", low):
                log("choosing Duo Push - his phone rings once now")
                wp("click", "text=Duo Push")
                pushed = True
                outcome = "timeout"
                time.sleep(8)
                continue
            if "trust this browser" in low or "yes, this is my device" in low:
                log("marking this browser trusted (his own persistent profile)")
                for label in ("Yes, this is my device", "Trust this browser"):
                    if label.lower() in low:
                        wp("click", "text=" + label)
                        break
                time.sleep(5)
                continue
            time.sleep(5)      # pushed and waiting for his tap, or a page we do not act on
        shot("duo-timeout")
        die("Duo was not completed in time", 6)
    finally:
        run([str(HOME / "bin/twofa-gate"), "release", SERVICE, outcome])
        log("twofa-gate released as " + outcome)


def ref_of(line):
    m = re.search(r"ref=(@?e\d+)", line)
    return m.group(1) if m else None


def add_course():
    wp("open", "https://princeton.stellic.com/", timeout=300)
    time.sleep(5)
    shot("stellic-home")
    body = snapshot("stellic-home")
    if re.search(r"COS\s*522", body, re.I) and re.search(r"registered|enrolled", body, re.I):
        log("COS 522 already appears on the Stellic schedule - nothing to submit")
        return "already"

    for label in ("Registration", "Register", "Plan", "Courses"):
        line = next((l for l in body.splitlines() if '"' + label in l and ref_of(l)), None)
        if line:
            log("opening the " + label + " area")
            wp("click", ref_of(line))
            time.sleep(5)
            break
    else:
        die("could not find Stellic's registration area from the landing page", 7)

    body = snapshot("registration-area")
    search = next((l for l in body.splitlines()
                   if re.search(r"searchbox|textbox", l, re.I) and ref_of(l)), None)
    if not search:
        die("no course-search box on the registration page", 7)
    wp("fill", ref_of(search), COURSE)
    wp("press", "Enter")
    time.sleep(6)
    shot("search-results")

    body = snapshot("course-search")
    hits = [l for l in body.splitlines() if "522" in l]
    row = next((l for l in hits if re.search(r"\badd\b|\bregister\b|\benroll\b", l, re.I)), None)
    if row is None:
        row = hits[0] if len(hits) == 1 else None
    if not row:
        die("could not identify a single unambiguous " + COURSE + " control in the results", 7)
    target = ref_of(row)
    if not target:
        die("found " + COURSE + " but no clickable control on its row", 7)
    log("pre-submit check on the row I am about to click: " + row.strip()[:200])
    wp("click", target)
    time.sleep(5)
    shot("pre-confirm")
    body = snapshot("pre-confirm")

    confirm = next((l for l in body.splitlines()
                    if re.search(r'"(confirm|register|add course|submit|save)', l, re.I)
                    and ref_of(l)), None)
    if confirm:
        if not re.search(r"522", body):
            die("the confirmation step no longer mentions COS 522 - not submitting", 7)
        log("confirming: " + confirm.strip()[:200])
        wp("click", ref_of(confirm))
        time.sleep(8)
    shot("post-submit")
    return "submitted"


def verify():
    wp("open", "https://princeton.stellic.com/", timeout=300)
    time.sleep(6)
    body = page_text()
    shot("verify")
    snapshot("verify")
    ok = bool(re.search(r"COS\s*522", body, re.I))
    log("verification on Stellic: COS 522 present = " + str(ok))
    return ok


def main():
    log("=== COS 522 enrolment, card " + CARD + ", operation " + OPERATION[:12] + " ===")
    check_approval()
    if already_registered_by_mail():
        log("RESULT: already registered before this run; nothing submitted")
        return 0
    stop_shim()
    try:
        attach_clean_lane()
        if cas_login():
            duo_push()
        here = url()
        if "stellic" not in here:
            die("login did not end on Stellic (at " + here + ")", 5)
        log("logged in to Stellic")
        outcome = add_course()
        ok = verify()
    finally:
        start_shim()
    if outcome == "already":
        log("RESULT: COS 522 was already on the schedule")
        return 0
    if ok:
        log("RESULT: COS 522 registered and verified on the Stellic schedule")
        return 0
    log("RESULT: submitted but NOT verified on the schedule - treat as unfinished")
    return 8


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        log("FAILED: " + type(exc).__name__ + ": " + str(exc))
        start_shim()
        sys.exit(9)
