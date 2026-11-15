"""Where a defect appears: sprite | picked head render | composite | frame from the staged parts, head area, large; part borders in cyan.
  python trace_view.py <out_prefix> set:frame ... [--k 14]"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
import patch_final as pf  # noqa: E402
from pack_heads import Hero, pack_frame  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('out')
ap.add_argument('items', nargs='+')
ap.add_argument('--k', type=int, default=14)
ap.add_argument('--rows', type=int, default=20)
a = ap.parse_args()
k = a.k
h = Hero(pf.HD)
STAGE = os.path.join(pf.BART, 'stage')
cache = {}
for f in os.listdir(STAGE):
    nm = f[:-4]
    im = np.asarray(Image.open(os.path.join(STAGE, f)).convert('RGBA')).copy()
    im[..., 3] = np.where(im[..., 3] > 0, 255, 0)
    nw, nh = h.part(*nm.split('-')).size
    cache[nm] = (Image.fromarray(im, 'RGBA').resize((nw * k, nh * k), Image.LANCZOS), True)
rows = []
for it in a.items:
    s, fi = it.split(':')
    fi = int(fi)
    n = f'h_bart__{s}_{fi:03d}'
    pl = h.placements(s, fi)
    old, (x0, y0) = h.assemble(pl)
    hx, hy = pf.META[n]['head']
    c = a.rows * k
    o = old.resize((old.width * k, old.height * k), Image.NEAREST).crop((0, 0, old.width * k, c))
    head = Image.open(os.path.join(pf.F, 'v4', n + '__head.png')).convert('RGB')
    # head render placed on the frame: canvas 16x of the head window
    hd = Image.new('RGB', (old.width * k, c), (150, 170, 90))
    hd.paste(head.resize((32 * k, 32 * k), Image.LANCZOS), (hx * k, hy * k))
    red = Image.open(os.path.join(pf.BART, 'work', f'{s}_{fi:03d}_red.png')).convert('RGB').resize((old.width * k, old.height * k), Image.LANCZOS).crop((0, 0, old.width * k, c))
    new, _ = pack_frame(h, s, fi, k, dict(cache))
    nw = new.crop((0, 0, new.width, c)).copy()
    d = ImageDraw.Draw(nw)
    for p in pl:
        d.rectangle(((p['x'] - x0) * k, (p['y'] - y0) * k, (p['x'] - x0 + p['w']) * k - 1, (p['y'] - y0 + p['h']) * k - 1), outline=(0, 255, 255))
    new2 = new.crop((0, 0, new.width, c))
    rows.append((it, [o, hd, red, new2, nw]))
per = 4
for pi in range(0, len(rows), per):
    pg = rows[pi:pi + per]
    W = max(sum(i.width + 4 for i in r) for _, r in pg) + 8
    H = sum(r[0].height + 16 for _, r in pg) + 4
    s = Image.new('RGB', (W, H), (150, 170, 90))
    d = ImageDraw.Draw(s)
    y = 2
    for lab, r in pg:
        d.text((4, y), lab + '   sprite | head render | composite | new frame | + part borders', fill=(255, 255, 0))
        x = 4
        for i in r:
            s.paste(i, (x, y + 13), i if i.mode == 'RGBA' else None)
            x += i.width + 4
        y += r[0].height + 16
    p = f'{a.out}_{pi // per + 1}.png'
    s.save(p)
    print(p, s.size)
