"""Weltall's sprite pieces against the user's layouts, frame by frame: where they differ, and how.

The user's layout (xeno_sprites/extracted/disc1_full/<hero>/layout.json, set <file>_0) places each piece at
x = dx + mx, y = dy + my, sized as its picture, flipped by flipx / flipy. sprite_parts_dump.exe gives Weltall's pieces
for the same file (frame N of Weltall = frame N - 1 of the layout, pieces in the reverse order), placed as the original
does and with Weltall's fix. Pieces are matched by size and flips; the report counts the x / y offsets per kind.

Usage: python compare_layout.py <parts.jsonl> <layout.json> <set key>
"""
import json
import sys
from collections import Counter

MIRRORED = 0x10


def main(parts_path, layout_path, set_key):
    layout = json.load(open(layout_path))[set_key]
    weltall = [json.loads(line) for line in open(parts_path)]
    parts_dir = layout_path.replace('layout.json', 'parts')
    sizes = {}
    report = {mode: Counter() for mode in ('original', 'aligned')}
    unmatched = Counter()
    from PIL import Image
    for row in weltall:
        fi = row['frame'] - 1
        if fi >= len(layout['frames']):
            break
        ours = layout['frames'][fi]
        for mode in ('original', 'aligned'):
            theirs = list(reversed(row[mode]))
            if len(theirs) != len(ours):
                unmatched[(mode, 'count')] += 1
                continue
            for p, w in zip(ours, theirs):
                key = p['block']
                if key not in sizes:
                    pal = layout['palettes'][0]
                    try:
                        sizes[key] = Image.open(f'{parts_dir}/{key}-{pal}.png').size
                    except OSError:
                        sizes[key] = None
                mirrored = bool(w['flags'] & MIRRORED)
                kind = ('mirrored' if mirrored else 'straight') + (' flipx' if p['flipx'] else '')
                dx = w['x'] - (p['dx'] + p['mx'])
                dy = w['y'] - (p['dy'] + p['my'])
                size = sizes[key]
                dw = w['w'] - size[0] if size else None
                report[mode][(kind, dx, dy, dw)] += 1
    for mode, counts in report.items():
        print(f'Weltall {mode} placement - user layout (piece kind, dx, dy, width difference): count')
        for k, n in counts.most_common(14):
            print('  ', k, n)
    if unmatched:
        print('frames with another piece count:', dict(unmatched))


if __name__ == '__main__':
    main(*sys.argv[1:4])
