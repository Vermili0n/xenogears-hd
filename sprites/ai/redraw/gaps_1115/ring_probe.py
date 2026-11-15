"""Probe: the reticle (clut 0,508) and the left gauge (clut 0,511) assembled 1:1 on the 320x224 screen from a report."""
import re
import sys

import numpy as np
from PIL import Image

from hud_common import idx8, clut, vram
from hud_frame import LINE

REP = r'<XENO_PORT>\out\fix_1115\verify\reports\2026-11-16T00-01-18-426\frame.txt'


def prims(path, cl):
    out = []
    for line in open(path, encoding='utf-8', errors='replace'):
        m = LINE.match(line)
        if not m:
            continue
        g = [float(x) if '.' in x else int(x) for x in m.groups()]
        if (g[6], g[7]) != cl or (g[2], g[3]) != (960, 0):
            continue
        out.append((g[0], [(g[11 + 4 * i], g[12 + 4 * i], g[13 + 4 * i], g[14 + 4 * i]) for i in range(4)]))
    return out


def assemble(ps, idx, H=224, W=320):
    scr = np.zeros((H, W), np.int32) - 1
    for n, pts in ps:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        us, vs = [p[2] for p in pts], [p[3] for p in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        for y in range(y0, y1):
            for x in range(x0, x1):
                # bilinear map of the axis-aligned quad: corners 0 (x0?) etc.
                fx = (x - pts[0][0]) / (pts[1][0] - pts[0][0])
                fy = (y - pts[0][1]) / (pts[2][1] - pts[0][1])
                if not (0 <= fx < 1 and 0 <= fy < 1):
                    continue
                u = pts[0][2] + fx * (pts[1][2] - pts[0][2])
                v = pts[0][3] + fy * (pts[2][3] - pts[0][3])
                scr[y, x] = idx[int(np.floor(v + 1e-6)) - 52, int(np.floor(u + 1e-6))]
    return scr


if __name__ == '__main__':
    words = np.load('hud/upload_words.npy')
    i8 = idx8(words)
    for cl in ((0, 508), (0, 511)):
        ps = prims(REP, cl)
        print(cl, len(ps))
        for n, pts in ps:
            print(' ', n, pts)
        scr = assemble(ps, i8)
        np.save(f'ring/screen_{cl[1]}.npy', scr)
        ys, xs = np.nonzero(scr >= 0)
        print(' screen box', xs.min(), xs.max(), ys.min(), ys.max())
        row = clut(vram(), 0, cl[1], 256)
        from render_frames import psx_to_rgba
        rgb = np.array([psx_to_rgba(int(c))[:3] for c in row], np.uint8)
        img = np.zeros(scr.shape + (3,), np.uint8)
        m = scr > 0
        img[m] = rgb[scr[m]]
        # false colour of the indices too
        fc = np.zeros(scr.shape + (3,), np.uint8)
        fc[m] = np.stack([(scr[m] * 37) % 256, (scr[m] * 91) % 256, (scr[m] * 151) % 256], -1)
        crop = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
        Image.fromarray(np.hstack([img[crop], fc[crop]])).resize(((xs.max() - xs.min() + 1) * 4, (ys.max() - ys.min() + 1) * 4), Image.NEAREST).save(f'ring/screen_{cl[1]}.png')
