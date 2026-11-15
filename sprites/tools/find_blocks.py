"""Which disc sprite sets contain the given pixel blocks (upload hashes from the core's no-HD log)?

  python find_blocks.py 5de02dab bf6e5871 ... [--user work/disc1_user.bin]
Scans every disc file and sub-file 3 of the field archives (like scan_all.py); prints file, sub, set base,
frame count, palettes and which of the hashes the set holds.
"""
import argparse
import mmap
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_all import block_hash, clut_hash, set_candidates  # noqa: E402
from xfs import field_archive_index, get_file, lzss_decompress, read_toc  # noqa: E402
from xspr import cluts, parse_set, pixel_blocks  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sets_with(d, want):
    for base in set_candidates(d):
        try:
            s = parse_set(d, base)
            cnt, p256, blocks = pixel_blocks(s['meta'])
            pals = sorted({format(clut_hash(c), 'x') for c in cluts(s['clut_raw'])})
        except Exception:  # noqa: BLE001
            continue
        hs = set()
        for (w, h, b8, px) in blocks.values():
            hs.add(format(block_hash(w, h, px), 'x'))                     # 4bpp: (w/2)*h bytes
            if b8:
                hs.add(format(zlib.crc32(bytes(px[:w * h])) & 0xffffffff, 'x'))   # 8bpp: w*h bytes
        hit = sorted(hs & want)
        if hit:
            yield base, cnt, len(blocks), pals, hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('hashes', nargs='+')
    ap.add_argument('--user', default=os.path.join(ROOT, 'work', 'disc1_user.bin'))
    a = ap.parse_args()
    want = {h.lower() for h in a.hashes}
    fh = open(a.user, 'rb')   # keep the handle: the mapping needs an open file
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    for e in read_toc(mm):
        if e['is_dir'] or e['size'] <= 0 or e['lba'] * 2048 + e['size'] > len(mm):
            continue
        d = get_file(mm, e)
        for base, cnt, nb, pals, hit in sets_with(d, want):
            print(f"file {e['n']} sub - base {base}: {cnt} frames, {nb} blocks, pals {' '.join(pals)}; has {len(hit)}: {' '.join(hit)}")
        if len(d) > 0x154:
            try:
                idx = field_archive_index(d)
            except struct.error:
                idx = []
            if idx and all(0 < x['offset'] <= x['end'] <= len(d) for x in idx) and idx[0]['offset'] >= 0x150:
                for k, x in enumerate(idx):
                    if k != 3:
                        continue
                    try:
                        sub, _ = lzss_decompress(d[x['offset']:x['end']])
                    except Exception:  # noqa: BLE001
                        continue
                    for base, cnt, nb, pals, hit in sets_with(sub[:x['size']], want):
                        print(f"file {e['n']} sub {k} base {base}: {cnt} frames, {nb} blocks, pals {' '.join(pals)}; "
                              f"has {len(hit)}: {' '.join(hit)}")


if __name__ == '__main__':
    main()
