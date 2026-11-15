"""Turn redrawn 2x2 grids (from an image model) into 4x per-frame redraws for `batch_redraw.py slice`.

  python grid_to_red.py --hero fei --out-tag _gem --grid ai/or_test/out/x.png:427_0:57,58,59,60 [--grid ...]

Each cell's figure is fitted onto the original frame with scale + shift only (no warping), magenta fringe and
uncovered pixels are inpainted from the drawing, and the result is saved at 4x as ai/<hero><tag>/work/<set>_<fi>_red.png.
The silhouette itself comes from the original at slice time.
"""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero, xbr4  # noqa: E402
from gpt_rigid import best_fit, chamfer  # noqa: E402
from or_score import fg_mask  # noqa: E402

CELL = 512


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', default='fei')
    ap.add_argument('--out-tag', required=True)
    ap.add_argument('--grid', action='append', required=True, help='image.png:set:f1,f2,f3,f4 (cells left-right, top-bottom)')
    a = ap.parse_args()
    hobj = Hero(os.path.join(ROOT, 'extracted', 'disc1_full', a.hero))
    work = os.path.join(ROOT, 'ai', a.hero + a.out_tag, 'work')
    os.makedirs(work, exist_ok=True)
    for g in a.grid:
        path, s, ids = g.rsplit(':', 2)
        im = Image.open(path).convert('RGB')
        if im.size != (2 * CELL, 2 * CELL):
            im = im.resize((2 * CELL, 2 * CELL), Image.LANCZOS)
        rgb = np.asarray(im)
        fm, _ = fg_mask(rgb)
        for j, fi in enumerate(map(int, ids.split(','))):
            cx, cy = (j % 2) * CELL, (j // 2) * CELL
            dm = fm[cy:cy + CELL, cx:cx + CELL]
            drgb = rgb[cy:cy + CELL, cx:cx + CELL]
            n, lab, st, _ = cv2.connectedComponentsWithStats(dm.astype(np.uint8), 8)
            big = st[1:, cv2.CC_STAT_AREA].max()
            dm = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 0.05 * big])
            ys, xs = np.where(dm)
            x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
            frame, _ = hobj.assemble(hobj.placements(s, fi))
            c4, m4 = xbr4(frame)
            oys = np.where(m4)[0]
            s0 = (oys.max() + 1 - oys.min()) / (y1 - y0)
            iou, (w, h, x, y) = best_fit(drgb[y0:y1, x0:x1], dm[y0:y1, x0:x1], m4, s0)
            rgba = cv2.resize(np.dstack([drgb[y0:y1, x0:x1], dm[y0:y1, x0:x1].astype(np.uint8) * 255]), (w, h),
                              interpolation=cv2.INTER_AREA)
            H, W = m4.shape
            fit = np.zeros((H, W, 4), np.uint8)
            sx0, sy0, dx0, dy0 = max(0, -x), max(0, -y), max(0, x), max(0, y)
            ww, hh = min(w - sx0, W - dx0), min(h - sy0, H - dy0)
            fit[dy0:dy0 + hh, dx0:dx0 + ww] = rgba[sy0:sy0 + hh, sx0:sx0 + ww]
            col = fit[..., :3].copy()
            r, gg, b = (col[..., k].astype(int) for k in range(3))
            fringe = (r - gg > 50) & (b - gg > 50)          # magenta blended into the anti-aliased edge
            hole = (fit[..., 3] < 200) | fringe
            col = cv2.inpaint(col, hole.astype(np.uint8) * 255, 3, cv2.INPAINT_TELEA)
            Image.fromarray(col).save(os.path.join(work, f'{s}_{fi:03d}_red.png'))
            cm, c95 = chamfer(fit[..., 3] > 127, m4)
            print(f'{s}:{fi}  IoU {iou:.3f}  contour p95 {c95:.1f}px (4x)  uncovered {float((m4 & (fit[..., 3] < 128)).mean() / m4.mean()):.1%}')


if __name__ == '__main__':
    main()
