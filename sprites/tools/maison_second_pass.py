"""Maison, second pass: tips of the mustache left beside the first mask (profile views). White blobs next to the first mask, at its height,
on the repainted heads -> erased from the base -> job for pod/repaint_pod.py. Folder ai/redraw/maison2: jobs2.json, base2/, mask2/.

  python maison_second_pass.py <contact.png>
"""
import json
import os
import shutil
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
R = os.path.join(ROOT, 'ai', 'redraw', 'maison2')
HINT_NEG = 'mustache, moustache, beard, facial hair, white hair on the lip'


def tips(a, old):
    rgb = a.astype(int)
    white = (rgb.min(axis=-1) > 150) & (rgb.max(axis=-1) - rgb.min(axis=-1) < 48)
    ys = np.nonzero(old.any(axis=1))[0]
    near = cv2.dilate(old, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61))) > 0
    lab, n = ndimage.label(white)
    out = np.zeros(white.shape, bool)
    for i in range(1, n + 1):
        m = lab == i
        s = int(m.sum())
        if s < 25 or s > 2500 or not (m & near).any():
            continue
        yy = np.nonzero(m.any(axis=1))[0]
        if yy[0] < ys[0] - 8 or yy[-1] > ys[-1] + 8:
            continue
        out |= m
    return out


def main():
    os.makedirs(os.path.join(R, 'base2'), exist_ok=True)
    os.makedirs(os.path.join(R, 'mask2'), exist_ok=True)
    jobs = json.load(open(os.path.join(R, 'jobs.json')))
    out, cells = [], []
    for j in jobs:
        n = j['name']
        a = np.array(Image.open(os.path.join(R, 'm_7_60', 'v4', n + '.png')).convert('RGB'))
        old = np.asarray(Image.open(os.path.join(R, 'mask', n + '.png')).convert('L'))
        m = tips(a, old)
        if not m.any():
            continue
        mask = cv2.dilate(m.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
        base = cv2.inpaint(a[..., ::-1].copy(), mask, 7, cv2.INPAINT_TELEA)[..., ::-1]
        grown = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
        Image.fromarray(base).save(os.path.join(R, 'base2', n + '.png'))
        Image.fromarray(grown).save(os.path.join(R, 'mask2', n + '.png'))
        out.append(dict(j, base=f'base2/{n}.png', mask=f'mask2/{n}.png', neg=HINT_NEG))
        b = a.copy()
        cs, _ = cv2.findContours(grown, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(b, cs, -1, (0, 255, 255), 2)
        cells.append((n.replace('c_maison_', '').replace('__head', '').replace('__npc', ''), Image.fromarray(b).crop((96, 40, 416, 300)).resize((240, 195), Image.LANCZOS)))
    json.dump(out, open(os.path.join(R, 'jobs2.json'), 'w'), indent=1)
    print(len(out), 'of', len(jobs), 'heads have tips')
    W, cols = 1960, 8
    rows = len(cells) // cols + 1
    s = Image.new('RGB', (W, rows * 212), (60, 60, 60))
    d = ImageDraw.Draw(s)
    for i, (lab, im) in enumerate(cells):
        x, y = (i % cols) * 245, (i // cols) * 212
        d.text((x + 2, y), lab, fill=(255, 255, 0))
        s.paste(im, (x, y + 13))
    s.save(sys.argv[1])
    print(s.size)


if __name__ == '__main__':
    main()
