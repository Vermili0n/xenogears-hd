"""Pack sprite frames into 4x4 grids for the image model (cells 512 px, xBR-smoothed sprite at 8x on magenta).

  python make_grids.py --hero fei --out ai/fei_field --plan-priority 0 [--skip 25-40,57-64] [--per 16]
  python make_grids.py --hero fei --out ai/fei_retry --frames 427_0:12,427_0:13

Writes <out>/in/grid_<name>.png and <out>/in/grids.json (cell placement, same format as ai/or_test).
"""
import argparse
import csv
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero, xbr4  # noqa: E402

MAG = (255, 0, 255)
CELL, FEET = 512, 500


def frame_rgba(hobj, s, fi):
    frame, _ = hobj.assemble(hobj.placements(s, fi))
    c4, m4 = xbr4(frame)
    im = Image.fromarray(np.dstack([c4, (m4 * 255).astype(np.uint8)]), 'RGBA')
    im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    a = np.asarray(im).copy()
    a[..., 3] = np.where(a[..., 3] > 127, 255, 0)
    return Image.fromarray(a, 'RGBA')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', default='fei')
    ap.add_argument('--hero-dir', default='', help='sprite folder (default extracted/disc1_full/<hero>)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--plan-priority', type=int, default=None, help='take frames from plans/<hero>.csv with this priority')
    ap.add_argument('--frames', default='', help='explicit set:frame list instead of the plan')
    ap.add_argument('--skip', default='', help='frame ranges of the main set to leave out, e.g. 25-40,57-64')
    ap.add_argument('--per', type=int, default=16)
    ap.add_argument('--prefix', default='f')
    ap.add_argument('--grow', action='store_true', help='enlarge small sprites to fill the cell (the model scales them up anyway)')
    a = ap.parse_args()
    hobj = Hero(a.hero_dir or os.path.join(ROOT, 'extracted', 'disc1_full', a.hero))
    if a.frames:
        frames = [(t.split(':')[0], int(t.split(':')[1])) for t in a.frames.split(',')]
    else:
        with open(os.path.join(ROOT, 'plans', f'{a.hero}.csv')) as f:
            frames = sorted({(r['set'], int(r['frame'])) for r in csv.DictReader(f)
                             if a.plan_priority is None or int(r['priority']) == a.plan_priority})
    skip = set()
    for rng in filter(None, a.skip.split(',')):
        lo, _, hi = rng.partition('-')
        skip |= set(range(int(lo), int(hi or lo) + 1))
    frames = [(s, fi) for s, fi in frames if fi not in skip]
    cols = int(round(a.per ** 0.5))
    grow_k = 1.0
    if a.grow:  # one scale for the whole job, so every frame keeps the same size relative to the others
        sizes = [frame_rgba(hobj, s, fi).size for s, fi in frames]
        mw, mh = max(w for w, _ in sizes), max(h for _, h in sizes)
        grow_k = max(1.0, min(0.85 * FEET / mh, 0.85 * CELL / mw))
    os.makedirs(os.path.join(a.out, 'in'), exist_ok=True)
    meta = {}
    for g in range(0, len(frames), a.per):
        chunk = frames[g:g + a.per]
        if len(chunk) < a.per and len(frames) >= 1:  # partial grids confuse the model: pad with repeats
            pool = frames[:g] or frames
            chunk = chunk + [pool[i % len(pool)] for i in range(a.per - len(chunk))]
        name = f'{a.prefix}{g // a.per:02d}'
        grid = Image.new('RGB', (cols * CELL, cols * CELL), MAG)
        cells = []
        for j, (s, fi) in enumerate(chunk):
            im = frame_rgba(hobj, s, fi)
            if im.height > FEET or im.width > CELL:
                k = min(FEET / im.height, CELL / im.width)
                im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
            elif grow_k > 1.0:
                im = im.resize((int(im.width * grow_k), int(im.height * grow_k)), Image.LANCZOS)
            cx, cy = (j % cols) * CELL, (j // cols) * CELL
            x, y = cx + (CELL - im.width) // 2, cy + FEET - im.height
            grid.paste(im, (x, y), im)
            cells.append({'set': s, 'frame': fi, 'x': x, 'y': y, 'w': im.width, 'h': im.height,
                          'cx': cx, 'cy': cy, 'cols': cols, 'rows': cols})
        grid.save(os.path.join(a.out, 'in', f'grid_{name}.png'))
        meta[name] = cells
    json.dump(meta, open(os.path.join(a.out, 'in', 'grids.json'), 'w'), indent=1)
    print(f'{len(frames)} frames -> {len(meta)} grids in {a.out}/in')


if __name__ == '__main__':
    main()
