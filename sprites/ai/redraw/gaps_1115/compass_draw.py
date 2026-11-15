r"""The field compass in HD, drawn by program from the original's own texels (16.11.2026; user: «компас перерисовать
было бы здорово»). No pod, no model.

  python ai\redraw\gaps_1115\compass_draw.py             stage\ (all palette names) + previews in compass\
  python ai\redraw\gaps_1115\compass_draw.py --install   the staged files that neither pack has -> both packs
Pictures (field system images, disc file 589 = directory 4 file 0xA7; sysimg.py):
  913fcf    the dial, 64x64 8-bit, drawn as 4x4 quads (Weltall FieldCompass.h, DialQuads 16).
  6bdfe265  the shadow under it, a 32x32 4-bit quarter disc drawn four times mirrored, semi-transparent subtractive.
Geometry: the dial is rings around the texel centre (31.5, 31.5) and eight spokes (4 cardinal lines, 4 diagonal ticks).
Each HD pixel takes its colour from the original measured in polar terms: rings by a radial profile (median over all
texels away from the spokes, 0.5-texel radius bins, linear between bins: the staircase of the pixel circles goes, the
radii stay), spokes by a table over (radius bin, distance from the spoke's axis) of the texels near that spoke (each of
the eight spokes its own: the light/dark sides and the gaps stay where the original has them). Colours are the
original palette's (blue ring: the 16-step ramp by shade; greys: the grey values). Every opaque texel of both pictures
has the STP bit: HD pixels are (rgb, 255) (semi), transparent = (0,0,0,0), so blending and subtraction stay as in the
game. Scale 8 as the pack's field UI (the compass letters c267c54e, the cursors ee1cef1b are 8x).
Palettes (Weltall FieldCompassPalette): the game copies the dial's 16 colours to its 8 directions and blacks out
(0x0000 = transparent) the directions the camera may not turn to: 256 masks; the sweeps of all maps saw 16 of them
(names in NAMES_SEEN), all 256 are written (one drawing; a pixel of a blacked direction is transparent). The
direction of a blue pixel is its sector by angle, as the original's index blocks lie (checked against them: agree).
Written names: compass\installed.txt (undo: delete them from both packs).
"""
import argparse
import os
import zlib

import numpy as np
from PIL import Image

from gcommon import HERE, install_files, side_by_side
from npc_rects import write_bc7
from render_frames import psx_to_rgba
from sysimg import images

S = 8          # HD pixels per texel
SS = 4         # supersampling per HD pixel
C = 31.5
OUT = os.path.join(HERE, 'compass')
STAGE = os.path.join(OUT, 'stage')
NAMES_SEEN = ('20165069 2edc8643 4c1a8fff 71891e47 76f3314c 8ade0b2b 944b278d ad79d9c1 aff94b6b c02ed402 c48fbbf6 '
              'cc649082 e8180297 f68d2e31 f847f81b fe660545').split()


def pal_rgb(row):
    return np.array([psx_to_rgba(int(c))[:3] for c in row], np.float32)


def texel_polar(n):
    ys, xs = np.mgrid[0:n, 0:n]
    dx, dy = xs + 0.5 - C, ys + 0.5 - C
    return np.hypot(dx, dy), np.arctan2(dy, dx)


def spoke_frame(r, th):
    """Nearest spoke k (0..7, angle k*45 deg, y down) and the signed distance from its axis (texels)."""
    k = np.round(th / (np.pi / 4)).astype(int) % 8
    d = th - k * (np.pi / 4)
    d = (d + np.pi) % (2 * np.pi) - np.pi
    return k, r * np.sin(d), r * np.cos(d)


def sector(th):
    """Direction block of the blue ring by angle: k = floor((theta + 90 deg) / 45 deg) mod 8 (top-right = 0)."""
    return (np.floor((np.degrees(th) + 90) / 45).astype(int)) % 8


def measure(idx, rgb):
    """Ring profile and spoke tables from the original's texels."""
    n = idx.shape[0]
    r, th = texel_polar(n)
    k, p, along = spoke_frame(r, th)
    opaque = idx > 0
    blue = opaque & (idx < 128)
    shade = np.where(blue, idx % 16, 0).astype(np.float32)
    near = np.abs(p) < 2.5
    ring = {}
    for b in np.arange(0, 33, 0.5):
        m = (r >= b) & (r < b + 0.5) & ~near
        if m.sum() < 4:
            continue
        op = opaque[m].mean()
        bl = blue[m].mean()
        ring[b + 0.25] = {'op': op, 'blue': bl, 'shade': float(np.median(shade[m & blue])) if (m & blue).any() else 0,
                          'grey': np.median(rgb[m & opaque & ~blue], axis=0) if (m & opaque & ~blue).any() else None}
    return ring


SQ2 = np.sqrt(2.0)


def lattice(k, dx, dy):
    """Spoke k's lattice coordinates of offsets (dx, dy) from the centre: (u, v) integer at texel centres.
    Cardinal spokes: u = along, v = across. Diagonal: u = A = along*sqrt2, v = P = across*sqrt2, integers of equal
    parity (a row of constant P is a line parallel to the spoke; its points lie 2 apart in A)."""
    a = k * np.pi / 4
    along = dx * np.cos(a) + dy * np.sin(a)
    across = -dx * np.sin(a) + dy * np.cos(a)
    if k % 2 == 0:
        return along, across, along, across
    return along * SQ2, across * SQ2, along, across


def spoke_features(idx, rgb, ring, prgb):
    """Per spoke: {(u, v): (colour, opaque, blue)} of the texels near its axis that the ring profile does not
    explain (the lines, their dark sides, the gaps)."""
    n = idx.shape[0]
    r, th = texel_polar(n)
    op_p, bl_p, bcol, gcol = ring_value(ring, r, prgb)
    pred = np.where((bl_p > 0.5)[..., None], bcol, gcol)
    opaque = idx > 0
    blue = opaque & (idx < 128)
    ys, xs = np.mgrid[0:n, 0:n]
    dx, dy = xs + 0.5 - C, ys + 0.5 - C
    k, p, along = spoke_frame(r, th)
    feat = (opaque != (op_p > 0.5)) | (opaque & (np.abs(rgb - pred).max(-1) > 45))
    out = {kk: {} for kk in range(8)}
    for y, x in zip(*np.nonzero((np.abs(p) < 2.6) & (along > 0))):
        kk = int(k[y, x])
        u, v, _, _ = lattice(kk, dx[y, x], dy[y, x])
        out[kk][(int(round(u)), int(round(v)))] = (bool(feat[y, x]), rgb[y, x], bool(opaque[y, x]), bool(blue[y, x]))
    return out


def ring_value(ring, rr, prgb):
    """Opacity, blue share and colour of the rings at radii rr (array), linear between bin centres."""
    cs = np.array(sorted(ring))
    op = np.interp(rr, cs, [ring[c]['op'] for c in cs], left=0, right=0)
    bl = np.interp(rr, cs, [ring[c]['blue'] for c in cs], left=0, right=0)
    sh = np.interp(rr, cs, [ring[c]['shade'] if ring[c]['blue'] > 0.5 else np.nan for c in cs])
    # shade only inside the blue band: fill its ends with the nearest blue bin
    blue_cs = [c for c in cs if ring[c]['blue'] > 0.5]
    sh = np.interp(rr, blue_cs, [ring[c]['shade'] for c in blue_cs])
    sh = np.clip(sh, 1, 15)
    lo = np.floor(sh).astype(int)
    hi = np.minimum(lo + 1, 15)
    t = (sh - lo)[..., None]
    bcol = prgb[lo] * (1 - t) + prgb[hi] * t
    grey_cs = [c for c in cs if ring[c]['grey'] is not None and ring[c]['blue'] < 0.5]
    gcol = np.stack([np.interp(rr, grey_cs, [ring[c]['grey'][j] for c in grey_cs]) for j in range(3)], -1)
    return op, bl, bcol, gcol


def draw_dial(idx, row):
    prgb = pal_rgb(row)
    rgb = prgb[idx]
    ring = measure(idx, rgb)
    feats = spoke_features(idx, rgb, ring, prgb)
    n = idx.shape[0]
    N = n * S * SS
    ys, xs = np.mgrid[0:N, 0:N]
    X, Y = (xs + 0.5) / (S * SS), (ys + 0.5) / (S * SS)
    dx, dy = X - C, Y - C
    r, th = np.hypot(dx, dy), np.arctan2(dy, dx)
    op, bl, bcol, gcol = ring_value(ring, r, prgb)
    col = np.where((bl > 0.5)[..., None], bcol, gcol)
    blue = bl > 0.5
    # spokes: the features of each spoke's lattice, bilinear; a pixel is the feature where their weight >= 0.5
    k, p, along = spoke_frame(r, th)
    near = (np.abs(p) < 2.6) & (along > 0)
    F = np.zeros(r.shape, np.float32)
    fcol = np.zeros(r.shape + (3,), np.float32)
    fop = np.zeros(r.shape, np.float32)
    fbl = np.zeros(r.shape, np.float32)
    for kk in range(8):
        m = near & (k == kk)
        u, v, _, _ = lattice(kk, dx[m], dy[m])
        acc_f = np.zeros(u.shape, np.float32)
        acc_c = np.zeros(u.shape + (3,), np.float32)
        acc_o = np.zeros(u.shape, np.float32)
        acc_b = np.zeros(u.shape, np.float32)
        table = feats[kk]
        v0 = np.floor(v).astype(int)
        tv = v - v0
        for dv in (0, 1):
            vi = v0 + dv
            wv = tv if dv else 1 - tv
            step = 2 if kk % 2 else 1
            # points of this row: u of the row's parity (diagonals) or every integer (cardinals)
            ulo = np.floor(u).astype(int)
            if step == 2:
                ulo = ulo - ((ulo - vi) % 2)
            tu = (u - ulo) / step
            for du in (0, 1):
                w = wv * (tu if du else 1 - tu)
                vals = [table.get(q) for q in zip((ulo + du * step).tolist(), vi.tolist())]
                f = np.array([1.0 if (q and q[0]) else 0.0 for q in vals], np.float32) * w
                acc_f += f
                acc_c += f[:, None] * np.array([q[1] if q else (0, 0, 0) for q in vals], np.float32)
                acc_o += f * np.array([q[2] if q else 0 for q in vals], np.float32)
                acc_b += f * np.array([q[3] if q else 0 for q in vals], np.float32)
        F[m] = acc_f
        den = np.maximum(acc_f, 1e-6)
        fcol[m] = acc_c / den[:, None]
        fop[m] = acc_o / den
        fbl[m] = acc_b / den
    sm = np.clip((F - 0.35) / 0.3, 0, 1)
    use = F >= 0.5
    col = col * (1 - sm[..., None]) + fcol * sm[..., None]
    op = np.where(use, fop, op)
    bl = np.where(use, fbl, bl)
    blue = bl > 0.5
    # supersampled -> HD: colour = mean over the opaque samples, opaque when most samples are
    f = S * SS // S
    o = (op > 0.5).astype(np.float32)
    o4 = o.reshape(n * S, SS, n * S, SS).mean(axis=(1, 3))
    c4 = (col * o[..., None]).reshape(n * S, SS, n * S, SS, 3).sum(axis=(1, 3)) / np.maximum(
        o.reshape(n * S, SS, n * S, SS).sum(axis=(1, 3)), 1)[..., None]
    b4 = (blue & (o > 0)).reshape(n * S, SS, n * S, SS).mean(axis=(1, 3)) > 0.25
    sec = sector(th)[::SS, ::SS] if False else sector(np.arctan2(
        (np.arange(n * S)[:, None] + 0.5) / S - C, (np.arange(n * S)[None, :] + 0.5) / S - C))
    opaque = o4 >= 0.5
    del f
    return c4, opaque, b4, sec


def draw_shadow(idx, row):
    """Quarter disc around the corner (32, 32): its index rises inward; a smooth ramp by radius, edge where the
    original's opaque texels end (measured radius)."""
    prgb = pal_rgb(row)
    n = idx.shape[0]
    ys, xs = np.mgrid[0:n, 0:n]
    r = np.hypot(xs + 0.5 - n, ys + 0.5 - n)
    bins = {}
    for b in np.arange(0, 48, 0.5):
        m = (r >= b) & (r < b + 0.5)
        if m.any():
            bins[b + 0.25] = (float((idx[m] > 0).mean()), float(np.mean(idx[m][idx[m] > 0])) if (idx[m] > 0).any() else 0)
    cs = np.array(sorted(bins))
    N = n * S * SS
    yy, xx = np.mgrid[0:N, 0:N]
    R = np.hypot((xx + 0.5) / (S * SS) - n, (yy + 0.5) / (S * SS) - n)
    op = np.interp(R, cs, [bins[c][0] for c in cs], left=1, right=0)
    good = [c for c in cs if bins[c][0] > 0.5]
    lv = np.clip(np.interp(R, good, [bins[c][1] for c in good]), 1, 15)
    lo = np.floor(lv).astype(int)
    hi = np.minimum(lo + 1, 15)
    t = (lv - lo)[..., None]
    col = prgb[lo] * (1 - t) + prgb[hi] * t
    o = (op > 0.5).astype(np.float32)
    o4 = o.reshape(n * S, SS, n * S, SS).mean(axis=(1, 3))
    c4 = (col * o[..., None]).reshape(n * S, SS, n * S, SS, 3).sum(axis=(1, 3)) / np.maximum(
        o.reshape(n * S, SS, n * S, SS).sum(axis=(1, 3)), 1)[..., None]
    return c4, o4 >= 0.5


def psx(c, opaque):
    out = np.zeros(c.shape[:2] + (4,), np.uint8)
    rgb = np.clip(c + 0.5, 0, 255).astype(np.uint8)
    rgb[(rgb == 0).all(-1)] = 1
    out[..., :3] = rgb
    out[..., 3] = 255                     # every opaque texel of both pictures has the STP bit: semi
    out[~opaque] = 0
    return out


def palette_masks(row):
    """{name: mask of blacked directions} for all 256 masks (Weltall FieldCompassPalette)."""
    base = row.astype('<u2').copy()
    out = {}
    for mask in range(256):
        p = base.copy()
        for k in range(8):
            p[k * 16:k * 16 + 16] = 0 if mask >> k & 1 else base[:16]
        out[f'{zlib.crc32(p.tobytes()) & 0xffffffff:x}'] = mask
    return out


def check(hdimg, opaque, idx, rgb_orig):
    """HD brought back to texels against the original: transparency agreement, mean colour difference."""
    n = idx.shape[0]
    o = opaque.reshape(n, S, n, S).mean(axis=(1, 3)) >= 0.5
    c = hdimg[..., :3].astype(float).reshape(n, S, n, S, 3).mean(axis=(1, 3))
    agree = (o == (idx > 0)).mean()
    both = o & (idx > 0)
    diff = np.abs(c[both] - rgb_orig[both]).mean()
    return agree, diff


def nearest(idx, rgb, k):
    out = np.zeros(idx.shape + (3,), np.uint8)
    out[:] = (255, 0, 255)
    out[idx > 0] = rgb[idx > 0].astype(np.uint8)
    return np.repeat(np.repeat(out, k, 0), k, 1)


def view(p):
    out = np.zeros(p.shape[:2] + (3,), np.uint8)
    out[:] = (255, 0, 255)
    m = ~(p == 0).all(-1)
    out[m] = p[..., :3][m]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', action='store_true')
    a = ap.parse_args()
    os.makedirs(STAGE, exist_ok=True)
    ims = {im['name']: im for im in images()}
    dial, shad = ims['913fcf'], ims['6bdfe265']
    row = dial['clut'][0][:256]
    prgb = pal_rgb(row)
    c, opaque, blue, sec = draw_dial(dial['idx'].astype(int), row)
    base = psx(c, opaque)
    agree, diff = check(base, opaque, dial['idx'], prgb[dial['idx']])
    idx = dial['idx'].astype(int)
    blk = np.where((idx > 0) & (idx < 128), idx // 16, -1)
    sec_t = sec[S // 2::S, S // 2::S]
    sec_agree = (sec_t[blk >= 0] == blk[blk >= 0]).mean()
    print(f'dial: texel transparency agreement {agree:.3f}, mean colour difference {diff:.1f}, sectors agree {sec_agree:.3f}')
    masks = palette_masks(row)
    seen = [n for n in NAMES_SEEN if n not in masks]
    if seen:
        raise SystemExit(f'names not produced: {seen}')
    names = []
    for name, mask in masks.items():
        img = base.copy()
        for k in range(8):
            if mask >> k & 1:
                img[blue & (sec == k)] = 0
        fn = f'913fcf-{name}'
        if not write_bc7(os.path.join(STAGE, fn + '.bc7'), np.ascontiguousarray(img)):
            raise SystemExit(f'{fn}: BC7 failed')
        names.append(fn)
        if name in ('20165069', 'c48fbbf6', 'f847f81b'):
            Image.fromarray(view(img)).save(os.path.join(OUT, f'dial_{name}.png'))
    srow = shad['clut'][0][:16]
    sc, sop = draw_shadow(shad['idx'].astype(int), srow)
    simg = psx(sc, sop)
    sagree, sdiff = check(simg, sop, shad['idx'], pal_rgb(srow)[shad['idx']])
    print(f'shadow: texel transparency agreement {sagree:.3f}, mean colour difference {sdiff:.1f}')
    if not write_bc7(os.path.join(STAGE, '6bdfe265-31f23b8f.bc7'), np.ascontiguousarray(simg)):
        raise SystemExit('shadow: BC7 failed')
    names.append('6bdfe265-31f23b8f')
    # previews: original x8 / xBR candidate (sysimg\cand, if made) / new
    cells = [nearest(idx, prgb[idx], S)]
    cand = os.path.join(HERE, 'sysimg', 'cand', '913fcf-20165069.bc7')
    if os.path.exists(cand):
        from alias_dump_parts import read_bc7_level0
        cells.append(view(read_bc7_level0(cand)))
    cells.append(view(base))
    side_by_side(cells).save(os.path.join(OUT, 'dial_compare.png'))
    sidx = shad['idx'].astype(int)
    scells = [nearest(sidx, pal_rgb(srow)[sidx], S), view(simg)]
    side_by_side(scells).save(os.path.join(OUT, 'shadow_compare.png'))
    z = slice(0, 160)
    side_by_side([c_[z, z] for c_ in cells]).save(os.path.join(OUT, 'dial_zoom.png'))
    open(os.path.join(OUT, 'names.txt'), 'w').write('\n'.join(names) + '\n')
    print(f'{len(names)} files staged in {STAGE}')
    if a.install:
        done = install_files(STAGE, names, os.path.join(OUT, 'installed.txt'))
        print(f'installed {len(done)} new names (both packs); compass\\installed.txt')


if __name__ == '__main__':
    main()
