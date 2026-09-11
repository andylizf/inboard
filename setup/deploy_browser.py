#!/usr/bin/env python3
"""Install the authenticator service for the main profile; preserve any previous plist."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'logs' / f'browser-deploy-{stamp}'
    output.mkdir(parents=True, mode=0o700)
    label = 'local.inboard-webauthn'
    target = Path.home() / 'Library/LaunchAgents' / f'{label}.plist'
    with (output / 'events.jsonl').open('a') as log:
        def record(event, **fields):
            log.write(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(),
                                      event=event, **fields)) + '\n')
            log.flush()
        record('start', root=str(ROOT), label=label)
        if target.exists():
            shutil.copy2(target, output / target.name)
            record('backup', path=str(output / target.name))
        contents = (ROOT / 'setup' / f'{label}.plist.template').read_text()
        contents = contents.replace('__INBOARD_HOME__', str(ROOT))
        plistlib.loads(contents.encode())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents)
        service = f'gui/{os.getuid()}/{label}'
        subprocess.run(['launchctl', 'bootout', service], capture_output=True)
        subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(target)], check=True)
        state = subprocess.check_output(['launchctl', 'print', service], text=True)
        (output / 'service.txt').write_text(state)
        record('installed', service=service)
    print(output)


if __name__ == '__main__':
    main()
