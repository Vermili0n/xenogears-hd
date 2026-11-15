r"""Balthasar's heads in HD (from the pack), every frame of a set, labelled - to find a moustache by eye.
  python balthasar_grid.py <set> -> balthasar\grid_<set>.png"""
import sys

import numpy as np
from PIL import Image, ImageDraw

from gcommon import HERE, npc_set
from npc_rects import hd_sheet
from npc_twins import frame_rgb


def grid(nid, top=2, rows=13, cols=11):
    lay, u, idx, raw = npc_set(nid)
    h = hd_sheet(u['uses'], u['palettes'][0], idx.shape)
    cells = []
    for k in range(len(lay['frames'])):
        if not lay['frames'][k]:
            continue
        b = frame_rgb(lay, k, h, 8)[top * 8:(top + rows) * 8]
        w = b.shape[1]
        c = (w - 120) // 2 if w > 120 else 0
        cells.append((k, b[:, c:c + 120]))
    H = rows * 8 + 14
    out = Image.new('RGB', (cols * 124, ((len(cells) + cols - 1) // cols) * H), (30, 30, 30))
    d = ImageDraw.Draw(out)
    for i, (k, b) in enumerate(cells):
        x, y = (i % cols) * 124, (i // cols) * H
        out.paste(Image.fromarray(np.ascontiguousarray(b)), (x, y + 14))
        d.text((x + 2, y + 1), str(k), fill=(255, 255, 0))
    out.save(f'{HERE}/balthasar/grid_{nid}.png')


if __name__ == '__main__':
    for s in sys.argv[1:]:
        grid(s)
