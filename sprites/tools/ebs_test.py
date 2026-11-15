"""Leave-k-out test of ebsynth propagation: Gemini HD keyframes -> other frames of the same animation, guided by the
original sprites. Ground truth = Gemini's own redraw of the held-out frames.

  python ebs_test.py --grid ai/or_test/out/google_gemini-3-pro-image__g16_walk_4k.png --name g16_walk --keys 25,29 --frames 25-32
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
from gpt_rigid import best_fit  # noqa: E402
from or_score import fg_mask  # noqa: E402

CELL = 512
EBS = os.path.join(HERE, 'ebsynth_src', 'ebsynth-master', 'bin', 'ebsynth.exe')
MAG = np.array([255, 0, 255], np.uint8)


def load_cells(grid_png, meta):
    """-> {frame: (orig_rgb 512x512, orig_mask, fitted_rgb, fitted_mask)} in 8x cell coordinates."""
    cols, rows = meta[0].get('cols', 2), meta[0].get('rows', 2)
    im = Image.open(grid_png).convert('RGB')
    if im.size != (cols * CELL, rows * CELL):
        im = im.resize((cols * CELL, rows * CELL), Image.LANCZOS)
    rgb = np.asarray(im)
    fm, _ = fg_mask(rgb)
    out = {}
    for c in meta:
        o = Image.open(os.path.join(ROOT, 'extracted', 'disc1', 'fei', 'frames', f"{c['set']}_{c['frame']:03d}.png")).convert('RGBA')
        c4, m4 = xbr4(o)
        rgb8 = np.asarray(Image.fromarray(c4).resize((c['w'], c['h']), Image.LANCZOS))
        m8 = np.asarray(Image.fromarray((m4 * 255).astype(np.uint8)).resize((c['w'], c['h']), Image.LANCZOS)) > 127
        x, y = c['x'] - c['cx'], c['y'] - c['cy']
        om = np.zeros((CELL, CELL), bool)
        orgb = np.zeros((CELL, CELL, 3), np.uint8); orgb[:] = MAG
        om[y:y + c['h'], x:x + c['w']] = m8
        orgb[y:y + c['h'], x:x + c['w']][m8] = rgb8[m8]
        dm = fm[c['cy']:c['cy'] + CELL, c['cx']:c['cx'] + CELL]
        drgb = rgb[c['cy']:c['cy'] + CELL, c['cx']:c['cx'] + CELL]
        n, lab, st, _ = cv2.connectedComponentsWithStats(dm.astype(np.uint8), 8)
        big = st[1:, cv2.CC_STAT_AREA].max()
        dm = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 0.05 * big])
        ys, xs = np.where(dm)
        gx0, gy0, gx1, gy1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        oys = np.where(om)[0]
        s0 = (oys.max() + 1 - oys.min()) / (gy1 - gy0)
        _, (w, h, fx, fy) = best_fit(drgb[gy0:gy1, gx0:gx1], dm[gy0:gy1, gx0:gx1], om, s0)
        rgba = cv2.resize(np.dstack([drgb[gy0:gy1, gx0:gx1], dm[gy0:gy1, gx0:gx1].astype(np.uint8) * 255]), (w, h),
                          interpolation=cv2.INTER_AREA)
        fit = np.zeros((CELL, CELL, 4), np.uint8)
        sx0, sy0, dx0, dy0 = max(0, -fx), max(0, -fy), max(0, fx), max(0, fy)
        ww, hh = min(w - sx0, CELL - dx0), min(h - sy0, CELL - dy0)
        fit[dy0:dy0 + hh, dx0:dx0 + ww] = rgba[sy0:sy0 + hh, sx0:sx0 + ww]
        col = fit[..., :3].copy()
        r, g, b = (col[..., k].astype(int) for k in range(3))
        hole = (fit[..., 3] < 200) | ((r - g > 50) & (b - g > 50))
        col = cv2.inpaint(col, hole.astype(np.uint8) * 255, 3, cv2.INPAINT_TELEA)
        col[~om] = MAG
        out[c['frame']] = (orgb, om, col)
    return out


def edges(rgb, om):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    e = cv2.Canny(g, 40, 120)
    e = cv2.GaussianBlur(e.astype(np.float32), (0, 0), 3)
    e = (255 * e / max(1, e.max())).astype(np.uint8)
    return np.dstack([e] * 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--grid', required=True)
    ap.add_argument('--name', required=True, help='grid name in ai/or_test/in/grids.json')
    ap.add_argument('--keys', required=True)
    ap.add_argument('--frames', required=True)
    ap.add_argument('--wcolor', type=float, default=2.0)
    ap.add_argument('--wedge', type=float, default=1.0)
    ap.add_argument('--out', default=os.path.join(ROOT, 'ai', 'ebs_test'))
    a = ap.parse_args()
    meta = json.load(open(os.path.join(ROOT, 'ai', 'or_test', 'in', 'grids.json')))[a.name]
    cells = load_cells(a.grid, meta)
    keys = [int(k) for k in a.keys.split(',')]
    lo, hi = map(int, a.frames.split('-'))
    targets = [f for f in range(lo, hi + 1)]
    os.makedirs(a.out, exist_ok=True)
    w = os.path.join(a.out, 'tmp')
    os.makedirs(w, exist_ok=True)

    def save(img, name):
        p = os.path.join(w, name)
        Image.fromarray(img).save(p)
        return p

    res = {}
    for t in targets:
        if t in keys:
            res[t] = cells[t][2]
            continue
        k = min(keys, key=lambda k: (min(abs(t - k), 8 - abs(t - k)), k))  # nearest keyframe in the cycle
        A, Am, Ap = cells[k]
        B, Bm, _ = cells[t]
        out = os.path.join(w, f'out_{t}.png')
        cmd = [EBS, '-style', save(Ap, f'Ap_{k}.png'),
               '-guide', save(A, f'A_{k}.png'), save(B, f'B_{t}.png'), '-weight', str(a.wcolor),
               '-guide', save(edges(A, Am), f'Ae_{k}.png'), save(edges(B, Bm), f'Be_{t}.png'), '-weight', str(a.wedge),
               '-output', out]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        r = np.asarray(Image.open(out).convert('RGB')).copy()
        r[~Bm] = MAG
        res[t] = r
    # metrics vs Gemini ground truth (blurred colour difference inside the silhouette) + sheet
    font = ImageFont.truetype('arial.ttf', 18)
    S = 256
    sheet = Image.new('RGB', (len(targets) * (S + 4) + 4, 3 * (S + 4) + 30), (60, 60, 60))
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
            sheet.paste(Image.fromarray(v).resize((S, S), Image.LANCZOS), (4 + j * (S + 4), 30 + r_ * (S + 4)))
        d.text((6 + j * (S + 4), 6), f"{t}{' KEY' if t in keys else ''}  d={diff:.0f}", fill=(255, 230, 120), font=font)
    tag = f"{a.name}_k{'-'.join(map(str, keys))}"
    sheet.save(os.path.join(a.out, f'sheet_{tag}.png'))
    print(tag, 'mean colour diff vs Gemini on held-out frames:', round(float(np.mean(scores)), 1))


if __name__ == '__main__':
    main()
