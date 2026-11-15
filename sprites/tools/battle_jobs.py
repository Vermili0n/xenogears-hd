"""Pod jobs for battle sets (extracted/battle/<id>): every frame, the identity's board + head pass; 'noref' = no board, no head pass.

  python battle_jobs.py --out ai/redraw/<name> [--frames frames.json] <set id>:<slug or noref> ...
--frames {group: [frame, ...]}: only these frames of a group (a second render of the bad frames).
Writes jobs.json, meta.json, control/, boards/ (as nisan_joe_build.py); groups are b_<set id>.
own_<id>:<slug> = a field set with its own pixels (own_set.py extract): group c_<slug>_<id6> (prod_post takes the hero's
colour offset), o_<id> for noref or an npc_<id10> board. npc_<id10> boards go without the head pass.
<set id>:@<board png> = a board file given directly (self boards of battle_boards.py), no head pass.
"""
import argparse
import json
import os
import shutil
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from make_pairs_v3 import GREY  # noqa: E402
from render_build import CAP_NOREF  # noqa: E402
from render_prod import build_group, slug_board  # noqa: E402

BATTLE = os.path.join(ROOT, 'extracted', 'battle')
OWN = os.path.join(ROOT, 'extracted', 'disc1_full')


def set_dir(group):
    """Hero folder of a group made here: b_<id> battle set, c_<slug>_<id6> / o_<id> own-pixel field set."""
    if group.startswith('b_'):
        return os.path.join(BATTLE, group[2:])
    tag = group[-6:] if group.startswith('c_') else group[2:]
    return next(os.path.join(OWN, d) for d in os.listdir(OWN) if d.startswith('own_' + tag))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--frames', default='')
    ap.add_argument('sets', nargs='+')
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    os.makedirs(os.path.join(out, 'control'), exist_ok=True)
    os.makedirs(os.path.join(out, 'boards'), exist_ok=True)
    Image.new('RGB', (512, 512), GREY).save(os.path.join(out, 'boards', '_blank.png'))
    only = json.load(open(a.frames)) if a.frames else {}
    jobs, meta = [], {}
    for item in a.sets:
        sid, slug = item.split(':')
        own = slug.startswith('@')  # @<board png>: a board made of the set's own frames (battle_boards.py)
        npc = slug.startswith('npc_') or own  # an NPC board: no head pass, as the field NPCs
        if sid.startswith('own_'):
            hd = os.path.join(OWN, sid)
            g = f'o_{sid[4:]}' if slug == 'noref' or npc else f'c_{slug}_{sid[4:10]}'
        else:
            hd, g = os.path.join(BATTLE, sid), f'b_{sid}'
        lay = json.load(open(os.path.join(hd, 'layout.json')))
        sk = list(lay)[0]
        n = len(lay[sk]['frames'])
        board = None if slug == 'noref' else os.path.abspath(slug[1:]) if own else slug_board(slug)
        if slug != 'noref' and board is None:
            raise SystemExit(f'no board for {slug}')
        if board:
            shutil.copyfile(board, os.path.join(out, 'boards', os.path.basename(board)))
        j, m = build_group((g, hd, [(sk, i) for i in only.get(g, range(n))], board, 'npc' if board is None or npc else 'hero', out))
        if board is None:
            for x in j:
                x['prompt'] = CAP_NOREF
        jobs += j
        meta.update(m)
        print(f'{g} {slug}: frames {len(m)}, jobs {len(j)}')
    json.dump([{k: v for k, v in j.items() if k != 'lora'} for j in jobs], open(os.path.join(out, 'jobs.json'), 'w'), indent=0)
    json.dump(meta, open(os.path.join(out, 'meta.json'), 'w'), indent=0)
    print('total jobs', len(jobs), f'~{len(jobs) * 10.3 / 3600:.1f} h on one RTX PRO 6000')


if __name__ == '__main__':
    main()
