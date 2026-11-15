"""Training pairs for a local student model from the model redraws we already have (pixel-aligned by construction).

  python make_pairs.py --out ai/pairs [--size 512]
For every accepted redraw (Fei: ai/fei_prod/work; NPC keyframes: ai/npc_<id>_prod/work minus ebsynth fills):
  control/<name>.png  = xBR-smoothed sprite at 8x on magenta, bottom-centred in a size x size cell (as sent to Gemini)
  target/<name>.png   = the redraw, same placement, original silhouette, magenta outside
  target/<name>.txt   = caption
Writes split.json (train / held-out by whole animation set).
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402

MAG = (255, 0, 255)
CAP_FEI = 'redraw this pixel-art sprite as a clean 90s anime illustration of Fei, same pose and silhouette, flat magenta background'
CAP_NPC = 'redraw this pixel-art sprite as a clean 90s anime illustration, same pose, colors and silhouette, flat magenta background'


def place(img, size, feet):
    c = Image.new('RGB', (size, size), MAG)
    if img.height > feet or img.width > size:
        k = min(feet / img.height, size / img.width)
        img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)
    c.paste(img, ((size - img.width) // 2, feet - img.height), img)
    return c


def pair(hobj, setkey, fi, red_path, size, feet):
    o = frame_rgba(hobj, setkey, fi)                      # 8x, alpha 0/255
    red = Image.open(red_path).convert('RGB').resize(o.size, Image.LANCZOS)
    t = np.dstack([np.asarray(red), np.asarray(o)[..., 3]])
    return place(o, size, feet), place(Image.fromarray(t, 'RGBA'), size, feet)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'ai', 'pairs'))
    ap.add_argument('--size', type=int, default=512)
    ap.add_argument('--holdout', default='2397_0,2988_0,npc:034734b5f7', help='sets kept out of training')
    a = ap.parse_args()
    feet = a.size - 12
    for d in ('control', 'target'):
        os.makedirs(os.path.join(a.out, d), exist_ok=True)
    hold = set(a.holdout.split(','))
    split = {'train': [], 'test': []}
    # Fei
    fei = Hero(os.path.join(ROOT, 'extracted', 'disc1_full', 'fei'))
    w = os.path.join(ROOT, 'ai', 'fei_prod', 'work')
    for f in sorted(os.listdir(w)):
        if not f.endswith('_red.png'):
            continue
        s1, s2, fi = f.split('_')[:3]
        setkey, fi = f'{s1}_{s2}', int(fi)
        name = f'fei_{setkey}_{fi:03d}'
        c, t = pair(fei, setkey, fi, os.path.join(w, f), a.size, feet)
        c.save(os.path.join(a.out, 'control', name + '.png'))
        t.save(os.path.join(a.out, 'target', name + '.png'))
        open(os.path.join(a.out, 'target', name + '.txt'), 'w').write(CAP_FEI)
        split['test' if setkey in hold else 'train'].append(name)
    # NPC keyframes (model redraws only)
    for d in sorted(os.listdir(os.path.join(ROOT, 'ai'))):
        if not (d.startswith('npc_') and d.endswith('_prod')):
            continue
        nid = d[4:-5]
        hd = os.path.join(ROOT, 'extracted', 'npc', nid)
        w = os.path.join(ROOT, 'ai', d, 'work')
        if not os.path.isdir(hd) or not os.path.isdir(w):
            continue
        fills = set(json.load(open(os.path.join(w, 'fills.json')))) if os.path.exists(os.path.join(w, 'fills.json')) else set()
        h = Hero(hd)
        for f in sorted(os.listdir(w)):
            if not f.endswith('_red.png'):
                continue
            fi = int(f.split('_')[1])
            if str(fi) in fills:
                continue
            name = f'npc_{nid}_{fi:03d}'
            c, t = pair(h, 'npc', fi, os.path.join(w, f), a.size, feet)
            c.save(os.path.join(a.out, 'control', name + '.png'))
            t.save(os.path.join(a.out, 'target', name + '.png'))
            open(os.path.join(a.out, 'target', name + '.txt'), 'w').write(CAP_NPC)
            split['test' if f'npc:{nid}' in hold else 'train'].append(name)
    json.dump(split, open(os.path.join(a.out, 'split.json'), 'w'), indent=1)
    print('train', len(split['train']), 'test', len(split['test']))


if __name__ == '__main__':
    main()
