"""Local (low-frequency) chroma transfer from the sprite to a LoRA redraw: fixes regional colour drift
(e.g. trousers pulled to the board's olive) while keeping the drawn lines, shading and lightness.

  python color_local.py --set ai/pod_v2/test2 --src pod/report/test2/cols/crop_v2 --dst pod/report/test2/cols/crop_v2_cl
Inside the silhouette, in Lab:  ab_out += k * (G(ab_sprite) + offset - G(ab_out)),  G = mask-normalised Gaussian
(sigma 12 px at 8x = 1.5 native px); offset = mean (teacher - sprite) ab of the character, measured on training pairs.
"""
import argparse
import json
import os

import cv2
import numpy as np
from PIL import Image


def fg(rgb):
    a = rgb.astype(int)
    return (abs(a[..., 0] - 255) + a[..., 1] + abs(a[..., 2] - 255)) > 60


def blur_masked(x, m, sigma):
    num = cv2.GaussianBlur(x * m[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(m, (0, 0), sigma)[..., None]
    return num / np.maximum(den, 1e-3)


def local_match(ctrl_rgb, out_rgb, offset_ab=(0.0, 0.0), sigma=12.0, k=0.7):
    m = (fg(ctrl_rgb) & fg(out_rgb)).astype(np.float32)
    if m.sum() < 200:
        return out_rgb
    lc = cv2.cvtColor(ctrl_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lo = cv2.cvtColor(out_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    want = blur_masked(lc[..., 1:], m, sigma) + np.asarray(offset_ab, np.float32)
    have = blur_masked(lo[..., 1:], m, sigma)
    res = lo.copy()
    inside = fg(out_rgb)
    res[..., 1:][inside] = np.clip(lo[..., 1:] + k * (want - have), 0, 255)[inside]
    return cv2.cvtColor(res.astype(np.uint8), cv2.COLOR_LAB2RGB)


def anchor_match(ctrl_rgb, out_rgb, sil, sigma_ab=12.0, sigma_l=20.0, k_l=0.85):
    """Colours of a redraw anchored to the sprite, for sets drawn without a board (there the model's colours drift from
    frame to frame): low-frequency chroma taken from the sprite in full, low-frequency lightness as a gain, so the drawn
    lines and shading stay. Dark pixels (outlines) keep their chroma: a large shift would tint them."""
    m = sil.astype(np.float32)
    if m.sum() < 200:
        return out_rgb
    lc = cv2.cvtColor(ctrl_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lo = cv2.cvtColor(out_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    den = np.maximum(cv2.GaussianBlur(m, (0, 0), sigma_l), 1e-3)
    want_l = cv2.GaussianBlur(lc[..., 0] * m, (0, 0), sigma_l) / den
    have_l = cv2.GaussianBlur(lo[..., 0] * m, (0, 0), sigma_l) / den
    gain = np.clip((want_l + 8.0) / (have_l + 8.0), 0.4, 2.5) ** k_l
    res = lo.copy()
    res[..., 0] = np.clip(lo[..., 0] * gain, 0, 255)
    d_ab = blur_masked(lc[..., 1:], m, sigma_ab) - blur_masked(lo[..., 1:], m, sigma_ab)
    w = np.clip((res[..., 0] - 12.0) / 28.0, 0.0, 1.0)[..., None]
    res[..., 1:] = np.clip(lo[..., 1:] + w * d_ab, 0, 255)
    out = cv2.cvtColor(res.astype(np.uint8), cv2.COLOR_LAB2RGB)
    out[~sil] = out_rgb[~sil]
    return out


def teacher_offsets(pairs_dir, key_of):
    """{identity: mean (teacher - sprite) ab} over training pairs (full frames only); '' = global mean."""
    acc = {}
    names = [f[:-4] for f in os.listdir(os.path.join(pairs_dir, 'target')) if f.endswith('.png') and f.count('__') == 1]
    for n in names[::3]:
        c = np.asarray(Image.open(os.path.join(pairs_dir, 'control', n + '.png')).convert('RGB'))
        t = np.asarray(Image.open(os.path.join(pairs_dir, 'target', n + '.png')).convert('RGB'))
        m = fg(c) & fg(t)
        m = cv2.erode(m.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        if m.sum() < 200:
            continue
        d = cv2.cvtColor(t, cv2.COLOR_RGB2LAB)[m][:, 1:].astype(np.float32).mean(0) - \
            cv2.cvtColor(c, cv2.COLOR_RGB2LAB)[m][:, 1:].astype(np.float32).mean(0)
        for key in (key_of(n), ''):
            acc.setdefault(key, []).append(d)
    return {k: np.mean(v, 0).tolist() for k, v in acc.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', required=True, help='test set folder with jobs.json (control paths)')
    ap.add_argument('--src', required=True)
    ap.add_argument('--dst', required=True)
    ap.add_argument('--pairs', default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ai', 'pairs_v2'))
    ap.add_argument('--sigma', type=float, default=12.0)
    ap.add_argument('--k', type=float, default=0.7)
    a = ap.parse_args()

    def key_of(n):
        job = n.split('__')[0]
        return job.rsplit('_', 1)[0] if job.startswith('c_') else job.split('_')[1] if job.startswith('h_') else job

    offs = teacher_offsets(a.pairs, key_of)
    os.makedirs(a.dst, exist_ok=True)
    for j in json.load(open(os.path.join(a.set, 'jobs.json'))):
        sp = os.path.join(a.src, j['name'] + '.png')
        if not os.path.exists(sp):
            continue
        c = np.asarray(Image.open(os.path.join(a.set, j['control'])).convert('RGB'))
        o = np.asarray(Image.open(sp).convert('RGB'))
        off = offs.get(key_of(j['name']), offs.get('', [0, 0])) if not j['name'].startswith('g_') else [0, 0]
        Image.fromarray(local_match(c, o, off, a.sigma, a.k)).save(os.path.join(a.dst, j['name'] + '.png'))
    print('done', a.dst, 'offsets', len(offs))


if __name__ == '__main__':
    main()
