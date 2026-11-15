"""Run FLUX.2 klein 4B (sd.cpp) over a job list: control sprite + identity reference -> redraw. Resumable.

  python klein_batch.py --jobs ai/klein_npc/jobs.json [--lora name:weight]
job = {nid, frame, grid, ref}; control = ai/klein_npc/<nid>/in/grid_<grid>.png; output ai/klein_npc/<nid>/out/<grid>.png
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M = os.path.join(HERE, 'models')
PROMPT = ("Image 1 is a low-resolution pixel-art sprite. Image 2 is the same character, already redrawn. "
          "Redraw image 1 in exactly the style of image 2, with the same hair, face, clothes and colors as image 2. "
          "Keep exactly the pose, silhouette and position of image 1. Flat magenta background.")


def bbox(img):
    a = np.asarray(img).astype(int)
    ys, xs = np.nonzero((abs(a[..., 0] - 255) + a[..., 1] + abs(a[..., 2] - 255)) > 40)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def crop_box(imgs, size=512, margin=16, mult=64):
    """Common box around the sprites in all images: fewer tokens for the model, same placement on paste-back."""
    bs = [bbox(i) for i in imgs]
    x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
    x1, y1 = max(b[2] for b in bs), max(b[3] for b in bs)
    w = min(size, -(-(x1 - x0 + 2 * margin) // mult) * mult)
    h = min(size, -(-(y1 - y0 + 2 * margin) // mult) * mult)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    bx = max(0, min(size - w, cx - w // 2))
    by = max(0, min(size - h, cy - h // 2))
    return bx, by, bx + w, by + h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', required=True)
    ap.add_argument('--root', default=os.path.join(ROOT, 'ai', 'klein_npc'))
    ap.add_argument('--steps', type=int, default=4)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--lora', default='')
    ap.add_argument('--no-crop', action='store_true')
    ap.add_argument('--out-name', default='out')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--no-ref', action='store_true', help='control image only (LoRA mode), prompt = job["prompt"] or --prompt')
    ap.add_argument('--prompt', default='')
    ap.add_argument('--cfg', default='1.0')
    ap.add_argument('--model', default='flux-2-klein-4b-Q4_0.gguf')
    a = ap.parse_args()
    jobs = json.load(open(os.path.join(ROOT, a.jobs)))
    t0 = time.time()
    done = 0
    for i, j in enumerate(jobs):
        d = os.path.join(a.root, j['nid'])
        out = os.path.join(d, a.out_name, j['grid'] + '.png')
        if os.path.exists(out):
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if a.limit and done >= a.limit:
            break
        prompt = (f"<lora:{a.lora}> " if a.lora else '') + (j.get('prompt') or a.prompt or PROMPT)
        ctrl_p, ref_p = os.path.join(d, 'in', f"grid_{j['grid']}.png"), os.path.join(ROOT, j['ref'])
        ctrl, ref = Image.open(ctrl_p).convert('RGB'), Image.open(ref_p).convert('RGB')
        box = (0, 0, 512, 512) if a.no_crop else crop_box([ctrl, ref])
        tmp = out[:-4] + '_tmp'
        ctrl.crop(box).save(tmp + '_c.png')
        ref.crop(box).save(tmp + '_r.png')
        refs = ['-r', tmp + '_c.png'] + ([] if a.no_ref else ['-r', tmp + '_r.png'])
        cmd = [os.path.join(HERE, 'sdcpp', 'sd-cli.exe'), '--diffusion-model', os.path.join(M, a.model),
               '--vae', os.path.join(M, 'flux2_full_encoder_small_decoder.safetensors'), '--llm', os.path.join(M, 'Qwen3-4B-Q4_K_M.gguf'),
               *refs,
               '-p', prompt, '--cfg-scale', a.cfg, '--sampling-method', 'euler', '--steps', str(a.steps),
               '-W', str(box[2] - box[0]), '-H', str(box[3] - box[1]), '--offload-to-cpu', '--diffusion-fa', '--sage-attn',
               '-s', str(a.seed), '-o', tmp + '_o.png']
        if a.lora:
            cmd += ['--lora-model-dir', os.path.join(ROOT, 'lora', 'klein')]
        r = subprocess.run(cmd, capture_output=True, text=True)
        done += 1
        if os.path.exists(tmp + '_o.png'):
            canvas = Image.new('RGB', (512, 512), (255, 0, 255))
            canvas.paste(Image.open(tmp + '_o.png').convert('RGB'), box[:2])
            canvas.save(out)
        for suf in ('_c.png', '_r.png', '_o.png'):
            if os.path.exists(tmp + suf):
                os.remove(tmp + suf)
        if r.returncode or not os.path.exists(out):
            print('FAIL', j['nid'], j['frame'], r.stderr[-300:], flush=True)
        el = time.time() - t0
        print(f"{i + 1}/{len(jobs)} {j['nid']}:{j['frame']}  {el / done:.0f}s/frame  ETA {el / done * (len(jobs) - i - 1) / 3600:.1f}h", flush=True)
    print('KLEIN BATCH DONE', flush=True)


if __name__ == '__main__':
    main()
