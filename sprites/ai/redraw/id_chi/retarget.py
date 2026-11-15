r"""Id's chi attacks (file 3833) in HD from the HD of his battle set (15.11.2026). No new pictures are drawn.

  python ai\redraw\id_chi\retarget.py              match, composites, slice, BC7 + seam fill into stage\, preview.png
  python ai\redraw\id_chi\retarget.py --install    the same, then the staged .bc7 copied into the pack (RetroArch closed)
While Id uses chi the game streams his sprite block by block from file 3833 (39 frames, 357 blocks; found by
find_set.py from the names of two F6 reports), and the pack has no file under those names: he turns to original pixels.
Every one of the 39 frames is, texel for texel, a frame of his battle set b88399f123 (file 2721, sheets), which is
drawn: group b_b88399f123. So each frame's composite (ai/prod_work/b_b88399f123/work/npc_<k>_red.png) is laid under
the 3833 frame and sliced by 3833's own cut: batch_redraw slice as the production runs it, fix_magenta, BC7, seam fill.
Only names the pack does not have are written; the list: installed.txt (undo: delete them from the pack).
"""
import argparse
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import batch_redraw  # noqa: E402
import bc7pack  # noqa: E402
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from elly934_finalize import write_bc7_from_psx  # noqa: E402
from fix_apply import retroarch_running  # noqa: E402
from fix_magenta import fix as fix_magenta  # noqa: E402
from seam_fill import fill_interior, frame_interior  # noqa: E402

S = 8
TARGET = os.path.join(HERE, 'extracted', 'id_chi')
TARGET_SET = '3833_0'
SOURCE = os.path.join(ROOT, 'extracted', 'battle', 'b88399f123')
SOURCE_WORK = os.path.join(ROOT, 'ai', 'prod_work', 'b_b88399f123', 'work')
PREVIEW = [17, 25, 4, 12, 30, 35]


def opaque_box(a):
    ys, xs = np.nonzero(a[..., 3] > 0)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def match_frames(target, source):
    """{target frame: (source frame, dx, dy)}: the source frame whose texels are the target's, and where the source's
    assembled picture lies on the target's."""
    frames = []
    for k in range(len(source.layout['npc']['frames'])):
        img, _ = source.assemble(source.placements('npc', k))
        a = np.asarray(img)
        box = opaque_box(a)
        frames.append((a[box[1]:box[3], box[0]:box[2]], box))
    out = {}
    for fi in range(len(target.layout[TARGET_SET]['frames'])):
        img, _ = target.assemble(target.placements(TARGET_SET, fi))
        a = np.asarray(img)
        box = opaque_box(a)
        cut = a[box[1]:box[3], box[0]:box[2]]
        for k, (b, sbox) in enumerate(frames):
            if b.shape == cut.shape and (b[..., 3] > 0).tolist() == (cut[..., 3] > 0).tolist() and not (b[b[..., 3] > 0] != cut[cut[..., 3] > 0]).any():
                out[fi] = (k, box[0] - sbox[0], box[1] - sbox[1])
                break
        else:
            sys.exit(f'{TARGET_SET}:{fi} is no frame of the battle set')
    return out


def composites(target, matches, work):
    for fi, (k, dx, dy) in matches.items():
        img, _ = target.assemble(target.placements(TARGET_SET, fi))
        red = Image.open(os.path.join(SOURCE_WORK, f'npc_{k:03d}_red.png')).convert('RGB')
        canvas = Image.new('RGB', (img.width * S, img.height * S), red.getpixel((red.width // 2, red.height // 2)))
        canvas.paste(red, (dx * S, dy * S))
        canvas.save(os.path.join(work, f'{TARGET_SET}_{fi:03d}_red.png'))


def stage_parts(inst):
    """Every sliced part as .bc7 with its seams filled (seam_fill_all.one, on the staged file)."""
    lay = json.load(open(os.path.join(TARGET, 'layout.json')))
    inner = frame_interior([(v, TARGET) for v in lay.values()], lambda h, k: os.path.join(h, 'parts'))
    out = os.path.join(HERE, 'stage')
    os.makedirs(out, exist_ok=True)
    os.makedirs(os.path.join(inst, 'parts_magenta'), exist_ok=True)
    names, magenta, filled_all = [], 0, 0
    for f in sorted(os.listdir(os.path.join(inst, 'parts'))):
        name = f[:-4]
        png = os.path.join(inst, 'parts', f)
        magenta += bool(fix_magenta(png, os.path.join(inst, 'parts_magenta')))
        dst = os.path.join(out, name + '.bc7')
        _, res, info, _ = bc7pack.convert_one((png, dst))
        if res != 'ok':
            sys.exit(f'{name}: BC7 {res} {info}')
        block, pal = name.split('-')
        hd = read_bc7_level0(dst).astype(np.int16)
        mask = inner.get((block, pal))
        if mask is not None and mask.any() and hd.shape[:2] == (mask.shape[0] * S, mask.shape[1] * S):
            fixed, filled = fill_interior(hd, None, S, (hd == 0).all(-1), mask)
            if filled:
                fixed[..., :3][(fixed[..., :3] == 0).all(-1) & ~(fixed == 0).all(-1)] = 1
                if not write_bc7_from_psx(dst, fixed):
                    sys.exit(f'{name}: BC7 after the seam fill failed')
                filled_all += 1
        names.append(name)
    print(f'staged {len(names)} parts, magenta fixed in {magenta}, seams filled in {filled_all}')
    return names


def game_frame(h, fi):
    """The frame as the game shows it (a part's picture stretched from its first (w-1) x (h-1) texels), from stage\\ or
    the pack; a part without a picture as its original texels."""
    places = h.placements(TARGET_SET, fi)
    frame, (x0, y0) = h.assemble(places)
    out = np.zeros((frame.height * S, frame.width * S, 3), np.uint8)
    out[:] = (255, 0, 255)
    for p in places:
        w, hh = p['w'], p['h']
        name = f"{p['block']}-{p['pal']}"
        path = next((q for q in (os.path.join(HERE, 'stage', name + '.bc7'), os.path.join(PACK, name + '.bc7')) if os.path.exists(q)), None)
        hd = read_bc7_level0(path) if path else None
        if hd is None or hd.shape[:2] != (hh * S, w * S):
            part = np.asarray(h.part(p['block'], p['pal']).resize((w * S, hh * S), Image.NEAREST))
            rgb, opaque = part[..., :3], part[..., 3] > 0
        else:
            tw, th = (w - 1) * S if w > 1 else w * S, (hh - 1) * S if hh > 1 else hh * S
            rgb = np.asarray(Image.fromarray(np.ascontiguousarray(hd[:th, :tw, :3])).resize((w * S, hh * S), Image.LANCZOS))
            keep = (~(hd[:th, :tw] == 0).all(-1)).astype(np.uint8) * 255
            opaque = np.asarray(Image.fromarray(keep).resize((w * S, hh * S), Image.NEAREST)) > 0
        if p['flipx']:
            rgb, opaque = rgb[:, ::-1], opaque[:, ::-1]
        if p['flipy']:
            rgb, opaque = rgb[::-1], opaque[::-1]
        X, Y = (p['x'] - x0) * S, (p['y'] - y0) * S
        out[Y:Y + hh * S, X:X + w * S][opaque] = rgb[opaque]
    sprite = np.asarray(frame.resize((frame.width * S, frame.height * S), Image.NEAREST))
    pixel = np.zeros_like(out)
    pixel[:] = (255, 0, 255)
    pixel[sprite[..., 3] > 0] = sprite[..., :3][sprite[..., 3] > 0]
    return Image.fromarray(pixel), Image.fromarray(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', action='store_true')
    a = ap.parse_args()
    target, source = Hero(TARGET), Hero(SOURCE)
    matches = match_frames(target, source)
    print(f'{len(matches)} frames of {TARGET_SET}, each a frame of the battle set:', {fi: m[0] for fi, m in matches.items()})
    inst = os.path.join(HERE, 'inst')
    work = os.path.join(inst, 'work')
    os.makedirs(work, exist_ok=True)
    composites(target, matches, work)
    if os.path.isdir(os.path.join(inst, 'parts')):
        shutil.rmtree(os.path.join(inst, 'parts'))
    tag = os.path.relpath(inst, os.path.join(ROOT, 'ai')).replace('\\', '/')
    sys.argv = ['batch_redraw.py', 'slice', '--heroes', tag, '--hero-dir', TARGET, '--scale', '8', '--exact-mask', '--ring', '0',
                '--uv-compensate', '--only', ','.join(f'{TARGET_SET}:{fi}' for fi in sorted(matches))]
    batch_redraw.main()
    names = stage_parts(inst)
    pairs = [game_frame(target, fi) for fi in PREVIEW]
    sheet = Image.new('RGB', (sum(p.width + 16 for p, _ in pairs), max(p.height for p, _ in pairs) * 2 + 16), (40, 40, 40))
    x = 0
    for low, high in pairs:
        sheet.paste(low, (x, 0))
        sheet.paste(high, (x, sheet.height // 2 + 8))
        x += low.width + 16
    sheet.save(os.path.join(HERE, 'preview.png'))
    new = [n for n in names if not os.path.exists(os.path.join(PACK, n + '.bc7')) and not os.path.exists(os.path.join(PACK, n + '.png'))]
    print(f'{len(names)} names, {len(new)} not in the pack; preview.png (top: the sprite, bottom: as the game will show it)')
    if not a.install:
        return
    if retroarch_running():
        sys.exit('RetroArch is running - close it first')
    for n in new:
        shutil.copyfile(os.path.join(HERE, 'stage', n + '.bc7'), os.path.join(PACK, n + '.bc7'))
    with open(os.path.join(HERE, 'installed.txt'), 'a') as f:
        f.writelines(n + '.bc7\n' for n in new)
    print(f'installed {len(new)} files into {PACK}; the list: installed.txt')


if __name__ == '__main__':
    main()
