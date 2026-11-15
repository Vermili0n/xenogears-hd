"""Comparison sheet of the fix-list hint test: per case a row  control | plain | variant 1 | variant 2  (raw renders
cropped to the figure), frames and head close-ups on separate sheets.

  python fixtest_sheet.py <folder with the test renders (…/v4)> [--h 300] [--jobs ai/prod/jobs_fixtest2.json] [--tag 2]
Writes pod/report/qa/fixtest<tag>_<kind>_<frames|heads>.png. Kinds come from fixlist.json, or 'group' for whole-group
re-render jobs that are not in the fix list.
"""
import argparse
import json
import os
from collections import defaultdict

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROD = os.path.join(ROOT, 'ai', 'prod')


def figure_box(im):
    px = im.convert('RGB').load()
    w, h = im.size
    xs, ys = [], []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            if not (r > 200 and g < 70 and b > 200):
                xs.append(x)
                ys.append(y)
    if not xs:
        return 0, 0, w, h
    return max(0, min(xs) - 4), max(0, min(ys) - 4), min(w, max(xs) + 6), min(h, max(ys) + 6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('res')
    ap.add_argument('--h', type=int, default=300)
    ap.add_argument('--jobs', default=os.path.join(PROD, 'jobs_fixtest.json'))
    ap.add_argument('--tag', default='')
    a = ap.parse_args()
    fix = json.load(open(os.path.join(PROD, 'fixlist.json')))
    jobs = json.load(open(a.jobs))
    rows = defaultdict(dict)                                         # base job -> {variant: name}
    ctrl = {}
    for j in jobs:
        base, var = j['name'].rsplit('__', 1)
        rows[base][var] = j['name']
        ctrl[base] = j['control']
    sheets = defaultdict(list)
    for base, vs in sorted(rows.items()):
        frame = base[:-6] if base.endswith('__head') else base
        kind = fix.get(frame, 'group')
        c = Image.open(os.path.join(PROD, ctrl[base])).convert('RGB')
        box = figure_box(c)
        cells = [('sprite', c.crop(box).resize((round((box[2] - box[0]) * a.h / (box[3] - box[1])), a.h), Image.NEAREST))]
        for var in ['plain'] + sorted(v for v in vs if v != 'plain'):
            p = os.path.join(a.res, vs[var] + '.png')
            if not os.path.exists(p):
                continue
            r = Image.open(p).convert('RGB').crop(box)
            cells.append((var, r.resize((round(r.width * a.h / r.height), a.h), Image.LANCZOS)))
        sheets[(kind, 'heads' if base.endswith('__head') else 'frames')].append((frame.split('__')[0][2:14] + ':' +
                                                                                 frame.rsplit('_', 1)[1], cells))
    for (kind, part), rws in sheets.items():
        W = max(sum(c[1].width + 6 for c in cells) for _, cells in rws)
        sheet = Image.new('RGB', (W + 90, (a.h + 16) * len(rws)), (45, 45, 45))
        d = ImageDraw.Draw(sheet)
        for i, (lab, cells) in enumerate(rws):
            y = i * (a.h + 16)
            d.text((2, y + 2), lab, fill=(255, 255, 0))
            x = 90
            for name, im in cells:
                d.text((x + 2, y + 2), name, fill=(120, 220, 255))
                sheet.paste(im, (x, y + 14))
                x += im.width + 6
        p = os.path.join(ROOT, 'pod', 'report', 'qa', f'fixtest{a.tag}_{kind}_{part}.png')
        sheet.save(p)
        print(p, len(rws), 'rows')


if __name__ == '__main__':
    main()
