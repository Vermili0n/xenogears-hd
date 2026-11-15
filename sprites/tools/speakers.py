"""Who speaks on which map (USA disc 1 text) and which NPC sprite set stands there -> name of every NPC set.

  python speakers.py                    -> ai/speakers.json {map: [names]}, ai/npc_names.json {nid: [[name, score, shared, maps_name, maps_set], ...]}
Field text = sub-file 7 of map file N: u16 count, u16 offsets, messages in a 1-byte table
(u32 count, u16 offsets; 0x20.. 'A'..'Z', 0x3D.. 'a'..'z', 0x10 space, 0x01 newline, 0x58 quote). A message 'Name\\n"..."' is spoken by Name.
Score = Jaccard of the map sets of the speaker name and of the NPC set; a set's own name is the one that appears
with it on (nearly) every map and rarely elsewhere.
"""
import json
import mmap
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from xfs import field_archive_index, get_file, lzss_decompress, read_toc  # noqa: E402

PUNCT = {0x10: ' ', 0x01: '\n', 0x02: '\n', 0x14: '.', 0x12: ',', 0x13: '-', 0x5c: "'", 0x57: '!', 0x60: '?', 0x58: '"',
         0x0f: ' ', 0x5b: '&'}
for i in range(26):
    PUNCT[0x20 + i] = chr(65 + i)
    PUNCT[0x3D + i] = chr(97 + i)
for i in range(10):
    PUNCT[0x16 + i] = str(i)  # guess; digits are not needed for names


def decode(b):
    return ''.join(PUNCT.get(c, '') for c in b)


def messages(dec):
    if len(dec) < 4:
        return []
    n = int.from_bytes(dec[0:4], 'little')  # u32 count, then u16 offsets
    if n > 2000:
        return []
    offs = [int.from_bytes(dec[4 + 2 * i:6 + 2 * i], 'little') for i in range(n)]
    if not offs or max(offs) > len(dec) or n > 2000:
        return []
    out = []
    for i, o in enumerate(offs):
        end = offs[i + 1] if i + 1 < n and offs[i + 1] > o else len(dec)
        out.append(dec[o:end])
    return out


def speaker(msg):
    """'Name\\n"...' -> Name (1-3 words, starts with a capital)."""
    nl = msg.find(0x01)
    if nl <= 0 or nl > 30 or nl + 1 >= len(msg) or msg[nl + 1] != 0x58:
        return None
    name = decode(msg[:nl]).strip()
    if not name or not name[0].isupper() or len(name.split()) > 3:
        return None
    return name


def main():
    f = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    sp = {}
    for n in range(606, 2066, 2):
        try:
            d = get_file(mm, toc[n])
            idx = field_archive_index(d)
            x = idx[7]
            dec, _ = lzss_decompress(d[x['offset']:x['end']])
            dec = dec[:x['size']]
        except Exception:
            continue
        names = sorted({s for s in (speaker(m) for m in messages(dec)) if s})
        if names:
            sp[n] = names
    json.dump(sp, open(os.path.join(ROOT, 'ai', 'speakers.json'), 'w'), indent=0)
    name_maps = defaultdict(set)
    for n, names in sp.items():
        for s in names:
            name_maps[s].add(int(n))
    idx = json.load(open(os.path.join(ROOT, 'extracted', 'npc_all', 'index.json')))
    res = {}
    for nid, v in idx.items():
        ms = set(v['maps'])
        sc = []
        for s, nm in name_maps.items():
            inter = len(ms & nm)
            if inter:
                sc.append([s, round(inter / len(ms | nm), 3), inter, len(nm), len(ms)])
        sc.sort(key=lambda t: (-t[1], -t[2]))
        res[nid] = sc[:6]
    json.dump(res, open(os.path.join(ROOT, 'ai', 'npc_names.json'), 'w'), indent=0)
    print(len(sp), 'maps with speakers;', len(name_maps), 'names')
    top = sorted(name_maps.items(), key=lambda t: -len(t[1]))[:60]
    print(', '.join(f'{k}({len(v)})' for k, v in top))


if __name__ == '__main__':
    main()
