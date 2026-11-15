"""Assign NPC sprite sets to character folders from the game's own data and rebuild their packages.

  python assign_sprites.py
Sources (in this order):
  1. script names (ai/npc_names_script.json, from npc_names.py): the entity wearing the set speaks as <Name>
  2. SCENE: sets seen with the speaker in flashback cut-scenes (checked by eye, listed below)
  3. FEI_CHILD / NOSPRITE: characters drawn with Fei's sprite / without any field sprite
Writes for_chatgpt/<slug>/sprite.json {npc, root, variants, source} and 2_sprite_front_side_back.png; clears HOLD.txt.
"""
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from char_package import strip, views  # noqa: E402

D = os.path.join(ROOT, 'for_chatgpt')
NPC = os.path.join(ROOT, 'extracted', 'npc_full')
SPEAKER = {  # folder -> in-game speaker name (USA text)
    'alice': 'Alice', 'dan': 'Dan', 'timothy': 'Timothy', 'chief_lee': 'Chief Lee', 'marguerite_fatima': 'Margie',
    'sigurd_harcourt': 'Sigurd', 'kahran_ramsus': 'Ramsus', 'karellen': 'Krelian', 'myyah_hawwa': 'Miang',
    'hammer_xenogears': 'Hammer', 'dominia_yizkor': 'Dominia', 'jessie_black': 'Jessie', 'shakhan': 'Shakhan',
    'big_joe': 'Big Joe', 'zephyr': 'Zephyr', 'kelvena': 'Kelvena', 'wiseman': 'Wiseman', 'taura_melchior': 'Taura',
    'isaac_stone': 'Stone', 'midori_uzuki': 'Midori', 'primera_black': 'Primera', 'kim': 'Kim', 'yui_uzuki': 'Yui',
    'sigmund': 'Sigmund', 'franz': 'Franz', 'seraphita': 'Seraphita', 'id': 'Id', 'gaspar_uzuki': 'Gaspar',
    'medena_van_houten': 'Medena', 'tolone': 'Tolone', 'agnes': 'Agnes', 'grahf': 'Grahf', 'captain': 'Captain',
    'erich_van_houten': 'Erich', 'maison': 'Maison', 'rue_cohen': 'Rue', 'verlaine': 'Verlaine',
    'vanderkaum': 'Vanderkaum', 'leonardo': 'Leonardo', 'suzarn': 'Suzarn', 'latina': 'Latina',
}
SCENE = {  # flashback speakers: the only unnamed sets present on (nearly) all of their maps, checked by eye
    'roni_fatima': ['44f27d4ef0'], 'rene_fatima': ['7b3593ff53'], 'sophia': ['aae37c0c65', '6f3bf78799'],
    'karen_wong': ['a39520c161'],
}
PREFER = {'kelvena': 'c428d16107'}  # several sets speak as this name (gear + pilot): the human one is the main
FEI_CHILD = ['abel_xenogears', 'the_coward', 'lacan']
NOSPRITE = ['deus', 'Broyer', 'Helmholz', 'Vance', 'renk', 'stratski']


def main():
    named = json.load(open(os.path.join(ROOT, 'ai', 'npc_names_script.json')))
    by = defaultdict(list)
    for nid, v in named.items():
        if v['share'] >= 0.7:
            by[v['name']].append((v['n'], nid))
    report = []
    for slug in sorted(os.listdir(D)):
        d = os.path.join(D, slug)
        if not os.path.isdir(d):
            continue
        sets, src = [], ''
        if slug in SPEAKER and by.get(SPEAKER[slug]):
            sets = [nid for _, nid in sorted(by[SPEAKER[slug]], reverse=True)]
            if slug in PREFER and PREFER[slug] in sets:
                sets.remove(PREFER[slug])
                sets.insert(0, PREFER[slug])
            src = f'script:{SPEAKER[slug]}'
        elif slug in SCENE:
            sets, src = SCENE[slug], 'scene'
        elif slug in FEI_CHILD:
            open(os.path.join(d, 'FEI.txt'), 'w', encoding='utf-8').write(
                'рисуется по эталону Фея (тот же персонаж/спрайт Фея) — ChatGPT не нужен\n')
            report.append((slug, 'Fei'))
            continue
        elif slug in NOSPRITE:
            open(os.path.join(d, 'NOSPRITE.txt'), 'w', encoding='utf-8').write('спрайта в игре нет — эталон не нужен\n')
            report.append((slug, 'nosprite'))
            continue
        if not sets:
            if slug not in ('fei', 'elly', 'bart', 'citan', 'billy', 'rico', 'emeralda', 'emeralda_adult', 'chuchu', 'maria'):
                report.append((slug, '-'))
            continue
        h = Hero(os.path.join(NPC, sets[0]))
        fr = views(h)
        strip(h, fr, os.path.join(d, '2_sprite_front_side_back.png'))
        json.dump({'npc': sets[0], 'root': 'npc_full', 'variants': sets[1:], 'frames': fr, 'source': src},
                  open(os.path.join(d, 'sprite.json'), 'w'), indent=1)
        for f in ('HOLD.txt', 'sprite_candidates.png', 'candidates.json'):
            if os.path.exists(os.path.join(d, f)):
                os.remove(os.path.join(d, f))
        report.append((slug, f'{src} {sets[0]} +{len(sets) - 1}'))
    for r in report:
        print(*r)


if __name__ == '__main__':
    main()
