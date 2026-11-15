r"""Map NPC sets re-extracted with every texture of their item (15.11.2026): the tex id of a piece chooses the image.

  python ai\redraw\gaps_1115\npc_fixed.py <set id> [...]       -> fixed\<set id>\ (hero-style folder) + fixed\<set id>.png
  python ai\redraw\gaps_1115\npc_fixed.py --scan               which sets of extracted/npc_full are cut wrong
tools/npc_maps.py keeps only the first image of a sub-file-4 item (sub4_pages) and part_rect's tex id is dropped by the
rect name readers, so a piece on texture 1 or 2 was cut from texture 0: Khan's flashback set 1ecec3878b (map 662, the
second image 1ebf4490 64x66 at VRAM 384,256) came out with pieces of other figures and was held back
(ai/prod/exclude_parts.txt). Here each piece is cut from image <tex id> of the item (ty-0 sets; a ty-1 set's texture k is
the VRAM page k pages to the right). Parts are named as before (r<tid>x..), so a frame differs from the old extraction
only where a piece is on a texture other than 0. Pieces of size 0 (the game sizes them elsewhere) are listed, not cut.
"""
import json
import mmap
import os
import sys

import numpy as np
from PIL import Image

from gcommon import HERE, NPC, ROOT, side_by_side
from sub4all import sub4_all
from extract_heroes import clut_hash  # noqa: E402
from mapvram import page_indices  # noqa: E402
from npc_maps import map_sets, rect_name, rgba_from_idx  # noqa: E402
from npc_tex import part_rect  # noqa: E402
from xfs import read_toc  # noqa: E402
from xspr import cluts, frames  # noqa: E402

OUT = os.path.join(HERE, 'fixed')


def idx_of(raw, w, h):
    a = np.frombuffer(raw, np.uint8)
    out = np.empty(a.size * 2, np.uint8)
    out[0::2], out[1::2] = a & 15, a >> 4
    return out.reshape(h, w * 4)


def textures(mm, toc, use, vram):
    """[4bpp index image per tex id] of a use (map, set index, sx, sy)."""
    items = sub4_all(mm, toc, use['map'])
    if use['set'] in items and items[use['set']]:
        return [idx_of(raw, w, h) for w, h, raw, _ in items[use['set']]]
    return [page_indices(vram, use['sx'] + 64 * k, use['sy']) for k in range(3) if use['sx'] + 64 * k < 1024]


def extract(mm, toc, nid):
    u = json.load(open(os.path.join(NPC, nid, 'uses.json')))
    use = u['uses'][0]
    sets, vram, _ = map_sets(mm, toc, use['map'])
    st = next(s for s in sets if s['i'] == use['set'])
    s = st['set']
    pals = cluts(s['clut_raw'])
    phs = [f'{clut_hash(c):x}' for c in pals]
    tex = textures(mm, toc, use, vram)
    fr = frames(s['meta'])
    root = os.path.join(OUT, nid)
    os.makedirs(os.path.join(root, 'parts'), exist_ok=True)
    zero, bad = [], []
    lay = []
    for k, f in enumerate(fr):
        out = []
        for p in f:
            r = part_rect(s['meta'], p['ref'])
            tid, sx, sy, w, h = r
            if not w or not h:
                zero.append((k, r))
                continue
            if tid >= len(tex) or sy + h > tex[tid].shape[0]:
                bad.append((k, r))
                continue
            ci = min(p['clut'], len(pals) - 1)
            name = f'{rect_name(r)}-{phs[ci]}.png'
            path = os.path.join(root, 'parts', name)
            if not os.path.exists(path):
                Image.fromarray(rgba_from_idx(tex[tid][sy:sy + h, sx:sx + w], pals[ci]), 'RGBA').save(path)
            out.append({'block': rect_name(r), **{q: p[q] for q in ('dx', 'dy', 'flipx', 'flipy', 'clut', 'mx', 'my', 'rot')}})
        lay.append(out)
    json.dump({'npc': {'palettes': phs, 'frames': lay}}, open(os.path.join(root, 'layout.json'), 'w'))
    json.dump({'palettes_raw': [list(map(int, c)) for c in pals]}, open(os.path.join(root, 'pal.json'), 'w'))
    np.savez(os.path.join(root, 'textures.npz'), *tex)
    json.dump({'source': use, 'textures': [t.shape for t in tex], 'zero_size': zero, 'off_texture': bad},
              open(os.path.join(root, 'info.json'), 'w'), default=int)
    return root, len(fr), zero, bad, len(tex)


def sheet(root, old):
    """Frames as cut now (top) and as extracted/npc_full cut them (bottom), x3."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    from ai_redraw import Hero
    new, prev = Hero(root), Hero(old)
    cells = []
    n = len(new.layout['npc']['frames'])
    for k in range(0, n, max(1, n // 12)):
        for h in (new, prev):
            try:
                img, _ = h.assemble(h.placements('npc', k))
            except Exception:  # noqa: BLE001
                img = Image.new('RGBA', (8, 8))
            a = np.asarray(img)
            rgb = np.zeros(a.shape[:2] + (3,), np.uint8)
            rgb[:] = (255, 0, 255)
            rgb[a[..., 3] > 0] = a[..., :3][a[..., 3] > 0]
            cells.append(np.repeat(np.repeat(rgb, 3, 0), 3, 1))
    side_by_side(cells).save(root + '.png')


def main():
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    if sys.argv[1:] == ['--scan']:
        rows = []
        for nid in sorted(os.listdir(NPC)):
            p = os.path.join(NPC, nid, 'layout.json')
            if not os.path.exists(p):
                continue
            lay = json.load(open(p))['npc']
            tids = {q['block'][1:q['block'].index('x')] for f in lay['frames'] for q in f}
            if tids - {'0'}:
                n = sum(1 for f in lay['frames'] if any(q['block'][1:q['block'].index('x')] != '0' for q in f))
                rows.append(f'{nid}: {n} of {len(lay["frames"])} frames have pieces on texture {sorted(tids - {"0"})}')
        open(os.path.join(HERE, 'fixed_scan.txt'), 'w').write('\n'.join(rows) + '\n')
        print('\n'.join(rows))
        return
    for nid in sys.argv[1:]:
        root, n, zero, bad, nt = extract(mm, toc, nid)
        sheet(root, os.path.join(NPC, nid))
        print(nid, f'{n} frames, {nt} textures, zero-size pieces {len(zero)}, pieces off their texture {len(bad)} ->', root + '.png')


if __name__ == '__main__':
    main()
