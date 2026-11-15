"""Hero parts the game alters at upload time get our HD under the altered name too (30.10, Elly's hair).

Elly's field walk parts come from disc file 428, but the game sets a few transparent texels of some parts to a
semi-transparent hair colour before the VRAM upload, so the upload hash differs from the extracted part and Beetle
finds no HD (hair flickering pixel/HD while walking). The pixels are the same otherwise, so the HD file of the
extracted part is copied into the pack under the dumped name.

  python alias_dump_parts.py --hero elly [--dump <core texture dump dir>] [--dry]
For every dump file <hash>-<pal> with no HD in the pack and a palette of the hero: the extracted hero part of the same
size and palette with the fewest differing texels (opaque colours must match; at most --max-diff texels, default 5%)
-> copy its pack file (.bc7 / .png) as <hash>-<pal>. Log: pod/report/alias_dump_parts.log.
"""
import argparse
import csv
import json
import os
import shutil
import struct
import sys
import time
import zlib

import cv2
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402
PACK = r'<RETROARCH_DRIVE>\RetroArch\system\Xenogears (USA)-texture-replacements'
DUMP = r'<RETROARCH_DRIVE>\RetroArch\system\Xenogears (RUS)-texture-dump'
LOG = os.path.join(ROOT, 'pod', 'report', 'alias_dump_parts.log')


def log(s):
    s = time.strftime('%d.%m %H:%M ') + s
    print(s, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(s + '\n')


def rgba(path):
    return np.asarray(Image.open(path).convert('RGBA')).astype(np.int16)


def read_bc7_level0(path):
    raw = open(path, 'rb').read()
    _, _, w, h, _, flags, _, comp = struct.unpack('<4s7I', raw[:32])
    data = zlib.decompress(raw[32:]) if comp & 1 else raw[32:]
    return bc7pack.decode_level(data[:((w + 3) // 4) * ((h + 3) // 4) * 16], w, h)


_hd_cache = {}


def _hd_part(name):
    if name not in _hd_cache:
        _hd_cache[name] = read_bc7_level0(os.path.join(PACK, name)).astype(np.int16)
    return _hd_cache[name]


def frame_borrow(hero, block, hd, gap, pack, want=None, S=8):
    """Gap pixels of `block`'s HD taken from another frame of the same set: every frame is composed in HD, the
    rectangle where `block` sits in its own frame is cut out of it, and the frame that covers the whole gap and
    looks most like our piece elsewhere wins (walk frames move the hair a little, so a neighbouring frame has hair
    where the game's copy added it). Returns (pixels, frame id) or None."""
    lay = json.load(open(os.path.join(ROOT, 'extracted', 'disc1_full', hero, 'layout.json')))
    sizes = {r['name'].rsplit('-', 1)[0]: (int(r['w']), int(r['h']))
             for r in csv.DictReader(open(os.path.join(ROOT, 'extracted', 'disc1_full', hero, 'index.csv')))}
    if block not in sizes:
        return None
    bh, bw = hd.shape[:2]
    mine = ~(hd == 0).all(-1) & ~gap
    cands = []
    for key, v in lay.items():
        homes = [p for f in v['frames'] for p in f if p['block'] == block]
        if not homes:
            continue
        a = homes[0]                                   # where the piece sits in its own frames
        for fi, f in enumerate(v['frames']):
            canvas = np.zeros((bh, bw, 4), np.int16)
            for p in f:
                if p['block'] not in sizes:
                    continue
                pal = v['palettes'][min(p['clut'], len(v['palettes']) - 1)]
                name = pack.get(f"{p['block']}-{pal}")
                if not name or not name.endswith('.bc7'):
                    continue
                pw, ph = sizes[p['block']]
                ox, oy = (p['dx'] - a['dx']) * S, (p['dy'] - a['dy']) * S
                if ox >= bw or oy >= bh or ox + pw * S <= 0 or oy + ph * S <= 0:
                    continue
                im = _hd_part(name)
                if p['flipx']:
                    im = im[:, ::-1]
                if p['flipy']:
                    im = im[::-1]
                y0, x0 = max(0, oy), max(0, ox)
                y1, x1 = min(bh, oy + im.shape[0]), min(bw, ox + im.shape[1])
                src = im[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
                m = ~(src == 0).all(-1)
                canvas[y0:y1, x0:x1][m] = src[m]
            c_op = ~(canvas == 0).all(-1)
            both = mine & c_op
            if both.sum() < mine.sum() * 0.5 or not c_op[gap].any():
                continue
            diff = float(np.abs(canvas[..., :3] - hd[..., :3])[both].mean())
            cands.append((float(c_op[gap].mean()), diff, canvas, f'{key}:{fi}'))
    if not cands:
        return None
    # most gap first, then most alike; up to 3 frames fill what the previous ones left
    cands.sort(key=lambda c: (-round(c[0], 2), c[1]))
    out = np.zeros_like(hd)
    left = gap.copy()
    used = []
    for cov, diff, canvas, fid in cands[:6]:
        take = left & ~(canvas == 0).all(-1)
        if want is not None:   # per texel: only where the frame shows what the game draws there (hair, not a sleeve)
            ok = np.zeros_like(take)
            for (ty, tx), ref in want.items():
                blk = (slice(ty * S, (ty + 1) * S), slice(tx * S, (tx + 1) * S))
                cb = canvas[blk]
                if (~(cb == 0).all(-1)).all() and np.abs(cb[..., :3].reshape(-1, 3).mean(0) - ref).mean() < 40:
                    ok[blk] = True
            take &= ok
        if take.any():
            out[take] = canvas[take]
            left &= ~take
            used.append(fid)
        if not left.any():
            break
    return out, 'frames ' + ' '.join(used)


def frame_under(hero, block, pack, S=8):
    """HD of what the other pieces of a frame draw under `block` (core convention, block-sized x S), from the
    frame of the hero's layout that uses it and whose other pieces cover the most of it; None if not found."""
    lay = json.load(open(os.path.join(ROOT, 'extracted', 'disc1_full', hero, 'layout.json')))
    sizes = {r['name'].rsplit('-', 1)[0]: (int(r['w']), int(r['h']))
             for r in csv.DictReader(open(os.path.join(ROOT, 'extracted', 'disc1_full', hero, 'index.csv')))}
    if block not in sizes:
        return None
    bw, bh = sizes[block]
    best = None
    for v in lay.values():
        for f in v['frames']:
            me = [p for p in f if p['block'] == block]
            if not me:
                continue
            a = me[0]
            canvas = np.zeros((bh * S, bw * S, 4), np.int16)
            for p in f:                                    # list order, later pieces on top (Hero.assemble)
                if p is a or p['block'] not in sizes:
                    continue
                pal = v['palettes'][min(p['clut'], len(v['palettes']) - 1)]
                name = pack.get(f"{p['block']}-{pal}")
                if not name or not name.endswith('.bc7'):
                    continue
                im = read_bc7_level0(os.path.join(PACK, name)).astype(np.int16)
                if p['flipx']:
                    im = im[:, ::-1]
                if p['flipy']:
                    im = im[::-1]
                ox, oy = (p['dx'] - a['dx']) * S, (p['dy'] - a['dy']) * S
                if a['flipx']:                             # canvas is in the piece's own (unflipped) orientation
                    im = im[:, ::-1]
                    ox = bw * S - (ox + im.shape[1])
                if a['flipy']:
                    im = im[::-1]
                    oy = bh * S - (oy + im.shape[0])
                y0, x0 = max(0, oy), max(0, ox)
                y1, x1 = min(bh * S, oy + im.shape[0]), min(bw * S, ox + im.shape[1])
                if y1 <= y0 or x1 <= x0:
                    continue
                src = im[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
                m = ~(src == 0).all(-1)
                region = canvas[y0:y1, x0:x1]
                region[m] = src[m]
            cov = int((~(canvas == 0).all(-1)).sum())
            if best is None or cov > best[0]:
                best = (cov, canvas)
    return best[1] if best else None


def fill_gaps(path, dump, part, borrow=None):
    """The aliased HD (pack file `path`, our part's drawing) differs from the game's copy in a few texels: where the
    game has a texel and our part had none, paste the HD of a neighbouring texel that both have (shifted to the
    game's colour); where the game has none, clear it. Mips/BC7 rebuilt like bc7pack. Returns texels changed."""
    if not path.endswith('.bc7'):
        return 0
    hd = read_bc7_level0(path).astype(np.int16)          # PSX convention, as the core keeps it
    h, w = dump.shape[:2]
    S = hd.shape[1] // w
    if S < 1 or hd.shape[0] != h * S:
        return 0
    g_op, o_op = dump[..., 3] > 0, part[..., 3] > 0
    add, rem = g_op & ~o_op, ~g_op & o_op
    # 30.10: slits left between the old drawing and the added texels (transparent in the game's copy too, covered
    # there by another piece) showed the dark background through the hair in HD - fill texels enclosed by hair
    # within 2 texels on both sides (left+right or above+below); the outer silhouette is left alone
    op = g_op | o_op
    slit = np.zeros_like(op)
    for y, x in zip(*np.nonzero(~op)):
        lr = op[y, max(0, x - 2):x].any() and op[y, x + 1:x + 3].any()
        ud = op[max(0, y - 2):y, x].any() and op[y + 1:y + 3, x].any()
        slit[y, x] = lr or ud
    up = lambda m: np.repeat(np.repeat(m, S, 0), S, 1)   # noqa: E731  texel mask -> HD mask
    # every HD pixel of a texel the game draws must be covered (the old cut of our drawing could be thinner than
    # a texel: a sub-texel slit inside the hair); extra drawing where the game has none is kept (hidden under the
    # neighbouring piece, while clearing it could open a hole)
    gap = up(g_op | slit) & (hd == 0).all(-1)
    n = int((g_op | slit).sum() - (g_op & o_op).sum())
    fill_gaps.source = 'inpaint'
    if gap.any() and borrow is not None:
        # best source: our own redraw of a neighbouring walk frame that has hair there (sharp, same style); a texel
        # is taken only if it looks like what this palette colour looks like elsewhere in our piece
        refs = {}
        for y, x in zip(*np.nonzero(g_op & o_op)):
            refs.setdefault(tuple(dump[y, x][:3]), []).append(hd[y * S:(y + 1) * S, x * S:(x + 1) * S, :3].reshape(-1, 3).mean(0))
        want = {}
        for y, x in zip(*np.nonzero(g_op | slit)):
            if gap[y * S:(y + 1) * S, x * S:(x + 1) * S].any():
                col = tuple(dump[y, x][:3]) if g_op[y, x] else None
                if col in refs:
                    want[(y, x)] = np.mean(refs[col], 0)
        got = borrow(hd, gap, want)
        if got is not None:
            canvas, fill_gaps.source = got
            take = gap & ~(canvas == 0).all(-1)
            hd[take] = canvas[take]
            gap &= ~take
    if gap.any():
        empty = (hd == 0).all(-1) & ~gap
        # repaint a 3 px band around what is left: the old cut had a dark outline drawn along it
        band = cv2.dilate(gap.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & ~empty
        # inpaint from the surrounding drawing only: transparent pixels are masked too, so nothing pulls towards
        # black; then shift each added texel to the game's colour relative to its drawn neighbours
        rgb = np.clip(hd[..., :3], 0, 255).astype(np.uint8)
        fill = cv2.inpaint(np.ascontiguousarray(rgb), ((band | empty) * 255).astype(np.uint8), S, cv2.INPAINT_TELEA)
        fill = fill.astype(np.int16)
        shiftmap = np.zeros(hd.shape[:2] + (3,), np.int16)
        for y, x in zip(*np.nonzero(add)):
            nb = [dump[y + dy, x + dx][:3] for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                  if 0 <= y + dy < h and 0 <= x + dx < w and g_op[y + dy, x + dx] and o_op[y + dy, x + dx]]
            if nb:
                shiftmap[y * S:(y + 1) * S, x * S:(x + 1) * S] = dump[y, x][:3] - np.mean(nb, 0)
        out = np.clip(fill + shiftmap, 0, 255)
        out[(out == 0).all(-1)] = 1                                  # opaque never reads as transparent
        hd[band, :3] = out[band]
        hd[band, 3] = 0                                              # opaque in the core's convention
    lv = [hd.astype(np.uint8)]
    while lv[-1].shape[0] % 2 == 0 and lv[-1].shape[1] % 2 == 0:
        lv.append(bc7pack.gen_mip(lv[-1]))
    l0 = lv[0]
    tr = (l0 == 0).all(-1)
    flags = ((bc7pack.TRANSPARENT if tr.any() else 0) | (bc7pack.OPAQUE if (~tr & (l0[..., 3] == 0)).any() else 0)
             | (bc7pack.SEMI if (l0[..., 3] == 255).any() else 0))
    parts, failed, _ = bc7pack.encode_levels(lv)
    if failed:
        return 0
    data = bc7pack.pack_file(parts, l0.shape[1], l0.shape[0], flags)
    with open(path + '.tmp', 'wb') as f:
        f.write(data)
    os.replace(path + '.tmp', path)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', required=True)
    ap.add_argument('--dump', default=DUMP)
    ap.add_argument('--max-diff', type=float, default=0.05, help='share of texels whose transparency may differ')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--refill', action='store_true', help='redo earlier aliases (fresh copy + gap fill)')
    a = ap.parse_args()
    done = set()   # aliases made before (from the log)
    if os.path.exists(LOG):
        for line in open(LOG, encoding='utf-8'):
            p = line.split()
            if len(p) > 5 and p[4] == '<-' and not line.rstrip().endswith('(dry)'):
                done.add(p[2])
    hdir = os.path.join(ROOT, 'extracted', 'disc1_full', a.hero)
    rows = list(csv.DictReader(open(os.path.join(hdir, 'index.csv'))))
    pals = {r['name'].rsplit('-', 1)[1] for r in rows}
    by = {}
    for r in rows:
        by.setdefault((r['name'].rsplit('-', 1)[1], int(r['w']), int(r['h'])), []).append(r['name'])
    pack = {}
    for e in os.scandir(PACK):
        stem, ext = os.path.splitext(e.name)
        if ext in ('.bc7', '.png'):
            pack.setdefault(stem, e.name)
    cache = {}
    made = skipped = 0
    for f in sorted(os.listdir(a.dump)):
        if not f.endswith('.png'):
            continue
        stem = f[:-4]
        pal = stem.rsplit('-', 1)[-1]
        if pal not in pals or (stem in pack and not (a.refill and stem in done)):
            continue
        d = rgba(os.path.join(a.dump, f))
        h, w = d.shape[:2]
        td = d[..., 3] > 0
        best = None
        for name in by.get((pal, w, h), []):
            if name not in pack:
                continue
            if name not in cache:
                cache[name] = rgba(os.path.join(hdir, 'parts', name + '.png'))
            p = cache[name]
            tp = p[..., 3] > 0
            both = td & tp
            if np.abs(d[..., :3] - p[..., :3])[both].max(initial=0) > 8:
                continue
            n = int((td != tp).sum())
            if best is None or n < best[0]:
                best = (n, name)
        if best is None or best[0] > max(2, a.max_diff * w * h):
            skipped += 1
            log(f'{stem} {w}x{h}: no close part ({best})')
            continue
        src = pack[best[1]]
        dst = stem + os.path.splitext(src)[1]
        log(f'{stem} {w}x{h} <- {src} ({best[0]} texels differ)' + (' (dry)' if a.dry else ''))
        if not a.dry:
            shutil.copyfile(os.path.join(PACK, src), os.path.join(PACK, dst))
            pack[stem] = dst
            if best[0]:
                blk = best[1].rsplit('-', 1)[0]
                n = fill_gaps(os.path.join(PACK, dst), d, cache[best[1]],
                              lambda hd, gap, want: frame_borrow(a.hero, blk, hd, gap, pack, want))
                log(f'  {dst}: {n} texels filled from {fill_gaps.source}')
        made += 1
    log(f'{a.hero}: aliased {made}, no match {skipped}' + (' (dry run)' if a.dry else ''))


if __name__ == '__main__':
    main()
