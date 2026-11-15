"""Which of the 63 installed Bart parts carry the slicer's xBR stand-in (native look) where the previous pack file had a real drawing.
batch_redraw.slice paints a part from one frame: texels hidden in that frame keep the xBR upscale of the sprite. Slicing only the picked
frames made such texels visible in any other frame that shows them.

  python find_unredrawn.py <out_prefix>
For every part: share of its opaque pixels equal to the xBR stand-in now / before, and the frames where those pixels are really visible.
"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from batch_redraw import uv_compensate, xbr_at  # noqa: E402

BART = os.path.join(ROOT, 'ai', 'prod_work', 'h_bart_patch')
BK = sorted(glob.glob(r'<DATA_DRIVE>\xeno_redraw_backup\bart_patch_*'))[-1]
S = 8


def stand_in(pimg):
    pc, _ = xbr_at(pimg, S)
    al = np.kron(np.asarray(pimg)[..., 3] > 0, np.ones((S, S), bool))
    return uv_compensate(np.dstack([pc, np.where(al, 255, 0).astype(np.uint8)]), S)


def main():
    h = Hero(os.path.join(ROOT, 'extracted', 'disc1_full', 'bart'))
    sel = json.load(open(os.path.join(BART, 'selected.json')))['parts']
    use = {}
    for s in h.layout:
        for fi in range(len(h.layout[s]['frames'])):
            try:
                pl = h.placements(s, fi)
            except Exception:  # noqa: BLE001
                continue
            for p in pl:
                use.setdefault(f"{p['block']}-{p['pal']}", set()).add((s, fi))
    rows, cells = [], []
    for nm in sel:
        pimg = h.part(*nm.split('-'))
        si = stand_in(pimg).astype(int)
        now = read_bc7_level0(os.path.join(PACK, nm + '.bc7')).astype(int)
        old = read_bc7_level0(os.path.join(BK, nm + '.bc7')).astype(int)
        if now.shape != si.shape or old.shape != si.shape:
            print('shape differs', nm, now.shape, old.shape, si.shape)
            continue
        op = now[..., 3] > 0
        same_now = (np.abs(now[..., :3] - si[..., :3]).max(axis=-1) < 22) & op
        same_old = (np.abs(old[..., :3] - si[..., :3]).max(axis=-1) < 22) & (old[..., 3] > 0)
        changed = np.abs(now[..., :3] - old[..., :3]).mean(axis=-1)[op & (old[..., 3] > 0)].mean() if (op & (old[..., 3] > 0)).any() else 0
        rows.append((same_now.sum() - same_old.sum(), same_now.sum(), same_old.sum(), int(op.sum()), float(changed), nm, sorted(use[nm])[:6], len(use[nm])))
        cells.append((nm, pimg, old, now))
    rows.sort(reverse=True)
    print('extra stand-in px | now | before | opaque | mean change | part | frames')
    for r in rows[:40]:
        print(r)
    order = [r[5] for r in rows[:14]]
    by = {c[0]: c for c in cells}
    Z = 2
    W = 1900
    x = y = 4
    rh = 0
    place = []
    for n in order:
        _, pimg, old, now = by[n]
        ims = [pimg.resize((pimg.width * 8, pimg.height * 8), Image.NEAREST)] + [Image.fromarray(a.astype(np.uint8), 'RGBA') for a in (old, now)]
        w = sum(i.width * Z + 4 for i in ims) + 12
        if x + w > W:
            x, y, rh = 4, y + rh + 6, 0
        place.append((x, y, n, ims))
        x += w
        rh = max(rh, ims[0].height * Z + 16)
    s = Image.new('RGB', (W, y + rh + 8), (150, 170, 90))
    d = ImageDraw.Draw(s)
    for x, y, n, ims in place:
        d.text((x, y), n + '  sprite | before | now', fill=(255, 255, 0))
        xx = x
        for i in ims:
            j = i.resize((i.width * Z, i.height * Z), Image.NEAREST)
            s.paste(j, (xx, y + 13), j)
            xx += j.width + 4
    s.save(sys.argv[1] + '.png')
    print(sys.argv[1] + '.png', s.size)


if __name__ == '__main__':
    main()
