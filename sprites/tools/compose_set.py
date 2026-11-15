"""Compose LoRA renders of a set into slicer input: full frame (8x) + 16x head pass pasted inside the head part,
local colour transfer from the sprite, saved as <work>/<set>_<fi>_red.png (4x RGB, what batch_redraw slice reads).

  python compose_set.py --render ai/render_pilot --res pod/report/pilot/v3 --work ai/fei_pilotv3/work [--name fei]
--res: folder with <name>.png renders (infer_pod.py output). Head pass is used only when it agrees with the
full-frame head at low frequency (no face drawn onto a back view) - same gate as the evaluation.
Writes <work>/../compose.json with the per-frame decisions.
"""
import argparse
import json
import os
import sys
from collections import Counter

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from color_local import anchor_match, local_match, teacher_offsets  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from make_pairs_v3 import HEAD_N  # noqa: E402

GATE = 30.0  # catastrophic mismatch only: on test3 the 12-24 range did not predict which head is better


def consistency(a, b, mask, sigma=12):
    la = cv2.GaussianBlur(cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32), (0, 0), sigma)
    lb = cv2.GaussianBlur(cv2.cvtColor(b, cv2.COLOR_RGB2LAB).astype(np.float32), (0, 0), sigma)
    return float(np.linalg.norm(la - lb, axis=-1)[mask].mean()) if mask.any() else 999.0


def magentaish(rgb):
    r, g, b = (rgb[..., k].astype(int) for k in range(3))
    return (r - g > 60) & (b - g > 60) & (abs(r - b) < 90)


def purpleish(rgb):
    """Weak magenta: anti-aliased blend of a figure edge with the magenta background (e.g. dark purple)."""
    r, g, b = (rgb[..., k].astype(int) for k in range(3))
    return (r - g > 18) & (b - g > 18) & (b > g + 0.6 * (r - g))


def defringe(rgb, sil, ctrl, band=None):
    """Magenta background inside the silhouette (the render's figure is thinner than the sprite, or left a gap where
    the sprite is solid): pixels that are magenta in the render but not in the sprite are inpainted from neighbours.
    Near the silhouette edge (`band` px) weak, anti-aliased magenta blends are removed too, unless the sprite itself
    has purple there (purple clothing stays)."""
    ctrl_mag = cv2.dilate(magentaish(ctrl).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    hole = sil & magentaish(rgb) & ~ctrl_mag
    if band:
        edge = sil & ~(cv2.erode(sil.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=band) > 0)
        ctrl_pur = cv2.dilate(purpleish(ctrl).astype(np.uint8), np.ones((3, 3), np.uint8), iterations=band) > 0
        hole |= edge & purpleish(rgb) & ~ctrl_pur
    if not hole.any():
        return rgb, 0
    hole = (cv2.dilate(hole.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & sil
    # the background next to an edge hole is magenta too: mark it unknown as well, so only figure colours fill the hole
    near = cv2.dilate(hole.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=10) > 0
    mask = hole | (near & ~sil)
    out = cv2.inpaint(np.ascontiguousarray(rgb), mask.astype(np.uint8) * 255, 3, cv2.INPAINT_TELEA)
    res = rgb.copy()
    res[hole] = out[hole]
    return res, int(hole.sum())


def head_group_mask(h, setkey, fi, hx, hy, share=0.6):
    """8x mask (frame coords) of every part that lies mostly (>= share of its texels) inside the head window
    [hx, hx + HEAD_N) x [hy, hy + HEAD_N): the whole head (hair, face, ...), not only the topmost texture.
    A face split over two textures must come from the same drawing, otherwise the eyes break at the seam."""
    places = h.placements(setkey, fi)
    img, (ox, oy) = h.assemble(places)
    m = np.zeros((img.height, img.width), np.uint8)
    for p in places:
        part = h.part(p['block'], p['pal'])
        if p['flipx']:
            part = part.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            part = part.transpose(Image.FLIP_TOP_BOTTOM)
        a = (np.asarray(part)[..., 3] > 0).astype(np.uint8)
        x, y = p['x'] - ox, p['y'] - oy
        ys, xs = np.nonzero(a)
        if not len(xs):
            continue
        inside = ((xs + x >= hx) & (xs + x < hx + HEAD_N) & (ys + y >= hy) & (ys + y < hy + HEAD_N)).mean()
        if inside >= share:
            m[y:y + a.shape[0], x:x + a.shape[1]] = np.maximum(m[y:y + a.shape[0], x:x + a.shape[1]], a)
    return cv2.resize(m, (img.width * 8, img.height * 8), interpolation=cv2.INTER_NEAREST) > 0


def window_weight(n, ramp=12):
    """n x n weight: 1 inside, falling to 0 over `ramp` px at the window border (soft only where the window cuts a part)."""
    r = np.minimum(np.arange(n), np.arange(n)[::-1]).astype(np.float32)
    w = np.clip(r / ramp, 0, 1)
    return np.minimum.outer(w, w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--render', required=True)
    ap.add_argument('--res', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--name', default='')
    ap.add_argument('--offset-key', default='', help='character key for the teacher colour offset (e.g. fei); "" = global')
    ap.add_argument('--no-color', action='store_true')
    ap.add_argument('--color-mode', default='local', choices=['local', 'anchor'],
                    help='anchor: colours tied to the sprite in full (sets drawn without a board)')
    ap.add_argument('--no-head', action='store_true')
    ap.add_argument('--out-scale', type=int, default=4, choices=[4, 8], help='scale of the written <set>_<fi>_red.png')
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    meta = json.load(open(os.path.join(a.render, 'meta.json')))
    offs = {} if a.no_color else teacher_offsets(os.path.join(ROOT, 'ai', 'pairs_v3'), lambda n: (
        n.split('__')[0].split('_')[1] if n.startswith('h_') else n.split('__')[0]))
    off = offs.get(a.offset_key, offs.get('', [0.0, 0.0]))
    heroes, log = {}, {}
    for name, m in sorted(meta.items()):
        if a.name and not name.startswith(a.name + '__'):
            continue
        fp = os.path.join(a.res, name + '.png')
        if not os.path.exists(fp):
            continue
        h = heroes.setdefault(m['hero_dir'], Hero(os.path.join(ROOT, m['hero_dir'])))
        o8 = np.asarray(frame_rgba(h, m['set'], m['frame']))
        H, W = o8.shape[:2]
        sil = o8[..., 3] > 127
        k = min(500 / H, 512 / W, 1.0)
        if k < 1.0:  # tall sprites were shrunk into the canvas: scale the render back
            w2, h2 = int(W * k), int(H * k)
            box = ((512 - w2) // 2, 500 - h2, (512 - w2) // 2 + w2, 500)
            full = np.array(Image.open(fp).convert('RGB').crop(box).resize((W, H), Image.LANCZOS))
        else:
            x0 = (512 - W) // 2
            full = np.asarray(Image.open(fp).convert('RGB'))[500 - H:500, x0:x0 + W].copy()
        rec = {'head': 'none'}
        hp = os.path.join(a.res, name + '__head.png')
        if not a.no_head and m.get('head_job') and os.path.exists(hp):
            hx, hy = m['head']
            n8 = HEAD_N * 8
            head8 = np.asarray(Image.open(hp).convert('RGB').resize((n8, n8), Image.LANCZOS))
            pm = head_group_mask(h, m['set'], m['frame'], hx, hy) & sil
            ww8 = window_weight(n8)
            X0, Y0 = hx * 8, hy * 8
            sx0, sy0, dx0, dy0 = max(0, -X0), max(0, -Y0), max(0, X0), max(0, Y0)
            ww, hh = min(n8 - sx0, W - dx0), min(n8 - sy0, H - dy0)
            if ww > 0 and hh > 0:
                sub_full = full[dy0:dy0 + hh, dx0:dx0 + ww]
                sub_head = head8[sy0:sy0 + hh, sx0:sx0 + ww]
                sub_m = pm[dy0:dy0 + hh, dx0:dx0 + ww]
                agree = consistency(sub_head, sub_full, sub_m)
                rec['agree'] = round(agree, 2)
                if agree < GATE:
                    # hard at part borders (they are separate textures), soft only where the window cuts a part
                    alpha = sub_m * ww8[sy0:sy0 + hh, sx0:sx0 + ww]
                    full[dy0:dy0 + hh, dx0:dx0 + ww] = (sub_head * alpha[..., None] + sub_full * (1 - alpha[..., None])).astype(np.uint8)
                    rec['head'] = 'pass'
                else:
                    rec['head'] = 'rejected'
        full, rec['defringed'] = defringe(full, sil, o8[..., :3], band=12)
        if a.color_mode == 'anchor':
            full = anchor_match(np.ascontiguousarray(o8[..., :3]), full, sil)
        elif not a.no_color:
            ctrl = o8[..., :3].copy()
            ctrl[~sil] = (255, 0, 255)
            outc = full.copy()
            outc[~sil] = (255, 0, 255)
            full = local_match(ctrl, outc, off)
        # extend the figure's colours a few px past the silhouette so the 8x -> 4x average never mixes in background
        band = (cv2.dilate(sil.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=16) > 0) & ~sil
        full = cv2.inpaint(np.ascontiguousarray(full), band.astype(np.uint8) * 255, 3, cv2.INPAINT_TELEA)
        red4 = full if a.out_scale == 8 else cv2.resize(full, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
        for nm in [name] + m['dups']:
            s, fi = nm.split('__')[1].rsplit('_', 1)
            Image.fromarray(red4).save(os.path.join(a.work, f'{s}_{int(fi):03d}_red.png'))
        log[name] = rec
    json.dump(log, open(os.path.join(os.path.dirname(a.work.rstrip('/\\')), 'compose.json'), 'w'), indent=0)
    print('composed', len(log), Counter(r['head'] for r in log.values()))


if __name__ == '__main__':
    main()
