"""Set 1c0f2c14f4: why hd_sheet finds no complete use (missing files / sizes); big view of chosen story frames from the pack.
  python verify_more.py <out.png> sid:frame ..."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(TOOLS)), 'xeno_bc7'))
import verify_0311 as v  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from npc_rects import NPC  # noqa: E402

sid = '1c0f2c14f4'
d = os.path.join(NPC, sid)
u = json.load(open(os.path.join(d, 'uses.json')))
sheet = np.load(os.path.join(d, 'page.npy'))
print('page', sheet.shape, 'palettes', u['palettes'], 'uses', len(u['uses']))
for use in u['uses'][:4]:
    miss, bad = 0, 0
    for b in use['blocks']:
        f = os.path.join(PACK, f"{b['hash']:x}-{u['palettes'][0]}.bc7")
        if not os.path.exists(f):
            miss += 1
            continue
        if read_bc7_level0(f).shape[:2] != (b['h'] * 8, b['w'] * 4 * 8):
            bad += 1
    print('use', {k: use[k] for k in use if k != 'blocks'}, 'blocks', len(use['blocks']), 'missing', miss, 'wrong size', bad)
v.K = 12
cells = []
for it in sys.argv[2:]:
    s, fi = it.split(':')
    old, new = v.story_frame(s, int(fi))
    c = int(old.height * 0.36) * v.K
    cells.append((it, old.resize((old.width * v.K, old.height * v.K), Image.NEAREST).crop((0, 0, old.width * v.K, c)), new.crop((0, 0, new.width, c))))
W = sum(o.width + n.width + 12 for _, o, n in cells) + 8
s = Image.new('RGB', (W, max(o.height for _, o, _n in cells) + 20), (150, 170, 90))
d2 = ImageDraw.Draw(s)
x = 4
for lab, o, n in cells:
    d2.text((x, 2), lab, fill=(255, 255, 0))
    s.paste(o, (x, 15), o)
    s.paste(n, (x + o.width + 3, 15), n)
    x += o.width + n.width + 12
s.save(sys.argv[1])
print(s.size)
