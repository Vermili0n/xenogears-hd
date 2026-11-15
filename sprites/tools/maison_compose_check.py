"""Maison: new head renders (ai/redraw/maison2) + the current full renders -> composites of all his sets, without touching the pack or
ai/prod_work. Then a sheet: sprite | now | new, one per distinct control.

  python maison_compose_check.py <sheet_prefix>
"""
import json
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402

M1 = os.path.join(ROOT, 'ai', 'redraw', 'maison')
M2 = os.path.join(ROOT, 'ai', 'redraw', 'maison2')
F = os.path.join(M2, 'final')
RES = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod', 'v4')
META = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
K = 5


def main():
    fmap = json.load(open(os.path.join(M1, 'map.json')))
    done = {f[:-4] for f in os.listdir(os.path.join(M2, 'm_7_60', 'v4'))}
    res = os.path.join(F, 'v4')
    os.makedirs(res, exist_ok=True)
    head_of = {}
    for rep, names in fmap.items():
        for n in names:
            head_of[n] = rep
    names = [n for n in META if n.startswith('c_maison_')]
    for n in names:
        shutil.copyfile(os.path.join(RES, n + '.png'), os.path.join(res, n + '.png'))
        h = n + '__head'
        rep = head_of.get(h, h)
        src = os.path.join(M2, 'm_7_60', 'v4', rep + '.png') if rep in done else os.path.join(RES, h + '.png')
        shutil.copyfile(src, os.path.join(res, h + '.png'))
    render = os.path.join(F, '_render')
    os.makedirs(render, exist_ok=True)
    json.dump({n: META[n] for n in names}, open(os.path.join(render, 'meta.json'), 'w'))
    bad = {}
    groups = sorted({META[n]['group'] for n in names})
    for g in groups:
        w = os.path.join(F, g, 'work')
        os.makedirs(w, exist_ok=True)
        r = subprocess.run([sys.executable, 'compose_set.py', '--render', render, '--res', res, '--work', w, '--name', g, '--out-scale', '8',
                            '--offset-key', g], cwd=HERE, capture_output=True, text=True)
        print(g, r.stdout.strip()[-80:], r.stderr.strip()[-300:] if r.returncode else '', flush=True)
        c = json.load(open(os.path.join(F, g, 'compose.json')))
        bad.update({k: v for k, v in c.items() if v.get('head') != 'pass'})
    print('head pass not used:', len(bad), list(bad.items())[:12])
    seen, cells = set(), []
    for n in names:
        h = n + '__head'
        rep = head_of.get(h, h)
        if rep in seen or rep not in done:
            continue
        seen.add(rep)
        m = META[n]
        hero = Hero(os.path.join(ROOT, m['hero_dir']))
        old, _ = hero.assemble(hero.placements(m['set'], m['frame']))
        fn = f"{m['set']}_{m['frame']:03d}_red.png"
        al = old.getchannel('A').resize((old.width * K, old.height * K), Image.NEAREST)
        ims = [old.resize((old.width * K, old.height * K), Image.NEAREST)]
        for p in (os.path.join(ROOT, 'ai', 'prod_work', m['group'], 'work', fn), os.path.join(F, m['group'], 'work', fn)):
            i = Image.open(p).convert('RGB').resize((old.width * K, old.height * K), Image.LANCZOS).convert('RGBA')
            i.putalpha(al)
            ims.append(i)
        c = int(old.height * K * 0.42)
        cells.append((n.replace('c_maison_', '').replace('__npc', ''), [i.crop((0, 0, i.width, c)) for i in ims]))
    W, x, y, rh = 1980, 6, 6, 0
    pos = []
    for lab, ims in cells:
        w = sum(i.width + 2 for i in ims) + 8
        if x + w > W:
            x, y, rh = 6, y + rh + 4, 0
        pos.append((x, y, lab, ims))
        x += w
        rh = max(rh, ims[0].height + 15)
    s = Image.new('RGB', (W, y + rh + 8), (150, 170, 90))
    d = ImageDraw.Draw(s)
    for x, y, lab, ims in pos:
        d.text((x, y), lab, fill=(255, 255, 0))
        xx = x
        for i in ims:
            s.paste(i, (xx, y + 13), i)
            xx += i.width + 2
    s.save(sys.argv[1] + '.png')
    print(sys.argv[1] + '.png', s.size, len(pos))


if __name__ == '__main__':
    main()
