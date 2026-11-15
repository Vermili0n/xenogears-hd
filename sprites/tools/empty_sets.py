"""NPC sets whose frames came out empty from npc_maps: what is in their meta; which ones hold their pixels inside the set."""
import json
import mmap
import os
import struct
import sys

ROOT = r'<XENO_SPRITES>'
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from npc_maps import sub_data  # noqa: E402
from xfs import read_toc  # noqa: E402
from xspr import cluts, frames, parse_set, pixel_blocks, u24  # noqa: E402

BASE = os.path.join(ROOT, 'extracted', 'npc_full')
names = json.load(open(os.path.join(ROOT, 'ai', 'npc_names_script.json'), encoding='utf-8'))
fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
toc = read_toc(mm)
rows, total = [], 0
for sid in sorted(os.listdir(BASE)):
    f = os.path.join(BASE, sid, 'layout.json')
    if not os.path.exists(f):
        continue
    total += 1
    fr = json.load(open(f))['npc']['frames']
    if any(fr):
        continue
    u = json.load(open(os.path.join(BASE, sid, 'uses.json')))
    use = u['uses'][0]
    sub = sub_data(mm, toc, use['map'], 3)
    base = u24(sub, 4 + 4 * use['set'])
    s = parse_set(sub, base)
    meta = s['meta']
    hdr = struct.unpack_from('<H', meta, 0)[0]
    cnt, bl = 0, {}
    p256 = bool(hdr & 0x8000)
    if not p256:
        cnt, _, bl = pixel_blocks(meta)
    px = sum(len(v[3]) for v in bl.values())
    rows.append((sid, (names.get(sid) or {}).get('name'), u['frames'], [x['map'] for x in u['uses']], 'p256' if p256 else 'own pixels', len(bl), px, u['palettes'][0]))
print('sets', total, 'empty', len(rows))
for r in rows:
    print(r)
