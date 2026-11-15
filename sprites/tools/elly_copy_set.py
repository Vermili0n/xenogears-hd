"""Elly's walk copy on maps 934/936 (30.10): the game streams set 428's parts from the map archive (sub-file 4),
where 32 of the 1243 parts have a few more hair texels -> their upload hashes have no HD (hair flicker in game).

  python elly_copy_set.py [--out extracted/disc1_full/elly934]
Builds a hero folder for the copy: layout.json with only set 428_0, the changed blocks renamed to the copy's hashes,
parts/ = the original parts + the copy parts (same palettes), copy_map.json {copy hash: original hash}, and lists
the frames that use a changed part (frames.txt) - those are rendered like any hero frame (render_prod controls).
"""
import argparse
import json
import mmap
import os
import shutil
import sys
import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from extract_heroes import load_sets  # noqa: E402
from render_frames import psx_to_rgba  # noqa: E402
from xfs import field_archive_index, get_file, lzss_decompress, read_toc  # noqa: E402
from xspr import pixel_blocks  # noqa: E402

SRC = os.path.join(ROOT, 'extracted', 'disc1_full', 'elly')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'extracted', 'disc1_full', 'elly934'))
    ap.add_argument('--map-file', type=int, default=934)
    a = ap.parse_args()
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = {e['n']: e for e in read_toc(mm)}
    s = load_sets(get_file(mm, toc[428]))[0]
    _, _, bl = pixel_blocks(s['meta'])
    blocks = sorted(bl.items())
    d = get_file(mm, toc[a.map_file])
    x = field_archive_index(d)[4]
    sub, _ = lzss_decompress(d[x['offset']:x['end']])
    sub = sub[:x['size']]
    # parts lie back to back in the set's block order; a changed one sits right after its predecessor
    sizes = [(w // 2) * h for _, (w, h, b8, px) in blocks]
    p = sub.find(bytes(blocks[0][1][3][:sizes[0]]))   # read the copy in order (identical parts repeat elsewhere)
    changed = {}
    for k, (off, (w, h, b8, px)) in enumerate(blocks):
        mine = bytes(px[:sizes[k]])
        here = sub[p:p + sizes[k]]
        if here != mine:
            if len(here) < sizes[k]:
                raise SystemExit(f'block {k}: copy data ends early')
            old = format(zlib.crc32(mine) & 0xffffffff, 'x')
            changed[old] = (format(zlib.crc32(here) & 0xffffffff, 'x'), w, h, here)
        p += sizes[k]
    lay = json.load(open(os.path.join(SRC, 'layout.json')))['428_0']
    pals = lay['palettes']
    os.makedirs(os.path.join(a.out, 'parts'), exist_ok=True)
    cmap = {}
    for old, (new, w, h, data) in changed.items():
        idx = np.zeros((h, w), np.uint8)
        b = np.frombuffer(data, np.uint8)
        idx[:, 0::2] = (b & 15).reshape(h, w // 2)
        idx[:, 1::2] = (b >> 4).reshape(h, w // 2)
        for pal in pals:
            src = os.path.join(SRC, 'parts', f'{old}-{pal}.png')
            if not os.path.exists(src):
                continue
            # palette colours from the original part (same indices -> same colours): map index -> RGBA
            o = np.asarray(Image.open(src).convert('RGBA'))
            ob = np.frombuffer(bytes(bl[[k for k, v in bl.items()
                                        if format(zlib.crc32(bytes(v[3][:(v[0] // 2) * v[1]])) & 0xffffffff, 'x') == old][0]][3]), np.uint8)
            oidx = np.zeros((h, w), np.uint8)
            oidx[:, 0::2] = (ob[:(w // 2) * h] & 15).reshape(h, w // 2)
            oidx[:, 1::2] = (ob[:(w // 2) * h] >> 4).reshape(h, w // 2)
            lut = {}
            for i in range(16):
                m = oidx == i
                if m.any():
                    lut[i] = o[m][0]
            out = np.zeros((h, w, 4), np.uint8)
            for i in range(1, 16):
                m = idx == i
                if m.any():
                    if i not in lut:
                        raise SystemExit(f'{old}: index {i} not in the original part - palette unknown')
                    out[m] = lut[i]
            Image.fromarray(out, 'RGBA').save(os.path.join(a.out, 'parts', f'{new}-{pal}.png'))
        cmap[new] = old
    # copy every other part of set 428_0 and rename the changed blocks in the layout
    used = {(p['block'], pals[min(p['clut'], len(pals) - 1)]) for f in lay['frames'] for p in f}
    for blk, pal in used:
        if blk in changed:
            continue
        shutil.copyfile(os.path.join(SRC, 'parts', f'{blk}-{pal}.png'), os.path.join(a.out, 'parts', f'{blk}-{pal}.png'))
    frames = []
    for fi, f in enumerate(lay['frames']):
        hit = False
        for p in f:
            if p['block'] in changed:
                p['block'] = changed[p['block']][0]
                hit = True
        if hit:
            frames.append(fi)
    json.dump({'428_0': lay}, open(os.path.join(a.out, 'layout.json'), 'w'))
    json.dump(cmap, open(os.path.join(a.out, 'copy_map.json'), 'w'), indent=1)
    open(os.path.join(a.out, 'frames.txt'), 'w').write(' '.join(map(str, frames)) + '\n')
    print(f'changed parts {len(changed)}, frames using them {len(frames)}: {frames}')
    print('copy hashes:', ' '.join(sorted(cmap)))


if __name__ == '__main__':
    main()
