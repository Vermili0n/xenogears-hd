"""Temporarily take our installed sprite parts out of the HD pack (diagnostics), or put them back.

  python pack_toggle_ours.py out   # our parts -> HOLD, pack originals restored from the backup
  python pack_toggle_ours.py in    # our parts back from HOLD (originals stay in the backup)
Nothing is deleted: files are moved between PACK and HOLD (same drive), originals are copied from BK.
"""
import os
import shutil
import sys

from install_parts import BK, LOG, PACK

HOLD = r'<DATA_DRIVE>\XenogearsHD_CD1+CD2\hold_our_parts'


def main():
    mode = sys.argv[1]
    names = open(LOG).read().split()
    os.makedirs(HOLD, exist_ok=True)
    moved = restored = 0
    if mode == 'out':
        for f in names:
            src = os.path.join(PACK, f)
            if os.path.exists(src):
                os.replace(src, os.path.join(HOLD, f))
                moved += 1
            orig = os.path.join(BK, f)
            if os.path.exists(orig):
                shutil.copy2(orig, src)
                restored += 1
    elif mode == 'in':
        for f in names:
            src = os.path.join(HOLD, f)
            if os.path.exists(src):
                os.replace(src, os.path.join(PACK, f))
                moved += 1
    print(mode, 'moved', moved, 'originals restored', restored, 'of', len(names))


if __name__ == '__main__':
    main()
