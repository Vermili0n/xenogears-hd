"""Frames AS THE GAME DRAWS THEM. Xenogears draws a w x h part as a w x h quad whose UVs span only w-1 x h-1 texels, and the pack files are
pre-squeezed for that (batch_redraw.uv_compensate): the last texel row / column of a file is a repeat of the edge and is not shown. The older
QA sheets (pack_heads.pack_frame) drew the whole file: chin stripes, "keyhole" eyes, rectangles around eyes and shifted seams on them were
artifacts of those sheets.

  python patch_game.py stage                 parts touched by the masks -> seam fill -> ai/prod_work/h_bart_patch/stage + selected.json
  python patch_game.py sheet <prefix> [set:frame ...] [--k 9] [--top 0.34]     sprite | pack now | new
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
import patch_final as pf  # noqa: E402
import patch_final2 as p2  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from pack_heads import Hero  # noqa: E402
from patch_sheets import head_box as sheet_box  # noqa: E402
from seam_fill import fill_interior, frame_interior  # noqa: E402

PARTS = os.path.join(pf.BART, 'parts')
STAGE = os.path.join(pf.BART, 'stage')
S = 8


def game_part(a, w, h, k):
    """HD part (file array) -> what the game's w x h quad shows, at k px per texel."""
    H, W = a.shape[:2]
    tw = int(round((w - 1) * W / w)) if w > 1 else W
    th = int(round((h - 1) * H / h)) if h > 1 else H
    c = a[:th, :tw]
    rgb = Image.fromarray(np.ascontiguousarray(c[..., :3])).resize((w * k, h * k), Image.LANCZOS)
    al = Image.fromarray(np.where(c[..., 3] > 0, 255, 0).astype(np.uint8)).resize((w * k, h * k), Image.NEAREST)
    rgb.putalpha(al)
    return rgb


def game_frame(hero, s, fi, k, files, cache):
    """files(name) -> HD array or None (then the sprite's own part)."""
    pl = hero.placements(s, fi)
    x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
    W = max(p['x'] + p['w'] for p in pl) - x0
    H = max(p['y'] + p['h'] for p in pl) - y0
    out = Image.new('RGBA', (W * k, H * k), (0, 0, 0, 0))
    for p in pl:
        nm = f"{p['block']}-{p['pal']}"
        if nm not in cache:
            a = files(nm)
            if a is None:
                cache[nm] = hero.part(p['block'], p['pal']).convert('RGBA').resize((p['w'] * k, p['h'] * k), Image.NEAREST)
            else:
                cache[nm] = game_part(a, p['w'], p['h'], k)
        im = cache[nm]
        if p['flipx']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        out.alpha_composite(im, ((p['x'] - x0) * k, (p['y'] - y0) * k))
    return out


def pack_file(nm):
    f = os.path.join(PACK, nm + '.bc7')
    return read_bc7_level0(f) if os.path.exists(f) else None


def stage_file(nm):
    f = os.path.join(STAGE, nm + '.png')
    if os.path.exists(f):
        return np.asarray(Image.open(f).convert('RGBA'))
    return pack_file(nm)


def outer_cut(h, nm, a, frames, inner):
    """File pixels of a part that land on the head render's background in EVERY picked frame using the part: the sprite's silhouette is wider
    than the drawing there, and the composite only has a smear (brown / pink bits on the edge). Mapped through the game's stretch.
    Texels inside the figure in any frame stay."""
    H_, W_ = a.shape[:2]
    res = None
    for n in frames:
        m = pf.META[n]
        pl = h.placements(m['set'], m['frame'])
        x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
        hd = os.path.join(pf.F, 'v4', n + '__head.png')
        if not os.path.exists(hd):
            continue
        r = np.asarray(Image.open(hd).convert('RGB')).astype(int)
        bg = (r[..., 0] > 170) & (r[..., 1] < 110) & (r[..., 2] > 170)
        hx, hy = m['head']
        for p in pl:
            if f"{p['block']}-{p['pal']}" != nm:
                continue
            w, h_ = p['w'], p['h']
            if w < 2 or h_ < 2:
                return None
            tw, th = (w - 1) * S, (h_ - 1) * S
            yy, xx = np.mgrid[0:H_, 0:W_]
            tx, ty = np.minimum(xx, tw - 1) / tw * w, np.minimum(yy, th - 1) / th * h_
            fx = (w - tx) if p['flipx'] else tx
            fy = (h_ - ty) if p['flipy'] else ty
            cx = ((p['x'] - x0 + fx - hx) * 16).astype(int)
            cy = ((p['y'] - y0 + fy - hy) * 16).astype(int)
            ok = (cx >= 0) & (cx < 512) & (cy >= 0) & (cy < 512)
            c = np.zeros((H_, W_), bool)
            c[ok] = bg[cy[ok], cx[ok]]
            res = c if res is None else (res & c)
            if inner is not None:
                keep = inner[np.minimum(ty.astype(int), h_ - 1), np.minimum(tx.astype(int), w - 1)]
                res = res & ~keep
    return None if res is None else (res & (a[..., 3] > 0))


def stage():
    h = Hero(pf.HD)
    pf.mask_src = lambda name, pick: p2.mask_of(name)
    frames = [n for n in pf.PICKS if pf.META[n]['group'] == 'h_bart']
    names = {}
    for n in frames:
        for part in pf.touched(h, n):
            names.setdefault(part, []).append(n)
    lay = json.load(open(os.path.join(pf.HD, 'layout.json')))
    inner = frame_interior([(v, pf.HD) for v in lay.values()], lambda hh, k: os.path.join(hh, 'parts'))
    os.makedirs(STAGE, exist_ok=True)
    for f in os.listdir(STAGE):
        os.remove(os.path.join(STAGE, f))
    missing = []
    n_cut = 0
    for nm in names:
        f = os.path.join(PARTS, nm + '.png')
        if not os.path.exists(f):
            missing.append(nm)
            continue
        blk, pal = nm.split('-')
        a = np.asarray(Image.open(f).convert('RGBA')).astype(np.int16)
        a, _ = fill_interior(a, None, S, a[..., 3] == 0, inner.get((blk, pal)))
        a = a.copy()
        cut = outer_cut(h, nm, a, frames, inner.get((blk, pal)))
        if cut is not None and cut.any():
            a[cut, 3] = 0
            H_, W_ = a.shape[:2]
            th, tw = H_ - S, W_ - S
            a[th:, :tw] = a[th - 1:th, :tw]
            a[:, tw:] = a[:, tw - 1:tw]
            n_cut += int(cut.sum())
        Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA').save(os.path.join(STAGE, nm + '.png'))
    print('edge pixels made transparent:', n_cut)
    use = {}
    for s in h.layout:
        for fi in range(len(h.layout[s]['frames'])):
            try:
                pl = h.placements(s, fi)
            except Exception:  # noqa: BLE001
                continue
            for p in pl:
                nm = f"{p['block']}-{p['pal']}"
                if nm in names:
                    use.setdefault(nm, set()).add((s, fi))
    fixed = {(pf.META[n]['set'], pf.META[n]['frame']) for n in frames}
    others = sorted({f for v in use.values() for f in v} - fixed)
    json.dump({'parts': sorted(set(names) - set(missing)), 'missing': missing, 'others': [list(o) for o in others]},
              open(os.path.join(pf.BART, 'selected.json'), 'w'), indent=1)
    print(len(names), 'parts,', len(missing), 'not sliced:', missing)
    print('other frames that share them:', others)


def sheet(a):
    h = Hero(pf.HD)
    sel = json.load(open(os.path.join(pf.BART, 'selected.json')))
    if a.items:
        items = [(i.split(':')[0], int(i.split(':')[1])) for i in a.items]
    else:
        items = [(pf.META[n]['set'], pf.META[n]['frame']) for n in pf.PICKS if pf.META[n]['group'] == 'h_bart'] + [tuple(o) for o in sel['others']]
    k = a.k
    now, new, cells = {}, {}, []
    for s, fi in items:
        old, _ = h.assemble(h.placements(s, fi))
        y0, y1 = sheet_box(old, a.top)
        o = old.crop((0, y0, old.width, y1)).resize((old.width * k, (y1 - y0) * k), Image.NEAREST)
        n1 = game_frame(h, s, fi, k, pack_file, now).crop((0, y0 * k, old.width * k, y1 * k))
        n2 = game_frame(h, s, fi, k, stage_file, new).crop((0, y0 * k, old.width * k, y1 * k))
        cells.append((f'{s}:{fi}', [o, n1, n2]))
    W, Hmax = a.max_w, a.max_h
    pages, page, x, y, rh = [], [], 6, 6, 0
    for lab, ims in cells:
        w, h_ = sum(i.width + 3 for i in ims) + 10, ims[0].height + 16
        if x + w > W and page:
            x, y, rh = 6, y + rh + 4, 0
        if y + h_ > Hmax and page:
            pages.append(page)
            page, x, y, rh = [], 6, 6, 0
        page.append((x, y, lab, ims))
        x += w
        rh = max(rh, h_)
    pages.append(page)
    for pi, pg in enumerate(pages):
        H = max(c[1] + c[3][0].height + 20 for c in pg)
        s = Image.new('RGB', (W, H), (150, 170, 90))
        d = ImageDraw.Draw(s)
        for x, y, lab, ims in pg:
            d.text((x, y), lab, fill=(255, 255, 0))
            xx = x
            for i in ims:
                s.paste(i, (xx, y + 13), i)
                xx += i.width + 3
        p = f'{a.prefix}_{pi + 1}.png'
        s.save(p)
        print(p, s.size, len(pg))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['stage', 'sheet'])
    ap.add_argument('prefix', nargs='?')
    ap.add_argument('items', nargs='*')
    ap.add_argument('--k', type=int, default=9)
    ap.add_argument('--top', type=float, default=0.34)
    ap.add_argument('--max-w', type=int, default=1990)
    ap.add_argument('--max-h', type=int, default=1450)
    a = ap.parse_args()
    if a.cmd == 'stage':
        stage()
    else:
        sheet(a)
