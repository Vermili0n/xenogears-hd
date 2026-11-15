"""Per animation set: frames assembled from parts of source A vs source B (as the game shows them), side by side.

  python set_compare.py --hero-dir extracted/disc1_full/fei --a ai/fei_prod/parts --b ai/fei_lora/parts \
      --sets 427_0,2340_0 --out ai/compare [--labels Gemini,LoRA] [--per-row 12]
One PNG per set: row pairs (original | A | B) for every frame of the set that appears in the plan.
"""
import argparse
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from batch_redraw import read_plan  # noqa: E402


def assemble(hero_dir, setkey, frames, parts, out):
    subprocess.run([sys.executable, os.path.join(HERE, 'assemble4x.py'), '--hero-dir', hero_dir, '--set', setkey,
                    '--frames', ','.join(map(str, frames)), '--parts', parts, '--out', out],
                   check=True, capture_output=True)
    im = Image.open(out)
    return im, im.width // len(frames)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', default='fei')
    ap.add_argument('--hero-dir', default='')
    ap.add_argument('--a', required=True)
    ap.add_argument('--b', required=True)
    ap.add_argument('--labels', default='Gemini,LoRA')
    ap.add_argument('--sets', default='', help='default: every set of the plan')
    ap.add_argument('--out', required=True)
    ap.add_argument('--per-row', type=int, default=12)
    a = ap.parse_args()
    hd = a.hero_dir or os.path.join(ROOT, 'extracted', 'disc1_full', a.hero)
    plan = read_plan(a.hero, False)
    sets = a.sets.split(',') if a.sets else sorted({s for s, _ in plan}, key=lambda s: int(s.split('_')[0]))
    la, lb = a.labels.split(',')
    os.makedirs(a.out, exist_ok=True)
    tmp = os.path.join(a.out, '_tmp.png')
    for s in sets:
        frames = sorted(fi for ss, fi in plan if ss == s)
        if not frames:
            continue
        ia, w = assemble(hd, s, frames, a.a, tmp + 'a.png')
        ib, _ = assemble(hd, s, frames, a.b, tmp + 'b.png')
        h2 = ia.height // 2  # assemble4x: top = original, bottom = replaced
        n = len(frames)
        rows = -(-n // a.per_row)
        band = 3 * h2 + 40
        sheet = Image.new('RGB', (min(n, a.per_row) * w, rows * band), (40, 40, 40))
        d = ImageDraw.Draw(sheet)
        for i, fi in enumerate(frames):
            x, y = (i % a.per_row) * w, (i // a.per_row) * band
            sheet.paste(ia.crop((i * w, 0, (i + 1) * w, h2)), (x, y + 12))
            sheet.paste(ia.crop((i * w, h2, (i + 1) * w, 2 * h2)), (x, y + 12 + h2 + 2))
            sheet.paste(ib.crop((i * w, h2, (i + 1) * w, 2 * h2)), (x, y + 12 + 2 * h2 + 4))
            d.text((x + 3, y), str(fi), fill=(255, 255, 255))
        for r in range(rows):
            d.text((2, r * band + 12 + h2 + 4), la, fill=(255, 220, 0))
            d.text((2, r * band + 12 + 2 * h2 + 6), lb, fill=(0, 220, 255))
        sheet.save(os.path.join(a.out, f'{a.hero}_{s}.png'))
        print(s, n, 'frames', sheet.size, flush=True)
    for f in (tmp + 'a.png', tmp + 'b.png'):
        if os.path.exists(f):
            os.remove(f)


if __name__ == '__main__':
    main()
