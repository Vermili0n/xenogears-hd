"""Pick a small set of frames that covers every sprite part of a hero (greedy weighted set cover).

Order: field sets first (most screen time), then everything else. Weight of a part = its pixel area,
so big body parts are covered by the frames where they matter. Writes plan CSV: priority,set,frame,new_parts.
"""
import argparse
import csv
import json
import os

FIELD_FILES = {427, 428, 429, 430, 431, 432, 433, 434, 435, 436, 437, 439, 440, 441, 442}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero-dir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--min-new', type=int, default=1, help='stop when a frame adds fewer new parts')
    args = ap.parse_args()
    lay = json.load(open(os.path.join(args.hero_dir, 'layout.json')))
    sizes = {}
    with open(os.path.join(args.hero_dir, 'index.csv')) as f:
        for r in csv.DictReader(f):
            sizes[r['name'].split('-')[0]] = int(r['w']) * int(r['h'])
    frames = []
    for key, s in lay.items():
        fileno = int(key.split('_')[0])
        for fi, parts in enumerate(s['frames']):
            blocks = {p['block'] for p in parts}
            if blocks:
                frames.append((0 if fileno in FIELD_FILES else 1, key, fi, blocks))
    plan, covered = [], set()
    for prio in (0, 1):
        pool = [f for f in frames if f[0] == prio]
        while pool:
            best = max(pool, key=lambda f: sum(sizes.get(b, 1) for b in f[3] - covered))
            new = best[3] - covered
            if len(new) < args.min_new:
                break
            plan.append((prio, best[1], best[2], len(new)))
            covered |= best[3]
            pool.remove(best)
    allb = set().union(*(f[3] for f in frames)) if frames else set()
    with open(args.out, 'w', newline='') as o:
        w = csv.writer(o)
        w.writerow(['priority', 'set', 'frame', 'new_parts'])
        w.writerows(plan)
    field = sum(1 for p in plan if p[0] == 0)
    print(f'{os.path.basename(args.hero_dir)}: frames total={len(frames)} plan={len(plan)} '
          f'(field {field}, other {len(plan) - field}) covers {len(covered)}/{len(allb)} parts')


if __name__ == '__main__':
    main()
