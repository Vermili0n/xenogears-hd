r"""The field's system images (directory 4 file 0xA7 = disc file 589: compass, particles, ...) -> PNGs in sysimg\."""
import mmap
import os
import struct
import zlib

import numpy as np
from PIL import Image

from gcommon import HERE, ROOT
from faces import tim
from render_frames import psx_to_rgba
from xfs import get_file, read_toc

FILE = 589


def images():
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    d = get_file(mm, read_toc(mm)[FILE])
    offs = struct.unpack_from('<9I', d, 0)
    out = []
    for k, o in enumerate(offs[1:]):
        t = tim(d[o:])
        if not t:
            continue
        clut, (x, y, w, h, raw), bpp = t
        words = np.frombuffer(clut[4], '<u2').reshape(clut[3], clut[2]) if clut else None
        if bpp == 1:
            idx = np.frombuffer(raw, np.uint8).reshape(h, w * 2)
        else:
            b = np.frombuffer(raw, np.uint8)
            idx = np.empty(b.size * 2, np.uint8)
            idx[0::2], idx[1::2] = b & 15, b >> 4
            idx = idx.reshape(h, w * 4)
        out.append({'k': k, 'name': f'{zlib.crc32(raw) & 0xffffffff:x}', 'bpp': bpp, 'idx': idx, 'clut': words,
                    'place': (x, y, w, h)})
    return out


def rgba(idx, clut_row):
    pal = np.array([psx_to_rgba(int(c)) for c in clut_row], np.uint8)
    return pal[idx]


if __name__ == '__main__':
    os.makedirs(os.path.join(HERE, 'sysimg'), exist_ok=True)
    for im in images():
        row = im['clut'][0]
        cname = f'{zlib.crc32(row[:16].astype("<u2").tobytes()) & 0xffffffff:x}' if im['bpp'] == 0 else f'{zlib.crc32(row.astype("<u2").tobytes()) & 0xffffffff:x}'
        a = rgba(im['idx'], row[:256] if im['bpp'] else row[:16])
        Image.fromarray(np.repeat(np.repeat(a, 4, 0), 4, 1)).save(os.path.join(HERE, 'sysimg', f'{im["k"]}_{im["name"]}.png'))
        print(im['k'], im['name'], im['bpp'], im['idx'].shape, 'own clut', cname, 'rows', im['clut'].shape)
