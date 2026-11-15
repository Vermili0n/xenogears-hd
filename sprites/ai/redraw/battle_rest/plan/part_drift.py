"""Colour drift of every HD part against its native part: python part_drift.py <out dir> <group> ...
Per part: HD resized to native size, mean RGB shift over pixels opaque in both. Writes drift.json and a sheet of the worst parts per group."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = r'<XENO_SPRITES>'
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ai_redraw import Hero  # noqa: E402
from battle_jobs import set_dir  # noqa: E402


def drift(h, parts, nm):
    block, pal = nm.rsplit('-', 1)
    nat = np.asarray(h.part(block, pal).convert('RGBA')).astype(float)
    hd = Image.open(os.path.join(parts, nm + '.png')).convert('RGBA')
    hd = Image.fromarray(np.where(np.asarray(hd)[..., 3:] > 0, np.dstack([np.asarray(hd)[..., :3], np.full(np.asarray(hd).shape[:2], 255, np.uint8)]), 0).astype(np.uint8))
    sm = np.asarray(hd.resize((nat.shape[1], nat.shape[0]), Image.BOX)).astype(float)
    m = (nat[..., 3] > 0) & (sm[..., 3] > 64)
    if m.sum() < 12:
        return None, nat, hd
    d = sm[m][:, :3].mean(0) - nat[m][:, :3].mean(0)
    return float(np.linalg.norm(d)) if m.sum() >= 300 else 0.0, nat, hd


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    res = {}
    for g in sys.argv[2:]:
        h = Hero(set_dir(g))
        parts = os.path.join(ROOT, 'ai', 'prod_work', g, 'parts')
        rows = []
        for f in sorted(os.listdir(parts)):
            if not f.endswith('.png'):
                continue
            nm = f[:-4]
            try:
                s, nat, hd = drift(h, parts, nm)
            except Exception as e:  # noqa: BLE001
                print('skip', g, nm, repr(e)[:60])
                continue
            if s is not None:
                rows.append((s, nm, nat, hd))
        rows.sort(key=lambda r: -r[0])
        res[g] = [(round(s, 1), nm) for s, nm, _, _ in rows]
        top = [r for r in rows if r[0] > 30][:30]
        print(g, 'parts', len(rows), 'drift>30:', sum(r[0] > 30 for r in rows), 'drift>45:', sum(r[0] > 45 for r in rows), flush=True)
        if not top:
            continue
        cells = []
        for s, nm, nat, hd in top:
            n = Image.fromarray(nat.astype(np.uint8))
            k = max(1, 120 // max(n.height, n.width, 1))
            n = n.resize((n.width * k, n.height * k), Image.NEAREST)
            hh = hd.resize((n.width, n.height), Image.LANCZOS)
            cells.append((f'{s:.0f} {nm[:14]}', n, hh))
        W, x, y, rh, pos = 1990, 4, 4, 0, []
        for lab, n, hh in cells:
            w = n.width * 2 + 12
            if x + w > W:
                x, y, rh = 4, y + rh + 16, 0
            pos.append((lab, n, hh, x, y))
            x += w
            rh = max(rh, n.height)
        c = Image.new('RGB', (W, y + rh + 20), (150, 170, 90))
        d = ImageDraw.Draw(c)
        for lab, n, hh, x, y in pos:
            d.text((x, y), lab, fill=(255, 255, 0))
            c.paste(n, (x, y + 12), n)
            c.paste(hh, (x + n.width + 4, y + 12), hh)
        c.save(os.path.join(out, f'{g}.png'))
    json.dump(res, open(os.path.join(out, 'drift.json'), 'w'), indent=0)


if __name__ == '__main__':
    main()
