"""Compares the files of two discs by the game's own names (directory, 1-based number), as the kernel finds them (read only).

python tools/rus_discs.py <first.bin> <second.bin> [reference.bin] [out.csv]

Each disc's own index and directory table (tools/rus_files.py): file n of directory d is record start(d) - 1 + n - 1
(Weltall's FGameFileIndex::Find), so two discs whose directories start at other records still pair file for file.
Per directory: how many files are the same, differ, or are on one disc only; a file of the second disc that is a
stand-in (the size most files of its directory share, its bytes one block repeated over the directories) is told
apart. With a reference disc (USA disc 1), each differing file is also told as "first = reference" (the first disc
left it as the reference has it) or not. Movies (directory 25: XA sectors) are paired by size only.
"""
import collections
import hashlib
import sys

import psx_iso
import rus_files

MOVIES = 25


def named_files(img):
    recs, dirs = rus_files.read_index(rus_files.boot_exe(img))
    starts = sorted({s for s in dirs if s not in (0, 0xFFFF)})
    out = {}
    for d, start in enumerate(dirs):
        if start in (0, 0xFFFF):
            continue
        # A directory runs to the next directory's start (the records' end for the last).
        later = [s for s in starts if s > start]
        end = later[0] if later else len(recs) + 1
        for n in range(1, end - start + 1):
            out[(d, n)] = recs[start - 1 + n - 1]
    return out


def digest(img, rec, directory):
    lba, size = rec
    if size <= 0:
        return ('none', size)
    if directory == MOVIES:
        return ('size', size)
    return ('sha1', hashlib.sha1(img.read(lba, size)).hexdigest())


def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    ref_path = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].endswith('.csv') else None
    out_path = next((p for p in sys.argv[3:] if p.endswith('.csv')), None)
    a, b = psx_iso.Image(a_path), psx_iso.Image(b_path)
    ref = psx_iso.Image(ref_path) if ref_path else None
    fa, fb = named_files(a), named_files(b)
    fr = named_files(ref) if ref else {}
    # A stand-in: the second disc's digest shared by many files of every kind (the mastering tool's filler).
    b_digests = {k: digest(b, rec, k[0]) for k, rec in fb.items()}
    shared = collections.Counter(v for v in b_digests.values() if v[0] == 'sha1')
    stand_ins = {v for v, c in shared.items() if c >= 8}
    rows = []
    per_dir = collections.defaultdict(collections.Counter)
    for key in sorted(set(fa) | set(fb)):
        d, n = key
        da = digest(a, fa[key], d) if key in fa else ('absent', 0)
        db = b_digests.get(key, ('absent', 0))
        if da == db:
            kind = 'same'
        elif da[0] == 'absent' or db[0] == 'absent':
            kind = 'first only' if db[0] == 'absent' else 'second only'
        elif db in stand_ins:
            kind = 'second stand-in'
        elif da in stand_ins:
            kind = 'first stand-in'
        elif da[0] == 'none' or db[0] == 'none':
            kind = 'one empty'
        else:
            kind = 'differ'
        as_ref = ''
        if ref and kind == 'differ' and key in fr:
            dr = digest(ref, fr[key], d)
            as_ref = 'first=ref' if dr == da else 'second=ref' if dr == db else 'neither=ref'
            per_dir[d][kind + ' ' + as_ref] += 1
        else:
            per_dir[d][kind] += 1
        rows.append((d, n, fa.get(key, (0, 0))[1], fb.get(key, (0, 0))[1], kind, as_ref))
    for d in sorted(per_dir):
        print(f'dir {d}: ' + ', '.join(f'{k} {v}' for k, v in sorted(per_dir[d].items())))
    if out_path:
        with open(out_path, 'w') as out:
            out.write('dir,number,first_size,second_size,kind,reference\n')
            for r in rows:
                out.write(','.join(str(x) for x in r) + '\n')


if __name__ == '__main__':
    main()
