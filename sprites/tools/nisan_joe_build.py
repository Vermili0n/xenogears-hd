"""Marguerite's own-pixels set (maps 792/798, Nisan) and Big Joe's battle set (file 2713): hero folder + pod jobs.

  python nisan_joe_build.py [--out ai/redraw/nisan_joe]
1. extracted/disc1_full/margie_nisan: set 792_6 as a hero folder. npc_maps.py skips sets that carry their own pixels, so
   the frames of b42512df9d came out empty; names = crc32(block bytes)-palette, as for the heroes.
2. Jobs for all frames of both sets (no part cover: fewer stand-ins, see scan_standin.py). A Marguerite control image equal
   to one of c_marguerite_fatima_e91bdb is not rendered again: reuse.json {new job: old job}, copied after the pod run by
   nisan_joe_post.py. Seed 42 and the production captions, so the look matches the field sets.
"""
import argparse
import hashlib
import json
import mmap
import os
import shutil
import sys
import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from extract_heroes import clut_hash  # noqa: E402
from npc_maps import sub_data  # noqa: E402
from render_frames import block_rgba  # noqa: E402
from render_prod import build_group, slug_board  # noqa: E402
from xfs import read_toc  # noqa: E402
from xspr import cluts, frames, parse_set, pixel_blocks, u24  # noqa: E402

MARGIE = os.path.join(ROOT, 'extracted', 'disc1_full', 'margie_nisan')
JOE = os.path.join(ROOT, 'extracted', 'battle', 'e4ad71a9e8')
G_MARGIE, G_JOE = 'c_marguerite_fatima_b42512', 'b_e4ad71a9e8'
OLD_GROUP = 'c_marguerite_fatima_e91bdb'
PROD = os.path.join(ROOT, 'ai', 'prod')
OLD_RES = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod', 'v4')
MAP, SET = 792, 6


def extract_margie():
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    sub = sub_data(mm, toc, MAP, 3)
    s = parse_set(sub, u24(sub, 4 + 4 * SET))
    _, _, blocks = pixel_blocks(s['meta'])
    pals = cluts(s['clut_raw'])
    phs = [f'{clut_hash(c):x}' for c in pals]
    os.makedirs(os.path.join(MARGIE, 'parts'), exist_ok=True)
    name = {}
    for ref, (w, h, b8, px) in blocks.items():
        if b8 or w % 4 or not w or not h:
            continue
        name[ref] = f'{zlib.crc32(bytes(px[:(w // 2) * h])) & 0xffffffff:x}'
        for pi, ph in enumerate(phs):
            f = os.path.join(MARGIE, 'parts', f'{name[ref]}-{ph}.png')
            if not os.path.exists(f):
                block_rgba(w, h, px, pals[pi]).save(f)
    key = f'{MAP}_{SET}'
    lay = {key: {'palettes': phs, 'frames': [
        [{'block': name[p['ref']], **{k: p[k] for k in ('dx', 'dy', 'flipx', 'flipy', 'clut', 'mx', 'my', 'rot')}}
         for p in fr if p['ref'] in name] for fr in frames(s['meta'])]}}
    json.dump(lay, open(os.path.join(MARGIE, 'layout.json'), 'w'))
    print('margie: frames', len(lay[key]['frames']), 'parts', len(name), 'palettes', phs)
    return key, len(lay[key]['frames'])


def digest(path):
    a = np.asarray(Image.open(path).convert('RGBA'))
    return hashlib.sha1(a.tobytes() + repr(a.shape).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'ai', 'redraw', 'nisan_joe'))
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    os.makedirs(os.path.join(out, 'control'), exist_ok=True)
    os.makedirs(os.path.join(out, 'boards'), exist_ok=True)
    key, n = extract_margie()
    b_m, b_j = slug_board('marguerite_fatima'), slug_board('big_joe')
    for b in (b_m, b_j):
        shutil.copyfile(b, os.path.join(out, 'boards', os.path.basename(b)))
    j_m, m_m = build_group((G_MARGIE, MARGIE, [(key, i) for i in range(n)], b_m, 'hero', out))
    n_joe = len(json.load(open(os.path.join(JOE, 'layout.json')))['npc']['frames'])
    j_j, m_j = build_group((G_JOE, JOE, [('npc', i) for i in range(n_joe)], b_j, 'hero', out))
    old = {}
    for f in os.listdir(os.path.join(PROD, 'control')):
        if f.startswith(OLD_GROUP + '__') and os.path.exists(os.path.join(OLD_RES, f)):
            old.setdefault(digest(os.path.join(PROD, 'control', f)), f[:-4])
    reuse, keep = {}, []
    for j in j_m:
        d = digest(os.path.join(out, j['control']))
        if d in old:
            reuse[j['name']] = old[d]
            os.remove(os.path.join(out, j['control']))
        else:
            keep.append(j)
    jobs = [{k: v for k, v in j.items() if k != 'lora'} for j in keep + j_j]
    json.dump(jobs, open(os.path.join(out, 'jobs.json'), 'w'), indent=0)
    json.dump({**m_m, **m_j}, open(os.path.join(out, 'meta.json'), 'w'), indent=0)
    json.dump(reuse, open(os.path.join(out, 'reuse.json'), 'w'), indent=0)
    print('margie frames', len(m_m), 'jobs', len(j_m), 'reused', len(reuse), 'to render', len(keep))
    print('joe frames', len(m_j), 'jobs', len(j_j))
    print('total jobs', len(jobs), 'boards', os.listdir(os.path.join(out, 'boards')))


if __name__ == '__main__':
    main()
