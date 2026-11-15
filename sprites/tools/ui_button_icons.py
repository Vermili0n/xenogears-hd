"""Clear HD button-prompt icons in battle (01.11.2026, RUS disc).

The deathblow line in battle ("△ <icon> Ukigumo") shows a 12x12 clover of the four face buttons where the lit lobe is
the button to press (top △ green, left □ pink, right ○ red, bottom × blue) - unreadable at native size. The icons live
on the battle UI page: upload 49b52d64 (64x204 words, drawn 8bpp = 128x204 texels); palette 5413f562 is the one that
draws them (in every other palette the icon area is other elements' colours). The replacement is that whole page at
8x: nearest-upscaled (everything else looks exactly as before) with the three clovers redrawn: the lit lobe as a dark
button with a bright rim and the symbol in its colour, the other lobes as dim discs of their colours.

  python ui_button_icons.py [--install]      (--install: RetroArch closed; BC7 into the pack)
Source: ui_icons/49b52d64-5413f562_native.png (core texture dump). Output: ui_icons/49b52d64-5413f562.png + preview.png.
Undo: delete 49b52d64-5413f562.bc7 from the pack.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402

NAME = '49b52d64-5413f562'
DIR = os.path.join(ROOT, 'ui_icons')
PACK = r'<RETROARCH_DRIVE>\RetroArch\system\Xenogears (USA)-texture-replacements'
S = 8          # replacement scale
SS = 4         # supersampling of the drawing
ROW = 76       # top texel row of the clovers
ICONS = [(80, 'bottom'), (92, 'top'), (104, 'left')]   # left texel column, lit lobe
LOBES = {'top': (0, -1), 'left': (-1, 0), 'right': (1, 0), 'bottom': (0, 1)}
SYMBOL = {'top': 'triangle', 'left': 'square', 'right': 'circle', 'bottom': 'cross'}
DIM = {'top': (40, 92, 70), 'left': (82, 60, 112), 'right': (112, 50, 52), 'bottom': (60, 70, 128)}
LIT = {'top': (84, 255, 180), 'left': (255, 176, 255), 'right': (255, 110, 110), 'bottom': (150, 185, 255)}
OUTLINE = (24, 24, 24)
BUTTON = (34, 32, 40)
ALPHA = 127    # the dump's (and the core's) class of these texels: drawn as on the original page


def draw_clover(lit):
    """One 12x12-texel clover at S*SS px per texel -> RGBA (supersampled)."""
    u = S * SS
    n = 12 * u
    im = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = 6.0 * u
    off, r_dim, r_lit = 3.35 * u, 2.05 * u, 2.6 * u
    ow = 0.32 * u
    d.ellipse([c - 1.6 * u, c - 1.6 * u, c + 1.6 * u, c + 1.6 * u], fill=OUTLINE + (255,))
    for name, (dx, dy) in LOBES.items():
        if name == lit:
            continue
        x, y = c + dx * off, c + dy * off
        d.ellipse([x - r_dim - ow, y - r_dim - ow, x + r_dim + ow, y + r_dim + ow], fill=OUTLINE + (255,))
        d.ellipse([x - r_dim, y - r_dim, x + r_dim, y + r_dim], fill=DIM[name] + (255,))
    dx, dy = LOBES[lit]
    x, y = c + dx * off, c + dy * off
    x = min(max(x, r_lit + ow), n - r_lit - ow)
    y = min(max(y, r_lit + ow), n - r_lit - ow)
    col = LIT[lit] + (255,)
    d.ellipse([x - r_lit - ow, y - r_lit - ow, x + r_lit + ow, y + r_lit + ow], fill=OUTLINE + (255,))
    d.ellipse([x - r_lit, y - r_lit, x + r_lit, y + r_lit], fill=col)
    ri = r_lit - 0.42 * u
    d.ellipse([x - ri, y - ri, x + ri, y + ri], fill=BUTTON + (255,))
    w = int(0.36 * u)
    k = ri * 0.62
    sym = SYMBOL[lit]
    if sym == 'triangle':
        pts = [(x, y - k * 1.05), (x + k * 0.98, y + k * 0.68), (x - k * 0.98, y + k * 0.68)]
        d.line(pts + [pts[0], pts[1]], fill=col, width=w, joint='curve')
    elif sym == 'square':
        q = k * 0.78
        d.rectangle([x - q, y - q, x + q, y + q], outline=col, width=w)
    elif sym == 'cross':
        q = k * 0.8
        d.line([(x - q, y - q), (x + q, y + q)], fill=col, width=w)
        d.line([(x - q, y + q), (x + q, y - q)], fill=col, width=w)
    else:
        d.ellipse([x - k * 0.8, y - k * 0.8, x + k * 0.8, y + k * 0.8], outline=col, width=w)
    return im


def downsample(im):
    """Supersampled RGBA -> S px per texel: colour = coverage-weighted mean, alpha binary (edges smoothed by the GPU)."""
    a = np.asarray(im).astype(np.float64)
    h, w = a.shape[0] // SS, a.shape[1] // SS
    blk = a.reshape(h, SS, w, SS, 4)
    cov = blk[..., 3].mean((1, 3)) / 255.0
    rgb = (blk[..., :3] * blk[..., 3:4]).sum((1, 3)) / np.maximum(blk[..., 3].sum((1, 3)), 1e-9)[..., None]
    out = np.zeros((h, w, 4), np.uint8)
    on = cov >= 0.5
    out[..., :3] = np.clip(np.rint(rgb), 1, 255).astype(np.uint8)   # never pure black: black + alpha = transparent
    out[..., 3] = np.where(on, ALPHA, 0)
    out[~on] = 0
    return out


def build():
    src = np.asarray(Image.open(os.path.join(DIR, NAME + '_native.png')).convert('RGBA'))
    hd = np.kron(src, np.ones((S, S, 1), np.uint8))
    for x0, lit in ICONS:
        tile = downsample(draw_clover(lit))
        hd[ROW * S:(ROW + 12) * S, x0 * S:(x0 + 12) * S] = tile
    return src, hd


def preview(src, hd):
    """Native vs HD on battle sand at the on-screen size (~4.5x)."""
    box = (78, 74, 118, 90)
    sand = (232, 214, 172, 255)
    tiles = []
    for img, sc in ((src, 1), (hd, S)):
        crop = Image.fromarray(img[box[1] * sc:box[3] * sc, box[0] * sc:box[2] * sc]).convert('RGBA')
        a = np.asarray(crop).copy()
        a[..., 3] = np.where(a[..., 3] > 0, 255, 0)
        crop = Image.fromarray(a)
        size = (int((box[2] - box[0]) * 4.5) * 2, int((box[3] - box[1]) * 4.5) * 2)
        bg = Image.new('RGBA', crop.size, sand)
        bg.alpha_composite(crop)
        tiles.append(bg.resize(size, Image.NEAREST if sc == 1 else Image.LANCZOS))
    out = Image.new('RGBA', (tiles[0].width, tiles[0].height * 2 + 12), (60, 60, 60, 255))
    out.paste(tiles[0], (0, 0))
    out.paste(tiles[1], (0, tiles[0].height + 12))
    out.save(os.path.join(DIR, 'preview.png'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', action='store_true')
    a = ap.parse_args()
    src, hd = build()
    Image.fromarray(hd, 'RGBA').save(os.path.join(DIR, NAME + '.png'))
    preview(src, hd)
    print('written', os.path.join(DIR, NAME + '.png'), hd.shape[1], 'x', hd.shape[0])
    if a.install:
        lv, flags = bc7pack.levels_of(hd)
        enc, failed, _ = bc7pack.encode_levels(lv)
        if failed:
            sys.exit(f'BC7 rules failed in {failed} blocks - not installed')
        dst = os.path.join(PACK, NAME + '.bc7')
        with open(dst + '.tmp', 'wb') as f:
            f.write(bc7pack.pack_file(enc, hd.shape[1], hd.shape[0], flags))
        os.replace(dst + '.tmp', dst)
        print('installed', dst)


if __name__ == '__main__':
    main()
