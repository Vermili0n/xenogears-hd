"""Print the hidden TOC summary and which files contain the given sectors."""
import argparse
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xfs import read_toc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True)
    ap.add_argument('--sectors', type=int, nargs='*', default=[])
    ap.add_argument('--csv')
    args = ap.parse_args()
    with open(args.user, 'rb') as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        toc = read_toc(mm)
    files = [e for e in toc if not e['is_dir'] and e['size'] > 0]
    print('entries', len(toc), 'files', len(files), 'folders', sum(e['is_dir'] for e in toc))
    if args.csv:
        with open(args.csv, 'w') as o:
            o.write('n,folder,lba,size\n')
            for e in files:
                o.write(f"{e['n']},{e['folder']},{e['lba']},{e['size']}\n")
    for s in args.sectors:
        for e in files:
            if e['lba'] <= s < e['lba'] + (e['size'] + 2047) // 2048:
                print(f"sector {s}: file {e['n']} folder {e['folder']} lba {e['lba']} size {e['size']} off {(s - e['lba']) * 2048}")


if __name__ == '__main__':
    main()
