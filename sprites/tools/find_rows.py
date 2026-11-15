"""Search individual rows of a dumped part in the disc stream to learn the storage stride."""
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
    ap.add_argument('--user', required=True)
    ap.add_argument('--at', required=True)
    ap.add_argument('--dump', required=True)
    ap.add_argument('--part', required=True)
    args = ap.parse_args()
    sec, off = (int(v) for v in args.at.split(':'))
    clut = clut_from_bytes(Disc(args.bin).read(sec, off, 32))
    idx = png_to_indices(os.path.join(args.dump, args.part), clut)
    h, w = idx.shape
    rowbytes = w // 2
    raw = np.asarray(indices_to_halfwords(idx), dtype='<u2').tobytes()
    with open(args.user, 'rb') as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        for y in range(h):
            row = raw[y * rowbytes:(y + 1) * rowbytes]
            if len(set(row)) < 4:
                continue
            hits, pos = [], mm.find(row)
            while pos != -1 and len(hits) < 8:
                hits.append(pos)
                pos = mm.find(row, pos + 1)
            print(y, row.hex(), [f'{p // 2048}:{p % 2048}' for p in hits])


if __name__ == '__main__':
    main()
