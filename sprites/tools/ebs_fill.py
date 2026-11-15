"""Fill frames that have no model redraw by ebsynth propagation from finished neighbour frames (same animation).

  python ebs_fill.py --hero fei --tag _prod --set 427_0 --fill 77:76+78,84:83+85 [--sheet out.png]

Works at 4x on assembled frames: style = finished redraws of the key frames (ai/<hero><tag>/work/<set>_<k>_red.png),
guides = palette-material map (strongest), xBR colours and edges of key vs target sprite. All keys are merged into
one source canvas, so ebsynth picks patches from whichever key fits best. Writes <set>_<t>_red.png.
"""
import argparse
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero, xbr4  # noqa: E402
from ebs_test2 import CODES  # noqa: E402

EBS = os.path.join(HERE, 'ebsynth_src', 'ebsynth-master', 'bin', 'ebsynth.exe')
BG = np.array([255, 0, 255], np.uint8)


def edges(rgb):
    e = cv2.Canny(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), 40, 120)
    e = cv2.GaussianBlur(e.astype(np.float32), (0, 0), 1.5)
    return np.dstack([(255 * e / max(1, e.max())).astype(np.uint8)] * 3)


class Frames:
    def __init__(self, hobj, setkey):
        self.h, self.s = hobj, setkey
        self.cache = {}
        self.lut = {}

    def get(self, fi):
        """-> (rgb4, mask4, material4) of the assembled frame, padded to a fixed canvas (bottom-centre aligned)."""
        if fi in self.cache:
            return self.cache[fi]
        fr, _ = self.h.assemble(self.h.placements(self.s, fi))
        a = np.asarray(fr)
        code = np.zeros(a.shape[:2] + (4,), np.uint8)
        for p in {tuple(v) for v in a.reshape(-1, 4)[:, :3][a.reshape(-1, 4)[:, 3] > 0]}:
            if p not in self.lut:
                self.lut[p] = CODES[len(self.lut) % len(CODES)]
            m = (a[..., 0] == p[0]) & (a[..., 1] == p[1]) & (a[..., 2] == p[2]) & (a[..., 3] > 0)
            code[m, :3] = self.lut[p]
            code[m, 3] = 255
        c4, m4 = xbr4(fr)
        k4, _ = xbr4(Image.fromarray(code, 'RGBA'))
        self.cache[fi] = (c4, m4, k4)
        return self.cache[fi]


def pad(img, H, W, fill):
    out = np.zeros((H, W) + img.shape[2:], img.dtype)
    out[:] = fill
    y, x = H - img.shape[0], (W - img.shape[1]) // 2
    out[y:, x:x + img.shape[1]] = img
    return out, (y, x)


def fill_one(F, work, s, t, keys, tmp):
    c4t, m4t, k4t = F.get(t)
    srcs = []
    for k in keys:
        c4, m4, k4 = F.get(k)
        red = np.asarray(Image.open(os.path.join(work, f'{s}_{k:03d}_red.png')).convert('RGB'))
        if red.shape[:2] != c4.shape[:2]:
            red = np.asarray(Image.fromarray(red).resize((c4.shape[1], c4.shape[0]), Image.LANCZOS))
        red = red.copy(); red[~m4] = BG
        cc = c4.copy(); cc[~m4] = BG
        kk = k4.copy(); kk[~m4] = 0
        srcs.append((red, cc, kk))
    H = max([c4t.shape[0]] + [x[0].shape[0] for x in srcs]) + 8
    W = max([c4t.shape[1]] + [x[0].shape[1] for x in srcs]) + 8
    sty = np.concatenate([pad(x[0], H, W, BG)[0] for x in srcs], 1)
    scol = np.concatenate([pad(x[1], H, W, BG)[0] for x in srcs], 1)
    smat = np.concatenate([pad(x[2], H, W, 0)[0] for x in srcs], 1)
    sedg = np.concatenate([edges(pad(x[1], H, W, BG)[0]) for x in srcs], 1)
    tc = c4t.copy(); tc[~m4t] = BG
    tk = k4t.copy(); tk[~m4t] = 0
    tcol, (oy, ox) = pad(tc, H, W, BG)
    tmat, _ = pad(tk, H, W, 0)
    names = {}
    for n, img in (('sty', sty), ('scol', scol), ('smat', smat), ('sedg', sedg), ('tcol', tcol), ('tmat', tmat),
                   ('tedg', edges(tcol))):
        names[n] = os.path.join(tmp, f'{n}.png')
        Image.fromarray(img).save(names[n])
    out = os.path.join(tmp, 'out.png')
    subprocess.run([EBS, '-style', names['sty'],
                    '-guide', names['smat'], names['tmat'], '-weight', '3',
                    '-guide', names['scol'], names['tcol'], '-weight', '1',
                    '-guide', names['sedg'], names['tedg'], '-weight', '0.5',
                    '-patchsize', '5', '-output', out], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = np.asarray(Image.open(out).convert('RGB'))[oy:oy + c4t.shape[0], ox:ox + c4t.shape[1]].copy()
    Image.fromarray(r).save(os.path.join(work, f'{s}_{t:03d}_red.png'))
    return r, m4t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', default='fei')
    ap.add_argument('--hero-dir', default='')
    ap.add_argument('--tag', default='_prod')
    ap.add_argument('--set', default='427_0')
    ap.add_argument('--fill', required=True, help='t:k1+k2,...')
    ap.add_argument('--sheet', default='')
    a = ap.parse_args()
    hobj = Hero(a.hero_dir or os.path.join(ROOT, 'extracted', 'disc1_full', a.hero))
    F = Frames(hobj, a.set)
    work = os.path.join(ROOT, 'ai', a.hero + a.tag, 'work')
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for tok in a.fill.split(','):
            t, ks = tok.split(':')
            keys = [int(k) for k in ks.split('+')]
            r, m = fill_one(F, work, a.set, int(t), keys, tmp)
            rows.append((int(t), keys, r, m))
            print('filled', t, 'from', keys, flush=True)
    if a.sheet:
        S = 220
        sheet = Image.new('RGB', (len(rows) * (3 * S + 20), S + 30), (60, 60, 60))
        d = ImageDraw.Draw(sheet)
        font = ImageFont.truetype('arial.ttf', 16)
        for j, (t, keys, r, m) in enumerate(rows):
            c4, m4, _ = F.get(t)
            k = keys[0]
            kr = np.asarray(Image.open(os.path.join(work, f'{a.set}_{k:03d}_red.png')).convert('RGB')).copy()
            km = F.get(k)[1]
            ims = []
            for img, mm in ((c4, m4), (kr, km), (r, m)):
                v = img.copy(); v[~mm] = (60, 60, 60)
                ims.append(Image.fromarray(v))
            x0 = j * (3 * S + 20)
            for i, im in enumerate(ims):
                sc = S / max(im.size)
                sheet.paste(im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS), (x0 + i * S, 28))
            d.text((x0 + 4, 4), f'{t}: original | key {k} | ebsynth', fill=(255, 230, 120), font=font)
        sheet.save(a.sheet)


if __name__ == '__main__':
    main()
