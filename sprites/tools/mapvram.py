"""Map texture files (odd file N+1 of a map pair) -> VRAM image + the list of upload blocks, after rufaswan's
xeno_map2battle.php: chunks with type 0x1200/0x1201, header (bx, by, dx, dy, w) and per-block row counts at 0x1c;
data in 0x800-byte blocks. Each block is one LoadImage on the PS1, so Beetle names it crc32(block u16 data).

Map data file N (even): first bytes = 8-byte entries per field sprite set (sx, sy, ?, ty at byte 6);
ty 1 = sprite texture page lives in VRAM at (sx, sy), 64x256 u16 (256x256 4bpp pixels).
"""
import struct
import zlib

import numpy as np

VRAM_W, VRAM_H = 1024, 512


def parse_vram_file(d):
    """-> (vram uint16 [512,1024], blocks: list of dict(x, y, w, h, hash, off))"""
    vram = np.zeros((VRAM_H, VRAM_W), np.uint16)
    blocks = []
    pos = 0
    while pos + 0x20 <= len(d):
        t = struct.unpack_from('<I', d, pos)[0]
        if t not in (0x1200, 0x1201):
            break
        bx, by, dx, dy, w = struct.unpack_from('<5H', d, pos + 4)
        no = struct.unpack_from('<H', d, pos + 0x18)[0]
        heights = struct.unpack_from(f'<{no}H', d, pos + 0x1c)
        y = by + dy
        x = bx + dx
        for i, h in enumerate(heights):
            off = pos + 0x800 + i * 0x800
            raw = d[off:off + h * w * 2]
            if len(raw) < h * w * 2 or h == 0:
                continue
            a = np.frombuffer(raw, '<u2').reshape(h, w)
            if y + h <= VRAM_H and x + w <= VRAM_W:
                vram[y:y + h, x:x + w] = a
            blocks.append({'x': x, 'y': y, 'w': w, 'h': h, 'hash': zlib.crc32(raw) & 0xffffffff, 'off': off})
            y += h
        pos += 0x800 + no * 0x800
    return vram, blocks


def set_entries(map_raw, count):
    """8-byte sprite-set entries at the start of the map data file."""
    out = []
    for i in range(count):
        sx, sy = struct.unpack_from('<HH', map_raw, i * 8)
        out.append({'sx': sx, 'sy': sy, 'ty': map_raw[i * 8 + 6], 'raw': bytes(map_raw[i * 8:i * 8 + 8])})
    return out


def page_indices(vram, sx, sy, w16=64, h=256):
    """4bpp indices of a VRAM page (w16 u16 wide) -> uint8 [h, w16*4]."""
    a = vram[sy:sy + h, sx:sx + w16]
    idx = np.zeros((a.shape[0], a.shape[1] * 4), np.uint8)
    for k in range(4):
        idx[:, k::4] = (a >> (4 * k)) & 15
    return idx
