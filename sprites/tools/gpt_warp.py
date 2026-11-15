"""Warp ChatGPT redraws onto the original sprite silhouettes (bbox fit + dense optical flow), report IoU, save review."""
import argparse
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FR = 'extracted/disc1/fei/frames/{}_{:03d}.png'


def fg_mask(a):
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    return ~((r > 180) & (b > 180) & (g < 110))


def bbox(m):
    ys, xs = np.where(m)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def feat(rgb, m, s):
    """Feature image for flow: blurred luminance inside the figure, mid-grey outside, plus a soft silhouette."""
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    g = np.where(m, g, 255.0)
    g = cv2.GaussianBlur(g, (0, 0), s)
    soft = cv2.GaussianBlur(m.astype(np.float32) * 255, (0, 0), s)
    return np.clip(0.5 * g + 0.5 * (255 - soft), 0, 255).astype(np.uint8)


def warp_one(draw, dm, orig, om, k):
    h, w = om.shape
    flow = None
    for s in (k * 2.0, k * 1.0, k * 0.5):
        f0, f1 = feat(orig, om, s), feat(draw if flow is None else cur, dm if flow is None else cm, s)
        fl = cv2.calcOpticalFlowFarneback(f0, f1, None, 0.5, 4, int(k * 4) | 1, 5, 7, 1.5, 0)
        flow = fl if flow is None else flow + cv2.remap(fl, *np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32)), cv2.INTER_LINEAR) * 0 + fl
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        mx, my = gx + flow[..., 0], gy + flow[..., 1]
        cur = cv2.remap(draw, mx, my, cv2.INTER_LINEAR, borderValue=(255, 0, 255))
        cm = cv2.remap(dm.astype(np.uint8), mx, my, cv2.INTER_NEAREST, borderValue=0) > 0
        flow_total = flow
        draw_src, dm_src = draw, dm
        # next level starts from the original drawing with accumulated flow
        draw, dm = draw_src, dm_src
    return cur, cm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--img', required=True)
    ap.add_argument('--set', default='427_0')
    ap.add_argument('--frames', required=True)
    ap.add_argument('--k', type=int, default=6)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    lo, hi = map(int, a.frames.split('-'))
    gpt = np.asarray(Image.open(a.img).convert('RGB'))
    gm = fg_mask(gpt)
    os.makedirs(a.out, exist_ok=True)
    cols = []
    for j, i in enumerate(range(lo, hi + 1)):
        o = Image.open(FR.format(a.set, i)).convert('RGBA')
        ok = np.asarray(o.resize((o.width * a.k, o.height * a.k), Image.NEAREST))
        om = ok[..., 3] > 0
        orig = ok[..., :3].copy()
        orig[~om] = (255, 0, 255)
        cell = gm.copy()
        cell[:, :(j % 4) * 384] = False; cell[:, (j % 4 + 1) * 384:] = False
        cell[:(j // 4) * 512] = False; cell[(j // 4 + 1) * 512:] = False
        gx0, gy0, gx1, gy1 = bbox(cell)
        ox0, oy0, ox1, oy1 = bbox(om)
        W, H = ox1 - ox0, oy1 - oy0
        draw = np.zeros_like(orig); draw[:] = (255, 0, 255)
        crop = gpt[gy0:gy1, gx0:gx1].copy()
        crop[~cell[gy0:gy1, gx0:gx1]] = (255, 0, 255)
        draw[oy0:oy1, ox0:ox1] = cv2.resize(crop, (W, H), interpolation=cv2.INTER_AREA)
        dm = fg_mask(draw)
        b_iou = iou(dm, om)
        wd, wm = warp_one(draw, dm, orig, om, a.k)
        w_iou = iou(wm, om)
        print(f'{i:3d}  bbox-fit IoU {b_iou:.2f}  -> warped {w_iou:.2f}')
        Image.fromarray(wd).save(os.path.join(a.out, f'{a.set}_{i:03d}_warp.png'))
        cols.append((i, orig, draw, wd, om))
    # review: original | bbox fit + original contour | warped + contour
    font = ImageFont.truetype('arial.ttf', 18)
    cw = max(c[1].shape[1] for c in cols) + 12
    ch = max(c[1].shape[0] for c in cols) + 8
    sheet = Image.new('RGB', (cw * len(cols), ch * 3 + 30), (60, 60, 60))
    d = ImageDraw.Draw(sheet)
    for n, (i, orig, draw, wd, om) in enumerate(cols):
        edge = cv2.morphologyEx(om.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
        for r, img in enumerate((orig, draw, wd)):
            v = img.copy()
            v[(v == (255, 0, 255)).all(-1)] = (60, 60, 60)
            if r:
                v[edge] = (255, 40, 40)
            sheet.paste(Image.fromarray(v), (n * cw + 6, 30 + r * ch))
        d.text((n * cw + 6, 6), str(i), fill=(255, 230, 120), font=font)
    sheet.save(os.path.join(a.out, 'review.png'))
    print(sheet.size)


if __name__ == '__main__':
    main()
