"""Which frame's redraw each shared part takes, chosen to minimise seams inside assembled frames.

  python part_owners.py --hero fei --out-tag _prod [--hero-dir ...] [--tol 0.9] [--out owners.json]
Every part (block-pal) gets ONE drawing for all frames that show it. slice picks the frame that shows the part most
fully (max share); a face is then often stitched from drawings of 3-4 different frames -> visible seams.
Here: candidates = frames whose share >= tol * max share (still show the part almost fully); among them pick the owner
that agrees with the owners of the neighbouring parts (iterated conditional modes over the seam length).
Seam = pair of 4-adjacent opaque pixels of one assembled frame that come from parts drawn by different frames.
Writes {part: "set:frame"} for batch_redraw.py slice --owners.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from batch_redraw import read_plan  # noqa: E402


def frame_maps(hobj, s, fi):
    """Per-pixel index of the visible placement (top-most drawn last) and per-part visible/total pixel counts."""
    places = hobj.placements(s, fi)
    x0 = min(p['x'] for p in places)
    y0 = min(p['y'] for p in places)
    W = max(p['x'] + p['w'] for p in places) - x0
    H = max(p['y'] + p['h'] for p in places) - y0
    own = np.full((H, W), -1, np.int32)
    masks = []
    for k, p in enumerate(places):
        m = np.asarray(hobj.part(p['block'], p['pal']))[..., 3] > 0
        if p['flipx']:
            m = m[:, ::-1]
        if p['flipy']:
            m = m[::-1]
        X, Y = p['x'] - x0, p['y'] - y0
        own[Y:Y + m.shape[0], X:X + m.shape[1]][m] = k
        masks.append(m.sum())
    names = [f"{p['block']}-{p['pal']}" for p in places]
    vis = np.bincount(own[own >= 0], minlength=len(places))
    pidx = np.full(own.shape, -1, np.int32)  # pixel -> part name index (global ids assigned by caller)
    return names, own, vis, masks, pidx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', default='fei')
    ap.add_argument('--hero-dir', default='')
    ap.add_argument('--out-tag', default='_prod')
    ap.add_argument('--only', default='', help='set:frame list (default: plan frames that have a redraw)')
    ap.add_argument('--tol', type=float, default=0.9)
    ap.add_argument('--rounds', type=int, default=8)
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    hobj = Hero(a.hero_dir or os.path.join(ROOT, 'extracted', 'disc1_full', a.hero))
    work = os.path.join(ROOT, 'ai', a.hero + a.out_tag, 'work')
    cand = [(t.split(':')[0], int(t.split(':')[1])) for t in a.only.split(',')] if a.only else read_plan(a.hero, False)
    done = [(s, fi) for s, fi in cand if os.path.exists(os.path.join(work, f'{s}_{fi:03d}_red.png'))]
    pid, pname = {}, []
    share = defaultdict(dict)       # part -> {frame index: share}
    adj = defaultdict(lambda: defaultdict(int))  # (part a, part b, frame) seam length if owners differ -> key (a, b) per frame
    pairs = []                      # (frame, part a, part b, length)
    for f, (s, fi) in enumerate(done):
        names, own, vis, masks, _ = frame_maps(hobj, s, fi)
        g = np.full(own.shape, -1, np.int32)
        for k, n in enumerate(names):
            if n not in pid:
                pid[n] = len(pname)
                pname.append(n)
            if vis[k]:
                share[pid[n]][f] = max(share[pid[n]].get(f, 0), vis[k] / max(1, masks[k]))
        lut = np.array([pid[n] for n in names] + [-1], np.int32)
        g = lut[own]                # -1 maps to the last entry (-1)
        cnt = defaultdict(int)
        for A, B in ((g[:, :-1], g[:, 1:]), (g[:-1], g[1:])):
            sel = (A >= 0) & (B >= 0) & (A != B)
            for x, y in zip(A[sel].tolist(), B[sel].tolist()):
                cnt[(min(x, y), max(x, y))] += 1
        pairs += [(f, x, y, c) for (x, y), c in cnt.items()]
    nb = defaultdict(list)          # part -> [(other part, frame, length)]
    for f, x, y, c in pairs:
        nb[x].append((y, f, c))
        nb[y].append((x, f, c))

    def seams(owner):
        return sum(c for f, x, y, c in pairs if owner[x] != owner[y])

    base = {p: max(fs, key=fs.get) for p, fs in share.items()}
    cands = {p: [f for f, v in fs.items() if v >= a.tol * fs[base[p]]] for p, fs in share.items()}
    owner = dict(base)
    s0 = seams(owner)
    for r in range(a.rounds):
        changed = 0
        for p in sorted(share, key=lambda q: -len(cands[q])):
            if len(cands[p]) < 2:
                continue
            # cost of each candidate = seam length to neighbours whose owner differs
            best = min(cands[p], key=lambda f: (sum(c for q, fr, c in nb[p] if owner.get(q) != f), f != base[p]))
            if best != owner[p]:
                owner[p] = best
                changed += 1
        if not changed:
            break
    s1 = seams(owner)
    tot = sum(c for *_, c in pairs)
    multi = sum(1 for p in share if len(cands[p]) > 1)
    print(f'{len(done)} frames, {len(share)} parts ({multi} with >1 candidate); boundary px {tot}')
    print(f'seams: max-share {s0} ({s0 / tot:.1%})  ->  optimised {s1} ({s1 / tot:.1%}); owners changed {sum(owner[p] != base[p] for p in owner)}')
    if a.out:
        json.dump({pname[p]: f'{done[f][0]}:{done[f][1]}' for p, f in owner.items()}, open(a.out, 'w'), indent=0)


if __name__ == '__main__':
    main()
