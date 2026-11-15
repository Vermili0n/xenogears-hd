r"""The twelve parts of the frames with a block '0', from the picked renders to the pack (15.11.2026).

  python ai\redraw\zero_block\install.py              compose, slice, BC7 + seam fill into stage\, preview.png
  python ai\redraw\zero_block\install.py --install    the same, then the staged .bc7 copied into the pack (RetroArch closed)
The production's own steps (prod_post.py: compose_set -> batch_redraw slice -> BC7, seam fill), run for these frames
only and writing only the names in WANTED: every other part of these frames is in the pack already, and nothing of
ai/prod, ai/prod_work or the rest of the pack is touched (fix_apply.py would rebuild the whole h_bart group).
- ai_redraw.Hero leaves block '0' out here (see make_job.py), or compose and slice raise on these frames.
- PICKED: the renders the user chose on to_install.png (Citan: seed 7; Bart: seed 11, his head repainted after the
  sketch, strength 0.55 seed 23).
- Citan's field run 429_0:93 and 429_0:97 need no render: they are the world map set's 3924_0:33 / 3924_0:37 without
  the head, texel for texel (checked below), so their composites are cut from the production's.
Undo: delete from the pack the files listed in installed.txt (none of the names existed before).
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
TOOLS = os.path.join(ROOT, 'tools')
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import ai_redraw  # noqa: E402
import batch_redraw  # noqa: E402
import bc7pack  # noqa: E402
import compose_set  # noqa: E402
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from elly934_finalize import write_bc7_from_psx  # noqa: E402
from fix_apply import retroarch_running  # noqa: E402
from seam_fill import fill_interior, frame_interior  # noqa: E402

S = 8
PICKED = {
    'h_citan__3924_0_039': 'res_7/v4', 'h_citan__3924_0_039__head': 'res_7/v4', 'h_citan__2991_0_116': 'res_7/v4',
    'h_bart__430_0_070': 'res_11/v4', 'h_bart__430_0_070__head': 'bart_eye/res_055_23/v4',
}
# hero -> (frames sliced, the names written)
HEROES = {
    'citan': (['429_0:93', '429_0:97', '3924_0:39', '2991_0:116'],
              ['4c19563e-9694422f', '93b3328f-9694422f', '938162c3-9694422f', '69375a47-9694422f', 'f5c68a74-9694422f',
               '52d944e6-177a4dc6', '98658317-177a4dc6', '5d4aab65-177a4dc6', 'd8d0f8aa-177a4dc6']),
    'bart': (['430_0:70'], ['c2be06fd-84f5630b', 'ef212788-84f5630b', '9e3e77d0-84f5630b']),
}
# field frame <- the world map frame whose composite the production has
FROM_WORLD_MAP = {('429_0', 93): ('3924_0', 33), ('429_0', 97): ('3924_0', 37)}
PREVIEW = [('citan', '429_0', 93), ('citan', '429_0', 97), ('citan', '429_0', 99), ('citan', '3924_0', 39),
           ('citan', '2991_0', 116), ('bart', '430_0', 70)]


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
    sys.argv = [module.__name__ + '.py'] + list(argv)
    module.main()


def hero_dir(hero):
    return os.path.join(ROOT, 'extracted', 'disc1_full', hero)


def cut_from_world_map(work):
    h = ai_redraw.Hero(hero_dir('citan'))
    for (fs, ff), (ws, wf) in FROM_WORLD_MAP.items():
        field, (fx, fy) = h.assemble(h.placements(fs, ff))
        world, (wx, wy) = h.assemble(h.placements(ws, wf))
        dx, dy = fx - wx, fy - wy
        a, b = np.asarray(field), np.asarray(world)[dy:dy + field.height, dx:dx + field.width]
        opaque = a[..., 3] > 0
        if b.shape != a.shape or (a[opaque] != b[opaque]).any():
            sys.exit(f'{fs}:{ff} is not {ws}:{wf} without its head')
        red = Image.open(os.path.join(ROOT, 'ai', 'prod_work', 'h_citan', 'work', f'{ws}_{wf:03d}_red.png'))
        if red.size != (world.width * S, world.height * S):
            sys.exit(f'{ws}:{wf}: its composite is {red.size}, not {S}x the frame')
        red.crop((dx * S, dy * S, (dx + field.width) * S, (dy + field.height) * S)).save(os.path.join(work, f'{fs}_{ff:03d}_red.png'))
        print(f'{fs}:{ff} = {ws}:{wf} at {dx},{dy}: composite cut')


def stage_parts(hero, names, inst):
    """The wanted parts as .bc7 with their seams filled (seam_fill_all.one, on the staged file)."""
    hd = hero_dir(hero)
    lay = json.load(open(os.path.join(hd, 'layout.json')))
    inner = frame_interior([(v, hd) for v in lay.values()], lambda h, k: os.path.join(h, 'parts'))
    for d in ('png', 'bc7'):
        os.makedirs(os.path.join(HERE, 'stage', d), exist_ok=True)
    for name in names:
        src = os.path.join(inst, 'parts', name + '.png')
        if not os.path.exists(src):
            sys.exit(f'{name}: the slice did not write it')
        png = os.path.join(HERE, 'stage', 'png', name + '.png')
        shutil.copyfile(src, png)
        dst = os.path.join(HERE, 'stage', 'bc7', name + '.bc7')
        _, res, info, _ = bc7pack.convert_one((png, dst))
        if res != 'ok':
            sys.exit(f'{name}: BC7 {res} {info}')
        block, pal = name.split('-')
        hdp = read_bc7_level0(dst).astype(np.int16)
        mask = inner.get((block, pal))
        filled = 0
        if mask is not None and mask.any() and hdp.shape[:2] == (mask.shape[0] * S, mask.shape[1] * S):
            out, filled = fill_interior(hdp, None, S, (hdp == 0).all(-1), mask)
            if filled:
                out[..., :3][(out[..., :3] == 0).all(-1) & ~(out == 0).all(-1)] = 1
                if not write_bc7_from_psx(dst, out):
                    sys.exit(f'{name}: BC7 after the seam fill failed')
        print(f'  {name}: {hdp.shape[1]}x{hdp.shape[0]}, seam fill {filled} px')


def hd_part(name):
    for path in (os.path.join(HERE, 'stage', 'bc7', name + '.bc7'), os.path.join(PACK, name + '.bc7')):
        if os.path.exists(path):
            return read_bc7_level0(path)
    return None


def game_frame(h, setkey, fi):
    """The frame as the game shows it: every part's picture stretched from its first (w-1) x (h-1) texels over the part
    (batch_redraw.uv_compensate's reverse); a part without a picture as its original texels, on magenta."""
    places = h.placements(setkey, fi)
    frame, (x0, y0) = h.assemble(places)
    out = np.zeros((frame.height * S, frame.width * S, 3), np.uint8)
    out[:] = (255, 0, 255)
    for p in places:
        w, hh = p['w'], p['h']
        hd = hd_part(f"{p['block']}-{p['pal']}")
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


def preview():
    pairs = []
    for hero, sk, fi in PREVIEW:
        pairs.append(game_frame(ai_redraw.Hero(hero_dir(hero)), sk, fi))
    W = sum(max(a.width, b.width) for a, b in pairs) + 16 * len(pairs)
    H = max(a.height for a, _ in pairs)
    sheet = Image.new('RGB', (W, H * 2 + 16), (40, 40, 40))
    x = 0
    for a, b in pairs:
        sheet.paste(a, (x, 0))
        sheet.paste(b, (x, H + 16))
        x += a.width + 16
    sheet.save(os.path.join(HERE, 'preview.png'))
    print('preview.png', sheet.size, '(top: the sprite, bottom: as the game will show it)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', action='store_true')
    a = ap.parse_args()
    ai_redraw.Hero.placements = placements_without_zero
    picked = os.path.join(HERE, 'picked')
    os.makedirs(picked, exist_ok=True)
    for name, src in PICKED.items():
        shutil.copyfile(os.path.join(HERE, src, name + '.png'), os.path.join(picked, name + '.png'))
    names_all = []
    for hero, (frames, names) in HEROES.items():
        inst = os.path.join(HERE, 'inst_' + hero)
        work = os.path.join(inst, 'work')
        os.makedirs(work, exist_ok=True)
        run(compose_set, '--render', HERE, '--res', picked, '--work', work, '--name', 'h_' + hero, '--out-scale', '8',
            '--offset-key', hero)
        print(hero, 'compose:', json.load(open(os.path.join(inst, 'compose.json'))))
        if hero == 'citan':
            cut_from_world_map(work)
        tag = os.path.relpath(inst, os.path.join(ROOT, 'ai')).replace('\\', '/')
        run(batch_redraw, 'slice', '--heroes', tag, '--hero-dir', hero_dir(hero), '--scale', '8', '--exact-mask', '--ring', '0',
            '--uv-compensate', '--only', ','.join(frames))
        stage_parts(hero, names, inst)
        names_all += names
    preview()
    if not a.install:
        return
    if retroarch_running():
        sys.exit('RetroArch is running - close it first')
    there = [n for n in names_all if os.path.exists(os.path.join(PACK, n + '.bc7')) or os.path.exists(os.path.join(PACK, n + '.png'))]
    if there:
        sys.exit('already in the pack (not overwritten): ' + ', '.join(there))
    for n in names_all:
        shutil.copyfile(os.path.join(HERE, 'stage', 'bc7', n + '.bc7'), os.path.join(PACK, n + '.bc7'))
    open(os.path.join(HERE, 'installed.txt'), 'w').write('\n'.join(n + '.bc7' for n in names_all) + '\n')
    print(f'installed {len(names_all)} files into {PACK}; the list: installed.txt')


if __name__ == '__main__':
    main()
