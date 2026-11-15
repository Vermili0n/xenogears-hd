"""Diagnostic replacement textures: every native texel becomes a 4x4 checker cell in the part's own hue, with a white
marker in the top-left HD pixel of each cell and a black 1-HD-pixel frame around the part. In a screenshot this shows
where each part lands, whether rows/columns are dropped or doubled, and whether the HD texture is sampled at full res.

  python diag_parts.py --names ai/fei_pilotv3/parts --hero-dir extracted/disc1_full/fei --out ai/fei_test_diag
Writes <out>/<name>.png and <out>/legend.json {name: [r, g, b]}.
"""
import argparse
import colorsys
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402

S = int(os.environ.get("DIAG_SCALE", "4"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--names', required=True, help='folder whose file names (<block>-<clut>.png) are used')
    ap.add_argument('--hero-dir', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    h = Hero(os.path.join(ROOT, a.hero_dir))
    os.makedirs(a.out, exist_ok=True)
    legend = {}
    for f in sorted(os.listdir(os.path.join(ROOT, a.names) if not os.path.isabs(a.names) else a.names)):
        b, pal = f[:-4].split('-')
        nat = np.asarray(h.part(b, pal).convert('RGBA'))
        H, W = nat.shape[:2]
        hue = int(hashlib.md5(b.encode()).hexdigest()[:4], 16) / 65535
        c1 = np.array(colorsys.hsv_to_rgb(hue, 0.85, 0.95)) * 255
        c2 = c1 * 0.55
        img = np.zeros((H * S, W * S, 4), np.uint8)
        for y in range(H):
            for x in range(W):
                cell = c1 if (x + y) % 2 == 0 else c2
                img[y * S:(y + 1) * S, x * S:(x + 1) * S, :3] = cell
                img[y * S, x * S, :3] = 255
        img[0, :, :3] = img[-1, :, :3] = 0
        img[:, 0, :3] = img[:, -1, :3] = 0
        img[..., 3] = np.where(np.kron(nat[..., 3] > 0, np.ones((S, S), bool)), 128, 0)
        Image.fromarray(img, 'RGBA').save(os.path.join(a.out, f))
        legend[b] = [int(v) for v in c1]
    json.dump(legend, open(os.path.join(a.out, 'legend.json'), 'w'))
    print('diagnostic parts', len(legend))


if __name__ == '__main__':
    main()
