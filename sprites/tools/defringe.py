"""Remove magenta fringe (background bleed from the model's #FF00FF) near the silhouette edge of finished redraws.

  python defringe.py --hero-dir extracted/npc/<id> --work ai/npc_<id>_prod/work [--set npc]
Pixels within --band px (4x) of the original silhouette edge whose colour leans to magenta are inpainted from the inside.
"""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_redraw import Hero, xbr4  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero-dir', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--set', default='npc')
    ap.add_argument('--band', type=int, default=8)
    a = ap.parse_args()
    h = Hero(a.hero_dir)
    n = 0
    for f in sorted(os.listdir(a.work)):
        if not f.endswith('_red.png') or not f.startswith(a.set + '_'):
            continue
        fi = int(f[len(a.set) + 1:].split('_')[0])
        fr, _ = h.assemble(h.placements(a.set, fi))
        _, m4 = xbr4(fr)
        p = os.path.join(a.work, f)
        img = np.asarray(Image.open(p).convert('RGB')).copy()
        if img.shape[:2] != m4.shape:
            img = np.asarray(Image.fromarray(img).resize((m4.shape[1], m4.shape[0]), Image.LANCZOS)).copy()
        inner = cv2.erode(m4.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=a.band) > 0
        band = m4 & ~inner
        r, g, b = (img[..., k].astype(int) for k in range(3))
        pink = band & (r - g > 25) & (b - g > 25)
        if pink.any():
            hole = (pink | ~m4).astype(np.uint8) * 255  # outside counts as hole too, so only interior colours spread
            fixed = cv2.inpaint(img, hole, 4, cv2.INPAINT_TELEA)
            img[pink] = fixed[pink]
            Image.fromarray(img).save(p)
            n += 1
    print(os.path.basename(a.hero_dir), 'defringed', n, 'frames')


if __name__ == '__main__':
    main()
