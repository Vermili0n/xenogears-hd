"""Install Elly's walk fix (01.11.2026): the 32 redrawn parts of the map 934/936 copy + closed seams in set 428.

  python elly934_finalize.py [--dry]      (RetroArch closed)
1. copy parts (ai/prod_work/h_elly934/parts_unfilled, sliced from the L40S render): frame-aware seam fill
   (seam_fill.frame_interior over both layouts) -> BC7 -> pack <copy hash>-<pal>.bc7 (replaces the aliases)
2. every pack part of set 428 (original layout): same seam fill, BC7 rebuilt; originals backed up in
   pod/report/seam_fill_backup/.
"""
import argparse
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from seam_fill import BACKUP, fill_interior, frame_interior  # noqa: E402

COPY = os.path.join(ROOT, 'extracted', 'disc1_full', 'elly934')
ORIG = os.path.join(ROOT, 'extracted', 'disc1_full', 'elly')
RAW = os.path.join(ROOT, 'ai', 'prod_work', 'h_elly934', 'parts_unfilled')
S = 8


def write_bc7_from_psx(path, hd):
    lv = [hd.astype(np.uint8)]
    while lv[-1].shape[0] % 2 == 0 and lv[-1].shape[1] % 2 == 0:
        lv.append(bc7pack.gen_mip(lv[-1]))
    l0 = lv[0]
    tr = (l0 == 0).all(-1)
    flags = ((bc7pack.TRANSPARENT if tr.any() else 0) | (bc7pack.OPAQUE if (~tr & (l0[..., 3] == 0)).any() else 0)
             | (bc7pack.SEMI if (l0[..., 3] == 255).any() else 0))
    enc, failed, _ = bc7pack.encode_levels(lv)
    if failed:
        return False
    with open(path + '.tmp', 'wb') as f:
        f.write(bc7pack.pack_file(enc, l0.shape[1], l0.shape[0], flags))
    os.replace(path + '.tmp', path)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    lay_c = json.load(open(os.path.join(COPY, 'layout.json')))['428_0']
    lay_o = json.load(open(os.path.join(ORIG, 'layout.json')))['428_0']
    inner = frame_interior([(lay_c, COPY), (lay_o, ORIG)], lambda h, k: os.path.join(h, 'parts'))
    copy = json.load(open(os.path.join(COPY, 'copy_map.json')))
    os.makedirs(BACKUP, exist_ok=True)
    n1 = 0
    for f in sorted(os.listdir(RAW)):
        blk, pal = f[:-4].split('-')
        if not f.endswith('.png') or blk not in copy:
            continue
        rgba = np.asarray(Image.open(os.path.join(RAW, f)).convert('RGBA')).astype(np.int16)
        rgba, _ = fill_interior(rgba, None, S, rgba[..., 3] == 0, inner.get((blk, pal)))
        lv, flags = bc7pack.levels_of(np.ascontiguousarray(rgba.astype(np.uint8)))
        enc, failed, _ = bc7pack.encode_levels(lv)
        if failed:
            print('BC7 rules failed:', f)
            continue
        if not a.dry:
            dst = os.path.join(PACK, f[:-4] + '.bc7')
            with open(dst + '.tmp', 'wb') as fo:
                fo.write(bc7pack.pack_file(enc, rgba.shape[1], rgba.shape[0], flags))
            os.replace(dst + '.tmp', dst)
        n1 += 1
    print(f'copy parts installed: {n1}', flush=True)
    pals = lay_o['palettes']
    used = sorted({(p['block'], pals[min(p['clut'], len(pals) - 1)]) for fr in lay_o['frames'] for p in fr})
    n2 = px = 0
    for blk, pal in used:
        path = os.path.join(PACK, f'{blk}-{pal}.bc7')
        if (blk, pal) not in inner or not os.path.exists(path):
            continue
        hd = read_bc7_level0(path).astype(np.int16)
        out, k = fill_interior(hd, None, S, (hd == 0).all(-1), inner[(blk, pal)])
        if not k:
            continue
        out[..., :3][(out[..., :3] == 0).all(-1) & ~(out == 0).all(-1)] = 1
        px += k
        n2 += 1
        if a.dry:
            continue
        if not os.path.exists(os.path.join(BACKUP, os.path.basename(path))):
            shutil.copyfile(path, os.path.join(BACKUP, os.path.basename(path)))
        write_bc7_from_psx(path, out)
    print(f'set 428 parts with seams closed: {n2} ({px} HD px)' + (' (dry run)' if a.dry else ''))


if __name__ == '__main__':
    main()
