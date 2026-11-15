r"""Every image of every item of a map's sub-file 4 (npc_maps.sub4_pages keeps only the first image of an item)."""
import struct
import sys
import zlib

from gcommon import ROOT  # noqa: F401  (puts tools on the path)
from extract_npc import sub_data


def sub4_all(mm, toc, n):
    """-> {item: [(w, h, raw, crc), ...]} for map data file n."""
    try:
        d = sub_data(mm, toc, n, 4)
    except Exception:  # noqa: BLE001
        return {}
    if len(d) < 16:
        return {}
    cnt = struct.unpack_from('<I', d, 0)[0]
    if not 0 < cnt <= 64:
        return {}
    offs = struct.unpack_from(f'<{cnt + 1}I', d, 4)
    out = {}
    for i in range(cnt):
        it = d[offs[i]:offs[i + 1] if offs[i + 1] > offs[i] else len(d)]
        if len(it) < 16:
            continue
        k = struct.unpack_from('<I', it, 0)[0]
        if not 0 < k <= 8:
            continue
        imgs = []
        for j in range(k):
            o = struct.unpack_from('<I', it, 4 + 4 * j)[0]
            if o + 4 > len(it):
                continue
            w, h = struct.unpack_from('<HH', it, o)
            raw = it[o + 4:o + 4 + w * h * 2]
            if w and h and len(raw) == w * h * 2:
                imgs.append((w, h, raw, zlib.crc32(raw) & 0xffffffff))
        out[i] = imgs
    return out


if __name__ == '__main__':
    import mmap
    from xfs import read_toc
    fh = open(f'{ROOT}/work/disc1_user.bin', 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    for n in map(int, sys.argv[1:]):
        for i, imgs in sub4_all(mm, toc, n).items():
            print(n, i, [(w, h, f'{c:x}') for w, h, _, c in imgs])
