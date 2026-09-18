#!/usr/bin/env python3
"""Deliver a message into a Claude Code background agent via the daemon control
socket — the same daemon that backs `claude agents` / `--bg` / `attach`.

This is the no-messenger delivery path: no second `claude -p` session, no
guessed messaging-socket frame. It speaks the daemon's own JSON-lines control
protocol directly. Verified on CLI 2.1.246.

Wire protocol (reverse-engineered — UNDOCUMENTED, may break on CLI upgrade):
  - transport : AF_UNIX stream at /tmp/cc-daemon-<uid>/<hex>/control.sock,
                one JSON request per connection, '\n'-terminated, one JSON reply.
  - every request carries {"proto": 1}.
  - {"op":"ping"}                                  -> {"ok":true,...}   (no auth)
  - {"op":"list"}                                  -> {"ok":true,"jobs":[...]}
  - {"op":"reply","short":<id>,"text":<str>,
     "auth":<control-key bytes as latin-1>}        -> {"ok":true,"op":"reply"}
        delivers <text> as a user turn to job <short>; the agent acts on it.
        ok:true is a DAEMON-ACCEPTED ack (queued to the session), not a
        consumption receipt. A busy session queues it in order; an idle one
        starts a turn with it.
  - auth is the raw bytes of ~/.claude/daemon/control.key, decoded latin-1
    (hex form is rejected). ping/list need no auth; reply does.

Security: the socket is uid-restricted by the OS, so no network exposure. The
control key gates the write ops within the user's own session.
"""
from datetime import datetime
import glob
import json
import os
import socket
import subprocess
import time

DAEMON_KEY = os.path.expanduser("~/.claude/daemon/control.key")


class DaemonError(RuntimeError):
    pass


def _control_key() -> str:
    with open(DAEMON_KEY, "rb") as fh:
        return fh.read().decode("latin-1")


def _sock_candidates():
    uid = os.getuid()
    return glob.glob(f"/tmp/cc-daemon-{uid}/*/control.sock")


def _call(sock_path: str, obj: dict, timeout: float = 30.0) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(sock_path)
        s.sendall((json.dumps({**obj, "proto": 1}) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8", "replace").strip() or "{}")
    finally:
        s.close()


def live_control_sock() -> str:
    """The one control.sock whose daemon answers ping with ok:true. Raises if none."""
    failures = []
    for cand in _sock_candidates():
        try:
            # A live daemon took 9s to respond during host swapping. A 2s probe
            # misclassified it as absent; wait without resending a delivery.
            r = _call(cand, {"op": "ping"}, timeout=15.0)
            if r.get("ok") and r.get("op") == "ping":
                return cand
            failures.append(f"{cand}: unexpected ping response")
        except (OSError, ValueError) as exc:
            failures.append(f"{cand}: {type(exc).__name__}: {exc}")
    detail = "; ".join(failures) if failures else "no socket paths found"
    raise DaemonError(f"Claude Code daemon discovery failed: {detail}")


def list_jobs(sock: str | None = None) -> list[dict]:
    sock = sock or live_control_sock()
    r = _call(sock, {"op": "list"})
    if not r.get("ok"):
        raise DaemonError(f"list failed: {r}")
    return r.get("jobs", [])


def find_job(name: str, sock: str | None = None) -> dict | None:
    """Newest job answering to exactly `name`, or None. Prefers a live one."""
    jobs = [j for j in list_jobs(sock) if j.get("name") == name]
    if not jobs:
        return None
    live = [j for j in jobs if j.get("state") in ("working", "running", "adopted", "idle", "blocked")]
    pool = live or jobs
    return max(pool, key=lambda j: j.get("createdAt", 0))


def reply(short: str, text: str, sock: str | None = None) -> dict:
    sock = sock or live_control_sock()
    r = _call(sock, {"op": "reply", "short": short, "text": text, "auth": _control_key()})
    if not r.get("ok"):
        raise DaemonError(f"reply rejected for {short}: {r.get('error', r)}")
    return r


def interrupt(job, timeout=20):
    """Cancel the current response through the supported attach terminal; retain the worker."""
    import fcntl
    import pathlib
    import pty
    import re
    import select
    import struct
    import termios
    short = job['short']
    roster = json.loads((pathlib.Path.home() / '.claude/daemon/roster.json').read_text())
    worker = roster.get('workers', {}).get(short) or {}
    sid = worker.get('sessionId') or worker.get('dispatch', {}).get('sessionId')
    cwd = worker.get('cwd') or job.get('cwd')
    if not sid or not cwd:
        raise DaemonError('Cannot locate the response transcript to confirm interruption')
    transcript = pathlib.Path.home() / '.claude/projects' / re.sub(r'[^a-zA-Z0-9]', '-', cwd) / (sid + '.jsonl')

    def ended():
        if not transcript.exists():
            return False
        with transcript.open('rb') as fh:
            fh.seek(max(0, transcript.stat().st_size - 262144))
            lines = fh.read().splitlines()
        meaningful = []
        for line in lines:
            try:
                record = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if record.get('type') in ('user', 'assistant') or record.get('subtype') == 'turn_duration':
                meaningful.append(record)
        if not meaningful:
            return False
        last = meaningful[-1]
        return last.get('subtype') == 'turn_duration' or (
            last.get('type') == 'user' and any(
                isinstance(part, dict) and part.get('text', '').startswith('[Request interrupted by user')
                for part in last.get('message', {}).get('content', [])
            ))

    if ended():
        return 'already idle'
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 160, 0, 0))
    proc = subprocess.Popen(['claude', 'attach', short], stdin=slave, stdout=slave, stderr=slave,
                            env=dict(os.environ, TERM='xterm-256color'), start_new_session=True)
    os.close(slave)
    try:
        deadline = time.monotonic() + timeout
        output = b''
        while time.monotonic() < deadline and len(output) < 100:
            if proc.poll() is not None:
                raise DaemonError('Attach exited before it was ready')
            if select.select([master], [], [], .1)[0]:
                output += os.read(master, 65536)
        if len(output) < 100:
            raise DaemonError('Attach did not render the session')
        # Rendering precedes terminal input readiness on the current CLI.
        time.sleep(1)
        if ended():
            return 'finished before cancel'
        os.write(master, b'\x03')
        while time.monotonic() < deadline:
            if select.select([master], [], [], .1)[0]:
                os.read(master, 65536)
            if ended():
                return 'response stopped'
        raise DaemonError('No interruption receipt; replacement was not delivered')
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        os.close(master)


def spawn(name: str, cwd: str, allowed_tools: str = "Bash,Read,Write,Task,WebSearch,WebFetch,ToolSearch,Skill") -> str:
    """Start an idle background agent named `name` under `cwd`. Returns its short id."""
    # No --model here on purpose: the model is a PROJECT setting, agent/.claude/settings.json, which
    # every claude started from `cwd` reads and which outranks the machine's user settings. It used
    # to be inherited from that user file — a metered model on mac-mini — and when its credits ran
    # out every worker came up blocked and swallowed twelve hours of deliveries.
    out = subprocess.run(
        ["claude", "--bg", "-n", name, "--allowedTools", allowed_tools],
        cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60,
    )
    # First line: "backgrounded · <short> · <name> ...". Parse the short id.
    line = (out.stdout or "").splitlines()[0] if out.stdout else ""
    import re
    m = re.search(r"backgrounded\D+([0-9a-f]{8})", _strip_ansi(line))
    if not m:
        raise DaemonError(f"could not parse short id from spawn output: {line!r}\n{out.stderr}")
    return m.group(1)


def _strip_ansi(s: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def _reply_with_retry(short, text, sock, tries=8, gap=4.0):
    """reply, retrying while the freshly-spawned worker is not yet accepting
    (a cold bg worker briefly reports "isn't accepting replies" before it idles)."""
    last = None
    for _ in range(tries):
        try:
            return reply(short, text, sock)
        except DaemonError as e:
            last = e
            if "isn't accepting replies" in str(e) or "non-interactive" in str(e):
                time.sleep(gap)
                sock = live_control_sock()
                continue
            raise
    raise last


def shell_input(job, command, log_path, started_path, timeout=45):
    """Type ! into the actual attach terminal; never send it as a daemon user message."""
    import fcntl
    import pty
    import select
    import struct
    import termios
    from pathlib import Path
    if any(ord(c) < 32 or ord(c) == 127 for c in command):
        raise ValueError('Shell input must be one line without terminal control characters')
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 160, 0, 0))
    process = subprocess.Popen(['claude', 'attach', job['short']], stdin=slave,
                               stdout=slave, stderr=slave, start_new_session=True,
                               env=dict(os.environ, TERM='xterm-256color'))
    os.close(slave)
    try:
        with Path(log_path).open('xb') as log:
            rendered = bytearray()

            def drain(seconds):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise DaemonError('Claude attach exited before execution acknowledgement')
                    if select.select([master], [], [], min(.2, max(0, deadline - time.monotonic())))[0]:
                        chunk = os.read(master, 65536)
                        log.write(chunk)
                        log.flush()
                        rendered.extend(chunk)

            deadline = time.monotonic() + timeout
            while '❯'.encode() not in rendered:
                drain(.5)
                if time.monotonic() >= deadline:
                    raise DaemonError('Claude attach did not show an input prompt; script was not typed')
            # Attach can render before installing its input handler (also true for interrupt()).
            drain(1)
            os.write(master, b'!')
            rendered.clear()
            drain(1)
            if b'! for shell mode' not in rendered:
                raise DaemonError('Claude did not enter shell mode; command was not typed')
            os.write(master, command.encode())
            drain(.5)
            os.write(master, b'\r')
            deadline = time.monotonic() + timeout
            while not Path(started_path).exists():
                drain(.5)
                if time.monotonic() >= deadline:
                    raise DaemonError('Shell start not acknowledged; it may be queued. Check receipt before retrying.')
            drain(1)
    finally:
        # Detach this client only; the daemon owns the shell and original conversation.
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        os.close(master)


def session_of(name: str) -> str:
    """The session the daemon currently holds for `name`, or empty."""
    j = find_job(name)
    return (j or {}).get("sessionId", "") or ""


def retire(name: str) -> bool:
    """Drop the daemon's worker for `name` so the next delivery spawns a fresh one.

    The transcript file is left alone — it is the audit trail; what is being retired is the
    live context, not the record."""
    j = find_job(name)
    if not j:
        return False
    if j.get("state") == "working":
        return False        # mid-turn; rotating now would throw away work already done
    from card_hooks import retirement_ready, emit
    sid = j.get('sessionId', '')
    if not retirement_ready(sid):
        emit(sid, 'retirement_deferred', reason='no_completed_stop_without_background_tasks')
        return False
    short = j["short"]
    subprocess.run(["claude", "stop", short], capture_output=True, check=True)
    subprocess.run(["claude", "rm", short], capture_output=True, check=True)
    return True


def unfinished_background(session_id: str) -> bool:
    """Does the card hook's last snapshot of this session show a background task still running?"""
    try:
        from card_hooks import session_path
        path = session_path(session_id)
        if not path.exists():
            return False
        tasks = json.loads(path.read_text()).get("background_tasks") or []
        return any(t.get("status") not in ("completed", "failed", "killed") for t in tasks)
    except Exception:
        return False


def ensure_and_deliver(name: str, cwd: str, text: str, ready_timeout: float = 60.0) -> dict:
    """The one call inboard needs: make sure agent `name` exists & is reachable,
    then deliver `text` to it. Handles all four lifecycle states, and waits out a
    cold worker's brief not-yet-accepting window."""
    sock = live_control_sock()
    job = find_job(name, sock)
    if job is None:
        spawn(name, cwd)
        # poll until the new job registers with the daemon
        deadline = time.time() + ready_timeout
        while time.time() < deadline:
            time.sleep(3)
            sock = live_control_sock()
            job = find_job(name, sock)
            if job:
                break
        if job is None:
            raise DaemonError(f"spawned {name} but it never registered with the daemon")
        short = job["short"]
    else:
        short = job["short"]
        if job.get("state") == "stopped":
            # Not `claude respawn`: whether that re-applies the original --model could not be
            # confirmed, and the model is the one thing inboard must decide for itself on every
            # worker it runs. A stopped worker is dropped and a fresh one spawned through spawn(),
            # the single place the model is set.
            job, short = _respawn(name, cwd, short, ready_timeout, gone=("stopped",), stop=False)
        elif job.get("state") == "adopted" and not unfinished_background(job.get("sessionId", "")):
            # Every session reads as adopted after the daemon restarts. One with a background
            # task still running wakes when that task completes and consumes what was queued;
            # one with nothing running accepts a delivery and never reads it — a card sat
            # 执行中 for an hour behind one. Replace it as a stopped worker; the card holds
            # the state, so the replacement loses only the live session's working memory.
            job, short = _respawn(name, cwd, short, ready_timeout, gone=("adopted", "stopped"), stop=True)
        elif job.get("state") == "blocked":
            # "blocked" is the daemon's reading of the worker's last message, and it covers two
            # unrelated things: the worker asked the operator for something — the normal end of a
            # card turn, 「审一眼点帮我发送」 — and the API refused the worker (login, usage limit,
            # overload). A comment or a button press is exactly what clears the first kind, and it
            # is the one delivery the worker must receive with its memory intact: replacing it
            # here put five fresh sessions on one card in an hour, each answering the operator
            # as if it had never seen the exchange he was replying to. So a blocked worker is
            # delivered to first, and replaced only when it does not take the delivery up — the
            # API-refused kind accepts a reply and never runs it, which is how one came to eat
            # three comments in a row during an auth outage.
            r = _deliver(name, job, short, text, sock)
            if _taken_up(name, job.get("sessionId", ""), r["delivered_at"]):
                r["delivery"] = "blocked-worker-resumed"
                return r
            job, short = _respawn(name, cwd, short, ready_timeout, gone=("blocked",), stop=True)
            if job.get("state") == "blocked":
                raise DaemonError(
                    f"{name} came back blocked ({job.get('needs') or 'unknown'}) — "
                    "the daemon itself is unauthenticated; check its env carries a token")
            r = _deliver(name, job, short, text, sock)
            r["delivery"] = "blocked-worker-replaced"
            return r
    return _deliver(name, job, short, text, sock)


def _respawn(name, cwd, short, ready_timeout, *, gone, stop):
    """Drop worker `short` and spawn a fresh one for `name`; return (job, short) once the new
    one registers in a state outside `gone`."""
    if stop:
        subprocess.run(["claude", "stop", short], capture_output=True)
    subprocess.run(["claude", "rm", short], capture_output=True)
    spawn(name, cwd)
    deadline = time.time() + ready_timeout
    job = None
    while time.time() < deadline:
        time.sleep(3)
        job = find_job(name, live_control_sock())
        if job and job.get("state") not in gone:
            break
    if job is None:
        raise DaemonError(f"replaced {gone[0]} {name} but it never registered")
    return job, job["short"]


def _deliver(name, job, short, text, sock):
    # Bind before delivery: a short turn can reach Stop before the caller writes Session.
    from card_hooks import bind_session
    bind_session(name, (job or {}).get("sessionId", ""), pending=True)
    if name.startswith('inboard-card-'):
        text = ('Read the current CLAUDE.md in your working directory before handling this card. '
                'Read the current files for applicable project skills too; instructions remembered '
                'from an earlier turn may have changed.\n\n') + text
    delivered_at = time.time()
    r = _reply_with_retry(short, text, sock)
    # Hand the caller the session this actually landed in. The card records a session id, and
    # under daemon delivery nothing was writing it back — so a card kept naming the session that
    # last ran it in the shell, which on one bank card meant a July transcript, dead for five
    # weeks, while every September run happened somewhere the card never mentioned.
    r = dict(r) if isinstance(r, dict) else {"ok": True, "raw": r}
    r.setdefault("short", short)
    r.setdefault("sessionId", (job or {}).get("sessionId", ""))
    r["delivered_at"] = delivered_at
    return r


def _taken_up(name, session_id, since, timeout=30.0):
    """Did session `session_id` start a turn on a delivery made at `since`? The card hook stamps
    the session's state file on every UserPromptSubmit; a worker that queues a reply without
    running it never stamps. Only card agents have that file, so anything else reads as not
    taken up and is replaced as before."""
    if not name.startswith('inboard-card-') or not session_id:
        return False
    from card_hooks import session_path
    path = session_path(session_id)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            at = json.loads(path.read_text()).get("last_prompt_at")
            if at and datetime.fromisoformat(at).timestamp() >= since:
                return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Deliver a message to a bg agent via the daemon.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    sub.add_parser("list")
    se = sub.add_parser("session"); se.add_argument("--name", required=True)
    rt = sub.add_parser("retire"); rt.add_argument("--name", required=True)
    d = sub.add_parser("deliver"); d.add_argument("--name", required=True); d.add_argument("--cwd", default=os.getcwd()); d.add_argument("--text", required=True)
    args = ap.parse_args()
    if args.cmd == "ping":
        print(json.dumps(_call(live_control_sock(), {"op": "ping"})))
    elif args.cmd == "list":
        for j in list_jobs():
            print(f"{j['short']}  {j.get('state','?'):9s}  {j.get('name','')}")
    elif args.cmd == "session":
        print(session_of(args.name))
    elif args.cmd == "retire":
        print("retired" if retire(args.name) else "no-such-agent")
    elif args.cmd == "deliver":
        print(json.dumps(ensure_and_deliver(args.name, args.cwd, args.text)))
