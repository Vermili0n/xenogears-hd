"""Hero frames whose verdict the pictures found by content changed, before (left) and after (right), as the bridge draws
them (no tint), from two sprite_coverage runs: python tools/alias_frames.py <before folder> <after folder> <out folder> [k]"""
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sprite_coverage import draw_frame  # noqa: E402


def main():
    before, after, out = sys.argv[1:4]
    k = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    os.makedirs(out, exist_ok=True)
    for c in range(11):
        old = {json.loads(line)['frame']: json.loads(line) for line in open(os.path.join(before, f'draws_{c}.jsonl')) if json.loads(line)['variant'] == 'own'}
        new = {json.loads(line)['frame']: json.loads(line) for line in open(os.path.join(after, f'draws_{c}.jsonl')) if json.loads(line)['variant'] == 'own'}
        changed = [f for f in old if [p['kind'] for p in old[f]['pieces']] != [p['kind'] for p in new[f]['pieces']]]
        if not changed:
            continue
        pairs = []
        for f in changed:
            a, b = draw_frame(old[f], k, tint=False), draw_frame(new[f], k, tint=False)
            pair = Image.new('RGBA', (a.width + b.width + 12, max(a.height, b.height)), (70, 70, 76, 255))
            pair.alpha_composite(a, (0, 0))
            pair.alpha_composite(b, (a.width + 12, 0))
            pairs.append(pair)
        sheet = Image.new('RGBA', (sum(p.width for p in pairs) + 16 * len(pairs), max(p.height for p in pairs)), (30, 30, 34, 255))
        x = 0
        for p in pairs:
            sheet.alpha_composite(p, (x, 0))
            x += p.width + 16
        sheet.save(os.path.join(out, f'frames_{c}.png'))
        print(c, 'frames changed', changed)


if __name__ == '__main__':
    main()
