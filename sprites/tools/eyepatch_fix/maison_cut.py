"""Bits of Maison's mustache left on the face edge. On the sprite the mustache sticks out of the face; the repainted head has no mustache, so these
texels of the silhouette show a smear (pack) or a dark stepped blob the model drew there (head render). They are made transparent in the pack blocks,
only near the repaint mask of the head, never where a frame shows a real drawing there.

  python maison_cut.py heads <out.png>     what would be cut, on the head renders
  python maison_cut.py build               -> ai/redraw/maison2/cut/*.npy + cut.json (nothing in the pack)
  python maison_cut.py sheet <prefix>      frames from the pack: sprite | pack now | after the cut
  python maison_cut.py install             RetroArch closed: backup, blocks, draw-rect files of the sets
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import npc_rects  # noqa: E402
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from bart_limit import file_to_frame, frame_owner  # noqa: E402
from elly934_finalize import write_bc7_from_psx  # noqa: E402
from install_0311 import rect_names  # noqa: E402
from npc_rects import NPC, WRITTEN  # noqa: E402
from seam_fill import frame_interior  # noqa: E402
from seam_fill_npc import rect as part_rect  # noqa: E402

M1 = os.path.join(ROOT, 'ai', 'redraw', 'maison')
M2 = os.path.join(ROOT, 'ai', 'redraw', 'maison2')
CUT = os.path.join(M2, 'cut')
RES = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod', 'v4')
META = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
SETS = ['6e595cab89', '2be5277d28', 'a096333c67', '1c0f2c14f4']
S = 8
# Head of frame 30 drawn for set 1c0f2c (sets 2be527, a09633 share it) kept its white mustache: the first mask took the temple instead. The same frame
# of 6e595c differs in 6 texels and has a clean mouth: that zone of the head render (canvas px) and of the blocks comes from there.
MOUTH_REP = 'c_maison_1c0f2c__npc_030__head'
MOUTH_SRC = 'c_maison_6e595c__npc_030__head'
MOUTH_ZONE = (296, 205, 372, 268)
MOUTH_FROM = {n: MOUTH_SRC for n in json.load(open(os.path.join(M1, 'map.json')))[MOUTH_REP]}


def rep_map():
    out = {}
    for rep, names in json.load(open(os.path.join(M1, 'map.json'))).items():
        for n in names:
            out[n] = rep
    return out


def rep_mask(rep):
    m = None
    for d in ('mask', 'mask2'):
        f = os.path.join(M2, d, rep + '.png')
        if os.path.exists(f):
            a = np.asarray(Image.open(f).convert('L')) > 0
            m = a if m is None else (m | a)
    return m


def head_classes(rep_or_name, mask):
    """-> (bg, blob): canvas masks of a head render. blob = the dark stepped shape outside the face near the mask."""
    a = np.asarray(Image.open(os.path.join(RES, rep_or_name + '.png')).convert('RGB')).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    bg = (r > 170) & (g < 110) & (b > 170)
    if mask is None:
        return bg, np.zeros(bg.shape, bool)
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    dark = (lum < 75) & ~bg
    skin = (r > g + 18) & (g > b + 12) & (lum > 90)
    zone = cv2.dilate(mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (91, 91))) > 0
    core = ndimage.binary_opening(dark, structure=np.ones((7, 7)))
    lab, n = ndimage.label(core)
    near_bg = ndimage.binary_dilation(bg, structure=np.ones((3, 3)), iterations=2)
    blob = np.zeros(bg.shape, bool)
    my, mx = np.nonzero(mask)
    for i in range(1, n + 1):
        c = lab == i
        area = int(c.sum())
        ys, xs = np.nonzero(c)
        if area < 60 or area > 6000 or ys.max() - ys.min() > 130 or xs.max() - xs.min() > 110 or ys.max() >= 505:
            continue
        if (c & zone).sum() < 0.5 * area or (c & near_bg).sum() < 12:
            continue
        # all the views look right: the bit stands to the right of the mouth, at its height (coat and ribbon are lower / to the left)
        if xs.mean() < mx.mean() - 10 or ys.mean() > my.max() + 22 or ys.mean() < my.min() - 4:   # above the mask: the glasses at the edge
            continue
        blob |= c
    if blob.any():
        blob = ndimage.binary_dilation(blob, structure=np.ones((3, 3)), iterations=4) & dark
        blob &= ~(cv2.dilate(skin.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0)
    return bg, blob


def mouth_blocks():
    """Pixels of the blocks in the mouth zone of frame 30 for every set that shares that head, from 6e595c's sheet at the same rects.
    -> {block: (ys, xs, values)}"""
    ub = json.load(open(os.path.join(NPC, '6e595cab89', 'uses.json')))
    sheet = np.load(os.path.join(NPC, '6e595cab89', 'page.npy'))
    acc = {}
    zx0, zy0, zx1, zy1 = MOUTH_ZONE
    for n in MOUTH_FROM:
        group = n.split('__')[0]
        sid = next(x for x in SETS if x.startswith(group.split('_')[-1]))
        ha = Hero(os.path.join(NPC, sid))
        ua = json.load(open(os.path.join(NPC, sid, 'uses.json')))
        pl = ha.placements('npc', 30)
        owner, x0, y0 = frame_owner(ha, pl)
        hx, hy = META[n[:-6]]['head']
        for k, p in enumerate(pl):
            sx, sy, w, ht = part_rect(p['block'])
            hd = npc_rects.hd_sheet(ub['uses'], p['pal'], sheet.shape)
            FX, FY, _, _ = file_to_frame(p, x0, y0, ht * S, w * S)
            ix, iy = np.clip(FX.astype(int), 0, owner.shape[1] - 1), np.clip(FY.astype(int), 0, owner.shape[0] - 1)
            cx, cy = ((FX - hx) * 16).astype(int), ((FY - hy) * 16).astype(int)
            z = (cx >= zx0) & (cx < zx1) & (cy >= zy0) & (cy < zy1) & (owner[iy, ix] == k)
            if not z.any():
                continue
            ys, xs = np.nonzero(z)
            vals = hd[sy * S + ys, sx * S + xs]
            for use in ua['uses']:
                for b in use['blocks']:
                    bx, by = (b['x'] - use['sx']) * 4, b['y'] - use['sy']
                    px, py = sx * S + xs - bx * S, sy * S + ys - by * S
                    inb = (px >= 0) & (px < b['w'] * 4 * S) & (py >= 0) & (py < b['h'] * S)
                    if not inb.any():
                        continue
                    nm = f"{b['hash']:x}-{p['pal']}"
                    if os.path.exists(os.path.join(PACK, nm + '.bc7')):
                        acc.setdefault(nm, []).append((py[inb], px[inb], vals[inb]))
    out = {nm: tuple(np.concatenate([v[i] for v in lst]) for i in range(3)) for nm, lst in acc.items()}
    print('mouth of frame 30:', {nm: len(v[0]) for nm, v in out.items()})
    return out


def build():
    reps = rep_map()
    os.makedirs(CUT, exist_ok=True)
    for f in os.listdir(CUT):
        os.remove(os.path.join(CUT, f))
    blocks = {}
    stats = {}
    for sid in SETS:
        d = os.path.join(NPC, sid)
        h = Hero(d)
        lay = h.layout['npc']
        inner = frame_interior([(lay, d)], lambda hh, k: os.path.join(hh, 'parts'))
        u = json.load(open(os.path.join(d, 'uses.json')))
        group = 'c_maison_' + sid[:6]
        allow, near = {}, {}
        for fi in range(len(lay['frames'])):
            name = f'{group}__npc_{fi:03d}'
            if name not in META:
                continue
            hn = name + '__head'
            if not os.path.exists(os.path.join(RES, hn + '.png')):
                continue
            rep = reps.get(hn, hn)
            src = MOUTH_FROM.get(hn, hn)
            mask = rep_mask(reps.get(src, src))
            bg, blob = head_classes(src, mask)
            zone = None if mask is None else (cv2.dilate(mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (91, 91))) > 0)
            pl = h.placements('npc', fi)
            owner, x0, y0 = frame_owner(h, pl)
            hx, hy = META[name]['head']
            for k, p in enumerate(pl):
                r = part_rect(p['block'])
                sx, sy, w, ht = r
                if w < 2 or ht < 2:
                    continue
                H_, W_ = ht * S, w * S
                FX, FY, tx, ty = file_to_frame(p, x0, y0, H_, W_)
                ix, iy = np.clip(FX.astype(int), 0, owner.shape[1] - 1), np.clip(FY.astype(int), 0, owner.shape[0] - 1)
                vis = owner[iy, ix] == k
                cx, cy = ((FX - hx) * 16).astype(int), ((FY - hy) * 16).astype(int)
                ok = (cx >= 0) & (cx < 512) & (cy >= 0) & (cy < 512)
                out_face = np.zeros((H_, W_), bool)
                out_face[ok] = (bg | blob)[cy[ok], cx[ok]]
                key = (r, p['pal'])
                if key not in allow:
                    allow[key] = np.ones((H_, W_), bool)
                    near[key] = np.zeros((H_, W_), bool)
                allow[key] &= ~(vis & ok & ~out_face)    # a real drawing shows here in this frame: keep
                if zone is not None:
                    z = np.zeros((H_, W_), bool)
                    z[ok] = zone[cy[ok], cx[ok]]
                    near[key] |= z & vis & ok & out_face
        n_px = 0
        for key, al in allow.items():
            (sx, sy, w, ht), pal = key
            c = al & near[key]
            if not c.any():
                continue
            blk = f"r{sx:#x}"  # only for the message
            # texels inside the figure in any frame stay
            for (b_, p_), m in inner.items():
                if p_ == pal and part_rect(b_) == (sx, sy, w, ht) and m.any():
                    tw, th = (w - 1) * S, (ht - 1) * S
                    yy, xx = np.mgrid[0:ht * S, 0:w * S]
                    tix = np.minimum(np.minimum(xx, tw - 1) * w // tw, w - 1)
                    tiy = np.minimum(np.minimum(yy, th - 1) * ht // th, ht - 1)
                    c = c & ~m[tiy, tix]
            n_px += int(c.sum())
            ys, xs = np.nonzero(c)
            for use in u['uses']:
                for b in use['blocks']:
                    bx, by = (b['x'] - use['sx']) * 4, b['y'] - use['sy']
                    bw, bh = b['w'] * 4, b['h']
                    px, py = sx * S + xs - bx * S, sy * S + ys - by * S
                    inb = (px >= 0) & (px < bw * S) & (py >= 0) & (py < bh * S)
                    if not inb.any():
                        continue
                    nm = f"{b['hash']:x}-{pal}"
                    f = os.path.join(PACK, nm + '.bc7')
                    if not os.path.exists(f):
                        continue
                    if nm not in blocks:
                        blocks[nm] = np.zeros((bh * S, bw * S), bool)
                    if blocks[nm].shape != (bh * S, bw * S):
                        continue
                    blocks[nm][py[inb], px[inb]] = True
        stats[sid] = n_px
    moved = mouth_blocks()
    n_changed = 0
    for nm in sorted(set(blocks) | set(moved)):
        a = read_bc7_level0(os.path.join(PACK, nm + '.bc7')).copy()
        if nm in moved:
            ys, xs, vals = moved[nm]
            a[ys, xs] = vals
        c = blocks.get(nm)
        if c is not None:
            if a.shape[:2] != c.shape:
                print('size differs', nm, a.shape, c.shape)
                continue
            a[c & (a[..., 3] > 0)] = 0
        np.save(os.path.join(CUT, nm + '.npy'), a)
        n_changed += 1
    json.dump({'stats': stats, 'blocks': n_changed}, open(os.path.join(M2, 'cut.json'), 'w'))
    print('page px by set', stats, 'block files changed', n_changed)


def heads(out):
    jobs = [j['name'] for j in json.load(open(os.path.join(M2, 'jobs.json')))]
    W, cw, ch = 1980, 240, 200
    cols = W // cw
    s = Image.new('RGB', (W, (len(jobs) // cols + 1) * (ch + 14)), (60, 60, 60))
    d = ImageDraw.Draw(s)
    for i, n in enumerate(jobs):
        mask = rep_mask(n)
        bg, blob = head_classes(n, mask)
        a = np.asarray(Image.open(os.path.join(RES, n + '.png')).convert('RGB')).copy()
        a[blob] = (0, 255, 0)
        im = Image.fromarray(a).crop((96, 60, 416, 327)).resize((cw - 4, ch), Image.LANCZOS)
        x, y = (i % cols) * cw, (i // cols) * (ch + 14)
        s.paste(im, (x, y + 12))
        d.text((x + 2, y), n.replace('c_maison_', '').replace('__head', '').replace('__npc', '') + f'  blob {int(blob.sum())}', fill=(255, 255, 0))
    s.save(out)
    print(out, s.size)


def set_sheet(sid, over):
    """The set's HD sheet from its first use, clipped to the page (blocks may start above it). over(block file) -> array."""
    d = os.path.join(NPC, sid)
    u = json.load(open(os.path.join(d, 'uses.json')))
    shape = np.load(os.path.join(d, 'page.npy')).shape
    pal = u['palettes'][0]
    use = u['uses'][0]
    hd = np.zeros((shape[0] * S, 256 * S, 4), np.uint8)
    for b in use['blocks']:
        x, y, w, h_ = (b['x'] - use['sx']) * 4, b['y'] - use['sy'], b['w'] * 4, b['h']
        a = over(os.path.join(PACK, f"{b['hash']:x}-{pal}.bc7"))
        y0, y1 = max(0, y), min(y + h_, shape[0])
        if y1 > y0 and x + w <= 256:
            hd[y0 * S:y1 * S, x * S:(x + w) * S] = a[(y0 - y) * S:(y1 - y) * S]
    return hd


def game_rect(hd, r, k):
    sx, sy, w, h_ = r
    c = hd[sy * S:(sy + h_) * S, sx * S:(sx + w) * S]
    tw, th = (w - 1) * S if w > 1 else w * S, (h_ - 1) * S if h_ > 1 else h_ * S
    c = c[:th, :tw]
    rgb = Image.fromarray(np.ascontiguousarray(c[..., :3])).resize((w * k, h_ * k), Image.LANCZOS)
    rgb.putalpha(Image.fromarray(np.where(c[..., 3] > 0, 255, 0).astype(np.uint8)).resize((w * k, h_ * k), Image.NEAREST))
    return rgb


def draw(h, hd, fi, k):
    pl = h.placements('npc', fi)
    old, _ = h.assemble(pl)
    x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
    out = Image.new('RGBA', (old.width * k, old.height * k), (0, 0, 0, 0))
    for p in pl:
        im = game_rect(hd, part_rect(p['block']), k)
        if p['flipx']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        out.alpha_composite(im, ((p['x'] - x0) * k, (p['y'] - y0) * k))
    return old.resize((old.width * k, old.height * k), Image.NEAREST), out


def sheet(prefix, k=8, top=0.40):
    def over(f):
        n = os.path.join(CUT, os.path.basename(f)[:-4] + '.npy')
        return np.load(n) if os.path.exists(n) else read_bc7_level0(f)

    cells, seen = [], set()
    for sid in SETS:
        h = Hero(os.path.join(NPC, sid))
        hd0, hd1 = set_sheet(sid, read_bc7_level0), set_sheet(sid, over)
        for fi in range(len(h.layout['npc']['frames'])):
            o, now = draw(h, hd0, fi, k)
            _, new = draw(h, hd1, fi, k)
            if now.tobytes() == new.tobytes():
                continue
            c = int(o.height * top)
            n2 = new.crop((0, 0, new.width, c))
            key = n2.tobytes()
            if key in seen:
                continue
            seen.add(key)
            cells.append((f'{sid[:6]}:{fi}', o.crop((0, 0, o.width, c)), now.crop((0, 0, now.width, c)), n2))
    W, Hmax = 1990, 1450
    pages, page, x, y, rh = [], [], 6, 6, 0
    for lab, o, n1, n2 in cells:
        w, h_ = o.width + n1.width + n2.width + 12, o.height + 16
        if x + w > W and page:
            x, y, rh = 6, y + rh + 4, 0
        if y + h_ > Hmax and page:
            pages.append(page)
            page, x, y, rh = [], 6, 6, 0
        page.append((x, y, lab, o, n1, n2))
        x += w
        rh = max(rh, h_)
    pages.append(page)
    print('distinct frames changed', len(cells))
    for pi, pg in enumerate(pages):
        H = max(c[1] + c[3].height + 20 for c in pg)
        s_ = Image.new('RGB', (W, H), (150, 170, 90))
        d = ImageDraw.Draw(s_)
        for x, y, lab, o, n1, n2 in pg:
            d.text((x, y), lab, fill=(255, 255, 0))
            s_.paste(o, (x, y + 13), o)
            s_.paste(n1, (x + o.width + 2, y + 13), n1)
            s_.paste(n2, (x + o.width + n1.width + 4, y + 13), n2)
        p_ = f'{prefix}_{pi + 1}.png'
        s_.save(p_)
        print(p_, s_.size, len(pg))


def install():
    r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq retroarch.exe'], capture_output=True, text=True)
    if 'retroarch.exe' in r.stdout.lower():
        sys.exit('RetroArch is running - close it first')
    stamp = time.strftime('%Y-%m-%d_%H%M')
    bk = os.path.join(r'<DATA_DRIVE>\xeno_redraw_backup', 'maison_cut_' + stamp)
    os.makedirs(bk, exist_ok=True)
    ok = n = 0
    for f in os.listdir(CUT):
        nm = f[:-4]
        n += 1
        p = os.path.join(PACK, nm + '.bc7')
        shutil.copy2(p, bk)
        ok += bool(write_bc7_from_psx(p, np.load(os.path.join(CUT, f))))
    print(f'blocks {ok}/{n}, backup {bk}')
    if ok != n:
        sys.exit(1)
    for dst, src in MOUTH_FROM.items():    # the head renders follow, so that a rebuild of these groups does not bring the mustache back
        p = os.path.join(RES, dst + '.png')
        shutil.copy2(p, bk)
        a = np.array(Image.open(p).convert('RGB'))
        b = np.asarray(Image.open(os.path.join(RES, src + '.png')).convert('RGB'))
        zx0, zy0, zx1, zy1 = MOUTH_ZONE
        a[zy0:zy1, zx0:zx1] = b[zy0:zy1, zx0:zx1]
        Image.fromarray(a).save(p)
    ours = {ln.strip() for ln in open(WRITTEN, encoding='utf-8')}
    gone = 0
    for sid in SETS:
        for nm in rect_names(sid) & ours:
            p = os.path.join(PACK, nm + '.bc7')
            if os.path.exists(p):
                shutil.move(p, os.path.join(bk, nm + '.bc7'))
                gone += 1
    print('rect files moved to the backup', gone)
    r = subprocess.run([sys.executable, 'npc_rects.py', '--only', ','.join(SETS)], cwd=TOOLS, capture_output=True, text=True)
    print(r.stdout[-400:], r.stderr[-300:])
    lost = [nm for sid in SETS for nm in rect_names(sid) & ours if not os.path.exists(os.path.join(PACK, nm + '.bc7'))]
    for nm in lost:      # names of a set without a complete use: back from the backup
        shutil.copy2(os.path.join(bk, nm + '.bc7'), os.path.join(PACK, nm + '.bc7'))
    print('rect files restored from the backup', len(lost))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['heads', 'build', 'sheet', 'install'])
    ap.add_argument('out', nargs='?')
    a = ap.parse_args()
    if a.cmd == 'heads':
        heads(a.out)
    elif a.cmd == 'build':
        build()
    elif a.cmd == 'sheet':
        sheet(a.out)
    else:
        install()
