"""Colour card of a production group (report 28, step "check without correcting").

Every native sprite pixel has an exact palette colour; its 8x8 block in the composed render (ai/prod_work/<g>/work,
8x native) is where the render paints that material. For every palette colour: the render colour per frame (median Lab
of the central 4x4 of each interior block), the group median, the spread, and frames whose colour left the spread.

  python color_card.py <group> [--min-px 12] [--top 30]
Writes pod/report/qa/color/<group>_card.png (row per colour: sprite | group median | per-frame strip, frame order)
and <group>_card.json; prints the colour table and the worst frames.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = r'<XENO_SPRITES>'
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ai_redraw import Hero  # noqa: E402

OUT = os.path.join(ROOT, 'pod', 'report', 'qa', 'color')


def lab(rgb):
    a = np.asarray(rgb, np.float32).reshape(-1, 1, 3) / 255.0
    return cv2.cvtColor(a, cv2.COLOR_RGB2LAB).reshape(-1, 3)


def rgb_of(lab3):
    a = np.asarray(lab3, np.float32).reshape(1, 1, 3)
    return tuple(int(v) for v in np.clip(cv2.cvtColor(a, cv2.COLOR_LAB2RGB).reshape(3) * 255, 0, 255))


def frame_colours(h, s, f, red_path, min_px):
    nat, _ = h.assemble(h.placements(s, f))
    a = np.asarray(nat)
    rgb, op = a[..., :3].astype(np.int32), a[..., 3] > 0
    key = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    same = np.zeros(key.shape, np.int32)                       # 4-neighbours of the same colour
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        sh = np.roll(np.roll(key, dy, 0), dx, 1)
        so = np.roll(np.roll(op, dy, 0), dx, 1)
        same += (so & (sh == key)).astype(np.int32)
    inner = op & (same >= 2)
    inner[0, :] = inner[-1, :] = inner[:, 0] = inner[:, -1] = False
    r = np.asarray(Image.open(red_path).convert('RGB'))
    if r.shape[:2] != (a.shape[0] * 8, a.shape[1] * 8):
        return {}
    blocks = r.reshape(a.shape[0], 8, a.shape[1], 8, 3)[:, 2:6, :, 2:6, :]       # central 4x4 of every 8x8 block
    out = {}
    for k in np.unique(key[inner]):
        ys, xs = np.nonzero(inner & (key == k))
        if len(ys) < min_px:
            continue
        px = blocks[ys, :, xs, :, :].reshape(-1, 3)
        out[int(k)] = (np.median(lab(px), 0), len(ys))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('group')
    ap.add_argument('--min-px', type=int, default=4, help='interior sprite pixels of a colour in a frame to measure it')
    ap.add_argument('--top', type=int, default=30)
    a = ap.parse_args()
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    frames = sorted({(m['set'], m['frame']) for m in meta.values() if m['group'] == a.group})
    h = Hero(os.path.join(ROOT, next(m['hero_dir'] for m in meta.values() if m['group'] == a.group)))
    work = os.path.join(ROOT, 'ai', 'prod_work', a.group, 'work')
    per = defaultdict(list)                                     # colour -> [(frame, lab, n)]
    for s, f in frames:
        rp = os.path.join(work, f'{s}_{f:03d}_red.png')
        if os.path.exists(rp):
            for k, (lb, n) in frame_colours(h, s, f, rp, a.min_px).items():
                per[k].append((f'{s}:{f}', lb, n))
    rows = []
    for k, lst in per.items():
        if len(lst) < 3:
            continue
        L = np.array([x[1] for x in lst])
        med = np.median(L, 0)
        dab = np.hypot(L[:, 1] - med[1], L[:, 2] - med[2])
        dl = np.abs(L[:, 0] - med[0])
        mad_ab, mad_l = float(np.median(dab)), float(np.median(dl))
        sprite = ((k >> 16) & 255, (k >> 8) & 255, k & 255)
        sl = lab([sprite])[0]
        rows.append(dict(key=k, sprite=sprite, n_frames=len(lst), px=int(sum(x[2] for x in lst)), med=med.tolist(),
                         mad_ab=mad_ab, mad_l=mad_l, sprite_lab=sl.tolist(),
                         hue_shift=float(np.degrees(np.arctan2(med[2], med[1]) - np.arctan2(sl[2], sl[1]))),
                         frames=[(fr, lb.tolist(), float(d), float(e)) for (fr, lb, _), d, e in zip(lst, dab, dl)]))
    rows.sort(key=lambda r: -r['px'])
    os.makedirs(OUT, exist_ok=True)
    json.dump(rows, open(os.path.join(OUT, f'{a.group}_card.json'), 'w'))
    # card image: sprite swatch | group median | per-frame colours in frame order
    sw, strip_w = 36, 4
    W = sw * 2 + 30 + max(len(r['frames']) for r in rows) * strip_w + 240
    im = Image.new('RGB', (W, 22 + len(rows) * (sw + 6)), (30, 30, 30))
    d = ImageDraw.Draw(im)
    d.text((4, 4), f'{a.group}: sprite | render median | every frame (frame order)   spread ab/L', fill=(255, 255, 0))
    for i, r in enumerate(rows):
        y = 22 + i * (sw + 6)
        d.rectangle((0, y, sw - 1, y + sw - 1), fill=r['sprite'])
        d.rectangle((sw + 4, y, 2 * sw + 3, y + sw - 1), fill=rgb_of(r['med']))
        x = 2 * sw + 20
        for fr, lb, dab, dl in r['frames']:
            d.rectangle((x, y, x + strip_w - 1, y + sw - 1), fill=rgb_of(lb))
            x += strip_w
        d.text((x + 8, y + 4), f"{r['n_frames']} fr  ab {r['mad_ab']:.1f}  L {r['mad_l']:.1f}", fill=(220, 220, 220))
        d.text((x + 8, y + 18), f"hue {r['hue_shift']:+.0f} deg vs sprite", fill=(160, 160, 160))
    im.save(os.path.join(OUT, f'{a.group}_card.png'))
    print(f'{a.group}: {len(rows)} palette colours measured')
    print('  sprite RGB      render RGB      frames  px     spread ab  L   hue vs sprite')
    for r in rows:
        print(f"  {str(r['sprite']):15} {str(rgb_of(r['med'])):15} {r['n_frames']:5} {r['px']:6}   {r['mad_ab']:5.1f} {r['mad_l']:5.1f}   {r['hue_shift']:+5.0f}")
    # worst frames: a colour whose ab is far outside its own spread
    bad = defaultdict(list)
    for r in rows:
        thr = max(8.0, 3.5 * r['mad_ab'])
        for fr, lb, dab, dl in r['frames']:
            if dab > thr:
                bad[fr].append((dab / thr, r['sprite'], rgb_of(lb), rgb_of(r['med'])))
    worst = sorted(bad.items(), key=lambda kv: -max(x[0] for x in kv[1]))[:a.top]
    print(f'frames with an off colour: {len(bad)} of {len(frames)}; worst:')
    for fr, lst in worst:
        x = max(lst)
        print(f'  {fr:12} x{x[0]:.1f}  sprite {x[1]} -> render {x[2]} (group {x[3]})' + (f'  +{len(lst) - 1} more' if len(lst) > 1 else ''))


if __name__ == '__main__':
    main()
