"""Close HD seams between parts for whole heroes (01.11.2026; see seam_fill.py for the why).

  python seam_fill_all.py --heroes fei,elly,... [--workers 12] [--dry]      (RetroArch closed)
Per hero: frame_interior over ALL its sets (a texel is filled if it is inside the figure in at least one frame that
uses the part), then every pack .bc7 of its parts gets its transparent HD pixels in those texels inpainted from the
nearest drawn ones; BC7 + mips rebuilt. Originals backed up to <DATA_DRIVE>\\xeno_seam_backup_2026-11-01 (once).
Log: pod/report/seam_fill_all.log.
"""
import argparse
import json
import os
import shutil
import sys
import time
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from elly934_finalize import write_bc7_from_psx  # noqa: E402
from seam_fill import fill_interior, frame_interior  # noqa: E402

BACKUP = r'<DATA_DRIVE>\xeno_seam_backup_2026-11-01'
LOG = os.path.join(ROOT, 'pod', 'report', 'seam_fill_all.log')
S = 8


def log(s):
    s = time.strftime('%d.%m %H:%M ') + s
    print(s, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(s + '\n')


def one(args):
    path, inner, dry = args
    try:
        hd = read_bc7_level0(path).astype(np.int16)
        if hd.shape[1] != inner.shape[1] * S or hd.shape[0] != inner.shape[0] * S:
            return 0
        out, n = fill_interior(hd, None, S, (hd == 0).all(-1), inner)
        if not n or dry:
            return n
        out[..., :3][(out[..., :3] == 0).all(-1) & ~(out == 0).all(-1)] = 1
        bk = os.path.join(BACKUP, os.path.basename(path))
        if not os.path.exists(bk):
            shutil.copyfile(path, bk)
        return n if write_bc7_from_psx(path, out) else 0
    except Exception:  # noqa: BLE001
        return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--heroes', required=True)
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    os.makedirs(BACKUP, exist_ok=True)
    for hero in a.heroes.split(','):
        hdir = os.path.join(ROOT, 'extracted', 'disc1_full', hero)
        lay = json.load(open(os.path.join(hdir, 'layout.json')))
        t0 = time.time()
        inner = frame_interior([(v, hdir) for v in lay.values()], lambda h, k: os.path.join(h, 'parts'))
        jobs = [(os.path.join(PACK, f'{b}-{p}.bc7'), m, a.dry) for (b, p), m in inner.items()
                if m.any() and os.path.exists(os.path.join(PACK, f'{b}-{p}.bc7'))]
        with Pool(a.workers) as pool:
            res = pool.map(one, jobs, chunksize=8)
        changed = sum(1 for r in res if r > 0)
        log(f'{hero}: parts {len(inner)}, in pack {len(jobs)}, filled {changed} ({sum(r for r in res if r > 0)} HD px), '
            f'errors {sum(1 for r in res if r < 0)}, {time.time() - t0:.0f} s' + (' (dry)' if a.dry else ''))


if __name__ == '__main__':
    main()
