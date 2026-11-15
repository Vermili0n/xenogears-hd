"""Minimal Xenogears field script reader (map file N, sub-file 5) - enough to tie speakers to NPC sprite sets.

Layout found by inspection (USA disc 1):
  0x00..0x80  header (u16 0x00e0, 0x0938, ...)
  0x80..      entity table: 64-byte rows = 32 u16 script offsets per entity (0 = none), offsets rise monotonically
  table end + 4: code; script offsets are relative to it; scripts end with 0x00
Opcodes used here:
  0b NN 80        give the current entity the 2D sprite set NN (index into the map's sprite sets = 'set' in uses.json)
  d2 LL HH ff 9c  show message HHLL of sub-file 7, then wait
  69 NN 80        (in cut-scenes, before messages) - candidate for "speaker = entity NN"
"""
import struct


def parse(b):
    prev, r, rows = 0, 0x80, []
    while r + 64 <= len(b):
        v = struct.unpack('<32H', b[r:r + 64])
        nz = [t for t in v if t]
        if nz and min(nz) < prev:
            break
        if nz:
            prev = max(nz)
        rows.append([t for t in v if t])
        r += 64
    base = r + 4
    starts = sorted({p for v in rows for p in v})
    ents = []
    for v in rows:
        code = b''
        for p in sorted(set(v)):
            j = starts.index(p)
            q = starts[j + 1] if j + 1 < len(starts) else len(b) - base
            code += b[base + p:base + q]
        ents.append(code)
    return ents, b[base:]


def sprite_sets(code):
    return sorted({code[i + 1] for i in range(len(code) - 2) if code[i] == 0x0b and code[i + 2] == 0x80})


def message_ids(code, nmsg):
    out = []
    for i in range(len(code) - 4):
        if code[i] == 0xd2 and code[i + 4] == 0x9c:
            k = code[i + 1] | code[i + 2] << 8
            if k < nmsg:
                out.append((i, k))
    return out
