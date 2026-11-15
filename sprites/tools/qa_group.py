"""QA sheet of one production group: every RENDERED frame as sprite | composed result (what the slicer used),
numbered by frame, for spotting orientation / eyepatch / identity errors (fix list: ai/prod/fixlist.json).

  python qa_group.py c_bart_70a4dc [c_bart_9522cf ...] [--cols 10] [--h 150]
Writes pod/report/qa/<group>.png.
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


def tile(im, h):
    im = im.copy()
    im.thumbnail((h, h), Image.LANCZOS)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('groups', nargs='+')
    ap.add_argument('--cols', type=int, default=10)
    ap.add_argument('--h', type=int, default=150)
    ap.add_argument('--page', type=int, default=30, help='frames per sheet page')
    a = ap.parse_args()
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    out_dir = os.path.join(ROOT, 'pod', 'report', 'qa')
    os.makedirs(out_dir, exist_ok=True)
    for g in a.groups:
        names = sorted((n for n, m in meta.items() if m['group'] == g), key=lambda n: (meta[n]['set'], meta[n]['frame']))
        if not names:
            print(g, 'no frames')
            continue
        h = Hero(os.path.join(ROOT, meta[names[0]]['hero_dir']))
        work = os.path.join(ROOT, 'ai', 'prod_work', g, 'work')
        cells = []
        for n in names:
            m = meta[n]
            red = os.path.join(work, f"{m['set']}_{m['frame']:03d}_red.png")
            if not os.path.exists(red):
                continue
            o = frame_rgba(h, m['set'], m['frame'])
            ob = Image.new('RGBA', o.size, BG + (255,))
            ob.alpha_composite(o)
            r = Image.open(red).convert('RGB')
            mask = o.getchannel('A').point(lambda v: 255 if v > 127 else 0)
            rb = Image.new('RGB', r.size, BG)
            rb.paste(r, (0, 0), mask)
            cells.append((f"{m['set']}:{m['frame']}", tile(ob.convert('RGB'), a.h), tile(rb, a.h)))
        if not cells:
            print(g, 'no composed frames yet')
            continue
        W, H = 2 * a.h + 6, a.h + 16
        for pg in range(0, len(cells), a.page):
            part = cells[pg:pg + a.page]
            rows = (len(part) + a.cols - 1) // a.cols
            sheet = Image.new('RGB', (W * a.cols, H * rows), (45, 45, 45))
            d = ImageDraw.Draw(sheet)
            for i, (lab, o, r) in enumerate(part):
                x, y = (i % a.cols) * W, (i // a.cols) * H
                d.text((x + 2, y + 1), lab, fill=(255, 255, 0))
                sheet.paste(o, (x + (a.h - o.width) // 2, y + 14 + a.h - o.height))
                sheet.paste(r, (x + a.h + 4 + (a.h - r.width) // 2, y + 14 + a.h - r.height))
            p = os.path.join(out_dir, f'{g}_{pg // a.page}.png')
            sheet.save(p)
        print(g, len(cells), 'frames ->', (len(cells) + a.page - 1) // a.page, 'pages')


if __name__ == '__main__':
    main()
