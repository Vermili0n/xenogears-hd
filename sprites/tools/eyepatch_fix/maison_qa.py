"""Maison's faces as the PACK has them now, drawn by the game's rule: every distinct head of his sets, large, sprite | pack. For the eye.
Set 1c0f2c has no complete block use (hd_sheet), its heads come from the composites.

  python maison_qa.py <out_prefix> [--k 8] [--top 0.40]
"""
import argparse
import hashlib
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import verify_0311 as v  # noqa: E402
from ai_redraw import Hero  # noqa: E402
from npc_rects import NPC  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('out')
ap.add_argument('--k', type=int, default=8)
ap.add_argument('--top', type=float, default=0.40)
ap.add_argument('--max-w', type=int, default=1990)
ap.add_argument('--max-h', type=int, default=1450)
a = ap.parse_args()
v.K = a.k
seen, cells = {}, []
for sid in ('6e595cab89', '2be5277d28', 'a096333c67'):
    h = Hero(os.path.join(NPC, sid))
    for fi in range(len(h.layout['npc']['frames'])):
        old, new = v.story_frame(sid, fi)
        if new is None:
            print('no sheet', sid, fi)
            continue
        c = int(old.height * a.top) * a.k
        n = new.crop((0, 0, new.width, c))
        key = hashlib.md5(n.tobytes()).hexdigest()
        lab = f'{sid[:6]}:{fi}'
        if key in seen:
            seen[key].append(lab)
            continue
        seen[key] = [lab]
        o = old.resize((old.width * a.k, old.height * a.k), Image.NEAREST).crop((0, 0, old.width * a.k, c))
        cells.append((lab, o, n))
sid = '1c0f2c14f4'
h = Hero(os.path.join(NPC, sid))
for fi in range(len(h.layout['npc']['frames'])):
    p = os.path.join(ROOT, 'ai', 'prod_work', 'c_maison_1c0f2c', 'work', f'npc_{fi:03d}_red.png')
    if not os.path.exists(p):
        continue
    old, _ = h.assemble(h.placements('npc', fi))
    r = Image.open(p).convert('RGB').resize((old.width * a.k, old.height * a.k), Image.LANCZOS).convert('RGBA')
    r.putalpha(old.getchannel('A').resize(r.size, Image.NEAREST))
    c = int(old.height * a.top) * a.k
    n = r.crop((0, 0, r.width, c))
    o = old.resize((old.width * a.k, old.height * a.k), Image.NEAREST).crop((0, 0, old.width * a.k, c))
    cells.append((f'{sid[:6]}:{fi} comp', o, n))
print('distinct heads', len(cells), {k: v_ for k, v_ in list(seen.items())[:0]})
pages, page, x, y, rh = [], [], 6, 6, 0
for lab, o, n in cells:
    w, h_ = o.width + n.width + 10, o.height + 16
    if x + w > a.max_w and page:
        x, y, rh = 6, y + rh + 4, 0
    if y + h_ > a.max_h and page:
        pages.append(page)
        page, x, y, rh = [], 6, 6, 0
    page.append((x, y, lab, o, n))
    x += w
    rh = max(rh, h_)
pages.append(page)
for pi, pg in enumerate(pages):
    H = max(c[1] + c[3].height + 20 for c in pg)
    s = Image.new('RGB', (a.max_w, H), (150, 170, 90))
    d = ImageDraw.Draw(s)
    for x, y, lab, o, n in pg:
        d.text((x, y), lab, fill=(255, 255, 0))
        s.paste(o, (x, y + 13), o)
        s.paste(n, (x + o.width + 2, y + 13), n)
    p = f'{a.out}_{pi + 1}.png'
    s.save(p)
    print(p, s.size, len(pg))
