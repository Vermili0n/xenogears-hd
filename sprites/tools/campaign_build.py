"""Build every keyframe job of the one-shot Nano Banana run (heroes, story characters with references, gears).

  python campaign_build.py [--dry]    -> ai/campaign/<job>/in/{grid_*.png, grids.json, ref_*.png}, ai/campaign/jobs.json
Each job = one sprite folder (so prod_fit works per job); jobs.json: {job: {hero_dir, hero, prompt, refs, grids}}.
Keyframes = frames that bring new parts (greedy cover) thinned evenly; partial grids are padded by make_grids.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
from ai_redraw import Hero  # noqa: E402
OUT = os.path.join(ROOT, 'ai', 'campaign')
FC = os.path.join(ROOT, 'for_chatgpt')
STYLE = os.path.join(ROOT, 'ai', 'or_test', 'in', 'ref_style.png')
HEROES = ['fei', 'elly', 'bart', 'citan', 'billy', 'rico', 'emeralda', 'chuchu', 'maria']
DONE_FIELD_BATTLE = {'elly', 'bart', 'billy'}  # keyframes from the pilot (ai/keys_*, ai/pilot_elly_*) are reused


def cover(frames):
    parts = [{(p['block'], p['clut']) for p in f} for f in frames]
    allp = set().union(*parts) if parts else set()
    seen, cov = set(), []
    while seen != allp:
        b = max(range(len(frames)), key=lambda i: len(parts[i] - seen))
        if not parts[b] - seen:
            break
        cov.append(b)
        seen |= parts[b]
    return sorted(cov)


def thin(c, k):
    return c if len(c) <= k else [c[round(i * (len(c) - 1) / (k - 1))] for i in range(k)]


def whole_frames(lay, setkey, hero_dir):
    """Frames that show the whole figure: bbox height >= 75 % and opaque area >= 50 % of the set median
    (drops head-only / legs-only overlay frames used in cut-scenes)."""
    h = Hero(hero_dir)
    st = {}
    for i in range(len(lay[setkey]['frames'])):
        try:
            im, _ = h.assemble(h.placements(setkey, i))
            bb = im.getbbox()
            if bb:
                st[i] = (bb[3] - bb[1], sum(1 for px in im.getdata() if px[3]))
        except Exception:  # noqa: BLE001
            pass
    if not st:
        return set()
    mh = sorted(v[0] for v in st.values())[len(st) // 2]
    ma = sorted(v[1] for v in st.values())[len(st) // 2]
    return {i for i, (hh, ar) in st.items() if hh >= 0.75 * mh and ar >= 0.5 * ma}


def add_job(jobs, name, hero_dir, setkey, keys, prompt, refs, dry):
    lay = json.load(open(os.path.join(hero_dir, 'layout.json')))
    ok = whole_frames(lay, setkey, hero_dir)
    fr = thin([f for f in cover(lay[setkey]['frames']) if f in ok], keys)
    if not fr:
        return 0
    n = math.ceil(len(fr) / 16)
    jobs[name] = {'hero_dir': os.path.relpath(hero_dir, ROOT).replace('\\', '/'), 'set': setkey, 'frames': fr,
                  'prompt': prompt, 'refs': list(refs), 'grids': n}
    if dry:
        return n
    d = os.path.join(OUT, name)
    shutil.rmtree(d, ignore_errors=True)
    subprocess.run([sys.executable, os.path.join(HERE, 'make_grids.py'), '--hero', name, '--hero-dir', hero_dir,
                    '--out', d, '--frames', ','.join(f'{setkey}:{f}' for f in fr), '--per', '16', '--prefix', 'g', '--grow'],
                   check=True, capture_output=True)
    for r, src in refs.items():
        shutil.copy(src, os.path.join(d, 'in', f'ref_{r}.png'))
    return n


def refs_of(slug, face_only=False):
    r = {} if face_only else {'sheet': os.path.join(FC, slug, 'chatgpt_sheet.png')}
    r['face'] = os.path.join(FC, slug, 'chatgpt_face.png')
    r['style'] = STYLE
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    jobs, total = {}, {'heroes': 0, 'characters': 0, 'gears': 0}
    # heroes
    for h in HEROES:
        hd = os.path.join(ROOT, 'extracted', 'disc1_full', h)
        lay = json.load(open(os.path.join(hd, 'layout.json')))
        sets = list(lay)
        field = [s for s in sets if 400 <= int(s.split('_')[0]) < 450]
        battle = sorted([s for s in sets if 2988 <= int(s.split('_')[0]) <= 3017], key=lambda s: -len(lay[s]['frames']))[:2]
        scenes = [s for s in sets if 2336 <= int(s.split('_')[0]) <= 2460]
        if h == 'emeralda':  # child (433) and adult (437) forms have their own references
            total['heroes'] += add_job(jobs, 'h_emeralda_field', hd, '433_0', 32, 'hero.txt', refs_of('emeralda'), a.dry)
            total['heroes'] += add_job(jobs, 'h_emeralda_adult', hd, '437_0', 16, 'hero.txt', refs_of('emeralda_adult'), a.dry)
            for s in battle:
                total['heroes'] += add_job(jobs, f'h_emeralda_b{s}', hd, s, 16, 'hero_face.txt', refs_of('emeralda', True), a.dry)
            continue
        if h not in DONE_FIELD_BATTLE:
            for s in field[:1]:
                total['heroes'] += add_job(jobs, f'h_{h}_field', hd, s, 32, 'hero.txt', refs_of(h), a.dry)
            for s in battle:
                total['heroes'] += add_job(jobs, f'h_{h}_b{s}', hd, s, 16, 'hero_face.txt', refs_of(h, True), a.dry)
        if scenes:  # one grid over all scene sets: pick the biggest scene set
            s = max(scenes, key=lambda s: len(lay[s]['frames']))
            total['heroes'] += add_job(jobs, f'h_{h}_scene', hd, s, 16, 'hero.txt', refs_of(h), a.dry)
    # story characters
    for slug in sorted(os.listdir(FC)):
        d = os.path.join(FC, slug)
        sp = os.path.join(d, 'sprite.json')
        if slug in HEROES or slug == 'emeralda_adult' or not (os.path.exists(os.path.join(d, 'approved.txt')) and os.path.exists(sp)):
            continue
        s = json.load(open(sp))
        if s.get('root') != 'npc_full':
            continue
        sets = [s['npc']] + s.get('variants', [])
        covs = {n: len(cover(json.load(open(os.path.join(ROOT, 'extracted', 'npc_full', n, 'layout.json')))['npc']['frames'])) for n in sets}
        c = sum(covs.values())
        g = 1 if c <= 40 else (2 if c <= 120 else 3)
        for i, n in enumerate(sorted(sets, key=lambda n: -covs[n])):
            k = max(4, round(16 * g * covs[n] / c)) if i else max(16, round(16 * g * covs[n] / c))
            k = min(k, covs[n])
            if k < 4 and i:
                continue
            total['characters'] += add_job(jobs, f'c_{slug}_{n[:6]}', os.path.join(ROOT, 'extracted', 'npc_full', n), 'npc',
                                           k, 'hero.txt', refs_of(slug), a.dry)
    # gears (pre-rendered 3D: mecha prompt, style only)
    for g in sorted(os.listdir(os.path.join(ROOT, 'for_gears'))):
        sp = os.path.join(ROOT, 'for_gears', g, 'sprite.json')
        if not os.path.exists(sp):
            continue
        s = json.load(open(sp))
        if s.get('kind') == 'field':
            hd, setkey = os.path.join(ROOT, 'extracted', 'npc_full', s['npc']), 'npc'
        else:
            hd = os.path.join(ROOT, 'extracted', 'gears_wm', f"{s['file']}_-1_0")
            setkey = f"{s['file']}_0"
        total['gears'] += add_job(jobs, f'g_{g}', hd, setkey, 16, 'mecha.txt', {}, a.dry)
    json.dump(jobs, open(os.path.join(OUT, 'jobs.json'), 'w'), indent=1)
    n = sum(total.values())
    print(total, 'grids', n, f'~${n * 0.057:.2f} batch 4K (+20 % retries ~${n * 0.057 * 1.2:.2f})', 'jobs', len(jobs))


if __name__ == '__main__':
    main()
