"""The coverage tool against the bridge's own tallies: story states with the leader alone on screen, walked and run
(20 frames still, 40 running up), each frame's sprite tallies (session_smoke XENO_TRACE) against sprite_coverage's
verdict for the leader's frame (frames_0.csv: pieces, whole, partly, VRAM).

  python tools/sprite_crosscheck.py [out/sweep_sprites]
"""
import csv
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.environ.get('XENO_PACK', os.path.join(ROOT, 'pack'))  # the HD pack folder
STATES = ['099_story15_map21_p1_new', '101_story15_map15_p1_new', '102_story15_map18_p1_new', '103_story15_map20_p1_new', '117_story16_map18_p1_new']


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'out', 'sweep_sprites')
    tool = {int(r['frame']): r for r in csv.DictReader(open(os.path.join(folder, 'frames_0.csv'))) if r['palette_variant'] == 'own'}
    smoke = os.path.join(ROOT, 'bridge', 'build', 'Release', 'session_smoke.exe')
    for state in STATES:
        env = dict(os.environ, XENO_PACK=PACK, XENO_TRACE='1', XENO_WORLD_EVERY='1', XENO_SCRIPT='20:0,40:2010',
                   XENO_LOAD=os.path.join(ROOT, 'out', 'states', 'story', state + '.state'))
        out = subprocess.run([smoke, os.path.join(ROOT, 'weltall', 'Games'), '0', '60'], env=env, capture_output=True, text=True, cwd=ROOT).stdout
        agree = differ = 0
        shown = set()
        for frame, n, whole, partly, vram, leader in re.findall(r'trace (\d+): sprites (\d+) whole (\d+) partly (\d+) vram (\d+), leader frame (-?\d+)', out):
            leader = int(leader)
            if leader < 1 or int(n) == 0:
                continue
            t = tool[leader]
            shown.add(leader)
            if (int(n), int(whole), int(partly), int(vram)) == (int(t['pieces']), int(t['whole']), int(t['partial']), int(t['vram'])):
                agree += 1
            else:
                differ += 1
                print(f'  differ {state} frame {frame}: bridge {n}/{whole}/{partly}/{vram}, tool frame {leader} {t["pieces"]}/{t["whole"]}/{t["partial"]}/{t["vram"]}')
        print(f'{state}: frames compared {agree + differ}, agree {agree}, differ {differ}; leader frames {sorted(shown)}')


if __name__ == '__main__':
    main()
