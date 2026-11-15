"""Put re-rendered fix-list frames in place and rebuild + install their groups.

  python fix_apply.py <folder with the fixed renders (…/v4)> [--no-install] [--map ai/prod/regroup_map.json --no-record]
For every rendered job in ai/prod/fix_map.json (or --map: whole-group re-renders, name -> [name]): the original render(s) in res_prod/v4 are kept in
pod/report/prod/res_prod_prefix/v4 (first time only), the fixed render is copied over all twin names, the DONE marker
of each affected group is removed and prod_post.py rebuilds those groups (+ installs while RetroArch is not running).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROD = os.path.join(ROOT, 'ai', 'prod')
RES = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod', 'v4')
KEEP = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod_prefix', 'v4')
WORK = os.path.join(ROOT, 'ai', 'prod_work')


def retroarch_running():
    r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq retroarch.exe'], capture_output=True, text=True)
    return 'retroarch.exe' in r.stdout.lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fixed')
    ap.add_argument('--no-install', action='store_true')
    ap.add_argument('--map', default=os.path.join(PROD, 'fix_map.json'))
    ap.add_argument('--no-record', action='store_true', help='do not add to fix_done.json (whole-group re-renders)')
    a = ap.parse_args()
    fmap = json.load(open(a.map))
    meta = json.load(open(os.path.join(PROD, 'meta.json')))
    os.makedirs(KEEP, exist_ok=True)
    groups, copied, missing = set(), 0, []
    for rep, names in fmap.items():
        src = os.path.join(a.fixed, rep + '.png')
        if not os.path.exists(src):
            missing.append(rep)
            continue
        for n in names:
            dst = os.path.join(RES, n + '.png')
            keep = os.path.join(KEEP, n + '.png')
            if os.path.exists(dst) and not os.path.exists(keep):
                shutil.copy2(dst, keep)
            shutil.copyfile(src, dst)
            copied += 1
            groups.add(meta[n[:-6] if n.endswith('__head') else n]['group'])
    print(f'copied {copied} fixed renders, {len(missing)} not rendered: {missing[:5]}')
    if not a.no_record:
        dp = os.path.join(PROD, 'fix_done.json')  # fix_jobs.py skips these next time
        done = set(json.load(open(dp))) if os.path.exists(dp) else set()
        done |= {n for rep, names in fmap.items() if rep not in missing for n in names}
        json.dump(sorted(done), open(dp, 'w'), indent=1)
    for g in sorted(groups):
        dp = os.path.join(WORK, g, 'DONE')
        if os.path.exists(dp):
            os.remove(dp)
    install = not a.no_install and not retroarch_running()
    cmd = [sys.executable, os.path.join(HERE, 'prod_post.py'), '--prod', PROD, '--res', os.path.dirname(RES),
           '--only', ','.join(sorted(groups)), '--workers', '8'] + (['--install'] if install else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.strip()[-1500:])
    if r.returncode:
        print('prod_post error:', r.stderr[-800:])
    if install:  # twin NPC sets share pack files: keep every set's redrawn texels
        m = subprocess.run([sys.executable, os.path.join(HERE, 'merge_shared.py')], capture_output=True, text=True)
        print((m.stdout.strip().splitlines() or ['merge_shared: no output'])[-1])
    print('installed' if install else 'NOT installed (RetroArch running or --no-install) - rerun later')


if __name__ == '__main__':
    main()
