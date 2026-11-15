"""Plan (and count the cost of) the single Nano Banana keyframe run for the whole game.

  python plan_keys.py            -> prints grids per group and the estimated price, writes ai/keys_plan.json
Groups:
  heroes        9 party members: field set 32 keys + battle sets 32 keys (4 grids), refs sheet+face (+ face only in battle)
  characters    story NPCs with ChatGPT refs: 16 keys over all their sets (1 grid), refs sheet+face
  hero_npc      NPC sets that ARE party members (script-named Fei/Elly/...): 16 keys each, refs of that hero
  massovka      every other NPC set: 16 keys (1 grid), style reference only
Price: NB 2.1 batch 4K grid ~= $0.057; +20 % for retries.
"""
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'for_chatgpt')
HEROES = ['fei', 'elly', 'bart', 'citan', 'billy', 'rico', 'emeralda', 'chuchu', 'maria']
HERO_NAMES = {'Fei': 'fei', 'Elly': 'elly', 'Bart': 'bart', 'Citan': 'citan', 'Billy': 'billy', 'Rico': 'rico',
              'Emeralda': 'emeralda', 'Chu-Chu': 'chuchu', 'Maria': 'maria'}
GRID = 0.057


def main():
    named = json.load(open(os.path.join(ROOT, 'ai', 'npc_names_script.json')))
    idx = json.load(open(os.path.join(ROOT, 'extracted', 'npc_full', 'index.json')))
    plan = defaultdict(list)
    for h in HEROES:
        plan['heroes'].append({'slug': h, 'grids': 4})
    owned = set()
    for slug in sorted(os.listdir(D)):
        sp = os.path.join(D, slug, 'sprite.json')
        if slug in HEROES or not os.path.exists(sp):
            continue
        s = json.load(open(sp))
        if s.get('root') != 'npc_full':
            continue
        sets = [s['npc']] + s.get('variants', [])
        owned |= set(sets)
        ready = os.path.exists(os.path.join(D, slug, 'chatgpt_sheet.png'))
        plan['characters'].append({'slug': slug, 'sets': sets, 'grids': 1, 'refs_ready': ready})
    for nid, v in named.items():
        if v['name'] in HERO_NAMES and nid not in owned:
            plan['hero_npc'].append({'hero': HERO_NAMES[v['name']], 'nid': nid, 'grids': 1})
            owned.add(nid)
    for nid, v in idx.items():
        if nid not in owned and v['frames'] >= 2:
            plan['massovka'].append({'nid': nid, 'grids': 1, 'frames': v['frames']})
    total = 0
    for g, items in plan.items():
        n = sum(i['grids'] for i in items)
        total += n
        extra = ''
        if g == 'characters':
            extra = f"  (эталоны готовы у {sum(i['refs_ready'] for i in items)} из {len(items)})"
        print(f'{g:11s} {len(items):4d} шт  {n:4d} сеток  ~${n * GRID * 1.2:6.2f}{extra}')
    print(f'ИТОГО        {total:4d} сеток  ~${total * GRID * 1.2:.2f}')
    json.dump(plan, open(os.path.join(ROOT, 'ai', 'keys_plan.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
