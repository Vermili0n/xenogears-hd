"""Pre-shrink HD pack textures that the custom core would cap anyway (sides > 2048) - same result, 4-16x less to decode.

  python pack_shrink.py [--workers 4] [--dry]
The core uploads the first mip level with both sides <= 2048 (tt_upload_levels_id); mip levels halve with integer
division, so the file is reduced by the same power of two with a box filter (PIL reduce = 2x2.. averaging).
Originals are moved to BACKUP first (same drive, nothing deleted); a file already in BACKUP is never overwritten.
Our own sprite parts (_installed_sprite_parts.txt) are never touched.
"""
import argparse
import os
import shutil
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image

PACK = r'<RETROARCH_DRIVE>\RetroArch\system\Xenogears (USA)-texture-replacements'  # SSD since 29.10 (core option HD Texture Folder = System)
BACKUP = r'<DATA_DRIVE>\XenogearsHD_CD1+CD2\backup_pack_large'
OURS = r'<DATA_DRIVE>\XenogearsHD_CD1+CD2\backup_replaced_by_sprites\_installed_sprite_parts.txt'
CAP = 2048


def halvings(w, h):
    """How many times the core's mip chain halves before both sides fit (the chain stops at an odd side)."""
    n = 0
    while max(w, h) > CAP and w % 2 == 0 and h % 2 == 0:
        w, h, n = w // 2, h // 2, n + 1
    return n


def core_mip(a):
    """One level of the core's generate_mip (rhi_tt.c) in PNG alpha terms: a 2x2 block with > 2 fully transparent
    pixels is transparent; otherwise RGB = mean of the non-transparent pixels, and the block is opaque unless its
    semi-transparent pixels dominate (the core averages its own opaque=0 / semi=255 alpha codes)."""
    h, w = a.shape[0] // 2, a.shape[1] // 2
    q = a[:h * 2, :w * 2].reshape(h, 2, w, 2, 4).transpose(0, 2, 1, 3, 4).reshape(h, w, 4, 4).astype(np.int32)
    tr = q[..., 3] == 0
    nt = 4 - tr.sum(-1)
    keep = ~tr
    rgb = (q[..., :3] * keep[..., None]).sum(2) // np.maximum(nt, 1)[..., None]
    semi = keep & (q[..., 3] < 255)
    nsemi = semi.sum(-1)
    semi_a = (q[..., 3] * semi).sum(-1) // np.maximum(nsemi, 1)
    alpha = np.where(255 * nsemi / np.maximum(nt, 1) < 128, 255, semi_a)
    out = np.zeros((h, w, 4), np.uint8)
    ok = nt >= 2
    out[ok, :3] = rgb[ok]
    out[ok, 3] = alpha[ok]
    return out


def work(name):
    src = os.path.join(PACK, name)
    try:
        with Image.open(src) as im:
            w, h = im.size
            n = halvings(w, h)
            if n == 0:
                return name, 0, None
            a = np.asarray(im.convert('RGBA'))
        for _ in range(n):
            a = core_mip(a)
        bk = os.path.join(BACKUP, name)
        if not os.path.exists(bk):
            shutil.copy2(src, bk)
        tmp = src + '.tmp'
        Image.fromarray(a, 'RGBA').save(tmp, 'PNG', compress_level=6)
        os.replace(tmp, src)
        return name, 2 ** n, a.shape[1::-1]
    except Exception as e:  # noqa: BLE001
        return name, -1, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    os.makedirs(BACKUP, exist_ok=True)
    ours = set(open(OURS).read().split()) if os.path.exists(OURS) else set()
    names = [f for f in os.listdir(PACK) if f.lower().endswith('.png') and f not in ours]
    if a.dry:
        n = 0
        for f in names:
            with Image.open(os.path.join(PACK, f)) as im:
                if halvings(*im.size) > 0:
                    n += 1
        print('would shrink', n, 'of', len(names))
        return
    done = errs = 0
    with Pool(a.workers) as pool:
        for k, (name, f, info) in enumerate(pool.imap_unordered(work, names, chunksize=64)):
            if f > 1:
                done += 1
            elif f < 0:
                errs += 1
                print('ERROR', name, info, flush=True)
            if (k + 1) % 5000 == 0:
                print('checked', k + 1, '/', len(names), 'shrunk', done, 'errors', errs, flush=True)
    print('DONE shrunk', done, 'errors', errs, 'of', len(names), flush=True)


if __name__ == '__main__':
    sys.exit(main())
