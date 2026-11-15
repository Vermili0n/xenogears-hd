"""Find hero sprite sets on another disc by overlap with already extracted heroes (blocks/palettes).

Writes JSON {hero: [file numbers]} usable with extract_heroes.py --map.
"""
import argparse
import csv
import json
import mmap
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_all import set_candidates  # noqa: E402
from xspr import parse_set  # noqa: E402
from xfs import get_file, read_toc  # noqa: E402
from xspr import cluts, pixel_blocks  # noqa: E402

import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True)
    ap.add_argument('--ref', required=True, help='extracted/disc1 folder')
    ap.add_argument('--out', required=True)
    ap.add_argument('--min-overlap', type=float, default=0.2)
    ap.add_argument('--lzdir', help='folder with <n>.dec files from lzss_fast.cs (pre-decoded LZSS files)')
    args = ap.parse_args()
    hero_blocks, hero_pals = {}, {}
    for hero in os.listdir(args.ref):
        idx = os.path.join(args.ref, hero, 'index.csv')
        if not os.path.exists(idx):
            continue
        with open(idx) as f:
            names = [r['name'] for r in csv.DictReader(f)]
        hero_blocks[hero] = {int(n.split('-')[0], 16) for n in names}
        hero_pals[hero] = {int(n.split('-')[1], 16) for n in names}
    fh = open(args.user, 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    result = {h: [] for h in hero_blocks}
    report = []
    for e in toc:
        if e['is_dir'] or e['size'] <= 32 or e['lba'] * 2048 + e['size'] > len(mm):
            continue
        raw = get_file(mm, e)
        if len(raw) > 4 * 1024 * 1024:
            continue
        sets = []
        for data in (raw, None):
            if data is None:
                p = os.path.join(args.lzdir, f"{e['n']}.dec") if args.lzdir else ''
                if not p or not os.path.exists(p):
                    continue
                with open(p, 'rb') as fd:
                    data = fd.read()
            for base in set_candidates(data):
                try:
                    sets.append(parse_set(data, base))
                except Exception:  # noqa: BLE001
                    pass
        for s in sets:
            try:
                _, p256, blocks = pixel_blocks(s['meta'])
                pals = {zlib.crc32(np.asarray(c, '<u2').tobytes()) & 0xffffffff for c in cluts(s['clut_raw'])}
            except Exception:  # noqa: BLE001
                continue
            th = {zlib.crc32(bytes(px[:(w // 2) * h])) & 0xffffffff
                  for (w, h, b8, px) in blocks.values() if not b8 and w and h and w % 4 == 0}
            if not th:
                continue
            best, score = None, 0.0
            for hero, hb in hero_blocks.items():
                ov = len(th & hb) / len(th)
                if pals & hero_pals[hero]:
                    ov = max(ov, 0.5)
                if ov > score:
                    best, score = hero, ov
            if best and score >= args.min_overlap and e['n'] not in result[best]:
                result[best].append(e['n'])
                report.append((e['n'], best, round(score, 2), len(th)))
    with open(args.out, 'w') as o:
        json.dump(result, o, indent=1)
    for r in report:
        print(r)
    print({h: len(v) for h, v in result.items()})


if __name__ == '__main__':
    main()
