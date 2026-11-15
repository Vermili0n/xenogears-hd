"""Keyframe grids for a hero with approved references: field grids (sheet+face refs) and battle grids (face only).

  python hero_keys.py --hero bart --field 430_0:32 --battle 3007_0:16,2990_0:16
-> ai/keys_<hero>_field/in, ai/keys_<hero>_battle/in (grids + ref_sheet/ref_face/ref_style), ready for gem_batch.py.
Keyframes per set: the frames that bring new parts (greedy cover), evenly thinned to the requested count.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def cover(lay, s):
    fr = lay[s]['frames']
    parts = [{(p['block'], p['clut']) for p in f} for f in fr]
    allp = set().union(*parts)
    seen, cov = set(), []
    while seen != allp:
        b = max(range(len(fr)), key=lambda i: len(parts[i] - seen))
        if not parts[b] - seen:
            break
        cov.append(b)
        seen |= parts[b]
    return sorted(cov)


def thin(c, k):
    return c if len(c) <= k else [c[round(i * (len(c) - 1) / (k - 1))] for i in range(k)]


def build(hero, spec, kind, prefix):
    lay = json.load(open(os.path.join(ROOT, 'extracted', 'disc1_full', hero, 'layout.json')))
    frames = []
    for tok in spec.split(','):
        s, k = tok.split(':')
        frames += [f'{s}:{f}' for f in thin(cover(lay, s), int(k))]
    job = os.path.join(ROOT, 'ai', f'keys_{hero}_{kind}')
    shutil.rmtree(job, ignore_errors=True)
    subprocess.run([sys.executable, os.path.join(HERE, 'make_grids.py'), '--hero', hero, '--out', job,
                    '--frames', ','.join(frames), '--per', '16', '--prefix', prefix], check=True)
    refs = os.path.join(ROOT, 'for_chatgpt', hero)
    shutil.copy(os.path.join(refs, 'chatgpt_sheet.png'), os.path.join(job, 'in', 'ref_sheet.png'))
    shutil.copy(os.path.join(refs, 'chatgpt_face.png'), os.path.join(job, 'in', 'ref_face.png'))
    shutil.copy(os.path.join(ROOT, 'ai', 'or_test', 'in', 'ref_style.png'), os.path.join(job, 'in', 'ref_style.png'))
    print(kind, len(frames), 'frames ->', job)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', required=True)
    ap.add_argument('--field', required=True, help='set:count list')
    ap.add_argument('--battle', default='', help='set:count list')
    a = ap.parse_args()
    if not os.path.exists(os.path.join(ROOT, 'for_chatgpt', a.hero, 'approved.txt')):
        sys.exit(f'{a.hero}: references not approved yet (for_chatgpt/{a.hero}/approved.txt)')
    build(a.hero, a.field, 'field', 'f')
    if a.battle:
        build(a.hero, a.battle, 'battle', 'b')


if __name__ == '__main__':
    main()
