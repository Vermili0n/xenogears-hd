"""Build the ChatGPT package of a character folder from its art: sprite candidates, front/side/back strip, style refs, prompt.

  python char_package.py --char alice [--npc 57]     (npc = number in _NPC_GALLERY / sprite_candidates, default: best guess)
  python char_package.py --watch                      every 60 s: package every folder that got 1_portrait.png
Heroes (fixed folders with PROMPT.txt already) are left alone.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402

D = os.path.join(ROOT, 'for_chatgpt')
HEROES = {'fei', 'elly', 'bart', 'citan', 'billy', 'rico', 'emeralda', 'chuchu', 'maria'}

PROMPT = """Эталон для ChatGPT: {title}. Лучше в том же чате, где рисовались прошлые эталоны (стиль совпадёт сам).
2_sprite_front_side_back.png — спрайт из игры (определён по скрипту игры: кто говорит репликами этого персонажа).
Результаты сохранить сюда: chatgpt_sheet.png (разворот) и chatgpt_face.png (лицо).

=== Запрос 1: приложить 1_portrait, 2_sprite_front_side_back, 3_style_sheet_fei, 4_style_face_fei ===

Draw a character turnaround sheet of a new character for the same project as the sheets you made before.
Image 1 is official art of this character: it defines the face and hair.
Image 2 is the in-game sprite from the front, the side and the back: it defines the outfit, its colors and the body shape.
Images 3 and 4 are the sheet and face close-up you drew earlier for another character of the same game. Copy their art style exactly: the same 90s anime look, line weight, cel shading, color treatment and level of detail, the same layout and the same plain light grey background.
Layout: three full-body views side by side - front, side (profile) and back. Neutral standing pose, the whole figure visible.
If image 1 and image 2 disagree, image 2 decides the outfit and its colors, image 1 decides the face and hair.
Strong likeness to image 1. Do not add accessories, weapons or text.

=== Запрос 2: в том же чате ===

Now draw a close-up of the face and shoulders, front three-quarter view, in exactly the same style and layout as image 4. Strong likeness to image 1. Plain light grey background, no text.
"""


def views(hero):
    """front / side / back frame of an NPC set: symmetric with skin in the head = front, symmetric without = back."""
    feats = []
    fr = hero.layout['npc']['frames']
    for fi in range(len(fr)):
        try:
            im, _ = hero.assemble(hero.placements('npc', fi))
        except Exception:
            continue
        a = np.asarray(im).astype(int)
        m = a[..., 3] > 0
        if m.sum() < 50:
            continue
        ys, xs = np.nonzero(m)
        m, a = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1], a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        H, W = m.shape
        sym = (m & m[:, ::-1]).sum() / max((m | m[:, ::-1]).sum(), 1)
        head, hm = a[:int(H * 0.3)], m[:int(H * 0.3)]
        r, g, b = head[..., 0], head[..., 1], head[..., 2]
        skin = ((r > 150) & (r > g + 15) & (g > b + 5) & (g > 90) & hm).sum() / max(hm.sum(), 1)
        legs = m[int(H * 0.85):].any(0).sum() / W
        feats.append((fi, sym, skin, legs, H))
    if not feats:
        return [0, 0, 0]
    hmed = np.median([f[4] for f in feats])
    tall = [f for f in feats if f[4] >= hmed * 0.95 and f[3] < 0.75] or feats
    front = max(tall, key=lambda f: f[1] + 2 * f[2])[0]
    back = max(tall, key=lambda f: f[1] - 2 * f[2])[0]
    side = min(tall, key=lambda f: f[1])[0]
    return [front, side, back]


def strip(hero, frames, out):
    ims = [hero.assemble(hero.placements('npc', f))[0] for f in frames]
    H = max(i.height for i in ims)
    c = Image.new('RGBA', (sum(i.width for i in ims) + 10 * (len(ims) + 1), H + 8), (255, 255, 255, 255))
    x = 10
    for i in ims:
        c.alpha_composite(i, (x, H + 4 - i.height))
        x += i.width + 10
    c.convert('RGB').resize((c.width * 8, c.height * 8), Image.NEAREST).save(out)


def package(slug, npc=0):
    d = os.path.join(D, slug)
    sp = os.path.join(d, 'sprite.json')
    fixed = json.load(open(sp)) if os.path.exists(sp) else {}
    if fixed.get('source') and not npc:  # identified from the game's own data (assign_sprites.py): keep it
        nid, root, pick = fixed['npc'], fixed.get('root', 'npc_full'), fixed['source']
    else:
        subprocess.run([sys.executable, os.path.join(HERE, 'npc_match.py'), '--char', slug], check=True, capture_output=True)
        cand = json.load(open(os.path.join(d, 'candidates.json')))
        known = json.load(open(os.path.join(D, '_known_sprites.json'))) if os.path.exists(os.path.join(D, '_known_sprites.json')) else {}
        npc = npc or known.get(slug, 0)  # sprites identified in advance by eye
        nid = json.load(open(os.path.join(D, '_npc_gallery.json')))[str(npc)] if npc else cand['sprites'][0]
        pick = npc or 'auto'
        root = 'npc_all' if os.path.isdir(os.path.join(ROOT, 'extracted', 'npc_all', nid)) else 'npc_all_d2'
    hero = Hero(os.path.join(ROOT, 'extracted', root, nid))
    fr = views(hero)
    strip(hero, fr, os.path.join(d, '2_sprite_front_side_back.png'))
    shutil.copy(os.path.join(D, 'fei', 'chatgpt_sheet.png'), os.path.join(d, '3_style_sheet_fei.png'))
    shutil.copy(os.path.join(D, 'fei', 'chatgpt_face.png'), os.path.join(d, '4_style_face_fei.png'))
    title = open(os.path.join(d, 'WIKI.txt'), encoding='utf-8').readline().strip() if os.path.exists(os.path.join(d, 'WIKI.txt')) else slug
    open(os.path.join(d, 'PROMPT.txt'), 'w', encoding='utf-8').write(PROMPT.format(title=title, slug=slug))
    if not fixed.get('source') or npc:
        json.dump({'npc': nid, 'root': root, 'pick': pick, 'frames': fr}, open(sp, 'w'), indent=1)
    print(slug, 'sprite', nid, 'frames', fr, flush=True)


OURS = {'1_portrait.png', '2_sprite_front_side_back.png', '3_style_sheet_fei.png', '4_style_face_fei.png', 'chatgpt_sheet.png',
        'chatgpt_face.png', 'sprite_candidates.png', '1b_portrait_ingame.png', 'collage.png'}


def adopt_art(d):
    """User drops art under its own name (webp/jpg/png): the largest such image becomes 1_portrait.png."""
    if os.path.exists(os.path.join(d, '1_portrait.png')):
        return False
    imgs = [f for f in os.listdir(d) if f.lower().endswith(('.webp', '.png', '.jpg', '.jpeg', '.gif')) and f not in OURS]
    if not imgs:
        return False
    best = max(imgs, key=lambda f: os.path.getsize(os.path.join(d, f)))
    Image.open(os.path.join(d, best)).convert('RGB').save(os.path.join(d, '1_portrait.png'))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='')
    ap.add_argument('--npc', type=int, default=0)
    ap.add_argument('--watch', action='store_true')
    a = ap.parse_args()
    if a.char:
        package(a.char, a.npc)
        return
    while a.watch:
        for slug in sorted(os.listdir(D)):
            d = os.path.join(D, slug)
            if os.path.isdir(d) and not os.path.exists(os.path.join(d, 'NOSPRITE.txt')):
                try:
                    adopt_art(d)
                except Exception as e:
                    print(slug, 'art not readable', e, flush=True)
            if (slug in HEROES or not os.path.isdir(d) or not os.path.exists(os.path.join(d, '1_portrait.png'))
                    or os.path.exists(os.path.join(d, 'PROMPT.txt')) or any(os.path.exists(os.path.join(d, m)) for m in ('NOSPRITE.txt', 'FEI.txt', 'NOMATCH.txt'))):
                continue
            try:
                package(slug)
            except Exception as e:  # keep watching; report the folder
                print(slug, 'FAILED', e, flush=True)
        subprocess.run([sys.executable, os.path.join(HERE, 'refs_status.py')], capture_output=True)
        time.sleep(60)


if __name__ == '__main__':
    main()
