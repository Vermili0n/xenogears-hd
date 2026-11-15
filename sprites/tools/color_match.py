"""Remove a global colour cast from local-model redraws: shift Lab means inside the sprite to the teacher's tone.

  python color_match.py --job ai/klein_npc/<nid> --pairs npc_<nid>_ [--src out --dst out_cm]
The control (xBR sprite, same pose and placement) carries the palette; the teacher (Gemini) itself sits at a fairly
constant Lab offset from the control (Fei: L -3, a -4.7, b +4.4), so the target is control mean - teacher offset,
measured on this character's training pairs (ai/pairs, name prefix --pairs). Shading and detail stay as drawn.
"""
import argparse
import os

import cv2
import numpy as np
from PIL import Image


def fg(rgb):
    a = rgb.astype(int)
    return (abs(a[..., 0] - 255) + a[..., 1] + abs(a[..., 2] - 255)) > 60


def teacher_offset(prefix, root):
    """Mean (control - teacher) Lab offset over the character's training pairs."""
    ds = []
    for f in sorted(os.listdir(os.path.join(root, 'control'))):
        if not f.startswith(prefix):
            continue
        c = np.asarray(Image.open(os.path.join(root, 'control', f)).convert('RGB'))
        t = Image.open(os.path.join(root, 'target', f)).convert('RGBA')
        t = np.asarray(Image.alpha_composite(Image.new('RGBA', t.size, (255, 0, 255, 255)), t).convert('RGB'))
        r = match(c, t)
        if isinstance(r, tuple):
            ds.append(r[1])
    return np.mean(ds, 0) if ds else np.zeros(3)


def match(ctrl_rgb, red_rgb, strength=1.0, offset=None):
    m = fg(ctrl_rgb) & fg(red_rgb)
    m = cv2.erode(m.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    if m.sum() < 200:
        return red_rgb
    lc = cv2.cvtColor(ctrl_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lr = cv2.cvtColor(red_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    d = lc[m].mean(0) - lr[m].mean(0)
    if offset is not None:
        d = (d - offset) * strength
    out = lr.copy()
    inside = fg(red_rgb)
    out[inside] = np.clip(out[inside] + d, 0, 255)
    return cv2.cvtColor(out.astype(np.uint8), cv2.COLOR_LAB2RGB), d


def hist_match(src, ref):
    """Per-channel Lab histogram matching inside the sprites (ref = teacher redraw of a similar pose)."""
    ms, mr = fg(src), fg(ref)
    if ms.sum() < 200 or mr.sum() < 200:
        return src
    ls = cv2.cvtColor(src, cv2.COLOR_RGB2LAB)
    lr = cv2.cvtColor(ref, cv2.COLOR_RGB2LAB)
    out = ls.copy()
    for c in range(3):
        s, r = ls[..., c][ms], lr[..., c][mr]
        sv, si, sc = np.unique(s, return_inverse=True, return_counts=True)
        rv, rc = np.unique(r, return_counts=True)
        ch = out[..., c]
        ch[ms] = np.interp(np.cumsum(sc) / s.size, np.cumsum(rc) / r.size, rv)[si].astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_LAB2RGB)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--job', required=True)
    ap.add_argument('--src', default='out')
    ap.add_argument('--dst', default='out_cm')
    ap.add_argument('--strength', type=float, default=1.0)
    ap.add_argument('--pairs', default='', help='mean mode: training-pair name prefix of this character, e.g. fei_ or npc_<nid>_')
    ap.add_argument('--mode', choices=['mean', 'hist'], default='mean')
    ap.add_argument('--jobs', default='', help='hist mode: jobs.json with the reference of every grid')
    ap.add_argument('--pairs-dir', default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ai', 'pairs'))
    a = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if a.mode == 'mean':
        off = teacher_offset(a.pairs, a.pairs_dir)
        print('teacher offset L/a/b', np.round(off, 1))
    else:
        import json
        refs = {j['grid']: j['ref'] for j in json.load(open(a.jobs)) if j['nid'] == os.path.basename(os.path.normpath(a.job))}
    os.makedirs(os.path.join(a.job, a.dst), exist_ok=True)
    for f in sorted(os.listdir(os.path.join(a.job, a.src))):
        if not f.endswith('.png') or '_tmp' in f:
            continue
        ctrl = np.asarray(Image.open(os.path.join(a.job, 'in', 'grid_' + f)).convert('RGB'))
        red = np.asarray(Image.open(os.path.join(a.job, a.src, f)).convert('RGB'))
        if a.mode == 'hist':
            g = f[:-4]
            if g not in refs:
                continue
            t = Image.open(os.path.join(root, refs[g])).convert('RGBA')
            ref = np.asarray(Image.alpha_composite(Image.new('RGBA', t.size, (255, 0, 255, 255)), t).convert('RGB'))
            Image.fromarray(hist_match(red, ref)).save(os.path.join(a.job, a.dst, f))
            continue
        r = match(ctrl, red, a.strength, off)
        if isinstance(r, tuple):
            out, d = r
            print(f, 'shift L/a/b', np.round(d, 1))
        else:
            out = r
        Image.fromarray(out).save(os.path.join(a.job, a.dst, f))


if __name__ == '__main__':
    main()
