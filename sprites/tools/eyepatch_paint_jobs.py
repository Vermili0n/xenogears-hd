"""Eyepatch, second way (03.11): the sprite's dark block merges the open eye, the band and the patch, so with a blind mask the model
chose where the eye goes (moved, mirrored, invented). Here the patch (and the eye, where the base has none) is painted roughly by hand
on the current head close-up at the place read off the sprite, then the LoRA only refines it: masked repaint at strength < 1
(pod/repaint_pod.py). Texels the sprite has but the base render left as background are filled too.

  python eyepatch_paint_jobs.py        folder ai/redraw/eyepatch4: base (painted), mask, control, boards, jobs_r3.json, preview
"""
import json
import os
import shutil
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402

R4 = os.path.join(ROOT, 'ai', 'redraw', 'eyepatch4')
PROD = os.path.join(ROOT, 'ai', 'prod')
RES = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod', 'v4')
CAP = 'close-up of the head: redraw this pixel-art sprite as a clean 90s anime illustration of the character shown in the second image, same pose and silhouette, flat magenta background'
PATCH = ', he wears a black eyepatch over one eye exactly where the sprite shows the dark patch'
EYE = PATCH + ', his open eye is blue'
NO_EYE = ', a black eyepatch covers his eye, the eye is not visible'
NEG = 'goggles, visor, sunglasses, mask, both eyes covered, red eyes, green eyes, brown eyes'
NEG_NO_EYE = 'eye, eyes, iris, goggles, visor, sunglasses, mask'
META = json.load(open(os.path.join(PROD, 'meta.json')))
GROW = 17


def ell(c, a, ang=0):
    return np.array(cv2.ellipse2Poly(c, a, ang, 0, 360, 12), np.int32)


def poly(*pts):
    return np.array(pts, np.int32)


# patch: polygon in canvas px, skin: polygons repainted as skin first (goggles in the base), skin_at: where to take the skin colour,
# hair: polygons repainted as hair, strap: polygons repainted as the strap, eye: (x, y, rx, ry) of an eye to paint, lines: thin dark lines
# All places are read off the sprite: canvas = (col - head x) * 16, (row - head y) * 16.
TURNED = dict(hint=NO_EYE, neg=NEG_NO_EYE)
FRAMES = {
    # the head is turned away: the sprite shows hair over the near side of the face and only a narrow bar at the far edge
    'h_bart__430_0_065': dict(TURNED, hair=[poly((218, 150), (258, 146), (258, 198), (238, 206), (220, 194))], hair_at=(225, 100),
                              lines=[((230, 150), (240, 204)), ((246, 148), (252, 200))],
                              patch=poly((256, 130), (272, 128), (290, 150), (290, 194), (260, 196), (254, 150))),
    'h_bart__2356_0_047': dict(TURNED, hair=[poly((250, 150), (290, 146), (290, 198), (270, 206), (252, 194))], hair_at=(255, 100),
                               lines=[((262, 150), (272, 204)), ((278, 148), (284, 200))],
                               patch=poly((288, 130), (304, 128), (322, 150), (322, 194), (292, 196), (286, 150))),
    'h_bart__2356_0_048': dict(TURNED, hair=[poly((256, 122), (290, 118), (290, 196), (270, 204), (256, 190))], hair_at=(255, 100),
                               lines=[((266, 124), (274, 200)), ((280, 120), (284, 198))],
                               patch=poly((288, 130), (304, 128), (322, 150), (322, 194), (292, 196), (286, 150))),
    'c_bart_70a4dc__npc_033': dict(TURNED, hair=[poly((250, 150), (290, 146), (290, 198), (270, 206), (252, 194))], hair_at=(255, 100),
                                   lines=[((262, 150), (272, 204)), ((278, 148), (284, 200))],
                                   patch=poly((288, 130), (304, 128), (322, 150), (322, 194), (292, 196), (286, 150))),
    # the same idea: goggles in the base, a block at the far edge on the sprite
    'h_bart__2354_0_024': dict(TURNED, hair=[poly((212, 150), (272, 146), (272, 205), (240, 218), (215, 205))], hair_at=(230, 100),
                               lines=[((232, 152), (240, 214)), ((254, 148), (258, 208))],
                               patch=poly((272, 148), (318, 146), (322, 222), (296, 228), (274, 206))),
    'h_bart__2354_0_025': dict(TURNED, hair=[poly((218, 158), (258, 150), (258, 206), (235, 224), (220, 206))], hair_at=(230, 100),
                               lines=[((232, 160), (238, 220)), ((248, 154), (250, 212))],
                               patch=poly((256, 158), (304, 152), (306, 205), (290, 226), (262, 216), (254, 190))),
    'h_bart__2354_0_026': dict(TURNED, skin=[ell((285, 205), (18, 16))], skin_at=(290, 250),
                               hair=[poly((222, 150), (272, 146), (272, 192), (250, 215), (225, 205))], hair_at=(235, 100),
                               lines=[((238, 152), (244, 210)), ((258, 148), (260, 200))],
                               patch=poly((272, 146), (322, 140), (326, 195), (318, 232), (302, 226), (298, 195), (272, 190))),
    'h_bart__2354_0_027': dict(skin=[ell((262, 208), (30, 26))], skin_at=(265, 255), strap=[poly((238, 172), (274, 160), (274, 184), (240, 196))],
                               eye=(248, 208, 12, 9), patch=poly((272, 160), (318, 156), (322, 205), (306, 228), (280, 226), (272, 200)), hint=EYE),
    'h_bart__430_0_196': dict(skin=[ell((358, 196), (36, 30)), ell((406, 205), (30, 22))], skin_at=(395, 245),
                              strap=[poly((331, 150), (386, 136), (388, 160), (336, 176))], eye=(372, 206, 13, 10),
                              patch=poly((386, 136), (432, 134), (436, 172), (424, 206), (396, 208), (386, 180)), hint=EYE),
    # the base draws a front view, the sprite is turned to the right: the whole lower face again
    'h_bart__2354_0_028': dict(skin=[ell((250, 228), (62, 62))], skin_at=(245, 285),
                               hair=[poly((165, 140), (222, 150), (226, 225), (205, 255), (178, 262), (165, 235))], hair_at=(230, 110),
                               eye=(234, 208, 13, 10), patch=poly((244, 158), (308, 158), (314, 196), (302, 228), (274, 230), (256, 202), (244, 190)),
                               lines=[((248, 268), (282, 266)), ((268, 238), (262, 248))], hint=EYE),
}


def paint_patch(a, pl):
    """Flat dark shape with a lighter upper edge and a black outline: only a guide for the model."""
    m = np.zeros(a.shape[:2], np.uint8)
    cv2.fillPoly(m, [pl], 255, lineType=cv2.LINE_AA)
    ys = np.nonzero(m.any(axis=1))[0]
    t = np.clip((np.arange(a.shape[0]) - ys[0]) / max(1, ys[-1] - ys[0]), 0, 1)
    shade = (78 - 34 * t)[:, None, None]
    fill = np.concatenate([shade, shade, shade + 4], axis=2) * np.ones(a.shape)
    k = (m[..., None] / 255.0)
    a[:] = (a * (1 - k) + fill * k).round().astype(np.uint8)
    cv2.polylines(a, [pl], True, (20, 20, 24), 4, lineType=cv2.LINE_AA)


def paint_eye(a, c):
    x, y, rx, ry = c
    cv2.ellipse(a, (x, y), (rx, ry), 0, 0, 360, (245, 245, 245), -1, lineType=cv2.LINE_AA)
    cv2.circle(a, (x, y), int(ry * 0.9), (45, 85, 190), -1, lineType=cv2.LINE_AA)
    cv2.circle(a, (x, y), int(ry * 0.45), (15, 20, 50), -1, lineType=cv2.LINE_AA)
    cv2.ellipse(a, (x, y + 1), (rx + 2, ry + 2), 0, 180, 360, (15, 15, 20), 3, lineType=cv2.LINE_AA)


def sprite_mask(rep):
    """Sprite silhouette on the 512 canvas of the head close-up."""
    m = META[rep]
    h = Hero(os.path.join(ROOT, m['hero_dir']))
    nat = np.asarray(h.assemble(h.placements(m['set'], m['frame']))[0])
    hx, hy = m['head']
    out = np.zeros((512, 512), np.uint8)
    for y, x in zip(*np.nonzero(nat[..., 3] > 0)):
        u, v = (x - hx) * 16, (y - hy) * 16
        if -16 < u < 512 and -16 < v < 512:
            out[max(0, v):max(0, v + 16), max(0, u):max(0, u + 16)] = 255
    return out


def fill_background(a, rep):
    """Texels the sprite has but the render left as background: filled from the neighbours. -> their mask"""
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    bg = (r > 170) & (g < 110) & (b > 170)
    hole = (bg & (sprite_mask(rep) > 0)).astype(np.uint8) * 255
    hole = cv2.morphologyEx(hole, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    if hole.any():
        grown = cv2.dilate(hole, np.ones((5, 5), np.uint8))
        a[:] = cv2.inpaint(a[..., ::-1].copy(), grown, 5, cv2.INPAINT_TELEA)[..., ::-1]
    return hole


def main():
    for d in ('base', 'mask', 'control', 'boards', 'preview'):
        os.makedirs(os.path.join(R4, d), exist_ok=True)
    jobs_all = {j['name']: j for j in json.load(open(os.path.join(PROD, 'jobs_v4.json')))}
    jobs = []
    for rep, f in FRAMES.items():
        n = rep + '__head'
        j = jobs_all[n]
        a = np.array(Image.open(os.path.join(RES, n + '.png')).convert('RGB'))
        mask = np.zeros(a.shape[:2], np.uint8)
        hole = fill_background(a, rep)
        print(rep, 'background texels filled, px:', int((hole > 0).sum()))
        mask |= hole
        if 'skin' in f:
            sk = tuple(int(v) for v in a[f['skin_at'][1], f['skin_at'][0]])
            for pl in f['skin']:
                cv2.fillPoly(a, [pl], sk, lineType=cv2.LINE_AA)
                cv2.fillPoly(mask, [pl], 255)
        if 'hair' in f:
            hr = tuple(int(v) for v in a[f['hair_at'][1], f['hair_at'][0]])
            for pl in f['hair']:
                cv2.fillPoly(a, [pl], hr, lineType=cv2.LINE_AA)
                cv2.fillPoly(mask, [pl], 255)
        for pl in f.get('strap', []):
            cv2.fillPoly(a, [pl], (55, 55, 60), lineType=cv2.LINE_AA)
            cv2.fillPoly(mask, [pl], 255)
        for p0, p1 in f.get('lines', []):
            cv2.line(a, p0, p1, (60, 30, 25), 3, lineType=cv2.LINE_AA)
        if 'eye' in f:
            paint_eye(a, f['eye'])
            cv2.circle(mask, f['eye'][:2], f['eye'][2] + 8, 255, -1)
        paint_patch(a, f['patch'])
        cv2.fillPoly(mask, [f['patch']], 255)
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (GROW, GROW)))
        Image.fromarray(a).save(os.path.join(R4, 'base', n + '.png'))
        Image.fromarray(mask).save(os.path.join(R4, 'mask', n + '.png'))
        shutil.copyfile(os.path.join(PROD, j['control']), os.path.join(R4, j['control']))
        shutil.copyfile(os.path.join(PROD, j['ref']), os.path.join(R4, j['ref']))
        jobs.append({'name': n, 'control': j['control'], 'ref': j['ref'], 'prompt': CAP + f.get('hint', PATCH),
                     'neg': f.get('neg', NEG), 'base': f'base/{n}.png', 'mask': f'mask/{n}.png'})
        b = a.copy()
        cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(b, cs, -1, (0, 255, 255), 2)
        c = np.array(Image.open(os.path.join(PROD, j['control'])).convert('RGB'))
        Image.fromarray(np.hstack([c, b])).save(os.path.join(R4, 'preview', rep + '.png'))
    json.dump(jobs, open(os.path.join(R4, 'jobs_r3.json'), 'w'), indent=1)
    print(len(jobs), 'jobs')


if __name__ == '__main__':
    main()
