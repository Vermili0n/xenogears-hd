"""Sheet for infer_pod.py results on a test set: original | board | NB teacher (held-out) | one column per result folder.

  python pod/test_sheet.py --set ai/pod_v2/test2 --res pod/report/test2 --out pod/report/test2.png [--only m_,mass_] [--faces f.png]
--res holds one sub-folder per checkpoint / setting (infer_pod.py output); columns follow sorted folder names.
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from eval_sheet_v2 import JOBS, face_sheet, teacher  # noqa: E402
from klein_batch import bbox  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', required=True)
    ap.add_argument('--res', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--only', default='', help='comma list of name prefixes')
    ap.add_argument('--h', type=int, default=240)
    ap.add_argument('--faces', default='')
    ap.add_argument('--jobs', default='jobs.json', help='jobs file inside --set')
    a = ap.parse_args()
    jobs = json.load(open(os.path.join(a.set, a.jobs)))
    if a.only:
        jobs = [j for j in jobs if j['name'].startswith(tuple(a.only.split(',')))]
    cols = sorted(d for d in os.listdir(a.res) if os.path.isdir(os.path.join(a.res, d)))
    cj, heroes = json.load(open(JOBS)), {}
    rows = []
    for j in jobs:
        n = j['name']
        ctrl = Image.open(os.path.join(a.set, j['control'])).convert('RGB')
        x0, y0, x1, y1 = bbox(ctrl)
        box = (max(0, x0 - 12), max(0, y0 - 12), min(512, x1 + 12), min(512, y1 + 12))
        res = [os.path.join(a.res, c, n + '.png') for c in cols]
        tch = Image.open(os.path.join(a.set, j['target'])).convert('RGB') if j.get('target') else teacher(n, cj, heroes)
        ims = [ctrl, tch] + [Image.open(p).convert('RGB') if os.path.exists(p) else None for p in res]
        rows.append((n, box, ims, Image.open(os.path.join(a.set, j['ref'])).convert('RGB')))
    H = a.h
    labels = ['original', 'board', 'NB (teacher)'] + cols
    W = max(160, max(int((b[2] - b[0]) * H / (b[3] - b[1])) for _, b, _, _ in rows))
    sheet = Image.new('RGB', (len(labels) * W, len(rows) * (H + 16) + 18), (55, 55, 55))
    d = ImageDraw.Draw(sheet)
    for k, lab in enumerate(labels):
        d.text((k * W + 4, 3), lab, fill=(255, 255, 0))
    for r, (n, box, ims, board) in enumerate(rows):
        y = 18 + r * (H + 16)
        d.text((4, y + 1), n, fill=(255, 255, 255))
        w = int((box[2] - box[0]) * H / (box[3] - box[1]))
        bw = min(W, H)
        sheet.paste(board.resize((bw, bw), Image.LANCZOS), (W, y + 14))
        for k, im in enumerate(ims):
            if im is not None:
                col = k if k == 0 else k + 1
                sheet.paste(im.crop(box).resize((w, H), Image.LANCZOS), (col * W, y + 14))
    sheet.save(a.out)
    print(sheet.size, 'columns', cols)
    if a.faces:
        face_sheet(rows, cols, a.faces)


if __name__ == '__main__':
    main()
