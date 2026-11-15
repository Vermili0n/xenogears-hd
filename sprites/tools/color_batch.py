"""Colour cards for every composed hero / story group, then one summary table (worst colour jitter first).

  python color_batch.py
Runs color_card.py per group (skips groups whose card exists), writes pod/report/qa/color/_summary.txt.
Per group: share of frames with an off colour, the largest spread (ab) among colours covering >= 5 % of the pixels.
"""
import glob
import json
import os
import subprocess
import sys

ROOT = r'<XENO_SPRITES>'
OUT = os.path.join(ROOT, 'pod', 'report', 'qa', 'color')
CARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'color_card.py')


def main():
    work = os.path.join(ROOT, 'ai', 'prod_work')
    groups = sorted(g for g in os.listdir(work) if g.startswith(('h_', 'c_')) and
                    glob.glob(os.path.join(work, g, 'work', '*_red.png')))
    for g in groups:
        if not os.path.exists(os.path.join(OUT, f'{g}_card.json')):
            r = subprocess.run([sys.executable, CARD, g, '--top', '0'], capture_output=True, text=True)
            if r.returncode:
                print(g, 'failed', r.stderr[-200:], flush=True)
    rows = []
    for g in groups:
        p = os.path.join(OUT, f'{g}_card.json')
        if not os.path.exists(p):
            continue
        card = json.load(open(p))
        total = sum(c['px'] for c in card) or 1
        big = [c for c in card if c['px'] >= 0.05 * total]
        if not big:
            continue
        worst = max(big, key=lambda c: c['mad_ab'])
        frames = {f for c in card for f in (x[0] for x in c['frames'])}
        off = set()
        for c in card:
            thr = max(8.0, 3.5 * c['mad_ab'])
            off |= {x[0] for x in c['frames'] if x[2] > thr}
        rows.append((worst['mad_ab'], g, len(frames), len(off), worst['sprite']))
    rows.sort(reverse=True)
    with open(os.path.join(OUT, '_summary.txt'), 'w') as f:
        f.write('spread_ab  group  frames  off_frames  worst_colour(sprite rgb)\n')
        for r in rows:
            f.write(f'{r[0]:5.1f}  {r[1]}  {r[2]}  {r[3]}  {r[4]}\n')
    print(f'{len(rows)} groups; top 15 by colour spread:')
    for r in rows[:15]:
        print(f'  {r[0]:5.1f}  {r[1]:32} frames {r[2]:4}  off {r[3]:3}  colour {tuple(r[4])}')


if __name__ == '__main__':
    main()
