"""Find where dumped sprite parts live on the disc, whatever the container (30.10, Elly's hair).

  python find_dump_bytes.py --pal 24829d0f --clut-file 2342 <dump.png> ... [--user work/disc1rus_user.bin]
The dump PNG (core texture dump, 5-bit colours expanded, tri alpha) is turned back into 4bpp indices with the palette
taken from a sprite set that has it (--clut-file: disc file number), packed like VRAM (low nibble first) and searched
as raw bytes in the user-data stream (first row, then the whole block row by row with the block's stride).
"""
import argparse
import mmap
import os
import sys
import zlib

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_all import clut_hash, set_candidates  # noqa: E402
from xfs import get_file, read_toc  # noqa: E402
from xspr import cluts, parse_set  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_clut(mm, toc, fileno, pal):
    e = [x for x in toc if x['n'] == fileno][0]
    d = get_file(mm, e)
    for base in set_candidates(d):
        s = parse_set(d, base)
        for c in cluts(s['clut_raw']):
            if format(clut_hash(c), 'x') == pal:
                return [int(v) for v in c]
    raise SystemExit(f'palette {pal} not in file {fileno}')


def to_indices(png, clut):
    im = np.asarray(Image.open(png).convert('RGBA')).astype(int)
    cols = []
    for v in clut:
        r, g, b = (v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31
        cols.append((r, g, b))
    cols = np.array(cols)
    idx = np.zeros(im.shape[:2], np.uint8)
    for y in range(im.shape[0]):
        for x in range(im.shape[1]):
            p = im[y, x]
            if p[3] == 0 and not p[:3].any():
                idx[y, x] = 0
                continue
            d = np.abs(cols - p[:3]).sum(1)
            d[0] = 10 ** 6 if (p[3] or p[:3].any()) else d[0]
            idx[y, x] = int(d.argmin())
    return idx


def pack4(idx):
    h, w = idx.shape
    out = bytearray()
    for y in range(h):
        for x in range(0, w, 2):
            out.append(int(idx[y, x]) | (int(idx[y, x + 1]) << 4))
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pngs', nargs='+')
    ap.add_argument('--pal', required=True)
    ap.add_argument('--clut-file', type=int, required=True)
    ap.add_argument('--user', default=os.path.join(ROOT, 'work', 'disc1rus_user.bin'))
    ap.add_argument('--clut-user', default=os.path.join(ROOT, 'work', 'disc1_user.bin'),
                    help='stream the --clut-file number refers to (the extraction used the USA disc)')
    a = ap.parse_args()
    ch = open(a.clut_user, 'rb')
    cm = mmap.mmap(ch.fileno(), 0, access=mmap.ACCESS_READ)
    clut = find_clut(cm, read_toc(cm), a.clut_file, a.pal)
    fh = open(a.user, 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    starts = sorted((x['lba'] * 2048, x['lba'] * 2048 + x['size'], x['n']) for x in toc if not x['is_dir'])
    for png in a.pngs:
        idx = to_indices(png, clut)
        h, w = idx.shape
        data = pack4(idx)
        row = w // 2
        name = os.path.basename(png)
        crc = format(zlib.crc32(data) & 0xffffffff, 'x')
        hits = []
        pos = mm.find(data[:row])
        while pos >= 0 and len(hits) < 20:
            if mm[pos:pos + len(data)] == data:
                f = [n for s0, s1, n in starts if s0 <= pos < s1]
                hits.append((pos, f[0] if f else None))
            pos = mm.find(data[:row], pos + 1)
        print(f'{name}: {w}x{h} crc {crc} (name hash {name.split("-")[0]}); contiguous hits: {hits[:6]}')


if __name__ == '__main__':
    main()
