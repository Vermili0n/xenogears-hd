"""Locate dumped sprite parts inside the disc user-data stream (raw 4bpp rows, contiguous)."""
import argparse
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xdisc import Disc, clut_from_bytes, indices_to_halfwords, png_to_indices  # noqa: E402

import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bin', required=True)
    ap.add_argument('--user', required=True, help='user-data stream file')
    ap.add_argument('--at', required=True, help='sector:offset of the CLUT')
    ap.add_argument('--dump', required=True)
    ap.add_argument('--pal', required=True)
    ap.add_argument('--n', type=int, default=20)
    args = ap.parse_args()
    sec, off = (int(v) for v in args.at.split(':'))
    clut = clut_from_bytes(Disc(args.bin).read(sec, off, 32))
    parts = []
    for f in os.listdir(args.dump):
        if f.endswith('-' + args.pal + '.png'):
            idx = png_to_indices(os.path.join(args.dump, f), clut)
            if idx is not None:
                parts.append((idx.size, f, idx))
    parts.sort(key=lambda p: -p[0])
    with open(args.user, 'rb') as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        for _, f, idx in parts[:args.n]:
            raw = np.asarray(indices_to_halfwords(idx), dtype='<u2').tobytes()
            hits, pos = [], mm.find(raw)
            while pos != -1 and len(hits) < 6:
                hits.append(pos)
                pos = mm.find(raw, pos + 1)
            print(f, idx.shape, len(raw), 'hits:', [f'{p // 2048}:{p % 2048}' for p in hits])


if __name__ == '__main__':
    main()
