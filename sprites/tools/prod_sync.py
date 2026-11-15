"""One sync cycle of the production render: pull new renders from both pods, verify them, post-process and install
every group whose renders are complete.

  python prod_sync.py [--no-install]
Pull: lists res_prod on each pod, tars over only the files not here yet (direct SSH; both pods are fast).
A pulled PNG that does not decode (caught mid-write) is deleted and comes again next cycle.
Duplicate jobs rendered once (prod_dedup.py) are copied to all their names (ai/prod/dup_jobs.json).
Groups: complete = every job of the group (full frames + heads, v4 and v2) is here. Done groups are skipped
(ai/prod_work/<g>/DONE). Install only while RetroArch is not running.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROD = os.path.join(ROOT, 'ai', 'prod')
RES = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod')
KEY = os.path.expanduser('~/.ssh/<SSH_KEY>')
PODS = [('<POD_HOST>', '<POD_PORT>'), ('<POD_HOST>', '<POD_PORT>')]


def ssh(host, port):
    return ['ssh', '-o', 'ConnectTimeout=25', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no', '-p', port, '-i', KEY,
            f'root@{host}']


def local_files():
    have = set()
    for sub in ('v4', 'v2'):
        d = os.path.join(RES, sub)
        if os.path.isdir(d):
            have |= {f'{sub}/{f}' for f in os.listdir(d) if f.endswith('.png')}
    return have


def pull():
    os.makedirs(RES, exist_ok=True)
    have = local_files()
    got = 0
    for host, port in PODS:
        r = subprocess.run(ssh(host, port) + ["cd /workspace/res_prod 2>/dev/null && find . -name '*.png' -printf '%P\\n'"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        need = [f for f in r.stdout.split() if f not in have]
        if not need:
            continue
        remote = subprocess.Popen(ssh(host, port) + ['cd /workspace/res_prod && tar -cf - -T -'], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE)
        local = subprocess.Popen(['tar', '-xf', '-', '--no-same-owner', '-C', RES.replace('\\', '/')], stdin=remote.stdout)
        remote.stdin.write(('\n'.join(need) + '\n').encode())
        remote.stdin.close()
        local.wait()
        remote.wait()
        bad = 0
        for f in need:
            p = os.path.join(RES, f)
            try:
                with Image.open(p) as im:
                    im.load()
                got += 1
            except Exception:  # noqa: BLE001  (written mid-transfer or still being written on the pod)
                bad += 1
                if os.path.exists(p):
                    os.remove(p)
        print(f'pulled {len(need) - bad} from {host} ({bad} incomplete, retried next cycle)', flush=True)
    return got


def fill_dups():
    """Duplicate jobs (same control, board and prompt) are rendered once on the pods (prod_dedup.py): copy that render
    to the other names of the group."""
    p = os.path.join(PROD, 'dup_jobs.json')
    if not os.path.exists(p):
        return 0
    n = 0
    for d in json.load(open(p)):
        sub = os.path.join(RES, d['tag'])
        have = [m for m in d['names'] if os.path.exists(os.path.join(sub, m + '.png'))]
        if not have:
            continue
        src = os.path.join(sub, have[0] + '.png')
        for m in d['names']:
            dst = os.path.join(sub, m + '.png')
            if not os.path.exists(dst):
                shutil.copyfile(src, dst)
                n += 1
    return n


def complete_groups():
    jobs = [(j, 'v4') for j in json.load(open(os.path.join(PROD, 'jobs_v4.json')))] + \
           [(j, 'v2') for j in json.load(open(os.path.join(PROD, 'jobs_v2.json')))]
    meta = json.load(open(os.path.join(PROD, 'meta.json')))
    need = defaultdict(set)
    for j, tag in jobs:
        base = j['name'][:-6] if j['name'].endswith('__head') else j['name']
        need[meta[base]['group']].add(f"{tag}/{j['name']}.png")
    have = local_files()
    work = os.path.join(ROOT, 'ai', 'prod_work')
    done = {g for g in need if os.path.exists(os.path.join(work, g, 'DONE'))}
    ready = sorted(g for g, s in need.items() if s <= have and g not in done)
    return ready, len(need), len(done)


def retroarch_running():
    r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq retroarch.exe'], capture_output=True, text=True)
    return 'retroarch.exe' in r.stdout.lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-install', action='store_true')
    a = ap.parse_args()
    pull()
    n = fill_dups()
    if n:
        print(f'copied {n} renders to duplicate jobs', flush=True)
    ready, total, done = complete_groups()
    print(f'groups: {done} done, {len(ready)} ready now, {total} total', flush=True)
    if not ready:
        return
    install = not a.no_install and not retroarch_running()
    cmd = [sys.executable, os.path.join(HERE, 'prod_post.py'), '--prod', PROD, '--res', RES, '--only', ','.join(ready),
           '--workers', '12'] + (['--install'] if install else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    fails = [ln for ln in lines if 'failed' in ln or 'no renders' in ln]
    print(f'post-processed {len(ready)} groups, problems {len(fails)}, installed: {install}', flush=True)
    for ln in fails[:10]:
        print('  ', ln, flush=True)
    if r.returncode:
        print('prod_post error:', r.stderr[-500:], flush=True)
    if install:  # twin NPC sets share pack files: keep every set's redrawn texels (merge_shared.py)
        m = subprocess.run([sys.executable, os.path.join(HERE, 'merge_shared.py')], capture_output=True, text=True)
        print((m.stdout.strip().splitlines() or ['merge_shared: no output'])[-1], flush=True)


if __name__ == '__main__':
    main()
