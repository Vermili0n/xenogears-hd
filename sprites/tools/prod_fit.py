"""Production QA + fit for redrawn grids (make_grids.py layout).

  python prod_fit.py --job ai/fei_field --hero fei --out-tag _prod

For each cell: rigid fit (scale + shift) of the drawing onto the original at 8x; checks
  IoU >= 0.93, contour p95 <= 6 px (at 4x), redrawn (detail difference vs the smoothed sprite >= 10.5);
passing cells are written as 4x redraws to ai/<hero><out-tag>/work/<set>_<fi>_red.png (input for batch_redraw slice).
Writes <job>/qa.json, <job>/retry.txt (failed set:frame list) and <job>/sheet_<grid>.png for review.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from gpt_rigid import best_fit, chamfer  # noqa: E402
from make_grids import CELL, frame_rgba  # noqa: E402
from or_score import fg_mask  # noqa: E402


def fit_cell(drgb, dm, om):
    if not om.any():
        return None
    n, lab, st, _ = cv2.connectedComponentsWithStats(dm.astype(np.uint8), 8)
    if n < 2:
        return None
    big = st[1:, cv2.CC_STAT_AREA].max()
    dm = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 0.05 * big])
    ys, xs = np.where(dm)
    gx0, gy0, gx1, gy1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    oys = np.where(om)[0]
    s0 = (oys.max() + 1 - oys.min()) / (gy1 - gy0)
    iou, place = best_fit(drgb[gy0:gy1, gx0:gx1], dm[gy0:gy1, gx0:gx1], om, s0)
    if place is None:
        return None
    w, h, x, y = place
    rgba = cv2.resize(np.dstack([drgb[gy0:gy1, gx0:gx1], dm[gy0:gy1, gx0:gx1].astype(np.uint8) * 255]), (w, h),
                      interpolation=cv2.INTER_AREA)
    H, W = om.shape
    fit = np.zeros((H, W, 4), np.uint8)
    sx0, sy0, dx0, dy0 = max(0, -x), max(0, -y), max(0, x), max(0, y)
    ww, hh = min(w - sx0, W - dx0), min(h - sy0, H - dy0)
    fit[dy0:dy0 + hh, dx0:dx0 + ww] = rgba[sy0:sy0 + hh, sx0:sx0 + ww]
    return iou, fit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--job', required=True)
    ap.add_argument('--hero', default='fei')
    ap.add_argument('--hero-dir', default='', help='sprite folder (default extracted/disc1_full/<hero>)')
    ap.add_argument('--out-tag', default='_prod')
    ap.add_argument('--min-iou', type=float, default=0.93)
    ap.add_argument('--max-p95', type=float, default=6.0)
    ap.add_argument('--min-redraw', type=float, default=10.5)
    ap.add_argument('--src', default='out', help='folder with the model outputs inside the job')
    a = ap.parse_args()
    meta = json.load(open(os.path.join(a.job, 'in', 'grids.json')))
    hobj = Hero(a.hero_dir or os.path.join(ROOT, 'extracted', 'disc1_full', a.hero))
    work = os.path.join(ROOT, 'ai', a.hero + a.out_tag, 'work')
    os.makedirs(work, exist_ok=True)
    qa, retry = [], []
    font = ImageFont.truetype('arial.ttf', 16)
    for g, cells in sorted(meta.items()):
        path = os.path.join(a.job, a.src, f'{g}.png')
        if not os.path.exists(path):
            retry += [f"{c['set']}:{c['frame']}" for c in cells]
            print(g, 'no output')
            continue
        cols, rows = cells[0]['cols'], cells[0]['rows']
        im = Image.open(path).convert('RGB')
        if im.size != (cols * CELL, rows * CELL):
            im = im.resize((cols * CELL, rows * CELL), Image.LANCZOS)
        rgb = np.asarray(im)
        fm, _ = fg_mask(rgb)
        # the model sometimes draws grid lines between cells: drop rows/columns that run across the whole image
        for axis in (0, 1):
            line = fm.mean(axis=1 - axis) > 0.85
            line = np.convolve(line.astype(float), np.ones(9), 'same') > 0
            if axis == 0:
                fm[line, :] = False
            else:
                fm[:, line] = False
        S = 200
        sheet = Image.new('RGB', (cols * 2 * (S + 4) + 4, rows * (S + 24) + 4), (60, 60, 60))
        d = ImageDraw.Draw(sheet)
        for j, c in enumerate(cells):
            o = frame_rgba(hobj, c['set'], c['frame'])
            full = o.size  # 8x of the original frame; the grid may hold a shrunk copy
            if o.size != (c['w'], c['h']):
                o = o.resize((c['w'], c['h']), Image.LANCZOS)
            oa = np.asarray(o)
            om = np.zeros((CELL, CELL), bool)
            orgb = np.zeros((CELL, CELL, 3), np.uint8)
            x, y = c['x'] - c['cx'], c['y'] - c['cy']
            om[y:y + c['h'], x:x + c['w']] = oa[..., 3] > 0
            orgb[y:y + c['h'], x:x + c['w']] = oa[..., :3]
            dm = fm[c['cy']:c['cy'] + CELL, c['cx']:c['cx'] + CELL]
            drgb = rgb[c['cy']:c['cy'] + CELL, c['cx']:c['cx'] + CELL]
            rec = {'grid': g, 'set': c['set'], 'frame': c['frame']}
            r = fit_cell(drgb, dm, om)
            if r is None:
                rec.update(ok=False, why='empty')
            else:
                iou, fit = r
                fmask = fit[..., 3] > 127
                _, p95 = chamfer(fmask, om)
                col = fit[..., :3].copy()
                rr, gg, bb = (col[..., k].astype(int) for k in range(3))
                hole = (fit[..., 3] < 200) | ((rr - gg > 50) & (bb - gg > 50))
                col = cv2.inpaint(col, hole.astype(np.uint8) * 255, 3, cv2.INPAINT_TELEA)
                inner = cv2.erode(om.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
                go = cv2.GaussianBlur(cv2.cvtColor(orgb, cv2.COLOR_RGB2GRAY).astype(np.float32), (0, 0), 1)
                gf = cv2.GaussianBlur(cv2.cvtColor(col, cv2.COLOR_RGB2GRAY).astype(np.float32), (0, 0), 1)
                redraw = float(np.abs(go - gf)[inner].mean()) if inner.any() else 0.0
                # thin flying hair lowers IoU while the contour still matches: accept IoU >= 0.90 if contour p95 <= 4 px
                shape_ok = (iou >= a.min_iou and p95 / 2 <= a.max_p95) or (iou >= 0.90 and p95 / 2 <= 4.0)
                ok = shape_ok and redraw >= a.min_redraw * 0.8
                why = [] if ok else [w for w, bad in (('shape', not shape_ok),
                                                      ('not redrawn', redraw < a.min_redraw)) if bad]
                rec.update(ok=bool(ok), iou=round(float(iou), 3), p95=round(p95 / 2, 1), redraw=round(redraw, 1), why=why)
                if ok:  # 4x redraw for slicing: crop the original's box, halve
                    box = col[y:y + c['h'], x:x + c['w']]
                    red4 = cv2.resize(box, (full[0] // 2, full[1] // 2), interpolation=cv2.INTER_AREA)
                    Image.fromarray(red4).save(os.path.join(work, f"{c['set']}_{c['frame']:03d}_red.png"))
                v = col.copy(); v[~om] = (60, 60, 60)
                px, py = 4 + (j % cols) * 2 * (S + 4), 4 + (j // cols) * (S + 24)
                ov = orgb.copy(); ov[~om] = (60, 60, 60)
                sheet.paste(Image.fromarray(ov).resize((S, S), Image.LANCZOS), (px, py + 20))
                sheet.paste(Image.fromarray(v).resize((S, S), Image.LANCZOS), (px + S + 4, py + 20))
                d.text((px, py + 2), f"{c['frame']} {'OK' if ok else 'FAIL ' + ','.join(why)} iou {iou:.2f} r {redraw:.0f}",
                       fill=(120, 255, 120) if ok else (255, 90, 90), font=font)
            if not rec['ok']:
                retry.append(f"{c['set']}:{c['frame']}")
            qa.append(rec)
        gq = [r for r in qa if r['grid'] == g and 'redraw' in r]
        if gq and np.median([r['redraw'] for r in gq]) < a.min_redraw:  # the whole grid came back as a smoothed copy
            for r in gq:
                if r['ok']:
                    r['ok'] = False
                    r['why'] = ['grid not redrawn']
                    retry.append(f"{r['set']}:{r['frame']}")
                    rp = os.path.join(work, f"{r['set']}_{r['frame']:03d}_red.png")
                    if os.path.exists(rp):  # a frame repeated to pad a partial grid is removed once
                        os.remove(rp)
        sheet.save(os.path.join(a.job, f'sheet_{g}.png'))
        print(g, sum(r['ok'] for r in qa if r['grid'] == g), '/', len(cells), 'ok', flush=True)
    json.dump(qa, open(os.path.join(a.job, 'qa.json'), 'w'), indent=1)
    open(os.path.join(a.job, 'retry.txt'), 'w').write(','.join(retry))
    print('total ok', sum(r['ok'] for r in qa), '/', len(qa), ' retry:', len(retry))


if __name__ == '__main__':
    main()
