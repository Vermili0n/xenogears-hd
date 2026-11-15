r"""Which file of the disc holds the sprite set whose blocks the game streams for Id's chi attacks (15.11.2026).

  python ai\redraw\id_chi\find_set.py
F6 reports xeno_port/out/frame_reports/2026-11-15T00-50-38-422 and ...00-50-59-437: Id in original pixels while he
uses chi; the pieces are uploaded one by one (names <block crc>-938b5ed5: c784f610, 2c67fa31, 140acedb ...), and none
is in the pack or in any index.csv of extracted/. Every file of the disc is read as extract_heroes.py reads the heroes'
(sets of blocks with their own texels); a set with one of the wanted blocks, or with Id's palette, is printed.
"""
import mmap
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from extract_heroes import clut_hash, load_sets  # noqa: E402
from xfs import get_file, read_toc  # noqa: E402
from xspr import cluts, frames, pixel_blocks  # noqa: E402

WANTED = {0xc784f610, 0x2c67fa31, 0xd566207d, 0x0e2fd1c9, 0xd1418665, 0x886d4c89, 0xba93e93e, 0x140acedb, 0x3e3f834a,
          0x5e02209c, 0x7728f246, 0x9f2e5153, 0xb491bf4c, 0xc2d6830a, 0xf3e5f126}
PALETTE = '938b5ed5'


def main():
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
            except Exception:  # noqa: BLE001
                continue
            crcs = {zlib.crc32(bytes(px[:(w // 2) * h])) & 0xffffffff for w, h, b8, px in blocks.values() if not b8}
            hit = crcs & WANTED
            if hit or PALETTE in pals:
                print(f'file {n} set {si}: {"pages" if p256 else "blocks"} {len(blocks)}, frames {len(frames(s["meta"]))}, '
                      f'palettes {pals[:6]}, wanted blocks {len(hit)} of {len(WANTED)}', flush=True)
        if n % 500 == 0:
            print(f'... file {n} of {len(toc)}', flush=True)


if __name__ == '__main__':
    main()
