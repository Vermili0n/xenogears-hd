"""Field NPC sprites of map pairs (N = data, N+1 = VRAM textures) -> hero-style folders, and redrawn parts -> the
replacement files Beetle looks up for the map's VRAM upload blocks.

  python npc_maps.py extract --maps 608,616,618 --out extracted/npc
      one folder per unique NPC (content hash): parts/<rect>-<pal>.png, layout.json {'npc': {...}}, uses.json
      (every map/page where it appears). Same tools as heroes then work on it (make_grids, prod_fit, ebs_fill, slice).
  python npc_maps.py project --npc-dir extracted/npc/<id> --parts ai/<id>_prod/parts --out <pack-staging dir>
      redrawn 4x parts -> HD page per palette -> one <blockhash>-<clut>.png per VRAM upload block of every use.
"""
import argparse
import hashlib
import json
import mmap
import os
import sys
import struct
import warnings
import zlib

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import OPAQUE, xbr4  # noqa: E402
from extract_heroes import clut_hash  # noqa: E402
from extract_npc import sub_data  # noqa: E402
from mapvram import page_indices, parse_vram_file, set_entries  # noqa: E402
from npc_tex import part_rect, u24  # noqa: E402
from render_frames import psx_to_rgba  # noqa: E402
from xfs import get_file, read_toc  # noqa: E402
from xspr import cluts, frames, parse_set  # noqa: E402

S = 4
# palette swaps: a redrawn texel whose HD colour is > MISMATCH_DE from its sprite colour and that much closer (by
# MISMATCH_GAIN) to another palette colour is recoloured as that colour (Lab dE units)
MISMATCH_DE, MISMATCH_GAIN = 30.0, 20.0
PREFER_SHARED = 12.0  # ...choosing first among colours equal in both palettes (penalty for swapped ones)


def rect_name(r):
    tid, sx, sy, w, h = r
    return f'r{tid:x}x{sx:02x}y{sy:02x}w{w:02x}h{h:02x}'


def lut(pal):
    a = np.array([psx_to_rgba(c) for c in pal], np.uint8)
    return a


def rgba_from_idx(idx, pal):
    l = lut(pal)
    out = l[idx]
    out[..., 3] = np.where(idx == 0, 0, 255)
    return out


def sub4_pages(mm, toc, n):
    """ty-0 sets keep their texture page inside the map file (sub-file 4): u32 count, u32 offsets; item = u32 count,
    u32 offsets, image = u16 w (u16 units), u16 h, pixels. -> {set index: (w, h, raw bytes)} (first image of each item)."""
    try:
        d = sub_data(mm, toc, n, 4)
    except Exception:  # noqa: BLE001
        return {}
    if len(d) < 16:
        return {}
    cnt = struct.unpack_from('<I', d, 0)[0]
    if not 0 < cnt <= 64:
        return {}
    offs = struct.unpack_from(f'<{cnt + 1}I', d, 4)
    out = {}
    for i in range(cnt):
        it = d[offs[i]:offs[i + 1] if i + 1 <= cnt and offs[i + 1] > offs[i] else len(d)]
        if len(it) < 16:
            continue
        k = struct.unpack_from('<I', it, 0)[0]
        if not 0 < k <= 8:
            continue
        o = struct.unpack_from('<I', it, 4)[0]
        w, h = struct.unpack_from('<HH', it, o)
        raw = it[o + 4:o + 4 + w * h * 2]
        if w and h and len(raw) == w * h * 2:
            out[i] = (w, h, raw)
    return out


def map_sets(mm, toc, n):
    """-> list of dicts for the field sprite sets of map n: ty 1 = page from the VRAM file n+1, ty 0 = page in sub-file 4."""
    sub = sub_data(mm, toc, n, 3)
    cnt = u24(sub, 0)
    if cnt <= 0 or cnt > 64:
        return [], None, None
    bases = [u24(sub, 4 + 4 * i) for i in range(cnt)]
    ents = set_entries(get_file(mm, toc[n]), cnt)
    try:
        vram, blocks = parse_vram_file(get_file(mm, toc[n + 1]))
    except Exception:  # noqa: BLE001
        vram, blocks = np.zeros((512, 1024), np.uint16), []
    vram = vram.copy()
    own = sub4_pages(mm, toc, n)
    out = []
    for i, (b, e) in enumerate(zip(bases, ents)):
        if e['ty'] == 0 and i in own:
            w, h, raw = own[i]
            a = np.frombuffer(raw, '<u2').reshape(h, w)
            hh, ww = min(h, 512 - e['sy']), min(w, 1024 - e['sx'])
            vram[e['sy']:e['sy'] + hh, e['sx']:e['sx'] + ww] = a[:hh, :ww]
            blocks.append({'x': e['sx'], 'y': e['sy'], 'w': w, 'h': h, 'hash': zlib.crc32(raw) & 0xffffffff, 'off': -1,
                           'src': 'sub4'})
        elif e['ty'] != 1:
            continue
        try:
            s = parse_set(sub, b)
        except Exception:  # noqa: BLE001
            continue
        out.append({'i': i, 'set': s, 'sx': e['sx'], 'sy': e['sy']})
    return out, vram, blocks


def cmd_extract(a):
    fh = open(a.user, 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    seen = {}
    for n in [int(x) for x in a.maps.split(',')]:
        try:
            sets, vram, blocks = map_sets(mm, toc, n)
        except Exception as ex:  # noqa: BLE001
            print(n, 'skip', ex)
            continue
        for st in sets:
            s = st['set']
            pals = cluts(s['clut_raw'])
            if not pals:
                continue
            idx = page_indices(vram, st['sx'], st['sy'])
            try:
                fr = frames(s['meta'])
                rects = {}
                for f in fr:
                    for p in f:
                        rects[p['ref']] = part_rect(s['meta'], p['ref'])
            except Exception as ex:  # noqa: BLE001  (not a p256 set / broken refs)
                print(n, st['i'], 'skip set:', ex)
                continue
            # content id: meta + palettes + the pixels of all used rects
            hsh = hashlib.sha1(bytes(s['meta']) + bytes(s['clut_raw']))
            for r in sorted(set(rects.values())):
                _, sx, sy, w, h = r
                hsh.update(idx[sy:sy + h, sx:sx + w].tobytes())
            nid = hsh.hexdigest()[:10]
            root = os.path.join(a.out, nid)
            use = {'map': n, 'set': st['i'], 'sx': st['sx'], 'sy': st['sy'],
                   'blocks': [b for b in blocks if b['x'] < st['sx'] + 64 and b['x'] + b['w'] > st['sx']
                              and b['y'] < st['sy'] + 256 and b['y'] + b['h'] > st['sy']]}
            if nid in seen:
                seen[nid]['uses'].append(use)
                continue
            os.makedirs(os.path.join(root, 'parts'), exist_ok=True)
            phs = [f'{clut_hash(c):x}' for c in pals]
            used = {(rects[p['ref']], min(p['clut'], len(pals) - 1)) for f in fr for p in f}
            for r, ci in used:
                _, sx, sy, w, h = r
                if w == 0 or h == 0:
                    continue
                Image.fromarray(rgba_from_idx(idx[sy:sy + h, sx:sx + w], pals[ci]), 'RGBA').save(
                    os.path.join(root, 'parts', f'{rect_name(r)}-{phs[ci]}.png'))
            layout = {'npc': {'palettes': phs, 'frames': [
                [{'block': rect_name(rects[p['ref']]), **{k: p[k] for k in ('dx', 'dy', 'flipx', 'flipy', 'clut', 'mx', 'my', 'rot')}}
                 for p in f if rects[p['ref']][3] and rects[p['ref']][4]] for f in fr]}}
            json.dump(layout, open(os.path.join(root, 'layout.json'), 'w'))
            np.save(os.path.join(root, 'page.npy'), idx)
            json.dump({'palettes_raw': [list(map(int, c)) for c in pals]}, open(os.path.join(root, 'pal.json'), 'w'))
            seen[nid] = {'id': nid, 'frames': len(fr), 'palettes': phs, 'uses': [use]}
            print(n, st['i'], '->', nid, len(fr), 'frames', phs, flush=True)
        for nid, info in seen.items():
            json.dump(info, open(os.path.join(a.out, nid, 'uses.json'), 'w'), default=int)
    json.dump({k: {'frames': v['frames'], 'uses': len(v['uses']), 'maps': sorted({u['map'] for u in v['uses']})}
               for k, v in seen.items()}, open(os.path.join(a.out, 'index.json'), 'w'), indent=1)
    print(len(seen), 'unique NPC sets')


def xbr_page(idx, pal, S):
    """xBR upscale of the whole page in one palette, at scale S (RGBA)."""
    c4, m4 = xbr4(Image.fromarray(rgba_from_idx(idx, pal), 'RGBA'))
    if S != 4:
        k = S // 4
        c4 = np.asarray(Image.fromarray(np.ascontiguousarray(c4)).resize((c4.shape[1] * k, c4.shape[0] * k), Image.LANCZOS))
        m4 = np.asarray(Image.fromarray(np.ascontiguousarray(m4.astype(np.uint8) * 255)).resize(
            (m4.shape[1] * k, m4.shape[0] * k), Image.NEAREST)) > 127
    return np.dstack([c4, np.where(m4, OPAQUE, 0).astype(np.uint8)])


def derive_palette_pages(pages, cov, idx, pals_raw, phs, S):
    """Palette swaps (30.10): the game draws the same NPC sheet with other palettes (Chief Lee's sheet in purple for a
    merchant...), but only the palettes our redrawn frames used got an HD page - the rest stayed pixel in game.
    Every missing palette gets a page recoloured from the best redrawn one: each texel's palette index is known
    (page.npy), so the HD pixels of that texel move in Lab by  dst[index] - src[index]  (shading and lines kept);
    the delta field is softened over ~1 texel so index borders do not show. Untouched texels = xBR of that palette."""
    src = max(pages, key=lambda p: int(cov[p].sum()))
    s_lut, h, w = lut(pals_raw[phs.index(src)]), idx.shape[0], idx.shape[1]
    s_lab = cv2.cvtColor(s_lut[:, :3].reshape(1, -1, 3).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)[0]
    hd = pages[src]
    hd_lab = cv2.cvtColor(np.ascontiguousarray(hd[..., :3]).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)
    # where the redraw put something else than the sprite texel (a face over the sprite's sleeve, 30.10: the Lahan
    # boy's face turned green), the texel takes the delta of the palette colour the redraw actually shows there
    blk = hd_lab.reshape(h, S, w, S, 3).transpose(0, 2, 1, 3, 4).reshape(h, w, S * S, 3)
    opq = (hd[..., 3] > 0).reshape(h, S, w, S).transpose(0, 2, 1, 3).reshape(h, w, S * S)
    with np.errstate(all='ignore'), warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        med = np.nanmedian(np.where(opq[..., None], blk, np.nan), axis=2)          # h x w x 3 (nan: empty texel)
    dist = np.linalg.norm(med[:, :, None, :] - s_lab[None, None], axis=-1)       # h x w x 16
    dist[:, :, s_lut[:, 3] == 0] = np.inf
    dist = np.nan_to_num(dist, nan=np.inf)
    d_own = np.take_along_axis(dist, idx[..., None].astype(np.int64), 2)[..., 0]
    redrawn = cov[src].reshape(h, S, w, S).any(axis=(1, 3))
    mism = redrawn & np.isfinite(d_own) & (d_own > MISMATCH_DE) & (d_own - dist.min(2) > MISMATCH_GAIN) & (idx != 0)
    for pal in phs:
        if pal in pages:
            continue
        d_lut = lut(pals_raw[phs.index(pal)])
        d_lab = cv2.cvtColor(d_lut[:, :3].reshape(1, -1, 3).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)[0]
        # what the redraw shows instead of the sprite is mostly what every palette shares (skin, hair, outline):
        # skin and the swapped clothes can be near-identical in the source palette (Lahan boy: skin vs tan trousers)
        swapped = np.linalg.norm(d_lab - s_lab, axis=-1) > 3
        eff = np.where(mism, (dist + np.where(swapped, PREFER_SHARED, 0)).argmin(2), idx)
        delta = (d_lab - s_lab)[eff]                                         # h x w x 3, per texel
        delta[(s_lut[idx][..., 3] == 0) | (d_lut[idx][..., 3] == 0) | (d_lut[eff][..., 3] == 0)] = 0
        up = np.repeat(np.repeat(delta, S, 0), S, 1)
        up = np.dstack([cv2.GaussianBlur(np.ascontiguousarray(up[..., c]), (0, 0), S / 3) for c in range(3)])
        lab = hd_lab + up
        rgb = (np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB), 0, 1) * 255 + 0.5).astype(np.uint8)
        page = xbr_page(idx, pals_raw[phs.index(pal)], S)
        m = cov[src]
        page[m, :3] = rgb[m]
        page[m, 3] = hd[m, 3]
        gone = np.repeat(np.repeat(d_lut[idx][..., 3] == 0, S, 0), S, 1)  # texels transparent in this palette
        page[gone & m, 3] = 0
        pages[pal], cov[pal] = page, m.copy()


def cmd_project(a):
    """Redrawn parts (<rect>-<pal>.png, 4x or 8x = --scale) -> per-palette HD page -> replacement file per VRAM block
    of every use. Texels of the page not covered by our parts keep the xBR upscale of the original."""
    S = a.scale
    info = json.load(open(os.path.join(a.npc_dir, 'uses.json')))
    pals_raw = json.load(open(os.path.join(a.npc_dir, 'pal.json')))['palettes_raw']
    idx = np.load(os.path.join(a.npc_dir, 'page.npy'))
    os.makedirs(a.out, exist_ok=True)
    phs = info['palettes']
    pages, cov = {}, {}  # cov: texels covered by our redrawn parts (the rest of a page is the xBR of the original)
    for f in os.listdir(a.parts):
        if not f.endswith('.png'):
            continue
        rn, pal = f[:-4].rsplit('-', 1)
        if pal not in phs:
            continue
        _, sx, sy, w, h = (int(rn[1:rn.index('x')], 16), int(rn[rn.index('x') + 1:rn.index('y')], 16),
                           int(rn[rn.index('y') + 1:rn.index('w')], 16), int(rn[rn.index('w') + 1:rn.index('h')], 16),
                           int(rn[rn.index('h') + 1:], 16))
        if pal not in pages:  # start from the xBR 4x of the whole page with this palette
            base = rgba_from_idx(idx, pals_raw[phs.index(pal)])
            c4, m4 = xbr4(Image.fromarray(base, 'RGBA'))
            if S != 4:  # xBR gives 4x; bring it to the parts' scale
                k = S // 4
                c4 = np.asarray(Image.fromarray(np.ascontiguousarray(c4)).resize((c4.shape[1] * k, c4.shape[0] * k), Image.LANCZOS))
                m4 = np.asarray(Image.fromarray(np.ascontiguousarray(m4.astype(np.uint8) * 255)).resize(
                    (m4.shape[1] * k, m4.shape[0] * k), Image.NEAREST)) > 127
            pages[pal] = np.dstack([c4, np.where(m4, OPAQUE, 0).astype(np.uint8)])
            cov[pal] = np.zeros(pages[pal].shape[:2], bool)
        part = np.asarray(Image.open(os.path.join(a.parts, f)).convert('RGBA'))
        H, W = min(part.shape[0], h * S), min(part.shape[1], w * S)
        pages[pal][sy * S:sy * S + H, sx * S:sx * S + W] = part[:H, :W]
        cov[pal][sy * S:sy * S + H, sx * S:sx * S + W] |= part[:H, :W, 3] > 0
    if pages and not a.no_recolor:
        derive_palette_pages(pages, cov, idx, pals_raw, phs, S)
    n = 0
    # the page runs from the first use's sy to the bottom of VRAM, so it can be shorter than 256 rows (sets loaded low
    # in VRAM); the set's texels all lie inside it, block rows beyond it stay empty like the other pages of a block
    PH, PW = idx.shape[:2]
    for use in info['uses']:
        for b in use['blocks']:
            # block region inside the page (pages are 64 u16 = 256 px wide; blocks are aligned to them)
            px0 = (b['x'] - use['sx']) * 4
            py0 = b['y'] - use['sy']
            for pal, pg in pages.items():
                y0, y1 = max(0, py0), min(PH, py0 + b['h'])
                x0, x1 = max(0, px0), min(PW, px0 + b['w'] * 4)
                if y1 <= y0 or x1 <= x0:
                    continue
                out = np.zeros((b['h'] * S, b['w'] * 4 * S, 4), np.uint8)
                out[(y0 - py0) * S:(y1 - py0) * S, (x0 - px0) * S:(x1 - px0) * S] = pg[y0 * S:y1 * S, x0 * S:x1 * S]
                Image.fromarray(out, 'RGBA').save(os.path.join(a.out, f"{b['hash']:x}-{pal}.png"))
                # coverage mask next to the staging dir (not installed): merge_shared.py combines files that several
                # sets write under the same name (same VRAM block + palette) keeping every set's redrawn texels
                cm = np.zeros(out.shape[:2], bool)
                cm[(y0 - py0) * S:(y1 - py0) * S, (x0 - px0) * S:(x1 - px0) * S] = cov[pal][y0 * S:y1 * S, x0 * S:x1 * S]
                os.makedirs(a.out + '_cov', exist_ok=True)
                Image.fromarray(cm.astype(np.uint8) * 255, 'L').save(os.path.join(a.out + '_cov', f"{b['hash']:x}-{pal}.png"))
                n += 1
    print(os.path.basename(a.npc_dir), 'pages', len(pages), '->', n, 'block files')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['extract', 'project'])
    ap.add_argument('--user', default=os.path.join(ROOT, 'work', 'disc1_user.bin'))
    ap.add_argument('--maps', default='')
    ap.add_argument('--out', default='')
    ap.add_argument('--npc-dir', default='')
    ap.add_argument('--parts', default='')
    ap.add_argument('--scale', type=int, default=4, choices=[4, 8], help='scale of the redrawn parts and of the written files')
    ap.add_argument('--no-recolor', action='store_true', help='project: no recoloured pages for palettes without redrawn parts')
    a = ap.parse_args()
    (cmd_extract if a.cmd == 'extract' else cmd_project)(a)


if __name__ == '__main__':
    main()
