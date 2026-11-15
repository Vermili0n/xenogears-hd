r"""tools/xspr.frames with the parts' grow bytes kept (draw commands 0x80..0xBF, bits 1 and 2: GrowWidth, GrowHeight as
Weltall's FPlacementWalker reads them; xspr skips them). A part of record size 0 is drawn with its grow as its size."""
import struct

from xspr import s8


def frames_grow(meta):
    hdr = struct.unpack_from('<H', meta, 0)[0]
    cnt, p256 = hdr & 0x1ff, hdr & 0x8000
    out = []
    for i in range(cnt):
        pos = struct.unpack_from('<H', meta, 2 + 2 * i)[0]
        b = meta[pos]
        num, int16 = b & 0x3f, b & 0x80
        img = pos + (4 if p256 else 6)
        dat = img + num * (2 if p256 else 4)
        parts, flipy, mx, my, rot, gw, gh, left = [], False, 0, 0, 0, 0, 0, num
        while left > 0 and dat < len(meta):
            c = meta[dat]
            dat += 1
            if c & 0x80 == 0:
                if int16:
                    dx, dy = struct.unpack_from('<hh', meta, dat)
                    dat += 4
                else:
                    dx, dy = s8(meta[dat]), s8(meta[dat + 1])
                    dat += 2
                if p256:
                    ref = struct.unpack_from('<H', meta, img)[0]
                    img += 2
                else:
                    ref = struct.unpack_from('<H', meta, img)[0] * 4
                    img += 4
                parts.append({'ref': ref, 'dx': dx, 'dy': dy, 'flipx': bool(c & 0x40), 'flipy': flipy, 'clut': c & 0x0f,
                              'mx': mx, 'my': my, 'rot': rot, 'grow_w': gw, 'grow_h': gh})
                flipy, gw, gh = False, 0, 0
                left -= 1
                continue
            if c & 0x40 == 0:
                if c & 0x04:
                    flipy = True
                if c & 0x01:
                    gw = s8(meta[dat])
                    dat += 1
                if c & 0x02:
                    gh = s8(meta[dat])
                    dat += 1
                continue
            mx = my = rot = 0
            if c & 0x20:
                mx, my = s8(meta[dat]), s8(meta[dat + 1])
                dat += 2
            if c & 0x10:
                rot = meta[dat]
                dat += 1
        parts.reverse()
        out.append(parts)
    return out
