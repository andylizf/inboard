#!/usr/bin/env python3
"""Read Princeton's Duo device list for al9080, for inbox card 3d02a1a7.

Default run is READ ONLY. With DUO_PUSH=1 it sends exactly ONE Duo Push and waits up to
five minutes; take the twofa gate before that and never send a second one.

Same trick as bin/princeton-login: drive ONE tab of the shared web-plane profile over raw
CDP with no agent-browser lane attached, so Duo's security-key request is answered by the
enrolled virtual key instead of falling through to the macOS passkey sheet. The difference
from princeton-login is the identity provider: oit.princeton.edu/duo goes to Microsoft
Entra, not CAS, so the form is Entra's -- and measured on 2026-09-18, that Duo integration
does NOT accept the key (35s of waiting still reports "This option didn't work"), which is
why the push mode exists at all. Behind CAS the key still works and no push is needed.

Two Entra traps, both paid for once already: #i0116 and #i0118 both stay in the DOM after
the page advances, so "does it exist" loops forever typing into a hidden box -- test
offsetParent; and the password screen is the LATER one, so check for it first.

Password comes from $CRED (run under `cred with <Entra item> --`).
"""
import asyncio, base64, json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

USER = "al9080@princeton.edu"
TARGET = "https://oit.princeton.edu/duo"
PUSH = os.environ.get("DUO_PUSH") == "1"
OUT = Path(os.environ.get("DUO_OUT", "/Users/andyl/Projects/inboard/logs"))
OUT.mkdir(parents=True, exist_ok=True)
TS = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def main_port():
    r = subprocess.run(["web-plane", "-s=main", "cdp"], capture_output=True, text=True)
    m = re.search(r"CDP port:\s+(\d+)", r.stdout + r.stderr)
    if not m:
        sys.exit("cannot find the profile's CDP port")
    return int(m.group(1))


async def run():
    import websockets
    pw = os.environ.get("CRED")
    if not pw:
        sys.exit("no CRED in env")
    port = main_port()
    browser = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version"))["webSocketDebuggerUrl"]
    async with websockets.connect(browser, max_size=None) as ws:
        n = 0; pending = {}

        async def reader():
            async for raw in ws:
                m = json.loads(raw)
                if "id" in m and m["id"] in pending:
                    pending.pop(m["id"]).set_result(m)
        asyncio.create_task(reader())

        async def cmd(method, params=None, sid=None, timeout=30):
            nonlocal n; n += 1
            fut = asyncio.get_event_loop().create_future(); pending[n] = fut
            msg = {"id": n, "method": method, "params": params or {}}
            if sid:
                msg["sessionId"] = sid
            await ws.send(json.dumps(msg))
            r = await asyncio.wait_for(fut, timeout)
            if "error" in r:
                raise RuntimeError(f"{method}: {r['error']}")
            return r["result"]

        tid = (await cmd("Target.createTarget", {"url": "about:blank"}))["targetId"]
        sid = (await cmd("Target.attachToTarget", {"targetId": tid, "flatten": True}))["sessionId"]
        outcome = "unused"
        try:
            await cmd("Page.enable", sid=sid); await cmd("Runtime.enable", sid=sid)
            await asyncio.sleep(3)
            await cmd("Page.bringToFront", sid=sid)

            async def ev(expr, timeout=30):
                r = await cmd("Runtime.evaluate",
                              {"expression": expr, "awaitPromise": True, "returnByValue": True},
                              sid=sid, timeout=timeout)
                return (r.get("result") or {}).get("value")

            async def url():
                return await ev("location.href")

            async def text():
                return await ev("document.body ? document.body.innerText : ''") or ""

            async def shot(name):
                try:
                    await cmd("Page.bringToFront", sid=sid)
                    await asyncio.sleep(0.5)
                    data = (await cmd("Page.captureScreenshot", {"format": "png"}, sid=sid))["data"]
                    p = OUT / f"duo-{name}.png"
                    p.write_bytes(base64.b64decode(data))
                    log(f"screenshot {p}")
                except Exception as e:
                    log(f"(screenshot {name} failed: {e})")

            async def settle(seconds, until=None):
                end = time.time() + seconds
                while time.time() < end:
                    await asyncio.sleep(1.5)
                    u = await url()
                    if until and until(u):
                        return u
                return await url()

            log(f"tab -> {TARGET}")
            await cmd("Page.navigate", {"url": TARGET}, sid=sid)
            await settle(12)
            u = await url()
            log(f"at {u}")

            # ---- Entra, if it asks ----
            for _ in range(22):
                u = await url()
                body = await text()
                if "login.microsoftonline.com" not in u and "duosecurity.com" not in u:
                    break
                if "duosecurity.com" in u:
                    if "Is this your device" in body:
                        outcome = "ok"
                        log("Duo cleared by the key; confirming device")
                        await ev("[...document.querySelectorAll('button')]"
                                 ".find(b=>/Yes, this is my device/i.test(b.innerText))?.click()")
                        await asyncio.sleep(4)
                        continue
                    # Give the enrolled key its chance before concluding anything.
                    # princeton-login allows ~25s; anything shorter reads a prompt that
                    # is still working as a prompt that failed.
                    waited = 0
                    while waited < 35:
                        await asyncio.sleep(5); waited += 5
                        u2 = await url(); b2 = await text()
                        if "duosecurity.com" not in u2:
                            log(f"Duo cleared by the key after {waited}s")
                            break
                        if "Is this your device" in b2:
                            log(f"key answered Duo after {waited}s; confirming device")
                            outcome = "ok"
                            await ev("[...document.querySelectorAll('button')]"
                                     ".find(b=>/Yes, this is my device/i.test(b.innerText))?.click()")
                            await asyncio.sleep(5)
                            break
                    if "duosecurity.com" not in (await url()):
                        continue
                    if not PUSH:
                        log("Duo prompt: the key did not clear it; reading the device list (no push)")
                    else:
                        log("Duo prompt: the key did not clear it; sending ONE Duo Push")
                        r = await ev("(()=>{const rows=[...document.querySelectorAll('button,a,div[role=button]')];"
                                     "const hit=rows.find(e=>/Duo Push/i.test(e.textContent||''));"
                                     "if(hit){hit.click();return 'pushed';}return 'no-push-row';})()")
                        log(f"push row click -> {r}")
                        outcome = "timeout"          # honest default until he answers
                        await asyncio.sleep(4)
                        body2 = await text()
                        code = None
                        import re as _re
                        m = _re.search(r"\b(\d{1,3})\b(?=[\s\S]{0,80}(Verify|verification|check))", body2)
                        for line in body2.splitlines():
                            if line.strip().isdigit() and 1 <= len(line.strip()) <= 3:
                                code = line.strip(); break
                        log(f"Duo screen after push: {body2[:300]!r}")
                        if code:
                            log(f"*** MATCHING CODE SHOWN ON SCREEN: {code} ***")
                        (OUT / "duo-push-screen.txt").write_text(body2)
                        await shot("push-sent")
                        log("waiting up to 5 minutes for him to approve on his phone")
                        pushed_deadline = time.time() + 300
                        while time.time() < pushed_deadline:
                            await asyncio.sleep(6)
                            u3 = await url(); b3 = await text()
                            if "duosecurity.com" not in u3:
                                outcome = "ok"; log("push approved; Duo cleared"); break
                            if "Is this your device" in b3 or "Trust this browser" in b3:
                                outcome = "ok"
                                log("push approved; answering the trust prompt")
                                await ev("[...document.querySelectorAll('button')]"
                                         ".find(b=>/Yes, this is my device|Yes, trust browser/i.test(b.innerText))?.click()")
                                await asyncio.sleep(6); break
                        if outcome != "ok":
                            log("STOP: the push was not approved within 5 minutes")
                            await shot("push-unanswered")
                            return 7
                        continue
                    await ev("(()=>{const a=[...document.querySelectorAll('a,button')]"
                             ".find(e=>/other options/i.test(e.textContent||''));"
                             "if(a){a.click();return 'opened';}return 'no-link';})()")
                    await asyncio.sleep(3)
                    opts = await text()
                    (OUT / "duo-options.txt").write_text(f"URL: {u}\n\n{opts}")
                    log("---- Duo options list ----")
                    for line in opts.splitlines():
                        if line.strip():
                            log("  | " + line.strip())
                    log("---- end ----")
                    await shot("options")
                    return 0
                # Entra. Both fields stay in the DOM after the page advances, so
                # "is it there" is not the question - "is it on screen" is. Password
                # first, because that is the later of the two screens.
                vis = "(s)=>{const e=document.querySelector(s);return !!(e && e.offsetParent !== null && !e.disabled);}"
                async def visible(sel):
                    return await ev(f"({vis})({json.dumps(sel)})")

                if await visible('#i0118'):
                    await ev("document.querySelector('#i0118').focus()")
                    await ev("document.querySelector('#i0118').value=''")
                    await cmd("Input.insertText", {"text": pw}, sid=sid)
                    got = await ev("document.querySelector('#i0118').value.length")
                    if got != len(pw):
                        await shot("entra-fill")
                        log(f"STOP: password field holds {got} chars, expected {len(pw)}")
                        return 3
                    log("entra: password entered; submitting")
                    await ev("document.querySelector('#idSIButton9')?.click()")
                    await asyncio.sleep(6)
                    continue
                if await visible('#i0116'):
                    await ev("document.querySelector('#i0116').focus()")
                    await ev("document.querySelector('#i0116').value=''")
                    await cmd("Input.insertText", {"text": USER}, sid=sid)
                    log("entra: username entered; submitting")
                    await ev("document.querySelector('#idSIButton9')?.click()")
                    await asyncio.sleep(5)
                    continue
                if "Stay signed in" in body:
                    log("entra: declining 'stay signed in'")
                    await ev("document.querySelector('#idBtn_Back')?.click()")
                    await asyncio.sleep(4)
                    continue
                if re.search(r"pick an account|Use another account|Sign in", body, re.I) and \
                   await ev("!!document.querySelector('[data-test-id], .table')"):
                    clicked = await ev(
                        "(()=>{const t=[...document.querySelectorAll('div,button')]"
                        ".find(e=>/al9080@princeton\\.edu/i.test(e.textContent||''));"
                        "if(t){t.click();return 'tile';}return 'none';})()")
                    log(f"entra: account tile -> {clicked}")
                    await asyncio.sleep(4)
                    continue
                await asyncio.sleep(3)

            u = await url()
            body = await text()
            log(f"settled at {u}")
            (OUT / "duo-landing.txt").write_text(f"URL: {u}\n\n{body}")
            await shot("landing")
            log("---- landing page text ----")
            for line in body.splitlines():
                if line.strip():
                    log("  | " + line.strip())
            log("---- end ----")
            log(f"page text written to {OUT/'duo-landing.txt'} ({len(body)} chars)")
            return 0
        finally:
            subprocess.run(["twofa-gate", "release", "princeton", outcome], capture_output=True)
            try:
                await cmd("Target.closeTarget", {"targetId": tid})
            except Exception:
                pass


def main():
    gate = subprocess.run(["twofa-gate", "acquire", "princeton"], capture_output=True, text=True)
    if gate.returncode != 0:
        sys.exit("gate: " + gate.stdout.strip() + gate.stderr.strip())
    log("gate: " + gate.stdout.strip().splitlines()[0])
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
