"""Fill the slicer's xBR stand-in in hero parts with real pixels of other frames.

A part is cut from one frame; texels another part hides there stay an xBR upscale of the sprite. Frames that were never rendered (nothing new in
the part cover) can show those texels: the rectangular native-looking chunk. Each such texel gets the pixels of a rendered frame whose sprite has
the same colour at that place (shift up to +-3 texels), best donors first. No new render needed.

  python fill_standin.py <hero> <out_dir> <part,part,...|json:scan.json> [--min 0.6]
Writes <out_dir>/<part>.npy (core convention, ready for write_bc7_from_psx) and prints what was filled. Reads the pack, writes nothing to it.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from scan_standin import stand_texels  # noqa: E402

S = 8


def frames_of(h):
    out = {}
    for s in h.layout:
        for fi in range(len(h.layout[s]['frames'])):
            try:
                pl = h.placements(s, fi)
            except Exception:  # noqa: BLE001
                continue
            out[(s, fi)] = pl
    return out


def layout_native(h, pl):
    """Frame in layout coordinates: (RGBA array, x0, y0) and part index per texel."""
    img, (x0, y0) = h.assemble(pl)
    return np.asarray(img), x0, y0


def visible_texels(h, nm, frames):
    """Texels of the part visible in some frame, each with one (frame, placement) that shows it."""
    res = {}
    for key, pl in frames.items():
        idx = [k for k, p in enumerate(pl) if f"{p['block']}-{p['pal']}" == nm]
        if not idx:
            continue
        x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
        W, H = max(p['x'] + p['w'] for p in pl) - x0, max(p['y'] + p['h'] for p in pl) - y0
        owner = np.full((H, W), -1)
        for k, p in enumerate(pl):
            m = np.asarray(h.part(p['block'], p['pal']))[..., 3] > 0
            if p['flipx']:
                m = m[:, ::-1]
            if p['flipy']:
                m = m[::-1]
            owner[p['y'] - y0:p['y'] - y0 + p['h'], p['x'] - x0:p['x'] - x0 + p['w']][m] = k
        for k in idx:
            p = pl[k]
            v = owner[p['y'] - y0:p['y'] - y0 + p['h'], p['x'] - x0:p['x'] - x0 + p['w']] == k
            ys, xs = np.nonzero(v)
            for yy, xx in zip(ys, xs):
                ty = p['h'] - 1 - yy if p['flipy'] else yy
                tx = p['w'] - 1 - xx if p['flipx'] else xx
                res.setdefault((int(ty), int(tx)), (key, p))
    return res


def fill_part(h, nm, frames, natives, comps, min_share):
    st = stand_texels(h, nm)
    if st is None:
        return None, 'no file'
    vis = visible_texels(h, nm, frames)
    want = {t: v for t, v in vis.items() if st[t]}
    if not want:
        return None, 'nothing visible'
    nat = np.asarray(h.part(*nm.split('-')))
    W, H = nat.shape[1], nat.shape[0]
    sample = {}      # texel -> (composite key, cx, cy): composite px of the texel's top-left, before the part's own squeeze
    left = dict(want)
    used = []
    while left:
        best = None
        for dk, (d, dx0, dy0) in natives.items():
            for sy in range(-3, 4):
                for sx in range(-3, 4):
                    hit = []
                    for (ty, tx), (key, p) in left.items():
                        fx = p['w'] - 1 - tx if p['flipx'] else tx
                        fy = p['h'] - 1 - ty if p['flipy'] else ty
                        X, Y = p['x'] + fx - dx0 + sx, p['y'] + fy - dy0 + sy
                        if 0 <= Y < d.shape[0] and 0 <= X < d.shape[1] and d[Y, X, 3] and (d[Y, X, :3] == nat[ty, tx, :3]).all():
                            hit.append(((ty, tx), X, Y, p['flipx'], p['flipy']))
                    if best is None or len(hit) > len(best[1]):
                        best = (dk, hit, sx, sy)
            if best is not None and len(best[1]) == len(left):
                break
        if best is None or len(best[1]) < max(2, min_share * len(left) if not used else 2):
            break
        dk, hit, sx, sy = best
        used.append((dk, len(hit), sx, sy))
        for t, X, Y, fl, fu in hit:
            sample[t] = (dk, X, Y, fl, fu)
            left.pop(t)
    if not sample:
        return None, f'no donor for {len(want)} texels'
    a = read_bc7_level0(os.path.join(PACK, nm + '.bc7')).copy()
    fh, fw = a.shape[:2]
    sxs, sys_ = (W - 1) * S / W if W > 1 else S, (H - 1) * S / H if H > 1 else S
    for fy in range(fh):
        ty = min(int(fy / sys_), H - 1)
        for fx in range(fw):
            tx = min(int(fx / sxs), W - 1)
            t = sample.get((ty, tx))
            if t is None or a[fy, fx, 3] == 0:
                continue
            dk, X, Y, fl, fu = t
            ox = fx / sxs - tx          # 0..1 inside the texel
            oy = fy / sys_ - ty
            if fl:
                ox = 1 - ox
            if fu:
                oy = 1 - oy
            c = comps[dk]
            cy, cx = min(int((Y + oy) * S), c.shape[0] - 1), min(int((X + ox) * S), c.shape[1] - 1)
            a[fy, fx, :3] = c[cy, cx]
    return a, f'filled {len(sample)}/{len(want)} texels from {used}, left {len(left)}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('hero')
    ap.add_argument('out')
    ap.add_argument('parts')
    ap.add_argument('--min', type=float, default=0.6)
    a = ap.parse_args()
    h = Hero(os.path.join(ROOT, 'extracted', 'disc1_full', a.hero))
    work = os.path.join(ROOT, 'ai', 'prod_work', 'h_' + a.hero, 'work')
    frames = frames_of(h)
    natives, comps = {}, {}
    for key, pl in frames.items():
        p = os.path.join(work, f'{key[0]}_{key[1]:03d}_red.png')
        if os.path.exists(p):
            d, x0, y0 = layout_native(h, pl)
            c = np.asarray(Image.open(p).convert('RGB'))
            if c.shape[0] != d.shape[0] * S or c.shape[1] != d.shape[1] * S:
                continue
            natives[key] = (d, x0, y0)
            comps[key] = c
    print('rendered frames', len(natives), 'of', len(frames), flush=True)
    names = a.parts.split(',')
    os.makedirs(a.out, exist_ok=True)
    for nm in names:
        arr, msg = fill_part(h, nm, frames, natives, comps, a.min)
        print(nm, msg, flush=True)
        if arr is not None:
            np.save(os.path.join(a.out, nm + '.npy'), arr)


if __name__ == '__main__':
    main()
