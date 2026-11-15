"""One collage per character for ChatGPT (art + in-game portrait + sprite + style references), labelled A..E.

  python gpt_collage.py [--slug alice]      -> for_chatgpt/<slug>/collage.png
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'for_chatgpt')
W, H = 1800, 1250
FONT = ImageFont.truetype('arialbd.ttf', 44)


def fit(im, w, h, bg=(255, 255, 255)):
    im = im.convert('RGBA')
    im.thumbnail((w, h), Image.LANCZOS)
    c = Image.new('RGB', (w, h), bg)
    c.paste(im, ((w - im.width) // 2, (h - im.height) // 2), im)
    return c


def collage(slug):
    d = os.path.join(D, slug)
    c = Image.new('RGB', (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(c)
    panels = []
    art = os.path.join(d, '1_portrait.png')
    ing = os.path.join(d, '1b_portrait_ingame.png')
    panels.append(('A', art, (10, 60, 560, 560)))
    if os.path.exists(ing):
        panels.append(('B', ing, (590, 60, 560, 560)))
        panels.append(('C', os.path.join(d, '2_sprite_front_side_back.png'), (1170, 60, 620, 560)))
    else:
        panels.append(('C', os.path.join(d, '2_sprite_front_side_back.png'), (590, 60, 1200, 560)))
    panels.append(('D', os.path.join(D, 'fei', 'chatgpt_sheet.png'), (10, 690, 1170, 550)))
    panels.append(('E', os.path.join(D, 'fei', 'chatgpt_face.png'), (1200, 690, 590, 550)))
    for lab, path, (x, y, w, h) in panels:
        c.paste(fit(Image.open(path), w, h), (x, y))
        dr.rectangle([x - 2, y - 2, x + w + 1, y + h + 1], outline=(0, 0, 0), width=3)
        dr.text((x + 4, y - 54), lab, fill=(220, 0, 0), font=FONT)
    c.save(os.path.join(d, 'collage.png'))
    return os.path.exists(ing)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--slug', default='')
    a = ap.parse_args()
    print(collage(a.slug))


if __name__ == '__main__':
    main()
