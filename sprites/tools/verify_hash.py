"""Check Beetle's hash formula: palette from disc + dumped part -> CRC32 must equal the file name."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xdisc import Disc, beetle_hash, clut_from_bytes, indices_to_halfwords, png_to_indices, psx_to_rgba  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bin', required=True)
    ap.add_argument('--at', required=True, help='sector:offset of the CLUT')
    ap.add_argument('--dump', required=True)
    ap.add_argument('--pal', required=True)
    args = ap.parse_args()
    d = Disc(args.bin)
    sec, off = (int(v) for v in args.at.split(':'))
    raw = d.read(sec, off, 32)
    clut = clut_from_bytes(raw)
    print('clut crc', format(beetle_hash(clut), 'x'))
    print('clut', ' '.join(format(c, '04x') for c in clut))
    print('rgba', [psx_to_rgba(c) for c in clut])
    ok = bad = skip = 0
    for f in sorted(os.listdir(args.dump)):
        if not f.endswith('-' + args.pal + '.png'):
            continue
        idx = png_to_indices(os.path.join(args.dump, f), clut)
        if idx is None or idx.shape[1] % 4:
            skip += 1
            continue
        h = beetle_hash(indices_to_halfwords(idx))
        name = int(f.split('-')[0], 16)
        if h == name:
            ok += 1
        else:
            bad += 1
            if bad <= 5:
                print('mismatch', f, format(h, 'x'))
    print(f'match={ok} mismatch={bad} skipped={skip}')


if __name__ == '__main__':
    main()
