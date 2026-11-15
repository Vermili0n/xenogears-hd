"""Eye-region QA sheets for characters with glasses: in every frame whose SPRITE head shows the glasses glint (small
grey/white specks in the top of the figure), crop the region around the specks in the sprite and in the render, side by
side, many per page - spotting renders that dropped the glasses.

  python glasses_sheet.py <group> [--top 0.4] [--h 110]
Writes pod/report/qa/z_<group>_glasses_<n>.png; prints the pages and how many frames were shown.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = r'<XENO_SPRITES>'
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402

BG = (150, 170, 90)
MAX_W, MAX_H, GAP, LABEL = 2000, 1400, 8, 16


def glint_box(o, top):
    a = np.asarray(o)
    al = a[..., 3] > 127
    ys, xs = np.nonzero(al)
    if not len(ys):
        return None
    y0, y1 = ys.min(), ys.min() + max(2, int((ys.max() - ys.min() + 1) * top))
    rgb = a[..., :3].astype(np.int16)
    neutral = (rgb.max(2) - rgb.min(2) < 24) & (rgb.max(2) >= 125) & al
    neutral[:y0] = False
    neutral[y1:] = False
    n, lab, st, _ = cv2.connectedComponentsWithStats(neutral.astype(np.uint8), connectivity=8)
    head_area = (y1 - y0) * (xs.max() - xs.min() + 1)
    keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] <= 0.03 * head_area]
    if not keep:
        return None
    bx0 = min(st[i, 0] for i in keep)
    by0 = min(st[i, 1] for i in keep)
    bx1 = max(st[i, 0] + st[i, 2] for i in keep)
    by1 = max(st[i, 1] + st[i, 3] for i in keep)
    side = max(bx1 - bx0, by1 - by0, int((y1 - y0) * 0.6))
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    return (max(0, int(cx - side)), max(0, int(cy - side * 0.8)), min(a.shape[1], int(cx + side)),
            min(a.shape[0], int(cy + side * 0.8)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('group')
    ap.add_argument('--top', type=float, default=0.4)
    ap.add_argument('--h', type=int, default=110)
    a = ap.parse_args()
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    frames = sorted({(m['set'], m['frame']) for m in meta.values() if m['group'] == a.group})
    hd = next(m['hero_dir'] for m in meta.values() if m['group'] == a.group)
    h = Hero(os.path.join(ROOT, hd))
    work = os.path.join(ROOT, 'ai', 'prod_work', a.group, 'work')
    cells = []
    for s, f in frames:
        rp = os.path.join(work, f'{s}_{f:03d}_red.png')
        if not os.path.exists(rp):
            continue
        o = frame_rgba(h, s, f)
        box = glint_box(o, a.top)
        if not box:
            continue
        ob = Image.new('RGBA', o.size, BG + (255,))
        ob.alpha_composite(o)
        r = Image.open(rp).convert('RGB')
        if r.size != o.size:
            r = r.resize(o.size, Image.LANCZOS)
        rb = Image.new('RGB', o.size, BG)
        rb.paste(r, (0, 0), o.getchannel('A').point(lambda v: 255 if v > 127 else 0))
        sc, rc = ob.convert('RGB').crop(box), rb.crop(box)
        w = max(1, round(sc.width * a.h / sc.height))
        cell = Image.new('RGB', (2 * w + 4, a.h), (45, 45, 45))
        cell.paste(sc.resize((w, a.h), Image.NEAREST), (0, 0))
        cell.paste(rc.resize((w, a.h), Image.LANCZOS), (w + 4, 0))
        cells.append((f'{s}:{f}', cell))
    pages, page, row, x, y = [], [], [], 0, 0
    for lab, im in cells:
        if row and x + im.width > MAX_W:
            page.append(row)
            y += a.h + LABEL + GAP
            row, x = [], 0
            if y + a.h + LABEL > MAX_H:
                pages.append(page)
                page, y = [], 0
        row.append((x, lab, im))
        x += im.width + GAP
    if row:
        page.append(row)
    if page:
        pages.append(page)
    out_dir = os.path.join(ROOT, 'pod', 'report', 'qa')
    for k, pg in enumerate(pages):
        W = max(x + im.width for r in pg for x, _, im in r)
        H = len(pg) * (a.h + LABEL + GAP)
        sheet = Image.new('RGB', (W, H), (30, 30, 30))
        d = ImageDraw.Draw(sheet)
        for i, r in enumerate(pg):
            yy = i * (a.h + LABEL + GAP)
            for x, lab, im in r:
                d.text((x + 2, yy + 2), lab, fill=(255, 255, 0))
                sheet.paste(im, (x, yy + LABEL))
        p = os.path.join(out_dir, f'z_{a.group}_glasses_{k}.png')
        sheet.save(p)
        print(p, f'{W}x{H}')
    print(len(cells), 'frames with a glint of', len(frames))


if __name__ == '__main__':
    main()
