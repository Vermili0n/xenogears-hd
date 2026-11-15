"""Head comparison sheet for test3: sprite head | teacher 16x head | head-pass renders | heads cut from full-frame renders.

  python pod/head_sheet.py --res pod/report/test3/res_test3 --runs v3_cfg4_s42/1000,v3_cfg4_s42/v3 --cut v2_cfg4_s42/v2,v3_cfg4_s42/v3 --out pod/report/test3_heads.png
--runs: run/tag folders whose __head renders are shown; --cut: run/tag folders whose full-frame renders are cropped to the head.
"""
import argparse
import json
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(ROOT, 'ai', 'pod_v3', 'test3')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--res', required=True)
    ap.add_argument('--runs', default='')
    ap.add_argument('--cut', default='')
    ap.add_argument('--out', required=True)
    ap.add_argument('--s', type=int, default=200)
    ap.add_argument('--only', default='', help='comma list of name prefixes')
    a = ap.parse_args()
    hm = json.load(open(os.path.join(T, 'headmap.json')))
    runs = [r for r in a.runs.split(',') if r]
    cuts = [r for r in a.cut.split(',') if r]
    names = sorted(n for n in hm if not a.only or n.startswith(tuple(a.only.split(','))))
    S = a.s
    labels = ['sprite', 'teacher'] + [f'pass {r}' for r in runs] + [f'cut {r}' for r in cuts]
    sheet = Image.new('RGB', (len(labels) * S, len(names) * (S + 14) + 16), (50, 50, 50))
    d = ImageDraw.Draw(sheet)
    for k, lab in enumerate(labels):
        d.text((k * S + 3, 2), lab[:32], fill=(255, 255, 0))
    for i, n in enumerate(names):
        y = 16 + i * (S + 14)
        d.text((3, y), n[:40] + ('' if hm[n].get('face', True) else '  [back?]'), fill=(255, 255, 255))
        ims = [Image.open(os.path.join(T, 'control', n + '.png')), Image.open(os.path.join(T, 'target', n + '.png'))]
        for r in runs:
            p = os.path.join(a.res, r, n + '.png')
            ims.append(Image.open(p) if os.path.exists(p) else None)
        for r in cuts:
            p = os.path.join(a.res, r, hm[n]['full'] + '.png')
            ims.append(Image.open(p).crop(tuple(hm[n]['box'])) if os.path.exists(p) else None)
        for k, im in enumerate(ims):
            if im is not None:
                sheet.paste(im.convert('RGB').resize((S, S), Image.LANCZOS), (k * S, y + 12))
    sheet.save(a.out)
    print(sheet.size)


if __name__ == '__main__':
    main()
