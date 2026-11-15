"""Baseline jobs for LoRA v2 on the v3 held-out set: same frames, but v2 boards (characters) or the blank board with
the no-reference caption (NPCs) - the inputs v2 was trained with. Head crops are skipped (v2 never saw 16x heads;
its heads are cut from the full-frame renders when comparing).

  python test3_v2jobs.py [--test ai/pod_v3/test3] [--boards ai/pairs_v3/boards]
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from make_pairs_v2 import slug_of  # noqa: E402
from render_build import CAP_NOREF  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--test', default=os.path.join(ROOT, 'ai', 'pod_v3', 'test3'))
    ap.add_argument('--boards', default=os.path.join(ROOT, 'ai', 'pairs_v3', 'boards'))
    a = ap.parse_args()
    out = []
    for j in json.load(open(os.path.join(a.test, 'jobs.json'))):
        n = j['name']
        if n.endswith('__head') or n.endswith('__noref'):
            continue
        job = n.split('__')[0]
        k = dict(j)
        if job.startswith('n_'):
            k['ref'], k['prompt'] = 'ref/_blank.png', CAP_NOREF
        elif not job.startswith('g_'):
            b = slug_of(job) + '@v2.png'
            shutil.copyfile(os.path.join(a.boards, b), os.path.join(a.test, 'ref', b))
            k['ref'] = 'ref/' + b
        out.append(k)
    json.dump(out, open(os.path.join(a.test, 'jobs_v2.json'), 'w'), indent=0)
    print('v2 baseline jobs', len(out))


if __name__ == '__main__':
    main()
