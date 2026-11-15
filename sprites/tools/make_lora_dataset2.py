"""Build the LoRA dataset from reference sheets: auto-crop figures (connected components) or grid cells,
caption each crop, add mirrored copies. Manifest = list of (file, mode, [captions left-to-right/top-to-bottom])."""
import argparse
import os

import numpy as np
from PIL import Image, ImageOps

BASE = ('{tok}, 1boy, solo, long hair, dark brown hair, ponytail, red hair bead, tan skin, brown eyes, '
        'white sleeveless shirt, blue trim, blue shoulder bands, blue wristbands, brown belt, straps, '
        'dark green baggy pants, brown boots, simple background, grey background, '
        '90s anime style, clean lineart, cel shading')

MANIFEST = [
    ('chatgpt_face.png', 'whole', ['portrait, upper body, looking at viewer, front view, facing viewer']),
    ('chatgpt_sheet.png', 'figures', ['full body, standing, front view, facing viewer, arms at sides',
                                      'full body, standing, from side, profile',
                                      'full body, standing, from behind, back view']),
    ('Без имени.png', 'figures', ['full body, standing, three-quarter view',
                                  'full body, standing, from behind, three-quarter back view']),
    ('run.png', 'cols3', ['full body, walking, front view, facing viewer',
                            'full body, walking, from side, profile',
                            'full body, running, from side, profile, hair flowing']),
    ('fight.png', 'figures', ['full body, fighting stance, front view, fists, martial arts',
                              'full body, fighting stance, three-quarter view, martial arts',
                              'full body, high kick, from side, martial arts']),
    ('emotions.png', 'grid3x2', ['portrait, front view, looking at viewer, serious',
                                 'portrait, front view, looking at viewer, smile',
                                 'portrait, three-quarter view, angry, shouting, open mouth',
                                 'portrait, three-quarter view, looking to the side',
                                 'portrait, profile, side view',
                                 'portrait, looking down, sad']),
    ('full-body.png', 'figures', ['full body, jumping, midair, dynamic pose',
                                  'full body, crouching, hand on ground',
                                  'full body, sitting on ground, one knee up']),
]


def label(mask):
    """8-connected labelling of a small boolean mask -> (labels, {id: pixel count})."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    sizes, cur = {}, 0
    for y in range(h):
        for x in range(w):
            if mask[y, x] and not lab[y, x]:
                cur += 1
                stack, n = [(y, x)], 0
                lab[y, x] = cur
                while stack:
                    cy, cx = stack.pop()
                    n += 1
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                                lab[ny, nx] = cur
                                stack.append((ny, nx))
                sizes[cur] = n
    return lab, sizes


def isolate(im, small_mask, k, bg, pad=6):
    """Crop the figure given by small_mask (downscaled by k); pixels of other figures become background."""
    m = small_mask.copy()
    for _ in range(2):  # dilate a little so anti-aliased edges survive
        m[1:] |= m[:-1]; m[:-1] |= m[1:]; m[:, 1:] |= m[:, :-1]; m[:, :-1] |= m[:, 1:]
    full = np.kron(m, np.ones((k, k), bool))[:im.height, :im.width]
    a = np.asarray(im).copy()
    a[~full] = bg
    ys, xs = np.where(small_mask)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    return Image.fromarray(a).crop((max(0, (x0 - pad) * k), max(0, (y0 - pad) * k),
                                    min(im.width, (x1 + pad) * k), min(im.height, (y1 + pad) * k)))


def crops(im, mode, n):
    if mode == 'whole':
        return [im]
    if mode == 'grid3x2':
        w, h = im.width // 3, im.height // 2
        return [im.crop(((i % 3) * w, (i // 3) * h, (i % 3 + 1) * w, (i // 3 + 1) * h)) for i in range(6)]
    a = np.asarray(im).astype(int)
    bg = np.median(np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3)]), axis=0)
    k = 4
    small = (np.abs(a - bg).sum(-1) > 45)[::k, ::k]
    lab, sizes = label(small)
    bgc = tuple(int(v) for v in bg)
    if mode == 'cols3':
        # touching figures: split into vertical thirds, keep the biggest blob inside each third
        out, w3 = [], small.shape[1] // 3
        for c in range(3):
            stripe = np.zeros_like(small)
            stripe[:, c * w3:(c + 1) * w3] = small[:, c * w3:(c + 1) * w3]
            sl, ss = label(stripe)
            big = max(ss, key=ss.get)
            out.append(isolate(im, sl == big, k, bgc))
        return out
    ids = sorted(sizes, key=sizes.get, reverse=True)[:n]
    ids = sorted(ids, key=lambda i: np.where(lab == i)[1].mean())
    return [isolate(im, lab == i, k, bgc) for i in ids]

def pad_square(im, bg=(214, 214, 214)):
    s = max(im.size)
    out = Image.new('RGB', (s, s), bg)
    out.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--token', default='feifong')
    ap.add_argument('--repeats', type=int, default=4)
    ap.add_argument('--size', type=int, default=768)
    a = ap.parse_args()
    d = os.path.join(a.out, f'{a.repeats}_{a.token}')
    os.makedirs(d, exist_ok=True)
    i = 0
    for fname, mode, caps in MANIFEST:
        im = Image.open(os.path.join(a.src, fname)).convert('RGB')
        cs = crops(im, mode, len(caps))
        if len(cs) != len(caps):
            print(f'WARNING {fname}: {len(cs)} crops for {len(caps)} captions')
        for c, cap in zip(cs, caps):
            for mirror in (False, True):
                img = ImageOps.mirror(c) if mirror else c
                pad_square(img).resize((a.size, a.size), Image.LANCZOS).save(os.path.join(d, f'{a.token}_{i:03d}.png'))
                with open(os.path.join(d, f'{a.token}_{i:03d}.txt'), 'w', encoding='utf-8') as f:
                    f.write(BASE.format(tok=a.token) + ', ' + cap)
                i += 1
    print(f'{i} images -> {d}')


if __name__ == '__main__':
    main()
