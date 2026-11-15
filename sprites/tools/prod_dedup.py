"""Drop duplicate jobs from the remaining production queue.

Jobs with byte-identical control image, the same board and the same prompt give the same render (fixed seed), so
only one of them is rendered; prod_sync.py copies that render to the other names (ai/prod/dup_jobs.json).
The new queue holds only jobs not rendered on any pod yet, one per duplicate group (none at all when some member of
the group is already rendered somewhere).

  python prod_dedup.py            -> ai/prod/jobs_v4_dd.json, jobs_v2_dd.json, dup_jobs.json (+ prints totals)
"""
import hashlib
import json
import os
import subprocess
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROD = os.path.join(ROOT, 'ai', 'prod')
KEY = os.path.expanduser('~/.ssh/<SSH_KEY>')
PODS = [('<POD_HOST>', '<POD_PORT>'), ('<POD_HOST>', '<POD_PORT>')]
FILES = {'v4': 'jobs_v4.json', 'v2': 'jobs_v2.json'}


def rendered():
    have = set()
    for host, port in PODS:
        r = subprocess.run(['ssh', '-o', 'ConnectTimeout=25', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no', '-p',
                            port, '-i', KEY, f'root@{host}',
                            "cd /workspace/res_prod && find . -name '*.png' -printf '%P\\n'"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, check=True)
        have |= {ln.strip()[:-4] for ln in r.stdout.split() if ln.strip()}
    return have                                                          # 'v4/<name>'


def main():
    have = rendered()
    dups, total_after = [], len(have)
    for tag, fn in FILES.items():
        jobs = json.load(open(os.path.join(PROD, fn)))
        groups = defaultdict(list)
        for j in jobs:
            c = hashlib.md5(open(os.path.join(PROD, j['control']), 'rb').read()).hexdigest()
            r = hashlib.md5(open(os.path.join(PROD, j['ref']), 'rb').read()).hexdigest() if j.get('ref') else ''
            groups[(c, r, j['prompt'])].append(j)
        keep = []
        for members in groups.values():
            if len(members) > 1:
                dups.append({'tag': tag, 'names': [m['name'] for m in members]})
            if any(f"{tag}/{m['name']}" in have for m in members):
                continue
            keep.append(members[0])
        order = {j['name']: i for i, j in enumerate(jobs)}
        keep.sort(key=lambda j: order[j['name']])
        json.dump(keep, open(os.path.join(PROD, fn.replace('.json', '_dd.json')), 'w'))
        total_after += len(keep)
        print(f'{tag}: {len(jobs)} jobs, {len(groups)} unique, rendered {sum(1 for h in have if h.startswith(tag + "/"))}, '
              f'queue now {len(keep)}')
    json.dump(dups, open(os.path.join(PROD, 'dup_jobs.json'), 'w'))
    print(f'duplicate groups {len(dups)}, pod images at the end {total_after}')


if __name__ == '__main__':
    main()
