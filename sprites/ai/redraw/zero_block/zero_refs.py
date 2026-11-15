r"""What a frame's block '0' is on the disc (14.11.2026): the raw image table of the frames this job is about.

  python ai\redraw\zero_block\zero_refs.py
Prints, for each part of the frame, the 4-byte image entry (the block reference and the two bytes after it) and what
stands at the referenced place of the set's meta section (w, h, bpp flag). Reads work/disc1_user.bin only.
"""
import mmap
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from extract_heroes import load_sets  # noqa: E402
from xfs import get_file, read_toc  # noqa: E402

FRAMES = [(429, 0, 97), (429, 0, 98), (3924, 0, 37), (2991, 0, 116), (2991, 0, 115), (430, 0, 70)]


def main():
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    for n, si, fi in FRAMES:
        s = load_sets(get_file(mm, toc[n]), os.path.join(ROOT, 'work', 'lz_disc1', f'{n}.dec'))[si]
        meta = s['meta']
        hdr = struct.unpack_from('<H', meta, 0)[0]
        pos = struct.unpack_from('<H', meta, 2 + 2 * fi)[0]
        num = meta[pos] & 0x3f
        print(f'file {n} set {si} frame {fi}: meta {len(meta)} bytes, header {hdr:04x}, frame at {pos}, first bytes '
              f'{meta[pos:pos + 6].hex()}, {num} parts')
        for k in range(num):
            entry = meta[pos + 6 + 4 * k:pos + 10 + 4 * k]
            ref = struct.unpack_from('<H', entry, 0)[0]
            p = ref * 4
            at = meta[p:p + 4].hex() if p + 4 <= len(meta) else 'beyond the meta'
            print(f'   part {k}: entry {entry.hex()} ref {ref} -> offset {p}: {at}')


if __name__ == '__main__':
    main()
