"""Score bake-off outputs against the original sprites and build review sheets.

  python or_score.py --dir ai/or_test

Per output cell: raw IoU (no refit: does the model keep the exact placement?), rigid IoU + contour error p95 at 4x
after the best scale+shift (no warping), and region mismatch = share of the silhouette where blurred colours differ
(boot where a boot should be, face where the face is). Pass = rigid IoU >= 0.95 and p95 <= 6 px.
"""
import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import xbr4  # noqa: E402
from gpt_rigid import best_fit, chamfer  # noqa: E402

CELL = 512


def fg_mask(rgb):
    """Foreground = far from the background colour (median of the image border)."""
    b = np.concatenate([rgb[:4].reshape(-1, 3), rgb[-4:].reshape(-1, 3), rgb[:, :4].reshape(-1, 3), rgb[:, -4:].reshape(-1, 3)])
    bg = np.median(b, axis=0)
    d = np.abs(rgb.astype(int) - bg).sum(-1)
    m = d > 90
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
    return m, bg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=os.path.join(ROOT, 'ai', 'or_test'))
    a = ap.parse_args()
    meta = json.load(open(os.path.join(a.dir, 'in', 'grids.json')))
    orig = {}
    for g, cells in meta.items():
        for c in cells:
            o = Image.open(os.path.join(ROOT, 'extracted', 'disc1', 'fei', 'frames', f"{c['set']}_{c['frame']:03d}.png")).convert('RGBA')
            c4, m4 = xbr4(o)
            rgb8 = np.asarray(Image.fromarray(c4).resize((c['w'], c['h']), Image.LANCZOS))
            m8 = np.asarray(Image.fromarray((m4 * 255).astype(np.uint8)).resize((c['w'], c['h']), Image.LANCZOS)) > 127
            om = np.zeros((CELL, CELL), bool)
            orgb = np.zeros((CELL, CELL, 3), np.uint8)
            x, y = c['x'] - c.get('cx', (c['x'] // CELL) * CELL), c['y'] - c.get('cy', (c['y'] // CELL) * CELL)
            om[y:y + c['h'], x:x + c['w']] = m8
            orgb[y:y + c['h'], x:x + c['w']][m8] = rgb8[m8]
            orig[(g, c['frame'])] = (om, orgb)
    rows, cellimgs = [], {}
    for path in sorted(glob.glob(os.path.join(a.dir, 'out', '*__*.png'))):
        model, grid = os.path.basename(path)[:-4].split('__')
        if grid not in meta:  # repeat runs: <grid>_<tag> -> score as the grid, label the model with the tag
            base = grid
            while base not in meta and '_' in base:
                base = base.rsplit('_', 1)[0]
            if base not in meta:
                continue
            model, grid = model + grid[len(base):], base
        im = Image.open(path).convert('RGB')
        size = im.size
        cols, grows = meta[grid][0].get('cols', 2), meta[grid][0].get('rows', 2)
        if im.size != (cols * CELL, grows * CELL):
            im = im.resize((cols * CELL, grows * CELL), Image.LANCZOS)
        rgb = np.asarray(im)
        fm, bg = fg_mask(rgb)
        for j, c in enumerate(meta[grid]):
            cx, cy = c.get('cx', (j % 2) * CELL), c.get('cy', (j // 2) * CELL)
            om, orgb = orig[(grid, c['frame'])]
            dm = fm[cy:cy + CELL, cx:cx + CELL]
            drgb = rgb[cy:cy + CELL, cx:cx + CELL]
            n, lab, st, _ = cv2.connectedComponentsWithStats(dm.astype(np.uint8), 8)
            keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 0.02 * om.sum()]
            dm = np.isin(lab, keep)
            rec = {'model': model, 'grid': grid, 'frame': c['frame'], 'out_size': f'{size[0]}x{size[1]}'}
            if not dm.any():
                rec.update(raw_iou=0, rigid_iou=0, p95=99, region=1)
                rows.append(rec)
                continue
            rec['raw_iou'] = float((dm & om).sum() / (dm | om).sum())
            ys, xs = np.where(dm)
            gx0, gy0, gx1, gy1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
            oys, oxs = np.where(om)
            s0 = (oys.max() + 1 - oys.min()) / (gy1 - gy0)
            iou, (w, h, x, y) = best_fit(drgb[gy0:gy1, gx0:gx1], dm[gy0:gy1, gx0:gx1], om, s0)
            fitted = np.zeros((CELL, CELL, 4), np.uint8)
            rgba = cv2.resize(np.dstack([drgb[gy0:gy1, gx0:gx1], dm[gy0:gy1, gx0:gx1].astype(np.uint8) * 255]), (w, h),
                              interpolation=cv2.INTER_AREA)
            sx0, sy0, dx0, dy0 = max(0, -x), max(0, -y), max(0, x), max(0, y)
            ww, hh = min(w - sx0, CELL - dx0), min(h - sy0, CELL - dy0)
            fitted[dy0:dy0 + hh, dx0:dx0 + ww] = rgba[sy0:sy0 + hh, sx0:sx0 + ww]
            fmask = fitted[..., 3] > 127
            cm, c95 = chamfer(fmask, om)
            both = fmask & om
            bo = cv2.GaussianBlur(orgb.astype(np.float32), (0, 0), 5)
            bf = cv2.GaussianBlur(fitted[..., :3].astype(np.float32), (0, 0), 5)
            region = float((np.abs(bo - bf).sum(-1)[both] > 90).mean()) if both.any() else 1.0
            rec.update(rigid_iou=float(iou), p95=c95 / 2, mean_edge=cm / 2, region=region, scale=w / (gx1 - gx0))
            rows.append(rec)
            cellimgs[(model, grid, c['frame'])] = (fitted, om)
    json.dump(rows, open(os.path.join(a.dir, 'scores.json'), 'w'), indent=1)
    # summary per model
    models = sorted({r['model'] for r in rows})
    print(f"{'model':42s} {'n':>3s} {'rawIoU':>7s} {'rigIoU':>7s} {'p95@4x':>7s} {'region':>7s} {'pass':>5s}")
    summ = []
    for m in models:
        rs = [r for r in rows if r['model'] == m]
        ok = [r for r in rs if r['rigid_iou'] >= 0.95 and r['p95'] <= 6]
        s = (m, len(rs), np.mean([r['raw_iou'] for r in rs]), np.mean([r['rigid_iou'] for r in rs]),
             np.mean([r['p95'] for r in rs]), np.mean([r['region'] for r in rs]), len(ok))
        summ.append(s)
    for s in sorted(summ, key=lambda s: -s[3]):
        print(f'{s[0]:42s} {s[1]:3d} {s[2]:7.3f} {s[3]:7.3f} {s[4]:7.1f} {s[5]:7.3f} {s[6]:5d}')
    for g in meta:
        print(g, ' '.join(f"{m.split('_', 1)[1][:18]}={np.mean([r['rigid_iou'] for r in rows if r['model'] == m and r['grid'] == g]):.2f}"
                          for m in models if any(r['grid'] == g and r['model'] == m for r in rows)))
    # review sheets: one per grid; rows = original + models (rigid-fitted, original contour in red on the debug sheet)
    font = ImageFont.truetype('arial.ttf', 20)
    S = 256
    for g, cells in meta.items():
        ms = [m for m in models if (m, g, cells[0]['frame']) in cellimgs]
        if len(cells) > 4:
            continue  # big grids get their own sheet (big_sheet below)
        for debug in (False, True):
            sheet = Image.new('RGB', (230 + 4 * (S + 6), (len(ms) + 1) * (S + 6) + 10), (60, 60, 60))
            d = ImageDraw.Draw(sheet)
            d.text((6, 10 + S // 2), 'original', fill=(255, 230, 120), font=font)
            for j, c in enumerate(cells):
                om, orgb = orig[(g, c['frame'])]
                v = orgb.copy(); v[~om] = (60, 60, 60)
                sheet.paste(Image.fromarray(v).resize((S, S), Image.LANCZOS), (230 + j * (S + 6), 5))
            for r, m in enumerate(ms, 1):
                rs = [x for x in rows if x['model'] == m and x['grid'] == g]
                d.text((6, 5 + r * (S + 6) + S // 2 - 20), m.split('_', 1)[1][:22], fill=(255, 230, 120), font=font)
                d.text((6, 5 + r * (S + 6) + S // 2 + 6), f"IoU {np.mean([x['rigid_iou'] for x in rs]):.2f}", fill=(200, 200, 200), font=font)
                for j, c in enumerate(cells):
                    if (m, g, c['frame']) not in cellimgs:
                        continue
                    fitted, om = cellimgs[(m, g, c['frame'])]
                    bgim = Image.new('RGBA', (CELL, CELL), (60, 60, 60, 255))
                    bgim.alpha_composite(Image.fromarray(fitted, 'RGBA'))
                    v = np.asarray(bgim.convert('RGB')).copy()
                    if debug:
                        e = cv2.morphologyEx(om.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
                        v[e] = (255, 50, 50)
                    sheet.paste(Image.fromarray(v).resize((S, S), Image.LANCZOS), (230 + j * (S + 6), 5 + r * (S + 6)))
            sheet.save(os.path.join(a.dir, f"sheet_{g}{'_debug' if debug else ''}.png"))
    big_sheet(a, meta, orig, rows, cellimgs, models)


def big_sheet(a, meta, orig, rows, cellimgs, models):
    S = 192
    for g, cells in meta.items():
        if len(cells) <= 4:
            continue
        for m in models:
            if (m, g, cells[0]['frame']) not in cellimgs:
                continue
            per = 8
            nrow = -(-len(cells) // per)
            sheet = Image.new('RGB', (per * (S + 4) + 4, nrow * (2 * S + 12) + 4), (60, 60, 60))
            for j, c in enumerate(cells):
                om, orgb = orig[(g, c['frame'])]
                v = orgb.copy(); v[~om] = (60, 60, 60)
                x, y = 4 + (j % per) * (S + 4), 4 + (j // per) * (2 * S + 12)
                sheet.paste(Image.fromarray(v).resize((S, S), Image.LANCZOS), (x, y))
                fitted, _ = cellimgs[(m, g, c['frame'])]
                bgim = Image.new('RGBA', (CELL, CELL), (60, 60, 60, 255))
                bgim.alpha_composite(Image.fromarray(fitted, 'RGBA'))
                sheet.paste(bgim.convert('RGB').resize((S, S), Image.LANCZOS), (x, y + S + 2))
            sheet.save(os.path.join(a.dir, f'sheet_{g}__{m}.png'))


if __name__ == '__main__':
    main()
