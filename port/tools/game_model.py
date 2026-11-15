"""The user's model of how the game draws a sprite frame from the pack (xeno_sprites/tools/eyepatch_fix/patch_game.py,
game_part / game_frame), restated here: each piece a w x h quad at (dx + mx, dy + my), showing the first (w - 1) x (h - 1)
of its pack picture stretched over it, flipped as the layout says. Reads the pack's BC7 with the user's xbc7.dll.

Usage: python game_model.py <hero folder> <set key> <frame> [<frame> ...] --out <png> [--k 8]
"""
import argparse
import ctypes
import json
import os
import struct
import zlib

import numpy as np
from PIL import Image

PACK = os.environ.get('XENO_PACK', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pack'))
# A BC7 decoder DLL with xbc7_init / xbc7_decode (not part of this repository): XENO_XBC7=<path>.
XBC7 = os.environ.get('XENO_XBC7', 'xbc7.dll')
_dll = None


def read_bc7(path):
    global _dll
    if _dll is None:
        _dll = ctypes.CDLL(XBC7)
        _dll.xbc7_init(1, 0)
    data = open(path, 'rb').read()
    _, _, w, h, _, _, raw_size, flags = struct.unpack_from('<4s7I', data, 0)
    raw = zlib.decompress(data[32:]) if flags & 1 else data[32:]
    out = np.zeros((h, w, 4), np.uint8)
    _dll.xbc7_decode(raw[:((w + 3) // 4) * ((h + 3) // 4) * 16], w, h, out.ctypes.data_as(ctypes.c_void_p))
    out[..., 3] = np.where(out.any(axis=-1), 255, 0)
    return out


def game_part(a, w, h, k):
    """HD picture -> what the game's w x h quad shows, at k px per texel (patch_game.game_part)."""
    H, W = a.shape[:2]
    tw = int(round((w - 1) * W / w)) if w > 1 else W
    th = int(round((h - 1) * H / h)) if h > 1 else H
    c = a[:th, :tw]
    rgb = Image.fromarray(np.ascontiguousarray(c[..., :3])).resize((w * k, h * k), Image.LANCZOS)
    alpha = Image.fromarray(np.where(c[..., 3] > 0, 255, 0).astype(np.uint8)).resize((w * k, h * k), Image.NEAREST)
    rgb.putalpha(alpha)
    return rgb


def frame(hero_dir, set_key, fi, k):
    layout = json.load(open(os.path.join(hero_dir, 'layout.json')))[set_key]
    places = []
    for p in layout['frames'][fi]:
        pal = layout['palettes'][min(p['clut'], len(layout['palettes']) - 1)]
        size = Image.open(os.path.join(hero_dir, 'parts', f"{p['block']}-{pal}.png")).size
        places.append({**p, 'pal': pal, 'w': size[0], 'h': size[1], 'x': p['dx'] + p['mx'], 'y': p['dy'] + p['my']})
    x0, y0 = min(p['x'] for p in places), min(p['y'] for p in places)
    W = max(p['x'] + p['w'] for p in places) - x0
    H = max(p['y'] + p['h'] for p in places) - y0
    out = Image.new('RGBA', (W * k, H * k), (0, 0, 0, 0))
    for p in places:
        path = os.path.join(PACK, f"{p['block']}-{p['pal']}.bc7")
        if os.path.exists(path):
            im = game_part(read_bc7(path), p['w'], p['h'], k)
        else:
            im = Image.open(os.path.join(hero_dir, 'parts', f"{p['block']}-{p['pal']}.png")).convert('RGBA').resize((p['w'] * k, p['h'] * k), Image.NEAREST)
        if p['flipx']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        out.alpha_composite(im, ((p['x'] - x0) * k, (p['y'] - y0) * k))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('hero')
    ap.add_argument('set')
    ap.add_argument('frames', nargs='+', type=int)
    ap.add_argument('--out', required=True)
    ap.add_argument('--k', type=int, default=8)
    a = ap.parse_args()
    images = [frame(a.hero, a.set, fi, a.k) for fi in a.frames]
    sheet = Image.new('RGBA', (sum(i.width for i in images) + 8 * len(images), max(i.height for i in images)), (40, 40, 40, 255))
    x = 0
    for i in images:
        sheet.alpha_composite(i, (x, 0))
        x += i.width + 8
    sheet.save(a.out)


if __name__ == '__main__':
    main()
