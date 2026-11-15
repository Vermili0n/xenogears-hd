"""Real-ESRGAN variant for sprite parts.

prep:    write color-filled RGB copies of the parts (transparent pixels filled with
         neighbouring colors) into a folder for realesrgan-ncnn-vulkan.
combine: take the 4x RGB produced by the network and the binary 0/128 alpha of an
         already upscaled variant (xBR silhouette) and write final RGBA parts.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upscale_parts import fill_transparent  # noqa: E402


def prep(dump, pals, out):
    os.makedirs(out, exist_ok=True)
    n = 0
    for f in os.listdir(dump):
        if not f.lower().endswith('.png') or '-' not in f or f[:-4].split('-', 1)[1] not in pals:
            continue
        a = np.asarray(Image.open(os.path.join(dump, f)).convert('RGBA'))
        mask = a[..., 3] > 0
        if not mask.any():
            continue
        Image.fromarray(fill_transparent(a[..., :3], mask), 'RGB').save(os.path.join(out, f))
        n += 1
    print(f'prepared={n}')


def combine(rgb_dir, alpha_dir, out):
    os.makedirs(out, exist_ok=True)
    n = 0
    for f in os.listdir(rgb_dir):
        ref = os.path.join(alpha_dir, f)
        if not os.path.exists(ref):
            continue
        rgb = Image.open(os.path.join(rgb_dir, f)).convert('RGB')
        alpha = Image.open(ref).getchannel('A')
        if rgb.size != alpha.size:
            rgb = rgb.resize(alpha.size, Image.LANCZOS)
        im = rgb.copy()
        im.putalpha(alpha)
        im.save(os.path.join(out, f))
        n += 1
    print(f'combined={n}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['prep', 'combine'])
    ap.add_argument('--dump')
    ap.add_argument('--pal')
    ap.add_argument('--rgb')
    ap.add_argument('--alpha')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    if args.mode == 'prep':
        prep(args.dump, set(args.pal.split(',')), args.out)
    else:
        combine(args.rgb, args.alpha, args.out)


if __name__ == '__main__':
    main()
