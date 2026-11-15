r"""The gear battle HUD put together as a report's 2D primitives draw it: the original texels (VRAM) | with the HD
(pack files, plus hud\stage for the new names) - item 13 preview (16.11.2026).
  python ai\redraw\gaps_1115\hud_frame.py [<frame.txt>] -> hud\frame_<report>.png
Only primitives on page 960,0 (the HUD sheet). Semi-transparent primitives blend by their page's mode (0 average,
1 add, 2 subtract, 3 add a quarter) where the texel has its STP bit; texel 0 / colour 0 is transparent.
Background: the report's shot_plain.png under the HUD is not clean, so a flat dark grey.
"""
import os
import re
import sys

import cv2
import numpy as np

from gcommon import PACK, side_by_side
from alias_dump_parts import read_bc7_level0
from hud_common import H_DIR, clut, crc, idx4, idx8, vram
from render_frames import psx_to_rgba

Z = 4
STAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hud', 'stage')
LINE = re.compile(r'^2d (\d+) .*?semi (\d) .*?page (\d+),(\d+) depth (\d) pageblend (\d) clut (\d+),(\d+) .*?colour (\d+),(\d+),(\d+) corners '
                  + r'\((-?\d+),(-?\d+) uv ([\d.]+),([\d.]+)\) ' * 4)
DEFAULT = os.path.join(H_DIR, 'rep1', 'reports', '2026-11-15T22-49-30-649', 'frame.txt')


def tex_orig(i, row):
    """RGBA float (alpha: 0 transparent, 1 opaque, 2 opaque + STP) of the sheet through a CLUT row."""
    rgb = np.array([psx_to_rgba(int(c))[:3] for c in row], np.float32)
    a = np.array([0 if int(c) == 0 else (2 if int(c) & 0x8000 else 1) for c in row], np.float32)
    return np.dstack([rgb[i], a[i]])


def tex_hd(path):
    h = read_bc7_level0(path).astype(np.float32)
    t = (h == 0).all(-1)
    a = np.where(t, 0, np.where(h[..., 3] > 0, 2, 1)).astype(np.float32)
    return np.dstack([h[..., :3], a])


def draw(canvas, tex, k, pts, depth, semi, mode, colour):
    src = np.float32([[u * k, (v - 52) * k] for _, _, u, v in pts])
    dst = np.float32([[x * Z, y * Z] for x, y, _, _ in pts])
    if len({tuple(p) for p in src.tolist()}) < 4 or len({tuple(p) for p in dst.tolist()}) < 4:
        return
    M = cv2.getPerspectiveTransform(src, dst)
    H, W = canvas.shape[:2]
    w = cv2.warpPerspective(tex, M, (W, H), flags=cv2.INTER_LINEAR if k > 1 else cv2.INTER_NEAREST,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    mask = np.zeros((H, W), np.uint8)
    cv2.fillConvexPoly(mask, np.int32(dst[[0, 1, 3, 2]]), 1)
    a = np.round(w[..., 3])
    on = (a > 0) & (mask > 0)
    rgb = np.clip(w[..., :3] * np.array(colour, np.float32) / 128, 0, 255)
    stp = on & (a >= 2) & bool(semi)
    plain = on & ~stp
    canvas[plain] = rgb[plain]
    if mode == 0:
        canvas[stp] = (canvas[stp] + rgb[stp]) / 2
    elif mode == 1:
        canvas[stp] = np.clip(canvas[stp] + rgb[stp], 0, 255)
    elif mode == 2:
        canvas[stp] = np.clip(canvas[stp] - rgb[stp], 0, 255)
    else:
        canvas[stp] = np.clip(canvas[stp] + rgb[stp] / 4, 0, 255)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    v = vram()
    words = np.load(os.path.join(os.path.dirname(STAGE), 'upload_words.npy'))
    i4, i8 = idx4(words), idx8(words)
    prims = []
    for line in open(path, encoding='utf-8', errors='replace'):
        m = LINE.match(line)
        if not m:
            continue
        g = [float(x) if '.' in x else int(x) for x in m.groups()]
        n, semi, px, py, depth, mode, cx, cy, r_, g_, b_ = g[:11]
        if (px, py) != (960, 0) or depth > 1:
            continue
        pts = [(g[11 + 4 * i], g[12 + 4 * i], g[13 + 4 * i], g[14 + 4 * i]) for i in range(4)]
        prims.append((n, semi, depth, mode, (cx, cy), (r_, g_, b_), pts))
    cache = {}
    stats = {'hd': 0, 'stage': 0, 'orig': 0}
    pics = []
    for use_hd in (False, True):
        canvas = np.zeros((224 * Z, 320 * Z, 3), np.float32)
        canvas[:] = (40, 44, 48)
        for n, semi, depth, mode, cl, colour, pts in sorted(prims, key=lambda p: -p[0]):
            row = clut(v, cl[0], cl[1], 256 if depth else 16)
            name = f'49b52d64-{crc(row)}'
            tex, k = None, 1
            if use_hd:
                for p, tag in ((os.path.join(PACK, name + '.bc7'), 'hd'), (os.path.join(STAGE, name + '.bc7'), 'stage')):
                    if os.path.exists(p):
                        if p not in cache:
                            cache[p] = tex_hd(p)
                        tex, k = cache[p], 8
                        stats[tag] += 1
                        break
            if tex is None:
                key = (name, depth)
                if key not in cache:
                    cache[key] = tex_orig(i8 if depth else i4, row)
                tex, k = cache[key], 1
                if use_hd:
                    stats['orig'] += 1
            draw(canvas, tex, k, pts, depth, semi, mode, colour)
        pics.append(np.clip(canvas, 0, 255).astype(np.uint8))
    rep = os.path.basename(os.path.dirname(path))
    out = os.path.join(os.path.dirname(STAGE), f'frame_{rep}.png')
    side_by_side(pics).save(out)
    print(len(prims), 'primitives;', stats, '->', out)


if __name__ == '__main__':
    main()
