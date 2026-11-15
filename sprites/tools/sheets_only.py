"""Rebuild the full-frame QA sheets (qa_zoom, --h 150) of already composed and sieved groups, update state.json.

  python sheets_only.py g1 g2 ...
"""
import glob
import json
import os
import subprocess
import sys

ROOT = r'<XENO_SPRITES>'
TOOLS = os.path.join(ROOT, 'tools')
QA = os.path.join(ROOT, 'pod', 'report', 'qa')
STATE = os.path.join(QA, 'auto', 'state.json')


def main():
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    state = json.load(open(STATE))
    sel_csv = os.path.join(QA, 'auto', 'sel_rebuild.csv')
    with open(sel_csv, 'w') as sel:
        for g in sys.argv[1:]:
            work = os.path.join(ROOT, 'ai', 'prod_work', g, 'work')
            pick = sorted({(m['set'], m['frame']) for m in meta.values() if m['group'] == g and
                           os.path.exists(os.path.join(work, f"{m['set']}_{m['frame']:03d}_red.png"))})
            for s, f in pick:
                sel.write(f'{g},{s},{f},0,0,1\n')
            state[g].update(mode='all', shown=len(pick))
    for g in sys.argv[1:]:
        for old in glob.glob(os.path.join(QA, f'z_{g}_auto_*.png')):
            os.remove(old)
        z = subprocess.run([sys.executable, 'qa_zoom.py', g, 'csv:' + sel_csv, '--h', '150', '--tag', '_auto'], cwd=TOOLS,
                           capture_output=True, text=True)
        state[g]['sheets'] = [ln.split()[0] for ln in z.stdout.splitlines() if '.png' in ln]
        print(g, state[g]['shown'], 'frames ->', len(state[g]['sheets']), 'sheets', z.stderr[-200:] if z.returncode else '')
    json.dump(state, open(STATE, 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
