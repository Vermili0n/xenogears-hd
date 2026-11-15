r"""Sets of blocks on the disc that the pack knows by palette but not by block (15.11.2026): the class Id's chi set was.

  python ai\redraw\id_chi\scan_streamed.py > ai\redraw\id_chi\scan_streamed.txt
A set of blocks (the game streams it block by block; the pack names a block <crc of its texels>-<palette>) whose
palette has files in the pack while few of its own blocks do: probably a second cut of a character that is drawn from
another file (Id: 3833 beside the sheets of 2721; Citan's field run beside the world map set; Elly's forest copy).
One line per such set: file, set, blocks, frames, palettes, blocks with a file under the set's first palette.
"""
import mmap
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from alias_dump_parts import PACK  # noqa: E402
from extract_heroes import clut_hash, load_sets  # noqa: E402
from xfs import get_file, read_toc  # noqa: E402
from xspr import cluts, frames, pixel_blocks  # noqa: E402


def main():
    have, by_palette = set(), {}
    for f in os.listdir(PACK):
        name = f.rsplit('.', 1)[0]
        if '-' in name:
            have.add(name)
            by_palette[name.split('-')[1]] = by_palette.get(name.split('-')[1], 0) + 1
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    for n, e in enumerate(toc):
        if e['is_dir'] or e['size'] <= 0:
            continue
        try:
            sets = load_sets(get_file(mm, e), os.path.join(ROOT, 'work', 'lz_disc1', f'{n}.dec'))
        except Exception:  # noqa: BLE001
            continue
        for si, s in enumerate(sets):
            try:
                _, p256, blocks = pixel_blocks(s['meta'])
                pals = [f'{clut_hash(c):x}' for c in cluts(s['clut_raw'])]
                count = len(frames(s['meta']))
            except Exception:  # noqa: BLE001
                continue
            if p256 or not pals or not blocks:
                continue
            crcs = {zlib.crc32(bytes(px[:(w // 2) * h])) & 0xffffffff for w, h, b8, px in blocks.values() if not b8 and w and h}
            known = [p for p in pals if by_palette.get(p, 0) >= 50]
            if not crcs or not known:
                continue
            got = max(sum(f'{c:x}-{p}' in have for c in crcs) for p in known)
            if got < 0.5 * len(crcs):
                print(f'file {n} set {si}: blocks {len(crcs)}, frames {count}, palettes {pals[:4]} (in the pack: '
                      f'{[(p, by_palette[p]) for p in known][:4]}), blocks with a file {got}', flush=True)


if __name__ == '__main__':
    main()
