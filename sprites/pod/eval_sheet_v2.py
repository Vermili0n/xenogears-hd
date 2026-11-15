"""LoRA v2 sample sheet: original | board | NB (held-out target, if any) | LoRA at each checkpoint.

  python pod/eval_sheet_v2.py --samples pod/report/v2_samples --out pod/report/v2_step.png
Sample index follows sorted(ai/pod_v2/eval/*_c.png) (same order as the pod config).
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
from ai_redraw import Hero  # noqa: E402
from make_pairs import pair  # noqa: E402

EVAL = os.path.join(ROOT, 'ai', 'pod_v2', 'eval')
JOBS = os.path.join(ROOT, 'ai', 'campaign', 'jobs.json')


def teacher(n, jobs, heroes):
    """Held-out NB frame placed like the control (None for massovka / no accepted frame)."""
    if '__' not in n:
        return None
    job, rest = n.split('__', 1)
    setkey, fi = rest.rsplit('_', 1)
    w = os.path.join(ROOT, 'ai', f'{job}_keys', 'work', f'{setkey}_{fi}_red.png')
    if job not in jobs or not os.path.exists(w):
        return None
    if job not in heroes:
        heroes[job] = Hero(os.path.join(ROOT, jobs[job]['hero_dir']))
    return pair(heroes[job], setkey, int(fi), w, 512, 500)[1].convert('RGB')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--samples', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--h', type=int, default=300)
    ap.add_argument('--steps', default='', help='comma list of steps to show (default all)')
    ap.add_argument('--faces', default='', help='also write a head close-up sheet here (characters only)')
    a = ap.parse_args()
    names = sorted(f[:-6] for f in os.listdir(EVAL) if f.endswith('_c.png'))
    got = {}
    for f in os.listdir(a.samples):
        m = re.match(r'\d+__(\d+)_(\d+)\.jpg$', f)
        if m:
            got[(int(m.group(1)), int(m.group(2)))] = os.path.join(a.samples, f)
    steps = sorted({s for s, _ in got})
    if a.steps:
        steps = [s for s in steps if str(s) in a.steps.split(',')]
    H = a.h
    rows = []
    jobs, heroes = json.load(open(JOBS)), {}
    for i, n in enumerate(names):
        ctrl = Image.open(os.path.join(EVAL, n + '_c.png')).convert('RGB')
        x0, y0, x1, y1 = bbox(ctrl)
        box = (max(0, x0 - 12), max(0, y0 - 12), min(512, x1 + 12), min(512, y1 + 12))
        nb = teacher(n, jobs, heroes)
        ims = [ctrl, nb] + [Image.open(got[(s, i)]).convert('RGB').resize((512, 512)) if (s, i) in got else None for s in steps]
        board = Image.open(os.path.join(EVAL, n + '_r.png')).convert('RGB')
        rows.append((n, box, ims, board))
    labels = ['original', 'board', 'NB (teacher)'] + [f'LoRA v2 {s}' for s in steps]
    W = max(int((b[2] - b[0]) * H / (b[3] - b[1])) for _, b, _, _ in rows)
    W = max(W, 160)
    sheet = Image.new('RGB', (len(labels) * W, len(rows) * (H + 16) + 18), (55, 55, 55))
    d = ImageDraw.Draw(sheet)
    for k, lab in enumerate(labels):
        d.text((k * W + 4, 3), lab, fill=(255, 255, 0))
    for r, (n, box, ims, board) in enumerate(rows):
        y = 18 + r * (H + 16)
        d.text((4, y + 1), n, fill=(255, 255, 255))
        w = int((box[2] - box[0]) * H / (box[3] - box[1]))
        bw = min(W, int(board.width * H / board.height))
        sheet.paste(board.resize((bw, int(board.height * bw / board.width)), Image.LANCZOS), (W, y + 14))
        for k, im in enumerate(ims):
            if im is not None:
                col = k if k == 0 else k + 1
                sheet.paste(im.crop(box).resize((w, H), Image.LANCZOS), (col * W, y + 14))
    sheet.save(a.out)
    print(sheet.size, 'steps', steps)
    if a.faces:
        face_sheet(rows, steps, a.faces)


def head_box(ctrl):
    """Square around the head: the topmost part of the sprite, side = 38 % of the sprite height."""
    x0, y0, x1, y1 = bbox(ctrl)
    side = max(48, int(0.38 * (y1 - y0)))
    px = ctrl.load()
    xs = [x for y in range(y0, y0 + max(4, (y1 - y0) // 10)) for x in range(x0, x1) if px[x, y] != (255, 0, 255)]
    cx = sum(xs) // len(xs) if xs else (x0 + x1) // 2
    bx = min(max(0, cx - side // 2), 512 - side)
    return (bx, max(0, y0 - 6), bx + side, max(0, y0 - 6) + side)


def face_sheet(rows, steps, out, S=260):
    labels = ['original', 'NB (teacher)'] + [f'LoRA v2 {s}' for s in steps]
    rows = [r for r in rows if not r[0].startswith('g_')]
    sheet = Image.new('RGB', (len(labels) * S, len(rows) * (S + 16) + 18), (55, 55, 55))
    d = ImageDraw.Draw(sheet)
    for k, lab in enumerate(labels):
        d.text((k * S + 4, 3), lab, fill=(255, 255, 0))
    for r, (n, _, ims, _) in enumerate(rows):
        y = 18 + r * (S + 16)
        d.text((4, y + 1), n, fill=(255, 255, 255))
        hb = head_box(ims[0])
        for k, im in enumerate(ims):
            if im is not None:
                sheet.paste(im.crop(hb).resize((S, S), Image.LANCZOS), (k * S, y + 14))
    sheet.save(out)
    print('faces', sheet.size)


if __name__ == '__main__':
    main()
