"""Page-aligned HD for map NPCs that a map uploads in full-VRAM-width strips (01.11.2026).

Some maps load their VRAM in 1024x16-word strips (dump 4096x16): an NPC sheet is then part of an upload whose hash covers
the whole row, so the pack's upload-rect files (one per NPC block) never match and the NPC stays native, although it
is redrawn (bar map, soldier in green, sets m_44596de657 & twins). The core can fall back to the page-aligned pack
(option HD Replacement Cross-Mode Fallback): a file per (texture page 64x256 words, palette) in
<game>-texture-replacements-pages. Here every dumped page (core dump mode "both" -> <game>-texture-dump-pages) that
holds an NPC sheet texel for texel gets one: the page upscaled nearest x8 (everything else looks as before) with the
set's HD blocks from the pack (merged + seam-filled) pasted over the sheet's footprint.

  python npc_pages.py [--dump <pages dump dir>] [--dry]      (RetroArch closed for the real run)
Needs in the .opt: beetle_psx_hw_hd_replacement_fallback = "enabled". Log: pod/report/npc_pages.log.
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from elly934_finalize import write_bc7_from_psx  # noqa: E402

DUMP = r'<RETROARCH_DRIVE>\RetroArch\system\Xenogears (RUS)-texture-dump-pages'
OUT = r'<RETROARCH_DRIVE>\RetroArch\system\Xenogears (RUS)-texture-replacements-pages'
NPC = os.path.join(ROOT, 'extracted', 'npc_full')
LOG = os.path.join(ROOT, 'pod', 'report', 'npc_pages.log')
S = 8


def log(s):
    s = time.strftime('%d.%m %H:%M ') + s
    print(s, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(s + '\n')


def sets_by_palette():
    by = defaultdict(list)
    for sid in sorted(os.listdir(NPC)):
        d = os.path.join(NPC, sid)
        try:
            u = json.load(open(os.path.join(d, 'uses.json')))
            raw = json.load(open(os.path.join(d, 'pal.json')))['palettes_raw']
        except (OSError, ValueError, KeyError):
            continue
        for k, pal in enumerate(u['palettes']):
            if k < len(raw):
                by[pal].append((sid, raw[k], u['uses']))
    return by


def index_map(rgba, pal):
    """Dump colours (5-bit expanded) -> palette indices (-1 = colour not in the palette, 0 = transparent)."""
    a = rgba.astype(np.int32)
    c5 = (a[..., 0] >> 3) | ((a[..., 1] >> 3) << 5) | ((a[..., 2] >> 3) << 10)
    out = np.full(a.shape[:2], -1, np.int32)
    for i in range(len(pal) - 1, -1, -1):
        out[c5 == (pal[i] & 0x7fff)] = i
    out[a[..., 3] == 0] = 0
    return out


def footprint(use):
    """The use's blocks in page texels: [(x, y, w, h, block)] (4bpp: 4 texels per word)."""
    return [((b['x'] - use['sx']) * 4, b['y'] - use['sy'], b['w'] * 4, b['h'], b) for b in use['blocks']]


def build(rgba, pal_hash, cands):
    """HD page (PSX convention) for the first candidate set whose sheet is in this page texel for texel, or None."""
    for sid, pal, uses in cands:
        sheet = np.load(os.path.join(NPC, sid, 'page.npy')).astype(np.int32)
        if sheet.shape != rgba.shape[:2]:
            continue
        idx = index_map(rgba, pal)
        for use in uses:
            fp = footprint(use)
            files = [os.path.join(PACK, f"{b['hash']:x}-{pal_hash}.bc7") for _, _, _, _, b in fp]
            if not all(os.path.exists(f) for f in files):
                continue
            inside = np.zeros(sheet.shape, bool)
            for x, y, w, h, _ in fp:
                inside[max(0, y):y + h, max(0, x):x + w] = True
            if not inside.any() or not np.array_equal(idx[inside], sheet[inside]):
                continue
            hd = np.kron(bc7pack.tri_to_psx(rgba)[0], np.ones((S, S, 1), np.uint8))
            for (x, y, w, h, _), f in zip(fp, files):
                blk = read_bc7_level0(f)
                if blk.shape[:2] != (h * S, w * S):
                    break
                hd[y * S:(y + h) * S, x * S:(x + w) * S] = blk
            else:
                return sid, use['map'], hd
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump', default=DUMP)
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    t0 = time.time()
    by = sets_by_palette()
    os.makedirs(OUT, exist_ok=True)
    made, skipped = [], 0
    for f in sorted(os.listdir(a.dump)):
        if not f.endswith('.png') or '-' not in f:
            continue
        page_hash, pal_hash = f[:-4].split('-', 1)
        if pal_hash not in by:
            continue
        dst = os.path.join(OUT, f[:-4] + '.bc7')
        if os.path.exists(dst):
            skipped += 1
            continue
        rgba = np.asarray(Image.open(os.path.join(a.dump, f)).convert('RGBA'))
        r = build(rgba, pal_hash, by[pal_hash])
        if r is None:
            continue
        sid, use_map, hd = r
        if not a.dry and not write_bc7_from_psx(dst, hd):
            print('BC7 rules failed:', f)
            continue
        made.append((f[:-4], sid, use_map))
        print(f'  {f[:-4]}: set {sid} (HD of its map {use_map} blocks)', flush=True)
    log(f'NPC pages: {len(made)} built, {skipped} already there, {time.time() - t0:.0f} s' + (' (dry)' if a.dry else ''))


if __name__ == '__main__':
    main()
