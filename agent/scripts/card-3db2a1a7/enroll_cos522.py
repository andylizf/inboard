#!/usr/bin/env python3
"""Register COS 522 on Zhifei's Fall 2026 Stellic schedule, once, after his 📤 click.

Both halves of this were measured on 2026-09-19, not guessed.

LOGIN. Duo's default factor for this account is a security key. Earlier versions stopped
the local.inboard-webauthn shim and attached the lane with --no-webauthn so Duo would
offer its other factors; on 09-18 Stellic stopped falling back and the run died on
"Use your security key". The shim now stays UP and the lane keeps WebAuthn. The key is
still not accepted by Stellic's Duo integration — Chrome raises the macOS passkey sheet,
which sits over the page — but that sheet only swallows real input events: web-plane's
`eval` still runs, so a JavaScript .click() reaches "Other options" straight through it
and Duo Push is one click away. That is what unwedges a login this machine could not
finish for four days. One push, gated, and the code Duo shows must reach him fast.

REGISTRATION. Stellic does not register from a search box. COS 522 is already in his
Fall 2026 plan but has no section, and the course panel says so: "You need to select a
section before you can register for this class." So: open the scheduler, pick the one
LECTURE section (Lec L01, hidden behind a filter until "show all"), then Start
Registration. Its seat count reads 0, so the submit may be refused unless the
department's 09-15 clearance is recorded as an override; that is reported, not worked
around.

Fails closed: anything ambiguous stops BEFORE the submit, and nothing that drops, swaps
or removes a course he already has is ever clicked.
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
HELD = ("COS 433", "COS 585", "COS 551", "MAT 579")   # already registered - never touch
SHIM_LOG = HOME / "logs" / "webauthn-main.log"
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


def run(argv, timeout=180):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def wp(*args, timeout=180):
    return run(["web-plane", "lane", FULL_LANE] + list(args), timeout=timeout)


def clean(p):
    return "\n".join(l for l in p.stdout.splitlines()
                     if '"lane-source"' not in l and '"UI_BLOCKED"' not in l)


def js(expr):
    """The one command a native modal cannot block."""
    out = clean(wp("eval", expr)).strip()
    try:
        return json.loads(out) if out else ""
    except ValueError:
        return out


def url():
    for line in reversed(clean(wp("get", "url")).splitlines()):
        line = line.strip()
        if line.startswith("http") or line == "about:blank":
            return line
    return ""


def page_text():
    return js("document.body ? document.body.innerText : ''") or ""


def shot(name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / (name + ".png")
    wp("screenshot", str(path))
    log("screenshot " + str(path))
    return path


def snapshot(label):
    body = clean(wp("snapshot", "-i"))
    with open(LOG, "a") as f:
        f.write("----- snapshot " + label + " -----\n" + body + "\n----- end -----\n")
    return body


def ref_of(line):
    m = re.search(r"ref=(@?e\d+)", line)
    return m.group(1) if m else None


def find_ref(body, pattern):
    """The single snapshot line matching pattern, or None if it is not unique."""
    hits = [l for l in body.splitlines() if re.search(pattern, l, re.I) and ref_of(l)]
    if len(hits) != 1:
        return None, hits
    return ref_of(hits[0]), hits


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


# ---------------------------------------------------------------- login


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
            if cfg.get("lane") in (FULL_LANE, LANE):
                return cfg.get("targetId"), cfg.get("webauthnDisabled")
    return None, None


def attach_lane_with_key():
    """Attach WITH WebAuthn and prove the key is on this tab before a Duo page loads."""
    run(["web-plane", "lane", FULL_LANE, "close"])
    time.sleep(1)
    r = run(["web-plane", "-s=main", "attach", "--as", FULL_LANE, "about:blank"])
    log("lane " + FULL_LANE + " attached WITH webauthn rc=" + str(r.returncode))
    if r.returncode != 0:
        die("could not attach the lane: " + (r.stderr or r.stdout)[:300], 4)
    time.sleep(3)
    tid, disabled = lane_target_id()
    log("lane tab target=" + str(tid) + " webauthnDisabled=" + str(disabled))
    if disabled:
        die("the lane came up with WebAuthn disabled - the key could not answer", 4)
    for _ in range(10):
        tail = SHIM_LOG.read_text().splitlines()[-40:] if SHIM_LOG.exists() else []
        if tid and any("equipped" in l and tid in l and "creds=1" in l for l in tail):
            log("the security-key service equipped this tab")
            return
        if not tid and any("creds=1" in l for l in tail):
            log("the security-key service reported a recent equip (tab id unknown)")
            return
        time.sleep(2)
    die("the security-key service never reported equipping this tab - not spending a login", 4)


def cas_login():
    wp("open", "https://princeton.stellic.com/", timeout=300)
    time.sleep(4)
    here = url()
    log("landed on " + here)
    if "stellic" in here and "fed.princeton.edu" not in here:
        log("already authenticated - no password needed")
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


CLICK_TEXT = """
(() => {
  const want = new RegExp(%s, 'i');
  const els = [...document.querySelectorAll(%s)];
  const hit = els.find(e => want.test((e.textContent||'').trim()));
  if (!hit) return 'miss';
  hit.click();
  return 'clicked: ' + (hit.textContent||'').trim().slice(0,60);
})()
"""


def js_click(pattern, selector="'a,button,[role=button]'"):
    return js(CLICK_TEXT % (json.dumps(pattern), selector))


def duo():
    """Answer Duo. The key is tried first; a push is the fallback, once, gated."""
    gate_held = False
    outcome = "unused"
    pushed = False
    deadline = time.time() + 330
    try:
        while time.time() < deadline:
            here = url()
            if "stellic" in here and "duo" not in here and "fed.princeton" not in here:
                log("authenticated - Duo satisfied")
                if pushed:
                    outcome = "ok"
                return
            low = (page_text() or "").lower()
            if not low:
                time.sleep(5)
                continue
            if re.search(r"use your security key|verify it's you", low) and "other options" in low:
                # The sheet is up and the key will not answer; JS reaches the button anyway.
                log("the key was not accepted; opening Duo's other-options list in the page")
                log(js_click(r"^\\s*Other options\\s*$"))
                time.sleep(4)
                continue
            if not pushed and re.search(r"select an option to log in", low) and "duo push" in low:
                gate = run([str(HOME / "bin/twofa-gate"), "acquire", SERVICE])
                log("twofa-gate acquire rc=" + str(gate.returncode) + " "
                    + (gate.stdout or "").strip()[:200])
                if gate.returncode != 0:
                    die("another verification is already outstanding - not competing for his phone", 6)
                gate_held = True
                log("choosing Duo Push - his phone rings once now")
                log(js_click(r"^\\s*Duo Push", "'button.auth-method'"))
                pushed = True
                outcome = "timeout"
                time.sleep(6)
                # Duo shows a matching code he has to type. He cannot approve without it.
                code = js("(() => { const m = (document.body.innerText||'')"
                          ".match(/\\\\b(\\\\d{3})\\\\b\\\\s*\\\\n?\\\\s*Sent to/); return m ? m[1] : ''; })()")
                if code:
                    log("Duo verification code shown on the page: " + str(code))
                    run([str(HOME / "bin/board"), "reply", "--card", CARD, "--text",
                         "【现在，约 60 秒内】你手机（尾号 1608）刚收到一次 Duo 验证，是我在替你把 COS 522 加进 "
                         "Stellic 秋季课表。打开 Duo Mobile，输入验证码 " + str(code) + " 就能通过。"])
                    log("the code was posted to the card")
                else:
                    log("no matching code on the page; it is a plain approve-or-deny push")
                continue
            if "trust this browser" in low or "yes, this is my device" in low:
                log("marking this browser trusted (his own persistent profile)")
                log(js_click(r"yes, this is my device|trust this browser"))
                time.sleep(5)
                continue
            time.sleep(5)
        shot("duo-timeout")
        die("Duo was not completed in time", 6)
    finally:
        if gate_held:
            run([str(HOME / "bin/twofa-gate"), "release", SERVICE, outcome])
            log("twofa-gate released as " + outcome)


# ---------------------------------------------------------------- registration


def registration_state():
    """('registered'|'planned'|'absent', page text) for COS 522, read off the home page.

    Measured 09-19: the scheduler's course rail is aria-label text, absent from
    innerText, and neither view carries a REGISTERED heading - the earlier reader
    saw only the week calendar and called a present course absent. The home page's
    "Fall 2026" course list is where the status word lives: a code line, then the
    title, then "Enrolled" or "Planned" (or nothing while it still has no section).
    That list is the authority here.
    """
    wp("open", "https://stellic.princeton.edu/app/home", timeout=300)
    time.sleep(8)
    body = page_text()
    lines = [l.strip() for l in body.splitlines()]
    hits = [i for i, l in enumerate(lines) if re.fullmatch(r"COS\s*522", l)]
    if not hits:
        return "absent", body
    block = []
    for l in lines[hits[-1] + 1:]:
        if re.fullmatch(r"[A-Z]{2,4}\s*\d{3}[A-Z]?", l):
            break
        block.append(l)
    label = " ".join(block)
    log("home page reads COS 522 as: " + (label[:120] or "(no status word yet)"))
    return ("registered" if re.search(r"\bEnrolled\b", label) else "planned"), body


def open_scheduler():
    wp("open", "https://princeton.stellic.com/", timeout=300)
    time.sleep(6)
    if "stellic" not in url():
        die("not on Stellic after opening it: " + url(), 5)
    body = snapshot("stellic-home")
    ref, hits = find_ref(body, r'button "Start Registration"')
    if not ref:
        die("could not find one Start Registration button on the home page ("
            + str(len(hits)) + " candidates)", 7)
    wp("click", ref)
    time.sleep(7)
    if "scheduler" not in url():
        die("Start Registration did not open the scheduler (at " + url() + ")", 7)
    shot("scheduler")
    log("on the scheduler at " + url())


def pick_section():
    body = snapshot("scheduler")
    ref, hits = find_ref(body, r'button "select a section"')
    if not ref:
        # No such control can also mean the section is already attached: the rail
        # row then names it instead of saying "No section selected".
        rail = [l for l in body.splitlines() if re.search(r'COS\s*522', l)]
        if rail and not any("No section selected" in l for l in rail):
            log("COS 522 already carries a section: " + rail[0].strip()[:160])
            return "picked"
        die("no single 'select a section' control for " + COURSE
            + " (" + str(len(hits)) + " candidates)", 7)
    wp("click", ref)
    time.sleep(5)
    body = snapshot("course-panel")
    if not re.search(r"Computational Complexity", body, re.I):
        die("the panel that opened is not COS 522's", 7)

    show_all, _ = find_ref(body, r'show all"')
    if show_all:
        log("the section list is filtered; showing all sections")
        wp("click", show_all)
        time.sleep(4)
        body = snapshot("sections-shown")

    rows = [l for l in body.splitlines()
            if re.search(r'button "Lec [A-Z]?\d+', l) and ref_of(l)]
    if len(rows) != 1:
        die("expected exactly one lecture section for " + COURSE + ", saw "
            + str(len(rows)), 7)
    log("the one section on offer: " + rows[0].strip()[:160])
    if re.search(r"\b0\b", rows[0]):
        log("NOTE: this section's seat count reads 0 - the submit may be refused")
    # The row's own child button is the one that selects it.
    idx = body.splitlines().index(rows[0])
    child = next((ref_of(l) for l in body.splitlines()[idx + 1:idx + 4]
                  if re.match(r"\s+- button \[ref=e\d+\]", l)), None)
    wp("click", child or ref_of(rows[0]))
    time.sleep(5)
    shot("section-picked")
    body = snapshot("section-picked")
    if re.search(r"No [Ss]ection [Ss]elected", body):
        die("COS 522 still shows no section after picking Lec L01", 7)
    log("a section is now attached to " + COURSE)
    close, _ = find_ref(body, r'^\s+- button "close" \[ref=')
    if close:
        wp("click", close)
        time.sleep(3)
    return "picked"


SELECT_ONLY = """
(() => {
  const host = [...document.querySelectorAll('*')].find(e => e.shadowRoot);
  if (!host) return 'no registration app';
  const boxes = [...host.shadowRoot.querySelectorAll('[data-testid=registration-row-checkbox]')];
  if (!boxes.length) return 'no row checkboxes';
  const ticked = b => [...b.querySelectorAll('path')]
      .some(p => /zm-9 14-5/.test(p.getAttribute('d') || ''));
  const out = [];
  for (const b of boxes) {
    const row = b.closest('tr,[role=row]');
    const text = (row ? row.textContent : '') || '';
    const mine = /COS\\s*522/.test(text);
    if (ticked(b) !== mine) b.click();
    out.push((mine ? 'keep ' : 'clear ') + text.replace(/\\s+/g, ' ').trim().slice(0, 40));
  }
  return out.join(' | ');
})()
"""


def select_only_this_course():
    """Stellic registers every ticked PLANNED row at once, not the one you came for.

    Measured 09-19: with COS 597C also planned, Register Now offered "Register 2
    Courses" - and COS 597C belongs to a different matter. Each row carries its own
    checkbox (data-testid=registration-row-checkbox); the ticked icon is the one whose
    path contains the tick stroke "zm-9 14-5". Leave only COS 522 ticked, then make the
    dialog's own count prove it before anything is confirmed.
    """
    log("row selection: " + str(js(SELECT_ONLY)))
    time.sleep(3)


def submit_registration():
    select_only_this_course()
    body = snapshot("before-submit")
    for course in HELD:
        for line in body.splitlines():
            if course.replace(" ", "") in line.replace(" ", "") \
                    and re.search(r"\bdrop\b|\bremove\b|\bswap\b", line, re.I):
                die("a control on this page would drop or swap " + course
                    + " - stopping before any submit: " + line.strip()[:160], 7)
    ref, hits = find_ref(body, r'button "Start Registration"')
    if not ref:
        die("could not find one Start Registration button on the scheduler ("
            + str(len(hits)) + " candidates)", 7)
    log("pre-submit: clicking " + hits[0].strip()[:160])
    wp("click", ref)
    time.sleep(7)
    shot("registration-dialog")
    body = snapshot("registration-dialog")
    if not re.search(r"COS\s*522|Computational Complexity", body, re.I):
        die("the registration step no longer mentions COS 522 - not submitting", 7)
    confirm, hits = find_ref(body, r'button "(Register|Confirm|Submit|Register Courses)[^"]*"')
    if not confirm:
        log("no separate confirm control; snapshot recorded in the log")
        die("could not identify a single confirm control (" + str(len(hits))
            + " candidates) - stopping before submitting", 7)
    # The dialog names its own scope. One course, and it has to be this one.
    if not re.search(r'heading "Register 1 Course"', body):
        heading = next((l.strip() for l in body.splitlines() if "Register " in l and "Course" in l), "?")
        die("the confirm dialog is not scoped to one course - not submitting: " + heading[:120], 7)
    log("confirming: " + hits[0].strip()[:160])
    wp("click", confirm)
    time.sleep(10)
    shot("post-submit")
    snapshot("post-submit")


def verify():
    state, body = registration_state()
    shot("verify")
    snapshot("verify")
    log("verification on Stellic: COS 522 is " + state)
    if re.search(r"seats?|full|closed|waitlist|error|could not|unable", body, re.I):
        for line in body.splitlines():
            if re.search(r"seats?|full|closed|waitlist|error|could not|unable", line, re.I):
                log("page says: " + line.strip()[:200])
    return state == "registered"


def main():
    log("=== COS 522 registration, card " + CARD + ", operation " + OPERATION[:12] + " ===")
    check_approval()
    if already_registered_by_mail():
        log("RESULT: already registered before this run; nothing submitted")
        return 0
    attach_lane_with_key()
    if cas_login():
        duo()
    if "stellic" not in url():
        die("login did not end on Stellic (at " + url() + ")", 5)
    log("logged in to Stellic")
    state, _ = registration_state()
    log("COS 522 currently reads: " + state)
    if state == "registered":
        log("RESULT: COS 522 was already registered")
        return 0
    if state == "absent":
        die("COS 522 is not in the Fall 2026 plan at all - not adding it blindly", 7)
    open_scheduler()
    pick_section()
    submit_registration()
    if verify():
        log("RESULT: COS 522 registered and verified on the Stellic schedule")
        return 0
    log("RESULT: submitted but NOT verified as registered - treat as unfinished")
    return 8


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        log("FAILED: " + type(exc).__name__ + ": " + str(exc))
        sys.exit(9)
