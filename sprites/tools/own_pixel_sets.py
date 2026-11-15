"""Field sets that carry their own pixels (missed by npc_maps): frames sheet, part names, pack coverage, frames equal to already drawn sets, text of the maps."""
import json
import mmap
import os
import struct
import sys
import zlib

import numpy as np
from PIL import Image, ImageDraw

ROOT = r'<XENO_SPRITES>'
OUT = sys.argv[1]
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK  # noqa: E402
from extract_heroes import clut_hash  # noqa: E402
from npc_maps import sub_data  # noqa: E402
from render_frames import render_set  # noqa: E402
from speakers import messages  # noqa: E402
from xfs import read_toc  # noqa: E402
from xspr import cluts, frames, parse_set, pixel_blocks, u24  # noqa: E402

fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
toc = read_toc(mm)
DUMP = r'<RETROARCH_DRIVE>\RetroArch\system\Xenogears (RUS)-texture-dump'


def native_frames(sid):
    h = Hero(os.path.join(ROOT, 'extracted', 'npc_full', sid))
    s = list(h.layout)[0]
    out = {}
    for fi in range(len(h.layout[s]['frames'])):
        try:
            im, _ = h.assemble(h.placements(s, fi))
        except Exception:  # noqa: BLE001
            continue
        out[np.asarray(im.crop(im.getbbox())).tobytes()] = fi
    return out


for sid, maps, cmp_sets in (('b42512df9d', (792, 798), ('e91bdb2dd8',)), ('cefe13a9f6', (624,), ()), ('b0bc3a886a', (942,), ())):
    u = json.load(open(os.path.join(ROOT, 'extracted', 'npc_full', sid, 'uses.json')))
    use = u['uses'][0]
    sub = sub_data(mm, toc, use['map'], 3)
    s = parse_set(sub, u24(sub, 4 + 4 * use['set']))
    _, _, bl = pixel_blocks(s['meta'])
    pals = cluts(s['clut_raw'])
    phs = [f'{clut_hash(c):x}' for c in pals]
    names = set()
    for ref, (w, h, b8, px) in bl.items():
        if b8 or w % 4 or not w or not h:
            continue
        th = zlib.crc32(bytes(px[:(w // 2) * h])) & 0xffffffff
        names.add(f'{th:x}-{phs[0]}')
    have = sum(os.path.exists(os.path.join(PACK, n + '.bc7')) for n in names)
    dumped = sum(os.path.exists(os.path.join(DUMP, n + '.png')) for n in names)
    print(sid, 'blocks', len(bl), 'names', len(names), 'in pack', have, 'in old dump', dumped, 'palettes', phs)
    imgs = render_set(s)
    vis = [(i, im.crop(im.getbbox())) for i, im in enumerate(imgs) if im.getbbox()]
    print(' frames with pixels', len(vis), 'of', len(imgs))
    for c in cmp_sets:
        nat = native_frames(c)
        same = [(i, nat[np.asarray(im.convert('RGBA')).tobytes()]) for i, im in vis if np.asarray(im.convert('RGBA')).tobytes() in nat]
        print(' equal to frames of', c, len(same), same[:30])
    k = 3
    W, x, y, rh, pos = 1900, 4, 4, 0, []
    for i, im in vis:
        b = im.resize((im.width * k, im.height * k), Image.NEAREST).convert('RGBA')
        if x + b.width + 6 > W:
            x, y, rh = 4, y + rh + 14, 0
        pos.append((i, b, x, y))
        x += b.width + 6
        rh = max(rh, b.height)
    c = Image.new('RGB', (W, y + rh + 16), (70, 70, 70))
    d = ImageDraw.Draw(c)
    for i, b, x, y in pos:
        d.text((x, y), str(i), fill=(255, 255, 0))
        c.paste(b, (x, y + 10), b)
    c.save(os.path.join(OUT, f'own_{sid}.png'))
    for n in maps:
        try:
            m = messages(mm, toc, n)
        except Exception as ex:  # noqa: BLE001
            print(' map', n, 'text err', repr(ex)[:100])
            continue
        print(' map', n, 'messages', len(m))
        for t in m[:14]:
            print('   ', repr(t)[:110])
pal_hits = {}
for f in os.listdir(DUMP):
    for p in ('df3ad574', '36a7f02f', '1223a1c0'):
        if p in f:
            pal_hits.setdefault(p, []).append(f)
print({k: (len(v), v[:4]) for k, v in pal_hits.items()})
