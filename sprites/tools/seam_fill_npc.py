"""Close HD seams for map NPC / story sets (01.11.2026; heroes: seam_fill_all.py, why: seam_fill.py).

NPC sets live in the pack as VRAM upload blocks (64x16 words of the set's page, one file per palette), not as
parts. Interior texels are found per frame on the page (a part = a rectangle of the page, index 0 transparent),
unioned over all frames, then each block file of every use and palette gets its transparent HD pixels in those
texels inpainted (BC7 + mips rebuilt, originals backed up to <DATA_DRIVE>\\xeno_seam_backup_2026-11-01).

  python seam_fill_npc.py [--only <npc id>,...] [--workers 12] [--dry]      (RetroArch closed)
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from alias_dump_parts import PACK  # noqa: E402
from install_parts import excluded_groups  # noqa: E402
from seam_fill_all import log, one  # noqa: E402

S = 8
PILOTS = ['f6ad8ce563', '36e3637a9a', 'd8943ce397']


def rect(name):
    """'r{tid}x{sx}y{sy}w{w}h{h}' (hex) -> (sx, sy, w, h) in page texels."""
    i = {c: name.index(c) for c in 'xywh'}
    return (int(name[i['x'] + 1:i['y']], 16), int(name[i['y'] + 1:i['w']], 16), int(name[i['w'] + 1:i['h']], 16),
            int(name[i['h'] + 1:], 16))


def page_interior(ndir):
    idx = np.load(os.path.join(ndir, 'page.npy'))
    lay = json.load(open(os.path.join(ndir, 'layout.json')))['npc']
    inner = np.zeros(idx.shape, bool)
    for f in lay['frames']:
        pl = []
        for p in f:
            sx, sy, w, h = rect(p['block'])
            m = idx[sy:sy + h, sx:sx + w] != 0
            if m.size == 0:
                continue
            if p['flipx']:
                m = m[:, ::-1]
            if p['flipy']:
                m = m[::-1]
            pl.append((p['dx'] + p['mx'], p['dy'] + p['my'], m, (sx, sy, w, h), p))
        if not pl:
            continue
        x0 = min(x for x, _, _, _, _ in pl)
        y0 = min(y for _, y, _, _, _ in pl)
        W = max(x + m.shape[1] for x, _, m, _, _ in pl) - x0
        H = max(y + m.shape[0] for _, y, m, _, _ in pl) - y0
        cov = np.zeros((H, W), bool)
        for x, y, m, _, _ in pl:
            cov[y - y0:y - y0 + m.shape[0], x - x0:x - x0 + m.shape[1]] |= m
        pad = np.pad(cov, 1, constant_values=False)
        fin = cov.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                fin &= pad[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]
        for x, y, m, (sx, sy, w, h), p in pl:
            part = fin[y - y0:y - y0 + m.shape[0], x - x0:x - x0 + m.shape[1]] & m
            if p['flipx']:
                part = part[:, ::-1]
            if p['flipy']:
                part = part[::-1]
            inner[sy:sy + h, sx:sx + w] |= part
    return inner


def jobs_for(ndir, dry):
    inner = page_interior(ndir)
    info = json.load(open(os.path.join(ndir, 'uses.json')))
    PH, PW = inner.shape
    out, seen = [], set()
    for use in info['uses']:
        for b in use['blocks']:
            px0, py0 = (b['x'] - use['sx']) * 4, b['y'] - use['sy']
            m = np.zeros((b['h'], b['w'] * 4), bool)
            y0, y1 = max(0, py0), min(PH, py0 + b['h'])
            x0, x1 = max(0, px0), min(PW, px0 + b['w'] * 4)
            if y1 <= y0 or x1 <= x0:
                continue
            m[y0 - py0:y1 - py0, x0 - px0:x1 - px0] = inner[y0:y1, x0:x1]
            if not m.any():
                continue
            for pal in info['palettes']:
                path = os.path.join(PACK, f"{b['hash']:x}-{pal}.bc7")
                if path not in seen and os.path.exists(path):
                    seen.add(path)
                    out.append((path, m, dry))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    skip = excluded_groups()
    dirs = sorted({m['hero_dir'] for m in meta.values() if 'npc_full' in m['hero_dir'] and m['group'] not in skip})
    dirs += [f'extracted/npc_full/{p}' for p in PILOTS]
    if a.only:
        dirs = [d for d in dirs if os.path.basename(d) in set(a.only.split(','))]
    t0 = time.time()
    jobs = []
    for d in dirs:
        nd = os.path.join(ROOT, d)
        if all(os.path.exists(os.path.join(nd, f)) for f in ('page.npy', 'layout.json', 'uses.json')):
            jobs += jobs_for(nd, a.dry)
    with Pool(a.workers) as pool:
        res = pool.map(one, jobs, chunksize=8)
    log(f'NPC sets {len(dirs)}: block files {len(jobs)}, filled {sum(1 for r in res if r > 0)} '
        f'({sum(r for r in res if r > 0)} HD px), errors {sum(1 for r in res if r < 0)}, {time.time() - t0:.0f} s'
        + (' (dry)' if a.dry else ''))


if __name__ == '__main__':
    main()
