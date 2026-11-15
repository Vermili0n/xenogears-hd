r"""The gear HUD's reticle ring (palette row 508) drawn smooth (16.11.2026): circles by radius, not by texels.

  python ai\redraw\gaps_1115\ring_draw.py      ring\weights.npz + ring\preview_*.png (original x6 | before | after)
Used by hud_draw.py for every state of row 508 (hud_draw.py --install rewrites our own files).

Why the ring stayed stepped in game (out\fix_1115\verify\ring_cmp.png): the reticle is drawn 1:1 on the 320x224 screen
from 24 tiles of the sheet (texels 0..103 x 156..187, 8-bit): tiles 0-11 make the right half, 12-23 the same tiles
turned by 180 degrees about (173,104). Its band's indices 1..197 run with the angle (the palette row turns, so a light
sweeps round), indices 223/238 are the thin rings and the outer arcs, 211..235 the outer arcs' darker edge texels.
hud_draw.labels() interpolated each index's mask between texel centres: an index that changes every texel along the
angle keeps its texel blocks, and a circle stays a staircase at 6x on a 1920 screen.
Here: the ring is put together on the screen as the game does (right half from tiles 0-11, the left by the turn), read
in polar coordinates about the centre, and
  - the layers (thin rings, band, outer arcs) are each radius's majority over +-WIN degrees of angle: their borders become
    circles, the arcs' ends stay where they were (the majority turns at the end);
  - the band's index at an angle is the majority along its ray (borders become radial lines); between two indices the
    colour ramps over RAMP texels of arc (the sweep has no steps);
  - every HD pixel is 4x4 samples: its colour is the samples' palette colours averaged, transparent samples black - the
    ring is drawn with additive blending (every colour has its STP bit, pageblend 1), so a darker edge pixel is exactly
    a partly covered one.
The HD of each tile is cut from this picture at the tile's place (tiles 0-11; 12-23 show the same files turned).
"""
import os

import numpy as np
from PIL import Image
from scipy import sparse

from hud_common import clut, idx8, vram
from hud_frame import LINE
from render_frames import psx_to_rgba

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'ring')
REP = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))), 'xeno_port', 'out',
                   'fix_1115', 'H', 'rep1', 'reports', '2026-11-15T22-49-30-649', 'frame.txt')
S = 8
SUB = 4
CX, CY = 173.0, 104.0
R0, R1, RSTEP = 28.0, 62.0, 1 / 16
NTH = 4096
WIN = 12.0          # degrees each side for a layer's majority
RAMP = 0.8          # texels of arc over which the band ramps between two indices
BAND = 1000
EDGE_AA = set(range(199, 238)) - {223}   # the outer arcs' darker edge texels: coverage of 238, not colours of their own


def prims(path, cl=(0, 508)):
    out = []
    for line in open(path, encoding='utf-8', errors='replace'):
        m = LINE.match(line)
        if not m:
            continue
        g = [float(x) if '.' in x else int(x) for x in m.groups()]
        if (g[6], g[7]) != cl or (g[2], g[3]) != (960, 0):
            continue
        out.append((g[0], [(g[11 + 4 * i], g[12 + 4 * i], g[13 + 4 * i], g[14 + 4 * i]) for i in range(4)]))
    return out


def tiles(path=REP):
    """The unturned tiles: (screen x0, y0, sheet u0, v0, w, h), moved so that the reticle's centre is (CX, CY) (the
    reticle follows its target: tile 0,156 lies 48 rows above the centre and starts at it)."""
    out = []
    for n, pts in prims(path):
        (x0, y0, u0, v0), (x1, _, u1, _), (_, y2, _, v2) = pts[0], pts[1], pts[2]
        if x1 > x0 and u1 > u0 and y2 > y0 and v2 > v0:
            out.append((int(x0), int(y0), int(u0), int(v0), int(x1 - x0), int(y2 - y0)))
    ref = [t for t in out if t[2:4] == (0, 156)][0]
    dx, dy = int(CX) - ref[0], int(CY) - 48 - ref[1]
    return [(x + dx, y + dy, u, v, w, h) for x, y, u, v, w, h in out]


def screen(i8, tl):
    scr = np.full((224, 320), -1, np.int32)
    for x0, y0, u0, v0, w, h in tl:
        scr[y0:y0 + h, x0:x0 + w] = i8[v0 - 52:v0 - 52 + h, u0:u0 + w]
    # the left half: the same tiles turned about (173,104): pixel (x, y) <- (345 - x, 207 - y)
    yy, xx = np.mgrid[0:224, 0:320]
    sy, sx = 207 - yy, 345 - xx
    ok = (sy >= 0) & (sy < 224) & (sx >= 0) & (sx < 320)
    turned = np.full_like(scr, -1)
    turned[ok] = scr[sy[ok], sx[ok]]
    scr = np.where((scr < 0) & (turned >= 0), turned, scr)
    return scr


def polar(scr):
    rs = np.arange(R0, R1, RSTEP)
    th = np.arange(NTH) * 2 * np.pi / NTH
    x = np.floor(CX + rs[:, None] * np.cos(th)[None]).astype(int)
    y = np.floor(CY + rs[:, None] * np.sin(th)[None]).astype(int)
    ok = (x >= 0) & (x < 320) & (y >= 0) & (y < 224)
    P = np.full(x.shape, -1, np.int32)
    P[ok] = scr[y[ok], x[ok]]
    return P


def layers(P):
    """Each radius's majority over +-WIN degrees (labels: -1 none, BAND, the constant indices)."""
    L = P.copy()
    L[(L >= 1) & (L <= 198)] = BAND
    L[np.isin(L, list(EDGE_AA))] = 238
    L[L == 0] = -1
    labs = sorted(set(L.ravel().tolist()))
    k = int(round(WIN / 360 * NTH))
    best = np.full(L.shape, -1, np.int32)
    bestc = np.full(L.shape, -1.0)
    for lab in labs:
        one = (L == lab).astype(np.float32)
        ext = np.concatenate([one[:, -k:], one, one[:, :k]], 1)
        cs = np.cumsum(np.pad(ext, ((0, 0), (1, 0))), 1)
        cnt = cs[:, 2 * k + 1:] - cs[:, :-2 * k - 1]
        better = cnt > bestc
        best[better], bestc[better] = lab, cnt[better]
    return best


def band_angle(P):
    """The band's index at each angle: the majority of the band's cells on that ray."""
    A = np.zeros(NTH, np.int32)
    for j in range(NTH):
        col = P[:, j]
        col = col[(col >= 1) & (col <= 198)]
        A[j] = np.bincount(col).argmax() if col.size else 0
    for j in range(NTH):                         # rays with no band cell: the nearest angle's
        if A[j] == 0:
            A[j] = A[(j - 1) % NTH] or A[(j + 1) % NTH]
    return A


def weights(path=REP):
    """Sparse (pixels x 256) weights of every HD pixel of the ring's tiles, and where those pixels lie on the sheet."""
    i8 = idx8(np.load(os.path.join(HERE, 'hud', 'upload_words.npy')))
    tl = tiles(path)
    scr = screen(i8, tl)
    P = polar(scr)
    Lay = layers(P)
    A = band_angle(P)
    # run boundaries of A, for the ramp: for each angle, the index before/after and the distance (in angle steps) to
    # the nearest boundary
    change = np.nonzero(A != np.roll(A, 1))[0]          # first step of each run
    rows, cols, vals, places = [], [], [], []
    base = 0
    for x0, y0, u0, v0, w, h in tl:
        gy, gx = np.mgrid[0:h * S * SUB, 0:w * S * SUB]
        sx = x0 + (gx + 0.5) / (S * SUB)
        sy = y0 + (gy + 0.5) / (S * SUB)
        r = np.hypot(sx - CX, sy - CY)
        t = np.mod(np.arctan2(sy - CY, sx - CX), 2 * np.pi)
        ri = np.clip(np.round((r - R0) / RSTEP).astype(int), 0, Lay.shape[0] - 1)
        tj = np.round(t / (2 * np.pi) * NTH).astype(int) % NTH
        lab = Lay[ri, tj]
        lab[(r < R0) | (r >= R1)] = -1
        pix = (gy // SUB) * (w * S) + (gx // SUB) + base
        # band samples: index and ramp to the neighbour run
        bm = lab == BAND
        j = tj[bm]
        k = np.searchsorted(change, j, side='right') - 1
        start = change[k % len(change)]
        nxt = change[(k + 1) % len(change)]
        d_prev = (j - start) % NTH
        d_next = (nxt - j) % NTH
        arc = 2 * np.pi * r[bm] / NTH                    # texels per angle step at this radius
        a_here = A[j]
        a_prev = A[(start - 1) % NTH]
        a_next = A[nxt % NTH]
        half = RAMP / 2
        dp, dn = d_prev * arc, d_next * arc
        wp = np.clip((half - dp) / RAMP, 0, 0.5)         # share of the previous run near its border
        wn = np.clip((half - dn) / RAMP, 0, 0.5)
        wh = 1 - wp - wn
        for idx, wt in ((a_here, wh), (a_prev, wp), (a_next, wn)):
            rows.append(pix[bm])
            cols.append(idx)
            vals.append(wt / (SUB * SUB))
        cm = (lab >= 0) & ~bm
        rows.append(pix[cm])
        cols.append(lab[cm])
        vals.append(np.full(cm.sum(), 1.0 / (SUB * SUB)))
        places.append((u0, v0 - 52, w, h, base))
        base += w * h * S * S
    W = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(base, 256))
    return W, places, scr


GAUGE_ROWS, GAUGE_RAMP_ROWS, GAUGE_RAMP_COLS = (241 - 52, 249 - 52), (241 - 52, 246 - 52), 112


def gauge_weights():
    """The left vertical gauge (row 511; one primitive, sheet rows 243..247 turned upright, 2x across): its texels hold a
    diagonal ramp, index = c - u + v over the turning range 1..198, so a band of colour moves along it as the row turns.
    hud_draw drew each index as its own shape (diagonal steps) and the 2-row bar under it as a thin stroke. Here every
    texel keeps its square (the strip's edges are straight), the ramp's colour runs continuously: the index is
    interpolated between texel centres (cyclic over 1..198) and the colour mixed between its two palette neighbours."""
    i8 = idx8(np.load(os.path.join(HERE, 'hud', 'upload_words.npy')))
    r0, r1 = GAUGE_ROWS
    sub = i8[r0:r1]
    h, w = sub.shape
    ramp = np.zeros_like(sub, bool)
    ramp[GAUGE_RAMP_ROWS[0] - r0:GAUGE_RAMP_ROWS[1] - r0, :GAUGE_RAMP_COLS] = True
    ramp &= (sub >= 1) & (sub <= 198)
    gy, gx = np.mgrid[0:h * S, 0:w * S]
    ty, tx = gy // S, gx // S
    fy, fx = (gy + 0.5) / S - 0.5, (gx + 0.5) / S - 0.5
    pix = gy * (w * S) + gx
    rows, cols, vals = [], [], []
    opq = sub[ty, tx] > 0
    plain = opq & ~ramp[ty, tx]
    rows.append(pix[plain]), cols.append(sub[ty, tx][plain]), vals.append(np.ones(plain.sum()))
    m = opq & ramp[ty, tx]
    y0 = np.clip(np.floor(fy[m]).astype(int), 0, h - 1)
    x0 = np.clip(np.floor(fx[m]).astype(int), 0, w - 1)
    ay, ax = fy[m] - y0, fx[m] - x0
    ref = sub[ty, tx][m].astype(float)
    acc, wsum = np.zeros(m.sum()), np.zeros(m.sum())
    for dy, dx, wt in ((0, 0, (1 - ay) * (1 - ax)), (0, 1, (1 - ay) * ax), (1, 0, ay * (1 - ax)), (1, 1, ay * ax)):
        yy, xx = np.clip(y0 + dy, 0, h - 1), np.clip(x0 + dx, 0, w - 1)
        ok = ramp[yy, xx]
        val = sub[yy, xx].astype(float)
        val = ref + (np.mod(val - ref + 99, 198) - 99)          # nearest turn of the cycle
        acc += np.where(ok, wt * val, 0)
        wsum += np.where(ok, wt, 0)
    f = acc / np.maximum(wsum, 1e-6)
    lo = np.floor(f)
    t = f - lo
    k0 = (np.mod(lo - 1, 198) + 1).astype(int)
    k1 = (np.mod(lo, 198) + 1).astype(int)
    for k, wt in ((k0, 1 - t), (k1, t)):
        rows.append(pix[m]), cols.append(k), vals.append(wt)
    W = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(h * w * S * S, 256))
    return W, (0, r0, w, h)


def apply_gauge(img, row):
    """Overwrite the gauge's rows (sheet v 241..248) of the HD sheet img with the continuous ramp in row's colours."""
    if 'gauge' not in _CACHE:
        _CACHE['gauge'] = gauge_weights()
    W, (u0, v0, w, h) = _CACHE['gauge']
    rgb = np.array([psx_to_rgba(int(c))[:3] for c in row], np.float32)
    stp = np.array([(int(c) & 0x8000) != 0 for c in row])
    zero = np.array([int(c) == 0 for c in row])
    col = (W @ rgb).reshape(h * S, w * S, 3)
    any_w = np.asarray(W.sum(1)).reshape(h * S, w * S) > 0
    i8 = idx8(np.load(os.path.join(HERE, 'hud', 'upload_words.npy')))[v0:v0 + h, u0:u0 + w]
    near = np.repeat(np.repeat(i8, S, 0), S, 1)
    tile = np.zeros((h * S, w * S, 4), np.uint8)
    q = np.clip(col + 0.5, 0, 255).astype(np.uint8)
    q[(q == 0).all(-1)] = 1
    tile[..., :3] = q
    tile[..., 3] = np.where(stp[near], 255, 0)
    tile[~any_w | zero[near]] = 0
    img[v0 * S:(v0 + h) * S, u0 * S:(u0 + w) * S] = tile
    return img


_CACHE = {}


def apply(img, row, path=REP):
    """Overwrite the ring's tiles in the HD sheet img (PSX convention, 8-bit sheet x8) with the smooth ring in row's colours."""
    if path not in _CACHE:
        _CACHE[path] = weights(path)[:2]
    W, places = _CACHE[path]
    rgb = np.array([psx_to_rgba(int(c))[:3] for c in row], np.float32)
    rgb[np.array([int(c) == 0 for c in row])] = 0
    col = W @ rgb
    for u0, v0, w, h, base in places:
        c = col[base:base + w * h * S * S].reshape(h * S, w * S, 3)
        q = np.clip(c + 0.5, 0, 255).astype(np.uint8)
        dark = (q < 2).all(-1)                           # adds nothing: transparent
        tile = np.zeros((h * S, w * S, 4), np.uint8)
        tile[..., :3] = q
        tile[..., 3] = 255
        tile[dark] = 0
        img[v0 * S:(v0 + h) * S, u0 * S:(u0 + w) * S] = tile
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    W, places, scr = weights()
    np.save(os.path.join(OUT, 'screen_right_turned.npy'), scr)
    print('ring tiles', len(places), 'HD pixels', W.shape[0])


if __name__ == '__main__':
    main()
