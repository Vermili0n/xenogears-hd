r"""Dialogue portraits the pack lacks by name, but has as the same picture under another upload name (15.11.2026).

  python ai\redraw\gaps_1115\faces_install.py             faces.json (faces.py) -> twins, preview faces\twins.png
  python ai\redraw\gaps_1115\faces_install.py --install   the twin's HD file copied under the missing name (pack + mod)
Adult Emeralda's portrait (file 517, upload 54cb8504-84598680) is not in the pack, but the pack's bf58561-84598680 is
the same face in the same palette (the third-party pack was made from another dump of it): the shapes match, only the
pack's colour grading differs, as for every other portrait of that pack. A twin = a pack file under the same palette whose
picture, brought down to the face's 64x64, covers the face's opaque texels: mask IoU >= MIN_IOU (the pack's own
portraits against their faces: median 0.91; colours are no measure - that pack regraded them, luminance correlation of
true pairs runs from -0.15 to 1). The twin is then checked by eye on faces\twins.png.
Written names: faces\installed.txt (undo: delete them from both packs).
"""
import argparse
import json
import mmap
import os

import numpy as np

from gcommon import HERE, ROOT, hd, install_files, pack_names, PACK, show, side_by_side
from faces import tim
from render_frames import psx_to_rgba
from xfs import get_file, read_toc

MIN_IOU = 0.85


def face_rgba(n):
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    clut, (x, y, w, h, raw), _ = tim(get_file(mm, read_toc(mm)[n]))
    pal = np.array([psx_to_rgba(int(c)) for c in np.frombuffer(clut[4][:512], '<u2')], np.uint8)
    return pal[np.frombuffer(raw, np.uint8).reshape(h, w * 2)]


def mask_iou(face, h):
    """IoU of the face's opaque texels and the HD's (a texel is opaque when most of its HD pixels are not (0,0,0,0))."""
    k = h.shape[0] // face.shape[0]
    a = (~(h == 0).all(-1)).reshape(face.shape[0], k, face.shape[1], k).mean(axis=(1, 3)) > 0.5
    b = face[..., 3] > 0
    return (a & b).sum() / max(1, (a | b).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', action='store_true')
    a = ap.parse_args()
    have = pack_names()
    faces = json.load(open(os.path.join(HERE, 'faces.json')))
    rows, twins = [], {}
    for name, where in sorted(faces.items()):
        if name in have:
            continue
        usa = [w for w in where if w[0] == 'usa']
        if not usa:
            print(name, 'not on disc 1 (USA numbering): skipped')
            continue
        face = face_rgba(usa[0][1])
        if not (face[..., :3] > 0).any():
            print(name, f'file {usa[0][1]}: an all-black face (nothing to draw), skipped')
            continue
        pal = name.split('-')[1]
        best = (0, None)
        for cand in sorted(n for n in have if n.endswith('-' + pal)):
            h = hd(cand)
            if h is None or h.shape[0] % face.shape[0] or h.shape[1] % face.shape[1]:
                continue
            c = mask_iou(face, h)
            if c > best[0]:
                best = (c, cand)
        print(name, f'file {usa[0][1]}: best twin {best[1]} mask IoU {best[0]:.3f}')
        if best[0] >= MIN_IOU:
            twins[name] = best[1]
            big = show(hd(best[1]))
            k = big.shape[0] // face.shape[0]
            orig = np.repeat(np.repeat(np.where(face[..., 3:] > 0, face[..., :3], (255, 0, 255)).astype(np.uint8), k // 4, 0), k // 4, 1)
            rows += [orig, big[::4, ::4]]
    os.makedirs(os.path.join(HERE, 'faces'), exist_ok=True)
    if rows:
        side_by_side(rows).save(os.path.join(HERE, 'faces', 'twins.png'))
    json.dump(twins, open(os.path.join(HERE, 'faces', 'twins.json'), 'w'), indent=1)
    if not a.install:
        print(len(twins), 'twins; faces\\twins.png (the face, the HD it gets); --install to copy')
        return
    stage = os.path.join(HERE, 'faces', 'stage')
    os.makedirs(stage, exist_ok=True)
    for name, twin in twins.items():
        open(os.path.join(stage, name + '.bc7'), 'wb').write(open(os.path.join(PACK, twin + '.bc7'), 'rb').read())
    done = install_files(stage, list(twins), os.path.join(HERE, 'faces', 'installed.txt'))
    print('installed', done)


if __name__ == '__main__':
    main()
