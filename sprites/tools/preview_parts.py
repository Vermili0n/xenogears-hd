"""Reassemble frames from sliced replacement parts (4x) exactly as the game composes them: shows seams between parts.

  python preview_parts.py --hero-dir extracted/disc1_full/fei --parts ai/fei_pilotv3/parts --set 427_0 --frames 0-40 --out pod/report/pilot_frames.png
Missing parts fall back to the xBR-smoothed original (marked by a red dot in the corner of the frame).
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero, xbr4  # noqa: E402

S = 4
GAME_UV = os.environ.get('GAME_UV') == '1'  # preview as the game draws it (UV span = size-1)


def assemble4(h, parts_dir, setkey, fi, cache):
    places = h.placements(setkey, fi)
    _, (x0, y0) = h.assemble(places)
    W = max(p['x'] + p['w'] for p in places) - x0
    H = max(p['y'] + p['h'] for p in places) - y0
    canvas = Image.new('RGBA', (W * S, H * S), (0, 0, 0, 0))
    missing = 0
    for p in places:
        name = f"{p['block']}-{p['pal']}"
        if name not in cache:
            fp = os.path.join(parts_dir, name + '.png')
            if os.path.exists(fp):  # pack convention: alpha 128 = opaque texel
                arr = np.array(Image.open(fp).convert('RGBA'))
                arr[..., 3] = np.where(arr[..., 3] > 0, 255, 0)
                im = Image.fromarray(arr, 'RGBA')
                nw, nh = h.part(p['block'], p['pal']).size
                if GAME_UV and nw > 1 and nh > 1:  # emulate the game: texels 0..w-1 stretched over the whole part
                    k = im.width // nw
                    im = im.crop((0, 0, (nw - 1) * k, (nh - 1) * k))
                if im.size != (nw * S, nh * S):  # 8x parts / game stretch: preview at 4x
                    im = im.resize((nw * S, nh * S), Image.LANCZOS)
                cache[name] = (im, True)
            else:
                c4, m4 = xbr4(h.part(p['block'], p['pal']))
                cache[name] = (Image.fromarray(np.dstack([c4, (m4 * 255).astype(np.uint8)]), 'RGBA'), False)
        im, ok = cache[name]
        missing += not ok
        if p['flipx']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        canvas.alpha_composite(im, ((p['x'] - x0) * S, (p['y'] - y0) * S))
    return canvas, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero-dir', required=True)
    ap.add_argument('--parts', required=True)
    ap.add_argument('--set', required=True)
    ap.add_argument('--frames', default='0-31')
    ap.add_argument('--out', required=True)
    ap.add_argument('--cols', type=int, default=8)
    ap.add_argument('--bg', default='60,90,60')
    a = ap.parse_args()
    h = Hero(os.path.join(ROOT, a.hero_dir) if not os.path.isabs(a.hero_dir) else a.hero_dir)
    lo, hi = (int(x) for x in a.frames.split('-'))
    frames = list(range(lo, min(hi + 1, len(h.layout[a.set]['frames']))))
    cache, ims = {}, []
    for fi in frames:
        new, miss = assemble4(h, os.path.join(ROOT, a.parts) if not os.path.isabs(a.parts) else a.parts, a.set, fi, cache)
        old, _ = h.assemble(h.placements(a.set, fi))
        old = old.resize((old.width * S, old.height * S), Image.NEAREST)
        ims.append((fi, old, new, miss))
    cw = max(o.width for _, o, _, _ in ims) * 2 + 8
    ch = max(o.height for _, o, _, _ in ims) + 16
    bg = tuple(int(x) for x in a.bg.split(','))
    rows = (len(ims) + a.cols - 1) // a.cols
    sheet = Image.new('RGB', (a.cols * cw, rows * ch), bg)
    d = ImageDraw.Draw(sheet)
    for k, (fi, old, new, miss) in enumerate(ims):
        x, y = (k % a.cols) * cw, (k // a.cols) * ch
        d.text((x + 2, y + 1), str(fi), fill=(255, 255, 0))
        sheet.paste(old, (x, y + 14), old)
        sheet.paste(new, (x + old.width + 4, y + 14), new)
        if miss:
            d.ellipse((x + cw - 10, y + 2, x + cw - 4, y + 8), fill=(255, 0, 0))
    sheet.save(os.path.join(ROOT, a.out) if not os.path.isabs(a.out) else a.out)
    print(sheet.size, 'frames', len(ims), 'with missing parts', sum(1 for i in ims if i[3]))


if __name__ == '__main__':
    main()
