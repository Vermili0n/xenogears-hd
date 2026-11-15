"""How parts are shared between frames of the battle_rest groups, and what the QA skip lists really remove.
python share_stats.py"""
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = r'<XENO_SPRITES>'
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ai_redraw import Hero  # noqa: E402
from battle_jobs import set_dir  # noqa: E402
from color_local import teacher_offsets  # noqa: E402


def main():
    meta = json.load(open(os.path.join(ROOT, 'ai', 'redraw', 'battle_rest', 'meta.json')))
    groups = sorted({m['group'] for m in meta.values()})
    dec = json.load(open(os.path.join(ROOT, 'ai', 'redraw', 'battle_rest', 'qa_decisions.json')))
    tot = Counter()
    for g in groups:
        h = Hero(set_dir(g))
        sk = list(h.layout)[0]
        n = len(h.layout[sk]['frames'])
        use = defaultdict(set)
        area = {}
        for fi in range(n):
            try:
                pl = h.placements(sk, fi)
            except Exception:  # noqa: BLE001
                continue
            for p in pl:
                nm = f"{p['block']}-{p['pal']}"
                use[nm].add(fi)
                area[nm] = p['w'] * p['h']
        c = Counter(min(len(v), 5) for v in use.values())
        a_multi = sum(area[k] for k, v in use.items() if len(v) > 1) / max(1, sum(area.values()))
        skip = set(dec.get(g, {}).get('skip', []))
        only_skip = [k for k, v in use.items() if v <= skip]
        shared = [k for k, v in use.items() if v & skip and not v <= skip]
        mixed = [fi for fi in skip if any(not use[f"{p['block']}-{p['pal']}"] <= skip for p in h.placements(sk, fi))]
        print(f'{g}: frames {n}, parts {len(use)}, used in 1/2/3/4/5+ frames: {[c[i] for i in range(1, 6)]}, '
              f'area in shared parts {a_multi:.0%}; skip {len(skip)} frames -> parts only there {len(only_skip)}, '
              f'shared with kept {len(shared)}, skip frames still partly HD {len(mixed)}')
        tot['parts'] += len(use)
        tot['multi'] += sum(len(v) > 1 for v in use.values())
        tot['skipf'] += len(skip)
        tot['mixed'] += len(mixed)
    print(dict(tot))
    offs = teacher_offsets(os.path.join(ROOT, 'ai', 'pairs_v3'), lambda nn: (
        nn.split('__')[0].split('_')[1] if nn.startswith('h_') else nn.split('__')[0]))
    print('global teacher offset (a, b):', [round(x, 2) for x in offs.get('', [0, 0])], 'keys', len(offs))


if __name__ == '__main__':
    main()
