"""Xenogears 2D sprite set parser (layout per rufaswan/Web2D_Games quad_xeno_battle_2d.php, GPL).

A sprite set = sections [anim, meta, clut(, seds, wds, ...)].
meta: u16 header (cnt = &0x1ff frames, 0x8000 = parts come from 256x256 texpages),
      u16 frame offsets; each frame: byte (num parts &0x3f, 0x80 = int16 offsets), then
      image refs (non-p256: u16 pixel-block offset/4 + u16 ?) and a draw bytecode stream.
pixel block: w, h, bpp8 flag, 0, then raw pixels (4bpp: w*h/2 bytes, low nibble = left pixel).
"""
import struct


def u24(b, o):
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)


def s8(v):
    return v - 256 if v >= 128 else v


def parse_set(data, base=0):
    """Return dict(anim, meta, clut_raw, sections) for a sprite set starting at `base`."""
    num = u24(data, base)
    offs = [u24(data, base + 4 + 4 * k) for k in range(num + 1)]
    sec = [data[base + offs[k]:base + offs[k + 1]] for k in range(num)]
    return {'num': num, 'offs': offs, 'anim': sec[0], 'meta': sec[1], 'clut_raw': sec[2], 'sections': sec}


def cluts(clut_raw):
    """Section starts with a 4-byte header, then 16-color palettes (32 bytes each)."""
    body = clut_raw[4:]
    return [list(struct.unpack_from('<16H', body, k)) for k in range(0, len(body) - 31, 32)]


def pixel_blocks(meta):
    """All non-p256 pixel blocks referenced by frames: {offset: (w, h, bpp8, bytes)}."""
    hdr = struct.unpack_from('<H', meta, 0)[0]
    cnt, p256 = hdr & 0x1ff, hdr & 0x8000
    blocks = {}
    if p256:
        return cnt, True, blocks
    for i in range(cnt):
        pos = struct.unpack_from('<H', meta, 2 + 2 * i)[0]
        num = meta[pos] & 0x3f
        img = pos + 6
        for k in range(num):
            p = struct.unpack_from('<H', meta, img + 4 * k)[0] * 4
            if p + 4 > len(meta) or p in blocks:
                continue
            w, h, bpp8 = meta[p], meta[p + 1], meta[p + 2]
            size = w * h if bpp8 else (w * h) // 2
            blocks[p] = (w, h, bpp8, meta[p + 4:p + 4 + size])
    return cnt, False, blocks


def frames(meta):
    """Decode draw lists: per frame a list of parts (block offset, dx, dy, flipx, flipy, clut id, mx, my, rot)."""
    hdr = struct.unpack_from('<H', meta, 0)[0]
    cnt, p256 = hdr & 0x1ff, hdr & 0x8000
    out = []
    for i in range(cnt):
        pos = struct.unpack_from('<H', meta, 2 + 2 * i)[0]
        b = meta[pos]
        num, int16 = b & 0x3f, b & 0x80
        img = pos + (4 if p256 else 6)
        dat = img + num * (2 if p256 else 4)
        parts, flipy, mx, my, rot, left = [], False, 0, 0, 0, num
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
                parts.append({'ref': ref, 'dx': dx, 'dy': dy, 'flipx': bool(c & 0x40), 'flipy': flipy,
                              'clut': c & 0x0f, 'mx': mx, 'my': my, 'rot': rot})
                flipy = False
                left -= 1
                continue
            if c & 0x40 == 0:
                if c & 0x04:
                    flipy = True
                if c & 0x01:
                    dat += 1
                if c & 0x02:
                    dat += 1
                continue
            mx = my = rot = 0
            if c & 0x20:
                mx, my = s8(meta[dat]), s8(meta[dat + 1])
                dat += 2
            if c & 0x10:
                rot = meta[dat]
                dat += 1
        parts.reverse()  # draw order: last listed is drawn first
        out.append(parts)
    return out
