r"""Sheet of scene_recolor results: per name the HD under the source palette, the recoloured one and the original texels
in the target palette (x HD scale), each fitted into a 300x150 cell.  python scene_sheet.py <map>"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from gcommon import HERE, hd, show
from scene_recolor import OUT, cluts, disc, indices, map_vram
from npc_maps import lut


def fit(a, W=300, H=150):
    im = Image.fromarray(np.ascontiguousarray(a))
    k = min(W / im.width, H / im.height)
    im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.NEAREST if k > 1 else Image.LANCZOS)
    c = Image.new('RGB', (W, H), (40, 40, 40))
    c.paste(im, (0, 0))
    return c


def main():
    m = int(sys.argv[1])
    info = json.load(open(os.path.join(OUT, f'{m}.json')))
    mm, toc = disc()
    vram, blocks = map_vram(mm, toc, m)
    blk = {f"{b['hash']:x}": b for b in blocks}
    cl = cluts(vram)
    rows = []
    for note in info['notes']:
        if ': from ' not in note:
            continue
        name, rest = note.split(': from ')
        src = rest.split(' ')[0]
        up, pal = name.split('-')
        bpp = 8 if cl[pal][0] == '8' else 4
        idx = indices(vram, blk[up], bpp)
        orig = lut([int(c) for c in cl[pal][1]])[idx][..., :3]
        new = __import__('alias_dump_parts').read_bc7_level0(os.path.join(OUT, 'stage', name + '.bc7'))
        rows.append((name, [fit(show(hd(f'{up}-{src}'))), fit(show(new)), fit(orig)]))
    per = 2
    W, H = 3 * 304 * per, ((len(rows) + per - 1) // per) * 168
    sheet = Image.new('RGB', (W, H), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, (name, cells) in enumerate(rows):
        x0, y0 = (i % per) * 3 * 304, (i // per) * 168
        d.text((x0 + 2, y0 + 2), name + '  (pack HD other palette | recoloured | original)', fill=(255, 255, 0))
        for j, c in enumerate(cells):
            sheet.paste(c, (x0 + j * 304, y0 + 16))
    sheet.save(os.path.join(OUT, f'{m}_sheet.png'))
    print(len(rows), 'rows ->', os.path.join(OUT, f'{m}_sheet.png'), sheet.size)


if __name__ == '__main__':
    main()
