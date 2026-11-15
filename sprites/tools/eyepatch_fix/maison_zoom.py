"""Big faces: pack now | after the cut (ai/redraw/maison2/cut).  python maison_zoom.py <out_prefix> sid:frame ... [--k 14] [--top 0.34]"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import maison_cut as mc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('out')
ap.add_argument('items', nargs='+')
ap.add_argument('--k', type=int, default=14)
ap.add_argument('--top', type=float, default=0.34)
a = ap.parse_args()


def over(f):
    n = os.path.join(mc.CUT, os.path.basename(f)[:-4] + '.npy')
    return np.load(n) if os.path.exists(n) else mc.read_bc7_level0(f)


cells, sheets = [], {}
for it in a.items:
    sid, fi = it.split(':')
    sid = next(s for s in mc.SETS if s.startswith(sid))
    if sid not in sheets:
        sheets[sid] = (mc.Hero(os.path.join(mc.NPC, sid)), mc.set_sheet(sid, mc.read_bc7_level0), mc.set_sheet(sid, over))
    h, hd0, hd1 = sheets[sid]
    o, now = mc.draw(h, hd0, int(fi), a.k)
    _, new = mc.draw(h, hd1, int(fi), a.k)
    c = int(o.height * a.top)
    cells.append((it, now.crop((0, 0, now.width, c)), new.crop((0, 0, new.width, c))))
W, Hmax = 1990, 1450
pages, page, x, y, rh = [], [], 6, 6, 0
for lab, n1, n2 in cells:
    w, h_ = n1.width + n2.width + 10, n1.height + 16
    if x + w > W and page:
        x, y, rh = 6, y + rh + 4, 0
    if y + h_ > Hmax and page:
        pages.append(page)
        page, x, y, rh = [], 6, 6, 0
    page.append((x, y, lab, n1, n2))
    x += w
    rh = max(rh, h_)
pages.append(page)
for pi, pg in enumerate(pages):
    H = max(c[1] + c[3].height + 20 for c in pg)
    s = Image.new('RGB', (W, H), (150, 170, 90))
    d = ImageDraw.Draw(s)
    for x, y, lab, n1, n2 in pg:
        d.text((x, y), lab, fill=(255, 255, 0))
        s.paste(n1, (x, y + 13), n1)
        s.paste(n2, (x + n1.width + 2, y + 13), n2)
    p = f'{a.out}_{pi + 1}.png'
    s.save(p)
    print(p, s.size, len(pg))
