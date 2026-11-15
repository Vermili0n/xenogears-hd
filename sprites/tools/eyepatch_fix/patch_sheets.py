"""Eyepatch QA sheets: every distinct head WITH A FACE of a group, native | HD, sorted by how thick the dark band/patch of
the HD head is (thinnest first = band without a patch come first). Only an order for the eye, it decides nothing.

  python patch_sheets.py <group: h_bart | c_bart | c_sigurd> <out_prefix> [--k 6] [--only set:f,f] [--max-w 2000] [--max-h 1400]
Hero sets are composed from the PACK files, cutscene sets from their final composites (work/*_red.png).
"""
import argparse
import csv
import hashlib
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
from pack_heads import Hero, pack_frame  # noqa: E402

XS = r'<XENO_SPRITES>'
GROUPS = {
    'c_bart': {'c_bart_4b16d7': '4b16d73da7', 'c_bart_5822b9': '5822b9bb58', 'c_bart_70a4dc': '70a4dcc69d',
               'c_bart_9522cf': '9522cfbb67', 'c_bart_bcc899': 'bcc8990fb9', 'c_bart_c75eb5': 'c75eb56e69',
               'c_bart_c7ad1d': 'c7ad1d08fb', 'c_bart_eaf637': 'eaf637a98c'},
    'c_sigurd': {'c_sigurd_harcourt_172669': '172669b371', 'c_sigurd_harcourt_179511': '179511abf3',
                 'c_sigurd_harcourt_195138': '195138629a'},
}
BG = (150, 170, 90)


def head_box(native, top):
    """Rows of the head: from the top of the figure, a share of its height (at least 12, at most 26 texels)."""
    rows = np.where(np.asarray(native)[..., 3].any(axis=1))[0]
    if not len(rows):
        return 0, 0
    y0, y1 = rows[0], rows[-1] + 1
    return y0, min(y1, y0 + max(12, min(26, int((y1 - y0) * top))))


def measure(hd_rgb, k):
    """-> (skin share of the opaque head, radius of the thickest dark blob in texels). hd_rgb: float HxWx3 on white."""
    r, g, b = hd_rgb[..., 0], hd_rgb[..., 1], hd_rgb[..., 2]
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    opaque = ~((r > 250) & (g > 250) & (b > 250))
    skin = (r > g + 18) & (g > b + 12) & (lum > 60) & (lum < 175) & (r < 225)
    dark = (lum < 88) & ((np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)) < 42) & opaque
    rad = float(ndimage.distance_transform_edt(dark).max()) / k if dark.any() else 0.0
    return skin.sum() / max(1, opaque.sum()), rad


def cells_hero(a):
    h = Hero(os.path.join(XS, 'extracted', 'disc1_full', 'bart'))
    cache = {}
    want = None
    if a.only:
        s, fr = a.only.split(':')
        want = (s, {int(x) for x in fr.split(',')})
    for s in h.layout:
        if want and s != want[0]:
            continue
        for fi in range(len(h.layout[s]['frames'])):
            if want and fi not in want[1]:
                continue
            try:
                new, _ = pack_frame(h, s, fi, a.k, cache)
                old, _ = h.assemble(h.placements(s, fi))
            except Exception:  # noqa: BLE001
                continue
            yield f'{s}:{fi}', old, new
        print(s, 'done', flush=True)


def cells_npc(a):
    for grp, sid in GROUPS[a.group].items():
        h = Hero(os.path.join(XS, 'extracted', 'npc_full', sid))
        short = grp.split('_')[-1]
        for s in h.layout:
            for fi in range(len(h.layout[s]['frames'])):
                p = os.path.join(XS, 'ai', 'prod_work', grp, 'work', f'{s}_{fi:03d}_red.png')
                if not os.path.exists(p):
                    continue
                try:
                    old, _ = h.assemble(h.placements(s, fi))
                except Exception:  # noqa: BLE001
                    continue
                al = old.getchannel('A').resize((old.width * a.k, old.height * a.k), Image.NEAREST)
                new = Image.open(p).convert('RGB').resize((old.width * a.k, old.height * a.k), Image.LANCZOS).convert('RGBA')
                new.putalpha(al)
                yield f'{short}:{fi}', old, new
        print(grp, 'done', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('group')
    ap.add_argument('out')
    ap.add_argument('--k', type=int, default=6)
    ap.add_argument('--top', type=float, default=0.42)
    ap.add_argument('--only', default='')
    ap.add_argument('--min-skin', type=float, default=0.05)
    ap.add_argument('--max-w', type=int, default=2000)
    ap.add_argument('--max-h', type=int, default=1400)
    a = ap.parse_args()
    it = cells_hero(a) if a.group == 'h_bart' else cells_npc(a)
    seen, items, n_all, n_back = {}, [], 0, 0
    for lab, old, new in it:
        n_all += 1
        y0, y1 = head_box(old, a.top)
        hd = Image.new('RGB', new.size, (255, 255, 255))
        hd.paste(new, (0, 0), new)
        crop_hd = hd.crop((0, y0 * a.k, hd.width, y1 * a.k))
        sk, rad = measure(np.asarray(crop_hd).astype(float), a.k)
        if a.group == 'h_bart':
            # a face = the sprite's own skin colours on the head (the HD share also takes hair shadows for skin)
            na = np.asarray(old)[y0:y1]
            sk_n = int(((na[..., 3] > 0) & (((na[..., :3] == (222, 164, 90)).all(axis=-1)) | ((na[..., :3] == (180, 123, 49)).all(axis=-1)))).sum())
            if sk_n < 4:
                n_back += 1
                continue
        elif sk < a.min_skin:
            n_back += 1
            continue
        key = hashlib.md5(crop_hd.tobytes()).hexdigest()
        if key in seen:
            seen[key].append(lab)
            continue
        seen[key] = [lab]
        o = old.crop((0, y0, old.width, y1)).resize((old.width * a.k, (y1 - y0) * a.k), Image.NEAREST)
        items.append((rad, lab, key, o, new.crop((0, y0 * a.k, new.width, y1 * a.k))))
    items.sort(key=lambda t: t[0])
    print(f'{n_all} frames, {n_back} without a face, {len(items)} distinct heads')
    with open(a.out + '.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['radius', 'first', 'same_head_in'])
        for rad, lab, key, _o, _n in items:
            w.writerow([f'{rad:.2f}', lab, ' '.join(seen[key])])
    # flow onto pages
    pages, page, x, y, rh = [], [], 8, 8, 0
    for it_ in items:
        rad, lab, key, o, n = it_
        w = o.width + n.width + 12
        h = max(o.height, n.height) + 14
        if x + w > a.max_w:
            x, y, rh = 8, y + rh + 6, 0
        if y + h > a.max_h:
            pages.append(page)
            page, x, y, rh = [], 8, 8, 0
        page.append((x, y, f'{lab} r{rad:.1f}' + (f' x{len(seen[key])}' if len(seen[key]) > 1 else ''), o, n))
        x += w
        rh = max(rh, h)
    if page:
        pages.append(page)
    for pi, pg in enumerate(pages):
        H = max(c[1] + max(c[3].height, c[4].height) + 22 for c in pg)
        s = Image.new('RGB', (a.max_w, H), BG)
        d = ImageDraw.Draw(s)
        for x, y, lab, o, n in pg:
            d.text((x, y), lab, fill=(255, 255, 0))
            s.paste(o, (x, y + 12), o)
            s.paste(n, (x + o.width + 2, y + 12), n)
        p = f'{a.out}_{pi + 1}.png'
        s.save(p)
        print(p, s.size, len(pg))


if __name__ == '__main__':
    main()
