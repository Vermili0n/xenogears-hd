"""Review sheets BEFORE fix_apply.py: per re-rendered job a row  sprite (control) | current render | new render,
raw renders cropped to the figure; frames only (head close-ups are pasted in by compose anyway).

  python fix_review.py <folder with the new renders (…/v4)> [--map ai/prod/fix_map.json] [--h 260] [--tag fix3]
Current render = pod/report/prod/res_prod/v4/<name>.png (what is installed now). Kind label from fixlist.json
('group' for whole-group re-renders). Writes pod/report/qa/review_<tag>_<n>.png: a grid of cases, pages of at most 2000x1400 px.
"""
import argparse
import json
import os

from PIL import Image, ImageDraw

from fixtest_sheet import figure_box

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROD = os.path.join(ROOT, 'ai', 'prod')
RES = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod', 'v4')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fixed')
    ap.add_argument('--map', default=os.path.join(PROD, 'fix_map.json'))
    ap.add_argument('--h', type=int, default=260)
    ap.add_argument('--tag', default='fix')
    ap.add_argument('--max-h', type=int, default=1400)
    ap.add_argument('--max-w', type=int, default=2000)
    a = ap.parse_args()
    fmap = json.load(open(a.map))
    fix = json.load(open(os.path.join(PROD, 'fixlist.json')))
    jobs = {}
    for fn in ('jobs_v4.json', 'jobs_v2.json'):
        for j in json.load(open(os.path.join(PROD, fn))):
            jobs[j['name']] = j
    rows = []
    for rep in sorted(fmap):
        if rep.endswith('__head'):
            continue
        new = os.path.join(a.fixed, rep + '.png')
        old = os.path.join(RES, rep + '.png')
        if not os.path.exists(new) or not os.path.exists(old):
            continue
        c = Image.open(os.path.join(PROD, jobs[rep]['control'])).convert('RGB')
        box = figure_box(c)
        w = round((box[2] - box[0]) * a.h / (box[3] - box[1]))
        cells = [c.crop(box).resize((w, a.h), Image.NEAREST)]
        for p in (old, new):
            cells.append(Image.open(p).convert('RGB').crop(box).resize((w, a.h), Image.LANCZOS))
        twins = len(fmap[rep])
        rows.append((f"{rep.split('__')[0][:24]}:{rep.rsplit('_', 1)[1]}  {fix.get(rep, 'group')}"
                     + (f'  (+{twins - 1} twins)' if twins > 1 else ''), cells))
    # one tile per case: label over  sprite | now | new ; tiles flow into rows of <= max_w, rows into pages of <= max_h
    tiles = []
    for lab, cells in rows:
        tw = sum(im.width + 4 for im in cells)
        t = Image.new('RGB', (max(tw, 160), a.h + 16), (40, 40, 40))
        ImageDraw.Draw(t).text((2, 2), lab, fill=(255, 255, 0))
        x = 0
        for im in cells:
            t.paste(im, (x, 16))
            x += im.width + 4
        tiles.append(t)
    pages, page, row, x = [], [], [], 0
    for t in tiles:
        if row and x + t.width > a.max_w:
            page.append(row)
            row, x = [], 0
            if (len(page) + 1) * (a.h + 24) > a.max_h:
                pages.append(page)
                page = []
        row.append(t)
        x += t.width + 8
    if row:
        page.append(row)
    if page:
        pages.append(page)
    for n, pg in enumerate(pages):
        W = max(sum(t.width + 8 for t in r) for r in pg)
        sheet = Image.new('RGB', (W, len(pg) * (a.h + 24)), (25, 25, 25))
        for i, r in enumerate(pg):
            x = 0
            for t in r:
                sheet.paste(t, (x, i * (a.h + 24)))
                x += t.width + 8
        p = os.path.join(ROOT, 'pod', 'report', 'qa', f'review_{a.tag}_{n}.png')
        sheet.save(p)
        print(p, sum(len(r) for r in pg), 'cases')


if __name__ == '__main__':
    main()
