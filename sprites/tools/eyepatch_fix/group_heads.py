"""Faces of a few groups from their composites: sprite | composite (head area).  python group_heads.py <out.png> <group> ... [--per 8]"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from ai_redraw import Hero  # noqa: E402

META = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
ap = argparse.ArgumentParser()
ap.add_argument('out')
ap.add_argument('groups', nargs='+')
ap.add_argument('--per', type=int, default=8)
ap.add_argument('--k', type=int, default=6)
a = ap.parse_args()
cells = []
for g in a.groups:
    names = [n for n, m in META.items() if m['group'] == g and not n.endswith('__head')]
    names.sort()
    step = max(1, len(names) // a.per)
    for n in names[::step][:a.per]:
        m = META[n]
        h = Hero(os.path.join(ROOT, m['hero_dir']))
        old, _ = h.assemble(h.placements(m['set'], m['frame']))
        p = os.path.join(ROOT, 'ai', 'prod_work', g, 'work', f"{m['set']}_{m['frame']:03d}_red.png")
        if not os.path.exists(p):
            continue
        k = a.k
        c = int(old.height * 0.5) * k
        o = old.resize((old.width * k, old.height * k), Image.NEAREST).crop((0, 0, old.width * k, c))
        r = Image.open(p).convert('RGB').resize((old.width * k, old.height * k), Image.LANCZOS).convert('RGBA')
        r.putalpha(old.getchannel('A').resize(r.size, Image.NEAREST))
        cells.append((g.replace('m_', '') + ':' + n.split('__')[1].replace('npc_', ''), o, r.crop((0, 0, r.width, c))))
W, x, y, rh, pos = 1980, 6, 6, 0, []
for lab, o, r in cells:
    w = o.width + r.width + 10
    if x + w > W:
        x, y, rh = 6, y + rh + 4, 0
    pos.append((x, y, lab, o, r))
    x += w
    rh = max(rh, o.height + 16)
s = Image.new('RGB', (W, y + rh + 8), (150, 170, 90))
d = ImageDraw.Draw(s)
for x, y, lab, o, r in pos:
    d.text((x, y), lab, fill=(255, 255, 0))
    s.paste(o, (x, y + 13), o)
    s.paste(r, (x + o.width + 2, y + 13), r)
s.save(a.out)
print(a.out, s.size, len(pos))
