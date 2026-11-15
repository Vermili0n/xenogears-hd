"""Second renders of bad battle frames: compare the variants, then put the chosen ones into the set.

  python battle_variants.py sheet <out.png> <frames.json> <label>=<dir with name.png> ...
      one strip per frame: sprite x2 | current parts (as the game draws them) | each variant (raw render, colours
      anchored to the sprite as battle_post.py does), all at 3 px per texel. A <label>=<work dir with *_red.png>
      (composed frames, e.g. a set with a board and the head pass) is taken as is.
  python battle_variants.py apply --prod <jobs dir> --res <dir with v4/> [--hero]
      the renders in <res>/v4 replace their frames: composed into ai/prod_work/<group>/work (old *_red.png kept in
      work_v1), then the whole group is sliced again from all its frames, so shared parts stay consistent.
      The parts as they were before the first apply stay in parts_v2.
      --hero: as prod_post.py does for a set with a board (local colour, head pass); default: anchor, no head pass.
"""
import argparse
import json
import os
import shutil
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from battle_qa import frames_of  # noqa: E402
from color_local import anchor_match  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from nisan_joe_post import game_frame  # noqa: E402
from prod_post import WORK, run  # noqa: E402

K = 3


def raw_frame(h, sk, fi, fp):
    """A render cut back to the frame (compose_set.py geometry), colours anchored, alpha = the sprite's silhouette."""
    o8 = np.asarray(frame_rgba(h, sk, fi))
    H, W = o8.shape[:2]
    k = min(500 / H, 512 / W, 1.0)
    if k < 1.0:
        w2, h2 = int(W * k), int(H * k)
        box = ((512 - w2) // 2, 500 - h2, (512 - w2) // 2 + w2, 500)
        full = np.array(Image.open(fp).convert('RGB').crop(box).resize((W, H), Image.LANCZOS))
    else:
        x0 = (512 - W) // 2
        full = np.asarray(Image.open(fp).convert('RGB'))[500 - H:500, x0:x0 + W].copy()
    sil = o8[..., 3] > 127
    full = anchor_match(np.ascontiguousarray(o8[..., :3]), full, sil)
    return Image.fromarray(np.dstack([full, np.where(sil, 255, 0).astype(np.uint8)]), 'RGBA')


def red_frame(h, sk, fi, fp):
    o8 = np.asarray(frame_rgba(h, sk, fi))
    red = np.asarray(Image.open(fp).convert('RGB').resize((o8.shape[1], o8.shape[0]), Image.LANCZOS))
    return Image.fromarray(np.dstack([red, np.where(o8[..., 3] > 127, 255, 0).astype(np.uint8)]), 'RGBA')


def sheet(out, frames_json, variants):
    cells = []
    for g, fl in json.load(open(frames_json)).items():
        h, sk, parts, _ = frames_of(g)
        cache = {}
        for fi in fl:
            old, _ = h.assemble(h.placements(sk, fi))
            size = (old.width * K, old.height * K)
            ims = [('', old.resize((old.width * 2, old.height * 2), Image.NEAREST)), ('cur', game_frame(h, sk, fi, parts, K, cache))]
            for lab, d in variants:
                fp, fr = os.path.join(d, f'{g}__{sk}_{fi:03d}.png'), os.path.join(d, f'{sk}_{fi:03d}_red.png')
                if os.path.exists(fp):
                    ims.append((lab, raw_frame(h, sk, fi, fp).resize(size, Image.LANCZOS)))
                elif os.path.exists(fr):
                    ims.append((lab, red_frame(h, sk, fi, fr).resize(size, Image.LANCZOS)))
            cells.append((f'{g[2:8]}:{fi}', ims))
    W, pages, pos, x, y, rh = 1990, [], [], 4, 4, 0
    for lab, ims in cells:
        w = sum(i.width + 4 for _, i in ims) + 10
        hh = max(i.height for _, i in ims) + 14
        if x + w > W:
            x, y, rh = 4, y + rh + 6, 0
        if y + hh > 1900 and pos:
            pages.append(pos)
            x, y, rh, pos = 4, 4, 0, []
        pos.append((lab, ims, x, y))
        x += w
        rh = max(rh, hh)
    pages.append(pos)
    for k, pg in enumerate(pages, 1):
        c = Image.new('RGB', (W, max(p[3] + max(i.height for _, i in p[1]) for p in pg) + 20), (150, 170, 90))
        d = ImageDraw.Draw(c)
        for lab, ims, x, y in pg:
            for j, (vl, im) in enumerate(ims):
                d.text((x, y), lab if j == 0 else vl, fill=(255, 255, 0))
                c.paste(im, (x, y + 12), im)
                x += im.width + 4
        f = f'{out[:-4]}_{k}.png'
        c.save(f)
        print(f, c.size, len(pg))


def apply_one(args):
    g, prod, res, hero, fr, hd = args
    gd = os.path.join(WORK, g)
    work, keep, log = os.path.join(gd, 'work'), os.path.join(gd, 'work_v1'), os.path.join(gd, 'post.log')
    os.makedirs(keep, exist_ok=True)
    for s, fi in fr:
        f = f'{s}_{fi:03d}_red.png'
        if os.path.exists(os.path.join(work, f)) and not os.path.exists(os.path.join(keep, f)):
            shutil.copyfile(os.path.join(work, f), os.path.join(keep, f))
    if not os.path.exists(os.path.join(gd, 'parts_v2')):  # the parts as they were before the first apply
        shutil.copytree(os.path.join(gd, 'parts'), os.path.join(gd, 'parts_v2'))
    cmd = [sys.executable, 'compose_set.py', '--render', prod, '--res', os.path.join(res, 'v4'), '--work', work,
           '--name', g, '--out-scale', '8']
    cmd += ['--offset-key', g] if hero else ['--color-mode', 'anchor', '--no-color', '--no-head']
    if run(cmd, log):
        return g, f'compose failed, see {log}'
    reds = [f[:-8] for f in os.listdir(work) if f.endswith('_red.png')]
    only = ','.join(f"{r.rsplit('_', 1)[0]}:{int(r.rsplit('_', 1)[1])}" for r in reds)
    tag = os.path.relpath(gd, os.path.join(ROOT, 'ai')).replace(os.sep, '/')
    if run([sys.executable, 'batch_redraw.py', 'slice', '--heroes', tag, '--hero-dir', hd, '--scale', '8', '--exact-mask',
            '--ring', '0', '--uv-compensate', '--only', only], log):
        return g, f'slice failed, see {log}'
    return g, f'frames replaced {len(fr)} {[fi for _, fi in fr]}, sliced {len(reds)} frames'


def apply(a):
    prod, res = os.path.abspath(a.prod), os.path.abspath(a.res)
    meta = json.load(open(os.path.join(prod, 'meta.json')))
    have = sorted(n for n in meta if os.path.exists(os.path.join(res, 'v4', n + '.png')))
    jobs = []
    for g in sorted({meta[n]['group'] for n in have}):
        own = [n for n in have if meta[n]['group'] == g]
        jobs.append((g, prod, res, a.hero, [(meta[n]['set'], meta[n]['frame']) for n in own], os.path.join(ROOT, meta[own[0]]['hero_dir'])))
    with Pool(a.workers) as pool:
        for g, st in pool.imap_unordered(apply_one, jobs):
            print(f'{g}: {st}', flush=True)


def main():
    if sys.argv[1] == 'sheet':
        sheet(sys.argv[2], sys.argv[3], [v.split('=', 1) for v in sys.argv[4:]])
        return
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['apply'])
    ap.add_argument('--prod', required=True)
    ap.add_argument('--res', required=True)
    ap.add_argument('--hero', action='store_true')
    ap.add_argument('--workers', type=int, default=12)
    apply(ap.parse_args())


if __name__ == '__main__':
    main()
