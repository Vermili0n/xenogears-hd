r"""Reticle put together as a report's primitives draw it, at the 1920 screen's scale (x6): original | pack now | new.
  python ai\redraw\gaps_1115\ring_preview.py [<frame.txt>] [--row 508|511]  -> ring\preview_<row>_<report>.png"""
import argparse
import os

import numpy as np

import hud_frame
from gcommon import PACK, side_by_side
from hud_common import clut, crc, idx8, vram
from hud_draw import labels, paint, rotations
from hud_frame import draw, tex_hd, tex_orig
from ring_draw import HERE, apply, apply_gauge, prims

VERIFY = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))), 'xeno_port', 'out',
                      'fix_1115', 'verify', 'reports', '2026-11-16T00-01-18-426', 'frame.txt')
Z = 6


def as_tex(img):
    h = img.astype(np.float32)
    t = (img == 0).all(-1)
    a = np.where(t, 0, np.where(img[..., 3] > 0, 2, 1)).astype(np.float32)
    return np.dstack([h[..., :3], a])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('report', nargs='?', default=VERIFY)
    ap.add_argument('--row', type=int, default=508)
    ap.add_argument('--new-dir', default='', help='take the new files from this folder (else made here)')
    a = ap.parse_args()
    hud_frame.Z = Z
    v = vram()
    words = np.load(os.path.join(HERE, 'hud', 'upload_words.npy'))
    i8 = idx8(words)
    ps = []
    for line in open(a.report, encoding='utf-8', errors='replace'):
        m = hud_frame.LINE.match(line)
        if not m:
            continue
        g = [float(x) if '.' in x else int(x) for x in m.groups()]
        if (g[2], g[3]) != (960, 0) or (g[6], g[7]) != (0, a.row):
            continue
        ps.append((g[0], g[1], g[4], g[5], (g[8], g[9], g[10]),
                   [(g[11 + 4 * i], g[12 + 4 * i], g[13 + 4 * i], g[14 + 4 * i]) for i in range(4)]))
    names = {line.split('-> pack-upload ')[1].split('/')[-1].split('.')[0] for line in open(a.report, encoding='utf-8', errors='replace')
             if f'clut 0,{a.row} ' in line and '-> pack-upload ' in line}
    name = sorted(names)[0]
    base = clut(v, 0, a.row, 256)
    row = next(r for c, r in rotations(base).items() if f'49b52d64-{c}' == name)
    xs = [p[0] for q in ps for p in q[5]]
    ys = [p[1] for q in ps for p in q[5]]
    x0, x1, y0, y1 = int(min(xs)) - 4, int(max(xs)) + 4, int(min(ys)) - 4, int(max(ys)) + 4
    new = paint(labels(i8, 256), row)
    if a.row == 508:
        new = apply(new, row)
    elif a.row == 511:
        new = apply_gauge(new, row)
    texs = [(tex_orig(i8, row), 1), (tex_hd(os.path.join(PACK, name + '.bc7')), 8), (as_tex(new), 8)]
    pics = []
    for tex, k in texs:
        canvas = np.zeros((224 * Z, 320 * Z, 3), np.float32)
        canvas[:] = (40, 44, 48)
        for n, semi, depth, mode, colour, pts in sorted(ps, key=lambda p: -p[0]):
            draw(canvas, tex, k, pts, depth, semi, mode, colour)
        pics.append(np.clip(canvas, 0, 255).astype(np.uint8)[y0 * Z:y1 * Z, x0 * Z:x1 * Z])
    rep = os.path.basename(os.path.dirname(a.report))
    out = os.path.join(HERE, 'ring', f'preview_{a.row}_{rep}.png')
    side_by_side(pics).save(out)
    print(name, len(ps), 'primitives ->', out)


if __name__ == '__main__':
    main()
