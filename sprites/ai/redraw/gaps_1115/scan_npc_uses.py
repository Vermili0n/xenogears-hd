r"""Map NPC sets (extracted/npc_full) whose VRAM uploads have no file in the pack, per palette (15.11.2026).
  python scan_npc_uses.py  -> npc_uses.json + a table on stdout
For every set and every palette: how many of its uses' upload blocks have <block crc>-<palette> in the pack.
A set with some palettes covered and others not = recolour class (derive_palette_pages); a set with no file at all and a
twin set (same layout, page nearly equal) that has files = the same picture under another upload; none at all = not drawn."""
import json
import os

import numpy as np

from gcommon import HERE, NPC, pack_names


def main():
    have = pack_names()
    rows = {}
    for nid in sorted(os.listdir(NPC)):
        p = os.path.join(NPC, nid, 'uses.json')
        if not os.path.exists(p):
            continue
        u = json.load(open(p))
        blocks = sorted({f"{b['hash']:x}" for use in u['uses'] for b in use['blocks']})
        cov = {pal: sum(f'{b}-{pal}' in have for b in blocks) for pal in u['palettes']}
        rows[nid] = {'frames': u['frames'], 'palettes': u['palettes'], 'blocks': len(blocks), 'cov': cov,
                     'maps': sorted({x['map'] for x in u['uses']}), 'sub4': any(b.get('src') == 'sub4' for x in u['uses'] for b in x['blocks'])}
    json.dump(rows, open(os.path.join(HERE, 'npc_uses.json'), 'w'), indent=0)
    full = [k for k, r in rows.items() if all(v == r['blocks'] for v in r['cov'].values())]
    none = [k for k, r in rows.items() if not any(r['cov'].values())]
    some_pal = [k for k, r in rows.items() if any(v == r['blocks'] for v in r['cov'].values()) and not all(v == r['blocks'] for v in r['cov'].values())]
    part = [k for k in rows if k not in full and k not in none and k not in some_pal]
    print(f'sets {len(rows)}: all blocks under every palette {len(full)}, none at all {len(none)}, '
          f'complete under some palettes only {len(some_pal)}, partly {len(part)}')
    for title, ks in (('none at all', none), ('some palettes only', some_pal), ('partly', part)):
        print('==', title)
        for k in ks:
            r = rows[k]
            print(k, r['frames'], 'frames, blocks', r['blocks'], r['cov'], 'maps', r['maps'][:6], 'sub4' if r['sub4'] else '')


if __name__ == '__main__':
    main()
