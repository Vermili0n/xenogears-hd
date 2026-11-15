"""Head of a sprite frame as letters: which dark texels are what.  D 49 grey, G 74 grey, B 106/106/123 blue-grey, W white / pale,
s skin, o skin shadow, h hair, H hair shadow, . other, space = transparent.   python sprite_map.py set:frame ..."""
import os
import sys

import numpy as np

XS = r'<XENO_SPRITES>'
sys.path.insert(0, os.path.join(XS, 'tools'))
from ai_redraw import Hero  # noqa: E402

h = Hero(os.path.join(XS, 'extracted', 'disc1_full', 'bart'))
L = {(49, 49, 49): 'D', (74, 74, 74): 'G', (106, 106, 123): 'B', (255, 255, 255): 'W', (238, 230, 172): 'W', (222, 164, 90): 's',
     (180, 123, 49): 'o', (246, 222, 148): 'h', (205, 180, 106): 'h', (164, 139, 106): 'H'}
for it in sys.argv[1:]:
    s, fi = it.split(':')
    a = np.asarray(h.assemble(h.placements(s, int(fi)))[0])
    rows = np.where(a[..., 3].any(axis=1))[0]
    print('---', it)
    for y in range(rows[0], rows[0] + 18):
        print(f'{y - rows[0]:2d} ' + ''.join(' ' if a[y, x, 3] == 0 else L.get(tuple(int(v) for v in a[y, x, :3]), '.') for x in range(a.shape[1])))
