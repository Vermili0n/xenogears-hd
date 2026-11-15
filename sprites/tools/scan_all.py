"""Scan every disc file (and every LZSS sub-file of field archives) for 2D sprite sets.

Writes a CSV: file, sub, set_base, frames, blocks, palettes, matched_dump_count.
"""
import argparse
import mmap
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xfs import field_archive_index, get_file, lzss_decompress, read_toc  # noqa: E402
from xspr import cluts, parse_set, pixel_blocks, u24  # noqa: E402

import numpy as np  # noqa: E402


def block_hash(w, h, data):
    return zlib.crc32(bytes(data[:(w // 2) * h])) & 0xffffffff


def clut_hash(c):
    return zlib.crc32(np.asarray(c, '<u2').tobytes()) & 0xffffffff


def looks_like_set(d, base=0):
    if base + 24 > len(d):
        return False
    num = u24(d, base)
    if not 3 <= num <= 6 or d[base + 3] != 0:
        return False
    offs = [u24(d, base + 4 + 4 * k) for k in range(num + 1)]
    if offs[0] != (num + 2) * 4:
        return False
    return all(offs[k] < offs[k + 1] for k in range(num)) and base + offs[-1] <= len(d) + 3


def set_candidates(d):
    """Single set at 0, or the multi-set table form (met_off, tex_off, ?) entries."""
    if looks_like_set(d, 0):
        yield 0
        return
    if len(d) < 16:
        return
    num = u24(d, 0)
    if 0 < num < 64:
        for i in range(num):
            o = 8 + 12 * i
            if o + 4 > len(d):
                break
            met = u24(d, o)
            if 0 < met < len(d) and looks_like_set(d, met):
                yield met


def analyse(d, dumped):
    rows = []
    for base in set_candidates(d):
        try:
            s = parse_set(d, base)
            cnt, p256, blocks = pixel_blocks(s['meta'])
            pals = sorted({format(clut_hash(c), 'x') for c in cluts(s['clut_raw'])})
        except Exception:  # noqa: BLE001
            continue
        hit = sum(1 for (w, h, b8, px) in blocks.values()
                  if not b8 and w % 4 == 0 and block_hash(w, h, px) in dumped)
        rows.append((base, cnt, int(bool(p256)), len(blocks), pals, hit))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True)
    ap.add_argument('--dump', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    dumped = set()
    for f in os.listdir(args.dump):
        if f.endswith('.png'):
            dumped.add(int(f.split('-')[0].split('.')[0], 16))
    fh = open(args.user, 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    with open(args.out, 'w') as o:
        o.write('file,sub,base,frames,p256,blocks,matched,palettes\n')
        for e in toc:
            if e['is_dir'] or e['size'] <= 0 or e['lba'] * 2048 + e['size'] > len(mm):
                continue
            d = get_file(mm, e)
            for base, cnt, p256, nb, pals, hit in analyse(d, dumped):
                o.write(f"{e['n']},-,{base},{cnt},{p256},{nb},{hit},{' '.join(pals)}\n")
            # field archive: 8 LZSS sub-files, sizes at 0x10C, offsets at 0x130
            if len(d) > 0x154:
                try:
                    idx = field_archive_index(d)
                except struct.error:
                    idx = []
                ok = idx and all(0 < x['offset'] <= x['end'] <= len(d) for x in idx) and idx[0]['offset'] >= 0x150
                if ok:
                    for k, x in enumerate(idx):
                        if k != 3:  # sub-file 3 of a map archive = 2D sprite data
                            continue
                        try:
                            sub, _ = lzss_decompress(d[x['offset']:x['end']])
                        except Exception:  # noqa: BLE001
                            continue
                        sub = sub[:x['size']]
                        for base, cnt, p256, nb, pals, hit in analyse(sub, dumped):
                            o.write(f"{e['n']},{k},{base},{cnt},{p256},{nb},{hit},{' '.join(pals)}\n")
            o.flush()


if __name__ == '__main__':
    main()
