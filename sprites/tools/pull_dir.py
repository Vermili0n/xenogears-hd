"""Download one render folder from a pod (side jobs: fixes, tests) - only files not here yet, every PNG decoded,
broken ones deleted (come again next run). Same transport as prod_sync.pull.

  python pull_dir.py <pod: A|B> <remote folder under /workspace> <local folder>
  e.g. python pull_dir.py B res_fix3 pod/report/prod/res_fix3
"""
import argparse
import os
import subprocess

from PIL import Image

from prod_sync import PODS, ssh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pod', choices=['A', 'B'])
    ap.add_argument('remote')
    ap.add_argument('local')
    a = ap.parse_args()
    host, port = PODS[0 if a.pod == 'A' else 1]
    os.makedirs(a.local, exist_ok=True)
    have = set()
    for dp, _, fs in os.walk(a.local):
        have |= {os.path.relpath(os.path.join(dp, f), a.local).replace('\\', '/') for f in fs if f.endswith('.png')}
    r = subprocess.run(ssh(host, port) + [f"cd /workspace/{a.remote} 2>/dev/null && find . -name '*.png' -printf '%P\\n'"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    need = [f for f in r.stdout.split() if f not in have]
    if not need:
        print('nothing new')
        return
    remote = subprocess.Popen(ssh(host, port) + [f'cd /workspace/{a.remote} && tar -cf - -T -'], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE)
    local = subprocess.Popen(['tar', '-xf', '-', '--no-same-owner', '-C', os.path.abspath(a.local).replace('\\', '/')],
                             stdin=remote.stdout)
    remote.stdin.write(('\n'.join(need) + '\n').encode())
    remote.stdin.close()
    local.wait()
    remote.wait()
    bad = 0
    for f in need:
        p = os.path.join(a.local, f)
        try:
            with Image.open(p) as im:
                im.load()
        except Exception:  # noqa: BLE001
            bad += 1
            if os.path.exists(p):
                os.remove(p)
    print(f'pulled {len(need) - bad} into {a.local} ({bad} incomplete, run again)')


if __name__ == '__main__':
    main()
