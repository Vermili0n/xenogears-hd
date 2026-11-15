r"""Scenery uploads the pack has under other palettes only -> recoloured HD per texel index (15.11.2026).

  python scene_recolor.py <F6 report folder> [...]            preview scene\<map>.png + scene\<map>.json (no pack write)
  python scene_recolor.py --install <map> [...]                write the staged files of those maps (new names only)
  python scene_recolor.py --disc                               every map of disc 1: how many (upload, palette) pairs of
                                                               its CLUTs are missing while the upload has a file
The F6 report lists the models' textures drawn from the original with "the pack has this upload under N other palettes".
The upload's texels come from the map's texture file (2*map + 607, tools/mapvram.parse_vram_file; Beetle names each block
crc32 of its words), the CLUTs from the same file's VRAM (a 16- or 256-colour run whose crc is the palette's name).
The HD of the upload under another palette (one whose CLUT is also in the map's VRAM) is recoloured texel by texel:
battle_palettes/recolor_set.recolour (lightness by ratio, chroma by difference, weighted by the pixel's lightness).
"""
import json
import mmap
import os
import re
import sys
import zlib

import numpy as np

from gcommon import HERE, PACK, ROOT, hd, install_files, pack_names, show, side_by_side
from mapvram import parse_vram_file  # noqa: E402
from xfs import get_file, read_toc  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, 'ai', 'redraw', 'battle_palettes'))
from recolor_set import recolour  # noqa: E402
from battle_rects import write_bc7  # noqa: E402

OUT = os.path.join(HERE, 'scene')
LINE = re.compile(r'^  ([0-9a-f]+)-([0-9a-f]+)\s+(\d+)x(\d+) units \((\d+)x(\d+) texels\) at VRAM (\d+),(\d+).*?(other palette)?')


def disc():
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    return mm, read_toc(mm)


def map_vram(mm, toc, m):
    return parse_vram_file(get_file(mm, toc[2 * m + 607]))


def cluts(vram):
    """{crc name: (bpp4 16 colours | bpp8 256 colours)} of every 16-aligned run in VRAM rows (palettes are 16-aligned)."""
    out = {}
    for y in range(512):
        row = vram[y]
        if not row.any():
            continue
        for x in range(0, 1024 - 15, 16):
            seg = row[x:x + 16]
            if seg.any():
                out.setdefault(f'{zlib.crc32(seg.astype("<u2").tobytes()) & 0xffffffff:x}', ('4', seg.copy()))
            if x + 256 <= 1024:
                seg = row[x:x + 256]
                if seg.any():
                    out.setdefault(f'{zlib.crc32(seg.astype("<u2").tobytes()) & 0xffffffff:x}', ('8', seg.copy()))
    return out


def indices(vram, b, bpp):
    a = vram[b['y']:b['y'] + b['h'], b['x']:b['x'] + b['w']]
    if bpp == 8:
        idx = np.zeros((a.shape[0], a.shape[1] * 2), np.uint8)
        idx[:, 0::2], idx[:, 1::2] = a & 0xFF, a >> 8
    else:
        idx = np.zeros((a.shape[0], a.shape[1] * 4), np.uint8)
        for k in range(4):
            idx[:, k::4] = (a >> (4 * k)) & 15
    return idx


def by_upload(have):
    out = {}
    for n in have:
        if '-' in n:
            a, b = n.split('-', 1)
            out.setdefault(a, []).append(b)
    return out


def one_map(m, wanted, have, ups, mm, toc, stage):
    """wanted: [(upload, palette, texel/unit ratio)] -> staged files, preview cells, notes."""
    vram, blocks = map_vram(mm, toc, m)
    blk = {f"{b['hash']:x}": b for b in blocks}
    cl = cluts(vram)
    cells, done, notes = [], [], []
    for up, pal, ratio in wanted:
        if up not in blk:
            notes.append(f'{up}-{pal}: upload not in the map file')
            continue
        bpp = 8 if ratio == 2 else 4
        if pal not in cl or cl[pal][0] != str(bpp):
            notes.append(f'{up}-{pal}: palette not in the map file VRAM')
            continue
        others = [q for q in ups.get(up, []) if q in cl and q != pal and cl[q][0] == str(bpp)]
        if not others:
            notes.append(f'{up}-{pal}: no other palette of the pack is in the map file ({ups.get(up, [])})')
            continue
        idx = indices(vram, blk[up], bpp)
        src = others[0]
        h = hd(f'{up}-{src}')
        if h is None or h.shape[0] % idx.shape[0] or h.shape[1] % idx.shape[1]:
            notes.append(f'{up}-{pal}: HD of {up}-{src} has another shape')
            continue
        k = h.shape[0] // idx.shape[0]
        import recolor_set
        recolor_set.S = k
        png = h.copy()                         # PSX convention -> PNG (recolour and battle_rects.write_bc7 take PNG)
        png[..., 3] = np.where((h == 0).all(-1), 0, np.where(h[..., 3] == 0, 255, 128))
        new = recolour(png, idx, [int(c) for c in cl[src][1]], [int(c) for c in cl[pal][1]])
        name = f'{up}-{pal}'
        if write_bc7(os.path.join(stage, name + '.bc7'), np.ascontiguousarray(new)):
            done.append(name)
        cells.append((name, src, h, new))
        notes.append(f'{name}: from {src} (x{k})')
    return done, cells, notes


def main():
    os.makedirs(OUT, exist_ok=True)
    have = pack_names()
    ups = by_upload(have)
    mm, toc = disc()
    args = sys.argv[1:]
    if args and args[0] == '--install':
        for m in args[1:]:
            info = json.load(open(os.path.join(OUT, f'{m}.json')))
            done = install_files(os.path.join(OUT, 'stage'), info['written'], os.path.join(OUT, 'installed.txt'))
            print(m, 'installed', len(done))
        return
    for rep in args:
        txt = open(os.path.join(rep, 'frame.txt'), encoding='utf-8').read()
        m = int(re.search(r'^map: (\d+)', txt, re.M).group(1))
        sec = txt.split('-- Models\' textures', 1)[1].split('\n-- ', 1)[0]
        wanted = []
        for line in sec.split('\n'):
            g = LINE.match(line)
            if g and 'other palette' in line:
                wanted.append((g.group(1), g.group(2), int(g.group(5)) // int(g.group(3))))
        stage = os.path.join(OUT, 'stage')
        os.makedirs(stage, exist_ok=True)
        done, cells, notes = one_map(m, wanted, have, ups, mm, toc, stage)
        json.dump({'map': m, 'asked': len(wanted), 'written': done, 'notes': notes}, open(os.path.join(OUT, f'{m}.json'), 'w'), indent=1)
        pics = []
        for name, src, h, new in cells[:24]:
            a, b = show(h), show(new)
            s = max(1, a.shape[1] // 512)
            pics += [a[::s, ::s], b[::s, ::s]]
        if pics:
            side_by_side(pics).save(os.path.join(OUT, f'{m}.png'))
        print(f'map {m}: names with other palettes {len(wanted)}, recoloured {len(done)}; {OUT}\\{m}.json')
        for n in notes:
            print('  ', n)


if __name__ == '__main__':
    main()
