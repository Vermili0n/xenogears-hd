"""Shift chosen palette colours of a group (hair) to the SPRITE's colour in every frame - for groups drawn with the
wrong hair colour (Erich: brown instead of golden, Yui: grey-blond instead of bright yellow). Lightness moves too,
the render's shading inside the region is kept. Writes copies + a before|after sheet; the group's work/ is untouched.

  python hair_fix.py <group> <r,g,b> [<r,g,b> ...] [--mix 1.0] [--gate 30]
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from color_fix import COLOR, ROOT, Hero, fix_frame  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('group')
    ap.add_argument('colours', nargs='+', help='sprite palette colours to move, r,g,b')
    ap.add_argument('--mix', type=float, default=1.0, help='1 = all the way to the sprite colour')
    ap.add_argument('--gate', type=float, default=30.0)
    ap.add_argument('--sheet', type=int, default=12)
    a = ap.parse_args()
    card = {c['key']: c for c in json.load(open(os.path.join(COLOR, f'{a.group}_card.json')))}
    keys = []
    for t in a.colours:
        r, g, b = map(int, t.split(','))
        keys.append((r << 16) | (g << 8) | b)
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    h = Hero(os.path.join(ROOT, next(m['hero_dir'] for m in meta.values() if m['group'] == a.group)))
    work = os.path.join(ROOT, 'ai', 'prod_work', a.group, 'work')
    out_dir = os.path.join(COLOR, f'hair_{a.group}')
    os.makedirs(out_dir, exist_ok=True)
    measured = {k: {fr: lb for fr, lb, _, _ in card[k]['frames']} for k in keys}
    frames = sorted({(m['set'], m['frame']) for m in meta.values() if m['group'] == a.group})
    done = []
    for s, f in frames:
        name = f'{s}_{f:03d}_red.png'
        if not os.path.exists(os.path.join(work, name)):
            continue
        fixes = {}
        for k in keys:
            have = np.asarray(measured[k].get(f'{s}:{f}', card[k]['med']), np.float32)
            want = have + a.mix * (np.asarray(card[k]['sprite_lab'], np.float32) - have)
            fixes[k] = (have.tolist(), want.tolist())
        red = np.asarray(Image.open(os.path.join(work, name)).convert('RGB'))
        new, moved = fix_frame(h, s, f, red, fixes, gate=a.gate, ab_only=False)
        Image.fromarray(new).save(os.path.join(out_dir, name))
        done.append((moved, f'{s}:{f}', red, new))
    print(f'{a.group}: {len(done)} frames written to {out_dir}')
    done.sort(key=lambda x: -x[0])
    pick = done[:a.sheet]
    cells = []
    for _, fr, before, after in pick:
        hh = 260
        b = Image.fromarray(before)
        w = max(1, round(b.width * hh / b.height))
        pair = Image.new('RGB', (2 * w + 4, hh + 16), (40, 40, 40))
        pair.paste(b.resize((w, hh), Image.LANCZOS), (0, 16))
        pair.paste(Image.fromarray(after).resize((w, hh), Image.LANCZOS), (w + 4, 16))
        ImageDraw.Draw(pair).text((2, 2), f'{fr}  before | after', fill=(255, 255, 0))
        cells.append(pair)
    per_row = max(1, 1900 // (max(c.width for c in cells) + 8))
    rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
    W = max(sum(c.width + 8 for c in r) for r in rows)
    H = sum(max(c.height for c in r) + 8 for r in rows)
    sheet = Image.new('RGB', (W, H), (25, 25, 25))
    y = 0
    for r in rows:
        x = 0
        for c in r:
            sheet.paste(c, (x, y))
            x += c.width + 8
        y += max(c.height for c in r) + 8
    p = os.path.join(COLOR, f'{a.group}_hair_sheet.png')
    sheet.save(p)
    print(p, sheet.size)


if __name__ == '__main__':
    main()
