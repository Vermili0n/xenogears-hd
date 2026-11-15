"""Fit ChatGPT-redrawn sprite grids back onto the original silhouettes: per-cell IoU raw / after bbox fit."""
import argparse
import os

import numpy as np
from PIL import Image

FR = 'extracted/disc1/fei/frames/{}_{:03d}.png'


def fg_mask(a):
    """Non-magenta pixels of an RGB array."""
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    mag = (r > 180) & (b > 180) & (g < 110)
    return ~mag


def bbox(m):
    ys, xs = np.where(m)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--img', required=True)
    ap.add_argument('--set', default='427_0')
    ap.add_argument('--frames', required=True, help='57-64')
    ap.add_argument('--k', type=int, default=6)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    lo, hi = map(int, a.frames.split('-'))
    ids = list(range(lo, hi + 1))
    gpt = np.asarray(Image.open(a.img).convert('RGB'))
    gm = fg_mask(gpt)
    os.makedirs(a.out, exist_ok=True)
    rows = []
    for j, i in enumerate(ids):
        o = Image.open(FR.format(a.set, i)).convert('RGBA')
        ok = o.resize((o.width * a.k, o.height * a.k), Image.NEAREST)
        cx, by = (j % 4) * 384 + 192, (j // 4) * 512 + 470
        x0, y0 = cx - ok.width // 2, by - ok.height
        om = np.zeros(gm.shape, bool)
        om[y0:y0 + ok.height, x0:x0 + ok.width] = np.asarray(ok)[..., 3] > 0
        cell = np.zeros(gm.shape, bool)
        cell[(j // 4) * 512:(j // 4 + 1) * 512, (j % 4) * 384:(j % 4 + 1) * 384] = True
        g = gm & cell
        raw = iou(g, om)
        # bbox fit: scale GPT figure so its bbox matches the original bbox
        gx0, gy0, gx1, gy1 = bbox(g)
        ox0, oy0, ox1, oy1 = bbox(om)
        crop = Image.fromarray(gpt[gy0:gy1, gx0:gx1])
        cm = Image.fromarray((g[gy0:gy1, gx0:gx1] * 255).astype(np.uint8))
        W, H = ox1 - ox0, oy1 - oy0
        fit = np.asarray(cm.resize((W, H), Image.BILINEAR)) > 127
        fm = np.zeros(gm.shape, bool)
        fm[oy0:oy1, ox0:ox1] = fit
        fitted = iou(fm, om)
        crop.resize((W, H), Image.LANCZOS).save(os.path.join(a.out, f'{a.set}_{i:03d}_fit.png'))
        rows.append((i, raw, fitted, (gx1 - gx0) / W, (gy1 - gy0) / H))
        print(f'{i:3d}  IoU raw {raw:.2f}  bbox-fit {fitted:.2f}  scale x{(gx1 - gx0) / W:.2f} y{(gy1 - gy0) / H:.2f}')
    print('mean bbox-fit IoU', np.mean([r[2] for r in rows]).round(3))


if __name__ == '__main__':
    main()
