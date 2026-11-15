"""Extract all 2D sprite sets of the playable characters from a Xenogears disc.

Per character it writes:
  parts/<texhash>-<palhash>.png  native-size part, one file per palette the set can draw it with
                                 (exactly the name Beetle PSX HW looks up in -texture-replacements)
  frames/<file>_<set>_<frame>.png assembled frames (for reference / redrawing)
  layout.json                    per frame: parts with block id, position, flips, palette id
  index.csv                      name -> source file, block offset, w, h
"""
import argparse
import csv
import json
import mmap
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_frames import block_rgba, render_set  # noqa: E402
from scan_all import set_candidates  # noqa: E402
from xfs import get_file, lzss_decompress, read_toc  # noqa: E402
from xspr import cluts, frames, parse_set, pixel_blocks  # noqa: E402

import numpy as np  # noqa: E402

# disc 1 file numbers (hidden TOC indices), per rufaswan's Xenogears ISO map
HEROES_DISC1 = {
    'fei':      [427, 439, 440, 441, 442] + list(range(2336, 2342)) + list(range(2396, 2403)) + [2988, 3005, 3922] + list(range(3933, 3938)),
    'elly':     [428] + list(range(2342, 2348)) + list(range(2403, 2406)) + [2989, 3006, 3923],
    'citan':    [429, 436] + list(range(2348, 2354)) + [2991, 2997, 3008, 3014, 3924, 3931],
    'bart':     [430] + list(range(2354, 2360)) + [2990, 3007, 3925],
    'billy':    [431] + list(range(2360, 2366)) + [2992, 3009, 3926],
    'rico':     [432] + list(range(2366, 2372)) + [2993, 3010, 3927],
    'emeralda': [433, 437] + list(range(2372, 2378)) + list(range(2390, 2396)) + [2994, 2998, 3011, 3015, 3928, 3932],
    'chuchu':   [434] + list(range(2378, 2384)) + [2995, 3012, 3929],
    'maria':    [435] + list(range(2384, 2390)) + [2996, 3013, 3930],
}


def clut_hash(c):
    return zlib.crc32(np.asarray(c, '<u2').tobytes()) & 0xffffffff


def load_sets(raw, dec_path=None):
    """Sprite sets in a file, trying it as-is and LZSS-decompressed (pre-decoded file if given)."""
    found = [(raw, b) for b in set_candidates(raw)]
    if not found and dec_path and os.path.exists(dec_path):
        with open(dec_path, 'rb') as fd:
            dec = fd.read()
        found = [(dec, b) for b in set_candidates(dec)]
    if not found and len(raw) > 8:
        try:
            dec, _ = lzss_decompress(raw)
            found = [(dec, b) for b in set_candidates(dec)]
        except Exception:  # noqa: BLE001
            pass
    out = []
    for data, base in found:
        try:
            out.append(parse_set(data, base))
        except Exception:  # noqa: BLE001
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--heroes', default='all')
    ap.add_argument('--no-frames', action='store_true')
    ap.add_argument('--lzdir', help='folder with pre-decoded <n>.dec files')
    ap.add_argument('--map', help='JSON {hero: [file numbers]} instead of the built-in disc 1 table')
    args = ap.parse_args()
    fh = open(args.user, 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    table = HEROES_DISC1
    if args.map:
        with open(args.map) as f:
            table = json.load(f)
    heroes = table if args.heroes == 'all' else {h: table[h] for h in args.heroes.split(',')}
    summary = {}
    for hero, files in heroes.items():
        root = os.path.join(args.out, hero)
        os.makedirs(os.path.join(root, 'parts'), exist_ok=True)
        if not args.no_frames:
            os.makedirs(os.path.join(root, 'frames'), exist_ok=True)
        layout, index, nframes = {}, {}, 0
        for n in files:
            e = toc[n]
            if e['is_dir'] or e['size'] <= 0:
                continue
            for si, s in enumerate(load_sets(get_file(mm, e), os.path.join(args.lzdir, f'{n}.dec') if args.lzdir else None)):
                _, p256, blocks = pixel_blocks(s['meta'])
                pals = cluts(s['clut_raw'])
                if p256 or not pals:
                    continue
                phs = [clut_hash(c) for c in pals]
                # every 4bpp block, with every palette of its set
                for ref, (w, h, b8, px) in blocks.items():
                    if b8 or w % 4 or not w or not h:
                        continue
                    th = zlib.crc32(bytes(px[:(w // 2) * h])) & 0xffffffff
                    for pi, ph in enumerate(phs):
                        name = f'{th:x}-{ph:x}'
                        if name in index:
                            continue
                        block_rgba(w, h, px, pals[pi]).save(os.path.join(root, 'parts', name + '.png'))
                        index[name] = (n, si, ref, w, h)
                key = f'{n}_{si}'
                layout[key] = {'palettes': [f'{p:x}' for p in phs], 'frames': [
                    [{'block': f'{zlib.crc32(bytes(blocks[p["ref"]][3][:(blocks[p["ref"]][0] // 2) * blocks[p["ref"]][1]])) & 0xffffffff:x}',
                      **{k: p[k] for k in ('dx', 'dy', 'flipx', 'flipy', 'clut', 'mx', 'my', 'rot')}}
                     for p in fr if p['ref'] in blocks and not blocks[p['ref']][2]]
                    for fr in frames(s['meta'])]}
                if not args.no_frames:
                    for fi, img in enumerate(render_set(s)):
                        if img.getbbox():
                            img.crop(img.getbbox()).save(os.path.join(root, 'frames', f'{key}_{fi:03d}.png'))
                nframes += len(layout[key]['frames'])
        with open(os.path.join(root, 'layout.json'), 'w') as o:
            json.dump(layout, o)
        with open(os.path.join(root, 'index.csv'), 'w', newline='') as o:
            wr = csv.writer(o)
            wr.writerow(['name', 'file', 'set', 'block', 'w', 'h'])
            for k, v in sorted(index.items()):
                wr.writerow([k, *v])
        summary[hero] = {'files': len(files), 'sets': len(layout), 'frames': nframes, 'part_files': len(index),
                         'unique_blocks': len({k.split('-')[0] for k in index})}
        print(hero, summary[hero], flush=True)
    with open(os.path.join(args.out, 'summary.json'), 'w') as o:
        json.dump(summary, o, indent=1)


if __name__ == '__main__':
    main()
