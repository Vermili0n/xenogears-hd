"""Crop the same region (Fei + neighbour NPC) from every variant screenshot into one labelled sheet."""
import argparse
import glob
import os

from PIL import Image, ImageDraw, ImageFont

LABELS = {
    '1_original': 'Оригинал',
    '2_emu_xbr': 'Фильтр эмулятора xBR',
    '2b_emu_adaptive': 'Adaptive Smoothing',
    '3_parts_xbr': 'Куски: xBR',
    '4_parts_hqx': 'Куски: hqx',
    '5_parts_esrgan_anime': 'Куски: Real-ESRGAN anime',
    '5b_parts_esrgan_animevideo': 'Куски: Real-ESRGAN animevideo',
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--box', default='575,430,900,710')
    ap.add_argument('--zoom', type=float, default=1.6)
    ap.add_argument('--cols', type=int, default=4)
    ap.add_argument('--pick', default='last', choices=['first', 'last'])
    args = ap.parse_args()
    box = tuple(int(v) for v in args.box.split(','))
    cw, ch = int((box[2] - box[0]) * args.zoom), int((box[3] - box[1]) * args.zoom)
    names = [n for n in LABELS if os.path.isdir(os.path.join(args.root, n))]
    rows = (len(names) + args.cols - 1) // args.cols
    head = 34
    sheet = Image.new('RGB', (args.cols * cw, rows * (ch + head)), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype('arial.ttf', 22)
    except OSError:
        font = ImageFont.load_default()
    for i, n in enumerate(names):
        shots = sorted(glob.glob(os.path.join(args.root, n, '*.png')))
        if not shots:
            continue
        im = Image.open(shots[-1] if args.pick == 'last' else shots[0]).convert('RGB').crop(box)
        im = im.resize((cw, ch), Image.LANCZOS)
        x, y = (i % args.cols) * cw, (i // args.cols) * (ch + head)
        sheet.paste(im, (x, y + head))
        draw.text((x + 8, y + 5), f'{i + 1}. {LABELS[n]}', fill=(255, 230, 120), font=font)
    sheet.save(args.out)


if __name__ == '__main__':
    main()
