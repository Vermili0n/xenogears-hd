"""Which Bart frame is on a screenshot: the native-looking chunk of the shot is searched in the native frames of all sets at several scales.

  python find_shot_frame.py <shot.png> x0,y0,x1,y1 [--top 8]
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from ai_redraw import Hero  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('shot')
ap.add_argument('box')
ap.add_argument('--top', type=int, default=8)
a = ap.parse_args()
shot = np.asarray(Image.open(a.shot).convert('RGB'))
x0, y0, x1, y1 = (int(v) for v in a.box.split(','))
Q = cv2.GaussianBlur(shot[y0:y1, x0:x1].astype(np.float32), (0, 0), 3)
print('shot', shot.shape, 'query', Q.shape)
SETS = [('bart', os.path.join(ROOT, 'extracted', 'disc1_full', 'bart'))]
for sid in ('4b16d73da7', '5822b9bb58', '70a4dcc69d', '9522cfbb67', 'bcc8990fb9', 'c75eb56e69', 'c7ad1d08fb', 'eaf637a98c', '448b7348ca'):
    SETS.append((sid, os.path.join(ROOT, 'extracted', 'npc_full', sid)))
res = []
seen = {}
for tag, d in SETS:
    h = Hero(d)
    for s in h.layout:
        for fi in range(len(h.layout[s]['frames'])):
            try:
                img, _ = h.assemble(h.placements(s, fi))
            except Exception:  # noqa: BLE001
                continue
            b = img.tobytes()
            if b in seen:
                continue
            seen[b] = f'{tag}/{s}:{fi}'
            arr = np.asarray(img)
            rgb = arr[..., :3].astype(np.float32)
            rgb[arr[..., 3] == 0] = (120, 120, 120)
            for sc in np.arange(5.0, 8.01, 0.1):
                W, H = int(arr.shape[1] * sc), int(arr.shape[0] * sc)
                if W < Q.shape[1] or H < Q.shape[0]:
                    continue
                big = cv2.GaussianBlur(cv2.resize(rgb, (W, H), interpolation=cv2.INTER_NEAREST), (0, 0), 3)
                m = cv2.matchTemplate(big, Q, cv2.TM_SQDIFF)
                v, _, loc, _ = cv2.minMaxLoc(m)
                res.append((v / Q.size, seen[b], round(float(sc), 1), loc))
res.sort(key=lambda r: r[0])
for r in res[:40]:
    pass
out, used = [], set()
for r in res:
    if r[1] in used:
        continue
    used.add(r[1])
    out.append(r)
    if len(out) >= a.top:
        break
for r in out:
    print(f'{r[0]:8.1f} {r[1]:28s} scale {r[2]} at {r[3]}  (texel row {r[3][1] / r[2]:.1f})')
print('distinct frames', len(seen))
