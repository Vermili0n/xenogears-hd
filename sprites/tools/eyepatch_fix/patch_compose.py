"""Eyepatch renders -> composites per seed (same compose_set call as prod_post, in folders of their own; nothing is touched
in ai/prod_work or the pack), then head sheets: sprite | in the game now | seed 7 | seed 11 | seed 23.

  python patch_compose.py compose          composites to ai/redraw/eyepatch/comp/<seed>/<group>/work
  python patch_compose.py sheets <prefix>  [--k 8] [--top 0.42]
"""
import argparse
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw

XS = r'<XENO_SPRITES>'
T = os.path.join(XS, 'tools')
R = os.path.join(XS, 'ai', 'redraw', 'eyepatch')
SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
from pack_heads import Hero, pack_frame  # noqa: E402
from patch_sheets import head_box  # noqa: E402

SEEDS = (7, 11, 23)


def reps():
    """rep job -> meta of the frame jobs only."""
    fmap = json.load(open(os.path.join(R, 'map.json')))
    meta = json.load(open(os.path.join(XS, 'ai', 'prod', 'meta.json')))
    return {k: meta[k] for k in fmap if not k.endswith('__head')}, meta


def offset_key(g):
    if g.startswith('h_'):
        return g[2:].split('_')[0]
    # c_<hero>_<id6> of the 9 heroes uses the hero's offset, like prod_post; the rest uses its own job name
    s = g[2:-7]
    return s if s in ('fei', 'elly', 'citan', 'bart', 'billy', 'rico', 'emeralda', 'chuchu', 'maria') else g


def compose():
    rp, meta = reps()
    groups = sorted({m['group'] for m in rp.values()})
    render = os.path.join(R, 'comp', '_render')
    os.makedirs(render, exist_ok=True)
    json.dump({k: meta[k] for k in rp}, open(os.path.join(render, 'meta.json'), 'w'))
    for s in SEEDS:
        for g in groups:
            work = os.path.join(R, 'comp', str(s), g, 'work')
            os.makedirs(work, exist_ok=True)
            r = subprocess.run([sys.executable, 'compose_set.py', '--render', render, '--res', os.path.join(R, f'res_{s}', 'v4'),
                                '--work', work, '--name', g, '--out-scale', '8', '--offset-key', offset_key(g)],
                               cwd=T, capture_output=True, text=True)
            print(s, g, r.stdout.strip()[-120:], r.stderr.strip()[-200:] if r.returncode else '', flush=True)


def sheets(a):
    rp, _ = reps()
    heroes, cache = {}, {}
    cells = []
    for name, m in sorted(rp.items(), key=lambda kv: (kv[1]['group'], kv[1]['set'], kv[1]['frame'])):
        if a.only and not any(name.endswith(o) for o in a.only.split(',')):
            continue
        h = heroes.setdefault(m['hero_dir'], Hero(os.path.join(XS, m['hero_dir'])))
        old, _ = h.assemble(h.placements(m['set'], m['frame']))
        y0, y1 = head_box(old, a.top)
        k = a.k
        o = old.crop((0, y0, old.width, y1)).resize((old.width * k, (y1 - y0) * k), Image.NEAREST)
        al = old.getchannel('A').resize((old.width * k, old.height * k), Image.NEAREST)
        ims = [o]
        if m['group'] == 'h_bart':
            now, _ = pack_frame(h, m['set'], m['frame'], k, cache)
            ims.append(now.crop((0, y0 * k, now.width, y1 * k)))
        else:
            p = os.path.join(XS, 'ai', 'prod_work', m['group'], 'work', f"{m['set']}_{m['frame']:03d}_red.png")
            cur = Image.open(p).convert('RGB').resize((old.width * k, old.height * k), Image.LANCZOS).convert('RGBA')
            cur.putalpha(al)
            ims.append(cur.crop((0, y0 * k, cur.width, y1 * k)))
        for s in SEEDS:
            p = os.path.join(R, 'comp', str(s), m['group'], 'work', f"{m['set']}_{m['frame']:03d}_red.png")
            im = Image.open(p).convert('RGB').resize((old.width * k, old.height * k), Image.LANCZOS).convert('RGBA')
            im.putalpha(al)
            ims.append(im.crop((0, y0 * k, im.width, y1 * k)))
        cells.append((name.split('__')[0].replace('c_bart_', '').replace('c_sigurd_harcourt_', 'sig').replace('h_bart', 'b') + ':' + name.split('__')[1], ims))
    pages, page, x, y, rh = [], [], 8, 8, 0
    W, H = a.max_w, a.max_h
    for lab, ims in cells:
        w = sum(i.width + 3 for i in ims) + 10
        h_ = ims[0].height + 16
        if x + w > W and page:
            x, y, rh = 8, y + rh + 4, 0
        if y + h_ > H and page:
            pages.append(page)
            page, x, y, rh = [], 8, 8, 0
        page.append((x, y, lab, ims))
        x += w
        rh = max(rh, h_)
    if page:
        pages.append(page)
    for pi, pg in enumerate(pages):
        hh = max(c[1] + c[3][0].height + 20 for c in pg)
        s = Image.new('RGB', (W, hh), (150, 170, 90))
        d = ImageDraw.Draw(s)
        for x, y, lab, ims in pg:
            d.text((x, y), lab + '  sprite|now|7|11|23', fill=(255, 255, 0))
            xx = x
            for i in ims:
                s.paste(i, (xx, y + 13), i if i.mode == 'RGBA' else None)
                xx += i.width + 3
        p = f'{a.prefix}_{pi + 1}.png'
        s.save(p)
        print(p, s.size, len(pg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['compose', 'sheets'])
    ap.add_argument('prefix', nargs='?')
    ap.add_argument('--k', type=int, default=8)
    ap.add_argument('--top', type=float, default=0.42)
    ap.add_argument('--max-w', type=int, default=2000)
    ap.add_argument('--max-h', type=int, default=1350)
    ap.add_argument('--only', default='', help='frame job name endings, comma separated')
    a = ap.parse_args()
    if a.cmd == 'compose':
        compose()
    else:
        sheets(a)


if __name__ == '__main__':
    main()
