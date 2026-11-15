"""QA helpers for battle groups (parts in ai/prod_work/<group>/parts), the frames as the game will draw them.

  python battle_qa.py pick <out.png> <group>:<f,f,f> ...        close-up sheet: sprite x3 | HD x4 of the chosen frames
                                                                (several pages -> <out>_1.png, <out>_2.png ...)
  python battle_qa.py rank <out.json> <group> ...               per frame: how far the HD frame is from the sprite
  python battle_qa.py cmp <out.png> <work root> <group>:<f,f> ...  sprite x3 | parts of ai/prod_work | parts of <work root>
rank: HD frame box-reduced to native size, both blurred by 1 px, mean Lab distance inside the silhouette. Colour-anchored
sets differ from the sprite mostly by the drawn lines, so a frame far above its set's median has a wrong drawing
(stripes, blobs, a face on a mask). A sieve before the eyes, not a verdict. Writes {group: [[score, z, frame], ...]}.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from battle_jobs import set_dir  # noqa: E402
from nisan_joe_post import game_frame  # noqa: E402


def frames_of(group, work=None):
    h = Hero(set_dir(group))
    sk = list(h.layout)[0]
    return h, sk, os.path.join(work or os.path.join(ROOT, 'ai', 'prod_work'), group, 'parts'), len(h.layout[sk]['frames'])


def pick(out, specs, work=None):
    cells = []
    for spec in specs:
        g, fl = spec.split(':')
        h, sk, parts, _ = frames_of(g)
        cache, cache2 = {}, {}
        for f in fl.split(','):
            fi = int(f)
            old, _ = h.assemble(h.placements(sk, fi))
            n = game_frame(h, sk, fi, parts, 4, cache)
            if work:  # second version to the right of the first
                n2 = game_frame(h, sk, fi, frames_of(g, work)[2], 4, cache2)
                both = Image.new('RGBA', (n.width * 2 + 6, n.height), (0, 0, 0, 0))
                both.paste(n, (0, 0))
                both.paste(n2, (n.width + 6, 0))
                n = both
            cells.append((f'{g[2:8]}:{fi}', old.resize((old.width * 3, old.height * 3), Image.NEAREST), n))
    W, pages, pos, x, y, rh = 1990, [], [], 4, 4, 0
    for lab, o, n in cells:
        w = o.width + n.width + 10
        if x + w > W:
            x, y, rh = 4, y + rh + 16, 0
        if y + max(n.height, o.height) + 16 > 1900 and pos:
            pages.append(pos)
            x, y, rh, pos = 4, 4, 0, []
        pos.append((lab, o, n, x, y))
        x += w
        rh = max(rh, n.height, o.height)
    pages.append(pos)
    for k, pg in enumerate(pages, 1):
        c = Image.new('RGB', (W, max(p[4] + max(p[1].height, p[2].height) for p in pg) + 20), (150, 170, 90))
        d = ImageDraw.Draw(c)
        for lab, o, n, x, y in pg:
            d.text((x, y), lab, fill=(255, 255, 0))
            c.paste(o, (x, y + 12), o)
            c.paste(n, (x + o.width + 4, y + 12), n)
        f = out if len(pages) == 1 else f'{out[:-4]}_{k}.png'
        c.save(f)
        print(f, c.size, len(pg))


def score(old, hd):
    o = np.asarray(old.convert('RGBA'))
    n = np.asarray(hd.resize(old.size, Image.BOX).convert('RGBA'))
    m = (o[..., 3] > 0) & (n[..., 3] > 100)
    if m.sum() < 30:
        return None
    lo = cv2.blur(cv2.cvtColor(np.ascontiguousarray(o[..., :3]), cv2.COLOR_RGB2LAB).astype(np.float32), (3, 3))
    ln = cv2.blur(cv2.cvtColor(np.ascontiguousarray(n[..., :3]), cv2.COLOR_RGB2LAB).astype(np.float32), (3, 3))
    return float(np.linalg.norm(lo - ln, axis=-1)[m].mean())


def rank(out, groups):
    res = {}
    for g in groups:
        h, sk, parts, n = frames_of(g)
        cache, rows = {}, []
        for fi in range(n):
            try:
                old, _ = h.assemble(h.placements(sk, fi))
            except Exception:  # noqa: BLE001  (empty frame)
                continue
            s = score(old, game_frame(h, sk, fi, parts, 4, cache))
            if s is not None:
                rows.append((s, fi))
        v = np.array([s for s, _ in rows])
        med = float(np.median(v))
        mad = float(np.median(np.abs(v - med))) or 1.0
        res[g] = sorted(([round(s, 1), round((s - med) / mad, 1), fi] for s, fi in rows), reverse=True)
        print(g, 'frames', len(rows), 'median', round(med, 1), 'z>4:', [fi for _, z, fi in res[g] if z > 4], flush=True)
    json.dump(res, open(out, 'w'), indent=0)


if __name__ == '__main__':
    if sys.argv[1] == 'cmp':
        pick(sys.argv[2], sys.argv[4:], os.path.abspath(sys.argv[3]))
    else:
        {'pick': pick, 'rank': rank}[sys.argv[1]](sys.argv[2], sys.argv[3:])
