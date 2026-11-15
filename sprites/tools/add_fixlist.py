"""Add confident QA findings (pod/report/qa/auto/findings.txt: "<group> <set> <f1,f2,..> back|eyepatch") to ai/prod/fixlist.json,
expanded to every job name whose control image is byte-identical (twins/dups: fix_jobs collapses only what is listed).
Moderate / 3/4 lines are skipped. Existing entries are kept. Backup: fixlist.json.bak_<stamp>.

  python add_fixlist.py <group> [--dry]
"""
import argparse
import hashlib
import json
import os
import shutil
import time
from collections import defaultdict

ROOT = r'<XENO_SPRITES>'
PROD = os.path.join(ROOT, 'ai', 'prod')
FIND = os.path.join(ROOT, 'pod', 'report', 'qa', 'auto', 'findings.txt')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('group')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    jobs = {j['name']: j for j in json.load(open(os.path.join(PROD, 'jobs_v4.json')))}
    md5 = {}

    def h(name):
        if name not in md5:
            md5[name] = hashlib.md5(open(os.path.join(PROD, jobs[name]['control']), 'rb').read()).hexdigest()
        return md5[name]

    want = {}
    for ln in open(FIND, encoding='utf-8'):
        p = ln.split()
        if len(p) < 4 or p[0] != a.group or p[3] not in ('back', 'eyepatch', 'eyepatch_left', 'glasses', 'front', 'flip', 'boots', 'white_coat', 'visor', 'creature', 'short_hair', 'dog', 'mask'):
            continue
        for f in p[2].split(','):
            name = f'{p[0]}__{p[1]}_{int(f):03d}'
            if name not in jobs:
                print('no job', name)
                continue
            want[name] = p[3]
    # every non-head job with the same control bytes gets the same kind
    by_md5 = defaultdict(list)
    sizes = defaultdict(list)
    for n, j in jobs.items():
        if not n.endswith('__head'):
            sizes[os.path.getsize(os.path.join(PROD, j['control']))].append(n)
    for name in want:
        for n in sizes[os.path.getsize(os.path.join(PROD, jobs[name]['control']))]:
            if h(n) == h(name) and jobs[n]['ref'] == jobs[name]['ref']:   # same frame AND same board
                by_md5[name].append(n)
    fix = json.load(open(os.path.join(PROD, 'fixlist.json')))
    added = {}
    for name, kind in want.items():
        for n in by_md5[name]:
            if n not in fix and n not in added:
                added[n] = kind
    twins = len(added) - sum(1 for n in added if n.startswith(a.group + '__'))
    print(f'{a.group}: {len(want)} frames -> {len(added)} new fixlist names ({twins} twins in other groups); '
          f"back {sum(v == 'back' for v in added.values())}, eyepatch {sum(v == 'eyepatch' for v in added.values())}")
    if not a.dry and added:
        shutil.copyfile(os.path.join(PROD, 'fixlist.json'), os.path.join(PROD, f'fixlist.json.bak_{time.strftime("%m%d_%H%M")}'))
        fix.update(added)
        json.dump(fix, open(os.path.join(PROD, 'fixlist.json'), 'w'), indent=1)
        print('fixlist now', len(fix))


if __name__ == '__main__':
    main()
