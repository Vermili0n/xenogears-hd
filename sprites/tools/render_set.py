"""Render jobs for whole sprite sets (pilot / production): unique frames, full frame + 16x head pass, one board.

  python render_set.py --hero-dir extracted/disc1_full/fei --sets 427_0 --board ai/pairs_v3/boards/fei.png --name fei --out ai/render_pilot
Writes <out>/control/<name>__<set>_<fi>[__head].png, <out>/boards/<name>.png, <out>/jobs.json (infer_pod.py format,
paths relative to <out>) and <out>/meta.json {name: {hero_dir, set, frame, head: [x0, y0] native window, dups: [...]}}.
--no-board renders with the blank board and the no-reference caption (massovka without keyframes); --mecha for gears.
"""
import argparse
import json
import os
import shutil
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from make_pairs import MAG, place  # noqa: E402
from make_pairs_v3 import CAP_HEAD, GREY, HEAD_N, crop_pad, head_window  # noqa: E402
from render_build import CAP_MECHA, CAP_NOREF, CAP_REF, sig  # noqa: E402


def head_control(o8, x0, y0):
    o = np.asarray(o8)
    o16 = cv2.resize(o, (o.shape[1] * 2, o.shape[0] * 2), interpolation=cv2.INTER_NEAREST)
    c = crop_pad(o16, x0 * 16, y0 * 16, HEAD_N * 16, 0)
    rgb = c[..., :3].copy()
    rgb[c[..., 3] < 128] = MAG
    return Image.fromarray(rgb), float((c[..., 3] > 128).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero-dir', required=True)
    ap.add_argument('--sets', default='', help='comma list of set keys (default: all sets of the folder)')
    ap.add_argument('--board', default='')
    ap.add_argument('--name', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--no-board', action='store_true')
    ap.add_argument('--mecha', action='store_true')
    ap.add_argument('--no-heads', action='store_true')
    ap.add_argument('--only', default='', help='file with set:frame lines - render only these frames (part-cover frames)')
    a = ap.parse_args()
    only = set(open(a.only).read().split()) if a.only else None
    hd = os.path.join(ROOT, a.hero_dir) if not os.path.isabs(a.hero_dir) else a.hero_dir
    h = Hero(hd)
    for d in ('control', 'boards'):
        os.makedirs(os.path.join(a.out, d), exist_ok=True)
    jp, mp = os.path.join(a.out, 'jobs.json'), os.path.join(a.out, 'meta.json')
    jobs = json.load(open(jp)) if os.path.exists(jp) else []
    meta = json.load(open(mp)) if os.path.exists(mp) else {}
    have = {j['name'] for j in jobs}
    bname = f'boards/{a.name}.png'
    if a.no_board or a.mecha:
        bname = 'boards/_blank.png'
        Image.new('RGB', (512, 512), GREY).save(os.path.join(a.out, bname))
    else:
        shutil.copyfile(a.board, os.path.join(a.out, bname))
    cap = CAP_MECHA if a.mecha else CAP_NOREF if a.no_board else CAP_REF
    sets = a.sets.split(',') if a.sets else list(h.layout)
    n_full = n_head = 0
    for setkey in sets:
        seen = {}
        for fi, fr in enumerate(h.layout[setkey]['frames']):
            if only is not None and f'{setkey}:{fi}' not in only:
                continue
            name = f'{a.name}__{setkey}_{fi:03d}'
            key = sig(fr)
            if key in seen:
                meta[seen[key]]['dups'].append(name)
                continue
            seen[key] = name
            try:
                o8 = frame_rgba(h, setkey, fi)
            except Exception:  # noqa: BLE001  (empty frame)
                continue
            x0, y0 = head_window(h, setkey, fi)
            meta[name] = {'hero_dir': os.path.relpath(hd, ROOT).replace('\\', '/'), 'set': setkey, 'frame': fi,
                          'head': [x0, y0], 'dups': []}
            if name not in have:
                place(o8, 512, 500).save(os.path.join(a.out, 'control', name + '.png'))
                jobs.append({'name': name, 'control': f'control/{name}.png', 'ref': bname, 'prompt': cap})
            n_full += 1
            if a.no_heads or a.mecha:
                continue
            hc, cover = head_control(o8, x0, y0)
            if cover < 0.15:
                continue
            meta[name]['head_job'] = name + '__head'
            if name + '__head' not in have:
                hc.save(os.path.join(a.out, 'control', name + '__head.png'))
                jobs.append({'name': name + '__head', 'control': f'control/{name}__head.png', 'ref': bname,
                             'prompt': CAP_HEAD if not a.no_board else 'close-up of the head: ' + CAP_NOREF})
            n_head += 1
    json.dump(jobs, open(jp, 'w'), indent=0)
    json.dump(meta, open(mp, 'w'), indent=0)
    print(a.name, 'full', n_full, 'heads', n_head, 'jobs total', len(jobs))


if __name__ == '__main__':
    main()
