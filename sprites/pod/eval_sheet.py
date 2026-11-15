"""Sheet of pod samples on held-out frames: control | Gemini (if any) | LoRA sample at each checkpoint.

  python pod/eval_sheet.py --samples pod/samples --out <png>
Sample files are ai-toolkit's <ts>__<step>_<index>.jpg; index follows sorted(pod/eval/*.png).
"""
import argparse
import os
import re
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from klein_batch import bbox  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--samples', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--h', type=int, default=260)
    a = ap.parse_args()
    names = sorted(f[:-4] for f in os.listdir(os.path.join(ROOT, 'pod', 'eval')))
    got = {}
    for f in os.listdir(a.samples):
        m = re.match(r'\d+__(\d+)_(\d+)\.jpg$', f)
        if m:
            got[(int(m.group(1)), int(m.group(2)))] = os.path.join(a.samples, f)
    steps = sorted({s for s, _ in got})
    rows = []
    for i, n in enumerate(names):
        ctrl = Image.open(os.path.join(ROOT, 'pod', 'eval', n + '.png')).convert('RGB')
        x0, y0, x1, y1 = bbox(ctrl)
        box = (max(0, x0 - 10), max(0, y0 - 10), min(512, x1 + 10), min(512, y1 + 10))
        gp = os.path.join(ROOT, 'ai', 'pairs', 'target', n + '.png')
        g = None
        if os.path.exists(gp):
            t = Image.open(gp).convert('RGBA')
            g = Image.alpha_composite(Image.new('RGBA', t.size, (255, 0, 255, 255)), t).convert('RGB')
        ims = [ctrl, g] + [Image.open(got[(s, i)]).convert('RGB').resize((512, 512)) if (s, i) in got else None for s in steps]
        rows.append((n, box, ims))
    labels = ['original', 'Gemini'] + [f'LoRA {s}' for s in steps]
    H = a.h
    W = max(int((b[2] - b[0]) * H / (b[3] - b[1])) for _, b, _ in rows)
    sheet = Image.new('RGB', (len(labels) * W, len(rows) * (H + 16) + 18), (55, 55, 55))
    d = ImageDraw.Draw(sheet)
    for k, lab in enumerate(labels):
        d.text((k * W + 4, 3), lab, fill=(255, 255, 0))
    for r, (n, box, ims) in enumerate(rows):
        y = 18 + r * (H + 16)
        d.text((4, y + 1), n, fill=(255, 255, 255))
        w = int((box[2] - box[0]) * H / (box[3] - box[1]))
        for k, im in enumerate(ims):
            if im is not None:
                sheet.paste(im.crop(box).resize((w, H), Image.LANCZOS), (k * W, y + 14))
    sheet.save(a.out)
    print(sheet.size, 'steps', steps)


if __name__ == '__main__':
    main()
