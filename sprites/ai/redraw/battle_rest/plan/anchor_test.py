"""Colour anchoring prototype on raw renders: sprite | as now (chroma k=0.7 + teacher offset) | chroma k=1, no offset |
chroma k=1 + low-frequency lightness.   python anchor_test.py <out.png> <group>:<f,f,...> ..."""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = r'<XENO_SPRITES>'
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ai_redraw import Hero  # noqa: E402
from color_local import blur_masked, local_match  # noqa: E402
from make_grids import frame_rgba  # noqa: E402

RES = os.path.join(ROOT, 'ai', 'redraw', 'battle_rest', 'res', 'v4')
OFF = (4.01, -1.59)


def load(h, m, name):
    o8 = np.asarray(frame_rgba(h, m['set'], m['frame']))
    H, W = o8.shape[:2]
    k = min(500 / H, 512 / W, 1.0)
    fp = os.path.join(RES, name + '.png')
    if k < 1.0:
        w2, h2 = int(W * k), int(H * k)
        box = ((512 - w2) // 2, 500 - h2, (512 - w2) // 2 + w2, 500)
        full = np.array(Image.open(fp).convert('RGB').crop(box).resize((W, H), Image.LANCZOS))
    else:
        x0 = (512 - W) // 2
        full = np.asarray(Image.open(fp).convert('RGB'))[500 - H:500, x0:x0 + W].copy()
    return o8, full


def anchor(ctrl, out, sil, sig_ab=12.0, sig_l=20.0, k_l=0.85):
    m = sil.astype(np.float32)
    lc = cv2.cvtColor(ctrl, cv2.COLOR_RGB2LAB).astype(np.float32)
    lo = cv2.cvtColor(out, cv2.COLOR_RGB2LAB).astype(np.float32)
    res = lo.copy()
    d_ab = blur_masked(lc[..., 1:], m, sig_ab) - blur_masked(lo[..., 1:], m, sig_ab)
    den = np.maximum(cv2.GaussianBlur(m, (0, 0), sig_l), 1e-3)
    d_l = (cv2.GaussianBlur((lc[..., 0] - lo[..., 0]) * m, (0, 0), sig_l) / den)[..., None]
    res[..., 1:] = np.clip(lo[..., 1:] + d_ab, 0, 255)
    res[..., :1] = np.clip(lo[..., :1] + k_l * d_l, 0, 255)
    return cv2.cvtColor(res.astype(np.uint8), cv2.COLOR_LAB2RGB)


def show(rgb, sil):
    a = np.dstack([rgb, np.where(sil, 255, 0).astype(np.uint8)])
    im = Image.fromarray(a, 'RGBA')
    return im.resize((im.width // 2, im.height // 2), Image.LANCZOS)


def main():
    out = sys.argv[1]
    meta = json.load(open(os.path.join(ROOT, 'ai', 'redraw', 'battle_rest', 'meta.json')))
    rows = []
    for spec in sys.argv[2:]:
        g, fl = spec.split(':')
        h = None
        for f in fl.split(','):
            name = next(n for n, m in meta.items() if m['group'] == g and m['frame'] == int(f))
            m = meta[name]
            h = h or Hero(os.path.join(ROOT, m['hero_dir']))
            o8, full = load(h, m, name)
            sil = o8[..., 3] > 127
            ctrl = o8[..., :3].copy()
            ctrl[~sil] = (255, 0, 255)
            oc = full.copy()
            oc[~sil] = (255, 0, 255)
            now = local_match(ctrl, oc, OFF)
            k1 = local_match(ctrl, oc, (0.0, 0.0), k=1.0)
            full_a = anchor(o8[..., :3], full, sil)
            rows.append((f'{g[2:8]}:{f}', [show(o8[..., :3], sil), show(now, sil), show(k1, sil), show(full_a, sil)]))
    W = max(sum(i.width + 6 for i in r[1]) for r in rows) + 8
    cols = max(1, 1990 // W)
    pos, x, y, rh = [], 4, 4, 0
    for k, (lab, ims) in enumerate(rows):
        if k and k % cols == 0:
            x, y, rh = 4, y + rh + 16, 0
        pos.append((lab, ims, x, y))
        x += W
        rh = max(rh, max(i.height for i in ims))
    c = Image.new('RGB', (cols * W + 8, y + rh + 20), (150, 170, 90))
    d = ImageDraw.Draw(c)
    for lab, ims, x, y in pos:
        d.text((x, y), lab + '  sprite | now | chroma k=1 | chroma+L', fill=(255, 255, 0))
        for im in ims:
            c.paste(im, (x, y + 12), im)
            x += im.width + 6
    c.save(out)
    print(out, c.size)


if __name__ == '__main__':
    main()
