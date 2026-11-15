"""List ISO9660 files of the disc user-data stream (LBA, size, path); optionally find the file at a sector."""
import argparse
import struct


def read_sector(f, lba, n=1):
    f.seek(lba * 2048)
    return f.read(2048 * n)


def walk(f, lba, size, path, out):
    data = read_sector(f, lba, (size + 2047) // 2048)
    i = 0
    while i < size:
        ln = data[i]
        if ln == 0:
            i = (i // 2048 + 1) * 2048
            continue
        rec = data[i:i + ln]
        ext = struct.unpack('<I', rec[2:6])[0]
        sz = struct.unpack('<I', rec[10:14])[0]
        flags = rec[25]
        nlen = rec[32]
        name = rec[33:33 + nlen]
        i += ln
        if name in (b'\x00', b'\x01'):
            continue
        name = name.decode('ascii', 'replace').split(';')[0]
        full = path + '/' + name
        if flags & 2:
            walk(f, ext, sz, full, out)
        else:
            out.append((ext, sz, full))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True)
    ap.add_argument('--find', type=int, nargs='*', default=[])
    args = ap.parse_args()
    with open(args.user, 'rb') as f:
        pvd = read_sector(f, 16)
        root = pvd[156:156 + 34]
        ext = struct.unpack('<I', root[2:6])[0]
        sz = struct.unpack('<I', root[10:14])[0]
        out = []
        walk(f, ext, sz, '', out)
    out.sort()
    if args.find:
        for s in args.find:
            for e, z, p in out:
                if e <= s < e + (z + 2047) // 2048:
                    print(s, '->', p, 'lba', e, 'size', z, 'offset', (s - e) * 2048)
    else:
        print(len(out), 'files')
        for e, z, p in out:
            print(e, z, p)


if __name__ == '__main__':
    main()
