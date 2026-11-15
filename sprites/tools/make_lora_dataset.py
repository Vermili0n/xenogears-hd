"""Build a small LoRA dataset (kohya format: <repeats>_<token>/img.png + img.txt) from approved reference art."""
import argparse
import os

from PIL import Image, ImageOps

BASE = ('{tok}, 1boy, solo, long hair, dark brown hair, ponytail, red hair bead, tan skin, brown eyes, '
        'white sleeveless shirt, blue trim, blue shoulder bands, blue wristbands, brown belt, straps, '
        'dark green baggy pants, brown boots, simple background, grey background, '
        '90s anime style, clean lineart, cel shading')


def pad_square(im, bg=(214, 214, 214)):
    s = max(im.size)
    out = Image.new('RGB', (s, s), bg)
    out.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True, help='folder with chatgpt_face.png, ref_front/side/back.png')
    ap.add_argument('--out', required=True)
    ap.add_argument('--token', default='feifong')
    ap.add_argument('--repeats', type=int, default=10)
    a = ap.parse_args()
    d = os.path.join(a.out, f'{a.repeats}_{a.token}')
    os.makedirs(d, exist_ok=True)
    items = []
    face = Image.open(os.path.join(a.src, 'chatgpt_face.png')).convert('RGB')
    items.append((face, 'portrait, upper body, looking at viewer, front view, facing viewer'))
    views = {'front': 'full body, standing, front view, facing viewer, arms at sides',
             'side': 'full body, standing, from side, profile',
             'back': 'full body, standing, from behind, back view'}
    for v, tags in views.items():
        im = Image.open(os.path.join(a.src, f'ref_{v}.png')).convert('RGB')
        items.append((im, tags))
        items.append((ImageOps.mirror(im), tags))
        # head and upper body close-ups
        w, h = im.size
        head = im.crop((0, 0, w, int(h * 0.28)))
        upper = im.crop((0, 0, w, int(h * 0.55)))
        hv = {'front': 'face, close-up, front view, looking at viewer', 'side': 'face, close-up, profile',
              'back': 'head, close-up, from behind'}[v]
        items.append((head, hv))
        items.append((upper, 'upper body, ' + tags.replace('full body, ', '')))
    for i, (im, tags) in enumerate(items):
        sq = pad_square(im).resize((768, 768), Image.LANCZOS)
        name = f'{a.token}_{i:02d}'
        sq.save(os.path.join(d, name + '.png'))
        with open(os.path.join(d, name + '.txt'), 'w', encoding='utf-8') as f:
            f.write(BASE.format(tok=a.token) + ', ' + tags)
    print(f'{len(items)} images -> {d}')


if __name__ == '__main__':
    main()
