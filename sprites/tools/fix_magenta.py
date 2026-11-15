"""Paint over the render's magenta key background that leaked into sliced parts (thin effect pixels, sword tips).

  python fix_magenta.py <group> ...        parts in ai/prod_work/<group>/parts, fixed in place (originals in parts_magenta/)
Leaked pixels: opaque, R and B > 160, G < 0.55 * min(R, B), plus a 1 px ring; filled from the neighbours (cv2 inpaint, Telea).
"""
import os
import shutil
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, 'ai', 'prod_work')


def fix(path, backup):
    a = np.asarray(Image.open(path).convert('RGBA')).copy()
    vis = a[..., 3] > 0
    r, g, b = (a[..., i].astype(int) for i in range(3))
    m = vis & (r > 160) & (b > 160) & (g < 0.55 * np.minimum(r, b))
    if not m.any():
        return 0
    keep = os.path.join(backup, os.path.basename(path))
    if not os.path.exists(keep):  # the first original stays
        shutil.copyfile(path, keep)
    mask = cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)) & vis.astype(np.uint8)
    if mask.sum() >= vis.sum():  # nothing left to fill from: drop the pixels
        a[m, 3] = 0
    else:
        # transparent pixels are masked too, so the fill takes colours only from visible ones
        rgb = cv2.inpaint(np.ascontiguousarray(a[..., :3]), mask | (~vis).astype(np.uint8), 3, cv2.INPAINT_TELEA)
        a[mask > 0, :3] = rgb[mask > 0]
    Image.fromarray(a).save(path)
    return int(m.sum())


def main():
    for g in sys.argv[1:]:
        parts = os.path.join(WORK, g, 'parts')
        backup = os.path.join(WORK, g, 'parts_magenta')
        os.makedirs(backup, exist_ok=True)
        n = files = 0
        for f in sorted(os.listdir(parts)):
            if f.endswith('.png'):
                k = fix(os.path.join(parts, f), backup)
                n += k
                files += k > 0
        print(f'{g}: {n} px in {files} files')


if __name__ == '__main__':
    main()
