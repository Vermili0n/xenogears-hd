"""Pod inference: FLUX.2 klein base + trained LoRA, control sprite (+ optional identity reference) -> redraw.

  python infer_pod.py --jobs jobs.json --lora output/xeno_klein/xeno_klein_000001500.safetensors --out out_1500 [--scale 1.0]
jobs.json: [{"name": .., "control": path, "ref": path or null, "prompt": ..}]  (paths relative to the jobs file)
--crop renders only the sprite box (margin 16, multiples of 64) and pastes it back on the 512 magenta canvas.
Resumable: existing outputs are skipped. --shard i/n renders every n-th job starting at i.
"""
import argparse
import json
import os
import time

import torch
from diffusers import Flux2KleinPipeline
from PIL import Image

MAG = (255, 0, 255)


def crop_box(img, margin=16, mult=64, size=512):
    px = img.load()
    xs, ys = [], []
    for y in range(0, size, 2):
        for x in range(0, size, 2):
            r, g, b = px[x, y]
            if not (r > 230 and g < 30 and b > 230):
                xs.append(x)
                ys.append(y)
    if not xs:
        return 0, 0, size, size
    x0, y0, x1, y1 = max(0, min(xs) - margin), max(0, min(ys) - margin), min(size, max(xs) + margin), min(size, max(ys) + margin)
    w = min(size, -(-(x1 - x0) // mult) * mult)
    h = min(size, -(-(y1 - y0) // mult) * mult)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    x0 = min(max(0, cx - w // 2), size - w)
    y0 = min(max(0, cy - h // 2), size - h)
    return x0, y0, x0 + w, y0 + h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', required=True)
    ap.add_argument('--lora', action='append', default=[], help='repeatable: several checkpoints in one run')
    ap.add_argument('--out', default='infer')
    ap.add_argument('--scale', type=float, default=1.0)
    ap.add_argument('--steps', type=int, default=28)
    ap.add_argument('--cfg', type=float, default=4.0)
    ap.add_argument('--crop', action='store_true')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--shard', default='0/1')
    ap.add_argument('--model', default='black-forest-labs/FLUX.2-klein-base-4B')
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.jobs))
    si, sn = map(int, a.shard.split('/'))
    jobs = json.load(open(a.jobs))[si::sn]
    pipe = Flux2KleinPipeline.from_pretrained(a.model, torch_dtype=torch.bfloat16).to('cuda')
    for lp in (a.lora or [None]):
        tag = os.path.basename(lp).split('_')[-1].split('.')[0].lstrip('0') if lp else 'base'
        out = f'{a.out}/{tag}'
        os.makedirs(out, exist_ok=True)
        if lp:
            pipe.unload_lora_weights()
            pipe.load_lora_weights(lp, adapter_name='xeno')
            pipe.set_adapters(['xeno'], adapter_weights=[a.scale])
        todo = [j for j in jobs if not os.path.exists(f"{out}/{j['name']}.png")]
        print(tag, 'jobs', len(jobs), 'todo', len(todo), flush=True)
        t0 = time.time()
        for k, j in enumerate(todo):
            ctrl = Image.open(os.path.join(base, j['control'])).convert('RGB')
            box = crop_box(ctrl) if a.crop else (0, 0, 512, 512)
            imgs = [ctrl.crop(box)]
            if j.get('ref'):
                imgs.append(Image.open(os.path.join(base, j['ref'])).convert('RGB'))
            g = torch.Generator('cuda').manual_seed(a.seed)
            im = pipe(prompt=j['prompt'], image=imgs, height=box[3] - box[1], width=box[2] - box[0],
                      num_inference_steps=a.steps, guidance_scale=a.cfg, generator=g).images[0]
            if a.crop:
                canvas = Image.new('RGB', (512, 512), MAG)
                canvas.paste(im, box[:2])
                im = canvas
            im.save(f"{out}/{j['name']}.png")
            if (k + 1) % 50 == 0 or k + 1 == len(todo):
                dt = (time.time() - t0) / (k + 1)
                print(f'{tag} {k + 1}/{len(todo)} {dt:.1f}s/img eta {dt * (len(todo) - k - 1) / 3600:.1f}h', flush=True)


if __name__ == '__main__':
    main()
