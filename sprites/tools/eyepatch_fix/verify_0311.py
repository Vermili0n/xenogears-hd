"""After install_0311: read the PACK itself. Sheet: frames as the game draws them, from the installed files - story sets through their blocks
(uses.json), Bart through his parts - next to the sprite. Also compares every staged Bart part with its pack file.

  python verify_0311.py <out_prefix>
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from npc_rects import NPC, hd_sheet  # noqa: E402
from seam_fill_npc import rect as part_rect  # noqa: E402

BART = os.path.join(ROOT, 'ai', 'prod_work', 'h_bart_patch')
K, S = 7, 8
STORY = [('6e595cab89', 44), ('6e595cab89', 53), ('6e595cab89', 33), ('6e595cab89', 37), ('1c0f2c14f4', 45), ('2be5277d28', 44), ('a096333c67', 44),
         ('172669b371', 8), ('172669b371', 73), ('179511abf3', 73), ('195138629a', 8), ('70a4dcc69d', 33), ('bcc8990fb9', 33), ('9522cfbb67', 11), ('c7ad1d08fb', 24)]
HERO = [('430_0', 190), ('430_0', 194), ('430_0', 65), ('2356_0', 47), ('2354_0', 24), ('2354_0', 28), ('430_0', 132), ('430_0', 203), ('430_0', 140), ('430_0', 147)]


def game_part(c, w, h):
    H, W = c.shape[:2]
    tw = int(round((w - 1) * W / w)) if w > 1 else W
    th = int(round((h - 1) * H / h)) if h > 1 else H
    c = c[:th, :tw]
    rgb = Image.fromarray(np.ascontiguousarray(c[..., :3])).resize((w * K, h * K), Image.LANCZOS)
    rgb.putalpha(Image.fromarray(np.where(c[..., 3] > 0, 255, 0).astype(np.uint8)).resize((w * K, h * K), Image.NEAREST))
    return rgb


def story_frame(sid, fi):
    d = os.path.join(NPC, sid)
    h = Hero(d)
    sheet = np.load(os.path.join(d, 'page.npy'))
    u = json.load(open(os.path.join(d, 'uses.json')))
    pl = h.placements('npc', fi)
    old, _ = h.assemble(pl)
    x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
    out = Image.new('RGBA', (old.width * K, old.height * K), (0, 0, 0, 0))
    hd = {}
    for p in pl:
        pal = p['pal']
        if pal not in hd:
            hd[pal] = hd_sheet(u['uses'], pal, sheet.shape)
        if hd[pal] is None:
            return old, None
        sx, sy, w, h_ = part_rect(p['block'])
        im = game_part(hd[pal][sy * S:(sy + h_) * S, sx * S:(sx + w) * S], w, h_)
        if p['flipx']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        out.alpha_composite(im, ((p['x'] - x0) * K, (p['y'] - y0) * K))
    return old, out


def hero_frame(h, s, fi):
    pl = h.placements(s, fi)
    old, _ = h.assemble(pl)
    x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
    out = Image.new('RGBA', (old.width * K, old.height * K), (0, 0, 0, 0))
    for p in pl:
        f = os.path.join(PACK, f"{p['block']}-{p['pal']}.bc7")
        if not os.path.exists(f):
            continue
        im = game_part(read_bc7_level0(f), p['w'], p['h'])
        if p['flipx']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        out.alpha_composite(im, ((p['x'] - x0) * K, (p['y'] - y0) * K))
    return old, out


def main():
    sel = json.load(open(os.path.join(BART, 'selected.json')))['parts']
    diffs = []
    for nm in sel:
        a = np.asarray(Image.open(os.path.join(BART, 'stage', nm + '.png')).convert('RGBA')).astype(int)
        b = read_bc7_level0(os.path.join(PACK, nm + '.bc7')).astype(int)
        op = (a[..., 3] > 0) & (b[..., 3] > 0)
        diffs.append((float(np.abs(a[..., :3] - b[..., :3])[op].mean()) if op.any() else 0.0, int(((a[..., 3] > 0) != (b[..., 3] > 0)).sum()), nm))
    diffs.sort(reverse=True)
    print('bart parts', len(sel), 'worst colour diff / alpha mismatch px:', diffs[:3])
    print('png in pack:', sum(1 for e in os.scandir(PACK) if e.name.endswith('.png')))
    cells = []
    for sid, fi in STORY:
        old, new = story_frame(sid, fi)
        cells.append((f'{sid[:6]}:{fi}', old, new))
    h = Hero(os.path.join(ROOT, 'extracted', 'disc1_full', 'bart'))
    for s, fi in HERO:
        old, new = hero_frame(h, s, fi)
        cells.append((f'{s}:{fi}', old, new))
    W, x, y, rh = 1980, 6, 6, 0
    pos = []
    for lab, old, new in cells:
        c = int(old.height * 0.42) * K
        o = old.resize((old.width * K, old.height * K), Image.NEAREST).crop((0, 0, old.width * K, c))
        n = new.crop((0, 0, new.width, c)) if new is not None else Image.new('RGBA', o.size, (255, 0, 0, 255))
        w = o.width + n.width + 12
        if x + w > W:
            x, y, rh = 6, y + rh + 4, 0
        pos.append((x, y, lab, o, n))
        x += w
        rh = max(rh, o.height + 16)
    s = Image.new('RGB', (W, y + rh + 8), (150, 170, 90))
    d = ImageDraw.Draw(s)
    for x, y, lab, o, n in pos:
        d.text((x, y), lab, fill=(255, 255, 0))
        s.paste(o, (x, y + 13), o)
        s.paste(n, (x + o.width + 3, y + 13), n)
    s.save(sys.argv[1] + '.png')
    print(sys.argv[1] + '.png', s.size)


if __name__ == '__main__':
    main()
