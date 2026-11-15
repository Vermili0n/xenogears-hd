r"""Gear battle HUD (item 13): the HUD upload 49b52d64 (64x204 units at VRAM 960,52; page 960,0) and its CLUTs from the
cockpit VRAM dump of the other worker (xeno_port\out\fix_1115\H\vram_cockpit.0: 1024 units x 1024 rows, 16-bit LE)."""
import os
import zlib

import numpy as np

from gcommon import HERE  # noqa: F401
from render_frames import psx_to_rgba

H_DIR = r'<XENO_PORT>\out\fix_1115\H'
UX, UY, UW, UH = 960, 52, 64, 204
PAGE_Y = 0


def vram():
    return np.fromfile(os.path.join(H_DIR, 'vram_cockpit.0'), '<u2').reshape(-1, 1024)


def upload_words(v):
    return v[UY:UY + UH, UX:UX + UW]


def idx4(words):
    out = np.zeros((words.shape[0], words.shape[1] * 4), np.uint8)
    for k in range(4):
        out[:, k::4] = (words >> (4 * k)) & 15
    return out


def idx8(words):
    out = np.zeros((words.shape[0], words.shape[1] * 2), np.uint8)
    out[:, 0::2] = words & 255
    out[:, 1::2] = words >> 8
    return out


def clut(v, x, y, n):
    return v[y, x:x + n].copy()


def crc(a):
    return f'{zlib.crc32(np.ascontiguousarray(a).astype("<u2").tobytes()) & 0xffffffff:x}'


def pal_rgba(row):
    return np.array([psx_to_rgba(int(c)) for c in row], np.uint8)
