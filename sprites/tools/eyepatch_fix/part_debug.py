"""Facts for a frame's head: per part - users, is it in the selection, pack / sliced / staged picture next to the frame's composite crop;
then which part really draws each texel of the head (letters) and which of those parts are not staged.
  python part_debug.py <out_prefix> set:frame [rows]"""
import json
import os
import string
import sys

import numpy as np
from PIL import Image, ImageDraw

XS = r'<XENO_SPRITES>'
SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
sys.path.insert(0, os.path.join(XS, 'tools'))
sys.path.insert(0, r'<XENO_BC7>')
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from pack_heads import Hero  # noqa: E402

B = os.path.join(XS, 'ai', 'prod_work', 'h_bart_patch')
h = Hero(os.path.join(XS, 'extracted', 'disc1_full', 'bart'))
sel = set(json.load(open(os.path.join(B, 'selected.json')))['parts'])
use = {}
for s in h.layout:
    for fi in range(len(h.layout[s]['frames'])):
        try:
            for p in h.placements(s, fi):
                use.setdefault(f"{p['block']}-{p['pal']}", set()).add(f'{s}:{fi}')
        except Exception:  # noqa: BLE001
            pass
s, fi = sys.argv[2].split(':')
fi = int(fi)
rows_n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
pl = h.placements(s, fi)
old, (x0, y0) = h.assemble(pl)
W, H = old.size
idb = np.full((H, W), -1)
for i, p in enumerate(pl):
    im = h.part(p['block'], p['pal'])
    if p['flipx']:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if p['flipy']:
        im = im.transpose(Image.FLIP_TOP_BOTTOM)
    a = np.asarray(im)[..., 3] > 0
    ys, xs = np.nonzero(a)
    idb[ys + p['y'] - y0, xs + p['x'] - x0] = i
L = string.ascii_uppercase + string.ascii_lowercase
for i, p in enumerate(pl):
    n = f"{p['block']}-{p['pal']}"
    vis = int((idb[:rows_n] == i).sum())
    print(L[i], n, f"x{p['x'] - x0} y{p['y'] - y0} {p['w']}x{p['h']} flip {p['flipx']},{p['flipy']} head texels {vis}", 'SELECTED' if n in sel else 'not selected',
          'users', len(use[n]), sorted(use[n])[:5])
for y in range(rows_n):
    print(f'{y:2d} ' + ''.join(' ' if v < 0 else L[v] for v in idb[y]))
red = np.asarray(Image.open(os.path.join(B, 'work', f'{s}_{fi:03d}_red.png')).convert('RGB'))
Z = 2
cells = []
for i, p in enumerate(pl):
    n = f"{p['block']}-{p['pal']}"
    if (idb[:rows_n] == i).sum() == 0:
        continue
    row = [('native', h.part(p['block'], p['pal']).convert('RGBA').resize((p['w'] * 8, p['h'] * 8), Image.NEAREST))]
    f = os.path.join(PACK, n + '.bc7')
    if os.path.exists(f):
        row.append(('pack', Image.fromarray(read_bc7_level0(f), 'RGBA').resize((p['w'] * 8, p['h'] * 8), Image.NEAREST)))
    for lab, d in (('sliced', 'parts'), ('staged', 'stage')):
        f = os.path.join(B, d, n + '.png')
        if os.path.exists(f):
            row.append((lab, Image.open(f).convert('RGBA').resize((p['w'] * 8, p['h'] * 8), Image.NEAREST)))
    X, Y = (p['x'] - x0) * 8, (p['y'] - y0) * 8
    c = Image.fromarray(red).crop((X, Y, X + p['w'] * 8, Y + p['h'] * 8))
    if p['flipx']:
        c = c.transpose(Image.FLIP_LEFT_RIGHT)
    if p['flipy']:
        c = c.transpose(Image.FLIP_TOP_BOTTOM)
    row.append(('composite here', c.convert('RGBA')))
    cells.append((L[i] + ' ' + n, row))
TW = max(sum(i.width * Z + 6 for _, i in r) for _, r in cells) + 8
TH = sum(max(i.height for _, i in r) * Z + 30 for _, r in cells) + 4
sh = Image.new('RGB', (TW, TH), (150, 170, 90))
d = ImageDraw.Draw(sh)
y = 2
for lab, r in cells:
    d.text((4, y), lab + '   ' + ' | '.join(l for l, _ in r), fill=(255, 255, 0))
    x = 4
    for _, i in r:
        j = i.resize((i.width * Z, i.height * Z), Image.NEAREST)
        sh.paste(j, (x, y + 14), j)
        x += j.width + 6
    y += max(i.height for _, i in r) * Z + 30
sh.save(sys.argv[1] + '.png')
print(sh.size)
