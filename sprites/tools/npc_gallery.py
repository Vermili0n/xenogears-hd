"""Numbered gallery of every NPC sprite set (both discs) so the user can say which one a character is.

  python npc_gallery.py   -> for_chatgpt/_NPC_GALLERY_<page>.png + for_chatgpt/_npc_gallery.json {number: nid}
Order: most used sets first. Thumbnail = front view (same rule as char_package.views), 3x nearest.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from char_package import views  # noqa: E402

D = os.path.join(ROOT, 'for_chatgpt')


def main():
    sets = {}
    for root in ('npc_all', 'npc_all_d2'):
        idx = json.load(open(os.path.join(ROOT, 'extracted', root, 'index.json')))
        for nid, v in idx.items():
            if nid not in sets:
                sets[nid] = (v['uses'], root)
    order = sorted(sets, key=lambda n: -sets[n][0])
    S, cols, rows = 120, 10, 6
    font = ImageFont.truetype('arial.ttf', 18)
    mapping, page, cells = {}, 1, []
    for nid in order:
        h = Hero(os.path.join(ROOT, 'extracted', sets[nid][1], nid))
        try:
            im, _ = h.assemble(h.placements('npc', views(h)[0]))
        except Exception:
            continue
        if im.width * im.height < 30:
            continue
        cells.append((nid, im))
    for p0 in range(0, len(cells), cols * rows):
        sheet = Image.new('RGB', (cols * S, rows * (S + 24)), (70, 70, 70))
        d = ImageDraw.Draw(sheet)
        for k, (nid, im) in enumerate(cells[p0:p0 + cols * rows]):
            num = p0 + k + 1
            mapping[num] = nid
            sc = min((S - 6) / im.width, (S - 6) / im.height, 3)
            im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.NEAREST)
            bg = Image.new('RGBA', im.size, (70, 70, 70, 255))
            bg.alpha_composite(im)
            x, y = (k % cols) * S, (k // cols) * (S + 24)
            sheet.paste(bg.convert('RGB'), (x + (S - im.width) // 2, y + 24 + (S - im.height) // 2))
            d.text((x + 4, y + 2), str(num), fill=(255, 230, 0), font=font)
        sheet.save(os.path.join(D, f'_NPC_GALLERY_{page}.png'))
        page += 1
    json.dump(mapping, open(os.path.join(D, '_npc_gallery.json'), 'w'), indent=0)
    print(len(cells), 'sets on', page - 1, 'pages')


if __name__ == '__main__':
    main()
