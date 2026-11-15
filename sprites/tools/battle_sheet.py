"""Sheet of a battle group as the game will draw it: sprite | sliced HD frame (game UV stretch), all frames of the set.

  python battle_sheet.py <group> <out prefix> [--k 4]       group = b_<set id>, c_<slug>_<id6> or o_<id> (battle_jobs.py);
parts from ai/prod_work/<group>/parts
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from battle_jobs import set_dir  # noqa: E402
from nisan_joe_post import game_frame  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('group')
    ap.add_argument('prefix')
    ap.add_argument('--k', type=int, default=4)
    a = ap.parse_args()
    h = Hero(set_dir(a.group))
    sk = list(h.layout)[0]
    parts = os.path.join(ROOT, 'ai', 'prod_work', a.group, 'parts')
    cache, cells = {}, []
    for fi in range(len(h.layout[sk]['frames'])):
        try:
            old, _ = h.assemble(h.placements(sk, fi))
        except Exception:  # noqa: BLE001  (empty frame)
            continue
        cells.append((fi, old.resize((old.width * 2, old.height * 2), Image.NEAREST), game_frame(h, sk, fi, parts, a.k, cache)))
    W, pages, pos, x, y, rh = 1990, [], [], 4, 4, 0
    for fi, o, n in cells:
        w = o.width + n.width + 8
        if x + w > W:
            x, y, rh = 4, y + rh + 14, 0
        if y + n.height + 14 > 1450 and pos:
            pages.append(pos)
            x, y, rh, pos = 4, 4, 0, []
        pos.append((fi, o, n, x, y))
        x += w
        rh = max(rh, n.height)
    pages.append(pos)
    for pi, pg in enumerate(pages, 1):
        c = Image.new('RGB', (W, max(p[4] + p[2].height + 16 for p in pg)), (150, 170, 90))
        d = ImageDraw.Draw(c)
        for fi, o, n, x, y in pg:
            d.text((x, y), str(fi), fill=(255, 255, 0))
            c.paste(o, (x, y + 12), o)
            c.paste(n, (x + o.width + 2, y + 12), n)
        c.save(f'{a.prefix}_{pi}.png')
        print(f'{a.prefix}_{pi}.png', c.size, len(pg))


if __name__ == '__main__':
    main()
