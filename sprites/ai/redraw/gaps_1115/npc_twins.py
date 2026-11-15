r"""Map NPC sets with no file in the pack whose picture another, drawn set already has (15.11.2026).

  python ai\redraw\gaps_1115\npc_twins.py                 match + previews twins\<set>.png, twins\twins.json
  python ai\redraw\gaps_1115\npc_twins.py --install <set>[,<set>...]   write the upload files of those sets (new names only)
The class of the ship corridor man (F6 2026-11-15T10-35-59-053, map 522): Timothy's sheet is uploaded whole (64x239,
63604b80) where the pack has Timothy only as the 16-row strips of maps 610/2004 (pilot p3h_timothy, set d8943ce397).
A target set (none of its uploads in the pack, scan_npc_uses.py) is a twin of a source set when every texel its frames
draw is the source page's texel at the same place (up to MAX_DIFF of them may differ: Timothy's two sheets differ in 24
texels). The source's HD page (its pack blocks, npc_rects.hd_sheet) is then cut by the target's own uploads; a palette
the source lacks is recoloured from its first one per texel index (battle_palettes.recolor_set.recolour).
Besides the sets of the scan, a name may be given that a report lacks: an upload of a twin set's page cut as the game
cut it (Timothy's 64x239 of d8943ce397's page) - see EXTRA.
Written names: twins\installed.txt (undo: delete them from the pack and the mod's pack).
"""
import argparse
import json
import os
import sys
import zlib

import numpy as np

from gcommon import HERE, NPC, PACK, ROOT, install_files, npc_set, pack_names, show, side_by_side
sys.path.insert(0, os.path.join(ROOT, 'ai', 'redraw', 'battle_palettes'))
from npc_rects import hd_sheet, sheet_words, write_bc7  # noqa: E402
from recolor_set import recolour  # noqa: E402
from seam_fill_npc import rect as part_rect  # noqa: E402
from npc_maps import rgba_from_idx  # noqa: E402

S = 8
MAX_DIFF = 0.01
OUT = os.path.join(HERE, 'twins')
# uploads reports name that no extracted use has: (source set, page rows) -> the name is crc32 of those rows' words
EXTRA = {'d8943ce397': [239]}


def used_mask(lay, shape):
    m = np.zeros(shape, bool)
    for f in lay['frames']:
        for p in f:
            sx, sy, w, h = part_rect(p['block'])
            m[sy:sy + h, sx:sx + w] = True
    return m


def sources(rows):
    """Sets whose uploads all have files under at least one palette: {set: [covered palettes]}."""
    return {k: [p for p, v in r['cov'].items() if v == r['blocks'] and r['blocks']] for k, r in rows.items()
            if any(v == r['blocks'] and r['blocks'] for v in r['cov'].values())}


def frame_rgb(lay, k, page_rgba, scale):
    """A layout frame assembled from a page (RGBA, texels x scale)."""
    rects = [part_rect(p['block']) + (p['dx'], p['dy'], p['flipx'], p['flipy']) for p in lay['frames'][k]]
    if not rects:
        return np.zeros((8, 8, 3), np.uint8)
    x0, y0 = min(r[4] for r in rects), min(r[5] for r in rects)
    W, H = max(r[4] + r[2] for r in rects) - x0, max(r[5] + r[3] for r in rects) - y0
    out = np.zeros((H * scale, W * scale, 3), np.uint8)
    out[:] = (255, 0, 255)
    for sx, sy, w, h, dx, dy, fx, fy in reversed(rects):
        c = page_rgba[sy * scale:(sy + h) * scale, sx * scale:(sx + w) * scale]
        if fx:
            c = c[:, ::-1]
        if fy:
            c = c[::-1]
        m = c[..., 3] > 0 if c.dtype == np.uint8 and scale == 1 else ~(c == 0).all(-1)
        X, Y = (dx - x0) * scale, (dy - y0) * scale
        out[Y:Y + c.shape[0], X:X + c.shape[1]][m] = c[..., :3][m]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', default='')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    have = pack_names()
    rows = json.load(open(os.path.join(HERE, 'npc_uses.json')))
    src = sources(rows)
    targets = [k for k, r in rows.items() if not any(r['cov'].values())]
    pages = {}

    def page(k):
        if k not in pages:
            pages[k] = npc_set(k)
        return pages[k]

    found = {}
    for t in targets:
        lay, u, idx, raw = page(t)
        m = used_mask(lay, idx.shape)
        if not m.any():
            continue
        best = None
        for s, pals in src.items():
            slay, su, sidx, sraw = page(s)
            if sidx.shape[1] != idx.shape[1]:
                continue
            h = min(sidx.shape[0], idx.shape[0])
            if m[h:].any():
                continue
            diff = (sidx[:h][m[:h]] != idx[:h][m[:h]]).mean()
            if diff <= MAX_DIFF and (best is None or diff < best[1]):
                best = (s, diff)
        if best:
            found[t] = {'source': best[0], 'diff': round(float(best[1]), 5), 'source_palettes': src[best[0]],
                        'palettes': u['palettes'], 'frames': len(lay['frames'])}
            print(t, '<-', best[0], f'diff {best[1]:.4f}', 'palettes', u['palettes'], 'source drawn under', src[best[0]], flush=True)
    for s in EXTRA:
        found.setdefault('extra:' + s, {'source': s, 'diff': 0.0, 'source_palettes': src.get(s, []),
                                        'palettes': npc_set(s)[1]['palettes'], 'frames': rows[s]['frames']})
    json.dump(found, open(os.path.join(OUT, 'twins.json'), 'w'), indent=1)
    print(len(found), 'twins of', len(targets), 'sets with no file')

    want = set(a.install.split(',')) if a.install else set()
    for t, info in found.items():
        s = info['source']
        slay, su, sidx, sraw = page(s)
        tid = s if t.startswith('extra:') else t
        tlay, tu, tidx, traw = page(tid)
        spal = info['source_palettes'][0]
        hd_src = hd_sheet(su['uses'], spal, sidx.shape)
        if hd_src is None:
            print(t, 'no HD sheet of the source under', spal)
            continue
        names, cells = {}, []
        for pal in tu['palettes']:
            if pal in info['source_palettes']:
                hd_pal = hd_sheet(su['uses'], pal, sidx.shape)
            else:
                sraw_i = su['palettes'].index(spal)
                hd_pal = recolour(hd_src, sidx, sraw[sraw_i], traw[tu['palettes'].index(pal)])
            uploads = []
            if t.startswith('extra:'):
                words = sheet_words(sidx.astype(np.uint16))
                for rows_n in EXTRA[s]:
                    crc = zlib.crc32(np.ascontiguousarray(words[:rows_n]).astype('<u2').tobytes()) & 0xffffffff
                    uploads.append((f"{crc:x}", 0, 0, 256, rows_n))
            else:
                for use in tu['uses']:
                    for b in use['blocks']:
                        uploads.append((f"{b['hash']:x}", (b['x'] - use['sx']) * 4, b['y'] - use['sy'], b['w'] * 4, b['h']))
            for h, x, y, w, hh in uploads:
                name = f'{h}-{pal}'
                if name in have or name in names:
                    continue
                crop = np.zeros((hh * S, w * S, 4), np.uint8)
                y1 = min(y + hh, hd_pal.shape[0] // S)
                if y1 > y and x >= 0:
                    crop[:(y1 - y) * S] = hd_pal[y * S:y1 * S, x * S:(x + w) * S]
                names[name] = crop
            # preview: 4 frames of the target, sprite (its own page) and HD (the source's page in this palette)
            ks = np.linspace(0, len(tlay['frames']) - 1, 4).astype(int)
            low = rgba_from_idx(tidx, traw[tu['palettes'].index(pal)])
            for k in ks:
                a1 = frame_rgb(tlay, k, low, 1)
                cells += [np.repeat(np.repeat(a1, S, 0), S, 1), frame_rgb(tlay, k, hd_pal, S)]
        side_by_side(cells).save(os.path.join(OUT, f'{t.replace(":", "_")}.png'))
        info['names'] = sorted(names)
        print(t, 'names to write', len(names), f'twins\\{t.replace(":", "_")}.png')
        if t in want or s in want and t.startswith('extra:'):
            stage = os.path.join(OUT, 'stage')
            os.makedirs(stage, exist_ok=True)
            for n, crop in names.items():
                if not write_bc7(os.path.join(stage, n + '.bc7'), np.ascontiguousarray(crop)):
                    sys.exit(f'{n}: BC7 failed')
            done = install_files(stage, list(names), os.path.join(OUT, 'installed.txt'))
            print(t, 'installed', len(done))
    json.dump(found, open(os.path.join(OUT, 'twins.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
