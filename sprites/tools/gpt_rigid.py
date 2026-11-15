"""Rigid (scale + shift, no warping) fit of ChatGPT redraws onto the original sprites at 4x.
Outputs per frame: <set>_<fi>_rigid.png (RGBA, drawing's own alpha) and a review sheet with the original outline."""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
from ai_redraw import xbr4  # noqa: E402

FR = 'extracted/disc1/fei/frames/{}_{:03d}.png'


def fg_mask(a):
    r, g, b = (a[..., c].astype(int) for c in range(3))
    return ~((r - g > 60) & (b - g > 60))


def bbox(m):
    ys, xs = np.where(m)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def chamfer(a, b):
    """Symmetric boundary distance between masks a and b (px): mean and 95th percentile."""
    ea = cv2.morphologyEx(a.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    eb = cv2.morphologyEx(b.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    da = cv2.distanceTransform((~ea).astype(np.uint8), cv2.DIST_L2, 5)
    db = cv2.distanceTransform((~eb).astype(np.uint8), cv2.DIST_L2, 5)
    d = np.concatenate([db[ea], da[eb]])
    return float(d.mean()), float(np.percentile(d, 95))


def best_fit(dcrop, dmask, om, s0):
    """Search scale (uniform + slight anisotropy) and shift maximising IoU with the original mask om."""
    H, W = om.shape
    A = om.sum()
    best = (-1, None)
    pad = 40
    big = np.zeros((H + 2 * pad, W + 2 * pad), np.float32)
    big[pad:pad + H, pad:pad + W] = om
    for s in s0 * np.linspace(0.88, 1.12, 25):
        for asp in (0.94, 0.97, 1.0, 1.03, 1.06):
            w, h = max(4, int(round(dmask.shape[1] * s * asp))), max(4, int(round(dmask.shape[0] * s)))
            if w >= big.shape[1] or h >= big.shape[0]:
                continue
            m = cv2.resize(dmask.astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)
            m = (m > 0.5).astype(np.float32)
            inter = cv2.matchTemplate(big, m, cv2.TM_CCORR)
            B = m.sum()
            iou = inter / (A + B - inter)
            y, x = np.unravel_index(np.argmax(iou), iou.shape)
            if iou[y, x] > best[0]:
                best = (float(iou[y, x]), (w, h, x - pad, y - pad))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--img', required=True)
    ap.add_argument('--set', default='427_0')
    ap.add_argument('--frames', required=True)
    ap.add_argument('--k', type=int, default=6, help='scale of the sprites in the ChatGPT input grid')
    ap.add_argument('--cell', default='384x512')
    ap.add_argument('--feet', type=int, default=470, help='feet line inside a cell in the input grid')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    cwid, chei = map(int, a.cell.split('x'))
    lo, hi = map(int, a.frames.split('-'))
    gpt = np.asarray(Image.open(a.img).convert('RGB'))
    if gpt.shape[1] != 4 * cwid or gpt.shape[0] != 2 * chei:  # ChatGPT may change the canvas size
        gpt = cv2.resize(gpt, (4 * cwid, 2 * chei), interpolation=cv2.INTER_AREA)
    gm = fg_mask(gpt)
    os.makedirs(a.out, exist_ok=True)
    res = []
    for j, i in enumerate(range(lo, hi + 1)):
        o = Image.open(FR.format(a.set, i)).convert('RGBA')
        c4, m4 = xbr4(o)
        cell = np.zeros_like(gm)
        cell[(j // 4) * chei:(j // 4 + 1) * chei, (j % 4) * cwid:(j % 4 + 1) * cwid] = True
        g = gm & cell
        n, lab, st, _ = cv2.connectedComponentsWithStats(g.astype(np.uint8), 8)
        keep = 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])  # the figure = biggest blob in the cell
        g = lab == keep
        gx0, gy0, gx1, gy1 = bbox(g)
        dcrop = gpt[gy0:gy1, gx0:gx1]
        dmask = g[gy0:gy1, gx0:gx1]
        ox0, oy0, ox1, oy1 = bbox(m4)
        s0 = (oy1 - oy0) / (gy1 - gy0)
        iou, (w, h, x, y) = best_fit(dcrop, dmask, m4, s0)
        rgba = np.dstack([dcrop, dmask.astype(np.uint8) * 255])
        rgba = cv2.resize(rgba, (w, h), interpolation=cv2.INTER_AREA)
        canvas = np.zeros(m4.shape + (4,), np.uint8)
        # paste with clipping
        H, W = m4.shape
        sx0, sy0 = max(0, -x), max(0, -y)
        dx0, dy0 = max(0, x), max(0, y)
        ww, hh = min(w - sx0, W - dx0), min(h - sy0, H - dy0)
        canvas[dy0:dy0 + hh, dx0:dx0 + ww] = rgba[sy0:sy0 + hh, sx0:sx0 + ww]
        Image.fromarray(canvas, 'RGBA').save(os.path.join(a.out, f'{a.set}_{i:03d}_rigid.png'))
        cm, c95 = chamfer(canvas[..., 3] > 127, m4)
        print(f'{i:3d}  rigid IoU {iou:.3f}  edge err mean {cm:.1f}px p95 {c95:.1f}px (4x)  scale {w / dcrop.shape[1]:.3f}')
        res.append((i, o, c4, m4, canvas, iou, cm, c95))
    print('mean rigid IoU', round(float(np.mean([r[5] for r in res])), 3),
          ' edge err mean', round(float(np.mean([r[6] for r in res])), 1), 'px  p95', round(float(np.mean([r[7] for r in res])), 1), 'px')
    font = ImageFont.truetype('arial.ttf', 18)
    S = 2  # review zoom
    cw = max(r[3].shape[1] for r in res) * S + 12
    ch = max(r[3].shape[0] for r in res) * S + 8
    sheet = Image.new('RGB', (cw * len(res), ch * 2 + 30), (60, 60, 60))
    d = ImageDraw.Draw(sheet)
    for n, (i, o, c4, m4, canvas, iou, _, _) in enumerate(res):
        orig = o.resize((o.width * 4 * S, o.height * 4 * S), Image.NEAREST)
        bg = Image.new('RGBA', orig.size, (60, 60, 60, 255)); bg.alpha_composite(orig)
        sheet.paste(bg.convert('RGB'), (n * cw + 6, 30))
        dr = Image.fromarray(canvas, 'RGBA').resize((canvas.shape[1] * S, canvas.shape[0] * S), Image.LANCZOS)
        bg = Image.new('RGBA', dr.size, (60, 60, 60, 255)); bg.alpha_composite(dr)
        v = np.asarray(bg.convert('RGB')).copy()
        mz = cv2.resize(m4.astype(np.uint8), (dr.width, dr.height), interpolation=cv2.INTER_NEAREST)
        edge = cv2.morphologyEx(mz, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
        v[edge] = (255, 60, 60)
        sheet.paste(Image.fromarray(v), (n * cw + 6, 30 + ch))
        d.text((n * cw + 6, 6), f'{i}  IoU {iou:.2f}', fill=(255, 230, 120), font=font)
    sheet.save(os.path.join(a.out, 'review.png'))
    print(sheet.size)


if __name__ == '__main__':
    main()
