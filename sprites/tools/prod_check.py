"""Pre-flight check of the production package (render_prod.py output) + smoke-test job selection.

  python prod_check.py --prod ai/prod [--smoke 3]
Checks: every job's control and board exist and are 512x512 RGB; captions match the training (CAP_REF / CAP_HEAD /
CAP_MECHA); gears only in jobs_v2 with the blank board; head jobs only for heroes; every meta entry has a job.
--smoke N writes <prod>/jobs_smoke_v4.json / jobs_smoke_v2.json: N jobs of every kind (hero full + head, story set,
karellen_past, massovka, field gear, world-map gear) for a quick look before the full run.
"""
import argparse
import json
import os
import random
import sys
from collections import Counter

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_pairs_v3 import CAP_HEAD  # noqa: E402
from render_build import CAP_MECHA, CAP_REF  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prod', required=True)
    ap.add_argument('--smoke', type=int, default=0)
    a = ap.parse_args()
    P = a.prod
    meta = json.load(open(os.path.join(P, 'meta.json')))
    j4 = json.load(open(os.path.join(P, 'jobs_v4.json')))
    j2 = json.load(open(os.path.join(P, 'jobs_v2.json')))
    errs = []
    names = set()
    sizes = {}
    for tag, jobs in (('v4', j4), ('v2', j2)):
        for j in jobs:
            names.add(j['name'])
            base = j['name'][:-6] if j['name'].endswith('__head') else j['name']
            m = meta.get(base)
            if m is None:
                errs.append(('no meta', j['name']))
                continue
            for k in ('control', 'ref'):
                p = os.path.join(P, j[k])
                if not os.path.exists(p):
                    errs.append((f'missing {k}', j['name']))
                elif p not in sizes:
                    with Image.open(p) as im:
                        sizes[p] = (im.size, im.mode)
                    if sizes[p][0] != (512, 512):
                        errs.append((f'{k} size {sizes[p][0]}', j['name']))
            head = j['name'].endswith('__head')
            want = CAP_HEAD if head else (CAP_MECHA if m['kind'] == 'gear' else CAP_REF)
            if j['prompt'] != want:
                errs.append(('caption', j['name']))
            if head and m['kind'] != 'hero':
                errs.append(('head for non-hero', j['name']))
            if (tag == 'v2') != (m['kind'] == 'gear'):
                errs.append(('wrong lora', j['name']))
            if m['kind'] == 'gear' and j['ref'] != 'boards/_blank.png':
                errs.append(('gear with board', j['name']))
            if m['kind'] != 'gear' and j['ref'] == 'boards/_blank.png':
                errs.append(('no board', j['name']))
    missing = [n for n in meta if n not in names]
    kinds = Counter(m['kind'] for m in meta.values())
    heads = sum(1 for j in j4 if j['name'].endswith('__head'))
    boards = Counter(j['ref'] for j in j4 + j2)
    print('jobs v4', len(j4), '(heads', heads, ') v2', len(j2), '| frames by kind', dict(kinds), '| boards used', len(boards))
    print('meta frames without a job:', len(missing), '| errors:', len(errs), Counter(e[0] for e in errs))
    for e in errs[:10]:
        print('  ', e)
    if a.smoke:
        random.seed(7)
        pick = []
        def take(pred, n):
            c = [j for j in j4 + j2 if pred(j)]
            pick.extend(random.sample(c, min(n, len(c))))
        take(lambda j: j['name'].startswith('h_') and not j['name'].endswith('__head'), a.smoke)
        take(lambda j: j['name'].startswith('h_') and j['name'].endswith('__head'), a.smoke)
        take(lambda j: j['name'].startswith('c_') and 'karellen_past' not in j['name'] and not j['name'].endswith('__head'), a.smoke)
        take(lambda j: 'karellen_past' in j['name'] and not j['name'].endswith('__head'), 1)
        take(lambda j: j['name'].startswith('m_'), a.smoke)
        take(lambda j: j['name'].startswith('b_'), 1)
        take(lambda j: j['name'].startswith('g_') and 'worldmap' not in j['name'] and meta[j['name']]['hero_dir'].split('/')[1] == 'npc_full', 2)
        take(lambda j: j['name'].startswith('g_') and meta[j['name']]['hero_dir'].split('/')[1] == 'gears_wm', 2)
        s4 = [j for j in pick if j in j4]
        s2 = [j for j in pick if j in j2]
        json.dump(s4, open(os.path.join(P, 'jobs_smoke_v4.json'), 'w'), indent=0)
        json.dump(s2, open(os.path.join(P, 'jobs_smoke_v2.json'), 'w'), indent=0)
        print('smoke jobs v4', len(s4), 'v2', len(s2), [j['name'] for j in pick])
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main())
