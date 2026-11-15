"""Close-up sheet of chosen frames: python pick_sheet.py <out.png> <group>:<f,f,f> ...  (sprite x3 | HD as the game draws it)."""
import os
import sys

from PIL import Image, ImageDraw

ROOT = r'<XENO_SPRITES>'
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ai_redraw import Hero  # noqa: E402
from battle_jobs import set_dir  # noqa: E402
from nisan_joe_post import game_frame  # noqa: E402


def main():
    out = sys.argv[1]
    cells = []
    for spec in sys.argv[2:]:
        g, fl = spec.split(':')
        h = Hero(set_dir(g))
        sk = list(h.layout)[0]
        parts = os.path.join(ROOT, 'ai', 'prod_work', g, 'parts')
        cache = {}
        for f in fl.split(','):
            fi = int(f)
            old, _ = h.assemble(h.placements(sk, fi))
            n = game_frame(h, sk, fi, parts, 4, cache)
            cells.append((f'{g[2:8]}:{fi}', old.resize((old.width * 3, old.height * 3), Image.NEAREST), n))
    W, pos, x, y, rh = 1990, [], 4, 4, 0
    for lab, o, n in cells:
        w = o.width + n.width + 10
        if x + w > W:
            x, y, rh = 4, y + rh + 16, 0
        pos.append((lab, o, n, x, y))
        x += w
        rh = max(rh, n.height, o.height)
    c = Image.new('RGB', (W, y + rh + 20), (150, 170, 90))
    d = ImageDraw.Draw(c)
    for lab, o, n, x, y in pos:
        d.text((x, y), lab, fill=(255, 255, 0))
        c.paste(o, (x, y + 12), o)
        c.paste(n, (x + o.width + 4, y + 12), n)
    c.save(out)
    print(out, c.size)


if __name__ == '__main__':
    main()
