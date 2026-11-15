"""Parts of a frame: size, place, users, which users have a production composite, did the frame itself get rendered; picture of each part's pack file.
  python frame_parts.py <out.png> set:frame"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402

WORK = os.path.join(ROOT, 'ai', 'prod_work', 'h_bart', 'work')
RES = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod', 'v4')
JOBS = {j['name'] for j in json.load(open(os.path.join(ROOT, 'ai', 'prod', 'jobs_v4.json')))}
h = Hero(os.path.join(ROOT, 'extracted', 'disc1_full', 'bart'))
use = {}
for s in h.layout:
    for fi in range(len(h.layout[s]['frames'])):
        try:
            for p in h.placements(s, fi):
                use.setdefault(f"{p['block']}-{p['pal']}", set()).add((s, fi))
        except Exception:  # noqa: BLE001
            pass
s, fi = sys.argv[2].split(':')
fi = int(fi)
print(sys.argv[2], 'composite', os.path.exists(os.path.join(WORK, f'{s}_{fi:03d}_red.png')), 'render', os.path.exists(os.path.join(RES, f'h_bart__{s}_{fi:03d}.png')), 'job', f'h_bart__{s}_{fi:03d}' in JOBS)
pl = h.placements(s, fi)
x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
rows = []
for p in pl:
    nm = f"{p['block']}-{p['pal']}"
    u = sorted(use[nm])
    rend = [f'{a}:{b}' for a, b in u if os.path.exists(os.path.join(WORK, f'{a}_{b:03d}_red.png'))]
    print(nm, f"x{p['x'] - x0} y{p['y'] - y0} {p['w']}x{p['h']} flip {p['flipx']},{p['flipy']} users {len(u)} {u[:5]} rendered users {rend[:6]}")
    f = os.path.join(PACK, nm + '.bc7')
    rows.append((nm, h.part(p['block'], p['pal']).resize((p['w'] * 8, p['h'] * 8), Image.NEAREST), Image.fromarray(read_bc7_level0(f), 'RGBA') if os.path.exists(f) else None))
W = sum(max(a.width, 1) * 2 + 10 for _, a, _ in rows) + 8
H = max(a.height for _, a, _ in rows) * 2 + 30
c = Image.new('RGB', (W, H), (150, 170, 90))
d = ImageDraw.Draw(c)
x = 4
for nm, a, b in rows:
    d.text((x, 2), nm[:8], fill=(255, 255, 0))
    c.paste(a, (x, 14), a)
    if b is not None:
        c.paste(b, (x, 14 + a.height + 4), b)
    x += a.width + 8
c.save(sys.argv[1])
print(c.size)
