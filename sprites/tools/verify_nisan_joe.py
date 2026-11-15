"""After nisan_joe_post.py install: Marguerite's parts and Big Joe's rect files against what was prepared, read back from the pack."""
import json
import os
import sys
import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from battle_rects import DUMP, part_rect, rect_variants, sheet_words, tex_id  # noqa: E402
from nisan_joe_build import G_JOE, G_MARGIE, JOE, MARGIE  # noqa: E402

WORK = os.path.join(ROOT, 'ai', 'prod_work')
parts = os.path.join(WORK, G_MARGIE, 'parts')
lay = json.load(open(os.path.join(MARGIE, 'layout.json')))
lay = lay[list(lay)[0]]
pals = lay['palettes']
need = {f"{p['block']}-{pals[min(p['clut'], len(pals) - 1)]}" for f in lay['frames'] for p in f}
have = [n for n in need if os.path.exists(os.path.join(PACK, n + '.bc7'))]
worst, shape_bad = 0.0, 0
for n in have:
    a = np.asarray(Image.open(os.path.join(parts, n + '.png')).convert('RGBA')).astype(int)
    b = read_bc7_level0(os.path.join(PACK, n + '.bc7')).astype(int)
    if a.shape != b.shape:
        shape_bad += 1
        continue
    vis = a[..., 3] > 0
    if vis.any():
        worst = max(worst, float(np.abs(a[..., :3] - b[..., :3])[vis].mean()))
print('marguerite: names', len(need), 'in the pack', len(have), 'other size', shape_bad, 'worst mean colour diff', round(worst, 1))

z = np.load(os.path.join(JOE, 'pages.npz'))
words = [sheet_words(z[k].astype(np.uint16)) for k in z.files]
fr = json.load(open(os.path.join(JOE, 'layout.json')))['npc']['frames']
skip = set(range(63, 69))
keep = {p['block'] for i, f in enumerate(fr) if i not in skip for p in f}
can = {p['block'] for i, f in enumerate(fr) if i in skip for p in f} - keep


def names_of(blocks):
    out = set()
    for b in blocks:
        t = tex_id(b)
        for x, y, w, h in rect_variants(*part_rect(b)):
            if y + h <= words[t].shape[0] and x + w <= 64:
                out.add(f"{zlib.crc32(np.ascontiguousarray(words[t][y:y + h, x:x + w]).astype('<u2').tobytes()) & 0xffffffff:x}")
    return out


nk, nc = names_of(keep), names_of(can)
rows = [ln.split() for ln in open(os.path.join(DUMP, 'rects.txt')).read().splitlines()[2053:]]
rows = [r for r in rows if r[0].split('-')[1] in ('df3ad574', '36a7f02f') and int(r[4]) > 1]
in_pack = [r for r in rows if os.path.exists(os.path.join(PACK, r[0] + '.bc7'))]
miss = [r for r in rows if not os.path.exists(os.path.join(PACK, r[0] + '.bc7'))]
print('joe: dump rows taller than one line', len(rows), 'with a file', len(in_pack), 'without', len(miss))
print('   without a file: of the can', sum(r[0].split('-')[0] in nc for r in miss), 'other', [r[:5] for r in miss if r[0].split('-')[0] not in nc][:8])
can_only = nc - nk
print('   can names', len(can_only), 'with a file', sum(any(os.path.exists(os.path.join(PACK, f'{n}-{p}.bc7')) for p in ('df3ad574', '36a7f02f')) for n in can_only))
sizes = 0
for ln in open(os.path.join(ROOT, 'pod', 'report', 'battle_rects_written.txt'), encoding='utf-8'):
    sizes += os.path.getsize(os.path.join(PACK, ln.strip() + '.bc7'))
print('   rect files MB', round(sizes / 1e6))
print('png in pack', sum(1 for e in os.scandir(PACK) if e.name.endswith('.png')), 'tmp', sum(1 for e in os.scandir(PACK) if e.name.endswith('.tmp')))
