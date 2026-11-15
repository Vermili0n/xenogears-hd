"""Field sets that carry their own pixels (missed by npc_maps.py, see empty_sets.py): extract as a hero folder, install the parts.

  python own_set.py extract <set id>          extracted/npc_full/<id>/uses.json -> extracted/disc1_full/own_<id> (layout, parts)
  python own_set.py install <group> <set id> [--skip-frames 3-5]     (RetroArch closed) ai/prod_work/<group>/parts -> pack
Part names = crc32(block bytes)-palette, as for the heroes (nisan_joe_build.py did this for Marguerite). Existing pack
files stay: a name shared with another set keeps its picture. Written names: pod/report/own_set_written.txt.
Jobs: battle_jobs.py --out ... own_<id>:<slug|noref>.
"""
import argparse
import json
import mmap
import os
import sys
import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402
from alias_dump_parts import PACK  # noqa: E402
from extract_heroes import clut_hash  # noqa: E402
from fix_apply import retroarch_running  # noqa: E402
from npc_maps import sub_data  # noqa: E402
from render_frames import block_rgba  # noqa: E402
from seam_fill import fill_interior, frame_interior  # noqa: E402
from xfs import read_toc  # noqa: E402
from xspr import cluts, frames, parse_set, pixel_blocks, u24  # noqa: E402

OWN = os.path.join(ROOT, 'extracted', 'disc1_full')
WORK = os.path.join(ROOT, 'ai', 'prod_work')
WRITTEN = os.path.join(ROOT, 'pod', 'report', 'own_set_written.txt')
S = 8


def extract(sid):
    use = json.load(open(os.path.join(ROOT, 'extracted', 'npc_full', sid, 'uses.json')))['uses'][0]
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    sub = sub_data(mm, read_toc(mm), use['map'], 3)
    s = parse_set(sub, u24(sub, 4 + 4 * use['set']))
    _, _, blocks = pixel_blocks(s['meta'])
    pals = cluts(s['clut_raw'])
    phs = [f'{clut_hash(c):x}' for c in pals]
    out = os.path.join(OWN, f'own_{sid}')
    os.makedirs(os.path.join(out, 'parts'), exist_ok=True)
    name = {}
    for ref, (w, h, b8, px) in blocks.items():
        if b8 or w % 4 or not w or not h:
            continue
        name[ref] = f'{zlib.crc32(bytes(px[:(w // 2) * h])) & 0xffffffff:x}'
        for pi, ph in enumerate(phs):
            f = os.path.join(out, 'parts', f'{name[ref]}-{ph}.png')
            if not os.path.exists(f):
                block_rgba(w, h, px, pals[pi]).save(f)
    key = f"{use['map']}_{use['set']}"
    lay = {key: {'palettes': phs, 'frames': [
        [{'block': name[p['ref']], **{k: p[k] for k in ('dx', 'dy', 'flipx', 'flipy', 'clut', 'mx', 'my', 'rot')}}
         for p in fr if p['ref'] in name] for fr in frames(s['meta'])]}}
    json.dump(lay, open(os.path.join(out, 'layout.json'), 'w'))
    print(f'{out}: key {key}, frames {len(lay[key]["frames"])}, parts {len(name)}, palettes {phs}')


def install(group, sid, skip_frames):
    if retroarch_running():
        raise SystemExit('RetroArch is running - close it first')
    hd = os.path.join(OWN, f'own_{sid}')
    lay = json.load(open(os.path.join(hd, 'layout.json')))
    lay = lay[list(lay)[0]]
    pals = lay['palettes']
    skip = set()
    for r in filter(None, skip_frames.split(',')):
        lo, _, hi = r.partition('-')
        skip |= set(range(int(lo), int(hi or lo) + 1))
    keep = {f"{p['block']}-{pals[min(p['clut'], len(pals) - 1)]}"
            for fi, fr in enumerate(lay['frames']) if fi not in skip for p in fr}
    parts = os.path.join(WORK, group, 'parts')
    inner = frame_interior([(lay, hd)], lambda h, k: os.path.join(h, 'parts'))
    written, kept, failed = [], 0, 0
    for f in sorted(os.listdir(parts)):
        if not f.endswith('.png') or f[:-4] not in keep:
            continue
        blk, pal = f[:-4].split('-')
        dst = os.path.join(PACK, f[:-4] + '.bc7')
        if os.path.exists(dst):
            kept += 1
            continue
        a = np.asarray(Image.open(os.path.join(parts, f)).convert('RGBA')).astype(np.int16)
        a, _ = fill_interior(a, None, S, a[..., 3] == 0, inner.get((blk, pal)))
        lv, flags = bc7pack.levels_of(np.ascontiguousarray(np.clip(a, 0, 255).astype(np.uint8)))
        enc, bad, _ = bc7pack.encode_levels(lv)
        if bad:
            failed += 1
            continue
        with open(dst + '.tmp', 'wb') as o:
            o.write(bc7pack.pack_file(enc, a.shape[1], a.shape[0], flags))
        os.replace(dst + '.tmp', dst)
        written.append(f[:-4])
    with open(WRITTEN, 'a', encoding='utf-8') as o:
        o.writelines(n + '\n' for n in written)
    print(f'{group}: names {len(keep)}, written {len(written)}, already in the pack {kept}, BC7 failed {failed}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['extract', 'install'])
    ap.add_argument('args', nargs='+')
    ap.add_argument('--skip-frames', default='')
    a = ap.parse_args()
    if a.cmd == 'extract':
        for sid in a.args:
            extract(sid)
    else:
        install(a.args[0], a.args[1], a.skip_frames)


if __name__ == '__main__':
    main()
