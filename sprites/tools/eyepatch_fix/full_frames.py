"""Whole frames as the game draws them: sprite | before (backup files) | pack now.  python full_frames.py <out_prefix> set:frame ... [--k 6]"""
import argparse
import glob
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
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402

BK = sorted(glob.glob(r'<DATA_DRIVE>\xeno_redraw_backup\bart_patch_*'))[-1]


def game_part(c, w, h, k):
    H, W = c.shape[:2]
    tw = int(round((w - 1) * W / w)) if w > 1 else W
    th = int(round((h - 1) * H / h)) if h > 1 else H
    c = c[:th, :tw]
    rgb = Image.fromarray(np.ascontiguousarray(c[..., :3])).resize((w * k, h * k), Image.LANCZOS)
    rgb.putalpha(Image.fromarray(np.where(c[..., 3] > 0, 255, 0).astype(np.uint8)).resize((w * k, h * k), Image.NEAREST))
    return rgb


def frame(h, s, fi, k, dirs):
    pl = h.placements(s, fi)
    old, _ = h.assemble(pl)
    x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
    out = Image.new('RGBA', (old.width * k, old.height * k), (0, 0, 0, 0))
    for p in pl:
        nm = f"{p['block']}-{p['pal']}"
        f = next((os.path.join(d, nm + '.bc7') for d in dirs if os.path.exists(os.path.join(d, nm + '.bc7'))), None)
        if f is None:
            im = h.part(p['block'], p['pal']).convert('RGBA').resize((p['w'] * k, p['h'] * k), Image.NEAREST)
        else:
            im = game_part(read_bc7_level0(f), p['w'], p['h'], k)
        if p['flipx']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        out.alpha_composite(im, ((p['x'] - x0) * k, (p['y'] - y0) * k))
    return old.resize((old.width * k, old.height * k), Image.NEAREST), out


ap = argparse.ArgumentParser()
ap.add_argument('out')
ap.add_argument('items', nargs='+')
ap.add_argument('--k', type=int, default=6)
ap.add_argument('--max-w', type=int, default=1990)
a = ap.parse_args()
h = Hero(os.path.join(ROOT, 'extracted', 'disc1_full', 'bart'))
cells = []
for it in a.items:
    s, fi = it.split(':')
    o, now = frame(h, s, int(fi), a.k, [PACK])
    _, bef = frame(h, s, int(fi), a.k, [BK, PACK])
    cells.append((it, [o, bef, now]))
x, y, rh, pos = 6, 6, 0, []
for lab, ims in cells:
    w = sum(i.width + 3 for i in ims) + 10
    if x + w > a.max_w:
        x, y, rh = 6, y + rh + 4, 0
    pos.append((x, y, lab, ims))
    x += w
    rh = max(rh, ims[0].height + 16)
s = Image.new('RGB', (a.max_w, y + rh + 8), (150, 170, 90))
d = ImageDraw.Draw(s)
for x, y, lab, ims in pos:
    d.text((x, y), lab + ' sprite|before|now', fill=(255, 255, 0))
    xx = x
    for i in ims:
        s.paste(i, (xx, y + 13), i)
        xx += i.width + 3
s.save(a.out + '.png')
print(a.out + '.png', s.size)
