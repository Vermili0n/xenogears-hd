"""NPC sprite sets with a 256x256 texture page (p256 meta, field archive sub-file 3), after rufaswan's
quad_xeno_battle_2d.php: sub-file header = num, b04, then 12-byte entries (meta offset, texture-list offset, ?);
texture list = num + offsets, each image = (w in u16, h) + 4bpp pixels; a part = 5-byte record (tex id << 1, sx, sy, w, h).
"""
import struct
import zlib

import numpy as np


def u24(b, o):
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)


def sets_in_sub(d):
    """-> list of (meta_off, tex_off) for every sprite set in a field sprite sub-file."""
    num, b04 = u24(d, 0), u24(d, 4)
    out = []
    if num <= 0 or num > 256:
        return out
    for i in range(num):
        off = 8 + i * 12
        if off + 8 > len(d):
            break
        met, tex = u24(d, off), u24(d, off + 4)
        if tex >= b04 and tex < len(d) and met < len(d):
            out.append((met, tex))
    return out


def textures(d, tex_off):
    """-> list of dicts(w_px, h, raw bytes, idx uint8 HxW) of the 4bpp texture images."""
    n = u24(d, tex_off)
    out = []
    for i in range(n):
        pos = u24(d, tex_off + 4 + i * 4)
        o = tex_off + pos
        w, h = struct.unpack_from('<HH', d, o)
        raw = bytes(d[o + 4:o + 4 + w * h * 2])
        a = np.frombuffer(raw, np.uint8)
        idx = np.empty(a.size * 2, np.uint8)
        idx[0::2] = a & 15
        idx[1::2] = a >> 4
        out.append({'w': w * 4, 'h': h, 'wu16': w, 'raw': raw, 'idx': idx.reshape(h, w * 4),
                    'hash': zlib.crc32(raw) & 0xffffffff})
    return out


def part_rect(meta, ref):
    """5-byte part record -> (tex id, sx, sy, w, h)."""
    r = meta[ref:ref + 5]
    return r[0] >> 1, r[1], r[2], r[3], r[4]
