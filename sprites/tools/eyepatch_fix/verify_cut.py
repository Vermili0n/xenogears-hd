"""After bart_limit / maison_cut install: every prepared array against the file now in the pack; draw-rect names of Maison's sets; PNG in the pack."""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from install_0311 import rect_names  # noqa: E402

for lab, d in (('bart', os.path.join(ROOT, 'ai', 'prod_work', 'h_bart_patch', 'stage2')), ('maison', os.path.join(ROOT, 'ai', 'redraw', 'maison2', 'cut'))):
    worst, bad_alpha, n = 0.0, 0, 0
    for f in glob.glob(os.path.join(d, '*.npy')):
        nm = os.path.basename(f)[:-4]
        a = np.load(f).astype(int)
        b = read_bc7_level0(os.path.join(PACK, nm + '.bc7')).astype(int)
        n += 1
        ta, tb = (a == 0).all(axis=-1), (b == 0).all(axis=-1)
        bad_alpha += int((ta != tb).sum())
        vis = ~ta & ~tb
        if vis.any():
            worst = max(worst, float(np.abs(a[..., :3] - b[..., :3])[vis].mean()))
    print(lab, 'files', n, 'worst mean colour diff', round(worst, 2), 'pixels with another transparency', bad_alpha)
for sid in ('6e595cab89', '2be5277d28', 'a096333c67', '1c0f2c14f4'):
    names = rect_names(sid)
    print(sid, 'rect files', sum(os.path.exists(os.path.join(PACK, x + '.bc7')) for x in names), '/', len(names))
print('png in pack', sum(1 for e in os.scandir(PACK) if e.name.endswith('.png')), 'tmp', sum(1 for e in os.scandir(PACK) if e.name.endswith('.tmp')))
