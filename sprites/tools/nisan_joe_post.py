"""After the pod run of ai/redraw/nisan_joe (nisan_joe_build.py): slice the renders, then install Marguerite's parts and Big Joe's rect files.

  python nisan_joe_post.py post       res/v4 + the reused renders -> prod_post.py -> ai/prod_work/<group>/parts
  python nisan_joe_post.py sheet <out dir>     sprite | sliced frame, as the game draws it, one sheet per group
  python nisan_joe_post.py install    (RetroArch closed) parts -> seam fill -> BC7 -> pack; names in pod/report/nisan_joe_written.txt
Big Joe goes through battle_rects.py. Existing pack files stay: a name shared with another set keeps its current picture.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'eyepatch_fix'))
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402
from ai_redraw import Hero  # noqa: E402
from alias_dump_parts import PACK  # noqa: E402
from fix_apply import retroarch_running  # noqa: E402
from nisan_joe_build import G_JOE, G_MARGIE, JOE, MARGIE, OLD_RES  # noqa: E402
from patch_game import game_part  # noqa: E402
from seam_fill import fill_interior, frame_interior  # noqa: E402

DIR = os.path.join(ROOT, 'ai', 'redraw', 'nisan_joe')
RES = os.path.join(DIR, 'res')
WORK = os.path.join(ROOT, 'ai', 'prod_work')
WRITTEN = os.path.join(ROOT, 'pod', 'report', 'nisan_joe_written.txt')
# Big Joe: the head pass drew a second head on the collar, the full render is right
JOE_NO_HEAD = (8, 20)
# Big Joe: a blue can, not the character; the LoRA drew his parts on it, so it stays native
JOE_NATIVE = '63-68'
S = 8


def post():
    reuse = json.load(open(os.path.join(DIR, 'reuse.json')))
    for new, old in reuse.items():
        shutil.copyfile(os.path.join(OLD_RES, old + '.png'), os.path.join(RES, 'v4', new + '.png'))
    print('reused renders', len(reuse))
    os.makedirs(os.path.join(RES, 'no_head'), exist_ok=True)
    for fi in JOE_NO_HEAD:
        f = os.path.join(RES, 'v4', f'{G_JOE}__npc_{fi:03d}__head.png')
        if os.path.exists(f):
            os.replace(f, os.path.join(RES, 'no_head', os.path.basename(f)))
    subprocess.run([sys.executable, os.path.join(HERE, 'prod_post.py'), '--prod', DIR, '--res', RES, '--only', f'{G_MARGIE},{G_JOE}', '--workers', '2'], check=True)


def game_frame(h, s, fi, parts, k, cache):
    pl = h.placements(s, fi)
    x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
    W, H = max(p['x'] + p['w'] for p in pl) - x0, max(p['y'] + p['h'] for p in pl) - y0
    out = Image.new('RGBA', (W * k, H * k), (0, 0, 0, 0))
    for p in pl:
        nm = f"{p['block']}-{p['pal']}"
        if nm not in cache:
            f = os.path.join(parts, nm + '.png')
            if os.path.exists(f):
                a = np.asarray(Image.open(f).convert('RGBA'))
                cache[nm] = game_part(a, p['w'], p['h'], k)
            else:
                cache[nm] = h.part(p['block'], p['pal']).convert('RGBA').resize((p['w'] * k, p['h'] * k), Image.NEAREST)
        im = cache[nm]
        if p['flipx']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        out.alpha_composite(im, ((p['x'] - x0) * k, (p['y'] - y0) * k))
    return out


def sheet(out_dir):
    k = 4
    for g, hd, tag in ((G_MARGIE, MARGIE, 'margie'), (G_JOE, JOE, 'joe')):
        h = Hero(hd)
        s = list(h.layout)[0]
        parts = os.path.join(WORK, g, 'parts')
        cache, cells = {}, []
        for fi in range(len(h.layout[s]['frames'])):
            try:
                old, _ = h.assemble(h.placements(s, fi))
            except Exception:  # noqa: BLE001  (empty frame)
                continue
            cells.append((fi, old.resize((old.width * 2, old.height * 2), Image.NEAREST), game_frame(h, s, fi, parts, k, cache)))
        W, x, y, rh, pos = 1990, 4, 4, 0, []
        pages = []
        for fi, o, n in cells:
            w = o.width + n.width + 8
            if x + w > W:
                x, y, rh = 4, y + rh + 14, 0
            if y + n.height + 14 > 1450 and pos:
                pages.append(pos)
                x, y, rh, pos = 4, 4, 0, []
            pos.append((fi, o, n, x, y))
            x += w
            rh = max(rh, n.height)
        pages.append(pos)
        for pi, pg in enumerate(pages, 1):
            H = max(p[4] + p[2].height + 16 for p in pg)
            c = Image.new('RGB', (W, H), (150, 170, 90))
            d = ImageDraw.Draw(c)
            for fi, o, n, x, y in pg:
                d.text((x, y), str(fi), fill=(255, 255, 0))
                c.paste(o, (x, y + 12), o)
                c.paste(n, (x + o.width + 2, y + 12), n)
            f = os.path.join(out_dir, f'{tag}_{pi}.png')
            c.save(f)
            print(f, c.size, len(pg))


def install():
    if retroarch_running():
        raise SystemExit('RetroArch is running - close it first')
    parts = os.path.join(WORK, G_MARGIE, 'parts')
    lay = json.load(open(os.path.join(MARGIE, 'layout.json')))
    lay = lay[list(lay)[0]]
    inner = frame_interior([(lay, MARGIE)], lambda h, k: os.path.join(h, 'parts'))
    written, kept, failed = [], 0, 0
    for f in sorted(os.listdir(parts)):
        if not f.endswith('.png'):
            continue
        blk, pal = f[:-4].split('-')
        dst = os.path.join(PACK, f[:-4] + '.bc7')
        if os.path.exists(dst):
            kept += 1
            continue
        a = np.asarray(Image.open(os.path.join(parts, f)).convert('RGBA')).astype(np.int16)
        a, _ = fill_interior(a, None, S, a[..., 3] == 0, inner.get((blk, pal)))
        lv, flags = bc7pack.levels_of(np.ascontiguousarray(a.astype(np.uint8)))
        enc, bad, _ = bc7pack.encode_levels(lv)
        if bad:
            failed += 1
            continue
        with open(dst + '.tmp', 'wb') as o:
            o.write(bc7pack.pack_file(enc, a.shape[1], a.shape[0], flags))
        os.replace(dst + '.tmp', dst)
        written.append(f[:-4])
    with open(WRITTEN, 'a', encoding='utf-8') as o:
        o.writelines(n + '\n' for n in written)
    print(f'marguerite: written {len(written)}, already in the pack {kept}, BC7 failed {failed}')
    subprocess.run([sys.executable, os.path.join(HERE, 'battle_rects.py'), os.path.basename(JOE), G_JOE, '--skip-frames', JOE_NATIVE], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['post', 'sheet', 'install'])
    ap.add_argument('out', nargs='?')
    a = ap.parse_args()
    if a.cmd == 'post':
        post()
    elif a.cmd == 'sheet':
        sheet(a.out)
    else:
        install()


if __name__ == '__main__':
    main()
