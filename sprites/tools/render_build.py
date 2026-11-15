"""Render manifest for LoRA v2 on the pod: one control per unique frame + the character board, as in training.

  python render_build.py --tier important|massovka|battle [--out ai/render_<tier>] [--count]
Writes <out>/control/<name>.png, <out>/boards/<slug>.png, <out>/jobs.json ([{name, control, ref, prompt}], paths relative
to <out>) and <out>/dups.json ({name: [same-frame names]}: identical part layouts are rendered once and copied).
Tiers: important = heroes + story characters with an approved reference + gears; massovka = other map NPC sets;
battle = battle sprite sets (no board).
"""
import argparse
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from make_pairs import place  # noqa: E402
from make_pairs_v2 import ref_board  # noqa: E402

FC = os.path.join(ROOT, 'for_chatgpt')
HEROES = ['fei', 'elly', 'bart', 'citan', 'billy', 'rico', 'emeralda', 'chuchu', 'maria']
CAP_REF = ('redraw this pixel-art sprite as a clean 90s anime illustration of the character shown in the second image, '
           'same pose and silhouette, flat magenta background')
CAP_NOREF = 'redraw this pixel-art sprite as a clean 90s anime illustration, same pose, colors and silhouette, flat magenta background'
CAP_MECHA = 'redraw this pre-rendered mecha sprite as a clean detailed illustration, same pose and silhouette, flat magenta background'
BLANK = '_blank'


def sig(f):
    return tuple(sorted(tuple(sorted((k, str(v)) for k, v in p.items())) for p in f))


def groups(tier):
    """[(group, hero_dir, {setkey: board slug or BLANK}, caption)]"""
    out = []
    story, gears = set(), set()
    for slug in sorted(os.listdir(FC)):
        sp = os.path.join(FC, slug, 'sprite.json')
        if slug in HEROES or not os.path.exists(sp) or not os.path.exists(os.path.join(FC, slug, 'approved.txt')):
            continue
        s = json.load(open(sp))
        if s.get('root') == 'npc_full':
            for n in [s['npc']] + s.get('variants', []):
                if n not in story:
                    story.add(n)
                    if tier == 'important':
                        out.append((f'c_{slug}_{n[:6]}', os.path.join(ROOT, 'extracted', 'npc_full', n), {'npc': slug}, CAP_REF))
    # map NPC sets that are really heroes / story characters (palette match + visual check, match_story_npcs.py):
    # rendered with that character's board; sets with a broken part assembly are left out until re-extracted
    sm = os.path.join(ROOT, 'ai', 'story_match', 'decisions.json')
    dec = json.load(open(sm)) if os.path.exists(sm) else {}
    for n, slug in sorted(dec.get('confirmed', {}).items()):
        if n not in story:
            story.add(n)
            if tier == 'important':
                out.append((f'c_{slug}_{n[:6]}', os.path.join(ROOT, 'extracted', 'npc_full', n), {'npc': slug}, CAP_REF))
    story |= set(dec.get('broken_assembly', {}))
    for g in sorted(os.listdir(os.path.join(ROOT, 'for_gears'))):
        sp = os.path.join(ROOT, 'for_gears', g, 'sprite.json')
        if not os.path.exists(sp):
            continue
        s = json.load(open(sp))
        if s.get('kind') == 'field':
            gears.add(s['npc'])
            hd = os.path.join(ROOT, 'extracted', 'npc_full', s['npc'])
        else:
            hd = os.path.join(ROOT, 'extracted', 'gears_wm', f"{s['file']}_-1_0")
        if tier == 'important':
            lay = json.load(open(os.path.join(hd, 'layout.json')))
            out.append((f'g_{g}', hd, {k: BLANK for k in lay}, CAP_MECHA))
    if tier == 'important':
        for h in HEROES:
            hd = os.path.join(ROOT, 'extracted', 'disc1_full', h)
            lay = json.load(open(os.path.join(hd, 'layout.json')))
            out.append((f'h_{h}', hd, {k: ('emeralda_adult' if h == 'emeralda' and k.startswith('437_') else h) for k in lay}, CAP_REF))
    elif tier == 'massovka':
        base = os.path.join(ROOT, 'extracted', 'npc_full')
        for n in sorted(os.listdir(base)):
            if n not in story and n not in gears and os.path.exists(os.path.join(base, n, 'layout.json')):
                out.append((f'm_{n[:10]}', os.path.join(base, n), {'npc': BLANK}, CAP_NOREF))
    elif tier == 'battle':
        base = os.path.join(ROOT, 'extracted', 'battle')
        for n in sorted(os.listdir(base)):
            p = os.path.join(base, n, 'layout.json')
            if os.path.exists(p):
                out.append((f'b_{n}', os.path.join(base, n), {k: BLANK for k in json.load(open(p))}, CAP_NOREF))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tier', required=True, choices=['important', 'massovka', 'battle'])
    ap.add_argument('--out')
    ap.add_argument('--count', action='store_true', help='only print frame counts')
    a = ap.parse_args()
    out = a.out or os.path.join(ROOT, 'ai', f'render_{a.tier}')
    jobs, dups, total = [], {}, 0
    if not a.count:
        for d in ('control', 'boards'):
            os.makedirs(os.path.join(out, d), exist_ok=True)
        Image.new('RGB', (512, 512), (205, 205, 205)).save(os.path.join(out, 'boards', BLANK + '.png'))
    for group, hd, boards, cap in groups(a.tier):
        lay = json.load(open(os.path.join(hd, 'layout.json')))
        h = None if a.count else Hero(hd)
        seen = {}
        for setkey, slug in boards.items():
            if setkey not in lay:
                continue
            for fi, fr in enumerate(lay[setkey]['frames']):
                total += 1
                name = f'{group}__{setkey}_{fi:03d}'
                key = (sig(fr), slug)
                if key in seen:
                    dups.setdefault(seen[key], []).append(name)
                    continue
                seen[key] = name
                if a.count:
                    jobs.append(name)
                    continue
                try:
                    c = place(frame_rgba(h, setkey, fi), 512, 500)
                except Exception:  # noqa: BLE001  (empty / broken frame)
                    continue
                c.save(os.path.join(out, 'control', name + '.png'))
                bp = os.path.join(out, 'boards', slug + '.png')
                if slug != BLANK and not os.path.exists(bp):
                    ref_board(slug).save(bp)
                jobs.append({'name': name, 'control': f'control/{name}.png', 'ref': f'boards/{slug}.png',
                             'prompt': CAP_NOREF if slug == BLANK and cap == CAP_REF else cap})
    print(a.tier, 'frames', total, 'unique', len(jobs))
    if not a.count:
        json.dump(jobs, open(os.path.join(out, 'jobs.json'), 'w'), indent=0)
        json.dump(dups, open(os.path.join(out, 'dups.json'), 'w'))


if __name__ == '__main__':
    main()
