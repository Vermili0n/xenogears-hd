r"""Gear battle HUD (item 13, 16.11.2026): the HUD sheet 49b52d64 redrawn by program for the palettes the pack lacks.

  python ai\redraw\gaps_1115\hud_draw.py            stage\ + sheets in hud\
  python ai\redraw\gaps_1115\hud_draw.py --install  the staged names neither pack has -> both packs (hud\installed.txt)
The sheet: battle data file (directory 12 file 3 = disc file 2614), section 2, the 64x204-unit image (crc 49b52d64,
hud\upload_words.npy). The texels' palette indices are redrawn x8 (labels()): 1-texel strokes (the fonts, ticks,
lines) as round-capped strokes of constant width between texel centres; solid shapes by their index masks interpolated
between texel centres (a staircase becomes its straight line), crisp borders between colours. For the green text's
palette (RIMS) a solid's darker texels are its anti-aliasing: coverage of the solid's main colour (flat fill, smooth
edge). A pixel's colour is always a palette colour (or a mix of two at a border), its STP bit is its index's (semi /
opaque as the original texel), colour 0x0000 is transparent. The 8-bit (animated) palettes share one drawing: a state
is a palette lookup, not a new drawing.
Palettes (hud_names.txt of xeno_port\out\fix_1115\H; CLUT rows from vram_cockpit.0):
  4-bit: 2d9e64ad (green text), ab5adc12 (frame, ruler), 34bbffe0 (backings), 801b56d1 (gauge frames), cc37b45
         (windows), 2083ded8 (scroll ticks), 6d417fc4 (cursor), 3137fd29? (walking vertical gauge - 8-bit, below)
  8-bit, animated rows 508 (reticle) and 511 (vertical gauge): Weltall FBattleHud::AnimateMenuTextures re-uploads x 1..198
         of each row shifted by 8 units every second frame (offset 0..196 step 4, x2): the states are the row turned
         by even steps; every even turn (99) is written so no state is missed; the names seen in the reports must be
         among them (checked).
"""
import argparse
import os
import shutil
import time
import zlib

import cv2
import numpy as np
from PIL import Image

from gcommon import HERE, MOD_PACK, PACK, install_files, side_by_side
from hud_common import clut, idx4, idx8, vram
from npc_rects import write_bc7
from ring_draw import apply as ring_apply, apply_gauge
from render_frames import psx_to_rgba

S = 8
SOFT = 0.15
STROKE = 0.9
RIM_DARK = 0.7
EDGE = 4.0
RIMS = {'2d9e64ad'}       # palettes whose solids are anti-aliased by darker indices (the large digits, the infinity)
OUT = os.path.join(HERE, 'hud')
STAGE = os.path.join(OUT, 'stage')
CLUTS4 = {(144, 498): '2d9e64ad', (96, 498): 'ab5adc12', (96, 497): '34bbffe0', (144, 497): '801b56d1',
          (80, 497): 'cc37b45', (176, 498): '2083ded8', (160, 497): '6d417fc4'}
ROWS8 = {508: ['60d6b3cc', '7baaee8b', 'cc9df8b0', '87d0bf96', '27035b63', 'af73c8f7', 'a420b1a6', 'a097d7e0'],
         511: ['ce937dad', 'a9be1bd7', 'ffa5fe1e', '33b1cc44', '28de20d8', '281e0fbb', 'b747dc32']}


def crc(a):
    return f'{zlib.crc32(np.ascontiguousarray(a).astype("<u2").tobytes()) & 0xffffffff:x}'


def labels(idx, n_labels, pal=None, rims=False):
    """x8 label map of an index image: (l1, l2, w1, opaque) per HD pixel.
    Components of the opaque texels with no texel whose 4 neighbours are all opaque are STROKES (the small fonts, ticks,
    1-texel lines): drawn as round-capped segments of constant width STROKE between the centres of neighbouring texels
    (4-neighbours; a diagonal only where no 4-neighbour joins the two), each texel's own index along it.
    The rest (shapes, filled bars, the large anti-aliased digits, the reticle's rings) is SOLID: each index's mask is
    interpolated bilinearly between texel centres (a staircase turns into its straight line) and softened by SOFT texels;
    a pixel is opaque where the masks' sum >= 0.5, takes the strongest index and blends to the second."""
    H, W = idx.shape
    opq_t = idx > 0
    if pal is not None:     # a colour 0x0000 is transparent too (the backings' palette has one colour)
        opq_t &= np.array([int(c) != 0 for c in pal])[idx]
    core = cv2.erode(opq_t.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    # a texel is SOLID when it is a core texel (all 8 neighbours opaque) or touches one; the rest are strokes
    solid_t = opq_t & (cv2.dilate(core.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    n, comp = cv2.connectedComponents(solid_t.astype(np.uint8), connectivity=8)
    stroke_t = opq_t & ~solid_t
    cov_t = solid_t.astype(np.float32)
    if pal is not None and rims:
        # anti-aliased rims (4-bit palettes): a solid texel next to a transparent one and darker than RIM_DARK of its
        # component's brightest colour is partial coverage of that colour, not a dark colour of its own
        lum = np.array([sum(psx_to_rgba(int(c))[:3]) for c in pal], np.float32)
        lt = lum[idx]
        cmax = np.zeros(n, np.float32)
        np.maximum.at(cmax, comp[solid_t], lt[solid_t])
        # every texel of such a solid: coverage = its brightness against the solid's brightest, colour = the
        # solid's brightest index (the most common among its texels >= 0.95 of the brightest): a flat fill, crisp edge
        idx = idx.copy()
        for c in range(1, n):
            m = comp == c
            if cmax[c] <= 0:
                continue
            bright = m & (lt >= 0.6 * cmax[c])
            target = np.bincount(idx[bright]).argmax()      # the colour most of the solid has (not the lightest:
            cov_t[m] = np.clip(lt[m] / max(lt[idx == target].max(), 1), 0, 1)  # a touching digit row is lighter)
            idx[m] = target
        # a lone dark texel off a solid is its anti-aliasing too, not a stroke (else: dark dots)
        touch = cv2.dilate(solid_t.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        stroke_t = stroke_t & ~(touch & (lt < 0.35 * lt.max()))

    def bil(m):
        up = cv2.resize(m.astype(np.float32), (W * S, H * S), interpolation=cv2.INTER_LINEAR)
        return cv2.GaussianBlur(up, (0, 0), SOFT * S) if SOFT > 0 else up

    best1 = np.zeros((H * S, W * S), np.int32)
    best2 = np.zeros((H * S, W * S), np.int32)
    w1 = np.full((H * S, W * S), -1.0, np.float32)
    w2 = np.full((H * S, W * S), -1.0, np.float32)
    opq = np.zeros((H * S, W * S), np.float32)
    for l in [l for l in range(1, n_labels) if ((idx == l) & solid_t).any()]:
        b = bil((idx == l) & solid_t)
        opq += b
        better = b > w1
        best2 = np.where(better, best1, np.where(b > w2, l, best2))
        w2 = np.where(better, w1, np.maximum(w2, b))
        best1 = np.where(better, l, best1)
        w1 = np.where(better, b, w1)
    tot = np.maximum(w1 + np.maximum(w2, 0), 1e-6)
    w = np.clip((w1 / tot - 0.5) * EDGE + 0.5, 0, 1)      # crisp borders between colours, ~1/EDGE texel of blend
    op = bil(cov_t) >= 0.5
    # strokes: distance to the segments between stroke texel centres
    dist = np.full((H * S, W * S), 1e9, np.float32)
    slab = np.zeros((H * S, W * S), np.int32)
    py, px = np.nonzero(stroke_t)
    segs = []
    sset = set(zip(py.tolist(), px.tolist()))
    for y, x in zip(py.tolist(), px.tolist()):
        segs.append((y, x, y, x))
        for dy, dx in ((0, 1), (1, 0)):
            if (y + dy, x + dx) in sset:
                segs.append((y, x, y + dy, x + dx))
        for dy, dx in ((1, 1), (1, -1)):
            if (y + dy, x + dx) in sset and (y + dy, x) not in sset and (y, x + dx) not in sset:
                segs.append((y, x, y + dy, x + dx))
    r = int(np.ceil((STROKE / 2 + 0.5) * S))
    for y0, x0, y1, x1 in segs:
        cy0, cx0, cy1, cx1 = (y0 + 0.5) * S, (x0 + 0.5) * S, (y1 + 0.5) * S, (x1 + 0.5) * S
        Y0, Y1 = max(0, int(min(cy0, cy1)) - r), min(H * S, int(max(cy0, cy1)) + r + 1)
        X0, X1 = max(0, int(min(cx0, cx1)) - r), min(W * S, int(max(cx0, cx1)) + r + 1)
        gy, gx = np.mgrid[Y0:Y1, X0:X1].astype(np.float32) + 0.5
        vy, vx = cy1 - cy0, cx1 - cx0
        L = vy * vy + vx * vx
        t = np.clip(((gy - cy0) * vy + (gx - cx0) * vx) / L, 0, 1) if L > 0 else np.zeros_like(gy)
        d = np.hypot(gy - (cy0 + t * vy), gx - (cx0 + t * vx)) / S
        lab = np.where(t < 0.5, idx[y0, x0], idx[y1, x1])
        sub = dist[Y0:Y1, X0:X1]
        closer = d < sub
        sub[closer] = d[closer]
        slab[Y0:Y1, X0:X1][closer] = lab[closer]
    stroke = dist <= STROKE / 2
    best1 = np.where(stroke, slab, best1)
    best2 = np.where(stroke, slab, best2)
    w = np.where(stroke, 1.0, w)
    op = op | stroke
    return best1, best2, w, op


def paint(lab, pal_words):
    """HD in the PSX convention: transparent (0,0,0,0); STP colour -> (rgb, 255) semi; else (rgb, 0)."""
    l1, l2, w, op = lab
    rgb = np.array([psx_to_rgba(int(c))[:3] for c in pal_words], np.float32)
    stp = np.array([(int(c) & 0x8000) != 0 for c in pal_words])
    zero = np.array([int(c) == 0 for c in pal_words])
    col = rgb[l1] * w[..., None] + rgb[l2] * (1 - w[..., None])
    out = np.zeros(l1.shape + (4,), np.uint8)
    c = np.clip(col + 0.5, 0, 255).astype(np.uint8)
    c[(c == 0).all(-1)] = 1
    out[..., :3] = c
    out[..., 3] = np.where(stp[l1], 255, 0)
    out[~op | zero[l1]] = 0
    return out


def rotations(row):
    """Every even turn of units 1..198 of a 256-unit CLUT row (the HUD's scrolling uploads), as {crc: row}."""
    out = {}
    body = row[1:199]
    for s in range(0, 198, 2):
        r = row.copy()
        r[1:199] = np.roll(body, -s)
        out[crc(r)] = r
    return out


def view(p):
    out = np.zeros(p.shape[:2] + (3,), np.uint8)
    out[:] = (40, 40, 40)
    m = ~(p == 0).all(-1)
    out[m] = p[..., :3][m]
    return out


def nearest(idx, pal_words):
    rgb = np.array([psx_to_rgba(int(c))[:3] for c in pal_words], np.uint8)
    o = np.zeros(idx.shape + (3,), np.uint8)
    o[:] = (40, 40, 40)
    m = (idx > 0) & (np.array([int(c) != 0 for c in pal_words])[idx])
    o[m] = rgb[idx][m]
    return np.repeat(np.repeat(o, S, 0), S, 1)


def refresh_own(names):
    r"""Our own files (hud\installed.txt) of the given names rewritten from stage\ in both packs; the files they replace
    are kept in hud\backup_<time>\{retroarch,mod} (undo: copy them back)."""
    own = {l.strip()[:-4] for l in open(os.path.join(OUT, 'installed.txt')) if l.strip()}
    todo = [n for n in names if n in own]
    bk = os.path.join(OUT, 'backup_' + time.strftime('%m%d_%H%M'))
    for sub in ('retroarch', 'mod'):
        os.makedirs(os.path.join(bk, sub), exist_ok=True)
    for n in todo:
        for root, sub in ((PACK, 'retroarch'), (MOD_PACK, 'mod')):
            dst = os.path.join(root, n + '.bc7')
            if os.path.exists(dst):
                shutil.copyfile(dst, os.path.join(bk, sub, n + '.bc7'))
            shutil.copyfile(os.path.join(STAGE, n + '.bc7'), dst)
    bad = [n for n in todo for root in (PACK, MOD_PACK)
           if open(os.path.join(root, n + '.bc7'), 'rb').read() != open(os.path.join(STAGE, n + '.bc7'), 'rb').read()]
    open(os.path.join(OUT, 'refreshed.txt'), 'a').write(''.join(n + '.bc7\n' for n in todo))
    print(f'rewrote {len(todo)} own files in both packs (backup {bk}); byte check: {len(bad)} differ')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', action='store_true')
    ap.add_argument('--refresh-own', action='store_true', help='rewrite our own installed files of rows 508/511 (16.11)')
    a = ap.parse_args()
    os.makedirs(STAGE, exist_ok=True)
    words = np.load(os.path.join(OUT, 'upload_words.npy'))
    up = crc(words)
    assert up == '49b52d64', up
    v = vram()
    names = []
    i4 = idx4(words)
    lab4s = {}
    for (x, y), want in CLUTS4.items():
        row = clut(v, x, y, 16)
        assert crc(row) == want, (x, y, crc(row), want)
        lab4s[(x, y)] = labels(i4, 16, row, want in RIMS)
        img = paint(lab4s[(x, y)], row)
        n = f'49b52d64-{want}'
        if not write_bc7(os.path.join(STAGE, n + '.bc7'), np.ascontiguousarray(img)):
            raise SystemExit(n + ': BC7 failed')
        names.append(n)
        np.save(os.path.join(OUT, f'paint_{want}.npy'), img[::1, ::1, :])
    i8 = idx8(words)
    lab8 = labels(i8, 256)
    for y, seen in ROWS8.items():
        rots = rotations(clut(v, 0, y, 256))
        missing = [s for s in seen if s not in rots]
        print(f'row {y}: {len(rots)} states; seen in reports {len(seen)}, not among the states: {missing}')
        if missing:
            continue
        for name, row in rots.items():
            img = paint(lab8, row)
            img = ring_apply(img, row) if y == 508 else apply_gauge(img, row)   # 16.11: smooth ring / ramp
            n = f'49b52d64-{name}'
            if not write_bc7(os.path.join(STAGE, n + '.bc7'), np.ascontiguousarray(img)):
                raise SystemExit(n + ': BC7 failed')
            names.append(n)
        np.save(os.path.join(OUT, f'paint_row{y}.npy'), paint(lab8, clut(v, 0, y, 256)))
    open(os.path.join(OUT, 'names.txt'), 'w').write('\n'.join(names) + '\n')
    print(len(names), 'files staged')
    # sheets: regions the cockpit draws, original x8 | new
    regions = {'font': (52, 76, 152, 256, (144, 498)), 'frame': (136, 165, 32, 256, (96, 498)),
               'backings': (112, 136, 200, 256, (96, 497)), 'gauge_frames': (195, 203, 0, 124, (144, 497))}
    for tag, (r0, r1, c0, c1, cl) in regions.items():
        row = clut(v, *cl, 16)
        o = nearest(i4, row)[r0 * S:r1 * S, c0 * S:c1 * S]
        n = view(paint(lab4s[cl], row))[r0 * S:r1 * S, c0 * S:c1 * S]
        Image.fromarray(np.vstack([o, np.full((8, o.shape[1], 3), 200, np.uint8), n])).save(os.path.join(OUT, f'sheet_{tag}.png'))
    row = clut(v, 0, 508, 256)
    o = nearest(i8, row)[104 * S:136 * S, 0:88 * S]
    n = view(paint(lab8, row))[104 * S:136 * S, 0:88 * S]
    side_by_side([o, n]).save(os.path.join(OUT, 'sheet_reticle.png'))
    if a.install:
        done = install_files(STAGE, names, os.path.join(OUT, 'installed.txt'))
        print('installed', len(done))
    if a.refresh_own:
        refresh_own([n for n in names if n.split('-')[1] in {c for r in (508, 511) for c in rotations(clut(v, 0, r, 256))}])


if __name__ == '__main__':
    main()
