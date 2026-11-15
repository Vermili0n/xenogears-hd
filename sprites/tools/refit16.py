"""Re-fit accepted teacher frames at the native grid resolution (16x) instead of the 4x copies prod_fit keeps.

  python refit16.py [--only <job-prefix>] [--force]
For every accepted frame (<work>/<set>_<fi>_red.png written by prod_fit) the rigid fit is searched again on the
512-cell grid exactly as prod_fit does, then applied to the native cell of the raw grid (4096 px -> 1024 px cells).
Output: ai/fit16/<job>/<set>_<fi>.png = RGBA at 16x of the native frame (alpha = original silhouette).
When a frame was drawn in several grids (retries) the fit closest to the accepted 4x redraw wins.
Writes ai/fit16/index.json {job: {hero_dir, kind, slug, frames: {"set_fi": diff}}}.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from gpt_rigid import best_fit  # noqa: E402
from make_grids import CELL, frame_rgba  # noqa: E402
from make_pairs_v2 import BAD, slug_of  # noqa: E402
from or_score import fg_mask  # noqa: E402

cv2.setNumThreads(1)  # several shards run in parallel
AI = os.path.join(ROOT, 'ai')
OUT = os.path.join(AI, 'fit16')
PILOTS = {  # work dir -> (grid job dirs, hero dir, slug)
    'elly_keys': (['keys_elly', 'pilot_elly_nb'], 'extracted/disc1_full/elly', 'elly'),
    'bart_keys': (['keys_bart_field', 'keys_bart_battle', 'keys_bart_retry', 'keys_bart_retryb'], 'extracted/disc1_full/bart', 'bart'),
    'billy_keys': (['keys_billy_field', 'keys_billy_battle'], 'extracted/disc1_full/billy', 'billy'),
}


def sources():
    """[(job, [grid dirs], hero_dir, work_dir, kind, slug, skip set)]"""
    out = []
    jobs = json.load(open(os.path.join(AI, 'campaign', 'jobs.json')))
    for job, v in jobs.items():
        if job in BAD:
            continue
        kind = 'gear' if job.startswith('g_') else 'npc' if job.startswith('m_') else 'char'
        out.append((job, [os.path.join(AI, 'campaign', job)], os.path.join(ROOT, v['hero_dir']),
                    os.path.join(AI, f'{job}_keys', 'work'), kind, slug_of(job), set()))
    for w, (grids, hd, slug) in PILOTS.items():
        out.append((w, [os.path.join(AI, g) for g in grids], os.path.join(ROOT, hd), os.path.join(AI, w, 'work'), 'char', slug, set()))
    for nid in sorted(os.listdir(os.path.join(AI, 'npcj'))):
        w = os.path.join(AI, f'npc_{nid}_prod', 'work')
        if not os.path.isdir(w):
            continue
        fp = os.path.join(w, 'fills.json')
        skip = {f'npc_{int(k):03d}' for k in json.load(open(fp))} if os.path.exists(fp) else set()  # ebsynth fills
        hd = os.path.join(ROOT, 'extracted', 'npc', nid)
        if not os.path.exists(os.path.join(hd, 'layout.json')):
            hd = os.path.join(ROOT, 'extracted', 'npc_full', nid)
        out.append((f'n_{nid}', [os.path.join(AI, 'npcj', nid)], hd, w, 'npc', None, skip))
    return out


def grid_masks(raw, cols, rows):
    """fg mask at the 512-cell scale (with the grid-line removal of prod_fit) + the 512-scale RGB."""
    im = raw.resize((cols * CELL, rows * CELL), Image.LANCZOS) if raw.size != (cols * CELL, rows * CELL) else raw
    rgb = np.asarray(im)
    fm, _ = fg_mask(rgb)
    for axis in (0, 1):
        line = fm.mean(axis=1 - axis) > 0.85
        line = np.convolve(line.astype(float), np.ones(9), 'same') > 0
        if axis == 0:
            fm[line, :] = False
        else:
            fm[:, line] = False
    return rgb, fm


def fit16(raw_np, S, rgb, fm, c, o8):
    """Rigid fit on the 512 cell, applied to the native cell. Returns RGB at 16x of the frame (2 * 8x size) or None."""
    full = o8.size
    o = o8.resize((c['w'], c['h']), Image.LANCZOS) if o8.size != (c['w'], c['h']) else o8
    oa = np.asarray(o)
    om = np.zeros((CELL, CELL), bool)
    x0, y0 = c['x'] - c['cx'], c['y'] - c['cy']
    om[y0:y0 + c['h'], x0:x0 + c['w']] = oa[..., 3] > 0
    dm = fm[c['cy']:c['cy'] + CELL, c['cx']:c['cx'] + CELL]
    if not om.any() or not dm.any():
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
    iou, place = best_fit(rgb[c['cy']:c['cy'] + CELL, c['cx']:c['cx'] + CELL][gy0:gy1, gx0:gx1], dm[gy0:gy1, gx0:gx1], om, s0)
    if place is None:
        return None
    w, h, x, y = place
    N = CELL * S
    cell = raw_np[c['cy'] * S:c['cy'] * S + N, c['cx'] * S:c['cx'] * S + N]
    dcrop = cell[gy0 * S:gy1 * S, gx0 * S:gx1 * S]
    mcrop = cv2.resize(dm[gy0:gy1, gx0:gx1].astype(np.uint8) * 255, (dcrop.shape[1], dcrop.shape[0]), interpolation=cv2.INTER_NEAREST)
    W2, H2 = w * S, h * S
    interp = cv2.INTER_AREA if W2 < dcrop.shape[1] else cv2.INTER_LANCZOS4
    rgba = cv2.resize(np.dstack([dcrop, mcrop]), (W2, H2), interpolation=interp)
    fit = np.zeros((N, N, 4), np.uint8)
    X, Y = x * S, y * S
    sx0, sy0, dx0, dy0 = max(0, -X), max(0, -Y), max(0, X), max(0, Y)
    ww, hh = min(W2 - sx0, N - dx0), min(H2 - sy0, N - dy0)
    if ww <= 0 or hh <= 0:
        return None
    fit[dy0:dy0 + hh, dx0:dx0 + ww] = rgba[sy0:sy0 + hh, sx0:sx0 + ww]
    # fill holes / magenta bleed only inside the original silhouette (the rest is cut away later), on the box crop
    P = 8
    bx0, by0 = max(0, x0 * S - P), max(0, y0 * S - P)
    bx1, by1 = min(N, (x0 + c['w']) * S + P), min(N, (y0 + c['h']) * S + P)
    sub = np.ascontiguousarray(fit[by0:by1, bx0:bx1])
    col = np.ascontiguousarray(sub[..., :3])
    rr, gg, bb = (col[..., k].astype(int) for k in range(3))
    om16 = cv2.resize(om.astype(np.uint8), (N, N), interpolation=cv2.INTER_NEAREST)[by0:by1, bx0:bx1]
    om16 = cv2.dilate(om16, np.ones((7, 7), np.uint8)) > 0
    hole = ((sub[..., 3] < 200) | ((rr - gg > 50) & (bb - gg > 50))) & om16
    if hole.any():
        col = cv2.inpaint(col, hole.astype(np.uint8) * 255, 3, cv2.INPAINT_TELEA)
    box = col[y0 * S - by0:(y0 + c['h']) * S - by0, x0 * S - bx0:(x0 + c['w']) * S - bx0]
    return cv2.resize(box, (full[0] * 2, full[1] * 2), interpolation=cv2.INTER_AREA if c['w'] * S > full[0] * 2 else cv2.INTER_LANCZOS4)


def diff_to_red(rgb16, red_path, a8):
    red = np.asarray(Image.open(red_path).convert('RGB')).astype(np.float32)
    small = cv2.resize(rgb16, (red.shape[1], red.shape[0]), interpolation=cv2.INTER_AREA).astype(np.float32)
    m = cv2.resize(a8, (red.shape[1], red.shape[0]), interpolation=cv2.INTER_NEAREST) > 127
    m = cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    return float(np.abs(small - red)[m].mean()) if m.any() else 999.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--shard', default='0/1', help='i/n: process every n-th job (index written per shard)')
    ap.add_argument('--max-diff', type=float, default=14.0, help='reject fits that do not reproduce the accepted 4x redraw')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    si, sn = map(int, a.shard.split('/'))
    ip = os.path.join(OUT, f'index_{si}.json' if sn > 1 else 'index.json')
    index = json.load(open(ip)) if os.path.exists(ip) else {}
    for k, (job, gdirs, hd, work, kind, slug, skip) in enumerate(sources()):
        if k % sn != si:
            continue
        if a.only and not job.startswith(a.only):
            continue
        if not os.path.isdir(work):
            continue
        accepted = {f[:-8] for f in os.listdir(work) if f.endswith('_red.png')} - skip
        jd = os.path.join(OUT, job)
        if job in index and not a.force and all(os.path.exists(os.path.join(jd, k + '.png')) for k in index[job]['frames']):
            continue
        os.makedirs(jd, exist_ok=True)
        h = Hero(hd)
        best = {}
        for gdir in gdirs:
            gp = os.path.join(gdir, 'in', 'grids.json')
            if not os.path.exists(gp):
                continue
            for g, cells in sorted(json.load(open(gp)).items()):
                path = os.path.join(gdir, 'out', f'{g}.png')
                todo = [c for c in cells if f"{c['set']}_{c['frame']:03d}" in accepted]
                if not os.path.exists(path) or not todo:
                    continue
                raw = Image.open(path).convert('RGB')
                cols, rows = cells[0]['cols'], cells[0]['rows']
                S = max(1, round(raw.width / (cols * CELL)))
                raw_np = np.asarray(raw.resize((cols * CELL * S, rows * CELL * S), Image.LANCZOS)) if raw.size != (cols * CELL * S, rows * CELL * S) else np.asarray(raw)
                rgb, fm = grid_masks(raw, cols, rows)
                for c in todo:
                    key = f"{c['set']}_{c['frame']:03d}"
                    try:
                        o8 = frame_rgba(h, c['set'], c['frame'])
                        r = fit16(raw_np, S, rgb, fm, c, o8)
                    except Exception as e:  # noqa: BLE001
                        print(job, key, 'error', e)
                        continue
                    if r is None:
                        continue
                    a8 = np.asarray(o8)[..., 3]
                    d = diff_to_red(r, os.path.join(work, key + '_red.png'), a8)
                    if d < best.get(key, (999.0,))[0]:
                        best[key] = (d, r, a8)
        frames = {}
        for key, (d, r, a8) in best.items():
            if d > a.max_diff:
                continue
            a16 = cv2.resize(a8, (r.shape[1], r.shape[0]), interpolation=cv2.INTER_NEAREST)
            Image.fromarray(np.dstack([r, a16]), 'RGBA').save(os.path.join(jd, key + '.png'))
            frames[key] = round(d, 2)
        index[job] = {'hero_dir': os.path.relpath(hd, ROOT).replace('\\', '/'), 'kind': kind, 'slug': slug, 'frames': frames}
        json.dump(index, open(ip, 'w'), indent=0)
        ds = sorted(frames.values())
        print(job, kind, f'{len(frames)}/{len(accepted)}', 'median diff', ds[len(ds) // 2] if ds else '-', flush=True)


if __name__ == '__main__':
    main()
