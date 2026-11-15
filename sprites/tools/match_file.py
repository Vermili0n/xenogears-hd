"""Compute Beetle names for every pixel block of a sprite file and compare with dumped textures."""
import argparse
import mmap
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xfs import get_file, read_toc  # noqa: E402
from xspr import cluts, parse_set, pixel_blocks  # noqa: E402

import numpy as np  # noqa: E402


def block_hash(w, h, data):
    """4bpp block uploaded as (w/4) x h halfwords, rows contiguous."""
    rowb = w // 2
    raw = b''.join(data[y * rowb:(y + 1) * rowb] for y in range(h))
    return zlib.crc32(raw) & 0xffffffff


def clut_hash(c):
    return zlib.crc32(np.asarray(c, '<u2').tobytes()) & 0xffffffff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True)
    ap.add_argument('--files', type=int, nargs='+', required=True)
    ap.add_argument('--dump', required=True)
    args = ap.parse_args()
    dumped = {}
    for f in os.listdir(args.dump):
        if f.endswith('.png') and '-' in f:
            h, p = f[:-4].split('-', 1)
            dumped.setdefault(int(h, 16), set()).add(p)
    fh = open(args.user, 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    for n in args.files:
        d = get_file(mm, toc[n])
        try:
            s = parse_set(d)
            cnt, p256, blocks = pixel_blocks(s['meta'])
            pals = [format(clut_hash(c), 'x') for c in cluts(s['clut_raw'])]
        except Exception as e:  # noqa: BLE001
            print(n, 'parse error', e)
            continue
        hits = sum(1 for (w, h, b8, px) in blocks.values() if not b8 and w % 4 == 0 and block_hash(w, h, px) in dumped)
        print(f'file {n}: sections={s["num"]} frames={cnt} p256={bool(p256)} blocks={len(blocks)} '
              f'palettes={pals[:4]}{"..." if len(pals) > 4 else ""} matched_dump={hits}')


if __name__ == '__main__':
    main()
