"""Find frames whose original sprite shows no face (back view: the head is hair only) but whose render draws a face.

Self-calibrating per group:
  1. sprite skin = warm k-means colours of the sprite heads that are present in some frames and absent in others
     (hair is in every frame, the face only in front/side frames);
  2. render skin = render pixels lying where the sprite has skin, in frames with a clearly visible face;
  3. per frame: share of skin in the head (top part of the figure) of the sprite and of the render.
A frame is a candidate when the sprite head has no skin but the render head has about as much as a face.

  python qa_backview.py c_bart_70a4dc [...] [--all-done] [--prefix c_,h_] [--csv out.csv] [--top 0.30]
Prints candidates per group; --csv writes every frame (group,set,frame,sprite_skin,render_skin,flag).
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
from make_grids import frame_rgba  # noqa: E402

CRIT = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.3)
STEP = np.array([8, 5, 5], np.float32)          # Lab bin size (OpenCV 0..255 scale)
BINS = (32, 52, 52)
RATIO = 0.45


def binidx(px):
    q = np.minimum((px / STEP).astype(np.int32), np.array(BINS) - 1)
    return q[:, 0], q[:, 1], q[:, 2]


def lab(rgb):
    return cv2.cvtColor(np.ascontiguousarray(rgb).reshape(-1, 1, 3).astype(np.uint8),
                        cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)


def head_rows(alpha, top):
    ys = np.nonzero(alpha.any(1))[0]
    y0, y1 = ys.min(), ys.max()
    return y0, y0 + max(2, int((y1 - y0 + 1) * top))


def load_group(meta, g, top):
    names = sorted((n for n, m in meta.items() if m['group'] == g), key=lambda n: (meta[n]['set'], meta[n]['frame']))
    if not names:
        return []
    h = Hero(os.path.join(ROOT, meta[names[0]]['hero_dir']))
    work = os.path.join(ROOT, 'ai', 'prod_work', g, 'work')
    out = []
    for n in names:
        m = meta[n]
        red = os.path.join(work, f"{m['set']}_{m['frame']:03d}_red.png")
        if not os.path.exists(red):
            continue
        o = np.asarray(frame_rgba(h, m['set'], m['frame']))
        al = o[..., 3] > 127
        if not al.any():
            continue
        r = Image.open(red).convert('RGB')
        if r.size != (o.shape[1], o.shape[0]):
            r = r.resize((o.shape[1], o.shape[0]), Image.LANCZOS)
        y0, y1 = head_rows(al, top)
        hm = al[y0:y1]
        out.append(dict(set=m['set'], frame=m['frame'], spr=lab(o[y0:y1, :, :3][hm]), ren=lab(np.asarray(r)[y0:y1][hm])))
    return out


def analyse(frames, k=14):
    """Returns (rows, info). rows: (set, frame, sprite_skin, render_skin, flag)."""
    allp = np.concatenate([f['spr'] for f in frames])
    if len(allp) > 200000:
        allp = allp[np.random.default_rng(0).choice(len(allp), 200000, replace=False)]
    kk = min(k, len(np.unique(allp, axis=0)))
    _, _, cen = cv2.kmeans(allp, kk, None, CRIT, 3, cv2.KMEANS_PP_CENTERS)
    for f in frames:
        f['lab'] = np.argmin(((f['spr'][:, None] - cen[None]) ** 2).sum(2), 1)
        f['share'] = np.bincount(f['lab'], minlength=kk) / len(f['lab'])
    shares = np.array([f['share'] for f in frames])                       # frames x clusters
    L, A, B = cen[:, 0] * 100 / 255, cen[:, 1] - 128, cen[:, 2] - 128
    warm = (L > 30) & (L < 95) & (A > 4) & (A < 32) & (B > 8) & (B < 55) & (B > A * 0.6)
    absent = (shares < 0.003).mean(0)                                      # share of frames without this colour
    strong = np.percentile(shares, 90, axis=0)
    skin = warm & (absent >= 0.10) & (absent <= 0.90) & (strong >= 0.03)
    if not skin.any():
        return [], dict(skin=[], note='no skin colour found')
    sp = shares[:, skin].sum(1)
    face = sp >= max(0.03, np.percentile(sp, 75) * 0.5)
    # render skin: Lab-histogram classifier trained on this group - positives are render pixels where the sprite is
    # skin (clear-face frames), negatives are render pixels where the sprite is not skin (all frames)
    sk_idx = np.nonzero(skin)[0]
    pos = np.concatenate([f['ren'][np.isin(f['lab'], sk_idx)] for f, fc in zip(frames, face) if fc] or
                         [np.zeros((0, 3), np.float32)])
    neg = np.concatenate([f['ren'][~np.isin(f['lab'], sk_idx)] for f in frames])
    if len(pos) < 50:
        return [], dict(skin=cen[skin].tolist(), note='too few face pixels')
    hp, hn = np.zeros(BINS, np.float32), np.zeros(BINS, np.float32)
    np.add.at(hp, binidx(pos), 1)
    np.add.at(hn, binidx(neg), 1)
    hp, hn = hp / hp.sum(), hn / max(hn.sum(), 1)
    prob = hp / np.maximum(hp + hn, 1e-12)
    is_skin = (prob > 0.75) & (hp > 2e-4)
    rs = np.array([float(is_skin[binidx(f['ren'])].mean()) for f in frames])
    med = np.median(pos, 0)
    ref = float(np.median(rs[face])) if face.any() else 0.0
    rows = []
    for f, s, r in zip(frames, sp, rs):
        flag = s < 0.004 and r >= RATIO * ref and r >= 0.02
        rows.append((f['set'], f['frame'], float(s), float(r), flag))
    return rows, dict(skin=cen[skin].tolist(), render_skin=med.tolist(), ref=ref, faces=int(face.sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('groups', nargs='*')
    ap.add_argument('--all-done', action='store_true', help='every group with a DONE marker')
    ap.add_argument('--prefix', default='c_,h_', help='with --all-done: group prefixes to check')
    ap.add_argument('--top', type=float, default=0.30)
    ap.add_argument('--csv')
    ap.add_argument('--ratio', type=float, default=0.45, help='render skin vs face frames to flag')
    a = ap.parse_args()
    global RATIO
    RATIO = a.ratio
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    work_root = os.path.join(ROOT, 'ai', 'prod_work')
    groups = list(a.groups)
    if a.all_done:
        pre = tuple(a.prefix.split(','))
        groups += [g for g in sorted(os.listdir(work_root))
                   if g.startswith(pre) and os.path.exists(os.path.join(work_root, g, 'DONE'))]
    out = open(a.csv, 'w') if a.csv else None
    for g in groups:
        frames = load_group(meta, g, a.top)
        if not frames:
            continue
        rows, info = analyse(frames)
        cand = [f"{s}:{fr}" for s, fr, _, _, fl in rows if fl]
        note = info.get('note', f"faces {info.get('faces')} ref {info.get('ref', 0):.3f}")
        print(f'{g}: {len(frames)} frames, {note}, candidates {len(cand)}: {" ".join(cand)}', flush=True)
        if out:
            for s, fr, ss, rr, fl in rows:
                out.write(f'{g},{s},{fr},{ss:.4f},{rr:.4f},{int(fl)}\n')


if __name__ == '__main__':
    main()
