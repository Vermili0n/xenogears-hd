"""Review sheet for the user: portrait | per frame: original sprite (pixel) above, AI redraw below."""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--orig-frames', required=True, help='extracted/<hero>/frames dir')
    ap.add_argument('--work', required=True, help='dir with <set>_<frame>_red.png')
    ap.add_argument('--frames', required=True, help='427_0:190,427_0:193,...')
    ap.add_argument('--portrait', required=True)
    ap.add_argument('--title', default='')
    ap.add_argument('--out', required=True)
    ap.add_argument('--h', type=int, default=420)
    args = ap.parse_args()
    H = args.h
    try:
        font = ImageFont.truetype('arial.ttf', 22)
    except OSError:
        font = ImageFont.load_default()
    cols = []
    for tok in args.frames.split(','):
        s, fi = tok.split(':')
        o = Image.open(os.path.join(args.orig_frames, f'{s}_{int(fi):03d}.png')).convert('RGBA')
        r = Image.open(os.path.join(args.work, f'{s}_{int(fi):03d}_red.png')).convert('RGB')
        sc = H / r.height
        r = r.resize((int(r.width * sc), H), Image.LANCZOS)
        k = max(1, int(H * 0.8 / o.height))
        o = o.resize((o.width * k, o.height * k), Image.NEAREST)
        cols.append((tok, o, r))
    p = Image.open(args.portrait).convert('RGB').resize((H, H), Image.LANCZOS)
    W = p.width + 20 + sum(max(o.width, r.width) + 16 for _, o, r in cols)
    sheet = Image.new('RGB', (W, 40 + H * 2 + 20), (60, 60, 60))
    d = ImageDraw.Draw(sheet)
    d.text((10, 8), args.title, fill=(255, 230, 120), font=font)
    sheet.paste(p, (10, 40 + H // 2))
    x = p.width + 30
    for tok, o, r in cols:
        cw = max(o.width, r.width)
        bg = Image.new('RGBA', o.size, (60, 60, 60, 255))
        bg.alpha_composite(o)
        sheet.paste(bg.convert('RGB'), (x + (cw - o.width) // 2, 40 + (H - o.height) // 2))
        sheet.paste(r, (x + (cw - r.width) // 2, 40 + H + 20))
        d.text((x, 40 + H - 26), tok.split(':')[1], fill=(200, 200, 200), font=font)
        x += cw + 16
    sheet.save(args.out)
    print(sheet.size)


if __name__ == '__main__':
    main()
