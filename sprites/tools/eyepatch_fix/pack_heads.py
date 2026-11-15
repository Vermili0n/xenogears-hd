"""Head crops of a hero set's frames as the PACK has them (bc7 parts), next to the native sprite. QA sheet pages.

  python pack_heads.py <hero_dir> <set> <out_prefix> [--frames a-b] [--top 0.4] [--k 6]
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

T = r'<XENO_SPRITES>\tools'
sys.path.insert(0, T)
sys.path.insert(0, r'<XENO_BC7>')
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402


def pack_frame(h, setkey, fi, k, cache):
    places = h.placements(setkey, fi)
    _, (x0, y0) = h.assemble(places)
    W = max(p['x'] + p['w'] for p in places) - x0
    H = max(p['y'] + p['h'] for p in places) - y0
    canvas = Image.new('RGBA', (W * k, H * k), (0, 0, 0, 0))
    miss = 0
    for p in places:
        name = f"{p['block']}-{p['pal']}"
        if name not in cache:
            f = os.path.join(PACK, name + '.bc7')
            nw, nh = h.part(p['block'], p['pal']).size
            if os.path.exists(f):
                a = read_bc7_level0(f).copy()
                a[..., 3] = np.where(a[..., 3] > 0, 255, 0)
                cache[name] = (Image.fromarray(a, 'RGBA').resize((nw * k, nh * k), Image.LANCZOS), True)
            else:
                im = h.part(p['block'], p['pal']).convert('RGBA')
                cache[name] = (im.resize((nw * k, nh * k), Image.NEAREST), False)
        im, ok = cache[name]
        miss += not ok
        if p['flipx']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        canvas.alpha_composite(im, ((p['x'] - x0) * k, (p['y'] - y0) * k))
    return canvas, miss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('hero_dir')
    ap.add_argument('set')
    ap.add_argument('out')
    ap.add_argument('--frames', default='')
    ap.add_argument('--top', type=float, default=0.4)
    ap.add_argument('--k', type=int, default=6)
    ap.add_argument('--max-w', type=int, default=2000)
    ap.add_argument('--max-h', type=int, default=1400)
    a = ap.parse_args()
    h = Hero(a.hero_dir)
    n = len(h.layout[a.set]['frames'])
    if a.frames:
        lo, hi = (int(x) for x in a.frames.split('-'))
        frames = range(lo, min(hi + 1, n))
    else:
        frames = range(n)
    cache, pairs = {}, []
    for fi in frames:
        try:
            new, miss = pack_frame(h, a.set, fi, a.k, cache)
            old, _ = h.assemble(h.placements(a.set, fi))
        except Exception as e:  # noqa: BLE001
            print('skip', fi, e)
            continue
        old = old.convert('RGBA').resize((old.width * a.k, old.height * a.k), Image.NEAREST)
        ch = max(8, int(old.height * a.top))
        pairs.append((fi, old.crop((0, 0, old.width, ch)), new.crop((0, 0, new.width, ch)), miss))
    pages, row, rows, x, rh = [], [], [], 10, 0
    for p in pairs:
        w = p[1].width * 2 + 6
        if x + w > a.max_w and row:
            rows.append((row, rh))
            row, x, rh = [], 10, 0
        row.append(p)
        x += w + 10
        rh = max(rh, p[1].height + 16)
    if row:
        rows.append((row, rh))
    page, y = [], 10
    for r in rows:
        if y + r[1] > a.max_h and page:
            pages.append(page)
            page, y = [], 10
        page.append(r)
        y += r[1] + 6
    if page:
        pages.append(page)
    for pi, pg in enumerate(pages):
        H = sum(r[1] + 6 for r in pg) + 14
        sheet = Image.new('RGB', (a.max_w, H), (150, 170, 90))
        d = ImageDraw.Draw(sheet)
        y = 10
        for r, rh in pg:
            x = 10
            for fi, old, new, miss in r:
                d.text((x, y), f'{fi}' + (' *' if miss else ''), fill=(255, 255, 0) if not miss else (255, 0, 0))
                sheet.paste(old, (x, y + 14), old)
                sheet.paste(new, (x + old.width + 6, y + 14), new)
                x += old.width * 2 + 16
            y += rh + 6
        p = f'{a.out}_{pi + 1}.png'
        sheet.save(p)
        print(p, sheet.size)


if __name__ == '__main__':
    main()
