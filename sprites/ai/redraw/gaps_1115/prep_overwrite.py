r"""Folders for overwrite_install.py from install_pod.py's stages (16.11.2026): which staged names of one group would
overwrite the pack and which are new.

  python ai\redraw\gaps_1115\prep_overwrite.py multitex <group> [...]   -> ow_<group>\overwrite.txt, new.txt (stage: inst_multitex\stage)
  python ai\redraw\gaps_1115\prep_overwrite.py roni                     -> ow_roni\ (the sheet 86ef69b7-98d6171a from inst_rest\stage)
Then: overwrite_install.py ow_<group> --check|--install --stage=inst_<job>\stage
"""
import json
import os
import sys

from gcommon import HERE, PACK, ROOT
from install_pod import RONI_SHEET, disc, project


def write(folder, names, stage):
    os.makedirs(folder, exist_ok=True)
    missing = [n for n in names if not os.path.exists(os.path.join(stage, n + '.bc7'))]
    if missing:
        sys.exit(f'{folder}: not staged {missing[:5]}')
    over = sorted(n for n in names if os.path.exists(os.path.join(PACK, n + '.bc7')))
    new = sorted(n for n in names if not os.path.exists(os.path.join(PACK, n + '.bc7')))
    open(os.path.join(folder, 'overwrite.txt'), 'w').write(''.join(n + '\n' for n in over))
    open(os.path.join(folder, 'new.txt'), 'w').write(''.join(n + '\n' for n in new))
    open(os.path.join(folder, 'stage_dir.txt'), 'w').write(stage + '\n')
    print(f'{folder}: overwrite {len(over)}, new {len(new)}; stage {stage}')


def main():
    job = sys.argv[1]
    if job == 'roni':
        write(os.path.join(HERE, 'ow_roni'), [RONI_SHEET], os.path.join(HERE, 'inst_rest', 'stage'))
        return
    inst = os.path.join(HERE, 'inst_multitex')
    meta = json.load(open(os.path.join(HERE, 'pod_multitex', 'meta.json')))
    mm, toc = disc()
    for g in sys.argv[2:]:
        hdir = next(m['hero_dir'] for m in meta.values() if m['group'] == g)
        files, notes = project(os.path.basename(hdir), os.path.join(ROOT, hdir), os.path.join(inst, g, 'parts'), inst, mm, toc)
        for n in notes:
            print('  note:', n)
        write(os.path.join(HERE, 'ow_' + g), list(files), os.path.join(inst, 'stage'))


if __name__ == '__main__':
    main()
