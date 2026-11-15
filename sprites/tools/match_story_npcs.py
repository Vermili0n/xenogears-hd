"""Find massovka NPC sets that are really heroes / story characters (special poses, flashbacks, map-only variants).

  python match_story_npcs.py   -> ai/story_match/matches.json + sheet_<k>.png
A massovka set matches an identity when it uses exactly one of that identity's palettes (Beetle CLUT crc32).
The sheets show the massovka set (3 frames) next to a reference frame of the identity for a visual check.
"""
import json
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from render_build import FC, HEROES, groups  # noqa: E402

OUT = os.path.join(ROOT, 'ai', 'story_match')
CELL = 120
PER_SHEET = 30


def identities():
    """{identity: (hero_dir, setkey of a reference frame, set of palettes)}"""
    ids = {}
    for h in HEROES:
        hd = os.path.join(ROOT, 'extracted', 'disc1_full', h)
        lay = json.load(open(os.path.join(hd, 'layout.json')))
        ids[h] = (hd, sorted(lay)[0], {p for v in lay.values() for p in v['palettes']})
    for slug in sorted(os.listdir(FC)):
        sp = os.path.join(FC, slug, 'sprite.json')
        if not os.path.exists(sp) or not os.path.exists(os.path.join(FC, slug, 'approved.txt')):
            continue
        s = json.load(open(sp))
        if s.get('root') != 'npc_full':
            continue
        pals = set()
        for n in [s['npc']] + s.get('variants', []):
            lay = json.load(open(os.path.join(ROOT, 'extracted', 'npc_full', n, 'layout.json')))
            pals |= {p for v in lay.values() for p in v['palettes']}
        ids[slug] = (os.path.join(ROOT, 'extracted', 'npc_full', s['npc']), 'npc', pals)
    return ids


def thumb(h, setkey, fi):
    im = frame_rgba(h, setkey, fi)
    bg = Image.new('RGBA', im.size, (200, 200, 200, 255))
    bg.alpha_composite(im)
    bg = bg.convert('RGB')
    bg.thumbnail((CELL, CELL), Image.LANCZOS)
    return bg


def main():
    os.makedirs(OUT, exist_ok=True)
    ids = identities()
    pal2id = {}
    for i, (_, _, ps) in ids.items():
        for p in ps:
            pal2id.setdefault(p, set()).add(i)
    matches = {}
    for g, hd, _, _ in groups('massovka'):
        lay = json.load(open(os.path.join(hd, 'layout.json')))
        ps = {p for v in lay.values() for p in v['palettes']}
        hit = {}
        for p in ps:
            for i in pal2id.get(p, ()):
                hit[i] = hit.get(i, 0) + 1
        if hit:
            best = max(hit, key=hit.get)
            matches[g] = {'hero_dir': os.path.relpath(hd, ROOT).replace('\\', '/'), 'identity': best,
                          'shared_palettes': hit[best], 'palettes': len(ps), 'others': sorted(set(hit) - {best})}
    json.dump(matches, open(os.path.join(OUT, 'matches.json'), 'w'), indent=1)
    heroes = {}
    items = sorted(matches.items(), key=lambda kv: (kv[1]['identity'], kv[0]))
    for k in range(0, len(items), PER_SHEET):
        chunk = items[k:k + PER_SHEET]
        cols = 2
        W = CELL * 4 + 20
        sheet = Image.new('RGB', (W * cols, ((len(chunk) + cols - 1) // cols) * (CELL + 16)), (40, 40, 40))
        d = ImageDraw.Draw(sheet)
        for j, (g, m) in enumerate(chunk):
            x, y = (j % cols) * W, (j // cols) * (CELL + 16)
            d.text((x + 2, y + 1), f'{k + j:03d} {g} -> {m["identity"]}', fill=(255, 255, 0))
            h = heroes.setdefault(m['hero_dir'], Hero(os.path.join(ROOT, m['hero_dir'])))
            n = len(h.layout['npc']['frames'])
            for c, fi in enumerate(sorted({0, n // 2, n - 1})[:3]):
                try:
                    sheet.paste(thumb(h, 'npc', fi), (x + c * CELL, y + 16))
                except Exception:  # noqa: BLE001
                    pass
            rd, rs, _ = ids[m['identity']]
            rh = heroes.setdefault(rd, Hero(rd))
            try:
                sheet.paste(thumb(rh, rs, 0), (x + 3 * CELL + 16, y + 16))
            except Exception:  # noqa: BLE001
                pass
        sheet.save(os.path.join(OUT, f'sheet_{k // PER_SHEET}.png'))
    print('matches', len(matches), 'sheets', (len(items) + PER_SHEET - 1) // PER_SHEET)


if __name__ == '__main__':
    main()
