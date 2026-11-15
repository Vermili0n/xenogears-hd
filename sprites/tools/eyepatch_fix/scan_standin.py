"""All parts of a hero that show the slicer's xBR stand-in (native look) in some frame, as the pack has them now.

The slicer takes a part from one frame; texels hidden there keep the xBR upscale of the sprite. A greedy frame cover draws every part name
once but does not look at what is visible, so a part can be "covered" by a frame that hides it and show the stand-in in another frame.

  python scan_standin.py <hero> <out.json> [--work ai/prod_work/h_<hero>/work]
"""
import argparse
import ctypes
import json
import os
import sys
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from batch_redraw import uv_compensate, xbr_at  # noqa: E402

S = 8


def stand_texels(h, nm):
    """Texel mask (in the part's own texels) where the pack file equals the stand-in. None when the file is missing / other size."""
    f = os.path.join(PACK, nm + '.bc7')
    if not os.path.exists(f):
        return None
    pimg = h.part(*nm.split('-'))
    a = read_bc7_level0(f).astype(int)
    pc, _ = xbr_at(pimg, S)
    al = np.kron(np.asarray(pimg)[..., 3] > 0, np.ones((S, S), bool))
    si = uv_compensate(np.dstack([pc, np.where(al, 255, 0).astype(np.uint8)]), S).astype(int)
    if a.shape != si.shape:
        return None
    same = (np.abs(a[..., :3] - si[..., :3]).max(axis=-1) < 14) & (a[..., 3] > 0)
    w, ht = pimg.size
    # file -> texels: the file is squeezed into (w-1) x (h-1)
    out = np.zeros((ht, w), bool)
    sx, sy = (w - 1) * S / w if w > 1 else S, (ht - 1) * S / ht if ht > 1 else S
    for y in range(ht):
        for x in range(w):
            c = same[int(y * sy):max(int(y * sy) + 1, int((y + 1) * sy)), int(x * sx):max(int(x * sx) + 1, int((x + 1) * sx))]
            out[y, x] = c.mean() > 0.75
    return out


_H = None


def _init(d):
    global _H
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)   # below normal: the game may be running
    _H = Hero(d)


def _one(nm):
    return nm, stand_texels(_H, nm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('hero')
    ap.add_argument('out')
    ap.add_argument('--work', default='')
    ap.add_argument('--workers', type=int, default=4)
    a = ap.parse_args()
    d = os.path.join(ROOT, 'extracted', 'disc1_full', a.hero)
    h = Hero(d)
    names = set()
    for s in h.layout:
        for fi in range(len(h.layout[s]['frames'])):
            try:
                names |= {f"{p['block']}-{p['pal']}" for p in h.placements(s, fi)}
            except Exception:  # noqa: BLE001
                pass
    with Pool(a.workers, _init, (d,)) as pool:
        precomputed = dict(pool.imap_unordered(_one, sorted(names), chunksize=16))
    work = a.work or os.path.join(ROOT, 'ai', 'prod_work', 'h_' + a.hero, 'work')
    rendered = set(os.listdir(work))
    cache, parts = precomputed, {}
    n_frames = 0
    for s in h.layout:
        for fi in range(len(h.layout[s]['frames'])):
            try:
                pl = h.placements(s, fi)
            except Exception:  # noqa: BLE001
                continue
            n_frames += 1
            x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
            W, H = max(p['x'] + p['w'] for p in pl) - x0, max(p['y'] + p['h'] for p in pl) - y0
            owner = np.full((H, W), -1)
            al = []
            for k, p in enumerate(pl):
                m = np.asarray(h.part(p['block'], p['pal']))[..., 3] > 0
                if p['flipx']:
                    m = m[:, ::-1]
                if p['flipy']:
                    m = m[::-1]
                al.append(m)
                X, Y = p['x'] - x0, p['y'] - y0
                owner[Y:Y + p['h'], X:X + p['w']][m] = k
            for k, p in enumerate(pl):
                nm = f"{p['block']}-{p['pal']}"
                st = cache[nm]
                X, Y = p['x'] - x0, p['y'] - y0
                vis = owner[Y:Y + p['h'], X:X + p['w']] == k
                e = parts.setdefault(nm, {'frames': {}, 'vis_rendered': 0, 'missing': st is None, 'w': p['w'], 'h': p['h']})
                if st is None:
                    continue
                s2 = st
                if p['flipx']:
                    s2 = s2[:, ::-1]
                if p['flipy']:
                    s2 = s2[::-1]
                bad = int((vis & s2).sum())
                tag = f'{s}_{fi:03d}_red.png' in rendered
                if bad:
                    e['frames'][f'{s}:{fi}'] = (bad, int(vis.sum()), tag)
                if tag:
                    e['vis_rendered'] = max(e['vis_rendered'], int(vis.sum()))
    rows = []
    for nm, e in parts.items():
        if not e['frames']:
            continue
        worst = max(v[0] for v in e['frames'].values())
        if worst >= 12:
            rows.append((worst, nm, e['w'], e['h'], e['vis_rendered'], len(e['frames']), sorted(e['frames'].items(), key=lambda kv: -kv[1][0])[:4]))
    rows.sort(key=lambda r: -r[0])
    json.dump({'rows': rows, 'missing': sorted(n for n, e in parts.items() if e['missing'])}, open(a.out, 'w'), indent=0)
    print(f'{a.hero}: frames {n_frames}, parts {len(parts)}, without a pack file {sum(e["missing"] for e in parts.values())}, parts with a visible stand-in >=12 texels: {len(rows)}')
    for r in rows[:30]:
        print(r)


if __name__ == '__main__':
    main()
