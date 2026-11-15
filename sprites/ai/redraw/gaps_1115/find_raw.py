r"""Find VRAM uploads (crc32 of their words) in the disc's files: plain files, map archives' sub-files (LZSS), TIMs.
  python find_raw.py <disc usa|rus1|rus2> <w units> <h> <crc hex> [...]   (w, h: upload size in 16-bit units)"""
import mmap
import os
import struct
import sys
import zlib

from gcommon import ROOT, rus_disc
from xfs import field_archive_index, get_file, lzss_decompress, read_toc


def main():
    disc, specs = sys.argv[1], sys.argv[2:]
    wanted, sizes = {}, {}
    for k in range(0, len(specs), 3):
        w, h = int(specs[k]), int(specs[k + 1])
        wanted.setdefault(w * h * 2, set()).add(int(specs[k + 2], 16))
        sizes.setdefault(w * h * 2, set()).add((w, h))
    if disc == 'usa':
        fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        toc = read_toc(mm)
    else:
        mm, toc = rus_disc(int(disc[-1]))
    for n, e in enumerate(toc):
        if e['is_dir'] or e['size'] <= 0:
            continue
        d = get_file(mm, e)
        bufs = [('plain', d)]
        try:
            for k, x in enumerate(field_archive_index(d)):
                if 0 < x['size'] < 4 << 20 and 0 <= x['offset'] < x['end'] <= len(d):
                    bufs.append((f'sub{k}', lzss_decompress(d[x['offset']:x['end']])[0][:x['size']]))
        except Exception:  # noqa: BLE001
            pass
        for tag, b in bufs:
            for size, ws in wanted.items():
                # an image of a TIM (or a sprite sheet item) follows its u16 w, h: look there only
                for w, h in sizes[size]:
                    key = struct.pack('<HH', w, h)
                    o = b.find(key)
                    while o >= 0:
                        c = zlib.crc32(b[o + 4:o + 4 + size]) & 0xffffffff
                        if c in ws:
                            print(f'file {n} {tag} offset {o + 4:#x}: {c:x}', flush=True)
                        o = b.find(key, o + 1)
        if n % 400 == 0:
            print(f'... {n}', flush=True)


if __name__ == '__main__':
    main()
