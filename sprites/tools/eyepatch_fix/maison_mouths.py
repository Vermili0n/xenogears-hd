"""Mouth area of Maison's repainted heads, large, with a canvas grid: sprite | head render | frame from the pack. Only the heads with a repaint mask.
  python maison_mouths.py <out_prefix> [--only 037,038] [--per 12]"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import verify_0311 as v  # noqa: E402

M2 = os.path.join(ROOT, 'ai', 'redraw', 'maison2')
RES = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod', 'v4')
PROD = os.path.join(ROOT, 'ai', 'prod')
META = json.load(open(os.path.join(PROD, 'meta.json')))
SIDS = {'6e595c': '6e595cab89', '2be527': '2be5277d28', 'a09633': 'a096333c67', '1c0f2c': '1c0f2c14f4'}
ap = argparse.ArgumentParser()
ap.add_argument('out')
ap.add_argument('--only', default='')
ap.add_argument('--per', type=int, default=12)
a = ap.parse_args()
names = [j['name'] for j in json.load(open(os.path.join(M2, 'jobs.json')))]
if a.only:
    names = [n for n in names if any(o in n for o in a.only.split(','))]
Z = 2
cells = []
v.K = 16
for n in names:
    fr = n[:-6]
    m = META[fr]
    mask = np.asarray(Image.open(os.path.join(M2, 'mask', n + '.png')).convert('L'))
    ys, xs = np.nonzero(mask > 0)
    # the big blob of the mask = the mustache
    x0, x1, y0, y1 = max(0, xs.min() - 50), min(512, xs.max() + 50), max(0, ys.min() - 40), min(512, ys.max() + 40)
    if x1 - x0 > 230:
        x1 = x0 + 230
    head = Image.open(os.path.join(RES, n + '.png')).convert('RGB').crop((x0, y0, x1, y1))
    ctrl = Image.open(os.path.join(PROD, 'control', n + '.png')).convert('RGB').crop((x0, y0, x1, y1))
    sid = fr.split('__')[0].split('_')[-1]
    fi = m['frame']
    hx, hy = m['head']
    pack = None
    if sid != '1c0f2c':
        old, new = v.story_frame(SIDS[sid], fi)
        if new is not None:
            pack = Image.new('RGB', (512, 512), (150, 170, 90))
            pack.paste(new, (-hx * 16, -hy * 16), new)
            pack = pack.crop((x0, y0, x1, y1))
    ims = [ctrl, head] + ([pack] if pack is not None else [])
    ims = [i.resize((i.width * Z, i.height * Z), Image.LANCZOS) for i in ims]
    d = ImageDraw.Draw(ims[1])
    for vx in range((x0 // 20 + 1) * 20, x1, 20):
        X = (vx - x0) * Z
        d.line([(X, 0), (X, 6)], fill=(0, 255, 255))
        if vx % 40 == 0:
            d.text((X + 1, 7), str(vx), fill=(0, 255, 255))
    for vy in range((y0 // 20 + 1) * 20, y1, 20):
        Y = (vy - y0) * Z
        d.line([(0, Y), (6, Y)], fill=(0, 255, 255))
        if vy % 40 == 0:
            d.text((8, Y), str(vy), fill=(0, 255, 255))
    cells.append((n.replace('c_maison_', '').replace('__head', '').replace('__npc', ''), ims))
W, Hmax = 1990, 1450
pages, page, x, y, rh = [], [], 6, 6, 0
for lab, ims in cells:
    w, h_ = sum(i.width + 2 for i in ims) + 8, max(i.height for i in ims) + 15
    if x + w > W and page:
        x, y, rh = 6, y + rh + 4, 0
    if y + h_ > Hmax and page:
        pages.append(page)
        page, x, y, rh = [], 6, 6, 0
    page.append((x, y, lab, ims))
    x += w
    rh = max(rh, h_)
pages.append(page)
for pi, pg in enumerate(pages):
    H = max(c[1] + max(i.height for i in c[3]) + 20 for c in pg)
    s = Image.new('RGB', (W, H), (60, 60, 60))
    dd = ImageDraw.Draw(s)
    for x, y, lab, ims in pg:
        dd.text((x, y), lab, fill=(255, 255, 0))
        xx = x
        for i in ims:
            s.paste(i, (xx, y + 13))
            xx += i.width + 2
    p = f'{a.out}_{pi + 1}.png'
    s.save(p)
    print(p, s.size, len(pg))
