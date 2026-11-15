"""Suggest which NPC sprite set (and which pack portrait) belongs to a character, from its art.

  python npc_match.py --char alice [--top 5]
Reads for_chatgpt/<char>/1_portrait.png. Palette = weighted k-means colors of the figure (light flat background removed).
NPC sets: palette over all frames of extracted/npc_all/<id> (+ npc_all_d2). Score = palette distance in Lab (lower = closer).
Writes for_chatgpt/<char>/sprite_candidates.png (numbered) and candidates.json.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402

CACHE = os.path.join(ROOT, 'ai', 'npc_palettes.json')
PACK = r'<RETROARCH_DRIVE>/RetroArch/system/Xenogears (USA)-texture-replacements'


def palette(rgb, mask, k=6):
    px = rgb[mask].reshape(-1, 3).astype(np.float32)
    if len(px) < k:
        return None
    if len(px) > 20000:
        px = px[np.random.default_rng(0).choice(len(px), 20000, replace=False)]
    lab = cv2.cvtColor(px.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    _, lab_l, cent = cv2.kmeans(lab, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1.0), 3, cv2.KMEANS_PP_CENTERS)
    w = np.bincount(lab_l.ravel(), minlength=k) / len(lab_l)
    return [(c.tolist(), float(x)) for c, x in zip(cent, w)]


def dist(p, q):
    """Symmetric weighted nearest-center distance between two palettes."""
    def one(a, b):
        return sum(w * min(np.linalg.norm(np.array(c) - np.array(d)) for d, _ in b) for c, w in a)
    return 0.5 * (one(p, q) + one(q, p))


FACES_EXCLUDE = {13, 15, 17, 18, 19, 20, 21, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 36, 37, 40, 43, 44, 45, 46, 47, 49, 50,
                 51, 52, 58, 61, 62, 66, 67, 68}  # textures in portraits_idx.json, not faces


def first_frame(h):
    for fi in range(len(h.layout['npc']['frames'])):
        if h.layout['npc']['frames'][fi]:
            return fi
    return 0


def art_mask(rgb):
    """Figure = not the flat light background (estimated from the border)."""
    b = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]).astype(int)
    bg = np.median(b, 0)
    m = np.abs(rgb.astype(int) - bg).sum(2) > 60
    return cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0


def npc_palettes():
    if os.path.exists(CACHE):
        return json.load(open(CACHE))
    out = {}
    for root in ('npc_all', 'npc_all_d2'):
        base = os.path.join(ROOT, 'extracted', root)
        if not os.path.isdir(base):
            continue
        for nid in sorted(os.listdir(base)):
            d = os.path.join(base, nid)
            if nid in out or not os.path.isdir(d):
                continue
            h = Hero(d)
            ims = []
            for fi in range(0, len(h.layout['npc']['frames']), 4):
                try:
                    ims.append(np.asarray(h.assemble(h.placements('npc', fi))[0]))
                except Exception:
                    pass
            if not ims:
                continue
            px = np.concatenate([a[a[..., 3] > 0][:, :3] for a in ims])
            if len(px) < 50:
                continue
            hp = []
            for a in ims:
                ys = np.nonzero((a[..., 3] > 0).any(1))[0]
                if len(ys):
                    t = a[ys.min():ys.min() + max(1, (ys.max() - ys.min()) // 4)]
                    hp.append(t[t[..., 3] > 0][:, :3])
            hp = np.concatenate(hp) if hp else px
            p = palette(px.reshape(-1, 1, 3), np.ones((len(px), 1), bool))
            ph = palette(hp.reshape(-1, 1, 3), np.ones((len(hp), 1), bool), k=3) if len(hp) >= 3 else p
            if p:
                out[nid] = {'pal': p, 'hair': ph or p, 'root': root}
    json.dump(out, open(CACHE, 'w'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', required=True)
    ap.add_argument('--top', type=int, default=8)
    a = ap.parse_args()
    d = os.path.join(ROOT, 'for_chatgpt', a.char)
    art = np.asarray(Image.open(os.path.join(d, '1_portrait.png')).convert('RGB'))
    am = art_mask(art)
    pa = palette(art, am)
    ys = np.nonzero(am.any(1))[0]
    top = am.copy()
    top[ys.min() + (ys.max() - ys.min()) // 3:] = False
    ph = palette(art, top, k=3) or pa
    pals = npc_palettes()
    ranked = sorted(pals, key=lambda n: 0.5 * dist(pa, pals[n]['pal']) + 0.5 * dist(ph, pals[n].get('hair', pals[n]['pal'])))[:a.top]
    # pack portraits
    names = json.load(open(os.path.join(ROOT, 'work', 'portraits_idx.json')))
    pp = []
    for i, n in enumerate(names):
        if i in FACES_EXCLUDE:
            continue
        f = os.path.join(PACK, n + '.png')
        if os.path.exists(f):
            im = np.asarray(Image.open(f).convert('RGB').resize((128, 128)))
            p = palette(im, art_mask(im))
            if p:
                pp.append((dist(pa, p), i))
    pp.sort()
    json.dump({'sprites': ranked, 'portraits': [i for _, i in pp[:3]]}, open(os.path.join(d, 'candidates.json'), 'w'), indent=1)
    gp = os.path.join(ROOT, 'for_chatgpt', '_npc_gallery.json')
    gal = {v: k for k, v in json.load(open(gp)).items()} if os.path.exists(gp) else {}
    S = 150
    sheet = Image.new('RGB', ((a.top + 3) * S, S + 40), (60, 60, 60))
    dr = ImageDraw.Draw(sheet)
    font = ImageFont.truetype('arial.ttf', 16)
    for k, nid in enumerate(ranked):
        h = Hero(os.path.join(ROOT, 'extracted', pals[nid]['root'], nid))
        im, _ = h.assemble(h.placements('npc', first_frame(h)))
        sc = min((S - 8) / im.width, (S - 8) / im.height, 4)
        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.NEAREST)
        bg = Image.new('RGBA', im.size, (60, 60, 60, 255))
        bg.alpha_composite(im)
        sheet.paste(bg.convert('RGB'), (k * S + (S - im.width) // 2, 30 + (S - im.height) // 2))
        dr.text((k * S + 4, 4), f'№ {gal.get(nid, "?")}', fill=(255, 255, 0), font=font)
    for k, (_, i) in enumerate(pp[:3]):
        im = Image.open(os.path.join(PACK, names[i] + '.png')).convert('RGB').resize((S - 8, S - 8))
        x = (a.top + k) * S
        sheet.paste(im, (x + 4, 30))
        dr.text((x + 4, 4), f'портрет {i}', fill=(0, 220, 255), font=font)
    sheet.save(os.path.join(d, 'sprite_candidates.png'))
    print(a.char, 'sprites', ranked, 'portraits', [i for _, i in pp[:3]])


if __name__ == '__main__':
    main()
