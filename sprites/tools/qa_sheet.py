"""Compact QA sheets: sprite (nearest) | render pairs packed by their real width into pages of at most 1600x1600 px.

  python qa_sheet.py <group> <sel.csv> [--h 180] [--tag _auto]
sel.csv lines: group,set,frame,flagged(0/1). Flagged pairs get a red label. Writes pod/report/qa/z_<group><tag>_<n>.png
and prints one path per page.
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

ROOT = r'<XENO_SPRITES>'
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402

BG = (150, 170, 90)
PAGE = 1600
LAB = 16


def pair(h, work, s, f, hh):
    o = frame_rgba(h, s, f)
    ob = Image.new('RGBA', o.size, BG + (255,))
    ob.alpha_composite(o)
    mask = o.getchannel('A').point(lambda v: 255 if v > 127 else 0)
    r = Image.open(os.path.join(work, f'{s}_{f:03d}_red.png')).convert('RGB')
    rb = Image.new('RGB', r.size, BG)
    rb.paste(r, (0, 0), mask)
    bb = mask.getbbox() or (0, 0, o.width, o.height)
    ob, rb = ob.convert('RGB').crop(bb), rb.crop(bb)
    w = max(1, round(ob.width * hh / ob.height))
    if 2 * w + 4 > PAGE:                     # very wide frame: fit the page width
        w = (PAGE - 4) // 2
    hh2 = max(1, round(ob.height * w / ob.width))
    cell = Image.new('RGB', (2 * w + 4, hh2), (45, 45, 45))
    cell.paste(ob.resize((w, hh2), Image.NEAREST), (0, 0))
    cell.paste(rb.resize((w, hh2), Image.LANCZOS), (w + 4, 0))
    return cell


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('group')
    ap.add_argument('sel')
    ap.add_argument('--h', type=int, default=180)
    ap.add_argument('--tag', default='_auto')
    a = ap.parse_args()
    want = []
    for ln in open(a.sel):
        p = ln.strip().split(',')
        if p[0] == a.group:
            want.append((p[1], int(p[2]), p[3] == '1'))
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    hd = next(m['hero_dir'] for m in meta.values() if m['group'] == a.group)
    h = Hero(os.path.join(ROOT, hd))
    work = os.path.join(ROOT, 'ai', 'prod_work', a.group, 'work')
    cells = [(f'{s}:{f}', fl, pair(h, work, s, f, a.h)) for s, f, fl in want]
    pages, rows, row, x = [], [], [], 0       # greedy packing: rows of cells, pages of rows
    for c in cells:
        if row and x + c[2].width > PAGE:
            rows.append(row)
            row, x = [], 0
        row.append(c)
        x += c[2].width + 8
    if row:
        rows.append(row)
    page, y = [], 0
    for r in rows:
        rh = max(c[2].height for c in r) + LAB + 6
        if page and y + rh > PAGE:
            pages.append(page)
            page, y = [], 0
        page.append(r)
        y += rh
    if page:
        pages.append(page)
    out_dir = os.path.join(ROOT, 'pod', 'report', 'qa')
    for k, pg in enumerate(pages):
        W = max(sum(c[2].width + 8 for c in r) for r in pg)
        H = sum(max(c[2].height for c in r) + LAB + 6 for r in pg)
        sheet = Image.new('RGB', (W, H), (30, 30, 30))
        d = ImageDraw.Draw(sheet)
        y = 0
        for r in pg:
            x = 0
            for lab, fl, im in r:
                d.text((x + 2, y + 2), lab + (' !' if fl else ''), fill=(255, 60, 60) if fl else (255, 255, 0))
                sheet.paste(im, (x, y + LAB))
                x += im.width + 8
            y += max(c[2].height for c in r) + LAB + 6
        p = os.path.join(out_dir, f'z_{a.group}{a.tag}_{k}.png')
        sheet.save(p)
        print(p)


if __name__ == '__main__':
    main()
