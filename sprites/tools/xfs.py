"""Xenogears hidden file table + LZSS (logic follows andreaukk/XenoTools, MIT)."""
import struct

TOC_SECTOR = 24


def read_toc(user):
    """user: bytes/mmap of the 2048-byte user-data stream. Returns list of dicts."""
    eot = b'\xff\xff\xff\x00\x00\x00\x00\x00'
    pos = TOC_SECTOR * 2048
    toc, folder = [], -1
    while True:
        e = user[pos:pos + 7]
        seq = e[0:3] + b'\x00' + e[3:7]
        if seq == eot or len(e) < 7:
            break
        lba, size = struct.unpack('<Ii', seq)
        if size < 0:
            folder += 1
            toc.append({'n': len(toc), 'lba': lba, 'size': size, 'folder': folder, 'is_dir': True})
        else:
            toc.append({'n': len(toc), 'lba': lba, 'size': size, 'folder': folder, 'is_dir': False})
        pos += 7
    return toc


def get_file(user, entry):
    start = entry['lba'] * 2048
    return bytes(user[start:start + entry['size']])


def lzss_decompress(data, offset=0):
    """Xenogears LZSS: u32 out_len, then flag bytes; bit=1 -> u16 ref (len = hi4+3, dist = lo12)."""
    out_len = struct.unpack_from('<I', data, offset)[0]
    out = bytearray(out_len)
    p = 0
    i = offset + 4
    n = len(data)
    while p < out_len and i < n:
        flags = data[i]
        i += 1
        for bit in range(8):
            if p >= out_len or i >= n:
                break
            if flags & (1 << bit):
                if i + 1 >= n:
                    i = n
                    break
                h = data[i] | (data[i + 1] << 8)
                i += 2
                size = (h >> 12) + 3
                src = p - (h & 0x0FFF) % 4078
                for k in range(size):
                    if p >= out_len:
                        break
                    out[p] = out[src + k] if src + k >= 0 else 0
                    p += 1
            else:
                out[p] = data[i]
                i += 1
                p += 1
    return bytes(out), i - offset


def field_archive_index(data):
    sizes = struct.unpack_from('<8i', data, 0x10C)
    addr = struct.unpack_from('<9i', data, 0x130)
    return [{'size': sizes[k], 'offset': addr[k], 'end': addr[k + 1]} for k in range(8)]
