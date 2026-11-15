"""Job list for klein_batch.py: for each control cell pick the most similar accepted redraw as the identity reference.

  python klein_jobs.py --job ai/klein_fei/fei --pool fei_ --exclude ai/pairs/weak.txt --out ai/klein_fei/jobs.json
Controls come from make_grids.py --per 1 (one 512 cell per grid, same placement as ai/pairs/control).
Similarity = silhouette IoU in that shared placement + a small colour-histogram term.
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def mask_hist(path):
    a = np.asarray(Image.open(path).convert('RGB').resize((128, 128), Image.NEAREST)).astype(int)
    m = (abs(a[..., 0] - 255) + a[..., 1] + abs(a[..., 2] - 255)) > 40
    q = (a[m] // 64)
    h = np.bincount(q[:, 0] * 16 + q[:, 1] * 4 + q[:, 2], minlength=64).astype(float)
    return m, h / max(h.sum(), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--job', required=True, help='folder with in/grid_*.png + in/grids.json')
    ap.add_argument('--pool', default='fei_', help='name prefix of reference pairs in ai/pairs')
    ap.add_argument('--exclude', default='', help='file with pair names not to use as references')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    excl = set(open(os.path.join(ROOT, a.exclude)).read().split()) if a.exclude else set()
    pdir = os.path.join(ROOT, 'ai', 'pairs')
    pool = []
    for f in sorted(os.listdir(os.path.join(pdir, 'control'))):
        n = f[:-4]
        if n.startswith(a.pool) and n not in excl and os.path.exists(os.path.join(pdir, 'target', f)):
            pool.append((n, *mask_hist(os.path.join(pdir, 'control', f))))
    meta = json.load(open(os.path.join(ROOT, a.job, 'in', 'grids.json')))
    rel = os.path.relpath(os.path.join(ROOT, a.job), os.path.join(ROOT, os.path.dirname(a.out))).replace('\\', '/')
    jobs = []
    for g, cells in sorted(meta.items()):
        c = cells[0]
        m, h = mask_hist(os.path.join(ROOT, a.job, 'in', f'grid_{g}.png'))
        self_name = f"{a.pool}{c['set']}_{c['frame']:03d}"
        best = max((p for p in pool if p[0] != self_name),
                   key=lambda p: (m & p[1]).sum() / max((m | p[1]).sum(), 1) + 0.3 * np.minimum(h, p[2]).sum())
        jobs.append({'nid': os.path.basename(a.job), 'set': c['set'], 'frame': c['frame'], 'grid': g,
                     'ref': f'ai/pairs/target/{best[0]}.png', 'key': best[0]})
    json.dump(jobs, open(os.path.join(ROOT, a.out), 'w'), indent=0)
    print(len(jobs), 'jobs; refs used:', len({j['ref'] for j in jobs}), ' root for klein_batch:', rel)


if __name__ == '__main__':
    main()
