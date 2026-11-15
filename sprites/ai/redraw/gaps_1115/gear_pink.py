r"""Pink/violet fringe in the HD of field gear sets (15.11.2026; Emeralda's Crescens, F6 2026-11-15T19-08-13-690).

  python ai\redraw\gaps_1115\gear_pink.py scan [<gear folder> ...]     count per part, all extracted/disc1_full/gear*
  python ai\redraw\gaps_1115\gear_pink.py fix <gear folder> [--frame K] fixed files + preview in pinkfix\<gear>\ (pack NOT written)
The renders were drawn on a magenta background; where the HD silhouette is wider than the sprite's, or a thin gap of the
sprite was filled, the background stays as a pink line next to wings and edges (shot.png has it, shot_plain.png not).
A pixel is fringe when it is pinkish (magenta-like hue, see pinkish()) and the original texel under it is transparent
or a colour that is not pinkish itself. Fix: such pixels take the nearest non-fringe opaque HD colour of the same part
when the texel under them is opaque, and become transparent (0,0,0,0) when it is transparent.
"""
import json
import zlib
import os
import sys

import cv2
import numpy as np
from PIL import Image

from gcommon import HERE, PACK, ROOT, hd, side_by_side
from alias_dump_parts import read_bc7_level0  # noqa: E402

GEARS = os.path.join(ROOT, 'extracted', 'disc1_full')
S = 8


def pinkish(rgb):
    """Magenta to violet (the render's background mixed into an edge): red and blue both well over green."""
    r, g, b = (rgb[..., k].astype(int) for k in range(3))
    return (r - g > 35) & (b - g > 35) & (r > 90) & (b > 90)


HUE_FAR = 45


def hue(rgb):
    """Hue in degrees (0..360) of an RGB array."""
    return cv2.cvtColor(np.ascontiguousarray(rgb).astype(np.uint8), cv2.COLOR_RGB2HSV_FULL)[..., 0].astype(float) * 360 / 256


def hue_dist(a, b):
    d = np.abs(a - b) % 360
    return np.minimum(d, 360 - d)


def part_png(gdir, name):
    p = os.path.join(gdir, 'parts', name + '.png')
    return np.asarray(Image.open(p).convert('RGBA')) if os.path.exists(p) else None


def fringe(h, orig):
    """Mask of fringe pixels of an HD part (PSX convention) against its original part (RGBA, alpha 0/255)."""
    H, W = h.shape[:2]
    if orig is None or H % orig.shape[0] or W % orig.shape[1]:
        return None, None
    k = H // orig.shape[0]
    o = np.repeat(np.repeat(orig, k, 0), k, 1)
    opaque = ~(h == 0).all(-1)
    pk = pinkish(h[..., :3]) & opaque
    o_op = o[..., 3] > 0
    o_pink = pinkish(o[..., :3]) & o_op
    # 16.11: a red gear (gear445) shades its red toward pink inside the silhouette - that is the drawing, not the
    # background. Inside the original's opaque texels a pixel counts only when its hue is far (> HUE_FAR deg) from
    # the texel's and nearer to magenta than the texel's; outside them every pinkish pixel is background.
    hh, oh = hue(h[..., :3]), hue(o[..., :3])
    far = (hue_dist(hh, oh) > HUE_FAR) & (hue_dist(hh, 300) < hue_dist(oh, 300))
    return pk & ~o_pink & (~o_op | far), o_op


def fix_part(h, mask, o_opaque, orig):
    """Fringe pixels take the colour of the nearest opaque original texel when one lies within REACH texels (thin lines
    of the sprite stay whole: the render drew them a little off the texels), else they become transparent."""
    out = h.copy()
    k = h.shape[0] // orig.shape[0]
    big = np.repeat(np.repeat(orig, k, 0), k, 1)
    dist, lab = cv2.distanceTransformWithLabels((~o_opaque).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(o_opaque)
    if len(ys):
        src = np.zeros(lab.max() + 1, np.int64)
        src[lab[o_opaque]] = np.arange(len(ys))
        near = mask & (dist <= REACH * k)
        j = src[lab[near]]
        out[near, :3] = big[ys[j], xs[j], :3]
        out[near, 3] = 0                                     # PSX convention: (rgb, 0) = opaque
        out[near & (out[..., :3] == 0).all(-1), 0] = 1   # opaque black must not read as transparent
        mask = mask & ~near
    out[mask] = 0
    return out


REACH = 1.0


def gear_parts(gdir):
    lay = json.load(open(os.path.join(gdir, 'layout.json')))
    out = set()
    for s in lay.values():
        for f in s['frames']:
            for p in f:
                if p['block'] != '0':
                    out.add(f"{p['block']}-{s['palettes'][min(p['clut'], len(s['palettes']) - 1)]}")
    return sorted(out)


def scan(gears):
    for g in gears:
        gdir = os.path.join(GEARS, g)
        n_parts, hit, px = 0, [], 0
        for name in gear_parts(gdir):
            h = hd(name)
            if h is None:
                continue
            n_parts += 1
            m, _ = fringe(h, part_png(gdir, name))
            if m is not None and m.sum() >= 4:
                hit.append((name, int(m.sum())))
                px += int(m.sum())
        print(f'{g}: parts with HD {n_parts}, with a pink fringe (>=4 px) {len(hit)}, pixels {px}', flush=True)
        json.dump(hit, open(os.path.join(HERE, 'pinkfix', f'scan_{g}.json'), 'w'))


def frame_pic(gdir, setkey, fi, files):
    lay = json.load(open(os.path.join(gdir, 'layout.json')))[setkey]
    pl = []
    for p in lay['frames'][fi]:
        if p['block'] == '0':
            continue
        name = f"{p['block']}-{lay['palettes'][min(p['clut'], len(lay['palettes']) - 1)]}"
        o = part_png(gdir, name)
        pl.append((name, o, p['dx'] + p['mx'], p['dy'] + p['my'], p['flipx'], p['flipy']))
    x0, y0 = min(q[2] for q in pl), min(q[3] for q in pl)
    W = max(q[2] + q[1].shape[1] for q in pl) - x0
    Hh = max(q[3] + q[1].shape[0] for q in pl) - y0
    pics = []
    for src in ('orig',) + tuple(files):
        out = np.zeros((Hh * S, W * S, 3), np.uint8)
        out[:] = (40, 40, 40)
        for name, o, x, y, fx, fy in reversed(pl):
            if src == 'orig':
                a = np.repeat(np.repeat(o, S, 0), S, 1)
                rgb, m = a[..., :3], a[..., 3] > 0
            else:
                h = src(name)
                if h is None or h.shape[0] != o.shape[0] * S:
                    a = np.repeat(np.repeat(o, S, 0), S, 1)
                    rgb, m = a[..., :3], a[..., 3] > 0
                else:
                    rgb, m = h[..., :3], ~(h == 0).all(-1)
            if fx:
                rgb, m = rgb[:, ::-1], m[:, ::-1]
            if fy:
                rgb, m = rgb[::-1], m[::-1]
            X, Y = (x - x0) * S, (y - y0) * S
            out[Y:Y + rgb.shape[0], X:X + rgb.shape[1]][m] = rgb[m]
        pics.append(out)
    return pics


def fix(g, frames):
    gdir = os.path.join(GEARS, g)
    od = os.path.join(HERE, 'pinkfix', g)
    os.makedirs(od, exist_ok=True)
    from npc_rects import write_bc7          # PSX convention in, as read_bc7_level0 gives it
    from gear_redraw import block_bytes
    raw = block_bytes(os.path.join(gdir, 'index.csv'))
    fixed, files = {}, []
    for name in gear_parts(gdir):
        h = hd(name)
        if h is None:
            continue
        o = part_png(gdir, name)
        m, oo = fringe(h, o)
        if m is None or m.sum() < 4:
            continue
        f = fix_part(h, m, oo, o)
        fixed[name] = f
        targets = [(name, f)]
        # the pack also has each block's h-1 name (gear_redraw install): the same picture less its last texel row
        if name in raw and raw[name][1] > 1:
            w, hh, b = raw[name]
            alias = '%x-%s' % (zlib.crc32(b[:(w // 2) * (hh - 1)]) & 0xffffffff, name.split('-')[1])
            if hd(alias) is not None:
                targets.append((alias, f[:(hh - 1) * S]))
        for tn, img in targets:
            if write_bc7(os.path.join(od, tn + '.bc7'), np.ascontiguousarray(img)):
                files.append(tn)
            else:
                print(tn, 'BC7 failed')
    json.dump({'parts': sorted(fixed), 'files': sorted(files)}, open(os.path.join(od, 'fixed_names.json'), 'w'), indent=0)
    with open(os.path.join(od, 'files_to_overwrite.txt'), 'w') as f:
        f.writelines(n + '.bc7\n' for n in sorted(files))
    lay = json.load(open(os.path.join(gdir, 'layout.json')))
    setkey = next(iter(lay))
    if not frames:      # the frames that show the most fixed parts
        pal = lay[setkey]['palettes']
        score = [sum(f"{p['block']}-{pal[min(p['clut'], len(pal) - 1)]}" in fixed for p in fr) for fr in lay[setkey]['frames']]
        frames = sorted(range(len(score)), key=lambda i: -score[i])[:3]
    cells = []
    for fi in frames:
        o, before, after = frame_pic(gdir, setkey, fi, (hd, lambda n: fixed.get(n, hd(n))))
        cells += [o, before, after]
    side_by_side(cells).save(os.path.join(od, 'preview.png'))
    print(f'{g}: {len(fixed)} parts fixed, {len(files)} files with the h-1 names -> {od} (fixed_names.json, preview.png: original / pack now / fixed)')


def main():
    os.makedirs(os.path.join(HERE, 'pinkfix'), exist_ok=True)
    if sys.argv[1] == 'scan':
        scan(sys.argv[2:] or sorted(d for d in os.listdir(GEARS) if d.startswith('gear') or d == 'weltall'))
    else:
        frames = [int(x) for x in sys.argv[sys.argv.index('--frame') + 1].split(',')] if '--frame' in sys.argv else []
        for g in sys.argv[2:]:
            if not g.startswith('--') and not g[0].isdigit():
                fix(g, frames)


if __name__ == '__main__':
    main()
