r"""Dialogue portraits (faces) of a disc: TIM files of the field's face directory -> Beetle upload names.
  python faces.py   -> faces_<disc>.json and the count against the pack"""
import json
import mmap
import os
import struct
import sys
import zlib

from gcommon import HERE, ROOT, pack_names, rus_disc
from xfs import get_file, read_toc


def tim(d):
    """-> (clut rows [(x, y, w, h, raw)], image (x, y, w, h, raw), bpp) of a TIM, or None."""
    if len(d) < 20 or struct.unpack_from('<I', d, 0)[0] != 0x10:
        return None
    flag = struct.unpack_from('<I', d, 4)[0]
    if flag & ~0xf or (flag & 7) > 3:
        return None
    p, clut = 8, None
    if flag & 8:
        n = struct.unpack_from('<I', d, p)[0]
        x, y, w, h = struct.unpack_from('<4H', d, p + 4)
        clut = (x, y, w, h, d[p + 12:p + 12 + w * h * 2])
        p += n
    n = struct.unpack_from('<I', d, p)[0]
    x, y, w, h = struct.unpack_from('<4H', d, p + 4)
    raw = d[p + 12:p + 12 + w * h * 2]
    if len(raw) != w * h * 2 or not w or not h:
        return None
    return clut, (x, y, w, h, raw), flag & 7


def main():
    out = {}
    have = pack_names()
    for disc in ('usa', 'rus1', 'rus2'):
        if disc == 'usa':
            fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
            mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            toc = read_toc(mm)
        else:
            mm, toc = rus_disc(int(disc[-1]))
        for n, e in enumerate(toc):
            if e['is_dir'] or not 0 < e['size'] <= 0x8000:
                continue
            t = tim(get_file(mm, e))
            if not t or t[0] is None or t[2] != 1:
                continue
            clut, (x, y, w, h, raw), bpp = t
            cname = zlib.crc32(clut[4][:512]) & 0xffffffff
            name = f'{zlib.crc32(raw) & 0xffffffff:x}-{cname:x}'
            out.setdefault(name, []).append([disc, n, x, y, w, h])
    json.dump(out, open(os.path.join(HERE, 'faces.json'), 'w'), indent=0)
    miss = {k: v for k, v in out.items() if k not in have}
    print(len(out), 'face names,', len(out) - len(miss), 'in the pack')
    for k, v in sorted(miss.items(), key=lambda kv: kv[1][0][1]):
        print('missing', k, v[:3])


if __name__ == '__main__':
    main()
