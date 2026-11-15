"""Draw-rect files of the 13 sets after install_0311: which names of each set / palette are missing from the pack, and which moved files have no
new file (candidates to restore from the backup).  python check_rects.py <backup_dir> [--restore]"""
import glob
import json
import os
import shutil
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(TOOLS)), 'xeno_bc7'))
from alias_dump_parts import PACK  # noqa: E402
from install_0311 import rect_names  # noqa: E402
from npc_rects import NPC, part_rect, sheet_words  # noqa: E402

SETS = '172669b371,179511abf3,195138629a,1c0f2c14f4,2be5277d28,6e595cab89,70a4dcc69d,9522cfbb67,a096333c67,bcc8990fb9,c75eb56e69,c7ad1d08fb,eaf637a98c'.split(',')
for sid in SETS:
    u = json.load(open(os.path.join(NPC, sid, 'uses.json')))
    names = rect_names(sid)
    per = {}
    for n in names:
        pal = n.split('-')[1]
        p = per.setdefault(pal, [0, 0])
        p[0] += 1
        p[1] += os.path.exists(os.path.join(PACK, n + '.bc7'))
    print(sid, {k: f'{v[1]}/{v[0]}' for k, v in per.items()})
bk = sys.argv[1]
moved = [os.path.basename(f)[:-4] for f in glob.glob(os.path.join(bk, '*.bc7'))]
gone = [n for n in moved if not os.path.exists(os.path.join(PACK, n + '.bc7'))]
print('moved', len(moved), 'without a new file', len(gone))
pals = {}
for n in gone:
    pals[n.split('-')[1]] = pals.get(n.split('-')[1], 0) + 1
print(pals)
if '--restore' in sys.argv:
    for n in gone:
        shutil.copy2(os.path.join(bk, n + '.bc7'), os.path.join(PACK, n + '.bc7'))
    print('restored', len(gone))
