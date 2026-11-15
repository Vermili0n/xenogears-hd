"""Name every NPC sprite set from the game's own scripts: the entity that wears set NN speaks lines 'Name\\n"..."'.

  python npc_names.py   -> ai/npc_names_script.json {nid: {"name": best, "share": .., "votes": {name: n}}}
Disc 1 (USA text). Votes = number of messages of each speaker inside scripts of entities that use the set.
"""
import json
import mmap
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from fieldscript import message_ids, parse, sprite_sets  # noqa: E402
from speakers import messages, speaker  # noqa: E402
from xfs import field_archive_index, get_file, lzss_decompress, read_toc  # noqa: E402


def main():
    setmap = {}
    base = os.path.join(ROOT, 'extracted', 'npc_full')
    for nid in os.listdir(base):
        p = os.path.join(base, nid, 'uses.json')
        if os.path.exists(p):
            for u in json.load(open(p))['uses']:
                setmap[(u['map'], u['set'])] = nid
    f = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    votes = defaultdict(Counter)
    for n in range(606, 2066, 2):
        try:
            d = get_file(mm, toc[n])
            idx = field_archive_index(d)
            b = lzss_decompress(d[idx[5]['offset']:idx[5]['end']])[0][:idx[5]['size']]
            t = lzss_decompress(d[idx[7]['offset']:idx[7]['end']])[0][:idx[7]['size']]
            ents, _ = parse(b)
        except Exception:
            continue
        msgs = messages(t)
        for c in ents:
            sets = [s for s in sprite_sets(c) if (n, s) in setmap]
            if len(sets) != 1:  # entity switching sprites: ambiguous
                continue
            nid = setmap[(n, sets[0])]
            for _, k in message_ids(c, len(msgs)):
                s = speaker(msgs[k])
                if s:
                    votes[nid][s] += 1
    out = {}
    for nid, c in votes.items():
        name, v = c.most_common(1)[0]
        out[nid] = {'name': name, 'share': round(v / sum(c.values()), 2), 'n': v, 'votes': dict(c.most_common(5))}
    json.dump(out, open(os.path.join(ROOT, 'ai', 'npc_names_script.json'), 'w'), indent=1)
    print(len(out), 'NPC sets named')


if __name__ == '__main__':
    main()
