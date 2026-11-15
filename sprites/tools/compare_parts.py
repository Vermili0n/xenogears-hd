"""Side-by-side preview: original part (nearest 4x) vs upscaled part, on gray."""
import argparse
import os

from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump', required=True)
    ap.add_argument('--hd', nargs='+', required=True, help='one or more upscaled dirs (columns)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--n', type=int, default=12)
    ap.add_argument('--pal', default='')
    args = ap.parse_args()
    names = [f for f in os.listdir(args.hd[0]) if not args.pal or args.pal in f]
    names.sort(key=lambda f: -(Image.open(os.path.join(args.dump, f)).size[0] * Image.open(os.path.join(args.dump, f)).size[1]))
    names = names[:args.n]
    cols = 1 + len(args.hd)
    cell = 140
    sheet = Image.new('RGBA', (cols * cell * 2, (len(names) + 1) // 2 * cell), (90, 90, 90, 255))
    for i, f in enumerate(names):
        ox = (i % 2) * cols * cell
        oy = (i // 2) * cell
        src = Image.open(os.path.join(args.dump, f)).convert('RGBA')
        imgs = [src.resize((src.width * 4, src.height * 4), Image.NEAREST)]
        imgs += [Image.open(os.path.join(d, f)).convert('RGBA') for d in args.hd]
        for j, im in enumerate(imgs):
            im = im.copy()
            a = im.getchannel('A').point(lambda v: 255 if v > 0 else 0)
            im.putalpha(a)
            scale = min((cell - 8) / im.width, (cell - 8) / im.height, 1.5)
            im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.NEAREST)
            sheet.alpha_composite(im, (ox + j * cell + 4, oy + 4))
    sheet.save(args.out)


if __name__ == '__main__':
    main()
