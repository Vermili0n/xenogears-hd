r"""A map NPC frame assembled from the pack's draw-rect files (npc_rects.py names: crc32 of the drawn rect's words),
the files the core / the port use where a map uploads the sheet in a way no upload file matches.
  python rect_frames.py <set> <frame,...> -> balthasar\rects_<set>.png (sprite x8 | from rect files | from the page)"""
import os
import sys
import zlib

import numpy as np

from gcommon import HERE, PACK, npc_set, read_bc7_level0, rgba_from_idx, side_by_side
from npc_rects import hd_sheet, sheet_words
from npc_twins import frame_rgb
from seam_fill_npc import rect as part_rect
from use_page import use_page

S = 8


def rect_page(lay, idx, pal):
    """A page (x8) painted from the rect files of every piece: each file holds the piece's rect, x = sx>>2 words wide."""
    words = sheet_words(idx.astype(np.uint16))
    out = np.zeros((idx.shape[0] * S, 256 * S, 4), np.uint8)
    names = {}
    for f in lay['frames']:
        for p in f:
            sx, sy, w, h = part_rect(p['block'])
            x0, ww, hh = sx >> 2, ((sx + w + 1) >> 2) - (sx >> 2), h - 1
            if ww <= 0 or hh <= 0:
                continue
            crc = zlib.crc32(np.ascontiguousarray(words[sy:sy + hh, x0:x0 + ww]).astype('<u2').tobytes()) & 0xffffffff
            path = os.path.join(PACK, f'{crc:x}-{pal}.bc7')
            names[(x0, sy, ww, hh)] = os.path.exists(path)
            if os.path.exists(path):
                blk = read_bc7_level0(path)
                if blk.shape[:2] == (hh * S, ww * 4 * S):
                    out[sy * S:(sy + hh) * S, x0 * 4 * S:(x0 + ww) * 4 * S] = blk
    return out, names


def main():
    nid, frames = sys.argv[1], [int(x) for x in sys.argv[2].split(',')]
    lay, u, idx, raw = npc_set(nid)
    pal = u['palettes'][0]
    rp, names = rect_page(lay, idx, pal)
    page = hd_sheet(u['uses'], pal, idx.shape)
    if page is None:
        page = use_page(u['uses'][0], pal, idx.shape)
    low = rgba_from_idx(idx, raw[0])
    cells = []
    for k in frames:
        a = np.repeat(np.repeat(frame_rgb(lay, k, low, 1), S, 0), S, 1)
        cells += [a, frame_rgb(lay, k, rp, S), frame_rgb(lay, k, page, S)]
    side_by_side(cells).save(os.path.join(HERE, 'balthasar', f'rects_{nid}.png'))
    print(nid, 'rect files present', sum(names.values()), 'of', len(names))


if __name__ == '__main__':
    main()
