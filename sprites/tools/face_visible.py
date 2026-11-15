"""Is a face visible in a sprite head crop?  Skin-coloured pixels in the upper part of the head window.

  python face_visible.py --test ai/pod_v3/test3      (adds "face": true/false to headmap.json and prints a summary)
Used to decide where the 16x head pass makes sense: back views (hair only) get no head pass.
"""
import argparse
import json
import os

import cv2
import numpy as np
from PIL import Image


def face_visible(ctrl_rgb, min_share=0.04):
    """ctrl_rgb: head-window control (sprite on magenta). True when skin covers >= min_share of the upper silhouette."""
    a = ctrl_rgb.astype(int)
    sil = (abs(a[..., 0] - 255) + a[..., 1] + abs(a[..., 2] - 255)) > 60
    top = sil.copy()
    top[int(sil.shape[0] * 0.7):] = False
    if not top.any():
        return False
    hsv = cv2.cvtColor(ctrl_rgb, cv2.COLOR_RGB2HSV).astype(int)
    skin = top & (hsv[..., 0] >= 3) & (hsv[..., 0] <= 22) & (hsv[..., 1] >= 50) & (hsv[..., 1] <= 200) & (hsv[..., 2] >= 110)
    return bool(skin.sum() / top.sum() >= min_share)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--test', required=True)
    a = ap.parse_args()
    hp = os.path.join(a.test, 'headmap.json')
    hm = json.load(open(hp))
    for n, v in hm.items():
        v['face'] = face_visible(np.asarray(Image.open(os.path.join(a.test, 'control', n + '.png')).convert('RGB')))
    json.dump(hm, open(hp, 'w'), indent=0)
    print('faces visible', sum(v['face'] for v in hm.values()), '/', len(hm))
    print('back / hidden:', sorted(n for n, v in hm.items() if not v['face']))


if __name__ == '__main__':
    main()
