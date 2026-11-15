"""PNG pack -> BC7 pack for the Xenogears HD core (30.10.2026).

Each <hash>-<pal>.png becomes <hash>-<pal>.bc7: the same level chain the core builds from the PNG
(rhi_tt.c convert_tri_to_psx + generate_mip, reproduced bit for bit), every level BC7-encoded by xbc7.dll
(bc7enc + rule-keeping fallback, see xbc7.cpp), zlib-compressed. The core uploads the blocks as
VK_FORMAT_BC7_UNORM_BLOCK: 4x less VRAM than RGBA8.

File: 32-byte header  'XBC7' u32 version=1, u32 width, u32 height, u32 levels, u32 alpha_flags,
      u32 raw_size (bytes of all levels' blocks), u32 flags (1 = zlib)  + payload.

  python bc7pack.py sample --n 40                     quality/size/time on random pack files (no writes)
  python bc7pack.py convert --src <pack> --dst <dir>  convert every PNG not converted yet (resumable);
                                                      textures that cannot keep the rules stay PNG (listed)
"""
import argparse
import ctypes
import json
import os
import random
import struct
import sys
import time
import zlib
from multiprocessing import Pool

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.environ.get('XENO_PACK', 'pack')    # the pack folder: XENO_PACK or --src
OPAQUE, SEMI, TRANSPARENT = 1, 2, 4
MAGIC, VERSION = b'XBC7', 1
_dll = None


def dll():
    global _dll
    if _dll is None:
        _dll = ctypes.CDLL(os.path.join(HERE, 'xbc7.dll'))
        _dll.xbc7_init(1, 0)    # uber level 1, linear RGB weights
    return _dll


def tri_to_psx(im):
    """rhi_tt.c convert_tri_to_psx: alpha 0 -> (0,0,0,0); 255 -> (rgb,0); else (rgb,255); black rgb -> 1,1,1."""
    a = im[..., 3]
    t, o = a == 0, a == 255
    s = ~t & ~o
    out = im.copy()
    out[(out[..., :3] == 0).all(-1) & ~t, :3] = 1
    out[..., 3] = np.where(s, 255, 0)
    out[t] = 0
    flags = (TRANSPARENT if t.any() else 0) | (OPAQUE if o.any() else 0) | (SEMI if s.any() else 0)
    return out, flags


def gen_mip(p):
    """rhi_tt.c generate_mip: 2x2 average of the non-transparent texels; 3+ transparent -> transparent."""
    q = [p[0::2, 0::2], p[0::2, 1::2], p[1::2, 0::2], p[1::2, 1::2]]
    nt = sum((x == 0).all(-1).astype(np.int32) for x in q)
    s = sum(x.astype(np.int32) for x in q)
    cnt = np.maximum(4 - nt, 1)[..., None]
    out = (s // cnt).astype(np.uint8)
    out[nt > 2] = 0
    return out


def levels_of(rgba):
    psx, flags = tri_to_psx(rgba)
    lv = [psx]
    while lv[-1].shape[0] % 2 == 0 and lv[-1].shape[1] % 2 == 0:
        lv.append(gen_mip(lv[-1]))
    return lv, flags


def encode_levels(lv):
    stats = (ctypes.c_int64 * 6)()
    parts, failed = [], 0
    for p in lv:
        h, w = p.shape[:2]
        p = np.ascontiguousarray(p)
        out = ctypes.create_string_buffer(((w + 3) // 4) * ((h + 3) // 4) * 16)
        failed += dll().xbc7_encode(p.ctypes.data_as(ctypes.c_void_p), w, h, out, stats)
        parts.append(out.raw)
    return parts, failed, list(stats)


def decode_level(blocks, w, h):
    out = np.zeros((h, w, 4), np.uint8)
    dll().xbc7_decode(blocks, w, h, out.ctypes.data_as(ctypes.c_void_p))
    return out


def pack_file(parts, w, h, flags):
    raw = b''.join(parts)
    return struct.pack('<4s7I', MAGIC, VERSION, w, h, len(parts), flags, len(raw), 1) + zlib.compress(raw, 6)


def convert_one(args):
    src, dst = args
    try:
        rgba = np.asarray(Image.open(src).convert('RGBA'))
        lv, flags = levels_of(rgba)
        parts, failed, st = encode_levels(lv)
        if failed:
            return src, 'kept_png', failed, st
        data = pack_file(parts, rgba.shape[1], rgba.shape[0], flags)
        tmp = dst + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, dst)
        return src, 'ok', len(data), st
    except Exception as ex:  # noqa: BLE001
        return src, 'error', repr(ex)[:200], None


def cmd_sample(a):
    names = sorted(e.name for e in os.scandir(a.src) if e.name.endswith('.png'))
    random.seed(a.seed)
    pick = random.sample(names, a.n)
    tot = {'png': 0, 'bc7': 0, 'raw': 0, 'rgba': 0, 't': 0.0}
    st_all = [0] * 6
    worst = []
    for n in pick:
        p = os.path.join(a.src, n)
        t0 = time.time()
        rgba = np.asarray(Image.open(p).convert('RGBA'))
        lv, flags = levels_of(rgba)
        parts, failed, st = encode_levels(lv)
        dt = time.time() - t0
        st_all = [x + y for x, y in zip(st_all, st)]
        data = pack_file(parts, rgba.shape[1], rgba.shape[0], flags)
        # verify level 0: rules + PSNR on the non-transparent texels
        d0 = decode_level(parts[0], rgba.shape[1], rgba.shape[0])
        ref = lv[0]
        tr, dtr = (ref == 0).all(-1), (d0 == 0).all(-1)
        rule = int((tr != dtr).sum()) + int(((ref[..., 3] >= 128) != (d0[..., 3] >= 128)).sum())
        m = ~tr
        mse = float(((d0[m][:, :3].astype(np.float64) - ref[m][:, :3]) ** 2).mean()) if m.any() else 0.0
        psnr = 99.0 if mse == 0 else 10 * np.log10(255 ** 2 / mse)
        tot['png'] += os.path.getsize(p); tot['bc7'] += len(data); tot['raw'] += sum(map(len, parts))
        tot['rgba'] += sum(x.size for x in lv); tot['t'] += dt
        worst.append((psnr, n, rgba.shape[1], rgba.shape[0], rule, failed))
    worst.sort()
    print(f"{a.n} files: png {tot['png']/1e6:.1f} MB -> bc7 file {tot['bc7']/1e6:.1f} MB (raw blocks {tot['raw']/1e6:.1f} MB, "
          f"VRAM was {tot['rgba']/1e6:.1f} MB); {tot['t']:.1f} s ({tot['t']/a.n*1000:.0f} ms/file, 1 thread)")
    print('blocks: total {} empty {} bc7enc {} own-m6 {} own-m5 {} own-m4 {}'.format(*st_all))
    print('worst PSNR (dB, file, w, h, rule violations, failed blocks):')
    for x in worst[:8]:
        print('  %.1f %s %dx%d %d %d' % x)
    print('median PSNR %.1f dB; rule violations total %d' % (worst[len(worst) // 2][0], sum(x[4] for x in worst)))


def cmd_convert(a):
    os.makedirs(a.dst, exist_ok=True)
    have = {e.name: e.stat().st_mtime for e in os.scandir(a.dst) if e.name.endswith('.bc7')}
    todo = [(e.path, os.path.join(a.dst, e.name[:-4] + '.bc7')) for e in os.scandir(a.src)
            if e.name.endswith('.png') and have.get(e.name[:-4] + '.bc7', -1) < e.stat().st_mtime]   # new or re-installed PNG
    print(f'{len(todo)} PNG to convert', flush=True)
    kept, errors, t0, nb, st_all = [], [], time.time(), 0, [0] * 6
    with Pool(a.workers) as pool:
        for k, (src, res, info, st) in enumerate(pool.imap_unordered(convert_one, todo, chunksize=16), 1):
            if res == 'ok':
                nb += info
                st_all = [x + y for x, y in zip(st_all, st)]
            elif res == 'kept_png':
                kept.append(os.path.basename(src))
            else:
                errors.append((os.path.basename(src), info))
            if k % 5000 == 0 or k == len(todo):
                el = time.time() - t0
                print(f'  {k}/{len(todo)} {el:.0f} s, ETA {el / k * (len(todo) - k) / 60:.0f} min, bc7 {nb/1e9:.2f} GB, '
                      f'kept png {len(kept)}, errors {len(errors)}', flush=True)
    rep = {'blocks': st_all, 'kept_png': kept, 'errors': errors}
    json.dump(rep, open(os.path.join(a.dst, '_bc7pack_report.json'), 'w'), indent=1)
    print('done; blocks total/empty/bc7enc/m6/m5/m4:', st_all, 'kept png', len(kept), 'errors', len(errors))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['sample', 'convert'])
    ap.add_argument('--src', default=PACK)
    ap.add_argument('--dst', required=True)
    ap.add_argument('--n', type=int, default=40)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 4) - 2))
    a = ap.parse_args()
    cmd_sample(a) if a.cmd == 'sample' else cmd_convert(a)


if __name__ == '__main__':
    sys.exit(main())
