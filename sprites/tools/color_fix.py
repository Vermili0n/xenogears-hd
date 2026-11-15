"""Palette-card colour alignment of a composed group (report 28, step 3): every palette colour of the sprite is pulled to
the group's own median render colour in the frames where it drifted (ab and/or lightness), shading kept.

  python color_fix.py <group> [--out DIR] [--k-ab 1.5] [--k-l 2.0] [--sheet N] [--inplace]
Needs pod/report/qa/color/<group>_card.json (color_card.py). Default writes corrected copies to
pod/report/qa/color/fix_<group>/ (the group's work/ is untouched) and a before|after sheet of the N most changed frames;
--inplace rewrites ai/prod_work/<group>/work/*_red.png (originals kept in work_before_color/).
Only a/b move (hue, saturation); lightness stays. Mask per colour: the sprite pixels of that palette colour at 8x, gated by render pixels near the frame's measured colour
(a misaligned render never tints its neighbours), feathered 2 px.
"""
import argparse
import json
import os
import shutil
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = r'<XENO_SPRITES>'
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ai_redraw import Hero  # noqa: E402

COLOR = os.path.join(ROOT, 'pod', 'report', 'qa', 'color')


def to_lab(rgb):
    return cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


def to_rgb(lab):
    return (np.clip(cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB), 0, 1) * 255 + 0.5).astype(np.uint8)


def fix_frame(h, s, f, red, fixes, gate=15.0, ab_only=True):
    """fixes: {palette key: (frame Lab, target Lab)}. Returns corrected RGB and the mean |shift| applied."""
    nat, _ = h.assemble(h.placements(s, f))
    a = np.asarray(nat)
    key = (a[..., 0].astype(np.int32) << 16) | (a[..., 1].astype(np.int32) << 8) | a[..., 2]
    op = a[..., 3] > 0
    lab = to_lab(red)
    out = lab.copy()
    moved = 0.0
    for k, (have, want) in fixes.items():
        m = np.kron((op & (key == k)).astype(np.uint8), np.ones((8, 8), np.uint8)).astype(bool)
        if m.shape != lab.shape[:2] or not m.any():
            continue
        near = np.linalg.norm(lab - np.asarray(have, np.float32), axis=2) < gate
        w = cv2.GaussianBlur((m & near).astype(np.float32), (0, 0), 2.0)
        d = np.asarray(want, np.float32) - np.asarray(have, np.float32)
        if ab_only:   # lightness differences are mostly shading / a different material on the same palette entry
            d[0] = 0.0
        out += w[..., None] * d
        moved += float(np.abs(d).sum() * w.mean())
    return to_rgb(out), moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('group')
    ap.add_argument('--out', default='')
    ap.add_argument('--k-ab', type=float, default=3.0, help='fix a colour when its ab is off by > max(8, k * group spread)')
    ap.add_argument('--sheet', type=int, default=24)
    ap.add_argument('--inplace', action='store_true')
    a = ap.parse_args()
    card = json.load(open(os.path.join(COLOR, f'{a.group}_card.json')))
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    h = Hero(os.path.join(ROOT, next(m['hero_dir'] for m in meta.values() if m['group'] == a.group)))
    work = os.path.join(ROOT, 'ai', 'prod_work', a.group, 'work')
    per = {}                                                  # frame -> {key: (have, want)}
    for c in card:
        tab = max(8.0, a.k_ab * c['mad_ab'])
        sp, md = np.asarray(c['sprite_lab'][1:]), np.asarray(c['med'][1:])
        for fr, lb, dab, dl in c['frames']:
            # only frames that drifted AWAY from the sprite's colour: a frame closer to the sprite than the group median
            # (e.g. Maria's vivid orange where most frames are duller) is left alone
            if dab > tab and np.linalg.norm(np.asarray(lb[1:]) - sp) > np.linalg.norm(md - sp):
                per.setdefault(fr, {})[c['key']] = (lb, c['med'])
    out_dir = work if a.inplace else (a.out or os.path.join(COLOR, f'fix_{a.group}'))
    if a.inplace:
        bk = os.path.join(os.path.dirname(work), 'work_before_color')
        os.makedirs(bk, exist_ok=True)
    else:
        os.makedirs(out_dir, exist_ok=True)
    changed = []
    for fr, fixes in sorted(per.items()):
        s, f = fr.split(':')
        name = f'{s}_{int(f):03d}_red.png'
        src = os.path.join(work, name)
        red = np.asarray(Image.open(src).convert('RGB'))
        new, moved = fix_frame(h, s, int(f), red, fixes)
        if a.inplace and not os.path.exists(os.path.join(bk, name)):
            shutil.copy2(src, os.path.join(bk, name))
        Image.fromarray(new).save(os.path.join(out_dir, name))
        changed.append((moved, fr, red, new))
    print(f'{a.group}: {len(changed)} frames corrected of {len({f[0] for c in card for f in c["frames"]})}')
    if not changed or not a.sheet:
        return
    changed.sort(key=lambda x: -x[0])
    cells = []
    for moved, fr, before, after in changed[:a.sheet]:
        hh = 220
        b = Image.fromarray(before)
        w = max(1, round(b.width * hh / b.height))
        pair = Image.new('RGB', (2 * w + 4, hh + 16), (40, 40, 40))
        pair.paste(b.resize((w, hh), Image.LANCZOS), (0, 16))
        pair.paste(Image.fromarray(after).resize((w, hh), Image.LANCZOS), (w + 4, 16))
        ImageDraw.Draw(pair).text((2, 2), f'{fr}  before | after', fill=(255, 255, 0))
        cells.append(pair)
    per_row = max(1, 1900 // (max(c.width for c in cells) + 8))
    rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
    W = max(sum(c.width + 8 for c in r) for r in rows)
    H = sum(max(c.height for c in r) + 8 for r in rows)
    sheet = Image.new('RGB', (W, H), (25, 25, 25))
    y = 0
    for r in rows:
        x = 0
        for c in r:
            sheet.paste(c, (x, y))
            x += c.width + 8
        y += max(c.height for c in r) + 8
    p = os.path.join(COLOR, f'{a.group}_fix_sheet.png')
    sheet.save(p)
    print(p, sheet.size)


if __name__ == '__main__':
    main()
