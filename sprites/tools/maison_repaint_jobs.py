"""Maison without the mustache (03.11): the full re-render with a "clean-shaven" hint put faces on the back views, so only the mustache
of the current head close-ups is repainted. Mustache = bright low-saturation blobs in the lower half of the face, enclosed by skin.
They are erased from the base by inpainting, then the LoRA (new clean-shaven board) refines that area: pod/repaint_pod.py, strength < 1.

  python maison_repaint_jobs.py        folder ai/redraw/maison2: base, mask, control, boards, jobs.json, preview
"""
import json
import os
import shutil

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
R1 = os.path.join(ROOT, 'ai', 'redraw', 'maison')
R2 = os.path.join(ROOT, 'ai', 'redraw', 'maison2')
HINT = ', clean-shaven, a bare upper lip'
NEG = 'mustache, moustache, beard, facial hair, white hair on the lip'


def face_box(a):
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    skin = (r > g + 18) & (g > b + 12) & (r > 120) & (r < 250) & ~((r > 200) & (g < 90))
    skin = ndimage.binary_opening(skin, structure=np.ones((5, 5)))
    lab, n = ndimage.label(skin)
    if not n:
        return None, skin
    sizes = ndimage.sum(skin, lab, range(1, n + 1))
    # the biggest skin blobs of the upper 2/3 of the canvas: the face (hands and arms are below or off to the side)
    keep = np.zeros(skin.shape, bool)
    for i in np.argsort(sizes)[::-1][:3]:
        m = lab == i + 1
        ys = np.nonzero(m.any(axis=1))[0]
        if sizes[i] > 400 and ys[0] < 300:
            keep |= m
    if not keep.any():
        return None, skin
    ys, xs = np.nonzero(keep)
    return (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1), skin


def mustache(a):
    box, skin = face_box(a)
    if box is None:
        return None, None
    x0, y0, x1, y1 = box
    rgb = a.astype(int)
    white = (rgb.min(axis=-1) > 150) & (rgb.max(axis=-1) - rgb.min(axis=-1) < 48)
    lab, n = ndimage.label(white)
    out = np.zeros(white.shape, bool)
    fh = y1 - y0
    for i in range(1, n + 1):
        m = lab == i
        s = int(m.sum())
        if s < 60 or s > 9000:
            continue
        ys, xs = np.nonzero(m)
        if ys.mean() < y0 + 0.5 * fh or ys.mean() > y1 + 6 or xs.mean() < x0 - 4 or xs.mean() > x1 + 4:
            continue
        ring = ndimage.binary_dilation(m, structure=np.ones((3, 3)), iterations=8) & ~m
        if (skin & ring).sum() / max(1, ring.sum()) > 0.3:
            out |= m
    if not out.any():
        return None, box
    # the mustache only: blobs next to the biggest one (lens highlights sit higher, the ear far to the side)
    lab, n = ndimage.label(out)
    sizes = ndimage.sum(out, lab, range(1, n + 1))
    main_blob = int(np.argmax(sizes)) + 1
    cy, cx = ndimage.center_of_mass(lab == main_blob)
    keep = np.zeros(out.shape, bool)
    for i in range(1, n + 1):
        y, x = ndimage.center_of_mass(lab == i)
        if abs(y - cy) < 24 and abs(x - cx) < 70:
            keep |= lab == i
    return keep, box


def main():
    shutil.rmtree(R2, ignore_errors=True)
    for d in ('base', 'mask', 'control', 'boards', 'preview'):
        os.makedirs(os.path.join(R2, d), exist_ok=True)
    jobs1 = json.load(open(os.path.join(R1, 'jobs.json')))
    fmap = json.load(open(os.path.join(R1, 'map.json')))
    heads = [j for j in jobs1 if j['name'].endswith('__head')]
    jobs, none = [], []
    for j in heads:
        n = j['name']
        a = np.array(Image.open(os.path.join(R1, 'before', n + '.png')).convert('RGB'))
        m, box = mustache(a)
        if m is None:
            none.append(n)
            continue
        mask = cv2.dilate(m.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
        base = cv2.inpaint(a[..., ::-1].copy(), mask, 7, cv2.INPAINT_TELEA)[..., ::-1]
        grown = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
        Image.fromarray(base).save(os.path.join(R2, 'base', n + '.png'))
        Image.fromarray(grown).save(os.path.join(R2, 'mask', n + '.png'))
        shutil.copyfile(os.path.join(R1, j['control']), os.path.join(R2, j['control']))
        shutil.copyfile(os.path.join(R1, j['ref']), os.path.join(R2, j['ref']))
        jobs.append({'name': n, 'control': j['control'], 'ref': j['ref'], 'prompt': j['prompt'].split(', clean-shaven')[0] + HINT, 'neg': NEG,
                     'base': f'base/{n}.png', 'mask': f'mask/{n}.png'})
        b = a.copy()
        cs, _ = cv2.findContours(grown, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(b, cs, -1, (0, 255, 255), 2)
        Image.fromarray(b).save(os.path.join(R2, 'preview', n + '.png'))
    json.dump(jobs, open(os.path.join(R2, 'jobs.json'), 'w'), indent=1)
    json.dump({'with': [j['name'] for j in jobs], 'without': none}, open(os.path.join(R2, 'found.json'), 'w'), indent=1)
    print(len(heads), 'heads,', len(jobs), 'with a mustache,', len(none), 'without')
    # contact sheet of all heads: mask outline, or just the head when nothing was found
    names = [j['name'] for j in heads]
    W, cw, ch = 1980, 165, 150
    cols = W // cw
    s = Image.new('RGB', (W, (len(names) // cols + 1) * (ch + 14)), (60, 60, 60))
    d = ImageDraw.Draw(s)
    for i, n in enumerate(names):
        p = os.path.join(R2, 'preview', n + '.png')
        found = os.path.exists(p)
        im = Image.open(p if found else os.path.join(R1, 'before', n + '.png')).convert('RGB').crop((96, 20, 416, 310)).resize((cw - 4, ch), Image.LANCZOS)
        x, y = (i % cols) * cw, (i // cols) * (ch + 14)
        s.paste(im, (x, y + 12))
        d.text((x + 2, y), n.replace('c_maison_', '').replace('__head', '').replace('__npc', ''), fill=(0, 255, 0) if found else (255, 160, 160))
    s.save(os.path.join(R2, 'contact.png'))
    print(s.size)


if __name__ == '__main__':
    main()
