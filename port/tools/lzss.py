"""The game's LZSS (as Weltall's Formats/Lzss.cpp reads it): 4-byte size, then groups of a flag byte and 8 items."""
import struct


def unpack(stream):
    size = struct.unpack_from('<I', stream, 0)[0]
    out = bytearray()
    pos = 4
    while len(out) < size:
        flags = stream[pos]
        pos += 1
        for bit in range(8):
            if not (flags >> bit) & 1:
                out.append(stream[pos])
                pos += 1
                continue
            lo, hi = stream[pos], stream[pos + 1]
            pos += 2
            dist = lo | (hi & 0x0F) << 8
            length = (hi >> 4) + 3
            start = len(out) - dist
            for i in range(length):
                out.append(out[start + i])
    return bytes(out[:size])


def unpack_prefix(stream, count):
    """The first count bytes of a stream (whose own size may be larger), stopping as soon as they are out."""
    out = bytearray()
    pos = 4
    while len(out) < count:
        flags = stream[pos]
        pos += 1
        for bit in range(8):
            if len(out) >= count:
                break
            if not (flags >> bit) & 1:
                out.append(stream[pos])
                pos += 1
                continue
            lo, hi = stream[pos], stream[pos + 1]
            pos += 2
            dist = lo | (hi & 0x0F) << 8
            start = len(out) - dist
            for i in range((hi >> 4) + 3):
                if len(out) >= count:
                    break
                out.append(out[start + i])
    return bytes(out)
