"""Per-hero totals over several extraction folders (frames, unique blocks, replacement files)."""
import csv
import json
import os
import sys


def main():
    root = sys.argv[1]
    discs = sys.argv[2:]
    tot = {}
    for disc in discs:
        for hero in os.listdir(os.path.join(root, disc)):
            p = os.path.join(root, disc, hero, 'index.csv')
            if not os.path.exists(p):
                continue
            with open(p) as f:
                names = {r['name'] for r in csv.DictReader(f)}
            t = tot.setdefault(hero, {'names': set(), 'blocks': set(), 'frames': 0})
            t['names'] |= names
            t['blocks'] |= {n.split('-')[0] for n in names}
            with open(os.path.join(root, disc, hero, 'layout.json')) as f:
                lay = json.load(f)
            t['frames'] += sum(len(v['frames']) for v in lay.values())
    allb, alln, fr = set(), set(), 0
    for h, t in sorted(tot.items()):
        print(f"{h:9s} frames={t['frames']:5d} unique_blocks={len(t['blocks']):5d} part_files={len(t['names']):6d}")
        allb |= t['blocks']
        alln |= t['names']
        fr += t['frames']
    print(f'TOTAL     frames={fr} unique_blocks={len(allb)} part_files={len(alln)}')


if __name__ == '__main__':
    main()
