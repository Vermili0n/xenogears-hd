"""AI redraw of hero frames and slicing back into Beetle replacement parts.

Per frame: assemble from parts (layout.json) -> smooth 8x base (xBR 4x + lanczos 2x) on a flat
background -> stable-diffusion.cpp img2img + ControlNet tile -> back to 4x, cut by silhouette ->
slice into parts by layout (visible pixels from the redraw, hidden ones from the xBR base).
Per part the candidate with the largest visible share wins. Output: 4x RGBA parts named
<texhash>-<palhash>.png with the 0/128 alpha the HD pack uses.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upscale_parts import fill_transparent  # noqa: E402

SCALE = 4          # replacement scale (pack convention)
GEN = 2            # extra factor for generation (8x total)
BG = (232, 232, 232)
OPAQUE = 128


def xbr4(rgba):
    """xBR 4x of a native RGBA image -> (rgb4 uint8 HxWx3, mask4 bool)."""
    a = np.asarray(rgba)
    mask = a[..., 3] > 0
    rgb = fill_transparent(a[..., :3], mask) if mask.any() else a[..., :3]
    with tempfile.TemporaryDirectory() as t:
        ci, co, mi, mo = (os.path.join(t, n) for n in ('c.png', 'c4.png', 'm.png', 'm4.png'))
        Image.fromarray(rgb, 'RGB').save(ci)
        Image.fromarray(np.repeat((mask * 255).astype(np.uint8)[..., None], 3, 2), 'RGB').save(mi)
        for s, d in ((ci, co), (mi, mo)):
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', s, '-vf', 'xbr=4', '-pix_fmt', 'rgb24', d],
                           check=True, stdin=subprocess.DEVNULL)
        c4 = np.asarray(Image.open(co).convert('RGB')).copy()
        m4 = np.asarray(Image.open(mo).convert('L')) > 127
    return c4, m4


def erode(mask, r):
    out = mask.copy()
    for _ in range(r):
        m = out.copy()
        m[1:] &= out[:-1]
        m[:-1] &= out[1:]
        m[:, 1:] &= out[:, :-1]
        m[:, :-1] &= out[:, 1:]
        out = m
    return out


class Hero:
    def __init__(self, root):
        self.root = root
        with open(os.path.join(root, 'layout.json')) as f:
            self.layout = json.load(f)
        self.cache = {}

    def part(self, block, pal):
        key = (block, pal)
        if key not in self.cache:
            self.cache[key] = Image.open(os.path.join(self.root, 'parts', f'{block}-{pal}.png')).convert('RGBA')
        return self.cache[key]

    def placements(self, setkey, fi):
        s = self.layout[setkey]
        out = []
        for p in s['frames'][fi]:
            pal = s['palettes'][min(p['clut'], len(s['palettes']) - 1)]
            img = self.part(p['block'], pal)
            out.append({**p, 'pal': pal, 'w': img.width, 'h': img.height,
                        'x': p['dx'] + p['mx'], 'y': p['dy'] + p['my']})
        return out

    def assemble(self, places):
        """Native frame (RGBA) and its origin offset (min x, min y)."""
        x0 = min(p['x'] for p in places)
        y0 = min(p['y'] for p in places)
        x1 = max(p['x'] + p['w'] for p in places)
        y1 = max(p['y'] + p['h'] for p in places)
        img = Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0))
        for p in places:
            im = self.part(p['block'], p['pal'])
            if p['flipx']:
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            if p['flipy']:
                im = im.transpose(Image.FLIP_TOP_BOTTOM)
            img.alpha_composite(im, (p['x'] - x0, p['y'] - y0))
        return img, (x0, y0)


def sd_redraw(base_rgb, mask, args, workdir, tag):
    """img2img on an 8x canvas padded to multiples of 64; returns 8x RGB of the original size."""
    h, w = base_rgb.shape[:2]
    W, H = -(-w // 64) * 64, -(-h // 64) * 64
    canvas = np.full((H, W, 3), BG, np.uint8)
    ox, oy = (W - w) // 2, (H - h) // 2
    region = canvas[oy:oy + h, ox:ox + w]
    region[mask] = base_rgb[mask]
    init = os.path.join(workdir, f'{tag}_init.png')
    out = os.path.join(workdir, f'{tag}_out.png')
    Image.fromarray(canvas, 'RGB').save(init)
    cmd = [args.sd, '-M', 'img_gen', '-m', args.model, '-i', init, '-o', out,
           '-p', args.prompt, '-n', args.negative,
           '--strength', str(args.strength), '--cfg-scale', str(args.cfg), '--steps', str(args.steps),
           '--sampling-method', args.sampler, '--scheduler', args.scheduler, '-s', str(args.seed),
           '-W', str(W), '-H', str(H), '--clip-skip', str(getattr(args, 'clip_skip', 2))]
    if args.controlnet:
        cmd += ['--control-net', args.controlnet, '--control-image', init,
                '--control-strength', str(args.control_strength)]
    if args.ip_adapter and args.ip_image:
        cmd += ['--ip-adapter', args.ip_adapter, '--clip_vision', args.clip_vision,
                '--ip-adapter-image', args.ip_image, '--ip-adapter-strength', str(args.ip_strength)]
    cmd += args.extra.split() if args.extra else []
    subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL if not args.verbose else None,
                   stderr=subprocess.DEVNULL if not args.verbose else None)
    res = np.asarray(Image.open(out).convert('RGB'))
    return res[oy:oy + h, ox:ox + w]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero-dir', required=True)
    ap.add_argument('--set', required=True)
    ap.add_argument('--frames', required=True, help='comma list or a-b ranges')
    ap.add_argument('--out', required=True)
    ap.add_argument('--sd', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--controlnet')
    ap.add_argument('--prompt', required=True)
    ap.add_argument('--negative', default='lowres, blurry, pixelated, jpeg artifacts, deformed, extra limbs, '
                                          'bad anatomy, text, watermark, signature, background scenery')
    ap.add_argument('--strength', type=float, default=0.5)
    ap.add_argument('--control-strength', type=float, default=0.8)
    ap.add_argument('--cfg', type=float, default=6.0)
    ap.add_argument('--steps', type=int, default=24)
    ap.add_argument('--sampler', default='dpm++2m')
    ap.add_argument('--scheduler', default='karras')
    ap.add_argument('--seed', type=int, default=1234)
    ap.add_argument('--ring', type=int, default=2, help='outline width (4x px) kept from the base')
    ap.add_argument('--ip-adapter', help='IP-Adapter model (character/face reference)')
    ap.add_argument('--clip-vision', help='CLIP vision encoder for the IP-Adapter')
    ap.add_argument('--ip-image', help='reference image (dialogue portrait or a canonical redrawn frame)')
    ap.add_argument('--ip-strength', type=float, default=0.6)
    ap.add_argument('--extra', default='', help='extra sd-cli arguments')
    ap.add_argument('--gen', type=int, default=2, help='generation scale on top of 4x (2 -> 8x, 4 -> 16x)')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    frames = []
    for tok in args.frames.split(','):
        if '-' in tok:
            a, b = tok.split('-')
            frames += list(range(int(a), int(b) + 1))
        else:
            frames.append(int(tok))
    hero = Hero(args.hero_dir)
    os.makedirs(os.path.join(args.out, 'frames'), exist_ok=True)
    os.makedirs(os.path.join(args.out, 'parts'), exist_ok=True)
    work = os.path.join(args.out, 'work')
    os.makedirs(work, exist_ok=True)
    best = {}  # name -> (visible share, image)
    xbr_cache = {}
    for fi in frames:
        places = hero.placements(args.set, fi)
        if not places:
            continue
        frame, (x0, y0) = hero.assemble(places)
        c4, m4 = xbr4(frame)
        GEN = args.gen
        base8 = np.asarray(Image.fromarray(c4).resize((c4.shape[1] * GEN, c4.shape[0] * GEN), Image.LANCZOS))
        mask8 = np.asarray(Image.fromarray((m4 * 255).astype(np.uint8)).resize(
            (m4.shape[1] * GEN, m4.shape[0] * GEN), Image.LANCZOS)) > 127
        red8 = sd_redraw(base8, mask8, args, work, f'{args.set}_{fi:03d}')
        red4 = np.asarray(Image.fromarray(red8).resize((c4.shape[1], c4.shape[0]), Image.LANCZOS)).copy()
        # keep the original dark outline: outer ring of the silhouette comes from the xBR base
        ring = m4 & ~erode(m4, args.ring)
        red4[ring] = c4[ring]
        # save the redrawn frame for review
        rgba = np.dstack([red4, np.where(m4, 255, 0).astype(np.uint8)])
        Image.fromarray(rgba, 'RGBA').save(os.path.join(args.out, 'frames', f'{args.set}_{fi:03d}.png'))
        base_rgba = np.dstack([c4, np.where(m4, 255, 0).astype(np.uint8)])
        Image.fromarray(base_rgba, 'RGBA').save(os.path.join(args.out, 'frames', f'{args.set}_{fi:03d}_base.png'))
        # coverage map: which placement owns each 4x pixel (last drawn wins)
        H4, W4 = m4.shape
        owner = np.full((H4, W4), -1, np.int32)
        pmasks = []
        for k, p in enumerate(places):
            key = (p['block'], p['pal'])
            if key not in xbr_cache:
                xbr_cache[key] = xbr4(hero.part(p['block'], p['pal']))
            pc4, pm4 = xbr_cache[key]
            if p['flipx']:
                pc4, pm4 = pc4[:, ::-1], pm4[:, ::-1]
            if p['flipy']:
                pc4, pm4 = pc4[::-1], pm4[::-1]
            X, Y = (p['x'] - x0) * SCALE, (p['y'] - y0) * SCALE
            h, w = pm4.shape
            sub = owner[Y:Y + h, X:X + w]
            sub[pm4[:sub.shape[0], :sub.shape[1]]] = k
            pmasks.append((pc4, pm4, X, Y))
        for k, p in enumerate(places):
            pc4, pm4, X, Y = pmasks[k]
            h, w = pm4.shape
            vis = np.zeros_like(pm4)
            vis[:min(h, H4 - Y), :min(w, W4 - X)] = owner[Y:Y + h, X:X + w] == k
            vis &= pm4
            col = pc4.copy()
            if vis.any():
                col[vis] = red4[Y:Y + h, X:X + w][vis]
            # back to the part's own orientation
            if p['flipx']:
                col, pm, vv = col[:, ::-1], pm4[:, ::-1], vis[:, ::-1]
            else:
                pm, vv = pm4, vis
            if p['flipy']:
                col, pm, vv = col[::-1], pm[::-1], vv[::-1]
            share = vv.sum() / max(1, pm.sum())
            name = f"{p['block']}-{p['pal']}"
            if name not in best or share > best[name][0]:
                best[name] = (share, np.dstack([col, np.where(pm, OPAQUE, 0).astype(np.uint8)]))
        print(f'frame {fi}: parts={len(places)}', flush=True)
    for name, (share, img) in best.items():
        Image.fromarray(np.ascontiguousarray(img), 'RGBA').save(os.path.join(args.out, 'parts', name + '.png'))
    print(f'parts written: {len(best)}')


if __name__ == '__main__':
    main()
