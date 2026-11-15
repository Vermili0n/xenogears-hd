"""A pack picture .bc7 -> .png, to look at it and to edit it.

  python bc7_to_png.py <file.bc7 or folder> [--out <folder>]

The pack's .bc7 file: a 32-byte header ('XBC7', version, width, height, levels, alpha flags, raw size, flags: 1 = zlib)
and the BC7 blocks of every mip level. Level 0 is decoded by xbc7.dll (xbc7.cpp, built as README.md says) and written
as a PNG in the convention the pack's PNG files use:
  alpha 0   - transparent;
  alpha 255 - opaque;
  alpha 128 - a texel the game blends (the PlayStation's semi-transparency bit); any alpha between 1 and 254 means it.
The port reads a .png of the same name before the .bc7, so an edited PNG put beside the .bc7 is what the game shows.
"""
import argparse
import ctypes
import os
import struct
import sys
import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def decode(path, dll):
    data = open(path, 'rb').read()
    magic, _version, width, height, _levels, _alpha, _raw_size, flags = struct.unpack('<4s7I', data[:32])
    if magic != b'XBC7':
        raise ValueError('not an XBC7 file')
    raw = zlib.decompress(data[32:]) if flags & 1 else data[32:]
    psx = np.zeros((height, width, 4), np.uint8)
    dll.xbc7_decode(raw[:((width + 3) // 4) * ((height + 3) // 4) * 16], width, height, psx.ctypes.data_as(ctypes.c_void_p))
    # The core's convention back to the PNG's: (0,0,0,0) transparent; (r,g,b,0) opaque; (r,g,b,255) blended.
    transparent = ~psx.any(axis=-1)
    blended = psx[..., 3] > 127
    out = psx.copy()
    out[..., 3] = np.where(transparent, 0, np.where(blended, 128, 255))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('source')
    parser.add_argument('--out', default=None, help='where the PNG files go (default: beside the .bc7)')
    args = parser.parse_args()
    dll = ctypes.CDLL(os.path.join(HERE, 'xbc7.dll'))
    if os.path.isdir(args.source):
        files = sorted(os.path.join(args.source, name) for name in os.listdir(args.source) if name.endswith('.bc7'))
    else:
        files = [args.source]
    for path in files:
        folder = args.out or os.path.dirname(path)
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, os.path.splitext(os.path.basename(path))[0] + '.png')
        try:
            Image.fromarray(decode(path, dll), 'RGBA').save(target)
        except (ValueError, zlib.error, struct.error) as error:
            print(f'{path}: {error}', file=sys.stderr)
            continue
        print(target)


if __name__ == '__main__':
    main()
