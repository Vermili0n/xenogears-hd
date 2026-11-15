"""Which reference board fits a battle set: colour histograms of the battle frames against the field sprites that have a board.

  python battle_ref_match.py <out dir> <set id> ...      (own_<id> for an own-pixel field set)
Candidates: named boards (for_chatgpt/<slug>/sprite.json -> field set) and npc_<id10> boards (pairs_v4, accepted extra).
Histogram: opaque pixels, 3 bits per channel, intersection score. Writes match.json (top 6 per set) and one sheet per
set: battle frames | the best field sprites with their board, to be judged by eye.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from battle_jobs import BATTLE, OWN  # noqa: E402
from render_prod import B4, BX, slug_board  # noqa: E402

EXT = os.path.join(ROOT, 'extracted')


def frames_of(hd, n_max=12):
    h = Hero(hd)
    sk = list(h.layout)[0]
    n = len(h.layout[sk]['frames'])
    out = []
    for fi in sorted(set(np.linspace(0, n - 1, min(n, n_max)).astype(int))):
        try:
            im, _ = h.assemble(h.placements(sk, fi))
        except Exception:  # noqa: BLE001  (empty frame)
            continue
        out.append(im.convert('RGBA'))
    return out


def hist(ims):
    hv = np.zeros(512)
    for im in ims:
        a = np.asarray(im)
        p = a[a[..., 3] > 0][:, :3] >> 5
        np.add.at(hv, (p[:, 0].astype(int) << 6) | (p[:, 1].astype(int) << 3) | p[:, 2].astype(int), 1)
    return hv / max(hv.sum(), 1)


def candidates():
    out = {}
    for slug in os.listdir(os.path.join(ROOT, 'for_chatgpt')):
        sj = os.path.join(ROOT, 'for_chatgpt', slug, 'sprite.json')
        if os.path.exists(sj) and slug_board(slug):
            s = json.load(open(sj))
            hd = os.path.join(EXT, s.get('root', 'npc_full'), s['npc'])
            if os.path.isdir(hd):
                out[slug] = (hd, slug_board(slug))
    acc = set(json.load(open(os.path.join(BX, '..', 'accepted.json')))['accepted'])
    for d in (B4, BX):
        for f in os.listdir(d):
            if not f.startswith('npc_') or (d == BX and f not in acc):
                continue
            nid = f[4:14]
            for root in ('npc_full', 'npc_all', 'npc_all_d2'):
                hd = next((os.path.join(EXT, root, x) for x in os.listdir(os.path.join(EXT, root)) if x.startswith(nid)), None) \
                    if os.path.isdir(os.path.join(EXT, root)) else None
                if hd:
                    out.setdefault(f[:-4], (hd, os.path.join(d, f)))
                    break
    return out


def thumb(im, h):
    k = max(1, h // max(im.height, 1))
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def main():
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    cands = candidates()
    print('candidates', len(cands), flush=True)
    ch = {}
    for name, (hd, _) in cands.items():
        try:
            fr = frames_of(hd, 6)
            ch[name] = (hist(fr), fr[0] if fr else None)
        except Exception as e:  # noqa: BLE001
            print('skip', name, repr(e)[:80])
    res = {}
    for sid in sys.argv[2:]:
        hd = os.path.join(OWN, sid) if sid.startswith('own_') else os.path.join(BATTLE, sid)
        fr = frames_of(hd)
        hv = hist(fr)
        sc = sorted(((float(np.minimum(hv, c[0]).sum()), n) for n, c in ch.items()), reverse=True)[:6]
        res[sid] = sc
        print(sid, ' '.join(f'{n}:{s:.2f}' for s, n in sc), flush=True)
        H = 150
        cells = [('battle', thumb(f, H)) for f in fr[:3]]
        for s, n in sc:
            board = Image.open(cands[n][1]).convert('RGB').resize((H, H))
            cells.append((f'{n} {s:.2f}', board))
            if ch[n][1] is not None:
                cells.append(('', thumb(ch[n][1], H)))
        W = sum(c[1].width + 6 for c in cells) + 4
        c = Image.new('RGB', (W, H * 2 + 20), (150, 170, 90))
        d = ImageDraw.Draw(c)
        x = 4
        for label, im in cells:
            d.text((x, 2), label, fill=(255, 255, 0))
            c.paste(im, (x, 16), im if im.mode == 'RGBA' else None)
            x += im.width + 6
        c.save(os.path.join(out_dir, f'{sid}.png'))
    json.dump(res, open(os.path.join(out_dir, 'match.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
