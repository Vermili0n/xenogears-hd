r"""Heads of Balthasar's field sets (the sets the scripts filed as Maison, c_maison_*): original and HD from the pack.
  python balthasar_heads.py -> balthasar\heads_<set>.png (pairs: sprite x6 | HD, the top 22 texels of each frame)"""
import sys

import numpy as np
from PIL import Image

from gcommon import HERE, npc_set, rgba_from_idx, side_by_side
from npc_rects import hd_sheet
from npc_twins import frame_rgb

SETS = ['2be5277d28', '1c0f2c14f4', 'a096333c67', '6e595cab89']
TOP = 22
Z = 6


def heads(nid):
    lay, u, idx, raw = npc_set(nid)
    h = hd_sheet(u['uses'], u['palettes'][0], idx.shape)
    low = rgba_from_idx(idx, raw[0])
    rows, row = [], []
    for k in range(len(lay['frames'])):
        if not lay['frames'][k]:
            continue
        a = frame_rgb(lay, k, low, 1)[:TOP]
        cells = [np.repeat(np.repeat(a, Z, 0), Z, 1)]
        if h is not None:
            b = frame_rgb(lay, k, h, 8)[:TOP * 8]
            cells.append(np.asarray(Image.fromarray(b).resize((a.shape[1] * Z, a.shape[0] * Z), Image.LANCZOS)))
        pic = np.asarray(side_by_side(cells, gap=2))
        lab = np.zeros((10, pic.shape[1], 3), np.uint8)
        row.append(np.vstack([lab, pic]))
        if len(row) == 8:
            rows.append(np.asarray(side_by_side(row, gap=10)))
            row = []
    if row:
        rows.append(np.asarray(side_by_side(row, gap=10)))
    W = max(r.shape[1] for r in rows)
    out = np.vstack([np.pad(r, ((0, 6), (0, W - r.shape[1]), (0, 0))) for r in rows])
    Image.fromarray(out).save(f'{HERE}/balthasar/heads_{nid}.png')
    return out.shape


if __name__ == '__main__':
    for s in sys.argv[1:] or SETS:
        print(s, heads(s))
