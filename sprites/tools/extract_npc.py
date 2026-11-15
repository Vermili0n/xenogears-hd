"""Extract NPC 2D sprite sets (field archive sub-file 3) into hero-style folders, so the hero tools work on them.

  python extract_npc.py --user work/disc1_user.bin --out extracted/disc1_npc --set 608:3:10812 [--set ...] [--name id]

Each set -> <out>/<file>_<sub>_<base>/{parts/<tex>-<clut>.png, frames/<key>_<fi>.png, layout.json}, key = '<file>_<base>'.
"""
import argparse
import json
import mmap
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_heroes import clut_hash  # noqa: E402
from render_frames import block_rgba, render_set  # noqa: E402
from xfs import field_archive_index, get_file, lzss_decompress, read_toc  # noqa: E402
from xspr import cluts, frames, parse_set, pixel_blocks  # noqa: E402


def sub_data(mm, toc, n, sub):
    d = get_file(mm, toc[n])
    if sub < 0:
        return d
    x = field_archive_index(d)[sub]
    dec, _ = lzss_decompress(d[x['offset']:x['end']])
    return dec[:x['size']]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--set', action='append', required=True, help='file:sub:base (sub -1 = plain file)')
    a = ap.parse_args()
    fh = open(a.user, 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    for spec in a.set:
        n, sub, base = map(int, spec.split(':'))
        s = parse_set(sub_data(mm, toc, n, sub), base)
        _, p256, blocks = pixel_blocks(s['meta'])
        pals = cluts(s['clut_raw'])
        root = os.path.join(a.out, f'{n}_{sub}_{base}')
        os.makedirs(os.path.join(root, 'parts'), exist_ok=True)
        os.makedirs(os.path.join(root, 'frames'), exist_ok=True)
        phs = [clut_hash(c) for c in pals]
        names = 0
        for ref, (w, h, b8, px) in blocks.items():
            if b8 or w % 4 or not w or not h:
                continue
            th = zlib.crc32(bytes(px[:(w // 2) * h])) & 0xffffffff
            for pi, ph in enumerate(phs):
                p = os.path.join(root, 'parts', f'{th:x}-{ph:x}.png')
                if not os.path.exists(p):
                    block_rgba(w, h, px, pals[pi]).save(p)
                    names += 1
        key = f'{n}_{base}'
        layout = {key: {'palettes': [f'{p:x}' for p in phs], 'frames': [
            [{'block': f'{zlib.crc32(bytes(blocks[p["ref"]][3][:(blocks[p["ref"]][0] // 2) * blocks[p["ref"]][1]])) & 0xffffffff:x}',
              **{k: p[k] for k in ('dx', 'dy', 'flipx', 'flipy', 'clut', 'mx', 'my', 'rot')}}
             for p in fr if p['ref'] in blocks and not blocks[p['ref']][2]]
            for fr in frames(s['meta'])]}}
        json.dump(layout, open(os.path.join(root, 'layout.json'), 'w'))
        for fi, img in enumerate(render_set(s)):
            if img.getbbox():
                img.crop(img.getbbox()).save(os.path.join(root, 'frames', f'{key}_{fi:03d}.png'))
        print(spec, '->', root, f'{len(layout[key]["frames"])} frames, {names} part files, palettes {layout[key]["palettes"]}', flush=True)


if __name__ == '__main__':
    main()
