"""Watch RetroArch for crashes (30.10: the game crashed twice in the core at the same place - out of VRAM).

  python crash_watch.py            runs until the NEXT crash or hang of retroarch.exe, then prints the report and exits
                                   (so a background run wakes whoever started it); normal session ends are only logged.
Every session end goes to pod/report/crash_watch.log: crash (module, offset, exception) from the Windows Application
log, the last errors of that session's RetroArch log and how many times the core hit "out of VRAM".
"""
import glob
import json
import os
import subprocess
import time

ROOT = r'<XENO_SPRITES>'
LOG = os.path.join(ROOT, 'pod', 'report', 'crash_watch.log')
RA_LOGS = r'<RETROARCH_DRIVE>\RetroArch\logs'
PS = ("Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=(Get-Date).AddSeconds(-%d)} "
      "-ErrorAction SilentlyContinue | Where-Object { $_.ProviderName -in 'Application Error','Application Hang' "
      "-and $_.Message -match 'retroarch' } | ForEach-Object { [pscustomobject]@{id=$_.RecordId; t=$_.TimeCreated."
      "ToString('dd.MM HH:mm:ss'); p=$_.ProviderName; m=(($_.Message -split \"`n\")[0..4] -join ' | ')} } | ConvertTo-Json")


def log(line):
    line = time.strftime('%d.%m %H:%M:%S ') + line
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def ra_pids():
    r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq retroarch.exe', '/FO', 'CSV', '/NH'],
                       capture_output=True, text=True, errors='replace')
    return {int(l.split('","')[1]) for l in r.stdout.splitlines() if l.startswith('"retroarch')}


def events(seconds):
    r = subprocess.run(['powershell', '-NoProfile', '-Command', PS % seconds], capture_output=True, text=True,
                       errors='replace')
    try:
        ev = json.loads(r.stdout) if r.stdout.strip() else []
    except ValueError:
        return []
    return ev if isinstance(ev, list) else [ev]


def session_log_summary():
    files = sorted(glob.glob(os.path.join(RA_LOGS, 'retroarch__*.log')), key=os.path.getmtime)
    if not files:
        return 'no RetroArch log'
    lines = open(files[-1], encoding='utf-8', errors='replace').read().splitlines()
    oom = [l for l in lines if 'out of VRAM' in l]
    errs = [l for l in lines if '[ERROR]' in l or 'libretro ERROR' in l]
    cap = oom[-1].split('cap now ')[-1] if oom else '-'
    return (f'log {os.path.basename(files[-1])}: out-of-VRAM {len(oom)} (cap {cap}), errors {len(errs)}'
            + (f'; last error: {errs[-1].strip()[:200]}' if errs else ''))


def main():
    seen = {e['id'] for e in events(3600)}
    pids = ra_pids()
    log(f'watch started; RetroArch running: {sorted(pids) or "no"}')
    while True:
        time.sleep(10)
        now = ra_pids()
        gone = pids - now
        pids = now
        new = [e for e in events(120) if e['id'] not in seen]
        for e in new:
            seen.add(e['id'])
        if new or gone:
            if not new:  # Windows writes the crash event a few seconds after the process is gone
                time.sleep(8)
                new = [e for e in events(120) if e['id'] not in seen]
                for e in new:
                    seen.add(e['id'])
            summary = session_log_summary()
            if new:
                for e in new:
                    log(f"CRASH {e['t']} {e['p']}: {e['m'].replace(chr(13), '')}")
                log('  ' + summary)
                return
            log('RetroArch closed normally; ' + summary)


if __name__ == '__main__':
    main()
