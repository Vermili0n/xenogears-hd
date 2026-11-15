"""Helpers for the Xenogears MODE2/2352 disc image: user-data access, PSX colors, Beetle hashes."""
import os
import struct
import zlib

import numpy as np
from PIL import Image

SECTOR = 2352
USER = 2048
USER_OFF = 24


class Disc:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        self.sectors = os.path.getsize(path) // SECTOR

    def read(self, sector, offset, length):
        """Read `length` bytes of Form-1 user data starting at sector:offset."""
        out = bytearray()
        sector += offset // USER
        offset %= USER
        while len(out) < length:
            self.f.seek(sector * SECTOR + USER_OFF)
            data = self.f.read(USER)
            out += data[offset:]
            offset = 0
            sector += 1
        return bytes(out[:length])


def clut_from_bytes(b):
    return list(struct.unpack('<16H', b[:32]))


def psx_to_rgba(c):
    """Same conversion Beetle uses when dumping."""
    r = int((c & 0x1f) * 255.0 / 31.0)
    g = int(((c >> 5) & 0x1f) * 255.0 / 31.0)
    b = int(((c >> 10) & 0x1f) * 255.0 / 31.0)
    a = 255 if (c >> 15) == 0 else 127
    if c & 0x8000 == 0 and r == 0 and g == 0 and b == 0:
        a = 0
    return (r, g, b, a)


def beetle_hash(halfwords):
    arr = np.asarray(halfwords, dtype='<u2')
    return zlib.crc32(arr.tobytes()) & 0xffffffff


def png_to_indices(path, clut):
    """Map a dumped 4bpp part back to palette indices (exact color match)."""
    a = np.asarray(Image.open(path).convert('RGBA'))
    lut = {}
    for i, c in enumerate(clut):
        lut.setdefault(psx_to_rgba(c), i)
    h, w = a.shape[:2]
    idx = np.zeros((h, w), np.uint8)
    for y in range(h):
        for x in range(w):
            key = tuple(int(v) for v in a[y, x])
            if key not in lut:
                return None
            idx[y, x] = lut[key]
    return idx


def indices_to_halfwords(idx):
    """4 pixels per u16, low nibble first (PSX 4bpp)."""
    h, w = idx.shape
    hw = []
    for y in range(h):
        for x in range(0, w, 4):
            v = 0
            for p in range(4):
                v |= int(idx[y, x + p]) << (4 * p)
            hw.append(v)
    return hw
