"""ebsynth propagation v2: material (palette-index) guide + all keyframes merged into one source canvas, optional
work scale. Same leave-k-out evaluation as ebs_test.py (ground truth = Gemini's own redraw of held-out frames).

  python ebs_test2.py --grid <gemini grid.png> --name g16_walk --keys 25,29 --frames 25-32 [--scale 4] [--patch 7]
"""
import argparse
import json
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import xbr4  # noqa: E402
from ebs_test import CELL, EBS, MAG, edges, load_cells  # noqa: E402

CODES = np.array([(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180),
                  (70, 240, 240), (240, 50, 230), (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255),
                  (170, 110, 40), (255, 250, 200), (128, 0, 0), (170, 255, 195), (128, 128, 0), (255, 215, 180),
                  (0, 0, 128), (128, 128, 128)], np.uint8)


def material_maps(meta, frames):
    """Palette-colour -> distinct code colour, xBR-upscaled to the 8x cell like the other guides."""
    sprites = {c['frame']: (c, Image.open(os.path.join(ROOT, 'extracted', 'disc1', 'fei', 'frames',
                                                        f"{c['set']}_{c['frame']:03d}.png")).convert('RGBA'))
               for c in meta if c['frame'] in frames}
    cols = sorted({tuple(p[:3]) for _, im in sprites.values() for p in np.asarray(im).reshape(-1, 4) if p[3] > 0})
    lut = {c: CODES[i % len(CODES)] for i, c in enumerate(cols)}
    out = {}
    for f, (c, im) in sprites.items():
        a = np.asarray(im)
        code = np.zeros(a.shape[:2] + (4,), np.uint8)
        for (r, g, b), v in lut.items():
            m = (a[..., 0] == r) & (a[..., 1] == g) & (a[..., 2] == b) & (a[..., 3] > 0)
            code[m, :3] = v
            code[m, 3] = 255
        c4, m4 = xbr4(Image.fromarray(code, 'RGBA'))
        c8 = np.asarray(Image.fromarray(c4).resize((c['w'], c['h']), Image.NEAREST))
        m8 = np.asarray(Image.fromarray((m4 * 255).astype(np.uint8)).resize((c['w'], c['h']), Image.NEAREST)) > 127
        cell = np.zeros((CELL, CELL, 3), np.uint8)
        x, y = c['x'] - c['cx'], c['y'] - c['cy']
        cell[y:y + c['h'], x:x + c['w']][m8] = c8[m8]
        out[f] = cell
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--grid', required=True)
    ap.add_argument('--name', required=True)
    ap.add_argument('--keys', required=True)
    ap.add_argument('--frames', required=True)
    ap.add_argument('--scale', type=int, default=8, help='work scale over native (8 = grid cells, 4 = final)')
    ap.add_argument('--patch', type=int, default=7)
    ap.add_argument('--uniformity', type=float, default=3500)
    ap.add_argument('--wmat', type=float, default=3.0)
    ap.add_argument('--wcolor', type=float, default=1.0)
    ap.add_argument('--wedge', type=float, default=0.5)
    ap.add_argument('--tag', default='v2')
    ap.add_argument('--out', default=os.path.join(ROOT, 'ai', 'ebs_test'))
    a = ap.parse_args()
    meta = json.load(open(os.path.join(ROOT, 'ai', 'or_test', 'in', 'grids.json')))[a.name]
    keys = [int(k) for k in a.keys.split(',')]
    lo, hi = map(int, a.frames.split('-'))
    targets = list(range(lo, hi + 1))
    cells = load_cells(a.grid, meta)
    mats = material_maps(meta, set(targets) | set(keys))
    k = a.scale / 8
    S = int(CELL * k)

    def rs(img, nearest=False):
        return np.asarray(Image.fromarray(img).resize((S, S), Image.NEAREST if nearest else Image.LANCZOS))

    w = os.path.join(a.out, 'tmp2')
    os.makedirs(w, exist_ok=True)

    def save(img, name):
        p = os.path.join(w, name)
        Image.fromarray(img).save(p)
        return p

    # source canvas = all keyframes side by side
    src_style = np.concatenate([rs(cells[f][2]) for f in keys], 1)
    src_col = np.concatenate([rs(cells[f][0]) for f in keys], 1)
    src_mat = np.concatenate([rs(mats[f], True) for f in keys], 1)
    src_edge = np.concatenate([rs(edges(cells[f][0], cells[f][1])) for f in keys], 1)
    res = {}
    for t in targets:
        B, Bm, gt = cells[t]
        if t in keys:
            res[t] = gt
            continue
        out = os.path.join(w, f'out_{a.tag}_{t}.png')
        cmd = [EBS, '-style', save(src_style, 'src_style.png'),
               '-guide', save(src_mat, 'src_mat.png'), save(rs(mats[t], True), f'tm_{t}.png'), '-weight', str(a.wmat),
               '-guide', save(src_col, 'src_col.png'), save(rs(B), f'tc_{t}.png'), '-weight', str(a.wcolor),
               '-guide', save(src_edge, 'src_edge.png'), save(rs(edges(B, Bm)), f'te_{t}.png'), '-weight', str(a.wedge),
               '-patchsize', str(a.patch), '-uniformity', str(a.uniformity), '-output', out]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        r = np.asarray(Image.open(out).convert('RGB').resize((CELL, CELL), Image.LANCZOS)).copy()
        r[~Bm] = MAG
        res[t] = r
    font = ImageFont.truetype('arial.ttf', 18)
    T = 256
    sheet = Image.new('RGB', (len(targets) * (T + 4) + 4, 3 * (T + 4) + 30), (60, 60, 60))
    d = ImageDraw.Draw(sheet)
    scores = []
    for j, t in enumerate(targets):
        B, Bm, gt = cells[t]
        bo = cv2.GaussianBlur(gt.astype(np.float32), (0, 0), 2)
        br = cv2.GaussianBlur(res[t].astype(np.float32), (0, 0), 2)
        diff = float(np.abs(bo - br).sum(-1)[Bm].mean())
        if t not in keys:
            scores.append(diff)
        for r_, img in enumerate((B, gt, res[t])):
            v = img.copy(); v[(v == MAG).all(-1)] = (60, 60, 60)
            sheet.paste(Image.fromarray(v).resize((T, T), Image.LANCZOS), (4 + j * (T + 4), 30 + r_ * (T + 4)))
        d.text((6 + j * (T + 4), 6), f"{t}{' KEY' if t in keys else ''}  d={diff:.0f}", fill=(255, 230, 120), font=font)
        Image.fromarray(res[t]).save(os.path.join(w, f'final_{a.tag}_{t}.png'))
    tag = f"{a.name}_{a.tag}_k{'-'.join(map(str, keys))}"
    sheet.save(os.path.join(a.out, f'sheet_{tag}.png'))
    print(tag, 'mean colour diff vs Gemini on held-out frames:', round(float(np.mean(scores)), 1))


if __name__ == '__main__':
    main()
