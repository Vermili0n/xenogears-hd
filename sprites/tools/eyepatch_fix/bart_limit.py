"""Second build of the Bart parts: the 63 parts of 03.11 were replaced whole, and the owner frame of a slice brings its own drawing of the
whole part (2354_0:24-29 lost the braid and got another jacket). Here every part starts from the file it had BEFORE the install and only the pixels
inside the repaint mask of its owner frame, visible in that frame, take the new drawing (soft edge). Everything else stays pixel for pixel.

  python bart_limit.py build              -> ai/prod_work/h_bart_patch/stage2/<part>.npy (core convention), parts/fill/*.npy on top
  python bart_limit.py sheet <prefix> [set:frame ...] [--k 6]   whole frames: sprite | before the install | new build
  python bart_limit.py install            RetroArch closed: backup + write_bc7_from_psx
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from elly934_finalize import write_bc7_from_psx  # noqa: E402
import patch_final as pf  # noqa: E402
import patch_final2 as p2  # noqa: E402

BART = os.path.join(ROOT, 'ai', 'prod_work', 'h_bart_patch')
STAGE2 = os.path.join(BART, 'stage2')
FILL = os.path.join(BART, 'fill')
BK = sorted(glob.glob(r'<DATA_DRIVE>\xeno_redraw_backup\bart_patch_*'))[0]
S = 8


def file_to_frame(p, x0, y0, H_, W_):
    """Each file pixel -> frame coordinates in texels (float), through the game's stretch and flips."""
    w, h_ = p['w'], p['h']
    tw, th = (w - 1) * S, (h_ - 1) * S
    yy, xx = np.mgrid[0:H_, 0:W_]
    tx, ty = np.minimum(xx, tw - 1) / tw * w, np.minimum(yy, th - 1) / th * h_
    fx = (w - tx) if p['flipx'] else tx
    fy = (h_ - ty) if p['flipy'] else ty
    return p['x'] - x0 + fx, p['y'] - y0 + fy, tx, ty


def frame_owner(h, pl):
    x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
    W, H = max(p['x'] + p['w'] for p in pl) - x0, max(p['y'] + p['h'] for p in pl) - y0
    owner = np.full((H, W), -1)
    for k, p in enumerate(pl):
        m = np.asarray(h.part(p['block'], p['pal']))[..., 3] > 0
        if p['flipx']:
            m = m[:, ::-1]
        if p['flipy']:
            m = m[::-1]
        owner[p['y'] - y0:p['y'] - y0 + p['h'], p['x'] - x0:p['x'] - x0 + p['w']][m] = k
    return owner, x0, y0


def build():
    h = Hero(pf.HD)
    sel = json.load(open(os.path.join(BART, 'selected.json')))['parts']
    frames = [n for n in pf.PICKS if pf.META[n]['group'] == 'h_bart']
    os.makedirs(STAGE2, exist_ok=True)
    for f in os.listdir(STAGE2):
        os.remove(os.path.join(STAGE2, f))
    changed = {}
    for nm in sel:
        old_p = os.path.join(BK, nm + '.bc7')
        if not os.path.exists(old_p):
            print('no backup', nm)
            continue
        old = read_bc7_level0(old_p).copy()
        new = np.asarray(Image.open(os.path.join(BART, 'stage', nm + '.png')).convert('RGBA')).astype(int)
        H_, W_ = old.shape[:2]
        best = None
        for n in frames:
            m = pf.META[n]
            pl = h.placements(m['set'], m['frame'])
            idx = [k for k, p in enumerate(pl) if f"{p['block']}-{p['pal']}" == nm]
            if not idx:
                continue
            owner, x0, y0 = frame_owner(h, pl)
            red = np.asarray(Image.open(os.path.join(BART, 'work', f"{m['set']}_{m['frame']:03d}_red.png")).convert('RGB')).astype(int)
            mask = np.asarray(Image.open(p2.mask_of(n)).convert('L')).astype(np.float32) / 255
            hx, hy = m['head']
            for k in idx:
                p = pl[k]
                FX, FY, tx, ty = file_to_frame(p, x0, y0, H_, W_)
                ix, iy = np.clip(FX.astype(int), 0, owner.shape[1] - 1), np.clip(FY.astype(int), 0, owner.shape[0] - 1)
                vis = owner[iy, ix] == k
                # how well does the new file fit this frame's composite = is this the slice's owner frame
                rx, ry = np.clip((FX * S).astype(int), 0, red.shape[1] - 1), np.clip((FY * S).astype(int), 0, red.shape[0] - 1)
                sel_ = vis & (new[..., 3] > 0)
                err = float(np.abs(new[..., :3] - red[ry, rx])[sel_].mean()) if sel_.sum() > 64 else 1e9
                cx, cy = ((FX + x0 - hx - x0) * 16).astype(int), ((FY + y0 - hy - y0) * 16).astype(int)
                ok = (cx >= 0) & (cx < 512) & (cy >= 0) & (cy < 512)
                w = np.zeros((H_, W_), np.float32)
                w[ok] = mask[cy[ok], cx[ok]]
                w *= vis
                if best is None or err < best[0]:
                    best = (err, n, w)
        if best is None:
            print('no frame', nm)
            continue
        err, n, w = best
        w = cv2.GaussianBlur(w, (0, 0), 2.0)
        w = np.clip(w * 1.6 - 0.3, 0, 1)
        out = old.astype(np.float32)
        opaque_new = new[..., 3] > 0
        k = (w * opaque_new)[..., None]
        out[..., :3] = out[..., :3] * (1 - k) + new[..., :3] * k
        out = out.round().astype(np.uint8)
        old_tr = (old == 0).all(axis=-1)
        grow = (w > 0.5) & opaque_new & old_tr
        out[grow, :3] = new[grow, :3]
        out[grow, 3] = 255
        out[old_tr & ~grow] = 0      # RGB != 0 with alpha 0 would be an opaque pixel in the core's convention
        cut = (~opaque_new) & ~old_tr & (w > 0.5)
        out[cut] = 0
        np.save(os.path.join(STAGE2, nm + '.npy'), out)
        changed[nm] = (n, round(err, 1), int((w > 0.05).sum()), int(cut.sum()))
    for f in glob.glob(os.path.join(FILL, '*.npy')):
        nm = os.path.basename(f)[:-4]
        if nm in changed:
            print('fill and patch on one part:', nm)
            continue
        shutil.copyfile(f, os.path.join(STAGE2, nm + '.npy'))
    print(len(changed), 'parts built, +', len(glob.glob(os.path.join(FILL, '*.npy'))), 'filled')
    for nm, v in sorted(changed.items(), key=lambda kv: -kv[1][2])[:8]:
        print(nm, v)
    json.dump(changed, open(os.path.join(BART, 'stage2.json'), 'w'), indent=0)


def game_part(c, w, h_, k):
    H, W = c.shape[:2]
    tw = int(round((w - 1) * W / w)) if w > 1 else W
    th = int(round((h_ - 1) * H / h_)) if h_ > 1 else H
    c = c[:th, :tw]
    rgb = Image.fromarray(np.ascontiguousarray(c[..., :3])).resize((w * k, h_ * k), Image.LANCZOS)
    rgb.putalpha(Image.fromarray(np.where(c[..., 3] > 0, 255, 0).astype(np.uint8)).resize((w * k, h_ * k), Image.NEAREST))
    return rgb


def old_file(nm):
    f = os.path.join(BK, nm + '.bc7')
    if not os.path.exists(f):
        f = os.path.join(PACK, nm + '.bc7')
    return read_bc7_level0(f) if os.path.exists(f) else None


def new_file(nm):
    f = os.path.join(STAGE2, nm + '.npy')
    if os.path.exists(f):
        return np.load(f)
    return old_file(nm)


def frame(h, s, fi, k, files, cache):
    pl = h.placements(s, fi)
    old, _ = h.assemble(pl)
    x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
    out = Image.new('RGBA', (old.width * k, old.height * k), (0, 0, 0, 0))
    for p in pl:
        nm = f"{p['block']}-{p['pal']}"
        if nm not in cache:
            a = files(nm)
            cache[nm] = h.part(p['block'], p['pal']).convert('RGBA').resize((p['w'] * k, p['h'] * k), Image.NEAREST) if a is None else game_part(a, p['w'], p['h'], k)
        im = cache[nm]
        if p['flipx']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        out.alpha_composite(im, ((p['x'] - x0) * k, (p['y'] - y0) * k))
    return old.resize((old.width * k, old.height * k), Image.NEAREST), out


def sheet(a):
    h = Hero(pf.HD)
    if a.items:
        items = [(i.split(':')[0], int(i.split(':')[1])) for i in a.items]
    else:
        sel = json.load(open(os.path.join(BART, 'selected.json')))
        items = [(pf.META[n]['set'], pf.META[n]['frame']) for n in pf.PICKS if pf.META[n]['group'] == 'h_bart'] + [tuple(o) for o in sel['others']] + [('430_0', 54), ('430_0', 63), ('430_0', 66)]
    k = a.k
    c1, c2, cells = {}, {}, []
    for s, fi in items:
        o, n1 = frame(h, s, fi, k, old_file, c1)
        _, n2 = frame(h, s, fi, k, new_file, c2)
        ch = int(o.height * a.top)
        cells.append((f'{s}:{fi}', [i.crop((0, 0, i.width, ch)) for i in (o, n1, n2)]))
    W, Hmax = 1990, 1450
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


def install():
    bk = os.path.join(r'<DATA_DRIVE>\xeno_redraw_backup', 'bart_limit_' + time.strftime('%Y-%m-%d_%H%M'))
    os.makedirs(bk, exist_ok=True)
    ok = n = 0
    for f in sorted(glob.glob(os.path.join(STAGE2, '*.npy'))):
        nm = os.path.basename(f)[:-4]
        n += 1
        p = os.path.join(PACK, nm + '.bc7')
        if os.path.exists(p):
            shutil.copy2(p, bk)
        ok += bool(write_bc7_from_psx(p, np.load(f)))
    print(f'installed {ok}/{n}, backup {bk}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['build', 'sheet', 'install'])
    ap.add_argument('prefix', nargs='?')
    ap.add_argument('items', nargs='*')
    ap.add_argument('--k', type=int, default=6)
    ap.add_argument('--top', type=float, default=1.0)
    a = ap.parse_args()
    if a.cmd == 'build':
        build()
    elif a.cmd == 'sheet':
        sheet(a)
    else:
        install()
