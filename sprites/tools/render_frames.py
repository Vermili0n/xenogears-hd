"""Assemble every frame of a Xenogears 2D sprite set from its parts and save a contact sheet."""
import argparse
import math
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xdisc import psx_to_rgba  # noqa: E402
from xfs import field_archive_index, get_file, lzss_decompress, read_toc  # noqa: E402
from xspr import cluts, frames, parse_set, pixel_blocks  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402


def block_rgba(w, h, px, pal):
    idx = np.zeros((h, w), np.uint8)
    flat = np.frombuffer(bytes(px[:(w * h) // 2]), np.uint8)
    idx.reshape(-1)[0::2] = flat & 0x0f
    idx.reshape(-1)[1::2] = flat >> 4
    lut = np.array([psx_to_rgba(c) for c in pal], np.uint8)
    lut[0, 3] = 0
    rgba = lut[idx]
    rgba[..., 3] = np.where(idx == 0, 0, 255)
    return Image.fromarray(rgba, 'RGBA')


def render_set(s, canvas=160, origin=(80, 128)):
    _, _, blocks = pixel_blocks(s['meta'])
    pals = cluts(s['clut_raw'])
    out = []
    for parts in frames(s['meta']):
        img = Image.new('RGBA', (canvas, canvas), (0, 0, 0, 0))
        for p in parts:
            b = blocks.get(p['ref'])
            if b is None or b[2]:
                continue
            w, h, _, px = b
            if not w or not h:
                continue
            part = block_rgba(w, h, px, pals[min(p['clut'], len(pals) - 1)])
            if p['flipx']:
                part = part.transpose(Image.FLIP_LEFT_RIGHT)
            if p['flipy']:
                part = part.transpose(Image.FLIP_TOP_BOTTOM)
            x = origin[0] + p['dx'] + p['mx']
            y = origin[1] + p['dy'] + p['my']
            if p['rot']:
                part = part.rotate(-p['rot'] / 0x80 * 180, expand=True)
            img.alpha_composite(part, (int(x), int(y)))
        out.append(img)
    return out


def load(user, n, sub, base):
    fh = open(user, 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    d = get_file(mm, read_toc(mm)[n])
    if sub >= 0:
        x = field_archive_index(d)[sub]
        d = lzss_decompress(d[x['offset']:x['end']])[0][:x['size']]
    return parse_set(d, base)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True)
    ap.add_argument('--file', type=int, required=True)
    ap.add_argument('--sub', type=int, default=-1)
    ap.add_argument('--base', type=int, default=0)
    ap.add_argument('--out', required=True)
    ap.add_argument('--cols', type=int, default=16)
    ap.add_argument('--scale', type=int, default=2)
    ap.add_argument('--first', type=int, default=0)
    ap.add_argument('--count', type=int, default=64)
    args = ap.parse_args()
    s = load(args.user, args.file, args.sub, args.base)
    imgs = render_set(s)[args.first:args.first + args.count]
    cell = 160
    rows = math.ceil(len(imgs) / args.cols)
    sheet = Image.new('RGBA', (args.cols * cell, rows * cell), (70, 70, 70, 255))
    for i, im in enumerate(imgs):
        sheet.alpha_composite(im, ((i % args.cols) * cell, (i // args.cols) * cell))
    sheet = sheet.resize((sheet.width * args.scale // 2, sheet.height * args.scale // 2), Image.NEAREST)
    sheet.save(args.out)
    print('frames', len(imgs))


if __name__ == '__main__':
    main()
