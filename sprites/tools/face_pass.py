"""Second pass for the head: crop the head region of a finished redraw, redraw it large with the character LoRA
and a view-specific reference (IP-Adapter), keep the original geometry via ControlNet tile, paste it back.

  python face_pass.py --hero fei --src-tag _it3 --out-tag _it3f --only 427_0:57@front,427_0:41@side --lora fei_lora:0.8

Input:  ai/<hero><src-tag>/work/<set>_<frame>_red.png (16x redraw from batch_redraw gen)
Output: ai/<hero><out-tag>/work/<set>_<frame>_red.png (same size, head replaced) + head_<tag>_{in,out}.png for review.
The head = topmost part of the frame (Xenogears sprites keep the head as its own piece), plus a margin.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import BG, Hero, xbr4  # noqa: E402

VIEW_TAGS = {
    'front': 'portrait, face, looking at viewer, front view, facing viewer, both eyes visible',
    'front34': 'portrait, face, three-quarter view, both eyes visible',
    'side': 'portrait, face, profile, from side',
    'back34': 'head, from behind, three-quarter back view',
    'back': 'head, from behind, back of head, ponytail',
}
VIEW_REF = {'front': 'fei_cg_face', 'front34': 'fei_cg_front', 'side': 'fei_cg_side',
            'back34': 'fei_cg_back', 'back': 'fei_cg_back'}


def head_box(places, origin, margin, neck):
    """Native-pixel box of the topmost part, expanded by margin (and neck below)."""
    top = min(places, key=lambda p: p['y'])
    x0, y0 = origin
    return (top['x'] - x0 - margin, top['y'] - y0 - margin,
            top['x'] - x0 + top['w'] + margin, top['y'] - y0 + top['h'] + margin + neck)


def run_sd(a, init, control, ref, prompt, out, W, H, seed):
    cmd = [a.sd, '-M', 'img_gen', '-m', a.model, '-i', init, '-o', out, '-p', prompt, '-n', a.negative,
           '--strength', str(a.strength), '--cfg-scale', str(a.cfg), '--steps', str(a.steps),
           '--sampling-method', 'dpm++2m', '--scheduler', 'karras', '-s', str(seed), '-W', str(W), '-H', str(H),
           '--clip-skip', '2', '--control-net', a.controlnet, '--control-image', control,
           '--control-strength', str(a.control_strength)]
    if a.lora:
        cmd += ['--lora-model-dir', a.lora_dir]
    if ref and a.ip_strength > 0:
        cmd += ['--ip-adapter', a.ip_adapter, '--clip_vision', a.clip_vision,
                '--ip-adapter-image', ref, '--ip-adapter-strength', str(a.ip_strength)]
    cmd += a.extra.split() if a.extra else []
    subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL,
                   stdout=None if a.verbose else subprocess.DEVNULL, stderr=None if a.verbose else subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', default='fei')
    ap.add_argument('--src-tag', required=True)
    ap.add_argument('--out-tag', required=True)
    ap.add_argument('--only', required=True, help='set:frame@view,... view in ' + ','.join(VIEW_TAGS))
    ap.add_argument('--gen', type=int, default=4, help='scale of *_red.png over 4x (as in batch_redraw)')
    ap.add_argument('--size', type=int, default=512, help='longest side of the head crop for SD')
    ap.add_argument('--margin', type=int, default=2, help='native px around the head part')
    ap.add_argument('--neck', type=int, default=4, help='extra native px below the head part')
    ap.add_argument('--strength', type=float, default=0.6)
    ap.add_argument('--control-strength', type=float, default=0.55)
    ap.add_argument('--ip-strength', type=float, default=0.4)
    ap.add_argument('--cfg', type=float, default=6.0)
    ap.add_argument('--steps', type=int, default=28)
    ap.add_argument('--seeds', default='1234')
    ap.add_argument('--lora', default='', help='name:weight')
    ap.add_argument('--lora-dir', default='')
    ap.add_argument('--feather', type=int, default=24, help='blend width at gen scale (px)')
    ap.add_argument('--fit', choices=['auto', 'gpu'], default='auto')
    ap.add_argument('--device', default='CUDA0')
    ap.add_argument('--extra', default='')
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args()
    if a.fit == 'gpu':
        a.extra = (a.extra + f' --params-backend diffusion={a.device},controlnet={a.device},vae={a.device},te=cpu --diffusion-fa').strip()
    cfg = json.load(open(os.path.join(HERE, 'heroes.json'), encoding='utf-8'))
    m = os.path.join(HERE, 'models')
    a.sd = os.path.join(HERE, 'sdcpp', 'sd-cli.exe')
    a.model = os.path.join(m, 'Counterfeit-V3.0_fix_fp16.safetensors')
    a.controlnet = os.path.join(m, 'control_v11f1e_sd15_tile_fp16.safetensors')
    a.ip_adapter = os.path.join(m, 'ip-adapter-plus_sd15.safetensors')
    a.clip_vision = os.path.join(m, 'clip_vision_vit_h.safetensors')
    a.lora_dir = a.lora_dir or os.path.join(ROOT, 'lora', a.hero)
    a.negative = cfg['_common']['negative']
    base_prompt = cfg['_common']['prefix'] + cfg[a.hero]['prompt']
    hobj = Hero(os.path.join(ROOT, 'extracted', 'disc1_full', a.hero))
    src = os.path.join(ROOT, 'ai', a.hero + a.src_tag, 'work')
    dst = os.path.join(ROOT, 'ai', a.hero + a.out_tag, 'work')
    os.makedirs(dst, exist_ok=True)
    G = 4 * a.gen
    for tok in a.only.split(','):
        tok, _, view = tok.partition('@')
        view = view or 'front'
        s, fi = tok.split(':')
        fi = int(fi)
        tag = f'{s}_{fi:03d}'
        places = hobj.placements(s, fi)
        frame, origin = hobj.assemble(places)
        c4, m4 = xbr4(frame)
        red = np.asarray(Image.open(os.path.join(src, f'{tag}_red.png')).convert('RGB')).copy()
        Hn, Wn = m4.shape[0] // 4, m4.shape[1] // 4
        bx0, by0, bx1, by1 = head_box(places, origin, a.margin, a.neck)
        bx0, by0, bx1, by1 = max(0, bx0), max(0, by0), min(Wn, bx1), min(Hn, by1)
        X0, Y0, X1, Y1 = bx0 * G, by0 * G, bx1 * G, by1 * G
        crop = red[Y0:Y1, X0:X1]
        # geometry reference: the original frame, xBR 4x upscaled to the gen scale
        base = np.asarray(Image.fromarray(c4).resize((red.shape[1], red.shape[0]), Image.LANCZOS))
        mfull = np.asarray(Image.fromarray((m4 * 255).astype(np.uint8)).resize(
            (red.shape[1], red.shape[0]), Image.LANCZOS)) > 127
        bcrop = base[Y0:Y1, X0:X1].copy()
        mc = mfull[Y0:Y1, X0:X1]
        h, w = crop.shape[:2]
        k = a.size / max(h, w)
        W, H = -(-int(w * k) // 64) * 64, -(-int(h * k) // 64) * 64
        sw, sh = int(round(w * k)), int(round(h * k))
        ox, oy = (W - sw) // 2, (H - sh) // 2

        def canvas(img):
            c = np.full((H, W, 3), BG, np.uint8)
            im = img.copy()
            im[~mc] = BG
            c[oy:oy + sh, ox:ox + sw] = np.asarray(Image.fromarray(im).resize((sw, sh), Image.LANCZOS))
            return c

        init = os.path.join(dst, f'head_{tag}_in.png')
        ctrl = os.path.join(dst, f'head_{tag}_ctrl.png')
        Image.fromarray(canvas(crop)).save(init)
        Image.fromarray(canvas(bcrop)).save(ctrl)
        ref = os.path.join(ROOT, 'ai', 'refs', VIEW_REF.get(view, 'fei_cg_face') + '.png')
        prompt = (f'<lora:{a.lora}>, ' if a.lora else '') + base_prompt + ', ' + VIEW_TAGS[view]
        for seed in map(int, a.seeds.split(',')):
            out = os.path.join(dst, f'head_{tag}_s{seed}.png')
            run_sd(a, init, ctrl, ref if os.path.exists(ref) else None, prompt, out, W, H, seed)
            res = np.asarray(Image.open(out).convert('RGB'))[oy:oy + sh, ox:ox + sw]
            res = np.asarray(Image.fromarray(res).resize((w, h), Image.LANCZOS))
            # feathered blend inside the silhouette: full weight in the middle of the box, fading to the edges
            wgt = Image.new('L', (w, h), 0)
            f = a.feather
            wgt.paste(255, (f if X0 > 0 else 0, f if Y0 > 0 else 0, w - f, h - f))
            wgt = np.asarray(wgt.filter(ImageFilter.GaussianBlur(f / 2))).astype(np.float32)[..., None] / 255
            outimg = red.copy()
            outimg[Y0:Y1, X0:X1] = (res * wgt + crop * (1 - wgt)).astype(np.uint8)
            suffix = '' if seed == int(a.seeds.split(',')[0]) else f'_s{seed}'
            Image.fromarray(outimg).save(os.path.join(dst, f'{tag}_red{suffix}.png'))
            print(f'{tag} {view} seed {seed}: head box native {bx1 - bx0}x{by1 - by0}, sd {W}x{H}', flush=True)


if __name__ == '__main__':
    main()
