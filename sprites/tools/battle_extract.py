"""Battle 2D sprite sets with their own texture pages (gears, enemies, bosses) -> hero-style folders.

  python battle_extract.py --files 2617-2770,3380-3920 --out extracted/battle
File layout (rufaswan quad_xeno_battle_2d.php, same as field sprite sub-files): u24 num, u24 b04, then 12-byte
entries (meta/set offset, texture-list offset, ?); texture list = u32 n + u32 offsets, image = u16 w (u16 units), u16 h,
4bpp pixels; a part of a p256 frame = 5-byte record (tex id << 1, sx, sy, w, h) inside texture image <tex id>.
Output per set: parts/<rect>-<pal>.png, layout.json {'npc': {...}} (so Hero/make_grids/prod_fit work), pages.npz,
pal.json, info.json (file, entry, texture hashes for the pack names).
"""
import argparse
import hashlib
import json
import mmap
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from extract_heroes import clut_hash  # noqa: E402
from npc_maps import rect_name, rgba_from_idx  # noqa: E402
from npc_tex import part_rect, sets_in_sub, textures  # noqa: E402
from xfs import get_file, read_toc  # noqa: E402
from xspr import cluts, frames, parse_set  # noqa: E402


def ranges(spec):
    out = []
    for tok in spec.split(','):
        a, _, b = tok.partition('-')
        out += list(range(int(a), int(b or a) + 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default=os.path.join(ROOT, 'work', 'disc1_user.bin'))
    ap.add_argument('--files', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    fh = open(a.user, 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    os.makedirs(a.out, exist_ok=True)
    index = {}
    for n in ranges(a.files):
        if n >= len(toc) or toc[n]['is_dir'] or toc[n]['size'] < 64:
            continue
        d = get_file(mm, toc[n])
        try:
            entries = sets_in_sub(d)
        except Exception:  # noqa: BLE001
            continue
        for k, (met, tex) in enumerate(entries):
            try:
                s = parse_set(d, met)
                pals = cluts(s['clut_raw'])
                texs = textures(d, tex)
                fr = frames(s['meta'])
                rects = {p['ref']: part_rect(s['meta'], p['ref']) for f in fr for p in f}
            except Exception:  # noqa: BLE001
                continue
            if not pals or not texs or not fr:
                continue
            if any(r[0] >= len(texs) for r in rects.values()):
                continue
            hsh = hashlib.sha1(bytes(s['meta']) + bytes(s['clut_raw']) + b''.join(t['raw'] for t in texs)).hexdigest()[:10]
            if hsh in index:
                index[hsh]['uses'].append([n, k])
                continue
            root = os.path.join(a.out, hsh)
            os.makedirs(os.path.join(root, 'parts'), exist_ok=True)
            phs = [f'{clut_hash(c):x}' for c in pals]
            used = {(rects[p['ref']], min(p['clut'], len(pals) - 1)) for f in fr for p in f}
            for r, ci in used:
                tid, sx, sy, w, h = r
                if not w or not h:
                    continue
                idx = texs[tid]['idx'][sy:sy + h, sx:sx + w]
                Image.fromarray(rgba_from_idx(idx, pals[ci]), 'RGBA').save(os.path.join(root, 'parts', f'{rect_name(r)}-{phs[ci]}.png'))
            layout = {'npc': {'palettes': phs, 'frames': [
                [{'block': rect_name(rects[p['ref']]), **{q: p[q] for q in ('dx', 'dy', 'flipx', 'flipy', 'clut', 'mx', 'my', 'rot')}}
                 for p in f if rects[p['ref']][3] and rects[p['ref']][4]] for f in fr]}}
            json.dump(layout, open(os.path.join(root, 'layout.json'), 'w'))
            np.savez_compressed(os.path.join(root, 'pages.npz'), *[t['idx'] for t in texs])
            json.dump({'palettes_raw': [list(map(int, c)) for c in pals]}, open(os.path.join(root, 'pal.json'), 'w'))
            info = {'id': hsh, 'file': n, 'entry': k, 'frames': len(fr), 'palettes': phs,
                    'textures': [{'w': t['w'], 'h': t['h'], 'hash': f"{t['hash']:x}"} for t in texs], 'uses': [[n, k]]}
            json.dump(info, open(os.path.join(root, 'info.json'), 'w'), indent=1)
            index[hsh] = info
            print(n, k, '->', hsh, len(fr), 'frames', len(texs), 'tex', flush=True)
    json.dump({k: {'file': v['file'], 'frames': v['frames'], 'uses': v['uses']} for k, v in index.items()},
              open(os.path.join(a.out, 'index.json'), 'w'), indent=1)
    print(len(index), 'battle sets')


if __name__ == '__main__':
    main()
