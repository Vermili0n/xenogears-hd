"""Close HD seams between sprite parts (30.10, Elly's walk: dark lines through her hair).

The redraw is a little thinner than the pixel silhouette, and slicing keeps the redraw's own transparency, so many
parts have transparent HD pixels inside their own opaque texels (1158 of the 1179 parts of Elly's set 428). On the
outer silhouette that is just the smooth edge, but where a part meets the next one inside the figure the background
shows through as a dark line. Here only "interior" texels are filled: opaque texels whose 8 neighbours inside the part
are opaque too (a neighbour beyond the part's rectangle counts as opaque - the next part continues there), so the
outer silhouette keeps its smooth redraw edge. The hole pixels get the colour of the nearest drawn pixels (inpaint).

  fill_interior(rgba, texel_mask, S, transparent=...) -> (rgba, filled px)    (library)
  python seam_fill.py --hero elly --set 428_0 [--dry]                         pack BC7 files of the set's parts
Backups of rewritten pack files: pod/report/seam_fill_backup/.
"""
import argparse
import json
import os
import shutil
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
sys.path.insert(0, HERE)
import bc7pack  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402

BACKUP = os.path.join(ROOT, 'pod', 'report', 'seam_fill_backup')


def interior_texels(mask):
    m = np.pad(mask, 1, constant_values=True)       # beyond the rectangle: the next part
    inner = mask.copy()
    h, w = mask.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            inner &= m[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
    return inner


def frame_interior(layouts, parts_dir_of):
    """{(block, pal): texel mask} - texels of a part that lie inside the figure (all 8 neighbours opaque in the
    assembled pixel frame) in at least one frame that uses the part. layouts: [(layout set dict, hero dir)]."""
    out = {}
    for lay, hdir in layouts:
        pals = lay['palettes']
        masks = {}
        for f in lay['frames']:
            pl = []
            for p in f:
                pal = pals[min(p['clut'], len(pals) - 1)]
                key = (p['block'], pal)
                if key not in masks:
                    path = os.path.join(parts_dir_of(hdir, key), f'{p["block"]}-{pal}.png')
                    masks[key] = np.asarray(Image.open(path).convert('RGBA'))[..., 3] > 0 if os.path.exists(path) else None
                m = masks[key]
                if m is None:
                    continue
                if p['flipx']:
                    m = m[:, ::-1]
                if p['flipy']:
                    m = m[::-1]
                pl.append((p['dx'] + p['mx'], p['dy'] + p['my'], m, key, p))
            if not pl:
                continue
            x0 = min(x for x, _, _, _, _ in pl)
            y0 = min(y for _, y, _, _, _ in pl)
            W = max(x + m.shape[1] for x, _, m, _, _ in pl) - x0
            H = max(y + m.shape[0] for _, y, m, _, _ in pl) - y0
            cov = np.zeros((H, W), bool)
            for x, y, m, _, _ in pl:
                cov[y - y0:y - y0 + m.shape[0], x - x0:x - x0 + m.shape[1]] |= m
            pad = np.pad(cov, 1, constant_values=False)
            inner = cov.copy()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    inner &= pad[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]
            for x, y, m, key, p in pl:
                part_inner = inner[y - y0:y - y0 + m.shape[0], x - x0:x - x0 + m.shape[1]] & m
                if p['flipx']:
                    part_inner = part_inner[:, ::-1]
                if p['flipy']:
                    part_inner = part_inner[::-1]
                out[key] = out.get(key, np.zeros_like(part_inner)) | part_inner
    return out


def fill_interior(rgba, mask, S, empty, inner=None):
    """rgba: HD part (H x W x 4, int), mask: texel opacity, empty: HD pixels that are transparent; inner: texels to
    cover fully (default: the part's own interior texels)."""
    up = np.repeat(np.repeat(interior_texels(mask) if inner is None else inner, S, 0), S, 1)
    if up.shape != empty.shape:
        return rgba, 0
    hole = up & empty
    if not hole.any():
        return rgba, 0
    rgb = np.ascontiguousarray(np.clip(rgba[..., :3], 0, 255).astype(np.uint8))
    fill = cv2.inpaint(rgb, ((hole | empty) * 255).astype(np.uint8), 3, cv2.INPAINT_TELEA)
    # alpha / flags of the nearest drawn pixel (128 = PS1 STP in the PNG convention, 0/255 in the core's)
    _, lab = cv2.distanceTransformWithLabels((~empty).astype(np.uint8) ^ 1, cv2.DIST_L2, 3,
                                            labelType=cv2.DIST_LABEL_PIXEL)
    src = np.zeros((lab.max() + 1, 2), np.int32)
    ys, xs = np.nonzero(~empty)
    src[lab[ys, xs]] = np.stack([ys, xs], 1)
    out = rgba.copy()
    out[hole, :3] = fill[hole]
    ny, nx = src[lab[hole], 0], src[lab[hole], 1]
    out[hole, 3] = rgba[ny, nx, 3]
    return out, int(hole.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', required=True)
    ap.add_argument('--set', required=True)
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    hdir = os.path.join(ROOT, 'extracted', 'disc1_full', a.hero)
    lay = json.load(open(os.path.join(hdir, 'layout.json')))[a.set]
    pals = lay['palettes']
    used = sorted({(p['block'], pals[min(p['clut'], len(pals) - 1)]) for f in lay['frames'] for p in f})
    os.makedirs(BACKUP, exist_ok=True)
    tot = files = 0
    for blk, pal in used:
        path = os.path.join(PACK, f'{blk}-{pal}.bc7')
        if not os.path.exists(path):
            continue
        mask = np.asarray(Image.open(os.path.join(hdir, 'parts', f'{blk}-{pal}.png')).convert('RGBA'))[..., 3] > 0
        hd = read_bc7_level0(path).astype(np.int16)                 # core convention
        S = hd.shape[1] // mask.shape[1]
        if S < 1 or hd.shape[0] != mask.shape[0] * S:
            continue
        out, n = fill_interior(hd, mask, S, (hd == 0).all(-1))
        if not n:
            continue
        out[..., :3][(out[..., :3] == 0).all(-1) & ~(out == 0).all(-1)] = 1
        tot += n
        files += 1
        if a.dry:
            continue
        if not os.path.exists(os.path.join(BACKUP, os.path.basename(path))):
            shutil.copyfile(path, os.path.join(BACKUP, os.path.basename(path)))
        lv = [out.astype(np.uint8)]
        while lv[-1].shape[0] % 2 == 0 and lv[-1].shape[1] % 2 == 0:
            lv.append(bc7pack.gen_mip(lv[-1]))
        l0 = lv[0]
        tr = (l0 == 0).all(-1)
        flags = ((bc7pack.TRANSPARENT if tr.any() else 0) | (bc7pack.OPAQUE if (~tr & (l0[..., 3] == 0)).any() else 0)
                 | (bc7pack.SEMI if (l0[..., 3] == 255).any() else 0))
        enc, failed, _ = bc7pack.encode_levels(lv)
        if failed:
            continue
        with open(path + '.tmp', 'wb') as f:
            f.write(bc7pack.pack_file(enc, l0.shape[1], l0.shape[0], flags))
        os.replace(path + '.tmp', path)
    print(f'{a.hero} {a.set}: {files} files, {tot} HD px filled' + (' (dry run)' if a.dry else ''))


if __name__ == '__main__':
    main()
