r"""From the pod's renders of gaps_1115 to pack files (16.11.2026). Stages everything, writes only new names unless told.

  python ai\redraw\gaps_1115\install_pod.py multitex  [--sets a,b] [--install]
  python ai\redraw\gaps_1115\install_pod.py balthasar --board a|b  [--install]
  python ai\redraw\gaps_1115\install_pod.py rest [--roni-seed 7|11|23|42] [--only roni46,gear456,f2410,f2427,f3837] [--install]
Every run: compose (compose_set, the production's colour steps; head close-ups where the job had them) -> slice
(batch_redraw slice --scale 8 --exact-mask --ring 0 --uv-compensate) -> pack files into inst_<job>\stage\ ->
lists inst_<job>\new.txt (names neither pack has) and inst_<job>\overwrite.txt (names the pack has: the old drawing) +
inst_<job>\preview_<group>.png (top: the sprite, bottom: the new HD as the game stretches it).
--install copies ONLY the new names into both packs (log inst_<job>\installed.txt; undo = delete them).
Overwrites are never done here: pink_install.py-style backup + the user's word, per group (see README of the job).

multitex / balthasar = map NPC sets (projection per texture): a part r<k>x.. belongs to texture k of its set's item.
  Texture k's HD page = xBR of the texture + the sliced parts on it, other palettes recoloured (npc_maps
  derive_palette_pages, per texture). Files per use of the set:
   sub-file-4 uses (ty 0): image k of the item is its own upload: <crc of image k>-<pal>, the page cut to its rows;
   VRAM-file uses (ty 1): texture 0 = the page at (sx, sy) as before; texture k >= 1 = the 64-word page of the map's
     VRAM whose texels equal texture k (searched; none found -> reported, skipped): its upload blocks cut as
     npc_maps.cmd_project cuts them;
   and every part's draw rect (npc_rects: crc of the rect's words) for maps that load sheets in strips.
rest:
  roni46   only the head piece r0x07y5aw0dh0d (the game draws it 13x13 at uv 7,90) goes into the sheet
           86ef69b7-98d6171a (set 44f27d4ef0's upload on all four maps): an OVERWRITE -> staged only, with
           preview roni46.png (sprite | the pack now | patched).
  gear456  frames 21-30 with block '0' left out (HeroZ); the parts and their h-1 aliases (gear_redraw install).
  f2410, f2427, f3837  streamed files: parts named by their own block crc (hero-style folders), fix_magenta, BC7,
           seam fill (id_chi/retarget.stage_parts' steps).
"""
import argparse
import json
import mmap
import os
import shutil
import sys
import zlib

import numpy as np
from PIL import Image

from gcommon import HERE, MOD_PACK, NPC, PACK, ROOT, hd, install_files, side_by_side
import ai_redraw  # noqa: E402
import batch_redraw  # noqa: E402
import bc7pack  # noqa: E402
import compose_set  # noqa: E402
from alias_dump_parts import read_bc7_level0  # noqa: E402
from elly934_finalize import write_bc7_from_psx  # noqa: E402
from fix_magenta import fix as fix_magenta  # noqa: E402
from gear_redraw import block_bytes, write_bc7 as write_bc7_rgba  # noqa: E402
from mapvram import page_indices  # noqa: E402
from npc_maps import derive_palette_pages, map_sets, rgba_from_idx, xbr_page  # noqa: E402
from npc_rects import sheet_words  # noqa: E402
from seam_fill import fill_interior, frame_interior  # noqa: E402
from seam_fill_npc import rect as part_rect  # noqa: E402
from sub4all import sub4_all
from xfs import read_toc  # noqa: E402

S = 8
ORIG_PLACEMENTS = ai_redraw.Hero.placements


def placements_without_zero(self, setkey, fi):
    s = self.layout[setkey]
    out = []
    for p in s['frames'][fi]:
        if p['block'] == '0':
            continue
        pal = s['palettes'][min(p['clut'], len(s['palettes']) - 1)]
        img = self.part(p['block'], pal)
        out.append({**p, 'pal': pal, 'w': img.width, 'h': img.height, 'x': p['dx'] + p['mx'], 'y': p['dy'] + p['my']})
    return out


def run(module, *argv):
    sys.argv = [module.__name__ + '.py'] + [str(x) for x in argv]
    module.main()


def disc():
    fh = open(os.path.join(ROOT, 'work', 'disc1_user.bin'), 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    return mm, read_toc(mm)


# ---------------------------------------------------------------- compose + slice
def prepare(job, picks):
    r"""inst_<job>\render\meta.json (the job's meta with dups) + picked\ (the chosen render of every name).
    picks: {meta name: path of the render to use for it (and of its head, '<name>__head')}."""
    inst = os.path.join(HERE, f'inst_{job}')
    render, picked = os.path.join(inst, 'render'), os.path.join(inst, 'picked')
    os.makedirs(render, exist_ok=True)
    os.makedirs(picked, exist_ok=True)
    return inst, render, picked


def compose_slice(inst, render, picked, group, hero_dir, heads):
    gw = os.path.join(inst, group)
    work = os.path.join(gw, 'work')
    os.makedirs(work, exist_ok=True)
    argv = ['--render', render, '--res', picked, '--work', work, '--name', group, '--out-scale', '8', '--offset-key', group]
    if not heads:
        argv.append('--no-head')
    run(compose_set, *argv)
    reds = [f[:-8] for f in os.listdir(work) if f.endswith('_red.png')]
    if not reds:
        return gw, []
    only = ','.join(f"{r.rsplit('_', 1)[0]}:{int(r.rsplit('_', 1)[1])}" for r in reds)
    if os.path.isdir(os.path.join(gw, 'parts')):
        shutil.rmtree(os.path.join(gw, 'parts'))
    tag = os.path.relpath(gw, os.path.join(ROOT, 'ai')).replace('\\', '/')
    run(batch_redraw, 'slice', '--heroes', tag, '--hero-dir', os.path.join(ROOT, hero_dir), '--scale', S, '--exact-mask',
        '--ring', '0', '--uv-compensate', '--only', only)
    return gw, reds


def write_meta(render, meta):
    for m in meta.values():
        m.setdefault('dups', [])
    json.dump(meta, open(os.path.join(render, 'meta.json'), 'w'), indent=0)


# ---------------------------------------------------------------- NPC projection per texture
def texture_pages(set_dir, parts):
    """{tid: {pal: HD page (PSX alpha convention as xbr_page gives: OPAQUE)}}, {tid: index image}."""
    tex = np.load(os.path.join(set_dir, 'textures.npz')) if os.path.exists(os.path.join(set_dir, 'textures.npz')) else None
    idxs = [tex[k] for k in tex.files] if tex is not None else [np.load(os.path.join(set_dir, 'page.npy'))]
    pals_raw = json.load(open(os.path.join(set_dir, 'pal.json')))['palettes_raw']
    phs = json.load(open(os.path.join(set_dir, 'layout.json')))['npc']['palettes']
    pages, covs = {}, {}
    for f in sorted(os.listdir(parts)):
        if not f.endswith('.png'):
            continue
        rn, pal = f[:-4].rsplit('-', 1)
        if pal not in phs:
            continue
        tid = int(rn[1:rn.index('x')], 16)
        if tid >= len(idxs):
            continue
        sx, sy, w, h = part_rect(rn)
        pg = pages.setdefault(tid, {})
        cv = covs.setdefault(tid, {})
        if pal not in pg:
            pg[pal] = xbr_page(idxs[tid], pals_raw[phs.index(pal)], S)
            cv[pal] = np.zeros(pg[pal].shape[:2], bool)
        part = np.asarray(Image.open(os.path.join(parts, f)).convert('RGBA'))
        H, W = min(part.shape[0], h * S), min(part.shape[1], w * S)
        pg[pal][sy * S:sy * S + H, sx * S:sx * S + W] = part[:H, :W]
        cv[pal][sy * S:sy * S + H, sx * S:sx * S + W] |= part[:H, :W, 3] > 0
    for tid in pages:
        derive_palette_pages(pages[tid], covs[tid], idxs[tid], pals_raw, phs, S)
    return pages, idxs


def find_page(vram, want, sy_hint):
    """(x, y) of the 64-word VRAM page whose 4-bit texels equal `want` (rows of want), or None."""
    h = want.shape[0]
    for y in sorted({sy_hint, 0, 256}):
        for x in range(0, 1024 - 63, 64):
            if y + h <= 512 and (page_indices(vram, x, y, 64, h) == want).all():
                return x, y
    return None


def project(set_id, set_dir, parts, stage, mm, toc):
    """Pack files of an NPC set's pages per use; -> {name: rgba (PSX convention)}."""
    pages, idxs = texture_pages(set_dir, parts)
    uses = json.load(open(os.path.join(NPC, set_id, 'uses.json')))['uses']
    out, notes = {}, []
    for use in uses:
        sub4 = any(b.get('src') == 'sub4' for b in use['blocks'])
        if sub4:
            imgs = sub4_all(mm, toc, use['map']).get(use['set'], [])
            for k, (w, h, raw, crc) in enumerate(imgs):
                if k not in pages:
                    continue
                a = np.frombuffer(raw, np.uint8)
                ix = np.empty(a.size * 2, np.uint8)
                ix[0::2], ix[1::2] = a & 15, a >> 4
                if k >= len(idxs) or ix.reshape(h, w * 4).shape != idxs[k][:h].shape or (ix.reshape(h, w * 4) != idxs[k][:h]).any():
                    notes.append(f'map {use["map"]}: image {k} is not texture {k} - skipped')
                    continue
                for pal, pg in pages[k].items():
                    out[f'{crc:x}-{pal}'] = pg[:h * S]
            continue
        _, vram, blocks = map_sets(mm, toc, use['map'])
        for k in pages:
            if k == 0:
                x0, y0 = use['sx'], use['sy']
            else:
                at = find_page(vram, idxs[k], use['sy'])
                if at is None:
                    notes.append(f'map {use["map"]}: texture {k} not found in its VRAM - skipped')
                    continue
                x0, y0 = at
            PH = idxs[k].shape[0]
            for b in blocks:
                if not (b['x'] < x0 + 64 and b['x'] + b['w'] > x0 and b['y'] < y0 + PH and b['y'] + b['h'] > y0):
                    continue
                px0, py0 = (b['x'] - x0) * 4, b['y'] - y0
                for pal, pg in pages[k].items():
                    yy0, yy1 = max(0, py0), min(PH, py0 + b['h'])
                    xx0, xx1 = max(0, px0), min(256, px0 + b['w'] * 4)
                    if yy1 <= yy0 or xx1 <= xx0:
                        continue
                    o = np.zeros((b['h'] * S, b['w'] * 4 * S, 4), np.uint8)
                    o[(yy0 - py0) * S:(yy1 - py0) * S, (xx0 - px0) * S:(xx1 - px0) * S] = pg[yy0 * S:yy1 * S, xx0 * S:xx1 * S]
                    out[f"{b['hash']:x}-{pal}"] = o
    # draw-rect names (npc_rects formula: x = sx >> 2, width = ((sx + w + 1) >> 2) - (sx >> 2) words, h - 1 rows)
    for f in os.listdir(parts):
        if not f.endswith('.png'):
            continue
        rn, pal = f[:-4].rsplit('-', 1)
        tid = int(rn[1:rn.index('x')], 16)
        if tid not in pages or pal not in pages[tid]:
            continue
        sx, sy, w, h = part_rect(rn)
        x, wd, hh = sx >> 2, ((sx + w + 1) >> 2) - (sx >> 2), h - 1
        if hh < 1 or x + wd > 64 or sy + hh > idxs[tid].shape[0]:
            continue
        words = sheet_words(idxs[tid].astype(np.uint16))
        crc = zlib.crc32(np.ascontiguousarray(words[sy:sy + hh, x:x + wd]).astype('<u2').tobytes()) & 0xffffffff
        out.setdefault(f'{crc:x}-{pal}', pages[tid][pal][sy * S:(sy + hh) * S, x * 4 * S:(x + wd) * 4 * S])
    return out, notes


def to_psx(page):
    """xbr_page / parts give PNG alpha (OPAQUE 255 = opaque, 0 = transparent): -> PSX convention for write_bc7_from_psx."""
    out = page.copy()
    t = page[..., 3] == 0
    out[..., :3][(out[..., :3] == 0).all(-1) & ~t] = 1
    out[..., 3] = 0
    out[t] = 0
    return out


def stage_files(inst, files):
    st = os.path.join(inst, 'stage')
    os.makedirs(st, exist_ok=True)
    new, over, failed = [], [], []
    for name, img in sorted(files.items()):
        if not write_bc7_from_psx(os.path.join(st, name + '.bc7'), np.ascontiguousarray(to_psx(img))):
            failed.append(name)
            continue
        (over if os.path.exists(os.path.join(PACK, name + '.bc7')) else new).append(name)
    return new, over, failed


def game_preview(set_dir, parts, frames, path):
    """Top: the sprite; bottom: the sliced parts as the game stretches them ((w-1) x (h-1) texels over the part)."""
    h = ai_redraw.Hero(set_dir)
    sk = 'npc' if 'npc' in h.layout else next(iter(h.layout))
    cells = []
    for fi in frames:
        if not h.layout[sk]['frames'][fi]:
            continue
        places = h.placements(sk, fi)
        frame, (x0, y0) = h.assemble(places)
        low = np.zeros((frame.height * S, frame.width * S, 3), np.uint8)
        low[:] = (255, 0, 255)
        sp = np.asarray(frame.resize((frame.width * S, frame.height * S), Image.NEAREST))
        low[sp[..., 3] > 0] = sp[..., :3][sp[..., 3] > 0]
        high = np.zeros_like(low)
        high[:] = (255, 0, 255)
        for p in places:
            fp = os.path.join(parts, f"{p['block']}-{p['pal']}.png")
            w, hh = p['w'], p['h']
            if os.path.exists(fp):
                a = np.asarray(Image.open(fp).convert('RGBA'))
                tw, th = (w - 1) * S if w > 1 else w * S, (hh - 1) * S if hh > 1 else hh * S
                rgb = np.asarray(Image.fromarray(np.ascontiguousarray(a[:th, :tw, :3])).resize((w * S, hh * S), Image.LANCZOS))
                op = np.asarray(Image.fromarray((a[:th, :tw, 3] > 0).astype(np.uint8) * 255).resize((w * S, hh * S), Image.NEAREST)) > 0
            else:
                a = np.asarray(h.part(p['block'], p['pal']).resize((w * S, hh * S), Image.NEAREST))
                rgb, op = a[..., :3], a[..., 3] > 0
            if p['flipx']:
                rgb, op = rgb[:, ::-1], op[:, ::-1]
            if p['flipy']:
                rgb, op = rgb[::-1], op[::-1]
            X, Y = (p['x'] - x0) * S, (p['y'] - y0) * S
            high[Y:Y + hh * S, X:X + w * S][op] = rgb[op]
        cells.append(np.vstack([low, np.full((8, low.shape[1], 3), 40, np.uint8), high]))
    if cells:
        side_by_side(cells).save(path)


def finish(inst, new, over, failed, notes, install):
    # the lists cover the whole stage (runs for some sets add to it): new = not in the RetroArch pack
    st = os.path.join(inst, 'stage')
    staged = sorted(f[:-4] for f in os.listdir(st) if f.endswith('.bc7')) if os.path.isdir(st) else []
    installed = set(open(os.path.join(inst, 'installed.txt')).read().split()) if os.path.exists(os.path.join(inst, 'installed.txt')) else set()
    new = [n for n in staged if not os.path.exists(os.path.join(PACK, n + '.bc7'))]
    over = [n for n in staged if os.path.exists(os.path.join(PACK, n + '.bc7')) and n + '.bc7' not in installed]
    open(os.path.join(inst, 'new.txt'), 'w').write(''.join(n + '\n' for n in new))
    open(os.path.join(inst, 'overwrite.txt'), 'w').write(''.join(n + '\n' for n in over))
    print(f'staged: new {len(new)}, would overwrite {len(over)} (not written), BC7 failed {len(failed)}')
    for n in notes:
        print('  note:', n)
    if install:
        done = install_files(os.path.join(inst, 'stage'), new, os.path.join(inst, 'installed.txt'))
        print(f'installed {len(done)} new names into both packs ({PACK}, {MOD_PACK}); undo: inst_*\\installed.txt')


# ---------------------------------------------------------------- jobs
def cmd_multitex(a):
    d = os.path.join(HERE, 'pod_multitex')
    meta = json.load(open(os.path.join(d, 'meta.json')))
    res = os.path.join(d, 'res_42', 'v4')
    inst, render, picked = prepare('multitex', None)
    if a.install_only:
        # install the staged new names of the chosen sets only (their names recomputed from the sliced parts, no
        # compose / slice / BC7 again): sets whose group is not yet in the pack go whole, nothing is overwritten
        want = set(a.sets.split(',')) if a.sets else set()
        groups = {}
        for m in meta.values():
            groups.setdefault(m['group'], m['hero_dir'])
        mm, toc = disc()
        names = []
        for g, hdir in sorted(groups.items()):
            set_id = os.path.basename(hdir)
            if set_id in want or g in want:
                files, _ = project(set_id, os.path.join(ROOT, hdir), os.path.join(inst, g, 'parts'), inst, mm, toc)
                names += [n for n in files if not os.path.exists(os.path.join(PACK, n + '.bc7'))]
        names = sorted(set(names))
        st = os.path.join(inst, 'stage')
        lost = [n for n in names if not os.path.exists(os.path.join(st, n + '.bc7'))]
        in_mod = [n for n in names if os.path.exists(os.path.join(MOD_PACK, n + '.bc7'))]
        print(f'{sorted(want)}: {len(names)} names the RetroArch pack lacks; not staged {len(lost)}, '
              f'already in the mod pack {len(in_mod)} (left as they are)')
        if a.dry:
            open(os.path.join(inst, 'install_only_dry.txt'), 'w').write(''.join(n + '\n' for n in names))
            print('dry: nothing written; the list: inst_multitex/install_only_dry.txt')
            return
        if lost:
            sys.exit(f'staged files missing: {lost[:5]}')
        done = install_files(os.path.join(inst, 'stage'), sorted(set(names)), os.path.join(inst, 'installed.txt'))
        print(f'installed {len(done)} new names of {sorted(want)} into both packs; undo: inst_multitex/installed.txt')
        return
    write_meta(render, meta)
    for f in os.listdir(res):
        shutil.copyfile(os.path.join(res, f), os.path.join(picked, f))
    groups = {}
    for m in meta.values():
        groups.setdefault(m['group'], m['hero_dir'])
    want = set(a.sets.split(',')) if a.sets else None
    mm, toc = disc()
    new_all, over_all, failed_all, notes_all = [], [], [], []
    for g, hdir in sorted(groups.items()):
        set_id = os.path.basename(hdir)
        if want and set_id not in want and g not in want:
            continue
        heads = any(m.get('head_job') for m in meta.values() if m['group'] == g)
        gw, reds = compose_slice(inst, render, picked, g, hdir, heads)
        if not reds:
            print(g, 'no renders yet')
            continue
        files, notes = project(set_id, os.path.join(ROOT, hdir), os.path.join(gw, 'parts'), inst, mm, toc)
        new, over, failed = stage_files(inst, files)
        new_all += new
        over_all += over
        failed_all += failed
        notes_all += [f'{g}: {n}' for n in notes]
        n = len(json.load(open(os.path.join(ROOT, hdir, 'layout.json')))['npc']['frames'])
        game_preview(os.path.join(ROOT, hdir), os.path.join(gw, 'parts'), list(range(0, n, max(1, n // 10)))[:10],
                     os.path.join(inst, f'preview_{g}.png'))
        print(f'{g}: {len(reds)} frames composed, files {len(files)} (new {len(new)}, overwrite {len(over)})', flush=True)
    finish(inst, new_all, over_all, failed_all, notes_all, a.install)


def cmd_balthasar(a):
    d = os.path.join(HERE, 'pod_balthasar')
    meta = json.load(open(os.path.join(d, 'meta.json')))
    res = os.path.join(d, 'res_42', 'v4')
    inst, render, picked = prepare('balthasar', None)
    write_meta(render, meta)
    for f in os.listdir(res):
        if f.startswith(a.board + '__'):
            shutil.copyfile(os.path.join(res, f), os.path.join(picked, f[len(a.board) + 2:]))
    g = 'm_48c502a64f'
    hdir = 'extracted/npc_full/48c502a64f'
    gw, reds = compose_slice(inst, render, picked, g, hdir, True)
    mm, toc = disc()
    files, notes = project('48c502a64f', os.path.join(ROOT, hdir), os.path.join(gw, 'parts'), inst, mm, toc)
    new, over, failed = stage_files(inst, files)
    n = len(json.load(open(os.path.join(ROOT, hdir, 'layout.json')))['npc']['frames'])
    game_preview(os.path.join(ROOT, hdir), os.path.join(gw, 'parts'), list(range(0, n, 4)), os.path.join(inst, f'preview_{a.board}.png'))
    finish(inst, new, over, failed, notes, a.install)


def stage_hero_parts(inst, hero_dir, parts, aliases=None):
    """Hero-style parts (named by the game's own block crc) -> BC7 with fix_magenta and seam fill; h-1 aliases."""
    lay = json.load(open(os.path.join(hero_dir, 'layout.json')))
    inner = frame_interior([(v, hero_dir) for v in lay.values()], lambda h, k: os.path.join(h, 'parts'))
    st = os.path.join(inst, 'stage')
    os.makedirs(os.path.join(inst, 'magenta'), exist_ok=True)
    os.makedirs(st, exist_ok=True)
    new, over, failed = [], [], []
    for f in sorted(os.listdir(parts)):
        if not f.endswith('.png'):
            continue
        name = f[:-4]
        png = os.path.join(parts, f)
        fix_magenta(png, os.path.join(inst, 'magenta'))
        blk, pal = name.split('-')
        rgba = np.asarray(Image.open(png).convert('RGBA')).astype(np.int16)
        rgba, _ = fill_interior(rgba, None, S, rgba[..., 3] == 0, inner.get((blk, pal)))
        targets = [(name, rgba)]
        if aliases and name in aliases:
            w, h, b = aliases[name]
            if h > 1:
                targets.append(('%x-%s' % (zlib.crc32(b[:(w // 2) * (h - 1)]) & 0xffffffff, pal), rgba[:(h - 1) * S]))
        for tn, img in targets:
            if not write_bc7_rgba(os.path.join(st, tn + '.bc7'), img):
                failed.append(tn)
                continue
            (over if os.path.exists(os.path.join(PACK, tn + '.bc7')) else new).append(tn)
    return new, over, failed


def cmd_rest(a):
    d = os.path.join(HERE, 'pod_rest')
    meta = json.load(open(os.path.join(d, 'meta.json')))
    inst, render, picked = prepare('rest', None)
    write_meta(render, meta)
    # renders: res_v4_<seed>/v4 and res_v2_42/v2; seed-suffixed names (roni46) take the picked seed
    for sub in os.listdir(d):
        if not sub.startswith('res_'):
            continue
        for tag in ('v4', 'v2'):
            rd = os.path.join(d, sub, tag)
            if not os.path.isdir(rd):
                continue
            for f in os.listdir(rd):
                n = f[:-4]
                if '__s' in n:
                    base, seed = n.rsplit('__s', 1)
                    if seed != str(a.roni_seed):
                        continue
                    n = base
                shutil.copyfile(os.path.join(rd, f), os.path.join(picked, n + '.png'))
    only = set(a.only.split(',')) if a.only else None
    groups = {}
    for m in meta.values():
        groups.setdefault(m['group'], m['hero_dir'])
    new_all, over_all, failed_all, notes = [], [], [], []
    for g, hdir in sorted(groups.items()):
        if only and g not in only:
            continue
        hero_dir = os.path.join(ROOT, hdir)
        heads = any(m.get('head_job') for m in meta.values() if m['group'] == g)
        ai_redraw.Hero.placements = placements_without_zero if g == 'gear456' else ORIG_PLACEMENTS
        gw, reds = compose_slice(inst, render, picked, g, hdir, heads)
        if not reds:
            print(g, 'no renders yet')
            continue
        parts = os.path.join(gw, 'parts')
        if g == 'roni46':
            new, over, failed = roni_patch(inst, parts)
        elif g == 'gear456':
            raw = block_bytes(os.path.join(hero_dir, 'index.csv'))
            new, over, failed = stage_hero_parts(inst, hero_dir, parts, raw)
            # only the names the pack lacks: the frames' other parts are in the pack from the production
        else:
            new, over, failed = stage_hero_parts(inst, hero_dir, parts)
        new_all += new
        over_all += over
        failed_all += failed
        lay = json.load(open(os.path.join(hero_dir, 'layout.json')))
        sk = next(iter(lay))
        frames = sorted(int(r.rsplit('_', 1)[1]) for r in reds)[:10]
        game_preview(hero_dir, parts, frames, os.path.join(inst, f'preview_{g}.png'))
        print(f'{g}: {len(reds)} frames, new {len(new)}, overwrite {len(over)} ({sk})', flush=True)
    ai_redraw.Hero.placements = ORIG_PLACEMENTS
    finish(inst, new_all, over_all, failed_all, notes, a.install)


RONI_SHEET = '86ef69b7-98d6171a'
RONI_PIECE = 'r0x07y5aw0dh0d'


def roni_patch(inst, parts):
    """The head piece's HD into the pack's sheet at texels (7, 90): an overwrite, staged only."""
    pf = [f for f in os.listdir(parts) if f.startswith(RONI_PIECE + '-')]
    if not pf:
        return [], [], [RONI_SHEET]
    piece = np.asarray(Image.open(os.path.join(parts, pf[0])).convert('RGBA'))
    sheet = read_bc7_level0(os.path.join(PACK, RONI_SHEET + '.bc7')).copy()
    sx, sy, w, h = part_rect(RONI_PIECE)
    region = sheet[sy * S:(sy + h) * S, sx * S:(sx + w) * S]
    psx = to_psx(piece[:h * S, :w * S])
    keep = ~(psx == 0).all(-1)
    region[keep] = psx[keep]
    st = os.path.join(inst, 'stage')
    os.makedirs(st, exist_ok=True)
    if not write_bc7_from_psx(os.path.join(st, RONI_SHEET + '.bc7'), np.ascontiguousarray(sheet)):
        return [], [], [RONI_SHEET]
    before = read_bc7_level0(os.path.join(PACK, RONI_SHEET + '.bc7'))
    z = slice(max(0, (sy - 4) * S), (sy + h + 4) * S), slice(max(0, (sx - 4) * S), (sx + w + 4) * S)
    view = lambda p: np.where((p == 0).all(-1)[..., None], np.array([255, 0, 255], np.uint8), p[..., :3]).astype(np.uint8)
    set_dir = os.path.join(HERE, 'fixed', 'roni46')
    idx = np.load(os.path.join(set_dir, 'page.npy'))
    raw = json.load(open(os.path.join(set_dir, 'pal.json')))['palettes_raw'][0]
    o = rgba_from_idx(idx, raw)
    o = np.repeat(np.repeat(o, S, 0), S, 1)[z]
    side_by_side([view(np.where(o[..., 3:] > 0, o, 0).astype(np.uint8)), view(before[z]), view(sheet[z])]).save(
        os.path.join(inst, 'roni46.png'))
    return [], [RONI_SHEET], []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('job', choices=['multitex', 'balthasar', 'rest'])
    ap.add_argument('--sets', default='')
    ap.add_argument('--board', default='a', choices=['a', 'b'])
    ap.add_argument('--roni-seed', type=int, default=7)
    ap.add_argument('--only', default='')
    ap.add_argument('--install', action='store_true')
    ap.add_argument('--install-only', action='store_true', help='multitex: install the staged new names of --sets, no redo')
    ap.add_argument('--dry', action='store_true', help='with --install-only: list, write nothing')
    a = ap.parse_args()
    {'multitex': cmd_multitex, 'balthasar': cmd_balthasar, 'rest': cmd_rest}[a.job](a)


if __name__ == '__main__':
    main()
