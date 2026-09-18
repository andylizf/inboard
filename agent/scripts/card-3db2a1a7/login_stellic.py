#!/usr/bin/env python3
"""Log in to Stellic and stop at its home page. No registration, nothing submitted.

The route changed on 2026-09-18. Until then every attempt stopped the webauthn shim
first and attached the lane with --no-webauthn, so Duo would fall back to a list of
other factors; on 09-18 Stellic stopped falling back and the run died on the
"Use your security key" page. The shim now files the enrolled key as DISCOVERABLE
(bin/webauthn-shim, commit bf7ccf8), which is what Duo's auto-started, allow-list-free
request asks for. So the shim stays UP and the lane keeps WebAuthn: the key answers
Duo in the page and no phone is involved.

The 2 s equip race is closed by attaching to about:blank first and confirming in the
shim's log that this lane's own tab was equipped before any Duo page loads. A virtual
authenticator's scope is the CDP session, not the document, so it survives the
navigation to Stellic (measured 2026-09-18, MyClaw scripts/webauthn-cdp-nav-probe).

Fallback, only if the key is not accepted: "Other options" -> "Duo Push", one push,
through twofa-gate. If the macOS passkey sheet appears instead, every command on the
lane is refused and the run stops there with evidence rather than fighting it.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path("/Users/andyl/Projects/inboard")
LANE = "inboard-cos522login"
CRED_ITEM = "a0463dac-685e-4207-8146-b42c00f2f44e"   # "Princeton", user al9080
NETID = "al9080"
SERVICE = "princeton"
SHIM_LOG = HOME / "logs" / "webauthn-main.log"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
LOG = HOME / "logs" / ("cos522-login-" + STAMP + ".log")
SHOTS = HOME / "logs" / ("cos522-login-" + STAMP)


def log(msg):
    line = datetime.now(timezone.utc).isoformat() + " " + str(msg)
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def run(argv, timeout=180):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def wp(*args, timeout=180):
    return run(["web-plane", "lane", LANE] + list(args), timeout=timeout)


def blocked(p):
    """web-plane refuses every command while a native modal is up."""
    return "UI_BLOCKED" in (p.stdout + p.stderr)


def url():
    out = wp("get", "url").stdout
    for line in reversed(out.strip().splitlines()):
        line = line.strip()
        if line.startswith("http") or line == "about:blank":
            return line
    return ""


def page_text():
    return wp("eval", "document.body ? document.body.innerText : ''").stdout


def shot(name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / (name + ".png")
    wp("screenshot", str(path))
    log("screenshot " + str(path))
    return path


def snapshot(label):
    p = wp("snapshot", "-i")
    body = "\n".join(l for l in p.stdout.splitlines() if '"lane-source"' not in l)
    with open(LOG, "a") as f:
        f.write("----- snapshot " + label + " -----\n" + body + "\n----- end -----\n")
    if blocked(p):
        log("NOTE: snapshot came back UI_BLOCKED — a native modal is up")
    return body


def die(msg, code=3):
    log("STOP: " + msg)
    try:
        shot("stopped")
        snapshot("stopped")
    except Exception as e:
        log("(could not capture stop evidence: " + str(e) + ")")
    raise SystemExit(code)


def lane_target_id():
    """The lane-monitor worker carries its tab's target id on its command line."""
    p = run(["ps", "-axo", "command"])
    for line in p.stdout.splitlines():
        if "lane-monitor.js" in line and '"lane":"' in line:
            blob = line[line.index("{"):]
            try:
                cfg = json.loads(blob[:blob.index("}") + 1])
            except ValueError:
                continue
            if cfg.get("lane") in (LANE, LANE.replace("inboard-", "", 1)):
                return cfg.get("targetId"), cfg.get("webauthnDisabled")
    return None, None


def attach_lane_with_key():
    run(["web-plane", "lane", LANE, "close"])
    time.sleep(1)
    r = run(["web-plane", "-s=main", "attach", "--as", LANE, "about:blank"])
    log("lane " + LANE + " attached WITH webauthn rc=" + str(r.returncode))
    if r.returncode != 0:
        die("could not attach the lane: " + (r.stderr or r.stdout)[:300], 4)
    time.sleep(3)
    tid, disabled = lane_target_id()
    log("lane tab target=" + str(tid) + " webauthnDisabled=" + str(disabled))
    if disabled:
        die("the lane came up with WebAuthn disabled — the key could not answer", 4)
    if not tid:
        log("WARNING: could not read the lane's target id; falling back to a log-tail check")
    # The shim must have equipped THIS tab before any Duo page loads.
    for attempt in range(10):
        tail = SHIM_LOG.read_text().splitlines()[-40:] if SHIM_LOG.exists() else []
        hits = [l for l in tail if "equipped" in l and (tid or "") in l and "creds=1" in l]
        if tid and hits:
            log("shim equipped this tab: " + hits[-1])
            return
        if not tid and any("creds=1" in l for l in tail):
            log("shim log shows a recent equip with creds=1 (tab id unknown)")
            return
        time.sleep(2)
    die("the security-key service never reported equipping this tab — not spending a login", 4)


def cas_login():
    wp("open", "https://princeton.stellic.com/", timeout=300)
    time.sleep(4)
    here = url()
    log("landed on " + here)
    if "stellic" in here and "fed.princeton.edu" not in here:
        log("already authenticated — no password needed")
        return False
    if "fed.princeton.edu" not in here:
        die("unexpected page instead of the Princeton login: " + here, 4)
    shot("cas-page")
    wp("fill", "#username", NETID)
    fill = run(["cred", "with", CRED_ITEM, "--", "bash", "-c",
                'web-plane lane ' + LANE + ' fill "#password" "$CRED"'])
    if fill.returncode != 0:
        die("could not put the saved netID password into the form: "
            + (fill.stderr or fill.stdout).strip()[:300], 5)
    log("netID and saved password filled (password never printed)")
    wp("click", "#submitBtn")
    time.sleep(6)
    return True


def wait_for_duo():
    """Give the local key its chance. Only if it is refused do we touch his phone."""
    gate_held = False
    outcome = "unused"
    pushed = False
    modal_seen = False
    deadline = time.time() + 300
    try:
        while time.time() < deadline:
            here = url()
            if "stellic" in here and "duo" not in here and "fed.princeton" not in here:
                log("authenticated — landed on " + here)
                return "ok"
            p = wp("eval", "document.body ? document.body.innerText : ''")
            if blocked(p):
                if not modal_seen:
                    modal_seen = True
                    log("the macOS passkey sheet is up: web-plane is refusing commands on this lane")
                time.sleep(5)
                continue
            text = p.stdout
            low = text.lower()
            if modal_seen:
                log("the native sheet cleared on its own; commands work again")
                modal_seen = False
            if not pushed and re.search(r"use your security key|verify it's you", low):
                log("Duo is asking for the security key; waiting for the local key to answer")
                if time.time() > deadline - 240:
                    pass
                time.sleep(5)
                continue
            if "other options" in low and "duo push" not in low:
                log("the key was not accepted; opening Duo's other-options list")
                c = wp("click", "text=Other options")
                if blocked(c):
                    log("could not open other options: a native modal is swallowing clicks")
                time.sleep(3)
                continue
            if not pushed and re.search(r"duo\s*push|send me a push", low):
                if not gate_held:
                    gate = run([str(HOME / "bin/twofa-gate"), "acquire", SERVICE])
                    log("twofa-gate acquire rc=" + str(gate.returncode) + " "
                        + (gate.stdout or "").strip()[:200])
                    if gate.returncode != 0:
                        die("another verification is already outstanding — not competing for his phone", 6)
                    gate_held = True
                log("choosing Duo Push — his phone rings once now")
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
            time.sleep(5)
        return "modal" if modal_seen else "timeout"
    finally:
        if gate_held:
            if outcome == "timeout" and "stellic" in url():
                outcome = "ok"
            run([str(HOME / "bin/twofa-gate"), "release", SERVICE, outcome])
            log("twofa-gate released as " + outcome)


def main():
    log("=== COS 522 card: Stellic LOGIN ONLY, nothing is submitted ===")
    attach_lane_with_key()
    needed_password = cas_login()
    if needed_password:
        shot("after-password")
        snapshot("after-password")
        result = wait_for_duo()
    else:
        result = "ok"
    here = url()
    if result == "ok" and "stellic" in here:
        time.sleep(4)
        shot("stellic-home")
        body = snapshot("stellic-home")
        log("RESULT: logged in to Stellic, at " + here)
        log("COS 522 visible on the landing page = "
            + str(bool(re.search(r"COS\s*522", body, re.I))))
        return 0
    if result == "modal":
        shot("blocked-by-native-sheet")
        log("RESULT: the macOS passkey sheet blocked the lane; still at " + here)
        return 7
    shot("duo-unfinished")
    snapshot("duo-unfinished")
    log("RESULT: Duo not completed; still at " + here)
    return 6


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        log("FAILED: " + type(exc).__name__ + ": " + str(exc))
        sys.exit(9)
