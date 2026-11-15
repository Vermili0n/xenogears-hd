"""Compares every file of the game's own index (in the boot executable) between two discs (read only).

python tools/rus_files.py <usa.bin> <other.bin> [out.csv]
Prints which files differ, grouped by directory, and writes one line per record to out.csv.
"""
import hashlib
import struct
import sys

import psx_iso

INDEX = 0x80010004
INDEX_BYTES = 0x7FFC
DIRS = 0x80018004
DIR_COUNT = 61


def boot_exe(img):
    cnf = img.file('SYSTEM.CNF').decode('ascii', 'replace')
    name = cnf.split('cdrom:')[1].lstrip('\\').split(';')[0]
    return img.file(name)


def read_index(exe):
    load = struct.unpack_from('<I', exe, 0x18)[0]
    at = lambda a: 0x800 + a - load
    idx = exe[at(INDEX):at(INDEX) + INDEX_BYTES]
    recs = []
    for o in range(0, len(idx) - 6, 7):
        lba = idx[o] | idx[o + 1] << 8 | idx[o + 2] << 16
        if lba == 0xFFFFFF:
            break
        recs.append((lba, struct.unpack_from('<i', idx, o + 3)[0]))
    dirs = struct.unpack_from('<%dH' % DIR_COUNT, exe, at(DIRS))
    return recs, dirs


def name_of(dirs, rec):
    best = None
    for d, start in enumerate(dirs):
        if start in (0, 0xFFFF) or start - 1 > rec:
            continue
        if best is None or start - 1 > dirs[best] - 1:
            best = d
    # 1-based, as the game (and Weltall's FGameFileIndex::Find) numbers them
    return (best, rec - (dirs[best] - 1) + 1) if best is not None else (None, rec)


def main():
    u = psx_iso.Image(sys.argv[1])
    r = psx_iso.Image(sys.argv[2])
    ur, ud = read_index(boot_exe(u))
    rr, rd = read_index(boot_exe(r))
    print('records', len(ur), len(rr), 'dirs equal', ud == rd)
    out = open(sys.argv[3], 'w') if len(sys.argv) > 3 else None
    if out:
        out.write('record,dir,number,usa_lba,usa_size,other_lba,other_size,same\n')
    by_dir = {}
    for i, (a, b) in enumerate(zip(ur, rr)):
        d, n = name_of(ud, i)
        same = None
        if a[1] > 0 and b[1] > 0:
            same = a[1] == b[1] and u.read(a[0], a[1]) == r.read(b[0], b[1])
        elif a[1] != b[1]:
            same = False
        if out:
            out.write(f'{i},{d},{n},{a[0]},{a[1]},{b[0]},{b[1]},{same}\n')
        if same is False:
            by_dir.setdefault(d, []).append((n, a[1], b[1]))
    for d in sorted(by_dir, key=lambda x: -1 if x is None else x):
        files = by_dir[d]
        print(f'dir {d}: {len(files)} differ; first: ' + ' '.join(f'{n}({s1}->{s2})' for n, s1, s2 in files[:12]))


if __name__ == '__main__':
    main()
