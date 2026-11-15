"""Elly's chest gem drawn in some HD frames and missing in others (01.11.2026).

DO NOT RUN: not a defect. The user found the cause: in her breathing / idle animation the chest rises and covers
the gem, so it shows in some frames only, as in the original sprite. Kept for reference only.

The sprite has a small dark spot on the chest (palette index 12); the redraw turned it into a green gem in 98 parts
and left it out elsewhere. Every part where the pixel neighbourhood of a gem part repeats exactly (same indices,
gem bbox + 1 texel) but the HD has no gem gets the gem's HD texels copied from that part (existing pixels only).

  python elly_gem_fix.py [--preview] [--dry]      (RetroArch closed for the real run)
Backups: <DATA_DRIVE>\\xeno_gem_backup_2026-11-01. Log: pod/report/elly_gem_fix.log.
"""
import argparse
import json
import os
import shutil
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from elly934_finalize import write_bc7_from_psx  # noqa: E402
from hero_palette_swaps import hero_cluts  # noqa: E402

HDIR = os.path.join(ROOT, 'extracted', 'disc1_full', 'elly')
BACKUP = r'<DATA_DRIVE>\xeno_gem_backup_2026-11-01'
LOG = os.path.join(ROOT, 'pod', 'report', 'elly_gem_fix.log')


def is_green(hd):
    return (hd[..., 1] > hd[..., 0] + 40) & (hd[..., 1] > hd[..., 2] + 15) & ~(hd == 0).all(-1)


def plan():
    CL = hero_cluts('elly')
    lay = json.load(open(os.path.join(HDIR, 'layout.json')))
    keys = {(p['block'], v['palettes'][min(p['clut'], len(v['palettes']) - 1)])
            for v in lay.values() for f in v['frames'] for p in f}
    idx, hds, gem = {}, {}, {}
    for blk, pal in sorted(keys):
        bc, pp = os.path.join(PACK, f'{blk}-{pal}.bc7'), os.path.join(HDIR, 'parts', f'{blk}-{pal}.png')
        if not (os.path.exists(bc) and os.path.exists(pp) and pal in CL):
            continue
        a = np.asarray(Image.open(pp).convert('RGBA')).astype(int)
        c = np.array(CL[pal])
        rgb = np.stack([(c & 31) * 255 // 31, ((c >> 5) & 31) * 255 // 31, ((c >> 10) & 31) * 255 // 31], -1)
        d = np.abs(a[..., None, :3] - rgb[None, None]).sum(-1)
        d[..., 0] += 10 ** 6
        ix = d.argmin(-1)
        ix[a[..., 3] == 0] = 0
        idx[(blk, pal)] = ix
        hd = read_bc7_level0(bc).astype(np.int16)
        hds[(blk, pal)] = hd
        g = is_green(hd)
        if g.sum() >= 40:
            S = hd.shape[1] // ix.shape[1]
            ty, tx = np.nonzero(g.any(1))[0] // S, np.nonzero(g.any(0))[0] // S
            gem[(blk, pal)] = (ty.min(), ty.max(), tx.min(), tx.max(), S)
    fixes = {}
    for src, (y0, y1, x0, x1, S) in gem.items():
        six = idx[src]
        Y0, X0 = max(0, y0 - 1), max(0, x0 - 1)
        t = six[Y0:min(six.shape[0], y1 + 2), X0:min(six.shape[1], x1 + 2)]
        for k, ix in idx.items():
            if k in gem or k[1] != src[1] or t.shape[0] > ix.shape[0] or t.shape[1] > ix.shape[1]:
                continue
            for y in range(ix.shape[0] - t.shape[0] + 1):
                for x in range(ix.shape[1] - t.shape[1] + 1):
                    if np.array_equal(ix[y:y + t.shape[0], x:x + t.shape[1]], t):
                        ty0, tx0 = y + (y0 - Y0), x + (x0 - X0)
                        fixes.setdefault(k, {}).setdefault((ty0, tx0), (src, y0, y1, x0, x1, S))
    return fixes, hds


def apply_fix(hd, items, hds):
    out = hd.copy()
    for (ty0, tx0), (src, y0, y1, x0, x1, S) in items.items():
        s = hds[src][y0 * S:(y1 + 1) * S, x0 * S:(x1 + 1) * S]
        h, w = s.shape[:2]
        if ty0 * S + h > out.shape[0] or tx0 * S + w > out.shape[1]:
            continue
        region = out[ty0 * S:ty0 * S + h, tx0 * S:tx0 * S + w]
        m = ~(s == 0).all(-1) & ~(region == 0).all(-1)      # only over drawn pixels of the target
        region[m] = s[m]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    fixes, hds = plan()
    os.makedirs(BACKUP, exist_ok=True)
    n = 0
    for (blk, pal), items in sorted(fixes.items()):
        path = os.path.join(PACK, f'{blk}-{pal}.bc7')
        out = apply_fix(hds[(blk, pal)], items, hds)
        if a.dry:
            n += 1
            continue
        if not os.path.exists(os.path.join(BACKUP, os.path.basename(path))):
            shutil.copyfile(path, os.path.join(BACKUP, os.path.basename(path)))
        if write_bc7_from_psx(path, out):
            n += 1
    line = time.strftime('%d.%m %H:%M ') + f'gem copied into {n} parts' + (' (dry)' if a.dry else '')
    print(line)
    open(LOG, 'a', encoding='utf-8').write(line + '\n')


if __name__ == '__main__':
    main()
