"""Draw-rect HD files for a battle sprite set (03.11.2026; the core's third lookup, see npc_rects.py).

A battle set's sheets go to VRAM whole, so no block file matches; with hd_replacement_fallback the core hashes the rect
each part is drawn from: crc32 of its VRAM words + palette. Dump of Big Joe's battle (rects.txt): all 1027 rows are
explained by the words of his sheets. The rect depends on how the quad lies on screen, so one part has several: the first
texel moves by -1..+1 and the end by 0..+2 texels, the first row by 0..+1 (height h - 1). Every variant gets a file, cut from
the set's HD sheet: the shader maps the rect to the whole file, so the sheet's texels stay where the part's UVs expect them.
The variants cover all 644 taller rows of the dump. One-row rects of taller parts (flat shadows, probably, not checked) stay native.

  python battle_rects.py <set id> <group> [--skip-frames 63-68] [--dump-from N] [--replace] [--dry]     (RetroArch closed)
--replace: rewrite this tool's earlier files (names in battle_rects_written.txt), e.g. after fix_magenta.py.
Parts: ai/prod_work/<group>/parts. Existing pack files are not overwritten. Written names: pod/report/battle_rects_written.txt.
--skip-frames: frames whose parts stay native (objects the LoRA turned into the character).
--dump-from N: also the rows with a palette of the set, from line N of rects.txt in the dump folder (taller than one row).
"""
import argparse
import json
import os
import sys
import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402
from alias_dump_parts import PACK  # noqa: E402
from fix_apply import retroarch_running  # noqa: E402
from npc_rects import sheet_words  # noqa: E402
from seam_fill import fill_interior, frame_interior  # noqa: E402
from seam_fill_npc import rect as part_rect  # noqa: E402

BATTLE = os.path.join(ROOT, 'extracted', 'battle')
DUMP = r'<RETROARCH_DRIVE>\RetroArch\system\Xenogears (RUS)-texture-dump'
WRITTEN = os.path.join(ROOT, 'pod', 'report', 'battle_rects_written.txt')
S = 8


def tex_id(block):
    return int(block[1:block.index('x')], 16)


def rect_variants(sx, sy, w, h):
    """Word rects (x, y, width, height) a part of the sheet can be drawn from."""
    out = set()
    for u0 in (sx - 1, sx, sx + 1):
        for u1 in (sx + w, sx + w + 1, sx + w + 2):
            x, end = max(u0, 0) >> 2, u1 >> 2
            for e in (end, ((sx + w) >> 2) + 1):
                if e > x and h > 1:
                    for y in (sy, sy + 1):
                        out.add((x, y, e - x, h - 1))
    return out


def dump_rows(pals, start, origins):
    """Tall rows of the dump with a palette of the set -> {(tex id, palette): {word rect}}. origins: {tex id: (x, y)} in VRAM."""
    out = {}
    with open(os.path.join(DUMP, 'rects.txt')) as f:
        rows = f.read().splitlines()[start:]
    for ln in rows:
        a = ln.split()
        pal = a[0].split('-')[1]
        x, y, w, h = (int(v) for v in a[1:5])
        if pal not in pals or h < 2:
            continue
        for t, (ox, oy) in origins.items():
            if ox <= x < ox + 64 and oy <= y:
                out.setdefault((t, pal), set()).add((x - ox, y - oy, w, h))
    return out


def hd_page(parts, keys, shape, inner):
    """HD sheet in the PNG alpha convention from the sliced parts of one sheet and palette."""
    page = np.zeros((shape[0] * S, 256 * S, 4), np.uint8)
    for block, pal in keys:
        f = os.path.join(parts, f'{block}-{pal}.png')
        if not os.path.exists(f):
            continue
        a = np.asarray(Image.open(f).convert('RGBA')).astype(np.int16)
        a, _ = fill_interior(a, None, S, a[..., 3] == 0, inner.get((block, pal)))
        a = np.clip(a, 0, 255).astype(np.uint8)
        sx, sy, w, h = part_rect(block)
        H, W = a.shape[:2]
        dst = page[sy * S:sy * S + H, sx * S:sx * S + W]
        H, W = dst.shape[:2]
        m = a[:H, :W, 3] > 0
        dst[m] = a[:H, :W][m]
    return page


def write_bc7(path, rgba):
    lv, flags = bc7pack.levels_of(np.ascontiguousarray(rgba))
    enc, failed, _ = bc7pack.encode_levels(lv)
    if failed:
        return False
    with open(path + '.tmp', 'wb') as f:
        f.write(bc7pack.pack_file(enc, rgba.shape[1], rgba.shape[0], flags))
    os.replace(path + '.tmp', path)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('set_id')
    ap.add_argument('group')
    ap.add_argument('--skip-frames', default='')
    ap.add_argument('--dump-from', type=int)
    ap.add_argument('--origins', default='0:320,256;1:384,256', help='sheets in VRAM, only for --dump-from')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--replace', action='store_true', help='rewrite files listed in battle_rects_written.txt')
    a = ap.parse_args()
    if not a.dry and retroarch_running():
        raise SystemExit('RetroArch is running - close it first')
    d = os.path.join(BATTLE, a.set_id)
    z = np.load(os.path.join(d, 'pages.npz'))
    sheets = [z[k] for k in z.files]
    words = [sheet_words(s.astype(np.uint16)) for s in sheets]
    lay = json.load(open(os.path.join(d, 'layout.json')))['npc']
    pals = lay['palettes']
    skip = set()
    for r in filter(None, a.skip_frames.split(',')):
        lo, _, hi = r.partition('-')
        skip |= set(range(int(lo), int(hi or lo) + 1))
    used = {}
    for fi, f in enumerate(lay['frames']):
        if fi in skip:
            continue
        for p in f:
            used.setdefault((tex_id(p['block']), pals[min(p['clut'], len(pals) - 1)]), set()).add(p['block'])
    extra = {}
    if a.dump_from is not None:
        org = {int(x.split(':')[0]): tuple(int(v) for v in x.split(':')[1].split(',')) for x in a.origins.split(';')}
        extra = dump_rows(set(pals), a.dump_from, org)
    parts = os.path.join(ROOT, 'ai', 'prod_work', a.group, 'parts')
    inner = {} if a.dry else frame_interior([(lay, d)], lambda h, k: os.path.join(parts))
    ours = set()  # --replace: files this tool wrote earlier may be rewritten, other pack files never
    if a.replace and os.path.exists(WRITTEN):
        ours = set(open(WRITTEN, encoding='utf-8').read().split())
    written, skipped, empty, failed, names, rewritten = [], 0, 0, 0, set(), 0
    for (t, pal), blocks in sorted(used.items()):
        rects = set().union(*[rect_variants(*part_rect(b)) for b in blocks]) | extra.get((t, pal), set())
        page = None if a.dry else hd_page(parts, [(b, pal) for b in blocks], sheets[t].shape, inner)
        H = sheets[t].shape[0]
        for x, y, w, h in sorted(rects):
            if y + h > H or x + w > 64:
                continue
            crc = zlib.crc32(np.ascontiguousarray(words[t][y:y + h, x:x + w]).astype('<u2').tobytes()) & 0xffffffff
            name = f'{crc:x}-{pal}'
            if name in names:
                continue
            names.add(name)
            path = os.path.join(PACK, name + '.bc7')
            if os.path.exists(path) and name not in ours:
                skipped += 1
                continue
            if a.dry:
                continue
            crop = page[y * S:(y + h) * S, x * 4 * S:(x + w) * 4 * S]
            if not crop.any():
                empty += 1
                continue
            if write_bc7(path, crop):
                if name in ours:
                    rewritten += 1
                else:
                    written.append(name)
            else:
                failed += 1
    if not a.dry and written:
        with open(WRITTEN, 'a', encoding='utf-8') as f:
            f.writelines(n + '\n' for n in written)
    print(f'names {len(names)}, written {len(written)}, rewritten {rewritten}, already in the pack {skipped}, empty {empty}, BC7 failed {failed}' + (' (dry)' if a.dry else ''))
    return names


if __name__ == '__main__':
    main()
