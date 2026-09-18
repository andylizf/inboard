#!/usr/bin/env python3
"""Does Chrome's own profile already hold the Entra password? Read-only probe.

The credential broker restarted and its vault session is gone. But the shared web-plane
profile is a real Chrome with a real password manager, and prior work on this machine
recorded that it pre-fills the CAS form. If it pre-fills Entra's too, the login needs no
vault at all.

Reports only the LENGTH of whatever sits in the password field. The value itself is never
read out, printed or stored. Submits nothing.
"""
import asyncio, json, re, subprocess, sys, time, urllib.request

TARGET = "https://oit.princeton.edu/duo"


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
        try:
            await cmd("Page.enable", sid=sid); await cmd("Runtime.enable", sid=sid)
            await asyncio.sleep(2)
            await cmd("Page.bringToFront", sid=sid)

            async def ev(expr, timeout=30):
                r = await cmd("Runtime.evaluate",
                              {"expression": expr, "awaitPromise": True, "returnByValue": True},
                              sid=sid, timeout=timeout)
                return (r.get("result") or {}).get("value")

            await cmd("Page.navigate", {"url": TARGET}, sid=sid)
            await asyncio.sleep(10)
            u = await ev("location.href")
            log(f"at {u[:90]}")

            # Walk the Entra flow only as far as the password screen, using the username
            # (not a secret) so Chrome is offered the origin it has a credential for.
            for _ in range(8):
                u = await ev("location.href")
                if "login.microsoftonline.com" not in u:
                    log(f"no Entra form here: {u[:90]}")
                    break
                vis = ("(s)=>{const e=document.querySelector(s);"
                       "return !!(e && e.offsetParent !== null && !e.disabled);}")
                if await ev(f"({vis})('#i0118')"):
                    ln = await ev("document.querySelector('#i0118').value.length")
                    log(f"PASSWORD FIELD PRESENT, prefilled length = {ln}")
                    log("VERDICT: " + ("chrome prefilled it — the vault is not needed"
                                       if ln and ln > 0 else
                                       "empty — chrome has no usable saved password here"))
                    break
                if await ev(f"({vis})('#i0116')"):
                    await ev("document.querySelector('#i0116').value=''")
                    await ev("document.querySelector('#i0116').focus()")
                    await cmd("Input.insertText", {"text": "al9080@princeton.edu"}, sid=sid)
                    await ev("document.querySelector('#idSIButton9')?.click()")
                    await asyncio.sleep(5)
                    continue
                await asyncio.sleep(3)
            # Also ask Chrome's own store, the authoritative answer.
            return 0
        finally:
            try:
                await cmd("Target.closeTarget", {"targetId": tid})
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
