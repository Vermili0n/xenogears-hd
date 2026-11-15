"""Eyepatch by masked repaint (03.11): the head close-ups in the pack stay as they are, the LoRA redraws only the area of the
sprite's dark patch (pod/repaint_pod.py). Full renders with a hint changed the drawing style of the whole figure.

  python eyepatch_repaint_jobs.py [--only h_bart__430_0_190,...]     folder ai/redraw/eyepatch3: jobs, masks, previews
The frames come from ai/redraw/eyepatch/map.json; base = the current head render (eyepatch/before).
Mask: Bart - dark sprite blobs of the head touching the skin; frames that now wear a visor also get the visor's area of the
base render. Sigurd (his dark hair shadows look like the patch on the sprite) - the patch as drawn by seed 7 of eyepatch.
"""
import argparse
import json
import os
import shutil
import sys

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402

R1 = os.path.join(ROOT, 'ai', 'redraw', 'eyepatch')
R3 = os.path.join(ROOT, 'ai', 'redraw', 'eyepatch3')
META = os.path.join(ROOT, 'ai', 'prod', 'meta.json')
PATCH = np.array([(49, 49, 49), (74, 74, 74), (106, 106, 123)])
SKIN = np.array([(222, 164, 90), (180, 123, 49), (238, 230, 172)])
COAT = np.array([(98, 24, 24), (172, 74, 74), (123, 49, 49)])
HAIR = np.array([(246, 222, 148), (205, 180, 106), (164, 139, 106)])
VISOR = {'h_bart__430_0_073', 'h_bart__430_0_105', 'h_bart__430_0_167', 'h_bart__430_0_169', 'h_bart__430_0_187',
         'h_bart__430_0_196', 'h_bart__2354_0_028', 'h_bart__2354_0_032', 'h_bart__2356_0_059'}
HINT = ', he wears a black eyepatch over one eye exactly where the sprite shows the dark patch, his other eye is blue'
SIDE = ', only a thin dark strap goes across his hair, his open blue eye is clearly visible'
PROMPT = {'h_bart__430_0_105': SIDE}
NEG = 'goggles, visor, sunglasses, mask, both eyes covered, green eyes, brown eyes'
SEEDS = (7, 11, 23, 31)
# by eye on the mask previews, in canvas px of the head close-up (512):
SKIP = {'h_bart__430_0_134'}   # the glove hides the patch on the sprite too, the head stays as it is
CLIP = {'h_bart__2354_0_032': (0, 0, 512, 250), 'h_bart__430_0_105': (0, 0, 512, 235), 'h_bart__430_0_196': (0, 0, 512, 250),
        'h_bart__430_0_203': (218, 0, 512, 512), 'h_bart__430_0_132': (0, 0, 344, 512)}
# olive visors the dark search misses: replaced by this ellipse box (the sprite blob of these frames is off the face)
AREA = {'h_bart__430_0_167': (197, 150, 317, 222), 'h_bart__430_0_169': (240, 150, 344, 238),
        'h_bart__430_0_187': (195, 134, 299, 206)}


def has(rgb, colors):
    return np.any([(rgb == c).all(axis=-1) for c in colors], axis=0)


def head_rows(a):
    op = a[..., 3] > 0
    rows = np.where(op.any(axis=1))[0]
    y0 = rows[0]
    for y in rows:
        if y - y0 >= 8 and has(a[y, :, :3], COAT).sum() >= 0.3 * op[y].sum():
            return y0, y
    return y0, rows[-1] + 1


def head_box(nat):
    """(x0, y0, x1, y1) native box of the head: the top 16 rows, x range of the hair and skin there (a ponytail flying to
    the side only widens it; gloves and the coat stay out unless they are in front of the head)."""
    op = nat[..., 3] > 0
    y0 = np.where(op.any(axis=1))[0][0]
    y1 = y0 + 16
    top = (has(nat[..., :3], HAIR) | has(nat[..., :3], SKIN)) & op
    top[:y0] = False
    top[y1:] = False
    # columns with at least 3 head texels: stray pixels of a raised fist do not count
    cols = np.where(top.sum(axis=0) >= 3)[0]
    if not len(cols):        # other colours than Bart's (Sigurd): the figure itself in these rows
        cols = np.where(op[y0:y1].any(axis=0))[0]
    return cols[0], y0, cols[-1] + 1, y1


def sprite_blob(nat):
    """Native mask of the patch: dark blobs of the head rows touching the skin, not below the eye line."""
    op = nat[..., 3] > 0
    y0, y1 = head_rows(nat)
    pat = has(nat[..., :3], PATCH) & op
    pat[:y0] = False
    pat[y1:] = False
    skin = has(nat[..., :3], SKIN) & op
    rows = np.where(skin[y0:y1].any(axis=1))[0]
    if len(rows):                # the patch ends at most 5 rows below the first skin: the undershirt also touches the chin
        pat[y0 + rows[0] + 6:] = False
    lab, n = ndimage.label(pat, structure=np.ones((3, 3)))
    near = ndimage.binary_dilation(skin, structure=np.ones((3, 3)))
    keep = np.zeros(pat.shape, bool)
    bx0, by0, bx1, by1 = head_box(nat)
    box = np.zeros(pat.shape, bool)
    box[by0:by1, bx0:bx1] = True
    for i in range(1, n + 1):
        b = lab == i
        if b.sum() >= 3 and (b & near).any() and (b & box).sum() >= 0.7 * b.sum():
            keep |= b
    return keep


def dark_blob(path, rows=None, cols=None):
    """Big dark low-saturation shape of a head render (512 canvas) in the given canvas rows / columns."""
    a = np.asarray(Image.open(path).convert('RGB')).astype(float)
    lum = a @ np.array([0.3, 0.59, 0.11])
    dark = (lum < 92) & ((a.max(axis=-1) - a.min(axis=-1)) < 46)
    if rows:
        dark[:rows[0]] = False
        dark[rows[1]:] = False
    if cols:
        dark[:, :cols[0]] = False
        dark[:, cols[1]:] = False
    core = ndimage.binary_opening(dark, structure=np.ones((13, 13)))
    lab, n = ndimage.label(core)
    if not n:
        return np.zeros(dark.shape, bool)
    sizes = ndimage.sum(core, lab, range(1, n + 1))
    return lab == (int(np.argmax(sizes)) + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    a = ap.parse_args()
    meta = json.load(open(META))
    fmap = json.load(open(os.path.join(R1, 'map.json')))
    jobs1 = {j['name']: j for j in json.load(open(os.path.join(R1, 'jobs.json')))}
    reps = [k for k in fmap if not k.endswith('__head') and k not in SKIP and (not a.only or k in a.only.split(','))]
    for d in ('control', 'boards', 'base', 'mask', 'preview'):
        os.makedirs(os.path.join(R3, d), exist_ok=True)
    out, heroes = [], {}
    empty = []
    for rep in reps:
        m = meta[rep]
        hn = rep + '__head'
        h = heroes.setdefault(m['hero_dir'], Hero(os.path.join(ROOT, m['hero_dir'])))
        img, _ = h.assemble(h.placements(m['set'], m['frame']))    # exact colours (frame_rgba is smoothed)
        nat = np.asarray(img)
        assert nat.shape[1] * 8 == frame_rgba(h, m['set'], m['frame']).width
        hx, hy = m['head']
        bx0, by0, bx1, by1 = head_box(nat)
        canvas_rows = (max(0, (by0 - hy) * 16), min(512, (by1 - hy) * 16))
        canvas_cols = (max(0, (bx0 - hx) * 16), min(512, (bx1 - hx) * 16))
        base = os.path.join(R1, 'before', hn + '.png')
        mask = np.zeros((512, 512), np.uint8)
        if rep.startswith('c_sigurd'):
            mask[dark_blob(os.path.join(R1, 'res_7', 'v4', hn + '.png'), canvas_rows, canvas_cols)] = 255
        else:
            blob = sprite_blob(nat)
            for ny, nx in zip(*np.nonzero(blob)):
                u, v = (nx - hx) * 16, (ny - hy) * 16
                if -16 < u < 512 and -16 < v < 512:
                    mask[max(0, v):max(0, v + 16), max(0, u):max(0, u + 16)] = 255
            if rep in VISOR:
                mask[dark_blob(base, canvas_rows, canvas_cols)] = 255
        if rep in AREA:
            x0, y0, x1, y1 = AREA[rep]
            mask[:] = 0
            cv2.ellipse(mask, ((x0 + x1) // 2, (y0 + y1) // 2), ((x1 - x0) // 2, (y1 - y0) // 2), 0, 0, 360, 255, -1)
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
        if rep in CLIP:
            x0, y0, x1, y1 = CLIP[rep]
            clip = np.zeros(mask.shape, np.uint8)
            clip[y0:y1, x0:x1] = 255
            mask &= clip
        ctrl = jobs1[hn]['control']
        if not mask.any():
            empty.append(rep)
            continue
        Image.fromarray(mask).save(os.path.join(R3, 'mask', hn + '.png'))
        shutil.copyfile(base, os.path.join(R3, 'base', hn + '.png'))
        shutil.copyfile(os.path.join(R1, ctrl), os.path.join(R3, ctrl))
        shutil.copyfile(os.path.join(R1, jobs1[hn]['ref']), os.path.join(R3, jobs1[hn]['ref']))
        cap = jobs1[hn]['prompt'].split(', he wears')[0]
        out.append({'name': hn, 'control': ctrl, 'ref': jobs1[hn]['ref'], 'prompt': cap + PROMPT.get(rep, HINT),
                    'base': f'base/{hn}.png', 'mask': f'mask/{hn}.png'})
        # preview: control | base + mask outline
        b = np.asarray(Image.open(base).convert('RGB')).copy()
        cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(b, cs, -1, (0, 255, 255), 2)
        c = np.asarray(Image.open(os.path.join(R1, ctrl)).convert('RGB')).copy()
        cv2.drawContours(c, cs, -1, (0, 255, 255), 2)
        Image.fromarray(np.hstack([c, b])).save(os.path.join(R3, 'preview', rep + '.png'))
    json.dump(out, open(os.path.join(R3, 'jobs.json'), 'w'), indent=1)
    with open(os.path.join(R3, 'run.sh'), 'w', newline='\n') as f:
        f.write('#!/usr/bin/env bash\n# Eyepatch by masked repaint of the head close-ups. Resumable.\n'
                'cd /workspace\nexport PYTHONPATH=/workspace HF_HOME=/workspace/hf\n'
                f'for s in {" ".join(map(str, SEEDS))}; do\n'
                '  python repaint_pod.py --jobs redraw/eyepatch3/jobs.json --out redraw/eyepatch3/res_$s --seed $s '
                f'--lora lora/xeno_klein_v4.safetensors --neg "{NEG}"\n'
                'done\necho RENDER_DONE\n')
    test = ('h_bart__430_0_190__head', 'h_bart__430_0_064__head', 'h_bart__430_0_073__head',
            'c_sigurd_harcourt_172669__npc_008__head')
    json.dump([j for j in out if j['name'] in test], open(os.path.join(R3, 'jobs_test.json'), 'w'), indent=1)
    with open(os.path.join(R3, 'test.sh'), 'w', newline='\n') as f:
        f.write('#!/usr/bin/env bash\n# 4 heads, one seed: does the repaint work at all? Runs in the foreground, ~1 min.\n'
                'cd /workspace\nexport PYTHONPATH=/workspace HF_HOME=/workspace/hf\n'
                'python repaint_pod.py --jobs redraw/eyepatch3/jobs_test.json --out redraw/eyepatch3/test_7 --seed 7 '
                f'--lora lora/xeno_klein_v4.safetensors --neg "{NEG}" 2>&1 | grep -v "it/s"\n'
                'ls redraw/eyepatch3/test_7/v4 | wc -l\necho TEST_DONE\n')
    print(len(out), 'jobs x', len(SEEDS), 'seeds; no mask:', empty)


if __name__ == '__main__':
    main()
