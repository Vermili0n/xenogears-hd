"""Hero parts drawn in a palette we never redrew them in (30.10, Elly following Fei in the forest: her parts in
497431e1 / bb5ad862 while our HD of the same images exists only in the other one).

  python hero_palette_swaps.py --hero elly [--dump <core texture dump dir>] [--dry]
For every dump file <hash>-<P> with no HD in the pack, where <hash> is one of the hero's parts and the pack has
<hash>-<Q> (both P and Q palettes of the hero): the HD of <hash>-<Q> is recoloured to P with the NPC palette-swap
recolour (npc_maps.derive_palette_pages: per palette index Lab shift, mismatch-aware) and written as <hash>-<P>.bc7.
Palettes come from the hero's sprite sets on the USA disc. Log: pod/report/hero_palette_swaps.log.
"""
import argparse
import csv
import json
import mmap
import os
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402
from alias_dump_parts import DUMP, PACK, read_bc7_level0  # noqa: E402
from npc_maps import derive_palette_pages  # noqa: E402
from scan_all import clut_hash, set_candidates  # noqa: E402
from xfs import get_file, read_toc  # noqa: E402
from xspr import cluts, parse_set  # noqa: E402

LOG = os.path.join(ROOT, 'pod', 'report', 'hero_palette_swaps.log')


def log(s):
    s = time.strftime('%d.%m %H:%M ') + s
    print(s, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(s + '\n')


def hero_cluts(hero):
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = {e['n']: e for e in read_toc(mm)}
    out = {}
    for k in json.load(open(os.path.join(ROOT, 'extracted', 'disc1_full', hero, 'layout.json'))):
        d = get_file(mm, toc[int(k.split('_')[0])])
        for b in set_candidates(d):
            try:
                for c in cluts(parse_set(d, b)['clut_raw']):
                    out[format(clut_hash(c), 'x')] = [int(v) for v in c]
            except Exception:  # noqa: BLE001
                pass
    return out


def index_map(png, clut):
    """Dump PNG (core dump: 5-bit colours expanded, tri alpha) -> palette indices (0 = transparent)."""
    a = np.asarray(Image.open(png).convert('RGBA')).astype(int)
    c = np.array(clut)
    cols = np.stack([(c & 31) * 255 // 31, ((c >> 5) & 31) * 255 // 31, ((c >> 10) & 31) * 255 // 31], -1)
    d = np.abs(a[..., None, :3] - cols[None, None]).sum(-1)
    d[..., 0] += 10 ** 6
    idx = d.argmin(-1)
    idx[a[..., 3] == 0] = 0
    return idx.astype(np.uint8)


def psx_to_tri(p):
    """Core convention (transparent 0, opaque alpha 0, semi alpha 255) -> straight RGBA (tri: 255 / 127)."""
    t = (p == 0).all(-1)
    out = p.copy()
    out[..., 3] = np.where(p[..., 3] == 255, 127, 255)
    out[t] = 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', required=True)
    ap.add_argument('--dump', default=DUMP)
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    CL = hero_cluts(a.hero)
    hashes = {r['name'].rsplit('-', 1)[0] for r in csv.DictReader(open(
        os.path.join(ROOT, 'extracted', 'disc1_full', a.hero, 'index.csv')))}
    pack = {}
    for e in os.scandir(PACK):
        stem, ext = os.path.splitext(e.name)
        if ext in ('.bc7', '.png') and '-' in stem:
            pack[stem] = e.name
    by_hash = {}
    for stem in pack:
        h, p = stem.rsplit('-', 1)
        by_hash.setdefault(h, []).append(p)
    made = 0
    for f in sorted(os.listdir(a.dump)):
        stem = f[:-4]
        if not f.endswith('.png') or stem in pack or '-' not in stem:
            continue
        h, P = stem.rsplit('-', 1)
        if h not in hashes or P not in CL:
            continue
        srcs = [q for q in by_hash.get(h, []) if q in CL and pack[f'{h}-{q}'].endswith('.bc7')]
        if not srcs:
            continue
        Q = srcs[0]
        idx = index_map(os.path.join(a.dump, f), CL[P])
        hd = psx_to_tri(read_bc7_level0(os.path.join(PACK, pack[f'{h}-{Q}'])))
        S = hd.shape[1] // idx.shape[1]
        if S < 1 or hd.shape[0] != idx.shape[0] * S:
            log(f'{stem}: size mismatch {hd.shape} vs {idx.shape}')
            continue
        pages = {Q: hd.astype(np.uint8)}
        cov = {Q: hd[..., 3] > 0}
        derive_palette_pages(pages, cov, idx, [CL[Q], CL[P]], [Q, P], S)
        out = pages[P]
        log(f'{stem} {idx.shape[1]}x{idx.shape[0]} <- recolour of {h}-{Q}' + (' (dry)' if a.dry else ''))
        if a.dry:
            made += 1
            continue
        lv, flags = bc7pack.levels_of(np.ascontiguousarray(out))
        parts, failed, _ = bc7pack.encode_levels(lv)
        if failed:
            log(f'  {stem}: BC7 rules failed, skipped')
            continue
        with open(os.path.join(PACK, stem + '.bc7.tmp'), 'wb') as fo:
            fo.write(bc7pack.pack_file(parts, out.shape[1], out.shape[0], flags))
        os.replace(os.path.join(PACK, stem + '.bc7.tmp'), os.path.join(PACK, stem + '.bc7'))
        made += 1
    log(f'{a.hero}: palette swaps {made}' + (' (dry run)' if a.dry else ''))


if __name__ == '__main__':
    main()
