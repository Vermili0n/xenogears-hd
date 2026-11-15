r"""Every frame of a staged set, 10 a sheet (top: the sprite as cut, bottom: the HD as the game stretches it) - for QA by eye.
  python ai\redraw\gaps_1115\all_frames_sheet.py <inst dir> <group> [<per sheet>]  -> <inst>\all_<group>_<k>.png"""
import json
import os
import sys

from gcommon import ROOT
from install_pod import game_preview


def main():
    inst, g = sys.argv[1], sys.argv[2]
    per = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    meta = json.load(open(os.path.join(os.path.dirname(os.path.abspath(inst)), 'pod_' + os.path.basename(inst)[5:], 'meta.json')))
    hdir = next(m['hero_dir'] for m in meta.values() if m['group'] == g)
    set_dir = os.path.join(ROOT, hdir)
    n = len(json.load(open(os.path.join(set_dir, 'layout.json')))['npc']['frames'])
    for k in range(0, n, per):
        out = os.path.join(inst, f'all_{g}_{k // per}.png')
        game_preview(set_dir, os.path.join(inst, g, 'parts'), list(range(k, min(n, k + per))), out)
        print(out, f'frames {k}..{min(n, k + per) - 1}')


if __name__ == '__main__':
    main()
