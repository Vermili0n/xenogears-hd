r"""Local candidates for the field system images the pack lacks (compass dial 913fcf-20165069, compass shadow
6bdfe265-31f23b8f, particle sheet 24d69ca8-d7bc17be): xBR 4x + Lanczos 2x = 8x (ai_redraw.xbr4, CPU, ffmpeg), the base
the sprite pipeline starts from. Written to sysimg\cand\<name>.bc7 + sysimg\cand_preview.png; NOT installed (the user
judged plain upscales of sprites «всё не то»; for UI pieces it is his call)."""
import os
import sys

import numpy as np
from PIL import Image

from gcommon import HERE, side_by_side
from ai_redraw import xbr4  # noqa: E402
from sysimg import images, rgba

S = 8
WANT = {'913fcf': '20165069', '6bdfe265': '31f23b8f', '24d69ca8': 'd7bc17be'}


def main():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'redraw', 'battle_palettes'))
    from battle_rects import write_bc7
    out = os.path.join(HERE, 'sysimg', 'cand')
    os.makedirs(out, exist_ok=True)
    cells = []
    for im in images():
        if im['name'] not in WANT:
            continue
        row = im['clut'][0]
        a = rgba(im['idx'], row[:256] if im['bpp'] else row[:16])
        a[..., 3] = np.where(a[..., 3] > 0, 255, 0)
        c4, m4 = xbr4(Image.fromarray(a, 'RGBA'))
        c8 = np.asarray(Image.fromarray(c4).resize((c4.shape[1] * 2, c4.shape[0] * 2), Image.LANCZOS))
        m8 = np.repeat(np.repeat(m4, 2, 0), 2, 1)
        hd = np.zeros(c8.shape[:2] + (4,), np.uint8)
        hd[..., :3] = c8
        hd[..., 3] = np.where(m8, 255, 0)
        hd[~m8] = 0
        hd[m8 & (hd[..., :3] == 0).all(-1), 0] = 1
        name = f'{im["name"]}-{WANT[im["name"]]}'
        write_bc7(os.path.join(out, name + '.bc7'), hd)
        bg = np.zeros(hd.shape[:2] + (3,), np.uint8)
        bg[:] = (60, 60, 90)
        bg[m8] = hd[..., :3][m8]
        lo = np.repeat(np.repeat(np.where(a[..., 3:] > 0, a[..., :3], (60, 60, 90)).astype(np.uint8), S, 0), S, 1)
        cells += [lo, bg]
        print(name, hd.shape)
    side_by_side(cells).save(os.path.join(HERE, 'sysimg', 'cand_preview.png'))


if __name__ == '__main__':
    main()
