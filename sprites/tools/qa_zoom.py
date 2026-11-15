"""Large sprite | render pairs (nearest-neighbour sprite) for chosen frames of one group, flowed onto readable sheets.

  python qa_zoom.py <group> <f1,f2,...|csv:path> [--set npc] [--h 260] [--max-w 2000] [--max-h 1400]
                    [--per-row N] [--rows N] [--crop-top 0.3] [--tag x]
csv:path takes the flagged frames of this group from a qa_backview.py --csv file.
Layout: each pair keeps its own width (wide, low poses do not widen the other columns); a pair wider than the sheet is
scaled down to fit; rows wrap at --max-w (2000 = shown without downscaling), pages break at --max-h.
--per-row / --rows are optional extra caps (0 = no cap).
Writes pod/report/qa/z_<group><tag>_<n>.png.
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402

BG = (150, 170, 90)
GAP = 10      # px between pairs and around the sheet
LABEL = 18    # px for the frame label above a pair


def pair(sprite, render, max_w):
    """sprite | render side by side as one image; scaled down when wider than max_w."""
    im = Image.new('RGB', (sprite.width + 4 + render.width, max(sprite.height, render.height)), (45, 45, 45))
    im.paste(sprite, (0, 0))
    im.paste(render, (sprite.width + 4, 0))
    if im.width > max_w:
        im = im.resize((max_w, max(1, round(im.height * max_w / im.width))), Image.LANCZOS)
    return im


def layout(cells, max_w, max_h, per_row=0, max_rows=0):
    """Flow pairs into rows (wrap at max_w) and rows into pages (break at max_h).
    -> pages: [[(x, y, label, image), ...] per row, ...]"""
    pages, page, row, x, y, row_h = [], [], [], GAP, GAP, 0
    for lab, im in cells:
        if row and (x + im.width + GAP > max_w or (per_row and len(row) >= per_row)):
            page.append(row)
            row, x, y = [], GAP, y + row_h + GAP
            row_h = 0
            if y + LABEL + im.height + GAP > max_h or (max_rows and len(page) >= max_rows):
                pages.append(page)
                page, y = [], GAP
        row.append((x, y, lab, im))
        x += im.width + GAP
        row_h = max(row_h, LABEL + im.height)
    if row:
        page.append(row)
    if page:
        pages.append(page)
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('group')
    ap.add_argument('frames')
    ap.add_argument('--set', default=None, help='only this sprite set (default: any)')
    ap.add_argument('--h', type=int, default=260, help='pair height in px (before fitting into --max-w)')
    ap.add_argument('--max-w', type=int, default=2000, help='sheet width in px')
    ap.add_argument('--max-h', type=int, default=1400, help='sheet height in px (page break)')
    ap.add_argument('--per-row', type=int, default=0, help='max pairs per row (0 = only --max-w decides)')
    ap.add_argument('--rows', type=int, default=0, help='max rows per sheet (0 = only --max-h decides)')
    ap.add_argument('--tag', default='', help='file name suffix')
    ap.add_argument('--crop-top', type=float, default=0, help='show only the top part of the figure (heads)')
    a = ap.parse_args()
    if a.frames.startswith('csv:'):
        want = [(ln.split(',')[1], int(ln.split(',')[2])) for ln in open(a.frames[4:])
                if ln.startswith(a.group + ',') and ln.strip().endswith(',1')]
    else:
        want = [(a.set, int(x)) for x in a.frames.split(',')]
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    by = {(m['set'], m['frame']): n for n, m in meta.items() if m['group'] == a.group}
    h = Hero(os.path.join(ROOT, meta[next(iter(by.values()))]['hero_dir']))
    work = os.path.join(ROOT, 'ai', 'prod_work', a.group, 'work')
    cells = []
    for s, f in want:
        key = (s, f) if s else next(k for k in by if k[1] == f)
        o = frame_rgba(h, key[0], key[1])
        ob = Image.new('RGBA', o.size, BG + (255,))
        ob.alpha_composite(o)
        ob = ob.convert('RGB').resize((max(1, round(o.width * a.h / o.height)), a.h), Image.NEAREST)
        r = Image.open(os.path.join(work, f'{key[0]}_{key[1]:03d}_red.png')).convert('RGB')
        mask = o.getchannel('A').point(lambda v: 255 if v > 127 else 0)
        rb = Image.new('RGB', r.size, BG)
        rb.paste(r, (0, 0), mask)
        if a.crop_top:
            bb = mask.getbbox()
            y1 = bb[1] + max(2, int((bb[3] - bb[1]) * a.crop_top))
            hb = mask.crop((0, bb[1], mask.width, bb[1] + max(2, (y1 - bb[1]) // 2))).getbbox() or bb
            pad = (hb[2] - hb[0]) * 0.35
            box = (max(0, int(hb[0] - pad)), bb[1], min(mask.width, int(hb[2] + pad)), y1)
            o2 = Image.new('RGBA', o.size, BG + (255,))
            o2.alpha_composite(o)
            ob = o2.convert('RGB').crop(box).resize((max(1, round((box[2] - box[0]) * a.h / (box[3] - box[1]))), a.h),
                                                     Image.NEAREST)
            rb = rb.crop(box)
        rb = rb.resize((max(1, round(rb.width * a.h / rb.height)), a.h), Image.LANCZOS)
        cells.append((f'{key[0]}:{key[1]}', pair(ob, rb, a.max_w - 2 * GAP)))
    if not cells:
        print('nothing to show')
        return
    out_dir = os.path.join(ROOT, 'pod', 'report', 'qa')
    for n, page in enumerate(layout(cells, a.max_w, a.max_h, a.per_row, a.rows)):
        W = max(x + im.width for row in page for x, _, _, im in row) + GAP
        H = max(y + LABEL + im.height for row in page for _, y, _, im in row) + GAP
        sheet = Image.new('RGB', (W, H), (45, 45, 45))
        d = ImageDraw.Draw(sheet)
        for row in page:
            for x, y, lab, im in row:
                d.text((x + 2, y + 2), lab, fill=(255, 255, 0))
                sheet.paste(im, (x, y + LABEL))
        p = os.path.join(out_dir, f'z_{a.group}{a.tag}_{n}.png')
        sheet.save(p)
        print(p, sum(len(r) for r in page), 'pairs', f'{W}x{H}')


if __name__ == '__main__':
    main()
