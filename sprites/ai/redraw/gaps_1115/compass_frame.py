r"""The compass put together as the game draws it, original vs HD (16.11.2026): the 2D primitives of an F6 report
(the shadow's 4 quads, subtractive; the dial's 16 quads) mapped from their texels onto the 320x224 screen, x6.
  python ai\redraw\gaps_1115\compass_frame.py [<frame.txt>]  -> compass\frame_assembled.png (original | HD), seams by eye
A quad's texels span u0..u1 as the primitive gives them (the game shows 16-texel tiles through 15 texels); the HD is
sampled over the same span x8, as the port samples a pack picture.
"""
import os
import re
import sys

import cv2
import numpy as np

from gcommon import HERE, side_by_side
from alias_dump_parts import read_bc7_level0
from compass_draw import pal_rgb
from sysimg import images

Z = 6
REPORT = r'<XENO_PORT>\out\frame_reports\2026-11-15T19-08-13-690\frame.txt'
LINE = re.compile(r'^2d (\d+) .*?semi (\d) .*?depth (\d) .*?clut (\d+),(\d+) .*?corners ' + r'\((-?\d+),(-?\d+) uv (\d+),(\d+)\) ' * 4)


def quads(path):
    out = []
    for line in open(path, encoding='utf-8', errors='replace'):
        m = LINE.match(line)
        if not m:
            continue
        g = list(map(int, m.groups()))
        n, semi, depth, cx, cy = g[:5]
        pts = [(g[5 + 4 * i], g[6 + 4 * i], g[7 + 4 * i], g[8 + 4 * i]) for i in range(4)]
        if (cx, cy) == (0, 251) and depth == 1:
            out.append(('dial', pts, semi))
        elif (cx, cy) == (256, 242) and depth == 0:
            out.append(('shadow', pts, semi))
    return out


def tex_rgba(idx, row, hd):
    """Texture as float RGBA (alpha 1 opaque) at 1x (original) or the HD."""
    if hd is not None:
        rgb = hd[..., :3].astype(np.float32)
        a = (~(hd == 0).all(-1)).astype(np.float32)
        return np.dstack([rgb, a]), 8
    rgb = pal_rgb(row)[idx]
    return np.dstack([rgb, (idx > 0).astype(np.float32)]), 1


def draw(canvas, tex, k, pts, origin, mode):
    src = np.float32([[(u - origin[0]) * k, (v - origin[1]) * k] for _, _, u, v in pts])
    dst = np.float32([[x * Z, y * Z] for x, y, _, _ in pts])
    M = cv2.getPerspectiveTransform(src, dst)
    H, W = canvas.shape[:2]
    warped = cv2.warpPerspective(tex, M, (W, H), flags=cv2.INTER_LINEAR if k > 1 else cv2.INTER_NEAREST,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    # coverage of the quad itself
    mask = np.zeros((H, W), np.uint8)
    cv2.fillConvexPoly(mask, np.int32(dst[[0, 1, 3, 2]]), 1)
    a = (warped[..., 3] > 0.5) & (mask > 0)
    if mode == 'subtract':
        canvas[a] = np.clip(canvas[a] - warped[..., :3][a], 0, 255)
    else:
        canvas[a] = warped[..., :3][a]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else REPORT
    ims = {im['name']: im for im in images()}
    dial, shad = ims['913fcf'], ims['6bdfe265']
    stage = os.path.join(HERE, 'compass', 'stage')
    q = quads(path)
    pics = []
    for use_hd in (False, True):
        canvas = np.zeros((224 * Z, 320 * Z, 3), np.float32)
        canvas[:] = (110, 130, 110)
        dt = tex_rgba(dial['idx'].astype(int), dial['clut'][0][:256],
                      read_bc7_level0(os.path.join(stage, '913fcf-20165069.bc7')) if use_hd else None)
        st = tex_rgba(shad['idx'].astype(int), shad['clut'][0][:16],
                      read_bc7_level0(os.path.join(stage, '6bdfe265-31f23b8f.bc7')) if use_hd else None)
        for kind, pts, semi in q:
            if kind == 'shadow':
                draw(canvas, st[0], st[1], pts, (0, 192), 'subtract' if semi else 'over')
        for kind, pts, semi in q:
            if kind == 'dial':
                draw(canvas, dt[0], dt[1], pts, (64, 192), 'over')
        crop = canvas[140 * Z:200 * Z, 210 * Z:330 * Z]
        pics.append(np.clip(crop, 0, 255).astype(np.uint8))
    side_by_side(pics).save(os.path.join(HERE, 'compass', 'frame_assembled.png'))
    print(len(q), 'quads;', os.path.join(HERE, 'compass', 'frame_assembled.png'))


if __name__ == '__main__':
    main()
