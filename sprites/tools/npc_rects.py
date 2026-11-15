"""Draw-rect HD files for NPC sprite parts (01.11.2026; core: third try of the cross-mode fallback).

When a map loads an NPC sheet inside full-width VRAM strips, neither the pack's block files (upload rect) nor a page
file match. The core then hashes the rect each part is drawn from like an upload (crc32 of its 16-bit VRAM words) and
looks that name up in the pack. The words of a part's rect come from the set's sheet only, so the names are computed
here for every part of every rendered set, map-independently: the HD crop of the rect (from the set's merged,
seam-filled pack blocks) goes into the pack as <rect crc>-<palette>.bc7.

Draw rect of a layout part (sx, sy, w, h; 4bpp page texels), measured on dumps (rects.txt, maps with the white-robe
and the soldier NPCs): x = sx >> 2, width = ((sx + w + 1) >> 2) - (sx >> 2) words, y = sy, height = h - 1 rows.

  python npc_rects.py [--only <set id>,...] [--workers 12] [--dry]      (RetroArch closed)
Existing pack files are never overwritten. List of written names: pod/report/npc_rects_written.txt (undo = delete them).
"""
import argparse
import json
import os
import sys
import time
import zlib
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from install_parts import excluded_groups  # noqa: E402
from seam_fill_npc import rect as part_rect  # noqa: E402

NPC = os.path.join(ROOT, 'extracted', 'npc_full')
LOG = os.path.join(ROOT, 'pod', 'report', 'npc_rects.log')
WRITTEN = os.path.join(ROOT, 'pod', 'report', 'npc_rects_written.txt')
S = 8


def log(s):
    s = time.strftime('%d.%m %H:%M ') + s
    print(s, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(s + '\n')


def write_bc7(path, hd):
    """elly934_finalize.write_bc7_from_psx with a per-process temp name: twin sets share parts, so two workers can
    write the same name at once (same content) - the loser of the rename just skips."""
    lv = [hd]
    while lv[-1].shape[0] % 2 == 0 and lv[-1].shape[1] % 2 == 0:
        lv.append(bc7pack.gen_mip(lv[-1]))
    tr = (hd == 0).all(-1)
    flags = ((bc7pack.TRANSPARENT if tr.any() else 0) | (bc7pack.OPAQUE if (~tr & (hd[..., 3] == 0)).any() else 0)
             | (bc7pack.SEMI if (hd[..., 3] == 255).any() else 0))
    enc, failed, _ = bc7pack.encode_levels(lv)
    if failed:
        return False
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'wb') as f:
        f.write(bc7pack.pack_file(enc, hd.shape[1], hd.shape[0], flags))
    try:
        os.replace(tmp, path)
    except OSError:
        os.remove(tmp)
        return False
    return True


def sheet_words(sheet):
    """4bpp indices (H x 256) -> VRAM words (H x 64), low nibble first."""
    s = np.zeros((sheet.shape[0], 256), np.uint16)
    s[:, :min(sheet.shape[1], 256)] = sheet[:, :256]
    return s[:, 0::4] | (s[:, 1::4] << 4) | (s[:, 2::4] << 8) | (s[:, 3::4] << 12)


def hd_sheet(uses, pal, shape):
    """The set's HD sheet (PSX convention, page texels x8) from the first use whose blocks are all in the pack."""
    for use in uses:
        files = [(b, os.path.join(PACK, f"{b['hash']:x}-{pal}.bc7")) for b in use['blocks']]
        if not files or not all(os.path.exists(f) for _, f in files):
            continue
        hd = np.zeros((shape[0] * S, 256 * S, 4), np.uint8)
        ok = True
        for b, f in files:
            x, y, w, h = (b['x'] - use['sx']) * 4, b['y'] - use['sy'], b['w'] * 4, b['h']
            blk = read_bc7_level0(f)
            if blk.shape[:2] != (h * S, w * S) or x < 0 or y < 0 or x + w > 256 or y >= shape[0]:   # strip-wide uses: next use
                ok = False
                break
            y1 = min(y + h, shape[0])
            hd[y * S:y1 * S, x * S:(x + w) * S] = blk[:(y1 - y) * S]
        if ok:
            return hd
    return None


def one_set(args):
    sid, dry = args
    d = os.path.join(NPC, sid)
    try:
        sheet = np.load(os.path.join(d, 'page.npy')).astype(np.uint16)
        lay = json.load(open(os.path.join(d, 'layout.json')))['npc']
        u = json.load(open(os.path.join(d, 'uses.json')))
    except (OSError, KeyError, ValueError):
        return sid, [], 0, 'no data'
    words = sheet_words(sheet)
    H = sheet.shape[0]
    rects = set()
    for f in lay['frames']:
        for p in f:
            sx, sy, w, h = part_rect(p['block'])
            x0, ww, hh = sx >> 2, ((sx + w + 1) >> 2) - (sx >> 2), h - 1
            if ww > 0 and hh > 0 and sy + hh <= H and x0 + ww <= 64:
                rects.add((x0, sy, ww, hh))
    written, skipped = [], 0
    for pal in u['palettes']:
        hd = None
        for x0, y0, ww, hh in sorted(rects):
            crc = zlib.crc32(np.ascontiguousarray(words[y0:y0 + hh, x0:x0 + ww]).astype('<u2').tobytes())
            name = f'{crc:x}-{pal}'
            path = os.path.join(PACK, name + '.bc7')
            if os.path.exists(path) or os.path.exists(os.path.join(PACK, name + '.png')):
                skipped += 1
                continue
            if hd is None:
                hd = hd_sheet(u['uses'], pal, sheet.shape)
                if hd is None:
                    return sid, written, skipped, f'no HD blocks for {pal}'
            crop = hd[y0 * S:(y0 + hh) * S, x0 * 4 * S:(x0 + ww) * 4 * S]
            if not crop.any():
                continue
            if dry or write_bc7(path, np.ascontiguousarray(crop)):
                written.append(name)
    return sid, written, skipped, ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    skip = excluded_groups()
    sets = sorted({os.path.basename(m['hero_dir']) for m in meta.values()
                   if 'npc_full' in m['hero_dir'] and m['group'] not in skip})
    if a.only:
        sets = [s for s in sets if s in set(a.only.split(','))]
    t0 = time.time()
    n_w = n_s = 0
    with Pool(a.workers) as pool, open(WRITTEN, 'a', encoding='utf-8') as wf:
        for k, (sid, written, skipped, err) in enumerate(pool.imap_unordered(one_set, [(s, a.dry) for s in sets]), 1):
            n_w += len(written)
            n_s += skipped
            if not a.dry:
                wf.writelines(n + '\n' for n in written)
            if err:
                print(f'  {sid}: {err}', flush=True)
            if k % 50 == 0:
                print(f'  {k}/{len(sets)} sets, {n_w} files, {time.time() - t0:.0f} s', flush=True)
    log(f'NPC rects: {len(sets)} sets, {n_w} files written, {n_s} names already in the pack, '
        f'{time.time() - t0:.0f} s' + (' (dry)' if a.dry else ''))


if __name__ == '__main__':
    main()
