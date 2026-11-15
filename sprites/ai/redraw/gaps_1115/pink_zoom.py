r"""Zoom on the parts a pink-fringe fix changes most: original x8 | pack now | fixed (pinkfix\<gear>\zoom_parts.png)."""
import json
import os
import sys

import numpy as np

from gcommon import HERE, hd, show, side_by_side
from alias_dump_parts import read_bc7_level0
from gear_pink import GEARS, part_png


def main():
    for g in sys.argv[1:]:
        d = os.path.join(HERE, 'pinkfix', g)
        names = json.load(open(os.path.join(d, 'fixed_names.json')))['parts']
        scored = []
        for n in names:
            a, b = hd(n), read_bc7_level0(os.path.join(d, n + '.bc7'))
            if a is None or a.shape != b.shape:
                continue
            scored.append(((a != b).any(-1).sum(), n, a, b))
        scored.sort(key=lambda t: -t[0])
        rows = []
        for cnt, n, a, b in scored[:6]:
            o = part_png(os.path.join(GEARS, g), n)
            k = a.shape[0] // o.shape[0]
            orig = np.repeat(np.repeat(np.where(o[..., 3:] > 0, o[..., :3], (255, 0, 255)).astype(np.uint8), k, 0), k, 1)
            rows.append(np.asarray(side_by_side([orig, show(a), show(b)], gap=4)))
        W = max(r.shape[1] for r in rows)
        out = np.vstack([np.pad(r, ((0, 6), (0, W - r.shape[1]), (0, 0)), constant_values=40) for r in rows])
        side_by_side([out]).save(os.path.join(d, 'zoom_parts.png'))
        print(g, [(c, n) for c, n, _, _ in scored[:6]])


if __name__ == '__main__':
    main()
