r"""Pieces of size 0 in the frames of the map NPC sets (15.11.2026; Roni Fatima's head, F6 2026-11-15T15-11-11-094).
  python zero_pieces.py -> zero_pieces.json + stdout
A frame's part record (tex id, sx, sy, w, h) with w = h = 0 is dropped by npc_maps extract (it keeps w and h > 0), but
the game draws it, sized elsewhere (Roni's frame 46: record 07,5a,0,0 drawn as 13x13 at uv 7,90). Such a piece was never
redrawn: on the HD sheet its texels are the xBR stand-in of the original (the "hood" over Roni's head). Here every set
of extracted/npc_full is read again from its first use and every zero-size record listed (frame, sx, sy) with whether
the HD sheet in the pack has a picture there and whether any other part of the layout covers those texels."""
import json
import mmap
import os

from gcommon import HERE, NPC, ROOT
from npc_maps import map_sets
from npc_tex import part_rect
from xfs import read_toc
from xspr import frames


def main():
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    cache, out = {}, {}
    for nid in sorted(os.listdir(NPC)):
        p = os.path.join(NPC, nid, 'uses.json')
        if not os.path.exists(p):
            continue
        use = json.load(open(p))['uses'][0]
        if use['map'] not in cache:
            try:
                cache[use['map']] = map_sets(mm, toc, use['map'])[0]
            except Exception:  # noqa: BLE001
                cache[use['map']] = []
        st = next((s for s in cache[use['map']] if s['i'] == use['set']), None)
        if st is None:
            continue
        try:
            fr = frames(st['set']['meta'])
        except Exception:  # noqa: BLE001
            continue
        z = []
        for k, f in enumerate(fr):
            for q in f:
                r = part_rect(st['set']['meta'], q['ref'])
                if r[3] == 0 or r[4] == 0:
                    z.append([k, r[0], r[1], r[2], r[3], r[4]])
        if z:
            out[nid] = z
    json.dump(out, open(os.path.join(HERE, 'zero_pieces.json'), 'w'), indent=0)
    n = sum(len(v) for v in out.values())
    print(f'{len(out)} sets with zero-size pieces, {n} pieces in all')
    for k, v in sorted(out.items(), key=lambda kv: -len(kv[1]))[:40]:
        print(k, len(v), 'frames', sorted({x[0] for x in v})[:12], 'at', sorted({(x[2], x[3]) for x in v})[:6])


if __name__ == '__main__':
    main()
