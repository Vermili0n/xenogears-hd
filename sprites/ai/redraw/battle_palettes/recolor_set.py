r"""A battle set's other palettes from the HD drawn for one (15.11.2026).

  python ai\redraw\battle_palettes\recolor_set.py <set id> <group> [--install]      (--install: RetroArch closed)
The game draws one battle sheet with several palettes: another enemy of the same shape (set 4c0acc20fc: the frames name
palette e004eaf1 only, and a pale one comes with 15a10496; F6 report xeno_port/out/frame_reports/2026-11-15T00-25-48-041).
The set's HD files exist under the palette its frames were drawn with, so the other enemies stay in original pixels.
Here, as npc_maps.derive_palette_pages does for the map NPCs: every texel's palette index is known (pages.npz), so the
HD pixels of that texel take the other palette's colour for it, keeping their shading (recolour()), softened over
about a texel. Then the same draw-rect files as battle_rects.py writes, under the other palette's name: only the rects whose
file exists under the drawn palette (the frames skipped at that install stay skipped), nothing in the pack overwritten.
Without --install: counts and preview_<set>.png (a frame: the sprite and the HD, each palette) beside this file.
Written names: written_<set>.txt beside this file (undo: delete them from the pack).
"""
import argparse
import json
import os
import sys
import zlib

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from alias_dump_parts import PACK  # noqa: E402
from battle_rects import BATTLE, hd_page, rect_variants, tex_id, write_bc7  # noqa: E402
from fix_apply import retroarch_running  # noqa: E402
from npc_maps import lut, rgba_from_idx  # noqa: E402
from npc_rects import sheet_words  # noqa: E402
from seam_fill import frame_interior  # noqa: E402
from seam_fill_npc import rect as part_rect  # noqa: E402

S = 8


def lab_of(table):
    return cv2.cvtColor(table[:, :3].reshape(1, -1, 3).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)[0]


def recolour(page, idx, src_raw, dst_raw):
    """The HD sheet (PNG alpha convention) of the source palette in the colours of another. A pixel is its texel's
    palette colour shaded: its lightness is scaled by the two colours' ratio, and its chroma moves by their difference
    in the measure the pixel is as light as the colour (a plain shift, as derive_palette_pages makes, tints the dark
    outlines: red-brown to grey turned them teal)."""
    s_lut, d_lut = lut(src_raw), lut(dst_raw)
    s_lab, d_lab = lab_of(s_lut), lab_of(d_lut)
    same = (s_lut[idx][..., 3] == 0) | (d_lut[idx][..., 3] == 0)
    ratio = ((d_lab[:, 0] + 5) / (s_lab[:, 0] + 5))[idx]
    ratio[same] = 1
    shift = (d_lab[:, 1:] - s_lab[:, 1:])[idx]
    shift[same] = 0
    fields = np.dstack([ratio, shift, s_lab[:, 0][idx]]).astype(np.float32)
    up = np.repeat(np.repeat(fields, S, 0), S, 1)
    up = np.dstack([cv2.GaussianBlur(np.ascontiguousarray(up[..., c]), (0, 0), S / 3) for c in range(4)])
    lab = cv2.cvtColor(np.ascontiguousarray(page[..., :3]).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)
    weight = np.clip((lab[..., 0] + 5) / (up[..., 3] + 5), 0, 1)
    lab[..., 0] = np.clip(lab[..., 0] * up[..., 0], 0, 100)
    lab[..., 1] += up[..., 1] * weight
    lab[..., 2] += up[..., 2] * weight
    out = page.copy()
    drawn = page[..., 3] > 0
    out[..., :3][drawn] = ((np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB), 0, 1) * 255 + 0.5).astype(np.uint8))[drawn]
    out[np.repeat(np.repeat(d_lut[idx][..., 3] == 0, S, 0), S, 1) & drawn, 3] = 0
    return out


def frame_picture(frame, sheets, pages, raw):
    """A layout frame: its sprite in the palette and the same from the HD sheets."""
    rects = [(tex_id(p['block']),) + tuple(part_rect(p['block'])) + (p['dx'] + p['mx'], p['dy'] + p['my'], p['flipx'], p['flipy']) for p in frame]
    x0, y0 = min(r[5] for r in rects), min(r[6] for r in rects)
    W, H = max(r[5] + r[3] for r in rects) - x0, max(r[6] + r[4] for r in rects) - y0
    low, high = np.zeros((H * S, W * S, 3), np.uint8), np.zeros((H * S, W * S, 3), np.uint8)
    low[:], high[:] = (255, 0, 255), (255, 0, 255)
    for t, sx, sy, w, h, x, y, fx, fy in rects:
        a = rgba_from_idx(sheets[t][sy:sy + h, sx:sx + w], raw)
        a = np.repeat(np.repeat(a, S, 0), S, 1)
        b = pages[t][sy * S:(sy + h) * S, sx * S:(sx + w) * S]
        if fx:
            a, b = a[:, ::-1], b[:, ::-1]
        if fy:
            a, b = a[::-1], b[::-1]
        X, Y = (x - x0) * S, (y - y0) * S
        for dst, src in ((low, a), (high, b)):
            m = src[..., 3] > 0
            dst[Y:Y + src.shape[0], X:X + src.shape[1]][m] = src[..., :3][m]
    return low, high


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('set_id')
    ap.add_argument('group')
    ap.add_argument('--frame', type=int, default=0, help='the frame of the preview')
    ap.add_argument('--install', action='store_true')
    a = ap.parse_args()
    if a.install and retroarch_running():
        sys.exit('RetroArch is running - close it first')
    d = os.path.join(BATTLE, a.set_id)
    z = np.load(os.path.join(d, 'pages.npz'))
    sheets = [z[k] for k in z.files]
    words = [sheet_words(s.astype(np.uint16)) for s in sheets]
    lay = json.load(open(os.path.join(d, 'layout.json')))['npc']
    pals = lay['palettes']
    raw = json.load(open(os.path.join(d, 'pal.json')))['palettes_raw']
    parts = os.path.join(ROOT, 'ai', 'prod_work', a.group, 'parts')
    drawn = {}
    for f in lay['frames']:
        for p in f:
            drawn.setdefault(pals[min(p['clut'], len(pals) - 1)], set()).add(p['block'])
    if len(drawn) != 1:
        sys.exit(f'the frames name {len(drawn)} palettes: this tool is for a set drawn with one')
    src = next(iter(drawn))
    blocks = {}
    for b in drawn[src]:
        blocks.setdefault(tex_id(b), set()).add(b)
    inner = frame_interior([(lay, d)], lambda h, k: parts)
    pages = {src: {t: hd_page(parts, [(b, src) for b in bs], sheets[t].shape, inner) for t, bs in blocks.items()}}
    written, kept, absent, failed = [], 0, 0, 0
    for dst in pals:
        if dst == src:
            continue
        pages[dst] = {t: recolour(pages[src][t], sheets[t], raw[pals.index(src)], raw[pals.index(dst)]) for t in blocks}
        for t, bs in sorted(blocks.items()):
            names = set()
            for x, y, w, h in sorted(set().union(*[rect_variants(*part_rect(b)) for b in bs])):
                if y + h > sheets[t].shape[0] or x + w > 64:
                    continue
                crc = zlib.crc32(np.ascontiguousarray(words[t][y:y + h, x:x + w]).astype('<u2').tobytes()) & 0xffffffff
                if crc in names:
                    continue
                names.add(crc)
                if not os.path.exists(os.path.join(PACK, f'{crc:x}-{src}.bc7')):
                    absent += 1
                    continue
                path = os.path.join(PACK, f'{crc:x}-{dst}.bc7')
                if os.path.exists(path) or os.path.exists(path[:-4] + '.png'):
                    kept += 1
                    continue
                crop = pages[dst][t][y * S:(y + h) * S, x * 4 * S:(x + w) * 4 * S]
                if not crop.any():
                    absent += 1
                    continue
                if not a.install:
                    written.append(f'{crc:x}-{dst}')
                elif write_bc7(path, crop):
                    written.append(f'{crc:x}-{dst}')
                else:
                    failed += 1
    cells = []
    for pal in pals:
        low, high = frame_picture(lay['frames'][a.frame], sheets, pages[pal], raw[pals.index(pal)])
        cells += [low, high]
    H, W = max(c.shape[0] for c in cells), sum(c.shape[1] + 8 for c in cells)
    sheet = Image.new('RGB', (W, H), (40, 40, 40))
    x = 0
    for c in cells:
        sheet.paste(Image.fromarray(c), (x, 0))
        x += c.shape[1] + 8
    sheet.save(os.path.join(HERE, f'preview_{a.set_id}.png'))
    if a.install and written:
        with open(os.path.join(HERE, f'written_{a.set_id}.txt'), 'a', encoding='utf-8') as f:
            f.writelines(n + '.bc7\n' for n in written)
    print(f'{a.set_id}: drawn under {src}, other palettes {[p for p in pals if p != src]}: '
          f'{"written" if a.install else "to write"} {len(written)}, already in the pack {kept}, '
          f'no file under {src} (or empty) {absent}, BC7 failed {failed}; preview_{a.set_id}.png (per palette: sprite, HD)')


if __name__ == '__main__':
    main()
