r"""Index of every sub-file-4 image of every map file of a disc: crc -> where (file, item, image, w, h).
  python scan_sub4.py usa|rus1|rus2  -> sub4_<disc>.json"""
import json
import mmap
import os
import sys

from gcommon import HERE, ROOT, rus_disc
from sub4all import sub4_all
from xfs import read_toc


def main():
    which = sys.argv[1]
    if which == 'usa':
        fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        toc = read_toc(mm)
    else:
        mm, toc = rus_disc(int(which[-1]))
    out = {}
    for n, e in enumerate(toc):
        if e['is_dir'] or e['size'] <= 0x200 or n < 400:
            continue
        for i, imgs in sub4_all(mm, toc, n).items():
            for j, (w, h, _, c) in enumerate(imgs):
                out.setdefault(f'{c:x}', []).append([n, i, j, w, h])
    json.dump(out, open(os.path.join(HERE, f'sub4_{which}.json'), 'w'))
    print(which, len(out), 'images')


if __name__ == '__main__':
    main()
