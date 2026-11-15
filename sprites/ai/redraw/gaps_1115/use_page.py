r"""The HD page of one use of a map NPC set, from that use's own upload files in the pack (blocks may start above the
page or run past it; npc_rects.hd_sheet skips such uses). -> RGBA (PSX convention, page texels x8) or None."""
import os

import numpy as np

from gcommon import PACK, read_bc7_level0

S = 8


def use_page(use, pal, shape):
    hd = np.zeros((shape[0] * S, 256 * S, 4), np.uint8)
    got = 0
    for b in use['blocks']:
        f = os.path.join(PACK, f"{b['hash']:x}-{pal}.bc7")
        if not os.path.exists(f):
            continue
        blk = read_bc7_level0(f)
        x, y, w, h = (b['x'] - use['sx']) * 4, b['y'] - use['sy'], b['w'] * 4, b['h']
        if blk.shape[:2] != (h * S, w * S):
            continue
        y0, y1 = max(0, y), min(shape[0], y + h)
        x0, x1 = max(0, x), min(256, x + w)
        if y1 <= y0 or x1 <= x0:
            continue
        hd[y0 * S:y1 * S, x0 * S:x1 * S] = blk[(y0 - y) * S:(y1 - y) * S, (x0 - x) * S:(x1 - x) * S]
        got += 1
    return hd if got else None
