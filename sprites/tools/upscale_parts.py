"""Upscale dumped Xenogears sprite parts 4x with ffmpeg's xBR/hqx filter.

Color and silhouette are scaled separately: transparent pixels are first filled
with neighbouring colors (so the filter does not blend edges towards black),
the alpha mask is scaled as a black/white image and thresholded back to the
binary 0/128 alpha that the HD pack uses.
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

OPAQUE_ALPHA = 128


def fill_transparent(rgb, mask):
    """Propagate opaque colors into transparent pixels (simple iterative dilation)."""
    rgb = rgb.astype(np.float32).copy()
    known = mask.copy()
    h, w = mask.shape
    for _ in range(max(h, w)):
        if known.all():
            break
        acc = np.zeros_like(rgb)
        cnt = np.zeros((h, w), np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            src = np.roll(np.roll(known, dy, 0), dx, 1)
            col = np.roll(np.roll(rgb, dy, 0), dx, 1)
            if dy == -1: src[-1, :] = False
            if dy == 1: src[0, :] = False
            if dx == -1: src[:, -1] = False
            if dx == 1: src[:, 0] = False
            acc += col * src[..., None]
            cnt += src
        grow = (~known) & (cnt > 0)
        rgb[grow] = acc[grow] / cnt[grow][:, None]
        known = known | grow
    return np.clip(rgb, 0, 255).astype(np.uint8)


def ffmpeg_scale(src, dst, filt):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-vf', filt, '-pix_fmt', 'rgb24', dst],
                   check=True, stdin=subprocess.DEVNULL)


def upscale(path, out_path, filt, tmp):
    im = Image.open(path).convert('RGBA')
    a = np.asarray(im)
    mask = a[..., 3] > 0
    if not mask.any():
        return False
    rgb = fill_transparent(a[..., :3], mask)
    c_in, c_out = os.path.join(tmp, 'c.png'), os.path.join(tmp, 'c4.png')
    m_in, m_out = os.path.join(tmp, 'm.png'), os.path.join(tmp, 'm4.png')
    Image.fromarray(rgb, 'RGB').save(c_in)
    Image.fromarray(np.repeat((mask * 255).astype(np.uint8)[..., None], 3, 2), 'RGB').save(m_in)
    ffmpeg_scale(c_in, c_out, filt)
    ffmpeg_scale(m_in, m_out, filt)
    c4 = np.asarray(Image.open(c_out).convert('RGB'))
    m4 = np.asarray(Image.open(m_out).convert('L'))
    alpha = np.where(m4 > 127, OPAQUE_ALPHA, 0).astype(np.uint8)
    Image.fromarray(np.dstack([c4, alpha]), 'RGBA').save(out_path)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--pal', required=True, help='comma-separated palette hashes')
    ap.add_argument('--filter', default='xbr=4')
    args = ap.parse_args()
    pals = set(args.pal.split(','))
    os.makedirs(args.out, exist_ok=True)
    names = [f for f in os.listdir(args.dump)
             if f.lower().endswith('.png') and '-' in f and f[:-4].split('-', 1)[1] in pals]
    done = 0
    with tempfile.TemporaryDirectory() as tmp:
        for f in names:
            if upscale(os.path.join(args.dump, f), os.path.join(args.out, f), args.filter, tmp):
                done += 1
    print(f'parts={len(names)} written={done}')


if __name__ == '__main__':
    sys.exit(main())
