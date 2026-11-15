"""Laptop pass for massovka NPCs: defringe keyframes, then redo the ebsynth fills (similarity-picked keys).

  python npc_laptop_pass.py --plan ai/npc_lahan/plan.json
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', required=True)
    a = ap.parse_args()
    plan = json.load(open(os.path.join(ROOT, a.plan)))
    for nid in plan:
        work = os.path.join(ROOT, 'ai', f'npc_{nid}_prod', 'work')
        if not os.path.isdir(work):
            continue
        r = subprocess.run([sys.executable, os.path.join(HERE, 'defringe.py'), '--hero-dir',
                            os.path.join(ROOT, 'extracted', 'npc', nid), '--work', work], capture_output=True, text=True)
        print((r.stdout or r.stderr).strip().splitlines()[-1], flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, 'ebs_npc.py'), '--plan', a.plan], capture_output=True, text=True)
    print(r.stdout[-3000:], r.stderr[-1500:], flush=True)


if __name__ == '__main__':
    main()
