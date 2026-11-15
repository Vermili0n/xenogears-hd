"""Sheet of LoRA v3 training-time samples: original | board | teacher | sample at each checkpoint.

  python pod/sample_sheet_v3.py --samples pod/report/v3_samples --out pod/report/v3_steps.png
Sample index = order of ai/pod_v3/samples.json (same as the pod YAML); inputs/teacher from ai/pod_v3/test3.
"""
import argparse
import json
import os
import re
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from klein_batch import bbox  # noqa: E402

T = os.path.join(ROOT, 'ai', 'pod_v3', 'test3')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--samples', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--h', type=int, default=220)
    ap.add_argument('--spec', default=os.path.join(ROOT, 'ai', 'pod_v3', 'samples.json'))
    ap.add_argument('--tag', default='v3')
    a = ap.parse_args()
    samples = json.load(open(a.spec))
    jobs = {j['name']: j for j in json.load(open(os.path.join(T, 'jobs.json')))}
    got = {}
    for f in os.listdir(a.samples):
        m = re.match(r'\d+__(\d+)_(\d+)\.jpg$', f)
        if m:
            got[(int(m.group(1)), int(m.group(2)))] = os.path.join(a.samples, f)
    steps = sorted({s for s, _ in got})
    H = a.h
    labels = ['original', 'board', 'teacher'] + [f'{a.tag} {s}' for s in steps]
    rows = []
    for i, s in enumerate(samples):
        j = jobs[s['name']]
        ctrl = Image.open(os.path.join(T, j['control'])).convert('RGB')
        x0, y0, x1, y1 = bbox(ctrl)
        box = (max(0, x0 - 12), max(0, y0 - 12), min(512, x1 + 12), min(512, y1 + 12))
        ims = [ctrl, Image.open(os.path.join(T, j['target'])).convert('RGB')]
        ims += [Image.open(got[(st, i)]).convert('RGB').resize((512, 512)) if (st, i) in got else None for st in steps]
        rows.append((s['name'], box, ims, Image.open(os.path.join(T, j['ref'])).convert('RGB')))
    W = max(H, max(int((b[2] - b[0]) * H / (b[3] - b[1])) for _, b, _, _ in rows))
    sheet = Image.new('RGB', (len(labels) * W, len(rows) * (H + 16) + 18), (55, 55, 55))
    d = ImageDraw.Draw(sheet)
    for k, lab in enumerate(labels):
        d.text((k * W + 4, 3), lab, fill=(255, 255, 0))
    for r, (n, box, ims, board) in enumerate(rows):
        y = 18 + r * (H + 16)
        d.text((4, y + 1), n, fill=(255, 255, 255))
        w = int((box[2] - box[0]) * H / (box[3] - box[1]))
        sheet.paste(board.resize((H, H), Image.LANCZOS), (W, y + 14))
        for k, im in enumerate(ims):
            if im is not None:
                sheet.paste(im.crop(box).resize((w, H), Image.LANCZOS), ((k if k == 0 else k + 1) * W, y + 14))
    sheet.save(a.out)
    print(sheet.size, 'steps', steps)


if __name__ == '__main__':
    main()
