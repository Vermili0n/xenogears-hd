"""Collect every (block, palette) name a palette group can produce on disc and compare with the dump."""
import argparse
import csv
import mmap
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xfs import field_archive_index, get_file, lzss_decompress, read_toc  # noqa: E402
from xspr import cluts, frames, parse_set, pixel_blocks  # noqa: E402

import numpy as np  # noqa: E402


def clut_hash(c):
    return zlib.crc32(np.asarray(c, '<u2').tobytes()) & 0xffffffff


def names_for_set(s):
    """Names Beetle would give each 4bpp block, using the palette the frame data selects for it."""
    _, p256, blocks = pixel_blocks(s['meta'])
    pals = cluts(s['clut_raw'])
    ph = [clut_hash(c) for c in pals]
    out = {}
    if p256 or not pals:
        return out
    for parts in frames(s['meta']):
        for p in parts:
            b = blocks.get(p['ref'])
            if not b or b[2] or b[0] % 4:
                continue
            w, h, _, px = b
            th = zlib.crc32(bytes(px[:(w // 2) * h])) & 0xffffffff
            name = f'{th:x}-{ph[min(p["clut"], len(ph) - 1)]:x}'
            out[name] = (w, h, p['ref'])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True)
    ap.add_argument('--sets', required=True, help='sprite_sets csv from scan_all.py')
    ap.add_argument('--pal', required=True)
    ap.add_argument('--dump', required=True)
    ap.add_argument('--list')
    args = ap.parse_args()
    fh = open(args.user, 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    allnames = {}
    with open(args.sets) as f:
        for row in csv.DictReader(f):
            if args.pal not in row['palettes'].split():
                continue
            d = get_file(mm, toc[int(row['file'])])
            if row['sub'] != '-':
                x = field_archive_index(d)[int(row['sub'])]
                d = lzss_decompress(d[x['offset']:x['end']])[0][:x['size']]
            for name, info in names_for_set(parse_set(d, int(row['base']))).items():
                allnames.setdefault(name, (int(row['file']),) + info)
    mine = {k: v for k, v in allnames.items() if k.endswith('-' + args.pal)}
    dumped = {f[:-4] for f in os.listdir(args.dump) if f.endswith('-' + args.pal + '.png')}
    print(f'palette {args.pal}: names on disc = {len(mine)}, dumped in game = {len(dumped)}, '
          f'dumped covered by disc = {len(dumped & set(mine))}, missing = {len(dumped - set(mine))}')
    if args.list:
        with open(args.list, 'w') as o:
            o.write('name,file,w,h,ref\n')
            for k, v in sorted(mine.items()):
                o.write(f'{k},{v[0]},{v[1]},{v[2]},{v[3]}\n')


if __name__ == '__main__':
    main()
